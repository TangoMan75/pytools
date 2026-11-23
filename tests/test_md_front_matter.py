#!/usr/bin/env python3
"""Tests for md_front_matter module."""

import importlib.util
import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))

_SPEC = importlib.util.spec_from_file_location(
    "md_front_matter", Path(__file__).parents[1] / "md-front-matter.py"
)
md_front_matter = importlib.util.module_from_spec(_SPEC)
sys.modules["md_front_matter"] = md_front_matter
_SPEC.loader.exec_module(md_front_matter)

class TestGetTitleFromFilename(unittest.TestCase):
    """Tests for get_title_from_filename method."""

    def setUp(self):
        self.handler = md_front_matter.FrontMatterHandler()

    def test_simple_filename(self):
        """Test title extraction from simple filename."""
        filepath = Path("test.md")
        result = self.handler.get_title_from_filename(filepath=filepath)
        self.assertEqual(result, "Test")

    def test_filename_with_hyphens(self):
        """Test title extraction with hyphens."""
        filepath = Path("my-document.md")
        result = self.handler.get_title_from_filename(filepath=filepath)
        self.assertEqual(result, "My Document")

    def test_filename_with_underscores(self):
        """Test title extraction with underscores."""
        filepath = Path("my_document.md")
        result = self.handler.get_title_from_filename(filepath=filepath)
        self.assertEqual(result, "My Document")

    def test_filename_with_hyphens_and_underscores(self):
        """Test title extraction with both hyphens and underscores."""
        filepath = Path("my_interesting-document.md")
        result = self.handler.get_title_from_filename(filepath=filepath)
        self.assertEqual(result, "My Interesting Document")

    def test_filename_with_date_prefix(self):
        """Test title extraction with date prefix."""
        filepath = Path("2024-01-15-my-notes.md")
        result = self.handler.get_title_from_filename(filepath=filepath)
        self.assertEqual(result, "My Notes")

    def test_filename_with_date_prefix_underscore(self):
        """Test title extraction with date prefix and underscore separator."""
        filepath = Path("2023-12-25_project-ideas.md")
        result = self.handler.get_title_from_filename(filepath=filepath)
        self.assertEqual(result, "Project Ideas")


class TestGetDateFromFilename(unittest.TestCase):
    """Tests for get_date_from_filename method."""

    def setUp(self):
        self.handler = md_front_matter.FrontMatterHandler()

    def test_no_date_prefix(self):
        """Test returns None when no date prefix."""
        filepath = Path("my-document.md")
        result = self.handler.get_date_from_filename(filepath=filepath)
        self.assertIsNone(result)

    def test_date_prefix_hyphen(self):
        """Test extracts date from hyphen-separated prefix."""
        filepath = Path("2024-01-15-my-notes.md")
        result = self.handler.get_date_from_filename(filepath=filepath)
        self.assertEqual(result, "2024-01-15")

    def test_date_prefix_underscore(self):
        """Test extracts date from underscore-separated prefix."""
        filepath = Path("2023-12-25_project-ideas.md")
        result = self.handler.get_date_from_filename(filepath=filepath)
        self.assertEqual(result, "2023-12-25")

    def test_date_prefix_no_separator(self):
        """Test extracts date from prefix with no separator."""
        filepath = Path("2024-01-15.md")
        result = self.handler.get_date_from_filename(filepath=filepath)
        self.assertEqual(result, "2024-01-15")


class TestGetDateFromFile(unittest.TestCase):
    """Tests for get_date_from_file method."""

    def setUp(self):
        self.handler = md_front_matter.FrontMatterHandler()

    def test_returns_iso_format(self):
        """Test date is returned in ISO format."""
        filepath = Path(__file__)
        result = self.handler.get_date_from_file(filepath=filepath)
        self.assertRegex(result, r"^\d{4}-\d{2}-\d{2}$")


