#!/usr/bin/env python3
"""Tests for md_category_tags module."""

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
    "md_category_tags", Path(__file__).parents[1] / "md-category-tags.py"
)
md_category_tags = importlib.util.module_from_spec(_SPEC)
sys.modules["md_category_tags"] = md_category_tags
_SPEC.loader.exec_module(md_category_tags)


class TestCategoryResolver(unittest.TestCase):
    """Tests for category extraction methods."""

    def test_extract_from_filename(self):
        """Test extracts category from date-category filename."""
        result = md_category_tags.CategoryResolver.from_filename(
            filename="2024-01-15_workout.md"
        )
        self.assertEqual(result, "workout")

    def test_extract_from_filename_no_match(self):
        """Test returns None for filenames without date-category pattern."""
        result = md_category_tags.CategoryResolver.from_filename(filename="notes.md")
        self.assertIsNone(result)

    def test_extract_from_title(self):
        """Test extracts category from a bare first-line date-category title."""
        result = md_category_tags.CategoryResolver.from_title(
            content="2024-01-15_reading\n\nbody"
        )
        self.assertEqual(result, "reading")

    def test_extract_from_title_no_match(self):
        """Test returns None when title is not date-category."""
        result = md_category_tags.CategoryResolver.from_title(content="# Hello World")
        self.assertIsNone(result)


class TestNoteTagger(unittest.TestCase):
    """Tests for the NoteTagger.add method."""

    def setUp(self):
        self.tagger = md_category_tags.NoteTagger()

    def test_prepends_to_existing_tag_line(self):
        """Test prepends category tag to existing tag line."""
        note = "## Note\n#old #note"
        updated, modified = self.tagger.add(note=note, category="workout")
        self.assertTrue(modified)
        self.assertEqual(updated, "## Note\n#workout #old #note")

    def test_skips_when_tag_present(self):
        """Test does not duplicate an existing category tag."""
        note = "## Note\n#workout #note"
        updated, modified = self.tagger.add(note=note, category="workout")
        self.assertFalse(modified)
        self.assertEqual(updated, note)

    def test_inserts_after_title(self):
        """Test inserts category tag after the note title."""
        note = "## My Note\n\nSome content"
        updated, modified = self.tagger.add(note=note, category="workout")
        self.assertTrue(modified)
        self.assertEqual(updated, "## My Note\n#workout\n\nSome content")

    def test_appends_when_no_title(self):
        """Test appends category tag at end when there is no title."""
        note = "Some content without heading"
        updated, modified = self.tagger.add(note=note, category="workout")
        self.assertTrue(modified)
        self.assertEqual(updated, "Some content without heading\n#workout")

    def test_no_category_returns_unchanged(self):
        """Test returns note unchanged when category is empty."""
        note = "## Note"
        updated, modified = self.tagger.add(note=note, category=None)
        self.assertFalse(modified)
        self.assertEqual(updated, note)

    def test_dry_run_does_not_modify(self):
        """Test dry run reports modification without changing content."""
        note = "## Note\n#old"
        updated, modified = self.tagger.add(note=note, category="workout", dry_run=True)
        self.assertTrue(modified)
        self.assertEqual(updated, note)


class TestProcessFile(unittest.TestCase):
    """Tests for process_file method."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)
        self.handler = md_category_tags.CategoryTagsAdder()

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

    def test_skips_file_without_category(self):
        """Test skips file without resolvable category."""
        filepath = Path("untagged.md")
        filepath.write_text("# Hello World", encoding="utf-8")
        self.handler.process_file(filepath)
        self.assertEqual(self.handler.files_skipped, 1)

    def test_adds_tag_from_filename(self):
        """Test adds category tag derived from filename."""
        filepath = Path("2024-01-15_workout.md")
        filepath.write_text("## Session\n#note", encoding="utf-8")
        self.handler.process_file(filepath)
        self.assertEqual(self.handler.files_updated, 1)
        self.assertIn("#workout", filepath.read_text(encoding="utf-8"))

    def test_adds_tag_from_title(self):
        """Test adds category tag derived from first-line title."""
        filepath = Path("notes.md")
        filepath.write_text("2024-01-15_reading\n\n## Book\n#old", encoding="utf-8")
        self.handler.process_file(filepath)
        self.assertEqual(self.handler.files_updated, 1)
        self.assertIn("#reading", filepath.read_text(encoding="utf-8"))

    def test_dry_run_no_write(self):
        """Test dry run does not write to disk."""
        filepath = Path("2024-01-15_workout.md")
        original = "## Session\n#note"
        filepath.write_text(original, encoding="utf-8")
        self.handler.process_file(filepath, dry_run=True)
        self.assertEqual(self.handler.files_updated, 1)
        self.assertEqual(filepath.read_text(encoding="utf-8"), original)


class TestCompletion(unittest.TestCase):
    """Tests for bash completion generation."""

    def test_generate_completion_script(self):
        """Test completion script contains known options."""
        script = md_category_tags.Kernel(
            author="TangoMan75",
            title="t",
            description="d",
        ).generate_completion()
        self.assertIn("--completion", script)
        self.assertIn("--recursive", script)
        self.assertIn("complete -f", script)


class TestIntegration(unittest.TestCase):
    """Integration tests for the script."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    def test_cli_adds_tag(self):
        """Test CLI adds a tag to a file."""
        filepath = Path("2024-01-15_workout.md")
        filepath.write_text("## Session\n#note", encoding="utf-8")
        with patch.object(sys, "argv", ["script", str(filepath)]):
            md_category_tags.Kernel(
                author="TangoMan75",
                title="Markdown Category Tags",
                description="desc",
            ).run(md_category_tags.CategoryTagsAdder)
        self.assertIn("#workout", filepath.read_text(encoding="utf-8"))

    def test_cli_completion(self):
        """Test CLI prints completion script and exits early."""
        with patch.object(sys, "argv", ["script", "--completion"]):
            with patch("sys.stdout") as mock_stdout:
                md_category_tags.Kernel(
                    author="TangoMan75",
                    title="Markdown Category Tags",
                    description="desc",
                ).run(md_category_tags.CategoryTagsAdder)
                written = "".join(
                    str(call.args[0]) for call in mock_stdout.write.call_args_list
                )
                self.assertIn("complete -f", written)

    def test_cli_quiet(self):
        """Test CLI updates file in quiet mode."""
        filepath = Path("2024-01-15_workout.md")
        filepath.write_text("## Session\n#note", encoding="utf-8")
        with patch.object(sys, "argv", ["script", str(filepath), "--quiet"]):
            md_category_tags.Kernel(
                author="TangoMan75",
                title="Markdown Category Tags",
                description="desc",
            ).run(md_category_tags.CategoryTagsAdder)
        self.assertIn("#workout", filepath.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
