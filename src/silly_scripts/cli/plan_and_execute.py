"""Run a prompt through Claude in plan mode, then execute the resulting plan."""

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

EXECUTION_TOOLS = ["Read", "Edit", "Write", "Bash", "Glob", "Grep"]


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


async def run_plan_phase(prompt: str) -> str:
    """Run Claude in plan mode to create an execution plan.

    Args:
        prompt: The user's prompt describing the task.

    Returns:
        The session ID for resuming execution.

    Raises:
        click.ClickException: If the plan phase fails or returns no session ID.
    """
    session_id: str | None = None

    try:
        async for message in query(
            prompt=prompt,
            options=ClaudeAgentOptions(permission_mode="plan"),
        ):
            text = collect_text(message)
            if text:
                click.echo(text)

            if isinstance(message, ResultMessage):
                session_id = message.session_id
                logger.info(f"Plan completed. Session ID: {session_id}")
    except Exception as e:
        msg = f"Plan phase failed: {e}"
        raise click.ClickException(msg) from e

    if not session_id:
        msg = "Plan phase did not return a session ID"
        raise click.ClickException(msg)

    return session_id


async def run_execute_phase(session_id: str) -> None:
    """Resume the plan session and execute with full tool access.

    Args:
        session_id: The session ID from the plan phase.

    Raises:
        click.ClickException: If the execution phase fails.
    """
    try:
        async for message in query(
            prompt="Execute the plan",
            options=ClaudeAgentOptions(
                resume=session_id,
                permission_mode="bypassPermissions",
                allowed_tools=EXECUTION_TOOLS,
            ),
        ):
            text = collect_text(message)
            if text:
                click.echo(text)

            if isinstance(message, ResultMessage):
                logger.info(f"Execution completed: {message.subtype}")
    except Exception as e:
        msg = f"Execution phase failed: {e}"
        raise click.ClickException(msg) from e


async def plan_and_execute(prompt: str) -> None:
    """Run the full plan-then-execute workflow.

    Args:
        prompt: The user's prompt describing the task.
    """
    click.echo("=== Planning Phase ===")
    session_id = await run_plan_phase(prompt)

    click.echo("\n=== Execution Phase ===")
    await run_execute_phase(session_id)


@click.command()
@click.argument("prompt")
def main(prompt: str) -> None:
    """Run a prompt through Claude: first plan, then execute.

    PROMPT: The task description for Claude to plan and execute.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    asyncio.run(plan_and_execute(prompt))


if __name__ == "__main__":
    main()  # pragma: no cover
