#!/usr/bin/env python3
"""Tests for md_convert_setext_to_atx module."""

import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

_SPEC = importlib.util.spec_from_file_location(
    "md_convert_setext_to_atx", Path(__file__).parents[1] / "md-convert-setext-to-atx.py"
)
md_convert_setext_to_atx = importlib.util.module_from_spec(_SPEC)
sys.modules["md_convert_setext_to_atx"] = md_convert_setext_to_atx
_SPEC.loader.exec_module(md_convert_setext_to_atx)



class MockLogger:
    """Mock Logger for testing."""

    def __init__(self, verbose=0):
        self.verbose = verbose

    def success(self, message):
        """Log success message."""

    def info(self, message):
        """Log info message."""

    def warning(self, message):
        """Log warning message."""


class TestConvertSetextToAtx(unittest.TestCase):
    """Tests for convert_setext_to_atx method in SetextConverter."""

    def test_h1_heading_with_long_underline(self):
        """Test H1 heading with long underline."""
        text = "Main Title\n======\n"
        converter = md_convert_setext_to_atx.SetextConverter()
        result = converter.convert_setext_to_atx(text)
        self.assertEqual(result, "# Main Title\n")

    def test_h2_heading_with_long_underline(self):
        """Test H2 heading with long underline."""
        text = "Sub Section\n------\n"
        converter = md_convert_setext_to_atx.SetextConverter()
        result = converter.convert_setext_to_atx(text)
        self.assertEqual(result, "## Sub Section\n")

    def test_h1_heading_with_short_underline(self):
        """Test H1 heading with short underline."""
        text = "Title Space\n===\n"
        converter = md_convert_setext_to_atx.SetextConverter()
        result = converter.convert_setext_to_atx(text)
        self.assertEqual(result, "# Title Space\n")

    def test_h2_heading_with_short_underline(self):
        """Test H2 heading with short underline."""
        text = "Sub Space\n---\n"
        converter = md_convert_setext_to_atx.SetextConverter()
        result = converter.convert_setext_to_atx(text)
        self.assertEqual(result, "## Sub Space\n")

    def test_short_underline_ignored(self):
        """Test that underlines with fewer than 3 characters are ignored."""
        text = "Small Title\n==\n"
        converter = md_convert_setext_to_atx.SetextConverter()
        result = converter.convert_setext_to_atx(text)
        self.assertEqual(result, text)

    def test_thematic_break_unchanged(self):
        """Test that thematic breaks with blank line before are unchanged."""
        text = "Some paragraph text.\n\n---\n"
        converter = md_convert_setext_to_atx.SetextConverter()
        result = converter.convert_setext_to_atx(text)
        self.assertEqual(result, text)

    def test_thematic_break_without_blank_line_converted(self):
        """Test that --- without blank line is converted (treated as setext)."""
        text = "Some text\n---\n"
        converter = md_convert_setext_to_atx.SetextConverter()
        result = converter.convert_setext_to_atx(text)
        self.assertEqual(result, "## Some text\n")

    def test_multiple_headings(self):
        """Test multiple headings in same text."""
        text = "Main Title\n======\n\nSub Section\n------\n"
        converter = md_convert_setext_to_atx.SetextConverter()
        result = converter.convert_setext_to_atx(text)
        self.assertEqual(result, "# Main Title\n\n## Sub Section\n")

    def test_heading_with_trailing_whitespace(self):
        """Test heading with trailing whitespace on underline."""
        text = "Title\n===   \n"
        converter = md_convert_setext_to_atx.SetextConverter()
        result = converter.convert_setext_to_atx(text)
        self.assertEqual(result, "# Title\n")

    def test_plain_text_unchanged(self):
        """Test that plain text without headings is unchanged."""
        text = "This is just regular text.\n\nNo headings here.\n"
        converter = md_convert_setext_to_atx.SetextConverter()
        result = converter.convert_setext_to_atx(text)
        self.assertEqual(result, text)

    def test_atx_headings_unchanged(self):
        """Test that existing ATX headings are not affected."""
        text = "# Existing ATX Heading\n\n## Another One\n"
        converter = md_convert_setext_to_atx.SetextConverter()
        result = converter.convert_setext_to_atx(text)
        self.assertEqual(result, text)

    def test_front_matter_preserved(self):
        """Test that YAML front matter is preserved."""
        text = "---\ntitle: My Post\ndate: 2024-01-15\n---\nMain Title\n======\n"
        converter = md_convert_setext_to_atx.SetextConverter()
        result = converter.convert_setext_to_atx(text)
        self.assertEqual(result, "---\ntitle: My Post\ndate: 2024-01-15\n---\n# Main Title\n")

    def test_front_matter_only(self):
        """Test file with only front matter and no headings."""
        text = "---\ntitle: Just Front Matter\n---\n"
        converter = md_convert_setext_to_atx.SetextConverter()
        result = converter.convert_setext_to_atx(text)
        self.assertEqual(result, text)

    def test_no_front_matter_unchanged(self):
        """Test that no front matter means no changes to front matter logic."""
        text = "Title\n======\n"
        converter = md_convert_setext_to_atx.SetextConverter()
        result = converter.convert_setext_to_atx(text)
        self.assertEqual(result, "# Title\n")


