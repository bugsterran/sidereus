// ── Structure «Architecture» focus view as HTML rows (a clicked module): boxes in layer-band rows + an SVG connector overlay ──
// ⚠Called from 84j behind typeof guards; no top-level reads of other files' names. Owns archFh* / ARCH_FH only.
// Markup keeps the 81e tag-mode contract: boxes [data-p] (hub data-on), edges .mmdfe[data-f/t/k/c] with a .mmdel.mmdfl badge,
// so 84j archDgClick, 84j4 archFocusClick/archFocusHx, 84j archHovPaint and 84j3 archLitPaint work on the .archfh root unchanged.
// ⚠Names, entry labels and step numbers are agent data: esc() only, never T().
const ARCH_FH = { LS: 14, GS: 12, G0: 12, ROW: 28, SUB: 14, PAD: 16, RV: 5, PS: 10 };   // px: lane step · gutter lane step · gutter offset · min band gap · min sub-row gap · min side pad · two-way neighbour split · min port step
// Pure: what the focus rows draw from an 84j4 plan. ⚠No flow lit: only edges touching the hub (entry/ifx edges into it included), so far
// modules never appear. A lit flow keeps every numbered step edge and its entry too — the person follows the whole flow.
// Rows = band index (entries 0, ifx P.fl, external bp.n, unknown layer bp.n+1); v1 (no layers): callers / hub / callees.
// Inside a row: first lit step, then in · both · hub · out, then name — so a lit flow reads left to right.
function archFhPlan(P, v1){
  const own = (o, k) => Object.prototype.hasOwnProperty.call(o, k), km = {}, ek = {}, sk = P.sk, num = P.num || {}, io = P.io || {};
  const fs = new Set((P.fs || []).map(String));
  (P.ms || []).forEach(m => { km['m' + P.ix[m.id]] = m; });
  (P.ents || []).forEach(e => { ek[e.k] = e; });
  const id = k => own(km, k) ? km[k].id : null;
  const steps = (a, b) => { const x = id(a), y = id(b); return x == null || y == null ? null : num[x + '\u0001' + y] || num[y + '\u0001' + x] || null; };
  const litEnt = k => fs.size > 0 && own(ek, k) && (ek[k].flows || []).some(f => fs.has(String(f)));
  const es = (P.edges || []).filter(e => e.a === sk || e.b === sk || (fs.size > 0 && (!!steps(e.a, e.b) || litEnt(e.a))));
  const keep = new Set([sk]), first = {}, lo = (k, v) => { first[k] = Math.min(own(first, k) ? first[k] : Infinity, v); };
  es.forEach(e => { keep.add(e.a); keep.add(e.b); const s = steps(e.a, e.b);
    if(s && s.size){ const v = Math.min(...s); lo(e.a, v); lo(e.b, v); } else if(litEnt(e.a)) lo(e.a, 0); });
  const band = k => { if(v1) return k === sk ? 1 : io[k] === 'in' ? 0 : 2;
    if(own(ek, k)) return 0;
    if(k === 'ifx') return P.fl;
    const b = own(km, k) ? P.bp.of(km[k]) : -1; return b >= 0 ? b : P.bp.n + 1; };
  const lbl = b => v1 ? (b === 0 ? T('In') : b === 2 ? T('Out') : '') : b > P.bp.n ? '' : P.bp.lbl(b);
  const IOR = { in: 0, both: 1, out: 2 }, ior = k => k === sk ? 1.5 : own(IOR, io[k]) ? IOR[io[k]] : 3;
  const name = k => own(km, k) ? String(km[k].name || km[k].id) : own(ek, k) ? String(ek[k].label || '') : '';
  const by = {};
  keep.forEach(k => { if(k === sk || own(km, k) || own(ek, k) || (k === 'ifx' && P.fold)){ const b = band(k); (by[b] = by[b] || []).push(k); } });
  const fk = k => own(first, k) ? first[k] : Infinity;
  const rows = Object.keys(by).map(Number).sort((a, b) => a - b).map(b => ({ b, lbl: lbl(b), ks: by[b].sort((x, y) =>
    fk(x) - fk(y) || ior(x) - ior(y) || (name(x) < name(y) ? -1 : name(x) > name(y) ? 1 : 0) || (x < y ? -1 : x > y ? 1 : 0)) }));
  // ⚠One band in a single line made every hub link a U-turn through the gap above (stacked lanes, direction only at the arrow head).
  // ⇒ the hub's band splits into three lines: callers only above, the hub alone, the rest (callees, two-way, flow-only) below.
  if(!v1){ const cr = new Set(es.filter(e => e.b === sk).map(e => e.a)), ce = new Set(es.filter(e => e.a === sk).map(e => e.b));
    rows.forEach(r => { if(!r.ks.includes(sk) || r.ks.length < 2) return;
      const o = r.ks.filter(k => k !== sk), up = o.filter(k => cr.has(k) && !ce.has(k)), dn = o.filter(k => !(cr.has(k) && !ce.has(k)));
      r.sp = [up, [sk], dn].filter(a => a.length); r.ks = [].concat(...r.sp); }); }
  return { rows, edges: es.filter(e => e.a !== e.b), keep };
}
// HTML of the focus view (sync, no Mermaid). Connectors are empty here: 84j calls archFhRoute(slot) once the string is in the DOM.
function archFhHtml(mods, edges, tests, sel, groups, ents, fo, flit, bp){
  const P = archFocusPlanM(mods, edges, tests, sel, ents, fo, flit, bp), F = archFhPlan(P, !bp);   // ⚠PlanM: archFocusHx reads ARCH_FOCUS_MEMO.P
  const kinds = archFocusKinds(mods, edges, tests, sel, ents, fo, flit, bp), own = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const km = {}, ek = {}, gn = {}, sk = P.sk;
  (P.ms || []).forEach(m => { km['m' + P.ix[m.id]] = m; });
  (P.ents || []).forEach(e => { ek[e.k] = e; });
  (groups || []).forEach(g => { if(g && g.id != null && !own(gn, g.id)) gn[g.id] = g.name || g.id; });
  const nm = k => k === 'ifx' ? T('Infrastructure {n}').replace('{n}', P.fold ? P.fold.size : 0) : own(ek, k) ? archFocusEntLab(ek[k]) : own(km, k) ? String(km[k].name || km[k].id) : k;
  const box = k => {
    if(k === 'ifx' || own(ek, k)) return '<button type=button class="archfh-n' + (k === 'ifx' ? '' : ' hx') + '" data-p="' + esc(k) + '" data-kd="' + (k === 'ifx' ? 'ifx' : 'entry') + '" title="' + esc(own(ek, k) ? ek[k].label || nm(k) : nm(k)) + '">' + esc(nm(k)) + '</button>';
    const m = km[k], g = m.group == null ? '' : own(gn, m.group) ? gn[m.group] : m.group;
    const tip = nm(k) + (m.path ? ' · ' + m.path : '') + (g !== '' ? ' · ' + g : '') + (k === sk && m.path ? ' — ' + T('Click again to open the code') : '');
    return '<button type=button class="archfh-n' + (own(P.hx || {}, k) ? ' hx' : '') + '" data-p="' + esc(k) + '" data-kd="' + esc(m.kind || 'module') + '"'
      + (k === sk ? ' data-on=1' : '') + ' title="' + esc(tip) + '">' + esc(nm(k)) + '</button>'; };
  const rows = F.rows.map(r => '<div class=archfh-row data-b="' + r.b + '"><span class=archfh-lb>' + esc(r.lbl) + '</span><div class="archfh-bx' + (r.sp ? ' sp' : '') + '">'
    + (r.sp ? r.sp.map(s => '<div class=archfh-sr>' + s.map(box).join('') + '</div>').join('') : r.ks.map(box).join('')) + '</div></div>').join('');
  const tix = {}; F.edges.forEach(e => { if(!own(tix, e.b)) tix[e.b] = Object.keys(tix).length % 6; });   // colour per target box: lines into one box share a hue
  // ⚠Full step labels (several calls) ran 300px wide over boxes and each other. ⇒ badge text cut at 28 chars; the full label is the <title>.
  const eg = e => { const kd = kinds[e.a + '\u0001' + e.b] || e.kind || '', full = String(e.lab || ''), lab = archFocusCut(full, 28), c = e.a === sk ? 'out' : e.b === sk ? 'in' : '';
    const w = (typeof mmdTw === 'function' ? mmdTw(lab) : 7 * lab.length) + 8;
    return '<g class=mmdfe data-f="' + esc(e.a) + '" data-t="' + esc(e.b) + '"' + (kd ? ' data-k="' + esc(kd) + '"' : '') + ' data-c="' + c + '" data-ci=' + (own(tix, e.b) ? tix[e.b] : 0) + ' aria-label="' + esc(nm(e.a) + ' → ' + nm(e.b)) + '">'
      + '<path class=mmdhit d="M0 0"/><path class="mmde e-' + (e.est ? 'dot' : 'solid') + '" d="M0 0" marker-end="url(#archfh-ah)"/>'
      + (lab ? '<g class="mmdel mmdfl"><title>' + esc(full) + '</title><rect width="' + w + '" height=18 rx=3 /><text class=mmdtx text-anchor=middle dominant-baseline=central>' + esc(lab) + '</text></g>' : '') + '</g>'; };
  return '<div class=archfh-w><div class=archfh data-sk="' + esc(sk) + '">' + rows
    + '<svg class=archfh-e xmlns="http://www.w3.org/2000/svg"><defs><marker id=archfh-ah viewBox="0 0 10 10" refX=9 refY=5 markerUnits=userSpaceOnUse markerWidth=8 markerHeight=8 orient=auto-start-reverse>'
    + '<path class=mmdah d="M0,0L10,5L0,10z"/></marker></defs>' + F.edges.map(eg).join('') + '</svg></div></div>';
}
// Pure: lanes of one gap. its = [{up: [x], dn: [x], lo, hi}] (stubs leaving the run upward / downward) → sets it.l, returns the lane count.
// A stub strictly inside another run crosses it unless ordered: up stub → its run above that run, down stub → below (channel routing).
// ⚠A cycle is broken at the item with the fewest unplaced constraints: that pair crosses once instead of the route failing.
function archFhLanes(its){
  const n = its.length, inn = (x, o) => x > o.lo + 0.5 && x < o.hi - 0.5, ab = its.map(() => new Set()), done = new Set(), lanes = [];
  for(let i = 0; i < n; i++) for(let j = 0; j < n; j++){ if(i === j) continue;
    if(its[i].up.some(x => inn(x, its[j]))) ab[j].add(i);
    if(its[i].dn.some(x => inn(x, its[j]))) ab[i].add(j); }
  const ov = (u, v) => u.lo <= v.hi + 2 && v.lo <= u.hi + 2;
  while(done.size < n){ let best = -1, bc = Infinity;
    for(let i = 0; i < n; i++){ if(done.has(i)) continue; let c = 0; ab[i].forEach(j => { if(!done.has(j)) c++; }); if(c < bc){ bc = c; best = i; } }
    let l = 0; ab[best].forEach(j => { if(done.has(j)) l = Math.max(l, its[j].l + 1); });
    done.add(best);
    while((lanes[l] || []).some(o => ov(o, its[best]))) l++;
    its[best].l = l; (lanes[l] = lanes[l] || []).push(its[best]); }
  return lanes.length;
}
// Pure: orthogonal connector paths. rects = {key: {x, y, w, h}}, rows = [[key]] top → bottom (wrapped sub-rows are rows), edges = [{a, b}].
// Ends sit on per-end ports along the side; horizontal runs on lanes in the gap between rows; a run spanning 2+ rows takes a left/right gutter lane
// (outer = longer, so nested runs never cross). → {paths: [{a, b, pts, lx, ly}], need: [px per gap g above row g], gw: [left, right px]}.
function archFhPaths(rects, rows, edges){
  const C = ARCH_FH, own = (o, k) => Object.prototype.hasOwnProperty.call(o, k), rk = {}, ix = {}, R = rows.length, gi = [];
  rows.forEach((r, i) => r.filter(k => own(rects, k)).sort((a, b) => rects[a].x - rects[b].x).forEach((k, j) => { rk[k] = i; ix[k] = j; }));
  for(let g = 0; g <= R; g++) gi.push([]);
  const all = Object.keys(rk).map(k => rects[k]);
  if(!all.length) return { paths: (edges || []).map(e => ({ a: e.a, b: e.b, pts: null, lx: 0, ly: 0 })), need: gi.map(() => 0), gw: [C.PAD, C.PAD] };
  const x0 = Math.min(...all.map(r => r.x)), x1 = Math.max(...all.map(r => r.x + r.w)), xm = (x0 + x1) / 2;
  const ins = k => own(rk, k), cx = k => rects[k].x + rects[k].w / 2, cy = k => rects[k].y + rects[k].h / 2;
  const top = i => Math.min(...rows[i].filter(ins).map(k => rects[k].y)), bot = i => Math.max(...rows[i].filter(ins).map(k => rects[k].y + rects[k].h));
  const gut = [], it = (g, up, dn) => { const xs = up.concat(dn), o = { g, up, dn, lo: Math.min(...xs), hi: Math.max(...xs), l: 0 }; gi[g].push(o); return o; };
  const pair = {}, cost = (r0, r1, x, s) => rows.slice(Math.max(0, r0), r1 + 1).reduce((n, r) => n + r.filter(k => ins(k) && (s ? cx(k) > x : cx(k) < x)).length, 0);
  const paths = (edges || []).map((e, n) => {
    const p = { a: e.a, b: e.b, pts: null, lx: 0, ly: 0 }, pk = e.a < e.b ? e.a + '\u0001' + e.b : e.b + '\u0001' + e.a;
    if(e.a === e.b || !ins(e.a) || !ins(e.b)) return p;
    // ⚠b -> a used to reuse the a -> b line with arrow heads on both ends: in and out colours differ, so it read as two lines on top
    // of each other. ⇒ each direction is its own path (own ports and lanes); straight neighbours split by +-C.RV px.
    const rv = own(pair, pk) ? 1 : 0; pair[pk] = n;
    const ra = rk[e.a], rb = rk[e.b], A = rects[e.a], B = rects[e.b];
    if(ra === rb && Math.abs(ix[e.a] - ix[e.b]) === 1){   // neighbours in one row: straight between facing sides
      const two = rv || (edges || []).some(f => f.a === e.b && f.b === e.a), dy = two ? (rv ? C.RV : -C.RV) : 0;
      const l = A.x < B.x, xa = l ? A.x + A.w : A.x, xb = l ? B.x : B.x + B.w, ya = cy(e.a) + dy, yb = cy(e.b) + dy, xh = (xa + xb) / 2;
      p.pts = ya === yb ? [[xa, ya], [xb, yb]] : [[xa, ya], [xh, ya], [xh, yb], [xb, yb]]; return p; }
    p.ra = ra; p.rb = rb;
    if(Math.abs(ra - rb) >= 2){   // side: fewer boxes between the ends and the gutter in the rows beside the two gaps, else the nearer half
      const u = Math.min(ra, rb), v = Math.max(ra, rb), xu = ra < rb ? cx(e.a) : cx(e.b), xv = ra < rb ? cx(e.b) : cx(e.a);
      const c0 = cost(u, u + 1, xu, 0) + cost(v - 1, v, xv, 0), c1 = cost(u, u + 1, xu, 1) + cost(v - 1, v, xv, 1);
      const s = c0 !== c1 ? (c0 < c1 ? 0 : 1) : (cx(e.a) + cx(e.b)) / 2 <= xm ? 0 : 1, far = s ? 2 * x1 - cx(e.a) - cx(e.b) : cx(e.a) + cx(e.b) - 2 * x0;
      gut.push({ p, s, far, lo: Math.min(ra, rb) + 1, hi: Math.max(ra, rb) }); }
    return p; });
  // inner lanes first: shorter runs, then ends farther from the gutter (a nearer end on the inner lane crosses the outer run)
  const gl = [[], []], gn = [0, 0];
  gut.sort((u, v) => (u.hi - u.lo) - (v.hi - v.lo) || v.far - u.far).forEach(u => { let l = 0;
    gl[u.s].forEach(v => { if(u.lo <= v.hi && v.lo <= u.hi) l = Math.max(l, v.l + 1); });
    u.l = l; gl[u.s].push(u); gn[u.s] = Math.max(gn[u.s], l + 1); u.p.gx = u.s ? x1 + C.G0 + l * C.GS : x0 - C.G0 - l * C.GS; });
  // ⚠Ends on one side centre drew one stub over another (in + out on the hub top). ⇒ one port per end, spread along the side, ordered by the far end's x.
  // Bundle: 3+ adjacent-row links on one (box, side), same direction and kind, share that box's port and one gap lane: they merge on
  // one horizontal run into one trunk / arrow head. ⚠Not via a gutter. A box right over the port joins too: left out, its straight line
  // crossed the bundle's run (its branch off the run is straight anyway).
  const bun = {}, kd = n => { const e = (edges || [])[n] || {}; return String(e.k || '') + (e.est ? '~' : ''); };
  const cand = paths.map((p, n) => p.ra == null || p.gx != null || Math.abs(p.rb - p.ra) !== 1 ? null : n);
  // ⚠A badged link never bundles: on a shared trunk its badge had no run of its own and stacked beside the trunk, unreadable.
  const gk = (p, n, end) => { const dn = p.rb > p.ra; return ((edges || [])[n] || {}).lab ? '' : [end ? p.b : p.a, end ? (dn ? 0 : 1) : (dn ? 1 : 0), end, kd(n)].join('\u0001'); };
  [1, 0].forEach(end => { const by = {};
    cand.forEach(n => { if(n == null || paths[n].bd) return; const k = gk(paths[n], n, end); if(k) (by[k] = by[k] || []).push(paths[n]); });
    Object.keys(by).forEach(k => { if(by[k].length < 3) return; bun[k] = { end, ps: by[k] }; by[k].forEach(p => { p.bd = k; }); }); });
  const pe = {}, add = (k, s, far, set) => { const id = k + '\u0001' + s; (pe[id] = pe[id] || []).push({ k, far, set }); };
  paths.forEach(p => { if(p.ra == null) return; const dn = p.rb > p.ra, g = p.gx != null, B = p.bd ? bun[p.bd] : null;
    if(!B || B.end) add(p.a, dn ? 1 : 0, g ? p.gx : cx(p.b), x => { p.xa = x; });
    if(!B || !B.end) add(p.b, p.rb === p.ra || dn ? 0 : 1, g ? p.gx : cx(p.a), x => { p.xb = x; }); });
  Object.keys(bun).forEach(k => { const B = bun[k], p0 = B.ps[0], dn = p0.rb > p0.ra, far = B.ps.reduce((s, p) => s + cx(B.end ? p.a : p.b), 0) / B.ps.length;
    add(B.end ? p0.b : p0.a, B.end ? (dn ? 0 : 1) : (dn ? 1 : 0), far, x => B.ps.forEach(p => { if(B.end) p.xb = x; else p.xa = x; })); });
  // ⚠A bottom port of row r and a top port of row r+1 can land on one x by chance: their stubs then share the gap's vertical. ⇒ nudge by 6px.
  // ⚠A narrow hub with many ends spread its ports ~2px apart: runs read as one thick line. ⇒ wd = width each box needs for C.PS per port; archFhRoute widens.
  const gx = {}, wd = {};
  Object.keys(pe).forEach(id => { const L = pe[id].sort((u, v) => u.far - v.far), k = L[0].k, r = rects[k], g = rk[k] + (id.endsWith('\u00011') ? 1 : 0);
    wd[k] = Math.max(wd[k] || 0, (L.length + 1) * C.PS);
    const used = gx[g] = gx[g] || [];
    // ⚠only against other boxes' ports: nudging against its own spread ports piled a crowded side onto its clamped edge
    const hit = x => used.some(u => u.k !== k && Math.abs(u.x - x) < 3);
    // ⚠a nudge on a crowded side landed ~1px from a sibling port (one run): a candidate must stay half a spread step from every sibling slot
    const st = r.w / (L.length + 1), mine = c => L.some((_, j) => Math.abs(r.x + st * (j + 1) - c) < st / 2);
    L.forEach((e, i) => { const x0 = r.x + st * (i + 1); let x = x0;
      for(let t = 1; t <= 6 && hit(x); t++){ const c = x0 + (t % 2 ? 1 : -1) * 6 * Math.ceil(t / 2); if(c > r.x + 2 && c < r.x + r.w - 2 && !mine(c)) x = c; }
      if(hit(x)) x = [x0 + st / 4, x0 - st / 4].find(c => !hit(c)) || x0;   // quarter step: siblings stay half a step apart
      used.push({ k, x }); e.set(x); }); });
  // ⚠A link between boxes stacked over each other bent anyway (spread ports rarely share an x). ⇒ adjacent rows: when one end's port
  // lies over the other box and no other port sits within 6px there (same side) or 3px (same gap), move that port: a straight vertical.
  const po = [];
  paths.forEach(p => { if(p.ra == null || p.ra === p.rb) return; const dn = p.rb > p.ra;
    p.qa = { k: p.a, s: dn ? 1 : 0, x: p.xa }; p.qb = { k: p.b, s: dn ? 0 : 1, x: p.xb }; po.push(p.qa, p.qb); });
  const free = (q, x, p) => !po.some(o => o !== q && (o.k === q.k ? o.s === q.s && Math.abs(o.x - x) < 6
    : o.k !== p.a && o.k !== p.b && rk[o.k] + o.s === rk[q.k] + q.s && Math.abs(o.x - x) < 3));
  const over = (R, x) => x > R.x + 6 && x < R.x + R.w - 6;
  paths.forEach(p => { if(!p.qa || p.bd || p.gx != null || Math.abs(p.rb - p.ra) !== 1) return;
    if(over(rects[p.b], p.xa) && free(p.qb, p.xa, p)){ p.xb = p.qb.x = p.xa; }
    else if(over(rects[p.a], p.xb) && free(p.qa, p.xb, p)){ p.xa = p.qa.x = p.xb; } });
  paths.forEach(p => { delete p.qa; delete p.qb; });
  Object.keys(bun).forEach(k => { const ps = bun[k].ps, dn = ps[0].rb > ps[0].ra, u = new Set(), w = new Set();
    ps.forEach(p => { u.add(dn ? p.xa : p.xb); w.add(dn ? p.xb : p.xa); });
    const o = it(dn ? ps[0].rb : ps[0].ra, [...u], [...w]); ps.forEach(p => { p.it = [o]; }); });
  paths.forEach(p => { if(p.ra == null || p.bd) return;
    const xa = p.xa, xb = p.xb, dn = p.rb > p.ra, d = Math.abs(p.rb - p.ra);
    p.it = d === 0 ? [it(p.ra, [], [xa, xb])] : d === 1 ? [dn ? it(p.rb, [xa], [xb]) : it(p.ra, [xb], [xa])]
      : dn ? [it(p.ra + 1, [xa], [p.gx]), it(p.rb, [p.gx], [xb])] : [it(p.ra, [p.gx], [xa]), it(p.rb + 1, [xb], [p.gx])]; });
  const nl = gi.map(archFhLanes), need = nl.map(n => n ? (n + 1) * C.LS : 0);
  const span = g => { const b = g < R ? top(g) : 0, t = g > 0 ? bot(g - 1) : Math.max(0, b - need[g]); return g < R ? [t, b] : [t, t + need[g]]; };
  const ly = o => { const [t, b] = span(o.g); return t + (o.l + 1) * (b - t) / (nl[o.g] + 1); };
  paths.forEach(p => { if(p.ra == null) return;
    const A = rects[p.a], B = rects[p.b], xa = p.xa, xb = p.xb, Y = p.it.map(ly), dn = p.rb > p.ra;
    const ya = dn ? A.y + A.h : A.y, yb = p.rb === p.ra ? B.y : dn ? B.y : B.y + B.h;
    p.pts = p.it.length === 1 ? [[xa, ya], [xa, Y[0]], [xb, Y[0]], [xb, yb]] : [[xa, ya], [xa, Y[0]], [p.gx, Y[0]], [p.gx, Y[1]], [xb, Y[1]], [xb, yb]];
    delete p.it; delete p.ra; delete p.rb; delete p.gx; delete p.xa; delete p.xb; });
  paths.forEach(p => { if(!p.pts) return;
    p.pts = p.pts.filter((q, i) => !i || q[0] !== p.pts[i - 1][0] || q[1] !== p.pts[i - 1][1]);
    p.pts = p.pts.filter((q, i, a) => !i || i === a.length - 1 || !((a[i - 1][0] === q[0] && q[0] === a[i + 1][0]) || (a[i - 1][1] === q[1] && q[1] === a[i + 1][1])));   // drop a corner on a straight run
    let bl = -1, s = null;   // badge: middle of the longest horizontal run, else of the path
    p.pts.slice(1).forEach((q, i) => { const a = p.pts[i], L = Math.abs(q[0] - a[0]); if(a[1] === q[1] && L > bl){ bl = L; s = [a, q]; } });
    if(!s){ const m = Math.floor((p.pts.length - 1) / 2); s = [p.pts[m], p.pts[m + 1] || p.pts[m]]; }
    p.lx = (s[0][0] + s[1][0]) / 2; p.ly = (s[0][1] + s[1][1]) / 2; p.bs = s[0][1] === s[1][1] ? [Math.min(s[0][0], s[1][0]), Math.max(s[0][0], s[1][0])] : null; });
  return { paths, need, gw: gn.map(n => Math.max(C.PAD, n ? C.G0 + (n - 1) * C.GS + 6 : 0)), wd };
}
// Boxes narrower than archFhPaths wd get that min-width (past the CSS max-width). true = changed. ⚠Only grows: few-port boxes keep their size.
function archFhWiden(fh, M, wd){
  let ch = false;
  Object.keys(wd || {}).forEach(k => { const r = M.rects[k]; if(!r || wd[k] <= r.w + 0.5) return;
    const el = Array.from(fh.querySelectorAll('.archfh-n')).find(n => n.dataset.p === k);
    if(el){ el.style.minWidth = Math.ceil(wd[k]) + 'px'; el.style.maxWidth = 'none'; ch = true; } });
  return ch;
}
// Pure: {crossings, boxHits, overlaps} of drawn lines (a reverse pair on one line counts once), the 81g mmdQuality segment tests (strict crossings, a box shrunk 1px so touching ends do not count).
function archFhQuality(paths, rects){
  const seen = new Set(), line = p => { const k = JSON.stringify(p.pts), r = JSON.stringify(p.pts.slice().reverse()); if(seen.has(k) || seen.has(r)) return false; seen.add(k); return true; };
  const ln = (paths || []).filter(p => p && p.pts && line(p)), bd = ln.map(p => p.bd || null);   // one bundle shares its run and trunk on purpose
  const segs = ln.map(p => p.pts.slice(1).map((q, i) => [p.pts[i], q])), rs = Object.keys(rects || {}).map(k => rects[k]);
  let boxHits = 0, crossings = 0;
  segs.forEach(ss => rs.forEach(R => { if(ss.some(s => mmdSegRect(s[0], s[1], R, -1))) boxHits++; }));
  const o = (p, q, r) => Math.sign((q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]));
  for(let i = 0; i < segs.length; i++) for(let j = i + 1; j < segs.length; j++)
    segs[i].forEach(a => segs[j].forEach(b => { if(o(a[0], a[1], b[0]) * o(a[0], a[1], b[1]) < 0 && o(b[0], b[1], a[0]) * o(b[0], b[1], a[1]) < 0) crossings++; }));
  // ⚠The strict test above never sees collinear runs: two lines drawn on top of each other count as overlaps (> 0.5px shared).
  let overlaps = 0; const ax = (s, d) => Math.abs(s[0][d] - s[1][d]) < 0.01;
  const ov = (a, b, d) => Math.abs(a[0][d] - b[0][d]) < 0.01 && Math.min(Math.max(a[0][1 - d], a[1][1 - d]), Math.max(b[0][1 - d], b[1][1 - d])) - Math.max(Math.min(a[0][1 - d], a[1][1 - d]), Math.min(b[0][1 - d], b[1][1 - d])) > 0.5;
  for(let i = 0; i < segs.length; i++) for(let j = i + 1; j < segs.length; j++)
    if(!bd[i] || bd[i] !== bd[j]) segs[i].forEach(a => segs[j].forEach(b => { if([0, 1].some(d => ax(a, d) && ax(b, d) && ov(a, b, d))) overlaps++; }));
  return { crossings, boxHits, overlaps };
}
// Box rects (offsets inside .archfh, position:relative) and sub-rows: boxes of one band whose tops differ by over half a box start a new row.
function archFhMeasure(fh){
  const rects = {}, rows = [], bands = [];
  fh.querySelectorAll('.archfh-row').forEach(rw => { const ns = Array.from(rw.querySelectorAll('.archfh-n')).sort((a, b) => a.offsetTop - b.offsetTop);
    let cur = null, t0 = 0, sub = 0;
    ns.forEach(n => { const k = n.dataset.p; rects[k] = { x: n.offsetLeft, y: n.offsetTop, w: n.offsetWidth, h: n.offsetHeight };
      if(!cur || n.offsetTop > t0 + n.offsetHeight / 2){ rows.push(cur = []); bands.push({ el: rw, sub: sub++ }); t0 = n.offsetTop; }
      cur.push(k); }); });
  return { rects, rows, bands };
}
// Gap sizes from archFhPaths need/gw: padding above row 0, band margin, sub-row gap (max of the band's own gaps), side gutters. true = changed.
function archFhSpace(fh, M, need, gw){
  const C = ARCH_FH; let ch = false;
  const set = (el, p, v) => { const s = Math.round(v) + 'px'; if(el && el.style && el.style[p] !== s){ el.style[p] = s; ch = true; } };
  const sv = (p, v) => { const s = Math.round(v) + 'px'; if(fh.style.getPropertyValue(p) !== s){ fh.style.setProperty(p, s); ch = true; } };
  set(fh, 'paddingTop', Math.max(C.SUB, need[0] || 0));
  const sg = new Map();
  M.bands.forEach((b, g) => { if(!g) return;
    if(b.sub) sg.set(b.el, Math.max(sg.get(b.el) || C.SUB, need[g] || 0)); else set(b.el, 'marginTop', Math.max(C.ROW, need[g] || 0)); });
  fh.querySelectorAll('.archfh-row').forEach(rw => set(rw.querySelector('.archfh-bx'), 'rowGap', sg.get(rw) || C.SUB));
  sv('--fh-gl', gw[0]); sv('--fh-gr', gw[1]);
  return ch;
}
// Pure: extra px per row gap that spreads a short focus map over the free height under it (none under 24px, cap 120).
function archFhGap(free, n){ return n > 0 && free > 24 ? Math.min(120, Math.floor(free / n)) : 0; }
// Free height under the map inside its scrolling box, in layout px (the slot may be CSS-zoomed). 0 when that box already scrolls.
// ⚠Only the vertical gaps grow: node sizes, lanes and badges keep the tight layout.
function archFhFill(fh, n){
  let sc = fh.parentElement;
  while(sc && sc !== document.body){ const oy = getComputedStyle(sc).overflowY; if(oy === 'auto' || oy === 'scroll') break; sc = sc.parentElement; }
  if(!sc || sc === document.body || sc.scrollHeight > sc.clientHeight + 1 || !fh.offsetHeight) return 0;
  const r = fh.getBoundingClientRect(), z = r.height / fh.offsetHeight || 1, cs = getComputedStyle(sc);
  const bot = sc.getBoundingClientRect().bottom - (parseFloat(cs.borderBottomWidth) || 0) - (parseFloat(cs.paddingBottom) || 0) - 8;
  return archFhGap((bot - r.bottom) / z, n);
}
// Pure: badge spot for path p (w wide, 18 high) clear of placed badges put [[x, y, w]] and boxes [{x, y, w, h}]; sets p.lx / p.ly.
function archFhBadge(p, w, put, boxes){
  const bx = (x, y) => (boxes || []).some(R => x - w / 2 < R.x + R.w && x + w / 2 > R.x && y - 9 < R.y + R.h && y + 9 > R.y);
  const cl = (x, y) => put.some(o => Math.abs(o[0] - x) < (o[2] + w) / 2 + 3 && Math.abs(o[1] - y) < 20) || bx(x, y);
  // ⚠Close lanes put badges on top of each other: slide along the badge's own horizontal run to the nearest free spot.
  if(p.bs) for(let k = 1; cl(p.lx, p.ly) && k < 12; k++){ const dx = Math.ceil(k / 2) * (w + 6) * (k % 2 ? 1 : -1), x = p.lx + dx;
    if(x - w / 2 >= p.bs[0] && x + w / 2 <= p.bs[1] && !cl(x, p.ly)){ p.lx = x; break; } }
  // ⚠A short run (or one shared by a bundle) has no free spot: try beside the path's own vertical runs, longest first.
  if(cl(p.lx, p.ly)){ const v = p.pts.slice(1).map((q, j) => [p.pts[j], q]).filter(s => s[0][0] === s[1][0])
      .sort((a, b) => Math.abs(b[1][1] - b[0][1]) - Math.abs(a[1][1] - a[0][1]));
    for(const s of v){ const y = (s[0][1] + s[1][1]) / 2, x = [s[0][0] + w / 2 + 4, s[0][0] - w / 2 - 4].find(x => !cl(x, y));
      if(x != null){ p.lx = x; p.ly = y; break; } } }
  // ⚠A run between two adjacent boxes is shorter than the badge: step off the boxes across the run, nearest side first.
  if(bx(p.lx, p.ly)) for(let k = 1; k <= 24; k++){ const y = p.ly + Math.ceil(k / 2) * 4 * (k % 2 ? -1 : 1); if(!cl(p.lx, y)){ p.ly = y; break; } }
}
// After insertion: measure, size the gaps (re-measure while wrapping moves), draw each .mmdfe path and badge.
// Returns archFhQuality (also on data-q) — never moves the scroll.
function archFhRoute(slot){
  const fh = !slot ? null : slot.classList && slot.classList.contains('archfh') ? slot : slot.querySelector ? slot.querySelector('.archfh') : null;
  if(!fh) return null;
  const gs = Array.from(fh.querySelectorAll('.archfh-e .mmdfe')), es = gs.map(g => ({ a: g.dataset.f, b: g.dataset.t, k: g.dataset.k || '', est: !!g.querySelector('.e-dot'), lab: !!g.querySelector('.mmdfl') })), f = v => String(Math.round(v * 10) / 10);
  let M = null, R = null;
  for(let i = 0; i < 4; i++){ M = archFhMeasure(fh); R = archFhPaths(M.rects, M.rows, es); if(i === 3) break;
    const w = archFhWiden(fh, M, R.wd); if(!archFhSpace(fh, M, R.need, R.gw) && !w) break; }
  const e = archFhFill(fh, M.bands.length - 1);
  if(e){ const C = ARCH_FH, n2 = R.need.map((v, g) => g && M.bands[g] ? Math.max(M.bands[g].sub ? C.SUB : C.ROW, v || 0) + e : v);   // need has one gap past the last row
    archFhSpace(fh, M, n2, R.gw); M = archFhMeasure(fh); R = archFhPaths(M.rects, M.rows, es); }
  const put = [];
  gs.forEach((g, i) => { const p = R.paths[i], d = p && p.pts ? 'M' + p.pts.map(q => f(q[0]) + ',' + f(q[1])).join('L') : '';
    g.style.display = d ? '' : 'none';
    g.querySelectorAll(':scope > path').forEach(x => x.setAttribute('d', d || 'M0 0'));
    const r = g.querySelector('.mmdfl rect'), t = g.querySelector('.mmdfl text');
    if(r && t && d){ const w = +r.getAttribute('width') || 0;
      archFhBadge(p, w, put, Object.keys(M.rects).map(k => M.rects[k]));
      put.push([p.lx, p.ly, w]);
      r.setAttribute('x', f(p.lx - w / 2)); r.setAttribute('y', f(p.ly - 9)); t.setAttribute('x', f(p.lx)); t.setAttribute('y', f(p.ly)); } });
  const q = archFhQuality(R.paths, M.rects);
  fh.dataset.q = q.crossings + ',' + q.boxHits;
  return q;
}
// ⚠Layer zoom lives only in 84j3 archLyZoom (CSS zoom on the slot): a second scale here compounded with it. Hover is 84j's .archdg .archfh listener.
