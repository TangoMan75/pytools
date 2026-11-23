#!/usr/bin/env python3
"""Tests for history_opencode module."""
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
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))

_SPEC = importlib.util.spec_from_file_location(
    "history_opencode", Path(__file__).parents[1] / "history-opencode.py"
)
history_opencode = importlib.util.module_from_spec(_SPEC)
sys.modules["history_opencode"] = history_opencode
_SPEC.loader.exec_module(history_opencode)

TZ_PARIS = history_opencode.Dates.TZ_PARIS

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
        self.assertEqual(history_opencode.Dates.parse_date("2026-08-13"), "2026-08-13")

    def test_invalid_exits_2(self):
        """Bad input exits with code 2."""
        err = io.StringIO()
        with self.assertRaises(SystemExit) as ctx, redirect_stderr(err):
            history_opencode.Dates.parse_date("nope")
        self.assertEqual(ctx.exception.code, 2)


class TestFlexibleParseDate(unittest.TestCase):
    """Tests for Dates.resolve_date."""

    def test_date_only(self):
        """YYYY-MM-DD is parsed."""
        self.assertEqual(history_opencode.Dates.resolve_date("2026-08-13"), "2026-08-13")

    def test_datetime_with_minutes(self):
        """YYYY-MM-DD HH:MM is parsed."""
        self.assertEqual(history_opencode.Dates.resolve_date("2026-08-13 10:30"), "2026-08-13")

    def test_datetime_with_seconds(self):
        """YYYY-MM-DD HH:MM:SS is parsed."""
        self.assertEqual(history_opencode.Dates.resolve_date("2026-08-13 10:30:45"), "2026-08-13")

    def test_epoch_seconds(self):
        """Epoch seconds are converted via local time."""
        self.assertEqual(
            history_opencode.Dates.resolve_date("1786579200"),
            datetime.fromtimestamp(1786579200).date().isoformat(),
        )

    def test_iso8601(self):
        """ISO 8601 timestamps are parsed."""
        self.assertEqual(
            history_opencode.Dates.resolve_date("2026-08-13T10:30:00+02:00"),
            "2026-08-13",
        )

    def test_iso8601_z_suffix(self):
        """A trailing Z is accepted as UTC."""
        self.assertEqual(
            history_opencode.Dates.resolve_date("2026-08-13T10:30:00Z"),
            "2026-08-13",
        )

    def test_invalid_raises(self):
        """Malformed input raises ValueError."""
        with self.assertRaises(ValueError):
            history_opencode.Dates.resolve_date("not-a-date")

    def test_empty_raises(self):
        """Empty input raises ValueError."""
        with self.assertRaises(ValueError):
            history_opencode.Dates.resolve_date("")


class TestComputePrevDate(unittest.TestCase):
    """Tests for Dates.compute_prev_date."""

    def test_previous_day(self):
        """The day before is returned."""
        self.assertEqual(history_opencode.Dates.compute_prev_date("2026-08-13"), "2026-08-12")

    def test_month_boundary(self):
        """The first of a month rolls back to the previous month."""
        self.assertEqual(history_opencode.Dates.compute_prev_date("2026-03-01"), "2026-02-28")


class TestComputeEpochRange(unittest.TestCase):
    """Tests for Dates.compute_epoch_range."""

    def test_paris_midnight_bounds(self):
        """The range spans the day in Europe/Paris (UTC+2)."""
        start, end = history_opencode.Dates.compute_epoch_range("2026-08-13")
        self.assertEqual(start, int(datetime(2026, 8, 13, tzinfo=TZ_PARIS).timestamp() * 1000))
        self.assertEqual(end, int(datetime(2026, 8, 14, tzinfo=TZ_PARIS).timestamp() * 1000))


class TestComputeWindowRanges(unittest.TestCase):
    """Tests for week/month window ranges."""

    def test_week_range_is_seven_days(self):
        """Dates.compute_week_range spans the target day and six prior days."""
        start, end = history_opencode.Dates.compute_week_range("2026-08-13")
        self.assertEqual(start, history_opencode.Dates.compute_epoch_range("2026-08-07")[0])
        self.assertEqual(end - start, 7 * 86400 * 1000)

    def test_month_range_is_thirty_one_days(self):
        """Dates.compute_month_range spans the target day and thirty prior days."""
        start, end = history_opencode.Dates.compute_month_range("2026-08-13")
        self.assertEqual(start, history_opencode.Dates.compute_epoch_range("2026-07-14")[0])
        self.assertEqual(end - start, 31 * 86400 * 1000)


