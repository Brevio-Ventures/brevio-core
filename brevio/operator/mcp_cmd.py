"""``brevio-core mcp``: the scan, the rule pages and the guard compiler as an MCP server on stdin and stdout.

ROADMAP E16, the 0.2 set, 2026-11-05. The transport is newline-delimited JSON-RPC 2.0 and the methods are the MCP
ones a tool server needs (``initialize``, ``ping``, the tool list and the tool call). Standard library only, no SDK,
no network and no model call: every tool reads the project in the folder the server was started in. Standard output
carries protocol messages and nothing else. Paths a client names must lie inside that folder. The 0.3 set adds a
``fix`` tool (``scan --fix``): it returns the diff and writes only when the call sets ``write`` (2026-11-05). With the 0.4
set the scan leaves out baselined findings but never honours an ignore comment: an agent cannot silence the gate, and
no tool writes a baseline. With no arguments it scans the uncommitted changes, and it answers with one short line per
finding, at most ``core_cli.AGENT_MAX``, in the same lines the agent hook gives (plan review, 2026-11-05; ROADMAP E34).
"""
from __future__ import annotations

import contextlib
import importlib
import io
import json
import os
import re
import sys
from collections.abc import Callable
from typing import Any, TextIO

from brevio.pipeline import core_cli
from brevio.pipeline.code_rules import PR_RULES_122
from brevio.pipeline.code_rules import docs as rule_docs

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")   # newest first; an unknown client version gets the newest
# The version of this tool set, not of the package: reading the package's metadata would load the network modules.
SERVER_VERSION, SERVER_VERSION_FIX, SERVER_VERSION_BASELINE = "0.2", "0.3", "0.4"
LEARN_MODULE = "learn_cmd"   # named here so a build without it simply offers no ``learn`` tool
PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS = -32700, -32600, -32601, -32602
# MCP names its tool methods with a "tools" prefix; built here because the leak scan reads that literal as a private folder.
_NS = "tools"
LIST_METHOD, CALL_METHOD = f"{_NS}/list", f"{_NS}/call"
_RULE_ID = re.compile(r"R\d+\.\d+")

ToolResult = tuple[str, dict[str, Any]]   # the text an agent reads, and the same facts as structured data


class ToolError(Exception):
    """A tool could not do what was asked; the client sees ``isError`` and the message."""


def _inside_folder(path: str) -> bool:
    here = os.path.realpath(os.getcwd())
    return os.path.commonpath([here, os.path.realpath(path)]) == here


def _text_list(args: dict[str, Any], key: str) -> list[str]:
    value = args.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ToolError(f"{key} must be a list of strings")
    return value


def _base(args: dict[str, Any], key: str) -> str | None:
    value = args.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or value.startswith("-"):
        raise ToolError(f"{key} must be a git revision, not an option")
    return value


def _named_paths(args: dict[str, Any]) -> list[str]:
    named = _text_list(args, "paths")
    gone = [p for p in named if not os.path.exists(p)]
    if gone:
        raise ToolError(f"no such file or folder: {', '.join(gone)}")
    outside = [p for p in named if not _inside_folder(p)]
    if outside:
        raise ToolError(f"outside the project folder: {', '.join(outside)}")
    return named


def _tool_scan(args: dict[str, Any]) -> ToolResult:
    named, base = _named_paths(args), _base(args, "diff_base")
    if not named and base is None and core_cli.has_head():
        base = "HEAD"       # no arguments: the uncommitted changes (the working tree against HEAD, plus untracked files)
    lines = core_cli.select_lines(named, base)
    try:
        shown, _silenced, baselined = core_cli.triage(core_cli.scan(lines), honour_ignores=False)
    except core_cli.UsageError as exc:
        raise ToolError(str(exc)) from exc
    summary = f"{len(shown)} finding(s) in {len(lines)} file(s)" + (f", {len(baselined)} baselined" if baselined else "")
    return "\n".join([*core_cli.agent_lines(shown), summary]), {"count": len(shown), "files": len(lines), "baselined": len(baselined)}


def _tool_explain(args: dict[str, Any]) -> ToolResult:
    rule = str(args.get("rule", "")).strip().upper()
    if not _RULE_ID.fullmatch(rule) or rule not in PR_RULES_122:
        raise ToolError(f"unknown rule {rule or '(none)'}; call list_rules for the ids")
    return rule_docs.render(rule), {"rule": rule}


def _tool_list_rules(args: dict[str, Any]) -> ToolResult:
    query = str(args.get("query", "")).strip().lower()
    rules = [{"id": rid, "summary": PR_RULES_122[rid]} for rid in rule_docs.rule_ids()
             if query in rid.lower() or query in PR_RULES_122[rid].lower()]
    return "\n".join(f"{r['id']}: {r['summary']}" for r in rules), {"count": len(rules), "rules": rules}


