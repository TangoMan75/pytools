# Moments

`moments.py` resolves one date for daily commands. `DATE` is optional and
defaults to today. Input is inferred and validated as `YYYY-MM-DD`,
`YYYY-MM-DD HH:MM`, `HH:MM DD/MM/YYYY`, ISO 8601, or epoch seconds. Timezone
names use the IANA database and default to `Europe/Paris` with
daylight-saving support.

```text
python3 moments.py [DATE] [--short | --long | --iso | --epoch | --format FMT]
python3 moments.py [DATE] [--day N | --week N | --month N | --year N] [--tz TZ]
python3 moments.py [DATE] --from DATE [--short]
```

The output format defaults to `--short`, which prints `YYYY-MM-DD`.
`--long` prints one `YYYY-MM-DD HH:MM:SS` timestamp. `--iso` prints one ISO
8601 timestamp. `--epoch` prints one epoch-millisecond timestamp. `--format`
accepts a Python `strftime` format. `--weekday`, `--week-number`, and `--json`
provide calendar and machine-readable output. `--utc` converts output to UTC.

Adjustment options accept a signed integer count:

- `--sec N`, `--min N`, `--hour N`
- `--day N`, `--week N`, `--month N`, `--year N`

`--from DATE` computes the relative time between `DATE` and the target (default:
now). With `--short`, only years, months, and days are shown. Without `--short`,
hours, minutes, and seconds are included. Date-only inputs are treated as
midnight.

`--quiet` suppresses non-error output; runtime errors are still reported.

Month and year adjustments clamp invalid dates to the last valid day of the
target month. Use `--tz TZ` for another IANA timezone. `-h` and `--help` list
common valid timezone values.
