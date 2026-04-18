"""Tests for the epub_to_md CLI command."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from ebooklib import epub

from silly_scripts.cli.epub_to_md import (
    convert_chapter,
    extract_chapter_title,
    get_document_items,
    main,
    sanitize_filename,
)


if TYPE_CHECKING:
    from pathlib import Path


class TestSanitizeFilename:
    """Tests for the sanitize_filename helper."""

    def test_removes_special_characters(self) -> None:
        """Removes characters unsafe for filenames."""
        assert sanitize_filename("Hello/World:Test?") == "HelloWorldTest"

    def test_replaces_spaces_with_underscores(self) -> None:
        """Replaces whitespace with underscores."""
        assert sanitize_filename("Hello World") == "Hello_World"

    def test_collapses_multiple_spaces(self) -> None:
        """Multiple spaces become a single underscore."""
        assert sanitize_filename("Hello   World") == "Hello_World"

    def test_empty_string_returns_untitled(self) -> None:
        """Empty or all-special input returns 'untitled'."""
        assert sanitize_filename("") == "untitled"
        assert sanitize_filename("///") == "untitled"

    def test_preserves_hyphens_and_dots(self) -> None:
        """Hyphens and dots are kept."""
        assert sanitize_filename("chapter-1.part") == "chapter-1.part"


class TestExtractChapterTitle:
    """Tests for the extract_chapter_title helper."""

    def test_extracts_h1(self) -> None:
        """Finds an h1 title."""
        html = "<html><body><h1>My Chapter</h1><p>text</p></body></html>"
        assert extract_chapter_title(html) == "My Chapter"

    def test_extracts_h2_when_no_h1(self) -> None:
        """Falls back to h2 when no h1 exists."""
        html = "<html><body><h2>Section Title</h2></body></html>"
        assert extract_chapter_title(html) == "Section Title"

    def test_strips_inner_html_tags(self) -> None:
        """Removes nested HTML inside heading."""
        html = "<h1><em>Bold</em> Title</h1>"
        assert extract_chapter_title(html) == "Bold Title"

    def test_returns_none_when_no_heading(self) -> None:
        """Returns None when no headings found."""
        html = "<html><body><p>Just a paragraph</p></body></html>"
        assert extract_chapter_title(html) is None


class TestGetDocumentItems:
    """Tests for the get_document_items helper."""

    def test_returns_items_in_spine_order(self) -> None:
        """Items are returned in the order specified by the spine."""
        book = epub.EpubBook()
        ch1 = epub.EpubHtml(title="Ch1", file_name="ch1.xhtml", lang="en")
        ch1.content = b"<html><body><p>1</p></body></html>"
        ch2 = epub.EpubHtml(title="Ch2", file_name="ch2.xhtml", lang="en")
        ch2.content = b"<html><body><p>2</p></body></html>"
        book.add_item(ch1)
        book.add_item(ch2)
        book.spine = [(ch2.get_id(), "yes"), (ch1.get_id(), "yes")]

        result = get_document_items(book)

        assert len(result) == 2
        assert result[0].get_name() == "ch2.xhtml"
        assert result[1].get_name() == "ch1.xhtml"

    def test_returns_empty_for_no_documents(self) -> None:
        """Returns empty list when book has no document items."""
        book = epub.EpubBook()
        book.spine = []
        assert get_document_items(book) == []


class TestConvertChapter:
    """Tests for the convert_chapter helper."""

    @patch("silly_scripts.cli.epub_to_md.convert")
    def test_converts_chapter_with_title(self, mock_convert) -> None:
        """Uses extracted title for the filename."""
        mock_convert.return_value = "# My Chapter\n\nSome text"
        item = MagicMock()
        item.get_content.return_value = b"<h1>My Chapter</h1><p>Some text</p>"
        item.get_name.return_value = "chapter1.xhtml"

        filename, content = convert_chapter(item, 1)

        assert filename == "001_My_Chapter.md"
        assert content == "# My Chapter\n\nSome text"

    @patch("silly_scripts.cli.epub_to_md.convert")
    def test_falls_back_to_item_name(self, mock_convert) -> None:
        """Uses item name when no heading found."""
        mock_convert.return_value = "plain text"
        item = MagicMock()
        item.get_content.return_value = b"<p>no heading</p>"
        item.get_name.return_value = "section.xhtml"

        filename, _content = convert_chapter(item, 3)

        assert filename == "003_section.xhtml.md"

    @patch("silly_scripts.cli.epub_to_md.convert")
    def test_raises_runtime_error_on_failure(self, mock_convert) -> None:
        """Raises RuntimeError when conversion fails."""
        mock_convert.side_effect = Exception("conversion error")
        item = MagicMock()
        item.get_content.return_value = b"<p>bad</p>"
        item.get_name.return_value = "bad.xhtml"

        with pytest.raises(RuntimeError, match=r"Failed to convert chapter bad\.xhtml"):
            convert_chapter(item, 1)


class TestMainCommand:
    """Tests for the Click CLI command."""

    @patch("silly_scripts.cli.epub_to_md.epub.read_epub")
    @patch("silly_scripts.cli.epub_to_md.convert")
    def test_creates_output_directory_and_converts(
        self, mock_convert, mock_read, tmp_path: Path
    ) -> None:
        """Creates output folder and converts chapters to markdown files."""
        mock_convert.return_value = "# Chapter 1\n\nContent"

        book = epub.EpubBook()
        ch = epub.EpubHtml(title="Ch1", file_name="ch1.xhtml", lang="en")
        ch.content = b"<html><body><h1>Chapter 1</h1><p>Content</p></body></html>"
        book.add_item(ch)
        book.spine = [(ch.get_id(), "yes")]
        mock_read.return_value = book

        epub_file = tmp_path / "my-book.epub"
        epub_file.touch()

        runner = CliRunner()
        result = runner.invoke(main, [str(epub_file)])

        assert result.exit_code == 0
        assert "1 converted, 0 failed" in result.output

        output_dir = tmp_path / "my-book"
        assert output_dir.is_dir()
        md_files = list(output_dir.glob("*.md"))
        assert len(md_files) == 1
        assert md_files[0].read_text(encoding="utf-8") == "# Chapter 1\n\nContent"

    @patch("silly_scripts.cli.epub_to_md.epub.read_epub")
    def test_no_chapters_found(self, mock_read, tmp_path: Path) -> None:
        """Shows message when EPUB has no document items."""
        book = epub.EpubBook()
        book.spine = []
        mock_read.return_value = book

        epub_file = tmp_path / "empty.epub"
        epub_file.touch()

        runner = CliRunner()
        result = runner.invoke(main, [str(epub_file)])

        assert result.exit_code == 0
        assert "No chapters found" in result.output

    @patch("silly_scripts.cli.epub_to_md.epub.read_epub")
    def test_invalid_epub_file(self, mock_read, tmp_path: Path) -> None:
        """Errors when EPUB cannot be read."""
        mock_read.side_effect = Exception("bad epub")

        epub_file = tmp_path / "bad.epub"
        epub_file.touch()

        runner = CliRunner()
        result = runner.invoke(main, [str(epub_file)])

        assert result.exit_code != 0
        assert "Failed to read EPUB file" in result.output

    @patch("silly_scripts.cli.epub_to_md.epub.read_epub")
    @patch("silly_scripts.cli.epub_to_md.convert")
    def test_handles_conversion_failure_gracefully(
        self, mock_convert, mock_read, tmp_path: Path
    ) -> None:
        """Continues when a chapter fails to convert."""
        mock_convert.side_effect = Exception("boom")

        book = epub.EpubBook()
        ch = epub.EpubHtml(title="Ch1", file_name="ch1.xhtml", lang="en")
        ch.content = b"<html><body><h1>Chapter 1</h1></body></html>"
        book.add_item(ch)
        book.spine = [(ch.get_id(), "yes")]
        mock_read.return_value = book

        epub_file = tmp_path / "book.epub"
        epub_file.touch()

        runner = CliRunner()
        result = runner.invoke(main, [str(epub_file)])

        assert result.exit_code == 0
        assert "0 converted, 1 failed" in result.output

    @patch("silly_scripts.cli.epub_to_md.epub.read_epub")
    @patch("silly_scripts.cli.epub_to_md.convert")
    def test_multiple_chapters(self, mock_convert, mock_read, tmp_path: Path) -> None:
        """Converts multiple chapters into separate files."""
        mock_convert.return_value = "markdown content"

        book = epub.EpubBook()
        for i in range(3):
            ch = epub.EpubHtml(title=f"Ch{i}", file_name=f"ch{i}.xhtml", lang="en")
            ch.content = f"<html><body><h1>Chapter {i}</h1></body></html>".encode()
            book.add_item(ch)
            book.spine = [*getattr(book, "spine", []), (ch.get_id(), "yes")]
        mock_read.return_value = book

        epub_file = tmp_path / "multi.epub"
        epub_file.touch()

        runner = CliRunner()
        result = runner.invoke(main, [str(epub_file)])

        assert result.exit_code == 0
        assert "3 converted, 0 failed" in result.output

        output_dir = tmp_path / "multi"
        md_files = list(output_dir.glob("*.md"))
        assert len(md_files) == 3

    def test_nonexistent_file(self) -> None:
        """Errors when EPUB file does not exist."""
        runner = CliRunner()
        result = runner.invoke(main, ["/nonexistent/book.epub"])

        assert result.exit_code != 0

    @patch("silly_scripts.cli.epub_to_md.epub.read_epub")
    @patch("silly_scripts.cli.epub_to_md.convert")
    def test_output_dir_already_exists(
        self, mock_convert, mock_read, tmp_path: Path
    ) -> None:
        """Works when output directory already exists."""
        mock_convert.return_value = "# Content"

        book = epub.EpubBook()
        ch = epub.EpubHtml(title="Ch1", file_name="ch1.xhtml", lang="en")
        ch.content = b"<html><body><h1>Title</h1></body></html>"
        book.add_item(ch)
        book.spine = [(ch.get_id(), "yes")]
        mock_read.return_value = book

        epub_file = tmp_path / "existing.epub"
        epub_file.touch()
        (tmp_path / "existing").mkdir()

        runner = CliRunner()
        result = runner.invoke(main, [str(epub_file)])

        assert result.exit_code == 0
        assert "1 converted" in result.output
