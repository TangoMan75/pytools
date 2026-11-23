#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TangoMan Calendar Generator.

Generate a Google Calendar-compatible CSV with AM/PM time slots for every
working day (Monday-Friday) in a given date range.

A Tkinter front-end is also available via the ``--gui`` flag. The GUI
modules (``tkinter`` and ``tkcalendar``) are imported lazily so the CLI
stays usable on headless systems.

Usage:
    python3 calendar_generator.py [output_file] [options]
    python3 calendar_generator.py --gui
"""

import argparse
import csv
import re
import shlex
import sys
from datetime import date, datetime, timedelta
from pathlib import Path


#--------------------------------------------------
# CalendarGenerator: pure row-generation logic
#--------------------------------------------------


class CalendarGenerator:
    """Generate calendar CSV rows for working days in a date range."""

    DEFAULT_NAME = "TangoMan"
    DEFAULT_AM_FROM = "09:00"
    DEFAULT_AM_TO = "13:00"
    DEFAULT_PM_FROM = "14:00"
    DEFAULT_PM_TO = "18:00"
    DEFAULT_OUTPUT = "calendar.csv"

    CSV_HEADERS = [
        "Subject", "Start Date", "Start Time",
        "End Date", "End Time", "Description", "Location",
    ]

    WEEKEND = (5, 6)

    def __init__(
        self,
        *,
        name,
        address,
        start,
        end,
        am_from,
        am_to,
        pm_from,
        pm_to,
    ):
        self.name = name
        self.address = address
        self.start = start
        self.end = end
        self.am_from = am_from
        self.am_to = am_to
        self.pm_from = pm_from
        self.pm_to = pm_to

    def working_days(self):
        """Yield each working day (Mon-Fri) in [start, end] inclusive."""
        current = self.start
        while current <= self.end:
            if current.weekday() not in self.WEEKEND:
                yield current
            current += timedelta(days=1)

    def generate_rows(self):
        """Build the CSV rows: one AM entry and one PM entry per working day."""
        rows = []
        for day in self.working_days():
            iso = day.isoformat()
            rows.append([
                self.name, iso, self.am_from, iso, self.am_to, "", self.address,
            ])
            rows.append([
                self.name, iso, self.pm_from, iso, self.pm_to, "", self.address,
            ])
        return rows

    def write_csv(self, output_path, *, dry_run=False):
        """Write the generated rows to a CSV file and return the row count."""
        rows = self.generate_rows()
        if dry_run:
            Console.info(
                f"[DRY RUN] Would write {len(rows)} rows to: {output_path}\n"
            )
            return len(rows)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(self.CSV_HEADERS)
            writer.writerows(rows)
        Console.success(f"Wrote {len(rows)} rows to: {output_path}\n")
        return len(rows)


#--------------------------------------------------
# CalendarValidator: input validation helpers
#--------------------------------------------------


class CalendarValidator:
    """Validation helpers for calendar generator inputs."""

    DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

    @staticmethod
    def parse_date(value, *, default):
        """Return ``value`` parsed as YYYY-MM-DD, or ``default`` on failure."""
        if not value or not CalendarValidator.DATE_PATTERN.match(value):
            return default
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return default

    @staticmethod
    def parse_time(value, *, default):
        """Return ``value`` if it matches HH:MM, otherwise ``default``."""
        if value and CalendarValidator.TIME_PATTERN.match(value):
            return value
        return default

    @staticmethod
    def next_month(reference):
        """Return the first day of the month following ``reference``."""
        if reference.month == 12:
            return date(reference.year + 1, 1, 1)
        return date(reference.year, reference.month + 1, 1)

    @staticmethod
    def to_snake_case(value):
        """Convert ``value`` to lower_snake_case.

        Any run of non-alphanumeric characters is replaced by a single
        underscore, leading and trailing underscores are stripped, and
        the result is lowercased. Returns ``"calendar"`` when the input
        is empty or contains only non-alphanumeric characters.
        """
        cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", str(value))
        cleaned = cleaned.strip("_").lower()
        return cleaned or "calendar"


#--------------------------------------------------
# GuiLoader: lazy GUI imports
#--------------------------------------------------


class GuiLoader:
    """Import the GUI toolkit modules only when the GUI is requested."""

    @classmethod
    def load(cls):
        """Return the GUI modules, raising RuntimeError when unavailable."""
        try:
            import tkinter as tk
            from tkinter import filedialog, messagebox, ttk
        except ImportError as exc:
            raise RuntimeError(
                "tkinter is required to launch the GUI but is not available "
                "on this system."
            ) from exc

        try:
            from tkcalendar import DateEntry
        except ImportError as exc:
            raise RuntimeError(
                "tkcalendar is required to launch the GUI. Install it with "
                "'pip install tkcalendar'."
            ) from exc

        return tk, ttk, filedialog, messagebox, DateEntry


#--------------------------------------------------
# CalendarGeneratorGUI
#--------------------------------------------------


class CalendarGeneratorGUI:
    """Tkinter front-end for the TangoMan Calendar Generator."""

    def __init__(self, *, modules=None):
        modules = modules if modules is not None else GuiLoader.load()
        (
            self._tk,
            self._ttk,
            self._filedialog,
            self._messagebox,
            self._date_entry_cls,
        ) = modules
        self.root = self._tk.Tk()
        self.root.title("TangoMan Calendar Generator")
        self._build_widgets()
        self._set_defaults()

    def _set_defaults(self):
        """Pre-fill the form with the same defaults as the CLI."""
        today = date.today()
        self.name_var.set(CalendarGenerator.DEFAULT_NAME)
        self.start_picker.set_date(today)
        self.end_picker.set_date(CalendarValidator.next_month(today))
        self.am_from_var.set(CalendarGenerator.DEFAULT_AM_FROM)
        self.am_to_var.set(CalendarGenerator.DEFAULT_AM_TO)
        self.pm_from_var.set(CalendarGenerator.DEFAULT_PM_FROM)
        self.pm_to_var.set(CalendarGenerator.DEFAULT_PM_TO)

    def _build_widgets(self):
        """Build the main window widgets."""
        tk = self._tk
        ttk = self._ttk
        date_entry_cls = self._date_entry_cls

        main = ttk.Frame(self.root, padding=10)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="Calendar name:").grid(
            row=0, column=0, sticky="w", pady=4
        )
        self.name_var = tk.StringVar()
        ttk.Entry(main, textvariable=self.name_var, width=30).grid(
            row=0, column=1, sticky="ew", pady=4
        )

        ttk.Label(main, text="Address:").grid(
            row=1, column=0, sticky="w", pady=4
        )
        self.address_var = tk.StringVar()
        ttk.Entry(main, textvariable=self.address_var, width=30).grid(
            row=1, column=1, sticky="ew", pady=4
        )

        ttk.Label(main, text="Start date:").grid(
            row=2, column=0, sticky="w", pady=4
        )
        self.start_picker = date_entry_cls(
            main,
            width=12,
            background="darkblue",
            foreground="white",
            borderwidth=2,
            date_pattern="yyyy-mm-dd",
        )
        self.start_picker.grid(row=2, column=1, sticky="w", pady=4)

        ttk.Label(main, text="End date:").grid(
            row=3, column=0, sticky="w", pady=4
        )
        self.end_picker = date_entry_cls(
            main,
            width=12,
            background="darkblue",
            foreground="white",
            borderwidth=2,
            date_pattern="yyyy-mm-dd",
        )
        self.end_picker.grid(row=3, column=1, sticky="w", pady=4)

        ttk.Label(main, text="AM:").grid(
            row=4, column=0, sticky="w", pady=4
        )
        am_frame = ttk.Frame(main)
        am_frame.grid(row=4, column=1, sticky="w", pady=4)
        ttk.Label(am_frame, text="from").pack(side="left")
        self.am_from_var = tk.StringVar()
        ttk.Entry(am_frame, textvariable=self.am_from_var, width=8).pack(
            side="left", padx=4
        )
        ttk.Label(am_frame, text="to").pack(side="left")
        self.am_to_var = tk.StringVar()
        ttk.Entry(am_frame, textvariable=self.am_to_var, width=8).pack(
            side="left", padx=4
        )

        ttk.Label(main, text="PM:").grid(
            row=5, column=0, sticky="w", pady=4
        )
        pm_frame = ttk.Frame(main)
        pm_frame.grid(row=5, column=1, sticky="w", pady=4)
        ttk.Label(pm_frame, text="from").pack(side="left")
        self.pm_from_var = tk.StringVar()
        ttk.Entry(pm_frame, textvariable=self.pm_from_var, width=8).pack(
            side="left", padx=4
        )
        ttk.Label(pm_frame, text="to").pack(side="left")
        self.pm_to_var = tk.StringVar()
        ttk.Entry(pm_frame, textvariable=self.pm_to_var, width=8).pack(
            side="left", padx=4
        )

        button_frame = ttk.Frame(main)
        button_frame.grid(row=6, column=0, columnspan=2, pady=10)
        ttk.Button(
            button_frame, text="Generate", command=self.on_generate
        ).pack(side="left", padx=4)
        ttk.Button(
            button_frame, text="Quit", command=self.root.quit
        ).pack(side="left", padx=4)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(
            main, textvariable=self.status_var, foreground="blue"
        ).grid(row=7, column=0, columnspan=2, pady=4)

        main.columnconfigure(1, weight=1)

    def on_generate(self):
        """Handle the Generate button: validate, prompt for output, write CSV."""
        try:
            start = self.start_picker.get_date()
            end = self.end_picker.get_date()
        except (ValueError, TypeError) as exc:
            self._show_error(f"Invalid date: {exc}")
            return

        if start >= end:
            self._show_error(
                "Calendar cannot start later than (or on) the finishing date."
            )
            return

        am_from = CalendarValidator.parse_time(
            self.am_from_var.get(),
            default=CalendarGenerator.DEFAULT_AM_FROM,
        )
        am_to = CalendarValidator.parse_time(
            self.am_to_var.get(),
            default=CalendarGenerator.DEFAULT_AM_TO,
        )
        pm_from = CalendarValidator.parse_time(
            self.pm_from_var.get(),
            default=CalendarGenerator.DEFAULT_PM_FROM,
        )
        pm_to = CalendarValidator.parse_time(
            self.pm_to_var.get(),
            default=CalendarGenerator.DEFAULT_PM_TO,
        )

        name = self.name_var.get() or CalendarGenerator.DEFAULT_NAME
        output_path = self._filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"{CalendarValidator.to_snake_case(name)}.csv",
        )
        if not output_path:
            return

        try:
            generator = CalendarGenerator(
                name=name,
                address=self.address_var.get(),
                start=start,
                end=end,
                am_from=am_from,
                am_to=am_to,
                pm_from=pm_from,
                pm_to=pm_to,
            )
            count = generator.write_csv(Path(output_path))
        except (ValueError, OSError) as exc:
            self._show_error(str(exc))
            return

        self.status_var.set(f"Generated {count} rows in {output_path}")
        self._messagebox.showinfo(
            "Success", f"Generated {count} rows in {output_path}"
        )

    def _show_error(self, message):
        """Show an error in both a popup and the status bar."""
        self.status_var.set(f"Error: {message}")
        self._messagebox.showerror("Error", message)

    def run(self):
        """Start the Tkinter main loop."""
        self.root.mainloop()


#--------------------------------------------------
# Console: minimal semantic console output
#--------------------------------------------------


class Console:
    """Minimal semantic console output used by this standalone script."""

    quiet = False

    @staticmethod
    def primary(message):
        """Print general output."""
        print(message, end="")

    @staticmethod
    def info(message):
        """Print informational output."""
        print(message, end="")

    @staticmethod
    def success(message):
        """Print successful output."""
        print(message, end="")

    @staticmethod
    def error(message):
        """Print an error to stderr."""
        print(f"error: {message}", file=sys.stderr)


#--------------------------------------------------
# Logger: log file handling
#--------------------------------------------------


class Logger:
    """Minimal logger supporting the application's --log option."""

    def __init__(self, *, verbose=0):
        self.verbose = verbose
        script = Path(sys.argv[0]).resolve()
        log_dir = script.parent / "log"
        self.log_file = log_dir / f"{date.today().isoformat()}_{script.stem}.log"

    def print(self):
        """Print the current log file, if it exists."""
        if not self.log_file.exists():
            Console.error(f'"{self.log_file}" file not found.')
            return False
        print(self.log_file.read_text(encoding="utf-8"), end="")
        return True


