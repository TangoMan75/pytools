#!/usr/bin/env python3
"""List Google Calendar events through the ``gws`` command."""

import argparse
import gzip
import json
import re
import shlex
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

#--------------------------------------------------
# Console: stream output and diagnostics
#--------------------------------------------------


class Console:
    """Write results to stdout and warnings or errors to stderr."""

    def __init__(self, *, stdout=None, stderr=None):
        self._stdout = stdout if stdout is not None else sys.stdout
        self._stderr = stderr if stderr is not None else sys.stderr

    def write(self, message):
        """Write a result payload verbatim to standard output."""
        self._stdout.write(message)

    def warning(self, message):
        """Write a non-fatal warning to standard error."""
        print(f"WARN: {message}", file=self._stderr)

    def error(self, message):
        """Write a fatal error to standard error."""
        print(f"ERROR: {message}", file=self._stderr)

#--------------------------------------------------
# Date range: local CLI values to ISO-8601 bounds
#--------------------------------------------------


class LocalDateRange:
    """Parse local-time CLI values into an inclusive ISO-8601 range."""

    DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d")

    @classmethod
    def parse_local(cls, value):
        """Parse 'YYYY-MM-DD HH:MM:SS' or 'YYYY-MM-DD' as a naive local datetime."""
        for date_format in cls.DATE_FORMATS:
            try:
                return datetime.strptime(value, date_format)
            except ValueError:
                continue
        raise ValueError(
            f"invalid date '{value}', expected 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS'"
        )

    @classmethod
    def resolve_iso_range(cls, *, start, end):
        """Return ``(tmin_iso, tmax_iso)`` for local ``start`` and ``end``.

        Date-only values default to 00:00:00 for the start and 23:59:59
        for the end.
        """
        start_dt = cls.parse_local(start)
        if ":" not in start:
            start_dt = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = cls.parse_local(end)
        if ":" not in end:
            end_dt = end_dt.replace(hour=23, minute=59, second=59, microsecond=0)
        if end_dt < start_dt:
            raise ValueError("end cannot be set before start")
        return start_dt.astimezone().isoformat(), end_dt.astimezone().isoformat()

#--------------------------------------------------
# GwsCommandRunner: invoke the gws CLI
#--------------------------------------------------


