# ADR-001: CLI Command Wrapping the Claude Agent SDK

**Status:** Proposed
**Date:** 2026-03-08
**Context:** task-001 — Design the CLI command that wraps the Claude Agent SDK

---

## 1. Decision Summary

Add a new CLI command `ask-claude` to the existing `silly-scripts` Python package. The command accepts a natural-language prompt, forwards it to the Claude Agent SDK's `query()` async iterator, and streams all output to stdout in real time. It follows every established project convention: Click for argument parsing, pydantic-settings for configuration, and an independent module under `src/silly_scripts/cli/`.

---

## 2. Target Language / Runtime

**Python 3.14+** (matches `pyproject.toml` `requires-python`).

**Rationale — Python over TypeScript:**

| Criterion | Python | TypeScript |
|-----------|--------|------------|
| Existing project runtime | Yes (`silly-scripts` is Python) | Would require a second runtime |
| Claude Agent SDK maturity | First-class, async iterator API | Equivalent, but adds Node.js dependency |
| CLI framework in use | Click (already a dependency) | Would need a new framework |
| Consistency with other CLIs | Identical pattern | Breaks project uniformity |

Adding a TypeScript entry point was considered and rejected because it would introduce a second runtime, a second package manager, and a second build system into a single-package Python project.

---

## 3. CLI Argument Interface

### Command name

```
ask-claude
```

Registered as a console-script entry point in `pyproject.toml`.

### Argument parsing (Click)

| Argument / Flag | Type | Required | Default | Description |
|-----------------|------|----------|---------|-------------|
| `PROMPT` | positional `str` | No* | — | The prompt to send to Claude |
| `--prompt` / `-p` | `str` | No* | — | Alternative: pass prompt via flag |
| `--model` / `-m` | `str` | No | `"sonnet"` | Model to use (e.g. `sonnet`, `opus`, `haiku`) |
| `--tools` / `-t` | `str` (comma-sep) | No | `"Read,Glob,Grep"` | Allowed tools (comma-separated) |
| `--system-prompt` | `str` | No | `None` | Custom system prompt |
| `--permission-mode` | Choice | No | `"default"` | One of `default`, `acceptEdits`, `bypassPermissions` |
| `--working-dir` / `-C` | `Path` | No | `.` | Working directory for agent |
| `--verbose` / `-v` | flag | No | `False` | Show all message types (tool calls, system) |
| `--json` | flag | No | `False` | Output raw JSON messages (one per line, NDJSON) |

*\* At least one of positional `PROMPT` or `--prompt` must be provided. If neither is given and stdin is a pipe, read from stdin. This three-source strategy (positional → flag → stdin) allows ergonomic interactive use and scriptable piping.*

### Usage examples

```bash
# Positional (most common)
ask-claude "What files are in this directory?"

# Flag form (useful when prompt contains shell-special characters)
ask-claude --prompt "Find TODO comments" --tools "Read,Glob,Grep"

# Pipe from another command
echo "Summarize this codebase" | ask-claude

# With model and permission overrides
ask-claude "Fix the bug in auth.py" -m opus --permission-mode acceptEdits --tools "Read,Edit,Bash"
```

---

## 4. SDK Invocation

### Entry point used

`claude_agent_sdk.query()` — the async iterator API. This is the correct entry point because:

1. It streams messages incrementally (required for real-time output).
2. It manages the full agentic loop internally (tool execution, retries, context).
3. It does not require manual tool implementation.

`ClaudeSDKClient` was considered but rejected for v1 — it adds session-management complexity that is unnecessary for a stateless CLI command. Session support (`--resume <session-id>`) can be added later without architectural changes.

### Instantiation pattern

```python
from claude_agent_sdk import query, ClaudeAgentOptions

options = ClaudeAgentOptions(
    allowed_tools=parsed_tools,          # from --tools
    permission_mode=permission_mode,     # from --permission-mode
    system_prompt=system_prompt,         # from --system-prompt, if provided
)

async for message in query(prompt=prompt, options=options):
    handle_message(message)
```

