# Traps — Alarms, cards, health strip, attention

Conventions (entry shape, `★` `⚠` `⇒`, `§N`, `:NNNN`): [TRAPS.md](../TRAPS.md). Newest first within an area; new traps go at the top of their area.

## Alarms, cards, health strip, attention

- ⚠**«Mail waiting · session idle» is only for `state == wait` with no fresh wake lock** (2026-10-20). A `.wake/<sid>.lock` touched within 15 s (`sessions.WAKE_STALE_S`) means a waiter holds the session for mail, not idle; a working session reads its mail at turn end. ⇒ `mail_idle.annotate` skips both and counts only unacked/undelivered posts past the cursor, older than `mail_idle_min` (default 10). ⚠Counts and age only — never subject or body. Test: `test_mail_idle.py`.
- ⚠**A subagent's `idle` on the row is a snapshot, not a clock** (2026-10-14). `sub[].idle` is computed when the parse cache refreshes (`bgtasks._lab`), so `now - idle` drifts between refreshes and the permission badge blinked (missing 44/120 one-second polls). ⇒ `perm_marks._sub_act` reads the sub log's mtime (path from `note_sub_log`); `now - idle` only when the stat fails. ⚠Never compare a marker time against a cached relative age. Test: `test_perm_mark_sub.py`.
- ⚠**A `queued_command` attachment is not activity** (2026-10-14). A message typed while a tool waits for approval lands as an `attachment` line; counting it as activity cleared every main-turn permission badge. ★355 of 4,868 real `queued_command` lines landed while a tool call was pending. ⇒ `parse.py` skips it like `queue-operation`. Test: `test_perm_queue_activity.py`.
- ⚠**Parallel tool calls leave a row at «think» with a named tool** (2026-10-14). When one result returns while another call waits for approval, the last line is a tool_result, so the row reads think but keeps `tool`. ⇒ The permission badge checks think + tool as well as tool (same marker-newer / not-answered checks). ⚠Only `tool_decision` clears a pending tool; an OTel think still never does (e76d6704). Test: `test_think_row_with_tool_blocks_on_newer_marker`.
- ★**Bulk mark-read on alarms was slow** (2026-09-24). Cause: group/read buttons sent one POST per key + one server lock and file rewrite each (measured N=50 67ms · 200 159ms), and poll responses in between overwrote the optimistic `CRIDS`, so read state appeared to revert. «mark all read» was a tick late because `poll()` returned at once while a poll was in flight.
  - ⇒ `markCardsRead(keys)` → one POST `{keys:[...]}` → `mark_cards_read` one lock, one write (N=200 1.7ms). Keys in flight merge into poll results via `CRPEND`. Mark-all puts the response `at` straight into `CREAD`. `{key}` is still accepted.
  - ⇒ Auto-expiry: `cards()` sets `old:true` on done/general cards past 24h (`CARD_EXPIRE_S`) and failure cards past 3 days (`FAIL_CARD_EXPIRE_S`) → `isNew` and attention treat them as read (server-side, so badges agree across tabs and reloads).
  - ⇒ File pruning: `_card_add` removes lines older than 7 days (`CARD_KEEP_S`) once a day via `_atomic_write` (measured 2,384 → 760 lines · 555KB → 162KB · 6.8ms).
  - ⚠Prune only inside `_cards_lock` — without the same lock as append, a card appended between read and replace is lost. ⚠`_recent_card`'s `within_s` must be shorter than `CARD_KEEP_S` (longer → re-alerts after pruned cards) — checked by `test_cards_expire_trim`.
