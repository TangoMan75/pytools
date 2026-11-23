#!/usr/bin/env python3
"""Report OpenCode sessions and messages."""

import argparse
import json
import os
import platform
import re
import shlex
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

#--------------------------------------------------
# Dates: date parsing and window math
#--------------------------------------------------


class Dates:
    """Parse dates and compute epoch ranges for OpenCode reports."""

    TZ_PARIS = timezone(timedelta(hours=2))
    DATE_FORMAT = "%Y-%m-%d"
    DATETIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d")
    EPOCH_PATTERN = r"^-?\d+$"

    @staticmethod
    def parse_date(value):
        """Validate a 'YYYY-MM-DD' string and return it unchanged.

        On bad input, prints an error to stderr and exits with code 2.
        """
        try:
            return datetime.strptime(value, Dates.DATE_FORMAT).date().isoformat()
        except ValueError:
            print(f"ERROR: invalid date '{value}', expected YYYY-MM-DD", file=sys.stderr)
            sys.exit(2)

    @staticmethod
    def _parse_flexible(raw):
        """Parse various date/time strings and return a date.

        Accepts YYYY-MM-DD, YYYY-MM-DD HH:MM, YYYY-MM-DD HH:MM:SS,
        epoch seconds (e.g. "2147483647"), and ISO 8601.
        """
        text = raw.strip()
        if re.match(Dates.EPOCH_PATTERN, text):
            try:
                return datetime.fromtimestamp(int(text)).date()
            except (OSError, OverflowError, ValueError):
                pass
        if "T" in text:
            normalized = text[:-1] + "+00:00" if text[-1] in ("Z", "z") else text
            try:
                return datetime.fromisoformat(normalized).date()
            except ValueError:
                pass
        for date_format in Dates.DATETIME_FORMATS:
            try:
                return datetime.strptime(text, date_format).date()
            except ValueError:
                continue
        raise ValueError(
            f'invalid date "{raw}". '
            f"Use YYYY-MM-DD, YYYY-MM-DD HH:MM, YYYY-MM-DD HH:MM:SS, "
            f"epoch seconds, or ISO 8601."
        )

    @staticmethod
    def resolve_date(raw):
        """Parse a date string in various formats and return 'YYYY-MM-DD'.

        Raises ValueError on bad input.
        """
        return Dates._parse_flexible(raw).isoformat()

    @staticmethod
    def compute_prev_date(target):
        """Return the calendar day before `target` (a 'YYYY-MM-DD' string)."""
        day = datetime.strptime(target, Dates.DATE_FORMAT)
        return (day - timedelta(days=1)).strftime(Dates.DATE_FORMAT)

    @staticmethod
    def compute_epoch_range(target):
        """Return (start_ms, end_ms) for the day `target` in Europe/Paris (UTC+2).

        The end is the start of the next day, matching how `history-opencode.py`
        queries `time_created` (exclusive upper bound).
        """
        local = datetime.strptime(target, Dates.DATE_FORMAT).replace(tzinfo=Dates.TZ_PARIS)
        start = int(local.timestamp() * 1000)
        end = int((local + timedelta(days=1)).timestamp() * 1000)
        return start, end

    @staticmethod
    def _compute_window_range(*, target, days_before):
        """Return an epoch range ending after `target`, including prior days."""
        target_date = datetime.strptime(target, Dates.DATE_FORMAT).date()
        start_date = target_date - timedelta(days=days_before)
        start, _ = Dates.compute_epoch_range(start_date.isoformat())
        end, _ = Dates.compute_epoch_range((target_date + timedelta(days=1)).isoformat())
        return start, end

    @staticmethod
    def compute_week_range(target):
        """Return (start_ms, end_ms) for `target` and the six preceding days."""
        return Dates._compute_window_range(target=target, days_before=6)

    @staticmethod
    def compute_month_range(target):
        """Return (start_ms, end_ms) for `target` and the 30 preceding days."""
        return Dates._compute_window_range(target=target, days_before=30)

    @staticmethod
    def compute_calendar_range(target):
        """Return (tmin_iso, tmax_iso) for the day `target` in Europe/Paris.

        tmin is the start of the day (00:00:00), tmax is the end of the
        day (23:59:59). Both are ISO-8601 strings with the +02:00 offset,
        suitable for the Google Calendar `events.list` API.
        """
        day = datetime.strptime(target, Dates.DATE_FORMAT).replace(tzinfo=Dates.TZ_PARIS)
        tmin = day.isoformat()
        tmax = day.replace(hour=23, minute=59, second=59).isoformat()
        return tmin, tmax

    @staticmethod
    def daterange(*, start, end):
        """Yield 'YYYY-MM-DD' strings from `start` to `end` inclusive.

        Exits with code 2 if `end` is before `start` or either is malformed.
        """
        first = datetime.strptime(start, Dates.DATE_FORMAT).date()
        last = datetime.strptime(end, Dates.DATE_FORMAT).date()
        if last < first:
            print(f"ERROR: end {end} is before start {start}", file=sys.stderr)
            sys.exit(2)
        day = first
        while day <= last:
            yield day.isoformat()
            day += timedelta(days=1)

    @staticmethod
    def default_end_ms(from_ms):
        """Return exclusive end = midnight of the next calendar day after from_ms."""
        local = datetime.fromtimestamp(from_ms / 1000, tz=timezone.utc).astimezone()
        next_midnight = datetime.combine(
            local.date() + timedelta(days=1), datetime.min.time(), tzinfo=local.tzinfo
        )
        return int(next_midnight.timestamp() * 1000)

