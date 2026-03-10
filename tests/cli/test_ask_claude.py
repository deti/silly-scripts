"""Tests for the ask_claude CLI command."""

import json
from unittest.mock import patch

import click
import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKError,
    CLINotFoundError,
    ProcessError,
    ResultMessage,
    SystemMessage,
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
        """--help prints usage and examples without crashing."""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Ask Claude a question" in result.output
        assert "--model" in result.output
        assert "--tools" in result.output
        assert "--verbose" in result.output
        assert "--json" in result.output
        assert "--system-prompt" in result.output
        assert "--permission-mode" in result.output
        assert "--working-dir" in result.output
        assert "Examples:" in result.output
        assert "ask-claude" in result.output

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

    def test_process_error_exits_nonzero(self) -> None:
        """ProcessError produces non-zero exit code with message."""

        async def mock_query(*, prompt, options):  # noqa: ARG001
            msg = "process crashed"
            raise ProcessError(msg)
            yield  # make it an async generator  # pragma: no cover

        runner = CliRunner()
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-key"}),
            patch("silly_scripts.cli.ask_claude.query", side_effect=mock_query),
        ):
            get_settings.cache_clear()
            result = runner.invoke(main, ["test prompt"])

        assert result.exit_code != 0
        assert "process failed" in result.output

    def test_keyboard_interrupt_exits_130(self) -> None:
        """KeyboardInterrupt produces exit code 130 with message."""

        async def mock_query(*, prompt, options):  # noqa: ARG001
            raise KeyboardInterrupt
            yield  # make it an async generator  # pragma: no cover

        runner = CliRunner()
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-key"}),
            patch("silly_scripts.cli.ask_claude.query", side_effect=mock_query),
        ):
            get_settings.cache_clear()
            result = runner.invoke(main, ["test prompt"])

        assert result.exit_code == 130

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


# ---------------------------------------------------------------------------
# Additional unit tests: edge cases for prompt resolution
# ---------------------------------------------------------------------------


