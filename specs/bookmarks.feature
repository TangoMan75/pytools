Feature: Read Chrome bookmarks
  As a chrome bookmarks librarian
  I want to read local Chrome bookmarks from the command line
  So that I can export and filter them in JSON, Markdown or Netscape HTML

  Background:
    Given the tool "bookmarks" is available
    And a Chrome profile with a "Bookmarks" JSON file

  Scenario: Default output is JSON
    When I run the tool without format options
    Then the output is a JSON array
    And each entry has a "name", "url", "date_created", "date_modified"
      and "tags" attribute
    And no entry has a "datetime", "guid" or "profile" attribute

  Scenario: Bookmarks are flattened from every root
    Given bookmarks stored in "bookmark_bar", "other" and "synced" roots
    When I flatten the tree
    Then only "url" nodes are emitted
    And folder nodes are not emitted as entries

  Scenario: Tags come from the ancestor folder chain
    Given a bookmark stored in folder "dev" itself inside "Bookmarks bar"
    When I render the entry with --json
    Then the "tags" list contains the slugs "bookmarks-bar" and "dev"

  Scenario: Date fields are converted from Chrome epoch
    Given a bookmark with date_added "13380000200000000"
    When I render the entry with --json
    Then "date_created" equals the local time of the bookmark add date
    And "date_modified" equals the local time of the parent folder
      "date_modified"

  Scenario: --start filters by inclusive add date
    When I run the tool with --start "2020-01-01"
    Then only bookmarks added at or after 2020-01-01 00:00:00 are printed

  Scenario: --end marks the end of the day and is inclusive
    When I run the tool with --end "2024-12-30"
    Then only bookmarks added on or before 2024-12-30 23:59:59 are printed

  Scenario: --end excludes later bookmarks
    When I run the tool with --start "2026-01-01" and --end "2026-01-02"
    Then a bookmark added on "2026-06-15" is not printed

  Scenario: A date-only --start uses midnight
    When I run the tool with --start "2024-12-30"
    Then bookmarks added at "00:00:00" exactly are included

  Scenario: --start with a timestamp keeps the time of day
    When I run the tool with --start "2024-12-30 04:00:20"
    Then a bookmark added at "2024-12-30 04:00:20" is included
    And a bookmark added earlier the same day is excluded

  Scenario: End before start exits 2
    When I run the tool with --start "2026-01-02" and --end "2026-01-01"
    Then the tool exits with code 2
    And an error message is printed to stderr

  Scenario: An invalid date exits 2
    When I run the tool with --start "not-a-date"
    Then the tool exits with code 2

  Scenario: Default JSON output is sorted by add date
    When the fixture bookmarks are added out of file order
    Then the printed JSON array is sorted by add date

  Scenario: --md renders the front matter template
    Given a bookmark "Python" in folder "dev"
    When I run the tool with --md
    Then the output contains a block starting with front matter
    And the front matter contains "created_at" and "modified_at" ISO dates
    And the front matter contains "- tags:" followed by slugified folder names
    And the output contains "## Python"
    And the output contains "#bookmark #bookmarks-bar #dev"
    And the output contains "- [Python](https://www.python.org)"

  Scenario: Trailing slashes are removed from URLs
    Given a bookmark with url "https://www.python.org/"
    When I render the entry with --json
    Then the "url" attribute is "https://www.python.org"

  Scenario: --md hashtags and front matter tags are slugified
    Given a bookmark in folder "web <&>"
    When I run the tool with --md
    Then the front matter contains the slugified folder name "web"
    And the hashtag list contains "#bookmark #bookmarks-bar #web"

  Scenario: --html renders a NETSCAPE-Bookmark-file-1
    When I run the tool with --html
    Then the output starts with "<!DOCTYPE NETSCAPE-Bookmark-file-1>"
    And the output contains a "<DL><p>" structure
    And each bookmark is an "<A HREF=...>" entry
    And folders are rendered as nested "<H3>" headings
    And "ADD_DATE" values are Unix epoch seconds

  Scenario: --html escapes text values
    Given a bookmark title "Outside <Range>" in folder "web <&>"
    When I run the tool with --html
    Then the folder name is rendered "web &lt;&amp;&gt;"
    And the title is rendered "Outside &lt;Range&gt;"

  Scenario: Read every profile by default
    Given Chrome profiles "Default" and "Profile 1" both with a "Bookmarks" file
    When I run the tool without --profile
    Then bookmarks from both profiles are printed

  Scenario: --profile restricts to one profile
    When I run the tool with --profile "Default"
    Then only bookmarks from the "Default" profile are printed

  Scenario: --db reads an explicit Bookmarks file
    Given the fixture file "tests/fixtures/Bookmarks.json"
    When I run the tool with --db pointing to the fixture
    Then the fixture bookmarks are printed and no profile is scanned

  Scenario: Missing Bookmarks file is a runtime error
    When I run the tool with a --db path that does not exist
    Then the tool exits with code 1
    And an error message is printed to stderr

  Scenario: --quiet does not hide runtime errors
    When I run the tool with --quiet and a --db path that does not exist
    Then the tool exits with code 1
    And an error message is printed to stderr

  Scenario: --quiet does not hide usage errors
    When I run the tool with --quiet and --start "not-a-date"
    Then the tool exits with code 2
    And an error message is printed to stderr

  Scenario: --completion prints a bash completion script
    When I run the tool with --completion
    Then a "_bookmarks_completions" bash function is printed
    And the options --json, --md, --html, --start and --end appear in it
