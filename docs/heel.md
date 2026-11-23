# Heel

A minimal dependency-free single-file CLI microframework for Python scripts.

## Usage

Subclass `FileHandler` and pass it to `Kernel.run()`:

```python
from heel import FileHandler, Kernel

class MyHandler(FileHandler):
    def process_file(self, path, *, output=None, dry_run=False):
        # Your logic here
        pass

if __name__ == "__main__":
    Kernel(author="Author", title="Title", description="Description").run(MyHandler)
```

## Features

- **Colors**: Primary, Secondary, Success, Danger, Warning, Info, Light, Dark
- **Console output**: semantic color methods and alert blocks
- **Alert blocks**: `alert_primary()`, `alert_success()`, `alert_danger()`, etc.
- **File walking**: `walk_paths()` with include/exclude filters
- **Self-describing completion**: every script owns a `--completion` flag

## CLI Arguments

|         Flag        |                   Description                   |
|---------------------|-------------------------------------------------|
| `input`             | File or directory to process (required)         |
| `--output`          | Output file or directory                        |
| `--recursive`       | Enable recursive directory traversal            |
| `--include`         | Include filter (glob pattern)                   |
| `--exclude`         | Exclude filter (glob pattern)                   |
| `--dry-run`         | Simulate actions without modifying anything     |
| `--log`             | Print today's log and stop                      |
| `-v`, `--verbose`   | Increase verbosity (stackable: -v, -vv, -vvv)   |
| `--quiet`           | Suppress non-error output; runtime errors are still reported |
| `--completion`        | Print the bash completion script to stdout and exit |

Heel requires Python 3.10 or newer and uses only the standard library.
Missing input paths fail with an error. Installation and log-display actions
complete before the required positional input is parsed.

## Installer Wrapper

`installer.py` provides a short form for the self-installation actions. Pass the
Python script and choose an action:

```bash
./installer.py install path/to/script.py
./installer.py uninstall path/to/script.py
```

Multiple scripts can be installed or uninstalled in a single command:

```bash
./installer.py install path/to/one.py path/to/two.py
```

The `-g`/`--global` flag installs the symlink to `/usr/bin` (requires root).
The uninstall command cleans symlinks from both `~/.local/bin` and `/usr/bin`
regardless of the `-g` flag, only removing symlinks that point to the script
being removed. The wrapper performs the installation directly, so the target
script does not need to implement `--self-install` or `--self-uninstall`. It
uses the same installation paths, symlink, and shell-completion handling as
Heel itself. It does not install `heel.py`; that file is a conventions
template, not a runtime module. Installation actions are reported verbosely in
the terminal by default.

### Completion generation

Each script generates its own bash completion script from its own argument
parser. Running a script with `--completion` prints that completion script to
stdout, so the options listed always match the script's real signature
(`--output` completes files, `--include`/`--exclude` complete globs, boolean
flags complete nothing, and `-v`/`--verbose` complete `-v -vv -vvv`).

`installer.py` delegates to the target: it runs `<script> --completion` after
copying the script and writes the output to `<name>-completion.sh`. If the
target does not support `--completion` (non-zero exit or output that is not a
bash completion script), `installer.py` warns and skips completion instead of
writing a broken file.
