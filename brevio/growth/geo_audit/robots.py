"""The one robots.txt parser behind every GEO audit view of crawler access.

Three readers used to carry their own parse of the same file. They now share ``directives`` (the
line tokenizer) and keep their own answers: ``parse_robots`` / ``bot_blocked`` (grouped rules, the
scorecard), ``blocked_bots`` (which listed crawlers a whole-site ``Disallow: /`` shuts out, the
rubric) and ``ai_rules`` (blocked | allowed | not_specified per crawler, the competitor probe).
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Iterator

_FULL_DISALLOW_RE = re.compile(r"^\s*disallow:\s*/\s*(?:#.*)?$", re.M)


def directives(text: str) -> Iterator[tuple[str, str]]:
    """Every ``key: value`` line of a robots.txt as ``(lower key, value)``, comments stripped."""
    for raw in (text or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" in line:
            key, _, val = line.partition(":")
            yield key.strip().lower(), val.strip()


def parse_robots(text: str) -> dict[str, list[tuple[str, str]]]:
    """Minimal robots.txt parser → {user_agent_lower: [(directive, path), ...]}.

    Consecutive `User-agent:` lines share the rules that follow, so a block like
    `User-agent: GPTBot\\nUser-agent: CCBot\\nDisallow: /` groups correctly.
    """
    groups: dict[str, list[tuple[str, str]]] = {}
    pending: list[str] = []
    current: list[tuple[str, str]] = []
    for key, val in directives(text):
        if key == "user-agent":
            ua = val.lower()
            if ua not in pending:  # a new UA after rules starts a fresh block
                if not pending or current:
                    pending = []
                pending.append(ua)
            groups.setdefault(ua, [])
            current = groups[ua]
        elif key in ("disallow", "allow"):
            for ua in pending:
                groups.setdefault(ua, []).append((key, val))
            current = groups[pending[-1]] if pending else current
    return groups


def bot_blocked(groups: dict[str, list[tuple[str, str]]], bot: str) -> bool:
    """True if `bot` (or the `*` group it inherits from) is blanket-disallowed."""
    rules = groups.get(bot.lower())
    if rules is None:
        rules = groups.get("*")
    if not rules:
        return False
    disallow_all = any(d == "disallow" and p == "/" for d, p in rules)
    allow_all = any(d == "allow" and p == "/" for d, p in rules)
    return disallow_all and not allow_all


def blocked_bots(text: str, crawlers: Iterable[str]) -> list[str]:
    """The ``crawlers`` a whole-site ``Disallow: /`` (their own group or ``*``) shuts out, in
    first-blocked order; a later ``Allow: /`` for the crawler by name lifts it again."""
    crawlers = tuple(crawlers)
    blocked: list[str] = []
    agents: list[str] = []
    for key, val in directives(text):
        if key == "user-agent":
            agents = [val]
            continue
        if val != "/":
            continue
        low = {a.lower() for a in agents}
        if key == "disallow":
            for bot in crawlers:
                if (bot.lower() in low or "*" in low) and bot not in blocked:
                    blocked.append(bot)
        elif key == "allow":
            for bot in crawlers:
                if bot.lower() in low and bot in blocked:
                    blocked.remove(bot)
    return blocked


def ai_rules(robots_txt: str, bots: Iterable[str]) -> dict:
    """``{bot: blocked | allowed | not_specified}``. Blocked only on a whole-site ``Disallow: /``: a
    substring test read ``Disallow: /admin`` as a full block (code review 2026-10-22, plan-llm 14)."""
    txt = (robots_txt or "").lower()
    rules = {}
    for bot in bots:
        if f"user-agent: {bot}" in txt:
            part = txt.split(f"user-agent: {bot}", 1)[1].split("user-agent:")[0]
            rules[bot] = "blocked" if _FULL_DISALLOW_RE.search(part) else "allowed"
        else:
            rules[bot] = "not_specified"
    return rules
