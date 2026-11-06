# Coding agent integrations

brevio-core checks an agent's work in three places. Use all three; each catches what the one before let through.

1. **In the agent's loop.** A hook scans each file right after the agent edits it, and the uncommitted changes when
   the agent is about to stop, and hands the findings back to the agent to fix. Where a client has no hook, its rules
   file and the MCP server do the same job less directly.
2. **On the pull request.** The [Action](../action.md) scans the lines the change adds and fails the check on a
   finding, whoever or whatever wrote them.
3. **In the agent's instructions.** `brevio-core init` adds a short block of rules to `AGENTS.md`, which most agents
   read before they start.

The hook and the MCP server never honour an ignore comment, so an agent cannot silence a finding; only a person can.

| Client | Hook after each edit | Skill | MCP server | Instructions |
| --- | --- | --- | --- | --- |
| [Claude Code](claude-code.md) | yes | yes | yes | `AGENTS.md` through `CLAUDE.md` |
| [Cursor](cursor.md) | yes | a rule file | yes | a rule file |
| [Codex](codex.md) | no | no | yes | `AGENTS.md` |
| [Hermes](hermes.md) | no | yes | yes | the skill |
| [OpenClaw](openclaw.md) | no | yes | yes | the skill |

To start a new repository with the check and the rules in place, use the agent-safe starter template
([templates/agent-safe-starter](https://github.com/Brevio-Ventures/brevio-core/tree/main/templates/agent-safe-starter)).
