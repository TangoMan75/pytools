#!/usr/bin/env python3
"""Tests for gcontacts module."""
# noqa: E402


import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

import gcontacts

# These tests intentionally exercise private rendering and gws helpers.
# noqa: SLF001, E402


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

    def body(self, *, index=0):
        """Return the parsed ``--json`` body of one recorded call."""
        args = self.calls[index]
        return json.loads(args[args.index("--json") + 1])


#--------------------------------------------------
# helpers
#--------------------------------------------------


class TestResourceId(unittest.TestCase):
    """Tests for PersonBodyBuilder.resource_id."""

    def test_strips_prefix(self):
        """A people/... resource name yields its bare id."""
        self.assertEqual(
            gcontacts.PersonBodyBuilder.resource_id(resource_name="people/c123"),
            "c123",
        )

    def test_passthrough_without_prefix(self):
        """An id without a slash passes through unchanged."""
        self.assertEqual(
            gcontacts.PersonBodyBuilder.resource_id(resource_name="c123"),
            "c123",
        )


#--------------------------------------------------
# body builders
#--------------------------------------------------


class TestBuildPerson(unittest.TestCase):
    """Tests for PersonBodyBuilder.build_person."""

    def test_full_body(self):
        """All convenience flags map to their People API fields."""
        body = gcontacts.PersonBodyBuilder.build_person(
            name="John Doe",
            email="john@x.com",
            phone="+331",
            org="ACME",
            address="1 St",
            note="note",
            url="http://x",
        )
        self.assertEqual(body["names"], [{"displayName": "John Doe"}])
        self.assertEqual(body["emailAddresses"], [{"value": "john@x.com"}])
        self.assertEqual(body["phoneNumbers"], [{"value": "+331"}])
        self.assertEqual(body["organizations"], [{"name": "ACME"}])
        self.assertEqual(body["addresses"], [{"formattedValue": "1 St"}])
        self.assertEqual(body["biographies"], [{"value": "note"}])
        self.assertEqual(body["urls"], [{"value": "http://x"}])

    def test_empty_when_no_flags(self):
        """With no flags the body is empty."""
        self.assertEqual(gcontacts.PersonBodyBuilder.build_person(), {})


class TestBuildUpdateBody(unittest.TestCase):
    """Tests for PersonBodyBuilder.build_update_body."""

    def test_body_and_mask(self):
        """Provided fields are sourced and the mask lists their paths."""
        body, mask = gcontacts.PersonBodyBuilder.build_update_body(
            resource_name="people/c123",
            name="John",
            email="john@x.com",
        )
        self.assertEqual(mask, "names,emailAddresses")
        self.assertEqual(body["metadata"]["sources"], [{"type": "CONTACT", "id": "c123"}])
        self.assertEqual(
            body["names"],
            [{"metadata": {"source": {"type": "CONTACT", "id": "c123"}}, "displayName": "John"}],
        )
        self.assertEqual(
            body["emailAddresses"],
            [{"metadata": {"source": {"type": "CONTACT", "id": "c123"}}, "value": "john@x.com"}],
        )

    def test_empty_when_no_flags(self):
        """With no flags the body and mask are empty."""
        self.assertEqual(
            gcontacts.PersonBodyBuilder.build_update_body(resource_name="people/c123"),
            ({}, ""),
        )


#--------------------------------------------------
# rendering
#--------------------------------------------------


class TestRenderMarkdown(unittest.TestCase):
    """Tests for MarkdownRenderer.render."""

    def setUp(self):
        """Build the renderer used by each test."""
        self.renderer = gcontacts.MarkdownRenderer()

    def test_empty_placeholder(self):
        """No contacts renders a placeholder."""
        self.assertEqual(self.renderer.render(people=[]), "_No contacts._\n")

    def test_renders_fields(self):
        """Name, email, phone, and org are rendered."""
        person = {
            "resourceName": "people/c123",
            "names": [{"displayName": "John Doe"}],
            "emailAddresses": [{"value": "john@x.com"}],
            "phoneNumbers": [{"value": "+331"}],
            "organizations": [{"name": "ACME"}],
        }
        out = self.renderer.render(people=[person])
        self.assertIn("# John Doe", out)
        self.assertIn("- email: john@x.com", out)
        self.assertIn("- phone: +331", out)
        self.assertIn("- org: ACME", out)
        self.assertIn("resource: people/c123", out)

    def test_missing_name_placeholder(self):
        """A contact without a name uses a placeholder."""
        self.assertIn("# (no name)", self.renderer.render(people=[{}]))


#--------------------------------------------------
# gws calls
#--------------------------------------------------


