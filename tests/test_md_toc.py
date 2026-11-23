#!/usr/bin/env python3
# noqa: SLF001
"""Tests for md_toc module."""

import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

_SPEC = importlib.util.spec_from_file_location(
    "md_toc", Path(__file__).parents[1] / "md-toc.py"
)
md_toc = importlib.util.module_from_spec(_SPEC)
sys.modules["md_toc"] = md_toc
_SPEC.loader.exec_module(md_toc)


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

    def danger(self, message):
        """Log danger message."""


class TestBuildToc(unittest.TestCase):
    """Tests for build_toc method in MarkdownToc."""

    def setUp(self):
        self.toc = md_toc.MarkdownToc()

    def test_simple_headings(self):
        text = "# Title\n\n## Section One\n\n## Section Two\n"
        result = self.toc.build_toc(text)
        self.assertIn("- [Title](#title)", result)
        self.assertIn("- [Section One](#section-one)", result)
        self.assertIn("- [Section Two](#section-two)", result)

    def test_depth_filtering(self):
        text = "# H1\n\n## H2\n\n### H3\n"
        toc = md_toc.MarkdownToc(min_depth=2, max_depth=2)
        result = toc.build_toc(text)
        self.assertIn("#h2", result)
        self.assertNotIn("#h1", result)
        self.assertNotIn("#h3", result)

    def test_indentation_by_depth(self):
        text = "## A\n\n### B\n"
        result = self.toc.build_toc(text)
        self.assertIn("- [A](#a)", result)
        self.assertIn("  - [B](#b)", result)

    def test_duplicate_headings(self):
        text = "# Title\n\n## Title\n\n## Title\n"
        result = self.toc.build_toc(text)
        self.assertIn("- [Title](#title)", result)
        self.assertIn("- [Title](#title-1)", result)
        self.assertIn("- [Title](#title-2)", result)

    def test_code_fence_skipped(self):
        text = "# Real\n\n```\n# Not A Heading\n```\n"
        result = self.toc.build_toc(text)
        self.assertIn("#real", result)
        self.assertNotIn("#not-a-heading", result)

    def test_setext_headings(self):
        text = "Top Heading\n===\n\nSub Heading\n---\n"
        result = self.toc.build_toc(text)
        self.assertIn("- [Top Heading](#top-heading)", result)
        self.assertIn("- [Sub Heading](#sub-heading)", result)

    def test_front_matter_headings_skipped(self):
        text = "---\ntitle: # Not Heading\ndate: 2024-01-01\n---\n\n# Real Title\n"
        result = self.toc.build_toc(text)
        self.assertIn("#real-title", result)
        self.assertNotIn("#not-heading", result)

    def test_no_title(self):
        text = "# Title\n"
        toc = md_toc.MarkdownToc(title="")
        result = toc.build_toc(text)
        self.assertNotIn("Table of Contents", result)
        self.assertIn("- [Title](#title)", result)

    def test_empty_document(self):
        text = "Just text, no headings.\n"
        result = self.toc.build_toc(text)
        self.assertEqual(result, "")


class TestInsertToc(unittest.TestCase):
    """Tests for _insert_toc method."""

    def setUp(self):
        self.toc = md_toc.MarkdownToc()

    def test_replace_marker(self):
        text = "# Doc\n\n<!-- toc -->\n\n## Section\n"
        toc = self.toc.build_toc(text)
        result = self.toc._insert_toc(text=text, toc=toc)
        self.assertNotIn("<!-- toc -->", result)
        self.assertIn("- [Section](#section)", result)
        self.assertIn("# Doc", result)

    def test_insert_after_front_matter(self):
        text = "---\ntitle: Post\n---\n\n# Title\n\n## Section\n"
        toc = self.toc.build_toc(text)
        result = self.toc._insert_toc(text=text, toc=toc)
        self.assertIn("---\ntitle: Post\n---", result)
        self.assertIn("- [Section](#section)", result)

    def test_insert_at_top(self):
        text = "# Title\n\n## Section\n"
        toc = self.toc.build_toc(text)
        result = self.toc._insert_toc(text=text, toc=toc)
        self.assertTrue(result.startswith("**Table of Contents**"))