class TestComputeCalendarRange(unittest.TestCase):
    """Tests for Dates.compute_calendar_range."""

    def test_paris_day_bounds(self):
        """The range runs 00:00:00 to 23:59:59 in Paris time."""
        tmin, tmax = history_opencode.Dates.compute_calendar_range("2026-08-13")
        self.assertEqual(tmin, datetime(2026, 8, 13, tzinfo=TZ_PARIS).isoformat())
        self.assertEqual(tmax, datetime(2026, 8, 13, 23, 59, 59, tzinfo=TZ_PARIS).isoformat())


class TestDaterange(unittest.TestCase):
    """Tests for Dates.daterange."""

    def test_inclusive_range(self):
        """Dates are yielded inclusive of both ends."""
        self.assertEqual(
            list(history_opencode.Dates.daterange(start="2026-08-01", end="2026-08-03")),
            ["2026-08-01", "2026-08-02", "2026-08-03"],
        )

    def test_end_before_start_exits_2(self):
        """Reversed ranges exit 2."""
        err = io.StringIO()
        with self.assertRaises(SystemExit) as ctx, redirect_stderr(err):
            list(history_opencode.Dates.daterange(start="2026-08-03", end="2026-08-01"))
        self.assertEqual(ctx.exception.code, 2)


#--------------------------------------------------
# Date-range resolution
#--------------------------------------------------


class TestResolveRange(unittest.TestCase):
    """Tests for DateRangeArgs.parse_human, resolve, and resolve_date_range."""

    def test_parse_human(self):
        """Both accepted formats parse with the correct flag."""
        dt, had = history_opencode.DateRangeArgs.parse_human("2026-08-13 10:30:45")
        self.assertEqual(dt, datetime(2026, 8, 13, 10, 30, 45))
        self.assertTrue(had)
        _, had = history_opencode.DateRangeArgs.parse_human("2026-08-13")
        self.assertFalse(had)

    def test_human_start(self):
        """A date-only start resolves to local midnight."""
        from_ms, _ = history_opencode.DateRangeArgs.resolve(make_args(start="2026-08-13"))
        self.assertEqual(from_ms, int(datetime(2026, 8, 13).timestamp() * 1000))

    def test_epoch_ms_passthrough(self):
        """--start-ms / --end-ms pass through unchanged."""
        self.assertEqual(
            history_opencode.DateRangeArgs.resolve(make_args(start_ms=1000, end_ms=2000)),
            (1000, 2000),
        )

    def test_conflicting_start_raises(self):
        """Supplying both --start and --start-ms raises."""
        with self.assertRaises(ValueError):
            history_opencode.DateRangeArgs.resolve(make_args(start="2026-08-13", start_ms=1000))

    def test_end_before_start_raises(self):
        """An end before start raises ValueError."""
        with self.assertRaises(ValueError):
            history_opencode.DateRangeArgs.resolve(make_args(start="2026-08-14", end="2026-08-13"))

    def test_resolve_date_range_exits_2(self):
        """DateRangeArgs.resolve_date_range exits 2 on error."""
        err = io.StringIO()
        with self.assertRaises(SystemExit) as ctx, redirect_stderr(err):
            history_opencode.DateRangeArgs.resolve_date_range(
                make_args(start="2026-08-14", end="2026-08-13")
            )
        self.assertEqual(ctx.exception.code, 2)

    def test_add_date_range_args(self):
        """The helper registers the four date options."""
        parser = argparse.ArgumentParser()
        history_opencode.DateRangeArgs.add_date_range_args(parser)
        args = parser.parse_args(["--start", "2026-08-13", "--end-ms", "5000"])
        self.assertEqual(args.start, "2026-08-13")
        self.assertEqual(args.end_ms, 5000)


#--------------------------------------------------
# Formatting helpers
#--------------------------------------------------


