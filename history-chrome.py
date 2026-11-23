#!/usr/bin/env python3
"""Read Google Chrome history and emit a chronological log of visits."""

import argparse
import json
import os
import platform
import re
import shlex
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

#--------------------------------------------------
# Logging
#--------------------------------------------------


class Logger:
    """Write warnings and errors to stderr, honoring quiet mode."""

    def __init__(self, *, quiet=False):
        self._quiet = quiet

    def warning(self, *, message):
        """Print a warning unless quiet mode is enabled."""
        if not self._quiet:
            print(f"WARNING: {message}", file=sys.stderr)

    def danger(self, *, message):
        """Print an error to stderr; errors are never suppressed."""
        print(f"ERROR: {message}", file=sys.stderr)


class NullLogger:
    """No-op logger used when no logger is injected."""

    def warning(self, *, message):
        """Discard a warning."""

    def danger(self, *, message):
        """Discard an error."""


#--------------------------------------------------
# Date range resolution
#--------------------------------------------------


class DateRangeResolver:
    """Resolve human and epoch-millisecond CLI ranges into a UTC window."""

    DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
    DATE_FORMAT = "%Y-%m-%d"

    def __init__(self, *, logger=None):
        self._logger = logger if logger is not None else NullLogger()

    @staticmethod
    def add_arguments(*, parser):
        """Register --start, --end, --start-ms, and --end-ms on the parser."""
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

    @classmethod
    def parse_human(cls, *, value):
        """Parse a date or datetime string into ``(datetime, had_explicit_time)``."""
        for date_format, had_time in (
            (cls.DATETIME_FORMAT, True),
            (cls.DATE_FORMAT, False),
        ):
            try:
                return datetime.strptime(value, date_format), had_time
            except ValueError:
                continue
        raise ValueError(
            f"invalid date '{value}', expected 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS'"
        )

    @staticmethod
    def resolve(*, options):
        """Return ``(start_ms, end_ms)`` from parsed CLI options."""
        now = datetime.now()
        from_ms = DateRangeResolver._start_ms(options=options, now=now)
        to_ms = DateRangeResolver._end_ms(options=options, now=now)
        if to_ms < from_ms:
            raise ValueError("end cannot be set before start")
        return from_ms, to_ms

    def resolve_or_exit(self, *, options):
        """Resolve the range, reporting invalid input and exiting 2."""
        try:
            return self.resolve(options=options)
        except ValueError as error:
            self._logger.danger(message=str(error))
            sys.exit(2)

    @staticmethod
    def default_end_ms(*, from_ms):
        """Return midnight after the local calendar day containing ``from_ms``."""
        local = datetime.fromtimestamp(from_ms / 1000, tz=timezone.utc).astimezone()
        next_midnight = datetime.combine(
            local.date() + timedelta(days=1), datetime.min.time(), tzinfo=local.tzinfo
        )
        return int(next_midnight.timestamp() * 1000)

    @staticmethod
    def _start_ms(*, options, now):
        if options.start_ms is not None and options.start is not None:
            raise ValueError("pass only one of --start or --start-ms (not both)")
        if options.start_ms is not None:
            return options.start_ms
        if options.start is not None:
            moment, had_time = DateRangeResolver.parse_human(value=options.start)
            if not had_time:
                moment = moment.replace(hour=0, minute=0, second=0, microsecond=0)
            return int(moment.timestamp() * 1000)
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return int(midnight.timestamp() * 1000)

    @staticmethod
    def _end_ms(*, options, now):
        if options.end_ms is not None and options.end is not None:
            raise ValueError("pass only one of --end or --end-ms (not both)")
        if options.end_ms is not None:
            return options.end_ms
        if options.end is not None:
            moment, had_time = DateRangeResolver.parse_human(value=options.end)
            if not had_time:
                moment = moment.replace(
                    hour=now.hour, minute=now.minute, second=now.second, microsecond=0
                )
            return int(moment.timestamp() * 1000)
        return int(now.timestamp() * 1000)


#--------------------------------------------------
# Visit formatting
#--------------------------------------------------