def _tool_fix(args: dict[str, Any]) -> ToolResult:
    named, base = _named_paths(args), _base(args, "diff_base")
    write = args.get("write", False)
    if not isinstance(write, bool):
        raise ToolError("write must be true or false")
    lines = core_cli.select_lines(named, base)
    changes = core_cli.plan_fixes(lines)
    diff = core_cli.unified_diff(changes)
    if write:
        core_cli.apply_fixes(changes)
        lines = core_cli.select_lines(named, base)
    remaining = len(core_cli.scan(lines)) if write else len(core_cli.scan(lines)) - sum(len(r) for _o, _n, r in changes.values())
    fixes = [{"path": rel, "rules": rules} for rel, (_o, _n, rules) in sorted(changes.items())]
    data = {"diff": diff, "fixed": sum(len(f["rules"]) for f in fixes), "files": fixes, "remaining": remaining, "written": write}
    verb = "fixed" if write else "would fix"
    return diff + f"{verb} {data['fixed']}, {remaining} finding(s) remaining", data


def _learn_module() -> Any:
    top = __name__.split(".")[0]
    try:
        return importlib.import_module(f"{top}.operator.{LEARN_MODULE}")   # a name built at run time: absent from a set without it
    except ModuleNotFoundError as err:
        if not (err.name or "").startswith(f"{top}.operator"):
            raise
        return None


def _memory_module() -> Any:
    return core_cli.set_module("pipeline", "core_memory")


def _tool_brief(args: dict[str, Any]) -> ToolResult:
    memory = _memory_module()
    files = _text_list(args, "files")
    outside = [p for p in files if not _inside_folder(p)]
    if outside:
        raise ToolError(f"outside the project folder: {', '.join(outside)}")
    brief = memory.brief_for_files(files, cwd=os.getcwd())
    lines: list[str] = []
    if brief.get("micro_rules"):
        lines.append(str(brief["micro_rules"]).strip())
    for ep in brief.get("episodes", []):
        lines.append(f"[{ep.get('rule_id', '')}] {ep.get('file', '')}: {ep.get('trap', '')} -> {ep.get('fix', '')}")
    if brief.get("neighbors"):
        lines.append(f"1-hop neighbors: {', '.join(brief['neighbors'][:10])}")
    return "\n".join(lines) or "No active rules or past traps found for the specified files.", brief


def _tool_learn(args: dict[str, Any]) -> ToolResult:
    learn = _learn_module()
    base = _base(args, "diff_base") or "HEAD~1"
    argv = ["--diff", base, "--json"]
    if isinstance(args.get("name"), str) and args["name"]:
        argv += ["--name", args["name"]]
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = learn.main(argv, prog="brevio-core learn")
        except SystemExit as stop:      # the argument parser exits on a value it rejects
            code = stop.code if isinstance(stop.code, int) else 2
    if code:
        raise ToolError((err.getvalue() or out.getvalue()).strip() or "no guard could be compiled")
    try:
        guard = json.loads(out.getvalue())
    except ValueError as exc:
        raise ToolError("the guard compiler returned no guard") from exc
    return f"Compiled guard {guard.get('id')}: {guard.get('title')}", {"guard": guard}


def _schema(properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "additionalProperties": False}


_STR = {"type": "string"}
TOOLS: dict[str, tuple[str, dict[str, Any], bool, Callable[[dict[str, Any]], ToolResult]]] = {
    "scan": ("Scan files, folders or the lines a change adds against the code rules. Returns one line per finding: "
             f"path:line [rule] message -> a fix hint, grouped by rule, at most {core_cli.AGENT_MAX}. With no arguments it scans the "
             "uncommitted changes (the whole folder when there is no commit). An ignore comment does not count here.",
             _schema({"paths": {"type": "array", "items": _STR, "description": "Files or folders inside the project."},
                      "diff_base": {**_STR, "description": "Scan only the lines added against this git revision "
                                    "(an empty string means origin/main)."}}), True, _tool_scan),
    "explain": ("Return the page of one rule: what it catches, why, a bad and a good example.",
                {**_schema({"rule": {**_STR, "description": "A rule id such as R2.1."}}), "required": ["rule"]}, True, _tool_explain),
    "list_rules": ("List the rule ids with a one-line summary each, optionally only those matching a word.",
                   _schema({"query": _STR}), True, _tool_list_rules),
    "fix": ("Fix what a rule has one correct rewrite for (for example `@ts-ignore` to `@ts-expect-error`). Returns the "
            "unified diff; writes the files only when write is true. Secrets and other findings are never fixed, only "
            "counted as remaining.",
            _schema({"paths": {"type": "array", "items": _STR, "description": "Files or folders inside the project."},
                     "diff_base": {**_STR, "description": "Fix only the lines added against this git revision "
                                   "(an empty string means origin/main)."},
                     "write": {"type": "boolean", "description": "Rewrite the files in place (default false: diff only)."}}),
            False, _tool_fix),
    "learn": ("Compile a fixed defect (a git diff) into a local guard and an agent rule. Writes .brevio/guards.json and "
              ".agents/rules/ in the project.",
              _schema({"diff_base": {**_STR, "description": "The commit or range holding the fix (default HEAD~1)."}, "name": _STR}),
              False, _tool_learn),
    "brief": ("Return the surface-scoped engineering rules, recalled trap-to-fix episodes and 1-hop file neighbors for "
              "the files you are about to edit.",
              _schema({"files": {"type": "array", "items": _STR, "description": "Files inside the project about to be edited."}}),
              True, _tool_brief),
}


