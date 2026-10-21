# Traps — UI kit, CSS, layout, header, i18n

Conventions (entry shape, `★` `⚠` `⇒`, `§N`, `:NNNN`): [TRAPS.md](../TRAPS.md). Newest first within an area; new traps go at the top of their area.

## UI kit, CSS, layout, header, i18n

- ⚠**Default tab is Pipelines, fallback stays Timeline.** Nothing saved / invalid opens `pipe` (05-i18n.js `mainView`), but `pipe` is feature-gated, so `time` remains the unhideable lock (`mpTabs`), the `setMainView`/`buildMv` fallback and the boot choice when `mbTabsOff` lists `pipe`. ⚠Do not make `pipe` the fallback or the lock — a feature-off pipe would open a 404 tab.
- ⚠**`.open` in 60-sessions.css was an unscoped pill rule** (2026-10-13, fixed). It matched any element with an `open` class: `#rail.open` got its border (1px shift) and `#alarm.open` painted alarm text gold. ⇒ Scoped to `span.open` (the «Awaiting reply» pill, 10-feed.js); the 93b-rail.css reset is gone. ⚠Never style a bare state class (`.open`, `.on`) globally — prefix it with its element/component.
- **Font sizes are rewritten in place once, last** (`fsApply`, 00-core.js). Every px `font-size` becomes `calc(max(12, ladder)px * var(--fs,1))`; px `line-height` below the new size becomes `max(Npx, 1.2em)`.
  - ⇒ call it only after `#nxcss`/`#nxlt` are appended; size math goes through `fsSize`.
  - ⚠Do not run the ladder or `fsApply` again: rules carry `calc()` afterwards and neither parses it (sizes stay unscaled).
  - ⚠Fixed-height text boxes clip at `--fs` 1.25: size them with `max(Npx, Nem)` or `calc(Npx * var(--fs,1))`, never smaller text. Below-12px exceptions go in `FS_KEEP` with a reason.
- ★**A plain `.x.on` can lose to its own base rule's next-UI twin** (2026-10-06: `.plovr.on` border computed transparent). 00-core.js re-emits `.x{border-color…}` as `html[data-ui=next] .x` (0,2,1), which outranks `.x.on` (0,2,0); the `.on` rule itself was not twinned.
  - ⇒ write the state selector as `.x.on,html[data-ui] .x.on` — higher weight, and the rewriter skips selectors containing `data-ui`.
- ★**The 00-core next-UI twin copies a base rule's `background` as `background-color:transparent`** and wipes a `:checked`/state fill (★10-06 `.mdtask` checked fill went to 1.14:1).
  - ⇒ keep `background` out of the base rule and put `html[data-ui]` on the state selector.
  - ⚠Check the computed style on the rendered page in both themes; the source CSS looks correct.
- **UI prefs are server-backed (`UIS`, app-head.js), not localStorage.** ⇒ read/write prefs via `UIS` or `lsGet`/`lsSet`; `tests/test_arch.py` refuses bare `localStorage` outside `88e-rvnotes.js`·`43-notify.js`. ⚠localStorage is kept as a rollback copy and only read once (`__UIP === null` migration) — never clear it. ⚠Pref writes from a page (tests, screen_check) reach the server file: stub `fetch` / pin `window.__UIP`.
- **«Reset display settings» wipes only the tab that pressed it.** Other open Sidereus tabs keep their in-memory `UIS` and re-post any key they write afterwards (per-key last writer wins). ⚠Reload the other tabs after a reset; a 4xx batch is dropped (not retried), network/5xx failures are requeued.
- ⚠**Automation pages must not write the owner's prefs.** A playwright live check loads the real `ui-prefs.json`, and one stray click (status-bar popup primary row) removed `mbMainAcct`. ⇒ `UIS` (app-head.js) never posts when `navigator.webdriver === true` or the page was opened with `?nosave=1` (kept in sessionStorage `sidereus.nosave` for the tab); changes stay in that page's memory. ⚠Use `?nosave=1` for every automated visit: MCP playwright browsers report `webdriver=false`. ⚠Do not move this check into callers — the single gate is the POST switch `on`.
- ★**Pipeline running animations hitched every poll** (2026-10-04). A live run changes the HTML each poll, so `paintPipe` rebuilds `.plw` and every CSS animation restarts at 0%.
  - ⇒ `paintPipe` sets `--plt = -performance.now() ms` on `.plw`; looping rules (`plbreath`·`plrot`·`tldot` in 43-pipeline.css) use `animation-delay:var(--plt,0s)` — same phase after any rebuild.
  - ⚠A new looping animation inside `.plw` needs the same delay; one-shot ones (`plpop`) must not get it.
- **Pipeline stage colours are display-only**. Nodes, chevrons and catalog items read `plgHue(n)` = the stage's own `ui.color`, else its catalog group colour (`plgFam`).
  - ⚠Never write a preset colour into `ui.color` — it would be saved and outlive a rename. A user `ui.color` always wins.
  - ⚠New preset colours stay in relative luminance 0.13–0.30: that window keeps ≥3:1 against both dark and light panels.
