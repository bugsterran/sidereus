// ── Markdown preview: ```mermaid flowcharts drawn by our own small renderer (the app is offline — no mermaid.js) ──────
// md(src, 1) (00-core) hands mermaid fences to mmdBlock. Flowcharts are drawn here, sequenceDiagram in 81h; anything else keeps the code block.
// ⚠Labels are reduced to plain text (<br> → line break, other tags dropped) and esc()'d on output — never label HTML.
// ⚠A parse/layout error must never break the rest of the markdown: mmdBlock catches and falls back to the code block.

// Label → plain text with '\n' line breaks.
function mmdLabel(raw){
  let s = String(raw == null ? '' : raw).trim();
  if(s.length > 1 && s[0] === '"' && s[s.length - 1] === '"') s = s.slice(1, -1);
  if(s.length > 1 && s[0] === '`' && s[s.length - 1] === '`') s = s.slice(1, -1);
  s = s.replace(/<br\s*\/?>/gi, '\n').replace(/<\/?[A-Za-z][^>]*>/g, '').replace(/#quot;/g, '"')
    .replace(/&(nbsp|amp|lt|gt|quot|apos|#\d{1,7}|#x[0-9a-f]{1,6});/gi, (m, e) => {
      const k = e.toLowerCase(), E = { nbsp: ' ', amp: '&', lt: '<', gt: '>', quot: '"', apos: "'" };
      if(E[k] != null) return E[k];
      const n = k[1] === 'x' ? parseInt(k.slice(2), 16) : parseInt(k.slice(1), 10);
      return n > 31 && n <= 0x10FFFF ? String.fromCodePoint(n) : '';
    });
  const ls = s.split('\n').map(x => x.replace(/\s+/g, ' ').trim());
  while(ls.length > 1 && !ls[ls.length - 1]) ls.pop();
  while(ls.length > 1 && !ls[0]) ls.shift();
  return ls.join('\n');
}
// Source → statements (lines, then ';' outside quotes and brackets). Drops %% comments and a --- front-matter block.
function mmdSplit(src){
  const out = [], lines = String(src == null ? '' : src).split(/\r?\n/);
  let k = 0;
  while(k < lines.length && !lines[k].trim()) k++;
  if(k < lines.length && lines[k].trim() === '---'){ k++; while(k < lines.length && lines[k].trim() !== '---') k++; k++; }
  for(; k < lines.length; k++){
    const t = lines[k].trim();
    if(!t || t.slice(0, 2) === '%%') continue;
    let cur = '', q = false, d = 0;
    for(const c of t){
      if(c === '"') q = !q;
      else if(!q && '[({'.includes(c)) d++;
      else if(!q && '])}'.includes(c) && d > 0) d--;
      if(c === ';' && !q && !d){ if(cur.trim()) out.push(cur.trim()); cur = ''; continue; }
      cur += c;
    }
    if(cur.trim()) out.push(cur.trim());
  }
  return out;
}
// One statement `A[x] & B --> |l| C -- "m" --> D`: registers nodes via node(id, label|null, shape), pushes edges.
function mmdChain(s, node, edges){
  const SH = [['(((', ')))', 'dcircle'], ['((', '))', 'circle'], ['([', '])', 'stadium'], ['[(', ')]', 'cyl'], ['[[', ']]', 'sub'],
    ['[/', '/]', 'lean_r'], ['[\\', '\\]', 'lean_l'], ['[/', '\\]', 'trap'], ['[\\', '/]', 'trapalt'], ['{{', '}}', 'hex'],
    ['{', '}', 'diamond'], ['>', ']', 'flag'], ['(', ')', 'round'], ['[', ']', 'rect']];
  const n = s.length;
  let i = 0;
  const ws = () => { while(i < n && /\s/.test(s[i])) i++; };
  const one = () => {
    ws();
    const m = /^[A-Za-z0-9_À-￿]+(?:-[A-Za-z0-9_À-￿]+)*/.exec(s.slice(i));
    if(!m) throw new Error('mermaid: node expected at ' + i);
    const id = m[0];
    let lab = null, shape = 'rect';
    i += id.length;
    for(const sh of SH){
      if(!s.startsWith(sh[0], i)) continue;
      let j = i + sh[0].length, k, t;
      while(j < n && s[j] === ' ') j++;
      if(s[j] === '"'){
        const q = s.indexOf('"', j + 1);
        if(q < 0) continue;
        let e = q + 1;
        while(e < n && s[e] === ' ') e++;
        if(!s.startsWith(sh[1], e)) continue;
        t = s.slice(j, q + 1); k = e;
      }else{
        k = s.indexOf(sh[1], i + sh[0].length);
        if(k < 0) continue;
        t = s.slice(i + sh[0].length, k);
      }
      lab = t; shape = sh[2]; i = k + sh[1].length;
      break;
    }
    if(s.startsWith(':::', i)){ i += 3; const c = /^[\w-]+/.exec(s.slice(i)); i += c ? c[0].length : 0; }
    return node(id, lab, shape);
  };
  const group = () => { const ids = [one()]; ws(); while(s[i] === '&'){ i++; ids.push(one()); ws(); } return ids; };
  const edge = () => {
    const r = s.slice(i);
    let m = /^\s*(<?)(-{2,}>|-{3,}|-\.+->|-\.+-|={2,}>|={3,}|-{2,}[xo](?![A-Za-z0-9_])|={2,}[xo](?![A-Za-z0-9_])|~{3,})/.exec(r);
    let lab = '', tok;
    if(m){
      tok = m[2]; i += m[0].length;
      const p = /^\s*\|([^|]*)\|/.exec(s.slice(i));
      if(p){ lab = p[1]; i += p[0].length; }
    }else{
      m = /^\s*(<?)(--|==|-\.)\s*(?:"([^"]*)"|([^"\n]*?))\s*(-{2,}>|-{3,}|\.-+>|\.-+|={2,}>|={3,}|-{2,}[xo]|={2,}[xo])/.exec(r);
      if(!m) return null;
      tok = m[2] + m[5]; lab = m[3] != null ? m[3] : m[4]; i += m[0].length;
    }
    return { lab: String(lab || '').trim(), style: /~/.test(tok) ? 'invis' : /\./.test(tok) ? 'dot' : /=/.test(tok) ? 'thick' : 'solid',
      head: /[>xo]$/.test(tok), both: m[1] === '<' };
  };
  let prev = group();
  for(;;){
    ws();
    if(i >= n) break;
    const e = edge();
    if(!e) throw new Error('mermaid: edge expected at ' + i);
    const nx = group(), label = e.lab ? mmdLabel(e.lab) : '';
    prev.forEach(a => nx.forEach(b => edges.push({ from: a, to: b, label, style: e.style, head: e.head, both: e.both })));
    prev = nx;
  }
}
// Mermaid source → { ok, dir, nodes, nlist, edges, sgs, slist } or { ok: false, type } for other diagram types. Throws on bad flowcharts.
function mmdParse(src){
  const st = mmdSplit(src);
  const hd = (st[0] || '').match(/^(flowchart|graph)(?:\s+(TB|TD|BT|LR|RL))?$/i);
  if(!hd) return { ok: false, type: (st[0] || '').split(/\s+/)[0] };
  const dirOf = d => { const x = String(d || 'TB').toUpperCase(); return x === 'TD' ? 'TB' : x; };
  const g = { ok: true, dir: dirOf(hd[2]), nodes: {}, nlist: [], edges: [], sgs: {}, slist: [] }, stack = [''];
  let seq = 0, auto = 0;
  const cur = () => stack[stack.length - 1];
  const node = (id, lab, shape) => {
    let x = g.nodes[id];
    if(!x){ x = g.nodes[id] = { id, label: id, shape: 'rect', sg: '', seq: seq++ }; g.nlist.push(id); }
    if(!x.sg && cur()) x.sg = cur();            // the first mention inside a subgraph decides membership
    if(lab != null){ x.label = mmdLabel(lab); x.shape = shape; }
    return id;
  };
  for(let k = 1; k < st.length; k++){
    const s = st[k];
    let m;
    if(/^(classDef|class|style|linkStyle|click|accTitle|accDescr)\b/.test(s)) continue;
    if((m = s.match(/^direction\s+(TB|TD|BT|LR|RL)$/i))){ if(cur()) g.sgs[cur()].dir = dirOf(m[1]); else g.dir = dirOf(m[1]); continue; }
    if((m = s.match(/^subgraph(?:\s+([\s\S]*))?$/))){
      const r = (m[1] || '').trim();
      let id, title, mm;
      if((mm = r.match(/^([^\s\[\]"]+)\s*\[\s*([\s\S]*?)\s*\]$/))){ id = mm[1]; title = mm[2]; }
      else if(/^[^\s\[\]"]+$/.test(r)){ id = title = r; }
      else { id = '#sg' + (auto++); title = r; }
      if(g.sgs[id]) throw new Error('mermaid: duplicate subgraph ' + id);
      g.sgs[id] = { id, title: mmdLabel(title), dir: '', parent: cur(), seq: seq++ };
      g.slist.push(id); stack.push(id);
      continue;
    }
    if(s === 'end'){ if(stack.length < 2) throw new Error('mermaid: end without subgraph'); stack.pop(); continue; }
    mmdChain(s, node, g.edges);
  }
  if(stack.length > 1) throw new Error('mermaid: unclosed subgraph');
  // A subgraph id used as an edge end means the box, not a node.
  g.slist.forEach(id => { if(g.nodes[id]){ delete g.nodes[id]; g.nlist = g.nlist.filter(x => x !== id); } });
  if(g.nlist.length > 400 || g.edges.length > 800) throw new Error('mermaid: too large');
  if(!g.nlist.length && !g.slist.length) return { ok: false, type: 'empty' };
  return g;
}
// Rough text width at the rendered 13px (00-core fsz bumps the CSS 12px). Deterministic, so layout tests need no DOM.
function mmdTw(s){
  let w = 0;
  for(const c of String(s)){
    const k = c.codePointAt(0);
    w += k >= 0x1100 ? 13 : k >= 128 ? 8 : /[MW@%]/.test(c) ? 10.5 : /[A-Z&#]/.test(c) ? 8.4 : /[ il.,:;'|!()\[\]{}\/]/.test(c) ? 4 : 7.2;
  }
  return w;
}
function mmdBox(label, shape){
  const ls = String(label).split('\n'), tw = Math.max(8, ...ls.map(mmdTw)), th = ls.length * 16;
  let w = tw + 24, h = th + 14;
  if(shape === 'diamond'){ w = tw * 1.5 + 28; h = th * 1.8 + 24; }
  else if(shape === 'circle' || shape === 'dcircle') w = h = Math.max(tw, th) + 28 + (shape === 'dcircle' ? 8 : 0);
  else if(shape === 'hex') w += 28;
  else if(shape === 'stadium') w += h / 2;
  else if(shape === 'cyl') h += 14;
  else if(shape === 'sub') w += 16;
  else if(shape === 'comp') w += 18;   // component icon on the left edge (84i tag mode only)
  else if(/^(lean|trap|flag)/.test(shape)) w += 22;
  return { w: Math.round(Math.max(w, 44)), h: Math.round(h) };
}
// Parsed graph → absolute rects for nodes and subgraph boxes, routed edges, total size. Subgraphs are laid out inside-out as blocks.
function mmdLayout(g){
  const PAD = 16, RP = 8, PORTGAP = 16;
  const parentOf = id => g.sgs[id] ? g.sgs[id].parent : (g.nodes[id] ? g.nodes[id].sg : null);
  const dirOf = sid => { for(let s = sid; s; s = g.sgs[s].parent) if(g.sgs[s].dir) return g.sgs[s].dir; return g.dir; };
  const depth = sid => { let d = 0; for(let s = sid; s; s = g.sgs[s].parent) d++; return d; };
  // The child of block `sid` that contains `id` (null when id is outside sid).
  const lift = (id, sid) => {
    if(!g.nodes[id] && !g.sgs[id]) return null;
    let key = id, p = parentOf(id);
    while(p !== sid){ if(!p) return null; key = p; p = g.sgs[p].parent; }
    return key;
  };
  const box = {}, blk = {}, kids = {}, rel = {};
  const deg = {};
  g.edges.forEach(e => { if(e.from !== e.to){ deg[e.from] = (deg[e.from] || 0) + 1; deg[e.to] = (deg[e.to] || 0) + 1; } });
  g.nlist.forEach(id => {
    const b = box[id] = mmdBox(g.nodes[id].label, g.nodes[id].shape), n = Math.ceil((deg[id] || 0) / 2);
    // A hub grows along its layer so each line gets its own port (a 30px side can't hold twelve arrowheads).
    if(n > 2 && !/circle|diamond/.test(g.nodes[id].shape)){ if(/^(TB|BT)$/.test(dirOf(g.nodes[id].sg))) b.w = Math.max(b.w, Math.min(360, 24 + 18 * n)); else b.h = Math.max(b.h, Math.min(200, 12 + 12 * n)); }
  });
  const size = id => g.sgs[id] ? blk[id] : box[id];
  // ⚠84i component look only (box3d class boxes, comp methods): place with a margin so arrows and call numbers get room; md never has these
  const gapOf = id => g.sgs[id] ? (g.sgs[id].box3d ? 28 : 0) : g.nodes[id] && g.nodes[id].shape === 'comp' ? 18 : 0;
  const psize = id => { const z = size(id), m = gapOf(id); return m ? { w: z.w + m, h: z.h + m } : z; };
  g.nlist.map(id => [id, g.nodes[id].sg, g.nodes[id].seq]).concat(g.slist.map(id => [id, g.sgs[id].parent, g.sgs[id].seq]))
    .sort((a, b) => a[2] - b[2]).forEach(x => { (kids[x[1]] = kids[x[1]] || []).push(x[0]); });
  const lsz = t => { const ls = String(t).split('\n'); return { lw: Math.max(...ls.map(mmdTw)) + 10, lh: ls.length * 16 + 4 }; };
  // Two passes: the second orders each block's layers by where its outside neighbours ended up in the first (hint),
  // so e.g. a stack of three files faces the boxes it talks to instead of keeping source order.
  const run = hint => {
  const nodes = {}, sgs = {};
  g.slist.slice().sort((a, b) => depth(b) - depth(a)).concat(['']).forEach(sid => {
    const items = kids[sid] || [], seen = {}, es = [];
    g.edges.forEach(e => {
      const a = lift(e.from, sid), b = lift(e.to, sid);
      if(a == null || b == null || a === b) return;
      const k = a + '\u0001' + b, z = e.label ? lsz(e.label) : { lw: 0, lh: 0 };
      if(seen[k]){ seen[k].lw = Math.max(seen[k].lw, z.lw); seen[k].lh = Math.max(seen[k].lh, z.lh); seen[k].w++; return; }
      es.push(seen[k] = { a, b, lw: z.lw, lh: z.lh, w: 1 });                // w = real edges merged: cycle breaking keeps the heavier way
    });
    const pl = mmdPlace(items, es, psize, dirOf(sid), hint, sid ? null : g.rankFix, sid ? null : g.fit, v => g.sgs[v] && g.sgs[v].oneLayer, g.front ? v => !!g.front[v] : null);   // fixed ranks and fit size (84j focus): root block only · oneLayer (84j2 rows), front (84j2 served modules): opt-in
    items.forEach(v => { const m = gapOf(v); if(m){ pl.pos[v].x += m / 2; pl.pos[v].y += m / 2; } });
    if(sid){
      // ⚠A group inside a pass band (84j2) gets PORTGAP more under its title: 8px left no free port row above a first-row box,
      // so 81g band ports (top-in) found no route and the line fell back to a side entry.
      const pb = g.sgs[sid].parent && g.sgs[g.sgs[sid].parent] && g.sgs[g.sgs[sid].parent].pass && !g.sgs[sid].pass;
      const tl = g.sgs[sid].title ? lsz(g.sgs[sid].title) : { lw: 0, lh: 0 }, top = PAD + tl.lh + 4 + (g.sgs[sid].box3d ? 8 : 0) + (pb && tl.lw ? PORTGAP : 0);
      const W = Math.max(pl.w + 2 * PAD, tl.lw + 2 * PAD, 60), ox = (W - pl.w) / 2;
      items.forEach(v => { rel[v] = { x: pl.pos[v].x + ox, y: pl.pos[v].y + top }; });
      blk[sid] = { w: W, h: pl.h + PAD + top, tl };
    }else{
      // g.axis (84j2 bands, TB root only): every root block centred on one vertical axis A; g.axisHub (focus) puts that node on A
      // instead of its block's centre. A = the widest left half, so every block starts at RP or right of it. ⚠Opt-in: other views keep bytes.
      const ax = g.axis && !/^(LR|RL)$/.test(dirOf('')) ? {} : null;
      if(ax){ items.forEach(v => { let h = psize(v).w / 2;
        if(g.axisHub && v !== g.axisHub && lift(g.axisHub, '') === v){ h = size(g.axisHub).w / 2; for(let k = g.axisHub; k !== v; k = parentOf(k)) h += rel[k].x; }
        ax[v] = h; });
        const A = Math.max(0, ...items.map(v => ax[v])); items.forEach(v => { ax[v] = A - ax[v]; }); }
      items.forEach(v => { rel[v] = { x: (ax ? ax[v] : pl.pos[v].x) + RP, y: pl.pos[v].y + RP }; });
    }
  });
  const place = (sid, ox, oy) => (kids[sid] || []).forEach(v => {
    const z = size(v), R = { x: ox + rel[v].x, y: oy + rel[v].y, w: z.w, h: z.h };
    if(g.sgs[v]){
      R.depth = depth(v); sgs[v] = R;
      if(z.tl.lw) R.tr = { x: g.sgs[v].box3d ? R.x + 5 : R.x + (R.w - z.tl.lw) / 2, y: R.y + PAD - 4, w: z.tl.lw, h: z.tl.lh };   // title: a wall for lines and labels; ⚠box3d (84i) draws it at the left, so the wall moves with it
      place(v, R.x, R.y);
    } else nodes[v] = R;
  });
  place('', 0, 0);
  return { nodes, sgs };
  };
  const P1 = run(g.hint0 || null), hint = {};   // hint0: start order from the caller (84j2 bands); none = source order
  g.slist.concat(['']).forEach(sid => {
    const vt = /^(TB|BT)$/.test(dirOf(sid)), acc = {};
    g.edges.forEach(e => [[e.from, e.to], [e.to, e.from]].forEach(([i, o]) => {
      const a = lift(i, sid), R = P1.nodes[o] || P1.sgs[o];
      if(a == null || lift(o, sid) != null || !R) return;
      (acc[a] = acc[a] || []).push(vt ? R.x + R.w / 2 : R.y + R.h / 2);
    }));
    Object.keys(acc).forEach(v => { hint[v] = acc[v].reduce((s, c) => s + c, 0) / acc[v].length; });
  });
  const { nodes, sgs } = run(hint);
  const L = { nodes, sgs, edges: mmdRouteAll(g, nodes, sgs, dirOf) };
  if(!g.flLabels) mmdLabels(g, L);   // flLabels: caller draws tag mode, whose labels come from mmdFlPlace (★self-map 1.1s of 1.5s here)
  // Routes may run round the outside: shift everything so the whole drawing starts at RP.
  let x0 = Infinity, y0 = Infinity, W = 0, H = 0;
  const grow = (x, y) => { x0 = Math.min(x0, x); y0 = Math.min(y0, y); W = Math.max(W, x); H = Math.max(H, y); };
  const rs = Object.keys(nodes).map(k => nodes[k]).concat(Object.keys(sgs).map(k => sgs[k]), L.edges.map(e => e.lr).filter(Boolean));
  rs.forEach(R => { grow(R.x, R.y); grow(R.x + R.w, R.y + R.h); });
  L.edges.forEach(e => e.pts.forEach(p => grow(p[0], p[1])));
  if(!isFinite(x0)){ x0 = y0 = RP; }
  const dx = RP - x0, dy = RP - y0, mv = R => { if(R){ R.x += dx; R.y += dy; } };
  if(Math.abs(dx) > 0.01 || Math.abs(dy) > 0.01){
    rs.forEach(mv); Object.keys(sgs).forEach(k => mv(sgs[k].tr));
    L.edges.forEach(e => e.pts.forEach(p => { p[0] += dx; p[1] += dy; }));
  }
  return Object.assign(L, { w: Math.ceil(W + dx + RP), h: Math.ceil(H + dy + RP) });
}
// Outline of a polygon node shape in rect R ([[x, y]], clockwise from the top left), or null for boxes, rounds and circles.
function mmdPoly(s, R){
  const { x, y, w, h } = R, cx = x + w / 2, cy = y + h / 2;
  if(s === 'diamond') return [[cx, y], [x + w, cy], [cx, y + h], [x, cy]];
  if(s === 'hex') return [[x + 14, y], [x + w - 14, y], [x + w, cy], [x + w - 14, y + h], [x + 14, y + h], [x, cy]];
  if(s === 'flag') return [[x, y], [x + w, y], [x + w, y + h], [x, y + h], [x + 12, cy]];
  if(s === 'lean_r') return [[x + 11, y], [x + w, y], [x + w - 11, y + h], [x, y + h]];
  if(s === 'lean_l') return [[x, y], [x + w - 11, y], [x + w, y + h], [x + 11, y + h]];
  if(s === 'trap') return [[x + 11, y], [x + w - 11, y], [x + w, y + h], [x, y + h]];
  if(s === 'trapalt') return [[x, y], [x + w, y], [x + w - 11, y + h], [x + 11, y + h]];
  return null;
}
// Route end e (on the node's bounding box, n = the next point) pushed along its end run onto polygon P, so a line meets a
// diamond or hexagon on its outline instead of stopping at the invisible box side with a gap.
function mmdTip(e, n, P){
  const dx = e[0] - n[0], dy = e[1] - n[1], L = Math.hypot(dx, dy);
  if(!P || L < 1e-6) return e;
  const ux = dx / L, uy = dy / L;
  let best = Infinity;
  P.forEach((a, i) => {
    const b = P[(i + 1) % P.length], ex = b[0] - a[0], ey = b[1] - a[1], den = ux * ey - uy * ex;
    if(Math.abs(den) < 1e-9) return;
    const t = ((a[0] - e[0]) * ey - (a[1] - e[1]) * ex) / den, u = ((a[0] - e[0]) * uy - (a[1] - e[1]) * ux) / den;
    if(t > -0.01 && u > -1e-6 && u < 1 + 1e-6) best = Math.min(best, t);
  });
  return isFinite(best) && best > 0.01 ? [e[0] + ux * best, e[1] + uy * best] : e;
}
// Tag mode (84i) label placement: candidates above/below horizontal and left/right of vertical runs (start, middle, end);
// the nearest one clear of nodes, subgraph titles, placed labels and the bounds wins. None free -> number badge + legend entry.
function mmdFlPlace(g, L){
  const obs = Object.keys(L.nodes).map(k => L.nodes[k]).concat(Object.keys(L.sgs).map(k => L.sgs[k].tr).filter(Boolean));
  const ov = (a, b) => a.x < b.x + b.w + 2 && b.x < a.x + a.w + 2 && a.y < b.y + b.h + 2 && b.y < a.y + a.h + 2;
  const placed = [], labs = [], leg = [];
  // ⚠flHead: in-edge labels first, so head-anchored out-labels avoid them instead of displacing them
  const ord = L.edges.map((e, i) => i);
  if(g.flHead) ord.sort((p, q) => (L.edges[p].from === g.flHead) - (L.edges[q].from === g.flHead));
  ord.forEach(i => {
    const e = L.edges[i], ps = e.pts;
    if(!e.label || !ps || ps.length < 2){ labs[i] = null; return; }
    const ls = String(e.label).split('\n'), w = Math.max(...ls.map(mmdTw)) + 8, h = ls.length * 16 + 2, cs = [];
    // anchor = 16px along the first run: call numbers sit by the arrow's tail
    // ⚠g.flHead (arch focus): its out-edges share the hub as tail, so tail anchors pile up there -> anchor 28px before the head
    const hd = g.flHead && e.from === g.flHead, p0 = hd ? ps[ps.length - 1] : ps[0], p1 = hd ? ps[ps.length - 2] : ps[1];
    const l0 = Math.hypot(p1[0] - p0[0], p1[1] - p0[1]) || 1, t0 = Math.min(hd ? 28 : 16, l0 / 2) / l0;
    const ax = p0[0] + (p1[0] - p0[0]) * t0, ay = p0[1] + (p1[1] - p0[1]) * t0;
    for(let k = 1; k < ps.length; k++){
      const a = ps[k - 1], b = ps[k], hz = Math.abs(a[1] - b[1]) < 0.5, vt = Math.abs(a[0] - b[0]) < 0.5;
      if(hz){ const lo = Math.min(a[0], b[0]), hi = Math.max(a[0], b[0]);
        [(lo + hi) / 2, lo + w / 2 + 8, hi - w / 2 - 8].forEach(cx => { cs.push({ x: cx - w / 2, y: a[1] - 4 - h, w, h }, { x: cx - w / 2, y: a[1] + 4, w, h }); }); }
      else if(vt){ const lo = Math.min(a[1], b[1]), hi = Math.max(a[1], b[1]);
        [(lo + hi) / 2, lo + h / 2 + 8, hi - h / 2 - 8].forEach(cy => { cs.push({ x: a[0] + 4, y: cy - h / 2, w, h }, { x: a[0] - 4 - w, y: cy - h / 2, w, h }); }); }
    }
    const d = R => Math.hypot(R.x + R.w / 2 - ax, R.y + R.h / 2 - ay);
    const free = R => R.x >= 0 && R.y >= 0 && R.x + R.w <= L.w && R.y + R.h <= L.h && !obs.some(o => ov(R, o)) && !placed.some(o => ov(R, o));
    const R = cs.sort((p, q) => d(p) - d(q)).find(free);
    if(R){ placed.push(R); labs[i] = { R }; return; }
    const num = mmdNum(leg.length + 1), bw = Math.max(18, mmdTw(num) + 8), bc = cs.map(R => ({ x: R.x + R.w / 2 - bw / 2, y: R.y + R.h / 2 - 9, w: bw, h: 18 }));
    // badge: nearest candidate spot clear of placed labels first; the anchor only when every spot is taken
    let B = bc.sort((p, q) => d(p) - d(q)).find(free);
    // ⚠no bc spot free: slide along the edge (4px steps) before the anchor, which ignores nodes and labels (last resort)
    if(!B){ const sl = [];
      for(let k = 1; k < ps.length; k++){ const a = ps[k - 1], b = ps[k], n = Math.max(1, Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / 4));
        for(let j = 0; j <= n; j++){ const x = a[0] + (b[0] - a[0]) * j / n, y = a[1] + (b[1] - a[1]) * j / n; sl.push({ x: x - bw / 2, y: y - 9, w: bw, h: 18 }); } }
      B = sl.sort((p, q) => d(p) - d(q)).find(free) || { x: ax - bw / 2, y: ay - 9, w: bw, h: 18 }; }
    placed.push(B); labs[i] = { R: B, num }; leg.push({ num, label: e.label, e });
  });
  return { labs, leg };
}
// Laid-out graph → SVG string. key makes the arrow marker ids unique per diagram. Every label goes through esc().
// ⚠tag (84i flowchart only) adds rgr-* / mmdfe data-c / data-p hooks; without it the output must stay byte-identical (sha256-pinned).
function mmdSvg(g, L, key, tag){
  const f = v => String(Math.round(v * 10) / 10);
  const txt = (t, cx, cy, cls) => { const ls = String(t).split('\n');
    return '<text class=' + cls + ' x="' + f(cx) + '" text-anchor=middle dominant-baseline=central>' + ls.map((x, i) => '<tspan x="' + f(cx)
      + '" y="' + f(cy + (i - (ls.length - 1) / 2) * 16) + '">' + esc(x) + '</tspan>').join('') + '</text>'; };
  const poly = a => '<polygon points="' + a.map(p => f(p[0]) + ',' + f(p[1])).join(' ') + '"/>';
  const rect = (R, rx) => '<rect x="' + f(R.x) + '" y="' + f(R.y) + '" width="' + f(R.w) + '" height="' + f(R.h) + '" rx="' + f(rx) + '"/>';
  const shape = (s, R) => {
    const { x, y, w, h } = R, cx = x + w / 2, cy = y + h / 2;
    if(s === 'round') return rect(R, 9);
    if(s === 'stadium') return rect(R, h / 2);
    if(s === 'circle') return '<circle cx="' + f(cx) + '" cy="' + f(cy) + '" r="' + f(w / 2) + '"/>';
    if(s === 'dcircle') return '<circle cx="' + f(cx) + '" cy="' + f(cy) + '" r="' + f(w / 2) + '"/><circle cx="' + f(cx) + '" cy="' + f(cy) + '" r="' + f(w / 2 - 4) + '"/>';
    const pg = mmdPoly(s, R);
    if(pg) return poly(pg);
    if(s === 'cyl'){ const e = 6, rx = w / 2;
      return '<path d="M' + f(x) + ',' + f(y + e) + 'A' + f(rx) + ',' + e + ' 0 0 0 ' + f(x + w) + ',' + f(y + e) + 'A' + f(rx) + ',' + e + ' 0 0 0 '
        + f(x) + ',' + f(y + e) + 'V' + f(y + h - e) + 'A' + f(rx) + ',' + e + ' 0 0 0 ' + f(x + w) + ',' + f(y + h - e) + 'V' + f(y + e) + '"/>'; }
    if(s === 'sub') return rect(R, 2) + '<path d="M' + f(x + 8) + ',' + f(y) + 'V' + f(y + h) + 'M' + f(x + w - 8) + ',' + f(y) + 'V' + f(y + h) + '"/>';
    if(s === 'comp') return rect(R, 2) + '<g class=mmdcpi>' + rect({ x: x - 5, y: cy - 9, w: 10, h: 6 }, 1) + rect({ x: x - 5, y: cy + 3, w: 10, h: 6 }, 1) + '</g>';
    return rect(R, 3);
  };
  const id = 'mmda' + String(key || 'x').replace(/[^\w-]/g, '');
  const P = tag ? mmdFlPlace(g, L) : null, LG = [];
  let vb = '0 0 ' + L.w + ' ' + L.h, W = L.w, H = L.h;
  if(P && P.leg.length){   // legend column right of the drawing (tag mode only)
    let y = 16;
    P.leg.forEach(x => String(x.label).split('\n').forEach((t, k) => { LG.push({ e: x.e, t: (k ? '   ' : x.num + ' ') + t, y }); y += 16; }));
    W = Math.ceil(L.w + 16 + Math.max(...LG.map(r => mmdTw(r.t))) + 8); H = Math.max(H, y + 8); vb = '0 0 ' + W + ' ' + H;
  }
  let o = '<svg class=mmdsvg xmlns="http://www.w3.org/2000/svg" width="' + W + '" height="' + H + '" viewBox="' + vb + '" role=img>'
    + '<defs><marker id="' + id + '" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
    + '<path class=mmdah d="M0,0L10,5L0,10z"/></marker>' + (tag ? '<marker id="' + id + 'o" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
    + '<path class=mmdaho d="M0,0L10,5L0,10"/></marker>' : '') + '</defs>';
  Object.keys(L.sgs).sort((a, b) => L.sgs[a].depth - L.sgs[b].depth).forEach(k => {
    const R = L.sgs[k], t = g.sgs[k].title, n = t ? t.split('\n').length : 0, d3 = 8;
    const st = typeof g.sgs[k].tip === 'string' ? '<title>' + esc(g.sgs[k].tip) + '</title>' : '';   // hover text; no tip = bytes unchanged
    if(tag && g.sgs[k].box3d){   // UML «node»: bevel drawn inside the laid-out rect (routes keep their clearance), name underlined at the left
      const { x, y, w, h } = R, ty = R.tr ? R.tr.y + R.tr.h / 2 : y + 14, F = { x: x, y: y + d3, w: w - d3, h: h - d3 };
      o += '<g class="mmdsg mmdsg3 ' + esc(g.sgs[k].cls || '') + '" data-s="' + esc(k) + '">' + st + poly([[x, y + d3], [x + d3, y], [x + w, y], [x + w - d3, y + d3]])
        + poly([[x + w - d3, y + d3], [x + w, y], [x + w, y + h - d3], [x + w - d3, y + h]])
        + rect(F, 0) + (t ? '<text class=mmdst x="' + f(R.tr ? R.tr.x + 5 : x + 10) + '" y="' + f(ty) + '" dominant-baseline=central text-decoration=underline>' + esc(t) + '</text>' : '') + '</g>';
      return;
    }
    o += (tag && g.sgs[k].cls ? '<g class="mmdsg ' + esc(g.sgs[k].cls) + '">' : '<g class=mmdsg>') + st + rect(R, 6) + (t ? txt(t, R.x + R.w / 2, R.tr ? R.tr.y + R.tr.h / 2 : R.y + 12 + (n - 1) * 8, 'mmdst') : '') + '</g>';
  });
  const ge = {};   // L.edges keep no index: find the model edge by its ends (84i draws one edge per pair)
  if(tag) g.edges.forEach(e => { const k = e.from + '\u0001' + e.to; if(!ge[k]) ge[k] = e; });
  // data-f/data-t = node keys (same as data-p) so 84j hover can light an edge's ends without a lookup
  const fe = e => { const m = ge[e.from + '\u0001' + e.to]; return '<g class=mmdfe data-c="' + esc(((m && m.calls) || []).join(' ')) + '"' + (m && m.kind ? ' data-k="' + esc(m.kind) + '"' : '')   // data-k: 84j v2 edge kind only
    + ' data-f="' + esc(e.from) + '" data-t="' + esc(e.to) + '">'; };
  L.edges.forEach(e => {
    const pp = e.pts.slice(), z = pp.length - 1, pg = k => g.nodes[k] && L.nodes[k] ? mmdPoly(g.nodes[k].shape, L.nodes[k]) : null;
    if(z > 0 && e.from !== e.to){ pp[0] = mmdTip(pp[0], pp[1], pg(e.from)); pp[z] = mmdTip(pp[z], pp[z - 1], pg(e.to)); }
    const d = mmdPathD(pp);
    const op = tag && ge[e.from + '\u0001' + e.to] && ge[e.from + '\u0001' + e.to].open ? 'o' : '';   // open arrowhead (UML dependency)
    // mmdhit = wide transparent copy of the line so a 1px edge is clickable (tag mode only; untagged bytes are pinned)
    o += (tag ? fe(e) + '<path class=mmdhit d="' + d + '"/>' : '') + '<path class="mmde e-' + e.style + '" d="' + d + '"' + (e.head ? ' marker-end="url(#' + id + op + ')"' : '')
      + (e.both ? ' marker-start="url(#' + id + ')"' : '') + '/>' + (tag ? '</g>' : '');
  });
  g.nlist.forEach(k => { const R = L.nodes[k], N = g.nodes[k]; if(R) o += '<g class="mmdn s-' + N.shape + '"' + (tag ? ' data-p="' + esc(k) + '"' : '') + '>'
    + (tag && N.tip ? '<title>' + esc(N.tip) + '</title>' : '') + shape(N.shape, R)
    + txt(N.label, R.x + R.w / 2 + (N.shape === 'comp' ? 7 : 0), R.y + R.h / 2 + (N.shape === 'cyl' ? 4 : 0), 'mmdtx') + '</g>'; });
  // Label pills (or a numbered badge listed under the diagram, mmdLabels) drawn last, above every line.
  const tip = e => { const m = ge[e.from + '\u0001' + e.to]; return m && m.tip ? '<title>' + esc(m.tip) + '</title>' : ''; };
  if(tag){
    L.edges.forEach((e, i) => { const p = P.labs[i], R = p && p.R; if(R) o += fe(e) + '<g class="mmdel mmdfl' + (p.num ? ' mmdnum' : '') + '">' + tip(e) + rect(R, p.num ? 9 : 3)
      + txt(p.num || e.label, R.x + R.w / 2, R.y + R.h / 2, 'mmdtx') + '</g></g>'; });
    LG.forEach(r => { o += fe(r.e) + '<g class=mmdflg>' + tip(r.e) + '<text class=mmdtx x="' + f(L.w + 16) + '" y="' + f(r.y) + '" dominant-baseline=central>' + esc(r.t) + '</text></g></g>'; });
  }
  else L.edges.forEach(e => { const R = e.lr; if(e.label && R) o += '<g class="mmdel' + (e.num ? ' mmdnum' : '') + '">' + rect(R, Math.min(R.h / 2, 9))
    + txt(e.num || e.label, R.x + R.w / 2, R.y + R.h / 2, 'mmdtx') + '</g>'; });
  return o + '</svg>';
}
// Numbered labels (no free spot on their line) listed under the diagram: «① label  from → to».
function mmdLegend(g, L){
  if(!L.notes || !L.notes.length) return '';
  const nm = id => String(g.nodes[id] ? g.nodes[id].label : g.sgs[id] ? g.sgs[id].title || id : id).replace(/\n/g, ' ');
  return '<ol class=mmdleg>' + L.notes.map(n => '<li><b>' + esc(n.num) + '</b> ' + esc(n.label.replace(/\n/g, ' '))
    + ' <span class=mmdlft>' + esc(nm(n.from)) + ' → ' + esc(nm(n.to)) + '</span></li>').join('') + '</ol>';
}
// One ```mermaid fence → diagram with a «Source text» toggle, or the plain code block plus «Preview not supported for this type».
function mmdBlock(src){
  const code = codeBlock(src, 'mermaid');
  let svg = '';
  try {
    const g = mmdParse(src);
    let h = 0;
    for(const ch of String(src)) h = (h * 31 + ch.charCodeAt(0)) | 0;
    if(g.ok){
      const L = mmdLayout(g);
      svg = mmdSvg(g, L, (h >>> 0).toString(36));
      svg += mmdLegend(g, L);
    } else if(g.type === 'sequenceDiagram'){       // 81h
      const q = mmdSeqParse(src);
      if(q.ok) svg = mmdSeqSvg(q, mmdSeqLayout(q), (h >>> 0).toString(36));
    }
  } catch(e){ svg = ''; if(typeof softErr === 'function') softErr('mermaid', e); }
  if(!svg) return '<div class=mmdno><div class=mmdnote>' + esc(T('Preview not supported for this type')) + '</div>' + code + '</div>';
  return '<div class=mmd><div class=mmdbar><button type=button class=mmdtg aria-pressed=false>' + esc(T('Source text')) + '</button></div>'
    + '<div class=mmdv>' + svg + '</div><div class=mmdsrc>' + code + '</div></div>';
}
// «Source text» toggle: one delegated listener (the preview is re-rendered as a string, so no per-node handlers).
document.addEventListener('click', ev => {
  const b = ev.target && ev.target.closest && ev.target.closest('.mmdtg'), w = b && b.closest('.mmd');
  if(!w) return;
  const on = w.classList.toggle('src');
  b.classList.toggle('on', on);
  b.setAttribute('aria-pressed', on ? 'true' : 'false');
});
// Ctrl/⌘ + wheel (or a trackpad pinch) inside a diagram zooms it 0.5–3× around its natural 100% size; plain wheel still scrolls.
document.addEventListener('wheel', ev => {
  if(!(ev.ctrlKey || ev.metaKey)) return;
  const v = ev.target && ev.target.closest && ev.target.closest('.mmdv'), s = v && v.querySelector('svg.mmdsvg');
  if(!s) return;
  ev.preventDefault();
  const vb = (s.getAttribute('viewBox') || '').split(' ').map(Number), z = Math.max(0.5, Math.min(3, (+s.dataset.z || 1) * Math.exp(-ev.deltaY * 0.002)));
  s.dataset.z = String(z);
  s.setAttribute('width', String(Math.round(vb[2] * z))); s.setAttribute('height', String(Math.round(vb[3] * z)));
}, { passive: false });
