"""The ``brevio-core`` command line: ``scan`` runs the scanned code rules on files or on a diff (ROADMAP E16, 2026-11-04).

Standard library only, so it exports with the rule engines (the core exporter) and runs with no model call and
no network. It is what the GitHub Action, the pre-commit hook and the agent hooks call. Exit code 0 means no finding,
1 means findings, 2 means a usage error. The 0.2 export set adds ``learn``, ``hook``, ``gain`` and ``add`` (ROADMAP
E16, 0.2 set); they show up only when the build ships them (``agent_tools``). The 0.3 set adds ``scan --fix``: the
fixers of ``code_rules.fixers`` rewrite a line only where its rule has one correct fix, then the files are scanned again
(ROADMAP E16, 0.3 set, 2026-11-05). The 0.4 set adds ``init`` and ``init --undo`` (``core_init``, ROADMAP E22), and
``baseline``, ``--fail-on``, inline ignores with a reason and ``--format markdown`` (``core_baseline``, ``core_markdown``;
ROADMAP E20, E21, E26). Agents cannot silence the gate: the agent hook never honours an ignore comment, and a diff scan
reports a new suppression as a finding unless ``--allow-new-suppressions`` says a person reviewed it (2026-11-05).
``--format agent`` prints the compact lines the agent hook and the MCP server answer with (ROADMAP E34, 2026-11-05).
The 0.6 set adds ``brevio-core.toml`` (``core_config``, ROADMAP E32): which rules run where and at which level, shown by
``brevio-core config``, with ``--fail-on error`` failing on error-level findings only. A preview rule reports but never
fails, and a deprecated rule reports nothing, in every set (ROADMAP E33, 2026-11-05). The 0.6 set also adds ``up``
(``core_up``, ROADMAP E37): a preview of what a team sync would take, and one Teams line at the end of the Markdown
report, which ``--no-upgrade-line`` leaves out. The agent format (hook, MCP) never carries it.
"""
from __future__ import annotations

import argparse
import difflib
import importlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Iterable
from typing import Any

from brevio.pipeline import dev_rules, leak_scan
from brevio.pipeline.code_rules import DEPRECATED, PR_RULES_122, PREVIEW, rule_status, scan_lines
from brevio.pipeline.code_rules import docs as rule_docs
from brevio.pipeline.code_rules.details import DETAILS, scanned_by
from brevio.pipeline.rule_host import GIT

CODE_SUFFIXES = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".css", ".html", ".sql", ".vue", ".svelte")
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next"}
# Code a project keeps but did not write: vendored folders, minified files and bundle chunks. Their findings are the
# upstream's, and most of the false positives of the E35 precision run came from them (docs/benchmarks/precision.md,
# 2026-11-05). Every scan mode skips them; a project excludes more with `exclude` in brevio-core.toml.
VENDORED_DIRS = {"vendor", "third_party", "third-party"}
_BUNDLE_NAME = re.compile(r"\.min\.(?:[cm]?js|css)$|\.(?:bundle|chunk)\.[cm]?js$|^chunk-[\w-]+\.[cm]?js$"
                          r"|[.-](?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{8,}\.[cm]?js$")
LONG_LINE = 500         # a file whose first two lines are longer than this is minified or bundled
MAX_BYTES = 1_000_000
AGENT_MAX = 20          # finding lines an agent is shown at once; a longer list is cut, so one reply stays short
AGENT_HINT = 100        # characters of the rule's good example a finding line carries
# DOTALL: a file name may hold a newline, and its finding must still parse (so the Markdown report escapes it).
_FINDING = re.compile(r"^(?P<path>.+?):(?P<line>\d+): (?:\[(?P<rule>[^\]]+)\] )?(?P<msg>.*)$", re.S)
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
    """Every line of each named file, and of each code file under a named folder that is not vendored, minified or
    bundled (a file named on the command line is read as asked)."""
    out: Numbered = {}
    for p in paths:
        if os.path.isdir(p):
            for dirpath, dirs, names in os.walk(p):
                dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and d not in VENDORED_DIRS)
                for n in sorted(names):
                    if n.endswith(CODE_SUFFIXES) and not _BUNDLE_NAME.search(n):
                        lines = _read(os.path.join(dirpath, n))
                        if not _long_head(lines):
                            out[_rel(os.path.join(dirpath, n))] = lines
        else:
            out[_rel(p)] = _read(p)
    return out


def _long_head(numbered: list[tuple[int, str]]) -> bool:
    return any(lno <= 2 and len(text) > LONG_LINE for lno, text in numbered[:2])


