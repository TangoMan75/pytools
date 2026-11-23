#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Generate a Table of Contents from the headings of a markdown document.
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


class MarkdownToc(FileHandler):
    """Handler to generate a Table of Contents from markdown headings."""

    MARKDOWN_SUFFIXES = (".md", ".markdown", ".mdown", ".mkd")
    TOC_MARKER = re.compile(
        r"^[ \t]*<!-{2,}[ \t]*toc[ \t]*-{2,}>[ \t]*$", re.IGNORECASE
    )
    FRONT_MATTER_KEY = re.compile(r"^\s*[\w-]+:")
    ATX_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
    SETEXT_H1_UNDERLINE = re.compile(r"^=+\s*$")
    SETEXT_H2_UNDERLINE = re.compile(r"^-+\s*$")
    INLINE_MARKUP = re.compile(r"[`*_~]+")
    NON_WORD = re.compile(r"[^\w\s-]")
    WHITESPACE = re.compile(r"[\s]+")
    CODE_FENCE_MARKERS = ("```", "~~~")
    FALLBACK_SLUG = "section"
    DEFAULT_MIN_DEPTH = 1
    DEFAULT_MAX_DEPTH = 6
    DEFAULT_TITLE = "Table of Contents"

    def __init__(
        self,
        *,
        logger=None,
        min_depth=DEFAULT_MIN_DEPTH,
        max_depth=DEFAULT_MAX_DEPTH,
        title=DEFAULT_TITLE,
        insert=False,
    ):
        super().__init__(logger=logger)
        self._min_depth = min_depth
        self._max_depth = max_depth
        self._title = title
        self._insert = insert

    @classmethod
    def _slugify(cls, text):
        """Return a GitHub-style anchor slug for a heading."""
        value = text.strip().lower()
        value = cls.INLINE_MARKUP.sub("", value)
        value = cls.NON_WORD.sub("", value)
        value = value.strip()
        value = cls.WHITESPACE.sub("-", value)
        return value

    @classmethod
    def _extract_front_matter(cls, *, lines):
        """Return (front_matter_lines, body_lines) splitting YAML front matter."""
        if not lines or lines[0].strip() != "---":
            return [], lines
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                block = lines[1:index]
                if any(cls.FRONT_MATTER_KEY.match(line) for line in block):
                    return lines[:index + 1], lines[index + 1:]
                return [], lines
        return [], lines

    @classmethod
    def _iter_headings(cls, *, body_lines):
        """Yield (depth, text) for each heading in body_lines, skipping code fences."""
        in_fence = False
        fence_marker = None
        index = 0
        total = len(body_lines)
        while index < total:
            line = body_lines[index]
            stripped = line.strip()
            if not in_fence and stripped.startswith(cls.CODE_FENCE_MARKERS):
                in_fence = True
                fence_marker = stripped[:3]
                index += 1
                continue
            if in_fence:
                if stripped.startswith(fence_marker):
                    in_fence = False
                    fence_marker = None
                index += 1
                continue

            atx = cls.ATX_HEADING.match(line)
            if atx:
                yield len(atx.group(1)), atx.group(2).strip()
                index += 1
                continue

            if index + 1 < total:
                next_line = body_lines[index + 1].strip()
                if cls.SETEXT_H1_UNDERLINE.match(next_line):
                    yield 1, line.strip()
                    index += 2
                    continue
                if cls.SETEXT_H2_UNDERLINE.match(next_line) and line.strip():
                    yield 2, line.strip()
                    index += 2
                    continue

            index += 1

    def build_toc(self, text):
        """Return the Table of Contents block for the given markdown text."""
        lines = text.splitlines()
        _, body = self._extract_front_matter(lines=lines)
        headings = list(self._iter_headings(body_lines=body))

        used = set()
        counts = {}
        entries = []
        for depth, heading in headings:
            if depth < self._min_depth or depth > self._max_depth:
                continue
            slug = self._slugify(heading) or f"{self.FALLBACK_SLUG}-{len(entries) + 1}"
            count = counts.get(slug, 0)
            anchor = slug if count == 0 else f"{slug}-{count}"
            while anchor in used:
                count += 1
                anchor = f"{slug}-{count}"
            counts[slug] = count + 1
            used.add(anchor)
            indent = "  " * (depth - self._min_depth)
            entries.append(f"{indent}- [{heading}](#{anchor})")

        if not entries:
            return ""

        block = []
        if self._title:
            block.append(f"**{self._title}**")
            block.append("")
        block.extend(entries)
        block.append("")
        return "\n".join(block)

    def _insert_toc(self, *, text, toc):
        """Insert or replace the TOC inside the document text."""
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if self.TOC_MARKER.match(line):
                marker_indent = line[:len(line) - len(line.lstrip())]
                replacement = [
                    f"{marker_indent}{entry}" if entry else entry
                    for entry in toc.splitlines()
                ]
                return (
                    "\n".join(lines[:index] + replacement + lines[index + 1:])
                    + ("\n" if text.endswith("\n") else "")
                )

        front_matter, body = self._extract_front_matter(lines=lines)
        if front_matter:
            return (
                "\n".join(front_matter + [""] + toc.splitlines() + [""] + body)
                + ("\n" if text.endswith("\n") else "")
            )
        return toc.rstrip("\n") + "\n\n" + text

    @staticmethod
    def _resolve_target(*, path, output, insert):
        """Resolve the output target, placing a file inside a directory if needed."""
        if not output:
            return path
        target = Path(output)
        if target.is_dir():
            if insert:
                return target / path.name
            return target / f"{path.stem}.toc.md"
        return target

    def _write_toc(self, *, path, output, content, toc, dry_run, insert):
        """Write the generated TOC and report the result."""
        self.files_processed += 1
        target = self._resolve_target(path=path, output=output, insert=insert)
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            text = self._insert_toc(text=content, toc=toc) if insert else toc
            target.write_text(text, encoding="utf-8")
        if insert:
            self._logger.success(f"Inserted TOC into: {target}")
        else:
            self._logger.success(f"Wrote TOC to: {target}")

    def process_file(self, path, *, output=None, dry_run=False):
        """Generate a Table of Contents for a markdown file."""
        if path.suffix.lower() not in self.MARKDOWN_SUFFIXES:
            self._logger.info(f"Skipping non-markdown file: {path}")
            self.files_skipped += 1
            return

        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as err:
            self._logger.danger(f"Cannot read {path}: {err}")
            self.files_skipped += 1
            return

        toc = self.build_toc(content)

        if not toc:
            self._logger.info(f"No headings found: {path}")
            self.files_skipped += 1
            return

        if self._insert:
            self._write_toc(
                path=path,
                output=output,
                content=content,
                toc=toc,
                dry_run=dry_run,
                insert=True,
            )
            return

        if output:
            self._write_toc(
                path=path,
                output=output,
                content=content,
                toc=toc,
                dry_run=dry_run,
                insert=False,
            )
            return

        self.files_processed += 1
        print(toc)

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
        parser.add_argument(
            "--insert",
            action="store_true",
            help=(
                "Insert the TOC into the document (replace '<!-- toc -->' or place "
                "after front matter)"
            ),
        )
        parser.add_argument(
            "--min-depth",
            type=int,
            default=1,
            help="Minimum heading depth to include (default 1)",
        )
        parser.add_argument(
            "--max-depth",
            type=int,
            default=6,
            help="Maximum heading depth to include (default 6)",
        )
        parser.add_argument(
            "--title",
            default="Table of Contents",
            help="TOC title (use empty string for none)",
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
        handler = handler_class(
            logger=Logger(quiet=args.quiet),
            min_depth=args.min_depth,
            max_depth=args.max_depth,
            title=args.title,
            insert=args.insert,
        )
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
        title='Markdown Table of Contents Generator',
        description='Generate a Table of Contents from the headings of a markdown document.',
    )
    app.run(MarkdownToc)
