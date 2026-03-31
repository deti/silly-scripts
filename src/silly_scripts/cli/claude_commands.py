"""List all available Claude Code slash commands via the Claude Agent SDK."""

import asyncio
import logging

import click
from claude_agent_sdk import (
    ClaudeAgentOptions,
    SystemMessage,
    query,
)


logger = logging.getLogger(__name__)


async def fetch_commands() -> list[str]:
    """Fetch available slash commands from a local Claude Code instance.

    Starts a minimal Agent SDK session and extracts the slash_commands
    list from the init SystemMessage.

    Returns:
        List of slash command names.

    Raises:
        click.ClickException: If the Agent SDK query fails or no init
            message is received.
    """
    commands: list[str] | None = None
    try:
        async for message in query(
            prompt="List slash commands",
            options=ClaudeAgentOptions(max_turns=1),
        ):
            if (
                isinstance(message, SystemMessage)
                and message.subtype == "init"
                and commands is None
            ):
                commands = message.data.get("slash_commands", [])
    except Exception as e:
        msg = f"Failed to fetch available commands: {e}"
        raise click.ClickException(msg) from e

    if commands is None:
        msg = "No init message received from Claude Code"
        raise click.ClickException(msg)

    return commands


@click.command()
def main() -> None:
    """List all available Claude Code slash commands.

    Connects to a local Claude Code instance via the Agent SDK and
    extracts slash commands from the session init message.
    """
    logging.basicConfig(level=logging.INFO)

    logger.info("Fetching available Claude Code slash commands...")
    commands = asyncio.run(fetch_commands())

    if not commands:
        click.echo("No slash commands available.")
        return

    click.echo("Available slash commands:")
    for cmd in sorted(commands):
        click.echo(f"  {cmd}")


if __name__ == "__main__":
    main()  # pragma: no cover
