# Traps — Sessions and work-log popup

Conventions (entry shape, `★` `⚠` `⇒`, `§N`, `:NNNN`): [TRAPS.md](../TRAPS.md). Newest first within an area; new traps go at the top of their area.

## Sessions: state, subagents, external CLIs

- ⚠**Fold-all must clear the session list's HTML cache** (2026-10-13). Toggling one `<details>` group changes the DOM but not `box._sh`, the cached HTML string the list compares before redrawing. «Expand all» right after closing one group then renders identical HTML and the redraw is skipped. ⇒ `wfFoldAll` clears `box._sh` before redrawing (40b-sessions-list.js). Test: `test_sess_wf_fold_all_js.py`.
- **A background shell running over 2 h vanished from the session** (2026-10-15; `sidereus/bgtasks.py` `_bg_expire`).
  - Cause: the RUN_STALE_S (7200 s) age expiry dropped every non-watcher row; a 5 h dev server (pid alive, no notice) showed `bgs: []`.
  - ⇒ `bg` rows are exempt like `task`; they close on their `<tool-use-id>` notice, an error receipt, session death or ✕. `sub` rows keep the 2 h backstop.
  - ⚠Never measure a shell's liveness by age. Test: `tests/test_bg_monitor.py` `BgExpiry`.
- **A subagent's approval prompt never showed** (2026-10-14; `hooks/perm_mark.py`, `sidereus/perm_marks.py` `_sub_badge`).
  - Cause: one marker per sid with no agent id, compared with main-transcript activity; the main turn kept writing, `ask` rows were skipped, and a main AskUserQuestion notification overwrote the sub's marker.
  - ⇒ An event with `agent_id` writes `permwait/<sid>.<aid>.json`; any live row state shows «subagent waiting for approval» while it is newer than that sub's own activity (`sub[].idle` / `wf[].agents[].end`).
  - ⚠Never clear a sub badge via `_answered` (OTel decisions are session-wide; auto-approved tools emit them too). A main marker with `tool` "AskUserQuestion" is never a sub wait.
  - ⇒ Exception, attributable decisions only (`_sub_decided`): ★an approved long sub Bash kept the badge 186 s after the decision. A decision clears it only when it is the session's sole open prompt, the decision is newer and names the same tool, and no other writer (main, other sub, wf agent) is newer than marker+1 s. A tool-less main marker within 15 s is the Notification duplicate of the same prompt.
  - ⚠Recurrence (2026-10-14 15:15): ★the parent's own 90 s Bash made `tool_busy` mark the cwd busy (probe is per process cwd), so the sub's pending Bash read as «approved and running»; ★a sub log is flushed ~0.1 s after its line timestamps (185 logs, median 0.102 s) and landed 52 ms after the marker. ⇒ `_sub_badge` skips the shell check while the parent row is `tool`/Bash and allows `_SUB_FLUSH_S` = 1 s. `tests/test_perm_mark_sub.py`.
  - ⚠A sibling sub's Bash in the same cwd hid it the same way. ★Tool shells carry no agent id (`ps -E` shows the command only) and an approved Bash writes nothing until its result (1,352 sub Bash calls >30 s: only hook lines in between), so the probe can neither be attributed nor dropped. ⇒ `_sole_shell_owner`: a live shell clears the badge only when no parent Bash, other sub with `now` Bash or running workflow agent could own it; otherwise the badge stays (fail toward the badge).
- **`claude agents` keeps the pre-/clear sid; pair by the hook's pid record** (2026-10-12; `hooks/invite_notice.py` `record_clear`, `sidereus/sess_clear.py`).
  - Cause: after /clear the process lists its old sid while transcripts move to a new one, so the two look like separate sessions.
  - ⇒ SessionStart writes `sesspid/<claude pid>` = sid; on `source` "clear" it appends `{at, pid, old, new}` to `clears.jsonl`; `clear_links()`/`clear_of(sid)` read it; timeline row `clr`.
  - ⚠Pid = hook parent, or its parent when that is a shell. Never pair by cwd (several sessions share one); rows without a record get no `clr` key.
  - ⚠The selfcheck cwd-staleness fallback (`sessions_health._cleared_in_cwd`, for clears before the hook existed) silences every unconfirmed row in that cwd — broad on purpose; narrow it if a real dead session ever hides behind it.
- **A shared-history profile is an account but not a scan root** (2026-10-12; `sidereus/claude_roots.py`).
  - Cause: a profile whose `projects/` symlinks to another root's writes transcripts there, so the file path cannot say which account ran a session; scanning it again would double every row.
  - ⇒ `roots()` drops it (projects realpath already seen); `accounts()` keeps it; `acct_of(sid, fp)` reads the SessionStart record `ACCT_DIR/<sid>` (one line = config dir) and falls back to `root_of(fp)`.
  - ⚠Never dedupe `accounts()` by projects realpath, and never add a shared profile to `roots()`/`projects_dirs()`.
- **Blocked red beats the account band on purpose** (2026-10-12; `web/css/60-sessions.css`).
  - `.sxw:has(.sl.sblk)` (0,3,0) outranks `.acb:is(...)` (0,2,0), so a blocked row shows red, not its account colour.
  - ⚠Do not raise the band's specificity above the blocked rule; blocked state wins.
