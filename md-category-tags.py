#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Add category tags to daily notes.

This script processes markdown files, extracting the category from filenames
(YYYY-MM-DD_category.md pattern) and adding it as a tag to each note within the files.

Usage:
    python3 md-category-tags.py <directory> [-r]
"""

import argparse
import re
import shlex
import sys
from pathlib import Path

#--------------------------------------------------
# Console: semantic console output
#--------------------------------------------------


class Console:
    """Console output helpers for this standalone tool."""

    quiet = False

    @staticmethod
    def info(message):
        """Print an informational message unless quiet mode is enabled."""
        if not Console.quiet:
            print(message)

    @staticmethod
    def success(message):
        """Print a success message unless quiet mode is enabled."""
        if not Console.quiet:
            print(message)

    @staticmethod
    def warning(message):
        """Print a warning unless quiet mode is enabled."""
        if not Console.quiet:
            print(message)

    @staticmethod
    def error(message):
        """Print an error message to standard error."""
        print(message, file=sys.stderr)

#--------------------------------------------------
# Logger: optional handler collaborator
#--------------------------------------------------


class NullLogger:
    """No-op logger used as the default handler collaborator."""

    def info(self, message):
        """Discard an informational message."""

    def success(self, message):
        """Discard a success message."""

    def warning(self, message):
        """Discard a warning message."""

    def danger(self, message):
        """Discard an error message."""


class ConsoleLogger:
    """Forward handler messages to the console."""

    def info(self, message):
        """Print an informational message."""
        Console.info(message)

    def success(self, message):
        """Print a success message."""
        Console.success(message)

    def warning(self, message):
        """Print a warning message."""
        Console.warning(message)

    def danger(self, message):
        """Print an error message."""
        Console.error(message)

#--------------------------------------------------
# FileHandler: common path traversal
#--------------------------------------------------


class FileHandler:
    """Base handler with consistent path traversal."""

    DEFAULT_ENCODING = "utf-8"

    def __init__(self, *, logger=None):
        self._logger = logger if logger is not None else NullLogger()
        self.files_processed = 0
        self.files_skipped = 0

    @staticmethod
    def walk_paths(input_path, *, recursive=False, include=None, exclude=None):
        """Yield files matching the requested filters."""
        path = Path(input_path)
        iterator = [path] if path.is_file() else (path.rglob("*") if recursive else path.glob("*"))
        for item in sorted(iterator):
            matches_include = not include or item.match(include)
            matches_exclude = not exclude or not item.match(exclude)
            if item.is_file() and matches_include and matches_exclude:
                yield item

#--------------------------------------------------
# Completion: bash completion generation
#--------------------------------------------------


class Completion:
    """Build bash completion scripts from an argparse parser."""

    BOOLEAN_BODY = "            COMPREPLY=()\n"
    VERBOSE_BODY = '            COMPREPLY=( $(compgen -W "-v -vv -vvv" -- "${cur}") )\n'
    FILE_BODY = '            COMPREPLY=( $(compgen -f -- "${cur}") )\n'
    GLOB_BODY = '            COMPREPLY=( $(compgen -G "${cur}*") )\n'

    NAME_PATTERN = re.compile(r"[^a-zA-Z0-9_]")
    FILE_KEYS = ("output", "file", "path", "dest")
    GLOB_KEYS = ("include", "exclude", "glob", "pattern")

    @classmethod
    def _bodies(cls):
        """Return the completion body for each option category."""
        return {
            "boolean": cls.BOOLEAN_BODY,
            "verbose": cls.VERBOSE_BODY,
            "file": cls.FILE_BODY,
            "glob": cls.GLOB_BODY,
        }

    @staticmethod
    def _classify_parser_actions(arg_parser):
        """Walk the parser actions and return ``(all_opts, categories)``."""
        all_opts = set()
        categories = {"boolean": [], "verbose": [], "file": [], "glob": []}
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
            if any(key in joined for key in Completion.FILE_KEYS):
                categories["file"].extend(opts)
            if any(key in joined for key in Completion.GLOB_KEYS):
                categories["glob"].extend(opts)
        return all_opts, categories

    @classmethod
    def _render_case(cls, *, opt, kind):
        """Return the bash case branch for the given option kind."""
        return f"        {opt})\n{cls._bodies()[kind]}            return 0\n            ;;\n"

    @classmethod
    def _render_script(cls, *, all_opts, categories, name):
        """Build the final bash completion script string."""
        blocks = []
        for kind, opts in categories.items():
            for opt in sorted(set(opts)):
                blocks.append(cls._render_case(opt=opt, kind=kind))
        option_case = "".join(blocks)
        completion_name = cls.NAME_PATTERN.sub("_", name)
        sorted_opts = sorted(
            all_opts,
            key=lambda option: (not option.startswith("--"), option.lower()),
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
        """Return a bash completion script string for the given parser."""
        all_opts, categories = cls._classify_parser_actions(parser)
        return cls._render_script(all_opts=all_opts, categories=categories, name=name)

#--------------------------------------------------
# Kernel: minimal CLI runner
#--------------------------------------------------


class Kernel:
    """Minimal standalone CLI runner for markdown handlers."""

    def __init__(self, *, author, title, description):
        self._author = author
        self._title = title
        self._description = description

    def build_parser(self):
        """Build the command-line parser."""
        parser = argparse.ArgumentParser(description=self._description)
        parser.add_argument("input")
        parser.add_argument("--output", help="Output file or directory")
        parser.add_argument("--recursive", action="store_true")
        parser.add_argument("--include")
        parser.add_argument("--exclude")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--log", action="store_true")
        parser.add_argument("--verbose", "-v", action="count", default=0)
        parser.add_argument("--quiet", action="store_true",
                            help="suppress non-error output; runtime errors are still reported")
        parser.add_argument("--completion", action="store_true",
                            help="Print bash completion script to stdout and exit")
        return parser

    def generate_completion(self):
        """Return the bash completion script for this command."""
        return Completion.generate(
            parser=self.build_parser(),
            name=Path(sys.argv[0]).resolve().stem,
        )

    def run(self, handler_class):
        """Parse arguments and run the handler over every matching path."""
        parser = self.build_parser()
        if "--completion" in sys.argv:
            print(self.generate_completion())
            return
        args = parser.parse_args()
        Console.quiet = args.quiet
        handler = handler_class(logger=ConsoleLogger())
        for path in handler.walk_paths(args.input, recursive=args.recursive):
            handler.process_file(path, dry_run=args.dry_run)

#--------------------------------------------------
# Category resolution
#--------------------------------------------------


class CategoryResolver:
    """Resolve a category from a dated filename or leading title."""

    CATEGORY_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}_(.+)")

    @classmethod
    def from_filename(cls, *, filename):
        """Return the category encoded in a dated filename, if any."""
        match = cls.CATEGORY_PATTERN.match(Path(filename).stem)
        if match:
            return match.group(1)
        return None

    @classmethod
    def from_title(cls, *, content):
        """Return the category encoded in the first content line, if any."""
        lines = content.split("\n")
        if lines:
            title_line = lines[0].strip()
            match = cls.CATEGORY_PATTERN.match(title_line)
            if match:
                return match.group(1)
        return None

    @classmethod
    def resolve(cls, *, filename, content):
        """Resolve a category from the filename first, then the title."""
        return cls.from_filename(filename=filename) or cls.from_title(content=content)

#--------------------------------------------------
# Note tagging
#--------------------------------------------------


class NoteTagger:
    """Add a category hashtag to a single markdown note."""

    TAG_PATTERN = re.compile(r"#\w+")
    TAG_LINE_MARKER = "#"
    TAG_LINE_EXCLUSION = "# "
    TITLE_MARKER = "## "

    def __init__(self, *, logger=None):
        self._logger = logger if logger is not None else NullLogger()

    def add(self, *, note, category, dry_run=False):
        """Return the note with the category tag and whether it changed."""
        if not category:
            return note, False

        category_tag = f"#{category}"
        lines = note.split("\n")
        tag_lines = self._tag_lines(lines=lines)

        for _, _, tags in tag_lines:
            if category_tag in tags:
                return note, False

        self._insert_tag(
            lines=lines,
            tag_lines=tag_lines,
            category_tag=category_tag,
            dry_run=dry_run,
        )
        return "\n".join(lines), True

    def _tag_lines(self, *, lines):
        """Return ``(index, line, tags)`` for lines that already carry tags."""
        tag_lines = []
        for index, line in enumerate(lines):
            stripped = line.strip()
            if (
                stripped.startswith(self.TAG_LINE_MARKER)
                and not stripped.startswith(self.TAG_LINE_EXCLUSION)
            ):
                tags = self.TAG_PATTERN.findall(line)
                if tags:
                    tag_lines.append((index, line, tags))
        return tag_lines

    def _insert_tag(self, *, lines, tag_lines, category_tag, dry_run):
        """Insert the category tag into the first suitable location."""
        if tag_lines:
            index, line, _ = tag_lines[0]
            if dry_run:
                self._logger.info(
                    f"  Would add '{category_tag}' to existing tags: {line.strip()}"
                )
            else:
                lines[index] = f"{category_tag} {line}"
            return

        for index, line in enumerate(lines):
            if line.strip().startswith(self.TITLE_MARKER) and index + 1 < len(lines):
                if dry_run:
                    self._logger.info(
                        f"  Would add '{category_tag}' after note title: {line.strip()}"
                    )
                else:
                    lines.insert(index + 1, category_tag)
                return

        if dry_run:
            self._logger.info(f"  Would add '{category_tag}' at end of note")
        else:
            lines.append(category_tag)

#--------------------------------------------------
# Custom Logic
#--------------------------------------------------


class CategoryTagsAdder(FileHandler):
    """Handler that adds category tags to daily notes."""

    MARKDOWN_SUFFIX = ".md"
    NOTE_SEPARATOR = re.compile(r"\n(?=## )")

    def __init__(self, *, logger=None):
        super().__init__(logger=logger)
        self.files_updated = 0
        self.errors = 0
        self._resolver = CategoryResolver()
        self._tagger = NoteTagger(logger=self._logger)

    def process_file(self, path, *, output=None, dry_run=False):
        """Process a single markdown file and add category tags."""
        self.files_processed += 1

        if path.suffix != self.MARKDOWN_SUFFIX:
            self.files_skipped += 1
            return

        try:
            content = path.read_text(encoding=FileHandler.DEFAULT_ENCODING)
        except OSError as err:
            self._logger.danger(f"Error reading {path}: {err}")
            self.errors += 1
            return

        category = self._resolver.resolve(filename=path.name, content=content)
        if not category:
            self._logger.info(f"No category found in {path.name}")
            self.files_skipped += 1
            return

        self._logger.info(f"Processing {path.name} (category: {category})")

        notes = self.NOTE_SEPARATOR.split(content)
        updated_notes = []
        file_modified = False

        for index, note in enumerate(notes):
            if note.strip():
                updated_note, note_modified = self._tagger.add(
                    note=note,
                    category=category,
                    dry_run=dry_run,
                )
                if note_modified:
                    file_modified = True
                    note_title = (
                        note.split("\n")[0].strip() if note.split("\n") else f"Note {index + 1}"
                    )
                    self._logger.info(f"  Modified note: {note_title}")
                updated_notes.append(updated_note)
            else:
                updated_notes.append(note)

        if file_modified and not dry_run:
            try:
                path.write_text("\n".join(updated_notes), encoding=FileHandler.DEFAULT_ENCODING)
                self._logger.success(f"Updated {path.name}")
                self.files_updated += 1
            except OSError as err:
                self._logger.danger(f"Error writing {path}: {err}")
                self.errors += 1
        elif file_modified and dry_run:
            self._logger.info(f"Would update {path.name}")
            self.files_updated += 1
        else:
            self._logger.info(f"No changes needed for {path.name}")


if __name__ == "__main__":
    kernel = Kernel(
        author="TangoMan75",
        title="Markdown Category Tags",
        description="Add category tags to daily notes."
    )
    kernel.run(CategoryTagsAdder)
