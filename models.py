#!/usr/bin/env python3
"""Recommend OpenCode models by cost, value, or quality."""

import argparse
import datetime
import http.client
import json
import re
import shlex
import shutil
import socket
import ssl
import sys
import urllib.error
import urllib.request
from abc import ABC
from abc import abstractmethod
from html.parser import HTMLParser
from pathlib import Path

#--------------------------------------------------
# Console: Semantic console output
#--------------------------------------------------


class Console:
    """Console output with semantic coloring and alert blocks."""

    quiet = False

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
        """Return (indentation, text, padding)."""
        pad = max(0, padding - len(text))
        return " " * indent, text, " " * pad

    @staticmethod
    def _alert_block(color, *, text):
        """Print a colored alert block."""
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
        indentation, body, pad = Console._pad_and_indent(text, indent=indent, padding=padding)
        print(f"{indentation}{Console.PRIMARY}{body}{Console.DEFAULT}{pad}", end='')

    @staticmethod
    def secondary(text, *, indent=0, padding=0):
        """Print text in secondary color."""
        indentation, body, pad = Console._pad_and_indent(text, indent=indent, padding=padding)
        print(f"{indentation}{Console.SECONDARY}{body}{Console.DEFAULT}{pad}", end='')

    @staticmethod
    def success(text, *, indent=0, padding=0):
        """Print text in success color."""
        indentation, body, pad = Console._pad_and_indent(text, indent=indent, padding=padding)
        print(f"{indentation}{Console.SUCCESS}{body}{Console.DEFAULT}{pad}", end='')

    @staticmethod
    def danger(text, *, indent=0, padding=0):
        """Print text in danger color."""
        indentation, body, pad = Console._pad_and_indent(text, indent=indent, padding=padding)
        print(f"{indentation}{Console.DANGER}{body}{Console.DEFAULT}{pad}", end='')

    @staticmethod
    def warning(text, *, indent=0, padding=0):
        """Print text in warning color."""
        indentation, body, pad = Console._pad_and_indent(text, indent=indent, padding=padding)
        print(f"{indentation}{Console.WARNING}{body}{Console.DEFAULT}{pad}", end='')

    @staticmethod
    def info(text, *, indent=0, padding=0):
        """Print text in info color."""
        indentation, body, pad = Console._pad_and_indent(text, indent=indent, padding=padding)
        print(f"{indentation}{Console.INFO}{body}{Console.DEFAULT}{pad}", end='')

    @staticmethod
    def light(text, *, indent=0, padding=0):
        """Print text in light color."""
        indentation, body, pad = Console._pad_and_indent(text, indent=indent, padding=padding)
        print(f"{indentation}{Console.LIGHT}{body}{Console.DEFAULT}{pad}", end='')

    @staticmethod
    def dark(text, *, indent=0, padding=0):
        """Print text in dark color."""
        indentation, body, pad = Console._pad_and_indent(text, indent=indent, padding=padding)
        print(f"{indentation}{Console.DARK}{body}{Console.DEFAULT}{pad}", end='')

    @staticmethod
    def error(message):
        """Print error message to stderr."""
        print(f"{Console.DANGER}error: {message}{Console.DEFAULT}", file=sys.stderr)

#--------------------------------------------------
# Logger: file logging and output
#--------------------------------------------------


class Logger:
    """Log messages to file and console based on verbosity."""

    LEVEL_NAMES = {0: "ERROR", 1: "SUCCESS", 2: "WARNING", 3: "INFO"}

    def __init__(self, *, verbose=0, script_file=None, quiet=False):
        self.verbose = verbose
        self.quiet = quiet
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
        level = Logger.LEVEL_NAMES.get(loglevel, "INFO")
        timestamp = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f')
        line = f"{timestamp} {level} {message}"
        with open(self.log_file, "a", encoding="utf-8") as log_file:
            log_file.write(line + "\n")
        if loglevel == 0:
            Console.danger(f"{message}\n")
        elif not self.quiet and self.verbose >= loglevel:
            if loglevel == 1:
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
    """No-op logger used when no logger is injected."""

    def __init__(self, *, verbose=0, quiet=False):
        self.verbose = verbose
        self.quiet = quiet

    def print(self):
        """Do nothing and report that no log was printed."""
        return False

    def log(self, message, *, loglevel=0):
        """Ignore a log entry."""

    def info(self, message):
        """Ignore an info entry."""

    def warning(self, message):
        """Ignore a warning entry."""

    def success(self, message):
        """Ignore a success entry."""

    def danger(self, message):
        """Ignore an error entry."""

#--------------------------------------------------
# Completion: bash completion script generator
#--------------------------------------------------


class Completion:
    """Bash completion script generator."""

    FILE_KEYS = ("output", "file", "path", "dest")
    GLOB_KEYS = ("include", "exclude", "glob", "pattern")
    BOOLEAN_BODY = "            COMPREPLY=()\n"
    VERBOSE_BODY = '            COMPREPLY=( $(compgen -W "-v -vv -vvv" -- "${cur}") )\n'
    FILE_BODY = '            COMPREPLY=( $(compgen -f -- "${cur}") )\n'
    GLOB_BODY = '            COMPREPLY=( $(compgen -G "${cur}*") )\n'

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
    def _classify_parser_actions(*, arg_parser):
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

