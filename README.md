# brevio-core

Catches the mistakes coding agents repeat before they merge: a pull-request gate with no model call and no API key.

Save this as `.github/workflows/brevio-core.yml`:

```yaml
name: brevio-core
on:
  pull_request:
  merge_group:
permissions:
  contents: read
  pull-requests: write     # the comment on the pull request
  security-events: write   # the upload to code scanning
jobs:
  brevio-core:
    name: brevio-core
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09 # v5.1.0
        with:
          fetch-depth: 0
      - uses: Brevio-Ventures/brevio-core@v0.6.0
        with:
          sarif: true
```

<!-- The picture of the pull request comment goes here: docs/img/pr-comment.png, a screenshot of a real run. -->

It catches what review keeps finding in agent-written code:

- secrets written into source, `eval` on input, and `any` casts on data from outside;
- type errors silenced with `@ts-ignore`, and exceptions caught and dropped;
- fixed sleeps in end-to-end tests, images without alt text, and click handlers a keyboard cannot reach.

**No API key, no model. `scan`, the agent hook and the MCP server use no network and send nothing.**

These are line-level pattern checks on the lines a change adds, not AST or dataflow analysis. The catalogue has
123 rules: `brevio-core scan` checks 8 scanned rules, and the other 115 are documented rules,
written down for review and for agents, with no scanner in this package yet. Every finding links to its
[rule page](docs/rules/README.md): what it catches, why, a bad and a good example.

## Run it without installing

Version 0.6.0, Python 3.10 or newer, no runtime dependencies. In a repository, scan the lines your change adds:

```sh
uvx brevio-core@0.6.0 scan --diff
```

```sh
pipx run --spec brevio-core==0.6.0 brevio-core scan --diff
```

Or install it, then run it the same way:

```sh
pip install brevio-core==0.6.0
```

<!-- readme-test -->
```sh
brevio-core scan --diff
```