class TestGetDefaultAuthor(unittest.TestCase):
    """Tests for get_default_author method."""

    def setUp(self):
        self.handler = md_front_matter.FrontMatterHandler()

    def test_returns_user_env(self):
        """Test returns USER environment variable."""
        result = self.handler.get_default_author()
        self.assertEqual(result, os.environ.get("USER"))

    @patch.dict(os.environ, {"USER": "testuser"})
    def test_returns_custom_user(self):
        """Test returns custom user from environment."""
        result = self.handler.get_default_author()
        self.assertEqual(result, "testuser")


class TestParseFrontMatter(unittest.TestCase):
    """Tests for parse_front_matter method."""

    def setUp(self):
        self.handler = md_front_matter.FrontMatterHandler()

    def test_no_front_matter(self):
        """Test parsing content without front matter."""
        content = "# Hello World"
        front_matter, remaining = self.handler.parse_front_matter(content=content)
        self.assertIsNone(front_matter)
        self.assertEqual(remaining, content)

    def test_with_front_matter(self):
        """Test parsing content with front matter."""
        content = "---\ntitle: Test\n---\n# Content"
        front_matter, remaining = self.handler.parse_front_matter(content=content)
        assert front_matter is not None
        self.assertEqual(front_matter["title"], "Test")
        self.assertEqual(remaining.strip(), "# Content")

    def test_with_front_matter_and_tags(self):
        """Test parsing content with tags."""
        content = "---\ntitle: Test\ntags: [tag1, tag2]\n---\n# Content"
        front_matter, _ = self.handler.parse_front_matter(content=content)
        assert front_matter is not None
        self.assertEqual(front_matter["title"], "Test")
        self.assertEqual(front_matter["tags"], ["tag1", "tag2"])


class TestFormatFrontMatter(unittest.TestCase):
    """Tests for format_front_matter method."""

    def setUp(self):
        self.handler = md_front_matter.FrontMatterHandler()

    def test_simple_front_matter(self):
        """Test formatting simple front matter."""
        data = {"title": "Test", "date": "2024-01-01", "author": "John"}
        result = self.handler.format_front_matter(data=data)
        self.assertIn("title: Test", result)
        self.assertIn("date: 2024-01-01", result)
        self.assertIn("author: John", result)

    def test_front_matter_with_tags(self):
        """Test formatting front matter with tags."""
        data = {"title": "Test", "tags": ["python", "markdown"]}
        result = self.handler.format_front_matter(data=data)
        self.assertIn("tags:", result)
        self.assertIn("  - python", result)
        self.assertIn("  - markdown", result)


class TestMergeTags(unittest.TestCase):
    """Tests for merge_tags method."""

    def setUp(self):
        self.handler = md_front_matter.FrontMatterHandler()

    def test_merge_new_tags(self):
        """Test merging new tags with existing."""
        existing = ["tag1"]
        new = ["tag2", "tag3"]
        result = self.handler.merge_tags(existing=existing, new=new)
        self.assertEqual(sorted(result), ["tag1", "tag2", "tag3"])

    def test_merge_with_duplicates(self):
        """Test merging handles duplicates."""
        existing = ["python", "tools"]
        new = ["python", "ruby"]
        result = self.handler.merge_tags(existing=existing, new=new)
        self.assertEqual(sorted(result), ["python", "ruby", "tools"])

    def test_merge_empty_existing(self):
        """Test merging with no existing tags."""
        existing = None
        new = ["tag1", "tag2"]
        result = self.handler.merge_tags(existing=existing, new=new)
        self.assertEqual(sorted(result), ["tag1", "tag2"])


