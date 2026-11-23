#!/usr/bin/env python3
"""Tests for conv-ics module."""

import argparse
import importlib.util
import io
import os
import shutil
import ssl
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

_SPEC = importlib.util.spec_from_file_location(
    "conv_ics", Path(__file__).parents[1] / "conv-ics.py"
)
conv_ics = importlib.util.module_from_spec(_SPEC)
sys.modules["conv_ics"] = conv_ics
_SPEC.loader.exec_module(conv_ics)

FIXTURES = Path(__file__).parent / "fixtures"

# These tests intentionally exercise private parser and downloader helpers.
# noqa: SLF001


#--------------------------------------------------
# DateUtils
#--------------------------------------------------


class TestDateUtilsDetect(unittest.TestCase):
    """Tests for DateUtils.detect."""

    def test_detect_utc_datetime(self):
        """Detect utc datetime."""
        self.assertEqual(conv_ics.DateUtils.detect("20240101T100000Z"), "utc datetime")

    def test_detect_datetime(self):
        """Detect datetime."""
        self.assertEqual(conv_ics.DateUtils.detect("20240101T100000"), "datetime")

    def test_detect_date(self):
        """Detect date."""
        self.assertEqual(conv_ics.DateUtils.detect("20240101"), "date")

    def test_detect_empty(self):
        """Detect empty."""
        self.assertEqual(conv_ics.DateUtils.detect(""), "")

    def test_detect_unrecognized(self):
        """Detect unrecognized."""
        self.assertEqual(conv_ics.DateUtils.detect("not-a-date"), "")

    def test_detect_too_short(self):
        """Detect too short."""
        self.assertEqual(conv_ics.DateUtils.detect("2024"), "")

    def test_detect_too_long(self):
        """Detect too long."""
        self.assertEqual(conv_ics.DateUtils.detect("20240101T100000ZZ"), "")


class TestDateUtilsToIso(unittest.TestCase):
    """Tests for DateUtils.to_iso."""

    def test_utc_datetime(self):
        """Utc datetime."""
        self.assertEqual(conv_ics.DateUtils.to_iso("20240101T100000Z"), "2024-01-01 10:00:00Z")

    def test_datetime(self):
        """Datetime."""
        self.assertEqual(conv_ics.DateUtils.to_iso("20240101T100000"), "2024-01-01 10:00:00")

    def test_date(self):
        """Date."""
        self.assertEqual(conv_ics.DateUtils.to_iso("20240101"), "2024-01-01")

    def test_unrecognized_returns_input(self):
        """Unrecognized returns input."""
        self.assertEqual(conv_ics.DateUtils.to_iso("hello"), "hello")


class TestDateUtilsToLocal(unittest.TestCase):
    """Tests for DateUtils.to_local."""

    def test_utc_converts_to_local(self):
        """Utc converts to local."""
        result = conv_ics.DateUtils.to_local("20240101T100000Z")
        self.assertRegex(result, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")

    def test_non_utc_returns_iso(self):
        """Non utc returns iso."""
        self.assertEqual(conv_ics.DateUtils.to_local("20240101T100000"), "2024-01-01 10:00:00")

    def test_date_returns_iso(self):
        """Date returns iso."""
        self.assertEqual(conv_ics.DateUtils.to_local("20240101"), "2024-01-01")


class TestDateUtilsToIcs(unittest.TestCase):
    """Tests for DateUtils.to_ics."""

    def test_date(self):
        """Date."""
        self.assertEqual(conv_ics.DateUtils.to_ics("2024-01-01"), "20240101")

    def test_datetime(self):
        """Datetime."""
        self.assertEqual(conv_ics.DateUtils.to_ics("2024-01-01 10:00:00"), "20240101T100000")

    def test_utc_datetime(self):
        """Utc datetime."""
        self.assertEqual(conv_ics.DateUtils.to_ics("2024-01-01 10:00:00Z"), "20240101T100000Z")

    def test_unrecognized_returns_input(self):
        """Unrecognized returns input."""
        self.assertEqual(conv_ics.DateUtils.to_ics("hello"), "hello")

    def test_empty_returns_input(self):
        """Empty returns input."""
        self.assertEqual(conv_ics.DateUtils.to_ics(""), "")

    def test_no_dash_returns_input(self):
        """No dash returns input."""
        self.assertEqual(conv_ics.DateUtils.to_ics("plain"), "plain")

    def test_invalid_format_returns_input(self):
        """Invalid format returns input."""
        self.assertEqual(conv_ics.DateUtils.to_ics("2024-13-99"), "2024-13-99")


class TestDateUtilsGetDuration(unittest.TestCase):
    """Tests for DateUtils.get_duration."""

    def test_one_hour(self):
        """One hour."""
        duration = conv_ics.DateUtils.get_duration(
            start_value="20240101T100000Z", end_value="20240101T110000Z",
        )
        self.assertEqual(duration, "1h")

    def test_thirty_minutes(self):
        """Thirty minutes."""
        duration = conv_ics.DateUtils.get_duration(
            start_value="20240101T100000Z", end_value="20240101T103000Z",
        )
        self.assertEqual(duration, "30m")

    def test_one_hour_thirty(self):
        """One hour thirty."""
        duration = conv_ics.DateUtils.get_duration(
            start_value="20240101T100000Z", end_value="20240101T113000Z",
        )
        self.assertEqual(duration, "1h30m")

    def test_invalid_start_returns_empty(self):
        """Invalid start returns empty."""
        duration = conv_ics.DateUtils.get_duration(
            start_value="bad", end_value="20240101T110000Z",
        )
        self.assertEqual(duration, "")

    def test_invalid_end_returns_empty(self):
        """Invalid end returns empty."""
        duration = conv_ics.DateUtils.get_duration(
            start_value="20240101T100000Z", end_value="bad",
        )
        self.assertEqual(duration, "")

    def test_date_duration(self):
        """Date duration."""
        duration = conv_ics.DateUtils.get_duration(
            start_value="20240101", end_value="20240102",
        )
        self.assertEqual(duration, "24h")


#--------------------------------------------------
# IcsPreprocessor
#--------------------------------------------------


class TestIcsPreprocessor(unittest.TestCase):
    """Tests for IcsPreprocessor."""

    def test_joins_continuation_lines(self):
        """Joins continuation lines."""
        pre = conv_ics.IcsPreprocessor(delimiter=",")
        text = "BEGIN:VEVENT\r\nNOTE:Multi\r\n line"
        result = pre.process(text)
        self.assertIn("NOTE,Multiline", result)

    def test_strips_parameters(self):
        """Strips parameters."""
        pre = conv_ics.IcsPreprocessor(delimiter=",")
        text = "DTSTART;TZID=America/New_York:20240101T100000"
        result = pre.process(text)
        self.assertIn("DTSTART,20240101T100000", result)
        self.assertNotIn("TZID", result)

    def test_unescapes_special_chars(self):
        """Unescapes special chars."""
        pre = conv_ics.IcsPreprocessor(delimiter=",")
        text = "DESCRIPTION:Hello\\, World\\;"
        result = pre.process(text)
        self.assertIn("Hello, World;", result)
        self.assertNotIn("\\,", result)

    def test_keeps_alpha_escapes(self):
        """Keeps alpha escapes."""
        pre = conv_ics.IcsPreprocessor(delimiter=",")
        text = "DESCRIPTION:Hello\\nWorld"
        result = pre.process(text)
        self.assertIn("Hello\\nWorld", result)

    def test_strips_carriage_returns(self):
        """Strips carriage returns."""
        pre = conv_ics.IcsPreprocessor(delimiter=",")
        text = "SUMMARY:Test\r"
        result = pre.process(text)
        self.assertNotIn("\r", result)
        self.assertIn("SUMMARY,Test", result)

    def test_tsv_delimiter(self):
        """Tsv delimiter."""
        pre = conv_ics.IcsPreprocessor(delimiter="\t")
        text = "DTSTART;TZID=NY:20240101T100000"
        result = pre.process(text)
        self.assertIn("DTSTART\t20240101T100000", result)


#--------------------------------------------------
# IcsParser
#--------------------------------------------------


class TestIcsParserCollectRecords(unittest.TestCase):
    """Tests for IcsParser._collect_records."""

    def test_collects_single_vevent(self):
        """Collects single vevent."""
        parser = conv_ics.IcsParser(delimiter="\t")
        text = "BEGIN\tVEVENT\nSUMMARY\tHello\nEND\tVEVENT\n"
        records = parser._collect_records(text)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["SUMMARY"], "Hello")

    def test_collects_multiple_vevents(self):
        """Collects multiple vevents."""
        parser = conv_ics.IcsParser(delimiter="\t")
        text = (
            "BEGIN\tVEVENT\nSUMMARY\tA\nEND\tVEVENT\n"
            "BEGIN\tVEVENT\nSUMMARY\tB\nEND\tVEVENT\n"
        )
        records = parser._collect_records(text)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["SUMMARY"], "A")
        self.assertEqual(records[1]["SUMMARY"], "B")

    def test_ignores_other_components(self):
        """Ignores other components."""
        parser = conv_ics.IcsParser(delimiter="\t")
        text = "BEGIN\tVTODO\nSUMMARY\tTodo\nEND\tVTODO\n"
        records = parser._collect_records(text)
        self.assertEqual(records, [])

    def test_ignores_lines_outside_component(self):
        """Ignores lines outside component."""
        parser = conv_ics.IcsParser(delimiter="\t")
        text = "BEGIN\tVCALENDAR\nVERSION\t2.0\nEND\tVCALENDAR\n"
        records = parser._collect_records(text)
        self.assertEqual(records, [])