class TestGwsCalls(unittest.TestCase):
    """Tests for ContactsClient with a scripted runner."""

    def test_list_contacts_pages(self):
        """Connections are merged across pages and capped by limit."""
        responses = [
            '{"connections": [{"resourceName": "people/a"}], "nextPageToken": "t"}',
            '{"connections": [{"resourceName": "people/b"}]}',
        ]
        runner = FakeGwsRunner(responses=responses)
        client = gcontacts.ContactsClient(runner=runner)
        people = client.list_contacts(mask="names", limit=0)
        self.assertEqual([p["resourceName"] for p in people], ["people/a", "people/b"])

    def test_list_contacts_respects_limit(self):
        """A limit stops collection early across pages."""
        responses = [
            '{"connections": [{"resourceName": "people/a"}, '
            '{"resourceName": "people/b"}], "nextPageToken": "t"}',
            '{"connections": [{"resourceName": "people/c"}]}',
        ]
        runner = FakeGwsRunner(responses=responses)
        client = gcontacts.ContactsClient(runner=runner)
        people = client.list_contacts(mask="names", limit=1)
        self.assertEqual([p["resourceName"] for p in people], ["people/a"])
        self.assertEqual(len(runner.calls), 1)

    def test_search_contacts(self):
        """Search results flatten to their person objects."""
        raw = (
            '{"results": [{"person": {"resourceName": "people/a"}}, '
            '{"person": {"resourceName": "people/b"}}]}'
        )
        runner = FakeGwsRunner(responses=[raw])
        client = gcontacts.ContactsClient(runner=runner)
        people = client.search_contacts(query="john", mask="names")
        self.assertEqual([p["resourceName"] for p in people], ["people/a", "people/b"])

    def test_get_contact(self):
        """get_contact returns the parsed person."""
        runner = FakeGwsRunner(responses=['{"resourceName": "people/a"}'])
        client = gcontacts.ContactsClient(runner=runner)
        self.assertEqual(
            client.get_contact(resource_name="people/a", mask="names"),
            {"resourceName": "people/a"},
        )

    def test_create_contact_sends_body(self):
        """createContact forwards the JSON body."""
        runner = FakeGwsRunner(responses=['{"resourceName": "people/a"}'])
        client = gcontacts.ContactsClient(runner=runner)
        result = client.create_contact(body={"names": [{"displayName": "X"}]})
        self.assertEqual(result, {"resourceName": "people/a"})
        self.assertEqual(runner.body(), {"names": [{"displayName": "X"}]})

    def test_update_contact_sends_mask(self):
        """updateContact sends the resourceName param and updateMask."""
        runner = FakeGwsRunner(responses=['{"resourceName": "people/a"}'])
        client = gcontacts.ContactsClient(runner=runner)
        client.update_contact(
            resource_name="people/a", body={"names": []}, update_mask="names"
        )
        params = runner.params()
        self.assertEqual(params["resourceName"], "people/a")
        self.assertEqual(params["updateMask"], "names")

    def test_delete_contact(self):
        """deleteContact sends the resourceName param."""
        runner = FakeGwsRunner(responses=[""])
        client = gcontacts.ContactsClient(runner=runner)
        client.delete_contact(resource_name="people/a")
        self.assertEqual(runner.params()["resourceName"], "people/a")


#--------------------------------------------------
# main / CLI
#--------------------------------------------------