class VisitFormatter:
    """Format visit values for JSON and Markdown output."""

    @staticmethod
    def format_duration(*, seconds):
        """Render a duration compactly by magnitude."""
        if seconds <= 0:
            return ""
        if seconds < 60:
            return f"{int(seconds)}s"
        if seconds < 3600:
            return f"{int(seconds // 60)}m{int(seconds % 60):02d}s"
        return f"{int(seconds // 3600)}h{int((seconds % 3600) // 60):02d}m"

    @staticmethod
    def format_datetime(*, epoch_ms):
        """Render epoch milliseconds as a local ``YYYY-MM-DD HH:MM:SS`` string."""
        moment = datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc).astimezone()
        return moment.strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def format_time(*, epoch_ms):
        """Render epoch milliseconds as a local ``HH:MM:SS`` string."""
        return VisitFormatter.format_datetime(epoch_ms=epoch_ms)[11:19]

    @staticmethod
    def escape_markdown(*, value):
        """Escape pipes and flatten newlines for a Markdown table cell."""
        if value is None:
            return ""
        return str(value).replace("|", "\\|").replace("\n", " ").strip()

    @staticmethod
    def truncate(*, value, limit):
        """Flatten and shorten a value to ``limit`` characters with an ellipsis."""
        if value is None:
            return ""
        text = str(value).replace("\n", " ").strip()
        return text if len(text) <= limit else text[: limit - 1] + "\u2026"

    @staticmethod
    def format_range_title(*, from_ms, to_ms):
        """Render a single date, or an arrow-separated multi-day range."""
        start = datetime.fromtimestamp(from_ms / 1000).date().isoformat()
        end = datetime.fromtimestamp(to_ms / 1000).date().isoformat()
        return start if start == end else f"{start} \u2192 {end}"


#--------------------------------------------------
# Chrome history access
#--------------------------------------------------


class ChromeHistory:
    """Locate, snapshot, and query Chrome History databases."""

    EPOCH_OFFSET_US = 11644473600000000
    HISTORY_FILE = "History"
    PROFILE_PATTERN = re.compile(r"^(Default|Profile \d+)$")
    CORE_TRANSITIONS = {
        0: "link",
        1: "typed",
        2: "auto_bookmark",
        3: "auto_subframe",
        4: "manual_subframe",
        5: "generated",
        6: "start_page",
        7: "form_submit",
        8: "reload",
        9: "keyword",
        10: "keyword_generated",
    }
    TYPED_CORES = {"typed", "keyword", "keyword_generated", "form_submit", "reload"}
    VISITS_SQL = (
        "SELECT v.visit_time, u.url, u.title, v.visit_duration, v.transition "
        "FROM visits v JOIN urls u ON u.id = v.url "
        "WHERE v.visit_time >= ? AND v.visit_time < ? "
    )
    TYPED_FILTER_SQL = "AND (v.transition & 0xFF) IN (1, 7, 8, 9, 10) "

    def __init__(self, *, user_data):
        self._user_data = user_data

    @staticmethod
    def default_user_data_dir():
        """Return the platform-specific Chrome user-data directory."""
        system = platform.system()
        if system == "Windows":
            appdata = os.environ.get("LOCALAPPDATA", "")
            if not appdata:
                return ""
            return os.path.join(appdata, "Google", "Chrome", "User Data")
        if system == "Darwin":
            return os.path.expanduser("~/Library/Application Support/Google/Chrome")
        return os.path.expanduser("~/.config/google-chrome")

    @staticmethod
    def webkit_us_to_epoch_ms(*, value):
        """Convert WebKit microseconds to Unix epoch milliseconds."""
        try:
            return (int(value) - ChromeHistory.EPOCH_OFFSET_US) // 1000
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def epoch_ms_to_webkit_us(*, value):
        """Convert Unix epoch milliseconds to WebKit microseconds."""
        return (value * 1000) + ChromeHistory.EPOCH_OFFSET_US

    @staticmethod
    def decode_transition(*, transition):
        """Decode a Chrome transition bitfield into named flags."""
        value = int(transition or 0)
        core = ChromeHistory.CORE_TRANSITIONS.get(value & 0xFF, f"core_{value & 0xFF}")
        return {
            "transition_core": core,
            "redirect": bool(value & (1 << 20)),
            "server_redirect": bool(value & (1 << 19)),
            "client_redirect": bool(value & (1 << 18)),
            "from_address_bar": bool(value & (1 << 22)),
            "home_page": bool(value & (1 << 23)),
            "blocked": bool(value & (1 << 25)),
            "typed": core in ChromeHistory.TYPED_CORES,
        }

    def discover_profiles(self):
        """Return Default/Profile N directories that contain a History file."""
        root = Path(self._user_data)
        if not root.is_dir():
            return []
        found = []
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            if self.PROFILE_PATTERN.match(child.name) and (child / self.HISTORY_FILE).is_file():
                found.append(child.name)
        return found

    def locate_profiles(self, *, db_path="", profile=""):
        """Return ``(profiles, missing_paths)`` for the requested selection."""
        if db_path:
            return [("explicit", db_path)], []
        names = [profile] if profile else (self.discover_profiles() or ["Default"])
        profiles = []
        missing = []
        for name in names:
            path = os.path.join(self._user_data, name, self.HISTORY_FILE)
            if os.path.isfile(path):
                profiles.append((name, path))
            else:
                missing.append(path)
        return profiles, missing

    @staticmethod
    def snapshot_to_tmp(*, history_path):
        """Copy the locked History file to a fresh temporary SQLite file."""
        handle, tmp_path = tempfile.mkstemp(prefix="chrome-history-", suffix=".sqlite")
        os.close(handle)
        shutil.copyfile(history_path, tmp_path)
        return tmp_path

    def read_visits(self, *, db_path, start_us, end_us, typed_only, profile):
        """Return the visits in the WebKit-microsecond range for one profile."""
        query = self.VISITS_SQL
        if typed_only:
            query += self.TYPED_FILTER_SQL
        query += "ORDER BY v.visit_time ASC"
        connection = sqlite3.connect(db_path)
        try:
            rows = connection.execute(query, (start_us, end_us)).fetchall()
        finally:
            connection.close()
        return [Visit.from_row(row=row, profile=profile) for row in rows]


