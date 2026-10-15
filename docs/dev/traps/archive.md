# Traps — Archive: removed features

Traps whose code no longer exists (checked by grep, 2026-10-15). Kept for the ★ evidence; do not apply them to current code. Conventions: [TRAPS.md](../TRAPS.md).

## From «Timeline»

- ★**The server sent `awake` but the screen never drew it** (2026-09-22).
  Cause: `:8426` adds `{"on","n"}` every poll, but no JS read the key ⇒ `caffeinate` was really running and **the Mac stayed awake with no visible reason**.
  ⇒ `awakeRow()` draws one `.qrow` line under the sidebar quota stack (5h·7d·credits). ★The two mean different things — `on` is **whether the caffeinate child is alive** (`_awake_busy`:5906), `n` is **the number of `tool`/`think` sessions** (waiting-for-input not counted). `AWAKE_GRACE_S` (180 s) leaves stretches with `n=0`·`on=true`, so the text splits («N sessions working» / «right after the last work · releasing soon»).
  ⚠When `on` is false **draw nothing** (an always-on line soon becomes invisible). ⚠**Do not draw it anywhere else as well** (2026-09-21, duplicate removed). ⚠No new CSS — reuses `.qrow`/`.quota .qamt`, so no descendant-selector trap.

## From «Sessions: state, subagents, external CLIs»

- ~~An external CLI's `blocked` has an age cap `EXT_BLOCK_TTL_S`~~ (2026-09-23) — removed 2026-10-14, see «A pending feedback request never leaves attention by age».

## From «Mailbox and chat»

- ★**Thread line pruning** (2026-09-28; measured 56 DM threads · 46 quiet for 7+ days) — the chat thread line shows only threads with a post within `THREAD_QUIET_D` (7) days, newest first. The rest fold under «+N» → «quiet threads (7d↑) N» (`THQUIET`, 92). ⚠Nothing is written — a bulk [done] would notify every receiving session, so it was not added (per-thread «close» and idle-thread «close all» remain).
  - ★Auto-archive — threads finished more than `THREAD_DONE_D` (3) days ago or quiet more than `THREAD_ARCH_D` (30) days leave the list; only an «archived N» count at the end of «+N» (`THARCH`). ⚠Hidden, not deleted — sent posts stay in the mailbox (AGENTS rule 7) · sessions read the same bus · posts remain visible in «All» and search. Actually pruning the bus is an owner decision.

## From «UI kit, CSS, layout, header, i18n»

- ★**Collapsing is the whole right «column», not card by card** (2026-09-22). Per-card collapse (`#fbar` · `.f-*`) was **removed** the same day.
  - ⇒ One `body.lsoff` removes `.lside` and shrinks the `.wrap` · `#composein` grids together to `360px 1fr`. **One** button `#lstog` (fixed at the right edge · text only `⟩ collapse`↔`⟨ expand`). ⚠Kept outside `.wrap` — inside, it vanishes on collapse. State in `localStorage.sidereusLsOff`.
  - ⇒ Replaced by the drawer on 09-24 — `body.lsoff` · `#lstog` no longer exist; `sidereusLsOff` is only read by a one-time migration in `web/js/41-sesdrawer.js` (to be removed after 2026-10-24) (see «Right session column → top-right drawer» in [ui.md](ui.md)).
  - ⚠Never fix only one grid — the input spreads into the session area (precedent in the `#composein` comment).
