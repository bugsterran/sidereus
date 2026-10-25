# Traps — General lessons

Conventions (entry shape, `★` `⚠` `⇒`, `§N`, `:NNNN`): [TRAPS.md](../TRAPS.md). Newest first within an area; new traps go at the top of their area.

## General lessons

- ★**«Float up and overlay» (`float` + negative margin) reserves an overlap** (§31). A neighbour's length is set by data —
  put hints and badges in as **siblings in the flow**. CSS whose overlap must be checked by eye is already wrong CSS.
- ★**Verifying screen code without opening a browser**: **lift the function fragment verbatim** from `<script>` and run it
  with `new Function(...)` in node on real data (`/api/state`). Retyping it is different code and proves nothing.
  ⚠Cutting fragments by regex **breaks on nesting** (`function staleThreads(){…}` did) — **count bracket pairs.**
  Searching for `{` on something that is an array like `const KIND = [...]` swallows unrelated code (measured: `DONE` duplicate declaration error).
- ★**«Drawn on the screen» and «visible on the screen» differ** (§24). This page scrolls to the bottom on open, so anything
  at the top of the document is **never seen.** A DOM existence check (`querySelector`) never catches it —
  **measure coordinates** with `getBoundingClientRect()` (negative y = off screen).
- ★**Never hard-code a sticky element's `top`** (§24). Header height changes with added bars (toolbar).
- ★**Judging «unfinished» by tag alone misreads finished work as abandoned** (§22). In data that predates the convention,
  *no marker* and *really not closed* are indistinguishable. ⇒ Add a time cap and **state the cut count on screen.**
- ★**Some files' fingerprint is the contract** (e.g. a shared charter document). Even a typo fix or title change breaks it.
  To edit, announce it in the room and record it in the §7 revision history (§23).
- ★**A repainting list + «close on outside click» fight each other** (§17). If the click handler replaces the DOM,
  the element is already gone when the event reaches window. ⇒ Use both `stopPropagation` and `document.contains`.
- ★**Error-reporting paths never run normally — so they stay wrong for a long time.** `_warn_once` (a nonexistent name) was
  in 5 places, and when an exception occurred **the report raised a second exception**, hiding the cause (§15ⓐ).
  ⇒ When writing a new `except`, **force that path once** (make `subprocess.run` throw and call it).
- ★**launchd runs `/usr/bin/python3` (3.9.6).** That **differs** from the homebrew 3.14 · venv 3.11 used for testing in a session.
  One line of `match` or `X | None` dies **only under launchd** (there is no 3.10+ syntax now).
  ⇒ After editing, pass `/usr/bin/python3 -m py_compile chat_server.py`.
- ★★**`node --check` only parses — it cannot catch a runtime TDZ death** (measured 2026-08-19:
  `const lost` was declared **below** its use, so `buildSessions()` threw every poll and
  **the Claude session panel went entirely blank**. Parsing, py syntax and server responses were all fine, so it was invisible).
  ⇒ After changing row-assembly code, **actually run it**: lift the `rows.map(x=>{…})` body from `<script>`,
  build it with `new Function('x','esc',…)` and pass a few fake sessions through (unresponsive · running · watch-only · empty).
  Declare **before use** — the only way never to hit it.
- ★**A JS identifier clash kills the whole page.** A new `KIND` declaration collided with the existing `KIND` (tag classes),
  script parsing failed and the screen did not render at all. ⇒ **Always after editing**:
  ```
  curl -s localhost:8799/ | python3 -c "import re,sys;print(re.search(r'<script>(.*)</script>',sys.stdin.read(),re.S).group(1))" > /tmp/p.js && node --check /tmp/p.js
  ```
- **Polling is 2.5 s** — server collection must finish within it (currently cold ~124ms · parse-cache hit ~1ms).
  To hold up as sessions grow: one `lsof` + a `(path, mtime)` parse cache + a 20 s git cache.