class TestCodeFencePreservation(unittest.TestCase):
    """Tests for code fence preservation."""

    def test_code_fence_backticks_ignored(self):
        """Test that code blocks with backticks are preserved."""
        text = "Title\n======\n\n```\nsome\n=== code\n```\n"
        converter = md_convert_setext_to_atx.SetextConverter()
        result = converter.convert_setext_to_atx(text)
        self.assertEqual(result, "# Title\n\n```\nsome\n=== code\n```\n")

    def test_code_fence_with_language_ignored(self):
        """Test that code blocks with language specifier are preserved."""
        text = "Title\n======\n\n```javascript\nconst x = 1;\n----\n```\n"
        converter = md_convert_setext_to_atx.SetextConverter()
        result = converter.convert_setext_to_atx(text)
        self.assertEqual(result, "# Title\n\n```javascript\nconst x = 1;\n----\n```\n")

    def test_code_fence_php_ignored(self):
        """Test that PHP code blocks are preserved."""
        text = "Title\n======\n\n```php\n<?php\n$x = 1;\n===\n```\n"
        converter = md_convert_setext_to_atx.SetextConverter()
        result = converter.convert_setext_to_atx(text)
        self.assertEqual(result, "# Title\n\n```php\n<?php\n$x = 1;\n===\n```\n")

    def test_code_fence_tilde_ignored(self):
        """Test that code blocks with tildes are preserved."""
        text = "Title\n======\n\n~~~\nsome\n=== code\n~~~\n"
        converter = md_convert_setext_to_atx.SetextConverter()
        result = converter.convert_setext_to_atx(text)
        self.assertEqual(result, "# Title\n\n~~~\nsome\n=== code\n~~~\n")

    def test_heading_outside_code_fence_converted(self):
        """Test that headings outside code fences are still converted."""
        text = "Title\n======\n\nContent\n\n```\ncode\n```\n\nMore\n======\n"
        converter = md_convert_setext_to_atx.SetextConverter()
        result = converter.convert_setext_to_atx(text)
        self.assertEqual(result, "# Title\n\nContent\n\n```\ncode\n```\n\n# More\n")

    def test_code_fence_with_triple_backticks(self):
        """Test that code blocks with more than 3 backticks are preserved."""
        text = "Title\n======\n\n````\nsome\n=== code\n````\n"
        converter = md_convert_setext_to_atx.SetextConverter()
        result = converter.convert_setext_to_atx(text)
        self.assertEqual(result, "# Title\n\n````\nsome\n=== code\n````\n")