- ★**Browsers never give an absolute folder path** (`<input type=file webkitdirectory>` = names only) ⇒ «Choose folder…» POSTs `/api/pick-folder` and the server opens the OS dialog (`pipeline_projects.pick_folder`, one at a time, Origin-guarded, fills the path only). ⚠The dialog opens behind the browser unless brought forward: Mac runs `choose folder` inside `tell application "System Events"` + `activate`; Windows uses a TopMost owner form. Mac shows dot-folders via `with invisibles`; Windows only with Explorer «Hidden items» on.
- ★**Pipeline canvas: «Arrange» keeps the zoom only if it marks the view touched** (2026-10-05: 80% → 100% on «Arrange», 6 stages showed 1 at 900px). `plGwFit` re-fits every untouched view after the paint. ⇒ `plFit(E, cv, true, true)` re-flows for `cw / z` and sets `E.touched`; saved positions fit the whole chain (≥ `PL_ZFIT` 40%); «Fit to view» = `plFit(E, cv, false)`. ⚠Leaving `touched` false brings the zoom snap back.
- ★**First paint wraps saved one-row positions that only fit below 80%** (2026-10-05, 6 stages: 900 → 53% 6/6 · 1100 → 74% 6/6 · 1440 → 79% 6/6, was 40% 3/6 · 5/6 · 59%). ⇒ `plWrapFirst`: `plWrapCols` tries every row count, keeps the largest whole-chain zoom; `E.laid` keeps the draft clean, `E.touched` stops `plGwFit` re-flowing it. «Arrange» / «Fit to view» use the same `plWrapBest` (Arrange keeps the zoom only while `plFitRaw` — loop lanes included — still fits). ⚠A second re-flow rule for either button brings back results smaller than the first paint.
- ★**48f folder browser swallows Escape while open** (2026-10-03, `48f-pipeline-browse.js` capture keydown). On purpose: other Esc handlers (code popup, drawer) would close the view underneath. ⚠Do not drop `stopPropagation` or the capture flag; Tab is trapped in the same handler (`plBrTrap`).
- ★**`input[type=search]{flex:1}` (45-saver-quota.css, specificity 0,1,1) beats a single class** (2026-09-29, «Source» tree filter). In a column flex it stretched the box to half the popup height. ⇒ scope with two classes (`.srtl .srtq`). ⚠Any new search input inside a flex column needs the same.
- ★**The toolbar search box lost focus on every keystroke** (2026-09-28 history filter). Cause: putting `value=` in markup drawn via `tbSlot`/`setHtml` changes the slot HTML on each input and triggers a repaint. ⇒ Draw markup without value, then fill `.value` (`85-history.js` paintHist).
- ★**Closed review drawer #rvpop and preview #rvq stayed visible** (2026-09-27 review). Cause: `#rvpop[hidden]{display:none}` had lower specificity than `html[data-ui=next] #rvpop{display:flex}` ⇒ the hidden rule also gets `html[data-ui=next]` (82-review.css:2). ⚠When writing a new popover rule that sets `display`, write its `[hidden]` rule with the same prefix.
- ★**One session-count basis `sesCount()`** (41-sesdrawer): open = not done, working = think · tool · waiting on subagents, idle = the rest. The header chips and «Sessions» number (`sesdrBadge`) read the same value.
- ★**Question waits and aborts counted as «idle»** (2026-09-24). ⇒ `sesCount().need` (ask · abort) = «Waiting on you» — same value in chips and header tooltip; sum = open. The activity line (42-activity `actRows`) uses the same classes — ask · abort are pills; waiting on background work (subagent + Bash background) is a running pill.
- ★**The session drawer ended 70px above the footer** (1024×700). Cause: `#sess{max-height:46vh}` (for the pinned column). ⇒ Drawer mode only: `max-height:none` + bottom `--sesdr-bot` (`sesdrPlace` computes it from `#sbar` top).
- ★**Scroll position lost on tab return**. Cause: `mvScrollBack` set it once before the async load → clamped on a short page. ⇒ Reapply via rAF for 4 s, stopping on user input (wheel · touch · pointer · key) or tab switch.
- ★**Numbers without units or legends** (2026-09-24 UX audit). Structure treemap «sidereus 10,198» (no unit) · timeline hatching explained only in bar tooltips · drawer «opus-5» touching the scrollbar, looking clipped (1024).
  - ⇒ Treemap project/region labels use `U(n, <lines unit>)` (82-structure-canvas) · «asleep (sleep)» · «earlier records not read» chips in the axis row's empty name cell `.tllg` (74-timeline, adds 0 height; white in 91-light) · `#sess` gets `scrollbar-gutter:stable` + 6px (60-sessions.css).
  - ⇒ Token notation is one `fmtTok` (uppercase K/M/B) — 40b-sessions-list's `k` · the Korean 10^4-unit form of «1M» aligned. ⚠Never write new values in the Korean 10^4 unit (e.g. 300K as «30 × 10^4») (1 left in 45-tokens).
- ★**Switching tabs carried the scroll over** (2026-09-24 UX audit: chat 4136 → the token tab opened mid-table at 1965). Cause: all tabs share the single `#feed` scroller and `setMainView` never touched scrollTop.
  - ⇒ Record into `mvScroll[tab]` on leave and call `mvScrollBack()` right after painting (92-mainview-tabs) — a first-opened tab gets 0. Chat keeps its existing `toBottom`. Measured: chat 3744 → token 0 · token 600 → history 0 → token 600.
  - ⚠A new tab needs `mvScrollBack()` in its branch too.
