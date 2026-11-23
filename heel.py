#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Heel: A Minimal dependency-free single-file CLI microframework for Python scripts.
"""

import argparse
import datetime
import json
import re
import shlex
import sys
import unicodedata
from pathlib import Path

#--------------------------------------------------
# Cache: file-based caching with TTL
#--------------------------------------------------


class Cache:
    """File-based caching with configurable TTL.

    When installed (running from ~/.local/share/TangoMan75/),
    uses ~/.cache/TangoMan75/<name>/; otherwise uses ./cache/.
    """

    def __init__(self, *, name, ttl=None):
        script_dir = Path(__file__).resolve().parent
        if str(script_dir).startswith(str(Path.home() / ".local" / "share" / "TangoMan75")):
            self.cache_dir = Path.home() / ".cache" / "TangoMan75" / name
        else:
            self.cache_dir = script_dir / "cache" / name
        self.ttl = ttl or datetime.timedelta(days=1)

    def _cache_path(self, request):
        """Return the cache file path for a given request name."""
        stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        return self.cache_dir / f"{stamp}_{request}.json"

    def read(self, request):
        """Return cached data if fresh, else None."""
        if not self.cache_dir.exists():
            return None
        prefix = f"{request}.json"
        for path in sorted(self.cache_dir.glob(f"*_{prefix}"), reverse=True):
            try:
                stamp = path.stem.rsplit("_", 1)[0]
                cached_at = datetime.datetime.strptime(stamp, "%Y-%m-%d_%H-%M-%S")
                if datetime.datetime.now() - cached_at > self.ttl:
                    return None
                return json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, json.JSONDecodeError, OSError):
                continue
        return None

    def write(self, request, *, data):
        """Write data to the cache file."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self._cache_path(request)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

#--------------------------------------------------
# Console: Semantic console output
#--------------------------------------------------


