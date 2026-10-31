# ext-hooks — external AI CLIs into Sidereus
`ext_hook.py` reads hook JSON on stdin and sends it to `POST http://127.0.0.1:8799/api/hook`.
Change the endpoint with `SIDEREUS_HOOK_URL` or `--url`; `--dry-run` prints the body to stderr only.
Supported `--platform` (source of truth: `EXT_PLAT` in `sidereus/ext_store.py`): `gemini codex copilot cursor cline windsurf warp trae zed grok deepseek qwen kimi mistral ollama perplexity huggingface meta openrouter` (19 · ⚠Claude is not in the list - Sidereus already reads its transcripts)
- Automatic: Settings › «Diagnostics» › «CLI hooks» › «Connect» merges the example below into Cursor, Codex, Gemini or Copilot after a diff preview and confirm (`docs/HOOKS.md` «Automatic connect»).
- Preview: `bash ext-hooks/demo.sh` starts 3 fake external sessions (thinking · running a tool · waiting for a person) and `bash ext-hooks/demo.sh clean` removes them — for seeing the screen without installing a CLI.
- In the example JSON, replace `<MAILBOX_CODE_DIR>` with the absolute path of this repository and `<PYTHON>` with macOS `/usr/bin/python3` · Windows `py -3` (or the full `python.exe` path).
- Gemini: merge `hooksConfig`·`mcpServers`·`hooks` from `gemini-settings-example.json` into `~/.gemini/settings.json` (`timeout` = ms)
  - `gemini_mail_stop.py` — AfterAgent hook. At turn end, if there is new mail, it blocks once so the agent reads it (same rule as Claude `hooks/mailbox_stop.py`; id is `<folder>-gemini`)
  - `gemini_mailbox_mcp.sh` — mailbox MCP launcher for Gemini. Picks a per-folder id and never uses the Claude id (`docs/HOOKS.md` «Gemini CLI: mail at turn end»)
