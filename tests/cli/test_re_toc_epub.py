"""Tests for the re_toc_epub CLI command."""

import sys
from pathlib import Path
from unittest.mock import patch

import click
import pytest
from ebooklib import epub

from silly_scripts.cli.re_toc_epub import (
    create_toc_from_structure,
    find_chapter_by_title,
    main,
    parse_markdown_toc,
)


# Ensure the package can be imported from the src/ layout during tests
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


def test_parse_markdown_toc_basic(tmp_path: Path):
    """Test parsing basic markdown ToC structure."""
    toc_file = tmp_path / "toc.md"
    toc_file.write_text(
        """# Header 1

## Header 1.1

### Header 1.1.1

# Header 2
""",
        encoding="utf-8",
    )

    result = parse_markdown_toc(toc_file)

    assert len(result) == 4
    assert result[0] == (1, "Header 1")
    assert result[1] == (2, "Header 1.1")
    assert result[2] == (3, "Header 1.1.1")
    assert result[3] == (1, "Header 2")


def test_parse_markdown_toc_empty_file(tmp_path: Path):
    """Test parsing empty markdown file."""
    toc_file = tmp_path / "toc.md"
    toc_file.write_text("", encoding="utf-8")

    result = parse_markdown_toc(toc_file)

    assert result == []


def test_parse_markdown_toc_with_blank_lines(tmp_path: Path):
    """Test parsing markdown with blank lines."""
    toc_file = tmp_path / "toc.md"
    toc_file.write_text(
        """
# Header 1


## Header 1.1

# Header 2
""",
        encoding="utf-8",
    )

    result = parse_markdown_toc(toc_file)

    assert len(result) == 3
    assert result[0] == (1, "Header 1")
    assert result[1] == (2, "Header 1.1")
    assert result[2] == (1, "Header 2")


def test_parse_markdown_toc_ignores_non_headers(tmp_path: Path):
    """Test that non-header lines are ignored."""
    toc_file = tmp_path / "toc.md"
    toc_file.write_text(
        """Some text here
# Header 1
More text
## Header 1.1
""",
        encoding="utf-8",
    )

    result = parse_markdown_toc(toc_file)

    assert len(result) == 2
    assert result[0] == (1, "Header 1")
    assert result[1] == (2, "Header 1.1")


def test_find_chapter_by_title_found():
    """Test finding a chapter by title when it exists."""
    book = epub.EpubBook()
    chapter1 = epub.EpubHtml(
        title="Chapter 1",
        file_name="chapter1.xhtml",
        lang="en",
    )
    chapter1.content = b"<html><body><h1>Header 1</h1></body></html>"
    book.add_item(chapter1)

    chapter2 = epub.EpubHtml(
        title="Chapter 2",
        file_name="chapter2.xhtml",
        lang="en",
    )
    chapter2.content = b"<html><body><h1>Header 2</h1></body></html>"
    book.add_item(chapter2)

    result = find_chapter_by_title(book, "Header 1")

    assert result is not None
    assert result.get_name() == "chapter1.xhtml"


def test_find_chapter_by_title_not_found():
    """Test finding a chapter by title when it doesn't exist."""
    book = epub.EpubBook()
    chapter1 = epub.EpubHtml(
        title="Chapter 1",
        file_name="chapter1.xhtml",
        lang="en",
    )
    chapter1.content = b"<html><body><h1>Other Header</h1></body></html>"
    book.add_item(chapter1)

    result = find_chapter_by_title(book, "Header 1")

    assert result is None


def test_find_chapter_by_title_case_insensitive():
    """Test that title matching is case insensitive."""
    book = epub.EpubBook()
    chapter1 = epub.EpubHtml(
        title="Chapter 1",
        file_name="chapter1.xhtml",
        lang="en",
    )
    chapter1.content = b"<html><body><h1>Header 1</h1></body></html>"
    book.add_item(chapter1)

    result = find_chapter_by_title(book, "header 1")

    assert result is not None
    assert result.get_name() == "chapter1.xhtml"


def test_create_toc_from_structure_simple():
    """Test creating ToC from simple structure."""
    book = epub.EpubBook()
    chapter1 = epub.EpubHtml(
        title="Chapter 1",
        file_name="chapter1.xhtml",
        lang="en",
    )
    chapter1.content = b"<html><body><h1>Header 1</h1></body></html>"
    book.add_item(chapter1)

    chapter2 = epub.EpubHtml(
        title="Chapter 2",
        file_name="chapter2.xhtml",
        lang="en",
    )
    chapter2.content = b"<html><body><h1>Header 2</h1></body></html>"
    book.add_item(chapter2)

    toc_structure = [(1, "Header 1"), (1, "Header 2")]

    result = create_toc_from_structure(book, toc_structure)

    assert len(result) == 2
    assert all(isinstance(item, epub.Link) for item in result)


