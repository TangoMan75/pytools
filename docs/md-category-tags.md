# md-category-tags.py

Add category tags to daily notes based on the filename or title date-category pattern.

## Requirements

- Python 3.10+

## Usage

```bash
python3 md-category-tags.py <directory> [-r]
```

## Category Detection

The category is taken from the `category` portion of either:

- The filename pattern `YYYY-MM-DD_category.md`
- The first-line H1 title pattern `YYYY-MM-DD_category`

Example: `2024-01-15-workout.md` or `# 2024-01-15-workout` yields category `workout`
and tag `#workout`.

## CLI Arguments

|         Flag        |                   Description                   |
|---------------------|-------------------------------------------------|
| `input`             | File or directory to process (required)         |
| `--output`          | Output file or directory                        |
| `--recursive`, `-r` | Enable recursive directory traversal            |
| `--include`         | Include filter (glob pattern)                   |
| `--exclude`         | Exclude filter (glob pattern)                   |
| `--dry-run`, `-d`   | Simulate actions without modifying anything     |
| `-v`, `--verbose`   | Increase verbosity (stackable: -v, -vv, -vvv)   |
| `--completion`      | Print bash completion script to stdout and exit |

## Behavior

- **Split**: Each file is split into notes; a new note begins at every `## ` heading.
- **Tag existing**: If a note already has a tag line (a line of `#word` tags), the
  category tag is prepended to the first such line.
- **Tag without tags**: If a note has no tag line, the category tag is inserted
  right after its `## ` title; if there is no `## ` title, the tag is appended at
  the end of the note.
- **Skip**: Files without a resolvable category.
- **Skip**: Notes that already contain the category tag.
- `--quiet`: Suppress non-error output; runtime errors are still reported.
- `--completion`: Print a bash completion script and exit (used by `installer.py`).
