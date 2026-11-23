#!/usr/bin/env python3
"""Tests for bookmarks module."""
# noqa: E402


import importlib.util
import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))

_SPEC = importlib.util.spec_from_file_location(
    "bookmarks", Path(__file__).parents[1] / "bookmarks.py"
)
bookmarks = importlib.util.module_from_spec(_SPEC)
sys.modules["bookmarks"] = bookmarks
_SPEC.loader.exec_module(bookmarks)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "Bookmarks.json"

DOC = json.loads(FIXTURE.read_text(encoding="utf-8"))


def ms_of(offset_us):
    """Convert a fixture Chrome microsecond value to Unix epoch ms."""
    return bookmarks.ChromeBookmarks.chrome_us_to_ms(offset_us)


def iso_of(offset_us):
    """Format a fixture Chrome microsecond value as local ISO with seconds."""
    return datetime.fromtimestamp(ms_of(offset_us) / 1000).isoformat(timespec="seconds")


def make_entries():
    """Flatten the fixture document with the Chrome bookmarks loader."""
    return bookmarks.ChromeBookmarks().flatten(document=DOC)


#--------------------------------------------------
# Conversion and parsing helpers
#--------------------------------------------------


class TestChromeEpoch(unittest.TestCase):
    """Tests for ChromeBookmarks.chrome_us_to_ms."""

    def test_converts_chrome_epoch(self):
        """A Chrome epoch microsecond value converts to Unix milliseconds."""
        self.assertEqual(
            bookmarks.ChromeBookmarks.chrome_us_to_ms("13380000200000000"),
            (
                13380000200000000
                - bookmarks.ChromeBookmarks.CHROME_EPOCH_OFFSET_US
            ) // 1000,
        )

    def test_invalid_returns_zero(self):
        """Invalid input converts to 0."""
        self.assertEqual(bookmarks.ChromeBookmarks.chrome_us_to_ms("garbage"), 0)
        self.assertEqual(bookmarks.ChromeBookmarks.chrome_us_to_ms(None), 0)


class TestParseHuman(unittest.TestCase):
    """Tests for DateRangeResolver.parse."""

    def setUp(self):
        self.resolver = bookmarks.DateRangeResolver()

    def test_parses_datetime(self):
        """A full datetime string is parsed with an explicit-time flag."""
        moment, had_time = self.resolver.parse(value="2026-08-13 10:30:45")
        self.assertEqual(moment, datetime(2026, 8, 13, 10, 30, 45))
        self.assertTrue(had_time)

    def test_parses_date_only(self):
        """A bare date is parsed without an explicit-time flag."""
        moment, had_time = self.resolver.parse(value="2026-08-13")
        self.assertEqual(moment, datetime(2026, 8, 13))
        self.assertFalse(had_time)

    def test_invalid_raises(self):
        """Malformed input raises ValueError."""
        with self.assertRaises(ValueError):
            self.resolver.parse(value="not-a-date")


#--------------------------------------------------
# Date range resolution
#--------------------------------------------------


