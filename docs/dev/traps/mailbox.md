# Traps — Mailbox and chat

Conventions (entry shape, `★` `⚠` `⇒`, `§N`, `:NNNN`): [TRAPS.md](../TRAPS.md). Newest first within an area; new traps go at the top of their area.

## Mailbox and chat

- **Room hashtags live in `room-tags.json`, owned by Sidereus** (`sidereus/room_tags.py`, `POST /api/rooms/tags`). Cause: `rooms.json` belongs to the MCP server, which rewrites it whole (read-modify-write) and would drop or clash with keys it does not know.
  - ⇒ Tags go in their own file (tmp + `os.replace`, previous copy in `.bak`); `rooms.json` is only read to check the room exists.
  - ⚠Do not add a `tags` field to `rooms.json`.
- **#feed is shared by every tab, so its `setHtml` cache (`_sh`) goes stale** (room cards, 92 `rcPaint`). Cause: `full()` and other tabs write `feed.innerHTML` directly without clearing `feed._sh`, so a later `setHtml(feed, h)` with the same `h` is skipped and the room list stays blank.
  - ⇒ `rcPaint` skips only when its own `feed._rcH` matches and `:scope > .rcw` exists; it and `full()` clear `feed._sh` after writing.
  - ⚠Do not use `setHtml(feed, …)` for chat. `toBottom` goes to the top while `.rcw` is showing (the room list reads top-down).
- **Chat has no threads** (rooms + hashtags only). The bus still carries `thread` fields (MCP, pipeline DMs, invites); the chat UI ignores them. ⚠Saved views / ui-keep with an old `byThread` key must keep loading (key ignored, tested).
- **Mailbox watch default (`mailbox_watch` pref, 90d) is read raw by `hooks/invite_notice.py`.** Cause: hooks must not import `sidereus/*`. ⇒ the hook reads `config.local.json` itself; longest project-path prefix wins, else `mode`; missing/broken = on.
  - ⚠Both sides resolve paths the same way (prefix per path segment) — change one, change the other.
  - ⚠90d mounts after `paintCfg` rebuilds `#cfgbox` and observes direct children only (subtree would re-trigger on its own insert).
- ★**Reply thread inheritance and name merging happen on the server** (`bus.say_thread`, `/api/say`). Cause: a reply sent without `thread` fell out of the parent thread, and `Foo  bar` · `foo bar` became different thread keys.
  - ⇒ With only `replyTo`, use the parent post's `thread`; if it equals an **open** thread in the same room after trim, whitespace collapse and case-folding, use that name as-is. An explicit new name is kept.
  - ⚠Do not inherit or normalise separately in the UI — old cached pages and other clients would make different keys. Never merge into closed threads or other rooms.
  - Bulk «close» = `POST /api/thread/close {threads:[…]}` (≤50; one bad name rejects all; closed/missing ones are `skipped`). Tests `tests/test_thread_rules.py` · `test_thread_close.py`.
- ★**With a single room, absorption covers only public posts with no recipient** (2026-09-24; test mail should have gone to a separate room). DMs (`m.to` set) were absorbed too, so test mail appeared in a working room ⇒ DMs get the «no room» pill (shown even with one room when DMs exist).
  - ⚠The verdict is one `inPlace`/`absorbed` (10-feed.js) — never re-implement it in `visible` · `buildTabs` · `buildPeople` · `buildRooms`.
- ★**Narrow chat: participant cards covered the conversation and the input was 88px** (2026-09-24 · 1000px). Cause: 65's default `#composein` grid (id selector, later file) beat 50/60's ≤1320/≤1000 rules, so the input stayed `360px 1fr 500px`. Gap was also 14px ≠ `.wrap` 8px (6px off at 1400px).
  - ⇒ All narrow grids live in one place, `45-saver-quota.css`, as `html[data-ui=next] body…` covering `.wrap` and `#composein` together: unpinned 1101–1320 `340px 1fr` · ≤1100 one column · pinned 761–1320 `1fr 360px` · ≤760 one column. In one column participants collapse to a title line, expanded by clicking it (`.popen`, 50-people.js).
  - ⚠`#composein` gap = `.wrap` gap. The old `#composein` media rules in 50/60 do not apply — do not fix things there. Measured: at 900 · 1000 · 1200 · 1320 · 1400 (pinned/unpinned) input left · width = `#feed`, horizontal scroll 0.
