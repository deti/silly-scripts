"""Tests for the claude_usage CLI command."""

from __future__ import annotations

import asyncio
import contextlib
from types import SimpleNamespace
from unittest.mock import patch

import click
import pytest
from click.testing import CliRunner

from silly_scripts.cli.claude_usage import collect_text, fetch_usage, main


class TestCollectText:
    """Tests for the collect_text helper."""

    def test_returns_empty_for_unknown_message(self) -> None:
        """Verify unknown message types return empty string."""
        message = SimpleNamespace(type="system", subtype="init")
        result = collect_text(message)
        assert result == ""


class TestFetchUsage:
    """Tests for the fetch_usage coroutine."""

    def test_collects_result_messages(self) -> None:
        """Verify fetch_usage collects result text from messages."""
        msg1 = SimpleNamespace(result="Usage line 1")
        msg2 = SimpleNamespace(result="Usage line 2")

        async def fake_query(**_kwargs):
            for m in [msg1, msg2]:
                yield m

        with (
            patch("silly_scripts.cli.claude_usage.query", side_effect=fake_query),
            patch(
                "silly_scripts.cli.claude_usage.collect_text",
                side_effect=["Usage line 1", "Usage line 2"],
            ),
        ):
            result = asyncio.run(fetch_usage())

        assert "Usage line 1" in result
        assert "Usage line 2" in result

    def test_skips_empty_messages(self) -> None:
        """Verify messages with no text content are skipped."""
        msg1 = SimpleNamespace(type="system")
        msg2 = SimpleNamespace(result="The usage data")

        async def fake_query(**_kwargs):
            for m in [msg1, msg2]:
                yield m

        with (
            patch("silly_scripts.cli.claude_usage.query", side_effect=fake_query),
            patch(
                "silly_scripts.cli.claude_usage.collect_text",
                side_effect=["", "The usage data"],
            ),
        ):
            result = asyncio.run(fetch_usage())

        assert result == "The usage data"

    def test_raises_on_sdk_error(self) -> None:
        """Verify SDK errors are wrapped in ClickException."""

        async def fake_query(**_kwargs):
            raise ConnectionError
            yield

        with (
            patch("silly_scripts.cli.claude_usage.query", side_effect=fake_query),
            pytest.raises(click.ClickException, match="Failed to fetch usage"),
        ):
            asyncio.run(fetch_usage())

    def test_raises_on_empty_response(self) -> None:
        """Verify empty response raises ClickException."""

        async def fake_query(**_kwargs):
            return
            yield

        with (
            patch("silly_scripts.cli.claude_usage.query", side_effect=fake_query),
            pytest.raises(click.ClickException, match="No usage information"),
        ):
            asyncio.run(fetch_usage())

    def test_passes_correct_prompt(self) -> None:
        """Verify /usage is sent as the prompt."""
        captured_kwargs: dict = {}

        async def fake_query(**kwargs):
            captured_kwargs.update(kwargs)
            return
            yield

        with (
            patch("silly_scripts.cli.claude_usage.query", side_effect=fake_query),
            contextlib.suppress(click.ClickException),
        ):
            asyncio.run(fetch_usage())

        assert captured_kwargs["prompt"] == "/usage"

    def test_passes_max_turns_option(self) -> None:
        """Verify max_turns=1 is set in options."""
        captured_kwargs: dict = {}

        async def fake_query(**kwargs):
            captured_kwargs.update(kwargs)
            return
            yield

        with (
            patch("silly_scripts.cli.claude_usage.query", side_effect=fake_query),
            contextlib.suppress(click.ClickException),
        ):
            asyncio.run(fetch_usage())

        assert captured_kwargs["options"].max_turns == 1


class TestMainCli:
    """Tests for the Click CLI entry point."""

    def test_success_path(self) -> None:
        """Verify successful usage fetch prints results."""

        async def fake_query(**_kwargs):
            yield SimpleNamespace(result="Total tokens used: 1234")

        runner = CliRunner()
        with (
            patch("silly_scripts.cli.claude_usage.query", side_effect=fake_query),
            patch(
                "silly_scripts.cli.claude_usage.collect_text",
                return_value="Total tokens used: 1234",
            ),
        ):
            result = runner.invoke(main)

        assert result.exit_code == 0
        assert "Total tokens used: 1234" in result.output

    def test_sdk_error_shows_message(self) -> None:
        """Verify SDK connection errors display user-friendly message."""

        async def fake_query(**_kwargs):
            raise ConnectionError
            yield

        runner = CliRunner()
        with patch("silly_scripts.cli.claude_usage.query", side_effect=fake_query):
            result = runner.invoke(main)

        assert result.exit_code != 0
        assert "Failed to fetch usage information" in result.output

    def test_empty_response_shows_message(self) -> None:
        """Verify empty response displays user-friendly message."""

        async def fake_query(**_kwargs):
            return
            yield

        runner = CliRunner()
        with patch("silly_scripts.cli.claude_usage.query", side_effect=fake_query):
            result = runner.invoke(main)

        assert result.exit_code != 0
        assert "No usage information returned" in result.output
