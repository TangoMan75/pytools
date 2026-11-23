Feature: Convert iCalendar (.ics) files to and from CSV/TSV
  As a calendar data analyst
  I want to convert iCalendar files into tabular form and back
  So that I can pipe calendar data through standard CLI tools

  Background:
    Given the input format is auto-detected from the file extension
    And ".ics" files are parsed as iCalendar (forward direction)
    And ".csv" files are converted to iCalendar with "," delimiter (reverse)
    And ".tsv" files are converted to iCalendar with TAB delimiter (reverse)
    And the default tabular output format is CSV
    And the default forward output layout is Google Calendar-compatible
    And the old "every field found" layout is opt-in via --full

  Scenario: Default output is the Google Calendar-compatible CSV layout
    When I run the tool on "cal.ics"
    Then the output headers should be "Calendar,Subject,Start Date,Start Time,End Date,End Time,Description,Attendee,Location"
    And each row should start with the input file stem in the Calendar column
    And UID, DTSTAMP, STATUS and ORGANIZER columns should be absent

  Scenario: The ATTENDEE column is always present in the Google Calendar output
    When I run the tool on "cal.ics"
    Then the output headers should contain "Attendee"
    And the ATTENDEE value from each event should appear in the row

  Scenario: --full reverts to the full iCalendar dump layout
    When I run the tool with --full on "cal.ics" with columns "uid,summary"
    Then the output headers should be "UID,SUMMARY"
    And the output should contain "test-1@example.com,Test Event One"

  Scenario: .csv input is converted to iCalendar
    Given a CSV file "events.csv" with a single event
    When I run the tool on "events.csv"
    Then the output should start with "BEGIN:VCALENDAR"
    And the output should end with "END:VCALENDAR"
    And the output should contain "UID:test@example.com"

  Scenario: .tsv input is converted to iCalendar with TAB delimiter
    Given a TSV file "events.tsv" with a single event separated by TAB
    When I run the tool on "events.tsv"
    Then the output should start with "BEGIN:VCALENDAR"
    And the output should contain "UID:test@example.com"

  Scenario: Use -d for a custom output delimiter (TSV)
    When I run the tool with -d $'\t' and --full on "cal.ics" with columns "uid,summary"
    Then the output headers should be "UID<SUMMARY"

  Scenario: Use -d for a custom delimiter
    When I run the tool with --full on "cal.ics" with delimiter ";" and columns "uid,summary"
    Then the output should use ";" as the field separator

  Scenario: Strip iCalendar parameters (TZID)
    Given an iCalendar file with a TZID parameter on DTSTART
    When I run the tool with --full on the file
    Then the DTSTART column should contain a normalized ISO datetime without TZID data

  Scenario: Join continuation lines
    Given an iCalendar file with a multi-line DESCRIPTION field
    When I run the tool with --full and columns "description" on the file
    Then the description should be on a single line

  Scenario: Unescape backslash-escaped characters
    Given an iCalendar file with "Hello\, World\!" in the summary
    When I run the tool with --full and columns "summary" on the file
    Then the summary should contain "Hello, World!"

  Scenario: Skip components other than the target
    When I run the tool on a file with VTODO entries
    Then the VTODO entries should not appear in the output

  Scenario: Convert UTC datetimes to local ISO format
    When I run the tool with --full on "cal.ics" with columns "dtstart"
    Then each DTSTART value should be in "YYYY-MM-DD HH:MM:SS" form

  Scenario: Compute DURATION column from DTSTART and DTEND
    When I run the tool with --full on "cal.ics" with columns "dtstart,duration"
    Then each DURATION value should look like "Nh" or "Nm" or "NhMm"

  Scenario: Convert ISO dates back to iCalendar form in reverse
    Given a CSV file with DTSTART in "YYYY-MM-DD HH:MM:SS" form
    When I run the tool on the file
    Then the output DTSTART should be in "YYYYMMDDTHHMMSS" form

  Scenario: Skip empty values in reverse mode
    Given a CSV file with empty SUMMARY cells
    When I run the tool on the file
    Then no "SUMMARY:" line with an empty value should appear in the output

  Scenario: Skip the DURATION column in reverse mode
    Given a CSV file with a DURATION column
    When I run the tool on the file
    Then no "DURATION:" line should appear in the output

  Scenario: Without -o, output is written next to the input basename with a new extension
    When I run the tool with --full on "cal.ics" with columns "uid,summary"
    Then "cal.csv" should be created in the current directory

  Scenario: -o - writes to stdout
    When I run the tool on "cal.ics" with -o "-"
    Then the output is streamed to stdout

  Scenario: -o with an explicit file path
    When I run the tool with --full on "cal.ics" with -o "out.csv" and columns "uid,summary"
    Then "out.csv" should be created
    And "out.csv" should contain "Test Event One"

  Scenario: -d sets the output extension based on the delimiter
    When I run the tool with --full and -d $'\t' on "cal.ics" with -o "out/"
    Then "out/cal.tsv" should exist

  Scenario: Reverse direction always outputs .ics
    Given a CSV file "events.csv"
    When I run the tool on "events.csv" with -o "out/"
    Then "out/events.ics" should exist

  Scenario: --recursive without -o is rejected
    When I run the tool with --recursive on "in_dir/" without -o
    Then the tool should exit with an error

  Scenario: Write to a directory, preserving structure with --recursive
    Given a directory "in/" containing "a.ics" and "in/sub/b.ics"
    When I run the tool with --recursive and --full on "in/" with -o "out/"
    Then "out/a.csv" should exist
    And "out/sub/b.csv" should exist

  Scenario: --dry-run does not write
    When I run the tool on "cal.ics" with -o "out.csv" and --dry-run
    Then "out.csv" should not exist
    And the file count of files_processed should be 1

  Scenario: Handle CRLF line endings
    Given an iCalendar file with Windows line endings
    When I run the tool with --full on the file
    Then each event should be parsed correctly

  Scenario: Default Google-format output splits DTSTART into Start Date and Start Time
    When I run the tool on "cal.ics"
    Then each Start Date should look like "YYYY-MM-DD"
    And each Start Time should look like "HH:MM" in 24-hour form

  Scenario: Default Google-format output maps SUMMARY/DESCRIPTION/LOCATION to their Google columns
    When I run the tool on "cal.ics"
    Then the SUMMARY value should appear in the Subject column
    And the DESCRIPTION value should appear in the Description column
    And the LOCATION value should appear in the Location column

  Scenario: Default Google-format output preserves the input stem in each row when used with --recursive
    Given a directory "in/" containing "a.ics" and "in/sub/b.ics"
    When I run the tool with --recursive on "in/" with -o "out/"
    Then "out/a.csv" should have rows starting with "a,"
    And "out/sub/b.csv" should have rows starting with "b,"

  Scenario: -d $'\t' produces a Google-format TSV
    When I run the tool with -d $'\t' on "cal.ics"
    Then the output headers should be "Calendar<Subject<Start Date<Start Time<End Date<End Time<Description<Attendee<Location"
    And each row should start with the input file stem

  Scenario: A "https://" input is downloaded and converted to CSV
    When I run the tool on "https://example.com/calendar/basic.ics"
    Then "basic.ics" should be created in the current directory
    And "basic.csv" should be created in the current directory

  Scenario: A "http://" input is downloaded to the current directory
    When I run the tool on "http://example.com/cal.ics"
    Then "cal.ics" should be created in the current directory

  Scenario: The downloaded filename is derived from the last URL path segment
    When I run the tool on "https://example.com/path/team.ics"
    Then "team.ics" should be created in the current directory

  Scenario: Query string is stripped from the downloaded filename
    When I run the tool on "https://example.com/cal.ics?cid=abc"
    Then "cal.ics" should be created in the current directory

  Scenario: A missing .ics extension is appended to the downloaded filename
    When I run the tool on "https://example.com/calendar/feed"
    Then "feed.ics" should be created in the current directory

  Scenario: A bare host URL falls back to "calendar.ics"
    When I run the tool on "https://example.com/"
    Then "calendar.ics" should be created in the current directory

  Scenario: Filename collisions are auto-suffixed
    Given a file "cal.ics" already exists in the current directory
    When I run the tool on "https://example.com/cal.ics"
    Then "cal_1.ics" should be created in the current directory
    And the pre-existing "cal.ics" should be untouched

  Scenario: HTTPS downloads always skip SSL certificate verification
    When I run the tool on "https://example.com/cal.ics"
    Then the request is issued with an unverified SSL context

  Scenario: A local file path does not trigger a download
    Given an iCalendar file "local.ics" exists
    When I run the tool on "local.ics" with --full and columns "uid"
    Then the output is the conversion of "local.ics"
    And no download is attempted
  Scenario: Quiet mode suppresses progress output
    Given a valid iCalendar input file
    When I run icsp with --quiet
    Then the converted file should be written
    And progress output should be suppressed
