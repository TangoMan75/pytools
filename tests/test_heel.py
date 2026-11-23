#!/usr/bin/env python3
"""Tests for heel module."""

# noqa: ARG001, E402

import argparse
import datetime
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))

import heel

class TestWalkPaths(unittest.TestCase):
    """Tests for walk_paths method."""

    def setUp(self):
        """Set up test directory."""
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)
        self.handler = heel.FileHandler()

    def tearDown(self):
        """Clean up test directory."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    def test_walk_paths_single_file(self):
        """Test walk_paths with single file."""
        test_file = Path("sample.txt")
        test_file.touch()

        result = list(self.handler.walk_paths("sample.txt", recursive=False, include=None, exclude=None))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "sample.txt")

    def test_walk_paths_directory_non_recursive(self):
        """Test walk_paths with directory, non-recursive."""
        (Path("file1.txt")).touch()
        (Path("file2.md")).touch()
        subdir = Path("subdir")
        subdir.mkdir()
        (subdir / "nested.txt").touch()

        result = list(self.handler.walk_paths(".", recursive=False, include=None, exclude=None))
        self.assertEqual(len(result), 2)
        names = {r.name for r in result}
        self.assertIn("file1.txt", names)
        self.assertIn("file2.md", names)
        self.assertNotIn("nested.txt", names)

    def test_walk_paths_directory_recursive(self):
        """Test walk_paths with directory, recursive."""
        (Path("file1.txt")).touch()
        subdir = Path("subdir")
        subdir.mkdir()
        (subdir / "file2.txt").touch()

        result = list(self.handler.walk_paths(".", recursive=True, include=None, exclude=None))
        self.assertEqual(len(result), 2)

    def test_walk_paths_include_filter(self):
        """Test walk_paths with include filter."""
        (Path("file.txt")).touch()
        (Path("file.md")).touch()

        result = list(self.handler.walk_paths(".", recursive=False, include="*.txt", exclude=None))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "file.txt")

    def test_walk_paths_exclude_filter(self):
        """Test walk_paths with exclude filter."""
        (Path("file.txt")).touch()
        (Path("file.log")).touch()

        result = list(self.handler.walk_paths(".", recursive=False, include=None, exclude="*.log"))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "file.txt")

    def test_walk_paths_include_and_exclude(self):
        """Test walk_paths with both include and exclude filters."""
        (Path("report.txt")).touch()
        (Path("report-draft.txt")).touch()
        (Path("other.txt")).touch()

        result = list(self.handler.walk_paths(".", recursive=False, include="*.txt", exclude="*-draft.txt"))
        names = {r.name for r in result}
        self.assertIn("report.txt", names)
        self.assertIn("other.txt", names)
        self.assertNotIn("report-draft.txt", names)

class TestBuildParser(unittest.TestCase):
    """Tests for build_parser function."""

    def test_parser_has_required_arguments(self):
        """Test parser has required input argument."""
        parser = heel.Kernel(author="test", title="test", description="test description").build_parser()

        args = parser.parse_args(["test.txt"])
        self.assertEqual(args.input, "test.txt")

    def test_parser_short_flags(self):
        """Test parser short flags."""
        parser = heel.Kernel(author="test", title="test", description="test description").build_parser()

        args = parser.parse_args(["test.txt", "--output", "result.json", "--recursive", "-v"])
        self.assertEqual(args.input, "test.txt")
        self.assertEqual(args.output, "result.json")
        self.assertTrue(args.recursive)
        self.assertEqual(args.verbose, 1)

    def test_parser_optional_arguments(self):
        """Test parser optional arguments."""
        parser = heel.Kernel(author="test", title="test", description="test description").build_parser()

        args = parser.parse_args([
            "test.txt",
            "--output", "result.json",
            "--recursive",
            "--include", "*.txt",
            "--exclude", "*.log",
            "--dry-run",
            "-v"
        ])
        self.assertEqual(args.output, "result.json")
        self.assertTrue(args.recursive)
        self.assertEqual(args.include, "*.txt")
        self.assertEqual(args.exclude, "*.log")
        self.assertTrue(args.dry_run)
        self.assertEqual(args.verbose, 1)

    def test_parser_verbose_count(self):
        """Test parser verbose count."""
        parser = heel.Kernel(author="test", title="test", description="test description").build_parser()

        args = parser.parse_args(["test.txt", "-vvv"])
        self.assertEqual(args.verbose, 3)

    def test_parser_missing_required_input(self):
        """Test parser raises error when required input is missing."""
        parser = heel.Kernel(author="test", title="test", description="test description").build_parser()

        with self.assertRaises(SystemExit):
            parser.parse_args([])

    def test_help_flag_prints_help(self):
        """Test --help flag prints help."""
        parser = heel.Kernel(author="test", title="test", description="test description").build_parser()
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            with self.assertRaises(SystemExit):
                parser.parse_args(['--help'])
            output = mock_stdout.getvalue()
            self.assertIn('input', output)
            self.assertIn('--output', output)
            self.assertIn('--recursive', output)
            self.assertIn('--include', output)
            self.assertIn('--exclude', output)
            self.assertIn('--dry-run', output)
            self.assertIn('--verbose', output)
            self.assertIn('--completion', output)
            self.assertIn('--help', output)

class TestHandlerClass(unittest.TestCase):
    """Tests for Handler class."""

    def test_process_file_base_handler_skips(self):
        """The base handler intentionally performs no file processing."""
        handler = heel.FileHandler()
        handler.process_file(Path("test.txt"))
        self.assertEqual(handler.files_skipped, 1)

    def test_process_directory_default_verbose_0(self):
        """Test process_directory with verbose=0."""
        handler = heel.FileHandler()
        test_dir = tempfile.mkdtemp()
        try:
            with patch("sys.stdout") as mock_stdout:
                handler.process_directory(Path(test_dir))
                mock_stdout.write.assert_not_called()
        finally:
            shutil.rmtree(test_dir)

    def test_process_directory_non_recursive(self):
        """Test process_directory with recursive=False does not recurse."""
        class MockHandler(heel.FileHandler):
            def __init__(self):
                super().__init__()
                self.files = []

            def process_file(self, path, **kwargs):
                self.files.append(path)

        handler = MockHandler()
        test_dir = tempfile.mkdtemp()
        try:
            (Path(test_dir) / "file1.txt").touch()
            subdir = Path(test_dir) / "subdir"
            subdir.mkdir()
            (subdir / "file2.txt").touch()

            handler.process_directory(test_dir, recursive=False)
            self.assertEqual(len(handler.files), 1)
            self.assertEqual(handler.files[0].name, "file1.txt")
        finally:
            shutil.rmtree(test_dir)

    def test_process_directory_recursive(self):
        """Test process_directory with recursive=True recurses into subdirs."""
        class MockHandler(heel.FileHandler):
            def __init__(self):
                super().__init__()
                self.files = []

            def process_file(self, path, **kwargs):
                self.files.append(path)

        handler = MockHandler()
        test_dir = tempfile.mkdtemp()
        try:
            (Path(test_dir) / "file1.txt").touch()
            subdir = Path(test_dir) / "subdir"
            subdir.mkdir()
            (subdir / "file2.txt").touch()

            handler.process_directory(test_dir, recursive=True)
            self.assertEqual(len(handler.files), 2)
            names = {f.name for f in handler.files}
            self.assertIn("file1.txt", names)
            self.assertIn("file2.txt", names)
        finally:
            shutil.rmtree(test_dir)

    def test_process_directory_recursive_default_false(self):
        """Test process_directory defaults to recursive=False."""
        class MockHandler(heel.FileHandler):
            def __init__(self):
                super().__init__()
                self.files = []

            def process_file(self, path, **kwargs):
                self.files.append(path)

        handler = MockHandler()
        test_dir = tempfile.mkdtemp()
        try:
            (Path(test_dir) / "file1.txt").touch()
            subdir = Path(test_dir) / "subdir"
            subdir.mkdir()
            (subdir / "file2.txt").touch()

            handler.process_directory(test_dir)
            self.assertEqual(len(handler.files), 1)
            self.assertEqual(handler.files[0].name, "file1.txt")
        finally:
            shutil.rmtree(test_dir)

class TestRunFunction(unittest.TestCase):
    """Tests for run function."""

    def setUp(self):
        """Set up test directory."""
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)
        (Path("test.txt")).touch()

    def tearDown(self):
        """Clean up test directory."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    def test_run_calls_process_file(self):
        """Test run calls process_file."""
        class TestHandler(heel.FileHandler):
            processed = []

            def process_file(self, path, **kwargs):
                TestHandler.processed.append(path)

        with patch.object(sys, "argv", ["script", "test.txt"]):
            heel.Kernel(author="test", title="test", description="test description").run(TestHandler)
            self.assertEqual(len(TestHandler.processed), 1)
        TestHandler.processed = []