class TestResolvePromptEdgeCases:
    """Edge-case tests for _resolve_prompt."""

    def test_empty_string_positional_falls_through_to_flag(self) -> None:
        """Empty string positional arg is falsy, so flag is used instead."""
        assert _resolve_prompt("", "fallback") == "fallback"

    def test_empty_string_both_raises(self) -> None:
        """Empty string for both positional and flag raises UsageError."""
        with patch("silly_scripts.cli.ask_claude.sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            with pytest.raises(click.UsageError, match="No prompt provided"):
                _resolve_prompt("", "")

    def test_whitespace_only_positional_falls_through(self) -> None:
        """Whitespace-only positional is truthy but preserved as-is."""
        # " " is truthy, so it's returned directly
        assert _resolve_prompt("   ", None) == "   "

    def test_very_long_prompt_accepted(self) -> None:
        """Very long prompts are accepted without truncation."""
        long_prompt = "x" * 100_000
        assert _resolve_prompt(long_prompt, None) == long_prompt

    def test_prompt_with_newlines(self) -> None:
        """Prompts containing newlines are preserved."""
        multiline = "line1\nline2\nline3"
        assert _resolve_prompt(multiline, None) == multiline

    def test_prompt_with_unicode(self) -> None:
        """Unicode characters in prompts are preserved."""
        unicode_prompt = "こんにちは 🌍 résumé"
        assert _resolve_prompt(unicode_prompt, None) == unicode_prompt


# ---------------------------------------------------------------------------
# Additional unit tests: edge cases for tool parsing
# ---------------------------------------------------------------------------


class TestParseToolsEdgeCases:
    """Edge-case tests for _parse_tools."""

    def test_empty_string_returns_empty_list(self) -> None:
        """Empty string returns an empty list."""
        assert _parse_tools("") == []

    def test_only_commas_returns_empty_list(self) -> None:
        """String of only commas returns an empty list."""
        assert _parse_tools(",,,") == []

    def test_only_whitespace_returns_empty_list(self) -> None:
        """Whitespace-only entries are filtered out."""
        assert _parse_tools("  ,  ,  ") == []


# ---------------------------------------------------------------------------
# Additional unit tests: _print_assistant with multiple blocks
# ---------------------------------------------------------------------------


class TestPrintAssistantEdgeCases:
    """Edge-case tests for _print_assistant."""

    def test_multiple_text_blocks_printed_in_order(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Multiple text blocks in one message are all printed to stdout."""
        msg = AssistantMessage(
            content=[
                TextBlock(text="first"),
                TextBlock(text="second"),
                TextBlock(text="third"),
            ],
            model="sonnet",
        )
        _print_assistant(msg, verbose=False)
        captured = capsys.readouterr()
        assert "first" in captured.out
        assert "second" in captured.out
        assert "third" in captured.out
        # Verify order: first before second before third
        assert captured.out.index("first") < captured.out.index("second")
        assert captured.out.index("second") < captured.out.index("third")

    def test_mixed_blocks_text_and_tool(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Text blocks are printed, tool blocks hidden when not verbose."""
        msg = AssistantMessage(
            content=[
                TextBlock(text="visible text"),
                ToolUseBlock(id="t1", name="Grep", input={"pattern": "foo"}),
            ],
            model="sonnet",
        )
        _print_assistant(msg, verbose=False)
        captured = capsys.readouterr()
        assert "visible text" in captured.out
        assert "Grep" not in captured.out
        assert "Grep" not in captured.err

    def test_empty_content_list(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Message with empty content list produces no output."""
        msg = AssistantMessage(content=[], model="sonnet")
        _print_assistant(msg, verbose=False)
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_empty_text_block(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Text block with empty string still calls echo (prints newline)."""
        msg = AssistantMessage(content=[TextBlock(text="")], model="sonnet")
        _print_assistant(msg, verbose=False)
        captured = capsys.readouterr()
        # click.echo("") prints a newline
        assert captured.out == "\n"


# ---------------------------------------------------------------------------
# Additional unit tests: _print_json edge cases
# ---------------------------------------------------------------------------


class TestPrintJsonEdgeCases:
    """Edge-case tests for _print_json."""

    def test_result_message_serialized(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """ResultMessage with cost field serializes correctly."""
        msg = ResultMessage(
            subtype="result",
            duration_ms=200,
            duration_api_ms=150,
            is_error=False,
            num_turns=3,
            session_id="s42",
            total_cost_usd=0.05,
        )
        _print_json(msg)
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert data["session_id"] == "s42"
        assert data["num_turns"] == 3
        assert data["total_cost_usd"] == 0.05

    def test_assistant_message_with_tool_use_serialized(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """AssistantMessage containing ToolUseBlock serializes as JSON."""
        msg = AssistantMessage(
            content=[ToolUseBlock(id="t1", name="Read", input={"path": "/x"})],
            model="opus",
        )
        _print_json(msg)
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip())
        assert data["model"] == "opus"
        assert data["content"][0]["name"] == "Read"


# ---------------------------------------------------------------------------
# Additional async tests: _run_query streaming and message types
# ---------------------------------------------------------------------------


class TestRunQueryEdgeCases:
    """Edge-case tests for the async _run_query function."""

    @pytest.mark.asyncio
    async def test_multiple_assistant_messages_streamed(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Multiple assistant messages stream text incrementally to stdout."""
        messages = [
            AssistantMessage(content=[TextBlock(text="chunk1")], model="sonnet"),
            AssistantMessage(content=[TextBlock(text="chunk2")], model="sonnet"),
            AssistantMessage(content=[TextBlock(text="chunk3")], model="sonnet"),
            ResultMessage(
                subtype="result",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="s1",
            ),
        ]

        async def mock_query(*, prompt, options):  # noqa: ARG001
            for msg in messages:
                yield msg

        with patch("silly_scripts.cli.ask_claude.query", side_effect=mock_query):
            await _run_query(
                "test", ClaudeAgentOptions(), verbose=False, json_mode=False
            )

        captured = capsys.readouterr()
        assert "chunk1" in captured.out
        assert "chunk2" in captured.out
        assert "chunk3" in captured.out

    @pytest.mark.asyncio
    async def test_system_message_hidden_when_not_verbose(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """System messages are hidden when verbose is False."""
        messages = [
            SystemMessage(subtype="init", data={"version": "1.0"}),
            ResultMessage(
                subtype="result",
                duration_ms=50,
                duration_api_ms=40,
                is_error=False,
                num_turns=1,
                session_id="s1",
            ),
        ]

        async def mock_query(*, prompt, options):  # noqa: ARG001
            for msg in messages:
                yield msg

        with patch("silly_scripts.cli.ask_claude.query", side_effect=mock_query):
            await _run_query(
                "test", ClaudeAgentOptions(), verbose=False, json_mode=False
            )

        captured = capsys.readouterr()
        assert captured.out == ""
        assert "init" not in captured.err

    @pytest.mark.asyncio
    async def test_system_message_shown_when_verbose(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """System messages are shown on stderr when verbose is True."""
        messages = [
            SystemMessage(subtype="init", data={"version": "1.0"}),
            ResultMessage(
                subtype="result",
                duration_ms=50,
                duration_api_ms=40,
                is_error=False,
                num_turns=1,
                session_id="s1",
            ),
        ]

        async def mock_query(*, prompt, options):  # noqa: ARG001
            for msg in messages:
                yield msg

        with patch("silly_scripts.cli.ask_claude.query", side_effect=mock_query):
            await _run_query(
                "test", ClaudeAgentOptions(), verbose=True, json_mode=False
            )

        captured = capsys.readouterr()
        assert "[system:init]" in captured.err

    @pytest.mark.asyncio
    async def test_error_result_includes_session_id(self) -> None:
        """Error result ClickException message includes session ID."""
        messages = [
            ResultMessage(
                subtype="result",
                duration_ms=50,
                duration_api_ms=40,
                is_error=True,
                num_turns=1,
                session_id="err-sess-42",
            ),
        ]

        async def mock_query(*, prompt, options):  # noqa: ARG001
            for msg in messages:
                yield msg

        with (
            patch("silly_scripts.cli.ask_claude.query", side_effect=mock_query),
            pytest.raises(click.ClickException, match="err-sess-42"),
        ):
            await _run_query(
                "test", ClaudeAgentOptions(), verbose=False, json_mode=False
            )

    @pytest.mark.asyncio
    async def test_json_mode_system_message_serialized(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """In JSON mode, system messages are also serialized as NDJSON."""
        messages = [
            SystemMessage(subtype="init", data={"version": "1.0"}),
            ResultMessage(
                subtype="result",
                duration_ms=50,
                duration_api_ms=40,
                is_error=False,
                num_turns=1,
                session_id="s1",
            ),
        ]

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
        system_data = json.loads(lines[0])
        assert system_data["subtype"] == "init"

    @pytest.mark.asyncio
    async def test_very_long_prompt_forwarded(self) -> None:
        """Very long prompts are forwarded to the SDK without truncation."""
        long_prompt = "a" * 100_000
        captured_prompt = {}

        async def mock_query(*, prompt, options):  # noqa: ARG001
            captured_prompt["value"] = prompt
            for msg in _make_result_only():
                yield msg

        with patch("silly_scripts.cli.ask_claude.query", side_effect=mock_query):
            await _run_query(
                long_prompt, ClaudeAgentOptions(), verbose=False, json_mode=False
            )

        assert captured_prompt["value"] == long_prompt
        assert len(captured_prompt["value"]) == 100_000


# ---------------------------------------------------------------------------
# Additional CLI integration tests: options forwarding
# ---------------------------------------------------------------------------


class TestCliOptionsForwarding:
    """Integration tests verifying all CLI options are forwarded to the SDK."""

    def _run_with_captured_options(
        self, cli_args: list[str], *, input_text: str | None = None
    ) -> tuple:
        """Helper: run CLI, capture prompt + options passed to query()."""
        captured = {}

        async def mock_query(*, prompt, options):
            captured["prompt"] = prompt
            captured["options"] = options
            for msg in _make_result_only():
                yield msg

        runner = CliRunner()
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-key"}),
            patch("silly_scripts.cli.ask_claude.query", side_effect=mock_query),
        ):
            get_settings.cache_clear()
            result = runner.invoke(main, cli_args, input=input_text)

        return result, captured

    def test_tools_flag_forwarded(self) -> None:
        """--tools flag is parsed and forwarded to allowed_tools."""
        result, captured = self._run_with_captured_options(
            ["hello", "--tools", "Write,Edit,Bash"]
        )
        assert result.exit_code == 0
        assert captured["options"].allowed_tools == ["Write", "Edit", "Bash"]

    def test_system_prompt_forwarded(self) -> None:
        """--system-prompt flag is forwarded to options."""
        result, captured = self._run_with_captured_options(
            ["hello", "--system-prompt", "Be concise."]
        )
        assert result.exit_code == 0
        assert captured["options"].system_prompt == "Be concise."

    def test_permission_mode_forwarded(self) -> None:
        """--permission-mode flag is forwarded to options."""
        result, captured = self._run_with_captured_options(
            ["hello", "--permission-mode", "bypassPermissions"]
        )
        assert result.exit_code == 0
        assert captured["options"].permission_mode == "bypassPermissions"

    def test_working_dir_forwarded(self, tmp_path: pytest.TempPathFactory) -> None:
        """--working-dir flag is forwarded to options.cwd."""
        result, captured = self._run_with_captured_options(
            ["hello", "--working-dir", str(tmp_path)]
        )
        assert result.exit_code == 0
        assert captured["options"].cwd == str(tmp_path)

    def test_prompt_flag_short_form(self) -> None:
        """-p short form for --prompt is accepted."""
        result, captured = self._run_with_captured_options(["-p", "short flag prompt"])
        assert result.exit_code == 0
        assert captured["prompt"] == "short flag prompt"

    def test_model_short_form(self) -> None:
        """-m short form for --model is accepted."""
        result, captured = self._run_with_captured_options(["hello", "-m", "haiku"])
        assert result.exit_code == 0
        assert captured["options"].model == "haiku"

    def test_tools_short_form(self) -> None:
        """-t short form for --tools is accepted."""
        result, captured = self._run_with_captured_options(["hello", "-t", "Read"])
        assert result.exit_code == 0
        assert captured["options"].allowed_tools == ["Read"]

    def test_default_model_from_settings(self) -> None:
        """Default model comes from settings when --model is not provided."""
        result, captured = self._run_with_captured_options(["hello"])
        assert result.exit_code == 0
        # Default from settings is "sonnet"
        assert captured["options"].model == "sonnet"

    def test_default_tools_from_settings(self) -> None:
        """Default tools come from settings when --tools is not provided."""
        result, captured = self._run_with_captured_options(["hello"])
        assert result.exit_code == 0
        assert captured["options"].allowed_tools == ["Read", "Glob", "Grep"]

    def test_prompt_forwarded_to_query(self) -> None:
        """Prompt text is forwarded verbatim to query()."""
        result, captured = self._run_with_captured_options(
            ["Tell me about Python 3.14"]
        )
        assert result.exit_code == 0
        assert captured["prompt"] == "Tell me about Python 3.14"


# ---------------------------------------------------------------------------
# Additional CLI integration tests: output behavior
# ---------------------------------------------------------------------------


class TestCliOutputBehavior:
    """Integration tests for CLI output formatting and streaming."""

    def test_streamed_text_appears_in_stdout(self) -> None:
        """Text from multiple assistant messages appears in CLI stdout."""
        messages = [
            AssistantMessage(content=[TextBlock(text="Part 1.")], model="sonnet"),
            AssistantMessage(content=[TextBlock(text="Part 2.")], model="sonnet"),
            ResultMessage(
                subtype="result",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="s1",
            ),
        ]

        async def mock_query(*, prompt, options):  # noqa: ARG001
            for msg in messages:
                yield msg

        runner = CliRunner()
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-key"}),
            patch("silly_scripts.cli.ask_claude.query", side_effect=mock_query),
        ):
            get_settings.cache_clear()
            result = runner.invoke(main, ["test"])

        assert result.exit_code == 0
        assert "Part 1." in result.output
        assert "Part 2." in result.output

    def test_json_mode_via_cli(self) -> None:
        """--json flag produces valid NDJSON output via CLI."""
        messages = _make_success_messages("JSON test")

        async def mock_query(*, prompt, options):  # noqa: ARG001
            for msg in messages:
                yield msg

        runner = CliRunner()
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-key"}),
            patch("silly_scripts.cli.ask_claude.query", side_effect=mock_query),
        ):
            get_settings.cache_clear()
            result = runner.invoke(main, ["test", "--json"])

        assert result.exit_code == 0
        lines = [line for line in result.output.strip().split("\n") if line]
        assert len(lines) == 2
        # First line: AssistantMessage
        first = json.loads(lines[0])
        assert first["content"][0]["text"] == "JSON test"
        # Second line: ResultMessage
        second = json.loads(lines[1])
        assert second["subtype"] == "result"

    def test_verbose_shows_tool_calls(self) -> None:
        """--verbose flag shows tool calls on stderr (verified via capsys)."""
        messages = [
            AssistantMessage(
                content=[
                    TextBlock(text="Searching..."),
                    ToolUseBlock(id="t1", name="Grep", input={"pattern": "TODO"}),
                ],
                model="sonnet",
            ),
            ResultMessage(
                subtype="result",
                duration_ms=100,
                duration_api_ms=80,
                is_error=False,
                num_turns=1,
                session_id="s1",
            ),
        ]

        async def mock_query(*, prompt, options):  # noqa: ARG001
            for msg in messages:
                yield msg

        runner = CliRunner()
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-key"}),
            patch("silly_scripts.cli.ask_claude.query", side_effect=mock_query),
        ):
            get_settings.cache_clear()
            result = runner.invoke(main, ["test", "--verbose"])

        assert result.exit_code == 0
        assert "Searching..." in result.output
        # Tool call output goes to stderr via click.echo(err=True),
        # which CliRunner captures in output when mix_stderr is not available
        assert "[tool:Grep]" in result.output

    def test_error_result_exits_nonzero_via_cli(self) -> None:
        """ResultMessage with is_error=True produces non-zero exit via CLI."""
        messages = [
            AssistantMessage(content=[TextBlock(text="Oops")], model="sonnet"),
            ResultMessage(
                subtype="result",
                duration_ms=50,
                duration_api_ms=40,
                is_error=True,
                num_turns=1,
                session_id="err-session",
            ),
        ]

        async def mock_query(*, prompt, options):  # noqa: ARG001
            for msg in messages:
                yield msg

        runner = CliRunner()
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-key"}),
            patch("silly_scripts.cli.ask_claude.query", side_effect=mock_query),
        ):
            get_settings.cache_clear()
            result = runner.invoke(main, ["test"])

        assert result.exit_code != 0
        assert "error" in result.output.lower()

    def test_very_long_prompt_via_cli(self) -> None:
        """Very long prompt is accepted and forwarded via CLI."""
        long_prompt = "z" * 50_000
        captured_prompt = {}

        async def mock_query(*, prompt, options):  # noqa: ARG001
            captured_prompt["value"] = prompt
            for msg in _make_result_only():
                yield msg

        runner = CliRunner()
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-key"}),
            patch("silly_scripts.cli.ask_claude.query", side_effect=mock_query),
        ):
            get_settings.cache_clear()
            result = runner.invoke(main, [long_prompt])

        assert result.exit_code == 0
        assert len(captured_prompt["value"]) == 50_000


# ---------------------------------------------------------------------------
# Exit code summary tests
# ---------------------------------------------------------------------------


class TestExitCodes:
    """Comprehensive exit code verification."""

    def test_success_exit_code_zero(self) -> None:
        """Successful execution exits with code 0."""
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
            result = runner.invoke(main, ["test"])

        assert result.exit_code == 0

    def test_usage_error_exit_code_two(self) -> None:
        """Click usage errors (like invalid option) exit with code 2."""
        runner = CliRunner()
        result = runner.invoke(main, ["--nonexistent-option"])
        assert result.exit_code == 2

    def test_click_exception_exit_code_one(self) -> None:
        """ClickException (missing API key) exits with code 1."""
        runner = CliRunner()
        with patch.dict("os.environ", {}, clear=True):
            get_settings.cache_clear()
            result = runner.invoke(main, ["test prompt"], catch_exceptions=False)
        assert result.exit_code == 1

    def test_keyboard_interrupt_exit_code_130(self) -> None:
        """KeyboardInterrupt exits with POSIX-conventional code 130."""

        async def mock_query(*, prompt, options):  # noqa: ARG001
            raise KeyboardInterrupt
            yield  # make it an async generator  # pragma: no cover

        runner = CliRunner()
        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-key"}),
            patch("silly_scripts.cli.ask_claude.query", side_effect=mock_query),
        ):
            get_settings.cache_clear()
            result = runner.invoke(main, ["test"])

        assert result.exit_code == 130
