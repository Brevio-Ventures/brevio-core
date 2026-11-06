"""Mechanical fixes for the code rules that have exactly one correct rewrite (ROADMAP E16, the 0.3 set, 2026-11-05).

Each fixer is declared for one rule id, the file suffixes it applies to, a pattern and its replacement. A fixer runs
on a line only when its rule fires on that line, and its output must no longer trigger the rule (tested). Rules
without a fixer are reported unchanged: a secret (R13.1), an empty catch, ``as any``, ``eval`` or a missing ``alt``
need a person to decide, so no fix is invented for them. Standard library only; no model call, no network.
"""
from __future__ import annotations

import os
import re
from typing import NamedTuple

from brevio.pipeline.code_rules import scan_lines


class Fixer(NamedTuple):
    suffixes: tuple[str, ...]
    pattern: re.Pattern[str]
    replacement: str
    summary: str


FIXERS: dict[str, Fixer] = {
    # Only the comment directive is rewritten; ``@ts-ignore`` inside a string stays a finding for a person to read.
    "R9.2": Fixer((".ts", ".tsx", ".js", ".jsx"), re.compile(r"(//|/\*)(\s*)@ts-ignore\b"), r"\1\2@ts-expect-error",
                  "`@ts-ignore` comment becomes `@ts-expect-error`"),
    # ``except BaseException:`` catches exactly what a bare ``except:`` catches, so behaviour does not change.
    "R5.4": Fixer((".py",), re.compile(r"^(\s*)except\s*:"), r"\1except BaseException:",
                  "bare `except:` becomes `except BaseException:` (same behaviour, now explicit)"),
}
_RULE = re.compile(r"\[([^\]]+)\]")


def rules_on(rel_path: str, line: str) -> set[str]:
    """The rule ids that fire on one line of ``rel_path``."""
    prefix = f"{rel_path}:1: "
    return {m.group(1) for f in scan_lines(rel_path, [(1, line)]) if (m := _RULE.match(f, len(prefix)))}


def fix_line(rel_path: str, line: str) -> tuple[str, list[str]]:
    """``line`` with every applicable fixer applied, and the rule ids it fixed (sorted)."""
    ext = os.path.splitext(rel_path)[1].lower()
    fired, fixed = rules_on(rel_path, line), []
    for rule, fixer in sorted(FIXERS.items()):
        if rule in fired and ext in fixer.suffixes:
            new = fixer.pattern.sub(fixer.replacement, line)
            if new != line:
                line = new
                fixed.append(rule)
    return line, fixed
