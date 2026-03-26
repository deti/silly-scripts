"""Tests for split_prompts CLI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from click.testing import CliRunner


if TYPE_CHECKING:
    from pathlib import Path

from silly_scripts.cli.split_prompts import extract_prompts, main


class TestExtractPrompts:
    """Tests for the extract_prompts helper."""

    def test_extracts_single_prompt(self) -> None:
        """Extract a single prompt from markdown."""
        content = "# Title\n\n## Prompt 01: First\n\n```\nDo something\n```\n"
        result = extract_prompts(content)
        assert result == ["Do something"]

    def test_extracts_multiple_prompts(self) -> None:
        """Extract multiple prompts preserving order."""
        content = (
            "# Title\n\n"
            "## Prompt 01: First\n\n```\nAAA\n```\n\n"
            "---\n\n"
            "## Prompt 02: Second\n\n```\nBBB\n```\n\n"
            "## Prompt 03: Third\n\n```\nCCC\n```\n"
        )
        result = extract_prompts(content)
        assert result == ["AAA", "BBB", "CCC"]

    def test_returns_empty_when_no_prompts(self) -> None:
        """Return empty list when no prompt headers found."""
        content = "# Just a title\n\nSome text.\n"
        result = extract_prompts(content)
        assert result == []

    def test_skips_prompt_without_code_block(self) -> None:
        """Skip prompts that have no code block."""
        content = (
            "## Prompt 01: Has code\n\n```\nAAA\n```\n\n"
            "## Prompt 02: No code\n\nJust text.\n\n"
            "## Prompt 03: Has code\n\n```\nCCC\n```\n"
        )
        result = extract_prompts(content)
        assert result == ["AAA", "CCC"]

    def test_preserves_multiline_content(self) -> None:
        """Preserve multiline prompt content."""
        content = "## Prompt 01: Multi\n\n```\nLine 1\nLine 2\nLine 3\n```\n"
        result = extract_prompts(content)
        assert result == ["Line 1\nLine 2\nLine 3"]

    def test_ignores_preamble(self) -> None:
        """Content before first prompt header is ignored."""
        content = (
            "# Big header\n\n> Some notes\n\n## Prompt 1: Only one\n\n```\nHello\n```\n"
        )
        result = extract_prompts(content)
        assert result == ["Hello"]


class TestMainCli:
    """Tests for the CLI entry point."""

    def test_splits_prompts_into_files(self, tmp_path: Path) -> None:
        """Create numbered prompt files in output directory."""
        md_file = tmp_path / "my-prompts.md"
        md_file.write_text(
            "## Prompt 01: A\n\n```\nFirst prompt\n```\n\n"
            "## Prompt 02: B\n\n```\nSecond prompt\n```\n"
        )

        runner = CliRunner()
        result = runner.invoke(main, [str(md_file)])

        assert result.exit_code == 0
        output_dir = tmp_path / "my-prompts"
        assert output_dir.is_dir()
        assert (output_dir / "Prompt01.md").read_text() == "First prompt\n"
        assert (output_dir / "Prompt02.md").read_text() == "Second prompt\n"
        assert "Extracted 2 prompts" in result.output

    def test_error_when_no_prompts(self, tmp_path: Path) -> None:
        """Exit with error when no prompts found."""
        md_file = tmp_path / "empty.md"
        md_file.write_text("# Nothing here\n")

        runner = CliRunner()
        result = runner.invoke(main, [str(md_file)])

        assert result.exit_code != 0
        assert "No prompts found" in result.output

    def test_error_when_file_missing(self, tmp_path: Path) -> None:
        """Exit with error when input file does not exist."""
        runner = CliRunner()
        result = runner.invoke(main, [str(tmp_path / "nonexistent.md")])

        assert result.exit_code != 0

    def test_creates_output_dir(self, tmp_path: Path) -> None:
        """Output directory is created if it does not exist."""
        md_file = tmp_path / "test-file.md"
        md_file.write_text("## Prompt 1: X\n\n```\nContent\n```\n")

        runner = CliRunner()
        result = runner.invoke(main, [str(md_file)])

        assert result.exit_code == 0
        assert (tmp_path / "test-file").is_dir()