- ★**Failure tab → alarm cards** (2026-09-23; the tab was a list with no response guidance).
  - Server: `_fail_alert` (grade → flimit/fcut/fcheck; mine · noise raise no alarm) · `_wreck_cards` (uncommitted wreckage → fwreck). Key = kind|sig|tid or sid; the first scan seeds.
  - Screen: `15-alarms.js` `faLine` (one-line response) · `faBtns`/`faAct` (work log · diff · **copy only** of a follow-up instruction) · `faTip` (harness evidence text).
  - ⚠Card fields are metadata only (tid · sid · sig · why · label · n · reset). Copied text never includes conversation content or the task description (adesc).
  - ⚠`/api/failures` · `/api/wreckage` stay (for attention and «Insights»). A stored `mbMainView='fail'` falls back to the timeline.
  - `POST /api/wreck/dismiss` · `/api/wreck/send` removed 09-24 — no screen called them (cards only copy). ⚠`wreck-dismissed.json` (7 entries) stays read-only and feeds the `wreckage()` filter.
- ★**`state().attention` = ranking of sessions that need me** (2026-09-23 · `sidereus/attention.py`). Row `{sid,cwd,project,branch,score,why,since,sigs[{k,why,pts,since}]}`.
  - Score = top signal pts + 5 per signal kind · ties go to the older since. Table `ATT_PTS` (blocked 100 … bgdone 15). No quota signal (owner decision: nothing to do per session).
  - ⚠Several cards of one kind fold into **one signal** — unfolded, 29 unread done cards gave +145 and outranked an approval wait (100) (measured).
  - ⚠Card and tool failures attach only to the **single most recent session** of the cwd. Tool failures read `failures._FAIL_EV` via getattr only (30 s TTL).
  - ⚠toolfail = **same error signature 4×/10 min + within the last 3 min**, excluding `_TF_BENIGN` (Exit code · File does not exist, etc.). Counting every is_error put busy healthy sessions first (measured 09-23 · Exit code 1 was 185/322).
  - ⚠The loop signal `rep` is `parse._tail_rep` — key is (tool, hash of full input). Switching to the display target flags Reads differing only by offset as a loop.
  - ★**A /loop cron raised «Bash same call 8×»** (2026-10-12, session b8382e5b; cron every ~10 min ran the same Bash once per turn, results differed each time). Cause: the count crossed turn boundaries. ⇒ `_tail_rep` stops at `queue-operation` and at any user record that is not only tool_results (`_turn_break`). ⚠No keyword (sleep etc.) exclusions — the turn boundary is the rule.
  - ⛔`why` is built from tool name, count and minutes only — never task/reply/card bodies.
- ★**The tab title counts «sessions that need my hands» first** (2026-09-23 · ADE research — Vibe Kanban and Conductor surface waiting alerts outside the screen).
  - `[n] (m) <old product name>` — `n` = `blocked` · `ask` · `abort` (`needsMe`/`handsCount`/`titleOf`, `:12715`), `m` = the existing unread chat count. A 0 drops its slot. Measured `[1] (45) <old product name>`.
  - ⚠Do not count `wait` · `tool` · `think` — idle sessions are all `wait`, so the badge would always be on and meaningless. ⚠The `ISPOP` (popup) title branch is separate (`:14160`).
  - ⚠No OS push or sound — external messenger notifications were dropped for being too frequent. A badge inside the already-open tab is not subject to that.
- ★**Stale values say so on screen — `health.stale`** (2026-09-21). The fallback was right but the fact lived only in
  `viewer.err`, so the user could not tell how old a value was. The fallback site records `_stale_mark`
  (last success time) and the health strip appends «using the previous value · process 12 s ago».
  - ⚠Shown **only when stale** (normal → `stale:[]` ⇒ 0 characters). Removed at once on success, and dropped if no fallback within
    `_STALE_SHOW_S` (15 s) (so the conditionally called `tool_busy` does not stick).
  - ⚠The server sends **absolute times only** (`health()` contract). Under 60 s `agoAt` collapses to «just now», so the
    screen-only `agoSec` counts seconds. Only times go up — never conversation content.
