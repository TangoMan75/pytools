#!/usr/bin/env python3
"""Tests for calendar_generator module."""

import csv
import os
import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))

from calendar_generator import (  # noqa: E402
    CalendarGenerator,
    CalendarGeneratorApp,
    CalendarValidator,
)


#--------------------------------------------------
# CalendarGenerator
#--------------------------------------------------


class TestCalendarGeneratorWorkingDays(unittest.TestCase):
    """Tests for CalendarGenerator.working_days iterator."""

    def test_yields_each_working_day_in_range(self):
        """Test iterator yields Mon-Fri only, skipping Saturday and Sunday."""
        generator = CalendarGenerator(
            name="X", address="", start=date(2024, 1, 1), end=date(2024, 1, 10),
            am_from="09:00", am_to="13:00", pm_from="14:00", pm_to="18:00",
        )
        days = list(generator.working_days())
        # 2024-01-01 (Mon) to 2024-01-10 (Wed): Mon-Fri of week 1, Mon-Wed of week 2
        self.assertEqual(
            [d.isoformat() for d in days],
            [
                "2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05",
                "2024-01-08", "2024-01-09", "2024-01-10",
            ],
        )

    def test_skips_weekend_days(self):
        """Test Saturday and Sunday are excluded."""
        generator = CalendarGenerator(
            name="X", address="", start=date(2024, 1, 6), end=date(2024, 1, 7),
            am_from="09:00", am_to="13:00", pm_from="14:00", pm_to="18:00",
        )
        self.assertEqual(list(generator.working_days()), [])

    def test_single_working_day(self):
        """Test a single working day yields exactly one entry."""
        generator = CalendarGenerator(
            name="X", address="", start=date(2024, 1, 1), end=date(2024, 1, 1),
            am_from="09:00", am_to="13:00", pm_from="14:00", pm_to="18:00",
        )
        days = list(generator.working_days())
        self.assertEqual(len(days), 1)
        self.assertEqual(days[0], date(2024, 1, 1))


class TestCalendarGeneratorGenerateRows(unittest.TestCase):
    """Tests for CalendarGenerator.generate_rows."""

    def test_emits_two_rows_per_working_day(self):
        """Test each working day produces an AM and a PM row."""
        generator = CalendarGenerator(
            name="MyCal", address="Home", start=date(2024, 1, 1), end=date(2024, 1, 2),
            am_from="09:00", am_to="13:00", pm_from="14:00", pm_to="18:00",
        )
        rows = generator.generate_rows()
        self.assertEqual(len(rows), 4)

    def test_row_uses_configured_values(self):
        """Test rows reflect the configured name, address and time slots."""
        generator = CalendarGenerator(
            name="MyCal", address="Office", start=date(2024, 1, 1), end=date(2024, 1, 1),
            am_from="08:00", am_to="12:00", pm_from="13:30", pm_to="17:30",
        )
        rows = generator.generate_rows()
        self.assertEqual(
            rows[0],
            ["MyCal", "2024-01-01", "08:00", "2024-01-01", "12:00", "", "Office"],
        )
        self.assertEqual(
            rows[1],
            ["MyCal", "2024-01-01", "13:30", "2024-01-01", "17:30", "", "Office"],
        )

    def test_empty_when_range_only_contains_weekend(self):
        """Test no rows are emitted when the range is a weekend only."""
        generator = CalendarGenerator(
            name="X", address="", start=date(2024, 1, 6), end=date(2024, 1, 7),
            am_from="09:00", am_to="13:00", pm_from="14:00", pm_to="18:00",
        )
        self.assertEqual(generator.generate_rows(), [])


