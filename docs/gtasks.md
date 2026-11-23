# Google Tasks

`gtasks.py` lists or creates Google Tasks through the `gws`
command-line tool. It wraps `gws tasks tasklists list` and
`gws tasks tasks list` / `insert`.

```text
python3 gtasks.py [--list TITLE]
                        [--due | --completed]
                        [--start YYYY-MM-DD] [--end YYYY-MM-DD]
                        [--create] [--title TITLE] [--notes TEXT]
                        [--show-completed] [--max-results N] [--md] [--quiet]
```

## Arguments

- `--list`: task list TITLE (case-insensitive exact match, with raw ID
  passthrough fallback). If omitted, every task list in the account is
  queried and merged.
- `--create`: create one task instead of listing (requires `--list` and
  `--title`); `--notes` adds task notes.
- `--due`, `--completed`: select which timestamp is filtered by
  `--start` / `--end`. These options are mutually exclusive. `--due` keeps
  only not-yet-completed tasks that have a due date; `--completed` keeps only
  finished tasks. Without date bounds, all matching results are requested,
  subject to `--max-results`.
- `--start` / `--end`: inclusive `YYYY-MM-DD` dates. If only one is given,
  the other defaults to today. Date bounds use `00:00:00` at the start and
  `23:59:59` at the end. If neither is given, no timestamp filter is applied
  and **all** tasks are returned regardless of date.
- `--show-completed`: include completed tasks (default: off). It is enabled
  automatically for `--completed` and always overridden off for `--due`. When
  completed tasks are requested, `showHidden` is also sent so tasks completed
  in Google's first-party clients (web UI, mobile apps), which the API marks
  as `hidden`, are returned too.
- `--max-results`: max tasks per page, per list (default 100, the API max).
- `--md`: render each task as a Markdown block instead of JSON.
- `--quiet`: suppress non-error output; runtime errors are still reported.

## Date Filters: plain YYYY-MM-DD dates → RFC-3339 UTC midnight

The date range is resolved as plain `YYYY-MM-DD` strings — no epoch, no
timezone offset arithmetic:

- `--start` / `--end` are validated to `YYYY-MM-DD` by
  `TaskDateSelection.parse_date`.
- `TaskDateSelection.window(start, end)` produces
  `min = f"{start}T00:00:00Z"` and `max = f"{end}T23:59:59Z"`.
- `--due` sends `dueMin` / `dueMax`, excludes completed tasks, and drops
  tasks without a due date.
- `--completed` sends `completedMin` / `completedMax`, includes completed
  tasks, and keeps only finished tasks.
- `--show-completed` (and `--completed`) send `showCompleted` and
  `showHidden`, so hidden completed tasks (finished in the web UI or mobile
  apps) are included.
- When dates are given with `--show-completed` and no explicit selector, the
  range uses completion time and returns completed tasks only.

## Output

- Default output is JSON: for a single list, the raw `gws` response annotated
  with a `_tasklist` `{id, title}` field; for the all-lists fan-out, a merged
  `{kind, items}` object where each task is tagged with its source
  `tasklist` / `tasklistTitle`.
- `--md` renders one front-matter block per task with `##` titles, a task-list
  tag, `#task`/`#done`/`#todo` status tags, due/updated/completed metadata,
  links, and notes.

## Exit codes

- `0`: tasks fetched (possibly an empty list) or created.
- `1`: `gws` invocation failed.
- `2`: bad CLI arguments.
