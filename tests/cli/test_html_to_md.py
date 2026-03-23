"""Tests for the html_to_md CLI command."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from silly_scripts.cli.html_to_md import convert_file, find_html_files, main


if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def _mock_convert_error():
    """Mock html_to_markdown.convert to always raise."""
    with patch(
        "silly_scripts.cli.html_to_md.convert",
        side_effect=Exception("boom"),
    ):
        yield


class TestFindHtmlFiles:
    """Tests for the find_html_files helper."""

    def test_finds_html_and_htm_files(self, tmp_path: Path) -> None:
        """Finds both .html and .htm files."""
        (tmp_path / "page.html").write_text("<p>hello</p>")
        (tmp_path / "other.htm").write_text("<p>world</p>")
        (tmp_path / "readme.md").write_text("# Not HTML")

        result = find_html_files(tmp_path)

        assert len(result) == 2
        names = {p.name for p in result}
        assert names == {"page.html", "other.htm"}

    def test_returns_empty_for_no_html(self, tmp_path: Path) -> None:
        """Returns empty list when no HTML files exist."""
        (tmp_path / "data.json").write_text("{}")

        result = find_html_files(tmp_path)

        assert result == []

    def test_returns_sorted_results(self, tmp_path: Path) -> None:
        """Results are sorted by path."""
        (tmp_path / "z.html").write_text("<p>z</p>")
        (tmp_path / "a.html").write_text("<p>a</p>")

        result = find_html_files(tmp_path)

        assert result[0].name == "a.html"
        assert result[1].name == "z.html"


class TestConvertFile:
    """Tests for the convert_file helper."""

    @patch("silly_scripts.cli.html_to_md.convert")
    def test_converts_and_saves_md(self, mock_convert, tmp_path: Path) -> None:
        """Converts HTML content and writes .md file."""
        mock_convert.return_value = "# Hello\n\nWorld"
        html_path = tmp_path / "page.html"
        html_path.write_text("<h1>Hello</h1><p>World</p>")

        md_path = convert_file(html_path)

        assert md_path == tmp_path / "page.md"
        assert md_path.read_text() == "# Hello\n\nWorld"
        mock_convert.assert_called_once_with("<h1>Hello</h1><p>World</p>")

    @patch("silly_scripts.cli.html_to_md.convert")
    def test_htm_extension_becomes_md(self, mock_convert, tmp_path: Path) -> None:
        """A .htm file produces a .md file."""
        mock_convert.return_value = "content"
        html_path = tmp_path / "page.htm"
        html_path.write_text("<p>hi</p>")

        md_path = convert_file(html_path)

        assert md_path.suffix == ".md"

    @pytest.mark.usefixtures("_mock_convert_error")
    def test_raises_runtime_error_on_failure(self, tmp_path: Path) -> None:
        """Raises RuntimeError when conversion fails."""
        html_path = tmp_path / "bad.html"
        html_path.write_text("<invalid>")

        with pytest.raises(RuntimeError, match=r"Failed to convert bad\.html"):
            convert_file(html_path)


class TestMainCommand:
    """Tests for the Click CLI command."""

    @patch("silly_scripts.cli.html_to_md.convert")
    def test_converts_all_files(self, mock_convert, tmp_path: Path) -> None:
        """Successfully converts multiple HTML files."""
        mock_convert.return_value = "# Markdown"
        (tmp_path / "a.html").write_text("<h1>A</h1>")
        (tmp_path / "b.htm").write_text("<h1>B</h1>")

        runner = CliRunner()
        result = runner.invoke(main, [str(tmp_path)])

        assert result.exit_code == 0
        assert "Found 2 HTML file(s)" in result.output
        assert "2 converted, 0 failed" in result.output
        assert (tmp_path / "a.md").exists()
        assert (tmp_path / "b.md").exists()

    def test_no_html_files(self, tmp_path: Path) -> None:
        """Shows message when no HTML files found."""
        runner = CliRunner()
        result = runner.invoke(main, [str(tmp_path)])

        assert result.exit_code == 0
        assert "No .html or .htm files found" in result.output

    @pytest.mark.usefixtures("_mock_convert_error")
    def test_handles_conversion_failure(self, tmp_path: Path) -> None:
        """Continues processing when a file fails to convert."""
        (tmp_path / "good.html").write_text("<p>hi</p>")

        runner = CliRunner()
        result = runner.invoke(main, [str(tmp_path)])

        assert result.exit_code == 0
        assert "0 converted, 1 failed" in result.output

    def test_invalid_folder(self) -> None:
        """Errors when folder does not exist."""
        runner = CliRunner()
        result = runner.invoke(main, ["/nonexistent/path"])

        assert result.exit_code != 0
