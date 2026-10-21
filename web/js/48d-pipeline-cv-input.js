function plCvPt(E, cv, e){ const r = cv.getBoundingClientRect(); return { x: (e.clientX - r.left - E.view.x) / E.view.z, y: (e.clientY - r.top - E.view.y) / E.view.z }; }
function plTouch(){ PLS.diff = null; PLS.msg = ''; }
function plView(E){ return E.view || (E.view = { x: 0, y: 0, z: 1 }); }
// ⚠Any interaction ends first-open centring: a later re-fit (stage count, height) must not jump the camera.
function plNoFirst(){ const E = plCurEnt(); if(E) E.first = false; }
document.addEventListener('pointerdown', e => {
  if(e.button !== 0 || !e.target.closest || !e.target.closest('.plw')) return;
  plNoFirst();
  const gh = e.target.closest('[data-plgh]'), g = gh && gh.closest('.plgw'), side = g && g.querySelector('.plpan');
  if(side){ PLDRAG = { k: 'split', g, y0: e.clientY, h0: side.offsetHeight, h: side.offsetHeight }; e.preventDefault(); return; }
  const cv = e.target.closest('.plcv'), E = plCurEnt();
  if(!cv || !E || e.target.closest('.plcvt')) return;
  plView(E);
  const port = e.target.closest('[data-plport]'), node = e.target.closest('[data-plnode]'), edge = e.target.closest('[data-pledge]');
  if(node && plRO()){ E.sel = { k: 'n', id: node.dataset.plnode }; plPaint(); return; }   // borrowed (48h): select to read, never drag/connect
  if(port && node) PLDRAG = { k: 'edge', kind: port.dataset.plport, from: node.dataset.plnode, cv, E };
  else if(node){
    const n = plgNode(E.G, node.dataset.plnode), vu = plgNode(plVG(E), n.id).ui;   // drag from where it is shown
    E.pxF = plgPush(E.G); delete E.pxF[n.id]; E.pyF = plgAlign(E.G); delete E.pyF[n.id];   // ⚠freeze the others while dragging: their elements are not re-placed mid-drag
    PLDRAG = { k: 'node', n, el: node, cv, E, x0: e.clientX, y0: e.clientY, ux: vu.x, uy: vu.y, moved: false };
  }
  else if(edge){ const [k, i] = edge.dataset.pledge.split(':'); E.sel = { k, i: +i }; plPaint(); return; }
  else PLDRAG = { k: 'pan', cv, E, x0: e.clientX, y0: e.clientY, vx: E.view.x, vy: E.view.y, moved: false };
  e.preventDefault();
});
document.addEventListener('pointermove', e => {
  const D = PLDRAG;
  if(!D) return;
  if(D.k === 'split'){ D.h = plPanH(Math.max(1, D.h0 - (e.clientY - D.y0)), D.g.clientHeight); D.g.style.setProperty(PL_SPLIT.v, D.h + 'px'); plFitSoon(); return; }   // down = taller canvas
  const E = D.E;
  if(D.k === 'node'){
    const dx = (e.clientX - D.x0) / E.view.z, dy = (e.clientY - D.y0) / E.view.z;
    if(Math.abs(dx) + Math.abs(dy) > 3){ D.moved = true; E.touched = true; E.ctrd = false; }   // ⚠a later re-fit would jump the view under the user
    if(D.moved) D.n.ui = Object.assign({}, D.n.ui, { x: Math.round(D.ux + dx), y: Math.round(D.uy + dy) });   // keeps ui.color; a click saves nothing
    D.el.style.left = (D.moved ? D.n.ui.x : D.ux) + 'px'; D.el.style.top = (D.moved ? D.n.ui.y : D.uy) + 'px';   // under 3px it stays where shown
    const g = plRedrawEdges(E, D.cv);
    // drop target: a flow edge between two other stages under the pointer (10px, canvas units) is highlighted
    D.drop = D.moved ? plgEdgeAt(plVG(E), plCvPt(E, D.cv, e), D.n.id, 10 / E.view.z) : -1;
    const hp = g && D.drop >= 0 && g.querySelector('[data-pledge="f:' + D.drop + '"]');
    if(hp && hp.nextSibling) hp.nextSibling.classList.add('pldrop');
  } else if(D.k === 'pan'){
    if(Math.abs(e.clientX - D.x0) + Math.abs(e.clientY - D.y0) > 3) D.moved = true;
    E.view.x = D.vx + e.clientX - D.x0; E.view.y = D.vy + e.clientY - D.y0; E.touched = true; E.ctrd = false; plApplyView(E, D.cv);
  } else if(D.k === 'edge'){
    const a = plgNode(plVG(E), D.from).ui, p = plCvPt(E, D.cv, e);
    const aw = plgW(E.G, D.from), x1 = D.kind === 'loop' ? a.x + aw / 2 : a.x + aw, ah = plgH(E.G, D.from), y1 = D.kind === 'loop' ? a.y + ah : a.y + ah / 2;
    const t = D.cv.querySelector('.pltmp'); if(t){ t.setAttribute('d', 'M' + x1 + ' ' + y1 + ' L' + p.x + ' ' + p.y); t.setAttribute('class', 'pltmp ' + D.kind); }
  }
});
document.addEventListener('pointerup', e => {
  const D = PLDRAG;
  if(!D) return;
  PLDRAG = null;
  if(D.k === 'split'){ lsSet(PL_SPLIT.key, String(Math.round(D.h))); return; }
  const E = D.E;
  if(D.k === 'node'){
    E.pxF = null; E.pyF = null;
    if(D.moved){ const px = plgPush(E.G); Object.keys(px).forEach(id => { plgNode(E.G, id).ui.x = px[id]; }); }   // a drag saves what is shown
    const f = D.moved && D.drop >= 0 && E.G.flow[D.drop];
    if(f && plgInsertAt(E.G, D.n.id, f[0], f[1])){ E.sel = { k: 'n', id: D.n.id }; E.laid = true; E.touched = false; plFit(E, D.cv, true); }   // re-flow like «Arrange»
    if(!D.moved && ((E.lt || {})[D.n.title] || {}).st === 'run'){ plNodeWork(D.n.title, D.el.getBoundingClientRect()); return; }   // lit ● node: no select, no repaint
    if(!D.moved) E.sel = { k: 'n', id: D.n.id }; else plTouch();
  }
  else if(D.k === 'pan'){ if(!D.moved) E.sel = null; }
  else if(D.k === 'edge'){
    const t = document.elementFromPoint(e.clientX, e.clientY), n = t && t.closest && t.closest('[data-plnode]');
    if(n && plgConnect(E.G, D.kind === 'loop' ? 'loop' : 'flow', D.from, n.dataset.plnode)){ E.sel = null; plTouch(); }
  }
  plPaint();
});
// Running node / overview row click → that stage's newest agent work log; several agents → a small picker. Metadata only.
let PLAPK = null;   // open picker {sid, list}
function plApkClose(){ const el = document.getElementById('plapk'); if(el) el.remove(); PLAPK = null; }
function plNodeWork(title, rc){
  const p = plCur(), lv = p && plViewRun(PLS.proj, p.name);   // same run the canvas shows
  plApkClose();
  if(!lv) return;
  const E = plCurEnt(), nd = E && E.G.nodes.find(x => x.title === title), L = lv.lt && lv.lt[title], pi = nd ? plPassSel(E, nd.id, L) : -1;
  const list = lv.pr ? plStageAgents(pi >= 0 ? { [title]: plPass(L, pi) } : lv.lt, title, Date.now()) : [];   // picked pass: its agents only
  if(list.length < 2) return plOpenWork(lv.sid, list.length ? list[0].tid : '');   // workflow run / main mark only: the session's work
  PLAPK = { sid: lv.sid, list };
  const el = document.createElement('div');
  el.id = 'plapk'; el.className = 'plapk'; el.setAttribute('role', 'menu');
  el.innerHTML = '<div class=plapkh>' + esc(title + ' · ' + TV({msg: 'Agents {n}', vars: {n: list.length}})) + '</div>' + list.map((a, i) => '<button class=plapki data-plapk="' + i + '" title="' + esc(plLabTip(a.lab)) + '"><span>'
    + esc(plLabTip(a.lab)) + '</span><i>' + esc((a.run === false ? T('done') : T('running', 'exec')) + ' · ' + ago(a.sec)) + '</i></button>').join('');
  el.style.left = Math.max(4, Math.min(rc.left, window.innerWidth - 344)) + 'px'; el.style.top = Math.round(rc.bottom + 4) + 'px';   // fixed: never scrolls the view
  document.body.appendChild(el);
}
document.addEventListener('click', e => {
  const b = PLAPK && e.target.closest && e.target.closest('[data-plapk]');
  if(!b) return;
  const a = PLAPK.list[+b.dataset.plapk], sid = PLAPK.sid;
  plApkClose();
  if(a) plOpenWork(sid, a.tid);
});
document.addEventListener('pointerdown', e => { if(PLAPK && !(e.target.closest && e.target.closest('#plapk'))) plApkClose(); }, true);   // ⚠pointerdown, not click: the opening gesture's click would close it at once
document.addEventListener('keydown', e => { if(PLAPK && e.key === 'Escape') plApkClose(); });
document.addEventListener('wheel', e => {
  const cv = e.ctrlKey && e.target.closest && e.target.closest('.plcv'), E = cv && plCurEnt();
  if(!E) return;
  e.preventDefault();
  const V = plView(E), r = cv.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top, z0 = V.z;
  const z = Math.max(0.4, Math.min(2, z0 * (e.deltaY < 0 ? 1.1 : 1 / 1.1)));
  E.view = { x: mx - (mx - V.x) * z / z0, y: my - (my - V.y) * z / z0, z }; E.touched = true; E.first = false; E.ctrd = false;
  plApplyView(E, cv);
  plZoomLabel(cv, z);
}, { passive: false });
function plDelSel(E){
  const s = E.sel;
  if(!s) return;
  if(s.k === 'n') plgRemove(E.G, s.id);
  else if(s.k === 'l') E.G.loops.splice(s.i, 1);
  else if(s.k === 'f') E.G.flow.splice(s.i, 1);
  E.sel = null; E.first = false; plTouch(); plPaint();
}
document.addEventListener('keydown', e => {
  if(mainView !== 'pipe' || (e.key !== 'Delete' && e.key !== 'Backspace')) return;
  if(e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
  if(e.target && e.target.closest && e.target.closest('.plnl')) return;   // ⚠48j stage-row click sets E.sel and keeps focus in the list: Backspace there deleted that stage
  const E = plCurEnt();
  if(E && E.sel && !plRO()){ e.preventDefault(); plDelSel(E); }
});
// Keyboard twin of the pointerdown selection above: same E.sel + plPaint, never fits/centres the view.
// ⚠Must run before 98-a11y's [data-kb] activator (preventDefault stops it): its click() is a no-op here (selection is on pointerdown) and SVG paths have no click().
document.addEventListener('keydown', e => {
  if((e.key !== 'Enter' && e.key !== ' ') || e.defaultPrevented || e.isComposing || e.keyCode === 229 || e.repeat) return;
  const t = e.target, E = plCurEnt();
  if(!E || !t || !t.matches || !t.matches('.plw [data-plnode], .plw path[data-pledge]')) return;
  e.preventDefault(); plNoFirst();
  const id = t.getAttribute('data-plnode'), ed = t.getAttribute('data-pledge');
  if(id){ E.sel = { k: 'n', id }; plPaint(); plRefocus('[data-plnode="' + CSS.escape(id) + '"]'); return; }
  const [k, i] = ed.split(':'); E.sel = { k, i: +i }; plPaint(); plRefocus('path[data-pledge="' + CSS.escape(ed) + '"]');
});
// ⚠ skip IME composition (isComposing, or keyCode 229 on Safari): the Korean commit Enter would otherwise add the stage twice.
document.addEventListener('keydown', e => {
  if(e.key !== 'Enter' || e.isComposing || e.keyCode === 229 || mainView !== 'pipe' || !e.target.closest || !e.target.closest('.plw [data-plnt]')) return;
  const pal = e.target.closest('.plpal'), one = pal && PLPQ.trim() ? [...pal.querySelectorAll('.plci:not([hidden])')] : [];
  const b = one.length === 1 && one[0].querySelector('.plcadd') || e.target.parentNode.querySelector('[data-pladd]');   // exactly one match = add it
  if(b){ e.preventDefault(); b.click(); }
});
document.addEventListener('click', e => {
  if(!e.target.closest || !e.target.closest('.plw')) return;
  const E = plCurEnt();
  if(!E) return;
  E.first = false;
  const pk = e.target.closest('[data-plpick]');
  if(pk){ E.sel = { k: 'n', id: pk.dataset.plpick }; plPaint(); return; }
  if(plRO() && e.target.closest('[data-pldel],[data-plmv],[data-plcol],[data-pldrag],[data-pladd],[data-plcadd],[data-plfit]')) return;   // borrowed: view and zoom only
  if(e.target.closest('[data-pldel]')) return plDelSel(E);
  const mv = e.target.closest('[data-plmv]');
  if(mv){ if(E.sel && E.sel.k === 'n' && plgMove(E.G, E.sel.id, +mv.dataset.plmv)){ plTouch(); plPaint(); } return; }
  const sw = e.target.closest('[data-plcol]');
  if(sw) return plSetColor(E, sw.dataset.plcol);
  // Catalog item by «+ Add» or its name (click / Enter / Space): same slot as «+ Stage» — after the selected node, else at the end.
  const pp = e.target.closest('[data-plcadd],.plpi[data-pldrag]'), pk2 = pp ? pp.dataset.plcadd || pp.dataset.pldrag.replace(/^c:/, '') : '';
  if(pp){
    const id = plgAddTpl(E.G, plgTpl(plCat(), pk2), plAddCtx(), E.sel && E.sel.k === 'n' ? E.sel.id : '');
    if(!id) return;
    PLPQ = ''; E.sel = { k: 'n', id }; plTouch(); plPaint();   // added: the filtered list restores
    plRefocus('[data-plcadd="' + CSS.escape(pk2) + '"]', '.plcadd', '.plpal [data-plnt]');   // the pressed item stays (in use): focus it again
    return;
  }
  const add = e.target.closest('[data-pladd]');
  if(add){
    const inp = add.parentNode.querySelector('[data-plnt]'), typed = inp ? inp.value.trim() : '';
    const t = typed || ((plCat().items || []).find(c => !E.G.nodes.some(n => n.title === c.title.ko)) || { title: {} }).title.ko;
    if(!t) return;
    if(E.G.nodes.some(n => n.title === t)){ PLS.msg = T('A stage with that name exists') + ': ' + t; plPaint(); return; }
    const at = E.sel && E.sel.k === 'n' ? E.sel.id : '';   // a catalog title takes its agent/model/task/gate/loop; any other title is a bare custom stage
    PLPQ = ''; E.sel = { k: 'n', id: plgAddTpl(E.G, plgTpl(plCat(), t), plAddCtx(), at) || plgInsert(E.G, t, at) }; plTouch(); plPaint();
    return;
  }
  // ⚠«Arrange» sets touched: an untouched view is re-fitted by plGwFit after the paint, which would drop the kept zoom.
  if(e.target.closest('[data-plfit]')){ const w = e.target.closest('.plcvw'); plWrapBest(E, w && w.querySelector('.plcv'), true, true); E.touched = true; plTouch(); plPaint(); return; }   // centred like «Fit to view»: without ctr plFit anchors the chain near the top
  if(e.target.closest('[data-plfitv]')){ const w = e.target.closest('.plcvw'); plWrapBest(E, w && w.querySelector('.plcv'), false, true); E.touched = true; plTouch(); plPaint(); return; }
  const z = e.target.closest('[data-plz]');
  if(z){ const V = plView(E), k = +z.dataset.plz > 0 ? 1.2 : 1 / 1.2; V.z = Math.max(0.4, Math.min(2, V.z * k)); E.touched = true; E.ctrd = false; plPaint(); }
});
document.addEventListener('dragstart', e => {
  const s = e.target.closest && e.target.closest('[data-pldrag]');
  if(s && e.dataTransfer){ e.dataTransfer.setData('text/plain', s.dataset.pldrag); e.dataTransfer.effectAllowed = 'copy'; }
});
document.addEventListener('dragover', e => { if(e.target.closest && e.target.closest('.plcv')) e.preventDefault(); });
document.addEventListener('drop', e => {
  const cv = e.target.closest && e.target.closest('.plcv'), E = cv && plCurEnt();
  if(!E || !e.dataTransfer || plRO()) return;
  e.preventDefault();
  plView(E);
  const v = e.dataTransfer.getData('text/plain') || '';
  const p = plCvPt(E, cv, e), id = v.startsWith('c:') && plgAddTpl(E.G, plgTpl(plCat(), v.slice(2)), plAddCtx(), { x: p.x - PLG_W / 2, y: p.y - PLG_H / 2 });
  if(!id) return;
  E.sel = { k: 'n', id }; plTouch(); plPaint();
});
// Stage rename in the editor model: loop-back «then» follows (goto is by node id); written by Save → diff → Confirm (server checks again).
function plRetitle(E, v){
  const G = E.G, n = E.sel && E.sel.k === 'n' && plgNode(G, E.sel.id), t = String(v || '').trim();
  if(!n || t === n.title){ plPaint(); return; }
  const err = plTitleErr(G, n, t);
  if(err){ PLS.msg = err; plPaint(); return; }
  G.loops.forEach(l => { if(l.then === n.title) l.then = t; });
  if(G.guards && G.guards.requireGates) G.guards.requireGates = G.guards.requireGates.map(x => x === n.title ? t : x);
  n.title = t; PLS.msg = ''; plTouch(); plPaint();
}
// Field edits in the side panel: node fields (data-plf), loop-back fields, pipeline defaults (data-pld).
function plField(E, f, el){
  const G = E.G, s = E.sel, val = el.type === 'checkbox' ? el.checked : el.value;
  if(el.dataset.pld != null){ G.defaults[el.dataset.pld] = el.dataset.pld === 'retry' ? +val : val; return; }
  if(s && s.k === 'l' && G.loops[s.i]){
    const l = G.loops[s.i];
    if(f === 'max') l.max = +val;
    else if(f === 'then'){ if(val) l.then = val; else delete l.then; }
    else if(f === 'stopOn'){ if(val === 'none') l.stopOn = []; else delete l.stopOn; }
    return;
  }
  const n = s && s.k === 'n' && plgNode(G, s.id);
  if(!n) return;
  if(f === 'retry' || f === 'parallel'){ if(val === '') delete n[f]; else n[f] = parseInt(val, 10); }
  else if(f === 'produces' || f === 'fanout'){ if(val) n[f] = 'slices'; else delete n[f]; }
  else if(f === 'onlyOnJump'){ if(val) n[f] = true; else delete n[f]; }
  else if(val === '') delete n[f];
  else n[f] = val;
}
document.addEventListener('change', e => {
  const el = e.target, pan = el && el.closest && el.closest('.plpan');
  if(pan && plRO()) return;   // borrowed (48h): keyboard can still reach the dimmed panel
  if(pan && el.dataset.plcolc != null){ const E = plCurEnt(); if(E) plSetColor(E, el.value); return; }
  if(pan && (el.dataset.plr != null || el.dataset.plrf != null)){ const E = plCurEnt(); if(E){ E.G.rules = plRulesRead(pan); plTouch(); plPaint(); } return; }
  if(pan && (el.dataset.plgq != null || el.dataset.plgm != null)){ const E = plCurEnt(); if(E){ E.G.guards = plGuardsRead(pan); plTouch(); plPaint(); } return; }
  if(pan && el.dataset.plu != null){ const E = plCurEnt(); if(E){ E.G.use = el.value.replace(/[\r\n]+/g, ' ').trim(); plTouch(); plPaint(); } return; }
  if(pan && el.dataset.plti != null){ const E = plCurEnt(); if(E) plRetitle(E, el.value); return; }
  if(!el || !el.closest || !el.closest('.plpan') || (el.dataset.plf == null && el.dataset.pld == null)) return;
  const E = plCurEnt();
  if(!E) return;
  plField(E, el.dataset.plf, el); plTouch(); plPaint();
});
// Typing in the panel keeps the value without a repaint (a repaint would drop the caret); change/blur repaints.
document.addEventListener('input', e => {
  const el = e.target;
  if(el && el.closest && el.closest('.plpan') && plRO()) return;
  if(el && el.dataset && el.dataset.plrf != null && el.closest('.plpan')){ const E = plCurEnt(); if(E) E.G.rules = plRulesRead(el.closest('.plpan')); return; }
  if(el && el.dataset && el.dataset.plu != null && el.closest('.plpan')){ const E = plCurEnt(); if(E) E.G.use = el.value; return; }
  if(!el || !el.closest || !el.closest('.plpan') || !/^(instr|gate)$/.test(el.dataset.plf || '')) return;
  const E = plCurEnt();
  if(E) plField(E, el.dataset.plf, el);
});
document.addEventListener('dblclick', e => {
  const gh = e.target.closest && e.target.closest('.plw [data-plgh]'), g = gh && gh.closest('.plgw');
  if(!g) return;
  lsSet(PL_SPLIT.key, ''); g.style.removeProperty(PL_SPLIT.v); plFitSoon();
});
