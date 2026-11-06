"""``brevio-core aeo``: the AEO rubric on a folder of built pages, printed as a scorecard (ADOPTION.md 0.29, 2026-11-05).

It scores how well answer engines can find, read and cite a site, with the exported rubric (``geo_audit.rubric``) and
robots parser (``geo_audit.robots``). It reads local files only: every ``.html`` page under a folder (or one page), and
``robots.txt``, ``llms.txt``, ``skill.md`` and ``.well-known/agent-card.json`` at the folder's root. It fetches
nothing, so a URL is refused with a hint to save the page first or to use the hosted check (OSS.md section 2: the
rubric is a second, separate command, not the headline). The exit code is 0 when every page meets ``--min``, 1 when
one does not and 2 for a usage error. Standard library only (the 0.6 set).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

from brevio.growth.geo_audit import rubric
from brevio.pipeline.core_markdown import escape

HELP = "score a folder of built HTML pages, with its robots.txt and llms.txt, against the AEO rubric"
HOSTED = "https://brevio.pro"
PAGE_SUFFIXES = (".html", ".htm")
SKIP_DIRS = frozenset({"node_modules"})          # plus every hidden folder
# The site files the rubric reads, by the keyword ``rubric.score_page`` takes them under.
SITE_FILES = {"robots_txt": "robots.txt", "llms_txt": "llms.txt", "skill_md": "skill.md",
              "agent_card": ".well-known/agent-card.json"}
FORMATS = ("text", "markdown", "json")
_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*://", re.I)
_HOST = re.compile(r"^(?:[a-z0-9-]+\.)+([a-z]{2,})(?::\d+)?(?:/.*)?$", re.I)
_FILE_WORDS = frozenset({"html", "htm", "md", "txt", "json", "xml"})


class UsageError(Exception):
    """The command cannot run as asked (exit code 2)."""


def is_url(arg: str) -> bool:
    """``arg`` names a web address, not a local path: it has a scheme, or it is a host name that is not on disk."""
    if _SCHEME.match(arg):
        return True
    m = _HOST.match(arg)
    return bool(m) and not os.path.exists(arg) and m.group(1).lower() not in _FILE_WORDS


def refusal(arg: str) -> str:
    """What ``aeo`` says when it is given a URL: it reads local files only."""
    return (f"aeo reads local files only and does not fetch {arg}. Save the built page first (your browser's "
            "\"Save page as\", or your site's build output), put its robots.txt and llms.txt beside it, and run "
            f"`brevio-core aeo` on that folder. Or use the hosted check at {HOSTED}.")


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
        return ""


def pages(root: str) -> list[str]:
    """Every ``.html`` page under ``root`` (hidden folders and ``node_modules`` left out), relative, sorted."""
    found: list[str] = []
    for dirpath, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS)
        found += [os.path.relpath(os.path.join(dirpath, n), root).replace(os.sep, "/")
                  for n in names if n.lower().endswith(PAGE_SUFFIXES)]
    return sorted(found)


def site_files(root: str) -> dict[str, str]:
    """The text of each site file at ``root``; an empty string for one that is missing."""
    return {key: _read(os.path.join(root, rel)) for key, rel in SITE_FILES.items()}


def has_md_mirror(root: str, rel: str) -> bool:
    """A Markdown copy of the page sits beside it: ``page.md`` or ``page.html.md``."""
    path = os.path.join(root, rel)
    return os.path.isfile(os.path.splitext(path)[0] + ".md") or os.path.isfile(path + ".md")


def score_page(root: str, rel: str, site: dict[str, str]) -> dict:
    """The rubric's scorecard of one page, trimmed to what the report prints."""
    card = rubric.score_page(html=_read(os.path.join(root, rel)), url=rel, has_md_mirror=has_md_mirror(root, rel), **site)
    return {"path": rel, "score": card["score"], "grade": card["grade"],
            "pillars": {name: p["score"] for name, p in card["pillars"].items()}, "gaps": card["gaps"]}