- ★**Three mailbox signals — «load everything», «auto ack» and «heartbeat» each lied** (2026-09-23).
  - `acks`, once sent in full, is cut to **the last 7 days** (`ACK_KEEP_S`) — 251,128B → 12,590B (−95%). The file (`acks.jsonl`) is unchanged; only the response is cut.
  - **The watcher does not write acks** (`monitor_stream._flush`) — `stdout` output is **delivery**, not confirmation. With the session dead and only the watcher alive, «✔ confirmed» showed though nobody read it (all 1,485 such records came from there). Remaining signals: `delivered` and replies.
  - Participant dots never show ● from heartbeats alone — `presence()` combines `active` (MCP calls within `ACT_STALE_S`, 1 hour) with send times (measured: heartbeat refreshed for 11 days 22 hours · no activity for 21 hours, yet ●).
  - ⚠Never render bubbles in the cut range as «unread» — posts older than the response's `acksSince` are «past the ack retention period». Longer retention grows the response accordingly (30 days = 124,401B).
  - ⚠**Never go back to instructing sessions to call `mailbox_ack`** — on 2026-09-04, 541 ack-only turns burned ≈60M tokens. Auto ack was its replacement and is now removed too.
  - ⚠Without auto ack, the `unacked()` nag fires again **for every delivered post** (`NAG_MAX_TIMES` cap 2 · measured 7–9 posts per 24h = 14–18 wake-ups) — and the nag text «posts whose full text you have not received» no longer fits. Separate follow-up.
  - ⚠Never hard-code ids — the fix is structural, not tied to a specific participant; all rules are generic and age-based.
- ★**«N skipped · 0 delivered for 83 h» was a false alarm — identity was fine** (2026-09-22 · `monitor_stream.py`).
  Cause: the warning fired «if any post for others exists», so a quiet identity barks forever. Measured for Sidereus: ME=SELF=Sidereus · registered; all 8 new posts in that span were in **a room it had not joined, `room-A`**, and 1:1 posts to Sidereus were 0 in 972 bus lines — 0 deliveries was correct.
  ⇒ `_suspect(r, myrooms)` excludes «posts that belong to someone» — evidence is only ⓐposts in **my room** that were filtered (SELF overreach) ⓑ1:1 posts with no owner in the registry (`identity.json` · `profiles.json`). Typo identities are caught separately at startup as «unregistered identity». ★Control: reproducing SELF overreach still barks on all 8; Sidereus 8→0.
  ⚠Do not touch `mine()` — only «whether to warn» changed. Joining the room to silence it means receiving others' conversations, breaking rule 1.
- ★**A tab left open for days grew the feed without bound — `shownN` had no cap** (2026-09-22).
  Cause: `shownN` only grew in `append()` per new post and never shrank (reset only on filter change). ★969-row repro: **DOM 13,568 nodes · 969 `innerHTML` writes per poll · `full()` 59.2ms · event-loop lag max 273ms · heap 15→31MB in 20 s**.
  ⇒ ①`shownN` stops at `SHOW_MAX = 300` and `trimFeed()` removes overflow rows **from the DOM only** ②`refreshReceipts()` remembers output strings in `box.__rcpt` and writes **only changed rows**. ★**300 rows / 4,204 nodes · writes 300 on first poll then 0 · `full()` 32.5ms**.
  ⚠**Never trim `MSGS`** — idle threads, verdict/correction tabs and read counts use all of it. Only drawing is trimmed. ⚠Never lower a `shownN` raised above the cap by «More» (the reading position jumps). ⚠Changing the comparison key away from the output string means read marks never update.
