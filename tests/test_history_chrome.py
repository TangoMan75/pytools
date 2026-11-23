#!/usr/bin/env python3
"""Tests for history_chrome module."""

import argparse
import importlib.util
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))

_SPEC = importlib.util.spec_from_file_location(
    "history_chrome", Path(__file__).parents[1] / "history-chrome.py"
)
history_chrome = importlib.util.module_from_spec(_SPEC)
sys.modules["history_chrome"] = history_chrome
_SPEC.loader.exec_module(history_chrome)


class HistoryChromeTestCase(unittest.TestCase):
    """Shared fixtures and helpers for the history-chrome tests."""

    @staticmethod
    def make_args(*, start=None, end=None, start_ms=None, end_ms=None):
        """Build an argparse Namespace from the given date-range values."""
        return argparse.Namespace(
            start=start,
            end=end,
            start_ms=start_ms,
            end_ms=end_ms,
        )

    @staticmethod
    def build_history_db(*, path, visits):
        """Create a Chrome-style History database containing the given visits."""
        connection = sqlite3.connect(path)
        cursor = connection.cursor()
        cursor.execute("CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT, title TEXT)")
        cursor.execute(
            "CREATE TABLE visits (visit_time INTEGER, url INTEGER, "
            "visit_duration INTEGER, transition INTEGER)"
        )
        for index, (visit_time, url, title, duration, transition) in enumerate(visits, 1):
            cursor.execute(
                "INSERT INTO urls (id, url, title) VALUES (?,?,?)",
                (index, url, title),
            )
            cursor.execute(
                "INSERT INTO visits (visit_time, url, visit_duration, transition) "
                "VALUES (?,?,?,?)",
                (visit_time, index, duration, transition),
            )
        connection.commit()
        connection.close()

    @staticmethod
    def formatter():
        """Return a visit formatter for JSON and Markdown assertions."""
        return history_chrome.VisitFormatter()

    @classmethod
    def urls(cls, *, visits):
        """Return the URL of each visit through the public JSON representation."""
        formatter = cls.formatter()
        return [visit.as_dict(formatter=formatter)["url"] for visit in visits]


#--------------------------------------------------
# Date-range resolution
#--------------------------------------------------


class TestParseHuman(HistoryChromeTestCase):
    """Tests for DateRangeResolver.parse_human."""

    def test_parses_datetime(self):
        """A full datetime string is parsed with an explicit-time flag."""
        moment, had_time = history_chrome.DateRangeResolver.parse_human(
            value="2026-08-13 10:30:45"
        )
        self.assertEqual(moment, datetime(2026, 8, 13, 10, 30, 45))
        self.assertTrue(had_time)

    def test_parses_date_only(self):
        """A bare date is parsed without an explicit-time flag."""
        moment, had_time = history_chrome.DateRangeResolver.parse_human(
            value="2026-08-13"
        )
        self.assertEqual(moment, datetime(2026, 8, 13))
        self.assertFalse(had_time)

    def test_invalid_raises(self):
        """Malformed input raises ValueError."""
        with self.assertRaises(ValueError):
            history_chrome.DateRangeResolver.parse_human(value="not-a-date")


