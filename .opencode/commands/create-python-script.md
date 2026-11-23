---
description: Create a new self-contained Python CLI script following the pytools repository conventions (heel.py microframework, semantic coloring, handler pattern, CLI args, tests, specs, docs).
agent: build
---

# Create a Python Script

This command is a thin input layer. The full procedural logic lives in the
`create-python-script` skill, which is loaded below and is reusable on its own.

## 1. Parse `$ARGUMENTS`

Inspect the command arguments (`$ARGUMENTS`) and resolve the script request:

- The first whitespace-delimited token is the **script name** (hyphenated,
  e.g. `split-csv`). Capture it as the script name and do **not** ask the user
  to provide it again if present.
- The remaining text after the first token is the **description** of what the
  script does. Capture it as the description.
- If `$ARGUMENTS` is empty, or contains a name but no description, ask the user
  for the missing piece(s) before proceeding:
  - the hyphenated script name, and/or
  - a one-line description of what the script should do.
- If the argument provides only a partial or ambiguous request, ask only for the
  missing information. Do not re-ask for what was already supplied.

Pass the resolved script name and description forward to the skill as context;
do not re-ask for them once resolved.

## 2. Delegate to the skill

Load and follow the canonical instructions in the `create-python-script` skill
(`skills/create-python-script/SKILL.md`). All framework duplication, CLI design,
style rules, supporting files, and validation steps are defined there.

Execute the skill using the script name and description gathered above.
