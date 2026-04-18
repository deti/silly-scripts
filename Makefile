.PHONY: \
	help \
	init \
	sync \
	sync-prod \
	test \
	test-cov \
	lint \
	clean \
	show-settings \
	serve \
	analyze-pdf \
	claude-commands \
	claude-usage \
	epub-to-md \
	fleet-plan-and-execute \
	html-to-md \
	m4b-to-m4a \
	plan-and-execute \
	re-toc-epub \
	research-chapter-pipeline \
	speech-to-text \
	split-book \
	split-prompts \
	split-video

help:  ## Show this help message
	@echo "Silly scripts for doing random things around"
	@echo "=============================="
	@echo ""
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

init:  ## Initialize project dependencies and setup
	uv venv
	uv sync

sync:  ## Install dev dependencies. Default
	uv sync

sync-prod:  ## Install without dev dependencies
	uv sync --no-dev

test:  ## Run tests
	uv run pytest tests/ -v

test-cov:  ## Run tests with coverage
	uv run pytest tests/ --cov=src/silly_scripts --cov-report=html --cov-report=term-missing

lint:  ## Run linting
	uv run ruff check --fix src/ tests/
	uv run ruff format src/ tests/

clean:  ## Clean up generated files
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	find . -type f -name ".coverage" -delete
	rm -rf htmlcov/
	rm -rf .pytest_cache/
	rm -rf .ruff_cache/

show-settings:  ## Show current application settings
	uv run show-settings

serve:  ## Serve API
	uv run serve

analyze-pdf: ## Analyze a PDF file with Claude
	uv run analyze-pdf

claude-commands: ## List all available Claude Code slash commands
	uv run claude-commands

claude-usage: ## Display Claude Code usage information
	uv run claude-usage

epub-to-md: ## Convert EPUB chapters to Markdown
	uv run epub-to-md

fleet-plan-and-execute: ## Run prompt through Fleet plan creation and execution
	uv run fleet-plan-and-execute

html-to-md: ## Convert HTML files to Markdown
	uv run html-to-md

m4b-to-m4a: ## Split M4B to M4A chapters
	uv run m4b-to-m4a

plan-and-execute: ## Run prompt through Claude plan and execution
	uv run plan-and-execute

re-toc-epub: ## Update EPUB table of contents
	uv run re-toc-epub

research-chapter-pipeline: ## Run research chapter pipeline
	uv run research-chapter-pipeline

speech-to-text: ## Transcribe audio to text
	uv run speech-to-text

split-book: ## Split HTML book into chunks
	uv run split-book

split-prompts: ## Split consolidated prompt chain
	uv run split-prompts

split-video: ## Split video for Instagram stories
	uv run split-video
