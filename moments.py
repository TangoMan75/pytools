#!/usr/bin/env python3
"""Date conversion helper for the opencode daily/journal commands.

This module merges the previous small helper scripts into a single entry
point. It exposes a class-based Python API and a CLI with date formatting,
timezone, and calendar adjustment options.

CLI:
    moments.py                 -> ISO 8601 (default: today)
    moments.py DATE --short    -> YYYY-MM-DD
    moments.py DATE --long     -> YYYY-MM-DD HH:MM:SS
    moments.py DATE --iso      -> ISO 8601 in Europe/Paris
    moments.py DATE --epoch    -> epoch milliseconds in Europe/Paris
    moments.py DATE --day "-3"             -> 3 days before DATE
    moments.py DATE --month "1" --year "2" -> 1 month + 2 years after DATE

Library helpers (used by the daily_* consumer scripts):
    MomentParser.resolve_date(raw)     -> 'YYYY-MM-DD' (raises ValueError)
    MomentParser.resolve_datetime(raw) -> Europe/Paris datetime
    MomentParser.parse_date(value)     -> 'YYYY-MM-DD' (exits 2 on bad input)
    RelativeTimeFormatter.format(...)  -> a human-readable relative time
"""

import argparse
import json
import re
import shlex
import sys
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

#--------------------------------------------------
# Console: stream output and diagnostics
#--------------------------------------------------


class Console:
    """Write results to stdout and errors to stderr."""

    def __init__(self, *, stdout=None, stderr=None):
        self._stdout = stdout if stdout is not None else sys.stdout
        self._stderr = stderr if stderr is not None else sys.stderr

    def write(self, message):
        """Write a result payload verbatim to standard output."""
        self._stdout.write(message)

    def error(self, message):
        """Write a fatal error to standard error."""
        print(f"ERROR: {message}", file=self._stderr)

#--------------------------------------------------
# TimezoneResolver: resolve IANA timezone names
#--------------------------------------------------