def bundled(path: str) -> bool:
    """One of the first two lines of the file on disk is longer than ``LONG_LINE``: minified or bundled output."""
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            return any(len(fh.readline(LONG_LINE + 2).rstrip("\r\n")) > LONG_LINE for _ in range(2))
    except OSError:
        return False


def _git(*args: str) -> str:
    try:
        r = subprocess.run([*GIT, *args], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout if r.returncode == 0 else ""


def has_head() -> bool:
    """The current folder is a git checkout with at least one commit."""
    return bool(_git("rev-parse", "--verify", "-q", "HEAD").strip())


def _base(want: str) -> str:
    for ref in ([want] if want else ["origin/main", "main", "HEAD"]):
        if _git("rev-parse", "--verify", "-q", ref).strip():
            return ref
    return "HEAD"


def diff_lines(base: str, only: Iterable[str] = ()) -> Numbered:
    """The lines the working tree adds against ``base`` (with their real line numbers), plus new untracked files.

    ``only`` narrows both to those paths (the agent hook asks for the one file an edit changed)."""
    spec = [f":(literal){p}" for p in only]
    out: Numbered = {}
    path, lno = "", 0
    for ln in _git("diff", "-U0", "--no-color", "--diff-filter=ACMR", _base(base), "--", *spec).splitlines():
        if ln.startswith("+++ "):
            path = ln[6:] if ln.startswith("+++ b/") else ""
        elif ln.startswith("@@"):
            m = _HUNK.match(ln)
            lno = int(m.group(1)) if m else 0
        elif path and ln.startswith("+"):
            out.setdefault(path, []).append((lno, ln[1:]))
            lno += 1
    for new in _git("ls-files", "--others", "--exclude-standard", "--", *spec).splitlines():
        if new.endswith(CODE_SUFFIXES):
            out[new] = _read(new)
    # Build output and dependencies are never the change under review, tracked or not: an install in CI writes
    # build/lib copies of the package, and scanning those flagged the rule docs' own bad examples (2026-11-05).
    # Vendored, minified and bundled files are not the project's own code either (E35, 2026-11-05).
    return {p: v for p, v in out.items() if not skipped(p) and not bundled(p)}


def skipped(path: str) -> bool:
    """``path`` lies in a folder the scan never reads (``SKIP_DIRS``, ``VENDORED_DIRS`` or an ``*.egg-info`` folder),
    or is named as a minified file or a bundle chunk."""
    parts = path.replace("\\", "/").split("/")
    return (any(p in SKIP_DIRS or p in VENDORED_DIRS or p.endswith(".egg-info") for p in parts[:-1])
            or bool(_BUNDLE_NAME.search(parts[-1])))


_DEV_FINDING = re.compile(r"^- (?P<path>.+?):(?P<line>\d+) \[(?P<rule>R\d+\.\d+)\b[^\]]*\]: (?P<msg>.*)$")


def scan(files: Numbered, proj: Any = None) -> list[str]:
    """Findings (``path:line: [rule] message``) for the given numbered lines.

    A deprecated rule reports nothing. With ``brevio-core.toml`` (the 0.6 set, ``proj`` or read here) an excluded file
    is not scanned, and a rule the config turns off for a file reports nothing there."""
    proj = project(files) if proj is None else proj
    found: list[str] = []
    for rel, numbered in sorted(files.items()):
        if proj is None or not proj.for_path(rel).excluded:
            found += scan_lines(rel, numbered)
    return [f for f in found if _runs(f, proj)]


def scan_surface(files: Numbered, proj: Any = None) -> list[str]:
    """Run both the 8 line-pattern rules (``code_rules``) and the 9 surface rules (``dev_rules``) across ``files``."""
    proj = project(files) if proj is None else proj
    found = list(scan(files, proj))
    seen = {(f["path"], f["line"], f["rule"]) for f in map(finding_fields, found) if f}
    for rel, numbered in sorted(files.items()):
        if proj is not None and proj.for_path(rel).excluded:
            continue
        full_text = ""
        if os.path.isfile(rel):
            try:
                with open(rel, encoding="utf-8", errors="ignore") as fh:
                    full_text = fh.read()
            except OSError:
                full_text = ""
        if not full_text:
            full_text = "\n".join(t for _, t in numbered)
        for raw in dev_rules._scan_single_file(rel, full_text, numbered):
            m = _DEV_FINDING.match(raw)
            if not m:
                continue
            key = (m["path"], int(m["line"]), m["rule"])
            if key in seen:
                continue
            norm = f"{m['path']}:{m['line']}: [{m['rule']}] {m['msg']}"
            if _runs(norm, proj):
                found.append(norm)
                seen.add(key)
    return found


def _catalogued(finding: str) -> tuple[str, str]:
    """``(path, rule)`` of a finding of a catalogue rule, or ``("", "")`` (a suppression finding, or not a finding)."""
    fields = finding_fields(finding)
    rule = str(fields["rule"]) if fields else ""
    return (str(fields["path"]), rule) if fields and rule in PR_RULES_122 else ("", "")


def _runs(finding: str, proj: Any) -> bool:
    path, rule = _catalogued(finding)
    if not rule:
        return True
    return rule_status(rule) != DEPRECATED and (proj is None or proj.for_path(path).runs(rule))


def level_of(finding: str, proj: Any) -> str:
    """``warn`` or ``error``: a preview rule's finding is a warning; otherwise the config's level, ``error`` by default."""
    path, rule = _catalogued(finding)
    if not rule:
        return "error"
    if rule_status(rule) == PREVIEW:
        return "warn"
    return proj.for_path(path).level(rule) if proj is not None else "error"


def blocking(shown: list[str], fail_on: str, proj: Any = None) -> list[str]:
    """The findings that fail the scan: none with ``none``; never a preview rule's; with ``error`` only error-level ones."""
    if fail_on == "none":
        return []
    return [f for f in shown if rule_status(_catalogued(f)[1]) != PREVIEW
            and (fail_on != "error" or level_of(f, proj) == "error")]


def finding_fields(finding: str) -> dict[str, str | int] | None:
    """``path``, ``line``, ``rule`` and ``message`` of one finding line, or ``None`` when it is not one."""
    m = _FINDING.match(finding)
    if not m:
        return None
    return {"path": m["path"], "line": int(m["line"]), "rule": m["rule"] or "brevio-core", "message": m["msg"]}


def _hint(rule: str) -> str:
    """`` -> `` and the first line of the rule's good example, or "" when it has none."""
    good = DETAILS[rule].good.strip() if rule in DETAILS else ""
    first = good.splitlines()[0].strip() if good else ""
    return f" -> {first[:AGENT_HINT]}" if first else ""


def agent_lines(shown: list[str]) -> list[str]:
    """``path:line [R] message -> fix hint`` per finding, grouped by rule, cut at ``AGENT_MAX`` with "+N more".

    What an agent reads: the agent hook, the MCP ``scan`` and ``scan --format agent`` print these lines."""
    order = {rid: i for i, rid in enumerate(rule_docs.rule_ids())}
    rows = sorted((f for f in map(finding_fields, shown) if f),
                  key=lambda f: (order.get(str(f["rule"]), len(order)), str(f["rule"]), str(f["path"]), int(f["line"])))
    out = [f"{f['path']}:{f['line']} [{f['rule']}] {f['message']}{_hint(str(f['rule']))}" for f in rows[:AGENT_MAX]]
    return out + ([f"+{len(rows) - AGENT_MAX} more"] if len(rows) > AGENT_MAX else [])


def select_lines(named: list[str], diff: str | None) -> Numbered:
    """The lines to scan: the added lines against ``diff`` (``None``: no diff scan), narrowed to ``named``, or whole files."""
    if diff is None:
        return collect_files(named or ["."])
    lines = diff_lines(diff)
    if named:
        wanted = collect_files(named)
        lines = {k: v for k, v in lines.items() if k in wanted or any(k.startswith(w.rstrip("/") + "/") for w in named)}
    return lines


def sarif(findings: list[str], silenced: Iterable[tuple[str, str]] = (),
          level: Callable[[str], str] = lambda _f: "error") -> dict:
    """The findings as a SARIF 2.1.0 log, for GitHub code scanning; a silenced one carries its reason as a suppression,
    and a warn-level one (``level``) is a SARIF warning."""
    results = []
    for f, reason in [*((f, None) for f in findings), *silenced]:
        fields = finding_fields(f)
        if not fields:
            continue
        result: dict[str, Any] = {
            "ruleId": fields["rule"], "level": "warning" if level(f) == "warn" else "error",
            "message": {"text": fields["message"]},
            "locations": [{"physicalLocation": {"artifactLocation": {"uri": fields["path"]},
                                                "region": {"startLine": fields["line"]}}}]}
        if reason is not None:
            result["suppressions"] = [{"kind": "inSource", "justification": reason}]
        results.append(result)
    rules = [{"id": rid, "shortDescription": {"text": text}} for rid, text in sorted(PR_RULES_122.items())]
    return {"version": "2.1.0",
            "runs": [{"tool": {"driver": {"name": "brevio-core", "rules": rules}}, "results": results}]}


def write_atomic(path: str, text: str) -> None:
    """Write ``text`` to ``path`` through a temporary file, so a crash never leaves half a report."""
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    os.replace(tmp, path)


FIXERS_MODULE = "fixers"   # the module of the 0.3 set that declares the fixers; a build without it offers no ``--fix``
BASELINE_MODULE, MARKDOWN_MODULE = "core_baseline", "core_markdown"   # the 0.4 set; a build without them has no baseline
CONFIG_MODULE = "core_config"   # the 0.6 set's brevio-core.toml (ROADMAP E32); a build without it reads no config
Changes = dict[str, tuple[str, str, list[str]]]   # path -> (old text, new text, rule id of each fix made)
Triaged = tuple[list[str], list[tuple[str, str]], list[str]]   # shown, silenced (finding, reason), baselined


class UsageError(Exception):
    """The command cannot run as asked (exit code 2)."""


def set_module(package: str, name: str) -> Any:
    """The module ``name`` of ``package`` from a later export set, or ``None`` in a build that does not ship it."""
    top = __name__.split(".")[0]
    try:
        return importlib.import_module(f"{top}.{package}.{name}")   # a name built at run time: absent from earlier sets
    except ModuleNotFoundError as err:
        if not (err.name or "").startswith(f"{top}.{package}"):
            raise
        return None


def fixers() -> Any:
    """The fixer module of the 0.3 set, or ``None`` in a build that does not ship it."""
    return set_module("pipeline.code_rules", FIXERS_MODULE)


def baseline_tools() -> Any:
    """The baseline and ignore module of the 0.4 set, or ``None`` in a build that does not ship it."""
    return set_module("pipeline", BASELINE_MODULE)


def config_tools() -> Any:
    """The ``brevio-core.toml`` module of the 0.6 set, or ``None`` in a build that does not ship it."""
    return set_module("pipeline", CONFIG_MODULE)


def project(paths: Iterable[str] = ()) -> Any:
    """The ``brevio-core.toml`` files of the current folder, read for ``paths`` now, so a broken file is a usage error
    before anything is scanned; ``None`` in a build without config."""
    tools = config_tools()
    if tools is None:
        return None
    proj = tools.Project(".")
    try:
        proj.preload(paths)
    except tools.ConfigError as exc:
        raise UsageError(str(exc)) from exc
    return proj


def scanned_rules() -> list[str]:
    """The rule IDs ``scan`` checks, read from the rule definitions (the code engine of ``details.SCANS``)."""
    return scanned_by("code")


def line_reader() -> Callable[[str, int], str]:
    """``text_of(path, line)``: one line of a file as it is on disk, each file read once."""
    cache: dict[str, dict[int, str]] = {}

    def text_of(path: str, lno: int) -> str:
        if path not in cache:
            cache[path] = dict(_read(path))
        return cache[path].get(lno, "")
    return text_of


def commented(path: str) -> bool:
    """An ignore comment in ``path`` counts: it is a code file, not a doc that shows the comment."""
    return path.endswith(CODE_SUFFIXES)


def _code_only(lines: Numbered) -> Numbered:
    return {p: v for p, v in lines.items() if commented(p)}


def _load_baseline(tools: Any) -> Any:
    try:
        return tools.load(tools.BASELINE_PATH)
    except ValueError as exc:
        raise UsageError(str(exc)) from exc


def triage(found: list[str], fail_on: str = "new", honour_ignores: bool = True) -> Triaged:
    """``found`` split into shown, silenced and baselined findings; all shown in a build without the 0.4 set.

    ``fail_on`` ``all`` ignores the baseline. ``honour_ignores`` is false on the agent paths (hook, MCP), so an agent
    cannot silence a rule; such a finding says the comment counts in CI only."""
    tools = baseline_tools()
    if tools is None:
        return found, [], []
    base = None if fail_on == "all" else _load_baseline(tools)
    t = tools.triage(found, finding_fields, line_reader(), base, honour_ignores, commented)
    return t.shown, t.silenced, t.baselined


def new_suppressions(lines: Numbered, base: str) -> list[str]:
    """A finding for each ignore comment the change adds and each entry it adds to the baseline file."""
    tools = baseline_tools()
    found = tools.added_ignores(_code_only(lines)) + _config_changes(lines, tools.SUPPRESSION_RULE)
    after_text = _read_raw(tools.BASELINE_PATH) or ""
    if not after_text:
        return found
    before_text = _git("show", f"{_base(base)}:{tools.BASELINE_PATH}")
    try:
        before = tools.parse(before_text) if before_text.strip() else Counter()
    except ValueError:      # a broken baseline on the base holds nothing to compare with: every entry is new
        before = Counter()
    return found + tools.added_entries(before, _load_baseline(tools), after_text)


def _config_changes(lines: Numbered, rule: str) -> list[str]:
    """A finding for each ``brevio-core.toml`` a change adds or edits: a config can turn rules off or down."""
    cfg = config_tools()
    if cfg is None:
        return []
    new = _git("ls-files", "--others", "--exclude-standard", "--", f":(glob)**/{cfg.CONFIG_NAME}").splitlines()
    out = []
    for path in sorted({*(p for p in lines if cfg.is_config(p)), *new}):
        rows = lines.get(path) or _read(path)
        first = next((n for n, text in rows if text.strip() and not text.lstrip().startswith("#")), None)
        if first is not None:
            out.append(f"{path}:{first}: [{rule}] {cfg.CHANGE_MESSAGE}")
    return out


def warnings(lines: Numbered) -> list[str]:
    """Ignore comments that name an unknown rule or give no reason, and baseline entries of rules that do not exist."""
    tools = baseline_tools()
    if tools is None:
        return []
    known = frozenset(PR_RULES_122)
    return tools.ignore_warnings(_code_only(lines), known) + tools.stale_entries(_load_baseline(tools), known)


def _read_raw(path: str) -> str | None:
    try:
        if os.path.getsize(path) > MAX_BYTES:
            return None
        with open(path, encoding="utf-8", newline="") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError):
        return None