- ★**Tool failure metric — OTel received `ok` · `lastTool` and overwrote «only the last value»** (2026-09-21).
  - Cause: no cumulative counter, and `_otel_state()` did not return the two, so they were discarded before the screen.
  - ⇒ Per-session `_otel_tools{tool:[calls,fails]}` + all-session total `_otel_tools_all`, top-level `state()`
    `toolStats` (screen table `fvTools()` removed with the failure tab 2026-09-23 · the `state()` field removed 09-25 — «Insights» has `retro.py` call `_otel_tools_summary()` directly).
  - ⚠The canonical table is the **top-level total**. Drawn from the session row's `otelTools`, the axis vanishes when OTel state
    **expires at 300 s**.
  - ⚠In-memory, so 0 after restart ⇒ the screen says «counted since server start».
  - ⚠Tool **names and counts only** (no argument or result bodies). Cap 40 kinds per session, overflow goes to the Korean «Other» bucket.
- **«Tool ranking» card — per-day tally `otel-tools.json`** (`_otel_tday`, `_otel_tool_rank`).
  - Per day `{ymd:{tool:[calls,fails,msSum,msN]}}` · kept 31 days · 160 names/day + the «Other» bucket · saved alongside `_otel_src_save` (60 s throttle).
  - ⚠Counts start at **first ingest** — days before rollout are empty (`from` = oldest day held). A restart no longer resets it.
  - ⚠A fail counts only on an **explicit false** `success`. Names, counts and durations only.
  - ⚠The load merges additively ⇒ `_otel_tday_load` re-checks `loaded` under the lock (save loop vs retro request would double-count).
- **«Time spent» · «Cache rewrites» cards** (`_otel_tool_rank` `time`/`tms`/`fms`, `sidereus/otel_cache.py` `otel-cache.json`).
  - Tool rows gained a 5th field `failDurMs`; files written earlier hold 4-element rows ⇒ the load pads 0. ⚠Never drop non-5 rows (old days would vanish).
  - The cache split is a separate store; ⚠the token sum (`_tkn` → `_usage_add`, `_otel_src_add`, sparkline, quota) stays read + creation + input + output — do not subtract.
  - ⚠`_oc_add` runs with `_otel_lock` held ⇒ `otel_cache` uses only `_oc_lock` and must never take `_otel_lock` (deadlock).
- ★**The same warning came back 2.5 s after closing it** (2026-09-09). Two causes overlapped.
  - False positive: `selfcheck` ② (alive on screen but missing from the official list) flagged **a live session** as a ghost.
    Measured — pid 78979 `claude --resume c5b6f705…` had run for 13 min but was absent from `claude agents --json`.
    ⇒ Exclude from the comparison when `sid_alive` (= the very evidence `_sess_state` uses) is true.
  - Dismiss: ✕ only cleared `_WARN_LOG` · `_warned`, so with the condition unchanged it returned **on the next poll**.
    ⇒ `WARN_MUTE_S` (10 min) mute. It postpones, not disables, so a persisting problem returns.
  - ★Negative control: ghost rows with no sid evidence are still caught / the mute re-shows after expiry (measured via module load).
  - ⚠**The official list is sometimes wrong** — absent does not mean dead. Never conclude from one side alone.
- ★**`selfcheck` flagged a hook-spawned session as «a session we missed»** (2026-09-09).
  - The devil's-advocate hook starts **its own Claude session in a temp folder**:
    `/private/var/folders/…/T/devils-advocate-XXXXXX`. It appears in `claude agents --json` but is
    **by design absent** from our session list (not monitored and leaves no transcript — measured:
    `5e435f6b` on the strip had no file anywhere under `~/.claude/projects/`).
    ⇒ ①the check flagged it every time as «official running, screen ended/absent» (`viewer.err` 14 lines accumulated).
  - ⇒ Exclude via `_HOOK_SESS_RE` (`/devils-advocate-`) **only inside `selfcheck`**.
    ⚠**Never filter `agent_view()` itself** — pid↔sid attribution (`live_cwds`) uses that list as-is,
      so removing it there lets hook processes **leak back into path counting** (the defect fixed on 2026-09-08).
    ⚠**Never exclude the whole temp folder either** — subagent worktrees live in `/private/tmp/claude-501/…`
      and are sessions that **must show** (negative control confirmed: worktree sessions are still caught).
  - If the folder name changes the warning returns — **that is correct** (unknowns are not passed over silently).
