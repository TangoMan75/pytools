#!/usr/bin/env python3
"""Convert SQL INSERT statements to CSV.

Handles nested parens, escaped strings, type casts (::type), and
ON CONFLICT / RETURNING clauses.

Usage:
  python3 conv-sql.py file.sql        # writes file.csv beside the input
  python3 conv-sql.py file.sql --output result.csv
"""

import argparse
import csv
import re
import shlex
import sys
from io import StringIO
from pathlib import Path

#--------------------------------------------------
# SqlTokenizer: split SQL value lists and row groups
#--------------------------------------------------


class SqlTokenizer:
    """Split SQL value lists while respecting quoting and nested parens."""

    QUOTES = ("'", '"')

    @staticmethod
    def tokenize_values(*, text):
        """Split a comma-separated value string into individual values,
        respecting nested parens, single-quoted strings, and double-quoted
        identifiers."""
        values = []
        depth = 0
        quote = None
        buf = []

        i = 0
        while i < len(text):
            ch = text[i]

            if quote is not None:
                buf.append(ch)
                if ch == quote and i + 1 < len(text) and text[i + 1] == quote:
                    i += 1
                    buf.append(text[i])
                elif ch == quote:
                    quote = None
            elif ch in SqlTokenizer.QUOTES:
                quote = ch
                buf.append(ch)
            elif ch == '(':
                depth += 1
                buf.append(ch)
            elif ch == ')':
                depth -= 1
                buf.append(ch)
            elif ch == ',' and depth == 0:
                values.append(''.join(buf).strip())
                buf = []
            else:
                buf.append(ch)

            i += 1

        if buf:
            values.append(''.join(buf).strip())

        return values

    @staticmethod
    def split_top_level_parens(*, text):
        """Split a string like (a,b),(c,d) into ['a,b', 'c,d']."""
        groups = []
        depth = 0
        buf = []
        quote = None
        i = 0

        while i < len(text):
            ch = text[i]

            if quote is not None:
                buf.append(ch)
                if ch == quote and i + 1 < len(text) and text[i + 1] == quote:
                    i += 1
                    buf.append(text[i])
                elif ch == quote:
                    quote = None
            elif ch in SqlTokenizer.QUOTES:
                quote = ch
                buf.append(ch)
            elif ch == '(':
                if depth > 0:
                    buf.append(ch)
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    groups.append(''.join(buf).strip())
                    buf = []
                else:
                    buf.append(ch)
            elif ch == ',' and depth == 0:
                pass
            elif depth > 0:
                buf.append(ch)

            i += 1

        return groups

#--------------------------------------------------
# SqlValueParser: strip SQL quoting from scalar values
#--------------------------------------------------


class SqlValueParser:
    """Strip SQL quoting from a value for CSV output.

    Handles:
      'string'              -> string
      'string'::type        -> string::type
      E'string'             -> string  (Postgres escapes)
      B'string', X'string'  -> string
      "ident"               -> ident
    """

    STRING_LITERAL = re.compile(
        r"^(?:([EBX])\s*)?'((?:[^']|'')*)'(::\w+(?:\[\])?)?$",
        re.IGNORECASE,
    )
    QUOTED_IDENTIFIER = re.compile(r'^"((?:[^"]|"")*)"$')

    @staticmethod
    def parse(*, value):
        """Return the unquoted value, keeping an optional SQL cast suffix."""
        match = SqlValueParser.STRING_LITERAL.match(value)
        if match:
            inner = match.group(2).replace("''", "'")
            cast = match.group(3) or ''
            return inner + cast
        match = SqlValueParser.QUOTED_IDENTIFIER.match(value)
        if match:
            return match.group(1).replace('""', '"')
        return value

#--------------------------------------------------
# InsertParser: extract columns and rows from INSERT statements
#--------------------------------------------------


class InsertParser:
    """Parse INSERT INTO table (columns) VALUES (...) statements."""

    INSERT_PATTERN = re.compile(
        r'INSERT\s+INTO\s+(?:\w+\.)?\w+\s*\(([^)]+)\)\s+VALUES\s+',
        re.IGNORECASE,
    )
    TERMINATORS = (' on conflict ', ' returning ', ';')

    def __init__(self, *, tokenizer=None):
        self._tokenizer = tokenizer if tokenizer is not None else SqlTokenizer()

    def extract_values_clause(self, *, sql):
        """Extract the portion after VALUES up to ON CONFLICT / RETURNING / ;."""
        normalized = re.sub(r'\s+', ' ', sql.strip())

        index = normalized.lower().find(' values ')
        if index == -1:
            index = normalized.lower().find('values ')
            if index == -1:
                return None
            index += len('values ')
        else:
            index += len(' values ')

        rest = normalized[index:]

        end = len(rest)
        for keyword in InsertParser.TERMINATORS:
            position = rest.lower().find(keyword)
            if position != -1 and position < end:
                end = position

        return rest[:end].strip()

    def parse(self, *, sql):
        """Parse an INSERT statement returning (columns, rows), or None."""
        normalized = re.sub(r'\s+', ' ', sql.strip()).rstrip(';')

        match = InsertParser.INSERT_PATTERN.match(normalized)
        if not match:
            return None

        columns = [column.strip() for column in match.group(1).split(',')]

        values_part = normalized[match.end():]
        for keyword in InsertParser.TERMINATORS:
            position = values_part.lower().find(keyword)
            if position != -1:
                values_part = values_part[:position]

        values_part = values_part.strip()

        if not values_part:
            return None

        rows = []
        groups = self._tokenizer.split_top_level_parens(text=values_part)
        for group in groups:
            rows.append(self._tokenizer.tokenize_values(text=group))

        return columns, rows

#--------------------------------------------------
# SqlToCsvConverter: convert SQL text to CSV text
#--------------------------------------------------


