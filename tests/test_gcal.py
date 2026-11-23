#!/usr/bin/env python3
"""Tests for gcal module."""
# noqa: E402


import io
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))

import gcal


#--------------------------------------------------
# Test doubles
#--------------------------------------------------


class FakeGwsRunner:
    """Scripted stand-in for GwsCommandRunner."""

    def __init__(self, *, responses):
        self._responses = list(responses) if isinstance(responses, list) else [responses]
        self.calls = []

    def run(self, *, args):
        """Record the call and return or raise the next scripted response."""
        self.calls.append(list(args))
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


#--------------------------------------------------
# Date-range resolution
#--------------------------------------------------


class TestParseLocal(unittest.TestCase):
    """Tests for LocalDateRange.parse_local."""

    def test_parses_datetime(self):
        """A full datetime string is parsed."""
        self.assertEqual(gcal.LocalDateRange.parse_local("2026-08-13 10:30:45"),
                         datetime(2026, 8, 13, 10, 30, 45))

    def test_parses_date_only(self):
        """A bare date parses to midnight."""
        self.assertEqual(gcal.LocalDateRange.parse_local("2026-08-13"), datetime(2026, 8, 13))

    def test_invalid_raises(self):
        """Malformed input raises ValueError."""
        with self.assertRaises(ValueError):
            gcal.LocalDateRange.parse_local("nope")


class TestResolveIsoRange(unittest.TestCase):
    """Tests for LocalDateRange.resolve_iso_range."""

    def test_datetime_inputs(self):
        """Timed inputs are converted to local ISO-8601 unchanged."""
        tmin, tmax = gcal.LocalDateRange.resolve_iso_range(
            start="2026-08-13 10:30:00", end="2026-08-13 12:00:00"
        )
        self.assertEqual(tmin, datetime(2026, 8, 13, 10, 30).astimezone().isoformat())
        self.assertEqual(tmax, datetime(2026, 8, 13, 12, 0).astimezone().isoformat())

    def test_date_only_start_uses_midnight(self):
        """A date-only start resolves to local midnight."""
        tmin, _ = gcal.LocalDateRange.resolve_iso_range(
            start="2026-08-13", end="2026-08-15"
        )
        self.assertEqual(tmin, datetime(2026, 8, 13).astimezone().isoformat())

    def test_date_only_end_uses_end_of_day(self):
        """A date-only end resolves to 23:59:59."""
        _, tmax = gcal.LocalDateRange.resolve_iso_range(
            start="2026-08-13", end="2026-08-15"
        )
        expected = datetime(2026, 8, 15, 23, 59, 59).astimezone().isoformat()
        self.assertEqual(tmax, expected)

    def test_end_before_start_raises(self):
        """An end before start raises ValueError."""
        with self.assertRaises(ValueError):
            gcal.LocalDateRange.resolve_iso_range(start="2026-08-15", end="2026-08-13")


#--------------------------------------------------
# Rendering
#--------------------------------------------------


class TestRendering(unittest.TestCase):
    """Tests for EventRow and range-title helpers."""

    def test_md_escape(self):
        """Pipes and newlines are escaped for table cells."""
        self.assertEqual(gcal.EventRow.md_escape("a|b\nc"), "a\\|b c")
        self.assertEqual(gcal.EventRow.md_escape(None), "")

    def test_fmt_range_title(self):
        """Only the date part is shown."""
        self.assertEqual(
            gcal.MarkdownEventRenderer.format_range_title(
                tmin="2026-08-13T00:00:00+02:00",
                tmax="2026-08-13T23:00:00+02:00",
            ),
            "2026-08-13",
        )
        self.assertEqual(
            gcal.MarkdownEventRenderer.format_range_title(
                tmin="2026-08-13T00:00:00+02:00",
                tmax="2026-08-15T23:00:00+02:00",
            ),
            "2026-08-13 \u2192 2026-08-15",
        )

    def test_calendar_label_prefers_summary(self):
        """calendarSummary wins over the raw id."""
        self.assertEqual(
            gcal.EventRow.calendar_label({"calendarSummary": "Work", "calendarId": "x@y"}),
            "Work",
        )

    def test_calendar_label_falls_back_to_organizer(self):
        """The organizer email is used when no summary or id is present."""
        event = {"organizer": {"email": "a@b.com"}}
        self.assertEqual(gcal.EventRow.calendar_label(event), "a@b.com")

    def test_calendar_label_empty(self):
        """No labels yield an empty string."""
        self.assertEqual(gcal.EventRow.calendar_label({}), "")


