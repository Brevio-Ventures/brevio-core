"""The defect-to-guard compiler: `cli.py learn` in the harness, `brevio-core learn` in the package.

``--staged`` and ``--worktree`` compile a fix that is not committed yet (the index, or the working tree against HEAD),
and ``--dry-run`` prints the guard and how many lines of the repository it matches today, writing nothing, so an agent
can check a guard before it keeps it (ROADMAP E34, 2026-11-05).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from brevio.pipeline import core_cli
from brevio.pipeline.agent_host import config
from brevio.pipeline.gates import defect_compiler, guard_scan


def _check(paths: list[str], as_json: bool) -> int:
    """Match the learned guards against whole files; record trials and interceptions."""
    files: dict[str, list[str]] = {}
    for path in paths:
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                files[path] = f.read().splitlines()
        except OSError:
            print(f"cannot read {path}", file=sys.stderr)
    hits = guard_scan.scan_files(files)
    if as_json:
        print(json.dumps(hits, indent=2))
    for h in hits:
        print(f"guard {h['guard']}: {h['file']} holds `{h['pattern']}` ({h['title']})")
    return 1 if hits else 0


def repo_files(root: str) -> dict[str, list[str]]:
    """Every code file under ``root`` the scan would read, as ``{path relative to root: lines}``."""
    return {os.path.relpath(p, root).replace(os.sep, "/"): [text for _n, text in lines]
            for p, lines in core_cli.collect_files([root]).items()}


def _diff_spec(args: argparse.Namespace) -> tuple[str, str]:
    """The ``git diff`` argument for the fix, and how to name it in a message."""
    if args.staged:
        return "--cached", "the staged changes"
    if args.worktree:
        return "HEAD", "the uncommitted changes"
    return args.diff, f"reference '{args.diff}'"


def _print_dry_run(guard: dict, hits: int, as_json: bool) -> None:
    if as_json:
        print(json.dumps({**guard, "repo_hits": hits, "written": False}, indent=2))
        return
    print(f"guard {guard['id']}: {guard['title']}")
    print(f"  watches:  {', '.join(guard['file_patterns'])}")
    print(f"  patterns: {', '.join(guard['patterns'])}")
    print(f"  matches {hits} line(s) in this repository today")
    print("  dry run: nothing written (run again without --dry-run to keep it)")


def main(argv: list[str] | None = None, prog: str = "cli.py learn") -> int:
    """Compile a fixed defect into a guard; ``prog`` is how the user types the command."""
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Compile fixed defects into zero-token guards and progressive agent rules.",
    )
    parser.add_argument("--diff", default="HEAD~1", help="Git diff commit or range (default: HEAD~1)")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--staged", action="store_true", help="compile the staged fix (git diff --cached) instead of --diff")
    source.add_argument("--worktree", action="store_true", help="compile the uncommitted fix (the working tree against HEAD)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the guard and how many lines of the repository it matches; write nothing")
    parser.add_argument("--file", help="Specific file to inspect or extract diff from")
    parser.add_argument("--name", help="Human-readable title for the synthesized guard")
    parser.add_argument("--category", default="robustness", choices=["security", "robustness", "functional", "compliance", "finops"])
    parser.add_argument("--json", action="store_true", help="Output result as JSON")
    parser.add_argument("--check", nargs="+", metavar="FILE", help="Run the learned guards over these files instead of compiling one")

    args = parser.parse_args(argv)
    if args.check:
        return _check(args.check, as_json=args.json)

    diff_text = ""
    if args.file and os.path.isfile(args.file):
        try:
            with open(args.file, encoding="utf-8", errors="ignore") as f:
                diff_text = f.read()
        except OSError:
            diff_text = ""
    else:
        diff_text = defect_compiler.get_git_diff_text(_diff_spec(args)[0])

    if not diff_text:
        print(f"No git diff changes detected for {_diff_spec(args)[1]}.", file=sys.stderr)
        return 1

    compile_fn = defect_compiler.plan_guard if args.dry_run else defect_compiler.compile_guard_from_diff
    guard = compile_fn(diff_text=diff_text, name=args.name, category=args.category)

    if not guard:
        print("Could not extract a deterministic fault pattern from the diff.", file=sys.stderr)
        return 1

    if args.dry_run:
        _print_dry_run(guard, guard_scan.line_hits(guard, repo_files(config.WORKSPACE_DIR)), args.json)
        return 0

    if args.json:
        print(json.dumps(guard, indent=2))
        return 0

    print("═══════════════════════════════════════════════════════════════")
    print("  brevio-core learn — Zero-Token Guard Compiled (G11)")
    print("═══════════════════════════════════════════════════════════════")
    print(f"  Guard ID:     {guard['id']}")
    print(f"  Title:        {guard['title']}")
    print(f"  Category:     {guard['category']}")
    print(f"  File Globs:   {', '.join(guard['file_patterns'])}")
    print(f"  Patterns:     {', '.join(guard['patterns'])}")
    print("  Saved Guard:  .brevio/guards.json")
    print(f"  Agent Rule:   {guard['rule_file']}")
    print("  Status:       ✅ Guard compiled & active in trial mode (0 prompt tokens)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
