#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
iCalendar (.ics) parser and builder.

Converts iCalendar files to and from CSV/TSV files. The direction (forward or
reverse) is auto-detected from the input file extension: ``.ics`` is parsed as
iCalendar, while ``.csv`` and ``.tsv`` are converted to iCalendar.

The default tabular format is CSV (comma-separated); pass ``--delimiter`` to
override the field delimiter (e.g. ``--delimiter $'\\t'`` for TAB).

Usage:
    python3 conv-ics.py <input> [--columns columns] [--delimiter delimiter]
        [--full] [--output output]
"""


import argparse
import re
import shlex
import ssl
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen


#--------------------------------------------------
# Console and logging
#--------------------------------------------------


class Console:
    """Minimal console output helper."""

    quiet = False

    @staticmethod
    def error(message):
        print(message, file=sys.stderr)


class NullLogger:
    """No-op logger fallback."""

    def info(self, message):
        return None

    success = info
    warning = info
    danger = info


class Logger:
    """Lightweight verbose-aware logger."""

    def __init__(self, *, verbose=0, quiet=False):
        self.verbose = verbose
        self.quiet = quiet

    def print(self):
        return None

    def info(self, message):
        if self.verbose and not self.quiet:
            print(message)

    def success(self, message):
        if not self.quiet:
            print(message)

    warning = success

    def danger(self, message):
        print(message, file=sys.stderr)


#--------------------------------------------------
# FileHandler: base class for business logic
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
        iterator = [path] if path.is_file() else (path.rglob("*") if recursive else path.glob("*"))
        for item in sorted(iterator):
            matches_include = not include or item.match(include)
            excluded = exclude and item.match(exclude)
            if item.is_file() and matches_include and not excluded:
                yield item


#--------------------------------------------------
# Kernel: minimal standalone CLI base
#--------------------------------------------------


class Kernel:
    """Minimal standalone CLI base."""

    def __init__(self, *, author, title, description):
        self.author = author
        self.title = title
        self.description = description

    def _build_early_parser(self):
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--log", action="store_true")
        parser.add_argument("--verbose", "-v", action="count", default=0)
        parser.add_argument("--quiet", action="store_true",
                            help="suppress non-error output; runtime errors are still reported")
        parser.add_argument("--completion", action="store_true",
                            help="Print bash completion script to stdout and exit")
        return parser

    def _build_parser(self):
        parser = argparse.ArgumentParser(description=self.description)
        parser.add_argument("input")
        parser.add_argument("--output")
        parser.add_argument("--recursive", action="store_true")
        parser.add_argument("--include")
        parser.add_argument("--exclude")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--log", action="store_true", help="Print the current log and stop")
        parser.add_argument("--verbose", "-v", action="count", default=0)
        parser.add_argument("--quiet", action="store_true",
                            help="suppress non-error output; runtime errors are still reported")
        parser.add_argument("--completion", action="store_true",
                            help="Print bash completion script to stdout and exit")
        return parser

    def hero(self):
        return None


#--------------------------------------------------
# IcsDownloader: fetch a remote .ics file
#--------------------------------------------------


class IcsDownloader:
    """Download an iCalendar file from an HTTP(S) URL into a local directory."""

    DEFAULT_FILENAME = "calendar.ics"
    DEFAULT_TIMEOUT = 30
    DEFAULT_USER_AGENT = "conv-ics/1.0"
    URL_SCHEMES = ("http://", "https://")

    def __init__(self, *, logger=None):
        self.logger = logger if logger is not None else NullLogger()

    @classmethod
    def is_url(cls, value):
        """Return True if ``value`` is a recognized HTTP(S) URL."""
        if not value:
            return False
        return value.startswith(cls.URL_SCHEMES)

    def download(self, *, url, dest_dir):
        """Fetch ``url`` and write the response body to ``dest_dir``.

        SSL certificate verification is always skipped. Returns the path of
        the saved file. Exits the process on network or HTTP errors (the
        caller is expected to let the script terminate after a failed
        download).
        """
        filename = self._derive_filename(url)
        target = self._unique_path(dest_dir=dest_dir, filename=filename)
        request = Request(url, headers={"User-Agent": self.DEFAULT_USER_AGENT})
        context = self._build_ssl_context()
        self.logger.info(f"Downloading {url}")
        try:
            with urlopen(
                request, timeout=self.DEFAULT_TIMEOUT, context=context,
            ) as response:
                content = response.read()
        except (HTTPError, URLError) as err:
            self.logger.danger(f"Download failed: {err}")
            sys.exit(1)
        target.write_bytes(content)
        return target

    @staticmethod
    def _build_ssl_context():
        """Return a permissive SSL context that skips certificate verification."""
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    @classmethod
    def _derive_filename(cls, url):
        """Return a sensible ``.ics`` filename derived from the URL."""
        path = urlparse(url).path
        name = unquote(path.rsplit("/", 1)[-1]) if path else ""
        if name and name.lower().endswith(".ics"):
            return name
        if name:
            return f"{name}.ics"
        return cls.DEFAULT_FILENAME

    @staticmethod
    def _unique_path(*, dest_dir, filename):
        """Return a path in ``dest_dir`` that does not yet exist.

        On collision, suffix the stem with ``_1``, ``_2``, ... (preserving
        the original extension when present, defaulting to ``.ics``).
        """
        if "." in filename:
            stem, suffix = filename.rsplit(".", 1)
        else:
            stem, suffix = filename, "ics"
        target = dest_dir / filename
        if not target.exists():
            return target
        counter = 1
        while True:
            target = dest_dir / f"{stem}_{counter}.{suffix}"
            if not target.exists():
                return target
            counter += 1


#--------------------------------------------------
# DateUtils: pure parsing and formatting helpers
#--------------------------------------------------


class DateUtils:
    """Utility class for parsing and formatting iCalendar dates."""

    DATE_PATTERN = re.compile(r"^\d{8}$")
    DATETIME_PATTERN = re.compile(r"^\d{8}T\d{6}$")
    UTC_DATETIME_PATTERN = re.compile(r"^\d{8}T\d{6}Z$")
    DATE_HEADERS = ("DTSTART", "DTEND", "DTSTAMP", "CREATED", "LAST-MOD")

    @classmethod
    def detect(cls, value):
        """Return the iCalendar date type for a value, or '' if unrecognized."""
        if not value:
            return ""
        if cls.UTC_DATETIME_PATTERN.match(value):
            return "utc datetime"
        if cls.DATETIME_PATTERN.match(value):
            return "datetime"
        if cls.DATE_PATTERN.match(value):
            return "date"
        return ""

    @classmethod
    def to_iso(cls, value):
        """Convert an iCalendar date value to ISO 8601 format."""
        dt_type = cls.detect(value)
        if dt_type == "date":
            return f"{value[0:4]}-{value[4:6]}-{value[6:8]}"
        if dt_type in ("datetime", "utc datetime"):
            date_part = f"{value[0:4]}-{value[4:6]}-{value[6:8]}"
            time_part = f"{value[9:11]}:{value[11:13]}:{value[13:15]}"
            iso = f"{date_part} {time_part}"
            if dt_type == "utc datetime":
                iso += "Z"
            return iso
        return value

    @classmethod
    def to_local(cls, value):
        """Convert a UTC datetime iCalendar value to local time ISO format."""
        if cls.detect(value) != "utc datetime":
            return cls.to_iso(value)
        dt = datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")

    @classmethod
    def to_ics(cls, iso_value):
        """Convert an ISO date/time string back to iCalendar form."""
        if not iso_value or "-" not in iso_value:
            return iso_value
        try:
            if len(iso_value) == 10:
                return datetime.strptime(iso_value, "%Y-%m-%d").strftime("%Y%m%d")
            if len(iso_value) == 19:
                return datetime.strptime(iso_value, "%Y-%m-%d %H:%M:%S").strftime("%Y%m%dT%H%M%S")
            if len(iso_value) == 20 and iso_value.endswith("Z"):
                return datetime.strptime(iso_value, "%Y-%m-%d %H:%M:%SZ").strftime("%Y%m%dT%H%M%SZ")
        except ValueError:
            return iso_value
        return iso_value

    @classmethod
    def get_duration(cls, *, start_value, end_value):
        """Return a human-readable duration between two iCalendar date values."""
        start_dt = cls._parse(start_value)
        end_dt = cls._parse(end_value)
        if start_dt is None or end_dt is None:
            return ""
        delta = end_dt - start_dt
        total_seconds = int(delta.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        if minutes == 0:
            return f"{hours}h"
        if hours == 0:
            return f"{minutes}m"
        return f"{hours}h{minutes}m"

    @classmethod
    def _parse(cls, value):
        """Parse an iCalendar date/datetime into a datetime (tz-aware for UTC)."""
        dt_type = cls.detect(value)
        if dt_type == "date":
            return datetime.strptime(value, "%Y%m%d")
        if dt_type == "datetime":
            return datetime.strptime(value, "%Y%m%dT%H%M%S")
        if dt_type == "utc datetime":
            return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return None


#--------------------------------------------------
# IcsPreprocessor: reproduces the original sed/awk/tr pipeline
#--------------------------------------------------


class IcsPreprocessor:
    """Replicates the original conv-ics shell pipeline on a raw iCalendar string.

    Steps mirror the bash + awk + sed + tr chain:
      1. Join RFC 5545 continuation lines.
      2. Replace the first ':' with the delimiter (creates key<tab>value).
      3. Strip iCalendar parameters from the key portion (e.g. ``;TZID=...``).
      4. Unescape backslash sequences before non-alpha characters.
      5. Remove DOS carriage returns.
    """

    CONTINUATION_RE = re.compile(r"\r?\n[ \t]")
    ESCAPE_RE = re.compile(r"\\([^a-zA-Z])")
    CR_RE = re.compile(r"\r")

    def __init__(self, *, delimiter):
        self.delimiter = delimiter
        self._param_re = re.compile(r";.*" + re.escape(delimiter))

    def process(self, text):
        """Run the full preprocessing pipeline and return the normalized text."""
        text = self.CONTINUATION_RE.sub("", text)
        text = self.CR_RE.sub("", text)
        lines = []
        for line in text.split("\n"):
            colon_index = line.find(":")
            if colon_index == -1:
                lines.append(line)
                continue
            line = f"{line[:colon_index]}{self.delimiter}{line[colon_index + 1:]}"
            line = self._param_re.sub(self.delimiter, line)
            line = self.ESCAPE_RE.sub(r"\1", line)
            lines.append(line)
        return "\n".join(lines)


#--------------------------------------------------
# IcsParser: ICS -> TSV
#--------------------------------------------------


class IcsParser:
    """Parse an iCalendar stream into headers and rows."""

    DEFAULT_COMPONENT = "VEVENT"
    DEFAULT_DELIMITER = ","
    TAB_DELIMITER = "\t"

    def __init__(self, *, delimiter=DEFAULT_DELIMITER, columns=""):
        self.delimiter = delimiter
        self.columns = columns.upper() if columns else ""
        self._preprocessor = IcsPreprocessor(delimiter=delimiter)

    def parse(self, text):
        """Parse ICS text and return (headers, rows)."""
        preprocessed = self._preprocessor.process(text)
        records = self._collect_records(preprocessed)
        headers = self._resolve_columns(records)
        rows = self._build_rows(records=records, headers=headers)
        return headers, rows

    def collect_records(self, text):
        """Preprocess and collect raw iCalendar records from the given text."""
        preprocessed = self._preprocessor.process(text)
        return self._collect_records(preprocessed)

    def format_output(self, *, headers, rows):
        """Format headers and rows as a delimited string."""
        lines = [self.delimiter.join(headers)]
        for row in rows:
            cells = [self._escape_cell(value) for value in row]
            lines.append(self.delimiter.join(cells))
        return "\n".join(lines)

    def _collect_records(self, text):
        """Collect key/value pairs for each occurrence of the target component."""
        records = []
        current = None
        in_component = False
        for line in text.split("\n"):
            parts = line.split(self.delimiter, 1)
            if len(parts) != 2:
                continue
            key, value = parts
            if key == "BEGIN":
                in_component = value == self.DEFAULT_COMPONENT
                if in_component:
                    current = {}
                continue
            if key == "END":
                if value == self.DEFAULT_COMPONENT and current is not None:
                    records.append(current)
                    current = None
                elif value != self.DEFAULT_COMPONENT:
                    in_component = True
                continue
            if in_component and current is not None and key and value:
                current[key] = value
        return records

    def _resolve_columns(self, records):
        """Return the column list: explicit (uppercased) or auto-sorted by frequency."""
        if self.columns:
            return [c.strip() for c in self.columns.split(",") if c.strip()]
        counts = {}
        for record in records:
            for key in record:
                counts[key] = counts.get(key, 0) + 1
        return sorted(counts, key=lambda k: (-counts[k], k))

    def _build_rows(self, *, records, headers):
        """Build rows aligned to headers, applying date conversion and DURATION."""
        rows = []
        for record in records:
            duration = record.get("DURATION", "")
            if "DURATION" in headers and not duration:
                if record.get("DTSTART") and record.get("DTEND"):
                    duration = DateUtils.get_duration(
                        start_value=record["DTSTART"],
                        end_value=record["DTEND"],
                    )
            row = []
            for header in headers:
                if header == "DURATION":
                    value = duration
                else:
                    value = record.get(header, "")
                if header in DateUtils.DATE_HEADERS:
                    if DateUtils.detect(value) == "utc datetime":
                        value = DateUtils.to_local(value)
                    elif DateUtils.detect(value):
                        value = DateUtils.to_iso(value)
                row.append(value)
            rows.append(row)
        return rows

    def _escape_cell(self, value):
        """Quote a value that contains the delimiter."""
        if self.delimiter in value:
            escaped = value.replace('"', '""')
            return f'"{escaped}"'
        return value


#--------------------------------------------------
# IcsBuilder: TSV -> ICS
#--------------------------------------------------


class IcsBuilder:
    """Build an iCalendar document from a delimited tabular stream."""

    DEFAULT_DELIMITER = IcsParser.DEFAULT_DELIMITER

    def __init__(self, *, delimiter=DEFAULT_DELIMITER):
        self.delimiter = delimiter

    def build(self, text):
        """Parse delimited text and return an iCalendar document string."""
        lines = text.splitlines()
        if not lines:
            return "BEGIN:VCALENDAR\nEND:VCALENDAR\n"
        headers = self._split_line(lines[0])
        events = []
        for raw_line in lines[1:]:
            if not raw_line.strip():
                continue
            cells = self._split_line(raw_line)
            event = {}
            for header, cell in zip(headers, cells):
                if cell:
                    event[header.upper()] = cell
            events.append(event)
        return self._format_calendar(events)

    def _split_line(self, line):
        """Split a delimited line honoring double-quoted values."""
        cells = []
        current = []
        in_quotes = False
        i = 0
        length = len(line)
        while i < length:
            char = line[i]
            if char == '"':
                in_quotes = not in_quotes
            elif char == self.delimiter and not in_quotes:
                cells.append("".join(current).strip('"'))
                current = []
                i += 1
                continue
            else:
                current.append(char)
            i += 1
        cells.append("".join(current).strip('"'))
        return cells

    def _format_calendar(self, events):
        """Render events as an iCalendar document."""
        output = ["BEGIN:VCALENDAR"]
        for event in events:
            output.append("BEGIN:VEVENT")
            for header, value in event.items():
                if header == "DURATION":
                    continue
                if header in DateUtils.DATE_HEADERS and "-" in value:
                    value = DateUtils.to_ics(value)
                output.append(f"{header}:{value}")
            output.append("END:VEVENT")
        output.append("END:VCALENDAR")
        return "\n".join(output) + "\n"


#--------------------------------------------------
# GoogleCalendarFormatter: ICS -> Google Calendar CSV
#--------------------------------------------------


class GoogleCalendarFormatter:
    """Render iCalendar records as a Google Calendar-compatible CSV.

    The output follows the column layout expected by Google Calendar's CSV
    importer. Fields that are not relevant for re-import (UID, STATUS, ...) are
    dropped, ``DTSTART`` / ``DTEND`` are split into a date and a time column,
    and a ``Calendar`` column carries the source file's basename. ``ATTENDEE``
    is included in the default output.
    """

    DROP_COLUMNS = (
        "CREATED", "DTSTAMP", "LAST-MODIFIED", "SEQUENCE", "STATUS",
        "TRANSP", "UID", "ORGANIZER", "X-GOOGLE-CONFERENCE",
        "RECURRENCE-ID", "ATTACH", "RRULE", "EXDATE",
    )
    BASE_HEADERS = (
        "Calendar", "Subject", "Start Date", "Start Time",
        "End Date", "End Time", "Description", "Attendee", "Location",
    )
    DEFAULT_DELIMITER = IcsParser.DEFAULT_DELIMITER

    def __init__(self, *, delimiter=DEFAULT_DELIMITER):
        self.delimiter = delimiter
        self.headers = self.BASE_HEADERS

    def format_records(self, *, records, calendar):
        """Format the given records as a Google Calendar CSV string."""
        lines = [self.delimiter.join(self.headers)]
        for record in records:
            row = self._build_row(record=record, calendar=calendar)
            cells = [self._escape_cell(value) for value in row]
            lines.append(self.delimiter.join(cells))
        return "\n".join(lines)

    def _build_row(self, *, record, calendar):
        start_date, start_time = self._split_datetime(record.get("DTSTART", ""))
        end_date, end_time = self._split_datetime(record.get("DTEND", ""))
        return [
            calendar,
            record.get("SUMMARY", ""),
            start_date,
            start_time,
            end_date,
            end_time,
            record.get("DESCRIPTION", ""),
            record.get("ATTENDEE", ""),
            record.get("LOCATION", ""),
        ]

    def _split_datetime(self, value):
        """Return ``(date, time)`` in Google Calendar CSV format."""
        if not value:
            return "", ""
        dt_type = DateUtils.detect(value)
        if dt_type == "date":
            return DateUtils.to_iso(value), ""
        if dt_type == "datetime":
            iso = DateUtils.to_iso(value)
            return iso[:10], self._format_time(iso[11:19])
        if dt_type == "utc datetime":
            iso = DateUtils.to_local(value)
            return iso[:10], self._format_time(iso[11:19])
        return value, ""

    @staticmethod
    def _format_time(iso_time):
        """Convert ``HH:MM:SS`` to ``HH:MM`` 24-hour form."""
        hour, minute, _ = iso_time.split(":")
        return f"{hour}:{minute}"

    def _escape_cell(self, value):
        """Quote a value that contains the delimiter, quotes, or newlines."""
        if self.delimiter in value or '"' in value or "\n" in value:
            escaped = value.replace('"', '""')
            return f'"{escaped}"'
        return value


#--------------------------------------------------
# IcsHandler: FileHandler implementation
#--------------------------------------------------


class IcsHandler(FileHandler):
    """Convert ICS files to/from tabular form on disk."""

    REVERSE_EXTENSIONS = (".csv", ".tsv")
    DEFAULT_DELIMITER = IcsParser.DEFAULT_DELIMITER
    TAB_DELIMITER = IcsParser.TAB_DELIMITER

    def __init__(
        self,
        *,
        logger=None,
        columns="",
        delimiter=DEFAULT_DELIMITER,
        input_delimiter=None,
        recursive=False,
        input_root=None,
        full=False,
    ):
        super().__init__(logger=logger)
        self.columns = columns
        self.delimiter = delimiter
        self.input_delimiter = input_delimiter
        self.recursive = recursive
        self.input_root = input_root
        self.full = full

    @staticmethod
    def detect_format(path):
        """Return the inferred format token for an input path.

        ``"ics"`` for ``.ics`` files, ``"csv"`` for ``.csv`` files, ``"tsv"``
        for ``.tsv`` files. Unknown extensions fall back to ``"ics"`` (forward
        direction is treated as the default).
        """
        suffix = path.suffix.lower()
        if suffix == ".csv":
            return "csv"
        if suffix == ".tsv":
            return "tsv"
        return "ics"

    def is_reverse(self, path):
        """Return True if the given file should be processed in reverse direction."""
        return path.suffix.lower() in self.REVERSE_EXTENSIONS

    @staticmethod
    def delimiter_for(path):
        """Return the field delimiter that matches the given input file's extension."""
        suffix = path.suffix.lower()
        if suffix == ".tsv":
            return IcsHandler.TAB_DELIMITER
        return IcsHandler.DEFAULT_DELIMITER

    def _resolve_input_delimiter(self, path):
        """Return the delimiter to use for parsing this input file.

        Prefers an explicit ``input_delimiter`` override (set via ``-d``) and
        falls back to the extension-based default.
        """
        if self.input_delimiter is not None:
            return self.input_delimiter
        return self.delimiter_for(path)

    def process_file(self, path, *, output=None, dry_run=False):
        """Convert a single file. Direction is auto-detected from the extension."""
        if not path.is_file():
            self.files_skipped += 1
            return

        try:
            text = path.read_text(encoding="utf-8")
        except OSError as err:
            self.logger.warning(f"Skipping {path}: {err}")
            self.files_skipped += 1
            return

        reverse = self.is_reverse(path)

        if reverse:
            builder = IcsBuilder(delimiter=self._resolve_input_delimiter(path))
            result = builder.build(text)
        elif self.full:
            parser = IcsParser(
                delimiter=self.delimiter,
                columns=self.columns,
            )
            headers, rows = parser.parse(text)
            result = parser.format_output(headers=headers, rows=rows)
        else:
            parser = IcsParser(delimiter=self.delimiter)
            records = parser.collect_records(text)
            formatter = GoogleCalendarFormatter(delimiter=self.delimiter)
            result = formatter.format_records(records=records, calendar=path.stem)

        self._write_result(result, path, output=output, dry_run=dry_run)
        self.files_processed += 1

    def _write_result(self, result, path, *, output, dry_run):
        """Route the conversion result to stdout, a file, or a directory.

        Routing rules:
        - ``output is None`` and not recursive: write to ``<basename>.<new_ext>``
          in the current working directory.
        - ``output is None`` and recursive: raise ``ValueError`` (the CLI
          validates this up front).
        - ``output == "-"``: write to stdout.
        - Otherwise: treat ``output`` as a file or directory path.
        """
        if output is None:
            if self.recursive:
                raise ValueError(
                    "--output is required when --recursive is enabled"
                )
            target = path.parent / self._relative_output_name(path)
        elif output == "-":
            sys.stdout.write(result)
            if not result.endswith("\n"):
                sys.stdout.write("\n")
            return
        else:
            output_path = Path(output)
            target_dir = self._resolve_output_dir(output_path)
            if target_dir is not None:
                target = target_dir / self._relative_output_name(path)
            else:
                target = output_path

        target.parent.mkdir(parents=True, exist_ok=True)

        if dry_run:
            self.logger.info(f"[DRY RUN] Would write: {target}")
            return

        target.write_text(result, encoding="utf-8")
        self.logger.success(f"Wrote: {target}")

    def _resolve_output_dir(self, output_path):
        """Return the target directory if output should be a directory, else None."""
        if output_path.is_dir():
            return output_path
        if str(output_path).endswith(("/", "\\")):
            return output_path
        if self.input_root is not None and self.input_root.is_dir():
            return output_path
        # Heuristic: a non-existent path with no recognized tabular extension
        # is treated as a directory so single-file inputs land in a folder.
        if not output_path.exists() and output_path.suffix.lower() not in (
            ".ics", ".csv", ".tsv", ".txt",
        ):
            return output_path
        return None

    def _relative_output_name(self, path):
        """Compute the output path for a given input, preserving structure when recursive."""
        suffix = ".ics" if self.is_reverse(path) else self._tabular_suffix()
        if self.recursive and self.input_root is not None:
            try:
                relative = path.relative_to(self.input_root)
                return str(relative.with_suffix(suffix))
            except ValueError:
                pass
        return f"{path.stem}{suffix}"

    def _tabular_suffix(self):
        """Return the file suffix that matches the current delimiter."""
        if self.delimiter == self.TAB_DELIMITER:
            return ".tsv"
        if self.delimiter == self.DEFAULT_DELIMITER:
            return ".csv"
        return ".txt"


