"""Baseline, inline ignores and the new-suppression check of ``brevio-core scan`` (ROADMAP E20, E21, the 0.4 set, 2026-11-05).

The baseline (``.brevio/baseline.json``) records the findings a project already has, so a scan reports only new ones.
An entry is keyed by path, rule ID and the sha256 of the stripped line text, never by line number, so a line that
moves stays baselined. The file holds one entry per line, sorted, so two branches that add entries merge cleanly.

An ignore comment (``brevio-core: ignore <rule ID> -- reason``) in a code file, on the line or the line above, silences
that rule there. Without a reason it does not count. In other files (docs that show the comment) it is plain text. Agents cannot silence the gate: the agent hook and the MCP tools do not honour ignores, and a diff
scan reports a new ignore comment or a new baseline entry as a finding a person has to review (plan review,
2026-11-05). Standard library only, so it exports with the CLI.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable, Collection, Iterable
from typing import Any, NamedTuple

BASELINE_PATH = ".brevio/baseline.json"
FORMAT_VERSION = 1
FAIL_ON = ("new", "all", "none")
SUPPRESSION_RULE = "suppression"
SUPPRESSION_MESSAGE = "new suppression: needs a human review"
CI_ONLY = " (an ignore comment counts in CI only, not here)"
_ID = r"[A-Za-z]+\d+(?:\.\d+)*"
_DIRECTIVE = re.compile(rf"brevio-core:\s*ignore\s+(?P<rules>{_ID}(?:[\s,]+{_ID})*)(?P<rest>.*)$")
_CLOSER = re.compile(r"(?:\*/\s*\}?|-->|%\}|\}\})\s*$")     # the end of a /* */, <!-- -->, {/* */} or template comment

Key = tuple[str, str, str]              # path, rule ID, sha256 of the stripped line
Numbered = dict[str, list[tuple[int, str]]]
TextOf = Callable[[str, int], str]      # the text of line ``n`` of a file; "" when there is none
FieldsOf = Callable[[str], "dict[str, Any] | None"]


class Directive(NamedTuple):
    rules: frozenset[str]
    reason: str             # empty: the comment does not count


class Triage(NamedTuple):
    shown: list[str]                    # reported, and they fail the scan
    silenced: list[tuple[str, str]]     # (finding, reason)
    baselined: list[str]


def directive(text: str) -> Directive | None:
    """The ignore comment on one line, or ``None`` when it has none."""
    m = _DIRECTIVE.search(text)
    if not m:
        return None
    rest = _CLOSER.sub("", m["rest"]).strip()
    reason = rest[2:].strip() if rest.startswith("--") else ""
    return Directive(frozenset(r.upper() for r in re.split(r"[\s,]+", m["rules"].strip())), reason)


def ignore_reason(rule: str, *texts: str) -> str:
    """The reason the first ignore comment in ``texts`` that names ``rule`` gives; "" when none silences it."""
    for text in texts:
        d = directive(text)
        if d and d.reason and rule.upper() in d.rules:
            return d.reason
    return ""


def line_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def key(fields: dict[str, Any], text_of: TextOf) -> Key:
    return str(fields["path"]), str(fields["rule"]), line_hash(text_of(str(fields["path"]), int(fields["line"])))


def triage(findings: Iterable[str], fields_of: FieldsOf, text_of: TextOf, baseline: Counter[Key] | None,
           honour_ignores: bool = True, commented: Callable[[str], bool] = lambda _path: True) -> Triage:
    """Split ``findings`` into shown, silenced and baselined ones (``baseline`` ``None``: every finding counts).

    ``commented(path)`` says whether an ignore comment in that file is one (a code file) rather than text."""
    budget: Counter[Key] = Counter(baseline or {})
    out = Triage([], [], [])
    for finding in findings:
        fields = fields_of(finding)
        if fields is None:
            out.shown.append(finding)
            continue
        path, lno = str(fields["path"]), int(fields["line"])
        reason = ignore_reason(str(fields["rule"]), text_of(path, lno), text_of(path, lno - 1) if lno > 1 else "") \
            if commented(path) else ""
        if reason and honour_ignores:
            out.silenced.append((finding, reason))
            continue
        k = key(fields, text_of)
        if budget[k] > 0:
            budget[k] -= 1
            out.baselined.append(finding)
            continue
        out.shown.append(finding + CI_ONLY if reason else finding)
    return out


def counts(findings: Iterable[str], fields_of: FieldsOf, text_of: TextOf) -> Counter[Key]:
    """How often each key occurs among ``findings``: what a baseline records for them."""
    return Counter(key(f, text_of) for f in map(fields_of, findings) if f is not None)


def merge(old: Counter[Key], new: Counter[Key], replaced: Callable[[str], bool]) -> Counter[Key]:
    """``old`` without the paths ``replaced`` names, plus ``new`` (the larger count wins where both hold a key)."""
    out = Counter({k: n for k, n in old.items() if not replaced(k[0])})
    for k, n in new.items():
        out[k] = max(out[k], n)
    return out


def render(entries: Counter[Key]) -> str:
    """The baseline file: sorted, one entry per line, the same text for the same entries."""
    rows = [json.dumps({"path": p, "rule": r, "line_sha256": h, "count": n}, ensure_ascii=False)
            for (p, r, h), n in sorted(entries.items()) if n > 0]
    body = "".join(f"    {row}{',' if i < len(rows) - 1 else ''}\n" for i, row in enumerate(rows))
    return f'{{\n  "version": {FORMAT_VERSION},\n  "findings": [\n{body}  ]\n}}\n'


def parse(text: str) -> Counter[Key]:
    """The entries of a baseline file; ``ValueError`` when it is not one."""
    doc = json.loads(text)
    rows = doc.get("findings") if isinstance(doc, dict) else None
    if not isinstance(rows, list):
        raise ValueError("not a brevio-core baseline (no findings list)")
    out: Counter[Key] = Counter()
    for row in rows:
        fields = [row.get(k) for k in ("path", "rule", "line_sha256")] if isinstance(row, dict) else []
        n = row.get("count", 1) if isinstance(row, dict) else 0
        texts = [f for f in fields if isinstance(f, str)]
        if len(texts) != 3 or not isinstance(n, int) or isinstance(n, bool) or n < 1:
            raise ValueError(f"not a brevio-core baseline entry: {row!r}")
        out[(texts[0], texts[1], texts[2])] += n
    return out


def load(path: str = BASELINE_PATH) -> Counter[Key]:
    """The baseline at ``path``; empty when there is none, ``ValueError`` when it cannot be read."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except FileNotFoundError:
        return Counter()
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    try:
        return parse(text)
    except ValueError as exc:
        raise ValueError(f"{path}: {exc}") from exc