class GwsCommandRunner:
    """Run gws subcommands and translate their failures into runtime errors."""

    AUTH_HINT = "error: Please re-authenticate with `gws auth login` command"

    def run(self, *, args):
        """Run a gws subcommand, raise on failure, and return its stdout."""
        gws_bin = shutil.which("gws")
        if gws_bin is None:
            raise FileNotFoundError("`gws` is not on PATH")
        proc = subprocess.run(
            [gws_bin, *args, "--format", "json"],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            err = (proc.stderr or "").strip()
            raise RuntimeError(err or f"gws exited {proc.returncode}")
        return proc.stdout

    @classmethod
    def auth_hint(cls, *, exc):
        """Return the re-authentication hint when a token was rejected."""
        if "invalid_grant" in str(exc).lower():
            return f"\n{cls.AUTH_HINT}"
        return ""

#--------------------------------------------------
# CalendarCatalog: list calendars and resolve friendly names
#--------------------------------------------------


class CalendarCatalog:
    """Read the user's calendarList and resolve calendar names to IDs."""

    def __init__(self, *, runner):
        self._runner = runner

    def list_calendars(self):
        """Return calendarList entries that carry an ``id``."""
        raw = self._runner.run(args=["calendar", "calendarList", "list"])
        data = json.loads(raw)
        items = data.get("items", []) if isinstance(data, dict) else []
        return [calendar for calendar in items if calendar.get("id")]

    @classmethod
    def resolve_id(cls, *, query, calendars):
        """Resolve a calendar name to its ID, passing unknown values through.

        Matching is case-insensitive against ``summaryOverride`` or
        ``summary``. Multiple matches raise ``ValueError``; no match returns
        ``query`` unchanged so a raw calendar ID still works.
        """
        normalized = (query or "").strip().lower()
        if not normalized:
            return query

        matches = [
            calendar for calendar in calendars
            if cls._summary(calendar).lower() == normalized
        ]
        if len(matches) == 1:
            return matches[0]["id"]
        if len(matches) > 1:
            candidates = ", ".join(
                f'"{cls._summary(calendar) or calendar.get("id")}"'
                for calendar in matches
            )
            raise ValueError(f"ambiguous calendar name '{query}' — matches: {candidates}")
        return query

    @staticmethod
    def _summary(calendar):
        """Return the calendar's effective summary."""
        return (calendar.get("summaryOverride") or calendar.get("summary") or "").strip()

#--------------------------------------------------
# CalendarEventFetcher: query events through gws
#--------------------------------------------------


class CalendarEventFetcher:
    """Fetch events for one calendar or fan out across the whole calendar list."""

    def __init__(self, *, runner, catalog, console):
        self._runner = runner
        self._catalog = catalog
        self._console = console

    def raw_events(self, *, calendar_id, time_min, time_max, max_results):
        """Return the raw gws events.list response for one calendar."""
        params = {
            "calendarId": calendar_id,
            "timeMin": time_min,
            "timeMax": time_max,
            "orderBy": "startTime",
            "singleEvents": True,
            "maxResults": max_results,
        }
        return self._runner.run(
            args=["calendar", "events", "list", "--params", json.dumps(params)]
        )

    def events_for_calendar(self, *, calendar_id, time_min, time_max, max_results):
        """Return the ``items`` array for a single calendar events.list response."""
        raw = self.raw_events(
            calendar_id=calendar_id,
            time_min=time_min,
            time_max=time_max,
            max_results=max_results,
        )
        data = json.loads(raw)
        if not isinstance(data, dict):
            return []
        return data.get("items") or []

    def all_events(self, *, time_min, time_max, max_results):
        """Fan out to every calendar and merge the events into one document.

        Calendars that cannot list events are reported as warnings and
        skipped so the remaining calendars still produce a result.
        """
        calendars = self._catalog.list_calendars()

        all_items = []
        queried = []
        for calendar in calendars:
            calendar_id = calendar["id"]
            calendar_summary = calendar.get("summary", calendar_id)
            queried.append({"id": calendar_id, "summary": calendar_summary})
            try:
                events = self.events_for_calendar(
                    calendar_id=calendar_id,
                    time_min=time_min,
                    time_max=time_max,
                    max_results=max_results,
                )
            except Exception as exc:
                hint = GwsCommandRunner.auth_hint(exc=exc)
                self._console.warning(
                    f"skipping calendar {calendar_id} ({calendar_summary}): {exc}{hint}"
                )
                continue
            for event in events:
                event["calendarId"] = calendar_id
                event["calendarSummary"] = (
                    calendar.get("summaryOverride") or calendar.get("summary") or calendar_id
                )
            all_items.extend(events)

        all_items.sort(key=EventRow.start_key)
        return {
            "kind": "calendar#events",
            "items": all_items,
            "calendars_queried": queried,
        }

#--------------------------------------------------
# Event rendering: rows, CSV, markdown, JSON
#--------------------------------------------------


class EventRow:
    """Map a Google Calendar event to the shared nine-column table row."""

    COLUMNS = ["Calendar", "Subject", "Start Date", "Start Time",
               "End Date", "End Time", "Description", "Attendee", "Location"]

    @classmethod
    def md_escape(cls, value):
        """Escape one value for a markdown table cell."""
        if value is None:
            return ""
        return str(value).replace("|", "\\|").replace("\n", " ").strip()

    @classmethod
    def calendar_label(cls, event):
        """Return the best available source-calendar label for an event."""
        return (
            event.get("calendarSummary")
            or event.get("calendarId")
            or (event.get("organizer") or {}).get("email")
            or ""
        )

    @classmethod
    def cells(cls, event):
        """Return the nine cells matching ``COLUMNS`` for one event."""
        start = event.get("start") or {}
        end = event.get("end") or {}
        start_value = start.get("dateTime") or start.get("date") or ""
        end_value = end.get("dateTime") or end.get("date") or ""
        is_all_day = "T" not in start_value

        start_date = start_value[:10] if start_value else ""
        start_time = start_value[11:16] if start_value and not is_all_day else ""
        end_date = end_value[:10] if end_value else ""
        end_time = end_value[11:16] if end_value and not is_all_day else ""
        description = (event.get("description") or "").replace("\n", " ").strip()
        attendees = ", ".join(
            attendee.get("email", "")
            for attendee in (event.get("attendees") or [])
            if attendee.get("email")
        )
        location = event.get("location") or ""
        return [
            cls.calendar_label(event),
            event.get("summary") or "(no title)",
            start_date,
            start_time,
            end_date,
            end_time,
            description,
            attendees,
            location,
        ]

    @staticmethod
    def start_key(event):
        """Return the sortable start value for an event."""
        start = event.get("start") or {}
        return start.get("dateTime") or start.get("date") or ""


class CsvEventRenderer:
    """Render events as CSV with the shared table columns."""

    @classmethod
    def render(cls, events):
        """Return the CSV document for ``events``."""
        lines = [",".join(EventRow.COLUMNS)]
        for event in events:
            lines.append(",".join(cls._quote(cell) for cell in EventRow.cells(event)))
        return "\n".join(lines) + "\n"

    @staticmethod
    def _quote(value):
        """Quote a CSV cell when it contains a comma, quote, or newline."""
        if not value:
            return ""
        if "," in value or '"' in value or "\n" in value:
            value = value.replace('"', '""')
            return f'"{value}"'
        return value


class MarkdownEventRenderer:
    """Render events as a compact markdown table."""

    @classmethod
    def render(cls, *, events, tmin, tmax):
        """Return the markdown document for ``events`` within the range."""
        title = cls.format_range_title(tmin=tmin, tmax=tmax)
        if not events:
            return f"# Calendar events for {title}\n\n_No events in this range._\n"

        header = "| " + " | ".join(EventRow.COLUMNS) + " |"
        separator = "|" + "|".join("---" for _ in EventRow.COLUMNS) + "|"
        lines = [f"# Calendar events for {title}", "", header, separator]
        for event in events:
            cells = [EventRow.md_escape(cell) for cell in EventRow.cells(event)]
            lines.append("| " + " | ".join(cells) + " |")
        return "\n".join(lines) + "\n"

    @staticmethod
    def format_range_title(*, tmin, tmax):
        """Return the date span shown above the table."""
        start = tmin[:10]
        end = tmax[:10]
        return start if start == end else f"{start} → {end}"


class JsonEventRenderer:
    """Render gws-shaped documents as indented JSON."""

    @staticmethod
    def render(data):
        """Return the JSON document with a trailing newline."""
        return json.dumps(data, ensure_ascii=False, indent=2) + "\n"

#--------------------------------------------------
# IcsCodec: iCalendar value parsing
#--------------------------------------------------


class IcsCodec:
    """Parse and decode iCalendar property values."""

    @classmethod
    def parse_datetime(cls, *, raw, tzid=None):
        """Parse an ICS date or datetime value into ``(datetime, is_all_day)``."""
        raw = (raw or "").strip()
        if raw.endswith("Z"):
            parsed = datetime.strptime(raw, "%Y%m%dT%H%M%SZ")
            return parsed.replace(tzinfo=timezone.utc), False
        if "T" in raw:
            parsed = datetime.strptime(raw, "%Y%m%dT%H%M%S")
            if tzid:
                try:
                    parsed = parsed.replace(tzinfo=ZoneInfo(tzid))
                except Exception:
                    parsed = parsed.astimezone()
            else:
                parsed = parsed.astimezone()
            return parsed, False
        parsed = datetime.strptime(raw, "%Y%m%d").astimezone()
        return parsed, True

    @staticmethod
    def unescape(*, value):
        """Decode the escaped characters allowed in ICS text values."""
        return (
            value.replace("\\n", "\n").replace("\\N", "\n")
            .replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")
        )

    @staticmethod
    def split_property(*, line):
        """Split a single ICS property line into ``(NAME, params, value)``."""
        if ":" not in line:
            return line.upper(), {}, ""
        index = line.index(":")
        name_params = line[:index]
        value = line[index + 1:]
        if ";" in name_params:
            name, params_str = name_params.split(";", 1)
        else:
            name, params_str = name_params, ""
        params = {}
        for part in params_str.split(";"):
            if "=" in part:
                key, param_value = part.split("=", 1)
                params[key.upper()] = param_value
        return name.upper(), params, value

    @staticmethod
    def unfold(*, lines):
        """Join folded ICS continuation lines."""
        out = []
        for line in lines:
            if line[:1] in (" ", "\t"):
                if out:
                    out[-1] += line[1:]
                else:
                    out.append(line[1:])
            else:
                out.append(line)
        return out

    @staticmethod
    def to_aware(*, value):
        """Parse an ISO-8601 string, handling a trailing ``Z``, to an aware datetime."""
        normalized = value[:-1] + "+00:00" if value and value[-1] in ("Z", "z") else value
        return datetime.fromisoformat(normalized)

#--------------------------------------------------
# IcsParser: extract VEVENT blocks
#--------------------------------------------------


class IcsParser:
    """Parse iCalendar text into a calendar name and raw event dictionaries."""

    def __init__(self, *, codec):
        self._codec = codec

    def parse(self, *, text):
        """Return ``(calendar_name, [raw event dicts])`` for an ICS document."""
        calendar_name = None
        events = []
        current = {}
        in_event = False
        for line in self._codec.unfold(lines=text.splitlines()):
            name, params, value = self._codec.split_property(line=line)
            if name == "BEGIN" and value.upper() == "VEVENT":
                in_event = True
                current = {"attendees": []}
            elif name == "END" and value.upper() == "VEVENT":
                in_event = False
                events.append(current)
            elif name == "X-WR-CALNAME" and not in_event:
                calendar_name = self._codec.unescape(value=value)
            elif in_event:
                self._read_event_property(
                    current=current,
                    name=name,
                    params=params,
                    value=value,
                )
        return calendar_name, events

    def _read_event_property(self, *, current, name, params, value):
        """Store one VEVENT property on the event dictionary."""
        if name == "SUMMARY":
            current["summary"] = self._codec.unescape(value=value)
        elif name == "DESCRIPTION":
            current["description"] = self._codec.unescape(value=value)
        elif name == "LOCATION":
            current["location"] = self._codec.unescape(value=value)
        elif name == "UID":
            current["uid"] = value
        elif name == "DTSTART":
            current["start"], current["all_day"] = self._codec.parse_datetime(
                raw=value, tzid=params.get("TZID")
            )
        elif name == "DTEND":
            current["end"], _ = self._codec.parse_datetime(
                raw=value, tzid=params.get("TZID")
            )
        elif name == "RRULE":
            current["rrule"] = dict(
                part.split("=", 1) for part in value.split(";") if "=" in part
            )
        elif name == "ATTENDEE":
            email = value[len("mailto:"):] if value.lower().startswith("mailto:") else ""
            current["attendees"].append({"email": email})

#--------------------------------------------------
# RecurrenceExpander: expand RRULE occurrences
#--------------------------------------------------


class RecurrenceExpander:
    """Expand daily, weekly, monthly, and yearly RRULE occurrences."""

    MAX_OCCURRENCES = 5000
    WEEKDAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}

    def __init__(self, *, codec):
        self._codec = codec

    def expand(self, *, base_start, base_end, params, window_start, window_end):
        """Return ``[(start, end), ...]`` occurrences inside the window."""
        frequency = (params.get("FREQ") or "").upper()
        if frequency not in ("DAILY", "WEEKLY", "MONTHLY", "YEARLY"):
            return [(base_start, base_end)]
        interval = int(params.get("INTERVAL", 1) or 1)
        count = int(params["COUNT"]) if params.get("COUNT") else None
        until = None
        if params.get("UNTIL"):
            until, _ = self._codec.parse_datetime(raw=params["UNTIL"])
        byday = self._parse_byday(spec=params.get("BYDAY", ""))
        bymonthday = [
            int(value) for value in (params.get("BYMONTHDAY") or "").split(",") if value
        ]

        duration = base_end - base_start
        end_bound = window_end
        if until and until < end_bound:
            end_bound = until

        results = []
        day = base_start.date()
        last_day = end_bound.date()
        while day <= last_day and len(results) < RecurrenceExpander.MAX_OCCURRENCES:
            if self._matches(
                candidate=day,
                base_date=base_start.date(),
                frequency=frequency,
                interval=interval,
                byday=byday,
                bymonthday=bymonthday,
            ):
                occurrence = datetime.combine(
                    day, base_start.time(), tzinfo=base_start.tzinfo
                )
                results.append(occurrence)
                if count is not None and len(results) >= count:
                    break
            day += timedelta(days=1)

        occurrences = []
        for start in results:
            end = start + duration
            if end > window_start and start < window_end:
                occurrences.append((start, end))
        return occurrences

    def _parse_byday(self, *, spec):
        """Parse a BYDAY value into ``(ordinal, weekday)`` pairs."""
        parsed = []
        for token in (spec or "").split(","):
            token = token.strip()
            if not token:
                continue
            index = 0
            while index < len(token) and token[index] in "+-0123456789":
                index += 1
            ordinal = int(token[:index]) if index > 0 else None
            weekday = token[index:]
            if weekday in RecurrenceExpander.WEEKDAYS:
                parsed.append((ordinal, RecurrenceExpander.WEEKDAYS[weekday]))
        return parsed

    def _matches(self, *, candidate, base_date, frequency, interval, byday, bymonthday):
        """Return True when ``candidate`` matches the recurrence rule."""
        if candidate < base_date:
            return False
        if frequency == "DAILY":
            return (candidate - base_date).days % interval == 0
        if frequency == "WEEKLY":
            if (candidate - base_date).days // 7 % interval != 0:
                return False
            if byday:
                weekdays = [weekday for _, weekday in byday]
                return candidate.weekday() in weekdays
            return candidate.weekday() == base_date.weekday()
        if frequency == "MONTHLY":
            months = (candidate.year - base_date.year) * 12
            months += candidate.month - base_date.month
            if months % interval != 0:
                return False
            if bymonthday:
                return candidate.day in bymonthday
            if byday:
                return self._matches_byday_in_month(candidate=candidate, byday=byday)
            return candidate.day == base_date.day
        if frequency == "YEARLY":
            years = candidate.year - base_date.year
            if years % interval != 0:
                return False
            if bymonthday:
                return candidate.month == base_date.month and candidate.day in bymonthday
            if byday:
                return (
                    candidate.month == base_date.month
                    and self._matches_byday_in_month(candidate=candidate, byday=byday)
                )
            return (candidate.month, candidate.day) == (base_date.month, base_date.day)
        return False

    def _matches_byday_in_month(self, *, candidate, byday):
        """Return True when ``candidate`` matches one BYDAY entry in its month."""
        for ordinal, weekday in byday:
            if candidate.weekday() != weekday:
                continue
            if ordinal is None:
                return True
            matching_days = [
                day for day in range(1, candidate.day + 1)
                if datetime(candidate.year, candidate.month, day).weekday() == weekday
            ]
            if ordinal > 0:
                return matching_days and matching_days[ordinal - 1] == candidate.day
            return matching_days and matching_days[ordinal] == candidate.day
        return False

