#!/usr/bin/env python3
"""Read Google Chrome bookmarks and emit them as JSON, Markdown or Netscape HTML."""

import argparse
import json
import os
import platform
import re
import shlex
import sys
import unicodedata
from abc import ABC
from abc import abstractmethod
from datetime import datetime
from pathlib import Path

#--------------------------------------------------
# Logging: runtime warnings and errors
#--------------------------------------------------


class Logger(ABC):
    """Report runtime warnings and errors."""

    @abstractmethod
    def warning(self, message):
        """Report a warning."""

    @abstractmethod
    def error(self, message):
        """Report an error."""


class StderrLogger(Logger):
    """Write prefixed runtime messages to stderr, honoring quiet mode."""

    ERROR_PREFIX = "ERROR"
    WARNING_PREFIX = "WARNING"

    def __init__(self, *, quiet=False):
        self._quiet = quiet

    def warning(self, message):
        """Print a warning unless quiet mode is enabled."""
        if not self._quiet:
            self._emit(prefix=self.WARNING_PREFIX, message=message)

    def error(self, message):
        """Print an error regardless of quiet mode."""
        self._emit(prefix=self.ERROR_PREFIX, message=message)

    @staticmethod
    def _emit(*, prefix, message):
        """Write a prefixed message to stderr."""
        print(f"{prefix}: {message}", file=sys.stderr)


class NullLogger(Logger):
    """No-op logger for collaborators that do not need to report anything."""

    def warning(self, message):
        """Discard a warning."""

    def error(self, message):
        """Discard an error."""


class UsageError(Exception):
    """Raised when a command-line value is invalid."""


#--------------------------------------------------
# Date range resolution
#--------------------------------------------------


class DateRangeResolver:
    """Resolve human-readable start and end values to Unix epoch milliseconds."""

    DATE_FORMATS = (
        ("%Y-%m-%d %H:%M:%S", True),
        ("%Y-%m-%d", False),
    )

    def parse(self, *, value):
        """Return ``(datetime, had_explicit_time)`` for a human date string."""
        for date_format, had_time in self.DATE_FORMATS:
            try:
                return datetime.strptime(value, date_format), had_time
            except ValueError:
                continue
        raise ValueError(
            f"invalid date '{value}', expected 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS'"
        )

    def resolve(self, *, start=None, end=None):
        """Return ``(start_ms, end_ms)`` for the requested add-date range.

        A missing start means no lower bound; a missing end means now.
        Date-only values snap to the start or the end of the day. Invalid
        values raise :class:`UsageError` so the CLI can exit with code 2.
        """
        try:
            start_ms = self._start_ms(value=start)
            end_ms = self._end_ms(value=end)
        except ValueError as error:
            raise UsageError(str(error)) from error
        if end_ms < start_ms:
            raise UsageError("end cannot be set before start")
        return start_ms, end_ms

    def _start_ms(self, *, value):
        """Return the inclusive lower bound in epoch milliseconds."""
        if value is None:
            return 0
        moment, had_time = self.parse(value=value)
        if not had_time:
            moment = moment.replace(hour=0, minute=0, second=0, microsecond=0)
        return int(moment.timestamp() * 1000)

    def _end_ms(self, *, value):
        """Return the exclusive upper bound in epoch milliseconds."""
        if value is None:
            return int(datetime.now().timestamp() * 1000)
        moment, had_time = self.parse(value=value)
        if not had_time:
            moment = moment.replace(hour=23, minute=59, second=59, microsecond=0)
        return int(moment.timestamp() * 1000)


#--------------------------------------------------
# Chrome profiles: locate Bookmarks files
#--------------------------------------------------


