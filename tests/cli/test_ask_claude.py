"""Tests for the ask_claude CLI command."""

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from silly_scripts.cli.ask_claude import _parse_tools, _resolve_prompt, main
from silly_scripts.settings import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    """Clear settings cache before and after each test."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class TestResolvePrompt:
    """Tests for prompt resolution logic."""

    def test_positional_arg_wins(self) -> None:
        """Positional argument is used when provided."""
        assert _resolve_prompt("hello", None) == "hello"

    def test_flag_used_when_no_positional(self) -> None:
        """Flag is used when positional is absent."""
        assert _resolve_prompt(None, "from flag") == "from flag"

    def test_positional_takes_precedence_over_flag(self) -> None:
        """Positional argument takes precedence over flag."""
        assert _resolve_prompt("positional", "flag") == "positional"

    def test_raises_when_no_prompt(self) -> None:
        """Raises UsageError when no prompt is provided and stdin is a tty."""
        with patch("silly_scripts.cli.ask_claude.sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            with pytest.raises(Exception, match="No prompt provided"):
                _resolve_prompt(None, None)

    def test_reads_from_stdin_pipe(self) -> None:
        """Reads prompt from stdin when piped."""
        with patch("silly_scripts.cli.ask_claude.sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = "piped input\n"
            assert _resolve_prompt(None, None) == "piped input"

    def test_raises_on_empty_stdin(self) -> None:
        """Raises UsageError when stdin pipe is empty."""
        with patch("silly_scripts.cli.ask_claude.sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = "   "
            with pytest.raises(Exception, match="No prompt provided"):
                _resolve_prompt(None, None)


class TestParseTools:
    """Tests for tool string parsing."""

    def test_basic_comma_separated(self) -> None:
        """Parses comma-separated tools."""
        assert _parse_tools("Read,Glob,Grep") == ["Read", "Glob", "Grep"]

    def test_whitespace_trimmed(self) -> None:
        """Trims whitespace around tool names."""
        assert _parse_tools("Read , Glob , Grep") == ["Read", "Glob", "Grep"]

    def test_empty_entries_ignored(self) -> None:
        """Ignores empty entries from trailing commas."""
        assert _parse_tools("Read,,Grep,") == ["Read", "Grep"]

    def test_single_tool(self) -> None:
        """Handles a single tool."""
        assert _parse_tools("Read") == ["Read"]


class TestCli:
    """Integration tests for the Click CLI."""

    def test_help_flag(self) -> None:
        """--help prints usage without crashing."""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Ask Claude a question" in result.output
        assert "--model" in result.output
        assert "--tools" in result.output
        assert "--verbose" in result.output
        assert "--json" in result.output

    def test_no_args_prints_error(self) -> None:
        """Running with no args and no stdin prints an error."""
        runner = CliRunner()
        result = runner.invoke(main, [])
        assert result.exit_code != 0
        assert "No prompt provided" in result.output

    def test_prompt_positional_accepted(self) -> None:
        """Positional prompt is accepted and reaches the scaffold stub."""
        runner = CliRunner()
        result = runner.invoke(main, ["test prompt"])
        # Should hit the "not yet implemented" error
        assert result.exit_code != 0
        assert "Not yet implemented" in result.output

    def test_prompt_flag_accepted(self) -> None:
        """--prompt flag is accepted."""
        runner = CliRunner()
        result = runner.invoke(main, ["--prompt", "test prompt"])
        assert result.exit_code != 0
        assert "Not yet implemented" in result.output

    def test_model_flag_accepted(self) -> None:
        """--model flag is accepted without error."""
        runner = CliRunner()
        result = runner.invoke(main, ["hello", "--model", "opus"])
        assert result.exit_code != 0
        assert "Not yet implemented" in result.output

    def test_invalid_permission_mode_rejected(self) -> None:
        """Invalid permission mode is rejected by Click."""
        runner = CliRunner()
        result = runner.invoke(main, ["hello", "--permission-mode", "invalid"])
        assert result.exit_code != 0
        assert "Invalid value" in result.output

    def test_stdin_pipe(self) -> None:
        """Piped stdin is accepted as prompt."""
        runner = CliRunner()
        result = runner.invoke(main, [], input="piped prompt\n")
        assert result.exit_code != 0
        assert "Not yet implemented" in result.output