- ★**The bottom bar was clipped** (2026-09-24, 2 external · 1440px). ⇒ `sbFit` hides whole items in `SB_STEPS` order (100% forecast → forecast at reset → `.sbtight` padding 10→6px, no text lost → duplicate «left ≈» token value → ext «today» → ext limit % → reset times → saver extras). Ellipsis is the last resort.
  - ★2026-10-08: after the 12px floor, 1100px was 4px short and dropped ext «today» (the label that gives the number its meaning); the padding step now absorbs that.
  - ⚠Never re-add fixed-width media rules to `.sbar` (e.g. hiding `.sb2` at `max-width:1400px`) — they hide even with room and break the priority.
- **The header activity strip `#actv` is removed** (42-activity · 94-activity.css). 42-activity renders only the needs-me pills of the rail «Attention» list `#rattnl` (red, same set as `attnRows().shown` badge rows); click → `cpGo`, hover = `#acthc`.
  - ⚠Metadata only: tools by **name** (`x.tool`) only — never put `x.targ` (command · file · pattern), task or reply on the pills or cards.
  - ⚠Do not bring the strip back into `.hrow`; `tests/test_header_no_activity_strip.py` fails on leftover strip code.
- ★**Left rail + one-row top bar** (2026-10-11). `<nav id=rail>` (56px icons · 208px open, pushes content at ≥1200px, overlays below · Cmd/Ctrl+B · `sidereus.rail`) holds brand + `#dot`, «Attention» `#rattnl`, the `#mvw` views, bell · gear. Top bar `.hrow` (48px, nowrap) = `#vtitle` · `#todo` · `#sesb`.
  - ⚠The header squeeze ladder (`hdrFit`, `body.hf1..hf6`) is removed: with tabs out of the bar, `.hrow` stays 48px with no wrap or overflow at 900/1100/1440 (en, five `#todo` chips). Do not bring back width steps for the bar.
  - ⚠Collapsed rail labels (`.mvl` · `.rlab`) are clip-path visually-hidden, never `display:none` — `scripts/screen_check.mjs` reads tab names via `innerText`, which skips `display:none` text.
  - Toggle `#railtg` lives in `.rbrand`: open = borderless «‹» at the brand row's right end; collapsed = laid over the 28px mark, which swaps to «›» on hover/focus (expand = click the mark). Its name shows in `#railtip` right of the rail in both states. ⚠Keep the collapsed button exactly the mark's box (no shift) · the mark's moon tooltip shows only while open (the button covers it when collapsed) · do not put the toggle back in flow under the mark (read as a stray bordered box).
  - ⚠Needs-me pills render into `#rattnl` (rail); every pill selector (click · hover · `actTick` · `actHovShow` · drawer outside-click exceptions) targets `#rattnl`.
  - ⚠The collapsed rail's Attention badge `#rattnb` opens a **peek** (`railShow`, no `lsSet`) — it once called `railSet(true)`, saving `sidereus.rail='1'` so the rail stayed open for good. The peek ends on an outside pointerdown, a jump from the list (`actGo` → `railPeekEnd`) or scrim/Esc. Only `railSet` (toggle · Cmd/Ctrl+B) writes the pref (92d-rail.js, test `test_rail_js.test_peek_keeps_saved_pref`).
- ★**Per-tab toolbar `#tbar`** (2026-09-24). **`#tbar` at the very end of the header (right above the body)**. The header does not scroll, so the toolbar is always visible (no sticky needed).
  - ⇒ Contract: one `<div class=tbs data-tb=<mainView>>` per tab inside `#tbar`. `applyMainView` shows only the current tab's. Tabs draw with `tbSet('<mainView>', html)` and bind directly to the returned slot (or global ids). An empty slot collapses the row (`:has`).
  - ⇒ Moved so far: chat (room · filter · thread · count · search · time order · view, static markup) · time (replay · refresh · range · `?`) · token (period day/week/month) · br (repo · ↻) · struct (session · project chips · ↻) · hist (search · last 7/14/30/90 days · loading) · retro (last 7/30 days · loading). Structure's colour axis, test toggle and replay bar stay in the body, attached to the legend/canvas.
  - ⚠struct · hist · retro slots are not in `index.html` — `tbSlot(k, html)` (80-structure) creates them after the last `.tbs` in `#tbar` on first paint and calls `tbSet`. If a static slot is added, `tbSlot` simply becomes `tbSet`.
  - ⇒ Threads: `thsFit` folds chips that do not fit into «+N» (the selected one stays) · click → full list in `#thpop` (max 60). At ≤900px the toolbar wraps to 2 lines.
  - ⚠`tbSet` does not rewrite identical html (keeps an open `<select>` and focus across poll repaints). Code that edits the DOM directly (`tlrp`) is reconciled on the next paint.
  - ⚠The timeline axis is sticky at `top:34px` — when controls left the view head and it became 31.7px, rows showed through the gap. ⇒ `.wvh.wvht:has(+ .tlaxr){min-height:34px}`.
  - ⚠Same family (2026-09-26): the work log's `.wvh` was 31.67px while `.aghd` is sticky at `top:66px` (=34+32), so log text showed through a 0.33px gap. ⇒ `.wvh:has(+ .aghd){box-sizing:border-box;min-height:32px}` (`40-tokens.css`). When changing a sticky head's height, check the `top` of the layer below.
