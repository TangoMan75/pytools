#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Jira REST wrapper: authenticate with an Atlassian API token and fetch Jira
tickets with their comments as markdown, calling the Jira Cloud REST API
directly (no external CLI required).
"""

import argparse
import base64
import datetime
import getpass
import json
import os
import re
import shlex
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

#--------------------------------------------------
# Console: Semantic console output
#--------------------------------------------------


class Console:
    """Console output with semantic coloring and alert blocks."""

    ALERT_PRIMARY = "\033[1;104;97m"
    ALERT_SECONDARY = "\033[1;45;97m"
    ALERT_SUCCESS = "\033[1;42;97m"
    ALERT_DANGER = "\033[1;41;97m"
    ALERT_WARNING = "\033[1;43;97m"
    ALERT_INFO = "\033[1;44;97m"
    ALERT_LIGHT = "\033[1;47;90m"
    ALERT_DARK = "\033[1;40;37m"

    PRIMARY = "\033[97m"
    SECONDARY = "\033[94m"
    SUCCESS = "\033[32m"
    DANGER = "\033[31m"
    WARNING = "\033[33m"
    INFO = "\033[95m"
    LIGHT = "\033[47;90m"
    DARK = "\033[40;37m"
    DEFAULT = "\033[0m"
    EOL = "\033[0m\n"

    @staticmethod
    def _pad_and_indent(text, *, indent=0, padding=0):
        """Return (indentation, text, padding)"""
        pad = max(0, padding - len(text))
        return " " * indent, text, " " * pad

    @staticmethod
    def _alert_block(color, *, text):
        text = " ".join(str(text).splitlines())[:63]
        top = f"{Console.EOL}{color}{'':>64}{Console.EOL}"
        middle = f"{color} {text:<63}{Console.EOL}"
        bottom = f"{color}{'':>64}{Console.EOL}\n"
        print(top + middle + bottom, end='')

    @staticmethod
    def alert_primary(text):
        """Print primary alert block."""
        Console._alert_block(Console.ALERT_PRIMARY, text=text)

    @staticmethod
    def alert_secondary(text):
        """Print secondary alert block."""
        Console._alert_block(Console.ALERT_SECONDARY, text=text)

    @staticmethod
    def alert_success(text):
        """Print success alert block."""
        Console._alert_block(Console.ALERT_SUCCESS, text=text)

    @staticmethod
    def alert_danger(text):
        """Print danger alert block."""
        Console._alert_block(Console.ALERT_DANGER, text=text)

    @staticmethod
    def alert_warning(text):
        """Print warning alert block."""
        Console._alert_block(Console.ALERT_WARNING, text=text)

    @staticmethod
    def alert_info(text):
        """Print info alert block."""
        Console._alert_block(Console.ALERT_INFO, text=text)

    @staticmethod
    def alert_light(text):
        """Print light alert block."""
        Console._alert_block(Console.ALERT_LIGHT, text=text)

    @staticmethod
    def alert_dark(text):
        """Print dark alert block."""
        Console._alert_block(Console.ALERT_DARK, text=text)

    @staticmethod
    def primary(text, *, indent=0, padding=0):
        """Print text in primary color."""
        i, t, p = Console._pad_and_indent(text, indent=indent, padding=padding)
        print(f"{i}{Console.PRIMARY}{t}{Console.DEFAULT}{p}", end='')

    @staticmethod
    def secondary(text, *, indent=0, padding=0):
        """Print text in secondary color."""
        i, t, p = Console._pad_and_indent(text, indent=indent, padding=padding)
        print(f"{i}{Console.SECONDARY}{t}{Console.DEFAULT}{p}", end='')

    @staticmethod
    def success(text, *, indent=0, padding=0):
        """Print text in success color."""
        i, t, p = Console._pad_and_indent(text, indent=indent, padding=padding)
        print(f"{i}{Console.SUCCESS}{t}{Console.DEFAULT}{p}", end='')

    @staticmethod
    def danger(text, *, indent=0, padding=0):
        """Print text in danger color."""
        i, t, p = Console._pad_and_indent(text, indent=indent, padding=padding)
        print(f"{i}{Console.DANGER}{t}{Console.DEFAULT}{p}", end='')

    @staticmethod
    def warning(text, *, indent=0, padding=0):
        """Print text in warning color."""
        i, t, p = Console._pad_and_indent(text, indent=indent, padding=padding)
        print(f"{i}{Console.WARNING}{t}{Console.DEFAULT}{p}", end='')

    @staticmethod
    def info(text, *, indent=0, padding=0):
        """Print text in info color."""
        i, t, p = Console._pad_and_indent(text, indent=indent, padding=padding)
        print(f"{i}{Console.INFO}{t}{Console.DEFAULT}{p}", end='')

    @staticmethod
    def light(text, *, indent=0, padding=0):
        """Print text in light color."""
        i, t, p = Console._pad_and_indent(text, indent=indent, padding=padding)
        print(f"{i}{Console.LIGHT}{t}{Console.DEFAULT}{p}", end='')

    @staticmethod
    def dark(text, *, indent=0, padding=0):
        """Print text in dark color."""
        i, t, p = Console._pad_and_indent(text, indent=indent, padding=padding)
        print(f"{i}{Console.DARK}{t}{Console.DEFAULT}{p}", end='')

    @staticmethod
    def error(message):
        """Print error message to stderr."""
        print(f"{Console.DANGER}error: {message}{Console.DEFAULT}", file=sys.stderr)


#--------------------------------------------------
# Logger: file logging and output
#--------------------------------------------------


class Logger:
    """Log messages to file and console based on verbosity"""

    def __init__(self, *, verbose=0, script_file=None):
        self.verbose = verbose
        self.script_file = script_file or Path(sys.argv[0]).resolve()
        self.script_dir = self.script_file.parent
        self.name = self.script_file.stem
        self.log_dir = self.script_dir / 'log'
        self.log_file = self.log_dir / f"{datetime.date.today().isoformat()}_{self.name}.log"

    def print(self):
        """Print the log file contents to stdout and return whether it exists."""
        if self.log_file.exists():
            if self.verbose > 0:
                Console.info(f"{self.log_file}\n")
            print(self.log_file.read_text(encoding='utf-8'), end='')
            return True
        Console.error(f"\"{self.log_file}\" file not found.")
        return False

    def log(self, message, *, loglevel=0):
        """Log message to file and console with appropriate coloring."""
        self.log_dir.mkdir(parents=True, exist_ok=True)
        level = 'ERROR' if loglevel == 0 else 'SUCCESS' if loglevel == 1 else 'WARNING' if loglevel == 2 else 'INFO'
        timestamp = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f')
        line = f"{timestamp} {level} {message}"
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        if self.verbose >= loglevel:
            if loglevel == 0:
                Console.danger(f"{message}\n")
            elif loglevel == 1:
                Console.success(f"{message}\n")
            elif loglevel == 2:
                Console.warning(f"{message}\n")
            else:
                Console.info(f"{message}\n")

    def info(self, message):
        """Log info message."""
        self.log(message, loglevel=3)

    def warning(self, message):
        """Log warning message."""
        self.log(message, loglevel=2)

    def success(self, message):
        """Log success message."""
        self.log(message, loglevel=1)

    def danger(self, message):
        """Log danger/error message."""
        self.log(message, loglevel=0)


class NullLogger:
    """No-op logger used when logging is not needed."""

    def __init__(self, *, verbose=0):
        self.verbose = verbose

    def print(self):
        """Do nothing."""

    def log(self, message, *, loglevel=0):
        """Do nothing."""

    def info(self, message):
        """Do nothing."""

    def warning(self, message):
        """Do nothing."""

    def success(self, message):
        """Do nothing."""

    def danger(self, message):
        """Do nothing."""


#--------------------------------------------------
# Completion: bash completion script generator
#--------------------------------------------------


class Completion:
    """Build bash completion scripts from an argparse parser."""

    FILE_OPTION_KEYS = ("output", "file", "path", "dest")
    GLOB_OPTION_KEYS = ("include", "exclude", "glob", "pattern")
    VERBOSE_WORDS = "-v -vv -vvv"

    @staticmethod
    def _classify_actions(parser):
        """Return sorted, de-duplicated option lists keyed by completion kind."""
        groups = {
            "long": [],
            "short": [],
            "boolean": [],
            "verbose": [],
            "file": [],
            "glob": [],
        }
        for action in parser._actions:  # noqa: SLF001
            opts = action.option_strings
            if not opts:
                continue
            is_boolean = action.nargs == 0 and action.const is True
            is_count = action.__class__.__name__ == "_CountAction"
            joined = " ".join(opts).lower()
            for opt in opts:
                if opt.startswith("--"):
                    groups["long"].append(opt)
                elif opt.startswith("-"):
                    groups["short"].append(opt)
            if is_boolean:
                groups["boolean"].extend(opts)
            if is_count:
                groups["verbose"].extend(opts)
            if any(key in joined for key in Completion.FILE_OPTION_KEYS):
                groups["file"].extend(opts)
            if any(key in joined for key in Completion.GLOB_OPTION_KEYS):
                groups["glob"].extend(opts)
        return {kind: sorted(set(options)) for kind, options in groups.items()}

    @classmethod
    def _render_cases(cls, *, groups):
        """Return the bash case branches for every classified option."""
        case_lines = []
        for opt in groups["boolean"]:
            case_lines.append(
                f"        {opt})\n            COMPREPLY=()\n            return 0\n            ;;\n"
            )
        for opt in groups["file"]:
            case_lines.append(
                f"        {opt})\n            COMPREPLY=( $(compgen -f -- \"${{cur}}\") )\n            return 0\n            ;;\n"
            )
        for opt in groups["glob"]:
            case_lines.append(
                f"        {opt})\n            COMPREPLY=( $(compgen -G \"${{cur}}*\") )\n            return 0\n            ;;\n"
            )
        for opt in groups["verbose"]:
            case_lines.append(
                f"        {opt})\n            COMPREPLY=( $(compgen -W \"{cls.VERBOSE_WORDS}\" -- \"${{cur}}\") )\n            return 0\n            ;;\n"
            )
        return "".join(case_lines)

    @classmethod
    def generate(cls, *, parser, name):
        """Return a bash completion script string for the given argparse parser."""
        groups = cls._classify_actions(parser)
        option_case = cls._render_cases(groups=groups)
        completion_name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
        long_opts = groups["long"]
        short_opts = groups["short"]
        return f'''#!/bin/bash

_{completion_name}_completions()
{{
    local cur prev opts
    COMPREPLY=()
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"

    opts="{" ".join(long_opts)} {" ".join(short_opts)}"

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
# FileHandler: base class for file processing
#--------------------------------------------------


class FileHandler:
    """Base class to extend with your own processing logic."""

    def __init__(self, *, logger=None):
        self.logger = logger if logger is not None else NullLogger()
        self.files_processed = 0
        self.files_skipped = 0

    @staticmethod
    def walk_paths(input_path, *, recursive=False, include=None, exclude=None):
        """Yield file paths from input, optionally filtered and recursively."""
        path = Path(input_path)

        if not path.exists():
            raise FileNotFoundError(f"input path not found: {path}")

        if path.is_file():
            if (not include or path.match(include)) and (not exclude or not path.match(exclude)):
                yield path
            return

        iterator = path.rglob("*") if recursive else path.glob("*")

        for item in sorted(iterator):
            if not item.is_file():
                continue
            if include and not item.match(include):
                continue
            if exclude and item.match(exclude):
                continue
            yield item

    @staticmethod
    def get_unique_filename(path, *, base_filename):
        """Generate a unique filename if one already exists."""
        directory = path if path.is_dir() else path.parent
        base_path = Path(base_filename)
        filepath = directory / base_path.name
        counter = 1
        while filepath.exists():
            filepath = directory / f"{base_path.stem}_{counter}{base_path.suffix}"
            counter += 1
        return filepath

    def process_file(self, path, *, output=None, dry_run=False):
        """Process a single file."""
        self.files_skipped += 1


#--------------------------------------------------
# Configuration: load credentials from .env and environment
#--------------------------------------------------


class JiraConfig:
    """Own the Jira credentials file and its environment overrides."""

    CONFIG_DIR = Path.home() / ".config" / "TangoMan75" / "jira"
    ENV_FILENAME = ".env"
    FILE_MODE = 0o600
    DEFAULT_ENCODING = "utf-8"

    def __init__(self, *, path=None, environ=None):
        self.path = path if path is not None else JiraConfig.default_path()
        self._environ = environ if environ is not None else os.environ

    @classmethod
    def default_path(cls):
        """Return the default credentials file path."""
        return cls.CONFIG_DIR / cls.ENV_FILENAME

    def load(self):
        """Parse a simple KEY=VALUE .env file into a dict (no external deps)."""
        values = {}
        if not self.path.exists():
            return values
        for raw in self.path.read_text(encoding=JiraConfig.DEFAULT_ENCODING).splitlines():
            line = raw.strip()
            if not line or line.startswith('#') or line.startswith(';'):
                continue
            if '=' not in line:
                continue
            key, _, value = line.partition('=')
            key = key.strip()
            if key.startswith("export "):
                key = key[len("export "):]
            value = value.strip()
            if len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
                value = value[1:-1]
            elif value.startswith("#"):
                value = ""
            elif " #" in value:
                value = value.split(" #", 1)[0].strip()
            if key:
                values[key] = value
        return values

    def save(self, *, site, email, token):
        """Write Jira credentials as a KEY=VALUE .env file with owner-only access."""
        content = "\n".join([
            f"ATLASSIAN_SITE={site}",
            f"ATLASSIAN_EMAIL={email}",
            f"ATLASSIAN_API_TOKEN={token}",
        ]) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(content, encoding=JiraConfig.DEFAULT_ENCODING)
        os.chmod(self.path, JiraConfig.FILE_MODE)

    def resolve(self):
        """Resolve Jira credentials from the default .env then the environment."""
        dotenv = self.load()

        site = self._environ.get("ATLASSIAN_SITE") or dotenv.get("ATLASSIAN_SITE", "")
        email = self._environ.get("ATLASSIAN_EMAIL") or dotenv.get("ATLASSIAN_EMAIL", "")
        token = self._environ.get("ATLASSIAN_API_TOKEN") or dotenv.get("ATLASSIAN_API_TOKEN", "")
        bearer = self._environ.get("ATLASSIAN_TOKEN") or dotenv.get("ATLASSIAN_TOKEN", "")
        if not token and bearer:
            token = bearer
            email = ""
        return {"site": site, "email": email, "token": token}


#--------------------------------------------------
# Jira REST client
#--------------------------------------------------


class JiraClient:
    """Minimal Jira Cloud REST API client using only the standard library."""

    DEFAULT_TIMEOUT = 30
    PAGE_SIZE = 100

    def __init__(self, *, site, email, token, timeout=DEFAULT_TIMEOUT):
        if not site:
            raise ValueError("missing Atlassian site (set ATLASSIAN_SITE)")
        if not token:
            raise ValueError("missing Atlassian API token (set ATLASSIAN_API_TOKEN)")
        if site.startswith("http://"):
            raise ValueError("refusing to send credentials over plain HTTP; use an https:// site")
        if site.startswith("https://"):
            self._base = site.rstrip('/')
        else:
            self._base = f"https://{site.rstrip('/')}"
        self._email = email
        self._token = token
        self._timeout = timeout

    @staticmethod
    def _issue_path(key):
        """Return the relative API path for an issue."""
        return f"/rest/api/3/issue/{urllib.parse.quote(key)}"

    @staticmethod
    def _comment_path(key):
        """Return the relative API path for an issue's comments."""
        return f"{JiraClient._issue_path(key=key)}/comment"

    def _headers(self):
        """Return the authentication and content negotiation headers."""
        if self._email:
            raw = f"{self._email}:{self._token}".encode('utf-8')
            encoded = base64.b64encode(raw).decode('ascii')
            auth = f"Basic {encoded}"
        else:
            auth = f"Bearer {self._token}"
        return {
            "Authorization": auth,
            "Accept": "application/json",
        }

    def _request(self, *, request, error_path):
        """Send a prepared request and decode the JSON response."""
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as error:
            detail = error.read().decode('utf-8', 'replace')
            raise RuntimeError(f"Jira API {error.code} for {error_path}: {detail[:300]}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"network error contacting {self._base}: {error.reason}") from error

    def _get(self, *, path):
        """Send a GET request for a relative API path."""
        request = urllib.request.Request(f"{self._base}{path}", headers=self._headers())
        return self._request(request=request, error_path=path)

    def get_issue(self, *, key):
        """Return the raw issue payload for a key."""
        return self._get(path=self._issue_path(key=key))

    def get_comments(self, *, key):
        """Return the comment container ({comments: [...], total: N}) for a key."""
        all_comments = []
        start_at = 0
        while True:
            path = f"{self._comment_path(key=key)}?startAt={start_at}&maxResults={JiraClient.PAGE_SIZE}"
            payload = self._get(path=path)
            batch = payload.get("comments", [])
            all_comments.extend(batch)
            total = payload.get("total", len(all_comments))
            if not batch or start_at + len(batch) >= total:
                break
            start_at += len(batch)
        return {"comments": all_comments, "total": len(all_comments)}

    def issue_url(self, *, key):
        """Return the human-readable issue URL."""
        return f"{self._base}/browse/{key}"

    def issue_api_url(self, *, key):
        """Return the absolute issue API URL."""
        return f"{self._base}{self._issue_path(key=key)}"

    def comments_api_url(self, *, key, start_at=0, max_results=None):
        """Return the absolute paginated comments API URL."""
        if max_results is None:
            max_results = JiraClient.PAGE_SIZE
        return f"{self._base}{self._comment_path(key=key)}?startAt={start_at}&maxResults={max_results}"

    def comment_api_url(self, *, key):
        """Return the absolute comment API URL."""
        return f"{self._base}{self._comment_path(key=key)}"

    def add_comment(self, *, key, body):
        """Post a comment (plain text) to a ticket, returning the created comment."""
        adf = {
            "type": "doc",
            "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": body}]}],
        }
        payload = json.dumps({"body": adf}).encode('utf-8')
        headers = dict(self._headers())
        headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.comment_api_url(key=key),
            data=payload,
            method="POST",
            headers=headers,
        )
        return self._request(request=request, error_path=f"{key}/comment")


