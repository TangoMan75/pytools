#!/usr/bin/env python3
"""Tests for history_backlog module."""
# noqa: E402


import io
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))

_SPEC = importlib.util.spec_from_file_location(
    "history_backlog", Path(__file__).parents[1] / "history-backlog.py"
)
history_backlog = importlib.util.module_from_spec(_SPEC)
sys.modules["history_backlog"] = history_backlog
_SPEC.loader.exec_module(history_backlog)

# noqa: E402


class TestParseDate(unittest.TestCase):
    """Tests for parse_date."""

    def test_valid_date_passes_through(self):
        """A valid YYYY-MM-DD string is returned unchanged."""
        self.assertEqual(history_backlog.DateRange.parse(value="2026-08-15"), "2026-08-15")

    def test_datetime_string_is_truncated(self):
        """A YYYY-MM-DD HH:MM:SS string is truncated to its date."""
        self.assertEqual(history_backlog.DateRange.parse(value="2026-08-14 22:19:55"), "2026-08-14")

    def test_midnight_datetime_string_is_truncated(self):
        """A datetime at 00:00:00 is truncated to its date."""
        self.assertEqual(history_backlog.DateRange.parse(value="2026-08-14 00:00:00"), "2026-08-14")

    def test_invalid_date_exits_with_code_2(self):
        """Bad input exits with code 2 and an error on stderr."""
        err = io.StringIO()
        with self.assertRaises(SystemExit) as ctx, redirect_stderr(err):
            history_backlog.DateRange.parse(value="2026-13-45")
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("invalid date", err.getvalue())


class TestDaterange(unittest.TestCase):
    """Tests for daterange."""

    def test_yields_inclusive_range(self):
        """Dates are yielded from start to end inclusive."""
        days = list(history_backlog.DateRange.days(
            start="2026-08-01",
            end="2026-08-03",
        ))
        self.assertEqual(days, ["2026-08-01", "2026-08-02", "2026-08-03"])

    def test_single_day(self):
        """A one-day range yields a single date."""
        days = list(history_backlog.DateRange.days(
            start="2026-08-01",
            end="2026-08-01",
        ))
        self.assertEqual(days, ["2026-08-01"])

    def test_end_before_start_exits_2(self):
        """An end before start prints an error and exits 2."""
        err = io.StringIO()
        with self.assertRaises(SystemExit) as ctx, redirect_stderr(err):
            list(history_backlog.DateRange.days(start="2026-08-03", end="2026-08-01"))
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("is before start", err.getvalue())

    def test_malformed_raises(self):
        """Malformed dates raise ValueError."""
        with self.assertRaises(ValueError):
            list(history_backlog.DateRange.days(start="nope", end="2026-08-01"))

    def test_accepts_normalized_datetime_dates(self):
        """Datetime-derived dates work in daterange."""
        days = list(history_backlog.DateRange.days(start="2026-08-14", end="2026-08-14"))
        self.assertEqual(days, ["2026-08-14"])