class TestFormatting(unittest.TestCase):
    """Tests for Formatting helpers."""

    def test_to_local_has_offset(self):
        """Formatting.to_local returns a local ISO-8601 timestamp."""
        out = history_opencode.Formatting.to_local(1786579200000)
        parsed = datetime.fromisoformat(out)
        self.assertIsNotNone(parsed.tzinfo)

    def test_fmt_duration(self):
        """Durations render compactly by magnitude."""
        self.assertEqual(history_opencode.Formatting.format_duration(0), "0s")
        self.assertEqual(history_opencode.Formatting.format_duration(45), "45s")
        self.assertEqual(history_opencode.Formatting.format_duration(90), "1m30s")
        self.assertEqual(history_opencode.Formatting.format_duration(3661), "1h01m")

    def test_fmt_cost(self):
        """Costs render with sensible precision."""
        self.assertEqual(history_opencode.Formatting.format_cost(None), "$0")
        self.assertEqual(history_opencode.Formatting.format_cost(0), "$0")
        self.assertEqual(history_opencode.Formatting.format_cost(0.005), "$0.0050")
        self.assertEqual(history_opencode.Formatting.format_cost(1.2345), "$1.234")

    def test_fmt_hhmm(self):
        """Only the time part is kept."""
        self.assertEqual(
            history_opencode.Formatting.format_hhmm("2026-08-13T10:30:00+02:00"), "10:30"
        )
        self.assertEqual(history_opencode.Formatting.format_hhmm(""), "")

    def test_fmt_range_title(self):
        """Single-day and multi-day titles."""
        a = int(datetime(2026, 8, 13).timestamp() * 1000)
        b = int(datetime(2026, 8, 15).timestamp() * 1000)
        self.assertEqual(
            history_opencode.Formatting.format_range_title(from_ms=a, to_ms=a), "2026-08-13"
        )
        self.assertEqual(
            history_opencode.Formatting.format_range_title(from_ms=a, to_ms=b),
            "2026-08-13 \u2192 2026-08-15",
        )

    def test_md_escape(self):
        """Pipes and newlines are escaped."""
        self.assertEqual(history_opencode.Formatting.escape("a|b\nc"), "a\\|b c")
        self.assertEqual(history_opencode.Formatting.escape(None), "")

    def test_truncate(self):
        """Long strings are truncated with an ellipsis."""
        self.assertEqual(
            history_opencode.Formatting.truncate(text="hello world", limit=5), "hell\u2026"
        )
        self.assertEqual(history_opencode.Formatting.truncate(text=None, limit=5), "")


class TestIsToolArtefact(unittest.TestCase):
    """Tests for Formatting.is_tool_artefact."""

    def test_empty_text(self):
        """Empty or blank text is an artefact."""
        self.assertTrue(history_opencode.Formatting.is_tool_artefact(""))
        self.assertTrue(history_opencode.Formatting.is_tool_artefact("   "))
        self.assertTrue(history_opencode.Formatting.is_tool_artefact(None))

    def test_called_the_prefix(self):
        """'Called the ...' tool messages are artefacts."""
        self.assertTrue(history_opencode.Formatting.is_tool_artefact("Called the Read tool"))

    def test_angle_bracket_blocks(self):
        """XML-like blocks are artefacts."""
        self.assertTrue(history_opencode.Formatting.is_tool_artefact("<result>data</result>"))

    def test_short_text(self):
        """Text shorter than 40 chars is an artefact."""
        self.assertTrue(history_opencode.Formatting.is_tool_artefact("short"))

    def test_real_message(self):
        """A long plain message is not an artefact."""
        text = "This is a sufficiently long assistant message body for testing."
        self.assertFalse(history_opencode.Formatting.is_tool_artefact(text))


class TestNormalize(unittest.TestCase):
    """Tests for Formatting.normalize."""

    def test_strips_and_joins_lines(self):
        """CRLF is normalized and whitespace is stripped."""
        self.assertEqual(history_opencode.Formatting.normalize("  a\r\nb  "), "a\nb")

    def test_empty(self):
        """Empty input yields an empty string."""
        self.assertEqual(history_opencode.Formatting.normalize(None), "")
        self.assertEqual(history_opencode.Formatting.normalize(""), "")


