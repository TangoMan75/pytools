#!/usr/bin/env python3
# noqa: SLF001
"""Tests for jira-rest module."""

import importlib.util
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "jira-rest.py"


def load_module():
    """Load jira-rest.py as a module by path (avoids name clashes)."""
    spec = importlib.util.spec_from_file_location("jira_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


jira = load_module()


class FakeResponse:
    """Minimal stand-in for urllib response context manager."""

    def __init__(self, payload):
        self._bytes = json.dumps(payload).encode('utf-8')

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._bytes


class TestAdfToMarkdown(unittest.TestCase):
    """Tests for ADF -> markdown conversion."""

    def test_plain_text(self):
        self.assertEqual(jira.AdfConverter.convert(node="hello"), "hello")

    def test_text_node_with_marks(self):
        node = {"type": "text", "text": "bold", "marks": [{"type": "strong"}]}
        self.assertEqual(jira.AdfConverter.convert(node=node), "**bold**")

    def test_heading(self):
        node = {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Title"}]}
        self.assertEqual(jira.AdfConverter.convert(node=node), "## Title")

    def test_bullet_list(self):
        node = {
            "type": "bulletList",
            "content": [
                {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "a"}]}]},
                {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "b"}]}]},
            ],
        }
        self.assertEqual(jira.AdfConverter.convert(node=node), "- a\n- b")

    def test_code_block(self):
        node = {"type": "codeBlock", "attrs": {"language": "python"}, "content": [{"type": "text", "text": "print(1)"}]}
        self.assertEqual(jira.AdfConverter.convert(node=node), "```python\nprint(1)\n```")

    def test_link(self):
        node = {"type": "text", "text": "site", "marks": [{"type": "link", "attrs": {"href": "https://x"}}]}
        self.assertEqual(jira.AdfConverter.convert(node=node), "[site](https://x)")


class TestFormatDate(unittest.TestCase):
    """Tests for timestamp formatting."""

    def test_trailing_z(self):
        self.assertEqual(jira.MarkdownRenderer.format_date("2024-01-15T10:30:00.000Z"), "2024-01-15 10:30")

    def test_offset_no_colon(self):
        self.assertEqual(jira.MarkdownRenderer.format_date("2024-01-15T10:30:00.000+0000"), "2024-01-15 10:30")

    def test_empty(self):
        self.assertEqual(jira.MarkdownRenderer.format_date(""), "")


class TestUnwrap(unittest.TestCase):
    """Tests for envelope unwrapping."""

    def test_bare_issue(self):
        obj = {"key": "X-1", "fields": {"summary": "s"}}
        self.assertEqual(jira.ResponseUnwrapper.unwrap_issue(obj)["key"], "X-1")

    def test_data_envelope(self):
        obj = {"ok": True, "data": {"key": "X-1", "fields": {}}}
        self.assertEqual(jira.ResponseUnwrapper.unwrap_issue(obj)["key"], "X-1")

    def test_comments_list(self):
        self.assertEqual(jira.ResponseUnwrapper.unwrap_comments([{"id": "1"}]), [{"id": "1"}])

    def test_comments_wrapped(self):
        obj = {"comments": [{"id": "1"}]}
        self.assertEqual(jira.ResponseUnwrapper.unwrap_comments(obj), [{"id": "1"}])


class TestRendering(unittest.TestCase):
    """Tests for markdown rendering of issues and comments."""

    def _issue(self):
        return {
            "key": "PROJ-123",
            "fields": {
                "summary": "Broken thing",
                "status": {"name": "Open"},
                "issuetype": {"name": "Bug"},
                "priority": {"name": "High"},
                "assignee": {"displayName": "Ada Lovelace"},
                "reporter": {"displayName": "Alan Turing"},
                "created": "2024-01-15T10:30:00.000+0000",
                "updated": "2024-01-16T10:30:00.000+0000",
                "labels": ["backend"],
                "components": [{"name": "api"}],
                "description": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "It is broken."}]}]},
            },
        }

    def test_issue_heading_and_sections(self):
        md = jira.MarkdownRenderer().render_issue(
            issue=self._issue(),
            url="https://x.atlassian.net/browse/PROJ-123",
        )
        self.assertIn("# PROJ-123: Broken thing", md)
        self.assertIn("<https://x.atlassian.net/browse/PROJ-123>", md)
        self.assertIn("## Description", md)
        self.assertIn("It is broken.", md)
        self.assertIn("| Status | Open |", md)

    def test_comments_section(self):
        md = jira.MarkdownRenderer().render_comments(comments={
            "comments": [
                {"id": "5", "author": {"displayName": "Grace Hopper"}, "created": "2024-02-01T09:00:00.000+0000", "body": "looks fine"},
            ],
        })
        self.assertIn("## Comments", md)
        self.assertIn("Grace Hopper", md)
        self.assertIn("looks fine", md)

    def test_no_comments(self):
        md = jira.MarkdownRenderer().render_comments(comments=[])
        self.assertIn("_No comments._", md)