class TestExtractTagsFromContent(unittest.TestCase):
    """Tests for extract_tags_from_content method."""

    def setUp(self):
        self.handler = md_front_matter.FrontMatterHandler()

    def test_extract_single_tag(self):
        """Test extracting a single tag."""
        content = "#my-tag"
        result = self.handler.extract_tags_from_content(content=content)
        self.assertEqual(result, ["my-tag"])

    def test_extract_multiple_tags(self):
        """Test extracting multiple tags."""
        content = "#tag1\n#tag2\n#tag_3"
        result = self.handler.extract_tags_from_content(content=content)
        self.assertEqual(sorted(result), ["tag1", "tag2", "tag_3"])

    def test_extract_valid_tags(self):
        """Test extracting valid tags."""
        content = "#this-is-a-valid-tag\n#ThisIsAValidTag\n#this_is_a_valid_tag\n#tag1\n#tag_2"
        result = self.handler.extract_tags_from_content(content=content)
        self.assertEqual(sorted(result), ["ThisIsAValidTag", "tag1", "tag_2", "this-is-a-valid-tag", "this_is_a_valid_tag"])

    def test_ignore_markdown_heading(self):
        """Test ignoring markdown headings with spaces."""
        content = "# This Is A Markdown Title"
        result = self.handler.extract_tags_from_content(content=content)
        self.assertEqual(result, [])

    def test_ignore_code_comment(self):
        """Test ignoring code comments."""
        content = "$foobar='Some String' # I am a code comment"
        result = self.handler.extract_tags_from_content(content=content)
        self.assertEqual(result, [])

    def test_ignore_tag_with_space(self):
        """Test ignoring tags with spaces."""
        content = "# tag with space"
        result = self.handler.extract_tags_from_content(content=content)
        self.assertEqual(result, [])

    def test_extract_from_multiline_content(self):
        """Test extracting tags from multiline content."""
        content = "# Title\n\nSome text\n\n#python #not-valid\n\n#valid-tag"
        result = self.handler.extract_tags_from_content(content=content)
        self.assertEqual(sorted(result), ["not-valid", "python", "valid-tag"])

    def test_extract_tags_from_fixture_file(self):
        """Test extracting tags from fixture file with multiple tags on same line."""
        fixture_path = Path(__file__).parent / "fixtures" / "1998-07-12_test_document_with_tags.md"
        content = fixture_path.read_text()
        result = self.handler.extract_tags_from_content(content=content)
        self.assertEqual(sorted(result), ["brazil", "france", "soccer"])


