#!/usr/bin/env python3
"""Tests for gtasks module."""
# noqa: E402


import io
import json
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

import gtasks

# These tests intentionally exercise internal rendering and gws helpers.
# noqa: SLF001, E402


class FakeRunner:
    """Return queued gws responses and record every invocation."""

    def __init__(self, *, responses):
        self._responses = list(responses)
        self.calls = []

    def run(self, *, args):
        """Record the call and return or raise the next queued response."""
        self.calls.append(args)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class ApplicationHarness:
    """Run the gtasks Application with captured streams and a fake runner."""

    def __init__(self, *, responses):
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        self.runner = FakeRunner(responses=responses)
        self.console = gtasks.Console(
            stdout=self.stdout, stderr=self.stderr
        )

    def run(self, argv):
        """Run the application and return (rc, stdout, stderr)."""
        app = gtasks.Application(
            argv=argv, runner=self.runner, console=self.console
        )
        return app.run(), self.stdout.getvalue(), self.stderr.getvalue()

    def params_at(self, index):
        """Return the decoded --params value of the indexed runner call."""
        args = self.runner.calls[index]
        return json.loads(args[args.index("--params") + 1])

    def body_at(self, index):
        """Return the decoded --json value of the indexed runner call."""
        args = self.runner.calls[index]
        return json.loads(args[args.index("--json") + 1])


#--------------------------------------------------
# Date helpers
#--------------------------------------------------


class TestParseDate(unittest.TestCase):
    """Tests for TaskDateSelection.parse_date."""

    def test_valid_date_passes_through(self):
        """A valid YYYY-MM-DD string is returned unchanged."""
        self.assertEqual(
            gtasks.TaskDateSelection.parse_date(value="2026-08-15"),
            "2026-08-15",
        )

    def test_invalid_date_exits_with_code_2(self):
        """Bad input exits with code 2."""
        err = io.StringIO()
        with self.assertRaises(SystemExit) as ctx, redirect_stderr(err):
            gtasks.TaskDateSelection.parse_date(value="2026-13-45")
        self.assertEqual(ctx.exception.code, 2)


class TestDateWindow(unittest.TestCase):
    """Tests for TaskDateSelection.window."""

    def test_returns_start_and_end_of_day_bounds(self):
        """min is midnight at start and max is 23:59:59 on end."""
        self.assertEqual(
            gtasks.TaskDateSelection.window(
                start="2026-08-15", end="2026-08-15"
            ),
            ("2026-08-15T00:00:00Z", "2026-08-15T23:59:59Z"),
        )


class TestFmtRangeTitle(unittest.TestCase):
    """Tests for TaskDateSelection.range_title."""

    def test_single_day(self):
        """A one-day range uses the single date."""
        self.assertEqual(
            gtasks.TaskDateSelection.range_title(
                start="2026-08-15", end="2026-08-15"
            ),
            "2026-08-15",
        )

    def test_multi_day(self):
        """A multi-day range uses an arrow."""
        self.assertEqual(
            gtasks.TaskDateSelection.range_title(
                start="2026-08-15", end="2026-08-16"
            ),
            "2026-08-15 \u2192 2026-08-16",
        )


#--------------------------------------------------
# Formatting helpers
#--------------------------------------------------


class TestFmtDueDate(unittest.TestCase):
    """Tests for TaskFormatter.due_date."""

    def test_extracts_date(self):
        """The first ten characters are kept."""
        self.assertEqual(
            gtasks.TaskFormatter.due_date("2026-07-17T00:00:00.000Z"),
            "2026-07-17",
        )

    def test_missing_uses_dash(self):
        """An empty value renders as an em dash."""
        self.assertEqual(gtasks.TaskFormatter.due_date(""), "\u2014")