def plan_fixes(lines: Numbered) -> Changes:
    """The rewrite of each file among ``lines`` that a fixer changes; only the selected line numbers are touched.

    A file ``brevio-core.toml`` excludes is left alone, and so is a line whose fix belongs to a rule that does not run
    there."""
    fix_line, proj = fixers().fix_line, project(lines)
    out: Changes = {}
    for rel, numbered in sorted(lines.items()):
        cfg = proj.for_path(rel) if proj is not None else None
        old = None if cfg is not None and cfg.excluded else _read_raw(rel)
        if old is None:
            continue
        parts, made = old.splitlines(keepends=True), []
        for lno in sorted({n for n, _text in numbered}):
            if not 0 < lno <= len(parts):
                continue
            body = parts[lno - 1].rstrip("\r\n")
            new, rules = fix_line(rel, body)
            if rules and all(rule_status(r) != DEPRECATED and (cfg is None or cfg.runs(r)) for r in rules):
                parts[lno - 1] = new + parts[lno - 1][len(body):]
                made += rules
        if made:
            out[rel] = (old, "".join(parts), made)
    return out


def unified_diff(changes: Changes) -> str:
    """The changes as one unified diff, with ``a/`` and ``b/`` paths so it applies as a patch."""
    return "".join("".join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                                f"a/{rel}", f"b/{rel}")) for rel, (old, new, _r) in sorted(changes.items()))