class TimezoneResolver:
    """Resolve IANA timezone names for parsing and output."""

    DEFAULT_NAME = "Europe/Paris"
    HELP = """\
--tz TZ          timezone for output (default: Europe/Paris)
                Common values: UTC, Europe/Paris, Europe/London,
                America/New_York, America/Los_Angeles, Asia/Tokyo,
                Australia/Sydney
                Any IANA timezone database name is accepted.
"""

    @classmethod
    def resolve(cls, *, name):
        """Return an IANA timezone or raise ValueError for an unknown name."""
        try:
            return ZoneInfo(name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown timezone '{name}'") from exc

    @classmethod
    def default(cls):
        """Return the default Europe/Paris timezone."""
        return cls.resolve(name=cls.DEFAULT_NAME)

#--------------------------------------------------
# MomentParser: parse and adjust dates and datetimes
#--------------------------------------------------


class MomentParser:
    """Parse, validate, and shift dates and datetimes."""

    DATE_FORMAT = "%Y-%m-%d"
    DATE_ONLY_PATTERN = r"^\d{4}-\d{2}-\d{2}$"
    EPOCH_PATTERN = r"^-?\d+$"
    EPOCH_MILLISECONDS_THRESHOLD = 100_000_000_000
    DATE_TIME_FORMATS = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%H:%M %d/%m/%Y",
        "%H:%M:%S %d/%m/%Y",
    )
    INVALID_DATE_MESSAGE = (
        'invalid date "{raw}". '
        "Use YYYY-MM-DD, YYYY-MM-DD HH:MM, YYYY-MM-DD HH:MM:SS, "
        "HH:MM DD/MM/YYYY, epoch seconds, or ISO 8601."
    )

    @classmethod
    def parse_date(cls, *, value):
        """Validate a ``YYYY-MM-DD`` string and return it unchanged.

        Bad input prints an error to stderr and exits with code 2.
        """
        try:
            return datetime.strptime(value, cls.DATE_FORMAT).date().isoformat()
        except ValueError:
            print(
                f"ERROR: invalid date '{value}', expected YYYY-MM-DD",
                file=sys.stderr,
            )
            sys.exit(2)

    @classmethod
    def resolve_datetime(cls, *, raw, tz=None):
        """Parse a date or datetime string and return an aware datetime.

        Accepts YYYY-MM-DD, YYYY-MM-DD HH:MM, YYYY-MM-DD HH:MM:SS,
        HH:MM DD/MM/YYYY, HH:MM:SS DD/MM/YYYY, epoch seconds or milliseconds,
        and ISO 8601. Naive input is interpreted in ``tz``. A date without a
        time component defaults to the current time of day.
        """
        target_tz = TimezoneResolver.default() if tz is None else tz
        normalized = raw.strip()

        epoch_moment = cls._resolve_epoch(value=normalized, tz=target_tz)
        if epoch_moment is not None:
            return epoch_moment

        iso_moment = cls._resolve_iso(value=normalized, tz=target_tz)
        if iso_moment is not None:
            return iso_moment

        for date_format in cls.DATE_TIME_FORMATS:
            try:
                moment = datetime.strptime(normalized, date_format)
            except ValueError:
                continue
            if date_format == cls.DATE_FORMAT:
                now = datetime.now(target_tz)
                moment = moment.replace(
                    hour=now.hour,
                    minute=now.minute,
                    second=now.second,
                    microsecond=now.microsecond,
                )
            return moment.replace(tzinfo=target_tz)

        raise ValueError(cls.INVALID_DATE_MESSAGE.format(raw=raw))

    @classmethod
    def _resolve_epoch(cls, *, value, tz):
        """Return the datetime for an epoch value, or None when not an epoch."""
        if not re.match(cls.EPOCH_PATTERN, value):
            return None
        try:
            timestamp = int(value)
            if abs(timestamp) >= cls.EPOCH_MILLISECONDS_THRESHOLD:
                timestamp //= 1000
            return datetime.fromtimestamp(
                timestamp, tz=timezone.utc
            ).astimezone(tz)
        except (OSError, OverflowError, ValueError):
            return None

    @classmethod
    def _resolve_iso(cls, *, value, tz):
        """Return the datetime for an ISO 8601 value, or None."""
        if "T" not in value:
            return None
        try:
            iso_value = value[:-1] + "+00:00" if value[-1] in ("Z", "z") else value
            moment = datetime.fromisoformat(iso_value)
        except ValueError:
            return None
        if moment.tzinfo is None:
            return moment.replace(tzinfo=tz)
        return moment.astimezone(tz)

    @classmethod
    def resolve_date(cls, *, raw):
        """Parse a date string in any supported format and return YYYY-MM-DD."""
        return cls.resolve_datetime(raw=raw).date().isoformat()

    @classmethod
    def previous_date(cls, *, target):
        """Return the calendar day before ``target``."""
        moment = datetime.strptime(target, cls.DATE_FORMAT)
        return (moment - timedelta(days=1)).strftime(cls.DATE_FORMAT)

    @staticmethod
    def days_in_month(*, year, month):
        """Return the number of days in a calendar month."""
        next_month = date(year + (month == 12), month % 12 + 1, 1)
        return (next_month - date(year, month, 1)).days

    @classmethod
    def _shift_months(cls, *, target, months):
        """Shift a date by signed calendar months, clamping month end."""
        target_date = datetime.strptime(target, cls.DATE_FORMAT).date()
        total_months = target_date.year * 12 + target_date.month - 1 + months
        year, month_index = divmod(total_months, 12)
        month = month_index + 1
        last_day = cls.days_in_month(year=year, month=month)
        return date(year, month, min(target_date.day, last_day)).isoformat()

    @classmethod
    def subtract_months(cls, *, target, months=1):
        """Return ``target`` N calendar months earlier, clamping month end."""
        return cls._shift_months(target=target, months=-months)

    @classmethod
    def add_months(cls, *, target, months=1):
        """Return ``target`` N calendar months later, clamping month end."""
        return cls._shift_months(target=target, months=months)

    @classmethod
    def _shift_years(cls, *, target, years):
        """Shift a date by signed calendar years, clamping February 29."""
        target_date = datetime.strptime(target, cls.DATE_FORMAT).date()
        try:
            return target_date.replace(year=target_date.year + years).isoformat()
        except ValueError:
            return target_date.replace(
                year=target_date.year + years, day=28
            ).isoformat()

    @classmethod
    def subtract_years(cls, *, target, years=1):
        """Return ``target`` N calendar years earlier, clamping February 29."""
        return cls._shift_years(target=target, years=-years)

    @classmethod
    def add_years(cls, *, target, years=1):
        """Return ``target`` N calendar years later, clamping February 29."""
        return cls._shift_years(target=target, years=years)

    @classmethod
    def replace_date(cls, *, moment, iso_date):
        """Replace the date part of a moment, keeping its time and timezone."""
        return moment.replace(
            year=int(iso_date[0:4]),
            month=int(iso_date[5:7]),
            day=int(iso_date[8:10]),
        )

    @classmethod
    def format_date(cls, *, target, output_format, tz=None):
        """Convert a validated short date to the requested output format."""
        if output_format == "short":
            return target
        target_tz = TimezoneResolver.default() if tz is None else tz
        local = datetime.strptime(target, cls.DATE_FORMAT).replace(tzinfo=target_tz)
        if output_format == "iso":
            return local.isoformat()
        if output_format == "epoch":
            return str(int(local.timestamp() * 1000))
        raise ValueError(f"invalid output format '{output_format}'")

    @classmethod
    def is_date_only(cls, *, value):
        """Return True when ``value`` is exactly a YYYY-MM-DD date."""
        return bool(re.match(cls.DATE_ONLY_PATTERN, value.strip()))

