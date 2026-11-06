# Governance

brevio-core is maintained by Brevio, which also sells a paid product built on it. This page says what stays open, who
decides, and how that changes.

## What stays open

These are commitments, not plans:

- **The rules stay Apache-2.0.** Every rule, its page, the scanner, the GitHub Action, the agent hook and the MCP server
  in this repository are under the Apache-2.0 licence, and stay under it.
- **No relicensing.** Code released here is never moved to another licence. Contributions come in under the Developer
  Certificate of Origin, not a CLA, so nobody is asked to hand over rights that would allow it.
- **Nothing shipped moves to paid.** A feature in a release of brevio-core stays in every later release, under
  Apache-2.0. The paid product adds services around it, such as syncing learned guards across repositories and
  teammates; it never takes a feature away from this repository.

## Who decides

The maintainers review and merge pull requests, triage issues and answer Discussions. Releases are cut by the owner
from the harness this repository is exported from ([CONTRIBUTING.md](CONTRIBUTING.md), "How this repo works").
Decisions are made in the open: in the pull request, the issue or the Discussion they concern.

Maintainers: rmb (owner).

## How a maintainer is added

1. Anyone may propose a contributor, or themselves, in a Discussion. A candidate has had pull requests merged here and
   has helped others through reviews, triage or answers over several months.
2. The current maintainers agree in that Discussion. With no objection after two weeks, the proposal stands.
3. A pull request adds the new maintainer to the list above, and the owner grants the access.

A maintainer who has been inactive for six months, or who asks to step down, is moved to an emeritus line in this file.
A maintainer who breaks the [code of conduct](CODE_OF_CONDUCT.md) can be removed by the owner, who says why.

## Roadmap and capacity

[ROADMAP.md](ROADMAP.md) lists what is planned for the next release only; later ideas live in Discussions. Support is
best effort ([SUPPORT.md](SUPPORT.md)).
