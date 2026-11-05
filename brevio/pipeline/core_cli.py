"""The ``brevio-core`` command line: ``scan`` runs the 122 code rules on files or on a diff (ROADMAP E16, 2026-11-04).

Standard library only, so it exports with the rule engines (the core exporter) and runs with no model call and
no network. It is what the GitHub Action, the pre-commit hook and the agent hooks call. Exit code 0 means no finding,
1 means findings, 2 means a usage error. The 0.2 export set adds ``learn``, ``hook``, ``gain`` and ``add`` (ROADMAP
E16, 0.2 set); they show up only when the build ships them (``agent_tools``).
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterable

from brevio.pipeline import leak_scan
from brevio.pipeline.code_rules import PR_RULES_122, scan_lines
from brevio.pipeline.rule_host import GIT

CODE_SUFFIXES = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".css", ".html", ".sql", ".vue", ".svelte")
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next"}
MAX_BYTES = 1_000_000
_FINDING = re.compile(r"^(?P<path>.+?):(?P<line>\d+): (?:\[(?P<rule>[^\]]+)\] )?(?P<msg>.*)$")
_HUNK = re.compile(r"^@@ -\S+ \+(\d+)")

Numbered = dict[str, list[tuple[int, str]]]


def _read(path: str) -> list[tuple[int, str]]:
    try:
        if os.path.getsize(path) > MAX_BYTES:
            return []
        with open(path, encoding="utf-8", errors="ignore") as fh:
            return list(enumerate(fh.read().splitlines(), 1))
    except OSError:
        return []


def _rel(path: str) -> str:
    return os.path.relpath(path).replace(os.sep, "/")


def collect_files(paths: Iterable[str]) -> Numbered:
    """Every line of each named file, and of each code file under a named folder."""
    out: Numbered = {}
    for p in paths:
        if os.path.isdir(p):
            for dirpath, dirs, names in os.walk(p):
                dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
                for n in sorted(names):
                    if n.endswith(CODE_SUFFIXES):
                        out[_rel(os.path.join(dirpath, n))] = _read(os.path.join(dirpath, n))
        else:
            out[_rel(p)] = _read(p)
    return out


def _git(*args: str) -> str:
    try:
        r = subprocess.run([*GIT, *args], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout if r.returncode == 0 else ""


def _base(want: str) -> str:
    for ref in ([want] if want else ["origin/main", "main", "HEAD"]):
        if _git("rev-parse", "--verify", "-q", ref).strip():
            return ref
    return "HEAD"


def diff_lines(base: str) -> Numbered:
    """The lines the working tree adds against ``base`` (with their real line numbers), plus new untracked files."""
    out: Numbered = {}
    path, lno = "", 0
    for ln in _git("diff", "-U0", "--no-color", "--diff-filter=ACMR", _base(base), "--").splitlines():
        if ln.startswith("+++ "):
            path = ln[6:] if ln.startswith("+++ b/") else ""
        elif ln.startswith("@@"):
            m = _HUNK.match(ln)
            lno = int(m.group(1)) if m else 0
        elif path and ln.startswith("+"):
            out.setdefault(path, []).append((lno, ln[1:]))
            lno += 1
    for new in _git("ls-files", "--others", "--exclude-standard").splitlines():
        if new.endswith(CODE_SUFFIXES):
            out[new] = _read(new)
    return out


def scan(files: Numbered) -> list[str]:
    """Findings (``path:line: [rule] message``) for the given numbered lines."""
    found: list[str] = []
    for rel, numbered in sorted(files.items()):
        found += scan_lines(rel, numbered)
    return found


def sarif(findings: list[str]) -> dict:
    """The findings as a SARIF 2.1.0 log, for GitHub code scanning."""
    results = []
    for f in findings:
        m = _FINDING.match(f)
        if not m:
            continue
        results.append({
            "ruleId": m["rule"] or "brevio-core", "level": "error", "message": {"text": m["msg"]},
            "locations": [{"physicalLocation": {"artifactLocation": {"uri": m["path"]},
                                                "region": {"startLine": int(m["line"])}}}]})
    rules = [{"id": rid, "shortDescription": {"text": text}} for rid, text in sorted(PR_RULES_122.items())]
    return {"version": "2.1.0",
            "runs": [{"tool": {"driver": {"name": "brevio-core", "rules": rules}}, "results": results}]}


def write_atomic(path: str, text: str) -> None:
    """Write ``text`` to ``path`` through a temporary file, so a crash never leaves half a report."""
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


AGENT_TOOLS = "agent_cmds"      # the module of the 0.2 set that holds the commands; named here so a build without it is detected


def agent_tools() -> tuple[dict[str, Callable[[list[str]], int]], dict[str, str]]:
    """``(commands, help)`` of the 0.2 agent tools, or two empty tables in a build that does not ship them."""
    top = __name__.split(".")[0]
    try:
        mod = importlib.import_module(f"{top}.operator.{AGENT_TOOLS}")   # a name built at run time: absent in the 0.1 set
    except ModuleNotFoundError as err:
        if not (err.name or "").startswith(f"{top}.operator"):
            raise
        return {}, {}
    return mod.COMMANDS, mod.HELP


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="brevio-core", description="Zero-token code rules for coding-agent mistakes.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    tools, tool_help = agent_tools()
    for name in tools:      # listed for ``--help``; the command itself reads the rest of the line
        sub.add_parser(name, help=tool_help[name], add_help=False)
    sc = sub.add_parser("scan", help="scan files, folders or a diff against the 122 code rules")
    sc.add_argument("paths", nargs="*", help="files or folders to scan (default: the current folder)")
    sc.add_argument("--file", action="append", default=[], metavar="PATH", help="a file to scan (repeatable)")
    sc.add_argument("--diff", nargs="?", const="", default=None, metavar="BASE",
                    help="scan only the lines added against BASE (default origin/main)")
    sc.add_argument("--sarif", metavar="FILE", help="also write the findings to FILE as SARIF")
    lk = sub.add_parser("leaks", help="check a folder for stray URLs, emails and paths that should not be public")
    lk.add_argument("root", nargs="?", default=".", help="the folder to check (default: the current folder)")
    line = sys.argv[1:] if argv is None else argv
    if line and line[0] in tools:
        return tools[line[0]](line[1:])
    args = ap.parse_args(line)
    if args.cmd == "leaks":
        problems = leak_scan.scan_tree(args.root)
        print("\n".join(problems))
        return 1 if problems else 0
    named = [*args.paths, *args.file]
    missing = [p for p in named if not os.path.exists(p)]
    if missing:
        print(f"brevio-core: no such file or folder: {', '.join(missing)}", file=sys.stderr)
        return 2
    if args.diff is not None:
        lines = diff_lines(args.diff)
        if named:
            wanted = collect_files(named)
            lines = {k: v for k, v in lines.items() if k in wanted or any(k.startswith(w.rstrip("/") + "/") for w in named)}
    else:
        lines = collect_files(named or ["."])
    findings = scan(lines)
    for f in findings:
        print(f)
    if args.sarif:
        write_atomic(args.sarif, json.dumps(sarif(findings), indent=2))
    print(f"brevio-core: {len(findings)} finding(s) in {len(lines)} file(s)", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
