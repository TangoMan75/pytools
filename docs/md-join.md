# md-join.py

Concatenate multiple markdown files into a single file, removing YAML front matter.

## Usage

```bash
python3 md-join.py <input_path> [options]
```

## Options

- `input_path` - File or directory to process (required)
- `--output` - Output file (default: YYYY-MM-DD.md)
- `--recursive` - Enable recursive directory traversal
- `--include` - Include filter (default: *.md)
- `--exclude` - Exclude filter (glob pattern)
- `--dry-run` - Simulate actions without modifying anything
- `-v, --verbose` - Increase verbosity (stackable: -v, -vv, -vvv)

## Description

The script reads markdown files and concatenates them into a single output file. YAML front matter is automatically removed from each file before joining. Files are sorted alphabetically by filename before concatenation.

## Examples

### Basic Usage

Given a directory with files `a.md` and `b.md`:
```bash
python3 md-join.py ./notes
```

Creates output file `2026-03-26.md` (today's date) containing the joined content.

### Custom Output File

```bash
python3 md-join.py ./notes --output combined.md
```

Creates `combined.md` instead of the default date-named file.

### Recursive Traversal

```bash
python3 md-join.py ./docs --recursive --output all.md
```

Recursively processes all `.md` files in `./docs` and subdirectories.

### Dry Run

```bash
python3 md-join.py ./notes --dry-run --verbose
```

Shows what would be created without actually writing the output file.

### Verbose Mode

```bash
python3 md-join.py ./notes -v
python3 md-join.py ./notes -vv
python3 md-join.py ./notes -vvv
```

Increases verbosity level for more detailed output.

## Behavior

### File Sorting

Files are sorted alphabetically by filename before joining. This ensures consistent output regardless of filesystem ordering.

### Front Matter Removal

YAML front matter between `---` delimiters at the start of files is stripped:
```markdown
---
title: My Notes
date: 2023-10-25
---
## Content

Some content.
```

Becomes:
```markdown
## Content

Some content.
```

### Empty Files

Files that become empty after front matter removal (i.e., files containing only front matter) are skipped.

### Non-Markdown Files

Files without `.md` extension are automatically excluded unless `--include` specifies a different pattern.

## Installation

```bash
```

Installs the script to `~/.local/share/TangoMan75/md-join.py` and creates a symlink in `~/.local/bin/`.

## Exit Codes

- `0` - Success
- `1` - Error (missing input, path not found, etc.)
- `--quiet`: Suppress non-error output; runtime errors are still reported.
