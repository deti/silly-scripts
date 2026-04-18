"""Convert EPUB chapters to individual Markdown files.

Usage example:
    epub-to-md /path/to/book.epub
"""

import logging
import re
from pathlib import Path

import click
import ebooklib
from ebooklib import epub
from html_to_markdown import convert


logger = logging.getLogger(__name__)


def sanitize_filename(name: str) -> str:
    """Convert a string into a safe filename.

    Args:
        name: Raw string to sanitize.

    Returns:
        Sanitized string suitable for use as a filename.
    """
    name = re.sub(r"[^\w\s\-.]", "", name)
    name = re.sub(r"\s+", "_", name.strip())
    return name or "untitled"


def extract_chapter_title(html_content: str) -> str | None:
    """Extract the first heading from HTML content.

    Args:
        html_content: HTML string to search for headings.

    Returns:
        The text of the first heading found, or None.
    """
    for level in range(1, 7):
        pattern = rf"<h{level}[^>]*>(.*?)</h{level}>"
        match = re.search(pattern, html_content, re.IGNORECASE | re.DOTALL)
        if match:
            return re.sub(r"<[^>]+>", "", match.group(1)).strip()
    return None


def get_document_items(book: epub.EpubBook) -> list[epub.EpubItem]:
    """Get all document items from an EPUB book in spine order.

    Args:
        book: The EPUB book object.

    Returns:
        List of document items in reading order.
    """
    spine_ids = [item_id for item_id, _ in book.spine]
    items_by_id = {}
    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            items_by_id[item.get_id()] = item

    ordered = []
    for item_id in spine_ids:
        if item_id in items_by_id:
            ordered.append(items_by_id.pop(item_id))

    # Append any remaining document items not in spine
    for item in items_by_id.values():
        ordered.append(item)

    return ordered


def convert_chapter(item: epub.EpubItem, index: int) -> tuple[str, str]:
    """Convert a single EPUB chapter item to Markdown.

    Args:
        item: EPUB document item to convert.
        index: Chapter index for fallback naming.

    Returns:
        Tuple of (filename, markdown_content).

    Raises:
        RuntimeError: If HTML-to-Markdown conversion fails.
    """
    html_content = item.get_content().decode("utf-8", errors="ignore")
    title = extract_chapter_title(html_content)

    if title:
        filename = f"{index:03d}_{sanitize_filename(title)}.md"
    else:
        filename = f"{index:03d}_{sanitize_filename(item.get_name())}.md"

    try:
        markdown_content = convert(html_content)
    except Exception as exc:
        msg = f"Failed to convert chapter {item.get_name()}: {exc}"
        raise RuntimeError(msg) from exc

    return filename, markdown_content


@click.command()
@click.argument(
    "epub_file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
def main(epub_file: Path) -> None:
    """Convert EPUB chapters to individual Markdown files.

    Creates a folder named after the EPUB file (without extension) in the same
    directory, then extracts each chapter as a separate Markdown file.

    \b
    Example:
        epub-to-md my-book.epub
    """
    logging.basicConfig(level=logging.INFO)

    output_dir = epub_file.parent / epub_file.stem
    output_dir.mkdir(exist_ok=True)
    click.echo(f"Output directory: {output_dir}")

    try:
        book = epub.read_epub(str(epub_file))
    except Exception as exc:
        msg = f"Failed to read EPUB file: {exc}"
        raise click.ClickException(msg) from exc

    items = get_document_items(book)
    if not items:
        click.echo("No chapters found in EPUB file.")
        return

    click.echo(f"Found {len(items)} chapter(s)")

    converted = 0
    failed = 0
    for index, item in enumerate(items, start=1):
        try:
            filename, markdown_content = convert_chapter(item, index)
            md_path = output_dir / filename
            md_path.write_text(markdown_content, encoding="utf-8")
            logger.info(f"Wrote {filename}")
            converted += 1
        except RuntimeError:
            logger.exception(f"Skipping chapter {index}")
            failed += 1

    click.echo(f"Done: {converted} converted, {failed} failed.")


if __name__ == "__main__":
    main()  # pragma: no cover