class TestIcsParserColumns(unittest.TestCase):
    """Tests for IcsParser._resolve_columns."""

    def test_explicit_columns_preserves_order(self):
        """Explicit columns preserves order."""
        parser = conv_ics.IcsParser(columns="uid,summary,dtstart")
        self.assertEqual(
            parser._resolve_columns([{"UID": "x", "SUMMARY": "y", "DTSTART": "z"}]),
            ["UID", "SUMMARY", "DTSTART"],
        )

    def test_explicit_columns_uppercased(self):
        """Explicit columns uppercased."""
        parser = conv_ics.IcsParser(columns="uid,summary")
        self.assertEqual(parser._resolve_columns([{"UID": "x", "SUMMARY": "y"}]), ["UID", "SUMMARY"])

    def test_auto_columns_sorted_by_frequency(self):
        """Auto columns sorted by frequency."""
        parser = conv_ics.IcsParser()
        records = [
            {"A": "1", "B": "2"},
            {"A": "1", "B": "2", "C": "3"},
            {"A": "1"},
        ]
        columns = parser._resolve_columns(records)
        self.assertEqual(columns[0], "A")
        self.assertEqual(columns[1], "B")
        self.assertEqual(columns[2], "C")


class TestIcsParserBuildRows(unittest.TestCase):
    """Tests for IcsParser._build_rows."""

    def test_iso_conversion_applied(self):
        """Iso conversion applied."""
        parser = conv_ics.IcsParser(columns="dtstart")
        rows = parser._build_rows(
            records=[{"DTSTART": "20240101T100000"}],
            headers=["DTSTART"],
        )
        self.assertEqual(rows[0][0], "2024-01-01 10:00:00")

    def test_duration_computed_from_dtstart_dtend(self):
        """Duration computed from dtstart dtend."""
        parser = conv_ics.IcsParser(columns="duration")
        rows = parser._build_rows(
            records=[{"DTSTART": "20240101T100000Z", "DTEND": "20240101T110000Z"}],
            headers=["DURATION"],
        )
        self.assertEqual(rows[0][0], "1h")


class TestIcsParserFormatOutput(unittest.TestCase):
    """Tests for IcsParser.format_output."""

    def test_formats_headers_and_rows(self):
        """Formats headers and rows."""
        parser = conv_ics.IcsParser(delimiter=",")
        result = parser.format_output(
            headers=["A", "B"], rows=[["1", "2"], ["3", "4"]],
        )
        self.assertEqual(result, "A,B\n1,2\n3,4")

    def test_quotes_value_with_delimiter(self):
        """Quotes value with delimiter."""
        parser = conv_ics.IcsParser(delimiter=",")
        result = parser.format_output(headers=["A"], rows=[["has,comma"]])
        self.assertIn('"has,comma"', result)

    def test_escapes_double_quotes(self):
        """Escapes double quotes."""
        parser = conv_ics.IcsParser(delimiter=",")
        result = parser.format_output(headers=["A"], rows=[['has "quotes" and,comma']])
        self.assertIn('"has ""quotes"" and,comma"', result)

    def test_tsv_delimiter(self):
        """Tsv delimiter."""
        parser = conv_ics.IcsParser(delimiter="\t")
        result = parser.format_output(headers=["A", "B"], rows=[["1", "2"]])
        self.assertEqual(result, "A\tB\n1\t2")


class TestIcsParserIntegration(unittest.TestCase):
    """Integration tests for IcsParser using a fixture."""

    def setUp(self):
        self.text = (FIXTURES / "sample.ics").read_text(encoding="utf-8")

    def test_default_parse(self):
        """Default parse."""
        parser = conv_ics.IcsParser()
        headers, rows = parser.parse(self.text)
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertEqual(len(row), len(headers))

    def test_explicit_columns(self):
        """Explicit columns."""
        parser = conv_ics.IcsParser(columns="uid,summary")
        headers, rows = parser.parse(self.text)
        self.assertEqual(headers, ["UID", "SUMMARY"])
        self.assertEqual(rows[0], ["test-1@example.com", "Test Event One"])

    def test_csv_output(self):
        """Csv output."""
        parser = conv_ics.IcsParser(delimiter=",", columns="uid,summary")
        headers, rows = parser.parse(self.text)
        self.assertEqual(headers, ["UID", "SUMMARY"])
        result = parser.format_output(headers=headers, rows=rows)
        self.assertIn("test-1@example.com,Test Event One", result)

    def test_tsv_output(self):
        """Tsv output."""
        parser = conv_ics.IcsParser(delimiter="\t", columns="uid,summary")
        headers, rows = parser.parse(self.text)
        result = parser.format_output(headers=headers, rows=rows)
        self.assertIn("test-1@example.com\tTest Event One", result)

    def test_continuation_joined(self):
        """Continuation joined."""
        parser = conv_ics.IcsParser(columns="description")
        _headers, rows = parser.parse(self.text)
        self.assertEqual(rows[1][0], "Multi-linedescription here")

    def test_escaped_comma_unescaped(self):
        """Escaped comma unescaped."""
        parser = conv_ics.IcsParser(columns="description")
        _headers, rows = parser.parse(self.text)
        self.assertEqual(rows[0][0], "Hello, World!")

    def test_tzid_parameter_stripped(self):
        """Tzid parameter stripped."""
        parser = conv_ics.IcsParser(columns="dtstart")
        _headers, rows = parser.parse(self.text)
        self.assertEqual(rows[2][0], "2024-03-01 09:00:00")

    def test_no_event_returns_empty(self):
        """No event returns empty."""
        parser = conv_ics.IcsParser()
        text = (FIXTURES / "sample_no_event.ics").read_text(encoding="utf-8")
        headers, rows = parser.parse(text)
        self.assertEqual(headers, [])
        self.assertEqual(rows, [])

    def test_crlf_line_endings(self):
        """Crlf line endings."""
        parser = conv_ics.IcsParser(columns="uid,summary")
        text = (FIXTURES / "sample_crlf.ics").read_text(encoding="utf-8")
        _headers, rows = parser.parse(text)
        self.assertEqual(rows[0], ["crlf-1@example.com", "CRLF Event"])


#--------------------------------------------------
# IcsBuilder
#--------------------------------------------------


class TestIcsBuilderSplitLine(unittest.TestCase):
    """Tests for IcsBuilder._split_line."""

    def test_simple_csv_split(self):
        """Simple csv split."""
        builder = conv_ics.IcsBuilder(delimiter=",")
        self.assertEqual(builder._split_line("a,b,c"), ["a", "b", "c"])

    def test_simple_tsv_split(self):
        """Simple tsv split."""
        builder = conv_ics.IcsBuilder(delimiter="\t")
        self.assertEqual(builder._split_line("a\tb\tc"), ["a", "b", "c"])

    def test_quoted_value_with_delimiter(self):
        """Quoted value with delimiter."""
        builder = conv_ics.IcsBuilder(delimiter=",")
        self.assertEqual(
            builder._split_line('a,"b,c",d'),
            ["a", "b,c", "d"],
        )

    def test_outer_quotes_stripped(self):
        """Outer quotes stripped."""
        builder = conv_ics.IcsBuilder(delimiter=",")
        self.assertEqual(builder._split_line('"hello"'), ["hello"])


class TestIcsBuilderBuild(unittest.TestCase):
    """Tests for IcsBuilder.build."""

    def test_empty_input(self):
        """Empty input."""
        builder = conv_ics.IcsBuilder()
        self.assertEqual(builder.build(""), "BEGIN:VCALENDAR\nEND:VCALENDAR\n")

    def test_simple_event(self):
        """Simple event."""
        builder = conv_ics.IcsBuilder()
        result = builder.build("DTSTART,SUMMARY\n20240101T100000,Hello\n")
        self.assertIn("BEGIN:VCALENDAR", result)
        self.assertIn("BEGIN:VEVENT", result)
        self.assertIn("DTSTART:20240101T100000", result)
        self.assertIn("SUMMARY:Hello", result)
        self.assertIn("END:VEVENT", result)
        self.assertIn("END:VCALENDAR", result)

    def test_simple_event_tsv(self):
        """Simple event tsv."""
        builder = conv_ics.IcsBuilder(delimiter="\t")
        result = builder.build("DTSTART\tSUMMARY\n20240101T100000\tHello\n")
        self.assertIn("DTSTART:20240101T100000", result)
        self.assertIn("SUMMARY:Hello", result)

    def test_multiple_events(self):
        """Multiple events."""
        builder = conv_ics.IcsBuilder()
        result = builder.build(
            "DTSTART,SUMMARY\n"
            "20240101T100000,A\n"
            "20240102T100000,B\n"
        )
        self.assertEqual(result.count("BEGIN:VEVENT"), 2)
        self.assertEqual(result.count("END:VEVENT"), 2)

    def test_skips_empty_values(self):
        """Skips empty values."""
        builder = conv_ics.IcsBuilder()
        result = builder.build("DTSTART,SUMMARY\n20240101T100000,\n")
        self.assertNotIn("SUMMARY:", result)

    def test_skips_duration(self):
        """Skips duration."""
        builder = conv_ics.IcsBuilder()
        result = builder.build("DTSTART,DURATION\n20240101T100000,1h\n")
        self.assertNotIn("DURATION:", result)

    def test_iso_to_ics_conversion(self):
        """Iso to ics conversion."""
        builder = conv_ics.IcsBuilder()
        result = builder.build("DTSTART\n2024-01-01 10:00:00\n")
        self.assertIn("DTSTART:20240101T100000", result)

    def test_iso_date_to_ics(self):
        """Iso date to ics."""
        builder = conv_ics.IcsBuilder()
        result = builder.build("DTSTART\n2024-01-01\n")
        self.assertIn("DTSTART:20240101", result)

    def test_utc_iso_to_ics(self):
        """Utc iso to ics."""
        builder = conv_ics.IcsBuilder()
        result = builder.build("DTSTART\n2024-01-01 10:00:00Z\n")
        self.assertIn("DTSTART:20240101T100000Z", result)

    def test_uppercase_headers(self):
        """Uppercase headers."""
        builder = conv_ics.IcsBuilder()
        result = builder.build("dtstart,summary\n20240101T100000,A\n")
        self.assertIn("DTSTART:20240101T100000", result)
        self.assertIn("SUMMARY:A", result)

    def test_blank_lines_skipped(self):
        """Blank lines skipped."""
        builder = conv_ics.IcsBuilder()
        result = builder.build("DTSTART\n20240101T100000\n\n\n")
        self.assertEqual(result.count("BEGIN:VEVENT"), 1)

    def test_custom_delimiter(self):
        """Custom delimiter."""
        builder = conv_ics.IcsBuilder(delimiter="|")
        result = builder.build("DTSTART|SUMMARY\n20240101T100000|Hello\n")
        self.assertIn("DTSTART:20240101T100000", result)
        self.assertIn("SUMMARY:Hello", result)