class ChromeProfileLocator:
    """Locate the Chrome profile ``Bookmarks`` files to read."""

    BOOKMARKS_FILENAME = "Bookmarks"
    DEFAULT_PROFILE = "Default"
    EXPLICIT_PROFILE = "explicit"
    PROFILE_PATTERN = re.compile(r"^(Default|Profile \d+)$")

    def __init__(self, *, logger=None):
        self._logger = logger if logger is not None else NullLogger()

    @staticmethod
    def default_user_data_dir():
        """Return the platform default Chrome user data directory."""
        system = platform.system()
        if system == "Windows":
            appdata = os.environ.get("LOCALAPPDATA", "")
            return os.path.join(appdata, "Google", "Chrome", "User Data") if appdata else ""
        if system == "Darwin":
            return os.path.expanduser("~/Library/Application Support/Google/Chrome")
        return os.path.expanduser("~/.config/google-chrome")

    def discover(self, *, user_data):
        """Return profile directory names containing a Bookmarks file."""
        directory = Path(user_data)
        if not directory.is_dir():
            return []
        return [
            child.name
            for child in sorted(directory.iterdir())
            if child.is_dir()
            and self.PROFILE_PATTERN.match(child.name)
            and (child / self.BOOKMARKS_FILENAME).is_file()
        ]

    def resolve(self, *, db, profile, user_data):
        """Return ``(profile_name, Bookmarks_path)`` pairs to read."""
        if db:
            return [(self.EXPLICIT_PROFILE, db)]
        names = (
            [profile]
            if profile
            else (self.discover(user_data=user_data) or [self.DEFAULT_PROFILE])
        )
        profiles = []
        for name in names:
            path = Path(user_data) / name / self.BOOKMARKS_FILENAME
            if path.is_file():
                profiles.append((name, str(path)))
            else:
                self._logger.warning(f"{path} not found, skipping")
        return profiles


#--------------------------------------------------
# Chrome bookmarks: load, flatten, filter and sort
#--------------------------------------------------


class ChromeBookmarks:
    """Read and normalize entries from a Chrome Bookmarks document."""

    CHROME_EPOCH_OFFSET_US = 11644473600000000
    ENCODING = "utf-8"
    ROOT_KEYS = ("bookmark_bar", "other", "synced")
    ROOT_NAMES = {
        "bookmark_bar": "Bookmarks bar",
        "other": "Other bookmarks",
        "synced": "Mobile bookmarks",
    }

    @classmethod
    def chrome_us_to_ms(cls, us):
        """Convert Chrome epoch microseconds to Unix epoch milliseconds."""
        try:
            return (int(us) - cls.CHROME_EPOCH_OFFSET_US) // 1000
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def strip_trailing_slash(url):
        """Remove trailing slashes from a URL, keeping a bare scheme intact."""
        stripped = url.rstrip("/")
        if stripped.endswith(":"):
            return url
        return stripped

    def load(self, *, path):
        """Load a Chrome Bookmarks JSON file and return the parsed document."""
        with open(path, encoding=self.ENCODING) as handle:
            return json.load(handle)

    def flatten(self, *, document):
        """Flatten a Chrome Bookmarks document into a list of URL entries.

        Each entry carries the ancestor folder chain as tags, so folder nodes
        are not emitted as entries themselves.
        """
        entries = []
        roots = document.get("roots", {})
        for root_key in self.ROOT_KEYS:
            root = roots.get(root_key)
            if not isinstance(root, dict):
                continue
            entries.extend(
                self._walk_node(
                    node=root,
                    tags=[self.ROOT_NAMES.get(root_key, root_key)],
                    modified_us=None,
                )
            )
        return entries

    def filter(self, *, entries, start_ms, end_ms):
        """Keep entries whose add date falls in ``[start_ms, end_ms)``."""
        return [entry for entry in entries if start_ms <= entry["_ts_ms"] < end_ms]

    @staticmethod
    def sort(*, entries):
        """Return entries sorted by add date and then URL."""
        return sorted(entries, key=lambda entry: (entry["_ts_ms"], entry["url"]))

    def _walk_node(self, *, node, tags, modified_us):
        """Return entries produced by a bookmark tree node."""
        if node.get("type") == "url":
            return [self._entry(node=node, tags=tags, modified_us=modified_us)]
        folder_us = int(node.get("date_modified", 0) or 0) or None
        entries = []
        for child in node.get("children", []) or []:
            child_tags = tags + [child["name"]] if child.get("type") == "folder" else tags
            entries.extend(
                self._walk_node(node=child, tags=child_tags, modified_us=folder_us)
            )
        return entries

    def _entry(self, *, node, tags, modified_us):
        """Build the normalized entry for a URL node."""
        node_us = int(node.get("date_added", 0) or 0)
        mod_us = modified_us if modified_us else node_us
        node_ms = self.chrome_us_to_ms(node_us)
        parent_ms = self.chrome_us_to_ms(mod_us)
        return {
            "_ts_ms": node_ms,
            "url": self.strip_trailing_slash(node.get("url", "")),
            "name": node.get("name", ""),
            "date_created": self._local_iso(ms=node_ms),
            "date_modified": self._local_iso(ms=parent_ms),
            "tags": list(tags),
        }

    @staticmethod
    def _local_iso(*, ms):
        """Format Unix epoch milliseconds as local ISO time with seconds."""
        return datetime.fromtimestamp(ms / 1000).isoformat(timespec="seconds")


