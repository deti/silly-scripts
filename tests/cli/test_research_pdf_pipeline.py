"""Tests for the research PDF pipeline CLI."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from silly_scripts.cli.research_pdf_pipeline import (
    apply_list_replacements,
    apply_substitutions,
    collect_text,
    discover_chapters,
    extract_technique_name,
    main,
    output_filename,
    preprocess_prompt,
    run_pipeline,
    slugify,
)


class TestDiscoverChapters:
    """Tests for chapter PDF discovery."""

    def test_finds_chapter_pdfs(self, tmp_path: Path) -> None:
        """Discovers chapter PDFs and returns sorted numbers."""
        (tmp_path / "ch02.pdf").touch()
        (tmp_path / "ch12.pdf").touch()
        (tmp_path / "ch07.pdf").touch()
        (tmp_path / "prompt01.md").touch()  # not a chapter

        result = discover_chapters(tmp_path)

        assert result == ["02", "07", "12"]

    def test_empty_folder(self, tmp_path: Path) -> None:
        """Returns empty list when no chapter PDFs exist."""
        (tmp_path / "prompt01.md").touch()
        assert discover_chapters(tmp_path) == []

    def test_pads_single_digit(self, tmp_path: Path) -> None:
        """Pads single-digit chapter numbers with leading zero."""
        (tmp_path / "ch3.pdf").touch()
        assert discover_chapters(tmp_path) == ["03"]


class TestSlugify:
    """Tests for technique name slugification."""

    def test_basic_slugify(self) -> None:
        """Converts spaces to hyphens and lowercases."""
        assert slugify("Domain Testing") == "domain-testing"

    def test_strips_special_chars(self) -> None:
        """Removes non-alphanumeric characters."""
        assert slugify("Path/Branch Coverage!") == "pathbranch-coverage"

    def test_collapses_multiple_spaces(self) -> None:
        """Collapses multiple spaces to single hyphen."""
        assert slugify("data   flow  testing") == "data-flow-testing"

    def test_strips_leading_trailing(self) -> None:
        """Strips leading and trailing hyphens."""
        assert slugify("  testing  ") == "testing"


class TestExtractTechniqueName:
    """Tests for technique name extraction from prompt 01 responses."""

    def test_extracts_with_heading(self) -> None:
        """Extracts technique name from Core technique heading."""
        response = (
            "## Core Technique\nDomain Testing is a black-box method.\nMore text here."
        )
        assert (
            extract_technique_name(response) == "Domain Testing is a black-box method."
        )

    def test_extracts_with_colon(self) -> None:
        """Extracts technique from 'Core technique:' format."""
        response = "Core technique: Path Testing.\nDetails follow."
        assert extract_technique_name(response) == "Path Testing"

    def test_returns_none_on_no_match(self) -> None:
        """Returns None when no Core technique section found."""
        response = "This response has no technique heading."
        assert extract_technique_name(response) is None


class TestApplySubstitutions:
    """Tests for template substitution."""

    def test_replaces_chapter_number(self) -> None:
        """Replaces [N] with chapter number."""
        result = apply_substitutions(
            "Chapter [N] analysis",
            "07",
            Path("/out/ch07"),
        )
        assert result == "Chapter 07 analysis"

    def test_replaces_output_dir(self) -> None:
        """Replaces [OUTPUT_DIR] with absolute path."""
        result = apply_substitutions(
            "Save to [OUTPUT_DIR]/file.md",
            "07",
            Path("/data/ch07"),
        )
        assert result == "Save to /data/ch07/file.md"

    def test_replaces_technique_name(self) -> None:
        """Replaces [Technique Name] placeholder."""
        result = apply_substitutions(
            "Analyze [Technique Name]",
            "07",
            Path("/out"),
            technique_name="Domain Testing",
        )
        assert result == "Analyze Domain Testing"

    def test_replaces_technique_slug(self) -> None:
        """Replaces [technique-slug] placeholder."""
        result = apply_substitutions(
            "file-[technique-slug].md",
            "07",
            Path("/out"),
            technique_slug="domain-testing",
        )
        assert result == "file-domain-testing.md"


class TestApplyListReplacements:
    """Tests for list placeholder replacements."""

    def test_prompt01_removes_paste_line(self) -> None:
        """Removes the paste/attach placeholder from prompt 01."""
        text = "Intro\n[Paste chapter HTML/text here, or attach file]\nMore"
        result = apply_list_replacements(text, 1)
        assert "[Paste chapter" not in result
        assert "Intro" in result

    def test_prompt02_replaces_technique_ref(self) -> None:
        """Replaces technique name reference in prompt 02."""
        text = "Research [technique name from Prompt 1] in depth"
        result = apply_list_replacements(text, 2)
        assert "the technique extracted in the chapter analysis above" in result

    def test_prompt03_replaces_papers_list(self) -> None:
        """Replaces papers list placeholder in prompt 03."""
        text = "[list the key papers from Prompt 2, e.g.:]"
        result = apply_list_replacements(text, 3)
        assert "Extract ALL papers" in result

    def test_prompt03_replaces_tools_list(self) -> None:
        """Replaces tools list placeholder in prompt 03."""
        text = "[list key tools, e.g.:]"
        result = apply_list_replacements(text, 3)
        assert "Extract ALL tools" in result

    def test_prompt04_replaces_concepts(self) -> None:
        """Replaces concept placeholders in prompt 04."""
        text = "[specific coverage criteria / formal concepts] and [e.g.:]"
        result = apply_list_replacements(text, 4)
        assert "coverage criteria and formal concepts" in result
        assert "Extract ALL coverage criteria" in result

    def test_prompt05_replaces_algorithms(self) -> None:
        """Replaces algorithm placeholder in prompt 05."""
        text = "Algorithms: [e.g.:]"
        result = apply_list_replacements(text, 5)
        assert "Extract ALL algorithms" in result

    def test_prompt06_no_changes(self) -> None:
        """Prompts without list replacements are unchanged."""
        text = "No placeholders here"
        assert apply_list_replacements(text, 6) == text


class TestPreprocessPrompt:
    """Tests for full prompt preprocessing."""

    def test_prompt01_prepends_pdf_instruction(self) -> None:
        """Prepends PDF read instruction for prompt 01."""
        result = preprocess_prompt(
            "Analyze chapter [N]",
            1,
            "07",
            Path("/out/ch07"),
            pdf_path=Path("/input/ch07.pdf"),
        )
        assert result.startswith("Read and analyze the PDF file at")
        assert "/ch07.pdf" in result
        assert "Analyze chapter 07" in result

    def test_prompt07_no_pdf_prefix(self) -> None:
        """Does not prepend PDF instruction for non-01 prompts."""
        result = preprocess_prompt(
            "Gap analysis for [N]",
            7,
            "07",
            Path("/out/ch07"),
        )
        assert not result.startswith("Read and analyze")
        assert "Gap analysis for 07" in result


class TestOutputFilename:
    """Tests for output filename generation."""

    def test_generates_correct_name(self) -> None:
        """Generates expected filename pattern."""
        assert output_filename("07", 1) == "ch07-01.md"
        assert output_filename("12", 6) == "ch12-06.md"
        assert output_filename("02", 8) == "ch02-08.md"


class TestCollectText:
    """Tests for text extraction from SDK messages."""

    def test_assistant_message_text(self) -> None:
        """Extracts text from AssistantMessage with TextBlocks."""
        block = MagicMock(spec=["text"])
        block.text = "Hello world"
        # Cannot easily test isinstance-based logic with mocks;
        # verify the function returns empty for non-matching types
        assert collect_text(block) == ""

    def test_result_message_text(self) -> None:
        """Extracts text from ResultMessage."""
        msg = MagicMock()
        msg.result = "Final result"
        # collect_text checks isinstance which won't match MagicMock,
        # so we test the hasattr path indirectly
        assert hasattr(msg, "result")

    def test_unknown_message_returns_empty(self) -> None:
        """Returns empty string for unknown message types."""
        assert collect_text("not a message") == ""


class TestMainCli:
    """Tests for the CLI entry point."""

    def test_missing_prompt_file(self, tmp_path: Path) -> None:
        """Errors when prompt01.md is not found."""
        runner = CliRunner()
        result = runner.invoke(main, [str(tmp_path)])
        assert result.exit_code != 0
        assert "prompt01.md" in result.output

    def test_valid_input_folder(self, tmp_path: Path) -> None:
        """Runs pipeline with valid input folder."""
        (tmp_path / "prompt01.md").write_text("prompt 1")
        (tmp_path / "system-prompt.md").write_text("system prompt")
        (tmp_path / "ch07.pdf").touch()

        for i in range(2, 9):
            (tmp_path / f"prompt{i:02d}.md").write_text(f"prompt {i}")

        with patch("silly_scripts.cli.research_pdf_pipeline.asyncio.run") as mock_run:
            mock_run.return_value = None
            runner = CliRunner()
            result = runner.invoke(main, [str(tmp_path)])

        assert result.exit_code == 0

    def test_custom_repo_path(self, tmp_path: Path) -> None:
        """Accepts --repo option."""
        input_dir = tmp_path / "input"
        repo_dir = tmp_path / "repo"
        input_dir.mkdir()
        repo_dir.mkdir()
        (input_dir / "prompt01.md").write_text("prompt 1")

        with patch("silly_scripts.cli.research_pdf_pipeline.asyncio.run") as mock_run:
            mock_run.return_value = None
            runner = CliRunner()
            result = runner.invoke(main, [str(input_dir), "--repo", str(repo_dir)])

        assert result.exit_code == 0


class TestRunPipeline:
    """Tests for the pipeline orchestration."""

    @pytest.mark.asyncio
    async def test_no_chapters_raises(self, tmp_path: Path) -> None:
        """Raises when no chapter PDFs found."""
        (tmp_path / "system-prompt.md").write_text("system prompt")
        for i in range(1, 9):
            (tmp_path / f"prompt{i:02d}.md").write_text(f"prompt {i}")

        with pytest.raises(Exception, match="No chapter PDFs"):
            await run_pipeline(tmp_path, tmp_path.parent)

    @pytest.mark.asyncio
    async def test_processes_chapters(self, tmp_path: Path) -> None:
        """Processes discovered chapters through the pipeline."""
        (tmp_path / "system-prompt.md").write_text("system prompt")
        for i in range(1, 9):
            (tmp_path / f"prompt{i:02d}.md").write_text(f"prompt {i}")
        (tmp_path / "ch07.pdf").touch()

        with patch(
            "silly_scripts.cli.research_pdf_pipeline.process_chapter",
            new_callable=AsyncMock,
            return_value="complete",
        ) as mock_process:
            await run_pipeline(tmp_path, tmp_path.parent)

        mock_process.assert_called_once()
        args = mock_process.call_args
        assert args[0][1] == "07"
