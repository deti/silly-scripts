"""Convert HTML files in a folder to Markdown using html-to-markdown.

Usage example:
    html-to-md /path/to/folder
"""

import logging
from pathlib import Path

import click
from html_to_markdown import convert


logger = logging.getLogger(__name__)


def find_html_files(folder: Path) -> list[Path]:
    """Find all .html and .htm files in the given folder.

    Args:
        folder: Directory to scan for HTML files.

    Returns:
        Sorted list of HTML file paths.
    """
    patterns = ("*.html", "*.htm")
    files: list[Path] = []
    for pattern in patterns:
        files.extend(folder.glob(pattern))
    return sorted(set(files))


def convert_file(html_path: Path) -> Path:
    """Convert a single HTML file to Markdown and save it alongside the original.

    Args:
        html_path: Path to the HTML file.

    Returns:
        Path to the created Markdown file.

    Raises:
        RuntimeError: If conversion fails.
    """
    html_content = html_path.read_text(encoding="utf-8")
    try:
        markdown_content = convert(html_content)
    except Exception as exc:
        msg = f"Failed to convert {html_path.name}: {exc}"
        raise RuntimeError(msg) from exc

    md_path = html_path.with_suffix(".md")
    md_path.write_text(markdown_content, encoding="utf-8")
    return md_path


@click.command()
@click.argument(
    "folder",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
def main(folder: Path) -> None:
    """Convert all HTML/HTM files in FOLDER to Markdown.

    For each .html or .htm file found, creates a .md file with the same base
    name in the same directory.

    \b
    Example:
        html-to-md ./my-html-pages
    """
    logging.basicConfig(level=logging.INFO)

    html_files = find_html_files(folder)
    if not html_files:
        click.echo(f"No .html or .htm files found in {folder}")
        return

    click.echo(f"Found {len(html_files)} HTML file(s) in {folder}")

    converted = 0
    failed = 0
    for html_path in html_files:
        try:
            md_path = convert_file(html_path)
            logger.info(f"Converted {html_path.name} -> {md_path.name}")
            converted += 1
        except RuntimeError:
            logger.exception(f"Skipping {html_path.name}")
            failed += 1

    click.echo(f"Done: {converted} converted, {failed} failed.")


if __name__ == "__main__":
    main()  # pragma: no cover