#--------------------------------------------------
# RelativeTimeFormatter: human-readable relative time
#--------------------------------------------------


class RelativeTimeFormatter:
    """Render the elapsed time between two moments as human-readable text."""

    @classmethod
    def _replace_clamped(cls, *, moment, **components):
        """Replace date components, clamping the day to the last valid day."""
        try:
            return moment.replace(**components)
        except ValueError:
            day = components.pop("day", None)
            if day is None:
                raise
            year = components.get("year", moment.year)
            month = components.get("month", moment.month)
            last_day = MomentParser.days_in_month(year=year, month=month)
            return moment.replace(day=min(day, last_day), **components)

    @classmethod
    def format(cls, *, target, origin, short=False):
        """Return the relative time from ``origin`` to ``target``.

        ``short`` limits the output to years, months, and days.
        """
        if target < origin:
            sign = "-"
            origin, target = target, origin
        else:
            sign = ""

        years = 0
        cursor = origin
        while True:
            next_cursor = cls._replace_clamped(moment=cursor, year=cursor.year + 1)
            if next_cursor <= target:
                years += 1
                cursor = next_cursor
            else:
                break

        months = 0
        while True:
            if cursor.month == 12:
                next_cursor = cls._replace_clamped(
                    moment=cursor, year=cursor.year + 1, month=1
                )
            else:
                next_cursor = cls._replace_clamped(
                    moment=cursor, month=cursor.month + 1
                )
            if next_cursor <= target:
                months += 1
                cursor = next_cursor
            else:
                break

        remaining = target - cursor
        days = remaining.days
        hours = remaining.seconds // 3600
        minutes = (remaining.seconds % 3600) // 60
        seconds = remaining.seconds % 60

        parts = []
        if years:
            parts.append(cls._unit(value=years, name="year"))
        if months:
            parts.append(cls._unit(value=months, name="month"))
        if days:
            parts.append(cls._unit(value=days, name="day"))
        if not short:
            if hours:
                parts.append(cls._unit(value=hours, name="hour"))
            if minutes:
                parts.append(cls._unit(value=minutes, name="minute"))
            if seconds:
                parts.append(cls._unit(value=seconds, name="second"))

        result = " ".join(parts) if parts else "0"
        return f"{sign}{result}" if sign else result

    @staticmethod
    def _unit(*, value, name):
        """Return one counted unit with its plural suffix."""
        suffix = "s" if value != 1 else ""
        return f"{value} {name}{suffix}"

