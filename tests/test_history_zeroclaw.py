#!/usr/bin/env python3
"""Tests for history_zeroclaw module."""
# noqa: E402


import argparse
import io
import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

_SPEC = importlib.util.spec_from_file_location(
    "history_zeroclaw", Path(__file__).parents[1] / "history-zeroclaw.py"
)
history_zeroclaw = importlib.util.module_from_spec(_SPEC)
sys.modules["history_zeroclaw"] = history_zeroclaw
_SPEC.loader.exec_module(history_zeroclaw)

TZ_PARIS = history_zeroclaw.Dates.TZ_PARIS

# These tests intentionally exercise private helpers.
# noqa: SLF001, E402


def make_args(**kwargs):
    """Build an argparse Namespace from the given date-range values."""
    base = {"start": None, "end": None, "start_ms": None, "end_ms": None}
    base.update(kwargs)
    return argparse.Namespace(**base)


#--------------------------------------------------
# Date helpers
#--------------------------------------------------


class TestParseDate(unittest.TestCase):
    """Tests for Dates.parse_date."""

    def test_valid(self):
        """A valid date passes through."""
        self.assertEqual(history_zeroclaw.Dates.parse_date("2026-08-13"), "2026-08-13")

    def test_invalid_exits_2(self):
        """Bad input exits with code 2."""
        err = io.StringIO()
        with self.assertRaises(SystemExit) as ctx, redirect_stderr(err):
            history_zeroclaw.Dates.parse_date("nope")
        self.assertEqual(ctx.exception.code, 2)


class TestFlexibleParseDate(unittest.TestCase):
    """Tests for Dates.resolve_date."""

    def test_date_only(self):
        """YYYY-MM-DD is parsed."""
        self.assertEqual(history_zeroclaw.Dates.resolve_date("2026-08-13"), "2026-08-13")

    def test_datetime_with_seconds(self):
        """YYYY-MM-DD HH:MM:SS is parsed."""
        self.assertEqual(
            history_zeroclaw.Dates.resolve_date("2026-08-13 10:30:45"), "2026-08-13"
        )

    def test_iso8601(self):
        """ISO 8601 timestamps are parsed."""
        self.assertEqual(
            history_zeroclaw.Dates.resolve_date("2026-08-13T10:30:00+02:00"),
            "2026-08-13",
        )

    def test_invalid_raises(self):
        """Malformed input raises ValueError."""
        with self.assertRaises(ValueError):
            history_zeroclaw.Dates.resolve_date("not-a-date")


class TestComputeEpochRange(unittest.TestCase):
    """Tests for Dates.compute_epoch_range."""

    def test_paris_midnight_bounds(self):
        """The range spans the day in Europe/Paris (UTC+2)."""
        start, end = history_zeroclaw.Dates.compute_epoch_range("2026-08-13")
        self.assertEqual(start, int(datetime(2026, 8, 13, tzinfo=TZ_PARIS).timestamp() * 1000))
        self.assertEqual(end, int(datetime(2026, 8, 14, tzinfo=TZ_PARIS).timestamp() * 1000))


class TestComputeWindowRanges(unittest.TestCase):
    """Tests for week/month window ranges."""

    def test_week_range_is_seven_days(self):
        """Dates.compute_week_range spans the target day and six prior days."""
        start, end = history_zeroclaw.Dates.compute_week_range("2026-08-13")
        self.assertEqual(start, history_zeroclaw.Dates.compute_epoch_range("2026-08-07")[0])
        self.assertEqual(end - start, 7 * 86400 * 1000)

    def test_month_range(self):
        """Dates.compute_month_range spans the target day and thirty prior days."""
        start, end = history_zeroclaw.Dates.compute_month_range("2026-08-13")
        self.assertEqual(start, history_zeroclaw.Dates.compute_epoch_range("2026-07-14")[0])
        self.assertEqual(end - start, 31 * 86400 * 1000)


class TestComputeCalendarRange(unittest.TestCase):
    """Tests for Dates.compute_calendar_range."""

    def test_paris_day_bounds(self):
        """The range runs 00:00:00 to 23:59:59 in Paris time."""
        tmin, tmax = history_zeroclaw.Dates.compute_calendar_range("2026-08-13")
        self.assertEqual(tmin, datetime(2026, 8, 13, tzinfo=TZ_PARIS).isoformat())
        self.assertEqual(tmax, datetime(2026, 8, 13, 23, 59, 59, tzinfo=TZ_PARIS).isoformat())


