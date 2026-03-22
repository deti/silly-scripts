"""Split a local HTML book into upload-ready chunks by chapter or chapter-part."""

import json
import logging
import re
import shutil
from pathlib import Path
from typing import Any

import click
from bs4 import BeautifulSoup, Tag


logger = logging.getLogger(__name__)

# Constants for splitting
MAX_WORDS = 8000
MIN_WORDS_PER_CHUNK = 1000  # Avoid tiny chunks if possible
SECTION_RE = re.compile(r"^\d+\.\d+(\.\d+)*\s")  # Matches "3.1 ", "3.1.2 "


class ChunkManifest:
    def __init__(
        self,
        source_chapter: str,
        chunk_name: str,
        section_range: str,
        image_files: list[str],
        word_count: int,
    ):
        self.source_chapter = source_chapter
        self.chunk_name = chunk_name
        self.section_range = section_range
        self.image_files = image_files
        self.word_count = word_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_chapter": self.source_chapter,
            "chunk_name": self.chunk_name,
            "section_range": self.section_range,
            "image_files": self.image_files,
            "estimated_word_count": self.word_count,
        }


def count_words(text: str) -> int:
    """Simple word count."""
    return len(text.split())


def get_section_title(element: Tag) -> str | None:
    """Extract section number/title if it looks like a major section (e.g. 3.1)."""
    if element.name not in ["h1", "h2", "h3", "h4", "h5", "h6"]:
        return None
    text = element.get_text().strip()
    if SECTION_RE.match(text):
        return text
    return None


def extract_images(soup: BeautifulSoup) -> list[str]:
    """Find all image filenames referenced in the HTML."""
    images = []
    for img in soup.find_all("img"):
        src = img.get("src")
        if src:
            # We assume images are in 'images/' folder or flat in HTML dir
            # But the requirement says they are in 'images/' folder in input
            # and should be copied to the chunk folder.
            # We'll take the basename.
            images.append(Path(src).name)
    return list(set(images))