class TestLoadDotenv(unittest.TestCase):
    """Tests for .env parsing."""

    def test_parses_simple_and_quoted(self):
        data = 'ATLASSIAN_SITE=shippeo.atlassian.net\n# comment\nATLASSIAN_EMAIL="a@b.com"\n'
        with patch.object(Path, "exists", return_value=True), patch.object(Path, "read_text", return_value=data):
            values = jira.JiraConfig(path=Path(".env")).load()
        self.assertEqual(values["ATLASSIAN_SITE"], "shippeo.atlassian.net")
        self.assertEqual(values["ATLASSIAN_EMAIL"], "a@b.com")

    def test_missing_file_returns_empty(self):
        with patch.object(Path, "exists", return_value=False):
            self.assertEqual(jira.JiraConfig(path=Path(".env")).load(), {})

    def test_export_prefix_is_stripped(self):
        data = 'export ATLASSIAN_SITE=shippeo.atlassian.net\nATLASSIAN_EMAIL=a@b.com\n'
        with patch.object(Path, "exists", return_value=True), patch.object(Path, "read_text", return_value=data):
            values = jira.JiraConfig(path=Path(".env")).load()
        self.assertEqual(values["ATLASSIAN_SITE"], "shippeo.atlassian.net")
        self.assertEqual(values["ATLASSIAN_EMAIL"], "a@b.com")

    def test_inline_comment_is_stripped(self):
        data = 'ATLASSIAN_SITE=shippeo.atlassian.net # instance\n'
        with patch.object(Path, "exists", return_value=True), patch.object(Path, "read_text", return_value=data):
            values = jira.JiraConfig(path=Path(".env")).load()
        self.assertEqual(values["ATLASSIAN_SITE"], "shippeo.atlassian.net")


