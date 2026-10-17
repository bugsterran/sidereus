# Traps — Timeline

Conventions (entry shape, `★` `⚠` `⇒`, `§N`, `:NNNN`): [TRAPS.md](../TRAPS.md). Newest first within an area; new traps go at the top of their area.

## Timeline

- ★**The right «Changes» rail is gone; a toolbar chip replaces it** (2026-10-17). Cause: at 1100 the 400px rail left the Gantt ~386px and hid most bar labels; the rail entries below are history.
  - ⇒ `tlgChipHtml` (77) «Changes · N files +a −d», untracked excluded; «· ⚠ n shared» = rail files with `conflict` (tooltip lists paths only). Click = `loadDiff(cwd, '', b:<base>|work, '', sid)`; tree, baselines, untracked and repo tabs live in the diff window.
  - ⚠`tlgPaint` rewrites only `#tlgb` and clears the toolbar slot's `_sh`; without that, the next `tbSet` would compare against stale markup and skip a needed rewrite.
  - ⚠Fetch only from `tlgTick` while `mainView === 'time'` and the tab is visible, 30 s per cwd (`TLG_TTL_S`). Saved snapshot is `{sel}` only; old `sidereus.tlgit`/`tlgw`/`tlgUntr` prefs are ignored.
- ⚠**Timeline marks inside `.tlt` stay in the 4px band lane** (2026-10-08). Session bars fill 4..20px of the 24px track and `.tlt` is overflow:hidden; the pipeline «↺ sent back» glyph (`.tlplk`, 10px at bottom:3px) sat on top of the bars and read as broken. ⇒ It is now a 9x4px orange wedge in the band lane, text hidden, meaning kept in the title tooltip (21-timeline-plrun.css).
- **«Runs N» chip slid left and right in the header.** It came before the stepper key and both had `margin-left:auto`, so they split the free space and the chip floated mid-header, moving whenever text widths changed or the key came and went. ⇒ key first, chip last (74c `tlPlLegendFor`), `.tlplg + .tlplhb{margin-left:8px}`. ⚠Keep the chip the last header item.
- **«Apply» off records no run even while a session tags `[pl:…]`** (hooks `_apply_off`), so the row drew nothing. ⇒ row `plOff` (sessions._pl_off, boolean only) draws «Pipeline recording off» (74c `tlPlOffNote`). ⚠Keep it a boolean — the tag source is the Agent description; never send the label.
- **A session row with a pipeline strip (`.tlpl`) is taller than its name cell.** The cell was centered at ~19px, so clicks above/below it hit `.tlwrap`'s pin toggle and no work log opened. ⇒ `.tlrs > .tlnm{align-self:stretch}` (20-timeline.css) so the 74b name-cell handler covers the row height. ⚠Do not drop `.tlpl` from that handler's early return — the strip must keep opening the pipeline.
- **Name-column grip (`#tlnmg`, 74d) caps at half the Gantt column (`.tlaxr`), not half of #feed.** With the «Changes» rail open, half of #feed would shrink the track to ~150px. ⇒ `tlNmWClamp(w, axisRow.clientWidth)`. ⚠Do not make the grip an `<i>`: `.tllg i` (20-timeline.css) gives it a legend swatch size and margin.
- ★**`sessByIdle` sorts by `idle`, which only bgs rows carry** (2026-09-28, timeline «Changes» session picker). Session rows have `ageSec`, so the picker stayed in server order. ⇒ sort session rows by `ageSec` (newest first, name tie-break). ⚠Do not reuse `sessByIdle` on SESS rows.
- ★**Restored UI picks must wait for data** (2026-09-28, `sidereus.tlgsel`). `tlgTarget` used to drop a missing pick at boot while SESS was still `[]`, wiping the restored value. ⇒ forget a missing pick only after SESS has loaded.
- ★**The rail-width drag handle kept following the mouse during redraws** (2026-09-25 review; releasing the button outside the window sends no `pointerup`). ⇒ End at once when `ev.buttons` is 0 in `pointermove` (web/js/77-timeline-git.js:258). ⚠New drag handles must carry this guard too, not trust `pointerup` alone.
  - Rail commit-row click → reuses the existing diff popup pipeline with `scope=c:<sha>` (77-timeline-git.js:345, server check `_SHA_RE`/git_view.py:65,278). Popup boot accepts a scope with no file (99-boot.js:10). ⚠A new scope prefix must update both `_SHA_RE` and the boot parser — fixing only one opens the window with an empty diff.
