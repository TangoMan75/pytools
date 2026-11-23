#!/usr/bin/env python3
"""Tests for gmail module."""
# noqa: E402

import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

import gmail

# These tests intentionally exercise private query and rendering helpers.
# noqa: SLF001


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

    def params(self, *, index=0):
        """Return the parsed ``--params`` payload of one recorded call."""
        args = self.calls[index]
        return json.loads(args[args.index("--params") + 1])


#--------------------------------------------------
# Date helpers
#--------------------------------------------------


class TestParseDate(unittest.TestCase):
    """Tests for GmailDate.parse."""

    def test_valid_date_passes_through(self):
        """A valid YYYY-MM-DD string is returned unchanged."""
        self.assertEqual(gmail.GmailDate.parse(value="2026-08-15"), "2026-08-15")

    def test_invalid_date_raises(self):
        """Bad input raises ValueError naming the expected format."""
        with self.assertRaises(ValueError) as ctx:
            gmail.GmailDate.parse(value="2026-13-45")
        self.assertIn("invalid date", str(ctx.exception))


class TestGmailDate(unittest.TestCase):
    """Tests for GmailDate.search_value."""

    def test_converts_to_slashes(self):
        """Dashes are converted to Gmail's YYYY/MM/DD form."""
        self.assertEqual(gmail.GmailDate.search_value(value="2026-08-15"), "2026/08/15")


class TestNextDate(unittest.TestCase):
    """Tests for GmailDate.next_day."""

    def test_returns_calendar_day_after(self):
        """The day after the given date is returned as YYYY-MM-DD only."""
        self.assertEqual(gmail.GmailDate.next_day(value="2026-08-15"), "2026-08-16")

    def test_returns_date_without_time_component(self):
        """The result must not include a time component (Gmail rejects it)."""
        self.assertNotIn("T", gmail.GmailDate.next_day(value="2026-08-15"))

    def test_crosses_month_boundary(self):
        """The last day of a month rolls into the next month."""
        self.assertEqual(gmail.GmailDate.next_day(value="2026-08-31"), "2026-09-01")

    def test_crosses_year_boundary(self):
        """The last day of December rolls into the next year."""
        self.assertEqual(gmail.GmailDate.next_day(value="2026-12-31"), "2027-01-01")

    def test_leap_day_follows_feb_28_in_leap_year(self):
        """Feb 28 2024 is followed by Feb 29 2024."""
        self.assertEqual(gmail.GmailDate.next_day(value="2024-02-28"), "2024-02-29")


#--------------------------------------------------
# Query builders
#--------------------------------------------------


class TestLabelQuery(unittest.TestCase):
    """Tests for GmailQuery.label."""

    def test_bare_token_passes_through(self):
        """Simple labels are not quoted."""
        self.assertEqual(gmail.GmailQuery.label(value="INBOX"), "label:INBOX")

    def test_whitespace_is_quoted(self):
        """Labels containing whitespace are quoted."""
        self.assertEqual(gmail.GmailQuery.label(value="My Label"), 'label:"My Label"')

    def test_nested_label_passes_through(self):
        """Nested names with a slash are not quoted."""
        self.assertEqual(gmail.GmailQuery.label(value="Work/Projects"), "label:Work/Projects")

    def test_strips_surrounding_space(self):
        """Leading and trailing whitespace is stripped."""
        self.assertEqual(gmail.GmailQuery.label(value="  INBOX  "), "label:INBOX")

    def test_blank_returns_empty(self):
        """A blank label produces no query fragment."""
        self.assertEqual(gmail.GmailQuery.label(value="   "), "")


class TestAddressQuery(unittest.TestCase):
    """Tests for GmailQuery.address."""

    def test_bare_address_passes_through(self):
        """Bare addresses are not quoted."""
        self.assertEqual(
            gmail.GmailQuery.address(operator="from", value="alice@example.com"),
            "from:alice@example.com",
        )

    def test_whitespace_is_quoted(self):
        """Names containing whitespace are quoted."""
        self.assertEqual(
            gmail.GmailQuery.address(operator="to", value="Jane Doe"),
            'to:"Jane Doe"',
        )

    def test_blank_returns_empty(self):
        """A blank address produces no query fragment."""
        self.assertEqual(gmail.GmailQuery.address(operator="from", value="  "), "")


#--------------------------------------------------
# Message parsing
#--------------------------------------------------