- ★★**When the evidence source is dead, no fix works — mailbox watches are now judged by process** (2026-09-07, three failures the same day).
  Watches (Monitor) are normally quiet, so they were **not expired by time** (correct), and since exit notices sometimes never come
  (in one session `beu8ozhfb`, killed by `pkill` (last heartbeat 09-04 06:02), vanished without a notice and
  `bo373wcua` (06:17) appeared — the same file mixes `stopped` · `script failed (exit 143)` · no notice),
  a fix was added where **the successor pushes out the old one**. That did not work either:
  all **7 watches the screen showed had been silent for 70–73 hours**, while the real watch processes numbered **3**.
  Since watch.sh was merged, harness Monitor events **never arrive** ⇒ **live and dead are equally quiet.**
  On heartbeats, time expiry, relative comparison and label push-out are all powerless (all three fixes stood on them).
  ⇒ **Mailbox watches are built from processes by `mailbox_watches()`** (one full `ps` + one env lookup per watch pid · 5 s cache).
  - ⚠An earlier note here said «resist counting by process — pid→session cannot be mapped (it does not hold the transcript open)».
    **That was wrong.** Only **linking via lsof** fails (the watch process really does not hold the
    transcript open); **the parent chain works** — `watch.sh` is a child of the session shell (Bash tool), so
    two `ppid` hops reach `claude`. Measured:
    `monitor_stream 55298 ← zsh 55295 ← claude 84637(--resume 452cb0e4)` ·
    `80771 ← 80767 ← claude 64859(bare claude · cwd=~/repo-A)` ·
    `86650 ← 86647 ← claude 57914(--resume 10d426f5 but the real file is 2ab0b0ad)`.
    claude pid → transcript goes through the existing `_sid_claim_stale()`/`_sid_transcript()` (stale `--resume` label check) and
    the **newest `.jsonl`** in the cwd slug. cwd is the by-product `live_cwds()` leaves from its one lsof (`_live_pid_cwd`).
    Identity is read from env var **`MAILBOX_ME`** (`ps -Ewwo pid=,etime=,command=` gives uptime in the same call).
  - ⚠Never count by **substring** `monitor_stream` — the moment some shell runs `pgrep -f monitor_stream`,
    that `zsh -c …` is caught as a watch and **a nonexistent watch** shows on that session row (actually hit during this fix).
    Only argv[0] python with an argument ending in `monitor_stream.py` is a watch (`_is_watch_cmd`).
  - Only heartbeat entries **that are mailbox watches** are dropped (`_MBOX_LAB_RE`: `mailbox` · the Korean word for mailbox · `watch.sh`).
    Other harness Monitors **keep current behaviour** (no expiry · push-out kept) — this file's principle of not
    concluding death from silence still applies there.
  - The meaning of the number changed too: a `src=proc` entry's value is **real uptime**, so «N min running» is accurate, and
    the 30-min `late` colour and the "may have missed the completion notice" tooltip are **not attached** (a long-running watch is normal).
    Old heartbeat entries become `src=beat` and keep their labels — the screen draws by that marker.
  - ★The async Stop-hook waiter (`hooks/mailbox_wake.py`) is also a watch: a `.wake/<sid>.lock` with mtime < 15 s adds one `src=proc` row without `min` (`sessions._wake_rows`). ⚠Never `os.kill` the pid in it — that terminates the process on Windows.
  - A `ps` failure **never drops to 0**: success reused for 5 s · on failure the previous value for up to 60 s ·
    longer failures fall back to the heartbeat list and are recorded via `warn_once` (→ `health.warns`).
- ★**Room hide is an overlay, never a delete** (2026-10-05). rooms.json is the MCP's record and bus.jsonl is append-only evidence; trimming either loses history other sessions read.
  ⇒ `sidereus/room_admin.py` keeps `{hidden, pending}` in `room-admin.json` (+ `.bak` before each write); the screen filters by it. Room create without ids is `pending` only.
  ⚠Never rewrite bus.jsonl lines or drop rooms from rooms.json to «hide» a room (`test_room_admin.test_hide_keeps_bus`).
