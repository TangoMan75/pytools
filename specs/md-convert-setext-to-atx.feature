Feature: Convert Setext Markdown Headings to ATX
  As a Markdown Writer
  I want to automatically convert underlined headings to hash-prefixed headings
  So that my document follows a consistent ATX style and is easier to read.

  Background:
    Given the tool "markdown_convert_setext_to_atx" is available

  Scenario Outline: Convert valid setext headings to ATX
    Given a file containing a <type> heading:
      """
      <title>
      <underline>
      """
    When I run the "md-convert-setext-to-atx.py" script
    Then the text should be transformed to:
      """
      <result>
      """

    Examples:
      | type | title        | underline | result         |
      | H1   | Main Title   | ======    | # Main Title   |
      | H2   | Sub Section  | ------    | ## Sub Section |
      | H1   | Title Space  | ===       | # Title Space  |
      | H2   | Sub Space    | ---       | ## Sub Space   |

  Scenario: Ignore underlines that are too short
    Given a file containing a title with a short underline:
      """
      Small Title
      ==
      """
    When I run the "md-convert-setext-to-atx.py" script
    Then the text should remain unchanged

  Scenario: Ignore thematic breaks (Horizontal Rules)
    Given a file containing a horizontal rule without a preceding title:
      """
      Some paragraph text.

      ---
      """
    When I run the "md-convert-setext-to-atx.py" script
    Then the text should remain unchanged

  Scenario: Preserve YAML front matter metadata
    Given a file containing front matter with a setext heading:
      """
      ---
      title: My Post
      date: 2024-01-15
      ---
      Title Text
      ======
      """
    When I run the "md-convert-setext-to-atx.py" script
    Then the text should be transformed to:
      """
      ---
      title: My Post
      date: 2024-01-15
      ---
      # Title Text
      """
  Scenario: Preserve content inside code fences
    Given a file containing a setext heading and code fence:
      """
      Title
      =====

      ```javascript
      const x = 1;
      ----
      ```
      """
    When I run the "md-convert-setext-to-atx.py" script
    Then the text should be transformed to:
      """
      # Title

      ```javascript
      const x = 1;
      ----
      ```
      """

  Scenario: Preserve code fences with tildes
    Given a file containing a setext heading and tilde code fence:
      """
      Title
      =====

      ~~~
      code
      ===
      ~~~
      """
    When I run the "md-convert-setext-to-atx.py" script
    Then the text should be transformed to:
      """
      # Title

      ~~~
      code
      ===
      ~~~
      """

  Scenario: Quiet mode suppresses conversion messages
    Given a Markdown file with setext headings
    When I run the converter with --quiet
    Then the Markdown file should be converted
    And conversion messages should be suppressed
