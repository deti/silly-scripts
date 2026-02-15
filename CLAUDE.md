# CLAUDE.md

## Project Overview

A collection of standalone CLI utilities ("silly scripts") packaged as a single Python project. Each CLI is a self-contained tool for a specific task (audiobook splitting, EPUB manipulation, speech transcription, etc.), built with Click for CLI parsing and pydantic-settings for configuration. The project uses a src-layout Python package managed by `uv`, with FastAPI providing a minimal API server. Python >=3.14.

## Development Setup

```bash
make init          # Creates venv and installs all deps (uses uv)
```

Or manually:

```bash
uv venv && uv sync
```

Verify the install:

```bash
uv run pytest tests/ -v
```

Configuration uses a `.env` file at the project root. Copy the template to get started:

```bash
cp env.template .env
```

Environment variables are loaded by pydantic-settings with no prefix (e.g., `DEBUG=true`, `LOG_LEVEL=DEBUG`). See `env.template` for available options.

## Architecture

- **`src/silly_scripts/`** — Main package. Contains `settings.py` (pydantic-settings configuration, accessed via cached `get_settings()`) and `main.py` (FastAPI app).
- **`src/silly_scripts/cli/`** — CLI commands. Each file is one standalone Click command with a `main()` entry point, registered in `pyproject.toml` under `[project.scripts]`.
- **`tests/`** — Test suite mirroring the source structure. `tests/cli/` tests CLI commands, `tests/` root tests core modules.
- **`docs/`** — User-facing documentation for individual commands.
- **`changelog/`** — Per-day changelog files (`YYYY-MM-DD.md`) with timestamped entries.

**Dependency direction**: CLI modules import from `silly_scripts.settings` (and occasionally `silly_scripts.main`). CLI modules do not import from each other. Settings is the shared dependency; each CLI is independent.

**Adding a new CLI**: Create a new module in `src/silly_scripts/cli/`, define a `@click.command()` `main()` function, register the entry point in `pyproject.toml` `[project.scripts]`, and create a corresponding test file in `tests/cli/`.

## Code Conventions

- **Imports**: stdlib, then third-party, then local (`from silly_scripts...`). Managed by ruff/isort. Two blank lines after imports. No relative imports.
- **Typing**: Full type hints on all function signatures and return types. Use `X | None` union syntax (not `Optional[X]`). Use `pathlib.Path` for all file paths. Click arguments use `path_type=Path`.
- **Docstrings**: Google-style with `Args:`, `Returns:`, `Raises:` sections on source functions. Test functions get a single-line docstring.
- **Error handling**: CLI-facing errors use `click.ClickException` for user-friendly messages. Internal helpers raise standard Python exceptions.
- **Logging**: `logger = logging.getLogger(__name__)` at module level. `logging.basicConfig()` called in CLI `main()` functions. Uses f-string log messages.
- **CLI structure**: Every CLI module follows this order: module docstring, imports, logger, helper functions, `@click.command()` main, `if __name__ == "__main__": main()` guard (with `# pragma: no cover` comment).
- **Formatting**: Ruff handles all formatting. Line length 88, double quotes, 4-space indent. Full config in `pyproject.toml` `[tool.ruff]`.

## Testing

### Running Tests

```bash
uv run pytest tests/ -v                          # full suite
uv run pytest tests/cli/test_m4b_to_m4a.py -v    # single file
uv run pytest tests/ -v -k "test_sanitize"        # by keyword
```

### Test Conventions

- Tests mirror source: `src/silly_scripts/cli/foo.py` -> `tests/cli/test_foo.py`
- Naming: `test_<what_is_tested>` functions. Test classes (e.g., `TestTranscribeAudio`) group related tests when a module has many.
- **Mocking**: Use `unittest.mock.patch` and `MagicMock` (not pytest-mock). Patch at the usage site: `"silly_scripts.cli.m4b_to_m4a.subprocess.run"`.
- **External calls are always mocked**: subprocess (ffmpeg/ffprobe), API clients (Deepgram), servers (uvicorn). Never make real network calls or run real subprocesses in tests.
- **Settings tests**: Use an `autouse` fixture that calls `get_settings.cache_clear()` before and after each test, since settings are cached with `lru_cache`.
- **CLI testing**: Use `click.testing.CliRunner` for integration tests or call `main.callback()` directly to bypass Click parsing.
- **Async tests**: Use `@pytest.mark.asyncio` with `httpx.AsyncClient` and `ASGITransport` for FastAPI endpoint tests.
- **Temp files**: Prefer pytest's built-in `tmp_path` fixture.

