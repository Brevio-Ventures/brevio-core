"""Portable single-repo PageRank and surface-briefing module: rules and trap memory.

Standard library plus exported package modules only. Read-only git subcommands only.
"""
from __future__ import annotations

import argparse
import ast
import datetime
import fnmatch
import json
import os
import subprocess
import sys
from typing import Any

from brevio.pipeline import agent_host, dev_rules
from brevio.pipeline.rule_host import GIT

MEMORY_DIR = ".brevio"
MEMORY_FILE = "file_memory.json"
MAX_EPISODES = 50
HELP = "print the zero-token rule & trap briefing for the files you are about to edit"


def _git(cwd: str, *args: str) -> str:
    try:
        r = subprocess.run([*GIT, "-C", cwd, *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout if r.returncode == 0 else ""


def _memory_path(cwd: str | None = None) -> str:
    root = cwd if cwd is not None else agent_host.config.WORKSPACE_DIR
    return os.path.join(root, MEMORY_DIR, MEMORY_FILE)


def load_episodes(cwd: str | None = None) -> list[dict[str, Any]]:
    """Load stored episodes from the workspace memory file."""
    path = _memory_path(cwd)
    data = agent_host.jsonstore.read_or(path, {"version": 1, "episodes": []})
    if isinstance(data, dict):
        return list(data.get("episodes", []))
    if isinstance(data, list):
        return list(data)
    return []


def save_episodes(episodes: list[dict[str, Any]], cwd: str | None = None) -> str:
    """Save episodes to the workspace memory file atomically."""
    path = _memory_path(cwd)
    data = {"version": 1, "episodes": episodes}
    agent_host.jsonstore.write(path, data)
    return path


def record_episode(
    file_path: str,
    rule_id: str,
    trap: str,
    fix: str,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Record a trap-to-fix episode for file_path, deduplicating and keeping the newest 50."""
    norm_path = file_path.replace(os.sep, "/")
    ep: dict[str, Any] = {
        "file": norm_path,
        "rule_id": rule_id,
        "trap": trap,
        "fix": fix,
        "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    existing = load_episodes(cwd=cwd)
    deduped = [e for e in existing if (e.get("file"), e.get("rule_id")) != (norm_path, rule_id)]
    new_list = ([ep] + deduped)[:MAX_EPISODES]
    save_episodes(new_list, cwd=cwd)
    return ep


def _py_import_candidates(root: str, full_path: str, tree: ast.AST) -> list[str]:
    cands: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod_rel = alias.name.replace(".", "/")
                cands.extend((os.path.join(root, mod_rel + ".py"), os.path.join(root, mod_rel, "__init__.py")))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base_dir = os.path.dirname(full_path)
                for _ in range(node.level - 1):
                    base_dir = os.path.dirname(base_dir)
                target_dir = os.path.join(base_dir, node.module.replace(".", "/")) if node.module else base_dir
            elif node.module:
                target_dir = os.path.join(root, node.module.replace(".", "/"))
            else:
                continue
            cands.extend((target_dir + ".py", os.path.join(target_dir, "__init__.py")))
            cands.extend(os.path.join(target_dir, alias.name + ".py") for alias in node.names)
    return cands


def _matches_any_glob(rel_path: str, globs: list[str] | tuple[str, ...]) -> bool:
    """Match a normalized relative path against a list of glob patterns, supporting root-level ``**/``."""
    norm = rel_path.replace(os.sep, "/").lstrip("./")
    for pat in globs:
        if fnmatch.fnmatch(norm, pat) or (pat.startswith("**/") and fnmatch.fnmatch(norm, pat[3:])):
            return True
    return False


def _normalize_target(tf: str, real_root: str) -> str | None:
    if os.path.isabs(tf):
        try:
            real_tf = os.path.realpath(tf)
            if os.path.commonpath([real_root, real_tf]) != real_root:
                return None
            rel = os.path.relpath(real_tf, real_root).replace(os.sep, "/")
            return None if rel.startswith("..") else rel
        except ValueError:
            return None
    return tf.replace(os.sep, "/")


def one_hop_neighbors(root: str, target_files: list[str], max_files: int = 25) -> set[str]:
    """Return bounded 1-hop neighborhood for target_files via imports and commit co-changes."""
    ast_neighbors: set[str] = set()
    cochange_neighbors: set[str] = set()
    real_root = os.path.realpath(root)
    norm_targets = [r for tf in target_files if (r := _normalize_target(tf, real_root)) is not None]
    target_set = set(norm_targets)

    def _add_cand(cand: str) -> None:
        if not os.path.isfile(cand):
            return
        try:
            real_cand = os.path.realpath(cand)
            if os.path.commonpath([real_root, real_cand]) != real_root:
                return
        except ValueError:
            return
        rel = os.path.relpath(real_cand, real_root).replace(os.sep, "/")
        if not rel.startswith("..") and rel not in target_set:
            ast_neighbors.add(rel)

    for rel_tf in norm_targets:
        full_path = os.path.join(root, rel_tf)
        if not rel_tf.endswith(".py") or not os.path.isfile(full_path):
            continue
        try:
            with open(full_path, encoding="utf-8", errors="ignore") as fh:
                tree = ast.parse(fh.read(), full_path)
        except (OSError, SyntaxError):
            continue
        for cand in _py_import_candidates(root, full_path, tree):
            _add_cand(cand)

    for ref in ("HEAD", "HEAD~1", "HEAD~2", "HEAD~3", "HEAD~4"):
        commit_files_raw = _git(root, "show", "--name-only", "--format=", ref)
        if not commit_files_raw:
            continue
        commit_files = {ln.strip().replace(os.sep, "/") for ln in commit_files_raw.splitlines() if ln.strip()}
        if len(commit_files) <= 30 and target_set.intersection(commit_files):
            cochange_neighbors.update(commit_files - target_set)

    ordered = sorted(ast_neighbors) + sorted(cochange_neighbors - ast_neighbors)
    return set(ordered[:max_files])


def brief_for_files(files: list[str], cwd: str | None = None) -> dict[str, Any]:
    """Combine micro rules, recalled episodes, and 1-hop neighbors for files."""
    root = cwd if cwd is not None else agent_host.config.WORKSPACE_DIR
    target_set = {f.replace(os.sep, "/") for f in files}
    micro_rules = dev_rules.slice_micro_rules(files)
    neighbors = one_hop_neighbors(root, files)

    episodes = load_episodes(cwd=root)
    recalled: list[dict[str, Any]] = []
    for ep in episodes:
        ep_file = str(ep.get("file", "")).replace(os.sep, "/")
        score = 0.0
        if ep_file in target_set:
            score = 1.0
        elif ep_file in neighbors:
            score = 0.5
        if score > 0.0:
            recalled.append(dict(ep, score=score))

    recalled.sort(key=lambda e: (e.get("score", 0.0), e.get("at", "")), reverse=True)
    return {
        "files": files,
        "micro_rules": micro_rules,
        "episodes": recalled,
        "neighbors": sorted(neighbors),
    }


def main(argv: list[str] | None = None, prog: str = "brevio-core brief", cwd: str | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(prog=prog, description=HELP)
    parser.add_argument("files", nargs="*", help="files to generate briefing for")
    parser.add_argument("--json", action="store_true", help="output briefing as JSON")
    parser.add_argument(
        "--record",
        nargs=3,
        metavar=("RULE", "TRAP", "FIX"),
        help="record a Trap -> Fix episode for the first named file",
    )
    args = parser.parse_args(argv)

    root = cwd if cwd is not None else os.getcwd()
    if args.record:
        if not args.files:
            sys.stderr.write("error: a file must be specified with --record\n")
            return 2
        rule_id, trap, fix = args.record
        target_file = args.files[0]
        ep = record_episode(target_file, rule_id, trap, fix, cwd=root)
        if args.json:
            print(
                json.dumps(
                    {
                        "recorded": True,
                        "rule_id": rule_id,
                        "file": target_file,
                        "path": f"{MEMORY_DIR}/{MEMORY_FILE}",
                        "episode": ep,
                    },
                    indent=2,
                )
            )
        else:
            sys.stdout.write(f"Recorded episode for {target_file}: [{rule_id}] {trap} -> {fix}\n")
        return 0

    brief = brief_for_files(args.files, cwd=root)
    if args.json:
        print(json.dumps(brief, indent=2))
    else:
        out: list[str] = []
        if brief["micro_rules"]:
            out.append(brief["micro_rules"].strip())
        if brief["episodes"]:
            out.append("\nRECALLED TRAPS & FIXES:")
            for ep in brief["episodes"]:
                rel = ep.get("score", 1.0)
                out.append(
                    f"  [{ep.get('rule_id', '')}] {ep.get('file', '')} (score: {rel}): {ep.get('trap', '')} -> {ep.get('fix', '')}"
                )
        if brief["neighbors"]:
            out.append(f"\n1-HOP NEIGHBORS: {', '.join(brief['neighbors'][:10])}")
        if not out:
            out.append("No active rules or past traps found for the specified files.")
        sys.stdout.write("\n".join(out) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