class Console:
    """Console output with semantic coloring and alert blocks."""

    quiet = False

    ALERT_PRIMARY = "\033[1;104;97m"
    ALERT_SECONDARY = "\033[1;45;97m"
    ALERT_SUCCESS = "\033[1;42;97m"
    ALERT_DANGER = "\033[1;41;97m"
    ALERT_WARNING = "\033[1;43;97m"
    ALERT_INFO = "\033[1;44;97m"
    ALERT_LIGHT = "\033[1;47;90m"
    ALERT_DARK = "\033[1;40;37m"

    PRIMARY = "\033[97m"
    SECONDARY = "\033[94m"
    SUCCESS = "\033[32m"
    DANGER = "\033[31m"
    WARNING = "\033[33m"
    INFO = "\033[95m"
    LIGHT = "\033[47;90m"
    DARK = "\033[40;37m"
    DEFAULT = "\033[0m"
    EOL = "\033[0m\n"

    @staticmethod
    def _pad_and_indent(text, *, indent=0, padding=0):
        """Return (indentation, text, padding)"""
        pad = max(0, padding - len(text))
        return " " * indent, text, " " * pad

    @staticmethod
    def _alert_block(color, *, text):
        text = " ".join(str(text).splitlines())[:63]
        top = f"{Console.EOL}{color}{'':>64}{Console.EOL}"
        middle = f"{color} {text:<63}{Console.EOL}"
        bottom = f"{color}{'':>64}{Console.EOL}\n"
        print(top + middle + bottom, end='')

    @staticmethod
    def alert_primary(text):
        """Print primary alert block."""
        Console._alert_block(Console.ALERT_PRIMARY, text=text)

    @staticmethod
    def alert_secondary(text):
        """Print secondary alert block."""
        Console._alert_block(Console.ALERT_SECONDARY, text=text)

    @staticmethod
    def alert_success(text):
        """Print success alert block."""
        Console._alert_block(Console.ALERT_SUCCESS, text=text)

    @staticmethod
    def alert_danger(text):
        """Print danger alert block."""
        Console._alert_block(Console.ALERT_DANGER, text=text)

    @staticmethod
    def alert_warning(text):
        """Print warning alert block."""
        Console._alert_block(Console.ALERT_WARNING, text=text)

    @staticmethod
    def alert_info(text):
        """Print info alert block."""
        Console._alert_block(Console.ALERT_INFO, text=text)

    @staticmethod
    def alert_light(text):
        """Print light alert block."""
        Console._alert_block(Console.ALERT_LIGHT, text=text)

    @staticmethod
    def alert_dark(text):
        """Print dark alert block."""
        Console._alert_block(Console.ALERT_DARK, text=text)

    @staticmethod
    def primary(text, *, indent=0, padding=0):
        """Print text in primary color."""
        i, t, p = Console._pad_and_indent(text, indent=indent, padding=padding)
        print(f"{i}{Console.PRIMARY}{t}{Console.DEFAULT}{p}", end='')

    @staticmethod
    def secondary(text, *, indent=0, padding=0):
        """Print text in secondary color."""
        i, t, p = Console._pad_and_indent(text, indent=indent, padding=padding)
        print(f"{i}{Console.SECONDARY}{t}{Console.DEFAULT}{p}", end='')

    @staticmethod
    def success(text, *, indent=0, padding=0):
        """Print text in success color."""
        i, t, p = Console._pad_and_indent(text, indent=indent, padding=padding)
        print(f"{i}{Console.SUCCESS}{t}{Console.DEFAULT}{p}", end='')

    @staticmethod
    def danger(text, *, indent=0, padding=0):
        """Print text in danger color."""
        i, t, p = Console._pad_and_indent(text, indent=indent, padding=padding)
        print(f"{i}{Console.DANGER}{t}{Console.DEFAULT}{p}", end='')

    @staticmethod
    def warning(text, *, indent=0, padding=0):
        """Print text in warning color."""
        i, t, p = Console._pad_and_indent(text, indent=indent, padding=padding)
        print(f"{i}{Console.WARNING}{t}{Console.DEFAULT}{p}", end='')

    @staticmethod
    def info(text, *, indent=0, padding=0):
        """Print text in info color."""
        i, t, p = Console._pad_and_indent(text, indent=indent, padding=padding)
        print(f"{i}{Console.INFO}{t}{Console.DEFAULT}{p}", end='')

    @staticmethod
    def light(text, *, indent=0, padding=0):
        """Print text in light color."""
        i, t, p = Console._pad_and_indent(text, indent=indent, padding=padding)
        print(f"{i}{Console.LIGHT}{t}{Console.DEFAULT}{p}", end='')

    @staticmethod
    def dark(text, *, indent=0, padding=0):
        """Print text in dark color."""
        i, t, p = Console._pad_and_indent(text, indent=indent, padding=padding)
        print(f"{i}{Console.DARK}{t}{Console.DEFAULT}{p}", end='')

    @staticmethod
    def error(message):
        """Print error message to stderr."""
        print(f"{Console.DANGER}error: {message}{Console.DEFAULT}", file=sys.stderr)

#--------------------------------------------------
# String: strign operations utility class
#--------------------------------------------------


class String:
    """Utility class for string operations."""

    @staticmethod
    def slugify(value):
        """Convert a string to a URL-friendly slug."""
        value = str(value)
        value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
        value = re.sub(r'[^a-zA-Z0-9\s-]', '', value).strip().lower()
        value = re.sub(r'[-\s]+', '-', value)
        return value

#--------------------------------------------------
# Logger: file logging and output
#--------------------------------------------------


