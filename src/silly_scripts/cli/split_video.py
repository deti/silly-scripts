"""Split a video into 1-minute chunks for Instagram stories using ffmpeg."""

import json
import logging
import math
import shutil
import subprocess
from pathlib import Path

import click


logger = logging.getLogger(__name__)


def check_ffmpeg() -> None:
    """Verify that ffmpeg and ffprobe are available on PATH.

    Raises:
        click.ClickException: If ffmpeg or ffprobe is not found.
    """
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            msg = f"'{tool}' not found. Please install ffmpeg: https://ffmpeg.org/"
            raise click.ClickException(msg)


def get_duration(input_file: Path) -> float:
    """Get video duration in seconds via ffprobe.

    Args:
        input_file: Path to the video file.

    Returns:
        Duration in seconds.

    Raises:
        click.ClickException: If ffprobe fails or duration cannot be read.
    """
    cmd = [
        "ffprobe",
        "-hide_banner",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        str(input_file),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        msg = f"Error reading file: {result.stderr}"
        raise click.ClickException(msg)

    data = json.loads(result.stdout)
    duration_str = data.get("format", {}).get("duration")
    if duration_str is None:
        msg = "Could not determine video duration."
        raise click.ClickException(msg)

    return float(duration_str)


def compute_digit_count(total_chunks: int) -> int:
    """Compute the number of trailing digits needed for chunk numbering.

    Args:
        total_chunks: Total number of chunks.

    Returns:
        Number of digits to use in the suffix.
    """
    if total_chunks <= 0:
        return 1
    return max(1, len(str(total_chunks)))


def split_video(
    input_file: Path,
    chunk_duration: int,
) -> list[Path]:
    """Split a video into chunks without re-encoding.

    Args:
        input_file: Path to the input video file.
        chunk_duration: Duration of each chunk in seconds.

    Returns:
        List of paths to the created chunk files.

    Raises:
        click.ClickException: If ffmpeg fails.
    """
    duration = get_duration(input_file)
    total_chunks = math.ceil(duration / chunk_duration)
    digits = compute_digit_count(total_chunks)

    logger.info(
        f"Video duration: {duration:.1f}s -> {total_chunks} chunk(s) "
        f"of {chunk_duration}s, using {digits} digit(s) in suffix"
    )

    stem = input_file.stem
    suffix = input_file.suffix
    parent = input_file.parent
    output_files: list[Path] = []

    for i in range(1, total_chunks + 1):
        start = (i - 1) * chunk_duration
        output_path = parent / f"{stem}_{i:0{digits}d}{suffix}"

        cmd = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-v",
            "error",
            "-i",
            str(input_file),
            "-ss",
            str(start),
            "-t",
            str(chunk_duration),
            "-c",
            "copy",
            "-avoid_negative_ts",
            "make_zero",
            str(output_path),
        ]

        logger.info(f"Chunk {i}/{total_chunks}: {output_path.name}")
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            msg = f"ffmpeg failed on chunk {i}: {result.stderr}"
            raise click.ClickException(msg)

        output_files.append(output_path)

    return output_files


@click.command()
@click.argument("input_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--duration",
    type=int,
    default=60,
    show_default=True,
    help="Duration of each chunk in seconds.",
)
def main(input_path: Path, duration: int) -> None:
    """Split a video into chunks for Instagram stories.

    INPUT_PATH: Path to the input video file.

    Splits the video into segments (default 60 seconds each) without
    re-encoding. Output files are saved next to the original with
    numbered suffixes (_1, _2, ...).
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    check_ffmpeg()
    output_files = split_video(input_path, duration)
    click.echo(f"Created {len(output_files)} chunk(s):")
    for f in output_files:
        click.echo(f"  {f}")


if __name__ == "__main__":
    main()  # pragma: no cover
