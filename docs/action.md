# The GitHub Action

The Action installs `brevio-core` and runs `brevio-core scan --diff <base>` on the lines a change adds. It needs no
secret and makes no model call. It ships from the root of the brevio-core repository, so a workflow names it as
`Brevio-Ventures/brevio-core`.

## Start here

Save this as `.github/workflows/brevio-core.yml`:

```yaml
name: brevio-core
on:
  pull_request:
  merge_group:
permissions:
  contents: read
  pull-requests: write     # the comment on the pull request
jobs:
  brevio-core:
    name: brevio-core
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09 # v5.1.0
        with:
          fetch-depth: 0
      - uses: Brevio-Ventures/brevio-core@v0.6.0
```

`fetch-depth: 0` matters: the scan compares the change with its base commit, which must be in the checkout.
`brevio-core init` writes the same workflow for you, pinned to the release you installed.

## Pin it to a commit

A tag can move; a commit SHA cannot. To pin the Action the way it pins its own dependencies, look up the commit of
the release tag and name it, with the tag as a comment:

```sh
git ls-remote https://github.com/Brevio-Ventures/brevio-core refs/tags/v0.6.0
```

```yaml
      - uses: Brevio-Ventures/brevio-core@<the commit SHA printed above> # v0.6.0
```

The Action installs exactly brevio-core 0.6.0 from PyPI, because `package-version` defaults to the release of the
Action. Dependabot's `github-actions` updates move a pinned SHA and its comment together.

`v0` is a moving major tag until 1.0. It is the easiest to write and the least predictable; use an exact tag or a SHA
in a repository that needs every run to be repeatable.

## Events

The Action runs on `pull_request`, `merge_group` and `push`, and stops with an error on any other event. It never
supports the privileged events that hand a write token to a run on code from a fork: the scan reads the code under
review, and that code must not run next to a write token ([SECURITY-REVIEW.md](https://github.com/Brevio-Ventures/brevio-core/blob/main/SECURITY-REVIEW.md)).

| Event | The base the change is compared with |
| --- | --- |
| `pull_request` | the pull request's base branch (`origin/<base branch>`) |
| `merge_group` | the merge group's base commit |
| `push` | the commit before the push; the default branch for the first push of a branch |

The `base` input overrides all three.

### A merge queue

With a merge queue, a required check must also run on `merge_group`, or the queue waits for it for ever. Keep
`merge_group:` in `on:`, as in the workflow above, and give the job a fixed `name:`, so the check the queue waits
for has the same name as the one the pull request reported. The scan then reads what the queue is about to merge.

### Pushes to the default branch

```yaml
on:
  push:
    branches: [main]
```

A push run writes the summary and the annotations; it posts no comment, since there is no pull request.

## Permissions

```yaml
permissions:
  contents: read            # check out the code
  pull-requests: write      # the comment (optional: without it the Action writes the summary only)
  security-events: write    # the SARIF upload (optional: only with sarif: true)
```

A private repository may also need `actions: read` for the SARIF upload. On a pull request from a fork the token is
read-only: the Action says so in the summary and does not fail.

## Inputs

| Input | Default | What it does |
| --- | --- | --- |
| `base` | empty | the git ref or SHA the diff is taken against; empty picks it from the event, as above |
| `fail-on` | `new` | which findings fail the check: `new` (not in `.brevio/baseline.json`), `all`, `error` (new error-level findings only, with levels from `brevio-core.toml`) or `none` (report only) |
| `comment` | `on-findings` | the pull request comment: `on-findings` (post or update it while there are findings, mark it resolved once they are gone), `always` or `never` |
| `footer` | `auto` | end the comment with "checked by brevio-core": `auto` (public repositories only), `true` or `false` |
| `sarif` | `false` | upload the findings to GitHub code scanning (needs `security-events: write`) |
| `source` | empty | a pip requirement or path to install instead of the PyPI release |
| `package-version` | this release | the brevio-core version to install; `latest` takes the newest |

## Outputs

| Output | What it holds |
| --- | --- |
| `status` | `pass` or `fail` |
| `findings` | how many findings the scan reported, silenced ones left out |

Give the step an `id` to read them in a later step as `steps.<id>.outputs.status`.

## What a run does

1. Checks the event, sets up Python and installs brevio-core.
2. Picks the base and runs the scan once, with `--format markdown` and links to the rule pages.
3. Writes the report to the job summary and one warning annotation per finding, up to the number GitHub shows per
   step; the summary lists every finding.
4. With `comment: on-findings`, posts one comment on the pull request while there are findings and updates the same
   comment on the next run. A later clean run edits it to "Resolved"; a clean run never creates one.
5. With `sarif: true`, uploads the findings to code scanning. A repository without code scanning does not fail.
6. Exits with the scan's exit code, which `fail-on` decides.

## Examples

### A trial week: report, never fail

```yaml
      - uses: Brevio-Ventures/brevio-core@v0.6.0
        with:
          fail-on: none
```

### Adopt it on a repository with findings

Record what is there once, commit `.brevio/baseline.json`, and the check fails only on new findings:

```sh
brevio-core baseline
git add .brevio/baseline.json
```

### Code scanning, and no comment

```yaml
permissions:
  contents: read
  security-events: write
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
          comment: never
```

### Block only on error-level rules

With a `brevio-core.toml` that sets some rules to `warn` (see the README's team rollout):

```yaml
      - uses: Brevio-Ventures/brevio-core@v0.6.0
        with:
          fail-on: error
```

## Without the Action

The Action is a thin wrapper. Any CI can run the same check:

```sh
pip install brevio-core==0.6.0
brevio-core scan --diff origin/main --sarif brevio-core.sarif
```
