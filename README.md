# Silly Scripts

Silly scripts for doing random things around.

## Installation

Requires **Python 3.14+** and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/deti/silly-scripts.git
cd silly-scripts
make init   # creates a venv and installs all dependencies
```

Or manually:

```bash
uv venv
uv sync
```

## Configuration

Copy the environment template and fill in your values:

```bash
cp env.template .env
```

The most important setting for the `ask-claude` command is the Anthropic API key:

```bash
# .env
ANTHROPIC_API_KEY=sk-ant-...
```

You can also configure defaults for the Claude CLI:

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(required)* | Your Anthropic API key |
| `CLAUDE_DEFAULT_MODEL` | `sonnet` | Model to use (`sonnet`, `opus`, `haiku`) |
| `CLAUDE_DEFAULT_TOOLS` | `Read,Glob,Grep` | Comma-separated tools available to the agent |

All settings are loaded from the `.env` file at the project root via
[pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/).
See `env.template` for the full list of available options.

## Usage

### ask-claude

Ask Claude a question using the Claude Agent SDK. Run `ask-claude --help`
for the full option list.

```
Usage: ask-claude [OPTIONS] [PROMPT]

  Ask Claude a question using the Claude Agent SDK.

  Pass a prompt as a positional argument, via --prompt, or pipe from stdin.

Options:
  -p, --prompt TEXT               The prompt to send to Claude (alternative to
                                  positional argument).
  -m, --model TEXT                Model to use (e.g. sonnet, opus, haiku).
  -t, --tools TEXT                Allowed tools, comma-separated (e.g.
                                  Read,Glob,Grep).
  --system-prompt TEXT            Custom system prompt.
  --permission-mode [default|acceptEdits|bypassPermissions]
                                  Permission mode for tool execution.
                                  [default: default]
  -C, --working-dir DIRECTORY     Working directory for the agent.
  -v, --verbose                   Show all message types (tool calls, system).
  --json                          Output raw JSON messages (NDJSON).
  --help                          Show this message and exit.
```

### Examples

**Simple question:**

```bash
ask-claude "What files are in this directory?"
```

**Pipe input from another command:**

```bash
echo "Summarize this codebase" | ask-claude
```

**Choose a model and enable verbose output:**

```bash
ask-claude "Find TODO comments" -m opus --verbose
```

**Use specific tools with a custom working directory:**

```bash
ask-claude "Refactor the utils module" \
  --tools "Read,Edit,Bash" \
  --permission-mode acceptEdits \
  -C /path/to/project
```

**Get structured NDJSON output:**

```bash
ask-claude --json "List all API endpoints" | jq .
```

### Other scripts

| Command | Description |
|---|---|
| `re-toc-epub` | [Re-create table of contents](./docs/re_toc_epub.md) in an EPUB |
| `speech-to-text` | Transcribe audio using Deepgram |
| `split-video` | Split a video file into segments |
| `m4b-to-m4a` | Convert M4B audiobooks to M4A chapters |
| `show-settings` | Print current application settings |
| `serve` | Start the FastAPI development server |

## Development

```bash
make test       # run the test suite
make test-cov   # run tests with coverage report
make lint       # lint and format with ruff
make clean      # remove generated files
```

Run `make help` for all available targets.