class TestHandlerClass(unittest.TestCase):
    """Tests for Handler class."""

    # noqa: SLF001

    def setUp(self):
        """Set up test directory."""
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        """Clean up test directory."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    def test_handler_initialization(self):
        """Test Handler initializes with default values."""
        handler = md_front_matter.FrontMatterHandler()
        self.assertEqual(handler.files_processed, 0)
        self.assertIsNone(handler.author)
        self.assertIsNone(handler.custom_date)
        self.assertEqual(handler.tags, [])
        self.assertFalse(handler.force)

    def test_process_file_new_file(self):
        """Test processing a new file adds front matter."""
        filepath = Path("test.md")
        filepath.write_text("# Test Content", encoding="utf-8")

        handler = md_front_matter.FrontMatterHandler(
            author=None,
            custom_date=None,
            tags=[],
            force=False,
        )
        handler.process_file(filepath)

        content = filepath.read_text(encoding="utf-8")
        self.assertIn("title: Test", content)
        self.assertIn("date:", content)
        self.assertIn("author:", content)

    def test_process_file_with_tags(self):
        """Test processing file with tags."""
        filepath = Path("test.md")
        filepath.write_text("# Test Content", encoding="utf-8")

        handler = md_front_matter.FrontMatterHandler(
            author=None,
            custom_date=None,
            tags=["python", "markdown", "tools"],
            force=False,
        )
        handler.process_file(filepath)

        content = filepath.read_text(encoding="utf-8")
        self.assertIn("tags:", content)
        self.assertIn("  - markdown", content)
        self.assertIn("  - python", content)
        self.assertIn("  - tools", content)

    def test_process_file_preserves_existing(self):
        """Test existing front matter is preserved."""
        filepath = Path("existing.md")
        filepath.write_text(
            "---\ntitle: Existing Title\ndate: 2023-06-01\nauthor: Jane Smith\ntags: [old-tag]\n---\n# Content",
            encoding="utf-8"
        )

        handler = md_front_matter.FrontMatterHandler(
            author=None,
            custom_date=None,
            tags=[],
            force=False,
        )
        handler.process_file(filepath)

        content = filepath.read_text(encoding="utf-8")
        self.assertIn("title: Existing Title", content)
        self.assertIn("date: 2023-06-01", content)
        self.assertIn("author: Jane Smith", content)

    def test_process_file_appends_tags(self):
        """Test new tags are appended to existing."""
        filepath = Path("existing.md")
        filepath.write_text(
            "---\ntitle: Existing Title\ndate: 2023-06-01\nauthor: Jane Smith\ntags: [zebra, alpha]\n---\n# Content",
            encoding="utf-8"
        )

        handler = md_front_matter.FrontMatterHandler(
            author=None,
            custom_date=None,
            tags=["middle-tag", "beta"],
            force=False,
        )
        handler.process_file(filepath)

        content = filepath.read_text(encoding="utf-8")
        self.assertIn("  - alpha", content)
        self.assertIn("  - beta", content)
        self.assertIn("  - middle-tag", content)
        self.assertIn("  - zebra", content)

    def test_process_file_deduplicates_tags(self):
        """Test duplicate tags are not added."""
        filepath = Path("existing.md")
        filepath.write_text(
            "---\ntitle: Existing Title\ntags: [python, tools]\n---\n# Content",
            encoding="utf-8"
        )

        handler = md_front_matter.FrontMatterHandler(
            author=None,
            custom_date=None,
            tags=["python", "ruby"],
            force=False,
        )
        handler.process_file(filepath)

        content = filepath.read_text(encoding="utf-8")
        tag_count = content.count("  - ")
        self.assertEqual(tag_count, 3)

    def test_process_file_force_overrides(self):
        """Test force overrides existing front matter."""
        filepath = Path("existing.md")
        filepath.write_text(
            "---\ntitle: Original Title\ndate: 2023-06-01\nauthor: Original Author\ntags: [original-tag]\n---\n# Content",
            encoding="utf-8"
        )

        handler = md_front_matter.FrontMatterHandler(
            author="New Author",
            custom_date=None,
            tags=["forced-tag"],
            force=True,
        )
        handler.process_file(filepath)

        content = filepath.read_text(encoding="utf-8")
        self.assertIn("title: Original Title", content)
        self.assertIn("author: New Author", content)
        self.assertIn("  - forced-tag", content)
        self.assertNotIn("original-tag", content)

    def test_process_file_skips_non_markdown(self):
        """Test non-markdown files are skipped."""
        filepath = Path("test.txt")
        filepath.write_text("content", encoding="utf-8")

        handler = md_front_matter.FrontMatterHandler()
        handler.process_file(filepath)

        content = filepath.read_text(encoding="utf-8")
        self.assertEqual(content, "content")
        self.assertEqual(handler.files_processed, 0)

    def test_process_file_dry_run(self):
        """Test dry run does not modify file."""
        filepath = Path("test.md")
        filepath.write_text("# Test Content", encoding="utf-8")

        handler = md_front_matter.FrontMatterHandler(logger=md_front_matter.NullLogger())
        handler.process_file(filepath, dry_run=True)

        content = filepath.read_text(encoding="utf-8")
        self.assertEqual(content, "# Test Content")

    def test_walk_paths_single_file(self):
        """Test walk_paths with single file."""
        filepath = Path("test.md")
        filepath.touch()

        handler = md_front_matter.FrontMatterHandler()
        result = list(handler.walk_paths("test.md", recursive=False, include=None, exclude=None))
        self.assertEqual(len(result), 1)

    def test_walk_paths_directory(self):
        """Test walk_paths with directory."""
        (Path("file1.md")).touch()
        (Path("file2.md")).touch()
        subdir = Path("subdir")
        subdir.mkdir()
        (subdir / "nested.md").touch()

        handler = md_front_matter.FrontMatterHandler()
        result = list(handler.walk_paths(".", recursive=False, include="*.md", exclude=None))
        self.assertEqual(len(result), 2)

    def test_get_date_priority(self):
        """Test _get_date priority: custom > filename > file modification."""
        handler = md_front_matter.FrontMatterHandler(custom_date="2024-06-01")
        path = Path("2023-12-25-test.md")
        path.touch()
        self.assertEqual(handler._get_date(path=path), "2024-06-01")

    def test_get_date_from_filename(self):
        """Test _get_date uses filename date when no custom date."""
        handler = md_front_matter.FrontMatterHandler(custom_date=None)
        path = Path("2023-12-25-test.md")
        path.touch()
        self.assertEqual(handler._get_date(path=path), "2023-12-25")

    def test_process_file_with_date_prefix(self):
        """Test processing file with date prefix uses filename date."""
        filepath = Path("2024-01-15-my-document.md")
        filepath.write_text("# Test Content", encoding="utf-8")

        handler = md_front_matter.FrontMatterHandler(
            author=None,
            custom_date=None,
            tags=[],
            force=False,
        )
        handler.process_file(filepath)

        content = filepath.read_text(encoding="utf-8")
        self.assertIn("date: 2024-01-15", content)
        self.assertIn("title: My Document", content)

    def test_extract_tags_from_new_file(self):
        """Test extracting tags from new file content."""
        filepath = Path("document.md")
        filepath.write_text("# Title\n\n#python\n#markdown\n#tools", encoding="utf-8")

        handler = md_front_matter.FrontMatterHandler(
            author=None,
            custom_date=None,
            tags=[],
            force=False,
        )
        handler.process_file(filepath)

        content = filepath.read_text(encoding="utf-8")
        self.assertIn("  - markdown", content)
        self.assertIn("  - python", content)
        self.assertIn("  - tools", content)

    def test_extract_tags_with_existing_front_matter(self):
        """Test extracting tags merges with existing front matter tags."""
        filepath = Path("existing.md")
        filepath.write_text(
            "---\ntitle: Existing Title\ntags: [existing-tag]\n---\n# Content\n\n#new-tag\n#another-tag",
            encoding="utf-8"
        )

        handler = md_front_matter.FrontMatterHandler(
            author=None,
            custom_date=None,
            tags=[],
            force=False,
        )
        handler.process_file(filepath)

        content = filepath.read_text(encoding="utf-8")
        self.assertIn("  - another-tag", content)
        self.assertIn("  - existing-tag", content)
        self.assertIn("  - new-tag", content)

    def test_extract_and_cli_tags_merged(self):
        """Test extracted tags merge with CLI tags."""
        filepath = Path("document.md")
        filepath.write_text("# Title\n\n#extracted-tag", encoding="utf-8")

        handler = md_front_matter.FrontMatterHandler(
            author=None,
            custom_date=None,
            tags=["cli-tag"],
            force=False,
        )
        handler.process_file(filepath)

        content = filepath.read_text(encoding="utf-8")
        self.assertIn("  - cli-tag", content)
        self.assertIn("  - extracted-tag", content)

    def test_force_overrides_with_extracted_tags(self):
        """Test force flag replaces existing with extracted and CLI tags."""
        filepath = Path("existing.md")
        filepath.write_text(
            "---\ntitle: Original Title\ntags: [old-tag]\n---\n# Content\n\n#new-tag",
            encoding="utf-8"
        )

        handler = md_front_matter.FrontMatterHandler(
            author=None,
            custom_date=None,
            tags=["cli-tag"],
            force=True,
        )
        handler.process_file(filepath)

        content = filepath.read_text(encoding="utf-8")
        self.assertIn("  - cli-tag", content)
        self.assertIn("  - new-tag", content)
        self.assertNotIn("old-tag", content)


class TestBuildParser(unittest.TestCase):
    """Tests for build_parser function."""

    def test_parser_has_required_arguments(self):
        """Test parser has required input argument."""
        parser = md_front_matter.FrontMatterApp(
            author='TangoMan75',
            title='Front Matter Generator',
            description='Generate front matter.',
        ).build_parser()

        args = parser.parse_args(["test.md"])
        self.assertEqual(str(args.input), "test.md")

    def test_parser_with_options(self):
        """Test parser accepts all options."""
        parser = md_front_matter.FrontMatterApp(
            author='TangoMan75',
            title='Front Matter Generator',
            description='Generate front matter.',
        ).build_parser()

        args = parser.parse_args([
            "test.md",
            "--author", "John Doe",
            "--date", "2024-01-15",
            "--tags", "python,markdown",
            "--force",
            "-v",
        ])
        self.assertEqual(args.author, "John Doe")
        self.assertEqual(args.date, "2024-01-15")
        self.assertEqual(args.tags, "python,markdown")
        self.assertTrue(args.force)
        self.assertEqual(args.verbose, 1)


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

    def test_cli_new_file(self):
        """Test CLI creates front matter on new file."""
        filepath = Path("test.md")
        filepath.write_text("# Test", encoding="utf-8")

        with patch.object(sys, "argv", ["script", str(filepath)]):
            md_front_matter.FrontMatterApp(
            author='TangoMan75',
            title='Front Matter Generator',
            description='Generate front matter.',
        ).run(md_front_matter.FrontMatterHandler)

        content = filepath.read_text(encoding="utf-8")
        self.assertIn("title: Test", content)

    def test_cli_with_author(self):
        """Test CLI with author override."""
        filepath = Path("test.md")
        filepath.write_text("# Test", encoding="utf-8")

        with patch.object(sys, "argv", ["script", str(filepath), "--author", "John Doe"]):
            md_front_matter.FrontMatterApp(
            author='TangoMan75',
            title='Front Matter Generator',
            description='Generate front matter.',
        ).run(md_front_matter.FrontMatterHandler)

        content = filepath.read_text(encoding="utf-8")
        self.assertIn("author: John Doe", content)

    def test_cli_with_date(self):
        """Test CLI with date override."""
        filepath = Path("test.md")
        filepath.write_text("# Test", encoding="utf-8")

        with patch.object(sys, "argv", ["script", str(filepath), "--date", "2024-01-15"]):
            md_front_matter.FrontMatterApp(
            author='TangoMan75',
            title='Front Matter Generator',
            description='Generate front matter.',
        ).run(md_front_matter.FrontMatterHandler)

        content = filepath.read_text(encoding="utf-8")
        self.assertIn("date: 2024-01-15", content)

    def test_cli_with_tags(self):
        """Test CLI with tags."""
        filepath = Path("test.md")
        filepath.write_text("# Test", encoding="utf-8")

        with patch.object(sys, "argv", ["script", str(filepath), "--tags", "python,markdown,tools"]):
            md_front_matter.FrontMatterApp(
            author='TangoMan75',
            title='Front Matter Generator',
            description='Generate front matter.',
        ).run(md_front_matter.FrontMatterHandler)

        content = filepath.read_text(encoding="utf-8")
        self.assertIn("tags:", content)

    def test_cli_force_override(self):
        """Test CLI with force flag."""
        filepath = Path("existing.md")
        filepath.write_text(
            "---\ntitle: Original\ndate: 2023-01-01\nauthor: Original\ntags: [old]\n---\n# Content",
            encoding="utf-8"
        )

        with patch.object(sys, "argv", ["script", str(filepath), "--force", "--author", "New Author"]):
            md_front_matter.FrontMatterApp(
            author='TangoMan75',
            title='Front Matter Generator',
            description='Generate front matter.',
        ).run(md_front_matter.FrontMatterHandler)

        content = filepath.read_text(encoding="utf-8")
        self.assertIn("author: New Author", content)

    def test_cli_missing_file(self):
        """A missing file exits 1 with an error on stderr."""
        stderr = io.StringIO()
        with patch.object(sys, "argv", ["script", "nonexistent.md"]), \
             redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as cm:
                md_front_matter.FrontMatterApp(
                    author='TangoMan75',
                    title='Front Matter Generator',
                    description='Generate front matter.',
                ).run(md_front_matter.FrontMatterHandler)
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("input path not found", stderr.getvalue())

    def test_cli_non_markdown_file(self):
        """Test CLI skips non-markdown file."""
        filepath = Path("test.txt")
        filepath.write_text("content", encoding="utf-8")

        with patch.object(sys, "argv", ["script", str(filepath)]):
            md_front_matter.FrontMatterApp(
            author='TangoMan75',
            title='Front Matter Generator',
            description='Generate front matter.',
        ).run(md_front_matter.FrontMatterHandler)


if __name__ == "__main__":
    unittest.main()