- ★**Subagents that ended with `SubagentHandback` stayed «running» on the timeline** (2026-10-07).
  - Cause: `bgtasks._ended_turn` accepted only an assistant `end_turn`; a handback log ends on the user `tool_result`, so `_bg_revive` re-opened it and `_retired` (3) never fired. (4) leaned on `_bg_popped`, whose 400-entry cap one busy transcript evicted.
  - ⇒ `_ended_turn` also asks `agents._agent_ended` when the last record is a user `tool_result`; `_bg_popped` cap 4000. `tests/test_bg_completion.py` `test_handback_*`.
  - ⚠An `is_error` handback stays open. Never call `_agent_ended` on a plain user prompt — it skips string content and reads the earlier `end_turn`, killing a resumed agent.
- ★**A pending feedback request never leaves attention by age** (2026-10-14; replaces the 30-min `EXT_BLOCK_TTL_S` cap of 09-23/10-01).
  - Cause: the cap dropped a live CLI's question/approval after 31 min; `perm_marks.PERM_MAX_S` dropped a Claude approval after 12 h; unknown Claude liveness turned `ask` into `unknown`.
  - ⇒ Only liveness removes it: ext dead pid -> `gone` (`ext_gone_check`), Claude no process -> `done`. Unknown liveness keeps it (`notes._sess_state`, `ext_store._pending` exempt from `EXT_TTL_S`).
  - ⚠Never add an age cap to ask/blocked/plan approval; age may change a label only. A pid-less dead CLI's request stays until dismissed (attention ack -> `POST /api/ext/dismiss` -> `ext_store.ext_dismiss`, pid-less pending rows only). Tests `TestExtAskCap`, `TestClaudePendingAge`, `test_ext_gone.py`.
- ⚠**Attention «Reply» box draft lives in `attnRp`, not the DOM** — `buildAttn` replaces `#attn` innerHTML on any change, so the value/caret are restored after it (`preventScroll` focus); never render the draft into the HTML (`attnHtml` compare + metadata-only). «Done» acks by row id + signal key (`attnDone`), never by session alone. Test `test_attention_actions_js.py`.
- ★**An auto-mode session showed «blocked · Bash»** (2026-09-29). Cause: `_blocked` ignored the permission mode. ⇒ `parse._tail_pmode` (user-line `permissionMode`, latest wins) → row `pmode` → `_blocked(pmode=)`: auto · bypassPermissions · dontAsk are never judged; acceptEdits excludes only Edit/Write-type tools. `tests/test_live_probe.py`.
  - ⚠No `permissionMode` in the tail (400KB) → `""` = the old judgement. Do not guess the mode.
- **A background subagent's permission prompt showed no badge** (`perm_marks.perm_rows`). Cause: only `state == "tool"` rows read the marker, but after the main turn ends the row is `wait` while the sub still runs.
  - ⇒ `wait` rows with a non-empty `sub`: activity = newest of main `ageSec` and min sub `idle`; marker newer than that ⇒ `blocked = "subagent waiting for approval"` (fixed label; client special-cases it before the `<Tool> waiting for approval` split). `tests/test_perm_mark.py`.
  - ⚠Never set it for idle rows without a running sub — stale markers ⇒ false «blocked».
  - ⚠With 2+ subs, a sibling's newer log write hides a real prompt (accepted false negative); a sub without an int `idle` skips the row.
- ★**Turn end without a marker read as «thinking» forever** (live: 7h). Cause: a resumed/ended session can end on a text-only assistant line with no `turn_duration`/`stop_hook_summary` after it.
  - ⇒ `parse._turn_shape` also closes the turn when the line has `stop_reason` `end_turn`/`stop_sequence` or model `"<synthetic>"`.
  - ⚠A text line with `stop_reason` null is mid-turn and stays `"result"`.
- **A pending prompt showed «thinking» for ~5 min** (A1, `sessions._row_state`). Cause: an OTel `api_request` for the same session overrode transcript `tool`/`wait`.
  - ⇒ no OTel `think` (tool_result · user_prompt · api_request) overrides a pending `tool`; only `tool_decision` does. `api_request` also never overrides `wait`. `tests/test_otel_tool_state.py`.
  - ⚠Do not let a newer OTel event replace a transcript state that means «waiting» — the request fires before the prompt is answered.
- **A prompt unanswered for 30 min dropped off** (A3, `perm_marks.PERM_MAX_S`, `ext.ext_rows`). Cause: 1800 s caps on the marker and on external `blocked`/`ask`.
  - ⇒ `PERM_MAX_S` = 12 h (safety net; newer activity is what clears it); the external 30-min cap applies only to entries without a `pid` (ext_gone_check handles pid entries). `tests/test_perm_mark.py`, `tests/test_ext_gone.py`.
  - ⚠Do not shorten the marker cap again — an unanswered prompt is exactly the row the user must see.
  - ⚠An approved long tool writes nothing until its result, so the marker stays newer than activity ⇒ `perm_rows` clears on an OTel `tool_decision`/`tool_result` after the marker (row `otelEv`/`otelAt` from sessions.py, remembered in `_DEC_AT` since `_otel` keeps only the latest event; ⚠no otel import — STAGE3 order) or a live shell in the cwd for Bash (`tool_busy`, not with `bgs`). Without OTel a non-Bash approved long tool still shows blocked (accepted).
- **A Workflow agent's prompt showed no badge** (A4, `perm_marks.perm_rows`). Cause: the `wait` branch needed a running `sub`; Workflow agents live in `wf[].agents`, not `sub`.
  - ⇒ also fires when a `wf` run has `run` and an agent `st == "run"`; activity = newest of main activity, those agents' `end`, sub idles. Label «subagent waiting for approval».
  - ⚠A wf agent without an int `end` skips the row (fail toward no badge).
- **An MCP elicitation showed no badge** (A5, `hooks/perm_mark.py`). Cause: `elicitation_dialog` wrote no marker.
  - ⇒ hook `_is_prompt` and `scripts/build_plugin.py` matcher accept `permission_prompt|elicitation_dialog`.
  - ⚠Each account's `settings.json` Notification matcher must include `elicitation_dialog` too, or the hook never runs.