#--------------------------------------------------
# ADF: convert Atlassian Document Format to markdown
#--------------------------------------------------


class AdfConverter:
    """Recursively convert Atlassian Document Format nodes to markdown."""

    MAX_HEADING_LEVEL = 6

    @classmethod
    def convert(cls, *, node):
        """Convert an ADF node (dict, list, string, or scalar) to markdown."""
        if node is None:
            return ""
        if isinstance(node, str):
            return node
        if isinstance(node, list):
            return "\n".join(cls.convert(node=item) for item in node)
        if not isinstance(node, dict):
            return str(node)

        node_type = node.get("type")
        content = node.get("content") or []
        inner = cls.convert(node=content)

        if node_type == "doc":
            return inner
        if node_type == "paragraph":
            return inner
        if node_type == "heading":
            level = int(node.get("attrs", {}).get("level", 1))
            level = max(1, min(cls.MAX_HEADING_LEVEL, level))
            return "#" * level + " " + inner
        if node_type == "bulletList":
            return cls._convert_list(node=node, ordered=False)
        if node_type == "orderedList":
            return cls._convert_list(node=node, ordered=True)
        if node_type == "codeBlock":
            language = node.get("attrs", {}).get("language", "")
            return f"```{language}\n{inner}\n```"
        if node_type == "blockquote":
            return "\n".join("> " + line for line in inner.split("\n"))
        if node_type == "rule":
            return "---"
        if node_type == "text":
            return cls._convert_text(node=node)
        return inner

    @classmethod
    def _convert_list(cls, *, node, ordered):
        """Convert a bullet or ordered list node to markdown lines."""
        items = []
        for index, item in enumerate(node.get("content") or [], 1):
            if not isinstance(item, dict) or item.get("type") != "listItem":
                continue
            rendered = cls.convert(node=item.get("content", []))
            prefix = f"{index}. " if ordered else "- "
            items.append(prefix + rendered.replace("\n", " "))
        return "\n".join(items)

    @classmethod
    def _convert_text(cls, *, node):
        """Convert a text node and apply its formatting marks."""
        text = node.get("text", "")
        for mark in node.get("marks", []) or []:
            mark_type = mark.get("type")
            if mark_type == "strong":
                text = f"**{text}**"
            elif mark_type == "em":
                text = f"*{text}*"
            elif mark_type == "code":
                text = f"`{text}`"
            elif mark_type == "strike":
                text = f"~~{text}~~"
            elif mark_type == "link":
                href = mark.get("attrs", {}).get("href", "")
                text = f"[{text}]({href})"
        return text

    @classmethod
    def body_to_markdown(cls, *, value):
        """Convert an issue/comment body (ADF, string, or unknown) to markdown."""
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            return cls.convert(node=value)
        return str(value)


