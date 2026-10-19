# Traps — Quota, saver and tokens

Conventions (entry shape, `★` `⚠` `⇒`, `§N`, `:NNNN`): [TRAPS.md](../TRAPS.md). Newest first within an area; new traps go at the top of their area.

## Quota, burndown and saver

- ⚠**A non-primary main account lost «left ≈» on the status bar** (2026-10-12). The status bar returned nothing when `mainAcct()` was set, and `burn._qb_acct_body` never filled `est`, so only % showed. ⇒ The account body gets `est` from its own `uuid|plan` history row (`_qb_acct_key`; ⚠always with the plan — plan-less and `|claude_pro` rows exist), and the page shows only «left ≈» from `burnFor()` (measured «Used» stays the primary's, hidden). ⚠Guard `typeof burnFor` — JS tests load a subset of files.
- ⚠**Saver level table is hook data, not a UI copy** (2026-10-14). Settings › «Saver mode» › «What each level does» renders `levels`/`how` from `.saver-view.json`; the hook builds them from the same `RULES` table `rules_text` injects (`~/.claude/hooks/saver.py`, `saver_levels_test.py`). ⇒ Change a rule in `RULES` only — never hardcode level text in `web/`. `_saver_levels_clean` caps sizes and drops malformed keys; rule strings are escaped and never go through `T()`. Test: `test_saver_levels.py`.
- **Per-account quota for extra roots** (`sidereus/quota_roots.py`, popover «Other accounts»).
  - Cause: each signed-in root has its own token, limit window and 429 state; the primary path keeps one global state.
  - Fix: `tick()` at the top of `quota_loop._quota_tick` (no sleep), own `_acc` entry per root (fail count, Retry-After, `next`), local request+parse.
  - ⚠Claude Code's keychain service hashes the **raw** `CLAUDE_CONFIG_DIR` string (`~/x`, `/abs/x`, `/abs/x/` differ) — try every spelling; `~/.claude` is the plain service. Check existence by exit code; `-w` only for the match.
  - ⚠Never write (or read) an OMC cache under a root whose `plugins` is a symlink or resolves to the primary's — it would put another account's numbers on the primary HUD.
  - ⚠Never call `quota_fetch._qf_request`/`_qf_parse` from here: they write the primary `_quota["err"]`/`_quota_retry_after`.
  - 5h used-% steps per root persist in `PTS_FILE` (`DATA_DIR/quota-roots-pts.json`: hashed uid, epochs, % only; cleared on account or window change, cap 300). ⚠Never write them to `quota-log.jsonl` — that log is the primary's and feeds BURN/plan.
- **Saver for a non-primary account** (`GET /api/quota/burn?dir=` · `burn.quota_burn_acct` · `saver._saver_views`).
  - Cause: the hook judged every session on the primary's 5h %, so a session on another account got the wrong stage.
  - Fix: `?dir=` is realpath-matched to `claude_roots.accounts()`; primary or no dir = the old body byte-for-byte, unmatched = 400 `{ok:false}` (path never opened). The body comes from the `quota_roots` row (5h/7d %, slope of its `pts` ring, 45-min window); <2 pts = `rate_pph: null`, `rate_src: "not measured"`.
  - Per-account snapshot: `.saver-view-<tag>.json` next to `SAVER_VIEW`, `tag = hashlib.sha1(os.path.realpath(dir).encode()).hexdigest()[:10]`; `/api/state.saverViews` = {label: view}, only with 2+ accounts.
  - ⚠The hook must compute the same tag formula (realpath, sha1, first 10 hex) — change both or neither.
  - ⚠Bodies carry the label only, never dir/email/uuid.
- **Modal burndown and saver cap follow the account in use** (`burn.burn_use` · `routes_get._g_quota_burn` `use`/`cap` · `55b burnUse`).
  - Cause: both read the primary only, so after the primary's reset the modal showed the idle note and `cap.avail_tpm` was None while work ran on another account.
  - Fix: one helper picks the account — explicit non-primary «Main account» (ui-prefs `mbMainAcct`) > newest 5h step inside a live window (`quota-log` vs `quota_roots.ring_last`) > primary (tie/none). Every body gets `use`; `cap` is computed from that account's body whichever `?dir=` was asked. A non-primary body has no back-solve, so `cap` uses min(`est.h5_left`, `est.wk_left`) and stays `conf: low`.
  - ⚠Do not add `start`/`reset`/`elapsed` to the `?dir=` body: `svLive` would start deriving rates from it. The page derives them in `burnAcctCur`.
- **MCP quota for a non-primary account** (`GET /api/agent/quota?dir=` · `routes_get._acct_of_dir` · `agent_brief.brief_quota(acct=)`).
  - Cause: `brief_quota()` read only the primary's `quota()`/`quota_burn()`/`_saver_view()`, so `sidereus_quota` reported the primary account to every session.
  - Fix: `?dir=` (the session's config dir) is realpath-matched like `/api/quota/burn`; non-primary reads its `quota_accounts()` row + `quota_burn_acct` + `_saver_views()[label]`. Output names the account in `acct` (label).
  - ⚠Unknown dir = `{ok:false, err:"unknown account"}`, an unmeasured extra = `ok:false, err:"not measured"` — never the primary's numbers. `used5Tok` is None for non-primary.
- **Primary OMC cache written by another account** (`sidereus/quota.py` `_omc_shared_foreign`).
  - Cause: OMC picks its cache from `CLAUDE_CONFIG_DIR/plugins` and keys keychain logins by nothing, so a profile whose `plugins` symlinks to the primary's writes its own account's 5h/7d into the primary's file.
  - Fix: if a non-primary root's `plugins` realpath equals ours and its `accountUuid` differs from the primary's, `_quota_from_omc` returns None (our own fetch only) and `_omc_cache_write` skips (else their HUD shows our quota); checked every 30 s, `warn_once` `omc-shared-foreign`.
  - ⚠Same account or unknown uuid on either side = cache still trusted (unknown is not a mismatch).
- **Status-bar click opens the layer, not the modal** (`60b-sbar-layer.js`, `60-statusbar.js`).
  - Cause: the KPI strip is gone, so its per-account and failure summary moved into a layer on `#sbar`.
  - Fix: bar click/Enter/Space -> `sblToggle`; the centred `#sdrw` modal is one click deeper, via the layer's «Quota details» button (`sblClose` then `sdrwSet(true)`).
  - ⚠Do not wire the bar back to `sdrwSet` — the layer would never open. `buildSbar` repaints the layer only while `popIsOpen('sblpop')`.
  - ⚠Never use the strings `knpop` / `#kn ` — `test_kpi_strip_removed` bans them.
  - ⚠Account rows switch the main account (`sblMakeMain` -> `mpMainAcctRedraw`); the clicked row becomes the main row (not a control), so focus goes to the layer; `sblPaint` puts focus back on the same row after a poll repaint, never on a detached node.
- **Saver `cap` block units** (2026-10-05, `sidereus/saver_cap.py`, merged into `GET /api/quota/burn`).
  - Cause: n = avail ÷ per; the two sides must be the same counter or n is off by the cache-read share (cache reads dominate raw totals).
  - Fix: both are raw totals (in + out + cache_read + cache_creation, unweighted) per minute — `head.eff` comes from `_tok_events`, per-agent rates from the usage index `[in, out, cc, cr]` summed the same way. The hook divides by 1e6 for «M/min».
  - ⚠Do not send M or tokens/hour, and do not cost-weight one side only. ⚠`out` may be the cached `quota_burn` body — merge into a copy.
  - ⚠The 85% stop lives twice: hook `CAP_STOP_PCT` (saver.py) and 55-saver-quota.js `svCapLine` fallback. Change both. The tooltip prefers the hook's `capEff` (count after the stops), never the raw `capN`.
- ★**Token headroom («Remaining ≈ NM» · «used ≈ NM») removed from the screen** (2026-10-02; «38% = 4M used, 6M left» beside «weekly 120M» read as a broken formula).
  - Cause: no stable denominator. Backtest over `quota-log.jsonl`: raw tokens per 1% CV 0.29 (account A, n=99 5h) · 0.40 (account B, n=86) · 0.49 (account B 7d, n=36); cost-weighted (in1 · out5 · cw1.25 · cr0.1) only 0.21 · 0.27 · 0.35. The two accounts differ ~7x per 1% (plan). Other machines' usage is invisible to local transcripts.
  - Fix: burndown rows · status bar show only the official remaining %, the «runs out HH:MM at this pace» time and reset time (`57-burn.js burnHead`, `60-statusbar.js use`). Server `head` (tok/lim/eff) stays — the tokens-tab pace bands (`burnLim`) reads it; MCP `sidereus_quota` sends `used5Tok` (measured) + `emptyAt`, never a token headroom.
  - ⚠Do not reintroduce a token headroom without a stable denominator. Tests `test_burn_js.test_no_token_headroom` · `test_sbar_pct`.
  - Used = measured (`cur.used_local` local sum since the segment start · 7d `wk_used_local` only for `cyc`), shown without ≈ (10-02); limit/headroom/`head.used` = estimate, not shown.
  - ★«left ≈» / 7d «used ≈» = this account's **history** per 1% (`est`, `sidereus/burn_hist.py`: 5h median over closed windows that reached 99% · 7d pooled Δd7), not this window's average (used ÷ %). Backtest median error at 30/50/70%: window-avg 27/22/19% (Pro) · 38/25/16% (team) vs history 12/17/15% · 11/12/9% (10-02). ⚠Window-avg is only the fallback while `est` is null (cold start, unknown account). ⚠Never scan on the request path — background pass + `burn-hist-cache.json`.
  - ★5h history from < 3 windows (`h5_n` < HIST_MIN_WIN) yields to the window average from 30% (10-05): pool n=2 2.66M/% vs window 3.97M/% put «used 207M · left ≈ 136M» at 60% by tokens beside official 49%. Tooltip «history N windows — estimated from this window's average» (`burnEst`; `tests/test_sbar_pct`, `test_burn_js`). ⚠≥ 3 windows: history still wins (decision above unchanged).
- ★**Primary «used» counted every account sharing its projects dir** (2026-10-20; `~/.claude-myaccount/projects` symlinked to `~/.claude/projects`). 7d `wk_used_local` 390.6M = primary 83.5M + other 307.8M; 5h 131.1M = 83.3M + 48.4M.
  - Cause: `_tok_events` (`timeline.py`) and `_tok_scan` (`burn_hist.py`) summed every transcript in the shared dir; `root_of` cannot tell accounts apart there.
  - ⇒ Both keep a session only when `claude_roots.primary_owned(sid, fp)` (SessionStart record first; no record = primary only if no other account shares the primary's projects dir). Exact reset cut unchanged. Test `tests/test_tok_primary.py`.
  - ⚠Never sum the shared projects dir unfiltered for the primary. ⚠Do not use `acct_of(...)[0] == ""` here — it maps unknown to primary, which is the overcount.
- **Non-primary account had no «left ≈»** (`burn._qb_acct_win`, `usage_index.acct_tokens`, `60b-sbar-layer.js sblEst`).
  - Cause: `quota-log.jsonl` and `burn-hist-cache.json` hold the primary only, so `burn_est` is None for another account and `plan_est` had no `head`; the page skips the window average when a main account is set.
  - Fix: with no history est, the account body runs `plan_est` on a copy carrying that account's own window per-1% (its sessions' tokens since the 5h/7d start, hour buckets, `low`); the layer shows «≈ N left» per row, the bar stays as it was (history est only).
  - ⚠Never put that `head` on the body (saver_cap would read conf high) and never use the primary's per-1% for another account (plans sit 5-9x apart).
  - ⚠Own per-account history is not built: the log has one writer for the primary and `_tok_scan` does not attribute tokens per account.
- **Main account bar dropped every token figure** (`burn._qb_acct_body`, `60-statusbar.js use`).
  - Cause: the account body had no used sum and the bar blanks the primary's `used_local` while a main account is set.
  - Fix: the body carries `cur.used_acct` / `wk.used_acct` = `acct_tokens` hour-bucket sums since that account's 5h/7d start (counted once, shared with `_qb_acct_win`); the bar shows them as «used ≈».
  - ⚠Never name them `used_local` (exact measured sum, read by `quota_used5`/MCP) and never fill them from the primary's `_tok_events`. Tests `test_burn_acct.test_own_used_acct_not_primary_sum` · `test_main_acct_js.test_main_own_used_is_approx`.
- ★**Quota history mixed plans after an upgrade** — old-plan windows skewed `base` · `delta` · `est` · held `_qb_lim`.
  - Cause: `~/.claude.json` plan fields (`userRateLimitTier`) lag the upgrade by ~1.6 days, so rows keep the old plan code.
  - Fix: log rows carry `plan`; `burn_hist` groups by `acct|plan` (untagged rows stay `acct`). Fallback: `plan_shift` — this window's per-1% ≥ 2x or ≤ 0.5x history (≥ 3 windows) sets `_plan_cut[acct]` = window start; older windows leave the baseline (`base.why = "plan"`), `est` is null (`est_why = "plan"`) until the next pass, an older `_qb_lim` is stale. The cut only moves forward and never clears; with tagged rows the baseline prefers current-plan windows.
  - ⚠Do not lower `PLAN_MIN_DPCT` (5) or `PLAN_RATIO` (2.0): integer % rounding below 5% is ≥ ±10%, model-mix per-1% CV is 0.29-0.49, plans sit 5-7x apart. Tests `test_burn_plan`.
- ★**Adopting OMC erased the credit (extra) cell** (2026-09-25; the OMC response has no credit slot, so assigning it as-is dropped it). ⇒ `sidereus/quota_loop.py:234-241` carries the existing `extra` over with its own `at` — **only when the account matches** (`_cc_account()` vs stored `acct`, same rule as `_qf_store`). Unknown account: keep. ⚠Any new path that assigns the OMC response as-is must copy this carry-over block.
- ★**5h contribution modal `since` froze at the first cycle** (2026-09-24 · `sidereus/usage.py` `quota_who`). Cause: the seed (`_who_seed_kick`) ran only once after server start, so after cycles changed `since` = first cycle start (★measured 1790164200 < current 1790182799).
  - ⇒ Record `bycSeed.start`; when the cycle start moves by ≥ `WHO_STEP`, re-seed once in the background; `since` uses only the current cycle's seed. Re-seed lower bound = previous seed `until` (no overlap).
  - ⚠Do not rescan on `resets_at` jitter (<300s) — it would cold-scan every poll. Test `test_new_cycle_reseeds_once`.
- ★**Settings modal «Saver mode» writes the same files with the same bytes as `/saver`** (2026-09-23 · `POST /api/saver/set` → `saver_set()`). Mode is `.saver-force.json`, goal % is `.saver-goal.json`.
  - ⇒ `auto` = delete the FORCE file (same as the skill) · compact JSON + newline · tmp + `os.replace` · both caches invalidated. All 11 commands byte-identical to `saver-mode.sh` output.
  - ⚠Never write goal into the FORCE file — `saver.py pace_of` uses that file's mtime as the pace reference point. Re-applying pace also resets the reference point (same as the skill).
  - ⚠`saverView` is refreshed by the hook only at prompts — the modal's «currently applied» line is drawn from `saverSwitch` (raw file) and `saver` (server decision).
- ★**5h «Remaining» cannot exceed the weekly headroom** (2026-09-23 · ★measured «5h headroom 420M» beside «7d headroom 238M»).
  - ⇒ The server sends `head.eff = min(tok, wk.lim - wk.used)` and `head.cap` ('5h'|'7d'); burndown rows and tooltips only read them. When weekly is the limit: «(weekly limit)».
  - ⚠`head.wk.left` is **seconds** (until reset) — token headroom is `wk.lim - wk.used`.
  - ⚠When measuring via module load, `wk` = None is an illusion — call `cs._usage_load(); cs._quota_load()` first.
- ★**The 7d denominator is back-computed from this cycle's data only** (2026-09-23 · at 15% left the screen said 224M ↔ ≈375M by increments).
  - Cause ① «weekly cumulative tokens ÷ cumulative %» mixed a stretch where tokens per 1% doubled (11.8~15.4 → 24.7~26.1M/%) with what came before ② the local weekly sum (`usage().week`) is a **calendar week**, unaware of a mid-week early reset (09-23 16:02, d7 87→0 · `resets_at` unchanged).
  - ⇒ `_qwk_rate()`: a d7 drop in `quota-log.jsonl` = reset. If a reset was seen, simple back-computation as for 5h — `wk.used` = actual tokens since reset, `wk.lim` = used ÷ pct × 100 (`src='cyc'`, pct ≥ 1 only). `wk.lo`/`wk.hi` = pct±0.5 rounding range (for the tooltip). Without a seen reset: walking back from now, the first ≥`QB_WK_DPCT_TARGET` (5) %p step span (else the widest ≥`QB_WK_DPCT` (2) %p span), tokens ÷ Δ% (`'step'`); failing that the old calendar week (`'week'`, ≥8%).
  - ⚠When a reset is visible `cyc` beats `step` — the whole cycle is after the change, so its own sum is exact.
  - ⚠An early reset does not change `resets_at` — assuming «cycle start = resets_at − 7d» piles pre-reset tokens onto 3%. Before, `wk=None` (3% < 8% guard) → the row vanished. ★Measured 17:25: 74.1M since reset · 4% ⇒ lim 1.85B (1.65~2.12B).
  - ★Measured (15:57 reproduction, d7=87, pre-reset cycle): old cumulative 15.15M/% → headroom 197M · `step` 25.86M/% → **336M**.
  - ⚠Never fix the denominator or mix in past cycles — back-compute from in-cycle data only.
- ★**Quota is never derived from the timeline (a screen feature)** (2026-09-23 — third occurrence of the same symptom. Chip `5h 119M` beside burndown `5h 206M`).
  - The cause was **wiring**, not the formula: `quota_burn()` called `agents_timeline()`, which buckets tokens by `step = max(30, span/240)` — **bucket size is set by «how many hours are drawn».** ★Measured: cycle 4.95h → 75 s buckets, the first valid cell started **48 s after** the reset (that much missed). The screen's `curWinTok()` summed the timeline **display range** outright, swinging range 1h 90.0M ↔ 6h 226.1M (gauge 225.3M).
  - ⇒ ① the server sums from `_tok_events(since)`, which returns raw `(ts, tokens)` cut **exactly** at the reset time ② it sends `head.used`, so the screen does no subtraction. ★Measured: boundary loss **+2.14%** recovered in a 1h window · `quota_burn` cold 2.99s → 1.40s · `agents_timeline` response byte-identical (0 regressions).
  - ⚠**Never compute 5h/7d figures on the screen** — read only `BURN.head.used`/`.tok`. Showing no number before warm-up is correct (slipping in another source was the seed of this defect).
  - ⚠`curWinTok()` is **not a cycle sum** — it is the sum over the timeline display range, for the «this-window summary» only. Do not put it back in the quota slot.
  - ⚠With `src=='win'`, `lim = total/pct`, so `used ≡ total` (circular) — the two agreeing is not evidence of correctness. They diverge under `recent`·`anchor`.
- ★**The 5h denominator pairs the current % with tokens at the time that % was first recorded** (2026-09-28).
  - Cause: the official % is an integer, so the same % is recorded many times; dividing by tokens up to the last record (`rows[-1]`) grew the denominator while % stood still, so headroom rose in a sawtooth (★measured 533M at 92% → 529M at 93%, headroom 40.6M ↔ 37.1M).
  - Fix: `burn._qb_step_at` = first record of the current % run · tokens after it are subtracted as `after`. Golden D (staying at 100%) denominator 230M → 136M, unc 0.63 → 0.14.
  - ⚠Never pair with `rows[-1][0]` again.
- ★**The fallback denominator source `live` (ccusage block tokens/Δ%) was removed** (2026-09-23). Order is `win` → `recent` → `anchor`.
  - Cause: local blocks open on the hour (05:00Z), always before the official cycle (06:49Z) — the guard `_ust >= start` was dead code that had never been true.
  - ⚠Do not revive it — even when the guard passes it yields the same value as `win` (local sum over the official cycle / pct). Checked: `quota_burn()` identical before and after removal.
- ★**Burndown «used · Remaining» comes from the gauge alone** (2026-09-23 — recurrence at the same spot).
  - ★Measured at the time: gauge `now_pct` 49% · denominator `hd.lim` 409M · server headroom `hd.tok` 208M (=409×51%), but the screen subtracted `curWinTok()` 79M and printed **`49% · used 79M · headroom 330M`**. 79M is the transcript's own sum, 1/2.5 of the gauge basis (200M).
  - ⇒ `used = hd.lim - hd.tok` · `room = hd.tok`. After the fix `50% · used 204M · headroom 204M` (denominator 408M), matching the gauge.
  - ⚠**Matching the denominator is not enough** — an earlier comment claimed «subtracted from the same denominator, so used + headroom = denominator always holds», which caused this recurrence. `hd.lim` is back-computed from the gauge (`tok/(1-pct)`), so **subtracting a value from another source is meaningless.**
  - ★**The chip was aligned to the same source** (same day, second report) — chip `5h 51% 119M` and the burndown right below, `5h used 206M`, gave different numbers under the same name on one screen. ⇒ `gaugeTok()` derives both 5h·7d from the gauge. Checked: chip `51% 213M` · burndown `used 213M · headroom 205M` (sum 418M).
  - ⚠**Never settle for «the tooltip names the source, so it is fine»** — that excuse sat here as a comment, which is why it was hit twice. The local sum (84M) belongs in the tooltip's `[Reference · local count]` block.
- ★**The saver banner is «always» two lines** (2026-09-22).
  - One-line flex + `flex-wrap` dropped `?` to the next line only when the text got long, so the same banner jumped 33px ↔ 53px.
  - ⇒ Both branches (`sv2`·`on`) are fixed to `<div class=svr1>` (goal·verdict chip·`?`) + `<div class=svr2>` (detail). ★Measured 474×53px (row 1 22 · row 2 18 · `?` 10px from the right).
  - ⚠Do not revert `.saver.on`·`.saver.sv2` to `display:flex` — the symptom returns. ⚠`?` is pinned right by `.svr1 i{margin-left:auto}` (the detail is on row 2, so nothing else pushes it).
- ★**The verdict axis changed from «speed multiple» to «how many minutes the empty time misses the goal» — 5 levels** (2026-09-22).
  - A multiple band (0.8~1.3) **loosens as remaining time grows** — ★measured 1.2× in a 156-minute window ran out 28 min early yet read «on pace» (in a 30-minute window the same multiple is 5 min).
  - ⇒ The source of truth is `pace_lv()` in `saver.py`: minute gap `mins - mins*need/actual` split by `PACE_TOL_MIN/BIG = 10/30` into `lv` +2~-2 («way too fast·fast·on pace·slow·way too slow»); `view_snap` puts `lv`·`earlyMin`·`lvNm` in the snapshot. The screen picks **name and colour only** via `SV_JLV` (`svjfast2`·`svjslow2` = same colour filled to show «way too»). ★Measured `33 min early → way too fast` · 474×57px.
  - ⚠Never re-measure the minute gap on the screen — `svOver` also uses `earlyMin` first. The level must come from the **raw value before rounding**, or it disagrees with the injected text by 1 minute (snapshot `need` is rounded to 2 decimals).
  - ⚠The price of tightening: the chip changes more often (±10 min ≈ ±6% on a 45-min slope). To loosen, raise `PACE_TOL_MIN`; do not go back to multiples.
- ★**The verdict chip alone cannot tell «will the goal hold» — show the empty time against the target too** (2026-09-22).
  - The verdict band is wide («on pace» = 0.8~1.3×), to absorb 45-minute-slope noise, but **anything over 1.0× already misses the goal** — ★measured at 1.2× the chip said «on pace» and empty time was 28 min before the goal.
  - ⇒ `svOver(v)` compares `overAt` with the reference (pace = goal `paceMin` · otherwise reset `leftMin`) and emits «runs out at 17:31 at this rate (28 min early)». Under pace it replaces «N min left»; the margin is appended **only when early** (normal length unchanged).
  - ⚠Do not touch the chip (verdict) — the threshold source of truth is `PACE_TOL_MIN/BIG` in `saver.py` (item above · old `PACE_FAST/OK/SLOW` removed). The screen only adds facts. ⚠Without `overAt` (rate unmeasured) it is silently omitted.
- ★**The verdict is one «colour chip»; «N concurrent recommended» was removed from the screen** (2026-09-22).
  - «on pace» did not say **relative to what**, and the recommended count is set automatically by the hook, so there was no reason to show it.
  - ⇒ `svJudge` (snapshot `lv` · else `goalSay`, else `SV_JREC` fallback) yields one of five, **«fast/on pace/slow/way too slow/verdict pending»**, and `svChip()` draws it (meaning = current ÷ needed, in the chip tooltip). The pace badge is unified to one «needed·current·average» group. ★Measured 474px, one line 33px.
  - ⚠The **recommendation** is gone but the **cap** stays — once a stage is set, «up to N concurrent»·«no subagents» are binding. ⚠With a stage set, `rec` is a cap, not a verdict (do not look it up via `SV_JREC`). ⚠No new chip colours (#e0725f·#6fd39a·#8ab4ff·#8b95a7).
- ★**The saver badge shows three labelled rates: «needed·current·average»** (2026-09-22).
  - Before, only «needed x · actual y», so it was unclear whether «actual» was recent or the window average. They differ: **«current» = `rate_pph` (last 45-minute slope)** · **«average» = `now_pct / elapsed`** (computed by `svLive()`) · «needed» = `need` (to the goal).
  - ⇒ `svRate(v, live)` emits «needed 0.33 · current 0.33 · average 0.33%/min», and `svJudge(v, terse)` then drops «N×» (it is current/needed itself, so it would repeat). Text `.saver` 11.5/10.5 → 12/11 · `.sv2` 11/10.5 → 11.5/11 · chip 11 (one step down from 13/12·12.5/12). ★Measured 474px, one line 32px.
  - ⚠`svJudge` emits **only the 4 known names + «verdict pending»** — passing an unknown `goalSay` through inserts a whole paragraph («could not measure the actual burn rate (…)») and the badge overflows to 99px. ⚠The unit appears once, at the end.
- ★**Why «behind/fast» and needed %/min vanished from the screen — not deleted, only present in the `mode==='pace'` branch** (2026-09-22).
  - The hook snapshot (`.saver-view.json`) kept carrying `goalSay`·`need`·`rate`·`proj`. Once auto became the default that branch was never taken, so they survived only in the tooltip (`head`).
  - ⇒ `svJudge()` (shortens goalSay to «name + N×») · `svRate()` («needed x · actual y%/min», both 2 digits) were added to the headroom/saver-stage branches and to `buildSaver`'s `why`. ★Measured one line, 474px.
  - ⚠Never write new verdict text — the source of truth is `saver.py` (if the screen recomputes, it says something different from what the model was told). ⚠The sv2 badge draws **only one** of `tag || sub` — extend `sub`.
- ★**An empty 5h «Remaining» is not a fault — it has not been back-computed yet** (2026-09-22).
  - Three blockers: `win`·`live` need `QB_HEAD_WARM` (30-min window)·`QB_HEAD_MIN_PCT` (8%); `recent` loses `_qb_lim` on restart because it is **memory-only** ⇒ falls to `src="anchor"` (519,164,200 · 3.2× overestimate) and the screen hides the headroom.
  - ⇒ ① send `head.warm_at` so the screen writes «headroom from N min on» («not measured yet» if warm-up passed and it is still unmeasured) ② persist the back-computed denominator in `qb-lim-cache.json` (`_qb_lim_set`·`_qb_lim_load`) across restarts — TTL 12h · discarded on account mismatch.
  - ⚠Never leave it blank (reads as broken). ⚠Never touch `usage-anchor.json` — it is managed by hand (auto-correction was turned off 09-04).
  - ★**09-27: 30-minute wait removed** — after an account switch discarded the stored denominator, a 22% window was blocked by the 30-min rule and fell to anchor. The error comes from integer %, not elapsed time (±0.5/pct) ⇒ `QB_HEAD_WARM`·`head.warm_at` deleted; only `QB_HEAD_MIN_PCT` (8%) remains. Card text under 8%: «from 8% used» (`383352f`).
    ⚠Do not revive a time wait. ⚠Keep the 8% floor — dividing at 1–2% swings by tens of times.
- ★**After an account switch the previous account's usage leaked into the new account's headroom** (2026-09-27, account A → account B). d7 rose 4→12, so no reset was visible, and `cyc` divided 87.0M counted from the previous account's 03:03 reset (78M of it the previous account's) by 14%: `head.wk.lim` 617M.
  - ⇒ `quota-log.jsonl` rows carry `acct` (uuid) and `_acct_seg` cuts after another account's rows — 7d `_qwk_rate` · 5h `_qb_limit` (on a mid-window switch, tokens from the first new-account row ÷ the %p risen, unc rounding 1/span) · baseline (pre-switch cycles excluded).
  - ⚠Old rows without `acct` (before 09-27) are «unknown» — not cut as a mismatch (the 09-27 switch was hand-tagged on the 09:58:06 row).
  - ⚠7d stays `wk=None` until ≥2%p steps (`QB_WK_DPCT`) accumulate within the new account — never fill it with the calendar-week sum (which includes the previous account's tokens).
    ★09-27: the 5%p floor hid 12→15, so weekly could not be measured ⇒ lowered to 2%p and the error `unc`=1/span (3%p ±33%) is shown. d7 reset detection also only on ≥2%p drops (1%p is jitter). ⚠Do not lower to 1 (±100%).
- ★**After a switch «headroom» stayed at the previous account's value** (2026-10-01 Max 5x → Pro). 5h borrowed the previous account's 5.19M/%, and 7d read a 30→22 drop spanning another account's stretch as a reset, so `cyc` produced 9.08M ÷ 22% = lim 41.3M (±2%).
  - ⇒ No value crosses a switch: 5h uses its own first %p step (`step`, unc 1/span, `win` from 8%p) · no anchor once there is a switch history · 7d `cyc` only for drops within one run · before that «measuring headroom». Meanwhile the usage API is polled every 60 s (`quota_calibrating`, own span under 5%p).
  - ⚠Do not add a plan-ratio prior (Pro 1 · Max 5x 5) — rejected by the owner. ⚠7d still starts from ≥2%p steps (item above).
    ★Same day: «latest ≥2%p» was greedy (14→16 674M ±50% vs 12→15 449M ±33%) ⇒ walk back to the first ≥5%p, else the widest span (live 12→16 ±25%).
  - ★10-01: a ±50% deviation — cutting at the last other-account row let account B's 1.5h (11:53–13:21) erase account A's records since 09-28, leaving a 96→98 (26 min) 2%p span at 19.5M/% ±50% (its own 4→96 span ≈29M/%). ⇒ `_acct_runs` filters other-account rows and splits into contiguous runs; step spans are measured within one run only (`quota-log` rows carry the account; local tokens are already primary-only — item below). With other-account rows after a reset, `step` replaces `cyc`. ⚠Do not revert to cutting at the last other-account row.
  - ★10-01: weekly headroom stuck at 40M — `wk.used` was only pct×per, so while sitting at 98% the headroom froze at 40M (25.3M used since 13:52). ⇒ Tokens after the current %'s first record are added to `used` (per unchanged; `cyc` per also uses tokens up to the first record). `wk.unc` ≥ per/headroom (integer % → ±1%×per). ⚠5h is the opposite (subtracting `after` gives a sawtooth — 09-29 item above) — for 7d one % is ~29M, so freezing is the larger error.
  - ★A manual 5h reset (h5 40→0 within one cycle while `reset5` is unchanged) is cut at the same spot — `_qb_seg` = max(account switch, last ≥2%p drop); only rows/tokens after it feed slope, denominator and unc, and past cycles containing a drop leave the baseline. ⚠A 1%p drop is jitter (09-04 66↔67) — do not lower `QB_DROP_MIN` to 1.
- ★**The burndown 7d row swapped used and headroom** (2026-09-22).
  - Cause: `head.wk` copied the 5h `head.tok` formula (= **remaining headroom** `(100-pct)/100*lim`) and the screen drew it as «used». ★Measured: used 765M showed as 599M, headroom 577M as 762M.
  - ⇒ The server sends only `wk.used = _wtok` (ccusage total); headroom is `lim - used` on the screen (`:5585` · `buildBurn` 7d row).
  - ⚠`%` is **usage** — never put it beside headroom. ⚠`head.tok` and `head.wk.used` mean opposite things (do not copy one formula to the other).
- ★**A stretch where saver mode «ran but changed nothing»** (2026-09-22).
  - Two causes: ① the stage-2 prescription was only «1 concurrent agent», so **useless when only 1 was already running** (★measured 80% · 2.2× needed · empty in 58 min) ② `auto_of` decided by the pace formula but the injected text used the headroom axis (`head_text`), so **the reason for the verdict was not on screen**.
  - ⇒ `saver.py` ① `HOT_X=2.0`·`HOT_PCT=70` — when «too fast» is large, escalate to stage 3 (no new agents · `/clear` advised) ② `auto_head()` rewrites the first line in pace language (empty time · multiple of needed).
  - ⚠Never remove `HOT_PCT` — early in the window the multiple swings with noise (at 2% it flips between 0.3× and 3×; ★measured: p=2 stays stage 0).
- ★**The mid-turn brake was dead code — it ran only when `mode == "pace"`** (2026-09-22).
  - Cause: both mechanisms existed — `saver.py pace_brake()` (PostToolUse · every tool) · `agent-brief.py pace_over()` (PreToolUse `Task|Agent` · **deny** over 2×). But both returned on their first line with `mode != "pace"`, so **in normal (auto) mode they never ran.**
  - ⇒ Condition widened to `("pace","auto")`. The auto snapshot already has `need`·`rate`·`overAt` (`view_snap`). ★Measured: fired immediately, 0.35%/min vs needed 0.14%/min (2.5×).
  - ⚠In auto, do not brake below `HOT_PCT`/`AUTO_HOT_PCT` (70%). ⚠`agent-brief.py` does not import saver, so that value must be **kept in sync by hand**.
- ★**The burndown header has two rows, `5h` / `7d` — do not delete weekly because of a «5h axis only» comment** (2026-09-22).
  Cause: a same-day decision to keep weekly out of the **verdict** was read as removing it from the **display** too, and the weekly row was taken out.
  ⇒ `buildBurn`'s header draws a second row from `hd.wk` (already sent by the server) — `7d used ≈ 741M · Remaining ≈ 606M (45%)`. No new computation; CSS is `.bheadwk` (9.5px/#7b8496) + label `.blab`.
  ⚠**Never put weekly into the saver verdict** — some weeks have only 2–3 work days, which breaks the even-burn premise (`saver.py` auto looks at 5h only).
  ⚠Without `wk` or with `lim<=0` the row is omitted entirely — drawing `0`/`0%` reads as «all used».
- ★**When 5h back-computation dies it silently falls to the old anchor (3.2× overestimate) — first choice is now «local sum aligned to the cycle»** (2026-09-22).
  Cause: the `live` guard `_ust >= start` (`chat_server.py:5557`) almost always fails because the ccusage **local block** (05:00) opens before the official cycle (08:30), and the last good `_qb_lim` lived **only in memory**, so every restart fell to `anchor`. ★Measured `head.src=anchor · lim 519,164,200 · Remaining 462M` (actual use 21M).
  ⇒ Source `win` added **before** `live` (`:5516`) — from the same origin as the front-end `curWinTok()` (`tok` buckets of `agents_timeline()`), only `[start, now]` cells are summed and divided by `now_pct`. Cells straddling the boundary are dropped. Guards (`QB_HEAD_WARM` 30 min · `QB_HEAD_MIN_PCT` 8) unchanged; failing them it falls `live → recent → anchor`.
  ★Verified: `head.src=win · lim 171,475,513 · tok 145,754,186` (`now_pct 15.0` unchanged). Cost cold 2.4 s · warm 0.07 s (covered by `quota_burn`'s 30 s `QBURN_TTL` cache).
  ⚠**Never reverse the order** · ⚠`_qb_lim` is memory-only (never write it to a file) · ⚠a `lim <= 0` guard keeps `live` from overwriting a successful `win`.
- ★**Three token numbers on screen looked at different windows — unified into `curWinTok()` (`web/js/55a-quota-credit.js`)** (2026-09-22).
  Cause: `usage().block` is the **local 5-hour block** (05:00~10:00 that day), whose boundary differs from the official reset cycle (08:30~13:30) — it dragged in pre-reset usage and printed `167M` beside `5h 4%`. ★Measured at the same moment `block.tokens 167,710,746` vs this window `13,507,777`.
  ⇒ `curWinTok()` sums only `TLD.tok` cells after `BURN.cur.start`, and ① the `5h` row (`amt(o2, win)`) ② summary card «this-window tokens» ③ card hover `[Reference · local count]` all use it. Boundary cells are dropped; `null` when unmeasurable.
  ⚠**The `7d` row still uses `week`** — the weekly window is separate. ⚠If falling back to the block value when unmeasurable, **label it «local 5h block»** (unlabelled, one card states two numbers).
- ★**The burndown header first says «how much was used this window», not «what is left»** (2026-09-22).
  Cause: `remaining headroom tokens ≈ 483M (0.97×)` — correct, but not the question asked. `(N×)` is the **headroom axis** (remaining share ÷ remaining time), and after the verdict moved to the goal axis it read on a different axis and only misled.
  ⇒ `this window used ≈ N · Remaining ≈ M` (`:13846`), multiple removed. ★Measured on screen `this window used ≈ 15M · Remaining ≈ 472M`.
  ⚠The server's `room` computation (`:5570`) stays in the API — only the **screen text** was removed.
- ★**With one sample the burndown projection copies «the current value» — a blank that looks like a number** (2026-09-22).
  Cause: `raw = now_pct + slope × remaining time`, where `slope` is least squares over the last 45 min (`QBURN_RATE_W`). With one point in the window the slope is 0 ⇒ right after reset `2%` printed as «2% at reset».
  ⇒ `quota_burn()` measures `n_obs = len(seg)` (`:5445`) **before** adding the anchor and `now`; with `n_obs < 2`, `proj = None` (`:5582`) and the header says «· rate not measured yet» (`:13798`).
  ⚠`over_at`·`over_in`·`cur.rate_pph` were left alone — killing them too would remove the end-of-window warning.
- ★**The headroom axis and goal axis have opposite signs — chaining them as fallbacks flips the verdict** (2026-09-22).
  Cause: the headroom multiple assumes «leaving some is good», goal burn assumes «use it all». Right after reset `p=2 · left=298 min` read as headroom **0.99× (= tight)**, so **every window opened in saver stage 1** — the goal axis reads the same numbers as «launch more» (first prompt's 2% is 3× the even line).
  ⇒ Cut both headroom-axis fallbacks in `auto_of` (`saver.py:332`) — ① when `rate` is unmeasured (0 samples right after reset), **withhold the verdict** instead of using the headroom axis (stage 0 · 2 concurrent · «could not measure the actual burn rate») ② `0 if rec >= 3 else stage_of(...)` ⇒ `rec >= 2` (the stage is handed to the headroom axis only when «too fast»).
  ⇒ The header leaked too — the unknown-rate stretch fell to `VIEW_SLACK_HEAD` («a little tight to spend»), so `VIEW_NORATE_HEAD` («burn rate not measured yet · goal N%») was added (`view_snap`).
  ★Measured `auto_of(p,left,rate,goal=100)`: window start at pace `(2,298,0.33) → stage 0` · window start at 3× `(2,298,1.0) → stage 1` (real overspeed still braked) · end `(87,1,0.7) → stage 0 · wrap up` · `100% → stage 4` special case kept.
  ⚠**Never revert to `rec >= 3`** · ⚠**never call `stage_of` in the unknown-rate branch** — either brings the symptom straight back.
- ★**At the end (`PACE_END_MIN=5`) `rec` is a brake value, not a verdict — the screen printed it as a recommendation** (2026-09-22).
  Cause: `need = (goal - p) / remaining min` diverges near 0 and would always be «4 or more», so `pace_rec` stops judging and returns `1`; the screen printed that `1` as «1 concurrent recommended» — **the opposite advice (launch only one) while behind**. ★Measured at `p=84 · left=4`: `need=4.0` vs `rate=0.63`.
  ⇒ The snapshot carries an `end` key, and **both** the head (`VIEW_GOAL_END_HEAD`) and the viewer label (`svfree` branch of `svParts`) show «wrap up» instead of a count.
  ⇒ End text «almost there» ⇒ «time is up» — at 84% «arrived» reads as goal achieved (it was originally pace mode's *arrival time* text). ★Measured on screen «headroom · 88% / goal 100% · wrap up».
  ⚠**The normal stretch is unchanged** — «N concurrent recommended» in a 40-minute reproduction. Do not widen the end branch into the general path.
- ★**Text for `proj_pct` over 100 is built in one place only, `proj_say()` (`saver.py:314`)** (2026-09-22).
  Cause: if each consumer prints over-100 projections its own way, screen and commands diverge again — `status` (`saver-mode.sh:137`)·`goal`·`VIEW_GOAL_HEAD` (`saver.py:971`)·`projSay` in `.saver-view.json` **all use this function**.
  ⇒ Text is «at this rate it runs out before reset (in about N min)». ★Measured p=80 · 5.0%/min · 30 min ⇒ `proj_pct=230`, text «in about 4 min».
  ⚠**Never clamp the raw `proj` number** — the viewer reads it. Only the text is clamped.
- ★**stage>0 badges now carry the goal too — only the `legacyBadge` path had the old text** (2026-09-22).
  Cause: `legacyBadge` in `buildSaver` (`web/js/55-saver-quota.js`), unlike the stage-0 auto label, put only the limit in `why`, mixing goal and headroom axes on one screen.
  ⇒ `why` ordered as «limit N% · goal N% · cap». ★Measured `stage1+goal100` ⇒ «5h limit 55% · goal 100% · 2 agents at once».
  ⚠**Never add it to manual (`mode === 'on'`)** — manual is unrelated to limit and goal, and `why` is «turned on manually», so a goal there implies a false cause.
- ★**`/saver goal` output split from `status`** (2026-09-22).
  Cause: both commands printed the same block, so after changing the goal the output did not show what changed.
  ⇒ Three goal-specific lines in `saver-mode.sh:37-66` — ① goal value + how to change/turn off ② now·reset·at this rate·verdict ③ one weekly line.
  ⚠**`status` was not touched** — if both were identical there would be no reason for two commands.
- ★**The snapshot must carry «the axis used for the verdict» — the label lacked the goal** (2026-09-22).
  Cause: the auto verdict moved to the goal-burn axis, but `.saver-view.json` dropped by the hook was **still the old headroom axis** — no `goal` key · `need` null · `head` = «headroom 4.9×». Only `/saver status` used the new text, so **screen and command showed different axes**.
  ⇒ `saver.py` `view_snap` adds `goal`·`proj`·`goalSay` + a real `need` + switches to `VIEW_GOAL_HEAD` only for stage-0 auto on the goal axis. Computation is unified in `goal_need`·`proj_pct`, so `auto_of` and `saver-mode.sh` use **the same function**.
  ⇒ Viewer `svParts` only prefixes `sub` with «goal N%». ★Measured render «headroom · 76%» / «goal 100% · 4 concurrent recommended» (474×28px · one line).
  ⚠**Never put `goalSay` («far behind (0.3× of needed)») in the label** — it overflows at the sidebar's 10.5px font. It is in the tooltip (full `head`).
  ⚠**Silently omit when the key is missing** — the label must not break when only one side is deployed.
  ⚠**Never recompute the verdict in the viewer** — the source of truth is `saver.py` (fixed twice in one day for this reason).
- ★**«remaining headroom tokens» was divided by a fixed denominator — 3.4× overestimate** (2026-09-22).
  Cause: `head.tok` divided by `blockLimitTokens` in `usage-anchor.json` (09-04 calibration, 519,164,200). ⚠**A fixed denominator is impossible in principle** — the limit is metered by **model weighting**, not raw tokens (cache reads 0.1× · Opus the other way). ★Observed max block 617,242,503 vs same-day back-computed 135M = **4.5× spread**.
  ⇒ Back-compute **on the fly** inside `quota_burn()` (not stored). ⚠ccusage blocks and the official cycle have different anchors and **are always misaligned** (★measured 90 min: block `[05:00,10:00]` vs official `[03:30,08:30]`) — requiring equal windows falls back almost always. ⇒ Measure Δtokens/Δ% **over the overlap only** (`_p0` = last pct in `rows` with `t <= _ust`). ★**519,164,200 ⇒ 173,882,362** · `head.tok` 290,731,952 ⇒ **92,157,651** · `src="live"`.
  ⚠If the block opened before the cycle (`_ust < start`), the previous cycle's share is mixed in and cannot be split — then hold the last good `_qb_lim` (**memory-only** · TTL 12h · `src="recent"`). ⚠Never persist `_qb_lim` to a file (auto-correction on the `usage()` path was turned off 09-04). ⚠Never drop the `≈` in screen text — cache weights are not published.
- ★**Cumulative % removed from the auto verdict — the only axis is «headroom vs remaining time»** (2026-09-22).
  Cause: the floor line in `saver.py` `stage_of` (`if st == 0 and floor and p >= ON: st = 1`) raised to stage 1 whenever `p >= 50`, even with 3× headroom. The caller gate `p >= ON` was the opposite defect — burning fast early in the window with headroom under 1.0 stayed silent while `p < 50`. ★Measured 5h 55% · 42 min to reset · headroom 3.2×, yet verdict «stage 1 · 2 concurrent».
  ⇒ Removed the floor line, the `floor` parameter and the `ON = 50` constant; the 3 gates became `stage_of(p, left_min) > 0`. The `p >= 100 ⇒ 4` special case stays.
  ⚠`_stage_by_pct` is **a fallback only for «time to reset unknown»** — do not revive it as the main path.
- ★**The auto verdict axis became «goal burn» — default goal 100%** (2026-09-22).
  Cause: the headroom multiple **ignores the current rate** — it disagrees with the visible «79% at reset at this rate», and cannot see **under-using and leaving quota** as a defect.
  ⇒ `saver.py` gains `goal_of()` (`~/.claude/hooks/.saver-goal.json` · **100** if absent) and `auto_of(p, left_min, rate, goal)`, passing `need = (goal - p) / left_min` **straight into the existing `pace_rec`** (including the end-of-window `PACE_END_MIN` brake). Command: `/saver goal <0~100|off>`.
  ⇒ Three fallbacks — `goal off` · rate/remaining time unknown · after `p >= goal` is reached ⇒ all use the headroom axis above.
  ⚠**Never store the goal in `.saver-force.json`** — `pace_of` reads that file's **mtime as the goal anchor** (`saver.py:183`) and pace goes wrong. Hence a separate file.
  ⚠The `mode == "pace"` branch was not touched — it is a separate feature that sets a goal **time** other than the reset.
  Weekly appears only as **one number line** in `status`·`goal` output (no multiple · not in the verdict) — an input for a person to lower `goal`.
- ★**The verdict label is drawn from live values, not the snapshot — `svParts()`** (2026-09-22).
  Cause: the label drew `state.saverView` (← `.saver-view.json`) as-is, and that file is refreshed **only on prompt submit by the hook** — the 5h bar polls every 2.5 s, so they are **always misaligned**. ★Measured 07:50 label «headroom · 55%» vs bar `59%`.
  ⇒ New `svLive()`; `svParts(v, nowS, live)` swaps **only the displayed numbers** (% · minutes left) for live `QLAST.q.five_hour`. Fallback: burndown (`BURN.cur`) ⇒ `SV` snapshot.
  ⚠**Stage and recommended count stay as in the snapshot — never duplicate the verdict formula in JS.** The source of truth is `saver.py`; two copies drift.
  ⚠Never override a snapshot `pct == null` («limit unknown») with a live value.
- ★**The weekly axis was removed from both verdict and screen — introduced and withdrawn the same day** (2026-09-22).
  Cause: **the headroom multiple assumes «even use across the whole window»**; with only 2–3 work days a week, being faster than the even line on work days is normal, so the weekly multiple always reads «short». A 5-hour window is actually attended for those five hours, so the premise holds there.
  ⇒ ① Removed: `ON_WK`·`gate_on()` in `saver.py` + 4 callers restored to `p >= ON` · `seven_day`/`wk` passing in `saver-mode.sh` · `head["tight"]`·`hwk["room"]` in `chat_server.py` · JS `buildBurn()` weekly rendering · CSS `.btight` ② Kept: `head["wk"]` in `/api/quota/burn` (tokens·limit·%·minutes left) · `room_min(wk=None)`·`WIN_7D`·`_hm` day-unit plumbing in `saver.py`.
  ⚠**Never revive weekly in the default screen or default verdict** — reviving it requires a form that knows work days. If separate tracking is needed it will be requested then; read the value from `head.wk` in `/api/quota/burn`.
- ★**The pace goal revived at midnight, and the verdict diverged right before the goal — `saver.py`** (2026-09-22).
  Cause: ① `pace_of` rebuilt `HH:MM` on **today's date** from `tm_year/mon/mday` (`.saver-force.json` has no date). ★Measured at 05:57: «goal 19:00 · now 3% · far behind — launch 4 or more». ② `need` (remaining % / remaining min) diverged as remaining min → 0, always giving **4**.
  ⇒ ① use `.saver-force.json`'s **mtime as the «moment the goal was set» anchor**, and the goal is **the first `HH:MM` after the anchor** (better than a `day` field: a date alone cannot tell «02:00 set at 23:00» · file format unchanged, fully backward compatible) ② under **5 minutes** left, inject `PACE_END` instead of `PACE_ONLY` (1 concurrent · «wrap up, start nothing new»).
  ⚠The anchor is the mtime, so **a touch/restore for any other reason re-bases the goal at that moment** (even with identical content). ⚠Do not revert `pace_rec`'s «actual/needed» axis (comparing with the even line gave inverted verdicts). ⚠The `python3 -c "..."` in `saver-mode.sh` status is inside shell **double quotes**, so backticks in its comments execute as commands.
- ★**The hook told the model to re-check quota via `/api/state` — 3.7MB into the context** (2026-09-22).
  Cause: `TAIL_AUTO` in `~/.claude/hooks/saver.py` hard-coded `curl /api/state` as the re-check command. A model following it reads 3.7MB «just to look at quota».
  ⇒ Switched to `/api/quota/burn` — ★the same values in **1,401B** (1/2,664). Field names differ: `quota.five_hour.pct` ⇒ `cur.now_pct`, `leftSec` ⇒ `cur.left`.
  ⚠`TAIL_AUTO` is a `%` format string — **never put a literal `%` in it** (`TypeError`; the hook dies on every prompt). After editing, actually run `TAIL_AUTO % "X"` before committing.
- ★**Saver verdicts need the same «inputs» — the server did not read the hook's manual switch** (2026-09-21).
  Cause: `_saver_state()` knew only `on`/`off` in `.saver-force.json` and **not `pace`**, so while the hook said «use it all by 19:00» the server saw only quota 56% > 50% and turned on «saver stage 1».
  ⇒ ① read the mode via `_saver_force()` (5 s TTL cache) and record `pace`/`manual`/`off`/`quota`/`auto` in `why` ② **for pace, the hook snapshot is the source of truth for the stage** — the hook swaps the denominator to «until the goal» and recomputes the stage (`stage_of(p, pace_min, floor=False)`); the server lacks that denominator, so never recompute.
  ⚠**Never force the stage to 0 because it is pace** — burning faster than the goal sets a stage in pace too (the model is throttled while the screen says otherwise). ⚠With a stage set, `rec`'s **meaning flips** — `view_snap` checks `elif stage: rec = CAP[stage]` before the pace branch (a **cap**, not a pace verdict). ⚠Without a snapshot, or one older than 120 s, do not turn it on (unknown does not block).
- ★**`/api/state` with `since=0` is 3.7MB — the hook hit its 3 s timeout and dropped quota to «unknown»** (2026-09-21).
  Cause: `saver.py`'s `pct()` hit this endpoint on every prompt without `since`. ★Measured single 0.13~0.51 s (cold 1.87 s), but **8 concurrent all cut off at 3 s** — each builds its own 3.7MB.
  ⇒ `_state_body(since, nc)` **shares the body for 1 s for identical arguments** (8 concurrent 0.58 s ⇒ 0.05 s). ⚠Never raise the TTL to the poll interval (2.5 s) or above. ⚠**Never build inside the lock** (reverted the same day, 2026-09-21) — `state()` calls `claude agents --json`·`ps`·`pmset`. Inside the lock **every request hung on one lock and `/api/state` took 90 s** (the key is `(since, nc)`, so hook and browser shared the lock without sharing the cache). ⇒ The lock guards only the dict; build outside, and while the same key is being built serve the stale body (stale-while-revalidate · 90 s ⇒ 0.096 s).
- ★**Pace mode only talked and never braked — «real brakes» at two hook points** (2026-09-21).
  Cause: the verdict was one `UserPromptSubmit` injection line, with no guarantee the model follows it, and no update point during one long turn (★subagents were 52.5% of a 36-hour bill — 540M vs main 489M).
  ⇒ Above **2×** actual/needed rate: ① `agent-brief.py` blocks `Task|Agent` with `permissionDecision:"deny"` (numbers and empty time in the reason) ② `saver.py` `pace_brake()` injects one line «wrap up, start nothing new» via `PostToolUse` (**only when** the 2/3/4× level rises · min 120 s apart · state in the existing session file `pb`/`pbt`).
  ⚠**Never remove the escape hatch** — after more than 2 consecutive denials the next one passes (`.agent-brake.json`). Blocked forever, the requested work itself never proceeds.
  ⚠Without a snapshot (`.saver-view.json`) or one older than 120 s, **neither block nor speak** (unmeasured is not «fast»). ⚠Running agents are never killed — only new launches are blocked. ⚠Never make HTTP calls on this path (one snapshot file read, nothing more).
- ★**The goal-burn (pace) verdict ignored «actual rate» — `saver.py` `pace_rec`** (2026-09-21 18:17).
  Cause: it compared `need` alone (= remaining % ÷ minutes to goal · «what must be used») with the even line 0.33%/min — a high `need` does not mean «under-used», only that **the goal is more aggressive than the even line**. ★Measured at that time needed 0.56 vs actual 1.32%/min (2.3×), yet the verdict was «far behind — 4 or more».
  ⇒ The axis became the **`actual/needed` ratio** (>1.3 slow down·1 concurrent · 0.8~1.3 keep·2 · <0.8 3 · <0.5 4 — with ratio r it runs out at `1/r` of the remaining time, and `rate_pph` is a 5-minute sample, so narrower than ±30% swings with noise). The first line starts «at this rate it runs out at HH:MM».
  ⇒ Actual rate is `rate_pph`·`proj.over_at` from `/api/quota/burn`. Moving `pct()` wholesale to it **also fixed the 3.7MB timeout** (`/api/state` remains as fallback).
  ⚠**No verdict when the rate is unmeasured** — `actual=None` is neutral (2 concurrent); never revert to the old need-only text. ⚠The badge uses the snapshot's `rate`·`overAt` as-is — never recompute on screen.
  ⚠`saver-mode.sh` status execs saver.py **with `main()` stripped** — if the stripped string (`'\ntry:\n    main()'`) does not match, the hook eats stdin and status always ends with «could not read the viewer» (old product name in the message).
- ★**A saver display without affordance gets reported as broken — `.burn`·`.saver`** (2026-09-21).
  Collapsed by default + a lone `▾` glyph is not a control; laying the full text in the same 10px grey as `.bhead` buries it; `#6d7a8c`/9.5px (**3.2~4.0:1**) is not design, just unreadable.
  ⇒ ① expanded by default (⚠`localStorage` **3 states** — only a missing key expands; `'0'` is the viewer's choice, never override it) ② the full text is built in one place, `svParts()`, so the badge (`.saver.sv2`) and full-text row (`.svrow`) share colour ③ hierarchy kept, only the floor raised one step (official #cfd8e6 12.2 > estimate #b9c4d4 9.9 > body #a8b3c4 8.2 > aside #8b95a7 5.8 · min 10.5px).
  ⚠**`body.svon` and the pulse are for saver «stages» only** — on in headroom/off states, the whole screen looks like power saving when it is not. ⚠The hook (`saver.py`) is the verdict's source of truth — assemble from structured keys, never parse `head`. ⚠Never lower the brightness again.
  ④ The near-empty red (`.bwarn`) **never applied until 2026-09-21 because the selector was a descendant (`.burn .bwarn`)** — `bwarn` sits on `.burn` itself. Fixed to `.burn.bwarn .bpj`, so **only the overflowing number** is red (`.bsoon` yellow = «when will it run out», red = «the estimate exceeds 100%» — do not merge).
- ★**The saver display reads the snapshot file; never import the hook — `_saver_view()`** (2026-09-21).
  `~/.claude/hooks/saver.py` **runs the hook body at module level** (reads stdin and injects) — importing it turns the server into the hook.
  ⇒ Read only `/Users/<user>/.claude/hooks/.saver-view.json` dropped by the hook (the server's `_saver_state` does not know pace mode).
  ⚠**Hard-code the path as absolute** — this file's `HOME` is `~/.mailbox-mcp` (`:42`). With `expanduser` it looks in the wrong place.
- ★**Quota burndown — never split cycles by `reset5` «as a string»** (2026-09-21). `GET /api/quota/burn`
  (`quota_burn()`) is the first reader of `quota-log.jsonl`, which was previously write-only — current cycle curve + linear
  extrapolation to reset + median of the last 6 cycles.
  - ⚠Even within one cycle `reset5` jitters by seconds (★measured: `23:29:59.7` ↔ `23:30:00.2` · in 30 days /
    1,821 lines, 66 «distinct minute values» → 36 real cycles). ⇒ Split with **±120 s tolerance**.
  - ⚠**Append** `(now, now_pct)` to the right of the slope window (45 min). % is a step function recorded only on change;
    without it, after 45 idle minutes the old slope remains and falsely says «empty soon».
  - ⚠If the cycle is already over (`now > reset`), **hide the panel** with `ok:false, why:"stale"` — extrapolating a past cycle
    as current is not an estimate but a lie. Screen text is fixed to «at this rate».
  - Not fully parsed: `_tail_incr` incremental tail + 30 s TTL cache (★measured recompute 0.6ms). Names are
    `_qburn`/`QBURN_*` — `_burn`/`BURN_MIN` (tokens per minute) are **something else**.
- ★**Quantile band — the band fails «both ways»** (2026-09-21 · one median line → p25~p75 band).
  - ⚠Too wide or too narrow carries no information. ★Measured: 4 of the last 6 cycles sat at 0% throughout, so **width
    0.0%p everywhere** — invisible when drawn, yet it takes a legend slot. ⇒ With grid samples under `QBURN_BAND_N` (5) ·
    median width over `QBURN_BAND_W` (40%p) · max width under `QBURN_BAND_MIN` (1%p), **drop the band** and keep only the
    median. The reason goes out as `base.why` (`n`/`wide`/`flat`) and the legend writes «… · band omitted».
  - ⚠Decided **on the server only** — if JS holds the thresholds too, they diverge. ★Measured recompute 1.1ms.
- ★**The only basis for expressing «Remaining» in tokens is `blockLimitTokens`** (2026-09-21). That value in
  `usage-anchor.json` is a **calibration denominator** back-computed from the official `/usage` %, and the 5h gauge uses
  the same ⇒ it shares an axis with `h5` (1% ≈ 5.19M · ★measured 519,164,200).
  - ⚠**Never convert to a request count.** `_burn` measures **context size** per request, not consumption (cache reads
    0.1×). Dividing gives a baseless number — not showing it is correct.
  - ⚠Screen text has never dropped `≈` and is drawn dimmer than official values via `.bhead`. Calibration is fixed as of 09-04.
- ★**Do not set the poll interval from 5h** (2026-09-11).
  On `enterprise_usage_based` 5h is permanently 0%, so `_quota_interval()` always fell to `QUOTA_SLOW_S` (300 s), while
  what actually moves is credit — ★measured: screen 26.435% (300 s old) vs API at the same time 27.145% ($1.42 in 5 min).
  ⇒ Seats with credit poll every **60 s**. ⚠The 1% gap was **age**, not rounding.
- ★**Live credit during 429 stretches comes from «response headers»** (2026-09-11). The CLI rarely calls
  `/api/oauth/usage` — it reads `anthropic-ratelimit-unified-*` attached to ordinary model-call responses (header name found
  28 times in the binary). That is why only the CLI was live.
  ⇒ `_quota_probe_hdr()` — one haiku call with `max_tokens 1` reads `overage-utilization`.
  - ⚠Header values are **0~1 ratios** (0.25 = 25% · cross-checked against the official API's 24.845% at the same moment).
  - ⚠**It is a paid call** (≈ $0.00002 each) — throttled by `QUOTA_HDR_EVERY_S` (120 s) and used only under 429.
  - ⚠The amount is not in the header — it is an approximation (ratio × monthly limit), so the screen adds `≈`. 5h/weekly are
    not read (only one representative claim is present; misreading an empty slot as 0 would break saver mode).
- ★**Credit (amount) exists only in the official API — that row states its own age** (2026-09-11).
  The OMC cache has only 5h/weekly, so during 429 stretches 5h stayed fresh via OMC while **only the amount froze**, and the
  payload age (`q.age`) kept refreshing, so the screen did not show it (5% shown, actual 19.02%).
  ⇒ Stamp `extra.at` (time received); `creditRow` shows «value from N min ago». ⚠An OMC fallback cannot fix this.
- ★**429 backoff cap 900→300** (2026-09-11, measured). After 6.5 min without knocking, a single call got **200** (extra 19.02%);
  10 calls at 15 s intervals right after were **all 429** (135 s). ⇒ The window opens when left alone and closes when hammered —
  what is needed is «one shot after a rest», and 5 min was enough. ⚠900 leaves the credit value 15 min stale (no other source).
- ★**The quota cache is bound to the account** (2026-09-11).
  After switching accounts `quota-cache.json` survived and kept showing **the previous account's `5h 100%`**.
  ⇒ Save and load stamp `acct` (= `oauthAccount.accountUuid` in `~/.claude.json`); discard on mismatch.
  - ★The switch is visible in the log: 11:12 `h5=5%` → rising to 13:50 `h5=100%` → 13:55 `h5=null d7=null`.
    **A successful response with both windows `null` is not a failed lookup but «no usage in this window»** (= new account).
  - ⚠The keychain (`Claude Code-credentials`) has no account identifier — only tokens, tier and scopes.
  - ⚠If either side is unknown, do not discard (unknown ≠ mismatch). Only the uuid is used — email never goes on screen.
  - ⚠**Local totals (ccusage) tokens/$ cannot be split by account.** Transcript lines carry no account identifier
    (★measured: only `userType` among top-level keys). They are this machine's whole history, including the previous account's sessions.
- ★**The quota cache is merged «per slot»** (2026-09-10).
  `_quota_fetch()` replaced the new response `out` wholesale, so one response without `five_hour`
  **wiped both the 5h·7d gauges** (only `extra` left in the cache).
  ⇒ Slots missing from the new response are carried over **while their window has not ended** (`resets_at > now`). Ended windows are dropped.
  - ★Measured 09-10 14:10 `h5:100 d7:58` → 14:15 response with both slots null → cache had only `{"extra":…}`.
  - ⚠Carried slots get `keptAt` (time of last real measurement) — `at` is refreshed, so `q.age` cannot catch staleness and
    the screen would show an old % as «just now». `one()` uses `keptAt` to write «value from N min ago».
  - ⚠Slots without `resets_at` (7d) are carried for at most **6 hours** from `keptAt`. `keptAt` is carried, never refreshed.
- ★**The credit row is drawn separately from the 5-hour limit** (2026-09-10).
  The credit row lived inside `buildQuota()`, so when the quota lookup hit 429 the whole block fell to `buildQuotaLocal()`
  and **the credit row vanished with it** — though it is a separate field.
  ⇒ Split out as `creditRow(q)`, called from both paths (drawn whenever `extra` exists).
  - ★Measured 09-10: `five_hour` empty with `err:"HTTPError 429"` while `extra` was fine (4.8% · $9.69/$200).
  - ⚠The badge (`#credit`) still turns on only at **5h 100%** — `is_enabled` means «available», not «in use».
  - ⚠Wording split (2026-09-11): the gauge row says only «Credits»; **the status text «credit mode» appears only on the badge**.
- ★**The saver badge shows stage and cap** (2026-09-10).
  Before, it said only «saver mode», so **how many agents may run now** was not on screen.
  ⇒ `_saver_state()` sends `stage`·`cap` and `buildSaver` writes «saver stage 3 · no agents».
  - ⚠**The source of truth is `STAGES`·`CAP` in `~/.claude/hooks/saver.py`.** `SAVER_STAGES`·`SAVER_CAP` here are copies;
    changing only one makes the screen and the model say different things (the same trap already hit with the `pct()` guard).
  - Manual mode has stages too (`/saver on 2` → `.saver-force.json {"mode":"on","stage":2}`). Default stage 3.
  - ★Measured: auto verdict `49→off · 50→1 (2) · 75→2 (1) · 85→3 (0) · 100→4 (wrap up)` · screen «saver stage 3 · turned on manually · no agents».
- ★**Quota 429 in 41 of 300 lines · screen up to 1510 s (25 min) stale** (2026-09-09, measured).
  - Cause: ① `QUOTA_STEPS` (80,60)(50,120) put 60 s dense polling on the most common 80% band, burning the request-count
    cap itself (a request-count limit, not usage — measured above). ② `_wait_hint`'s exponent was capped at
    `min(fail,4)` (15×2⁴=240), so even with consecutive 429s the retry interval was **fixed at 240 s forever**.
  - ⇒ ① `QUOTA_STEPS` → (90,60)(70,120)(else 300) — dense stretch narrowed to 90%+. ② `_wait_hint`
    exponent `min(fail,6)` · `QUOTA_MAX_BACKOFF` 300→900 — really grows 30·60·120·240·480·900 s.
    ③ `_quota_from_omc(fresh_s=...)` — during backoff the trusted OMC age widens to `fail`×180 s (max 1800).
  - ⚠The 900 s cap is safe thanks to `warn_once`'s `_alive` carry-over (added the same day) — before that the `SOFT_WIN_S`
    (900) window prevented raising it. **If that carry-over is reverted, revert this 900 s too.**
  - ⚠During sustained 429 (all blocked) «screen age within 5 min» cannot hold — retries must slow to 15 min for the window to
    rest, so this trade-off is intended (verified by module load only, no API calls).
- ★**Credit (extra usage) row** (2026-09-09).
  It was already in the same response (`GET /api/oauth/usage`), `extra_usage{is_enabled, monthly_limit, used_credits,
  utilization, currency, disabled_reason}`, but `_quota_fetch` dropped it.
  ⇒ Carried as `quota.extra{pct,used,limit,cur}`; `buildQuota` draws one more row under 5h·7d.
  - ⚠**Amounts are cents** — the CLI passes `spendLimitCents`·`usedCents` as-is. Divide by 100.
  - ⚠The OMC cache has no such slot. When OMC wins and our `extra` is not added on top, the row flickers away.
  - ★Measured: `pct 47.58 · used 4758 · limit 10000` → screen «Credits 48% · US$47.58 / US$100.00 · US$52.42 left».
  - The **badge** (`#credit` · `buildCredit`) is on only while «money is being spent now»: `extra` present **and**
    5h at 100%. ⚠Turning it on from `is_enabled` alone is a lie — that means «enabled», not «in use».
  - ⚠Saver mode **still applies** during credit stretches (owner decision 2026-09-09).
    Do not propose loosening `saver.py` thresholds because of credit.
- ★★**Saver mode — unless «told» it has ended, the model keeps working in saver mode. And the hook and the screen must
  hold «the same guard» for that decision** (2026-09-08).
  - **The cause was the hook's «chance to run».** `UserPromptSubmit` runs only on prompt submit. ★Measured: the 5-hour window
    reset at **15:59** but `07e9bc3a`'s saver record stayed **14:55 · on=true** — that session crossed the reset **within one
    turn**, so the release had nowhere to land, and the context held only the 14:55
    the saver-mode notice «do not launch new subagents», so it worked directly for the whole turn.
  - ⇒ `~/.claude/hooks/saver.py` **also handles `PostToolUse`** (on that event it checks **release only**).
    ⚠A comment in that file **asserting without checking** that «`UserPromptSubmit` is the only hook supporting
      `additionalContext`, so there is no mid-turn update path» kept this defect alive for 6 days.
      Per the docs `PostToolUse`·`Stop` also support `additionalContext`, and the text goes to the model
      (hooks.md#posttooluse-decision-control). `systemMessage` is seen **by the user only** — do not mix the two fields.
    ★Live check: **right after** registering the hook, a marker was planted in a running session (`be858dca`) and one tool call
      injected the release on the spot — the file's caveat «only applies to sessions started after registering this hook» did
      not hold, at least here. `dadfe88a` also really received the release at 16:09.
  - ⚠**Cost** — `PostToolUse` runs on every tool call. Cut cheapest first: if the session record is not `on`, read one file
    and stop (no HTTP · ★measured 20-run mean 48ms); only when `on`, query at 60 s intervals.
  - ⚠★**Never turn saver mode on from «the % of an already-ended window» — this file needs the same guard.**
    `quota()` values are cached (`age`). Right after a reset they report **the pre-reset %** for a while, and in that gap session
    `dadfe88a` newly received saver mode **at 16:00, 1 minute after the reset** (actual pct 0). An age threshold cannot cut it —
    even 60 s was already wrong. ⇒ `_saver_state(pct, left)` treats pct as **unknown when `leftSec <= 0`**.
    6 unit cases: `leftSec` 0·-12 → off (unknown) · **5 (just before reset) → stays on** (small but positive is normal).
    ⚠**The hook's `pct()` has the same guard — changing only one makes the screen and the model disagree**
      (that is what «use the same inputs as the hook» in the comment above `buildSaver` means).
  - **The question mark explains «trigger → hold → release»** (2026-09-08). Before, it listed only «injected rules», so what to
    obey was clear but **why it turned on and when it ends** was not.
    ⚠The threshold comes from the server's `saver.th` (= `SAVER_ON`). Hard-coding `85` on screen drifts when the constant changes.
  - **The background changes too** — the badge sits at the **very bottom** of the sidebar (`margin-top:auto`) and gets missed.
    `body.svon` is toggled **at the same spot** as `buildSaver` (kept apart, one side lingers).
    ⚠**Painting only `body` changes half the screen.** ★Measured: the only elements actually painting the viewport are `body` (100%)
      and `aside.lside` (20% · `#12161d`) — panels with their own background cover the body tint.
      `.wpn` exists only in multi-pane views (the timeline view has **0** `.wpn`).
    ⚠No new colours (colour convention above `.hlb`) — the badge pulse's `rgba(232,198,122,…)` with lower alpha is **layered**
      as `background-image` (replacing the hex leaves seams with other containers sharing `#0d1014`). Keep alpha low — on this
      screen state is read from bar colours.
  - ⚠**Screen verification misfired twice.** ⓐ a screenshot after calling `buildSaver` captured the off state because
    **the poll (2.5 s) reverted it to the server value** in between ⇒ while checking, temporarily override `buildSaver` to hold the
    state, then restore. ⓑ wrapping a playwright `evaluate` in `Promise` + `setTimeout` threw inside the callback and **never
    finished** (that was the console error too) ⇒ write it synchronously.
- ★**`resets_at` jitters by under a second around the minute** (2026-10-05: `…01:59:59.600Z` and `…02:00:00.008Z` on consecutive fetches). Views truncate to HH:MM, so the card, status bar and drawer flipped between 10:59 and 11:00. ⇒ `quota()` (`sidereus/quota.py`) rounds to the whole minute once, and `leftSec` uses the rounded value (`tests/test_quota_reset_round.py`). ⚠Do not round per view — that brings back views that disagree.
- ★**auto mode: `saver.stage` comes from the hook's fresh snapshot, not the % table** (2026-10-05: settings «currently applied · stage 2» vs status bar «saver stage 1» at 83%).
  - Cause: the hook stages auto by goal pace (`auto_of`); `_saver_state` used `SAVER_STAGES` only, while the status bar read `saverView.stage`.
  - ⇒ `_saver_hook_stage("auto")` wins when fresh (≤ `SAVER_VIEW_STALE`); the table is the fallback (`tests/test_saver.py` `test_auto_follows_fresh_hook_stage`).
  - ⚠Recomputing the stage on the server again splits the two views — the hook is the source of truth (same rule as `pace`).
- ★**7d «used» must not depend on the 5h cycle** (2026-10-05: status bar `used 483M` flipped to `used ≈ 506M`).
  - Cause: `cur.wk_used_local` was set only when the 5h `head` existed; at h5 0% (no denominator) or a just-ended 5h cycle («stale», no `cur`) it was null and `use()` fell back to `burnWkEst`.
  - ⇒ `_qb_current` takes it from `_qb_week` directly; `_qb_body` also puts it on top-level `wk.used_local`; `60-statusbar.js` reads `cur` then `wk` (`tests/test_qb_wk_used.py`).
  - ★Not a wrong cycle start: account B went d7 100 -> 0 at 10-05 00:07 with `resets_at` still 10-05 19:00 (mid-window reset, per 1% 5.9M -> 26M). The official 18% counts from that drop: 495M since it vs 3.26B since `resets_at − 7d` (other account + pre-reset usage).
  - ⚠Do not anchor 7d «used» at `resets_at − 7d` — an early reset keeps `resets_at` (see «7d denominator» above).
- **«Main account» (UIS `mbMainAcct`) changes display and the status-bar saver verdict only** (`40b` `mainAcct`, `55a` `knQ`).
  - Cause: BURN, plan and local token estimates are computed for the primary only; `quota.accounts` rows carry `{pct, resets_at}` and nothing else.
  - ⇒ The status bar 5h/7d cells read `knQ`; tokens and «left ≈» hide while main is set; projection and 100% ETA read `burnFor()` (`55b` `BURNM`, fetched with `?dir=` main's dir).
  - ⚠`svLive`/`svCapLine` feed main's SV — they must read `knQ('5h')` and `burnFor()`, not `QLAST.q.five_hour`/`BURN` (the primary's live numbers overrode main's saver chip). Missing BURNM = show nothing, never the primary (`tests/test_burn_main_js.py`).
  - ⚠Server primary, the server-side saver stage and the drawer's quota/burndown stay on the primary — never feed `mainAcct()` into them (the status-bar saver verdict follows main via `state.saverViews`); `sbPrimNote` names the primary there. Unset or stale key = byte-identical output.
- **The Sessions account pick (UIS `mbAcctPick.sess`) filters the lists, not the badges** (`40b` `acctPick`/`acctInPick`/`acctOthHtml`, `17` `buildAttn`, `41b` `srecRows`, `41` `sesCount`).
  - ⇒ Each list hides other-account rows behind one «In other accounts: N» line (count only, red dot when a hidden row needs you); click expands that list only (in memory); a new pick folds them again.
  - ⚠The pick is view-only — never write `mbMainAcct` from it. Old `mbOnlyMain='1'` migrates once to the Sessions pick (main or primary label), Timeline never migrates.
  - ⚠The picker is a `<select>` inside a 2.5 s repaint — read `acctPickFocusId()` before the repaint and pass it to `acctPickWire`, or the open dropdown drops to `<body>`.
  - ⚠`attnRows`/`attnBadgeN` stay unfiltered — the tab title and drawer badge count every account; filter only inside `buildAttn`.
  - ⚠External CLI rows and sessions not in `SESS` count as main (never hidden). Row `acct` absent = primary.
- **A session with no account record counts by the folder it lives in** (`claude_roots.acct_of` -> `root_of(fp)`; History/Timeline row `acct`).
  - Cause: shared-history profiles symlink the primary `projects/`, so their transcripts live under the primary root.
  - ⚠Old sessions from before the `acct/<sid>` record (hooks/invite_notice.py) count as primary in every account pick — not a filter bug.
- **Burndown explanation in the quota modal is a hover card, not a native `title`** (`57-burn.js buildBurn`/`burnHcBind`, `.bnhc`).
  - Cause: the `title` on `#burn` popped over the modal title and its font/position cannot be styled; its «Click the row…» line was wrong (no toggle in the modal).
  - Fix: inside `.sdrw` the title is removed and `hcShow('bnhc')` shows `burnTitle(b, true)` fixed at `.bnh` bottom + 6px; hidden on leave, click, Escape and modal close. Outside the modal the native title stays.
  - ⚠Inline hex in JS-built markup (legend glyphs, SVG strokes) bypasses the light-theme twin remap — use `thc(dark, light)`; median dash and legend ┄ share `thc('#8b95a7','#61656c')` (`test_burn_js`). ★`#5f6a7a` was 3.17:1 on the panel.

## Tokens and usage accounting

- ⚠**`_slug_name` depends on the live session snapshot** (2026-10-15). It returns the real folder name only while a session with that cwd is in `sessions_rows(wait=0)`; otherwise the slug minus the home prefix. The 7d and 30d token slots are fetched at different times, so the same project showed two names. ⇒ `burn_usage._wk_namer()` resolves once per fetch, `_WK_NAMES` remembers a session-matched name and `_wk_rename()` corrects older slots. ⚠`_wk_is_fallback` copies the fallback rule — change both together. Test: `test_wk_daily_top.py`.
- ★**The usage-index top 5 went empty at TTL expiry** (2026-09-25, `RuntimeError: dictionary changed size during iteration`). Cause: `agentcost`/`usage_index` iterated `_uidx` outside the lock and collided with a refresh ⇒ `_agc_snap` (agentcost.py:55)·`_uidx_snap` (usage_index.py:87) make a two-level copy inside `_uidx_lock` and iterate only the copy. ⚠Any new iteration over `_uidx["files"]` must go through the snapshot — iterating directly brings the race back.
- ★**Usage per platform** (2026-09-24). Gemini chat files (`transcript_path`) are tail-read from an offset and de-duplicated by message id (`$set` rewrites) → row `tok`·`tokSplit`, `state().extUsage` (today) → token tab «By platform» table. `input` includes cached, so `in = input - cached + tool`.
  - ⚠Separate store (`ext._tok`) — never mix into Claude's `_usage_add`·burn·5h/7d quota.
  - Bottom bar (2026-09-24): `sbExt(EXTU)` gives each platform one cell, logo + tokens + ≈$ (only with usage today); the Claude 5h cell gets the Claude logo. Tooltip = input/cache/output/thinking·models (`extUsage.models`). ⚠`ext_usage_today` is based on `gemini_chats(midnight)` (same source as timeline and history) — using `_tok` alone gives `{}` after restart and misses ended sessions; `_tok` only adds message ids not yet on disk. ⚠`.sbext` has flex-shrink 8 — it shrinks first when narrow, and hides «today» at ≤1600px.
  - Cost is an **estimate** «≈ $x.xx» — `ext.GEMINI_PRICE` (bundled official prices, source and date in a comment). Each request's tier is chosen by its prompt size (>200k) and stored in the message tuple; when the table changes, `GEMINI_PRICE_VER` recomputes from stored tokens. Rows use `estCost` (⚠`cost` is the Claude chip and stays 0); models missing from the table show «—» («Model not in the price table»).
  - ⚠The path is the hook POST value — only `~/.gemini/**.jsonl` under the real home (`pwd`, not `$HOME`) is read. Test `tests/test_ext_tok.py`.
- ★**The agent cost table goes down to «type» only — `_agc_fetch()`** (2026-09-21). Subagents are a large share of the bill
  (★measured all-time $5,894 / $27,750 = **21.2%** · 2,330 calls · 60 types), yet nowhere showed which agent spent how much.
  ⇒ A cumulative table under the token tab's «subagents running now».
  Sources are only `_uidx`'s per-file token buckets + the adjacent `agent-*.meta.json` sidecars.
  - ⚠**Never add agent «name» or «model» columns.** Names are not in the logs (meta's `description` is that call's task, not a
    name), and `model` exists on only **43** of 2,326. Empty axes were dropped.
  - ⚠It is an all-time total — independent of the period buttons above (day·week·month). Hence the «last» column is required
    (an agent type unused since 08-24 still ranks 7th).
  - ⚠Aggregation has **TTL 120 s** (`AGC_TTL`). The screen polls every 2.5 s — never recompute per poll.
    `_agc_meta` is a permanent per-path cache (meta.json is written once and never changes): cold **434ms** → warm **6ms**.
- ★**Token totals do not use ccusage — a local incremental index** (2026-09-11). Cause: ccusage re-reads **all 2,273 transcript
  files, 2.86GB** every time even with a range (`weekly` 45.35s · `blocks` 30.96s · `daily --since` 41.68s). ⇒ `usage-index.json`
  keeps **per-file byte offsets** and reads only new tails (`_uidx_*` · `_usage_backfill_local` · `_uidx_projects`) — first scan
  7.7 s · incremental **0.05 s**. Accuracy, side-by-side: 7-day project·model·cost **0.0000%** · all-block sum 0.0088%.
  - ⚠**Without de-duplication it doubles** (duplicate tokens 49.05%). 99.73% are on the very next line and only 0.05% cross files,
    so **a 2,048-key window per file + 8MB rewind** suffices — no global seen-set needed.
  - ⚠**Never drop zero-token lines** — they set the start of a 5-hour block (dropping them shifted 41 of 378 blocks).
  - ⚠Never write prices from memory — the opus family is **$5/$25** (not 15/75). `USAGE_PRICE` was back-computed from ccusage
    output. Unknown models cost 0 + `warn_once`. To revert, `USAGE_LOCAL = False` is enough.
  - Cheaper, so intervals were tightened: `WK_EVERY {1:120, 7:180, 30:600}` · `WK_RETRY_S 120` ·
    `_projcost_loop` 600→120 s. ⚠Never 0 — every call `stat`s 2,273 files.
  - Per-project cumulative cost (`_projcost_local`) uses the same index: `ccusage session` 26.0 s → **0.003 s**, per-project values
    identical to the digit (total $21,792.14 identical). ⚠Subagents are split by «path», so only that bucket differs by 0.06%
    ($5,699.68 ↔ $5,696.36).
- ★**Index model keys carry tier and cache-TTL suffixes** (2026-10-12, `UIDX_V = 2`). Cause: Haiku 5.5 bills a whole request at
  $0.50/$2.50 when its prompt (input + cache write + cache read) is over 100k (5x the short rate), and 1-hour cache writes cost
  input x2 (5-min x1.25); hour x model sums cannot price either.
  - ⇒ `_req_rows` splits each request at scan time into `model[|long]` = [in, out, cc5m, cr] and `model[|long]|1h` = [0, 0, cc1h, 0];
    `_cost4` reads the suffixes (`USAGE_TIER`). `commit_link` prices requests with the same `_req_cost`.
  - ⚠Suffixed keys hold **disjoint** tokens — never re-add one into its base key (double count). Token sums over all keys stay right.
  - ⚠Any place that **shows** a model name must go through `_model_disp` (`_uidx_projects` modelBreakdowns, history top model/count).
  - ⚠An index with another `v` is ignored at load (full rescan) — bump `UIDX_V` whenever the key shape changes.
- ★**The live sparkline was empty for 10 minutes after every restart** (2026-09-09).
  - Cause: `_usage_save()` (`chat_server.py:_usage_save`) saved only blocks·week, and `_usage["spark"]` (time series) was
    memory-only — backfill is aggregated and cannot restore a time series.
  - ⇒ `spark` included in `_usage_save`/`_usage_load`. On load, points older than `LIVE_SEC` (600 s) are dropped.
    Saving piggybacks on `_today_loop`, already running every 30 s, instead of `_usage_loop` (900 s) (no new timer).
  - ⚠`_usage_save()` takes only a shallow copy inside `_usage_lock` and runs `json.dump` outside it —
    file IO inside the lock blocks other threads.
  - ★Verified: 10 fresh points restored / 5 points 610 s+ old dropped; an old cache without spark loads without error (module-load test).
- ★**Live tokens went to 0** (2026-09-09).
  - Cause: `_otel_ingest`'s order guard (drop if `seq < cur["seq"]`). `event.sequence` is **not monotonic** — when the exporter
    reconnects it counts from 1 again (★measured: across a viewer restart, live sessions' seq went 5182→210 · 58528→1241). After
    one reset everything was dropped until restart.
  - ⇒ ① **accounting moved outside the guard** — sums are order-independent. Resends are blocked by `request_id` (`_otel_req`).
    ② on a large step back (`OTEL_SEQ_BACK` 100) or silence (`OTEL_SEQ_STALE_S` 60 s), follow the new counter.
  - ⚠«Not arriving» and «arriving and dropped» look the same on screen ⇒ tell them apart with `_stat` in `/api/otel`.
    `dropName` is normal (`hook_execution_*` is outside `OTEL_KEEP`).
  - ⚠When `_otel` freezes, session state freezes too — «live 0» and «state not changing» share one root.
- ★**OTel bySrc reset to 0 on every restart** (2026-09-24 · OTel +37% over transcripts, so 5h comparison was impossible).
  - Cause: `_otel_stat["bySrc"]` was memory-only — feature work restarts often.
  - ⇒ `otel-bysrc.json` (DATA_DIR) holds 5-minute buckets `{ts:{model|query_source:[count,tokens]}}` · 8-day retention · 64+`other` per bucket.
    Saved by `_today_loop` via `_otel_src_save()` (60 s throttle · atomic) · loaded (merged) on first call.
  - Query: `_stat.bySrcWin` in `/api/otel?h=1..192` · `/api/otel?cmp=1&h=5` = `{otelTotal, transcriptTotal, ratio,
    ratioNoSide, byKind:{main,agent,side,nonMain}, since, covered}`. The transcript side uses `usage-index` hourly buckets.
  - ⚠Windows are **whole hours** (transcripts are hourly buckets) · longer than OTel's history gives `covered:false` — check it before trusting ratio.
  - ⚠Keep `bySrc` (cumulative since restart) as-is — the two values cover different periods.
- ★**Three token totals all differed — «one response = several lines»** (2026-09-09).
  - Transcripts write one line per content block of a response and **copy the full usage on every line**
    (★measured: 3,385 usage lines / 1,693 responses = 2.00 per line). The timeline also added the `usage.iterations[]` copies.

    | Screen | Definition | Today | vs. true |
    |---|---|---|---|
    | Agent timeline | regex to end of line · per line | 618.1M | ×2.94 |
    | Today by project | `message.usage` · per line | 413.3M | ×1.97 |
    | Daily | ccusage (`msg+req` de-duplicated) | 210.0M | **reference** |

  - ⇒ One definition (★ above `_TOKRE`): `in + output + cache read + cache write` · first occurrence per field only ·
    once per response by `(message.id, requestId)`. Applied to `_seg_scan`·`_today_fetch`·`_burn_fetch`.
    ★Identical to the digit with `ccusage daily` (09-07 352,606,896 · 09-08 683,110,423).
  - ⚠Do not drop output tokens again · ⚠do not cut `iterations` by name (the rule is first occurrence per field).
  - ⚠Duplicates occur **within one file** — filter while scanning a file, not when merging files.
  - ⚠`_burn_fetch` doubled even the request count (only the median was right). Its `c` is context size, so output is not included.
- ★**Unquoted `class=brdot off` made every dot «running»** (2026-10-05, token tab subagent list). `off` parsed as a separate attribute, so `.brdot.off` never matched. The table is the burn window (finished agents included), titled «running now». ⇒ `class="brdot off"`, heading «subagents in the last N min · dot = running now» (46-tokens-tab.js). ⚠Quote every multi-class attribute in built HTML.
- ★**5h used tokens had three counts** (2026-10-05). Status bar/MCP = transcript sum (`quota_burn().cur.used_local`); `/api/state` `usage.block` = ccusage + OTel, `quotaWho` = OTel buckets + seed. Same window, 0.4–3.1M apart. ⇒ `burn.used5_peek` (cached body only, None past 120 s) feeds both `/api/state` figures (`state._used5_one`). ⚠Don't count 5h used anywhere else. quotaWho rows are rescaled onto the headline (`state._scale_rows`, largest remainder; rows + «others» = header, 118M header vs 123M rows before) and keep their OTel `share`.
- **Tokens account pick: the all-accounts path keeps its one-argument calls** (`burn_usage._wkuse_fetch`, `_wkuse_acct`).
  - Cause: `test_golden_wkuse_fetch` stubs `_wk_slot` and `_uidx_projects` with exactly one argument.
  - ⇒ With `acct=""` call `_wk_slot(nd)` and `_uidx_projects(nd)`; pass the account only on the per-account path.
  - ⚠Per-account slots `_wkuse_acct[(nd, label)]` refresh on request only (`wk_stale`), never from `_wkuse_loop`.
