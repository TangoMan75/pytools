#!/usr/bin/env python3
# noqa: E402
"""Tests for semantic_versioning module."""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))

import semantic_versioning


#--------------------------------------------------
# VersionParser
#--------------------------------------------------


class TestVersionParserParse(unittest.TestCase):
    """Tests for VersionParser.parse."""

    def test_parse_simple(self):
        """Parse simple."""
        self.assertEqual(semantic_versioning.VersionParser.parse("0.1.0"), (0, 1, 0))

    def test_parse_double_digit(self):
        """Parse double digit."""
        self.assertEqual(semantic_versioning.VersionParser.parse("10.20.30"), (10, 20, 30))

    def test_parse_triple_digit(self):
        """Parse triple digit."""
        self.assertEqual(semantic_versioning.VersionParser.parse("255.255.255"), (255, 255, 255))

    def test_parse_zeros(self):
        """Parse zeros."""
        self.assertEqual(semantic_versioning.VersionParser.parse("0.0.0"), (0, 0, 0))

    def test_parse_invalid_too_few_segments(self):
        """Parse invalid too few segments."""
        with self.assertRaises(ValueError):
            semantic_versioning.VersionParser.parse("1.2")

    def test_parse_invalid_too_many_segments(self):
        """Parse invalid too many segments."""
        with self.assertRaises(ValueError):
            semantic_versioning.VersionParser.parse("1.2.3.4")

    def test_parse_invalid_non_numeric(self):
        """Parse invalid non numeric."""
        with self.assertRaises(ValueError):
            semantic_versioning.VersionParser.parse("a.b.c")

    def test_parse_invalid_with_prerelease(self):
        """Parse invalid with prerelease."""
        with self.assertRaises(ValueError):
            semantic_versioning.VersionParser.parse("1.2.3-rc.1")

    def test_parse_invalid_empty(self):
        """Parse invalid empty."""
        with self.assertRaises(ValueError):
            semantic_versioning.VersionParser.parse("")

    def test_parse_invalid_too_long_segments(self):
        """Parse invalid too long segments."""
        with self.assertRaises(ValueError):
            semantic_versioning.VersionParser.parse("1000.0.0")


class TestVersionParserFormat(unittest.TestCase):
    """Tests for VersionParser.format."""

    def test_format_zeros(self):
        """Format zeros."""
        self.assertEqual(semantic_versioning.VersionParser.format((0, 0, 0)), "0.0.0")

    def test_format_simple(self):
        """Format simple."""
        self.assertEqual(semantic_versioning.VersionParser.format((1, 2, 3)), "1.2.3")

    def test_format_large(self):
        """Format large."""
        self.assertEqual(semantic_versioning.VersionParser.format((100, 200, 300)), "100.200.300")


class TestVersionParserBump(unittest.TestCase):
    """Tests for VersionParser.bump."""

    def test_bump_major(self):
        """Bump major."""
        self.assertEqual(semantic_versioning.VersionParser.bump("0.1.0", kind="major"), "1.0.0")

    def test_bump_major_resets_minor_and_fix(self):
        """Bump major resets minor and fix."""
        self.assertEqual(semantic_versioning.VersionParser.bump("1.5.7", kind="major"), "2.0.0")

    def test_bump_minor(self):
        """Bump minor."""
        self.assertEqual(semantic_versioning.VersionParser.bump("0.1.0", kind="minor"), "0.2.0")

    def test_bump_minor_resets_fix(self):
        """Bump minor resets fix."""
        self.assertEqual(semantic_versioning.VersionParser.bump("1.5.7", kind="minor"), "1.6.0")

    def test_bump_fix(self):
        """Bump fix."""
        self.assertEqual(semantic_versioning.VersionParser.bump("0.1.0", kind="fix"), "0.1.1")

    def test_bump_fix_increments_only_fix(self):
        """Bump fix increments only fix."""
        self.assertEqual(semantic_versioning.VersionParser.bump("1.5.7", kind="fix"), "1.5.8")

    def test_bump_invalid_kind_raises(self):
        """Bump invalid kind raises."""
        with self.assertRaises(ValueError):
            semantic_versioning.VersionParser.bump("1.2.3", kind="patch")

    def test_bump_invalid_version_raises(self):
        """Bump invalid version raises."""
        with self.assertRaises(ValueError):
            semantic_versioning.VersionParser.bump("not-a-version", kind="fix")


