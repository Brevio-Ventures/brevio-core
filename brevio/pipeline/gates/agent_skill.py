"""The agent skill text of the ``brevio-core`` package (ROADMAP E16, the 0.2 set, 2026-11-05).

One source for the skill file: ``hook install`` writes it into each coding agent's skills folder, and the exporter
ships the same text as ``skills/brevio-core/SKILL.md`` (the core exporter). The format is the common
agent-skills one: YAML frontmatter with ``name`` and ``description``, then plain Markdown. Standard library only.
The frontmatter keeps to the portable keys (name, description, license, compatibility, metadata). A test
(``tests/pipeline/core_export/test_core_skill.py``) checks that every command the text names exists. ``AGENT_RULES``
is also the block ``brevio-core init`` writes into ``AGENTS.md`` and a Cursor rule, so the three cannot drift (ROADMAP
E22, 2026-11-05).
"""
from __future__ import annotations

SKILL_PATH = "skills/brevio-core/SKILL.md"

AGENT_RULES = """- After you edit code, scan the files you changed: `brevio-core scan <files>`.
- Fix every finding in the code itself, also those the agent hook reports after an edit or before you stop.
- Never add an ignore comment and never edit `.brevio/baseline.json` to make a finding go away.
- When you cannot fix a finding, stop and tell the human the rule and the line.
- After you fix a bug, run `brevio-core learn` so the fix becomes a guard.
"""

SKILL_MD = f"""---
name: brevio-core
description: Check code you wrote or changed against deterministic code rules, with no model call; `scan`, the agent hook and the MCP server use no network and send nothing. Use it after editing files, before running tests or opening a pull request, and after fixing a bug you want to stop coming back.
license: Apache-2.0
compatibility: Needs Python 3.10 or newer and the brevio-core package (pip install brevio-core, or run it with uvx).
metadata: {{"version": "0.2", "openclaw": {{"homepage": "https://brevio.pro", "requires": {{"bins": ["brevio-core"]}}}}}}
---

# brevio-core

A local rule gate for the mistakes coding agents keep repeating. It reads the lines a change adds and checks them
against fixed code rules. It makes no model call and needs no API key; `scan`, the agent hook and the MCP server use
no network and send nothing.

## When to run it

- After you edit or create code files: scan what you touched.
- Before you run the test suite or open a pull request: scan the whole change.
- After you fix a bug that escaped: compile the fix into a guard so it cannot return.

## Commands

```
brevio-core scan src/                  # files or folders
brevio-core scan --diff origin/main    # only the lines added against a base
brevio-core scan --diff --sarif out.sarif
brevio-core learn                      # compile the last commit's fix into a guard
brevio-core learn --check src/a.py     # run the learned guards over whole files
brevio-core add                        # list the curated guard packs
brevio-core hook install               # wire the scan into the coding agents found here
brevio-core gain                       # print the receipt of what the guards caught
brevio-core mcp                        # serve these tools over MCP on stdin and stdout
```

If the command is not on the path, put `uvx` in front of it.

The MCP server offers `scan`, `explain`, `list_rules` and `learn` as tools, so an agent can call them without a shell.

## How to read findings

Each finding is one line: `path:line: [RULE] message`. The exit code is 0 when nothing is found, 1 when there are
findings and 2 for a usage error.

- Fix the code the line points at. An agent cannot silence a rule: the hook and the MCP tools do not honour an ignore
  comment, and one added to a pull request is reported until a human reviews it. A human can, with a reason.
- Run `brevio-core mcp` and call `explain` with the rule id, or open `docs/rules/<RULE>.md`, to see what the rule
  catches, why, and a bad and a good example.
- Scan again after the fix. Stop when the exit code is 0.
- A finding in a line you did not add is not yours to fix in this change: scan with `--diff` to see only your lines.

## Rules

{AGENT_RULES}"""
