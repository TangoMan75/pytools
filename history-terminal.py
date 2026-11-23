#!/usr/bin/env python3
"""Read shell history and emit a chronological report."""

import argparse
import json
import re
import shlex
import sys
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

# The command preserves source ordering and cross-file deduplication.

#--------------------------------------------------
# DateRange: human date parsing and epoch resolution
#--------------------------------------------------


class DateRange:
    """Resolve human-readable date bounds to epoch seconds."""

    INPUT_FORMATS = (("%Y-%m-%d %H:%M:%S", True), ("%Y-%m-%d", False))

    @classmethod
    def parse(cls, *, value):
        """Parse a date string and return ``(datetime, had_explicit_time)``."""
        for input_format, had_time in cls.INPUT_FORMATS:
            try:
                return datetime.strptime(value, input_format), had_time
            except ValueError:
                continue
        raise ValueError(
            f"invalid date '{value}', expected 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS'"
        )

    @classmethod
    def resolve(cls, *, args):
        """Return ``(start_sec, end_sec)`` in epoch seconds from argparse args."""
        now = datetime.now()
        today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

        start_ms = getattr(args, "start_ms", None)
        end_ms = getattr(args, "end_ms", None)
        if start_ms is not None:
            from_sec = start_ms // 1000
        elif args.start is not None:
            start_dt, had_time = cls.parse(value=args.start)
            if not had_time:
                start_dt = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            from_sec = int(start_dt.timestamp())
        else:
            from_sec = int(today_midnight.timestamp())

        if end_ms is not None:
            to_sec = end_ms // 1000
        elif args.end is not None:
            end_dt, had_time = cls.parse(value=args.end)
            if not had_time:
                end_dt = end_dt.replace(
                    hour=now.hour,
                    minute=now.minute,
                    second=now.second,
                    microsecond=0,
                )
            to_sec = int(end_dt.timestamp())
        else:
            to_sec = int(now.timestamp())

        if to_sec < from_sec:
            raise ValueError("end cannot be set before start")

        return from_sec, to_sec

    @classmethod
    def add_arguments(cls, *, parser):
        """Add --start and --end options to an argparse parser."""
        parser.add_argument(
            "--start", dest="start",
            metavar="YYYY-MM-DD[ HH:MM:SS]",
            help="inclusive start (local). Date-only -> 00:00:00. Default: today 00:00:00.",
        )
        parser.add_argument(
            "--end", dest="end",
            metavar="YYYY-MM-DD[ HH:MM:SS]",
            help="exclusive end (local). Date-only -> 'now'. Default: now.",
        )
        parser.add_argument("--start-ms", dest="start_ms", type=int, metavar="EPOCH_MS")
        parser.add_argument("--end-ms", dest="end_ms", type=int, metavar="EPOCH_MS")

#--------------------------------------------------
# History line parsers
#--------------------------------------------------


class HistoryLineParser(ABC):
    """Parse one shell history line into a normalized mapping."""

    @abstractmethod
    def parse(self, *, line):
        """Return a parsed entry mapping or None for non-entry lines."""


class ZshLineParser(HistoryLineParser):
    """Parse zsh extended-history lines."""

    LINE_PATTERN = re.compile(r": (\d+):\d+;(.*)")
    DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

    def parse(self, *, line):
        """Return the timestamp and command from a zsh history line."""
        match = self.LINE_PATTERN.match(line)
        if not match:
            return None
        timestamp, command = match.groups()
        timestamp_seconds = int(timestamp)
        return {
            "datetime": datetime.fromtimestamp(timestamp_seconds).strftime(self.DATETIME_FORMAT),
            "command": command,
            "_ts_sec": timestamp_seconds,
        }


class BashLineParser(HistoryLineParser):
    """Parse plain bash history lines."""

    def parse(self, *, line):
        """Return the stripped command from a bash history line."""
        command = line.strip()
        if not command:
            return None
        return {"command": command}

#--------------------------------------------------
# HistorySource: history file and parser pairing
#--------------------------------------------------


