// «Pipelines» canvas model (step 4, docs/dev/PIPELINE.md): pure helpers — pipeline row <-> graph, order, checks, layout, edge paths.
// n8n-style drag & drop: nodes + flow edges + loop-back edges over the SAME JSON.
// Graph G = {nodes:[{id, title, agent, ...stage fields, ui:{x,y}}], flow:[[from, to]], loops:[{from, to, max, then, stopOn}], defaults}.
// Stage order = order along the flow chain; a loop-back edge = the source stage's onFail.goto (runner semantics unchanged).
const PLG_TITLES = ['설계', '구현', '검증', '리뷰', '재검증', '재현', '원인', '수정', '회귀', '트리아지', '라이브 검증', 'AI 설정 점검', '프롬프트 검증'];   // = runner STAGE_TITLES
// Stage display name for the current language (PLG_NAMES, 06-i18n-w.js); unknown titles show as-is. Display only.
// Renamed recommended titles (old -> new): a legacy file or run still matches. ⚠Same map in sidereus/pipeline_schema.py RENAMED.
function plTk(t){ const R = { '최종 검증': '재검증' }; return typeof t === 'string' && Object.prototype.hasOwnProperty.call(R, t) ? R[t] : t; }   // self-contained: test harnesses load it by name
function plgShow(title){ const d = PLG_NAMES[LANG] || {}, h = k => Object.prototype.hasOwnProperty.call(d, k), b = plgBase(title);
  return h(title) ? d[title] : b !== title && h(b) ? d[b] + title.slice(b.length) : title; }   // a numbered copy shows as «Verify 2»
