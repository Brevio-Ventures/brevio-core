"""``brevio-core score``: deterministic Agent Safety Score (0-100, A+ to F), README badge and scorecard.

Standard library and exported core modules only; runs with zero network calls and no git remote/config subprocesses.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
from collections import Counter
from typing import Any

from brevio.pipeline import core_cli
from brevio.pipeline.code_rules import PR_RULES_122
from brevio.pipeline.gates import dopamine_ledger

HELP = "compute the deterministic Agent Safety Score (0-100, A+ to F), README badge and scorecard"
ENCYCLOPEDIA_URL = "https://brevio.pro/tools/rules-encyclopedia"
PLAYGROUND_URL = "https://brevio.pro/tools/agent-guard-playground"
FORMATS = ("text", "markdown", "json")
_GITHUB_REPO_RE = re.compile(r"github\.com[:/]([\w.-]+/[\w.-]+?)(?:\.git)?\s*$", re.M)


def grade_and_color(score: int) -> tuple[str, str]:
    """Map numeric Agent Safety Score (0-100) to ``(grade, shield_color)``."""
    if score >= 100:
        return "A+", "brightgreen"
    if score >= 90:
        return "A", "brightgreen"
    if score >= 80:
        return "B", "green"
    if score >= 70:
        return "C", "yellow"
    if score >= 60:
        return "D", "orange"
    return "F", "red"


def detect_repo_slug(root: str = ".") -> str:
    """Detect ``<owner>/<repo>`` from ``GITHUB_REPOSITORY`` or ``.git/config`` without subprocesses."""
    env = os.environ
    env_slug = env.get("GITHUB_REPOSITORY", "").strip().strip("/")
    if "/" in env_slug and len(env_slug.split("/")) == 2:
        return env_slug
    try:
        cfg = pathlib.Path(root, ".git", "config").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    m = _GITHUB_REPO_RE.search(cfg)
    return m.group(1) if m else ""


def build_roast(score: int, rule_counts: dict[str, int]) -> str:
    """Deterministic verdict / roast line based on the score and triggered rules."""
    if score >= 100 and not rule_counts:
        return "Zero agent-slop detected across scanned files — ready for autonomous merge."
    top = list(rule_counts)[:3]
    risks = ", ".join(f"{r} ({PR_RULES_122.get(r, 'agent defect').split(':')[0]})" for r in top) or "findings"
    if score >= 80:
        return f"Mostly clean ({score}/100), but coding-agent shortcuts slipped in via {risks}."
    if score >= 60:
        return f"Agent-slop warning ({score}/100): autonomous edits risked production via {risks}."
    return f"Critical agent-slop alert ({score}/100): merge blocked by {risks} — test fixes in Playground."


def _build_receipt_url(meta: dict[str, Any], score: int) -> str:
    interceptions = int(meta.get("errors", 0) + meta.get("warnings", 0))
    try:
        return dopamine_ledger.generate_receipt_url(interceptions, None, 0, aeo_score=score)  # type: ignore[arg-type]
    except TypeError:
        return dopamine_ledger.generate_receipt_url(interceptions, aeo_score=score)  # type: ignore[call-arg]


def _triggered_rules(shown: list[str]) -> tuple[dict[str, int], list[dict[str, Any]]]:
    counts: Counter[str] = Counter()
    for f in shown:
        fields = core_cli.finding_fields(f)
        if fields and fields.get("rule"):
            counts[str(fields["rule"])] += 1
    ordered = dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
    details = [
        {
            "rule": rid,
            "count": cnt,
            "title": PR_RULES_122.get(rid, rid),
            "playground_url": f"{PLAYGROUND_URL}?rule={rid}",
        }
        for rid, cnt in ordered.items()
    ]
    return ordered, details


def compute_scorecard(paths: list[str] | None = None, diff: str | None = None, root: str = ".") -> dict[str, Any]:
    """Run the deterministic scan and build the Agent Safety Score payload."""
    named = list(paths or [])
    missing = [p for p in named if not os.path.exists(p)]
    if missing:
        raise core_cli.UsageError(f"no such file or folder: {', '.join(missing)}")
    files = core_cli.select_lines(named, diff)
    proj = core_cli.project(files)
    raw = core_cli.scan_surface(files, proj, root=root)
    shown, silenced, baselined = core_cli.triage(raw)
    warnings = sum(1 for f in shown if core_cli.level_of(f, proj) == "warn")
    errors = len(shown) - warnings
    score = max(0, 100 - 10 * errors - 3 * warnings)
    grade, color = grade_and_color(score)
    grade_enc = grade.replace("+", "%2B")
    rule_counts, rules_list = _triggered_rules(shown)
    repo_slug = detect_repo_slug(root)
    badge_md = (
        f"[![Agent Safety: {grade} ({score}/100)]"
        f"(https://img.shields.io/badge/agent%20safety-{grade_enc}%20({score}%2F100)-{color})]"
        f"({ENCYCLOPEDIA_URL})"
    )
    repo_badge_md = (
        f"[![Brevio Agent Safety](https://brevio.pro/api/badge/{repo_slug}?score={score}&grade={grade_enc})]"
        f"(https://brevio.pro/scan?repo={repo_slug})"
        if repo_slug else ""
    )
    scorecard_md = (
        f"[![Brevio Agent Scorecard]"
        f"(https://brevio.pro/api/tools/scorecard.svg?mode=repo&repo={repo_slug}&score={score}&grade={grade_enc})]"
        f"(https://brevio.pro/scan?repo={repo_slug})"
        if repo_slug else ""
    )
    meta = {"score": score, "grade": grade, "errors": errors, "warnings": warnings, "files": len(files)}
    return {
        "score": score,
        "grade": grade,
        "color": color,
        "errors": errors,
        "warnings": warnings,
        "files": len(files),
        "findings": shown,
        "silenced": len(silenced),
        "baselined": len(baselined),
        "triggered_rules": rules_list,
        "playground_links": {r["rule"]: r["playground_url"] for r in rules_list},
        "rules_encyclopedia_url": ENCYCLOPEDIA_URL,
        "roast": build_roast(score, rule_counts),
        "repo": repo_slug,
        "badge_markdown": badge_md,
        "repo_badge_markdown": repo_badge_md,
        "scorecard_markdown": scorecard_md,
        "receipt_url": _build_receipt_url(meta, score),
    }


def render_text(card: dict[str, Any], footer: str = "", roast: bool = False) -> str:
    """Format the Agent Safety Scorecard as plain text."""
    lines = [
        f"brevio-core score: {card['score']}/100 (Grade: {card['grade']})",
        f"Files scanned: {card['files']} | Errors: {card['errors']} | Warnings: {card['warnings']}",
        f"Verdict: {card['roast']}",
    ]
    for item in card["triggered_rules"]:
        lines.append(f"  [{item['rule']}] ({item['count']}x) {item['title']} -> {item['playground_url']}")
    if roast and card.get("triggered_rules"):
        lines.append("Engineering Roast:")
        for r in card["triggered_rules"]:
            lines.append(f"  * {r['rule']}: AI wrote code violating {r['title']}. Fix this before merge.")
    lines += [
        f"Rules Encyclopedia: {card['rules_encyclopedia_url']}",
        f"Verified Receipt: {card['receipt_url']}",
        f"README Badge: {card['badge_markdown']}",
    ]
    if card["repo_badge_markdown"]:
        lines.append(f"Repo Badge: {card['repo_badge_markdown']}")
        lines.append(f"Repo Scorecard: {card['scorecard_markdown']}")
    if footer:
        lines.append(footer)
    return "\n".join(lines) + "\n"


def render_markdown(card: dict[str, Any], footer: str = "", roast: bool = False) -> str:
    """Format the Agent Safety Scorecard as Markdown."""
    lines = [
        f"### Brevio Agent Safety Score: {card['score']}/100 (Grade `{card['grade']}`)",
        "",
        card["badge_markdown"],
        "",
        f"> **Verdict:** {card['roast']}",
        "",
        f"- **Files scanned:** {card['files']} | **Errors:** {card['errors']} | **Warnings:** {card['warnings']}",
    ]
    if card["scorecard_markdown"]:
        lines += ["", card["scorecard_markdown"]]
    if card["triggered_rules"]:
        lines += ["", "| Rule | Hits | Description | Playground |", "| :--- | :--- | :--- | :--- |"]
        for item in card["triggered_rules"]:
            lines.append(
                f"| `{item['rule']}` | {item['count']} | {item['title']} | "
                f"[Test {item['rule']} in Playground]({item['playground_url']}) |"
            )
    if roast and card.get("triggered_rules"):
        lines += ["", "#### Engineering Roast", ""]
        for r in card["triggered_rules"]:
            lines.append(f"- **{r['rule']}**: AI wrote code violating {r['title']}. Fix this before merge.")
    lines += [
        "",
        f"[Rules Encyclopedia]({card['rules_encyclopedia_url']}) · [Verified Receipt]({card['receipt_url']})",
        "",
        "<details><summary>Copy README badge Markdown</summary>",
        "",
        "```markdown",
        card["badge_markdown"],
        "```",
        "</details>",
    ]
    if footer:
        lines += ["", footer]
    return "\n".join(lines) + "\n"


def parser(prog: str = "brevio-core score") -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=prog, description=HELP)
    ap.add_argument("paths", nargs="*", help="files or folders to score (default: the current folder)")
    ap.add_argument("--diff", nargs="?", const="", default=None, metavar="BASE",
                    help="score only the lines added against BASE (default origin/main)")
    ap.add_argument("--min", dest="min_score", type=int, default=0, metavar="SCORE",
                    help="exit 1 when the score is below SCORE (default 0)")
    ap.add_argument("--format", choices=FORMATS, default="text", help="output format (default: text)")
    ap.add_argument("--markdown", action="store_true", help="alias for --format markdown")
    ap.add_argument("--json", action="store_true", help="output scorecard as JSON")
    ap.add_argument("--badge", action="store_true", help="print only the Markdown shield badge")
    ap.add_argument("--roast", action="store_true", help="include the verdict roast line")
    ap.add_argument("--no-upgrade-line", action="store_true", help="leave out the closing Teams line")
    return ap


def main(argv: list[str] | None = None, prog: str = "brevio-core score") -> int:
    args = parser(prog).parse_args(sys.argv[1:] if argv is None else argv)
    try:
        card = compute_scorecard(args.paths, args.diff)
    except core_cli.UsageError as exc:
        print(f"brevio-core: {exc}", file=sys.stderr)
        return 2
    rc = 0 if card["score"] >= args.min_score else 1
    if args.badge:
        sys.stdout.write(card["badge_markdown"] + "\n")
        return rc
    fmt = "markdown" if args.markdown else ("json" if args.json else args.format)
    if fmt == "json":
        print(json.dumps(card, indent=2))
        return rc
    footer = core_cli.upgrade_line("score", not args.no_upgrade_line)
    out = render_markdown(card, footer, roast=args.roast) if fmt == "markdown" else render_text(card, footer, roast=args.roast)
    sys.stdout.write(out)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
