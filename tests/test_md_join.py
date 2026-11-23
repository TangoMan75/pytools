#!/usr/bin/env python3
"""Tests for md_join module."""

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
    "md_join", Path(__file__).parents[1] / "md-join.py"
)
md_join = importlib.util.module_from_spec(_SPEC)
sys.modules["md_join"] = md_join
_SPEC.loader.exec_module(md_join)



class TestRemoveFrontMatter(unittest.TestCase):
    """Tests for _remove_front_matter static method."""

    def test_no_front_matter(self):
        """Test returns original content when no front matter."""
        content = "## Section\nContent here."
        result = md_join.MarkdownJoiner.remove_front_matter(content)
        self.assertEqual(result, content)

    def test_with_front_matter(self):
        """Test removes front matter from content."""
        content = "---\ntitle: Test\ndate: 2023-10-25\n---\n## Section\nContent"
        result = md_join.MarkdownJoiner.remove_front_matter(content)
        self.assertEqual(result, "## Section\nContent")

    def test_front_matter_with_empty_body(self):
        """Test handles front matter with empty body."""
        content = "---\ntitle: Test\n---\n"
        result = md_join.MarkdownJoiner.remove_front_matter(content)
        self.assertEqual(result, "")

    def test_front_matter_not_at_start(self):
        """Test content not starting with --- is returned as-is."""
        content = "Some text\n---\ntitle: Test\n---\n"
        result = md_join.MarkdownJoiner.remove_front_matter(content)
        self.assertEqual(result, content)

    def test_incomplete_front_matter(self):
        """Test returns content when front matter is incomplete."""
        content = "---\ntitle: Test"
        result = md_join.MarkdownJoiner.remove_front_matter(content)
        self.assertEqual(result, content)

    def test_front_matter_multiple_dashes(self):
        """Test handles multiple --- separators."""
        content = "---\ntitle: Test\n---\n---\n## Section\nContent"
        result = md_join.MarkdownJoiner.remove_front_matter(content)
        self.assertEqual(result, "---\n## Section\nContent")

    def test_strips_leading_newlines(self):
        """Test strips leading newlines after front matter."""
        content = "---\ntitle: Test\n---\n\n\n## Section\nContent"
        result = md_join.MarkdownJoiner.remove_front_matter(content)
        self.assertTrue(result.startswith("## Section"))


class TestGetDefaultOutputFilename(unittest.TestCase):
    """Tests for _get_default_output_filename static method."""

    def test_returns_iso_date_filename(self):
        """Test returns filename with today's date in ISO format."""
        result = md_join.MarkdownJoiner.get_default_output_filename()
        today = date.today().isoformat()
        self.assertEqual(result, f"{today}.md")

    def test_filename_format(self):
        """Test filename has correct format."""
        result = md_join.MarkdownJoiner.get_default_output_filename()
        self.assertRegex(result, r"^\d{4}-\d{2}-\d{2}\.md$")


