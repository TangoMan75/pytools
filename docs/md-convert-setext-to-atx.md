# md-convert-setext-to-atx.py

Convert setext-style markdown headings (underlines) to ATX-style headings (hash prefixes).

## Requirements

- Python 3.10+

## Usage

```bash
python3 md-convert-setext-to-atx.py <file-or-directory> [-r]
```

## Setext vs ATX Heading Styles

**Setext style** (old):
```
Main Title
==========
```

**ATX style** (modern):
```
# Main Title
```

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
| `--quiet`           | Suppress non-error output; runtime errors are still reported |

## Behavior

- **H1 headings**: Lines underlined with `=` (3+ characters) become `# Heading`
- **H2 headings**: Lines underlined with `-` (3+ characters) become `## Heading`
- **Short underlines**: Lines with fewer than 3 underline characters are ignored
- **Thematic breaks**: Horizontal rules (`---`) preceded by a blank line are preserved
- **Code fences**: Content inside fenced code blocks (`` ``` `` or `~~~`) is preserved unchanged
- **Front matter**: YAML front matter blocks (between `---` delimiters) are preserved unchanged
- **File types**: Only processes `.md`, `.markdown`, `.mdown`, `.mkd` files

## Examples

| Input                              | Output                     |
|------------------------------------|----------------------------|
| `Title\n======`                    | `# Title`                  |
| `Sub Section\n------`              | `## Sub Section`           |
| `Title\n===`                       | `# Title`                  |
| `Small\n==`                        | `Small\n==` (unchanged)    |
| `Text\n\n---`                      | `Text\n\n---` (unchanged)  |
| `` ```\ncode\n===\n``` ``          | `` ```\ncode\n===\n``` `` (unchanged) |
