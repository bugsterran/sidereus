// «Pipelines» Watch / Edit mode (key sidereus.plmode). Watch (default): «Working now» list (48j) | select-only canvas | the selected stage's result.
// Edit: palette | editable canvas | stage editor — the pre-mode layout, byte for byte. Drafts (std, suggestion, unsaved) always render as Edit.
// ⚠Metadata only: the pane shows outcome, gate evidence and agent types; an Agent description goes only into title= (plLabTip).
let PLMODE = lsGet('sidereus.plmode', 'watch') === 'edit' ? 'edit' : 'watch';
function plModeSet(m, quiet){
  PLMODE = m === 'edit' ? 'edit' : 'watch'; lsSet('sidereus.plmode', PLMODE);
  if(PLMODE === 'watch'){ PLS.diff = null; PLS.del = null; }   // ⚠a pending Save/Delete preview with «Confirm» must not show in Watch
  if(!quiet) plPaint();
}
// Borrowed (p.from) is always Watch: it is read-only here, and a saved Edit mode left only a disabled «Edit» with Watch unreachable.
function plWatchFor(p){ return !!(p && p.ok && p.sha && !p.std && !p.suggest) && (PLMODE === 'watch' || !!p.from); }
function plWatchOn(){ return plWatchFor(plCur()); }
// One left column: the list, unless Edit shows the palette there (a saved or draft pipeline on the canvas).
function plNowShown(){ const p = plCur(); return !(p && p.ok) || plWatchFor(p) || !!PLS.wf || (typeof PLAG !== 'undefined' && !!PLAG); }
function plModeBtn(){
  const p = plCur();
  if(!p || !p.ok || !p.sha || p.std || p.suggest || PLS.wf || (typeof PLAG !== 'undefined' && PLAG)) return '';
  if(p.from) return '<button class="wkrgb plmode" data-plmode=edit disabled title="' + esc(T('Read-only — edit it in its own project')) + '">' + esc(T('Edit')) + '</button>';
  // Sits right before «Run» in the action group (48 plBody/plWatchBody); Edit shows «Done» in the same spot.
  if(PLMODE !== 'watch') return '<button class="wkrgb plmode on" data-plmode=watch aria-pressed=true title="' + esc(T('Back to watching runs')) + '">' + esc(T('Done')) + '</button>';
  return '<button class="wkrgb plmode" data-plmode=edit aria-pressed=false title="' + esc(T('Edit stages, agents and gates')) + '"><span aria-hidden=true>✎</span> ' + esc(T('Edit')) + '</button>';
}
// Edit mode band above the head row: says which file is being edited («Done» is in the action group).
function plModeBand(){
  const p = plCur();
  if(PLMODE !== 'edit' || !p || !p.ok || !p.sha || p.std || p.suggest || p.from || PLS.wf || (typeof PLAG !== 'undefined' && PLAG)) return '';
  return '<div class=plmband><span aria-hidden=true>✎</span> ' + esc(T('Editing')) + ' <b>' + esc(p.name) + '</b></div>';
}
// Watch with nothing selected: the run's running stage, else its last non-waiting one (canvas order). Read-only: E.sel untouched.
function plWatchDef(E, lt){
  if(!E || !lt) return null;
  const ns = E.G.nodes, st = n => (lt[n.title] || {}).st;
  return ns.find(n => st(n) === 'run') || ns.filter(n => st(n) && st(n) !== 'wait').pop() || null;
}
// Result of the selected stage from data already on the page: run row (48b plStageRows), gate evidence (48f plEvLine), agents → work log.
function plWatchPane(E, d, lv, lt){
  const n = E && E.sel && E.sel.k === 'n' ? plgNode(E.G, E.sel.id) : plWatchDef(E, lt);
  if(!n) return lt ? '<div class="plpan plwp"><div class=hidnote>' + esc(T('Click a stage to see its result')) + '</div></div>' : '';   // no run, nothing picked: no pane
  const L = (lt || {})[n.title] || null, r = plStageRows(lt, [{ title: n.title }])[0];
  const st = '<div class="plwst plrt-' + r.st + '"' + (r.why ? ' title="' + esc(r.why) + '"' : '') + '><span class=plrtpl>' + esc(PL_MK[r.st] + ' ' + (r.st === 'wait' ? T('Waiting') : plOc(r.st))) + '</span>'
    + (r.rb ? '<span>' + esc('↺ ' + r.rb) + '</span>' : '') + (r.n ? '<span>' + esc(T('Agents') + ' ' + r.n) + '</span>' : '') + (r.sec ? '<span>' + esc(ago(r.sec)) + '</span>' : '')
    + (r.type ? '<span>' + esc(r.type) + '</span>' : '') + '</div>';
  const ev = L ? plEvLine(plEvRows(PLS.proj), L, plEvCommits(PLS.proj)) : '';
  const gate = '<div class=plwg><span>' + esc(T('Gate')) + '</span>' + (n.gate ? '<code>' + esc(n.gate) + '</code>' : '<i>' + esc(T('No gate command — nothing machine-checks this stage')) + '</i>') + '</div>';
  const ags = lv && lv.sid && lt ? plStageAgents(lt, n.title, Date.now()) : [];
  const ab = ags.map(a => '<button type=button class=plwa data-plwsid="' + esc(lv.sid) + '" data-plwtid="' + esc(a.tid) + '" title="' + esc(plLabTip(a.lab)) + '">'
    + (a.run ? '<i class=plrtdot></i>' : '') + esc(plLabParts(a.lab).type || T('Agent')) + (a.sec ? ' · ' + esc(ago(a.sec)) : '') + '</button>').join('');
  return '<div class="plpan plwp"><div class=plph><b>' + esc(plgShow(n.title)) + '</b><small>' + esc((n.agent || '') + (n.model ? ' · ' + n.model : '')) + '</small></div>' + st
    + (ev || '<div class=hidnote>' + esc(T('No gate evidence for this stage yet')) + '</div>') + gate + (ab ? '<div class=plwas>' + ab + '</div>' : '') + '</div>';
}
// Watch is three stacked regions: canvas | result pane | «Running N» card, split by two drag grips (p, r).
// Sizes are kept as shares of the free height (sidereus.plwv = [canvas, pane, card]) so a window resize keeps the proportions.
// ⚠Mins canvas 260 · pane 80 · card 48; the whole stack ends at the feed bottom (plGwFit passes h) and never scrolls the page.
const PLW_MIN = [260, 80, 48], PLW_GRIP = 8, PLW_RUN0 = 110, PLW_PANE0 = 120;   // default pane hugs its content up to 120px (header · status · gate · note), longer scrolls
let PLWPH = { k: '', h: 0 }, PLWDRAG = null;
function plWGrip(k){ return '<div class=plwgr data-plwg=' + k + ' role=separator aria-orientation=horizontal title="' + esc(T('Drag to resize · double-click for default')) + '"></div>'; }
// Always present (an empty state, not nothing): runs starting or ending must not move the layout.
function plWatchOv(ov){
  return '<div class=plwov>' + (ov || '<div class=plov><b class=plovh>' + esc(TV({msg: 'Running {n}', vars: {n: 0}})) + '</b><span class=hidnote>' + esc(T('No runs running')) + '</span></div>') + '</div>';
}
function plWShares(){ const v = lsJson('sidereus.plwv', null); return Array.isArray(v) && v.length === 3 && v.every(x => typeof x === 'number' && x > 0 && x < 1) ? v : null; }
// Heights [canvas, pane, card] for free height A; F = saved shares, ph0 = the pane's natural height.
// Mins win over shares; when the canvas would drop under its min, the card then the pane give way first.
function plWSizes(A, F, ph0){
  const s = F ? F.map(f => Math.round(f * A)) : [0, Math.max(PLW_MIN[1], Math.min(PLW_PANE0, ph0)), PLW_RUN0];
  s[1] = Math.max(PLW_MIN[1], s[1]); s[2] = Math.max(PLW_MIN[2], s[2]);
  let d = PLW_MIN[0] - (A - s[1] - s[2]);
  for(const i of [2, 1]){ if(d <= 0) break; const r = Math.min(d, s[i] - PLW_MIN[i]); s[i] -= r; d -= r; }
  s[0] = Math.max(PLW_MIN[0], A - s[1] - s[2]);
  return s;
}
function plWApply(g, oc, s){ g.style.setProperty('--plcvh', s[0] + 'px'); g.style.setProperty('--plwph', s[1] + 'px'); if(oc) oc.style.height = s[2] + 'px'; }
function plWatchFit(g, fd, h){
  if(PLWDRAG) return;
  g.style.height = '';
  const nl = document.querySelector('.plw .plnl:not(.plnlc)'), oc = document.querySelector('.plw .plwov'), wp = g.querySelector('.plwp');
  if(nl) nl.style.minHeight = '';   // ⚠a kept card height from the last fit would count as overflow below
  // ⚠The pane's natural height is measured once per (window size, project, shown stage): re-measuring each poll made the canvas jump.
  const wk = wp ? [innerWidth, innerHeight, PLS.proj, (wp.querySelector('.plph b') || {}).textContent || ''].join('|') : '';
  if(wp && PLWPH.k !== wk){ g.style.removeProperty('--plwph'); PLWPH = { k: wk, h: wp.scrollHeight }; }
  const F = plWShares(), ph0 = wp ? PLWPH.h : PLW_MIN[1], end = oc || g, pb = parseFloat(getComputedStyle(fd).paddingBottom) || 0;
  let A = h - 2 * PLW_GRIP;
  plWApply(g, oc, plWSizes(A, F, ph0));
  // Close the gap to the feed bottom (h is the shared estimate), then take back anything that overflows (Run panel, a note): no page scroll.
  const slack = Math.floor(fd.getBoundingClientRect().bottom - pb - end.getBoundingClientRect().bottom) - 2;
  if(slack > 0){ A += slack; plWApply(g, oc, plWSizes(A, F, ph0)); }
  const over = fd.scrollHeight - fd.clientHeight;
  if(over > 0){ A -= over; plWApply(g, oc, plWSizes(A, F, ph0)); }
  if(nl) nl.style.minHeight = Math.max(0, Math.round(end.getBoundingClientRect().bottom - nl.getBoundingClientRect().top)) + 'px';
}
document.addEventListener('pointerdown', e => {
  const gr = e.target.closest && e.target.closest('.plw .plwgr');
  if(!gr || e.button !== 0) return;
  const g = document.querySelector('.plw .plgw.plwt'), oc = document.querySelector('.plw .plwov');
  if(!g || !oc) return;
  e.preventDefault();
  const k = gr.dataset.plwg, s0 = [parseFloat(g.style.getPropertyValue('--plcvh')) || 0, parseFloat(g.style.getPropertyValue('--plwph')) || 0, oc.offsetHeight];
  const i = k === 'p' ? 0 : 1, y0 = e.clientY, sum = s0[i] + s0[i + 1];
  PLWDRAG = { s: s0.slice() }; gr.classList.add('on'); document.body.classList.add('dragging');
  dragTrack(e, gr, ev => {
    const a = Math.max(PLW_MIN[i], Math.min(sum - PLW_MIN[i + 1], s0[i] + ev.clientY - y0));
    PLWDRAG.s[i] = Math.round(a); PLWDRAG.s[i + 1] = Math.round(sum - a);
    plWApply(g, oc, PLWDRAG.s);
  }, () => {
    const s = PLWDRAG.s, A = s[0] + s[1] + s[2];
    PLWDRAG = null; gr.classList.remove('on'); document.body.classList.remove('dragging');
    if(A > 0) lsSetJson('sidereus.plwv', s.map(x => +(x / A).toFixed(4)));
    if(typeof plFitSoon === 'function') plFitSoon();   // re-fit the graph to the new canvas height
  });
});
document.addEventListener('dblclick', e => {
  if(!(e.target.closest && e.target.closest('.plw .plwgr'))) return;
  lsDel('sidereus.plwv');
  if(typeof plFitSoon === 'function') plFitSoon();
});
document.addEventListener('click', e => {
  const t = e.target.closest && e.target.closest('.plw [data-plmode],.plw .plwp [data-plwsid]');
  if(!t || t.disabled) return;
  if(t.hasAttribute('data-plmode')) return plModeSet(t.dataset.plmode);
  plOpenWork(t.dataset.plwsid, t.dataset.plwtid);   // work popup: the click-only exception (sidereus/work.py)
});
