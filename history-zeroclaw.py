#!/usr/bin/env python3
"""Report ZeroClaw sessions and chat messages.

Combine zeroclaw session metadata with the full chat log in range.

zeroclaw sessions are long-lived chat channels (one per `session_key`),
so this script emits the entire chronological message history for the
query window rather than first/last messages.

JSON mode (default):
  [{"id", "title", "time_created", "time_updated",
    "start_local", "end_local", "duration_seconds",
    "agent", "model", "provider", "cost",
    "tokens_in", "tokens_out", "files", "additions", "deletions",
    "message_count", "state",
    "channel_id", "room_id", "sender_id",
    "messages": [
        {"role", "content", "time_created", "created_at_local"}, ...
    ]}, ...]

  Only `role` = "user" or "assistant" are included (tool calls are
  discarded).

Markdown mode (--md):
  # zeroclaw Memory — {date range}
  ## Sessions (table)
  ## Chat Log (per session, chronological)

Args (all optional):
    --db:                    path to zeroclaw SQLite DB
                             (default: ~/.zeroclaw/data/sessions/sessions.db)
    --start, --end:          "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS" (local)
    --start-ms, --end-ms:    epoch ms (UTC)
    --md:                    print as markdown instead of JSON

  When neither --end nor --end-ms is given the query defaults to a single
  calendar day: end = midnight of the day after start (or tomorrow if no
  start given). To query a longer window pass an explicit --end or --end-ms.

Filtering: a session is included when its [created_at, last_activity)
window overlaps the [start, end) range. Each included session then
contributes only the messages whose own created_at falls in [start, end).

zeroclaw schema reference (from ~/.zeroclaw/data/sessions/sessions.db):

  sessions(id, session_key, role, content, created_at)
      role: 'user' | 'assistant' | 'tool'
      user content is prefixed with "[YYYY-MM-DD HH:MM:SS +ZZ:ZZ] "
      tool content is JSON: {"content": "...", "tool_call_id": "..."}
      created_at is an ISO-8601 string with timezone offset

  session_metadata(session_key, created_at, last_activity, message_count,
                   name, state, turn_id, turn_started_at,
                   agent_alias, channel_id, room_id, sender_id)
"""

import argparse
import json
import os
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
    """Parse dates and compute epoch ranges for ZeroClaw reports."""

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
    def parse_iso(value):
        """Return epoch milliseconds for an ISO-8601 timestamp."""
        if not value:
            return 0
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp() * 1000)

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
    """Render timestamps and safe Markdown text for ZeroClaw reports."""

    USER_PREFIX_RE = re.compile(
        r"^\s*\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\s*[+-]\d{2}:\d{2})?)\]\s*"
    )

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
    def format_hms(local_iso):
        """Return the HH:MM:SS part of a local ISO timestamp."""
        return local_iso[11:19] if local_iso else ""

    @staticmethod
    def format_date(local_iso):
        """Return the YYYY-MM-DD part of a local ISO timestamp."""
        return local_iso[:10] if local_iso else ""

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

    @classmethod
    def strip_user_prefix(cls, text):
        """Remove a leading bracketed timestamp from user content."""
        if not text:
            return ""
        return cls.USER_PREFIX_RE.sub("", text, count=1).strip()

#--------------------------------------------------
# Markdown: report rendering
#--------------------------------------------------


class Markdown:
    """Render ZeroClaw sessions and chat messages as Markdown."""

    SESSION_TABLE_HEADER = "| Start | Duration | Channel | Title | Msgs | State |"
    SESSION_TABLE_RULE = "|-------|----------|---------|-------|------|-------|"

    @classmethod
    def sessions(cls, records):
        """Render the session summary table and totals."""
        if not records:
            return "_No sessions in this range._\n"

        lines = [cls.SESSION_TABLE_HEADER, cls.SESSION_TABLE_RULE]
        for record in records:
            lines.append(
                "| {start} | {duration} | {channel} | {title} | {count} | {state} |".format(
                    start=(
                        Formatting.format_date(record["start_local"])[5:]
                        + " "
                        + Formatting.format_hms(record["start_local"])
                    ),
                    duration=Formatting.format_duration(record["duration_seconds"]),
                    channel=Formatting.escape(
                        Formatting.truncate(text=record.get("channel_id") or "", limit=24)
                    ),
                    title=Formatting.escape(
                        Formatting.truncate(text=record.get("title") or "", limit=60)
                    ),
                    count=len(record.get("messages", [])),
                    state=Formatting.escape(record.get("state") or ""),
                )
            )

        total_messages = sum(len(record.get("messages", [])) for record in records)
        lines.append("")
        lines.append(
            f"**Total:** {len(records)} sessions, {total_messages} messages in range"
        )
        return "\n".join(lines) + "\n"

    @classmethod
    def message_block(cls, message):
        """Render one chat message as a stamped blockquote."""
        role = (message.get("role") or "").upper()
        local = message.get("created_at_local") or ""
        stamp = (
            f"[{Formatting.format_date(local)} {Formatting.format_hms(local)}]"
            if local
            else "[????-??-?? ??:??:??]"
        )
        header = f"**`{stamp} {role}`**"
        body = message.get("content") or ""
        if not body:
            return f"{header}\n\n> _(empty)_\n"
        quoted = "\n".join(f"> {line}" if line else ">" for line in body.split("\n"))
        return f"{header}\n\n{quoted}\n"

    @classmethod
    def messages(cls, records):
        """Render the per-session chronological chat log."""
        if not records:
            return "_No chat log in this range._\n"

        parts = []
        for record in records:
            title = record.get("title") or ""
            sender = record.get("sender_id") or ""
            messages = record.get("messages", [])
            header = f"## `{record['id']}`"
            if title:
                header += f" \u2014 {Formatting.escape(title)}"
            parts.append(header)
            parts.append("")
            meta_bits = []
            if sender:
                meta_bits.append(f"Sender `{sender}`")
            meta_bits.append(f"{len(messages)} messages in range")
            if record.get("time_created") and record.get("time_updated"):
                meta_bits.append(
                    f"channel active {Formatting.format_date(record['start_local'])} "
                    f"{Formatting.format_hms(record['start_local'])}"
                    f" \u2192 {Formatting.format_date(record['end_local'])} "
                    f"{Formatting.format_hms(record['end_local'])}"
                )
            parts.append("_" + " \u00b7 ".join(meta_bits) + "_")
            parts.append("")
            if not messages:
                parts.append("_(no messages in this range)_")
                parts.append("")
                continue
            for message in messages:
                parts.append(cls.message_block(message))
                parts.append("")
        return "\n".join(parts).rstrip() + "\n"

    @classmethod
    def report(cls, *, sessions, from_ms, to_ms):
        """Render the complete Markdown report."""
        title = Formatting.format_range_title(from_ms=from_ms, to_ms=to_ms)
        parts = [
            f"# zeroclaw Memory \u2014 {title}",
            "",
            "## Sessions",
            "",
            cls.sessions(sessions),
            "",
            "## Chat Log",
            "",
            cls.messages(sessions),
        ]
        return "\n".join(parts)