class TestIndexFile(unittest.TestCase):
    """Tests for index_file."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _write(self, name, content):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_indexes_tags_sections_and_size(self):
        """Sections and sorted unique tags are extracted with the byte size."""
        path = self._write("notes.md", "# Title\n\n#task #todo #task\n\n## One\ntext\n\n## Two\ntext\n")
        idx = history_backlog.BacklogIndex.build(path=path, file_date="2026-08-01")
        self.assertEqual(idx["date"], "2026-08-01")
        self.assertEqual(idx["file"], path)
        self.assertEqual(idx["sections"], ["One", "Two"])
        self.assertEqual(idx["tags"], ["task", "todo"])
        self.assertEqual(idx["size"], len("# Title\n\n#task #todo #task\n\n## One\ntext\n\n## Two\ntext\n"))

    def test_no_tags_or_sections(self):
        """Files without tags or headings yield empty lists."""
        path = self._write("plain.md", "just text")
        idx = history_backlog.BacklogIndex.build(path=path, file_date="2026-08-01")
        self.assertEqual(idx["tags"], [])
        self.assertEqual(idx["sections"], [])

    def test_sections_capped_at_30(self):
        """No more than 30 headings are collected."""
        body = "\n\n".join(f"## Section {i}" for i in range(40))
        path = self._write("many.md", body)
        sections = history_backlog.BacklogIndex.build(
            path=path,
            file_date="2026-08-01",
        )["sections"]
        self.assertEqual(len(sections), 30)


class TestFmtSize(unittest.TestCase):
    """Tests for fmt_size."""

    def test_bytes(self):
        """Small sizes render as bytes."""
        self.assertEqual(history_backlog.BacklogReport.format_size(size=512), "512 B")

    def test_kilobytes(self):
        """Kilobyte sizes render with one decimal."""
        self.assertEqual(history_backlog.BacklogReport.format_size(size=2048), "2.0 KB")

    def test_megabytes(self):
        """Megabyte sizes render with one decimal."""
        self.assertEqual(history_backlog.BacklogReport.format_size(size=2 * 1024 * 1024), "2.0 MB")


class TestRenderMarkdown(unittest.TestCase):
    """Tests for render_markdown."""

    def test_empty_placeholder(self):
        """An empty record list renders the no-files placeholder."""
        out = history_backlog.BacklogReport.render(
            records=[],
            from_date="2026-08-01",
            to_date="2026-08-01",
        )
        self.assertEqual(out, "# Backlog index for 2026-08-01\n\n_No files in this range._\n")

    def test_populated(self):
        """Records render with date, path, size, tags, and sections."""
        records = [{
            "file": "/tmp/2026-08-01_notes.md",
            "date": "2026-08-01",
            "size": 100,
            "tags": ["task", "todo"],
            "sections": ["One"],
        }]
        out = history_backlog.BacklogReport.render(
            records=records,
            from_date="2026-08-01",
            to_date="2026-08-01",
        )
        self.assertIn("# Backlog index for 2026-08-01", out)
        self.assertIn("## `2026-08-01_notes.md`", out)
        self.assertIn("- **Date:** 2026-08-01", out)
        self.assertIn("- **Size:** 100 B", out)
        self.assertIn("- **Tags:** #task #todo", out)
        self.assertIn("  - One", out)

    def test_range_title_spans_dates(self):
        """A multi-day range is reflected in the title."""
        out = history_backlog.BacklogReport.render(
            records=[],
            from_date="2026-08-01",
            to_date="2026-08-03",
        )
        self.assertIn("# Backlog index for 2026-08-01 \u2192 2026-08-03", out)


class TestMain(unittest.TestCase):
    """Tests for main against a temporary directory."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        for name in ("2026-08-01_notes.md", "2026-08-01_tasks.md", "2026-08-02_notes.md",
                     "2026-08-03_other.md", "2026-08-03_other.txt"):
            with open(os.path.join(self.tmp, name), "w", encoding="utf-8") as f:
                f.write(f"# {name}\n\n#task\n\n## Heading\n")
        self.files = sorted(n for n in ("2026-08-01_notes.md", "2026-08-01_tasks.md",
                                        "2026-08-02_notes.md", "2026-08-03_other.md"))

    @staticmethod
    def run_main(argv):
        """Run main with argv, returning (rc, stdout, stderr)."""
        buf = io.StringIO()
        err = io.StringIO()
        with patch.object(sys, "argv", ["history_backlog", *argv]), \
             redirect_stdout(buf), redirect_stderr(err):
            rc = history_backlog.BacklogApp().run()
        return rc, buf.getvalue(), err.getvalue()

    def test_json_output_matches_range(self):
        """Only .md files on included dates are indexed."""
        rc, out, _ = self.run_main([
            "--directory", self.tmp, "--start", "2026-08-01", "--end", "2026-08-02",
        ])
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(len(data), 3)
        self.assertEqual(sorted(r["date"] for r in data), ["2026-08-01", "2026-08-01", "2026-08-02"])

    def test_md_output(self):
        """--md renders a markdown document."""
        rc, out, _ = self.run_main([
            "--directory", self.tmp, "--md", "--start", "2026-08-01", "--end", "2026-08-01",
        ])
        self.assertEqual(rc, 0)
        self.assertIn("# Backlog index for 2026-08-01", out)
        self.assertIn("2026-08-01_notes.md", out)
        self.assertIn("2026-08-01_tasks.md", out)
        self.assertNotIn("2026-08-02_notes.md", out)

    def test_missing_directory_returns_1(self):
        """A missing directory prints an error and returns 1."""
        rc, _, err = self.run_main(["--directory", "/no/such/dir"])
        self.assertEqual(rc, 1)
        self.assertIn("directory not found", err)

    def test_no_files_in_range(self):
        """A range with no matching files yields an empty list."""
        rc, out, _ = self.run_main([
            "--directory", self.tmp, "--start", "2020-01-01", "--end", "2020-01-02",
        ])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out), [])

    def test_datetime_start_end_truncate_time(self):
        """Datetime strings for --start/--end truncate to their date."""
        rc, out, _ = self.run_main([
            "--directory", self.tmp,
            "--start", "2026-08-01 22:19:55", "--end", "2026-08-02 06:00:00",
        ])
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(len(data), 3)
        self.assertEqual(sorted(r["date"] for r in data), ["2026-08-01", "2026-08-01", "2026-08-02"])


if __name__ == "__main__":
    unittest.main()