Or download `brevio-core.pyz` from the [GitHub release](https://github.com/Brevio-Ventures/brevio-core/releases), check where it
was built, and run it with any `python3`:

```sh
gh attestation verify brevio-core.pyz --repo Brevio-Ventures/brevio-core
python3 brevio-core.pyz scan --diff
```

To scan whole files instead, name them, or nothing for the current folder:

<!-- readme-test -->
```sh
brevio-core scan
```

## Set it up in one step

<!-- readme-test -->
```sh
brevio-core init --dry-run
```

`--dry-run` shows, as a diff, what `brevio-core init` would write, and writes nothing. `init` writes a pull-request
workflow like the one above (pinned to this release), a block of agent rules in `AGENTS.md` and a baseline, so the
first local run is quiet. `--with precommit,hook,mcp` adds the pre-commit entry, the agent hook and the MCP server
config. It asks before it writes (`--yes` skips the question), never rewrites a file you have, and records what it
wrote in `.brevio/init.json`; `brevio-core init --undo` removes what it wrote and you have not changed since.

## Adopt it on a repository that already has findings

```
brevio-core baseline                 # record the findings the repository has now in .brevio/baseline.json
brevio-core scan                     # report only the findings that are not in the baseline
brevio-core scan --fail-on none      # report them but never fail, for a trial week
brevio-core scan --fail-on all       # leave the baseline out: every finding fails
```

A baseline entry names the file, the rule and a hash of the line's text, not its line number, so moving a line does
not make it new. Commit the file. Run `baseline` again after a fix and the fixed entries drop out. The file holds one
entry per line, sorted, so branches that add entries merge cleanly.

## Silence one finding, with a reason

```ts
// brevio-core: ignore R9.2 -- the generated client has no type for this field
// @ts-ignore
```

The comment goes on the line or the line above, and silences that rule there. Without `-- reason` it does not count,
and the scan warns about it and about a rule ID that does not exist. The summary line counts what was silenced, and
SARIF carries each one as a suppression with its reason, which code scanning shows.

Only a person can silence the gate. The agent hook and the MCP tools never honour an ignore comment
(`--forbid-ignores`), and a diff scan reports each ignore comment and baseline entry the change adds as a finding,
"new suppression: needs a human review", until a reviewer allows it with `--allow-new-suppressions`.

## A report for the pull request

`brevio-core scan --diff origin/main --format markdown` prints the findings as a Markdown table of rule, file and line,
and why, for a job summary or a pull request comment. `--rules-url BASE` links each rule ID to its page at `BASE`
followed by the ID. Paths and lines from the repository are escaped, so a file name cannot add a mention or a link.

## Configure it for a team

Put a `brevio-core.toml` at the root of the repository, and another in any folder that needs its own settings. For a
file, the files from the root down to its folder apply in that order, so the nearest one wins.

```toml
extends = "policy/brevio-core.toml"   # an org policy, read first (see below)
select = ["R9", "R13.1"]              # the rules that run: an ID, a group or a glob (default: every rule)
ignore = ["R6.3"]                     # rules that do not run
exclude = ["generated/**", "*.pb.ts"] # paths not scanned, relative to this file's folder
level = "warn"                        # the level of every rule (default: error)

[rules."R13.1"]
level = "error"                       # the level of one rule

[[overrides]]
paths = ["legacy/**"]                 # relative to this file's folder
ignore = ["R9.1"]                     # rules that do not run on these paths
rules = ["R9"]                        # the rules the level applies to (default: every rule)
level = "warn"
```

A nearer file replaces `select` and `ignore`; `exclude` and `[[overrides]]` add up; for a level, the last setting that
names the rule wins. An unknown key, a wrong value or a broken file stops the scan as a usage error, and a rule pattern
that matches no rule is a warning. Write a rule ID in quotes as a table name, as in `[rules."R13.1"]`.

Every scan already skips code a project keeps but did not write: dependencies and build output (`node_modules/`,
`dist/`, `build/`, `.next/`, virtual environments), vendored folders (`vendor/`, `third_party/`, `third-party/`),
minified files (`*.min.js`, `*.min.mjs`, `*.min.cjs`, `*.min.css`), bundle chunks (`*.chunk.js`, `*.bundle.js`,
`chunk-*.js`, and names that end in a hex hash, such as `index-<hash>.js`) and any file whose first two lines are
longer than five hundred characters. A file named on the command line is scanned as asked. No rule reads a TypeScript
declaration file (`*.d.ts`, `*.d.mts`, `*.d.cts`), named or not: it holds types, no code that runs. Exclude more, such
as generated code or a third-party folder with another name, with `exclude`.

`brevio-core config src/app.ts` shows what applies to a file or folder: the files it comes from, whether it is
excluded, and each rule that runs there with its level and status (`--json` for a tool).

`brevio-core scan --fail-on error` (in the Action, `fail-on: error`) fails only on error-level findings and reports the
warn-level ones; the default, `--fail-on new`, fails on every new finding whatever its level. A preview rule never
fails a scan (see [RULES-STABILITY.md](RULES-STABILITY.md)). A config can turn rules off, so a diff scan reports a
change that adds or edits a `brevio-core.toml` as a new suppression, as it does an ignore comment.

### An org policy with `extends`

`extends` reads a policy file before the file that names it; the policy's paths are relative to that file's folder.

- `extends = "policy/brevio-core.toml"`: a file vendored into the repository, pinned by your own history.
- `extends = "policy@<commit SHA>"`: a folder that is a git checkout, such as a submodule, at that commit.
- `extends = "<git URL>@<commit SHA>"`: the submodule whose URL in `.gitmodules` is that URL, at that commit.

`extends` reads only files already in your checkout: brevio-core does not fetch a policy (`scan`, the agent hook and
the MCP server use no network and send nothing). When the checkout is missing or at another commit, the scan stops and
says so, and `git submodule update --init` fixes it. To move to a new policy, update the submodule and the
SHA in one pull request.

### Roll it out

1. **Observe.** Run `brevio-core scan --fail-on none` in CI for a week: everything is reported, nothing fails.
2. **Warn on new.** Record what is there with `brevio-core baseline`, set `level = "warn"` in `brevio-core.toml` and
   run `--fail-on error`: new findings show on the pull request and nothing blocks.
3. **Block on new.** Raise the rules you trust to `level = "error"`, one by one or with `[[overrides]]` for the paths
   that are ready. Their new findings now fail the check.
4. **Tighten.** Fix baseline entries and run `brevio-core baseline` again so they drop out, raise the last rules to
   error, then go back to the default `--fail-on new`.

### GitHub Enterprise Server

It works with the `.pyz` from the GitHub release, vendored into your repository, and with a PyPI mirror for `pip`.
This is untested: no one has run it on GitHub Enterprise Server yet.

<!-- mcp-name: io.github.Brevio-Ventures/brevio-core -->

## Use it from your agent

Three ways, all local: no model call and no API key.

**Wire the scan into your coding agents.** In the project folder:

```
brevio-core hook install
```

It finds the coding agents set up in the folder or on the machine and attaches the scan to each, so every edit is
checked against the rules. It also installs the agent skill ([skills/brevio-core/SKILL.md](skills/brevio-core/SKILL.md)),
which tells the agent when to run the commands and how to read a finding. It replaces any older skill text and a second
run changes nothing.

**Run it as an MCP server.** Add this to the `mcpServers` block of any client that supports MCP servers over stdio
(the settings file differs by client, the shape does not):

```json
{
  "mcpServers": {
    "brevio-core": {
      "command": "brevio-core",
      "args": ["mcp"]
    }
  }
}
```

Without a global install, use `"command": "uvx"` and `"args": ["brevio-core@0.6.0", "mcp"]`. Start the client in the project
folder: the server reads that folder and nothing else. The tools are `scan` (paths, or a diff base), `explain` (a rule
id, returns the rule page), `list_rules` and `learn` (compiles a fixed defect into a guard).

**Learn from a fix.** `brevio-core learn` turns the last fix into a guard. See [docs/agent-tools.md](docs/agent-tools.md)
for `learn`, `hook install`, `gain`, `add` and `mcp`.

## What ESLint, Biome and typescript-eslint don't cover

Linters check how code is written: syntax, types and style. Several mistakes agents make are valid code to them, and
are what these rules look for. From the rule pages:

## Compared with ESLint, Semgrep and CodeQL

brevio-core complements them; keep them.

- **Where they win.** They parse the code, so they see types, the syntax tree and, in Semgrep and CodeQL, data flowing
  across lines and files. They have far more rules and editor integration. brevio-core matches patterns line by line on
  the lines you add, so it misses a mistake spread over several lines and can flag a line that is fine in context.
- **What this adds.** Rules picked from the mistakes coding agents repeat, an agent hook that scans after each edit, an
  MCP server an agent can call, `learn` to turn one fix into a local guard, and a page per rule written for people and
  agents. Nothing to configure and no dependency.

## Use

```sh
brevio-core scan src/                 # files or folders
brevio-core scan --diff origin/main   # only the lines added against a base
brevio-core scan --diff --sarif out.sarif
```

The exit code is 0 when nothing is found, 1 when there are findings and 2 for a usage error.

## Fix what has one correct fix

```
brevio-core scan --fix --dry-run    # print the fixes as a unified diff, write nothing
brevio-core scan --fix              # rewrite the files in place, then scan again
brevio-core scan --fix --diff main  # fix only the lines your change adds
```

A rule gets a fixer only when it has one correct rewrite, applied by code, never by a model: a `@ts-ignore` comment
becomes `@ts-expect-error`, and a bare Python `except:` becomes `except BaseException:`, which catches the same things.
Every other finding, a hardcoded secret above all, is reported and left for you. The command prints what it fixed and
what remains, and fails while anything remains. Running it twice changes nothing the second time. The MCP server has
a `fix` tool that returns the same diff and writes only when asked.

## GitHub Action

The workflow at the top runs the scan on the lines a pull request adds. It writes the report to the job summary and
marks each finding on the changed file. With `pull-requests: write` it keeps one comment on the pull request up to date
while there are findings, and marks it resolved once they are gone; a pull request from a fork gets the summary only.
With `sarif: true` and `security-events: write` it uploads the findings to code scanning. It needs no secret and no
API key. The tag `v0.6.0` runs exactly brevio-core 0.6.0. To follow every release instead, write
`uses: Brevio-Ventures/brevio-core@v0`; to pin a commit, see [SECURITY-REVIEW.md](SECURITY-REVIEW.md). It runs on
`pull_request`, `merge_group` and `push`, and refuses any other event.

## pre-commit

```yaml
repos:
  - repo: https://github.com/Brevio-Ventures/brevio-core
    rev: v0.6.0
    hooks:
      - id: brevio-core
```

## Rules

Each rule has a page under [`docs/rules`](docs/rules/README.md): what it catches, why, and what to write instead.

## What it does not claim

This release publishes no benchmark. When a reproducible one exists, its method and data will be published with the
number.

## Questions and support

Ask questions and propose rules in [GitHub Discussions](https://github.com/Brevio-Ventures/brevio-core/discussions); report bugs
and false positives as issues, with the forms. Support is best effort, with a first response within a week
([SUPPORT.md](SUPPORT.md)).

## Project

- [Security review](SECURITY-REVIEW.md): what it runs, reads and writes, for a security team
- [Contributing](CONTRIBUTING.md) (sign-off required), with how this repository is exported and how contributions come back
- [Governance](GOVERNANCE.md): what stays open, and how maintainers are added; the [roadmap](ROADMAP.md) for the next release
- [Security](SECURITY.md)
- [Privacy](PRIVACY.md)
- [Code of conduct](CODE_OF_CONDUCT.md)
- [Trademark policy](TRADEMARK.md)

Made by [Brevio](https://brevio.pro).