def apply_fixes(changes: Changes) -> None:
    """Write each rewritten file in place, keeping its permission bits."""
    for rel, (_old, new, _rules) in changes.items():
        mode = os.stat(rel).st_mode
        write_atomic(rel, new)
        os.chmod(rel, mode)


def _failed(shown: list[str], fail_on: str, proj: Any = None) -> int:
    return 1 if blocking(shown, fail_on, proj) else 0


def _run_fix(named: list[str], diff: str | None, dry_run: bool, fail_on: str = "new", honour_ignores: bool = True) -> int:
    lines = select_lines(named, diff)
    proj = project(lines)
    changes = plan_fixes(lines)
    fixed = sum(len(r) for _o, _n, r in changes.values())
    if dry_run:     # nothing is written, so every finding remains
        print(unified_diff(changes), end="")
        print(f"brevio-core: {fixed} fix(es) in {len(changes)} file(s) would be made; nothing written", file=sys.stderr)
        return _failed(triage(scan(lines, proj), fail_on, honour_ignores)[0], fail_on, proj)
    apply_fixes(changes)
    lines = select_lines(named, diff)
    remaining = triage(scan(lines, proj), fail_on, honour_ignores)[0]
    for f in remaining:
        print(f)
    print(f"brevio-core: {fixed} fixed, {len(remaining)} remaining in {len(lines)} file(s)", file=sys.stderr)
    return _failed(remaining, fail_on, proj)