### Writing New Tests

When creating or modifying code, ALWAYS:
1. Write or update tests in the corresponding test file
2. Run the specific test file first: `uv run pytest tests/cli/test_<module>.py -v`
3. Then run the full suite: `uv run pytest tests/ -v`
4. If tests fail, fix them before proceeding

### Test Coverage

```bash
make test-cov
# or
uv run pytest tests/ --cov=src/silly_scripts --cov-report=html --cov-report=term-missing
```

Maintain or improve current coverage. Never submit changes that reduce coverage without justification.

## Linting & Formatting

### Commands

```bash
uv run ruff format src/ tests/             # format
uv run ruff check src/ tests/              # lint (check only)
uv run ruff check --fix src/ tests/        # lint + auto-fix
```

Or all at once:

```bash
make lint    # runs ruff check --fix then ruff format
```

### Workflow

After EVERY code change:
1. Run `uv run ruff check --fix src/ tests/`
2. Run `uv run ruff format src/ tests/`
3. Fix any remaining issues manually
4. Re-run `uv run ruff check src/ tests/` to confirm clean

Do not skip linting. Do not leave lint warnings "to fix later."

## Pre-Commit Checklist

Before considering any task complete, verify ALL of these pass:

```bash
uv run ruff check --fix src/ tests/
uv run ruff format src/ tests/
uv run pytest tests/ -v
```

If any step fails, fix it. Then re-run ALL steps (a lint fix might break a test, a test fix might introduce a lint issue).

## Common Tasks

### Adding a new CLI command

1. Create `src/silly_scripts/cli/<command_name>.py` following the existing CLI structure: module docstring, imports, logger, helper functions, `@click.command()` main, `__main__` guard.
2. Add the entry point to `pyproject.toml` under `[project.scripts]`: `command-name = "silly_scripts.cli.command_name:main"`.
3. Run `uv sync` to register the new entry point.
4. Create `tests/cli/test_<command_name>.py` with tests covering success paths, error paths, and edge cases. Mock all external tool calls.
5. Run the pre-commit checklist.

### Adding a new setting

1. Add a `Field(...)` to the `Settings` class in `src/silly_scripts/settings.py`.
2. Add the corresponding env var to `env.template` with a comment.
3. Add a test for the new setting in `tests/test_settings.py`.
4. If a CLI needs it, import via `get_settings()` in that CLI module.

### Modifying an existing CLI command

1. Read the existing source and its test file first.
2. Make changes to the source module.
3. Update or add tests to cover the changed behavior.
4. Run the pre-commit checklist.

### Writing changelog entries

After completing a task, append a summary to `changelog/YYYY-MM-DD.md` (today's date). Start the section with a `#` header containing the date, time, and a 3-to-7 word title summarizing the work.

## Pitfalls & Gotchas

- **Settings cache**: `get_settings()` is wrapped in `@lru_cache`. In tests, you MUST call `get_settings.cache_clear()` before and after tests that change environment variables, or stale settings will leak between tests.
- **Settings loads `.env` at import time**: The module-level `settings = get_settings()` in `settings.py` runs on import. Tests that need different settings should mock `get_settings` or clear the cache and set env vars before importing.
- **`show_settings` is not a Click command**: Unlike every other CLI, `show_settings.py` defines a plain function (not `@click.command()`). If adding CLI options to it, it would need to be converted to Click first.
- **Subprocess mocking location**: When mocking `subprocess.run`, patch it at the usage site (`silly_scripts.cli.<module>.subprocess.run`), not at `subprocess.run` globally.
- **`T20` lint rule is active**: `print()` calls are flagged. Use `click.echo()` in CLIs or `logger` for internal code. Suppress with `# noqa: T201` only when `print` is intentional (like `show_settings`).
- **`uv run` prefix**: All commands must be run via `uv run` to use the project's virtualenv. Running `pytest` or `ruff` directly will use system-level installs (if any) and may fail.