class TestResolveRange(unittest.TestCase):
    """Tests for DateRangeResolver.resolve."""

    def setUp(self):
        self.resolver = bookmarks.DateRangeResolver()

    def test_missing_start_is_unbounded(self):
        """A missing --start resolves to the epoch lower limit."""
        start_ms, _ = self.resolver.resolve()
        self.assertEqual(start_ms, 0)

    def test_end_defaults_to_now(self):
        """A missing --end resolves to now."""
        before = int(datetime.now().timestamp() * 1000)
        _, end_ms = self.resolver.resolve()
        after = int(datetime.now().timestamp() * 1000)
        self.assertGreaterEqual(end_ms, before)
        self.assertLessEqual(end_ms, after)

    def test_date_only_start_uses_midnight(self):
        """A date-only start resolves to local midnight."""
        start_ms, _ = self.resolver.resolve(start="2026-08-13")
        self.assertEqual(start_ms, int(datetime(2026, 8, 13).timestamp() * 1000))

    def test_start_with_time(self):
        """A start with a time keeps its time of day."""
        start_ms, _ = self.resolver.resolve(start="2026-08-13 10:30:00")
        self.assertEqual(
            start_ms,
            int(datetime(2026, 8, 13, 10, 30).timestamp() * 1000),
        )

    def test_date_only_end_resolves_to_end_of_day(self):
        """A date-only end resolves to end of that day."""
        _, end_ms = self.resolver.resolve(end="2026-08-13")
        self.assertEqual(
            end_ms,
            int(datetime(2026, 8, 13, 23, 59, 59).timestamp() * 1000),
        )

    def test_end_before_start_raises(self):
        """An end earlier than start raises UsageError."""
        with self.assertRaises(bookmarks.UsageError) as ctx:
            self.resolver.resolve(start="2026-08-14", end="2026-08-13")
        self.assertIn("end cannot be set before start", str(ctx.exception))


#--------------------------------------------------
# Bookmark flattening
#--------------------------------------------------


class TestFlatten(unittest.TestCase):
    """Tests for ChromeBookmarks.flatten."""

    def setUp(self):
        self.bookmarks = bookmarks.ChromeBookmarks()
        self.entries = self.bookmarks.flatten(document=DOC)

    def test_flattens_only_urls(self):
        """Only url nodes are emitted."""
        names = {entry["name"] for entry in self.entries}
        self.assertEqual(names, {"Python", "Ruff", "Outside <Range>", "Loose"})

    def test_tags_use_ancestor_folders(self):
        """Bookmarks carry their ancestor folder chain as tags."""
        by_name = {entry["name"]: entry for entry in self.entries}
        self.assertEqual(by_name["Python"]["tags"], ["Bookmarks bar", "dev"])
        self.assertEqual(by_name["Loose"]["tags"], ["Other bookmarks"])

    def test_dates(self):
        """date_created reflects the node ADD_DATE; date_modified the parent folder."""
        by_name = {entry["name"]: entry for entry in self.entries}
        self.assertEqual(
            by_name["Python"]["date_created"],
            iso_of(13380000200000000),
        )
        self.assertEqual(
            by_name["Python"]["date_modified"],
            iso_of(13380000100000000),
        )
        self.assertEqual(
            by_name["Ruff"]["date_created"],
            iso_of(13390000000000000),
        )

    def test_entry_keys(self):
        """Entries expose only name, url, dates, tags and the internal timestamp."""
        entry = self.entries[0]
        self.assertEqual(
            set(entry),
            {"_ts_ms", "name", "url", "date_created", "date_modified", "tags"},
        )

    def test_trailing_slash_stripped(self):
        """Trailing slashes are removed from URLs."""
        by_name = {entry["name"]: entry for entry in self.entries}
        self.assertEqual(by_name["Python"]["url"], "https://www.python.org")
        self.assertEqual(by_name["Ruff"]["url"], "https://docs.astral.sh/ruff")
        self.assertEqual(
            by_name["Outside <Range>"]["url"],
            "https://example.org/?a=1&b=2",
        )
        self.assertEqual(by_name["Loose"]["url"], "https://example.com/loose")


#--------------------------------------------------
# Filtering
#--------------------------------------------------


class TestFilter(unittest.TestCase):
    """Tests for ChromeBookmarks.filter."""

    def setUp(self):
        self.bookmarks = bookmarks.ChromeBookmarks()
        self.entries = self.bookmarks.filter(
            entries=self.bookmarks.flatten(document=DOC),
            start_ms=ms_of(13380000100000000),
            end_ms=ms_of(13380000500000000),
        )

    def test_keeps_in_range(self):
        """Entries within [start, end) are kept."""
        self.assertEqual({entry["name"] for entry in self.entries}, {"Python"})

    def test_exclusive_end(self):
        """The end boundary is exclusive."""
        self.assertNotIn("Loose", {entry["name"] for entry in self.entries})

    def test_start_boundary(self):
        """Entries before the start boundary are dropped."""
        self.assertNotIn(
            "Outside <Range>",
            {entry["name"] for entry in self.entries},
        )


