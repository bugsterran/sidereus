// ── Structure «Architecture» v2 focus view: the clicked module + its direct neighbours inside the layer bands (called from 84j) ──────
// ⚠Only called from inside 84j functions: no top-level reads of 84j/84j2 names. Owns archFocus* names only; the ARCH object is
// owned by 84j — archFocusClick only sets its ifx / lit / op fields.
// ⚠Every direct pair is drawn (no archReduce): the focus view is where all of a module's edges show.
// ⚠Group names, entry and edge labels are agent data: archMq only, never T().
const ARCH_FOCUS_FOLD = ['shared', 'infra'];
const ARCH_FOCUS_KR = { event: 0, call: 1, read: 2, write: 3 };
// Pure: what the focus view draws. lit = {flows, fs}: every map flow + the lit flow ids (fs null = none lit).
// Neighbours on a shared/infra layer fold into one 'ifx' node when there are 2+ and !open; lit step modules never fold.
// bp = 84j2 archBandPlan (none = layer bands): band index of every module, the hub band sb and the fold band fl.
function archFocusPlan(mods, edges, tests, sel, ents, open, lit, bp){
  bp = bp || archBandPlan(null);
  const ix = {}, own = (o, k) => Object.prototype.hasOwnProperty.call(o, k), nb = {}, on = {}, num = {}, F = [], E = [], at = {};
  (mods || []).forEach((m, i) => { if(m && m.id != null) ix[m.id] = i; });
  const vis = id => own(ix, id) && (tests || id === sel || !archIsTest(mods[ix[id]]));
  const all = archPairs(mods, edges, tests), ps = all.filter(p => p.from === sel || p.to === sel), pk = {};
  all.forEach(p => { pk[p.from + '\u0001' + p.to] = p; });
  nb[sel] = 1; ps.forEach(p => { nb[p.from] = nb[p.to] = 1; });
  const fls = (lit && Array.isArray(lit.flows) ? lit.flows : []).filter(f => f && f.id != null && Array.isArray(f.steps));
  const fs = lit && Array.isArray(lit.fs) ? lit.fs.map(String) : [];
  fls.filter(f => fs.indexOf(String(f.id)) >= 0).forEach(f => f.steps.forEach((s, i) => {
    if(!s || s.from === s.to || !vis(s.from) || !vis(s.to)) return;
    on[s.from] = on[s.to] = 1; const k = s.from + '\u0001' + s.to; (num[k] = num[k] || new Set()).add(i + 1); }));
  Object.keys(nb).forEach(id => { const m = mods[ix[id]];
    if(m && id !== sel && !on[id] && m.kind !== 'external' && ARCH_FOCUS_FOLD.indexOf(m.layer) >= 0) F.push(id); });
  const fold = !open && F.length >= 2 ? new Set(F) : null, key = id => fold && fold.has(id) ? 'ifx' : 'm' + ix[id];
  // R4: step numbers of a pair in either direction, «1·3» when it is a step in two places
  const stepLab = (a, b) => { const s = new Set([...(num[a + '\u0001' + b] || []), ...(num[b + '\u0001' + a] || [])]);
    return s.size ? Array.from(s).sort((x, y) => x - y).join('·') : ''; };
  const add = (a, b, est, lab, kind, n) => { const k = a + '\u0001' + b, x = at[k];
    if(!x){ E.push(at[k] = { a, b, est, lab, kind, n }); return; }
    x.n += n; if(!est) x.est = false; if(ARCH_FOCUS_KR[kind] > ARCH_FOCUS_KR[x.kind]) x.kind = kind;
    if(a === 'ifx' || b === 'ifx') x.lab = x.n > 1 ? '×' + x.n : ''; };
  ps.forEach(p => { const a = key(p.from), b = key(p.to), sl = stepLab(p.from, p.to);
    add(a, b, p.est, a === 'ifx' || b === 'ifx' ? (p.n > 1 ? '×' + p.n : '') : sl || (p.label + (p.n > 1 ? ' ×' + p.n : '')).trim(), p.kind, p.n); });
  Object.keys(num).forEach(k => { const [f, t] = k.split('\u0001');
    if(at[key(f) + '\u0001' + key(t)] || at[key(t) + '\u0001' + key(f)]) return;   // drawn pair already carries the number
    const p = pk[k]; add(key(f), key(t), p ? p.est : true, stepLab(f, t), p ? p.kind : '', 1); });
  const drawn = id => (nb[id] || on[id]) && !(fold && fold.has(id));
  // paired entry (84j2 archEntPair): its drawn L0 entry module takes the hexagon, no en node and no entry edge
  const pr = archEntPair(ents, i => { const m = mods[i]; return !!m && m.kind === 'entry' && bp.of(m) === 0 && !!drawn(m.id); }), hx = {};
  Object.keys(pr).forEach(i => { hx['m' + i] = pr[i]; });
  // an entry is drawn only with an edge to a drawn module (a lit flow's first module is always drawn)
  const en = (ents || []).filter(e => pr[Array.from(e.to)[0]] !== e).filter(e => Array.from(e.to).some(i => { const id = mods[i] && mods[i].id; return id != null && (nb[id] || on[id]); }));
  en.forEach(e => Array.from(e.to).forEach(i => { const id = mods[i] && mods[i].id;
    if(id != null && (drawn(id) || (fold && fold.has(id)))) add(e.k, key(id), false, '', 'entry', 1); }));
  const ms = (mods || []).filter(m => m && m.id != null && ix[m.id] === mods.indexOf(m) && drawn(m.id));
  const fl = fold ? Math.min(...F.map(id => bp.of(mods[ix[id]]))) : -1;
  const sm = mods[ix[sel]], sb = !sm ? -1 : bp.of(sm);   // hub band index (bp.n = external band)
  return { ix, ms, fold, fl, edges: E, ents: en, hx, sb, sk: 'm' + ix[sel], bp };
}
// Pure: entry node label: kind · label cut at 12 characters (full label in the flow picker).
// ⚠Longer made two entries wider than a 1100px pane's row (room 432), so the second one wrapped under the first.
function archFocusEntLab(e){
  const kd = typeof archFlowKind === 'function' ? archFlowKind(e.kind) : e.kind, cut = archFocusCut(e.label, 12);
  return kd && cut ? kd + ' · ' + cut : kd || cut;
}
// Pure: text cut at 24 characters with «…» — a long group title set the minimum width of every chunk of that group.
function archFocusCut(s, n = 24){ const a = Array.from(String(s)); return a.length > n ? a.slice(0, n - 1).join('').trimEnd() + '…' : String(s); }
// Pure: banded mermaid source of the focus view (same band L<i> / group G<n> / Lx layout as 84j2 archBandSrc): one box per band
// and per (band, group). fit = archFitOf room: items of one rank (edges inside the block set the ranks) that are wider than it wrap
// into sub-rows, chained top to bottom by invisible edges (`~~~`: ranked, never routed or drawn).
// ⚠Pack per rank, not per block: one row over all items wrapped an entry and the module it calls into separate rows, and the
// chain plus the real edge stepped every box one rank lower (diagonal stair, hub below the first screen).
// ⚠Rows alone do not bound the width: long edges add dummies beside a band, bands sit at their neighbours' barycentre and unplaced
// labels add a legend column (★real hub 13 in / 17 out: 1157px for an 860px room). ⇒ measure the drawing and shrink the row budget (8 tries, memoised).
// ⚠Memo keys compare map arrays by identity (unchanged map = same cached object) but ents by value: 84j rebuilds them every paint.
const ARCH_FOCUS_MEMO = { a: null, src: '', pa: null, P: null };
const archFocusSame = (x, y) => !!x && x.length === y.length && x.every((v, i) => v === y[i]);
// Plan memo shared by archFocusSrc and archFocusKinds: one archFocusPlan per view state.
function archFocusPlanM(mods, edges, tests, sel, ents, open, lit, bp){
  const es = (ents || []).map(e => e.k + '|' + e.kind + '|' + e.label + '|' + Array.from(e.to).join(',') + '|' + e.flows.join(',')).join(';');
  const a = [mods, edges, !!tests, sel, es, !!open, lit && lit.flows, lit && lit.fs ? lit.fs.join('\u0001') : '', bp ? bp.key : ''], M = ARCH_FOCUS_MEMO;
  if(!archFocusSame(M.pa, a)){ M.pa = a; M.P = archFocusPlan(mods, edges, tests, sel, ents, open, lit, bp); }
  return M.P;
}
// Drawn width of a focus source as 84j archMmd lays it out (labels stripped, archFocusStrip).
// rk = each item's rank inside its block (node key / group id → index of its row, by centre y), for archFocusRows.
function archFocusW(src, bp, hub){   // hub = focused node key: on the centre axis, as 84j archMmd draws it
  const g = mmdParse(src); archBandFix(g, bp, hub); g.flLabels = true; archFocusStrip(g);
  const L = mmdLayout(g), by = {}, rk = {};
  g.nlist.forEach(k => { const R = L.nodes[k]; if(R) (by[g.nodes[k].sg] = by[g.nodes[k].sg] || []).push([k, R.y + R.h / 2]); });
  g.slist.forEach(s => { const R = L.sgs[s]; if(R && g.sgs[s].parent) (by[g.sgs[s].parent] = by[g.sgs[s].parent] || []).push([s, R.y + R.h / 2]); });
  Object.keys(by).forEach(b => { const ys = Array.from(new Set(by[b].map(x => Math.round(x[1])))).sort((p, q) => p - q);
    by[b].forEach(([k, y]) => { rk[k] = ys.indexOf(Math.round(y)); }); });
  return { w: L.w, rk };
}
// R3: edge labels show only on hover, so the layout leaves them out — laid out they set the width
// (★real hub: 1225px with labels, 759 without; unplaced ones also added a legend column). ⇒ strip before layout, archFocusPills after.
function archFocusStrip(g){
  const lab = {};
  g.edges.forEach(e => { if(e.label){ lab[e.from + '\u0001' + e.to] = e.label; e.label = ''; } });
  return lab;
}
// Label pills for the laid-out focus view, same markup as 81e mmdSvg tag mode (.mmdfe > .mmdel.mmdfl, hover via data-f/data-t).
// A label with no free spot sits on its edge anyway (hidden until hover), never in a legend column. Every label goes through esc().
function archFocusPills(g, L, lab){
  const f = v => String(Math.round(v * 10) / 10), ge = {};
  g.edges.forEach(e => { const k = e.from + '\u0001' + e.to; if(!ge[k]) ge[k] = e; });
  L.edges.forEach(e => { e.label = lab[e.from + '\u0001' + e.to] || ''; });
  const P = mmdFlPlace(g, L);
  let o = '';
  L.edges.forEach((e, i) => { const p = P.labs[i]; if(!p || !p.R || !e.label) return;
    // ⚠The pill is wider than the placed badge: clamp its centre into [0, L.w] or the SVG cuts it at the right edge.
    const t = String(e.label), w = mmdTw(t) + 8, cy = p.R.y + p.R.h / 2, m = ge[e.from + '\u0001' + e.to] || {};
    const cx = w > L.w - 4 ? 2 + w / 2 : Math.min(Math.max(p.R.x + p.R.w / 2, w / 2 + 2), L.w - w / 2 - 2);
    o += '<g class=mmdfe data-c="' + esc((m.calls || []).join(' ')) + '"' + (m.kind ? ' data-k="' + esc(m.kind) + '"' : '') + ' data-f="' + esc(e.from) + '" data-t="' + esc(e.to) + '">'
      + '<g class="mmdel mmdfl"><rect x="' + f(cx - w / 2) + '" y="' + f(cy - 9) + '" width="' + f(w) + '" height="18" rx="3"/><text class=mmdtx x="' + f(cx)
      + '" text-anchor=middle dominant-baseline=central><tspan x="' + f(cx) + '" y="' + f(cy) + '">' + esc(t) + '</tspan></text></g></g>'; });
  return o;
}
function archFocusSrc(mods, edges, tests, sel, groups, ents, open, lit, fit, bp){
  const P = archFocusPlanM(mods, edges, tests, sel, ents, open, lit, bp), a = [P, groups, fit ? fit.w : 0], M = ARCH_FOCUS_MEMO;
  if(archFocusSame(M.a, a)) return M.src;
  // ⚠Width is not monotonic in the row budget (★real hub, fit 680: 632→689px, 545→906, 299→645): keep the narrowest try, stop at the first fit
  // ⚠Rows follow the renderer's own ranks from an unwrapped trial layout: archRanks broke hub cycles the other way, so the
  //   wrap chains hung out-neighbours under in-neighbours and the real rank stayed too wide (★fit 520: 723px, hub at y 508+).
  // ⚠A shrinking budget wraps only bands from the hub's band down: bands above keep the full room, every row they wrap pushes the hub
  //   off the first screen (★1100 pane, fit 480: hub at y 644 with entries and the entry group each stepped onto two rows).
  //   When the bands above are what overflows (a hub with many callers), a second pass shrinks every band.
  const room0 = fit && fit.w > 0 ? fit.w - 2 * 8 - 2 * 16 : Infinity, trial = archFocusBuild(P, groups, Infinity);
  let src = trial, best = null, rk = null, done = !(fit && fit.w > 0);
  [room0, null].forEach(keep => {
    let room = room0;
    src = trial;
    for(let i = 0; !done && i < 8; i++){
      let r = null;
      try{ r = archFocusW(src, P.bp, P.sk); }catch(e){ done = true; break; }
      if(!rk) rk = r.rk;
      if(!best || r.w < best.w) best = { w: r.w, src };
      if(r.w <= fit.w){ best = { w: r.w, src }; done = true; break; }
      if(room <= 160) break;
      if(i) room = Math.max(160, room - Math.max(40, r.w - fit.w + 20));
      src = archFocusBuild(P, groups, room, rk, keep);
    }
  });
  src = best ? best.src : trial;
  M.a = a; M.src = src;
  return src;
}
// Pure: rows of one block. its = [{id, w}], es = [[from id, to id]] inside the block, ht = {rk, h, full} (ranks; ranks above h pack in full) → {inv: invisible edges, w: widest row}.
// Rank = 84j archRanks (DFS back edges ignored, longest path); a rank wider than `room` packs into sub-rows, each hung under the
// first item of the sub-row above, and the next rank under its last sub-row. ⚠Only where a rank wrapped: an invisible edge that
// disagrees with the renderer's own cycle break adds a rank (★mutual hub pairs: every in-neighbour one row lower).
function archFocusRows(its, es, room, ht){
  const SEP = 36, ids = its.map(x => x.id), at = new Set(ids), inv = [], by = {}, rk0 = ht && ht.rk;
  const rk = rk0 && ids.every(k => rk0[k] >= 0) ? rk0 : archRanks(ids, es.filter(([a, b]) => a !== b && at.has(a) && at.has(b)).map(([a, b]) => ({ from: a, to: b })));
  its.forEach(x => { (by[rk[x.id] || 0] = by[rk[x.id] || 0] || []).push(x); });
  let w = 0, prev = null;
  Object.keys(by).map(Number).sort((a, b) => a - b).forEach(r => { const rows = [];
    let cur = null, used = 0;
    const rm = ht && r < ht.h ? Math.max(room, ht.full) : room;   // above the hub: full room (archFocusBuild hubTop)
    by[r].forEach(x => { if(cur && used + SEP + x.w <= rm){ cur.push(x); used += SEP + x.w; } else { rows.push(cur = [x]); used = x.w; } });
    rows.forEach((q, i) => { w = Math.max(w, q.reduce((a, x) => a + x.w, 0) + SEP * (q.length - 1));
      const top = i ? rows[i - 1][0] : prev && prev.length > 1 ? prev[prev.length - 1][0] : null;
      if(top) q.forEach(x => inv.push([top.id, x.id])); });
    prev = rows; });
  return { inv, w };
}
// Pure: source text of plan P with each block's ranks packed into rows of `room` px (Infinity = one row per rank).
function archFocusBuild(P, groups, room1, rk, room0){
  const gn = {}, bands = {}, ln = ['flowchart TB'], deg = {}, inv = [], up = {};
  const own = Object.prototype.hasOwnProperty, PAD = 16;
  (groups || []).forEach(g => { if(g && g.id != null && !own.call(gn, g.id)) gn[g.id] = g.name || g.id; });
  P.edges.forEach(e => { deg[e.a] = (deg[e.a] || 0) + 1; deg[e.b] = (deg[e.b] || 0) + 1; });
  // box width as 81e mmdLayout draws it, hub growth included
  const bw = (k, label, shape) => { const w = mmdBox(label, shape).w, n = Math.ceil((deg[k] || 0) / 2); return n > 2 ? Math.max(w, Math.min(360, 24 + 18 * n)) : w; };
  const band = b => bands[b] = bands[b] || { its: [], by: {} };
  const loose = (b, k, line, label, shape) => band(b).its.push({ id: k, line, w: bw(k, label, shape) });
  P.ents.forEach(e => { const lb = archFocusEntLab(e); loose('L0', e.k, e.k + '{{' + archMq(lb) + '}}', lb, 'hex'); });
  if(P.fold){ const lb = T('Infrastructure {n}').replace('{n}', P.fold.size); loose('L' + P.fl, 'ifx', 'ifx[' + archMq(lb) + ']', lb, 'rect'); }
  let gi = 0;
  P.ms.forEach(m => { const ex = m.kind === 'external', b = ex ? 'Lx' : 'L' + P.bp.of(m), k = 'm' + P.ix[m.id], nm = m.name || m.id;
    const hx = own.call(P.hx || {}, k), line = k + (ex ? '([' + archMq(nm) + '])' : hx ? '{{' + archMq(nm) + '}}' : '[' + archMq(nm) + ']'), w = bw(k, nm, ex ? 'stadium' : hx ? 'hex' : 'rect');
    const gk = ex ? String(m.ext || '') : m.group == null ? '' : String(m.group), B = band(b);
    if(!ex && !gk){ B.its.push({ id: k, line, w }); return; }
    let G = B.by['\u0001' + gk];
    if(!G){ G = B.by['\u0001' + gk] = { id: 'G' + (gi++), title: archFocusCut(ex ? gk || T('External') : own.call(gn, gk) ? gn[gk] : gk), ms: [] }; B.its.push(G); }
    G.ms.push({ id: k, line, w }); up[k] = G.id; });
  const pairs = P.edges.map(e => [e.a, e.b]), lift = k => own.call(up, k) ? up[k] : k;
  // ⚠Ranks above the hub inside its block keep the full room, as bands above do: a wrapped caller rank put the hub one row
  //   lower (★1100 pane: hub box 851-881, first screen ends at 860). Callers still wider than it ⇒ mutual neighbours go below the
  //   hub, listed first so the renderer's DFS cycle break starts at it, plus an invisible hub ~~~ m edge.
  const pk = new Set(pairs.map(([a, c]) => a + '\u0001' + c)), mu = k => pk.has(k + '\u0001' + P.sk) && pk.has(P.sk + '\u0001' + k);
  const hubTop = (its, full) => { const h = rk && its.some(x => x.id === P.sk) ? rk[P.sk] : -1, ab = h > 0 ? its.filter(x => rk[x.id] === h - 1) : [];
    if(!ab.length) return { rk };
    if(ab.reduce((a, x) => a + x.w, 0) + 36 * (ab.length - 1) <= full || !ab.some(x => mu(x.id))) return { rk, h, full };
    const o = Object.assign({}, rk); ab.forEach(x => { if(mu(x.id)){ o[x.id] = h + 1; inv.push([P.sk, x.id]); } });
    its.unshift(its.splice(its.findIndex(x => x.id === P.sk), 1)[0]); return { rk: o, h, full }; };
  ARCH_LAYERS.slice(0, P.bp.n).map((l, i) => 'L' + i).concat(['Lx']).forEach((b, bi) => {
    const B = bands[b], room = bi < P.sb && room0 ? Math.max(room0, room1) : room1;   // above the hub: full room
    if(!B) return;
    // hub's group alone in its band: no box (the path bar names it). ★1100 pane: its title row kept the hub 31px below the first screen
    if(bi === P.sb && B.its.length === 1 && B.its[0].ms && B.its[0].ms.some(x => x.id === P.sk)){ B.its = B.its[0].ms; B.its.forEach(x => { delete up[x.id]; }); }
    B.its.forEach(it => { if(!it.ms) return;   // group: its members' rows inside the box, then the box width
      const r = archFocusRows(it.ms, pairs, room - 2 * PAD, hubTop(it.ms, Math.max(room, room0 || 0) - 2 * PAD));
      r.inv.forEach(x => inv.push(x));
      it.w = Math.max(60, mmdTw(it.title) + 10 + 2 * PAD, r.w + 2 * PAD); });
    archFocusRows(B.its, pairs.map(([a, c]) => [lift(a), lift(c)]), room, hubTop(B.its, Math.max(room, room0 || 0))).inv.forEach(x => inv.push(x));
    ln.push('  subgraph ' + b + '[' + archMq(b === 'Lx' ? T('External') : P.bp.lbl(+b.slice(1))) + ']');
    B.its.forEach(it => { if(!it.ms){ ln.push('    ' + it.line); return; }
      ln.push('    subgraph ' + it.id + '[' + archMq(it.title) + ']');
      it.ms.forEach(x => ln.push('      ' + x.line));
      ln.push('    end'); });
    ln.push('  end');
  });
  P.edges.forEach(e => ln.push('  ' + e.a + ' ' + (e.est ? '-.->' : '-->') + (e.lab ? '|' + archMq(e.lab) + '|' : '') + ' ' + e.b));
  return ln.concat(inv.map(([a, c]) => '  ' + a + ' ~~~ ' + c)).join('\n');
}
// Pure: drawn-edge kinds of the focus view for 84j archMmd (node-key pair → call|read|write|event|entry), ifx edges included.
function archFocusKinds(mods, edges, tests, sel, ents, open, lit, bp){
  const out = {}, P = archFocusPlanM(mods, edges, tests, sel, ents, open, lit, bp), fk = P.bp.fk || {};
  const uses = e => e.kind === 'call' && fk[e.b] && /^m\d+$/.test(e.a) && mods[+e.a.slice(1)] && mods[+e.a.slice(1)].kind !== 'entry';   // as 84j2 archKindMap
  P.edges.forEach(e => { if(e.kind) out[e.a + '\u0001' + e.b] = uses(e) ? 'uses' : e.kind; });
  return out;
}
// Paired entry hexagon m<i> of the drawn focus view (not the hub), else null; 84j archDgClick routes it to archFocusClick.
function archFocusHx(k){ const P = ARCH_FOCUS_MEMO.P; return P && P.hx && k !== P.sk && Object.prototype.hasOwnProperty.call(P.hx, k) ? P.hx[k] : null; }
// Focus-view click on a non-module node: 'ifx' unfolds the infrastructure chip; an entry node 'en<n>' or a paired entry hexagon m<i>
// lights the flows starting at it (again = off). ⚠No scroll or centring: archPaint keeps the map scroll like any other repaint.
function archFocusClick(p, d, k){
  const s = ARCH.sel && ARCH.sel.p === p ? ARCH.sel.id : null;
  if(s == null) return;
  if(k === 'ifx'){ ARCH.ifx = ARCH.ifx && ARCH.ifx.p === p && ARCH.ifx.id === s ? null : { p, id: s }; paintStruct(); return; }
  const hx = archFocusHx(k);
  if(!hx && (!/^en\d+$/.test(k) || typeof archFlowEntries !== 'function')) return;
  const mods = d.modules || [], m = mods.find(x => x && x.id === s), e = hx || archFlowEntries(d, mods, ARCH.tests || archIsTest(m)).find(x => x.k === k);
  if(!e || !e.flows.length) return;
  const cur = ARCH.lit && ARCH.lit.p === p && Array.isArray(ARCH.lit.fs) ? ARCH.lit.fs.join('\u0001') : null;
  ARCH.lit = cur === e.flows.join('\u0001') ? null : { p, flow: e.flows[0], fs: e.flows.slice() };
  ARCH.op = ''; paintStruct();
}
