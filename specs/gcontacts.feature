Feature: gcontacts
  As a user of Google Contacts
  I want a command-line wrapper around gws to read, create, update, and delete contacts
  So that I can manage my address book without leaving the terminal

  Background:
    Given the "gws" binary is available on PATH

  Scenario: List all contacts as JSON
    When I run "gcontacts.py"
    Then gws is invoked with "people people connections list"
    And the output is a JSON array of contact persons

  Scenario: Search contacts by query
    When I run "gcontacts.py --search john"
    Then gws is invoked with "people people searchContacts"
    And the output contains only contacts matching "john"

  Scenario: Get a single contact
    When I run "gcontacts.py --get people/c123"
    Then gws is invoked with "people people get"
    And the output is the single matching person resource

  Scenario: Create a contact from convenience flags
    When I run "gcontacts.py --create --name "John Doe" --email john@example.com"
    Then gws is invoked with "people people createContact"
    And the request body contains the display name "John Doe"

  Scenario: Create a contact from raw JSON
    When I run "gcontacts.py --create --json '{"names":[{"displayName":"X"}]}'"
    Then gws is invoked with "people people createContact"
    And the raw JSON body is forwarded unchanged

  Scenario: Update a contact from convenience flags
    When I run "gcontacts.py --update people/c123 --name "John" --email john@example.com"
    Then gws is invoked with "people people updateContact"
    And the request includes an updateMask covering names and emailAddresses

  Scenario: Update a contact with raw JSON requires an update mask
    When I run "gcontacts.py --update people/c123 --json '{}'"
    Then the command exits with code 2

  Scenario: Delete a contact
    When I run "gcontacts.py --delete people/c123"
    Then gws is invoked with "people people deleteContact"
    And the resourceName parameter is "people/c123"

  Scenario: Quiet mode does not swallow runtime errors
    When I run "gcontacts.py --list --quiet" and gws fails
    Then the command exits with code 1 and prints an error to stderr
