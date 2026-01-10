import json
import logging
import shlex
import subprocess
from pathlib import Path

import click


logger = logging.getLogger(__name__)


def get_metadata(input_file: Path) -> dict:
    """Run ffprobe and return JSON metadata.

    Args:
        input_file: Path to the input media file.

    Returns:
        JSON metadata as a dictionary.

    Raises:
        click.ClickException: If ffprobe fails.
    """
    cmd = [
        "ffprobe",
        "-hide_banner",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        "-show_chapters",
        str(input_file),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        msg = f"Error reading file: {result.stderr}"
        raise click.ClickException(msg)
    return json.loads(result.stdout)


def sanitize_filename(name: str) -> str:
    """Remove illegal characters for filenames.

    Args:
        name: The filename to sanitize.

    Returns:
        The sanitized filename.
    """
    return "".join(c for c in name if c.isalnum() or c in (" ", ".", "_")).strip()


def process_audiobook(
    input_file: Path, output_folder: Path, cover_file: Path | None = None
) -> None:
    """Split M4B into M4A chapters.

    Args:
        input_file: Path to the input M4B file.
        output_folder: Path to the folder where output M4A files will be saved.
        cover_file: Optional path to a cover image to be embedded.

    Raises:
        click.ClickException: If no chapters are found or ffmpeg fails.
    """
    # Get metadata
    data = get_metadata(input_file)

    # Extract global tags
    format_tags = data.get("format", {}).get("tags", {})
    artist = format_tags.get("artist", "Unknown Artist")
    album = format_tags.get("album", format_tags.get("title", "Unknown Album"))

    chapters = data.get("chapters", [])
    if not chapters:
        msg = "No chapters found in the file."
        raise click.ClickException(msg)

    if not output_folder.exists():
        output_folder.mkdir(parents=True)

    total = len(chapters)

    for i, chapter in enumerate(chapters, start=1):
        start = chapter["start_time"]
        end = chapter["end_time"]
        title = chapter.get("tags", {}).get("title", f"Chapter {i}")

        safe_title = sanitize_filename(title)
        output_filename = f"{i:02d} - {safe_title}.m4a"
        output_path = output_folder / output_filename

        # Build FFmpeg command
        cmd = ["ffmpeg", "-y", "-hide_banner", "-v", "info", "-i", str(input_file)]

        if cover_file:
            cmd += ["-i", str(cover_file)]

        cmd += [
            f"-ss {start}",
            f"-to {end}",
            "-c:a aac",
            "-b:a 384k",
            "-ac 6",
            f"-metadata title={title}",
            f"-metadata album={album}",
            f"-metadata artist={artist}",
            f"-metadata track={i}/{total}",
            "-movflags",
            "+faststart",
        ]

        if cover_file:
            # Map audio from first input, video from second
            cmd += [
                "-map 0:a:0",
                "-map 1:v:0",
                "-disposition:v:0",
                "attached_pic",
            ]
        else:
            cmd += ["-vn"]

        cmd.append(str(output_path))

        # Print debug command (shlex joins arguments correctly for copy-pasting)
        logger.info(f"\n--- Processing Chapter {i}/{total}: {title} ---")
        logger.info(shlex.join(cmd))

        # Execute
        subprocess.run(cmd, check=True)


@click.command()
@click.argument("input_path", type=click.Path(exists=True, path_type=Path))
@click.argument("output_path", type=click.Path(path_type=Path))
@click.option(
    "--cover",
    type=click.Path(exists=True, path_type=Path),
    help="Optional path to cover image",
    default=None,
)
def main(input_path: Path, output_path: Path, cover: Path | None) -> None:
    """Split M4B with EAC3 into 5.1 AAC M4A chapters.

    INPUT_PATH: Path to input M4B file.
    OUTPUT_PATH: Path to output folder.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    process_audiobook(input_path, output_path, cover)


if __name__ == "__main__":
    main()
