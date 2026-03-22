"""Automate a chapter-by-chapter research pipeline using Claude Agent SDK.

Processes chapter PDFs through 8 sequential prompts, producing research briefs,
gap analyses, and feature briefs for a target codebase.
"""

import asyncio
import logging
import re
import time
from datetime import UTC, datetime
from pathlib import Path

import click
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    query,
)


logger = logging.getLogger(__name__)

PROMPT_NAMES = {
    1: "chapter-extraction",
    2: "current-state-research",
    3: "technical-deep-dive",
    4: "formal-definitions",
    5: "algorithm-specifications",
    6: "research-brief",
    7: "gap-analysis",
    8: "feature-briefs",
}

PROMPT03_REPLACEMENTS = {
    "[list the key papers from Prompt 2, e.g.:]": (
        "Extract ALL papers from the research above that were cited with "
        "specific quantitative claims, flagged as unverified, or proposed "
        "novel methods. Include at minimum:"
    ),
    "[list key tools, e.g.:]": (
        "Extract ALL tools from the research above that were identified as "
        "potentially relevant for implementation or integration. "
        "Include at minimum:"
    ),
}

PROMPT04_REPLACEMENTS = {
    "[specific coverage criteria / formal concepts]": (
        "coverage criteria and formal concepts"
    ),
    "[e.g.:]": (
        "Extract ALL coverage criteria or formal concepts from the research "
        "and deep-dive above that lack established formal definitions. "
        "Include at minimum:"
    ),
}

PROMPT05_REPLACEMENTS = {
    "[e.g.:]": (
        "Extract ALL algorithms from the research and deep-dive above that "
        "APEX would need to implement. Include at minimum:"
    ),
}


def discover_chapters(input_folder: Path) -> list[str]:
    """Find chapter PDF files and return sorted chapter numbers.

    Args:
        input_folder: Path to the input folder containing chapter PDFs.

    Returns:
        Sorted list of chapter number strings (e.g., ["02", "03", "07"]).
    """
    pattern = re.compile(r"^ch(\d+)\.pdf$", re.IGNORECASE)
    chapters = []
    for f in input_folder.iterdir():
        m = pattern.match(f.name)
        if m:
            chapters.append(m.group(1).zfill(2))
    return sorted(chapters)


def load_prompt(input_folder: Path, prompt_num: int) -> str:
    """Load a prompt file from the input folder.

    Args:
        input_folder: Path to the input folder.
        prompt_num: Prompt number (1-8).

    Returns:
        The prompt text content.

    Raises:
        FileNotFoundError: If the prompt file does not exist.
    """
    path = input_folder / f"prompt{prompt_num:02d}.md"
    return path.read_text(encoding="utf-8")


def slugify(name: str) -> str:
    """Convert a technique name to a URL-friendly slug.

    Args:
        name: The technique name to slugify.

    Returns:
        Lowercase, hyphen-separated slug with non-alphanumeric chars stripped.
    """
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    return re.sub(r"-+", "-", slug).strip("-")


def extract_technique_name(response: str) -> str | None:
    """Extract the technique name from prompt 01's response.

    Looks for a "Core technique" section heading and extracts the primary
    testing technique term from the first sentence after it.

    Args:
        response: The full text response from prompt 01.

    Returns:
        The extracted technique name, or None if extraction fails.
    """
    patterns = [
        r"[#*]*\s*Core\s+[Tt]echnique[s]?\s*[#*:]*\s*\n+\s*(.+?)(?:\n|$)",
        r"[Cc]ore\s+[Tt]echnique[s]?\s*(?:is|:)\s*(.+?)(?:\.|,|\n)",
    ]
    for pattern in patterns:
        match = re.search(pattern, response)
        if match:
            name = match.group(1).strip().strip("*#:").strip()
            if name and len(name) < 100:
                return name
    return None


def apply_substitutions(
    text: str,
    chapter_num: str,
    output_dir: Path,
    technique_name: str | None = None,
    technique_slug: str | None = None,
) -> str:
    """Apply template substitutions to prompt text.

    Args:
        text: The raw prompt text.
        chapter_num: Chapter number with leading zero (e.g., "07").
        output_dir: Absolute path to chapter output directory.
        technique_name: The extracted technique name.
        technique_slug: The slugified technique name.

    Returns:
        The prompt text with all placeholders replaced.
    """
    text = text.replace("[N]", chapter_num)
    text = text.replace("[OUTPUT_DIR]", str(output_dir))

    if technique_name:
        text = text.replace("[Technique Name]", technique_name)
    if technique_slug:
        text = text.replace("[technique-slug]", technique_slug)

    return text