#--------------------------------------------------
# Renderers
#--------------------------------------------------


class TestMarkdownRender(unittest.TestCase):
    """Tests for MarkdownRenderer.render."""

    def setUp(self):
        self.out = bookmarks.MarkdownRenderer().render(entries=make_entries())

    def test_block_structure(self):
        """Each entry renders a front matter block, heading, tags and link."""
        self.assertIn("## Python", self.out)
        self.assertIn("- [Python](https://www.python.org)", self.out)
        self.assertIn("- created_at: " + iso_of(13380000200000000), self.out)
        self.assertIn("- modified_at: " + iso_of(13380000100000000), self.out)
        self.assertIn("  - dev", self.out)
        self.assertIn("  - bookmarks-bar", self.out)
        self.assertIn("\n#bookmark #bookmarks-bar #dev\n", self.out)
        self.assertNotIn("##bookmark", self.out)
        self.assertNotIn("  - Bookmarks bar", self.out)

    def test_top_header(self):
        """Output starts with a title header."""
        self.assertTrue(self.out.startswith("# chrome Bookmarks"))


class TestHtmlRender(unittest.TestCase):
    """Tests for NetscapeRenderer.render."""

    def setUp(self):
        self.out = bookmarks.NetscapeRenderer().render(entries=make_entries())

    def test_header_and_escaping(self):
        """Netscape header present and values escaped."""
        self.assertIn("<!DOCTYPE NETSCAPE-Bookmark-file-1>", self.out)
        self.assertIn("web &lt;&amp;&gt;", self.out)
        self.assertIn("Outside &lt;Range&gt;", self.out)
        self.assertIn('HREF="https://example.org/?a=1&amp;b=2"', self.out)

    def test_folder_tree(self):
        """Folders render as nested H3/DL blocks."""
        self.assertIn("<DT><H3", self.out)
        self.assertIn("<DL><p>", self.out)
        self.assertIn("</DL><p>", self.out)

    def test_add_date_is_epoch_seconds(self):
        """Bookmark ADD_DATE values are Unix epoch seconds."""
        add_date = str(ms_of(13380000200000000) // 1000)
        self.assertIn(f'ADD_DATE="{add_date}"', self.out)


#--------------------------------------------------
# Completion
#--------------------------------------------------


class TestCompletion(unittest.TestCase):
    """Tests for Completion.generate."""

    def test_completion_script(self):
        """The generated script exposes all options and the function name."""
        script = bookmarks.Completion.generate(
            parser=bookmarks.Application().build_parser(),
            name="bookmarks",
        )
        self.assertIn("_bookmarks_completions", script)
        for opt in ("--md", "--html", "--json", "--start", "--end"):
            self.assertIn(opt, script)


#--------------------------------------------------
# CLI behavior
#--------------------------------------------------


class TestCli(unittest.TestCase):
    """CLI end-to-end tests."""

    def run_cli(self, argv):
        """Run the application with the given CLI args, capturing output and exits."""
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = bookmarks.Application().run(argv=argv)
            except SystemExit as error:
                code = error.code if error.code else 0
        return code, out.getvalue(), err.getvalue()

    def test_json_default_output(self):
        """Default output is a JSON array with slugified tags and no dead fields."""
        code, out, _ = self.run_cli(
            ["--db", str(FIXTURE), "--start", "2020-01-01", "--end", "2027-01-01"]
        )
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(len(data), 4)
        python = next(entry for entry in data if entry["name"] == "Python")
        self.assertEqual(
            set(python),
            {"name", "url", "date_created", "date_modified", "tags"},
        )
        self.assertEqual(python["tags"], ["bookmarks-bar", "dev"])

    def test_md_output_with_explicit_flag(self):
        """--md renders markdown blocks."""
        code, out, _ = self.run_cli(
            ["--db", str(FIXTURE), "--md", "--start", "2020-01-01", "--end", "2027-01-01"]
        )
        self.assertEqual(code, 0)
        self.assertIn("## Python", out)
        self.assertIn("\n#bookmark #bookmarks-bar #dev\n", out)
        self.assertNotIn("##bookmark", out)

    def test_html_output(self):
        """--html renders a Netscape bookmark file."""
        code, out, _ = self.run_cli(
            ["--db", str(FIXTURE), "--html", "--start", "2020-01-01", "--end", "2027-01-01"]
        )
        self.assertEqual(code, 0)
        self.assertIn("NETSCAPE-Bookmark-file-1", out)

    def test_date_filter_excludes(self):
        """A narrow range excludes out-of-range bookmarks."""
        base = datetime.fromtimestamp(ms_of(13380000200000000) / 1000)
        code, out, _ = self.run_cli([
            "--db", str(FIXTURE),
            "--start", (base - timedelta(seconds=5)).strftime("%Y-%m-%d %H:%M:%S"),
            "--end", (base + timedelta(seconds=50)).strftime("%Y-%m-%d %H:%M:%S"),
        ])
        data = json.loads(out)
        self.assertEqual({entry["name"] for entry in data}, {"Python"})

    def test_invalid_db_runtime_error(self):
        """A missing db file is a runtime error (exit 1)."""
        code, _, err = self.run_cli(
            ["--db", "/nonexistent/Bookmarks", "--start", "2020-01-01"]
        )
        self.assertEqual(code, 1)
        self.assertIn("ERROR", err)

    def test_quiet_does_not_hide_runtime_error(self):
        """With --quiet a runtime error still exits 1 with an error on stderr."""
        code, out, err = self.run_cli(
            ["--db", "/nonexistent/Bookmarks", "--quiet", "--start", "2020-01-01"]
        )
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("ERROR", err)

    def test_invalid_date_usage_error(self):
        """An invalid date is a usage error (exit 2)."""
        code, _, err = self.run_cli(
            ["--db", str(FIXTURE), "--start", "yesterday"]
        )
        self.assertEqual(code, 2)
        self.assertIn("ERROR", err)

    def test_usage_error_is_quiet_safe(self):
        """Usage errors return exit 2 even with --quiet."""
        code, _, err = self.run_cli(
            ["--db", str(FIXTURE), "--start", "nope", "--quiet"]
        )
        self.assertEqual(code, 2)
        self.assertIn("ERROR", err)

    def test_end_before_start_usage_error(self):
        """An end before the start exits 2 with a diagnostic."""
        code, _, err = self.run_cli(
            ["--db", str(FIXTURE), "--start", "2026-08-14", "--end", "2026-08-13"]
        )
        self.assertEqual(code, 2)
        self.assertIn("end cannot be set before start", err)

    def test_completion_flag_prints_script(self):
        """--completion prints the bash completion script and exits 0."""
        with patch.object(sys, "argv", ["bookmarks.py", "--completion"]):
            code, out, _ = self.run_cli(["--completion"])
        self.assertEqual(code, 0)
        self.assertIn("#!/bin/bash", out)
        self.assertIn("_bookmarks_completions", out)

    def test_collect_entries_sorted(self):
        """BookmarkReader.collect returns entries sorted by add date."""
        reader = bookmarks.BookmarkReader(
            locator=bookmarks.ChromeProfileLocator(),
            bookmarks=bookmarks.ChromeBookmarks(),
            ranges=bookmarks.DateRangeResolver(),
        )
        entries = reader.collect(
            db=str(FIXTURE),
            profile="",
            user_data="",
            start="2020-01-01",
            end="2027-01-01",
        )
        timestamps = [entry["_ts_ms"] for entry in entries]
        self.assertEqual(len(entries), 4)
        self.assertEqual(timestamps, sorted(timestamps))


if __name__ == "__main__":
    unittest.main()