def test_create_toc_from_structure_hierarchical():
    """Test creating ToC from hierarchical structure."""
    book = epub.EpubBook()
    chapter1 = epub.EpubHtml(
        title="Chapter 1",
        file_name="chapter1.xhtml",
        lang="en",
    )
    chapter1.content = b"<html><body><h1>Header 1</h1></body></html>"
    book.add_item(chapter1)

    chapter2 = epub.EpubHtml(
        title="Chapter 2",
        file_name="chapter2.xhtml",
        lang="en",
    )
    chapter2.content = b"<html><body><h2>Header 1.1</h2></body></html>"
    book.add_item(chapter2)

    toc_structure = [(1, "Header 1"), (2, "Header 1.1")]

    result = create_toc_from_structure(book, toc_structure)

    assert len(result) >= 1
    # First item should be a Link or tuple
    assert isinstance(result[0], (epub.Link, tuple))


@patch("silly_scripts.cli.re_toc_epub.epub.read_epub")
@patch("silly_scripts.cli.re_toc_epub.epub.write_epub")
def test_main_with_output_file(mock_write, mock_read, tmp_path: Path):
    """Test main function with output file specified."""
    epub_file = tmp_path / "input.epub"
    toc_file = tmp_path / "toc.md"
    output_file = tmp_path / "output.epub"

    toc_file.write_text("# Header 1\n", encoding="utf-8")

    # Mock EPUB book
    book = epub.EpubBook()
    chapter = epub.EpubHtml(
        title="Chapter 1",
        file_name="chapter1.xhtml",
        lang="en",
    )
    chapter.content = b"<html><body><h1>Header 1</h1></body></html>"
    book.add_item(chapter)
    mock_read.return_value = book

    # Create dummy epub file
    epub_file.touch()

    main.callback(epub_file, toc_file, output_file)

    mock_read.assert_called_once_with(str(epub_file))
    mock_write.assert_called_once()
    assert str(output_file) in str(mock_write.call_args[0][0])


@patch("silly_scripts.cli.re_toc_epub.epub.read_epub")
@patch("silly_scripts.cli.re_toc_epub.epub.write_epub")
def test_main_without_output_file(mock_write, mock_read, tmp_path: Path):
    """Test main function without output file (overwrites input)."""
    epub_file = tmp_path / "input.epub"
    toc_file = tmp_path / "toc.md"

    toc_file.write_text("# Header 1\n", encoding="utf-8")

    # Mock EPUB book
    book = epub.EpubBook()
    chapter = epub.EpubHtml(
        title="Chapter 1",
        file_name="chapter1.xhtml",
        lang="en",
    )
    chapter.content = b"<html><body><h1>Header 1</h1></body></html>"
    book.add_item(chapter)
    mock_read.return_value = book

    # Create dummy epub file
    epub_file.touch()

    # Make write_epub actually create the temp file
    def side_effect_write(path, _book_obj):
        Path(path).touch()

    mock_write.side_effect = side_effect_write

    main.callback(epub_file, toc_file, None)

    mock_read.assert_called_once_with(str(epub_file))
    # Should be called with temp file path
    assert mock_write.called


@patch("silly_scripts.cli.re_toc_epub.epub.read_epub")
def test_main_invalid_toc_file(mock_read, tmp_path: Path):  # noqa: ARG001
    """Test main function with invalid ToC file."""
    epub_file = tmp_path / "input.epub"
    toc_file = tmp_path / "toc.md"

    # Empty ToC file
    toc_file.write_text("", encoding="utf-8")

    epub_file.touch()

    with pytest.raises(click.ClickException):
        main.callback(epub_file, toc_file, None)


@patch("silly_scripts.cli.re_toc_epub.epub.read_epub")
def test_main_invalid_epub_file(mock_read, tmp_path: Path):
    """Test main function with invalid EPUB file."""
    epub_file = tmp_path / "input.epub"
    toc_file = tmp_path / "toc.md"

    toc_file.write_text("# Header 1\n", encoding="utf-8")
    epub_file.touch()

    mock_read.side_effect = Exception("Invalid EPUB")

    with pytest.raises(click.ClickException):
        main.callback(epub_file, toc_file, None)


def test_main_module_can_be_imported():
    """Test that the re_toc_epub module can be imported."""
    import silly_scripts.cli.re_toc_epub  # noqa: PLC0415

    assert hasattr(silly_scripts.cli.re_toc_epub, "main")
    assert callable(silly_scripts.cli.re_toc_epub.main)