#--------------------------------------------------
# IcsFeedDownloader: fetch remote iCalendar feeds
#--------------------------------------------------


class IcsFeedDownloader:
    """Download and decode a remote iCalendar feed."""

    USER_AGENT = "gcal/1.0"
    TIMEOUT = 30

    def download(self, *, url):
        """Download ``url`` and return its decoded text."""
        request = urllib.request.Request(
            url, headers={"User-Agent": IcsFeedDownloader.USER_AGENT}
        )
        try:
            with urllib.request.urlopen(request, timeout=IcsFeedDownloader.TIMEOUT) as response:
                raw = response.read()
        except urllib.error.URLError as exc:
            raise RuntimeError(f"failed to fetch calendar URL: {exc}") from exc
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("utf-8", errors="replace")

#--------------------------------------------------
# IcsCalendarFetcher: parse feeds into event documents
#--------------------------------------------------


class IcsCalendarFetcher:
    """Download an iCalendar feed and return events inside a time window."""

    def __init__(self, *, downloader, parser, expander, codec):
        self._downloader = downloader
        self._parser = parser
        self._expander = expander
        self._codec = codec

    @staticmethod
    def is_calendar_url(value):
        """Return True when ``value`` looks like an http(s) iCal feed URL."""
        return bool(value) and value.lower().startswith(("http://", "https://"))

    def events(self, *, url, time_min, time_max):
        """Return events from ``url`` that overlap ``[time_min, time_max]``."""
        text = self._downloader.download(url=url)
        calendar_name, raw_events = self._parser.parse(text=text)
        calendar_label = calendar_name or url
        window_start = self._codec.to_aware(value=time_min)
        window_end = self._codec.to_aware(value=time_max)

        events = []
        for raw_event in raw_events:
            base_start = raw_event.get("start")
            if base_start is None:
                continue
            if raw_event.get("end") is not None:
                base_end = raw_event["end"]
            else:
                offset = timedelta(days=1) if raw_event.get("all_day") else timedelta(0)
                base_end = base_start + offset
            if raw_event.get("rrule"):
                occurrences = self._expander.expand(
                    base_start=base_start,
                    base_end=base_end,
                    params=raw_event["rrule"],
                    window_start=window_start,
                    window_end=window_end,
                )
            else:
                occurrences = [(base_start, base_end)]
            for start, end in occurrences:
                if end > window_start and start < window_end:
                    events.append(
                        self._build_event(
                            event=raw_event,
                            start=start,
                            end=end,
                            calendar_name=calendar_label,
                        )
                    )
        events.sort(key=EventRow.start_key)
        return events

    @classmethod
    def _build_event(cls, *, event, start, end, calendar_name):
        """Map one ICS occurrence to the gws event shape."""
        if event.get("all_day"):
            start_value = {"date": start.strftime("%Y-%m-%d")}
            end_value = {"date": end.strftime("%Y-%m-%d")}
        else:
            start_value = {"dateTime": start.isoformat()}
            end_value = {"dateTime": end.isoformat()}
        return {
            "summary": event.get("summary") or "(no title)",
            "start": start_value,
            "end": end_value,
            "description": event.get("description", ""),
            "location": event.get("location", ""),
            "attendees": event.get("attendees", []),
            "calendarId": event.get("uid") or calendar_name,
            "calendarSummary": calendar_name,
        }

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
        """Return a bash completion script for ``parser``."""
        all_opts, categories = cls._classify_parser_actions(parser)
        return cls._render_script(all_opts=all_opts, categories=categories, name=name)

