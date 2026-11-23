Feature: Rename Markdown Files from Front Matter
  As a content creator
  I want markdown files to be automatically renamed based on their front matter
  So that my files follow a consistent naming convention

  Background:
    Given a directory containing markdown files with YAML front matter
    And each file has a date, title, and author in its front matter

  Scenario: Rename a single markdown file
    Given a markdown file "old_name.md" with front matter:
      """
      ---
      date: 2024-01-15
      title: My First Post
      author: John Doe
      ---
      """
    When I run the rename script on the directory
    Then the file should be renamed to "2024-01-15-john-doe-my-first-post.md"

  Scenario: Handle duplicate filenames
    Given two markdown files with identical front matter date, title, and author
    When I run the rename script on the directory
    Then the first file should be renamed to "2024-01-15-john-doe-my-first-post.md"
    And the second file should be renamed to "2024-01-15-john-doe-my-first-post_1.md"

  Scenario: Skip file without front matter
    Given a markdown file with no YAML front matter
    When I run the rename script on the directory
    Then the file should not be renamed

  Scenario: Skip file with missing required fields
    Given a markdown file with front matter missing the author field
    When I run the rename script on the directory
    Then the file should not be renamed

  Scenario: Skip file already correctly named
    Given a markdown file already named with the correct format "2024-01-15-john-doe-my-post.md"
    When I run the rename script on the directory
    Then the file should not be renamed
  Scenario: Quiet mode suppresses rename messages
    Given a Markdown file with front matter
    When I run markdown_rename with --quiet
    Then the file should be renamed
    And rename messages should be suppressed
