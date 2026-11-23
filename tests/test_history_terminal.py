#!/usr/bin/env python3
"""Tests for history_terminal module."""
# noqa: E402


import argparse
import io
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))

_SPEC = importlib.util.spec_from_file_location(
    "history_terminal", Path(__file__).parents[1] / "history-terminal.py"
)
history_terminal = importlib.util.module_from_spec(_SPEC)
sys.modules["history_terminal"] = history_terminal
_SPEC.loader.exec_module(history_terminal)

# These tests intentionally exercise private helpers.
# noqa: SLF001, E402


class ArgsFactory:
    """Build argparse namespaces for date-range tests."""

    @staticmethod
    def make(*, start=None, end=None):
        """Return a namespace with the given start and end values."""
        return argparse.Namespace(start=start, end=end)


#--------------------------------------------------
# Date-range resolution
#--------------------------------------------------


class TestDateRangeParse(unittest.TestCase):
    """Tests for DateRange.parse."""

    def test_parses_datetime(self):
        """A full datetime string parses with an explicit-time flag."""
        dt, had_time = history_terminal.DateRange.parse(value="2026-08-13 10:30:45")
        self.assertEqual(dt, datetime(2026, 8, 13, 10, 30, 45))
        self.assertTrue(had_time)

    def test_parses_date_only(self):
        """A bare date parses without an explicit-time flag."""
        dt, had_time = history_terminal.DateRange.parse(value="2026-08-13")
        self.assertEqual(dt, datetime(2026, 8, 13))
        self.assertFalse(had_time)

    def test_invalid_raises(self):
        """Malformed input raises ValueError."""
        with self.assertRaises(ValueError):
            history_terminal.DateRange.parse(value="nope")


class TestDateRangeResolve(unittest.TestCase):
    """Tests for DateRange.resolve and the CLI boundary."""

    def test_human_start(self):
        """A date-only start resolves to local midnight in seconds."""
        from_sec, _ = history_terminal.DateRange.resolve(
            args=ArgsFactory.make(start="2026-08-13")
        )
        self.assertEqual(from_sec, int(datetime(2026, 8, 13).timestamp()))

    def test_human_end_with_time(self):
        """An end with a time keeps its time of day."""
        _, to_sec = history_terminal.DateRange.resolve(
            args=ArgsFactory.make(start="2026-08-12", end="2026-08-13 10:30:45")
        )
        self.assertEqual(to_sec, int(datetime(2026, 8, 13, 10, 30, 45).timestamp()))

    def test_end_before_start_raises(self):
        """An end before start raises ValueError."""
        with self.assertRaises(ValueError):
            history_terminal.DateRange.resolve(
                args=ArgsFactory.make(start="2026-08-14", end="2026-08-13")
            )

    def test_invalid_range_exits_2(self):
        """The CLI exits 2 on invalid input."""
        err = io.StringIO()
        with patch.object(sys, "argv", [
            "history_terminal",
            "--start", "2026-08-14",
            "--end", "2026-08-13",
        ]):
            with self.assertRaises(SystemExit) as ctx, redirect_stderr(err):
                history_terminal.HistoryApp().run()
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("end cannot be set before start", err.getvalue())

    def test_add_date_range_args(self):
        """The helper adds --start and --end."""
        parser = argparse.ArgumentParser()
        history_terminal.DateRange.add_arguments(parser=parser)
        args = parser.parse_args(["--start", "2026-08-13", "--end", "2026-08-15"])
        self.assertEqual(args.start, "2026-08-13")
        self.assertEqual(args.end, "2026-08-15")


#--------------------------------------------------
# Line parsers
#--------------------------------------------------


