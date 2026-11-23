#!/usr/bin/env python3
"""Tests for ovhcloud module."""
# noqa: E402

import csv
import importlib.util
import io
import sys
import unittest
import urllib.error
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1]))

_SPEC = importlib.util.spec_from_file_location(
    "ovhcloud", Path(__file__).parents[1] / "ovhcloud.py"
)
ovhcloud = importlib.util.module_from_spec(_SPEC)
sys.modules["ovhcloud"] = ovhcloud
_SPEC.loader.exec_module(ovhcloud)

FIXTURE = Path(__file__).parent / "fixtures" / "ovhcloud_tld.html"

TLDS = [
    {"tld": ".com", "creation": 8.49, "renewal": 14.29},
    {"tld": ".fr", "creation": 4.99, "renewal": 7.79},
]

#--------------------------------------------------
# Test doubles
#--------------------------------------------------


class FakeTransport:
    """Scripted stand-in for HttpTransport."""

    def __init__(self, *, body):
        self._body = body
        self.calls = []

    def fetch_text(self, *, url, timeout):
        """Record the call and return or raise the scripted body."""
        self.calls.append({"url": url, "timeout": timeout})
        if isinstance(self._body, Exception):
            raise self._body
        return self._body

#--------------------------------------------------
# Parser
#--------------------------------------------------


class TestOvhTldParser(unittest.TestCase):
    """Tests for OvhTldParser."""

    def setUp(self):
        """Load the HTML fixture before each test."""
        self.html = FIXTURE.read_text(encoding="utf-8")

    def test_parses_entries(self):
        """TLD prices are extracted from the Drupal settings payload."""
        result = ovhcloud.OvhTldParser.parse(html=self.html)
        self.assertEqual([entry["tld"] for entry in result], [".asso.fr", ".com", ".fr", ".io"])

    def test_prices_are_numeric(self):
        """Creation and renewal prices are floats taken from the page data."""
        result = ovhcloud.OvhTldParser.parse(html=self.html)
        com = next(entry for entry in result if entry["tld"] == ".com")
        self.assertEqual(com["creation"], 8.49)
        self.assertEqual(com["renewal"], 14.29)

    def test_free_creation_price_is_kept(self):
        """A zero creation price is a valid price and is not skipped."""
        result = ovhcloud.OvhTldParser.parse(html=self.html)
        asso = next(entry for entry in result if entry["tld"] == ".asso.fr")
        self.assertEqual(asso["creation"], 0.0)
        self.assertEqual(asso["renewal"], 6.99)

    def test_incomplete_entries_are_skipped(self):
        """Entries missing a renewal price are ignored."""
        result = ovhcloud.OvhTldParser.parse(html=self.html)
        self.assertNotIn(".broken", [entry["tld"] for entry in result])

    def test_entries_are_sorted_alphabetically(self):
        """TLDs are returned in alphabetical order."""
        result = ovhcloud.OvhTldParser.parse(html=self.html)
        names = [entry["tld"] for entry in result]
        self.assertEqual(names, sorted(names, key=str.lower))

    def test_missing_prices_data_raises(self):
        """A page without the prices payload raises a ValueError."""
        with self.assertRaises(ValueError):
            ovhcloud.OvhTldParser.parse(html="<html><body>nothing here</body></html>")

    def test_empty_prices_data_raises(self):
        """An empty prices payload raises a ValueError."""
        html = (
            '<script type="application/json" data-drupal-selector="drupal-settings-json">'
            '{"ovh_domain_names":{"pricesData":{}}}</script>'
        )
        with self.assertRaises(ValueError):
            ovhcloud.OvhTldParser.parse(html=html)

#--------------------------------------------------
# Fetcher
#--------------------------------------------------


class TestOvhTldFetcher(unittest.TestCase):
    """Tests for OvhTldFetcher."""

    def setUp(self):
        """Load the HTML fixture before each test."""
        self.html = FIXTURE.read_text(encoding="utf-8")

    def test_fetches_and_parses(self):
        """The fetcher requests the OVHcloud page and returns parsed prices."""
        transport = FakeTransport(body=self.html)
        fetcher = ovhcloud.OvhTldFetcher(transport=transport)
        result = fetcher.fetch()
        self.assertEqual(len(result), 4)
        self.assertEqual(transport.calls[0]["url"], ovhcloud.OvhTldFetcher.URL)

    def test_fetch_error_exits(self):
        """A failed page fetch exits with an error."""
        transport = FakeTransport(body=urllib.error.URLError("boom"))
        fetcher = ovhcloud.OvhTldFetcher(transport=transport)
        with self.assertRaises(SystemExit) as context, redirect_stderr(io.StringIO()) as stderr:
            fetcher.fetch()
        self.assertEqual(context.exception.code, 1)
        self.assertIn("Failed to fetch", stderr.getvalue())

    def test_parse_error_exits(self):
        """A page without TLD prices exits with an error."""
        transport = FakeTransport(body="<html></html>")
        fetcher = ovhcloud.OvhTldFetcher(transport=transport)
        with self.assertRaises(SystemExit) as context, redirect_stderr(io.StringIO()) as stderr:
            fetcher.fetch()
        self.assertEqual(context.exception.code, 1)
        self.assertIn("Failed to parse", stderr.getvalue())