class TestKebab(unittest.TestCase):
    """Tests for TaskFormatter.kebab."""

    def test_lowercases_and_hyphenates(self):
        """Spaces become hyphens and everything is lowercased."""
        self.assertEqual(
            gtasks.TaskFormatter.kebab("Liste de Matthias"),
            "liste-de-matthias",
        )

    def test_strips_surrounding_hyphens(self):
        """Leading and trailing hyphens are removed."""
        self.assertEqual(gtasks.TaskFormatter.kebab("  --Work--  "), "work")

    def test_empty(self):
        """Empty input yields an empty string."""
        self.assertEqual(gtasks.TaskFormatter.kebab(""), "")
        self.assertEqual(gtasks.TaskFormatter.kebab(None), "")


class TestHumanStatus(unittest.TestCase):
    """Tests for TaskFormatter.human_status."""

    def test_maps_needs_action(self):
        """needsAction becomes 'needs action'."""
        self.assertEqual(
            gtasks.TaskFormatter.human_status("needsAction"), "needs action"
        )

    def test_maps_completed(self):
        """completed stays 'completed'."""
        self.assertEqual(
            gtasks.TaskFormatter.human_status("completed"), "completed"
        )

    def test_unknown_passthrough(self):
        """Unknown statuses pass through unchanged."""
        self.assertEqual(
            gtasks.TaskFormatter.human_status("weird"), "weird"
        )

    def test_missing_uses_dash(self):
        """An empty status renders as an em dash."""
        self.assertEqual(
            gtasks.TaskFormatter.human_status(""), "\u2014"
        )


class TestFmtUpdated(unittest.TestCase):
    """Tests for TaskFormatter.updated."""

    def test_formats_timestamp(self):
        """A full timestamp becomes date and time."""
        self.assertEqual(
            gtasks.TaskFormatter.updated("2026-07-22T21:36:09.854Z"),
            "2026-07-22 21:36",
        )

    def test_missing_uses_dash(self):
        """An empty value renders as an em dash."""
        self.assertEqual(gtasks.TaskFormatter.updated(""), "\u2014")


class TestCollectLinks(unittest.TestCase):
    """Tests for TaskFormatter.links."""

    def test_prefixes_matching_description(self):
        """A description differing from the URL becomes a prefix."""
        task = {"links": [{"link": "https://a.com", "description": "Report"}]}
        self.assertEqual(
            gtasks.TaskFormatter.links(task), ["Report: https://a.com"]
        )

    def test_no_description_or_same_as_url(self):
        """Links without a distinct description render bare."""
        task = {
            "links": [
                {"link": "https://a.com", "description": "https://a.com"},
                {"link": "https://b.com"},
            ]
        }
        self.assertEqual(
            gtasks.TaskFormatter.links(task),
            ["https://a.com", "https://b.com"],
        )

    def test_missing_links(self):
        """No links yields an empty list."""
        self.assertEqual(gtasks.TaskFormatter.links({}), [])


#--------------------------------------------------
# Rendering
#--------------------------------------------------


class TestRenderTaskBlock(unittest.TestCase):
    """Tests for MarkdownTaskRenderer.render_task."""

    def test_renders_full_block(self):
        """All present fields are rendered in order."""
        task = {
            "kind": "tasks#task",
            "title": "Write report",
            "tasklistTitle": "Liste de Matthias",
            "status": "needsAction",
            "due": "2026-07-17T00:00:00.000Z",
            "updated": "2026-07-22T21:36:09.854Z",
            "completed": "2026-07-23T10:15:00.000Z",
            "links": [{"link": "https://a.com", "description": "Report"}],
            "notes": "Do it soon",
        }
        out = gtasks.MarkdownTaskRenderer().render_task(task=task)
        self.assertIn(
            "---\n- due: 2026-07-17\n- updated: 2026-07-22 21:36\n"
            "- completed: 2026-07-23 10:15\n---",
            out,
        )
        self.assertIn("## Write report", out)
        self.assertIn("#liste-de-matthias", out)
        self.assertIn("#liste-de-matthias #bookmark #task #todo", out)
        self.assertIn("- Report: https://a.com", out)
        self.assertIn("- completed: 2026-07-23 10:15", out)
        self.assertIn("Do it soon", out)

    def test_omits_missing_sections(self):
        """A sparse task omits empty sections."""
        out = gtasks.MarkdownTaskRenderer().render_task(
            task={"title": "Bare"}
        )
        self.assertIn("## Bare", out)
        self.assertIn("- updated: —", out)
        self.assertIn("#todo", out)
        self.assertNotIn("- due:", out)
        self.assertNotIn("- completed:", out)

    def test_default_title(self):
        """Missing titles use a placeholder."""
        out = gtasks.MarkdownTaskRenderer().render_task(task={})
        self.assertIn("## (no title)", out)

    def test_no_notes_does_not_add_empty_lines(self):
        """A task without notes ends after its tags when it has no links."""
        out = gtasks.MarkdownTaskRenderer().render_task(
            task={"title": "Bare", "notes": None}
        )
        self.assertEqual(
            out, "---\n- updated: —\n---\n\n## Bare\n\n#todo\n"
        )


