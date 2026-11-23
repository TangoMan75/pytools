#!/usr/bin/env python3
"""Show current OVHcloud TLD creation and renewal prices."""

import argparse
import csv
import datetime
import json
import re
import shlex
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
# Transport: HTTPS page fetching
#--------------------------------------------------


class HttpTransport:
    """Fetch page bodies over HTTPS."""

    USER_AGENT = "TangoMan75-ovhcloud/1.0 (+https://github.com/TangoMan75/pytools)"
    ENCODING = "utf-8"

    def fetch_text(self, *, url, timeout):
        """Fetch a URL and return the response body decoded as text."""
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": HttpTransport.USER_AGENT,
                "Accept-Language": "fr-FR,fr;q=0.9",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or HttpTransport.ENCODING
            return response.read().decode(charset)

#--------------------------------------------------
# Parser: OVHcloud TLD prices
#--------------------------------------------------


class DrupalSettingsParser(HTMLParser):
    """Collect the JSON payloads embedded in Drupal settings script tags."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.scripts = []
        self._buffer = None

    def handle_starttag(self, tag, attrs):
        """Start collecting a settings script body."""
        if tag != "script":
            return
        if dict(attrs).get("data-drupal-selector") != "drupal-settings-json":
            return
        self._buffer = []

    def handle_data(self, data):
        """Append script text while a settings script is open."""
        if self._buffer is not None:
            self._buffer.append(data)

    def handle_endtag(self, tag):
        """Finish collecting the current settings script body."""
        if tag == "script" and self._buffer is not None:
            self.scripts.append("".join(self._buffer))
            self._buffer = None


class OvhTldParser:
    """Extract TLD creation and renewal prices from an OVHcloud page."""

    SETTINGS_KEY = "ovh_domain_names"
    PRICES_KEY = "pricesData"

    @classmethod
    def parse(cls, *, html):
        """Return the TLD price entries sorted by extension."""
        prices = cls._prices_data(html=html)
        entries = []
        for extension, item in prices.items():
            if not isinstance(item, dict):
                continue
            creation = item.get("data-installation-price")
            renewal = item.get("data-renew-price")
            if not isinstance(creation, (int, float)) or not isinstance(renewal, (int, float)):
                continue
            name = str(item.get("data-extension-name") or extension).strip()
            if not name:
                continue
            tld = name if name.startswith(".") else f".{name}"
            entries.append({
                "tld": tld,
                "creation": float(creation),
                "renewal": float(renewal),
            })
        if not entries:
            raise ValueError("No valid TLD prices found in page")
        entries.sort(key=lambda entry: entry["tld"].lower())
        return entries

    @classmethod
    def _prices_data(cls, *, html):
        """Return the ``pricesData`` mapping from the page settings."""
        settings = DrupalSettingsParser()
        settings.feed(html)
        for payload in settings.scripts:
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue
            domain_names = data.get(cls.SETTINGS_KEY)
            if not isinstance(domain_names, dict):
                continue
            prices = domain_names.get(cls.PRICES_KEY)
            if isinstance(prices, dict) and prices:
                return prices
        raise ValueError("OVHcloud TLD prices not found in page")

#--------------------------------------------------
# Fetcher: OVHcloud TLD prices
#--------------------------------------------------


class OvhTldFetcher:
    """Fetch the current OVHcloud TLD price list."""

    URL = "https://www.ovhcloud.com/fr/domains/tld/"
    TIMEOUT = 30

    def __init__(self, *, transport, logger=None):
        self._transport = transport
        self._logger = logger if logger is not None else NullLogger()

    def fetch(self):
        """Fetch and parse the TLD price list."""
        self._logger.info(f"Fetching {OvhTldFetcher.URL}")
        try:
            html = self._transport.fetch_text(
                url=OvhTldFetcher.URL,
                timeout=OvhTldFetcher.TIMEOUT,
            )
        except (urllib.error.URLError, OSError) as err:
            Console.error(f"Failed to fetch OVHcloud TLD prices: {err}")
            sys.exit(1)
        try:
            tlds = OvhTldParser.parse(html=html)
        except ValueError as err:
            Console.error(f"Failed to parse OVHcloud TLD prices: {err}")
            sys.exit(1)
        self._logger.success(f"Loaded {len(tlds)} TLD prices")
        return tlds

#--------------------------------------------------
# Formatter: TLD prices
#--------------------------------------------------


class TldFormatter:
    """Format TLD price values."""

    @staticmethod
    def price(value):
        """Format a price in euros with two decimals."""
        return f"{float(value):.2f}"

#--------------------------------------------------
# Printers: TLD prices
#--------------------------------------------------


class TldTablePrinter:
    """Print TLD prices as a formatted text table."""

    HEADER = f"  {'Extension':<25} {'Creation':>10} {'Renewal':>10}"

    def __init__(self, *, formatter=None):
        self._formatter = formatter if formatter is not None else TldFormatter()

    def render(self, *, tlds):
        """Print TLD prices as a formatted table."""
        if not tlds:
            Console.warning("No TLD prices found.\n")
            return
        Console.alert_info("OVHcloud TLD prices (EUR per year)")
        Console.secondary(TldTablePrinter.HEADER)
        print()
        Console.secondary(f"  {'-' * 25} {'-' * 10} {'-' * 10}")
        print()
        for entry in tlds:
            line = (
                f"  {entry['tld']:<25} "
                f"{self._formatter.price(entry['creation']):>10} "
                f"{self._formatter.price(entry['renewal']):>10}"
            )
            Console.primary(line)
            print()


class TldMarkdownPrinter:
    """Print TLD prices as a markdown table."""

    TITLE = "OVHcloud TLD prices (EUR per year)"

    def __init__(self, *, formatter=None):
        self._formatter = formatter if formatter is not None else TldFormatter()

    def render(self, *, tlds):
        """Print TLD prices as a markdown table."""
        if not tlds:
            print("*No TLD prices found.*")
            return
        print(f"## {TldMarkdownPrinter.TITLE}\n")
        print("| Extension | Creation | Renewal |")
        print("|---|---:|---:|")
        for entry in tlds:
            creation = self._formatter.price(entry["creation"])
            renewal = self._formatter.price(entry["renewal"])
            print(f"| {entry['tld']} | {creation} | {renewal} |")
        print()


class TldCsvPrinter:
    """Print TLD prices as comma-separated values."""

    HEADER = ("tld", "creation_eur", "renewal_eur")

    def __init__(self, *, formatter=None):
        self._formatter = formatter if formatter is not None else TldFormatter()

    def render(self, *, tlds):
        """Print TLD prices as CSV."""
        writer = csv.writer(sys.stdout, lineterminator="\n")
        writer.writerow(TldCsvPrinter.HEADER)
        for entry in tlds:
            writer.writerow([
                entry["tld"],
                self._formatter.price(entry["creation"]),
                self._formatter.price(entry["renewal"]),
            ])

#--------------------------------------------------
# Output selection
#--------------------------------------------------


class OutputFormat:
    """Map CLI output flags to printer registry keys."""

    FORMATS = (
        ("csv_output", "csv"),
        ("md_output", "markdown"),
    )
    DEFAULT = "table"

    @classmethod
    def select(cls, *, args):
        """Return the format key selected by the output flags."""
        for attribute, name in cls.FORMATS:
            if getattr(args, attribute, False):
                return name
        return cls.DEFAULT


class TldOutput:
    """Render TLD prices in the format selected by the CLI flags."""

    def __init__(self, *, formatter=None):
        formatter = formatter if formatter is not None else TldFormatter()
        self._printers = {
            "table": TldTablePrinter(formatter=formatter),
            "markdown": TldMarkdownPrinter(formatter=formatter),
            "csv": TldCsvPrinter(formatter=formatter),
        }

    def render(self, *, args, tlds):
        """Render TLD prices."""
        name = OutputFormat.select(args=args)
        self._printers[name].render(tlds=tlds)

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
        """Build parser for early arguments (before the main parser)."""
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
        """Handle options that must run before the main arguments are parsed."""
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
    """Show current OVHcloud TLD creation and renewal prices."""

    def build_parser(self):
        """Build and return the argument parser."""
        parser = argparse.ArgumentParser(description=self.description)
        formats = parser.add_mutually_exclusive_group()
        formats.add_argument(
            '--md',
            action='store_true',
            dest='md_output',
            help='Output a markdown table',
        )
        formats.add_argument(
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
        """Fetch and display the current TLD prices."""
        fetcher = OvhTldFetcher(
            transport=HttpTransport(),
            logger=self.logger,
        )
        tlds = fetcher.fetch()
        TldOutput().render(args=self.args, tlds=tlds)


if __name__ == '__main__':
    app = App(
        author='TangoMan75',
        title='OVHcloud TLD prices',
        description='Show current OVHcloud TLD creation and renewal prices.',
    )
    app.run()
