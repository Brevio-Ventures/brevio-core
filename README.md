# brevio-core

A zero-token pull-request gate that catches the mistakes coding agents keep repeating.

It reads the lines a change adds and checks them against 122 deterministic code rules. It makes no model call, needs
no API key and sends nothing anywhere. Every finding names a rule, and every rule has a page that says what it
catches, why, and what to write instead.

Version 0.1.0. Licensed under Apache-2.0.

## Install

```
pip install brevio-core
```

Python 3.10 or newer. There are no runtime dependencies.

## Use

```
brevio-core scan src/                 # files or folders
brevio-core scan --diff origin/main   # only the lines added against a base
brevio-core scan --diff --sarif out.sarif
```

The exit code is 0 when nothing is found, 1 when there are findings and 2 for a usage error.

## GitHub Action

```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 0
- uses: Brevio-Ventures/brevio-core@v0
```

The Action installs `brevio-core`, scans the pull request diff and fails the check on a finding. It needs no secrets.

## pre-commit

```yaml
repos:
  - repo: https://github.com/Brevio-Ventures/brevio-core
    rev: v0.1.0
    hooks:
      - id: brevio-core
```

## Rules

Each rule has a page under [`docs/rules`](docs/rules/README.md). There is no ignore comment: a comment that silences a
rule is the easiest way for an automated author to pass its own gate, so the fix goes in the code.

## What it does not claim

This release publishes no benchmark. When a reproducible one exists, its method and data will be published with the
number.

## Project

- [Contributing](CONTRIBUTING.md) (sign-off required)
- [Security](SECURITY.md)
- [Code of conduct](CODE_OF_CONDUCT.md)
- [Trademark policy](TRADEMARK.md)

Made by [Brevio](https://brevio.pro).
