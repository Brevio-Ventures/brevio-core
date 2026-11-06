# Roadmap

What is planned for the next release, in plain words. Only the next release is listed; later ideas live in
Discussions. The list changes as work lands, and nothing on it takes a shipped feature away ([GOVERNANCE.md](GOVERNANCE.md)).

## Next release

- **A config file.** `brevio-core.toml` at the root and in any folder: choose rules, leave paths out, set warn or error
  per rule and per path, and extend an organisation policy pinned to a commit. A guide for rolling it out across a
  team: observe first, then warn on new findings, then block them.
- **Stable rule IDs.** A rule ID is never reused or renumbered, and a retired rule keeps its ID. A new rule starts as a
  preview: it reports but does not block, for one minor release.
- **A precision table.** The scanned rules run over popular open-source TypeScript and React repositories at pinned
  commits, with the hits per rule, a hand-checked sample and the commands to repeat it. The weakest rules are fixed or
  retired first.
- **Fuller docs.** A command reference, a guide to the Action, a guide to writing a rule, a FAQ and a changelog.
- **One page per coding agent** on wiring the hook into it, and a template repository that starts agent-safe.
- **A hint after a fix.** When an agent commits a fix, the hook suggests `learn`. It never runs it.
- **Contributions back without hand work.** An importer brings merged pull requests back into the harness, checks the
  sign-off and the licence, and a generated contributors list credits everyone.
- **`up`, opt in.** Sync learned guards and suppression approvals across repositories and teammates, the paid service.
  It asks first, and shows the exact files before anything leaves your machine ([PRIVACY.md](PRIVACY.md)).
- **A public benchmark** of the mistakes coding agents repeat, published with its method and data once it has passed a
  legal review.

Missing something? Ask in Discussions.