class TestGenerateCompletionScript(unittest.TestCase):
    """Tests for the bash completion script generator."""

    def _parser(self):
        parser = argparse.ArgumentParser(description="demo")
        parser.add_argument("input")
        parser.add_argument("--output")
        parser.add_argument("--include")
        parser.add_argument("--recursive", action="store_true")
        parser.add_argument("--verbose", "-v", action="count", default=0)
        return parser

    def test_generate_completion_script_includes_options(self):
        """Completion script lists every option from the parser."""
        script = heel.Completion.generate(parser=self._parser(), name="demo")
        for token in ("--output", "--include", "--recursive", "--verbose", "-v"):
            self.assertIn(token, script)

    def test_generate_completion_script_reflects_signatures(self):
        """Completion script tailors completion per option kind."""
        script = heel.Completion.generate(parser=self._parser(), name="demo")
        self.assertIn("--output)\n            COMPREPLY=( $(compgen -f", script)
        self.assertIn("--include)\n            COMPREPLY=( $(compgen -G", script)
        self.assertIn("--recursive)\n            COMPREPLY=()", script)
        self.assertIn("--verbose)\n            COMPREPLY=( $(compgen -W \"-v -vv -vvv\"", script)

    def test_generate_completion_script_is_valid_bash(self):
        """Completion script is syntactically valid bash."""
        script = heel.Completion.generate(parser=self._parser(), name="demo")
        path = Path(tempfile.gettempdir()) / "demo-completion.sh"
        path.write_text(script, encoding="utf-8")
        try:
            self.assertEqual(subprocess.run(["bash", "-n", str(path)], check=False).returncode, 0)
        finally:
            path.unlink(missing_ok=True)

    def test_kernel_generate_completion_delegates(self):
        """Kernel.generate_completion returns a valid completion script."""
        kernel = heel.Kernel(author="TangoMan75", title="demo", description="demo description")
        script = kernel.generate_completion()
        self.assertIn("#!/bin/bash", script)
        self.assertIn("complete -f -F", script)


