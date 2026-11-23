# semantic_versioning

Auto-increment semver-shaped version numbers in text files.

## Overview

`semantic_versioning` finds three-segment dotted version numbers (e.g. `0.1.0`, `1.2.9`) inside any text file and bumps them in place. It uses a constrained regex with negative lookarounds so IP addresses (`192.168.1.1`), calendar dates (`2024.01.15`), and four-segment build numbers (`1.2.3.4`) are left alone.

## Installation

```bash
```

## Usage

```bash
python3 semantic_versioning.py <input> [options]
```

## Arguments

| Argument |             Description              |
|----------|--------------------------------------|
| `input`  | Path to a text file or directory     |

## Options

|          Option          |                Description                |
|--------------------------|-------------------------------------------|
| `--major`                | Bump the major version (resets minor/fix) |
| `--minor`                | Bump the minor version (resets fix)       |
| `--fix`                  | Bump the fix version (default)            |
| `--line` N               | Only bump the given 1-indexed line        |
| `--check`                | Exit non-zero if any file would change    |
| `--recursive`            | Recurse into sub-directories              |
| `--include` PATTERN      | Include filter (glob)                      |
| `--exclude` PATTERN      | Exclude filter (glob)                      |
| `--dry-run`              | Simulate without writing                  |
| `--verbose`, `-v`        | Increase verbosity (`-v`, `-vv`, `-vvv`)  |
| `--quiet`                | Suppress non-error output; runtime errors are still reported |

`--major`, `--minor`, and `--fix` are mutually exclusive. If none is given, the script defaults to `--fix`.

## Version Pattern

The matcher is:

```
(?<![\d.])\d{1,3}\.\d{1,3}\.\d{1,3}(?!\d|\.)
```

|     Input      | Matched? |       Why        |
|----------------|----------|------------------|
| `1.2.3`        | yes      | Clean semver    |
| `v1.2.3`       | yes      | `v` is non-digit |
| `"1.2.3"`      | yes      | Quotes are non-digit |
| `1.2.3-rc.1`   | yes (suffix stripped) | Pre-release captured |
| `192.168.1.1`  | no       | Has a trailing `.1` and a leading `.` |
| `2024.01.15`   | no       | First segment has 4 digits |
| `1.2.3.4`      | no       | Has a trailing `.4` |
| `0.1.0`        | yes      | Clean semver    |

## Bump Semantics

| Kind   | 0.1.0 becomes | 1.5.7 becomes | 1.2.3-rc.1 becomes |
|--------|---------------|---------------|---------------------|
| major  | 1.0.0         | 2.0.0         | 2.0.0               |
| minor  | 0.2.0         | 1.6.0         | 1.3.0               |
| fix    | 0.1.1         | 1.5.8         | 1.2.4               |

Pre-release suffixes (`-rc.1`, `-beta.4`, etc.) are stripped on every bump. The `--line` flag can be used in conjunction with any kind.

## `--line` Behavior

- 1-indexed. `--line 1` targets the first line.
- Limits changes to that one line. Other lines in the file are not touched.
- Applies per file in recursive mode (line 5 of file A is independent of line 5 of file B).
- Out-of-range or no-match on the targeted line counts as a skip (the file is left untouched).

## Binary File Detection

Files whose first 8 KB contain a NUL byte are treated as binary and skipped. This prevents the script from corrupting images, archives, or compiled artifacts that may happen to contain a `\d+\.\d+\.\d+` pattern.

## Encoding

- Reads/writes UTF-8.
- Strips a leading UTF-8 BOM (`\ufeff`) transparently — the file is rewritten without the BOM.

## Atomic Writes

Writes go to a temp file in the same directory, then `os.replace()` swaps it in. A crash mid-write leaves the original file intact.

## `--check` Mode (CI gate)

`--check` runs the same matcher but never writes. If any file *would* be modified, the script exits with code 1. Use it in CI to enforce that version strings are always up to date.

```bash
python3 semantic_versioning.py src/ --recursive --check
echo $?  # 0 = clean, 1 = stale version found
```

## Examples

### Bump the fix version in a single file

```bash
python3 semantic_versioning.py CHANGELOG.md
```

Before: `1.2.3` → After: `1.2.4`

### Bump the minor version in a JSON file

```bash
python3 semantic_versioning.py package.json --minor
```

### Bump the major version on line 3 only

```bash
python3 semantic_versioning.py pyproject.toml --major --line 3
```

### Bump recursively, only Markdown files

```bash
python3 semantic_versioning.py docs/ --recursive --include "*.md" --fix
```

### Dry run with full verbosity

```bash
python3 semantic_versioning.py src/ --recursive --dry-run -vvv
```

### CI gate: fail if any version is stale

```bash
python3 semantic_versioning.py . --recursive --check
```

## Exit Codes

| Code |                  Description                  |
|------|-----------------------------------------------|
|    0 | Success (or `--check` found no stale versions) |
|    1 | Error, or `--check` found stale versions      |
