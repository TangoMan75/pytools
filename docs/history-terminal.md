# Terminal History

`history-terminal.py` reads shell history from `~/.zsh_history` and/or
`~/.bash_history` and emits a chronological report.

```text
python3 history-terminal.py [--start YYYY-MM-DD[ HH:MM:SS]]
                            [--end YYYY-MM-DD[ HH:MM:SS]] [--md]
```

## Arguments

- `--start` / `--end`: local `YYYY-MM-DD` or `YYYY-MM-DD HH:MM:SS`
  (defaults: today 00:00:00 / now). A date-only `--start` means that day's
  00:00:00; a date-only `--end` means the current time of day. `--end` is
  exclusive.
- `--md`: print as a Markdown table instead of JSON.

## Time format: epoch seconds

zsh history lines are stored as `: <epoch_seconds>:<elapsed>;<command>`, so
the file's native time unit is **epoch seconds**. The range is resolved once
to `(start_sec, end_sec)` at the input boundary (`DateRange.resolve`), and
each zsh entry's raw epoch-seconds timestamp is compared directly:

```python
if not (from_sec <= parsed["_ts_sec"] < to_sec):
    continue
```

There is no epoch-ms layer: converting the range and every entry to
milliseconds would add a `*1000` round-trip without any extra precision, so
the whole pipeline works in the unit the history file actually uses. bash
history lines carry no timestamp, so range filtering only applies to zsh
entries.

## Output

- Default output is JSON: an array of `{"index", "command", "datetime"?}`
  objects (chronological, deduplicated across both history files).
- `--md` renders a Markdown table (`# | Command | Datetime`).
- `--quiet`: Suppress non-error output; runtime errors are still reported.