class TestVersionParserBumpInLine(unittest.TestCase):
    """Tests for VersionParser.bump_in_line."""

    def _bump(self, line, *, kind):
        return semantic_versioning.VersionParser.bump_in_line(line, kind=kind)

    def test_no_match_returns_empty_changes(self):
        """No match returns empty changes."""
        new_line, changes = self._bump("hello world", kind="fix")
        self.assertEqual(new_line, "hello world")
        self.assertEqual(changes, [])

    def test_single_match(self):
        """Single match."""
        new_line, changes = self._bump("Release 1.2.3", kind="fix")
        self.assertEqual(new_line, "Release 1.2.4")
        self.assertEqual(changes, [("1.2.3", "1.2.4")])

    def test_multiple_matches_on_same_line(self):
        """Multiple matches on same line."""
        new_line, changes = self._bump("from 0.1.0 to 1.2.9", kind="fix")
        self.assertEqual(new_line, "from 0.1.1 to 1.2.10")
        self.assertEqual(changes, [("0.1.0", "0.1.1"), ("1.2.9", "1.2.10")])

    def test_preserves_surrounding_text(self):
        """Preserves surrounding text."""
        new_line, changes = self._bump(
            '__version__ = "1.2.3"  # current', kind="minor"
        )
        self.assertEqual(new_line, '__version__ = "1.3.0"  # current')
        self.assertEqual(changes, [('1.2.3', '1.3.0')])

    def test_strips_prerelease(self):
        """Strips prerelease."""
        new_line, changes = self._bump("1.2.3-rc.1", kind="fix")
        self.assertEqual(new_line, "1.2.4")
        self.assertEqual(changes, [("1.2.3-rc.1", "1.2.4")])

    def test_strips_prerelease_on_major(self):
        """Strips prerelease on major."""
        new_line, changes = self._bump("1.2.3-beta.4", kind="major")
        self.assertEqual(new_line, "2.0.0")
        self.assertEqual(changes, [("1.2.3-beta.4", "2.0.0")])

    def test_ignores_ip_address(self):
        """Ignores ip address."""
        new_line, changes = self._bump("IP: 192.168.1.1", kind="fix")
        self.assertEqual(new_line, "IP: 192.168.1.1")
        self.assertEqual(changes, [])

    def test_ignores_date_with_four_digit_first_segment(self):
        """Ignores date with four digit first segment."""
        new_line, changes = self._bump("Date: 2024.01.15", kind="fix")
        self.assertEqual(new_line, "Date: 2024.01.15")
        self.assertEqual(changes, [])

    def test_ignores_four_segment_version(self):
        """Ignores four segment version."""
        new_line, changes = self._bump("Build 1.2.3.4", kind="fix")
        self.assertEqual(new_line, "Build 1.2.3.4")
        self.assertEqual(changes, [])

    def test_matches_v_prefix(self):
        """Matches v prefix."""
        new_line, changes = self._bump("v1.2.3", kind="fix")
        self.assertEqual(new_line, "v1.2.4")
        self.assertEqual(changes, [("1.2.3", "1.2.4")])

    def test_matches_quoted(self):
        """Matches quoted."""
        new_line, changes = self._bump('"1.0.0"', kind="fix")
        self.assertEqual(new_line, '"1.0.1"')
        self.assertEqual(changes, [('1.0.0', '1.0.1')])


#--------------------------------------------------
# VersionBumper
#--------------------------------------------------