class TestMain(unittest.TestCase):
    """Tests for Application with a scripted runner."""

    @staticmethod
    def run_app(argv, responses):
        """Run the application with argv and mocked gws."""
        out = io.StringIO()
        err = io.StringIO()
        runner = FakeGwsRunner(responses=responses)
        with redirect_stdout(out), redirect_stderr(err):
            rc = gcontacts.Application(argv=argv, runner=runner).run()
        return rc, out.getvalue(), err.getvalue(), runner

    def test_default_lists(self):
        """With no action, all contacts are listed as JSON."""
        rc, out, _, _ = self.run_app(
            [], ['{"connections": [{"resourceName": "people/a"}]}']
        )
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data[0]["resourceName"], "people/a")

    def test_search(self):
        """--search invokes searchContacts and emits JSON."""
        rc, out, _, _ = self.run_app(
            ["--search", "john"],
            ['{"results": [{"person": {"resourceName": "people/a"}}]}'],
        )
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)[0]["resourceName"], "people/a")

    def test_get(self):
        """--get fetches a single contact."""
        rc, out, _, _ = self.run_app(
            ["--get", "people/a"], ['{"resourceName": "people/a"}']
        )
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["resourceName"], "people/a")

    def test_create_from_flags(self):
        """--create builds a body from convenience flags."""
        rc, out, _, runner = self.run_app(
            ["--create", "--name", "John", "--email", "j@x.com"],
            ['{"resourceName": "people/a"}'],
        )
        self.assertEqual(rc, 0)
        body = runner.body()
        self.assertEqual(body["names"], [{"displayName": "John"}])
        self.assertEqual(body["emailAddresses"], [{"value": "j@x.com"}])
        self.assertEqual(json.loads(out)["resourceName"], "people/a")

    def test_create_from_json(self):
        """--create with --json forwards the raw body."""
        rc, _, _, runner = self.run_app(
            ["--create", "--json", '{"names": [{"displayName": "X"}]}'],
            ['{}'],
        )
        self.assertEqual(rc, 0)
        self.assertEqual(runner.body()["names"], [{"displayName": "X"}])

    def test_create_requires_name(self):
        """--create without --name or --json exits with code 2."""
        err = io.StringIO()
        with redirect_stderr(err):
            with self.assertRaises(SystemExit) as ctx:
                gcontacts.Application(
                    argv=["--create"], runner=FakeGwsRunner(responses=[])
                ).run()
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("requires --name", err.getvalue())

    def test_create_quiet_does_not_hide_error(self):
        """--quiet still reports a create error and exits 1."""
        rc, out, err, _ = self.run_app(
            ["--create", "--name", "John", "--quiet"],
            RuntimeError("boom"),
        )
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("boom", err)

    def test_create_error_returns_1(self):
        """A create error exits 1 with an error on stderr."""
        rc, _, err, _ = self.run_app(
            ["--create", "--name", "John"], RuntimeError("boom")
        )
        self.assertEqual(rc, 1)
        self.assertIn("boom", err)

    def test_update_from_flags(self):
        """--update builds a sourced body and a mask from convenience flags."""
        responses = [
            '{"resourceName": "people/a", "etag": "E1", '
            '"metadata": {"sources": [{"type": "CONTACT", "id": "a"}]}}',
            '{"resourceName": "people/a"}',
        ]
        rc, out, _, runner = self.run_app(
            ["--update", "people/a", "--name", "John", "--email", "j@x.com"],
            responses,
        )
        self.assertEqual(rc, 0)
        self.assertEqual(runner.params(index=1)["updateMask"], "names,emailAddresses")
        self.assertEqual(runner.body(index=1)["metadata"]["sources"][0]["id"], "a")
        self.assertEqual(json.loads(out)["resourceName"], "people/a")

    def test_update_requires_mask_with_json(self):
        """--update with --json but no --update-mask exits with code 2."""
        err = io.StringIO()
        with redirect_stderr(err):
            with self.assertRaises(SystemExit) as ctx:
                gcontacts.Application(
                    argv=["--update", "people/a", "--json", "{}"],
                    runner=FakeGwsRunner(responses=[]),
                ).run()
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("update-mask", err.getvalue())

    def test_update_quiet_does_not_hide_error(self):
        """--quiet still reports an update error and exits 1."""
        rc, out, err, _ = self.run_app(
            ["--update", "people/a", "--name", "John", "--quiet"],
            RuntimeError("boom"),
        )
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("boom", err)

    def test_delete(self):
        """--delete invokes deleteContact and reports success."""
        rc, _, err, runner = self.run_app(["--delete", "people/a"], [""])
        self.assertEqual(rc, 0)
        self.assertEqual(runner.params()["resourceName"], "people/a")
        self.assertIn("Deleted people/a", err)

    def test_delete_quiet_does_not_hide_error(self):
        """--quiet still reports a delete error and exits 1."""
        rc, out, err, _ = self.run_app(
            ["--delete", "people/a", "--quiet"],
            RuntimeError("boom"),
        )
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("boom", err)

    def test_list_quiet_does_not_hide_error(self):
        """--quiet still reports a list error and exits 1."""
        rc, out, err, _ = self.run_app(["--quiet"], RuntimeError("boom"))
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("boom", err)

    def test_list_md(self):
        """--md renders front-matter markdown for the list."""
        rc, out, _, _ = self.run_app(
            ["--md"],
            ['{"connections": [{"resourceName": "people/a", "names": [{"displayName": "John"}]}]}'],
        )
        self.assertEqual(rc, 0)
        self.assertIn("# John", out)
        self.assertIn("resource: people/a", out)

    def test_search_md(self):
        """--md renders search results as markdown."""
        rc, out, _, _ = self.run_app(
            ["--search", "john", "--md"],
            [
                '{"results": [{"person": {"resourceName": "people/a", '
                '"names": [{"displayName": "John"}]}}]}'
            ],
        )
        self.assertEqual(rc, 0)
        self.assertIn("# John", out)

    def test_get_md(self):
        """--md renders a single fetched contact as markdown."""
        rc, out, _, _ = self.run_app(
            ["--get", "people/a", "--md"],
            ['{"resourceName": "people/a", "names": [{"displayName": "John"}]}'],
        )
        self.assertEqual(rc, 0)
        self.assertIn("# John", out)

    def test_update_fetches_then_updates(self):
        """--update convenience flags fetch the contact, attach etag/source,
        then send the update with a derived mask."""
        responses = [
            '{"resourceName": "people/c123", "etag": "E1", '
            '"metadata": {"sources": [{"type": "CONTACT", "id": "c123"}]}}',
            '{"resourceName": "people/c123"}',
        ]
        rc, _, _, runner = self.run_app(
            ["--update", "people/c123", "--name", "John"], responses
        )
        self.assertEqual(rc, 0)
        self.assertEqual(runner.params(index=1)["updateMask"], "names")
        body = runner.body(index=1)
        self.assertEqual(body["etag"], "E1")
        self.assertEqual(body["metadata"]["sources"][0]["id"], "c123")
        self.assertEqual(body["names"][0]["displayName"], "John")

    def test_update_quiet_does_not_hide_get_error(self):
        """--quiet still reports a fetch-before-update error and exits 1."""
        rc, out, err, _ = self.run_app(
            ["--update", "people/c123", "--name", "John", "--quiet"],
            RuntimeError("boom"),
        )
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("boom", err)


