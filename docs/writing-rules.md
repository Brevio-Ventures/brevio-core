# Writing a rule

A rule is a fixed pattern on the lines a change adds. It runs with no model, no dependency and no setup, so the same
line gives the same finding on every machine. This page shows where a rule lives and what a pull request for one
needs. [CONTRIBUTING.md](https://github.com/Brevio-Ventures/brevio-core/blob/main/CONTRIBUTING.md) has the acceptance rubric
and the test template; open a "New rule" issue before you write code.

## What a rule sees

One added line at a time, with the file's path. It does not see the lines around it, the rest of the file or other
files. This is on purpose: a line-level rule is fast, explains itself in one sentence, and never flags a line that was
already there. A mistake that needs the whole file or a type checker to see belongs in a linter or a type checker.

## The parts of a rule

All of them live under `brevio/pipeline/code_rules/`.

| Part | Where | What you write |
| --- | --- | --- |
| The ID and its one line | `PR_RULES_122` in `__init__.py` | `"R9.2": "No silenced type errors: no @ts-ignore; every @ts-expect-error states its reason"`. The text before the colon is the title. |
| The check | `_check_line_patterns` in `__init__.py` | a compiled regular expression, tested only on files of the right kind (by extension), that appends `path:line: [RX.Y] message` |
| Why, and two examples | `DETAILS` in `details.py` | why the mistake matters, in one or two short sentences; a bad example the check flags; a good one it does not; the language of the examples; any exemption the check makes, in plain words |
| Which scanner runs it | `SCANS` in `details.py` | `"RX.Y": ("code", "src/example.ts")`: the scanner of `brevio-core scan` and a path the examples are checked at |
| Its status | `RULE_STATUS` in `__init__.py` | `"RX.Y": "preview"` for a new rule: it reports but never fails a scan, for one minor release |
| A fix, if there is exactly one | `FIXERS` in `fixers.py` | only when one rewrite is always right, such as `@ts-ignore` to `@ts-expect-error`; most rules have none |

## Steps

1. Pick the next free ID in the group the mistake belongs to. An ID is never reused or renumbered, and a retired rule
   keeps its ID as `deprecated` ([RULES-STABILITY.md](https://github.com/Brevio-Ventures/brevio-core/blob/main/RULES-STABILITY.md)).
2. Add the one line, the check, the details, the `SCANS` entry and the `preview` status.
3. Regenerate the rule pages:

   ```sh
   python -m brevio.pipeline.code_rules.docs --out docs/rules
   ```

   The page title, the short answer, the related rules and the search data all come from what you wrote; never edit a
   page by hand.
4. Add a test class from the template in CONTRIBUTING.md, with the bad and good examples and the near misses from your
   false-positive check.
5. Run the tests:

   ```sh
   python -m unittest discover -s tests/pipeline/core_export -t .
   ```

   The rule-page test checks that the bad example is flagged and the good one is not, and that every page matches
   the definitions.

## Writing the pattern

- Anchor it to the mistake, not to the code around it. `@ts-ignore\b` is a rule; "a line with `ignore` in it" is noise.
- Test the extension first, so a CSS rule never reads Python.
- Leave out what the rule cannot judge from one line, and say so in the `exempt` text, so the page tells a reader
  what is not flagged.
- A message says what is wrong and what to do instead, in one line: the agent hook shows it to the agent as it is.

## What a rule must not do

- Open a file, start a process or open a connection. The security tests fail on any of these.
- Read a configuration of its own. Which rules run where, and at which level, is the job of `brevio-core.toml`.
- Flag a line the change did not add.
