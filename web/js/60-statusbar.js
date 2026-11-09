// Bottom status bar — reads only state `poll()` already refreshed (SV, QLAST, #dot); no fetch of its own.
//   The drawer holds the original #burn/#saver/#quota nodes, moved once, so their builders keep drawing them.
let SBAR_SV = null;
let EXTU = {};            // state().extUsage — external CLI tokens today per platform (never Claude quota); set by 95-poll.js
let SDRW_OPEN = false;    // a modal never reopens by itself on reload
// Connection state of the /api/state poll — written only through connMark (95-poll.js), read by the status bar
// and quota drawer. `bad` = the server answered but the body was unusable (bad JSON, non-2xx).
// ⚠While down, every number on screen is the last good value — html.agstale dims it and «as of N min ago» says how old;
//   a failed fetch must never be drawn as a fresh zero.
// `slow` = the last try timed out but the server answered within POLL_DOWN_MS; `pend` = start of the request in flight (0 = none).
const CONN = {fails: 0, next: 0, okAt: 0, bad: false, slow: false, pend: 0};
// Poll backoff while down: 5 → 10s cap (base tick 2.5s); the first success resets it.
// ⚠Without it a dead server got ~55 failed requests a minute (state 2.5s + live 3s), each one a console error.
// ⚠Cap stays at 10s: the viewer restarts often, and a 30s cap took ~23s to notice it was back up.
function connBackoffMs(n){ return n > 0 ? Math.min(10000, 2500 * Math.pow(2, n)) : 0; }
function connMark(c, ok, bad, now){
  c.slow = false;
  if(ok){ c.fails = 0; c.next = 0; c.okAt = now; c.bad = false; }
  // ⚠`now` = request start (ticks align to it); 250ms absorbs timer jitter so the retry gap stays ≤ the 10s cap.
  else { c.fails++; c.bad = !!bad; c.next = now + connBackoffMs(c.fails) - 250; }
  return c;
}
function connWait(c, now){ return c.fails > 0 && now < c.next; }
// A timed-out poll: true = count it as down (no reply ever, already down, or none for `downMs`); false = mark slow only.
// ⚠Slow is not down: the server is alive, the screen keeps the last data and the next try waits longer.
function connTimedOut(c, now, downMs){
  if(!c.okAt || c.fails > 0 || now - c.okAt >= downMs) return true;
  c.slow = true;
  return false;
}
// ★Load 100-190 made /api/state take 30-39 s (2026-11-04) and the bar read «Disconnected» while the server was alive.
// ⇒ «Data delayed · Ns ago» replaces «Connected» while a poll is slow/pending or the server snapshot is old;
//   the cause (load, slow pieces) goes in the tooltip only. Load alone does not delay data, so it is not a trigger.
const SB_SNAP_OLD_S = 10, SB_POLL_SLOW_MS = 10000;
var SRVLOAD = null;   // state().srvLoad {load1, snapAge, slow: [[piece, ms]]} of the last good poll (set by 95-poll); null = old server
// Delay/load verdict or null. Missing/odd srvLoad fields count as unknown, never as 0.
// ★Load 30-135 on 12 cores with no poll delay (2026-11-04): «Data delayed» alone never showed who used the CPU,
//   so load above SB_LOAD_X × ncpu is a second trigger («Machine busy»); unknown ncpu leaves only the delay path.
const SB_LOAD_X = 2;
function sbBusy(srv, c, now){
  const num = v => typeof v === 'number' && isFinite(v) ? v : null;
  const l = srv ? num(srv.load1) : null, sa = srv ? num(srv.snapAge) : null, nc = srv ? num(srv.ncpu) : null;
  const cli = c.okAt > 0 && (c.slow || (c.pend > 0 && now - c.pend >= SB_POLL_SLOW_MS));
  const delayed = !!(cli || (sa != null && sa >= SB_SNAP_OLD_S));
  if(!delayed && !(l != null && nc > 0 && l > nc * SB_LOAD_X)) return null;
  // Age of the data on screen: time since the last applied reply or the server snapshot age, whichever is larger.
  const age = Math.round(Math.max(sa != null ? sa : 0, c.okAt ? Math.max(0, now - c.okAt) / 1000 : 0));
  const slow = (srv && Array.isArray(srv.slow) ? srv.slow : []).filter(p => Array.isArray(p) && p.length >= 2).slice(0, 8);
  // Busiest session (srvLoad.top); an odd shape is dropped, never shown as 0.
  const t = srv && srv.top, top = t && typeof t === 'object' && typeof t.repo === 'string' && t.repo && num(t.cpu) != null && num(t.rssMb) != null ? t : null;
  const out = {load: l, age: age, slow: slow, delayed: delayed};
  if(top) out.top = top;
  return out;
}
// Calm (amber, not red) connection piece; piece names are server data, so esc() only, never T().
function sbBusyHtml(b){
  const n = b.load == null ? '' : String(b.load >= 10 ? Math.round(b.load) : Math.round(b.load * 10) / 10);
  const lbl = b.delayed === false ? TV({msg: 'Machine busy · load {n}', vars: {n: n}}) : T('Data delayed · {s}s ago').replace('{s}', String(b.age));
  const why = (n ? T('load {n}').replace('{n}', n) : '')
    + (b.slow.length ? (n ? ' · ' : '') + T('slow:') + ' ' + b.slow.map(p => String(p[0]) + ' ' + Math.round(+p[1] || 0) + ' ms').join(', ') : '');
  const t = b.top, gb = v => String(Math.round(v / 1024 * 10) / 10);
  const ex = t && Array.isArray(t.exe) ? t.exe.filter(p => Array.isArray(p) && p.length >= 2).slice(0, 5) : [];
  const un = t && t.unowned && typeof t.unowned === 'object' && typeof t.unowned.cpu === 'number' && isFinite(t.unowned.cpu) && typeof t.unowned.rssMb === 'number' && isFinite(t.unowned.rssMb) ? t.unowned : null;
  const tip = (b.delayed === false ? T('Load is above twice the CPU count') : T('The server is answering slowly — the screen keeps the last data')) + (why ? '\n' + why : '')
    + (t ? '\n' + TV({msg: 'mostly {r} · CPU {c}% · {m} GB', vars: {r: t.repo, c: Math.round(t.cpu), m: gb(t.rssMb)}}) : '')
    + (ex.length ? '\n' + T('processes:') + ' ' + ex.map(p => String(p[0]) + ' ×' + Math.round(+p[1] || 0)).join(', ') : '')
    + (un ? '\n' + TV({msg: 'outside Claude sessions: CPU {c}% · {m} GB', vars: {c: Math.round(un.cpu), m: gb(un.rssMb)}}) : '');
  // ⚠The repo name is the point («who»): it drops last (SB_STEPS end); the numbers drop first (SB_STEPS[0]). At 1440 one piece
  //   with the first step hid the name and the tooltip did not carry it either.
  //   The first <small> (repo) is width-capped in 90-main-ui.css; the full name stays in the .sbconn title.
  const sfx = t ? ' <small class=sbd' + SB_STEPS[SB_STEPS.length - 1] + '>· ' + esc(TV({msg: 'mostly {r}', vars: {r: t.repo}})) + '</small>'
    + '<small class=sbd' + SB_STEPS[0] + '> · ' + esc(TV({msg: 'CPU {c}% · {m} GB', vars: {c: Math.round(t.cpu), m: gb(t.rssMb)}})) + '</small>' : '';
  return '<span class=sbconn title="' + esc(tip) + '"><b class=sbwarn>● ' + esc(lbl) + '</b>' + sfx + '</span>';
}
// «as of 2 min ago» — age of the last good poll; '' while connected or before the first success.
function connAge(c, now){
  if(!c.fails || !c.okAt) return '';
  const s = Math.max(0, Math.floor((now - c.okAt) / 1000));
  const span = AGO(ago(s));
  return T('as of {t}', 'conn').replace('{t}', span);
}
// One-line notice for popovers opened while down (same wording as the status bar).
function connStaleNote(c, now){
  const a = connAge(c, now);
  return a ? '<div class=connst>' + esc((c.bad ? T('Bad response') : T('Disconnected', 'link')) + ' · ' + a) + '</div>' : '';
}
function sdrwSet(open){
  const was = SDRW_OPEN;
  SDRW_OPEN = !!open;
  const d = document.getElementById('sdrw'), bar = document.getElementById('sbar');
  if(d) d.classList.toggle('on', SDRW_OPEN);
  // aria-expanded tracks the layer (popAnchor/popHide), which is what the bar controls.
  buildSbar();
  // ⚠The opener (layer button) is hidden on open, so focus must move in, and back to the bar on close.
  const f = sdrwFocusTarget(was, SDRW_OPEN, d, document.activeElement);
  if(f === 'in'){ const x = document.getElementById('sdrwx'); if(x) x.focus(); }
  else if(f === 'bar' && bar) bar.focus();
}
// Where focus goes after sdrwSet: 'in' (opening, unless already inside), 'bar' (an open modal closed), '' (leave it).
function sdrwFocusTarget(was, open, d, a){
  if(open) return was && d && d.contains(a) ? '' : 'in';
  return was ? 'bar' : '';
}
// Visible focusable elements inside the modal, in DOM order.
function sdrwFocusables(d){
  return [...d.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')]
    .filter(n => !n.disabled && n.offsetParent !== null);
}
// Focus wrap: Tab past the last / Shift+Tab before the first, or focus outside the modal -> the element to focus; null = let the browser move.
function sdrwTabTarget(list, a, shift){
  if(!list.length) return null;
  const i = list.indexOf(a);
  if(i < 0) return shift ? list[list.length - 1] : list[0];
  if(!shift && i === list.length - 1) return list[0];
  if(shift && i === 0) return list[list.length - 1];
  return null;
}
// One segment per external platform with a session today (state().extUsage, «Today 0» included), each led by its logo; '' when none.
// ⚠Separate from Claude figures — never summed into 5h/7d/cost.
function sbExt(ex){
  return Object.keys(ex || {}).filter(k => ex[k]).sort().map(k => sbExtSeg(k, ex[k])).join('');
}
function sbExtSeg(k, e){
  const name = platName(k), qs = k === 'cp' ? extQuotaStr(e.quota) : '';
  const tip = name + ' ' + T('usage today — separate from Claude limits and cost') + '\n'
    + T('Input') + ' ' + fmtTok(e.in || 0) + ' · ' + T('Cache') + ' ' + fmtTok(e.cache || 0)
    + ' · ' + T('Output') + ' ' + fmtTok(e.out || 0) + ' · ' + T('Thinking') + ' ' + fmtTok(e.thought || 0)
    + ((e.models || []).length ? '\n' + T('Model') + ': ' + e.models.join(', ') : '')
    + (e.n_sessions ? '\n' + T('Sessions') + ': ' + e.n_sessions : '')
    + (!e.tok ? '' : '\n' + (e.cost == null ? T('Model not in the price table') : extCostStr(e.cost) + ' — ' + T('Cost is an estimate from the bundled price table'))
    + (e.costMiss ? ' (' + e.costMiss + ' ' + T('requests left out (model not in the price table)') + ')' : ''))
    + (k === 'cx' ? '\n' + extRateDetail(e.rate, k, true) : '')
    + (k === 'cp' ? '\n' + (qs ? T('Quota') + ': ' + qs : T('No limit data'))
       + '\n' + T('Quota values refresh only when Copilot runs') : '');
  // The logo's own title would shadow the segment tooltip, so it is dropped. ⚠Logo only — the name lives in the tooltip.
  return '<span class=sbext title="' + esc(tip) + '">' + aiLogo(k).replace(/ title="[^"]*"/, '')
    + '<small class="sbxd sbd4">' + esc(T('Today')) + '</small> <b>' + esc(fmtTok(e.tok)) + '</b>'
    + (e.cost != null ? ' <small class=sbd8>· ' + esc(extCostStr(e.cost)) + '</small>' : '')
    + (e.rate && extRateStr(e.rate) ? ' <small class=sbd5>· ' + esc(extRateStr(e.rate)) + '</small>' : '')
    + (qs ? ' <small class=sbd9>· ' + esc(qs) + '</small>' : '') + '</span>';
}
// ★Short bar: hide whole low-priority parts rather than ellipsize key numbers (key numbers stay visible).
// ⚠No padding-squeeze step: gaps are never squeezed, whole cells drop instead.
// Drop order (SB_STEPS): 9 Copilot quota (⚠first: it must never cost a Claude piece) · 1 «100% at» · 2 «left at reset» · 3 «left ≈» (same
//   quantity as «left %», in tokens) · 5 ext limit % (Codex card has it) · 6 reset times · 7 saver secondary (also in its
//   tooltip) · 8 ext «≈ $cost» and 7d «used» (both in their tooltips) · 4 ext «Today».
// ⚠«Today» is what makes the ext number mean «today» — keep cheaper drops (5, 6, 7, 8) ahead of it; the goal pill and ext
//   token+cost segments are never dropped and overflowed 900 by 63-255 px after step 7. Ellipsis stays only as the last resort.
const SB_STEPS = [9, 1, 2, 3, 5, 6, 7, 8, 4];
// ★UX audit 2026-09-28: «slower than goal» named no subject — the verdict is 5h usage pace vs the saver goal, so the label says «use», same width.
const SB_JNAME = {'Way too fast': 'Burning far above target', 'Fast': 'Above target', 'On pace': 'On target',
                  'Slow': 'Below target', 'Way too slow': 'Far below target',
                  // Weekly near the cap replaces the 5h verdict.
                  'Weekly near cap': 'Weekly ≈ used up'};
function sbFit(el){
  if(!el.clientWidth) return;
  el.classList.add('sbfit');
  for(let i = 0; i < SB_STEPS.length && el.scrollWidth > el.clientWidth + 1; i++){
    el.querySelectorAll('.sbd' + SB_STEPS[i]).forEach(n => n.classList.add('sbh'));
  }
  el.classList.remove('sbfit');
}
// English tooltip rebuilt from the hook snapshot's numeric fields; goalSay/head are Korean sentences
//   written for the injected text. '' when the snapshot lacks the fields, so the caller keeps the raw text.
function svWhyEn(v){
  if(!v) return '';
  if(v.mode === 'off') return 'Saver off (auto start blocked too)';
  if(typeof v.pct !== 'number') return '';
  const n = Math.abs(v.earlyMin || 0);
  const LV = {2: 'Much too fast (runs out ' + n + 'm before the target) — slow down',
              1: 'Fast (runs out ' + n + 'm before the target) — ease off a little',
              0: 'On pace (' + n + 'm off the target) — keep it up',
              '-1': 'Behind (runs out ' + n + 'm after the target) — run independent work in parallel',
              '-2': 'Far behind (runs out ' + n + 'm after the target) — run independent work in parallel'};
  const lines = [];
  if(v.lvNm === '주간 임박') lines.push('Weekly limit nearly used — no longer advising more parallel work');   // lvNm: wire value from saver.py, not UI
  else if(v.lv != null && v.earlyMin != null && LV[v.lv]) lines.push(LV[v.lv]);
  const parts = ['5h limit ' + v.pct + '%'];
  if(v.leftMin) parts.push('resets ' + LATER(HM(v.leftMin)));
  if(v.mode === 'pace' && v.until) parts.push('target ' + v.until);
  if(v.overAt) parts.push('at this pace runs out at ' + CLK(new Date(v.overAt * 1000)));
  if(v.goal != null) parts.push('goal ' + v.goal + '%');
  if(v.stage) parts.push('saver level ' + v.stage);
  if(v.end) parts.push('wrap up');
  else if(v.rec != null) parts.push(v.rec ? 'up to ' + v.rec + ' in parallel' : 'no new subagents');
  lines.push(parts.join(' · '));
  return lines.join('\n');
}
// ⚠The drawer's quota rows and token figures stay on the primary even with a «Main account» set (the modal burndown follows main); '' when unset.
function sbPrimNote(){
  if(!mainAcct()) return '';
  const p = (acctList() || []).find(a => a && a.primary);
  return TV({msg: 'Quota rows and token figures follow the default account ({a})', vars: {a: String((p && p.label) || '')}});
}
// Colour class keyed on used % (>=70 / >=90 used = <=30 / <=10 left); shared with the status-bar layer (60b).
function sbPctCls(p){ return p >= 90 ? 'sberr' : p >= 70 ? 'sbwarn' : 'sbok'; }
let SB_RZ = 0;
// ⚠One rebuild per frame, not a timeout debounce: buildSbar is ~0.3 ms, and a 150 ms debounce froze the bar's old layout for the whole drag.
addEventListener('resize', () => { cancelAnimationFrame(SB_RZ); SB_RZ = requestAnimationFrame(() => { SB_RZ = 0; buildSbar(); }); });
function buildSbar(sv){
  if(sv !== undefined) SBAR_SV = sv;
  const el = document.getElementById('sbar');
  if(!el) return;
  const it = (cls, html, tip) => '<span' + (tip ? ' title="' + esc(tip) + '"' : '') + '>'
    + (cls ? '<b class=' + cls + '>' : '<b>') + html + '</b></span>';
  const out = [];
  // Pace vs goal is the primary word; "no throttle" (the old «Easy») is the dim secondary.
  const r = svParts(SV, null, svLive());
  const snap = !!(r && !r.old);
  if(r){
    const j = r.judge;
    const JC = {ok: 'sbok', slow: 'sbinfo', slow2: 'sbinfo', fast: 'sbwarn', fast2: 'sberr', wait: 'sbidle'};
    // A manual /saver switch wins over the hook snapshot, which only refreshes on the next CLI prompt.
    const sw = SVSW && SVSW.mode;
    const sec = sw === 'on' ? T('Manual') + ' ' + TV({msg: 'level {n}', vars: {n: SVSW.stage}})
              : sw === 'off' ? T('Manual off')
              : r.cls.indexOf('svfree') === 0 ? T('No throttle') : '';
    // Tooltip leads with the hook's own sentence (goalSay/head) so «Pending» says why, in the same words as the badge.
    const why = (LANG === 'en' && svWhyEn(SV)) || [SV && SV.goalSay, SV && SV.head].filter(Boolean).map(String).join('\n');
    // sec (.sbd7) is dropped before «Today» on a short bar, so the tooltip carries it too.
    const ptip = (j && sec ? sec + '\n\n' : '') + (why ? why + '\n\n' : '') + T(SV_JTIP).replace(/\*\*/g, '')
      + (sec === T('No throttle') ? '\n' + T('No throttle = no saver stage is set (subagent concurrency not capped)') : '')
      + (sbPrimNote() ? '\n\n' + sbPrimNote() : '');
    // In goal mode the target time was the grey fallback text — now a pill, always shown.
    const gp = r.mode === 'pace' ? '<b class=sbgoal>' + esc(r.main) + '</b>' : '';
    out.push('<span title="' + esc(ptip) + '">' + gp + (j || !gp ? '<b class="' + (j ? JC[j.k] || '' : 'sbidle') + '">'
      + esc(j ? (SB_JNAME[j.nm] ? T(SB_JNAME[j.nm]) : svJName(j)) : r.main) + '</b>' : '') + (j && sec ? '<small class=sbd7>' + esc(sec) + '</small>' : '') + '</span>');
  }
  const now = Date.now();
  // Quota window = knQ (55a: «Main account» or the primary); token parts are primary-only (hidden while main is set),
  // projection and 100% ETA read burnFor() (main's own `?dir=` body, nothing when it is missing).
  // «Show in bar» (kpiQ, 60b select): another account's 5h/7d only — tokens, «left ≈», projection and ETA are main's, so they hide (kx).
  const kq = typeof kpiQ === 'function' ? kpiQ : knQ, k5 = kq('5h'), k7 = kq('7d'), kx = k5.kpi, ma = mainAcct() || kx;
  // ⚠A usage-billed seat has no 5h/7d windows (both null -> 0%), so «left 100% · left ≈ N» and a 100% ETA were false;
  //   the drawer badge was the only credit sign and is hidden while the drawer is closed. Credits replace both segments.
  const cs = !ma && typeof creditInfo === 'function' ? creditInfo(typeof QLAST !== 'undefined' && QLAST && QLAST.q) : null;
  const meterSeat = !!(cs && cs.meter), fh = meterSeat ? null : k5.w, sd = meterSeat ? null : k7.w;
  if(meterSeat) out.push('<span class=sbcredit title="' + esc(cs.tip) + '">' + aiLogo('cc').replace(/ title="[^"]*"/, '')
    + '<b class=sbwarn>' + esc(T('Credit mode')) + '</b>'
    // Monthly-limit gauge (used share), coloured on the same used-% steps as the 5h/7d «left» numbers.
    + (cs.pct != null ? '<span class="sbqg ' + sbPctCls(cs.pct) + '"><i style="width:' + Math.min(100, Math.max(0, cs.pct)).toFixed(1) + '%"></i></span>' : '')
    + (cs.pct != null ? '<b class=' + sbPctCls(cs.pct) + '>' + esc(creditPct(cs.pct)) + '</b>' : '')
    + '<small>' + esc(cs.usedOf) + '</small></span>');
  const mtip = r => (r.kpi ? '\n' + TV({msg: 'Shown in bar: {a}', vars: {a: r.kpi}}) + (r.kmiss ? ' (' + TV({msg: 'Quota unknown for {a} — showing the main account', vars: {a: r.kpi}}) + ')' : '') : '')
    + (r.main && (!r.kpi || r.kmiss) ? '\n' + T('Main account') + ' ' + r.main + (r.miss ? ' (' + T('Main account quota unknown — showing the default account') + ')' : '') : '');
  // Remaining official % only — no token used/headroom (traps/quota.md «Token headroom»).
  const pc = sbPctCls;
  // Used tokens = measured local sum (`cur.used_local` / `wk_used_local`), shown; estimates never are.
  const cu0 = (!ma && BURN && BURN.cur) || {}, est0 = (!ma && BURN && BURN.est) || {};
  // 7d measured sum: top-level `wk.used_local` also covers a body without `cur` (5h cycle just ended).
  const wkU = ma ? null : cu0.wk_used_local != null ? cu0.wk_used_local : (BURN && BURN.wk && BURN.wk.used_local != null ? BURN.wk.used_local : null);
  // ⚠Main account: its own hour-bucket sums (`used_acct`, approximate) shown as «used ≈», never the primary's used_local.
  const bmA = ma && !kx && typeof burnFor === 'function' ? burnFor() : null, au5 = bmA && bmA.cur ? bmA.cur.used_acct : null, au7 = bmA && bmA.wk ? bmA.wk.used_acct : null;
  // «left N%»; «left ≈» from `burnEst` (history per-1%); 7d unmeasured: «Used ≈ · left ≈».
  const sbt = (l, v) => ' <small>· ' + esc(l) + '</small> <b>' + esc(fmtTok(v)) + '</b>';
  const use = (p, n, k, a) => {
    const w = k === '7d' && n == null && est0.wk_used != null ? burnWkEst(BURN) : null;
    // main account: measured tokens are the primary's, so only «left ≈» from the main account's own history (est)
    const bm = ma && !kx && typeof burnFor === 'function' ? burnFor() : null;
    // ⚠A low (own-window) est stays in the layer (sblEst) only — the bar keeps its length.
    const e = ma ? (bm && !(bm.est && bm.est.low) && (k === '7d' ? burnWkEst(bm) : burnEst(bm, k, null, p))) : w || burnEst(BURN, k, n, p);
    // Remaining %; colour still keyed on used (≥70/≥90 used = ≤30/≤10 left). Tooltip keeps used %.
    const u = n != null ? sbt(T('used'), n) : w ? sbt(T('used ≈'), w.used) : a != null ? sbt(T('used ≈'), a) : '';
    // 7d used (.sbd8) goes before ext «Today»; 5h used stays (it is the live cycle).
    return (p == null ? '' : '<small>' + esc(T('left')) + '</small> <b class=' + pc(p) + '>' + esc(fmtPct(Math.max(0, 100 - p))) + '</b>') + (u && k === '7d' ? '<span class=sbd8>' + u + '</span>' : u)
      + (e ? '<span class=sbd3> <small>· ' + esc(T('left ≈')) + '</small> <b>' + esc(estLeftTxt(e)) + '</b></span>' : '');   // estLeftTxt: rounded 100% reads «< 1%», not 0
  };
  if(fh){
    const ms = fh.resets_at ? Date.parse(fh.resets_at) : NaN;
    const m = !isNaN(ms) ? Math.max(0, Math.round((ms - now)/60000))
            : (fh.leftSec != null ? Math.max(0, Math.round(fh.leftSec/60)) : null);
    const bm5 = ma && !kx && typeof burnFor === 'function' ? burnFor() : null;
    const e5 = ma ? (bm5 && burnEst(bm5, '5h', null, fh.pct)) : burnEst(BURN, '5h', cu0.used_local, fh.pct);
    const t5 =T('5-hour limit — official usage') + ' ' + (fh.pct == null ? '?' : fmtPct(fh.pct)) + mtip(k5)
      + (cu0.used_local != null ? '\n' + T('Tokens used') + ' ' + fmtTok(cu0.used_local) + ' — ' + burnUsedTip() : '')
      + (au5 != null ? '\n' + T('used ≈') + ' ' + fmtTok(au5) : '')
      + (e5 ? '\n' + T('left ≈') + ' ' + estLeftTxt(e5) + ' — ' + e5.tip : '')   // same pick as the bar text
      + (!isNaN(ms) ? '\n' + T('Resets', 'card') + ' ' + CLK(new Date(ms)) : '');
    // Claude logo leads the Claude group (5h … 7d); external platforms lead theirs in sbExt.
    out.push('<span title="' + esc(t5) + '">' + aiLogo('cc').replace(/ title="[^"]*"/, '') + '<b>5h</b> '
      + use(fh.pct, cu0.used_local, '5h', au5)
      + (m != null ? ' <small class="sbd6' + (m < 30 ? ' sbwarn' : '') + '">· ' + esc(T('reset')) + ' ' + esc(LATER(HM(m))) + '</small>' : '') + '</span>');
    // Projected remaining at reset = 100 - burndown projection % (same «left» framing as the 5h segment); colour keyed on used.
    const bf = kx ? null : burnFor(), pj = bf && bf.proj;
    if(pj && pj.pct != null){
      const over = pj.over_in != null || pj.over_at != null;    // limit is hit before the reset
      out.push('<span class="sb2 sbd2" title="' + esc(TV({msg: 'Projected 5h limit left at reset at this pace (projected used {p})', vars: {p: fmtPct(pj.pct)}}) + (over ? T(' — runs out before the reset') : '')) + '"><small>' + esc((over ? T('runs out', 'sbar') : T('left at reset'))) + '</small> '
        // en reorders the over case: «left at reset out» does not parse, «runs out before reset» does
        + '<b class=' + (over ? 'sberr' : pc(pj.pct)) + '>' + esc(over ? T('before reset', 'sbar') : '≈' + fmtPct(Math.max(0, 100 - pj.pct))) + '</b>'
        + '</span>');
    }
    // ETA to 100% at the current pace. Shown even when it lands after the reset, so the margin is always visible.
    const cu = bf && bf.cur;
    // ★2026-09-27 cross-tab audit: absolute `over_at` like #burn — now + server-relative over_in drifted by poll age.
    const nowS = Date.now()/1000;
    const oat = (pj && pj.over_at) ? pj.over_at
      : (cu && cu.rate_pph > 0 && cu.now_pct != null && cu.now_pct < 100 && bf.at)
        ? bf.at + (100 - cu.now_pct) / cu.rate_pph * 3600 : null;
    const eta = oat != null ? Math.max(0, oat - nowS) : null;
    if(eta != null){
      const at = new Date(oat*1000), past = m != null && eta/60 > m;
      out.push('<span class="sb2 sbd1" title="' + esc(T('When the 5h limit reaches 100% at the current pace')) + '"><small>' + esc(T('100% at')) + '</small> '
        + '<b class=' + (past ? 'sbok' : eta < 3600 ? 'sberr' : 'sbwarn') + '>' + esc(CLK(at)) + '</b>'
        + ' <small>' + esc(LATER(HM(Math.round(eta/60)))) + (past ? ' · ' + esc(T('after reset')) : '') + '</small></span>');
    }
  }
  if(sd){
    const d = sd.resets_at ? new Date(sd.resets_at) : null;
    const w7 = wkU == null && est0.wk_used != null ? burnWkEst(BURN) : null;
    const t7 = T('7-day limit — official usage') + ' ' + (sd.pct == null ? '?' : fmtPct(sd.pct)) + mtip(k7)
      + '\n' + T('Account limit window: from the reset · includes other devices and claude.ai (the Tokens tab «last 7 days» is this PC · calendar days)')
      + (wkU != null ? '\n' + T('Tokens used') + ' ' + fmtTok(wkU) + ' — ' + burnUsedTip() : '')
      + (au7 != null ? '\n' + T('used ≈') + ' ' + fmtTok(au7) : '')
      + (wkU == null && au7 == null && w7 ? '\n' + T('used ≈') + ' ' + fmtTok(w7.used) : '')   // bar's estimate case, so dropping .sbd8 loses nothing
      + (est0.wk_left != null ? '\n' + T('left ≈') + ' ' + estLeftTxt({left: est0.wk_left}) + ' — ' + burnEstTip('7d', est0) : '')
      + (d && !isNaN(d) ? '\n' + T('Resets', 'card') + ' ' + RST7(d).abs + ' · ' + RST7(d).rel : '');
    out.push('<span title="' + esc(t7) + '"><b>7d</b> <small class=sbd6>' + esc(T('account')) + '</small> ' + use(sd.pct, wkU, '7d', au7)
      + (d && !isNaN(d) ? ' <small class="sbd6' + (d - now < 6*3600e3 ? ' sbwarn' : '') + '">· ' + esc(T('reset')) + ' ' + esc(RST7(d).rel) + '</small>' : '') + '</span>');   // rel piece only: abs+rel pushed other segments out at 1100 (full text in the title)
  }
  // No 5h/7d at all: say why (lookup off · no login · API unreachable) instead of leaving the Claude group blank.
  if(!fh && !sd && typeof QERR !== 'undefined' && QERR){
    const why = qErrText(QERR);
    out.push('<span title="' + esc(why) + '">' + aiLogo('cc').replace(/ title="[^"]*"/, '') + '<b>5h</b> <small class=sbwarn>' + esc(why) + '</small></span>');
  }
  const gx = sbExt(typeof EXTU === 'undefined' ? null : EXTU);
  if(gx) out.push(gx);
  const st = snap ? r.stage : (SBAR_SV && SBAR_SV.on ? (+SBAR_SV.stage || 0) : 0);
  if(st > 0) out.push(it(st >= 3 ? 'sberr' : 'sbwarn', esc(TV({msg: 'Saver: level {n}', vars: {n: st}}))));
  // Busy-session count is omitted: the top stat panel already shows it (one number, one place).
  const off = document.getElementById('dot').classList.contains('off');
  // Connection sits after the gap, pinned right beside the chevron — it must never be clipped by overflow:hidden.
  const age = off ? connAge(CONN, Date.now()) : '';
  const busy = off ? null : sbBusy(SRVLOAD, CONN, Date.now());
  const conn = busy ? sbBusyHtml(busy) : it(off ? 'sberr' : 'sbok', '● ' + esc(off ? (CONN.bad ? T('Bad response') : T('Disconnected', 'link')) : T('Connected')) + (age ? ' <small>· ' + esc(age) + '</small>' : ''))
    .replace('<span', '<span class=sbconn');
  const tip = T('Click (or Enter) for quota and session summary');
  if(el.title !== tip) el.title = tip;
  // sbFit only adds .sbh, so a width change must rewrite before refitting.
  if(el._fitW !== el.clientWidth){ el._fitW = el.clientWidth; el._sh = null; }
  if(setHtml(el, out.join('') + '<span class=sbgap></span>' + conn + '<span class=sbchev>' + (SDRW_OPEN ? '▾' : '▴') + '</span>')) sbFit(el);
  if(SDRW_OPEN) buildQwho();
  if(popIsOpen('sblpop')) sblPaint();
}
// «Who is using the 5h» — per-project share of the current cycle (state.quotaWho; metadata only).
//   Drawn only while the modal is open; buildSbar calls it, so the language switch re-renders it too.
let QWHO = null;
// Approximate when the server had no official 5h reset, or its window is not the account the bar shows (knQ, 55a).
function qwhoApprox(w){
  if(!w || !w.exact) return true;
  const k = typeof knQ === 'function' ? knQ('5h') : null, r = k && k.w && k.w.resets_at ? Date.parse(k.w.resets_at) : NaN;
  return !isNaN(r) && Math.abs(r / 1000 - 5 * 3600 - w.start) > 120;
}
function buildQwho(){
  const el = document.getElementById('qwho');
  if(!el) return;
  const w = QWHO, rows = (w && w.rows) || [];
  const tip = T('Cycle so far from session transcripts, live OTel after server start · subagents fold into the parent session · metadata only (no conversation content)');
  // Account whose 5h window is shown (usage.quota_who acct; '' = primary): a user label, so esc() only, never T().
  let h = connStaleNote(CONN, Date.now()) + '<div class=qwh title="' + esc(tip) + '"><b>' + esc(T('Who is using the 5h')) + '</b>'
    + (w && w.acct ? ' <small class=qwa>' + esc(String(w.acct)) + '</small>' : '')
    + (w ? ' <small' + (qwhoApprox(w) ? ' title="' + esc(T('estimated')) + '">≈' : '>') + esc(CLK(new Date(w.start * 1000))) + '~ · ' + esc(fmtTok(w.total || 0)) + '</small>' : '')
    + (w && w.partial && w.since ? ' <small class=sbwarn>· ' + esc(T('counting since')) + ' ' + esc(CLK(new Date(w.since * 1000))) + '</small>' : '')
    + '</div>';
  if(!rows.length){ setHtml(el, h + '<div class=qwe>' + esc(T('No requests recorded this cycle')) + '</div>'); return; }
  h += rows.map((r, i) => '<div class=qwr title="' + esc(r.sids.map(x => x.sid + ' ' + fmtTok(x.tok)).join('\n')) + '">'
    + '<span class=qwn>' + esc(r.name) + (r.n > 1 ? ' <small>×' + r.n + '</small>' : '') + '</span>'
    + '<span class=qwb><i style="width:' + Math.max(1, Math.min(100, r.share)) + '%;background:' + wkc(i) + '"></i></span>'
    + '<b>' + esc(fmtPct(r.share)) + '</b><small>' + esc(fmtTok(r.tok)) + '</small></div>').join('')
    + (w.others ? '<div class=qwe>' + esc(T('Other', 'rest') + ' ' + w.others + (w.othersTok ? ' · ' + fmtTok(w.othersTok) : '')) + '</div>' : '');
  setHtml(el, h);
}
{
  const inner = document.getElementById('sdrwin');
  if(inner){
    // role=dialog + aria-modal live on #sdrw (index.html), labelled by #sdrwt.
    inner.innerHTML = '<div class=sdrwh><b id=sdrwt>' + esc(T('Quota details')) + '</b><button id=sdrwx aria-label="' + esc(T('Close')) + '">✕</button></div>';
  }
  ['burn', 'saver', 'quota'].forEach(id => { const n = document.getElementById(id); if(n && inner) inner.appendChild(n); });
  if(inner){ const qw = document.createElement('div'); qw.className = 'qwho'; qw.id = 'qwho'; inner.appendChild(qw); }
  const bar = document.getElementById('sbar'), dr = document.getElementById('sdrw');
  if(dr) dr.onclick = e => { if(e.target === dr || e.target.id === 'sdrwx') sdrwSet(false); };
  // Tab cycles inside the modal (aria-modal alone does not stop the browser tabbing behind it).
  if(dr) document.addEventListener('keydown', e => {
    if(e.key !== 'Tab' || !SDRW_OPEN || e.defaultPrevented) return;
    const t = sdrwTabTarget(sdrwFocusables(dr), document.activeElement, e.shiftKey);
    if(t){ e.preventDefault(); t.focus(); }
  });
  // The bar opens the summary layer (60b); the modal is reached through the layer's «Quota details» button.
  bar.onclick = () => sblToggle();
  bar.onkeydown = e => { if(e.key === 'Enter' || e.key === ' '){ e.preventDefault(); sblToggle(); } };
  document.addEventListener('click', e => { if(e.target.closest && e.target.closest('#sblpop [data-sdrw]')){ sblClose(false); sdrwSet(true); } });
  // ⚠One Esc closes one layer: skip when a layer above (Cmd+K palette, dialogs) already handled it.
  document.addEventListener('keydown', e => { if(e.key === 'Escape' && SDRW_OPEN && !e.defaultPrevented && !cpOn) sdrwSet(false); });
  sdrwSet(SDRW_OPEN);
}