class TestHeader(unittest.TestCase):
    """Tests for MessageParser.header."""

    def test_lookup_is_case_insensitive(self):
        """Header names match regardless of case."""
        headers = [{"name": "From", "value": "a@b.com"}, {"name": "SUBJECT", "value": "Hi"}]
        self.assertEqual(gmail.MessageParser.header(headers=headers, name="subject"), "Hi")
        self.assertEqual(gmail.MessageParser.header(headers=headers, name="from"), "a@b.com")

    def test_missing_header_returns_empty(self):
        """An absent header yields an empty string."""
        headers = [{"name": "From", "value": "x"}]
        self.assertEqual(gmail.MessageParser.header(headers=headers, name="Date"), "")

    def test_none_headers_returns_empty(self):
        """A None headers list yields an empty string."""
        self.assertEqual(gmail.MessageParser.header(headers=None, name="From"), "")


class TestFormatDate(unittest.TestCase):
    """Tests for MessageParser.format_date."""

    def test_parses_rfc2822(self):
        """A valid RFC2822 date is reformatted."""
        self.assertEqual(
            gmail.MessageParser.format_date(value="Tue, 13 Aug 2026 10:30:00 +0200"),
            "2026-08-13 10:30",
        )

    def test_empty_returns_empty(self):
        """An empty header yields an empty string."""
        self.assertEqual(gmail.MessageParser.format_date(value=""), "")

    def test_malformed_falls_back_to_raw(self):
        """Malformed dates are returned unchanged."""
        self.assertEqual(gmail.MessageParser.format_date(value="garbage"), "garbage")


class TestCleanSubject(unittest.TestCase):
    """Tests for MessageParser.clean_subject."""

    def test_strips_and_returns(self):
        """Surrounding whitespace is stripped."""
        self.assertEqual(gmail.MessageParser.clean_subject(value="  Hello  "), "Hello")

    def test_empty_uses_fallback(self):
        """Empty subjects become a placeholder."""
        self.assertEqual(gmail.MessageParser.clean_subject(value=""), "(no subject)")

    def test_none_uses_fallback(self):
        """None subjects become a placeholder."""
        self.assertEqual(gmail.MessageParser.clean_subject(value=None), "(no subject)")


class TestSenderInfo(unittest.TestCase):
    """Tests for MessageParser.sender."""

    def test_returns_name_and_email(self):
        """A dict 'from' yields its name and email."""
        message = {"from": {"name": "Alice", "email": "alice@example.com"}}
        self.assertEqual(
            gmail.MessageParser.sender(message=message),
            ("Alice", "alice@example.com"),
        )

    def test_missing_from_returns_blanks(self):
        """No 'from' key yields two empty strings."""
        self.assertEqual(gmail.MessageParser.sender(message={}), ("", ""))

    def test_non_dict_from_returns_blanks(self):
        """A non-dict 'from' yields two empty strings."""
        self.assertEqual(gmail.MessageParser.sender(message={"from": "Alice"}), ("", ""))


class TestMsgSortKey(unittest.TestCase):
    """Tests for MessageParser.sort_key."""

    def test_returns_epoch_milliseconds(self):
        """The Date header is converted to epoch milliseconds."""
        message = {"date": "Tue, 13 Aug 2026 10:30:00 +0200"}
        expected = int(parsedate_to_datetime(message["date"]).timestamp() * 1000)
        self.assertEqual(gmail.MessageParser.sort_key(message=message), expected)

    def test_malformed_returns_zero(self):
        """An unparseable date yields zero."""
        self.assertEqual(gmail.MessageParser.sort_key(message={"date": "nope"}), 0)

    def test_missing_returns_zero(self):
        """A missing date yields zero."""
        self.assertEqual(gmail.MessageParser.sort_key(message={}), 0)


#--------------------------------------------------
# Rendering
#--------------------------------------------------


