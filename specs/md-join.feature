Feature: Concatenate Markdown Files with Front Matter Removal
  As a Content Manager
  I want to join multiple markdown files into one
  So that I can consolidate my notes or blog posts.

  Background:
    Given a Python script "md-join.py"

  Scenario: Join multiple markdown files from directory
    Given a directory with files:
      | filename | content                              |
      | a.md     | ---\ntitle: A\n---\nContent A |
      | b.md     | ---\ntitle: B\n---\nContent B |
    When the script processes the directory
    Then output file "YYYY-MM-DD.md" should exist
    And it should contain "Content A"
    And it should contain "Content B"

  Scenario: Front matter is removed from joined content
    Given a file "notes.md" with content:
      """
      ---
      title: My Notes
      date: 2023-10-25
      tags: [journal, personal]
      ---
      ## Section One
      Content here.
      """
    When the script processes the file
    Then output should not contain "title:"
    And output should not contain "date:"
    And output should contain "Content here."

  Scenario: Files are sorted alphabetically before joining
    Given a directory with files:
      | filename  | content     |
      | z_file.md | Z content   |
      | a_file.md | A content    |
      | m_file.md | M content    |
    When the script processes the directory
    Then "A content" should appear before "M content"
    And "M content" should appear before "Z content"

  Scenario: Files without content after front matter removal are skipped
    Given a directory with files:
      | filename | content                          |
      | empty.md | ---\ntitle: Empty\n---\n       |
      | data.md  | ---\ntitle: Data\n---\nReal content |
    When the script processes the directory
    Then output should contain "Real content"
    And output should not contain "Empty"

  Scenario: Non-markdown files are skipped
    Given a directory with files:
      | filename  | content       |
      | notes.md  | Markdown text |
      | readme.txt| Plain text    |
    When the script processes the directory
    Then output should contain "Markdown text"
    And output should not contain "Plain text"

  Scenario: Custom output filename is used
    Given a directory with file "entry.md" containing "Test content"
    When the script processes the directory with "--output custom.md"
    Then file "custom.md" should exist
    And it should contain "Test content"

  Scenario: Recursive directory traversal includes nested files
    Given a directory structure:
      """
      .
      └── docs/
          └── notes.md: Nested content
      """
    When the script processes the directory with "--recursive"
    Then output should contain "Nested content"

  Scenario: Dry run does not create output file
    Given a directory with file "test.md" containing "Content"
    When the script processes the directory with "--dry-run"
    Then no output file should be created

  Scenario: Verbose mode shows processing details
    Given a directory with file "test.md" containing "Content"
    When the script processes the directory with "--verbose"
    Then status messages should be displayed
  Scenario: Quiet mode suppresses join messages
    Given Markdown input files
    When I run markdown_join with --quiet
    Then the joined file should be created
    And join messages should be suppressed
