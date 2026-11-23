Feature: Generate a Google Calendar-compatible CSV with AM/PM time slots
  As a TangoMan power user
  I want to generate a CSV file with one AM and one PM entry per working day
  So that I can import my work schedule into Google Calendar in one click

  Background:
    Given a Python script "calendar_generator.py"
    And the default calendar name is "TangoMan"
    And the default AM time range is "09:00" to "13:00"
    And the default PM time range is "14:00" to "18:00"
    And the default output file is "tangoman.csv" (calendar name in lower_snake_case)
    And the fallback output file is "calendar.csv" (used when the calendar name is empty or only special characters)
    And the default CSV header is "Subject,Start Date,Start Time,End Date,End Time,Description,Location"

  Scenario: Generating a calendar for a working week
    Given the current working directory is empty
    When I run the script with --start "2024-01-01" --end "2024-01-05"
    Then a "tangoman.csv" file should be created
    And the file should contain the CSV header line
    And the file should contain 10 data rows (2 per working day, 5 working days)
    And no row should be dated 2024-01-06 or 2024-01-07 (weekend)

  Scenario: Skipping Saturday and Sunday
    Given the current working directory is empty
    When I run the script with --start "2024-01-06" --end "2024-01-07"
    Then a "tangoman.csv" file should be created
    And the file should contain only the CSV header line (no data rows)

  Scenario: Using a custom calendar name
    Given the current working directory is empty
    When I run the script with --name "StandUp" --start "2024-01-01" --end "2024-01-01"
    Then a "standup.csv" file should be created
    And every Subject cell should be "StandUp"

  Scenario: Using a custom address (location)
    Given the current working directory is empty
    When I run the script with --name "StandUp" --address "1 Rue de la Paix" --start "2024-01-01" --end "2024-01-01"
    Then a "standup.csv" file should be created
    And every Location cell should be "1 Rue de la Paix"

  Scenario: Using custom AM/PM time ranges
    Given the current working directory is empty
    When I run the script with --am-from "08:00" --am-to "12:00" --pm-from "13:00" --pm-to "17:00" --start "2024-01-01" --end "2024-01-01"
    Then a "tangoman.csv" file should be created
    And the AM rows should use "08:00" as Start Time and "12:00" as End Time
    And the PM rows should use "13:00" as Start Time and "17:00" as End Time

  Scenario: Writing to a custom output file via --output
    Given the current working directory is empty
    When I run the script with --output "my_calendar.csv" --start "2024-01-01" --end "2024-01-01"
    Then a "my_calendar.csv" file should be created
    And no "tangoman.csv" file should be created

  Scenario: Dry-run does not write any file
    Given the current working directory is empty
    When I run the script with --dry-run --start "2024-01-01" --end "2024-01-01"
    Then no "tangoman.csv" file should be created
    And the script should report the number of rows that would have been written

  Scenario: Invalid --start falls back to today's date
    Given the current working directory is empty
    And today's date is "2024-06-15"
    When I run the script with --start "not-a-date" --end "2099-12-31"
    Then a "tangoman.csv" file should be created
    And the first data row should be dated "2024-06-15"

  Scenario: Default output filename is the calendar name in lower_snake_case
    Given the current working directory is empty
    When I run the script with --name "My Calendar" --start "2024-01-01" --end "2024-01-02"
    Then a "my_calendar.csv" file should be created

  Scenario: Calendar name with punctuation becomes snake_case
    Given the current working directory is empty
    When I run the script with --name "My-Calendar!" --start "2024-01-01" --end "2024-01-02"
    Then a "my_calendar.csv" file should be created

  Scenario: GUI save dialog is pre-filled with the snake_case calendar name
    Given the GUI window is open with default values
    When I set the calendar name field to "StandUp"
    And I click the Generate button
    Then the save dialog should be pre-filled with "standup.csv"

  Scenario: Rejecting a start date later than the end date
    Given the current working directory is empty
    When I run the script with --start "2024-12-31" --end "2024-01-01"
    Then the script should exit with a non-zero status
    And an error message mentioning the start and end dates should be printed

  Scenario: Rejecting a start date equal to the end date
    Given the current working directory is empty
    When I run the script with --start "2024-06-15" --end "2024-06-15"
    Then the script should exit with a non-zero status
    And an error message mentioning the start and end dates should be printed

  Scenario: Invalid HH:MM times fall back to defaults
    Given the current working directory is empty
    When I run the script with --am-from "bad" --start "2024-01-01" --end "2024-01-01"
    Then a "tangoman.csv" file should be created
    And the AM rows should use "09:00" as Start Time (the default)

  Scenario: Each working day produces exactly one AM and one PM row
    Given the current working directory is empty
    When I run the script with --start "2024-01-01" --end "2024-01-05"
    Then every date in the file should appear exactly twice (AM and PM)

  Scenario: --gui launches the graphical user interface
    When I run the script with --gui
    Then a window titled "TangoMan Calendar Generator" should open
    And the form should be pre-filled with the default calendar name "TangoMan"
    And the start date picker should default to today
    And the end date picker should default to the first day of next month
    And the AM time fields should default to "09:00" and "13:00"
    And the PM time fields should default to "14:00" and "18:00"

  Scenario: GUI form fields propagate to the CSV
    Given the GUI window is open with default values
    When I set the calendar name field to "StandUp"
    And I set the address field to "1 Rue de la Paix"
    And I set the start date to "2024-06-03"
    And I set the end date to "2024-06-07"
    And I click the Generate button and pick "gui_out.csv"
    Then a "gui_out.csv" file should be created
    And every Subject cell should be "StandUp"
    And every Location cell should be "1 Rue de la Paix"
    And every row should be dated between "2024-06-03" and "2024-06-07"

  Scenario: GUI rejects a start date later than the end date
    Given the GUI window is open with default values
    When I set the start date to "2024-12-31"
    And I set the end date to "2024-01-01"
    And I click the Generate button
    Then an error dialog should mention the start and end dates
    And no file should be written

  Scenario: GUI rejects equal start and end dates
    Given the GUI window is open with default values
    When I set the start date to "2024-06-15"
    And I set the end date to "2024-06-15"
    And I click the Generate button
    Then an error dialog should mention the start and end dates
    And no file should be written

  Scenario: GUI falls back to defaults when the name field is empty
    Given the GUI window is open with default values
    When I clear the calendar name field
    And I click the Generate button and pick "empty_name.csv"
    Then a "empty_name.csv" file should be created
    And every Subject cell should be "TangoMan" (the default)

  Scenario: GUI invalid time fields fall back to defaults
    Given the GUI window is open with default values
    When I set the AM-from field to "bad"
    And I set the PM-to field to "99:99"
    And I click the Generate button and pick "bad_time.csv"
    Then a "bad_time.csv" file should be created
    And the AM rows should use "09:00" as Start Time
    And the PM rows should use "18:00" as End Time

  Scenario: Quiet mode suppresses progress output
    Given the current working directory is empty
    When I run the script with --quiet --start "2024-01-01" --end "2024-01-01"
    Then the calendar file should be created
    And progress output should be suppressed
