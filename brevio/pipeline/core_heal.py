"""Autonomous self-healing loop: deterministic auto-fixes, gate checks, defect guards, and heal packets (ROADMAP E42).

Standard library and existing brevio pipeline modules only. No model calls, no network, no vendor SDKs.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys
from collections.abc import Generator
from typing import Any

from brevio.pipeline import core_cli, core_memory
from brevio.pipeline.code_rules import details, fixers
from brevio.pipeline.gates import core_gates, defect_compiler

EXIT_OK = 0
EXIT_BLOCK = 1
MAX_HEAL_PACKET_CHARS = 6000
_FINDING_LINE_RE = re.compile(r"^([^:\n]+?):(\d+):\s*(?:\[(R\d+\.\d+)\])?\s*(.*)")
_GATE_PATH_RE = re.compile(r"^([^:\n]+?)(?::(\d+))?:?\s*(.*)")
_COMMENT_HASH_EXTS = frozenset({".py", ".sh", ".yaml", ".yml", ".toml", ".rb"})


@contextlib.contextmanager
def _in_directory(target_dir: str) -> Generator[str, None, None]:
    """Change working directory temporarily within context manager."""
    orig = os.getcwd()
    abs_target = os.path.abspath(target_dir)
    try:
        os.chdir(abs_target)
        yield abs_target
    finally:
        os.chdir(orig)


def _surgical_edit_for_finding(finding: str, root: str = ".") -> str:
    """Generate a <<<<<<< SEARCH ... ======= ... >>>>>>> REPLACE block for one rule finding."""
    m = _FINDING_LINE_RE.match(finding)
    if not m:
        return ""
    rel_path, lno_str, rule_id, desc = m.group(1), m.group(2), m.group(3) or "", m.group(4)
    lno = int(lno_str)
    full_path = os.path.join(root, rel_path)
    target_line = ""
    try:
        with open(full_path, encoding="utf-8", errors="replace") as fh:
            for cur_idx, line in enumerate(fh, 1):
                if cur_idx == lno:
                    target_line = line.rstrip("\r\n")
                    break
    except OSError:
        pass

    ext = os.path.splitext(rel_path)[1].lower()
    is_hash_comment = ext in _COMMENT_HASH_EXTS

    if not target_line:
        target_line = f"# Implicated line at {rel_path}:{lno}" if is_hash_comment else f"// Implicated line at {rel_path}:{lno}"

    replacement = ""
    fixer = fixers.FIXERS.get(rule_id)
    if fixer and ext in fixer.suffixes:
        try:
            cand = fixer(target_line)
            if cand != target_line:
                replacement = cand
        except Exception:
            pass

    if not replacement:
        detail = details.DETAILS.get(rule_id)
        if detail and detail.good:
            good_example = detail.good.strip().splitlines()[0]
            if is_hash_comment:
                replacement = f"# Fix [{rule_id}]: {desc}\n# Ref: {good_example}"
            else:
                replacement = f"// Fix [{rule_id}]: {desc}\n// Ref: {good_example}"
        else:
            replacement = f"# Fix [{rule_id}]: {desc}" if is_hash_comment else f"// Fix [{rule_id}]: {desc}"

    return (
        f"#### File: {rel_path}:{lno} [{rule_id}]\n"
        f"<<<<<<< SEARCH\n"
        f"{target_line}\n"
        f"=======\n"
        f"{replacement}\n"
        f">>>>>>> REPLACE\n"
    )


def _surgical_edit_for_gate_failure(failure: str, root: str = ".") -> str:
    """Generate a <<<<<<< SEARCH ... ======= ... >>>>>>> REPLACE block for one gate failure."""
    m = _GATE_PATH_RE.match(failure)
    if not m:
        return ""
    rel_path = m.group(1).strip()
    lno_str = m.group(2)
    desc = m.group(3).strip()
    lno = int(lno_str) if lno_str else 1
    ext = os.path.splitext(rel_path)[1].lower()
    is_hash_comment = ext in _COMMENT_HASH_EXTS

    target_line = ""
    full_path = os.path.join(root, rel_path)
    if os.path.isfile(full_path):
        try:
            with open(full_path, encoding="utf-8", errors="replace") as fh:
                for cur_idx, line in enumerate(fh, 1):
                    if cur_idx == lno:
                        target_line = line.rstrip("\r\n")
                        break
        except OSError:
            pass

    if not target_line:
        target_line = f"# Conflict marker or gate failure at {rel_path}:{lno}" if is_hash_comment else f"// Conflict marker or gate failure at {rel_path}:{lno}"

    replacement = f"# Resolved: {desc}" if is_hash_comment else f"// Resolved: {desc}"

    return (
        f"#### Gate Issue: {rel_path}:{lno}\n"
        f"<<<<<<< SEARCH\n"
        f"{target_line}\n"
        f"=======\n"
        f"{replacement}\n"
        f">>>>>>> REPLACE\n"
    )


def _synthesize_heal_packet(
    remaining_findings: list[str],
    gate_failures: list[str],
    implicated_files: list[str],
    brief: dict[str, Any],
    max_chars: int = MAX_HEAL_PACKET_CHARS,
    root: str = ".",
) -> str:
    """Synthesize compact, self-contained <brevio_heal_packet>."""
    parts: list[str] = [
        "<brevio_heal_packet>",
        "### Brevio Autonomous Self-Healing Packet",
        f"Target: resolve {len(remaining_findings)} finding(s) and {len(gate_failures)} gate failure(s).",
        "Instructions: Apply surgical edits below directly. Do NOT run noisy full-repo test suites.",
        "",
    ]

    if remaining_findings:
        parts.append("#### Remaining Findings:")
        for f in remaining_findings:
            parts.append(f"- {f}")
        parts.append("")

    if gate_failures:
        parts.append("#### Gate Failures:")
        for gf in gate_failures:
            parts.append(f"- {gf}")
        parts.append("")

    parts.append("#### 1-Hop Architectural Context:")
    parts.append(f"- Implicated files: {', '.join(implicated_files) if implicated_files else 'none'}")
    neighbors = brief.get("neighbors", [])
    if neighbors:
        parts.append(f"- 1-Hop neighbors: {', '.join(neighbors[:6])}")
    episodes = brief.get("episodes", [])
    if episodes:
        parts.append("- Recalled traps & fixes:")
        for ep in episodes[:4]:
            parts.append(f"  • {ep.get('rule_id')}: {ep.get('trap')} -> {ep.get('fix')}")
    guards = brief.get("guards", [])
    if guards:
        parts.append(f"- Active zero-token guards: {len(guards)} registered")
    parts.append("")

    rule_ids = set()
    for f in remaining_findings:
        m = re.search(r"\[(R\d+\.\d+)\]", f)
        if m:
            rule_ids.add(m.group(1))

    if rule_ids:
        parts.append("#### Rule Rationales:")
        for rid in sorted(rule_ids):
            detail = details.DETAILS.get(rid)
            if detail:
                parts.append(f"- [{rid}]: {detail.why}")
                if detail.bad:
                    parts.append(f"  Bad: {detail.bad.splitlines()[0]}")
                if detail.good:
                    parts.append(f"  Good: {detail.good.splitlines()[0]}")
        parts.append("")

    parts.append("#### Surgical Edits:")
    for f in remaining_findings:
        block = _surgical_edit_for_finding(f, root=root)
        if block:
            parts.append(block)
    for gf in gate_failures:
        block = _surgical_edit_for_gate_failure(gf, root=root)
        if block:
            parts.append(block)

    parts.append("</brevio_heal_packet>")
    full_text = "\n".join(parts)

    if len(full_text) > max_chars:
        closing = "\n...\n</brevio_heal_packet>"
        allowed = max(0, max_chars - len(closing))
        full_text = full_text[:allowed] + closing

    return full_text


def run_heal(
    root: str = ".",
    diff_base: str | None = None,
    apply_fixes: bool = True,
    compile_guards: bool = True,
    max_chars: int = MAX_HEAL_PACKET_CHARS,
) -> dict[str, Any]:
    """Run autonomous self-healing loop: auto-fixes, scan/gate checks, guards compilation, and packet synthesis."""
    with _in_directory(root):
        auto_fixed_files: list[str] = []
        auto_fixed_count = 0

        # Step 1 (Deterministic Auto-Fix)
        if apply_fixes:
            lines = core_cli.select_lines([], diff_base)
            changes = core_cli.plan_fixes(lines)
            if changes:
                core_cli.apply_fixes(changes)
                auto_fixed_files = sorted(changes.keys())
                auto_fixed_count = sum(len(r) for _o, _n, r in changes.values())

        # Step 2 (Scan & Pre-PR Gate Check)
        lines = core_cli.select_lines([], diff_base)
        gate_res = core_gates.run_check(root=".", base=diff_base or "HEAD", lines=lines)
        checks = gate_res.get("checks", {})
        rule_findings = list(checks.get("rules", []))
        try:
            triaged_rules, _, _ = core_cli.triage(rule_findings, root=".")
        except TypeError:
            triaged_rules, _, _ = core_cli.triage(rule_findings)

        remaining_findings = sorted(set(triaged_rules))
        gate_failures = []
        for k in ("conflict_markers", "test_custody", "test_imports", "complexity", "orphan_files", "agent_files", "env_parity"):
            gate_failures.extend(checks.get(k, []))
        gate_failures = sorted(set(gate_failures))

        # Step 3 (Defect Compilation & Guard Synthesis)
        if compile_guards and (remaining_findings or gate_failures):
            diff_text = core_gates._git(".", "diff", "-U1", diff_base or "HEAD")
            if diff_text:
                try:
                    defect_compiler.compile_guard_from_diff(diff_text, cwd=".")
                except Exception:
                    pass
            try:
                guards_data = defect_compiler.load_guards(cwd=".")
                guards = guards_data.setdefault("guards", {})
                for finding in remaining_findings:
                    m = re.search(r"\[(R\d+\.\d+)\]\s*(.*)", finding)
                    if m:
                        rid, desc = m.group(1), m.group(2).strip()
                        gid = f"guard-{rid.lower().replace('.', '-')}"
                        if gid not in guards:
                            guards[gid] = {
                                "id": gid,
                                "title": f"Prevent recurrence of {rid}",
                                "rule_id": rid,
                                "description": desc[:60],
                                "status": "active",
                                "created_at": defect_compiler._now_iso(),
                            }
                defect_compiler.save_guards(guards_data, cwd=".")
            except Exception:
                pass

        # Step 4 (1-Hop Context & Surgical <brevio_heal_packet> Synthesis)
        implicated_set: set[str] = set()
        for item in remaining_findings + gate_failures:
            m = re.match(r"^([^:\n]+?):(?:\d+):", item)
            if m:
                cand = m.group(1).strip()
                if os.path.exists(cand):
                    implicated_set.add(cand)
            else:
                parts = item.split(":", 1)
                if parts and os.path.exists(parts[0].strip()):
                    implicated_set.add(parts[0].strip())
        implicated_files = sorted(implicated_set)

        brief: dict[str, Any] = {}
        if hasattr(core_memory, "build_brief"):
            try:
                brief = core_memory.build_brief(implicated_files, root=".")
            except Exception:
                brief = {}
        if not brief and hasattr(core_memory, "brief_for_files"):
            try:
                brief = core_memory.brief_for_files(implicated_files, cwd=".")
            except Exception:
                brief = {}

        ok = len(remaining_findings) == 0 and len(gate_failures) == 0
        status = "clean" if ok else "needs_repair"

        heal_packet_str = ""
        if not ok:
            heal_packet_str = _synthesize_heal_packet(
                remaining_findings=remaining_findings,
                gate_failures=gate_failures,
                implicated_files=implicated_files,
                brief=brief,
                max_chars=max_chars,
                root=".",
            )

        return {
            "ok": ok,
            "status": status,
            "auto_fixed_files": auto_fixed_files,
            "auto_fixed_count": auto_fixed_count,
            "remaining_findings": remaining_findings,
            "gate_failures": gate_failures,
            "implicated_files": implicated_files,
            "heal_packet": heal_packet_str,
        }


def format_heal_text(report: dict[str, Any]) -> str:
    """Format self-heal report for terminal output."""
    if report.get("ok"):
        count = report.get("auto_fixed_count", 0)
        files = report.get("auto_fixed_files", [])
        if count > 0:
            return f"✅ Self-heal complete: 0 remaining findings ({count} auto-fixed in {len(files)} file(s))."
        return "✅ Self-heal complete: 0 remaining findings."
    return str(report.get("heal_packet", ""))


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for brevio-core heal."""
    parser = argparse.ArgumentParser(prog="brevio-core heal", description="Autonomous self-healing loop")
    parser.add_argument("--root", default=".", help="project root directory")
    parser.add_argument("--diff", default=None, help="diff base commit or branch")
    parser.add_argument("--no-fix", action="store_true", help="skip deterministic auto-fixes")
    parser.add_argument("--no-compile-guards", action="store_true", help="skip compiling defect guards")
    parser.add_argument("--json", action="store_true", help="output report as JSON")
    parser.add_argument("--format", choices=("text", "json"), default=None, help="output format")
    parser.add_argument("--max-chars", type=int, default=MAX_HEAL_PACKET_CHARS, help="max chars for heal packet")
    args = parser.parse_args(argv)

    report = run_heal(
        root=args.root,
        diff_base=args.diff,
        apply_fixes=not args.no_fix,
        compile_guards=not args.no_compile_guards,
        max_chars=args.max_chars,
    )

    fmt = "json" if (args.json or args.format == "json") else "text"
    if fmt == "json":
        print(json.dumps(report, indent=2))
    else:
        print(format_heal_text(report))

    return EXIT_OK if report.get("ok") else EXIT_BLOCK


if __name__ == "__main__":
    sys.exit(main())