#--------------------------------------------------
# GoogleCalendarFormatter
#--------------------------------------------------


class TestGoogleCalendarFormatter(unittest.TestCase):
    """Tests for GoogleCalendarFormatter."""

    def test_headers(self):
        """Headers."""
        formatter = conv_ics.GoogleCalendarFormatter()
        result = formatter.format_records(records=[], calendar="cal")
        self.assertEqual(
            result,
            "Calendar,Subject,Start Date,Start Time,End Date,End Time,Description,Attendee,Location",
        )

    def test_drops_irrelevant_columns(self):
        """Drops irrelevant columns."""
        formatter = conv_ics.GoogleCalendarFormatter()
        records = [
            {
                "UID": "x@example.com",
                "DTSTAMP": "20240101T100000Z",
                "DTSTART": "20240101T100000Z",
                "DTEND": "20240101T110000Z",
                "SUMMARY": "Event",
                "CREATED": "20240101T100000Z",
                "LAST-MODIFIED": "20240101T100000Z",
                "SEQUENCE": "0",
                "STATUS": "CONFIRMED",
                "TRANSP": "OPAQUE",
                "ATTENDEE": "foo@example.com",
                "ORGANIZER": "bar@example.com",
                "X-GOOGLE-CONFERENCE": "https://meet.google.com/abc",
                "RECURRENCE-ID": "20240101T100000Z",
                "ATTACH": "https://example.com/file",
                "RRULE": "FREQ=DAILY",
                "EXDATE": "20240102T100000Z",
            },
        ]
        result = formatter.format_records(records=records, calendar="cal")
        # Only Google columns should be present, in this exact order
        self.assertEqual(
            result.splitlines()[0],
            "Calendar,Subject,Start Date,Start Time,End Date,End Time,Description,Attendee,Location",
        )
        # The dropped columns must not appear anywhere in the output
        for column in (
            "UID", "DTSTAMP", "CREATED", "LAST-MODIFIED", "SEQUENCE",
            "STATUS", "TRANSP", "ORGANIZER",
            "X-GOOGLE-CONFERENCE", "RECURRENCE-ID", "ATTACH", "RRULE",
            "EXDATE",
        ):
            self.assertNotIn(column, result)

    def test_splits_datetime_into_date_and_time(self):
        """Splits datetime into date and time."""
        formatter = conv_ics.GoogleCalendarFormatter()
        records = [
            {
                "DTSTART": "20240115T140000",
                "DTEND": "20240115T150000",
                "SUMMARY": "Meeting",
            },
        ]
        result = formatter.format_records(records=records, calendar="work")
        line = result.splitlines()[1]
        self.assertEqual(
            line,
            "work,Meeting,2024-01-15,14:00,2024-01-15,15:00,,,",
        )

    def test_splits_date_only_into_date_with_blank_time(self):
        """Splits date only into date with blank time."""
        formatter = conv_ics.GoogleCalendarFormatter()
        records = [
            {
                "DTSTART": "20240115",
                "DTEND": "20240116",
                "SUMMARY": "All day",
            },
        ]
        result = formatter.format_records(records=records, calendar="personal")
        line = result.splitlines()[1]
        self.assertEqual(
            line,
            "personal,All day,2024-01-15,,2024-01-16,,,,",
        )

    def test_calendar_column_uses_input_basename(self):
        """Calendar column uses input basename."""
        formatter = conv_ics.GoogleCalendarFormatter()
        records = [{"SUMMARY": "Event"}]
        result = formatter.format_records(records=records, calendar="my-calendar")
        line = result.splitlines()[1]
        self.assertTrue(line.startswith("my-calendar,"))

    def test_local_datetime_conversion(self):
        """Local datetime conversion."""
        formatter = conv_ics.GoogleCalendarFormatter()
        records = [{"DTSTART": "20240101T100000", "DTEND": "20240101T110000"}]
        result = formatter.format_records(records=records, calendar="cal")
        line = result.splitlines()[1]
        self.assertIn("2024-01-01", line)
        self.assertIn("10:00", line)
        self.assertIn("11:00", line)

    def test_utc_datetime_converted_to_local(self):
        """Utc datetime converted to local."""
        formatter = conv_ics.GoogleCalendarFormatter()
        # 14:00 UTC will land at a different local hour depending on tz
        records = [{"DTSTART": "20240101T140000Z", "DTEND": "20240101T150000Z"}]
        result = formatter.format_records(records=records, calendar="cal")
        line = result.splitlines()[1]
        # Layout: Calendar, Subject, Start Date, Start Time, End Date, End Time, Description, Attendee, Location
        self.assertRegex(line, r"cal,,\d{4}-\d{2}-\d{2},\d{2}:\d{2},\d{4}-\d{2}-\d{2},\d{2}:\d{2},,,")

    def test_description_and_location(self):
        """Description and location."""
        formatter = conv_ics.GoogleCalendarFormatter()
        records = [
            {
                "DTSTART": "20240101T100000Z",
                "DTEND": "20240101T110000Z",
                "SUMMARY": "Topic",
                "DESCRIPTION": "Detailed notes",
                "LOCATION": "Room 42",
            },
        ]
        result = formatter.format_records(records=records, calendar="cal")
        line = result.splitlines()[1]
        self.assertIn("Topic", line)
        self.assertIn("Detailed notes", line)
        self.assertIn("Room 42", line)

    def test_quotes_value_with_delimiter(self):
        """Quotes value with delimiter."""
        formatter = conv_ics.GoogleCalendarFormatter()
        records = [
            {
                "DTSTART": "20240101T100000Z",
                "DTEND": "20240101T110000Z",
                "SUMMARY": "Hello, World",
            },
        ]
        result = formatter.format_records(records=records, calendar="cal")
        self.assertIn('"Hello, World"', result)

    def test_quotes_value_with_newline(self):
        """Quotes value with newline."""
        formatter = conv_ics.GoogleCalendarFormatter()
        records = [
            {
                "DTSTART": "20240101T100000Z",
                "DTEND": "20240101T110000Z",
                "DESCRIPTION": "Line 1\nLine 2",
            },
        ]
        result = formatter.format_records(records=records, calendar="cal")
        self.assertIn('"Line 1\nLine 2"', result)

    def test_quotes_value_with_double_quote(self):
        """Quotes value with double quote."""
        formatter = conv_ics.GoogleCalendarFormatter()
        records = [
            {
                "DTSTART": "20240101T100000Z",
                "DTEND": "20240101T110000Z",
                "SUMMARY": 'She said "hi"',
            },
        ]
        result = formatter.format_records(records=records, calendar="cal")
        self.assertIn('"She said ""hi"""', result)

    def test_missing_dtstart_dtend_yields_blank_date_and_time(self):
        """Missing dtstart dtend yields blank date and time."""
        formatter = conv_ics.GoogleCalendarFormatter()
        records = [{"SUMMARY": "TBD"}]
        result = formatter.format_records(records=records, calendar="cal")
        line = result.splitlines()[1]
        self.assertEqual(line, "cal,TBD,,,,,,,")

    def test_date_format_is_iso(self):
        """Date format is iso."""
        formatter = conv_ics.GoogleCalendarFormatter()
        records = [{"DTSTART": "20240115T000000", "DTEND": "20240115T235959"}]
        result = formatter.format_records(records=records, calendar="cal")
        line = result.splitlines()[1]
        self.assertIn("2024-01-15,00:00,", line)
        self.assertIn(",23:59,", line)

    def test_attendee_column_always_present(self):
        """Attendee column always present."""
        formatter = conv_ics.GoogleCalendarFormatter()
        records = [
            {
                "DTSTART": "20240101T100000Z",
                "DTEND": "20240101T110000Z",
                "SUMMARY": "Event",
                "ATTENDEE": "mailto:foo@example.com",
            },
        ]
        result = formatter.format_records(records=records, calendar="cal")
        first_line = result.splitlines()[0]
        self.assertIn(",Attendee,", first_line)
        data_line = result.splitlines()[1]
        self.assertIn("mailto:foo@example.com", data_line)

    def test_format_time_helper_24hour(self):
        """Format time helper 24hour."""
        self.assertEqual(conv_ics.GoogleCalendarFormatter._format_time("00:00:00"), "00:00")
        self.assertEqual(conv_ics.GoogleCalendarFormatter._format_time("01:30:00"), "01:30")
        self.assertEqual(conv_ics.GoogleCalendarFormatter._format_time("11:59:00"), "11:59")
        self.assertEqual(conv_ics.GoogleCalendarFormatter._format_time("12:00:00"), "12:00")
        self.assertEqual(conv_ics.GoogleCalendarFormatter._format_time("13:00:00"), "13:00")
        self.assertEqual(conv_ics.GoogleCalendarFormatter._format_time("23:45:00"), "23:45")

    def test_split_datetime_unrecognized_value(self):
        """Split datetime unrecognized value."""
        formatter = conv_ics.GoogleCalendarFormatter()
        self.assertEqual(formatter._split_datetime(""), ("", ""))
        self.assertEqual(formatter._split_datetime("not-a-date"), ("not-a-date", ""))

    def test_multiple_records(self):
        """Multiple records."""
        formatter = conv_ics.GoogleCalendarFormatter()
        records = [
            {
                "DTSTART": "20240101T100000Z",
                "DTEND": "20240101T110000Z",
                "SUMMARY": "A",
            },
            {
                "DTSTART": "20240201T100000Z",
                "DTEND": "20240201T110000Z",
                "SUMMARY": "B",
            },
        ]
        result = formatter.format_records(records=records, calendar="cal")
        lines = result.splitlines()
        self.assertEqual(len(lines), 3)
        self.assertIn(",A,", lines[1])
        self.assertIn(",B,", lines[2])

    def test_custom_delimiter(self):
        """Custom delimiter."""
        formatter = conv_ics.GoogleCalendarFormatter(delimiter=";")
        records = [
            {
                "DTSTART": "20240101T100000Z",
                "DTEND": "20240101T110000Z",
                "SUMMARY": "X",
            },
        ]
        result = formatter.format_records(records=records, calendar="cal")
        self.assertTrue(result.startswith("Calendar;Subject;"))