class TestRenderMarkdown(unittest.TestCase):
    """Tests for MarkdownTaskRenderer.render."""

    def test_empty_placeholder(self):
        """An empty task list renders the no-tasks placeholder."""
        out = gtasks.MarkdownTaskRenderer().render(
            tasks=[], section_title="All tasks"
        )
        self.assertEqual(out, "# All tasks\n\n_No tasks._\n")

    def test_multiple_tasks_rendered_as_blocks(self):
        """Task blocks use front matter and no outer section heading."""
        tasks = [{"title": "A"}, {"title": "B"}]
        out = gtasks.MarkdownTaskRenderer().render(
            tasks=tasks, section_title="All tasks"
        )
        self.assertNotIn("# All tasks", out)
        self.assertIn("## A", out)
        self.assertIn("## B", out)
        self.assertEqual(out.count("---"), 4)


#--------------------------------------------------
# Resolution helpers
#--------------------------------------------------


class TestResolveTasklistId(unittest.TestCase):
    """Tests for TaskListCatalog.resolve_id."""

    def setUp(self):
        self.lists = [
            {"id": "A", "title": "Work"},
            {"id": "B", "title": "Personal"},
        ]

    def test_case_insensitive_exact_match(self):
        """A case-insensitive title match resolves to the id."""
        self.assertEqual(
            gtasks.TaskListCatalog.resolve_id(
                query="work", tasklists=self.lists
            ),
            "A",
        )
        self.assertEqual(
            gtasks.TaskListCatalog.resolve_id(
                query="  WORK  ", tasklists=self.lists
            ),
            "A",
        )

    def test_no_match_passthrough(self):
        """Unmatched queries are returned unchanged."""
        self.assertEqual(
            gtasks.TaskListCatalog.resolve_id(
                query="xyz", tasklists=self.lists
            ),
            "xyz",
        )

    def test_empty_query_passthrough(self):
        """An empty query is returned unchanged."""
        self.assertEqual(
            gtasks.TaskListCatalog.resolve_id(
                query="", tasklists=self.lists
            ),
            "",
        )
        self.assertEqual(
            gtasks.TaskListCatalog.resolve_id(
                query=None, tasklists=self.lists
            ),
            None,
        )

    def test_ambiguous_raises(self):
        """Duplicate titles raise ValueError listing the candidates."""
        lists = [
            {"id": "A", "title": "Work"},
            {"id": "B", "title": "Work"},
        ]
        with self.assertRaises(ValueError) as ctx:
            gtasks.TaskListCatalog.resolve_id(
                query="Work", tasklists=lists
            )
        self.assertIn("ambiguous", str(ctx.exception))


class TestTasklistMeta(unittest.TestCase):
    """Tests for TaskListCatalog.meta_for."""

    def test_known_list(self):
        """A known id yields its title."""
        self.assertEqual(
            gtasks.TaskListCatalog.meta_for(
                tasklist_id="A",
                tasklists=[{"id": "A", "title": "Work"}],
            ),
            {"id": "A", "title": "Work"},
        )

    def test_unknown_list(self):
        """An unknown id falls back to the id as title."""
        self.assertEqual(
            gtasks.TaskListCatalog.meta_for(
                tasklist_id="X", tasklists=[]
            ),
            {"id": "X", "title": "X"},
        )

    def test_empty_title_falls_back(self):
        """A blank title falls back to the id."""
        self.assertEqual(
            gtasks.TaskListCatalog.meta_for(
                tasklist_id="A",
                tasklists=[{"id": "A", "title": ""}],
            ),
            {"id": "A", "title": "A"},
        )