class TestVersionBumperHelpers(unittest.TestCase):
    """Tests for VersionBumper static helpers."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_is_binary_text_file(self):
        """Is binary text file."""
        path = Path(self.tmp) / "text.txt"
        path.write_text("hello world", encoding="utf-8")
        self.assertFalse(semantic_versioning.VersionBumper.is_binary(path))

    def test_is_binary_with_null_bytes(self):
        """Is binary with null bytes."""
        path = Path(self.tmp) / "blob.bin"
        path.write_bytes(b"hello\x00world")
        self.assertTrue(semantic_versioning.VersionBumper.is_binary(path))

    def test_is_binary_empty_file(self):
        """Is binary empty file."""
        path = Path(self.tmp) / "empty.txt"
        path.touch()
        self.assertFalse(semantic_versioning.VersionBumper.is_binary(path))

    def test_read_text_strips_bom(self):
        """Read text strips bom."""
        path = Path(self.tmp) / "bom.txt"
        path.write_bytes(b"\xef\xbb\xbfversion: 1.2.3\n")
        content = semantic_versioning.VersionBumper.read_text(path)
        self.assertEqual(content, "version: 1.2.3\n")

    def test_read_text_plain(self):
        """Read text plain."""
        path = Path(self.tmp) / "plain.txt"
        path.write_text("hello\n", encoding="utf-8")
        self.assertEqual(semantic_versioning.VersionBumper.read_text(path), "hello\n")

    def test_write_text_atomic(self):
        """Write text atomic."""
        path = Path(self.tmp) / "out.txt"
        semantic_versioning.VersionBumper.write_text_atomic(
            path, content="content"
        )
        self.assertEqual(path.read_text(encoding="utf-8"), "content")
        # No leftover temp files
        leftovers = [p for p in Path(self.tmp).iterdir() if p.name.startswith("out.txt.")]
        self.assertEqual(leftovers, [])

    def test_write_text_atomic_creates_parent(self):
        """Write text atomic creates parent."""
        path = Path(self.tmp) / "sub" / "out.txt"
        semantic_versioning.VersionBumper.write_text_atomic(
            path, content="content"
        )
        self.assertEqual(path.read_text(encoding="utf-8"), "content")


class TestVersionBumperProcessFile(unittest.TestCase):
    """Tests for VersionBumper.process_file."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)

    def _make_handler(self, *, kind="fix", line=None):
        return semantic_versioning.VersionBumper(
            logger=semantic_versioning.NullLogger(),
            kind=kind,
            line=line,
        )

    def test_in_place_modification_fix(self):
        """In place modification fix."""
        path = Path(self.tmp) / "ver.txt"
        path.write_text("version: 1.2.3\n", encoding="utf-8")
        handler = self._make_handler(kind="fix")
        handler.process_file(path)
        self.assertEqual(path.read_text(encoding="utf-8"), "version: 1.2.4\n")
        self.assertEqual(handler.files_processed, 1)
        self.assertEqual(handler.files_skipped, 0)

    def test_in_place_modification_minor(self):
        """In place modification minor."""
        path = Path(self.tmp) / "ver.txt"
        path.write_text("version: 1.2.3\n", encoding="utf-8")
        handler = self._make_handler(kind="minor")
        handler.process_file(path)
        self.assertEqual(path.read_text(encoding="utf-8"), "version: 1.3.0\n")

    def test_in_place_modification_major(self):
        """In place modification major."""
        path = Path(self.tmp) / "ver.txt"
        path.write_text("version: 1.2.3\n", encoding="utf-8")
        handler = self._make_handler(kind="major")
        handler.process_file(path)
        self.assertEqual(path.read_text(encoding="utf-8"), "version: 2.0.0\n")

    def test_dry_run_does_not_modify(self):
        """Dry run does not modify."""
        path = Path(self.tmp) / "ver.txt"
        path.write_text("version: 1.2.3\n", encoding="utf-8")
        handler = self._make_handler(kind="fix")
        handler.process_file(path, dry_run=True)
        self.assertEqual(path.read_text(encoding="utf-8"), "version: 1.2.3\n")
        self.assertEqual(handler.files_processed, 1)

    def test_no_match_increments_skipped(self):
        """No match increments skipped."""
        path = Path(self.tmp) / "plain.txt"
        path.write_text("no version here\n", encoding="utf-8")
        handler = self._make_handler(kind="fix")
        handler.process_file(path)
        self.assertEqual(path.read_text(encoding="utf-8"), "no version here\n")
        self.assertEqual(handler.files_processed, 0)
        self.assertEqual(handler.files_skipped, 1)

    def test_specific_line_only(self):
        """Specific line only."""
        path = Path(self.tmp) / "ver.txt"
        path.write_text("1.0.0\n2.0.0\n3.0.0\n", encoding="utf-8")
        handler = self._make_handler(kind="fix", line=2)
        handler.process_file(path)
        self.assertEqual(path.read_text(encoding="utf-8"), "1.0.0\n2.0.1\n3.0.0\n")

    def test_specific_line_no_match(self):
        """Specific line no match."""
        path = Path(self.tmp) / "ver.txt"
        path.write_text("1.0.0\nno version\n3.0.0\n", encoding="utf-8")
        handler = self._make_handler(kind="fix", line=2)
        handler.process_file(path)
        self.assertEqual(path.read_text(encoding="utf-8"), "1.0.0\nno version\n3.0.0\n")
        self.assertEqual(handler.files_skipped, 1)

    def test_specific_line_out_of_range_is_skipped(self):
        """Specific line out of range is skipped."""
        path = Path(self.tmp) / "ver.txt"
        path.write_text("1.0.0\n", encoding="utf-8")
        handler = self._make_handler(kind="fix", line=99)
        handler.process_file(path)
        self.assertEqual(path.read_text(encoding="utf-8"), "1.0.0\n")
        self.assertEqual(handler.files_skipped, 1)

    def test_binary_file_is_skipped(self):
        """Binary file is skipped."""
        path = Path(self.tmp) / "blob.bin"
        path.write_bytes(b"1.2.3\x00\x00more")
        handler = self._make_handler(kind="fix")
        handler.process_file(path)
        self.assertEqual(path.read_bytes(), b"1.2.3\x00\x00more")
        self.assertEqual(handler.files_skipped, 1)

    def test_bom_is_stripped_on_rewrite(self):
        """Bom is stripped on rewrite."""
        path = Path(self.tmp) / "bom.txt"
        path.write_bytes(b"\xef\xbb\xbfversion: 1.2.3\n")
        handler = self._make_handler(kind="fix")
        handler.process_file(path)
        self.assertEqual(path.read_bytes(), b"version: 1.2.4\n")

    def test_multiple_versions_on_one_line(self):
        """Multiple versions on one line."""
        path = Path(self.tmp) / "multi.txt"
        path.write_text("from 0.1.0 to 1.2.9\n", encoding="utf-8")
        handler = self._make_handler(kind="fix")
        handler.process_file(path)
        self.assertEqual(path.read_text(encoding="utf-8"), "from 0.1.1 to 1.2.10\n")

    def test_prerelease_is_stripped(self):
        """Prerelease is stripped."""
        path = Path(self.tmp) / "pre.txt"
        path.write_text("1.2.3-rc.1\n", encoding="utf-8")
        handler = self._make_handler(kind="fix")
        handler.process_file(path)
        self.assertEqual(path.read_text(encoding="utf-8"), "1.2.4\n")

    def test_crlf_line_endings_preserved(self):
        """Crlf line endings preserved."""
        path = Path(self.tmp) / "crlf.txt"
        path.write_bytes(b"version: 1.2.3\r\nfoo: 4.5.6\r\n")
        handler = self._make_handler(kind="fix")
        handler.process_file(path)
        self.assertEqual(path.read_bytes(), b"version: 1.2.4\r\nfoo: 4.5.7\r\n")

    def test_fixture_file_bumps_only_intended(self):
        """Fixture file bumps only intended."""
        fixture = Path(__file__).parent / "fixtures" / "with_edge_cases.txt"
        path = Path(self.tmp) / "copy.txt"
        path.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
        handler = self._make_handler(kind="fix")
        handler.process_file(path)
        result = path.read_text(encoding="utf-8")
        # Bumped
        self.assertIn("0.1.1", result)
        self.assertIn("0.2.1", result)
        self.assertIn("1.2.4", result)
        self.assertIn('"1.0.1"', result)
        self.assertIn("3.4.6", result)
        self.assertIn("4.5.7", result)
        self.assertIn("7.8.10", result)
        # Not bumped
        self.assertIn("192.168.1.1", result)
        self.assertIn("2024.01.15", result)
        self.assertIn("1.2.3.4", result)
        # Pre-release stripped
        self.assertNotIn("1.2.3-rc.1", result)