class TestDefaultEndMs(unittest.TestCase):
    """Tests for Dates.default_end_ms."""

    def test_returns_local_midnight_of_next_day(self):
        """The exclusive end is midnight after the from_ms day."""
        from_ms = int(datetime(2026, 1, 1, 15, 30).timestamp() * 1000)
        expected = int(datetime(2026, 1, 2).timestamp() * 1000)
        self.assertEqual(history_opencode.Dates.default_end_ms(from_ms), expected)


#--------------------------------------------------
# Rendering
#--------------------------------------------------


def sample_session(**overrides):
    """Build a session record dict with the given overrides."""
    base = {
        "start_local": "2026-08-13T10:30:00+02:00",
        "duration_seconds": 300,
        "model": "gpt-4o",
        "agent": "main",
        "title": "Fix bug",
        "files": 3,
        "additions": 10,
        "deletions": 2,
        "cost": 0.05,
        "tokens_in": 1000,
        "tokens_out": 500,
    }
    base.update(overrides)
    return base


class TestRenderMarkdownSessions(unittest.TestCase):
    """Tests for Markdown.sessions."""

    def test_empty_placeholder(self):
        """An empty record list renders the placeholder."""
        self.assertEqual(
            history_opencode.Markdown.sessions([]), "_No sessions in this range._\n"
        )

    def test_table_and_totals(self):
        """A populated list renders a row plus totals."""
        records = [sample_session()]
        out = history_opencode.Markdown.sessions(records)
        self.assertIn("| Start | Duration | Model | Agent | Title | Files | +/- | Cost |", out)
        self.assertIn("| 10:30 | 5m00s | gpt-4o | main | Fix bug | 3 | 10/2 | $0.050 |", out)
        self.assertIn(
            "**Total:** 1 sessions, 5m00s total, 1,000 in / 500 out tokens, $0.050, 3 files edited",
            out,
        )


class TestRenderMarkdownMessages(unittest.TestCase):
    """Tests for Markdown.messages."""

    def test_empty_placeholder(self):
        """An empty record list renders the placeholder."""
        self.assertEqual(
            history_opencode.Markdown.messages([]),
            "_No session messages in this range._\n",
        )

    def test_message_blocks(self):
        """First user, last assistant, and reasoning are rendered."""
        records = [
            {
                "id": "s1",
                "first_user": "Hello",
                "last_assistant": "Long enough assistant reply text here.",
                "last_reasoning": "Thinking step",
            }
        ]
        out = history_opencode.Markdown.messages(records)
        self.assertIn("## `s1`", out)
        self.assertIn("> Hello", out)
        self.assertIn("**Last assistant:**", out)
        self.assertIn("**Last reasoning:**", out)

    def test_missing_values(self):
        """Missing values render placeholders and omit reasoning."""
        out = history_opencode.Markdown.messages(
            [{"id": "s1", "first_user": None, "last_assistant": None}]
        )
        self.assertIn("> _(none)_", out)
        self.assertNotIn("**Last reasoning:**", out)


#--------------------------------------------------
# Database helpers
#--------------------------------------------------


class TestDefaultDbPath(unittest.TestCase):
    """Tests for SessionRepository.default_path."""

    def test_windows(self):
        """Windows uses %APPDATA%."""
        with patch("history_opencode.platform.system", return_value="Windows"), \
             patch.dict(os.environ, {"APPDATA": "C:\\AppData"}, clear=False):
            self.assertEqual(
                history_opencode.SessionRepository.default_path(),
                os.path.join("C:\\AppData", "opencode", "opencode.db"),
            )

    def test_macos(self):
        """macOS uses Application Support."""
        with patch("history_opencode.platform.system", return_value="Darwin"):
            self.assertEqual(
                history_opencode.SessionRepository.default_path(),
                os.path.expanduser("~/Library/Application Support/opencode/opencode.db"),
            )

    def test_linux(self):
        """Linux uses ~/.local/share."""
        with patch("history_opencode.platform.system", return_value="Linux"):
            self.assertEqual(
                history_opencode.SessionRepository.default_path(),
                os.path.expanduser("~/.local/share/opencode/opencode.db"),
            )


