# jira-rest

A thin, dependency-free wrapper around the Jira Cloud REST API. It authenticates
with an Atlassian API token and fetches or updates a Jira ticket, rendering
tickets and their comments as markdown for notes, docs, or chat — no external
Jira CLI required.

## Setup

Credentials are stored in `~/.config/TangoMan75/jira/.env` (created by
`init`). Generate the file interactively:

```bash
python3 jira-rest.py init
```

It prompts for the three values and writes them with `0600` permissions:

```dotenv
ATLASSIAN_SITE=shippeo.atlassian.net
ATLASSIAN_EMAIL=you@example.com
ATLASSIAN_API_TOKEN=ATATT3xFf...
```

- `ATLASSIAN_SITE` — your Jira Cloud site host (without `https://`).
- `ATLASSIAN_EMAIL` — the account email used for Basic auth.
- `ATLASSIAN_API_TOKEN` — an Atlassian API token (or a bearer token if no email).

Environment variables (`ATLASSIAN_SITE` / `ATLASSIAN_EMAIL` /
`ATLASSIAN_API_TOKEN` / `ATLASSIAN_TOKEN`) override the file. The `.env` file
is git-ignored.

## Commands

```bash
# Create / overwrite the credentials file
python3 jira-rest.py init [--force]

# Fetch a ticket and print markdown to stdout
python3 jira-rest.py read PROJ-123

# Write markdown to a file
python3 jira-rest.py read PROJ-123 --output PROJ-123.md

# Preview the API requests without calling Jira
python3 jira-rest.py read PROJ-123 --dry-run

# Add a comment to a ticket
python3 jira-rest.py update PROJ-123 --comment "Verified in QA"
python3 jira-rest.py update PROJ-123 --file note.md

# Preview the comment POST without calling Jira
python3 jira-rest.py update PROJ-123 --comment "Verified" --dry-run
```

## API surface

| Endpoint                                    | Purpose                    |
|---------------------------------------------|----------------------------|
| `GET /rest/api/3/issue/{key}`              | Ticket metadata + description |
| `GET /rest/api/3/issue/{key}/comment`      | Comments (paginated, all) |
| `POST /rest/api/3/issue/{key}/comment`     | Add a comment (plain text) |

Authentication uses HTTP Basic (`email:token`, base64) when an email is
present, or `Bearer` when only a token is supplied. Plain HTTP sites are
refused.

## Global options

- `--verbose`/`-v` — increase verbosity (stackable).
- `--quiet` — suppress non-error output; runtime errors are still reported.
- `--log` — print the log file to the terminal.
- `--completion` — print the bash completion script.

## Markdown output (read)

The ticket is rendered as:

- a `# <KEY>: <summary>` heading with a link to the issue,
- a metadata table (status, type, priority, assignee, reporter, dates, labels,
  components),
- a `## Description` section (Atlassian Document Format bodies are converted to
  markdown),
- a `## Comments` section listing each comment with author, date, and body.

With `--quiet`, runtime errors are still reported and exit `1`; usage errors
still exit `2`.
