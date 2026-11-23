# Gmail

`gmail.py` lists or reads Gmail messages through the `gws` command-line tool.
It wraps `gws gmail users messages list`, `gws gmail users messages get`, and
`gws gmail +read`.

```text
python3 gmail.py [--start YYYY-MM-DD] [--end YYYY-MM-DD]
                 [--from SENDER] [--to RECIPIENT] [--label LABEL]
                 [--read MESSAGE_ID] [--max-results N] [--max-messages N]
                 [--md] [--quiet]
```

## Arguments

- `--start` / `--end`: inclusive `YYYY-MM-DD` dates (default: today for
  both). `--end` is made inclusive of the full day (see below).
- `--from` / `--to`: filter by sender or recipient email/name.
- `--label`: filter by Gmail label (name or ID, e.g. `INBOX`, `"My Label"`,
  nested `Work/Projects`). If omitted, all messages in the date range are
  queried.
- `--read MESSAGE_ID`: read one message with headers and body as JSON. When
  combined with `--md`, render that message as markdown instead.
- `--max-results`: messages per page (default 100, max 500).
- `--max-messages`: hard cap on total messages fetched (default 500).
- `--md`: render each message as YAML front matter + body instead of JSON.
  HTML links from `body_html` that are missing from `body_text` are kept as a
  markdown `Links:` section. With `--read`, render that message as markdown.
- `--quiet`: suppress non-error output; runtime errors are still reported.

## Time format: plain YYYY-MM-DD dates

Gmail's search operators are **date-only**: `after:` and `before:` are
interpreted as whole calendar days in the user's account timezone, and Gmail
does not support sub-day filtering. The date range is therefore resolved as
plain `YYYY-MM-DD` strings — no epoch, no timezone arithmetic, no
`--start-ms` / `--end-ms`:

- `--start` / `--end` are validated to `YYYY-MM-DD` by `GmailDate.parse`.
- Date-only ranges represent `00:00:00` on `--start` through `23:59:59` on
  `--end`.
- The query uses `after:YYYY/MM/DD` with the start date, and
  `before:YYYY/MM/DD` with the day *after* `--end` — because `before:` is
  exclusive of its date, adding one day (`GmailDate.next_day`) is Gmail's
  equivalent of an inclusive `23:59:59` end bound.
- The literal date the user types is exactly what goes into the query; there
  is no round-trip through epoch milliseconds.

## Output

- Default output is JSON: one object per message (metadata headers when
  listed, full headers + body with `--read` / `--md`).
- `--md` renders each message as a YAML front-matter block (subject, from
  name, from email, date, and Gmail id when available) followed by the body,
  sorted by message date.
- When `body_text` already contains a URL, that link is not duplicated.
  HTML-only application links (for example Collective `Postuler` buttons)
  are appended so `--md` consumers do not lose them.
- `gmail --read MESSAGE_ID --md` prints a single markdown message block.

## Exit codes

- `0`: messages fetched (possibly an empty list).
- `1`: `gws` invocation failed.
- `2`: bad CLI arguments.