- ★**3/4 of «too many warnings» was load** (2026-09-09 measured).
  `live-slow` (ps · cap 4 s) · `agents-slow` (`claude agents --json` · cap 6 s) · `mon-slow` were
  all `TimeoutExpired`, yet measured directly at the same moment **ps 0.03 s · agents 0.22 s**. The cause was not the commands
  but **load spikes** (load average then 14.77/20.58/16.53 · java 117% · Chrome 4 processes ·
  6 claude + subagents).
  - ⚠**`agents-slow` was a new warning source from 2026-09-08 14:20** — switching identity from argv guessing to
    `claude agents --json` added the first subprocess with a 6 s cap. Half of the «sudden increase today» was that addition.
  - ⚠`viewer.err` cannot split «yesterday vs today» — **lines carry no date** (append-only).
    And `warn_once` writes **only the first line** per window, so line count is **window count**, not event count.
  - **Caps were not raised — measurement gave no grounds.** 4 min, 40 samples: `ps` median 0.03 · p90 0.04 · max 0.05
    (**0** over the 4 s cap), `claude agents --json` median 0.20 · p90 0.23 · max 0.28 (0 over 6 s),
    load median 7.8 · max 9.3. Normal is **1% of the cap**, so exceeding 4 s means «100× slower at that moment», not
    «the cap is short» ⇒ with the spike size unknown, 8 s cannot be justified, and every extra second holds a poll.
  - ⇒ **Attribution** instead of caps (`_slow_why()`). Six slow/failure warnings carry «· load then 18.2».
    It is instantly clear the machine, not the viewer, needs attention, and after a few the threshold load
    emerges from measurement — set caps then.
    ⚠Without `getloadavg` it is an empty string (the warning itself is not lost). Both layers confirmed on real paths:
    layer 1 `live-slow … takes up to 30 s · load then 6.2` / layer 2 `live … falls to 'unknown' · load then 6.2` (English renderings of the Korean server text).
- ★★**Invariant self-check (`selfcheck`) — so the user is not the bug detector** (2026-09-08).
  With the official list available, **my verdicts can be cross-checked**. Called inside `state()` **before `health()`**
  (so it ships in the same poll). Three checks:
  | key | invariant | broken means |
  |---|---|---|
  | `sc-dead` | a session the official list says is running is not `done`/absent on screen | alive reported dead |
  | `sc-live` | a sid the screen says is alive is in the official list | ghost row |
  | `sc-mon` | running watches ≤ watches attached on screen | a watch attached nowhere |
  - ⚠**If `agent_view()` is `None`, judge nothing** — warning on «unknown» turns a slow official query into a false alarm.
  - ⚠**The `SELF_GRACE_S` (75) grace is mandatory.** As a session starts or dies the two sources differ briefly
    (poll period + official TTL 8s). `_self_since` records the first mismatch; warn only if it lasts longer, and
    clear on resolution. ★Measured: quiet in normal state · an induced mismatch yields one `selfcheck-live` after the grace.
  - ⇒ Whenever judgement logic changes, **add a check line here.** The point is that the screen raises symptoms on the strip
    by itself instead of the user reporting them.