class Logger:
    """Log messages to file and console based on verbosity"""

    def __init__(self, *, verbose=0, script_file=None, quiet=False):
        self.verbose = verbose
        self.quiet = quiet
        self.script_file = script_file or Path(sys.argv[0]).resolve()
        self.script_dir = self.script_file.parent
        self.name = self.script_file.stem
        self.log_dir = self.script_dir / 'log'
        self.log_file = self.log_dir / f"{datetime.date.today().isoformat()}_{self.name}.log"

    def print(self):
        """Print the log file contents to stdout and return whether it exists."""
        if self.log_file.exists():
            if self.verbose > 0:
                Console.info(f"{self.log_file}\n")
            print(self.log_file.read_text(encoding='utf-8'), end='')
            return True
        Console.error(f"\"{self.log_file}\" file not found.")
        return False

    def log(self, message, *, loglevel=0):
        """Log message to file and console with appropriate coloring."""
        self.log_dir.mkdir(parents=True, exist_ok=True)
        level = 'ERROR' if loglevel == 0 else 'SUCCESS' if loglevel == 1 else 'WARNING' if loglevel == 2 else 'INFO'
        timestamp = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f')
        line = f"{timestamp} {level} {message}"
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        if loglevel == 0:
            Console.danger(f"{message}\n")
        elif not self.quiet and self.verbose >= loglevel:
            if loglevel == 1:
                Console.success(f"{message}\n")
            elif loglevel == 2:
                Console.warning(f"{message}\n")
            else:
                Console.info(f"{message}\n")

    def info(self, message):
        """Log info message."""
        self.log(message, loglevel=3)

    def warning(self, message):
        """Log warning message."""
        self.log(message, loglevel=2)

    def success(self, message):
        """Log success message."""
        self.log(message, loglevel=1)

    def danger(self, message):
        """Log danger/error message."""
        self.log(message, loglevel=0)


class NullLogger:
    def __init__(self, *, verbose=0, quiet=False):
        self.verbose = verbose
        self.quiet = quiet

    def __getattr__(self, name):
        return lambda *a, **k: None


#--------------------------------------------------
# Completion: bash completion script generator
#--------------------------------------------------


class Completion:
    """Bash completion script generator."""

    @staticmethod
    def classify_parser_actions(*, arg_parser):
        """Walk the parser actions and return ``(all_opts, categories)``."""
        all_opts = set()
        categories = {"boolean": [], "verbose": [], "file": [], "glob": []}
        file_keys = ("output", "file", "path", "dest")
        glob_keys = ("include", "exclude", "glob", "pattern")
        for action in arg_parser._actions:  # noqa: SLF001
            opts = action.option_strings
            if not opts:
                continue
            all_opts.update(opts)
            joined = " ".join(opts).lower()
            if action.nargs == 0 and action.const is True:
                categories["boolean"].extend(opts)
            if action.__class__.__name__ == "_CountAction":
                categories["verbose"].extend(opts)
            if any(key in joined for key in file_keys):
                categories["file"].extend(opts)
            if any(key in joined for key in glob_keys):
                categories["glob"].extend(opts)
        return all_opts, categories

    @staticmethod
    def render_completion_case(*, opt, kind):
        """Return the bash case branch for the given option kind."""
        bodies = {
            "boolean": "            COMPREPLY=()\n",
            "verbose": "            COMPREPLY=( $(compgen -W \"-v -vv -vvv\" -- \"${cur}\") )\n",
            "file": "            COMPREPLY=( $(compgen -f -- \"${cur}\") )\n",
            "glob": "            COMPREPLY=( $(compgen -G \"${cur}*\") )\n",
        }
        return f"        {opt})\n{bodies[kind]}            return 0\n            ;;\n"

    @staticmethod
    def render_completion_script(*, all_opts, categories, name):
        """Build the final bash completion script string."""
        blocks = []
        for kind, opts in categories.items():
            for opt in sorted(set(opts)):
                blocks.append(Completion.render_completion_case(opt=opt, kind=kind))
        option_case = "".join(blocks)
        completion_name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
        sorted_opts = sorted(all_opts, key=lambda o: (not o.startswith("--"), o.lower()))
        opts_str = " ".join(sorted_opts)
        return f'''#!/bin/bash

_{completion_name}_completions()
{{
    local cur prev opts
    COMPREPLY=()
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"

    opts="{opts_str}"

    case "${{prev}}" in
{option_case}        *)
            COMPREPLY=( $(compgen -W "${{opts}}" -- "${{cur}}") )
            return 0
            ;;
    esac
}}

complete -f -F _{completion_name}_completions {shlex.quote(name)}
'''

    @staticmethod
    def generate(*, parser, name):
        """Return a bash completion script string for the given argparse parser."""
        all_opts, categories = Completion.classify_parser_actions(arg_parser=parser)
        return Completion.render_completion_script(
            all_opts=all_opts,
            categories=categories,
            name=name,
        )

