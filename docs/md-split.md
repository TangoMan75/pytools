# md-split.py

Split a Markdown file into sub-files based on H2 sections, with date prefixes.

## Requirements

- Python 3.10+
- PyYAML (`pip install -r requirements.txt`)

## Usage

```bash
python3 md-split.py <input_file> [options]
```

## Options

- `input_file` - Path to the markdown file to process (required)
- `--output` - Output directory (default: same as input file)
- `--verbose`, `-v` - Enable verbose output

## Description

The script reads a markdown file and splits it into separate files for each H2 (`##`) section. Each output file is named with the pattern `{date}_{slug}.md` where:

- `date` comes from the YAML front matter `date` field, or falls back to the file's modification date
- `slug` is a URL-safe version of the H2 section title

## Examples

### Basic Usage

Given a file `journal.md`:
```markdown
---
date: 2023-10-25
title: My Collection
---
## Ideas
Some ideas here.

## Projects
Project notes here.
```

Running:
```bash
python3 md-split.py journal.md
```

Creates:
- `2023-10-25_ideas.md`
- `2023-10-25_projects.md`

### Handling Duplicates

If multiple sections have the same title, the script adds numeric suffixes:
```markdown
## Gift List
First list.
## Gift List
Second list.
```

Creates:
- `2023-12-25_gift-list.md`
- `2023-12-25_gift-list-1.md`

### Complex Titles

Special characters are handled during slugification:
```markdown
## Update: Project Alpha & Beta!
```

Creates: `2024-03-24_update-project-alpha-beta.md`

### Using Output Directory

```bash
python3 md-split.py journal.md --output ./output
```

## Date Sources

1. **YAML Front Matter** - If the file has a `date` field in its front matter, that date is used
2. **Filename Date** - If the filename starts with `YYYY-MM-DD_` (e.g., `2024-01-15_journal.md`)
3. **File Modification Date** - Falls back to the file's modification timestamp

## Exit Codes

- `0` - Success
- `1` - Error (file not found, not a file, etc.)

## Code Blocks

H2 sections inside code blocks (triple backticks) are not treated as section dividers. The code block content is preserved in the output files.
- `--quiet`: Suppress non-error output; runtime errors are still reported.
