# Silly scripts

Silly scripts for doing random things around

* Land of holy [prompts](./prompts.txt) for code assitants 🤖
* [Changelog](./changelog) files

# Scripts
* 📄 `analyze-pdf` - Analyze a PDF file with Claude via the Agent SDK.
* ⌨️ `claude-commands` - List all available Claude Code slash commands.
* 📊 `claude-usage` - Display Claude Code usage information.
* 📖 `epub-to-md` - Convert EPUB chapters to individual Markdown files.
* 🚀 `fleet-plan-and-execute` - Run a prompt through Fleet plan creation, then execute.
* 🌐 `html-to-md` - Convert all HTML/HTM files in a folder to Markdown.
* 🎵 `m4b-to-m4a` - Split M4B with EAC3 into 5.1 AAC M4A chapters.
* 📝 `plan-and-execute` - Run a prompt through Claude: first plan, then execute.
* 📕 [Re create table of contents](./docs/re_toc_epub.md) in epub (`re-toc-epub`) - Update EPUB table of contents from markdown structure.
* 🧪 `research-chapter-pipeline` - Run the research chapter pipeline on chapter Markdown files.
* 📡 `serve` - Start the API server.
* ⚙️ `show-settings` - Print the app settings.
* 🎙️ `speech-to-text` - Transcribe audio file to text using Deepgram.
* 📚 `split-book` - Analyze a local HTML book and split it into chunks.
* ✂️ `split-prompts` - Split a consolidated prompt chain into separate files.
* 🎬 `split-video` - Split a video into chunks for Instagram stories.



## Development and Management
A `Makefile` is provided for common tasks:
* `make init` - Initialize project dependencies and setup
* `make test` - Run tests
* `make lint` - Run linting (ruff)
* `make help` - Show all available commands (including script shortcuts)

Most scripts can be run directly via `make <script-name>` or `uv run <script-name>`.
