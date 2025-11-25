"""CLI command to update EPUB table of contents from markdown structure."""

import logging
import re
from pathlib import Path

import click
import ebooklib
from ebooklib import epub


logger = logging.getLogger(__name__)


def parse_markdown_toc(toc_file: Path) -> list[tuple[int, str]]:
    """Parse markdown ToC structure into list of (level, title) tuples.

    Args:
        toc_file: Path to markdown file with ToC structure

    Returns:
        List of tuples (level, title) where level is 1-6 (header depth)
    """
    toc_structure = []
    with toc_file.open(encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            # Check if line is a markdown header
            if line.startswith("#"):
                level = 0
                for char in line:
                    if char == "#":
                        level += 1
                    else:
                        break
                if level > 0 and level <= 6:
                    title = line[level:].strip()
                    if title:
                        toc_structure.append((level, title))
    return toc_structure


def find_chapter_by_title(book: epub.EpubBook, title: str) -> epub.EpubItem | None:
    """Find a chapter/item in the book by matching title.

    Args:
        book: The EPUB book object
        title: Title to search for

    Returns:
        EpubItem if found, None otherwise
    """
    title_lower = title.lower().strip()
    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            # Try to extract title from HTML content
            content = item.get_content().decode("utf-8", errors="ignore")
            # Try to find title in h1-h6 tags
            for level in range(1, 7):
                pattern = rf"<h{level}[^>]*>(.*?)</h{level}>"
                matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)
                for match in matches:
                    # Remove HTML tags from match
                    clean_match = re.sub(r"<[^>]+>", "", match).strip()
                    if clean_match.lower() == title_lower:
                        return item
    return None


def create_toc_from_structure(  # noqa: PLR0912
    book: epub.EpubBook,
    toc_structure: list[tuple[int, str]],
) -> list:
    """Create EPUB ToC structure from markdown structure.

    Args:
        book: The EPUB book object
        toc_structure: List of (level, title) tuples

    Returns:
        List of ToC entries (Link objects or tuples) for EPUB ToC
    """
    toc_items = []
    stack: list[
        tuple[epub.Link, list, int]
    ] = []  # Stack of (parent_link, children_list, level)

    for level, title in toc_structure:
        # Find the chapter/item for this title
        chapter = find_chapter_by_title(book, title)
        if chapter is None:
            logger.warning(f"Could not find chapter for title: {title}")
            # Use first available chapter as fallback
            chapters = [
                item
                for item in book.get_items()
                if item.get_type() == ebooklib.ITEM_DOCUMENT
            ]
            if chapters:
                chapter = chapters[0]
                logger.info(f"Using fallback chapter: {chapter.get_name()}")
            else:
                logger.error("No chapters found in EPUB")
                continue

        # Create Link for this ToC entry
        link = epub.Link(
            chapter.get_name(),
            title,
            chapter.get_id(),
        )

        # Pop stack until we reach the correct parent level
        # Pop items whose level is >= current level (same or deeper)
        # This finalizes siblings and deeper items
        while stack and stack[-1][2] >= level:
            parent_link, children, _ = stack.pop()
            if stack:
                # Add to parent's children
                stack[-1][1].append(
                    (parent_link, children) if children else parent_link
                )
            else:
                # Top level item - add to toc_items when finalized
                toc_items.append((parent_link, children) if children else parent_link)

        # Add current link
        if level == 1:
            # Top level - push to stack (will be added to toc_items when finalized)
            stack.append((link, [], level))
        else:
            # Child level - add to current parent's children
            if stack:
                stack[-1][1].append(link)
            # Push to stack for potential children
            stack.append((link, [], level))

    # Pop remaining items from stack
    while stack:
        parent_link, children, _ = stack.pop()
        if stack:
            stack[-1][1].append((parent_link, children) if children else parent_link)
        else:
            toc_items.append((parent_link, children) if children else parent_link)

    return toc_items


@click.command()
@click.argument("epub_file", type=click.Path(exists=True, path_type=Path))
@click.argument("toc_file", type=click.Path(exists=True, path_type=Path))
@click.argument("output_file", required=False, type=click.Path(path_type=Path))
def main(epub_file: Path, toc_file: Path, output_file: Path | None) -> None:
    """Update EPUB table of contents from markdown structure.

    EPUB_FILE: Path to input EPUB file
    TOC_FILE: Path to markdown file with ToC structure
    OUTPUT_FILE: Optional path to output EPUB file (defaults to overwriting input)
    """
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Determine output file
    output_file = epub_file if output_file is None else Path(output_file)

    logger.info(f"Reading EPUB file: {epub_file}")
    logger.info(f"Reading ToC structure from: {toc_file}")
    logger.info(f"Output will be written to: {output_file}")

    # Parse markdown ToC structure
    toc_structure = parse_markdown_toc(toc_file)
    if not toc_structure:
        msg = (
            f"No valid ToC structure found in {toc_file}. "
            "Expected markdown headers (# Header, ## Header, etc.)"
        )
        raise click.ClickException(msg)

    logger.info(f"Parsed {len(toc_structure)} ToC entries")

    # Read EPUB file
    try:
        book = epub.read_epub(str(epub_file))
    except Exception as e:
        msg = f"Failed to read EPUB file: {e}"
        raise click.ClickException(msg) from e

    # Create new ToC structure
    toc_items = create_toc_from_structure(book, toc_structure)

    # Clear existing ToC and add new structure
    book.toc = toc_items

    # Write updated EPUB
    try:
        # If output is same as input, write to temp file first
        if output_file == epub_file:
            temp_file = epub_file.with_suffix(".tmp.epub")
            epub.write_epub(str(temp_file), book)
            temp_file.replace(output_file)
        else:
            epub.write_epub(str(output_file), book)
        logger.info(f"Successfully updated EPUB: {output_file}")
    except Exception as e:
        msg = f"Failed to write EPUB file: {e}"
        raise click.ClickException(msg) from e


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
