#!/usr/bin/env python3
"""Tests for md_rename module."""

import datetime
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))

_SPEC = importlib.util.spec_from_file_location(
    "md_rename", Path(__file__).parents[1] / "md-rename.py"
)
md_rename = importlib.util.module_from_spec(_SPEC)
sys.modules["md_rename"] = md_rename
_SPEC.loader.exec_module(md_rename)


sys.path.insert(0, str(Path(__file__).parent.parent))


class TestExtractFrontMatter(unittest.TestCase):
    """Tests for _extract_front_matter method."""

    def setUp(self):
        self.handler = md_rename.MarkdownRenamer()

    def test_extract_valid_front_matter(self):
        """Test extracting valid front matter."""
        content = """---
title: Test Title
date: 2024-01-15
author: John Doe
---
# Content"""
        result = self.handler._extract_front_matter(content)
        self.assertIsNotNone(result)
        self.assertIn("title: Test Title", result)
        self.assertIn("date: 2024-01-15", result)
        self.assertIn("author: John Doe", result)

    def test_extract_no_front_matter(self):
        """Test returns None when no front matter."""
        content = "# Hello World"
        result = self.handler._extract_front_matter(content)
        self.assertIsNone(result)

    def test_extract_empty_front_matter(self):
        """Test handles empty front matter."""
        content = "---\n---\n# Content"
        result = self.handler._extract_front_matter(content)
        self.assertIsNone(result)


class TestValidateFrontMatter(unittest.TestCase):
    """Tests for _validate_front_matter method."""

    def setUp(self):
        self.handler = md_rename.MarkdownRenamer()

    def test_valid_front_matter(self):
        """Test returns empty list for valid front matter."""
        data = {"date": "2024-01-15", "title": "Test", "author": "John"}
        result = self.handler._validate_front_matter(data)
        self.assertEqual(result, [])

    def test_missing_date(self):
        """Test detects missing date."""
        data = {"title": "Test", "author": "John"}
        result = self.handler._validate_front_matter(data)
        self.assertIn("date", result)

    def test_missing_title(self):
        """Test detects missing title."""
        data = {"date": "2024-01-15", "author": "John"}
        result = self.handler._validate_front_matter(data)
        self.assertIn("title", result)

    def test_missing_author(self):
        """Test detects missing author."""
        data = {"date": "2024-01-15", "title": "Test"}
        result = self.handler._validate_front_matter(data)
        self.assertIn("author", result)

    def test_missing_multiple_fields(self):
        """Test detects multiple missing fields."""
        data = {}
        result = self.handler._validate_front_matter(data)
        self.assertEqual(len(result), 3)


class TestGetDateString(unittest.TestCase):
    """Tests for _get_date_string method."""

    def setUp(self):
        self.handler = md_rename.MarkdownRenamer()

    def test_string_date(self):
        """Test passes through string date."""
        result = self.handler._get_date_string("2024-01-15")
        self.assertEqual(result, "2024-01-15")

    def test_datetime_object(self):
        """Test converts datetime to string."""
        date_obj = datetime.date(2024, 1, 15)
        result = self.handler._get_date_string(date_obj)
        self.assertEqual(result, "2024-01-15")