#--------------------------------------------------
# IcsHandler
#--------------------------------------------------


class TestIcsHandlerProcessFile(unittest.TestCase):
    """Tests for IcsHandler.process_file."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def _make_handler(self, **kwargs):
        return conv_ics.IcsHandler(
            logger=conv_ics.NullLogger(),
            columns=kwargs.get("columns", ""),
            delimiter=kwargs.get("delimiter", conv_ics.IcsParser.DEFAULT_DELIMITER),
            input_delimiter=kwargs.get("input_delimiter"),
            recursive=kwargs.get("recursive", False),
            input_root=kwargs.get("input_root"),
            full=kwargs.get("full", False),
        )

    def test_writes_to_file_in_cwd_when_no_output(self):
        """Writes to file in cwd when no output."""
        path = Path(self.tmp) / "cal.ics"
        path.write_text((FIXTURES / "sample.ics").read_text(encoding="utf-8"), encoding="utf-8")
        handler = self._make_handler(columns="uid,summary", full=True)
        original_cwd = os.getcwd()
        os.chdir(self.tmp)
        try:
            handler.process_file(path)
        finally:
            os.chdir(original_cwd)
        target = Path(self.tmp) / "cal.csv"
        self.assertTrue(target.exists())
        content = target.read_text(encoding="utf-8")
        self.assertIn("UID,SUMMARY", content)
        self.assertIn("Test Event One", content)
        self.assertEqual(handler.files_processed, 1)

    def test_recursive_without_output_raises(self):
        """Recursive without output raises."""
        path = Path(self.tmp) / "cal.ics"
        path.write_text((FIXTURES / "sample.ics").read_text(encoding="utf-8"), encoding="utf-8")
        handler = self._make_handler(columns="uid,summary", recursive=True)
        with self.assertRaises(ValueError):
            handler.process_file(path)

    def test_writes_to_stdout_with_dash_output(self):
        """Writes to stdout with dash output."""
        path = Path(self.tmp) / "cal.ics"
        path.write_text((FIXTURES / "sample.ics").read_text(encoding="utf-8"), encoding="utf-8")
        handler = self._make_handler(columns="uid,summary", full=True)
        buf = io.StringIO()
        with redirect_stdout(buf):
            handler.process_file(path, output="-")
        output = buf.getvalue()
        self.assertIn("UID,SUMMARY", output)
        self.assertIn("Test Event One", output)

    def test_writes_to_file_when_output_is_file(self):
        """Writes to file when output is file."""
        path = Path(self.tmp) / "cal.ics"
        path.write_text((FIXTURES / "sample.ics").read_text(encoding="utf-8"), encoding="utf-8")
        output_path = Path(self.tmp) / "out.csv"
        handler = self._make_handler(columns="uid,summary", full=True)
        handler.process_file(path, output=str(output_path))
        self.assertTrue(output_path.exists())
        content = output_path.read_text(encoding="utf-8")
        self.assertIn("UID,SUMMARY", content)
        self.assertIn("Test Event One", content)

    def test_writes_to_directory(self):
        """Writes to directory."""
        path = Path(self.tmp) / "cal.ics"
        path.write_text((FIXTURES / "sample.ics").read_text(encoding="utf-8"), encoding="utf-8")
        out_dir = Path(self.tmp) / "out"
        handler = self._make_handler(columns="uid,summary", input_root=path.parent)
        handler.process_file(path, output=str(out_dir))
        self.assertTrue((out_dir / "cal.csv").exists())

    def test_tsv_writes_tsv(self):
        """Tsv writes tsv."""
        path = Path(self.tmp) / "cal.ics"
        path.write_text((FIXTURES / "sample.ics").read_text(encoding="utf-8"), encoding="utf-8")
        out_dir = Path(self.tmp) / "out"
        handler = self._make_handler(
            columns="uid,summary", delimiter="\t", full=True, input_root=path.parent,
        )
        handler.process_file(path, output=str(out_dir))
        self.assertTrue((out_dir / "cal.tsv").exists())
        content = (out_dir / "cal.tsv").read_text(encoding="utf-8")
        self.assertIn("UID\tSUMMARY", content)

    def test_dry_run_does_not_write(self):
        """Dry run does not write."""
        path = Path(self.tmp) / "cal.ics"
        path.write_text((FIXTURES / "sample.ics").read_text(encoding="utf-8"), encoding="utf-8")
        output_path = Path(self.tmp) / "out.csv"
        handler = self._make_handler(columns="uid,summary")
        handler.process_file(path, output=str(output_path), dry_run=True)
        self.assertFalse(output_path.exists())
        self.assertEqual(handler.files_processed, 1)

    def test_non_existent_file_skipped(self):
        """Non existent file skipped."""
        path = Path(self.tmp) / "missing.ics"
        handler = self._make_handler()
        handler.process_file(path)
        self.assertEqual(handler.files_skipped, 1)
        self.assertEqual(handler.files_processed, 0)

    def test_unreadable_file_skipped(self):
        """Unreadable file skipped."""
        path = Path(self.tmp) / "cal.ics"
        path.write_text((FIXTURES / "sample.ics").read_text(encoding="utf-8"), encoding="utf-8")
        path.chmod(0o000)
        self.addCleanup(path.chmod, 0o644)
        handler = self._make_handler()
        handler.process_file(path)
        self.assertEqual(handler.files_skipped, 1)

    def test_reverse_writes_ics(self):
        """Reverse writes ics."""
        path = Path(self.tmp) / "cal.csv"
        path.write_text((FIXTURES / "sample_input.csv").read_text(encoding="utf-8"), encoding="utf-8")
        output_path = Path(self.tmp) / "out.ics"
        handler = self._make_handler()
        handler.process_file(path, output=str(output_path))
        self.assertTrue(output_path.exists())
        content = output_path.read_text(encoding="utf-8")
        self.assertIn("BEGIN:VCALENDAR", content)
        self.assertIn("DTSTART:20240101T150000", content)
        self.assertIn("SUMMARY:Test Event One", content)

    def test_recursive_preserves_directory_structure(self):
        """Recursive preserves directory structure."""
        sub = Path(self.tmp) / "sub"
        sub.mkdir()
        (Path(self.tmp) / "a.ics").write_text(
            (FIXTURES / "sample.ics").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (sub / "b.ics").write_text(
            (FIXTURES / "sample.ics").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        out_dir = Path(self.tmp) / "out"
        handler = self._make_handler(
            columns="uid", recursive=True, input_root=Path(self.tmp),
        )
        handler.process_file(Path(self.tmp) / "a.ics", output=str(out_dir))
        handler.process_file(sub / "b.ics", output=str(out_dir))
        self.assertTrue((out_dir / "a.csv").exists())
        self.assertTrue((out_dir / "sub" / "b.csv").exists())

    def test_default_outputs_google_format(self):
        """Default outputs google format."""
        path = Path(self.tmp) / "cal.ics"
        path.write_text((FIXTURES / "sample.ics").read_text(encoding="utf-8"), encoding="utf-8")
        output_path = Path(self.tmp) / "out.csv"
        handler = self._make_handler()
        handler.process_file(path, output=str(output_path))
        self.assertTrue(output_path.exists())
        content = output_path.read_text(encoding="utf-8")
        first_line = content.splitlines()[0]
        self.assertEqual(
            first_line,
            "Calendar,Subject,Start Date,Start Time,End Date,End Time,Description,Attendee,Location",
        )
        self.assertIn("cal,Test Event One,", content)
        self.assertNotIn("cal.ics,", content)
        # Dropped columns must not appear
        for column in ("UID", "DTSTAMP", "STATUS", "ORGANIZER"):
            self.assertNotIn(column, content)

    def test_default_includes_attendee_column(self):
        """Default includes attendee column."""
        path = Path(self.tmp) / "cal.ics"
        path.write_text((FIXTURES / "sample.ics").read_text(encoding="utf-8"), encoding="utf-8")
        output_path = Path(self.tmp) / "out.csv"
        handler = self._make_handler()
        handler.process_file(path, output=str(output_path))
        content = output_path.read_text(encoding="utf-8")
        first_line = content.splitlines()[0]
        self.assertIn("Attendee", first_line)
        self.assertTrue(first_line.endswith(",Location"))

    def test_default_uses_input_stem_as_calendar(self):
        """Default uses input stem as calendar."""
        path = Path(self.tmp) / "my-work.ics"
        path.write_text((FIXTURES / "sample.ics").read_text(encoding="utf-8"), encoding="utf-8")
        output_path = Path(self.tmp) / "out.csv"
        handler = self._make_handler()
        handler.process_file(path, output=str(output_path))
        content = output_path.read_text(encoding="utf-8")
        for line in content.splitlines()[1:]:
            self.assertTrue(line.startswith("my-work,"))
            self.assertFalse(line.startswith("my-work.ics,"))

    def test_default_dry_run_does_not_write(self):
        """Default dry run does not write."""
        path = Path(self.tmp) / "cal.ics"
        path.write_text((FIXTURES / "sample.ics").read_text(encoding="utf-8"), encoding="utf-8")
        output_path = Path(self.tmp) / "out.csv"
        handler = self._make_handler()
        handler.process_file(path, output=str(output_path), dry_run=True)
        self.assertFalse(output_path.exists())
        self.assertEqual(handler.files_processed, 1)

    def test_default_writes_to_stdout(self):
        """Default writes to stdout."""
        path = Path(self.tmp) / "cal.ics"
        path.write_text((FIXTURES / "sample.ics").read_text(encoding="utf-8"), encoding="utf-8")
        handler = self._make_handler()
        buf = io.StringIO()
        with redirect_stdout(buf):
            handler.process_file(path, output="-")
        output = buf.getvalue()
        self.assertIn("Calendar,Subject,Start Date,Start Time", output)
        self.assertIn("cal,Test Event One,", output)
        self.assertNotIn("cal.ics,", output)

    def test_default_recursive_preserves_structure(self):
        """Default recursive preserves structure."""
        sub = Path(self.tmp) / "sub"
        sub.mkdir()
        (Path(self.tmp) / "a.ics").write_text(
            (FIXTURES / "sample.ics").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (sub / "b.ics").write_text(
            (FIXTURES / "sample.ics").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        out_dir = Path(self.tmp) / "out"
        handler = self._make_handler(recursive=True, input_root=Path(self.tmp))
        handler.process_file(Path(self.tmp) / "a.ics", output=str(out_dir))
        handler.process_file(sub / "b.ics", output=str(out_dir))
        self.assertTrue((out_dir / "a.csv").exists())
        self.assertTrue((out_dir / "sub" / "b.csv").exists())
        # Each output carries its own input stem in the Calendar column
        a_content = (out_dir / "a.csv").read_text(encoding="utf-8")
        b_content = (out_dir / "sub" / "b.csv").read_text(encoding="utf-8")
        for line in a_content.splitlines()[1:]:
            self.assertTrue(line.startswith("a,"))
            self.assertFalse(line.startswith("a.ics,"))
        for line in b_content.splitlines()[1:]:
            self.assertTrue(line.startswith("b,"))
            self.assertFalse(line.startswith("b.ics,"))

    def test_full_outputs_full_format(self):
        """Full outputs full format."""
        path = Path(self.tmp) / "cal.ics"
        path.write_text((FIXTURES / "sample.ics").read_text(encoding="utf-8"), encoding="utf-8")
        output_path = Path(self.tmp) / "out.csv"
        handler = self._make_handler(full=True, columns="uid,summary")
        handler.process_file(path, output=str(output_path))
        self.assertTrue(output_path.exists())
        content = output_path.read_text(encoding="utf-8")
        self.assertIn("UID,SUMMARY", content)
        self.assertIn("test-1@example.com,Test Event One", content)
        # The Google-specific columns should not appear
        self.assertNotIn("Calendar,Subject,Start Date", content)
        self.assertNotIn("cal.ics,", content)


class TestIcsHandlerFormatDetection(unittest.TestCase):
    """Tests for extension-based format detection in IcsHandler."""

    def test_detect_format_ics(self):
        """Detect format ics."""
        self.assertEqual(conv_ics.IcsHandler.detect_format(Path("cal.ics")), "ics")

    def test_detect_format_csv(self):
        """Detect format csv."""
        self.assertEqual(conv_ics.IcsHandler.detect_format(Path("cal.csv")), "csv")

    def test_detect_format_tsv(self):
        """Detect format tsv."""
        self.assertEqual(conv_ics.IcsHandler.detect_format(Path("cal.tsv")), "tsv")

    def test_detect_format_uppercase(self):
        """Detect format uppercase."""
        self.assertEqual(conv_ics.IcsHandler.detect_format(Path("CAL.ICS")), "ics")
        self.assertEqual(conv_ics.IcsHandler.detect_format(Path("CAL.CSV")), "csv")
        self.assertEqual(conv_ics.IcsHandler.detect_format(Path("CAL.TSV")), "tsv")

    def test_detect_format_unknown_defaults_to_ics(self):
        """Detect format unknown defaults to ics."""
        self.assertEqual(conv_ics.IcsHandler.detect_format(Path("cal.txt")), "ics")

    def test_delimiter_for_tsv(self):
        """Delimiter for tsv."""
        self.assertEqual(conv_ics.IcsHandler.delimiter_for(Path("cal.tsv")), "\t")

    def test_delimiter_for_csv(self):
        """Delimiter for csv."""
        self.assertEqual(conv_ics.IcsHandler.delimiter_for(Path("cal.csv")), ",")

    def test_delimiter_for_ics_defaults_to_csv(self):
        """Delimiter for ics defaults to csv."""
        self.assertEqual(conv_ics.IcsHandler.delimiter_for(Path("cal.ics")), ",")

    def test_is_reverse_for_ics_file(self):
        """Is reverse for ics file."""
        handler = conv_ics.IcsHandler(logger=conv_ics.NullLogger())
        self.assertFalse(handler.is_reverse(Path("cal.ics")))

    def test_is_reverse_for_csv_file(self):
        """Is reverse for csv file."""
        handler = conv_ics.IcsHandler(logger=conv_ics.NullLogger())
        self.assertTrue(handler.is_reverse(Path("cal.csv")))

    def test_is_reverse_for_tsv_file(self):
        """Is reverse for tsv file."""
        handler = conv_ics.IcsHandler(logger=conv_ics.NullLogger())
        self.assertTrue(handler.is_reverse(Path("cal.tsv")))


class TestIcsHandlerProcessFileExtensionDetection(unittest.TestCase):
    """End-to-end tests verifying direction is picked from the file extension."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def _handler(self, **kwargs):
        return conv_ics.IcsHandler(
            logger=conv_ics.NullLogger(),
            columns=kwargs.get("columns", ""),
            delimiter=kwargs.get("delimiter", conv_ics.IcsParser.DEFAULT_DELIMITER),
            input_delimiter=kwargs.get("input_delimiter"),
            recursive=kwargs.get("recursive", False),
            input_root=kwargs.get("input_root"),
            full=kwargs.get("full", False),
        )

    def test_ics_extension_triggers_forward(self):
        """Ics extension triggers forward."""
        ics = Path(self.tmp) / "cal.ics"
        ics.write_text((FIXTURES / "sample.ics").read_text(encoding="utf-8"), encoding="utf-8")
        handler = self._handler(columns="uid,summary")
        out_dir = Path(self.tmp) / "out"
        handler.process_file(ics, output=str(out_dir))
        self.assertTrue((out_dir / "cal.csv").exists())
        self.assertFalse((out_dir / "cal.ics").exists())

    def test_csv_extension_triggers_reverse_with_comma(self):
        """Csv extension triggers reverse with comma."""
        csv = Path(self.tmp) / "events.csv"
        csv.write_text("UID,SUMMARY\ntest@example.com,Test\n", encoding="utf-8")
        handler = self._handler()
        out_dir = Path(self.tmp) / "out"
        handler.process_file(csv, output=str(out_dir))
        self.assertTrue((out_dir / "events.ics").exists())
        content = (out_dir / "events.ics").read_text(encoding="utf-8")
        self.assertIn("UID:test@example.com", content)
        self.assertIn("SUMMARY:Test", content)

    def test_tsv_extension_triggers_reverse_with_tab(self):
        """Tsv extension triggers reverse with tab."""
        tsv = Path(self.tmp) / "events.tsv"
        tsv.write_text("UID\tSUMMARY\ntest@example.com\tTest\n", encoding="utf-8")
        handler = self._handler()
        out_dir = Path(self.tmp) / "out"
        handler.process_file(tsv, output=str(out_dir))
        self.assertTrue((out_dir / "events.ics").exists())
        content = (out_dir / "events.ics").read_text(encoding="utf-8")
        self.assertIn("UID:test@example.com", content)
        self.assertIn("SUMMARY:Test", content)

    def test_resolve_input_delimiter_uses_extension_when_unset(self):
        """Resolve input delimiter uses extension when unset."""
        handler = conv_ics.IcsHandler(
            logger=conv_ics.NullLogger(), delimiter=",", input_delimiter=None,
        )
        self.assertEqual(handler._resolve_input_delimiter(Path("cal.csv")), ",")
        self.assertEqual(handler._resolve_input_delimiter(Path("cal.tsv")), "\t")

    def test_resolve_input_delimiter_prefers_override(self):
        """Resolve input delimiter prefers override."""
        handler = conv_ics.IcsHandler(
            logger=conv_ics.NullLogger(), delimiter=",", input_delimiter=";",
        )
        self.assertEqual(handler._resolve_input_delimiter(Path("cal.csv")), ";")
        self.assertEqual(handler._resolve_input_delimiter(Path("cal.tsv")), ";")