def _covered(named: list[str]) -> Callable[[str], bool]:
    """Whether a path lies under one of ``named`` (everything, when nothing or the current folder is named)."""
    roots = [_rel(p) for p in named]
    if not roots or "." in roots:
        return lambda _path: True
    return lambda path: any(path == r or path.startswith(r.rstrip("/") + "/") for r in roots)


def _run_baseline(named: list[str], diff: str | None) -> int:
    """Record the findings of the selection in the baseline. A path scan replaces the entries of the paths it covers,
    so fixed findings drop out; a diff scan only adds."""
    tools = baseline_tools()
    lines = select_lines(named, diff)
    shown, _silenced, _baselined = triage(scan(lines), "all")   # a finding silenced in the code needs no entry
    new = tools.counts(shown, finding_fields, line_reader())
    merged = tools.merge(_load_baseline(tools), new, (lambda _path: False) if diff is not None else _covered(named))
    os.makedirs(os.path.dirname(tools.BASELINE_PATH), exist_ok=True)
    write_atomic(tools.BASELINE_PATH, tools.render(merged))
    print(f"brevio-core: {sum(merged.values())} finding(s) in {tools.BASELINE_PATH}")
    return 0


def _print_findings(shown: list[str], silenced: int, baselined: int, args: argparse.Namespace) -> None:
    if getattr(args, "format", "text") == "agent":
        print("\n".join(agent_lines(shown)), end="\n" if shown else "")
        return
    if getattr(args, "format", "text") == "markdown":
        rows = [f for f in map(finding_fields, shown) if f]
        footer = upgrade_line("pr-comment", not getattr(args, "no_upgrade_line", False))
        print(set_module("pipeline", MARKDOWN_MODULE).render(rows, silenced, baselined, args.rules_url, footer), end="")
        return
    for f in shown:
        print(f)