class Visit:
    """A single visit loaded from a Chrome History database."""

    URL_LIMIT = 60
    TITLE_LIMIT = 50

    def __init__(
        self, *, epoch_ms, url, title, duration_ms, profile,
        transition_core, redirect, typed,
    ):
        self._epoch_ms = epoch_ms
        self._url = url
        self._title = title
        self._duration_ms = duration_ms
        self._profile = profile
        self._transition_core = transition_core
        self._redirect = redirect
        self._typed = typed
        self._index = 0

    @classmethod
    def from_row(cls, *, row, profile):
        """Build a visit from a Chrome ``visits``/``urls`` join row."""
        visit_time, url, title, visit_duration, transition = row
        info = ChromeHistory.decode_transition(transition=transition)
        return cls(
            epoch_ms=ChromeHistory.webkit_us_to_epoch_ms(value=visit_time),
            url=url or "",
            title=title or "",
            duration_ms=int(visit_duration or 0) // 1000,
            profile=profile,
            transition_core=info["transition_core"],
            redirect=info["redirect"],
            typed=info["typed"],
        )

    def sort_key(self):
        """Return the chronological sort key used for the final report."""
        return self._epoch_ms, self._url

    def number(self, *, index):
        """Assign the one-based position shown in the report."""
        self._index = index

    def domain(self):
        """Return the URL host, or None when the URL has no scheme."""
        if "://" not in self._url:
            return None
        return self._url.split("/")[2]

    def is_typed(self):
        """Return whether the visit came from a typed URL-bar-like transition."""
        return self._typed

    def as_dict(self, *, formatter):
        """Return the JSON-ready representation of this visit."""
        return {
            "datetime": formatter.format_datetime(epoch_ms=self._epoch_ms),
            "url": self._url,
            "title": self._title,
            "visit_duration_ms": self._duration_ms,
            "profile": self._profile,
            "transition_core": self._transition_core,
            "redirect": self._redirect,
            "typed": self._typed,
            "index": self._index,
        }

    def as_markdown_row(self, *, formatter):
        """Return the Markdown table cells for this visit."""
        return (
            str(self._index),
            formatter.format_time(epoch_ms=self._epoch_ms),
            formatter.escape_markdown(
                value=formatter.truncate(value=self._url, limit=self.URL_LIMIT)
            ),
            formatter.escape_markdown(
                value=formatter.truncate(value=self._title, limit=self.TITLE_LIMIT)
            ),
            formatter.format_duration(seconds=self._duration_ms / 1000.0),
            self._transition_core,
        )


