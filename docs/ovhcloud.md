# OVHcloud TLD prices

`ovhcloud.py` prints the current OVHcloud domain-extension creation and renewal
prices. It fetches the public French price page
`https://www.ovhcloud.com/fr/domains/tld/`, extracts the embedded Drupal
settings payload, and writes the price list to stdout.

```text
python3 ovhcloud.py [--md | --csv] [--verbose] [--quiet] [--log] [--completion]
```

## Output formats

The default output is a formatted text table:

```text
  Extension     Creation    Renewal
  --------------------------------
  .com              8.49      14.29
  .fr               4.99       7.79
```

Use `--md` for a markdown table or `--csv` for comma-separated values. The two
options are mutually exclusive. Markdown output adds a heading; CSV output
contains only the header and data rows so it can be piped into other tools.

| Format | Columns |
|---|---|
| Table / Markdown | Extension, Creation, Renewal |
| CSV | `tld,creation_eur,renewal_eur` |

Prices are in euros with two decimals and represent the yearly prices shown on
the OVHcloud page. The creation column is the initial registration price,
including any promotion currently displayed by OVHcloud. The renewal column is
the standard renewal price. Entries without both values are skipped. A missing
price source or a failed fetch is reported on stderr and exits with code `1`.

TLDs are sorted alphabetically by extension, including internationalized
extensions in their punycode form (`xn--...`).

## Source

The page embeds all prices in a JSON payload inside a
`<script data-drupal-selector="drupal-settings-json">` tag, under
`ovh_domain_names.pricesData`. The script reads `data-installation-price` for
creation and `data-renew-price` for renewal. Prices and promotions can change at
any time; the script always fetches the live page and does not cache results.

## Examples

```bash
# Full price list as a table
python3 ovhcloud.py

# Markdown table
python3 ovhcloud.py --md

# CSV, then look up one extension
python3 ovhcloud.py --csv | grep '^\.com,'

# Save the CSV for a spreadsheet
python3 ovhcloud.py --csv > tlds.csv
```

## Options

- `--md`: Output a markdown table
- `--csv`: Output comma-separated values
- `--verbose`, `-v`: Increase verbosity (stackable)
- `--quiet`: Suppress non-error output; runtime errors are still reported
- `--log`: Print the current log file and stop
- `--completion`: Print the bash completion script to stdout and exit