class TestConsoleInlineFunctions(unittest.TestCase):
    """Tests for Console inline functions."""

    def test_primary_outputs_white_text(self):
        """Test primary outputs white text."""
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            heel.Console.primary("test")
            output = mock_stdout.getvalue()
            self.assertIn("\033[97m", output)
            self.assertIn("test", output)

    def test_secondary_outputs_blue_text(self):
        """Test secondary outputs blue text."""
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            heel.Console.secondary("test")
            output = mock_stdout.getvalue()
            self.assertIn("\033[94m", output)
            self.assertIn("test", output)

    def test_light_outputs_light_gray_text(self):
        """Test light outputs light gray text."""
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            heel.Console.light("test")
            output = mock_stdout.getvalue()
            self.assertIn("\033[47;90m", output)
            self.assertIn("test", output)

    def test_dark_outputs_dark_text(self):
        """Test dark outputs dark text."""
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            heel.Console.dark("test")
            output = mock_stdout.getvalue()
            self.assertIn("\033[40;37m", output)
            self.assertIn("test", output)

    def test_success_outputs_green_text(self):
        """Test echo_success outputs green text."""
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            heel.Console.success("test")
            output = mock_stdout.getvalue()
            self.assertIn("\033[32m", output)
            self.assertIn("test", output)

    def test_danger_outputs_red_text(self):
        """Test echo_danger outputs red text."""
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            heel.Console.danger("error")
            output = mock_stdout.getvalue()
            self.assertIn("\033[31m", output)
            self.assertIn("error", output)

    def test_warning_outputs_orange_text(self):
        """Test echo_warning outputs orange text."""
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            heel.Console.warning("warning")
            output = mock_stdout.getvalue()
            self.assertIn("\033[33m", output)
            self.assertIn("warning", output)

    def test_info_outputs_purple_text(self):
        """Test echo_info outputs purple text."""
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            heel.Console.info("info")
            output = mock_stdout.getvalue()
            self.assertIn("\033[95m", output)
            self.assertIn("info", output)

    def test_error_outputs_to_stderr(self):
        """Test echo_error outputs to stderr."""
        with patch('sys.stderr', new_callable=StringIO) as mock_stderr:
            heel.Console.error("error message")
            output = mock_stderr.getvalue()
            self.assertIn("\033[31m", output)
            self.assertIn("error: error message", output)

