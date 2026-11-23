# ZeroClaw Memory

`history-zeroclaw.py` reports ZeroClaw sessions and their full chronological
chat log from the zeroclaw SQLite database. By default it covers a single
calendar day, and can be widened with the date-range arguments:

```text
python3 history-zeroclaw.py [--db PATH]
                           [--start YYYY-MM-DD[ HH:MM:SS]] [--end YYYY-MM-DD[ HH:MM:SS]]
                           [--start-ms EPOCH_MS] [--end-ms EPOCH_MS] [--md]
```

## Date-range arguments

- `--start` / `--end` accept a date (`YYYY-MM-DD`) or a timestamp
  (`YYYY-MM-DD HH:MM:SS`) in local time. A date-only `--start` means that
  day's 00:00:00; a date-only `--end` means the current time of day. `--end`
  is exclusive.
- `--start-ms` / `--end-ms` accept raw UTC epoch milliseconds and are
  mutually exclusive with the human-readable forms.
- When neither `--end` nor `--end-ms` is given, the query defaults to a single
  calendar day: end = midnight of the day after start (or tomorrow if no
  start is given). Pass an explicit `--end` / `--end-ms` for a longer window.
- A session is included when its `[created_at, last_activity)` window overlaps
  the `[start, end)` range. Each included session then contributes only the
  messages whose own `created_at` falls in `[start, end)`.

## Canonical time format: UTC epoch milliseconds

As with `history-opencode.py`, the range is resolved to **UTC epoch
milliseconds** exactly once at the input boundary
(`DateRangeArgs.resolve_date_range`).
All filtering then compares epoch-ms integers against epoch-ms integers:

- Session overlap: `time_created >= to_ or time_updated <= from_` skips the
  session.
- Message filtering: `ts < from_ or ts >= to_` skips the message.
- Durations are computed as `(time_updated - time_created) / 1000.0`, which
  only works because both columns are normalized to the same epoch-ms unit.

To avoid unnecessary calculations, pass `--start-ms` / `--end-ms` to skip
human-date parsing entirely.

### Difference from opencode

The zeroclaw database does **not** store epoch ms. `created_at` and
`last_activity` are ISO-8601 strings with a timezone offset
(`~/.zeroclaw/data/sessions/sessions.db`). Each record is therefore converted
per row via `Dates.parse_iso()` during the fetch
(`SessionRepository.fetch_sessions`, `SessionRepository.fetch_messages`), and
the overlap filtering happens in Python rather than in
SQL. Only the range itself is pre-converted; the per-record conversion is
unavoidable unless the schema is changed.

### Notes

- `Dates.TZ_PARIS` (fixed `+02:00`) is used only by the standalone date
  helpers (`Dates.compute_epoch_range`, `Dates.compute_week_range`,
  `Dates.compute_calendar_range`), which are not part of the `Application.run`
  query path. `DateRangeArgs.resolve` and `Dates.default_end_ms` use the
  OS-local timezone instead, which is the correct behavior for date-range
  input. The fixed offset is wrong half the year and should not be relied on.
- `Dates.parse_iso()` treats naive ISO strings as UTC.

## Output

- Default output is JSON: one object per session with `time_created` /
  `time_updated` (epoch ms), `start_local` / `end_local` (local ISO 8601),
  duration, message count, state, channel/room/sender ids, and the full
  `messages` array (`role`, `content`, `time_created`, `created_at_local`).
  Only `user` and `assistant` roles are included; tool calls are discarded.
- `--md` renders a Markdown report of sessions and a chronological chat log
  per session.
- `--quiet`: Suppress non-error output; runtime errors are still reported.