class HistorySource:
    """A history file paired with its line parser."""

    DEFAULT_PATHS = (
        Path.home() / ".zsh_history",
        Path.home() / ".bash_history",
    )
    PARSERS = {
        ".zsh_history": ZshLineParser,
        ".bash_history": BashLineParser,
    }
    DEFAULT_ENCODING = "utf-8"

    def __init__(self, *, path, parser=None):
        self._path = Path(path)
        self._parser = parser if parser is not None else self._parser_for(path=self._path)

    @classmethod
    def _parser_for(cls, *, path):
        """Return the parser matching the history filename."""
        parser_class = cls.PARSERS.get(path.name, BashLineParser)
        return parser_class()

    def exists(self):
        """Return whether the history file exists."""
        return self._path.exists()

    def entries(self):
        """Yield parsed entries from the history file."""
        with open(
            self._path,
            "r",
            encoding=self.DEFAULT_ENCODING,
            errors="replace",
        ) as handle:
            for line in handle:
                parsed = self._parser.parse(line=line)
                if parsed is not None:
                    yield parsed

#--------------------------------------------------
# TerminalReport: collect and render history entries
#--------------------------------------------------


class TerminalReport:
    """Collect shell history entries and render them as JSON or markdown."""

    JSON_INDENT = 2

    def build(self, *, sources, from_sec, to_sec):
        """Return filtered, deduplicated, and indexed history entries."""
        entries = []
        seen = set()
        for source in sources:
            if not source.exists():
                continue
            for parsed in source.entries():
                if "_ts_sec" in parsed:
                    if not (from_sec <= parsed["_ts_sec"] < to_sec):
                        continue
                dedup_key = parsed.get("datetime", "") + "|" + parsed["command"]
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                entry = {"index": len(entries) + 1, "command": parsed["command"]}
                if "datetime" in parsed:
                    entry["datetime"] = parsed["datetime"]
                entries.append(entry)
        return entries

    @classmethod
    def render_json(cls, *, entries):
        """Render entries as indented JSON."""
        return json.dumps(entries, indent=cls.JSON_INDENT)

    @staticmethod
    def render_markdown(*, entries):
        """Render entries as a markdown table."""
        has_datetime = any("datetime" in entry for entry in entries)
        header = "| # | Command" + (" | Datetime |" if has_datetime else " |")
        separator = "|---" + ("|---" + "|---" + "|---" if has_datetime else "|---") + "|"
        lines = [header, separator]
        for entry in entries:
            command = entry["command"].replace("|", "\\|")
            index = entry["index"]
            if has_datetime:
                lines.append(f"| {index} | {command} | {entry.get('datetime', '')} |")
            else:
                lines.append(f"| {index} | {command} |")
        return "\n".join(lines) + "\n"

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
# HistoryApp: command-line application
#--------------------------------------------------


class HistoryApp:
    """Command-line application for the chronological history report."""

    STDERR_PREFIX = "ERROR: "

    def __init__(self, *, sources=None):
        self._sources = sources

    def build_parser(self):
        """Build the command-line parser."""
        parser = argparse.ArgumentParser()
        DateRange.add_arguments(parser=parser)
        parser.add_argument(
            "--md", action="store_true", help="print output as markdown table"
        )
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
        """Run the history report for the current command-line arguments."""
        if "--completion" in sys.argv:
            print(self.generate_completion())
            return

        args = self.build_parser().parse_args()

        try:
            from_sec, to_sec = DateRange.resolve(args=args)
        except ValueError as err:
            print(f"{self.STDERR_PREFIX}{err}", file=sys.stderr)
            raise SystemExit(2)

        report = TerminalReport()
        entries = report.build(
            sources=self._history_sources(),
            from_sec=from_sec,
            to_sec=to_sec,
        )

        if args.md:
            print(report.render_markdown(entries=entries), end="")
        else:
            print(report.render_json(entries=entries))

    def _history_sources(self):
        """Return the history source objects for this run."""
        paths = self._sources if self._sources is not None else HistorySource.DEFAULT_PATHS
        return [HistorySource(path=path) for path in paths]


if __name__ == "__main__":
    HistoryApp().run()
