"""Split a consolidated prompt chain markdown file into separate prompt files."""

import logging
import re
from pathlib import Path

import click


logger = logging.getLogger(__name__)

PROMPT_HEADER_RE = re.compile(r"^## Prompt\s+\d+", re.MULTILINE)


def extract_prompts(content: str) -> list[str]:
    """Extract prompt texts from markdown content.

    Each prompt starts with a ``## Prompt`` header and the actual prompt
    text lives inside the first triple-backtick code block that follows.

    Args:
        content: Full markdown file content.

    Returns:
        List of prompt texts in order.
    """
    prompts: list[str] = []
    sections = PROMPT_HEADER_RE.split(content)
    # First element is everything before the first ## Prompt header
    for section in sections[1:]:
        # Find the code block in this section
        match = re.search(r"```\n?(.*?)```", section, re.DOTALL)
        if match:
            prompts.append(match.group(1).strip())
    return prompts


@click.command()
@click.argument("md_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def main(md_file: Path) -> None:
    """Split a consolidated prompt chain into separate files.

    MD_FILE: Markdown file containing prompts. Each prompt starts with
    a ``## Prompt`` header and the prompt text is inside a triple-backtick
    code block.

    Creates a folder with the same name as the input file (without extension)
    and writes each prompt to Prompt01.md, Prompt02.md, etc.
    """
    logging.basicConfig(level=logging.INFO)

    content = md_file.read_text(encoding="utf-8")
    prompts = extract_prompts(content)

    if not prompts:
        msg = f"No prompts found in {md_file}"
        raise click.ClickException(msg)

    output_dir = md_file.parent / md_file.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    for i, prompt_text in enumerate(prompts, start=1):
        out_file = output_dir / f"Prompt{i:02d}.md"
        out_file.write_text(prompt_text + "\n", encoding="utf-8")
        logger.info(f"Wrote {out_file.name}")

    click.echo(f"Extracted {len(prompts)} prompts to {output_dir}")


if __name__ == "__main__":
    main()  # pragma: no cover