### API key sourcing

The SDK reads `ANTHROPIC_API_KEY` from the environment automatically. The CLI does **not** accept an API key as a flag (security: avoids key exposure in shell history and process listings). The CLI validates the env var is set before calling `query()` and emits a clear error message if missing.

The SDK also supports Bedrock (`CLAUDE_CODE_USE_BEDROCK=1`), Vertex AI (`CLAUDE_CODE_USE_VERTEX=1`), and Azure (`CLAUDE_CODE_USE_FOUNDRY=1`) via environment variables. The CLI inherits this behavior without additional code.

---

## 5. Streaming / Output Strategy

### Default mode (human-readable)

All `AssistantMessage` text blocks are printed to **stdout** as they arrive, producing a live-typing effect. Tool invocations are printed as single summary lines to **stderr** (so they can be suppressed or redirected independently).

```
[stdout] Claude's reasoning text streams here in real time...
[stderr] [tool] Read: src/auth.py
[stderr] [tool] Edit: src/auth.py
[stdout] I've fixed the null-check bug in the authentication module.
```

### `--verbose` mode

All message types are printed, including system init, tool inputs/outputs, and result metadata. Useful for debugging.

### `--json` mode (machine-readable)

Each SDK message is serialized as a single JSON line to stdout (NDJSON format). This enables piping to `jq`, log aggregators, or downstream programs.

```
{"type":"system","subtype":"init","session_id":"abc123"}
{"type":"assistant","content":[{"type":"text","text":"Reading auth.py..."}]}
{"type":"result","subtype":"success","result":"..."}
```

### Output contract

| Stream | Content |
|--------|---------|
| stdout | Agent's textual output (human mode) or full NDJSON (json mode) |
| stderr | Tool-call summaries (human mode), warnings, errors |

This separation lets callers capture the "answer" from stdout while still seeing operational detail on stderr.

---

## 6. Error Handling Strategy

### Error categories and behavior

| Error | Detection | User message | Exit code |
|-------|-----------|-------------|-----------|
| Missing API key | Check `ANTHROPIC_API_KEY` before SDK call | `Error: ANTHROPIC_API_KEY environment variable is not set.` | 2 |
| Invalid arguments | Click validation | Click's built-in error formatting | 2 |
| SDK authentication failure | Catch SDK auth exception | `Error: Authentication failed. Verify your API key.` | 3 |
| SDK rate limit / quota | Catch SDK rate-limit exception | `Error: Rate limited. Retry after {n} seconds.` | 4 |
| Network / transient error | Catch `ConnectionError` / SDK transport errors | `Error: Network error: {detail}` | 5 |
| Agent task failure | `ResultMessage` with error subtype | Print error detail, no stack trace | 1 |
| Unexpected exception | Top-level `except Exception` | `Error: Unexpected failure: {detail}` + suggest `--verbose` | 99 |
| Keyboard interrupt | `KeyboardInterrupt` handler | `\nInterrupted.` (clean newline) | 130 |

### Design principles

1. **No stack traces by default.** Users see a one-line message. `--verbose` adds the traceback.
2. **Errors to stderr.** stdout remains clean for piping.
3. **Consistent with existing CLIs.** Uses `click.ClickException` where appropriate (exit code 1 for Click errors) and `sys.exit(n)` for SDK-specific codes.

---

## 7. Exit Code Conventions

| Code | Meaning |
|------|---------|
| 0 | Success — agent completed task |
| 1 | Agent reported a task-level failure |
| 2 | Usage error (bad args, missing env var) |
| 3 | Authentication error |
| 4 | Rate limit / quota exceeded |
| 5 | Network / transient error |
| 99 | Unexpected internal error |
| 130 | Interrupted (SIGINT / Ctrl-C) |

