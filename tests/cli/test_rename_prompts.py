"""Tests for the rename_prompts CLI command."""

from __future__ import annotations

from typing import TYPE_CHECKING

from click.testing import CliRunner


if TYPE_CHECKING:
    from pathlib import Path

from silly_scripts.cli.rename_prompts import (
    build_new_name,
    extract_feature_code,
    main,
)


def _create_prompt_file(folder: Path, name: str, first_line: str) -> Path:
    """Create a prompt file with the given first line."""
    path = folder / name
    path.write_text(f"{first_line}\n\nSome content here.\n", encoding="utf-8")
    return path


class TestExtractFeatureCode:
    """Tests for extract_feature_code."""

    def test_standard_feature_line(self, tmp_path: Path) -> None:
        """Extracts feature code from a standard header."""
        f = _create_prompt_file(tmp_path, "S01.md", "# F7.S1 — Internal event bus")
        assert extract_feature_code(f) == "F7"

    def test_multi_digit_feature(self, tmp_path: Path) -> None:
        """Extracts multi-digit feature codes."""
        f = _create_prompt_file(tmp_path, "S01.md", "# F12.S3 — Something")
        assert extract_feature_code(f) == "F12"

    def test_no_feature_code(self, tmp_path: Path) -> None:
        """Returns None when the first line has no feature code."""
        f = _create_prompt_file(tmp_path, "S01.md", "# Just a title")
        assert extract_feature_code(f) is None

    def test_empty_file(self, tmp_path: Path) -> None:
        """Returns None for an empty file."""
        f = tmp_path / "S01.md"
        f.write_text("", encoding="utf-8")
        assert extract_feature_code(f) is None


class TestBuildNewName:
    """Tests for build_new_name."""

    def test_standard_rename(self) -> None:
        """Prepends feature code to filename."""
        assert build_new_name("S01-event-bus.md", "F7") == "F7-S01-event-bus.md"

    def test_different_feature(self) -> None:
        """Works with different feature codes."""
        assert build_new_name("S03-auth.md", "F12") == "F12-S03-auth.md"


class TestMainCommand:
    """Tests for the CLI main command."""

    def test_renames_files(self, tmp_path: Path) -> None:
        """Renames matching files correctly."""
        _create_prompt_file(
            tmp_path, "S01-event-bus.md", "# F7.S1 — Internal event bus"
        )
        _create_prompt_file(tmp_path, "S02-auth.md", "# F7.S2 — Auth module")

        runner = CliRunner()
        result = runner.invoke(main, [str(tmp_path)])

        assert result.exit_code == 0
        assert (tmp_path / "F7-S01-event-bus.md").exists()
        assert (tmp_path / "F7-S02-auth.md").exists()
        assert not (tmp_path / "S01-event-bus.md").exists()
        assert not (tmp_path / "S02-auth.md").exists()

    def test_dry_run(self, tmp_path: Path) -> None:
        """Dry run shows renames without performing them."""
        _create_prompt_file(
            tmp_path, "S01-event-bus.md", "# F7.S1 — Internal event bus"
        )

        runner = CliRunner()
        result = runner.invoke(main, [str(tmp_path), "--dry-run"])

        assert result.exit_code == 0
        assert "S01-event-bus.md -> F7-S01-event-bus.md" in result.output
        assert (tmp_path / "S01-event-bus.md").exists()
        assert not (tmp_path / "F7-S01-event-bus.md").exists()

    def test_skips_non_s_files(self, tmp_path: Path) -> None:
        """Ignores files that don't start with S."""
        _create_prompt_file(
            tmp_path, "S01-event-bus.md", "# F7.S1 — Internal event bus"
        )
        _create_prompt_file(tmp_path, "README.md", "# README")

        runner = CliRunner()
        result = runner.invoke(main, [str(tmp_path)])

        assert result.exit_code == 0
        assert (tmp_path / "README.md").exists()
        assert (tmp_path / "F7-S01-event-bus.md").exists()

    def test_skips_files_without_feature_code(self, tmp_path: Path) -> None:
        """Skips S-files that lack a feature code in the first line."""
        _create_prompt_file(
            tmp_path, "S01-event-bus.md", "# F7.S1 — Internal event bus"
        )
        _create_prompt_file(tmp_path, "S02-notes.md", "# Just some notes")

        runner = CliRunner()
        result = runner.invoke(main, [str(tmp_path)])

        assert result.exit_code == 0
        assert (tmp_path / "F7-S01-event-bus.md").exists()
        assert (tmp_path / "S02-notes.md").exists()
        assert "Renamed 1 files" in result.output

    def test_no_matching_files(self, tmp_path: Path) -> None:
        """Raises error when no S-prefixed markdown files found."""
        _create_prompt_file(tmp_path, "README.md", "# README")

        runner = CliRunner()
        result = runner.invoke(main, [str(tmp_path)])

        assert result.exit_code != 0
        assert "No markdown files starting with 'S' found" in result.output

    def test_mixed_features(self, tmp_path: Path) -> None:
        """Handles files from different features correctly."""
        _create_prompt_file(tmp_path, "S01-bus.md", "# F7.S1 — Event bus")
        _create_prompt_file(tmp_path, "S02-api.md", "# F8.S1 — API layer")

        runner = CliRunner()
        result = runner.invoke(main, [str(tmp_path)])

        assert result.exit_code == 0
        assert (tmp_path / "F7-S01-bus.md").exists()
        assert (tmp_path / "F8-S02-api.md").exists()