#--------------------------------------------------
# DateRangeArgs: --start/--end argument handling
#--------------------------------------------------


class DateRangeArgs:
    """Register and resolve human or epoch-millisecond date-range options."""

    @staticmethod
    def add_date_range_args(parser):
        """Add --start, --end, --start-ms, --end-ms to an argparse parser.

        The resulting attributes are ``args.start`` (human string),
        ``args.end`` (human string), ``args.start_ms`` and ``args.end_ms``
        (epoch ms).
        """
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
        parser.add_argument(
            "--start-ms", dest="start_ms",
            type=int,
            metavar="EPOCH_MS",
            help="inclusive start as epoch ms (UTC). Mutually exclusive with --start.",
        )
        parser.add_argument(
            "--end-ms", dest="end_ms",
            type=int,
            metavar="EPOCH_MS",
            help="exclusive end as epoch ms (UTC). Mutually exclusive with --end.",
        )

    @staticmethod
    def parse_human(value):
        """Parse 'YYYY-MM-DD HH:MM:SS' or 'YYYY-MM-DD'.

        Returns (datetime, had_explicit_time).
        """
        for date_format, had_time in (("%Y-%m-%d %H:%M:%S", True), ("%Y-%m-%d", False)):
            try:
                return datetime.strptime(value, date_format), had_time
            except ValueError:
                continue
        raise ValueError(
            f"invalid date '{value}', expected 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS'"
        )

    @staticmethod
    def resolve(args):
        """Return (start_ms, end_ms) in UTC epoch ms from an argparse Namespace.

        Raises ValueError on invalid combinations.
        """
        now = datetime.now()
        today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

        if args.start_ms is not None and args.start is not None:
            raise ValueError("pass only one of --start or --start-ms (not both)")
        if args.start_ms is not None:
            from_ms = args.start_ms
        elif args.start is not None:
            start, had_time = DateRangeArgs.parse_human(args.start)
            if not had_time:
                start = start.replace(hour=0, minute=0, second=0, microsecond=0)
            from_ms = int(start.timestamp() * 1000)
        else:
            from_ms = int(today_midnight.timestamp() * 1000)

        if args.end_ms is not None and args.end is not None:
            raise ValueError("pass only one of --end or --end-ms (not both)")
        if args.end_ms is not None:
            to_ms = args.end_ms
        elif args.end is not None:
            end, had_time = DateRangeArgs.parse_human(args.end)
            if not had_time:
                end = end.replace(
                    hour=now.hour, minute=now.minute, second=now.second, microsecond=0
                )
            to_ms = int(end.timestamp() * 1000)
        else:
            to_ms = int(now.timestamp() * 1000)

        if to_ms < from_ms:
            raise ValueError("end cannot be set before start")

        return from_ms, to_ms

    @staticmethod
    def resolve_date_range(args):
        """Return (start_ms, end_ms) from an argparse Namespace.

        On any validation error, prints a human-readable message to stderr
        and exits 2.
        """
        try:
            return DateRangeArgs.resolve(args)
        except ValueError as error:
            print(f"ERROR: {error}", file=sys.stderr)
            sys.exit(2)