def apply_list_replacements(text: str, prompt_num: int) -> str:
    """Apply list placeholder replacements for prompts 03, 04, 05.

    Args:
        text: The prompt text.
        prompt_num: The prompt number (1-8).

    Returns:
        The prompt text with list placeholders replaced.
    """
    replacements: dict[str, str] = {}
    if prompt_num == 1:
        text = re.sub(
            r"\[Paste chapter HTML/text here, or attach file\]\n?",
            "",
            text,
        )
    elif prompt_num == 2:
        text = text.replace(
            "[technique name from Prompt 1]",
            "the technique extracted in the chapter analysis above",
        )
    elif prompt_num == 3:
        replacements = PROMPT03_REPLACEMENTS
    elif prompt_num == 4:
        replacements = PROMPT04_REPLACEMENTS
    elif prompt_num == 5:
        replacements = PROMPT05_REPLACEMENTS

    for old, new in replacements.items():
        text = text.replace(old, new)

    return text


def preprocess_prompt(
    text: str,
    prompt_num: int,
    chapter_num: str,
    output_dir: Path,
    pdf_path: Path | None = None,
    technique_name: str | None = None,
    technique_slug: str | None = None,
) -> str:
    """Fully preprocess a prompt with all substitutions.

    Args:
        text: Raw prompt text.
        prompt_num: Prompt number (1-8).
        chapter_num: Chapter number with leading zero.
        output_dir: Absolute path to chapter output directory.
        pdf_path: Path to chapter PDF (used for prompt 01).
        technique_name: Extracted technique name.
        technique_slug: Slugified technique name.

    Returns:
        Fully preprocessed prompt text ready to send.
    """
    text = apply_list_replacements(text, prompt_num)
    text = apply_substitutions(
        text, chapter_num, output_dir, technique_name, technique_slug
    )

    if prompt_num == 1 and pdf_path is not None:
        text = f"Read and analyze the PDF file at {pdf_path.resolve()}.\n\n{text}"

    return text


def output_filename(chapter_num: str, prompt_num: int) -> str:
    """Generate the output filename for a chapter/prompt combination.

    Args:
        chapter_num: Chapter number with leading zero.
        prompt_num: Prompt number (1-8).

    Returns:
        The output filename string.
    """
    name = PROMPT_NAMES[prompt_num]
    return f"ch{chapter_num}-{prompt_num:02d}-{name}.md"


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


async def run_research_phase(
    input_folder: Path,
    chapter_num: str,
    output_dir: Path,
    system_prompt: str,
) -> tuple[str | None, str | None]:
    """Run prompts 01-06 in a single conversational session.

    Args:
        input_folder: Path to the input folder.
        chapter_num: Chapter number with leading zero.
        output_dir: Absolute path to chapter output directory.
        system_prompt: System prompt text from system-prompt.md.

    Returns:
        Tuple of (technique_name, technique_slug) extracted from prompt 01.

    Raises:
        RuntimeError: If a critical prompt fails after retries.
    """
    pdf_path = input_folder / f"ch{chapter_num}.pdf"
    technique_name: str | None = None
    technique_slug: str | None = None

    options = ClaudeAgentOptions(
        model="claude-opus-4-6",
        system_prompt=system_prompt,
        cwd=str(input_folder),
        allowed_tools=["Read", "WebSearch", "WebFetch"],
    )

    async with ClaudeSDKClient(options=options) as client:
        for prompt_num in range(1, 7):
            raw_text = load_prompt(input_folder, prompt_num)
            prompt_text = preprocess_prompt(
                raw_text,
                prompt_num,
                chapter_num,
                output_dir,
                pdf_path=pdf_path if prompt_num == 1 else None,
                technique_name=technique_name,
                technique_slug=technique_slug,
            )

            logger.info(f"Chapter {chapter_num} - Sending prompt {prompt_num:02d}")
            response_text = await send_with_retry(
                client, prompt_text, chapter_num, prompt_num
            )

            if prompt_num == 1:
                technique_name = extract_technique_name(response_text)
                if technique_name is None:
                    technique_name = prompt_technique_name(chapter_num)
                technique_slug = slugify(technique_name)
                logger.info(
                    f"Chapter {chapter_num} - Technique: {technique_name} "
                    f"(slug: {technique_slug})"
                )

            out_file = output_dir / output_filename(chapter_num, prompt_num)
            out_file.write_text(response_text, encoding="utf-8")
            logger.info(f"Chapter {chapter_num} - Saved {out_file.name}")

    return technique_name, technique_slug