class TestAlertFunctions(unittest.TestCase):
    """Tests for alert functions."""

    def test_alert_success_outputs_green_alert_box(self):
        """Test alert_success outputs green alert box."""
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            heel.Console.alert_success("test")
            output = mock_stdout.getvalue()
            self.assertIn("\033[1;42;97m", output)
            self.assertIn("test", output)

    def test_alert_danger_outputs_red_alert_box(self):
        """Test alert_danger outputs red alert box."""
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            heel.Console.alert_danger("test")
            output = mock_stdout.getvalue()
            self.assertIn("\033[1;41;97m", output)

    def test_alert_warning_outputs_orange_alert_box(self):
        """Test alert_warning outputs orange alert box."""
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            heel.Console.alert_warning("test")
            output = mock_stdout.getvalue()
            self.assertIn("\033[1;43;97m", output)

    def test_alert_info_outputs_blue_alert_box(self):
        """Test alert_info outputs blue alert box."""
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            heel.Console.alert_info("test")
            output = mock_stdout.getvalue()
            self.assertIn("\033[1;44;97m", output)

    def test_alert_primary_outputs_cyan_alert_box(self):
        """Test alert_primary outputs cyan alert box."""
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            heel.Console.alert_primary("test")
            output = mock_stdout.getvalue()
            self.assertIn("\033[1;104;97m", output)
            self.assertIn("test", output)

    def test_alert_secondary_outputs_magenta_alert_box(self):
        """Test alert_secondary outputs magenta alert box."""
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            heel.Console.alert_secondary("test")
            output = mock_stdout.getvalue()
            self.assertIn("\033[1;45;97m", output)

    def test_alert_light_outputs_light_alert_box(self):
        """Test alert_light outputs light alert box."""
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            heel.Console.alert_light("test")
            output = mock_stdout.getvalue()
            self.assertIn("\033[1;47;90m", output)

    def test_alert_dark_outputs_dark_alert_box(self):
        """Test alert_dark outputs dark alert box."""
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            heel.Console.alert_dark("test")
            output = mock_stdout.getvalue()
            self.assertIn("\033[1;40;37m", output)

class TestStringSlugify(unittest.TestCase):
    """Tests for String.slugify method."""

    def test_slugify_simple_text(self):
        """Test slugify with simple text."""
        result = heel.String.slugify("Hello World")
        self.assertEqual(result, "hello-world")

    def test_slugify_replaces_spaces_with_hyphens(self):
        """Test slugify replaces spaces with hyphens."""
        result = heel.String.slugify("hello world test")
        self.assertEqual(result, "hello-world-test")

    def test_slugify_multiple_hyphens(self):
        """Test slugify collapses multiple hyphens."""
        result = heel.String.slugify("hello   world")
        self.assertEqual(result, "hello-world")