class TestIcsHandlerOutputName(unittest.TestCase):
    """Tests for IcsHandler._relative_output_name and _tabular_suffix."""

    def test_csv_suffix(self):
        """Csv suffix."""
        handler = conv_ics.IcsHandler(logger=conv_ics.NullLogger(), delimiter=",")
        self.assertEqual(handler._relative_output_name(Path("/tmp/cal.ics")), "cal.csv")

    def test_tsv_suffix(self):
        """Tsv suffix."""
        handler = conv_ics.IcsHandler(logger=conv_ics.NullLogger(), delimiter="\t")
        self.assertEqual(handler._relative_output_name(Path("/tmp/cal.ics")), "cal.tsv")

    def test_reverse_ics_suffix(self):
        """Reverse ics suffix."""
        handler = conv_ics.IcsHandler(logger=conv_ics.NullLogger(), delimiter=",")
        self.assertEqual(handler._relative_output_name(Path("/tmp/cal.csv")), "cal.ics")

    def test_custom_delimiter_uses_txt(self):
        """Custom delimiter uses txt."""
        handler = conv_ics.IcsHandler(logger=conv_ics.NullLogger(), delimiter="|")
        self.assertEqual(handler._relative_output_name(Path("/tmp/cal.ics")), "cal.txt")

    def test_recursive_preserves_subpath(self):
        """Recursive preserves subpath."""
        handler = conv_ics.IcsHandler(
            logger=conv_ics.NullLogger(), delimiter=",", recursive=True, input_root=Path("/tmp/in"),
        )
        self.assertEqual(
            handler._relative_output_name(Path("/tmp/in/sub/cal.ics")),
            "sub/cal.csv",
        )


