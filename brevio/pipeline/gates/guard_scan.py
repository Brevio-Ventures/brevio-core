"""Run the learned guards over changed files: zero tokens, no model call.

`brevio-core learn` compiles a fixed defect into `.brevio/guards.json`. This module
is the other half of the loop: it matches those guards against added lines, bumps
each guard's trial counters (so trial guards promote or retire) and writes one
ledger event per caught defect, which `gain` then prints (ROADMAP §8.2 item 8/9,
2026-11-03).
"""
from __future__ import annotations

import fnmatch
import re
from typing import Any

from brevio.pipeline.gates import defect_compiler, dopamine_ledger

_LIVE = ("trial", "active")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _glob_match(path: str, glob: str) -> bool:
    path = path.replace("\\", "/")
    return fnmatch.fnmatch(path, glob) or fnmatch.fnmatch(path, glob.replace("**/", ""))


_REGEX_META_RE = re.compile(r"\.\*|\\[sSwWdDbB()]|\(\?[!:<=]")


def _compile_pattern(raw_pat: str) -> tuple[str, re.Pattern[str] | None, str]:
    is_rx = raw_pat.startswith("re:") or bool(_REGEX_META_RE.search(raw_pat))
    expr = raw_pat[3:] if raw_pat.startswith("re:") else raw_pat
    if is_rx:
        try:
            return raw_pat, re.compile(expr), expr
        except re.error:
            pass
    lit = expr.replace("\\\\", "\\")
    return lit, None, lit


def _line_matches(compiled: tuple[str, re.Pattern[str] | None, str], ln: str) -> bool:
    _label, rx, lit = compiled
    if rx is not None:
        return bool(rx.search(ln))
    return lit in ln


def guard_hits(guard: dict[str, Any], files: dict[str, list[str]]) -> list[tuple[str, str]]:
    """(file, pattern) pairs where an added line holds one of the guard's patterns."""
    hits: list[tuple[str, str]] = []
    pats = [_compile_pattern(p) for p in guard.get("patterns", [])]
    for path, lines in files.items():
        if not any(_glob_match(path, g) for g in guard.get("file_patterns", [])):
            continue
        normed = [_norm(ln) for ln in lines]
        hits.extend((path, pat[0]) for pat in pats if any(_line_matches(pat, ln) for ln in normed))
    return hits


def line_hits(guard: dict[str, Any], files: dict[str, list[str]]) -> int:
    """How many lines of ``files`` ({path: lines}) hold one of the guard's patterns, in the files it watches."""
    pats = [_compile_pattern(p) for p in guard.get("patterns", [])]
    return sum(1 for path, lines in files.items() if any(_glob_match(path, g) for g in guard.get("file_patterns", []))
               for ln in map(_norm, lines) if any(_line_matches(pat, ln) for pat in pats))


def scan_files(
    files: dict[str, list[str]], cwd: str | None = None, record: bool = True
) -> list[dict[str, Any]]:
    """Check every live guard against `files` ({path: added lines}); return the hits.

    With `record`, each live guard counts one evaluated run (trial promotion and
    retirement) and each hit adds a ledger interception.
    """
    guards = defect_compiler.load_guards(cwd).get("guards", {})
    found: list[dict[str, Any]] = []
    for gid, guard in guards.items():
        if guard.get("status") not in _LIVE:
            continue
        if not any(_glob_match(path, g) for path in files for g in guard.get("file_patterns", [])):
            continue  # nothing this guard watches was scanned: not a trial run
        hits = guard_hits(guard, files)
        for path, pattern in hits:
            found.append({"guard": gid, "title": guard.get("title", gid), "file": path, "pattern": pattern})
        if record:
            defect_compiler.evaluate_guard_trial(gid, caught=bool(hits), cwd=cwd)
            for path, _ in hits:
                dopamine_ledger.record_interception(gid, path, cwd=cwd)
    return found