class TestLoggerClass(unittest.TestCase):
    """Tests for Logger class."""

    def setUp(self):
        """Set up test directory."""
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        """Clean up test directory."""
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir)

    def test_logger_initialization(self):
        """Test logger initializes with verbose level."""
        logger = heel.Logger(verbose=2)
        self.assertEqual(logger.verbose, 2)

    def test_logger_log_creates_log_file(self):
        """Test logger creates log file on first log."""
        logger = heel.Logger(verbose=1)
        logger.log("test message", loglevel=1)
        self.assertTrue(logger.log_file.exists())

    def test_logger_info_logs_at_info_level(self):
        """Test logger.info logs at level 3."""
        logger = heel.Logger(verbose=3)
        with patch.object(heel.Console, 'info') as mock_info:
            logger.info("test info")
            mock_info.assert_called_once()

    def test_logger_warning_logs_at_warning_level(self):
        """Test logger.warning logs at level 2."""
        logger = heel.Logger(verbose=2)
        with patch.object(heel.Console, 'warning') as mock_warning:
            logger.warning("test warning")
            mock_warning.assert_called_once()

    def test_logger_success_logs_at_success_level(self):
        """Test logger.success logs at level 1."""
        logger = heel.Logger(verbose=1)
        with patch.object(heel.Console, 'success') as mock_success:
            logger.success("test success")
            mock_success.assert_called_once()

    def test_logger_danger_logs_at_error_level(self):
        """Test logger.danger logs at level 0."""
        logger = heel.Logger(verbose=0)
        with patch.object(heel.Console, 'danger') as mock_danger:
            logger.danger("test error")
            mock_danger.assert_called_once()

    def test_logger_print_outputs_log_file(self):
        """Test logger.print outputs log file contents."""
        logger = heel.Logger(verbose=0)
        log_file = logger.log_file
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.write_text("log content\n")

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            self.assertTrue(logger.print())
            output = mock_stdout.getvalue()
            self.assertIn("log content", output)

    def test_logger_print_raises_error_when_file_missing(self):
        """Test logger.print raises error when log file doesn't exist."""
        logger = heel.Logger(verbose=0)
        with patch('sys.stderr', new_callable=StringIO):
            self.assertFalse(logger.print())

class TestNullLoggerClass(unittest.TestCase):
    """Tests for NullLogger class."""

    def test_null_logger_returns_none_for_any_method(self):
        """Test NullLogger returns None for any method call."""
        logger = heel.NullLogger()
        result = logger.some_method("arg1", "arg2")
        self.assertIsNone(result)

    def test_null_logger_returns_none_for_log_methods(self):
        """Test NullLogger returns None for log methods."""
        logger = heel.NullLogger()
        self.assertIsNone(logger.log("message"))
        self.assertIsNone(logger.info("message"))
        self.assertIsNone(logger.warning("message"))
        self.assertIsNone(logger.success("message"))
        self.assertIsNone(logger.danger("message"))