class TestSetextConverter(unittest.TestCase):
    """Tests for SetextConverter class."""

    def setUp(self):
        """Set up test directory."""
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        """Clean up test directory."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    def test_process_markdown_file(self):
        """Test processing a markdown file."""
        test_file = Path("test.md")
        test_file.write_text("Main Title\n======\n\nSome content\n", encoding="utf-8")

        converter = md_convert_setext_to_atx.SetextConverter(logger=MockLogger())
        converter.process_file(test_file, dry_run=False)

        self.assertEqual(test_file.read_text(encoding="utf-8"), "# Main Title\n\nSome content\n")
        self.assertEqual(converter.files_processed, 1)

    def test_process_non_markdown_file(self):
        """Test processing a non-markdown file is skipped."""
        test_file = Path("test.txt")
        test_file.write_text("Main Title\n======\n", encoding="utf-8")

        converter = md_convert_setext_to_atx.SetextConverter(logger=MockLogger())
        converter.process_file(test_file, dry_run=False)

        self.assertEqual(converter.files_skipped, 1)

    def test_dry_run_no_changes(self):
        """Test dry run mode does not modify files."""
        test_file = Path("test.md")
        test_file.write_text("Main Title\n======\n", encoding="utf-8")

        converter = md_convert_setext_to_atx.SetextConverter(logger=MockLogger())
        converter.process_file(test_file, dry_run=True)

        self.assertEqual(test_file.read_text(encoding="utf-8"), "Main Title\n======\n")
        self.assertEqual(converter.files_processed, 1)

    def test_no_changes_needed(self):
        """Test file with no setext headings is skipped."""
        test_file = Path("test.md")
        test_file.write_text("# Already ATX\n", encoding="utf-8")

        converter = md_convert_setext_to_atx.SetextConverter(logger=MockLogger())
        converter.process_file(test_file, dry_run=False)

        self.assertEqual(converter.files_skipped, 1)


class TestFixtures(unittest.TestCase):
    """Tests using fixture files."""

    def setUp(self):
        """Set up test directory."""
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)
        self.fixtures_dir = Path(__file__).parent / "fixtures"

    def tearDown(self):
        """Clean up test directory."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    def test_fixture_setext_h1(self):
        """Test fixture setext_h1.md."""
        shutil.copy(self.fixtures_dir / "setext_h1.md", Path("."))
        converter = md_convert_setext_to_atx.SetextConverter(logger=MockLogger())
        converter.process_file(Path("setext_h1.md"), dry_run=False)
        self.assertEqual(Path("setext_h1.md").read_text(encoding="utf-8"), "# Main Title\n\nContent here.\n")

    def test_fixture_setext_h2(self):
        """Test fixture setext_h2.md."""
        shutil.copy(self.fixtures_dir / "setext_h2.md", Path("."))
        converter = md_convert_setext_to_atx.SetextConverter(logger=MockLogger())
        converter.process_file(Path("setext_h2.md"), dry_run=False)
        self.assertEqual(Path("setext_h2.md").read_text(encoding="utf-8"), "## Sub Section\n\nContent here.\n")

    def test_fixture_mixed(self):
        """Test fixture setext_mixed.md."""
        shutil.copy(self.fixtures_dir / "setext_mixed.md", Path("."))
        converter = md_convert_setext_to_atx.SetextConverter(logger=MockLogger())
        converter.process_file(Path("setext_mixed.md"), dry_run=False)
        self.assertEqual(
            Path("setext_mixed.md").read_text(encoding="utf-8"),
            "# First Heading\n\n## Second Heading\n\n### Third (ATX)\n\n## Another Section (SetEx)\n\n### Sub Section (ATX)\n"
        )

    def test_fixture_with_front_matter(self):
        """Test fixture setext_with_front_matter.md preserves front matter."""
        shutil.copy(self.fixtures_dir / "setext_with_front_matter.md", Path("."))
        converter = md_convert_setext_to_atx.SetextConverter(logger=MockLogger())
        converter.process_file(Path("setext_with_front_matter.md"), dry_run=False)
        result = Path("setext_with_front_matter.md").read_text(encoding="utf-8")
        self.assertTrue(result.startswith("---\ntitle: Post with Front Matter"))
        self.assertIn("# Main Title", result)
        self.assertIn("## Sub Section", result)


if __name__ == "__main__":
    unittest.main()
