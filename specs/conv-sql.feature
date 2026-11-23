Feature: Convert SQL inserts to CSV files

  Scenario: Convert an SQL file beside the input
    Given an SQL file containing an INSERT statement
    When I run conv-sql.py with that file as input
    Then a CSV file with the same basename is created

  Scenario: Select an output file
    Given an SQL file containing an INSERT statement
    When I run conv-sql.py with --output
    Then the CSV result is written to the requested file

  Scenario: Do not use standard input
    When I run conv-sql.py without an input file
    Then the command reports invalid usage
  Scenario: Quiet mode suppresses write messages
    Given a valid SQL input file
    When I run csql with --quiet
    Then the CSV file should be written
    And write messages should be suppressed