- The timeline sleep band merges DarkWake wakes shorter than `TL_NAP_JOIN_S=60` (seconds, 76-timeline-drawer.js:112) (★based on measured pmset DarkWake max 45 s). ⚠Lowering 60 splits sleeps at common DarkWakes and shortens «longest gap».
- ★**A pmset failure painted «no sleep» for 2 minutes at a time** (2026-09-25; ★measured 9 timeouts in 200 lines of viewer.err). `[]` was cached with the same TTL as success (120s). ⇒ Failure/timeout keeps the previous value and retries only after `NAP_RETRY_S` (30s) (timeline_scan.py:390). A real empty array still replaces it.
- ★**The timeline axis end label was clipped** (2026-09-25, «05:» — the right rail narrowed the width, 12px overflow). Labels sit right of their tick, so only the last overflows. ⇒ `tlAxFit` (74-timeline.js) flips it to the left of the tick on overflow (`.tlaxe`) and hides it if it overlaps the previous label. Re-measured by ResizeObserver whenever the width changes. ⚠Do not decide by a % threshold — it depends on width.
- ★**Labels inside bars overflowed and wrapped to two lines** (2026-09-25, «22 min · 6M» · 10 cases with the rail open at 1280). The `w > 3`/`w > 7` % thresholds were wrong when the px width shrank. ⇒ `tlBarFit` (74-timeline.js, called from the same ResizeObserver as `tlAxFit`) measures in px: «min · tokens» → «min» (`data-s`) → hidden. CSS `white-space:nowrap`. ⚠Never cut mid-text — drop whole parts only (full numbers are in the hover card).
- ★**After a language switch the timeline stayed in the old language** (2026-09-25, rail «Changes»). `time` was missing from `setLang`'s tab-redraw list and `full()` cleared #feed. ⇒ Added `paintTl()`. Add every new tab to this list.
- Rail file rows (2026-09-25): status is **name colour** (added blue · modified/renamed green · deleted grey + strikethrough); the text is only in title/aria-label. Extension chips = one row in the `TLG_FT`/`TLG_FN` table + CSS colour (`.tlgi-<key>{--h}`). ⚠No copied brand logos — own letter chips only. Test `test_tlgit_tree.test_file_type_icons`.
- ★**Timeline first load 1.9–3.5 s**. Cause: `naps()`'s `pmset -g log` (1.4–1.5 s) ran inside the request at every TTL (120 s) expiry. ⇒ Once filled, the old value is served and refreshed in the background (`_naps_refresh`). `tests/test_naps_cache.py`. ⚠Cold (right after restart) the main cost is `_seg_scan` — 160k strptime calls replaced by the hour-level cache `_fast_ts`, 2.9 → 1.9 s (`tests/test_fast_ts.py`, checked against the old parser). `_tl_warm` covers the rest.
- ★**Timeline left-column description → hover card** (2026-09-24). Removed the inline «N min total · description» text from agent rows (connector·icon·name·dot·i/N·count only). Session rows were never cut, so «55 min» stays.
  - ⇒ `#tlhc` card on `.tlnm` and bars (`data-tlh/tli/tls`) (74-timeline `tlHovHtml`): description (Agent `description`) · type · state (running/ended `fin`/stopped without report) · model (sessions only, SESS) · span · activity · this segment (bar) · tokens · tool calls `tc` · last tool · worktree · path·id. 150ms delay · edge flip · hidden while dragging/scrolling · also shown on focus.
  - ⚠Never show alongside a native `title` — `.tlnm` and bar titles were removed, and the state-dot title the 2.5 s sync re-adds is removed when the card opens.
  - ⚠Metadata only: last tool is **name only** (the ` · target` part of `last` is dropped). Session rows do not carry `desc` (the session task — it may be a prompt).
- ★**Timeline right-side «Changes» rail** (2026-09-25 · view only). Toolbar «Changes» toggle (`sidereus.tlgit`, closed by default · hidden below 1100px) · target = cwd of the hovered row, else the most recently active session.
  - Server `/api/git/diff?view=rail` → `sidereus/git_rail.py _git_rail` (split from git_view 09-25 · lazily imported by `git_diff`; 3 git calls: status v2 · `diff HEAD --raw --numstat -z -M` · log -5, no bodies). Existing calls unchanged.
  - Untracked files (excluding .gitignore) also show as «added» — taken from the same status call (`-z --untracked-files=all`), so still 3 git calls · max 200 (`RAIL_UNTRACKED_MAX`; past that only `n` grows, «first N only») · line counts only for text ≤ 1 MB, counted directly; a NUL means binary. ⚠Paths are relative to the repo root (`_repo_root`).
  - Untracked file click → the popup appends `&new=<path>` (`dfNew`, scope=work only) and gets that single file as an all-added patch (`_untracked_patch`; the full-expand `/api/git/file` too). ⚠There is still no bulk untracked view (08-25 decision) · refused if realpath is outside the root, a symlink, or absent from `ls-files --others --exclude-standard`.
  - Polling is `tlgTick` in `poll()` — only while open and visible, 10 s per cwd (`TLG_TTL_S`). File click = `loadDiff(cwd, path)` → popup `&scope=work&file=` selects that file (`dfWant`).
  - ⚠`paintTl` replaces `#feed` wholesale, so the rail is redrawn inside `tlgWrap` every time. The demo `/api/git/diff` returns empty, so the rail shows «No changes».
  - Repo chips hide a repo with 0 shown files (`tlgRepoChips`, count = `tlgShownN`, same as the header) behind «+N clean»; `tlgTick` fetches up to 6 other repos at 30 s (`TLG_BG_TTL_S`) under the same cache key a chip click uses. ⚠Unknown status (no reply, `!ok`) must stay shown — hiding it drops a dirty repo before its fetch lands. ⚠Selected repo is never hidden.
