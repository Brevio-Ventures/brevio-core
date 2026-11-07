# brevio-core

Catches the mistakes coding agents repeat before they merge: a pull-request gate with no model call and no API key.
`scan`, the agent hook and the MCP server use no network and send nothing.

| In Plain English (For Anyone) | Technical Contract (For Engineers) |
| --- | --- |
| **What it does:** Checks code changes for common AI coding mistakes and repairs them locally before a pull request merges.<br>**When to use it:** On your laptop with Claude Code or Cursor, or in GitHub Actions on every pull request. | **CLI:** `brevio-core scan`, `brevio-core check`, `brevio-core task` (`connect`, `plan`, `build`, `qa`, `pr`)<br>**Catalogue:** 123 rules (13 scanned, 110 documented)<br>**Exit Codes:** The exit code is 0 when nothing is found, 1 when not. |

## Track 1: Start & Single-Task Workflow

- [Command reference](commands.md): every command and option (`scan`, `check`, `connect`, `plan`, `build`, `qa`, `pr`, `task`, `init --specs`), generated from the code.
- [The GitHub Action](action.md): inputs, permissions, events, merge queues and pinning to a commit.
- [Questions people ask](faq.md): why Python, why one line at a time, why an agent cannot silence it, how it compares.
- [Changelog](CHANGELOG.md)

## Track 2: Rules & Auto-Fix

- [Rules](rules/README.md): one page per rule, saying what it catches, why, a bad and a good example, and how it is checked.
- [Writing a rule](writing-rules.md): where a rule lives and what a pull request for one needs.

## Track 3: Coding Agents & MCP

- [Integrations](integrations/README.md): what each client gets and how to set it up.
- [Agent tools](agent-tools.md): `learn`, `hook install`, `gain`, `add`, `mcp` and the agent skill.
- [Claude Code](integrations/claude-code.md), [Cursor](integrations/cursor.md), [Codex](integrations/codex.md),
  [Hermes](integrations/hermes.md), [OpenClaw](integrations/openclaw.md)

## Track 4: Formats & Guardrails

- [Guards](guards.md): `.brevio/guards.json` and the agent rules `learn` writes.
- [SARIF](sarif.md): what `scan --sarif` writes for code scanning.

## Track 5: Precision, AEO & Releases

- [Precision on open-source repositories](precision.md): sampled precision across 10 repositories and 19,126 files.
- [Scoring a site for answer engines](aeo.md): `brevio-core aeo`, a separate command.
- [Releases and listings](LISTINGS.md): what a release does by itself, and the maintainers' steps.
- [Source and install instructions](https://github.com/Brevio-Ventures/brevio-core)
