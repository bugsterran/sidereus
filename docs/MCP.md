# Sidereus MCP server (`sidereus`)

**English** · [Korean](MCP.ko.md)

`mcp/sidereus_mcp.py` lets a Claude session query Sidereus. It is read-only: it never controls, blocks or messages a session.
Answers contain metadata only (ids, names, states, tool names, counts, times).

## Register

The plugin registers it (as `plugin:sidereus:sidereus`); on Windows the plugin's MCP server runs bare `python3`, so without one on PATH register it by hand as below. ⚠If you use the plugin, skip the line below, or the server is
registered twice. Manual, from the clone on macOS (on Windows run `py -m sidereus setup-claude` in the clone and use the `claude mcp add` line it prints):

```sh
claude mcp add --scope user sidereus -- /usr/bin/python3 "$PWD/mcp/sidereus_mcp.py"
```

## Tools

| Tool | Arguments | Returns |
|---|---|---|
| `sidereus_quota` | none | 5h/7d used %, tokens used on this PC in this 5h window (no remaining budget), reset time, time to empty at this pace, pace vs goal, saver stage, one advice line |
| `sidereus_file_peers` | `path` (required), `sid`, `cwd` | sessions and agents that edited the file in the last 30 min (sid8/unit, agent type, project, time ago, live), and whether it is uncommitted; `no such file` for a missing path |
| `sidereus_peers` | `cwd` | live sessions and subagents in the same repo, any worktree: state, current tool, ctx % |
| `sidereus_attention` | none | sessions that need the user now, labels only |

- `sidereus_quota` numbers are per account of the calling session: when `CLAUDE_CONFIG_DIR` is set and is not `~/.claude`, the
  request carries `dir=<that path>` and the reply's first line is `account: <label>`. An unknown account returns
  `quota unavailable: unknown account` (never the primary account's numbers). Single-account setups send no `dir`.
- The caller is identified by the MCP process cwd, which Claude Code sets to the session cwd. `cwd` overrides it.
- `sidereus_file_peers` finds the caller's session from the parent Claude process and marks it `(you)`; `sid` overrides it. `sidereus_peers` includes your own session.
- Arguments are checked against each tool's `inputSchema` (types, unknown keys, required). A bad call returns JSON-RPC `-32602`.
- The advice line copies the saver hook's verdict (`.saver-view.json` `lv` and stage); the server has no rule of its own.
  The hook (`~/.claude/hooks/saver.py`) is optional and not shipped. Without it, or without its snapshot, `sidereus_quota`
  still returns usage, with no stage and the advice «no pace verdict». If the projected empty time is before the 5h reset, the advice is a warning instead.

## Implementation

- Viewer routes: `GET /api/agent/{quota,peers,file,attention}` in `sidereus/routes_get.py`; bodies from `sidereus/agent_brief.py`. Same Host check as every GET.
- Warm calls take under 2 ms. The first `file` call scans the owner index (~0.4 s).
- JSON-RPC 2.0 over stdio, standard library only, Python 3.9+ (`/usr/bin/python3` on macOS, `py` on Windows).
- HTTP timeout 8 s; the first call after a viewer restart can take over 3 s.
- Port: `SIDEREUS_PORT` > config `port` > 8799.
- If Sidereus is down or too old (404), the tool returns an error text; the server does not exit.
- ⚠ New routes need a viewer restart. Until then the tools answer «Sidereus answered HTTP 404 … — restart it to load the /api/agent routes».

Tests: `tests/test_sidereus_mcp.py` (protocol, tools over mocked HTTP, down path, no body text leaks), `tests/test_agent_brief.py` (briefs over patched readers).
