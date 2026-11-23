Feature: Daily backlog index

  Scenario: Index files on a single plain date
    Given the backlog directory contains "2026-08-14_notes.md"
    When history-backlog is run with "--start 2026-08-14 --end 2026-08-14"
    Then the JSON output contains 1 record with date "2026-08-14"

  Scenario: Index files across an inclusive range
    Given the backlog directory contains "2026-08-01_notes.md" and "2026-08-03_notes.md"
    When history-backlog is run with "--start 2026-08-01 --end 2026-08-03"
    Then the JSON output contains 2 records

  Scenario: A datetime value is truncated to its date
    When history-backlog is run with "--start 2026-08-14 22:19:55 --end 2026-08-14 22:20:00"
    Then the range is treated as the single date "2026-08-14"

  Scenario: A datetime with seconds for both bounds spans a single day
    Given the backlog directory contains "2026-08-14_notes.md"
    When history-backlog is run with "--start 2026-08-14 22:19:55 --end 2026-08-14 23:59:59"
    Then the JSON output contains 1 record with date "2026-08-14"

  Scenario: A malformed date is rejected
    When history-backlog is run with "--start 2026-13-45"
    Then the run exits with code 2 and prints an invalid date error

  Scenario: Rendering as a markdown document
    Given the backlog directory contains "2026-08-14_notes.md"
    When history-backlog is run with "--md --start 2026-08-14 --end 2026-08-14"
    Then the output is a markdown document titled "Backlog index for 2026-08-14"