- **Health-strip warnings were also «a list without expiry»** (measured 2026-09-07).
  `_WARN_LOG` is append-only, so a 429 sat there an hour after it cleared, and strip click only expanded/collapsed —
  no way to dismiss. Also `_warned` blocked re-output, so `at` **froze at the first occurrence** and
  "1 hour ago" could not distinguish «just happened again» from «ended long ago» — the age lied.
  ⇒ All three must be fixed together: ①refresh `at` on recurrence (stderr still once) ②`health()` drops entries older than
    `WARN_TTL_S` (30 min) but does not delete them from `_WARN_LOG` (a recurrence refreshes and re-shows)
    ③`POST /api/health/dismiss` — also removes from `_warned`, so it is **not permanent silence.** (✕ rows removed 09-26 — strip click = dismiss all; see «Warning strip split into two layers» below.)
  ⚠A short TTL hides **live** problems of slow loops (`WK_RETRY_S=600` · `QUOTA_SLOW_S=300`).
  ⚠A stopped thread (`dead`) cannot be dismissed — it is not a past event but a current dead state.
- ★★**The failure scan never looked at subagent logs** (measured 2026-09-07~08; a failure alert without the agent and task
  was not actionable). The failure scan used `_recent_transcripts`, which walks
  **only one level**, `<project>/<session>.jsonl`. Subagent logs are
  `<project>/<session>/subagents/agent-<id>.jsonl`, so **they were never scanned.**
  Measured: 38 subagent logs in the last 24h held 75 failures, while `/api/failures?h=24` showed **0**
  (52 from main sessions only). ⇒ A failure-scan-only `_fail_transcripts` widens **just the file list**.
  - ⚠**Never make `_recent_transcripts` recursive** — it has 6 callers and `sessions()` shares it, so
    **subagents would appear as sessions in the session list.**
  - ⚠**Cap main and subagent shares separately** (`FAIL_MAX_FILES` 60 / `FAIL_SUB_MAX_FILES` 400).
    One shared cap lets subagent files push out main files, and **currently visible failures disappear.**
  - ⚠**`ev["afile"]` is set only on events without a tid.** Events with a tid are «a child's completion notice»;
    recording the parent file carrying the notice as the child's log makes `wreckage` read the wrong agent's file list.
  - Identity is attached **regardless of `kind`** — via the `_id` reverse index. The old branch named only
    completion notices in the parent transcript (`kind=="agent"`).
  - ★Live check (2026-09-08 · rendered screen): failure catalogue lines carry agent type, task description and session —
    `3 cut-off limit reached — session / repo-B-bugfix 3 @ repo-A 3 · 4 days ago` ·
    `276 routine Exit code N / repo-B-bugfix 72 · general-purpose 25 @ repo-A 172 · bot-A 54 · 2 min ago`.
    In the 24h window of 127, rows with identity 9/19.
  - **Open**: newly caught subagent failures are mostly graded `noise` (tool error) · `mine` (hook block), but
    **default grade chips are only `check`/`cut`**, so they are hidden by default (16 of 745 visible in the 7-day window).
    Whether to show them by default is **pending an owner decision.**
