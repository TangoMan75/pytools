# Agent Guidelines

## Template Conventions
All scripts MUST follow the conventions in `heel.py`:

> **CRITICAL RULE: NEVER import code from `heel.py`.** `heel.py` is a TEMPLATE
> for convention purposes only. Every Python script in this repository MUST be
> independent and self-contained. Copy and duplicate the code (`Console`,
> `Logger`, `FileHandler`, `Kernel`, ...) into the destination script when
> necessary.
>
> `heel.py` is not a runtime module and MUST NOT be installed, copied, or
> bundled as a dependency of another script. It is only an example/template
> showing repository conventions.

Section separators MUST use this format:
```text
#--------------------------------------------------
# Section title
#--------------------------------------------------
```

## CLI Arguments
- `input`: File or directory to process (positional argument)
- `--output`: Output file or directory
- `--recursive`: Enable recursive directory traversal
- `--include`: Include filter (glob pattern)
- `--exclude`: Exclude filter (glob pattern)
- `--dry-run`: Simulate actions without modifying anything
- `--verbose`, `-v`: Increase verbosity (stackable: -v, -vv, -vvv)
- `--quiet`: Suppress non-error output; runtime errors are still printed and exit `1`
- `--log`: Print the current log and stop when supported
- `--self-install`, `--self-uninstall`: Optional template-supported installation actions

Short options are long-only by default. The only common short option is `-v`;
`-h` is provided by `argparse`. `installer.py` uses subcommands (`install` and
`uninstall`) instead of flag-based actions.

CLI programs use exit code `0` for success, `1` for runtime errors, and `2` for
invalid command-line usage. `--quiet` suppresses non-error output only; runtime
errors are always printed to stderr and return exit code `1`. Command-line usage
errors still return `2`.

## Semantic Coloring
Use local `Console` class methods copied from the template:
- `Console.success()` - success messages (green)
- `Console.info()` - info messages (magenta)
- `Console.warning()` - warnings (yellow)
- `Console.danger()` - errors to stderr (red)
- `Console.primary()`, `Console.secondary()` - general output

## Alert Blocks
Use `Console.alert_*()` methods for box-styled output:
- `Console.alert_primary()`, `Console.alert_secondary()`
- `Console.alert_success()`, `Console.alert_danger()`
- `Console.alert_warning()`, `Console.alert_info()`

## File/Folder Handling
- All scripts accept either a single file OR a folder
- When a folder is provided, process every file in that folder
- Use `FileHandler.walk_paths()` for consistent traversal

## Installation Features
- Generate bash completion scripts automatically
- Add completion to shell rc files (~/.bashrc, ~/.zshrc)

## Framework Usage
**Philosophy**: Copy the needed components from `heel.py` into your script, then
`Subclass FileHandler → Override process_file() → Call app.run(MyHandler)`.

**Minimal Example** (self-contained — never import `heel.py`):
```python
#!/usr/bin/env python3
from pathlib import Path

# Copy the Console, FileHandler, Kernel classes from heel.py into this script.

class MyHandler(FileHandler):
    def process_file(self, path: Path, *, output=None, dry_run=False):
        Console.success(f"Processing {path}")
        self.files_processed += 1

if __name__ == '__main__':
    app = Kernel(author='YourName', title='My Tool', description='Does something')
    app.run(MyHandler)
```

**Core Components** (duplicate these into each script — do NOT import them):
- `Console`: Static methods for inline text and alert blocks (semantic coloring)
- `Logger`: File + console logging with verbosity levels (0=error, 1=success, 2=warning, 3=info)
- `NullLogger`: No-op fallback when logger not needed
- `FileHandler`: Base class with `walk_paths()` iterator and `process_file()` heel
- `App`: Entry point with dual-phase argument parsing (early args before required input)

**Key Patterns**:
- Verbosity levels: `-v` (1), `-vv` (2), `-vvv` (3)
- Counters: `self.files_processed += 1` after each file
- Optional logger: `self.logger = logger if logger is not None else NullLogger()`

## Framework Rules
- **Handler pattern**: Subclass `FileHandler`, implement `process_file()`, pass to `App.run()`
- **App instantiation**: Pass `author`, `title`, `description` to `App` constructor
- **No imports from `heel.py`**: copy and duplicate the needed classes into each script

## Project Rules
- **NEVER import from `heel.py`** - always copy and duplicate the needed code into each script
- **NEVER create backward compatibility aliases for tests** - always refactor tests to use the new class structure
- Update `./specs/*.feature` files when script functionality changes
- Use Gherkin syntax exclusively in `./specs/*.feature` files
- Update `./docs/*.md` files when script functionality changes
- Update `./tests/test*.py` files when script functionality changes
- Add `./tests/fixtures/*.*` fixture files when test requires them
- **ALWAYS update unit tests when making changes to the codebase**
- **ALWAYS run the linter after a change**

## Build/Lint/Test Commands
- **Run scripts**: `python3 script_name.py [args]` (for example, `python3 history-chrome.py --help`)
- **Python version**: 3.10+
- **Test**: `python3 ./tests/test_<tool_name>.py`
- **Lint**: `python3 -m py_compile <tool_name>.py`
- **Lint**: `ruff check <tool_name>.py`

The history tools use hyphenated executable names. Their tests use underscore
names for Python test discovery and load the scripts by path.

## Code Style Guidelines
- **General**: Standard library only, minimal comments, simple/readable
- **Avoid kwargs**: Prefer explicit arguments; use `# noqa: ARG001` if necessary
- **Keyword Arguments**: Pass keyword-only args in methods, avoid positional args
- **Imports**: stdlib → third-party → local; standard library first, one per line, grouped
- **Annotations**: Never use type annotations or `from __future__ import annotations`.
- **Naming**: snake_case functions/variables, PascalCase classes, UPPER_SNAKE constants
- **Types**: Use type hints for function parameters and return values, descriptive names
- **Error handling**: Raise specific exceptions (ValueError, FileNotFoundError)
- **File ops**: Use pathlib.Path; handle encoding explicitly (default utf-8)
- **Python 3.10 ISO parsing**: `datetime.fromisoformat()` rejects the trailing `Z`
  timezone suffix until Python 3.11. Normalize it to `+00:00` before parsing:
  `iso_s = s[:-1] + "+00:00" if s[-1] in ("Z", "z") else s`. CI runs 3.10, so any
  code parsing ISO 8601 input must handle `Z` explicitly or it will fail there.
- **CLI**: Use argparse with help text; follow existing parameter patterns
- **Shebang**: `#!/usr/bin/env python3`
- **Structure**: `if __name__ == "__main__": main()`
- **Formatting**: 4 spaces, <100 chars, UTF-8 shebang
- **Error handling**: try/except for network ops, sys.exit(1) on errors
