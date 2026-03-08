"""Ask Claude a question using the Claude Agent SDK."""

import asyncio
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

import click
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKError,
    CLINotFoundError,
    ProcessError,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
    query,
)

from silly_scripts.settings import get_settings


logger = logging.getLogger(__name__)


def _resolve_prompt(prompt_arg: str | None, prompt_flag: str | None) -> str:
    """Resolve the prompt from positional arg, flag, or stdin.

    Args:
        prompt_arg: Positional argument value.
        prompt_flag: --prompt flag value.

    Returns:
        The resolved prompt string.

    Raises:
        click.UsageError: If no prompt is provided.
    """
    if prompt_arg:
        return prompt_arg
    if prompt_flag:
        return prompt_flag
    if not sys.stdin.isatty():
        text = sys.stdin.read().strip()
        if text:
            return text
    msg = (
        "No prompt provided. Pass a prompt as an argument, "
        "via --prompt, or pipe to stdin."
    )
    raise click.UsageError(msg)


def _parse_tools(tools_str: str) -> list[str]:
    """Parse a comma-separated tools string into a list.

    Args:
        tools_str: Comma-separated tool names (e.g. "Read,Glob,Grep").

    Returns:
        List of tool name strings.
    """
    return [t.strip() for t in tools_str.split(",") if t.strip()]


@click.command()
@click.argument("prompt", required=False, default=None)
@click.option(
    "--prompt",
    "-p",
    "prompt_flag",
    default=None,
    help="The prompt to send to Claude (alternative to positional argument).",
)
@click.option(
    "--model",
    "-m",
    default=None,
    help="Model to use (e.g. sonnet, opus, haiku).",
)
@click.option(
    "--tools",
    "-t",
    default=None,
    help="Allowed tools, comma-separated (e.g. Read,Glob,Grep).",
)
@click.option(
    "--system-prompt",
    default=None,
    help="Custom system prompt.",
)
@click.option(
    "--permission-mode",
    type=click.Choice(["default", "acceptEdits", "bypassPermissions"]),
    default="default",
    show_default=True,
    help="Permission mode for tool execution.",
)
@click.option(
    "--working-dir",
    "-C",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Working directory for the agent.",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Show all message types (tool calls, system).",
)
@click.option(
    "--json",
    "json_mode",
    is_flag=True,
    default=False,
    help="Output raw JSON messages (NDJSON).",
)
def main(
    prompt: str | None,
    prompt_flag: str | None,
    model: str | None,
    tools: str | None,
    system_prompt: str | None,
    permission_mode: str,
    working_dir: Path | None,
    verbose: bool,
    json_mode: bool,
) -> None:
    """Ask Claude a question using the Claude Agent SDK.

    Pass a prompt as a positional argument, via --prompt, or pipe from stdin.

    \b
    Examples:
        ask-claude "What files are in this directory?"
        ask-claude --prompt "Find TODO comments" --tools "Read,Glob,Grep"
        echo "Summarize this codebase" | ask-claude
        ask-claude "Fix the bug" -m opus --permission-mode acceptEdits
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    resolved_prompt = _resolve_prompt(prompt, prompt_flag)

    settings = get_settings()
    resolved_model = model or settings.claude_default_model
    resolved_tools = _parse_tools(tools or settings.claude_default_tools)

    logger.debug(f"Prompt: {resolved_prompt}")
    logger.debug(f"Model: {resolved_model}")
    logger.debug(f"Tools: {resolved_tools}")
    logger.debug(f"System prompt: {system_prompt}")
    logger.debug(f"Permission mode: {permission_mode}")
    logger.debug(f"Working dir: {working_dir}")
    logger.debug(f"JSON mode: {json_mode}")

    api_key = settings.anthropic_api_key
    if not api_key:
        msg = (
            "Anthropic API key not set. "
            "Export ANTHROPIC_API_KEY or add it to your .env file."
        )
        raise click.ClickException(msg)

    options = ClaudeAgentOptions(
        model=resolved_model,
        allowed_tools=resolved_tools,
        permission_mode=permission_mode,
        cwd=str(working_dir) if working_dir else None,
    )
    if system_prompt:
        options.system_prompt = system_prompt

    try:
        asyncio.run(
            _run_query(resolved_prompt, options, verbose=verbose, json_mode=json_mode)
        )
    except CLINotFoundError as exc:
        logger.debug("CLI not found", exc_info=True)
        msg = f"Claude Code CLI not found. Is it installed? ({exc})"
        raise click.ClickException(msg) from exc
    except ProcessError as exc:
        logger.debug("Process error", exc_info=True)
        msg = f"Claude process failed: {exc}"
        raise click.ClickException(msg) from exc
    except ClaudeSDKError as exc:
        logger.debug("SDK error", exc_info=True)
        msg = f"Claude SDK error: {exc}"
        raise click.ClickException(msg) from exc


async def _run_query(
    prompt: str,
    options: ClaudeAgentOptions,
    *,
    verbose: bool,
    json_mode: bool,
) -> None:
    """Send a prompt to Claude and stream output to stdout.

    Args:
        prompt: The user prompt to send.
        options: SDK options for the query.
        verbose: If True, show tool calls and system messages.
        json_mode: If True, output each message as NDJSON.
    """
    async for message in query(prompt=prompt, options=options):
        if json_mode:
            _print_json(message)
            continue

        if isinstance(message, AssistantMessage):
            _print_assistant(message, verbose=verbose)
        elif isinstance(message, SystemMessage) and verbose:
            click.echo(f"[system:{message.subtype}] {message.data}", err=True)
        elif isinstance(message, ResultMessage):
            logger.debug(
                f"Done: {message.num_turns} turns, "
                f"{message.duration_ms}ms, "
                f"cost=${message.total_cost_usd}"
            )
            if message.is_error:
                msg = f"Claude returned an error (session {message.session_id})."
                raise click.ClickException(msg)


def _print_assistant(message: AssistantMessage, *, verbose: bool) -> None:
    """Print assistant message content blocks to stdout.

    Args:
        message: The assistant message to print.
        verbose: If True, also print tool-use blocks.
    """
    for block in message.content:
        if isinstance(block, TextBlock):
            click.echo(block.text)
        elif isinstance(block, ToolUseBlock) and verbose:
            click.echo(
                f"[tool:{block.name}] {json.dumps(block.input, indent=2)}",
                err=True,
            )


def _print_json(message: object) -> None:
    """Print a message as a single NDJSON line to stdout.

    Args:
        message: The SDK message object to serialize.
    """
    try:
        data = asdict(message)  # type: ignore[arg-type]
    except TypeError:
        data = {"raw": str(message)}
    click.echo(json.dumps(data, default=str))


if __name__ == "__main__":
    main()  # pragma: no cover
