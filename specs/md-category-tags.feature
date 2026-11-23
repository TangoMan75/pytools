Feature: Add Category Tags to Daily Notes
  As a note taker
  I want category tags added to my daily markdown notes
  So that notes are consistently tagged for filtering

  Background:
    Given a directory containing markdown daily notes named with a date-category pattern

  Scenario: Add tag to a note with an existing tag line
    Given a markdown file "2024-01-15-workout.md" containing a note with an existing tag line "#note"
    When I run the category tags script on the directory
    Then the file should contain a "#workout" tag prepended to the tag line

  Scenario: Add tag to a note without a tag line
    Given a markdown file "2024-01-15-workout.md" containing a note with a "## " title and no tag line
    When I run the category tags script on the directory
    Then the file should contain a "#workout" tag after the title

  Scenario: Extract category from the first-line title
    Given a markdown file "notes.md" whose first line is "2024-01-15_reading"
    When I run the category tags script on the directory
    Then the file should be tagged with "#reading"

  Scenario: Skip file with no resolvable category
    Given a markdown file "untagged.md" with no date-category filename or title
    When I run the category tags script on the directory
    Then the file should not be modified

  Scenario: Do not duplicate an existing category tag
    Given a markdown file "2024-01-15-workout.md" already containing "#workout"
    When I run the category tags script on the directory
    Then the file should not gain a duplicate "#workout" tag

  Scenario: Dry run does not modify files
    Given a markdown file "2024-01-15-workout.md" without a category tag
    When I run the category tags script with --dry-run
    Then the file should remain unchanged
    And the script should report it would update the file

  Scenario: Quiet mode suppresses output
    Given a markdown file "2024-01-15-workout.md" without a category tag
    When I run the category tags script with --quiet
    Then the file should be updated
    And chatter should be suppressed

  Scenario: Completion script is emitted
    When I run the category tags script with --completion
    Then a bash completion script should be printed to stdout
