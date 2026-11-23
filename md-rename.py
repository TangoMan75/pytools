#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Rename markdown files based on front matter (date, title, author).

Usage:
    python3 md-rename.py <directory> [-r]
"""

import argparse
import re
import shlex
import sys
import unicodedata
from pathlib import Path

#--------------------------------------------------
# Console: semantic output
#--------------------------------------------------


class Console:
    """Console output with semantic message types."""

    @staticmethod
    def info(message):
        """Print an informational message."""
        print(message)

    @staticmethod
    def success(message):
        """Print a success message."""
        print(message)

    @staticmethod
    def warning(message):
        """Print a warning message."""
        print(message)

    @staticmethod
    def danger(message):
        """Print an error message to stderr."""
        print(message, file=sys.stderr)


class Logger:
    """Console logger honoring the quiet flag."""

    def __init__(self, *, quiet=False):
        self._quiet = quiet

    def info(self, message):
        """Print an informational message unless quiet."""
        if not self._quiet:
            Console.info(message)

    def success(self, message):
        """Print a success message unless quiet."""
        if not self._quiet:
            Console.success(message)

    def warning(self, message):
        """Print a warning message unless quiet."""
        if not self._quiet:
            Console.warning(message)

    def danger(self, message):
        """Print an error message to stderr."""
        Console.danger(message)


class NullLogger:
    """No-op logger used when no logger is injected."""

    def info(self, message):
        """Discard an informational message."""

    def success(self, message):
        """Discard a success message."""

    def warning(self, message):
        """Discard a warning message."""

    def danger(self, message):
        """Discard an error message."""

#--------------------------------------------------
# String: slug helpers
#--------------------------------------------------


class String:
    """String helpers used by the renamer."""

    NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")

    @classmethod
    def slugify(cls, value):
        """Return a filesystem-safe slug."""
        normalized = unicodedata.normalize("NFKD", str(value))
        ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
        return cls.NON_ALPHANUMERIC.sub("-", ascii_value.lower()).strip("-")

#--------------------------------------------------
# Completion: bash completion
#--------------------------------------------------


class Completion:
    """Bash completion script generator for argparse parsers."""

    FILE_KEYS = ("output", "file", "path", "dest")
    GLOB_KEYS = ("include", "exclude", "glob", "pattern")
    COMPLETION_NAME = re.compile(r"[^a-zA-Z0-9_]")
    BODIES = {
        "boolean": "            COMPREPLY=()\n",
        "verbose": "            COMPREPLY=( $(compgen -W \"-v -vv -vvv\" -- \"${cur}\") )\n",
        "file": "            COMPREPLY=( $(compgen -f -- \"${cur}\") )\n",
        "glob": "            COMPREPLY=( $(compgen -G \"${cur}*\") )\n",
    }

    @classmethod
    def classify_parser_actions(cls, *, parser):
        """Walk the parser actions and return ``(all_opts, categories)``."""
        all_opts = set()
        categories = {"boolean": [], "verbose": [], "file": [], "glob": []}
        for action in parser._actions:  # noqa: SLF001
            opts = action.option_strings
            if not opts:
                continue
            all_opts.update(opts)
            joined = " ".join(opts).lower()
            if action.nargs == 0 and action.const is True:
                categories["boolean"].extend(opts)
            if action.__class__.__name__ == "_CountAction":
                categories["verbose"].extend(opts)
            if any(key in joined for key in cls.FILE_KEYS):
                categories["file"].extend(opts)
            if any(key in joined for key in cls.GLOB_KEYS):
                categories["glob"].extend(opts)
        return all_opts, categories

    @classmethod
    def render_completion_case(cls, *, option, kind):
        """Return the bash case branch for the given option kind."""
        return f"        {option})\n{cls.BODIES[kind]}            return 0\n            ;;\n"

    @classmethod
    def render_completion_script(cls, *, all_opts, categories, name):
        """Build the final bash completion script string."""
        blocks = []
        for kind, opts in categories.items():
            for option in sorted(set(opts)):
                blocks.append(cls.render_completion_case(option=option, kind=kind))
        option_case = "".join(blocks)
        completion_name = cls.COMPLETION_NAME.sub("_", name)
        sorted_opts = sorted(
            all_opts, key=lambda option: (not option.startswith("--"), option.lower())
        )
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

    @classmethod
    def generate(cls, *, parser, name):
        """Return a bash completion script string for the given argparse parser."""
        all_opts, categories = cls.classify_parser_actions(parser=parser)
        return cls.render_completion_script(all_opts=all_opts, categories=categories, name=name)

#--------------------------------------------------
# FileHandler: base class for business logic
#--------------------------------------------------


class FileHandler:
    """Base handler with traversal and collision-safe output names."""

    def __init__(self, *, logger=None):
        self._logger = logger if logger is not None else NullLogger()
        self.files_processed = 0
        self.files_skipped = 0

    @staticmethod
    def get_unique_filename(*, path, base_filename):
        """Return a non-conflicting filename beside path."""
        directory = path if path.is_dir() else path.parent
        candidate = directory / base_filename
        counter = 1
        while candidate.exists():
            suffix = Path(base_filename).suffix
            stem = Path(base_filename).stem
            candidate = directory / f"{stem}_{counter}{suffix}"
            counter += 1
        return candidate

    @staticmethod
    def walk_paths(input_path, *, recursive=False, include=None, exclude=None):
        """Yield files matching filters."""
        path = Path(input_path)
        iterator = (
            [path] if path.is_file() else (path.rglob("*") if recursive else path.glob("*"))
        )
        for item in sorted(iterator):
            if (
                item.is_file()
                and (not include or item.match(include))
                and (not exclude or not item.match(exclude))
            ):
                yield item

#--------------------------------------------------
# YAML: front matter loading
#--------------------------------------------------


class YamlLoader:
    """Load YAML documents, reporting a missing PyYAML dependency."""

    MISSING_MESSAGE = (
        "PyYAML library not found. Please install it using 'pip install PyYAML'."
    )

    @classmethod
    def ensure_available(cls):
        """Exit with a clear message when PyYAML is not installed."""
        cls._import_module()

    @classmethod
    def load(cls, text):
        """Return ``(data, error)`` for a YAML document."""
        yaml_module = cls._import_module()
        try:
            return yaml_module.safe_load(text), None
        except yaml_module.YAMLError as err:
            return None, err

    @classmethod
    def _import_module(cls):
        try:
            import yaml
        except ImportError:
            Console.danger(cls.MISSING_MESSAGE)
            sys.exit(1)
        return yaml

#--------------------------------------------------
# Custom Logic
#--------------------------------------------------


class MarkdownRenamer(FileHandler):
    """Handler that renames markdown files based on front matter."""

    FRONT_MATTER = re.compile(r"---\s*\n(.*?)\n---", re.DOTALL)
    REQUIRED_FIELDS = ("date", "title", "author")
    MARKDOWN_SUFFIX = ".md"

    def __init__(self, *, logger=None):
        super().__init__(logger=logger)
        self.errors = 0

    @classmethod
    def _extract_front_matter(cls, content):
        """Extract front matter from markdown content."""
        match = cls.FRONT_MATTER.match(content)
        return match.group(1) if match else None

    @classmethod
    def _validate_front_matter(cls, data):
        """Validate that required front matter fields exist."""
        return [field for field in cls.REQUIRED_FIELDS if not data.get(field)]

    @staticmethod
    def _get_date_string(value):
        """Convert date to string format."""
        return value if isinstance(value, str) else value.strftime("%Y-%m-%d")

    def process_file(self, path, *, output=None, dry_run=False):
        """Process a single markdown file and rename it based on front matter."""
        self.files_processed += 1

        if path.suffix != self.MARKDOWN_SUFFIX:
            self.files_skipped += 1
            return

        self._logger.info(f"Processing: {path}\n")

        try:
            content = path.read_text(encoding="utf-8")
        except OSError as err:
            self._logger.danger(f"Error reading {path}: {err}\n")
            self.errors += 1
            return

        front_matter_str = self._extract_front_matter(content)
        if not front_matter_str:
            self.files_skipped += 1
            return

        front_matter_data, error = YamlLoader.load(front_matter_str)
        if error is not None:
            self._logger.danger(f"  Error parsing YAML in {path}: {error}. Skipping.\n")
            self.errors += 1
            return

        missing = self._validate_front_matter(front_matter_data)
        if missing:
            self.files_skipped += 1
            return

        date_str = self._get_date_string(front_matter_data["date"])
        author_slug = String.slugify(front_matter_data["author"])
        title_slug = String.slugify(front_matter_data["title"])
        new_filename = f"{date_str}-{author_slug}-{title_slug}{self.MARKDOWN_SUFFIX}"

        if path.name == new_filename:
            self._logger.info("  Filename is already correct. Skipping.\n")
            self.files_skipped += 1
            return

        new_filepath = self.get_unique_filename(path=path, base_filename=new_filename)

        if dry_run:
            self._logger.info(f"  Would rename '{path.name}' to '{new_filepath.name}'\n")
            self.files_processed += 1
            return

        try:
            path.rename(new_filepath)
            self._logger.success(f"  Renamed '{path.name}' to '{new_filepath.name}'\n")
            self.files_processed += 1
        except OSError as err:
            self._logger.danger(f"  Error renaming {path.name}: {err}\n")
            self.errors += 1

#--------------------------------------------------
# Kernel: CLI runner
#--------------------------------------------------


class Kernel:
    """Minimal standalone CLI runner."""

    def __init__(self, *, author, title, description):
        self._author = author
        self._title = title
        self._description = description
        self._name = Path(sys.argv[0]).resolve().stem

    def _build_parser(self):
        parser = argparse.ArgumentParser(description=self._description)
        parser.add_argument("input")
        parser.add_argument("--output", help="Output directory for renamed files")
        parser.add_argument("--recursive", action="store_true")
        parser.add_argument("--include")
        parser.add_argument("--exclude")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--log", action="store_true")
        parser.add_argument("--verbose", "-v", action="count", default=0)
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="suppress non-error output; runtime errors are still reported",
        )
        parser.add_argument(
            "--completion",
            action="store_true",
            help="Print bash completion script to stdout and exit",
        )
        return parser

    def _generate_completion(self):
        return Completion.generate(parser=self._build_parser(), name=self._name)

    def run(self, handler_class):
        """Run the handler over every path selected by the CLI arguments."""
        if "--completion" in sys.argv:
            print(self._generate_completion())
            return
        args = self._build_parser().parse_args()
        YamlLoader.ensure_available()
        handler = handler_class(logger=Logger(quiet=args.quiet))
        for path in handler.walk_paths(args.input, recursive=args.recursive):
            handler.process_file(path, dry_run=args.dry_run)


if __name__ == '__main__':
    app = Kernel(
        author='TangoMan75',
        title='Markdown Renamer',
        description='Rename markdown files based on front matter.',
    )
    app.run(MarkdownRenamer)
