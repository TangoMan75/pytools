#!/usr/bin/env python3
"""Index dated markdown backlog files and emit JSON or Markdown."""

import argparse
import json
import os
import re
import shlex
import sys
from datetime import datetime, timedelta
from pathlib import Path

#--------------------------------------------------
# DateRange: date validation and expansion
#--------------------------------------------------


class DateRange:
    """Validate input dates and expand inclusive date ranges."""

    INPUT_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d")
    DATE_FORMAT = "%Y-%m-%d"

    @classmethod
    def parse(cls, *, value):
        """Validate a date bound and return it as ``YYYY-MM-DD``."""
        for input_format in cls.INPUT_FORMATS:
            try:
                return datetime.strptime(value, input_format).date().isoformat()
            except ValueError:
                continue
        print(
            f"ERROR: invalid date '{value}', expected YYYY-MM-DD or YYYY-MM-DD HH:MM:SS",
            file=sys.stderr,
        )
        sys.exit(2)

    @classmethod
    def days(cls, *, start, end):
        """Yield ``YYYY-MM-DD`` strings from start to end inclusive."""
        start_date = datetime.strptime(start, cls.DATE_FORMAT).date()
        end_date = datetime.strptime(end, cls.DATE_FORMAT).date()
        if end_date < start_date:
            print(f"ERROR: end {end} is before start {start}", file=sys.stderr)
            sys.exit(2)
        current = start_date
        while current <= end_date:
            yield current.isoformat()
            current += timedelta(days=1)

#--------------------------------------------------
# BacklogIndex: index one markdown file
#--------------------------------------------------


class BacklogIndex:
    """Build an index record for one dated markdown file."""

    TAG_PATTERN = re.compile(
        r"#(article|backup|bookmark|bug|closed|contact|doing|done|how-to|"
        r"merged|message|note|pinned|post|pr|review|shippeo|snippet|task|"
        r"theodo|todo|tweet)\b"
    )
    SECTION_PATTERN = re.compile(r"^## (.+)$", flags=re.MULTILINE)
    MAX_SECTIONS = 30
    DEFAULT_ENCODING = "utf-8"

    @classmethod
    def build(cls, *, path, file_date):
        """Return the index record for the file at path."""
        content = Path(path).read_text(encoding=cls.DEFAULT_ENCODING)
        return {
            "date": file_date,
            "file": path,
            "size": len(content),
            "sections": cls.SECTION_PATTERN.findall(content)[:cls.MAX_SECTIONS],
            "tags": sorted(set(cls.TAG_PATTERN.findall(content))),
        }

#--------------------------------------------------
# BacklogReport: render indexed records
#--------------------------------------------------


class BacklogReport:
    """Render backlog records as a markdown document."""

    BYTE_LIMIT = 1024
    KILOBYTE_LIMIT = 1024 * 1024

    @classmethod
    def format_size(cls, *, size):
        """Format a character count as bytes, kilobytes, or megabytes."""
        if size < cls.BYTE_LIMIT:
            return f"{size} B"
        if size < cls.KILOBYTE_LIMIT:
            return f"{size / cls.BYTE_LIMIT:.1f} KB"
        return f"{size / cls.KILOBYTE_LIMIT:.1f} MB"

    @classmethod
    def render(cls, *, records, from_date, to_date):
        """Render records as a markdown backlog index."""
        title = from_date if from_date == to_date else f"{from_date} → {to_date}"
        if not records:
            return f"# Backlog index for {title}\n\n_No files in this range._\n"

        lines = [f"# Backlog index for {title}", ""]
        for record in records:
            lines.append(f"## `{os.path.basename(record['file'])}`")
            lines.append("")
            lines.append(f"- **Date:** {record['date']}")
            lines.append(f"- **Path:** `{record['file']}`")
            lines.append(f"- **Size:** {cls.format_size(size=record['size'])}")
            if record["tags"]:
                tags = " ".join(f"#{tag}" for tag in record["tags"])
                lines.append(f"- **Tags:** {tags}")
            if record["sections"]:
                lines.append("- **Sections:**")
                for section in record["sections"]:
                    lines.append(f"  - {section}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

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
# BacklogApp: command-line application
#--------------------------------------------------


class BacklogApp:
    """Command-line application for the backlog index."""

    DEFAULT_DIRECTORY = os.path.expanduser("~/Dropbox")
    DESCRIPTION = "Index markdown files in a directory by date prefix, over a date range."

    def build_parser(self):
        """Build the command-line parser."""
        today = datetime.now().date().isoformat()
        parser = argparse.ArgumentParser(description=self.DESCRIPTION)
        parser.add_argument("--start", default=today,
                            help=f"inclusive start date YYYY-MM-DD (default: {today})")
        parser.add_argument("--end", default=today,
                            help=f"inclusive end date YYYY-MM-DD (default: {today})")
        parser.add_argument("--directory", default=self.DEFAULT_DIRECTORY,
                            help=f"source directory (default: {self.DEFAULT_DIRECTORY})")
        parser.add_argument("--md", action="store_true", help="print as a markdown document")
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

    def run(self):
        """Run the backlog index and return the process exit code."""
        if "--completion" in sys.argv:
            print(self.generate_completion())
            return 0

        args = self.build_parser().parse_args()
        from_date = DateRange.parse(value=args.start)
        to_date = DateRange.parse(value=args.end)

        if not os.path.isdir(args.directory):
            print(f"ERROR: directory not found: {args.directory}", file=sys.stderr)
            return 1

        records = self._collect(
            directory=args.directory,
            from_date=from_date,
            to_date=to_date,
        )

        if args.md:
            print(BacklogReport.render(
                records=records,
                from_date=from_date,
                to_date=to_date,
            ), end="")
        else:
            print(json.dumps(records, ensure_ascii=False))
        return 0

    @staticmethod
    def _collect(*, directory, from_date, to_date):
        """Collect index records for the markdown files in the range."""
        records = []
        entries = sorted(os.listdir(directory))
        for target_date in DateRange.days(start=from_date, end=to_date):
            prefix = target_date + "_"
            for filename in entries:
                if not (filename.startswith(prefix) and filename.endswith(".md")):
                    continue
                records.append(BacklogIndex.build(
                    path=os.path.join(directory, filename),
                    file_date=target_date,
                ))
        return records


if __name__ == "__main__":
    raise SystemExit(BacklogApp().run())
