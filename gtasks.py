#!/usr/bin/env python3
"""List or create Google Tasks through the gws command.

Broad catches at the CLI boundaries intentionally preserve --quiet and
partial-result behavior.
"""

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

#--------------------------------------------------
# Console: stream output and diagnostics
#--------------------------------------------------


class Console:
    """Write results to stdout and warnings or errors to stderr."""

    def __init__(self, *, stdout=None, stderr=None):
        self._stdout = stdout if stdout is not None else sys.stdout
        self._stderr = stderr if stderr is not None else sys.stderr

    def write(self, message):
        """Write a result payload verbatim to standard output."""
        self._stdout.write(message)

    def warning(self, message):
        """Write a non-fatal warning to standard error."""
        print(f"WARN: {message}", file=self._stderr)

    def error(self, message):
        """Write a fatal error to standard error."""
        print(f"ERROR: {message}", file=self._stderr)

#--------------------------------------------------
# GwsCommandRunner: invoke the gws CLI
#--------------------------------------------------


class GwsCommandRunner:
    """Run gws subcommands and translate their failures into runtime errors."""

    AUTH_HINT = "error: Please re-authenticate with `gws auth login` command"

    def run(self, *, args):
        """Run a gws subcommand, raise on failure, and return its stdout."""
        gws_bin = shutil.which("gws")
        if gws_bin is None:
            raise FileNotFoundError("`gws` is not on PATH")
        proc = subprocess.run(
            [gws_bin, *args, "--format", "json"],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            # gws always prints a cosmetic keyring line to stderr; keep the
            # real error only.
            err_lines = [
                line for line in (proc.stderr or "").splitlines()
                if line.strip() and not line.startswith("Using keyring backend")
            ]
            err = "\n".join(err_lines).strip() or f"gws exited {proc.returncode}"
            raise RuntimeError(err)
        return proc.stdout

    @classmethod
    def auth_hint(cls, *, exc):
        """Return the re-authentication hint when a token was rejected."""
        if "invalid_grant" in str(exc).lower():
            return f"\n{cls.AUTH_HINT}"
        return ""

#--------------------------------------------------
# TaskListCatalog: list task lists and resolve titles
#--------------------------------------------------


class TaskListCatalog:
    """Read the user's task lists and resolve task list titles to IDs."""

    def __init__(self, *, runner):
        self._runner = runner

    def list_tasklists(self):
        """Return the user's task lists that carry an ``id``."""
        raw = self._runner.run(args=["tasks", "tasklists", "list"])
        data = json.loads(raw)
        items = data.get("items", []) if isinstance(data, dict) else []
        return [tasklist for tasklist in items if tasklist.get("id")]

    @staticmethod
    def resolve_id(*, query, tasklists):
        """Resolve a task list title to its ID, passing unknown values through.

        Matching is case-insensitive after stripping whitespace. Multiple
        matches raise ``ValueError``; no match returns ``query`` unchanged so
        a raw task list ID still works.
        """
        normalized = (query or "").strip().lower()
        if not normalized:
            return query

        matches = [
            tasklist for tasklist in tasklists
            if (tasklist.get("title") or "").strip().lower() == normalized
        ]
        if len(matches) == 1:
            return matches[0]["id"]
        if len(matches) > 1:
            candidates = ", ".join(
                f'"{tasklist.get("title") or tasklist.get("id")}"'
                for tasklist in matches
            )
            raise ValueError(
                f"ambiguous tasklist title '{query}' — matches: {candidates}"
            )
        return query

    @staticmethod
    def meta_for(*, tasklist_id, tasklists):
        """Return ``{id, title}``, falling back to the ID as title."""
        for tasklist in tasklists:
            if tasklist.get("id") == tasklist_id:
                return {
                    "id": tasklist["id"],
                    "title": tasklist.get("title") or tasklist["id"],
                }
        return {"id": tasklist_id, "title": tasklist_id}

#--------------------------------------------------
# TasksClient: create and fetch tasks through gws
#--------------------------------------------------


class TasksClient:
    """Create tasks and fetch task pages through the gws command."""

    def __init__(self, *, runner):
        self._runner = runner

    def create_task(self, *, tasklist_id, title, notes=None):
        """Create one task in a task list and return the gws JSON response."""
        body = {"title": title}
        if notes:
            body["notes"] = notes
        raw = self._runner.run(args=[
            "tasks", "tasks", "insert",
            "--params", json.dumps({"tasklist": tasklist_id}),
            "--json", json.dumps(body),
        ])
        data = json.loads(raw)
        return data if isinstance(data, dict) else {"response": data}

    def fetch_tasks(
        self, *, tasklist_id, time_min=None, time_max=None,
        min_key="dueMin", max_key="dueMax", show_completed=False,
        max_results=100,
    ):
        """Return the ``items`` array of one task list's tasks.list response.

        ``min_key`` and ``max_key`` select the timestamp pair used by the
        window. A ``None`` bound is omitted from the query.
        """
        params = {
            "tasklist": tasklist_id,
            "showCompleted": show_completed,
            "showHidden": show_completed,
            "maxResults": max_results,
        }
        if time_min is not None:
            params[min_key] = time_min
        if time_max is not None:
            params[max_key] = time_max
        raw = self._runner.run(
            args=["tasks", "tasks", "list", "--params", json.dumps(params)]
        )
        data = json.loads(raw)
        if not isinstance(data, dict):
            return []
        return data.get("items") or []

#--------------------------------------------------
# AllTasklistsFetcher: fan out to every task list
#--------------------------------------------------


class AllTasklistsFetcher:
    """Query every task list, tag each task, and merge the results."""

    RESULT_KIND = "tasks#tasks"

    def __init__(self, *, catalog, client, console):
        self._catalog = catalog
        self._client = client
        self._console = console

    def fetch(
        self, *, time_min, time_max, min_key, max_key,
        show_completed, max_results,
    ):
        """Fan out to every task list and return one merged tasks document.

        A list that cannot be queried is skipped with a warning so the
        remaining lists still produce a result.
        """
        tasklists = self._catalog.list_tasklists()

        all_items = []
        for tasklist in tasklists:
            tasklist_id = tasklist["id"]
            tasklist_title = tasklist.get("title", tasklist_id)
            try:
                tasks = self._client.fetch_tasks(
                    tasklist_id=tasklist_id,
                    time_min=time_min,
                    time_max=time_max,
                    min_key=min_key,
                    max_key=max_key,
                    show_completed=show_completed,
                    max_results=max_results,
                )
            except Exception as exc:
                hint = GwsCommandRunner.auth_hint(exc=exc)
                self._console.warning(
                    f"skipping tasklist {tasklist_id} ({tasklist_title}): "
                    f"{exc}{hint}"
                )
                continue
            for task in tasks:
                task["tasklist"] = tasklist_id
                task["tasklistTitle"] = tasklist_title
            all_items.extend(tasks)

        all_items.sort(key=TaskFormatter.sort_key)
        return {"kind": AllTasklistsFetcher.RESULT_KIND, "items": all_items}

#--------------------------------------------------
# TaskDateSelection: resolve date options and filter tasks
#--------------------------------------------------


class TaskDateSelection:
    """Resolve CLI date options into API bounds, filter semantics, and heading."""

    FILTER_PARAMS = {
        "due": ("dueMin", "dueMax"),
        "completed": ("completedMin", "completedMax"),
    }
    ALL_TASKS_TITLE = "All tasks"

    def __init__(
        self, *, date_filter, time_min, time_max, min_key, max_key,
        show_completed, title, heading,
    ):
        self.date_filter = date_filter
        self.time_min = time_min
        self.time_max = time_max
        self.min_key = min_key
        self.max_key = max_key
        self.show_completed = show_completed
        self.title = title
        self.heading = heading

    @classmethod
    def resolve(
        cls, *, date_filter, start, end, show_completed, today, console=None,
    ):
        """Build the selection for the parsed date options.

        No date arguments at all means an unfiltered query; otherwise the
        selector decides whether due or completion timestamps bound the
        request.
        """
        if date_filter:
            selector = date_filter
        elif start is not None or end is not None:
            selector = "completed" if show_completed else "due"
        else:
            selector = None

        min_key, max_key = cls.FILTER_PARAMS[selector or "due"]
        if start is not None or end is not None:
            start_date = (
                cls.parse_date(value=start, console=console) if start else today
            )
            end_date = (
                cls.parse_date(value=end, console=console) if end else today
            )
            time_min, time_max = cls.window(start=start_date, end=end_date)
            title = cls.range_title(start=start_date, end=end_date)
        else:
            time_min = time_max = None
            title = cls.ALL_TASKS_TITLE

        # A completion-time filter only makes sense for completed tasks; the
        # API returns completed fields only when showCompleted is enabled.
        # --due must keep completed tasks out, so it forces showCompleted off.
        if selector == "completed":
            include_completed = True
        elif selector == "due":
            include_completed = False
        else:
            include_completed = show_completed

        if selector:
            heading = (
                f"Tasks {selector}"
                if title == cls.ALL_TASKS_TITLE
                else f"Tasks {selector} in {title}"
            )
        else:
            heading = title

        return cls(
            date_filter=selector,
            time_min=time_min,
            time_max=time_max,
            min_key=min_key,
            max_key=max_key,
            show_completed=include_completed,
            title=title,
            heading=heading,
        )

    @staticmethod
    def parse_date(*, value, console=None):
        """Validate a ``YYYY-MM-DD`` string and return it unchanged.

        Bad input prints an error to stderr and exits with code 2.
        """
        reporter = console if console is not None else Console()
        try:
            return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
        except ValueError:
            reporter.error(
                f"invalid date '{value}', expected YYYY-MM-DD"
            )
            sys.exit(2)

    @staticmethod
    def window(*, start, end):
        """Return ``(min, max)`` RFC-3339 UTC timestamps for an inclusive range."""
        return (
            f"{start}T00:00:00Z",
            f"{end}T23:59:59Z",
        )

    @staticmethod
    def range_title(*, start, end):
        """Return the display title for a date range."""
        return start if start == end else f"{start} → {end}"

    @staticmethod
    def filter_tasks(*, tasks, date_filter):
        """Keep tasks matching the active selector's due/completed semantics.

        ``due`` keeps not-yet-completed tasks with a due date; ``completed``
        keeps finished tasks only. With no selector every task passes.
        """
        if date_filter == "due":
            return [
                task for task in tasks
                if task.get("due") and task.get("status") != "completed"
            ]
        if date_filter == "completed":
            return [task for task in tasks if task.get("status") == "completed"]
        return tasks

#--------------------------------------------------
# TaskFormatter: format fields and sort tasks
#--------------------------------------------------


class TaskFormatter:
    """Format task fields and provide the merged sort key."""

    EMPTY_VALUE = "—"
    WITHOUT_DUE_SENTINEL = "9999-99-99"
    DUE_DATE_LENGTH = 10
    UPDATED_LENGTH = 16
    STATUS_LABELS = {
        "needsAction": "needs action",
        "completed": "completed",
    }

    @staticmethod
    def due_date(due_iso):
        """``2026-07-17T00:00:00.000Z`` -> ``2026-07-17`` (or ``—``)."""
        if not due_iso:
            return TaskFormatter.EMPTY_VALUE
        return due_iso[:TaskFormatter.DUE_DATE_LENGTH]

    @staticmethod
    def kebab(value):
        """Lower-train-case: ``"Liste de Matthias"`` -> ``"liste-de-matthias"``."""
        normalized = (value or "").lower().strip()
        normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
        return normalized.strip("-")

    @classmethod
    def human_status(cls, status):
        """``"needsAction"`` -> ``"needs action"``."""
        if not status:
            return cls.EMPTY_VALUE
        return cls.STATUS_LABELS.get(status, status)

    @staticmethod
    def updated(value):
        """``2026-07-22T21:36:09.854Z`` -> ``2026-07-22 21:36`` (or ``—``)."""
        if not value:
            return TaskFormatter.EMPTY_VALUE
        return value[:TaskFormatter.UPDATED_LENGTH].replace("T", " ")

    @staticmethod
    def links(task):
        """Return link display strings for the ``- **links:**`` block."""
        items = []
        for link in task.get("links") or []:
            url = link.get("link")
            if not url:
                continue
            description = (link.get("description") or "").strip()
            if description and description != url:
                items.append(f"{description}: {url}")
            else:
                items.append(url)
        return items

    @staticmethod
    def sort_key(task):
        """Return ``(due_date_or_sentinel, position)`` for stable sorting.

        Tasks without a due date sort last; ties are broken by the API's
        ``position`` string (lexicographic display order).
        """
        due = task.get("due") or TaskFormatter.WITHOUT_DUE_SENTINEL
        return (due[:10], task.get("position") or "")

#--------------------------------------------------
# MarkdownTaskRenderer: render tasks as markdown
#--------------------------------------------------


class MarkdownTaskRenderer:
    """Render tasks as front-matter markdown blocks."""

    def render(self, *, tasks, section_title):
        """Render tasks as front-matter markdown blocks."""
        if not tasks:
            return f"# {section_title}\n\n_No tasks._\n"
        blocks = [self.render_task(task=task) for task in tasks]
        return "\n".join(blocks)

    def render_task(self, *, task):
        """Render one task using front matter and searchable markdown tags."""
        formatter = TaskFormatter
        due = formatter.due_date(task["due"]) if task.get("due") else None
        updated = formatter.updated(task.get("updated"))
        completed = (
            formatter.updated(task.get("completed"))
            if task.get("completed") else None
        )
        links_md = "\n".join(
            f"- {link}" for link in formatter.links(task)
        )
        title = task.get("title") or "(no title)"
        tasklist_title = (
            task.get("tasklistTitle") or task.get("tasklist") or ""
        )
        tags = [formatter.kebab(tasklist_title)] if tasklist_title else []
        if task.get("links"):
            tags.append("bookmark")
        if task.get("kind") == "tasks#task":
            tags.append("task")
        tags.append("done" if task.get("status") == "completed" else "todo")
        metadata = ""
        if due is not None:
            metadata += f"- due: {due}\n"
        metadata += f"- updated: {updated}\n"
        if completed is not None:
            metadata += f"- completed: {completed}\n"
        body = [f"## {title}", " ".join(f"#{tag}" for tag in tags if tag)]
        if links_md:
            body.append(links_md)
        notes = (task.get("notes") or "").strip()
        if notes:
            body.append(notes)
        body_md = "\n\n".join(body)
        return f"---\n{metadata}---\n\n{body_md}\n"

#--------------------------------------------------
# Completion: bash completion generation
#--------------------------------------------------


class Completion:
    """Build bash completion scripts from an argparse parser."""

    BOOLEAN_BODY = "            COMPREPLY=()\n"
    VERBOSE_BODY = '            COMPREPLY=( $(compgen -W "-v -vv -vvv" -- "${cur}") )\n'
    FILE_BODY = '            COMPREPLY=( $(compgen -f -- "${cur}") )\n'
    GLOB_BODY = '            COMPREPLY=( $(compgen -G "${cur}*") )\n'

    FILE_KEYS = ("output", "file", "path", "dest")
    GLOB_KEYS = ("include", "exclude", "glob", "pattern")

    @classmethod
    def _bodies(cls):
        """Return the completion body for each option category."""
        return {
            "boolean": cls.BOOLEAN_BODY,
            "verbose": cls.VERBOSE_BODY,
            "file": cls.FILE_BODY,
            "glob": cls.GLOB_BODY,
        }

    @staticmethod
    def _classify_parser_actions(arg_parser):
        """Walk the parser actions and return ``(all_opts, categories)``."""
        all_opts = set()
        categories = {"boolean": [], "verbose": [], "file": [], "glob": []}
        for action in arg_parser._actions:  # noqa: SLF001
            opts = action.option_strings
            if not opts:
                continue
            all_opts.update(opts)
            joined = " ".join(opts).lower()
            if action.nargs == 0 and action.const is True:
                categories["boolean"].extend(opts)
            if action.__class__.__name__ == "_CountAction":
                categories["verbose"].extend(opts)
            if any(key in joined for key in Completion.FILE_KEYS):
                categories["file"].extend(opts)
            if any(key in joined for key in Completion.GLOB_KEYS):
                categories["glob"].extend(opts)
        return all_opts, categories

    @classmethod
    def _render_case(cls, *, opt, kind):
        """Return the bash case branch for the given option kind."""
        return f"        {opt})\n{cls._bodies()[kind]}            return 0\n            ;;\n"

    @classmethod
    def _render_script(cls, *, all_opts, categories, name):
        """Build the final bash completion script string."""
        blocks = []
        for kind, opts in categories.items():
            for opt in sorted(set(opts)):
                blocks.append(cls._render_case(opt=opt, kind=kind))
        option_case = "".join(blocks)
        completion_name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
        sorted_opts = sorted(
            all_opts, key=lambda option: (not option.startswith("--"), option.lower())
        )
        opts_str = " ".join(sorted_opts)
        return f'''#!/bin/bash

_{completion_name}_completions()
{{
    local cur prev opts
    COMPREPLY=()
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"

    opts="{opts_str}"

    case "${{prev}}" in
{option_case}        *)
            COMPREPLY=( $(compgen -W "${{opts}}" -- "${{cur}}") )
            return 0
            ;;
    esac
}}

complete -f -F _{completion_name}_completions {shlex.quote(name)}
'''

    @classmethod
    def generate(cls, *, parser, name):
        """Return a bash completion script for ``parser``."""
        all_opts, categories = cls._classify_parser_actions(parser)
        return cls._render_script(
            all_opts=all_opts, categories=categories, name=name
        )

#--------------------------------------------------
# CliParser: build the command-line interface
#--------------------------------------------------


class CliParser:
    """Build the gtasks argument parser."""

    DESCRIPTION = "gws wrapper: list Google Tasks in a [start, end] range."
    DEFAULT_MAX_RESULTS = 100

    def build(self):
        """Build and return the argument parser."""
        parser = argparse.ArgumentParser(description=CliParser.DESCRIPTION)
        parser.add_argument(
            "--list", dest="tasklist", default=None,
            help="task list TITLE (case-insensitive exact match). Falls back to "
                 "treating the value as a raw tasklist ID if no title matches. "
                 "If omitted, query ALL task lists in the user's account.",
        )
        selector = parser.add_mutually_exclusive_group()
        selector.add_argument(
            "--due", dest="date_filter", action="store_const", const="due",
            help="only show not-yet-completed tasks that have a due date",
        )
        selector.add_argument(
            "--completed", dest="date_filter", action="store_const",
            const="completed", help="only show completed tasks",
        )
        parser.add_argument(
            "--start", default=None,
            help="inclusive start date YYYY-MM-DD (default: today)",
        )
        parser.add_argument(
            "--end", default=None,
            help="inclusive end date YYYY-MM-DD (default: today)",
        )
        parser.add_argument(
            "--create", action="store_true",
            help="create one task instead of listing tasks "
                 "(requires --list and --title)",
        )
        parser.add_argument("--title", default=None, help="task title for --create")
        parser.add_argument(
            "--notes", "--description", dest="notes", default=None,
            help="task notes for --create",
        )
        parser.add_argument(
            "--show-completed", action="store_true",
            help="include completed tasks (default: off)",
        )
        parser.add_argument(
            "--max-results", type=int, default=CliParser.DEFAULT_MAX_RESULTS,
            help="max tasks per page, per list (default: 100, the API max)",
        )
        parser.add_argument(
            "--md", action="store_true",
            help="render front-matter markdown instead of JSON",
        )
        parser.add_argument(
            "--quiet", action="store_true",
            help="suppress non-error output; runtime errors are still reported",
        )
        parser.add_argument("--verbose", "-v", action="count", default=0)
        parser.add_argument(
            "--completion", action="store_true",
            help="Print bash completion script to stdout and exit",
        )
        return parser

#--------------------------------------------------
# Application: orchestrate the CLI
#--------------------------------------------------


class Application:
    """Run the gtasks command and translate failures into exit codes."""

    EXIT_SUCCESS = 0
    EXIT_ERROR = 1

    def __init__(self, *, argv=None, runner=None, console=None):
        self._argv = list(sys.argv[1:] if argv is None else argv)
        self._console = console if console is not None else Console()
        self._runner = runner if runner is not None else GwsCommandRunner()
        self._catalog = TaskListCatalog(runner=self._runner)
        self._client = TasksClient(runner=self._runner)
        self._fetcher = AllTasklistsFetcher(
            catalog=self._catalog,
            client=self._client,
            console=self._console,
        )
        self._renderer = MarkdownTaskRenderer()

    def run(self):
        """Parse the command line, run the requested action, and return a code."""
        parser = CliParser().build()
        if "--completion" in self._argv:
            self._console.write(
                Completion.generate(parser=parser, name=self._command_name()) + "\n"
            )
            return Application.EXIT_SUCCESS

        options = parser.parse_args(self._argv)
        if options.create:
            return self._run_create(options=options, parser=parser)

        selection = TaskDateSelection.resolve(
            date_filter=options.date_filter,
            start=options.start,
            end=options.end,
            show_completed=options.show_completed,
            today=datetime.now().date().isoformat(),
            console=self._console,
        )
        if options.tasklist is not None:
            return self._run_single_list(options=options, selection=selection)
        return self._run_all_lists(options=options, selection=selection)

    @staticmethod
    def _command_name():
        """Return the installed command name derived from argv[0]."""
        return Path(sys.argv[0]).resolve().stem

    def _run_create(self, *, options, parser):
        """Create one task and print its annotated JSON response."""
        if not options.tasklist or not options.title or not options.title.strip():
            parser.error("--create requires --list and --title")
        try:
            tasklists = self._catalog.list_tasklists()
            tasklist_id = self._catalog.resolve_id(
                query=options.tasklist, tasklists=tasklists
            )
            task = self._client.create_task(
                tasklist_id=tasklist_id,
                title=options.title.strip(),
                notes=options.notes,
            )
        except Exception as exc:
            hint = GwsCommandRunner.auth_hint(exc=exc)
            self._console.error(f"gws task creation failed: {exc}{hint}")
            return Application.EXIT_ERROR
        task["tasklist"] = tasklist_id
        task["tasklistTitle"] = self._catalog.meta_for(
            tasklist_id=tasklist_id, tasklists=tasklists
        )["title"]
        self._console.write(json.dumps(task, ensure_ascii=False, indent=2))
        self._console.write("\n")
        return Application.EXIT_SUCCESS

    def _run_single_list(self, *, options, selection):
        """Query one task list and render the response."""
        try:
            tasklists = self._catalog.list_tasklists()
        except Exception as exc:
            hint = GwsCommandRunner.auth_hint(exc=exc)
            self._console.error(f"gws tasklists list failed: {exc}{hint}")
            return Application.EXIT_ERROR

        try:
            tasklist_id = self._catalog.resolve_id(
                query=options.tasklist, tasklists=tasklists
            )
        except ValueError as exc:
            self._console.error(str(exc))
            return Application.EXIT_ERROR

        meta = self._catalog.meta_for(
            tasklist_id=tasklist_id, tasklists=tasklists
        )
        params = {
            "tasklist": tasklist_id,
            "showCompleted": selection.show_completed,
            "showHidden": selection.show_completed,
            "maxResults": options.max_results,
        }
        if selection.time_min is not None:
            params[selection.min_key] = selection.time_min
        if selection.time_max is not None:
            params[selection.max_key] = selection.time_max

        try:
            raw = self._runner.run(
                args=["tasks", "tasks", "list", "--params", json.dumps(params)]
            )
        except Exception as exc:
            hint = GwsCommandRunner.auth_hint(exc=exc)
            self._console.error(f"gws tasks list failed: {exc}{hint}")
            return Application.EXIT_ERROR

        if options.md:
            return self._write_single_markdown(
                raw=raw, meta=meta, selection=selection
            )
        return self._write_single_json(raw=raw, meta=meta, selection=selection)

    def _write_single_markdown(self, *, raw, meta, selection):
        """Render one task list's response as markdown."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            self._console.write(raw)
            return Application.EXIT_SUCCESS
        tasks = data.get("items", []) if isinstance(data, dict) else data
        if not isinstance(tasks, list):
            tasks = []
        for task in tasks:
            task.setdefault("tasklist", meta["id"])
            task.setdefault("tasklistTitle", meta["title"])
        filtered = TaskDateSelection.filter_tasks(
            tasks=tasks, date_filter=selection.date_filter
        )
        self._console.write(
            self._renderer.render(
                tasks=filtered, section_title=selection.heading
            )
        )
        return Application.EXIT_SUCCESS

    def _write_single_json(self, *, raw, meta, selection):
        """Render one task list's response as annotated JSON."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            self._console.write(raw)
            return Application.EXIT_SUCCESS
        if not isinstance(data, dict):
            self._console.write(raw)
            return Application.EXIT_SUCCESS
        data["items"] = TaskDateSelection.filter_tasks(
            tasks=data.get("items") or [], date_filter=selection.date_filter
        )
        # Underscore prefix marks a wrapper-added field, not an API field.
        data["_tasklist"] = meta
        self._console.write(json.dumps(data, ensure_ascii=False, indent=2))
        self._console.write("\n")
        return Application.EXIT_SUCCESS

    def _run_all_lists(self, *, options, selection):
        """Fan out to every task list, merge the tasks, and render them."""
        try:
            merged = self._fetcher.fetch(
                time_min=selection.time_min,
                time_max=selection.time_max,
                min_key=selection.min_key,
                max_key=selection.max_key,
                show_completed=selection.show_completed,
                max_results=options.max_results,
            )
        except Exception as exc:
            hint = GwsCommandRunner.auth_hint(exc=exc)
            self._console.error(f"gws tasks fetch failed: {exc}{hint}")
            return Application.EXIT_ERROR

        merged["items"] = TaskDateSelection.filter_tasks(
            tasks=merged["items"], date_filter=selection.date_filter
        )
        if options.md:
            self._console.write(
                self._renderer.render(
                    tasks=merged["items"], section_title=selection.heading
                )
            )
        else:
            self._console.write(json.dumps(merged, ensure_ascii=False, indent=2))
            self._console.write("\n")
        return Application.EXIT_SUCCESS


if __name__ == "__main__":
    raise SystemExit(Application().run())