#--------------------------------------------------
# IcsConverterApp
#--------------------------------------------------


class TestIcsConverterAppBuildParser(unittest.TestCase):
    """Tests for IcsConverterApp._build_parser."""

    def _app(self):
        return conv_ics.IcsConverterApp(
            author="TangoMan75",
            title="iCalendar Parser",
            description="Convert iCalendar files.",
        )

    def test_default_columns_empty(self):
        """Default columns empty."""
        args = self._app()._build_parser().parse_args(["input.ics"])
        self.assertEqual(args.columns, "")

    def test_columns_long_flag(self):
        """Columns long flag."""
        args = self._app()._build_parser().parse_args(["input.ics", "--columns", "uid,summary"])
        self.assertEqual(args.columns, "uid,summary")

    def test_default_delimiter_is_none(self):
        """Default delimiter is none."""
        # The default is resolved at run-time as CSV; the parser stores None
        # as a sentinel meaning "use the default".
        args = self._app()._build_parser().parse_args(["input.ics"])
        self.assertIsNone(args.delimiter)

    def test_delimiter_long_flag(self):
        """Delimiter long flag."""
        args = self._app()._build_parser().parse_args(["input.ics", "--delimiter", ";"])
        self.assertEqual(args.delimiter, ";")

    def test_full_default_false(self):
        """Full default false."""
        args = self._app()._build_parser().parse_args(["input.ics"])
        self.assertFalse(args.full)

    def test_full_flag(self):
        """Full flag."""
        args = self._app()._build_parser().parse_args(["input.ics", "--full"])
        self.assertTrue(args.full)

    def test_inherited_verbose(self):
        """Inherited verbose."""
        args = self._app()._build_parser().parse_args(["input.ics", "-vv"])
        self.assertEqual(args.verbose, 2)

    def test_inherited_recursive(self):
        """Inherited recursive."""
        args = self._app()._build_parser().parse_args(["input.ics", "--recursive"])
        self.assertTrue(args.recursive)


class TestIcsConverterAppResolveDelimiters(unittest.TestCase):
    """Tests for IcsConverterApp._resolve_delimiters and _unescape_delimiter."""

    def _make_args(self, **kwargs):
        return argparse.Namespace(**kwargs)

    def test_default_output_csv_input_none(self):
        """Default output csv input none."""
        args = self._make_args(delimiter=None)
        out, inb = conv_ics.IcsConverterApp._resolve_delimiters(args)
        self.assertEqual(out, ",")
        self.assertIsNone(inb)

    def test_delimiter_sets_both(self):
        """Delimiter sets both."""
        args = self._make_args(delimiter=";")
        out, inb = conv_ics.IcsConverterApp._resolve_delimiters(args)
        self.assertEqual(out, ";")
        self.assertEqual(inb, ";")

    def test_unescape_tab(self):
        """Unescape tab."""
        self.assertEqual(conv_ics.IcsConverterApp._unescape_delimiter("\\t"), "\t")

    def test_unescape_comma(self):
        """Unescape comma."""
        self.assertEqual(conv_ics.IcsConverterApp._unescape_delimiter(","), ",")

    def test_unescape_letter(self):
        """Unescape letter."""
        self.assertEqual(conv_ics.IcsConverterApp._unescape_delimiter("a"), "a")

    def test_unescape_pipe(self):
        """Unescape pipe."""
        self.assertEqual(conv_ics.IcsConverterApp._unescape_delimiter("|"), "|")


#--------------------------------------------------
# Integration
#--------------------------------------------------


