# External CLI integration (Gemini · Codex) — how to attach and what is left

2026-09-22 implemented (server · hook scripts · screen). ★2026-09-24 **live Gemini CLI 0.61.0 integration done** — remaining work is in «To do» at the bottom.
⚠OS porting (Windows · Linux) is **a different job** — see `docs/notes/multiplatform.md`.

## Already done

| Where | What |
|---|---|
| `sidereus/ext_store.py` | `POST /api/hook` receiver `ext_ingest()` (:204) · registry `ext-sessions.json` (24h) · `EXT_PLAT`/`PLAT_MODS` (:31-40) |
| `sidereus/ext.py` | `ext_rows()` (:122) · merged into `sessions()` · row key `plat` · chips `GM`/`CX` |
| `ext-hooks/` | `ext_hook.py` (shared adapter for both CLIs) · 2 config examples · `README.md` |
| Logos | 20 official AI marks (simple-icons 16.32.0) — `AILG` and `EXT_PLAT` use the same 2-letter key |

- Supported `platform` values: `gemini codex copilot cursor cline windsurf warp trae zed grok deepseek qwen kimi mistral ollama perplexity huggingface meta openrouter claude`.
- ⚠Apart from Gemini and Codex, **hook event names are not verified** — the standard 7 (`SessionStart` · `UserPromptSubmit` · `PreToolUse` · `PostToolUse` · `Stop` · `SessionEnd` · `Notification`) are assumed. If they differ, pass `--event`.
- ⚠The Grok logo is not in simple-icons, so the **X mark is used instead**.

- Measured: 5 synthetic hooks → 2 external rows → survive a restart → 0 after `SessionEnd`. 0 lines in the hook failure log.

## Attaching

See `docs/HOOKS.md` (external CLI hooks) and `ext-hooks/README.md`. Failures are logged only in `ext-hooks/.ext-hook.log`.

## Gemini — done (2026-09-24)

- Session row · dedicated work panel (`/api/ext/work`, by `plat+sid` only — never leaks into a Claude session in the same folder) · turn-end mail (`gemini_mail_stop.py`, identity `<folder>-gemini`) · tokens · model · estimated cost (chat JSONL, price table `GEMINI_PRICE`) · token tab «By platform» · timeline row · history gm block.
- Measured: `gemini -p` README check 20/20 correct (20 s) · HOOKS check via DM 9/9 → reply by mailbox.
- ⚠Personal Google login is refused (`UNSUPPORTED_CLIENT`) ⇒ API key (`/auth`, keychain) · ⚠interactive gemini and `/auth` overwrite `settings.json` and drop the hooks · ⚠`$VAR` in config strings is expanded first ⇒ `gemini_mailbox_mcp.sh`.
- ⚠Gemini tokens are **never mixed** into Claude 5h/7d or cost totals (separate store · enforced by tests).

## To do (in order)

1. **Gemini started by a Claude session goes under that session** — kept as a timeline child row even after it ends. `SIDEREUS_PARENT_SID` → hook → `ext.py` parent map (survives restart) · `ext-hooks/ask-gemini` (read-only plan mode). ★Done 09-24 — measured: «gemini -p» row under parent b12214b1, still there after restart.
2. **Clean up dropped sessions** — when a forced kill means no `SessionEnd`, «Thinking» stays up to 24h (`EXT_TTL_S`). Silent N minutes ⇒ «cut off», check pid liveness. ★Done 09-24 — the hook sends CLI pid + start time (ancestor walk past the shell) → `ext_gone_check` (every 30 s `os.kill(pid,0)` + lstart) «cut off»; without a pid, busy and silent 20 min «cut off?», removed like SessionEnd 10 min later · child runs leave the drawer at once. ⚠pid works only on the same host · ⚠only CLIs using the new hook script send a pid.
3. **Platform adapter structure** — every new platform meant too much work. What differs per platform: ①hook event names ②log file location · format (time · id · model · tokens) ③price table ④name · logo · features (turn-end mail · resume). Only these live in one `sidereus/platforms/<plat>.py`; shared code reads it. Move Gemini first with **output bytes unchanged** (golden). ★Done 09-24 — `sidereus/plat_gemini.py` (price table · chat file parser · live tail) · ext/timeline/history iterate only `ext_store.PLAT_MODS`. Proof: fixed clock · snapshot dump (extUsage · timeline · history · work panel · PAGE sha) identical before/after.
   **Adding a new platform** (skeleton: `sidereus/plat_TEMPLATE.py.txt`)
   1. `sidereus/plat_<x>.py` — constants `PLAT` (hook platform value) · `KEY` (row plat, 2 letters) · `NAME` · `CHILD_LABEL` (label for runs started by Claude).
   2. In the same file, `scan(since)` → `[{sid, path, cwd, project, start, kind, msgs, acts[, rate]}]` · `session_msgs(path)` → `{id: (in, out, cache, thought, ts, model, cost)}` or None (includes path check).
   3. One entry in the `PLAT_MODS` tuple (`sidereus/ext_store.py:40`) — ⚠order = timeline and history output order. Add `PLAT: KEY` to `EXT_PLAT` (:31) if missing.
   4. Logo `AILG.<KEY>` (`web/js/55-saver-quota.js`) · hook example `ext-hooks/<x>-hooks-example.json` (also the `ext_hook.py` table if event names differ).
   5. ⚠Metadata only (do not read bodies) · ⚠tokens and cost only in the ext store — never in Claude totals. Synthetic fixture test (shaped like `tests/test_codex.py`).