#--------------------------------------------------
# Bookmark reader: orchestrate locator, loader and range resolver
#--------------------------------------------------


class BookmarkReader:
    """Collect filtered bookmark entries from the selected profiles."""

    def __init__(self, *, locator, bookmarks, ranges):
        self._locator = locator
        self._bookmarks = bookmarks
        self._ranges = ranges

    def collect(self, *, db, profile, user_data, start=None, end=None):
        """Load, flatten, filter and sort bookmarks from every selected profile."""
        start_ms, end_ms = self._ranges.resolve(start=start, end=end)
        entries = []
        for _, path in self._locator.resolve(db=db, profile=profile, user_data=user_data):
            document = self._bookmarks.load(path=path)
            entries.extend(self._bookmarks.flatten(document=document))
        entries = self._bookmarks.filter(entries=entries, start_ms=start_ms, end_ms=end_ms)
        return self._bookmarks.sort(entries=entries)


#--------------------------------------------------
# Renderers: shared contracts and tag slugs
#--------------------------------------------------


class BookmarkRenderer(ABC):
    """Format normalized bookmark entries as text."""

    @abstractmethod
    def render(self, *, entries):
        """Return the rendered representation of the given entries."""


class TagSlug:
    """Create hashtag-friendly slugs from folder names."""

    @staticmethod
    def slugify(value):
        """Return a hashtag-friendly slug for a folder name."""
        value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
        value = re.sub(r"[^a-zA-Z0-9\s-]", "", value).strip().lower()
        return re.sub(r"[-\s]+", "-", value)

    @classmethod
    def from_tags(cls, *, tags):
        """Return the non-empty slugs for a sequence of tags."""
        return [slug for slug in (cls.slugify(tag) for tag in tags) if slug]


#--------------------------------------------------
# Renderers: Markdown
#--------------------------------------------------


class MarkdownRenderer(BookmarkRenderer):
    """Render bookmark entries as Markdown blocks using the repository template."""

    BOOKMARK_HASHTAG = "#bookmark"
    TITLE = "# chrome Bookmarks"
    TEMPLATE = """---
- created_at: {date_created}
- modified_at: {date_modified}
- tags:{tags_block}
---

## {name}

{hashtags}

- [{name}]({url})

"""

    def render(self, *, entries):
        """Render entries as a Markdown document."""
        lines = [self.TITLE, ""]
        for entry in entries:
            lines.append(self._block(entry=entry))
            lines.append("")
        return "\n".join(lines)

    def _block(self, *, entry):
        """Render one bookmark entry as a Markdown block."""
        slugs = TagSlug.from_tags(tags=entry["tags"])
        tags_block = "".join(f"\n  - {slug}" for slug in slugs)
        hashtags = " ".join([self.BOOKMARK_HASHTAG] + [f"#{slug}" for slug in slugs])
        return self.TEMPLATE.format(
            date_created=entry["date_created"],
            date_modified=entry["date_modified"],
            tags_block=tags_block,
            name=entry["name"],
            hashtags=hashtags,
            url=entry["url"],
        ).rstrip("\n")


#--------------------------------------------------
# Renderers: JSON
#--------------------------------------------------


