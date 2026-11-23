Feature: Explode Markdown File with Date Prefixing
  As a Content Manager
  I want to split a Markdown file into sub-files prefixed with a date
  So that my exported notes maintain their chronological context.

  Background:
    Given a Python script "md-split.py"
    And a source file "journal.md"

  Scenario Outline: Extracting date from YAML Front Matter
    Given "journal.md" has the following front matter:
      """
      ---
      date: <input_date>
      title: My Collection
      ---
      ## <section_title>
      Section content.
      """
    When the script processes the file
    Then a file named "<expected_filename>" should be created

    Examples:
      | input_date | section_title | expected_filename      |
      | 2023-10-25 | Ideas         | 2023-10-25_ideas.md    |
      | 2024-01-01 | New Year      | 2024-01-01_new-year.md |

  Scenario: Fallback to File System modified date
    Given "journal.md" has no YAML front matter
    And the OS reports "journal.md" was last modified on "2023-05-12"
    And the file contains:
      """
      ## Local Section
      Content here.
      """
    When the script processes the file
    Then a file named "2023-05-12_local-section.md" should be created

  Scenario: Extract date from filename
    Given the source file is named "2024-02-14_journal.md"
    And "2024-02-14_journal.md" has no YAML front matter
    And the file contains:
      """
      ## My Notes
      Some content.
      """
    When the script processes the file
    Then a file named "2024-02-14_my-notes.md" should be created

  Scenario: Filename date has lower priority than front matter
    Given the source file is named "2024-02-14_journal.md"
    And "journal.md" has the following front matter:
      """
      ---
      date: 2024-01-01
      ---
      ## Section
      Content.
      """
    When the script processes the file
    Then a file named "2024-01-01_section.md" should be created

  Scenario: Handling duplicates with date prefixes
    Given "journal.md" has front matter date "2023-12-25"
    And the file contains:
      """
      ## Gift List
      First list.
      ## Gift List
      Second list.
      """
    When the script processes the file
    Then the first file created is "2023-12-25_gift-list.md"
    And the second file created is "2023-12-25_gift-list_1.md"

  Scenario: Handling complex sluggification with date
    Given "journal.md" has front matter date "2024-03-24"
    And it contains an H2 "Update: Project Alpha & Beta!"
    When the script processes the file
    Then the filename should be "2024-03-24_update-project-alpha-beta.md"

  Scenario: Ignoring H2 sections inside code blocks while preserving content
    Given "journal.md" has front matter date "2024-06-15"
    And the file contains:
      """
      ## Section One
      Content one.

      ```
      ## This Title Should Be Ignored
      Code block content here.
      ```

      ## Section Two
      Content two.
      """
    When the script processes the file
    Then a file named "2024-06-15_section-one.md" should be created
    And a file named "2024-06-15_section-two.md" should be created
    And "2024-06-15_section-one.md" should contain "Code block content here."
    And no file should be created for "This Title Should Be Ignored"
  Scenario: Quiet mode suppresses split messages
    Given a Markdown file with sections
    When I run markdown_split with --quiet
    Then section files should be created
    And split messages should be suppressed