class TestSearchPagination(unittest.TestCase):
    """Tests for ContactsClient.search_contacts pagination and limit."""

    def test_pages_until_exhausted(self):
        """Multiple pages are merged into one result list."""
        responses = [
            '{"results": [{"person": {"resourceName": "people/a"}}], "nextPageToken": "t"}',
            '{"results": [{"person": {"resourceName": "people/b"}}]}',
        ]
        runner = FakeGwsRunner(responses=responses)
        client = gcontacts.ContactsClient(runner=runner)
        people = client.search_contacts(query="john", mask="names")
        self.assertEqual([p["resourceName"] for p in people], ["people/a", "people/b"])

    def test_non_dict_response(self):
        """A non-dict response yields an empty list."""
        runner = FakeGwsRunner(responses=["[]"])
        client = gcontacts.ContactsClient(runner=runner)
        self.assertEqual(client.search_contacts(query="john", mask="names"), [])

    def test_limit_caps_results(self):
        """The limit stops collection early across pages."""
        responses = [
            '{"results": [{"person": {"resourceName": "people/a"}}, '
            '{"person": {"resourceName": "people/b"}}], "nextPageToken": "t"}',
            '{"results": [{"person": {"resourceName": "people/c"}}]}',
        ]
        runner = FakeGwsRunner(responses=responses)
        client = gcontacts.ContactsClient(runner=runner)
        people = client.search_contacts(query="john", mask="names", limit=1)
        self.assertEqual([p["resourceName"] for p in people], ["people/a"])
        self.assertEqual(len(runner.calls), 1)


class TestListLimitClamp(unittest.TestCase):
    """Tests for negative / zero limit handling in list_contacts."""

    def test_negative_limit_treated_as_all(self):
        """A negative limit does not produce a negative pageSize."""
        responses = ['{"connections": [{"resourceName": "people/a"}]}']
        runner = FakeGwsRunner(responses=responses)
        client = gcontacts.ContactsClient(runner=runner)
        people = client.list_contacts(mask="names", limit=-5)
        self.assertEqual(people[0]["resourceName"], "people/a")
        self.assertGreater(runner.params()["pageSize"], 0)


class TestPickContactSource(unittest.TestCase):
    """Tests for PersonBodyBuilder.pick_source."""

    def test_prefers_contact_source(self):
        """The CONTACT source is preferred over others."""
        person = {"metadata": {"sources": [
            {"type": "PROFILE", "id": "p1"},
            {"type": "CONTACT", "id": "c1"},
        ]}}
        self.assertEqual(
            gcontacts.PersonBodyBuilder.pick_source(person=person),
            {"type": "CONTACT", "id": "c1"},
        )

    def test_falls_back_to_first(self):
        """Without a CONTACT source, the first source is returned."""
        person = {"metadata": {"sources": [{"type": "PROFILE", "id": "p1"}]}}
        self.assertEqual(
            gcontacts.PersonBodyBuilder.pick_source(person=person),
            {"type": "PROFILE", "id": "p1"},
        )

    def test_missing_returns_none(self):
        """A person with no sources returns None."""
        self.assertIsNone(gcontacts.PersonBodyBuilder.pick_source(person={}))


if __name__ == "__main__":
    unittest.main()
