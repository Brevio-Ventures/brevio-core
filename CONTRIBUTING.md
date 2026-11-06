# Contributing

Thank you for helping. Small, focused changes are easiest to review. Questions and rule ideas go to GitHub
Discussions first; see [SUPPORT.md](SUPPORT.md).

## How this repo works

- **This repository is an export.** The code is developed in a private harness, and each release is generated from it
  by an exporter. A release replaces every file listed in `MANIFEST.json`, which names the harness file each one comes
  from; `RELEASE.md` names the harness commit.
- **Merged contributions are brought back within 14 days** of the merge, so the next release keeps them. An importer
  maps each merged commit to its harness file through `MANIFEST.json`, checks its `Signed-off-by` line and the licence
  of what it adds, and runs the release's leak checks on the result. Each commit becomes one harness commit that names
  the pull request and your GitHub handle, and its SHA goes into `IMPORTED`, from which
  [CONTRIBUTORS.md](CONTRIBUTORS.md) is made. A release is refused while `main` holds a merged commit that `IMPORTED`
  does not list, so nothing merged here is lost. A change to the release machinery (`.github/`, `scripts/`,
  `action.yml`, the packaging, the leak scan) needs a second maintainer's review before it is brought back.
- **Change only the files the release exports.** The `manifest` check fails a pull request that changes a file outside
  `MANIFEST.json` (issue and discussion forms and `docs/img/` excepted), or one of the files the release writes itself
  (`MANIFEST.json`, `VERSION`, `RELEASE.md`, `IMPORTED`, `CONTRIBUTORS.md`). For a new file, say where it belongs and a
  maintainer adds it.
- **Your contribution is also used in the paid product** built from the same harness, as the Apache-2.0 licence allows.
  Here it stays under Apache-2.0 ([GOVERNANCE.md](GOVERNANCE.md)).
- **You keep authorship.** Your commits, with your name and your `Signed-off-by` line, stay in this repository's public
  history. [PRIVACY.md](PRIVACY.md) says what that keeps about you.

## Sign your commits (DCO)

This project uses the Developer Certificate of Origin, not a CLA. Add a `Signed-off-by` line to every commit with
`git commit -s`. It says you wrote the change, or have the right to submit it under Apache-2.0.

```
Developer Certificate of Origin
Version 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I have the right to submit it under the open source
    license indicated in the file; or

(b) The contribution is based upon previous work that, to the best of my knowledge, is covered under an appropriate
    open source license and I have the right under that license to submit that work with modifications, whether
    created in whole or in part by me, under the same license (unless I am permitted to submit under a different
    license), as indicated in the file; or

(c) The contribution was provided directly to me by some other person who certified (a), (b) or (c) and I have not
    modified it.

(d) I understand and agree that this project and the contribution are public and that a record of the contribution
    (including all personal information I submit with it, including my sign-off) is maintained indefinitely and may
    be redistributed consistent with this project or the license(s) involved.
```

## Making a change

1. Fork the repository and make a branch.
2. Run the tests: `python -m unittest discover -s tests/pipeline/core_export -t .`
3. A new or changed rule needs a test, and its page under `docs/rules` must match the rule.
4. Open a pull request and fill in the template.

Never put secrets, personal data or private names in a commit. The leak test fails on stray URLs, email addresses and
paths.

## When a contribution is taken down

A merged contribution that turns out not to conform (no valid `Signed-off-by`, code under a licence that is not
compatible with Apache-2.0, code the author had no right to submit, or a secret or personal data) is reverted, not
kept:

1. A maintainer opens a pull request with `git revert -s` of the merged commits, saying which rule it broke. The
   reason names no personal data.
2. When the commits were already brought back, the maintainer reverts the harness commit as well, marks their lines in
   `IMPORTED` with `taken-down`, and the revert here is imported like any other commit. When they were not, the
   original commits and the revert are listed in `IMPORTED` together, each marked `taken-down`, and the harness is not
   changed.
3. The next release no longer carries the change, and `CONTRIBUTORS.md` no longer credits it.

The public history keeps the reverted commits. Removing them from history, for a leaked secret or personal data, is a
rewrite only the owner decides; write to legal@brevio.pro.

## Proposing a rule

Open a "New rule" issue first. A rule pull request is accepted when every point holds, so it can be judged without the
owner:

1. **Agents repeat it.** Link at least two public examples (a commit, a pull request or an issue) of the mistake in
   code a coding agent wrote.
2. **It is deterministic.** A fixed pattern on the lines a change adds: no model, no dependency, and no code that
   opens a connection.
3. **It has a bad and a good example.** The rule's page under `docs/rules` shows a bad line the rule flags and a good
   line it does not, and says why the bad one is wrong.
4. **It passes a false-positive check.** Run it over at least three popular public repositories at a pinned commit and
   list every hit with your verdict: a real mistake, or correct code. A hit on correct code is a false positive. If more
   than one hit in ten is one, narrow the pattern first.
5. **It has a test** that follows the template below, with the near misses from your check.
6. **It takes a new rule ID.** An ID is never reused or renumbered.

A finding on correct code from an existing rule is a "False positive" issue, with the line and why it is correct.

### Rule test template

Add the class to `tests/pipeline/core_export/test_core_rules.py`, with `RX.Y` replaced by the rule's ID:

```python
class TestRuleRXY(unittest.TestCase):
    """RX.Y: the rule's title. The lines come from docs/rules/RX.Y.md and from the false-positive check."""

    def flagged(self, *lines):
        return [f for f in scan_added_lines_for_rules({"src/example.ts": list(lines)}) if "[RX.Y]" in f]

    def test_the_bad_example_is_flagged(self):
        self.assertTrue(self.flagged("the bad line from the rule page"))

    def test_the_good_example_is_not_flagged(self):
        self.assertEqual(self.flagged("the good line from the rule page"), [])

    def test_a_near_miss_from_the_false_positive_check_is_not_flagged(self):
        self.assertEqual(self.flagged("a correct line that looks like the mistake"), [])
```