class TestTaskSortKey(unittest.TestCase):
    """Tests for TaskFormatter.sort_key."""

    def test_due_tasks_first(self):
        """Tasks with a due date sort before those without."""
        with_due = gtasks.TaskFormatter.sort_key(
            {"due": "2026-08-01T00:00:00.000Z", "position": "a"}
        )
        without = gtasks.TaskFormatter.sort_key({"position": "a"})
        self.assertLess(with_due, without)

    def test_missing_due_uses_sentinel(self):
        """A missing due date maps to the sentinel value."""
        self.assertEqual(
            gtasks.TaskFormatter.sort_key({})[0], "9999-99-99"
        )

    def test_breaks_ties_by_position(self):
        """Same due dates fall back to the position string."""
        a = gtasks.TaskFormatter.sort_key(
            {"due": "2026-08-01T00:00:00.000Z", "position": "0001"}
        )
        b = gtasks.TaskFormatter.sort_key(
            {"due": "2026-08-01T00:00:00.000Z", "position": "0002"}
        )
        self.assertLess(a, b)


class TestFilterByDateKind(unittest.TestCase):
    """Tests for TaskDateSelection.filter_tasks."""

    def setUp(self):
        self.tasks = [
            {"id": "a", "status": "needsAction",
             "due": "2026-08-01T00:00:00.000Z"},
            {"id": "b", "status": "needsAction"},
            {"id": "c", "status": "completed",
             "due": "2026-08-01T00:00:00.000Z"},
            {"id": "d", "status": "completed"},
        ]

    def test_due_keeps_only_open_dated_tasks(self):
        """--due keeps needsAction tasks with a due date."""
        filtered = gtasks.TaskDateSelection.filter_tasks(
            tasks=self.tasks, date_filter="due"
        )
        self.assertEqual([task["id"] for task in filtered], ["a"])

    def test_completed_keeps_only_completed_tasks(self):
        """--completed keeps finished tasks regardless of due date."""
        filtered = gtasks.TaskDateSelection.filter_tasks(
            tasks=self.tasks, date_filter="completed"
        )
        self.assertEqual([task["id"] for task in filtered], ["c", "d"])

    def test_no_filter_passes_everything(self):
        """No selector leaves the list untouched."""
        filtered = gtasks.TaskDateSelection.filter_tasks(
            tasks=self.tasks, date_filter=None
        )
        self.assertEqual(
            [task["id"] for task in filtered], ["a", "b", "c", "d"]
        )


#--------------------------------------------------
# gws calls
#--------------------------------------------------