class TestResolveRange(unittest.TestCase):
    """Tests for DateRangeArgs.resolve."""

    def test_human_start(self):
        """A date-only start resolves to local midnight."""
        from_ms, _ = history_zeroclaw.DateRangeArgs.resolve(make_args(start="2026-08-13"))
        self.assertEqual(from_ms, int(datetime(2026, 8, 13).timestamp() * 1000))

    def test_epoch_ms_passthrough(self):
        """--start-ms / --end-ms pass through unchanged."""
        self.assertEqual(
            history_zeroclaw.DateRangeArgs.resolve(make_args(start_ms=1000, end_ms=2000)),
            (1000, 2000),
        )

    def test_end_before_start_raises(self):
        """An end before start raises ValueError."""
        with self.assertRaises(ValueError):
            history_zeroclaw.DateRangeArgs.resolve(
                make_args(start="2026-08-14", end="2026-08-13")
            )


#--------------------------------------------------
# Timestamp parsing
#--------------------------------------------------


class TestParseIso(unittest.TestCase):
    """Tests for Dates.parse_iso."""

    def test_z_suffix(self):
        """A trailing Z is treated as UTC."""
        expected = int(datetime(2026, 8, 13, 10, 30, tzinfo=timezone.utc).timestamp() * 1000)
        self.assertEqual(history_zeroclaw.Dates.parse_iso("2026-08-13T10:30:00Z"), expected)

    def test_offset(self):
        """An explicit offset is honored."""
        expected = int(
            datetime(2026, 8, 13, 10, 30, tzinfo=timezone(timedelta(hours=2))).timestamp() * 1000
        )
        self.assertEqual(
            history_zeroclaw.Dates.parse_iso("2026-08-13T10:30:00+02:00"), expected
        )

    def test_naive_treated_as_utc(self):
        """A naive timestamp is treated as UTC."""
        expected = int(datetime(2026, 8, 13, 10, 30, tzinfo=timezone.utc).timestamp() * 1000)
        self.assertEqual(history_zeroclaw.Dates.parse_iso("2026-08-13T10:30:00"), expected)

    def test_empty_returns_zero(self):
        """Empty input yields zero."""
        self.assertEqual(history_zeroclaw.Dates.parse_iso(""), 0)


class TestStripUserPrefix(unittest.TestCase):
    """Tests for Formatting.strip_user_prefix."""

    def test_strips_timestamp_with_offset(self):
        """A full bracketed timestamp is removed."""
        self.assertEqual(
            history_zeroclaw.Formatting.strip_user_prefix(
                "[2026-08-13 10:00:00 +02:00] Hello there"
            ),
            "Hello there",
        )

    def test_strips_timestamp_without_offset(self):
        """A bracketed timestamp without an offset is removed."""
        self.assertEqual(
            history_zeroclaw.Formatting.strip_user_prefix("[2026-08-13 10:00:00] Hi"),
            "Hi",
        )

    def test_no_prefix_unchanged(self):
        """Plain content is returned unchanged."""
        self.assertEqual(
            history_zeroclaw.Formatting.strip_user_prefix("just text"), "just text"
        )

    def test_empty(self):
        """Empty input yields an empty string."""
        self.assertEqual(history_zeroclaw.Formatting.strip_user_prefix(""), "")
        self.assertEqual(history_zeroclaw.Formatting.strip_user_prefix(None), "")


#--------------------------------------------------
# Formatting helpers
#--------------------------------------------------


class TestFormatting(unittest.TestCase):
    """Tests for Formatting helpers."""

    def test_fmt_duration(self):
        """Durations render compactly by magnitude."""
        self.assertEqual(history_zeroclaw.Formatting.format_duration(0), "0s")
        self.assertEqual(history_zeroclaw.Formatting.format_duration(45), "45s")
        self.assertEqual(history_zeroclaw.Formatting.format_duration(90), "1m30s")
        self.assertEqual(history_zeroclaw.Formatting.format_duration(3661), "1h01m")

    def test_fmt_hms_and_date(self):
        """Time and date parts are extracted."""
        self.assertEqual(
            history_zeroclaw.Formatting.format_hms("2026-08-13T10:30:00+02:00"), "10:30:00"
        )
        self.assertEqual(
            history_zeroclaw.Formatting.format_date("2026-08-13T10:30:00+02:00"), "2026-08-13"
        )
        self.assertEqual(history_zeroclaw.Formatting.format_hms(""), "")

    def test_fmt_range_title(self):
        """Single-day and multi-day titles."""
        a = int(datetime(2026, 8, 13).timestamp() * 1000)
        b = int(datetime(2026, 8, 15).timestamp() * 1000)
        self.assertEqual(
            history_zeroclaw.Formatting.format_range_title(from_ms=a, to_ms=a), "2026-08-13"
        )
        self.assertEqual(
            history_zeroclaw.Formatting.format_range_title(from_ms=a, to_ms=b),
            "2026-08-13 \u2192 2026-08-15",
        )