#--------------------------------------------------
# Response unwrapping: issue and comment envelopes
#--------------------------------------------------


class ResponseUnwrapper:
    """Extract issue and comment payloads from common response shapes."""

    @staticmethod
    def unwrap_issue(payload):
        """Return the issue payload whether wrapped in an envelope or bare."""
        if isinstance(payload, dict):
            if "fields" in payload or "key" in payload:
                return payload
            if "data" in payload and isinstance(payload["data"], dict):
                return payload["data"]
            if "issues" in payload and isinstance(payload["issues"], list) and payload["issues"]:
                return payload["issues"][0]
        return payload

    @classmethod
    def unwrap_comments(cls, payload):
        """Return a list of comment objects from various response shapes."""
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("comments", "data", "values", "records"):
                value = payload.get(key)
                if isinstance(value, list):
                    return value
            data = payload.get("data")
            if isinstance(data, dict):
                return cls.unwrap_comments(data)
        return []


#--------------------------------------------------
# Markdown rendering: issues and comments
#--------------------------------------------------


class MarkdownRenderer:
    """Render Jira issues and comments as markdown documents."""

    DATE_FORMAT = "%Y-%m-%d %H:%M"
    DATE_OFFSET_PATTERN = r"^(.*[+-]\d{2})(\d{2})$"
    UNKNOWN_SUMMARY = "(no summary)"
    UNKNOWN_AUTHOR = "Unknown"
    UNASSIGNED = "Unassigned"
    NO_DESCRIPTION = "_No description._"
    NO_COMMENTS = "_No comments._"
    EMPTY_COMMENT = "_Empty comment._"
    TABLE_HEADINGS = ("| Field | Value |", "|-------|-------|")

    def __init__(self, *, converter=None, unwrapper=None):
        self._converter = converter if converter is not None else AdfConverter()
        self._unwrapper = unwrapper if unwrapper is not None else ResponseUnwrapper()

    @staticmethod
    def _dig(obj, *path):
        """Safely traverse nested dicts, returning None on any missing key."""
        current = obj
        for part in path:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        return current

    @staticmethod
    def _escape(value):
        """Escape a value so it is safe inside a markdown table cell."""
        return str(value).replace("|", "\\|").replace("\n", " ").strip()

    @classmethod
    def format_date(cls, value):
        """Render a Jira ISO timestamp as a compact human-readable string."""
        if not value:
            return ""
        text = str(value).strip()
        if text[-1:] in ("Z", "z"):
            text = text[:-1] + "+00:00"
        match = re.match(cls.DATE_OFFSET_PATTERN, text)
        if match:
            text = match.group(1) + ":" + match.group(2)
        try:
            parsed = datetime.datetime.fromisoformat(text)
        except ValueError:
            return str(value)
        try:
            return parsed.astimezone(datetime.timezone.utc).strftime(cls.DATE_FORMAT)
        except Exception:
            return parsed.strftime(cls.DATE_FORMAT)

    def _field_rows(self, *, fields):
        """Return the label/value rows for the issue metadata table."""
        rows = [
            ("Status", self._dig(fields, "status", "name")),
            ("Type", self._dig(fields, "issuetype", "name")),
            ("Priority", self._dig(fields, "priority", "name")),
            ("Assignee", self._dig(fields, "assignee", "displayName") or MarkdownRenderer.UNASSIGNED),
            ("Reporter", self._dig(fields, "reporter", "displayName") or MarkdownRenderer.UNKNOWN_AUTHOR),
            ("Created", self.format_date(fields.get("created"))),
            ("Updated", self.format_date(fields.get("updated"))),
        ]
        labels = fields.get("labels") or []
        if labels:
            rows.append(("Labels", ", ".join(labels)))
        components = [
            component.get("name")
            for component in (fields.get("components") or [])
            if component.get("name")
        ]
        if components:
            rows.append(("Components", ", ".join(components)))
        return rows

    @classmethod
    def _render_table(cls, *, rows):
        """Return markdown table lines for the given label/value rows."""
        lines = list(cls.TABLE_HEADINGS)
        for label, value in rows:
            escaped = cls._escape(value) if value is not None else ""
            lines.append(f"| {label} | {escaped} |")
        return lines

    def render_issue(self, *, issue, url=""):
        """Render a Jira issue dict as a markdown document."""
        payload = self._unwrapper.unwrap_issue(issue)
        key = self._dig(payload, "key") or "?"
        fields = payload.get("fields", {}) or {}
        summary = fields.get("summary") or MarkdownRenderer.UNKNOWN_SUMMARY

        lines = [f"# {key}: {summary}", ""]
        if url:
            lines.append(f"<{url}>")
            lines.append("")

        lines.extend(self._render_table(rows=self._field_rows(fields=fields)))
        lines.append("")

        lines.append("## Description")
        description = self._converter.body_to_markdown(value=fields.get("description"))
        lines.append(description if description.strip() else MarkdownRenderer.NO_DESCRIPTION)
        lines.append("")
        return "\n".join(lines)

    def render_comments(self, *, comments):
        """Render a list of Jira comment dicts as a markdown section."""
        payload = self._unwrapper.unwrap_comments(comments)
        lines = ["## Comments", ""]
        if not payload:
            lines.append(MarkdownRenderer.NO_COMMENTS)
            lines.append("")
            return "\n".join(lines)

        for comment in payload:
            author = (
                self._dig(comment, "author", "displayName")
                or self._dig(comment, "updateAuthor", "displayName")
                or MarkdownRenderer.UNKNOWN_AUTHOR
            )
            created = self.format_date(comment.get("created") or comment.get("updated"))
            comment_id = comment.get("id", "")
            body = self._converter.body_to_markdown(value=comment.get("body"))

            lines.append(f"### {MarkdownRenderer._escape(author)} · {created}")
            if comment_id:
                lines.append(f"<sub>comment {MarkdownRenderer._escape(comment_id)}</sub>")
            lines.append("")
            lines.append(body if body.strip() else MarkdownRenderer.EMPTY_COMMENT)
            lines.append("")
        return "\n".join(lines)