- ★**Chat compose names its target; `/api/say` never picks one** (2026-10-05). The client sent `room` only from a replied-to post, and the server filled the rest with `ROOM_DEFAULT`, so a DM reply was posted publicly in the default room and a post typed in room X landed in the default room.
  ⇒ `10-feed.js:chatTarget` = parent's room / DM peer, else the open room, else (in «Outside rooms») `cfg.defaultRoom` sent by name and labelled «(default room)»; `#cto` shows it above the box. `_p_say` takes exactly one of `room`/`to` (`to` checked by `bus.dm_target_error`, same as `/api/dm`), else 400.
  ⚠Re-adding a default-room fallback brings the misrouting back (`test_routes_post_say_dm.test_no_target_refused_never_default_room`).
  ⚠«Outside rooms» lists only room-less posts (`inPlace`), so a default-room post vanished after Enter ⇒ `send()` opens that room (`rcOpen`) on success when `g.dflt`.
- ★**`/api/say` room = create's name rules + must exist** (2026-10-05, sandbox: `dm`, `a\nb` and a typo each got 200 and a room card). ⇒ `room_admin.say_room`: `check_name`, then rooms.json · bus · pending, or `ROOM_DEFAULT` (the «Outside rooms» target, which may not exist yet). ⚠Dropping the default-room exception breaks «Outside rooms» on a fresh install (`test_room_name_rules_and_existence`).
- ★**The page's own posts are `mine` only because `state().mine` adds `VIEWER_ME`** (2026-10-05, sandbox: work-log DM trail empty). `MINE` is config `self.ids`; say/dm/invite write `from=VIEWER_ME`. ⇒ `sidereus/state.py` appends it; invites use `VIEWER_ME` too (was the literal `viewer`; `idSrc` still says «viewer»). ⚠Removing it empties the queued→delivered→read→replied trail and the «not read by the other side»/«not confirmed» filters (both mean *my sent* posts). Counts of what is new *to me* (`chatNew`, bell = cards) exclude my own posts explicitly (`test_chat_new_mine_js`).
- **A default viewer id follows the page language, per request** (2026-10-06). The UI language lives only in the browser, so `postJSON` sends `X-Sidereus-Lang`. While viewer_me is unset or a default spelling, `config.viewer_me_for` writes `from=user` (en) or the Korean word for «user» (ko). A post sent without the header (curl, a fetch that skips postJSON) gets the Korean form.
  ⇒ `config.viewer_ids` makes both spellings the viewer: `state().mine` + `cfg.viewerIds` (chatNew, chatTarget) and the self-check in `bus.dm_target_error`.
  ⚠Matching on `VIEWER_ME` alone loses a user's earlier posts once they switch language (`tests/test_viewer_me_lang.py`).
  ⚠While viewer_me is a default, the page cannot DM a session logged in as «user» or its Korean form (the self check runs first). Give that session another id.
- ★**Invite confirm shows the exact DM** (2026-10-05). The confirm showed only «invite DM to N people»; the body was built on send. ⇒ `{dry:true}` on `/api/room/invite`·`/api/rooms/create` returns `invite_text()` without writing; confirm sends it back as `expect`, and a mismatch (room changed) is refused (`stale`) and re-previewed. ⚠Build the body only in `invite_text` (`test_dry_preview_is_the_sent_body`).
- **A Stop block can be overridden, so the cursor must not move on block** (`hooks/mailbox_stop.py`). Cause: another Stop hook's `continue:false` (e.g. oh-my-claudecode) wins over `decision:block`; the reason never reaches the model, and a cursor saved before the print marked that mail as surfaced — lost.
  - ⇒ With `stop_hook_active` in the input, a block stages `pending`; the next Stop promotes it on `true`, drops it on `false` (re-block). `mailbox_wake` fires only above max(confirmed, pending) and clears it.
  - ⚠Do not write `hooked` receipts or move `last_t`/`relay_t` at block time. ⚠Without the key keep commit-at-once (Gemini and other CLIs never send a second phase).
  - Tests: `test_mailbox_stop.test_overridden_block_blocks_same_set_again` · `test_mailbox_wake.test_pending_only_does_not_wake`.

