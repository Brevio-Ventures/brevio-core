"""Zero-Token Defect-to-Guard Compiler (Master Growth Plan G11 / S7).

Compiles bug fixes and git diffs into:
1. Zero-Token Guards saved in `.brevio/guards.json`
2. Progressive-Disclosure Agent Rules in `.agents/rules/<id>.md` with `paths:` YAML frontmatter
3. Trial counter and auto-retirement tracking
"""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
from typing import Any

from brevio.pipeline.agent_host import config, gitsafe, jsonstore

GUARDS_DIR = ".brevio"
GUARDS_FILE = "guards.json"
RULES_DIR = os.path.join(".agents", "rules")


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(text).strip().lower()).strip("-")
    return cleaned[:48] or "unnamed-guard"


def get_guards_path(cwd: str | None = None) -> str:
    root = cwd or config.WORKSPACE_DIR
    return os.path.join(root, GUARDS_DIR, GUARDS_FILE)


def load_guards(cwd: str | None = None) -> dict[str, Any]:
    path = get_guards_path(cwd)
    return jsonstore.read_or(path, {"version": 1, "guards": {}})


def save_guards(data: dict[str, Any], cwd: str | None = None) -> None:
    path = get_guards_path(cwd)
    jsonstore.write(path, data, indent=2, lock=False)


def get_git_diff_text(diff_spec: str = "HEAD~1", cwd: str | None = None) -> str:
    workspace = cwd or config.WORKSPACE_DIR
    cmd = [*gitsafe.GIT, "diff", "-U1", diff_spec]
    try:
        proc = subprocess.run(cmd, cwd=workspace, capture_output=True, text=True, timeout=15)
        return proc.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _extract_diff_hunks(diff_text: str) -> list[dict[str, Any]]:
    hunks: list[dict[str, Any]] = []
    current_file = ""
    current_removed: list[str] = []
    current_added: list[str] = []

    for line in diff_text.splitlines():
        if line.startswith("--- a/"):
            continue
        elif line.startswith("+++ b/"):
            if current_file and (current_removed or current_added):
                hunks.append({
                    "file": current_file,
                    "removed": current_removed,
                    "added": current_added,
                })
            current_file = line[6:].strip()
            current_removed = []
            current_added = []
        elif line.startswith("-") and not line.startswith("---") and current_file:
            stripped = line[1:].strip()
            if len(stripped) > 4 and not stripped.startswith("//") and not stripped.startswith("#"):
                current_removed.append(stripped)
        elif line.startswith("+") and not line.startswith("+++") and current_file:
            stripped = line[1:].strip()
            if len(stripped) > 4:
                current_added.append(stripped)

    if current_file and (current_removed or current_added):
        hunks.append({
            "file": current_file,
            "removed": current_removed,
            "added": current_added,
        })

    return hunks


_TRIVIAL_STOP_WORDS = {
    "return null;",
    "return null",
    "return none",
    "return true;",
    "return true",
    "return false;",
    "return false",
    "pass",
    "pass;",
    "break;",
    "break",
    "continue;",
    "continue",
}


def _synthesize_forbidden_patterns(removed: list[str]) -> list[str]:
    patterns: list[str] = []
    for line in removed[:10]:
        pat = line.replace("\\", "\\\\")
        pat = re.sub(r"\s+", " ", pat).strip()
        pat_clean = pat.rstrip(";").lower()
        if pat.lower() in _TRIVIAL_STOP_WORDS or pat_clean in _TRIVIAL_STOP_WORDS:
            continue
        if len(pat) >= 8 and pat not in patterns:
            patterns.append(pat)
        if len(patterns) >= 3:
            break
    return patterns


def _derive_guard_patterns(hunk: dict[str, Any]) -> tuple[list[str], str]:
    patterns = _synthesize_forbidden_patterns(hunk.get("removed", []))
    title_candidate = patterns[0][:40] if patterns else ""
    return patterns, title_candidate or "defect regression"


def _derive_file_globs(filepath: str) -> list[str]:
    ext = os.path.splitext(filepath)[1]
    dirname = os.path.dirname(filepath)
    if dirname:
        return [f"{dirname}/**/*{ext}", f"**/*{ext}"]
    return [f"**/*{ext}"] if ext else ["**/*"]