#--------------------------------------------------
# FileHandler: base class for business logic
#--------------------------------------------------


class FileHandler:
    """Base class to extend with your own processing logic."""

    def __init__(self, *, logger=None):
        self.logger = logger if logger is not None else NullLogger()
        self.files_processed = 0
        self.files_skipped = 0

    @staticmethod
    def walk_paths(input_path, *, recursive=False, include=None, exclude=None):
        """Yield file paths from input, optionally filtered and recursively."""
        path = Path(input_path)

        if not path.exists():
            raise FileNotFoundError(f"input path not found: {path}")

        if path.is_file():
            if (not include or path.match(include)) and (not exclude or not path.match(exclude)):
                yield path
            return

        iterator = path.rglob("*") if recursive else path.glob("*")

        for p in sorted(iterator):
            if not p.is_file():
                continue
            if include and not p.match(include):
                continue
            if exclude and p.match(exclude):
                continue
            yield p

    @staticmethod
    def get_unique_filename(path, *, base_filename):
        """Generate a unique filename if one already exists."""
        directory = path if path.is_dir() else path.parent
        base_path = Path(base_filename)
        filepath = directory / base_path.name
        counter = 1
        while filepath.exists():
            filepath = directory / f"{base_path.stem}_{counter}{base_path.suffix}"
            counter += 1
        return filepath

    def process_file(self, path, *, output=None, dry_run=False):
        """Process a single file."""
        self.files_skipped += 1

    def process_directory(self, path, *, output=None, recursive=False, include=None, exclude=None, dry_run=False):
        """Process a directory."""
        for file_path in self.walk_paths(path, recursive=recursive, include=include, exclude=exclude):
            self.process_file(file_path, output=output, dry_run=dry_run)

#--------------------------------------------------
# Kernel
#--------------------------------------------------