class TestRenderMessageMd(unittest.TestCase):
    """Tests for MarkdownRenderer.render_message."""

    def setUp(self):
        """Build the renderer used by each test."""
        self.renderer = gmail.MarkdownRenderer()

    def test_renders_front_matter_and_body(self):
        """YAML front matter, heading, and body are rendered."""
        message = {
            "subject": "Hello",
            "from": {"name": "Alice", "email": "alice@example.com"},
            "date": "Tue, 13 Aug 2026 10:30:00 +0200",
            "body_text": "Body here",
        }
        out = self.renderer.render_message(message=message)
        self.assertIn('- subject: "Hello"', out)
        self.assertIn('- from: "Alice"', out)
        self.assertIn('- email: "alice@example.com"', out)
        self.assertIn("- date: 2026-08-13 10:30", out)
        self.assertIn("## Hello", out)
        self.assertIn("Body here", out)

    def test_empty_subject_and_body(self):
        """Placeholders are used for empty subject; body stays empty."""
        out = self.renderer.render_message(message={})
        self.assertIn('subject: "(no subject)"', out)
        self.assertIn("## (no subject)", out)

    def test_includes_message_id_when_present(self):
        """The Gmail id is rendered in front matter when available."""
        out = self.renderer.render_message(message={"subject": "Hi", "id": "m1"})
        self.assertIn('- id: "m1"', out)

    def test_preserves_html_links_missing_from_text(self):
        """HTML hrefs absent from body_text are appended as markdown links."""
        message = {
            "subject": "Offer",
            "body_text": "Une nouvelle offre est disponible Offre : Dev Postuler Voir l'offre",
            "body_html": (
                '<p>Une nouvelle offre est disponible Offre : Dev</p>'
                '<a href="https://example.com/jobs/dev-1">Postuler</a>'
                '<a href="https://example.com/jobs/dev-1-view">Voir l\'offre</a>'
            ),
        }
        out = self.renderer.render_message(message=message)
        self.assertIn("Links:", out)
        self.assertIn("[Postuler](https://example.com/jobs/dev-1)", out)
        self.assertIn("[Voir l'offre](https://example.com/jobs/dev-1-view)", out)

    def test_does_not_duplicate_links_already_in_text(self):
        """URLs already present in body_text are not re-listed."""
        url = "https://example.com/jobs/dev-1"
        message = {
            "subject": "Offer",
            "body_text": f"Postuler: {url}",
            "body_html": f'<a href="{url}">Postuler</a>',
        }
        out = self.renderer.render_message(message=message)
        self.assertNotIn("Links:", out)
        self.assertEqual(out.count(url), 1)

    def test_html_only_body_extracts_text_and_links(self):
        """When only body_html exists, text and links are both rendered."""
        message = {
            "subject": "Offer",
            "body_html": (
                "<div>Offre : Lead PHP Symfony</div>"
                '<a href="https://example.com/apply/42">Postuler</a>'
            ),
        }
        out = self.renderer.render_message(message=message)
        self.assertIn("Offre : Lead PHP Symfony", out)
        self.assertIn("Links:", out)
        self.assertIn("[Postuler](https://example.com/apply/42)", out)

    def test_skips_fragment_and_tracking_only_anchors_without_href(self):
        """Fragment-only hrefs are omitted from the Links section."""
        message = {
            "subject": "Offer",
            "body_text": "See the offer",
            "body_html": '<a href="#top">Top</a><a href="https://example.com/job">Job</a>',
        }
        out = self.renderer.render_message(message=message)
        self.assertIn("[Job](https://example.com/job)", out)
        self.assertNotIn("[Top]", out)


class TestRenderMarkdown(unittest.TestCase):
    """Tests for MarkdownRenderer.render."""

    def setUp(self):
        """Build the renderer used by each test."""
        self.renderer = gmail.MarkdownRenderer()

    def test_empty_messages(self):
        """An empty list renders the no-messages placeholder."""
        self.assertEqual(
            self.renderer.render(messages=[]),
            "_No messages in this range._\n",
        )

    def test_multiple_messages_separated_by_blank_line(self):
        """Each message block is rendered and joined by blank lines."""
        message = {
            "subject": "Hello",
            "from": {"name": "Alice", "email": "a@b.com"},
            "date": "",
            "body_text": "Body",
        }
        out = self.renderer.render(messages=[message, message])
        self.assertEqual(out.count("## Hello"), 2)
        self.assertEqual(out.count("---"), 4)


#--------------------------------------------------
# gws calls
#--------------------------------------------------


class TestListMessageIds(unittest.TestCase):
    """Tests for GmailClient.list_message_ids."""

    def test_paginates_until_exhausted(self):
        """nextPageToken is followed until the result set is complete."""
        responses = [
            '{"messages": [{"id": "a", "threadId": "ta"}], "nextPageToken": "token-1"}',
            '{"messages": [{"id": "b", "threadId": "tb"}], "nextPageToken": "token-2"}',
            '{"messages": [{"id": "c", "threadId": "tc"}]}',
        ]
        runner = FakeGwsRunner(responses=responses)
        client = gmail.GmailClient(runner=runner)
        result = client.list_message_ids(query="q", max_results=100)
        self.assertEqual(
            result,
            [
                {"id": "a", "threadId": "ta"},
                {"id": "b", "threadId": "tb"},
                {"id": "c", "threadId": "tc"},
            ],
        )
        self.assertEqual(len(runner.calls), 3)
        self.assertEqual(runner.params(index=1)["pageToken"], "token-1")
        self.assertEqual(runner.params(index=2)["pageToken"], "token-2")

    def test_empty_result(self):
        """No messages yields an empty list."""
        runner = FakeGwsRunner(responses=['{"messages": []}'])
        client = gmail.GmailClient(runner=runner)
        self.assertEqual(client.list_message_ids(query="q", max_results=100), [])

    def test_non_dict_response_breaks(self):
        """A non-dict response stops pagination gracefully."""
        runner = FakeGwsRunner(responses=["[]"])
        client = gmail.GmailClient(runner=runner)
        self.assertEqual(client.list_message_ids(query="q", max_results=100), [])