class TestGwsCalls(unittest.TestCase):
    """Tests for fetch/create helpers with a fake gws runner."""

    def test_fetch_tasklist_list(self):
        """Items with an id are returned."""
        runner = FakeRunner(responses=[
            '{"items": [{"id": "A"}, {"no": "x"}]}'
        ])
        catalog = gtasks.TaskListCatalog(runner=runner)
        self.assertEqual(catalog.list_tasklists(), [{"id": "A"}])

    def test_fetch_tasklist_list_non_dict(self):
        """A non-dict response yields an empty list."""
        runner = FakeRunner(responses=["[]"])
        catalog = gtasks.TaskListCatalog(runner=runner)
        self.assertEqual(catalog.list_tasklists(), [])

    def test_create_task(self):
        """The insert body carries the title and optional notes."""
        runner = FakeRunner(responses=['{"id": "1"}'])
        client = gtasks.TasksClient(runner=runner)
        self.assertEqual(
            client.create_task(
                tasklist_id="A", title="Task", notes="note"
            ),
            {"id": "1"},
        )
        args = runner.calls[0]
        self.assertEqual(
            json.loads(args[args.index("--params") + 1]),
            {"tasklist": "A"},
        )
        self.assertEqual(
            json.loads(args[args.index("--json") + 1]),
            {"title": "Task", "notes": "note"},
        )

    def test_create_task_without_notes(self):
        """The insert body omits notes when absent."""
        runner = FakeRunner(responses=["{}"])
        client = gtasks.TasksClient(runner=runner)
        client.create_task(tasklist_id="A", title="Task")
        args = runner.calls[0]
        self.assertEqual(
            json.loads(args[args.index("--json") + 1]),
            {"title": "Task"},
        )

    def test_create_task_non_dict_response(self):
        """A non-dict response is wrapped."""
        runner = FakeRunner(responses=["[1]"])
        client = gtasks.TasksClient(runner=runner)
        self.assertEqual(
            client.create_task(tasklist_id="A", title="Task"),
            {"response": [1]},
        )

    def test_fetch_tasks_for_list_includes_bounds(self):
        """The selected bound names are included only when provided."""
        runner = FakeRunner(responses=['{"items": [{"id": "t1"}]}'])
        client = gtasks.TasksClient(runner=runner)
        tasks = client.fetch_tasks(
            tasklist_id="A",
            time_min="2026-08-01T00:00:00Z",
            time_max="2026-08-02T00:00:00Z",
            min_key="dueMin",
            max_key="dueMax",
            show_completed=False,
            max_results=100,
        )
        self.assertEqual(tasks, [{"id": "t1"}])
        args = runner.calls[0]
        params = json.loads(args[args.index("--params") + 1])
        self.assertEqual(params["dueMin"], "2026-08-01T00:00:00Z")
        self.assertEqual(params["dueMax"], "2026-08-02T00:00:00Z")

    def test_fetch_tasks_for_list_omits_bounds(self):
        """None bounds are not present in the params."""
        runner = FakeRunner(responses=['{"items": []}'])
        client = gtasks.TasksClient(runner=runner)
        client.fetch_tasks(
            tasklist_id="A",
            time_min=None,
            time_max=None,
            min_key="dueMin",
            max_key="dueMax",
            show_completed=True,
            max_results=100,
        )
        args = runner.calls[0]
        params = json.loads(args[args.index("--params") + 1])
        self.assertNotIn("dueMin", params)
        self.assertNotIn("dueMax", params)


class TestFetchAllTasklistsTasks(unittest.TestCase):
    """Tests for AllTasklistsFetcher.fetch."""

    @staticmethod
    def build_fetcher(*, tasklists, client_responses, stderr):
        """Return a fetcher wired to fake task list and task responses."""
        catalog = gtasks.TaskListCatalog(
            runner=FakeRunner(responses=[
                json.dumps({"items": tasklists})
            ])
        )
        client = gtasks.TasksClient(
            runner=FakeRunner(responses=client_responses)
        )
        return gtasks.AllTasklistsFetcher(
            catalog=catalog,
            client=client,
            console=gtasks.Console(stderr=stderr),
        )

    def test_merges_and_tags(self):
        """Tasks from every list are merged, tagged, and sorted by due date."""
        fetcher = self.build_fetcher(
            tasklists=[
                {"id": "A", "title": "Work"},
                {"id": "B", "title": "Personal"},
            ],
            client_responses=[
                json.dumps({"items": [
                    {"id": "t1", "title": "No due", "position": "0"}
                ]}),
                json.dumps({"items": [
                    {"id": "t2", "title": "Due",
                     "due": "2026-08-01T00:00:00.000Z", "position": "0"}
                ]}),
            ],
            stderr=io.StringIO(),
        )
        merged = fetcher.fetch(
            time_min=None,
            time_max=None,
            min_key="dueMin",
            max_key="dueMax",
            show_completed=False,
            max_results=100,
        )
        self.assertEqual(merged["kind"], "tasks#tasks")
        self.assertEqual(
            [task["id"] for task in merged["items"]], ["t2", "t1"]
        )
        self.assertEqual(merged["items"][0]["tasklist"], "B")
        self.assertEqual(merged["items"][0]["tasklistTitle"], "Personal")

    def test_skips_failing_list_with_warning(self):
        """A failing list is skipped and always reported with a warning."""
        err = io.StringIO()
        fetcher = self.build_fetcher(
            tasklists=[
                {"id": "A", "title": "Work"},
                {"id": "B", "title": "Bad"},
            ],
            client_responses=[
                json.dumps({"items": [{"id": "t1"}]}),
                RuntimeError("boom"),
            ],
            stderr=err,
        )
        merged = fetcher.fetch(
            time_min=None,
            time_max=None,
            min_key="dueMin",
            max_key="dueMax",
            show_completed=False,
            max_results=100,
        )
        self.assertIn("skipping tasklist B", err.getvalue())
        self.assertEqual(
            [task["id"] for task in merged["items"]], ["t1"]
        )