#--------------------------------------------------
# SessionRepository: SQLite access
#--------------------------------------------------


class SessionRepository:
    """Read ZeroClaw sessions and messages from a SQLite connection."""

    DEFAULT_DB = "~/.zeroclaw/data/sessions/sessions.db"

    def __init__(self, *, connection):
        self._connection = connection

    @classmethod
    def default_path(cls):
        """Return the default ZeroClaw database path."""
        return os.path.expanduser(cls.DEFAULT_DB)

    def fetch_sessions(self, *, from_ms, to_ms):
        """Return sessions whose activity window overlaps the epoch range."""
        cursor = self._connection.cursor()
        cursor.execute(
            "SELECT session_key, name, created_at, last_activity, message_count, "
            "state, agent_alias, channel_id, room_id, sender_id "
            "FROM session_metadata "
            "ORDER BY created_at ASC"
        )
        records = []
        for row in cursor.fetchall():
            time_created = Dates.parse_iso(row[2])
            time_updated = Dates.parse_iso(row[3])
            if time_created >= to_ms or time_updated <= from_ms:
                continue
            records.append(
                {
                    "id": row[0],
                    "title": row[1],
                    "time_created": time_created,
                    "time_updated": time_updated,
                    "start_local": Formatting.to_local(time_created),
                    "end_local": Formatting.to_local(time_updated),
                    "duration_seconds": max(0.0, (time_updated - time_created) / 1000.0),
                    "agent": row[6],
                    "model": "",
                    "provider": "",
                    "cost": 0,
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "files": 0,
                    "additions": 0,
                    "deletions": 0,
                    "message_count": row[4],
                    "state": row[5],
                    "channel_id": row[7],
                    "room_id": row[8],
                    "sender_id": row[9],
                }
            )
        return records

    def fetch_messages(self, *, session_keys, from_ms, to_ms):
        """Return the chat messages for each session inside the epoch range."""
        result = {}
        cursor = self._connection.cursor()
        for session_key in session_keys:
            cursor.execute(
                "SELECT role, content, created_at FROM sessions "
                "WHERE session_key=? AND role IN ('user','assistant') "
                "ORDER BY id ASC",
                (session_key,),
            )
            messages = []
            for role, content, created_at in cursor.fetchall():
                timestamp = Dates.parse_iso(created_at)
                if timestamp < from_ms or timestamp >= to_ms:
                    continue
                text = (content or "").strip()
                if role == "user":
                    text = Formatting.strip_user_prefix(text)
                if not text:
                    continue
                messages.append(
                    {
                        "role": role,
                        "content": text,
                        "time_created": timestamp,
                        "created_at_local": Formatting.to_local(timestamp),
                    }
                )
            result[session_key] = messages
        return result

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
    """Command-line application for the ZeroClaw history report."""

    DESCRIPTION = "Combine zeroclaw session metadata with the full chat log in range."

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
            help=f"zeroclaw SQLite DB (default: {default_db})",
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
        self._emit(args=args, sessions=sessions, from_ms=from_ms, to_ms=to_ms)
        return 0

    def _load_sessions(self, *, db, from_ms, to_ms):
        """Return sessions with their chat messages attached."""
        connection = sqlite3.connect(db)
        repository = SessionRepository(connection=connection)
        try:
            sessions = repository.fetch_sessions(from_ms=from_ms, to_ms=to_ms)
            try:
                messages = repository.fetch_messages(
                    session_keys=[session["id"] for session in sessions],
                    from_ms=from_ms,
                    to_ms=to_ms,
                )
            except sqlite3.OperationalError:
                messages = {}
        finally:
            connection.close()

        for session in sessions:
            session["messages"] = messages.get(session["id"], [])
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
