#!/usr/bin/env python3
"""Install and uninstall Python scripts without requiring target-script options."""

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


#--------------------------------------------------
# Console: semantic console output
#--------------------------------------------------


class Console:
    """Print colored status messages."""

    ALERT_PRIMARY = "\033[1;104;97m"
    ALERT_SUCCESS = "\033[1;42;97m"
    ALERT_WARNING = "\033[1;43;97m"
    ALERT_INFO = "\033[1;44;97m"

    SUCCESS = "\033[32m"
    WARNING = "\033[33m"
    INFO = "\033[95m"
    DANGER = "\033[31m"
    DEFAULT = "\033[0m"
    EOL = "\033[0m\n"

    @staticmethod
    def _alert_block(color, *, text):
        text = " ".join(str(text).splitlines())[:63]
        top = f"{Console.EOL}{color}{'':>64}{Console.EOL}"
        middle = f"{color} {text:<63}{Console.EOL}"
        bottom = f"{color}{'':>64}{Console.EOL}\n"
        print(top + middle + bottom, end='')

    @staticmethod
    def alert_primary(text):
        """Print primary alert block."""
        Console._alert_block(Console.ALERT_PRIMARY, text=text)

    @staticmethod
    def alert_success(text):
        """Print success alert block."""
        Console._alert_block(Console.ALERT_SUCCESS, text=text)

    @staticmethod
    def alert_warning(text):
        """Print warning alert block."""
        Console._alert_block(Console.ALERT_WARNING, text=text)

    @staticmethod
    def alert_info(text):
        """Print info alert block."""
        Console._alert_block(Console.ALERT_INFO, text=text)

    @staticmethod
    def success(message):
        """Print a success message."""
        print(f"{Console.SUCCESS}{message}{Console.DEFAULT}")

    @staticmethod
    def warning(message):
        """Print a warning message."""
        print(f"{Console.WARNING}{message}{Console.DEFAULT}")

    @staticmethod
    def info(message):
        """Print an informational message."""
        print(f"{Console.INFO}{message}{Console.DEFAULT}")

    @staticmethod
    def danger(message):
        """Print an error message."""
        print(f"{Console.DANGER}{message}{Console.DEFAULT}", file=sys.stderr)


#--------------------------------------------------
# Logger: installer output
#--------------------------------------------------


class Logger:
    """Print installer messages according to the configured verbosity."""

    def __init__(self, *, verbose=3):
        self.verbose = verbose

    def info(self, message):
        """Print informational output."""
        if self.verbose >= 3:
            Console.info(message)

    def warning(self, message):
        """Print warning output."""
        if self.verbose >= 2:
            Console.warning(message)

    def success(self, message):
        """Print successful actions."""
        if self.verbose >= 1:
            Console.success(message)


class NullLogger:
    """No-op logger matching the Heel installer interface."""

    def __init__(self, *, verbose=0):
        self.verbose = verbose

    def __getattr__(self, name):
        return lambda *args, **kwargs: None


#--------------------------------------------------
# Target: installation paths and completion parser
#--------------------------------------------------


class Target:
    """Describe the target script and its Heel-compatible installation paths."""

    def __init__(self, *, script_file, author="TangoMan75", local=True):
        self.author = author
        self.script_file = script_file.resolve()
        self.name = self.script_file.stem
        self.install_dir = Path.home() / f".local/share/{author}" / self.name
        self.destination_file = self.install_dir / self.script_file.name
        self.completion_file = self.install_dir / f"{self.name}-completion.sh"
        self.local = local
        self.local_bin_dir = Path.home() / ".local/bin"
        self.global_bin_dir = Path("/usr/bin")
        self.bin_dir = self.local_bin_dir if local else self.global_bin_dir
        self.symlink_path = self.bin_dir / self.name
        self.bin_dirs = [self.local_bin_dir, self.global_bin_dir]


#--------------------------------------------------
# Installer: self-contained installation and uninstallation
#--------------------------------------------------


