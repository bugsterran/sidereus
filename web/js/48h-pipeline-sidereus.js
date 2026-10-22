// «Pipelines» tab: a Sidereus-owned tool pipeline (arch-map) running on this project, shown read-only.
// The definition lives in the Sidereus repo (84j archHome), never in the target project; nothing here edits or runs it.
// ⚠Run state = state `archRun` (sidereus/arch_map.runs) via 84j archRunOf; the hook keeps no plrun for such sessions.
let PLAG = false;   // the «arch-map · Sidereus» chip is open
function plAgSet(on){ PLAG = !!on; }
function plAgHome(){ return SIDEREUS_DIR || (typeof archHome === 'function' ? archHome(null) : ''); }
// Live run of the Sidereus pipeline on proj, or null; the Sidereus repo itself shows its own file instead.
function plAgRun(proj){
  const r = typeof archRunOf === 'function' ? archRunOf(proj) : null, home = r ? plAgHome() : '';
  return r && proj !== home ? r : null;
}
// Pure: chip after the project's own pipeline chips; live dot like theirs.
function plAgChip(r, on){
  return r ? '<button class="strp plon plag' + (on ? ' on' : '') + '" data-plag title="' + esc(T('Sidereus pipeline — read-only') + ' · ' + T('running', 'exec')) + '">'
    + esc(ARCH_PL + ' · Sidereus') + '<i class=mvdot></i></button>' : '';
}
// Pure: stage steps lit from the run's stage number n (1-based): earlier done, n running, later waiting.
function plAgSteps(titles, r){
  const c = titles.indexOf(r.stage), ci = c >= 0 ? c : (r.n || 0) - 1;
  return titles.map((t, i) => ({ st: i < ci ? 'done' : i === ci ? 'run' : 'wait', nm: t, tip: t }));
}
// Read-only body: title, stepper, stage and elapsed, session; stages from the Sidereus repo's arch-map.json.
// Sidereus's arch-map definition (loaded on demand) and its stage titles; unloaded = the run's current stage only.
function plAgDef(r){
  const home = plAgHome(), d = home && PLS.data[home];
  if(home && !d) plLoad(home, false);
  const p = d && d.ok && (d.pipelines || []).find(x => x && x.name === ARCH_PL);
  return { p, titles: p ? (p.stages || []).map(s => s && s.title).filter(Boolean) : [r.stage] };
}
function plAgStageN(r){ return r.n && r.of ? T('Stage {n}/{m}').replace('{n}', r.n).replace('{m}', r.of) : ''; }
// «Running» overview row (48b plOvHtml) from the run: no plrun or tagged subagents exist on the target project for it.
function plAgOvRow(proj, r, now){
  const steps = plAgSteps(plAgDef(r).titles, r), k = plAgStageN(r);
  return { proj, name: ARCH_PL, sid: r.sid || '', stages: steps.map(s => ({ t: s.nm, st: s.st, rb: 0 })), cur: [r.stage], n: 0,
    sumh: esc((k ? k + ' · ' : '') + archRunEl(r, now || Date.now())) };
}
function plAgBody(r, now){
  const { p, titles } = plAgDef(r);
  const steps = plAgSteps(titles, r), ci = steps.findIndex(s => s.st === 'run');
  return '<div class=plbar><b>' + esc((p && p.title) || ARCH_PL) + '</b><span class=hidnote>' + esc(T('Sidereus pipeline — read-only')) + '</span></div>'
    + '<div class=plagrun>' + plStepper(steps, ci, 'lg') + '<span class=hidnote>' + esc((plAgStageN(r) ? plAgStageN(r) + ' · ' : '') + r.stage
      + ' · ' + archRunEl(r, now || Date.now()) + ' · ' + T('Session') + ' ' + sid8(r.sid || '')) + '</span></div>';
}
// Any other head-row button (New menu, Workflow chips) leaves the arch-map view; the project picker and × do not.
document.addEventListener('click', e => {
  const b = e.target && e.target.closest ? e.target.closest('.plw :is(.pltop, .plnames) button') : null;
  if(!b || b.matches('[data-ppk], [data-plprojrm], [data-plnewm], [data-plmode]')) return;
  const on = b.hasAttribute('data-plag');
  if(on === PLAG) return;
  PLAG = on; plPaint();
});
// Borrowed pipelines (GET /api/pipelines `borrowed`): run on this project but defined in another (`from`); read-only here.
// ⚠Kept out of `pipelines`: plKnown/archHome/«copy from» read that list as «this project owns it».
function plBorrows(d){ return (d && d.ok && d.borrowed) || []; }
function plBorrowOf(d, name){ return plBorrows(d).find(b => b && b.name === name) || null; }
function plRO(){ const p = plCur(); return !!(p && p.from) || (typeof plWatchFor === 'function' && plWatchFor(p)); }   // canvas handlers (48d): borrowed view and 48k Watch are read-only
function plBorrowLab(b){
  return b.builtin ? b.name + ' · ' + T('Sidereus built-in') : TV({msg: '{name} · from {proj}', vars: {name: b.name, proj: strShort(b.from || '')}});
}
// Head-row chip of a borrowed pipeline running here (like plAgChip); the combobox lists own pipelines only.
function plBorrowChip(b, on){
  return '<button class="strp plon plbor' + (on ? ' on' : '') + '" data-plbor="' + esc(b.name) + '" title="' + esc(TV({msg: 'Defined in {proj} — read-only here', vars: {proj: b.from || ''}}) + ' · ' + T('running', 'exec')) + '">'
    + esc(plBorrowLab(b)) + '<i class=mvdot></i></button>';
}
// ⚠Live runs only: the server lists every borrowed pipeline with a run record here, ended ones included.
function plBorrowChips(d){
  const on = b => b.name === PLS.sel && !PLAG && !PLS.wf && !PLS.std;
  return plBorrows(d).filter(b => { const lv = plBorrowLv(PLS.proj, b); return !!(lv && lv.run && lv.run.run); }).map(b => plBorrowChip(b, on(b))).join('');
}
document.addEventListener('click', e => {
  const b = e.target && e.target.closest ? e.target.closest('.plw [data-plbor]') : null;
  if(b) plSelPick(b.dataset.plbor);
});
// Run of borrowed `p` on proj, matching the server's attach (sidereus/pipeline.runs_here): the Sidereus tool run, else a plrun of a session in proj.
function plBorrowLv(proj, p){
  const a = p.name === ARCH_PL ? plAgRun(proj) : null;
  if(a){
    const lt = {};
    plAgSteps((p.stages || []).map(s => s.title), a).forEach(s => { lt[s.nm] = { st: s.st, n: 0, sec: 0, retry: 0 }; });
    return { sid: a.sid || '', run: { run: true, start: +a.t0 || 0, total: 0 }, lt };
  }
  let pr = null, sid = '';
  (SESS || []).forEach(x => { if(x && x.cwd === proj) (x.plrun || []).forEach(r => {
    if(!r || r.name !== p.name || (r.proj && r.proj !== p.from)) return;
    const on = plPrLive(r);
    if(!pr || (on && !plPrLive(pr)) || (on === plPrLive(pr) && (r.t1 || 0) > (pr.t1 || 0))){ pr = r; sid = x.sid; }
  }); });
  return pr ? plPrLv(sid, pr, p.stages || [], Date.now()) : null;
}
// Same canvas as an owned pipeline; no Save/Run/Delete (edit and run stay in the owning project).
function plBorrowBody(d, p, list, ov){
  if(!p.ok) return list + '<div class=hidnote>' + esc(TV({msg: 'Defined in {proj} — read-only here', vars: {proj: p.from || ''}})) + '</div><ul class=plerrs>'
    + (p.errs || []).map(x => '<li>' + esc(x) + '</li>').join('') + '</ul>';
  const lv = plBorrowLv(PLS.proj, p), lt = lv ? lv.lt : null, cv = plCanvas(p, d, lt);
  return list + '<div class=plbar><b>' + esc(p.title) + '</b>' + plLiveHead(lv, lt) + '<span class=hidnote>'
    + esc(TV({msg: 'Defined in {proj} — read-only here', vars: {proj: p.from || ''}})) + '</span></div>' + plUseLine(p)
    + '<div class=plro>' + cv.html + '</div>' + plWGrip('r') + plWatchOv(ov);   // borrowed = always Watch (48k): same three regions
}
