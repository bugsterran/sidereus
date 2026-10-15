# ext-hooks — external AI CLIs into Sidereus
`ext_hook.py` reads hook JSON on stdin and sends it to `POST http://127.0.0.1:8799/api/hook`.
Change the endpoint with `SIDEREUS_HOOK_URL` or `--url`; `--dry-run` prints the body to stderr only.
Supported `--platform` (source of truth: `EXT_PLAT` in `sidereus/ext_store.py`): `gemini codex copilot cursor cline windsurf warp trae zed grok deepseek qwen kimi mistral ollama perplexity huggingface meta openrouter` (19 · ⚠Claude is not in the list - Sidereus already reads its transcripts)
- Preview: `bash ext-hooks/demo.sh` starts 3 fake external sessions (thinking · running a tool · waiting for a person) and `bash ext-hooks/demo.sh clean` removes them — for seeing the screen without installing a CLI.
- In the example JSON, replace `<MAILBOX_CODE_DIR>` with the absolute path of this repository and `<PYTHON>` with macOS `/usr/bin/python3` · Windows `py -3` (or the full `python.exe` path).
- Gemini: merge `hooksConfig`·`mcpServers`·`hooks` from `gemini-settings-example.json` into `~/.gemini/settings.json` (`timeout` = ms)
  - `gemini_mail_stop.py` — AfterAgent hook. At turn end, if there is new mail, it blocks once so the agent reads it (same rule as Claude `hooks/mailbox_stop.py`; id is `<folder>-gemini`)
  - `gemini_mailbox_mcp.sh` — mailbox MCP launcher for Gemini. Picks a per-folder id and never uses the Claude id (`docs/HOOKS.md` «Gemini CLI: mail at turn end»)
- Codex: `codex-hooks-example.json` into `~/.codex/hooks.json` (`timeout` = seconds, SessionEnd at most 3)
- The other 18: in `generic-hooks-example.json`, **replace every** `<PLATFORM>` with a value from the list above and use it as that CLI's hook config file (JSON allows no comments, so only the placeholder is left)

## Receiving mail — in code (no Monitor or watch.sh needed)
The turn-end hook `gemini_mail_stop.py --platform <key>` (default gemini) blocks once when there is new mail so the agent reads it. The id is the `<key>:<cwd>` key or `<folder>-<key>` — ⚠never Claude's `identity.json[cwd]` (it would take the Claude mail of the same folder).
- Start the mailbox MCP with the same id: `gemini_mailbox_mcp.sh <key>`. For Codex, in `~/.codex/config.toml`: `[mcp_servers.mailbox]` `command = "<MAILBOX_CODE_DIR>/ext-hooks/gemini_mailbox_mcp.sh"` `args = ["codex"]`.
  ⚠Not verified that Codex starts MCP servers in the session folder — if not, the hook and the MCP get different ids.
- Gemini: `AfterAgent` — ★verified end to end on 0.61.0 (2026-09-24).
- Codex: `Stop` — only the `decision:block`+`reason` contract was confirmed, from 0.156.1 binary strings; a real run is unverified.
- Others: `Stop` in `generic-hooks-example.json` — ⚠event name and blocking contract both unverified.

Waking an idle session (Claude's `asyncRewake`, `hooks/mailbox_wake.py`) is Claude-only. Other CLIs receive at the next turn end.
- Gemini: none (no such key in the 0.61.0 bundle). Instead, worker mode (`.mail-worker`, Gemini only) waits with `mailbox_wait`.
- Codex: the 0.156.1 hook config has `async`·`asyncRewake` keys, but behaviour is unverified — not put in the example.
- The other 17: unverified.
- `watch.sh` is optional — while it runs, the turn-end hook stays quiet (while `.watch-<id>.pid` is alive).

## Pipeline stage marks — shell markers
Attach `hooks/pl_mark.py`·`hooks/pl_flow.py` separately with `--platform <key>` (included in the example JSON · `ext_hook.py` still leaves stdout empty).
A shell command counts **only when it starts with the marker** — `echo "[pl:<name>/<stage>]"` · `: [pl:...]` · `# [pl:...]`. A marker in the middle, as in `grep "[pl:"`, is ignored.
- `[pl:<name>/<stage>]` = stage start (held 45 minutes in Sidereus) · `[pl-end:<name>/<stage>]` = pass · `[pl-end:<name>/<stage>|fail]` = fail (counts a round) · `[pl:-]` = clear
- The next-stage hint after an end marker goes out as `PostToolUse` `additionalContext` — codex·gemini only; the others only record state.
- The command text is never stored (name · stage · time · cwd · hold only). Called without `--platform`, it behaves as for Claude Code.
- ⚠Payload shape unverified: Gemini `BeforeTool`/`AfterTool` + `run_shell_command` `tool_input.command`, Codex `Bash`/`shell` (last item when argv is a list) — never run against the real CLIs.

⚠**Except for Gemini·Codex, the CLIs' hook event names were not verified** — the 7 standard events (`SessionStart` `SessionEnd` `UserPromptSubmit` `PreToolUse` `PostToolUse` `Stop` `Notification`) are accepted by name as-is (Codex never sends `Notification`, but there is a slot for it). If the names differ, pass `--event <standard name>`.
⚠**The hook never blocks the CLI** — exit 0 and empty stdout no matter what (the CLI reads stdout as control instructions).
⚠**Passes silently when Sidereus is down** — a connection failure is only logged to `.ext-hook.log` after a 2 s timeout (200KB cap).
⚠An event outside the contract or a `--platform` not in the list is **not sent**; it is only logged and exits 0. Missing fields are not guessed — **the key is dropped**.
