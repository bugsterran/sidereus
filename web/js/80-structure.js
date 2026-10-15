// ── Structure treemap (structure tab) ──────────────────────────────────────────────────────
// ★See by area «how a project grows» (2026-09-22: not raw line counts, but how the project
// grows, as a visualized structure).
// Scrub `/api/structure` snapshots (oldest→newest) with a slider and draw a squarify treemap on **one canvas**
// — outer cells=areas · inner cells=functions · area=line count · color=edit count (churn).
// ⚠**Paths only.** Chip labels are just the last folder name of `cwd`/`repos` —
// conversation content never goes on this screen (rule 1 of this file). Do not revert.
// ★Chips are **one project tier** (structure
// belongs to a project, and session chips labelled by cwd looked identical to project chips). The old session tier is gone.
// Projects = union of every live session's `cwd` + `repos`, most-touched first.
// ⚠The covered list is **already in** `sessions[].repos` of `/api/state`. An earlier note saying «repos
// is empty» was wrong (measured 2026-09-22: all 4 sessions had 1-2 each).
// Collecting only `cwd` drops the case "repo-A also needs repo-B" from the screen.
let STR = null;            // Response being viewed (one: that response as is · several: strBuild() merge)
const strCache = {};       // path → response. ★First fetch takes 1.5-4s, so the slider reads only this cache
let strAuto = 1;           // 1 = no project picked yet — the first session list picks the most recently active one
let strOn = [];            // ⚠Single-element array — only one project is on. Empty array = default path unknown
const strLoad = {};        // path → 1 (requesting). ★With several on, call **in parallel** and draw as they arrive
let strHome = '';
let strIdx = 0;            // Snapshot index being viewed
let strPlay = 0;           // Playback timer id (0 = stopped)
let strZoom = '';          // Area key being drilled into ('' = all)
let strErr = '';
let strRects = [];         // Coordinate→cell reverse index (hover). Scanning from the end puts function cells on top
let strNew = null;         // Set of function keys «newly created» in this snapshot
let strFlash = 0, strFlashT = 0, strRz = 0;
let strMs = 0;             // Last render ms — written in the ↻ tooltip (see by eye whether playback lags)
let strTests = 0;          // Code filter — 0 «Source» (default) · 1 «All» · 2 «Tests». Sent as `tests=0|1|only`
// ⚠Same storage key as the old «Include tests» checkbox: its '0'/'1' map to «Source»/«All» unchanged (migration).
{ const v = lsGet('mbStrTests', ''); strTests = (v === '1') ? 1 : (v === '2') ? 2 : 0; }
// ★Color axis — default is **"recent change"** (2026-09-22: too much gray, and clicking meant nothing).
// churn (edit count) is **overwhelmingly 0**, so the screen becomes one color
// — measured share of 0-edit cells: sidereus 64.3% · repo-B 87.5% · repo-A 83.2%.
// ⚠Do not create a new color family — both axes use `STR_COL` below (5-step blue) as is.
let strAxis = 'recent';
strAxis = (lsGet('mbStrAxis', '') === 'churn') ? 'churn' : 'recent';
// ★View mode — 'arch' (module map, 84j) · 'size' (treemap). Default 'arch'; a saved value other than 'size' (old 'rel') falls back to it.
let strMode = 'arch';
{ const m = tabGet('sidereus.strmd', ''); strMode = m === 'size' ? 'size' : 'arch'; }
let strFull = 0;           // Drilling into "+N more" = 1. Passed to the server as `full=1` to lift the area cap
let strPan = null;         // Open cell panel {ak, fk, name} · {ak, list:1, name} · null = closed
// ★Code/diff bodies go in a **popup** (#spop), not the panel (2026-09-22: show code in a popup,
// the screen is already narrow). The panel keeps only metrics, sparkline and child list.
let strPop = null;         // Cell shown in the popup {ak, fk} · null = closed
let strPanTab = 'code';    // Popup body — 'code' · 'diff'. **Switched** in one place
// ★Cell source cache — clicking the same cell again does not re-call the server (past points call git).
// Key is the request as is (project, file, line, point in time). ⚠No unbounded dict (max 400 lines per response).
const strSrc = {}, strSrcLoad = {};
const STR_SRC_KEEP = 80;
let strLastMap = null;     // Old server compat — function key → last-changed snapshot index (reconstructed from churn increase)
let strRO = null, strRaf = 0, strLastW = 0, strLastH = 0;   // Size tracking (ResizeObserver + rAF)
const STR_STEP = 600;      // Playback interval (ms)
// ⚠It used to be a **fixed** `STR_H = 470` (2026-09-22: use the whole screen, there is plenty of vertical room).
// ⇒ Height is read from `.strwrap`'s `clientHeight` on every render.
// Do not revert to a constant — the space below goes unused.
const STR_FONT = "-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Segoe UI',sans-serif";
// 5 churn levels (0 is lightest) — no new colors, uses this screen's blue family as is
const STR_COL = ['#1d2530', '#23405c', '#2c5f92', '#3d85c6', '#63a9e8'];
const STR_MORE = '#2b3038';   // Cell grouping functions omitted by the cap (60)

