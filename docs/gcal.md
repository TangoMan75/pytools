# Google Calendar

`gcal.py` lists Google Calendar events through the `gws`
command-line tool. It wraps `gws calendar events list` for a single calendar
or fans out to every calendar in the user's calendarList and merges the
results.

```text
python3 gcal.py [--calendar ID] [--start YYYY-MM-DD[ HH:MM:SS]]
                           [--end YYYY-MM-DD[ HH:MM:SS]]
                           [--max-results N] [--md] [--csv] [--quiet]
```

## Arguments

- `--calendar`: calendar ID, name, or an `http(s)` iCalendar (`.ics`) feed
  URL. A value starting with `http://` or `https://` is auto-detected as an
  iCal feed: it is downloaded and parsed directly (no `gws` call), its events
  are expanded for `RRULE` recurrences and filtered to the `--start`/`--end`
  window. If omitted, every calendar in the user's calendarList is queried and
  merged.
- `--start` / `--end`: local `YYYY-MM-DD` or `YYYY-MM-DD HH:MM:SS`
  (defaults: today / today). A date-only `--start` means that day's 00:00:00;
  a date-only `--end` means that day's 23:59:59.
- `--max-results`: max events per page, per calendar (default 250).
- `--md`: render a Markdown table instead of JSON.
- `--csv`: render CSV instead of JSON.
- `--quiet`: suppress non-error output; runtime errors are still reported.

## Time format: local ISO-8601 with timezone offset

Unlike Gmail's date-only search, Google Calendar's `events.list` accepts
`timeMin` / `timeMax` with **sub-day precision** (RFC 3339 timestamps). The
range is therefore resolved once, directly from the local-time input to
local ISO-8601 strings with the timezone offset (e.g.
`2026-08-14T09:30:00+02:00`):

- `--start` / `--end` are parsed as naive local datetimes by
  `LocalDateRange.parse_local`.
- `LocalDateRange.resolve_iso_range` applies the date-only defaults
  (00:00:00 for `--start`, 23:59:59 for `--end`), validates that
  `end >= start`, and formats each as `dt.astimezone().isoformat()`.
- These ISO strings are passed verbatim as `timeMin` / `timeMax` to the
  Calendar API. There is no epoch-ms intermediate: parsing to epoch
  milliseconds and converting back to ISO would add work without preserving
  any extra precision.

## Output

- Default output is JSON: for a single calendar, the raw `gws` response; for
  the all-calendars fan-out, a merged `{kind, items, calendars_queried}`
  object where each event is tagged with its source `calendarId` /
  `calendarSummary`.
- `--md` renders a Markdown table (`Calendar | Subject | Start Date | Start
  Time | End Date | End Time | Description | Attendee | Location`).
- `--csv` renders the same columns as CSV.

When `--calendar` is an iCal URL, the output is the same shape as the
all-calendars fan-out: a `{kind, items}` object (the Calendar column is
populated from the feed's `X-WR-CALNAME` or the URL). Recurring events
(`RRULE` with `FREQ` DAILY/WEEKLY/MONTHLY/YEARLY, `INTERVAL`, `COUNT`,
`UNTIL`, `BYDAY`, `BYMONTHDAY`) are expanded within the requested window.

## Exit codes

- `0`: events fetched (possibly an empty list).
- `1`: `gws` invocation failed.
- `2`: bad CLI arguments.
