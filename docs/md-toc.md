# md-toc

Generate a Table of Contents (TOC) from the headings of a markdown document.

## Usage

```bash
python3 md-toc.py <input> [options]
```

### Arguments

- `input` — a markdown file or directory to process.
- `--output` — write the TOC (or modified document) to this file.
- `--recursive` — traverse directories recursively.
- `--include` / `--exclude` — glob filters for directory traversal.
- `--dry-run` — simulate actions without modifying anything.
- `--log` — print the current log file and stop.
- `--verbose`, `-v` — increase verbosity (stackable).
- `--quiet` — suppress non-error output; runtime errors are still reported.
- `--completion` — print a bash completion script and exit.
- `--insert` — insert the TOC into the document (replaces an `<!-- toc -->`
  placeholder, or inserts after front matter when no placeholder exists).
- `--min-depth` — minimum heading depth to include (default `1`).
- `--max-depth` — maximum heading depth to include (default `6`).
- `--title` — TOC title text (default `Table of Contents`; empty string omits it).

## Behavior

- Headings are detected as ATX (`#`, `##`, ...) and setext (`=`/`-` underlines).
- Text inside fenced code blocks and YAML front matter is ignored.
- Links use GitHub-style anchors; duplicate headings get `-1`, `-2`, ... suffixes.
- Without `--insert` or `--output`, the TOC is printed to stdout.

## Examples

Print a TOC to stdout:

```bash
python3 md-toc.py README.md
```

Insert the TOC into a document, replacing the `<!-- toc -->` placeholder:

```bash
python3 md-toc.py README.md --insert
```

Limit the TOC to level 2 and 3 headings:

```bash
python3 md-toc.py docs/guide.md --min-depth 2 --max-depth 3 --output toc.md
```
