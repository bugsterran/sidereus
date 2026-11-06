// ── Markdown preview: ```mermaid sequenceDiagram (81e mmdBlock hands it here when mmdParse reports type sequenceDiagram) ──────
// Subset: participant/actor (+ as), messages ->> -->> -> --> -x --x -) --) <<->>, Note left of/right of/over, loop/alt/else/opt/par/and/
// critical/option/break/rect … end frames, autonumber. activate/deactivate/box/title and unknown lines are skipped, never thrown.
// ⚠Split on lines only (not mmdSplit's ';') — message text like «regex check; rows only» must stay whole. Labels go through esc() on output.

// Mermaid source → { ok, seq, parts, pmap, items, auto } or { ok: false, type }. Throws only when too large.
function mmdSeqParse(src){
  const lines = String(src == null ? '' : src).split(/\r?\n/), st = [];
  let k = 0;
  while(k < lines.length && !lines[k].trim()) k++;
  if(k < lines.length && lines[k].trim() === '---'){ k++; while(k < lines.length && lines[k].trim() !== '---') k++; k++; }
  for(; k < lines.length; k++){ const t = lines[k].trim(); if(t && t.slice(0, 2) !== '%%') st.push(t); }
  if(!/^sequenceDiagram\b/.test(st[0] || '')) return { ok: false, type: (st[0] || '').split(/\s+/)[0] };
  const g = { ok: true, seq: true, parts: [], pmap: {}, items: [], auto: false }, stack = [];
  let n = 0, fid = 0;
  // ⚠mmdLabel drops every tag; here only formatting tags go — «GET ?since=<ns>» keeps its <ns> (escaped back to text on output).
  const lab = s => mmdLabel(String(s == null ? '' : s).replace(/#(\d{1,7});/g, (m, d) => (+d > 31 && +d <= 0x10FFFF ? String.fromCodePoint(+d) : ''))
    .replace(/<(?!\/?(?:br|b|i|u|s|em|strong|span|code|small|sup|sub|a|font|p|div)\b)/gi, '&lt;'));
  const part = (id, label, actor) => {
    id = String(id).replace(/@\{[\s\S]*\}$/, '').trim();
    let p = g.pmap[id];
    if(!p){ p = g.pmap[id] = { id, label: id, actor: false, i: g.parts.length }; g.parts.push(p); }
    if(label != null) p.label = lab(label) || id;
    if(actor) p.actor = true;
    return id;
  };
  const top = () => { for(let i = stack.length - 1; i >= 0; i--) if(!stack[i].box) return stack[i]; return null; };
  for(let q = 1; q < st.length; q++){
    const s = st[q];
    let m;
    if(/^autonumber\b/.test(s)){ g.auto = true; continue; }
    if((m = s.match(/^(?:create\s+)?(participant|actor)\s+(.+?)(?:\s+as\s+(.+))?$/))){ part(m[2], m[3] == null ? null : m[3], m[1] === 'actor'); continue; }
    if(/^box\b/.test(s)){ stack.push({ box: true }); continue; }
    if((m = s.match(/^(loop|alt|opt|par|critical|break|rect)\b\s*(.*)$/))){
      const f = { id: fid++, kind: m[1] };
      stack.push(f); g.items.push({ k: 'open', f: f.id, kind: m[1], label: m[1] === 'rect' ? '' : lab(m[2]) });
      continue;
    }
    if((m = s.match(/^(else|and|option)\b\s*(.*)$/))){ const f = top(); if(f) g.items.push({ k: 'sect', f: f.id, label: lab(m[2]) }); continue; }
    if(s === 'end'){ const f = stack.pop(); if(f && !f.box) g.items.push({ k: 'close', f: f.id }); continue; }
    if((m = s.match(/^note\s+(left of|right of|over)\s+([^:]+?)\s*:\s*(.*)$/i))){
      const ps = m[2].split(',').map(x => x.trim()).filter(Boolean).slice(0, 2).map(x => part(x));
      if(ps.length) g.items.push({ k: 'note', pos: m[1].toLowerCase().split(' ')[0], ps, label: lab(m[3]) });
      continue;
    }
    const c = s.indexOf(':'), head = c < 0 ? s : s.slice(0, c);
    if((m = head.match(/^(.+?)\s*(<<-->>|<<->>|-->>|->>|--x|-x|--\)|-\)|-->|->)\s*([+-]?)\s*(.+)$/))){
      const a = m[1].trim(), b = m[4].trim(), ar = m[2];
      if(!a || !b || /\s/.test(a) || /\s/.test(b)) continue;
      g.items.push({ k: 'msg', a: part(a), b: part(b), label: c < 0 ? '' : lab(s.slice(c + 1)), dash: /^(<<)?--/.test(ar),
        head: /x$/.test(ar) ? 'cross' : /\)$/.test(ar) ? 'open' : />>$/.test(ar) ? 'fill' : 'none', both: /^<</.test(ar), n: g.auto ? ++n : 0 });
    }
    // anything else (activate, deactivate, destroy, title, links, …) is skipped
  }
  while(stack.length){ const f = stack.pop(); if(!f.box) g.items.push({ k: 'close', f: f.id }); }   // unclosed frames close quietly
  if(g.parts.length > 80 || g.items.length > 1200) throw new Error('mermaid: too large');
  if(!g.parts.length) return { ok: false, type: 'empty' };
  return g;
}
// Parsed sequence → lifeline centres, boxes, message/note/frame geometry, total size. Columns widen until every label fits its span.
// opt {tight:1} (84k only): smaller minimum gap, box padding and label padding; a self label reserves only its own width
// (its number sits on the lifeline). Omitted = md preview spacing, unchanged.
function mmdSeqLayout(g, opt){
  const PAD = 10, SW = 30, LH = 16, M = 12, np = g.parts.length, TI = !!(opt && opt.tight), GMIN = TI ? 64 : 110, GP = TI ? 24 : 36, LP = TI ? 8 : 24;
  const lw = t => (t ? Math.max(...String(t).split('\n').map(mmdTw)) : 0), nl = t => (t ? String(t).split('\n').length : 1);
  const bx = g.parts.map(p => mmdBox(p.label, 'rect')), BH = Math.max(...bx.map(b => b.h)), ix = id => g.pmap[id].i;
  const gap = [];
  for(let i = 0; i < np - 1; i++) gap.push(Math.max(bx[i].w / 2 + bx[i + 1].w / 2 + GP, GMIN));
  const need = (i, j, d) => {
    if(i > j){ const t = i; i = j; j = t; }
    let s = 0;
    for(let q = i; q < j; q++) s += gap[q];
    if(j > i && s < d) for(let q = i; q < j; q++) gap[q] += (d - s) / (j - i);
  };
  g.items.forEach(it => {
    if(it.k === 'msg'){
      const w = lw(it.label) + (it.n ? 22 : 0) + LP;
      if(it.a !== it.b) need(ix(it.a), ix(it.b), w);
      else if(ix(it.a) < np - 1) need(ix(it.a), ix(it.a) + 1, TI ? SW + 18 + lw(it.label) : SW + 16 + w);
    } else if(it.k === 'note' && it.ps.length === 1){
      const i = ix(it.ps[0]), w = lw(it.label) + 40;
      if(it.pos === 'left' && i > 0) need(i - 1, i, w);
      if(it.pos === 'right' && i < np - 1) need(i, i + 1, w);
    }
  });
  const cx = [0];
  for(let i = 0; i < np - 1; i++) cx.push(cx[i] + gap[i]);
  const msgs = [], notes = [], frames = [], open = [], fr = {};
  let y = BH + 14, x0 = Infinity, x1 = -Infinity;
  const ext = (a, b) => { x0 = Math.min(x0, a); x1 = Math.max(x1, b); const f = open[open.length - 1]; if(f){ f.x0 = Math.min(f.x0, a); f.x1 = Math.max(f.x1, b); } };
  g.parts.forEach((p, i) => ext(cx[i] - bx[i].w / 2, cx[i] + bx[i].w / 2));
  g.items.forEach(it => {
    if(it.k === 'msg'){
      const a = cx[ix(it.a)], b = cx[ix(it.b)], h = it.label ? nl(it.label) * LH : 0;
      if(it.a === it.b){
        const y0 = y + 6, hh = Math.max(20, h);
        msgs.push({ it, pts: [[a, y0], [a + SW, y0], [a + SW, y0 + hh], [a, y0 + hh]], lx: a + SW + 6, ly: y0 + hh / 2, self: true });
        ext(a, a + SW + 6 + lw(it.label)); y = y0 + hh + 14;
      } else {
        y += h + 6;
        msgs.push({ it, pts: [[a, y], [b, y]], lx: (a + b) / 2 + (it.n ? (b > a ? 9 : -9) : 0), ly: y - 4 - h / 2 });
        ext(Math.min(a, b), Math.max(a, b)); y += 14;
      }
    } else if(it.k === 'note'){
      const i = ix(it.ps[0]), j = ix(it.ps[it.ps.length - 1]), h = nl(it.label) * LH + 12;
      let w = lw(it.label) + 20, x;
      if(it.pos === 'left') x = cx[i] - 10 - w;
      else if(it.pos === 'right') x = cx[i] + 10;
      else { const l = Math.min(cx[i], cx[j]) - (i === j ? 0 : 20), r = Math.max(cx[i], cx[j]) + (i === j ? 0 : 20); w = Math.max(w, r - l); x = (l + r) / 2 - w / 2; }
      y += 4; notes.push({ it, x, y, w, h }); ext(x, x + w); y += h + 10;
    } else if(it.k === 'open'){
      y += 4;
      const f = fr[it.f] = { kind: it.kind, label: it.label, top: y, x0: Infinity, x1: -Infinity, sects: [], depth: open.length };
      open.push(f); y += it.kind === 'rect' ? 8 : 22;
    } else if(it.k === 'sect' && fr[it.f]){
      y += 6; fr[it.f].sects.push({ y, label: it.label }); y += 20;
    } else if(it.k === 'close' && fr[it.f]){
      const f = fr[it.f];
      open.splice(open.indexOf(f), 1);
      if(!isFinite(f.x0)){ f.x0 = cx[0]; f.x1 = cx[np - 1]; }
      const tab = f.kind === 'rect' ? 0 : lw(f.kind) + 18, lab = f.label ? lw('[' + f.label + ']') + 12 : 0;
      f.x = f.x0 - M; f.y = f.top; f.h = y + 8 - f.top; f.tw = tab;
      f.w = Math.max(f.x1 - f.x0 + 2 * M, tab + lab + 10, ...f.sects.map(s => (s.label ? lw('[' + s.label + ']') + 24 : 0)));
      frames.push(f); y += 8; ext(f.x, f.x + f.w); y += 8;
    }
  });
  const bot = y + 10;
  return { cx, bx, BH, bot, msgs, notes, frames, dx: PAD - x0, w: Math.ceil(x1 - x0 + 2 * PAD), h: Math.ceil(bot + BH + 2 * PAD) };
}
// Laid-out sequence → SVG string, same classes/tokens as the flowchart (75-structure.css .mmd*). key makes marker ids unique.
// tag (84i playback only): lifelines get data-p=<part index>, each message/note a <g class=mmdsqm data-i=<item index> data-d=l|r>.
// ⚠Without tag the output must stay byte-identical (md preview + its tests).
// tag {tag:1, mm:1} (84i only): Mermaid look — layer bands (parts' ly), activation bars, arrows ending at bar edges.
// tag {tag:1, fit:k} (84k only): width 100% of the pane, never wider than natural nor narrower than k × natural; part.full → <title>.
function mmdSeqSvg(g, L, key, tag){
  const mm = !!(tag && typeof tag === 'object' && tag.mm), fit = tag && typeof tag === 'object' && tag.fit, f = v => String(Math.round(v * 10) / 10);
  const txt = (t, x, cy, cls, anchor) => { const ls = String(t).split('\n');
    return '<text class=' + cls + ' x="' + f(x) + '" text-anchor=' + (anchor || 'middle') + ' dominant-baseline=central>' + ls.map((s, i) => '<tspan x="' + f(x)
      + '" y="' + f(cy + (i - (ls.length - 1) / 2) * 16) + '">' + esc(s) + '</tspan>').join('') + '</text>'; };
  const rect = (x, y, w, h, rx) => '<rect x="' + f(x) + '" y="' + f(y) + '" width="' + f(w) + '" height="' + f(h) + '" rx="' + f(rx) + '"/>';
  const id = 'mmds' + String(key || 'x').replace(/[^\w-]/g, '');
  const mk = (sfx, d, cls) => '<marker id="' + id + sfx + '" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
    + '<path class=' + cls + ' d="' + d + '"/></marker>';
  const H = mm ? L.h + 22 : L.h, bars = mm ? mmdSeqBars(g, L) : [];   // mm: +22 on top for the band labels
  let o = '<svg class="mmdsvg mmdseq' + (mm ? ' mmdmm' : '') + '" xmlns="http://www.w3.org/2000/svg" width="' + L.w + '" height="' + H + '" viewBox="0 0 ' + L.w + ' ' + H + '"'
    + (fit ? ' style="width:100%;height:auto;max-width:' + L.w + 'px;min-width:' + Math.ceil(L.w * fit) + 'px"' : '') + ' role=img>'
    + '<defs>' + mk('f', 'M0,0L10,5L0,10z', 'mmdah') + mk('o', 'M1,1L9,5L1,9', 'mmdahx') + mk('x', 'M2,1L9,9M9,1L2,9', 'mmdahx') + '</defs>'
    + '<g transform="translate(' + f(L.dx) + ',' + (mm ? 32 : 10) + ')">';
  if(mm){   // one band per run of same-layer participants (84i sorts parts by ly)
    const cls = ['rgr-entry', 'rgr-domain', 'rgr-data', 'rgr-util'], nm = [T('Entry'), T('Service'), T('Data'), T('Other')];
    const ly = p => (p.ly >= 0 && p.ly <= 3 ? p.ly : 3);
    for(let i = 0, j; i < g.parts.length; i = j){
      for(j = i + 1; j < g.parts.length && ly(g.parts[j]) === ly(g.parts[i]); j++);
      const l = ly(g.parts[i]), x0 = L.cx[i] - L.bx[i].w / 2 - 10, x1 = L.cx[j - 1] + L.bx[j - 1].w / 2 + 10;
      o += '<g class="mmdsqb ' + cls[l] + '">' + rect(x0, -20, x1 - x0, L.bot + L.BH + 26, 6) + txt(nm[l], x0 + 8, -10, 'mmdsqbl', 'start') + '</g>';
    }
  }
  g.parts.forEach((p, i) => { o += '<path class="mmde e-dot mmdll"' + (tag ? ' data-p=' + i : '') + ' d="M' + f(L.cx[i]) + ',' + f(L.BH) + 'V' + f(L.bot) + '"/>'; });
  L.frames.slice().sort((a, b) => a.depth - b.depth).forEach(F => {
    o += '<g class=mmdsqf>' + rect(F.x, F.y, F.w, F.h, 3);
    if(F.tw) o += '<path class=mmdsqt d="M' + f(F.x) + ',' + f(F.y) + 'H' + f(F.x + F.tw) + 'V' + f(F.y + 12) + 'L' + f(F.x + F.tw - 6) + ',' + f(F.y + 18)
      + 'H' + f(F.x) + 'Z"/>' + txt(F.kind, F.x + F.tw / 2 - 3, F.y + 9, 'mmdst');
    if(F.label) o += txt('[' + F.label + ']', F.x + F.tw + 8, F.y + 9, 'mmdst', 'start');
    F.sects.forEach(s => { o += '<path class=mmdsqd d="M' + f(F.x) + ',' + f(s.y) + 'H' + f(F.x + F.w) + '"/>'
      + (s.label ? txt('[' + s.label + ']', F.x + 8, s.y + 10, 'mmdst', 'start') : ''); });
    o += '</g>';
  });
  bars.forEach(b => { o += '<rect class=mmdsqa data-i=' + b.ci + ' data-e=' + b.e + ' x="' + f(b.x - 5) + '" y="' + f(b.y0) + '" width="10" height="' + f(b.y1 - b.y0) + '"/>'; });
  L.msgs.forEach(m => {
    const it = m.it, d = 'M' + (mm ? mmdSeqEdge(g, L, bars, m) : m.pts).map(p => f(p[0]) + ',' + f(p[1])).join('L');
    if(tag) o += '<g class=mmdsqm data-i=' + g.items.indexOf(it) + ' data-d=' + (!m.self && m.pts[1][0] < m.pts[0][0] ? 'l' : 'r') + '>';
    o += '<path class="mmde e-' + (it.dash ? 'dot' : 'solid') + '" d="' + d + '"' + (it.head !== 'none' ? ' marker-end="url(#' + id + ({ fill: 'f', open: 'o', cross: 'x' })[it.head] + ')"' : '')
      + (it.both ? ' marker-start="url(#' + id + 'f)"' : '') + '/>';
    if(it.label) o += m.self ? txt(it.label, m.lx, m.ly, 'mmdtx', 'start') : txt(it.label, m.lx, m.ly, 'mmdtx');
    if(it.n) o += '<g class=mmdsqn><circle cx="' + f(m.pts[0][0]) + '" cy="' + f(m.pts[0][1]) + '" r="8"/>' + txt(String(it.n), m.pts[0][0], m.pts[0][1], 'mmdtx') + '</g>';
    if(tag) o += '</g>';
  });
  L.notes.forEach(N => { o += (tag ? '<g class=mmdsqm data-i=' + g.items.indexOf(N.it) + ' data-d=r>' : '') + '<g class=mmdsqnote>' + rect(N.x, N.y, N.w, N.h, 2) + txt(N.it.label, N.x + N.w / 2, N.y + N.h / 2, 'mmdtx') + '</g>' + (tag ? '</g>' : ''); });
  g.parts.forEach((p, i) => [0, L.bot].forEach(y0 => {
    const b = L.bx[i], x = L.cx[i] - b.w / 2;
    o += '<g class="mmdn s-' + (p.actor ? 'stadium' : 'rect') + '">' + (fit && p.full ? '<title>' + esc(p.full) + '</title>' : '') + rect(x, y0, b.w, L.BH, p.actor ? L.BH / 2 : 3) + txt(p.label, L.cx[i], y0 + L.BH / 2, 'mmdtx') + '</g>';
  }));
  return o + '</g></svg>';
}
// Pure (mm only): activation bars {ci, e, p, x, y0, y1} — one per non-dashed, non-self call, on the callee lifeline from the
// call's y to its `end` item's y; +4px right per bar already open on the same lifeline.
function mmdSeqBars(g, L){
  const my = new Map(), bars = [];
  L.msgs.forEach(m => my.set(m.it, m.pts[m.pts.length - 1][1]));
  L.notes.forEach(N => my.set(N.it, N.y + N.h));
  L.msgs.forEach(m => {
    const it = m.it;
    if(m.self || it.dash || it.a === it.b || !g.pmap[it.b]) return;
    const ci = g.items.indexOf(it), e = it.end == null ? ci : it.end, p = g.pmap[it.b].i, y0 = m.pts[0][1];
    const y1 = Math.max(y0 + 12, my.has(g.items[e]) ? my.get(g.items[e]) : y0);
    const n = bars.filter(b => b.p === p && b.y0 <= y0 && y0 <= b.y1).length;
    bars.push({ ci: ci, e: e, p: p, x: L.cx[p] + 4 * n, y0: y0, y1: y1 });
  });
  return bars;
}
// Pure (mm only): message points moved off the lifeline centre to the edge of the innermost bar open there (cx ∓ 5).
function mmdSeqEdge(g, L, bars, m){
  const bar = (id, y) => { let r = null; const p = g.pmap[id] && g.pmap[id].i; bars.forEach(b => { if(b.p === p && b.y0 <= y && y <= b.y1) r = b; }); return r; };
  const pts = m.pts.map(q => q.slice()), y = pts[0][1];
  if(m.self){ const a = bar(m.it.a, y); if(a){ pts[0][0] = pts[3][0] = a.x + 5; } return pts; }
  const dir = pts[1][0] >= pts[0][0] ? 1 : -1, a = bar(m.it.a, y), b = bar(m.it.b, y);
  if(a) pts[0][0] = a.x + 5 * dir;
  if(b) pts[1][0] = b.x - 5 * dir;
  return pts;
}