- ★**Right after restart the timeline tab was blank for seconds to tens of seconds** (2026-09-23). Cause: `bootView()` had no `time` branch, so nothing drew `#feed` before the first response.
  - ★Measured cold `agents_timeline(1)` 2.9s alone (sessions 1.05 · pmset `naps` 1.35 · segments 0.45) · 5.5s beside the startup thread · warm 0.01~0.07s.
  - ⇒ `bootView` gets `paintTl()` + «aggregating the timeline… N s» · 90 s abort · «Retry» on failure · server `_tl_warm` (once for 12h, 4 s after start; first request under contention 5.5s → 0.2s).
  - ⚠The `naps` cache has a 120 s TTL — warm-up cannot remove the 1.35s pmset of the first request after that.
- ★**Timeline rows carry two fields, `tc` (tool count) and `fin` — not in meta.json, so the body is counted** (2026-09-22).
  Cause: the response had no tool-call count, so the summary card used the `segs` count (activity segments). The only source is `tool_use` blocks in the agent `.jsonl` body.
  ⇒ `sidereus/timeline.py` `_tl_agent_row` (**agent rows only**) carries `_agent_tools(fp)`·`_agent_fin(fp)` (`sidereus/agents.py`); the summary card total changed from «N activity segments» ⇒ «N tool calls». ★Measured cold 46 files 20.7MB **0.10 s** · warm 0.0002 s.
  ⚠**Never count by substring alone** — a `tool_use` quoted in a report counts as one. Only candidate lines are JSON-parsed.
  ⚠**Never call `fin` «abnormal exit»** — it only means «the last record is a tool call» (to avoid false positives on just-ended rows, only rows 5 minutes past `end` count).
- ★**The empty space at the timeline bottom was not padding but the «selection detail drawer» (`#tldrw`)** (2026-09-22).
  Cause: with nothing clicked its height is 0, so it always looked empty. ★Measured `#feed` 1217px · `.tlwrap` 609px · **empty drawer 615px ≈ 46vh**.
  ⇒ New `tlSumDraw()` — with no selection a **summary card** (145px); clicking a bar covers it with the detail (379px); `✕` **returns to the summary**, not blank (`tlOpen` path unchanged). The summary holds four things «the bars cannot say» — total · longest gap · what is running now · span outliers.
  ⚠**Never fill it by auto-selecting** — `paintTl()` redraws `#feed` wholesale every 2.5 s poll, so the detail would bounce every 2.5 s.
  ⚠**Bounce prevention cannot rely on string comparison alone** — right after `#feed` is replaced, host is an **empty new div**, so comparing only the previous render string never draws. Check `host.firstChild` too (★measured: in 8 s / 3–4 polls, 1 DOM replacement · real value changes).
  ⚠**Fields missing from the response** — with no tool-call count the `segs` count stood in, and agent rows have no `state`/`blocked` (session rows only), so «abnormal exit» could not be shown — span outliers only.
- ★**The timeline axis reads by «weight», not colour — `.tlax`** (2026-09-21).
  All 24 ticks were one 9.5px `#6f7889`, flat. ⇒ Raised to 10.5px and lift only **3-hour/on-the-hour (`.tlaxm` #cfd8e6) · midnight (`.tlaxd`, `9/21` instead of a time) · now (`.tlaxc` #8ab4f8)**.
  ⚠**The axis is background — it must not stand out over the bars.** Do not brighten everything; lift only the major ticks. No new colours either (reuse existing tokens).
- ★**Transcript tails are read «only as far as they grew»** (2026-09-18). `/api/agents/timeline` re-read
  **109.1MB** every request — the `_SEG_RAW` key included `size`, so **one appended byte missed the whole file**, and
  `_compacts` had no cache. ⇒ `_tail_incr()` continues reading **only the new tail** after the last `(start, end)`.
  ★Measured **643.9MB → 17.8MB (36.1×)** · old code = new cold = incremental, identical `rows` JSON (33 rows ·
  109 segments · 209,381,022 tokens · 19 compactions).
  - ⚠**Consume only up to the last newline and leave the offset there** — during an append the last line is half-written.
    Putting the half in the offset makes the next read start mid-line, splitting it in two and **dropping both**.
  - ⚠If `size` is **smaller** than the last `end`, treat it as a different file (rotated/rewritten) and re-read it all.
  - ⚠Accumulation grows at the front ⇒ trim **from the front** with `lim` (segments) and 200 (compactions). Only old
    entries outside the window are trimmed, so results with `cut` applied do not change.
  - ⚠**Never bake `cut` into the cache key** — it differs every call. The cache holds only `cut`-independent raw data;
    the `cut` filter, `[-20:]` and response de-duplication (`seen_resp`) are re-applied each time.
- ★**An empty stretch in the timeline may be «the Mac slept», not «unused»** (2026-09-17). ★Measured: the
  transcript was empty for all of 15:09·15:10·15:11 and `pmset -g log` recorded
  `15:08:08 Entering Sleep state 'Idle Sleep'` → `15:12:23 Wake from … UserActivity` (4 min).
  ⇒ `naps()` (`chat_server.py`) emits those spans, carried as `naps` in `agents_timeline`, and drawn on screen as a
  grey hatched band (`.tlnap`).
  - ⚠**Never count `DarkWake` as awake** — it is a few-second maintenance blip. ★Measured
    12:14~13:32 was 6 repeats of `DarkWake`/`Sleep` but **one long sleep** (part of a 607-minute span).
  - ⚠**Filtering by substring (`"DarkWake" not in ln`) also drops real full wakes** (2026-09-18) —
    full-wake lines contain `DarkWake to FullWake from...` in their description. 17:06~17:38 (32 min)
    vanished entirely ⇒ decide by the **event-type token** right after the timestamp (`Wake` vs `DarkWake`).
  - ★**«asleep» = «asleep + no records in that time»** (2026-09-18). Between 17:06~17:38 a `DarkWake` lasted
    **27 min** (1618 s), during which 20 lines of work (session 13 + 7) were logged at 17:11~17:12, and the band
    covered them ⇒ `_naps_awake()` **merges every row's `segs` and subtracts them** (no transcript re-read ·
    `NAP_MIN_S` still applies to fragments). `_nap_parse`'s DarkWake rule is unchanged — with no activity it is still one long sleep.
  - ⚠`pmset -g log` is tens of MB ⇒ narrowed with `grep -E`, `timeout=12` · 120 s cache (`NAP_TTL_S`).
    Failure/timeout = `warn_once` + **empty list** (the band is just not drawn; the screen survives).
  - ⚠**The first colour was invisible** (same day; hatch `#222834` was darker than the background) ⇒
    hatch **lighter** than the background + solid lines at both ends, and «asleep N min» text **on the axis row only** (when width ≥ 4%).