class TestVersionBumperAppBuildParser(unittest.TestCase):
    """Tests for VersionBumperApp.build_parser."""

    def _app(self):
        return semantic_versioning.VersionBumperApp(
            author='TangoMan75',
            title='Semantic Versioning',
            description='Auto-increment semver-shaped version numbers in text files.'
        )

    def test_default_kind_is_fix(self):
        """Default kind is fix."""
        app = self._app()
        args = app.build_parser().parse_args(["input.txt"])
        self.assertEqual(args.kind, "fix")

    def test_major_flag(self):
        """Major flag."""
        app = self._app()
        args = app.build_parser().parse_args(["input.txt", "--major"])
        self.assertEqual(args.kind, "major")

    def test_minor_short_flag(self):
        """Minor short flag."""
        app = self._app()
        args = app.build_parser().parse_args(["input.txt", "--minor"])
        self.assertEqual(args.kind, "minor")

    def test_fix_short_flag(self):
        """Fix short flag."""
        app = self._app()
        args = app.build_parser().parse_args(["input.txt", "--fix"])
        self.assertEqual(args.kind, "fix")

    def test_line_option(self):
        """Line option."""
        app = self._app()
        args = app.build_parser().parse_args(["input.txt", "--line", "5"])
        self.assertEqual(args.line, 5)

    def test_line_short_flag(self):
        """Line short flag."""
        app = self._app()
        args = app.build_parser().parse_args(["input.txt", "--line", "3"])
        self.assertEqual(args.line, 3)

    def test_check_flag(self):
        """Check flag."""
        app = self._app()
        args = app.build_parser().parse_args(["input.txt", "--check"])
        self.assertTrue(args.check)

    def test_mutually_exclusive_kinds(self):
        """Mutually exclusive kinds."""
        app = self._app()
        with self.assertRaises(SystemExit):
            app.build_parser().parse_args(["input.txt", "--major", "--minor"])

    def test_recursive_inherited(self):
        """Recursive inherited."""
        app = self._app()
        args = app.build_parser().parse_args(["input", "--recursive"])
        self.assertTrue(args.recursive)

    def test_dry_run_inherited(self):
        """Dry run inherited."""
        app = self._app()
        args = app.build_parser().parse_args(["input", "--dry-run"])
        self.assertTrue(args.dry_run)