class TestFileHandlerGetUniqueFilename(unittest.TestCase):
    """Tests for FileHandler.get_unique_filename method."""

    def test_unique_filename_preserves_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            target_dir = Path(directory)
            (target_dir / "report.txt").touch()
            result = heel.FileHandler.get_unique_filename(target_dir, base_filename="report.txt")
            self.assertEqual(result, target_dir / "report_1.txt")

    def test_unique_filename_accepts_existing_file_path(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "report.md"
            target.touch()
            result = heel.FileHandler.get_unique_filename(target, base_filename="report.md")
            self.assertEqual(result, target.parent / "report_1.md")

class TestAppHeroMethod(unittest.TestCase):
    """Tests for App.hero method."""

    def test_hero_outputs_title(self):
        """Test hero outputs title as alert."""
        app = heel.Kernel(author="test", title="Test Title", description="description")
        with patch('sys.stdout', new_callable=StringIO):
            with patch.object(heel.Console, 'alert_primary') as mock_alert:
                app.hero()
                mock_alert.assert_called_once_with("Test Title")

class TestHeelRegressionCases(unittest.TestCase):
    """Regression tests for framework lifecycle and filesystem behavior."""

    def test_missing_input_raises_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            list(heel.FileHandler.walk_paths("does-not-exist"))

    def test_kernel_uses_invoked_script_path(self):
        with patch.object(sys, "argv", ["/tmp/example_tool.py"]):
            app = heel.Kernel(author="Author", title="Title", description="Description")
        self.assertEqual(app.name, "example_tool")
        self.assertEqual(app.script_file, Path("/tmp/example_tool.py"))

    def test_file_lister_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.txt"
            handler = heel.FileLister(logger=heel.NullLogger())
            handler.process_file(Path("input.txt"), output=output, dry_run=True)
            self.assertFalse(output.exists())
            self.assertEqual(handler.files_processed, 1)

    def test_completion_script_has_valid_bash_syntax_without_boolean_options(self):
        parser = heel.argparse.ArgumentParser()
        parser.add_argument("input")
        script = heel.Completion.generate(parser=parser, name="tool-name")
        path = Path(tempfile.gettempdir()) / "tool-completion.sh"
        path.write_text(script, encoding="utf-8")
        try:
            result = subprocess.run(
                ["bash", "-n", str(path)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
        finally:
            path.unlink(missing_ok=True)

class TestCacheClass(unittest.TestCase):
    """Tests for Cache class."""

    def setUp(self):
        """Create a temporary cache directory."""
        self.test_dir = tempfile.mkdtemp()
        self.cache = heel.Cache(name="test", ttl=datetime.timedelta(hours=1))
        self.cache.cache_dir = Path(self.test_dir) / "cache"
        self.cache.cache_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up test directory."""
        shutil.rmtree(self.test_dir)

    def test_cache_dir_is_created(self):
        """Cache directory is created on write."""
        self.assertTrue(self.cache.cache_dir.exists())

    def test_write_creates_json_file(self):
        """write() creates a timestamped JSON file."""
        self.cache.write("models", data={"key": "value"})
        files = list(self.cache.cache_dir.glob("*_models.json"))
        self.assertEqual(len(files), 1)
        data = __import__('json').loads(files[0].read_text(encoding="utf-8"))
        self.assertEqual(data, {"key": "value"})

    def test_read_returns_fresh_cache(self):
        """read() returns cached data when TTL has not expired."""
        self.cache.write("models", data={"hello": "world"})
        result = self.cache.read("models")
        self.assertEqual(result, {"hello": "world"})

    def test_read_returns_none_when_expired(self):
        """read() returns None when cache has expired."""
        self.cache.ttl = datetime.timedelta(seconds=-1)
        self.cache.write("models", data={"hello": "world"})
        result = self.cache.read("models")
        self.assertIsNone(result)

    def test_read_returns_none_when_no_cache(self):
        """read() returns None when cache directory has no matching files."""
        result = self.cache.read("nonexistent")
        self.assertIsNone(result)

    def test_read_returns_none_when_dir_missing(self):
        """read() returns None when cache directory does not exist."""
        self.cache.cache_dir = Path(self.test_dir) / "missing"
        result = self.cache.read("models")
        self.assertIsNone(result)

    def test_read_returns_none_on_corrupt_json(self):
        """read() skips corrupt JSON files and returns None."""
        bad_file = self.cache.cache_dir / "2025-01-01_12-00-00_models.json"
        bad_file.write_text("not-json{{{", encoding="utf-8")
        result = self.cache.read("models")
        self.assertIsNone(result)

    def test_read_picks_freshest_file(self):
        """read() returns data from the newest file when multiple exist."""
        old = self.cache.cache_dir / "2020-01-01_00-00-00_models.json"
        old.write_text('{"version": "old"}', encoding="utf-8")
        new = self.cache.cache_dir / "2099-01-01_00-00-00_models.json"
        new.write_text('{"version": "new"}', encoding="utf-8")
        result = self.cache.read("models")
        self.assertEqual(result["version"], "new")

    def test_custom_ttl(self):
        """Cache respects custom TTL."""
        cache = heel.Cache(name="test", ttl=datetime.timedelta(days=7))
        self.assertEqual(cache.ttl, datetime.timedelta(days=7))

    def test_default_ttl_is_one_day(self):
        """Default TTL is 1 day."""
        cache = heel.Cache(name="test")
        self.assertEqual(cache.ttl, datetime.timedelta(days=1))

if __name__ == "__main__":
    unittest.main()