class TestResolveRange(HistoryChromeTestCase):
    """Tests for DateRangeResolver.resolve and resolve_or_exit."""

    def test_human_start_date_only_uses_midnight(self):
        """A date-only start resolves to local midnight."""
        from_ms, _ = history_chrome.DateRangeResolver.resolve(
            options=self.make_args(start="2026-08-13")
        )
        self.assertEqual(from_ms, int(datetime(2026, 8, 13).timestamp() * 1000))

    def test_human_start_with_time(self):
        """A start with a time keeps its time of day."""
        from_ms, _ = history_chrome.DateRangeResolver.resolve(
            options=self.make_args(start="2026-08-13 10:30:00")
        )
        self.assertEqual(
            from_ms,
            int(datetime(2026, 8, 13, 10, 30).timestamp() * 1000),
        )

    def test_epoch_ms_passthrough(self):
        """--start-ms is returned unchanged."""
        from_ms, to_ms = history_chrome.DateRangeResolver.resolve(
            options=self.make_args(start_ms=1000, end_ms=2000)
        )
        self.assertEqual((from_ms, to_ms), (1000, 2000))

    def test_start_and_start_ms_conflict(self):
        """Supplying both --start and --start-ms raises."""
        with self.assertRaises(ValueError):
            history_chrome.DateRangeResolver.resolve(
                options=self.make_args(start="2026-08-13", start_ms=1000)
            )

    def test_end_and_end_ms_conflict(self):
        """Supplying both --end and --end-ms raises."""
        with self.assertRaises(ValueError):
            history_chrome.DateRangeResolver.resolve(
                options=self.make_args(end="2026-08-13", end_ms=1000)
            )

    def test_end_before_start_raises(self):
        """An end earlier than start raises ValueError."""
        with self.assertRaises(ValueError):
            history_chrome.DateRangeResolver.resolve(
                options=self.make_args(start="2026-08-14", end="2026-08-13")
            )

    def test_defaults_to_today(self):
        """No arguments resolve to today 00:00 .. now."""
        from_ms, to_ms = history_chrome.DateRangeResolver.resolve(
            options=self.make_args()
        )
        now = datetime.now()
        today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        self.assertEqual(from_ms, int(today_midnight.timestamp() * 1000))
        self.assertEqual(to_ms, int(now.timestamp() * 1000))

    def test_resolve_or_exit_returns_2_on_error(self):
        """resolve_or_exit prints an error and exits 2 on invalid input."""
        err = io.StringIO()
        resolver = history_chrome.DateRangeResolver(
            logger=history_chrome.Logger(quiet=False)
        )
        with self.assertRaises(SystemExit) as context, redirect_stderr(err):
            resolver.resolve_or_exit(
                options=self.make_args(start="2026-08-14", end="2026-08-13")
            )
        self.assertEqual(context.exception.code, 2)
        self.assertIn("end cannot be set before start", err.getvalue())

    def test_add_arguments_registers_four_options(self):
        """add_arguments adds start, end, start_ms, and end_ms."""
        parser = argparse.ArgumentParser()
        history_chrome.DateRangeResolver.add_arguments(parser=parser)
        options = parser.parse_args(["--start", "2026-08-13", "--end-ms", "5000"])
        self.assertEqual(options.start, "2026-08-13")
        self.assertEqual(options.end_ms, 5000)
        self.assertIsNone(options.end)
        self.assertIsNone(options.start_ms)


#--------------------------------------------------
# Conversions and formatting
#--------------------------------------------------


class TestChromeEpoch(HistoryChromeTestCase):
    """Tests for ChromeHistory.webkit_us_to_epoch_ms."""

    def test_webkit_to_unix_ms(self):
        """A WebKit microsecond value converts to epoch ms."""
        unix_ms = int(datetime(2026, 1, 1, 12, 0).timestamp() * 1000)
        offset = history_chrome.ChromeHistory.EPOCH_OFFSET_US
        self.assertEqual(
            history_chrome.ChromeHistory.webkit_us_to_epoch_ms(
                value=unix_ms * 1000 + offset
            ),
            unix_ms,
        )

    def test_zero_input(self):
        """A zero WebKit value maps below the epoch to a negative number."""
        self.assertLess(
            history_chrome.ChromeHistory.webkit_us_to_epoch_ms(value=0),
            0,
        )

    def test_bad_input_returns_zero(self):
        """Non-numeric input yields 0."""
        self.assertEqual(
            history_chrome.ChromeHistory.webkit_us_to_epoch_ms(value="nope"),
            0,
        )
        self.assertEqual(
            history_chrome.ChromeHistory.webkit_us_to_epoch_ms(value=None),
            0,
        )