#--------------------------------------------------
# Formatting: shared display helpers
#--------------------------------------------------


class Formatting:
    """Render timestamps, durations, costs, and safe Markdown text."""

    @staticmethod
    def to_local(ms):
        """Return an ISO-8601 timestamp in the local timezone."""
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone().isoformat()

    @staticmethod
    def format_duration(seconds):
        """Render a duration compactly by magnitude."""
        if seconds < 60:
            return f"{seconds:.0f}s"
        if seconds < 3600:
            return f"{int(seconds // 60)}m{int(seconds % 60):02d}s"
        return f"{int(seconds // 3600)}h{int((seconds % 3600) // 60):02d}m"

    @staticmethod
    def format_cost(cost):
        """Render a cost with sensible precision."""
        if cost is None or cost == 0:
            return "$0"
        if cost < 0.01:
            return f"${cost:.4f}"
        return f"${cost:.3f}"

    @staticmethod
    def format_hhmm(local_iso):
        """Return the HH:MM part of a local ISO timestamp."""
        return local_iso[11:16] if local_iso else ""

    @staticmethod
    def format_range_title(*, from_ms, to_ms):
        """Return a single date or a 'start -> end' title."""
        start = datetime.fromtimestamp(from_ms / 1000).date().isoformat()
        end = datetime.fromtimestamp(to_ms / 1000).date().isoformat()
        return start if start == end else f"{start} \u2192 {end}"

    @staticmethod
    def escape(value):
        """Escape pipes and newlines for a Markdown table cell."""
        if value is None:
            return ""
        return str(value).replace("|", "\\|").replace("\n", " ").strip()

    @staticmethod
    def truncate(*, text, limit):
        """Collapse newlines and truncate text with an ellipsis."""
        if text is None:
            return ""
        value = str(text).replace("\n", " ").strip()
        return value if len(value) <= limit else value[: limit - 1] + "\u2026"

    @staticmethod
    def is_tool_artefact(text):
        """Return True when the text looks like a tool call or tool output."""
        if not text:
            return True
        stripped = text.strip()
        if not stripped:
            return True
        if stripped.startswith("Called the "):
            return True
        if stripped.startswith("<") and stripped.endswith(">"):
            return True
        return len(stripped) < 40

    @staticmethod
    def normalize(text):
        """Normalize CRLF and trim surrounding whitespace."""
        if not text:
            return ""
        return text.replace("\r\n", "\n").strip()

#--------------------------------------------------
# Markdown: report rendering
#--------------------------------------------------