def _run_scan(named: list[str], args: argparse.Namespace) -> int:
    fail_on = getattr(args, "fail_on", "new")
    lines = select_lines(named, args.diff)
    proj = project(lines)
    raw = scan_surface(lines, proj) if getattr(args, "surface", False) else scan(lines, proj)
    shown, silenced, baselined = triage(raw, fail_on, not args.forbid_ignores)
    if args.diff is not None and not getattr(args, "allow_new_suppressions", True):
        shown += new_suppressions(lines, args.diff)
    for w in warnings(lines) + (proj.warnings(PR_RULES_122) if proj is not None else []):
        print(f"brevio-core: warning: {w}", file=sys.stderr)
    _print_findings(shown, len(silenced), len(baselined), args)
    if args.sarif:
        write_atomic(args.sarif, json.dumps(sarif(shown, silenced, lambda f: level_of(f, proj)), indent=2))
    tail = f", {len(baselined)} baselined, {len(silenced)} silenced" if baseline_tools() is not None else ""
    warned = sum(1 for f in shown if level_of(f, proj) == "warn")
    tail += f", {warned} at warn level" if warned else ""
    print(f"brevio-core: {len(shown)} finding(s) in {len(lines)} file(s){tail}", file=sys.stderr)
    return _failed(shown, fail_on, proj)


AGENT_TOOLS = "agent_cmds"      # the module of the 0.2 set that holds the commands; named here so a build without it is detected


def agent_tools() -> tuple[dict[str, Callable[[list[str]], int]], dict[str, str]]:
    """``(commands, help)`` of the 0.2 agent tools, or two empty tables in a build that does not ship them."""
    mod = set_module("operator", AGENT_TOOLS)
    return (mod.COMMANDS, mod.HELP) if mod is not None else ({}, {})


INIT_MODULE = "core_init"       # the 0.4 set's ``init`` and ``init --undo`` (ROADMAP E22); a build without it has no ``init``
UP_MODULE = "core_up"           # the 0.6 set's ``up`` preview and upgrade line (ROADMAP E37); a build without it has neither


def init_command() -> tuple[dict[str, Callable[[list[str]], int]], dict[str, str]]:
    """``({"init": main}, {"init": help})`` in a build that ships ``init``, else two empty tables."""
    name = f"{__name__.split('.')[0]}.pipeline.{INIT_MODULE}"
    try:
        mod = importlib.import_module(name)     # built at run time: absent before the 0.4 set
    except ModuleNotFoundError as err:
        if err.name != name:
            raise
        return {}, {}
    return {"init": mod.main}, {"init": mod.HELP}


def up_tools() -> Any:
    """The ``up`` module of the 0.6 set (the preview and the upgrade line), or ``None`` in a build without it.

    It loads only when the command line is read, so its imports reach no other command."""
    return set_module("pipeline", UP_MODULE)


def up_command() -> tuple[dict[str, Callable[[list[str]], int]], dict[str, str]]:
    """``({"up": main}, {"up": help})`` in a build that ships ``up``, else two empty tables."""
    mod = up_tools()
    return ({"up": mod.main}, {"up": mod.HELP}) if mod is not None else ({}, {})


def upgrade_line(ref: str, wanted: bool = True) -> str:
    """The labelled Teams line for ``ref``, or "" when it is turned off or the build does not ship ``up``."""
    up = up_tools() if wanted else None
    return up.upgrade_line(ref) if up is not None else ""


AEO_MODULE = "core_aeo"         # the 0.6 set's ``aeo``, the AEO rubric on local pages (ADOPTION.md 0.29); absent before it
CHECK_MODULE = "core_gates"     # the 0.6 set's ``check`` pre-PR flight check
BRIEF_MODULE = "core_memory"    # the 0.6 set's ``brief`` surface rules & trap recall


