Feature: OpenCode model recommendations

  Scenario: Show cheapest non-free models
    When models.py is run with "--cheapest"
    Then a formatted text table is printed to stdout by default
    And models are sorted by total cost ascending
    And free models are excluded from the results
    And the table includes an Intel column

  Scenario: Show best value-for-money models
    When models.py is run with "--value"
    Then a formatted text table is printed to stdout by default
    And models are sorted by intelligence per dollar descending
    And models without a BenchLM score are shown after ranked models
    And the BenchLM attribution credit is displayed

  Scenario: Show absolute best models
    When models.py is run with "--best"
    Then a formatted text table is printed to stdout by default
    And models are sorted by BenchLM intelligence score descending
    And models without a BenchLM score are shown after ranked models
    And the BenchLM attribution credit is displayed

  Scenario: Show most recently released models
    When models.py is run with "--released"
    Then a formatted text table is printed to stdout by default
    And models are sorted by release date descending
    And the table includes an Intel column

  Scenario: Show most recently updated models
    When models.py is run with "--updated"
    Then a formatted text table is printed to stdout by default
    And models are sorted by update date descending
    And the table includes an Intel column

  Scenario: Intelligence fetch failure degrades gracefully
    Given the BenchLM leaderboard cannot be fetched
    When models.py is run with "--released"
    Then the run completes without an error exit code
    And the Intel column shows "-" for every displayed model

  Scenario: Attribution credit only when scores are displayed
    Given no displayed model has a BenchLM intelligence score
    When models.py is run with "--released"
    Then no BenchLM attribution credit is printed

  Scenario: Best intelligence-per-dollar in JSON
    When models.py is run with "--value --json"
    Then valid JSON is printed to stdout
    And each model entry contains intelligence (null when unmatched)
    And the BenchLM attribution credit is printed to stderr

  Scenario: Filter by provider
    When models.py is run with "--cheapest --provider openai"
    Then only models from OpenAI providers are shown

  Scenario: Default provider is opencode
    When models.py is run with "--cheapest" without specifying --provider
    Then only models from the opencode provider are shown

  Scenario: List available providers
    When models.py is run with "--providers"
    Then a formatted text table is printed to stdout by default
    And each provider entry contains id, name, and model count

  Scenario: Filter by minimum context
    When models.py is run with "--cheapest --min-context 100000"
    Then only models with at least 100K context are shown

  Scenario: Filter by tool calling support
    When models.py is run with "--cheapest --tool-call"
    Then only models supporting tool calling are shown

  Scenario: Filter by reasoning support
    When models.py is run with "--cheapest --reasoning"
    Then only models supporting reasoning are shown

  Scenario: Limit results
    When models.py is run with "--cheapest --limit 3"
    Then at most 3 models are displayed

  Scenario: JSON output with --json flag
    When models.py is run with "--cheapest --json"
    Then valid JSON is printed to stdout
    And each model entry contains provider, id, name, costs, context, score, and intelligence (null when unmatched)

  Scenario: Table output is default
    When models.py is run with "--cheapest"
    Then a formatted text table is printed to stdout
    And the table has columns Provider, Model, In, Out, Context, Cap, Intel, Score

  Scenario: Mode flags are mutually exclusive
    When models.py is run with "--cheapest --best"
    Then the run exits with code 2

  Scenario: No mode flag defaults to updated
    When models.py is run with no mode flag
    Then models are sorted by update date descending

  Scenario: Combined filters
    When models.py is run with "--value --provider anthropic --reasoning --limit 5"
    Then only reasoning models from Anthropic are shown
    And at most 5 models are displayed

  Scenario: Markdown output
    When models.py is run with "--cheapest --md"
    Then a markdown table is printed to stdout
    And the table has columns Provider, Model, In, Out, Context, Cap, Intel, Score

  Scenario: CSV output
    When models.py is run with "--cheapest --csv"
    Then comma-separated values are printed to stdout
    And the CSV has columns provider, model, input_cost, output_cost, context, reasoning, tool_call, structured_output, attachment, intelligence, score

  Scenario: Show OpenCode Go usage limits
    When models.py is run with "--go"
    Then a formatted text table is printed to stdout by default
    And the table lists Go models with their estimated requests per 5-hour window
    And the table includes an Intel column
    And the source URL https://opencode.ai/console/go is displayed

  Scenario: Go usage limits in JSON
    When models.py is run with "--go --json"
    Then valid JSON is printed to stdout
    And each Go model entry contains id, name, requests, costs, context, score, and intelligence (null when unmatched)

  Scenario: Go usage limits in markdown
    When models.py is run with "--go --md"
    Then a markdown table is printed to stdout
    And the table has columns Model, Requests, In, Out, Context, Cap, Intel, Score

  Scenario: Go usage limits in CSV
    When models.py is run with "--go --csv"
    Then comma-separated values are printed to stdout
    And the CSV has columns model, requests, input_cost, output_cost, context, reasoning, tool_call, structured_output, attachment, intelligence, score

  Scenario: Go models ranked by intelligence throughput
    When models.py is run with "--go --value"
    Then Go models are displayed sorted by intelligence times request allowance descending
    And the Score column shows each model's share of the best throughput (0 to 1)
    And models without a BenchLM score are shown after ranked models
    And the BenchLM attribution credit is displayed

  Scenario: Go models keep the legacy Score without --value
    When models.py is run with "--go"
    Then the Score column shows the usage-adjusted score
    And models appear in request-allowance order

  Scenario: Go models sorted by intelligence
    When models.py is run with "--go --best"
    Then Go models are displayed sorted by BenchLM intelligence score descending
    And models without a BenchLM score are shown after ranked models
    And the BenchLM attribution credit is displayed

  Scenario: Go models with unlimited requests
    Given the Go documentation requests table contains an Unlimited value
    When models.py is run with "--go"
    Then that model is flagged unlimited without crashing
    And the requests column shows an infinity sign for that model

  Scenario: Go requests come from the console limits table
    Given the OpenCode console Go page lists Go and Go Plus request values
    When models.py is run with "--go"
    Then model names and request counts come from the Go plan values
    And the Go Plus values and monthly usage limits are ignored

  Scenario: Bash completion
    When models.py is run with "--completion"
    Then a bash completion script is printed to stdout
    And the script contains the option "--cheapest"
    And the script contains the option "--released"
    And the script contains the option "--updated"
    And the script contains the option "--providers"
    And the script contains the option "--go"
    And the script contains the option "--cache"

  Scenario: Clear cache before fetching
    When models.py is run with "--cache"
    Then the cached catalog, Go models, and BenchLM leaderboard are removed before the request
    And fresh data is fetched from the network