- **Conversation content is not moved onto the page** — the session panel is metadata only; only card bodies carry a reply summary (allowed: the user's own machine, a local page).
- Without `cwd`, the project name **restores the path from the folder slug** (`-Users-<user>-repo-A` → real path).
  Previously it fell to `?` and looked like «session not showing». Hyphens can be part of a name, so it backtracks **longest child first**.
- ★**View-state keys go through `tabGet`/`tabSet` (08-ui-kit), never `lsGet`/`lsSet`** (2026-09-29; with several Sidereus tabs open, each refresh jumped tabs). Shared localStorage made every Sidereus tab jump to the last-saved view on refresh. ⇒ sessionStorage first (per tab, survives refresh), localStorage as the default for a brand-new tab; tone/language/sizes stay shared. ⚠A new view-state key written with lsSet brings the jump back.
- ★**`mmdSpread` must count 2-point (straight) routes as fixed slots** (2026-09-29, FLOW fixture a3->b2 overlapped a2->a3 by 40 px on the diamond). Skipping `p.length < 3` hid the straight line, so the other end was re-centred onto it. ⇒ straight ends stay put, the rest slide around them. ⚠Re-adding the skip brings the overlap back (`test_diamond_ports_not_shared`).
- ★**A `document.write` popup must copy `html` dataset from the main page** (2026-10-02; the flow popup background ignored the theme). The CSS keys on `html[data-theme|tone|ui]`; the written popup had a bare `<html>`, so it stayed on default colours. ⇒ `strWinTheme(w)` after write, and `setTheme` re-syncs + repaints every open window in `strWins`/`strFlowWins`. ⚠A new popup skeleton without it loses the theme again.
- ★**First-run defaults** (2026-10-05, fresh HOME + headless en-US). UI was Korean whatever the browser said; Gemini rows came from the account's real `~/.gemini` under an overridden HOME; `setup-claude` printed the CommandLineTools path behind the `/usr/bin/python3` shim.
  - ⇒ `langPick` (05-i18n): a saved `mbLang` wins, else `navigator.language` `en*` → en. `plat_gemini.root` honours `GEMINI_CLI_HOME` (the Gemini CLI's own variable; `.gemini` sits under it). `sidereus_cli.setup_python` prints `/usr/bin/python3` only when it runs the same interpreter.
  - ⚠Do not set `<html lang>` for this — it swaps CJK fonts (see `sesdrLang`, which uses `data-lang` instead).
  - ⚠The sessions empty hint lives in the `!SESS.length` early return (40b); lines after it never render with zero sessions.
- ★**Infinite CSS animations: opacity/transform only, and paused when hidden** (2026-10-05, headless 60 s idle on the timeline tab: TaskDuration 8.07 s → 0.65 s, style recalcs 3895 → 553).
  - Cause: `tlpulse` animated `box-shadow` on running bars, and the closed sessions drawer (`visibility:hidden`) kept its status dots (`pl`/`pl2` box-shadow, `dots` content) running.
  - ⇒ Glow is a static shadow on `.tlbr::after` with only opacity pulsing (20-timeline.css); everything inside the closed drawer gets `animation-play-state:paused` (92-sessions-drawer.css).
  - ⚠`visibility:hidden` does not stop animations — only `display:none` or a pause does.
- ★**Relay/copy inputs: bound what the user typed** (2026-10-05, headless QA). A name `-x` passed `brPwCheck` and became `claude -w -x` (read as an option); a failed `/api/dm` cleared the previous run's lighting before the ok check; a 200-char saved-view name widened the right-anchored `.vwpop` to ~1786 px, off the left edge.
  - ⇒ Worktree names must start `[a-z0-9]` (89); `plRunSend` clears PLSEEN/hidden rows only after `j.ok` (48b); `.vwpop` max-width `min(360px,90vw)` + names cut at `VW_NAME_MAX` 60 (97); the DM request is bounded by «» since it may contain `'`.
  - ⚠Notification `requestPermission()` resolving `'default'` means dismissed, not denied — asking again works (43 `ntfSet`).
- ★**Server down: held numbers must look held, and the poll must back off** (2026-10-05, headless demo, server killed 50 s). Numbers stayed full-strength with only «disconnected»; `loadWku` replaced `WKU` with `{err}`, so the KPI card read «live 0/min» and lost «today 400M», and the token tab sat on «measuring…»; ~55 failed requests/min (state 2.5 s + live 3 s).
  - ⇒ `CONN` + `connMark`/`connWait`/`connAge` (60-statusbar): `html.agstale` dims the status bar, chip and popovers say «as of N min ago»; backoff 5→10 s cap, reset on first success (a 30 s cap took ~23 s to see a restarted server); `loadLive` skips while down; `keepGood` keeps the last good `WKU`/`WKR`; token tab with nothing held shows a failure line + «Retry». Bad JSON / non-2xx = «response error».
  - ⚠Do not assign `{err}` over a good snapshot again — every reader (status bar, token tab, sidebar) draws it as zero (`test_conn_stale_js`).
  - ⇒ Hidden tab: `loadTl`, `burnTick`, `loadWku` (non-forced) and `actTick` return while `document.hidden`; the boot's `visibilitychange` → `poll()` refreshes them once on return (their own throttles decide).
  - ⚠The backoff deadline is marked from the request start (`t0`, minus 250 ms slack), not the failure return — marking from the return made the 2.5 s tick skip a round (measured gaps 7.5/10/12.5/12.5 s past the 10 s cap; `test_real_retry_gap_within_cap`).
- ★**Git paths in patch headers are not plain text** (2026-10-05, temp repo: renames with spaces + Korean name + binaries). Diff window said 8 files +4 −1 vs `git show --stat -M` 6 files +3 −1 — false «patch cut», duplicate row, «(unknown)».
  - Cause: `+++ b/<path>` ends in a TAB when the path has a space, and non-ASCII paths are octal-quoted while `core.quotePath` is on.
  - ⇒ `GIT_SAFE_OPTS` carries `-c core.quotePath=false` (gitinfo); `splitDiff` reads paths via `gitUnq`/`dfHdrPath` from the header before the first `@@` (30-diff, `test_diff_split_js`). Full-file expand of a renamed file passes `-M` and both paths (git_view).
- ★**One data attribute, one action** (2026-10-05). «+ Stage» and «+ Custom stage» shared `data-pladd` with the project button, so the 48 router also opened the «Add project» modal on every stage add.
  - ⇒ Project button is `data-plprojadd` (48, 48f refocus); `test_pipeline_palette` asserts a stage add opens `#plbr` 0 times.
- ★**BOM support has to reach every reader of the same file** (2026-10-05). 8e79719 made the shared reader accept a UTF-8 BOM but `cc_settings` (read + byte splice) and `mailbox_config.load`/`prefs` still used plain `utf-8` — «Preferences» showed «not valid JSON» while the tools list read the same file fine.
  - ⇒ `utf-8-sig` there; `_splice` strips the BOM to parse and writes the same 3 bytes back (byte-exact). ⚠`plugin/mailbox_config.py` is a built copy — rerun `scripts/build_plugin.py` after editing the root file (`test_plugin` fails otherwise).
- ★**Secret masking must walk the whole MCP entry, and file views must resolve symlinks** (2026-10-05, sandbox). The tools tab masked a fixed key list, so `headersHelper` and `oauth.clientSecret` showed in clear; the harness hook card returned script text unredacted (`ghp_…`, `sk-ant-…`); `/api/tools/file` followed a symlink in `agents/` to an outside file and to a `.jsonl` transcript (rule 1).
  - ⇒ `mask_mcp` masks `headersHelper` and any key matching secret/token/key/passw(or)d/auth/credential, recursing into nested values; `harness_file` runs `redact()` on hook text; `tool_file` refuses a realpath outside `CLAUDE_DIR`/the item's project and any `.jsonl` (toolinv, harness).
  - ⚠A key containing «auth» is masked whole — `oauth.clientId` is hidden too. Keep it that way.
- ★**`sidereus stop`: a timeout is not «down»** (2026-10-05, empty HOME, /api/state 5/20 over 2 s, max 6.5 s). `answering()` returned 0 for timeout and refused alike, so `stop` deleted the pid record of a live server (unstoppable afterwards) and `start` reported «no reply in 10 s» while up.
  - ⇒ timeout = `BUSY` (-1): `stop` keeps the record if the pid outlives `STOP_WAIT_S`; `start`/`wait_up` keep waiting (20 s) and never spawn a second server (sidereus_cli).
- ★**JS `slice` cuts UTF-16 units** (2026-10-05). A tag of «a» + 10 emoji was cut mid surrogate pair; the lone `\ud83d` reached `room_tags` and the utf-8 write raised → HTTP 500.
  - ⇒ `Array.from(x).slice(0,20)` (code points, same as Python `len`); the server refuses lone surrogates with 400; dedupe is case-insensitive on both sides so the confirm preview equals what is saved.
- ★**Pipeline: a node's glow washes out the edge end** (2026-10-05, 1440/1100 dark+light, glow frozen at peak). The running edge met the border geometrically (0 px), yet looked cut short: HTML nodes sit above the edge SVG, so the running node's breathing box-shadow (up to 24+7 px) covered the line's last pixels (contrast at the border 37 dark / 34 light).
  - ⇒ `plHeadsSvg` redraws the last 32 px of the running edge in the heads layer (above nodes), clipped to end at the border (`.plrin`, 48d); border contrast 94 dark / 87 light.
  - ⚠Do not "fix" such a gap by moving the endpoint into the box — the geometry is right; the glow is what hides it.
- ★**A state cue made by opacity fails contrast** (2026-10-06 UI/UX sweep). Dimming a whole element blends its text into the background: skipped pipeline node 2.72:1, «N low-priority» 2.53:1.
  - ⇒ Show the state with colour or a border at full opacity (a muted text token, dashed border): skip node 6.11:1, «N low-priority» 5.80:1.
  - ⚠Do not bring back `opacity` for «off / skipped / below» states. If text has to be dimmed, measure it at 4.5:1 or more on both themes.
- ★**A stored «run» is not proof a stage is running** (2026-10-07, two sessions idle with 0 subagents still showed 2 stages «running» each). The hook writes «run» on entry but gets no event when work stops: a backward move without onFail left the stage open, and an idle session never closes its cur stage.
  - ⇒ `pl_runs._close_stale` decides at read time: live agent / main marker / busy session = run; ask or perm wait = «Paused»; idle with every agent finished = done; stages after cur = back. A `git commit` closes the open run.
  - ⚠A new run (no current stage — first tag, a run opened by [pl-skip:], or after IDLE_S 6 h idle) that starts at a later stage is denied until the earlier stages run or are declared skipped (`hooks/pl_flow.py` `_jumped`). Before 2026-10-07 it passed silently and the run never finished («4 / 5 · latest run»). A late tagged stage (e.g. a commit) after 6 h idle is therefore denied too — declare the skips.
  - ⚠Session busy is session-wide: credit it only to open runs holding a live agent / main marker; the newest open run gets it only when none does. Giving it to the newest run always kept a finished Fix stage «running» (all 4 agents done) while another open run's agent in the same session was working (2026-10-07, `pl_runs.pl_model`).
  - ⚠A finished subagent whose log ends on a non-end_turn record (e.g. `user`) and was re-opened by a revive stayed «running» for up to 2 h (RUN_STALE_S), lighting finished stages «running» (2026-10-07, the Verify · Review stages beside a live Live check stage). ⇒ `_retired` also retires an agent whose completion notice was consumed, not resumed since, and quiet for SUB_DONE_QUIET_S (`sidereus/bgtasks.py` `_notice_consumed`). The main marker is not attached to a run whose `end` is set — it kept an ended run's tab dot blinking.
  - ⚠A denied tagged `git commit` Bash must not close the run (2026-10-08: commit retries alternated «You skipped <Verify>, <Review>» / «You skipped <Design>, <Implement>» forever, stage titles in Korean). The close ran even on a deny, so each `[pl-skip:]` opened a fresh run and the retry was checked against it.
    - ⇒ `main` skips `_commit_close` when `_flow` denied; `_declare` attaches a skip to the open run (a stage at or behind its cur = no-op), and opens a new run only when none is open (ended or IDLE_S idle).
  - ⚠A main-run last stage must not set `end` at its first tagged Bash (2026-10-08: the Live check stage read as ended while main was still restarting/checking — an ended run never takes the main marker).
    - ⇒ `pl_flow` keeps it «run» with `tail = <stage>` (exempts it from the untagged-SendMessage deny); a `git commit` closes it, or `pl_runs._close_stale` reads it done once no marker/agent is live and the session is idle.
    - ⚠Without a commit the hook never sets `end` until IDLE_S (6 h): a new request tagging the first stage within that window reuses the old run as a backward loop. Ship (commit) before starting the next request, or let the commit-free tail time out.
    - ⚠A fresh Agent dispatch to an earlier stage while a run sits on its last stage opens a new run (unless that stage's onFail goto names it); continue the same agent with SendMessage to stay in the run.
  - ⚠Main's `Bash(run_in_background)` leaves no sub row — an idle-looking session with one shows the stage as done. Do not "fix" it by trusting the stored «run» again.
- ★**Tests built on the real clock drift with the date and the time zone** (#22). Fixtures from `time.time()` against a module that also reads the clock, fixed ISO stamps against a moving `now`, and the live boot time each let a test pass today and fail later or under another `TZ`.
  - ⇒ `tests/_clock.py`: `frozen(*mods)` swaps each module's `time`/`datetime` for `NOW`; fixtures derive from `NOW`; temp files get `os.utime(p, (NOW, NOW))`; `agents.boot_time` is stubbed.
  - ⚠`from time import time` is not covered by `frozen` — patch that name. Run touched tests under `TZ=Asia/Seoul` and `TZ=UTC`.
  - ⚠A module whose wait loop computes a `time.time()` deadline never times out under `frozen` (the test waits for the stub instead) — give it a ticking clock that starts at `NOW` and advances by `time.monotonic()` (`tests/test_sessions_cached.py` `_TickingTime`).
- ⚠**A test module importing `sidereus` before `tests._load` read the live data dir** — `sidereus.config.DATA_DIR` froze on `~/.mailbox-mcp` for the process and `ext_store`/`bgtasks_parse` loaded the real `ext-sessions.json`, `bg-alive.json` at import.
  - ⇒ The isolation env (`MAILBOX_DIR` temp, `CODEX_HOME`, `SIDEREUS_HOOK_NO_PID`) lives in `tests/__init__.py`, which runs before any `tests.*` module; guard `tests/test_import_isolation.py`. ⚠Do not move it back into `_load.py` only.
