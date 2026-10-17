# Sidereus — developer handover

What the viewer is, how to run and check it, and the feature record. Traps: [TRAPS.md](TRAPS.md) (index of `traps/`) · file map: [FILEMAP.md](FILEMAP.md) · rules: `AGENTS.md` (it wins over this file).

## What it is

- Session control viewer at `http://127.0.0.1:8799`, started by launchd `<label>.viewer` (labels are `<label>.<job>`: viewer, watch, databackup; the prefix comes from config `launchd_labels`).
- Entry `chat_server.py` · Python body in `sidereus/<domain>.py` · screen in `web/`, assembled into one inline PAGE at import (`_load_page`) ⇒ **restart to apply a UI change**.
- Git remote `origin` is a private GitHub repo; the orchestrator commits and pushes only when the owner asks (agents never push; Sidereus itself never runs git write commands). Run `bash backup.sh` after a change (keeps the last 10).
- Separate owners: this folder (viewer) is one session; other projects have their own sessions. Their files do not overlap.
- ★**Name** (owner decision 2026-08-19): «Mailbox» → «Agora» (a square: the place where agents exchange messages), since renamed **Sidereus** (2026-10-13). It started as a viewer for inter-session chat; session control, alarms and stale-thread detection now sit on top, so «mailbox» no longer fit.
  - ⚠**Only screen and document names changed.** `mailbox_*` tools · `MAILBOX_ME/SELF` · `~/.mailbox-mcp` · launchd labels · `bus.jsonl` stay as they are — they are baked into every session's config, and one wrong identity setting once swallowed messages (2026-08-07).
  - ⛔`advocate/CHARTER.md` was **deliberately left alone** — its sha256 **fingerprint is the contract** (§3 · §7), so even a one-line title change makes advocate report "the rules were changed behind our back". To rename it: announce in the room first and record it in §7.

## Run and check

```
restart   launchctl kickstart -k gui/$(id -u)/<label>.viewer
check     curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8799/api/state
backup    bash backup.sh
stderr    viewer.err          # append-only — old lines are fossils
```

- Gates before a restart: AGENTS.md rule 3 (`/usr/bin/python3 -m py_compile` + `node --check`) · `bash scripts/check.sh --fast` · tests `bash tests/run.sh`.
- ⛔**Do not open a browser** — the user's tab is already open; tell them to refresh.
  - The plist carries `--no-open` — without it **every restart opened a new tab** (10+ times on a coding day).
- ⚠**Verify on the rendered page**, not on `/api/...` responses (the API was right while the screen was wrong, more than once). Tell the user to refresh; to look yourself, open `http://127.0.0.1:8799/` with playwright.
- After a code change the user's tab shows a **stale-build banner** (§7) — that replaces "please refresh".

### Dependency and runtime audit (monthly + before a release)

- Run: `/usr/bin/python3 scripts/deps_audit.py [--offline]` — `OK|WARN|FAIL item — detail`, exit 1 on FAIL. Full flow: pipeline `deps-audit` (Check → Triage → Update → Verify → Live verify); run `security-checks` alongside it the same month.
- FAIL = a non-stdlib Python import or a non-`node:` `.mjs` import. WARN = runtime past or within 180 days of EOL, or behind the latest patch, or an OSV.dev advisory (online lookups).
- The EOL table in the script carries a `★source + date checked` line; refresh it from the online output.
- ⚠Online by default after a 3 s probe (endoflife.date, OSV.dev for npm packages — not the CPython/Node/Chrome runtimes); unreachable or `--offline` = a «skipped» WARN, never «no advisories». Tests (`tests/test_deps_audit.py`) use tmp files, no clock or network.
- ⚠A runtime switch (launchd interpreter, Node major) is an owner decision — the audit and pipeline only report it.

## Feature log 2026-08-19 (§1–§37)

Kept as recorded. Written against the single-file `chat_server.py`: `:NNNN` line refs and "`chat_server.py` alone" wording predate the split — grep the name.

1. **Input row width·send button** — same grid as the conversation column (`#composein`, same max-width/columns as `.wrap`).
2. **"↓ New" position** — inside `#compose` with `absolute; top:-42px` (it used to be fixed and covered the send button).
3. **Claude session panel** (sidebar) — `sessions()` tails `~/.claude/projects/<slug>/<sessionId>.jsonl`.
   Six states: `Running a tool · Thinking · Awaiting answer · Replied · Aborted · Ended` (+`Unknown`).
   - **Liveness is decided by process** (one `ps`+`lsof` call · set of cwds). mtime does not work — while a 5-minute tool runs
     no lines are appended and the session turns "grey while working".
   - `run/wait` is decided by **the shape of the last event** (tool_use → model's turn / assistant text → person's turn).
   - Ended sessions are folded (`▸ Show N ended`), the list scrolls at `max-height:46vh`, sorted state first → most recent.
