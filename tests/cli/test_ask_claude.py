"""Tests for the ask_claude CLI command."""

import json
from unittest.mock import patch

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKError,
    CLINotFoundError,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)
from click.testing import CliRunner

from silly_scripts.cli.ask_claude import (
    _parse_tools,
    _print_assistant,
    _print_json,
    _resolve_prompt,
    _run_query,
    main,
)
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


class TestPrintAssistant:
    """Tests for assistant message printing."""

    def test_prints_text_blocks(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Prints text content from assistant messages."""
        msg = AssistantMessage(content=[TextBlock(text="Hello world")], model="sonnet")
        _print_assistant(msg, verbose=False)
        captured = capsys.readouterr()
        assert "Hello world" in captured.out

    def test_hides_tool_use_when_not_verbose(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Tool-use blocks are hidden when verbose is False."""
        msg = AssistantMessage(
            content=[ToolUseBlock(id="1", name="Read", input={"path": "/tmp"})],
            model="sonnet",
        )
        _print_assistant(msg, verbose=False)
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_shows_tool_use_when_verbose(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Tool-use blocks are shown on stderr when verbose is True."""
        msg = AssistantMessage(
            content=[ToolUseBlock(id="1", name="Read", input={"path": "/tmp"})],
            model="sonnet",
        )
        _print_assistant(msg, verbose=True)
        captured = capsys.readouterr()
        assert "[tool:Read]" in captured.err
        assert "/tmp" in captured.err


class TestPrintJson:
    """Tests for NDJSON output."""

    def test_serializes_dataclass(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Dataclass messages are serialized as JSON."""
        block = TextBlock(text="hello")
        _print_json(block)
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert data["text"] == "hello"

    def test_fallback_for_non_dataclass(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Non-dataclass objects are serialized with fallback."""
        _print_json("plain string")
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert "raw" in data


def _make_success_messages(text: str = "Answer") -> list:
    """Build a standard success message sequence for tests."""
    return [
        AssistantMessage(content=[TextBlock(text=text)], model="sonnet"),
        ResultMessage(
            subtype="result",
            duration_ms=100,
            duration_api_ms=80,
            is_error=False,
            num_turns=1,
            session_id="s1",
        ),
    ]


def _make_result_only(*, is_error: bool = False, session_id: str = "s1") -> list:
    """Build a result-only message sequence for tests."""
    return [
        ResultMessage(
            subtype="result",
            duration_ms=50,
            duration_api_ms=40,
            is_error=is_error,
            num_turns=1,
            session_id=session_id,
        ),
    ]


class TestRunQuery:
    """Tests for the async _run_query function."""

    @pytest.mark.asyncio
    async def test_streams_text_output(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Text blocks from assistant messages are printed to stdout."""
        messages = _make_success_messages("Hello!")

        async def mock_query(*, prompt, options):  # noqa: ARG001
            for msg in messages:
                yield msg

        with patch("silly_scripts.cli.ask_claude.query", side_effect=mock_query):
            await _run_query(
                "test", ClaudeAgentOptions(), verbose=False, json_mode=False
            )

        captured = capsys.readouterr()
        assert "Hello!" in captured.out

    @pytest.mark.asyncio
    async def test_raises_on_error_result(self) -> None:
        """Raises ClickException when result message indicates an error."""
        messages = _make_result_only(is_error=True, session_id="err-session")

        async def mock_query(*, prompt, options):  # noqa: ARG001
            for msg in messages:
                yield msg

        with (
            patch("silly_scripts.cli.ask_claude.query", side_effect=mock_query),
            pytest.raises(Exception, match="error"),
        ):
            await _run_query(
                "test", ClaudeAgentOptions(), verbose=False, json_mode=False
            )

    @pytest.mark.asyncio
    async def test_json_mode_outputs_ndjson(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """In JSON mode, messages are serialized as NDJSON."""
        messages = _make_success_messages("Hi")

        async def mock_query(*, prompt, options):  # noqa: ARG001
            for msg in messages:
                yield msg

        with patch("silly_scripts.cli.ask_claude.query", side_effect=mock_query):
            await _run_query(
                "test", ClaudeAgentOptions(), verbose=False, json_mode=True
            )

        captured = capsys.readouterr()
        lines = [line for line in captured.out.strip().split("\n") if line]
        assert len(lines) == 2
        # Each line should be valid JSON
        for line in lines:
            json.loads(line)


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

    def test_missing_api_key_prints_error(self) -> None:
        """Missing API key produces a clear error and non-zero exit code."""
        runner = CliRunner()
        with patch.dict("os.environ", {}, clear=True):
            get_settings.cache_clear()
            result = runner.invoke(main, ["test prompt"], catch_exceptions=False)
        assert result.exit_code != 0
        assert "API key" in result.output

    def test_successful_query_exits_zero(self) -> None:
        """Successful query exits with code 0."""
        messages = _make_success_messages()

        async def mock_query(*, prompt, options):  # noqa: ARG001
            for msg in messages:
                yield msg

        runner = CliRunner()
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-key"}),
            patch("silly_scripts.cli.ask_claude.query", side_effect=mock_query),
        ):
            get_settings.cache_clear()
            result = runner.invoke(main, ["test prompt"])

        assert result.exit_code == 0
        assert "Answer" in result.output

    def test_sdk_error_exits_nonzero(self) -> None:
        """SDK errors produce non-zero exit code with message."""

        async def mock_query(*, prompt, options):  # noqa: ARG001
            msg = "connection lost"
            raise ClaudeSDKError(msg)
            yield  # make it an async generator  # pragma: no cover

        runner = CliRunner()
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-key"}),
            patch("silly_scripts.cli.ask_claude.query", side_effect=mock_query),
        ):
            get_settings.cache_clear()
            result = runner.invoke(main, ["test prompt"])

        assert result.exit_code != 0
        assert "SDK error" in result.output

    def test_cli_not_found_exits_nonzero(self) -> None:
        """CLINotFoundError produces non-zero exit code with message."""

        async def mock_query(*, prompt, options):  # noqa: ARG001
            raise CLINotFoundError
            yield  # make it an async generator  # pragma: no cover

        runner = CliRunner()
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-key"}),
            patch("silly_scripts.cli.ask_claude.query", side_effect=mock_query),
        ):
            get_settings.cache_clear()
            result = runner.invoke(main, ["test prompt"])

        assert result.exit_code != 0
        assert "not found" in result.output

    def test_invalid_permission_mode_rejected(self) -> None:
        """Invalid permission mode is rejected by Click."""
        runner = CliRunner()
        result = runner.invoke(main, ["hello", "--permission-mode", "invalid"])
        assert result.exit_code != 0
        assert "Invalid value" in result.output

    def test_stdin_pipe_with_api_key(self) -> None:
        """Piped stdin is accepted as prompt when API key is set."""
        messages = _make_result_only()

        async def mock_query(*, prompt, options):  # noqa: ARG001
            for msg in messages:
                yield msg

        runner = CliRunner()
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-key"}),
            patch("silly_scripts.cli.ask_claude.query", side_effect=mock_query),
        ):
            get_settings.cache_clear()
            result = runner.invoke(main, [], input="piped prompt\n")

        assert result.exit_code == 0

    def test_model_flag_passed_to_options(self) -> None:
        """--model flag value is forwarded to SDK options."""
        captured_options = {}

        async def mock_query(*, prompt, options):  # noqa: ARG001
            captured_options["model"] = options.model
            yield ResultMessage(
                subtype="result",
                duration_ms=50,
                duration_api_ms=40,
                is_error=False,
                num_turns=1,
                session_id="s1",
            )

        runner = CliRunner()
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-key"}),
            patch("silly_scripts.cli.ask_claude.query", side_effect=mock_query),
        ):
            get_settings.cache_clear()
            result = runner.invoke(main, ["hello", "--model", "opus"])

        assert result.exit_code == 0
        assert captured_options["model"] == "opus"
