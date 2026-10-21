// «Working now» list left of «Pipelines» (master-detail): each live session as the Timeline's name cell + its run summary.
// Click a session → its run on the right (plNowPick); the canvas nodes show each stage's agent, so no per-agent rows here.
// ⚠Metadata only: never targ, prompts, tool input or Agent descriptions.
// ⚠'gone' = dead-pid ext session kept up to 600s (ext_store); one button per timeline row (cwd + plat).
function plNowLive(ss){
  const seen = {};
  return (ss || []).filter(x => {
    if(!x || x.state === 'done' || x.state === 'abort' || x.state === 'gone') return false;
    const k = (x.cwd || '') + '\n' + (x.plat || '');
    return seen[k] ? false : (seen[k] = true);
  });
}
function plNowFolded(){ return lsGet('sidereus.plnowc', '') === '1'; }
// Run summary where the timeline cell shows its stepper (74b tlPlStrip): open run «● Working · stage» (pulse) / «● Needs you · stage» (amber, same label as the rail dot) /
// «● Idle · stage»; ended «✓ name done»; no run = sessPlChip's «No pipeline» / «Undeclared» (unboxed by CSS).
function plNowRun(x, k){
  const runs = (x.plrun || []).filter(r => r && r.name), r = runs.find(q => !q.end);
  if(r) return '<span class="plnlrun plnlrun-' + k + '" title="' + esc(T('Pipeline run') + ': ' + r.name + (r.cur ? ' · ' + r.cur : '')) + '"><i class="plnld plnld-' + k + (k === 'work' ? ' plnlpulse' : '') + '"></i>'
    + esc(T(PLNOW_ST[k]) + ' · ' + (r.cur || r.name)) + '</span>';
  if(runs.length) return '<span class="plnlrun plnlrun-done" title="' + esc(T('Pipeline run') + ': ' + runs[0].name + ' · ' + T('done')) + '">' + esc('✓ ' + runs[0].name + ' ' + T('done')) + '</span>';
  return sessPlChip(x);
}
// Status dot: work = a turn is running (info) · need = blocked on the person (warn) · idle = anything else, incl. 'wait' (turn ended).
function plNowSt(x){
  if(x.blocked || x.state === 'ask') return 'need';
  return ['tool', 'think', 'run', 'sent', 'stopping'].includes(x.state) ? 'work' : 'idle';
}
const PLNOW_ST = { work: 'Working', need: 'Needs you', idle: 'Idle' };
function plNowList(ss){
  const live = plNowLive(ss === undefined ? SESS : ss), c = plNowFolded();
  const fold = '<button type=button class=plnlf data-pnfold aria-expanded="' + (c ? 'false' : 'true') + '" title="' + esc(T(c ? 'Expand list' : 'Collapse list'))
    + '" aria-label="' + esc(T(c ? 'Expand list' : 'Collapse list')) + '">' + (c ? '›' : '‹') + '</button>';
  const head = '<div class=plnlh>' + (c ? '' : '<b>' + esc(T('Working now')) + '</b><small class=plnln>' + live.length + '</small>') + fold + '</div>';
  // Collapsed rail: one dot per live session (title = project only); a dot click expands and picks it.
  if(c) return '<aside class="plnl plnlc">' + head + live.map(x => { const k = plNowSt(x); return '<button type=button class="plnlrd plnld-' + k + '" data-pncwd="' + esc(x.cwd || '')
    + '" data-pnplat="' + esc(x.plat || '') + '" title="' + esc(x.project || '') + '" aria-label="' + esc((x.project || '') + ' · ' + T(PLNOW_ST[k])) + '"></button>'; }).join('') + '</aside>';
  if(!live.length) return '<aside class=plnl>' + head + '<div class=plnle>' + esc(T('No sessions working now')) + '</div></aside>';
  // Row = the Timeline's session name cell (74b tlSessNmB, bare: no time/token chips) + the run summary; one button per (cwd, plat).
  return '<aside class=plnl>' + head + live.map(x => {
    const on = !!PLS.nowSid && x.sid === PLS.nowSid, k = plNowSt(x), it = { cwd: x.cwd || '', plat: x.plat || '', state: x.state, blocked: x.blocked, idle: x.ageSec };
    return '<div class="plnlr' + (on ? ' on' : '') + '"><button type=button class="plnli tlnm' + (on ? ' on' : '') + '" data-pncwd="' + esc(x.cwd || '') + '" data-pnplat="' + esc(x.plat || '') + '" title="' + esc(x.project || '') + '"'
      + (on ? ' aria-current=true' : '') + '>' + tlSessNmB({ sess: true, cwd: x.cwd || '', plat: x.plat || '', proj: x.project || '', items: [it] }, it, 0, 0, true) + plNowRun(x, k) + '</button></div>';
  }).join('') + '</aside>';
}
// List | run view; the list width uses the 81i grip (key sidereus.plmd, px).
function plNowWrap(body){
  return '<div class="plmd' + (plNowFolded() ? ' plnc' : '') + '"' + strSplitStyle('plmd') + '>' + plNowList() + strSplitGrip('plmd') + '<div class=plmdr>' + body + '</div></div>';
}
// Session → its open run (plrun without end, else the live [pl:] tag) in its project; no run → that project only.
function plNowPick(cwd, plat){
  const x = plNowLive(SESS).find(s => (s.cwd || '') === (cwd || '') && (s.plat || '') === (plat || ''));
  if(!x) return;
  PLS.nowSid = x.sid || '';
  const r = (x.plrun || []).find(q => q && q.name && !q.end) || (x.plm && x.plm.name ? { name: x.plm.name } : null);
  plNowGoProj((r && r.proj) || x.cwd || PLS.proj);
  if(r) PLS.sel = r.name;
  plPaint();
}
// Same reset as plPickProj, without its paint; an open arch-map panel (48h PLAG) would hide the picked pipeline.
function plNowGoProj(proj){
  PLS.proj = proj; lsSet('sidereus.plproj', proj); PLNEW = null; PLS.std = ''; PLS.wf = null; PLS.diff = null; PLS.del = null; PLS.msg = '';
  PLS.runSel = null; plAgSet(false);
}
document.addEventListener('click', e => {
  const t = e.target.closest && e.target.closest('.plw .plnl [data-pncwd],.plw .plnl [data-pnfold]');
  if(!t) return;
  if(t.hasAttribute('data-pnfold')){ if(plNowFolded()) lsDel('sidereus.plnowc'); else lsSet('sidereus.plnowc', '1'); plPaint(); return; }
  if(t.classList.contains('plnlrd')) lsDel('sidereus.plnowc');   // rail dot: expand, then pick
  plNowPick(t.dataset.pncwd, t.dataset.pnplat);
});
