// ── Mermaid layered layout, one block at a time (81e mmdLayout): cycle breaking, ranks, crossing reduction, coordinates ──
// ★2026-09-29 docs/ARCHITECTURE.md's flowchart was unreadable (lines through boxes, tangles, labels on labels).
// ⇒ Sugiyama-style: long edges get dummy nodes, barycentre sweeps + transpose keep the fewest crossings, layers are spaced
// for the lanes and labels that cross each gap. Routing (81g) runs afterwards on the finished boxes.

// Cycle-breaking candidates (Sets of reversed 'a\u0001b'): a DFS in source order (what mermaid/dagre does), then Eades'
// greedy order counting merged edges (e.w) and counting pairs. mmdPlace keeps the one that lays out best.
function mmdAcyclic(items, es){
  const out = {}, inn = {}, wt = {}, key = (a, b) => a + '\u0001' + b, st = {}, dfsB = new Set();
  items.forEach(v => { out[v] = []; inn[v] = []; });
  es.forEach(e => { if(e.a !== e.b){ out[e.a].push(e.b); inn[e.b].push(e.a); wt[key(e.a, e.b)] = e.w || 1; } });
  const dfs = v => { st[v] = 1; out[v].forEach(w => { if(st[w] === 1) dfsB.add(key(v, w)); else if(!st[w]) dfs(w); }); st[v] = 2; };
  items.forEach(v => { if(!st[v]) dfs(v); });
  const eades = W => {
    const left = new Set(items), dout = {}, din = {}, s1 = [], s2 = [], ix = {}, B = new Set();
    items.forEach(v => { dout[v] = out[v].reduce((s, w) => s + W(v, w), 0); din[v] = inn[v].reduce((s, u) => s + W(u, v), 0); });
    const drop = v => { left.delete(v); out[v].forEach(w => { if(left.has(w)) din[w] -= W(v, w); }); inn[v].forEach(u => { if(left.has(u)) dout[u] -= W(u, v); }); };
    while(left.size){
      for(let moved = true; moved;){
        moved = false;
        for(const v of items){
          if(!left.has(v)) continue;
          if(!dout[v]){ s2.unshift(v); drop(v); moved = true; } else if(!din[v]){ s1.push(v); drop(v); moved = true; }
        }
      }
      let best = null;
      for(const v of items) if(left.has(v) && (best === null || dout[v] - din[v] > dout[best] - din[best])) best = v;
      if(best !== null){ s1.push(best); drop(best); }
    }
    s1.concat(s2).forEach((v, i) => { ix[v] = i; });
    es.forEach(e => { if(e.a !== e.b && ix[e.a] > ix[e.b]) B.add(key(e.a, e.b)); });
    return B;
  };
  const all = [dfsB, eades((a, b) => wt[key(a, b)]), eades(() => 1)], seen = new Set();
  return all.filter(B => { const k = Array.from(B).sort().join('\u0003'); if(seen.has(k)) return false; seen.add(k); return true; });
}
// A fixed rank map applies only when it ranks every item (a partial map would leave the rest unplaceable).
function mmdFixed(items, fix){ return !!fix && items.every(v => typeof fix[v] === 'number' && isFinite(fix[v])); }
// Layers over items and edges es [{a, b}]: reversed back edges, longest path, then each node slides to its cheaper end
// (sources right above their successors, sinks right below their predecessors). → { rank, back, P, S } (forward adjacency).
// fix = id → rank: when it covers every item the ranks are taken as given and edges pointing up or sideways are the back edges.
function mmdRank(items, es, back, fix){
  const fx = mmdFixed(items, fix);
  back = fx ? new Set(es.filter(e => e.a !== e.b && fix[e.a] >= fix[e.b]).map(e => e.a + '\u0001' + e.b)) : back || mmdAcyclic(items, es)[0];
  const P = {}, S = {}, rank = {}, deg = {}, topo = [];
  items.forEach(v => { P[v] = []; S[v] = []; });
  es.forEach(e => { if(e.a === e.b) return; const bk = back.has(e.a + '\u0001' + e.b), a = bk ? e.b : e.a, b = bk ? e.a : e.b;
    for(let k = 0; k < (e.w || 1); k++){ S[a].push(b); P[b].push(a); } });
  if(fx){ items.forEach(v => { rank[v] = fix[v]; }); const m0 = items.length ? Math.min(...items.map(v => rank[v])) : 0; items.forEach(v => { rank[v] -= m0; }); return { rank, back, P, S }; }
  items.forEach(v => { deg[v] = P[v].length; });
  const q = items.filter(v => !deg[v]);
  while(q.length){ const v = q.shift(); topo.push(v); S[v].forEach(w => { if(!--deg[w]) q.push(w); }); }
  topo.forEach(v => { rank[v] = P[v].length ? Math.max(...P[v].map(u => rank[u] + 1)) : 0; });
  for(let it = 0; it < 8; it++){
    let ch = false;
    topo.forEach(v => {
      const lo = P[v].length ? Math.max(...P[v].map(u => rank[u] + 1)) : -Infinity, hi = S[v].length ? Math.min(...S[v].map(w => rank[w] - 1)) : Infinity;
      const d = P[v].length - S[v].length;
      let r = !isFinite(lo) && !isFinite(hi) ? 0 : d > 0 ? lo : d < 0 ? hi : rank[v];
      r = Math.max(lo, Math.min(hi, r));
      if(r !== rank[v]){ rank[v] = r; ch = true; }
    });
    if(!ch) break;
  }
  const m = items.length ? Math.min(...items.map(v => rank[v])) : 0;
  items.forEach(v => { rank[v] -= m; });
  return { rank, back, P, S };
}
// Weighted isotonic fit (pool adjacent violators): non-decreasing y minimising sum w·(y − t)².
function mmdPav(t, w){
  const bl = [], y = [];
  t.forEach((x, i) => {
    bl.push([x * w[i], w[i], 1]);
    while(bl.length > 1){ const a = bl[bl.length - 2], b = bl[bl.length - 1]; if(a[0] / a[1] <= b[0] / b[1]) break; a[0] += b[0]; a[1] += b[1]; a[2] += b[2]; bl.pop(); }
  });
  bl.forEach(b => { for(let k = 0; k < b[2]; k++) y.push(b[0] / b[1]); });
  return y;
}
// Layer order with the fewest crossings: alternating barycentre sweeps + adjacent transposes, best order kept.
// L = [[ids]] (edited in place), up/dn = id → [[id, w]]; vertices without neighbours on the swept side keep their slot.
function mmdOrder(L, up, dn){
  const pos = {};
  const idx = () => L.forEach(l => l.forEach((v, i) => { pos[v] = i; }));
  const cross = () => {
    let c = 0;
    for(let r = 0; r + 1 < L.length; r++){
      const s = [];
      L[r].forEach(u => dn[u].forEach(x => s.push([pos[u], pos[x[0]]])));
      for(let i = 0; i < s.length; i++) for(let j = i + 1; j < s.length; j++) if((s[i][0] - s[j][0]) * (s[i][1] - s[j][1]) < 0) c++;
    }
    return c;
  };
  const sweep = (r, nb) => {
    const l = L[r], bc = {};
    l.forEach(v => { const ns = nb[v]; bc[v] = ns.length ? ns.reduce((s, x) => s + pos[x[0]], 0) / ns.length : null; });
    const mv = l.filter(v => bc[v] !== null).sort((a, b) => bc[a] - bc[b] || pos[a] - pos[b]);
    let k = 0;
    L[r] = l.map(v => bc[v] === null ? v : mv[k++]);
    L[r].forEach((v, i) => { pos[v] = i; });
  };
  const pairC = (u, v) => { let c = 0; [up, dn].forEach(nb => nb[u].forEach(a => nb[v].forEach(b => { if(pos[a[0]] > pos[b[0]]) c++; }))); return c; };
  const transpose = () => {
    for(let n = 0, imp = true; imp && n < 6; n++){
      imp = false;
      L.forEach(l => { for(let i = 0; i + 1 < l.length; i++){ const u = l[i], v = l[i + 1];
        if(pairC(v, u) < pairC(u, v)){ l[i] = v; l[i + 1] = u; pos[v] = i; pos[u] = i + 1; imp = true; } } });
    }
  };
  idx();
  let best = cross(), keep = L.map(l => l.slice()), stale = 0;
  for(let it = 0; it < 24 && best > 0 && stale < 6; it++){
    if(it % 2 === 0) for(let r = 1; r < L.length; r++) sweep(r, up);
    else for(let r = L.length - 2; r >= 0; r--) sweep(r, dn);
    transpose();
    const c = cross();
    if(c < best){ best = c; keep = L.map(l => l.slice()); stale = 0; } else stale++;
  }
  keep.forEach((l, r) => { L[r] = l; });
  return best;
}
// Ranked, dummy-split and ordered layers for one cycle-breaking choice; cost = crossings·4 + dummies + reversed·2 + layers·3
// (⚠without the layer term Eades-by-weight won ARCHITECTURE.md with a 7-layer, 2636px-wide chain).
function mmdLayers(items, es, back, hint, fix){
  const R = mmdRank(items, es, back, fix), rank = Object.assign({}, R.rank), up = {}, dn = {}, isD = {}, L = [], ord = {}, lab = [];
  // Start order: source order, or the outside neighbours' side (hint); an item without a hint stays behind its predecessor.
  let hv = -Infinity;
  const io = items.map((v, i) => { if(hint && hint[v] != null) hv = hint[v]; return [v, hv, i]; }).sort((a, b) => a[1] - b[1] || a[2] - b[2]);
  io.forEach(([v], i) => { up[v] = []; dn[v] = []; ord[v] = i; });
  const link = (u, v, w) => { dn[u].push([v, w]); up[v].push([u, w]); };
  let nd = 0, rev = 0;
  es.forEach(e => {
    if(e.a === e.b) return;
    const bk = R.back.has(e.a + '\u0001' + e.b), a = bk ? e.b : e.a, b = bk ? e.a : e.b, n = rank[b] - rank[a];
    let u = a;
    if(bk) rev += e.w || 1;
    for(let r = rank[a] + 1; r < rank[b]; r++){                 // dummy chain: a lane through every layer the edge spans
      const d = '\u0002' + (nd++);
      isD[d] = 1; rank[d] = r; ord[d] = ord[a] + 0.5; up[d] = []; dn[d] = [];
      link(u, d, (u === a ? 2 : 4) * (e.w || 1)); u = d;
    }
    link(u, b, (u === a ? 1 : 2) * (e.w || 1));               // weights: straight dummy chains first
    if(e.lw) lab.push([rank[a] + Math.max(0, Math.floor((n - 1) / 2)), e.lw, e.lh]);
  });
  Object.keys(rank).forEach(v => { (L[rank[v]] = L[rank[v]] || []).push(v); });
  for(let r = 0; r < L.length; r++) L[r] = (L[r] || []).sort((a, b) => ord[a] - ord[b]);
  const cr = mmdOrder(L, up, dn);
  return { rank, up, dn, isD, L, lab, cost: cr * 4 + nd + rev * 2 + 3 * Math.max(0, L.length - 1) };
}
// Items of one block → positions (top-left, block-local) and block size. es = [{a, b, lw, lh, w}] (label size, 0 when none).
// room = {w, h} target drawing size (84j focus view): spacing grows to fill it, boxes and text never scale; null = natural.
// one = item → truthy (sg flag oneLayer, 84j2 entry rows): the whole block is one layer in source order, each item centred in it.
// front = item → truthy (g.front, 84j2 modules an entry serves): those items take the first rows of the block.
function mmdPlace(items, es, sizeOf, dir, hint, fix, room, one, front){
  // ⚠opt-in only: without one every other diagram keeps its bytes. With one the whole block is one layer (an edge between two
  // rows, e.g. entry → entry module, otherwise ranks them side by side) in source order.
  if(one && items.some(one)){ hint = null; fix = {}; items.forEach(v => { fix[v] = 0; }); }
  else if(front && !mmdFixed(items, fix) && items.some(front)){
    // Every front item on rank 0, one shared first row even when one calls another; the rest keep their relative ranks from 1,
    // ranked with every edge into a front item reversed (a filter sits above its callers). ⚠Ranking only: arrows keep their direction.
    const R = mmdRank(items, es.map(e => front(e.b) ? { a: e.b, b: e.a, w: e.w } : e)).rank, rest = items.filter(v => !front(v));
    const m0 = rest.length ? Math.min(...rest.map(v => R[v])) : 0;
    fix = {}; items.forEach(v => { fix[v] = front(v) ? 0 : 1 + R[v] - m0; });
  }
  const vert = dir === 'TB' || dir === 'BT', flip = dir === 'BT' || dir === 'RL', x = {};
  const cand = mmdFixed(items, fix) ? [null] : items.length <= 80 ? mmdAcyclic(items, es) : [null];   // ⚠each candidate is a full crossing reduction: small blocks only
  let Y = null;
  cand.forEach(B => { const y = mmdLayers(items, es, B, hint, fix); if(!Y || y.cost < Y.cost) Y = y; });
  const { rank, up, dn, isD, L, lab } = Y;
  const SEP = vert ? 36 : 28, C = v => isD[v] ? 0 : vert ? sizeOf(v).w : sizeOf(v).h, M = v => isD[v] ? 0 : vert ? sizeOf(v).h : sizeOf(v).w;
  let ex = 0;   // extra gap between two real boxes of a layer (room only)
  const sep = (u, v) => isD[u] && isD[v] ? 10 : isD[u] || isD[v] ? 18 : SEP + ex;
  const offs = () => L.map(l => { const o = [0]; for(let i = 1; i < l.length; i++) o[i] = o[i - 1] + C(l[i - 1]) / 2 + sep(l[i - 1], l[i]) + C(l[i]) / 2; return o; });
  let off = offs();
  const fit = (r, nbs) => {
    const l = L[r], t = [], w = [];
    l.forEach((v, i) => {
      let s = 0, W = 0;
      nbs.forEach(nb => nb[v].forEach(([u, ww]) => { s += x[u] * ww; W += ww; }));
      t.push((W ? s / W : x[v]) - off[r][i]); w.push(W || 0.01);
    });
    const y = mmdPav(t, w);
    l.forEach((v, i) => { x[v] = y[i] + off[r][i]; });
  };
  const spread = () => {
    L.forEach((l, r) => l.forEach((v, i) => { x[v] = off[r][i] - off[r][l.length - 1] / 2; }));
    for(let it = 0; it < 8; it++){
      for(let r = 1; r < L.length; r++) fit(r, [up]);
      for(let r = L.length - 2; r >= 0; r--) fit(r, [dn]);
    }
    for(let r = 0; r < L.length; r++) fit(r, [up, dn]);
    let a = Infinity, b = -Infinity;
    Object.keys(x).forEach(v => { a = Math.min(a, x[v] - C(v) / 2); b = Math.max(b, x[v] + C(v) / 2); });
    return b - a;
  };
  const span = spread(), RC = room ? (vert ? room.w : room.h) : 0;
  if(RC > 0 && span < RC){
    // ⚠ex comes from the fullest layer, then shrinks once if the barycentre pass pushed the span past the room
    const kr = L.map(l => { let k = 0; for(let i = 1; i < l.length; i++) if(!isD[l[i - 1]] && !isD[l[i]]) k++; return k; });
    let e = Infinity;
    L.forEach((l, r) => { if(kr[r]) e = Math.min(e, (RC - (off[r][l.length - 1] + C(l[0]) / 2 + C(l[l.length - 1]) / 2)) / kr[r]); });
    ex = isFinite(e) ? Math.max(0, Math.min(120, e)) : 0;
    if(ex){ off = offs(); const s2 = spread(); if(s2 > RC){ ex = Math.max(0, ex - (s2 - RC) / Math.max(...kr)); off = offs(); spread(); } }
  }
  // Gap after each layer: stubs + one lane per line crossing it, or room for the labels placed in it.
  const gap = L.map((l, r) => {
    const U = new Set(), D = new Set();
    l.forEach(u => dn[u].forEach(([v]) => { U.add(u); D.add(v); }));
    return Math.min(vert ? 150 : 170, Math.max(vert ? 44 : 52, 32 + 8 * Math.min(U.size, D.size)));
  });
  lab.forEach(([r, lw, lh]) => { if(r < gap.length) gap[r] = Math.max(gap[r], vert ? lh + 60 : Math.min(320, lw + 44)); });
  const T = L.map(l => Math.max(0, ...l.map(M))), mp = [], RM = room ? (vert ? room.h : room.w) : 0;
  if(RM > 0 && L.length > 1){ const tot = T.reduce((a, t) => a + t, 0) + gap.slice(0, -1).reduce((a, t) => a + t, 0);
    if(tot < RM){ const gx = Math.min(480, (RM - tot) / (L.length - 1)); for(let r = 0; r < gap.length - 1; r++) gap[r] += gx; } }   // room: wider layer gaps
  let acc = 0;
  T.forEach((t, r) => { mp[r] = acc; acc += t + (r < T.length - 1 ? gap[r] : 0); });
  let lo = Infinity, hi = -Infinity;
  Object.keys(x).forEach(v => { lo = Math.min(lo, x[v] - C(v) / 2); hi = Math.max(hi, x[v] + C(v) / 2); });
  if(!items.length){ lo = 0; hi = 0; }
  const out = {};
  items.forEach(v => {
    const r = rank[v];
    let m = mp[r] + (T[r] - M(v)) / 2;
    if(flip) m = acc - m - M(v);
    const c = x[v] - C(v) / 2 - lo;
    out[v] = vert ? { x: c, y: m } : { x: m, y: c };
  });
  return { pos: out, w: vert ? hi - lo : acc, h: vert ? acc : hi - lo };
}