- Codex: `codex-hooks-example.json` into `~/.codex/hooks.json` (`timeout` = seconds, SessionEnd at most 3)
  - Append the entries as a new group per event (keep existing groups first): Codex stores approval per `event:group:entry`, so other tools' approvals stay valid. Then approve them once in the Codex TUI with `/hooks` — the lines read `ext_hook.py` / `gemini_mail_stop.py`, not «Sidereus». ★Verified on 0.163.0 (2026-10-19): list, state, turn-end mail, `[pl:]` marks.
  - Without hooks a Codex session whose rollout changed in the last 10 minutes gets a coarse row marked «Hooks not connected» (folder, model, state unknown); the hook row replaces it once events arrive.
  - Optional `SessionStart` notices (room invites + turn-end mail line, the project's pipelines): add `<PYTHON> <MAILBOX_CODE_DIR>/hooks/invite_notice.py --platform codex` (timeout 10) and `<PYTHON> <MAILBOX_CODE_DIR>/hooks/pipelines_brief.py --platform codex` (timeout 5). ⚠Without `--platform codex` they print the Claude wording (mailbox_wake, Agent tool). On 0.163 `SessionStart` fires with the first turn, not at launch.
- Cursor CLI: copy `cursor-hooks-example.json` to `~/.cursor/hooks.json` (or `<project>/.cursor/hooks.json`; merge into an existing `hooks` object). ★Verified on macOS, Cursor CLI 2026.10.22 (2026-10-24): list, state, `[pl:]` marks.
  - Events are camelCase (`sessionStart` `beforeSubmitPrompt` `preToolUse` `postToolUse` `postToolUseFailure` `stop` `sessionEnd`); `afterAgentThought`/`afterAgentResponse` carry model text and are never sent.
  - The folder comes from the first `workspace_roots` entry (Cursor sends no base `cwd`); `user_email` and tool input are dropped.
  - ⚠`cursor-agent -p` sends no `beforeSubmitPrompt`/`stop`, so a headless row keeps its last state until `sessionEnd`.
- Copilot CLI: copy `copilot-hooks-example.json` to `~/.copilot/hooks/sidereus.json` (or `$COPILOT_HOME/hooks/`). ★Verified on macOS, Copilot CLI 1.0.105 (2026-10-31): list, state.
  - Register PascalCase event names only. ⚠Never also register the camelCase names - every event then fires twice.
  - `PermissionRequest` arrives camelCase (`hookName` `sessionId` `toolName`) even when registered PascalCase; it maps to `Notification` (waiting for approval until `PostToolUse`). `toolInput`, `permissionSuggestions` and `timestamp` are dropped.
- The other 15: in `generic-hooks-example.json`, **replace every** `<PLATFORM>` with a value from the list above and use it as that CLI's hook config file (JSON allows no comments, so only the placeholder is left)

## Receiving mail — in code (no Monitor or watch.sh needed)
The turn-end hook `gemini_mail_stop.py --platform <key>` (default gemini) blocks once when there is new mail so the agent reads it. The id is the `<key>:<cwd>` key or `<folder>-<key>` — ⚠never Claude's `identity.json[cwd]` (it would take the Claude mail of the same folder).
- Start the mailbox MCP with the same id: `gemini_mailbox_mcp.sh <key>`. For Codex, in `~/.codex/config.toml`: `[mcp_servers.mailbox]` `command = "<MAILBOX_CODE_DIR>/ext-hooks/gemini_mailbox_mcp.sh"` `args = ["codex"]` `tool_timeout_sec = 3600` (full block: `codex-config-example.toml`).
  - `tool_timeout_sec` only matters for long `mailbox_wait` calls the agent makes itself; ★0.163.0 (2026-10-20): `tool_timeout_sec = 30` cut a 60 s wait («timed out awaiting tools/call after 30s»).
  - ⚠`codex exec` refuses MCP calls («approval policy is never») unless the tools are approved: add `-c 'mcp_servers.mailbox.default_tools_approval_mode="approve"'`. The TUI asks instead.
  - ★0.163.0 (2026-10-20): Codex starts the MCP in the session folder — hook and MCP both resolved `<folder>-codex`.
- Gemini: `AfterAgent` — ★verified end to end on 0.61.0 (2026-09-24).
- Codex: `Stop` — ★verified end to end on 0.163.0 (2026-10-19): the hook blocked once and the session read its inbox; id `<folder>-codex`.
- Others: `Stop` in `generic-hooks-example.json` — ⚠event name and blocking contract both unverified.

Waking an idle session: each CLI's method is one row of `WAKE` in `hooks/mail_wait.py` (a new CLI = one row + `tests/test_mail_wake_table.py`). All of them watch `bus.jsonl` the same way on every OS (stat every 2 s, no model call while waiting).
- Claude: `async-rewake` (`hooks/mailbox_wake.py`, background Stop hook, exit 2 wakes the session).
- Codex: `turn-end` by default — the example Stop entry `gemini_mail_stop.py --platform codex` delivers mail at the next turn end.
- Codex mail wake (`--wake`, **opt-in**, timeout 5): append `--wake` to that Stop command in `~/.codex/hooks.json`, then re-approve with `/hooks` (the hash changes). Stop spawns a detached stdlib waiter (`codex_wake.py`) and returns at once, so typing is never blocked. When mail for the session's id arrives, it starts one turn on the session's own thread through the local Codex app-server daemon socket (`/private/tmp/codex-daemon-$UID/<hash>`, WebSocket over a unix socket). The turn text is the «[mailbox] N new mail …» line — ids and a count only.
  - If you type first, the waiter exits. No daemon, a thread not loaded in it, or `codex exec` = nothing happens; «Mail waiting» stays the fallback.
  - Approval: `default_tools_approval_mode = "approve"` on `[mcp_servers.mailbox]` (`codex-config-example.toml`) lets the woken turn read mail without a prompt. Only this server's tools; shell and other approvals are unchanged. Restart the session after editing.
  - ⚠Limits: the methods it calls (`thread/loaded/list`, `thread/resume`, `turn/start`) are documented app-server methods not marked experimental, but the daemon socket path is undocumented (an implementation detail) and the WebSocket transport is experimental (stdio is the default). A Codex update can break the wake; it then exits quietly (`.codex-wake.log` records the step, error type and Codex version) and «Mail waiting» stays the fallback. ★0.163.0 (2026-10-21): the injected turn ran in 17 s, every hook fired, it showed in the TUI. ★0.164.0 (2026-10-24): works without `experimentalApi`. macOS/Linux only — on Windows the daemon has no unix socket, so nothing is spawned.
- Codex: `stop-wait`, **opt-in, for unattended sessions only** — the example ships turn-end delivery. To enable, append `--wait` (instead of `--wake`) and set timeout 3600 in `~/.codex/hooks.json`, then re-approve with `/hooks` (the hash changes). It waits up to 59 min (`SIDEREUS_MAIL_WAIT_S`) and blocks when mail arrives.
  - ⚠The wait runs after every interactive turn: the TUI shows «Working · Running hook» and a prompt you type only queues (Codex does not cancel the hook) until mail arrives, the timeout, or Esc. ★0.163.0 (2026-10-20): a 1884 s dead gap inside one turn — Codex looked hung on simple requests. Never make `--wait` the default for an interactive Codex.
  - ⚠After 59 min the turn ends and waiting resumes only after the next prompt; the attention signal covers that gap.
  - After `SIDEREUS_MAIL_WAIT_MAX` (20) mail wakes without a human prompt it stops waiting until you type.
  - `codex exec` never waits (detected from the rollout's `session_meta`; an unreadable rollout also skips the wait).
- Gemini: `turn-end` (no async key in the 0.61.0 bundle). Worker mode (`.mail-worker`, Gemini only) waits with `mailbox_wait`.
- The other 17: `none` (unverified).
- `watch.sh` is optional — while it runs, the turn-end hook stays quiet (while `.watch-<id>.pid` is alive).

## Pipeline stage marks — shell markers
Attach `hooks/pl_mark.py`·`hooks/pl_flow.py` separately with `--platform <key>` (included in the example JSON · `ext_hook.py` still leaves stdout empty).
A shell command counts **only when it starts with the marker** — `echo "[pl:<name>/<stage>]"` · `: [pl:...]` · `# [pl:...]`. A marker in the middle, as in `grep "[pl:"`, is ignored.
- `[pl:<name>/<stage>]` = stage start (held 45 minutes in Sidereus) · `[pl-end:<name>/<stage>]` = pass · `[pl-end:<name>/<stage>|fail]` = fail (counts a round) · `[pl:-]` = clear
- The next-stage hint after an end marker goes out as `PostToolUse` `additionalContext` — codex·gemini only; the others only record state.
- The command text is never stored (name · stage · time · cwd · hold only). Called without `--platform`, it behaves as for Claude Code.
- ⚠Payload shape unverified: Gemini `BeforeTool`/`AfterTool` + `run_shell_command` `tool_input.command`, Codex `Bash`/`shell` (last item when argv is a list) — never run against the real CLIs.

⚠**Except for Gemini·Codex·Cursor·Copilot, the CLIs' hook event names were not verified** — the 7 standard events (`SessionStart` `SessionEnd` `UserPromptSubmit` `PreToolUse` `PostToolUse` `Stop` `Notification`) are accepted by name as-is (Codex never sends `Notification`, but there is a slot for it). If the names differ, pass `--event <standard name>`.
⚠**The hook never blocks the CLI** — exit 0 and empty stdout no matter what (the CLI reads stdout as control instructions).
⚠**Passes silently when Sidereus is down** — a connection failure is only logged to `.ext-hook.log` after a 2 s timeout (200KB cap).
⚠An event outside the contract or a `--platform` not in the list is **not sent**; it is only logged and exits 0. Missing fields are not guessed — **the key is dropped**.
