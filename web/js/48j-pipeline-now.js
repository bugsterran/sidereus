// «Working now» list left of «Pipelines» (master-detail): each live session · platform logo · project · pipeline chip (40b sessPlChip).
// Click a session → its run on the right (plNowPick); click a stage agent under it → that stage selected on the canvas (plNowPickApply).
// ⚠Metadata only: never targ, prompts or tool input; the Agent description goes only into title= (plLabTip).
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
// Stage agents of a session: its [pl:name/title] subs (plSubsOf adds the main agent's own stage).
function plNowStages(x){
  return plSubsOf(x).map(a => { const d = plDescStage(a && a.lab); return d ? { name: d.name, title: d.title, lab: a.lab } : null; }).filter(Boolean);
}
function plNowList(ss){
  const live = plNowLive(ss === undefined ? SESS : ss), c = plNowFolded();
  const fold = '<button type=button class=plnlf data-pnfold aria-expanded="' + (c ? 'false' : 'true') + '" title="' + esc(T(c ? 'Expand list' : 'Collapse list'))
    + '" aria-label="' + esc(T(c ? 'Expand list' : 'Collapse list')) + '">' + (c ? '›' : '‹') + '</button>';
  const head = '<div class=plnlh>' + (c ? '' : '<b>' + esc(T('Working now')) + '</b><small>' + live.length + '</small>') + fold + '</div>';
  if(c) return '<aside class=plnl>' + head + '</aside>';
  if(!live.length) return '<aside class=plnl>' + head + '<div class=plnle>' + esc(T('No sessions working now')) + '</div></aside>';
  return '<aside class=plnl>' + head + live.map(x => {
    const on = !!PLS.nowSid && x.sid === PLS.nowSid, cw = esc(x.cwd || ''), pt = esc(x.plat || '');
    const st = on ? plNowStages(x).map(s => '<button type=button class=plnls data-pnname="' + esc(s.name) + '" data-pnst="' + esc(s.title) + '" title="' + esc(plLabTip(s.lab))
      + '"><span class=plnlst>' + esc(s.title) + '</span><small>' + esc(plLabType(s.lab)) + '</small></button>').join('') : '';
    return '<div class="plnlr' + (on ? ' on' : '') + '"><button type=button class="plnli' + (on ? ' on' : '') + '" data-pncwd="' + cw + '" data-pnplat="' + pt + '" title="' + esc(x.project || '') + '">'
      + aiLogo(x.plat) + '<span class=plnlp>' + esc(x.project || '') + '</span>' + sessPlChip(x) + '</button>'
      + '<button type=button class=plnlt data-pntl="' + cw + '" data-pnplat="' + pt + '" title="' + esc(T('Show in Timeline')) + '">' + esc(T('Timeline')) + '</button>' + st + '</div>';
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
  PLS.nowPick = null;
  plPaint();
}
// Same reset as plPickProj, without its paint; an open arch-map panel (48h PLAG) would hide the picked pipeline.
function plNowGoProj(proj){
  PLS.proj = proj; lsSet('sidereus.plproj', proj); PLNEW = null; PLS.std = ''; PLS.wf = null; PLS.diff = null; PLS.del = null; PLS.msg = '';
  PLS.runSel = null; plAgSet(false);
}
// ⚠The project comes from the row's session, never the current PLS.proj: a stale pick would write `name` into another project's sidereus.plselp.
function plNowStage(name, title){
  const x = PLS.nowSid && (SESS || []).find(s => s && s.sid === PLS.nowSid);
  if(!x) return;
  const r = (x.plrun || []).find(q => q && q.name === name && !q.end);
  plNowGoProj((r && r.proj) || x.cwd || PLS.proj);
  PLS.sel = name; PLS.nowPick = { name, title };
  plPaint();
}
// ⚠Selection only (same as a data-plpick click): never plFit / centre — a click must not move the view.
function plNowPickApply(){
  const k = PLS.nowPick, d = PLS.data[PLS.proj];
  if(!k || !d) return;   // project still loading: keep the pick
  PLS.nowPick = null;
  const p = plCur();
  if(!p || p.name !== k.name) return;
  const E = plEnt(p), n = E && E.G.nodes.find(q => q.title === k.title);
  if(!n) return;
  E.first = false; E.sel = { k: 'n', id: n.id };
}
function plNowGo(cwd, plat){
  // ⚠Timeline rows carry no plat for Claude (74b data-tlp = g.plat || ''; 74 compares plat || 'cc'): 'cc' maps to ''.
  const tp = plat && plat !== 'cc' ? plat : '';
  const sel = '.tlr.tlrs[data-tlc="' + CSS.escape(cwd || '') + '"][data-tlp="' + CSS.escape(tp) + '"]';
  if(typeof mvGo === 'function') mvGo('time', sel); else setMainView('time');
}
document.addEventListener('click', e => {
  const t = e.target.closest && e.target.closest('.plw .plnl [data-pntl],.plw .plnl [data-pncwd],.plw .plnl [data-pnst],.plw .plnl [data-pnfold]');
  if(!t) return;
  if(t.hasAttribute('data-pnfold')){ if(plNowFolded()) lsDel('sidereus.plnowc'); else lsSet('sidereus.plnowc', '1'); plPaint(); return; }
  if(t.hasAttribute('data-pntl')) return plNowGo(t.dataset.pntl, t.dataset.pnplat);
  if(t.hasAttribute('data-pnst')) return plNowStage(t.dataset.pnname, t.dataset.pnst);
  plNowPick(t.dataset.pncwd, t.dataset.pnplat);
});
