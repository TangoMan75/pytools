# Daily Backlog Index

`history-backlog.py` scans a directory for dated markdown backlog files
(prefix `YYYY-MM-DD_`) and emits an index over a date range as JSON or
Markdown.

```text
python3 history-backlog.py [--start DATE] [--end DATE]
                               [--directory DIR] [--md]
```

## Arguments

- `--start`: inclusive start date (default: today).
- `--end`: inclusive end date (default: today).
- `--directory`: source directory (default: `~/Dropbox`).
- `--md`: print as a Markdown document instead of JSON.

## Time format: plain YYYY-MM-DD dates

Unlike the memory/history tools, this script has **no timestamp column to
query and no timezone involved**. Files are identified by a literal
`YYYY-MM-DD_` filename prefix, and the date range is resolved as plain date
strings:

- `--start` / `--end` accept either `YYYY-MM-DD` or `YYYY-MM-DD HH:MM:SS`;
  `DateRange.parse` validates the input and, for datetime strings, truncates
  the time and keeps only the date.
- `DateRange.days` yields each day string in `[start, end]` inclusive.
- Each file is matched purely by `startswith("YYYY-MM-DD_")` string
  comparison against the directory listing.

No epoch conversion, no timezone offset, and no `--start-ms` / `--end-ms`
options are needed: converting to epoch milliseconds would only add work, so
the range is resolved entirely in `YYYY-MM-DD` strings.

## Output

- Default output is JSON: one object per file with `date`, `file` path,
  `size` (bytes), up to 30 `sections` (top-level `## ` headings), and sorted
  `tags` from a fixed set of hashtags.
- `--md` renders a Markdown document with one section per file (Date, Path,
  Size, Tags, Sections).
- `--quiet`: Suppress non-error output; runtime errors are still reported.