- **An account without the perm_mark hook fell back silently** (A6, `sessions_health`). Cause: no check that each signed-in account's settings run the hook.
  - ⇒ `sessions_health` warns once per account label whose Notification hooks lack `perm_mark.py` and whose `enabledPlugins` has no enabled `sidereus@…` plugin (the plugin ships the hook; names only, never values).
- Session-id truncation on screen and in MCP is one function: `_sid8` (sidereus/ident.py:14) · JS `sid8()` (00-core.js:92) (strips session-/rollout- prefixes, leaves uuids as-is). ⚠Never write `sid.slice(0,8)`/`sid[:8]` in a new place — gemini/codex filename ids get cut wrong.
- ★**An external CLI's «cut off» pid is the CLI, not the shell** (2026-09-24). The hook's `os.getppid()` is a short-lived `sh -c`, so it went «cut off» at once ⇒ `ext_hook.cli_pid` walks up past shell/python. ⚠`ps lstart` follows the locale — hook and server both use `LC_ALL=C`, or the pid-reuse check declares a live session dead.
- ★**External CLI rows (Gemini · Codex) open only by `(plat, sid)`** (2026-09-24; clicking Gemini showed Claude's work log). Cause: row click → `openSession(cwd)` → `/api/session/work?cwd=` → the newest Claude transcript in the same folder.
  - ⇒ tid `ext:<plat>|<sid>` → `/api/ext/work` (`sidereus/ext.py ext_work`) → hook-metadata panel (`extBody`). `extTid`/`extTidOf` (35b-worklog-view.js) route row click, attention list, branch tab and popup boot through it. Events: a ring of the last 20 per session (`EXT_EV_N`, event name · tool name · time only).
  - ⚠Do not revive the cwd lookup for external rows · «Copy resume command» only when `plat==='cc'` · diff is labelled «Folder diff». Test `tests/test_ext_work.py`.
- ★**AskUserQuestion on a sibling line showed as «tool»**. Cause: parallel tool_use blocks of one message (same id) are split across lines and only the latest line was read. ⇒ `parse._pending_ask_sibling` — an unanswered Ask/ExitPlanMode on a same-id line. `tests/test_ask_state.py`.
- ★**«per-session compact window» was 1M for everyone** (2026-09-24). Cause: labels were fixed «300K» (Korean 10^4-unit form)/«1M» and keyed on settings.json **mtime**, so an unrelated edit (adding a Stop hook) turned every session «1M». The real value was `autoCompactWindow` 450000.
  - ⇒ `burn._compact_win` reads the value and moves `since` in `DATA_DIR/compact-win.json` {value, since, prev} **only when the value changes**. Session `win` = value if born after since, else prev (none → null → «previous setting»). Screen uses `fmtTok` (45-tokens, the Korean «300K» form removed). `tests/test_compact_win.py`.
  - ⚠The first `since` is seeded from the file mtime (`approx`) — if that mtime was an unrelated edit, earlier sessions show «previous setting».
  - ⚠settings.json is read only. In env, only keys containing `AUTOCOMPACT` and not `PCT` count as the window value.
- ★**Waiting on AskUserQuestion showed «thinking»** (2026-09-24 UX audit, a393bb9a 09:58:18–09:59:48). Two causes: `_sess_state` checked shape=`tool` before `asking` → `tool`; then the same response's OTel `api_request` (→ think) overwrote it.
  - ⇒ `parse` emits `askTool` (unanswered AskUserQuestion/ExitPlanMode on the last assistant line); `_sess_state` returns `ask` for it even when shape=tool · `_session_row` never overwrites `ask` with OTel. Result: attention 90 pts (red) · activity band «needs you». `tests/test_ask_state.py`.
  - ⚠Never turn tool into ask on `asking` (trailing «?») alone — a question mark next to a Bash call becomes a question wait. Permission prompts leave no trace in the transcript; they stay with `_blocked`.
  - ⇒ The header «No sessions need you» appends «N low-priority» when list-only rows (done · bgdone) exist (17-attention `quiet`) — list and header count the same `attnRows()`.
  - ★The same audit's «state since 08:06 AM · 32 s» came from that fake clock. ⇒ Start time = server time (`ATTN.at`) − `ageSec` (42-activity `actStart`) — the same server base as the elapsed time.
- ★**16 finished subagents showed «Running»** (2026-09-24 screenshot). Cause: CLI 2.1.281 carries completion notices in `type=attachment` · `attachment.prompt` (`queued_command`/`task-notification`), but `_running_bg` read only `message.content`·`content` (all 62 skipped). Also, when a session moves to a new transcript (f3f9583a → 729ffb33) notices arrive only in the new file, so old-file rows linger.
  - ⇒ Read `attachment.prompt` too · third ground in `_retired`: the agent log's last user/assistant record has `stop_reason == "end_turn"` and it has been quiet `SUB_DONE_QUIET_S` (300s). Measured 16 → 1 (the one really running). `tests/test_bg_completion.py`.
  - ⚠Do not judge by «last record is text» — streaming blocks have stop_reason `None`/`tool_use`; only `end_turn` separates an end from a long generation or long tool. An open child means not ended.
- ★**A subagent was running but the session's `sub` was empty → the conflict rule went silent** (2026-09-24, b12214b1). Cause: the `sessions()` parse cache, when `_bg_open` is empty, re-reads only when the parent transcript or `subagents/` mtime changes. A resumed agent **appends to its existing log**, so neither changed and `_bg_revive` never ran. Notices are also re-delivered in duplicate (queue-operation · attachment · user) and deleted the resumed row again.
  - ⇒ `agents._subs_newer`: re-read when a sub log is newer than the last parse. `_bg_revive`: if the log grew after the notice and the turn is **unfinished**, revive at once; in that state it survives quiet past `SUB_DONE_QUIET_S` (long tool). `tests/test_bg_completion.py`.
  - ⚠The conflict rule (`file_owner._live_units`) and the drawer (`timeline._tl_live`) both use only `sessions()` `sub` — do not build a separate liveness path. `end_turn` agents still close as before (16 → 1 holds).
  - ★Same day, old transcript f3f9583a stayed «waiting for input» (selfcheck-live warning). Cause: sending to background starts the official pid as `--session-id 729ffb33 --fork-session --resume …/f3f9583a.jsonl`, while the terminal pid `claude --resume f3f9583a` lives outside the official list and gave its path slot to the old file. ⇒ `live_cwds`: if an official pid's argv contains the label sid, mark that pid claimed. `tests/test_live_fork.py`. ⚠Do not widen to «same cwd» — real sessions missing from the official list (case 78979) disappear.
- ★**The session row's «Leftover N» badge only reads the dict `_fail_loop` writes** (2026-09-23 · ADE common verification signal).
  - `_wreck_by_cwd()` (`:3345`) writes cwd → uncommitted-wreckage count into `_WRECK_BY_CWD` in a 60 s loop; the session row (`:8552`) and badge (`.swr`, `:14732`) only read it. 0 draws nothing. Click → `setMainView('fail')`.
  - ⚠Never call `wreckage()` on the request thread — measured cold 0.906 s · warm 0.016 s. On a 2.5 s poll the screen freezes.
  - ⚠**Do not add a separate «Uncommitted N» badge** — the existing `sg` chip already draws `~N` (`_git_state`, `-uno`). Drawing twice shows the same number in two places.
  - ⚠No new colour — `.swr` uses `#f59e0b`, same as `.sz.hot`.
- ★**A logo shows which AI it is — session row and timeline use the same mark** (2026-09-22).
  - Offline, so no images or web fonts ⇒ inline SVG, **20 marks** (`AILG`), emitted by one `aiLogo(plat)`. Paths are the **official simple-icons 16.32.0 marks, verbatim** (2026-09-22; replaced hand-drawn approximations, 3 → 20).
  - 20 keys: `cc`Claude `gm`Gemini `cx`Codex `cp`Copilot `cu`Cursor `cl`Cline `wf`Windsurf `wp`Warp `tr`Trae `zd`Zed `gk`Grok `ds`DeepSeek `qw`Qwen `ki`Kimi `mi`Mistral `ol`Ollama `px`Perplexity `hf`HuggingFace `ma`MetaAI `or`OpenRouter. Hook `platform` → key mapping is the server's `EXT_PLAT` (`:8372`); **change both together**. Adapter `ext-hooks/ext_hook.py` gives new platforms the same standard 7-event mapping as Codex. Session row: **before** the project name; timeline: before the name on session lines and **agent lines** (`tlrk`, after the branch rule · `:17209`) — one per line, like orca. Measured 11×11px · logo 4 + timeline 4.
  - ⚠Do not hard-code colour in the SVG — it is `currentColor`; fill comes from `.ailg-cc/gm/cx`. ⚠Do not enlarge 11px (it aligns the baseline with the adjacent 12px text). ⚠Do not hand-edit paths — re-fetch the simple-icons original if one must change. ⚠**Grok is not in simple-icons** (X Corp trademark) — `gk` borrows the `x` mark. Swap it if an icon appears.
  - ⚠Three traps for external rows (caught in the 2026-09-22 review): ①`EXT_STATE["Stop"]` is **`wait`** — as `ask` it ranks 0 and a finished session holds the top of the list for 24h. ②**Never put `claude` in `EXT_PLAT`** — it is already loaded from transcripts, so the same `sid` becomes two rows and `_sid_proj` is overwritten, making the project name `?` (now blocked as `unknown platform`). ③The resume chip (`:14399`) only when `plat==='cc'` — `claude --resume` does not accept an external `sid`.
  - ⚠The timeline still loads **Claude only** (external CLIs are only in the session list) — that is why `aiLogo` falls back to `cc` for unknown values. If external sessions go on the timeline, fix that default first.
- ★**External CLI (Gemini · Codex) sessions merge into the same list — the hook sends, the server only receives** (2026-09-22).
  - Those CLIs differ in transcript shape and process name — so no scraping; **events are received**: `POST /api/hook` (`do_POST`, next to `/v1/logs`) → registry (`ext-sessions.json`, 24h prune) → `ext_rows()` → joined **just before** the `rank` sort in `sessions()`. Hook adapter: `ext-hooks/ext_hook.py` (shared by both CLIs).
  - ⇒ One key `plat` (`cc` · `gm` · `cx`) on the row; the screen adds only `GM` · `CX` chips (Claude is the majority, unmarked). Measured: 5 synthetic hooks → 2 external rows · survive restart · 0 after `SessionEnd`.
  - ⚠`ext_rows()` must have **the same key set** as `_session_row` (measured 36 vs 36, set difference 0 both ways). One missing key breaks the front end on that row. ⚠`runmin` is a **dict** read as `RM[kind]` — never a number (total run minutes is `runmin.run`).
  - ⚠Do not use `_model_label` for external models — it keeps the first two segments, so `gpt-5-codex` becomes `gpt-5`. ⚠Gemini hook payloads have **no** `model` or `turn_id`, and Codex has no `Notification` — absence is not an error.
- ★**Gemini subagents write separately to `chats/<parent sessionId>/<id>.jsonl`** (2026-10-01; invisible because only `session-*.jsonl` was globbed).
  - ⇒ `plat_gemini._files` collects both shapes and sets `parent` = folder name = parent header `sessionId` (full uuid). Timeline: `subagent` child rows under the Gemini head row; history: summed into the parent row; today's usage: tokens added, not counted as sessions.
  - ⚠The parent file has **no** subagent tokens (measured shared message ids 0 · parent 28.8M / sub 0.83M) — dropping them under-counts. The header has no agent name (only `kind: "subagent"`) — never use the first prompt as a label.
- ★★**Session identity now comes from the «official list», not «guessing» — and the switch once produced
  «alive but missing»** (2026-09-08).
  - **Why.** The argv UUID goes stale after `--resume` + `/clear` (next entry). Two fixes that «bent» stale
    labels by sibling mtime / cwd slug were **after-the-fact corrections of a wrong value**.
    `claude agents --json` gives each pid its **current** `sessionId` ⇒ no guessing needed
    (docs: code.claude.com/docs/en/agent-view.md). Measured: pid 6893 argv `8b12c025` (dead), official
    `be858dca` (alive) · pid 57914 → `5c040e0b`.
    ⚠`~/.claude/projects/<slug>/<sid>.jsonl` is **declared internal and unstable by the official docs**
    (sessions.md). Transcripts are still read but **never used as the ground for identity.**
  - **Where.** `agent_view(ttl=AGENTS_TTL 8)` — dedicated lock + TTL cache. Measured cold 0.16–0.43s
    (`ps` 0.03s) ⇒ **never call it per poll.** On failure, within `AGENTS_STALE_S` (90) the old answer is used
    with `agents-slow` (soft); beyond that an `agents` warning + `None`.
    ⚠**`None` means «unknown», not «none»** — every consumer then falls back to the old argv path.
    A pid with an official answer gets **no** argv guess on top (`if av is not None and pid in av: continue`).
  - ⚠**`status` is not an activity signal.** A session quiet for 5 hours still reports `busy` (measured pids 84637 · 97696
    `idle`). Tool names, subagent lineage and activity times still come only from transcripts.
    `waitingFor`/`state` fields were **not observed** in this build — do not rely on them.
  - ⚠★**Self-inflicted regression — «present reported as absent».** A pid claimed by an official sid is dropped from
    `live_cwds()` path counting (`claimed`). With all 5 pids claimed, `live_cwds()` became **`{}`**.
    But `_recent_transcripts` uses that dict to **revive age-expired transcripts of live paths**
    ⇒ sessions quiet beyond `max_age_h` (12h) would **vanish from the list entirely**.
    The same trap was hit on 2026-08-24 (a session launched and left idle).
    ⇒ `_recent_transcripts` **revives directly by official sid** (more exact than path guessing). Sessions the official
    list does not know leave their pid unclaimed and **cwd counting still covers them** — no overlap, no gap.
    ★Measured: narrowing the window 12h → **0.6h** keeps all 5 official sessions (before the fix, all dropped).
  - ⇒ **Lesson: when changing the source of identity, first count where the value is used «as a by-product».** Here
    `live_cwds()` returns «live path counts», which **empties** as identity gets more exact — a change toward
    accuracy looks like «disappearing» to its consumer.
- ★★**`/clear` after `--resume` — the successor appears under a «different slug». Sibling comparison alone misses it** (2026-09-08).
  No ghost was left; **two rows swapped places** — and the wrong one is the live row:
  - Measured pid 6893 `claude --resume 8b12c025…` · cwd `~/.mailbox-mcp` · started 13:30.
    A home session was resumed here, then `/clear` ⇒ the real transcript moved to `-Users-<user>--mailbox-mcp/be858dca….jsonl`
    (13:37:46) while **argv still holds the old sid.**
  - `live_cwds()` puts the argv UUID in `_live_sids` and **drops that pid from path counting** (`claimed`) ⇒
    ⓐdead `8b12c025` (13:32:42) passes `sid_alive` and stays **«waiting for input»**;
    ⓑlive `be858dca`, written 1 s ago, matches neither path nor sid and falls to **«ended»** (its cwd is absent from `live`).
  - `_sid_claim_stale()` exists for exactly this but **only compared sibling mtimes in the same directory.**
    Inside `-Users-<user>`, `8b12c025.jsonl` was still newest, so the claim was judged **valid**.
  ⇒ Also check the claim against **the process's own cwd slug** — `_sid_claim_stale(sid, cwd)`.
    So `live_cwds()` runs **lsof before sid judgement**, building `pid→cwd` first
    (still 1 call · measured lsof 18–19ms · `live_cwds()` total 126ms). The by-product `_live_pid_cwd`
    now holds **every** claude process (claimed too — `mailbox_watches()` uses that cwd).
  - ⚠**Only «something newer» overturns a claim** (recurring failure shape ②). No cwd slug, or an older one, leaves it alone ⇒
    the normal case at `:766` (home session `--resume` in repo-A) stays valid because the live side keeps writing.
    ★Negative control measured: `_sid_claim_stale(452cb0e4, cwd=repo-A)` = **False** (claim kept) ·
    `_sid_claim_stale(8b12c025, cwd=.mailbox-mcp)` = **True** · same sid with `cwd=None` = **False** (old behaviour).
  - ⚠**The same bug was in `_watch_transcript()` too.** For a stale label it resolved only «the newest file in the sid's
    directory», **attached the watch to a dead session**, and since that row is «ended», `_session_row` cleared mon ⇒
    **a running watch vanished from the screen** (one Sidereus watch on no row). Now the newer of the two directories is used
    (case 10d426f5 has both in the same directory, still correct). After the fix all 5 watches sat on their own sessions.
  - ⚠The verdict depends on cwd, so **include cwd in the `_sid_stale` cache key**.
- **A completion notice may lack `<tool-use-id>`** (measured 2026-09-07).
  `<task-notification>` usually carries both `<task-id>` and `<tool-use-id>`, but **an agent that finished again after a
  resume (SendMessage)** sends only `<task-id>`. In one file, 6 of 56 non-Monitor notices were like that, all the same agent.
  The subagent row (`sub`) is keyed **only by tool_use id**, so nothing matched and it stayed «running» for 71 min.
  The same block's `else` branch does `open_now.pop("task:"+tid)`, but that is the **watch key space**, so nothing was removed.
  ⇒ `<task-id>` = agent id = filename of `subagents/agent-<aid>.meta.json`, whose meta has `toolUseId`.
    Only when `tool-use-id` is missing, reverse-index via `_agent_meta()` and remove.
  ⚠**Monitor heartbeats also lack `tool-use-id`** — `alive` must be excluded. Otherwise every heartbeat deletes a live
    watch — a direct breach of the rule that reporting present as absent is the worse error.
- **A resumed subagent had no row at all** (measured 2026-09-07; 2 subagents running, 1 shown). Two notices arrive
  with the same `task-id` but different `tool-use-id` — the second is the tool_use created by the `SendMessage` resume.
  The parser only made rows from `name == "Agent"` tool_use, and `_bg_popped` blocks reviving the old key, so
  **it is off screen for the whole resumed span.**
  ⇒ ①Create a row keyed by the new tool_use id only when `SendMessage` `input.to` is in **this session's**
    `agent-<aid>.meta.json` (the only guard separating it from sends to other sessions, teammates or the cloud)
    ②that row must also get its meta back via `_meta_of` so `aid` · lineage · depth · idle are filled
    ③a resume tool_result body is not `Async agent launched` — accept only `Resuming agent`/`resumed from transcript`
      as the receipt and exclude `Message queued for delivery` (already running) · `won't be resumed`.
      Without these three the row is **deleted on the very next line** after it is created.
- ★**A resumed subagent kept its original launch label** (2026-10-01; a finished job still showed as running).
  Cause: resumed/revived row labels used only meta `description` — 559ad94f's ad471f1f6e31887bb kept its launch label, so the pipeline tab lit the Reproduce/Cause/Fix stages (actually a `[pl:bugfix/<Fix stage title>]` resume).
  ⇒ `_bg_said` keeps the last SendMessage `summary`; for an agent that moved after it, `_sub_label` uses it as the label (normalised to one line).
  ⚠Only `summary` — `message` is a body, a rule 1 breach.
- **★A constant came from a misdiagnosis — `REVIVE_GRACE_S` 900 → 30** (measured 2026-09-07).
  900 s was set on 2026-09-01 by reading «last record appended +283 s after the completion notice = harness flush is slow».
  Re-measured, that +283 s was **a resume, not a flush** — the first line after the notice was of the
  `The user sent a new message while you were working` / `[Request interrupted by user]` kind (all 179 checked).
  Full scan of **1,536** agents: of those with mtime after the notice, **419 within 1.1 s, 0 between 1.1 and 120 s**;
  the two larger ones were real resumes. So the real measured maximum flush delay is **1.1 s**.
  ⇒ Lesson: **when two or more hypotheses explain an observation, picking one and freezing it into a constant turns that
    constant into a defect in the opposite direction.** 900 s was a device that «hid resumed agents for 15 min». When setting a
    constant, measure what the observation actually was (here, «the content of the late line»).
- ★★**Blocked/denied background commands stayed «running» forever** (2026-09-08).
  A triage-bot card showed two «command Rebuild and start svc-D container» rows for 21 and 18 min.
  In reality `docker ps` showed `svc-D Up` (healthy) and `ps` had **no** build/compose process.
  The log had the same command three times:
  ```
  23:42:24 → 23:43:00  "Devil's advocate - 2 unverified claims…"   ← blocked by a hook; never ran
  23:45:03 → 23:45:44  "Devil's advocate - 1 unverified claim…"    ← blocked by a hook; never ran
  23:46:03 → 23:46:08  "Command running in background with ID: …"  ← actually started
  ```
  A `bg` row opens on `tool_use` alone (`name=="Bash" and run_in_background`) and closes **only on the
  `<tool-use-id>` of a `<task-notification>`**. That rule is right — a bg `tool_result` is a receipt; counting it as done makes it
  **0 the whole time it runs** (that comment is at the top of `_running_bg_locked`). What was missing is
  **the third case, a `tool_result` that is not a receipt**: blocks, denials and errors also get a `tool_result`, but
  no task was ever created, so **the notice never comes.**
  ⇒ If the `tool_result` is `is_error` and lacks the receipt marker (`running in background with ID`), remove it on the spot.
    `_bg_pop(..., done=False)` — keep `_bg_popped` to block revival but **do not count it as done**
    (turning something that never ran into a «work done» card claims a run that did not happen).
  - ⚠**Never remove on `is_error` alone** — if a version ever flags the receipt, **running commands get deleted.**
    Check the absence of the receipt marker **too**. Push toward neither extreme (always keep / drop on any result).
  - ⚠**No phrase whitelist** — 4 causes appeared in 7 days (hook block 9 · user denial 2 ·
    model temporarily unavailable 1 · Claude Code permission denial 1) and each new kind would leak again. `is_error` is a harness
    flag, kind-agnostic (measured 13/13 true, no overlap with 513 receipts).
  - ★**Third time this shape was hit in this file**: ①an Agent `tool_result` is a receipt ("Async agent
    launched") ②a resume (`SendMessage`) receipt has different wording ③a blocked bg `tool_result` is
    not a receipt. **Check the marker separating receipt from result every time.**
  - ★Live check (2026-09-08): both rows gone after restart. Attribution split too — the third (executed) had 2 notices and
    the existing path closed it; **the two blocked ones had 0 notices** and the existing path would never close them.
- ⚠**«To terminal» for Orca** (2026-10-08, `sidereus/term.py` `_focus_orca`; unverified live — Orca not installed here).
  - The `ORCA_TERMINAL_HANDLE` is runtime-scoped: stale after an Orca restart. ⇒ a failed `terminal switch` falls back to `open -b com.stablyai.orca` (how `app`, hint `handle`).
  - The CLI exists only after Orca › Settings › General › Orca CLI; Linux names it `orca-ide`. launchd's PATH lacks Homebrew/`~/.local/bin` ⇒ `_orca_cli` searches them explicitly.
  - ⚠Never call `orca terminal list`/`show` — their output carries a `preview` of terminal content (rule 1). The handle stays server-side; `row.term` never carries it.
- ⚠**«To terminal» failures looked like a permission problem** (2026-10-12; viewer.err «terminal tab lookup failed (TimeoutExpired)» at load 9–62, `sidereus/term.py`).
  - Cause: `_probe` dropped a cache entry at TTL *before* re-probing, so one `ps -E` timeout + 30 s fail cache = term None; and every 400 / osascript timeout reached the page as how `error` = «no permission».
  - ⇒ A failed re-probe keeps the old entry (a pid's tty never changes; gone only when ps answers without it). A click on a row with no term re-resolves once (`_resolve`, forced probe). Missing row / bad tty = 200 how `notfound`; osascript timeout = how `timeout`; the page shows the permission text only for `-1743`.
  - ⇒ Every failed jump but `off` goes to viewer.err as `term-jump-<how>` with a running count (`tests/test_term.py`).
  - ⚠Do not return 400 from term focus again — `postJSON` throws and the body's `how` was read as a permission failure.
- ★**A queued `SendMessage` result is not a completion** (2026-10-05: 3 running agents listed in the bell's «17 done»). «Message queued for delivery …» to a running agent closed the SendMessage row with `done=True`. ⇒ In `_bg_on_result`, a resume row whose result is not `_RESUME_OK_RE` closes with `done=False`; the agent's own row stays until its notice (`test_queued_message_to_running_agent_is_not_a_completion`). ⚠Never count a SendMessage tool_result as an end — only `<task-notification>` is one.
- ⚠**Extra Claude roots (accounts) share slugs** (`sidereus/claude_roots.py`). The same cwd can have transcripts in two roots; one slug dir per root.
  - ⇒ cwd/sid lookups (`live._newest_slug`, `live_probe._sid_transcript`, `cards._recent_transcripts` revival, `work._slug_files`) take the **newest mtime across roots**; a `/clear` successor is looked for in the **claimed file's own root**.
  - ⇒ The work/history path guard is `work._under_projects`: realpath strictly under one `projects_dirs()` entry. ⚠Never widen it to the root dir (`settings.json`, credentials sit there).
  - Team files and the window-learning cap come from the transcript's own root (`agents.team_info`, `live_win._root_hist`). Rows get `acct`/`acctDir` only for a non-primary root — single-root output is unchanged.
- ★**A run that reports via `SubagentHandback` ends on a `tool_result`, not on text** (2026-10-05: 90 of 94 timeline rows «cut off without a report»). `_agent_ended` treated any trailing tool record as still working. ⇒ Ended when the last tool_result is a non-error answer to a `SubagentHandback` tool_use (`tests/test_agent_ended_handback.py`). ⚠Do not widen this to other tools — a pending or failed handback is still running.
- **An idle session showed «think» after auto-compact** (`sidereus/parse.py` `_scan_tail`).
  - Cause: the compact summary is a `user` line (`isCompactSummary`, string content); as the newest user line it mapped to shape `result` = think, and its text could become the task label.
  - ⇒ `_scan_tail` skips `isCompactSummary` lines for shape and task; the turn markers and assistant line before the boundary decide (`tests/test_compact_state.py`). `act_at` still counts it.
  - ⚠Never let the summary text reach `task` — it is conversation content (Rule 1).

## Work-log popup and diff window

- ⚠**Whole-file diff: the change arrows need a sticky header** (2026-10-13). «▾ Show the whole file» in the unified view adds ▲▼ (`dfNav`, 30-diff.js) that scroll the next/previous run of +/- rows to a third of `.dbody`. Without `.dfh.dfhs{position:sticky}` the arrows scroll away with the file. ⇒ The step is read from the scroll position each click (no stored index), so a manual scroll is respected; ends wrap. Only one `.dfx` keeps `margin-left:auto` (`.dwnv ~ .dfx`), or the buttons spread across the row. Commit history above the diff folds to one line (`dfHistOpen`, ui pref `sidereus.dfhist`, folded by default). Test: `test_diff_change_nav_js.py`.
- ★**Diff window counted files from the cut patch** (412 KB commit cut at 220000 B: «6 files» vs `git show --stat` 30; this repo's 111babd: patch 7 vs 29 files, +2603/−2264).
  - ⇒ `git_diff` sends `numstat` (`--numstat -z -M`, cap `STAT_FILES_MAX`) + `numstatN`; `dfFiles` (30-diff.js) takes counts from it and marks files past the cut «patch cut», the cut-through one «patch partial».
  - ⚠Key is `numstat`, not `files` — `files` means the rail view (`test_git_rail`). Branches commit detail uses `-M` too; a rename's patch needs both `:(literal)old` and `:(literal)new`, or git shows an added file.
- ★**Work popup had no total size cap** (2026-10-05 synthetic: 400 MultiEdit steps → 96,240,940 bytes; per-step caps alone allow 240k chars).
  - ⇒ `steps._cap_edit_bodies` spends `AGENT_EDIT_BUDGET` (2M chars) newest step first; older steps drop `edit`/`edits`, get `editCut`, and the response carries `cutEdits` (popup head «edit bodies of the first N steps cut»). After: 1,975,134 bytes.
  - ⚠Do not remove step metadata to save bytes — only edit bodies are cut; every step stays listed.
- ★**Resumed agent: `sub.tid` = the SendMessage tool_use id ≠ meta `toolUseId` → «Could not find that subagent's record»** (2026-10-02 live: row `toolu_01B3…` failed, meta `toolu_017DS…` opened the same agent).
  - ⇒ Open by agent id: `subWorkId(v)` (35b) sends `sub.aid`, falls back to tid; `agent_work` also matches the meta `_id` (strict `^a[0-9a-f]{6,40}$`, lookup only, never a path).
  - ⚠Do not key a work popup on `sub.tid` — it changes on every resume.
- **Work items join an open work popup as tabs** (`wkPopup` → `wkHostOf`, 35c; popup side `wkReopen` 35b · `wkHasTab` 65).
  - ⚠Cross-window lookups must go through functions: top-level `let wtabs` is not a `window` property, so the main window calls `POPS[k].wkHasTab()`.
  - ⚠A moment (`&at=`) window is never a host — `workUrl` applies `at` to the popup's first tid, so a live click on that tid would show the frozen window.
  - ⇒ Shift comes from a capture-phase click/Enter stamp (`WKSHIFT`, 1.5 s) since callers pass no event. A throwing cross-window call falls back to a new window.
- ★**diff popup head `undefined`, body «Only repositories touched by a session on screen…»** (2026-09-23 usability audit). Cause: with session `repos` = `[]` (not git · no repo touched), `loadDiff`'s `(repos||[cwd])[0]` is `undefined` → request with `cwd=undefined`.
  - ⇒ `repos[0]` only when `repos.length`, else `cwd`. The allow check stays on the server (`git_diff` · `_repo_ok`) — the popup gets SESS first via `poll(true)`.
  - ⚠An empty array is truthy — `x||default` cannot guard an empty list.
- ★**The work-log split has N panes** (2026-09-23 · generalised from the 2-pane `wtActive/wtActive2`). Layouts «single · 2 side by side · 2 stacked · 3 columns · 2×2» = `WT_LAYOUTS` · state `wtPanes[]` (tab key per pane) + `wtFocus` (1-based).
  - ⇒ Switch `wtSetLayout` · swap `wtSwapPanes(a,b)` · paint `workPaintSplit` (CSS grid, `.wsd[data-ax][data-i]` on 9px gutter tracks). `wtSplit` is derived («2+ panes») — never assign it directly.
  - ⚠Stored in `mbWtLayout` · `mbWtFr` (fr per layout). Old `mbWtSplit=1` + `mbWtDir` are read as h2/v2 only when `mbWtLayout` is absent.
  - ⚠Pane scroll is kept **by tab key** (`.wpb[data-k]`) — keyed by pane number it jumps on swap or layout change. Below 700px everything stacks vertically.
  - ⇒ Empty panes are filled from `wtPickHtml` (SESS sessions + subs with a tid, metadata only). ⚠The pane `mousedown` repaint swallows the pick click, so `[data-wpk]` is skipped.
- ★**All Edit/Write changes in the work log were collapsed — two paths draw edit blocks and the default-expand rule was in only one** (2026-09-22).
  Cause: only `wroteBlock` (Bash · cumulative git diff) expanded by default; `editBlock` (Edit/Write) opened only «what a person clicked».
  ⇒ `editBlock` expands by default too. ⚠`wroteBlock`'s «last edit spot only» condition exists because **git diff is cumulative** — Edit old/new are not duplicates, so do not add it there. Only the length cap (300 lines) and count cap 40 apply, and **the `autoN` counter is shared by both paths** (counted separately → 80 on one screen).
  ⇒ Closed set `agEditShut` + previous render value `agEditWas` (recorded as «a person's choice» only when it differs from the DOM). ⚠Do not key open state on render order — after switching sessions the same number points to another file. Key is now `step time|file path|index`.
  ★Measured 40 of 45 blocks expanded = 11,920 lines · re-render 50ms (2.5 s poll). Over-cap and over-300-line blocks collapse with «over the 40-block expand cap» · «folded, too long» in the summary.
- **Session row `wt` = [prompts that waited on the person, seconds]** (`timeline_scan._scan_lines` → `_sess_waits` after `_sess_segments`, read by the Timeline «Window summary» «Waited on you» row).
  - A human prompt = `"type":"user"` line without `"type":"tool_result"` or `"isMeta":true`, ≥ `WAIT_MIN_S` (30 s) after the previous timestamped line; the wait is clipped to `cut`.
  - ⚠Matched by markers only — message text is never parsed or kept (rule 1). The key is omitted at 0 so goldens stay byte-equal.
  - ⚠The previous line includes `queue-operation` (a prompt queued while the model ran did not keep it waiting); `_SEG_RAW` carries `hp_all` + `last` so an appended chunk still sees its predecessor.
