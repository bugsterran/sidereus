# Traps — Server, /api/state payload, caching, performance

Conventions (entry shape, `★` `⚠` `⇒`, `§N`, `:NNNN`): [TRAPS.md](../TRAPS.md). Newest first within an area; new traps go at the top of their area.

## Server, /api/state payload, caching, performance

- ★**The `claude agents` budget (≤ 2/min) holds only in registry-signature mode** (2026-10-25, #24, `scripts/perf_budget.py`). ★sessions/ present: 1 spawn per simulated minute.
  - ⚠No `<config dir>/sessions/` dir ⇒ `_av_registry_sig` returns None ⇒ plain `AGENTS_TTL` 8 s ≈ 7.5 spawns/min (sidereus/live_probe.py `_av_one`).
  - ⇒ The budget run writes a `sessions/<pid>.json` first; never call `agent_view(ttl=…)` from a poll path.
  - ⚠`--live` warm p90 is a plain GET served from cache (★2 ms) — labelled `warm p90 (cached)`, informational, not a state() cost.
- ★**Boot warm-up threads ran in parallel and spiked memory** (2026-10-22, #20, `sidereus/boot_queue.py`): ★peak ~478 MB parallel vs ~301 MB serial.
  - ⇒ Each one-shot warm wraps its heavy pass in `boot_queue.gate(name)`: one holder at a time, `ORDER` decides who goes next, drained after all finish or `BQ_DRAIN_MAX` 600 s. Switched-off warms are pre-marked done.
  - ⚠Register a warm's «busy» state inside its gate, not before: `toolidx.warm()` set `_TI_STATE["bg"]` while still queued, so `_kick()` from Harness saw a live scan and started none until the earlier warms released.
  - ⚠Never hold the gate across a wait for an outside event (e.g. the first quota sample) — every later warm stalls until the 600 s cap.
- ★**A stalled server left the bar «● Connected»** (2026-10-13 sandbox, SIGSTOP 20 s: CONN.fails stayed 0; 7 pending `/api/live` used up Chrome's 6 connections per host). Cause: `getJSON` had no timeout, so one `/api/state` hung and `pollBusy` skipped every later tick.
  - ⇒ `getJSON(url, {timeout})` aborts (default 120 s, `e.timeout`); the poll passes 15 s warm / 75 s cold or after an outage (STATE_COLD_S 60 s) → `pollDown`; `loadLive` has a `liveBusy` guard + 10 s.
  - ⚠Never fire a timer-driven fetch without an in-flight guard, and never give a cold path (first state, timeline 90 s) the warm timeout. Test `tests/test_getjson_timeout_js.py`.
- ★**`/api/quota/burn` cold miss took 6-20 s and hooks timed out** (2026-09-29 after a reboot, /usr/bin/true 0.6 s; 28 hook_cancelled in one session). Cause: `_tok_events` -> `_tl_pick` ran a 40 s cold `sessions()` in the request thread every 30 s TTL miss.
  - ⇒ `_tl_snap_rows()` (sidereus/timeline.py): fresh snapshot (0.5 s wait) → last snapshot → `[]`; a snapshot-less result is cached only 5 s.
  - ⚠Never call `sessions()` from a request or hook path (saver.py · mailbox_stop 5 s · invite_notice 10 s call burn). Test `tests/test_tl_pick_nospawn.py`.
  - ⇒ (same day) every request path — `state()`, git, recent, work, routes_post, agent_brief, burn_scan — reads `sessions_cached()` / `sessions_rows()` (sidereus/sessions.py): fresh snapshot, else one background refresh + ≤0.5 s wait, else the last snapshot. ★state() with sessions() stubbed to 5 s: 5.29 s → 0.52 s. Test `tests/test_sessions_cached.py` (no request module imports `sessions`).
- ★**A cold request path must join the in-flight `sessions()`, not start its own** (2026-09-28, «Structure» right after a restart: 7.1 s). `_allowed_cwds()` with no snapshot ran a second cold `sessions()` beside the page's first `/api/state`, doubling CPU in the startup burst. ⇒ `sessions_snapshot_wait()` (sidereus/sessions.py) waits for the default call in flight; nothing in flight or timeout = the old path. ⚠Do not call `_allowed_cwds()`/`sessions()` on a request path when a snapshot can do.
- ★**The first `/api/state?since=0` carried every body** (2026-09-28 — 1013 posts, 2,942,050B). ⇒ Bodies only for the latest 200 (`bus.MSG_FIRST`); the rest go as `stub:1` (metadata without body) — bodies are filled on demand via `GET /api/messages?after=&before=` (`hydrate()` · `mbody()`, web/js/10-feed.js). ⚠New code reading bodies uses `mbody(m)` and calls `hydrate()` for stubs — reading `m.body` directly leaves old posts blank. ⚠Never drop stub rows — threads, counts and verdicts use the whole MSGS.
- ★**Agent file caches grew without bound keyed by (file, mtime), or were wiped whole by `clear()`** (2026-09-25; the timeline window scans 72h=639 · 168h=842 files, so the old 200/400 caps thrashed). A separate timeline memo (`3342379`) proved redundant once the `agents.py` cache itself grew, and was removed (`ae4cd05`) ⇒ `_AGENT_LAST`/`_AGENT_FIN`/`_AGENT_TOOLS` (sidereus/agents.py:20,199,200) are **keyed by file path only**, value `(mtime,size,val)` replaced in place, hits move to the end of an `OrderedDict`, oldest popped past `AGENT_CACHE_MAX=4000` (agents.py:26) (`_lru_get`/`_lru_put`, agents.py:29,41). ⚠Never empty a new agent cache with `dict.clear()` — active agents drop out behind a cold cache.
- ★**Replying without reading the POST body stalled the next request** (2026-09-25; leftover bytes on the keep-alive socket were parsed as the next request). ⇒ When the length cannot be read (oversize · negative · non-numeric) or the request is refused, always close the connection via `_body_unread()` (chat_server.py:197) · `Transfer-Encoding` is always 411 (no chunk decoder; even with Content-Length, TE wins under RFC 9112 so the length cannot be trusted, chat_server.py:210). ⚠Every new POST route follows this path, read or not, or keep-alive breaks.
- ★**An empty `/api/bg/dismiss` body cleared every cwd** (2026-09-25; `{}` · `{"tid":""}` read as «no cwd · no tid» = delete all) ⇒ one of `cwd`/`tid` must be a non-blank string (sidereus/routes_post.py:139). The UI always sends one — anything outside that contract is 400.
- ★**`awake:{on,n}` (`/api/state`) removed** (2026-09-25 `bf1d256`). A dead field nobody read since `awakeRow` was deleted 09-23 ⇒ removed from `sidereus/state.py` · `00-core.js` `AWAKE` · the `95-poll.js` assignment. The `caffeinate` loop (`sidereus/awake.py` `_awake_loop`) still runs — **keep-awake itself is alive**, only its on-screen display is gone. ⚠To show keep-awake state again, add a new key that reads `_awake` (do not revive this field — the reason it sat dead would repeat).
- ★**Guard refusals (Host · Origin 403) only via `_refuse`** (2026-09-25). Sent without Content-Length and without reading the body, they hung keep-alive connections (curl >120s) ⇒ `_send` with length + `close_connection`. ⚠Never hand-write `send_response`. Test `tests/test_guard_close.py`.
- ★**`/api/state` was sent as 3.1MB plain text** (2026-09-22).
  Cause: no compression. JSON repeats keys, so gzip works especially well.
  ⇒ `_state_body()` returns `(body, gzbox)` and `_send()` compresses **only after** checking `Accept-Encoding` (lazy — no CPU for clients that do not accept it). `GZIP_MIN=4096`. ★Full 3,130,720 ⇒ **984,423B (31.4%)** · incremental 261,628 ⇒ **56,643B (21.7%)**.
  ⚠`Content-Length` is the **compressed length** — the raw length truncates the response. ⚠Keep `Vary: Accept-Encoding` (otherwise intermediate caches serve gzip to plain clients). ⚠Short responses like `_send(404,...)` stay plain.
- ★**«full history» pulled 3.1MB at once — the whole state for 300 alarms** (2026-09-22).
  Cause: `#aall` called `/api/state?cards=300`. Only cards were needed, but sessions, messages and acks came along.
  ⇒ New `/api/cards?n=300` **reuses the existing builder `cards(limit)` as-is** (the same function `state()` calls, so formats cannot diverge). Cap `max(1, min(n, 300))`. ★**3,186,536 ⇒ 65,702B (48× · −97.9%)** · 300-row screen render confirmed.
  ⚠The poll's (`:15577`) `alarmAll?'&cards=300'` was **left as-is** — incremental, +55KB/poll, only while the panel is open, and gzip cuts it to 1/4. ⚠`/api/cards` is not gzipped (65KB).
- ★**98% of the incremental response was `acks` — drop unused fields in `ack_map()`** (2026-09-22).
  Cause: `acks` has no `since` filter, so all 761 ride every poll (2.5 s). ★Measured **846,069B (98%)** of an 863,507B increment, `note` alone 711,810B — about 1.2GB per tab per hour.
  ⇒ Drop `at` (unused by the UI) and cut `note` to 60 chars (JS already does `slice(0,60)`, so **display is unchanged**). ★**846,069 ⇒ 244,374B (−71.1%)** · whole increment 863,507 ⇒ 260,991B.
  ⚠If the UI starts using `at` or the full `note`, revert `ack_map()`. ⚠`acks` is still **not incremental** — 244KB resent every 2.5 s (making it incremental is separate).
- ★**The 38 s cold start was not slow assembly but «failures not cached»** (2026-09-22).
  Cause: `agent_view` (`:947`) cached only when `is not None`, so **failures (None) were never cached**, and 6 places in one `state()` each timed out at 6 s (36 s). `_ps_snap` too, 3 places × 4 s. ★`viewer.err` had 49+47 `TimeoutExpired`. Measured in isolation, `state()` itself is 0.6 s.
  ⇒ Cache failures exactly as the twins `live_cwds` (`:1102`) · `tool_busy` (`:1374`) already did — `AGENTS_FAIL_TTL=15` · `PS_SNAP_FAIL_TTL=4.0`. ★On repeated failure, forks **6 ⇒ 1** · **3 ⇒ 1**.
  ⚠**Never make the failure TTL equal to the success TTL** — «unknown» would stick that long. ⚠`_ps_snap`'s contract is to raise (3 callers rely on `except` fallbacks) — re-raise the same exception, just skip the fork.
- ★**One full process scan per poll — `_ps_snap()`** (2026-09-21 · 70 cumulative `TimeoutExpired` in `viewer.err`,
  load 70.3 on the latest warning). Four collectors each ran `ps`, **up to 5 per poll**, and under load spikes the
  4 s-capped ones piled up and screen values went stale. Measured forced single poll: `ps` 5→**2** (total 7→4).
  - ⚠Fields are the union `pid,ppid,command`. `comm` values contain spaces (`…/Google Chrome Helper`) and cannot share
    a line ⇒ the comm check only `live_cwds` used now uses argv[0] (full 626 lines, **0 difference**).
  - ⚠Not merged: `ps -Ewwo` (`-E` env vars — only for a few watches) · the 2 `lsof` calls (different pid sets).
  - Fallbacks (previous value N s) and `warn_once` text are unchanged. The snapshot **raises on failure** —
    caps differ per collector (30/60/30 s), so it does not decide for them.
- **`_lock` actually guarded only `rooms.json`** (measured 2026-09-07). `state()` read all 18 screen pieces inside the lock,
  but only `state()` and invite handling took `_lock`, and the real shared state was just
  `rooms.json` (+ its paired `bus.jsonl` invite posts). **`sessions()` was already called lock-free in 6 places**
  — «the lock guards `sessions()` globals» never held.
  ⇒ Slow work moves to locals outside the lock; the lock covers only «the set overlapping invites» (presence · acks · messages · cursors · rooms · profiles,
    0.022 s total). Write-path wait 0.880 s → 0.000 s.
  ⚠**Some things were protected by accident** — polls queueing serialised the `_prev_state` read-modify-write and `_sid_proj` cleanup.
    Narrowing the lock removes that (a dedicated `_note_lock` was added). And `sum(d.values())` in the `bgskip` sum was a
    `RuntimeError: dictionary changed size during iteration` waiting to happen, hidden by `_lock` — **narrowing a lock exposes hidden races. Find them before narrowing.**
  ⚠Honest cost: the 16-thread concurrent poll average **worsens** 0.317 s → 0.364–0.501 s, because polls really do hit the disk
    concurrently. The goal was freeing the write path, and that was achieved.
- ★**Harness tab waited 0.8-1.8 s right after each 30 s cache expiry** (2026-10-12, `sidereus/toolidx.py` `tool_uses`): the request thread ran `_refresh` (stat 3,547 files) + re-merged ~764k events under `_TI_LOCK` — 0.34 s alone, 0.8-1.8 s live (GIL contention).
  ⇒ stale-while-revalidate: an expired complete result is returned at once and one `_revalidate` thread (guard `_TI_STATE["rv"]`, set under the lock) refreshes every expired window with one merge. First call (no result), `pending` and age > `TI_STALE_MAX_S` (10 × TTL, so a failing revalidate surfaces) stay synchronous.
  ⚠Never move the refresh back onto the request path; never spawn per request — concurrent polls would each re-merge.
  ★Same request's uncached `mcp_status` (0.068 s alone) then waited 0.35 s on `_TI_LOCK` behind `_revalidate` ⇒ `_TI_MCP` result cache + `acquire(False)` when one exists (busy → cached); ⚠never block when a result exists.
- ★**Harness tab showed «Loading…» for seconds after a restart** (2026-10-13, `sidereus/toolidx.py`, `sidereus/pipeline.py` `borrowed`): the first /api/harness paid the cold toolidx load (63 MB `_load_disk` 0.50 s + 32 MB `_refresh` slice + `_merged`/`_count` 0.37 s, all under `_TI_LOCK`, 1.07 s) and `borrowed(proj, None)` ran `allowed_projects()` with no runs (0.74 s cold). ★Cold 2.97 s, second call 1.19 s.
  ⇒ `toolidx.warm()` startup thread (`toolidx_warm`) finishes the scan and fills `_TI_RES[30]`/`_TI_MCP[30]`; `borrowed` returns `[]` before `allowed_projects()` when `runs` is empty.
  ⚠Do not claim `toolidx_warm` in `features/harness.json` — /api/tools (core) reads toolidx too.
- ★**Viewer held 423-945 MB, mostly the tool index** (2026-10-22, #17, `sidereus/toolidx.py`): `_TI_FILES` kept every event as `{id str: (key, ts)}` — 5,335 files / 1.53M events = 294 MB traced (162 MB id strings), ~48k events/day; `_merged()` copied all of them on each recompute (+88 MB).
  ⇒ Cache v5: per-file parallel arrays (64-bit blake2b id hash · ts · key index); only ids seen in 2+ files go through `_merged()`; events past `TI_MAX_DAYS` dropped at scan/load and trimmed from active files. ★Index 328 → 55 MB, recompute peak 454 → 56 MB, maxrss 539 → 166 MB, cold scan 711 → 464 MB, cache 96 → 47 MB.
  ⚠A copy with ts 0 used to win the earliest-copy dedup and hide the real timestamped copy — across files and inside one file (`api-request-blob` lines carry the tool_use with no timestamp). ★Old vs new on the same scan: 47 more events (tool:Bash +45, SubagentHandback +2), 0 fewer. Never let a ts-0 copy decide the winner.
  ⚠The first start after upgrading discards the v4 cache: one cold rescan (~50 s «Loading», peak ~464 MB, mostly the 32 MB read chunks).
  ★#26 (2026-10-25): `_reindex` sorted every id as one Python list (~1.5M ints) at boot and each revalidate — the post-boot RSS spike to ~230-240 MB. ⇒ sort `TI_SORT_CHUNK` runs and `heapq.merge` into one array; ★synthetic 1.5M ids: peak 77 → 25 MB traced, 1.19 → 1.30 s. ⚠Do not go back to `sorted(chain(...))`.
  ★#26 (2026-10-25): the boot save joined every cache row into one str and `.encode`d it (boot RSS peak 317-442 MB at t≈3.6 s, save 265 MB traced). ⇒ `_snapshot` returns lines, `toolidx_fmt._write_rows` streams them to a tmp + `os.replace`; ★synthetic 200k rows / 64 MB: save peak 204 → 77 MB traced, same bytes. ⚠Do not rebuild the whole file as one string/bytes.
- ★**Today-by-hour scan re-read every transcript touched today, every 30 s** (2026-10-13, `sidereus/burn_scan.py` `_today_fetch`): 182 files / 220 MB per pass, one pass +379 MB peak, viewer maxrss 127 → 566 MB.
  ⇒ Incremental `_today_files`: per file inode + byte offset (kept at the last newline) + first-seen responses; a pass reads only appended bytes in 4 MB chunks, `b'"usage"'` filtered before decode. ★tracemalloc, 53 MB fixture: 152 MB → 14 MB first pass, 0.7 MB unchanged pass. Tests `tests/test_today_incremental.py`.
  ⚠Responses are deduplicated across files at aggregation (glob order), not per pass — a global seen-set kept across passes would undercount after a file reset. ⚠Reset only on inode change or shrink; the day rollover clears the cache.
- ★**`claude agents --json` spawned every 11-18 s** (2026-10-13; 8 in 2 min, 120-157 MB RSS per child, one per account) — an 8 s TTL on the 2.5 s state poll.
  ⇒ `sidereus/live_probe.py` `_av_registry_sig`: re-run only when the CLI's registry `<config dir>/sessions/<pid>.json` changes in (pid · sessionId · cwd · pid alive), else at `AGENTS_MAX_AGE` 60 s. Estimate ~7.5/min per account → ~1/min + session events. Tests `tests/test_live_probe.py` `AgentViewSignatureTest`.
  ⚠Never put `status`/`updatedAt` in the signature (they change every turn). ⚠No registry dir ⇒ plain `AGENTS_TTL`; the failure backoff (`AGENTS_FAIL_TTL`) still wins over a signature change.
  ⚠Off macOS (no `ps` snapshot) this listing is the only liveness source (`live.py` `_live_official_only`), so the 120-157 MB per-account spike lands on Windows/Linux every run — watch for low-memory or many-account reports before widening the cadence.
- **`X-Build-Time` header** (`chat_server.py` `_send`, value `sidereus/page.py` `BUILD_TIME` = `<UTC assembly time> <PAGE_BUILD>`): identifies the running page for the push gate. ⚠Set once at import — the value changes only on a restart, not on a `web/` edit.
- **Web app manifest + icons** (`sidereus/page.py` `MANIFEST`/`ICON_SVG`/`ICON_PNG`, `pwa_reply`, served by `routes_get._g_page`): `/manifest.webmanifest`, `/icon.svg`, `/icon-192.png`, `/icon-512.png` are same-origin, so `PAGE_CSP` stays unchanged (manifest-src falls back to `default-src 'self'`).
  ⚠The PNGs are generated — edit `web/icon.svg`, then run `scripts/make_icons.py` (same shapes in code). ⚠`.gitignore` has `*.png`: the icons need an exception or a clone serves 404 (a missing file never stops the viewer).
  ⚠The tab favicon stays the data: URI in `index.html` — `15-alarms.js` rebuilds it for the unread dot.
