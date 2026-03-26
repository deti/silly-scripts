"""Display Claude Code usage information via the Claude Agent SDK."""

import asyncio
import logging

import click
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    query,
)


logger = logging.getLogger(__name__)


def collect_text(message: object) -> str:
    """Extract text content from an Agent SDK message.

    Args:
        message: An Agent SDK message object.

    Returns:
        Extracted text, or empty string if no text content.
    """
    parts: list[str] = []
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                parts.append(block.text)
    elif (
        isinstance(message, ResultMessage)
        and hasattr(message, "result")
        and message.result
    ):
        parts.append(message.result)
    return "\n".join(parts)


async def fetch_usage() -> str:
    """Invoke the /usage slash command on a local Claude Code instance.

    Returns:
        The usage information text from Claude.

    Raises:
        click.ClickException: If the Agent SDK query fails.
    """
    result_parts: list[str] = []
    try:
        async for message in query(
            prompt="/usage",
            options=ClaudeAgentOptions(max_turns=1),
        ):
            text = collect_text(message)
            if text:
                result_parts.append(text)
    except Exception as e:
        msg = f"Failed to fetch usage information: {e}"
        raise click.ClickException(msg) from e

    if not result_parts:
        msg = "No usage information returned from Claude Code"
        raise click.ClickException(msg)

    return "\n".join(result_parts)


@click.command()
def main() -> None:
    """Display Claude Code usage information.

    Connects to a local Claude Code instance via the Agent SDK and
    invokes the /usage slash command.
    """
    logging.basicConfig(level=logging.INFO)

    logger.info("Fetching Claude Code usage information...")
    result = asyncio.run(fetch_usage())
    click.echo(result)


if __name__ == "__main__":
    main()  # pragma: no cover
