#!/usr/bin/env python3
"""Verify the repository-wide command-line naming contract."""

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = [
    path for path in sorted(ROOT.glob("*.py"))
    if path.name not in {"heel.py", "installer.py"}
]
FORBIDDEN_SHORTS = ("-o", "-r", "-i", "-e", "-d", "-c", "-M", "-m", "-f", "-l", "-u")


class CliContractTest(unittest.TestCase):
    """Keep human and agent-facing option names stable."""

    def help_text(self, script: Path) -> str:
        """Return a script's help output."""
        result = subprocess.run(
            [sys.executable, str(script), "--help"],
            capture_output=True,
            text=True,
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, script.name)
        return result.stdout + result.stderr

    def test_non_installer_scripts_do_not_advertise_legacy_short_options(self):
        """Reject removed short aliases in command help."""
        for script in SCRIPTS:
            with self.subTest(script=script.name):
                help_text = self.help_text(script)
                for option in FORBIDDEN_SHORTS:
                    self.assertNotIn(f"[{option}]", help_text)
                    self.assertNotIn(f", {option}", help_text)

    def test_verbose_is_common(self):
        """Require the common verbose option."""
        for script in SCRIPTS:
            with self.subTest(script=script.name):
                self.assertIn("--verbose", self.help_text(script))

    def test_quiet_is_common(self):
        """Require the common quiet option."""
        for script in SCRIPTS:
            with self.subTest(script=script.name):
                self.assertIn("--quiet", self.help_text(script))

    def test_conv_sql_is_file_based(self):
        """Ensure conv-sql advertises file output and not stdin input."""
        help_text = self.help_text(ROOT / "conv-sql.py")
        self.assertIn("--output", help_text)
        self.assertNotIn("stdin", help_text.lower())


if __name__ == "__main__":
    unittest.main()
