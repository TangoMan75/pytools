#!/usr/bin/env python3
"""Tests for file-based SQL-to-CSV conversion."""

import importlib.util
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

_SPEC = importlib.util.spec_from_file_location(
    "conv_sql", Path(__file__).parents[1] / "conv-sql.py"
)
conv_sql = importlib.util.module_from_spec(_SPEC)
sys.modules["conv_sql"] = conv_sql
_SPEC.loader.exec_module(conv_sql)


class SqlToCsvConverterTest(unittest.TestCase):
    """Exercise INSERT parsing through the converter class."""

    def setUp(self):
        self.converter = conv_sql.SqlToCsvConverter()

    def test_convert_returns_quoted_csv(self):
        """Convert an INSERT statement into quoted CSV."""
        result = self.converter.convert(
            sql="INSERT INTO people (id, name) VALUES (1, 'Ada'), (2, 'Bob');"
        )
        self.assertIn('"id","name"', result)
        self.assertIn('"1","Ada"', result)

    def test_convert_rejects_missing_insert(self):
        """Reject input without an INSERT statement."""
        with self.assertRaises(ValueError):
            self.converter.convert(sql="SELECT 1;")

    def test_convert_keeps_cast_suffix_and_unescapes_quotes(self):
        """Unescape doubled quotes and keep a type cast suffix."""
        result = self.converter.convert(
            sql="INSERT INTO t (a, b) VALUES ('O''Brien', 'x'::text);"
        )
        self.assertIn('"O\'Brien"', result)
        self.assertIn('"x::text"', result)

    def test_convert_handles_nested_calls_and_on_conflict(self):
        """Nested parentheses and trailing clauses do not leak into cells."""
        result = self.converter.convert(
            sql="INSERT INTO t (a, b) VALUES (fn(1, 2), 'v') ON CONFLICT DO NOTHING;"
        )
        self.assertIn('"fn(1, 2)","v"', result)
        self.assertNotIn('ON CONFLICT', result)


class SqlTokenizerTest(unittest.TestCase):
    """Exercise the tokenizer independently of the INSERT parser."""

    def test_tokenize_values_keeps_nested_commas(self):
        """Commas inside nested parens do not split values."""
        values = conv_sql.SqlTokenizer.tokenize_values(text="fn(1, 2), 'a,b', 3")
        self.assertEqual(["fn(1, 2)", "'a,b'", "3"], values)

    def test_split_top_level_parens_returns_group_contents(self):
        """Row groups are returned without their outer parentheses."""
        groups = conv_sql.SqlTokenizer.split_top_level_parens(text="(1, 'a'), (2, 'b')")
        self.assertEqual(["1, 'a'", "2, 'b'"], groups)


class SqlValueParserTest(unittest.TestCase):
    """Exercise SQL scalar unquoting."""

    def test_strips_single_quotes(self):
        """Single-quoted strings lose their outer quotes."""
        self.assertEqual("Ada", conv_sql.SqlValueParser.parse(value="'Ada'"))

    def test_strips_quoted_identifiers(self):
        """Double-quoted identifiers are unquoted."""
        self.assertEqual(
            'weird"ident',
            conv_sql.SqlValueParser.parse(value='"weird""ident"'),
        )


class OutputPathResolverTest(unittest.TestCase):
    """Exercise output path resolution."""

    def test_derives_csv_beside_input(self):
        """Without --output the CSV sits beside the SQL file."""
        source = Path("people.sql")
        destination = conv_sql.OutputPathResolver.resolve(input_path=source)
        self.assertEqual(Path("people.csv"), destination)

    def test_uses_existing_directory(self):
        """An existing output directory receives the derived filename."""
        with tempfile.TemporaryDirectory() as directory:
            destination = conv_sql.OutputPathResolver.resolve(
                input_path=Path("people.sql"),
                output=directory,
            )
            self.assertEqual(Path(directory) / "people.csv", destination)


class SqlFileProcessorTest(unittest.TestCase):
    """Exercise file output without standard streams."""

    def test_process_file_derives_csv_output(self):
        """Derive a CSV output path beside the SQL input."""
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "people.sql"
            source.write_text(
                "INSERT INTO people (id) VALUES (1);",
                encoding="utf-8",
            )
            with redirect_stdout(io.StringIO()):
                conv_sql.SqlFileProcessor().process_file(source)
            output = source.with_suffix(".csv")
            self.assertTrue(output.exists())
            self.assertIn('"id"', output.read_text(encoding="utf-8"))

    def test_process_file_dry_run_does_not_write(self):
        """Dry run reports the destination without creating it."""
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "people.sql"
            source.write_text(
                "INSERT INTO people (id) VALUES (1);",
                encoding="utf-8",
            )
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                conv_sql.SqlFileProcessor().process_file(source, dry_run=True)
            self.assertFalse(source.with_suffix(".csv").exists())
            self.assertIn("[DRY RUN] Would write:", buffer.getvalue())


class CompletionTest(unittest.TestCase):
    """Exercise bash completion generation."""

    def test_generate_mentions_script_and_options(self):
        """Completion script names the tool and lists parser options."""
        script = conv_sql.Completion.generate(
            parser=conv_sql.Kernel(
                author="TangoMan75",
                title="SQL to CSV Converter",
                description=conv_sql.Kernel.DESCRIPTION,
            ).build_parser(),
            name="conv-sql",
        )
        self.assertIn("_conv_sql_completions", script)
        self.assertIn("--output", script)
        self.assertIn("--dry-run", script)

    def test_kernel_prints_completion_without_input(self):
        """--completion prints the script and exits successfully."""
        app = conv_sql.Kernel(
            author="TangoMan75",
            title="SQL to CSV Converter",
            description=conv_sql.Kernel.DESCRIPTION,
            argv=["conv-sql.py", "--completion"],
        )
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            app.run()
        self.assertIn("complete -f", buffer.getvalue())


class KernelParserTest(unittest.TestCase):
    """Exercise the CLI contract of the Kernel parser."""

    def _parser(self):
        return conv_sql.Kernel(
            author="TangoMan75",
            title="SQL to CSV Converter",
            description=conv_sql.Kernel.DESCRIPTION,
        ).build_parser()

    def test_parser_accepts_standard_options(self):
        """All standard options are parsed."""
        args = self._parser().parse_args([
            "input.sql",
            "--output", "out.csv",
            "--recursive",
            "--include", "*.sql",
            "--exclude", "*.bak",
            "--dry-run",
            "-vv",
            "--quiet",
        ])
        self.assertEqual(args.input, "input.sql")
        self.assertEqual(args.output, "out.csv")
        self.assertTrue(args.recursive)
        self.assertEqual(args.include, "*.sql")
        self.assertEqual(args.exclude, "*.bak")
        self.assertTrue(args.dry_run)
        self.assertEqual(args.verbose, 2)
        self.assertTrue(args.quiet)

    def test_parser_requires_input(self):
        """Missing positional input exits with a usage error."""
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as context:
                self._parser().parse_args([])
        self.assertEqual(context.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