#--------------------------------------------------
# Completion: bash completion script generator
#--------------------------------------------------


class Completion:
    """Bash completion script generator."""

    @staticmethod
    def classify_parser_actions(*, arg_parser):
        """Walk the parser actions and return ``(all_opts, categories)``."""
        all_opts = set()
        categories = {"boolean": [], "file": [], "glob": [], "verbose": []}
        file_keys = ("output", "file", "path", "dest")
        glob_keys = ("include", "exclude", "glob", "pattern")
        for action in arg_parser._actions:  # noqa: SLF001
            opts = action.option_strings
            if not opts:
                continue
            all_opts.update(opts)
            joined = " ".join(opts).lower()
            if action.nargs == 0 and action.const is True:
                categories["boolean"].extend(opts)
            if action.__class__.__name__ == "_CountAction":
                categories["verbose"].extend(opts)
            if any(key in joined for key in file_keys):
                categories["file"].extend(opts)
            if any(key in joined for key in glob_keys):
                categories["glob"].extend(opts)
        return all_opts, categories

    @staticmethod
    def render_completion_case(*, opt, kind):
        """Return the bash case branch for the given option kind."""
        bodies = {
            "boolean": "            COMPREPLY=()\n",
            "verbose": "            COMPREPLY=( $(compgen -W \"-v -vv -vvv\" -- \"${cur}\") )\n",
            "file": "            COMPREPLY=( $(compgen -f -- \"${cur}\") )\n",
            "glob": "            COMPREPLY=( $(compgen -G \"${cur}*\") )\n",
        }
        return f"        {opt})\n{bodies[kind]}            return 0\n            ;;\n"

    @staticmethod
    def render_completion_script(*, all_opts, categories, name):
        """Build the final bash completion script string."""
        blocks = []
        for kind, opts in categories.items():
            for opt in sorted(set(opts)):
                blocks.append(
                    Completion.render_completion_case(opt=opt, kind=kind)
                )
        option_case = "".join(blocks)
        completion_name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
        sorted_opts = sorted(
            all_opts, key=lambda opt: (not opt.startswith("--"), opt.lower())
        )
        opts_str = " ".join(sorted_opts)
        return f'''#!/bin/bash

_{completion_name}_completions()
{{
    local cur prev opts
    COMPREPLY=()
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"

    opts="{opts_str}"

    case "${{prev}}" in
{option_case}        *)
            COMPREPLY=( $(compgen -W "${{opts}}" -- "${{cur}}") )
            return 0
            ;;
    esac
}}

complete -f -F _{completion_name}_completions {shlex.quote(name)}
'''

    @staticmethod
    def generate(*, parser, name):
        """Return a bash completion script string for the given parser."""
        all_opts, categories = Completion.classify_parser_actions(
            arg_parser=parser
        )
        return Completion.render_completion_script(
            all_opts=all_opts,
            categories=categories,
            name=name,
        )


