# Command reference

Every `brevio-core` command and option, generated from the argument definitions in the code; do not edit by hand. Unless a command says otherwise, the exit code is 0 for success, 1 for findings and 2 for a usage error. `brevio-core <command> --help` prints the same text.

| Command | What it does |
| --- | --- |
| [`brevio-core scan`](#brevio-core-scan) | scan files, folders or a diff against the 12 rules the scanner checks (of 123 documented) |
| [`brevio-core baseline`](#brevio-core-baseline) | record the current findings in .brevio/baseline.json, so scan reports only new ones |
| [`brevio-core config`](#brevio-core-config) | show the brevio-core.toml settings that apply to a file or folder |
| [`brevio-core leaks`](#brevio-core-leaks) | check a folder for stray URLs, emails and paths that should not be public |
| [`brevio-core learn`](#brevio-core-learn) | compile a fixed defect (a git diff) into a local guard and an agent rule |
| [`brevio-core hook`](#brevio-core-hook) | install the scan hook into the coding agents found here (hook install \| status \| detect) |
| [`brevio-core gain`](#brevio-core-gain) | print the savings receipt: counts always, savings only when measured |
| [`brevio-core add`](#brevio-core-add) | add a curated guard pack by name (no name lists the packs) |
| [`brevio-core mcp`](#brevio-core-mcp) | serve scan, explain, list_rules and learn to an agent over MCP on stdin and stdout |
| [`brevio-core init`](#brevio-core-init) | set this repository up in one step: the Action, agent rules and a baseline (init --undo takes it back) |
| [`brevio-core aeo`](#brevio-core-aeo) | score a folder of built HTML pages, with its robots.txt and llms.txt, against the AEO rubric |
| [`brevio-core check`](#brevio-core-check) | run the pre-PR flight check (rules, test custody, test imports, conflict markers and complexity) |
| [`brevio-core brief`](#brevio-core-brief) | print the zero-token rule & trap briefing for the files you are about to edit |
| [`brevio-core score`](#brevio-core-score) | compute the deterministic Agent Safety Score (0-100, A+ to F), README badge and scorecard |
| [`brevio-core up`](#brevio-core-up) | show what a team sync would take from this repository, and the waitlist link (uploads nothing) |

## `brevio-core scan`

Scan files, folders or a diff against the 12 rules the scanner checks (of 123 documented).

```
brevio-core scan [options] [paths ...]
```

| Argument | Default | What it does |
| --- | --- | --- |
| `[paths ...]` |  | files or folders to scan (default: the current folder) |
| `--file PATH` |  | a file to scan (repeatable) |
| `--diff [BASE]` |  | scan only the lines added against BASE (default origin/main) |
| `--sarif FILE` |  | also write the findings to FILE as SARIF |
| `--forbid-ignores` |  | never honour an ignore comment (the agent hook runs with this, so an agent cannot silence a rule) |
| `--surface` |  | also run the 9 surface-scoped rules (UI blur, SSR reveal, GTM deferral, webhook HMAC, integer cents, self-mocking tests, weak assertions, contract purity, package imports) |
| `--fix` |  | rewrite in place what a rule has one correct fix for, then scan again |
| `--dry-run` |  | with --fix: print the fixes as a unified diff and write nothing |
| `--fail-on {new,all,none,error}` | `new` | new (default): baselined findings are hidden and pass; all: ignore the baseline, any finding fails; none: report what is not baselined and always exit 0; error: like new, but only error-level findings fail (warn-level ones are reported). A preview rule never fails |
| `--allow-new-suppressions` |  | with --diff: do not report the ignore comments and baseline entries the change adds (for a change a person has reviewed) |
| `--format {text,markdown,agent}` | `text` | how to print the findings (agent: one short line each with a fix hint, grouped by rule, at most 20) |
| `--rules-url BASE` |  | with --format markdown: link each rule ID to BASE&lt;ID&gt; |
| `--no-upgrade-line` |  | with --format markdown: leave out the closing Teams line (the Action's footer: false) |

## `brevio-core baseline`

Record the current findings in .brevio/baseline.json, so scan reports only new ones.

```
brevio-core baseline [options] [paths ...]
```

| Argument | Default | What it does |
| --- | --- | --- |
| `[paths ...]` |  | files or folders (default: the current folder) |
| `--diff [BASE]` |  | record only the findings on the lines added against BASE (default origin/main) |

## `brevio-core config`

Show the brevio-core.toml settings that apply to a file or folder.

```
brevio-core config [options] [path]
```

| Argument | Default | What it does |
| --- | --- | --- |
| `[path]` |  | the file or folder (default: the current folder) |
| `--json` |  | print it as JSON |

## `brevio-core leaks`

Check a folder for stray URLs, emails and paths that should not be public.

```
brevio-core leaks [root]
```

| Argument | Default | What it does |
| --- | --- | --- |
| `[root]` |  | the folder to check (default: the current folder) |

## `brevio-core learn`

Compile a fixed defect (a git diff) into a local guard and an agent rule.

Compile fixed defects into zero-token guards and progressive agent rules.

```
brevio-core learn [options]
```

| Argument | Default | What it does |
| --- | --- | --- |
| `--diff DIFF` | `HEAD~1` | Git diff commit or range (default: HEAD~1) |
| `--staged` |  | compile the staged fix (git diff --cached) instead of --diff |
| `--worktree` |  | compile the uncommitted fix (the working tree against HEAD) |
| `--dry-run` |  | print the guard and how many lines of the repository it matches; write nothing |
| `--file FILE` |  | Specific file to inspect or extract diff from |
| `--name NAME` |  | Human-readable title for the synthesized guard |
| `--category {security,robustness,functional,compliance,finops}` | `robustness` |  |
| `--json` |  | Output result as JSON |
| `--check FILE` |  | Run the learned guards over these files instead of compiling one |

## `brevio-core hook`

Install the scan hook into the coding agents found here (hook install | status | detect).

Wire zero-token hooks and progressive rules into coding agents (Claude, Cursor, Hermes).

```
brevio-core hook [options] {install,status,detect,run} ...
```

| Argument | Default | What it does |
| --- | --- | --- |
| `--json` |  | Output status as JSON |

### `brevio-core hook install`

Install hooks into detected agent configurations.

```
brevio-core hook install [options]
```

| Argument | Default | What it does |
| --- | --- | --- |
| `--all` |  | Force install into all supported agents |
| `--target TARGET` |  | Comma-separated agents (claude_code,cursor,hermes,openclaw) |
| `--json` |  | Output status as JSON |

### `brevio-core hook status`

Check hook installation status.

```
brevio-core hook status [options]
```

| Argument | Default | What it does |
| --- | --- | --- |
| `--json` |  | Output status as JSON |

### `brevio-core hook detect`

Auto-detect available LLM clients, agents and local daemons.

```
brevio-core hook detect [options]
```

| Argument | Default | What it does |
| --- | --- | --- |
| `--json` |  | Output status as JSON |

### `brevio-core hook run`

The hook itself: reads a client's event JSON on stdin (run --event post-edit|stop).

The hook a coding client calls: reads its event JSON on stdin and answers with the findings in that client's format. Always exits 0.

```
brevio-core hook run [options]
```

| Argument | Default | What it does |
| --- | --- | --- |
| `--event {post-edit,post-command,stop}` |  | post-edit: after a file edit; post-command: after a shell command (a fix commit gets a `learn` suggestion); stop: before the agent finishes |
| `--client {claude-code,cursor}` | `claude-code` | the client whose config holds this hook (the reply follows the client that sent the event) |
| `--budget SECONDS` | `2.0` | give up quietly after this long (default 2) |

## `brevio-core gain`

Print the savings receipt: counts always, savings only when measured.

Show the savings receipt: defects intercepted, learned guards active, and savings when measured.

```
brevio-core gain [options]
```

| Argument | Default | What it does |
| --- | --- | --- |
| `--json` |  | Output metrics as JSON |
| `--no-upgrade-line` |  | leave out the closing Teams line |

## `brevio-core add`

Add a curated guard pack by name (no name lists the packs).

```
brevio-core add [options] pack
```

| Argument | Default | What it does |
| --- | --- | --- |
| `pack` |  | Name of the pack to install |
| `--json` |  | Output result as JSON |

## `brevio-core mcp`

Serve scan, explain, list_rules and learn to an agent over MCP on stdin and stdout.

It takes no arguments.

## `brevio-core init`

Set this repository up in one step: the Action, agent rules and a baseline (init --undo takes it back).

```
brevio-core init [options]
```

| Argument | Default | What it does |
| --- | --- | --- |
| `--with PARTS` |  | also write these, comma-separated: precommit, hook, mcp |
| `--without PARTS` |  | leave these out: action, agents-md, baseline |
| `--dry-run` |  | print the plan and write nothing |
| `--yes, -y` |  | write without asking |
| `--undo` |  | remove what init wrote and is unchanged since |
| `--personal` |  | install personal agent hooks and MCP config only, git-excluded via .git/info/exclude (touches no tracked files) |
| `--wizard` |  | run the interactive onboarding wizard |

## `brevio-core aeo`

Score a folder of built HTML pages, with its robots.txt and llms.txt, against the AEO rubric.

It reads local files only; save a page before you score it.

```
brevio-core aeo [options] target
```

| Argument | Default | What it does |
| --- | --- | --- |
| `target` |  | a folder of built pages (with robots.txt and llms.txt at its root), or one .html page |
| `--min SCORE` | `0` | exit 1 when a page scores below SCORE, out of 100 (default 0: report only) |
| `--format {text,markdown,json}` | `text` | how to print the scorecard |
| `--generate-llms` |  | write a missing llms.txt at the target folder's root from its HTML pages before scoring |

## `brevio-core check`

Run the pre-PR flight check (rules, test custody, test imports, conflict markers and complexity).

```
brevio-core check [options] [paths ...]
```

| Argument | Default | What it does |
| --- | --- | --- |
| `--base BASE` | `HEAD` | git base ref to compare against (default: HEAD) |
| `--json` |  | output JSON receipt |
| `--format {text,markdown,json}` | `text` | receipt format |
| `[paths ...]` |  | optional paths to check |

## `brevio-core brief`

Print the zero-token rule & trap briefing for the files you are about to edit.

```
brevio-core brief [options] [files ...]
```

| Argument | Default | What it does |
| --- | --- | --- |
| `[files ...]` |  | files to generate briefing for |
| `--json` |  | output briefing as JSON |
| `--record ('RULE', 'TRAP', 'FIX')` |  | record a Trap -&gt; Fix episode for the first named file |

## `brevio-core score`

Compute the deterministic Agent Safety Score (0-100, A+ to F), README badge and scorecard.

```
brevio-core score [options] [paths ...]
```

| Argument | Default | What it does |
| --- | --- | --- |
| `[paths ...]` |  | files or folders to score (default: the current folder) |
| `--diff [BASE]` |  | score only the lines added against BASE (default origin/main) |
| `--min SCORE` | `0` | exit 1 when the score is below SCORE (default 0) |
| `--format {text,markdown,json}` | `text` | output format (default: text) |
| `--json` |  | output scorecard as JSON |
| `--badge` |  | print only the Markdown shield badge |
| `--roast` |  | include the verdict roast line |
| `--no-upgrade-line` |  | leave out the closing Teams line |

## `brevio-core up`

Show what a team sync would take from this repository, and the waitlist link (uploads nothing).

```
brevio-core up [options]
```

| Argument | Default | What it does |
| --- | --- | --- |
| `--json` |  | print the files, sizes and fields as JSON |
