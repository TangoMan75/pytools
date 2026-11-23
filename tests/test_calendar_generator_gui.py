#!/usr/bin/env python3
"""Tests for the CalendarGeneratorGUI class in calendar_generator module."""

import csv
import os
import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parents[1]))

from calendar_generator import (  # noqa: E402
    CalendarGeneratorApp,
    CalendarGeneratorGUI,
    CalendarValidator,
)


#--------------------------------------------------
# Test helpers
#--------------------------------------------------


class _FakeStringVar:
    """Lightweight stand-in for tkinter.StringVar."""

    def __init__(self, value=""):
        self._value = value

    def get(self):
        """Return the stored string value."""
        return self._value

    def set(self, value):
        """Replace the stored string value."""
        self._value = value


class _FakeDateEntry:
    """Lightweight stand-in for tkcalendar.DateEntry."""

    instances = []

    def __init__(self, *args, **kwargs):  # noqa: ARG001
        self._date = date.today()
        _FakeDateEntry.instances.append(self)

    def grid(self, *args, **kwargs):
        """No-op grid layout call (the window is never shown)."""

    def set_date(self, value):
        """Record the selected date."""
        self._date = value

    def get_date(self):
        """Return the selected date."""
        return self._date


class FakeGuiBuilder:
    """Build a CalendarGeneratorGUI backed by mocked toolkit modules."""

    @staticmethod
    def build():
        """Return a GUI instance and the mocks it was built with.

        Every widget method that would touch the display is replaced with a
        ``MagicMock`` so the window never opens.
        """
        _FakeDateEntry.instances = []

        fake_tk = MagicMock()
        fake_tk.StringVar.side_effect = _FakeStringVar
        fake_ttk = MagicMock()
        fake_filedialog = MagicMock()
        fake_messagebox = MagicMock()

        modules = (
            fake_tk, fake_ttk, fake_filedialog, fake_messagebox, _FakeDateEntry,
        )
        gui = CalendarGeneratorGUI(modules=modules)
        return gui, fake_tk, fake_filedialog, fake_messagebox, _FakeDateEntry


#--------------------------------------------------
#  --gui flag
#--------------------------------------------------


class TestGuiFlag(unittest.TestCase):
    """Tests for the --gui flag in the CLI."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    def test_gui_flag_launches_gui(self):
        """Test --gui calls CalendarGeneratorGUI().run() and exits early."""
        app = CalendarGeneratorApp(
            author="TangoMan75", title="t", description="d",
        )
        with patch.object(sys, "argv", ["script", "--gui"]):
            with patch.object(
                CalendarGeneratorApp, "_launch_gui"
            ) as mock_launch:
                app.run()
                mock_launch.assert_called_once()

    def test_gui_flag_does_not_require_input(self):
        """Test --gui works without the positional input argument."""
        app = CalendarGeneratorApp(
            author="TangoMan75", title="t", description="d",
        )
        with patch.object(sys, "argv", ["script", "--gui"]):
            with patch.object(
                CalendarGeneratorApp, "_launch_gui"
            ) as mock_launch:
                try:
                    app.run()
                except SystemExit:
                    pass
                mock_launch.assert_called_once()

    def test_no_gui_flag_does_not_launch_gui(self):
        """Test the GUI is not launched when --gui is absent."""
        app = CalendarGeneratorApp(
            author="TangoMan75", title="t", description="d",
        )
        with patch.object(sys, "argv", [
            "script", "--start", "2024-01-01", "--end", "2024-01-05",
        ]):
            with patch.object(
                CalendarGeneratorApp, "_launch_gui"
            ) as mock_launch:
                app.run()
                mock_launch.assert_not_called()


#--------------------------------------------------
# CalendarGeneratorGUI
#--------------------------------------------------


class TestCalendarGeneratorGUIInit(unittest.TestCase):
    """Tests for CalendarGeneratorGUI construction."""

    def test_init_creates_root_window(self):
        """Test __init__ creates a Tk root window with the right title."""
        _gui, fake_tk, *_ = FakeGuiBuilder.build()
        fake_tk.Tk.assert_called_once()
        self.assertEqual(
            fake_tk.Tk.return_value.title.call_args.args[0],
            "TangoMan Calendar Generator",
        )

    def test_init_creates_two_date_pickers(self):
        """Test __init__ creates one DateEntry for start and one for end."""
        _gui, *_ = FakeGuiBuilder.build()
        self.assertEqual(len(_FakeDateEntry.instances), 2)

    def test_init_sets_default_name(self):
        """Test the calendar name field is pre-filled with the default name."""
        gui, *_ = FakeGuiBuilder.build()
        self.assertEqual(gui.name_var.get(), "TangoMan")

    def test_init_sets_default_am_times(self):
        """Test the AM time fields are pre-filled with the defaults."""
        gui, *_ = FakeGuiBuilder.build()
        self.assertEqual(gui.am_from_var.get(), "09:00")
        self.assertEqual(gui.am_to_var.get(), "13:00")

    def test_init_sets_default_pm_times(self):
        """Test the PM time fields are pre-filled with the defaults."""
        gui, *_ = FakeGuiBuilder.build()
        self.assertEqual(gui.pm_from_var.get(), "14:00")
        self.assertEqual(gui.pm_to_var.get(), "18:00")

    def test_init_sets_start_date_to_today(self):
        """Test the start date picker is set to today's date."""
        gui, *_ = FakeGuiBuilder.build()
        self.assertEqual(gui.start_picker.get_date(), date.today())

    def test_init_sets_end_date_to_next_month(self):
        """Test the end date picker is set to the first day of next month."""
        gui, *_ = FakeGuiBuilder.build()
        self.assertEqual(
            gui.end_picker.get_date(),
            CalendarValidator.next_month(date.today()),
        )