class TestGetUniqueFilename(unittest.TestCase):
    """Tests for get_unique_filename method (static method from FileHandler)."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.handler = md_rename.MarkdownRenamer()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_no_existing_file(self):
        """Test returns original filename when no conflict."""
        path = Path(self.test_dir) / "test.md"
        path.touch()
        result = md_rename.FileHandler.get_unique_filename(path=path, base_filename="new-name.md")
        self.assertEqual(result.name, "new-name.md")

    def test_with_existing_file(self):
        """Test appends counter when file exists."""
        path = Path(self.test_dir) / "test.md"
        path.touch()
        existing = Path(self.test_dir) / "2024-01-15-john-test.md"
        existing.touch()

        result = md_rename.FileHandler.get_unique_filename(
            path=path, base_filename="2024-01-15-john-test.md"
        )
        self.assertEqual(result.name, "2024-01-15-john-test_1.md")

    def test_with_multiple_existing(self):
        """Test handles multiple existing files."""
        path = Path(self.test_dir) / "test.md"
        path.touch()
        (Path(self.test_dir) / "2024-01-15-john-test.md").touch()
        (Path(self.test_dir) / "2024-01-15-john-test_1.md").touch()

        result = md_rename.FileHandler.get_unique_filename(
            path=path, base_filename="2024-01-15-john-test.md"
        )
        self.assertEqual(result.name, "2024-01-15-john-test_2.md")


class TestStringSlugify(unittest.TestCase):
    """Tests for String.slugify method."""

    def test_simple_string(self):
        """Test slugifies simple string."""
        result = md_rename.String.slugify("Hello World")
        self.assertEqual(result, "hello-world")

    def test_special_characters(self):
        """Test removes special characters."""
        result = md_rename.String.slugify("Test @#$% Title")
        self.assertEqual(result, "test-title")

    def test_unicode_characters(self):
        """Test normalizes unicode."""
        result = md_rename.String.slugify("Café")
        self.assertEqual(result, "cafe")

    def test_multiple_hyphens(self):
        """Test collapses multiple hyphens."""
        result = md_rename.String.slugify("Test   Title")
        self.assertEqual(result, "test-title")


class TestProcessFile(unittest.TestCase):
    """Tests for process_file method."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)
        self.handler = md_rename.MarkdownRenamer()

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    def test_skips_non_markdown(self):
        """Test skips non-markdown files."""
        filepath = Path("test.txt")
        filepath.write_text("content", encoding="utf-8")

        self.handler.process_file(filepath)

        self.assertEqual(self.handler.files_processed, 1)
        self.assertEqual(self.handler.files_skipped, 1)

    def test_skips_file_without_front_matter(self):
        """Test skips file without front matter."""
        filepath = Path("test.md")
        filepath.write_text("# Hello World", encoding="utf-8")

        self.handler.process_file(filepath)

        self.assertEqual(self.handler.files_processed, 1)
        self.assertEqual(self.handler.files_skipped, 1)

    def test_skips_file_with_incomplete_front_matter(self):
        """Test skips file with incomplete front matter."""
        filepath = Path("test.md")
        filepath.write_text(
            "---\ntitle: Test\n---\n# Content",
            encoding="utf-8"
        )

        self.handler.process_file(filepath)

        self.assertEqual(self.handler.files_processed, 1)
        self.assertEqual(self.handler.files_skipped, 1)

    def test_renames_file_with_valid_front_matter(self):
        """Test renames file with valid front matter."""
        filepath = Path("test.md")
        filepath.write_text(
            "---\ntitle: Test Title\ndate: 2024-01-15\nauthor: John Doe\n---\n# Content",
            encoding="utf-8"
        )

        self.handler.process_file(filepath)

        new_path = Path(self.test_dir) / "2024-01-15-john-doe-test-title.md"
        self.assertTrue(new_path.exists())

    def test_skips_already_correct_filename(self):
        """Test skips file with already correct name."""
        filepath = Path("2024-01-15-john-doe-test-title.md")
        filepath.write_text(
            "---\ntitle: Test Title\ndate: 2024-01-15\nauthor: John Doe\n---\n# Content",
            encoding="utf-8"
        )

        self.handler.process_file(filepath)

        self.assertEqual(self.handler.files_skipped, 1)

    def test_dry_run_no_rename(self):
        """Test dry run does not actually rename."""
        filepath = Path("test.md")
        filepath.write_text(
            "---\ntitle: Test Title\ndate: 2024-01-15\nauthor: John Doe\n---\n# Content",
            encoding="utf-8"
        )

        self.handler.process_file(filepath, dry_run=True)

        self.assertTrue(filepath.exists())
        new_path = Path(self.test_dir) / "2024-01-15-john-doe-test-title.md"
        self.assertFalse(new_path.exists())


class TestHandlerClass(unittest.TestCase):
    """Tests for MarkdownRenamer class."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    def test_handler_initialization(self):
        """Test handler initializes with default values."""
        handler = md_rename.MarkdownRenamer()
        self.assertEqual(handler.files_processed, 0)
        self.assertEqual(handler.files_skipped, 0)
        self.assertEqual(handler.errors, 0)

    def test_process_file_increments_counter(self):
        """Test process_file increments files_processed."""
        filepath = Path("test.txt")
        filepath.write_text("content", encoding="utf-8")

        handler = md_rename.MarkdownRenamer()
        handler.process_file(filepath)

        self.assertEqual(handler.files_processed, 1)


class TestIntegration(unittest.TestCase):
    """Integration tests for the script."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    def test_cli_rename_file(self):
        """Test CLI renames markdown file."""
        filepath = Path("test_cli_rename.md")
        filepath.write_text(
            "---\ntitle: Test Document\ndate: 2024-01-15\nauthor: John Doe\n---\n# Content",
            encoding="utf-8"
        )

        with patch.object(sys, "argv", ["script", str(filepath)]):
            md_rename.Kernel(
                author='TangoMan75',
                title='Markdown Renamer',
                description='Rename markdown files.',
            ).run(md_rename.MarkdownRenamer)

        new_path = Path(self.test_dir) / "2024-01-15-john-doe-test-document.md"
        self.assertTrue(new_path.exists())

    def test_cli_missing_file(self):
        """Test CLI handles missing file gracefully."""
        with patch.object(sys, "argv", ["script", "nonexistent.md"]):
            md_rename.Kernel(
                author='TangoMan75',
                title='Markdown Renamer',
                description='Rename markdown files.',
            ).run(md_rename.MarkdownRenamer)

    def test_cli_non_markdown_file(self):
        """Test CLI skips non-markdown file."""
        filepath = Path("test.txt")
        filepath.write_text("content", encoding="utf-8")

        with patch.object(sys, "argv", ["script", str(filepath)]):
            md_rename.Kernel(
                author='TangoMan75',
                title='Markdown Renamer',
                description='Rename markdown files.',
            ).run(md_rename.MarkdownRenamer)


if __name__ == "__main__":
    unittest.main()