complete -F _{completion_name}_completions {shlex.quote(name)}
'''

    @classmethod
    def generate(cls, *, parser, name):
        """Return a bash completion script for the given parser."""
        all_opts, categories = cls._classify_parser_actions(arg_parser=parser)
        return cls._render_script(all_opts=all_opts, categories=categories, name=name)

#--------------------------------------------------
# Cache: file-based caching with TTL
#--------------------------------------------------


class Cache:
    """File-based caching with configurable TTL.

    When installed (running from ~/.local/share/TangoMan75/), uses
    ~/.cache/TangoMan75/<name>/; otherwise uses ./cache/.
    """

    DEFAULT_TTL_DAYS = 1
    TIMESTAMP_FORMAT = "%Y-%m-%d_%H-%M-%S"

    def __init__(self, *, ttl=None):
        script_file = Path(__file__).resolve()
        script_dir = script_file.parent
        script_name = script_file.stem
        installed_dir = Path.home() / ".local" / "share" / "TangoMan75"
        if str(script_dir).startswith(str(installed_dir)):
            self.cache_dir = Path.home() / ".cache" / "TangoMan75" / script_name
        else:
            self.cache_dir = script_dir / "cache"
        self.ttl = ttl or datetime.timedelta(days=Cache.DEFAULT_TTL_DAYS)

    def _cache_path(self, *, request):
        """Return the cache file path for a given request name."""
        stamp = datetime.datetime.now().strftime(Cache.TIMESTAMP_FORMAT)
        return self.cache_dir / f"{stamp}_{request}.json"

    def read(self, *, request):
        """Return cached data if fresh, else None."""
        if not self.cache_dir.exists():
            return None
        prefix = f"{request}.json"
        for path in sorted(self.cache_dir.glob(f"*_{prefix}"), reverse=True):
            try:
                stamp = path.stem.rsplit("_", 1)[0]
                cached_at = datetime.datetime.strptime(stamp, Cache.TIMESTAMP_FORMAT)
                if datetime.datetime.now() - cached_at > self.ttl:
                    return None
                return json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, json.JSONDecodeError, OSError):
                continue
        return None

    def write(self, *, request, data):
        """Write data to the cache file."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self._cache_path(request=request)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def clear(self):
        """Remove every cached file for this cache."""
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)

#--------------------------------------------------
# Transport: URL fetching resilient to broken IPv6 routes
#--------------------------------------------------


class _FastHttpsConnection(http.client.HTTPSConnection):
    """HTTPS connection whose TCP connect prefers IPv4 addresses first."""

    CONNECT_TIMEOUT = 4.0
    DEFAULT_PORT = 443

    def __init__(self, host, *, transport, **kwargs):
        super().__init__(host, **kwargs)
        self._transport = transport

    def connect(self):
        """Open the TCP connection through the injected transport."""
        self.sock = self._transport.connect(
            host=self.host,
            port=self.port or _FastHttpsConnection.DEFAULT_PORT,
            timeout=_FastHttpsConnection.CONNECT_TIMEOUT,
        )
        server_hostname = self._tunnel_host or self.host
        self.sock = self._context.wrap_socket(self.sock, server_hostname=server_hostname)
        if isinstance(self.timeout, (int, float)):
            self.sock.settimeout(self.timeout)


class _FastHttpsHandler(urllib.request.HTTPSHandler):
    """HTTPS opener delegating TCP connections to :class:`_FastHttpsConnection`."""

    def __init__(self, *, transport, **kwargs):
        super().__init__(**kwargs)
        self._transport = transport

    def https_open(self, req):
        """Open an HTTPS request with the fast connection class."""
        return self.do_open(
            _FastHttpsConnection,
            req,
            transport=self._transport,
            context=self._context,
        )


class HttpTransport:
    """Fetch URL bodies over HTTPS, trying IPv4 addresses before IPv6.

    getaddrinfo sorts IPv6 addresses first, so urllib connects to them one by
    one; when the IPv6 route is dead (no RST, no answer) every attempt stalls
    for the full timeout before IPv4 is reached. Short per-address timeouts and
    IPv4-first ordering avoid that stall (Happy Eyeballs style). Remembering
    the first successful family skips the dead route entirely.
    """

    USER_AGENT = ""
    ENCODING = "utf-8"
    IPV4_RANK = 1
    OTHER_RANK = 2

    def __init__(self):
        self._preferred_family = None

    def fetch_text(self, *, url, timeout):
        """Fetch a URL and return the response body decoded as UTF-8."""
        request = urllib.request.Request(
            url,
            headers={"User-Agent": HttpTransport.USER_AGENT},
        )
        handler = _FastHttpsHandler(
            transport=self,
            context=ssl.create_default_context(),
        )
        with urllib.request.build_opener(handler).open(request, timeout=timeout) as response:
            return response.read().decode(HttpTransport.ENCODING)

    def connect(self, *, host, port, timeout):
        """Open a TCP connection, trying IPv4 addresses before IPv6."""
        infos = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
        candidates = [(info[0], info[4]) for info in infos]
        candidates.sort(key=self._rank)
        last_error = None
        for family, address in candidates:
            sock = socket.socket(family, socket.SOCK_STREAM)
            try:
                sock.settimeout(timeout)
                sock.connect(address)
                self._preferred_family = family
                return sock
            except OSError as err:
                sock.close()
                last_error = err
        raise ConnectionError(f"Could not connect to {host}:{port}: {last_error}")

    def _rank(self, entry):
        """Rank a socket address candidate for sorting."""
        if entry[0] == self._preferred_family:
            return 0
        if entry[0] == socket.AF_INET:
            return HttpTransport.IPV4_RANK
        return HttpTransport.OTHER_RANK

#--------------------------------------------------
# Catalog fetchers: models.dev, OpenCode Go, BenchLM
#--------------------------------------------------


class ModelsDevFetcher:
    """Fetch and cache the models.dev catalog."""

    URL = "https://models.dev/api.json"
    CACHE_KEY = "models"
    TIMEOUT = 30

    def __init__(self, *, transport, cache, logger=None):
        self._transport = transport
        self._cache = cache
        self._logger = logger if logger is not None else NullLogger()

    def fetch(self):
        """Fetch the models catalog, using the cache when fresh."""
        cached = self._cache.read(request=ModelsDevFetcher.CACHE_KEY)
        if cached is not None:
            self._logger.info("Using cached models catalog")
            return cached
        self._logger.info(f"Fetching {ModelsDevFetcher.URL}")
        try:
            text = self._transport.fetch_text(
                url=ModelsDevFetcher.URL,
                timeout=ModelsDevFetcher.TIMEOUT,
            )
            data = json.loads(text)
            self._cache.write(request=ModelsDevFetcher.CACHE_KEY, data=data)
            model_count = self._model_count(catalog=data)
            self._logger.success(f"Loaded {model_count} models from {len(data)} providers")
            return data
        except (urllib.error.URLError, OSError) as err:
            Console.error(f"Failed to fetch models: {err}")
            sys.exit(1)

    @staticmethod
    def _model_count(*, catalog):
        """Count models across every provider in the catalog."""
        return sum(len(provider.get("models", {})) for provider in catalog.values())


class GoModelsParser(HTMLParser):
    """Extract model rows from the Console Go requests table."""

    PLAN = "go"
    REQUESTS_HEADING = "requests"
    NAME_LAYER = "model-name"
    VALUE_LAYER = "current-value"
    VOID_TAGS = frozenset({
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    })

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self._tags = []
        self._table = None
        self._in_header = False
        self._in_body = False
        self._row = None
        self._cell = None
        self._name = None
        self._value = None
        self._found = False

    def handle_starttag(self, tag, attrs):
        """Track tables, rows, cells, names, and plan-attributed values."""
        attributes = dict(attrs)
        if tag not in GoModelsParser.VOID_TAGS:
            self._tags.append((tag, attributes))
        if tag == "table":
            self._table = {"header": [], "rows": []}
        elif tag == "thead":
            self._in_header = True
        elif tag == "tbody":
            self._in_body = True
        elif tag == "tr":
            self._row = {"id": attributes.get("data-model"), "cells": []}
        elif tag in ("th", "td"):
            self._cell = {
                "text": [],
                "type": attributes.get("data-allowance-type"),
                "values": [],
            }
        elif attributes.get("data-layer") == GoModelsParser.NAME_LAYER:
            self._name = {"parts": [], "depth": len(self._tags)}
        elif attributes.get("data-layer") == GoModelsParser.VALUE_LAYER:
            self._value = {
                "plan": self._active_plan(),
                "parts": [],
                "depth": len(self._tags),
            }

    def handle_endtag(self, tag):
        """Close the current name, value, cell, row, or table."""
        if self._name is not None and len(self._tags) == self._name["depth"]:
            self._close_name()
        if self._value is not None and len(self._tags) == self._value["depth"]:
            self._close_value()
        if tag in ("th", "td"):
            self._close_cell()
        elif tag == "tr":
            self._close_row()
        elif tag == "thead":
            self._in_header = False
        elif tag == "tbody":
            self._in_body = False
        elif tag == "table":
            self._close_table()
        if self._tags:
            self._tags.pop()

    def handle_data(self, data):
        """Collect text inside the current table cell, name, or value."""
        if self._cell is not None:
            self._cell["text"].append(data)
        if self._name is not None:
            self._name["parts"].append(data)
        if self._value is not None:
            self._value["parts"].append(data)

    def _active_plan(self):
        """Return the nearest plan attributed to an open ancestor tag."""
        for _, attributes in reversed(self._tags):
            plan = attributes.get("data-plan")
            if plan is not None:
                return plan
        return None

    def _close_name(self):
        """Store the model name without any trailing badge text."""
        if self._cell is not None:
            self._cell["name"] = " ".join("".join(self._name["parts"]).split())
        self._name = None

    def _close_value(self):
        """Store the plan-attributed value in the current cell."""
        if self._cell is not None:
            text = " ".join("".join(self._value["parts"]).split())
            self._cell["values"].append((self._value["plan"], text))
        self._value = None

    def _close_cell(self):
        """Append the normalized cell text to the current row."""
        if self._cell is None:
            return
        self._cell["text"] = " ".join("".join(self._cell["text"]).split())
        if self._row is not None:
            self._row["cells"].append(self._cell)
        self._cell = None

    def _close_row(self):
        """Store the current row in the table header or body."""
        if self._row is None:
            return
        if self._table is not None:
            if self._in_header:
                self._table["header"] = [
                    cell["text"] for cell in self._row["cells"]
                ]
            elif self._in_body:
                self._table["rows"].append(self._row)
        self._row = None

    def _close_table(self):
        """Keep the first table whose header lists request counts."""
        if self._table is None:
            return
        table = self._table
        self._table = None
        if self._found:
            return
        header = " ".join(table["header"]).lower()
        if GoModelsParser.REQUESTS_HEADING not in header:
            return
        self.rows = table["rows"]
        self._found = True


class GoFetcher:
    """Fetch and cache OpenCode Go request allowances from the console page."""

    URL = "https://opencode.ai/console/go"
    CACHE_KEY = "go"
    TIMEOUT = 30
    UNLIMITED_VALUES = ("unlimited", "infinity", "∞")

    def __init__(self, *, transport, cache, logger=None):
        self._transport = transport
        self._cache = cache
        self._logger = logger if logger is not None else NullLogger()

    def fetch(self):
        """Fetch Go models, using the cache when fresh."""
        cached = self._cache.read(request=GoFetcher.CACHE_KEY)
        if cached is not None:
            self._logger.info("Using cached Go models")
            return cached
        self._logger.info(f"Fetching {GoFetcher.URL}")
        html = self._fetch_page()
        parser = GoModelsParser()
        parser.feed(html)
        models = self._normalize(rows=parser.rows)
        if not models:
            Console.error("Failed to parse Go models from page.")
            sys.exit(1)
        self._cache.write(request=GoFetcher.CACHE_KEY, data=models)
        self._logger.success(f"Loaded {len(models)} Go models")
        return models

    def _fetch_page(self):
        """Fetch the Go documentation HTML."""
        try:
            return self._transport.fetch_text(
                url=GoFetcher.URL,
                timeout=GoFetcher.TIMEOUT,
            )
        except (urllib.error.URLError, OSError) as err:
            Console.error(f"Failed to fetch Go page: {err}")
            sys.exit(1)

    @classmethod
    def _normalize(cls, *, rows):
        """Convert table rows to model dicts sorted by request allowance."""
        models = []
        for row in rows:
            cells = row.get("cells", [])
            name = ""
            if cells:
                name = (cells[0].get("name") or cells[0]["text"]).strip()
            if not name:
                continue
            requests, unlimited = cls._parse_requests(value=cls._requests_text(cells=cells))
            models.append({
                "id": row.get("id") or "",
                "name": name,
                "requests": requests,
                "unlimited": unlimited,
            })
        models.sort(key=cls._allowance_key, reverse=True)
        return models

    @staticmethod
    def _requests_text(*, cells):
        """Return the Go-plan request value from a row's request cell."""
        cell = next(
            (item for item in cells if item.get("type") == "requests"),
            None,
        )
        if cell is None:
            cell = cells[1] if len(cells) > 1 else None
        if cell is None:
            return ""
        values = dict(cell.get("values", []))
        if GoModelsParser.PLAN in values:
            return values[GoModelsParser.PLAN]
        if values:
            return next(iter(values.values()))
        return cell["text"]

    @classmethod
    def _parse_requests(cls, *, value):
        """Return the request count and unlimited flag for a table cell."""
        text = value.strip().lower()
        if text in GoFetcher.UNLIMITED_VALUES or text.startswith("unlimited"):
            return 0, True
        digits = re.sub(r"\D", "", text)
        return int(digits) if digits else 0, False

    @staticmethod
    def _allowance_key(model):
        """Sort key ordering unlimited models first, then by requests."""
        return model["unlimited"], model["requests"]


class BenchLmFetcher:
    """Fetch and cache the BenchLM composite intelligence leaderboard."""

    URL = "https://benchlm.ai/data/leaderboard.json"
    CACHE_KEY = "benchlm"
    TIMEOUT = 30
    ATTRIBUTION = "Data from BenchLM.ai (CC BY-NC 4.0, https://benchlm.ai/data)\n"

    def __init__(self, *, transport, cache, logger=None):
        self._transport = transport
        self._cache = cache
        self._logger = logger if logger is not None else NullLogger()

    def fetch(self, *, required=True):
        """Fetch intelligence entries, degrading gracefully when optional."""
        cached = self._cache.read(request=BenchLmFetcher.CACHE_KEY)
        if cached is not None:
            self._logger.info("Using cached BenchLM leaderboard")
            return cached
        self._logger.info(f"Fetching {BenchLmFetcher.URL}")
        try:
            text = self._transport.fetch_text(
                url=BenchLmFetcher.URL,
                timeout=BenchLmFetcher.TIMEOUT,
            )
            data = json.loads(text)
        except (urllib.error.URLError, OSError) as err:
            message = f"Failed to fetch BenchLM leaderboard: {err}"
            if required:
                Console.error(message)
                sys.exit(1)
            self._logger.warning(message)
            return None
        entries = [
            {
                "key": item.get("canonicalModelKey", ""),
                "name": item.get("model", ""),
                "creator": item.get("creator", ""),
                "score": float(item.get("score", 0.0)),
                "rank": item.get("overallRank", 0),
            }
            for item in data.get("items", [])
        ]
        self._cache.write(request=BenchLmFetcher.CACHE_KEY, data=entries)
        self._logger.success(f"Loaded {len(entries)} BenchLM ranked models")
        return entries

#--------------------------------------------------
# Models: catalog flattening, filtering, scoring, sorting
#--------------------------------------------------


class ModelCatalog:
    """Flatten provider catalogs and merge Go models with models.dev data."""

    PROVIDER_PRIORITY = {"opencode-go": 0, "opencode": 1}
    OTHER_PROVIDER_PRIORITY = 2

    def __init__(self, *, logger=None):
        self._logger = logger if logger is not None else NullLogger()

    @staticmethod
    def flatten(*, catalog):
        """Flatten the provider/model hierarchy into a list of model dicts."""
        result = []
        for provider_id, provider in catalog.items():
            provider_name = provider.get("name", provider_id)
            for model_id, model in provider.get("models", {}).items():
                cost = model.get("cost", {})
                input_cost = cost.get("input", 0)
                output_cost = cost.get("output", 0)
                limit = model.get("limit", {})
                result.append({
                    "provider": provider_name,
                    "provider_id": provider_id,
                    "id": model_id,
                    "name": model.get("name", model_id),
                    "description": model.get("description", ""),
                    "input_cost": input_cost,
                    "output_cost": output_cost,
                    "total_cost": input_cost + output_cost,
                    "context": limit.get("context", 0),
                    "output_limit": limit.get("output", 0),
                    "reasoning": model.get("reasoning", False),
                    "tool_call": model.get("tool_call", False),
                    "structured_output": model.get("structured_output", False),
                    "attachment": model.get("attachment", False),
                    "open_weights": model.get("open_weights", False),
                    "status": model.get("status", ""),
                    "release_date": model.get("release_date", ""),
                    "updated_date": model.get("last_updated", ""),
                })
        return result

    @classmethod
    def _catalog_key(cls, *, text):
        """Normalize an id or name into a punctuation-insensitive lookup key."""
        return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")

    @classmethod
    def _provider_priority(cls, *, model):
        """Rank providers so OpenCode Go entries win over lookalikes."""
        return cls.PROVIDER_PRIORITY.get(
            model["provider_id"],
            cls.OTHER_PROVIDER_PRIORITY,
        )

    @classmethod
    def _catalog_lookup(cls, *, catalog):
        """Index flattened models by normalized id and name."""
        flattened = cls.flatten(catalog=catalog)
        flattened.sort(key=lambda model: cls._provider_priority(model=model))
        lookup = {}
        for model in flattened:
            keys = [model["id"], model["name"]]
            if "/" in model["id"]:
                keys.append(model["id"].split("/", 1)[1])
            for key in keys:
                lookup.setdefault(cls._catalog_key(text=key), model)
        return lookup

    def merge_go(self, *, go_models, catalog):
        """Merge Go models with the catalog to add cost, context, and capabilities."""
        lookup = self._catalog_lookup(catalog=catalog)
        merged = []
        for go_model in go_models:
            match = None
            for key in (go_model.get("name"), go_model.get("id")):
                if not key:
                    continue
                match = lookup.get(self._catalog_key(text=key))
                if match is not None:
                    break
            if match is None:
                label = go_model.get("name") or go_model.get("id") or "unknown"
                self._logger.warning(f"No catalog match for Go model: {label}")
                continue
            merged.append({
                "id": match["id"].rsplit("/", 1)[-1],
                "name": go_model["name"],
                "requests": go_model["requests"],
                "unlimited": go_model.get("unlimited", False),
                "input_cost": match["input_cost"],
                "output_cost": match["output_cost"],
                "total_cost": match["total_cost"],
                "context": match["context"],
                "reasoning": match["reasoning"],
                "tool_call": match["tool_call"],
                "structured_output": match["structured_output"],
                "attachment": match["attachment"],
            })
        self._logger.success(f"Merged {len(merged)} Go models with catalog")
        return merged


class ModelFilter:
    """Filter flattened models by user-selected criteria."""

    @classmethod
    def apply(cls, *, models, exclude_free=False, provider=None, min_context=0,
              tool_call=False, reasoning=False, free_only=False):
        """Return the models matching every requested filter."""
        result = models
        if exclude_free:
            result = [model for model in result if model["total_cost"] > 0]
        if provider:
            provider_lower = provider.lower()
            result = [
                model for model in result
                if provider_lower in model["provider_id"].lower()
                or provider_lower in model["provider"].lower()
            ]
        if min_context > 0:
            result = [model for model in result if model["context"] >= min_context]
        if tool_call:
            result = [model for model in result if model["tool_call"]]
        if reasoning:
            result = [model for model in result if model["reasoning"]]
        if free_only:
            result = [model for model in result if model["total_cost"] == 0]
        return result


class ModelScorer:
    """Compute heuristic value scores and BenchLM intelligence scores."""

    CONTEXT_UNIT = 1_000_000
    REQUESTS_SCALE = 1000
    UNLIMITED_RATIO = 2.0
    REASONING_BONUS = 0.2
    TOOL_CALL_BONUS = 0.2
    STRUCTURED_OUTPUT_BONUS = 0.2
    ATTACHMENT_BONUS = 0.1

    @classmethod
    def _capability_bonus(cls, *, model):
        """Return the capability multiplier for a model."""
        bonus = 1.0
        if model["reasoning"]:
            bonus += cls.REASONING_BONUS
        if model["tool_call"]:
            bonus += cls.TOOL_CALL_BONUS
        if model["structured_output"]:
            bonus += cls.STRUCTURED_OUTPUT_BONUS
        if model["attachment"]:
            bonus += cls.ATTACHMENT_BONUS
        return bonus

    @classmethod
    def score(cls, *, model):
        """Compute a value-for-money score (higher is better)."""
        context_millions = max(model["context"], 1) / cls.CONTEXT_UNIT
        bonus = cls._capability_bonus(model=model)
        if model["total_cost"] == 0:
            return context_millions * bonus
        return (context_millions * bonus) / model["total_cost"]

    @classmethod
    def score_go(cls, *, model):
        """Compute the Go usage-adjusted score."""
        context_millions = max(model["context"], 1) / cls.CONTEXT_UNIT
        bonus = cls._capability_bonus(model=model)
        if model.get("unlimited"):
            requests_ratio = cls.UNLIMITED_RATIO
        else:
            requests_ratio = 1 / max(model["requests"], 1) * cls.REQUESTS_SCALE
        if model["total_cost"] == 0:
            return context_millions * bonus * requests_ratio
        return (context_millions * bonus * requests_ratio) / model["total_cost"]

    @staticmethod
    def intelligence(*, model):
        """Compute intelligence per dollar (free models score raw intelligence)."""
        intelligence = model.get("intelligence")
        if intelligence is None:
            return 0.0
        if model["total_cost"] == 0:
            return intelligence
        return intelligence / model["total_cost"]

    @staticmethod
    def intelligence_allowance(*, model):
        """Compute intelligence throughput per Go window: intelligence x allowance."""
        intelligence = model.get("intelligence")
        if intelligence is None:
            return 0.0
        if model.get("unlimited"):
            return float("inf")
        requests = max(model.get("requests") or 0, 0)
        return intelligence * requests


class ModelSorter:
    """Sort flattened models by cost, intelligence, or recency."""

    def __init__(self, *, scorer=None):
        self._scorer = scorer if scorer is not None else ModelScorer()

    def cheapest(self, *, models):
        """Sort by total cost ascending (cheapest first)."""
        return sorted(models, key=lambda model: (model["total_cost"], -model["context"]))

    def value(self, *, models):
        """Sort by intelligence per dollar; unranked models follow by value score."""
        return sorted(models, key=self._value_key)

    def best(self, *, models):
        """Sort by intelligence descending, then by the quality heuristic."""
        return sorted(models, key=self._best_key)

    def released(self, *, models):
        """Sort by release date descending (most recent first)."""
        return sorted(models, key=lambda model: model["release_date"], reverse=True)

    def updated(self, *, models):
        """Sort by update date descending (most recent first)."""
        return sorted(models, key=lambda model: model["updated_date"], reverse=True)

    def value_go(self, *, models):
        """Sort Go models by intelligence x allowance, then by Go score."""
        return sorted(models, key=self._go_value_key)

    def _value_key(self, model):
        """Sort key for intelligence-per-dollar ordering."""
        return (
            0 if model.get("intelligence") is not None else 1,
            -self._scorer.intelligence(model=model),
            -self._scorer.score(model=model),
        )

    def _best_key(self, model):
        """Sort key for raw intelligence ordering."""
        intelligence = model.get("intelligence")
        if intelligence is not None:
            return 0, -intelligence
        capabilities = sum([
            model["reasoning"],
            model["tool_call"],
            model["structured_output"],
            model["attachment"],
        ])
        return 1, 0, -model["context"], -capabilities, model.get("release_date", "")

    def _go_value_key(self, model):
        """Sort key for Go intelligence-throughput ordering."""
        intelligence = model.get("intelligence")
        if intelligence is None:
            return 1, 0.0, 0.0, -self._scorer.score_go(model=model)
        return (
            0,
            -self._scorer.intelligence_allowance(model=model),
            -intelligence,
            -self._scorer.score_go(model=model),
        )

#--------------------------------------------------
# Intelligence: BenchLM name matching and attribution
#--------------------------------------------------


class IntelligenceMatcher:
    """Normalize model names and attach BenchLM intelligence scores."""

    VARIANT_TOKENS = (
        "adaptive",
        "beta",
        "contributor",
        "flex",
        "free",
        "preview",
        "reasoning",
        "spot",
        "tee",
        "thinking",
        "ultraspeed",
    )
    VARIANT_PHRASES = ("non-reasoning",)
    PARENTHESIS_PATTERN = r"\([^)]*\)"
    BRACKET_PATTERN = r"\[[^\]]*\]"
    SEPARATOR_PATTERN = r"[^a-z0-9]+"
    SEPARATOR = "-"
    ID_SEPARATOR = "/"

    @classmethod
    def normalize(cls, *, text):
        """Normalize a model name or id into a comparable lookup key."""
        text = text.lower()
        text = re.sub(cls.PARENTHESIS_PATTERN, " ", text)
        text = re.sub(cls.BRACKET_PATTERN, " ", text)
        text = re.sub(cls.SEPARATOR_PATTERN, cls.SEPARATOR, text)
        return text.strip(cls.SEPARATOR)

    @classmethod
    def variants(cls, *, key):
        """Return the key plus variants with plan, hosting, and state markers stripped.

        Only serving/billing markers are removed; model-defining markers
        (turbo, lite, codex, chat, effort knobs like max/high, date stamps)
        are kept on purpose, so a variant never inherits another model's score.
        """
        variants = {key}
        frontier = [key]
        while frontier:
            current = frontier.pop()
            for phrase in cls.VARIANT_PHRASES:
                if current.endswith(cls.SEPARATOR + phrase):
                    parent = current[: -(len(phrase) + 1)]
                    if parent and parent not in variants:
                        variants.add(parent)
                        frontier.append(parent)
            parent, _, last = current.rpartition(cls.SEPARATOR)
            if parent and last in cls.VARIANT_TOKENS and parent not in variants:
                variants.add(parent)
                frontier.append(parent)
        return variants

    @classmethod
    def lookup_keys(cls, *, model):
        """Return normalized lookup candidates for a flattened model."""
        candidates = set()
        for text in (model["id"], model["name"]):
            candidates |= cls.variants(key=cls.normalize(text=text))
        if cls.ID_SEPARATOR in model["id"]:
            short_id = model["id"].split(cls.ID_SEPARATOR, 1)[1]
            candidates |= cls.variants(key=cls.normalize(text=short_id))
        return candidates

    @staticmethod
    def _signature(*, key):
        """Return the order-independent token signature of a lookup key."""
        return tuple(sorted(part for part in key.split("-") if part))

    @classmethod
    def attach(cls, *, models, entries):
        """Attach BenchLM scores to flattened models without mutating inputs."""
        entries = entries or []
        exact = {}
        for entry in entries:
            for key in cls.variants(key=cls.normalize(text=entry["key"])):
                exact.setdefault(key, entry)
            for key in cls.variants(key=cls.normalize(text=entry["name"])):
                exact.setdefault(key, entry)
        token_lookup = {}
        for key, entry in exact.items():
            token_lookup.setdefault(cls._signature(key=key), entry)
        result = []
        for model in models:
            model = dict(model)
            candidates = cls.lookup_keys(model=model)
            match = None
            for key in candidates:
                if key in exact:
                    match = exact[key]
                    break
            if match is None:
                for key in candidates:
                    candidate = token_lookup.get(cls._signature(key=key))
                    if candidate is not None:
                        match = candidate
                        break
            if match is not None:
                model["intelligence"] = match["score"]
                model["intelligence_rank"] = match["rank"]
            else:
                model["intelligence"] = None
                model["intelligence_rank"] = None
            result.append(model)
        return result


class IntelligenceAttribution:
    """Print the BenchLM license credit only when a score is displayed."""

    ATTRIBUTION = BenchLmFetcher.ATTRIBUTION

    @classmethod
    def show(cls, *, models, machine_output=False):
        """Print the credit when any displayed model carries a score."""
        if any(model.get("intelligence") is not None for model in models):
            cls.render(machine_output=machine_output)

    @classmethod
    def render(cls, *, machine_output=False):
        """Print the BenchLM license credit to stdout or stderr."""
        if machine_output:
            print(cls.ATTRIBUTION, file=sys.stderr)
        else:
            Console.info(cls.ATTRIBUTION)

#--------------------------------------------------
# Model formatter: cost, context, flags, requests, scores
#--------------------------------------------------


class ModelFormatter:
    """Format model fields for display."""

    SMALL_COST = 0.01
    MEDIUM_COST = 1
    CONTEXT_MILLION = 1_000_000
    CONTEXT_THOUSAND = 1_000
    UNLIMITED = "∞"
    EMPTY = "-"

    def __init__(self, *, scorer=None):
        self._scorer = scorer if scorer is not None else ModelScorer()

    def cost(self, *, value):
        """Format a cost value for display."""
        if value == 0:
            return "free"
        if value < ModelFormatter.SMALL_COST:
            return f"${value:.4f}"
        if value < ModelFormatter.MEDIUM_COST:
            return f"${value:.3f}"
        return f"${value:.2f}"

    def context(self, *, tokens):
        """Format a context window for display."""
        if tokens >= ModelFormatter.CONTEXT_MILLION:
            return f"{tokens / ModelFormatter.CONTEXT_MILLION:.1f}M"
        if tokens >= ModelFormatter.CONTEXT_THOUSAND:
            return f"{tokens / ModelFormatter.CONTEXT_THOUSAND:.0f}K"
        return str(tokens)

    @staticmethod
    def flags(*, model):
        """Format capability flags as a compact string."""
        flags = []
        if model["reasoning"]:
            flags.append("R")
        if model["tool_call"]:
            flags.append("T")
        if model["structured_output"]:
            flags.append("S")
        if model["attachment"]:
            flags.append("A")
        return "".join(flags) if flags else "-"

    @staticmethod
    def requests(*, model):
        """Format a request count; unlimited models show infinity."""
        if model.get("unlimited"):
            return ModelFormatter.UNLIMITED
        return f"{model['requests']:,}"

    @staticmethod
    def intelligence(*, model):
        """Format the BenchLM intelligence score for display."""
        intelligence = model.get("intelligence")
        if intelligence is None:
            return ModelFormatter.EMPTY
        return f"{intelligence:.1f}"

    def score(self, *, model):
        """Return the heuristic value score for a model."""
        return self._scorer.score(model=model)

    def go_scores(self, *, models, value_score=False):
        """Return per-row Go scores: relative shares for --value, else legacy."""
        if not value_score:
            return [self._scorer.score_go(model=model) for model in models]
        products = [self._scorer.intelligence_allowance(model=model) for model in models]
        ceiling = max(
            (product for product in products if product < float("inf")),
            default=0.0,
        )
        shares = []
        for product in products:
            if product == 0.0:
                shares.append(0.0)
            elif product == float("inf"):
                shares.append(1.0)
            else:
                shares.append(product / ceiling)
        return shares

    @staticmethod
    def go_score(*, value, value_score=False, empty="-"):
        """Format a Go score cell (4-decimal share for --value, else 2 decimals)."""
        if value == 0:
            return empty
        if value_score:
            return f"{value:.4f}"
        return f"{value:.2f}"

#--------------------------------------------------
# Printers: model output
#--------------------------------------------------


class ModelPrinter(ABC):
    """Render flattened models in one output format."""

    def __init__(self, *, formatter=None):
        self._formatter = formatter if formatter is not None else ModelFormatter()

    @abstractmethod
    def render(self, *, models, title="", show_intel=False):
        """Write the models to stdout."""


class ModelTablePrinter(ModelPrinter):
    """Print models as a formatted table."""

    def render(self, *, models, title="", show_intel=False):
        """Print models as a formatted table."""
        if not models:
            Console.warning("No models match the given filters.\n")
            return
        Console.alert_info(title)
        intel_head = f" {'Intel':>6}" if show_intel else ""
        intel_rule = f" {'-' * 6}" if show_intel else ""
        header = (
            f"  {'Provider':<16} {'Model':<36} {'In':>8} {'Out':>8} {'Context':>9} {'Cap':<4}"
            f"{intel_head} {'Score':>7}"
        )
        Console.secondary(header)
        print()
        rule = (
            f"  {'-' * 16} {'-' * 36} {'-' * 8} {'-' * 8} {'-' * 9} {'-' * 4}"
            f"{intel_rule} {'-' * 7}"
        )
        Console.secondary(rule)
        print()
        for model in models:
            score = self._formatter.score(model=model)
            score_text = f"{score:.2f}" if score > 0 else "-"
            intel_cell = (
                f" {self._formatter.intelligence(model=model):>6}" if show_intel else ""
            )
            line = (
                f"  {model['provider']:<16} "
                f"{model['name']:<36} "
                f"{self._formatter.cost(value=model['input_cost']):>8} "
                f"{self._formatter.cost(value=model['output_cost']):>8} "
                f"{self._formatter.context(tokens=model['context']):>9} "
                f"{self._formatter.flags(model=model):<4}"
                f"{intel_cell} "
                f"{score_text:>7}"
            )
            Console.primary(line)
            print()


class ModelJsonPrinter(ModelPrinter):
    """Print models as JSON."""

    def render(self, *, models, title="", show_intel=False):
        """Print models as JSON; title and show_intel are not serialized."""
        output = []
        for model in models:
            output.append({
                "provider": model["provider"],
                "id": model["id"],
                "name": model["name"],
                "input_cost": model["input_cost"],
                "output_cost": model["output_cost"],
                "context": model["context"],
                "reasoning": model["reasoning"],
                "tool_call": model["tool_call"],
                "structured_output": model["structured_output"],
                "attachment": model["attachment"],
                "intelligence": model.get("intelligence"),
                "score": round(self._formatter.score(model=model), 2),
            })
        print(json.dumps(output, indent=2))


class ModelMarkdownPrinter(ModelPrinter):
    """Print models as a markdown table."""

    def render(self, *, models, title="", show_intel=False):
        """Print models as a markdown table."""
        if not models:
            print("*No models match the given filters.*")
            return
        print(f"## {title}\n")
        header = ["Provider", "Model", "In", "Out", "Context", "Cap"]
        if show_intel:
            header.append("Intel")
        header.append("Score")
        print("| " + " | ".join(header) + " |")
        print("|" + "---|" * len(header))
        for model in models:
            score = self._formatter.score(model=model)
            score_text = f"{score:.2f}" if score > 0 else "-"
            cells = [
                model["provider"],
                model["name"],
                self._formatter.cost(value=model["input_cost"]),
                self._formatter.cost(value=model["output_cost"]),
                self._formatter.context(tokens=model["context"]),
                self._formatter.flags(model=model),
            ]
            if show_intel:
                cells.append(self._formatter.intelligence(model=model))
            cells.append(score_text)
            print("| " + " | ".join(cells) + " |")
        print()


class ModelCsvPrinter(ModelPrinter):
    """Print models as CSV."""

    HEADER = (
        "provider,model,input_cost,output_cost,context,reasoning,tool_call,"
        "structured_output,attachment,intelligence,score"
    )

    def render(self, *, models, title="", show_intel=False):
        """Print models as CSV; title and show_intel are not serialized."""
        if not models:
            return
        print(ModelCsvPrinter.HEADER)
        for model in models:
            score = self._formatter.score(model=model)
            score_text = f"{score:.2f}" if score > 0 else ""
            intelligence = model.get("intelligence")
            intelligence_text = "" if intelligence is None else f"{intelligence:.1f}"
            print(
                f"{model['provider']},{model['name']},{model['input_cost']},"
                f"{model['output_cost']},{model['context']},{model['reasoning']},"
                f"{model['tool_call']},{model['structured_output']},{model['attachment']},"
                f"{intelligence_text},{score_text}"
            )

#--------------------------------------------------
# Printers: OpenCode Go output
#--------------------------------------------------


class GoPrinter(ABC):
    """Render OpenCode Go models in one output format."""

    def __init__(self, *, formatter=None):
        self._formatter = formatter if formatter is not None else ModelFormatter()

    @abstractmethod
    def render(self, *, models, show_intel=False, value_score=False):
        """Write the Go models to stdout."""


class GoTablePrinter(GoPrinter):
    """Print OpenCode Go models as a formatted table."""

    def render(self, *, models, show_intel=False, value_score=False):
        """Print OpenCode Go models as a formatted table."""
        if not models:
            Console.warning("No Go models found.\n")
            return
        Console.alert_info("OpenCode Go — Requests per 5h window")
        intel_head = f" {'Intel':>6}" if show_intel else ""
        intel_rule = f" {'-' * 6}" if show_intel else ""
        header = (
            f"  {'Model':<36} {'Requests':>10} {'In':>8} {'Out':>8} {'Context':>9} {'Cap':<4}"
            f"{intel_head} {'Score':>7}"
        )
        Console.secondary(header)
        print()
        rule = (
            f"  {'-' * 36} {'-' * 10} {'-' * 8} {'-' * 8} {'-' * 9} {'-' * 4}"
            f"{intel_rule} {'-' * 7}"
        )
        Console.secondary(rule)
        print()
        scores = self._formatter.go_scores(models=models, value_score=value_score)
        for model, value in zip(models, scores):
            score_text = self._formatter.go_score(value=value, value_score=value_score, empty="-")
            intel_cell = (
                f" {self._formatter.intelligence(model=model):>6}" if show_intel else ""
            )
            line = (
                f"  {model['name']:<36} "
                f"{self._formatter.requests(model=model):>10} "
                f"{self._formatter.cost(value=model['input_cost']):>8} "
                f"{self._formatter.cost(value=model['output_cost']):>8} "
                f"{self._formatter.context(tokens=model['context']):>9} "
                f"{self._formatter.flags(model=model):<4}"
                f"{intel_cell} "
                f"{score_text:>7}"
            )
            Console.primary(line)
            print()
        url = GoFetcher.URL
        hyperlink = f"\033]8;;{url}\033\\Source: {url}\033]8;;\033\\"
        print(f"  {hyperlink}")
        print()


class GoJsonPrinter(GoPrinter):
    """Print OpenCode Go models as JSON."""

    def render(self, *, models, show_intel=False, value_score=False):
        """Print OpenCode Go models as JSON; show_intel is not serialized."""
        output = []
        scores = self._formatter.go_scores(models=models, value_score=value_score)
        for model, value in zip(models, scores):
            if value_score:
                score_output = None if value == 0 else round(value, 4)
            else:
                score_output = round(value, 2)
            output.append({
                "id": model["id"],
                "name": model["name"],
                "requests": None if model.get("unlimited") else model["requests"],
                "unlimited": model.get("unlimited", False),
                "input_cost": model["input_cost"],
                "output_cost": model["output_cost"],
                "context": model["context"],
                "reasoning": model["reasoning"],
                "tool_call": model["tool_call"],
                "structured_output": model["structured_output"],
                "attachment": model["attachment"],
                "intelligence": model.get("intelligence"),
                "score": score_output,
            })
        print(json.dumps(output, indent=2))


class GoMarkdownPrinter(GoPrinter):
    """Print OpenCode Go models as a markdown table."""

    def render(self, *, models, show_intel=False, value_score=False):
        """Print OpenCode Go models as a markdown table."""
        if not models:
            print("*No Go models found.*")
            return
        print("## OpenCode Go — Requests per 5h window\n")
        header = ["Model", "Requests", "In", "Out", "Context", "Cap"]
        if show_intel:
            header.append("Intel")
        header.append("Score")
        print("| " + " | ".join(header) + " |")
        print("|" + "---|" * len(header))
        scores = self._formatter.go_scores(models=models, value_score=value_score)
        for model, value in zip(models, scores):
            score_text = self._formatter.go_score(value=value, value_score=value_score, empty="-")
            cells = [
                model["name"],
                self._formatter.requests(model=model),
                self._formatter.cost(value=model["input_cost"]),
                self._formatter.cost(value=model["output_cost"]),
                self._formatter.context(tokens=model["context"]),
                self._formatter.flags(model=model),
            ]
            if show_intel:
                cells.append(self._formatter.intelligence(model=model))
            cells.append(score_text)
            print("| " + " | ".join(cells) + " |")
        print()
        print(f"Source: {GoFetcher.URL}")
        print()


class GoCsvPrinter(GoPrinter):
    """Print OpenCode Go models as CSV."""

    HEADER = (
        "model,requests,input_cost,output_cost,context,reasoning,tool_call,"
        "structured_output,attachment,intelligence,score"
    )

    def render(self, *, models, show_intel=False, value_score=False):
        """Print OpenCode Go models as CSV; show_intel is not serialized."""
        if not models:
            return
        print(GoCsvPrinter.HEADER)
        scores = self._formatter.go_scores(models=models, value_score=value_score)
        for model, value in zip(models, scores):
            score_text = self._formatter.go_score(value=value, value_score=value_score, empty="")
            requests_value = "unlimited" if model.get("unlimited") else model["requests"]
            intelligence = model.get("intelligence")
            intelligence_text = "" if intelligence is None else f"{intelligence:.1f}"
            print(
                f"{model['name']},{requests_value},{model['input_cost']},"
                f"{model['output_cost']},{model['context']},{model['reasoning']},"
                f"{model['tool_call']},{model['structured_output']},{model['attachment']},"
                f"{intelligence_text},{score_text}"
            )

#--------------------------------------------------
# Printers: provider output
#--------------------------------------------------


class ProviderCatalog:
    """Normalize the provider catalog for display."""

    @staticmethod
    def entries(*, catalog):
        """Return provider entries sorted alphabetically by name."""
        providers = []
        for provider_id, provider in catalog.items():
            providers.append({
                "id": provider_id,
                "name": provider.get("name", provider_id),
                "models": len(provider.get("models", {})),
            })
        providers.sort(key=lambda provider: provider["name"].lower())
        return providers


class ProviderPrinter(ABC):
    """Render the provider catalog in one output format."""

    @abstractmethod
    def render(self, *, catalog):
        """Write the providers to stdout."""


class ProviderTablePrinter(ProviderPrinter):
    """Print available providers as a formatted table."""

    def render(self, *, catalog):
        """Print available providers as a formatted table."""
        providers = ProviderCatalog.entries(catalog=catalog)
        Console.alert_info("Available Providers")
        header = f"  {'ID':<30} {'Name':<30} {'Models':>7}"
        Console.secondary(header)
        print()
        Console.secondary(f"  {'-' * 30} {'-' * 30} {'-' * 7}")
        print()
        for provider in providers:
            line = f"  {provider['id']:<30} {provider['name']:<30} {provider['models']:>7}"
            Console.primary(line)
            print()


class ProviderJsonPrinter(ProviderPrinter):
    """Print available providers as JSON."""

    def render(self, *, catalog):
        """Print available providers as JSON."""
        print(json.dumps(ProviderCatalog.entries(catalog=catalog), indent=2))


class ProviderMarkdownPrinter(ProviderPrinter):
    """Print available providers as a markdown table."""

    def render(self, *, catalog):
        """Print available providers as a markdown table."""
        providers = ProviderCatalog.entries(catalog=catalog)
        print("## Available Providers\n")
        print("| ID | Name | Models |")
        print("|---|---|---|")
        for provider in providers:
            print(f"| {provider['id']} | {provider['name']} | {provider['models']} |")
        print()


class ProviderCsvPrinter(ProviderPrinter):
    """Print available providers as CSV."""

    HEADER = "id,name,models"

    def render(self, *, catalog):
        """Print available providers as CSV."""
        providers = ProviderCatalog.entries(catalog=catalog)
        print(ProviderCsvPrinter.HEADER)
        for provider in providers:
            print(f"{provider['id']},{provider['name']},{provider['models']}")

#--------------------------------------------------
# Output selection
#--------------------------------------------------


class OutputFormat:
    """Map CLI output flags to printer registry keys."""

    FORMATS = (
        ("csv_output", "csv"),
        ("md_output", "markdown"),
        ("json_output", "json"),
    )
    DEFAULT = "table"
    MACHINE_FORMATS = ("csv", "json")

    @classmethod
    def select(cls, *, args):
        """Return the format key selected by the output flags."""
        for attribute, name in cls.FORMATS:
            if getattr(args, attribute, False):
                return name
        return cls.DEFAULT

    @classmethod
    def is_machine(cls, *, name):
        """Return whether a format is intended for machine consumption."""
        return name in cls.MACHINE_FORMATS


class ModelOutput:
    """Render models in the format selected by the CLI flags."""

    def __init__(self, *, formatter=None):
        formatter = formatter if formatter is not None else ModelFormatter()
        self._printers = {
            "table": ModelTablePrinter(formatter=formatter),
            "json": ModelJsonPrinter(formatter=formatter),
            "markdown": ModelMarkdownPrinter(formatter=formatter),
            "csv": ModelCsvPrinter(formatter=formatter),
        }

    def render(self, *, args, models, title):
        """Render models and the intelligence attribution credit."""
        name = OutputFormat.select(args=args)
        self._printers[name].render(models=models, title=title, show_intel=True)
        IntelligenceAttribution.show(
            models=models,
            machine_output=OutputFormat.is_machine(name=name),
        )


class GoOutput:
    """Render Go models in the format selected by the CLI flags."""

    def __init__(self, *, formatter=None):
        formatter = formatter if formatter is not None else ModelFormatter()
        self._printers = {
            "table": GoTablePrinter(formatter=formatter),
            "json": GoJsonPrinter(formatter=formatter),
            "markdown": GoMarkdownPrinter(formatter=formatter),
            "csv": GoCsvPrinter(formatter=formatter),
        }

    def render(self, *, args, models):
        """Render Go models and the intelligence attribution credit."""
        name = OutputFormat.select(args=args)
        self._printers[name].render(
            models=models,
            show_intel=True,
            value_score=args.value,
        )
        IntelligenceAttribution.show(
            models=models,
            machine_output=OutputFormat.is_machine(name=name),
        )


class ProviderOutput:
    """Render providers in the format selected by the CLI flags."""

    def __init__(self):
        self._printers = {
            "table": ProviderTablePrinter(),
            "json": ProviderJsonPrinter(),
            "markdown": ProviderMarkdownPrinter(),
            "csv": ProviderCsvPrinter(),
        }

    def render(self, *, args, catalog):
        """Render the provider catalog."""
        name = OutputFormat.select(args=args)
        self._printers[name].render(catalog=catalog)

#--------------------------------------------------
# Kernel
#--------------------------------------------------


class Kernel(ABC):
    """CLI application with metadata, parsing, and error handling."""

    def __init__(self, *, author, title, description):
        self.author = author
        self.title = title
        self.description = description
        self.script_file = Path(sys.argv[0]).resolve()
        self.name = self.script_file.stem
        self.quiet = False
        self.logger = None
        self.args = None

    def build_early_parser(self):
        """Build parser for early arguments (before required input)."""
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument('--log', action='store_true')
        parser.add_argument('--verbose', '-v', action='count', default=0)
        parser.add_argument(
            '--quiet',
            action='store_true',
            help='Suppress non-error output; runtime errors are still reported',
        )
        parser.add_argument(
            '--completion',
            action='store_true',
            help='Print bash completion script to stdout and exit',
        )
        return parser

    @abstractmethod
    def build_parser(self):
        """Build and return the argument parser."""

    def hero(self):
        """Print hero to the terminal."""
        Console.alert_primary(self.title)

    def generate_completion(self):
        """Return the bash completion script for this script."""
        return Completion.generate(parser=self.build_parser(), name=self.name)

    def _handle_early_arguments(self):
        """Handle options that must run before the required input is parsed."""
        early_args, _ = self.build_early_parser().parse_known_args()
        self.quiet = early_args.quiet
        Console.quiet = early_args.quiet
        self.logger = Logger(
            verbose=early_args.verbose,
            script_file=self.script_file,
            quiet=early_args.quiet,
        )
        if not self.quiet and early_args.verbose >= 1:
            self.hero()
        if early_args.completion:
            print(self.generate_completion())
            return True
        if early_args.log:
            self.logger.print()
            return True
        return False

    def run(self):
        """Run the application and translate failures into exit codes."""
        if self._handle_early_arguments():
            return
        self.args = self.build_parser().parse_args()
        try:
            self.execute()
        except FileNotFoundError as err:
            Console.error(str(err))
            sys.exit(1)
        except Exception as err:  # noqa: BLE001
            Console.error(f"{type(err).__name__}: {err}")
            sys.exit(1)

    @abstractmethod
    def execute(self):
        """Implement application logic."""

#--------------------------------------------------
# App
#--------------------------------------------------


class App(Kernel):
    """Recommend OpenCode models by cost, value, or quality."""

    EPILOG = (
        "Intel: BenchLM composite intelligence score (0-100); --value ranks by "
        "intelligence per dollar, --best by intelligence. Cap flags: R=Reasoning, "
        "T=Tool calling, S=Structured output, A=Attachment support."
    )

    def build_parser(self):
        """Build and return the argument parser."""
        parser = argparse.ArgumentParser(
            description=self.description,
            epilog=App.EPILOG,
        )
        mode = parser.add_mutually_exclusive_group(required=False)
        mode.add_argument(
            '--cheapest',
            action='store_true',
            help='Show cheapest non-free models',
        )
        mode.add_argument(
            '--free',
            action='store_true',
            help='Show only free models (sorted by intelligence)',
        )
        mode.add_argument(
            '--value',
            action='store_true',
            help='Show best intelligence-per-dollar models (BenchLM)',
        )
        mode.add_argument(
            '--best',
            action='store_true',
            help='Show most intelligent models (BenchLM)',
        )
        mode.add_argument(
            '--released',
            action='store_true',
            help='Show most recently released models',
        )
        mode.add_argument(
            '--updated',
            action='store_true',
            help='Show most recently updated models',
        )
        mode.add_argument(
            '--providers',
            action='store_true',
            help='List available providers and exit',
        )
        parser.add_argument(
            '--go',
            action='store_true',
            help='Show OpenCode Go usage limits (requests per 5h window)',
        )
        parser.add_argument(
            '--provider',
            default='opencode',
            help='Filter by provider name (default: opencode)',
        )
        parser.add_argument(
            '--min-context',
            type=int,
            default=0,
            help='Minimum context window (tokens)',
        )
        parser.add_argument(
            '--tool-call',
            action='store_true',
            help='Only models supporting tool calling',
        )
        parser.add_argument(
            '--reasoning',
            action='store_true',
            help='Only models supporting reasoning',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=10,
            help='Max results to show (default: 10)',
        )
        parser.add_argument(
            '--cache',
            action='store_true',
            help='Clear the cache before fetching',
        )
        parser.add_argument(
            '--json',
            action='store_true',
            dest='json_output',
            help='Output JSON format',
        )
        parser.add_argument(
            '--md',
            action='store_true',
            dest='md_output',
            help='Output markdown table',
        )
        parser.add_argument(
            '--csv',
            action='store_true',
            dest='csv_output',
            help='Output comma-separated values',
        )
        parser.add_argument(
            '--log',
            action='store_true',
            help='Output log file to terminal',
        )
        parser.add_argument(
            '--verbose',
            '-v',
            action='count',
            default=0,
            help='Increase verbosity (stackable)',
        )
        parser.add_argument(
            '--quiet',
            action='store_true',
            help='Suppress non-error output; runtime errors are still reported',
        )
        parser.add_argument(
            '--completion',
            action='store_true',
            help='Print bash completion script to stdout and exit',
        )
        return parser

    def execute(self):
        """Fetch models, filter, sort, and display."""
        transport = HttpTransport()
        models_cache = Cache()
        go_cache = Cache()
        benchlm_cache = Cache()
        if self.args.cache:
            models_cache.clear()
            go_cache.clear()
            benchlm_cache.clear()
            self.logger.info("Cleared cache")
        models_fetcher = ModelsDevFetcher(
            transport=transport,
            cache=models_cache,
            logger=self.logger,
        )
        go_fetcher = GoFetcher(
            transport=transport,
            cache=go_cache,
            logger=self.logger,
        )
        intelligence_fetcher = BenchLmFetcher(
            transport=transport,
            cache=benchlm_cache,
            logger=self.logger,
        )
        if self.args.go:
            self._execute_go(
                go_fetcher=go_fetcher,
                models_fetcher=models_fetcher,
                intelligence_fetcher=intelligence_fetcher,
            )
            return
        catalog = models_fetcher.fetch()
        if self.args.providers:
            self._execute_providers(catalog=catalog)
            return
        self._execute_models(catalog=catalog, intelligence_fetcher=intelligence_fetcher)

    def _execute_go(self, *, go_fetcher, models_fetcher, intelligence_fetcher):
        """Fetch and display OpenCode Go usage limits."""
        go_models = go_fetcher.fetch()
        catalog = models_fetcher.fetch()
        catalog_merger = ModelCatalog(logger=self.logger)
        merged = catalog_merger.merge_go(go_models=go_models, catalog=catalog)
        intelligence_needed = self.args.value or self.args.best
        entries = intelligence_fetcher.fetch(required=intelligence_needed)
        merged = IntelligenceMatcher.attach(models=merged, entries=entries or [])
        sorter = ModelSorter()
        if self.args.best:
            merged = sorter.best(models=merged)
        elif self.args.value:
            merged = sorter.value_go(models=merged)
        GoOutput().render(args=self.args, models=merged)

    def _execute_providers(self, *, catalog):
        """Display available providers."""
        ProviderOutput().render(args=self.args, catalog=catalog)

    def _execute_models(self, *, catalog, intelligence_fetcher):
        """Filter, sort, and display models."""
        catalog_merger = ModelCatalog(logger=self.logger)
        models = catalog_merger.flatten(catalog=catalog)
        self.logger.info(f"Flattened {len(models)} total models")
        models = ModelFilter.apply(
            models=models,
            exclude_free=self.args.cheapest,
            provider=self.args.provider,
            min_context=self.args.min_context,
            tool_call=self.args.tool_call,
            reasoning=self.args.reasoning,
            free_only=self.args.free,
        )
        self.logger.info(f"After filtering: {len(models)} models")
        intelligence_needed = self.args.free or self.args.value or self.args.best
        entries = intelligence_fetcher.fetch(required=intelligence_needed)
        models = IntelligenceMatcher.attach(models=models, entries=entries or [])
        sorter = ModelSorter()
        if self.args.free:
            models = sorter.value(models=models)
            title = "Free Models"
        elif self.args.cheapest:
            models = sorter.cheapest(models=models)
            title = "Cheapest Models (non-free)"
        elif self.args.value:
            models = sorter.value(models=models)
            title = "Best Intelligence-per-Dollar Models"
        elif self.args.best:
            models = sorter.best(models=models)
            title = "Most Intelligent Models"
        elif self.args.released:
            models = sorter.released(models=models)
            title = "Most Recently Released Models"
        else:
            models = sorter.updated(models=models)
            title = "Most Recently Updated Models"
        models = models[:self.args.limit]
        ModelOutput().render(args=self.args, models=models, title=title)


if __name__ == '__main__':
    app = App(
        author='TangoMan75',
        title='OpenCode Models',
        description='Recommend OpenCode models by cost, value, or quality',
    )
    app.run()