- ★**Warning strip split into two layers — non-actionable warnings stayed up** (measured 2026-09-07~08).
  The code already had two layers by cause — `*-slow` keys
  (`live-slow` · `mon-slow` · `busy-slow`) are **covered by the previous value (fallback)**, so the screen was right and there is
  nothing for the user to do. Bare keys (`live` · `mon` · `busy`) mean the fallback ran out and the display fell to «unknown».
  **Yet both went on the strip alike.**
  ⇒ `warn_once(key, msg, soft=False)`. With `soft=True` it still writes stderr but does not go on the strip —
    it **only counts**. `SOFT_PROMOTE_N` (6) repeats within `SOFT_WIN_S` (900 s) promote it to the strip,
    with «repeated 6 times in 15 min — still slow» appended.
  - ⚠**The counting code must come before the `_warned` early return.** After it, counting stops at the second occurrence and it
    **never promotes.**
  - ⚠**The key is not pushing to either extreme** — always shown (before) leaves non-actionable warnings up;
    never shown misses persistent slowness. **Promotion by measured repetition** is the dividing rule.
  - `soft=True` in **exactly 4 places**: `live-slow` · `mon-slow` · `busy-slow` · `quota-429`.
    Layer 2 (bare keys) and thread death go on the strip **at once** (the display really is wrong).
  - Constants (measured): at load 12, 24 calls over 60 s, 0 timeouts · from 133 `viewer.err` lines
    `live-slow` 10 / `mon-slow` 1 / `busy-slow` 0 / `quota-429` 7 · recurrence interval live · busy 2.5 s ·
    mon 5 s · `quota-429` backs off 30/60/120/240/300 s, sum ~750 s < 900 s.
  - ★Live check (2026-09-08): the restarted server's `state.health` has a `soft` field,
    `warns 0 · soft []` · on the rendered screen `#hlb` is `display:none`. The `live-slow` that sat there the day before is gone.
  - ★**Strip click = dismiss all current warnings** (2026-09-26).
    ⇒ `POST /api/health/dismiss` per key (optimistic hide, failure via `note()`) · no expanded list or ✕ rows · details in the strip `title` tooltip (`25-health-todo.js`).
    ⚠Strips with only idle or stopped threads have no click action → `cursor:default`. A pointer cursor that did nothing was the original defect.
  - ⚠**Unverified**: the `quota-429` soft path was checked only by AST, **never exercised through the real `_quota_loop`.**
  - Side note, not fixed: `mailbox_watches()` calls `live_cwds()` again and the failure path does not refresh the
    cache time, so `live-slow` can fire **twice in one poll**.
- **Live sessions of another account flagged «status uncertain»** (`live_probe.agent_view`, `sessions_health`).
  - Cause: `claude agents --json` lists only the sessions of its own `CLAUDE_CONFIG_DIR`; one lookup missed every other account, so selfcheck (2) called them ghosts.
  - ⇒ One lookup per `claude_roots.accounts()` dir (dedup by realpath), merged by pid, each with its own last-good and negative cache; `agent_view_unknown()` names the failed accounts and selfcheck skips their rows.
  - ⇒ Strip shows only `BANNER_KEEP` keys, each with an action clause; every other warning goes to `health().diag` (not drawn).
  - ⚠Extras run with `CLAUDE_CONFIG_DIR=<dir>`, but the default `~/.claude` runs with it unset. ⚠A new warn key stays off the strip until added to `BANNER_KEEP` with an action.
  - ★2026-10-12: `3d2bbbfd` and `5ff9b286` under `~/.claude-<account>` were flagged `selfcheck-live` while alive.
- **A dismissed «blocked» row never came back for a new prompt** (A2, `attention._row_sigs`, 43 `ntfStep`). Cause: `since` = now - ageSec followed main-row activity, so dismissal and the OS alert keyed on the wrong episode.
  - ⇒ marker rows carry `blockedAt` (marker time); the blocked signal uses it as `since` and `ep`; `ntfStep` keys `sid|k|ep`. `tests/test_attention.py`, `tests/test_os_notify.py`.
  - ⚠Only marker-based rows get `ep` — transcript `_blocked` t0 jitters ±1 s and would re-fire every poll.
- **A prompt opened mid-message never showed «blocked»** (`perm_marks.perm_rows`, `_pend_mark`). Cause: Write + Bash + AskUserQuestion in one message — the later tool_use lines pushed last activity past the Write marker (`_mark_t` needs `act_at < t`), and the row then went `ask`, which `perm_rows` skipped.
  - ⇒ fallback compares the marker with the oldest unanswered tool_use of the newest tool_use message (`_pend_ts`, transcript tail, cached by mtime+size); `ask` rows are checked too. `tests/test_perm_mark.py`.
  - ⚠On an `ask` row a tool-less or AskUserQuestion marker is the question itself. ⚠Only a decision for the marker's own tool clears it (OTel decisions are session-wide).
  - ⚠Still open: one marker file per session — a later prompt overwrites the earlier record.