def process_chapter(
    chapter_path: Path, images_dir: Path, output_root: Path
) -> list[str]:
    """Process a single chapter file and split if necessary."""
    with chapter_path.open("r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "lxml")

    # Find the body content (or use the whole soup if no body)
    content = soup.find("body") or soup

    # Total word count
    total_text = content.get_text()
    total_words = count_words(total_text)
    chapter_id = chapter_path.stem  # e.g., "ch01"

    if total_words <= MAX_WORDS:
        # Keep as single chunk
        return [
            save_chunk(
                chapter_id,
                content,
                chapter_id,
                images_dir,
                output_root,
                chapter_path.name,
            )
        ]

    # Need to split
    chunks = []
    current_elements = []
    current_word_count = 0
    chunk_index = 1

    # Track section range for manifest
    first_section = "Start"
    last_section = "End"
    found_first_section = False

    # Iterate through top-level elements in content
    # We'll use soup.new_tag for chunks
    elements = content.find_all(recursive=False)
    if not elements and content.name != "body":
        # Fallback if structure is flat or weird
        elements = content.contents

    for el in elements:
        if isinstance(el, Tag):
            el_text = el.get_text()
            el_words = count_words(el_text)

            section_title = get_section_title(el)

            # Split condition:
            # 1. We have enough words (at least some minimum or close to max)
            # 2. We hit a major section boundary (e.g., 3.1)
            if (
                current_word_count >= MIN_WORDS_PER_CHUNK
                and section_title
                and (current_word_count + el_words > MAX_WORDS or current_word_count > MAX_WORDS * 0.7)
            ):
                # Save current chunk
                chunk_name = f"{chapter_id}-{chunk_index:02d}"
                last_section = section_title # The one we JUST hit belongs to NEXT chunk

                # Actually, the section we just hit should probably be the START of the next chunk.
                # So the current chunk ends BEFORE this element.

                chunks.append(
                    save_chunk(
                        chapter_id,
                        current_elements,
                        chunk_name,
                        images_dir,
                        output_root,
                        first_section,
                        last_section
                    )
                )

                # Reset for next chunk
                current_elements = [el]
                current_word_count = el_words
                chunk_index += 1
                first_section = section_title
                found_first_section = True
            else:
                current_elements.append(el)
                current_word_count += el_words
                if section_title and not found_first_section:
                    first_section = section_title
                    found_first_section = True
                if section_title:
                    last_section = section_title

    # Final chunk
    if current_elements:
        chunk_name = f"{chapter_id}-{chunk_index:02d}"
        chunks.append(
            save_chunk(
                chapter_id,
                current_elements,
                chunk_name,
                images_dir,
                output_root,
                first_section,
                "End"
            )
        )

    return chunks


def save_chunk(
    source_chapter: str,
    elements: list[Tag] | Tag,
    chunk_name: str,
    images_src_dir: Path,
    output_root: Path,
    start_section: str,
    end_section: str | None = None,
) -> str:
    """Save a chunk of HTML, its images, and manifest."""
    chunk_dir = output_root / chunk_name
    chunk_dir.mkdir(parents=True, exist_ok=True)

    # Create new soup for the chunk
    new_soup = BeautifulSoup("<html><head><meta charset='utf-8'/></head><body></body></html>", "lxml")
    body = new_soup.body

    if isinstance(elements, list):
        for el in elements:
            # Clone elements to avoid modifying original soup if we reuse it
            body.append(BeautifulSoup(str(el), "lxml").find(el.name))
    else:
        body.append(BeautifulSoup(str(elements), "lxml").find(elements.name))

    # Identify images used in this chunk
    chunk_images = extract_images(new_soup)

    # Copy images to chunk folder and update references in HTML
    for img_tag in new_soup.find_all("img"):
        src = img_tag.get("src")
        if src:
            img_name = Path(src).name
            img_tag["src"] = img_name  # Update to local path
            src_path = images_src_dir / img_name
            if src_path.exists():
                shutil.copy2(src_path, chunk_dir / img_name)
            else:
                logger.warning(f"Image not found: {src_path}")

    # Save HTML
    html_filename = f"{chunk_name}.html"
    with (chunk_dir / html_filename).open("w", encoding="utf-8") as f:
        f.write(new_soup.prettify())

    # Create manifest
    word_count = count_words(new_soup.get_text())
    section_range = f"{start_section} to {end_section}" if end_section else start_section
    manifest = ChunkManifest(
        source_chapter=source_chapter,
        chunk_name=chunk_name,
        section_range=section_range,
        image_files=chunk_images,
        word_count=word_count,
    )

    with (chunk_dir / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest.to_dict(), f, indent=2)

    return chunk_name


@click.command()
@click.argument("book_path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("output_path", type=click.Path(path_type=Path))
def main(book_path: Path, output_path: Path) -> None:
    """Analyze a local HTML book and split it into chunks.
    
    BOOK_PATH: Directory containing chNN.html files and an 'images' folder.
    OUTPUT_PATH: Directory where processed chunks will be saved.
    """
    logging.basicConfig(level=logging.INFO)

    images_dir = book_path / "images"
    if not images_dir.exists():
        logger.warning(f"Images directory not found at {images_dir}")

    # Find all chapter files
    chapter_files = sorted(book_path.glob("ch*.html"))
    if not chapter_files:
        click.echo("No chapter files (ch*.html) found in the input directory.")
        return

    all_chunks = []
    for chapter_file in chapter_files:
        logger.info(f"Processing {chapter_file.name}...")
        chunks = process_chapter(chapter_file, images_dir, output_path)
        all_chunks.extend(chunks)
        logger.info(f"Created {len(chunks)} chunks from {chapter_file.name}")

    click.echo(f"Successfully processed {len(chapter_files)} chapters into {len(all_chunks)} chunks.")
    click.echo(f"Output saved to: {output_path}")


if __name__ == "__main__":
    main()