def ignore_warnings(lines: Numbered, known: Collection[str]) -> list[str]:
    """A warning for each ignore comment among ``lines`` that names an unknown rule or gives no reason."""
    out: list[str] = []
    for path, numbered in sorted(lines.items()):
        for lno, text in numbered:
            d = directive(text)
            if d is None:
                continue
            out += [f"{path}:{lno}: the ignore comment names {r}, which is not a rule" for r in sorted(d.rules - set(known))]
            if not d.reason:
                out.append(f"{path}:{lno}: the ignore comment has no '-- reason', so it does not count")
    return out


def stale_entries(entries: Counter[Key], known: Collection[str]) -> list[str]:
    """A warning for each baseline entry whose rule ID is not a rule any more."""
    return [f"{BASELINE_PATH}: the entry for {p} names {r}, which is not a rule" for (p, r, _h) in sorted(entries) if r not in known]


def suppression(path: str, lno: int, detail: str = "") -> str:
    return f"{path}:{lno}: [{SUPPRESSION_RULE}] {SUPPRESSION_MESSAGE}{detail}"


def added_ignores(lines: Numbered) -> list[str]:
    """A finding for each line among ``lines`` (the lines a change adds) that holds an ignore comment which counts."""
    return [suppression(path, lno) for path, numbered in sorted(lines.items())
            for lno, text in numbered if (d := directive(text)) and d.reason]


def added_entries(before: Counter[Key], after: Counter[Key], after_text: str) -> list[str]:
    """A finding for each baseline entry ``after`` holds that ``before`` (the base's baseline) did not."""
    rows = after_text.splitlines()
    out = []
    for (path, rule, digest), n in sorted(after.items()):
        if n > before.get((path, rule, digest), 0):
            lno = next((i for i, row in enumerate(rows, 1) if digest in row), 1)
            out.append(suppression(BASELINE_PATH, lno, f" ({rule} in {path})"))
    return out