class Kernel:
    """CLI application with metadata and execution."""

    def __init__(self, *, author, title, description):
        self.author = author
        self.title = title
        self.description = description
        self.script_file = Path(sys.argv[0]).resolve()
        self.name = self.script_file.stem
        self.install_dir = Path.home() / f".local/share/{self.author}" / self.name
        self.destination_file = self.install_dir / self.script_file.name
        self.completion_file = self.install_dir / f"{self.name}-completion.sh"
        self.bin_dir = Path.home() / '.local/bin'
        self.symlink_path = self.bin_dir / self.name
        self.quiet = False
        self.logger = None
        self.args = None

    def build_early_parser(self):
        """Build parser for early arguments (before required input)."""
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument('--log', action='store_true')
        parser.add_argument('--verbose', '-v', action='count', default=0)
        parser.add_argument('--quiet', action='store_true', help='Suppress non-error output; runtime errors are still reported')
        parser.add_argument('--completion', action='store_true', help='Print bash completion script to stdout and exit')
        return parser

    def build_parser(self):
        """Build and return argument parser."""
        parser = argparse.ArgumentParser(description=self.description)
        parser.add_argument('input', help='File or directory to process')
        parser.add_argument('--output', help='Output file or directory')
        parser.add_argument('--recursive', action='store_true', help='Enable recursive directory traversal')
        parser.add_argument('--include', help='Include filter (glob pattern)')
        parser.add_argument('--exclude', help='Exclude filter (glob pattern)')
        parser.add_argument('--dry-run', action='store_true', help='Simulate actions without modifying anything')
        parser.add_argument('--log', action='store_true', help='Output log file to terminal')
        parser.add_argument('--verbose', '-v', action='count', default=0, help='Increase verbosity (stackable)')
        parser.add_argument('--quiet', action='store_true', help='Suppress non-error output; runtime errors are still reported')
        parser.add_argument('--completion', action='store_true', help='Print bash completion script to stdout and exit')
        return parser

    def hero(self):
        """Print hero to the terminal."""
        Console.alert_primary(self.title)

    def generate_completion(self):
        """Return the bash completion script for this script."""
        return Completion.generate(parser=self.build_parser(), name=self.name)

    def _handle_early_arguments(self):
        """Handle options that must run before the required input is parsed."""
        early_args, _ = self.build_early_parser().parse_known_args()
        self.quiet = early_args.quiet
        Console.quiet = early_args.quiet
        self.logger = Logger(
            verbose=early_args.verbose,
            script_file=self.script_file,
            quiet=early_args.quiet,
        )

        if not self.quiet and early_args.verbose >= 1:
            self.hero()

        if early_args.completion:
            print(self.generate_completion())
            return True

        if early_args.log:
            self.logger.print()
            return True
        return False

    def _configure_handler(self, handler):
        """Apply application-specific arguments to a handler."""

    def run(self, handler_class=None):
        """Run the application with the given handler class.

        Walks paths from the parsed ``input`` argument and invokes
        ``handler.process_file()`` for each file. If no handler is provided
        the base :class:`FileHandler` is used, which only walks paths without
        processing them.
        """
        if self._handle_early_arguments():
            return

        self.args = self.build_parser().parse_args()

        if handler_class is None:
            handler_class = FileHandler
        handler = handler_class(logger=self.logger)
        self._configure_handler(handler)

        try:
            file_paths = handler.walk_paths(
                self.args.input,
                recursive=self.args.recursive,
                include=self.args.include,
                exclude=self.args.exclude,
            )
            for file_path in file_paths:
                self.logger.info(f"Processing {file_path}")
                handler.process_file(
                    file_path,
                    output=self.args.output,
                    dry_run=self.args.dry_run,
                )
        except FileNotFoundError as err:
            Console.error(str(err))
            sys.exit(1)

        if handler.files_processed > 0:
            self.logger.success(f"Processed {handler.files_processed} files")
        else:
            self.logger.warning("Processed 0 files")
        if handler.files_skipped > 0:
            self.logger.warning(f"Skipped {handler.files_skipped} files")

#--------------------------------------------------
# App
#--------------------------------------------------


class App(Kernel):
    """Prints a list of files"""

    def build_parser(self):
        """Build and return argument parser with extra options."""
        parser = super().build_parser()
        parser.add_argument('--detail', action='store_true', help='Print detailed list')
        return parser

    def run(self, handler_class=None):
        """Execute the application, defaulting to the example file lister."""
        if handler_class is None:
            handler_class = FileLister
        super().run(handler_class)

    def _configure_handler(self, handler):
        """Apply App-specific parsed options to a handler."""
        handler.detail = self.args.detail


class FileLister(FileHandler):
    """List files and output to YYYY-MM-DD_list.txt"""

    def __init__(self, *, logger=None):
        super().__init__(logger=logger)
        self.detail = False

    def process_file(self, path, *, output=None, dry_run=False):
        """List files and output to YYYY-MM-DD_list.txt"""
        if output:
            output_path = Path(output)
        else:
            today = datetime.date.today().isoformat()
            output_path = Path(f"{today}_list.txt")

        if output_path.exists() and output_path.is_dir():
            output_path /= f"{datetime.date.today().isoformat()}_list.txt"

        if dry_run:
            self.logger.info(f"[DRY RUN] Would append: {output_path}")
            self.files_processed += 1
            return

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "a", encoding="utf-8") as f:
            if self.detail:
                f.write(f"{path}\n")
            else:
                f.write(f"{path.name}\n")

        self.files_processed += 1


if __name__ == '__main__':
    app = App(
        author='TangoMan75',
        title='TangoMan CLI microframework example',
        description='Prints a list of files',
    )
    app.run()