class TestEventRow(unittest.TestCase):
    """Tests for EventRow.cells."""

    def test_timed_event(self):
        """A timed event fills all nine cells."""
        event = {
            "start": {"dateTime": "2026-08-13T10:30:00+02:00"},
            "end": {"dateTime": "2026-08-13T11:00:00+02:00"},
            "summary": "Meeting",
            "description": "line1\nline2",
            "attendees": [{"email": "a@b.com"}, {"email": "c@d.com"}, {}],
            "location": "Room 1",
            "calendarSummary": "Work",
        }
        self.assertEqual(gcal.EventRow.cells(event), [
            "Work", "Meeting", "2026-08-13", "10:30",
            "2026-08-13", "11:00", "line1 line2", "a@b.com, c@d.com", "Room 1",
        ])

    def test_all_day_event(self):
        """All-day events have dates but no times."""
        event = {
            "start": {"date": "2026-08-13"},
            "end": {"date": "2026-08-14"},
            "summary": "Holiday",
        }
        row = gcal.EventRow.cells(event)
        self.assertEqual(row[1], "Holiday")
        self.assertEqual(row[2], "2026-08-13")
        self.assertEqual(row[3], "")
        self.assertEqual(row[4], "2026-08-14")
        self.assertEqual(row[5], "")

    def test_empty_event(self):
        """A sparse event renders defaults."""
        row = gcal.EventRow.cells({})
        self.assertEqual(row[0], "")
        self.assertEqual(row[1], "(no title)")


class TestRenderCsv(unittest.TestCase):
    """Tests for CsvEventRenderer."""

    def test_header_and_quoted_cells(self):
        """Cells containing commas or quotes are quoted with doubled quotes."""
        event = {
            "start": {"date": "2026-08-13"},
            "end": {"date": "2026-08-14"},
            "summary": 'Say "hi", folks',
        }
        out = gcal.CsvEventRenderer.render([event])
        lines = out.splitlines()
        self.assertEqual(lines[0], ",".join(gcal.EventRow.COLUMNS))
        self.assertIn('"Say ""hi"", folks"', lines[1])


class TestRenderMarkdown(unittest.TestCase):
    """Tests for MarkdownEventRenderer."""

    def test_empty_placeholder(self):
        """An empty event list renders the no-events placeholder."""
        out = gcal.MarkdownEventRenderer.render(
            events=[],
            tmin="2026-08-13T00:00:00+02:00",
            tmax="2026-08-13T23:00:00+02:00",
        )
        self.assertEqual(out, "# Calendar events for 2026-08-13\n\n_No events in this range._\n")

    def test_table(self):
        """A populated list renders a markdown table."""
        event = {
            "start": {"dateTime": "2026-08-13T10:30:00+02:00"},
            "end": {"dateTime": "2026-08-13T11:00:00+02:00"},
            "summary": "Meeting",
            "calendarSummary": "Work",
        }
        out = gcal.MarkdownEventRenderer.render(
            events=[event],
            tmin="2026-08-13T00:00:00+02:00",
            tmax="2026-08-13T23:00:00+02:00",
        )
        self.assertIn("| Work | Meeting | 2026-08-13 | 10:30 |", out)
        self.assertIn("| Calendar | Subject |", out)


#--------------------------------------------------
# Resolution and gws calls
#--------------------------------------------------