class TestIntegration(unittest.TestCase):
    """End-to-end CLI tests."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.original_cwd = os.getcwd()
        os.chdir(self.tmp)
        self.app = conv_ics.IcsConverterApp(
            author="TangoMan75",
            title="iCalendar Parser",
            description="Convert iCalendar files.",
        )

    def tearDown(self):
        os.chdir(self.original_cwd)

    def test_cli_default_csv(self):
        """Cli default csv."""
        path = Path("cal.ics")
        path.write_text((FIXTURES / "sample.ics").read_text(encoding="utf-8"), encoding="utf-8")
        buf = io.StringIO()
        with patch.object(sys, "argv", ["icsp", str(path), "--full", "--columns", "uid,summary", "--output", "-"]):
            with redirect_stdout(buf):
                self.app.run(conv_ics.IcsHandler)
        output = buf.getvalue()
        self.assertIn("UID,SUMMARY", output)
        self.assertIn("Test Event One", output)

    def test_cli_no_output_writes_to_cwd(self):
        """Cli no output writes to cwd."""
        # When --output is not provided (and not recursive), the file is
        # written to the current working directory with a new extension.
        path = Path("cal.ics")
        path.write_text((FIXTURES / "sample.ics").read_text(encoding="utf-8"), encoding="utf-8")
        with patch.object(sys, "argv", ["icsp", str(path), "--full", "--columns", "uid,summary"]):
            self.app.run(conv_ics.IcsHandler)
        target = Path("cal.csv")
        self.assertTrue(target.exists())
        self.assertIn("UID,SUMMARY", target.read_text(encoding="utf-8"))

    def test_cli_missing_input_exits_one(self):
        """A missing input path is a runtime error."""
        with patch.object(sys, "argv", ["icsp", "missing.ics"]):
            with redirect_stderr(io.StringIO()) as err:
                with self.assertRaises(SystemExit) as raised:
                    self.app.run(conv_ics.IcsHandler)
        self.assertEqual(raised.exception.code, 1)
        self.assertIn("input path not found", err.getvalue())

    def test_cli_recursive_without_output_errors(self):
        """Cli recursive without output errors."""
        # When --recursive is set, --output is required.
        in_dir = Path("in")
        in_dir.mkdir()
        (in_dir / "a.ics").write_text(
            (FIXTURES / "sample.ics").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        with patch.object(sys, "argv", ["icsp", str(in_dir), "--recursive", "--full", "--columns", "uid"]):
            with self.assertRaises(SystemExit):
                self.app.run(conv_ics.IcsHandler)

    def test_cli_custom_delimiter(self):
        """Cli custom delimiter."""
        path = Path("cal.ics")
        path.write_text((FIXTURES / "sample.ics").read_text(encoding="utf-8"), encoding="utf-8")
        buf = io.StringIO()
        with patch.object(sys, "argv", ["icsp", str(path), "--delimiter", ";", "--full", "--columns", "uid,summary", "--output", "-"]):
            with redirect_stdout(buf):
                self.app.run(conv_ics.IcsHandler)
        output = buf.getvalue()
        self.assertIn("UID;SUMMARY", output)

    def test_cli_csv_output_to_file(self):
        """Cli csv output to file."""
        path = Path("cal.ics")
        path.write_text((FIXTURES / "sample.ics").read_text(encoding="utf-8"), encoding="utf-8")
        out = Path("out.csv")
        with patch.object(sys, "argv", ["icsp", str(path), "--full", "--columns", "uid,summary", "--output", str(out)]):
            self.app.run(conv_ics.IcsHandler)
        self.assertTrue(out.exists())
        self.assertIn("Test Event One", out.read_text(encoding="utf-8"))

    def test_cli_tsv_output_to_file(self):
        """Cli tsv output to file."""
        path = Path("cal.ics")
        path.write_text((FIXTURES / "sample.ics").read_text(encoding="utf-8"), encoding="utf-8")
        out = Path("out.tsv")
        with patch.object(
            sys, "argv",
            ["icsp", str(path), "--delimiter", "\t", "--full", "--columns", "uid,summary", "--output", str(out)],
        ):
            self.app.run(conv_ics.IcsHandler)
        self.assertTrue(out.exists())
        content = out.read_text(encoding="utf-8")
        self.assertIn("UID\tSUMMARY", content)
        self.assertIn("Test Event One", content)

    def test_cli_directory_input_default_csv(self):
        """Cli directory input default csv."""
        in_dir = Path("in")
        in_dir.mkdir()
        (in_dir / "a.ics").write_text(
            (FIXTURES / "sample.ics").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        out_dir = Path("out")
        with patch.object(sys, "argv", ["icsp", str(in_dir), "--full", "--columns", "uid", "--output", str(out_dir)]):
            self.app.run(conv_ics.IcsHandler)
        self.assertTrue((out_dir / "a.csv").exists())

    def test_cli_directory_input_tsv(self):
        """Cli directory input tsv."""
        in_dir = Path("in")
        in_dir.mkdir()
        (in_dir / "a.ics").write_text(
            (FIXTURES / "sample.ics").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        out_dir = Path("out")
        with patch.object(
            sys, "argv",
            ["icsp", str(in_dir), "--delimiter", "\t", "--full", "--columns", "uid", "--output", str(out_dir)],
        ):
            self.app.run(conv_ics.IcsHandler)
        self.assertTrue((out_dir / "a.tsv").exists())

    def test_cli_recursive_preserves_structure(self):
        """Cli recursive preserves structure."""
        in_dir = Path("in")
        in_dir.mkdir()
        sub = in_dir / "sub"
        sub.mkdir()
        (in_dir / "a.ics").write_text(
            (FIXTURES / "sample.ics").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (sub / "b.ics").write_text(
            (FIXTURES / "sample.ics").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        out_dir = Path("out")
        with patch.object(
            sys, "argv",
            ["icsp", str(in_dir), "--recursive", "--full", "--columns", "uid", "--output", str(out_dir)],
        ):
            self.app.run(conv_ics.IcsHandler)
        self.assertTrue((out_dir / "a.csv").exists())
        self.assertTrue((out_dir / "sub" / "b.csv").exists())

    def test_cli_default_outputs_google_csv(self):
        """Cli default outputs google csv."""
        path = Path("cal.ics")
        path.write_text((FIXTURES / "sample.ics").read_text(encoding="utf-8"), encoding="utf-8")
        buf = io.StringIO()
        with patch.object(sys, "argv", ["icsp", str(path), "--output", "-"]):
            with redirect_stdout(buf):
                self.app.run(conv_ics.IcsHandler)
        output = buf.getvalue()
        first_line = output.splitlines()[0]
        self.assertEqual(
            first_line,
            "Calendar,Subject,Start Date,Start Time,End Date,End Time,Description,Attendee,Location",
        )
        self.assertIn("cal,Test Event One,", output)
        self.assertNotIn("cal.ics,", output)
        self.assertNotIn("UID,", output)
        self.assertNotIn("DTSTAMP,", output)

    def test_cli_default_to_file(self):
        """Cli default to file."""
        path = Path("cal.ics")
        path.write_text((FIXTURES / "sample.ics").read_text(encoding="utf-8"), encoding="utf-8")
        out = Path("out.csv")
        with patch.object(sys, "argv", ["icsp", str(path), "--output", str(out)]):
            self.app.run(conv_ics.IcsHandler)
        self.assertTrue(out.exists())
        content = out.read_text(encoding="utf-8")
        self.assertIn("Calendar,Subject,Start Date,Start Time", content)
        self.assertIn("cal,Test Event One,", content)
        self.assertNotIn("cal.ics,", content)

    def test_cli_default_with_directory_input(self):
        """Cli default with directory input."""
        in_dir = Path("in")
        in_dir.mkdir()
        (in_dir / "a.ics").write_text(
            (FIXTURES / "sample.ics").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        out_dir = Path("out")
        with patch.object(
            sys, "argv",
            ["icsp", str(in_dir), "--output", str(out_dir)],
        ):
            self.app.run(conv_ics.IcsHandler)
        self.assertTrue((out_dir / "a.csv").exists())
        content = (out_dir / "a.csv").read_text(encoding="utf-8")
        self.assertIn("a,", content)
        self.assertFalse(any(line.startswith("a.ics,") for line in content.splitlines()[1:]))

    def test_cli_default_recursive_preserves_structure(self):
        """Default output with --recursive preserves the input directory layout."""
        in_dir = Path("in")
        in_dir.mkdir()
        sub = in_dir / "sub"
        sub.mkdir()
        (in_dir / "a.ics").write_text(
            (FIXTURES / "sample.ics").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (sub / "b.ics").write_text(
            (FIXTURES / "sample.ics").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        out_dir = Path("out")
        with patch.object(
            sys, "argv",
            ["icsp", str(in_dir), "--recursive", "--output", str(out_dir)],
        ):
            self.app.run(conv_ics.IcsHandler)
        self.assertTrue((out_dir / "a.csv").exists())
        self.assertTrue((out_dir / "sub" / "b.csv").exists())

    def test_cli_attendee_column_always_present(self):
        """Cli attendee column always present."""
        path = Path("cal.ics")
        path.write_text((FIXTURES / "sample.ics").read_text(encoding="utf-8"), encoding="utf-8")
        buf = io.StringIO()
        with patch.object(sys, "argv", ["icsp", str(path), "--output", "-"]):
            with redirect_stdout(buf):
                self.app.run(conv_ics.IcsHandler)
        output = buf.getvalue()
        first_line = output.splitlines()[0]
        self.assertTrue(first_line.endswith(",Location"))
        self.assertIn("Attendee", first_line)

    def test_cli_full_outputs_full_csv(self):
        """Cli full outputs full csv."""
        path = Path("cal.ics")
        path.write_text((FIXTURES / "sample.ics").read_text(encoding="utf-8"), encoding="utf-8")
        buf = io.StringIO()
        with patch.object(
            sys, "argv",
            ["icsp", str(path), "--full", "--columns", "uid,summary", "--output", "-"],
        ):
            with redirect_stdout(buf):
                self.app.run(conv_ics.IcsHandler)
        output = buf.getvalue()
        self.assertIn("UID,SUMMARY", output)
        self.assertIn("test-1@example.com,Test Event One", output)
        # The Google-specific layout should not appear
        self.assertNotIn("Calendar,Subject,Start Date", output)
        self.assertNotIn("cal.ics,", output)


#--------------------------------------------------
# IcsDownloader
#--------------------------------------------------


class TestIcsDownloaderIsUrl(unittest.TestCase):
    """Tests for IcsDownloader.is_url."""

    def test_https_url(self):
        """Https url."""
        self.assertTrue(conv_ics.IcsDownloader.is_url("https://example.com/cal.ics"))

    def test_http_url(self):
        """Http url."""
        self.assertTrue(conv_ics.IcsDownloader.is_url("http://example.com/cal.ics"))

    def test_local_path_is_not_url(self):
        """Local path is not url."""
        self.assertFalse(conv_ics.IcsDownloader.is_url("./cal.ics"))

    def test_absolute_path_is_not_url(self):
        """Absolute path is not url."""
        self.assertFalse(conv_ics.IcsDownloader.is_url("/tmp/cal.ics"))

    def test_empty_is_not_url(self):
        """Empty is not url."""
        self.assertFalse(conv_ics.IcsDownloader.is_url(""))

    def test_ftp_scheme_is_not_url(self):
        """Ftp scheme is not url."""
        self.assertFalse(conv_ics.IcsDownloader.is_url("ftp://example.com/cal.ics"))

    def test_file_scheme_is_not_url(self):
        """File scheme is not url."""
        self.assertFalse(conv_ics.IcsDownloader.is_url("file:///tmp/cal.ics"))


class TestIcsDownloaderDeriveFilename(unittest.TestCase):
    """Tests for IcsDownloader._derive_filename."""

    def test_ics_extension_preserved(self):
        """Ics extension preserved."""
        self.assertEqual(
            conv_ics.IcsDownloader._derive_filename("https://host/foo/basic.ics"),
            "basic.ics",
        )

    def test_uppercase_ics_preserved(self):
        """Uppercase ics preserved."""
        self.assertEqual(
            conv_ics.IcsDownloader._derive_filename("https://host/foo/CAL.ICS"),
            "CAL.ICS",
        )

    def test_missing_extension_appended(self):
        """Missing extension appended."""
        self.assertEqual(
            conv_ics.IcsDownloader._derive_filename("https://host/foo/cal"),
            "cal.ics",
        )

    def test_query_string_stripped(self):
        """Query string stripped."""
        self.assertEqual(
            conv_ics.IcsDownloader._derive_filename("https://host/foo/cal.ics?cid=1"),
            "cal.ics",
        )

    def test_query_string_stripped_and_extension_appended(self):
        """Query string stripped and extension appended."""
        self.assertEqual(
            conv_ics.IcsDownloader._derive_filename("https://host/foo/cal?id=1"),
            "cal.ics",
        )

    def test_url_encoded_segment_decoded(self):
        """Url encoded segment decoded."""
        self.assertEqual(
            conv_ics.IcsDownloader._derive_filename("https://host/foo/my%20cal.ics"),
            "my cal.ics",
        )

    def test_root_url_uses_default(self):
        """Root url uses default."""
        self.assertEqual(
            conv_ics.IcsDownloader._derive_filename("https://host/"),
            "calendar.ics",
        )

    def test_bare_host_uses_default(self):
        """Bare host uses default."""
        self.assertEqual(
            conv_ics.IcsDownloader._derive_filename("https://host"),
            "calendar.ics",
        )

    def test_fragment_ignored(self):
        """Fragment ignored."""
        self.assertEqual(
            conv_ics.IcsDownloader._derive_filename("https://host/foo/cal.ics#section"),
            "cal.ics",
        )

    def test_deep_path_uses_last_segment(self):
        """Deep path uses last segment."""
        self.assertEqual(
            conv_ics.IcsDownloader._derive_filename("https://host/a/b/c/d/cal.ics"),
            "cal.ics",
        )


class TestIcsDownloaderUniquePath(unittest.TestCase):
    """Tests for IcsDownloader._unique_path."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_no_collision(self):
        """No collision."""
        target = conv_ics.IcsDownloader._unique_path(dest_dir=self.tmp, filename="cal.ics")
        self.assertEqual(target, self.tmp / "cal.ics")

    def test_collision_suffixes(self):
        """Collision suffixes."""
        (self.tmp / "cal.ics").write_bytes(b"")
        target = conv_ics.IcsDownloader._unique_path(dest_dir=self.tmp, filename="cal.ics")
        self.assertEqual(target, self.tmp / "cal_1.ics")

    def test_double_collision(self):
        """Double collision."""
        (self.tmp / "cal.ics").write_bytes(b"")
        (self.tmp / "cal_1.ics").write_bytes(b"")
        target = conv_ics.IcsDownloader._unique_path(dest_dir=self.tmp, filename="cal.ics")
        self.assertEqual(target, self.tmp / "cal_2.ics")

    def test_filename_without_extension(self):
        """Filename without extension."""
        target = conv_ics.IcsDownloader._unique_path(dest_dir=self.tmp, filename="cal")
        self.assertEqual(target, self.tmp / "cal")

    def test_collision_without_extension(self):
        """Collision without extension."""
        (self.tmp / "cal").write_bytes(b"")
        target = conv_ics.IcsDownloader._unique_path(dest_dir=self.tmp, filename="cal")
        self.assertEqual(target, self.tmp / "cal_1.ics")


