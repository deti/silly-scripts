import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click import ClickException
from click.testing import CliRunner

from silly_scripts.cli.m4b_to_m4a import get_metadata, main, sanitize_filename


def test_sanitize_filename():
    assert sanitize_filename("Chapter 1: The Beginning?") == "Chapter 1 The Beginning"
    assert (
        sanitize_filename("File*Name/With:Illegal|Chars") == "FileNameWithIllegalChars"
    )
    assert sanitize_filename("  Trim Space  ") == "Trim Space"


@patch("silly_scripts.cli.m4b_to_m4a.subprocess.run")
def test_get_metadata_success(mock_run):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=json.dumps(
            {"format": {"tags": {"title": "Test Album"}}, "chapters": []}
        ),
        stderr="",
    )

    metadata = get_metadata(Path("test.m4b"))
    assert metadata["format"]["tags"]["title"] == "Test Album"


@patch("silly_scripts.cli.m4b_to_m4a.subprocess.run")
def test_get_metadata_failure(mock_run):
    mock_run.return_value = MagicMock(
        returncode=1,
        stderr="ffprobe error",
    )

    with pytest.raises(ClickException, match="Error reading file: ffprobe error"):
        get_metadata(Path("test.m4b"))


@patch("silly_scripts.cli.m4b_to_m4a.get_metadata")
@patch("silly_scripts.cli.m4b_to_m4a.subprocess.run")
def test_main_success(mock_run, mock_get_metadata, tmp_path):
    input_file = tmp_path / "input.m4b"
    input_file.touch()
    output_dir = tmp_path / "output"

    mock_get_metadata.return_value = {
        "format": {"tags": {"artist": "Test Artist", "album": "Test Album"}},
        "chapters": [
            {
                "start_time": "0",
                "end_time": "10",
                "tags": {"title": "Chapter 1"},
            },
            {
                "start_time": "10",
                "end_time": "20",
                "tags": {"title": "Chapter 2"},
            },
        ],
    }

    runner = CliRunner()
    result = runner.invoke(main, [str(input_file), str(output_dir)])

    assert result.exit_code == 0
    assert output_dir.exists()
    assert mock_run.call_count == 2  # One for each chapter


@patch("silly_scripts.cli.m4b_to_m4a.get_metadata")
def test_main_no_chapters(mock_get_metadata, tmp_path):
    input_file = tmp_path / "input.m4b"
    input_file.touch()
    output_dir = tmp_path / "output"

    mock_get_metadata.return_value = {
        "format": {"tags": {}},
        "chapters": [],
    }

    runner = CliRunner()
    result = runner.invoke(main, [str(input_file), str(output_dir)])

    assert result.exit_code != 0
    assert "No chapters found" in result.output


@patch("silly_scripts.cli.m4b_to_m4a.get_metadata")
@patch("silly_scripts.cli.m4b_to_m4a.subprocess.run")
def test_main_with_cover(mock_run, mock_get_metadata, tmp_path):
    input_file = tmp_path / "input.m4b"
    input_file.touch()
    cover_file = tmp_path / "cover.jpg"
    cover_file.touch()
    output_dir = tmp_path / "output"

    mock_get_metadata.return_value = {
        "format": {"tags": {"artist": "Artist", "album": "Album"}},
        "chapters": [
            {
                "start_time": "0",
                "end_time": "10",
                "tags": {"title": "Chapter 1"},
            }
        ],
    }

    runner = CliRunner()
    result = runner.invoke(
        main, [str(input_file), str(output_dir), "--cover", str(cover_file)]
    )

    assert result.exit_code == 0
    # Check if cover file was included in ffmpeg command
    args, _ = mock_run.call_args
    cmd = args[0]
    assert "-i" in cmd
    assert str(cover_file) in cmd
    assert "attached_pic" in cmd