class TestGetMessage(unittest.TestCase):
    """Tests for GmailClient.get_message."""

    def test_fetches_metadata(self):
        """The get call requests format=metadata with the needed headers."""
        runner = FakeGwsRunner(responses=['{"id": "m1"}'])
        client = gmail.GmailClient(runner=runner)
        self.assertEqual(client.get_message(message_id="m1"), {"id": "m1"})
        params = runner.params()
        self.assertEqual(params["format"], "metadata")
        self.assertEqual(params["id"], "m1")


class TestReadMessage(unittest.TestCase):
    """Tests for GmailClient.read_message."""

    def test_reads_with_headers(self):
        """The +read call passes the message id and --headers."""
        runner = FakeGwsRunner(responses=['{"id": "m1"}'])
        client = gmail.GmailClient(runner=runner)
        self.assertEqual(client.read_message(message_id="m1"), {"id": "m1"})
        args = runner.calls[0]
        self.assertIn("+read", args)
        self.assertIn("--id", args)
        self.assertIn("--headers", args)
        self.assertEqual(args[args.index("--id") + 1], "m1")


#--------------------------------------------------
# main / CLI
#--------------------------------------------------


class TestMain(unittest.TestCase):
    """Tests for Application with a scripted gws runner."""

    @staticmethod
    def run_app(argv, responses):
        """Run the application with argv and mocked gws."""
        out = io.StringIO()
        err = io.StringIO()
        runner = FakeGwsRunner(responses=responses)
        with redirect_stdout(out), redirect_stderr(err):
            rc = gmail.Application(argv=argv, runner=runner).run()
        return rc, out.getvalue(), err.getvalue(), runner

    def test_query_uses_date_only_before_value(self):
        """Gmail's exclusive next-day before: includes the end day."""
        rc, _, _, runner = self.run_app(
            ["--start", "2026-08-01", "--end", "2026-08-15"],
            ['{"messages": []}'],
        )
        self.assertEqual(rc, 0)
        self.assertEqual(runner.params()["q"], "after:2026/08/01 before:2026/08/16")

    def test_query_includes_filters(self):
        """Sender, recipient, and label filters are folded into q."""
        rc, _, _, runner = self.run_app(
            [
                "--start", "2026-08-01", "--end", "2026-08-02",
                "--from", "alice@example.com",
                "--to", "bob@example.com",
                "--label", "My Label",
            ],
            ['{"messages": []}'],
        )
        self.assertEqual(rc, 0)
        query = runner.params()["q"]
        self.assertIn("after:2026/08/01", query)
        self.assertIn("before:2026/08/03", query)
        self.assertIn("from:alice@example.com", query)
        self.assertIn("to:bob@example.com", query)
        self.assertIn('label:"My Label"', query)

    def test_json_output(self):
        """Messages are emitted as a JSON array on stdout."""
        responses = [
            '{"messages": [{"id": "m1", "threadId": "t1"}]}',
            '{"id": "m1", "threadId": "t1"}',
        ]
        rc, out, _, _ = self.run_app(
            ["--start", "2026-08-01", "--end", "2026-08-01"], responses
        )
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out), [{"id": "m1", "threadId": "t1"}])

    def test_md_output(self):
        """--md renders front matter plus the body."""
        responses = [
            '{"messages": [{"id": "m1", "threadId": "t1"}]}',
            json.dumps({
                "id": "m1",
                "threadId": "t1",
                "subject": "Hello",
                "from": {"name": "Alice", "email": "alice@example.com"},
                "date": "Tue, 13 Aug 2026 10:30:00 +0200",
                "body_text": "Body here",
            }),
        ]
        rc, out, _, _ = self.run_app(
            ["--md", "--start", "2026-08-01", "--end", "2026-08-01"], responses
        )
        self.assertEqual(rc, 0)
        self.assertIn("## Hello", out)
        self.assertIn("Body here", out)
        self.assertIn('- id: "m1"', out)

    def test_md_preserves_html_links(self):
        """--md keeps application hrefs that plain body_text drops."""
        responses = [
            '{"messages": [{"id": "m1", "threadId": "t1"}]}',
            json.dumps({
                "thread_id": "t1",
                "subject": "Offer",
                "from": {"name": "Collective", "email": "ops@collective.work"},
                "date": "Thu, 01 Oct 2026 16:40:26 +0000 (UTC)",
                "body_text": "Offre : Lead PHP Symfony Postuler Voir l'offre",
                "body_html": (
                    '<b>Offre :</b> Lead PHP Symfony'
                    '<a href="https://www.example.com/jobs/lead-php">Postuler</a>'
                ),
            }),
        ]
        rc, out, _, _ = self.run_app(
            ["--md", "--start", "2026-08-01", "--end", "2026-08-01"], responses
        )
        self.assertEqual(rc, 0)
        self.assertIn("Links:", out)
        self.assertIn("[Postuler](https://www.example.com/jobs/lead-php)", out)

    def test_read_message_flow(self):
        """--read outputs the single message JSON."""
        message = {"id": "123", "snippet": "hi"}
        rc, out, _, _ = self.run_app(["--read", "123"], [json.dumps(message)])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out), message)

    def test_read_with_md_outputs_markdown(self):
        """--read combined with --md renders one markdown message block."""
        message = {
            "subject": "Offer",
            "from": {"name": "Collective", "email": "ops@collective.work"},
            "date": "Thu, 01 Oct 2026 16:40:26 +0000 (UTC)",
            "body_text": "Offre : Dev Postuler",
            "body_html": '<a href="https://example.com/apply/9">Postuler</a>',
        }
        rc, out, _, _ = self.run_app(["--read", "abc123", "--md"], [json.dumps(message)])
        self.assertEqual(rc, 0)
        self.assertIn("## Offer", out)
        self.assertIn('- id: "abc123"', out)
        self.assertIn("[Postuler](https://example.com/apply/9)", out)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(out)

    def test_read_error_returns_1(self):
        """A failed read exits 1 with an error on stderr."""
        rc, out, err, _ = self.run_app(["--read", "123"], RuntimeError("boom"))
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("boom", err)

    def test_list_error_returns_1(self):
        """A failed list exits 1 with an error on stderr."""
        rc, out, err, _ = self.run_app(
            ["--start", "2026-08-01", "--end", "2026-08-01"], RuntimeError("boom")
        )
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("boom", err)

    def test_quiet_does_not_hide_list_error(self):
        """--quiet still reports a list error and exits 1."""
        rc, out, err, _ = self.run_app(
            ["--quiet", "--start", "2026-08-01", "--end", "2026-08-01"],
            RuntimeError("boom"),
        )
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("boom", err)

    def test_quiet_does_not_hide_read_error(self):
        """--quiet still reports a read error and exits 1."""
        rc, out, err, _ = self.run_app(["--quiet", "--read", "123"], RuntimeError("boom"))
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("boom", err)

    def test_end_before_start_returns_2(self):
        """An end date before the start date exits 2."""
        rc, _, err, _ = self.run_app(
            ["--start", "2026-08-15", "--end", "2026-08-01"], []
        )
        self.assertEqual(rc, 2)
        self.assertIn("before start", err)

    def test_invalid_start_exits_2(self):
        """A malformed start date exits 2 with an error on stderr."""
        rc, _, err, _ = self.run_app(["--start", "not-a-date"], [])
        self.assertEqual(rc, 2)
        self.assertIn("invalid date", err)

    def test_skips_failed_message_fetches(self):
        """A failing per-message fetch is skipped with a warning."""
        responses = [
            '{"messages": [{"id": "m1", "threadId": "t1"}, {"id": "m2", "threadId": "t2"}]}',
            RuntimeError("bad message"),
            '{"id": "m2", "threadId": "t2"}',
        ]
        rc, out, err, _ = self.run_app(
            ["--start", "2026-08-01", "--end", "2026-08-01"], responses
        )
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out), [{"id": "m2", "threadId": "t2"}])
        self.assertIn("skipping message m1", err)

    def test_max_messages_truncates(self):
        """Fetching is capped at --max-messages with a warning."""
        refs = [{"id": f"m{i}", "threadId": f"t{i}"} for i in range(3)]
        responses = [json.dumps({"messages": refs})] + [json.dumps(ref) for ref in refs[:2]]
        rc, out, err, _ = self.run_app(
            ["--start", "2026-08-01", "--end", "2026-08-01", "--max-messages", "2"],
            responses,
        )
        self.assertEqual(rc, 0)
        self.assertEqual(len(json.loads(out)), 2)
        self.assertIn("truncated", err)


if __name__ == "__main__":
    unittest.main()
