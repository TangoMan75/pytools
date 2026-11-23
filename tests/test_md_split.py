#!/usr/bin/env python3
"""Tests for md_split module."""

import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))

_SPEC = importlib.util.spec_from_file_location(
    "md_split", Path(__file__).parents[1] / "md-split.py"
)
md_split = importlib.util.module_from_spec(_SPEC)
sys.modules["md_split"] = md_split
_SPEC.loader.exec_module(md_split)



class TestParseFrontMatter(unittest.TestCase):
    """Tests for MarkdownUtils.parse_front_matter method."""

    def test_no_front_matter(self):
        """Test parsing content without front matter."""
        content = "## Section\nContent here."
        front_matter, remaining = md_split.MarkdownUtils.parse_front_matter(content)
        self.assertIsNone(front_matter)
        self.assertEqual(remaining, content)

    def test_with_front_matter(self):
        """Test parsing content with front matter."""
        content = "---\ndate: 2023-10-25\ntitle: Test\n---\n## Section\nContent"
        front_matter, _ = md_split.MarkdownUtils.parse_front_matter(content)
        assert front_matter is not None
        self.assertEqual(front_matter["title"], "Test")
        self.assertIsInstance(front_matter["date"], date)

    def test_front_matter_with_datetime_object(self):
        """Test parsing front matter with datetime.date object."""
        content = "---\ndate: 2024-01-01\n---\n## Section\nContent"
        front_matter, _ = md_split.MarkdownUtils.parse_front_matter(content)
        assert front_matter is not None
        self.assertIsInstance(front_matter["date"], date)
        self.assertEqual(front_matter["date"], date(2024, 1, 1))


class TestGetDateFromFrontMatter(unittest.TestCase):
    """Tests for MarkdownUtils.get_date_from_front_matter method."""

    def test_returns_date_string(self):
        """Test returns date string from front matter."""
        front_matter = {"date": "2023-10-25"}
        result = md_split.MarkdownUtils.get_date_from_front_matter(front_matter)
        self.assertEqual(result, "2023-10-25")

    def test_returns_none_when_no_date(self):
        """Test returns None when no date in front matter."""
        front_matter = {"title": "Test"}
        result = md_split.MarkdownUtils.get_date_from_front_matter(front_matter)
        self.assertIsNone(result)

    def test_returns_none_when_no_front_matter(self):
        """Test returns None when front matter is None."""
        result = md_split.MarkdownUtils.get_date_from_front_matter(None)
        self.assertIsNone(result)


class TestGetDateFromFile(unittest.TestCase):
    """Tests for MarkdownUtils.get_date_from_file method."""

    def test_returns_iso_format(self):
        """Test returns date in ISO format."""
        filepath = Path(__file__)
        result = md_split.MarkdownUtils.get_date_from_file(filepath)
        self.assertRegex(result, r"^\d{4}-\d{2}-\d{2}$")


class TestGetDateFromFilename(unittest.TestCase):
    """Tests for MarkdownUtils.get_date_from_filename method."""

    def test_extracts_date_from_filename(self):
        """Test extracts YYYY-MM-DD from filename."""
        filepath = Path("2024-01-15_journal.md")
        result = md_split.MarkdownUtils.get_date_from_filename(filepath)
        self.assertEqual(result, "2024-01-15")

    def test_returns_none_without_date_prefix(self):
        """Test returns None when no date prefix."""
        filepath = Path("my-notes.md")
        result = md_split.MarkdownUtils.get_date_from_filename(filepath)
        self.assertIsNone(result)

    def test_extracts_date_without_validation(self):
        """Test extracts date pattern without validating date values."""
        filepath = Path("2024-13-01_invalid.md")
        result = md_split.MarkdownUtils.get_date_from_filename(filepath)
        self.assertEqual(result, "2024-13-01")

    def test_handles_date_with_underscore(self):
        """Test handles date followed by underscore."""
        filepath = Path("2023-12-25_notes.md")
        result = md_split.MarkdownUtils.get_date_from_filename(filepath)
        self.assertEqual(result, "2023-12-25")