class TestDecodeTransition(HistoryChromeTestCase):
    """Tests for ChromeHistory.decode_transition."""

    def test_link_core(self):
        """Transition core 0 maps to 'link' and is not typed."""
        info = history_chrome.ChromeHistory.decode_transition(transition=0)
        self.assertEqual(info["transition_core"], "link")
        self.assertFalse(info["typed"])

    def test_keyword_core_is_typed(self):
        """Transition core 9 maps to 'keyword' and is typed."""
        info = history_chrome.ChromeHistory.decode_transition(transition=9)
        self.assertEqual(info["transition_core"], "keyword")
        self.assertTrue(info["typed"])

    def test_unknown_core(self):
        """An unknown low byte maps to a core_<n> label."""
        info = history_chrome.ChromeHistory.decode_transition(transition=200)
        self.assertEqual(info["transition_core"], "core_200")

    def test_redirect_flags(self):
        """Redirect and other flag bits are surfaced as booleans."""
        info = history_chrome.ChromeHistory.decode_transition(
            transition=1 | (1 << 20)
        )
        self.assertTrue(info["redirect"])
        self.assertFalse(info["server_redirect"])
        self.assertFalse(info["client_redirect"])

    def test_server_redirect_flag(self):
        """The server redirect bit is surfaced."""
        info = history_chrome.ChromeHistory.decode_transition(transition=1 << 19)
        self.assertFalse(info["redirect"])
        self.assertTrue(info["server_redirect"])

    def test_blocked_flag(self):
        """The blocked bit is reported."""
        info = history_chrome.ChromeHistory.decode_transition(transition=1 << 25)
        self.assertTrue(info["blocked"])

    def test_none_treated_as_zero(self):
        """None input is treated as transition 0."""
        info = history_chrome.ChromeHistory.decode_transition(transition=None)
        self.assertEqual(info["transition_core"], "link")


class TestFormatting(HistoryChromeTestCase):
    """Tests for VisitFormatter string helpers."""

    def test_format_duration(self):
        """Durations render compactly by magnitude."""
        formatter = self.formatter()
        self.assertEqual(formatter.format_duration(seconds=0), "")
        self.assertEqual(formatter.format_duration(seconds=-5), "")
        self.assertEqual(formatter.format_duration(seconds=45), "45s")
        self.assertEqual(formatter.format_duration(seconds=90), "1m30s")
        self.assertEqual(formatter.format_duration(seconds=3661), "1h01m")

    def test_escape_markdown(self):
        """Pipes and newlines are escaped for table cells."""
        formatter = self.formatter()
        self.assertEqual(formatter.escape_markdown(value="a|b\nc"), "a\\|b c")
        self.assertEqual(formatter.escape_markdown(value=None), "")

    def test_truncate_short(self):
        """Short strings pass through unchanged."""
        formatter = self.formatter()
        self.assertEqual(formatter.truncate(value="hello", limit=10), "hello")

    def test_truncate_long(self):
        """Long strings are truncated with an ellipsis."""
        formatter = self.formatter()
        output = formatter.truncate(value="hello world", limit=5)
        self.assertEqual(output, "hell\u2026")
        self.assertEqual(formatter.truncate(value=None, limit=5), "")

    def test_format_range_title_same_day(self):
        """A single-day range shows one date."""
        formatter = self.formatter()
        ms = int(datetime(2026, 8, 13, 10).timestamp() * 1000)
        self.assertEqual(
            formatter.format_range_title(from_ms=ms, to_ms=ms + 1000),
            "2026-08-13",
        )

    def test_format_range_title_spanning(self):
        """A multi-day range shows both dates separated by an arrow."""
        formatter = self.formatter()
        start = int(datetime(2026, 8, 13).timestamp() * 1000)
        end = int(datetime(2026, 8, 15).timestamp() * 1000)
        self.assertEqual(
            formatter.format_range_title(from_ms=start, to_ms=end),
            "2026-08-13 \u2192 2026-08-15",
        )


#--------------------------------------------------
# File-system helpers
#--------------------------------------------------


