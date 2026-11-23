#!/usr/bin/env python3
"""Tests for the direct installer.py installer."""


import sys
import os
import tempfile
import unittest
from pathlib import Path
from io import StringIO
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import installer

COMPLETE_SCRIPT = '''#!/usr/bin/env python3
import argparse
import sys

def generate_completion(parser):
    return ("#!/bin/bash\\n"
            "_fixture_completions() { COMPREPLY=(); }\\n"
            "complete -F _fixture_completions fixture\\n")

def build_parser():
    p = argparse.ArgumentParser(description="fixture")
    p.add_argument("input")
    p.add_argument("--output")
    p.add_argument("--verbose", "-v", action="count", default=0)
    return p

if __name__ == "__main__":
    if "--completion" in sys.argv:
        print(generate_completion(build_parser()))
    else:
        build_parser().parse_args()
'''

LEGACY_SCRIPT = "print('tool')\n"


class TestInstallerScript(unittest.TestCase):
    """Test direct installation and uninstallation behavior."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.script = self.test_dir / "tool with spaces.py"
        self.script.write_text(COMPLETE_SCRIPT, encoding="utf-8")
        self.legacy_script = self.test_dir / "legacy.py"
        self.legacy_script.write_text(LEGACY_SCRIPT, encoding="utf-8")
        self.home = self.test_dir / "home"
        self.home.mkdir()
        (self.home / ".bashrc").write_text("", encoding="utf-8")

    def tearDown(self):
        for path in sorted(self.test_dir.rglob("*"), reverse=True):
            if path.is_symlink() or path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        self.test_dir.rmdir()

    def test_install_copies_target_runtime_and_completion(self):
        with patch("installer.Path.home", return_value=self.home), patch(
            "installer.shutil.which", side_effect=lambda name: "/usr/bin/bash" if name == "bash" else None
        ), patch("sys.stdout", new_callable=StringIO) as output:
            target = installer.Target(script_file=self.script, local=True)
            installer.Installer(target=target).install()

        self.assertEqual(
            (target.install_dir / self.script.name).read_text(encoding="utf-8"),
            COMPLETE_SCRIPT,
        )
        self.assertFalse(target.install_dir.joinpath("heel.py").exists())
        self.assertFalse(target.install_dir.joinpath("moments.py").exists())
        self.assertTrue(target.completion_file.is_file())
        self.assertIn("_fixture_completions", target.completion_file.read_text(encoding="utf-8"))
        self.assertTrue(target.symlink_path.is_symlink())
        self.assertEqual(target.symlink_path.resolve(), target.destination_file.resolve())
        self.assertIn(f"###> {target.name} ###", (self.home / ".bashrc").read_text())
        self.assertIn('export PATH="$HOME/.local/bin:$PATH"', (self.home / ".bashrc").read_text())
        self.assertIn("Installed:", output.getvalue())
        self.assertIn("Completion generated:", output.getvalue())

    def test_path_update_is_not_duplicated(self):
        rc_file = self.home / ".bashrc"
        path_line = 'export PATH="$HOME/.local/bin:$PATH"'
        rc_file.write_text(f"{path_line}\n", encoding="utf-8")
        with patch("installer.Path.home", return_value=self.home), patch(
            "installer.shutil.which", side_effect=lambda name: "/usr/bin/bash" if name == "bash" else None
        ), patch.dict(os.environ, {"PATH": "/usr/bin"}):
            target = installer.Target(script_file=self.script, local=True)
            installer.Installer(target=target).ensure_bin_dir_in_path()

        self.assertEqual(rc_file.read_text(encoding="utf-8").count(path_line), 1)

    def test_uninstall_removes_target_and_completion(self):
        with patch("installer.Path.home", return_value=self.home), patch(
            "installer.shutil.which", return_value="/usr/bin/bash"
        ), patch("sys.stdout", new_callable=StringIO) as output:
            target = installer.Target(script_file=self.script, local=True)
            inst = installer.Installer(target=target, logger=installer.Logger(verbose=3))
            inst.install()
            inst.uninstall()

        self.assertFalse(target.install_dir.exists())
        self.assertFalse(target.symlink_path.exists())
        self.assertNotIn(target.name, (self.home / ".bashrc").read_text())
        self.assertIn("Removed symlink:", output.getvalue())
        self.assertIn("Removed folder:", output.getvalue())

    def test_missing_script_fails(self):
        with self.assertRaises(SystemExit):
            installer.Application().run(arguments=["install", "missing.py"])

    def test_install_skips_completion_for_unsupported_script(self):
        with patch("installer.Path.home", return_value=self.home), patch(
            "installer.shutil.which", side_effect=lambda name: "/usr/bin/bash" if name == "bash" else None
        ), patch("sys.stdout", new_callable=StringIO) as output:
            target = installer.Target(script_file=self.legacy_script, local=True)
            installer.Installer(target=target).install()

        self.assertTrue(target.destination_file.is_file())
        self.assertFalse(target.completion_file.is_file())
        self.assertIn("does not support --completion", output.getvalue())
        # rc sourcing is skipped when no completion file exists
        self.assertNotIn(f"###> {target.name} ###", (self.home / ".bashrc").read_text())

    def test_install_multiple_files(self):
        script_two = self.test_dir / "tool_two.py"
        script_two.write_text("print('tool two')\n", encoding="utf-8")
        with patch("installer.Path.home", return_value=self.home), patch(
            "installer.shutil.which", side_effect=lambda name: "/usr/bin/bash" if name == "bash" else None
        ), patch("sys.stdout", new_callable=StringIO) as output:
            installer.Application().run(arguments=["install", str(self.script), str(script_two)])
            target_one = installer.Target(script_file=self.script, local=True)
            target_two = installer.Target(script_file=script_two, local=True)
        self.assertTrue(target_one.destination_file.is_file())
        self.assertTrue(target_two.destination_file.is_file())
        self.assertTrue(target_one.symlink_path.is_symlink())
        self.assertTrue(target_two.symlink_path.is_symlink())
        self.assertEqual(output.getvalue().count("Installation complete!"), 2)

    def test_action_is_required(self):
        with self.assertRaises(SystemExit):
            installer.Application().run(arguments=[str(self.script)])

    def test_verbose_is_stackable(self):
        parser = installer.Application().parser
        args = parser.parse_args(["install", str(self.script), "-vvv"])

        self.assertEqual(args.verbose, 3)

    def test_local_flag_creates_symlink_in_local_bin(self):
        with patch("installer.Path.home", return_value=self.home), patch(
            "installer.shutil.which", side_effect=lambda name: "/usr/bin/bash" if name == "bash" else None
        ), patch("sys.stdout", new_callable=StringIO):
            target = installer.Target(script_file=self.script, local=True)
            installer.Installer(target=target).install()

        self.assertTrue(target.symlink_path.is_symlink())
        self.assertEqual(str(target.bin_dir), str(self.home / ".local/bin"))
        self.assertEqual(target.symlink_path.parent, self.home / ".local/bin")

    def test_default_destination_is_local_bin(self):
        target = installer.Target(script_file=self.script)
        self.assertEqual(target.bin_dir, Path.home() / ".local/bin")
        self.assertEqual(target.symlink_path, Path.home() / ".local/bin" / target.name)

    def test_install_aborts_when_destination_exists_without_force(self):
        mock_bin = self.test_dir / "usr_bin"
        mock_bin.mkdir()
        target = installer.Target(script_file=self.script)
        target.bin_dir = mock_bin
        target.symlink_path = mock_bin / target.name
        existing = mock_bin / target.name
        existing.write_text("old", encoding="utf-8")
        with patch("installer.Path.home", return_value=self.home), patch(
            "installer.shutil.which", side_effect=lambda name: "/usr/bin/bash" if name == "bash" else None
        ), patch("os.geteuid", return_value=0), patch("sys.stderr", new_callable=StringIO) as err:
            inst = installer.Installer(target=target)
            inst.install()

        self.assertTrue(existing.exists())
        self.assertFalse(target.symlink_path.is_symlink())
        self.assertIn("already exists", err.getvalue())
        self.assertIn("--force", err.getvalue())

    def test_install_force_overwrites_existing_destination(self):
        mock_bin = self.test_dir / "usr_bin"
        mock_bin.mkdir()
        target = installer.Target(script_file=self.script)
        target.bin_dir = mock_bin
        target.symlink_path = mock_bin / target.name
        existing = mock_bin / target.name
        existing.write_text("old", encoding="utf-8")
        with patch("installer.Path.home", return_value=self.home), patch(
            "installer.shutil.which", side_effect=lambda name: "/usr/bin/bash" if name == "bash" else None
        ), patch("os.geteuid", return_value=0), patch("sys.stdout", new_callable=StringIO):
            inst = installer.Installer(target=target, force=True)
            inst.install()

        self.assertTrue(target.symlink_path.is_symlink())
        self.assertEqual(target.symlink_path.resolve(), target.destination_file.resolve())

    def test_install_force_overwrites_existing_symlink(self):
        mock_bin = self.test_dir / "usr_bin"
        mock_bin.mkdir()
        other_file = self.test_dir / "other.py"
        other_file.write_text("other", encoding="utf-8")
        target = installer.Target(script_file=self.script)
        target.bin_dir = mock_bin
        target.symlink_path = mock_bin / target.name
        existing_symlink = mock_bin / target.name
        existing_symlink.symlink_to(other_file)
        with patch("installer.Path.home", return_value=self.home), patch(
            "installer.shutil.which", side_effect=lambda name: "/usr/bin/bash" if name == "bash" else None
        ), patch("os.geteuid", return_value=0), patch("sys.stdout", new_callable=StringIO):
            inst = installer.Installer(target=target, force=True)
            inst.install()

        self.assertTrue(target.symlink_path.is_symlink())
        self.assertEqual(target.symlink_path.resolve(), target.destination_file.resolve())

    def test_cli_global_flag(self):
        args = installer.Application().parser.parse_args(["install", str(self.script), "-g"])
        self.assertTrue(args.global_install)

    def test_cli_force_flag(self):
        args = installer.Application().parser.parse_args(["install", str(self.script), "--force"])
        self.assertTrue(args.force)

    def test_install_aborts_without_sudo_for_usr_bin(self):
        with patch("installer.Path.home", return_value=self.home), patch(
            "installer.shutil.which", side_effect=lambda name: "/usr/bin/bash" if name == "bash" else None
        ), patch("os.geteuid", return_value=1000), patch("sys.stderr", new_callable=StringIO) as err:
            target = installer.Target(script_file=self.script, local=False)
            inst = installer.Installer(target=target)
            inst.install()

        self.assertFalse(target.symlink_path.exists())
        self.assertIn("requires root", err.getvalue())

    def test_install_aborts_when_destination_file_exists_without_force(self):
        with patch("installer.Path.home", return_value=self.home), patch(
            "installer.shutil.which", side_effect=lambda name: "/usr/bin/bash" if name == "bash" else None
        ), patch("os.geteuid", return_value=0), patch("sys.stderr", new_callable=StringIO) as err:
            target = installer.Target(script_file=self.script, local=True)
            target.install_dir.mkdir(parents=True, exist_ok=True)
            target.destination_file.write_text("old", encoding="utf-8")
            inst = installer.Installer(target=target)
            inst.install()

        self.assertEqual(target.destination_file.read_text(encoding="utf-8"), "old")
        self.assertIn("already exists", err.getvalue())
        self.assertIn("--force", err.getvalue())

    def test_install_force_overwrites_existing_destination_file(self):
        with patch("installer.Path.home", return_value=self.home), patch(
            "installer.shutil.which", side_effect=lambda name: "/usr/bin/bash" if name == "bash" else None
        ), patch("os.geteuid", return_value=0), patch("sys.stdout", new_callable=StringIO):
            target = installer.Target(script_file=self.script, local=True)
            target.install_dir.mkdir(parents=True, exist_ok=True)
            target.destination_file.write_text("old", encoding="utf-8")
            inst = installer.Installer(target=target, force=True)
            inst.install()

        self.assertEqual(target.destination_file.read_text(encoding="utf-8"), COMPLETE_SCRIPT)

    def test_uninstall_cleans_usr_bin_symlink_if_valid(self):
        usr_bin = self.test_dir / "usr_bin"
        usr_bin.mkdir()
        target = installer.Target(script_file=self.script, local=False)
        target.bin_dir = usr_bin
        target.symlink_path = usr_bin / target.name
        target.bin_dirs = [self.home / ".local/bin", usr_bin]
        target.install_dir.mkdir(parents=True, exist_ok=True)
        target.destination_file.write_text(COMPLETE_SCRIPT, encoding="utf-8")
        target.symlink_path.symlink_to(target.destination_file)
        with patch("installer.Path.home", return_value=self.home), patch(
            "installer.shutil.which", return_value="/usr/bin/bash"
        ), patch("sys.stdout", new_callable=StringIO) as output:
            inst = installer.Installer(target=target, logger=installer.Logger(verbose=3))
            inst.uninstall()

        self.assertFalse(target.symlink_path.exists())
        self.assertFalse(target.install_dir.exists())
        self.assertIn("Removed symlink:", output.getvalue())
        self.assertIn("Removed folder:", output.getvalue())

    def test_uninstall_skips_usr_bin_symlink_pointing_elsewhere(self):
        usr_bin = self.test_dir / "usr_bin"
        usr_bin.mkdir()
        other_file = self.test_dir / "other.py"
        other_file.write_text("other", encoding="utf-8")
        target = installer.Target(script_file=self.script, local=False)
        target.bin_dir = usr_bin
        target.symlink_path = usr_bin / target.name
        target.bin_dirs = [self.home / ".local/bin", usr_bin]
        target.install_dir.mkdir(parents=True, exist_ok=True)
        target.destination_file.write_text(COMPLETE_SCRIPT, encoding="utf-8")
        target.symlink_path.symlink_to(other_file)
        with patch("installer.Path.home", return_value=self.home), patch(
            "installer.shutil.which", return_value="/usr/bin/bash"
        ), patch("sys.stdout", new_callable=StringIO) as output:
            inst = installer.Installer(target=target, logger=installer.Logger(verbose=3))
            inst.uninstall()

        self.assertTrue(target.symlink_path.exists())
        self.assertIn("does not point to", output.getvalue())

    def test_uninstall_skips_non_symlink_in_usr_bin(self):
        usr_bin = self.test_dir / "usr_bin"
        usr_bin.mkdir()
        target = installer.Target(script_file=self.script, local=False)
        target.bin_dir = usr_bin
        target.symlink_path = usr_bin / target.name
        target.bin_dirs = [self.home / ".local/bin", usr_bin]
        target.install_dir.mkdir(parents=True, exist_ok=True)
        target.destination_file.write_text(COMPLETE_SCRIPT, encoding="utf-8")
        target.symlink_path.write_text("not a symlink", encoding="utf-8")
        with patch("installer.Path.home", return_value=self.home), patch(
            "installer.shutil.which", return_value="/usr/bin/bash"
        ), patch("sys.stdout", new_callable=StringIO) as output:
            inst = installer.Installer(target=target, logger=installer.Logger(verbose=3))
            inst.uninstall()

        self.assertTrue(target.symlink_path.exists())
        self.assertIn("is not a symlink", output.getvalue())


if __name__ == "__main__":
    unittest.main()