class TestSplitByH2(unittest.TestCase):
    """Tests for MarkdownUtils.split_by_h2 method."""

    def test_single_section(self):
        """Test splitting with single H2 section."""
        content = "## Section One\nContent here."
        result = md_split.MarkdownUtils.split_by_h2(content)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], "Section One")
        self.assertEqual(result[0][1], "## Section One\nContent here.")

    def test_multiple_sections(self):
        """Test splitting with multiple H2 sections."""
        content = "## Section One\nContent one.\n## Section Two\nContent two."
        result = md_split.MarkdownUtils.split_by_h2(content)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0][0], "Section One")
        self.assertEqual(result[0][1], "## Section One\nContent one.")
        self.assertEqual(result[1][0], "Section Two")
        self.assertEqual(result[1][1], "## Section Two\nContent two.")

    def test_no_h2_sections(self):
        """Test returns full content when no H2 sections."""
        content = "Some content without headers."
        result = md_split.MarkdownUtils.split_by_h2(content)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], "content")
        self.assertEqual(result[0][1], "Some content without headers.")

    def test_ignores_h2_in_code_blocks(self):
        """Test H2 inside code blocks are not treated as section dividers."""
        content = "## Title One\nContent.\n```\n## Should Be Ignored\n```\n## Title Two\nMore content."
        result = md_split.MarkdownUtils.split_by_h2(content)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0][0], "Title One")
        self.assertEqual(result[0][1], "## Title One\nContent.\n```\n## Should Be Ignored\n```")
        self.assertEqual(result[1][0], "Title Two")
        self.assertEqual(result[1][1], "## Title Two\nMore content.")

    def test_preserves_code_block_content_in_sections(self):
        """Test code block content is preserved in output."""
        content = "## Section One\nSome text.\n```\n## Ignored Header\ncode here\n```\nMore text.\n## Section Two\nEnd content."
        result = md_split.MarkdownUtils.split_by_h2(content)
        self.assertEqual(len(result), 2)
        self.assertIn("```", result[0][1])
        self.assertIn("## Ignored Header", result[0][1])
        self.assertIn("code here", result[0][1])

    def test_handles_multiple_code_blocks(self):
        """Test multiple code blocks in different sections."""
        content = "## One\n```python\n## Ignore\n```\n## Two\n```bash\n## Also Ignore\n```\n## Three"
        result = md_split.MarkdownUtils.split_by_h2(content)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0][0], "One")
        self.assertEqual(result[1][0], "Two")
        self.assertEqual(result[2][0], "Three")


class TestIntegration(unittest.TestCase):
    """Integration tests for the script."""

    def setUp(self):
        """Set up test directory."""
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        """Clean up test directory."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    def test_scenario_date_from_front_matter(self):
        """Test Scenario: date from YAML front matter."""
        filepath = Path("journal.md")
        filepath.write_text(
            "---\ndate: 2023-10-25\ntitle: My Collection\n---\n## Ideas\nSection content.",
            encoding="utf-8"
        )

        with patch("sys.argv", ["script", str(filepath)]):
            md_split.Kernel(
                author='TangoMan75',
                title='Markdown Splitter',
                description='Test',
            ).run(md_split.MarkdownSplitter)

        self.assertTrue(Path("2023-10-25_ideas.md").exists())

    def test_scenario_handling_duplicates(self):
        """Test Scenario: handling duplicate section titles."""
        filepath = Path("journal.md")
        filepath.write_text(
            "---\ndate: 2023-12-25\n---\n## Gift List\nFirst list.\n## Gift List\nSecond list.",
            encoding="utf-8"
        )

        with patch("sys.argv", ["script", str(filepath)]):
            md_split.Kernel(
                author='TangoMan75',
                title='Markdown Splitter',
                description='Test',
            ).run(md_split.MarkdownSplitter)

        self.assertTrue(Path("2023-12-25_gift-list.md").exists())
        self.assertTrue(Path("2023-12-25_gift-list_1.md").exists())

    def test_scenario_complex_sluggification(self):
        """Test Scenario: complex sluggification with special chars."""
        filepath = Path("journal.md")
        filepath.write_text(
            "---\ndate: 2024-03-24\n---\n## Update: Project Alpha & Beta!\nContent.",
            encoding="utf-8"
        )

        with patch("sys.argv", ["script", str(filepath)]):
            md_split.Kernel(
                author='TangoMan75',
                title='Markdown Splitter',
                description='Test',
            ).run(md_split.MarkdownSplitter)

        self.assertTrue(Path("2024-03-24_update-project-alpha-beta.md").exists())

if __name__ == "__main__":
    unittest.main()
