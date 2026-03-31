"""Tests for the claude_commands CLI command."""

from __future__ import annotations

import asyncio
import contextlib
from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner

from silly_scripts.cli.claude_commands import fetch_commands, main


def _make_init_message(slash_commands: list[str]) -> MagicMock:
    """Create a fake SystemMessage with subtype 'init'."""
    msg = MagicMock()
    msg.subtype = "init"
    msg.data = {"slash_commands": slash_commands}
    return msg


def _make_other_message() -> MagicMock:
    """Create a fake non-SystemMessage."""
    msg = MagicMock()
    msg.subtype = "other"
    return msg


class TestFetchCommands:
    """Tests for the fetch_commands coroutine."""

    def test_extracts_slash_commands_from_init(self) -> None:
        """Verify fetch_commands returns slash commands from the init message."""
        init_msg = _make_init_message(["/help", "/clear", "/commit"])

        async def fake_query(**_kwargs):
            yield init_msg

        with (
            patch("silly_scripts.cli.claude_commands.query", side_effect=fake_query),
            patch("silly_scripts.cli.claude_commands.SystemMessage", type(init_msg)),
        ):
            result = asyncio.run(fetch_commands())

        assert result == ["/help", "/clear", "/commit"]

    def test_returns_empty_list_when_no_commands(self) -> None:
        """Verify empty slash_commands list is returned correctly."""
        init_msg = _make_init_message([])

        async def fake_query(**_kwargs):
            yield init_msg

        with (
            patch("silly_scripts.cli.claude_commands.query", side_effect=fake_query),
            patch("silly_scripts.cli.claude_commands.SystemMessage", type(init_msg)),
        ):
            result = asyncio.run(fetch_commands())

        assert result == []

    def test_returns_empty_list_when_key_missing(self) -> None:
        """Verify missing slash_commands key defaults to empty list."""
        init_msg = MagicMock()
        init_msg.subtype = "init"
        init_msg.data = {}

        async def fake_query(**_kwargs):
            yield init_msg

        with (
            patch("silly_scripts.cli.claude_commands.query", side_effect=fake_query),
            patch("silly_scripts.cli.claude_commands.SystemMessage", type(init_msg)),
        ):
            result = asyncio.run(fetch_commands())

        assert result == []

    def test_skips_non_init_messages(self) -> None:
        """Verify non-init messages are ignored."""
        other_msg = _make_other_message()
        init_msg = _make_init_message(["/help"])

        async def fake_query(**_kwargs):
            yield other_msg
            yield init_msg

        with (
            patch("silly_scripts.cli.claude_commands.query", side_effect=fake_query),
            patch("silly_scripts.cli.claude_commands.SystemMessage", type(init_msg)),
        ):
            result = asyncio.run(fetch_commands())

        assert result == ["/help"]

    def test_raises_on_sdk_error(self) -> None:
        """Verify SDK errors are wrapped in ClickException."""

        async def fake_query(**_kwargs):
            raise ConnectionError
            yield

        with (
            patch("silly_scripts.cli.claude_commands.query", side_effect=fake_query),
            pytest.raises(
                click.ClickException, match="Failed to fetch available commands"
            ),
        ):
            asyncio.run(fetch_commands())

    def test_raises_when_no_init_message(self) -> None:
        """Verify missing init message raises ClickException."""

        async def fake_query(**_kwargs):
            return
            yield

        with (
            patch("silly_scripts.cli.claude_commands.query", side_effect=fake_query),
            pytest.raises(click.ClickException, match="No init message received"),
        ):
            asyncio.run(fetch_commands())

    def test_passes_max_turns_option(self) -> None:
        """Verify max_turns=1 is set in options."""
        captured_kwargs: dict = {}

        async def fake_query(**kwargs):
            captured_kwargs.update(kwargs)
            return
            yield

        with (
            patch("silly_scripts.cli.claude_commands.query", side_effect=fake_query),
            contextlib.suppress(click.ClickException),
        ):
            asyncio.run(fetch_commands())

        assert captured_kwargs["options"].max_turns == 1


class TestMainCli:
    """Tests for the Click CLI entry point."""

    def test_success_path(self) -> None:
        """Verify successful command fetch prints sorted results."""
        init_msg = _make_init_message(["/commit", "/clear", "/help"])

        async def fake_query(**_kwargs):
            yield init_msg

        runner = CliRunner()
        with (
            patch("silly_scripts.cli.claude_commands.query", side_effect=fake_query),
            patch("silly_scripts.cli.claude_commands.SystemMessage", type(init_msg)),
        ):
            result = runner.invoke(main)

        assert result.exit_code == 0
        assert "/clear" in result.output
        assert "/commit" in result.output
        assert "/help" in result.output
        # Verify sorted order
        lines = [
            line.strip()
            for line in result.output.strip().split("\n")
            if line.startswith("  /")
        ]
        assert lines == sorted(lines)

    def test_empty_commands_shows_message(self) -> None:
        """Verify empty commands list shows appropriate message."""
        init_msg = _make_init_message([])

        async def fake_query(**_kwargs):
            yield init_msg

        runner = CliRunner()
        with (
            patch("silly_scripts.cli.claude_commands.query", side_effect=fake_query),
            patch("silly_scripts.cli.claude_commands.SystemMessage", type(init_msg)),
        ):
            result = runner.invoke(main)

        assert result.exit_code == 0
        assert "No slash commands available" in result.output

    def test_sdk_error_shows_message(self) -> None:
        """Verify SDK connection errors display user-friendly message."""

        async def fake_query(**_kwargs):
            raise ConnectionError
            yield

        runner = CliRunner()
        with patch("silly_scripts.cli.claude_commands.query", side_effect=fake_query):
            result = runner.invoke(main)

        assert result.exit_code != 0
        assert "Failed to fetch available commands" in result.output

    def test_no_init_message_shows_error(self) -> None:
        """Verify missing init message displays user-friendly error."""

        async def fake_query(**_kwargs):
            return
            yield

        runner = CliRunner()
        with patch("silly_scripts.cli.claude_commands.query", side_effect=fake_query):
            result = runner.invoke(main)

        assert result.exit_code != 0
        assert "No init message received" in result.output
