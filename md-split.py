#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Explode a Markdown file into sub-files based on H2 sections.
"""

import argparse
import re
import shlex
import sys
from datetime import date
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
    """Base handler with the traversal behavior used by this tool."""

    def __init__(self, *, logger=None):
        self._logger = logger if logger is not None else NullLogger()
        self.files_processed = 0
        self.files_skipped = 0

    @staticmethod
    def walk_paths(input_path, *, recursive=False, include=None, exclude=None):
        """Yield files matching the requested path filters."""
        path = Path(input_path)
        if path.is_file():
            yield path
            return
        iterator = path.rglob("*") if recursive else path.glob("*")
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
        """Return ``(data, valid)`` for a YAML document."""
        yaml_module = cls._import_module()
        try:
            return yaml_module.safe_load(text), True
        except yaml_module.YAMLError:
            return None, False

    @classmethod
    def _import_module(cls):
        try:
            import yaml
        except ImportError:
            Console.danger(cls.MISSING_MESSAGE)
            sys.exit(1)
        return yaml

#--------------------------------------------------
# Markdown Utilities
#--------------------------------------------------


class MarkdownUtils:
    """Utility class for markdown processing."""

    DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})_")
    FRONT_MATTER_DELIMITER = "---"
    H2_PREFIX = "## "
    CODE_FENCE = "```"
    FALLBACK_SECTION_TITLE = "content"

    @classmethod
    def parse_front_matter(cls, content):
        """Parse YAML front matter from markdown content."""
        if not content.startswith(cls.FRONT_MATTER_DELIMITER):
            return None, content

        parts = content.split(cls.FRONT_MATTER_DELIMITER, 2)
        if len(parts) < 3:
            return None, content

        front_matter, valid = YamlLoader.load(parts[1])
        if not valid:
            return None, content
        if front_matter is None:
            front_matter = {}

        return front_matter, parts[2]

    @staticmethod
    def get_date_from_front_matter(front_matter):
        """Extract date from front matter."""
        if front_matter is None:
            return None
        return front_matter.get("date")

    @classmethod
    def get_date_from_filename(cls, filepath):
        """Extract date from filename if it starts with YYYY-MM-DD."""
        match = cls.DATE_PREFIX.match(filepath.stem)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def get_date_from_file(filepath):
        """Get file modification date in ISO format."""
        timestamp = filepath.stat().st_mtime
        return date.fromtimestamp(timestamp).isoformat()

    @classmethod
    def split_by_h2(cls, content):
        """Split content by H2 sections, ignoring H2 inside code blocks."""
        lines = content.split("\n")
        h2_positions = []
        in_code_block = False
        for index, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(cls.CODE_FENCE):
                in_code_block = not in_code_block
            elif not in_code_block and stripped.startswith(cls.H2_PREFIX):
                h2_positions.append((index, stripped[len(cls.H2_PREFIX):].strip()))

        if not h2_positions:
            return [(cls.FALLBACK_SECTION_TITLE, content)]

        sections = []
        for index, (position, title) in enumerate(h2_positions):
            next_position = (
                h2_positions[index + 1][0] if index + 1 < len(h2_positions) else len(lines)
            )
            section_content = "\n".join(lines[position:next_position]).strip()
            sections.append((title, section_content))

        return sections

#--------------------------------------------------
# Custom Logic
#--------------------------------------------------


class MarkdownSplitter(FileHandler):
    """Handler for exploding markdown files."""

    SLUG_PATTERN = re.compile(r"[^a-z0-9]+")
    MARKDOWN_SUFFIX = ".md"

    @classmethod
    def _slugify(cls, value):
        """Return a filesystem-safe slug."""
        return cls.SLUG_PATTERN.sub("-", value.lower()).strip("-")

    def _get_date(self, *, filepath, front_matter):
        """Get date: front matter > filename date > file modification date."""
        date_value = MarkdownUtils.get_date_from_front_matter(front_matter)
        if date_value:
            if isinstance(date_value, date):
                return date_value.isoformat()
            return str(date_value)[:10]
        filename_date = MarkdownUtils.get_date_from_filename(filepath)
        if filename_date:
            return filename_date
        return MarkdownUtils.get_date_from_file(filepath)

    def _generate_filename(self, *, date_str, title, used_names):
        """Generate unique filename with date prefix."""
        slug = self._slugify(title)
        filename = f"{date_str}_{slug}{self.MARKDOWN_SUFFIX}"

        if filename not in used_names:
            used_names.add(filename)
            return filename

        counter = 1
        while True:
            new_filename = f"{date_str}_{slug}_{counter}{self.MARKDOWN_SUFFIX}"
            if new_filename not in used_names:
                used_names.add(new_filename)
                return new_filename
            counter += 1

    def _write_section(self, *, output_path, content, dry_run):
        """Write one section or report the planned write in dry-run mode."""
        if dry_run:
            self._logger.info(f"[DRY RUN] Would create: {output_path}")
            return
        output_path.write_text(content, encoding="utf-8")
        self._logger.success(f"Created: {output_path}")

    def process_file(self, path, *, output=None, dry_run=False):
        """Process a single markdown file and create sub-files."""
        if path.suffix != self.MARKDOWN_SUFFIX:
            self._logger.warning(f"Skipping non-markdown file: {path}")
            self.files_skipped += 1
            return

        content = path.read_text(encoding="utf-8")
        front_matter, remaining_content = MarkdownUtils.parse_front_matter(content)
        date_str = self._get_date(filepath=path, front_matter=front_matter)
        sections = MarkdownUtils.split_by_h2(remaining_content)

        if not sections:
            self._logger.warning(f"No sections found in: {path}")
            self.files_skipped += 1
            return

        used_names = set()
        output_dir = Path(output) if output else path.parent

        for title, section_content in sections:
            filename = self._generate_filename(
                date_str=date_str, title=title, used_names=used_names
            )
            self._write_section(
                output_path=output_dir / filename,
                content=section_content,
                dry_run=dry_run,
            )
            self.files_processed += 1

#--------------------------------------------------
# Kernel: CLI runner
#--------------------------------------------------


class Kernel:
    """Minimal standalone CLI runner for markdown handlers."""

    def __init__(self, *, author, title, description):
        self._author = author
        self._title = title
        self._description = description
        self._name = Path(sys.argv[0]).resolve().stem

    def _build_parser(self):
        parser = argparse.ArgumentParser(description=self._description)
        parser.add_argument("input")
        parser.add_argument("--output")
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
        for path in handler.walk_paths(
            args.input,
            recursive=args.recursive,
            include=args.include,
            exclude=args.exclude,
        ):
            handler.process_file(path, output=args.output, dry_run=args.dry_run)


if __name__ == '__main__':
    app = Kernel(
        author='TangoMan75',
        title='Markdown Splitter',
        description='Explode a Markdown file into sub-files based on H2 sections.',
    )
    app.run(MarkdownSplitter)
