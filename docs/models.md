# Models

`models.py` recommends OpenCode models by cost, intelligence, or recency. It
fetches the current model catalog from models.dev, composite intelligence
scores from BenchLM, and displays filtered results.

```text
python3 models.py (--cheapest | --free | --value | --best | --released | --updated
                   | --providers)
                  [--provider PROVIDER] [--min-context MIN_CONTEXT]
                  [--tool-call] [--reasoning] [--limit LIMIT] [--cache]
                  [--json | --md | --csv]
python3 models.py --go [--value | --best] [--cache] [--json | --md | --csv]
```

## Output Formats

The default output is a formatted text table in the terminal. Use `--json` for
JSON output, `--md` for markdown tables, or `--csv` for comma-separated values.

## Modes

- `--cheapest`: Show cheapest non-free models, sorted by total cost ascending
- `--free`: Show only free models, sorted by intelligence descending
- `--value`: Show best intelligence-per-dollar models, sorted by intelligence/total_cost descending
- `--best`: Show most intelligent models, sorted by BenchLM intelligence descending
- `--released`: Show most recently released models, sorted by release date descending
- `--updated`: Show most recently updated models, sorted by update date descending (default)
- `--providers`: List available providers and exit

`--free`, `--value`, and `--best` require the BenchLM leaderboard; the other
modes also fetch it (best-effort) so the Intel column can be shown.

## OpenCode Go

`--go` shows the OpenCode Go plan usage limits instead of the general model
recommendations. It fetches `https://opencode.ai/console/go`, parses the
Go-plan "Est. requests / 5 hr" column of the included-models table, and merges
each model with the models.dev catalog to add cost, context, and capability
data. The OpenCode Go provider entries take precedence when a model id or name
appears in several providers.

The table reports each model's estimated requests per 5-hour window (the
request allowance the plan buys for that model), input and output cost,
context window, capability flags, and a Score column. `--value` ranks by
intelligence × request allowance — how much intelligence one plan window of
the model can actually deliver — and the Score column shows each model's
share of that throughput relative to the strongest Go model, so it always
lies between 0 and 1 with the leader at 1.0000; `--best` ranks by
intelligence descending (both fetch the BenchLM leaderboard); without either
mode, models appear in request-allowance order and the Score column keeps the
legacy usage-adjusted score. Models with an unlimited allowance form their own
top tier, ordered by intelligence, and also show a 1.0000 share.
`--json`, `--md`, and `--csv` select the output format.

The console table lists the full set of supported models (currently 32) with a
request estimate for both the Go and Go Plus plans; the Go values are used and
the Go Plus values and monthly usage limits on the same row are ignored. Model
names and ids are matched to catalog ids with punctuation-insensitive
normalization, so differences such as `GPT 6 Luna` versus `GPT-6 Luna` still
resolve correctly.

Models advertised with an unlimited request allowance are marked as unlimited:
the table and markdown output show `∞`, CSV output prints `unlimited`, and JSON
output sets `requests` to `null` with `unlimited: true`. Unexpected runtime
errors are reported as a clean error message instead of a traceback; `--quiet`
does not hide them.

## Networking

All HTTPS fetches go through a single transport (`HttpTransport.fetch_text`)
that sends an identifying `User-Agent` and connects with IPv4 addresses tried
before IPv6, with a short per-address connect timeout. Hosts resolve to IPv6
first, so a dead IPv6 route would otherwise make every attempt stall for the
full fetch timeout; the transport skips it (Happy Eyeballs style) and remembers
the first working address family for the rest of the run.

## Filters

- `--provider PROVIDER`: Filter by provider name (default: opencode)
- `--min-context MIN_CONTEXT`: Minimum context window in tokens
- `--tool-call`: Only show models supporting tool calling
- `--reasoning`: Only show models supporting reasoning
- `--limit LIMIT`: Maximum results to show (default: 10)

## Intelligence (BenchLM)