class TestMarkdownToc(unittest.TestCase):
    """Tests for MarkdownToc process_file behavior."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    def test_process_markdown_file_stdout(self):
        test_file = Path("test.md")
        test_file.write_text("# Title\n\n## Section\n", encoding="utf-8")
        handler = md_toc.MarkdownToc(logger=MockLogger())
        handler.process_file(test_file, dry_run=False)
        self.assertEqual(handler.files_processed, 1)
        self.assertEqual(test_file.read_text(encoding="utf-8"), "# Title\n\n## Section\n")

    def test_process_non_markdown_skipped(self):
        test_file = Path("test.txt")
        test_file.write_text("# Title\n", encoding="utf-8")
        handler = md_toc.MarkdownToc(logger=MockLogger())
        handler.process_file(test_file, dry_run=False)
        self.assertEqual(handler.files_skipped, 1)

    def test_insert_modifies_file(self):
        test_file = Path("test.md")
        test_file.write_text("# Title\n\n<!-- toc -->\n\n## Section\n", encoding="utf-8")
        handler = md_toc.MarkdownToc(logger=MockLogger(), insert=True)
        handler.process_file(test_file, dry_run=False)
        result = test_file.read_text(encoding="utf-8")
        self.assertIn("- [Section](#section)", result)
        self.assertNotIn("<!-- toc -->", result)
        self.assertEqual(handler.files_processed, 1)

    def test_dry_run_no_changes(self):
        test_file = Path("test.md")
        test_file.write_text("# Title\n\n<!-- toc -->\n\n## Section\n", encoding="utf-8")
        handler = md_toc.MarkdownToc(logger=MockLogger(), insert=True)
        handler.process_file(test_file, dry_run=True)
        self.assertIn("<!-- toc -->", test_file.read_text(encoding="utf-8"))
        self.assertEqual(handler.files_processed, 1)

    def test_output_to_file(self):
        test_file = Path("test.md")
        test_file.write_text("# Title\n\n## Section\n", encoding="utf-8")
        out_file = Path("out.md")
        handler = md_toc.MarkdownToc(logger=MockLogger())
        handler.process_file(test_file, output=out_file, dry_run=False)
        self.assertIn("- [Section](#section)", out_file.read_text(encoding="utf-8"))

    def test_no_headings_skipped(self):
        test_file = Path("test.md")
        test_file.write_text("No headings here.\n", encoding="utf-8")
        handler = md_toc.MarkdownToc(logger=MockLogger())
        handler.process_file(test_file, dry_run=False)
        self.assertEqual(handler.files_skipped, 1)

    def test_three_dash_placeholder_replaced(self):
        """Review #1: matcher tolerates 3-dash '<!--- toc -->' placeholder."""
        test_file = Path("test.md")
        test_file.write_text("# Title\n\n<!--- toc --->\n\n## Section\n", encoding="utf-8")
        handler = md_toc.MarkdownToc(logger=MockLogger(), insert=True)
        handler.process_file(test_file, dry_run=False)
        result = test_file.read_text(encoding="utf-8")
        self.assertIn("- [Section](#section)", result)
        self.assertNotIn("<!--- toc --->", result)

    def test_symbol_only_heading_anchor(self):
        """Review #5: symbol-only heading gets a non-empty fallback anchor."""
        text = "# !!!\n\n# ???\n"
        toc = md_toc.MarkdownToc().build_toc(text)
        self.assertIn("](#section-1)", toc)
        self.assertIn("](#section-2)", toc)


