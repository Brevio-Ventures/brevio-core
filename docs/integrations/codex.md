# brevio-core with Codex

Codex reads `AGENTS.md` before it starts and can call MCP servers. It has no hook brevio-core can attach to, so the
pull-request check is the backstop.

## Set it up

In the repository:

```sh
brevio-core init
```

It writes the pull-request workflow, a baseline, and a marked block of rules in `AGENTS.md`: scan the files you
changed with `brevio-core scan`, fix every finding in the code, never add an ignore comment or edit the baseline, stop
and tell the human when a finding cannot be fixed, and run `brevio-core learn` after fixing a bug. Codex follows `AGENTS.md` in the folder it works in, so the block applies to every task in this
repository. `init` asks before it writes, `--dry-run` shows the diff only, and `brevio-core init --undo` takes it back.

## The MCP server

Add the server to your Codex configuration (`~/.codex/config.toml`):

```toml
[mcp_servers.brevio-core]
command = "uvx"
args = ["brevio-core==0.8.1", "mcp"]
```

Start Codex in the repository: the server reads only the folder it was started in. The tools are `scan`, `explain`,
`list_rules`, `learn` and, from release 0.3, `fix`. `scan`, the agent hook and the MCP server use no network and send
nothing.

## What the agent sees

There is no hook, so findings reach Codex when it runs the scan itself, as `AGENTS.md` tells it to, or through the
MCP `scan` tool. Whatever it misses, the Action reports on the pull request.