- **One header→content divider** (2026-10-13). Cause: tab captions `.wvh.wvht` drew a second full-width rule under the header rule, and `.brep`/`.rcw` top padding doubled the 12px gap (24–26px).
  - ⇒ Only the header's `var(--nx-rule)` line, then `#feed`'s 12px. `.wvh.wvht{border-bottom-width:0}`; the timeline keeps its line as the axis top (`:has(+ .tlaxr)`). `.brep`/`.rcw` have no top padding.
  - ⇒ Sub-view switches (Tokens «Usage | Tools», Pipelines «Pipelines | Harness») go in `#tbar` via `tbSet('token')`/`tbSlot('pipe')`, never in the body.
  - ⚠The sticky caption has no bottom edge while stuck (accepted); a new caption/toolbar row must not add its own rule.
- ★**Right session column → top-right drawer** (2026-09-24). Default is no column; the header «Session» button (`#sesb`, badge = running tool/think · needs-me sessions `attnBadgeN`) opens it. `#lstog` · `body.lsoff/lson` are gone.
  - ⇒ State `sidereus.sespin` (1 = pinned = the old right column) · `sidereus.sesdr` (1 = drawer open). Old `sidereusLsOff` is migrated once ('0' → pinned, else → drawer) then deleted. `sidereus.wkside` shows only when pinned.
  - ⇒ Anything that goes to a row (`cpGo` · attention rows · top chips `#todo .td`) opens via `sesdrReveal()` first. Outside click is a capture `pointerdown` — correct even when a list repaint detaches the target.
  - ⚠Closed is `visibility:hidden` — `display:none` resets `#sess` scroll to 0. Poll repaints run even while closed.
  - ⚠Removing the outside-click exceptions (`#dpop` · `.cmdk` · `.cfgm` · `#alarm` · `#toasts` · `#sdrw`) closes the drawer the moment a diff or popup opened from it is clicked. Esc yields to windows on top, and `preventDefault` blocks the branch-detail Esc.
  - ⚠The drawer sits below `header .hrow` (`--sesdr-top`), not below the whole header.
  - ⇒ Size (09-27): default 640px · height fits content. Left · bottom · bottom-left handles (`#sesrz`, drag · arrows 24px · double-click/Home = default) → `sidereus.sesdrsz` {w,h} (0 = default), w 420..min(1200, vw−32) · h (max-height) 240..vh−80. ⚠Handles are fixed siblings outside the aside — inside, they scroll up with it.
  - ⇒ 09-24 cleanup: removed 50's ≤1320px `.lside{display:none}` block (the 45 grid covered everything) · token/retro two-column split is `.split2` (50, #feed ≥1100px, left share `--split2-a`). Retro also emits `split2` (09-24) — ⚠do not delete 50's `.rtg.split2`: 87's default `.rtg` grid is a later file with equal specificity and beats a bare `.split2`. Also removed 60's ≤1000px `.wrap`/`#composein` grid (45 covers it) — only `aside{position:static;order:-1}` remains (removing it moves the feed at pinned 700px, measured by probe).
- ★**Token widget removed from the right panel** (2026-09-24 owner-approved: the right side is the session column only). Off (default) → `body:not(.wkside) .lside > .wku{display:none}` + `buildWku` empties `#wku`.
  - ⚠The donut can appear in the side panel and the token tab at once, so ↻ is a delegated `.wkr` click with no `id` — never revert to `getElementById('wkr')`.
  - ⚠Today's point on the token tab line chart = `tok + liveAdd`. If `WKU.at === WKR.at` use `WKU.liveAdd` (30 s refresh), else `WKR.liveAdd` (re-fetched, 60 s throttle).
- ★**Light theme** (2026-09-24). Settings → «Display» → **one background tone** (black · grey · blue · white · system) = `localStorage.mbTone` → `html[data-tone]`+`html[data-theme]` (before first paint in `app-head.js`; switching via `setTheme` · 90-settings).
  - System = OS light → white, OS dark → the last dark tone (`mbToneDk`, else black). The trial `mbTheme=light` is migrated once to `mbTone=white` and deleted.
  - ⚠Do not add a separate «theme» — it overlapped with background tone, so they were merged (2026-09-24).
  - Tokens: `css/91-light.css` redefines `--nx-*` (body contrast ≥4.5). Hard-coded colours in old CSS are moved by the `#nxlt` twin (`lite()`) in `00-core.js` to `html[data-ui=next]:where([data-theme=light])`.
  - Colours drawn from JS (canvas · SVG attributes · inline style) use `thc(dark, light)` — on switch `setTheme` repaints the current tab and burndown.
  - ⚠New colours only via `var(--nx-*)` or `thc()`. The twin skips hard-coded colours in selectors containing `data-ui` → add an override in 91-light.
  - ⚠Keep `:where()` — the light twin must have the same specificity as the dark twin so cascade order holds (without it, it beats `html[data-ui=next] .x` rules).
  - ⚠Dark is byte-identical: `#nxcss` text 90,908 chars identical before/after (measured). Rules inside `@media` are skipped by both twins.
