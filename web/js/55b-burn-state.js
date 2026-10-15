// ★Limit burndown (2026-09-21: whether 12% left at 50 min is exactly right). The gauge only says «what % now»
// — whether it runs out before reset was mental math each time. The screen does that math instead.
// ⚠Numbers here are **all estimates**. Wording is fixed to "at this rate", and number weight is lower than official values (`.quota b`)
// (`.burn em`) — on a monitoring screen an estimate that looks measured is a lie.
// ⚠No new timer — piggybacks on `poll()` (2.5s) and throttles to 30s here.
// (The server also caches with TTL 30s, so calling more often returns the same value.)
// ★Default is **expanded** (2026-09-21: collapsed was too small to notice) — people did not know the row was collapsed
// and reported "curve not visible" as a bug. A single glyph is not an affordance.
// ⚠The stored value has 3 states — a single `=== '1'` cannot tell "never touched" from "deliberately
// collapsed". No key (null)=expanded · `'0'`=user collapsed it, leave it · `'1'`=expanded.
let BURN = null, BURN_AT = 0, BURN_BUSY = false, BURN_OPEN = true;
{ const bo = lsGet('sidereus.burn', null); if(bo !== null) BURN_OPEN = (bo === '1'); }
// BURNM = the non-primary «Main account»'s body (`?dir=`); BURN stays the primary's (drawer burndown, tokens).
let BURNM = null, BURNM_DIR = '';
function burnMainDir(){
  const m = mainAcct(), r = m ? (acctList() || []).find(a => a && !a.primary && String(a.label || '') === m) : null;
  return String((r && r.dir) || '');
}
// ⚠A non-primary main never falls back to BURN: missing/failed BURNM = null, so callers show nothing.
function burnFor(){
  if(!mainAcct()) return BURN;
  return BURNM && BURNM.ok && BURNM_DIR && BURNM_DIR === burnMainDir() ? BURNM : null;
}
// Account the modal burndown draws: explicit main, else the server's account in use (`use`, burn.burn_use) -> {label, dir}; dir '' = primary.
function burnUse(){
  const list = acctList() || [], u = BURN && BURN.use, m = mainAcct() || (u && !u.primary ? String(u.label || '') : '');
  const r = m ? list.find(a => a && !a.primary && String(a.label || '') === m) : null;
  const p = list.find(a => a && a.primary);
  return r && r.dir ? {label: String(r.label), dir: String(r.dir)} : {label: String((p && p.label) || ''), dir: ''};
}
// Body for the modal curve; null while a non-primary body is loading. ⚠Never the primary's curve for another account.
function burnDraw(){
  const d = burnUse().dir;
  if(!d) return BURN;
  return BURNM && BURNM_DIR === d ? burnAcctCur(BURNM) : null;
}
// A `?dir=` body carries only now_pct/left/pts: derive the window fields the curve needs (copy, from the body's own `at`).
function burnAcctCur(b){
  if(!(b && b.ok && b.cur && b.cur.left != null)) return b;
  const c = b.cur, reset = b.at + c.left, start = reset - 5*3600;
  return Object.assign({}, b, {cur: Object.assign({}, c, {reset: reset, start: start, elapsed: Math.max(0, b.at - start),
    pts: (c.pts && c.pts.length ? c.pts : [[b.at, c.now_pct]]).filter(q => q[0] >= start)})});
}
function burnTick(){
  const now = Date.now(), md = burnUse().dir;
  if(md !== BURNM_DIR){ BURNM = null; BURNM_DIR = md; BURN_AT = 0; }   // main/in-use account switched: drop the old body, refetch now
  if(BURN_BUSY || document.hidden || (BURN_AT && now - BURN_AT < 30000)) return;   // hidden: resumes on the visible poll
  BURN_BUSY = true; BURN_AT = now;
  const pm = md ? getJSON('/api/quota/burn?dir=' + encodeURIComponent(md))
    .then(b=>{ if(md === BURNM_DIR){ BURNM = b; buildBurn(); } }).catch(()=>{ if(md === BURNM_DIR) BURNM = null; }) : null;
  const pp = getJSON('/api/quota/burn')
    .then(b=>{ BURN = b; buildBurn(); }).catch(()=>{});
  Promise.all([pp, pm]).finally(()=>{ BURN_BUSY = false; });
}
const bnDur = sec => HM(Math.max(0, Math.round(sec/60)));
const bnHM = ts => CLK(new Date(ts*1000));
// Curve colour (current + extrapolation): red once the projection reaches 100%. Shared with the legend glyphs (burnCurve).
function burnCol(b){
  const pj = (b && b.proj) || {};
  return (pj.raw != null && pj.raw >= 100) ? thc('#e0725f', '#c11e32') : thc('#6fd39a', '#1a8a50');
}
// Projected run-out for the chart: {at, e} inside the window before reset · {none: 1} when projected but no run-out · null when not projected.
function burnOut(b){
  const c = b && b.cur, pj = (b && b.proj) || {};
  if(!c || pj.raw == null) return null;
  const e = pj.over_at ? pj.over_at - c.start : null;
  return (e != null && e < 5*3600 && (c.reset == null || pj.over_at < c.reset)) ? {at: pj.over_at, e: Math.max(0, e)} : {none: 1};
}
// Seconds into the 5h window -> SVG x (viewBox width BURN_W, 3-unit pad); shared by burnSvg and the HTML label row (burnOutLab).
const BURN_W = 200;
function burnX(e){ return 3 + Math.max(0, Math.min(5*3600, e))/(5*3600)*(BURN_W-6); }
// Small curve — **inline SVG**. No external library (this server runs offline).
// Solid=current cycle · dotted=median of past cycles · faint dashed=extrapolation of current slope.
function burnSvg(b){
  const c = b.cur, pj = b.proj || {}, base = (b.base && b.base.pts) || [];
  const band = (b.base && b.base.band) || [];
  const H = 46, P = 3, W = BURN_W, WIN = 5*3600, X = burnX;
  const Y = p => H-P - Math.max(0, Math.min(100, p))/100*(H-2*P);
  const d = pts => pts.map((q,i) => (i?'L':'M')+X(q[0]).toFixed(1)+' '+Y(q[1]).toFixed(1)).join(' ');
  const cur = c.pts.map(q => [q[0]-c.start, q[1]]);
  const col = burnCol(b);
  let pr = [[c.elapsed, c.now_pct]];
  if(pj.over_at) pr.push([pj.over_at - c.start, 100], [WIN, 100]);
  else pr.push([WIN, pj.raw == null ? c.now_pct : pj.raw]);
  let s = '<svg viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="none" aria-hidden="true">';
  s += '<line x1="'+P+'" y1="'+Y(100)+'" x2="'+(W-P)+'" y2="'+Y(100)+'" stroke="'+thc('#2a3340','#d0d5dc')+'" stroke-width=".7"/>';
  // ⚠Layer order: band → median → extrapolation → current. The band must be **at the bottom** so it does not cover the solid line.
  // (The server already filters samples/width — not re-judged here. See `base.why`)
  if(band.length >= 2){
    const up = band.map(q => [q[0], q[2]]);                       // p75 (upper)
    const dn = band.slice().reverse().map(q => [q[0], q[1]]);     // p25 (lower) — traced back to close
    s += '<path d="'+d(up)+' '+d(dn).replace('M','L')+' Z" fill="#5f6a7a" opacity=".16" stroke="none"/>';
  }
  if(base.length >= 2)
    s += '<path d="'+d(base)+'" fill="none" stroke="'+thc('#8b95a7','#61656c')+'" stroke-width="1.2" stroke-dasharray="2 2"/>';   // same colour as the legend ┄ (burnCurve)
  s += '<path d="'+d(pr)+'" fill="none" stroke="'+col+'" stroke-width="1" stroke-dasharray="3 3" opacity=".85"/>';
  const o = burnOut(b);   // ⚠non-scaling stroke: the SVG stretches (preserveAspectRatio none, 200px tall in the modal)
  if(o && o.at) s += '<line class=bnoutl x1="'+X(o.e).toFixed(1)+'" y1="'+P+'" x2="'+X(o.e).toFixed(1)+'" y2="'+(H-P)+'" stroke="'+thc('#e0725f','#c11e32')+'" stroke-width="1" stroke-dasharray="3 2" vector-effect="non-scaling-stroke"/>';
  if(cur.length >= 2)
    s += '<path d="'+d(cur)+'" fill="none" stroke="'+col+'" stroke-width="1.4" stroke-linejoin="round"/>';
  s += '<circle cx="'+X(c.elapsed).toFixed(1)+'" cy="'+Y(c.now_pct).toFixed(1)+'" r="1.8" fill="'+col+'"/>';
  return s + '</svg>';
}
