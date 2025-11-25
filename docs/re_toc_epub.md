# re_toc_epub - EPUB Table of Contents Updater

## Overview

`re_toc_epub` is a command-line tool that updates or recreates the table of contents (ToC) in EPUB files based on a markdown-formatted structure file. The script scans the EPUB file, matches chapters by title, and rebuilds the navigation structure according to your specified hierarchy.

## Installation

The script is automatically available after installing the project dependencies:

```bash
uv sync
```

Or install production dependencies only:

```bash
uv sync --no-dev
```

## Usage

```bash
uv run re-toc-epub <epub_file> <toc_file> [output_file]
```

### Arguments

- **`epub_file`** (required): Path to the input EPUB file
- **`toc_file`** (required): Path to a markdown file containing the desired table of contents structure
- **`output_file`** (optional): Path to the output EPUB file. If not provided, the input file is overwritten

### Examples

#### Basic Usage (Overwrite Input File)

```bash
uv run re-toc-epub book.epub toc_structure.md
```

This will update `book.epub` in place with the new table of contents.

#### Save to New File

```bash
uv run re-toc-epub book.epub toc_structure.md book_updated.epub
```

This creates a new file `book_updated.epub` while leaving the original unchanged.

## Table of Contents File Format

The ToC file should be a plain text file with markdown-style headers. The script supports headers from level 1 (`#`) through level 6 (`######`).

### Example ToC File

```markdown
# Introduction

## Getting Started

### Installation

### Configuration

# Main Content

## Chapter 1: Basics

### Section 1.1

### Section 1.2

## Chapter 2: Advanced Topics

# Conclusion
```

### Format Rules

- Headers must start with `#` characters (1-6 hashes)
- Header text follows the hashes (with optional space)
- Blank lines are ignored
- Non-header lines are ignored
- Header matching is case-insensitive

### Example Structure

```
# Header 1          → Level 1 (top-level)
## Header 1.1       → Level 2 (child of Header 1)
### Header 1.1.1    → Level 3 (child of Header 1.1)
# Header 2          → Level 1 (new top-level)
```

## How It Works

1. **Parse ToC Structure**: The script reads the markdown ToC file and extracts header levels and titles.

2. **Scan EPUB**: For each title in the ToC structure, the script searches through all HTML documents in the EPUB file.

3. **Match Chapters**: It looks for matching titles in HTML heading tags (`<h1>` through `<h6>`) within the EPUB content. Matching is case-insensitive.

4. **Build Navigation**: The script creates a hierarchical navigation structure based on the markdown header levels.

5. **Update EPUB**: The new table of contents replaces the existing one in the EPUB file.

## Chapter Matching

The script matches chapters by searching for titles in HTML heading tags. It:

- Searches all HTML documents in the EPUB
- Looks for titles in `<h1>` through `<h6>` tags
- Performs case-insensitive matching
- Strips HTML tags from heading content before comparison

### Fallback Behavior

If a title from the ToC file cannot be found in the EPUB:

- A warning is logged
- The first available chapter is used as a fallback
- If no chapters exist, an error is logged and that entry is skipped

## Error Handling

The script handles various error conditions:

- **Invalid EPUB file**: Raises an error if the EPUB cannot be read
- **Empty ToC file**: Raises an error if no valid headers are found
- **Write failures**: Raises an error if the EPUB cannot be written

All errors are displayed as user-friendly messages via Click exceptions.

## Logging

The script provides informational logging:

- File paths being processed
- Number of ToC entries parsed
- Warnings for unmatched titles
- Success confirmation

Logging level is set to INFO by default.

## Technical Details

### Dependencies

- **ebooklib**: For reading and writing EPUB files
- **lxml**: For XML/HTML parsing
- **click**: For command-line interface

### EPUB Structure

The script:
- Preserves all existing EPUB content
- Only modifies the table of contents (navigation)
- Maintains hierarchical structure using EPUB Link objects
- Supports nested navigation (parent-child relationships)

### File Safety

When overwriting the input file:
- The script writes to a temporary file first (`.tmp.epub`)
- Only replaces the original file after successful write
- This prevents data loss if the write operation fails

## Limitations

1. **Title Matching**: The script matches chapters by exact title text in HTML headings. If your EPUB uses different titles or formatting, matches may fail.

2. **HTML Structure**: The script expects standard HTML heading tags. Non-standard markup may not be detected.

3. **Encoding**: The script assumes UTF-8 encoding for both the ToC file and EPUB content.

## Examples

### Example 1: Simple Flat Structure

**toc_structure.md:**
```markdown
# Chapter 1
# Chapter 2
# Chapter 3
```

This creates a flat table of contents with three top-level entries.

### Example 2: Hierarchical Structure

**toc_structure.md:**
```markdown
# Part I: Introduction
## Chapter 1: Getting Started
### Installation
### Configuration
## Chapter 2: Basics
# Part II: Advanced Topics
## Chapter 3: Advanced Concepts
```

This creates a hierarchical structure with parts, chapters, and sections.

### Example 3: Complex Nested Structure

**toc_structure.md:**
```markdown
# Book Title
## Part 1
### Chapter 1
#### Section 1.1
##### Subsection 1.1.1
#### Section 1.2
### Chapter 2
## Part 2
### Chapter 3
```

This demonstrates deep nesting (up to 6 levels supported).

## Troubleshooting

### "Could not find chapter for title: X"

This warning means the script couldn't find a matching heading in the EPUB. Check:
- The title spelling matches exactly (case-insensitive)
- The title exists in an HTML heading tag (`<h1>`-`<h6>`)
- The EPUB file contains the expected content

### "No valid ToC structure found"

This error means the ToC file doesn't contain any valid markdown headers. Ensure:
- Headers start with `#` characters
- Headers have text after the hashes
- The file is readable and properly formatted

### "Failed to read EPUB file"

This error indicates the EPUB file is corrupted or not a valid EPUB. Verify:
- The file is a valid EPUB format
- The file is not corrupted
- You have read permissions for the file

## See Also

- [EPUB Specification](https://www.w3.org/publishing/epub3/)
- [Markdown Syntax](https://www.markdownguide.org/basic-syntax/#headings)

## License

Part of the silly-scripts project.