- ★**«no repository» flashed for 1–2 s on first load** (2026-09-23). Cause: `SESS=[]` before the first `/api/state` was drawn as «none» (branch-tab chips + `loadBr` error text).
  - ⇒ `STATE_IN` (00-core) turns on with the first state. Before that `loadBr` shows loading only; `poll()` calls `loadBr` again on the first state.
  - ⚠Any new screen that judges «none» from an empty array checks `STATE_IN` first.
- ⚠**Inline `style="left:%"` beats `.rgx i.a1{left:auto}`** (2026-09-23) — the last x-axis label stuck out 1px to the right, causing horizontal scroll on the token tab. ⇒ No inline `left` on the end label.
- ★**A parameter named `T` shadows i18n `T()`** (2026-09-23 · timeline cursor snapshot blank, console `T is not a function`). It broke the moment `T('…')` was used inside `tlCurSnap(T)`.
  - ⇒ The time argument is now `ts`. ⚠Never name a variable or argument `T` (`tlTokAt(T)` has no `T()` call, so still harmless).
- ★**`T()` cannot catch number+unit** (2026-09-23 · `Shown 3` + Korean people counter · a Korean «4 hours ago» remained in the English participant panel). `T()` keys on phrases, so it never sees `n + <Korean minutes unit>`.
  - ⇒ `U(n, <minutes unit>)` · `AGO(t)` · `LATER(t)` · `HM(min)` (next to `cntText`). `ago` · `agoAt` · `agoSec` · `fvAgo` · `bnDur` · `tlSumDur` already use them.
  - ⚠Korean output must stay byte-identical — never append `n` + a Korean counter word directly in a new place. Some all-Korean tooltips (`title`) remain.
  - ⇒ Sentences containing numbers branch whole: `LANG === 'en' ? English sentence : existing Korean expression` (timeline header · summary panel · name-cell tooltip, 09-23). Bar `title` («this segment …») is translated too.
  - ★09-24 full demo English sweep (text · title · aria · placeholder · hover cards · drawer · settings · work window): Hangul 4 → 2. Remaining: the token tab «(sub)» row (`45-tokens.js` does not go through `TN()`).
  - ⚠The server `type`/`desc` suffix ` · session <id>` (Korean on the wire) is swapped only at the tail by `wkLab()` (35b-worklog-view) — it contains user data, so never pass it whole to `T()`.
- ★**The language pack keys on the Korean source text** (2026-09-23; Korean and English only).
  - `T(<Korean «Settings»>)` ⇒ `LANG==='ko'` returns the source as-is, `'en'` returns `I18N.en[<same key>]`, **else the source** (around `:12809`). An empty dictionary never breaks the screen.
  - ⚠**Never wrap fragments in `T()`** — pieces joined to numbers or HTML like the Korean counter words for items · cases · people break in English word order. Wrap **complete phrases** only (so «22 hours ago» · «300 cases» stay Korean on the English screen — not a defect).
  - ⚠**`T()` cannot reach static HTML** — header, `h2` and the send bar are dressed by JS in `hdrLang()` · `paintCompose()`. New static text must be added there too to switch to English.
  - ⚠When merging the dictionary by script, **a trailing comma on the last entry** and **real newlines inside keys** break `node --check` (both hit here). Keys must match the source `T()` argument **down to spaces and `…`**.
  - ⛔Code comments are English, but **Korean is the canonical screen text** — fill `I18N.en` only.
  - Sentences with numbers/HTML use `KE(koExpr, enExpr)` (05-i18n.js) — the ko argument is **the original expression unchanged**, so Korean bytes do not change. Extra dictionaries `06-i18n-{a..e}.js` · `06-i18n-q.js` («Preferences» strings) append via `Object.assign(I18N.en, …)` (after 05, before 08).
  - Measured 2026-09-24: 897 dictionary entries. English mode at 1440×900 across all tabs, KPI popovers, alarms, session drawer, settings, hover cards and work log: 0 UI Hangul chars (body and title; previously up to 41 body chars and 1,560 title chars per tab). The Korean screen rendered side by side with the old PAGE is line-for-line identical.
  - ★Server-built text (2026-09-24): the server keeps Korean and the **screen** translates — stored old cards translate too. When `T()` misses, `TRX()` (06-i18n-g.js pattern table: «Other N» · «(subagent)» · «Mailbox watch» · failure signatures · git/history/«failed (…)» errors) applies. Health-strip warnings: `hlMsg(w)` picks English by **`key`** and extracts only exception names and numbers from `msg`. In English the saver tooltip shows `main`+`sub` instead of the hook `head`.
    - ⚠Superseded by stage D (2026-10-08): `TRX_EN`/`HL_EN` are gone. Korean the server still sends goes through `srvEn()` (06-i18n-g.js) at the caller — when changing `_SIG_RULES` or burn row names, update `srvEn` too, or the Korean source shows on the English screen.
    - ★2026-09-24: `warn_once(key, msg, en=…)` — the server emits the English original with each warning. `viewer.err` is English; health entries carry `msg` (Korean as-is) + `msgEn`. `hlMsg` prefers `msgEn`, else the `HL_EN` path above (kept for now). ⚠New calls require `en=` — `tests/test_warn_en.py` enforces it via AST (no exceptions).