#--------------------------------------------------
# Transport
#--------------------------------------------------


class TestHttpTransport(unittest.TestCase):
    """Tests for HttpTransport."""

    def test_fetch_decodes_response(self):
        """The response body is decoded using its declared charset."""
        response = mock.MagicMock()
        response.headers.get_content_charset.return_value = "utf-8"
        response.read.return_value = "8,49 €".encode("utf-8")
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        with mock.patch("urllib.request.urlopen", return_value=response) as opener:
            text = ovhcloud.HttpTransport().fetch_text(url="https://example.test/", timeout=5)
        self.assertEqual(text, "8,49 €")
        self.assertEqual(opener.call_args.kwargs["timeout"], 5)

    def test_sends_user_agent(self):
        """The request identifies the tool with a User-Agent header."""
        response = mock.MagicMock()
        response.headers.get_content_charset.return_value = "utf-8"
        response.read.return_value = b""
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        with mock.patch("urllib.request.urlopen", return_value=response) as opener:
            ovhcloud.HttpTransport().fetch_text(url="https://example.test/", timeout=5)
        request = opener.call_args.args[0]
        self.assertEqual(request.get_header("User-agent"), ovhcloud.HttpTransport.USER_AGENT)

#--------------------------------------------------
# Printers
#--------------------------------------------------


class TestTldTablePrinter(unittest.TestCase):
    """Tests for TldTablePrinter."""

    def test_renders_header_and_rows(self):
        """The table shows extensions, creation prices, and renewal prices."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            ovhcloud.TldTablePrinter().render(tlds=TLDS)
        output = buf.getvalue()
        self.assertIn("Extension", output)
        self.assertIn("Creation", output)
        self.assertIn("Renewal", output)
        self.assertIn(".com", output)
        self.assertIn("8.49", output)
        self.assertIn("14.29", output)

    def test_empty_list_warns(self):
        """An empty list prints a warning instead of a table."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            ovhcloud.TldTablePrinter().render(tlds=[])
        self.assertIn("No TLD prices found", buf.getvalue())


class TestTldMarkdownPrinter(unittest.TestCase):
    """Tests for TldMarkdownPrinter."""

    def test_renders_markdown_table(self):
        """The markdown output contains a heading and price rows."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            ovhcloud.TldMarkdownPrinter().render(tlds=TLDS)
        output = buf.getvalue()
        self.assertIn("## OVHcloud TLD prices", output)
        self.assertIn("| Extension | Creation | Renewal |", output)
        self.assertIn("| .com | 8.49 | 14.29 |", output)

    def test_empty_list_prints_notice(self):
        """An empty list prints a markdown notice."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            ovhcloud.TldMarkdownPrinter().render(tlds=[])
        self.assertIn("No TLD prices found", buf.getvalue())


class TestTldCsvPrinter(unittest.TestCase):
    """Tests for TldCsvPrinter."""

    def test_renders_csv(self):
        """The CSV output has a header and one row per TLD."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            ovhcloud.TldCsvPrinter().render(tlds=TLDS)
        rows = list(csv.reader(io.StringIO(buf.getvalue())))
        self.assertEqual(rows[0], ["tld", "creation_eur", "renewal_eur"])
        self.assertEqual(rows[1], [".com", "8.49", "14.29"])
        self.assertEqual(rows[2], [".fr", "4.99", "7.79"])

    def test_empty_list_keeps_header(self):
        """An empty list still prints the CSV header."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            ovhcloud.TldCsvPrinter().render(tlds=[])
        rows = list(csv.reader(io.StringIO(buf.getvalue())))
        self.assertEqual(rows, [["tld", "creation_eur", "renewal_eur"]])

#--------------------------------------------------
# Output selection
#--------------------------------------------------


class TestOutputFormat(unittest.TestCase):
    """Tests for OutputFormat and the output flags."""

    def _args(self, argv):
        """Parse arguments with the application parser."""
        app = ovhcloud.App(author="test", title="test", description="test")
        return app.build_parser().parse_args(argv)

    def test_default_is_table(self):
        """No output flag selects the table format."""
        self.assertEqual(ovhcloud.OutputFormat.select(args=self._args([])), "table")

    def test_md_selects_markdown(self):
        """--md selects markdown output."""
        self.assertEqual(ovhcloud.OutputFormat.select(args=self._args(["--md"])), "markdown")

    def test_csv_selects_csv(self):
        """--csv selects CSV output."""
        self.assertEqual(ovhcloud.OutputFormat.select(args=self._args(["--csv"])), "csv")

    def test_md_and_csv_are_mutually_exclusive(self):
        """Passing both --md and --csv is a usage error."""
        with self.assertRaises(SystemExit) as context, redirect_stderr(io.StringIO()):
            self._args(["--md", "--csv"])
        self.assertEqual(context.exception.code, 2)

#--------------------------------------------------
# Completion
#--------------------------------------------------


class TestCompletion(unittest.TestCase):
    """Tests for bash completion generation."""

    def test_completion_lists_output_options(self):
        """The completion script advertises --md and --csv."""
        app = ovhcloud.App(author="test", title="test", description="test")
        script = app.generate_completion()
        self.assertIn("--md", script)
        self.assertIn("--csv", script)


if __name__ == "__main__":
    unittest.main()