These follow POSIX conventions (0 = success, 1 = general error, 2 = usage error, 128+signal for signals).

---

## 8. Project Structure

### New files

```
src/silly_scripts/cli/
    ask_claude.py          # Click command — the only new module
```

### Module layout (`ask_claude.py`)

```
ask_claude.py
├── main()                 # Click command entry point
├── _resolve_prompt()      # Positional / flag / stdin resolution
├── _parse_tools()         # Comma-separated string → list
├── _run_agent()           # async: calls query(), yields messages
├── _print_human()         # Human-readable formatter
├── _print_json()          # NDJSON formatter
└── _handle_error()        # Categorize exception → exit code
```

No new packages or sub-packages. One file, following the project's established pattern where each CLI command is a single self-contained module.

### Entry point registration (`pyproject.toml`)

```toml
[project.scripts]
# ... existing entries ...
ask-claude = "silly_scripts.cli.ask_claude:main"
```

### New dependency

```toml
[project]
dependencies = [
    # ... existing ...
    "claude-agent-sdk",
]
```

No other new dependencies. `click` and `pydantic-settings` are already present.

---

## 9. Configuration via pydantic-settings

Extend the existing `Settings` class in `src/silly_scripts/settings.py`:

```python
class Settings(BaseSettings):
    # ... existing fields ...

    # Claude Agent SDK
    anthropic_api_key: str | None = None           # read from ANTHROPIC_API_KEY
    claude_default_model: str = "sonnet"            # overridable default
    claude_default_tools: str = "Read,Glob,Grep"   # overridable default
```

This enables `.env` file support (already wired via `pydantic-settings`) and a single source of truth for defaults. CLI flags override settings values; settings values override hardcoded defaults.

**Precedence:** CLI flag > environment variable (via Settings) > hardcoded default.

---

## 10. Architectural Invariants

1. **No SDK leakage.** `ask_claude.py` is the only module that imports from `claude_agent_sdk`. No other CLI or library module depends on it.
2. **Stateless.** Each invocation is independent. No session persistence in v1.
3. **No interactive prompts during agent execution.** `permission_mode` is set at invocation time. The CLI does not implement a `canUseTool` callback in v1 (would require a TUI, which is out of scope).
4. **stdout/stderr contract.** Answer text on stdout, operational detail on stderr. This is a public API that scripts may depend on.

---

## 11. Alternatives Considered

| Decision | Alternative | Why rejected |
|----------|-------------|-------------|
| Python | TypeScript/Node.js | Adds second runtime to a Python-only project |
| `query()` iterator | `ClaudeSDKClient` | Adds session complexity not needed for stateless CLI |
| Click | argparse | Click is already a project dependency; consistency wins |
| Single module | Separate package | Violates project's one-package structure |
| API key via flag | `--api-key` flag | Security risk (shell history, `/proc` exposure) |
| Interactive permission prompts | `canUseTool` callback | Requires TUI; out of scope for v1 |

---

## 12. Future Extensions (out of scope for v1)

- **Session resume:** `--resume <session-id>` flag, using `ClaudeSDKClient`.
- **MCP server attachment:** `--mcp <name:command>` flag.
- **Interactive permission mode:** TUI-based `canUseTool` callback (e.g. via `rich` or `prompt_toolkit`).
- **Subagent definitions:** `--agent <name:prompt>` for custom subagents.
- **Config file:** `~/.config/silly-scripts/claude.toml` for persistent defaults.

These can be added incrementally without changing the core architecture.

---

## Sources

- [Claude Agent SDK Overview](https://platform.claude.com/docs/en/agent-sdk/overview)
- [Claude Agent SDK Quickstart](https://platform.claude.com/docs/en/agent-sdk/quickstart)
- [claude-agent-sdk on PyPI](https://pypi.org/project/claude-agent-sdk/)
- [@anthropic-ai/claude-agent-sdk on npm](https://www.npmjs.com/package/@anthropic-ai/claude-agent-sdk)