## Mail watch: waking without Monitor (`hooks/mailbox_wake.py`)

- Cause: Monitor is enabled by a server feature switch (`tengu_amber_sentinel`). Under a `DISABLE_TELEMETRY` policy the switch never arrives, so it is off.
- ⇒ Stop hook with `asyncRewake: true` — it waits in the background, and exit 2 wakes the idle session (2.1.291 measured: woke after 60 s).
- ⚠exit 2 only for new mail or updates. The woken turn ends with Stop again, re-arming every turn — an unconditional exit 2 wakes forever.
- ⚠One per session: judged by lock-file mtime (no `os.kill` — on Windows it terminates). Cursor shared with `mailbox_stop`.
- ★**`claude -p` hung after a relay block** (2026-10-11, 2.1.296). Cause: headless runs wait for every Stop hook, `asyncRewake` included, before acting on `decision:block` — the waiter held the run to the 240 s test timeout, `pending` never promoted.
  - ⇒ `headless()`: `CLAUDE_CODE_ENTRYPOINT` starting `sdk` (measured `sdk-cli` under `-p`, `cli` interactive) exits 0 before reading stdin. Live re-run: relay answered in 10 s, cursor promoted.
  - ⚠SDK-hosted long-lived sessions (`sdk-ts`/`sdk-py`) also get no idle wake — their mail arrives at the next Stop via `mailbox_stop`.
  - ⚠Interactive (`cli`) must keep waiting — do not widen the check beyond `sdk*`. Test `test_mailbox_wake.test_headless_entrypoint_exits_without_reading`.
- ★**Codex sessions showed «Not logged into the mailbox»** (2026-10-20) although they received mail. Cause: `ext-hooks/gemini_mailbox_mcp.sh codex` exports `MAILBOX_ME=<basename>-codex`; the mailbox server treats it as a declared id (source env) and the Codex Stop hook reads it, but the viewer accepted only identity.json values.
  - ⇒ `ext.codex_env_dedupe` each poll: `<…>-codex` id (charset-checked, not a Claude identity value) held by exactly one live Codex row that has a reader — hook-fed (the Codex Stop hook checks that inbox at turn end) or `read-<id>.cursor` exists ⇒ src «env», published to `bus._codex_ok`; `dm_target_error` accepts only published ids. JS `mboxIn` treats env as logged in on cx rows only.
  - ⚠A rollout-only row (no hooks) needs the cursor; nothing else counts as a reader. Never trust the client's `mboxSrc`; before the first poll everything is refused. Tests `tests/test_ext_mbox_codex.py`.
  - ⚠A reader proves someone reads the id, not which row: an id held by two live Codex rows (two folders named `app`) is refused. Room invites accept the same published Codex launcher ids as DMs (`_room_invite` via `bus.codex_env_ok`); folder guesses stay refused.
- ★**Codex idle wake = the sync Stop hook waits** (2026-10-20, 0.163.0: no timeout cap, 3600 s accepted; block continues the turn; empty exit 0 = no model call). Cause: worker mode woke Codex with a `mailbox_wait` round per hour, ~33k input tokens each.
  - ⇒ `gemini_mail_stop.py --platform codex --wait` waits through `hooks/mail_wait.wait` (bus.jsonl stat every 2 s, `check` only on change); worker mode is Gemini-only. `WAKE` in `hooks/mail_wait.py` names each CLI's method.
  - ⚠Typed input queues until Esc or the wait ends; after 59 min the turn ends and waiting resumes only at the next prompt.
  - ⚠`decide()` gives up after `BUDGET_S` from `T0`; the wait resets `T0` per check or it never fires. `decide()` keeps other state fields (`wake_n` runaway guard, cap `SIDEREUS_MAIL_WAIT_MAX`).
  - ⚠`codex exec` must not wait (a script hangs up to 59 min). The Stop input has no exec field, so `interactive()` reads the rollout's session_meta (originator `codex_exec` / source `exec`); unreadable = no wait. Test `test_no_wait_under_codex_exec`.
