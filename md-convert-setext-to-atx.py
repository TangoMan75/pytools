#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Convert setext-style headings (underlines) to ATX-style headings (hash prefixes).
"""

import argparse
import re
import shlex
import sys
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
    """Base handler with path traversal."""

    def __init__(self, *, logger=None):
        self._logger = logger if logger is not None else NullLogger()
        self.files_processed = 0
        self.files_skipped = 0

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
# Custom Logic
#--------------------------------------------------


class CodeBlockStash:
    """Replace fenced code blocks with placeholders and restore them later."""

    PLACEHOLDER = "\x00CODE_BLOCK_{}\x00"

    def __init__(self):
        self._blocks = []

    def __call__(self, match):
        """Stash a code block and return its placeholder."""
        placeholder = self.PLACEHOLDER.format(len(self._blocks))
        self._blocks.append(match.group(0))
        return placeholder

    def restore(self, *, text):
        """Return text with every placeholder replaced by its code block."""
        for index, block in enumerate(self._blocks):
            text = text.replace(self.PLACEHOLDER.format(index), block)
        return text


class SetextConverter(FileHandler):
    """Handler to convert setext headings to ATX style."""

    MARKDOWN_SUFFIXES = (".md", ".markdown", ".mdown", ".mkd")
    FRONT_MATTER_DELIMITER = re.compile(r"^---\s*$", re.MULTILINE)
    CODE_FENCE = re.compile(
        r"^(`{3,}|~{3,})[^\n]*\n.*?\n\1[^\n]*\n", re.MULTILINE | re.DOTALL
    )
    SETEXT_HEADING = re.compile(
        r"^(?P<title>\S[^\n]*)\n(?<!\n\n)(?P<underline>[=-]){3,}[^\S\n]*(?:\n|$)",
        re.MULTILINE,
    )

    @staticmethod
    def _replace_heading(match):
        """Return the ATX replacement for one setext heading match."""
        title = match.group("title").strip()
        if match.group("underline").startswith("="):
            return f"# {title}\n"
        return f"## {title}\n"

    @classmethod
    def _split_front_matter(cls, *, text):
        """Return ``(front_matter, body)`` split at the closing YAML delimiter."""
        matches = list(cls.FRONT_MATTER_DELIMITER.finditer(text))
        if len(matches) < 2 or matches[0].start() != 0:
            return "", text
        end = matches[1].end()
        return text[:end], text[end:]

    @staticmethod
    def _ensure_trailing_newline(*, text):
        """Return text with a trailing newline when it has content."""
        if text and not text.endswith("\n"):
            return text + "\n"
        return text

    def convert_setext_to_atx(self, text):
        """Convert setext-style headings (underlines) to ATX-style headings (hash prefixes)."""
        front_matter, body = self._split_front_matter(text=text)
        stash = CodeBlockStash()
        stashed = self.CODE_FENCE.sub(stash, body)
        converted = self.SETEXT_HEADING.sub(self._replace_heading, stashed)
        converted = stash.restore(text=converted)
        return self._ensure_trailing_newline(text=front_matter + converted)

    def process_file(self, path, *, output=None, dry_run=False):
        """Process a markdown file and convert setext headings to ATX."""
        if path.suffix.lower() not in self.MARKDOWN_SUFFIXES:
            self._logger.info(f"Skipping non-markdown file: {path}")
            self.files_skipped += 1
            return

        content = path.read_text(encoding="utf-8")
        converted = self.convert_setext_to_atx(content)

        if converted == content:
            self._logger.info(f"No changes: {path}")
            self.files_skipped += 1
            return

        self.files_processed += 1
        target = Path(output) if output else path
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(converted, encoding="utf-8")
        self._logger.success(f"Converted: {path}")

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
        handler = handler_class(logger=Logger(quiet=args.quiet))
        for path in handler.walk_paths(
            args.input,
            recursive=args.recursive,
            include=args.include,
            exclude=args.exclude,
        ):
            handler.process_file(path, dry_run=args.dry_run)


if __name__ == '__main__':
    app = Kernel(
        author='TangoMan75',
        title='Setext to ATX Converter',
        description=(
            'Convert setext-style headings (underlines) to ATX-style headings '
            '(hash prefixes).'
        ),
    )
    app.run(SetextConverter)