class TestCalendarGeneratorGUIGenerate(unittest.TestCase):
    """Tests for CalendarGeneratorGUI.on_generate."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)
        self.gui, self._tk, self._filedialog, self._messagebox, _ = FakeGuiBuilder.build()
        self.output_path = Path(self.test_dir) / "gui_out.csv"

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    def test_writes_csv_when_user_picks_path(self):
        """Test on_generate writes the CSV when the user picks a path."""
        self._filedialog.asksaveasfilename.return_value = str(self.output_path)
        self.gui.on_generate()
        self.assertTrue(self.output_path.exists())
        self._messagebox.showinfo.assert_called_once()
        self.assertIn(str(self.output_path), self.gui.status_var.get())

    def test_aborts_when_user_cancels_save_dialog(self):
        """Test on_generate does nothing when the user cancels the dialog."""
        self._filedialog.asksaveasfilename.return_value = ""
        self.gui.on_generate()
        self.assertFalse(self.output_path.exists())
        self._messagebox.showinfo.assert_not_called()

    def test_rejects_start_after_end(self):
        """Test on_generate shows an error when start >= end."""
        self.gui.start_picker.set_date(date(2024, 12, 31))
        self.gui.end_picker.set_date(date(2024, 1, 1))
        self.gui.on_generate()
        self._messagebox.showerror.assert_called_once()
        self._filedialog.asksaveasfilename.assert_not_called()

    def test_rejects_equal_start_and_end(self):
        """Test on_generate shows an error when start == end."""
        self.gui.start_picker.set_date(date(2024, 6, 15))
        self.gui.end_picker.set_date(date(2024, 6, 15))
        self.gui.on_generate()
        self._messagebox.showerror.assert_called_once()
        self._filedialog.asksaveasfilename.assert_not_called()

    def test_falls_back_to_default_name_when_empty(self):
        """Test an empty name field uses the default TangoMan calendar name."""
        self.gui.name_var.set("")
        self._filedialog.asksaveasfilename.return_value = str(self.output_path)
        self.gui.on_generate()
        with open(self.output_path, encoding="utf-8", newline="") as f:
            reader = list(csv.reader(f))
        self.assertEqual(reader[1][0], "TangoMan")

    def test_invalid_time_falls_back_to_default(self):
        """Test invalid HH:MM inputs are replaced by the CLI defaults."""
        self.gui.am_from_var.set("bad")
        self.gui.pm_to_var.set("99:99")
        self._filedialog.asksaveasfilename.return_value = str(self.output_path)
        self.gui.on_generate()
        with open(self.output_path, encoding="utf-8", newline="") as f:
            reader = list(csv.reader(f))
        self.assertEqual(reader[1][2], "09:00")
        self.assertEqual(reader[2][4], "18:00")

    def test_propagates_address_to_location_column(self):
        """Test the address form value lands in the Location column."""
        self.gui.address_var.set("Office")
        self._filedialog.asksaveasfilename.return_value = str(self.output_path)
        self.gui.on_generate()
        with open(self.output_path, encoding="utf-8", newline="") as f:
            reader = list(csv.reader(f))
        self.assertEqual(reader[1][6], "Office")

    def test_save_dialog_initialfile_uses_snake_case_name(self):
        """Test the save dialog is pre-filled with the snake_case calendar name."""
        self.gui.name_var.set("StandUp")
        self._filedialog.asksaveasfilename.return_value = str(self.output_path)
        self.gui.on_generate()
        _, kwargs = self._filedialog.asksaveasfilename.call_args
        self.assertEqual(kwargs["initialfile"], "standup.csv")

    def test_save_dialog_initialfile_falls_back_to_default_calendar(self):
        """Test the save dialog initialfile uses the default calendar name when empty."""
        self.gui.name_var.set("")
        self._filedialog.asksaveasfilename.return_value = str(self.output_path)
        self.gui.on_generate()
        _, kwargs = self._filedialog.asksaveasfilename.call_args
        self.assertEqual(kwargs["initialfile"], "tangoman.csv")


class TestCalendarGeneratorGUIRun(unittest.TestCase):
    """Tests for CalendarGeneratorGUI.run."""

    def test_run_starts_mainloop(self):
        """Test run() calls Tk.mainloop exactly once."""
        gui, fake_tk, *_ = FakeGuiBuilder.build()
        gui.run()
        fake_tk.Tk.return_value.mainloop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
