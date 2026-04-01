"""Tests for the fleet-plan-and-execute CLI command."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import click
import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock
from click.testing import CliRunner

from silly_scripts.cli.fleet_plan_and_execute import (
    EXECUTION_TOOLS,
    _build_plugins,
    analyze_plan,
    collect_text,
    fleet_plan_and_execute,
    main,
    run_execute_phase,
    run_fleet_plan_phase,
)

FAKE_PLUGIN_PATH = Path("/fake/fleet/plugin")


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


class TestAnalyzePlan:
    """Tests for the analyze_plan helper."""

    def test_analyze_plan_with_waves_and_tasks(self) -> None:
        """Parses waves, tasks, and steps from plan markdown."""
        plan_text = (
            "## Wave 1\n"
            "### Task 1: Setup\n"
            "- [x] Step one\n"
            "- [ ] Step two\n"
            "## Wave 2\n"
            "### Task 2: Build\n"
            "### Task 3: Test\n"
            "- [ ] Step three\n"
            "- [ ] Step four\n"
        )
        summary = analyze_plan(plan_text)

        assert "Waves: 2" in summary
        assert "Tasks: 3" in summary
        assert "Steps: 4 (1 done, 3 pending)" in summary

    def test_analyze_plan_empty_text(self) -> None:
        """Returns zero counts for empty plan text."""
        summary = analyze_plan("")

        assert "Waves: 0" in summary
        assert "Tasks: 0" in summary
        assert "Steps: 0 (0 done, 0 pending)" in summary

    def test_analyze_plan_all_done(self) -> None:
        """Correctly counts when all steps are completed."""
        plan_text = "- [x] Done one\n- [x] Done two\n"
        summary = analyze_plan(plan_text)

        assert "Steps: 2 (2 done, 0 pending)" in summary


class TestRunFleetPlanPhase:
    """Tests for the fleet plan phase."""

    @pytest.mark.asyncio
    async def test_fleet_plan_returns_session_id_and_text(self) -> None:
        """Returns session ID and plan text from a successful plan phase."""
        block = MagicMock(spec=TextBlock)
        block.text = "## Wave 1\n### Task 1\n- [ ] Step"
        assistant_msg = MagicMock(spec=AssistantMessage)
        assistant_msg.content = [block]

        result_msg = MagicMock(spec=ResultMessage)
        result_msg.session_id = "session-fleet-abc"
        result_msg.result = "Plan created"

        async def mock_query(**kwargs):
            assert "/fleet:fleet-plan create" in kwargs["prompt"]
            assert kwargs["options"].permission_mode == "bypassPermissions"
            yield assistant_msg
            yield result_msg

        with patch("silly_scripts.cli.fleet_plan_and_execute.query", mock_query):
            session_id, plan_text = await run_fleet_plan_phase("build a feature")

        assert session_id == "session-fleet-abc"
        assert "Wave 1" in plan_text

    @pytest.mark.asyncio
    async def test_fleet_plan_no_session_id_raises(self) -> None:
        """Raises ClickException when no session ID is returned."""
        block = MagicMock(spec=TextBlock)
        block.text = "some text"
        msg = MagicMock(spec=AssistantMessage)
        msg.content = [block]

        async def mock_query(**_kwargs):
            yield msg

        with (
            patch("silly_scripts.cli.fleet_plan_and_execute.query", mock_query),
            pytest.raises(click.ClickException, match="did not return a session ID"),
        ):
            await run_fleet_plan_phase("test prompt")

    @pytest.mark.asyncio
    async def test_fleet_plan_exception_raises(self) -> None:
        """Raises ClickException when query fails."""

        async def mock_query(**_kwargs):
            raise RuntimeError("fail")
            yield

        with (
            patch("silly_scripts.cli.fleet_plan_and_execute.query", mock_query),
            pytest.raises(click.ClickException, match="Fleet plan phase failed"),
        ):
            await run_fleet_plan_phase("test prompt")


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
            assert "approved" in kwargs["prompt"].lower()
            yield result_msg

        with patch("silly_scripts.cli.fleet_plan_and_execute.query", mock_query):
            await run_execute_phase("session-abc")

    @pytest.mark.asyncio
    async def test_execute_phase_exception_raises(self) -> None:
        """Raises ClickException when execution query fails."""

        async def mock_query(**_kwargs):
            raise RuntimeError("fail")
            yield

        with (
            patch("silly_scripts.cli.fleet_plan_and_execute.query", mock_query),
            pytest.raises(click.ClickException, match="Execution phase failed"),
        ):
            await run_execute_phase("session-abc")


class TestFleetPlanAndExecute:
    """Tests for the combined workflow."""

    @pytest.mark.asyncio
    async def test_full_workflow(self) -> None:
        """Runs fleet plan then execute phases in sequence."""
        block = MagicMock(spec=TextBlock)
        block.text = "## Wave 1\n### Task 1\n- [ ] Step"
        assistant_msg = MagicMock(spec=AssistantMessage)
        assistant_msg.content = [block]

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
                assert kwargs["options"].permission_mode == "bypassPermissions"
                yield assistant_msg
                yield plan_result
            else:
                assert kwargs["options"].resume == "session-xyz"
                yield exec_result

        with patch("silly_scripts.cli.fleet_plan_and_execute.query", mock_query):
            await fleet_plan_and_execute("build something")

        assert call_count == 2


class TestMainCli:
    """Tests for the Click CLI entry point."""

    def test_main_invokes_workflow(self) -> None:
        """CLI invokes fleet_plan_and_execute with the prompt argument."""
        runner = CliRunner()

        with patch("silly_scripts.cli.fleet_plan_and_execute.asyncio.run") as mock_run:
            result = runner.invoke(main, ["do something cool"])

        assert result.exit_code == 0
        mock_run.assert_called_once()

    def test_main_missing_prompt(self) -> None:
        """CLI fails when no prompt is provided."""
        runner = CliRunner()
        result = runner.invoke(main, [])

        assert result.exit_code != 0
        assert "Missing argument" in result.output