class Markdown:
    """Render OpenCode sessions and messages as Markdown."""

    SESSION_TABLE_HEADER = "| Start | Duration | Model | Agent | Title | Files | +/- | Cost |"
    SESSION_TABLE_RULE = "|-------|----------|-------|-------|-------|-------|-----|------|"

    @classmethod
    def sessions(cls, records):
        """Render the session summary table and totals."""
        if not records:
            return "_No sessions in this range._\n"

        lines = [cls.SESSION_TABLE_HEADER, cls.SESSION_TABLE_RULE]
        for record in records:
            diff = f"{record['additions'] or 0}/{record['deletions'] or 0}"
            lines.append(
                "| {start} | {duration} | {model} | {agent} | {title} | "
                "{files} | {diff} | {cost} |".format(
                    start=Formatting.format_hhmm(record["start_local"]),
                    duration=Formatting.format_duration(record["duration_seconds"]),
                    model=Formatting.escape(
                        Formatting.truncate(text=record["model"], limit=20)
                    ),
                    agent=Formatting.escape(record["agent"] or ""),
                    title=Formatting.escape(
                        Formatting.truncate(text=record["title"], limit=60)
                    ),
                    files=record["files"] or 0,
                    diff=diff,
                    cost=Formatting.format_cost(record["cost"]),
                )
            )

        total_duration = sum(record["duration_seconds"] for record in records)
        total_cost = sum(record["cost"] or 0 for record in records)
        total_in = sum(record["tokens_in"] or 0 for record in records)
        total_out = sum(record["tokens_out"] or 0 for record in records)
        total_files = sum(record["files"] or 0 for record in records)
        lines.append("")
        lines.append(
            f"**Total:** {len(records)} sessions, "
            f"{Formatting.format_duration(total_duration)} total, "
            f"{total_in:,} in / {total_out:,} out tokens, "
            f"{Formatting.format_cost(total_cost)}, {total_files} files edited"
        )
        return "\n".join(lines) + "\n"

    @classmethod
    def messages(cls, records):
        """Render the first user and last assistant messages per session."""
        if not records:
            return "_No session messages in this range._\n"

        lines = []
        for record in records:
            lines.append(f"## `{record['id']}`")
            lines.append("")
            lines.append("**First user:**")
            lines.append("")
            lines.append(f"> {Formatting.normalize(record['first_user']) or '_(none)_'}")
            lines.append("")
            lines.append("**Last assistant:**")
            lines.append("")
            lines.append(
                f"> {Formatting.normalize(record['last_assistant']) or '_(none)_'}"
            )
            if record.get("last_reasoning"):
                lines.append("")
                lines.append("**Last reasoning:**")
                lines.append("")
                lines.append(f"> {Formatting.normalize(record['last_reasoning'])}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    @classmethod
    def report(cls, *, sessions, from_ms, to_ms):
        """Render the complete Markdown report."""
        title = Formatting.format_range_title(from_ms=from_ms, to_ms=to_ms)
        parts = [
            f"# opencode Memory \u2014 {title}",
            "",
            "## Sessions",
            "",
            cls.sessions(sessions),
            "",
            "## Session Messages",
            "",
            cls.messages(sessions),
        ]
        return "\n".join(parts)

#--------------------------------------------------
# SessionRepository: SQLite access
#--------------------------------------------------


class SessionRepository:
    """Read OpenCode sessions and messages from a SQLite connection."""

    V1_SESSION_TABLE = "session"
    V2_SESSION_TABLE = "session_v2"

    def __init__(self, *, connection):
        self._connection = connection

    @staticmethod
    def default_path():
        """Return the platform-specific default OpenCode database path."""
        system = platform.system()
        if system == "Windows":
            appdata = os.environ.get("APPDATA", "")
            return os.path.join(appdata, "opencode", "opencode.db") if appdata else ""
        if system == "Darwin":
            return os.path.expanduser("~/Library/Application Support/opencode/opencode.db")
        return os.path.expanduser("~/.local/share/opencode/opencode.db")

    def _table_exists(self, name):
        """Return True when the named table exists."""
        row = self._connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        return row is not None

    def is_v2(self):
        """Return True when the database uses the OpenCode v2 schema."""
        return self._table_exists(self.V2_SESSION_TABLE)

    def session_table(self):
        """Return the session table name matching the database schema.

        v2 keeps the same columns as v1 but stores sessions in ``session_v2``.
        """
        if self._table_exists(self.V2_SESSION_TABLE):
            return self.V2_SESSION_TABLE
        if self._table_exists(self.V1_SESSION_TABLE):
            return self.V1_SESSION_TABLE
        raise sqlite3.OperationalError(
            "no opencode session table found; expected 'session_v2' (v2) or 'session' (v1)"
        )

    def fetch_sessions(self, *, from_ms, to_ms):
        """Return session records created inside the given epoch range."""
        table = self.session_table()
        cursor = self._connection.cursor()
        cursor.execute(
            "SELECT id, title, directory, time_created, time_updated, model, "
            "agent, cost, tokens_input, tokens_output, "
            "summary_files, summary_additions, summary_deletions "
            f"FROM {table} "
            "WHERE time_created>=? AND time_created<? "
            "ORDER BY time_created ASC",
            (from_ms, to_ms),
        )
        records = []
        for row in cursor.fetchall():
            try:
                model = json.loads(row[5] or "{}")
            except json.JSONDecodeError:
                model = {}
            time_created, time_updated = row[3], row[4]
            records.append(
                {
                    "id": row[0],
                    "title": row[1],
                    "directory": row[2],
                    "time_created": time_created,
                    "time_updated": time_updated,
                    "start_local": Formatting.to_local(time_created),
                    "end_local": Formatting.to_local(time_updated),
                    "duration_seconds": (time_updated - time_created) / 1000.0,
                    "model": model.get("id", ""),
                    "provider": model.get("providerID", ""),
                    "agent": row[6],
                    "cost": row[7],
                    "tokens_in": row[8],
                    "tokens_out": row[9],
                    "files": row[10],
                    "additions": row[11],
                    "deletions": row[12],
                }
            )
        return records

    @staticmethod
    def _empty_message_entry():
        """Return the empty message summary for one session."""
        return {"first_user": None, "last_assistant": None, "last_reasoning": None}

    @staticmethod
    def _apply_part(*, entry, role, part_type, text):
        """Store one message part in the session summary."""
        if role == "user" and part_type == "text" and entry["first_user"] is None:
            entry["first_user"] = text
        elif role == "assistant" and part_type == "text" and not Formatting.is_tool_artefact(text):
            entry["last_assistant"] = text
        elif role == "assistant" and part_type == "reasoning":
            entry["last_reasoning"] = text

    def _fetch_messages_v1(self, session_ids):
        """Read messages from the v1 message/part tables."""
        result = {}
        cursor = self._connection.cursor()
        for session_id in session_ids:
            cursor.execute(
                "SELECT m.data, p.data "
                "FROM message m JOIN part p ON p.message_id=m.id "
                "WHERE m.session_id=? AND json_extract(p.data, '$.type') IN ('text','reasoning') "
                "ORDER BY m.time_created, p.time_created",
                (session_id,),
            )
            entry = self._empty_message_entry()
            for message_data, part_data in cursor.fetchall():
                try:
                    message = json.loads(message_data)
                    part = json.loads(part_data)
                except json.JSONDecodeError:
                    continue
                text = (part.get("text") or "").strip()
                if not text:
                    continue
                self._apply_part(
                    entry=entry,
                    role=message.get("role"),
                    part_type=part.get("type"),
                    text=text,
                )
            result[session_id] = entry
        return result

    def _fetch_messages_v2(self, session_ids):
        """Read messages stored in OpenCode v2's ``session_message`` table.

        v2 keeps the whole message in a single ``data`` JSON document: user
        messages carry a ``text`` field, assistant messages carry a ``content``
        list of text/reasoning/tool parts.
        """
        result = {}
        cursor = self._connection.cursor()
        for session_id in session_ids:
            cursor.execute(
                "SELECT type, data FROM session_message "
                "WHERE session_id=? AND type IN ('user','assistant') "
                "ORDER BY seq",
                (session_id,),
            )
            entry = self._empty_message_entry()
            for message_type, message_data in cursor.fetchall():
                try:
                    message = json.loads(message_data)
                except json.JSONDecodeError:
                    continue
                if message_type == "user":
                    text = (message.get("text") or "").strip()
                    if text:
                        self._apply_part(
                            entry=entry, role="user", part_type="text", text=text
                        )
                    continue
                for part in message.get("content") or []:
                    if not isinstance(part, dict):
                        continue
                    part_type = part.get("type")
                    if part_type not in ("text", "reasoning"):
                        continue
                    text = (part.get("text") or "").strip()
                    if text:
                        self._apply_part(
                            entry=entry,
                            role="assistant",
                            part_type=part_type,
                            text=text,
                        )
            result[session_id] = entry
        return result

    def fetch_messages(self, session_ids):
        """Return the message summary for each given session id."""
        if self.is_v2():
            return self._fetch_messages_v2(session_ids)
        return self._fetch_messages_v1(session_ids)

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

    @classmethod
    def _classify_parser_actions(cls, parser):
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
        """Return a bash completion script string for the given parser."""
        all_opts, categories = cls._classify_parser_actions(parser)
        return cls._render_script(all_opts=all_opts, categories=categories, name=name)

#--------------------------------------------------
# Application: command-line entry point
#--------------------------------------------------


class Application:
    """Command-line application for the OpenCode history report."""

    DESCRIPTION = "Combine opencode session summaries and per-session messages."

    def __init__(self, *, argv=None, stdout=None, stderr=None):
        self._argv = list(sys.argv if argv is None else argv)
        self._stdout = stdout if stdout is not None else sys.stdout
        self._stderr = stderr if stderr is not None else sys.stderr

    def build_parser(self):
        """Build the command-line parser."""
        default_db = SessionRepository.default_path()
        parser = argparse.ArgumentParser(description=self.DESCRIPTION)
        parser.add_argument(
            "--db", default=default_db,
            help=f"opencode SQLite DB (default: {default_db})",
        )
        DateRangeArgs.add_date_range_args(parser)
        parser.add_argument("--md", action="store_true", help="print as markdown instead of JSON")
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

    def completion_script(self):
        """Return the bash completion script for this command."""
        return Completion.generate(
            parser=self.build_parser(),
            name=Path(self._argv[0]).resolve().stem,
        )

    def run(self):
        """Run the report and return the process exit code."""
        if "--completion" in self._argv:
            print(self.completion_script(), file=self._stdout)
            return 0

        args = self.build_parser().parse_args(self._argv[1:])
        from_ms, to_ms = DateRangeArgs.resolve_date_range(args)
        if args.end is None and args.end_ms is None:
            to_ms = Dates.default_end_ms(from_ms)

        sessions = self._load_sessions(db=args.db, from_ms=from_ms, to_ms=to_ms)
        if sessions is None:
            return 1
        self._emit(args=args, sessions=sessions, from_ms=from_ms, to_ms=to_ms)
        return 0

    def _load_sessions(self, *, db, from_ms, to_ms):
        """Return sessions with messages attached, or None on a missing schema."""
        connection = sqlite3.connect(db)
        repository = SessionRepository(connection=connection)
        try:
            try:
                sessions = repository.fetch_sessions(from_ms=from_ms, to_ms=to_ms)
            except sqlite3.OperationalError as error:
                print(f"ERROR: {error}", file=self._stderr)
                return None
            try:
                messages = repository.fetch_messages(
                    session_ids=[session["id"] for session in sessions]
                )
            except sqlite3.OperationalError:
                messages = {}
        finally:
            connection.close()

        for session in sessions:
            entry = messages.get(session["id"], {})
            session["first_user"] = entry.get("first_user")
            session["last_assistant"] = entry.get("last_assistant")
            session["last_reasoning"] = entry.get("last_reasoning")
        return sessions

    def _emit(self, *, args, sessions, from_ms, to_ms):
        """Write the JSON or Markdown report to standard output."""
        if args.md:
            report = Markdown.report(sessions=sessions, from_ms=from_ms, to_ms=to_ms)
            print(report, end="", file=self._stdout)
            return
        print(json.dumps(sessions, ensure_ascii=False), file=self._stdout)


if __name__ == "__main__":
    raise SystemExit(Application().run())