class TestCalendarGeneratorWriteCsv(unittest.TestCase):
    """Tests for CalendarGenerator.write_csv."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.output_path = Path(self.test_dir) / "out.csv"

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_writes_header_and_rows(self):
        """Test the file is created with the CSV header followed by data rows."""
        generator = CalendarGenerator(
            name="MyCal", address="Home", start=date(2024, 1, 1), end=date(2024, 1, 1),
            am_from="09:00", am_to="13:00", pm_from="14:00", pm_to="18:00",
        )
        count = generator.write_csv(self.output_path)
        self.assertEqual(count, 2)
        with open(self.output_path, encoding="utf-8", newline="") as f:
            reader = list(csv.reader(f))
        self.assertEqual(reader[0], CalendarGenerator.CSV_HEADERS)
        self.assertEqual(len(reader), 3)  # 1 header + 2 rows

    def test_creates_parent_directories(self):
        """Test parent directories are created when missing."""
        nested = Path(self.test_dir) / "a" / "b" / "out.csv"
        generator = CalendarGenerator(
            name="X", address="", start=date(2024, 1, 1), end=date(2024, 1, 1),
            am_from="09:00", am_to="13:00", pm_from="14:00", pm_to="18:00",
        )
        generator.write_csv(nested)
        self.assertTrue(nested.exists())

    def test_dry_run_does_not_create_file(self):
        """Test --dry-run does not write any file but still reports count."""
        generator = CalendarGenerator(
            name="X", address="", start=date(2024, 1, 1), end=date(2024, 1, 1),
            am_from="09:00", am_to="13:00", pm_from="14:00", pm_to="18:00",
        )
        count = generator.write_csv(self.output_path, dry_run=True)
        self.assertEqual(count, 2)
        self.assertFalse(self.output_path.exists())


#--------------------------------------------------
# CalendarValidator
#--------------------------------------------------


class TestCalendarValidatorParseDate(unittest.TestCase):
    """Tests for CalendarValidator.parse_date."""

    def test_valid_iso_date(self):
        """Test a valid YYYY-MM-DD string is parsed."""
        self.assertEqual(
            CalendarValidator.parse_date("2024-06-15", default=date(2024, 1, 1)),
            date(2024, 6, 15),
        )

    def test_invalid_string_returns_default(self):
        """Test an unparseable string falls back to the default."""
        self.assertEqual(
            CalendarValidator.parse_date("not-a-date", default=date(2024, 1, 1)),
            date(2024, 1, 1),
        )

    def test_empty_string_returns_default(self):
        """Test an empty string falls back to the default."""
        self.assertEqual(
            CalendarValidator.parse_date("", default=date(2024, 1, 1)),
            date(2024, 1, 1),
        )

    def test_none_returns_default(self):
        """Test None falls back to the default."""
        self.assertEqual(
            CalendarValidator.parse_date(None, default=date(2024, 1, 1)),
            date(2024, 1, 1),
        )

    def test_wrong_format_returns_default(self):
        """Test a non-ISO format falls back to the default."""
        self.assertEqual(
            CalendarValidator.parse_date("15/06/2024", default=date(2024, 1, 1)),
            date(2024, 1, 1),
        )

    def test_invalid_calendar_date_returns_default(self):
        """Test a well-formed but impossible date falls back to the default."""
        self.assertEqual(
            CalendarValidator.parse_date("2024-13-45", default=date(2024, 1, 1)),
            date(2024, 1, 1),
        )


class TestCalendarValidatorParseTime(unittest.TestCase):
    """Tests for CalendarValidator.parse_time."""

    def test_valid_time(self):
        """Test a valid HH:MM string is returned as-is."""
        self.assertEqual(
            CalendarValidator.parse_time(
                "09:30", default=CalendarGenerator.DEFAULT_AM_FROM
            ),
            "09:30",
        )

    def test_invalid_format_returns_default(self):
        """Test an invalid format falls back to the default."""
        self.assertEqual(
            CalendarValidator.parse_time(
                "9:30", default=CalendarGenerator.DEFAULT_AM_FROM
            ),
            CalendarGenerator.DEFAULT_AM_FROM,
        )

    def test_out_of_range_hour_returns_default(self):
        """Test an out-of-range hour falls back to the default."""
        self.assertEqual(
            CalendarValidator.parse_time(
                "25:00", default=CalendarGenerator.DEFAULT_AM_FROM
            ),
            CalendarGenerator.DEFAULT_AM_FROM,
        )

    def test_out_of_range_minute_returns_default(self):
        """Test an out-of-range minute falls back to the default."""
        self.assertEqual(
            CalendarValidator.parse_time(
                "09:99", default=CalendarGenerator.DEFAULT_AM_FROM
            ),
            CalendarGenerator.DEFAULT_AM_FROM,
        )

    def test_empty_returns_default(self):
        """Test an empty string falls back to the default."""
        self.assertEqual(
            CalendarValidator.parse_time(
                "", default=CalendarGenerator.DEFAULT_AM_FROM
            ),
            CalendarGenerator.DEFAULT_AM_FROM,
        )


class TestCalendarValidatorNextMonth(unittest.TestCase):
    """Tests for CalendarValidator.next_month."""

    def test_mid_month(self):
        """Test a regular month returns the first of the next month."""
        self.assertEqual(
            CalendarValidator.next_month(date(2024, 6, 15)),
            date(2024, 7, 1),
        )

    def test_december_wraps_to_next_year(self):
        """Test December rolls over to January of the following year."""
        self.assertEqual(
            CalendarValidator.next_month(date(2024, 12, 15)),
            date(2025, 1, 1),
        )

    def test_january(self):
        """Test January returns the first of February."""
        self.assertEqual(
            CalendarValidator.next_month(date(2024, 1, 31)),
            date(2024, 2, 1),
        )


#--------------------------------------------------
# CalendarGeneratorApp CLI
#--------------------------------------------------


class TestCalendarGeneratorAppParser(unittest.TestCase):
    """Tests for the calendar generator argument parser."""

    def setUp(self):
        self.app = CalendarGeneratorApp(
            author="TangoMan75",
            title="TangoMan Calendar Generator",
            description="Generate a Google Calendar-compatible CSV.",
        )

    def test_input_is_optional(self):
        """Test the positional input argument is optional."""
        parser = self.app.build_parser()
        args = parser.parse_args([])
        self.assertFalse(hasattr(args, "input"))

    def test_default_values(self):
        """Test default values for name, times and dates."""
        parser = self.app.build_parser()
        args = parser.parse_args([])
        self.assertEqual(args.name, CalendarGenerator.DEFAULT_NAME)
        self.assertEqual(args.am_from, CalendarGenerator.DEFAULT_AM_FROM)
        self.assertEqual(args.am_to, CalendarGenerator.DEFAULT_AM_TO)
        self.assertEqual(args.pm_from, CalendarGenerator.DEFAULT_PM_FROM)
        self.assertEqual(args.pm_to, CalendarGenerator.DEFAULT_PM_TO)
        self.assertIsNone(args.output)

    def test_custom_options(self):
        """Test all options are parsed from the CLI."""
        parser = self.app.build_parser()
        args = parser.parse_args([
            "--name", "Work",
            "--address", "1 Rue de la Paix",
            "--start", "2024-01-01",
            "--end", "2024-12-31",
            "--am-from", "08:00",
            "--am-to", "12:00",
            "--pm-from", "13:00",
            "--pm-to", "17:00",
            "--output", "cal.csv",
        ])
        self.assertEqual(args.name, "Work")
        self.assertEqual(args.address, "1 Rue de la Paix")
        self.assertEqual(args.start, "2024-01-01")
        self.assertEqual(args.end, "2024-12-31")
        self.assertEqual(args.am_from, "08:00")
        self.assertEqual(args.am_to, "12:00")
        self.assertEqual(args.pm_from, "13:00")
        self.assertEqual(args.pm_to, "17:00")
        self.assertEqual(args.output, "cal.csv")

    def test_inherits_framework_flags(self):
        """Test the framework flags are still available."""
        parser = self.app.build_parser()
        args = parser.parse_args([
            "--start", "2024-01-01",
            "--end", "2024-01-10",
            "--dry-run",
            "--verbose",
        ])
        self.assertTrue(args.dry_run)
        self.assertEqual(args.verbose, 1)


class TestCalendarGeneratorAppRun(unittest.TestCase):
    """Integration tests for CalendarGeneratorApp.run."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)
        self.app = CalendarGeneratorApp(
            author="TangoMan75",
            title="TangoMan Calendar Generator",
            description="Test.",
        )

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    def test_writes_default_calendar_file(self):
        """Test the default behavior writes tangoman.csv in the cwd."""
        with patch.object(sys, "argv", ["script", "--start", "2024-01-01", "--end", "2024-01-05"]):
            self.app.run()
        self.assertTrue(Path("tangoman.csv").exists())

    def test_writes_to_output_argument(self):
        """Test --output writes to the specified path."""
        with patch.object(sys, "argv", [
            "script", "--start", "2024-01-01", "--end", "2024-01-05",
            "--output", "custom.csv",
        ]):
            self.app.run()
        self.assertTrue(Path("custom.csv").exists())
        self.assertFalse(Path("tangoman.csv").exists())

    def test_dry_run_does_not_create_file(self):
        """Test --dry-run skips the actual file write."""
        with patch.object(sys, "argv", [
            "script", "--start", "2024-01-01", "--end", "2024-01-05",
            "--dry-run",
        ]):
            self.app.run()
        self.assertFalse(Path("tangoman.csv").exists())
        self.assertFalse(Path(CalendarGenerator.DEFAULT_OUTPUT).exists())

    def test_custom_name_and_address(self):
        """Test the --name and --address flags are propagated to the CSV."""
        with patch.object(sys, "argv", [
            "script", "--start", "2024-01-01", "--end", "2024-01-02",
            "--name", "CustomCal", "--address", "Office",
        ]):
            self.app.run()
        with open("customcal.csv", encoding="utf-8", newline="") as f:
            reader = list(csv.reader(f))
        self.assertEqual(reader[1][0], "CustomCal")
        self.assertEqual(reader[1][6], "Office")

    def test_default_filename_uses_snake_case_name(self):
        """Test the default filename is the calendar name in lower_snake_case."""
        with patch.object(sys, "argv", [
            "script", "--name", "My Calendar",
            "--start", "2024-01-01", "--end", "2024-01-02",
        ]):
            self.app.run()
        self.assertTrue(Path("my_calendar.csv").exists())

    def test_invalid_date_falls_back_to_defaults(self):
        """Test an invalid --start string falls back to the default (today)."""
        with patch.object(sys, "argv", [
            "script", "--start", "invalid", "--end", "2099-12-31",
        ]):
            self.app.run()
        self.assertTrue(Path("tangoman.csv").exists())

    def test_rejects_start_after_end(self):
        """Test the script reports an invalid date range without writing."""
        with patch.object(sys, "argv", [
            "script", "--start", "2024-12-31", "--end", "2024-01-01",
        ]):
            self.app.run()
        self.assertFalse(Path("tangoman.csv").exists())

    def test_rejects_equal_start_and_end(self):
        """Test the script reports an equal date range without writing."""
        with patch.object(sys, "argv", [
            "script", "--start", "2024-06-15", "--end", "2024-06-15",
        ]):
            self.app.run()
        self.assertFalse(Path("tangoman.csv").exists())


