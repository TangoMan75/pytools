Feature: Moments date conversion

  Scenario: Convert an inferred ISO date to short format
    Given the target date is "2026-08-11T12:30:00+02:00"
    When moments is run with "--short"
    Then the output is "2026-08-11"

  Scenario: Select a timezone
    Given the target date is "2026-01-15T12:00:00Z"
    When moments is run with "--tz UTC --iso"
    Then the output is "2026-01-15T12:00:00+00:00"

  Scenario: Help lists timezone examples
    When moments is run with "--help"
    Then the help output contains "Europe/Paris"

  Scenario: Convert to ISO without a range
    Given the target date is "2026-08-11T12:30:00+02:00"
    When moments is run with "--iso"
    Then the output is "2026-08-11T12:30:00+02:00"

  Scenario: Convert to a long timestamp without a range
    Given the target date is "2026-08-11T15:20:30+02:00"
    When moments is run with "--long"
    Then the output is "2026-08-11 15:20:30"

  Scenario: Convert to epoch without a range
    Given the target date is "2026-08-11"
    When moments is run with "--epoch"
    Then the output is one epoch-millisecond value

  Scenario: Accept time-first slash date input
    Given the target date is "16:19 24/09/2026"
    When moments is run with "--long"
    Then the output is "2026-09-24 16:19:00"

  Scenario: Quiet mode keeps the primary result
    Given the target date is "2026-08-11"
    When moments is run with --quiet --short
    Then the output is "2026-08-11"

  Scenario: Relative time with --short shows years
    Given the target date is "2026-09-08T12:00:00+02:00"
    When moments is run with "--short --from 2016-09-08"
    Then the output is "10 years"

  Scenario: Relative time with --short shows months and days
    Given the target date is "2026-02-10T00:00:00+01:00"
    When moments is run with "--short --from 2026-01-01"
    Then the output is "1 month 9 days"

  Scenario: Relative time without --short includes hours minutes seconds
    Given the target date is "2026-09-08T12:30:30+02:00"
    When moments is run with "--from 2025-09-08T00:00:00+02:00"
    Then the output is "1 year 12 hours 30 minutes 30 seconds"

  Scenario: Relative time with explicit times on both sides
    Given the target date is "2026-09-08T12:30:30+02:00"
    When moments is run with "--from 2025-09-08T10:15:15+02:00"
    Then the output is "1 year 2 hours 15 minutes 15 seconds"

  Scenario: Relative time zero difference
    Given the target date is "2026-01-01T00:00:00+01:00"
    When moments is run with "--from 2026-01-01"
    Then the output is "0"

  Scenario: Relative time rejects invalid --from date
    When moments is run with "--from not-a-date"
    Then the command exits with code 1
