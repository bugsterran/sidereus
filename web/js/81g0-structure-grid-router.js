// ── Orthogonal grid router (A* on an RR_C grid, nodes block, routes spread into lanes) — used by the mermaid layout (81g).
// ⚠Kept from the removed Relations view: 81g-structure-mermaid-route.js calls relGridOf/relRoute/relLanes/relOccMark/relOrthoD/relSimp.
// ⚠RR_HW 2 = weighted A* (slightly longer routes): 373 edges route in ~90ms vs ~700ms at 1 (live repo, 2026-09-26).
const RR_C = 8, RR_TURN = 3, RR_GRP = 12, RR_FACE = 4, RR_SIDEIN = 2, RR_BEND = 8, RR_POPS = 20000, RR_BUDGET = 250, RR_HW = 2, RR_OCC = 4, RR_SHARE = 0.4, RR_NEAR = 1;
// Straight stub from a port before the first turn (arrowheads stay visible): merged lines
// RR_STUB on top/bottom, node edges RR_NSTUB (11px arrow + 6px corner). ⚠An end with no free stub falls back to 0, never a curve.
const RR_STUB = 24, RR_NSTUB = 16, RR_RING = 20;
// Merged lines keep >= RR_HUG px off every group box but their own two.
const RR_HUG = 5;
// Region layouts: a merged line's step in a gutter cell (tier gap, gap between two regions of a row) costs RR_GUT instead of 1,
// so bundles take the middle of the gutters (the RR_NEAR ring still keeps them off the panel borders).
const RR_GUT = 0.6;
let relRRB = null;
function relGridOf(ox, oy, nx, ny){
  const z = () => new Uint8Array(nx * ny), occ = () => new Int32Array(nx * ny).fill(-1);
  return { ox: ox, oy: oy, nx: nx, ny: ny, blk: z(), gid: new Int16Array(nx * ny), hd: z(), nb: z(), nr: new Int16Array(nx * ny), gt: z(), rng: {},
    th: occ(), sh: occ(), tv: occ(), sv: occ(), cs: -1, ct: -1, ea: 0, eb: 0 };
}
// Free cells just outside each side (0 top · 1 right · 2 bottom · 3 left = the direction leaving it), >=10px from corners:
// all of them with `all` (search), else the one nearest the side's centre (relSmooth re-attaches there).
function relPorts(G, o, r, fn, all, pen){
  const cx = i => G.ox + i * RR_C + RR_C / 2, cy = j => G.oy + j * RR_C + RR_C / 2;
  [[0, r[2] - 1], [2, r[3] + 1], [1, r[1] + 1], [3, r[0] - 1]].forEach(([sd, at]) => {
    if(pen && !isFinite(pen[sd])) return;                     // side not allowed for this end
    const hz = !(sd % 2), lo = hz ? r[0] : r[2], hi = hz ? r[1] : r[3], c = [];
    for(let t = lo; t <= hi; t++){
      const i = hz ? t : at, j = hz ? at : t;
      const i2 = i + [0, 1, 0, -1][sd], j2 = j + [-1, 0, 1, 0][sd];   // ⚠the next cell out must be free too, or the port is a dead end
      if(i2 < 0 || j2 < 0 || i2 >= G.nx || j2 >= G.ny || G.blk[j * G.nx + i] || G.blk[j2 * G.nx + i2]) continue;
      const v = hz ? cx(i) : cy(j);
      if(hz ? v >= o.x + 10 && v <= o.x + o.w - 10 : v >= o.y + 10 && v <= o.y + o.h - 10) c.push([i, j]);   // >=10px from corners
    }
    const m = hz ? o.x + o.w / 2 : o.y + o.h / 2, pos = x => hz ? cx(x[0]) : cy(x[1]);
    if(all){ c.forEach(x => fn(x[0], x[1], sd)); return; }
    const best = c.sort((u, w) => Math.abs(pos(u) - m) - Math.abs(pos(w) - m))[0];
    if(best) fn(best[0], best[1], sd);
  });
}
function relStubPx(G, o, sd){ return o.box ? (sd % 2 ? 0 : RR_STUB) : G.stubOff ? 0 : RR_NSTUB; }
function relRoute(G, a, b, ra, rb, ga, gb, occ, hw, cap){
  const nx = G.nx, ny = G.ny, N = nx * ny * 4, blk = G.blk, gid = G.gid, hd = G.hd;
  if(!relRRB || relRRB.n < N) relRRB = { n: N, g: new Float32Array(N), par: new Int32Array(N), st: new Int32Array(N), tg: new Uint8Array(N), ts: new Uint8Array(N), stamp: 0 };
  const B = relRRB, cur = ++B.stamp, hp = [], hf = [], tcs = [], tps = [], sps = [];
  let pf = 0;
  const push = (s, f) => { let i = hp.length; hp.push(s); hf.push(f);
    while(i){ const p = (i - 1) >> 1; if(hf[p] <= f) break; hp[i] = hp[p]; hf[i] = hf[p]; i = p; } hp[i] = s; hf[i] = f; };
  const pop = () => { const s = hp[0], f = hf[0], ls = hp.pop(), lf = hf.pop(), n = hp.length;
    if(n){ let i = 0; for(;;){ let c = 2 * i + 1; if(c >= n) break; if(c + 1 < n && hf[c + 1] < hf[c]) c++; if(hf[c] >= lf) break; hp[i] = hp[c]; hf[i] = hf[c]; i = c; }
      hp[i] = ls; hf[i] = lf; }
    pf = f; return s; };
  const DX = [0, 1, 0, -1], DY = [-1, 0, 1, 0];
  // Per-side port costs (Infinity = not a port). Nodes: sides facing away from the target cost RR_FACE, side entries RR_SIDEIN.
  // Group boxes (merged lines): top or bottom — bottom unless the
  // other box is above/below it — and a side only when both boxes share a row and that side faces the other.
  const bx = b.x + b.w / 2, by = b.y + b.h / 2, ax = a.x + a.w / 2;
  const face = [by < a.y, bx > a.x + a.w, by > a.y + a.h, bx < a.x], anyf = face.some(Boolean);
  const below = a.y + a.h <= b.y, above = b.y + b.h <= a.y, row = !below && !above, F = RR_FACE, X = Infinity;
  // Side ports for boxes only when a straight horizontal run between the facing sides is clear (no box, no group on it).
  let str = false;
  const y0 = Math.max(a.y, b.y) + 10, y1 = Math.min(a.y + a.h, b.y + b.h) - 10;
  if(a.box && b.box && row && y1 >= y0){
    const jm = Math.round(((y0 + y1) / 2 - G.oy - RR_C / 2) / RR_C), xa = bx > ax ? a.x + a.w : a.x, xb = bx > ax ? b.x : b.x + b.w;
    const i0 = Math.round((Math.min(xa, xb) - G.ox - RR_C / 2) / RR_C) + 1, i1 = Math.round((Math.max(xa, xb) - G.ox - RR_C / 2) / RR_C) - 1;
    str = i1 >= i0;
    for(let i = i0; str && i <= i1; i++){ const c = jm * nx + i; if(blk[c] || gid[c]) str = false; }
    // ⚠A clear same-row pair is one straight run at the overlap midpoint: A* tied it with a bottom detour, and centring
    // then dragged that detour's corner into the target box (a line down its left edge through the header).
    if(str) return [{ x: xa, y: (y0 + y1) / 2 }, { x: xb, y: (y0 + y1) / 2 }];
  }
  const hug = c => (a.box || b.box) && G.nr[c] && G.nr[c] !== G.ea && G.nr[c] !== G.eb;
  const spen = a.box ? [above ? 0 : 2 * F, str && bx > ax ? F : X, above ? F : 0, str && bx < ax ? F : X]
    : G.spen || face.map(f => anyf && !f ? F : 0);   // G.spen: mermaid pass bands fix the exit side
  const tpen = b.box ? [below ? 0 : 2 * F, str && ax > bx ? F : X, below ? F : 0, str && ax < bx ? F : X] : G.tpen || [0, RR_SIDEIN, 0, RR_SIDEIN];   // G.tpen: mermaid LR prefers side entries
  relPorts(G, b, rb, (i, j, sd) => { tps.push([i, j, sd]); }, false, tpen);
  relPorts(G, a, ra, (i, j, sd) => { sps.push([i, j, sd]); }, false, spen);
  // ⚠Merged lines never take the top margin above the first row (it read as a detour over every box).
  const jTop = (a.box || b.box) ? Math.ceil((0 - G.oy - RR_C / 2) / RR_C) : 0;
  const nbw = (a.box || b.box) && !G.nbOff ? RR_NEAR : 0;   // ⚠merged lines only: node edges paying it doubled a large repo's all-open time and lost 2 routes
  // ⚠Merged lines: other groups are walls in every pass (hug forbids them anyway) — at a cost only, a 2000px-tall open region
  // soaked up the whole pop cap and the line fell back to a curve (live all-open, domain/agents -> util/config).
  const bl = a.box || b.box, gut = bl ? G.gt : null;
  // Port cell → straight out until a cell centre is >= px from the edge (cells port..far) · null = blocked on the way.
  const cxy = (i, j) => ({ x: G.ox + i * RR_C + RR_C / 2, y: G.oy + j * RR_C + RR_C / 2 });
  const stub = (o, i, j, sd, px) => {
    const cs = [j * nx + i];
    for(;;){
      const q = cxy(i, j), d = sd === 0 ? o.y - q.y : sd === 2 ? q.y - o.y - o.h : sd === 1 ? q.x - o.x - o.w : o.x - q.x;
      if(d >= px) return cs;
      i += DX[sd]; j += DY[sd];
      if(i < 0 || j < jTop || i >= nx || j >= ny) return null;
      const c = j * nx + i;
      if(blk[c] || (gid[c] && gid[c] !== ga && gid[c] !== gb) || hug(c) || (G.inG && gid[c] !== G.inG)) return null;
      cs.push(c);
    }
  };
  const ports = (o, r, pen) => {                                // every allowed port with its stub; px 0 when none fits
    for(const k of [1, 0]){
      const L = [];
      relPorts(G, o, r, (i, j, sd) => { const cs = stub(o, i, j, sd, k ? relStubPx(G, o, sd) : 0); if(cs) L.push([sd, cs]); }, true, pen);
      if(L.length || !k){ L.k = k; return L; }
    }
  };
  const tpre = {}, spre = {}, TL = ports(b, rb, tpen), SL = ports(a, ra, spen);
  if(!TL.length || !SL.length) return null;
  let E = 1;
  TL.forEach(([sd, cs]) => { const c = cs[cs.length - 1], i = c % nx, j = (c - i) / nx; B.tg[c] = sd + 1; tcs.push(c); tpre[c] = cs;
    cs.slice(0, -1).forEach(u => { B.ts[u] = sd + 1; tcs.push(u); });
    E = Math.max(E, Math.max(0, rb[0] - i, i - rb[1]) + Math.max(0, rb[2] - j, j - rb[3])); });
  const H = (i, j) => hw * (Math.max(0, rb[0] - E - i, i - rb[1] - E) + Math.max(0, rb[2] - E - j, j - rb[3] - E));
  SL.forEach(([sd, cs]) => {
    const c = cs[cs.length - 1], i = c % nx, j = (c - i) / nx, s = c * 4 + sd, w = spen[sd] + cs.length - 1;
    if(B.st[s] === cur && B.g[s] <= w) return;
    B.st[s] = cur; B.g[s] = w; B.par[s] = -1; spre[s] = cs; push(s, w + H(i, j));
  });
  let pops = 0, end = -1, eside = 0;
  const cs = G.cs, ct = G.ct;
  while(hp.length && ++pops <= cap){
    const s = pop(), f = pf;
    if(s < 0){ end = -s - 1; eside = B.tg[end >> 2] - 1; break; }   // goal entry with its side cost settled
    const c = s >> 2, d = s & 3, i = c % nx, j = (c - i) / nx, gs = B.g[s];
    if(f > gs + H(i, j) + 1e-6) continue;
    if(B.tg[c] && d !== B.tg[c] - 1){ const pn = tpen[B.tg[c] - 1]; if(!pn){ end = s; eside = B.tg[c] - 1; break; } push(-s - 1, gs + pn); continue; }   // ⚠not while heading away (came up the stub)
    for(let nd = 0; nd < 4; nd++){
      if(nd === (d ^ 2)) continue;
      const ni = i + DX[nd], nj = j + DY[nd];
      if(ni < 0 || nj < 0 || ni >= nx || nj >= ny) continue;
      const nc = nj * nx + ni;
      if(blk[nc] || nj < jTop || ((occ || bl) && gid[nc] && gid[nc] !== ga && gid[nc] !== gb) || hug(nc)) continue;   // lane pass: foreign groups are walls (far fewer states)
      if(G.inG && gid[nc] !== G.inG) continue;                  // region inner edge: never leaves its region box
      if(B.ts[nc] === nd + 1) continue;                         // ⚠no running out along a target stub (it is entered from its far end)
      let q = gid[nc], w = gs + (gut && gut[nc] ? RR_GUT : 1) + (nd !== d ? RR_TURN : 0) + ((q && q !== ga && q !== gb) || hd[nc] ? RR_GRP : 0) + (G.nb[nc] ? nbw : 0)
        + (occ ? relOccCost(G, nc, nd & 1, cs, ct) : 0), ns = nc * 4 + nd;
      w = Math.fround(w);   // ⚠B.g is Float32: unrounded fractional costs (RR_GUT, RR_SHARE) dropped live states and re-pushed equal ones (pop cap)
      if(B.st[ns] === cur && B.g[ns] <= w) continue;
      B.st[ns] = cur; B.g[ns] = w; B.par[ns] = s; push(ns, w + H(ni, nj));
    }
  }
  tcs.forEach(c => { B.tg[c] = 0; B.ts[c] = 0; });
  if(end < 0) return null;
  const cells = [];
  for(let s = end; s >= 0; s = B.par[s]) cells.push(s);
  cells.reverse();
  const cp = c => { const i = c % nx; return cxy(i, (c - i) / nx); }, sp = spre[cells[0]], tp = tpre[end >> 2];
  const p = sp.slice(0, -1).map(cp).concat(cells.map(s => cp(s >> 2)), tp.slice(0, -1).reverse().map(cp)), f0 = p[0], fz = p[p.length - 1], sd0 = cells[0] & 3;
  p.unshift(sd0 === 0 ? { x: f0.x, y: a.y } : sd0 === 2 ? { x: f0.x, y: a.y + a.h } : sd0 === 3 ? { x: a.x, y: f0.y } : { x: a.x + a.w, y: f0.y });
  p.push(eside === 0 ? { x: fz.x, y: b.y } : eside === 2 ? { x: fz.x, y: b.y + b.h } : eside === 3 ? { x: b.x, y: fz.y } : { x: b.x + b.w, y: fz.y });
  return relSmooth(G, relSimp(p), a, b, sps, tps, ga, gb, spen, tpen, jTop, [SL.k, TL.k]);
}
// Drop repeated and straight-through points (a point where the run reverses is kept).
function relSimp(p){
  const q = [];
  p.forEach(v => { if(!q.length || q[q.length - 1].x !== v.x || q[q.length - 1].y !== v.y) q.push(v); });
  return q.filter((v, k) => k === 0 || k === q.length - 1 || !(
    (v.x === q[k - 1].x && v.x === q[k + 1].x && (v.y - q[k - 1].y) * (q[k + 1].y - v.y) > 0)
    || (v.y === q[k - 1].y && v.y === q[k + 1].y && (v.x - q[k - 1].x) * (q[k + 1].x - v.x) > 0)));
}
// Weighted A* (RR_HW) finds a good route, not the best one. Greedy rewrites fix that cheaply: re-attach the tail to
// another side of the target, the head to another side of the source, or short-cut i→j with one corner — kept only
// when every new cell is free (no box, no header, no foreign group) and the score (length + RR_BEND per bend) drops.
// Exit the right-side centre and come up into the bottom centre rather than bottom-corner → left side.
function relSmooth(G, p, a, b, sps, tps, ga, gb, spen, tpen, jTop, kst){
  const C = RR_C, ci = x => Math.round((x - G.ox - C / 2) / C), cj = y => Math.round((y - G.oy - C / 2) / C);
  const ctr = (i, j) => ({ x: G.ox + i * C + C / 2, y: G.oy + j * C + C / 2 });
  const ok = (s, t) => {
    let i = ci(s.x), j = cj(s.y);
    const i1 = ci(t.x), j1 = cj(t.y);
    if(i !== i1 && j !== j1) return false;
    const di = Math.sign(i1 - i), dj = Math.sign(j1 - j);
    for(;;){
      if(i < 0 || j < jTop || i >= G.nx || j >= G.ny) return false;
      const c = j * G.nx + i, q = G.gid[c], r = G.nr[c];
      if(G.blk[c] || G.hd[c] || (q && q !== ga && q !== gb) || (G.inG && q !== G.inG) || (r && (a.box || b.box) && r !== G.ea && r !== G.eb) ||((di || dj) && relOccCost(G, c, di ? 1 : 0, G.cs, G.ct) > 0)) return false;
      if(i === i1 && j === j1) return true;
      i += di; j += dj;
    }
  };
  const near = (s, t) => {                                      // hugging cells on an axis-aligned run
    let i = ci(s.x), j = cj(s.y), n = 0;
    const i1 = ci(t.x), j1 = cj(t.y), di = Math.sign(i1 - i), dj = Math.sign(j1 - j);
    if(di && dj) return 0;
    for(;;){ if(i >= 0 && j >= 0 && i < G.nx && j < G.ny && G.nb[j * G.nx + i]) n++; if(i === i1 && j === j1) return n; i += di; j += dj; }
  };
  const bd = (o, sd, P) => sd === 0 ? { x: P.x, y: o.y } : sd === 2 ? { x: P.x, y: o.y + o.h } : sd === 3 ? { x: o.x, y: P.y } : { x: o.x + o.w, y: P.y };
  const side = (o, q) => Math.abs(q.y - o.y) < 0.5 ? 0 : Math.abs(q.y - o.y - o.h) < 0.5 ? 2 : Math.abs(q.x - o.x) < 0.5 ? 3 : 1;
  const score = q => {
    let L = 0, n = 0;
    for(let k = 0; k < q.length - 1; k++) L += Math.abs(q[k + 1].x - q[k].x) + Math.abs(q[k + 1].y - q[k].y) + (a.box || b.box ? RR_NEAR * C * near(q[k], q[k + 1]) : 0);
    for(let k = 1; k < q.length - 1; k++){
      const hz1 = q[k].y === q[k - 1].y, hz2 = q[k + 1].y === q[k].y;
      n += hz1 !== hz2 ? 1 : 2;                                 // a reversal counts as two bends
    }
    return L / C + RR_BEND * n + tpen[side(b, q[q.length - 1])] + spen[side(a, q[0])];
  };
  let best = p, bs = score(p);
  const L1 = (u, v) => Math.abs(u.x - v.x) + Math.abs(u.y - v.y), z = p.length - 1;
  const need = [kst[0] && p.length > 2 ? Math.min(L1(p[0], p[1]), relStubPx(G, a, side(a, p[0]))) : 0, kst[1] && p.length > 2 ? Math.min(L1(p[z], p[z - 1]), relStubPx(G, b, side(b, p[z]))) : 0];
  const stubOk = q => q.length < 3 || (L1(q[0], q[1]) >= Math.min(need[0], relStubPx(G, a, side(a, q[0]))) - 0.5
    && L1(q[q.length - 1], q[q.length - 2]) >= Math.min(need[1], relStubPx(G, b, side(b, q[q.length - 1]))) - 0.5);
  const tryq = q => { q = relSimp(q); if(!stubOk(q)) return; const v = score(q); if(v < bs - 0.01){ best = q; bs = v; } };   // ⚠rewrites keep the port stubs
  for(let round = 0; round < 3; round++){
    const was = bs, cur = best, n = cur.length;
    tps.forEach(([i, j, sd]) => {                                // tail → target side sd, arriving inward
      const P = ctr(i, j), B = bd(b, sd, P);
      for(let k = 1; k < n - 1; k++){
        const q = cur[k], c = sd % 2 ? { x: q.x, y: P.y } : { x: P.x, y: q.y };
        if(sd === 0 ? c.y > P.y : sd === 2 ? c.y < P.y : sd === 3 ? c.x > P.x : c.x < P.x) continue;
        if(ok(q, c) && ok(c, P)) tryq(cur.slice(0, k + 1).concat([c, P, B]));
      }
    });
    sps.forEach(([i, j, sd]) => {                                // head ← source side sd, leaving outward
      const P = ctr(i, j), B = bd(a, sd, P);
      for(let k = 1; k < n - 1; k++){
        const q = cur[k], c = sd % 2 ? { x: q.x, y: P.y } : { x: P.x, y: q.y };
        if(sd === 0 ? c.y > P.y : sd === 2 ? c.y < P.y : sd === 3 ? c.x > P.x : c.x < P.x) continue;
        if(ok(P, c) && ok(c, q)) tryq([B, P, c].concat(cur.slice(k)));
      }
    });
    for(let i = 1; i < n - 2; i++) for(let j = i + 2; j < Math.min(n - 1, i + 9); j++){   // one-corner short cuts
      const u = cur[i], v = cur[j];
      [{ x: u.x, y: v.y }, { x: v.x, y: u.y }].forEach(c => { if(ok(u, c) && ok(c, v)) tryq(cur.slice(0, i + 1).concat([c], cur.slice(j))); });
    }
    if(bs >= was) break;
  }
  return best;
}
// Cells a finished route runs through, per axis, tagged with its bundle ids (source×kind, target×kind). Unrelated routes pay
// RR_OCC to run along them (crossing is free) so they take their own lane (same-colour overlaps are indistinguishable);
// routes sharing the source or the target (same kind) pay less there, so they merge into one trunk on purpose.
function relOccCost(G, c, hz, cs, ct){
  const t = (hz ? G.th : G.tv)[c];
  if(t === -1) return 0;
  return t === ct || (hz ? G.sh : G.sv)[c] === cs ? -RR_SHARE : RR_OCC;
}
function relOccMark(G, p){
  const ci = x => Math.round((x - G.ox - RR_C / 2) / RR_C), cj = y => Math.round((y - G.oy - RR_C / 2) / RR_C);
  for(let k = 0; k < p.length - 1; k++){
    let i = ci(p[k].x), j = cj(p[k].y);
    const i1 = ci(p[k + 1].x), j1 = cj(p[k + 1].y), di = Math.sign(i1 - i), dj = Math.sign(j1 - j), T = di ? G.th : G.tv, S = di ? G.sh : G.sv;
    if(di && dj) continue;
    for(;;){
      if(i >= 0 && j >= 0 && i < G.nx && j < G.ny){
        const c = j * G.nx + i;
        if(T[c] === -1){ T[c] = G.ct; S[c] = G.cs; } else { if(T[c] !== G.ct) T[c] = -2; if(S[c] !== G.cs) S[c] = -2; }
      }
      if(i === i1 && j === j1) break;
      i += di; j += dj;
    }
  }
}
// Endpoint box: a node, a collapsed-group head, or (merged group lines) the whole group box.
// Runs closer than 5px to another edge's parallel run move to the first free offset of ±6/±12/±18 px.
// ⚠A shift is kept only if it clears every box and every other run; port segments never move (they would leave the box).
function relLanes(pts, ends, clear, gsOf, need){
  ['y', 'x'].forEach(ax => {
    const o = ax === 'y' ? 'x' : 'y', segs = [], bk = new Map(), key = c => Math.floor(c / 5);
    const add = g => { const kk = key(g.c); if(!bk.has(kk)) bk.set(kk, []); bk.get(kk).push(g); };
    const del = g => { const L = bk.get(key(g.c)); L.splice(L.indexOf(g), 1); };
    Object.keys(pts).forEach(k => {
      const p = pts[k];
      for(let i = 0; i < p.length - 1; i++){
        const a = p[i], b = p[i + 1];
        if(Math.abs(a[ax] - b[ax]) > 0.5 || Math.abs(a[o] - b[o]) < 0.5) continue;
        const g = { p: p, i: i, k: k, c: a[ax], lo: Math.min(a[o], b[o]), hi: Math.max(a[o], b[o]), port: i === 0 || i === p.length - 2 };
        segs.push(g); add(g);
      }
    });
    // Same kind + shared source or target = one bundle: its runs may coincide (a trunk), others may not.
    const mate = (u, v) => ends[u][2] === ends[v][2] && (ends[u][0] === ends[v][0] || ends[u][1] === ends[v][1]);
    const hits = (g, c) => {
      for(let d = -1; d <= 1; d++){
        const L = bk.get(key(c) + d);
        if(L) for(const h of L) if(h !== g && h.k !== g.k && !mate(h.k, g.k) && Math.abs(h.c - c) < 5 && Math.min(h.hi, g.hi) - Math.max(h.lo, g.lo) > 1) return true;
      }
      return false;
    };
    segs.forEach(g => {
      if(g.port || !hits(g, g.c)) return;
      const p = g.p, i = g.i, sk = new Set(ends[g.k]), gs = gsOf(g.k), n = p.length, L1 = (u, v) => Math.abs(u.x - v.x) + Math.abs(u.y - v.y);
      // ⚠A shift next to a port must not shorten its stub below the RR_STUB/RR_NSTUB it was routed with.
      const s0 = i === 1 ? Math.min(L1(p[0], p[1]), need(g.k, 0)) : 0, s1 = i + 2 === n - 1 ? Math.min(L1(p[n - 1], p[n - 2]), need(g.k, 1)) : 0;
      for(const off of [6, -6, 12, -12, 18, -18]){
        if(hits(g, g.c + off)) continue;
        p[i][ax] += off; p[i + 1][ax] += off;
        if(clear(p[i], p[i + 1], sk, gs) && (i < 1 || clear(p[i - 1], p[i], sk, gs)) && (i + 2 >= p.length || clear(p[i + 1], p[i + 2], sk, gs))
          && L1(p[0], p[1]) >= s0 - 0.5 && L1(p[n - 1], p[n - 2]) >= s1 - 0.5){
          del(g); g.c += off; add(g); return;
        }
        p[i][ax] -= off; p[i + 1][ax] -= off;
      }
    });
  });
}
// Short jogs: segment k (p[k]→p[k+1]) shorter than RR_SJOG between two runs heading the same way (a Z). relOrthoD draws each as
// one S-curve with tangents along the runs.
const RR_SJOG = 24;
function relSJogs(p){
  const J = [], L = (u, v) => Math.abs(u.x - v.x) + Math.abs(u.y - v.y);
  for(let k = 1; k < p.length - 2; k++){
    const a = p[k - 1], b = p[k], c = p[k + 1], d = p[k + 2], m = L(b, c);
    if(m < 0.5 || m >= RR_SJOG || (J.length && J[J.length - 1] >= k - 1)) continue;
    const vt = Math.abs(a.x - b.x) < 0.5 && Math.abs(c.x - d.x) < 0.5 && Math.abs(b.y - c.y) < 0.5, hz = Math.abs(a.y - b.y) < 0.5 && Math.abs(c.y - d.y) < 0.5 && Math.abs(b.x - c.x) < 0.5;
    if(vt ? Math.sign(b.y - a.y) && Math.sign(b.y - a.y) === Math.sign(d.y - c.y) : hz && Math.sign(b.x - a.x) && Math.sign(b.x - a.x) === Math.sign(d.x - c.x)) J.push(k);
  }
  return J;
}
// Orthogonal route → path: bends rounded (radius 6, clamped to half of either run), short jogs as one S-curve.
// ⚠End runs keep their direction at the ends so arrowheads (orient=auto) line up.
// ⚠`hit(x0, y0, x1, y1)` (optional) = a box other than the ends overlaps that rect. The S-curve leaves the routed corridor
//   (it spans half of each run), so it cut through cards the orthogonal route went around (★66 cards crossed in the live
//   all-open view, 0 with plain bends) ⇒ a blocked jog keeps its two rounded bends.
function relOrthoD(p, hit){
  const f = v => v.toFixed(1), n = p.length, L = (u, v) => Math.abs(u.x - v.x) + Math.abs(u.y - v.y), J = new Set(relSJogs(p));
  const mv = (u, v, d) => { const l = L(u, v) || 1; return { x: u.x + (v.x - u.x) * d / l, y: u.y + (v.y - u.y) * d / l }; };
  let d = 'M' + f(p[0].x) + ' ' + f(p[0].y), at = p[0];
  const line = q => { if(L(at, q) > 0.05){ d += ' L' + f(q.x) + ' ' + f(q.y); at = q; } };
  for(let i = 1; i < n - 1; i++){
    const a = p[i - 1], c = p[i], nx = p[i + 1];
    const e = p[i + 2], A = J.has(i) && mv(c, a, i - 1 ? L(a, c) / 2 : L(a, c)), B = A && mv(nx, e, i + 2 < n - 1 ? L(nx, e) / 2 : L(nx, e));
    if(A && !(hit && hit(Math.min(A.x, B.x), Math.min(A.y, B.y), Math.max(A.x, B.x), Math.max(A.y, B.y)))){   // S-curve over the jog, eating half of each run (all of an end run)
      const vt = Math.abs(a.x - c.x) < 0.5, h = vt ? (A.y + B.y) / 2 : (A.x + B.x) / 2;
      line(A);
      d += ' C' + (vt ? f(A.x) + ' ' + f(h) + ' ' + f(B.x) + ' ' + f(h) : f(h) + ' ' + f(A.y) + ' ' + f(h) + ' ' + f(B.y)) + ' ' + f(B.x) + ' ' + f(B.y);
      at = B; i++; continue;
    }
    const r = Math.min(6, L(a, c) / 2, L(c, nx) / 2);
    const ux = Math.sign(c.x - a.x), uy = Math.sign(c.y - a.y), vx = Math.sign(nx.x - c.x), vy = Math.sign(nx.y - c.y);
    line({ x: c.x - ux * r, y: c.y - uy * r });
    d += ' Q' + f(c.x) + ' ' + f(c.y) + ' ' + f(c.x + vx * r) + ' ' + f(c.y + vy * r); at = { x: c.x + vx * r, y: c.y + vy * r };
  }
  line(p[n - 1]);
  return d;
}
