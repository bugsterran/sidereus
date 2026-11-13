// Pure: test/gate modules — off the map unless «Include tests» (they import everything and add only crossings).
function archIsTest(m){
  return !!m && (m.kind === 'test' || /^(gates?|tests?|checks?)$/i.test(String(m.id || '')) || /\btests?\b/i.test(String(m.name || '')));
}
// Pure: quoted mermaid label; 81e mmdLabel decodes the entities back, mmdSvg esc()s the result.
function archMq(s){
  return '"' + String(s == null ? '' : s).replace(/[\r\n]+/g, ' ').replace(/[&<>"|]/g, c => '&#' + c.charCodeAt(0) + ';') + '"';
}
// Pure: passed edges collapsed to one per ordered module pair; self-edges and hidden (test) modules dropped.
function archPairs(mods, edges, tests){
  const keep = {}, at = {}, out = [], KR = { event: 0, call: 1, read: 2, write: 3 };
  (mods || []).forEach(m => { if(m && m.id != null && (tests || !archIsTest(m))) keep[m.id] = 1; });
  (edges || []).forEach(e => {
    if(!e || !e.ok || e.from === e.to || !keep[e.from] || !keep[e.to]) return;
    const k = e.from + '\u0001' + e.to;
    let p = at[k];
    if(!p) out.push(p = at[k] = { from: e.from, to: e.to, n: 0, est: true, label: '', kind: '' });
    p.n++;
    const kk = KR[e.kind] != null ? e.kind : 'call';   // import/config/di/serve draw as call; event only when every edge is one
    if(!p.kind || KR[kk] > KR[p.kind]) p.kind = kk;
    if(!e.est) p.est = false;   // one direct reference is enough to draw the pair solid
    if(!p.label && e.label) p.label = String(e.label);
  });
  return out;
}
// Pure: transitive reduction for the overview — a pair is dropped while its target stays reachable without it
// (est pairs tried first, then input order; cycles kept). ★Self-map overview crossings 109 -> 2 (mmdQuality).
// ⚠Overview hover then lights only drawn edges, not every neighbour (downstream follows them for 2 hops); the focus view keeps every direct edge.
function archReduce(ps){
  const L = ps || [], on = L.map(() => true);
  const reach = (s, t, skip) => {
    const seen = new Set([s]), q = [s];
    while(q.length){ const u = q.shift();
      for(let i = 0; i < L.length; i++){
        if(!on[i] || i === skip || L[i].from !== u) continue;
        if(L[i].to === t) return true;
        if(!seen.has(L[i].to)){ seen.add(L[i].to); q.push(L[i].to); }
      } }
    return false;
  };
  L.map((p, i) => i).sort((a, b) => (L[b].est ? 1 : 0) - (L[a].est ? 1 : 0) || a - b)
    .forEach(i => { if(reach(L[i].from, L[i].to, i)) on[i] = false; });
  return L.filter((p, i) => on[i]);
}
// Pure: mermaid source. sel = '' → overview (every visible module, pair edges labelled only by «×N» when merged;
// implied pairs dropped by archReduce unless full); sel = module id → that module + direct neighbours, edges labelled.
// Node id = 'm' + index in mods (click maps it back).
function archSrc(mods, edges, tests, sel, full){
  const ix = {}, nb = {}, ln = ['flowchart ' + (sel ? 'LR' : ARCH_DIR)];
  (mods || []).forEach((m, i) => { if(m && m.id != null) ix[m.id] = i; });
  let ps = archPairs(mods, edges, tests);
  if(sel){ ps = ps.filter(p => p.from === sel || p.to === sel); nb[sel] = 1; ps.forEach(p => { nb[p.from] = nb[p.to] = 1; }); }
  else if(!full) ps = archReduce(ps);
  const vis = (mods || []).filter(m => m && m.id != null && (sel ? nb[m.id] : tests || !archIsTest(m)));
  const nd = m => '  m' + ix[m.id] + (m.kind === 'external' ? '([' + archMq(m.name || m.id) + '])' : '[' + archMq(m.name || m.id) + ']');
  vis.filter(m => m.kind !== 'external').forEach(m => ln.push(nd(m)));
  const ex = vis.filter(m => m.kind === 'external');
  if(ex.length){ ln.push('  subgraph xg[' + archMq(T('External')) + ']'); ex.forEach(m => ln.push(nd(m))); ln.push('  end'); }
  ps.forEach(p => {
    const lab = sel ? (p.label + (p.n > 1 ? ' ×' + p.n : '')).trim() : (p.n > 1 ? '×' + p.n : '');
    ln.push('  m' + ix[p.from] + ' ' + (p.est ? '-.->' : '-->') + (lab ? '|' + archMq(lab) + '|' : '') + ' m' + ix[p.to]);
  });
  return ln.join('\n');
}
// Pure, O(V+E): fixed overview ranks (id -> rank). DFS back edges ignored, longest path from entries (rank 0),
// the External box 'xg' one below. ⚠Sinks are not pinned to the bottom (self-map crossings 2 -> 6).
function archRanks(ids, pairs){
  const own = Object.prototype.hasOwnProperty, at = {}, out = {}, inn = {}, rk = {}, L = (ids || []).filter(k => k !== 'xg');
  L.forEach(k => { at[k] = 1; out[k] = []; inn[k] = 0; rk[k] = 0; });
  let xe = false;
  (pairs || []).forEach(p => {
    if(p.from === 'xg' || p.to === 'xg'){ xe = true; return; }
    if(own.call(at, p.from) && own.call(at, p.to) && p.from !== p.to) out[p.from].push(p.to);
  });
  L.forEach(k => out[k].forEach(t => { inn[t]++; }));
  const st = {}, back = new Set(), deg = {};   // st: 1 = on stack, 2 = done
  L.filter(k => !inn[k]).concat(L.filter(k => inn[k])).forEach(r => {
    if(st[r]) return;
    const sk = [[r, 0]]; st[r] = 1;
    while(sk.length){
      const f = sk[sk.length - 1], u = f[0];
      if(f[1] >= out[u].length){ st[u] = 2; sk.pop(); continue; }
      const i = f[1]++, v = out[u][i];
      if(st[v] === 1) back.add(u + '\u0001' + i);
      else if(!st[v]){ st[v] = 1; sk.push([v, 0]); }
    }
  });
  const fw = u => out[u].filter((v, i) => !back.has(u + '\u0001' + i));
  L.forEach(k => { deg[k] = 0; }); L.forEach(k => fw(k).forEach(v => { deg[v]++; }));
  const q = L.filter(k => !deg[k]);
  let mx = 0;
  for(let h = 0; h < q.length; h++){ const u = q[h]; fw(u).forEach(v => { rk[v] = Math.max(rk[v], rk[u] + 1); mx = Math.max(mx, rk[v]); if(!--deg[v]) q.push(v); }); }
  if((ids || []).indexOf('xg') >= 0) rk.xg = xe ? mx + 1 : mx;   // ⚠every root id needs a rank or 81f drops rankFix
  return rk;
}
