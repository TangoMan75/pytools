# OpenCode Memory

`history-opencode.py` reports OpenCode sessions and their messages from the
opencode SQLite database. By default it covers today, and can be narrowed or
widened with the date-range arguments:

```text
python3 history-opencode.py [--start YYYY-MM-DD[ HH:MM:SS]] [--end YYYY-MM-DD[ HH:MM:SS]]
                           [--start-ms EPOCH_MS] [--end-ms EPOCH_MS] [--md]
```

## Date-range arguments

- `--start` / `--end` accept a date (`YYYY-MM-DD`) or a timestamp
  (`YYYY-MM-DD HH:MM:SS`) in local time. A date-only `--start` means that
  day's 00:00:00; a date-only `--end` means the current time of day. `--end`
  is exclusive.
- `--start-ms` / `--end-ms` accept raw UTC epoch milliseconds and are
  mutually exclusive with the human-readable forms.
- Defaults are today 00:00:00 to now.

## Canonical time format: UTC epoch milliseconds

The database stores `time_created` and `time_updated` as **UTC epoch
milliseconds**. All range queries compare raw integers:

```sql
WHERE time_created>=? AND time_created<?
```

To avoid unnecessary calculations, epoch milliseconds are the canonical unit
throughout the pipeline:

- **No conversion in the hot path** — filtering and ordering operate directly
  on the integer columns.
- **One parse at the boundary** — human-readable input (`--start` / `--end`)
  is parsed exactly once and converted to epoch ms by
  `DateRangeArgs.resolve_date_range`; everything downstream is pure integer
  comparison.
- **`--start-ms` / `--end-ms` skip parsing entirely** — pass the stored values
  directly for the least work.

### Notes

- `Dates.TZ_PARIS` (fixed `+02:00`) is used only by the standalone date
  helpers (`Dates.compute_epoch_range`, `Dates.compute_week_range`,
  `Dates.compute_calendar_range`), which are not part of the `Application.run`
  query path. `DateRangeArgs.resolve` uses the OS-local timezone instead,
  which is the correct behavior for date-range input. The fixed offset is
  wrong half the year and should not be relied on.
- Durations are computed as `(time_updated - time_created) / 1000.0`, which
  only works because both columns are in the same epoch-ms unit.

## Schema compatibility

The script detects the database schema automatically and works with both
OpenCode generations:

- **v1** uses the `session`, `message`, and `part` tables.
- **v2** uses `session_v2` (same columns as `session`) and stores messages in
  `session_message`. In v2, a message is one JSON document: user messages carry
  a `text` field, assistant messages carry a `content` list of `text`,
  `reasoning`, and `tool` parts. Non-chat rows such as `idle` or
  `agent-switched` are ignored.

If neither schema is present, the script reports the missing session table on
stderr and exits with code `1`.

## Output

- Default output is JSON: one object per session with `time_created` /
  `time_updated` (epoch ms), `start_local` / `end_local` (local ISO 8601),
  duration, model, agent, cost, token counts, and file diff summary.
- `--md` renders a Markdown report of sessions and per-session first user /
  last assistant messages.
- `--quiet`: Suppress non-error output; runtime errors are still reported.
