"""Tests for the split_video CLI command."""

import json
from unittest.mock import MagicMock, patch

import pytest
from click import ClickException
from click.testing import CliRunner

from silly_scripts.cli.split_video import (
    check_ffmpeg,
    compute_digit_count,
    get_duration,
    main,
    split_video,
)


if __import__("typing").TYPE_CHECKING:
    from pathlib import Path


class TestCheckFfmpeg:
    """Tests for ffmpeg availability check."""

    @patch("silly_scripts.cli.split_video.shutil.which")
    def test_both_available(self, mock_which: MagicMock) -> None:
        """No exception when both tools are found."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        check_ffmpeg()

    @patch("silly_scripts.cli.split_video.shutil.which")
    def test_ffmpeg_missing(self, mock_which: MagicMock) -> None:
        """Raises ClickException when ffmpeg is missing."""
        mock_which.side_effect = (
            lambda name: None if name == "ffmpeg" else "/usr/bin/ffprobe"
        )
        with pytest.raises(Exception, match="ffmpeg"):
            check_ffmpeg()

    @patch("silly_scripts.cli.split_video.shutil.which")
    def test_ffprobe_missing(self, mock_which: MagicMock) -> None:
        """Raises ClickException when ffprobe is missing."""
        mock_which.side_effect = (
            lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None
        )
        with pytest.raises(Exception, match="ffprobe"):
            check_ffmpeg()


class TestGetDuration:
    """Tests for video duration extraction."""

    @patch("silly_scripts.cli.split_video.subprocess.run")
    def test_returns_duration(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Returns duration as float from ffprobe output."""
        probe_output = json.dumps({"format": {"duration": "125.5"}})
        mock_run.return_value = MagicMock(returncode=0, stdout=probe_output, stderr="")
        result = get_duration(tmp_path / "video.mp4")
        assert result == 125.5

    @patch("silly_scripts.cli.split_video.subprocess.run")
    def test_ffprobe_failure(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Raises ClickException on ffprobe error."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        with pytest.raises(Exception, match="Error reading file"):
            get_duration(tmp_path / "video.mp4")

    @patch("silly_scripts.cli.split_video.subprocess.run")
    def test_no_duration_field(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Raises ClickException when duration is missing."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout=json.dumps({"format": {}}), stderr=""
        )
        with pytest.raises(Exception, match="Could not determine"):
            get_duration(tmp_path / "video.mp4")


class TestComputeDigitCount:
    """Tests for digit count computation."""

    def test_single_chunk(self) -> None:
        """Single chunk needs 1 digit."""
        assert compute_digit_count(1) == 1

    def test_nine_chunks(self) -> None:
        """Nine chunks needs 1 digit."""
        assert compute_digit_count(9) == 1

    def test_ten_chunks(self) -> None:
        """Ten chunks needs 2 digits."""
        assert compute_digit_count(10) == 2

    def test_hundred_chunks(self) -> None:
        """Hundred chunks needs 3 digits."""
        assert compute_digit_count(100) == 3

    def test_zero_chunks(self) -> None:
        """Zero chunks returns 1."""
        assert compute_digit_count(0) == 1


class TestSplitVideo:
    """Tests for the video splitting logic."""

    @patch("silly_scripts.cli.split_video.subprocess.run")
    @patch("silly_scripts.cli.split_video.get_duration")
    def test_splits_into_correct_chunks(
        self, mock_duration: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        """Splits a 150s video into 3 chunks of 60s."""
        mock_duration.return_value = 150.0
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        video = tmp_path / "my_video.mp4"
        result = split_video(video, 60)

        assert len(result) == 3
        assert result[0] == tmp_path / "my_video_1.mp4"
        assert result[1] == tmp_path / "my_video_2.mp4"
        assert result[2] == tmp_path / "my_video_3.mp4"
        assert mock_run.call_count == 3

    @patch("silly_scripts.cli.split_video.subprocess.run")
    @patch("silly_scripts.cli.split_video.get_duration")
    def test_uses_correct_ffmpeg_args(
        self, mock_duration: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        """Verifies ffmpeg is called with -c copy (no transcoding)."""
        mock_duration.return_value = 65.0
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        video = tmp_path / "clip.mp4"
        split_video(video, 60)

        first_call = mock_run.call_args_list[0]
        cmd = first_call[0][0]
        assert "-c" in cmd
        assert cmd[cmd.index("-c") + 1] == "copy"
        assert "-ss" in cmd
        assert cmd[cmd.index("-ss") + 1] == "0"
        assert "-t" in cmd
        assert cmd[cmd.index("-t") + 1] == "60"

    @patch("silly_scripts.cli.split_video.subprocess.run")
    @patch("silly_scripts.cli.split_video.get_duration")
    def test_two_digit_suffixes_for_many_chunks(
        self, mock_duration: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        """Uses zero-padded two-digit suffixes when >9 chunks."""
        mock_duration.return_value = 600.0
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        video = tmp_path / "long.mp4"
        result = split_video(video, 60)

        assert len(result) == 10
        assert result[0].name == "long_01.mp4"
        assert result[9].name == "long_10.mp4"

    @patch("silly_scripts.cli.split_video.subprocess.run")
    @patch("silly_scripts.cli.split_video.get_duration")
    def test_ffmpeg_failure_raises(
        self, mock_duration: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        """Raises ClickException when ffmpeg fails on a chunk."""
        mock_duration.return_value = 120.0
        mock_run.return_value = MagicMock(returncode=1, stderr="encoding error")

        with pytest.raises(Exception, match="ffmpeg failed on chunk"):
            split_video(tmp_path / "video.mp4", 60)

    @patch("silly_scripts.cli.split_video.subprocess.run")
    @patch("silly_scripts.cli.split_video.get_duration")
    def test_preserves_file_extension(
        self, mock_duration: MagicMock, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        """Preserves original file extension in output names."""
        mock_duration.return_value = 90.0
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        result = split_video(tmp_path / "clip.mov", 60)

        assert result[0].suffix == ".mov"
        assert result[1].suffix == ".mov"


class TestCli:
    """Integration tests for the Click CLI."""

    @patch("silly_scripts.cli.split_video.split_video")
    @patch("silly_scripts.cli.split_video.check_ffmpeg")
    def test_success_output(
        self, mock_check: MagicMock, mock_split: MagicMock, tmp_path: Path
    ) -> None:
        """CLI prints created chunk paths."""
        video = tmp_path / "test.mp4"
        video.touch()

        mock_split.return_value = [
            tmp_path / "test_1.mp4",
            tmp_path / "test_2.mp4",
        ]

        runner = CliRunner()
        result = runner.invoke(main, [str(video)])

        assert result.exit_code == 0
        assert "Created 2 chunk(s)" in result.output
        assert "test_1.mp4" in result.output
        assert "test_2.mp4" in result.output
        mock_check.assert_called_once()

    @patch("silly_scripts.cli.split_video.split_video")
    @patch("silly_scripts.cli.split_video.check_ffmpeg")
    def test_custom_duration(
        self, mock_check: MagicMock, mock_split: MagicMock, tmp_path: Path
    ) -> None:
        """CLI passes custom duration to split_video."""
        video = tmp_path / "test.mp4"
        video.touch()
        mock_split.return_value = []

        runner = CliRunner()
        runner.invoke(main, [str(video), "--duration", "30"])

        mock_check.assert_called_once()
        mock_split.assert_called_once_with(video, 30)

    def test_missing_file(self) -> None:
        """CLI errors when input file does not exist."""
        runner = CliRunner()
        result = runner.invoke(main, ["/nonexistent/video.mp4"])
        assert result.exit_code != 0

    @patch("silly_scripts.cli.split_video.check_ffmpeg")
    def test_ffmpeg_not_found(self, mock_check: MagicMock, tmp_path: Path) -> None:
        """CLI exits with error when ffmpeg is not found."""
        mock_check.side_effect = ClickException("'ffmpeg' not found.")

        video = tmp_path / "test.mp4"
        video.touch()

        runner = CliRunner()
        result = runner.invoke(main, [str(video)])
        assert result.exit_code != 0
        assert "ffmpeg" in result.output
