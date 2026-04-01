"""Run a prompt through Fleet plan creation, analyze the plan, then execute it."""

import asyncio
import logging
import re

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


async def run_fleet_plan_phase(prompt: str) -> tuple[str, str]:
    """Invoke /fleet:fleet-plan create to generate a multi-crew plan.

    Args:
        prompt: The user's goal description.

    Returns:
        A tuple of (session_id, plan_text).

    Raises:
        click.ClickException: If the fleet plan phase fails or returns no
            session ID.
    """
    session_id: str | None = None
    plan_parts: list[str] = []

    fleet_prompt = f"/fleet:fleet-plan create\n\nGoal: {prompt}"
    # fleet_prompt = f"/fleet plan create\n\nGoal: {prompt}"

    try:
        async for message in query(
            prompt=fleet_prompt,
            options=ClaudeAgentOptions(
                permission_mode="bypassPermissions",
            ),
        ):
            text = collect_text(message)
            if text:
                plan_parts.append(text)
                click.echo(text)

            if isinstance(message, ResultMessage):
                session_id = message.session_id
                logger.info(f"Fleet plan completed. Session ID: {session_id}")
    except Exception as e:
        msg = f"Fleet plan phase failed: {e}"
        raise click.ClickException(msg) from e

    if not session_id:
        msg = "Fleet plan phase did not return a session ID"
        raise click.ClickException(msg)

    plan_text = "\n".join(plan_parts)
    return session_id, plan_text


def analyze_plan(plan_text: str) -> str:
    """Analyze fleet plan text and return a summary.

    Extracts wave counts, task counts, and step counts from the plan
    markdown to give the user a quick overview before execution.

    Args:
        plan_text: The raw plan text collected from the fleet plan phase.

    Returns:
        A human-readable summary of the plan structure.
    """
    waves = re.findall(r"##\s+Wave\s+\d+", plan_text)
    tasks = re.findall(r"###\s+Task\s+\d+", plan_text)
    steps_done = len(re.findall(r"- \[x\]", plan_text))
    steps_todo = len(re.findall(r"- \[ \]", plan_text))
    total_steps = steps_done + steps_todo

    lines = [
        f"Waves: {len(waves)}",
        f"Tasks: {len(tasks)}",
        f"Steps: {total_steps} ({steps_done} done, {steps_todo} pending)",
    ]
    return "\n".join(lines)


async def run_execute_phase(session_id: str) -> None:
    """Resume the fleet plan session and execute with full tool access.

    Args:
        session_id: The session ID from the plan phase.

    Raises:
        click.ClickException: If the execution phase fails.
    """
    try:
        async for message in query(
            prompt="The plan is approved. Execute it now.",
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


async def fleet_plan_and_execute(prompt: str) -> None:
    """Run the full fleet plan-then-execute workflow.

    Args:
        prompt: The user's goal description.
    """
    click.echo("=== Fleet Plan Phase ===")
    session_id, plan_text = await run_fleet_plan_phase(prompt)

    click.echo("\n=== Plan Analysis ===")
    summary = analyze_plan(plan_text)
    click.echo(summary)

    click.echo("\n=== Execution Phase ===")
    await run_execute_phase(session_id)


@click.command()
@click.argument("prompt")
def main(prompt: str) -> None:
    """Run a prompt through Fleet plan creation, then execute.

    PROMPT: The goal description for Fleet to plan and execute.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    asyncio.run(fleet_plan_and_execute(prompt))


if __name__ == "__main__":
    main()  # pragma: no cover