- ★**English source + `I18N.ko`** (2026-10-08, stage A of the migration). `T('Save')` = English as-is; Korean looks up `I18N.ko` (English → Korean); two Korean readings of one English text = `T('Clear', 'tidy')` → key `'Clear|tidy'`.
  - ⚠A missing ko entry shows English on the Korean screen with no error — `scripts/i18n_check.mjs` (`check.sh --fast`, `--stage=A|B|D`) is the only guard.
  - ⚠Korean mode now translates any `T(x)` whose `x` equals an English dictionary key — user data (names, tool names) must go through `TN()` or skip `T()`.
  - ★Stage D (2026-10-08): the bridge (`I18N.en`, `_legacy`, `i18nBridge`, `UNIT_EN`, `TRX_EN`, `HL_EN`) is removed; `T()` in English returns its input, `U()` takes English units only. `i18n_check --stage=D` fails on any bridge reference. Wire values the page compares verbatim (the Korean «Other» bucket, the Korean «cut off?» state, the Korean lvNm «weekly near limit», attention `why`, mailbox tags) stay Korean on purpose.
  - ⇒ Convert callers with `scripts/i18n_flip.mjs` (dry run lists the manual rest); equivalence = `tests/test_i18n_flip.py` against `tests/fixtures/i18n_legacy_en.json` + `screen_check.mjs --strict`.
    - Remaining Hangul is content: agent descriptions (`lab`), ack notes, message bodies/title tags, project names.
- ★**The palette (Cmd+K) finds sessions by `sid`, not cwd** (2026-09-23 · review finding).
  - `sessions()` is per transcript, so **one cwd can have several sessions** (`:8782` keeps old ones). Rows carry `data-ssid`; lookup is sid first, cwd second. The flash key `cpFlash` is `cpKey(x)` (`s:<sid>`) too.
  - ⚠Even when the row is found, if `.lside` is hidden (`@media max-width:1320px` · `body.dpop`) `scrollIntoView` **does nothing** ⇒ check `row.offsetParent` and explain via `note()`.
  - ⚠Clearing filters and sidebar collapse stays, but **say what was cleared via `note()`** — `saveFil()` persists, so a silent revert looks like lost settings.
  - ⚠In a popup (`ISPOP`) `cpOpen()` returns at once — `#cmdk` is outside `.wrap` so it would open, but the earlier-registered diff handler eats Esc and calls `window.close()`.
- ★**Descendant-selector trap — fourth time in this file** (2026-09-22).
  Cause: JS adds `run`/`warm` to **`.sxw`** (`:12490` · `:12526`) but CSS was `.sx.run .sd` · `.sx.warm .sd`. ★Measured **0** matches. Worse, 7 state colours (`.s-tool/.s-ask/.s-think/.s-abort/.s-wait/.s-done/.s-unknown .sd`) paint every `.sd`, so **fixing the selector still shows nothing**.
  ⇒ **Deleted** rather than revived — the dot (`.sd`) encodes **state only** (adding age puts two axes on one dot). The age signal is already `.sxw.idlelong .sx2`. The JS `warm` branch went too.
  ⚠`run` stays — `.sxw.run .sp` (bold project name) really uses it. ⚠Lowering specificity with `:where()` was **not the answer** (state colours still win). ⚠Before deleting, check other consumers with `grep -n "warm" chat_server.py`.