class TestResolveCalendarId(unittest.TestCase):
    """Tests for CalendarCatalog.resolve_id."""

    def setUp(self):
        self.calendars = [{"id": "A", "summary": "Work"}, {"id": "B", "summary": "Personal"}]

    def test_case_insensitive_match(self):
        """A case-insensitive summary match resolves to the id."""
        self.assertEqual(
            gcal.CalendarCatalog.resolve_id(query="work", calendars=self.calendars),
            "A",
        )

    def test_summary_override_preferred(self):
        """summaryOverride wins over summary for matching."""
        calendars = [{"id": "A", "summary": "Work", "summaryOverride": "Override"}]
        self.assertEqual(
            gcal.CalendarCatalog.resolve_id(query="Override", calendars=calendars),
            "A",
        )

    def test_no_match_passthrough(self):
        """Unmatched queries pass through unchanged."""
        self.assertEqual(
            gcal.CalendarCatalog.resolve_id(query="xyz", calendars=self.calendars),
            "xyz",
        )

    def test_empty_query_passthrough(self):
        """An empty query passes through unchanged."""
        self.assertEqual(
            gcal.CalendarCatalog.resolve_id(query="", calendars=self.calendars),
            "",
        )

    def test_ambiguous_raises(self):
        """Duplicate summaries raise ValueError."""
        calendars = [{"id": "A", "summary": "Work"}, {"id": "B", "summary": "Work"}]
        with self.assertRaises(ValueError) as ctx:
            gcal.CalendarCatalog.resolve_id(query="Work", calendars=calendars)
        self.assertIn("ambiguous", str(ctx.exception))


class TestGwsCalls(unittest.TestCase):
    """Tests for fetch helpers with a fake gws runner."""

    def test_fetch_calendar_list(self):
        """Items with an id are returned."""
        runner = FakeGwsRunner(
            responses=['{"items": [{"id": "A"}, {"no": "x"}]}']
        )
        catalog = gcal.CalendarCatalog(runner=runner)
        self.assertEqual(catalog.list_calendars(), [{"id": "A"}])

    def test_fetch_events_for_calendar(self):
        """The events.list params are passed through."""
        runner = FakeGwsRunner(responses=['{"items": [{"id": "e1"}]}'])
        console = gcal.Console(stdout=io.StringIO(), stderr=io.StringIO())
        catalog = gcal.CalendarCatalog(runner=runner)
        fetcher = gcal.CalendarEventFetcher(
            runner=runner, catalog=catalog, console=console
        )
        events = fetcher.events_for_calendar(
            calendar_id="A", time_min="tmin", time_max="tmax", max_results=250
        )
        self.assertEqual(events, [{"id": "e1"}])
        call = runner.calls[0]
        params = json.loads(call[call.index("--params") + 1])
        self.assertEqual(params["calendarId"], "A")
        self.assertEqual(params["timeMin"], "tmin")
        self.assertEqual(params["timeMax"], "tmax")
        self.assertEqual(params["orderBy"], "startTime")
        self.assertTrue(params["singleEvents"])

    def test_event_start_key(self):
        """The start key prefers dateTime over date."""
        self.assertEqual(
            gcal.EventRow.start_key({"start": {"dateTime": "x", "date": "y"}}), "x"
        )
        self.assertEqual(gcal.EventRow.start_key({"start": {"date": "y"}}), "y")
        self.assertEqual(gcal.EventRow.start_key({}), "")


class TestFetchAllCalendarsEvents(unittest.TestCase):
    """Tests for CalendarEventFetcher.all_events."""

    def test_merges_tags_and_sorts(self):
        """Events are merged, tagged, sorted, and listed in calendars_queried."""
        runner = FakeGwsRunner(responses=[])
        catalog = gcal.CalendarCatalog(runner=runner)
        fetcher = gcal.CalendarEventFetcher(
            runner=runner,
            catalog=catalog,
            console=gcal.Console(stdout=io.StringIO(), stderr=io.StringIO()),
        )
        with patch.object(
            catalog,
            "list_calendars",
            return_value=[{"id": "A", "summary": "Work"}, {"id": "B", "summary": "Personal"}],
        ), patch.object(
            fetcher,
            "events_for_calendar",
            side_effect=[
                [{"id": "late", "start": {"dateTime": "2026-08-13T12:00:00+02:00"}}],
                [{"id": "early", "start": {"dateTime": "2026-08-13T09:00:00+02:00"}}],
            ],
        ):
            merged = fetcher.all_events(time_min="tmin", time_max="tmax", max_results=250)
        self.assertEqual(merged["kind"], "calendar#events")
        self.assertEqual([event["id"] for event in merged["items"]], ["early", "late"])
        self.assertEqual(merged["items"][0]["calendarId"], "B")
        self.assertEqual(merged["items"][0]["calendarSummary"], "Personal")
        self.assertEqual(merged["calendars_queried"], [
            {"id": "A", "summary": "Work"}, {"id": "B", "summary": "Personal"},
        ])

    def test_skips_failing_calendar_with_warning(self):
        """A failing calendar is skipped and always reported with a warning."""
        err = io.StringIO()
        runner = FakeGwsRunner(responses=[])
        catalog = gcal.CalendarCatalog(runner=runner)
        fetcher = gcal.CalendarEventFetcher(
            runner=runner,
            catalog=catalog,
            console=gcal.Console(stdout=io.StringIO(), stderr=err),
        )
        with patch.object(
            catalog,
            "list_calendars",
            return_value=[{"id": "A", "summary": "Work"}, {"id": "B", "summary": "Bad"}],
        ), patch.object(
            fetcher,
            "events_for_calendar",
            side_effect=[[{"id": "e1"}], RuntimeError("boom")],
        ):
            merged = fetcher.all_events(time_min="tmin", time_max="tmax", max_results=250)
        self.assertIn("skipping calendar B", err.getvalue())
        self.assertEqual([event["id"] for event in merged["items"]], ["e1"])


