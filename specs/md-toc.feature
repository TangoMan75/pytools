Feature: Markdown Table of Contents Generator

  As a documentation author
  I want to generate a Table of Contents from my markdown headings
  So that readers can navigate long documents.

  Scenario: Generate a TOC from a simple document
    Given a markdown file with headings
    When I run md-toc on the file
    Then the Table of Contents is printed to stdout

  Scenario: Filter headings by depth
    Given a markdown file with headings of varying depth
    When I run md-toc with --min-depth 2 --max-depth 2
    Then only level 2 headings appear in the TOC

  Scenario: Skip code fences
    Given a markdown file containing a fenced code block with hash lines
    When I run md-toc on the file
    Then the code block text is not treated as a heading

  Scenario: Skip front matter
    Given a markdown file with YAML front matter containing a hash
    When I run md-toc on the file
    Then the front matter is not treated as a heading

  Scenario: Insert TOC at a placeholder
    Given a markdown file containing an "<!-- toc -->" placeholder
    When I run md-toc with --insert
    Then the placeholder is replaced with the generated TOC

  Scenario: Insert TOC after front matter
    Given a markdown file with front matter and no placeholder
    When I run md-toc with --insert
    Then the TOC is inserted after the front matter block

  Scenario: Write TOC to an output file
    Given a markdown file with headings
    When I run md-toc with --output result.md
    Then the TOC is written to result.md

  Scenario: Skip non-markdown files
    Given a plain text file
    When I run md-toc on the file
    Then the file is skipped and not processed

  Scenario: Dry run leaves the file unchanged
    Given a markdown file with an "<!-- toc -->" placeholder
    When I run md-toc with --insert --dry-run
    Then the file is not modified
