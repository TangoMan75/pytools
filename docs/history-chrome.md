# Chrome History

`history-chrome.py` reads the Google Chrome `History` SQLite database and emits
a chronological log of visits. It scans the `Default` and `Profile N`
directories (or a single `--profile`), snapshotting each locked `History` file
to a temp copy before querying. By default it covers a single calendar day,
and can be widened with the date-range arguments:

```text
python3 history-chrome.py [--user-data DIR] [--profile NAME] [--db PATH]
                          [--no-copy] [--typed-only]
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

## Canonical time format: UTC epoch milliseconds

As with `history-opencode.py`, the range is resolved to **UTC epoch
milliseconds** exactly once at the input boundary
(`DateRangeResolver.resolve_date_range`).
Human-readable input is parsed a single time; `--start-ms` / `--end-ms` skip
parsing entirely.

### Chrome epoch microseconds

Chrome does **not** store Unix time. The `visits.visit_time` column is an
integer count of microseconds since the Windows/WebKit epoch
(1601-01-01 00:00:00 UTC). The only additional step is a fixed conversion at
the query boundary:

```python
start_us = (from_ms * 1000) + ChromeHistory.EPOCH_OFFSET_US  # 11644473600000000
end_us   = (to_ms   * 1000) + ChromeHistory.EPOCH_OFFSET_US
```

The SQL filter is then a pure integer comparison on `visit_time`, with no
per-row conversion in the query itself:

```sql
WHERE v.visit_time >= ? AND v.visit_time < ?
```

Per-row conversion happens only when building the output records, where
`ChromeHistory.webkit_us_to_epoch_ms()` converts each `visit_time` back to
epoch ms before formatting a local `datetime` string.

### Notes

- Date-range input and the default single-day end are resolved in the
  OS-local timezone (`DateRangeResolver.resolve`,
  `DateRangeResolver.default_end_ms`).
- The History file is locked by Chrome, so it is copied to a temp file before
  reading unless `--no-copy` is given (which requires Chrome to be closed).

## Output

- Default output is JSON: one object per visit with a local `datetime`, URL,
  title, visit duration (ms), profile, transition core, and redirect/typed
  flags. Entries are sorted chronologically.
- `--md` renders a Markdown table (`# | Time | URL | Title | Duration |
  Transition`) with a per-domain and typed-entry summary line.
- `--typed-only` restricts the query to URL-bar / keyword / form-submit /
  reload transitions (cores 1, 7, 8, 9, 10).
- `--quiet`: Suppress non-error output; runtime errors are still reported.
