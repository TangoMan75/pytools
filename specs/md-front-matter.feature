Feature: Generate Front Matter from File
  As a markdown document author
  I want to automatically generate YAML front matter for my markdown files
  So that I can quickly add metadata without manual editing

  Background:
    Given the tool "markdown_front_matter" is available

  Scenario: Generate front matter for a new markdown file
    Given a new markdown file "my-document.md" does not have front matter
    When I run the tool on "my-document.md"
    Then the file should start with front matter containing:
      | attribute | value                  |
      | title     | My Document            |
      | date      | <current date>         |
      | author    | <current system user>  |

  Scenario: Title is sanitized and converted to title case
    Given a markdown file "my_interesting-document.md" without front matter
    When I run the tool on "my_interesting-document.md"
    Then the front matter should contain title "My Interesting Document"

  Scenario: Date is extracted from filename prefix
    Given a markdown file "2024-01-15-my-notes.md" without front matter
    When I run the tool on "2024-01-15-my-notes.md"
    Then the front matter should contain:
      | attribute | value          |
      | title     | My Notes       |
      | date      | 2024-01-15     |

  Scenario: Date prefix with underscore separator
    Given a markdown file "2023-12-25_project-ideas.md" without front matter
    When I run the tool on "2023-12-25_project-ideas.md"
    Then the front matter should contain:
      | attribute | value            |
      | title     | Project Ideas    |
      | date      | 2023-12-25       |

  Scenario: Date priority is custom > filename > file modification
    Given a markdown file "2023-06-01-document.md" without front matter
    When I run the tool with --date "2024-12-01" on "2023-06-01-document.md"
    Then the front matter should contain date "2024-12-01"

  Scenario: Override default author with command line option
    Given a markdown file "document.md" without front matter
    When I run the tool with --author "John Doe" on "document.md"
    Then the front matter should contain author "John Doe"

  Scenario: Override default date with command line option
    Given a markdown file "document.md" without front matter
    When I run the tool with --date "2024-01-15" on "document.md"
    Then the front matter should contain date "2024-01-15"

  Scenario: Add tags via command line
    Given a markdown file "document.md" without front matter
    When I run the tool with --tags "python,markdown,tools" on "document.md"
    Then the front matter should contain tags sorted alphabetically:
      | tag      |
      | markdown |
      | python   |
      | tools    |

  Scenario: Existing front matter is preserved when not using force
    Given a markdown file "existing.md" with front matter:
      """
      ---
      title: Existing Title
      date: 2023-06-01
      author: Jane Smith
      tags: [old-tag]
      ---
      """
    When I run the tool on "existing.md"
    Then the front matter should preserve:
      | attribute | value            |
      | title     | Existing Title   |
      | date      | 2023-06-01       |
      | author    | Jane Smith       |
    And the tags should contain:
      | tag      |
      | old-tag  |

  Scenario: New tags are appended to existing tags and sorted
    Given a markdown file "existing.md" with front matter:
      """
      ---
      title: Existing Title
      date: 2023-06-01
      author: Jane Smith
      tags: [zebra, alpha]
      ---
      """
    When I run the tool with --tags "middle-tag,beta" on "existing.md"
    Then the front matter should preserve the original attributes
    And the tags should contain sorted alphabetically:
      | tag         |
      | alpha       |
      | beta        |
      | middle-tag  |
      | zebra       |

  Scenario: Duplicate tags are not added
    Given a markdown file "existing.md" with front matter:
      """
      ---
      title: Existing Title
      tags: [python, tools]
      ---
      """
    When I run the tool with --tags "python,ruby" on "existing.md"
    Then the tags should contain sorted alphabetically:
      | tag    |
      | python |
      | ruby   |
      | tools  |

  Scenario: Force override existing front matter
    Given a markdown file "existing.md" with front matter:
      """
      ---
      title: Original Title
      date: 2023-06-01
      author: Original Author
      tags: [original-tag]
      ---
      """
    When I run the tool with --force --author "New Author" --tags "forced-tag" on "existing.md"
    Then the front matter should contain:
      | attribute | value          |
      | title     | Original Title |
      | date      | <current date> |
      | author    | New Author     |
    And the tags should contain:
      | tag         |
      | forced-tag  |

  Scenario: Force override with all options
    Given a markdown file "existing.md" with front matter:
      """
      ---
      title: Original Title
      date: 2023-06-01
      author: Original Author
      tags: [original-tag]
      ---
      """
    When I run the tool with --force --date "2025-12-25" --author "Override Author" --tags "new-tag" on "existing.md"
    Then the front matter should contain:
      | attribute | value            |
      | title     | Original Title   |
      | date      | 2025-12-25       |
      | author    | Override Author  |
    And the tags should contain:
      | tag      |
      | new-tag  |

  Scenario: Extract tags from document content
    Given a markdown file "document.md" without front matter with content:
      """
      # This Is A Title

      #this-is-a-valid-tag
      #ThisIsAValidTag
      #this_is_a_valid_tag
      #tag1
      #tag_2
      """
    When I run the tool on "document.md"
    Then the front matter should contain tags sorted alphabetically:
      | tag                |
      | tag1               |
      | tag_2              |
      | this-is-a-valid-tag |
      | this_is_a_valid_tag |
      | ThisIsAValidTag    |

  Scenario: Extract tags from content with existing front matter
    Given a markdown file "existing.md" with front matter:
      """
      ---
      title: Existing Title
      tags: [existing-tag]
      ---
      """
    And the file content after front matter is:
      """
      #document

      #new-tag
      #another-tag
      """
    When I run the tool on "existing.md"
    Then the tags should contain sorted alphabetically:
      | tag           |
      | another-tag   |
      | existing-tag  |
      | new-tag       |

  Scenario: Invalid hashtags are not extracted
    Given a markdown file "document.md" without front matter with content:
      """
      # This Is A Markdown Title, NOT a tag
      $foobar='Some String' # I am a code comment, NOT a tag

      #valid-tag
      """
    When I run the tool on "document.md"
    Then the front matter should contain tags:
      | tag        |
      | valid-tag  |
  Scenario: Quiet mode suppresses processing messages
    Given a Markdown input file
    When I run the front matter tool with --quiet
    Then front matter should be processed
    And processing messages should be suppressed