// ── squarify — implemented directly without a library (offline rule) ───────────────────
// Lay rows along the **short side** of the remaining cell, and close a row just before adding one more
// would worsen the «worst aspect ratio» (Bruls/Huizing/van Wijk 1999).
function strWorst(row, sum, side){
  if(!row.length || sum <= 0 || side <= 0) return Infinity;
  let mn = Infinity, mx = 0;
  for(let i = 0; i < row.length; i++){ const v = row[i].v; if(v < mn) mn = v; if(v > mx) mx = v; }
  if(mn <= 0) return Infinity;
  const s2 = sum * sum, d2 = side * side;
  return Math.max(d2 * mx / s2, s2 / (d2 * mn));
}
// items: [{v, d}] (v = line count). Accumulates {x,y,w,h,d} into out and returns it.
// ⚠Filter v<=0 and zero width **first** — division by 0 creates NaN cells, which break the hover reverse index entirely.
function strSquarify(items, x, y, w, h, out){
  out = out || [];
  const list = [];
  for(let i = 0; i < items.length; i++) if(items[i].v > 0) list.push(items[i]);
  if(!list.length || w <= 0.5 || h <= 0.5) return out;
  let sum = 0;
  for(let i = 0; i < list.length; i++) sum += list[i].v;
  if(sum <= 0) return out;
  const scale = (w * h) / sum;
  const q = list.map(it => ({ v: it.v * scale, d: it.d }));
  let rx = x, ry = y, rw = w, rh = h, i = 0, row = [], rs = 0;
  const flush = () => {
    if(!row.length) return;
    if(rw < rh){                       // Remaining cell is tall → lay the row horizontally
      const bh = Math.min(rh, rs / rw);
      let cx = rx;
      for(let k = 0; k < row.length; k++){
        const cw = bh > 0 ? row[k].v / bh : 0;
        out.push({ x: cx, y: ry, w: Math.max(0, Math.min(cw, rx + rw - cx)), h: bh, d: row[k].d });
        cx += cw;
      }
      ry += bh; rh -= bh;
    } else {                           // Wide → lay the row vertically
      const bw = Math.min(rw, rs / rh);
      let cy = ry;
      for(let k = 0; k < row.length; k++){
        const ch = bw > 0 ? row[k].v / bw : 0;
        out.push({ x: rx, y: cy, w: bw, h: Math.max(0, Math.min(ch, ry + rh - cy)), d: row[k].d });
        cy += ch;
      }
      rx += bw; rw -= bw;
    }
    if(rw < 0) rw = 0;
    if(rh < 0) rh = 0;
    row = []; rs = 0;
  };
  while(i < q.length){
    const side = Math.min(rw, rh);
    if(side <= 0.5) break;
    const it = q[i];
    if(!row.length){ row.push(it); rs += it.v; i++; continue; }
    if(strWorst(row.concat([it]), rs + it.v, side) <= strWorst(row, rs, side)){
      row.push(it); rs += it.v; i++;
    } else flush();
  }
  flush();
  for(; i < q.length; i++) out.push({ x: rx, y: ry, w: 0, h: 0, d: q[i].d });   // No room
  return out;
}
// Lay out one area group — outer cell=area · inner cells=functions.
// tight = **inside** a project cell (3 tiers), so padding/header shrink · zoom = one area uses the whole canvas.
function strLayArea(areas, X, Y, W, H, rects, tight, zoom){
  if(!areas.length || W <= 1 || H <= 1) return;
  const outer = [];
  if(zoom) outer.push({ x: X, y: Y, w: W, h: H, d: areas[0] });
  else strSquarify(areas.slice().sort((p, r) => r.lines - p.lines).map(a => ({ v: a.lines, d: a })),
                   X, Y, W, H, outer);
  const PAD = tight ? 1 : 2, HEAD = zoom ? 20 : (tight ? 12 : 15);
  for(let i = 0; i < outer.length; i++){
    const o = outer[i], a = o.d;
    rects.push({ x: o.x, y: o.y, w: o.w, h: o.h, a: a, area: true, tight: tight });
    const ix = o.x + PAD, iy = o.y + HEAD, iw = o.w - PAD * 2, ih = o.h - HEAD - PAD;
    if(iw <= 1 || ih <= 1) continue;
    const items = [], fns = a.fns || [];
    let used = 0;
    for(let k = 0; k < fns.length; k++){
      items.push({ v: fns[k].lines || 0, d: fns[k] });
      used += fns[k].lines || 0;
    }
    // ★«+N more» — line count of functions omitted by the area cap (60). Pretending they do not exist breaks the area sum.
    const restN = a.more || 0, restL = Math.max(0, (a.lines || 0) - used);
    // ★Per-file grey cells from `rest` (one blob said nothing). ⚠Only when its sum matches restL — else the old single cell.
    const rest = a.rest || [];
    if(restN > 0 && restL > 0 && rest.length && rest.reduce((s, x) => s + (x.lines || 0), 0) === restL)
      rest.forEach(x => { if((x.lines || 0) > 0) items.push({ v: x.lines, d: { more: x.n, rest: 1, file: x.file || '', etc: !!x.etc,
        files: x.files || 0, lines: x.lines, churn: -1,
        name: x.etc ? T('{n} other files · {m}').replace('{n}', x.files).replace('{m}', x.n)
                    : strShort(x.file) + ' · ' + U(x.n, '#') } }); });
    else if(restN > 0 && restL > 0)
      items.push({ v: restL, d: { more: restN, name: T('+{n} more', 'count').replace('{n}', restN), lines: restL, churn: -1 } });
    items.sort((p, r) => r.v - p.v);
    const inner = strSquarify(items, ix, iy, iw, ih, []);
    for(let k = 0; k < inner.length; k++)
      rects.push({ x: inner[k].x, y: inner[k].y, w: inner[k].w, h: inner[k].h,
                   a: a, f: inner[k].d, tight: tight });
  }
}
// Layout — with several projects on, **3 tiers** (project → area → function); with one, **exactly 2 tiers as before**.
// ⚠Do not change the 2-tier path. A measured regression comparison (32 snapshots × all/drilldown, 17,268 cells) confirmed
// «not a single cell's coordinates differ from the old layout» here.
function strLayout(snap, W, H){
  const rects = [];
  const areas = (snap.areas || []).filter(a => (a.lines || 0) > 0);
  if(!areas.length) return rects;
  if(strZoom){
    const z = areas.find(a => a.key === strZoom);
    if(z){ strLayArea([z], 0, 0, W, H, rects, false, true); return rects; }
  }
  const gs = (snap.projs || []).filter(g => (g.lines || 0) > 0);
  if(gs.length > 1){
    const outer = [];
    strSquarify(gs.slice().sort((p, r) => r.lines - p.lines).map(g => ({ v: g.lines, d: g })),
                0, 0, W, H, outer);
    const PAD = 2, HEAD = 16;
    for(let i = 0; i < outer.length; i++){
      const o = outer[i];
      rects.push({ x: o.x, y: o.y, w: o.w, h: o.h, g: o.d, proj: true });
      const ix = o.x + PAD, iy = o.y + HEAD, iw = o.w - PAD * 2, ih = o.h - HEAD - PAD;
      strLayArea((o.d.areas || []).filter(a => (a.lines || 0) > 0), ix, iy, iw, ih, rects, true, false);
    }
    return rects;
  }
  strLayArea(areas, 0, 0, W, H, rects, false, false);
  return rects;
}
// Newly created function — a name absent from the previous snapshot. This is the core of «how it grows», so its border differs.
// ⚠Because of the per-area cap (60), a function that rose in rank into the cap also looks «newly created».
function strNewSet(i){
  const s = new Set();
  if(!STR || !STR.snaps || i <= 0) return s;
  const prev = STR.snaps[i - 1], cur = STR.snaps[i];
  if(!prev || !cur) return s;
  const had = new Set();
  (prev.areas || []).forEach(a => (a.fns || []).forEach(f => had.add(strFk(a, f))));
  (cur.areas || []).forEach(a => (a.fns || []).forEach(f => {
    const k = strFk(a, f);
    if(!had.has(k)) s.add(k);
  }));
  return s;
}
// Function key — in the merged view, prefix the project (`a.pk`). Without it, functions of different projects
// sharing a filename make each other «already existing». With a single selection there is no `pk`, so the old key stays.
function strFk(a, f){ return ((a && a.pk) || '') + f.file + ':' + f.lang + ':' + f.name; }
const STR_COL_LT = ['#eef1f5', '#d3e3f5', '#a6c8ee', '#5b9be3', '#2f78d0'], STR_MORE_LT = '#dde1e6';   // light-theme twin of the same 5 steps
function strColor(lv){ return lv < 0 ? thc(STR_MORE, STR_MORE_LT) : thc(STR_COL, STR_COL_LT)[Math.min(STR_COL.length - 1, lv || 0)]; }
// ── Color levels ────────────────────────────────────────────────────────────────
// "Recent change" is cut **relatively** (against number of past snapshots). Snapshot counts differ per project
// (measured sidereus 21 · repo-B 11 · merged 30), so cutting by absolute count makes one side wholly bright or dark.
const STR_AGE = [0, 0.1, 0.25, 0.6];   // At or below these ratios: levels 4·3·2·1 · above: 0 (darkest)
// In the merged view each project has a different «snapshot index being viewed» — `strBuild()` attaches it to the area.
function strSi(a){ return (a && a.si != null) ? a.si : strIdx; }
// Index of the snapshot where it last changed. The server attaches `last`; if absent (old server), reconstruct from churn increase.
function strLastOf(a, f){
  if(f.last != null) return f.last;
  const v = strLastMap ? strLastMap.get(strFk(a, f)) : undefined;
  return (v === undefined) ? 0 : v;
}
function strLevel(a, f){
  if(f.more) return -1;
  if(strAxis === 'churn') return Math.min(STR_COL.length - 1, f.churn || 0);
  const si = strSi(a);
  if(si <= 0) return STR_COL.length - 1;          // In the first snapshot everything is «just created»
  const age = (si - strLastOf(a, f)) / si;
  for(let i = 0; i < STR_AGE.length; i++) if(age <= STR_AGE[i]) return STR_COL.length - 1 - i;
  return 0;
}
// ⚠Old-server compat only — when `last` arrives this map is unused. churn is monotonic, so
// «snapshot where the value changed» is «when it changed» (first appearance counts as a change).
function strLastScan(){
  const m = new Map(), snaps = (STR && STR.snaps) || [], prev = new Map();
  for(let j = 0; j < snaps.length; j++)
    (snaps[j].areas || []).forEach(a => (a.fns || []).forEach(f => {
      const k = strFk(a, f), c = f.churn || 0;
      if(prev.get(k) !== c){ m.set(k, j); prev.set(k, c); }
    }));
  return m;
}
function strShort(p){ const i = p.lastIndexOf('/'); return i >= 0 ? p.slice(i + 1) || p : p; }
// Project chips — union of `cwd` + `repos` over live sessions; `ss` = sessions touching it (folder · model only, rule 1).
function strProjList(){
  const m = new Map(), seen = new Set();
  const get = p => { let e = m.get(p); if(!e){ e = { p: p, ss: [], open: 0 }; m.set(p, e); } return e; };
  (SESS || []).forEach(x => {
    if(!x || !x.cwd || !x.id || seen.has(x.id)) return;
    seen.add(x.id);
    const who = strShort(x.cwd) + (x.model ? ' · ' + x.model : '');
    // ⚠SESS keeps ended sessions (state 'done'); `open` counts only live ones — the picker's «Working» uses it.
    // ⚠Deleted worktrees leave sessions behind — their folders get no chip (server `projGone`).
    new Set([x.root || x.cwd].concat(x.repos || [])).forEach(p => { if(p && !PROJ_GONE.has(p)){ const e = get(p); e.ss.push(who); if(x.state !== 'done') e.open++; } });
  });
  [strOn[0], strHome].forEach(p => { if(p && !PROJ_GONE.has(p)) get(p); });   // the selection and sidereus itself always have a chip
  const out = [...m.values()], cnt = {};
  out.forEach(e => { e.name = strShort(e.p); cnt[e.name] = (cnt[e.name] || 0) + 1; });
  // Same last folder name in two projects — prefix the parent folder (parent/child).
  out.forEach(e => { if(cnt[e.name] > 1) e.name = strShort(e.p.slice(0, e.p.lastIndexOf('/'))) + '/' + e.name; });
  return out.sort((a, b) => b.ss.length - a.ss.length || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
}
function strProjs(){ return strProjList().map(e => e.p); }
// Default = cwd of the most recently active session (smallest ageSec); null while no session has arrived.
function strDefProj(){
  let best = null;
  (SESS || []).forEach(x => { if(x && x.cwd && x.id && !PROJ_GONE.has(x.cwd) && (!best || (x.ageSec == null ? Infinity : x.ageSec)
                                  < (best.ageSec == null ? Infinity : best.ageSec))) best = x; });
  return best ? (best.root || best.cwd) : null;   // root = git root of cwd (a subfolder cd is the same project)
}
// ⚠Picks once — re-picking on every poll would jump projects under the user as ageSec shifts.
function strPickDef(){
  if(strOn[0] && PROJ_GONE.has(strOn[0])){ strStop(); strOn = []; strAuto = 1; }   // selected folder deleted -> back to the default pick
  if(!strAuto) return;
  const w = tabGet('sidereus.strp', ''), d = (w && strProjs().indexOf(w) >= 0) ? w : strDefProj();   // last chosen project wins while it is still listed
  if(!d) return;
  strAuto = 0;
  if(strOn[0] !== d){ strStop(); strOn = [d]; strZoom = ''; strErr = ''; strRebuild(true); }
}
// ⚠Boot paints this tab before the first /api/state (SESS = []), so the chips came out incomplete until a tab switch.
//   The poll (95-poll.js) compares this key with the one last painted and repaints on change (sessions starting/ending).
let strSessSig = '';
function strSessKey(){ return (SESS || []).map(x => x ? (x.id + '\t' + x.cwd + '\t' + (x.repos || []).join('|')) : '').join('\n') + '\n' + [...PROJ_GONE].join('|'); }
// Cache key — path + "include tests" value. ⚠Without `tests`, toggling off and on returns **old results**.
// The toggle may change while the response is in flight, so the request-time value (t) is passed and stored under the same key.
// ⚠`full` (drilldown cap lifted) is also part of the key — without it the expanded result leaks into the full view.
function strCk(p, t, fl){ return (p || '') + '\n' + ((t === undefined ? strTests : t) | 0)
                                 + '\n' + (((fl === undefined ? strFull : fl)) ? 1 : 0); }
// If the expanded response has not arrived, **keep drawing the capped old response** — do not show a blank screen.
function strCacheGet(p){
  return strCache[strCk(p)] || (strFull ? strCache[strCk(p, strTests, 0)] : null) || null;
}
// ── Several projects in one treemap ────────────────────────────────────────────
// Time axis: the **union** of snapshot times of the enabled projects; each project uses «the latest snapshot at or before
// that time» (step-wise). Needed because each project's snapshot times differ
// (measured 2026-09-22: sidereus 21 from 9/2 · repo-A 11 from 2017.8 → union 30).
// ⚠At times earlier than a project's first snapshot, **drop it instead of drawing 0** — it did not exist then.
// Leaving 0 reads as «existed but was empty».
function strPick(snaps, t){          // Last snapshot index with at <= t (-1 if none)
  let j = -1;
  for(let k = 0; k < snaps.length; k++){ if((snaps[k].at || 0) <= t) j = k; else break; }
  return j;
}
function strBuild(){
  const src = [];
  for(let i = 0; i < strOn.length; i++){
    const c = strCacheGet(strOn[i]);
    if(c && c.ok && (c.snaps || []).length) src.push({ p: strOn[i], snaps: c.snaps, c: c });
  }
  if(!src.length) return null;
  if(src.length === 1) return src[0].c;                    // ★With one, the response **as is** — no 2-tier regression
  // ⚠The merged path below is not used now (single project selection, 2026-09-22). Use it if multi-select is needed again.
  const seen = new Set(), ts = [];
  src.forEach(x => x.snaps.forEach(s => { const t = s.at || 0;
    if(!seen.has(t)){ seen.add(t); ts.push(t); } }));
  ts.sort((a, b) => a - b);
  const snaps = ts.map(t => {
    const areas = [], projs = [];
    let total = 0, partial = false, label = '';
    // Exclusion totals (libraries, tests) are **merged** too — missing from the merge, the header numbers would be one project's only
    const ex = { vendor: 0, vendorLines: 0, test: 0, testLines: 0, core: 0, coreLines: 0 };
    let exOn = false;
    for(let i = 0; i < src.length; i++){
      const x = src[i], j = strPick(x.snaps, t);
      if(j < 0) continue;                            // Period before it existed
      const s = x.snaps[j], nm = strShort(x.p), pk = x.p + '';
      if(!label && (s.at || 0) === t) label = s.label || '';
      total += s.total || 0;                         // total = sum over enabled projects
      if(s.partial) partial = true;
      const xe = s.excluded;
      if(xe){ exOn = true; ex.vendor += xe.vendor || 0; ex.vendorLines += xe.vendorLines || 0;
              ex.test += xe.test || 0; ex.testLines += xe.testLines || 0;
              ex.core += xe.core || 0; ex.coreLines += xe.coreLines || 0; }
      const my = [];
      let ln = 0;
      (s.areas || []).forEach(a => {
        if((a.lines || 0) <= 0) return;
        // Prefix area keys with the project — drilldown (strZoom) must not cross projects
        // ★`si` = that project's **own snapshot index**. The "recent change" color axis and info panel
        // measure age as `si - last` — using the merged index (j) would drift per project.
        my.push({ key: pk + a.key, name: strAreaNm(a), lines: a.lines, n: a.n, si: j,
                  more: a.more, rest: a.rest, fns: a.fns, pk: pk, pname: nm, test: a.test === true });
        ln += a.lines || 0;
      });
      areas.push.apply(areas, my);
      projs.push({ path: x.p, name: nm, lines: ln, areas: my, at: s.at || 0, label: s.label || '' });
    }
    return { at: t, label: label, src: projs.length + ' merged',   // label key, translated by strSrcTxt (82-structure-canvas.js) total: total,
             partial: partial, areas: areas, projs: projs,
             excluded: exOn ? ex : null };
  });
  return { ok: true, merged: true, path: '', snaps: snaps };
}
// Rebuild STR whenever the enabled list or cache changes. If viewing the end («current»), stay at the end.
function strRebuild(toEnd){
  const old = (STR && STR.snaps) || [];
  const end = !old.length || strIdx >= old.length - 1;
  STR = strBuild();
  const n = ((STR && STR.snaps) || []).length;
  strIdx = (toEnd || end) ? Math.max(0, n - 1) : Math.max(0, Math.min(strIdx, n - 1));
  const cur = ((STR && STR.snaps) || [])[strIdx];
  if(strZoom && !(cur && (cur.areas || []).some(a => a.key === strZoom))) strZoom = '';
  strNew = strNewSet(strIdx);
  strLastMap = strLastScan();
  strFlash = 0;
}
// ★Call each project **separately** and store in `strCache[path]` as is. Already-received ones are not refetched.
// Server cold start is 1.5-4s per project; waiting for all prolongs the blank screen — draw as they arrive.
function strFetch(p, force){
  // ★Carry the request-time tests/full values along — the toggle may change while the response is in flight
  const tv = strTests | 0, fv = strFull ? 1 : 0, k = strCk(p, tv, fv);
  if(!force && p && strCache[k]) return;
  if(strLoad[k]) return;
  strLoad[k] = 1;
  getJSON('/api/structure' + (p ? '?path=' + encodeURIComponent(p) + '&' : '?')
        + 'tests=' + (tv === 2 ? 'only' : tv) + '&full=' + fv)
    .then(j => {
      delete strLoad[k];
      if(!j || !j.ok) strErr = (j && j.msg) ? TV(j) : T('Could not fetch');   // already translated text
      else {
        if(!p && j.path){ strHome = j.path; if(!strOn.length) strOn = [j.path]; }
        // Cache the default-path response under its **real path** too
        strCache[strCk((!p && j.path) ? j.path : p, tv, fv)] = j;
        strErr = '';
      }
      strRebuild(false);
      if(mainView === 'struct') paintStruct();
    })
    .catch(() => { delete strLoad[k]; strErr = T('Could not fetch — check the server');
                   if(mainView === 'struct') paintStruct(); });
}
function loadStruct(force){
  strPickDef();
  if(!strHome && !strOn.length){ strFetch('', force); return; }   // Learn the default path from the response
  if(!strOn.length){ const ps = strProjs(); if(ps.length) strOn = [ps[0]]; }
  strOn.forEach(p => strFetch(p, force));                          // It is a single-element array
}
function strStop(){ if(strPlay){ clearInterval(strPlay); strPlay = 0; } }
// ★Branch badge beside «Source» — page data first (strBrPick fetches only when none):
//   session rows of this cwd (branch, git "↑N ~M"); the Branches tab response (BR) adds the detached sha and ↓behind when it is this repo's.
function strBrRows(n, sess){
  return (sess || []).filter(x => x && (brNorm(x.cwd) === n || (x.wt && brNorm(x.wt.root) === n)));
}
function strBrInfo(p, sess, br){
  const n = brNorm(p), age = x => (x.ageSec == null ? 1e12 : x.ageSec);
  if(!n) return null;
  // ⚠A row counts only when its cwd's git root is this repo — a `repos`-only row's branch/git describe its own cwd, not p.
  const rows = strBrRows(n, sess).sort((a, b) => age(a) - age(b));
  const r = rows.find(x => x.branch) || rows.find(x => x.git) || null;
  const own = !!(br && br.ok && brNorm(br.cwd) === n);
  if(!r && !own) return null;       // non-git project (or nothing known yet) -> no badge
  const g = String((r && r.git) || ''), num = re => { const m = re.exec(g); return m ? +m[1] : 0; };
  const o = { name: (r && r.branch) || '', sha: '', ahead: num(/↑(\d+)/), behind: 0, dirty: num(/~(\d+)/) };
  if(own && br.detached){ o.name = ''; o.sha = String(br.head || '').slice(0, 7); }
  else if(own && br.head){
    o.name = br.head;
    const b = (br.branches || []).find(x => x && x.kind === 'local' && x.name === br.head);
    if(b && b.upstream){ o.ahead = b.ahead | 0; o.behind = b.behind | 0; }
  }
  return o;
}
function strBrBadge(o, id){
  if(!o) return '';
  const nm = o.name || ('detached' + (o.sha ? ' @ ' + o.sha : ''));
  const ab = (o.ahead ? '↑' + o.ahead : '') + (o.ahead && o.behind ? ' ' : '') + (o.behind ? '↓' + o.behind : '');
  const tip = T('Branches') + ': ' + nm + (o.ahead ? ' · ' + T('Unpushed') + ' ' + o.ahead : '')
    + (o.behind ? ' · ' + T('behind') + ' ' + o.behind : '') + (o.dirty ? ' · ' + T('changed files') + ' ' + o.dirty : '')
    + '\n' + T('Click to open this repo in the Branches tab');
  return '<em class="tlrf strbr" id=' + (id || 'strbr') + ' title="' + esc(tip) + '"><i class=strbrn>' + esc(nm) + '</i>'
    + (ab ? '<small class=strbra>' + esc(ab) + '</small>' : '')
    + (o.dirty ? '<small class=strbrd>● ' + esc(o.dirty) + '</small>' : '') + '</em>';
}
let strBrH = '';
// Fallback for a repo with no session row and no Branches-tab data: one /api/branches?n=80 per path (same cache key as the Branches tab, so br_warm keeps one key per repo), re-fetched at most every 60 s.
//   ⚠A failure (403/non-git/network) is cached too — no badge, no retry storm.
const STR_BRF = {};
function strBrPick(p, sess, br, cache, now, get){
  const n = brNorm(p);
  if(!n || (br && br.ok && brNorm(br.cwd) === n) || strBrRows(n, sess).length) return br;
  let e = cache[n];
  if(!e || (!e.busy && now - e.at > 60000)){ e = cache[n] = { at: now, br: e ? e.br : null, busy: 1 }; get(p, e); }
  return e.br || br;
}
function strBrGet(p, e){
  const n = brNorm(p), done = j => { e.busy = 0; e.at = Date.now(); e.br = j; strBrSync(); };
  fetch('/api/branches?cwd=' + encodeURIComponent(p) + '&n=80', { cache: 'no-store' })
    .then(r => (r.ok ? r.json() : null))
    .then(j => done(j && j.ok ? { ok: true, cwd: n, head: j.head, detached: !!j.detached,
      branches: (j.branches || []).filter(b => b && b.kind === 'local' && b.name === j.head) } : null))
    .catch(x => { softErr('strbr-fetch', x); done(null); });
}
function strBrHtml(){
  const p = strOn[0] || (STR && STR.path) || '';
  return strBrBadge(strBrInfo(p, SESS, strBrPick(p, SESS, BR, STR_BRF, Date.now(), strBrGet)));
}
// Poll hook: swap only the badge when it changes (a toolbar repaint would drop the search input's focus).
function strBrSync(){
  strTreeBrSync();                            // the «Source» popup header carries the same badge
  const sv = document.getElementById('strsrc');
  if(!sv) return;
  const h = strBrHtml(), cur = document.getElementById('strbr');
  if(h === strBrH && !!cur === !!h) return;   // ⚠compare the source string — outerHTML re-serialises attributes
  strBrH = h;
  if(cur) cur.remove();
  if(h){ sv.insertAdjacentHTML('afterend', h); strBrWire(); }
}
// Structure headers show counts as tinted badges (.strbg-* in 75, same hue as the diagram).
function strHdBadge(cls, txt, tip){ return '<em class="strbg' + (cls ? ' strbg-' + cls : '') + '"' + (tip ? ' title="' + esc(tip) + '"' : '') + '>' + esc(txt) + '</em>'; }
function paintStruct(){
  if(mainView !== 'struct') return;
  const box = document.getElementById('feed');
  if(!box) return;
  strPickDef();
  const on = {};
  strOn.forEach(p => { on[p] = 1; });
  strSessSig = strSessKey();
  // One tier — projects (single selection); a count shows when more than one session touches it.
  // Chip row (selection · working · recent) + «Projects ▾» picker (08b); run = a pipeline running there (48).
  const run = typeof plLiveProjs === 'function' && typeof PLS === 'object' ? plLiveProjs(SESS, plMem(), plKnown()) : {};
  const items = strProjList().map(e => Object.assign({}, e, { live: e.open > 0, run: !!run[e.p] }));
  const pChips = ppChipsHtml({ k: 'str', label: T('Project'), items: items, cur: strOn[0] || '', rkey: 'sidereus.strrecent', pick: strPickProj,
    chip: e => { const p = e.p, ld = strLoad[strCk(p)];
    return '<button class="strp' + (on[p] ? ' on' : '') + (ld ? ' strld' : '')
    + '" data-sp="' + esc(p) + '" title="' + esc(p + (e.ss.length ? '\n' + T('Sessions') + ' ' + e.ss.length + ': ' + e.ss.join(', ') : '')
    + (ld ? ' — ' + T('loading') : '')) + '">' + esc(e.name)
    + (e.ss.length > 1 ? ' <small class=strpc>' + e.ss.length + '</small>' : '')
    + (ld ? ' …' : '') + '</button>'; } });
  // Project chips and ↻ live in the header toolbar slot (strWire wires both the slot and #feed).
  // ★2026-09-29 the screen flickered: chip titles list session names, so every session change rewrote the slot.
  //   ⇒ Once the slot exists it is patched (morphHtml), not rebuilt.
  const tsl = document.getElementById('tbstruct'), tbh = '<span class="strps tbg">' + pChips + '</span>'
    + '<span class=tbx><em class="tlrf strsrcb" id=strsrc title="' + esc(T('File tree and source')) + '">' + esc(T('Source', 'code')) + '</em>'
    + (strBrH = strBrHtml())
    + '<em class=tlrf id=strrf title="'
    + esc(T('Reload now') + (strMs ? ' · ' + T('last render') + ' ' + strMs + 'ms' : '')) + '">↻</em></span>';
  // ⚠Skip the patch while the picker is open: a poll morph would rewrite its opener and the list under the caret.
  if(tsl){ if(!popIsOpen('ppop')) morphHtml(tsl, tbh); } else tbSlot('struct', tbh);
  // Legend text **changes with the axis** — without saying what color means on screen, it means nothing
  const rec = (strAxis !== 'churn');
  // ⚠The selects also render in loading/error/empty states — a «Tests» filter on a project with no tests
  //   would otherwise leave an empty screen with no way to switch back.
  // ⚠Selects go before the switch: .strctl is right-anchored, so «Size»-only selects after it shifted the switch sideways.
  const ctl = ('<label class="strck straxw" title="'
    + esc(T('Last change = how recent the snapshot it last changed in is · Edit count = cumulative churn')) + '">' + esc(T('Color'))
    + '<select id=strax><option value=recent' + (rec ? ' selected' : '') + '>' + esc(T('Last change')) + '</option>'
    + '<option value=churn' + (rec ? '' : ' selected') + '>' + esc(T('Edit count')) + '</option></select></label>')
    // ★Code filter — replaced the «Include tests» checkbox.
    //   Each value is its own server variant (`tests=0|1|only`, different cache key) — switching refetches.
    + '<label class="strck straxw" title="' + esc(T('Source = main code without tests · All = source + tests · Tests = test code only'))
    + '">' + esc(T('Code')) + '<select id=strtf>'
    + [[0, 'Source'], [1, 'All'], [2, 'Tests']].map(o => '<option value=' + o[0] + (strTests === o[0] ? ' selected' : '')
        + '>' + esc(T(o[1])) + '</option>').join('') + '</select></label>';
  const seg = '<span id=strmd class=strseg title="' + esc(T('Architecture = module diagram · Size = line-count treemap')) + '">'
    + [['arch', 'Architecture'], ['size', 'Size']].map(o => '<button data-m' + (o[0] === 'arch' ? 'a' : 'd') + '=' + o[0] + (strMode === o[0] ? ' class=on' : '')
        + ' data-t="' + esc(T(o[1])) + '">'   // data-ma: wired in 84j · data-t: bold-width reserve (79-structure-arch.css)
        + esc(T(o[1])) + '</button>').join('') + '</span>';
  // ★Selects sit right-aligned on the view's title line
  //   (at the bottom-right above the replay bar they were 65x21px and went unnoticed). Every state uses head(), so they stay.
  // pre = html placed immediately left of the switch (84j: «Run project checks»).
  const head = (note, ex, pre) => '<div class="wvh wvht strh"><span>' + note + '</span>'
    + '<div class=strctl>' + ctl + (pre || '') + seg + '</div></div>' + (ex || '');
  if(strMode === 'arch'){ archPaint(box, head); return strWire(); }
  if(strErr && !STR){ box.innerHTML = head('') + '<div class="tlhd cwerr">' + esc(strErr) + '</div>';
                      return strWire(); }
  if(!STR && strOn.length) loadStruct(false);   // the poll skips this fetch in «Architecture» (95-poll), so «Size» asks on its first paint
  if(!STR){ box.innerHTML = head(esc(T('Loading…')))
      + '<div class=strload><b>' + esc(T('Reading the structure…')) + '</b><br>' + esc(T('Past snapshots are scanned too — the first pass takes 2-4s.')) + '</div>';
    return strWire(); }
  const snaps = STR.snaps || [];
  if(!snaps.length){ box.innerHTML = head('') + '<div class=strload>' + esc(T('No structure to read at this path.')) + '</div>';
                     return strWire(); }
  const snap = snaps[Math.min(strIdx, snaps.length - 1)];
  const zn = strZoom ? (snap.areas || []).find(a => a.key === strZoom) : null;
  const lgLab = (rec ? ['Long ago', '', '', '', 'Recent'] : ['0', '1', '2', '3', '4+']).map(x => T(x));
  const legend = '<div class=strlg><span>' + esc(T('Area = lines · Color =')) + ' '
    + esc(T(rec ? 'Last change' : 'Edit count')) + '</span>'
    + STR_COL.map((c, i) => '<i style="background:' + strColor(i) + '"></i><u>' + esc(lgLab[i]) + '</u>').join('')
    + '<i style="background:' + strColor(-1) + '"></i><u>' + esc(T('Over the cap — click to expand')) + '</u>'
    + '<i class=strnw></i><u>' + esc(T('New')) + '</u>'
    + (strTests === 1 ? '<i class=strts></i><u>' + esc(T('Tests')) + '</u>' : '')
    + '</div>';
  const note = (zn ? esc((zn.pname ? zn.pname + ' · ' : '') + zn.name)
                     + ' ' + esc(T('only')) + (strFull ? esc(T('(expanded)')) : '') + ' ' + esc(T('— click outside the box for the whole view'))
                   : esc(T('Click an area box to zoom in with its code list · click a function box for its code')))
    + ' ' + strHdBadge('', T('{n} snapshots').replace('{n}', snaps.length))
    + (STR.merged ? strHdBadge('', T('{n} projects merged').replace('{n}', ((snap.projs || []).length))) : '');
  // ⚠A folded area list sits inside the map, on the zoomed area's empty 20px header band: as its own row it still cost
  //   the map 38-73px on a drill-down (75-structure.css `.strwrap > .strpnC`).
  const pnl = strPanel(snap), pnIn = pnl.indexOf('strpnC') >= 0;
  // ⚠The repaint replaces .strpnc; keep its scroll or a row click jumps the area list to the top.
  const pnOld = box.querySelector('.strpnc'), pnTop = pnOld ? pnOld.scrollTop : 0;
  box.innerHTML = '<div class=strtab>' + head(note, strExLine(snap))
    + '<div class=strwrap><canvas id=strcv></canvas><div class=strtip id=strtip></div>' + (pnIn ? pnl : '') + '</div>'
    // ★The panel is **outside the canvas** — once it holds code, it gets its own cell so it does not cover the treemap.
    + (pnIn ? '' : pnl)
    + legend
    + '<div class=strbar>'
    + '<button class=strpl id=strpl title="' + esc(T(strPlay ? 'Stop' : 'Replay the growth every 0.6s'))
    + '">' + esc(T(strPlay ? '■ Stop' : '▶ Play')) + '</button>'
    + '<input type=range class=strrg id=strrg min=0 max="' + (snaps.length - 1) + '" value="'
    + Math.min(strIdx, snaps.length - 1) + '"' + (snaps.length < 2 ? ' disabled' : '') + '>'
    + '<span class=strlb id=strlb></span>'
    + '<b class=strtt id=strtt></b><em>' + esc(T('lines')) + '</em></div></div>';
  const pnNew = pnTop && box.querySelector('.strpnc');
  if(pnNew) pnNew.scrollTop = pnTop;
  strWire();
  strSyncBar();
}
// ★A line answering «why is it not visible» — the header states how many libraries/tests (files and lines) were excluded.
// ⚠Old servers do not send `excluded` — if the key is missing, omit that piece entirely (compat).
function strExLine(snap){
  const e = (snap && snap.excluded) || null;
  if(!e) return '';
  const n = v => (v || 0).toLocaleString(), bits = [];
  if(e.vendor) bits.push(T('{n} library files, {m} lines').replace('{n}', n(e.vendor)).replace('{m}', n(e.vendorLines)));
  if(!strTests && e.test) bits.push(T('{n} test files, {m} lines').replace('{n}', n(e.test)).replace('{m}', n(e.testLines)));
  if(strTests === 2 && e.core) bits.push(T('{n} source files, {m} lines').replace('{n}', n(e.core)).replace('{m}', n(e.coreLines)));
  return bits.length ? '<div class=strex><b>' + esc(T('Excluded')) + '</b>: ' + esc(bits.join(' · ')) + '</div>' : '';
}
// ── Cell info panel ──────────────────────────────────────────────────────────────
// ★Clicking a function cell shows that cell's **metadata** (2026-09-22: clicks meant nothing and there was too much gray).
// It holds only file:line · language · line count · edit count ·
// when it last changed · per-snapshot line count sparkline.
// ⚠**Do not include source bodies** — the target is another project's file (rule 1 of this file: metadata only).
function strSnapsOf(a){       // In the merged view, **that project's own** snapshot array — labels are read from there
  if(a && a.pk){ const c = strCacheGet(a.pk); if(c && c.snaps) return c.snaps; }
  return (STR && STR.snaps) || [];
}
// Line count per snapshot. ⚠Cells not included at that point due to the cap (60) are `null` — 0 would read as «disappeared».
// The sparkline breaks the line there.
function strSeries(ak, fk){
  const snaps = (STR && STR.snaps) || [], out = [];
  for(let j = 0; j < snaps.length; j++){
    let v = null;
    const ars = snaps[j].areas || [];
    for(let i = 0; i < ars.length; i++){
      if(ars[i].key !== ak) continue;
      const fns = ars[i].fns || [];
      for(let k = 0; k < fns.length; k++)
        if(!fns[k].more && strFk(ars[i], fns[k]) === fk){ v = fns[k].lines || 0; break; }
      break;
    }
    out.push(v);
  }
  return out;
}
// Small polyline — one inline SVG, no library (offline rule). A dot marks the point being viewed.
function strSpark(vals, cur){
  const W = 268, H = 34, n = vals.length;
  if(n < 2) return '';
  let mx = 0;
  for(let i = 0; i < n; i++) if(vals[i] != null && vals[i] > mx) mx = vals[i];
  if(mx <= 0) mx = 1;
  const px = i => (i * (W - 2) / (n - 1)) + 1;
  const py = v => H - 2 - (v / mx) * (H - 6);
  let d = '', pen = 0;
  for(let i = 0; i < n; i++){
    const v = vals[i];
    if(v == null){ pen = 0; continue; }
    d += (pen ? 'L' : 'M') + px(i).toFixed(1) + ' ' + py(v).toFixed(1) + ' ';
    pen = 1;
  }
  const cv = (cur >= 0 && cur < n) ? vals[cur] : null;
  return '<svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio=none>'
    + '<path d="' + d + '" fill=none stroke="#63a9e8" stroke-width=1.4 '
    + 'stroke-linejoin=round vector-effect=non-scaling-stroke></path>'
    + (cv == null ? '' : '<circle cx=' + px(cur).toFixed(1) + ' cy=' + py(cv).toFixed(1)
        + ' r=2.6 fill="' + thc('#ffe7a8', '#b57f00') + '"></circle>') + '</svg>';
}