`--value` and `--best` rank models by independent intelligence measurements
instead of the heuristic capability bonus. They fetch
`https://benchlm.ai/data/leaderboard.json`, a free static JSON download of the
BenchLM composite leaderboard (BenchAlign v5, 0-100 scale, no API key needed).
Scores are matched to models.dev entries by model id and name; plan, hosting,
and state markers are stripped during normalization (`-free`, `-ultraspeed`,
`-flex`, `-spot`, `-tee`, `-contributor`, `-preview`, `-reasoning`,
`-non-reasoning`, `-beta`, `-adaptive`, `-thinking`), and a token-set
comparison is the fallback. Model-defining markers are deliberately kept
(`-turbo`, `-lite`, `-codex`, `-chat`, effort knobs like `-max`/`-high`, date
stamps like `-0528`), so a variant never inherits another model's score.

- `--best` performs a raw intelligence ordering; models without a leaderboard
  entry show `-` for Intel and follow ranked ones, ordered by context,
  capabilities, and release date.
- `--value` is `intelligence / total_cost` (intelligence points per dollar).
  Free models score their raw intelligence, so free options lead paid ones.
- `--go --best` applies the intelligence ordering to Go plan models; `--go
  --value` ranks them by intelligence × request allowance instead (the fixed
  plan price buys a per-model request budget, so the allowance multiplies the
  usable intelligence), and the Score column shows that throughput as a
  relative share of the strongest Go model — always between 0 and 1, leader
  at 1.0000, unlimited allowance capped there too and placed first with
  intelligence breaking ties.

The Intel column appears in every mode: table and markdown output always
include it, and `intelligence` is part of the JSON and CSV fields (null/empty
when unmatched). For `--free`, `--value`, and `--best` the leaderboard is
required and a failed fetch stops the run; other modes degrade gracefully and
just show `-` when the fetch fails. The attribution credit is printed only when
at least one displayed model carries a score: on stdout for table and markdown
output, on stderr for `--json` and `--csv` so stdout stays machine-readable.
The data is licensed CC BY-NC 4.0: "Data from BenchLM.ai". `--cache` clears the
BenchLM cache together with the other caches. Roughly half of the catalog
entries carry a leaderboard score; the rest (embeddings, rerankers, older
releases, and niche listings) are absent from the source dataset.

## Score

The Score column keeps the heuristic value-for-money score
`(context_millions * bonus) / total_cost` where bonus factors in capabilities:
reasoning (+0.2), tool calling (+0.2), structured output (+0.2), and attachment
support (+0.1). It is shown for reference; the `--value` and `--best` rankings
themselves are driven by the BenchLM intelligence score. Go models use the
usage-adjusted variant `(context_millions * bonus * 1000/requests) /
total_cost`, and in `--go --value` mode the column is replaced by that
throughput as a share of the best Go model, so it stays between 0 and 1
(leader at 1.0000, unrated models empty, `null` in JSON).

## Capability Flags

The table includes capability flags:
- `R`: Reasoning
- `T`: Tool calling
- `S`: Structured output
- `A`: Attachment support

## Other Options

- `--cache`: Clear the cached catalog, Go models, and BenchLM leaderboard before fetching
- `--log`: Print the current log and stop
- `--verbose`, `-v`: Increase verbosity (stackable)
- `--quiet`: Suppress non-error output; runtime errors are still reported
- `--completion`: Print bash completion script to stdout and exit

## Examples

```bash
# Show top 5 most intelligent models
python3 models.py --best --limit 5

# Show best intelligence-per-dollar models across all providers
python3 models.py --value --provider '' --limit 10

# Show cheapest models with JSON output
python3 models.py --cheapest --json

# List all providers
python3 models.py --providers

# Show most intelligent reasoning models from OpenAI
python3 models.py --best --provider openai --reasoning --limit 10

# Show models with at least 200K context in markdown format
python3 models.py --best --min-context 200000 --md

# Order Go plan models by intelligence, or intelligence per dollar
python3 models.py --go --best
python3 models.py --go --value --md
```