class TestIcsDownloaderDownload(unittest.TestCase):
    """Tests for IcsDownloader.download (with mocked urlopen)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def _mock_response(self, body):
        mock = MagicMock()
        mock.read.return_value = body
        mock.__enter__.return_value = mock
        mock.__exit__.return_value = False
        return mock

    def test_writes_content_to_dest(self):
        """Writes content to dest."""
        body = b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"
        with patch("conv_ics.urlopen", return_value=self._mock_response(body)) as mocked:
            downloader = conv_ics.IcsDownloader()
            saved = downloader.download(
                url="https://example.com/cal.ics", dest_dir=self.tmp,
            )
        self.assertEqual(saved, self.tmp / "cal.ics")
        self.assertEqual(saved.read_bytes(), body)
        mocked.assert_called_once()
        _, kwargs = mocked.call_args
        self.assertEqual(kwargs["timeout"], 30)
        self.assertIsInstance(kwargs["context"], ssl.SSLContext)

    def test_passes_user_agent_header(self):
        """Passes user agent header."""
        with patch("conv_ics.urlopen", return_value=self._mock_response(b"")) as mocked:
            conv_ics.IcsDownloader().download(
                url="https://example.com/cal.ics", dest_dir=self.tmp,
            )
        request_arg = mocked.call_args[0][0]
        self.assertEqual(request_arg.headers["User-agent"], "conv-ics/1.0")

    def test_ssl_context_always_unverified(self):
        """Ssl context always unverified."""
        with patch("conv_ics.urlopen", return_value=self._mock_response(b"")) as mocked:
            conv_ics.IcsDownloader().download(
                url="https://example.com/cal.ics", dest_dir=self.tmp,
            )
        _, kwargs = mocked.call_args
        context = kwargs["context"]
        self.assertIsInstance(context, ssl.SSLContext)
        self.assertEqual(context.verify_mode, ssl.CERT_NONE)
        self.assertFalse(context.check_hostname)

    def test_http_error_exits(self):
        """Http error exits."""
        with patch("conv_ics.urlopen", side_effect=conv_ics.HTTPError(
            "https://example.com/cal.ics", 404, "Not Found", {}, None,
        )):
            with self.assertRaises(SystemExit):
                conv_ics.IcsDownloader().download(
                    url="https://example.com/cal.ics", dest_dir=self.tmp,
                )

    def test_url_error_exits(self):
        """Url error exits."""
        with patch("conv_ics.urlopen", side_effect=conv_ics.URLError("DNS failure")):
            with self.assertRaises(SystemExit):
                conv_ics.IcsDownloader().download(
                    url="https://example.com/cal.ics", dest_dir=self.tmp,
                )

    def test_collision_uses_unique_path(self):
        """Collision uses unique path."""
        (self.tmp / "cal.ics").write_bytes(b"old")
        with patch("conv_ics.urlopen", return_value=self._mock_response(b"new")):
            saved = conv_ics.IcsDownloader().download(
                url="https://example.com/cal.ics", dest_dir=self.tmp,
            )
        self.assertEqual(saved, self.tmp / "cal_1.ics")
        self.assertEqual(saved.read_bytes(), b"new")
        self.assertEqual((self.tmp / "cal.ics").read_bytes(), b"old")


#--------------------------------------------------
# IcsConverterApp URL handling
#--------------------------------------------------


class TestIcsConverterAppUrlDefaults(unittest.TestCase):
    """Tests for the URL downloader defaults exposed via the parser."""

    def _app(self):
        return conv_ics.IcsConverterApp(
            author="TangoMan75",
            title="iCalendar Parser",
            description="Convert iCalendar files.",
        )

    def test_default_timeout_is_class_constant(self):
        """Default timeout is class constant."""
        # The CLI no longer exposes a --timeout flag, but the default must
        # remain stable for the URL downloader.
        self.assertEqual(conv_ics.IcsDownloader.DEFAULT_TIMEOUT, 30)


class TestIcsConverterAppUrlRun(unittest.TestCase):
    """End-to-end tests: a URL argument triggers a download, no conversion."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.original_cwd = os.getcwd()
        os.chdir(self.tmp)
        self.app = conv_ics.IcsConverterApp(
            author="TangoMan75",
            title="iCalendar Parser",
            description="Convert iCalendar files.",
        )

    def tearDown(self):
        os.chdir(self.original_cwd)

    def _mock_response(self, body):
        mock = MagicMock()
        mock.read.return_value = body
        mock.__enter__.return_value = mock
        mock.__exit__.return_value = False
        return mock

    def test_url_downloads_and_converts_to_csv(self):
        """Url downloads and converts to csv."""
        body = (FIXTURES / "sample.ics").read_bytes()
        with patch("conv_ics.urlopen", return_value=self._mock_response(body)):
            with patch.object(
                sys, "argv",
                ["icsp", "https://example.com/calendar/basic.ics"],
            ):
                self.app.run(conv_ics.IcsHandler)
        self.assertTrue((Path("basic.ics")).exists())
        self.assertEqual((Path("basic.ics")).read_bytes(), body)
        self.assertTrue((Path("basic.csv")).exists())
        content = Path("basic.csv").read_text(encoding="utf-8")
        self.assertIn("Calendar,Subject,Start Date,Start Time,End Date,End Time", content)

    def test_url_http_scheme_works(self):
        """Url http scheme works."""
        body = b"BEGIN:VCALENDAR\nEND:VCALENDAR\n"
        with patch("conv_ics.urlopen", return_value=self._mock_response(body)):
            with patch.object(
                sys, "argv",
                ["icsp", "http://example.com/cal.ics"],
            ):
                self.app.run(conv_ics.IcsHandler)
        self.assertTrue((Path("cal.ics")).exists())

    def test_url_with_query_string(self):
        """Url with query string."""
        body = b"BEGIN:VCALENDAR\nEND:VCALENDAR\n"
        with patch("conv_ics.urlopen", return_value=self._mock_response(body)):
            with patch.object(
                sys, "argv",
                ["icsp", "https://example.com/cal.ics?cid=abc"],
            ):
                self.app.run(conv_ics.IcsHandler)
        self.assertTrue((Path("cal.ics")).exists())

    def test_url_no_extension_appends_ics(self):
        """Url no extension appends ics."""
        body = b"BEGIN:VCALENDAR\nEND:VCALENDAR\n"
        with patch("conv_ics.urlopen", return_value=self._mock_response(body)):
            with patch.object(
                sys, "argv",
                ["icsp", "https://example.com/calendar/feed"],
            ):
                self.app.run(conv_ics.IcsHandler)
        self.assertTrue((Path("feed.ics")).exists())

    def test_url_bare_host_uses_default_filename(self):
        """Url bare host uses default filename."""
        body = b"BEGIN:VCALENDAR\nEND:VCALENDAR\n"
        with patch("conv_ics.urlopen", return_value=self._mock_response(body)):
            with patch.object(
                sys, "argv",
                ["icsp", "https://example.com/"],
            ):
                self.app.run(conv_ics.IcsHandler)
        self.assertTrue((Path("calendar.ics")).exists())

    def test_url_collision_suffixes(self):
        """Url collision suffixes."""
        body = b"new"
        Path("cal.ics").write_bytes(b"old")
        with patch("conv_ics.urlopen", return_value=self._mock_response(body)):
            with patch.object(
                sys, "argv",
                ["icsp", "https://example.com/cal.ics"],
            ):
                self.app.run(conv_ics.IcsHandler)
        self.assertEqual(Path("cal.ics").read_bytes(), b"old")
        self.assertEqual(Path("cal_1.ics").read_bytes(), b"new")

    def test_url_always_uses_unverified_ssl_context(self):
        """Url always uses unverified ssl context."""
        with patch("conv_ics.urlopen", return_value=self._mock_response(b"")) as mocked:
            with patch.object(
                sys, "argv",
                ["icsp", "https://example.com/cal.ics"],
            ):
                self.app.run(conv_ics.IcsHandler)
        _, kwargs = mocked.call_args
        context = kwargs["context"]
        self.assertIsInstance(context, ssl.SSLContext)
        self.assertEqual(context.verify_mode, ssl.CERT_NONE)
        self.assertFalse(context.check_hostname)
        self.assertEqual(kwargs["timeout"], conv_ics.IcsDownloader.DEFAULT_TIMEOUT)

    def test_url_http_error_exits(self):
        """Url http error exits."""
        with patch("conv_ics.urlopen", side_effect=conv_ics.HTTPError(
            "https://example.com/cal.ics", 404, "Not Found", {}, None,
        )):
            with patch.object(
                sys, "argv",
                ["icsp", "https://example.com/cal.ics"],
            ):
                with self.assertRaises(SystemExit):
                    self.app.run(conv_ics.IcsHandler)
        self.assertFalse(Path("cal.ics").exists())

    def test_url_url_error_exits(self):
        """Url url error exits."""
        with patch("conv_ics.urlopen", side_effect=conv_ics.URLError("DNS failure")):
            with patch.object(
                sys, "argv",
                ["icsp", "https://example.com/cal.ics"],
            ):
                with self.assertRaises(SystemExit):
                    self.app.run(conv_ics.IcsHandler)
        self.assertFalse(Path("cal.ics").exists())

    def test_local_path_still_triggers_conversion(self):
        """Local path still triggers conversion."""
        body = (FIXTURES / "sample.ics").read_text(encoding="utf-8")
        Path("cal.ics").write_text(body, encoding="utf-8")
        buf = io.StringIO()
        with patch.object(
            sys, "argv",
            ["icsp", "cal.ics", "--output", "-"],
        ):
            with redirect_stdout(buf):
                self.app.run(conv_ics.IcsHandler)
        self.assertIn("Calendar,Subject", buf.getvalue())
        self.assertIn("Test Event One", buf.getvalue())
        self.assertFalse(Path("cal.csv").exists())


if __name__ == "__main__":
    unittest.main()
