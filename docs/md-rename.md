# md-rename.py

Rename markdown files based on YAML front matter (date, title, author).

## Requirements

- Python 3.10+
- PyYAML (`pip install PyYAML`)

## Usage

```bash
python3 md-rename.py <directory> [-r]
```

## Filename Format

`{date}-{author-slug}-{title-slug}.md`

Example: `2024-01-15-john-doe-my-first-post.md`

## CLI Arguments

|         Flag        |                   Description                   |
|---------------------|-------------------------------------------------|
| `input`             | File or directory to process (required)         |
| `--output`          | Output file or directory                        |
| `--recursive`       | Enable recursive directory traversal            |
| `--include`         | Include filter (glob pattern)                   |
| `--exclude`         | Exclude filter (glob pattern)                   |
| `--dry-run`         | Simulate actions without modifying anything     |
| `-v`, `--verbose`   | Increase verbosity (stackable: -v, -vv, -vvv)   |

## Front Matter Format

```yaml
---
date: 2024-01-15
title: My First Post
author: John Doe
---
```

Required fields: `date`, `title`, `author`

## Behavior

- **Rename**: Files with valid front matter containing all required fields
- **Handle duplicates**: Appends `_1`, `_2`, etc. when filename already exists
- **Skip**: Files without front matter
- **Skip**: Files missing required fields (date, title, author)
- **Skip**: Files already correctly named
- `--quiet`: Suppress non-error output; runtime errors are still reported.
