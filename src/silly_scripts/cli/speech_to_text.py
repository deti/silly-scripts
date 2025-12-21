"""CLI command for speech-to-text transcription using Deepgram."""

import sys
from pathlib import Path

import click
from deepgram import DeepgramClient

from silly_scripts.settings import get_settings


def transcribe_audio(audio_file_path: Path, api_key: str) -> str:
    """Transcribe audio file using Deepgram API.

    Args:
        audio_file_path: Path to the audio file to transcribe
        api_key: Deepgram API key

    Returns:
        Transcribed text

    Raises:
        FileNotFoundError: If audio file doesn't exist
        Exception: If transcription fails
    """
    if not audio_file_path.exists():
        msg = f"Audio file not found: {audio_file_path}"
        raise FileNotFoundError(msg)

    if not api_key:
        msg = "Deepgram API key is required. Set DEEPGRAM_API_KEY environment variable."
        raise ValueError(msg)

    # Initialize Deepgram client
    deepgram = DeepgramClient(api_key=api_key)

    # Read audio file
    with audio_file_path.open("rb") as audio_file:
        response = deepgram.listen.v1.media.transcribe_file(
            request=audio_file.read(),
            model="nova-3",
            smart_format=True,
            punctuate=True,
            diarize=True,
            detect_language=True,
        )

    # Extract transcript text with speaker information
    channel = response.results.channels[0]
    alternative = channel.alternatives[0]

    # If diarization is enabled and words are available, format with speakers
    if (
        hasattr(alternative, "words")
        and alternative.words
        and len(alternative.words) > 0
    ):
        formatted_transcript = ""
        current_speaker = None
        current_text = ""

        for word in alternative.words:
            word_speaker = getattr(word, "speaker", 0)

            if current_speaker is None:
                current_speaker = word_speaker
                current_text = word.punctuated_word
            elif current_speaker == word_speaker:
                current_text += " " + word.punctuated_word
            else:
                # New speaker, add previous speaker's text
                formatted_transcript += f"Speaker {current_speaker}: {current_text}\n\n"
                current_speaker = word_speaker
                current_text = word.punctuated_word

        # Add final speaker's text
        if current_text:
            formatted_transcript += f"Speaker {current_speaker}: {current_text}\n"

        return formatted_transcript.strip()
    # Fallback to basic transcript if diarization data not available
    return alternative.transcript


def save_transcript(transcript: str, output_path: Path) -> None:
    """Save transcript to text file.

    Args:
        transcript: Transcribed text to save
        output_path: Path where to save the transcript
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        f.write(transcript)


@click.command()
@click.argument("audio_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output file path. If not specified, will use input filename with _text.txt suffix.",
)
def main(audio_file: Path, output: Path | None) -> None:
    """Transcribe audio file to text using Deepgram.

    AUDIO_FILE: Path to the audio file to transcribe
    """
    try:
        # Determine output file path
        if output is None:
            # Use same directory and name as input file, with _text.txt suffix
            output = audio_file.parent / f"{audio_file.stem}_text.txt"

        # Get API key from settings
        settings = get_settings()
        api_key = settings.deepgram_api_key
        if not api_key:
            click.echo(
                "Error: Deepgram API key not found. Please set DEEPGRAM_API_KEY environment variable.",
                err=True,
            )
            sys.exit(1)

        # Transcribe audio
        click.echo(f"Transcribing audio file: {audio_file}")
        transcript = transcribe_audio(audio_file, api_key)

        # Save transcript
        click.echo(f"Saving transcript to: {output}")
        save_transcript(transcript, output)

        click.echo("Transcription completed successfully!")
        click.echo(f"Transcript saved to: {output}")

    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error during transcription: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
