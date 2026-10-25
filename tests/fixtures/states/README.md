# State replay fixtures

`tests/test_state_replay.py` runs every folder here through the real state path:
`live.live_cwds` → `parse._parse_transcript` → `sessions._row_state` → `_row_status` · `agents._bg_show` · `sessions._row_acct`.

**Add a case = add a folder.** No code change.

## Folder

| File | Required | Meaning |
|---|---|---|
| `<sid>.jsonl` | yes | Session transcript. Copied to `<root>/projects/<slug>/<sid>.jsonl` (slug of `/nonexistent-sidereus/demo`). |
| `subagents/agent-<id>.jsonl` + `.meta.json` | no | Subagent log and meta (`agentType`, `toolUseId`). Copied beside the transcript. |
| `sessions/<pid>.json` | no | CLI session registry entry. Copied to `<root>/sessions/`. |
| `ps.json` | no | `{"procs": [[pid, ppid, cmd]], "cwd": {pid: cwd}}` — Mac `ps` snapshot and `lsof` cwd map. Ignored when `os` is `win`. |
| `agents.json` | no | stdout of `claude agents --json`. Absent = the binary is missing (`FileNotFoundError`). |
| `otel.json` | no | `{sid: {"ev": ..., "age": s, "tool": ...}}` — OTel state per session. |
| `case.json` | yes | See below. |
| `expected.json` | yes | Subset compared: `state`, `blocked`, `acct`, `sub: [{busy}]` (only keys present). |

`case.json`: `os` (`mac`\|`win`) · `ages` (relative path → file age in seconds, default 0) · `busy` (`tool_busy()` result: `null` · `{}` · `{cwd: true}`) · optional `accounts` (`[{label, primary}]`, default one primary `main`) · optional `root` (label whose root holds the transcript) · `guards` (one line: what this case protects).

## Rules

- ⚠Metadata only (AGENTS.md rule 1): text and thinking blocks `""`, tool input `{}`, tool_result content empty, no prompts, commands or paths. The test fails otherwise.
- Timestamps are relative to the frozen clock (`tests/_clock.py` NOW = 2026-01-01T00:00:00Z).

## State map

| Screen | `state` |
|---|---|
| Working | `tool` · `think` |
| Idle | `wait` |
| Waiting | `ask` (+ `abort`) |
| Ended | `done` |
| Blocked | `blocked` != `""` |
| Unknown | `unknown` |
