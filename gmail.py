#!/usr/bin/env python3
"""List or read Gmail messages through the ``gws`` command."""

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

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
# GmailDate: validate and format search dates
#--------------------------------------------------


class GmailDate:
    """Parse ``YYYY-MM-DD`` values and render Gmail's search form."""

    DATE_FORMAT = "%Y-%m-%d"
    SEARCH_FORMAT = "%Y/%m/%d"

    @classmethod
    def parse(cls, *, value):
        """Validate a ``YYYY-MM-DD`` string and return it unchanged."""
        try:
            return datetime.strptime(value, cls.DATE_FORMAT).date().isoformat()
        except ValueError:
            raise ValueError(
                f"invalid date '{value}', expected YYYY-MM-DD"
            ) from None

    @classmethod
    def search_value(cls, *, value):
        """Format a validated date as Gmail's ``YYYY/MM/DD`` value."""
        return datetime.strptime(value, cls.DATE_FORMAT).strftime(cls.SEARCH_FORMAT)

    @classmethod
    def next_day(cls, *, value):
        """Return the calendar day after a validated ``YYYY-MM-DD`` date."""
        return (
            datetime.strptime(value, cls.DATE_FORMAT) + timedelta(days=1)
        ).date().isoformat()

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
# GmailClient: list, fetch, and read messages
#--------------------------------------------------


class GmailClient:
    """Talk to the Gmail API through the gws command."""

    USER_ID = "me"
    METADATA_HEADERS = ("From", "To", "Subject", "Date")

    def __init__(self, *, runner=None):
        self._runner = runner if runner is not None else GwsCommandRunner()

    def list_message_ids(self, *, query, max_results):
        """Page through ``messages.list`` and return every ``{id, threadId}``."""
        out = []
        page_token = None
        while True:
            params = {
                "userId": GmailClient.USER_ID,
                "q": query,
                "maxResults": max_results,
            }
            if page_token:
                params["pageToken"] = page_token
            raw = self._runner.run(
                args=["gmail", "users", "messages", "list", "--params", json.dumps(params)]
            )
            data = json.loads(raw)
            if not isinstance(data, dict):
                break
            for message in data.get("messages") or []:
                if message.get("id"):
                    out.append(message)
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return out

    def get_message(self, *, message_id):
        """Fetch a single message with ``format=metadata`` (headers only)."""
        raw = self._runner.run(
            args=[
                "gmail", "users", "messages", "get",
                "--params", json.dumps({
                    "userId": GmailClient.USER_ID,
                    "id": message_id,
                    "format": "metadata",
                    "metadataHeaders": list(GmailClient.METADATA_HEADERS),
                }),
            ]
        )
        return json.loads(raw)

    def read_message(self, *, message_id):
        """Read one message through ``gws gmail +read`` as JSON."""
        raw = self._runner.run(
            args=["gmail", "+read", "--id", message_id, "--headers"]
        )
        return json.loads(raw)

#--------------------------------------------------
# GmailQuery: build the search expression
#--------------------------------------------------


class GmailQuery:
    """Format a date window and optional filters as a Gmail ``q`` query."""

    @staticmethod
    def label(*, value):
        """Format a label for inclusion in a Gmail ``q`` query."""
        label = (value or "").strip()
        if not label:
            return ""
        if any(character.isspace() for character in label):
            return f'label:"{label}"'
        return f"label:{label}"

    @staticmethod
    def address(*, operator, value):
        """Format a sender or recipient for Gmail's ``from:``/``to:`` query."""
        address = (value or "").strip()
        if not address:
            return ""
        if any(character.isspace() for character in address):
            return f'{operator}:"{address}"'
        return f"{operator}:{address}"

    @classmethod
    def build(cls, *, start, end, sender=None, recipient=None, label=None):
        """Build the Gmail search expression for an inclusive date window."""
        parts = [
            f"after:{GmailDate.search_value(value=start)}",
            f"before:{GmailDate.search_value(value=GmailDate.next_day(value=end))}",
        ]
        if sender and sender.strip():
            parts.append(cls.address(operator="from", value=sender))
        if recipient and recipient.strip():
            parts.append(cls.address(operator="to", value=recipient))
        if label and label.strip():
            parts.append(cls.label(value=label))
        return " ".join(parts)

#--------------------------------------------------
# MessageParser: read fields from message payloads
#--------------------------------------------------


