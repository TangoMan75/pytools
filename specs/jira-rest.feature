Feature: Jira REST wrapper

  Scenario: Initialize credentials interactively
    When jira is run with "init"
    Then the three values are prompted and written to ~/.config/TangoMan75/jira/.env
    And the file is created with 0600 permissions

  Scenario: Overwrite existing credentials only with --force
    Given ~/.config/TangoMan75/jira/.env already exists
    When jira is run with "init" without --force
    Then the user is prompted to confirm and can abort

  Scenario: Fetch a ticket as markdown
    Given valid Atlassian credentials in the default .env
    When jira is run with "read PROJ-123"
    Then the markdown output contains the issue key heading
    And the markdown output contains a Description section
    And the markdown output contains a Comments section

  Scenario: Render comments from the paginated comment endpoint
    Given the comment endpoint returns multiple pages
    When jira fetches comments for "PROJ-123"
    Then all comments across pages are returned

  Scenario: Write markdown to an output file
    Given valid Atlassian credentials in the default .env
    When jira is run with "read PROJ-123 --output result.md"
    Then the markdown is written to "result.md"

  Scenario: Add a comment to a ticket
    Given valid Atlassian credentials in the default .env
    When jira is run with "update PROJ-123 --comment 'Verified'"
    Then a POST is sent to the comment endpoint with an ADF body

  Scenario: Missing subcommand is a usage error
    When jira is run with no arguments
    Then the run exits with code 2

  Scenario: Dry run prints the API requests
    When jira is run with "read PROJ-123 --dry-run"
    Then the issue and comment API URLs are printed

  Scenario: Basic auth is used with an email
    Given an email and token are configured
    When jira builds the auth header
    Then the Authorization header uses Basic auth

  Scenario: Bearer auth is used without an email
    Given only a token is configured
    When jira builds the auth header
    Then the Authorization header uses a Bearer token

  Scenario: HTTP error is reported as a runtime error
    Given the Jira API returns 401
    When jira fetches "PROJ-123"
    Then a runtime error is raised
