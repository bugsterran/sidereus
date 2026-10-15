// ── Mermaid edges: orthogonal routes on the 81g0 grid A* (relRoute), port spreading, lanes, labels, quality counts ──
// ⚠Walls are per edge: every node box and subgraph title, every subgraph box that is not an ancestor of either end, and —
// when both ends share a subgraph — everything outside it. The grid keeps one group id per cell, which can't express
// nested subgraphs, so relRoute runs on relGridOf (81g0) with this edge's walls copied in first.
// ⚠Past MMD_BUDGET ms the remaining edges get the plain elbow (mmdRoute), which may cross boxes; mmdQuality counts that.
const MMD_BUDGET = 600, MMD_UNCROSS = 120;   // ms: routing, then crossing clean-up (mmdUncross)

// Subgraph ancestors of a node or subgraph id, innermost first.
function mmdAnc(g, id){
  const s = [];
  for(let p = g.sgs[id] ? g.sgs[id].parent : g.nodes[id] ? g.nodes[id].sg : ''; p; p = g.sgs[p].parent) s.push(p);
  return s;
}
// Fallback edge between two absolute rects: an elbow along the block direction when B is ahead of A, else a clipped straight line.
function mmdRoute(A, B, dir){
  const vert = dir === 'TB' || dir === 'BT', s = (dir === 'BT' || dir === 'RL') ? -1 : 1, m = vert ? 1 : 0, c = 1 - m;
  const ac = [A.x + A.w / 2, A.y + A.h / 2], bc = [B.x + B.w / 2, B.y + B.h / 2];
  const aLo = [A.x, A.y], aSz = [A.w, A.h], bLo = [B.x, B.y], bSz = [B.w, B.h];
  const aEnd = s > 0 ? aLo[m] + aSz[m] : aLo[m], bEnd = s > 0 ? bLo[m] : bLo[m] + bSz[m];
  const P = (mm, x) => m ? [x, mm] : [mm, x];
  if((bEnd - aEnd) * s >= 8){
    const mid = (aEnd + bEnd) / 2;
    if(Math.abs(ac[c] - bc[c]) < 1){ const p = P(mid, ac[c]); return { pts: [P(aEnd, ac[c]), P(bEnd, ac[c])], lx: p[0], ly: p[1] }; }
    const lp = vert ? P((mid + bEnd) / 2, bc[c]) : P(mid, (ac[c] + bc[c]) / 2);
    return { pts: [P(aEnd, ac[c]), P(mid, ac[c]), P(mid, bc[c]), P(bEnd, bc[c])], lx: lp[0], ly: lp[1] };
  }
  const clip = (R, f, t) => {
    const dx = t[0] - f[0], dy = t[1] - f[1];
    const k = Math.min(1, dx ? R.w / 2 / Math.abs(dx) : Infinity, dy ? R.h / 2 / Math.abs(dy) : Infinity);
    return [f[0] + dx * k, f[1] + dy * k];
  };
  const p0 = clip(A, ac, bc), p1 = clip(B, bc, ac);
  return { pts: [p0, p1], lx: (p0[0] + p1[0]) / 2, ly: (p0[1] + p1[1]) / 2 };
}
// Segment a-b ([x, y] points) has a stretch strictly inside rect R grown by m (m < 0 shrinks; touching the edge is outside).
function mmdSegRect(a, b, R, m){
  const x0 = R.x - m, x1 = R.x + R.w + m, y0 = R.y - m, y1 = R.y + R.h + m, dx = b[0] - a[0], dy = b[1] - a[1];
  if(x1 <= x0 || y1 <= y0) return false;
  let t0 = 0, t1 = 1;
  const clip = (p, q) => {
    if(Math.abs(p) < 1e-9) return q > 1e-9;
    const r = q / p;
    if(p < 0){ if(r > t1) return false; if(r > t0) t0 = r; } else { if(r < t0) return false; if(r < t1) t1 = r; }
    return true;
  };
  return clip(-dx, a[0] - x0) && clip(dx, x1 - a[0]) && clip(-dy, a[1] - y0) && clip(dy, y1 - a[1]) && t1 - t0 > 1e-9;
}
// Several edge ends on one side of a box spread centre-out in the order their far ends lie, so they neither cross nor
// share a port; ends already on one point (a trunk) keep one slot. A move that leaves a wall-free segment is undone.
function mmdSpread(pts, ends, rects, clear){
  const side = (o, q) => Math.abs(q.y - o.y) < 0.5 ? 0 : Math.abs(q.y - o.y - o.h) < 0.5 ? 2 : Math.abs(q.x - o.x) < 0.5 ? 3 : Math.abs(q.x - o.x - o.w) < 0.5 ? 1 : -1;
  const at = {};
  Object.keys(pts).forEach(k => {
    const p = pts[k], z = p.length - 1;
    if(p.length < 2) return;
    // ★2026-09-29 a straight 2-point route can't move (both ends would shift) but is kept as a fixed slot: skipping it let
    // another end on that side re-centre onto it (FLOW a2->a3 / a3->b2 overlapped 40px on the diamond's top vertex).
    const fx = p.length < 3;
    [[0, 0, 1, Math.min(2, z)], [1, z, z - 1, Math.max(0, z - 2)]].forEach(([w, i, j, far]) => {
      const id = ends[k][w], o = rects[id], sd = side(o, p[i]);
      if(sd >= 0) (at[id + '|' + sd] = at[id + '|' + sd] || []).push({ k, p, i, j, far, o, sd, fx });
    });
  });
  Object.keys(at).forEach(key => {
    const Ls = at[key], o = Ls[0].o, c = Ls[0].sd % 2 ? 'y' : 'x', lo = c === 'x' ? o.x : o.y, len = c === 'x' ? o.w : o.h, sl = {};
    let n = 0;
    if(Ls.every(q => q.fx)) return;
    Ls.sort((u, w) => u.p[u.far][c] - w.p[w.far][c] || u.p[u.i][c] - w.p[w.i][c]).forEach(q => {
      const b = Math.round(q.p[q.i][c]) + (q.fx ? 'f' : '');   // ⚠a fixed end never joins a trunk slot: in and out would overlap
      if(!(b in sl)) sl[b] = n++;
      q.sl = sl[b];
    });
    const st = n > 1 ? Math.min(18, (len - 20) / (n - 1)) : 0;
    if(n > 1 && st < 6) return;                                 // too many for this side: keep the A* ports
    const f = Ls.find(q => q.fx), off = f ? f.p[f.i][c] - (lo + len / 2 + (f.sl - (n - 1) / 2) * st) : 0;   // slots slide to keep the fixed one
    if(f && (Ls.some(q => q.fx && q.sl !== f.sl) || Math.abs(off) + (n - 1) / 2 * st > len / 2 - 10)) return;
    Ls.forEach(q => {
      const v = lo + len / 2 + (q.sl - (n - 1) / 2) * st + off, p = q.p, old = p[q.i][c], oj = p[q.j][c];
      if(q.fx || Math.abs(oj - old) > 0.5 || Math.abs(v - old) < 0.5) return;
      p[q.i][c] = v; p[q.j][c] = v;
      const nb = q.i === 0 ? p[2] : p[p.length - 3];
      if(!clear(p[q.i], p[q.j], null, q.k) || (nb && !clear(p[q.j], nb, null, q.k))){ p[q.i][c] = old; p[q.j][c] = oj; }
    });
  });
}
// Crossing clean-up after lanes: for two crossing edges, a pair of parallel runs (each with every line merged onto it) swaps
// places or one hops past the other; kept only when total crossings drop and the moved runs stay clear, unreversed, off
// other lines and (end runs) on their box side. ★2026-09-29: crossings 32 -> 15 (ARCHITECTURE.md #1), 33 -> 12 (.ko); pierce/label overlap 0 — nested fans leaving one side crossed twice each.
function mmdUncross(pts, ends, rects, clear, budget){
  const K = Object.keys(pts), t0 = Date.now(), cr = (a, b, c) => Math.sign((b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x));
  const X = (P, Q) => { let n = 0; for(let i = 0; i + 1 < P.length; i++) for(let j = 0; j + 1 < Q.length; j++)
    if(cr(P[i], P[i + 1], Q[j]) * cr(P[i], P[i + 1], Q[j + 1]) < 0 && cr(Q[j], Q[j + 1], P[i]) * cr(Q[j], Q[j + 1], P[i + 1]) < 0) n++; return n; };
  const ax = (p, s) => Math.abs(p[s].x - p[s + 1].x) < 0.5 ? (Math.abs(p[s].y - p[s + 1].y) < 0.5 ? '' : 'x') : Math.abs(p[s].y - p[s + 1].y) < 0.5 ? 'y' : '';
  const span = (p, s, c) => { const o = c === 'x' ? 'y' : 'x'; return [Math.min(p[s][o], p[s + 1][o]), Math.max(p[s][o], p[s + 1][o])]; };
  const olap = (u, v) => Math.min(u[1], v[1]) - Math.max(u[0], v[0]) > 1;
  // Every run lying on run (k, s): a trunk moves as one.
  const group = (k, s) => { const p = pts[k], c = ax(p, s), sp = span(p, s, c), G = [];
    K.forEach(m => { const q = pts[m]; for(let t = 0; t + 1 < q.length; t++) if(ax(q, t) === c && Math.abs(q[t][c] - p[s][c]) < 0.5 && olap(span(q, t, c), sp)) G.push([m, t]); });
    return G; };
  const ok = (mv, c) => mv.every(([k, s]) => {
    const p = pts[k], n = p.length;
    for(const [w, i] of [[0, 0], [1, n - 1]]) if(s === (w ? n - 2 : 0)){
      const R = rects[ends[k][w]], lo = c === 'x' ? R.x : R.y, hi = lo + (c === 'x' ? R.w : R.h);
      if(p[i][c] < lo + 6 || p[i][c] > hi - 6) return false;
    }
    for(const t of [s - 1, s + 1]){
      if(t < 0 || t + 1 >= n) continue;
      const d = p[t + 1][c] - p[t][c], d0 = p[t].o0;
      if(Math.abs(d) < (t === 0 || t === n - 2 ? Math.min(Math.abs(d0), 12) : 2) || Math.sign(d) !== Math.sign(d0)) return false;
    }
    for(let t = Math.max(0, s - 1); t <= Math.min(n - 2, s + 1); t++){
      if(!clear(p[t], p[t + 1], null, k)) return false;
      const a = ax(p, t);
      if(a && K.some(m => { if(mv.some(x => x[0] === m)) return false; const q = pts[m];
        for(let u = 0; u + 1 < q.length; u++) if(ax(q, u) === a && Math.abs(q[u][a] - p[t][a]) < 4 && olap(span(q, u, a), span(p, t, a))) return true; return false; })) return false;
    }
    return true;
  });
  for(let pass = 0, imp = true; imp && pass < 4 && Date.now() - t0 < budget; pass++){
    imp = false;
    for(let a = 0; a < K.length; a++) for(let b = a + 1; b < K.length; b++){
      if(Date.now() - t0 >= budget || !X(pts[K[a]], pts[K[b]])) continue;
      const P = pts[K[a]], Q = pts[K[b]];
      for(let s = 0; s + 1 < P.length; s++) for(let t = 0; t + 1 < Q.length; t++){
        const c = ax(P, s);
        if(!c || ax(Q, t) !== c || Math.abs(P[s][c] - Q[t][c]) > 40 || Math.abs(P[s][c] - Q[t][c]) < 0.5 || !olap(span(P, s, c), span(Q, t, c))) continue;
        const GA = group(K[a], s), GB = group(K[b], t);
        if(GA.some(x => GB.some(y => x[0] === y[0]))) continue;
        const ca = P[s][c], cb = Q[t][c], sg = Math.sign(cb - ca), E = Array.from(new Set(GA.concat(GB).map(x => x[0])));
        const tot = () => { let n = 0; E.forEach((e, i) => K.forEach(m => { const j = E.indexOf(m); if(m !== e && (j < 0 || j > i)) n += X(pts[e], pts[m]); })); return n; };
        const before = tot();
        let done = false;
        for(const moves of [[[GA, cb], [GB, ca]], [[GA, cb + 8 * sg]], [[GB, ca - 8 * sg]]]){
          const mv = [], old = [];
          moves.forEach(([G, v]) => G.forEach(([k, u]) => { const p = pts[k]; mv.push([k, u]);
            [u - 1, u + 1].forEach(w => { if(w >= 0 && w + 1 < p.length && p[w].o0 == null) p[w].o0 = p[w + 1][c] - p[w][c]; });
            old.push([p[u], p[u][c]], [p[u + 1], p[u + 1][c]]); p[u][c] = v; p[u + 1][c] = v; }));
          if(ok(mv, c) && tot() < before){ done = true; break; }
          old.reverse().forEach(([q, v]) => { q[c] = v; });
        }
        K.forEach(k => pts[k].forEach(q => { delete q.o0; }));
        if(done){ imp = true; break; }
      }
    }
  }
}
// Absolute node/subgraph rects → routed edges [{from, to, style, head, both, label, pts: [[x, y]], d}] in g.edges order.
function mmdRouteAll(g, nodes, sgs, dirOf){
  const C = RR_C, rects = Object.assign({}, sgs, nodes), ids = Object.keys(rects);
  let W = 0, H = 0;
  ids.forEach(k => { W = Math.max(W, rects[k].x + rects[k].w); H = Math.max(H, rects[k].y + rects[k].h); });
  const ox = -48, oy = -48, nx = Math.ceil((W + 96) / C), ny = Math.ceil((H + 96) / C), G = relGridOf(ox, oy, nx, ny), blk = G.blk;
  const span = (R, m) => [Math.max(0, Math.ceil((R.x - m - ox) / C - 0.5)), Math.min(nx - 1, Math.floor((R.x + R.w + m - ox) / C - 0.5)),
    Math.max(0, Math.ceil((R.y - m - oy) / C - 0.5)), Math.min(ny - 1, Math.floor((R.y + R.h + m - oy) / C - 0.5))];
  const fill = (a, r) => { for(let j = r[2]; j <= r[3]; j++) if(r[0] <= r[1]) a.fill(1, j * nx + r[0], j * nx + r[1] + 1); };
  const base = new Uint8Array(nx * ny), anc = {}, ix = {};
  Object.keys(nodes).forEach(k => { fill(base, G.rng[k] = span(nodes[k], 2)); });
  Object.keys(sgs).forEach(k => { G.rng[k] = span(sgs[k], 2); if(sgs[k].tr) fill(base, span(sgs[k].tr, 2)); });
  ids.forEach((k, i) => { anc[k] = mmdAnc(g, k); ix[k] = i; });
  const list = [], fan = {}, pts = {}, ends = {}, walls = {};
  g.edges.forEach((e, i) => {
    if(!rects[e.from] || !rects[e.to] || e.from === e.to || e.style === 'invis' || anc[e.to].includes(e.from) || anc[e.from].includes(e.to)) return;
    list.push(i);
    if(!e.label) fan[e.to] = (fan[e.to] || 0) + 1;
  });
  const far = i => { const A = rects[g.edges[i].from], B = rects[g.edges[i].to]; return Math.abs(A.x + A.w / 2 - B.x - B.w / 2) + Math.abs(A.y + A.h / 2 - B.y - B.h / 2); };
  const fanOf = i => g.edges[i].label ? 0 : fan[g.edges[i].to];
  // Node edge with both ends in pass bands (84j2) → [source pens, target pens] (top · right · bottom · left), else null.
  // Other band below/above: bottom out, top in (or the reverse); same band: sides when the rows overlap, else by relative y.
  const bandPens = (f, t) => {
    const band = k => { const a = anc[k], s = a[a.length - 1]; return nodes[k] && s && g.sgs[s] && g.sgs[s].pass ? s : ''; };
    const sf = band(f), st = band(t);
    if(!sf || !st) return null;
    const X = Infinity, A = rects[f], B = rects[t], down = [[X, X, 0, X], [0, X, X, X]], up = [[0, X, X, X], [X, X, 0, X]];
    if(sf !== st){ const P = rects[sf], Q = rects[st]; return Q.y >= P.y + P.h ? down : P.y >= Q.y + Q.h ? up : null; }
    if(B.y < A.y + A.h && A.y < B.y + B.h) return [[X, 0, X, 0], [X, 0, X, 0]];
    return B.y >= A.y + A.h ? down : up;
  };
  const now = () => typeof performance !== 'undefined' ? performance.now() : Date.now(), t0 = now();
  // Big unlabelled fan-ins first (their trunk goes down before others take the gutters), then short edges.
  list.slice().sort((u, w) => fanOf(w) - fanOf(u) || far(u) - far(w) || u - w).forEach(i => {
    const e = g.edges[i], A = rects[e.from], B = rects[e.to], al = new Set(anc[e.from].concat(anc[e.to]));
    const lca = anc[e.from].find(s => anc[e.to].includes(s)) || '', ws = [];
    blk.set(base);
    Object.keys(nodes).forEach(k => { ws.push([nodes[k], k === e.from || k === e.to ? -0.5 : 2]); });
    Object.keys(sgs).forEach(s => {
      if(sgs[s].tr) ws.push([sgs[s].tr, 2]);
      if(al.has(s) || (g.sgs[s] && g.sgs[s].pass)) return;   // pass (84j2 layer band): lines cross it; its title and inner boxes stay walls
      const own = s === e.from || s === e.to;
      fill(blk, own ? G.rng[s] : span(sgs[s], 4));
      ws.push([sgs[s], own ? -0.5 : 3]);
    });
    if(lca){
      const r = span(sgs[lca], -3);
      for(let j = 0; j < ny; j++) for(let q = 0; q < nx; q++) if(q < r[0] || q > r[1] || j < r[2] || j > r[3]) blk[j * nx + q] = 1;
    }
    walls[i] = { ws, box: lca ? sgs[lca] : null };
    G.tpen = /^(TB|BT)$/.test(dirOf(lca)) ? null : [RR_SIDEIN, 0, RR_SIDEIN, 0];   // LR: enter a side, not top/bottom
    // Labelled edges get their own bundle ids: they never merge into a trunk, so each keeps a run of its own for the label.
    G.cs = e.label ? 1e6 + i : ix[e.from] * 8; G.ct = e.label ? 2e6 + i : ix[e.to] * 8;
    // LR (edge and source block), target ahead: the source leaves by a side (top/bottom stub rows walled), as targets enter one.
    if(G.tpen && nodes[e.from] && !/^(TB|BT)$/.test(dirOf(g.nodes[e.from].sg)) && B.x >= A.x + A.w + 16){ const r = G.rng[e.from]; [r[2] - 1, r[3] + 1].forEach(j => { if(j >= 0 && j < ny) for(let q = r[0]; q <= r[1]; q++) blk[j * nx + q] = 1; }); }
    // ⚠84i component look only (end inside a box3d class): leave and enter method boxes sideways, so no stub runs up through the class name
    [e.from, e.to].forEach(k => { const sg = nodes[k] && g.nodes[k].sg; if(!sg || !g.sgs[sg] || !g.sgs[sg].box3d) return;
      const r = G.rng[k]; [r[2] - 1, r[3] + 1].forEach(j => { if(j >= 0 && j < ny) for(let q = r[0]; q <= r[1]; q++) blk[j * nx + q] = 1; }); });
    // ⚠Pass bands (84j2): cross-band lines leave the source bottom/top and enter the target top/bottom only —
    // with free pens a side entry (RR_SIDEIN) was cheaper than the turn (RR_TURN) into a top port, so a hub's callers bussed into its sides.
    const tp0 = G.tpen, bp = bandPens(e.from, e.to);
    G.spen = bp && bp[0]; if(bp) G.tpen = bp[1];
    let p = null;
    if(now() - t0 < MMD_BUDGET){
      const R = (occ, hw, cap, nn) => { G.nbOff = G.stubOff = nn; return relRoute(G, A, B, G.rng[e.from], G.rng[e.to], 0, 0, occ, hw, cap); };
      const run = () => R(true, 2 * RR_HW, RR_POPS / 3) || R(true, 4 * RR_HW, RR_POPS) || R(false, 2 * RR_HW, 3 * RR_POPS) || R(false, 4 * RR_HW, 3 * RR_POPS, 1);
      p = run();
      // Strict ports found no route: target ports relaxed first (the source keeps its band exit), then both, before the elbow fallback.
      if(!p && bp){ G.tpen = tp0; p = run(); }
      if(!p && bp){ G.spen = null; p = run(); }
      G.nbOff = G.stubOff = 0;
    }
    G.spen = null;
    if(p) relOccMark(G, p);
    else p = mmdRoute(A, B, dirOf(lca)).pts.map(q => ({ x: q[0], y: q[1] }));
    pts[i] = p; ends[i] = [e.from, e.to, e.label ? 'l' + i : 0];
  });
  G.tpen = null; G.spen = null;
  const clear = (s, t, sk, k) => {
    const w = walls[k], a = [s.x, s.y], b = [t.x, t.y];
    if(w.box && (Math.min(s.x, t.x) < w.box.x + 2 || Math.max(s.x, t.x) > w.box.x + w.box.w - 2 || Math.min(s.y, t.y) < w.box.y + 2 || Math.max(s.y, t.y) > w.box.y + w.box.h - 2)) return false;
    return !w.ws.some(([R, m]) => mmdSegRect(a, b, R, m));
  };
  mmdSpread(pts, ends, rects, clear);
  relLanes(pts, ends, clear, k => k, () => RR_NSTUB);
  mmdUncross(pts, ends, rects, clear, MMD_UNCROSS);
  return g.edges.map((e, i) => {
    let p = pts[i];
    if(!p && e.from === e.to && rects[e.from] && e.style !== 'invis'){   // self loop on the right side
      const A = rects[e.from], x = A.x + A.w, y0 = A.y + A.h * 0.3, y1 = A.y + A.h * 0.7;
      p = [{ x, y: y0 }, { x: x + 18, y: y0 }, { x: x + 18, y: y1 }, { x, y: y1 }];
    }
    if(!p) return null;
    const q = relSimp(p);
    p = q.length > 1 ? q : p;
    return { from: e.from, to: e.to, style: e.style, head: e.head, both: e.both, label: e.label, pts: p.map(v => [v.x, v.y]) };
  }).filter(Boolean);
}
// Route [[x, y]] → SVG path: bends rounded (radius 6, at most half of either run). ⚠Not relOrthoD: its S-curve jogs ran a
// long diagonal across a mermaid diagram when the next run was long.
function mmdPathD(p){
  const f = v => String(Math.round(v * 10) / 10), L = (u, v) => Math.abs(u[0] - v[0]) + Math.abs(u[1] - v[1]);
  let d = 'M' + f(p[0][0]) + ',' + f(p[0][1]);
  for(let i = 1; i < p.length - 1; i++){
    const a = p[i - 1], c = p[i], n = p[i + 1], r = Math.min(6, L(a, c) / 2, L(c, n) / 2), la = L(a, c) || 1, ln = L(c, n) || 1;
    d += 'L' + f(c[0] - (c[0] - a[0]) * r / la) + ',' + f(c[1] - (c[1] - a[1]) * r / la) + 'Q' + f(c[0]) + ',' + f(c[1]) + ' '
      + f(c[0] + (n[0] - c[0]) * r / ln) + ',' + f(c[1] + (n[1] - c[1]) * r / ln);
  }
  return d + 'L' + f(p[p.length - 1][0]) + ',' + f(p[p.length - 1][1]);
}
// Circled number for a label that could not sit on its line (① … ⑳, then (21) …).
function mmdNum(n){ return n <= 20 ? String.fromCharCode(0x245F + n) : '(' + n + ')'; }
// Label pills on a free stretch of their own route: clear of boxes, titles, other pills and other edges' lines. Hardest edge
// first; centred on the line before beside it; none free → a numbered badge and a legend line (L.notes) instead of an overlap.
function mmdLabels(g, L){
  const nodeR = Object.keys(L.nodes).map(k => L.nodes[k]), sgR = Object.keys(L.sgs).map(k => L.sgs[k]), titles = sgR.map(R => R.tr).filter(Boolean);
  const ov = (a, b, m) => a.x < b.x + b.w + m && b.x < a.x + a.w + m && a.y < b.y + b.h + m && b.y < a.y + a.h + m;
  const segs = L.edges.map(e => e.pts.slice(1).map((p, i) => [e.pts[i], p])), placed = [];
  const straddle = R => sgR.some(S => ov(R, S, 0) && !(R.x >= S.x && R.y >= S.y && R.x + R.w <= S.x + S.w && R.y + R.h <= S.y + S.h));
  const hits = (R, ei) => nodeR.filter(n => ov(R, n, 3)).length + titles.filter(t => ov(R, t, 2)).length + placed.filter(q => ov(q, R, 4)).length
    + segs.reduce((s, ss, j) => s + (j !== ei && ss.some(x => mmdSegRect(x[0], x[1], R, 3)) ? 1 : 0), 0);
  const cands = (ei, w, h, beside) => {
    const ps = L.edges[ei].pts, n = ps.length - 1, len = [], out = [];
    let tot = 0, acc = 0;
    for(let k = 0; k < n; k++){ len[k] = Math.hypot(ps[k + 1][0] - ps[k][0], ps[k + 1][1] - ps[k][1]); tot += len[k]; }
    for(let k = 0; k < n; k++){
      const a = ps[k], b = ps[k + 1], l = len[k], hz = Math.abs(a[1] - b[1]) < 0.5, half = (hz ? w : h) / 2;
      const m0 = k === n - 1 || k === 0 ? half + 10 : Math.min(half, l / 2), m1 = k === n - 1 ? half + 12 : m0;   // off ports and arrowheads
      for(let t = m0; t <= l - m1 + 0.01; t += 4){
        const cx = a[0] + (b[0] - a[0]) * t / (l || 1), cy = a[1] + (b[1] - a[1]) * t / (l || 1), c = Math.abs(acc + t - tot / 2) / 24;
        out.push({ x: cx - w / 2, y: cy - h / 2, w, h, c });
        if(beside) [-1, 1].forEach(sg => out.push(hz ? { x: cx - w / 2, y: cy + sg * (h / 2 + 3) - h / 2, w, h, c: c + 8 }
          : { x: cx + sg * (w / 2 + 3) - w / 2, y: cy - h / 2, w, h, c: c + 8 }));
      }
      acc += l;
    }
    out.forEach(R => { if(straddle(R)) R.c += 20; });
    return out;
  };
  const best = (ei, w, h, beside) => { let b = null; cands(ei, w, h, beside).forEach(R => { if((!b || R.c < b.c) && !hits(R, ei)) b = R; }); return b; };
  let todo = L.edges.map((e, i) => i).filter(i => L.edges[i].label);
  const size = t => { const ls = String(t).split('\n'); return [Math.max(...ls.map(mmdTw)) + 14, ls.length * 16 + 4]; };
  const fail = [];
  while(todo.length){
    // Fewest free spots first, so a crowded edge is not boxed in by an easy one.
    let pick = -1, pc = Infinity;
    todo.forEach(i => { const [w, h] = size(L.edges[i].label), n = cands(i, w, h, true).filter(R => !hits(R, i)).length; if(n < pc){ pc = n; pick = i; } });
    todo = todo.filter(i => i !== pick);
    const [w, h] = size(L.edges[pick].label), R = pc ? best(pick, w, h, true) : null;
    if(R){ L.edges[pick].lr = { x: R.x, y: R.y, w, h }; placed.push(L.edges[pick].lr); } else fail.push(pick);
  }
  L.notes = [];
  fail.sort((a, b) => a - b).forEach((i, k) => {
    const e = L.edges[i], t = mmdNum(k + 1), w = Math.max(18, mmdTw(t) + 8), h = 18;
    let R = best(i, w, h, false);
    if(!R){ let bh = Infinity; cands(i, w, h, false).forEach(q => { const n = hits(q, i) * 100 + q.c; if(n < bh){ bh = n; R = q; } }); }
    if(!R){ const p = e.pts[0]; R = { x: p[0] - w / 2, y: p[1] - h / 2 }; }
    e.num = t; e.lr = { x: R.x, y: R.y, w, h }; placed.push(e.lr);
    L.notes.push({ num: t, label: e.label, from: e.from, to: e.to });
  });
}
// Readability counts for a laid-out graph: route segments inside a box they should not enter (other nodes, their own ends,
// subgraphs that are not an ancestor of either end), proper crossings between different edges, and label pills overlapping
// a box, a subgraph title, another pill or another edge's line.
function mmdQuality(g, L){
  const nk = Object.keys(L.nodes), sk = Object.keys(L.sgs), segs = L.edges.map(e => e.pts.slice(1).map((p, i) => [e.pts[i], p]));
  const ov = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
  const lab = e => e.lr || (e.label && e.lw ? { x: e.lx - e.lw / 2, y: e.ly - e.lh / 2, w: e.lw, h: e.lh } : null);
  const title = k => L.sgs[k].tr || (g.sgs[k] && g.sgs[k].title ? (() => { const ls = g.sgs[k].title.split('\n'), w = Math.max(...ls.map(mmdTw));
    return { x: L.sgs[k].x + L.sgs[k].w / 2 - w / 2, y: L.sgs[k].y + 4, w, h: ls.length * 16 }; })() : null);
  let boxHits = 0, crossings = 0, labelOverlaps = 0;
  L.edges.forEach((e, i) => {
    const al = new Set(mmdAnc(g, e.from).concat(mmdAnc(g, e.to))), hit = R => segs[i].some(s => mmdSegRect(s[0], s[1], R, -1));
    nk.forEach(k => { if(hit(L.nodes[k])) boxHits++; });
    sk.forEach(k => { if(!al.has(k) && !(g.sgs[k] && g.sgs[k].pass) && hit(L.sgs[k])) boxHits++; });
  });
  const o = (p, q, r) => Math.sign((q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]));
  for(let i = 0; i < segs.length; i++) for(let j = i + 1; j < segs.length; j++)
    segs[i].forEach(a => segs[j].forEach(b => { if(o(a[0], a[1], b[0]) * o(a[0], a[1], b[1]) < 0 && o(b[0], b[1], a[0]) * o(b[0], b[1], a[1]) < 0) crossings++; }));
  const ls = L.edges.map(lab), ts = sk.map(title).filter(Boolean);
  ls.forEach((R, i) => {
    if(!R) return;
    for(let j = i + 1; j < ls.length; j++) if(ls[j] && ov(R, ls[j])) labelOverlaps++;
    nk.forEach(k => { if(ov(R, L.nodes[k])) labelOverlaps++; });
    ts.forEach(t => { if(ov(R, t)) labelOverlaps++; });
    segs.forEach((ss, j) => { if(j !== i && ss.some(s => mmdSegRect(s[0], s[1], R, -1))) labelOverlaps++; });
  });
  return { boxHits, crossings, labelOverlaps, numbered: (L.notes || []).length };
}
