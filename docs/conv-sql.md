# conv-sql.py

Convert PostgreSQL-style `INSERT` statements into a CSV file.

## Usage

```text
python3 conv-sql.py INPUT [--output OUTPUT] [--recursive]
                       [--include PATTERN] [--exclude PATTERN]
                       [--dry-run] [--verbose]
```

`INPUT` is an SQL file or directory. Standard input is not supported. When
`--output` is omitted, each input file produces a CSV file beside it with the
same basename. When `--output` names a directory, each result is written there.

## Options

- `--output`: Output CSV file or directory.
- `--recursive`: Process SQL files below an input directory recursively.
- `--include`: Include filter using a glob pattern.
- `--exclude`: Exclude filter using a glob pattern.
- `--dry-run`: Report output paths without writing files.
- `--verbose`, `-v`: Increase verbosity.
- `--quiet`: Suppress non-error output; runtime errors are still reported.