#--------------------------------------------------
# Class constants
#--------------------------------------------------


class TestClassConstants(unittest.TestCase):
    """Tests for the constants owned by CalendarGenerator."""

    def test_csv_headers(self):
        """Test the CSV header row matches the Google Calendar layout."""
        self.assertEqual(
            CalendarGenerator.CSV_HEADERS,
            [
                "Subject", "Start Date", "Start Time",
                "End Date", "End Time", "Description", "Location",
            ],
        )

    def test_default_calendar_name(self):
        """Test the default calendar name is 'TangoMan'."""
        self.assertEqual(CalendarGenerator.DEFAULT_NAME, "TangoMan")

    def test_default_time_ranges(self):
        """Test the default AM/PM time ranges match the original bash script."""
        self.assertEqual(CalendarGenerator.DEFAULT_AM_FROM, "09:00")
        self.assertEqual(CalendarGenerator.DEFAULT_AM_TO, "13:00")
        self.assertEqual(CalendarGenerator.DEFAULT_PM_FROM, "14:00")
        self.assertEqual(CalendarGenerator.DEFAULT_PM_TO, "18:00")

    def test_default_output_filename_is_fallback(self):
        """Test the default output filename is the empty-name fallback."""
        self.assertEqual(CalendarGenerator.DEFAULT_OUTPUT, "calendar.csv")