#--------------------------------------------------
# main / CLI
#--------------------------------------------------


class TestMain(unittest.TestCase):
    """Tests for Application.run with a fake gws runner."""

    @staticmethod
    def run_main(argv, responses):
        """Run the application with argv and scripted gws responses."""
        stdout = io.StringIO()
        stderr = io.StringIO()
        app = gcal.Application(
            argv=argv,
            runner=FakeGwsRunner(responses=responses),
            console=gcal.Console(stdout=stdout, stderr=stderr),
        )
        rc = app.run()
        return rc, stdout.getvalue(), stderr.getvalue()

    def test_single_calendar_raw_passthrough(self):
        """A single calendar emits the raw gws JSON unchanged."""
        raw = '{"items": [{"id": "e1", "summary": "Meeting"}]}'
        responses = [
            '{"items": [{"id": "A", "summary": "Work"}]}',
            raw,
        ]
        rc, out, _ = self.run_main(
            ["--calendar", "Work", "--start", "2026-08-01", "--end", "2026-08-01"],
            responses,
        )
        self.assertEqual(rc, 0)
        self.assertEqual(out, raw)

    def test_single_calendar_md(self):
        """--md renders a table and injects the calendar summary."""
        responses = [
            '{"items": [{"id": "A", "summary": "Work"}]}',
            '{"items": [{"id": "e1", "summary": "Meeting", '
            '"start": {"dateTime": "2026-08-13T10:30:00+02:00"}, '
            '"end": {"dateTime": "2026-08-13T11:00:00+02:00"}}]}',
        ]
        rc, out, _ = self.run_main(
            ["--calendar", "Work", "--md", "--start", "2026-08-13", "--end", "2026-08-13"],
            responses,
        )
        self.assertEqual(rc, 0)
        self.assertIn("# Calendar events for 2026-08-13", out)
        self.assertIn("Meeting", out)

    def test_single_calendar_csv(self):
        """--csv renders CSV rows."""
        responses = [
            '{"items": [{"id": "A", "summary": "Work"}]}',
            '{"items": [{"id": "e1", "summary": "Meeting", '
            '"start": {"date": "2026-08-13"}, '
            '"end": {"date": "2026-08-14"}}]}',
        ]
        rc, out, _ = self.run_main(
            ["--calendar", "Work", "--csv", "--start", "2026-08-01", "--end", "2026-08-01"],
            responses,
        )
        self.assertEqual(rc, 0)
        self.assertEqual(out.splitlines()[0], ",".join(gcal.EventRow.COLUMNS))
        self.assertIn("Meeting", out)

    def test_single_calendar_quiet_does_not_hide_events_error(self):
        """--quiet still reports an events-list failure and exits 1."""
        rc, out, err = self.run_main(
            ["--calendar", "Work", "--quiet", "--start", "2026-08-01", "--end", "2026-08-01"],
            [RuntimeError("boom")],
        )
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("boom", err)

    def test_single_calendar_events_error_returns_1(self):
        """An events-list failure exits 1 with an error on stderr."""
        rc, _, err = self.run_main(
            ["--calendar", "Work", "--start", "2026-08-01", "--end", "2026-08-01"],
            [RuntimeError("boom")],
        )
        self.assertEqual(rc, 1)
        self.assertIn("boom", err)

    def test_all_calendars_merge(self):
        """Without --calendar, all calendars are fanned out and merged."""
        responses = [
            '{"items": [{"id": "A", "summary": "Work"}, {"id": "B", "summary": "Personal"}]}',
            '{"items": [{"id": "late", "start": {"dateTime": "2026-08-13T12:00:00+02:00"}}]}',
            '{"items": [{"id": "early", "start": {"dateTime": "2026-08-13T09:00:00+02:00"}}]}',
        ]
        rc, out, _ = self.run_main(
            ["--start", "2026-08-01", "--end", "2026-08-01"],
            responses,
        )
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["kind"], "calendar#events")
        self.assertEqual([event["id"] for event in data["items"]], ["early", "late"])
        self.assertEqual(len(data["calendars_queried"]), 2)

    def test_all_calendars_quiet_does_not_hide_error(self):
        """--quiet still reports a fan-out failure and exits 1."""
        rc, out, err = self.run_main(
            ["--quiet", "--start", "2026-08-01", "--end", "2026-08-01"],
            RuntimeError("boom"),
        )
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("boom", err)

    def test_all_calendars_error_returns_1(self):
        """A fan-out failure exits 1 with an error."""
        rc, _, err = self.run_main(
            ["--start", "2026-08-01", "--end", "2026-08-01"],
            RuntimeError("boom"),
        )
        self.assertEqual(rc, 1)
        self.assertIn("boom", err)

    def test_invalid_date_returns_2(self):
        """A malformed start date exits 2."""
        rc, _, err = self.run_main(["--start", "not-a-date"], [])
        self.assertEqual(rc, 2)
        self.assertIn("invalid date", err)

    def test_missing_end_sends_start_date_235959(self):
        """Without --end, timeMax is the start date at 23:59:59 local."""
        responses = [
            '{"items": [{"id": "A", "summary": "Work"}]}',
            '{"items": []}',
        ]
        runner = FakeGwsRunner(responses=responses)
        stdout = io.StringIO()
        stderr = io.StringIO()
        app = gcal.Application(
            argv=["--calendar", "Work", "--start", "2026-08-01"],
            runner=runner,
            console=gcal.Console(stdout=stdout, stderr=stderr),
        )
        rc = app.run()
        self.assertEqual(rc, 0)
        call = runner.calls[1]
        params = json.loads(call[call.index("--params") + 1])
        self.assertEqual(params["timeMin"][:10], "2026-08-01")
        self.assertEqual(params["timeMax"][:10], "2026-08-01")
        self.assertIn("T23:59:59", params["timeMax"])