def aeo_command() -> tuple[dict[str, Callable[[list[str]], int]], dict[str, str]]:
    """``({"aeo": main}, {"aeo": help})`` in a build that ships ``aeo``, else two empty tables."""
    mod = set_module("pipeline", AEO_MODULE)
    return ({"aeo": mod.main}, {"aeo": mod.HELP}) if mod is not None else ({}, {})


def check_command() -> tuple[dict[str, Callable[[list[str]], int]], dict[str, str]]:
    """``({"check": main}, {"check": help})`` in a build that ships ``check``, else two empty tables."""
    mod = set_module("pipeline.gates", CHECK_MODULE)
    return ({"check": mod.main}, {"check": mod.HELP}) if mod is not None else ({}, {})


def brief_command() -> tuple[dict[str, Callable[[list[str]], int]], dict[str, str]]:
    """``({"brief": main}, {"brief": help})`` in a build that ships ``brief``, else two empty tables."""
    mod = set_module("pipeline", BRIEF_MODULE)
    return ({"brief": mod.main}, {"brief": mod.HELP}) if mod is not None else ({}, {})


def _add_baseline_arguments(sub: Any, sc: argparse.ArgumentParser) -> None:
    """The 0.4 set: ``baseline`` and the scan flags that read it."""
    tools = baseline_tools()
    by_level = config_tools() is not None       # the 0.6 set: levels from brevio-core.toml
    sc.add_argument("--fail-on", choices=(*tools.FAIL_ON, *(("error",) if by_level else ())), default="new",
                    help="new (default): baselined findings are hidden and pass; all: ignore the baseline, any finding "
                         "fails; none: report what is not baselined and always exit 0"
                         + ("; error: like new, but only error-level findings fail (warn-level ones are reported)"
                            if by_level else "") + ". A preview rule never fails")
    sc.add_argument("--allow-new-suppressions", action="store_true",
                    help="with --diff: do not report the ignore comments and baseline entries the change adds "
                         "(for a change a person has reviewed)")
    if set_module("pipeline", MARKDOWN_MODULE) is not None:
        sc.add_argument("--format", choices=("text", "markdown", "agent"), default="text",
                        help="how to print the findings (agent: one short line each with a fix hint, grouped by rule, "
                             f"at most {AGENT_MAX})")
        sc.add_argument("--rules-url", default="", metavar="BASE", help="with --format markdown: link each rule ID to BASE<ID>")
        if up_tools() is not None:
            sc.add_argument("--no-upgrade-line", action="store_true",
                            help="with --format markdown: leave out the closing Teams line (the Action's footer: false)")
    bl = sub.add_parser("baseline", help=f"record the current findings in {tools.BASELINE_PATH}, so scan reports only new ones")
    bl.add_argument("paths", nargs="*", help="files or folders (default: the current folder)")
    bl.add_argument("--diff", nargs="?", const="", default=None, metavar="BASE",
                    help="record only the findings on the lines added against BASE (default origin/main)")