#--------------------------------------------------
# CalendarValidator.to_snake_case
#--------------------------------------------------


class TestCalendarValidatorToSnakeCase(unittest.TestCase):
    """Tests for CalendarValidator.to_snake_case."""

    def test_camel_case(self):
        """Test CamelCase is converted to snake_case."""
        self.assertEqual(CalendarValidator.to_snake_case("TangoMan"), "tangoman")

    def test_pascal_case(self):
        """Test PascalCase is converted to snake_case."""
        self.assertEqual(CalendarValidator.to_snake_case("StandUp"), "standup")

    def test_spaces_become_underscores(self):
        """Test spaces are replaced with underscores."""
        self.assertEqual(
            CalendarValidator.to_snake_case("My Calendar"),
            "my_calendar",
        )

    def test_hyphens_become_underscores(self):
        """Test hyphens are replaced with underscores."""
        self.assertEqual(
            CalendarValidator.to_snake_case("My-Calendar"),
            "my_calendar",
        )

    def test_special_characters_become_underscores(self):
        """Test punctuation and other non-alphanumeric chars become underscores."""
        self.assertEqual(
            CalendarValidator.to_snake_case("My-Calendar!"),
            "my_calendar",
        )

    def test_consecutive_separators_collapse(self):
        """Test runs of non-alphanumeric chars collapse to a single underscore."""
        self.assertEqual(
            CalendarValidator.to_snake_case("My   Calendar"),
            "my_calendar",
        )

    def test_leading_and_trailing_underscores_stripped(self):
        """Test leading and trailing underscores are removed."""
        self.assertEqual(
            CalendarValidator.to_snake_case("  My Calendar  "),
            "my_calendar",
        )

    def test_already_snake_case_is_unchanged(self):
        """Test an already snake_case string is returned lowercased."""
        self.assertEqual(
            CalendarValidator.to_snake_case("my_calendar"),
            "my_calendar",
        )

    def test_uppercase_input_is_lowercased(self):
        """Test an uppercase string is lowercased."""
        self.assertEqual(
            CalendarValidator.to_snake_case("TANGOMAN"),
            "tangoman",
        )

    def test_empty_string_falls_back_to_calendar(self):
        """Test an empty string falls back to 'calendar'."""
        self.assertEqual(CalendarValidator.to_snake_case(""), "calendar")

    def test_only_special_chars_falls_back_to_calendar(self):
        """Test a string of only special chars falls back to 'calendar'."""
        self.assertEqual(CalendarValidator.to_snake_case("!!!"), "calendar")

    def test_alphanumeric_with_underscores_preserved(self):
        """Test digits and underscores pass through correctly."""
        self.assertEqual(
            CalendarValidator.to_snake_case("Calendar 2024 v2"),
            "calendar_2024_v2",
        )


if __name__ == "__main__":
    unittest.main()
