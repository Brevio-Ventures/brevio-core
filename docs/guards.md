# The guard format

`brevio-core learn` turns a fixed defect into a guard: the lines the fix removed become patterns that must not come
back. Guards live in `.brevio/guards.json` in your repository, next to an agent rule for each one in
`.agents/rules/<guard id>.md`. Commit both, so the whole team and every agent get them. `brevio-core add <pack>`
writes guards in the same format.

## `.brevio/guards.json`

```json
{
  "version": 1,
  "guards": {
    "guard-fix-await-sleep-in-handler-ts": {
      "id": "guard-fix-await-sleep-in-handler-ts",
      "title": "Fix await sleep in handler.ts",
      "category": "robustness",
      "source_file": "src/api/handler.ts",
      "file_patterns": ["src/api/**/*.ts", "**/*.ts"],
      "patterns": ["await sleep(SECONDS * MS);"],
      "status": "trial",
      "runs_evaluated": 0,
      "false_fails": 0,
      "intercepted": 0,
      "rule_file": ".agents/rules/guard-fix-await-sleep-in-handler-ts.md",
      "created_at": "2026-11-05T09:30:00Z",
      "updated_at": "2026-11-05T09:30:00Z"
    }
  }
}
```

| Field | What it holds |
| --- | --- |
| `id` | `guard-` and a slug of the title; the key of the entry |
| `title` | `--name`, or "Fix <first removed line> in <file name>" |
| `category` | `--category`: `security`, `robustness`, `functional`, `compliance` or `finops` |
| `source_file` | the file the fix changed |
| `file_patterns` | the globs of the files the guard watches: the fixed file's folder and its extension |
| `patterns` | up to a few removed lines, whitespace folded. A guard hits when an added line contains one of them as text (not as a regular expression) |
| `status` | `trial`, `active` or `retired` |
| `runs_evaluated`, `false_fails`, `intercepted` | the trial counters: runs that saw a watched file, hits a person marked wrong, and hits |
| `rule_file` | the agent rule written beside it |
| `created_at`, `updated_at` | UTC times |

## The life of a guard

- A new guard is on **trial**: it reports, and every run that sees a file it watches counts.
- After a run of clean trial runs with no false failure it becomes **active**.
- A guard that fails wrongly too often is **retired** and stops reporting. Retired guards stay in the file, so the
  history is kept.

Both `trial` and `active` guards are checked by `brevio-core learn --check <files>` and the agent tools.
`brevio-core learn --dry-run` prints a guard and how many lines of the repository it matches today before anything is
written, so a guard that is too broad can be renamed or dropped first.

## The agent rule

`.agents/rules/<guard id>.md` tells a coding agent what not to write back. Its front matter names the files it applies
to, so an agent that reads rules by path loads it only for those files:

```markdown
---
description: "Learned Guard: Fix await sleep in handler.ts"
paths: ["src/api/**/*.ts", "**/*.ts"]
---
# Invariant: Fix await sleep in handler.ts (robustness)
```

## Editing guards by hand

The file is plain JSON; edit it like any other file in review. Narrow `file_patterns` or remove a pattern that is too
general, or set `status` to `retired` to switch a guard off while keeping its history. Delete the entry and its rule
file to remove a guard altogether.