def scorecard(target: str, min_score: int) -> dict:
    """Score every page of ``target`` (a folder, or one page whose folder holds the site files)."""
    if is_url(target):
        raise UsageError(refusal(target))
    if not os.path.exists(target):
        raise UsageError(f"no such file or folder: {target}")
    if os.path.isdir(target):
        root, rels = target, pages(target)
    else:
        if not target.lower().endswith(PAGE_SUFFIXES):
            raise UsageError(f"{target} is not an .html page")
        root, rels = os.path.dirname(target) or ".", [os.path.basename(target)]
    if not rels:
        raise UsageError(f"no .html page under {target}; point it at your site's build output")
    site = site_files(root)
    scored = sorted((score_page(root, rel, site) for rel in rels), key=lambda p: (p["score"], p["path"]))
    robots = rubric.check_robots_txt(site["robots_txt"])
    below = [p["path"] for p in scored if p["score"] < min_score]
    return {"target": target, "min": min_score, "ok": not below, "lowest": scored[0]["score"], "below_min": below,
            "site": {"robots_txt": robots["present"], "blocked_bots": robots["blocked_bots"],
                     **{key: bool(site[key].strip()) for key in ("llms_txt", "skill_md", "agent_card")}},
            "pages": scored}


def _site_lines(card: dict) -> list[str]:
    s = card["site"]
    blocked = ", ".join(s["blocked_bots"])
    robots = ("missing" if not s["robots_txt"] else f"blocks {blocked}" if blocked else "present, blocks no AI crawler")
    return [f"robots.txt: {robots}"] + [f"{SITE_FILES[k]}: {'present' if s[k] else 'missing'}"
                                         for k in ("llms_txt", "skill_md", "agent_card")]


def _verdict(card: dict) -> str:
    n = len(card["pages"])
    if card["ok"]:
        return f"{n} page(s), lowest score {card['lowest']}, all at or above --min {card['min']}"
    return f"{n} page(s), lowest score {card['lowest']}: {len(card['below_min'])} below --min {card['min']}"


def render_text(card: dict) -> str:
    out = [f"brevio-core aeo: {card['target']}", *(f"  {line}" for line in _site_lines(card)), ""]
    for p in card["pages"]:
        out.append(f"{p['score']:>3} {p['grade']}  {p['path']}")
        out += [f"      - {gap}" for gap in p["gaps"]]
    return "\n".join([*out, "", _verdict(card)]) + "\n"


def render_markdown(card: dict) -> str:
    """A heading, the site files, and a table of page, score, grade and gaps, escaped like the scan's report."""
    out = [f"### brevio-core aeo: {escape(card['target'])}", "", *(f"- {escape(line)}" for line in _site_lines(card)), "",
           "| Page | Score | Grade | Gaps |", "| --- | --- | --- | --- |"]
    out += [f"| {escape(p['path'])} | {p['score']} | {p['grade']} | {escape('; '.join(p['gaps'])) or 'none'} |"
            for p in card["pages"]]
    return "\n".join([*out, "", _verdict(card) + "."]) + "\n"


def _min_score(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a whole number: {text}") from None
    if not 0 <= value <= 100:
        raise argparse.ArgumentTypeError("must be from 0 to 100")
    return value


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="brevio-core aeo", description=HELP + ". It reads local files only; save a page "
                                 "before you score it.")
    ap.add_argument("target", help="a folder of built pages (with robots.txt and llms.txt at its root), or one .html page")
    ap.add_argument("--min", dest="min_score", type=_min_score, default=0, metavar="SCORE",
                    help="exit 1 when a page scores below SCORE, out of 100 (default 0: report only)")
    ap.add_argument("--format", choices=FORMATS, default="text", help="how to print the scorecard")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(sys.argv[1:] if argv is None else argv)
    try:
        card = scorecard(args.target, args.min_score)
    except UsageError as exc:
        print(f"brevio-core: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(card, indent=2))
    else:
        print(render_markdown(card) if args.format == "markdown" else render_text(card), end="")
    return 0 if card["ok"] else 1