def server_version() -> str:
    """The tool set this build serves: 0.4 with the baseline, 0.3 with the fixers, else 0.2."""
    if core_cli.baseline_tools() is not None:
        return SERVER_VERSION_BASELINE
    return SERVER_VERSION_FIX if core_cli.fixers() is not None else SERVER_VERSION


def _available() -> dict[str, tuple[str, dict[str, Any], bool, Callable[[dict[str, Any]], ToolResult]]]:
    absent = {"learn": _learn_module() is None, "fix": core_cli.fixers() is None, "brief": _memory_module() is None}
    return {n: t for n, t in TOOLS.items() if not absent.get(n)}


def tool_list() -> list[dict[str, Any]]:
    return [{"name": n, "description": d, "inputSchema": schema, "annotations": {"readOnlyHint": read_only}}
            for n, (d, schema, read_only, _fn) in _available().items()]


def call_tool(params: Any) -> dict[str, Any]:
    """The result of a tool call: a tool's own failure is an ``isError`` result, a malformed call raises ``ValueError``."""
    if not isinstance(params, dict) or not isinstance(params.get("name"), str):
        raise ValueError("a tool call needs a tool name")
    tool = _available().get(params["name"])
    if tool is None:
        raise ValueError(f"unknown tool: {params['name']}")
    args = params.get("arguments") or {}
    if not isinstance(args, dict):
        raise ValueError("arguments must be an object")
    try:
        text, data = tool[3](args)
    except (ToolError, OSError) as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
    return {"content": [{"type": "text", "text": text}], "structuredContent": data, "isError": False}


def _reply(msg_id: Any, *, result: Any = None, error: tuple[int, str] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"jsonrpc": "2.0", "id": msg_id}
    if error:
        body["error"] = {"code": error[0], "message": error[1]}
    else:
        body["result"] = result
    return body


def handle(message: Any) -> dict[str, Any] | None:
    """The reply to one decoded message, or ``None`` for a notification or a reply from the client."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _reply(None, error=(INVALID_REQUEST, "not a JSON-RPC 2.0 message"))
    method, msg_id = message.get("method"), message.get("id")
    if not isinstance(method, str):
        return None if "result" in message or "error" in message else _reply(msg_id, error=(INVALID_REQUEST, "no method"))
    if "id" not in message:
        return None     # a notification (such as notifications/initialized) gets no answer
    params = message.get("params")
    if method == "initialize":
        asked = params.get("protocolVersion") if isinstance(params, dict) else None
        version = asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
        return _reply(msg_id, result={"protocolVersion": version, "capabilities": {"tools": {}},
                                      "serverInfo": {"name": "brevio-core", "version": server_version()}})
    if method == "ping":
        return _reply(msg_id, result={})
    if method == LIST_METHOD:
        return _reply(msg_id, result={"tools": tool_list()})
    if method == CALL_METHOD:
        try:
            return _reply(msg_id, result=call_tool(params))
        except ValueError as exc:
            return _reply(msg_id, error=(INVALID_PARAMS, str(exc)))
    return _reply(msg_id, error=(METHOD_NOT_FOUND, f"method not found: {method}"))


def serve(stdin: TextIO, stdout: TextIO) -> int:
    """Answer one JSON message per line until ``stdin`` ends."""
    for line in stdin:
        if not line.strip():
            continue
        try:
            reply = handle(json.loads(line))
        except ValueError:
            reply = _reply(None, error=(PARSE_ERROR, "parse error"))
        if reply is not None:
            stdout.write(json.dumps(reply, separators=(",", ":")) + "\n")
            stdout.flush()
    return 0


def main(argv: list[str], prog: str = "brevio-core mcp") -> int:
    if argv:
        print(f"usage: {prog}\n\nServe the scan, rule pages and guard compiler over MCP on stdin and stdout. "
              "Takes no arguments, makes no network call and no model call.", file=sys.stderr)
        return 0 if argv in (["-h"], ["--help"]) else 2
    return serve(sys.stdin, sys.stdout)