async def send_with_retry(
    client: ClaudeSDKClient,
    prompt_text: str,
    chapter_num: str,
    prompt_num: int,
    max_retries: int = 3,
    initial_backoff: float = 30.0,
) -> str:
    """Send a prompt through a ClaudeSDKClient session with retries.

    Args:
        client: The active ClaudeSDKClient session.
        prompt_text: The prompt to send.
        chapter_num: Chapter number for logging.
        prompt_num: Prompt number for logging.
        max_retries: Maximum retry attempts.
        initial_backoff: Initial backoff in seconds.

    Returns:
        The collected response text.

    Raises:
        RuntimeError: If all retries are exhausted.
    """
    backoff = initial_backoff
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            await client.query(prompt_text)
            parts: list[str] = []
            async for message in client.receive_response():
                text = collect_text(message)
                if text:
                    parts.append(text)
            return "\n".join(parts)
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                logger.warning(
                    f"Chapter {chapter_num} prompt {prompt_num:02d} "
                    f"attempt {attempt + 1} failed: {e}. "
                    f"Retrying in {backoff}s..."
                )
                await asyncio.sleep(backoff)
                backoff *= 2
            else:
                logger.exception(
                    f"Chapter {chapter_num} prompt {prompt_num:02d} "
                    f"failed after {max_retries + 1} attempts"
                )

    msg = (
        f"Chapter {chapter_num} prompt {prompt_num:02d} "
        f"failed after {max_retries + 1} attempts"
    )
    raise RuntimeError(msg) from last_error


async def query_with_retry(
    prompt_text: str,
    options: ClaudeAgentOptions,
    chapter_num: str,
    prompt_num: int,
    max_retries: int = 3,
    initial_backoff: float = 30.0,
) -> str:
    """Run a one-shot query() call with retries.

    Args:
        prompt_text: The prompt to send.
        options: Agent options for the query.
        chapter_num: Chapter number for logging.
        prompt_num: Prompt number for logging.
        max_retries: Maximum retry attempts.
        initial_backoff: Initial backoff in seconds.

    Returns:
        The collected response text.

    Raises:
        RuntimeError: If all retries are exhausted.
    """
    backoff = initial_backoff
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            parts: list[str] = []
            async for message in query(prompt=prompt_text, options=options):
                text = collect_text(message)
                if text:
                    parts.append(text)
            return "\n".join(parts)
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                logger.warning(
                    f"Chapter {chapter_num} prompt {prompt_num:02d} "
                    f"attempt {attempt + 1} failed: {e}. "
                    f"Retrying in {backoff}s..."
                )
                await asyncio.sleep(backoff)
                backoff *= 2
            else:
                logger.exception(
                    f"Chapter {chapter_num} prompt {prompt_num:02d} "
                    f"failed after {max_retries + 1} attempts"
                )

    msg = (
        f"Chapter {chapter_num} prompt {prompt_num:02d} "
        f"failed after {max_retries + 1} attempts"
    )
    raise RuntimeError(msg) from last_error


async def run_code_analysis_phase(
    input_folder: Path,
    chapter_num: str,
    output_dir: Path,
    repo_path: Path,
    technique_name: str | None,
    technique_slug: str | None,
) -> None:
    """Run prompts 07-08 as one-shot queries against the repo.

    Args:
        input_folder: Path to the input folder.
        chapter_num: Chapter number with leading zero.
        output_dir: Absolute path to chapter output directory.
        repo_path: Path to the target repository.
        technique_name: Extracted technique name.
        technique_slug: Slugified technique name.
    """
    options = ClaudeAgentOptions(
        cwd=str(repo_path),
        allowed_tools=["Read", "Write", "Edit", "Bash", "Grep", "Glob"],
        permission_mode="acceptEdits",
    )

    for prompt_num in (7, 8):
        raw_text = load_prompt(input_folder, prompt_num)
        prompt_text = preprocess_prompt(
            raw_text,
            prompt_num,
            chapter_num,
            output_dir,
            technique_name=technique_name,
            technique_slug=technique_slug,
        )

        logger.info(
            f"Chapter {chapter_num} - Running prompt {prompt_num:02d} (code analysis)"
        )
        response_text = await query_with_retry(
            prompt_text, options, chapter_num, prompt_num
        )

        out_file = output_dir / output_filename(chapter_num, prompt_num)
        if not out_file.exists() or out_file.stat().st_size == 0:
            out_file.write_text(response_text, encoding="utf-8")
            logger.info(
                f"Chapter {chapter_num} - Saved {out_file.name} (from response text)"
            )
        else:
            logger.info(
                f"Chapter {chapter_num} - {out_file.name} already written by agent"
            )


