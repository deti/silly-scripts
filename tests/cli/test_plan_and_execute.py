"""Tests for the plan-and-execute CLI command."""

from unittest.mock import MagicMock, patch

import click
import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock
from click.testing import CliRunner

from silly_scripts.cli.plan_and_execute import (
    EXECUTION_TOOLS,
    collect_text,
    main,
    plan_and_execute,
    run_execute_phase,
    run_plan_phase,
)


class TestCollectText:
    """Tests for the collect_text helper."""

    def test_collect_text_from_assistant_message(self) -> None:
        """Extracts text from AssistantMessage content blocks."""
        block = MagicMock(spec=TextBlock)
        block.text = "hello world"
        msg = MagicMock(spec=AssistantMessage)
        msg.content = [block]

        assert collect_text(msg) == "hello world"

    def test_collect_text_from_result_message(self) -> None:
        """Extracts text from ResultMessage result field."""
        msg = MagicMock(spec=ResultMessage)
        msg.result = "final result"

        assert collect_text(msg) == "final result"

    def test_collect_text_from_unknown_message(self) -> None:
        """Returns empty string for unknown message types."""
        assert collect_text("not a message") == ""

    def test_collect_text_result_message_no_result(self) -> None:
        """Returns empty string when ResultMessage has no result."""
        msg = MagicMock(spec=ResultMessage)
        msg.result = None

        assert collect_text(msg) == ""


class TestRunPlanPhase:
    """Tests for the plan phase."""

    @pytest.mark.asyncio
    async def test_plan_phase_returns_session_id(self) -> None:
        """Returns session ID from a successful plan phase."""
        result_msg = MagicMock(spec=ResultMessage)
        result_msg.session_id = "session-abc"
        result_msg.result = "Plan created"

        async def mock_query(**_kwargs):
            yield result_msg

        with patch("silly_scripts.cli.plan_and_execute.query", mock_query):
            session_id = await run_plan_phase("test prompt")

        assert session_id == "session-abc"

    @pytest.mark.asyncio
    async def test_plan_phase_no_session_id_raises(self) -> None:
        """Raises ClickException when no session ID is returned."""
        block = MagicMock(spec=TextBlock)
        block.text = "some text"
        msg = MagicMock(spec=AssistantMessage)
        msg.content = [block]

        async def mock_query(**_kwargs):
            yield msg

        with (
            patch("silly_scripts.cli.plan_and_execute.query", mock_query),
            pytest.raises(click.ClickException, match="did not return a session ID"),
        ):
            await run_plan_phase("test prompt")

    @pytest.mark.asyncio
    async def test_plan_phase_exception_raises(self) -> None:
        """Raises ClickException when query fails."""

        async def mock_query(**_kwargs):
            raise RuntimeError("fail")
            yield

        with (
            patch("silly_scripts.cli.plan_and_execute.query", mock_query),
            pytest.raises(click.ClickException, match="Plan phase failed"),
        ):
            await run_plan_phase("test prompt")


class TestRunExecutePhase:
    """Tests for the execution phase."""

    @pytest.mark.asyncio
    async def test_execute_phase_success(self) -> None:
        """Completes without error on successful execution."""
        result_msg = MagicMock(spec=ResultMessage)
        result_msg.result = "Executed"
        result_msg.subtype = "success"

        async def mock_query(**kwargs):
            assert kwargs["options"].resume == "session-abc"
            assert kwargs["options"].permission_mode == "bypassPermissions"
            assert kwargs["options"].allowed_tools == EXECUTION_TOOLS
            yield result_msg

        with patch("silly_scripts.cli.plan_and_execute.query", mock_query):
            await run_execute_phase("session-abc")

    @pytest.mark.asyncio
    async def test_execute_phase_exception_raises(self) -> None:
        """Raises ClickException when execution query fails."""

        async def mock_query(**_kwargs):
            raise RuntimeError("fail")
            yield

        with (
            patch("silly_scripts.cli.plan_and_execute.query", mock_query),
            pytest.raises(click.ClickException, match="Execution phase failed"),
        ):
            await run_execute_phase("session-abc")


class TestPlanAndExecute:
    """Tests for the combined workflow."""

    @pytest.mark.asyncio
    async def test_full_workflow(self) -> None:
        """Runs plan then execute phases in sequence."""
        plan_result = MagicMock(spec=ResultMessage)
        plan_result.session_id = "session-xyz"
        plan_result.result = "Plan done"

        exec_result = MagicMock(spec=ResultMessage)
        exec_result.result = "Executed"
        exec_result.subtype = "success"

        call_count = 0

        async def mock_query(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                assert kwargs["options"].permission_mode == "plan"
                yield plan_result
            else:
                assert kwargs["options"].resume == "session-xyz"
                yield exec_result

        with patch("silly_scripts.cli.plan_and_execute.query", mock_query):
            await plan_and_execute("build something")

        assert call_count == 2


class TestMainCli:
    """Tests for the Click CLI entry point."""

    def test_main_invokes_workflow(self) -> None:
        """CLI invokes plan_and_execute with the prompt argument."""
        runner = CliRunner()

        with patch("silly_scripts.cli.plan_and_execute.asyncio.run") as mock_run:
            result = runner.invoke(main, ["do something cool"])

        assert result.exit_code == 0
        mock_run.assert_called_once()

    def test_main_missing_prompt(self) -> None:
        """CLI fails when no prompt is provided."""
        runner = CliRunner()
        result = runner.invoke(main, [])

        assert result.exit_code != 0
        assert "Missing argument" in result.output