class TestDefaultUserDataDir(HistoryChromeTestCase):
    """Tests for ChromeHistory.default_user_data_dir."""

    def test_windows(self):
        """Windows uses LOCALAPPDATA."""
        with patch("history_chrome.platform.system", return_value="Windows"), \
             patch.dict(os.environ, {"LOCALAPPDATA": "C:\\AppData"}, clear=False):
            self.assertEqual(
                history_chrome.ChromeHistory.default_user_data_dir(),
                os.path.join("C:\\AppData", "Google", "Chrome", "User Data"),
            )

    def test_macos(self):
        """macOS uses the Application Support path."""
        with patch("history_chrome.platform.system", return_value="Darwin"):
            self.assertEqual(
                history_chrome.ChromeHistory.default_user_data_dir(),
                os.path.expanduser("~/Library/Application Support/Google/Chrome"),
            )

    def test_linux(self):
        """Linux uses the .config/google-chrome path."""
        with patch("history_chrome.platform.system", return_value="Linux"):
            self.assertEqual(
                history_chrome.ChromeHistory.default_user_data_dir(),
                os.path.expanduser("~/.config/google-chrome"),
            )

    def test_windows_missing_appdata(self):
        """Windows without LOCALAPPDATA returns an empty string."""
        with patch("history_chrome.platform.system", return_value="Windows"), \
             patch.dict(os.environ, {}, clear=False):
            if "LOCALAPPDATA" in os.environ:
                del os.environ["LOCALAPPDATA"]
            self.assertEqual(history_chrome.ChromeHistory.default_user_data_dir(), "")