#--------------------------------------------------
# Ticket markdown: fetch and render a ticket
#--------------------------------------------------


class TicketMarkdown:
    """Fetch a ticket with its comments and render it as one markdown document."""

    def __init__(self, *, client, renderer=None):
        self._client = client
        self._renderer = renderer if renderer is not None else MarkdownRenderer()

    def render(self, *, key):
        """Return the issue and comment sections joined as markdown."""
        issue = self._client.get_issue(key=key)
        comments = self._client.get_comments(key=key)
        document = self._renderer.render_issue(issue=issue, url=self._client.issue_url(key=key))
        return document + "\n" + self._renderer.render_comments(comments=comments)


#--------------------------------------------------
# Kernel
#--------------------------------------------------


class Kernel:
    """CLI application with metadata and execution."""

    EXIT_RUNTIME_ERROR = 1

    def __init__(self, *, author, title, description, config=None):
        self._author = author
        self._title = title
        self._description = description
        self._config = config if config is not None else JiraConfig()
        self._script_file = Path(sys.argv[0]).resolve()
        self._name = self._script_file.stem
        self._logger = None
        self._args = None

    def build_early_parser(self):
        """Build parser for early arguments (before required input)."""
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument('--log', action='store_true')
        parser.add_argument('--verbose', '-v', action='count', default=0)
        parser.add_argument('--quiet', action='store_true', help='Suppress non-error output; runtime errors are still reported')
        parser.add_argument('--completion', action='store_true', help='Print bash completion script to stdout and exit')
        return parser

    def build_parser(self):
        """Build and return argument parser with subcommands."""
        parser = argparse.ArgumentParser(description=self._description)
        parser.add_argument('--verbose', '-v', action='count', default=0, help='Increase verbosity (stackable)')
        parser.add_argument('--quiet', action='store_true', help='Suppress non-error output; runtime errors are still reported')
        parser.add_argument('--log', action='store_true', help='Output log file to terminal')
        parser.add_argument('--completion', action='store_true', help='Print bash completion script to stdout and exit')
        subparsers = parser.add_subparsers(dest='command', required=True)

        init_parser = subparsers.add_parser('init', help='Interactively create the .env credentials file')
        init_parser.add_argument('--force', action='store_true', help='Overwrite an existing .env without prompting')

        read_parser = subparsers.add_parser('read', help='Fetch a ticket and print it as markdown')
        read_parser.add_argument('key', help='Jira issue key (e.g. PROJ-123)')
        read_parser.add_argument('--output', help='Write markdown to this file instead of stdout')
        read_parser.add_argument('--dry-run', action='store_true', help='Print the API requests without calling Jira')

        update_parser = subparsers.add_parser('update', help='Update a ticket (add a comment)')
        update_parser.add_argument('key', help='Jira issue key (e.g. PROJ-123)')
        update_parser.add_argument('--comment', help='Comment body to add to the ticket')
        update_parser.add_argument('--file', help='Read the comment body from this file')
        update_parser.add_argument('--dry-run', action='store_true', help='Print the API request without calling Jira')

        return parser

    def hero(self):
        """Print hero to the terminal."""
        Console.alert_primary(self._title)

    def generate_completion(self):
        """Return the bash completion script for this script."""
        return Completion.generate(parser=self.build_parser(), name=self._name)

    def _handle_early_arguments(self):
        """Handle options that must run before the required input is parsed."""
        early_args, _ = self.build_early_parser().parse_known_args()
        self._logger = Logger(verbose=early_args.verbose, script_file=self._script_file)

        if early_args.verbose >= 1:
            self.hero()

        if early_args.completion:
            print(self.generate_completion())
            return True

        if early_args.log:
            self._logger.print()
            return True
        return False

    def _runtime_error(self, message):
        """Report a runtime error and exit 1 (never silenced by --quiet)."""
        Console.error(message)
        sys.exit(Kernel.EXIT_RUNTIME_ERROR)

    def run(self):
        """Run the Jira REST wrapper application."""
        if self._handle_early_arguments():
            return

        self._args = self.build_parser().parse_args()
        commands = {
            "init": self._cmd_init,
            "read": self._cmd_read,
            "update": self._cmd_update,
        }
        commands[self._args.command]()

    def _cmd_init(self):
        """Interactively create the default .env credentials file."""
        env_path = self._config.path
        if env_path.exists() and not self._args.force:
            answer = input(f"{env_path} already exists. Overwrite? [y/N] ").strip().lower()
            if answer != 'y':
                Console.info("Aborted; existing credentials left untouched.")
                return
        site = input("Atlassian site (e.g. shippeo.atlassian.net): ").strip()
        email = input("Atlassian email: ").strip()
        Console.info('To generate an API token:\n')
        Console.info('  1. Go to https://id.atlassian.com/manage-profile/security/api-tokens\n')
        Console.info('  2. Log in and validate 2FA\n')
        Console.info('  3. Click "Create API token"\n')
        Console.info('  4. Choose a name and expiration date then click "Create""\n')
        Console.info('  5. Click "Copy"\n')
        Console.info('  6. Paste token below\n')
        token = getpass.getpass("Api token:").strip()
        if not site or not token:
            self._runtime_error("site and token are required")
            return
        self._config.save(site=site, email=email, token=token)
        Console.success(f"Wrote credentials to {env_path}\n")

    def _build_client(self):
        """Build a Jira client from the resolved credentials."""
        credentials = self._config.resolve()
        return JiraClient(
            site=credentials["site"],
            email=credentials["email"],
            token=credentials["token"],
        )

    def _cmd_read(self):
        """Fetch a ticket and print it as markdown."""
        try:
            client = self._build_client()
        except ValueError as error:
            self._runtime_error(str(error))
            return

        key = self._args.key
        if self._args.dry_run:
            Console.info(f"GET {client.issue_api_url(key=key)}")
            Console.info(f"GET {client.comments_api_url(key=key)}")
            return

        try:
            markdown = TicketMarkdown(client=client).render(key=key)
        except RuntimeError as error:
            self._runtime_error(str(error))
            return

        if self._args.output:
            self._write_markdown(markdown=markdown)
        else:
            print(markdown)

    def _write_markdown(self, *, markdown):
        """Write the rendered markdown to the requested output file."""
        out_path = Path(self._args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(markdown, encoding='utf-8')
        if not self._args.quiet:
            Console.success(f"Wrote markdown to {out_path}")

    def _comment_body(self):
        """Return the comment body from --comment or --file."""
        body = self._args.comment
        if self._args.file:
            body = Path(self._args.file).read_text(encoding='utf-8')
        return body

    def _cmd_update(self):
        """Add a comment to a ticket."""
        try:
            client = self._build_client()
        except ValueError as error:
            self._runtime_error(str(error))
            return

        key = self._args.key
        body = self._comment_body()
        if not body or not body.strip():
            self._runtime_error("a --comment or --file is required")
            return

        if self._args.dry_run:
            Console.info(f"POST {client.comment_api_url(key=key)}")
            return

        try:
            client.add_comment(key=key, body=body)
        except RuntimeError as error:
            self._runtime_error(str(error))
            return
        if not self._args.quiet:
            Console.success(f"Added comment to {key}")


if __name__ == '__main__':
    app = Kernel(
        author='TangoMan75',
        title='Jira REST wrapper',
        description='Authenticate and fetch Jira tickets with their comments as markdown.',
        config=JiraConfig(),
    )
    app.run()
