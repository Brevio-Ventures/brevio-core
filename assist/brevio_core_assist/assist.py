"""``brevio-core-assist``: explain a brevio-core finding, or suggest a fix, with a model endpoint and key of your own.

Optional and separate from brevio-core, which never imports it. It stays off until it is installed and these are set:

    BREVIO_ASSIST_URL      the full URL of the endpoint (https; plain http only to this machine)
    BREVIO_ASSIST_FORMAT   ``chat`` (a chat-completions request) or ``messages`` (a messages request)
    BREVIO_ASSIST_MODEL    the model name the endpoint expects
    BREVIO_ASSIST_KEY_ENV  the name of the environment variable that holds your key
    BREVIO_ASSIST_HEADER   optional: one more header, ``Name: value`` (some endpoints want a version header)

There is no default endpoint and no default model. Each command makes one request, holding the rule's text and the
one source line of the finding: no path, no other line. It prints that request first and sends it only when you
answer yes (``--yes`` skips the question; ``--dry-run`` prints it and stops). The key is read from the variable you
name and is never printed. Standard library only: the request goes through ``urllib``.

Exit codes: 0 answered (or the dry run printed the request); 1 the endpoint failed; 2 usage; 3 off (not configured)
or not sent (you said no).
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any, NamedTuple

from brevio.pipeline.code_rules import PR_RULES_122
from brevio.pipeline.code_rules.details import DETAILS

EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_OFF = 0, 1, 2, 3
FORMATS = ("chat", "messages")
FINDING = re.compile(r"^\s*(?P<path>.+?):(?P<line>\d+): \[(?P<rule>R\d+\.\d+)\]")
MAX_TOKENS = 400
MAX_LINE = 2000          # a minified file's one line is cut here, so a finding never sends a whole bundle
TIMEOUT_S = 60
SYSTEM = ("You review one line of code against one rule of a static checker. Answer briefly, about that line only, "
          "in plain words.")
ASK = {
    "explain": "Explain why this line breaks the rule and what can go wrong because of it.",
    "suggest-fix": "Suggest a corrected version of this line that satisfies the rule and keeps what the line does. "
                   "Give the corrected line first, then one sentence on why.",
    "verify-fix": "Return only the corrected single line of code that fixes this rule violation while preserving behavior (no markdown fences, no commentary).",
}


class Config(NamedTuple):
    url: str
    fmt: str
    model: str
    key_env: str
    header: str


class Finding(NamedTuple):
    path: str
    line: int
    rule: str


class AssistError(RuntimeError):
    """The endpoint could not be reached or answered without text; the message never holds the key."""


def config(env: Mapping[str, str], args: argparse.Namespace) -> Config:
    """The settings: a flag wins over its environment variable."""
    def pick(flag: str | None, name: str) -> str:
        return (flag if flag is not None else env.get(name, "")).strip()
    return Config(url=pick(args.url, "BREVIO_ASSIST_URL"), fmt=pick(args.format, "BREVIO_ASSIST_FORMAT").lower(),
                  model=pick(args.model, "BREVIO_ASSIST_MODEL"), key_env=pick(args.key_env, "BREVIO_ASSIST_KEY_ENV"),
                  header=env.get("BREVIO_ASSIST_HEADER", "").strip())


def loopback(host: str | None) -> bool:
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def problems(cfg: Config, env: Mapping[str, str]) -> list[str]:
    """What keeps the assistant off, in plain words; empty when it may run."""
    out = []
    parts = urllib.parse.urlsplit(cfg.url)
    if not cfg.url:
        out.append("set BREVIO_ASSIST_URL (or --url) to your endpoint's full URL")
    elif parts.scheme != "https" and not (parts.scheme == "http" and loopback(parts.hostname)):
        out.append("the URL must use https (plain http only to this machine), so the key never travels in clear")
    if cfg.fmt not in FORMATS:
        out.append(f"set BREVIO_ASSIST_FORMAT (or --format) to {' or '.join(FORMATS)}")
    if not cfg.model:
        out.append("set BREVIO_ASSIST_MODEL (or --model) to the model name your endpoint expects")
    if not cfg.key_env:
        out.append("set BREVIO_ASSIST_KEY_ENV (or --key-env) to the name of the variable that holds your key")
    elif not env.get(cfg.key_env, "").strip():
        out.append(f"the variable {cfg.key_env} holds no key")
    if cfg.header and ":" not in cfg.header:
        out.append("BREVIO_ASSIST_HEADER must read 'Name: value'")
    return out


def parse_finding(text: str) -> Finding:
    """A finding as ``brevio-core scan`` prints it: ``path:line: [R9.2] message``."""
    m = FINDING.match(text)
    if not m:
        raise ValueError(f"not a brevio-core finding (want 'path:line: [Rn.n] message'): {text[:120]!r}")
    if m.group("rule") not in PR_RULES_122:
        raise ValueError(f"unknown rule {m.group('rule')}")
    return Finding(m.group("path"), int(m.group("line")), m.group("rule"))


def rule_text(rule: str) -> str:
    """The rule as its page states it: what it catches and why."""
    detail = DETAILS.get(rule)
    return f"{rule}: {PR_RULES_122[rule]}" + (f"\nWhy: {detail.why}" if detail else "")


def source_line(root: str, finding: Finding) -> str:
    """The one line the finding points at, read from the file under ``root``."""
    path = finding.path if os.path.isabs(finding.path) else os.path.join(root, finding.path)
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for number, line in enumerate(fh, 1):
                if number == finding.line:
                    return line.rstrip("\r\n")[:MAX_LINE]
    except OSError as exc:
        raise ValueError(f"cannot read {finding.path}: {exc.strerror}") from exc
    raise ValueError(f"{finding.path} has no line {finding.line}")


def request_body(cfg: Config, command: str, rule: str, line: str) -> dict[str, Any]:
    """The whole request body: the question, the rule's text and the line; nothing else."""
    text = f"{ASK[command]}\n\nRule {rule}\n\nLine:\n{line}"
    if cfg.fmt == "messages":
        return {"model": cfg.model, "max_tokens": MAX_TOKENS, "system": SYSTEM,
                "messages": [{"role": "user", "content": text}]}
    return {"model": cfg.model, "max_tokens": MAX_TOKENS,
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}]}


