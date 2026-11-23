---
name: create-python-script
description: Create a new self-contained Python CLI script following the pytools repository conventions (heel.py microframework, semantic coloring, handler pattern, CLI args, tests, specs, docs). Use when the user wants a new Python tool generated with the exact conventions used in this repository.
---

# Create a Python Script

Generate a new, self-contained Python CLI script for this repository. The script
MUST follow the conventions in `AGENTS.md` and the `heel.py` template exactly.
`heel.py` is a TEMPLATE for reference only — its classes are copied and
duplicated into each new script; it is NEVER imported.

Work collaboratively: provide the implementation expertise, while the user
supplies the script name, purpose, and confirms any unresolved design decisions.

## 1. Get the script intent

Ask the user (or read `$ARGUMENTS`) for:

- A hyphenated script name (e.g. `split-csv`, `history-chrome`). Use the name
  verb-first when it describes an action.
- A one-line description of what the script does.
- Any specific input/output behavior, processing rules, or edge cases.

Do not invent behavior. If the request is ambiguous, ask focused questions only
for the missing parts before writing code.

## 2. Explore the repository conventions

Before writing, re-read the canonical references so the output matches exactly:

- `heel.py` — the microframework template (Console, Logger, NullLogger,
  FileHandler, Kernel, App, Installer, completion generator).
- `AGENTS.md` — the repository rules (CLI args, semantic coloring, section
  separators, exit codes, tests, specs, docs, lint).
- One or two existing scripts (e.g. `history-chrome.py`) to match real style.

Copy the needed framework classes verbatim from `heel.py` into the new script.
Never import from `heel.py`. Each script is independent and self-contained.

## 3. Skeleton the script

Start every script with:

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
```

Then, in order, copy the classes the script needs (at minimum `Console` and the
handler/application layer). Use these section separators between logical blocks:

```text
#--------------------------------------------------
# Section title
#--------------------------------------------------
```

Do NOT add comments unless the user explicitly asks. Keep comments minimal.

### Required framework components to duplicate

- `Console` — static semantic coloring + alert blocks (copy the whole class).
- `Logger` / `NullLogger` — file+console logging with verbosity levels
  (0=error, 1=success, 2=warning, 3=info). Use `NullLogger` when no logging.
- `FileHandler` — base class with `walk_paths()` and `process_file()` hook.
- `Kernel` (or `App`) — dual-phase argparse entry point. Copy the early-args
  parser (`--log`, `-v`, `--quiet`, `--self-install`, `--self-uninstall`,
  `--completion`), the main parser, hero, completion generation, install/
  uninstall hooks.
- `Installer` (optional) — only if `--self-install`/`--self-uninstall` support is
  desired; the `Kernel` already wires it.

## 4. Implement the CLI

Use argparse with this parameter set and semantics (mirror `Kernel._build_parser`):

- `input` (positional) — file or directory to process.
- `--output` — output file or directory.
- `--recursive` — recursive directory traversal.
- `--include` / `--exclude` — glob filters.
- `--dry-run` — simulate without modifying anything.
- `--log` — print the current log file and stop.
- `--verbose`, `-v` — stackable verbosity (count: -v, -vv, -vvv).
- `--quiet` — suppress non-primary output; runtime errors exit 0 with no output.
- `--self-install` / `--self-uninstall` — install/uninstall actions.
- `--completion` — print bash completion script and exit.

Exit codes: `0` success, `1` runtime error, `2` invalid CLI usage. With
`--quiet`, runtime errors produce no output and return `0`; usage errors still
return `2`.

## 5. Implement the handler

Subclass `FileHandler`, override `process_file(self, path, *, output=None,
dry_run=False)`, and increment `self.files_processed += 1` for each file
actually processed (base `process_file` increments `files_skipped`). Use
`FileHandler.walk_paths()` for traversal. Wire it with:

```python
if __name__ == '__main__':
    app = Kernel(author='TangoMan75', title='...', description='...')
    app.run(MyHandler)
```

## 6. Apply style rules

- Standard library only; minimal comments; simple and readable.
- `snake_case` functions/variables, `PascalCase` classes, `UPPER_SNAKE` constants.
- Type hints on function params and returns; descriptive names. NEVER use
  `from __future__ import annotations`.
- Use `pathlib.Path`; specify `encoding='utf-8'` on file ops.
- Prefer explicit arguments; use keyword-only args in method overrides
  (`def process_file(self, path, *, output=None, dry_run=False)`).
- Raise specific exceptions (`ValueError`, `FileNotFoundError`).
- On network ops, wrap in try/except and `sys.exit(1)` on errors.
- ISO 8601 parsing: `datetime.fromisoformat()` rejects a trailing `Z` on Python
  3.10. Normalize with
  `iso_s = s[:-1] + "+00:00" if s[-1] in ("Z", "z") else s` before parsing.

### Semantic coloring

Use the local `Console` methods, never raw ANSI:
- `Console.success()` green, `Console.info()` magenta, `Console.warning()` yellow,
  `Console.danger()` red (errors to stderr), `Console.primary()`/`Console.secondary()`.
- Use `Console.alert_*()` boxed blocks (`alert_primary`, `alert_secondary`,
  `alert_success`, `alert_danger`, `alert_warning`, `alert_info`) for prominent output.

## 7. Generate supporting files

If the script adds user-facing functionality:

- Add/update `./specs/<name>.feature` in Gherkin describing behavior.
- Add/update `./docs/<name>.md` describing usage.
- Add `./tests/test_<name>.py` (underscore name) loading the script by path;
  include `./tests/fixtures/*.*` fixtures when needed. NEVER create backward-
  compatibility aliases for tests — refactor tests to the new structure.

## 8. Validate

Run, from the repo root:

- `python3 -m py_compile <name>.py` — must compile cleanly.
- `ruff check <name>.py` — must be clean.
- `python3 ./tests/test_<name>.py` — tests pass.

Fix any issues before reporting completion. Do not commit unless asked.

## 9. Report

Summarize the created file(s), the framework classes duplicated, the CLI
surface, and the validation results.
