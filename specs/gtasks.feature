Feature: Google Tasks date filters

  Scenario: List tasks due in a date range
    When gtasks is run with --due --start "2026-08-01" --end "2026-08-01"
    Then the Tasks API should receive dueMin "2026-08-01T00:00:00Z"
    And the Tasks API should receive dueMax "2026-08-01T23:59:59Z"
    And completed tasks should be excluded

  Scenario: List tasks by completion time
    When gtasks is run with --completed --start "2026-08-01" --end "2026-08-01"
    Then the Tasks API should receive completedMin "2026-08-01T00:00:00Z"
    And the Tasks API should receive completedMax "2026-08-01T23:59:59Z"
    And completed tasks should be included

  Scenario: Retrieve all completed tasks without a date range
    When gtasks is run with --completed and without --start or --end
    Then the Tasks API should receive no timestamp bounds
    And completed tasks should be included
    And only completed tasks should be returned

  Scenario: Retrieve all due tasks without a date range
    When gtasks is run with --due and without --start or --end
    Then the Tasks API should receive no timestamp bounds
    And completed tasks should be excluded
    And tasks without a due date should be excluded

  Scenario: Show completed tasks within a date range
    When gtasks is run with --show-completed --start "2026-08-14" --end "2026-08-14"
    Then the Tasks API should receive completedMin "2026-08-14T00:00:00Z"
    And the Tasks API should receive completedMax "2026-08-14T23:59:59Z"
    And the Tasks API should receive showCompleted true
    And the Tasks API should receive showHidden true
    And only completed tasks should be returned

  Scenario: Show completed tasks including hidden ones
    When gtasks is run with --list "Work" and --show-completed
    Then the Tasks API should receive showCompleted true
    And the Tasks API should receive showHidden true
    And hidden completed tasks should be returned

  Scenario: Quiet mode returns task data without chatter
    When gtasks is run with --quiet
    Then task data should remain available on success

  Scenario: Quiet mode does not hide runtime errors
    When gtasks is run with --quiet and gws fails
    Then the command exits with code 1 and prints an error to stderr

  Scenario: Render tasks as front-matter markdown
    When gtasks is run with --md
    Then each task should render with due, updated, and optional completed metadata
    And each task should render with a level-two title and task status tags
    And links should render as one markdown list item per link