#--------------------------------------------------
# Rendering
#--------------------------------------------------


class MarkdownRenderer:
    """Render visits as a Markdown table with a summary line."""

    def __init__(self, *, formatter):
        self._formatter = formatter

    def render(self, *, visits, from_ms, to_ms):
        """Return the Markdown report for the given visits and window."""
        title = self._formatter.format_range_title(from_ms=from_ms, to_ms=to_ms)
        if not visits:
            return f"# chrome History \u2014 {title}\n\n_No visits in this range._\n"

        lines = [f"# chrome History \u2014 {title}", ""]
        lines.append("| # | Time | URL | Title | Duration | Transition |")
        lines.append("|---|------|-----|-------|----------|------------|")
        for visit in visits:
            cells = visit.as_markdown_row(formatter=self._formatter)
            lines.append("| " + " | ".join(cells) + " |")

        domains = set()
        typed = 0
        for visit in visits:
            domain = visit.domain()
            if domain is not None:
                domains.add(domain)
            if visit.is_typed():
                typed += 1
        lines.append("")
        lines.append(
            f"**Total:** {len(visits)} visits across {len(domains)} domains, "
            f"{typed} typed/bar entries"
        )
        return "\n".join(lines) + "\n"


class JsonRenderer:
    """Render visits as indented JSON."""

    def __init__(self, *, formatter):
        self._formatter = formatter

    def render(self, *, visits):
        """Return the JSON report for the given visits."""
        payload = [visit.as_dict(formatter=self._formatter) for visit in visits]
        return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


#--------------------------------------------------
# Shell completion
#--------------------------------------------------


class Completion:
    """Generate a bash completion script for the command-line parser."""

    @staticmethod
    def classify_parser_actions(*, parser):
        """Walk parser actions and return ``(all_options, categories)``."""
        all_options = set()
        categories = {"boolean": [], "verbose": [], "file": [], "glob": []}
        file_keys = ("output", "file", "path", "dest")
        glob_keys = ("include", "exclude", "glob", "pattern")
        for action in parser._actions:  # noqa: SLF001
            options = action.option_strings
            if not options:
                continue
            all_options.update(options)
            joined = " ".join(options).lower()
            if action.nargs == 0 and action.const is True:
                categories["boolean"].extend(options)
            if action.__class__.__name__ == "_CountAction":
                categories["verbose"].extend(options)
            if any(key in joined for key in file_keys):
                categories["file"].extend(options)
            if any(key in joined for key in glob_keys):
                categories["glob"].extend(options)
        return all_options, categories

    @staticmethod
    def render_case(*, option, kind):
        """Return the bash case branch for one option kind."""
        bodies = {
            "boolean": "            COMPREPLY=()\n",
            "verbose": "            COMPREPLY=( $(compgen -W \"-v -vv -vvv\" -- \"${cur}\") )\n",
            "file": "            COMPREPLY=( $(compgen -f -- \"${cur}\") )\n",
            "glob": "            COMPREPLY=( $(compgen -G \"${cur}*\") )\n",
        }
        return f"        {option})\n{bodies[kind]}            return 0\n            ;;\n"

    @classmethod
    def generate(cls, *, parser, name):
        """Return a bash completion script for the parser and command name."""
        all_options, categories = cls.classify_parser_actions(parser=parser)
        blocks = []
        for kind, options in categories.items():
            for option in sorted(set(options)):
                blocks.append(cls.render_case(option=option, kind=kind))
        option_case = "".join(blocks)
        completion_name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
        sorted_options = sorted(
            all_options, key=lambda option: (not option.startswith("--"), option.lower())
        )
        options_str = " ".join(sorted_options)
        return f'''#!/bin/bash

_{completion_name}_completions()
{{
    local cur prev opts
    COMPREPLY=()
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"

    opts="{options_str}"

    case "${{prev}}" in
{option_case}        *)
            COMPREPLY=( $(compgen -W "${{opts}}" -- "${{cur}}") )
            return 0
            ;;
    esac
}}

complete -f -F _{completion_name}_completions {shlex.quote(name)}
'''


#--------------------------------------------------
# Command line
#--------------------------------------------------


