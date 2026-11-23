#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Auto-increment semver-shaped version numbers in text files.

Matches three-segment dotted numbers (e.g. 0.1.0, 1.2.9) and bumps them in place.
Word boundaries and a 1-3 digit cap keep the matcher away from IP addresses and
calendar dates. Pre-release suffixes are stripped on bump.

Usage:
    python3 semantic_versioning.py <input> [-M|-m|-f] [-r] [--line N]
"""

import argparse
import os
import re
import shlex
import sys
import tempfile
from pathlib import Path


#--------------------------------------------------
# Console: semantic console output
#--------------------------------------------------


class Console:
    """Console output helpers."""

    quiet = False

    @staticmethod
    def error(message):
        """Print an error message to stderr."""
        print(message, file=sys.stderr)


#--------------------------------------------------
# Logging: console logger and null object
#--------------------------------------------------


class NullLogger:
    """No-op logger used when no logging collaborator is provided."""

    def print(self):
        """Do nothing."""

    def info(self, message):  # noqa: ARG002
        """Do nothing."""

    def success(self, message):  # noqa: ARG002
        """Do nothing."""

    def warning(self, message):  # noqa: ARG002
        """Do nothing."""

    def danger(self, message):  # noqa: ARG002
        """Do nothing."""


class Logger:
    """Small console logger used by the standalone command."""

    def __init__(self, *, verbose=0, quiet=False):
        self.verbose = verbose
        self.quiet = quiet

    def print(self):
        """Print the log file; this command keeps no log file."""
        return None

    def info(self, message):
        """Print an informational message when verbosity is enabled."""
        if self.verbose and not self.quiet:
            print(message)

    def success(self, message):
        """Print a success message unless quiet."""
        if not self.quiet:
            print(message)

    def warning(self, message):
        """Print a warning message unless quiet."""
        if not self.quiet:
            print(message)

    def danger(self, message):
        """Print an error message to stderr."""
        print(message, file=sys.stderr)


#--------------------------------------------------
# FileHandler: base path traversal
#--------------------------------------------------


class FileHandler:
    """Base handler with consistent path traversal."""

    def __init__(self, *, logger=None):
        self.logger = logger if logger is not None else NullLogger()
        self.files_processed = 0
        self.files_skipped = 0

    @staticmethod
    def walk_paths(input_path, *, recursive=False, include=None, exclude=None):
        """Yield files matching the requested filters."""
        path = Path(input_path)
        if not path.exists():
            raise FileNotFoundError(f"input path not found: {path}")

        if path.is_file():
            candidates = [path]
        elif recursive:
            candidates = sorted(path.rglob("*"))
        else:
            candidates = sorted(path.glob("*"))

        for item in candidates:
            if not item.is_file():
                continue
            if include and not item.match(include):
                continue
            if exclude and item.match(exclude):
                continue
            yield item


#--------------------------------------------------
# VersionParser: pure parsing & bumping logic
#--------------------------------------------------


class VersionParser:
    """Static utility for parsing and bumping semver-shaped strings."""

    VALID_KINDS = ("major", "minor", "fix")

    PATTERN = re.compile(r"(?<![\d.])\d{1,3}\.\d{1,3}\.\d{1,3}(?!\d|\.)")
    LINE_PATTERN = re.compile(
        r"(?<![\d.])"
        r"(\d{1,3}\.\d{1,3}\.\d{1,3})"
        r"(?:-[0-9A-Za-z.-]+)?"
        r"(?!\d|\.)"
    )

    @staticmethod
    def parse(version):
        """Parse a 'M.m.f' string into a (major, minor, fix) tuple."""
        match = re.fullmatch(r"\d{1,3}\.\d{1,3}\.\d{1,3}", version)
        if not match:
            raise ValueError(f"not a valid semver-shaped string: {version!r}")
        major, minor, fix = (int(part) for part in version.split("."))
        return major, minor, fix

    @staticmethod
    def format(components):
        """Format a (major, minor, fix) tuple as 'M.m.f'."""
        major, minor, fix = components
        return f"{major}.{minor}.{fix}"

    @staticmethod
    def bump(version, *, kind):
        """Return the bumped version string for the given kind."""
        if kind not in VersionParser.VALID_KINDS:
            raise ValueError(
                f"unknown bump kind: {kind!r} "
                f"(expected one of {VersionParser.VALID_KINDS})"
            )
        major, minor, fix = VersionParser.parse(version)
        if kind == "major":
            return VersionParser.format((major + 1, 0, 0))
        if kind == "minor":
            return VersionParser.format((major, minor + 1, 0))
        return VersionParser.format((major, minor, fix + 1))

    @staticmethod
    def bump_in_line(line, *, kind):
        """Return (new_line, [(old, new), ...]) with all matches bumped.

        Pre-release suffixes (e.g. ``-rc.1``) are stripped on bump.
        """
        pieces = []
        changes = []
        cursor = 0
        for match in VersionParser.LINE_PATTERN.finditer(line):
            old_full = match.group(0)
            old_version = match.group(1)
            new_version = VersionParser.bump(old_version, kind=kind)
            pieces.append(line[cursor:match.start()])
            pieces.append(new_version)
            changes.append((old_full, new_version))
            cursor = match.end()
        pieces.append(line[cursor:])
        return "".join(pieces), changes


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
                blocks.append(
                    Completion.render_completion_case(opt=opt, kind=kind)
                )
        option_case = "".join(blocks)
        completion_name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
        sorted_opts = sorted(
            all_opts, key=lambda opt: (not opt.startswith("--"), opt.lower())
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

    @staticmethod
    def generate(*, parser, name):
        """Return a bash completion script string for the given parser."""
        all_opts, categories = Completion.classify_parser_actions(
            arg_parser=parser
        )
        return Completion.render_completion_script(
            all_opts=all_opts,
            categories=categories,
            name=name,
        )


#--------------------------------------------------
# VersionBumper: FileHandler that applies bumps
#--------------------------------------------------


class VersionBumper(FileHandler):
    """Handler that bumps semver-shaped strings in text files."""

    BINARY_SNIFF_BYTES = 8192
    BINARY_NULL_THRESHOLD = 1

    def __init__(self, *, logger=None, kind="fix", line=None):
        super().__init__(logger=logger)
        if kind not in VersionParser.VALID_KINDS:
            raise ValueError(f"unknown bump kind: {kind!r}")
        self.kind = kind
        self.line = line

    @staticmethod
    def is_binary(path):
        """Heuristically detect binary files by sniffing for NUL bytes."""
        try:
            with open(path, "rb") as handle:
                sample = handle.read(VersionBumper.BINARY_SNIFF_BYTES)
        except OSError:
            return False
        return sample.count(b"\x00") >= VersionBumper.BINARY_NULL_THRESHOLD

    @staticmethod
    def read_text(path):
        """Read a text file, transparently handling UTF-8 BOM."""
        with open(path, "rb") as handle:
            raw = handle.read()
        if raw.startswith(b"\xef\xbb\xbf"):
            return raw[3:].decode("utf-8")
        return raw.decode("utf-8")

    @staticmethod
    def write_text_atomic(path, *, content):
        """Write content to path atomically via a temp file in the same directory."""
        directory = path.parent
        directory.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix=path.name + ".", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
            os.replace(tmp_path, path)
        except OSError:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def process_file(
        self,
        path,
        *,
        output=None,  # noqa: ARG002
        dry_run=False,
        verbose=0,
    ):
        """Process a single file, bumping matched versions on the target line(s)."""
        if not path.is_file():
            return

        if self.is_binary(path):
            self.logger.info(f"Skipping binary file: {path}")
            self.files_skipped += 1
            return

        try:
            content = self.read_text(path)
        except (OSError, UnicodeDecodeError) as err:
            self.logger.warning(f"Skipping unreadable file {path}: {err}")
            self.files_skipped += 1
            return

        new_content, file_changes = self._apply_bumps(content)

        if not file_changes:
            self.logger.info(f"No version match: {path}")
            self.files_skipped += 1
            return

        self._report_changes(
            path,
            file_changes=file_changes,
            dry_run=dry_run,
            verbose=verbose,
        )

        if dry_run:
            self.files_processed += 1
            return

        try:
            self.write_text_atomic(path, content=new_content)
        except OSError as err:
            self.logger.danger(f"Failed to write {path}: {err}")
            self.files_skipped += 1
            return

        self.files_processed += 1

    def _apply_bumps(self, content):
        """Apply bumps in the target line(s); return (content, [(line_no, [(old, new)])])."""
        lines = content.splitlines(keepends=True)
        total = len(lines)
        file_changes = []

        if self.line is not None:
            if self.line < 1 or self.line > total:
                return content, file_changes
            line_indices = [self.line - 1]
        else:
            line_indices = range(total)

        for index in line_indices:
            original = lines[index]
            stripped = original.rstrip("\r\n")
            trailing = original[len(stripped):]
            new_stripped, changes = VersionParser.bump_in_line(
                stripped, kind=self.kind
            )
            if changes:
                file_changes.append((index + 1, changes))
                lines[index] = new_stripped + trailing

        new_content = "".join(lines)
        return new_content, file_changes

    def _report_changes(self, path, *, file_changes, dry_run, verbose):
        """Log bumped versions with appropriate verbosity."""
        prefix = "[DRY RUN] " if dry_run else ""
        if verbose >= 1:
            self.logger.info(f"{prefix}{path}")
        for line_no, changes in file_changes:
            if verbose >= 2:
                self.logger.info(f"  line {line_no}: {len(changes)} bump(s)")
            if verbose >= 3:
                for old, new in changes:
                    self.logger.info(f"    {old} -> {new}")
        if verbose >= 1:
            summary = ", ".join(
                f"{old}->{new}"
                for _line_no, changes in file_changes
                for old, new in changes
            )
            self.logger.success(f"{prefix}bumped: {path} ({summary})")


#--------------------------------------------------
# Kernel: minimal standalone CLI base
#--------------------------------------------------


class Kernel:
    """Minimal standalone CLI base used by the version handler."""

    def __init__(self, *, author, title, description):
        self.author = author
        self.title = title
        self.description = description
        script_file = Path(sys.argv[0]).resolve()
        self.script_file = script_file
        self.name = script_file.stem
        self.logger = None

    def build_early_parser(self):
        """Build the parser for options handled before the required input."""
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--log", action="store_true")
        parser.add_argument("--verbose", "-v", action="count", default=0)
        parser.add_argument(
            "--quiet", action="store_true",
            help="suppress non-error output; runtime errors are still reported",
        )
        parser.add_argument(
            "--completion", action="store_true",
            help="Print bash completion script to stdout and exit",
        )
        return parser

    def build_parser(self):
        """Build and return the base argument parser."""
        parser = argparse.ArgumentParser(description=self.description)
        parser.add_argument("input")
        parser.add_argument("--output")
        parser.add_argument("--recursive", action="store_true")
        parser.add_argument("--include")
        parser.add_argument("--exclude")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--log", action="store_true",
            help="Print the current log and stop",
        )
        parser.add_argument("--verbose", "-v", action="count", default=0)
        parser.add_argument(
            "--quiet", action="store_true",
            help="suppress non-error output; runtime errors are still reported",
        )
        parser.add_argument(
            "--completion", action="store_true",
            help="Print bash completion script to stdout and exit",
        )
        return parser

    def hero(self):
        """Print the application banner."""


#--------------------------------------------------
# VersionBumperApp: CLI entry point
#--------------------------------------------------


class VersionBumperApp(Kernel):
    """CLI application that wires the VersionBumper handler to argparse."""

    def generate_completion(self):
        """Return the bash completion script for this script."""
        return Completion.generate(parser=self.build_parser(), name=self.name)

    def build_parser(self):
        """Build and return argument parser with version-bump specific options."""
        parser = super().build_parser()
        kind_group = parser.add_mutually_exclusive_group()
        kind_group.add_argument(
            "--major",
            action="store_const",
            const="major",
            dest="kind",
            help="Bump the major version (resets minor and fix to 0)",
        )
        kind_group.add_argument(
            "--minor",
            action="store_const",
            const="minor",
            dest="kind",
            help="Bump the minor version (resets fix to 0)",
        )
        kind_group.add_argument(
            "--fix",
            action="store_const",
            const="fix",
            dest="kind",
            help="Bump the fix/patch version (default)",
        )
        parser.set_defaults(kind="fix")
        parser.add_argument(
            "--line",
            type=int,
            default=None,
            help="Only bump the given 1-indexed line (applies per-file in recursive mode)",
        )
        parser.add_argument(
            "--check",
            action="store_true",
            help="Exit non-zero if any file would change (CI gate, implies dry-run)",
        )
        return parser

    def run(self, handler_class=None):
        """Run the handler with parsed CLI arguments."""
        early_args, _ = self.build_early_parser().parse_known_args()
        self.logger = Logger(
            verbose=early_args.verbose, quiet=early_args.quiet
        )
        Console.quiet = early_args.quiet

        if early_args.completion:
            print(self.generate_completion())
            return

        if early_args.log:
            self.logger.print()
            return

        args = self.build_parser().parse_args()
        if handler_class is None:
            handler_class = VersionBumper

        dry_run = args.dry_run or args.check
        handler = handler_class(
            logger=self.logger,
            kind=args.kind,
            line=args.line,
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
                self.logger.info(f"Processing {file_path}")
                handler.process_file(
                    file_path,
                    output=args.output,
                    dry_run=dry_run,
                    verbose=args.verbose,
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

        if args.check and handler.files_processed > 0:
            self.logger.warning("Check mode: changes would be made")
            sys.exit(1)


if __name__ == "__main__":
    kernel = VersionBumperApp(
        author="TangoMan75",
        title="Semantic Versioning",
        description="Auto-increment semver-shaped version numbers in text files.",
    )
    kernel.run(VersionBumper)