def prompt_technique_name(chapter_num: str) -> str:
    """Prompt the user to manually enter the technique name.

    Args:
        chapter_num: Chapter number for the prompt message.

    Returns:
        The user-entered technique name.
    """
    click.echo(f"\nCould not auto-extract technique name for chapter {chapter_num}.")
    name = click.prompt("Please enter the technique name")
    return name.strip()


async def process_chapter(
    input_folder: Path,
    chapter_num: str,
    system_prompt: str,
    repo_path: Path,
) -> str:
    """Process a single chapter through the full 8-prompt pipeline.

    Args:
        input_folder: Path to the input folder.
        chapter_num: Chapter number with leading zero.
        system_prompt: System prompt text.
        repo_path: Path to the target repository.

    Returns:
        Status string: "complete", "partial", or "failed".
    """
    output_dir = input_folder / f"ch{chapter_num}"
    output_dir.mkdir(exist_ok=True)

    try:
        technique_name, technique_slug = await run_research_phase(
            input_folder, chapter_num, output_dir, system_prompt
        )
    except Exception:
        logger.exception(f"Chapter {chapter_num} - Research phase failed")
        return "failed"

    try:
        await run_code_analysis_phase(
            input_folder,
            chapter_num,
            output_dir,
            repo_path,
            technique_name,
            technique_slug,
        )
    except Exception:
        logger.exception(f"Chapter {chapter_num} - Code analysis phase failed")
        return "partial"

    return "complete"


async def run_pipeline(input_folder: Path, repo_path: Path) -> None:
    """Run the full research pipeline across all chapters.

    Args:
        input_folder: Path to the input folder.
        repo_path: Path to the target repository.
    """
    start_time = time.monotonic()
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")

    system_prompt_path = input_folder / "system-prompt.md"
    if not system_prompt_path.exists():
        msg = f"system-prompt.md not found in {input_folder}"
        raise click.ClickException(msg)
    system_prompt = system_prompt_path.read_text(encoding="utf-8")

    chapters = discover_chapters(input_folder)
    if not chapters:
        msg = f"No chapter PDFs found in {input_folder}"
        raise click.ClickException(msg)

    logger.info(f"Found {len(chapters)} chapters: {', '.join(chapters)}")
    logger.info(f"Repo path: {repo_path}")

    results: dict[str, str] = {}

    for ch in chapters:
        pdf_path = input_folder / f"ch{ch}.pdf"
        if not pdf_path.exists():
            logger.warning(f"Chapter {ch} PDF not found, skipping")
            results[ch] = "skipped"
            continue

        logger.info(f"=== Processing chapter {ch} ===")
        status = await process_chapter(input_folder, ch, system_prompt, repo_path)
        results[ch] = status
        logger.info(f"Chapter {ch} finished with status: {status}")

    elapsed = time.monotonic() - start_time
    elapsed_min = elapsed / 60

    summary_lines = [
        f"Pipeline Run Summary - {timestamp}",
        f"Total wall-clock time: {elapsed_min:.1f} minutes",
        f"Chapters processed: {len(results)}",
        "",
    ]
    for ch, status in sorted(results.items()):
        summary_lines.append(f"  Chapter {ch}: {status}")

    summary = "\n".join(summary_lines)
    logger.info(f"\n{summary}")

    log_file = input_folder / f"pipeline-run-{timestamp}.log"
    log_file.write_text(summary + "\n", encoding="utf-8")
    logger.info(f"Run summary saved to {log_file.name}")


@click.command()
@click.argument(
    "input_folder",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option(
    "--repo",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Path to the target repo. Defaults to parent of input folder.",
)
def main(input_folder: Path, repo: Path | None) -> None:
    """Run the research PDF pipeline on chapter PDFs.

    INPUT_FOLDER: Path to folder containing chapter PDFs and prompt files.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    input_folder = input_folder.resolve()
    repo_path = repo.resolve() if repo else input_folder.parent

    if not (input_folder / "prompt01.md").exists():
        msg = "prompt01.md not found in input folder"
        raise click.ClickException(msg)

    if not repo_path.is_dir():
        msg = f"Repo path does not exist: {repo_path}"
        raise click.ClickException(msg)

    logger.info(f"Input folder: {input_folder}")
    logger.info(f"Repo path: {repo_path}")

    asyncio.run(run_pipeline(input_folder, repo_path))


if __name__ == "__main__":
    main()  # pragma: no cover