class TestDotenvWrite(unittest.TestCase):
    """Tests for writing and round-tripping the .env file."""

    def test_write_then_load_roundtrip(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            jira.JiraConfig(path=path).save(site="site.net", email="me@x.com", token="TOK")
            loaded = jira.JiraConfig(path=path).load()
        self.assertEqual(loaded["ATLASSIAN_SITE"], "site.net")
        self.assertEqual(loaded["ATLASSIAN_EMAIL"], "me@x.com")
        self.assertEqual(loaded["ATLASSIAN_API_TOKEN"], "TOK")

    def test_saved_file_is_owner_only(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            jira.JiraConfig(path=path).save(site="site.net", email="me@x.com", token="TOK")
            mode = path.stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)


class TestJiraClient(unittest.TestCase):
    """Tests for the REST client (network mocked)."""

    def _client(self):
        return jira.JiraClient(site="shippeo.atlassian.net", email="me@x.com", token="TOKEN")

    def test_basic_auth_header(self):
        import base64
        headers = self._client()._headers()
        expected = base64.b64encode(b"me@x.com:TOKEN").decode("ascii")
        self.assertEqual(headers["Authorization"], f"Basic {expected}")

    def test_bearer_auth_when_no_email(self):
        client = jira.JiraClient(site="shippeo.atlassian.net", email="", token="BEARER")
        self.assertEqual(client._headers()["Authorization"], "Bearer BEARER")

    def test_http_site_is_rejected(self):
        with self.assertRaises(ValueError):
            jira.JiraClient(site="http://shippeo.atlassian.net", email="me@x.com", token="TOKEN")

    def test_timeout_is_forwarded_to_urlopen(self):
        client = jira.JiraClient(
            site="shippeo.atlassian.net",
            email="me@x.com",
            token="TOKEN",
            timeout=15,
        )
        with patch.object(jira.urllib.request, "urlopen", return_value=FakeResponse({"key": "X", "fields": {}})) as mocked:
            client.get_issue(key="X")
        self.assertEqual(mocked.call_args.kwargs.get("timeout"), 15)

    def test_default_timeout_is_30(self):
        client = jira.JiraClient(site="shippeo.atlassian.net", email="me@x.com", token="TOKEN")
        with patch.object(jira.urllib.request, "urlopen", return_value=FakeResponse({"key": "X", "fields": {}})) as mocked:
            client.get_issue(key="X")
        self.assertEqual(mocked.call_args.kwargs.get("timeout"), 30)

    def test_get_issue_url(self):
        client = self._client()
        with patch.object(jira.urllib.request, "urlopen", return_value=FakeResponse({"key": "PROJ-1", "fields": {}})):
            issue = client.get_issue(key="PROJ-1")
        self.assertEqual(issue["key"], "PROJ-1")

    def test_dry_run_urls(self):
        client = self._client()
        self.assertEqual(
            client.issue_api_url(key="PROJ-1"),
            "https://shippeo.atlassian.net/rest/api/3/issue/PROJ-1",
        )
        self.assertEqual(
            client.comments_api_url(key="PROJ-1"),
            "https://shippeo.atlassian.net/rest/api/3/issue/PROJ-1/comment?startAt=0&maxResults=100",
        )
        self.assertEqual(
            client.comment_api_url(key="PROJ-1"),
            "https://shippeo.atlassian.net/rest/api/3/issue/PROJ-1/comment",
        )

    def test_get_comments_paginates(self):
        client = self._client()
        pages = [
            {"comments": [{"id": "1"}], "total": 2},
            {"comments": [{"id": "2"}], "total": 2},
        ]
        calls = {"n": 0}

        def fake_urlopen(request, **kwargs):
            payload = pages[calls["n"]]
            calls["n"] += 1
            return FakeResponse(payload)

        with patch.object(jira.urllib.request, "urlopen", side_effect=fake_urlopen):
            result = client.get_comments(key="PROJ-1")
        self.assertEqual(len(result["comments"]), 2)
        self.assertEqual(result["total"], 2)

    def test_http_error_raises_runtime(self):
        import urllib.error
        with patch.object(jira.urllib.request, "urlopen", side_effect=urllib.error.HTTPError(
                "url", 401, "unauthorized", {}, io.BytesIO(b'{"error": "bad"}'))):
            with self.assertRaises(RuntimeError):
                self._client().get_comments(key="PROJ-1")

    def test_add_comment_posts_adf(self):
        import urllib.request
        captured = {}

        def fake_urlopen(request, **kwargs):
            captured["method"] = request.method
            captured["body"] = request.data.decode("utf-8")
            captured["content_type"] = request.headers.get("Content-type")
            return FakeResponse({"id": "9", "body": {}})

        with patch.object(urllib.request, "urlopen", side_effect=fake_urlopen):
            result = self._client().add_comment(key="PROJ-1", body="hello world")
        self.assertEqual(captured["method"], "POST")
        self.assertIn("application/json", captured["content_type"])
        self.assertIn("hello world", captured["body"])
        self.assertEqual(result["id"], "9")


class TestTicketMarkdown(unittest.TestCase):
    """Tests for the ticket markdown service."""

    def test_render_combines_issue_and_comments(self):
        class FakeClient:
            def get_issue(self, *, key):
                return {"key": key, "fields": {"summary": "Broken thing"}}

            def get_comments(self, *, key):
                return {"comments": [{"id": "1", "body": "looks fine"}]}

            def issue_url(self, *, key):
                return f"https://x/browse/{key}"

        markdown = jira.TicketMarkdown(client=FakeClient()).render(key="PROJ-1")
        self.assertIn("# PROJ-1: Broken thing", markdown)
        self.assertIn("## Comments", markdown)
        self.assertIn("looks fine", markdown)


class TestCliContract(unittest.TestCase):
    """Tests for the command-line surface."""

    def test_help_exits_zero(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True, text=True, cwd=ROOT, check=False,
        )
        self.assertEqual(result.returncode, 0)

    def test_help_advertises_options(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True, text=True, cwd=ROOT, check=False,
        )
        for option in ("init", "read", "update", "--verbose", "--quiet"):
            self.assertIn(option, result.stdout)
        self.assertNotIn("--env", result.stdout)
        self.assertNotIn("--token", result.stdout)

    def test_no_key_exits_two(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True, text=True, cwd=ROOT, check=False,
        )
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