class TestDiscoverProfiles(HistoryChromeTestCase):
    """Tests for ChromeHistory.discover_profiles."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_returns_profiles_with_history(self):
        """Only directories matching Default/Profile N with a History file count."""
        for name in ("Default", "Profile 1", "Profile 2"):
            directory = os.path.join(self.tmp, name)
            os.makedirs(directory)
            Path(directory, "History").touch()
        os.makedirs(os.path.join(self.tmp, "Profile 3"))
        os.makedirs(os.path.join(self.tmp, "Guest Profile"))
        os.makedirs(os.path.join(self.tmp, "Other"))
        Path(os.path.join(self.tmp, "Other", "History")).touch()
        history = history_chrome.ChromeHistory(user_data=self.tmp)
        self.assertEqual(
            history.discover_profiles(),
            ["Default", "Profile 1", "Profile 2"],
        )

    def test_missing_directory(self):
        """A missing directory yields no profiles."""
        history = history_chrome.ChromeHistory(user_data="/no/such/dir")
        self.assertEqual(history.discover_profiles(), [])


class TestSnapshotToTmp(HistoryChromeTestCase):
    """Tests for ChromeHistory.snapshot_to_tmp."""

    def test_copies_file_to_tmpfile(self):
        """The source is copied to a fresh sqlite-named tmpfile."""
        source = os.path.join(tempfile.mkdtemp(), "History")
        with open(source, "wb") as stream:
            stream.write(b"payload")
        history = history_chrome.ChromeHistory(user_data="")
        tmp_path = history.snapshot_to_tmp(history_path=source)
        try:
            self.assertTrue(os.path.basename(tmp_path).startswith("chrome-history-"))
            with open(tmp_path, "rb") as stream:
                self.assertEqual(stream.read(), b"payload")
        finally:
            os.unlink(tmp_path)


class TestDefaultEndMs(HistoryChromeTestCase):
    """Tests for DateRangeResolver.default_end_ms."""

    def test_returns_local_midnight_of_next_day(self):
        """The exclusive end is midnight after the from_ms day."""
        from_ms = int(datetime(2026, 1, 1, 15, 30).timestamp() * 1000)
        expected = int(datetime(2026, 1, 2).timestamp() * 1000)
        self.assertEqual(
            history_chrome.DateRangeResolver.default_end_ms(from_ms=from_ms),
            expected,
        )


#--------------------------------------------------
# Database access
#--------------------------------------------------


class TestReadVisits(HistoryChromeTestCase):
    """Tests for ChromeHistory.read_visits."""

    def setUp(self):
        self.handle, self.path = tempfile.mkstemp(suffix=".sqlite")
        os.close(self.handle)

    def tearDown(self):
        os.unlink(self.path)

    def test_fetch_orders_and_filters(self):
        """Only visits in range are returned in ascending time order."""
        self.build_history_db(
            path=self.path,
            visits=[
                (1000, "http://old.example", "Old", 0, 0),
                (2000, "http://a.example", "A", 10, 9),
                (3000, "http://b.example", "B", 20, 0),
                (4000, "http://c.example", "C", 30, 0),
            ],
        )
        history = history_chrome.ChromeHistory(user_data="")
        visits = history.read_visits(
            db_path=self.path,
            start_us=2000,
            end_us=4000,
            typed_only=False,
            profile="explicit",
        )
        self.assertEqual(
            self.urls(visits=visits),
            ["http://a.example", "http://b.example"],
        )

    def test_typed_only_filters_transitions(self):
        """typed_only keeps only transitions 1, 7, 8, 9, 10."""
        self.build_history_db(
            path=self.path,
            visits=[
                (2000, "http://typed.example", "Typed", 0, 9),
                (3000, "http://link.example", "Link", 0, 0),
            ],
        )
        history = history_chrome.ChromeHistory(user_data="")
        visits = history.read_visits(
            db_path=self.path,
            start_us=1000,
            end_us=5000,
            typed_only=True,
            profile="explicit",
        )
        self.assertEqual(self.urls(visits=visits), ["http://typed.example"])


#--------------------------------------------------
# Rendering
#--------------------------------------------------


class TestRenderMarkdown(HistoryChromeTestCase):
    """Tests for MarkdownRenderer.render."""

    def test_empty_placeholder(self):
        """An empty list renders the no-visits placeholder."""
        from_ms = int(datetime(2026, 8, 13).timestamp() * 1000)
        renderer = history_chrome.MarkdownRenderer(formatter=self.formatter())
        output = renderer.render(visits=[], from_ms=from_ms, to_ms=from_ms)
        self.assertIn("# chrome History \u2014 2026-08-13", output)
        self.assertIn("_No visits in this range._", output)

    def test_table_and_totals(self):
        """A populated list renders rows plus a total line."""
        moment = int(datetime(2026, 8, 13, 10, 30).timestamp() * 1000)
        offset = history_chrome.ChromeHistory.EPOCH_OFFSET_US
        visit = history_chrome.Visit.from_row(
            row=(
                moment * 1000 + offset,
                "https://example.com/page",
                "Example",
                90000000,
                9,
            ),
            profile="explicit",
        )
        visit.number(index=1)
        renderer = history_chrome.MarkdownRenderer(formatter=self.formatter())
        output = renderer.render(visits=[visit], from_ms=moment, to_ms=moment)
        self.assertIn("| # | Time | URL | Title | Duration | Transition |", output)
        self.assertIn(
            "| 1 | 10:30:00 | https://example.com/page | Example | 1m30s | keyword |",
            output,
        )
        self.assertIn(
            "**Total:** 1 visits across 1 domains, 1 typed/bar entries",
            output,
        )


#--------------------------------------------------
# Completion
#--------------------------------------------------


class TestCompletion(HistoryChromeTestCase):
    """Tests for Completion.generate."""

    def test_generates_bash_script_for_parser(self):
        """The generated script completes the command and its options."""
        parser = history_chrome.CommandLine.build_parser()
        script = history_chrome.Completion.generate(
            parser=parser,
            name="history-chrome",
        )
        self.assertTrue(script.startswith("#!/bin/bash"))
        self.assertIn("_history_chrome_completions()", script)
        self.assertIn("--profile", script)
        self.assertIn("--typed-only", script)
        self.assertIn(
            "complete -f -F _history_chrome_completions history-chrome",
            script,
        )


#--------------------------------------------------
# Kernel / CLI
#--------------------------------------------------


class TestMain(HistoryChromeTestCase):
    """Tests for Kernel with a real temporary History database."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp, "History")
        from_ms = int(datetime(2026, 1, 1).timestamp() * 1000)
        in_ms = int(datetime(2026, 1, 1, 12, 0).timestamp() * 1000)
        out_ms = int(datetime(2026, 1, 2).timestamp() * 1000)
        offset = history_chrome.ChromeHistory.EPOCH_OFFSET_US
        self.build_history_db(
            path=self.db_path,
            visits=[
                (in_ms * 1000 + offset, "https://inside.example", "Inside", 90000000, 9),
                (out_ms * 1000 + offset, "https://outside.example", "Outside", 0, 0),
            ],
        )
        self.from_ms = from_ms
        self.to_ms = out_ms

    @staticmethod
    def run_kernel(argv):
        """Run Kernel with argv, returning (rc, stdout, stderr)."""
        buffer = io.StringIO()
        err = io.StringIO()
        with patch.object(sys, "argv", ["history_chrome", *argv]), \
             redirect_stdout(buffer), redirect_stderr(err):
            rc = history_chrome.Kernel().run()
        return rc, buffer.getvalue(), err.getvalue()

    def test_json_output(self):
        """Visits in range are emitted as JSON with transition metadata."""
        rc, output, _ = self.run_kernel([
            "--db", self.db_path, "--no-copy",
            "--start-ms", str(self.from_ms), "--end-ms", str(self.to_ms),
        ])
        self.assertEqual(rc, 0)
        data = json.loads(output)
        self.assertEqual(len(data), 1)
        entry = data[0]
        self.assertEqual(entry["url"], "https://inside.example")
        self.assertEqual(entry["title"], "Inside")
        self.assertEqual(entry["profile"], "explicit")
        self.assertEqual(entry["transition_core"], "keyword")
        self.assertTrue(entry["typed"])
        self.assertEqual(entry["index"], 1)
        self.assertEqual(entry["visit_duration_ms"], 90000)

    def test_md_output(self):
        """--md renders a markdown table."""
        rc, output, _ = self.run_kernel([
            "--db", self.db_path, "--no-copy", "--md",
            "--start-ms", str(self.from_ms), "--end-ms", str(self.to_ms),
        ])
        self.assertEqual(rc, 0)
        self.assertIn("| # | Time | URL | Title | Duration | Transition |", output)
        self.assertIn("https://inside.example", output)

    def test_typed_only(self):
        """--typed-only drops non-typed transitions."""
        rc, output, _ = self.run_kernel([
            "--db", self.db_path, "--no-copy", "--typed-only",
            "--start-ms", str(self.from_ms), "--end-ms", str(self.to_ms),
        ])
        self.assertEqual(rc, 0)
        self.assertEqual(len(json.loads(output)), 1)

    def test_snapshot_copy_is_cleaned_up(self):
        """A copied snapshot is removed in the finally block."""
        with patch.object(
            history_chrome.ChromeHistory,
            "snapshot_to_tmp",
            return_value=self.db_path,
        ), patch("history_chrome.os.unlink") as unlink:
            rc, _, _ = self.run_kernel([
                "--db", self.db_path,
                "--start-ms", str(self.from_ms), "--end-ms", str(self.to_ms),
            ])
        self.assertEqual(rc, 0)
        unlink.assert_called_once_with(self.db_path)

    def test_no_history_files_returns_1(self):
        """An empty user-data dir yields an error and exit 1."""
        empty = os.path.join(self.tmp, "empty")
        os.makedirs(empty)
        rc, _, err = self.run_kernel([
            "--user-data", empty,
            "--start-ms", str(self.from_ms), "--end-ms", str(self.to_ms),
        ])
        self.assertEqual(rc, 1)
        self.assertIn("no History files found", err)

    def test_missing_profile_warns(self):
        """A named profile without a History file warns and yields exit 1."""
        rc, _, err = self.run_kernel([
            "--user-data", self.tmp, "--profile", "Ghost",
            "--start-ms", str(self.from_ms), "--end-ms", str(self.to_ms),
        ])
        self.assertEqual(rc, 1)
        self.assertIn("not found, skipping", err)


if __name__ == "__main__":
    unittest.main()