LONG_ASSISTANT = "This is a sufficiently long assistant reply for tests."


def build_opencode_db(path):
    """Create a full opencode database at the given path."""
    con = sqlite3.connect(path)
    build_opencode_db_into(con)
    con.close()


class TestFetchSessions(unittest.TestCase):
    """Tests for SessionRepository.fetch_sessions on the v1 schema."""

    def test_filters_and_parses(self):
        """Only sessions in range are returned with parsed model fields."""
        con = sqlite3.connect(":memory:")
        build_opencode_db_into(con)
        repository = history_opencode.SessionRepository(connection=con)
        records = repository.fetch_sessions(from_ms=0, to_ms=100000)
        con.close()
        self.assertEqual([r["id"] for r in records], ["s1"])
        r = records[0]
        self.assertEqual(r["model"], "gpt-4o")
        self.assertEqual(r["provider"], "openai")
        self.assertEqual(r["duration_seconds"], 59.0)
        self.assertEqual(r["files"], 3)

    def test_bad_model_json(self):
        """Malformed model JSON yields an empty model string."""
        con = sqlite3.connect(":memory:")
        build_opencode_db_into(con)
        repository = history_opencode.SessionRepository(connection=con)
        records = repository.fetch_sessions(from_ms=100000, to_ms=200000)
        con.close()
        self.assertEqual(records[0]["model"], "")


def build_opencode_db_into(con):
    """Create the opencode session/message/part tables in the connection."""
    cur = con.cursor()
    cur.execute("CREATE TABLE session (id TEXT, title TEXT, directory TEXT, time_created INTEGER, "
                "time_updated INTEGER, model TEXT, agent TEXT, cost REAL, tokens_input INTEGER, "
                "tokens_output INTEGER, summary_files INTEGER, summary_additions INTEGER, "
                "summary_deletions INTEGER)")
    cur.execute("CREATE TABLE message (id INTEGER, session_id TEXT, time_created INTEGER, data TEXT)")
    cur.execute("CREATE TABLE part (id INTEGER, message_id INTEGER, time_created INTEGER, data TEXT)")
    cur.executemany(
        "INSERT INTO session VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("s1", "Fix bug", "/repo", 1000, 60000,
             '{"id": "gpt-4o", "providerID": "openai"}', "main", 0.02,
             1000, 500, 3, 10, 2),
            ("s2", "Outside", "/repo", 100000, 150000,
             "not-json", "main", 0.0, 0, 0, 0, 0, 0),
        ],
    )
    cur.executemany(
        "INSERT INTO message VALUES (?,?,?,?)",
        [
            (1, "s1", 10, '{"role": "user"}'),
            (2, "s1", 20, '{"role": "assistant"}'),
            (3, "s1", 30, '{"role": "assistant"}'),
            (4, "s1", 40, '{"role": "assistant"}'),
        ],
    )
    cur.executemany(
        "INSERT INTO part VALUES (?,?,?,?)",
        [
            (1, 1, 10, '{"type": "text", "text": "Hello"}'),
            (2, 2, 20, '{"type": "text", "text": "Called the Read tool to check"}'),
            (3, 3, 30, '{"type": "reasoning", "text": "Let me think"}'),
            (4, 4, 40, '{"type": "text", "text": "' + LONG_ASSISTANT + '"}'),
        ],
    )
    con.commit()


def build_opencode_db_v2(path):
    """Create a full opencode v2 database at the given path."""
    con = sqlite3.connect(path)
    build_opencode_db_v2_into(con)
    con.close()


