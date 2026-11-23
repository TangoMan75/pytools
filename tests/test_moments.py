#!/usr/bin/env python3
"""Tests for moments date conversion and adjustment CLI behavior."""

import io
import json
import subprocess
import sys
import unittest
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from moments import Application, Console, MomentParser, RelativeTimeFormatter, TimezoneResolver


class MomentCliTestCase(unittest.TestCase):
    """Provide the shared subprocess CLI runner for the moments tests."""

    @staticmethod
    def run_cli(*arguments):
        """Run the moments script and return the completed process."""
        script = Path(__file__).parents[1] / "moments.py"
        return subprocess.run(
            [sys.executable, str(script), *arguments],
            check=True,
            capture_output=True,
            text=True,
        )

    @staticmethod
    def seconds_of_day(moment):
        """Return the number of seconds elapsed since midnight."""
        return moment.hour * 3600 + moment.minute * 60 + moment.second


class MomentsTest(MomentCliTestCase):
    """Verify date parsing, formatting, and calendar adjustments."""

    def test_iso_format_is_the_default(self):
        """The default output is an ISO 8601 timestamp."""
        result = self.run_cli("2026-08-11")
        self.assertIn("2026-08-11T", result.stdout)
        self.assertTrue(result.stdout.strip().endswith("+02:00"))

    def test_short_format_can_be_requested(self):
        """--short explicitly selects the default date format."""
        result = self.run_cli("2026-08-11T12:30:00+02:00", "--short")
        self.assertEqual(result.stdout, "2026-08-11\n")

    def test_long_format_fills_missing_time_with_now(self):
        """--long uses the current time of day when the input has no time."""
        result = self.run_cli("2026-08-11", "--long")
        output = datetime.strptime(result.stdout.strip(), "%Y-%m-%d %H:%M:%S")
        now = datetime.now(TimezoneResolver.default()).replace(tzinfo=None)
        self.assertEqual(output.date(), date(2026, 8, 11))
        self.assertLess(
            abs(self.seconds_of_day(output) - self.seconds_of_day(now)),
            120,
        )

    def test_long_format_preserves_input_time(self):
        """--long keeps the time of day from the input."""
        result = self.run_cli("2026-08-11T15:20:30+02:00", "--long")
        self.assertEqual(result.stdout, "2026-08-11 15:20:30\n")

    def test_iso_input_converts_to_iso_output(self):
        """ISO input is inferred and converted to an ISO timestamp."""
        result = self.run_cli("2026-08-11T12:30:00+02:00", "--iso")
        self.assertEqual(result.stdout, "2026-08-11T12:30:00+02:00\n")

    def test_epoch_input_converts_to_epoch_output(self):
        """Epoch seconds input is inferred and converted to epoch milliseconds."""
        result = self.run_cli("1786442400", "--epoch")
        self.assertEqual(result.stdout, "1786442400000\n")

    def test_time_first_slash_date_input(self):
        """HH:MM DD/MM/YYYY input is accepted."""
        self.assertEqual(
            MomentParser.resolve_datetime(
                raw="16:19 24/09/2026"
            ).strftime("%Y-%m-%d %H:%M"),
            "2026-09-24 16:19",
        )
        self.assertEqual(
            MomentParser.resolve_date(raw="16:19 24/09/2026"),
            "2026-09-24",
        )
        self.assertEqual(
            MomentParser.resolve_datetime(
                raw="08:05:30 01/01/2020"
            ).strftime("%Y-%m-%d %H:%M:%S"),
            "2020-01-01 08:05:30",
        )

    def test_time_first_slash_date_cli(self):
        """CLI accepts HH:MM DD/MM/YYYY and formats it."""
        result = self.run_cli("16:19 24/09/2026", "--long")
        self.assertEqual(result.stdout, "2026-09-24 16:19:00\n")

    def test_calendar_adjustments_clamp_month_end(self):
        """Calendar subtraction clamps dates that do not exist in the target month."""
        self.assertEqual(
            MomentParser.subtract_months(target="2026-03-31"),
            "2026-02-28",
        )
        self.assertEqual(
            MomentParser.subtract_years(target="2024-02-29"),
            "2023-02-28",
        )

    def test_format_options_are_mutually_exclusive(self):
        """The output format flags cannot be combined."""
        for flags in (
            ["--short", "--iso"],
            ["--long", "--iso"],
            ["--long", "--epoch"],
        ):
            with self.subTest(flags=flags):
                result = subprocess.run(
                    [sys.executable,
                     str(Path(__file__).parents[1] / "moments.py"),
                     "2026-08-11", *flags],
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("not allowed with", result.stderr)

    def test_old_adjustment_options_are_removed(self):
        """The former adjustment option names are no longer accepted."""
        for option in ("--day", "--week", "--month", "--year", "--tomorrow",
                       "--prev", "--subtract-day", "--subtract-week",
                       "--subtract-month", "--subtract-year", "--add-day",
                       "--add-week", "--add-month", "--add-year"):
            with self.subTest(option=option):
                result = subprocess.run(
                    [sys.executable,
                     str(Path(__file__).parents[1] / "moments.py"), option],
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(result.returncode, 0)

    def test_timezone_is_dst_aware(self):
        """Europe/Paris uses its winter +01:00 offset."""
        result = self.run_cli("2026-01-15T12:00:00Z", "--iso")
        self.assertEqual(result.stdout, "2026-01-15T13:00:00+01:00\n")

    def test_timezone_can_be_selected_and_invalid_names_are_rejected(self):
        """--tz selects an IANA timezone and rejects unknown names."""
        self.assertEqual(
            self.run_cli(
                "2026-01-15T12:00:00Z", "--tz", "UTC", "--iso"
            ).stdout,
            "2026-01-15T12:00:00+00:00\n",
        )
        result = subprocess.run(
            [sys.executable, str(Path(__file__).parents[1] / "moments.py"),
             "2026-01-15", "--tz", "Not/A_Timezone"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("unknown timezone", result.stderr)

    def test_help_lists_common_timezones(self):
        """Help output lists examples of valid --tz values."""
        result = self.run_cli("--help")
        self.assertIn("Europe/Paris", result.stdout)
        self.assertIn("America/New_York", result.stdout)

    def test_help_is_available_after_date(self):
        """Help works after the optional date argument too."""
        result = self.run_cli("2026-08-11", "-h")
        self.assertIn("--tz TZ", result.stdout)

    def test_utc_format_and_custom_format(self):
        """--utc converts output and --format supports strftime directives."""
        self.assertEqual(
            self.run_cli(
                "2026-01-15T12:00:00+01:00", "--utc", "--long"
            ).stdout,
            "2026-01-15 11:00:00\n",
        )
        self.assertEqual(
            self.run_cli("2026-08-11", "--format", "%Y/%m/%d").stdout,
            "2026/08/11\n",
        )

    def test_weekday_and_week_number_formats(self):
        """The weekday and ISO week number formats are available."""
        self.assertEqual(
            self.run_cli("2026-08-11", "--weekday").stdout, "Tuesday\n"
        )
        self.assertEqual(
            self.run_cli("2026-08-11", "--week-number").stdout, "33\n"
        )

    def test_json_output_contains_resolved_moment_fields(self):
        """JSON output includes local, UTC, epoch, and calendar fields."""
        output = json.loads(self.run_cli("2026-01-15", "--json").stdout)
        self.assertEqual(output["input"], "2026-01-15")
        self.assertEqual(output["tz"], "Europe/Paris")
        self.assertEqual(output["local"][-6:], "+01:00")
        self.assertEqual(output["weekday"], "Thursday")
        self.assertEqual(output["week_number"], 3)

    def test_application_accepts_explicit_argv(self):
        """The Application entry point is testable with an explicit argv."""
        stdout = io.StringIO()
        app = Application(
            argv=["2026-08-11", "--short"],
            console=Console(stdout=stdout),
        )
        self.assertEqual(app.run(), 0)
        self.assertEqual(stdout.getvalue(), "2026-08-11\n")


class RelativeTimeTest(MomentCliTestCase):
    """Verify --from relative time computation."""

    def test_exact_years(self):
        """Ten full years between two identical month-day dates."""
        target = datetime(2026, 9, 8, 0, 0, 0, tzinfo=TimezoneResolver.default())
        from_dt = datetime(2016, 9, 8, 0, 0, 0, tzinfo=TimezoneResolver.default())
        self.assertEqual(
            RelativeTimeFormatter.format(target=target, origin=from_dt),
            "10 years",
        )

    def test_exact_years_short(self):
        """--short omits time components for exact years."""
        target = datetime(2026, 9, 8, 12, 0, 0, tzinfo=TimezoneResolver.default())
        from_dt = datetime(2016, 9, 8, 0, 0, 0, tzinfo=TimezoneResolver.default())
        self.assertEqual(
            RelativeTimeFormatter.format(
                target=target, origin=from_dt, short=True
            ),
            "10 years",
        )

    def test_months_and_days(self):
        """Month and day components with --short."""
        target = datetime(2026, 2, 10, tzinfo=TimezoneResolver.default())
        from_dt = datetime(2026, 1, 1, tzinfo=TimezoneResolver.default())
        self.assertEqual(
            RelativeTimeFormatter.format(
                target=target, origin=from_dt, short=True
            ),
            "1 month 9 days",
        )

    def test_full_precision_with_time(self):
        """Years, hours, minutes, seconds without --short."""
        target = datetime(
            2026, 9, 8, 12, 30, 30, tzinfo=TimezoneResolver.default()
        )
        from_dt = datetime(
            2025, 9, 8, 0, 0, 0, tzinfo=TimezoneResolver.default()
        )
        self.assertEqual(
            RelativeTimeFormatter.format(target=target, origin=from_dt),
            "1 year 12 hours 30 minutes 30 seconds",
        )

    def test_full_precision_with_explicit_time(self):
        """Both target and from have explicit times."""
        target = datetime(
            2026, 9, 8, 12, 30, 30, tzinfo=TimezoneResolver.default()
        )
        from_dt = datetime(
            2025, 9, 8, 10, 15, 15, tzinfo=TimezoneResolver.default()
        )
        self.assertEqual(
            RelativeTimeFormatter.format(target=target, origin=from_dt),
            "1 year 2 hours 15 minutes 15 seconds",
        )

    def test_zero_difference(self):
        """Identical dates produce '0'."""
        moment = datetime(2026, 1, 1, tzinfo=TimezoneResolver.default())
        self.assertEqual(
            RelativeTimeFormatter.format(target=moment, origin=moment),
            "0",
        )
        self.assertEqual(
            RelativeTimeFormatter.format(
                target=moment, origin=moment, short=True
            ),
            "0",
        )

    def test_singular_forms(self):
        """Singular year, month, day, hour, minute, second."""
        target = datetime(
            2027, 1, 1, 0, 0, 0, tzinfo=TimezoneResolver.default()
        )
        from_dt = datetime(
            2026, 12, 31, 23, 59, 59, tzinfo=TimezoneResolver.default()
        )
        self.assertEqual(
            RelativeTimeFormatter.format(target=target, origin=from_dt),
            "1 second",
        )

    def test_negative_when_reversed(self):
        """When target < from, the result is prefixed with '-'."""
        target = datetime(2026, 1, 1, tzinfo=TimezoneResolver.default())
        from_dt = datetime(2027, 1, 1, tzinfo=TimezoneResolver.default())
        self.assertEqual(
            RelativeTimeFormatter.format(target=target, origin=from_dt),
            "-1 year",
        )

    def test_cli_from_with_short(self):
        """CLI --from with --short on exact dates."""
        result = self.run_cli(
            "2026-02-10", "--short", "--from", "2026-01-01"
        )
        self.assertEqual(result.stdout, "1 month 9 days\n")

    def test_cli_from_without_short(self):
        """CLI --from without --short includes time components."""
        result = self.run_cli(
            "2026-09-08T12:30:30+02:00",
            "--from", "2025-09-08T00:00:00+02:00",
        )
        self.assertEqual(
            result.stdout, "1 year 12 hours 30 minutes 30 seconds\n"
        )

    def test_cli_from_rejects_bad_date(self):
        """CLI --from with an invalid date exits with code 1."""
        result = subprocess.run(
            [sys.executable, str(Path(__file__).parents[1] / "moments.py"),
             "--from", "not-a-date"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR", result.stderr)


if __name__ == "__main__":
    unittest.main()