#--------------------------------------------------
# Completion: bash completion script generator
#--------------------------------------------------


class Completion:
    """Generate the bash completion script for an argparse parser."""

    @staticmethod
    def classify_parser_actions(*, parser):
        """Walk the parser actions and return ``(all_opts, categories)``."""
        all_opts = set()
        categories = {"boolean": [], "verbose": [], "file": [], "glob": []}
        file_keys = ("output", "file", "path", "dest")
        glob_keys = ("include", "exclude", "glob", "pattern")
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
                blocks.append(Completion.render_completion_case(opt=opt, kind=kind))
        option_case = "".join(blocks)
        completion_name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
        sorted_opts = sorted(all_opts, key=lambda o: (not o.startswith("--"), o.lower()))
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
        """Return a bash completion script string for the given argparse parser."""
        all_opts, categories = Completion.classify_parser_actions(parser=parser)
        return Completion.render_completion_script(
            all_opts=all_opts,
            categories=categories,
            name=name,
        )


#--------------------------------------------------
# IcsConverterApp
#--------------------------------------------------


class IcsConverterApp(Kernel):
    """CLI application wiring IcsHandler to argparse."""

    def build_parser(self):
        """Build and return the argument parser (public, for autocomplete generation)."""
        return self._build_parser()

    def generate_completion(self):
        """Return the bash completion script for this script."""
        name = Path(sys.argv[0]).resolve().stem
        return Completion.generate(parser=self._build_parser(), name=name)

    def _build_parser(self):
        """Build and return the argument parser with conv-ics-specific options."""
        parser = super()._build_parser()
        parser.add_argument(
            "--columns",
            default="",
            help="Comma-separated list of fields to parse (order preserved, case insensitive).",
        )
        parser.add_argument(
            "--delimiter",
            default=None,
            help="Field delimiter for the tabular output (default: ',' CSV).",
        )
        parser.add_argument(
            "--full",
            action="store_true",
            help=(
                "Output the full iCalendar dump (every field found in the file, "
                "in iCalendar/ISO form)."
            ),
        )
        return parser

    def run(self, handler_class=IcsHandler):
        """Run the handler with parsed CLI arguments."""
        early_args, _ = self._build_early_parser().parse_known_args()
        self.logger = Logger(verbose=early_args.verbose, quiet=early_args.quiet)
        Console.quiet = early_args.quiet

        if early_args.completion:
            print(self.generate_completion())
            return

        if early_args.log:
            self.logger.print()
            return

        args = self._build_parser().parse_args()

        if IcsDownloader.is_url(args.input):
            downloader = IcsDownloader(logger=self.logger)
            saved = downloader.download(url=args.input, dest_dir=Path.cwd())
            self.logger.success(f"Downloaded: {saved}")
            args.input = str(saved)

        if args.recursive and args.output is None:
            Console.error("--output is required when --recursive is enabled.")
            sys.exit(1)

        if args.verbose >= 1:
            self.hero()

        output_delimiter, input_delimiter = self._resolve_delimiters(args)

        input_root = Path(args.input)
        handler = handler_class(
            logger=self.logger,
            columns=args.columns,
            delimiter=output_delimiter,
            input_delimiter=input_delimiter,
            recursive=args.recursive,
            input_root=input_root if input_root.is_dir() else None,
            full=args.full,
        )

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
                    dry_run=args.dry_run,
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

    @staticmethod
    def _resolve_delimiters(args):
        """Return ``(output_delimiter, input_delimiter)`` from the parsed CLI.

        ``-d X`` sets both to ``X``. With no flag, the output stays at CSV
        and the input is left unset, so the extension-based default kicks in.
        """
        if args.delimiter is not None:
            value = IcsConverterApp._unescape_delimiter(args.delimiter)
            return value, value
        return IcsParser.DEFAULT_DELIMITER, None

    @staticmethod
    def _unescape_delimiter(value):
        """Interpret common escape sequences (\\\\t, \\\\n, \\\\r) in delimiter strings."""
        try:
            return value.encode("utf-8").decode("unicode_escape")
        except UnicodeDecodeError:
            return value


#--------------------------------------------------
# Entry point
#--------------------------------------------------


if __name__ == "__main__":
    kernel = IcsConverterApp(
        author="TangoMan75",
        title="iCalendar Parser",
        description="Convert iCalendar (.ics) files to and from TSV/CSV files.",
    )
    kernel.run(IcsHandler)