#--------------------------------------------------
# CalendarGeneratorApp: standalone CLI
#--------------------------------------------------


class CalendarGeneratorApp:
    """CLI application for the TangoMan Calendar Generator."""

    def __init__(self, *, author, title, description):
        self.author = author
        self.title = title
        self.description = description
        self.name = Path(sys.argv[0]).resolve().stem

    def build_parser(self):
        """Build and return the calendar command-line parser."""
        parser = argparse.ArgumentParser(description=self.description)
        parser.add_argument("--output", help="Output CSV file path")
        parser.add_argument(
            "--recursive", action="store_true", help=argparse.SUPPRESS
        )
        parser.add_argument("--include", help=argparse.SUPPRESS)
        parser.add_argument("--exclude", help=argparse.SUPPRESS)
        parser.add_argument(
            "--dry-run", action="store_true", help="Do not write the CSV"
        )
        parser.add_argument(
            "--verbose", "-v", action="count", default=0,
            help="Increase verbosity",
        )
        parser.add_argument(
            "--quiet", action="store_true",
            help="suppress non-error output; runtime errors are still reported",
        )
        parser.add_argument("--log", action="store_true", help="Print the log file")
        parser.add_argument(
            "--gui", action="store_true",
            help="Launch the graphical user interface (requires tkinter and tkcalendar)",
        )
        parser.add_argument(
            "--name",
            default=CalendarGenerator.DEFAULT_NAME,
            help=f"Calendar name (default: {CalendarGenerator.DEFAULT_NAME})",
        )
        parser.add_argument(
            "--address",
            default="",
            help="Address or location written to the Location column",
        )
        parser.add_argument(
            "--start",
            help="Start date in YYYY-MM-DD format (default: today)",
        )
        parser.add_argument(
            "--end",
            help="End date in YYYY-MM-DD format (default: first day of next month)",
        )
        parser.add_argument(
            "--am-from",
            default=CalendarGenerator.DEFAULT_AM_FROM,
            help=f"AM start time in HH:MM (default: {CalendarGenerator.DEFAULT_AM_FROM})",
        )
        parser.add_argument(
            "--am-to",
            default=CalendarGenerator.DEFAULT_AM_TO,
            help=f"AM end time in HH:MM (default: {CalendarGenerator.DEFAULT_AM_TO})",
        )
        parser.add_argument(
            "--pm-from",
            default=CalendarGenerator.DEFAULT_PM_FROM,
            help=f"PM start time in HH:MM (default: {CalendarGenerator.DEFAULT_PM_FROM})",
        )
        parser.add_argument(
            "--pm-to",
            default=CalendarGenerator.DEFAULT_PM_TO,
            help=f"PM end time in HH:MM (default: {CalendarGenerator.DEFAULT_PM_TO})",
        )
        parser.add_argument(
            "--completion", action="store_true",
            help="Print bash completion script to stdout and exit",
        )
        return parser

    def _launch_gui(self):
        """Build and run the Tkinter GUI."""
        CalendarGeneratorGUI().run()

    def run(self):
        """Run the calendar generator with parsed CLI arguments."""
        if "--completion" in sys.argv:
            print(Completion.generate(parser=self.build_parser(), name=self.name))
            return 0
        args = self.build_parser().parse_args()

        if args.gui:
            self._launch_gui()
            return 0

        logger = Logger(verbose=0 if args.quiet else args.verbose)
        Console.quiet = args.quiet
        if args.log:
            logger.print()
            return 0

        if args.verbose >= 1 and not args.quiet:
            Console.primary(f"{self.title}\n")

        today = date.today()
        start = CalendarValidator.parse_date(args.start, default=today)
        end = CalendarValidator.parse_date(
            args.end,
            default=CalendarValidator.next_month(today),
        )

        if start >= end:
            Console.error(
                "Calendar cannot start later than (or on) the finishing date."
            )
            return 1

        am_from = CalendarValidator.parse_time(
            args.am_from,
            default=CalendarGenerator.DEFAULT_AM_FROM,
        )
        am_to = CalendarValidator.parse_time(
            args.am_to,
            default=CalendarGenerator.DEFAULT_AM_TO,
        )
        pm_from = CalendarValidator.parse_time(
            args.pm_from,
            default=CalendarGenerator.DEFAULT_PM_FROM,
        )
        pm_to = CalendarValidator.parse_time(
            args.pm_to,
            default=CalendarGenerator.DEFAULT_PM_TO,
        )

        if args.output:
            output_path = Path(args.output)
        else:
            default_basename = CalendarValidator.to_snake_case(args.name)
            output_path = Path(f"{default_basename}.csv")

        if not args.quiet:
            Console.primary(
                f"Generating calendar: \"{args.name}\" "
                f"from \"{start}\" to \"{end}\"\n"
            )

        generator = CalendarGenerator(
            name=args.name,
            address=args.address,
            start=start,
            end=end,
            am_from=am_from,
            am_to=am_to,
            pm_from=pm_from,
            pm_to=pm_to,
        )
        generator.write_csv(output_path, dry_run=args.dry_run)
        return 0


if __name__ == "__main__":
    app = CalendarGeneratorApp(
        author="TangoMan75",
        title="TangoMan Calendar Generator",
        description=(
            "Generate a Google Calendar-compatible CSV with AM/PM time slots "
            "for every working day in a date range. Use --gui to launch the "
            "graphical user interface instead."
        ),
    )
    sys.exit(app.run())
