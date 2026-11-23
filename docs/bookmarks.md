# Chrome Bookmarks

`bookmarks.py` reads the Google Chrome `Bookmarks` JSON files (plain JSON, not
encoded) from the `Default` and `Profile N` directories (or a single
`--profile` / `--db` file), flattens the bookmark tree, optionally filters
entries by add date and prints them as JSON, Markdown or Netscape Bookmarks
HTML.

```text
python3 bookmarks.py [--user-data DIR] [--profile NAME] [--db PATH]
                     [--start YYYY-MM-DD[ HH:MM:SS]] [--end YYYY-MM-DD[ HH:MM:SS]]
                     [--json | --md | --html]
                     [--verbose] [-v] [--quiet] [--completion]
```

## Options

- `--db PATH` — read an explicit `Bookmarks` JSON file (overrides
  `--user-data`/`--profile`). Useful for other Chromium-based browsers
  (Brave, Edge, Chromium...) or a test fixture.
- `--profile NAME` — restrict to one profile. Without it every profile
  containing a `Bookmarks` file is read.
- `--start` / `--end` — filter entries by bookmark add date in local time.
  A date-only `--start` means that day's 00:00:00; a date-only `--end` means
  23:59:59 of that day. `--end` is inclusive of the whole day. Without
  `--start` there is no lower bound; without `--end` the upper bound is now.
- `--json` — JSON array (default). One object per bookmark with `name`,
  `url`, `date_created`, `date_modified` and slugified `tags` (ancestor
  folder chain). No `datetime`, `guid` or `profile`. Entries are sorted by
  add date.
- `--md` — one Markdown block per bookmark. Tags come from the ancestor
  folder chain, slugified in both the front matter and the hashtag list
  (`#bookmark #bookmarks-bar #dev ...`). Block template:

  ```markdown
  ---
  - created_at: {{ADD_DATE}}
  - modified_at: {{LAST_MODIFIED}}
  - tags:
    - {{parent_folder_slug_1}}
    - {{parent_folder_slug_2}}
  ---

  ## {{name}}

  #bookmark #{{parent_folder_slug_1}} #{{parent_folder_slug_2}}

  - [{{name}}]({{url}})
  ```

  `created_at` is the bookmark add date; `modified_at` is the containing
  folder's `date_modified` (falls back to the bookmark add date).
- `--html` — Netscape Bookmark file format
  (`NETSCAPE-Bookmark-file-1`) with the folder tree preserved, ready to
  import into any browser. `ADD_DATE` / `LAST_MODIFIED` are Unix epoch
  seconds and all text values are HTML-escaped.
- `--quiet` — suppress non-error output; runtime errors are still reported
  and exit 1. Usage errors (invalid dates) still exit 2.
- `--completion` — print the bash completion script to stdout and exit.
  Install it with `./bookmarks-completion.sh` sourcing or pipe it into
  `~/.local/share/TangoMan75/bookmarks/bookmarks-completion.sh` via
  `installer.py`.

## Notes

- The `Bookmarks` file is plain JSON, so it is read in place; no temp copy
  is needed even while Chrome is running (the file is only rewritten on
  changes, so a mid-write read may throw `JSONDecodeError` -> runtime error
  exit 1).
- Chrome stores `date_added` as microseconds since 1601-01-01
  (`ChromeBookmarks.CHROME_EPOCH_OFFSET_US = 11644473600000000`); conversion
  happens at the output boundary via `ChromeBookmarks.chrome_us_to_ms()`.
- Tags are slugified in JSON `tags` and in the Markdown front matter and
  hashtags (`web <&>` -> `web`, no `#`-unsafe characters); the HTML folder
  tree keeps the raw folder names.
- Trailing slashes are stripped from bookmark URLs on output
  (`https://www.python.org/` -> `https://www.python.org`); a bare scheme
  like `https://` is left untouched.