class TestZshLineParser(unittest.TestCase):
    """Tests for ZshLineParser."""

    def setUp(self):
        self.parser = history_terminal.ZshLineParser()

    def test_parses_valid_line(self):
        """A zsh history line yields a dict with command and timestamp."""
        ts = int(datetime(2026, 8, 13, 10, 0).timestamp())
        parsed = self.parser.parse(line=f": {ts}:0;ls -la")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["command"], "ls -la")
        self.assertEqual(parsed["_ts_sec"], ts)
        self.assertEqual(parsed["datetime"], datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S"))

    def test_malformed_returns_none(self):
        """A line without the zsh prefix yields None."""
        self.assertIsNone(self.parser.parse(line="ls -la"))
        self.assertIsNone(self.parser.parse(line=""))


class TestBashLineParser(unittest.TestCase):
    """Tests for BashLineParser."""

    def setUp(self):
        self.parser = history_terminal.BashLineParser()

    def test_parses_command(self):
        """A bash line yields a dict with the stripped command."""
        self.assertEqual(
            self.parser.parse(line="  ls -la  "),
            {"command": "ls -la"},
        )

    def test_blank_returns_none(self):
        """Blank lines yield None."""
        self.assertIsNone(self.parser.parse(line=""))
        self.assertIsNone(self.parser.parse(line="   "))


#--------------------------------------------------
# Markdown rendering
#--------------------------------------------------


class TestRenderMarkdown(unittest.TestCase):
    """Tests for TerminalReport.render_markdown."""

    def test_with_datetime_column(self):
        """Entries with datetimes render a Datetime column."""
        out = history_terminal.TerminalReport.render_markdown(entries=[
            {"index": 1, "command": "ls", "datetime": "2026-08-13 10:00:00"},
        ])
        self.assertIn("| # | Command | Datetime |", out)
        self.assertIn("| 1 | ls | 2026-08-13 10:00:00 |", out)

    def test_without_datetime_column(self):
        """Entries without datetimes omit the column."""
        out = history_terminal.TerminalReport.render_markdown(
            entries=[{"index": 1, "command": "ls"}]
        )
        self.assertNotIn("Datetime", out)
        self.assertIn("| 1 | ls |", out)

    def test_escapes_pipes(self):
        """Pipes in commands are escaped."""
        out = history_terminal.TerminalReport.render_markdown(
            entries=[{"index": 1, "command": "a | b"}]
        )
        self.assertIn("| 1 | a \\| b |", out)


#--------------------------------------------------
# main / CLI
#--------------------------------------------------


class TestMain(unittest.TestCase):
    """Tests for the command-line application against temporary history files."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        ts1 = int(datetime(2026, 8, 13, 10, 0).timestamp())
        ts2 = int(datetime(2026, 8, 13, 11, 0).timestamp())
        ts3 = int(datetime(2026, 8, 13, 13, 0).timestamp())
        self.zsh = os.path.join(self.tmp, ".zsh_history")
        with open(self.zsh, "w", encoding="utf-8") as f:
            f.write(f": {ts1}:0;echo morning\n")
            f.write(f": {ts2}:0;echo afternoon\n")
            f.write(f": {ts3}:0;echo evening\n")
            f.write(f": {ts1}:0;echo morning\n")
            f.write("garbage line\n")
        self.bash = os.path.join(self.tmp, ".bash_history")
        with open(self.bash, "w", encoding="utf-8") as f:
            f.write("echo bashcmd\n")
            f.write("echo morning\n")
            f.write("\n")

    @staticmethod
    def run_main(argv, sources):
        """Run the app with argv against the given history sources."""
        buf = io.StringIO()
        with patch.object(sys, "argv", ["history_terminal", *argv]), \
             redirect_stdout(buf):
            history_terminal.HistoryApp(sources=sources).run()
        return buf.getvalue()

    def test_json_output_with_filter_dedup_and_merge(self):
        """Range filtering, cross-file dedup, and indexing work."""
        out = self.run_main(
            ["--start", "2026-08-13 09:00:00", "--end", "2026-08-13 12:00:00"],
            [Path(self.zsh), Path(self.bash)],
        )
        data = json.loads(out)
        commands = [e["command"] for e in data]
        self.assertEqual(commands, ["echo morning", "echo afternoon", "echo bashcmd", "echo morning"])
        self.assertEqual([e["index"] for e in data], [1, 2, 3, 4])
        self.assertEqual(data[0]["datetime"], datetime.fromtimestamp(
            int(datetime(2026, 8, 13, 10, 0).timestamp())
        ).strftime("%Y-%m-%d %H:%M:%S"))

    def test_md_output_with_datetimes(self):
        """--md renders a table with a Datetime column."""
        out = self.run_main(
            ["--md", "--start", "2026-08-13 09:00:00", "--end", "2026-08-13 12:00:00"],
            [Path(self.zsh)],
        )
        self.assertIn("| # | Command | Datetime |", out)
        self.assertIn("echo morning", out)
        self.assertNotIn("echo evening", out)

    def test_md_output_bash_only(self):
        """Bash-only history renders without a Datetime column."""
        out = self.run_main(["--md"], [Path(self.bash)])
        self.assertNotIn("Datetime", out)
        self.assertIn("echo bashcmd", out)

    def test_empty_history(self):
        """Empty sources yield an empty JSON list."""
        out = self.run_main([], [])
        self.assertEqual(json.loads(out), [])


if __name__ == "__main__":
    unittest.main()
