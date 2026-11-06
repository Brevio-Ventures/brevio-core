"""The agent-tool commands of the ``brevio-core`` package: learn, hook, gain, add and mcp (ROADMAP E16, the 0.2 set, 2026-11-04).

``core_cli`` loads this table when the build ships it (the 0.2 export set) and shows no such commands when it does not.
Standard library only, so it exports with the commands it calls. The cloud bridge (``up``) is not here: it stays in the
harness.
"""
from __future__ import annotations

from collections.abc import Callable

from brevio.operator import gain_cmd, hook_cmd, learn_cmd, mcp_cmd, pack_cmd

HELP = {
    "learn": "compile a fixed defect (a git diff) into a local guard and an agent rule",
    "hook": "install the scan hook into the coding agents found here (hook install | status | detect)",
    "gain": "print the savings receipt: counts always, savings only when measured",
    "add": "add a curated guard pack by name (no name lists the packs)",
    "mcp": "serve scan, explain, list_rules and learn to an agent over MCP on stdin and stdout",
}


def _add(argv: list[str]) -> int:
    """``add <pack>`` installs a pack; with no pack name it lists them."""
    named = [a for a in argv if not a.startswith("-")]
    return pack_cmd.main((["add", *argv] if named else ["list", *argv]), prog="brevio-core")


COMMANDS: dict[str, Callable[[list[str]], int]] = {
    "learn": lambda argv: learn_cmd.main(argv, prog="brevio-core learn"),
    "hook": lambda argv: hook_cmd.main(argv, prog="brevio-core hook"),
    "gain": lambda argv: gain_cmd.main(argv, prog="brevio-core gain"),
    "add": _add,
    "mcp": lambda argv: mcp_cmd.main(argv, prog="brevio-core mcp"),
}
