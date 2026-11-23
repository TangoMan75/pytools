Feature: OVHcloud TLD prices

  Scenario: Show TLD prices as a table
    When ovhcloud.py is run with no output option
    Then a formatted text table is printed to stdout
    And the table has columns Extension, Creation, and Renewal
    And each row shows the TLD, its creation price, and its renewal price
    And prices are shown in euros with two decimals

  Scenario: TLDs are sorted alphabetically
    When ovhcloud.py is run with no output option
    Then TLD rows are sorted alphabetically by extension

  Scenario: Markdown output
    When ovhcloud.py is run with "--md"
    Then a markdown table is printed to stdout
    And the table has columns Extension, Creation, and Renewal

  Scenario: CSV output
    When ovhcloud.py is run with "--csv"
    Then comma-separated values are printed to stdout
    And the CSV has columns tld, creation_eur, and renewal_eur
    And no table formatting or colors are printed to stdout

  Scenario: Output options are mutually exclusive
    When ovhcloud.py is run with "--md --csv"
    Then the run exits with code 2

  Scenario: Prices come from the OVHcloud TLD page
    Given the OVHcloud page contains a Drupal settings payload with TLD prices
    When ovhcloud.py fetches https://www.ovhcloud.com/fr/domains/tld/
    Then creation prices come from data-installation-price
    And renewal prices come from data-renew-price
    And entries missing either price are skipped

  Scenario: Zero creation price is valid
    Given the OVHcloud page lists a TLD with a zero creation price
    When ovhcloud.py is run
    Then that TLD is shown with a 0.00 creation price

  Scenario: Page fetch failure
    Given the OVHcloud page cannot be fetched
    When ovhcloud.py is run
    Then an error is printed to stderr
    And the run exits with code 1

  Scenario: Missing price payload
    Given the OVHcloud page does not contain the TLD price payload
    When ovhcloud.py is run
    Then an error is printed to stderr
    And the run exits with code 1

  Scenario: Quiet mode keeps runtime errors visible
    When ovhcloud.py is run with "--quiet" and the page cannot be fetched
    Then the fetch error is printed to stderr
    And the run exits with code 1

  Scenario: Bash completion
    When ovhcloud.py is run with "--completion"
    Then a bash completion script is printed to stdout
    And the script contains the option "--md"
    And the script contains the option "--csv"