// Catalog key of a stage title: a copy «<title> <n>» (n >= 2, plgFreeTitle) matches its template «<title>». Used by every title -> catalog lookup.
function plgBase(t){ const m = / (\d+)$/.exec(typeof t === 'string' ? t : ''); return m && +m[1] >= 2 ? t.slice(0, m.index) : t; }
// First free title for another copy: «<t>», else «<t> 2», «<t> 3»… cut to the schema's 40 chars.
function plgFreeTitle(G, t){
  const has = x => G.nodes.some(n => n.title === x);
  for(let i = 1; i < 1000; i++){ const sf = i === 1 ? '' : ' ' + i, c = t.slice(0, 40 - sf.length) + sf; if(!has(c)) return c; }
  return '';
}
function plgTplShow(title){ const d = PLG_TPL_NAMES[LANG] || {}; return Object.prototype.hasOwnProperty.call(d, title) ? d[title] : title; }
const PLG_MODELS = ['inherit', 'opus', 'sonnet', 'haiku'];
const PLG_KEYS = ['title', 'agent', 'instr', 'model', 'skill', 'retry', 'gate', 'parallel', 'produces', 'fanout', 'onError', 'onlyOnJump', 'ui'];
const PLG_W = 184, PLG_H = 100, PLG_GX = 64, PLG_X0 = 44, PLG_Y0 = 24, PLG_LANE = 34;   // X0 leaves a left gutter for cross-row loop-backs   // node size · gaps · loop-back lane spacing
function plgFrom(p){
  const S = p.stages || [], ids = S.map((s, i) => 'n' + (i + 1));
  const placed = S.every(s => s.ui && isFinite(s.ui.x) && isFinite(s.ui.y));
  const nodes = S.map((s, i) => {
    const n = { id: ids[i] };
    PLG_KEYS.forEach(k => { if(s[k] !== undefined) n[k] = k === 'ui' ? Object.assign({ x: s.ui.x, y: s.ui.y }, s.ui.color ? { color: s.ui.color } : {}) : s[k]; });
    if(!placed) n.ui = { x: PLG_X0 + i * (PLG_W + PLG_GX), y: PLG_Y0 };
    return n;
  });
  const byT = t => ids[S.findIndex(s => s.title === t)];
  const loops = S.map((s, i) => s.onFail ? Object.assign({ from: ids[i], to: byT(s.onFail.goto), max: s.onFail.max },
    s.onFail.then ? { then: s.onFail.then } : {}, s.onFail.stopOn !== undefined ? { stopOn: s.onFail.stopOn.slice() } : {}) : null).filter(Boolean);
  return { nodes, flow: ids.slice(1).map((id, i) => [ids[i], id]), loops,
    defaults: { model: p.defaults.model, retry: p.defaults.retry }, use: p.use || '', rules: p.rules || '', guards: JSON.parse(JSON.stringify(p.guards || {})), seq: S.length };
}
function plgNode(G, id){ return G.nodes.find(n => n.id === id) || null; }
// Node width = its content, measured by the canvas (48d plMeasure) into G.wd {id: px}; PLG_W until then. ⚠G.wd is never saved.
function plgW(G, id){ const w = G && G.wd && G.wd[id]; return w > 0 ? w : PLG_W; }
// Node height likewise (G.ht, ≥ PLG_H): a gate result line grows the card, and edge anchors/lanes must follow it. ⚠G.ht is never saved.
function plgH(G, id){ const h = G && G.ht && G.ht[id]; return h > 0 ? h : PLG_H; }
// {order:[ids], errs:[{id, msg}]}: the flow must be one chain (no branch, no merge, no cycle, nothing left out).
function plgOrder(G){
  const errs = [], outs = {}, ins = {};
  G.flow.forEach(([a, b]) => { (outs[a] = outs[a] || []).push(b); (ins[b] = ins[b] || []).push(a); });
  G.nodes.forEach(n => {
    if((outs[n.id] || []).length > 1) errs.push({ id: n.id, msg: TV({ msg: 'Branch: {t} splits into two paths', vars: { t: plgShow(n.title) } }) });
    if((ins[n.id] || []).length > 1) errs.push({ id: n.id, msg: TV({ msg: 'Merge: two paths lead into {t}', vars: { t: plgShow(n.title) } }) });
  });
  const heads = G.nodes.filter(n => !(ins[n.id] || []).length);
  if(G.nodes.length && !heads.length) errs.push({ id: '', msg: T('Cycle: the flow returns to the start — connect loop-backs with the bottom port') });
  if(heads.length > 1) errs.push({ id: '', msg: TV({ msg: 'Broken: {n} start stages ({t})', vars: { n: heads.length, t: heads.map(n => plgShow(n.title)).join(', ') } }) });
  const order = [], seen = {};
  let cur = heads.length ? heads[0].id : null;
  while(cur && !seen[cur]){ seen[cur] = 1; order.push(cur); cur = (outs[cur] || [])[0]; }
  if(cur && seen[cur] && heads.length) errs.push({ id: cur, msg: TV({ msg: 'Cycle: the flow returns to {t} — connect loop-backs with the bottom port', vars: { t: plgShow(plgNode(G, cur).title) } }) });
  return { order, errs };
}
// Stage list in runner schema (task travels as `instr`, the server maps it back).
function plgStages(G, order){
  return order.map(id => {
    const n = plgNode(G, id), s = {};
    PLG_KEYS.forEach(k => { const v = n[k]; if(v !== undefined && v !== null && v !== '' && v !== false) s[k] = v; });
    const l = G.loops.find(x => x.from === id), to = l && plgNode(G, l.to);
    if(l && to) s.onFail = Object.assign({ goto: to.title, max: l.max }, l.then ? { then: l.then } : {}, l.stopOn !== undefined ? { stopOn: l.stopOn } : {});
    return s;
  });
}
function plgKey(G){ const o = plgOrder(G).order; return JSON.stringify({ d: G.defaults, u: G.use || '', r: G.rules || '', g: plgGuards(G), s: plgStages(G, o) }); }
// Every reason the graph cannot be saved, with the node it belongs to ('' = whole graph). Mirrors the runner's validate.
function plgCheck(G){
  const { order, errs } = plgOrder(G);
  const pos = {}; order.forEach((id, i) => { pos[id] = i; });
  const n = G.nodes.length, bad = (id, msg) => errs.push({ id, msg });
  if(!n || n > 20) bad('', T('A pipeline needs 1–20 stages'));
  if(order.length !== n && !errs.length) bad('', T('Broken: some stages are not connected to the flow'));
  if(!PLG_MODELS.includes(G.defaults.model)) bad('', T('The default model is not valid'));
  if(!(Number.isInteger(G.defaults.retry) && G.defaults.retry >= 0 && G.defaults.retry <= 3)) bad('', T('Default retries: 0–3'));
  if((G.rules || '').length > 2000) bad('', T('Rules: up to 2000 characters'));
  if((G.use || '').length > 120 || /[\r\n]/.test(G.use || '')) bad('', T('«When to use»: one line, up to 120 characters'));
  if(G.nodes.filter(x => !PLG_TITLES.includes(plTk(x.title))).length > 12) bad('', T('Up to 12 custom stages'));
  const int = (v, lo, hi) => v === undefined || v === null || v === '' || (Number.isInteger(v) && v >= lo && v <= hi);
  G.nodes.forEach(x => {
    const t = x.title;
    if(typeof t !== 'string' || !t.trim() || t.length > 40 || /[\r\n]/.test(t)) bad(x.id, T('Stage name: one line, 1–40 characters'));
    // Reserved runner slot prefix (plgSlots), data not UI: shown verbatim in both languages.
    else if(t.startsWith('사용자 단계')) bad(x.id, TV({ msg: '{t}: «{r}» is a reserved name', vars: { t: plgShow(t), r: '사용자 단계' } }));
    else if(!PLG_TITLES.includes(plTk(t)) && !(x.instr || '').trim()) bad(x.id, TV({ msg: '{t}: a custom stage needs an instruction', vars: { t: plgShow(t) } }));
    if(G.nodes.filter(y => y.title === t).length > 1) bad(x.id, TV({ msg: '{t}: the same stage name appears twice', vars: { t: plgShow(t) } }));
    if(!/^[A-Za-z0-9][A-Za-z0-9_-]{0,59}$/.test(x.agent || '')) bad(x.id, TV({ msg: '{t}: the agent name is not valid', vars: { t: plgShow(t) } }));
    if(x.model && !PLG_MODELS.includes(x.model)) bad(x.id, TV({ msg: '{t}: the model is not valid', vars: { t: plgShow(t) } }));
    if(x.skill && !/^[a-z0-9-]{1,60}$/.test(x.skill)) bad(x.id, TV({ msg: '{t}: the skill name is not valid', vars: { t: plgShow(t) } }));
    if(!int(x.retry, 0, 3)) bad(x.id, TV({ msg: '{t}: retries: 0–3', vars: { t: plgShow(t) } }));
    if(!int(x.parallel, 1, 16)) bad(x.id, TV({ msg: '{t}: parallel runs: 1–16', vars: { t: plgShow(t) } }));
    if(x.gate && (x.gate.length > 200 || /[\r\n]/.test(x.gate))) bad(x.id, TV({ msg: '{t}: gate: one line, up to 200 characters', vars: { t: plgShow(t) } }));
    if(x.instr && x.instr.length > 1000) bad(x.id, TV({ msg: '{t}: instruction: up to 1000 characters', vars: { t: plgShow(t) } }));
    if(x.fanout && !order.slice(0, pos[x.id] || 0).some(id => plgNode(G, id).produces)) bad(x.id, TV({ msg: '{t}: fanout needs a produces stage before it', vars: { t: plgShow(t) } }));
    if(x.onlyOnJump && pos[x.id] === 0) bad(x.id, TV({ msg: '{t}: the first stage cannot be onlyOnJump', vars: { t: plgShow(t) } }));
  });
  G.loops.forEach(l => {
    const a = plgNode(G, l.from), b = plgNode(G, l.to);
    if(!a || !b) return;
    if(!(pos[b.id] < pos[a.id])) bad(a.id, TV({ msg: '{t}: a loop-back can only go to an earlier stage', vars: { t: plgShow(a.title) } }));
    if(!(Number.isInteger(l.max) && l.max >= 1 && l.max <= 5)) bad(a.id, TV({ msg: '{t}: loop-back max: 1–5', vars: { t: plgShow(a.title) } }));
    if(l.then){ const th = G.nodes.find(y => y.title === l.then); if(!th || !(pos[th.id] > pos[a.id])) bad(a.id, TV({ msg: '{t}: the «then» stage must come later', vars: { t: plgShow(a.title) } })); }
  });
  return { order, errs };
}
// «Arrange»: chain left→right, `cols` stages per row (snake: each row again left→right, the flow drops to the next row's
// first stage); nodes outside the chain go below. Rows leave room for one loop-back lane per loop plus the row connector.
function plgRowH(G){ return Math.max(PLG_H, ...G.nodes.map(n => plgH(G, n.id))) + 62 + PLG_LANE * Math.max(1, G.loops.length); }
function plgLayout(G, gx, cols){
  const { order } = plgOrder(G), rest = G.nodes.filter(n => !order.includes(n.id)), g = gx || PLG_GX;
  const per = cols || order.length || 1, rh = plgRowH(G);
  let x = PLG_X0;
  // Centre each node on its row's middle line: flow edges join side midpoints, so top-aligned nodes of different heights
  // (a gate line makes a stage taller) bent every arrow.
  const mh = order.reduce((m, id, i) => { const r = Math.floor(i / per); m[r] = Math.max(m[r] || 0, plgH(G, id)); return m; }, {});
  order.forEach((id, i) => { if(i % per === 0) x = PLG_X0; const r = Math.floor(i / per), n = plgNode(G, id); n.ui = Object.assign({}, n.ui, { x, y: PLG_Y0 + r * rh + Math.round((mh[r] - plgH(G, id)) / 2) }); x += plgW(G, id) + g; });   // keeps ui.color
  const y = PLG_Y0 + Math.ceil(Math.max(1, order.length) / per) * rh;
  x = PLG_X0;
  rest.forEach(n => { n.ui = Object.assign({}, n.ui, { x, y }); x += plgW(G, n.id) + g; });
}
// Display-only push: in each row (same top or middle line ±8) a node that overlaps its left neighbour (content-wide nodes on old 248px spacing)
// moves right to keep a 28px gap, cascading. Returns {id: x} for moved nodes; G is not changed (no dirty draft).
function plgRows(G){
  const N = G.nodes.filter(n => n.ui).slice().sort((a, b) => a.ui.y - b.ui.y || a.ui.x - b.ui.x), rows = [];
  const cy = n => n.ui.y + plgH(G, n.id) / 2;   // rows by middle line: plgLayout centres nodes, so tops differ
  N.forEach(n => { const r = rows[rows.length - 1]; if(r && (Math.abs(n.ui.y - r[0].ui.y) <= 8 || Math.abs(cy(n) - cy(r[0])) <= 8)) r.push(n); else rows.push([n]); });
  return rows;
}
function plgPush(G){
  const out = {};
  plgRows(G).forEach(r => {
    r.sort((a, b) => a.ui.x - b.ui.x);
    let edge = -Infinity;
    r.forEach(n => { const x = Math.max(n.ui.x, edge); if(x !== n.ui.x) out[n.id] = x; edge = x + plgW(G, n.id) + 28; });
  });
  return out;
}
// Display-only middle-line alignment (same rows as plgPush): y = row top + (tallest - h) / 2, so flow arrows stay straight
// when measured heights change at runtime (result/gate lines). Returns {id: y} for moved nodes; G is not changed.
function plgAlign(G){
  const out = {};
  plgRows(G).forEach(r => {
    if(r.length < 2) return;
    const top = Math.min(...r.map(n => n.ui.y)), mh = Math.max(...r.map(n => plgH(G, n.id)));
    r.forEach(n => { const y = top + Math.round((mh - plgH(G, n.id)) / 2); if(y !== n.ui.y) out[n.id] = y; });
  });
  return out;
}
// Stages per row for canvas width `w`: all on one row if that fits at zoom ≥ zmin, else as many as fit at 100%.
// `ws` = the chain's node widths (optional; PLG_W each); a wrapped row is sized by the widest node.
function plgCols(n, w, zmin, ws){
  const one = 2 * PLG_X0 + plgSumW(n, ws) + (n - 1) * plgGap(n, w, ws), mw = ws && ws.length ? Math.max(...ws) : PLG_W;
  return one * zmin <= w ? n : Math.max(1, Math.floor((w - 2 * PLG_X0 + 28) / (mw + 28)));
}
function plgSumW(n, ws){ return ws ? ws.reduce((s, v) => s + v, 0) : n * PLG_W; }
// Gap that fits `n` chain nodes into width `w` at 100% (28..PLG_GX); the caller zooms out only if even 28 does not fit.
function plgGap(n, w, ws){ return n < 2 ? PLG_GX : Math.max(28, Math.min(PLG_GX, Math.floor((w - 2 * PLG_X0 - plgSumW(n, ws)) / (n - 1)))); }
// Edge geometry from side midpoints (flow: right -> left, loop-back: bottom -> bottom, dipping below both boxes); wa = a's width.
function plgFlowPath(a, b, wa, ha, hb){
  const x1 = a.x + (wa || PLG_W), y1 = a.y + (ha || PLG_H) / 2, x2 = b.x, y2 = b.y + (hb || PLG_H) / 2, d = Math.max(40, Math.abs(x2 - x1) / 2);
  if(b.y > a.y + (ha || PLG_H) / 2 && x2 < x1){   // row wrap: out right, down to just above the next row, back left, into its left side
    const cy = b.y - 40;   // ⚠above the live label (48d .plls, top-27..top-5)
    return 'M' + x1 + ' ' + y1 + ' H' + (x1 + 16) + ' V' + cy + ' H' + (x2 - 16) + ' V' + y2 + ' H' + x2;
  }
  return 'M' + x1 + ' ' + y1 + ' C' + (x1 + d) + ' ' + y1 + ' ' + (x2 - d) + ' ' + y2 + ' ' + x2 + ' ' + y2;
}
// Loop-backs: fewest bends. Default = U (2 bends): down from the source's bottom, along a
// lane below both nodes and anything in between, up into the target's bottom. Only when a U's vertical would cross a box
// (e.g. target in an upper row with a node under it) the lane goes via the left gutter. Works on free-placed nodes too.
// Lanes never share y within PLG_LANE over overlapping spans and keep 12px off any box (label pills, status pills).
function plgLoopLanes(G){
  const box = n => n && n.ui && { x: n.ui.x, y: n.ui.y, w: plgW(G, n.id), h: plgH(G, n.id) }, pt = id => box(plgNode(G, id)), out = {}, taken = [], N = G.nodes.map(box);
  const ls = G.loops.map((l, i) => ({ i, a: pt(l.from), b: pt(l.to) })).filter(x => x.a && x.b);
  ls.sort((p, q) => Math.abs(p.a.y - p.b.y) - Math.abs(q.a.y - q.b.y) || Math.abs(p.a.x - p.b.x) - Math.abs(q.a.x - q.b.x) || p.i - q.i);
  const vhit = (x, y0, y1) => N.some(u => x > u.x && x < u.x + u.w && Math.min(y0, y1) < u.y + u.h && Math.max(y0, y1) > u.y);
  const free = (y, lo, hi) => {
    let v = y;
    for(let g = 0; g < 60; g++){
      const n = N.find(u => u.x < hi && u.x + u.w > lo && u.y < v + 12 && u.y + u.h > v - 12);
      const t = !n && taken.find(l => Math.abs(l.y - v) < PLG_LANE && l.lo < hi + 30 && l.hi > lo - 30);
      if(n) v = n.y + n.h + PLG_LANE; else if(t) v = t.y + PLG_LANE; else break;
    }
    return v;
  };
  const take = (y, lo, hi) => { taken.push({ y, lo, hi }); return y; };
  ls.forEach((x, k) => {
    const x1 = x.a.x + x.a.w / 2 + 14 * k, x2 = x.b.x + x.b.w / 2 - 14 * k, lo = Math.min(x1, x2), hi = Math.max(x1, x2);
    const y = free(Math.max(x.a.y + x.a.h, x.b.y + x.b.h) + PLG_LANE, lo, hi);
    if(!vhit(x1, x.a.y + x.a.h, y) && !vhit(x2, x.b.y + x.b.h, y)){ out[x.i] = { k, y: take(y, lo, hi) }; return; }
    const gx = PLG_X0 - 14 - 8 * k;
    out[x.i] = { k, y: take(free(x.a.y + x.a.h + PLG_LANE, gx, x1), gx, x1), y2: take(free(x.b.y + x.b.h + PLG_LANE, gx, x2), gx, x2), gx };
  });
  return out;
}
function plgLoopPath(a, b, lane, wa, wb, ha, hb){
  const k = lane.k, x1 = a.x + (wa || PLG_W) / 2 + 14 * k, x2 = b.x + (wb || PLG_W) / 2 - 14 * k, y1 = a.y + (ha || PLG_H), y2 = b.y + (hb || PLG_H), ly = lane.y, r = 8;
  if(lane.y2 != null){
    const gx = Math.max(4, lane.gx);
    return { d: 'M' + x1 + ' ' + y1 + ' V' + ly + ' H' + gx + ' V' + lane.y2 + ' H' + x2 + ' V' + y2, lx: (gx + x1) / 2, ly };
  }
  const dir = x2 < x1 ? -1 : 1;
  return { d: 'M' + x1 + ' ' + y1 + ' L' + x1 + ' ' + (ly - r) + ' Q' + x1 + ' ' + ly + ' ' + (x1 + dir * r) + ' ' + ly
    + ' L' + (x2 - dir * r) + ' ' + ly + ' Q' + x2 + ' ' + ly + ' ' + x2 + ' ' + (ly - r) + ' L' + x2 + ' ' + y2,
    lx: (x1 + x2) / 2, ly };
}
// Remove a stage and re-link its neighbours (p -> x -> q becomes p -> q); loops touching it go too.
function plgRemove(G, id){
  const pin = G.flow.find(e => e[1] === id), pout = G.flow.find(e => e[0] === id), gone = plgNode(G, id);
  G.flow = G.flow.filter(e => e[0] !== id && e[1] !== id);
  if(pin && pout) G.flow.push([pin[0], pout[1]]);
  G.loops = G.loops.filter(l => l.from !== id && l.to !== id);
  G.loops.forEach(l => { if(gone && l.then === gone.title) delete l.then; });
  G.nodes = G.nodes.filter(n => n.id !== id);
}
// Connect: flow a -> b replaces a's outgoing and b's incoming flow edge; loop a -> b replaces a's loop-back.
function plgConnect(G, kind, a, b){
  if(!a || !b || a === b) return false;
  if(kind === 'loop'){
    const old = G.loops.find(l => l.from === a);
    G.loops = G.loops.filter(l => l.from !== a);
    G.loops.push(Object.assign({ from: a, to: b, max: old ? old.max : 1 }, old && old.then ? { then: old.then } : {}));
    return true;
  }
  G.flow = G.flow.filter(e => e[0] !== a && e[1] !== b && !(e[0] === b && e[1] === a));
  G.flow.push([a, b]);
  return true;
}
// New stage from the palette: placed at (x, y) and appended after the chain's tail so the graph stays one chain.
function plgAdd(G, title, agent, x, y){
  const { order } = plgOrder(G), tail = order[order.length - 1];
  const id = 'n' + (++G.seq);
  G.nodes.push({ id, title, agent: agent || 'general-purpose', ui: { x: Math.round(x), y: Math.round(y) } });
  if(tail) G.flow.push([tail, id]);
  return id;
}
// «+ Stage»: new stage right after `after` (else the chain's tail), linked into the chain; later chain nodes shift right to make room.
// Reorder: only on a whole single chain; the flow is rebuilt from the new order.
// Loop-backs reference node ids, so they stay on the same stages (plgCheck flags a goto that is no longer earlier).
function plgChain(G, order){ G.flow = order.slice(1).map((id, i) => [order[i], id]); }
function plgLine(G){ const r = plgOrder(G); return r.errs.length || r.order.length !== G.nodes.length ? null : r.order; }
function plgMove(G, id, dir){
  const o = plgLine(G), i = o ? o.indexOf(id) : -1, j = i + dir;
  if(i < 0 || j < 0 || j >= o.length) return false;
  const A = plgNode(G, o[i]).ui, B = plgNode(G, o[j]).ui, ax = A.x, ay = A.y;   // swap places on the canvas too (colour stays)
  A.x = B.x; A.y = B.y; B.x = ax; B.y = ay;
  [o[i], o[j]] = [o[j], o[i]];
  plgChain(G, o);
  return true;
}
// Drop on a flow edge a -> b (n8n style): take `id` out of its place (neighbours joined) and put it between a and b.
function plgInsertAt(G, id, a, b){
  const o = plgLine(G);
  if(!o || id === a || id === b || !G.flow.some(e => e[0] === a && e[1] === b)) return false;
  const r = o.filter(x => x !== id);
  r.splice(r.indexOf(a) + 1, 0, id);
  plgChain(G, r);
  return true;
}
// Path "d" (M/L/H/V/Q/C) -> polyline points (curves sampled) for hit-testing.
function plgPathPts(d){
  const pts = []; let cur = [0, 0];
  (String(d).match(/[MLHVQC][^MLHVQC]*/g) || []).forEach(seg => {
    const c = seg[0], v = seg.slice(1).trim().split(/[\s,]+/).filter(Boolean).map(Number);
    if(c === 'C' || c === 'Q'){
      const P = c === 'C' ? [cur, [v[0], v[1]], [v[2], v[3]], [v[4], v[5]]] : [cur, [v[0], v[1]], [v[2], v[3]]];
      for(let k = 1; k <= 16; k++){
        const t = k / 16, m = (p, q) => [p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t];
        let L = P; while(L.length > 1){ const nx = []; for(let i = 0; i + 1 < L.length; i++) nx.push(m(L[i], L[i + 1])); L = nx; }
        pts.push(L[0]);
      }
      cur = pts[pts.length - 1];
      return;
    }
    cur = c === 'H' ? [v[0], cur[1]] : c === 'V' ? [cur[0], v[0]] : [v[0], v[1]];
    pts.push(cur);
  });
  return pts;
}
// Flow edge index nearest to canvas point p within `tol`, skipping edges that touch `skip` (the dragged node); -1 if none.
function plgEdgeAt(G, p, skip, tol){
  let best = -1, bd = tol;
  G.flow.forEach(([a, b], i) => {
    if(a === skip || b === skip) return;
    const A = plgNode(G, a), B = plgNode(G, b);
    if(!A || !B) return;
    const q = plgPathPts(plgFlowPath(A.ui, B.ui, plgW(G, a), plgH(G, a), plgH(G, b)));
    for(let k = 0; k + 1 < q.length; k++){
      const [x1, y1] = q[k], [x2, y2] = q[k + 1], dx = x2 - x1, dy = y2 - y1, L2 = dx * dx + dy * dy;
      const t = L2 ? Math.max(0, Math.min(1, ((p.x - x1) * dx + (p.y - y1) * dy) / L2)) : 0;
      const d = Math.hypot(p.x - x1 - t * dx, p.y - y1 - t * dy);
      if(d <= bd){ bd = d; best = i; }
    }
  });
  return best;
}
function plgInsert(G, title, after){
  const { order } = plgOrder(G), at = after && order.includes(after) ? after : order[order.length - 1];
  const prev = at ? plgNode(G, at) : null, dx = PLG_W + PLG_GX, id = 'n' + (++G.seq), px = prev ? prev.ui.x + plgW(G, at) + PLG_GX : 0;
  order.slice(order.indexOf(at) + 1).forEach(k => { const n = plgNode(G, k); n.ui = { x: n.ui.x + dx, y: n.ui.y }; });
  G.nodes.push({ id, title, agent: 'general-purpose', ui: prev ? { x: px, y: prev.ui.y } : { x: PLG_X0, y: PLG_Y0 } });
  if(prev){ const out = G.flow.find(e => e[0] === at); if(out) out[0] = id; G.flow.push([at, id]); }
  return id;
}
// Common checkable pipeline rules: [screen label, English line stored in `rules`].
const PLG_RULES = [['No server restarts', 'Never restart servers or services.'], ['No commit / push', 'Never commit or push.'],
  ['No whole-file writes (Edit only)', 'Edit existing files with small replacements only; never rewrite a whole file.'],
  ['No new dependencies', 'Do not add new dependencies.'], ['Tests required', 'Every change needs a test.']];