#--------------------------------------------------
# MomentFormatter: render absolute output formats
#--------------------------------------------------


class MomentFormatter:
    """Render a resolved moment in the selected absolute output format."""

    LONG_FORMAT = "%Y-%m-%d %H:%M:%S"
    WEEKDAY_FORMAT = "%A"

    @classmethod
    def format(cls, *, moment, options):
        """Render a resolved moment according to the selected output format."""
        if options.utc:
            moment = moment.astimezone(timezone.utc)
        if options.epoch:
            return str(int(moment.timestamp() * 1000))
        if options.iso:
            return moment.isoformat()
        if options.short:
            return moment.date().isoformat()
        if options.long:
            return moment.strftime(cls.LONG_FORMAT)
        if options.format:
            return moment.strftime(options.format)
        if options.weekday:
            return moment.strftime(cls.WEEKDAY_FORMAT)
        if options.week_number:
            return str(moment.isocalendar().week)
        return moment.isoformat()

#--------------------------------------------------
# MomentJsonRenderer: render the --json document
#--------------------------------------------------


class MomentJsonRenderer:
    """Render the machine-readable document selected by ``--json``."""

    @classmethod
    def render(cls, *, moment, options, raw):
        """Return the JSON document for a resolved moment."""
        output_moment = moment.astimezone(timezone.utc) if options.utc else moment
        return json.dumps({
            "input": raw,
            "tz": "UTC" if options.utc else options.tz,
            "local": moment.isoformat(),
            "utc": moment.astimezone(timezone.utc).isoformat(),
            "date": output_moment.date().isoformat(),
            "epoch_ms": int(moment.timestamp() * 1000),
            "weekday": output_moment.strftime(MomentFormatter.WEEKDAY_FORMAT),
            "week_number": output_moment.isocalendar().week,
        }, ensure_ascii=False, indent=2)

#--------------------------------------------------
# Usage: custom help text
#--------------------------------------------------


class Usage:
    """Provide the custom help text for the moments CLI."""

    TEXT = """\
moments.py [DATE] [FORMAT] [ADJUSTMENT] [--tz TZ] [--from DATE]

DATE is optional and defaults to today. It is the reference date for all calculations.
A date without a time component uses the current time of day.
Accepted formats: YYYY-MM-DD, YYYY-MM-DD HH:MM, HH:MM DD/MM/YYYY, epoch, ISO 8601.
  --short          output YYYY-MM-DD
  --long           output YYYY-MM-DD HH:MM:SS
  --iso            output ISO 8601 (the default)
  --epoch          output epoch milliseconds
  --format FMT     output using a strftime format
  --weekday        output the weekday name
  --week-number    output the ISO week number
  --json           output a JSON object
  --utc            convert output to UTC
  --from DATE      compute relative time from DATE to the target
  --sec N          adjust seconds (signed integer)
  --min N          adjust minutes (signed integer)
  --hour N         adjust hours (signed integer)
  --day N          adjust days (signed integer)
  --week N         adjust weeks (signed integer)
  --month N        adjust months (signed integer)
  --year N         adjust years (signed integer)
  --tz TZ           timezone (default: Europe/Paris)
  --verbose        increase verbosity (stackable; -v is accepted)
  --quiet          suppress non-error output; runtime errors are still reported
  --completion     print bash completion script to stdout and exit
"""

    @classmethod
    def render(cls):
        """Return the help output, including the timezone examples."""
        return f"usage: {cls.TEXT}{TimezoneResolver.HELP}"

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

