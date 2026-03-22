"""Tests for the analyze_pdf CLI command."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import patch


if TYPE_CHECKING:
    from pathlib import Path

from click.testing import CliRunner

from silly_scripts.cli.analyze_pdf import analyze, main


class TestAnalyze:
    """Tests for the analyze coroutine."""

    def test_analyze_collects_results(self, tmp_path: Path) -> None:
        """Verify analyze joins result messages."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")

        messages = [
            SimpleNamespace(result="Summary line 1"),
            SimpleNamespace(result="Summary line 2"),
        ]

        async def fake_query(**_kwargs):
            for m in messages:
                yield m

        with patch("silly_scripts.cli.analyze_pdf.query", side_effect=fake_query):
            result = asyncio.run(analyze(pdf_file, "Summarize this"))

        assert "Summary line 1" in result
        assert "Summary line 2" in result

    def test_analyze_skips_non_result_messages(self, tmp_path: Path) -> None:
        """Verify messages without result attr are ignored."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")

        messages = [
            SimpleNamespace(type="system", subtype="init", session_id="abc"),
            SimpleNamespace(result="The answer"),
        ]

        async def fake_query(**_kwargs):
            for m in messages:
                yield m

        with patch("silly_scripts.cli.analyze_pdf.query", side_effect=fake_query):
            result = asyncio.run(analyze(pdf_file, "Summarize"))

        assert result == "The answer"

    def test_analyze_passes_correct_prompt(self, tmp_path: Path) -> None:
        """Verify the prompt includes the file path and user instruction."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")

        captured_kwargs = {}

        async def fake_query(**kwargs):
            captured_kwargs.update(kwargs)
            return
            yield

        with patch("silly_scripts.cli.analyze_pdf.query", side_effect=fake_query):
            asyncio.run(analyze(pdf_file, "Find tables"))

        assert str(pdf_file.resolve()) in captured_kwargs["prompt"]
        assert "Find tables" in captured_kwargs["prompt"]


class TestMainCli:
    """Tests for the Click CLI entry point."""

    def test_rejects_non_pdf_file(self, tmp_path: Path) -> None:
        """Verify non-PDF files are rejected."""
        txt_file = tmp_path / "notes.txt"
        txt_file.write_text("hello")

        runner = CliRunner()
        result = runner.invoke(main, [str(txt_file)])

        assert result.exit_code != 0
        assert "Expected a PDF file" in result.output

    def test_success_path(self, tmp_path: Path) -> None:
        """Verify successful analysis prints results."""
        pdf_file = tmp_path / "report.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")

        async def fake_query(**_kwargs):
            yield SimpleNamespace(result="PDF analysis complete")

        runner = CliRunner()
        with patch("silly_scripts.cli.analyze_pdf.query", side_effect=fake_query):
            result = runner.invoke(main, [str(pdf_file)])

        assert result.exit_code == 0
        assert "PDF analysis complete" in result.output

    def test_custom_prompt(self, tmp_path: Path) -> None:
        """Verify custom prompt is passed through."""
        pdf_file = tmp_path / "data.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")

        captured = {}

        async def fake_query(**kwargs):
            captured.update(kwargs)
            yield SimpleNamespace(result="done")

        runner = CliRunner()
        with patch("silly_scripts.cli.analyze_pdf.query", side_effect=fake_query):
            result = runner.invoke(
                main, [str(pdf_file), "--prompt", "Extract all tables"]
            )

        assert result.exit_code == 0
        assert "Extract all tables" in captured["prompt"]

    def test_missing_file(self) -> None:
        """Verify missing file is caught by Click."""
        runner = CliRunner()
        result = runner.invoke(main, ["/nonexistent/file.pdf"])

        assert result.exit_code != 0