// rules text -> {on: [indices of PLG_RULES lines present], free: the other lines}; join is the inverse (common lines first).
// `list` defaults to PLG_RULES; the pane adds «Follow <rule file> in the repo.» rows (plRuleList).
function plgRulesSplit(txt, list){
  const L = list || PLG_RULES, lines = String(txt || '').split('\n'), on = [];
  const free = lines.filter(l => { const i = L.findIndex(r => r[1] === l.trim()); if(i < 0) return true; if(!on.includes(i)) on.push(i); return false; });
  return { on: on.sort((a, b) => a - b), free: free.join('\n').trim() };
}
function plgRulesJoin(on, free, list){
  return (list || PLG_RULES).filter((r, i) => on.includes(i)).map(r => r[1]).concat(String(free || '').trim() ? [String(free).trim()] : []).join('\n');
}
// Stage family for node/palette colour, so diagram areas read apart; unknown title = custom.
const PLG_FAM = { 설계: 'plan', 트리아지: 'und', 재현: 'und', 원인: 'und', 구현: 'build', 수정: 'build',
  검증: 'check', 회귀: 'check', 재검증: 'check', '최종 검증': 'check', '라이브 검증': 'check', 리뷰: 'review', 'AI 설정 점검': 'review', '프롬프트 검증': 'check' };
