![GH language](https://img.shields.io/github/languages/top/TangoMan75/pytools)
[![GH release](https://img.shields.io/github/v/release/TangoMan75/pytools)](https://github.com/TangoMan75/pytools/releases)
![GH license](https://img.shields.io/github/license/TangoMan75/pytools)
![GH stars](https://img.shields.io/github/stars/TangoMan75/pytools)
[![CI Status](https://github.com/TangoMan75/pytools/workflows/Python/badge.svg)](https://github.com/TangoMan75/pytools/actions/workflows/python.yml)
![Visitors](https://api.visitorbadge.io/api/visitors?path=https%3A%2F%2Fgithub.com%2FTangoMan75%2Fpytools&labelColor=%23697689&countColor=%2337d67a&style=flat)

👠 TangoMan Heel Microframework
===============================

CLI Micro-Framework
--------------------

A minimal dependency-free single-file CLI microframework for Python scripts

📚 Extra Documentation
----------------------

Documentation can be found here :

- [[Documentation](./docs)](https://tangoman75.github.io/pytools/docs)

## Tools

Every script is standalone and self-contained. All of them share the same CLI contract, so `--help`, `--verbose`, `--quiet`, and `--completion` work everywhere. Each tool has matching documentation in [`docs/`](./docs).

|                 Category                 |                                                                Tools                                                                 |
|------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------|
| [Framework](#-framework)                 | `heel.py`, `installer.py`                                                                                                            |
| [Google Workspace](#-google-workspace)   | `gcal.py`, `gcontacts.py`, `gmail.py`, `gtasks.py`                                                                                   |
| [Format Conversion](#-format-conversion) | `conv-ics.py`, `conv-sql.py`                                                                                                         |
| [Markdown](#-markdown)                   | `md-category-tags.py`, `md-convert-setext-to-atx.py`, `md-front-matter.py`, `md-join.py`, `md-rename.py`, `md-split.py`, `md-toc.py` |
| [History](#-history)                     | `bookmarks.py`, `history-backlog.py`, `history-chrome.py`, `history-opencode.py`, `history-terminal.py`, `history-zeroclaw.py`       |
| [Productivity](#-productivity)           | `calendar_generator.py`, `jira-rest.py`, `models.py`, `moments.py`, `ovhcloud.py`, `semantic_versioning.py`                          |

### 🔧 Framework

#### `heel.py` — Framework template

The canonical example every script is built from. It prints a list of files and demonstrates the `Console`, `Logger`, `FileHandler`, and `Kernel` components.

> **Never import `heel.py`.** It is a template only; copy the needed classes
> into each new script.

```bash
python3 heel.py . --recursive --include '*.py' --detail
```

#### `installer.py` — Installer

Installs scripts into `~/.local/share/TangoMan75` and symlinks them into `~/.local/bin`, without requiring `--self-install` support in the target script.

```bash
./installer.py install -vvv md-toc.py moments.py
./installer.py uninstall -vvv md-toc.py moments.py
```

### 📅 Google Workspace

These wrappers call the external [`gws`](https://github.com/googleworkspace/cli) command-line tool. `gcal.py` also accepts a public iCal (`.ics`) feed URL and parses it directly, without `gws`.

|      Tool      |                        Description                         |             Docs            |
|----------------|------------------------------------------------------------|-----------------------------|
| `gcal.py`      | List Google Calendar events in a date window               | [docs](./docs/gcal.md)      |
| `gcontacts.py` | List, search, create, update, and delete Google Contacts   | [docs](./docs/gcontacts.md) |
| `gmail.py`     | List or read Gmail messages with date/sender/label filters | [docs](./docs/gmail.md)     |
| `gtasks.py`    | List, filter, and create Google Tasks                      | [docs](./docs/gtasks.md)    |

```bash
python3 gcal.py --start 2026-11-01 --end 2026-11-30 --md
python3 gcontacts.py --search "Jane Doe" --md
python3 gmail.py --start 2026-11-01 --from boss@example.com --md
python3 gtasks.py --list Personal --due --md
```

### 🔄 Format Conversion

|        Tool       |                       Description                       |              Docs              |
|-------------------|---------------------------------------------------------|--------------------------------|
| `conv-ics.py`     | Convert iCalendar (`.ics`) to/from CSV or TSV           | [docs](./docs/conv-ics.md)     |
| `conv-sql.py`     | Convert SQL `INSERT` statements to CSV                  | [docs](./docs/conv-sql.md)     |

```bash
python3 conv-ics.py calendar.ics --output calendar.csv
python3 conv-sql.py dump.sql --output dump.csv
```

### 📝 Markdown

|              Tool             |                        Description                        |                    Docs                    |
|-------------------------------|-----------------------------------------------------------|--------------------------------------------|
| `md-category-tags.py`         | Add category tags from `YYYY-MM-DD_category.md` filenames | [docs](./docs/md-category-tags.md)         |
| `md-convert-setext-to-atx.py` | Convert setext headings to ATX (`#`) headings             | [docs](./docs/md-convert-setext-to-atx.md) |
| `md-front-matter.py`          | Add or update YAML front matter                           | [docs](./docs/md-front-matter.md)          |
| `md-join.py`                  | Concatenate markdown files, stripping front matter        | [docs](./docs/md-join.md)                  |
| `md-rename.py`                | Rename files from front matter date, title, and author    | [docs](./docs/md-rename.md)                |
| `md-split.py`                 | Split a document into files at each H2 section            | [docs](./docs/md-split.md)                 |
| `md-toc.py`                   | Generate or insert a table of contents                    | [docs](./docs/md-toc.md)                   |

```bash
python3 md-front-matter.py ./notes --recursive --author "Jane Doe"
python3 md-toc.py document.md --insert
python3 md-rename.py ./posts --recursive --dry-run
```

### 🕘 History

|          Tool         |                        Description                        |                Docs                |
|-----------------------|-----------------------------------------------------------|------------------------------------|
| `bookmarks.py`        | Read Chrome bookmarks as JSON, Markdown, or Netscape HTML | [docs](./docs/bookmarks.md)        |
| `history-backlog.py`  | Index dated markdown backlog files by date range          | [docs](./docs/history-backlog.md)  |
| `history-chrome.py`   | Report Chrome browsing history                            | [docs](./docs/history-chrome.md)   |
| `history-opencode.py` | Report OpenCode sessions and messages                     | [docs](./docs/history-opencode.md) |
| `history-terminal.py` | Report shell history across sessions                      | [docs](./docs/history-terminal.md) |
| `history-zeroclaw.py` | Report ZeroClaw sessions and chat messages                | [docs](./docs/history-zeroclaw.md) |

```bash
python3 history-chrome.py --start 2026-11-01 --md
python3 history-terminal.py --start 2026-11-20 --md
python3 history-opencode.py --start 2026-11-01 --md
python3 bookmarks.py --md --start 2026-11-01
```

### 🛠️ Productivity

|           Tool           |                        Description                        |                  Docs                 |
|--------------------------|-----------------------------------------------------------|---------------------------------------|
| `calendar_generator.py`  | Generate Google Calendar CSV slots (CLI or `--gui`)       | [docs](./docs/calendar_generator.md)  |
| `jira-rest.py`           | Fetch and update Jira Cloud tickets via REST              | [docs](./docs/jira-rest.md)           |
| `models.py`              | Recommend OpenCode models by cost, value, or quality      | [docs](./docs/models.md)              |
| `moments.py`             | Date parsing, formatting, timezone, and arithmetic helper | [docs](./docs/moments.md)             |
| `ovhcloud.py`            | Show current OVHcloud TLD creation and renewal prices     | [docs](./docs/ovhcloud.md)            |
| `semantic_versioning.py` | Auto-increment semver numbers in text files               | [docs](./docs/semantic_versioning.md) |

```bash
python3 calendar_generator.py --start 2026-12-01 --end 2026-12-31
python3 jira-rest.py read PROJ-123
python3 models.py --value --limit 15
python3 moments.py --short --day -3
python3 semantic_versioning.py version.txt --minor
```

🚀 Features
-----------

### ⚡ Core Features

1. **Console Output:** Semantic coloring with inline text and alert blocks
2. **File Logging:** File + console logging with verbosity levels (0-3)
3. **Path Handling:** Static path iterator with glob patterns support
4. **Zero Dependencies:** Standard library only, Python 3.10+

### ⚡ CLI Features

1. **Bash Completion:** `--completion` prints a ready-to-source completion script
2. **Common options:** Help, verbosity, output, traversal, filtering, dry-run, and logging
3. **Consistent exit codes:** `0` success, `1` runtime error, `2` usage error

📦 Installation
---------------

1. **Clone repository:** `git clone https://github.com/TangoMan75/pytools.git`
2. **Navigate to project:** `cd pytools`
3. **Run template:** `python3 heel.py --help`
4. **Optional — install on the system:** `./install.sh` (wraps `installer.py`)

🛠️ Usage
--------

```python
#!/usr/bin/env python3
from pathlib import Path

# Copy Console, Logger, FileHandler and Kernel from heel.py — never import heel.py.

class MyHandler(FileHandler):
    def process_file(self, path: Path, *, output=None, dry_run=False):
        Console.success(f"Processing {path}")
        self.files_processed += 1

if __name__ == '__main__':
    app = Kernel(author='TangoMan75', title='My Tool', description='Does something')
    app.run(MyHandler)
```

CLI Arguments:
- `input`: File or directory to process (positional)
- `--output`: Output file or directory
- `--recursive`: Enable recursive directory traversal
- `--include`: Include filter (glob pattern)
- `--exclude`: Exclude filter (glob pattern)
- `--dry-run`: Simulate actions without modifying
- `--verbose`, `-v`: Increase verbosity (`-v`, `-vv`, `-vvv`)
- `--quiet`: Suppress non-error output
- `--log`: Print the current log and stop
- `--completion`: Print a bash completion script and exit

🛠️ Dependencies / Requirements
------------------------------

1. Python 3.10+
2. `PyYAML` for `md-front-matter.py`, `md-rename.py`, and `md-split.py` (`pip install -r requirements.txt`)
3. [`gws`](https://github.com/googleworkspace/cli) for `gcal.py`, `gcontacts.py`, `gmail.py`, and `gtasks.py`
4. Optional `tkinter` + `tkcalendar` for `calendar_generator.py --gui`
5. Network access for `models.py` and `ovhcloud.py`
6. An Atlassian API token in `.env` for `jira-rest.py` (`python3 jira-rest.py init`)

🐞 Troubleshoot
---------------

1. **ImportError:** Ensure you're running from the project directory
2. **Permission denied:** Check file permissions on script execution
3. **`gws` not found:** Install `gws` and confirm it is on your `PATH`
4. **Empty history output:** Check the date window and the database path (`--db`)

🧪 Testing Strategy
-------------------

1. **Run the full suite:** `./entrypoint.sh tests`
2. **Single unit test:** `python3 ./tests/test_md_toc.py`
3. **Syntax check:** `python3 -m py_compile md-toc.py`
4. **Lint:** `ruff check md-toc.py`

🐛 Limitations
--------------

1. ⚠️ **No Windows support:** Shell completion targets bash/zsh only
2. ⚠️ **Single-file design:** Not suitable for large projects requiring multiple modules
3. ⚠️ **No built-in config:** All settings must be CLI arguments
4. ⚠️ **Local data only:** History tools read local SQLite/JSON files and do not sync

📝 Notes
--------

- Framework philosophy: Subclass FileHandler → Override process_file() → Call app.run(MyHandler)
- Verbosity levels: 0=error, 1=success, 2=warning, 3=info
- Use pathlib.Path for all file operations
- Each script duplicates its framework code; never import from `heel.py`

🤝 Contributing
---------------

Thank you for your interest in contributing to **pytools**

Please review the [code of conduct](./CODE_OF_CONDUCT.md) and [contribution guidelines](./CONTRIBUTING.md) before starting to work on any features

If you want to open an issue, please check first if it was not [reported already](https://github.com/TangoMan75/pytools/issues) before creating a new one

📜 License
----------

Copyrights (c) 2026 "Matthias Morin" &lt;mat@tangoman.io&gt;

[![License](https://img.shields.io/badge/Licence-MIT-green.svg)](LICENSE)
Distributed under the MIT license

If you like **pytools** please star, follow or tweet:

[![GitHub stars](https://img.shields.io/github/stars/TangoMan75/pytools?style=social)](https://github.com/TangoMan75/pytools/stargazers)
[![GitHub followers](https://img.shields.io/github/followers/TangoMan75?style=social)](https://github.com/TangoMan75)
[![Twitter](https://img.shields.io/twitter/url?style=social&url=https%3A%2F%2Fgithub.com%2FTangoMan75%2Fpytools)](https://twitter.com/intent/tweet?text=Wow:&url=https%3A%2F%2Fgithub.com%2FTangoMan75%2Fpytools)

🙏 Acknowledgements
-------------------

- **Python Standard Library:** For providing all required modules
- **argparse:** For CLI argument parsing
- **pathlib:** For object-oriented file path handling

👋 Let's Build Your Next Project Together !
-------------------------------------------

Clean code. Clear communication

From first sketch to final launch, I've got your back

[![tangoman.io](https://img.shields.io/badge/✉️%20Get%20in%20touch%20now%20!-FD9400?style=for-the-badge)](https://tangoman.io)
