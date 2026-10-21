// «Working now» list left of «Pipelines» (master-detail): each live session as the Timeline's name cell + its run summary.
// Click a session → its run on the right (plNowPick); its live subagents sit under the card as the Timeline's agent rows.
// ⚠Metadata only: never targ, prompts or tool input; subagent rows carry the one-line Agent description label only (rule 1).
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
  if(r) return '<span class="plnlrun plnlrun-' + k + '" title="' + esc(T('Pipeline run') + ': ' + r.name + (r.cur ? ' · ' + plgShow(r.cur) : '')) + '"><i class="plnld plnld-' + k + (k === 'work' ? ' plnlpulse' : '') + '"></i>'
    + esc(T(PLNOW_ST[k]) + ' · ' + (r.cur ? plgShow(r.cur) : r.name)) + '</span>';   // display name, as the canvas
  if(runs.length) return '<span class="plnlrun plnlrun-done" title="' + esc(T('Pipeline run') + ': ' + runs[0].name + ' · ' + T('done')) + '">' + esc('✓ ' + runs[0].name + ' ' + T('done')) + '</span>';
  return sessPlChip(x);
}
// Subagent tree under a card = the Timeline's agent name cell (74b tlAgNmB): connector · logo · description · type · running dot.
// Live x.sub rows only; running first, quiet ones (no log write for PLNOW_QUIET s) dimmed; at most PLNOW_AGMAX, then «+N more».
// ⚠Metadata only: the Agent description label (rule 1); a [pl:name/stage] tag makes the row select that stage on the canvas.
const PLNOW_AGMAX = 6, PLNOW_QUIET = 120;
function plNowAgents(x){
  const subs = (x.sub || []).filter(a => a && a.lab), hot = a => !(a.idle > PLNOW_QUIET);
  const ord = subs.filter(hot).concat(subs.filter(a => !hot(a))), shown = ord.slice(0, PLNOW_AGMAX), more = ord.length - shown.length;
  if(!shown.length) return '';
  return '<div class=plnag>' + shown.map((a, i) => {
    const p = plLabParts(a.lab), d = plDescStage(a.lab), h = hot(a);
    const g = { sess: false, type: p.type || T('Agent'), plat: a.plat || x.plat || '', br: i === shown.length - 1 && !more ? '└' : '├', items: [{ aid: a.aid || a.tid || 'a', desc: p.desc }] };
    return '<button type=button class="plnagr tlnm' + (h ? '' : ' quiet') + '" data-pnagc="' + esc(x.cwd || '') + '" data-pnplat="' + esc(x.plat || '') + '"'
      + (d && d.name !== '-' ? ' data-pnname="' + esc(d.name) + '" data-pnst="' + esc(d.title) + '"' : '') + ' title="' + esc(plLabTip(a.lab)) + '"><b>' + tlAgNmB(g, h) + '</b></button>';
  }).join('') + (more > 0 ? '<div class=plnagm>' + esc(TV({msg: '+{n} more', vars: {n: more}})) + '</div>' : '') + '</div>';
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
      + (on ? ' aria-current=true' : '') + '>' + tlSessNmB({ sess: true, cwd: x.cwd || '', plat: x.plat || '', proj: x.project || '', items: [it] }, it, 0, 0, true) + plNowRun(x, k) + '</button>' + plNowAgents(x) + '</div>';
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
  const r = (x.plrun || []).find(q => q && q.name && !q.end) || (x.plm && x.plm.name ? { name: x.plm.name } : null);
  plNowGoProj((r && r.proj) || x.cwd || PLS.proj);
  PLS.nowSid = x.sid || '';   // ⚠after plNowGoProj: a project change clears nowSid
  if(r) PLS.sel = r.name;
  plPaint();
}
// Subagent row with a [pl:] tag → that stage selected once its project's data is there (plNowPickApply, from paintPipe).
// ⚠Selection only (same as a node click): never plFit / centre — a click must not move the view.
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
// Same reset as plPickProj (48 plProjGo), without its paint; an open arch-map panel (48h PLAG) would hide the picked pipeline.
function plNowGoProj(proj){
  plProjGo(proj);
  PLS.runSel = null; plAgSet(false);
}
document.addEventListener('click', e => {
  const t = e.target.closest && e.target.closest('.plw .plnl [data-pncwd],.plw .plnl [data-pnagc],.plw .plnl [data-pnfold]');
  if(!t) return;
  if(t.hasAttribute('data-pnagc')){   // subagent row: its session's run, then its stage (untagged: the session only)
    plNowPick(t.dataset.pnagc, t.dataset.pnplat);
    if(t.dataset.pnname){ PLS.sel = t.dataset.pnname; PLS.nowPick = { name: t.dataset.pnname, title: t.dataset.pnst }; plPaint(); }
    return;
  }
  if(t.hasAttribute('data-pnfold')){ if(plNowFolded()) lsDel('sidereus.plnowc'); else lsSet('sidereus.plnowc', '1'); plPaint(); return; }
  if(t.classList.contains('plnlrd')) lsDel('sidereus.plnowc');   // rail dot: expand, then pick
  plNowPick(t.dataset.pncwd, t.dataset.pnplat);
});