def parser(tools: Iterable[str], tool_help: dict[str, str]) -> argparse.ArgumentParser:
    """The ``brevio-core`` argument parser; the commands and flags of later sets appear when the build ships them."""
    ap = argparse.ArgumentParser(prog="brevio-core", description="Zero-token code rules for coding-agent mistakes.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in tools:      # listed for ``--help``; the command itself reads the rest of the line
        sub.add_parser(name, help=tool_help[name], add_help=False)
    sc = sub.add_parser("scan", help=f"scan files, folders or a diff against the {len(scanned_rules())} rules the scanner "
                                     f"checks (of {len(PR_RULES_122)} documented)")
    sc.add_argument("paths", nargs="*", help="files or folders to scan (default: the current folder)")
    sc.add_argument("--file", action="append", default=[], metavar="PATH", help="a file to scan (repeatable)")
    sc.add_argument("--diff", nargs="?", const="", default=None, metavar="BASE",
                    help="scan only the lines added against BASE (default origin/main)")
    sc.add_argument("--sarif", metavar="FILE", help="also write the findings to FILE as SARIF")
    sc.add_argument("--forbid-ignores", action="store_true",
                    help="never honour an ignore comment (the agent hook runs with this, so an agent cannot silence a rule)")
    sc.add_argument("--surface", action="store_true",
                    help="also run the 9 surface-scoped rules (UI blur, SSR reveal, GTM deferral, webhook HMAC, integer cents, self-mocking tests, weak assertions, contract purity, package imports)")
    if fixers() is not None:
        sc.add_argument("--fix", action="store_true", help="rewrite in place what a rule has one correct fix for, then scan again")
        sc.add_argument("--dry-run", action="store_true", help="with --fix: print the fixes as a unified diff and write nothing")
    if baseline_tools() is not None:
        _add_baseline_arguments(sub, sc)
    cfg = config_tools()
    if cfg is not None:
        cf = sub.add_parser("config", help=f"show the {cfg.CONFIG_NAME} settings that apply to a file or folder")
        cf.add_argument("path", nargs="?", default=".", help="the file or folder (default: the current folder)")
        cf.add_argument("--json", action="store_true", help="print it as JSON")
    lk = sub.add_parser("leaks", help="check a folder for stray URLs, emails and paths that should not be public")
    lk.add_argument("root", nargs="?", default=".", help="the folder to check (default: the current folder)")
    return ap


def _run_config(path: str, as_json: bool) -> int:
    """``brevio-core config``: the effective settings for ``path``, with the files they come from."""
    if not os.path.exists(path):
        raise UsageError(f"no such file or folder: {path}")
    rel = _rel(path)
    proj = project([rel])
    for w in proj.warnings(PR_RULES_122):
        print(f"brevio-core: warning: {w}", file=sys.stderr)
    desc = config_tools().describe(proj, rel, scanned_rules(), rule_status, os.path.isdir(path))
    print(json.dumps(desc, indent=2) if as_json else config_tools().render(desc), end="\n" if as_json else "")
    return 0


def _dispatch(args: argparse.Namespace) -> int:
    if args.cmd == "config":
        return _run_config(args.path, args.json)
    named = [*args.paths, *getattr(args, "file", [])]
    missing = [p for p in named if not os.path.exists(p)]
    if missing:
        raise UsageError(f"no such file or folder: {', '.join(missing)}")
    if args.cmd == "baseline":
        return _run_baseline(named, args.diff)
    if getattr(args, "dry_run", False) and not args.fix:
        raise UsageError("--dry-run needs --fix")
    if getattr(args, "fix", False):
        if getattr(args, "format", "text") != "text":
            raise UsageError("--fix prints text only; leave out --format")
        return _run_fix(named, args.diff, args.dry_run, getattr(args, "fail_on", "new"), not args.forbid_ignores)
    return _run_scan(named, args)


def line_commands() -> tuple[dict[str, Callable[[list[str]], int]], dict[str, str]]:
    """``(commands, help)`` of every command that reads the rest of its line itself, in the order ``--help`` lists them:
    the agent tools, ``init``, ``aeo``, ``check``, ``brief`` and ``up``, each where the build ships it."""
    tools, tool_help = agent_tools()
    for more, more_help in (init_command(), aeo_command(), check_command(), brief_command(), up_command()):
        tools, tool_help = {**tools, **more}, {**tool_help, **more_help}
    return tools, tool_help


def _interactive_entry(tools: dict[str, Callable[[list[str]], int]]) -> int:
    """Zero-argument interactive TTY dispatcher: onboarding wizard on first run, quick-action menu thereafter."""
    code, top = _git("rev-parse", "--show-toplevel")
    root = os.path.normpath(top.strip()) if not code and top.strip() else "."
    if "init" in tools and not os.path.isfile(os.path.join(root, ".brevio", "init.json")):
        return tools["init"](["--wizard"])
    print("brevio-core interactive quick actions:\n"
          "  [1] Scan uncommitted changes (scan --diff HEAD) [default]\n"
          "  [2] Run Pre-PR Flight Check (check)\n"
          "  [3] Compile last fix into a guard (learn)\n"
          "  [4] Run interactive setup wizard (init --wizard)")
    try:
        choice = input("Choose [1/2/3/4] (Enter for 1): ").strip()
    except EOFError:
        choice = "1"
    if choice == "2" and "check" in tools:
        return tools["check"]([])
    if choice == "3" and "learn" in tools:
        return tools["learn"]([])
    if choice == "4" and "init" in tools:
        return tools["init"](["--wizard"])
    return main(["scan", "--diff", "HEAD"] if has_head() else ["scan"])


def main(argv: list[str] | None = None) -> int:
    tools, tool_help = line_commands()
    ap = parser(tools, tool_help)
    line = sys.argv[1:] if argv is None else argv
    if not line and sys.stdin.isatty() and sys.stdout.isatty():
        return _interactive_entry(tools)
    if line and line[0] in tools:
        return tools[line[0]](line[1:])
    args = ap.parse_args(line)
    if args.cmd == "leaks":
        problems = leak_scan.scan_tree(args.root)
        print("\n".join(problems))
        return 1 if problems else 0
    try:
        return _dispatch(args)
    except UsageError as exc:
        print(f"brevio-core: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