4. **Alarm (bell)** — header bell (line icon) + badge, dropdown history, **5-second toast**; `Mark all read` clears only the badge.
   - Card creation: (a) automatic (when a session moves from `tool/thinking` to `replied/awaiting answer/aborted`) (b) `card.sh`.
   - The card body is **a summary of the last reply** (it first showed the person's instruction, which only echoed what they had typed).
   - History `cards.jsonl`, read time `cards-read.txt` (on the server, so it survives closing the browser).
5. **Context display** — `%`. The window is decided **by observation** (§10 below fixed the decision itself).
6. **Emoji removed** — chronological·thread·bell use line SVGs (`.ic`); favicon is an SVG data URI too (red dot when unread).
7. **Stale tab detection** — `/api/state` returns `build` (PAGE hash); when it differs from the tab's own `MY_BUILD`, a banner shows.
8. **Session filters** (two chips under the Claude sessions heading in the sidebar) — past ten sessions, state sorting alone puts
   "replied 30 minutes ago and left alone" and "just finished" in the same bucket, burying the rows that need a hand.
   - `Idle` chip: off→10→30→60 min **cycle** (no hidden modifier-key tricks). Idle counts only **states where the ball is with the
     person** — `replied·awaiting answer·aborted`. ⛔`running a tool·thinking` is never idle even after 2 hours
     (5-minute tools are normal), and `Unknown` means the process could not be read, so **no conclusion is drawn**.
   - `Unpushed` chip: off→`↑` only→`↑ or ~` (including dirty) cycle. Reads the server's `git` string as is.
   - The choice persists in `localStorage.mbSessFil`. The hidden count is **stated** at the end of the list as `N hidden by filter` —
     shrinking silently reads as "sessions disappeared".
   - Marker: rows past the threshold get an amber stripe on the left and only the elapsed time changes colour (**no extra text** — rows would jitter).
     With the filter off the marker threshold is 30 min (with it on, its value is used so there is only one threshold).
9. **Click a session row → copy path** — `cursor:copy`; on success the row flashes green for 0.7 s and a text toast shows.
   - The handler is **delegated once on the `#sess` container**, not on rows — the list is redrawn every 2.5 s,
     so per-row listeners would pile up.
   - The toast is `note()` (text only). The card toast (`toast()`) is **tied to the bell history**; using it for notices pollutes the history.
   - 127.0.0.1 is a secure context, so `navigator.clipboard` works. On failure it falls back to textarea+`execCommand`,
     and if that fails too the path is shown in the toast for **manual selection** (never a silent failure).

10. ★**Context window decision — fixed so `%` shows instead of `k`** (2026-08-19).
    - **Why `k` showed**: the old rule was "1M only for sessions seen above 200k", so sessions still under 200k had no window
      and fell back to an absolute value (measured: 2 of 6 showed `152k`·`163k`).
    - **The evidence** — `compactMetadata.preTokens` of `type:"system" subtype:"compact_boundary"` is
      **the size at the moment it hit the window and compacted**, i.e. it states the window directly.
      ⚠Use only `trigger:"auto"`. `manual` (/compact) fires at points unrelated to the window — two measured values
      must not be mixed in (`sonnet-4-6` 387k · `opus-4-7` 485k). Mixing them learns the wrong window.
    - **Three-tier decision** (strongest first) — weaker evidence stays on screen as **dashed** (`.sc.est`) with the evidence in the tooltip:
      `obs` the session proved it itself (observed above 200k or its own auto compaction) → `model` a learned value proven by **another
      session** of the same model → `''` that model was never seen (only then `k`).
    - **Learned values** live in `win-model.json` (format version `v:2`), filled by a background thread scanning transcripts
      (measured: all of 1.2GB·88 files in **1.6 s** · afterwards only files whose mtime changed). Startup log prints them:
      `opus-5=1000k(5 sessions), sonnet-4-6=200k(3 sessions)`.
    - ★**Evidence is counted per session.** At first each observation added +1, and with 2.5 s polling one session piled up 24 per minute
      (measured: opus-5 46 → **82**). Then (a) the tooltip's "N" became a poll count and (b) the 200k/1M vote went to one
      long-running session. So evidence is held as **a set of session keys** and counted with `len()`.
    - ★**A format-version (`v`) mismatch discards the scan record too.** Clearing only the evidence while keeping `scanned` (88 done)
      means nothing is re-read and **the learned values stay empty forever** — a trap in the design, blocked up front.
    - **Not usable** (evidence rejected): transcript `message.model` has **no** `[1m]` marker.
      `lastModelUsage` keys in `~/.claude.json` do (`claude-opus-4-8[1m]`), but are written **only on clean exit**
      and per project, so they do not help running sessions (measured: empty for all 4 active projects).
11. **Four context colours** (2026-08-19, green or blue when low) —
    `~39% green (#6fd39a)` · `40~59% blue (#8ab4ff)` · `60~84% amber (#c9a24a)` · `85%~ red (#e0725f)`.
    The number already states the value, so colour is a glance aid (the % reads even when colour-blind). Absolute values with an unknown window get no colour.
12. **Legacy removal** (owner-approved 2026-08-19) — `transcript.py`·`transcript.html` (snapshot generator replaced by the server) ·
    `agent_mail.py`·`agent_watch.py` (early prototypes with hard-coded ids) · `agent_seen.txt` ·
    `acks.jsonl.bak`·`.bak2` · `__pycache__`. 1.0MB total.
    - **All references were checked** before deleting: the launchd plists call only `chat_server.py`·`watch_loop.sh`,
      and no MCP server source·shell script·hook·running process referenced them.
    - **Kept**: `readcheck.py` (working diagnostic CLI · named as a consumer by the `mailbox_core` docs) ·
      `bus.jsonl.bak` (**the only bus backup**) · cursor·PID·presence files (deleting them breaks loss prevention).
    - Recovery from `backup/mailbox-*.tar.gz` (code is in the tar — `transcript.html` is generated, so it is not).

13. **Bell — per-card read + `Unread only` filter** (2026-08-19: clicking an unread card should mark it read, not only «Mark all read»).
    - ★**One watermark cannot do it.** Setting the watermark to an old card's time on click marks **every newer card read**
      too. So the time (`cards-read.txt` · read all) and **a key set** (`cards-read-ids.txt` · per card) are kept separately.
    - Key is `at|kind|project` — `cards.jsonl` has no id, so it is derived (**the source of truth is not changed**).
    - Stored **on the server**, not the browser (survives closing the tab). `Mark all read` deletes the per-card key file (no longer meaningful).
      Keys older than the watermark are dropped on read — so the file does not grow forever (cap 500 lines).
    - Clicks are **delegated to `#alist`**, not the card, and the screen updates before the response (waiting for the 2.5 s poll
      looks like "the click did nothing"). On failure it reverts and shows a toast.
    - `Unread only` persists in `localStorage.mbUnreadOnly`; the hidden count is stated in the list.
    - ★Alert policy (2026-09-23, Settings › Alerts): per kind badge/list only/hidden + 30-min grouping, `localStorage.mbAlertPolicy`. Default «Important only» (badge for ask·abort·flimit·fwreck·fcheck, fcut list only).
      ⇒ Badge·tab title·favicon·top bar all count through one `alarmBadgeN()`. Toasts only for «Badge» kinds. Server counts·cards.jsonl unchanged (view filter).
14. **`sessions()` refactor 142 lines → 4 functions** (owner-approved 2026-08-19).
    `_recent_transcripts`(19) · `_parse_transcript`(87) · `_session_row`(23) · `sessions`(25).
    - ★**Why — the bug came from the structure.** The cache-hit path and the parse path each **assembled screen rows on their own**.
      Fixing one silently diverged from the other, and it did (the cache path had `_ctx_window(None, …)`).
      Now **the cache holds parse results** (not rows), and row assembly is only `_session_row()`.
    - Equivalence check: old and new modules run **in the same process at the same moment** — 6/6 sessions, identical key sets,
      **0** field mismatches. Cold vs cache hit also 0 mismatches (181ms / 1ms).
15. ★**The refactor exposed two latent bugs** (pre-existing; they happened to fire now).
    - **(a) No function named `_warn_once` exists in this file** — the name is `warn_once`. Five call sites were wrong
      (`live`·`card`·`cardread`·`cardread1`·`sessions`), so **the code meant to surface errors crashed with `NameError` itself.**
      The original exception was hidden and the request died with 500. It broke this file's own rule (*silent failures are logged*)
      head-on — nobody noticed **because the alert path rarely runs**.
    - **(b) `ps` took over 2 s** (`TimeoutExpired` on a busy machine). By design that gives `None` (unknown), which turns
      **every session grey at once** — the lookup was slow, the processes were fine, but it reads as "all dead".
      ⇒ On failure **reuse the last good value for up to 30 s** (`LIVE_STALE_S`), then unknown. Timeout 2→4 s.
    - Error paths were **forced** to verify: ps timeout→last value reused / expired→None / `sessions()` exception→empty list +
      one warning line (the page survives).
16. **Data backup** (owner-approved 2026-08-19) — `backup-data.sh` + launchd `<label>.databackup` (daily 09:05).
    - **Why a separate script**: `backup.sh` holds code only by design (data excluded — size·privacy, decided 2026-08-07).
      But `bus.jsonl` is the source of truth and the file the advocate charter names as its evidence. Measured: source 1.8MB, yet
      the only backup was from Aug 6 (784KB) — **13 days unprotected**. Code can be rewritten; conversations cannot.
    - Scope: `bus·acks·cards.jsonl` + `rooms·profiles·identity.json`. **No cursor·PID·presence** —
      restoring them rewinds to old positions and breaks loss prevention.
    - Keeps 7 · **no new archive when content is unchanged** (7 identical files in a quiet week would be 1 day, not 7).
    - Verified: ran the creation path in launchd's minimal environment (exit 0 · 672K) and **restored** —
      all 515 lines parse OK · 3 config files identical to the originals · `mailbox_core` thread decisions reproduced from the restore alone.
      *A backup never restored is not a backup.*

17. ★**Clicking a card closed the bell** (2026-08-19, every mark-read click closed the window).
    - **Cause: the 'close on outside click' handler.** Clicking a card makes `buildAlarm()` redraw the list, so
      **the clicked card leaves the DOM.** The window-level handler then asks `#alarm.contains(detached element)` and gets
      `false` — it **mistakes it for an outside click**. Any redrawing UI combined with outside-click close hits this trap.
    - Fix (a) `e.stopPropagation()` in the card handler (b) `if(!document.contains(e.target)) return` in the close handler
      (a detached element is not 'outside' — both sides blocked so it does not bite elsewhere).
18. **Toast 10 s · pause on hover · click = acknowledged** (2026-08-19).
    It used to be 5 s and a click **opened the bell** — glance at another window and it was gone; clicking did not mark it read,
    so the badge stayed (only `Mark all read` cleared it).
    - `TOAST_MS=10000` · hovering stops the timer; leaving makes it disappear after `TOAST_LEAVE_MS=3000` (vanishing mid-read
      was the original complaint). A click = **that card read + dismissed** and does not open the bell (no reason to show what was already seen).
    - Marking read is one function, `markCardRead()` — if list and toast diverge, only one gets fixed and they silently drift
      (this file already had that bug: cache path vs parse path §14).

19. **Last line of a session row = "what is it working on"** (2026-08-19).
    - That slot used to be `task` (**the person's last instruction**) — it showed *what the person had typed*, which had little value.
      Bell cards had already moved from instruction to reply summary for the same reason; only the session panel had not.
    - Now: **while running (tool·thinking), the tool's target** (`targ`); **when finished, what was just done** (`reply`). The instruction moved to the tooltip.
    - `targ` is taken from the tool input by `_tool_target()`. ⚠Only **fixed keys** are read
      (`description`·`file_path`·`path`·`pattern`·`query`·`url`·`command`). `prompt`·`body`·`subject` are **left out on purpose** —
      a `mailbox_send` body is conversation content itself, and the *session panel is metadata only* rule must hold.
      So MCP tools can have an empty target (then the line is not drawn — the tool name is already on the line above).
20. **↻ resume chip** — copies `cd <cwd> && claude --resume <full-id>` for the row. The server had the full session id but
    **sent it cut to 8 chars**, so ended sessions could not be resumed (`sid` field added). To avoid clashing with the row click
    (path copy), the chip handler catches it **first** and calls `stopPropagation()`.
21. ★**Top "needs a hand now" line** (`#todo`) — the purpose of this screen is one question: **is it my turn.**
    The answer was scattered across the middle of the sidebar, inside scrolls and the bell dropdown. It is **a collection**, not a new decision.
    - Cells: `Awaiting answer` `Aborted` `Context 85%+` `Unread` `Stale threads`. **A cell is absent at 0, and the line disappears when all are 0.**
    - Click → narrows the session filter (`stFil`) to that state and scrolls to the sidebar. Clicking the same cell again clears it,
      and `Awaiting answer only ✕` appears in the filter chip row to clear it there too (so it is never unclear where it was turned on).
    - `Unread` opens the bell; `Stale threads` expands thread chips on a second line (no popover —
      no reason to recreate the z-index·outside-click problem §17). Chip click → reuses the **existing tab filter** (`thread:<name>`).
22. ★**Stale-thread detection — useless without an upper bound** (learned by measurement).
    - Criteria: 4+ posts · 2+ participants · no done tag (`DONE` in web/js/00-core.js) · quiet **24 hours–14 days**.
    - **Without an upper bound it caught 17**, of which **11 had been quiet 15–23 days**. Those are **finished discussions**, not work —
      the done-tag habit came later, and old threads lack the tag even when decided. **Relying on the tag alone misreads
      "ended but unmarked" as stale.** Cutting at 14 days left 6, the same 6 as the initial server-side measurement.
    - The cut is **stated** at the end of the list as `14d+ · 11 excluded` (silent shrinking reads as "none").
    - The server was not touched — everything needed (all `MSGS`·the `DONE` tag set·`closedT`) is already on the page.
23. **Name: «Mailbox» → a new product name** (since renamed Sidereus) (owner decision 2026-08-19) — screen title·h1·tab title·startup log·doc titles.
    ⛔`advocate/CHARTER.md` was **deliberately left alone**: its sha256 **fingerprint is the contract** (§3·§7), so changing just the title line
    makes advocate flag "the rules were changed behind our back". Fingerprints measured before and after: still `75c0d658`.
    The protocol (`mailbox_*`·`MAILBOX_ME/SELF`·`~/.mailbox-mcp`·launchd labels·`bus.jsonl`) is unchanged.

24. ★★**The top bar must be inside the (sticky) header** — it was first placed outside the header, at the top of the document.
    This screen is a chat, so **it scrolls to the bottom on open** ⇒ measured: at scroll `277,049px` the bar's y was **`-276,977`**.
    So **it was normally never on screen** (it only showed by chance when a thread filter made the page short, which first looked like success).
    - Also fixed: the **hard-coded** `aside{top:76px}` became `syncAsideTop()` (measured header height + 4). ⇒ 09-24 `syncAsideTop` removed (a no-op after independent scrolling).
      The header is variable — with two tab rows or the bar attached, the sidebar head slid behind the header (it was already off).
      Measured: header 104 → aside top 108 · with the stale list expanded header 131 → aside top 135 (no overlap).
25. **Dropped connections are not logged** — closing or reloading a tab overlaps the 2.5 s poll and raises `ConnectionResetError`.
    **It is normal**, yet it piled up as tracebacks in `viewer.err`. Then, as in §15, **real errors get buried among them.**
    - ⚠Guarding only `_send` is not enough — the drop also happens **while reading the request** (`handle_one_request` → `readinto`).
      Both sides must be caught for a clean log (measured: `viewer.err` 0 bytes after 5 forced drops).

26. **"Whose turn" on stale chips** (owner choice 2026-08-19) — saying only *it stopped* **does not settle what to do.**
    Whoever is **not** the last poster owes the reply. With three or more, all are listed (picking one would be a guess).
    Measured: all 6 yield a target, e.g. `<thread> 12d → <agent>'s turn`.
27. **Decision·correction log tab** — subject tags are on **483/531 (91%)** posts, so there is enough material.
    - Decision (= the `DONE` set in web/js/00-core.js: three Korean done/closed/complete tags + DONE·CLOSED) **57** — what was decided had been scattered over 72 threads.
    - Correction (`FIXT` in web/js/15-alarms.js: correct·fix·withdraw·reverse tags) **41** — this room reversed itself 41 times, which is exactly what advocate charter axis 1
      (acceptance without evidence) targets. Collected, it becomes a checklist by itself.
    - The tag set **reuses** `DONE` (= `mailbox_core.CLOSE_TAGS`) — two copies would drift one day.
28. **Context 85% → one bell card** (`_note_ctx`) — on the top bar alone it **is missed while the tab is not watched.**
    Compaction loses context and this project runs on handover docs ⇒ the value is **a window to step in before compaction**.
    - ⚠Idle alerts were dropped but this was added because: (a) **once per session** (idle repeats as long as the condition holds) (b) **it demands action**.
    - When compaction actually happens and it drops below 60%, the mark is released to alert **again next cycle** (`CTX_REARM`).
    - Sessions with an unknown window (`win=0`) are **not alerted** — this file's rule of no warnings on estimates.
    - Verified: 8 isolated cases (84% ignored · 86% one · 91% re-call kept · 20 polls kept · released after compaction · one more on refill ·
      ended session ignored · win=0 ignored) + on the live server an 88% card appeared once and stayed one after 3 polls.

29. **favicon: envelope → stoa (sidereus)** (2026-08-19) — the name changed, so the picture did too.
    Roof (pediment) + 3 columns + base. Still a data URI for the same reason (file routes are only `/`·`/api`, so a file would 404).
    - **Unread badge** small in the top-right corner (`ring r=5.2` + `dot r=3.8`). First drawn large at `r=7`, it
      **ate the whole roof** and the icon became unreadable. A dark ring is drawn first so it reads as a badge (otherwise it blends into the blue roof).
    - ★**Checking the picture without a browser**: take the `href` the server sends, decode with `urllib.parse.unquote` →
      parse with `xml.dom.minidom` (syntax) → render PNG with **`qlmanage -t -s 160/32`** (shape·32px legibility).
      macOS has no `rsvg-convert`·ImageMagick·cairosvg, but has `qlmanage`.
30. **Wording: the Korean «unread» label switched from the Sino-Korean short form to the plain spelled-out form** (2026-08-19; ko dictionary values of `Unread`).
    Screen text only — top bar `Unread N` · bell chip `Unread only` · `No unread cards` ·
    bubble `✓ sent · Unread` · participants `Unread N` · tab `Not read by them N` (the run-together short form `Unread|short` was fixed too).
    ⚠The old short form in code comments·docstrings was left (internal term) — align it if the mismatch ever confuses.

31. ★**The card hint overlapped the body** (2026-08-19, overflow over the mark-read hint in the alarm list).
    - **The overlap was built in**: `::after{content:'<mark-read hint>';float:right;margin-top:-14px}` —
      it was **pulled up one line** over the last line, so when the last body line reached the right edge it sat on top.
      Cards without a body overlapped the time on the title row (`.ctime`). The overlap was **structural**, not accidental.
    - Fix: the hint became a **real child** (`.chint`) of the title row (`.crow1`) — in the flow there is nowhere to overlap.
      `float`·negative margins·`absolute` were all removed from cards (they were the only cause of this bug).
    - Also fixed: ellipsis on `.cproj` (`min-width:0`+ellipsis) — long project names pushed the time·hint out.

32. **Running background tasks·subagents shown** (2026-08-19). A session could show `Replied` while a
    subagent was actually running, so the state lied.
    - Rule: **a tool call with no result** — no `tool_result.tool_use_id` matching the `tool_use.id` means running.
      Subagents (`Agent`) and background commands (`Bash run_in_background`) are caught by **one rule**.
    - ⚠Only the last 300 lines are read — anything launched earlier is not counted (nothing unknown is invented).
    - ⛔`~/.claude/tasks/<session>/*.json` is a **to-do list** (TaskCreate · in_progress/pending), not running work.
      It was considered first by mistake and dropped.
    - Verified: a real transcript **cut right after** an Agent call gives 1, including the result gives 0
      (an Explore field-investigation agent · a bot GUI launched on a local port).
32b. ★**Background detection — wrong three times, then fixed** (2026-08-19, a background wait in a large repo did not show).
    The first rule (`tool_use` with no result) fit **only subagents**. What was actually missing was **Monitor**.
    - (a) **Completion signals differ by kind.** Background work ends with `<tool-use-id>` in a `<task-notification>`.
      `Bash(run_in_background)` **returns a task id immediately**, so counting `tool_result` as completion gives 0 the whole time.
    - (b) **The tail cannot catch it.** A large repo's transcript is **780MB**; the last 800KB is 209 lines and the launch line was outside.
      ⇒ **Remember** what each poll saw (`_bg_open`), and scan 20MB deep **only once per session** (1ms from the second time).
    - (c) **A persistent task (Monitor) has no launch line at all** (it started hours ago). So *the notification itself* is used as
      evidence of life — only those starting with `<summary>Monitor event:` are alive; things like `Agent … finished` are ended
      (treating "no tool-use-id = alive" counted completion notices as running).
    - (d) **Never run a regex over the raw string** — JSON escapes leak into labels, and it picked up 21 task ids from other
      bodies. Parse and read **only the body string**.
    - (e) ★**Never stamp with `now`** — scanning 20MB turns hours-old notifications into 'just now' and **dead monitors linger**
      (one session showed 2 monitors). Use the line's `timestamp` and **convert UTC→local** (otherwise everything is 9 hours off and expires).
    - Shown in three groups: `Agents N · Commands N · Monitor` — **calling a monitor an 'agent' is wrong**.
      The top bar counts without monitors (always on, not 'needs a hand'). Ended sessions show 0.
32c. ★★**An Agent `tool_result` is a receipt, not completion** (2026-08-19, running subagents showed as finished).
    The body is `"Async agent launched successfully. … agentId: …"` —
    it returns at launch **exactly like** background Bash. Counting it as completion showed **5 running agents as 0**.
    - Fix: a result containing that phrase **is not completion**. Synchronous calls (body = report) exist too, so the phrase decides.
    - Also caught (a) the notification block's `continue` was **skipping completion-notice handling** — 2 finished ones stayed.
      (b) monitor expiry 30 min → **2 hours** (after monitors were batched to wake together, quiet stretches grew and live monitors vanished.
      A stopped monitor lingering 2 hours is less harmful than a running one shown as absent).
    - Cross-check: 3 on screen = 3 unfinished Agents in the transcript (no completion notice) — names match too.
33. **Tokens — where they burn, measured** (2026-08-19). Detailed table in `docs/notes/monitoring.md`.
    - What fills context: **model output 61.2M > tool results 25.6M > human input 2.5M** (one large repo, cumulative).
    - One output token stays in context and **is re-read as cache read on every remaining request** (midpoint ≈ 480× its direct cost).
      By direct price it is 90% input / 10% output, but **output is what built that input mass**.
    - Reliable savings in order: (1) keep huge tool outputs out of context (98 results of 20k+ chars = 45% of result characters)
      (2) hand over before context grows (requests above 600k = 40%, holding 62% of input) (3) write short (800 chars = 58% less total).
    - ⚠**The mailbox is barely 1% of the total** (inbox 170 + ack 176 = 1.7% of tool calls). Batching·brief point the right way
      but are small — to save tokens look at (1)(2). Do not overstate it.

34. ★★**Receive session state instead of inferring it — official OpenTelemetry** (2026-08-19, adopt an open-source, benchmarkable source).
    File-tail inference **kept being wrong**: an Agent `tool_result` is a receipt, not completion (§32c) · lost completion notices ·
    cases never written to the transcript at all (reply in the terminal, nothing in the file).
    - Claude Code supports official OTel (`code.claude.com/docs/en/monitoring-usage`).
      ★Measured: **`OTEL_EXPORTER_OTLP_PROTOCOL=http/json`** works, so this server receives it directly **with no collector·Docker·Grafana**
      (it is already an HTTP server — `POST /v1/logs`). A 40-line receiver parsed `application/json` as is.
    - Enabled in: `env` of `~/.claude/settings.json` (backup `settings.json.bak-otel-*`).
      `OTEL_METRICS_EXPORTER=none` — tokens are in the `api_request` event, so receiving metrics too only doubles traffic.
    - ⛔**No bodies are received**: `OTEL_LOG_USER_PROMPTS`·`ASSISTANT_RESPONSES`·`TOOL_DETAILS` are **not enabled**.
      They would carry prompts·replies·tool arguments (this file's rule: conversation content never goes on the page).
      `tool_name` still arrives with them off — that is all that is needed.
    - Events used: `user_prompt` (turn start) · `tool_decision`/`tool_result` (tool·success·duration) · `api_request` (tokens) ·
      `assistant_response` (turn end). The rest (hook_*·mcp_server_connection) are **dropped**.
      `event.sequence` is the source of truth for order; sessions are joined by `session.id` (= our `sid`).
    - Priority: no process → `Ended` wins · `Awaiting answer` (ask) keeps the transcript, which is more specific ·
      otherwise **events are the source of truth**. Not used when no event for over 15 min (the session started without telemetry).
    - Diagnosis: `curl localhost:8799/api/otel` — which sessions are sending. Rows carry an `otel` flag too.
    - ⚠**A running session attaches only after restart (or `--resume`)** — env is read at process start. `/mcp` does not do it.

35. **Saved views** — header `Views ▾` · `+ Save`. Filters have several layers; rebuilding the same combination takes six actions.
    - Saved: mode · room · filter/thread · search term · grouping · sessions (idle·unpushed·top bar) · to-do bar · timeline (range·interval·replay speed) · failures (range·kind·grade).
    - ⚠**One-off UI is not saved** (open modals · scroll · split ratios · alarm window). Restoring it would change things the person did not pick.
    - Storage `localStorage.mbViews` = `[{v:1, n:name, s:{…}}]` · max 12 (one `note()` line past that) · a different `v` is not restored, one line says so.
    - ⚠Restore sets state, then calls the **existing render functions** (`buildRooms`…`setMainView`). Timeline·failure values are **also written to their own `mb*` keys** — those keys are the source of truth on reload, otherwise they revert.

36. **Global search palette (Cmd+K / Ctrl+K)** — with dozens of sessions, the three filters (`stFil`·`gitFil`·`idle`) cannot find «that session» (narrowing and finding are different jobs). A common ADE feature.
    - Searched: `project` · `cwd` · `id` · `sid` · `model` · `state` + `LBL` labels · platform name (`platHay(plat)` = `platName` Latin name + Korean aliases). Spaces are AND.
    - ⚠`platName` is Latin only, so searching Gemini by its Hangul spelling failed (2026-09-24) ⇒ aliases are one line each in the `platHay` table (`web/js/40b-sessions-list.js`, right under platName). Displayed text unchanged. Test `tests/test_plat_search.py`.
    - ⛔`task`·`reply` are **not included** — they are text taken from conversations (rule 1 of this page).
    - Location: `cpMatch`/`cpHay` (pure functions · near `:14377`) · `cpOpen`/`cpPaint`/`cpGo`/`cpInit` · CSS `.cmdk*` · markup `#cmdk`.
    - On pick, finds the row by `data-scwd`, `scrollIntoView` + 1.4 s `.sxw.cphit` (blue outline). The flash survives the 2.5 s repaint because `cpFlash` is **part of the render**.
    - ⚠Unhide the row first: `body.lsoff` (monitoring folded) · `sessOpen` (ended folded) · filters. Otherwise "picked it and nothing happened". ⇒ 09-24 replaced by the drawer — `body.lsoff` became `sesdrReveal()` (opens the drawer).
    - ⚠Not intercepted while an input (`INPUT`/`TEXTAREA`/contentEditable) has focus — it must not open while typing chat. Existing shortcuts are only Esc·Enter, so no clash.
    - The session list is `aside.lside`, so it **floats over every `mainView`** — no `setMainView` switch needed.

37. **Language pack (Korean/English) + `Settings` tab** — forks of the open-source release must be usable in English.
    - **The Korean source text is the key**: `T('<Korean source>')` · `I18N.en = {'<Korean source>':'Session Monitor', …}` (since superseded: sources are English, Korean lives in `I18N.ko`). Missing entries return **the source text as is** — empty translations never break the screen. Korean mode does not even look up.
    - ⛔Do not change keys to codes like `main.title` — the fallback works because «key = visible text».
    - Location: `I18N`·`LANG`·`T()` right above `let mainView` · `setLang()`/`paintCfg()` right above `buildMv()`.
    - State `localStorage.mbLang` (default `ko`). ⚠No automatic detection from the browser language — the person chooses.
    - Switching redraws with `buildMv(); paintCfg()`, no reload. The settings tab **has no fetch** (reads localStorage only).
    - ⚠Do not pile other settings into the `Settings` tab — it holds only the language for now.
    - Since 2026-09-24 every screen goes through `T()`/`KE()` (897 dictionary entries · status in traps/ui.md «The language pack keys on the Korean source text»).


## Feature notes (2026-09-23 →)

### Branch graph API (2026-09-23)
`GET /api/branches?cwd=<absolute path>&n=<80, cap 300>` — read-only. `branch_graph()` (`sidereus/git.py`).
- **Only 2** git calls: `for-each-ref` (branches·upstream·ahead/behind·time) + `log --all` (parents·subject·decorate).
- Paths are confined by `_branch_ok()` — no new list; `_allowed_cwds()` (session cwds + touched repos) + Sidereus itself.
- Same `(cwd, n)` is **cached 20 s** (`_git_state` convention) · git timeout 6 s (same cap as `DIFF_TIMEOUT`).
- ⚠**Do not put it on the poll** — called only on click. `origin/HEAD` is excluded from both branches and `refs` (symbolic — the same commit would be drawn twice).
- Not a repo → HTTP 200 + `{"ok":false,"err":"not a git repo"}` · missing path 400 · outside the list 403.

### `?ui=next` → main UI (2026-09-23)
★Owner decision: the preview became **the only screen**. Constant `UI_NEXT = true` · the first `<head>` script sets `data-ui=next`·`data-tone` before CSS (prevents a flash of old colours).
- Cleanup (09-23): `UI_NEXT` constant·branches·old-only code (`awakeRow`, burn header toggle, old participant/room rows) removed. Only 6 overrides without size·colour (`.kn` `.tlnote` `.pwhere` `.wrap` gap · `.rm` radius · `.wvh b` weight) were merged into the base rules. computed-style diff 0 (animations excluded).
- ⚠The remaining `html[data-ui=next]` rules (74) stay scoped — the prefix is the exclusion marker for the `#nxcss` twin generator (rules containing `data-ui` are skipped). Unscoping rules with size·colour creates twins with +1px·colour remapping.
- ⚠Twins stay at runtime — they derive from the base CSS; freezing them statically means keeping two copies in step on every base-rule change. ⚠`AWAKE` (sleep prevention) is no longer drawn anywhere.
- Below is the preview-era description ("unchanged without the flag" is no longer true).
- The header key-number row `#kn` is removed; 5h/7d quota lives in the status bar (`buildSbar`).
- Based on the dark tone of monitoring UIs (list layout after Datadog). The `#nxcss` twins add +1px to sizes, map dark neutral surfaces·lines to tone variables (`--nx-bg/panel/hover/rule`), and blue·green·yellow·red to Sidereus palette hues (HSL 215/115/49/356). Session colours `.c0~.c6` excluded.
- **Sidereus palette (09-24)** — tokens in the first block of `web/css/90-main-ui.css` (three dark tones) · `web/css/91-light.css` (white). The derivation rules (OKLCH lightness steps · hue/chroma per role) are defined in both files' head comments. `thc()` literals·CSS `var(--nx-*,#fallback)` use the same values.
  - ⚠New colours are **derived from this system** (role + L step). Do not paste hex from another product's theme — the public originality check caught Grafana values copied verbatim.
  - ⚠When token hues change, also align the HSL hues (215/115/49/356) in `00-core.js` `tone()`.
  - ⚠Body contrast ≥4.5 (bg·panel), glyphs ≥3. t3 is the lowest L above 4.6 over each tone's hover — lighten a surface and re-measure t3.
- Background tone `html[data-tone=black|grey|blue]` (`mbTone`, default black): only surface variables change; semantic colours are shared. The number row is a stat panel (remaining % below 10 red · below 30 yellow); participants·rooms are list rows (`.nxr`).
- Settings is a header gear (`#gear`) modal (`#cfgm`, including the default view), not a tab. A stored `mbMainView='cfg'` falls back to chat. ⚠Modal rows use the same state·functions as the original controls — do not create new settings.
- Two-pane settings modal (09-23): categories on the left (`CFGCAT`, `sidereus.cfgcat`; saved views only when present) · row cards on the right `set(label, description, control)` · button group `.cfgseg` · long lists (refresh interval·range) are `select.cfgsel[data-k]` → the same `act[k]`. Tabs on top below 640px.
  - ⚠CSS is scoped as `html[data-ui=next][data-ui] #cfgbox …` (excluded from twins + beats the old `.cfgbox`/`.strp` twins). ⚠`svSwSync` does not redraw while a `<select>` has focus (the open list would close).
- Timeline `.tlnote` hidden → `?` (`.tlq`) title · `Replay`/`Refresh`/`Range` labels before the controls (`.tlgl`).
- Bottom status bar `#sbar` (`buildSbar()`, called from `poll()`) + drawer `#sdrw` (`sidereus.sdrw`, click·Esc). The original `#burn/#saver/#quota` nodes are **moved** into the drawer so the existing builders draw them unchanged.
- Rule: never the same number twice — the drawer drops burn's current %·time to reset·5h/7d rows, the 5h line's remaining time·the 7d line's date, and the sleep-prevention line. Verdict names `SV_JLONG` («Way too slow» → «way slower than the target»), «Easy» → «No throttle».
- ⚠No burn header click under the flag — it writes `sidereus.burn` and changes the default view's folded state. Times use `CLK`/`MDCLK` (ko keeps the original calls).
- ⚠All flag CSS is scoped with `html[data-ui=next]`. Twins are made for **every** rule with size·colour — making only some reverses the original cascade order.

### Timeline first · work log in a popup window (2026-09-23)
- Default view `time` (for none stored·invalid·old `work`). Tabs: Timeline · Chat · Tokens · Structure · Branches · History · Failures. No work-log tab.
- Session card·timeline bar/name (`tlOpen`)·agent row → `wkPopup` → `/work?cwd&tid` window. The same document boots as `ISWP`, uses `#wkm` as the whole window with a one-line summary on top (`wkSum`). The main window's view does not change.
- `popOpen` shared by the three popups (window per name · 30px cascade · resets every 8 · `POPS` registry · link toast when blocked): `sidereus_work_<tid>` · `sidereus_diff_<cwd>` · `sidereus_brdiff_<sha12>_<path>` (`/brdiff`, old `#brfm` modal removed).
- ⚠The server paths `/work`·`/brdiff` must be in the `("/", "/diff", …)` list — missing, the popup 404s.

### Sessions needing you `#attn` (2026-09-23)
- `17-attention.js`·`62-attention.css`, source `/api/state.attention` (sidereus/attention.py). Right under the Claude sessions heading in the sidebar, 5 rows + `+N more`.
- Tab title `[N]`·top bar «Need you N» = `attnBadgeN()` (top signal not list·not snoozed). The old blocked/question/abort/85% cells merged into this one.
- Signal k → APOL kind (`ATTN_APOL`): hide removes the signal, list keeps the row but excludes it from the badge. `done` is always list.
- ★list rows (incl. `done`·`bgdone`) are not drawn at all. Row/button click = acknowledge → `mbAttnAck` {sid: `sid|sorted k|top since`}; it reappears when the key changes (new signal·new since). Snooze is behind `⋯`. The server `why` is Korean, so English mode rebuilds it from k + numbers in `attnWhy`.
- Snooze `mbAttnSnooze` {`sid|k`: expiry ms | 'clear'} — a newly raised higher signal wakes it and deletes the entry. 'clear' is deleted when that k goes away.
- `buildAlarm` (15-alarms.js) calls `buildAttn()`·`attnTitle()` directly — 17 comes later in file order, so only runtime calls work.

### Keyboard reach · failure-card read split (2026-09-23)
- `98-a11y.js`: collects selectors of `cursor:pointer` rules from CSS and gives matching non-native elements `tabindex=0`·`role=button`·`data-kb`. A MutationObserver handles only new nodes, once per frame. One Enter/Space delegate → `click()`. Focus ring `95-focus.css`.
- ⚠`cursor:pointer` is the contract — remove it and the element leaves the tab order. Elements that already have `tabindex` (`.wpk`·`.sbar`) have their own keydown and are skipped (overlap = double press).
- Failure cards (flimit·fcut·fcheck·fwreck): body clicks·action buttons do not mark read. Unread cards only get a `Read` (`data-fread`) button. Toasts: body/action = close only, `Read` = read + close.

### Sending a message from the work popup (2026-09-24)
- `36-wkcompose.js` · `#wkc` (last cell of `.wkmin` in index.html) · CSS at the end of `10-worklog-split.css`. Visible only in the `/work` window (`ISWP`).
- Recipient = cwd of the focused pane's tab → the `mbox` of that `SESS` row (agent tabs use the parent session). In a split one box follows focus (draft kept) · empty pane focused = pane 1.
- State: `mboxSrc!=='identity'` → disabled «not logged in to the mailbox» · `mon[].src==='proc'` (or presence watch) → ●watch · otherwise ○No mailbox watch · `blocked` → «Waiting for permission».
- Server `POST /api/dm` → `sidereus/bus.py:dm_send` — recipient id only from identity.json (no guessing from folders), body ≤ `DM_MAX`, `from`=`VIEWER_ME`, `thread=wk:<id>`. Test `tests/test_dm_send.py`.
- Progress `Queued/relayed → Confirm(ack) → Reply`: reuses `ACK`·`CUR`·`MSGS`. Polling = the 15 s poll + `wkcTick` for 10 min after sending (5 s, on the 2.5 s tick).
- ⚠No automatic sending — Enter/button only. ○No mailbox watch goes through a confirm line (`#wkcq`). Esc does not close the window while a draft exists (92).
- ⚠Immediate delivery needs a watcher (watch.sh) — without it the message waits in the mailbox and is read at the next mailbox tool call.

### Branch tab commit ↔ session·cost (2026-09-24)
- `sidereus/commit_link.py` → `GET /api/git/links?repo&shas` → `{ok, busy, links:{sha:{sid,agent,proj,ts,tok,usd,tid,cwd,how}}}`. Screen `88-branch.js` `brLk*` (row chip «session ab12cd34 · 3M» · detail «Made by» + `Open work`=`wkPopup`) · CSS `81-branch-links.css`.
- Pairs Bash `git commit` tool_use ↔ tool_result in transcripts (30 days). Per-file offset cache `commit-links.json` (cold 2.8GB 8.7 s in the background → `busy` · incremental 0.03 s).
- ★`git commit -q` prints no `[branch sha]` (every orchestrator commit in this repo) ⇒ the command's subject (-m · heredoc) is matched against the `git log` subject within a 15-min window (`how:"subj"`). Measured 33/33 linked.
- ⚠Cost is **an estimate**: all tokens in the same file since the previous commit to the same repo (else file start). Subagents = parent sid + agentType. Test `tests/test_commit_link.py`.
- ⚠Commands·output are read only on the server — the response is metadata only.

### MCP `sidereus` — sessions ask Sidereus (2026-09-24)
- ★Owner-approved: the session asks instead of a person watching the screen. Sidereus only answers questions — no session control.
- `mcp/sidereus_mcp.py` (stdio) → `GET /api/agent/{quota,peers,file,attention}` → `sidereus/agent_brief.py`. Tools·registration command in `docs/MCP.md`.
- ⚠Responses are built field by field — session rows (`task`·`reply`·`sub[].now`) are never passed whole. Tests catch leaks.
- ⚠Advice text only relays the saver hook verdict (`lv`·stage) — it creates no new rules.
- ⚠Routes exist only after a viewer restart — tool responses before that are «HTTP 404 — restart».
- Optional hook `hooks/file_peers_notice.py` (PreToolUse Edit|Write|MultiEdit|NotebookEdit) = asks the same `/api/agent/file` with a 0.5 s timeout; if another live session edited the file, one `additionalContext` line (never blocks) · once per (session, file, peer) per 10 min (`.file-peers-notice.json`) · registration in `docs/GETTING-STARTED.md` section 5.

### Agent row = task description (2026-09-25)
- Timeline agent row name = the newest run's `desc` (Agent description, 80 chars on the server) + type chip (`tlAgNm`) · Claude subagents (with `aid`) only · external CLI children keep their type.
- Setting «Show task description on subagent rows» (`sidereus.agdesc`, on by default) · ⚠off = the description is written nowhere: rows, hover cards, cursor snapshots. Test `test_agent_desc_label`.

### Fresh install showed «2 warnings» (2026-09-26)
- Cause: a new machine has no `bus.jsonl` and no `~/.claude/projects`; both reads raised and landed on the health strip (`bus`, `sessions`).
- Fix: `main()` calls `sidereus/bus.py` `ensure_bus()` (empty file, 0600) · `sidereus/cards.py` `_recent_transcripts` returns `[]` when the projects dir is missing.
- ⚠Do not silence the `bus`/`sessions` warnings themselves — a missing file on a running install is still a real fault. Test `tests/test_fresh_install.py`.
- Labels: `<label>.<job>` (viewer, watch, databackup); launchd untouched. Test `tests/test_launchd_label.py`.

### Workflow-tool agents were invisible (2026-09-26)
- Cause: they live at `<session>/subagents/workflows/wf_<id>/agent-*.jsonl` (+ `journal.jsonl`, meta without `toolUseId`); every scan globbed `subagents/*.jsonl` and derived the project/sid at a fixed depth.
- Fix: `sidereus/agents.py` `sub_globs`/`sub_paths`/`sub_sess_dir` (usage index, burn, commit link, file owner, failures) · `wf_runs` → session row `wf` (tree node «Workflow name ▰▱ done/total») and timeline run row (`kind:"wf"`, children `par`=`wf:<id>`).
- ⚠Never read journal `result` payloads or the Workflow args — only type/agentId/label/phase and the script basename. ⚠Never derive project/sid with `dirname(dirname(…))` — use `sub_sess_dir`. Test `tests/test_workflow_runs.py`.
- State: a live run (`wf[].run`) reads «Workflow running» (`20-session-state.js` `wfRunning`/`waitOnLabel`) in the list, timeline, activity pills and header count; `sidereus/attention.py` emits no `done` while it runs (a Workflow call returns at launch, so the parent sits in `wait`).
- Run row = one line «title [Workflow] [n/m] [phase]» (+ red «N failed»); time/tokens only on the bar (`70-timeline-state.js` `tlAgNm`). ⚠The old 3-line wrap came from `.tlnm b{display:flex}` hitting `<b class=wfn>` — don't put the run title in a bare `<b>` inside `.tlnm`.
- `sidereus/demo.py` carries a workflow run + an agent team so `scripts/screen_check.mjs` covers those nodes.

### Sessions list patches in place (2026-09-26)
- Cause: every poll rebuilt all rows because only «Ns ago» text changed → `98-a11y` re-marked every node (★~48 writes/10s → 0 after) and keyboard focus was lost.
- Fix: `buildSessions` (40b) writes through `morphHtml` (`08-ui-kit.js`) — only changed text/attrs are patched.
- ⚠Rows must use delegated listeners on the list box — no per-row listeners (a patched row is not a new node). ⚠An element that loses its clickable class keeps its old a11y marking until the row is rebuilt.

### Review queue · board (2026-09-27)
- Server `sidereus/review.py` → `state().review = {n, rows:[{sid,cwd,root,branch,nf,add,del,done,since}]}` · screen `REVIEW` (88c, filled by 95-poll). Header «Review N» chip (25) → `brBoard(true)`.
- Branch tab toolbar «Work units | Board» (`sidereus.brboard`). Board column priority: blocked (blocked·ask·abort·err·attention signals blocked/ask/abort/conflict/loop/stall/toolfail/fail/wreck/ctx95) > running (tool/think·sub·bgs·wf) > review (not done) > done > waiting. Ended sessions not in review collapse into «N ended hidden».
- Card = metadata only (name·branch·model·sid8·targ·age·ctx %·changed file count or git «~N»). Click: review/done → `rvOpen`, others → `wkPopup(cwd,'sess:cwd|sid')`. Buttons = one default per column + «Relay ▾» (fix·commit·stop·go·free).
- ★2026-09-27: relaying a message a person wrote to that session's mailbox (preview + confirm, `/api/dm`) is not direct control, so it is within the rules.
- ⚠Sidereus itself still runs no git write commands and kills no sessions · no automatic sending · no actions by drag.
- ★Same day, principle change: Sidereus is no longer a read-only web page but also relays control ⇒ Sidereus = monitoring + relaying control (AGENTS.md rule 7). Control features are built as mailbox relays · ⛔no direct CLI connection (pty·send-keys·spawn/kill).
- ⚠`paintBr` writes `#feed.innerHTML` directly, so the board decides same-HTML skipping by its own copy (`#feed._bd`) + whether `.bdtab` is mounted instead of `setHtml` (`_sh` is cleared).
- Relay stage chip: card `.bdrl` (one line above the buttons) · review drawer head `.rvrl` = «→ Sent/Delivered/Read · Nm ago» (stage + time only). Relay = `/api/dm {relay:true, sid}` → `kind:"relay"`·`sid` on the bus post. Decided by `relayStat(sid)` (88b, tests/test_board.py): delivered = recipient id in `ACK[id].hooked` (Stop hook receipt), read = the recipient id's ack. ⚠The watcher's `delivered` alone keeps «Sent» (tooltip «watcher notified only») — it is only a notification, not delivery.
- ⚠The preview (#rvq) does not focus «Send» (textarea or «Cancel» instead) — one Enter would send. Esc in the board «Relay ▾» menu closes only the menu via window capture (the drawer stays).
- ⚠A session idle at its input prompt cannot be woken — delivery happens **when its next turn ends**, by the Stop hook (`hooks/mailbox_stop.py`), which leaves a `kind:"hooked"` receipt in acks.jsonl. A watched session may see the same relay twice (hook text + inbox).
- ⚠On screen a relay post cannot be found by `m.kind` — `decorate()` (10-feed) overwrites `m.kind` with the subject tag ⇒ find it by `sid` + `idSrc:'viewer'`.
- Line comments (88e): review drawer «diff» → `loadDiff(cwd,path,'',sid)` → only with popup `&rvsid=` does a «+» appear on new-side lines (Shift+click = range, Ctrl/Cmd+Enter save, Esc cancel). Drafts = `localStorage sidereus.rvnotes.<sid>` (max 50, shared across windows via the `storage` event) · drawer «N comments» · the «Request changes» body gets `path:line` + quoted line (≤200 chars) + comment; after a successful send only what was sent is deleted. Merging happens inside `rvRelay` (kind fix), so the board «Relay ▾ Request changes» is the same · `rvnPack` cuts the body under `state().cfg.dmMax − 1000` (else 20000 − 1000) and appends «… N comments left out by the length limit».
- ⚠Esc in the comment box is consumed in the document capture phase — otherwise 35c's Esc closes the diff window itself.

### Jump to terminal (2026-09-27)
- ★2026-09-27 the workflow is iTerm2 + Sidereus rather than an ADE ⇒ a «Terminal» button on session rows `›_` · board cards · the attention list (live sessions only). `POST /api/term/focus {sid}` → `focused` = «Switched to the terminal», otherwise copies the `cmd` the server returned.
- Setting «Terminal integration: Auto · iTerm2 · Terminal · off» (`cfg.termApp`, auto = `term.app` detected per session). When unavailable the button reads «Copy command».
- ⚠Focus only — no input is typed into the tab (AGENTS.md rule 7: no pty·send-keys).
- ⚠First use raises the macOS automation permission dialog. Denied → `how:'error'` → guidance to allow iTerm2 under System Settings › Privacy & Security › Automation.
- ⚠One document capture-phase listener takes the click and stops propagation — so the row·card·attention line's own clicks (work log·open review·dismiss) do not fire too.

### «Waiting on you» notifications (2026-09-27)
- ★2026-09-27 priority 4 ⇒ when a session newly enters blocked·ask·abort·fail (attention signals) or review-waiting (`state().review` row, not done), an OS notification fires (43-notify `ntfTick`, called by 95-poll).
- Settings › Alerts «Notify when a session waits for me: off · on» (turning on calls `requestPermission` in that click; denied → allow guidance in the description slot) · «Also when this tab is visible» (off = only when `document.hidden`). Stored `sidereus.notify {on, visible}` — the old `sidereus.osntf='1'` also reads as on.
- Transitions only: sid|kind keys held in memory, the first poll only seeds (no burst on reload) · review seeded separately (`*|rv`) · limits = 1 per session per 2 min, 4 per minute overall, overflow as one «+N more» (`ntfGate`, tests/test_os_notify.py).
- Body = project·branch·state name·elapsed minutes·sid8 only. tag = `sidereus|<sid>`, so the OS replaces instead of stacking. Click = focus window + open the session (`rvOpen` when review only).
- ⚠Off by default (quiet defaults) · ⚠no message bodies·tool input·relay text (AGENTS.md rule 1) · ⚠a click never goes on to the terminal — «Terminal» is pressed by a person.

### Context sources (2026-09-28)
- Server `sidereus/ctxsrc.py` → `GET /api/session/context?cwd=&sid=` (60 s cache per cwd). 400 = missing cwd·relative path · sid format · cwd not on screen.
- Response `{ok,cwd,root,at,bytes,tokens,instr:[{path,scope,bytes,tokens}],memory:{dir,index,bytes,tokens,files},mcp:[{name,scope}],hooks:[{event,n}],skills:{user,project},agents:{user,project},counts:{instr,memory,mcp,hooks}}`.
- Scanned: `~/.claude/CLAUDE.md`·`~/.claude/rules` · `CLAUDE.md`/`CLAUDE.local.md`/`AGENTS.md`/`.claude/CLAUDE.md`/`.claude/rules/*.md` from git root→cwd (cwd only without a root) · `~/.claude/projects/<slug>/memory` (cwd → root slug) · MCP names = `~/.claude.json` (user·`projects[cwd]`) + `.mcp.json` · hooks = event counts in user/project `settings(.local).json` · counts of skills (folders with `SKILL.md`)·agents (`*.md`).
- Screen: session work popup (`sess:` tabs only), a folded line «Context ≈ N tokens · instructions · memory · MCP · hooks» under the received instruction. Tokens = bytes/3.5 rough estimate («≈»).
- ⚠Paths·sizes·counts·names only — file contents·memory bodies·MCP commands/env·hook commands are never read into the response (AGENTS.md rule 1; tests/test_ctxsrc.py enforces it).

### Preferences (2026-09-28)
- Files: `sidereus/prefs.py` (allow-list·validation·atomic write, `GET /api/prefs`·`POST /api/prefs/set`) · `web/js/90b-mypref.js` (settings «Preferences») · `web/js/06-i18n-q.js` (I18N.en). Key table in README «Customising»·docs/CONFIG.
- ⚠Server values (`saver_hook_dir`·`compact_history`·`viewer_me`·`default_room`) are read at import ⇒ **applied after restart**. The screen shows «Applies after restart».
- ⚠Keys set by environment variables are read-only («env») and the server refuses writes — env wins over the file, so writing would have no effect.
- ⚠Tests never touch the live `config.local.json` — monkeypatch `CONFIG_PATH` to a temp folder (tests/test_prefs.py).
- ⚠Empty repo·empty config = the same pixels as the default screen. The timeline tab cannot be hidden.

## Open candidates (when the user asks)

- **Multi-platform (Windows·Linux) support** — investigated, then **deferred** (2026-09-22). Size and blockers in `docs/notes/multiplatform.md`.
- ⛔**Showing recent transcript lines** — **removed** from the candidates. It collides head-on with the rule above
  (*conversation content never goes on the page*). The session panel is metadata only; another session's conversation belongs to that user. Doing it
  requires changing that rule first, which is the owner's decision. Row titles show only `path · session id · model`.
- Whether **idle alerts should also become bell cards** — today they stop at the screen marker·filter (§8). In the bell, every idle session would pile up a card,
  the same noise learned from an external messenger. Only `Awaiting answer` is worth nagging about (same place as the mailbox's `MAILBOX_NAG_S`).
- Two sessions in the same cwd show as one state (process↔session cannot be mapped 1:1 — transcripts have no PID)


## Verification snapshot (2026-08-19 · after §8–16)

Historical record; current gates are AGENTS.md rule 3 and `scripts/check.sh`.

```
context %       6/6 sessions     all show % (2 used to show 152k·163k) · evidence obs 5 · model 1 (learned from 5 sessions)
window learn    win-model.json   opus-5·opus-4-8·opus-4-7=1M · sonnet-4-6=200k · 88 files scanned in 1.6 s
evidence dedup  per session      opus-5 n=82 (poll accumulation) → corrected to n=5 (session count)
3.9 compat      py_compile       /usr/bin/python3 passes (launchd interpreter)
after legacy    viewer·watch     http=200 · both launchd jobs alive · all 3 presences watching
per-card read   API round trip   unread 2→1 · watermark unchanged · history kept · newline injection refused
refactor        module equiv.    old/new compared at the same moment 6/6 sessions · 0 field mismatches · cold 181ms·hit 1ms
error paths     forced           ps timeout→last value · expired→unknown · sessions exception→empty list (page survives)
data backup     launchd+restore  exit 0 · 672K · restored 515 lines parse OK · mailbox_core reproduced
after restart   viewer.err       0 bytes (4 polls http=200 · 29~95ms)
bell stays open ★real browser    card click → window stays · unread 3→2 · badge 3→2 (real click via playwright)
toast           ★real browser    alive after 6 s · kept to 12 s by hover · gone 3.6 s after leaving
toast click     ★real browser    dismissed · badge 4→3 · **server records that key as read** · history kept · bell not opened
top bar         ★real browser    `Awaiting answer 1 · Unread 2 · Stale threads 6` · cell click → sessions 4→1 rows · cleared by ✕ chip
stale threads   ★real browser    6 (24h~14 days) + `14d+ · 11 excluded` shown · chip click → bubbles 526→5
work line       ★real browser    thinking = the current tool target · replied = summary
↻ resume        ★real browser    `claude --resume 0a2c7889-…` (full 36 chars)
name            fingerprint      charter sha256 `75c0d658` identical before and after (untouched)
bar visibility  ★measured coords inside header y=69 (on screen) · was y=-276,977 (off screen) · aside top 108/135 follows
drop handling   forced 5×        viewer.err 0 bytes (was a 20-line traceback per request)
whose turn      node+real data   target produced for all 6 (thread → agent)
decision tab    node+real data   decisions 57 · corrections 41 (page code lifted and run as is)
context card    8 isolated+live  88% session, one card · still one after 3 more polls
browser         ★not opened      plist --no-open · the user's tab only refreshes (playwright to look)
verification    ★rendered page   ⚠look at the screen — do not substitute `/api/...` responses (gates are the two lines below · separate)
favicon         qlmanage render  stoa path 1 · old envelope path 0 · shape survives at 160px/32px
wording         server response  Unread only 3 · Unread <b> 1 · Not read by them 1 (old short form only in comments, 7)
card hint       structure check  .chint is a child of crow1 · 0 float/negative margin/absolute on cards (overlap impossible)
py syntax       ast.parse        OK
JS parse        node --check     OK  ★this file's #1 trap — always pass it before restarting
duplicate ids   one decl each    OK (note·isIdle·copyText·IDLE_ST·markMin…)
12 filter combos 6 real + 4 synth idle30 does not catch `tool 2h`·`unknown 2h` (as intended) · wait 15 min caught only by idle10
server          /api/state       http=200 · 2.1MB · 63ms (cold) · page 1.2ms
page            id=sfil·data-cwd rendered
```
