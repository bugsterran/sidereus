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
document.addEventListener('click', e => {
  const t = e.target.closest && e.target.closest('.plw [data-plmode],.plw .plwp [data-plwsid]');
  if(!t || t.disabled) return;
  if(t.hasAttribute('data-plmode')) return plModeSet(t.dataset.plmode);
  plOpenWork(t.dataset.plwsid, t.dataset.plwtid);   // work popup: the click-only exception (sidereus/work.py)
});
