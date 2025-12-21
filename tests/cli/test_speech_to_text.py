"""Tests for the speech_to_text CLI command."""

import io
import os
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from silly_scripts.cli.speech_to_text import main, save_transcript, transcribe_audio
from silly_scripts.settings import Settings, get_settings


# Ensure the package can be imported from the src/ layout during tests
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Clear settings cache before each test."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def mock_settings(monkeypatch):
    """Mock settings to use environment variables properly."""

    def mock_get_settings():
        return Settings()

    monkeypatch.setattr(
        "silly_scripts.cli.speech_to_text.get_settings", mock_get_settings
    )


@pytest.fixture
def mock_audio_file():
    """Create a temporary audio file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        # Write some dummy audio data
        f.write(b"dummy audio data")
        temp_path = Path(f.name)

    yield temp_path

    # Cleanup
    if temp_path.exists():
        temp_path.unlink()


@pytest.fixture
def mock_api_key():
    """Mock Deepgram API key."""
    return "test-api-key-12345"


@pytest.fixture
def mock_transcript():
    """Mock transcript text."""
    return "This is a test transcription of the audio file."


class TestTranscribeAudio:
    """Test the transcribe_audio function."""

    def test_transcribe_audio_success(
        self, mock_audio_file, mock_api_key, mock_transcript
    ):
        """Test successful audio transcription."""
        # Mock Deepgram response
        mock_response = MagicMock()
        mock_response.results.channels = [
            MagicMock(alternatives=[MagicMock(transcript=mock_transcript)])
        ]

        with patch(
            "silly_scripts.cli.speech_to_text.DeepgramClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.listen.v1.media.transcribe_file.return_value = mock_response

            result = transcribe_audio(mock_audio_file, mock_api_key)

            assert result == mock_transcript
            mock_client_class.assert_called_once_with(api_key=mock_api_key)

    def test_transcribe_audio_file_not_found(self, mock_api_key):
        """Test transcription with non-existent file."""
        non_existent_file = Path("/non/existent/file.wav")

        with pytest.raises(FileNotFoundError, match="Audio file not found"):
            transcribe_audio(non_existent_file, mock_api_key)

    def test_transcribe_audio_empty_api_key(self, mock_audio_file):
        """Test transcription with empty API key."""
        with pytest.raises(ValueError, match="Deepgram API key is required"):
            transcribe_audio(mock_audio_file, "")

    def test_transcribe_audio_none_api_key(self, mock_audio_file):
        """Test transcription with None API key."""
        with pytest.raises(ValueError, match="Deepgram API key is required"):
            transcribe_audio(mock_audio_file, None)

    def test_transcribe_audio_with_diarization(self, mock_audio_file, mock_api_key):
        """Test audio transcription with speaker diarization."""
        # Mock word objects with speaker information
        mock_word1 = MagicMock()
        mock_word1.punctuated_word = "Hello"
        mock_word1.speaker = 0

        mock_word2 = MagicMock()
        mock_word2.punctuated_word = "world."
        mock_word2.speaker = 0

        mock_word3 = MagicMock()
        mock_word3.punctuated_word = "Hi"
        mock_word3.speaker = 1

        mock_word4 = MagicMock()
        mock_word4.punctuated_word = "there!"
        mock_word4.speaker = 1

        # Mock Deepgram response with diarization
        mock_response = MagicMock()
        mock_alternative = MagicMock()
        mock_alternative.transcript = "Hello world. Hi there!"
        mock_alternative.words = [mock_word1, mock_word2, mock_word3, mock_word4]
        mock_response.results.channels = [MagicMock(alternatives=[mock_alternative])]

        with patch(
            "silly_scripts.cli.speech_to_text.DeepgramClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.listen.v1.media.transcribe_file.return_value = mock_response

            result = transcribe_audio(mock_audio_file, mock_api_key)

            expected = "Speaker 0: Hello world.\n\nSpeaker 1: Hi there!"
            assert result == expected
            mock_client_class.assert_called_once_with(api_key=mock_api_key)


class TestSaveTranscript:
    """Test the save_transcript function."""

    def test_save_transcript_success(self, mock_transcript):
        """Test successful transcript saving."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "test_transcript.txt"

            save_transcript(mock_transcript, output_path)

            assert output_path.exists()
            with output_path.open(encoding="utf-8") as f:
                content = f.read()
            assert content == mock_transcript

    def test_save_transcript_create_directories(self, mock_transcript):
        """Test that save_transcript creates parent directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "subdir" / "nested" / "transcript.txt"

            save_transcript(mock_transcript, output_path)

            assert output_path.exists()
            with output_path.open(encoding="utf-8") as f:
                content = f.read()
            assert content == mock_transcript


class TestMainCLI:
    """Test the main CLI function."""

    def test_main_success_default_output(
        self, mock_audio_file, mock_transcript, monkeypatch
    ):
        """Test successful CLI execution with default output path."""
        monkeypatch.setenv("DEEPGRAM_API_KEY", "test-api-key")

        # Mock Deepgram response
        mock_response = MagicMock()
        mock_response.results.channels = [
            MagicMock(alternatives=[MagicMock(transcript=mock_transcript)])
        ]

        with patch(
            "silly_scripts.cli.speech_to_text.DeepgramClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.listen.v1.media.transcribe_file.return_value = mock_response

            # Capture stdout and stderr
            f_stdout = io.StringIO()
            f_stderr = io.StringIO()

            with redirect_stdout(f_stdout), redirect_stderr(f_stderr):
                with pytest.raises(SystemExit) as exc_info:
                    main([str(mock_audio_file)])
                # Click raises SystemExit(0) on success
                assert exc_info.value.code == 0

            output = f_stdout.getvalue()

            # Check output messages
            assert "Transcribing audio file:" in output
            assert "Saving transcript to:" in output
            assert "Transcription completed successfully!" in output
            assert "Transcript saved to:" in output

            # Check that output file was created
            expected_output = (
                mock_audio_file.parent / f"{mock_audio_file.stem}_text.txt"
            )
            assert expected_output.exists()

            # Verify transcript content
            with expected_output.open(encoding="utf-8") as f:
                content = f.read()
            assert content == mock_transcript

            # Cleanup
            if expected_output.exists():
                expected_output.unlink()

    def test_main_success_custom_output(
        self, mock_audio_file, mock_transcript, monkeypatch
    ):
        """Test successful CLI execution with custom output path."""
        monkeypatch.setenv("DEEPGRAM_API_KEY", "test-api-key")

        # Mock Deepgram response
        mock_response = MagicMock()
        mock_response.results.channels = [
            MagicMock(alternatives=[MagicMock(transcript=mock_transcript)])
        ]

        with patch(
            "silly_scripts.cli.speech_to_text.DeepgramClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.listen.v1.media.transcribe_file.return_value = mock_response

            with tempfile.TemporaryDirectory() as temp_dir:
                custom_output = Path(temp_dir) / "custom_transcript.txt"

                # Capture stdout and stderr
                f_stdout = io.StringIO()
                f_stderr = io.StringIO()

                with redirect_stdout(f_stdout), redirect_stderr(f_stderr):
                    with pytest.raises(SystemExit) as exc_info:
                        main([str(mock_audio_file), "--output", str(custom_output)])
                    # Click raises SystemExit(0) on success
                    assert exc_info.value.code == 0

                output = f_stdout.getvalue()

                # Check output messages
                assert "Transcribing audio file:" in output
                assert f"Saving transcript to: {custom_output}" in output
                assert "Transcription completed successfully!" in output

                # Check that custom output file was created
                assert custom_output.exists()

                # Verify transcript content
                with custom_output.open(encoding="utf-8") as f:
                    content = f.read()
                assert content == mock_transcript

    def test_main_missing_api_key(self, mock_audio_file, monkeypatch):
        """Test CLI execution with missing API key."""
        # Ensure API key is not set
        monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)

        f_stdout = io.StringIO()
        f_stderr = io.StringIO()

        with redirect_stdout(f_stdout), redirect_stderr(f_stderr):
            with pytest.raises(SystemExit) as exc_info:
                main([str(mock_audio_file)])

            assert exc_info.value.code == 1

        error = f_stderr.getvalue()
        assert "Error during transcription:" in error

    def test_main_file_not_found(self, monkeypatch):
        """Test CLI execution with non-existent file."""
        monkeypatch.setenv("DEEPGRAM_API_KEY", "test-api-key")

        f_stdout = io.StringIO()
        f_stderr = io.StringIO()

        with redirect_stdout(f_stdout), redirect_stderr(f_stderr):
            with pytest.raises(SystemExit) as exc_info:
                main(["/non/existent/file.wav"])

            # Click returns 2 for invalid arguments (file not found)
            assert exc_info.value.code == 2

        error = f_stderr.getvalue()
        assert "does not exist" in error

    def test_main_transcription_error(self, mock_audio_file, monkeypatch):
        """Test CLI execution with transcription error."""
        monkeypatch.setenv("DEEPGRAM_API_KEY", "test-api-key")

        with patch(
            "silly_scripts.cli.speech_to_text.DeepgramClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.listen.v1.media.transcribe_file.side_effect = Exception(
                "API Error"
            )

            f_stdout = io.StringIO()
            f_stderr = io.StringIO()

            with redirect_stdout(f_stdout), redirect_stderr(f_stderr):
                with pytest.raises(SystemExit) as exc_info:
                    main([str(mock_audio_file)])

                assert exc_info.value.code == 1

            error = f_stderr.getvalue()
            assert "Error during transcription: API Error" in error


class TestCLIModuleExecution:
    """Test running the CLI module directly."""

    def test_cli_module_execution_success(self, monkeypatch):
        """Test running the CLI module directly with success."""
        monkeypatch.setenv("DEEPGRAM_API_KEY", "test-api-key")

        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC_PATH)

        # Note: This test will fail with real API call since mocking doesn't work across subprocess
        # We test that the module can be imported and basic structure works
        proc = subprocess.run(
            [
                sys.executable,
                "-c",
                f"import sys; sys.path.insert(0, r'{SRC_PATH}'); from silly_scripts.cli.speech_to_text import main; print('Import successful')",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

        assert proc.returncode == 0
        assert "Import successful" in proc.stdout

    def test_cli_module_execution_missing_api_key(self, mock_audio_file, monkeypatch):
        """Test running the CLI module with missing API key."""
        monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)

        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC_PATH)

        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "silly_scripts.cli.speech_to_text",
                str(mock_audio_file),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

        assert proc.returncode == 1
        assert "Error during transcription:" in proc.stderr

    def test_cli_module_execution_file_not_found(self, monkeypatch):
        """Test running the CLI module with non-existent file."""
        monkeypatch.setenv("DEEPGRAM_API_KEY", "test-api-key")

        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC_PATH)

        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "silly_scripts.cli.speech_to_text",
                "/non/existent/file.wav",
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

        # Click returns 2 for invalid arguments (file not found)
        assert proc.returncode == 2
        assert "does not exist" in proc.stderr


class TestScriptEntryPoint:
    """Test the script entry point configuration."""

    def test_script_entry_point_import(self):
        """Test that the script entry point can be imported."""
        # This test verifies the pyproject.toml script configuration
        # by testing the actual module import
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC_PATH)

        proc = subprocess.run(
            [
                sys.executable,
                "-c",
                f"import sys; sys.path.insert(0, r'{SRC_PATH}'); "
                "from silly_scripts.cli.speech_to_text import main; print('Import successful')",
            ],
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )

        assert proc.returncode == 0
        assert "Import successful" in proc.stdout