class MessageParser:
    """Read header and sender fields out of Gmail message payloads."""

    @staticmethod
    def header(*, headers, name):
        """Look up a header value (case-insensitive) in a Gmail payload."""
        target = name.lower()
        for header in headers or []:
            if (header.get("name") or "").lower() == target:
                return header.get("value") or ""
        return ""

    @staticmethod
    def format_date(*, value):
        """Render a Gmail Date header as ``YYYY-MM-DD HH:MM`` when possible."""
        if not value:
            return ""
        try:
            return parsedate_to_datetime(value).strftime("%Y-%m-%d %H:%M")
        except (TypeError, ValueError):
            return value

    @staticmethod
    def clean_subject(*, value):
        """Normalize a Subject header for display and markdown headings."""
        subject = (value or "").strip()
        return subject or "(no subject)"

    @staticmethod
    def sender(*, message):
        """Return ``(name, email)`` of the sender from a ``+read`` payload."""
        from_header = message.get("from") or {}
        if isinstance(from_header, dict):
            return (
                (from_header.get("name") or "").strip(),
                (from_header.get("email") or "").strip(),
            )
        return "", ""

    @staticmethod
    def sort_key(*, message):
        """Return the epoch milliseconds of a ``+read`` payload's Date header."""
        try:
            return int(parsedate_to_datetime(message.get("date") or "").timestamp() * 1000)
        except (TypeError, ValueError, OverflowError):
            return 0

#--------------------------------------------------
# HTML parsers: anchors and visible text
#--------------------------------------------------


class AnchorCollector(HTMLParser):
    """Collect ``(text, href)`` pairs from HTML ``<a>`` tags."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self._href = None
        self._chunks = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        href = None
        for key, value in attrs:
            if key.lower() == "href" and value:
                href = value.strip()
                break
        if href:
            self._href = href
            self._chunks = []

    def handle_data(self, data):
        if self._href is not None:
            self._chunks.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            text = " ".join("".join(self._chunks).split())
            self.links.append((text, self._href))
            self._href = None
            self._chunks = []

    @classmethod
    def collect(cls, *, html):
        """Return anchor pairs from an HTML body, ignoring parse failures."""
        if not html or "<" not in html:
            return []
        parser = cls()
        try:
            parser.feed(html)
            parser.close()
        except Exception:
            return []
        return parser.links


class TextCollector(HTMLParser):
    """Extract visible text from HTML, skipping script/style content."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.chunks = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag.lower() in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._skip:
            return
        text = data.strip()
        if text:
            self.chunks.append(text)

    @classmethod
    def collect(cls, *, html):
        """Return the visible text of an HTML body, ignoring parse failures."""
        if not html:
            return ""
        parser = cls()
        try:
            parser.feed(html)
            parser.close()
        except Exception:
            return ""
        return "\n".join(parser.chunks)

#--------------------------------------------------
# MarkdownRenderer: message front matter and body
#--------------------------------------------------