class TestFixtures(unittest.TestCase):
    """Tests using fixture files."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)
        self.fixtures_dir = Path(__file__).parent / "fixtures"

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    def test_fixture_with_marker(self):
        shutil.copy(self.fixtures_dir / "toc_with_marker.md", Path("."))
        handler = md_toc.MarkdownToc(logger=MockLogger(), insert=True)
        handler.process_file(Path("toc_with_marker.md"), dry_run=False)
        result = Path("toc_with_marker.md").read_text(encoding="utf-8")
        self.assertIn("- [Introduction](#introduction)", result)
        self.assertIn("- [Getting Started](#getting-started)", result)
        self.assertNotIn("<!-- toc -->", result)


class TestPatchFixes(unittest.TestCase):
    """Regression tests for review findings F1-F4, F8."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    def test_f1_duplicate_anchors_unique(self):
        """F1: duplicate headings get non-colliding anchors (a, a-1, a-2)."""
        text = "# A\n\n# A-1\n\n# A\n"
        toc = md_toc.MarkdownToc().build_toc(text)
        self.assertIn("- [A](#a)", toc)
        self.assertIn("- [A-1](#a-1)", toc)
        self.assertIn("- [A](#a-2)", toc)
        self.assertEqual(toc.count("](#a-1)"), 1)
        self.assertEqual(toc.count("](#a-2)"), 1)

    def test_f2_yaml_front_matter_keys_excluded(self):
        """F2: YAML front matter keys are not treated as headings."""
        text = "---\ntitle: Post\nauthor: Me\n---\n\n# Real\n\n## Sub\n"
        toc = md_toc.MarkdownToc().build_toc(text)
        self.assertIn("#real", toc)
        self.assertIn("#sub", toc)
        self.assertNotIn("title", toc.lower().split("table of contents")[1])

    def test_f2_front_matter_after_insert_preserved(self):
        """F2: TOC inserted after front matter without dropping headings."""
        text = "---\ntitle: Post\n---\n\n# Real\n\n## Sub\n"
        Path("doc.md").write_text(text, encoding="utf-8")
        handler = md_toc.MarkdownToc(logger=MockLogger(), insert=True)
        handler.process_file(Path("doc.md"), dry_run=False)
        result = Path("doc.md").read_text(encoding="utf-8")
        self.assertIn("title: Post", result)
        self.assertIn("- [Real](#real)", result)
        self.assertIn("- [Sub](#sub)", result)

    def test_f3_directory_traversal(self):
        """F3: directory run processes .md and skips non-markdown files."""
        Path("a.md").write_text("# A\n", encoding="utf-8")
        Path("b.txt").write_text("# B\n", encoding="utf-8")
        out = Path("out")
        out.mkdir()
        handler = md_toc.MarkdownToc(logger=MockLogger())
        for p in handler.walk_paths(".", recursive=False):
            handler.process_file(p, output=str(out), dry_run=False)
        self.assertEqual(handler.files_processed, 1)
        self.assertEqual(handler.files_skipped, 1)
        self.assertTrue((out / "a.toc.md").exists())
        self.assertFalse((out / "b.toc.md").exists())

    def test_f4_output_directory(self):
        """F4: --output as a directory places a file inside it."""
        Path("doc.md").write_text("# Doc\n", encoding="utf-8")
        out = Path("dest")
        out.mkdir()
        handler = md_toc.MarkdownToc(logger=MockLogger())
        handler.process_file(Path("doc.md"), output=str(out), dry_run=False)
        self.assertTrue((out / "doc.toc.md").exists())
        handler2 = md_toc.MarkdownToc(logger=MockLogger(), insert=True)
        handler2.process_file(Path("doc.md"), output=str(out), dry_run=False)
        self.assertTrue((out / "doc.md").exists())

    def test_f8_decode_error_skipped(self):
        """F8: a non-UTF-8 file is skipped, not crashing."""
        Path("bad.md").write_bytes(b"# Title\n\n\xff\xfe\x00\n")
        handler = md_toc.MarkdownToc(logger=MockLogger())
        handler.process_file(Path("bad.md"), dry_run=False)
        self.assertEqual(handler.files_skipped, 1)
        self.assertEqual(handler.files_processed, 0)


if __name__ == "__main__":
    unittest.main()
