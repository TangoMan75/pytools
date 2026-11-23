# markdown_front_matter

Prepend YAML front matter to markdown files with automatic metadata extraction.

## Overview

This tool automatically generates YAML front matter for markdown files. It extracts title from filename, date from file modification time, and author from the system USER environment variable.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
python3 md-front-matter.py <input> [options]
```

## Arguments

| Argument |             Description              |
|----------|--------------------------------------|
| `input`  | Path to a markdown file or directory |

## Options

|        Option       |                         Description                         |
|---------------------|-------------------------------------------------------------|
| `--author TEXT`     | Author name (default: $USER environment variable)           |
| `--date TEXT`       | Date in YYYY-MM-DD format (default: file modification date) |
| `--tags TEXT`       | Comma-separated list of tags                                |
| `--force`           | Override existing front matter attributes                   |
| `--recursive`       | Enable recursive directory traversal                        |
| `--dry-run`         | Simulate actions without modifying anything                 |
| `--verbose`, `-v`   | Increase verbosity (stackable)                              |
| `--quiet`           | Suppress non-error output; runtime errors are still reported |

## Title Extraction

The title is derived from the filename by:
1. Removing the `.md` extension
2. Replacing hyphens and underscores with spaces
3. Converting to title case

|           Filename           |     Generated Title     |
|------------------------------|-------------------------|
| `my-document.md`             | My Document             |
| `my_document.md`             | My Document             |
| `my_interesting-document.md` | My Interesting Document |

## Date Handling

Date priority (highest to lowest):
1. `--date` command line option
2. Date prefix in filename (`YYYY-MM-DD*`)
3. File modification date

### Date from Filename

If the filename starts with a date in `YYYY-MM-DD` format, that date is used instead of the file modification date:

|            Filename           | Extracted Date |         Title          |
|-------------------------------|----------------|------------------------|
| `2024-01-15-my-notes.md`      | 2024-01-15     | My Notes               |
| `2023-12-25_project-ideas.md` | 2023-12-25     | Project Ideas          |
| `2024-01-01.md`               | 2024-01-01     | (empty, uses filename) |

## Author

- Default: Uses the `USER` environment variable
- Override: Use `--author` to specify a custom author

## Tag Handling

Tags are always sorted alphabetically. There are two sources for tags:
1. **Command line**: Use `--tags` to specify tags
2. **Document content**: Tags are extracted from hashtags in the document (lines containing only `#tag`)

### Extracting Tags from Document

Tags can be automatically extracted from the document content. A valid tag is a line containing only a hashtag followed by alphanumeric characters, hyphens, or underscores:

```
#this-is-a-valid-tag
#ThisIsAValidTag
#this_is_a_valid_tag
#tag1
#tag_2
```

Lines that are **not** valid tags:
- `# This Is A Title` (contains spaces - it's a markdown heading)
- `# I am a comment` (contains spaces)
- `$var='value' # not a tag` (code comment)

### Tag Merging

When processing files with existing front matter:
- Without `--force`: New tags (CLI + extracted) are merged with existing tags (deduplicated and sorted)
- With `--force`: All existing tags are replaced by CLI tags and extracted tags

## Examples

### Generate front matter for a new file

```bash
python3 md-front-matter.py my-document.md
```

Result:
```yaml
---
title: My Document
date: 2024-01-15
author: username
---
```

### Add custom author and date

```bash
python3 md-front-matter.py document.md --author "John Doe" --date "2024-01-15"
```

### Add tags

```bash
python3 md-front-matter.py document.md --tags "python,markdown,tools"
```

### Preserve existing front matter (merge tags)

Given existing front matter with `tags: [zebra, alpha]`:
```bash
python3 md-front-matter.py existing.md --tags "middle-tag,beta"
```

Result:
```yaml
---
title: Existing Title
date: 2023-06-01
author: Jane Smith
tags:
  - alpha
  - beta
  - middle-tag
  - zebra
---
```

### Force override existing front matter

```bash
python3 md-front-matter.py existing.md --force --author "New Author" --tags "forced-tag"
```

This replaces the existing author and tags while preserving the title.

### Process directory recursively

```bash
python3 md-front-matter.py ./notes --recursive --tags "notes"
```

### Dry run (preview changes)

```bash
python3 md-front-matter.py document.md --dry-run --verbose
```

## Exit Codes

| Code |                  Description                  |
|------|-----------------------------------------------|
|    0 | Success                                       |
|    1 | Error (file not found or not a markdown file) |