- ★**Secondary text grey is fixed by «palette», not «per spot»** (2026-09-21; secondary text was too faint overall).
  **24** neutral greys had sprawled and the floor sank to **2.03:1** (`.stbr` #3d4756) — raising spot by spot makes the tone patchy.
  ⇒ **Converged** to five steps (`#c3ccda` 10.9 > `#a8b3c4` 8.6 > `#8b95a7` 6.3 > `#7e8896` 5.3 > `#6b7688` 4.2 floor), raising everything one step while keeping the hierarchy (evidence comment above `.cnt`).
  ⚠**No new colours** — this consolidates, it does not add. ⚠**Never revert downward.** ⚠State colours (red · yellow · green · blue) and the estimate hierarchy (`.burn em`) are out of scope.
- ★**Saved views — restore is «set variables + call renders» as one unit** (2026-09-21). With six filter layers,
  the same combination was rebuilt by hand every time. `mbViews` (localStorage · `[{v:1,n,s}]` · max 12 · 16 state fields).
  - ⚠Changing DOM values without calling renders desyncs screen and state ⇒ `vwApply()` applies `saveFil()` · `fvSave()`
    then calls `buildRooms`/`buildTabs`/`buildSessions`/`full()`/`setMainView()`.
  - ⚠**One-off UI is not saved** (modals · scroll position · split ratio · alarm window) — restoring it surprises people.
  - ⚠Tag with `v:1`. If the format changes, do not silently drop old views — say so in one line.
  - A per-item `✕` cannot go inside `<option>`, so it is a **custom dropdown** (`#vwb`/`#vwpop`) — reverting to
    `select` loses the delete buttons.
- ★**Boot did not repaint the saved view — the tab was lit but the body was empty**
  (2026-09-09 · surfaced while adding the «daily» tab).
  - Boot was only `setTimeout(… applyMainView(); buildMv(); loadTl(true) …)`; **per-view entry lived only in
    `setMainView` (= tab click)**. So reloading with `localStorage.mbMainView` = `fail`
    left `#feed` at `feedLen 0` **forever.** The tab showed `on`, so it read as «is the server dead?».
  - ⚠**Do not assume «blank» is the same for every view.** Measured, `token` was not — the main poll (2.5 s)
    calls `loadWku()`, which ends with `if(mainView === 'token') paintToken()`, so it **paints itself on the first poll.**
    So `fail` (and `daily` at the time) were broken, and `token` was merely 2.5 s late.
  - ⇒ `bootView()`, called from the boot `setTimeout`. ⚠**Never substitute `setMainView(mainView)`** — its
    `fvMarkSeen()` marks failures as seen **on reload alone**, clearing the bell and tab badge. Badges must clear
    **only when the user clicks** the tab.
  - Repro: in the console `localStorage.mbMainView='fail'`, reload → `document.getElementById('feed').innerHTML.length`.
- ★**The «daily» tab was removed** (2026-09-21).
  - Cause: updates depended on **manually running** `/today`, so `summaries.json` stopped on 9/9 (last 3 of
    99 · 12-day gap). No cron/launchd, and summaries must be written by a model, so it cannot be automated.
  - Removed: backend `daily()` · `_daily_*` · `/api/daily` 137 lines · CSS `.dl*` 28 lines · JS `paintDaily` family
    97 lines · 1 tab. Data (`~/claude-daily/`) and backup (`backup/mailbox-20260921-141109.tar.gz`) were kept.
  - ⚠**Do not delete `_tx_cwd` (formerly `_daily_cwd`)** — the timeline uses it (`:2126`). `.wvh`/`.wvempty` CSS is
    shared with the «work log». Only these two were kept outside the daily block; the rest was removed.
  - ★**`cwd` is read from the «end» of the transcript** (measured 2026-09-09). `--resume` changes the folder —
    `8b12c025` started in the home directory and moved to `~/.mailbox-mcp` from 13:19. Reading the first line gives a false name.
- ★**Never leave «a spot that does nothing when clicked»** (2026-09-08).
  - `.tlr` had `cursor:pointer`, but the click handler was **only on the bar** —
    a pointer cursor that does nothing reads as broken.
  - ⇒ The name cell (`.tlnm[data-tlt]`) opens the same drawer. Target is **the running one first, else the last**
    (`pickIt`) — «what is it doing now» is this screen's question. Without a tid, nothing is bound.
  - ⚠The name-cell click needs `stopPropagation()` — otherwise it leaks into the time cursor's pin toggle.
- ★**Stale dimming (`html.agstale`) made held numbers unreadable** (2026-10-05, demo 900 light: opacity .45 + grayscale(.7) = 1.81-2.63:1). ⇒ opacity .8, no grayscale: min 3.24:1 light (`.sbok` 3.47) / 3.88:1 dark; «as of N s ago» carries the «old» signal. ⚠.7 still left light `.sbok` at 2.89:1 — do not go lower without re-measuring both themes.
- ★**Poll-time cell swaps dropped keyboard focus** — cells `replaceWith`'d on an HTML change lost focus within 2-3 s. ⇒ copy attributes + `innerHTML` onto the same node; ⚠skip `aria-expanded` (popAnchor/popHide own it on the live node). Same for Cmd+K: `cpOpen` keeps the opener, `cpClose` refocuses it (`preventScroll`, cpGo scrolls after).
- ★**Pipeline clicks dropped focus to BODY** (2026-10-05, «Standard templates» / «Open draft» / palette preset by keyboard). `plPaint` replaces `.plw` with innerHTML, so the pressed button no longer exists. ⇒ call `plRefocus(sel, ...)` (48d) after `plPaint()` with stable `data-` selectors: the opened panel's first control, else the same control. ⚠Palette presets must stay `<button>`. As `div draggable` they could only be dragged; Enter and click did nothing.
- **Agent labels showed the raw `[pl:…]` tag.** Cause: the row label is the raw Agent `description`/SendMessage `summary`, and pipeline linking (`plDescStage` · `plTagNames` · `wpRunOf`) reads the tag from the same raw `lab`/`desc`.
  - ⇒ `plStrip()` (00-core) only at display time — strips only the leading tag (including after «type: »). `test_pl_tag_strip_js`.
  - ⚠Stripping `lab`/`desc` on the server turns pipeline stage lights off. Never touch the source fields.
- ⚠**Header KPI strip removed** (`#kn`, former 56/56b). 5h/7d quota shows only in the status bar `#sbar`.
  - ⇒ `screen_check.mjs` / `readme_cdp.mjs` wait for first render on `#sbar` text; `screen_check` fails if `#kn` or `.kni` comes back.
  - ⚠`knQ` (55a), `sesCount` (41), `knUnc` (57) keep their `kn` names on purpose — tests and callers find them by name.
  - Server `fail1h` and `extUsage[].rate10` stay in `state()` with no page reader (no API change).
- **Tab content heads do not repeat the header title** (`#vtitle`). Timeline · Tokens · Tools · Insights · Pipelines · Structure · Branches heads keep only the caption (age, status, «Tool list»).
  - ⇒ caption-only `.wvh.wvht` keeps the titled row height via `.wvh.wvht:not(:has(>b))` (40-tokens.css); retro emits no `.tlhd` until it has an age.
  - ⚠Do not add the tab name back as a `<b>`; a head whose title narrows the scope («Subagent timeline», «Harness», «Board») stays. `test_tab_head_dedupe_a_js`.

## Filled fields: the edge must be a box-shadow (`90-main-ui.css` base field rule)

- Cause: the light-theme focus border rule in `95-focus` (0,3,1) and the late field-border rule in `90-main-ui.css` (0,2,2) set `border-color` on every field, so a transparent resting border never stays transparent.
- ⇒ A filled field uses `border:0` and draws its hairline / hover edge / focus edge with `box-shadow`.
- ★Hairline on the fill 3.07–3.26:1 in every tone and light; the fill alone is only 1.09–1.15:1 — do not drop the hairline.
- ⚠The select chevron is `!important`: `.tlsel`, `.straxw select` and `#cfgbox .cfgsel` set the `background` shorthand, which erases a plain chevron background-image.

## Running animations: compositor-only (`21-timeline-plrun.css`, `43-pipeline.css`)

- Cause: animating `background-position`, `box-shadow` or an `@property` forces a style recalc every frame.
- ★Demo, 25 s: timeline recalcs 1,569 -> 176, pipeline tab 1,584 -> 140 after moving to `transform`/`opacity` on `::before`/`::after` (2026-10-08).
- ⚠New running/pulse effects animate only `transform`/`opacity` on a pseudo-element; reduced-motion rules target that pseudo-element.
- ★Session dots (`60-sessions.css`, drawer open, 10 s isolated): `pl`/`pl2` box-shadow and `dots` content ~590 recalcs over base each -> ~22 (ring = scaled `::after`, dots = `clip-path` step reveal, composited in Chrome 154).
- ⚠Measure the session list with the drawer open: a closed drawer pauses its animations (`92-sessions-drawer.css`), and `Animation.play()` overrides that pause (false ~600 recalcs).
- ⚠`plpulse` (`43-pipeline.css`, SVG `stroke-dashoffset`, ~600 recalcs/10 s while a loop edge pulses) has no compositor path; left as is.

## Drag-resize: always `dragTrack()` (`08-ui-kit.js`)

- Cause: hand-rolled drags without pointer capture, `pointercancel` or a `!ev.buttons` end stayed stuck when released outside the window.
- ⚠New grips call `dragTrack(e, cap, onMove, onEnd)`; do not add a pointermove/pointerup pair by hand.

## Relative times: always `ago()` (`20`), clock text: `CLK` (`05-i18n.js`)

- Cause: per-screen rounding showed 90–119 s as «2 min» on one screen and «1 min» on another.
- ⚠`ago()` floors; `CLK` caches one `Intl.DateTimeFormat` per language — do not call `toLocaleTimeString` with options in a poll path.

## T() now translates in Korean mode too (`05-i18n.js`)

- Cause: with English source text, Korean mode looks every argument up in `I18N.ko`; before, Korean mode returned the argument unchanged.
- ⚠Never pass user data (stage ids, project/agent names) through `T()` — a name equal to a dictionary text gets translated. Use `TN()` for server placeholders only.
- ⚠Server/exception text through `T()` (`T(c.err)`, `T(e.message)`) is accepted, but it is translated in both languages now.

## Markdown images: hydrated after innerHTML (`00-core.js` mdLinks, `81d` strMdImgs)

- Cause: `md(src, 1)` builds an HTML string, so an `<img>` there would fetch before any path check and show a broken icon.
- ⇒ `mdLinks` marks only relative image URLs (no scheme, no leading `/`, image extension) as `span.mdimg[data-mdimg]`; `strMdImgs` runs right after `el.innerHTML` in `strTreePaintCode` and swaps in a DOM-built `img` only for a listed, non-secret file of 5 MB or less.
- ⚠Never build an `<img` string or inline svg (alt is user data); `img.onerror` puts the span back. Unmarked spans keep the bytes pinned in `tests/test_structure_follow_js.py`.

## Chat counter names the «Outside rooms» card (`92-mainview-tabs.js` rcPaint)

- Cause: the counter excluded the dm card, so «2 rooms» showed above three cards.
- ⇒ `nr` stays the room count; « + Outside rooms» is appended only while the dm card is in `show` (a tag filter hides it).
- ⚠Do not count the dm card as a room — room actions (Invite · Hide · tags) never apply to it.

## Demo start tab comes from a seeded pref (`ui_prefs.memory_only(seed)`)

- Cause: the demo has no prefs file, so it opened on Timeline like a first run.
- ⇒ `chat_server.main` `--demo` seeds `{"mbMainView": "pipe"}` into the memory store; the real viewer passes no seed and keeps Timeline.
- ⚠Never write the seed to `PATH` — the demo writes nothing to disk.

## Branch chip name has no % floor (`60-sessions.css` `.sx .sb .sbt`)

- Cause: `.sbt{min-width:min(6ch,100%)}` — the % resolves to 0 when the chip (`overflow:visible`) is sized, then to the chip width at layout; a short name («dev») took 6ch and the git state spilled over the account chip.
- ★Headless Chrome: «dev ↑20 ~2» sbt 47px in a 54px chip, 22px over `.sacb`; with `min-width:0` 19px, no overlap; long names unchanged.
- ⇒ `.sbt{min-width:0}`; the chip floor is `.sb{min-width:auto}` (content, capped by `max-width:150px`).
- ⚠Do not put a percentage `min-width` on a child of a box with `overflow:visible` and an automatic min size.