SAMPLE_ICS = """BEGIN:VCALENDAR
X-WR-CALNAME:My Feed
VERSION:2.0
BEGIN:VEVENT
UID:u1
SUMMARY:Standup
DTSTART:20260803T090000Z
DTEND:20260803T093000Z
END:VEVENT
BEGIN:VEVENT
UID:u2
SUMMARY:Weekly Sync
DTSTART:20260803T140000Z
DTEND:20260803T150000Z
RRULE:FREQ=WEEKLY;BYDAY=TU;UNTIL=20260831T000000Z
END:VEVENT
BEGIN:VEVENT
UID:u3
SUMMARY:Holiday
DTSTART;VALUE=DATE:20260810
DTEND;VALUE=DATE:20260811
END:VEVENT
END:VCALENDAR
"""


class TestIsCalendarUrl(unittest.TestCase):
    """Tests for IcsCalendarFetcher.is_calendar_url."""

    def test_https(self):
        self.assertTrue(gcal.IcsCalendarFetcher.is_calendar_url("https://example.com/a.ics"))

    def test_http(self):
        self.assertTrue(gcal.IcsCalendarFetcher.is_calendar_url("http://example.com/a.ics"))

    def test_id_not_url(self):
        self.assertFalse(gcal.IcsCalendarFetcher.is_calendar_url("matthias@ext.theodo.com"))

    def test_empty(self):
        self.assertFalse(gcal.IcsCalendarFetcher.is_calendar_url(""))