def _write_agent_rule(
    guard_id: str,
    title: str,
    category: str,
    file_globs: list[str],
    patterns: list[str],
    cwd: str | None = None,
) -> str:
    workspace = cwd or config.WORKSPACE_DIR
    target_dir = os.path.join(workspace, RULES_DIR)
    os.makedirs(target_dir, exist_ok=True)
    rule_path = os.path.join(target_dir, f"{guard_id}.md")

    safe_title = title.replace('"', "'").replace("\n", " ").replace("\r", " ")
    globs_yaml = json.dumps(file_globs)
    patterns_md = "\n".join(f"- `{p}`" for p in patterns)

    content = f"""---
description: "Learned Guard: {safe_title}"
paths: {globs_yaml}
---
# Invariant: {safe_title} ({category})

This rule was automatically compiled by `brevio-core learn` from a fixed defect to prevent recurrence.
When editing files matching `{', '.join(file_globs)}`, ensure the following anti-patterns are NEVER introduced:

{patterns_md}

Always write type-safe, hermetic code conforming to project invariants.
"""
    with open(rule_path, "w", encoding="utf-8") as f:
        f.write(content)

    return rule_path


def plan_guard(
    diff_text: str,
    name: str | None = None,
    category: str = "robustness",
    cwd: str | None = None,
) -> dict[str, Any] | None:
    """The guard a git diff compiles into, without writing anything (``learn --dry-run``, ROADMAP E34)."""
    hunks = _extract_diff_hunks(diff_text)
    if not hunks:
        return None

    chosen_hunk = None
    patterns: list[str] = []
    detected_title = ""
    for hunk in hunks:
        cand_patterns, cand_title = _derive_guard_patterns(hunk)
        if cand_patterns:
            chosen_hunk = hunk
            patterns = cand_patterns
            detected_title = cand_title
            break
    if not chosen_hunk or not patterns:
        return None
    filepath = chosen_hunk["file"]

    title = name or f"Fix {detected_title} in {os.path.basename(filepath)}"
    guard_id = f"guard-{_slugify(title)}"
    return {
        "id": guard_id,
        "title": title,
        "category": category,
        "source_file": filepath,
        "file_patterns": _derive_file_globs(filepath),
        "patterns": patterns,
        "status": "trial",
        "runs_evaluated": 0,
        "false_fails": 0,
        "intercepted": 0,
        "rule_file": os.path.join(RULES_DIR, f"{guard_id}.md"),   # what _write_agent_rule writes, relative
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }


def compile_guard_from_diff(
    diff_text: str,
    name: str | None = None,
    category: str = "robustness",
    cwd: str | None = None,
) -> dict[str, Any] | None:
    """Compile removed patterns from a git diff into a zero-token guard and agent rule."""
    guard = plan_guard(diff_text, name, category, cwd)
    if not guard:
        return None
    _write_agent_rule(guard["id"], guard["title"], category, guard["file_patterns"], guard["patterns"], cwd=cwd)
    data = load_guards(cwd)
    data.setdefault("guards", {})[guard["id"]] = guard
    save_guards(data, cwd)
    return guard


def evaluate_guard_trial(
    guard_id: str,
    caught: bool = False,
    false_fail: bool = False,
    cwd: str | None = None,
) -> dict[str, Any] | None:
    """Record a guard evaluation run and handle trial promotion or auto-retirement."""
    data = load_guards(cwd)
    guards = data.get("guards", {})
    if guard_id not in guards:
        return None

    g = guards[guard_id]
    g["runs_evaluated"] = int(g.get("runs_evaluated", 0)) + 1
    if caught:
        g["intercepted"] = int(g.get("intercepted", 0)) + 1
    if false_fail:
        g["false_fails"] = int(g.get("false_fails", 0)) + 1

    runs = g["runs_evaluated"]
    fails = g["false_fails"]

    # Auto-promotion: 5 clean runs with zero false fails
    if g["status"] == "trial" and runs >= 5 and fails == 0:
        g["status"] = "active"

    # Auto-retirement: noisy guard with high false failure rate
    if fails >= 2 and (fails / max(1, runs)) > 0.3:
        g["status"] = "retired"

    g["updated_at"] = _now_iso()
    save_guards(data, cwd)
    return g