4. **Codex adapter** — ★code done 09-24 (before live integration): one file `sidereus/plat_codex.py` (event table · rollout parser · price table · name) + shared code reads it via `ext_store.PLAT_MODS` (usage · timeline · history · work panel · child runs). Synthetic fixture `tests/test_codex.py`. `PermissionRequest`→`Notification`. Limit % only when `rate_limits` is present.
   - ⚠Unverified (not run): whether hook `session_id` = `session_meta.id` · whether `cache_write_input_tokens` is included in `input_tokens` · long-context price basis (not on the page — short price only) · actual event flow after the trust gate.
   - Follow-up: turn-end mail (`gemini_mail_stop.py`) ties its identity rule to the Gemini MCP config, so Codex needs its own version.
5. **README «Other CLIs» section + public screenshots updated** (demo mode — no real data). ★Done 09-24 (`feac4c4`).
6. Small items: Gemini row model column (hook has no model — filled from JSONL, confirm) · no session title (Gemini does not store one) · `gemini_mail_stop` cannot stop a Claude name used via `mailbox_login` (needs a server-side fix).

## ⏸ On hold (re-dated 2026-10-15, since 2026-09-24) — other platforms after the Claude side is complete

Work stops here until the Claude side is complete. Resume from this section.
- Remaining: task mail P1–P6 (`docs/notes/agent-tasks.md`) · worker idle cost (⑳ below) · live Codex integration (⚠still not live-tested as of 2026-10-15) · naming consistency (Latin and Korean spellings of Gemini mixed) · numbers cut off in the live card at 1280px.
- Worker loop is off: `.mail-worker` deleted (loop ends). To revive: `touch .mail-worker`.

## Traps hit in the Gemini integration (2026-09-24)

| # | Symptom | Cause | Fix | Status |
|---|---|---|---|---|
| ① | Personal Google login refused | `UNSUPPORTED_CLIENT` | API key (`/auth`, keychain) | fixed |
| ② | Hooks disappear | interactive gemini and `/auth` overwrite `settings.json` | check the 7 hooks after setup | ⚠ongoing |
| ③ | `$VAR` in the MCP command arrives empty | config strings are expanded first | `gemini_mailbox_mcp.sh` wrapper | fixed |
| ④ | exit 55 in an untrusted folder | folder trust gate | `--skip-trust` | fixed |
| ⑤ | Wrong price (3.5-flash-lite cache) | read the free-tier column | paid column · 13 rechecked | fixed |
| ⑥ | Clicking a Gemini row → Claude work log | resolved by cwd | by plat+sid only | fixed |
| ⑦ | Claude and Gemini in the same folder mixed (10 spots) | lookup by cwd only | match plat too (`3a7ef57`) | fixed |
| ⑧ | Runs I started don't stay on the timeline | no parent link | `CLAUDE_CODE_SESSION_ID` → parent · `ext-runs.json` | fixed |
| ⑨ | «Thinking» for 24h after a forced kill | no SessionEnd | pid liveness «cut off» · 20 min silent «cut off?» | fixed |
| ⑩ | Bottom usage 0 after restart | summed only the hook store | based on the chat file scanner | fixed |
| ⑪ | Tests polluted live files (fake row `/x`, fixtures in CODEX_HOME) | storage path not isolated | loader redirects to a temp folder (`cd6a97f`) | fixed |
| ⑫ | `ask-gemini` hangs silently (8 min+) | unknown (second request unanswered, presumed) | watchdog: 180 s no progress 125 · 600 s 124 | fixed · cause unconfirmed |
| ⑬ | Plan mode cannot fetch web pages | headless plan refuses web_fetch | search only · can be enabled with `--policy` (off by default) | decision needed |
| ⑭ | Gemini answers wrong (model name · npm version · price) | guesses its own model · stale search results | model from the log file · always cross-check answers | ⚠ongoing |
| ⑮ | Mail cannot reach an idle session | checked only at turn end | `mailbox_wait` + worker mode | fixed |
| ⑯ | Empty-round count never grows, stop guard useless | `stop_hook_active=false` on every turn after a tool | reset only by human input (transcript) | fixed |
| ⑰ | Loop dies on the 5th wait | loop detection on 5 identical calls | `round=N` on each call | partly fixed — ★09-24 measured rounds 3 · 4 · 5 passed, then blocked at 20:43 with no 6th call recorded (cause unconfirmed: 30-turn detection presumed · `.mail-worker` deleted at the same time) · 1h waits reduced the turn count itself |
| ⑱ | Approval prompt for every tool | default confirm | `trust: true` for the mailbox server only | fixed |
| ⑲ | Two session rows on resume | resume fires one SessionStart with a new sid | same pid + start time = one row | fixed |
| ⑳ | Tokens even while waiting | per empty round, 2 model calls × whole conversation (≈26k) | ★measured ≈$0.024/round · ≈$0.35/h · 12 rounds ≈$0.28 ⇒ option A (1h wait) · D (external wake) | on hold |
| ㉑ | Ran shell commands nobody asked for | passed via user approval | make the worker folder empty · be careful approving | ⚠ongoing |
| ㉒ | Can log in with a Claude name | server does not block it | refuse on the server before task mail P1 | open |
| ㉓ | Failing tests got committed | `\| tail -1` hides the exit code | `set -o pipefail` | fixed |
