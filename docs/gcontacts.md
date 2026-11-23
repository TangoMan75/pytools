# Google Contacts

`gcontacts.py` reads, creates, updates, and deletes Google Contacts
through the `gws` command-line tool. It wraps the `gws people people`
resource methods (`connections list`, `searchContacts`, `get`,
`createContact`, `updateContact`, `deleteContact`).

```text
python3 gcontacts.py [--list]
                      [--search QUERY]
                      [--get RESOURCE]
                      [--create] [--update RESOURCE] [--delete RESOURCE]
                      [--name N] [--email E] [--phone P] [--org O]
                      [--address A] [--note T] [--url U]
                      [--json BODY] [--update-mask MASK]
                      [--mask FIELDS] [--limit N] [--md] [--dry-run]
                      [--quiet] [-v] [--completion]
```

The action flags (`--list`, `--search`, `--get`, `--create`, `--update`,
`--delete`) are mutually exclusive. With no action flag, the script lists
all contacts (equivalent to `--list`).

## Arguments

- `--list`: list all contacts via `connections.list`, paginating through
  every page. Honors `--limit` (0 = all) and `--mask`.
- `--search QUERY`: search grouped contacts whose names, email addresses,
  phone numbers, or organizations match `QUERY`.
- `--get RESOURCE`: fetch one contact by its resource name (e.g.
  `people/c123...`). Requires `personFields` (`--mask`).
- `--create`: create a contact. Requires `--name` (or `--json`). Convenience
  flags `--email`, `--phone`, `--org`, `--address`, `--note`, `--url` build
  the request body. `--json` forwards a raw People API body instead.
- `--update RESOURCE`: update a contact. Convenience flags build a body and
  an `updateMask` derived from the supplied fields, each tagged with the
  contact's `CONTACT` source. With `--json`, an explicit `--update-mask` is
  required.
- `--delete RESOURCE`: delete a contact by resource name.
- `--mask FIELDS`: comma-separated `personFields` / `readMask` (default:
  `names,emailAddresses,phoneNumbers,organizations,addresses,metadata`).
- `--limit N`: maximum contacts to list or search (default 0 = all).
- `--json BODY`: raw People API JSON body for `--create` / `--update`
  (overrides convenience flags).
- `--update-mask MASK`: explicit `updateMask` for `--update`. Required when
  using `--json`; otherwise it defaults to the fields you provide.
- `--dry-run`: pass `gws --dry-run` so requests are validated locally without
  mutating any contact. Useful for create/update/delete.
- `--md`: render contacts as YAML front-matter markdown instead of JSON.
- `--quiet`: suppress non-error output; gws runtime errors are still reported and exit 1.
- `--completion`: print a bash completion script and exit.

## Updating contacts

`--update` fetches the contact first to obtain its real source id and `etag`,
then attaches them to the request body (the People API requires both for a
successful `updateContact`). Convenience flags build the body and derive the
  `updateMask`; with `--json` you must supply an explicit `--update-mask`.

## Exit codes

- `0`: success
- `1`: gws invocation failed
- `2`: invalid CLI usage (missing required flags)

## Examples

```bash
# List all contacts as JSON
python3 gcontacts.py

# Search and render as markdown
python3 gcontacts.py --search "john" --md

# Create a contact with name and email
python3 gcontacts.py --create --name "John Doe" --email john@example.com

# Update a contact's phone number
python3 gcontacts.py --update people/c123 --phone "+33123456"

# Delete a contact
python3 gcontacts.py --delete people/c123
```