def headers(cfg: Config, key: str) -> dict[str, str]:
    out = {"Content-Type": "application/json"}
    if cfg.fmt == "messages":
        out["x-api-key"] = key
    else:
        out["Authorization"] = f"Bearer {key}"
    if cfg.header:
        name, value = cfg.header.split(":", 1)
        out[name.strip()] = value.strip()
    return out


def answer_text(fmt: str, data: Any) -> str:
    """The reply's text, read in the shape of ``fmt``."""
    try:
        if fmt == "messages":
            text = "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
        else:
            text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise AssistError(f"the endpoint's answer is not in the {fmt} shape") from exc
    if not isinstance(text, str) or not text.strip():
        raise AssistError("the endpoint answered with no text")
    return text.strip()


def send(cfg: Config, key: str, body: dict[str, Any]) -> str:
    """POST ``body`` to the endpoint and return the reply's text. A loopback endpoint never goes through a proxy."""
    req = urllib.request.Request(cfg.url, data=json.dumps(body).encode("utf-8"), headers=headers(cfg, key),
                                 method="POST")
    handlers = [urllib.request.ProxyHandler({})] if loopback(urllib.parse.urlsplit(cfg.url).hostname) else []
    try:
        with urllib.request.build_opener(*handlers).open(req, timeout=TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise AssistError(f"the endpoint answered HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise AssistError(f"could not reach the endpoint: {exc.reason}") from exc
    except (OSError, ValueError) as exc:
        raise AssistError(f"no usable answer from the endpoint: {type(exc).__name__}") from exc
    return answer_text(cfg.fmt, data)


def preview(cfg: Config, body: dict[str, Any]) -> str:
    names = ", ".join(sorted(headers(cfg, "-")))
    return (f"brevio-core-assist will POST this body to {cfg.url}\n"
            f"(headers: {names}; the key comes from {cfg.key_env} and is not shown)\n\n"
            f"{json.dumps(body, indent=2)}\n")


def consent(ask: Callable[[str], str] | None) -> bool:
    if ask is None:
        print("not sent: there is no terminal to ask; pass --yes to send it", file=sys.stderr)
        return False
    return ask("Send it? [y/N] ").strip().lower() in ("y", "yes")


def verify_replacement(finding: Finding, reply_text: str) -> tuple[str, bool]:
    """Extract candidate line from reply_text and test if it resolves finding.rule across all scanned rules."""
    from brevio.pipeline import core_cli

    candidate = ""
    in_fence = False
    fenced_lines: list[str] = []
    for raw in reply_text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("```"):
            if in_fence:
                break
            in_fence = True
            continue
        if in_fence and stripped:
            fenced_lines.append(raw.rstrip("\r\n"))

    if fenced_lines:
        candidate = fenced_lines[0]
    else:
        for raw in reply_text.splitlines():
            stripped = raw.strip()
            if stripped.startswith("```"):
                continue
            if stripped:
                candidate = raw.rstrip("\r\n")
                break

    if not candidate.strip():
        return (candidate, False)

    hits = core_cli.scan_surface({finding.path: [(finding.line, candidate)]})
    return (candidate, not any(f"[{finding.rule}]" in f for f in hits))


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="brevio-core-assist", description="Explain a brevio-core finding, or suggest a "
                                 "fix, with your own endpoint and key. Off until configured; asks before it sends.")
    sub = ap.add_subparsers(dest="command", required=True)
    for name, text in (("explain", "why the line breaks the rule"),
                       ("suggest-fix", "a corrected line"),
                       ("verify-fix", "a corrected line verified against the rule scanner")):
        p = sub.add_parser(name, help=text)
        p.add_argument("finding", help="one finding line as brevio-core scan prints it: 'path:line: [Rn.n] message'")
        p.add_argument("--root", default=".", help="the folder the finding's path is relative to (default: here)")
        p.add_argument("--yes", action="store_true", help="send without asking (the request is still printed)")
        p.add_argument("--dry-run", action="store_true", help="print the request and send nothing")
        p.add_argument("--url", help="the endpoint URL (default: BREVIO_ASSIST_URL)")
        p.add_argument("--format", choices=FORMATS, help="the request shape (default: BREVIO_ASSIST_FORMAT)")
        p.add_argument("--model", help="the model name (default: BREVIO_ASSIST_MODEL)")
        p.add_argument("--key-env", help="the variable holding your key (default: BREVIO_ASSIST_KEY_ENV)")
    return ap


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None,
         ask: Callable[[str], str] | None = None) -> int:
    args = _parser().parse_args(argv)
    env = os.environ if env is None else env
    cfg = config(env, args)
    off = problems(cfg, env)
    if off:
        print("brevio-core-assist is off:\n  " + "\n  ".join(off), file=sys.stderr)
        return EXIT_OFF
    try:
        finding = parse_finding(args.finding)
        body = request_body(cfg, args.command, rule_text(finding.rule), source_line(args.root, finding))
    except ValueError as exc:
        print(f"brevio-core-assist: {exc}", file=sys.stderr)
        return EXIT_USAGE
    print(preview(cfg, body))
    if args.dry_run:
        return EXIT_OK
    if ask is None and sys.stdin.isatty():
        ask = input
    if not args.yes and not consent(ask):
        print("not sent", file=sys.stderr)
        return EXIT_OFF
    try:
        reply = send(cfg, env[cfg.key_env].strip(), body)
    except AssistError as exc:
        print(f"brevio-core-assist: {exc}", file=sys.stderr)
        return EXIT_FAILED
    if args.command == "verify-fix":
        candidate, ok = verify_replacement(finding, reply)
        print(candidate)
        if ok:
            print(f"verified: passes [{finding.rule}]")
            return EXIT_OK
        print(f"unverified: still triggers [{finding.rule}]", file=sys.stderr)
        return EXIT_FAILED
    print(reply)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