class CommandLine:
    """Build the argparse parser for the history-chrome CLI."""

    DESCRIPTION = "Read Google Chrome history."

    @staticmethod
    def build_parser():
        """Return the fully configured argument parser."""
        parser = argparse.ArgumentParser(description=CommandLine.DESCRIPTION)
        parser.add_argument(
            "--user-data",
            default=ChromeHistory.default_user_data_dir(),
            help=argparse.SUPPRESS,
        )
        parser.add_argument(
            "--profile", default="",
            help="profile name to read (default: scan Default + Profile 1..N)",
        )
        parser.add_argument(
            "--db", default="",
            help="explicit path to a History file (overrides --user-data/--profile)",
        )
        parser.add_argument(
            "--no-copy", action="store_true",
            help="open the History file in place (Chrome must be closed)",
        )
        parser.add_argument(
            "--typed-only", action="store_true",
            help="keep only URL-bar / keyword / form-submit / reload entries",
        )
        DateRangeResolver.add_arguments(parser=parser)
        parser.add_argument("--md", action="store_true", help="print output as a markdown table")
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
# Application
#--------------------------------------------------


class Application:
    """Orchestrate range resolution, history loading, and report output."""

    def __init__(
        self, *, options, resolver, history, markdown, json_renderer, logger,
    ):
        self._options = options
        self._resolver = resolver
        self._history = history
        self._markdown = markdown
        self._json = json_renderer
        self._logger = logger

    def run(self):
        """Run the report and return the process exit code."""
        from_ms, to_ms = self._resolver.resolve_or_exit(options=self._options)
        if self._options.end is None and self._options.end_ms is None:
            to_ms = DateRangeResolver.default_end_ms(from_ms=from_ms)

        profiles, missing = self._history.locate_profiles(
            db_path=self._options.db,
            profile=self._options.profile,
        )
        for path in missing:
            self._logger.warning(message=f"{path} not found, skipping")
        if not profiles:
            self._logger.danger(message="no History files found")
            return 1

        visits = self._collect_visits(profiles=profiles, from_ms=from_ms, to_ms=to_ms)
        visits.sort(key=Visit.sort_key)
        for index, visit in enumerate(visits, 1):
            visit.number(index=index)
        self._write(visits=visits, from_ms=from_ms, to_ms=to_ms)
        return 0

    def _collect_visits(self, *, profiles, from_ms, to_ms):
        start_us = ChromeHistory.epoch_ms_to_webkit_us(value=from_ms)
        end_us = ChromeHistory.epoch_ms_to_webkit_us(value=to_ms)
        snapshots = []
        visits = []
        try:
            for name, path in profiles:
                if self._options.no_copy:
                    db_path = path
                else:
                    db_path = self._history.snapshot_to_tmp(history_path=path)
                    snapshots.append(db_path)
                visits.extend(
                    self._history.read_visits(
                        db_path=db_path,
                        start_us=start_us,
                        end_us=end_us,
                        typed_only=self._options.typed_only,
                        profile=name,
                    )
                )
        finally:
            for path in snapshots:
                self._remove(path=path)
        return visits

    def _write(self, *, visits, from_ms, to_ms):
        if self._options.md:
            output = self._markdown.render(visits=visits, from_ms=from_ms, to_ms=to_ms)
        else:
            output = self._json.render(visits=visits)
        print(output, end="")

    @staticmethod
    def _remove(*, path):
        try:
            os.unlink(path)
        except OSError:
            pass


class Kernel:
    """Composition root for the history-chrome command."""

    def __init__(self, *, argv=None, logger=None):
        self._argv = list(sys.argv if argv is None else argv)
        self._logger = logger

    def run(self):
        """Parse arguments and run the application, returning an exit code."""
        parser = CommandLine.build_parser()
        if "--completion" in self._argv:
            print(
                Completion.generate(
                    parser=parser,
                    name=Path(self._argv[0]).resolve().stem,
                )
            )
            return 0

        options = parser.parse_args(self._argv[1:])
        logger = self._logger if self._logger is not None else Logger(quiet=options.quiet)
        formatter = VisitFormatter()
        application = Application(
            options=options,
            resolver=DateRangeResolver(logger=logger),
            history=ChromeHistory(user_data=options.user_data),
            markdown=MarkdownRenderer(formatter=formatter),
            json_renderer=JsonRenderer(formatter=formatter),
            logger=logger,
        )
        return application.run()


if __name__ == "__main__":
    raise SystemExit(Kernel().run())