class JsonRenderer(BookmarkRenderer):
    """Render bookmark entries as a JSON array."""

    INDENT = 2

    def render(self, *, entries):
        """Render entries as a JSON array."""
        payload = [self._entry(entry=entry) for entry in entries]
        return json.dumps(payload, ensure_ascii=False, indent=self.INDENT)

    def _entry(self, *, entry):
        """Convert a normalized entry to its public JSON object."""
        return {
            "name": entry["name"],
            "url": entry["url"],
            "date_created": entry["date_created"],
            "date_modified": entry["date_modified"],
            "tags": TagSlug.from_tags(tags=entry["tags"]),
        }


#--------------------------------------------------
# Renderers: Netscape bookmark file
#--------------------------------------------------


class NetscapeRenderer(BookmarkRenderer):
    """Render bookmark entries as a Netscape Bookmark file."""

    HEADER = (
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
        '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
        "<TITLE>Bookmarks</TITLE>",
        "<H1>Bookmarks</H1>",
    )
    INDENT = "    "
    ROOT_KEY = "$root"
    ROOT_NAME = "Bookmarks"

    def render(self, *, entries):
        """Render entries as a Netscape Bookmark file."""
        prepared = [self._entry(entry=entry) for entry in entries]
        folders, folder_children, entries_by_folder = self._group(entries=prepared)
        lines = list(self.HEADER)
        lines.extend(
            self._render_folder(
                folder_key=self.ROOT_KEY,
                depth=1,
                folders=folders,
                folder_children=folder_children,
                entries_by_folder=entries_by_folder,
            )
        )
        return "\n".join(lines) + "\n"

    @staticmethod
    def escape(value):
        """Escape a value for the Netscape bookmark file format."""
        return (
            value.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    @staticmethod
    def _entry(*, entry):
        """Return a copy of an entry with its epoch-seconds add date."""
        return dict(entry, add_date=str(entry["_ts_ms"] // 1000))

    def _group(self, *, entries):
        """Group entries and their ancestor folders into renderable maps."""
        folders = {self.ROOT_KEY: (self.ROOT_NAME, 0, 0)}
        folder_children = {self.ROOT_KEY: []}
        entries_by_folder = {}
        for entry in entries:
            path_keys = []
            key = self.ROOT_KEY
            for tag in entry["tags"]:
                child_key = f"{key}/{tag}"
                if child_key not in folders:
                    folders[child_key] = (tag, entry["add_date"], entry["add_date"])
                    folder_children.setdefault(key, []).append(child_key)
                key = child_key
                path_keys.append(key)
            folder_key = path_keys[-1] if path_keys else self.ROOT_KEY
            entries_by_folder.setdefault(folder_key, []).append(entry)
        for folder_key in entries_by_folder:
            parent_key = folder_key.rsplit("/", 1)[0]
            if folder_key not in folder_children.get(parent_key, []):
                folder_children.setdefault(parent_key, []).append(folder_key)
        return folders, folder_children, entries_by_folder

    def _render_folder(self, *, folder_key, depth, folders, folder_children, entries_by_folder):
        """Render one folder and its children recursively."""
        name, add_date, mod_date = folders[folder_key]
        indent = self.INDENT * depth
        lines = [
            f'{indent}<DT><H3 ADD_DATE="{add_date}" LAST_MODIFIED="{mod_date}">'
            f"{self.escape(name)}</H3>"
        ]
        lines.append(f"{indent}<DL><p>")
        for child_key in folder_children.get(folder_key, []):
            if child_key in folders:
                lines.extend(
                    self._render_folder(
                        folder_key=child_key,
                        depth=depth + 1,
                        folders=folders,
                        folder_children=folder_children,
                        entries_by_folder=entries_by_folder,
                    )
                )
            else:
                for entry in entries_by_folder[child_key]:
                    lines.append(self._link(entry=entry, depth=depth + 1))
        for entry in entries_by_folder.get(folder_key, []):
            lines.append(self._link(entry=entry, depth=depth + 1))
        lines.append(f"{indent}</DL><p>")
        return lines

    def _link(self, *, entry, depth):
        """Render one bookmark link at the given depth."""
        indent = self.INDENT * depth
        return (
            f'{indent}<DT><A HREF="{self.escape(entry["url"])}" '
            f'ADD_DATE="{entry["add_date"]}">{self.escape(entry["name"])}</A>'
        )


#--------------------------------------------------
# Renderer selection
#--------------------------------------------------


class RendererSelector:
    """Select the renderer requested by the command-line flags."""

    RENDERERS = (
        ("html", NetscapeRenderer),
        ("md", MarkdownRenderer),
    )
    DEFAULT_RENDERER = JsonRenderer

    @classmethod
    def select(cls, *, arguments):
        """Return the renderer selected by the parsed arguments."""
        for flag, renderer_class in cls.RENDERERS:
            if getattr(arguments, flag):
                return renderer_class()
        return cls.DEFAULT_RENDERER()


#--------------------------------------------------
# Completion: bash completion script generator
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
        """Return a bash completion script string for the given argparse parser."""
        all_opts, categories = cls._classify_parser_actions(parser)
        return cls._render_script(all_opts=all_opts, categories=categories, name=name)


#--------------------------------------------------
# CLI: application
#--------------------------------------------------


class Application:
    """Command-line application for reading Chrome bookmarks."""

    COMPLETION_FLAG = "--completion"
    DESCRIPTION = "Read Google Chrome bookmarks."

    def build_parser(self):
        """Build and return the argument parser."""
        parser = argparse.ArgumentParser(description=self.DESCRIPTION)
        parser.add_argument(
            "--user-data",
            default=ChromeProfileLocator.default_user_data_dir(),
            help=argparse.SUPPRESS,
        )
        parser.add_argument(
            "--profile", default="",
            help="profile name to read (default: scan Default + Profile 1..N)",
        )
        parser.add_argument(
            "--db", default="",
            help="explicit path to a Bookmarks JSON file (overrides --user-data/--profile)",
        )
        parser.add_argument(
            "--start", metavar="YYYY-MM-DD[ HH:MM:SS]",
            help="inclusive bookmark add-date start (local). Default: no lower bound.",
        )
        parser.add_argument(
            "--end", metavar="YYYY-MM-DD[ HH:MM:SS]",
            help="exclusive bookmark add-date end (local). Date-only -> end of day. Default: now.",
        )
        parser.add_argument("--json", action="store_true", help="print output as JSON (default)")
        parser.add_argument("--md", action="store_true", help="print output as markdown blocks")
        parser.add_argument(
            "--html", action="store_true",
            help="print output as Netscape bookmark file",
        )
        parser.add_argument("--verbose", "-v", action="count", default=0)
        parser.add_argument("--quiet", action="store_true",
                            help="suppress non-error output; runtime errors are still reported")
        parser.add_argument("--completion", action="store_true",
                            help="Print bash completion script to stdout and exit")
        return parser

    @staticmethod
    def script_name():
        """Return the invoked script name used by the completion function."""
        return Path(sys.argv[0]).resolve().stem

    def generate_completion(self, *, name=None):
        """Return the bash completion script for this command."""
        return Completion.generate(
            parser=self.build_parser(),
            name=self.script_name() if name is None else name,
        )

    def run(self, *, argv=None):
        """Run the CLI and return the process exit code."""
        arguments = list(sys.argv[1:] if argv is None else argv)
        parser = self.build_parser()
        if self.COMPLETION_FLAG in arguments:
            print(Completion.generate(parser=parser, name=self.script_name()))
            return 0

        args = parser.parse_args(arguments)
        logger = StderrLogger(quiet=args.quiet)
        reader = BookmarkReader(
            locator=ChromeProfileLocator(logger=logger),
            bookmarks=ChromeBookmarks(),
            ranges=DateRangeResolver(),
        )
        try:
            entries = reader.collect(
                db=args.db,
                profile=args.profile,
                user_data=args.user_data,
                start=args.start,
                end=args.end,
            )
            renderer = RendererSelector.select(arguments=args)
            output = renderer.render(entries=entries)
        except UsageError as error:
            logger.error(str(error))
            return 2
        except (FileNotFoundError, ValueError) as error:
            logger.error(str(error))
            return 1

        print(output, end="")
        return 0


if __name__ == "__main__":
    raise SystemExit(Application().run())