class Installer:
    """Install a target."""

    def __init__(self, *, target, logger=None, force=False):
        self.app = target
        self.logger = logger if logger is not None else Logger()
        self.force = force

    def install(self):
        """Copy the target, runtime modules, symlink, and completion script."""
        if not self.app.local and os.geteuid() != 0:
            Console.danger(
                "Installing to /usr/bin requires root; "
                "re-run with sudo or use -l for a local install."
            )
            return
        self.app.install_dir.mkdir(parents=True, exist_ok=True)
        self.app.bin_dir.mkdir(parents=True, exist_ok=True)
        if self.app.destination_file.exists() and not self.force:
            Console.danger(
                f'"{self.app.destination_file}" already exists; '
                f"use --force to overwrite."
            )
            return
        shutil.copy2(self.app.script_file, self.app.destination_file)
        self.logger.success(f"Installed: {self.app.destination_file}")
        self.generate_autocomplete()
        if self.app.completion_file.exists():
            self.add_completion_to_rc(app_name=self.app.name, completion_path=self.app.completion_file)
        self.ensure_bin_dir_in_path()

        if self.app.symlink_path.is_symlink():
            if self.app.symlink_path.resolve() != self.app.destination_file.resolve():
                if not self.force:
                    Console.danger(
                        f'"{self.app.symlink_path}" already exists; '
                        f"use --force to overwrite."
                    )
                    return
                self.app.symlink_path.unlink()
                self.app.symlink_path.symlink_to(self.app.destination_file)
                self.logger.info(f"Symlink updated: {self.app.symlink_path}")
        elif self.app.symlink_path.exists():
            if not self.force:
                Console.danger(
                    f'"{self.app.symlink_path}" already exists; '
                    f"use --force to overwrite."
                )
                return
            self.app.symlink_path.unlink()
            self.app.symlink_path.symlink_to(self.app.destination_file)
            self.logger.info(f"Symlink created: {self.app.symlink_path}")
        else:
            self.app.symlink_path.symlink_to(self.app.destination_file)
            self.logger.info(f"Symlink created: {self.app.symlink_path}")

        Console.success("Installation complete!")

    def ensure_bin_dir_in_path(self):
        """Persist the private bin directory in detected shell startup files."""
        marker_name = ".local/bin"
        marker_start = f"###> {marker_name}"
        marker_end = f"###< {marker_name}"
        path_line = 'export PATH="$HOME/.local/bin:$PATH"'
        block = f"{marker_start}\n{path_line}\n{marker_end}"
        shells = []
        if shutil.which("bash") or shutil.which("sh"):
            shells.append(".bashrc")
        if shutil.which("zsh"):
            shells.append(".zshrc")

        for rc_name in shells:
            rc_file = Path.home() / rc_name
            if not rc_file.exists():
                continue
            content = rc_file.read_text(encoding="utf-8")
            if marker_start in content:
                continue
            if path_line in content:
                content = content.replace(path_line, block)
                separator = "" if content.endswith("\n") else "\n"
                rc_file.write_text(f"{content}{separator}", encoding="utf-8")
                Console.info(f"Added {self.app.bin_dir} to PATH in {rc_name}")
                self.logger.success(f"PATH updated in {rc_file}")
            else:
                separator = "" if not content or content.endswith("\n") else "\n"
                rc_file.write_text(f"{content}{separator}{block}\n", encoding="utf-8")
                Console.info(f"Added {self.app.bin_dir} to PATH in {rc_name}")
                self.logger.success(f"PATH updated in {rc_file}")

    def generate_autocomplete(self):
        """Generate a bash completion script by delegating to the target's own --completion.

        Runs the installed target script with ``--completion`` and writes its stdout
        to the completion file. If the target does not support ``--completion`` (or
        exits non-zero / prints nothing), the completion is skipped with a warning
        and no completion file is created.
        """
        try:
            result = subprocess.run(
                [sys.executable, str(self.app.destination_file), "--completion"],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as err:
            self.logger.warning(f"Could not generate completion for {self.app.name}: {err}")
            return

        if result.returncode != 0 or not result.stdout.strip().startswith("#!/bin/bash"):
            self.logger.warning(
                f"{self.app.name} does not support --completion; skipping completion."
            )
            return

        self.app.completion_file.write_text(result.stdout, encoding="utf-8")
        self.logger.success(f"Completion generated: {self.app.completion_file}")

    def add_completion_to_rc(self, *, app_name, completion_path):
        """Add completion sourcing to detected bash and zsh configuration files."""
        marker_start = f"###> {app_name} ###"
        marker_end = f"###< {app_name} ###"
        source_line = f"source {shlex.quote(str(completion_path))}"
        shells = []
        if shutil.which("bash") or shutil.which("sh"):
            shells.append("bash")
        if shutil.which("zsh"):
            shells.append("zsh")

        for shell in shells:
            rc_file = Path.home() / (".bashrc" if shell == "bash" else ".zshrc")
            if not rc_file.exists():
                continue
            content = rc_file.read_text(encoding="utf-8")
            if marker_start not in content:
                with open(rc_file, "a", encoding="utf-8") as file_handle:
                    file_handle.write(f"\n{marker_start}\n{source_line}\n{marker_end}\n")
                self.logger.info(f"Added completion to {rc_file}")
        return shells

    def uninstall(self):
        """Remove completion sourcing, symlinks from all bin dirs, and install dir."""
        self.remove_completion_from_rc(self.app.name)
        self.remove_path_from_rc()
        for bin_dir in self.app.bin_dirs:
            symlink = bin_dir / self.app.name
            if symlink.is_symlink():
                if symlink.resolve() == self.app.destination_file.resolve():
                    symlink.unlink()
                    self.logger.info(f"Removed symlink: {symlink}")
                else:
                    self.logger.warning(
                        f'"{symlink}" does not point to {self.app.destination_file}; skipping.'
                    )
            elif symlink.exists():
                self.logger.warning(f'"{symlink}" is not a symlink; skipping.')
        if self.app.install_dir.exists():
            shutil.rmtree(self.app.install_dir)
            self.logger.info(f"Removed folder: {self.app.install_dir}")
        else:
            self.logger.warning(f'"{self.app.install_dir}" folder not found.')
        Console.success("Uninstallation complete!")

    def remove_completion_from_rc(self, app_name):
        """Remove completion markers from bash and zsh configuration files."""
        marker_start = f"###> {app_name} ###"
        marker_end = f"###< {app_name} ###"
        for rc_name in (".bashrc", ".zshrc"):
            rc_file = Path.home() / rc_name
            if not rc_file.exists():
                continue
            content = rc_file.read_text(encoding="utf-8")
            if marker_start in content:
                pattern = rf"{re.escape(marker_start)}\n.*?\n{re.escape(marker_end)}\n?"
                content = re.sub(pattern, "", content, flags=re.DOTALL)
                content = re.sub(r"\n{3,}", "\n\n", content)
                content = content.strip("\n") + "\n"
                rc_file.write_text(content, encoding="utf-8")
                self.logger.info(f"Removed completion from {rc_file}")

    def remove_path_from_rc(self):
        """Remove PATH markers from bash and zsh configuration files."""
        marker_name = ".local/bin"
        marker_start = f"###> {marker_name}"
        marker_end = f"###< {marker_name}"
        bin_dir = self.app.bin_dir.resolve()
        if bin_dir.is_dir() and any(bin_dir.iterdir()):
            self.logger.warning(f"{bin_dir} is not empty; keeping PATH in rc files")
            return
        for rc_name in (".bashrc", ".zshrc"):
            rc_file = Path.home() / rc_name
            if not rc_file.exists():
                continue
            content = rc_file.read_text(encoding="utf-8")
            if marker_start in content:
                pattern = rf"{re.escape(marker_start)}\n.*?\n{re.escape(marker_end)}\n?"
                content = re.sub(pattern, "", content, flags=re.DOTALL)
                content = re.sub(r"\n{3,}", "\n\n", content)
                content = content.strip("\n") + "\n"
                rc_file.write_text(content, encoding="utf-8")
                self.logger.info(f"Removed PATH from {rc_file}")


#--------------------------------------------------
# Command line application
#--------------------------------------------------


class Application:
    """Parse actions and execute the direct installer."""

    def __init__(self):
        self.parser = argparse.ArgumentParser(description=__doc__)
        subparsers = self.parser.add_subparsers(dest="command", required=True)

        install_parser = subparsers.add_parser("install", help="Install scripts")
        install_parser.add_argument(
            "input", nargs="+", metavar="SCRIPT", help="Python script(s) to install"
        )
        install_parser.add_argument(
            "-g", "--global",
            action="store_true",
            dest="global_install",
            help="Install symlink to /usr/bin (requires root privileges)",
        )
        install_parser.add_argument(
            "--force",
            action="store_true",
            help="Force overwrite existing files and symlinks",
        )
        install_parser.add_argument(
            "--verbose",
            "-v",
            action="count",
            default=0,
            help="Increase verbosity (stackable: -v, -vv, -vvv)",
        )

        uninstall_parser = subparsers.add_parser("uninstall", help="Uninstall scripts")
        uninstall_parser.add_argument(
            "input", nargs="+", metavar="SCRIPT", help="Python script(s) to uninstall"
        )
        uninstall_parser.add_argument(
            "--verbose",
            "-v",
            action="count",
            default=0,
            help="Increase verbosity (stackable: -v, -vv, -vvv)",
        )

    def run(self, *, arguments=None):
        """Run installation or uninstallation and return a status code."""
        args = self.parser.parse_args(arguments)
        for script_name in args.input:
            script = Path(script_name)
            if not script.is_file():
                self.parser.error(f'"{script}" file not found')
            local = True
            force = False
            verbose = args.verbose
            if args.command == "install":
                local = not args.global_install
                force = args.force
            installer = Installer(
                target=Target(script_file=script, local=local),
                logger=Logger(verbose=verbose),
                force=force,
            )
            if args.command == "install":
                installer.install()
            else:
                installer.uninstall()
        return 0


if __name__ == "__main__":
    sys.exit(Application().run())