- ★**The other half of empty space = «idle»** (approved 2026-09-21). Spans that are not sleep and not covered by
  any row's `segs` — «absent because asleep» and «awake but not working» are different facts, yet both were blank
  (★measured 9/18 12:43~13:14 · 31 min). ⇒ `_idle_gaps()` computes window ∖ (sleep ∪ activity) (the inverse of
  `_naps_awake` · same inputs · no re-read), response key `idle`, drawn as `.tlidle` **one faint background layer** (not hatched).
  - ⚠**The sleep subtracted is the raw `naps()` — not the `_naps_awake()` result.** That one already has activity cut out,
    so idle leaks between the fragments and the two bands overlap. ★Measured overlap 0 (both 24h and 96h).
  - ⚠**Minimum length `IDLE_MIN_S = 600` (10 min).** With `NAP_MIN_S` (30 s) hundreds of gaps between bars are caught,
    the band becomes blotchy and thinner than the bar minimum width (0.5%), so it shows as dots. ★Measured: today's
    24h gaps were only 5 and 8 min, so **0** is correct.
  - ⚠Rendering also **carves out** the `TLBMINW` footprint (same trap as the sleep band — server overlap 0 is data;
    short segments spread sideways on screen due to minimum width). DOM order is `idleb+ticks+napb+bars`.