def build_opencode_db_v2_into(con):
    """Create the opencode v2 session_v2/session_message tables in the connection."""
    cur = con.cursor()
    cur.execute("CREATE TABLE session_v2 (id TEXT, title TEXT, directory TEXT, time_created INTEGER, "
                "time_updated INTEGER, model TEXT, agent TEXT, cost REAL, tokens_input INTEGER, "
                "tokens_output INTEGER, summary_files INTEGER, summary_additions INTEGER, "
                "summary_deletions INTEGER)")
    cur.execute("CREATE TABLE session_message (id TEXT, session_id TEXT, type TEXT, seq INTEGER, "
                "time_created INTEGER, time_updated INTEGER, data TEXT)")
    cur.executemany(
        "INSERT INTO session_v2 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("s1", "Fix bug", "/repo", 1000, 60000,
             '{"id": "gpt-4o", "providerID": "openai"}', "main", 0.02,
             1000, 500, 3, 10, 2),
            ("s2", "Outside", "/repo", 100000, 150000,
             "not-json", "main", 0.0, 0, 0, 0, 0, 0),
        ],
    )
    cur.executemany(
        "INSERT INTO session_message VALUES (?,?,?,?,?,?,?)",
        [
            ("m1", "s1", "user", 1, 10, 10, '{"time": {}, "text": "Hello"}'),
            ("m2", "s1", "assistant", 2, 20, 20,
             '{"content": [{"type": "reasoning", "text": "Let me think"}, '
             '{"type": "text", "text": "Called the Read tool to check"}]}'),
            ("m3", "s1", "assistant", 3, 30, 30,
             '{"content": [{"type": "text", "text": "' + LONG_ASSISTANT + '"}]}'),
            ("m4", "s1", "assistant", 4, 40, 40, "not-json"),
            ("m5", "s1", "idle", 5, 50, 50, '{"outcome": "completed"}'),
        ],
    )
    con.commit()


class TestSchemaDetection(unittest.TestCase):
    """Tests for the repository schema helpers."""

    def test_v1_schema(self):
        """A v1 database reports the session table."""
        con = sqlite3.connect(":memory:")
        build_opencode_db_into(con)
        repository = history_opencode.SessionRepository(connection=con)
        self.assertFalse(repository.is_v2())
        self.assertEqual(repository.session_table(), "session")
        con.close()

    def test_v2_schema(self):
        """A v2 database reports the session_v2 table."""
        con = sqlite3.connect(":memory:")
        build_opencode_db_v2_into(con)
        repository = history_opencode.SessionRepository(connection=con)
        self.assertTrue(repository.is_v2())
        self.assertEqual(repository.session_table(), "session_v2")
        con.close()

    def test_unknown_schema(self):
        """A database without session tables raises OperationalError."""
        con = sqlite3.connect(":memory:")
        repository = history_opencode.SessionRepository(connection=con)
        with self.assertRaises(sqlite3.OperationalError):
            repository.session_table()
        con.close()


class TestFetchSessionsV2(unittest.TestCase):
    """Tests for SessionRepository.fetch_sessions on the v2 schema."""

    def test_filters_and_parses(self):
        """v2 sessions use the same columns and are filtered the same way."""
        con = sqlite3.connect(":memory:")
        build_opencode_db_v2_into(con)
        repository = history_opencode.SessionRepository(connection=con)
        records = repository.fetch_sessions(from_ms=0, to_ms=100000)
        con.close()
        self.assertEqual([r["id"] for r in records], ["s1"])
        r = records[0]
        self.assertEqual(r["model"], "gpt-4o")
        self.assertEqual(r["provider"], "openai")
        self.assertEqual(r["duration_seconds"], 59.0)
        self.assertEqual(r["files"], 3)


class TestFetchMessages(unittest.TestCase):
    """Tests for SessionRepository.fetch_messages on the v1 schema."""

    def test_extracts_first_user_last_assistant_and_reasoning(self):
        """Tool artefacts are ignored; the last real assistant reply wins."""
        con = sqlite3.connect(":memory:")
        build_opencode_db_into(con)
        repository = history_opencode.SessionRepository(connection=con)
        result = repository.fetch_messages(session_ids=["s1"])
        con.close()
        entry = result["s1"]
        self.assertEqual(entry["first_user"], "Hello")
        self.assertEqual(entry["last_assistant"], LONG_ASSISTANT)
        self.assertEqual(entry["last_reasoning"], "Let me think")

    def test_missing_session(self):
        """An unknown session id yields empty fields."""
        con = sqlite3.connect(":memory:")
        build_opencode_db_into(con)
        repository = history_opencode.SessionRepository(connection=con)
        result = repository.fetch_messages(session_ids=["missing"])
        con.close()
        self.assertEqual(
            result["missing"],
            {"first_user": None, "last_assistant": None, "last_reasoning": None},
        )