class TestJoinFiles(unittest.TestCase):
    """Tests for join_files method."""

    def setUp(self):
        """Set up test directory."""
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        """Clean up test directory."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    def test_join_empty_directory(self):
        """Test joining empty directory shows warning."""
        handler = md_join.MarkdownJoiner()
        handler.join_files(
            Path("."),
            output_path=Path("output.md"),
            include="*.md",
            exclude=None,
            recursive=False,
            dry_run=False,
            verbose=0,
        )
        self.assertFalse(Path("output.md").exists())

    def test_join_single_file(self):
        """Test joining single markdown file."""
        filepath = Path("test1.md")
        filepath.write_text("## Content\nSome content.", encoding="utf-8")

        handler = md_join.MarkdownJoiner()
        handler.join_files(
            Path("."),
            output_path=Path("output.md"),
            include="*.md",
            exclude=None,
            recursive=False,
            dry_run=False,
            verbose=0,
        )

        self.assertTrue(Path("output.md").exists())
        content = Path("output.md").read_text(encoding="utf-8")
        self.assertIn("## Content", content)

    def test_join_multiple_files(self):
        """Test joining multiple markdown files."""
        Path("test1.md").write_text("## Section One\nContent one.", encoding="utf-8")
        Path("test2.md").write_text("## Section Two\nContent two.", encoding="utf-8")

        handler = md_join.MarkdownJoiner()
        handler.join_files(
            Path("."),
            output_path=Path("output.md"),
            include="*.md",
            exclude=None,
            recursive=False,
            dry_run=False,
            verbose=0,
        )

        content = Path("output.md").read_text(encoding="utf-8")
        self.assertIn("Section One", content)
        self.assertIn("Section Two", content)

    def test_join_removes_front_matter(self):
        """Test joining removes YAML front matter."""
        Path("test.md").write_text(
            "---\ntitle: Test\ndate: 2023-10-25\n---\n## Section\nContent.",
            encoding="utf-8"
        )

        handler = md_join.MarkdownJoiner()
        handler.join_files(
            Path("."),
            output_path=Path("output.md"),
            include="*.md",
            exclude=None,
            recursive=False,
            dry_run=False,
            verbose=0,
        )

        content = Path("output.md").read_text(encoding="utf-8")
        self.assertNotIn("title: Test", content)
        self.assertIn("## Section", content)

    def test_join_excludes_non_markdown(self):
        """Test excludes non-markdown files."""
        Path("test.md").write_text("## Content\nContent.", encoding="utf-8")
        Path("test.txt").write_text("Text content.", encoding="utf-8")

        handler = md_join.MarkdownJoiner()
        handler.join_files(
            Path("."),
            output_path=Path("output.md"),
            include="*.md",
            exclude=None,
            recursive=False,
            dry_run=False,
            verbose=0,
        )

        content = Path("output.md").read_text(encoding="utf-8")
        self.assertIn("## Content", content)
        self.assertNotIn("Text content", content)

    def test_join_with_exclude_pattern(self):
        """Test joining with exclude pattern."""
        Path("include.md").write_text("## Include\nContent.", encoding="utf-8")
        Path("exclude.md").write_text("## Exclude\nContent.", encoding="utf-8")

        handler = md_join.MarkdownJoiner()
        handler.join_files(
            Path("."),
            output_path=Path("output.md"),
            include="*.md",
            exclude="exclude.md",
            recursive=False,
            dry_run=False,
            verbose=0,
        )

        content = Path("output.md").read_text(encoding="utf-8")
        self.assertIn("Include", content)
        self.assertNotIn("Exclude", content)

    def test_join_recursive(self):
        """Test joining with recursive traversal."""
        subdir = Path("subdir")
        subdir.mkdir()
        Path("test1.md").write_text("## Content\nContent.", encoding="utf-8")
        (subdir / "test2.md").write_text("## Subdir Content\nContent.", encoding="utf-8")

        handler = md_join.MarkdownJoiner()
        handler.join_files(
            Path("."),
            output_path=Path("output.md"),
            include="*.md",
            exclude=None,
            recursive=True,
            dry_run=False,
            verbose=0,
        )

        content = Path("output.md").read_text(encoding="utf-8")
        self.assertIn("## Content", content)
        self.assertIn("## Subdir Content", content)

    def test_join_non_recursive(self):
        """Test non-recursive skips subdirectories."""
        subdir = Path("subdir")
        subdir.mkdir()
        Path("test1.md").write_text("## Content\nContent.", encoding="utf-8")
        (subdir / "test2.md").write_text("## Subdir Content\nContent.", encoding="utf-8")

        handler = md_join.MarkdownJoiner()
        handler.join_files(
            Path("."),
            output_path=Path("output.md"),
            include="*.md",
            exclude=None,
            recursive=False,
            dry_run=False,
            verbose=0,
        )

        content = Path("output.md").read_text(encoding="utf-8")
        self.assertIn("## Content", content)
        self.assertNotIn("Subdir Content", content)

    def test_join_dry_run(self):
        """Test dry run does not create output file."""
        Path("test.md").write_text("## Content\nContent.", encoding="utf-8")

        handler = md_join.MarkdownJoiner()
        handler.join_files(
            Path("."),
            output_path=Path("output.md"),
            include="*.md",
            exclude=None,
            recursive=False,
            dry_run=True,
            verbose=0,
        )

        self.assertFalse(Path("output.md").exists())

    def test_join_empty_content_files(self):
        """Test handles files with empty content after front matter removal."""
        Path("test1.md").write_text("", encoding="utf-8")
        Path("test2.md").write_text("---\ntitle: Test\n---\n", encoding="utf-8")

        handler = md_join.MarkdownJoiner()
        handler.join_files(
            Path("."),
            output_path=Path("output.md"),
            include="*.md",
            exclude=None,
            recursive=False,
            dry_run=False,
            verbose=0,
        )

        output_content = Path("output.md").read_text(encoding="utf-8") if Path("output.md").exists() else ""
        self.assertEqual(output_content, "")

    def test_join_sorts_files(self):
        """Test joins files in sorted order."""
        Path("z_file.md").write_text("## Z Content\nZ.", encoding="utf-8")
        Path("a_file.md").write_text("## A Content\nA.", encoding="utf-8")

        handler = md_join.MarkdownJoiner()
        handler.join_files(
            Path("."),
            output_path=Path("output.md"),
            include="*.md",
            exclude=None,
            recursive=False,
            dry_run=False,
            verbose=0,
        )

        content = Path("output.md").read_text(encoding="utf-8")
        a_pos = content.find("A Content")
        z_pos = content.find("Z Content")
        self.assertLess(a_pos, z_pos)


class TestProcessFile(unittest.TestCase):
    """Tests for process_file method."""

    def setUp(self):
        """Set up test directory."""
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        """Clean up test directory."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    def test_process_file_basic(self):
        """Test processing single markdown file."""
        filepath = Path("test.md")
        filepath.write_text("## Content\nSome content.", encoding="utf-8")

        handler = md_join.MarkdownJoiner()
        handler.process_file(filepath)

        self.assertEqual(handler.files_processed, 1)
        output_file = Path(md_join.MarkdownJoiner.get_default_output_filename())
        self.assertTrue(output_file.exists())

    def test_process_file_with_front_matter(self):
        """Test processing file with front matter."""
        filepath = Path("test.md")
        filepath.write_text(
            "---\ntitle: Test\n---\n## Section\nContent.",
            encoding="utf-8"
        )

        handler = md_join.MarkdownJoiner()
        handler.process_file(filepath)

        output_file = Path(md_join.MarkdownJoiner.get_default_output_filename())
        content = output_file.read_text(encoding="utf-8")
        self.assertIn("## Section", content)
        self.assertNotIn("title: Test", content)

    def test_process_file_with_output(self):
        """Test processing file with custom output path."""
        filepath = Path("test.md")
        filepath.write_text("## Content\nContent.", encoding="utf-8")

        handler = md_join.MarkdownJoiner()
        handler.process_file(filepath, output="custom.md")

        self.assertTrue(Path("custom.md").exists())

    def test_process_file_appends_to_existing(self):
        """Test appends content to existing output file."""
        Path("existing.md").write_text("## First\nFirst content.", encoding="utf-8")
        filepath = Path("test.md")
        filepath.write_text("## Second\nSecond content.", encoding="utf-8")

        handler = md_join.MarkdownJoiner()
        handler.process_file(filepath, output="existing.md")

        content = Path("existing.md").read_text(encoding="utf-8")
        self.assertIn("## First", content)
        self.assertIn("## Second", content)

    def test_process_file_skips_non_markdown(self):
        """Test skipping non-markdown files."""
        filepath = Path("test.txt")
        filepath.write_text("content", encoding="utf-8")

        handler = md_join.MarkdownJoiner()
        handler.process_file(filepath)

        self.assertEqual(handler.files_skipped, 1)

    def test_process_file_dry_run(self):
        """Test dry run does not write file."""
        filepath = Path("test.md")
        filepath.write_text("## Content\nContent.", encoding="utf-8")

        handler = md_join.MarkdownJoiner()
        handler.process_file(filepath, dry_run=True)

        output_file = Path(md_join.MarkdownJoiner.get_default_output_filename())
        self.assertFalse(output_file.exists())

    def test_process_file_empty_content(self):
        """Test skipping files with empty content."""
        filepath = Path("test.md")
        filepath.write_text("", encoding="utf-8")

        handler = md_join.MarkdownJoiner()
        handler.process_file(filepath)

        self.assertEqual(handler.files_skipped, 1)


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

    def test_cli_with_single_file(self):
        """Test CLI processes single file."""
        filepath = Path("notes.md")
        filepath.write_text("## Notes\nMy notes.", encoding="utf-8")

        with patch("sys.argv", ["script", str(filepath), "--output", "output.md"]):
            md_join.Kernel(
                author="TangoMan75",
                title="Test",
                description="Test",
            ).run(md_join.MarkdownJoiner)

        self.assertTrue(Path("output.md").exists())

    def test_cli_with_directory(self):
        """Test CLI processes directory."""
        Path("file1.md").write_text("## File 1\nContent 1.", encoding="utf-8")
        Path("file2.md").write_text("## File 2\nContent 2.", encoding="utf-8")

        with patch("sys.argv", ["script", ".", "--output", "output.md"]):
            md_join.Kernel(
                author="TangoMan75",
                title="Test",
                description="Test",
            ).run(md_join.MarkdownJoiner)

        self.assertTrue(Path("output.md").exists())
        content = Path("output.md").read_text(encoding="utf-8")
        self.assertIn("File 1", content)
        self.assertIn("File 2", content)

    def test_cli_recursive_directory(self):
        """Test CLI with recursive directory traversal."""
        subdir = Path("docs")
        subdir.mkdir()
        Path("readme.md").write_text("## README\nOverview.", encoding="utf-8")
        (subdir / "guide.md").write_text("## Guide\nInstructions.", encoding="utf-8")

        with patch("sys.argv", ["script", ".", "--output", "output.md", "--recursive"]):
            md_join.Kernel(
                author="TangoMan75",
                title="Test",
                description="Test",
            ).run(md_join.MarkdownJoiner)

        content = Path("output.md").read_text(encoding="utf-8")
        self.assertIn("README", content)
        self.assertIn("Guide", content)


if __name__ == "__main__":
    unittest.main()