#--------------------------------------------------
# Integration: CLI
#--------------------------------------------------


class TestIntegration(unittest.TestCase):
    """End-to-end CLI tests."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.original_cwd = os.getcwd()
        os.chdir(self.tmp)
        self.app = semantic_versioning.VersionBumperApp(
            author='TangoMan75',
            title='Semantic Versioning',
            description='Auto-increment semver-shaped version numbers in text files.'
        )

    def tearDown(self):
        os.chdir(self.original_cwd)

    def test_cli_default_fix(self):
        """Cli default fix."""
        path = Path("v.txt")
        path.write_text("1.2.3\n", encoding="utf-8")
        with patch.object(sys, "argv", ["sv", str(path)]):
            self.app.run(semantic_versioning.VersionBumper)
        self.assertEqual(path.read_text(encoding="utf-8"), "1.2.4\n")

    def test_cli_major_flag(self):
        """Cli major flag."""
        path = Path("v.txt")
        path.write_text("1.2.3\n", encoding="utf-8")
        with patch.object(sys, "argv", ["sv", str(path), "--major"]):
            self.app.run(semantic_versioning.VersionBumper)
        self.assertEqual(path.read_text(encoding="utf-8"), "2.0.0\n")

    def test_cli_dry_run_preserves_file(self):
        """Cli dry run preserves file."""
        path = Path("v.txt")
        path.write_text("1.2.3\n", encoding="utf-8")
        with patch.object(sys, "argv", ["sv", str(path), "--dry-run"]):
            self.app.run(semantic_versioning.VersionBumper)
        self.assertEqual(path.read_text(encoding="utf-8"), "1.2.3\n")

    def test_cli_line_option(self):
        """Cli line option."""
        path = Path("v.txt")
        path.write_text("1.0.0\n2.0.0\n3.0.0\n", encoding="utf-8")
        with patch.object(sys, "argv", ["sv", str(path), "--line", "2"]):
            self.app.run(semantic_versioning.VersionBumper)
        self.assertEqual(path.read_text(encoding="utf-8"), "1.0.0\n2.0.1\n3.0.0\n")

    def test_cli_recursive(self):
        """Cli recursive."""
        sub = Path("sub")
        sub.mkdir()
        (Path("a.txt")).write_text("1.0.0\n", encoding="utf-8")
        (sub / "b.txt").write_text("1.0.0\n", encoding="utf-8")
        with patch.object(sys, "argv", ["sv", ".", "--recursive", "--minor"]):
            self.app.run(semantic_versioning.VersionBumper)
        self.assertEqual(Path("a.txt").read_text(encoding="utf-8"), "1.1.0\n")
        self.assertEqual((sub / "b.txt").read_text(encoding="utf-8"), "1.1.0\n")

    def test_cli_check_exits_nonzero_when_changes(self):
        """Cli check exits nonzero when changes."""
        path = Path("v.txt")
        path.write_text("1.2.3\n", encoding="utf-8")
        with patch.object(sys, "argv", ["sv", str(path), "--check"]):
            with self.assertRaises(SystemExit) as cm:
                self.app.run(semantic_versioning.VersionBumper)
        self.assertEqual(cm.exception.code, 1)
        self.assertEqual(path.read_text(encoding="utf-8"), "1.2.3\n")

    def test_cli_check_exits_zero_when_no_changes(self):
        """Cli check exits zero when no changes."""
        path = Path("v.txt")
        path.write_text("no version here\n", encoding="utf-8")
        with patch.object(sys, "argv", ["sv", str(path), "--check"]):
            self.app.run(semantic_versioning.VersionBumper)
        self.assertEqual(path.read_text(encoding="utf-8"), "no version here\n")


if __name__ == "__main__":
    unittest.main()
