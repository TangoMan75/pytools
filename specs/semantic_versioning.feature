Feature: Auto-increment semver-shaped version numbers in text files
  As a developer
  I want to auto-bump version numbers in my project files
  So that I don't have to edit them by hand on every release

  Background:
    Given the tool "semantic_versioning" is available

  Scenario: Bump fix version (default)
    Given a text file "version.txt" with content "version: 1.2.3"
    When I run the tool on "version.txt"
    Then the file should contain "version: 1.2.4"

  Scenario: Bump minor version
    Given a text file "version.txt" with content "version: 1.2.3"
    When I run the tool with --minor on "version.txt"
    Then the file should contain "version: 1.3.0"

  Scenario: Bump major version
    Given a text file "version.txt" with content "version: 1.2.3"
    When I run the tool with --major on "version.txt"
    Then the file should contain "version: 2.0.0"

  Scenario: Bump multiple versions on the same line
    Given a text file "changelog.txt" with content "from 0.1.0 to 1.2.9"
    When I run the tool on "changelog.txt"
    Then the file should contain "from 0.1.1 to 1.2.10"

  Scenario: Pre-release suffix is stripped on bump
    Given a text file "pre.txt" with content "1.2.3-rc.1"
    When I run the tool on "pre.txt"
    Then the file should contain "1.2.4"
    And the file should not contain "-rc.1"

  Scenario: Pre-release suffix is stripped on major bump
    Given a text file "pre.txt" with content "1.2.3-beta.4"
    When I run the tool with --major on "pre.txt"
    Then the file should contain "2.0.0"

  Scenario: Surrounding text is preserved
    Given a text file "v.py" with content '__version__ = "1.2.3"  # current'
    When I run the tool with --minor on "v.py"
    Then the file should contain '__version__ = "1.3.0"  # current'

  Scenario: --line targets a specific line
    Given a text file "multi.txt" with content:
      """
      1.0.0
      2.0.0
      3.0.0
      """
    When I run the tool with --line 2 on "multi.txt"
    Then the file should contain:
      """
      1.0.0
      2.0.1
      3.0.0
      """

  Scenario: --line with no match on the targeted line is a skip
    Given a text file "no.txt" with content:
      """
      1.0.0
      no version
      3.0.0
      """
    When I run the tool with --line 2 on "no.txt"
    Then the file should remain unchanged
    And the file count of files_processed should be 0
    And the file count of files_skipped should be 1

  Scenario: --line out of range is a skip
    Given a text file "short.txt" with content "1.0.0"
    When I run the tool with --line 99 on "short.txt"
    Then the file should remain unchanged

  Scenario: --line applies per file in recursive mode
    Given a directory "src" containing:
      | file            | content   |
      | src/a.txt       | 1.0.0     |
      | src/sub/b.txt   | 1.0.0     |
    When I run the tool with --line 1 --recursive on "src"
    Then both files should contain "1.0.1"

  Scenario: IP address is not matched
    Given a text file "ip.txt" with content "server 192.168.1.1"
    When I run the tool on "ip.txt"
    Then the file should remain unchanged

  Scenario: Calendar date is not matched
    Given a text file "date.txt" with content "released 2024.01.15"
    When I run the tool on "date.txt"
    Then the file should remain unchanged

  Scenario: Four-segment version is not matched
    Given a text file "build.txt" with content "build 1.2.3.4"
    When I run the tool on "build.txt"
    Then the file should remain unchanged

  Scenario: File with no version is skipped
    Given a text file "readme.txt" with content "no version here"
    When I run the tool on "readme.txt"
    Then the file should remain unchanged
    And the file count of files_processed should be 0
    And the file count of files_skipped should be 1

  Scenario: --dry-run previews without modifying
    Given a text file "v.txt" with content "1.2.3"
    When I run the tool with --dry-run on "v.txt"
    Then the file should remain unchanged
    And the file count of files_processed should be 1

  Scenario: --check exits non-zero when changes would be made
    Given a text file "v.txt" with content "1.2.3"
    When I run the tool with --check on "v.txt"
    Then the file should remain unchanged
    And the tool should exit with a non-zero status

  Scenario: --check exits zero when no changes are needed
    Given a text file "v.txt" with content "no version"
    When I run the tool with --check on "v.txt"
    Then the tool should exit with a zero status

  Scenario: Mutually exclusive kind flags
    Given the tool is invoked with both --major and --minor
    Then argparse should reject the invocation

  Scenario: Binary file is skipped
    Given a binary file "blob.bin" containing "1.2.3" with null bytes
    When I run the tool on "blob.bin"
    Then the file should remain unchanged
    And the file count of files_skipped should be 1

  Scenario: Recursive directory traversal
    Given a directory "src" containing:
      | file            | content   |
      | src/a.txt       | 1.0.0     |
      | src/sub/b.txt   | 1.0.0     |
    When I run the tool with --recursive on "src"
    Then both files should contain "1.0.1"

  Scenario: --include filter
    Given a directory "d" containing:
      | file    | content |
      | d/a.txt | 1.0.0   |
      | d/b.md  | 1.0.0   |
    When I run the tool with --include "*.md" on "d"
    Then "d/b.md" should contain "1.0.1"
    And "d/a.txt" should remain unchanged
  Scenario: Quiet mode suppresses processing messages
    Given a file containing a semantic version
    When semantic_versioning is run with --quiet
    Then the file should be processed
    And processing messages should be suppressed