// Catalog stages take their group's family, one hue per group (PLG_CAT = {ko title: group}, filled by 48d plPalette from GET /api/pipelines).
const PLG_GFAM = { research: 'rsch', understand: 'und', design: 'plan', build: 'build', test: 'test', quality: 'qual', security: 'sec', consistency: 'cons', verify: 'check', review: 'review', release: 'rel', ops: 'ops' }; let PLG_CAT = {}; const PLG_FAMS = [...new Set(Object.values(PLG_GFAM).concat('check', 'cust'))];
// Group first so a catalog stage matches its catalog row; PLG_FAM covers pages that never loaded the catalog.
function plgFam(title){ const h = k => Object.prototype.hasOwnProperty.call(PLG_CAT, k) || Object.prototype.hasOwnProperty.call(PLG_FAM, k);
  const k = h(title) ? title : plgBase(title); return PLG_GFAM[PLG_CAT[k]] || PLG_FAM[k] || 'cust'; }
// User colour = stage.ui.color; ⚠regex-checked before it reaches a style attribute.
function plgColor(n){ const c = n && n.ui && n.ui.color; return /^#[0-9a-f]{6}$/.test(c || '') ? c : ''; }
function plgPfc(n){ const c = plgHue(n); return c ? ' style="--pfc:' + c + '"' : ''; }
// «Stage catalog» (GET /api/pipelines `catalog`, sidereus/stage_catalog.py): {groups:[{id, en}], items:[{id, group, title:{ko, en}, role|agent,
// model, instr, gate, gateHint, asserts, loop:{to:[titles], max}, tools:[{id, bin, install, net, avail}]}]}. The stage title written is title.ko.
// ⚠Exact id/title only (no plgBase): a typed «Verify 2» must stay a custom stage, not resolve to «Verify» and be renumbered.
function plgTpl(cat, key){ return ((cat && cat.items) || []).find(t => t.id === key || (t.title || {}).ko === key) || null; }
// Node display colour: its own ui.color only (catalog stages take their group's family colour through plgFam). ⚠Display only.
function plgHue(n){ return plgColor(n); }
// Add catalog template `tpl` (at = {x, y} drop point -> chain tail, else a node id to insert after); ctx = {roles, dt} from GET /api/pipelines.
// The gate is prefilled; a loop-back is wired only to an earlier node. Titles stay unique: an in-use template adds «<title> 2».
function plgAddTpl(G, tpl, ctx, at){
  const ok = a => typeof a === 'string' && /^[A-Za-z0-9][A-Za-z0-9_-]{0,59}$/.test(a), t0 = tpl && tpl.title && tpl.title.ko, t = t0 && plgFreeTitle(G, t0);
  if(!t) return null;
  const id = at && typeof at === 'object' ? plgAdd(G, t, '', at.x, at.y) : plgInsert(G, t, at), n = plgNode(G, id);
  const ra = tpl.role && ((ctx || {}).roles || {})[tpl.role];
  n.agent = ok(ra) ? ra : ok(tpl.agent) ? tpl.agent : 'general-purpose';
  if(tpl.model) n.model = tpl.model;
  const dt = t !== t0 && ((ctx || {}).dt || {})[t0];   // ⚠a copy of a recommended title gets no runner default: carry it as the task
  if(tpl.instr || dt) n.instr = tpl.instr || dt;
  if(tpl.gate) n.gate = tpl.gate;
  const order = plgOrder(G).order, i = order.indexOf(id), before = i > 0 ? order.slice(0, i) : [];
  const to = tpl.loop && before.slice().reverse().find(x => tpl.loop.to.includes(plgNode(G, x).title));
  if(to){ plgConnect(G, 'loop', id, to); G.loops.find(l => l.from === id).max = tpl.loop.max; }
  return id;
}
// Run guards saved as `guards` (validated by sidereus/pipeline_schema.py): requireGates = titles of graded stages that must pass
// their gate, maxLoopBacks 1..10. Titles that left the graph or lost their gate drop out; {} = no guards.
// modes = GET /api/pipelines `gate_modes` (schema GATE_MODES regexes): only a gate that records evidence can be required.
function plgGraded(G, modes){ return G.nodes.filter(n => { const g = String(n.gate || '').trim(); return g && (!modes || modes.some(rx => new RegExp(rx).test(g))); }); }
function plgGuards(G, modes){
  const g = G.guards || {}, graded = plgGraded(G, modes).map(n => n.title), out = {};
  const rq = (g.requireGates || []).filter(t => graded.includes(t));
  if(rq.length) out.requireGates = graded.filter(t => rq.includes(t));
  if(Number.isInteger(g.maxLoopBacks) && g.maxLoopBacks >= 1 && g.maxLoopBacks <= 10) out.maxLoopBacks = g.maxLoopBacks;
  return out;
}
// Why a typed stage name is refused, or '' (trimmed `t`); ⚠same rules as sidereus/pipeline.py title_err.
function plTitleErr(G, n, t){
  if(!t) return T('Stage name is empty');
  if(t.length > 24) return T('Stage name: at most 24 characters');
  if(/[\/\]|\r\n]/.test(t)) return T('Stage name cannot contain / ] |');
  return G.nodes.some(x => x !== n && x.title === t) ? T('A stage with that name exists') + ': ' + t : '';
}
// title -> runner phase: recommended titles map to themselves, others take "custom stage 1..12" (Korean phase names) in stage order.
// ⚠Mirror of the runner's phaseSlots (.claude/workflows/pipeline.js) — keep both in step (tests/test_pipeline_graph.py).
function plgSlots(stages){
  const m = {}; let n = 0;
  (stages || []).forEach(s => { m[s.title] = PLG_TITLES.includes(plTk(s.title)) ? plTk(s.title) : '사용자 단계 ' + (++n); });
  return m;
}
