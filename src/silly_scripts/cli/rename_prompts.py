"""Rename prompt markdown files by prefixing them with the feature code from their first line."""

import logging
import re
from pathlib import Path

import click


logger = logging.getLogger(__name__)

FEATURE_RE = re.compile(r"^#\s+(F\d+)\.S")


def extract_feature_code(file_path: Path) -> str | None:
    """Extract the feature code (e.g. 'F7') from the first line of a file.

    Expects the first line to match a pattern like ``# F7.S1 — Internal event bus``.

    Args:
        file_path: Path to the markdown file.

    Returns:
        The feature code string (e.g. 'F7'), or None if not found.
    """
    first_line = file_path.read_text(encoding="utf-8").split("\n", 1)[0]
    match = FEATURE_RE.match(first_line)
    if match:
        return match.group(1)
    return None


def build_new_name(original_name: str, feature_code: str) -> str:
    """Build the new filename by prepending the feature code.

    Args:
        original_name: Original filename like 'S01-event-bus.md'.
        feature_code: Feature code like 'F7'.

    Returns:
        New filename like 'F7-S01-event-bus.md'.
    """
    return f"{feature_code}-{original_name}"


@click.command()
@click.argument(
    "folder",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option("--dry-run", is_flag=True, help="Show renames without performing them.")
def main(folder: Path, *, dry_run: bool) -> None:
    """Rename prompt files by prefixing them with their feature code.

    FOLDER: Directory containing markdown prompt files.

    Scans for files starting with 'S' (e.g. S01-event-bus.md), reads the
    first line to extract the feature code (e.g. F7 from '# F7.S1 — ...'),
    and renames them to F7-S01-event-bus.md.
    """
    logging.basicConfig(level=logging.INFO)

    s_files = sorted(
        f for f in folder.iterdir() if f.name.startswith("S") and f.suffix == ".md"
    )

    if not s_files:
        msg = f"No markdown files starting with 'S' found in {folder}"
        raise click.ClickException(msg)

    renamed = 0
    for file_path in s_files:
        feature_code = extract_feature_code(file_path)
        if feature_code is None:
            logger.warning(f"Skipping {file_path.name}: no feature code found")
            continue

        new_name = build_new_name(file_path.name, feature_code)
        new_path = file_path.parent / new_name

        if dry_run:
            click.echo(f"{file_path.name} -> {new_name}")
        else:
            file_path.rename(new_path)
            logger.info(f"Renamed {file_path.name} -> {new_name}")
        renamed += 1

    click.echo(f"{'Would rename' if dry_run else 'Renamed'} {renamed} files")


if __name__ == "__main__":
    main()  # pragma: no cover