complete -F _{completion_name}_completions {shlex.quote(name)}
'''

    @classmethod
    def generate(cls, *, parser, name):
        """Return a bash completion script for ``parser``."""
        all_opts, categories = cls._classify_parser_actions(parser)
        return cls._render_script(
            all_opts=all_opts, categories=categories, name=name
        )

#--------------------------------------------------
# CliParser: build the command-line interface
#--------------------------------------------------


class CliParser:
    """Build the moments argument parser."""

    def build(self):
        """Build and return the argument parser."""
        parser = argparse.ArgumentParser(usage=Usage.TEXT, add_help=False)
        parser.add_argument(
            "date", nargs="?", default="",
            help="date string (YYYY-MM-DD, HH:MM DD/MM/YYYY, epoch, ISO 8601, etc.)",
        )
        parser.add_argument(
            "--verbose", "-v", action="count", default=0,
            help="Increase verbosity",
        )
        parser.add_argument(
            "--quiet", action="store_true",
            help="suppress non-error output; runtime errors are still reported",
        )
        parser.add_argument(
            "--tz", default=TimezoneResolver.DEFAULT_NAME, metavar="TZ",
            help="IANA timezone (default: Europe/Paris)",
        )
        parser.add_argument(
            "--utc", action="store_true", help="convert output to UTC",
        )
        format_group = parser.add_mutually_exclusive_group()
        format_group.add_argument(
            "--short", action="store_true", help="output YYYY-MM-DD",
        )
        format_group.add_argument(
            "--long", action="store_true", help="output YYYY-MM-DD HH:MM:SS",
        )
        format_group.add_argument(
            "--epoch", action="store_true", help="output epoch milliseconds",
        )
        format_group.add_argument(
            "--iso", action="store_true", help="output an ISO-8601 date",
        )
        format_group.add_argument(
            "--format", metavar="FMT", help="output using a strftime format",
        )
        format_group.add_argument(
            "--weekday", action="store_true", help="output the weekday name",
        )
        format_group.add_argument(
            "--week-number", action="store_true",
            help="output the ISO week number",
        )
        format_group.add_argument(
            "--json", action="store_true", help="output a JSON object",
        )
        unit_group = parser.add_argument_group("unit adjustments (signed integers)")
        unit_group.add_argument(
            "--sec", metavar="N", type=int,
            help="adjust seconds (signed integer)",
        )
        unit_group.add_argument(
            "--min", metavar="N", type=int,
            help="adjust minutes (signed integer)",
        )
        unit_group.add_argument(
            "--hour", metavar="N", type=int,
            help="adjust hours (signed integer)",
        )
        unit_group.add_argument(
            "--day", metavar="N", type=int,
            help="adjust days (signed integer)",
        )
        unit_group.add_argument(
            "--week", metavar="N", type=int,
            help="adjust weeks (signed integer)",
        )
        unit_group.add_argument(
            "--month", metavar="N", type=int,
            help="adjust months (signed integer)",
        )
        unit_group.add_argument(
            "--year", metavar="N", type=int,
            help="adjust years (signed integer)",
        )
        parser.add_argument(
            "--from", dest="from_date", metavar="DATE",
            help="compute relative time from DATE to the target",
        )
        parser.add_argument(
            "--completion", action="store_true",
            help="print bash completion script to stdout and exit",
        )
        return parser

#--------------------------------------------------
# Adjustments: signed unit shifts for a moment
#--------------------------------------------------


class UnitAdjustment(ABC):
    """Apply one signed unit adjustment to a moment."""

    @abstractmethod
    def apply(self, *, moment, value):
        """Return the adjusted moment."""


class ClockAdjustment(UnitAdjustment):
    """Shift a moment by a whole number of clock units."""

    DELTA_KEYS = {
        "sec": "seconds",
        "min": "minutes",
        "hour": "hours",
        "day": "days",
        "week": "weeks",
    }

    def __init__(self, *, unit):
        if unit not in self.DELTA_KEYS:
            raise ValueError(f"unsupported clock unit '{unit}'")
        self._unit = unit

    def apply(self, *, moment, value):
        """Return the moment shifted by ``value`` clock units."""
        return moment + timedelta(**{self.DELTA_KEYS[self._unit]: value})


class MonthAdjustment(UnitAdjustment):
    """Shift a moment by signed calendar months, clamping month end."""

    def apply(self, *, moment, value):
        """Return the moment shifted by ``value`` calendar months."""
        iso_date = moment.date().isoformat()
        if value >= 0:
            target = MomentParser.add_months(target=iso_date, months=value)
        else:
            target = MomentParser.subtract_months(target=iso_date, months=-value)
        return MomentParser.replace_date(moment=moment, iso_date=target)


class YearAdjustment(UnitAdjustment):
    """Shift a moment by signed calendar years, clamping February 29."""

    def apply(self, *, moment, value):
        """Return the moment shifted by ``value`` calendar years."""
        iso_date = moment.date().isoformat()
        if value >= 0:
            target = MomentParser.add_years(target=iso_date, years=value)
        else:
            target = MomentParser.subtract_years(target=iso_date, years=-value)
        return MomentParser.replace_date(moment=moment, iso_date=target)


class MomentAdjuster:
    """Apply every requested unit adjustment to a moment, in unit order."""

    def __init__(self, *, adjustments):
        self._adjustments = dict(adjustments)

    def adjust(self, *, moment, options):
        """Return the moment with all non-None adjustments applied."""
        for unit, adjustment in self._adjustments.items():
            value = getattr(options, unit)
            if value is not None:
                moment = adjustment.apply(moment=moment, value=value)
        return moment

#--------------------------------------------------
# Application: orchestrate the CLI
#--------------------------------------------------


class Application:
    """Run the moments command and translate failures into exit codes."""

    EXIT_SUCCESS = 0
    EXIT_ERROR = 1

    def __init__(self, *, argv=None, console=None):
        self._argv = list(sys.argv[1:] if argv is None else argv)
        self._console = console if console is not None else Console()
        self._adjuster = MomentAdjuster(adjustments={
            "sec": ClockAdjustment(unit="sec"),
            "min": ClockAdjustment(unit="min"),
            "hour": ClockAdjustment(unit="hour"),
            "day": ClockAdjustment(unit="day"),
            "week": ClockAdjustment(unit="week"),
            "month": MonthAdjustment(),
            "year": YearAdjustment(),
        })

    def run(self):
        """Parse the command line, resolve the moment, and return an exit code."""
        if "--completion" in self._argv:
            self._console.write(
                Completion.generate(
                    parser=CliParser().build(), name=self._command_name()
                ) + "\n"
            )
            return Application.EXIT_SUCCESS
        if any(argument in ("-h", "--help") for argument in self._argv):
            self._console.write(Usage.render())
            return Application.EXIT_SUCCESS

        options = CliParser().build().parse_args(self._argv)
        raw = options.date.strip() if options.date else ""
        if not raw:
            raw = date.today().strftime(MomentParser.DATE_FORMAT)

        try:
            target_tz = TimezoneResolver.resolve(name=options.tz)
            moment = MomentParser.resolve_datetime(raw=raw, tz=target_tz)
        except ValueError as exc:
            return self._error(str(exc))

        moment = self._adjuster.adjust(moment=moment, options=options)

        if options.from_date:
            return self._write_relative(
                moment=moment, options=options, target_tz=target_tz
            )
        if options.json:
            self._console.write(
                MomentJsonRenderer.render(moment=moment, options=options, raw=raw)
                + "\n"
            )
        else:
            self._console.write(
                MomentFormatter.format(moment=moment, options=options) + "\n"
            )
        return Application.EXIT_SUCCESS

    @staticmethod
    def _command_name():
        """Return the installed command name derived from argv[0]."""
        return Path(sys.argv[0]).resolve().stem

    def _write_relative(self, *, moment, options, target_tz):
        """Write the relative time between ``--from`` and the target moment."""
        try:
            origin = MomentParser.resolve_datetime(
                raw=options.from_date, tz=target_tz
            )
        except ValueError as exc:
            return self._error(str(exc))
        if MomentParser.is_date_only(value=options.from_date):
            origin = origin.replace(hour=0, minute=0, second=0, microsecond=0)
        self._console.write(
            RelativeTimeFormatter.format(
                target=moment, origin=origin, short=options.short
            ) + "\n"
        )
        return Application.EXIT_SUCCESS

    def _error(self, message):
        """Write a runtime error and return the error exit code."""
        self._console.error(message)
        return Application.EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(Application().run())