#--------------------------------------------------
# main / CLI
#--------------------------------------------------


class TestMain(unittest.TestCase):
    """Tests for the Application entry point with a fake gws runner."""

    @staticmethod
    def run_main(argv, responses):
        """Run the application and return (rc, stdout, stderr, harness)."""
        harness = ApplicationHarness(responses=responses)
        rc, out, err = harness.run(argv)
        return rc, out, err, harness

    def test_create_task(self):
        """--create resolves the list and inserts the task."""
        responses = [
            '{"items": [{"id": "A", "title": "Work"}]}',
            '{"id": "1", "title": "Task"}',
        ]
        rc, out, _, _ = self.run_main(
            ["--create", "--list", "Work", "--title", "Task",
             "--notes", "note"],
            responses,
        )
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["id"], "1")
        self.assertEqual(data["tasklist"], "A")
        self.assertEqual(data["tasklistTitle"], "Work")

    def test_create_requires_title(self):
        """--create without --title exits with argparse error code 2."""
        harness = ApplicationHarness(responses=[])
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                harness.run(["--create", "--list", "Work"])
        self.assertEqual(ctx.exception.code, 2)

    def test_create_quiet_does_not_hide_error(self):
        """--quiet still reports a create error and exits 1."""
        rc, out, err, _ = self.run_main(
            ["--create", "--list", "Work", "--title", "Task", "--quiet"],
            [RuntimeError("boom")],
        )
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("boom", err)

    def test_create_error_returns_1(self):
        """A create error exits 1 with an error on stderr."""
        rc, _, err, _ = self.run_main(
            ["--create", "--list", "Work", "--title", "Task"],
            [RuntimeError("boom")],
        )
        self.assertEqual(rc, 1)
        self.assertIn("boom", err)

    def test_single_list_json(self):
        """A single list emits annotated JSON with due bounds."""
        responses = [
            '{"items": [{"id": "A", "title": "Work"}]}',
            '{"items": []}',
        ]
        rc, out, _, harness = self.run_main(
            ["--list", "Work", "--start", "2026-08-01",
             "--end", "2026-08-01"],
            responses,
        )
        self.assertEqual(rc, 0)
        params = harness.params_at(1)
        self.assertEqual(params["tasklist"], "A")
        self.assertEqual(params["dueMin"], "2026-08-01T00:00:00Z")
        self.assertEqual(params["dueMax"], "2026-08-01T23:59:59Z")
        data = json.loads(out)
        self.assertEqual(data["_tasklist"], {"id": "A", "title": "Work"})

    def test_single_list_no_dates(self):
        """Without dates, no due bounds are sent."""
        responses = [
            '{"items": [{"id": "A", "title": "Work"}]}',
            '{"items": []}',
        ]
        rc, _, _, harness = self.run_main(["--list", "Work"], responses)
        self.assertEqual(rc, 0)
        params = harness.params_at(1)
        self.assertNotIn("dueMin", params)
        self.assertNotIn("dueMax", params)

    def test_single_list_md(self):
        """--md renders tasks with the injected tasklist title."""
        responses = [
            '{"items": [{"id": "A", "title": "Work"}]}',
            '{"items": [{"id": "t1", "title": "Do thing", '
            '"tasklistTitle": "ignored", "status": "needsAction", '
            '"due": "2026-08-01T00:00:00.000Z"}]}',
        ]
        rc, out, _, _ = self.run_main(
            ["--list", "Work", "--md", "--start", "2026-08-01",
             "--end", "2026-08-01"],
            responses,
        )
        self.assertEqual(rc, 0)
        self.assertNotIn("# Tasks due in 2026-08-01", out)
        self.assertIn("## Do thing", out)

    def test_created_selector_rejected(self):
        """--created is no longer a supported option."""
        harness = ApplicationHarness(responses=[])
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                harness.run(["--list", "Work", "--created"])
        self.assertEqual(ctx.exception.code, 2)

    def test_completed_selector_uses_completed_bounds_and_includes_completed(
        self,
    ):
        """--completed selects completion bounds and enables completed tasks."""
        responses = [
            '{"items": [{"id": "A", "title": "Work"}]}',
            '{"items": []}',
        ]
        rc, _, _, harness = self.run_main(
            ["--list", "Work", "--completed",
             "--start", "2026-08-01", "--end", "2026-08-01"],
            responses,
        )
        self.assertEqual(rc, 0)
        params = harness.params_at(1)
        self.assertTrue(params["showCompleted"])
        self.assertTrue(params["showHidden"])
        self.assertEqual(
            params["completedMin"], "2026-08-01T00:00:00Z"
        )
        self.assertEqual(
            params["completedMax"], "2026-08-01T23:59:59Z"
        )

    def test_selector_without_dates_fetches_unbounded_results(self):
        """A selector without dates omits timestamp bounds."""
        responses = [
            '{"items": [{"id": "A", "title": "Work"}]}',
            '{"items": []}',
        ]
        rc, _, _, harness = self.run_main(
            ["--list", "Work", "--completed"], responses
        )
        self.assertEqual(rc, 0)
        params = harness.params_at(1)
        self.assertTrue(params["showCompleted"])
        self.assertTrue(params["showHidden"])
        self.assertNotIn("completedMin", params)
        self.assertNotIn("completedMax", params)

    def test_due_without_dates_filters_to_open_dated_tasks(self):
        """--due without dates returns only open tasks with a due date."""
        responses = [
            '{"items": [{"id": "A", "title": "Work"}]}',
            '{"items": [{"id": "t1", "status": "needsAction", '
            '"due": "2026-08-01T00:00:00.000Z"}, '
            '{"id": "t2", "status": "needsAction"}, '
            '{"id": "t3", "status": "completed", '
            '"due": "2026-08-01T00:00:00.000Z"}]}',
        ]
        rc, out, _, harness = self.run_main(
            ["--list", "Work", "--due"], responses
        )
        self.assertEqual(rc, 0)
        params = harness.params_at(1)
        self.assertNotIn("dueMin", params)
        self.assertNotIn("dueMax", params)
        self.assertFalse(params["showCompleted"])
        self.assertFalse(params["showHidden"])
        data = json.loads(out)
        self.assertEqual(
            [task["id"] for task in data["items"]], ["t1"]
        )

    def test_completed_without_dates_filters_to_completed(self):
        """--completed without dates returns only completed tasks."""
        responses = [
            '{"items": [{"id": "A", "title": "Work"}]}',
            '{"items": [{"id": "t1", "status": "needsAction"}, '
            '{"id": "t2", "status": "completed"}]}',
        ]
        rc, out, _, _ = self.run_main(
            ["--list", "Work", "--completed"], responses
        )
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(
            [task["id"] for task in data["items"]], ["t2"]
        )

    def test_show_completed_requests_hidden_tasks(self):
        """--show-completed sends showHidden so first-party-completed tasks
        (hidden: true, e.g. from the web UI or mobile apps) are returned."""
        responses = [
            '{"items": [{"id": "A", "title": "Work"}]}',
            '{"items": [{"id": "t1", "title": "Foobar", '
            '"status": "completed", "hidden": true, '
            '"completed": "2026-08-14T18:22:51.819Z"}]}',
        ]
        rc, out, _, harness = self.run_main(
            ["--list", "Work", "--show-completed"], responses
        )
        self.assertEqual(rc, 0)
        params = harness.params_at(1)
        self.assertTrue(params["showCompleted"])
        self.assertTrue(params["showHidden"])
        data = json.loads(out)
        self.assertEqual(
            [task["id"] for task in data["items"]], ["t1"]
        )

    def test_show_completed_with_dates_uses_completion_bounds(self):
        """Dates with --show-completed select completed tasks by completion time."""
        responses = [
            '{"items": [{"id": "A", "title": "Work"}]}',
            '{"items": [{"id": "t1", "status": "completed", '
            '"hidden": true}, '
            '{"id": "t2", "status": "needsAction"}]}',
        ]
        rc, out, _, harness = self.run_main(
            ["--list", "Work", "--show-completed",
             "--start", "2026-08-14", "--end", "2026-08-14"],
            responses,
        )
        self.assertEqual(rc, 0)
        params = harness.params_at(1)
        self.assertTrue(params["showCompleted"])
        self.assertTrue(params["showHidden"])
        self.assertEqual(
            params["completedMin"], "2026-08-14T00:00:00Z"
        )
        self.assertEqual(
            params["completedMax"], "2026-08-14T23:59:59Z"
        )
        data = json.loads(out)
        self.assertEqual(
            [task["id"] for task in data["items"]], ["t1"]
        )

    def test_due_filters_in_md_output(self):
        """--due in markdown mode drops completed and undated tasks."""
        responses = [
            '{"items": [{"id": "A", "title": "Work"}]}',
            '{"items": [{"id": "t1", "title": "Open", '
            '"status": "needsAction", '
            '"due": "2026-08-01T00:00:00.000Z"}, '
            '{"id": "t2", "title": "Done", "status": "completed", '
            '"due": "2026-08-01T00:00:00.000Z"}, '
            '{"id": "t3", "title": "No date", '
            '"status": "needsAction"}]}',
        ]
        rc, out, _, _ = self.run_main(
            ["--list", "Work", "--due", "--md"], responses
        )
        self.assertEqual(rc, 0)
        self.assertIn("## Open", out)
        self.assertNotIn("## Done", out)
        self.assertNotIn("## No date", out)
        self.assertNotIn("# Tasks due", out)

    def test_all_lists_merge(self):
        """Without --list, all lists are fanned out and merged."""
        responses = [
            '{"items": [{"id": "A", "title": "Work"}, '
            '{"id": "B", "title": "Personal"}]}',
            '{"items": [{"id": "t1", "title": "Due early", '
            '"due": "2026-08-01T00:00:00.000Z", "position": "0"}]}',
            '{"items": [{"id": "t2", "title": "Due later", '
            '"due": "2026-08-02T00:00:00.000Z", "position": "0"}]}',
        ]
        rc, out, _, _ = self.run_main(
            ["--start", "2026-08-01", "--end", "2026-08-01"], responses
        )
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["kind"], "tasks#tasks")
        self.assertEqual(
            [task["id"] for task in data["items"]], ["t1", "t2"]
        )

    def test_all_lists_quiet_does_not_hide_error(self):
        """--quiet still reports a fan-out failure and exits 1."""
        rc, out, err, _ = self.run_main(
            ["--quiet", "--start", "2026-08-01", "--end", "2026-08-01"],
            [RuntimeError("boom")],
        )
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertIn("boom", err)

    def test_all_lists_error_returns_1(self):
        """A fan-out failure exits 1 with an error."""
        rc, _, err, _ = self.run_main(
            ["--start", "2026-08-01", "--end", "2026-08-01"],
            [RuntimeError("boom")],
        )
        self.assertEqual(rc, 1)
        self.assertIn("boom", err)

    def test_ambiguous_tasklist_returns_1(self):
        """An ambiguous title returns 1 with an error message."""
        responses = [
            '{"items": [{"id": "A", "title": "Work"}, '
            '{"id": "B", "title": "Work"}]}',
        ]
        rc, _, err, _ = self.run_main(["--list", "Work"], responses)
        self.assertEqual(rc, 1)
        self.assertIn("ambiguous", err)


if __name__ == "__main__":
    unittest.main()