#--------------------------------------------------
# Rendering
#--------------------------------------------------


def sample_zeroclaw_session(**overrides):
    """Build a zeroclaw session record dict with the given overrides."""
    base = {
        "id": "key-1",
        "title": "Daily",
        "start_local": "2026-08-13T10:30:00+02:00",
        "end_local": "2026-08-13T11:00:00+02:00",
        "duration_seconds": 1800,
        "channel_id": "channel-1",
        "sender_id": "sender-1",
        "state": "active",
        "time_created": 1000,
        "time_updated": 2000,
        "messages": [{
            "role": "user",
            "content": "Hello",
            "created_at_local": "2026-08-13T10:30:00+02:00",
        }],
    }
    base.update(overrides)
    return base


class TestRenderMarkdownSessions(unittest.TestCase):
    """Tests for Markdown.sessions."""

    def test_empty_placeholder(self):
        """An empty record list renders the placeholder."""
        self.assertEqual(
            history_zeroclaw.Markdown.sessions([]), "_No sessions in this range._\n"
        )

    def test_table_and_totals(self):
        """A populated list renders a row plus totals."""
        out = history_zeroclaw.Markdown.sessions([sample_zeroclaw_session()])
        self.assertIn("| Start | Duration | Channel | Title | Msgs | State |", out)
        self.assertIn("| 08-13 10:30:00 | 30m00s | channel-1 | Daily | 1 | active |", out)
        self.assertIn("**Total:** 1 sessions, 1 messages in range", out)


class TestRenderMessageBlock(unittest.TestCase):
    """Tests for Markdown.message_block."""

    def test_quotes_body(self):
        """The body is rendered as a blockquote with a stamp."""
        message = {
            "role": "user",
            "content": "Hello\nworld",
            "created_at_local": "2026-08-13T10:30:00+02:00",
        }
        out = history_zeroclaw.Markdown.message_block(message)
        self.assertIn("**`[2026-08-13 10:30:00] USER`**", out)
        self.assertIn("> Hello\n> world", out)

    def test_empty_body(self):
        """An empty body renders a placeholder."""
        message = {"role": "assistant", "content": "", "created_at_local": ""}
        out = history_zeroclaw.Markdown.message_block(message)
        self.assertIn("`[????-??-?? ??:??:??] ASSISTANT`", out)
        self.assertIn("> _(empty)_", out)


class TestRenderMarkdownMessages(unittest.TestCase):
    """Tests for Markdown.messages."""

    def test_empty_placeholder(self):
        """An empty record list renders the placeholder."""
        self.assertEqual(
            history_zeroclaw.Markdown.messages([]), "_No chat log in this range._\n"
        )

    def test_session_header_and_blocks(self):
        """Sessions render headers, meta, and message blocks."""
        out = history_zeroclaw.Markdown.messages([sample_zeroclaw_session()])
        self.assertIn("## `key-1`", out)
        self.assertIn("_Sender `sender-1`", out)
        self.assertIn("1 messages in range", out)
        self.assertIn("**`[2026-08-13 10:30:00] USER`**", out)

    def test_no_messages_in_range(self):
        """A session without messages renders a placeholder."""
        record = sample_zeroclaw_session(messages=[])
        out = history_zeroclaw.Markdown.messages([record])
        self.assertIn("_(no messages in this range)_", out)


class TestDefaultEndMs(unittest.TestCase):
    """Tests for Dates.default_end_ms."""

    def test_returns_local_midnight_of_next_day(self):
        """The exclusive end is midnight after the from_ms day."""
        from_ms = int(datetime(2026, 1, 1, 15, 30).timestamp() * 1000)
        expected = int(datetime(2026, 1, 2).timestamp() * 1000)
        self.assertEqual(history_zeroclaw.Dates.default_end_ms(from_ms), expected)


#--------------------------------------------------
# Database access
#--------------------------------------------------


def build_zeroclaw_db(path):
    """Create a full zeroclaw database at the given path."""
    con = sqlite3.connect(path)
    build_zeroclaw_db_into(con)
    con.close()


