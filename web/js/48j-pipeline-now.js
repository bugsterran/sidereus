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
    const p = plLabParts(a.lab), d = plDescStage(a.lab), h = hot(a), tip = plLabTip(a.lab) + ' · ' + T(h ? 'Running' : 'Idle');   // state in words, not only the dot/dimming
    const g = { sess: false, type: p.type || T('Agent'), plat: a.plat || x.plat || '', br: i === shown.length - 1 && !more ? '└' : '├', items: [{ aid: a.aid || a.tid || 'a', desc: p.desc }] };
    return '<button type=button class="plnagr tlnm' + (h ? '' : ' quiet') + '" data-pnagc="' + esc(x.cwd || '') + '" data-pnplat="' + esc(x.plat || '') + '" data-pntid="' + esc(subWorkId(a)) + '"'
      + (d && d.name !== '-' ? ' data-pnname="' + esc(d.name) + '" data-pnst="' + esc(d.title) + '"' : '') + ' title="' + esc(tip) + '" aria-label="' + esc(tip) + '"><b>' + tlAgNmB(g, h) + '</b></button>';
  }).join('') + (more > 0 ? '<div class=plnagm>' + esc(TV({msg: '+{n} more', vars: {n: more}})) + '</div>' : '') + '</div>';
}
// Status: need = blocked on the person · work = a turn is running, or (turn ended, 'wait') its open run / a live subagent / an open bg task still works · idle = else.
// ⚠One predicate for the row, the rail dot and the canvas (plPrLive): state alone read «Idle» while tagged background work ran.
function plNowSt(x){
  if(x.blocked || x.state === 'ask') return 'need';
  if(['tool', 'think', 'run', 'sent', 'stopping'].includes(x.state)) return 'work';
  const run = (x.plrun || []).some(r => r && !r.end && plPrLive(r)), sub = (x.sub || []).some(a => a && !(a.idle > PLNOW_QUIET));
  return run || sub || (x.bgs || []).length ? 'work' : 'idle';
}
const PLNOW_ST = { work: 'Working', need: 'Needs you', idle: 'Idle' };
// Plain-text run summary for the row's aria-label (the visible summary carries its state by colour/dot too).
function plNowRunTxt(x){
  const runs = (x.plrun || []).filter(r => r && r.name), r = runs.find(q => !q.end), n = x.plNone;
  if(r) return r.cur ? plgShow(r.cur) : r.name;
  if(runs.length) return runs[0].name + ' ' + T('done');
  if(n && n.cat) return T('No pipeline') + ' · ' + n.cat;
  return n && n.u ? T('Undeclared') : '';
}
function plNowList(ss){
  const live = plNowLive(ss === undefined ? SESS : ss), c = plNowFolded();
  const fold = '<button type=button class=plnlf data-pnfold aria-expanded="' + (c ? 'false' : 'true') + '" title="' + esc(T(c ? 'Expand list' : 'Collapse list'))
    + '" aria-label="' + esc(T(c ? 'Expand list' : 'Collapse list')) + '">' + (c ? '›' : '‹') + '</button>';
  const head = '<div class=plnlh>' + (c ? '' : '<b>' + esc(T('Working now')) + '</b><small class=plnln>' + live.length + '</small>') + fold + '</div>';
  // Collapsed rail: one dot per live session; hover/focus shows the floating label (plNowTip, data-pnlp/pnls); a dot click expands and picks it.
  if(c) return '<aside class="plnl plnlc">' + head + live.map(x => { const k = plNowSt(x), on = !!PLS.nowSid && x.sid === PLS.nowSid, st = T(PLNOW_ST[k]); return '<button type=button class="plnlrd plnld-' + k + (k === 'work' ? ' plnlrp' : '') + (on ? ' on' : '') + '" data-pncwd="' + esc(x.cwd || '')
    + '" data-pnplat="' + esc(x.plat || '') + '" data-pnlp="' + esc(x.project || '') + '" data-pnls="' + esc([st, plNowRunTxt(x)].filter(Boolean).join(' · ')) + '" aria-label="' + esc((x.project || '') + ' · ' + st) + '"' + (on ? ' aria-current=true' : '') + '></button>'; }).join('') + '</aside>';
  const hc = typeof hcRow === 'function' ? hcRow('pl') : '';   // «Connect» notice for CLIs without Sidereus hooks (90f); expanded list only
  if(!live.length) return '<aside class=plnl>' + head + '<div class=plnle>' + esc(T('No sessions working now')) + '</div>' + hc + '</aside>';
  // Row = the Timeline's session name cell (74b tlSessNmB, bare: no time/token chips) + the run summary; one button per (cwd, plat).
  return '<aside class=plnl>' + head + live.map(x => {
    const on = !!PLS.nowSid && x.sid === PLS.nowSid, k = plNowSt(x), it = { cwd: x.cwd || '', plat: x.plat || '', state: k === 'work' && x.state === 'wait' ? 'run' : x.state, blocked: x.blocked, idle: x.ageSec };   // dot agrees with plNowSt (list item only, x untouched)
    const st = T(PLNOW_ST[k]), al = [x.project || '', st, plNowRunTxt(x)].filter(Boolean).join(' · ');   // ⚠project is user data: never through T()
    return '<div class="plnlr' + (on ? ' on' : '') + '"><button type=button class="plnli tlnm' + (on ? ' on' : '') + '" data-pncwd="' + esc(x.cwd || '') + '" data-pnplat="' + esc(x.plat || '') + '" title="' + esc((x.project || '') + '\n' + st) + '" aria-label="' + esc(al) + '"'
      + (on ? ' aria-current=true' : '') + '>' + tlSessNmB({ sess: true, cwd: x.cwd || '', plat: x.plat || '', proj: x.project || '', items: [it] }, it, 0, 0, true) + plNowRun(x, k) + '</button>' + plNowAgents(x) + '</div>';
  }).join('') + hc + '</aside>';
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
// Follow live runs (from paintPipe): a new run is picked when no live run is viewed; the viewed one ending moves to the newest left.
// ⚠First call (reload): every run counts as new, so the newest live run opens only when nothing live is shown; a live view never jumps. Memory only (no prefs of its own); never plPaint / plFit — the view must not move.
let PLNOW_SEEN = null, PLNOW_VKEY = '';
// Working = a stage running (plPrLive, as the row status) or one that ran within PLNOW_GRACE s.
// ⚠An open run whose stages all wait is not working: counting it held the selection on an idle run. The grace keeps a run between two stages from flip-flopping.
const PLNOW_GRACE = 120;
function plNowWorking(r, now){
  if(plPrLive(r)) return true;
  const S = r.stages || {};
  return Object.keys(S).some(t => S[t] && (S[t].t1 || 0) >= now - PLNOW_GRACE);
}
function plNowFollow(ss){
  const cur = {}, now = Date.now() / 1000;
  // ⚠not plNowLive: its cwd+plat dedup keeps whichever session comes first in this poll
  (ss || []).filter(x => x && !['done', 'abort', 'gone'].includes(x.state)).forEach(x => (x.plrun || []).forEach(r => { if(r && r.name && !r.end && plNowWorking(r, now)) cur[x.sid + '\n' + r.name + '\n' + (r.rid != null ? r.rid : r.t0)] = { sid: x.sid, proj: r.proj || x.cwd, name: r.name, t0: r.t0 || 0 }; }));
  const viewed = () => {
    const p = plCur(), lv = p && plLiveRun(PLS.proj, p.name);
    if(lv && !lv.pr) return lv.run && lv.run.run ? 'wf\n' + lv.sid + '\n' + p.name : '';   // ⚠Workflow run (x.wf): no pr, still a viewed live run
    const k = lv && !lv.pr.end ? lv.sid + '\n' + p.name + '\n' + lv.pr.rid : '';
    return k && cur[k] ? k : '';
  };
  const seen = PLNOW_SEEN || {};
  PLNOW_SEEN = cur;
  const p = plCur(), edit = !!(p && p.ok && p.sha && !plWatchFor(p));   // ⚠only a real Edit view blocks: no saved pipeline / loading still shows the run view
  if(PLS.runSel || edit || PLS.wf || PLAG || PLS.std || PLS.diff || PLS.del || PLNEW || PLDRAFT){ PLNOW_VKEY = viewed(); return; }   // Edit / past run: track only
  const v = viewed();
  if(v){ PLNOW_VKEY = v; return; }   // a live run is viewed: later runs only show as running
  const ks = Object.keys(cur), newest = a => a.reduce((b, k) => (!b || cur[k].t0 > cur[b].t0 ? k : b), '');
  const k = PLNOW_VKEY && !cur[PLNOW_VKEY] ? newest(ks) : newest(ks.filter(q => !seen[q]));
  if(k){ const e = cur[k]; plNowGoProj(e.proj); PLS.nowSid = e.sid; PLS.sel = e.name; }   // same steps as plNowPick, without its paint
  PLNOW_VKEY = viewed() || k;
}
// Same reset as plPickProj (48 plProjGo), without its paint; an open arch-map panel (48h PLAG) would hide the picked pipeline.
function plNowGoProj(proj){
  plProjGo(proj);
  PLS.runSel = null; plAgSet(false);
}
// Rail dot label: one shared fixed element on <body>, because the rail scrolls (overflow:auto) and would clip a ::after.
function plNowTip(p, s){ return '<b>' + esc(p || '') + '</b><span>' + esc(s || '') + '</span>'; }   // ⚠project is user data: esc only, never T()
function plNowTipHide(){ const d = document.getElementById('plnltip'); if(d) d.remove(); }
function plNowTipShow(b){
  let d = document.getElementById('plnltip');
  if(!d){ d = document.createElement('div'); d.id = 'plnltip'; d.setAttribute('aria-hidden', 'true'); document.body.appendChild(d); }
  d.innerHTML = plNowTip(b.dataset.pnlp, b.dataset.pnls);
  const r = b.getBoundingClientRect();
  d.style.left = (r.right + 6) + 'px'; d.style.top = (r.top + r.height / 2) + 'px';
}
function plNowTipOn(e){ const b = e.target.closest && e.target.closest('.plw .plnlrd'); if(b) plNowTipShow(b); else plNowTipHide(); }
document.addEventListener('mouseover', plNowTipOn);
document.addEventListener('focusin', plNowTipOn);
document.addEventListener('focusout', plNowTipHide);
document.addEventListener('scroll', plNowTipHide, true);   // ⚠the label is fixed: a scrolling rail would leave it beside the wrong dot
document.addEventListener('click', e => {
  const t = e.target.closest && e.target.closest('.plw .plnl [data-pncwd],.plw .plnl [data-pnagc],.plw .plnl [data-pnfold]');
  if(!t) return;
  if(t.hasAttribute('data-pnagc')){   // subagent row: its session's run, then its stage (untagged: the session only), then its work-log popup
    plNowPick(t.dataset.pnagc, t.dataset.pnplat);
    if(t.dataset.pnname){ PLS.sel = t.dataset.pnname; PLS.nowPick = { name: t.dataset.pnname, title: t.dataset.pnst }; plPaint(); }
    if(t.dataset.pntid) openAgent(t.dataset.pnagc, t.dataset.pntid);   // same popup as a Timeline agent row (rule 1 exception: click only)
    return;
  }
  if(t.hasAttribute('data-pnfold')){ if(plNowFolded()) lsDel('sidereus.plnowc'); else lsSet('sidereus.plnowc', '1'); plPaint(); return; }
  if(t.classList.contains('plnlrd')) lsDel('sidereus.plnowc');   // rail dot: expand, then pick
  plNowPick(t.dataset.pncwd, t.dataset.pnplat);
});