- ★**While a session is running the viewer keeps the Mac awake** (2026-09-17 · follow-up to the item above). Asleep, no
  requests go out and **the work itself stops** — 4 minutes lost at 15:08 while spending 184,868 tokens. ⇒ `_awake_loop`
  (40 s) counts `tool`·`think` (ball on the model's side) in `sessions()`; if any, it starts
  `caffeinate -i -s -w <server pid>`, otherwise releases it. ⚠`awake:{on,n}` in `/api/state` was removed 2026-09-25 by `bf1d256` (TRAPS.md entry) — not shown on screen; only the loop runs.
  - ⚠**Waiting for input (`wait`/`ask`) is not counted** — the person has stepped away and sleeping is fine.
    Blips between turns are covered by `AWAKE_GRACE_S 180`.
  - ⚠Never drop `-w <pid>` — if the server dies, caffeinate is orphaned and the Mac **never sleeps**.
    The only off switch is `AWAKE_HOLD = False` (for long stretches on battery).
- ★**Clicking an old session bar in the timeline showed the newest session's work log** (2026-09-09 · side effect of the «all files» fix below).
  - Cause: bars were per session (`tid = sess:<cwd>|<sid>`) but `/api/session/work` took only `cwd`, so it always
    read that path's **newest** transcript (★same cwd old/new: 89 steps 12.9MB ↔ 54 steps 1.07MB).
  - ⇒ ① `session_work(cwd, sid="")` — without `sid`, newest as before (the session-card path calls it so)
    ② JS `workUrl()`/`tidSid()` appends the sid from the tid in one place (poll, tab and drawer all use it)
    ③ tab title and `desc` get `· session <first 8>` (Korean suffix on the wire) — ⛔conversation content still never goes up, metadata only.
  - ⚠`sid` is external input — **never remove** `_sid_path()`'s allow-list (hex·hyphen) + rejection outside the normalized
    `CLAUDE_PROJECTS` (negative control: `../..`·`<sid>.jsonl`·80 chars all rejected).
- ★**Timeline tokens were 23% below actual** (2026-09-09).
  - Cause: `agents_timeline()` read session rows from **only the newest transcript per project** (`fs[0]`), so
    older sessions split off by today's `/clear`/restarts were dropped wholesale (★12h window 524.4M ↔ all files 678.0M).
  - ⇒ ① read **all** transcripts in the window (`TL_SESS_MAX`) ② unchanged files are not re-read (`_SEG_RAW`)
    ③ the row cap applies **before** `vec` folding and session rows are never cut (`TL_ROW_MAX`) ④ still one line per
    project — JS `if(sess)` drew only `items[last]`, fixed together.
  - ⚠**Never bake response de-duplication into the cache** — if the first line is outside the window and the copy inside,
    that response vanishes. Cache only `cut`-independent data; trimming and de-duplication run every time.
  - ★Verified: row sum = all files (12h 0.00% · 0.5~48h ≤0.03%) · `sum(tks)==tk` on every row · 0.37s→0.28s.
- ★**Replay froze in place** (2026-09-09). The mouse was the cause, in two ways.
  - ① `wrap.onmouseleave` had no `tlRpOn` guard, so leaving the cell set `tlCurAt = 0`.
    `tlRpStep` kept adding from 0, so the cursor stuck at the window's left edge — playback was still running.
  - ② `onmousemove` defers the cursor update to a rAF; pressing ▶ in between runs that callback **after playback
    starts**, jumping back to the old mouse position. ⇒ `tlRpToggle` cancels that rAF on start.
  - ★Measured: before the fix, stuck at 352px (cell left edge) for 1.5 s after `mouseleave` → after the fix it kept
    advancing 377.9 → 404 → 430.2 → 482.6 → 508.7px (with `mouseleave`·`mousemove` injected midway).
  - ⚠**All three paths need the guard** — `mousemove` (had it) · `mouseleave` (did not) · the scheduled rAF (did not).
    Click is the exception: clicking during replay «jumps there» **on purpose**.
- ★**The timeline flickered a few times and went blank** (2026-09-09).
  - Cause: `loadTl`'s `catch` **overwrote** `TLD` with the error object. A single fetch failure from a server restart or
    load spike wiped every bar (including the running marker). Server data was fine for all 44 s.
  - ⇒ On failure **keep the last data received** and say so in orange in the header. Overlap (`tlBusy`) and order
    (`tlSeq`) guards added too — there were two callers (main poll · `tlAgeTick`), so an old response overwrote a new screen.
  - ★Negative control: with `fetch` forced to fail, 37 bars · 2 running kept + notice shown; notice gone on recovery.
  - ⚠**Never erase what was drawn from received data** — this file's principle («never claim an unknown span was empty»)
    applies to loaders too. Check that `loadFail`·`loadWku`·`loadDaily` have the same shape.
- ★**The timeline did not recognise a running subagent** (2026-09-09).
  - Cause: `agents_timeline` matched `live` **by tool-call id only**. A resumed row (`SendMessage`) is keyed by a
    **new** tool_use id, unlike meta's original `toolUseId` (★measured: running `a31bcefe545aa46ed` (idle 1 s) had list
    tid `toolu_013vHK…` ↔ timeline row tid `toolu_01FhSz…` ⇒ all 12 rows `run=False`).
  - ⇒ Also link by `live_aid` (the agent's own `_id`). `sessions()` subs already provide `aid`.
  - ⚠**Never use a tool-call id as identity** — same root as `_meta_of`'s ★ and the 2026-09-07 completion-notice trap.
  - ⚠Keep the decision in `sessions()` alone — measuring separately by log mtime makes two screens disagree.
- ★**A «row total» on a single bar is cumulative — the question is «what that segment spent»** (2026-09-09).
  - Screen state then: the token **band** was already per cell (45 s); the problem was **session/agent bars** —
    the bar tooltip had only `05:58 ~ 05:58 · 0 min active · .mailbox-mcp`, and tokens were **one total (`tkSum`) in the
    row-name tooltip**. ⚠**Do not mistake the target of «cumulative only» for the band** — the target was confirmed
    first by reading the screen's (DOM) `title`.
  - Fix: the server emits `tks` per row (per-segment sums in **the same order** as `segs`). Assignment is «the segment
    covering that time, else the previous one» — usage records land right after work ends, so falling into gaps is
    normal. Hence `sum(tks) == tk` **always** holds (the screen shows both numbers, so a broken invariant is visible at once).
  - ⚠The same lesson was already learned with minutes («write the segment's own length» in this file) —
    **stamping the total on every segment repeats one number across bars and becomes false.**
  - ★**Side finding — a «7 min active» bar was only 8 `queue-operation` lines.** `_seg_scan` counted every timestamped line
    as activity, but that kind is a queue typed ahead while the model runs, not a trace of the model running (that bar's
    tokens were 0). ⇒ Excluded from segments. Kinds kept and evidence (24h · tail 12 files): `assistant` 2,567 (the only
    kind with usage) · `attachment` 1,603 · `user` 1,323 (includes tool results) · `system` 343 ·
    `file-history-*`·`frame-link` 127 — all written while real work happens.
    **Per-bar tokens were the detector that exposed this** — «7 min active · no token records».
  - «no token records» on a 0-minute bar is **normal** (a one-line segment). Do not hide it.
- ★**A «fixed-window counter» never promotes twice for a slow key**
  (2026-09-09 · measured by running `warn_once` soft promotion through `_quota_loop` on a virtual clock).
  - The check was «does the `quota-429` soft path actually run» and **it does** — the 6th 429 at about 740 s
    (backoff 30+60+120+240 + jitter) is promoted to the band.
  - ⚠**What follows was the opposite of the design intent.** The `_SOFT` window is cut from `first`, not rolled, so
    after promotion `_n` returns to 1 in the next window. But `quota-429`'s steady-state interval is the effective
    backoff cap (**240 s** + jitter ≈ 260 s), so **only 4 fit** in a 900 s window
    ⇒ it never reaches `SOFT_PROMOTE_N` (6) again and never re-enters the `_warned` path (age refresh).
    ★Measured (virtual clock 60 iterations = 4h): after one promotion (t=739) the band `at` **froze at 738.6** →
    with 429 still blocking, **it disappeared from the screen after 30 min (`WARN_TTL_S`).**
    The exact opposite of «an ongoing problem stays visible» promised by the `WARN_TTL_S` comment.
  - ⇒ Fix: **while an unexpired band entry exists, the count is not required again** (`_alive` in `warn_once`).
    ⚠Do not decide by `key in _warned` — that set only shrinks when ✕ is clicked and otherwise lives for the whole
    process, so a **single stray hit** much later would go straight to the band (defeating layer 1).
    Requiring 6 again after expiry is the only line between the two.
  - ⚠`QUOTA_MAX_BACKOFF` (300) is **never reached** — `_wait_hint`'s exponent is `min(fail, 4)`, so it stops at
    15×16=240. Several comments said "max 300 s · 6th at 750 s" (fixed).
    **Do not raise it to 300**: the 6th would be 750 s + jitter = up to 900 s, exceeding the `SOFT_WIN_S` (900) window,
    and promotion would **never** happen. To raise it, first increase `SOFT_WIN_S` — they are a pair.
  - Method (to reproduce): `main()` is behind a guard, so load as a module and swap `cs.time` for a virtual clock
    (`sleep` advances time — `warn_once` and `_quota_loop` read the same global `time`), replace only `_quota_fetch`
    with a 429 failure, and run the original loop. The loop is `while True` + `except Exception`, so
    **only a `BaseException` subclass can break out.**
    The 3 probes (detailed run · 4h long run · ★negative control) are in the session scratchpad.
- ★**Timeline tokens — a «rising number» was the core of the request** (2026-09-08).
  - ⚠**The band (graph) and header total were built first — what was wanted was «a rising number».**
    Now a large counter (`.tlodo`) sits **right under the time** in the cursor panel. ⇒ «going up» may mean a
    **number**, not a graph. Ask where first, or build both with the number on top.
  - ⚠**The counter is never abbreviated** (`toLocaleString()`) — with `fmtTok` (251M) it changes only per 1M, so the
    rise is invisible. `font-variant-numeric:tabular-nums` stops digit jitter.
  - ⚠**Partially covered cells add proportionally** (`tlTokAt`) — adding per cell (45 s) makes the number jump during replay.
  - Server: `_seg_scan` already passes **every line** of the tail, so tokens are counted there (third return value).
    Reading separately reads the same file twice (up to 80MB). Extra cost per line is one `find('"usage"')`.
    ★Measured cost (12h window): 0.55 s → 0.65 s. Definition matches `_today_fetch` (input + cache read + cache write).
  - ⚠**This number is the sum of «what this screen drew».** ★Measured (12h window): here 0.868B vs the daily card
    06–18h 1.231B = **70%**. Session rows read only the newest transcript per project
    (that is how they are drawn) ⇒ not hidden; stated in the header and tooltip.
  - ⚠`_tk` (time·token pairs) rides on rows and is `pop`ped at the end — leaking into the response turns a few KB
    into a few MB (★measured: no leak).
- ★**Replay (time-lapse) — a «self-walking cursor» is a different state from «pinned»** (2026-09-08).
  - What it is: pressing `▶` walks the time cursor from the window's left to the right (`tlCurT1` = now). Speed is
    «seconds of time / 1 real second» (`TL_RSP` · 1 min·5 min·30 min per second · localStorage `mbTlRp`).
    Right of the cursor (time not yet reached) is covered by `.tlfut`, so the day appears to fill in.
  - ⚠**Three states must stay distinct**: following the mouse · **pinned** (orange) · **replay** (teal).
    Merged into one flag, moving the mouse during playback makes the cursor jump, or after stopping the next mouse
    move flings it. ⇒ Keep `tlRpOn` separate and **turn on `tlCurPin` at that spot on stop.**
  - ⚠**`requestAnimationFrame`, not `setInterval`** — the browser pauses it when the tab is hidden.
    ⚠Clamp the frame delta **to 0.5 s** (`Math.min(0.5, dt)`) — on returning to the tab rAF's dt is tens of seconds
    and the cursor would skip hours in one frame.
  - ⚠**It stops by itself at the end** (no wrap-around loop). «Reached now» is the information to read, and a loop
    burns rAF forever.
  - ⚠**The rule that hides the cursor over the name column does not apply during replay** — stopping playback because
    the mouse moved to read a name would be absurd. For the same reason a click during playback is not a pin toggle but
    a **jump to that spot** (no separate rewind/fast-forward buttons needed).
  - ⚠`.tlfut` is on **only during replay**. On otherwise, it hides real bars and reads as «none».
    (`.tlwrap`'s right edge = the bar column's right edge, so `right:0` fits exactly.)
  - ⚠The 30 s repaint keeps running during playback — button text (`▶`/`❙❙`) and the `on` class must be
    **derived from `tlRpOn` when building the HTML** so state stays right after a redraw.
- ★**Time cursor (timeline scrubber) — the «drawing code» and the «snapshot» must share rules** (2026-09-08).
  - What it is: one vertical line (`#tlcur`) and a floating panel (`#tlcurp`) inside `.tlwrap`; the mouse x is
    converted to **absolute time** and shows that moment's sessions·agents·compactions·token rate. Click to pin.
    **The server was not touched** — the only input is the already-received `TLD` (no new API).
  - ⚠**The window (`t0`/`t1`) is a `paintTl` local.** The cursor converts from outside, so drawing exports
    `tlCurT0/tlCurT1`. A pin is held as **absolute time** — even when the 30 s repaint shifts the window it points to the
    same moment (`tlCurApply()` is called again at the same spot as `tlDrawer()`).
  - ⚠**Bar highlight is decided geometrically** (does `offsetLeft ~ +offsetWidth` cover the cursor x).
    A bar's `offsetParent` is its row's `.tlt`, so **one in-cell x checks every row**.
    ★Measurement caught «data list ≠ highlight»: at the window's right edge the panel said «1 session» but **0** bars were
    highlighted (bar widths are fractional pixels, split by one rounding step) ⇒ **±1px tolerance**.
  - ⚠**The panel list's «covers» rule must match `inWin`** — a session head draws no bar at all when `segs` is empty, so
    it counts as not covering; branches (agents) use the `start~end` fallback.
    (The same trap was already hit in session hiding — «has data» and «is drawn» differ.)
  - ⚠**The cursor is off over the name column (left 340px).** Bound to `.tlwrap`, events arrive over names too, and the
    clamped **line stuck at the window start** would falsely claim «that time».
  - ⚠**The panel must be `pointer-events:none` before pinning** — otherwise touching the panel cuts mousemove and the
    cursor freezes there. Once pinned it is enabled for reading and scrolling.
  - ⚠**The handler is on one container (`.tlwrap`) only.** Per bar it would be hundreds, and the cursor drops in the gaps
    between bars. Bar click (drawer) is separated with `closest('.tlb')`.
    Computed once per frame (`requestAnimationFrame` — it scans every bar).
  - ⚠**Token rate outside the live bucket (default 10 min) is `null` — never written as 0.**
    0 means «quiet»; outside means «no record». Bucket → absolute time needs `WKU.liveAt` (= `/api/live` `at`), so
    `loadLive` keeps it.
- ★★**When «accounting» and a «graph» share one list, the accounting reset erases the graph** (2026-09-08).
  - `_usage["live"]` means «**since the last backfill**» — when a ccusage backfill succeeds it is emptied on the spot
    (`_usage["live"] = []` in `_usage_backfill`). But the live sparkline (`_live_buckets`) **folded the last 10 min from
    that list** ⇒ every `USAGE_BACKFILL_S` (900 s) the graph regrew from 0. It looked «occasional» because the period is 15 min.
  - ★The causal evidence is **two numbers sitting together** (measured): oldest non-zero bucket **330 s ago** ·
    last backfill **334 s ago**. The window is 600 s, yet only post-backfill was filled.
    ⚠For the same reason `liveby` (live top 3) is not emptied, so there was an asymmetry — **top 3 stays, only the graph
      goes to 0** — such asymmetries narrow down the cause.
  - ⇒ **A sparkline-only buffer `_usage["spark"]`** (`(ts, tokens)` · never emptied, trimmed by age only · same as
    `liveby`). The accounting path (`live` and its reset) was **left untouched**.
  - ⚠**Simply removing `live`'s reset is not OK.** Double counting is already blocked by time
    (`usage()` uses `x[0] >= at` · `wkuse()` uses `ts > at`), so accounting does not need the reset, but without it the
    list **sits at its 20000 cap** and a cleanup rebuilding a 20k list runs on every event (1–2 per second). The 15-min
    reset currently hides that cost — «unneeded code» doing another job on the side.
  - ★Verified (backfill reproduced via module load): with 54 events in the 10-min window and `live` emptied, 54 non-zero
    buckets · max age 540 s **unchanged**, events outside the window (50 min ago) still excluded, and `usage()`'s
    summing path unchanged.
  - ★★**Live confirmation** — watched a real backfill pass at 30 s intervals (2026-09-08 17:31:44):
    «since backfill» dropped **685 s → 22 s** (= backfill just succeeded) while the graph kept **max age 170 s ·
    15 non-zero cells**. Before the fix, max age at that moment would be ≈ 22 s (= empty graph).
    ⇒ If this area is touched again, measure **these two numbers side by side**: non-zero max age in `/api/live` vs
      `usage.stale` in `/api/state`. The first larger than the second is normal; the two sitting together means it was erased again.
- ★★**To hide «rows with no bars», use the same decision as the «drawing code» — having data and being drawn differ** (2026-09-08).
  - **It is AND.** A connected session stays even with no bars — ★measured: at that moment two connected sessions had
    0 bars in the window but **were alive** (quiet is not absent · same principle as the 2026-08-24 trap).
    Three sessions were hidden, counted in the header as «3 sessions outside the window hidden».
  - ⚠**Session heads and branches follow different rules.** A session head with empty `segs` **draws no bar**
    (`sg.map`). A branch (agent) with empty `segs` draws `start~end` as **one bar** (`parts`).
    Applying the fallback to sessions at first judged them «has a bar», and rows that should hide **stayed.**
    ⇒ How it was caught: **counting `.tlt > .tlb` in the DOM directly** — three rows showed «0 min» with 0 bars.
      When fixing a screen decision, count «what is drawn», not the data.
  - ⚠Rows with only a compaction marker (`comp`) stay — that is visible on screen too; hiding it removes shown information.
  - ⚠★**The window parameter is `hours` (not `h`).** Measuring with `?h=1` makes the server **ignore it and use the
    default 12 hours**, leading to the **wrong conclusion** «narrowing the window keeps the row count = the server returns
    everything regardless of window». A code comment was once written from that conclusion and reverted. The server
    **does filter by window** — but session rows enter when **their span touches the window**, and their activity may be
    outside it, producing empty rows.
- ★**Git «Changes» rail must refit on `#feed` resize** (2026-10-05: rail 657px vs feed 631px on first paint, bottom 24px hidden; grip stretched to ~900px). `tlgWrap` measures `#feed` before the header rows settle, and `tlgFitH` ran only on window resize. ⇒ `tlgFitH` (called from `tlgWire`) attaches a ResizeObserver on `#feed` and sizes rail + grip; the grip is sticky (77-timeline-git.js, 22-timeline-git.css). ⚠A one-shot height at paint time goes stale.
- ★**Timeline showed the summary, a blank area and no rows** (2026-10-07, 2000px screen). `#feed` was the scroller and the git rail (`#tlgit`, `max-height:calc(100vh - 240px)`) could outgrow it, so `#feed` scrolled past every row. ⇒ on the time tab `#feed` does not scroll; rows scroll in `.tlscr` (74-timeline.js, 20-timeline.css), `#tldrw` summary pinned at the bottom, rail `max-height:100%` of its box. paintTl restores `.tlscr` scrollTop. ⚠Do not let a sibling size the rows area — height comes from `#feed` only.
- ★**Timeline bars are not tab stops** (2026-10-06, 1440: 242 bars + 41 rows = 293 tab stops in #feed; the git rail needed ~290 Tabs). `.tlb{cursor:pointer}` made 98-a11y give each bar tabIndex 0. ⇒ 98-a11y gives `#feed .tlr .tlb` tabIndex -1 (still `data-kb`, so Enter and poll-repaint restore work); arrows from the row reach them (74b `tlRoveTarget`). Enter/Space on a row clicks its `.tlnm` (the row's own click toggles the cursor pin). ⚠Do not set tabindex on bars in the render — a11yOne skips elements that already have one, so they would lose `data-kb`. Test `tests/test_tl_rove_js.py`.
- **Pipeline strip focus survives repaint only by id** (74c `tlPlWire`). `paintTl` rewrites `#feed`, dropping a focused strip to `<body>`, and removing a focused node fires no reliable `focusout`. ⇒ track the id on `focusin` (cleared on focusin/mousedown elsewhere) and refocus `#tlpl-<sid8>-<name>` with `preventScroll`. ⚠Never `scrollIntoView` here — the view must not move. The strip carries its own tabindex, so 98-a11y's `data-kb` restore does not cover it.
- **Live-stage pulse must key on «live», not on `end`** (74c, 35e, 21-timeline-plrun.css). A run with no `end` but no «run» stage is not live; 35e checked only `run.end`, so such a stepper could pulse. ⇒ both callers pass `fin` for every non-live run (`!end && plPrLive`) and the stripe animation hangs only on `.tlpst:not(.fin) > .pl-run`. ⚠A waiting segment never uses `--nx-rule` alone: it was near-invisible on both themes (dark: t3/rule mix · light: `--nx-field`, ≥3:1).
- **Header run chip «Stuck» keys on session idle, not stage age** (74c `tlPlHead`). A stage's `sec` is the age of its current pass: a 30+ min verify between turns or waiting on a background Bash read «Stuck · no activity 31m» while the session was active a minute ago. ⇒ third trigger = `SESS[].ageSec >= 1800` (mirrors `ATT_STALL_S`) with no running stage agent and state not think/tool; the other triggers are ask/abort and an ATTN `stall` sig. ⚠Never derive idle from `lt[t].sec`/`tot`.

### First poll did not repaint the Timeline head
- Cause: `tlPlSync` skipped the repaint on its first signature, and accounts never triggered one; the picker and «Runs n» lane are built only in `paintTl`, so a Timeline painted before the first poll kept neither until the next `loadTl` (30 s; never in Manual).
- Fix: repaint on the first signature too and include account labels in it (`74c-timeline-plrun.js` `tlPlSync`; debounced, one paint).
- ⚠Do not restore the first-call skip to save a paint — it is the whole defect.
- ★Headless demo, Timeline as start view: before = picker/lane absent after 6 s; after = both present.