class TestIcsParsing(unittest.TestCase):
    """Tests for ICS parsing, recurrence, and window filtering."""

    def setUp(self):
        codec = gcal.IcsCodec()
        self.fetcher = gcal.IcsCalendarFetcher(
            downloader=gcal.IcsFeedDownloader(),
            parser=gcal.IcsParser(codec=codec),
            expander=gcal.RecurrenceExpander(codec=codec),
            codec=codec,
        )

    def _events(self):
        with patch("gcal.IcsFeedDownloader.download", return_value=SAMPLE_ICS):
            return self.fetcher.events(
                url="https://example.com/a.ics",
                time_min="2026-08-01T00:00:00+00:00",
                time_max="2026-08-31T23:59:59+00:00",
            )

    def test_single_event_shape(self):
        """A non-recurring event maps to the gws event shape."""
        events = self._events()
        standup = next(event for event in events if event["summary"] == "Standup")
        self.assertEqual(standup["start"], {"dateTime": "2026-08-03T09:00:00+00:00"})
        self.assertEqual(standup["end"], {"dateTime": "2026-08-03T09:30:00+00:00"})
        self.assertEqual(standup["calendarSummary"], "My Feed")

    def test_all_day_event(self):
        """An all-day VEVENT uses date-only fields."""
        events = self._events()
        holiday = next(event for event in events if event["summary"] == "Holiday")
        self.assertEqual(holiday["start"], {"date": "2026-08-10"})
        self.assertEqual(holiday["end"], {"date": "2026-08-11"})

    def test_rrule_expansion(self):
        """A weekly RRULE expands to one occurrence per matching week."""
        events = self._events()
        syncs = [event for event in events if event["summary"] == "Weekly Sync"]
        starts = sorted(event["start"]["dateTime"] for event in syncs)
        # Tuesdays: 2026-08-04, 08-11, 08-18, 08-25 (UNTIL 08-31).
        self.assertEqual(len(syncs), 4)
        self.assertEqual(starts[0], "2026-08-04T14:00:00+00:00")
        self.assertEqual(starts[-1], "2026-08-25T14:00:00+00:00")

    def test_window_filters_out_of_range(self):
        """Events outside the window are dropped."""
        with patch("gcal.IcsFeedDownloader.download", return_value=SAMPLE_ICS):
            events = self.fetcher.events(
                url="https://example.com/a.ics",
                time_min="2026-08-09T00:00:00+00:00",
                time_max="2026-08-11T23:59:59+00:00",
            )
        summaries = {event["summary"] for event in events}
        self.assertNotIn("Standup", summaries)
        self.assertIn("Holiday", summaries)


class TestMainIcsUrl(unittest.TestCase):
    """Tests for the --calendar URL path in Application.run."""

    @staticmethod
    def run_main(argv):
        stdout = io.StringIO()
        stderr = io.StringIO()
        app = gcal.Application(
            argv=argv,
            console=gcal.Console(stdout=stdout, stderr=stderr),
        )
        with patch("gcal.IcsFeedDownloader.download", return_value=SAMPLE_ICS):
            rc = app.run()
        return rc, stdout.getvalue(), stderr.getvalue()

    def test_url_md(self):
        """A calendar URL with --md renders a markdown table."""
        rc, out, _ = self.run_main([
            "--calendar", "https://example.com/a.ics",
            "--md", "--start", "2026-08-01", "--end", "2026-08-31",
        ])
        self.assertEqual(rc, 0)
        self.assertIn("# Calendar events for 2026-08-01", out)
        self.assertIn("Weekly Sync", out)

    def test_url_json(self):
        """A calendar URL emits merged JSON by default."""
        rc, out, _ = self.run_main([
            "--calendar", "https://example.com/a.ics",
            "--start", "2026-08-01", "--end", "2026-08-31",
        ])
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["kind"], "calendar#events")
        self.assertTrue(any(event["summary"] == "Standup" for event in data["items"]))

    def test_url_quiet_does_not_hide_error(self):
        """--quiet still reports a download failure and exits 1."""
        stdout = io.StringIO()
        stderr = io.StringIO()
        app = gcal.Application(
            argv=[
                "--calendar", "https://bad/url.ics",
                "--quiet", "--start", "2026-08-01", "--end", "2026-08-31",
            ],
            console=gcal.Console(stdout=stdout, stderr=stderr),
        )
        with patch("gcal.IcsFeedDownloader.download", side_effect=RuntimeError("boom")):
            rc = app.run()
        self.assertEqual(rc, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("boom", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