class MarkdownRenderer:
    """Render Gmail messages as YAML front matter plus body markdown."""

    EMPTY = "_No messages in this range._\n"

    def __init__(self, *, parser=None):
        self._parser = parser if parser is not None else MessageParser()

    @staticmethod
    def _url_mentioned(*, url, text):
        """Whether ``url`` already appears in ``text`` (raw or percent-decoded)."""
        if not url or not text:
            return False
        if url in text:
            return True
        decoded = unquote(url)
        return bool(decoded) and decoded in text

    @staticmethod
    def _link_lines(*, links):
        """Render ``(text, href)`` pairs as markdown list items."""
        return [f"- [{text or href}]({href})" for text, href in links if href]

    def _render_body(self, *, message):
        """Build the markdown body, preserving HTML links missing from text."""
        body_text = (message.get("body_text") or "").strip()
        body_html = (message.get("body_html") or "").strip()
        anchors = AnchorCollector.collect(html=body_html)

        missing = []
        seen = set()
        for text, href in anchors:
            if not href or href.startswith("#"):
                continue
            key = href.rstrip("/")
            if key in seen:
                continue
            seen.add(key)
            if self._url_mentioned(url=href, text=body_text):
                continue
            missing.append((text, href))

        if body_text:
            if not missing:
                return body_text
            return "\n".join(
                [body_text, "", "Links:", *self._link_lines(links=missing)]
            )

        if not body_html:
            return ""

        text = TextCollector.collect(html=body_html)
        if not anchors:
            return text or body_html

        lines = []
        if text:
            lines.append(text)
        if lines:
            lines.append("")
        lines.append("Links:")
        lines.extend(
            self._link_lines(
                links=[
                    (text, href) for text, href in anchors
                    if href and not href.startswith("#")
                ]
            )
        )
        return "\n".join(lines)

    def render_message(self, *, message):
        """Render one message as YAML front matter, a heading, and its body."""
        subject = self._parser.clean_subject(value=message.get("subject"))
        from_name, from_email = self._parser.sender(message=message)
        date_text = self._parser.format_date(value=message.get("date") or "")
        message_id = (message.get("id") or message.get("thread_id") or "").strip()
        front = [
            "---",
            f'- subject: "{subject}"',
            f'- from: "{from_name}"',
            f'- email: "{from_email}"',
            f"- date: {date_text}",
        ]
        if message_id:
            front.append(f'- id: "{message_id}"')
        front.extend([
            "---",
            "",
            f"## {subject}",
            "",
            self._render_body(message=message),
        ])
        return "\n".join(front)

    def render(self, *, messages):
        """Render each message as a front-matter block separated by blank lines."""
        if not messages:
            return MarkdownRenderer.EMPTY
        blocks = [self.render_message(message=message) for message in messages]
        return "\n\n".join(blocks) + "\n"

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
    """Build the gmail argument parser."""

    DESCRIPTION = (
        "gws wrapper: list Gmail messages in a [start, end] window, "
        "optionally filtered by sender, recipient, or label."
    )
    DEFAULT_MAX_RESULTS = 100
    DEFAULT_MAX_MESSAGES = 500
    LONG_DESCRIPTION = """gws wrapper: list Gmail messages in a [start, end] window, optionally filtered by sender, recipient, or label.

This is the Gmail counterpart to ``gcal.py``. It wraps
``gws gmail users messages list``, ``gws gmail users messages get``,
and ``gws gmail +read`` to:

* Filter by date range via Gmail's ``after:`` / ``before:`` search
  operators (which are date-only and use the user's account timezone).
* Filter by label via the ``label:`` operator. The argument can be a
  system name (``INBOX``, ``SENT``), a custom name (``"My Label"``),
  a nested name (``Work/Projects``), or a raw label ID — Gmail's
  search accepts any of these.
* Filter by sender or recipient via Gmail's ``from:`` and ``to:``
  search operators.
* Paginate through the full result set, then fetch each message
  individually with ``format=metadata`` to retrieve the headers
  without the body (much smaller payloads than ``format=full``).
* Read a message's headers and body with ``--read MESSAGE_ID``.

Default output: a JSON array of message objects on stdout. With
``--md``, render each message as a YAML front-matter block (subject,
from name, from email, date) followed by the body. HTML links from
``body_html`` that are missing from ``body_text`` are preserved as a
markdown ``Links:`` section. Combine ``--read MESSAGE_ID`` with ``--md``
to render that single message as markdown instead of JSON.

Date semantics
~~~~~~~~~~~~~~

Gmail's ``after:`` / ``before:`` operators are date-only and
``before:`` is exclusive of its date in the user's account timezone
(i.e. ``before:2024/01/02`` = up to end of Jan 1). To make ``--end``
inclusive of the full day, this script uses ``before:`` with the day
*after* ``--end``. Implications:

* ``--start 2024-01-01 --end 2024-01-07``  -> 00:00:00 Jan 1 through
  23:59:59 Jan 7.
* Gmail does not support sub-day filtering, so ``--start`` / ``--end``
  are whole calendar days in ``YYYY-MM-DD`` format.

Args:
    --start, --end        "YYYY-MM-DD" (local; default: today). Date-only
                          ranges mean 00:00:00 through 23:59:59.
    --from                filter by sender email address or name
    --to                  filter by recipient email address or name
    --read MESSAGE_ID     read one message with headers and body as JSON
                          (or markdown when combined with ``--md``)
    --label               filter by Gmail label (name or ID, e.g.
                          ``INBOX``, ``"My Label"``). If omitted,
                          queries ALL messages in the date range.
    --max-results         max messages per page (default: 100, max: 500)
    --max-messages        hard cap on total messages fetched (default: 500)
    --md                  render each message as front matter + body markdown
                          instead of JSON; HTML links are preserved. With
                          ``--read``, render that message as markdown.
    --quiet               suppress non-error output; runtime errors are still
                          reported and exit 1

Exit codes:
    0  messages fetched (possibly empty list)
    1  gws invocation failed
    2  bad CLI args
"""

    def build(self):
        """Build and return the argument parser."""
        today = datetime.now().date().isoformat()
        parser = argparse.ArgumentParser(description=CliParser.DESCRIPTION)
        parser.add_argument(
            "--start", default=today,
            help=f"inclusive start date YYYY-MM-DD (default: {today})",
        )
        parser.add_argument(
            "--end", default=today,
            help=f"inclusive end date YYYY-MM-DD (default: {today})",
        )
        parser.add_argument(
            "--label", default=None,
            help='filter by Gmail label (name or ID, e.g. INBOX, "My Label"). '
                 "If omitted, queries ALL messages in the date range.",
        )
        parser.add_argument(
            "--from", dest="sender", default=None,
            help="filter by sender email address or name",
        )
        parser.add_argument(
            "--to", dest="recipient", default=None,
            help="filter by recipient email address or name",
        )
        parser.add_argument(
            "--read", dest="read_message_id", default=None, metavar="MESSAGE_ID",
            help="read one message with headers and body as JSON (markdown with --md)",
        )
        parser.add_argument(
            "--max-results", type=int, default=CliParser.DEFAULT_MAX_RESULTS,
            help="max messages per page (default: 100, max: 500)",
        )
        parser.add_argument(
            "--max-messages", type=int, default=CliParser.DEFAULT_MAX_MESSAGES,
            help="hard cap on total messages fetched (default: 500)",
        )
        parser.add_argument(
            "--md", action="store_true",
            help="render front-matter blocks and message bodies instead of JSON; "
                 "HTML links are preserved. With --read, render that message as markdown",
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
    """Run the gmail command and translate failures into exit codes."""

    EXIT_SUCCESS = 0
    EXIT_ERROR = 1
    EXIT_USAGE = 2

    def __init__(self, *, argv=None, runner=None, console=None):
        self._argv = list(sys.argv[1:] if argv is None else argv)
        self._console = console if console is not None else Console()
        self._runner = runner if runner is not None else GwsCommandRunner()
        self._client = GmailClient(runner=self._runner)
        self._renderer = MarkdownRenderer()

    def run(self):
        """Parse the command line, fetch messages, and return an exit code."""
        parser = CliParser().build()
        if "--completion" in self._argv:
            self._console.write(
                Completion.generate(parser=parser, name=self._command_name()) + "\n"
            )
            return Application.EXIT_SUCCESS

        options = parser.parse_args(self._argv)
        if options.read_message_id:
            return self._read(options=options)
        return self._list(options=options)

    @staticmethod
    def _command_name():
        """Return the installed command name derived from argv[0]."""
        return Path(sys.argv[0]).resolve().stem

    def _read(self, *, options):
        """Read one message and write it as JSON or markdown."""
        try:
            message = self._client.read_message(message_id=options.read_message_id)
        except Exception as exc:
            hint = GwsCommandRunner.auth_hint(exc=exc)
            self._console.error(f"gws message read failed: {exc}{hint}")
            return Application.EXIT_ERROR
        if options.md:
            if "id" not in message:
                message = {**message, "id": options.read_message_id}
            self._console.write(self._renderer.render_message(message=message))
        else:
            self._write_json(data=message)
        return Application.EXIT_SUCCESS

    def _list(self, *, options):
        """List messages in the date window and write them as JSON or markdown."""
        try:
            from_date = GmailDate.parse(value=options.start)
            to_date = GmailDate.parse(value=options.end)
        except ValueError as exc:
            self._console.error(str(exc))
            return Application.EXIT_USAGE
        if to_date < from_date:
            self._console.error(f"end {to_date} is before start {from_date}")
            return Application.EXIT_USAGE

        query = GmailQuery.build(
            start=from_date,
            end=to_date,
            sender=options.sender,
            recipient=options.recipient,
            label=options.label,
        )
        try:
            message_refs = self._client.list_message_ids(
                query=query, max_results=options.max_results
            )
        except Exception as exc:
            hint = GwsCommandRunner.auth_hint(exc=exc)
            self._console.error(f"gws messages list failed: {exc}{hint}")
            return Application.EXIT_ERROR

        truncated = False
        if len(message_refs) > options.max_messages:
            truncated = True
            message_refs = message_refs[: options.max_messages]

        messages = []
        for message_ref in message_refs:
            try:
                message = self._fetch_message(
                    message_ref=message_ref, with_body=options.md
                )
            except Exception as exc:
                hint = GwsCommandRunner.auth_hint(exc=exc)
                self._console.warning(
                    f"skipping message {message_ref.get('id')}: {exc}{hint}"
                )
                continue
            messages.append(message)

        if truncated and not options.quiet:
            self._console.warning(
                f"results truncated to --max-messages={options.max_messages} "
                f"(matched {len(message_refs)} before truncation)"
            )

        if options.md:
            messages.sort(key=lambda message: MessageParser.sort_key(message=message))
            self._console.write(self._renderer.render(messages=messages))
        else:
            self._write_json(data=messages)
        return Application.EXIT_SUCCESS

    def _fetch_message(self, *, message_ref, with_body):
        """Fetch one message, adding the id when a markdown body is requested."""
        if with_body:
            message = self._client.read_message(message_id=message_ref["id"])
            if "id" not in message:
                message = {**message, "id": message_ref["id"]}
            return message
        return self._client.get_message(message_id=message_ref["id"])

    def _write_json(self, *, data):
        """Write one JSON document followed by a newline."""
        self._console.write(json.dumps(data, ensure_ascii=False, indent=2))
        self._console.write("\n")


if __name__ == "__main__":
    sys.exit(Application().run())
