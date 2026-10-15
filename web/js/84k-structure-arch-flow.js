// ── Structure «Architecture» view: agent-drawn process flows (/api/arch `flows`, verified per step by sidereus/arch_flow.py) ──────
// A picked flow replaces the module diagram with a sequence diagram (81h mmdSeq*) and the edge list with step rows.
// ⚠Evidence is file:line:symbol only; code opens on click through 81 strPopOpenRel, like the edge evidence in 84j.
const ARCH_FLOW_KIND = { http: 'HTTP', cli: 'CLI', job: 'Job', event: 'Event', hook: 'Hook', mcp: 'MCP' };
function archFlowKind(k){ k = String(k || ''); return Object.prototype.hasOwnProperty.call(ARCH_FLOW_KIND, k) ? T(ARCH_FLOW_KIND[k], 'arch flow kind') : k; }
// Pure: usable flows of map d and the index of the one picked for project p (-1 = module map; a flow gone from a rebuilt map falls back).
function archFlowAt(d, p){
  const fls = (d && Array.isArray(d.flows) ? d.flows : []).filter(f => f && f.id != null && Array.isArray(f.steps));
  const q = ARCH.flow, fi = q && q.p === p ? fls.findIndex(f => String(f.id) === String(q.id)) : -1;
  return { fls, fi };
}
// The picked flow of the project on screen, or null.
function archFlowCur(p){ const a = archFlowAt(ARCH.cache[p], p); return a.fi >= 0 ? a.fls[a.fi] : null; }
// Pure: «Flows» select — «Module diagram» + every flow name with ✓ (all steps proven) / ✗. Names are agent data: esc, never T().
// id = lit flow on the map (or the sequence one); then «Clear flow» + «Sequence diagram» (pressed = seq, the sequence view is open).
function archFlowPick(fls, id, seq){
  if(!fls || !fls.length) return '';
  const on = id != null && id !== '' && fls.some(f => String(f.id) === String(id));
  return '<label class=archfl>' + esc(T('Flows')) + ' <select data-arfl><option value="">' + esc(T('Module diagram')) + '</option>'
    + fls.map(f => '<option value="' + esc(f.id) + '"' + (on && String(f.id) === String(id) ? ' selected' : '') + '>' + esc((f.ok ? '✓ ' : '✗ ') + (f.name || f.id)) + '</option>').join('')
    + '</select></label>' + (on ? '<button type=button class="archfbt' + (seq ? ' on' : '') + '" data-arseq="' + esc(id) + '" aria-pressed=' + (seq ? 'true' : 'false') + '>' + esc(T('Sequence diagram')) + '</button>'
    + '<button type=button class=archfbt data-arlitx>' + esc(T('Clear flow')) + '</button>'
    + (seq ? '' : '<button type=button class=archfbt data-arlitn>' + esc(T('Next lit')) + '</button><span class=archlitc data-arlitc role=status hidden></span>') : '');   // count filled by archLitCount
}
// Pure: entry nodes of the layered overview — one per (kind, label), linked to each flow's first module (steps[0].from).
// Flows whose first module is missing or hidden (tests off) add nothing. ⚠Keys are 'en<n>', never 'm<i>': clicks and badges index mods by key.
function archFlowEntries(d, mods, tests){
  const ix = {}, vis = {}, by = {}, out = [], own = Object.prototype.hasOwnProperty;
  (mods || []).forEach((m, i) => { if(m && m.id != null){ ix[m.id] = i; if(tests || !archIsTest(m)) vis[m.id] = 1; } });   // last index wins, as archBandSrc
  (d && Array.isArray(d.flows) ? d.flows : []).forEach(f => {
    const s0 = f && f.id != null && Array.isArray(f.steps) && f.steps[0], to = s0 && s0.from;
    if(to == null || !own.call(vis, to)) return;
    const en = f.entry || {}, kind = String(en.kind || ''), label = String(en.label || ''), k = kind + '\u0001' + label;
    if(!kind && !label) return;   // no entry: nothing to draw
    let e = own.call(by, k) ? by[k] : null;
    if(!e) out.push(e = by[k] = { k: 'en' + out.length, kind, label, to: new Set(), flows: [] });
    e.to.add(ix[to]); e.flows.push(String(f.id));
  });
  return out;
}
// Pure: module display name; own keys only, so an id like «constructor» never reads the prototype.
function archFlowName(names, id){ id = String(id == null ? '' : id); return names && Object.prototype.hasOwnProperty.call(names, id) && names[id] ? String(names[id]) : id; }
// Pure: proven step count.
function archFlowRate(fl){ const s = (fl && fl.steps) || []; return { a: s.filter(x => x && x.ok).length, b: s.length }; }
// Pure: mermaid source. Participants pN in first-seen order; item 0 = entry -> first module, step i = item i + 1.
// autonumber comes after the entry arrow so the diagram numbers match the step rows (step i = i + 1).
// ⚠Labels lose [<>#\r\n;]: mmdSeqParse decodes #NN; entities and splits on lines, so these would change the drawing.
function archFlowSrc(fl, names){
  const cl = s => String(s == null ? '' : s).replace(/[<>#\r\n;]/g, ' ').trim();
  const st = (fl && fl.steps) || [], ix = {}, ln = ['sequenceDiagram', 'actor e as ' + (cl(fl && fl.entry && fl.entry.label) || 'entry')];
  const pid = id => { id = String(id == null ? '' : id); if(!(id in ix)){ ix[id] = 'p' + Object.keys(ix).length; ln.push('participant ' + ix[id] + ' as ' + (cl(archFlowName(names, id)) || ix[id])); } return ix[id]; };
  st.forEach(s => { pid(s.from); pid(s.to); });
  if(st.length) ln.push('e->>' + pid(st[0].from) + ':');
  ln.push('autonumber');
  st.forEach(s => ln.push(pid(s.from) + (s.ok ? '->>' : '-->>') + pid(s.to) + ': ' + cl(s.label)));
  return ln.join('\n');
}
// Pure: parsed flow with participant names over 22 chars cut to 21 + '…' (full name kept in p.full for the box <title>),
// and message labels over 20 chars wrapped at spaces, then after '.' / before '(' inside long words (the step list keeps the one-line label).
function archFlowGraph(fl, names){
  const g = mmdSeqParse(archFlowSrc(fl, names)), W = 20;
  if(!g.ok) return g;
  g.parts.forEach(p => { const c = Array.from(String(p.label)); if(c.length > 22){ p.full = p.label; p.label = c.slice(0, 21).join('').trimEnd() + '…'; } });
  const wrap = t => { const o = [];
    String(t).split(/\s+/).filter(Boolean).forEach(w => (w.length > W ? w.split(/(?<=\.)(?=.)|(?=\()/) : [w]).forEach((x, k) => { const l = o.length - 1, sp = k ? '' : ' ';
      if(l >= 0 && (o[l] + sp + x).length <= W) o[l] += sp + x; else o.push(x); }));
    return o.join('\n'); };
  g.items.forEach(it => { if(it.k === 'msg' && it.label && it.label.length > W) it.label = wrap(it.label); });
  return g;
}
// Pure: tighter lifeline gaps than the md preview (labels still widen them); self-loop labels count in the total width.
function archFlowLay(g){ return mmdSeqLayout(g, { tight: 1 }); }
// Sequence SVG in tag mode (messages carry data-i), scaled to the pane down to 0.75, then the pane scrolls; '' when it cannot be drawn.
function archFlowSvg(fl, names, fi){
  try{
    const g = archFlowGraph(fl, names);
    if(g.ok) return mmdSeqSvg(g, archFlowLay(g), 'af' + fi, { tag: 1, fit: 0.75 });
  }catch(e){ if(typeof softErr === 'function') softErr('archflow', e); }
  return '';
}
// After paint: failed steps get .archfx and an SVG <title> with the gate's reason (text node, no markup).
// ⚠data-i = step index + 1: item 0 is the synthetic entry arrow.
function archFlowMark(svg, fl){
  if(!svg || !fl) return 0;
  let n = 0;
  ((fl.steps) || []).forEach((s, i) => {
    if(!s || s.ok) return;
    const g = svg.querySelector('g.mmdsqm[data-i="' + (i + 1) + '"]');
    if(!g) return;
    const t = document.createElementNS('http://www.w3.org/2000/svg', 'title');
    t.textContent = T('Not proven: {why}').replace('{why}', String(s.why || '?'));
    g.classList.add('archfx'); g.insertBefore(t, g.firstChild); n++;
  });
  return n;
}
// Pure: one step row — number, from → to, badges, label, then its evidence (84j archEvHtml).
function archFlowRow(s, names, i){
  const nm = id => archFlowName(names, id), why = T('Not proven: {why}').replace('{why}', String(s.why || '?'));
  return '<li class="arche archfs' + (s.ok ? '' : ' bad') + '"><button type=button class=archeb data-afs="' + i + '" title="' + esc(T('View code')) + '">'
    + '<span class=archen><em class=archio>' + (i + 1) + '</em><b>' + esc(nm(s.from)) + '</b><i>→</i><b>' + esc(nm(s.to)) + '</b></span>'
    + '<span class=archem>' + (s.est ? '<em class="archbg archest" title="' + esc(T('Evidence is inferred, not a direct reference')) + '">' + esc(T('estimate')) + '</em>' : '')
    + (s.ok ? '' : '<em class="archbg archbad" title="' + esc(why) + '">' + esc(T('Check failed')) + '</em>') + '</span>'
    + (s.label ? '<span class=archel>' + esc(s.label) + '</span>' : '') + '</button>' + archEvHtml([s.evidence], 'f' + i) + '</li>';
}
// Pure: body of the flow view — toolbar (picker, entry kind + label, proven count), diagram, step list.
function archFlowBody(fls, fi, names){
  const fl = fls[fi], r = archFlowRate(fl), en = fl.entry || {}, svg = archFlowSvg(fl, names, fi);
  return '<div class=archbody><div class=archmap><div class=archtop><div class="archbar on">' + archFlowPick(fls, fl.id, true)
    + (en.kind ? '<em class=archk>' + esc(archFlowKind(en.kind)) + '</em>' : '') + '<span class=archhint>' + esc(en.label || '') + '</span>'
    + '<span class="archfr' + (r.a < r.b ? ' bad' : '') + '">' + esc(T('{a}/{b} steps proven').replace('{a}', r.a).replace('{b}', r.b)) + '</span></div></div>'   // .archtop: sticky like the map's
    + '<div class=archfdg>' + (svg ? '<div class=mmd><div class=mmdv>' + svg + '</div></div>' : mmdBlock(archFlowSrc(fl, names))) + '</div></div>'
    + '<aside class=archside><div class=archsh><b>' + esc(fl.name || fl.id) + '</b><span>' + esc(T('Click for evidence · click evidence for code')) + '</span>'
    + '<button type=button class=archrf data-arf title="' + esc(T('Reload now')) + '">↻</button></div>'
    + '<ul class=archel-list>' + (fl.steps || []).map((s, i) => archFlowRow(s || {}, names, i)).join('') + '</ul></aside></div>';
}
// Open a step's evidence in the code popup (same call as 84j's [data-aev] handler).
function archFlowOpen(p, s){
  const ev = s && s.evidence;
  if(!ev || !ev.file) return false;
  strPopOpenRel(p, ev.file, parseInt(ev.line, 10) || 1, 80, ev.symbol || '');
  return true;
}
// Message or step-row click opens that step's code; evidence buttons inside a row stay with 84j's [data-aev] handler.
function archFlowClick(t){
  if(!t || !t.closest || strMode !== 'arch' || !t.closest('.archtab')) return false;
  const p = strOn[0] || '', fl = archFlowCur(p);
  if(!fl || t.closest('[data-aev]')) return false;
  const m = t.closest('.archfdg .mmdsqm[data-i]'), r = !m && t.closest('[data-afs]');
  const i = m ? +m.dataset.i - 1 : r ? +r.dataset.afs : -1;
  return archFlowOpen(p, (fl.steps || [])[i]);
}
// «Sequence diagram» toggles the sequence view of the lit flow; «Clear flow» clears the highlight and the sequence view.
function archFlowBtn(t){
  if(!t || !t.closest || strMode !== 'arch' || !t.closest('.archtab')) return false;
  const p = strOn[0] || '', b = t.closest('[data-arseq],[data-arlitx]');
  if(!b) return false;
  if(b.dataset.arseq == null){ ARCH.lit = null; ARCH.flow = null; }
  else { const id = b.dataset.arseq; ARCH.flow = ARCH.flow && ARCH.flow.p === p ? null : { p, id }; ARCH.lit = { p, flow: id }; }
  ARCH.op = ''; paintStruct();
  return true;
}
// Picker: lights the flow on the map (the map stays); inside the sequence view it switches that view; «Module diagram» clears both.
function archFlowSet(p, v){
  if(!v){ ARCH.lit = null; ARCH.flow = null; }
  else { ARCH.lit = { p, flow: v }; if(ARCH.flow && ARCH.flow.p === p) ARCH.flow = { p, id: v }; }
  ARCH.op = '';
}
// «Next lit» cycle position: last node key moved to, per project + flow; raf = pending off-screen recount.
const ARCH_LITGO = { p: '', f: '', k: '', raf: 0, t: 0 };
// Pure: lit node keys in path order — entry node(s) en<n>, then modules m<i> in step order (from, to), each once.
function archLitOrder(d, id, tests){
  const mods = (d && d.modules) || [], ix = {}, out = [], seen = new Set(), own = Object.prototype.hasOwnProperty;
  const add = k => { if(k && !seen.has(k)){ seen.add(k); out.push(k); } };
  mods.forEach((m, i) => { if(m && m.id != null) ix[m.id] = 'm' + i; });   // last index wins, as archLitSet
  const f = ((d && d.flows) || []).find(y => y && y.id != null && String(y.id) === String(id)), st = f && Array.isArray(f.steps) ? f.steps : [];
  const s0 = st[0] && st[0].from;
  if(s0 != null && own.call(ix, s0)) archFlowEntries(d, mods, !!tests).forEach(en => { if(en.flows.indexOf(String(id)) >= 0) add(en.k); });
  st.forEach(s => { if(s) [s.from, s.to].forEach(k => { if(k != null && own.call(ix, k)) add(ix[k]); }); });
  return out;
}
// Pure: key after cur in order, wrapping; first key when cur is not in it; '' for an empty order.
function archLitNext(order, cur){ const o = order || []; return o.length ? o[(o.indexOf(cur) + 1) % o.length] : ''; }
// Pure: rects (left/top/right/bottom) lying wholly outside the visible rect v.
function archOffCount(rects, v){ return (rects || []).filter(r => r.right <= v.left || r.left >= v.right || r.bottom <= v.top || r.top >= v.bottom).length; }
// Pure: toolbar line, '' when nothing is off-screen (the line hides).
function archLitText(n, m){ return m > 0 ? T('{n} lit · {m} off-screen').replace('{n}', n).replace('{m}', m) : ''; }
// Pure: .archmap scroll that centres rect r in the visible rect v (both viewport coordinates).
function archScrollAt(r, v, sl, st){
  return { left: Math.max(0, Math.round(sl + (r.left + r.right) / 2 - (v.left + v.right) / 2)),
    top: Math.max(0, Math.round(st + (r.top + r.bottom) / 2 - (v.top + v.bottom) / 2)) };
}
// Visible part of .archmap in viewport coordinates: client box without scrollbars, minus the sticky .archtop.
function archViewRect(am){
  if(!am || !am.getBoundingClientRect) return null;
  const b = am.getBoundingClientRect(), top = am.querySelector('.archtop'), l = b.left + (am.clientLeft || 0), t = b.top + (am.clientTop || 0);
  return { left: l, top: t + (top ? top.offsetHeight : 0), right: l + am.clientWidth, bottom: t + am.clientHeight };
}
// Fill «{n} lit · {m} off-screen» from the painted .arlit nodes. ⚠Reads rects only: never moves the view.
function archLitCount(am){
  const c = am && am.querySelector && am.querySelector('[data-arlitc]');
  if(!c) return;
  const svg = am.querySelector('.archdg svg'), ns = svg ? Array.from(svg.querySelectorAll('[data-p].arlit')) : [], v = archViewRect(am);
  const t = v && ns.length ? archLitText(ns.length, archOffCount(ns.map(g => g.getBoundingClientRect()), v)) : '';
  c.textContent = t; c.hidden = !t;
}
// Press only: scroll .archmap (never the page or an ancestor) so node g is centred, then flash it.
function archLitGo(am, g){
  const v = archViewRect(am);
  if(!v || !g) return;
  const to = archScrollAt(g.getBoundingClientRect(), v, am.scrollLeft, am.scrollTop);
  if(am.scrollTo) am.scrollTo({ left: to.left, top: to.top, behavior: 'smooth' }); else { am.scrollLeft = to.left; am.scrollTop = to.top; }
  g.classList.remove('arflash'); void g.getBoundingClientRect(); g.classList.add('arflash');   // reflow restarts the animation on a repeat press
  clearTimeout(ARCH_LITGO.t); ARCH_LITGO.t = setTimeout(() => g.classList.remove('arflash'), 1100);   // an older timer would cut a repeat flash short
}
// «Next lit»: next drawn lit node in path order (keys missing from this view are skipped).
function archLitGoBtn(t){
  if(!t || !t.closest || strMode !== 'arch' || !t.closest('.archtab')) return false;
  const b = t.closest('[data-arlitn]'), p = strOn[0] || '', q = ARCH.lit;
  if(!b || !q || q.p !== p) return false;
  const am = b.closest('.archmap'), svg = am && am.querySelector('.archdg svg'), G = ARCH_LITGO, f = String(q.flow);
  if(!svg) return true;
  const node = k => svg.querySelector('[data-p="' + k + '"]');   // keys are m<i> / en<n>: no quoting needed
  const k = archLitNext(archLitOrder(ARCH.cache[p], f, !!ARCH.tests).filter(node), G.p === p && G.f === f ? G.k : '');
  if(!k) return true;
  G.p = p; G.f = f; G.k = k;
  archLitGo(am, node(k));
  return true;
}
document.addEventListener('click', ev => { if(!archFlowClick(ev.target) && !archFlowBtn(ev.target)) archLitGoBtn(ev.target); });
// ⚠scroll does not bubble: capture phase, one recount per frame.
document.addEventListener('scroll', ev => {
  const am = ev.target;
  if(ARCH_LITGO.raf || !am || !am.matches || !am.matches('.archtab .archmap') || !am.querySelector('[data-arlitc]')) return;
  ARCH_LITGO.raf = requestAnimationFrame(() => { ARCH_LITGO.raf = 0; archLitCount(am); });
}, true);
document.addEventListener('change', ev => {
  const s = ev.target;
  if(!s || !s.matches || !s.matches('.archtab select[data-arfl]')) return;
  archFlowSet(strOn[0] || '', s.value); paintStruct();
});