class SqlToCsvConverter:
    """Convert SQL INSERT statements into quoted CSV text."""

    def __init__(self, *, parser=None, value_parser=None):
        self._parser = parser if parser is not None else InsertParser()
        self._value_parser = value_parser if value_parser is not None else SqlValueParser()

    def convert(self, *, sql):
        """Convert SQL text to CSV text."""
        result = self._parser.parse(sql=sql)
        if not result:
            raise ValueError("No INSERT statement found.")
        columns, rows = result
        stream = StringIO()
        writer = csv.writer(stream, quoting=csv.QUOTE_ALL)
        writer.writerow(columns)
        for row in rows:
            writer.writerow([self._value_parser.parse(value=value) for value in row])
        return stream.getvalue()

#--------------------------------------------------
# OutputPathResolver: derive a CSV destination path
#--------------------------------------------------


class OutputPathResolver:
    """Resolve an output file from an input SQL file and optional destination."""

    SUFFIX = ".csv"

    @staticmethod
    def resolve(*, input_path, output=None):
        """Return the output path for the given input and optional destination."""
        if output:
            destination = Path(output)
            if destination.exists() and destination.is_dir():
                return destination / f"{input_path.stem}{OutputPathResolver.SUFFIX}"
            return destination
        return input_path.with_suffix(OutputPathResolver.SUFFIX)

#--------------------------------------------------
# SqlFileProcessor: convert one SQL file on disk
#--------------------------------------------------


class SqlFileProcessor:
    """Convert SQL files on disk to CSV files."""

    def __init__(self, *, converter=None, resolver=None):
        self._converter = converter if converter is not None else SqlToCsvConverter()
        self._resolver = resolver if resolver is not None else OutputPathResolver()

    def process_file(self, input_path, *, output=None, dry_run=False, quiet=False):
        """Convert one SQL file to a CSV file."""
        destination = self._resolver.resolve(input_path=input_path, output=output)
        content = self._converter.convert(sql=input_path.read_text(encoding="utf-8"))
        if dry_run:
            if not quiet:
                print(f"[DRY RUN] Would write: {destination}")
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        if not quiet:
            print(f"Wrote: {destination}")

#--------------------------------------------------
# Completion: bash completion script generator
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
    def render_case(cls, *, option, kind):
        """Return the bash case branch for the given option kind."""
        return f"        {option})\n{cls.BODIES[kind]}            return 0\n            ;;\n"

    @classmethod
    def render_script(cls, *, all_opts, categories, name):
        """Build the final bash completion script string."""
        blocks = []
        for kind, opts in categories.items():
            for option in sorted(set(opts)):
                blocks.append(cls.render_case(option=option, kind=kind))
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
        return cls.render_script(all_opts=all_opts, categories=categories, name=name)

#--------------------------------------------------
# Kernel: CLI runner
#--------------------------------------------------


class Kernel:
    """CLI application for the SQL to CSV converter."""

    DESCRIPTION = "Convert SQL INSERT statements to CSV files."

    def __init__(self, *, author, title, description, argv=None):
        self._author = author
        self._title = title
        self._description = description
        self._argv = list(sys.argv) if argv is None else list(argv)
        self._name = Path(self._argv[0]).resolve().stem

    def build_parser(self):
        """Build and return the argument parser for the SQL to CSV converter."""
        arg_parser = argparse.ArgumentParser(description=self._description)
        arg_parser.add_argument("input", help="SQL file or directory")
        arg_parser.add_argument("--output", help="Output CSV file or directory")
        arg_parser.add_argument(
            "--recursive",
            action="store_true",
            help="Process directories recursively",
        )
        arg_parser.add_argument("--include", help="Include filter (glob pattern)")
        arg_parser.add_argument("--exclude", help="Exclude filter (glob pattern)")
        arg_parser.add_argument("--dry-run", action="store_true", help="Do not write output files")
        arg_parser.add_argument("--log", action="store_true", help="Reserved for CLI consistency")
        arg_parser.add_argument("--verbose", "-v", action="count", default=0)
        arg_parser.add_argument("--quiet", action="store_true",
                                help="suppress non-error output; runtime errors are still reported")
        arg_parser.add_argument(
            "--completion",
            action="store_true",
            help="Print bash completion script to stdout and exit",
        )
        return arg_parser

    def generate_completion(self):
        """Return the bash completion script for this script."""
        return Completion.generate(parser=self.build_parser(), name=self._name)

    @staticmethod
    def _select_paths(*, source, args):
        """Return the files selected by the parsed CLI arguments."""
        paths = [source] if source.is_file() else sorted(
            (source.rglob("*") if args.recursive else source.glob("*"))
        )
        return [
            path for path in paths
            if path.is_file()
            and (not args.include or path.match(args.include))
            and (not args.exclude or not path.match(args.exclude))
        ]

    def run(self, processor=None):
        """Run the converter over every path selected by the CLI arguments."""
        if "--completion" in self._argv:
            print(self.generate_completion())
            return

        arg_parser = self.build_parser()
        args = arg_parser.parse_args(self._argv[1:])

        source = Path(args.input)
        if not source.exists():
            arg_parser.error(f"input path not found: {source}")

        paths = self._select_paths(source=source, args=args)
        if not paths:
            raise SystemExit("No SQL files found.")

        processor = processor if processor is not None else SqlFileProcessor()
        try:
            for path in paths:
                processor.process_file(
                    path,
                    output=args.output,
                    dry_run=args.dry_run,
                    quiet=args.quiet,
                )
        except (OSError, ValueError) as error:
            arg_parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    Kernel(
        author='TangoMan75',
        title='SQL to CSV Converter',
        description=Kernel.DESCRIPTION,
    ).run()
