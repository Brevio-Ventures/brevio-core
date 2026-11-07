# Changelog

## 0.7.0 (unreleased)

### Rules and fixers

- `brevio-core scan` now checks 13 scanned rules of the 123 in the catalogue (110 documented): R5.5 flags `subprocess`
  calls with `shell=True` and `os.system` calls with interpolated strings in Python; R10.1 flags single-line `requests`
  calls without `timeout=` in Python; R16.2 flags `"*"` and `"latest"` dependency ranges in `package.json`; and R18.2
  flags single-line `target="_blank"` anchor tags without `rel="noopener noreferrer"`.
- R2.8 also flags raw SQL string interpolation in `.execute(f"SELECT ...")` and `.$queryRawUnsafe` template literals,
  as well as hidden directional and Unicode tag control characters.
- R13.1 also flags secret-named environment variables exposed to client bundles (`NEXT_PUBLIC_`, `VITE_`, `REACT_APP_`).
- `brevio-core scan --fix` and the MCP `fix` tool now rewrite `target="_blank"` anchor tags that have no `rel=`
  attribute to add `rel="noopener noreferrer"` (R18.2).
- Every rule page in `docs/rules` now links to the interactive rule playground on `brevio.pro`.

## 0.6.0 (unreleased)

### Adopt it on a repository that has findings

- `brevio-core baseline` records the findings a repository has today in `.brevio/baseline.json`, so a scan reports
  only new ones. An entry names the file, the rule and a hash of the line, so moving a line does not make it new.
- `scan --fail-on` chooses what fails: `new` (the default), `all`, `none` for a trial, or `error` for error-level
  findings only.
- `brevio-core init` sets a repository up in one step: the pull-request workflow, a block of agent rules in
  `AGENTS.md` and a baseline, with `--with precommit,hook,mcp` for more. It shows a diff and asks first, never rewrites
  a file you have, and `init --undo` takes back what it wrote.

### Only a person can silence it

- An ignore comment with a reason (`brevio-core: ignore R9.2 -- reason`) silences one finding in a scan a person
  runs. Without a reason it does not count.
- The agent hook and the MCP server never honour an ignore comment, and a diff scan reports every ignore comment,
  baseline entry and config change it adds as a new suppression until a reviewer allows it.
- SARIF keeps each silenced finding as a suppression with its reason.

### Configure it for a team

- `brevio-core.toml` at the root and in any folder chooses the rules, leaves paths out, and sets `warn` or `error` per
  rule and per path. `extends` reads an organisation policy from a file in the repository or a checkout pinned to a
  commit; it never fetches one.
- `brevio-core config` shows what applies to a file or folder.
- The README has a rollout guide: observe, warn on new findings, block them, then tighten.

### Stable rule IDs

- Every rule has a status: `stable`, `preview` (reports, never fails) or `deprecated` (reports nothing, keeps its ID).
- A rule ID is never removed, reused or renumbered; the release refuses one that is.
- The release notes list the rules added, changed and retired.

### Rules

- R13.1 (a secret in code) flags a known credential format, a JWT, or a random-looking value bound to a secret, token,
  password or API key name. It no longer flags placeholders or keys that are public by design, such as Algolia search
  keys and Stripe `pk_` keys.
- Every scan skips vendored folders, minified files and bundles. Exclude more with `exclude` in `brevio-core.toml`.
- No rule reads a TypeScript declaration file (`.d.ts`, `.d.mts`, `.d.cts`): it holds types, no code that runs.
- The `eval`, `new Function` and `dangerouslySetInnerHTML` findings have their own rule, R2.8. Earlier builds reported
  them as R2.5, the SSRF and timeout guard.
- R6.3 (a sleep in a test) is `preview`: it reports and never fails a scan.

### In the agent's loop

- `brevio-core hook run` is the hook a coding client calls after an edit and before it stops. It reads the client's
  event, scans the changed lines and hands the findings back in that client's own format, so the agent fixes them
  without a human turn. It gives up quietly on an error or past its time budget.
- `hook install` writes the hooks for Claude Code and Cursor, and the agent skill for the clients that load skills.
- `scan --format agent` prints one short line per finding with a fix hint, as the hook and the MCP server do.
- `learn --staged`, `learn --worktree` and `learn --dry-run` compile a guard from a fix that is not committed yet,
  and show what it would match before anything is written.

### On the pull request

- `scan --format markdown` prints the findings as an escaped table, with links to the rule pages.
- The Action writes the job summary and annotations, keeps one pull request comment up to date and marks it resolved
  once the findings are gone, and can upload SARIF to code scanning. It runs on pull requests, merge queues and
  pushes only, and pins every action it uses to a commit.

### Scoring a site for answer engines

- `brevio-core aeo` scores a folder of built HTML pages, with its `robots.txt` and `llms.txt`, against the AEO
  rubric, as text, Markdown or JSON, and fails below `--min`. It reads local files only and refuses a URL with a hint
  to save the page first.

### Docs

- A command reference generated from the code, a guide to the Action, a guide to writing a rule, the guard and SARIF
  formats, a FAQ and this changelog.
- One page per coding agent: Claude Code, Cursor, Codex, Hermes and OpenClaw.
- Each rule page leads with a short answer, has a search-friendly title, links related rules and carries structured
  data; the docs site has a sitemap.
- An agent-safe starter template: the workflow, the `AGENTS.md` block and a README, ready to become a template
  repository.

### Releases and contributions

- Each release has a `MANIFEST.json` that maps every file to its source, and a `.pyz` single-file build with its SBOM
  and checksum in the release notes.
- Releases are published by a workflow with approvals, from a signed tag.
- The README is tested: its marked examples run in CI.
- The security review page states what the package reads and runs, and tests check each claim.
- Governance, support, a rule-acceptance rubric, a rule-test template and issue forms for bugs, false positives and new
  rules.
- A trademark brand-use section and a privacy notice.
