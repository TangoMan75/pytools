#!/usr/bin/env python3
"""Read, create, update, and delete Google Contacts through the gws command."""

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

#--------------------------------------------------
# Console: stream output and diagnostics
#--------------------------------------------------


class Console:
    """Write results to stdout and diagnostics to stderr."""

    def __init__(self, *, stdout=None, stderr=None):
        self._stdout = stdout if stdout is not None else sys.stdout
        self._stderr = stderr if stderr is not None else sys.stderr

    def write(self, message):
        """Write a result payload verbatim to standard output."""
        self._stdout.write(message)

    def status(self, message):
        """Write a plain status message to standard error."""
        print(message, file=self._stderr)

    def error(self, message):
        """Write a fatal error to standard error."""
        print(f"ERROR: {message}", file=self._stderr)

#--------------------------------------------------
# GwsCommandRunner: invoke the gws CLI
#--------------------------------------------------


class GwsCommandRunner:
    """Run gws subcommands and translate their failures into runtime errors."""

    AUTH_HINT = "error: Please re-authenticate with `gws auth login` command"
    NOISE_PREFIX = "Using keyring backend"

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
            err_lines = [
                line for line in (proc.stderr or "").splitlines()
                if line.strip() and not line.startswith(GwsCommandRunner.NOISE_PREFIX)
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
# PersonBodyBuilder: build People API bodies
#--------------------------------------------------


class PersonBodyBuilder:
    """Build People API Person bodies and update masks from convenience flags."""

    CONTACT_SOURCE = "CONTACT"

    @staticmethod
    def resource_id(*, resource_name):
        """Extract the bare contact id from a ``people/...`` resource name."""
        return resource_name.split("/", 1)[-1]

    @classmethod
    def build_person(cls, *, name=None, email=None, phone=None, org=None,
                     address=None, note=None, url=None):
        """Build a People API Person body from convenience flags.

        Returns an empty dict when no convenience flag was supplied (the
        caller should then fall back to ``--json``).
        """
        person = {}
        if name:
            person["names"] = [{"displayName": name}]
        if email:
            person["emailAddresses"] = [{"value": email}]
        if phone:
            person["phoneNumbers"] = [{"value": phone}]
        if org:
            person["organizations"] = [{"name": org}]
        if address:
            person["addresses"] = [{"formattedValue": address}]
        if note:
            person["biographies"] = [{"value": note}]
        if url:
            person["urls"] = [{"value": url}]
        return person

    @classmethod
    def build_update_body(cls, *, resource_name, name=None, email=None, phone=None,
                          org=None, address=None, note=None, url=None,
                          source=None, etag=None):
        """Build an updateContact body and updateMask from convenience flags.

        Each provided field is tagged with the contact's CONTACT source so the
        API knows which source to mutate. ``source`` is a ``{type, id}`` dict
        from the existing contact's ``metadata.sources`` (preferred); when
        omitted it is derived from ``resource_name``. ``etag`` (if provided) is
        attached for optimistic concurrency. Returns ``({}, "")`` when nothing
        was supplied (the caller should then fall back to ``--json`` /
        ``--update-mask``).
        """
        if isinstance(source, dict) and source.get("id"):
            src = {"type": source.get("type", cls.CONTACT_SOURCE), "id": source["id"]}
        else:
            src = {
                "type": cls.CONTACT_SOURCE,
                "id": cls.resource_id(resource_name=resource_name),
            }
        body = {}
        mask_parts = []
        if name:
            body["names"] = [{"metadata": {"source": src}, "displayName": name}]
            mask_parts.append("names")
        if email:
            body["emailAddresses"] = [{"metadata": {"source": src}, "value": email}]
            mask_parts.append("emailAddresses")
        if phone:
            body["phoneNumbers"] = [{"metadata": {"source": src}, "value": phone}]
            mask_parts.append("phoneNumbers")
        if org:
            body["organizations"] = [{"metadata": {"source": src}, "name": org}]
            mask_parts.append("organizations")
        if address:
            body["addresses"] = [{"metadata": {"source": src}, "formattedValue": address}]
            mask_parts.append("addresses")
        if note:
            body["biographies"] = [{"metadata": {"source": src}, "value": note}]
            mask_parts.append("biographies")
        if url:
            body["urls"] = [{"metadata": {"source": src}, "value": url}]
            mask_parts.append("urls")
        if body:
            body["metadata"] = {"sources": [src]}
            if etag:
                body["etag"] = etag
        return body, ",".join(mask_parts)

    @classmethod
    def pick_source(cls, *, person):
        """Return the CONTACT source from a person's metadata, if any."""
        sources = (person.get("metadata") or {}).get("sources") or []
        for source in sources:
            if source.get("type") == cls.CONTACT_SOURCE:
                return source
        return sources[0] if sources else None

#--------------------------------------------------
# ContactsClient: read and mutate contacts
#--------------------------------------------------


class ContactsClient:
    """Talk to the People API through the gws command."""

    SEARCH_PAGE_MAX = 100
    LIST_PAGE_MAX = 1000

    def __init__(self, *, runner=None):
        self._runner = runner if runner is not None else GwsCommandRunner()

    def list_contacts(self, *, mask, limit, dry_run=False):
        """Return all contacts by paging through ``connections.list``."""
        out = []
        page_token = None
        if limit and limit > 0:
            page_size = min(limit, ContactsClient.LIST_PAGE_MAX)
        else:
            page_size = ContactsClient.LIST_PAGE_MAX
        while True:
            params = {
                "resourceName": "people/me",
                "personFields": mask,
                "pageSize": page_size,
            }
            if page_token:
                params["pageToken"] = page_token
            args = [
                "people", "people", "connections", "list",
                "--params", json.dumps(params),
            ]
            if dry_run:
                args.append("--dry-run")
            raw = self._runner.run(args=args)
            data = json.loads(raw)
            if not isinstance(data, dict):
                break
            for connection in data.get("connections") or []:
                out.append(connection)
                if 0 < limit <= len(out):
                    return out
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return out

    def search_contacts(self, *, query, mask, limit=0, dry_run=False):
        """Return contacts matching ``query`` via ``searchContacts``."""
        out = []
        page_token = None
        if limit and limit > 0:
            page_size = min(limit, ContactsClient.SEARCH_PAGE_MAX)
        else:
            page_size = ContactsClient.SEARCH_PAGE_MAX
        while True:
            params = {"query": query, "readMask": mask, "pageSize": page_size}
            if page_token:
                params["pageToken"] = page_token
            args = [
                "people", "people", "searchContacts",
                "--params", json.dumps(params),
            ]
            if dry_run:
                args.append("--dry-run")
            raw = self._runner.run(args=args)
            data = json.loads(raw)
            if not isinstance(data, dict):
                break
            for result in data.get("results") or []:
                if isinstance(result, dict) and result.get("person"):
                    out.append(result["person"])
                    if 0 < limit <= len(out):
                        return out
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return out

    def get_contact(self, *, resource_name, mask, dry_run=False):
        """Fetch a single contact by resource name."""
        args = [
            "people", "people", "get",
            "--params", json.dumps(
                {"resourceName": resource_name, "personFields": mask}
            ),
        ]
        if dry_run:
            args.append("--dry-run")
        data = json.loads(self._runner.run(args=args))
        return data if isinstance(data, dict) else {}

    def create_contact(self, *, body, dry_run=False):
        """Create a contact and return the created Person resource."""
        args = [
            "people", "people", "createContact",
            "--json", json.dumps(body),
        ]
        if dry_run:
            args.append("--dry-run")
        data = json.loads(self._runner.run(args=args))
        return data if isinstance(data, dict) else {}

    def update_contact(self, *, resource_name, body, update_mask, dry_run=False):
        """Update a contact and return the updated Person resource."""
        args = [
            "people", "people", "updateContact",
            "--params", json.dumps(
                {"resourceName": resource_name, "updateMask": update_mask}
            ),
            "--json", json.dumps(body),
        ]
        if dry_run:
            args.append("--dry-run")
        data = json.loads(self._runner.run(args=args))
        return data if isinstance(data, dict) else {}

    def delete_contact(self, *, resource_name, dry_run=False):
        """Delete a contact by resource name."""
        args = [
            "people", "people", "deleteContact",
            "--params", json.dumps({"resourceName": resource_name}),
        ]
        if dry_run:
            args.append("--dry-run")
        self._runner.run(args=args)

#--------------------------------------------------
# MarkdownRenderer: contacts as front matter
#--------------------------------------------------


class MarkdownRenderer:
    """Render contacts as YAML front-matter blocks."""

    EMPTY = "_No contacts._\n"

    def render(self, *, people):
        """Render each contact as a front-matter block."""
        if not people:
            return MarkdownRenderer.EMPTY
        return "\n".join(self._render_person(person=person) for person in people)

    @staticmethod
    def _person_name(*, person):
        """Return the first display name, or a placeholder."""
        for name in person.get("names") or []:
            if name.get("displayName"):
                return name["displayName"]
        return "(no name)"

    @staticmethod
    def _first_values(*, person, field, key):
        """Return every non-empty ``key`` value stored under ``field``."""
        out = []
        for item in person.get(field) or []:
            value = item.get(key)
            if value:
                out.append(value)
        return out

    @classmethod
    def _render_person(cls, *, person):
        """Render one contact as a front-matter block."""
        resource = person.get("resourceName") or ""
        emails = cls._first_values(person=person, field="emailAddresses", key="value")
        phones = cls._first_values(person=person, field="phoneNumbers", key="value")
        orgs = cls._first_values(person=person, field="organizations", key="name")
        meta = f"- resource: {resource}\n"
        body = [f"# {cls._person_name(person=person)}"]
        if emails:
            body.append("- email: " + ", ".join(emails))
        if phones:
            body.append("- phone: " + ", ".join(phones))
        if orgs:
            body.append("- org: " + ", ".join(orgs))
        return f"---\n{meta}---\n\n" + "\n".join(body) + "\n"

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
        return cls._render_script(all_opts=all_opts, categories=categories, name=name)

#--------------------------------------------------
# CliParser: build the command-line interface
#--------------------------------------------------


class CliParser:
    """Build the gcontacts argument parser."""

    DESCRIPTION = "gws wrapper: read, create, update, and delete Google Contacts."
    DEFAULT_MASK = "names,emailAddresses,phoneNumbers,organizations,addresses,metadata"

    def build(self):
        """Build and return the argument parser."""
        parser = argparse.ArgumentParser(description=CliParser.DESCRIPTION)
        action = parser.add_mutually_exclusive_group()
        action.add_argument(
            "--list", action="store_true",
            help="list all contacts (default when no other action is given)",
        )
        action.add_argument(
            "--search", metavar="QUERY", default=None,
            help="search contacts matching QUERY",
        )
        action.add_argument(
            "--get", metavar="RESOURCE", default=None,
            help="get one contact by resource name (e.g. people/c123...)",
        )
        action.add_argument(
            "--create", action="store_true",
            help="create a contact (requires --name or --json)",
        )
        action.add_argument(
            "--update", metavar="RESOURCE", default=None,
            help="update a contact by resource name",
        )
        action.add_argument(
            "--delete", metavar="RESOURCE", default=None,
            help="delete a contact by resource name",
        )
        parser.add_argument("--name", default=None, help="contact display name (create/update)")
        parser.add_argument("--email", default=None, help="contact email address (create/update)")
        parser.add_argument("--phone", default=None, help="contact phone number (create/update)")
        parser.add_argument("--org", default=None, help="contact organization name (create/update)")
        parser.add_argument(
            "--address", default=None,
            help="contact postal address (create/update)",
        )
        parser.add_argument("--note", default=None, help="contact biography/note (create/update)")
        parser.add_argument("--url", default=None, help="contact URL (create/update)")
        parser.add_argument(
            "--json", dest="json_body", default=None,
            help="raw People API JSON body for create/update (overrides convenience flags)",
        )
        parser.add_argument(
            "--update-mask", default=None,
            help="explicit updateMask for --update; required when using --json, "
                 "otherwise defaults to the fields you provide",
        )
        parser.add_argument(
            "--mask", default=CliParser.DEFAULT_MASK,
            help=f"personFields/readMask (default: {CliParser.DEFAULT_MASK})",
        )
        parser.add_argument(
            "--limit", type=int, default=0,
            help="max contacts to list/search (default: 0 = all)",
        )
        parser.add_argument(
            "--md", action="store_true",
            help="render front-matter markdown instead of JSON",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="validate requests locally via gws --dry-run without mutating contacts",
        )
        parser.add_argument("--verbose", "-v", action="count", default=0)
        parser.add_argument(
            "--quiet", action="store_true",
            help="suppress non-error output; runtime errors are still reported",
        )
        parser.add_argument(
            "--completion", action="store_true",
            help="Print bash completion script to stdout and exit",
        )
        return parser

#--------------------------------------------------
# Application: orchestrate the CLI
#--------------------------------------------------


class Application:
    """Run the gcontacts command and translate failures into exit codes."""

    EXIT_SUCCESS = 0
    EXIT_ERROR = 1
    EXIT_USAGE = 2

    def __init__(self, *, argv=None, runner=None, console=None):
        self._argv = list(sys.argv[1:] if argv is None else argv)
        self._console = console if console is not None else Console()
        self._runner = runner if runner is not None else GwsCommandRunner()
        self._client = ContactsClient(runner=self._runner)
        self._renderer = MarkdownRenderer()

    def run(self):
        """Parse the command line, run one action, and return an exit code."""
        parser = CliParser().build()
        if "--completion" in self._argv:
            self._console.write(
                Completion.generate(parser=parser, name=self._command_name()) + "\n"
            )
            return Application.EXIT_SUCCESS

        options = parser.parse_args(self._argv)
        if (
            options.search is None
            and options.get is None
            and not options.create
            and options.update is None
            and options.delete is None
        ):
            return self._list(options=options)
        if options.search is not None:
            return self._search(options=options)
        if options.get is not None:
            return self._get(options=options)
        if options.delete is not None:
            return self._delete(options=options)
        if options.create:
            return self._create(parser=parser, options=options)
        return self._update(parser=parser, options=options)

    @staticmethod
    def _command_name():
        """Return the installed command name derived from argv[0]."""
        return Path(sys.argv[0]).resolve().stem

    def _list(self, *, options):
        """List every contact and write it as JSON or markdown."""
        try:
            people = self._client.list_contacts(
                mask=options.mask, limit=options.limit, dry_run=options.dry_run
            )
        except Exception as exc:
            hint = GwsCommandRunner.auth_hint(exc=exc)
            self._console.error(f"gws contacts list failed: {exc}{hint}")
            return Application.EXIT_ERROR
        self._write_people(people=people, options=options)
        return Application.EXIT_SUCCESS

    def _search(self, *, options):
        """Search contacts and write the matches as JSON or markdown."""
        try:
            people = self._client.search_contacts(
                query=options.search,
                mask=options.mask,
                limit=options.limit,
                dry_run=options.dry_run,
            )
        except Exception as exc:
            hint = GwsCommandRunner.auth_hint(exc=exc)
            self._console.error(f"gws contacts search failed: {exc}{hint}")
            return Application.EXIT_ERROR
        self._write_people(people=people, options=options)
        return Application.EXIT_SUCCESS

    def _get(self, *, options):
        """Fetch one contact and write it as JSON or markdown."""
        try:
            person = self._client.get_contact(
                resource_name=options.get,
                mask=options.mask,
                dry_run=options.dry_run,
            )
        except Exception as exc:
            hint = GwsCommandRunner.auth_hint(exc=exc)
            self._console.error(f"gws contact get failed: {exc}{hint}")
            return Application.EXIT_ERROR
        if options.md:
            self._console.write(self._renderer.render(people=[person]))
        else:
            self._write_json(data=person)
        return Application.EXIT_SUCCESS

    def _delete(self, *, options):
        """Delete one contact and report success unless quiet."""
        try:
            self._client.delete_contact(
                resource_name=options.delete, dry_run=options.dry_run
            )
        except Exception as exc:
            hint = GwsCommandRunner.auth_hint(exc=exc)
            self._console.error(f"gws contact delete failed: {exc}{hint}")
            return Application.EXIT_ERROR
        if not options.quiet and not options.dry_run:
            self._console.status(f"Deleted {options.delete}")
        return Application.EXIT_SUCCESS

    def _create(self, *, parser, options):
        """Create a contact from raw JSON or convenience flags."""
        if options.json_body:
            body, valid = self._load_json_body(value=options.json_body)
            if not valid:
                return Application.EXIT_USAGE
        else:
            if not options.name:
                parser.error("--create requires --name (or --json)")
            body = PersonBodyBuilder.build_person(
                name=options.name,
                email=options.email,
                phone=options.phone,
                org=options.org,
                address=options.address,
                note=options.note,
                url=options.url,
            )
        if not body:
            parser.error("--create requires --name/--email/... or --json")
        try:
            person = self._client.create_contact(body=body, dry_run=options.dry_run)
        except Exception as exc:
            hint = GwsCommandRunner.auth_hint(exc=exc)
            self._console.error(f"gws contact create failed: {exc}{hint}")
            return Application.EXIT_ERROR
        self._write_person(person=person, options=options)
        return Application.EXIT_SUCCESS

    def _update(self, *, parser, options):
        """Update a contact from raw JSON or convenience flags."""
        if options.json_body:
            body, valid = self._load_json_body(value=options.json_body)
            if not valid:
                return Application.EXIT_USAGE
            update_mask = options.update_mask or ""
        else:
            try:
                existing = self._client.get_contact(
                    resource_name=options.update,
                    mask=options.mask,
                    dry_run=options.dry_run,
                )
            except Exception as exc:
                hint = GwsCommandRunner.auth_hint(exc=exc)
                self._console.error(f"gws contact get failed: {exc}{hint}")
                return Application.EXIT_ERROR
            source = (
                PersonBodyBuilder.pick_source(person=existing)
                if isinstance(existing, dict) else None
            )
            etag = existing.get("etag") if isinstance(existing, dict) else None
            body, update_mask = PersonBodyBuilder.build_update_body(
                resource_name=options.update,
                name=options.name,
                email=options.email,
                phone=options.phone,
                org=options.org,
                address=options.address,
                note=options.note,
                url=options.url,
                source=source,
                etag=etag,
            )
            if not body:
                parser.error("--update requires --name/--email/... or --json")
            update_mask = options.update_mask or update_mask
        if not update_mask:
            parser.error("--update requires an --update-mask when using --json")
        try:
            person = self._client.update_contact(
                resource_name=options.update,
                body=body,
                update_mask=update_mask,
                dry_run=options.dry_run,
            )
        except Exception as exc:
            hint = GwsCommandRunner.auth_hint(exc=exc)
            self._console.error(f"gws contact update failed: {exc}{hint}")
            return Application.EXIT_ERROR
        self._write_person(person=person, options=options)
        return Application.EXIT_SUCCESS

    def _load_json_body(self, *, value):
        """Parse a raw JSON body and return ``(body, True)`` or ``(None, False)``."""
        try:
            return json.loads(value), True
        except json.JSONDecodeError as exc:
            self._console.error(f"invalid --json: {exc}")
            return None, False

    def _write_people(self, *, people, options):
        """Write a people collection as markdown or JSON."""
        if options.md:
            self._console.write(self._renderer.render(people=people))
        else:
            self._write_json(data=people)

    def _write_person(self, *, person, options):
        """Write a single person as markdown or JSON."""
        if options.md and not options.dry_run:
            self._console.write(self._renderer.render(people=[person]))
        else:
            self._write_json(data=person)

    def _write_json(self, *, data):
        """Write one JSON document followed by a newline."""
        self._console.write(json.dumps(data, ensure_ascii=False, indent=2))
        self._console.write("\n")


if __name__ == "__main__":
    sys.exit(Application().run())