#--------------------------------------------------
# CliParser: build the command-line interface
#--------------------------------------------------


class CliParser:
    """Build the gcal argument parser."""

    DESCRIPTION = "gws wrapper: list Google Calendar events in a [start, end] window."
    DEFAULT_MAX_RESULTS = 250
    LONG_DESCRIPTION = """gws wrapper: list Google Calendar events in a [start, end] window.

Drop-in replacement for the inline ``gws calendar events list ...`` call
in ``commands/daily.md`` §7. Resolves local-time ``--start``/``--end`` to
calendar ``events.list`` queries.

Calendar selection:
    * ``--calendar ID`` -> query that single calendar (response is the
      raw ``gws`` JSON).
    * ``--calendar URL`` -> if the value starts with http(s):// it is
      treated as an iCalendar (.ics) feed. The feed is downloaded and
      parsed directly (no ``gws`` call): events are expanded for RRULE
      recurrences, filtered to the ``--start``/``--end`` window, and
      rendered with the same ``--md``/``--csv``/JSON options.
    * omitted           -> fan out to every calendar in the user's
      ``calendarList``, merge the events, sort by start time, and tag
      each event with an extra ``calendarId`` field naming its source
      calendar. The merged response also includes a ``calendars_queried``
      array of ``{id, summary}`` for transparency.

Default output: JSON on stdout. With ``--md``, parse the response and
render a compact markdown table (adds a Calendar column when events
come from multiple calendars).

Args:
    --calendar            calendar ID, name, or an http(s) iCal (.ics) feed
                          URL (auto-detected). If omitted, query ALL calendars.
    --start, --end        "YYYY-MM-DD" or "YYYY-MM-DD HH:MM:SS" (local).
                          Date-only --start -> 00:00:00, date-only --end
                          -> 23:59:59. Defaults: --start today 00:00:00,
                          --end start date 23:59:59.
    --max-results         max events per page, per calendar (default: 250)
    --md                  render a markdown table instead of JSON
    --quiet               suppress non-error output; runtime errors are still
                          reported and exit 1

Exit codes:
    0  events fetched (possibly empty list)
    1  gws invocation failed
    2  bad CLI args
"""

    def build(self):
        """Build and return the argument parser."""
        today = datetime.now().date().isoformat()
        parser = argparse.ArgumentParser(description=CliParser.DESCRIPTION)
        parser.add_argument(
            "--calendar", default=None,
            help="calendar ID, name, or an http(s) iCal (.ics) feed URL. If omitted, "
                 "query ALL calendars in the user's list. A URL is auto-detected.",
        )
        parser.add_argument(
            "--start", default=today,
            help=f"inclusive start YYYY-MM-DD or YYYY-MM-DD HH:MM:SS "
                 f"(local; default: {today} 00:00:00)",
        )
        parser.add_argument(
            "--end", default=None,
            help="inclusive end YYYY-MM-DD or YYYY-MM-DD HH:MM:SS "
                 "(local; default: start date 23:59:59)",
        )
        parser.add_argument(
            "--max-results", type=int, default=CliParser.DEFAULT_MAX_RESULTS,
            help="max events per page, per calendar (default: 250)",
        )
        parser.add_argument(
            "--md", action="store_true",
            help="render a markdown table instead of JSON",
        )
        parser.add_argument(
            "--csv", action="store_true",
            help="render CSV instead of JSON",
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

#--------------------------------------------------
# Application: orchestrate the CLI
#--------------------------------------------------


class Application:
    """Run the gcal command and translate failures into exit codes."""

    EXIT_SUCCESS = 0
    EXIT_ERROR = 1
    EXIT_USAGE = 2

    def __init__(self, *, argv=None, runner=None, console=None):
        self._argv = list(sys.argv[1:] if argv is None else argv)
        self._console = console if console is not None else Console()
        self._runner = runner if runner is not None else GwsCommandRunner()
        self._catalog = CalendarCatalog(runner=self._runner)
        self._fetcher = CalendarEventFetcher(
            runner=self._runner,
            catalog=self._catalog,
            console=self._console,
        )
        codec = IcsCodec()
        self._ics = IcsCalendarFetcher(
            downloader=IcsFeedDownloader(),
            parser=IcsParser(codec=codec),
            expander=RecurrenceExpander(codec=codec),
            codec=codec,
        )

    def run(self):
        """Parse the command line, fetch events, and return an exit code."""
        parser = CliParser().build()
        if "--completion" in self._argv:
            self._console.write(
                Completion.generate(parser=parser, name=self._command_name()) + "\n"
            )
            return Application.EXIT_SUCCESS

        options = parser.parse_args(self._argv)
        end_arg = (
            options.end if options.end is not None
            else f"{options.start[:10]} 23:59:59"
        )
        try:
            time_min, time_max = LocalDateRange.resolve_iso_range(
                start=options.start, end=end_arg
            )
        except ValueError as exc:
            self._console.error(str(exc))
            return Application.EXIT_USAGE

        if options.calendar is not None:
            if IcsCalendarFetcher.is_calendar_url(options.calendar):
                return self._run_ics(
                    options=options, time_min=time_min, time_max=time_max
                )
            return self._run_single_calendar(
                options=options, time_min=time_min, time_max=time_max
            )
        return self._run_all_calendars(
            options=options, time_min=time_min, time_max=time_max
        )

    @staticmethod
    def _command_name():
        """Return the installed command name derived from argv[0]."""
        return Path(sys.argv[0]).resolve().stem

    def _run_ics(self, *, options, time_min, time_max):
        """Fetch an iCal feed URL and render its events."""
        try:
            events = self._ics.events(
                url=options.calendar, time_min=time_min, time_max=time_max
            )
        except Exception as exc:
            self._console.error(f"failed to fetch calendar URL: {exc}")
            return Application.EXIT_ERROR

        if not self._write_table(
            options=options, events=events, time_min=time_min, time_max=time_max
        ):
            merged = {"kind": "calendar#events", "items": events}
            self._console.write(JsonEventRenderer.render(merged))
        return Application.EXIT_SUCCESS

    def _run_single_calendar(self, *, options, time_min, time_max):
        """Query one calendar, resolving its name, and render the response."""
        try:
            calendars = self._catalog.list_calendars()
            calendar_id = self._catalog.resolve_id(
                query=options.calendar, calendars=calendars
            )
        except Exception as exc:
            hint = GwsCommandRunner.auth_hint(exc=exc)
            self._console.error(f"gws calendarList list failed: {exc}{hint}")
            return Application.EXIT_ERROR

        try:
            raw = self._fetcher.raw_events(
                calendar_id=calendar_id,
                time_min=time_min,
                time_max=time_max,
                max_results=options.max_results,
            )
        except Exception as exc:
            hint = GwsCommandRunner.auth_hint(exc=exc)
            self._console.error(f"gws calendar events list failed: {exc}{hint}")
            return Application.EXIT_ERROR

        if not (options.md or options.csv):
            self._console.write(raw)
            return Application.EXIT_SUCCESS

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            self._console.write(raw)
            return Application.EXIT_SUCCESS
        events = data.get("items", []) if isinstance(data, dict) else data
        if not isinstance(events, list):
            events = []
        calendar_summary = next(
            (
                calendar.get("summaryOverride")
                or calendar.get("summary")
                or calendar_id
                for calendar in calendars
                if calendar.get("id") == calendar_id
            ),
            calendar_id,
        )
        for event in events:
            event.setdefault("calendarId", calendar_id)
            event.setdefault("calendarSummary", calendar_summary)
        self._write_table(
            options=options, events=events, time_min=time_min, time_max=time_max
        )
        return Application.EXIT_SUCCESS

    def _run_all_calendars(self, *, options, time_min, time_max):
        """Fan out to every calendar, merge the events, and render them."""
        try:
            merged = self._fetcher.all_events(
                time_min=time_min,
                time_max=time_max,
                max_results=options.max_results,
            )
        except Exception as exc:
            hint = GwsCommandRunner.auth_hint(exc=exc)
            self._console.error(f"gws calendar fetch failed: {exc}{hint}")
            return Application.EXIT_ERROR

        if not self._write_table(
            options=options, events=merged["items"],
            time_min=time_min, time_max=time_max,
        ):
            self._console.write(JsonEventRenderer.render(merged))
        return Application.EXIT_SUCCESS

    def _write_table(self, *, options, events, time_min, time_max):
        """Write a markdown or CSV table and return True when one was requested."""
        if options.md:
            self._console.write(
                MarkdownEventRenderer.render(
                    events=events, tmin=time_min, tmax=time_max
                )
            )
            return True
        if options.csv:
            self._console.write(CsvEventRenderer.render(events))
            return True
        return False


if __name__ == "__main__":
    sys.exit(Application().run())
