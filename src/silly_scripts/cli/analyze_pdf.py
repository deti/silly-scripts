"""Analyze a PDF file using the Claude Agent SDK."""

import asyncio
import logging
from pathlib import Path

import click
from claude_agent_sdk import ClaudeAgentOptions, query


logger = logging.getLogger(__name__)


async def analyze(pdf_path: Path, prompt: str) -> str:
    """Send a PDF to Claude for analysis via the Agent SDK.

    Args:
        pdf_path: Path to the PDF file.
        prompt: The analysis prompt to send alongside the PDF.

    Returns:
        The final result text from Claude.
    """
    full_prompt = (
        f"Read and analyze the PDF file at {pdf_path.resolve()}. "
        f"Here is what the user wants: {prompt}"
    )

    result_parts: list[str] = []
    async for message in query(
        prompt=full_prompt,
        options=ClaudeAgentOptions(
            allowed_tools=["Read"],
        ),
    ):
        if hasattr(message, "result"):
            result_parts.append(message.result)

    return "\n".join(result_parts)


@click.command()
@click.argument("pdf_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--prompt",
    "-p",
    default="Provide a detailed summary of this PDF document.",
    help="Analysis prompt to send to Claude.",
)
def main(pdf_path: Path, prompt: str) -> None:
    """Analyze a PDF file with Claude via the Agent SDK.

    PDF_PATH: Path to the PDF file to analyze.
    """
    logging.basicConfig(level=logging.INFO)

    if pdf_path.suffix.lower() != ".pdf":
        msg = f"Expected a PDF file, got: {pdf_path.suffix}"
        raise click.ClickException(msg)

    logger.info(f"Analyzing {pdf_path.name}...")
    result = asyncio.run(analyze(pdf_path, prompt))
    click.echo(result)


if __name__ == "__main__":
    main()  # pragma: no cover