def build_zeroclaw_db_into(con):
    """Create the zeroclaw session tables in the given connection."""
    cur = con.cursor()
    cur.execute("CREATE TABLE session_metadata (session_key TEXT, name TEXT, created_at TEXT, "
                "last_activity TEXT, message_count INTEGER, state TEXT, agent_alias TEXT, "
                "channel_id TEXT, room_id TEXT, sender_id TEXT)")
    cur.executemany(
        "INSERT INTO session_metadata VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            ("key-1", "Daily", "2026-08-13T10:00:00+02:00", "2026-08-13T11:00:00+02:00",
             2, "active", "main", "channel-1", "room-1", "sender-1"),
            ("key-future", "Future", "2099-01-01T00:00:00+02:00", "2099-01-01T01:00:00+02:00",
             0, "active", "main", "channel-f", "room-f", "sender-f"),
        ],
    )
    cur.execute("CREATE TABLE sessions (id INTEGER PRIMARY KEY, session_key TEXT, role TEXT, "
                "content TEXT, created_at TEXT)")
    cur.executemany(
        "INSERT INTO sessions VALUES (?,?,?,?,?)",
        [
            (1, "key-1", "user", "[2026-08-13 10:05:00 +02:00] Hello there", "2026-08-13T10:05:00+02:00"),
            (2, "key-1", "assistant", "A reasonably long assistant reply", "2026-08-13T10:10:00+02:00"),
            (3, "key-1", "tool", '{"content": "tool stuff"}', "2026-08-13T10:11:00+02:00"),
            (4, "key-1", "user", "[2026-08-14 09:00:00 +02:00] Outside window", "2026-08-14T09:00:00+02:00"),
        ],
    )
    con.commit()


class TestFetchMessages(unittest.TestCase):
    """Tests for SessionRepository.fetch_messages."""

    def test_filters_roles_prefixes_and_range(self):
        """Only user/assistant messages in range are returned with prefixes stripped."""
        con = sqlite3.connect(":memory:")
        build_zeroclaw_db_into(con)
        from_ms = history_zeroclaw.Dates.parse_iso("2026-08-13T00:00:00+02:00")
        to_ms = history_zeroclaw.Dates.parse_iso("2026-08-13T23:59:59+02:00")
        repository = history_zeroclaw.SessionRepository(connection=con)
        messages = repository.fetch_messages(
            session_keys=["key-1"], from_ms=from_ms, to_ms=to_ms
        )
        con.close()
        self.assertEqual([m["role"] for m in messages["key-1"]], ["user", "assistant"])
        self.assertEqual(messages["key-1"][0]["content"], "Hello there")
        self.assertEqual(len(messages["key-1"]), 2)

    def test_unknown_session(self):
        """An unknown key yields an empty message list."""
        con = sqlite3.connect(":memory:")
        build_zeroclaw_db_into(con)
        repository = history_zeroclaw.SessionRepository(connection=con)
        messages = repository.fetch_messages(
            session_keys=["missing"], from_ms=0, to_ms=99999999999999
        )
        con.close()
        self.assertEqual(messages["missing"], [])


#--------------------------------------------------
# CLI
#--------------------------------------------------


class TestMain(unittest.TestCase):
    """Tests for Application against a temporary database."""

    def setUp(self):
        self.fd, self.db = tempfile.mkstemp(suffix=".db")
        os.close(self.fd)
        build_zeroclaw_db(self.db)

    def tearDown(self):
        os.unlink(self.db)

    @staticmethod
    def run_main(argv):
        """Run the application with argv, returning (rc, stdout)."""
        buf = io.StringIO()
        rc = history_zeroclaw.Application(
            argv=["history_zeroclaw", *argv], stdout=buf
        ).run()
        return rc, buf.getvalue()

    @staticmethod
    def _end_of_day():
        return history_zeroclaw.Dates.parse_iso("2026-08-14T00:00:00+02:00")

    def test_json_output(self):
        """Sessions are emitted as JSON with their message history."""
        rc, out = self.run_main(
            ["--db", self.db, "--start-ms", "0", "--end-ms", str(self._end_of_day())]
        )
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], "key-1")
        self.assertEqual([m["role"] for m in data[0]["messages"]], ["user", "assistant"])
        self.assertEqual(data[0]["messages"][0]["content"], "Hello there")

    def test_md_output(self):
        """--md renders sessions and chat log sections."""
        rc, out = self.run_main(
            ["--db", self.db, "--md", "--start-ms", "0", "--end-ms", str(self._end_of_day())]
        )
        self.assertEqual(rc, 0)
        self.assertIn("# zeroclaw Memory", out)
        self.assertIn("## Sessions", out)
        self.assertIn("## Chat Log", out)
        self.assertIn("Daily", out)

    def test_default_end_is_next_midnight(self):
        """Without --end, the range defaults to the start day only."""
        from_ms = int(datetime(2026, 8, 13, 12, 0).timestamp() * 1000)
        rc, out = self.run_main(["--db", self.db, "--start-ms", str(from_ms)])
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertIsInstance(data, list)


if __name__ == "__main__":
    unittest.main()
