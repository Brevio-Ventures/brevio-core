# Agent tools (the 0.2 set)

| In Plain English (For Anyone) | Technical Contract (For Engineers) |
| --- | --- |
| **What it does:** Gives your coding agent local hooks, learned bug guards, and an MCP server so it catches and repairs its own mistakes while editing.<br>**When to use it:** Inside any git checkout alongside Claude Code, Cursor, Codex, Hermes, or OpenClaw. | **Commands:** `brevio-core learn`, `brevio-core hook install`, `brevio-core gain`, `brevio-core add`, `brevio-core mcp`<br>**Artifacts:** `.brevio/guards.json`, `.agents/rules/`, `skills/brevio-core/SKILL.md`<br>**Exit Codes:** The exit code is 0 when nothing is found, 1 when not. |

Five commands and an agent skill for the project you run them in. All are local, with no model call and no API key;
`scan`, the agent hook and the MCP server use no network and send nothing. They work in the current folder, which
should be a git checkout.

## `brevio-core learn`

Turns a fixed defect into a guard.

```
brevio-core learn                  # from the last commit (git diff HEAD~1)
brevio-core learn --diff main~3    # from another commit or range
brevio-core learn --name "no sleep in handlers" --category robustness
brevio-core learn --check src/a.py src/b.py
brevio-core learn --worktree --dry-run      # a fix not committed yet: print the guard and its hits, write nothing
brevio-core learn --staged                  # the staged fix (git diff --cached)
```

It reads the lines the fix removed and writes the guard to `.brevio/guards.json`, plus an agent rule to
`.agents/rules/<id>.md`. A new guard is on trial: it becomes active after five clean runs and is retired when it
fires wrongly too often. `--check` runs the live guards over whole files and exits 1 on a hit. `--dry-run` (from
release 0.4) prints the guard and how many lines of the repository it matches today, so an agent can check that a
guard is not too broad before it keeps one.

## `brevio-core hook install`

Installs the scan hook for the coding agents found in the folder or on the machine.

```
brevio-core hook status
brevio-core hook detect
brevio-core hook install                       # only the agents it finds
brevio-core hook install --target claude_code  # named agents
brevio-core hook install --all
```

It writes `.claude/settings.json` (Claude Code: `PostToolUse` on `Edit|Write|MultiEdit`, and `Stop`),
`.cursor/hooks.json` (Cursor: `postToolUse` on `Write`, and `stop`), `.cursor/rules/`, and the agent skill (see below)
into the skills folders of the agents it wires. Running it twice changes nothing, and other hooks in those files are
kept.

Each hook runs `brevio-core hook run --event post-edit` or `--event stop` (from release 0.4). The client passes the
event as JSON on standard input. After an edit the hook scans the lines that file now adds; when the agent is about to
stop it scans the uncommitted changes, once. Findings go back through the client's own channel, one short line each
(`path:line [RULE] message -> fix`), so the agent fixes them without a human turn. An ignore comment never counts here.
The hook never blocks an agent on its own failure: on an error or past its time budget it lets the agent go on.

## The agent skill

`skills/brevio-core/SKILL.md` in this repository is the skill file: YAML frontmatter with a `name` and a
`description`, then when to run the commands, the commands, and how to read a finding. `hook install` writes the same
text to `.claude/skills/brevio-core/SKILL.md`, `.hermes/skills/brevio-core/SKILL.md` and `skills/brevio-core/SKILL.md`
and replaces any older skill text it finds there. A test checks that every command the skill names exists.

## `brevio-core gain`

Prints the savings receipt: how many defects the guards and hooks caught, and how many learned guards are live.

```
brevio-core gain
brevio-core gain --json
```

Tokens and money are shown only when a caller recorded a measured value for the event. There is no estimate per
catch, so a project with no measured value shows counts and nothing else. The receipt link is built on your machine
from the numbers shown, and stays on it until you open or share the link yourself.

## `brevio-core add`

Adds a curated guard pack by name.

```
brevio-core add                    # list the packs
brevio-core add fastapi-async
```

A pack writes its guards to `.brevio/guards.json` and its rules to `.agents/rules/`, active at once.

## `brevio-core mcp`

An MCP server over stdio for any agent client that can start one. It speaks newline-delimited JSON-RPC 2.0, answers
`initialize`, `ping`, the tool list and the tool call, and needs no package beyond the standard library. It makes no model call,
and it reads only the folder it was started in: a path outside that folder is refused.

```json
{ "mcpServers": { "brevio-core": { "command": "brevio-core", "args": ["mcp"] } } }
```

| Tool | Arguments | Returns |
|---|---|---|
| `scan` | `paths` (files or folders), `diff_base` (scan only the lines added against a git revision) | the findings, each with path, line, rule id and message; a long list is cut and says so |
| `explain` | `rule` (an id such as `R2.1`) | the rule page: what it catches, why, a bad and a good example |
| `list_rules` | `query` (optional word) | every rule id with a one-line summary |
| `learn` | `diff_base` (default `HEAD~1`), `name` | the compiled guard; writes `.brevio/guards.json` and `.agents/rules/` |

A tool that cannot do what was asked returns an error result with the reason; the session carries on.