class TestFetchMessagesV2(unittest.TestCase):
    """Tests for SessionRepository.fetch_messages on the v2 schema."""

    def test_extracts_from_embedded_content(self):
        """User text and assistant content parts are read from message JSON."""
        con = sqlite3.connect(":memory:")
        build_opencode_db_v2_into(con)
        repository = history_opencode.SessionRepository(connection=con)
        result = repository.fetch_messages(session_ids=["s1"])
        con.close()
        entry = result["s1"]
        self.assertEqual(entry["first_user"], "Hello")
        self.assertEqual(entry["last_assistant"], LONG_ASSISTANT)
        self.assertEqual(entry["last_reasoning"], "Let me think")

    def test_ignores_non_chat_messages_and_bad_json(self):
        """Idle events and malformed rows are skipped."""
        con = sqlite3.connect(":memory:")
        build_opencode_db_v2_into(con)
        repository = history_opencode.SessionRepository(connection=con)
        result = repository.fetch_messages(session_ids=["s1"])
        con.close()
        self.assertEqual(len(result), 1)
        self.assertEqual(result["s1"]["last_assistant"], LONG_ASSISTANT)

    def test_missing_session(self):
        """An unknown session id yields empty fields."""
        con = sqlite3.connect(":memory:")
        build_opencode_db_v2_into(con)
        repository = history_opencode.SessionRepository(connection=con)
        result = repository.fetch_messages(session_ids=["missing"])
        con.close()
        self.assertEqual(
            result["missing"],
            {"first_user": None, "last_assistant": None, "last_reasoning": None},
        )


#--------------------------------------------------
# CLI
#--------------------------------------------------


class _MainTestBase(unittest.TestCase):
    """Shared Application tests; subclasses pick the database schema."""

    db_builder = staticmethod(build_opencode_db)

    def setUp(self):
        self.fd, self.db = tempfile.mkstemp(suffix=".db")
        os.close(self.fd)
        self.db_builder(self.db)

    def tearDown(self):
        os.unlink(self.db)

    @staticmethod
    def run_main(argv):
        """Run the application with argv, returning (rc, stdout)."""
        buf = io.StringIO()
        rc = history_opencode.Application(
            argv=["history_opencode", *argv], stdout=buf
        ).run()
        return rc, buf.getvalue()

    def test_json_output(self):
        """Sessions are emitted as JSON with attached messages."""
        rc, out = self.run_main(["--db", self.db, "--start-ms", "0", "--end-ms", "100000"])
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], "s1")
        self.assertEqual(data[0]["first_user"], "Hello")
        self.assertEqual(data[0]["last_assistant"], LONG_ASSISTANT)
        self.assertEqual(data[0]["last_reasoning"], "Let me think")

    def test_md_output(self):
        """--md renders sessions and message sections."""
        rc, out = self.run_main(
            ["--db", self.db, "--md", "--start-ms", "0", "--end-ms", "100000"]
        )
        self.assertEqual(rc, 0)
        self.assertIn("# opencode Memory", out)
        self.assertIn("## Sessions", out)
        self.assertIn("## Session Messages", out)
        self.assertIn("Fix bug", out)

    def test_empty_range(self):
        """A range matching nothing yields an empty session list."""
        rc, out = self.run_main(
            ["--db", self.db, "--start-ms", "200000", "--end-ms", "300000"]
        )
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out), [])


class TestMain(_MainTestBase):
    """Tests for Application against a v1 database."""

    db_builder = staticmethod(build_opencode_db)


class TestMainV2(_MainTestBase):
    """Tests for Application against a v2 database."""

    db_builder = staticmethod(build_opencode_db_v2)


class TestMainMissingSchema(unittest.TestCase):
    """Tests for Application against a database without OpenCode tables."""

    def test_reports_missing_table(self):
        """An unknown schema reports an error and exits 1."""
        fd, db = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        err = io.StringIO()
        try:
            rc = history_opencode.Application(
                argv=["history_opencode", "--db", db], stderr=err
            ).run()
        finally:
            os.unlink(db)
        self.assertEqual(rc, 1)
        self.assertIn("no opencode session table", err.getvalue())


if __name__ == "__main__":
    unittest.main()
