#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Add YAML front matter to markdown files for static site generators and documentation tools.

This script automatically generates and adds front matter metadata to markdown files,
including title, date, author, and tags. It supports both creating new front matter
and updating existing front matter while preserving custom fields.

Features:
- Extract date from filename prefix (YYYY-MM-DD) or file modification time
- Generate title from filename by converting dashes/underscores to spaces and title-casing
- Extract hashtags from document content as tags
- Support for custom author, date, and tags via command-line arguments
- Preserve existing front matter while updating specified fields
- Process single files or entire directories with recursive traversal
- Include/exclude filters for selective file processing
- Dry-run mode for testing before making changes
- Verbose logging and colored output
- Self-installation with shell completion support

Usage:
    python3 md-front-matter.py input.md --author "John Doe" --tags "python,markdown"
    python3 md-front-matter.py docs/ --recursive --force --verbose
"""

import argparse
import os
import re
import shlex
import sys
from datetime import date
from pathlib import Path

#--------------------------------------------------
# Console: semantic console output
#--------------------------------------------------


class Console:
    """Console output helpers for this standalone tool."""

    quiet = False

    @staticmethod
    def error(message):
        """Print an error message to standard error."""
        print(message, file=sys.stderr)

#--------------------------------------------------
# YAML: front matter loading
#--------------------------------------------------


class YamlLoader:
    """Load YAML documents, reporting a missing PyYAML dependency."""

    MISSING_MESSAGE = (
        "PyYAML library not found. Please install it using 'pip install PyYAML'."
    )

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
            Console.error(cls.MISSING_MESSAGE)
            sys.exit(1)
        return yaml

#--------------------------------------------------
# Logger: optional handler collaborator
#--------------------------------------------------


class Logger:
    """Small logger used by the standalone command."""

    def __init__(self, *, verbose=0, quiet=False):
        self.verbose = verbose
        self.quiet = quiet

    def print(self):
        """Return without output; the log is kept for CLI compatibility."""
        return None

    def info(self, message):
        """Print an informational message when verbose and not quiet."""
        if self.verbose and not self.quiet:
            print(message)

    def success(self, message):
        """Print a success message unless quiet mode is enabled."""
        if not self.quiet:
            print(message)

    def warning(self, message):
        """Print a warning message unless quiet mode is enabled."""
        self.success(message)

    @staticmethod
    def danger(message):
        """Print an error message to standard error."""
        print(message, file=sys.stderr)


class NullLogger:
    """No-op logger used as the default handler collaborator."""

    def print(self):
        """Discard the log request."""

    def info(self, message):
        """Discard an informational message."""

    def success(self, message):
        """Discard a success message."""

    def warning(self, message):
        """Discard a warning message."""

    def danger(self, message):
        """Discard an error message."""

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
        if not path.exists():
            raise FileNotFoundError(f"input path not found: {path}")
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
    """Minimal standalone CLI base for front matter processing."""

    def __init__(self, *, author, title, description):
        self._author = author
        self._title = title
        self._description = description

    def build_early_parser(self):
        """Build the parser for options that must be known before the input."""
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--log", action="store_true")
        parser.add_argument("--verbose", "-v", action="count", default=0)
        parser.add_argument("--quiet", action="store_true",
                            help="suppress non-error output; runtime errors are still reported")
        parser.add_argument("--completion", action="store_true",
                            help="Print bash completion script to stdout and exit")
        return parser

    def build_parser(self):
        """Build the command-line parser."""
        parser = argparse.ArgumentParser(description=self._description)
        parser.add_argument("input")
        parser.add_argument("--output")
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

    def hero(self):
        """Return without output; the banner is kept for CLI compatibility."""
        return None

#--------------------------------------------------
# App
#--------------------------------------------------


class FrontMatterApp(Kernel):
    """CLI application with extra options for front matter generation."""

    def build_parser(self):
        """Build and return argument parser with extra options."""
        parser = super().build_parser()
        parser.add_argument("--author", type=str, help="Author name (default: $USER)")
        parser.add_argument("--date", type=str,
                            help="Date in YYYY-MM-DD format (default: file modification date)")
        parser.add_argument("--tags", type=str, help="Comma-separated list of tags")
        parser.add_argument("--force", action="store_true",
                            help="Override existing front matter attributes")
        return parser

    def generate_completion(self):
        """Return the bash completion script for this script."""
        return Completion.generate(
            parser=self.build_parser(),
            name=Path(sys.argv[0]).resolve().stem,
        )

    def run(self, handler_class=None):
        """Run the handler with CLI arguments including extra options."""
        early_args, _ = self.build_early_parser().parse_known_args()
        self._logger = Logger(verbose=early_args.verbose, quiet=early_args.quiet)
        Console.quiet = early_args.quiet

        if early_args.completion:
            print(self.generate_completion())
            return

        if early_args.log:
            self._logger.print()
            return

        args = self.build_parser().parse_args()

        handler = handler_class(
            logger=self._logger,
            author=args.author,
            custom_date=args.date,
            tags=args.tags.split(",") if args.tags else [],
            force=args.force,
        )

        if args.verbose >= 1:
            self.hero()

        try:
            file_paths = handler.walk_paths(
                args.input,
                recursive=args.recursive,
                include=args.include,
                exclude=args.exclude,
            )
            for file_path in file_paths:
                self._logger.info(f"Processing {file_path}")
                handler.process_file(file_path, output=args.output, dry_run=args.dry_run)
        except FileNotFoundError as err:
            Console.error(str(err))
            sys.exit(1)

        if handler.files_processed > 0:
            self._logger.success(f"Processed {handler.files_processed} files")
        else:
            self._logger.warning('Processed 0 files')

        if handler.files_skipped > 0:
            self._logger.warning(f"Skipped {handler.files_skipped} files")

#--------------------------------------------------
# Custom Logic
#--------------------------------------------------


class FrontMatterHandler(FileHandler):
    """Generate front matter in markdown files."""

    DATE_PREFIX_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}[_-]?(.*)$")
    TAG_PATTERN = re.compile(r"#([a-zA-Z0-9_-]+)")
    MARKDOWN_SUFFIX = ".md"

    def __init__(self, *, logger=None, author=None, custom_date=None, tags=None, force=False):
        super().__init__(logger=logger)
        self.author = author
        self.custom_date = custom_date
        self.tags = list(tags) if tags else []
        self.force = force

    def get_date_from_filename(self, *, filepath):
        """Extract date from filename prefix if present (YYYY-MM-DD*)."""
        match = self.DATE_PREFIX_PATTERN.match(filepath.stem)
        if match:
            return filepath.stem[:10]
        return None

    def get_title_from_filename(self, *, filepath):
        """Extract title from filename by sanitizing stem."""
        stem = filepath.stem
        match = self.DATE_PREFIX_PATTERN.match(stem)
        if match:
            stem = match.group(1)
        if not stem:
            stem = filepath.stem
        title = stem.replace("-", " ").replace("_", " ")
        return title.title()

    def get_date_from_file(self, *, filepath):
        """Get file modification date in ISO format."""
        timestamp = filepath.stat().st_mtime
        return date.fromtimestamp(timestamp).isoformat()

    def get_default_author(self):
        """Get default author from USER environment variable."""
        return os.environ.get("USER", "unknown")

    def extract_tags_from_content(self, *, content):
        """Extract hashtags from document content."""
        tags = []
        for line in content.splitlines():
            matches = self.TAG_PATTERN.findall(line)
            tags.extend(matches)
        return tags

    def parse_front_matter(self, *, content):
        """Parse YAML front matter from markdown content."""
        if not content.startswith("---"):
            return None, content

        parts = content.split("---", 2)
        if len(parts) < 3:
            return None, content

        front_matter, error = YamlLoader.load(parts[1])
        if error is not None:
            return None, content
        if front_matter is None:
            front_matter = {}

        return front_matter, parts[2]

    def format_front_matter(self, *, data):
        """Format front matter dictionary as YAML string."""
        lines = ["---"]
        for key, value in data.items():
            if isinstance(value, list):
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f"  - {item}")
            else:
                lines.append(f"{key}: {value}")
        lines.append("---")
        return "\n".join(lines)

    def merge_tags(self, *, existing, new):
        """Merge and deduplicate tags, returning sorted list."""
        all_tags = []
        if existing:
            all_tags.extend(existing)
        all_tags.extend(new)
        unique_tags = sorted(set(all_tags))
        return unique_tags

    def _get_date(self, *, path):
        """Get date: custom > filename prefix > file modification date."""
        if self.custom_date:
            return self.custom_date
        filename_date = self.get_date_from_filename(filepath=path)
        if filename_date:
            return filename_date
        return self.get_date_from_file(filepath=path)

    def _build_front_matter(self, *, path, existing, remaining_content):
        """Build front matter dictionary based on existing content and options."""
        extracted_tags = self.extract_tags_from_content(content=remaining_content)
        all_tags = []
        if self.tags:
            all_tags.extend(self.tags)
        all_tags.extend(extracted_tags)

        if existing is None:
            front_matter = {
                "title": self.get_title_from_filename(filepath=path),
                "date": self._get_date(path=path),
                "author": self.author if self.author else self.get_default_author(),
            }
            if all_tags:
                front_matter["tags"] = list(sorted(set(all_tags)))
            return front_matter

        if self.force:
            front_matter = existing.copy()
            front_matter["date"] = self._get_date(path=path)
            front_matter["author"] = self.author if self.author else self.get_default_author()
            if all_tags:
                front_matter["tags"] = list(sorted(set(all_tags)))
            return front_matter

        front_matter = existing.copy()
        existing_tags = front_matter.get("tags", [])
        front_matter["tags"] = self.merge_tags(existing=existing_tags, new=all_tags)
        return front_matter

    def process_file(self, path, *, output=None, dry_run=False, verbose=0):
        """Process a single file to add front matter."""
        if path.suffix != self.MARKDOWN_SUFFIX:
            if verbose:
                self._logger.info(f"Skipping non-markdown file: {path}\n")
            return

        if dry_run:
            self._logger.info(f"Would add front matter to: {path}\n")
            return

        content = path.read_text(encoding=FileHandler.DEFAULT_ENCODING)
        existing_front_matter, remaining_content = self.parse_front_matter(content=content)

        front_matter = self._build_front_matter(
            path=path,
            existing=existing_front_matter,
            remaining_content=remaining_content,
        )
        front_matter_str = self.format_front_matter(data=front_matter)

        if remaining_content.startswith("\n"):
            remaining_content = remaining_content[1:]

        new_content = front_matter_str + "\n\n" + remaining_content
        target = Path(output) if output else path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(new_content, encoding=FileHandler.DEFAULT_ENCODING)
        self.files_processed += 1

        if verbose:
            self._logger.success(f"Added front matter to: {path}\n")


if __name__ == '__main__':
    kernel = FrontMatterApp(
        author='TangoMan75',
        title='Front Matter Generator',
        description='Generate front matter in markdown files.'
    )
    kernel.run(FrontMatterHandler)
