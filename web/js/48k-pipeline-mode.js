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
  // Sits right before «Run» in the action group (48 plBody/plWatchBody); clean Edit shows «Close» there, dirty Edit shows «Cancel» by «Save» (plCancelBtn).
  if(PLMODE !== 'watch') return plDirty(p.name) ? '' : '<button class="wkrgb plmode on" data-plmode=watch aria-pressed=true title="' + esc(T('Back to watching runs')) + '">' + esc(T('Close')) + '</button>';
  return '<button class="wkrgb plmode" data-plmode=edit aria-pressed=false title="' + esc(T('Edit stages, agents and gates')) + '"><span aria-hidden=true>✎</span> ' + esc(T('Edit')) + '</button>';
}
// Dirty Edit: «Cancel» drops the unsaved edits (no server write) and returns to Watch; «Save» keeps its preview + confirm.
function plCancelBtn(p){
  return PLMODE === 'edit' && p && !p.from && plDirty(p.name) ? '<button class="wkrgb plmode" data-plcancel title="' + esc(T('Discard unsaved changes and go back to watching runs')) + '">' + esc(T('Cancel')) + '</button>' : '';
}
function plCancelEdit(){ plResetEnt(plCur()); PLS.msg = ''; plModeSet('watch'); }
// Esc in a clean Edit = «Close»; ⚠with unsaved changes Esc does nothing, so a key never discards work.
function plEditEsc(e){
  if(e.key !== 'Escape' || e.defaultPrevented || mainView !== 'pipe' || PLMODE !== 'edit') return false;
  const t = e.target;
  if(t && /^(INPUT|SELECT|TEXTAREA)$/.test(t.tagName || '')) return false;
  if(PLESC_MENU || plMenuOpen() || PLNEW || PLDRAFT || PLS.std || PLS.diff || PLS.del) return false;
  if(plEscOwned()) return false;
  const p = plCur();
  if(!plModeBtn() || plDirty(p.name)) return false;   // no «Close» on screen: draft, borrowed, agent/workflow view
  plModeSet('watch');
  return true;
}
// Edit mode band above the head row: says which file is being edited («Close»/«Cancel» are in the action group).
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
// Running stage agent's «tool · elapsed» from its live SESS sub row. ⚠Tool name only: sub.now may carry « · description» (Agent/Task) — cut here, rule 1.
function plAgNowLine(x, a){
  if(!x || !a || !a.run || a.id === 'main') return '';
  const subs = x.sub || [];
  const s = (a.id && subs.find(v => v && v.aid === a.id)) || (a.tid && subs.find(v => v && subWorkId(v) === a.tid));
  if(!s) return '';
  const tool = String(s.now || '').split(' · ')[0];
  if(s.idle > PLNOW_QUIET) return T('Idle') + ' · ' + ago(s.idle);
  return tool ? tool + ' · ' + ago(s.idle || 0) : '';
}
// Result of the selected stage from data already on the page: run row (48b plStageRows), gate evidence (48f plEvLine), agents → work log.
function plWatchPane(E, d, lv, lt){
  const n = E && E.sel && E.sel.k === 'n' ? plgNode(E.G, E.sel.id) : plWatchDef(E, lt);
  if(!n) return lt ? '<div class="plpan plwp"><div class=hidnote>' + esc(T('Click a stage to see its result')) + '</div></div>' : '';   // no run, nothing picked: no pane
  const L = (lt || {})[n.title] || null, r = plStageRows(lt, [{ title: n.title }])[0];
  const st = '<div class="plwst plrt-' + r.st + '"' + (r.why ? ' title="' + esc(r.why) + '"' : '') + '><span class=plrtpl>' + esc(PL_MK[r.st] + ' ' + (r.st === 'wait' ? T('Waiting') : plOc(r.st))) + '</span>'
    + (r.rb ? (t => '<span title="' + t + '" aria-label="' + t + '">')(esc(TV({msg: 'Sent back here {n} times', vars: {n: r.rb}})))   // the bare ↺n needs words
      + esc('↺ ' + r.rb) + '</span>' : '') + (r.n ? '<span>' + esc(T('Agents') + ' ' + r.n) + '</span>' : '') + (r.sec ? '<span>' + esc(ago(r.sec)) + '</span>' : '')
    + (r.type ? '<span>' + esc(r.type) + '</span>' : '') + '</div>';
  const ev = L ? plEvLine(plEvRows(PLS.proj), L, plEvCommits(PLS.proj)) : '';
  const gate = '<div class=plwg><span>' + esc(T('Gate')) + '</span>' + (n.gate ? '<code>' + esc(n.gate) + '</code>' : '<i>' + esc(T('No gate command — nothing machine-checks this stage')) + '</i>') + '</div>';
  const ags = lv && lv.sid && lt ? plStageAgents(lt, n.title, Date.now()) : [];
  const lx = ags.length ? (SESS || []).find(r => r.sid === lv.sid) : null;
  const plwBtn = a => { const p = plLabParts(a.lab), ds = plLabDesc(p), nl = plAgNowLine(lx, a);   // task line beside the type; data, so esc only
    return '<button type=button class=plwa data-plwsid="' + esc(lv.sid) + '" data-plwtid="' + esc(a.tid) + '" title="' + esc(plLabTip(a.lab)) + '">'
    + (a.run ? '<i class=plrtdot></i>' : '') + esc(p.type || T('Agent')) + (ds ? '<span class=plwad>' + esc(ds) + '</span>' : '') + (a.sec ? ' · ' + esc(ago(a.sec)) : '') + (nl ? '<span class=plwan>' + esc(nl) + '</span>' : '') + '</button>'; };
  // Running and finished agents on separate rows: a two-line running button beside a one-line finished one read as misaligned.
  const ar = ags.filter(a => a.run).map(plwBtn).join(''), af = ags.filter(a => !a.run).map(plwBtn).join('');
  const ab = (ar ? '<div class=plwas>' + ar + '</div>' : '') + (af ? '<div class="plwas plwdn"><span class=plwal>' + esc(T('Done')) + '</span>' + af + '</div>' : '');
  const ad = n.agent ? plAgDesc(n.agent) : '';
  return '<div class="plpan plwp"><div class=plph><b>' + esc(plgShow(n.title)) + '</b><small>' + esc((n.agent || '') + (n.model ? ' · ' + n.model : '')) + '</small>' + (ad ? '<small class=plphd title="' + esc(ad) + '">' + esc(ad) + '</small>' : '') + '</div>' + st
    + (ev || '<div class=hidnote>' + esc(T('No gate evidence for this stage yet')) + '</div>') + gate + ab + '</div>';
}
// Watch is three stacked regions: canvas | result pane | «Running N» card, split by two drag grips (p, r).
// Sizes are kept as shares of the free height (sidereus.plwv = [canvas, pane, card]) so a window resize keeps the proportions.
// ⚠Mins canvas 260 · pane 80 · card 84 (header + 2 rows; 48 clipped the 2nd row); the whole stack ends at the feed bottom (plGwFit passes h) and never scrolls the page.
const PLW_MIN = [260, 80, 84], PLW_GRIP = 24, PLW_DEF = [0.75, 0.14, 0.11];   // default shares of the free height; a longer pane/card scrolls inside
let PLWDRAG = null;
const PLW_STEP = 24;   // keyboard step, same as the session drawer grips (41 SESDR_STEP)
// aria-valuenow = the boundary position as a percent of the stack (p: under the canvas, r: under the pane); plWApply keeps it live.
function plWGrip(k){
  const F = plWShares() || PLW_DEF, now = Math.round(100 * (k === 'p' ? F[0] : F[0] + F[1]));
  return '<div class=plwgr data-plwg=' + k + ' tabindex=0 role=separator aria-orientation=horizontal aria-valuemin=0 aria-valuemax=100 aria-valuenow=' + now
    + ' aria-label="' + esc(T(k === 'p' ? 'Resize canvas and result pane' : 'Resize result pane and Running card')) + '" title="' + esc(T('Drag to resize · double-click for default')) + '"></div>';
}
// Always present (an empty state, not nothing): runs starting or ending must not move the layout.
function plWatchOv(ov){
  return '<div class=plwov>' + (ov || '<div class=plov><b class=plovh>' + esc(TV({msg: 'Running {n}', vars: {n: 0}})) + '</b><span class=hidnote>' + esc(T('No runs running')) + '</span></div>') + '</div>';
}
function plWShares(){ const v = lsJson('sidereus.plwv', null); return Array.isArray(v) && v.length === 3 && v.every(x => typeof x === 'number' && x > 0 && x < 1) ? v : null; }
// Heights [canvas, pane, card] for free height A; F = saved shares (else PLW_DEF).
// Mins win over shares; when the canvas would drop under its min, the card then the pane give way first.
function plWSizes(A, F){
  const s = (F || PLW_DEF).map(f => Math.round(f * A));
  s[1] = Math.max(PLW_MIN[1], s[1]); s[2] = Math.max(PLW_MIN[2], s[2]);
  let d = PLW_MIN[0] - (A - s[1] - s[2]);
  for(const i of [2, 1]){ if(d <= 0) break; const r = Math.min(d, s[i] - PLW_MIN[i]); s[i] -= r; d -= r; }
  s[0] = Math.max(PLW_MIN[0], A - s[1] - s[2]);
  return s;
}
function plWApply(g, oc, s){
  g.style.setProperty('--plcvh', s[0] + 'px'); g.style.setProperty('--plwph', s[1] + 'px'); if(oc) oc.style.height = s[2] + 'px';
  const A = s[0] + s[1] + s[2];
  if(A > 0) document.querySelectorAll('.plw .plwgr').forEach(x => x.setAttribute('aria-valuenow', Math.round(100 * (x.dataset.plwg === 'p' ? s[0] : s[0] + s[1]) / A)));
}
// Move the boundary under region i (0 canvas|pane, 1 pane|card) by dy px; drag and arrow keys share it so the mins match.
function plWStep(s0, i, dy){
  const s = s0.slice(), sum = s0[i] + s0[i + 1];
  const a = Math.max(PLW_MIN[i], Math.min(sum - PLW_MIN[i + 1], s0[i] + dy));
  s[i] = Math.round(a); s[i + 1] = Math.round(sum - a);
  return s;
}
function plWNow(g, oc){ return [parseFloat(g.style.getPropertyValue('--plcvh')) || 0, parseFloat(g.style.getPropertyValue('--plwph')) || 0, oc.offsetHeight]; }
function plWSave(s){
  const A = s[0] + s[1] + s[2];
  if(A > 0) lsSetJson('sidereus.plwv', s.map(x => +(x / A).toFixed(4)));
  if(typeof plFitSoon === 'function') plFitSoon();   // re-fit the graph to the new canvas height
}
function plWReset(){ lsDel('sidereus.plwv'); if(typeof plFitSoon === 'function') plFitSoon(); }
// Keyboard twin of the drag: ArrowUp/ArrowDown move the boundary PLW_STEP px, Home = default.
function plWKey(e){
  const gr = e.target && e.target.closest && e.target.closest('.plw .plwgr');
  if(!gr || e.altKey || e.metaKey || e.ctrlKey) return;
  if(e.key === 'Home'){ e.preventDefault(); plWReset(); return; }
  const dy = e.key === 'ArrowDown' ? PLW_STEP : e.key === 'ArrowUp' ? -PLW_STEP : 0;
  const g = document.querySelector('.plw .plgw.plwt'), oc = document.querySelector('.plw .plwov');
  if(!dy || !g || !oc) return;
  e.preventDefault();
  const s = plWStep(plWNow(g, oc), gr.dataset.plwg === 'p' ? 0 : 1, dy);
  plWApply(g, oc, s); plWSave(s);
}
function plWatchFit(g, fd, h){
  if(PLWDRAG) return;
  g.style.height = '';
  const nl = document.querySelector('.plw .plnl:not(.plnlc)'), oc = document.querySelector('.plw .plwov');
  if(nl) nl.style.minHeight = '';   // ⚠a kept card height from the last fit would count as overflow below
  // Sizes come from shares only (never from content), so polls never move the canvas.
  const F = plWShares(), end = oc || g, pb = parseFloat(getComputedStyle(fd).paddingBottom) || 0;
  let A = h - 2 * PLW_GRIP;
  plWApply(g, oc, plWSizes(A, F));
  // Close the gap to the feed bottom (h is the shared estimate), then take back anything that overflows (Run panel, a note): no page scroll.
  const slack = Math.floor(fd.getBoundingClientRect().bottom - pb - end.getBoundingClientRect().bottom) - 2;
  if(slack > 0){ A += slack; plWApply(g, oc, plWSizes(A, F)); }
  const over = fd.scrollHeight - fd.clientHeight;
  if(over > 0){ A -= over; plWApply(g, oc, plWSizes(A, F)); }
  if(nl) nl.style.minHeight = Math.max(0, Math.round(end.getBoundingClientRect().bottom - nl.getBoundingClientRect().top)) + 'px';
}
document.addEventListener('pointerdown', e => {
  const gr = e.target.closest && e.target.closest('.plw .plwgr');
  if(!gr || e.button !== 0) return;
  const g = document.querySelector('.plw .plgw.plwt'), oc = document.querySelector('.plw .plwov');
  if(!g || !oc) return;
  e.preventDefault();
  const s0 = plWNow(g, oc), i = gr.dataset.plwg === 'p' ? 0 : 1, y0 = e.clientY;
  PLWDRAG = { s: s0.slice() }; gr.classList.add('on'); document.body.classList.add('dragging');
  dragTrack(e, gr, ev => {
    PLWDRAG.s = plWStep(s0, i, ev.clientY - y0);
    plWApply(g, oc, PLWDRAG.s);
  }, () => {
    const s = PLWDRAG.s;
    PLWDRAG = null; gr.classList.remove('on'); document.body.classList.remove('dragging');
    plWSave(s);
  });
});
document.addEventListener('dblclick', e => {
  if(!(e.target.closest && e.target.closest('.plw .plwgr'))) return;
  plWReset();
});
document.addEventListener('keydown', plWKey);
document.addEventListener('click', e => {
  const t = e.target.closest && e.target.closest('.plw [data-plmode],.plw [data-plcancel],.plw .plwp [data-plwsid]');
  if(!t || t.disabled) return;
  if(t.hasAttribute('data-plcancel')) return plCancelEdit();
  if(t.hasAttribute('data-plmode')) return plModeSet(t.dataset.plmode);
  plOpenWork(t.dataset.plwsid, t.dataset.plwtid);   // work popup: the click-only exception (sidereus/work.py)
});
document.addEventListener('keydown', plEditEsc);
