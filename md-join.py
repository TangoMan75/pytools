#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Concatenate markdown files into a single file, removing front matter.
"""

import argparse
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
    def warning(message):
        """Print a warning unless quiet mode is enabled."""
        if not Console.quiet:
            print(message)

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

#--------------------------------------------------
# FileHandler: common path traversal
#--------------------------------------------------


class FileHandler:
    """Base handler with consistent path traversal."""

    DEFAULT_ENCODING = "utf-8"

    def __init__(self, *, logger=None):
        self.logger = logger if logger is not None else Console
        self.files_processed = 0
        self.files_skipped = 0

    @staticmethod
    def walk_paths(input_path, *, recursive=False, include=None, exclude=None):
        """Yield files matching the requested filters."""
        path = Path(input_path)
        iterator = [path] if path.is_file() else (path.rglob("*") if recursive else path.glob("*"))
        for item in sorted(iterator):
            if item.is_file() and (not include or item.match(include)) and (not exclude or not item.match(exclude)):
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
        completion_name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
        sorted_opts = sorted(all_opts, key=lambda option: (not option.startswith("--"), option.lower()))
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
        parser.add_argument("--output")
        parser.add_argument("--recursive", action="store_true")
        parser.add_argument("--include")
        parser.add_argument("--exclude")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--log", action="store_true")
        parser.add_argument("--verbose", "-v", action="count", default=0)
        parser.add_argument("--quiet", action="store_true",
                            help="suppress non-error output; runtime errors are still reported")
        parser.add_argument("--completion", action="store_true", help="Print bash completion script to stdout and exit")
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
        handler = handler_class()
        for path in handler.walk_paths(
            args.input,
            recursive=args.recursive,
            include=args.include,
            exclude=args.exclude,
        ):
            handler.process_file(path, output=args.output, dry_run=args.dry_run)

#--------------------------------------------------
# Custom Logic
#--------------------------------------------------


class MarkdownJoiner(FileHandler):
    """Handler for joining markdown files."""

    MARKDOWN_SUFFIX = ".md"

    @staticmethod
    def remove_front_matter(content):
        """Remove YAML front matter from markdown content."""
        if not content.startswith("---"):
            return content

        parts = content.split("---", 2)
        if len(parts) < 3:
            return content

        return parts[2].lstrip("\n")

    @staticmethod
    def get_default_output_filename():
        """Return default output filename with today's date."""
        return f"{date.today().isoformat()}.md"

    def _read_body(self, *, path):
        """Return file content with front matter removed and whitespace trimmed."""
        content = path.read_text(encoding=FileHandler.DEFAULT_ENCODING)
        return self.remove_front_matter(content).strip()

    def _write(self, *, output_path, content, dry_run):
        """Write joined content unless this is a dry run."""
        if dry_run:
            return
        output_path.write_text(content, encoding=FileHandler.DEFAULT_ENCODING)

    def join_files(
        self,
        input_path,
        *,
        output_path,
        include=None,
        exclude=None,
        recursive=False,
        dry_run=False,
        verbose=0,
    ):
        """Join all markdown files into a single output file."""
        files = sorted(self.walk_paths(
            input_path,
            recursive=recursive,
            include=include,
            exclude=exclude,
        ))

        if not files:
            Console.warning("No markdown files found to join\n")
            return

        joined_content = []
        for filepath in files:
            if filepath.suffix != self.MARKDOWN_SUFFIX:
                continue
            body = self._read_body(path=filepath)
            if body:
                joined_content.append(body)

        final_content = "\n\n".join(joined_content)

        if dry_run:
            if verbose:
                Console.info(f"[DRY RUN] Would create: {output_path}\n")
                Console.info(f"Content length: {len(final_content)} characters\n")
            return

        self._write(output_path=output_path, content=final_content, dry_run=dry_run)
        if verbose:
            Console.success(f"Created: {output_path}\n")

    def _append(self, *, output_path, content):
        """Append content to an existing output file or create it."""
        if output_path.exists():
            existing = output_path.read_text(encoding=FileHandler.DEFAULT_ENCODING)
            content = existing + "\n\n" + content
        output_path.write_text(content, encoding=FileHandler.DEFAULT_ENCODING)

    def process_file(self, path, *, output=None, dry_run=False):
        """Process a single markdown file."""
        if path.suffix != self.MARKDOWN_SUFFIX:
            self.files_skipped += 1
            return

        content = self._read_body(path=path)

        if not content:
            self.files_skipped += 1
            return

        output_path = Path(output) if output else Path(self.get_default_output_filename())
        if not dry_run:
            self._append(output_path=output_path, content=content)

        self.files_processed += 1


if __name__ == '__main__':
    app = Kernel(
        author='TangoMan75',
        title='Markdown Join',
        description='Concatenate markdown files into a single file, removing front matter',
    )
    app.run(MarkdownJoiner)
