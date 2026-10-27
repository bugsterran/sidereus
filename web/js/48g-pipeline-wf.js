// «Workflow» view of the pipeline tab: Workflow-tool runs (SESS[].wf) drawn read-only, opened from the name list (PLS.wf).
// Metadata only (rule 1): phase titles, one-line agent labels, states, times — the agents.wf_runs allow-list.
// ⚠Runs named 'pipeline' are the pipeline runner: they light the pipeline canvas (48b plLight) and are never listed here.
// Live/just-finished runs (`wf`) + older finished ones (`wfh`, sessions._wf_sets: 6 h, newest 10) — ⚠only this view reads `wfh`.
function wfAll(x){ return (x && x.wf || []).concat(x && x.wfh || []); }
function wfProjRuns(proj){
  const out = [];
  (SESS || []).forEach(x => { if(x && proj && x.cwd === proj) wfAll(x).forEach(r => { if(r && r.id && r.name !== 'pipeline') out.push({ sid: x.sid, run: r }); }); });
  return out.sort((a, b) => (b.run.run - a.run.run) || ((b.run.end || 0) - (a.run.end || 0)));
}
// Declared phase titles (run.phases) first, then phases only agents name, in first-seen order.
function wfStages(run){
  const out = [], add = t => { t = String(t || ''); if(t && !out.includes(t)) out.push(t); };
  ((run && run.phases) || []).forEach(p => add(p && typeof p === 'object' ? p.title : p));
  ((run && run.agents) || []).forEach(a => add(a && a.phase));
  return out;
}
// {title: {st: run|fail|done|wait, n, sec}} — same states as the canvas lighting (48b plLight); a cut agent counts as a failure.
function wfLight(run){
  const out = {}, ags = (run && run.agents) || [];
  wfStages(run).forEach(t => {
    const a = ags.filter(x => x && x.phase === t);
    if(!a.length){ out[t] = { st: 'wait', n: 0, sec: 0 }; return; }
    const st = run.run && a.some(x => x.st === 'run') ? 'run' : a.some(x => x.st === 'fail' || x.st === 'cut') ? 'fail' : 'done';
    out[t] = { st, n: a.length, sec: Math.max(0, Math.max(...a.map(x => x.end || 0)) - Math.min(...a.map(x => x.start || 0))) };
  });
  return out;
}
// «Workflow» type badge for a Workflow-run agent row outside this tab (40b session tree, 70 timeline); run name + phase in the title only.
function wfBadge(name, phase){
  return '<i class="tlpar tlwfk wfbdg" title="' + esc(['Workflow', name || '', phase || ''].filter(Boolean).join(' · ')) + '">Workflow</i>';
}
// Run name of a timeline workflow-agent item (tid "wfa:<aid>|<sid>", par "wf:<id>") from SESS[].wf; '' when not in the list.
function wfRunNameOf(tid, par){
  const sid = String(tid || '').split('|')[1] || '', id = String(par || '').replace(/^wf:/, '');
  const x = (typeof SESS !== 'undefined' && SESS || []).find(s => s && s.sid === sid), r = x && wfAll(x).find(q => q && q.id === id);
  return (r && r.name) || '';
}
// Terminal-style run summary: finished / started agents · elapsed since run start · tokens (run.tok from agents.wf_runs, 0 = omitted).
function wfSum(run, now){
  const ags = (run && run.agents) || [], sec = Math.max(0, Math.round(((run && run.run) ? now : (run && run.end) || 0) - ((run && run.start) || 0)));
  return { done: ags.filter(a => a && a.st === 'done').length, total: ags.length, sec, tok: +(run && run.tok) || 0 };
}
function wfSumHtml(run, now){
  const s = wfSum(run, now);
  return '<span class=wfsum><i class=wfprog><i style="width:' + (s.total ? Math.round(100 * s.done / s.total) : 0) + '%"></i></i><b>' + esc(TV({msg: 'Agents {n}/{m}', vars: {n: s.done, m: s.total}})) + '</b>'
    + esc(' · ' + ago(s.sec) + (s.tok ? ' · ↓' + fmtTok(s.tok) + T(' tokens') : '')) + '</span>';
}
function wfFind(sid, id){
  const x = (SESS || []).find(s => s && s.sid === sid), r = x && wfAll(x).find(q => q && q.id === id && q.name !== 'pipeline');
  return r ? { x, r } : null;
}
// «Workflow» group in the name list: one button per run of this project, live dot after the name while it runs.
function wfBtns(proj){
  const rs = wfProjRuns(proj);
  if(!rs.length) return '';
  return '<span class=wfgrp><b>' + esc(T('Workflow')) + '</b>' + rs.map(o => '<button class="strp' + (PLS.wf && PLS.wf.sid === o.sid && PLS.wf.id === o.run.id ? ' on' : '') + (o.run.run ? ' plon' : '')
    + '" data-wfs="' + esc(o.sid) + '" data-wfi="' + esc(o.run.id) + '" title="' + esc((o.run.name || o.run.id) + ' · ' + sid8(o.sid) + (o.run.run ? ' · ' + T('Running') : '')) + '">'
    + esc(o.run.name || o.run.id) + (o.run.run ? '<i class=mvdot></i>' : '') + '</button>').join('') + '</span>';
}
const WF_ST = { run: ['Running', 'plrt-run'], done: ['Done', 'plrt-done'], fail: ['Failed', 'plrt-fail'], cut: ['Aborted', 'plrt-fail'] };
function wfBody(sid, id){
  const f = wfFind(sid, id);
  if(!f) return '';
  const r = f.r, lt = wfLight(r), now = Date.now() / 1000, mk = { run: '<i class=plspin></i>', done: '<b class=plok>✓</b>', fail: '<b class=plx>✕</b>', wait: '' };
  const head = '<div class=plbar><b>' + esc(r.name || r.id) + '</b>' + wfSumHtml(r, now) + '<span class="hidnote wfnote">' + esc(T('Workflow') + ' · ' + T('read-only') + ' · ' + sid8(sid) + ' · '
    + (r.run ? T('Running') : T('Last run'))) + '</span></div>';
  const ph = wfStages(r).map(t => { const L = lt[t]; return '<div class="wfnd pl-' + L.st + '"><div class=plt>' + mk[L.st] + esc(t) + '</div><div class=plls>'
    + esc(L.n ? T('Agent') + ' ' + L.n + ' · ' + ago(L.sec) : T('Waiting')) + '</div></div>'; }).join('<i class=wfarr>→</i>');
  const ags = (r.agents || []).slice().sort((a, b) => ((b.st === 'run') - (a.st === 'run')) || ((b.start || 0) - (a.start || 0)));
  const rows = ags.map(a => { const s = WF_ST[a.st] || WF_ST.done, live = a.st === 'run' && r.run;
    return '<tr data-wfw="' + esc(sid) + '"' + (/^a[0-9a-f]{6,40}$/.test(String(a.aid || '')) ? ' data-tid="' + esc(a.aid) + '"' : '') + (live ? ' class=on' : '') + '><td title="' + esc(a.lab || '') + '">' + esc(a.lab || '') + '</td><td title="' + esc(a.phase || '') + '">'
      + esc(a.phase || '') + '</td><td class=' + s[1] + '><span class=plrtpl>' + (live ? '<i class=plrtdot></i>' : '') + esc(T(s[0], 'stage')) + '</span></td><td>'
      + esc(ago(Math.max(0, Math.round((live ? now : (a.end || 0)) - (a.start || 0))))) + '</td></tr>'; }).join('');
  return head + '<div class=wfph>' + (ph || '<span class=hidnote>' + esc(T('No phases')) + '</span>') + '</div>'
    + '<div class=plrt><div class=plrth><b>' + esc(T('Agent') + ' ' + ags.length) + '</b></div><table class="plrtb wftb"><colgroup><col><col class=c2><col class=c4><col class=c5></colgroup><thead><tr><th>'
    + esc(T('Doing')) + '</th><th>' + esc(T('Stage')) + '</th><th>' + esc(T('Status')) + '</th><th>' + esc(T('Elapsed')) + '</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
}
document.addEventListener('click', e => {
  if(!e.target.closest || !e.target.closest('.plw')) return;
  const b = e.target.closest('[data-wfi]');
  if(b){ PLS.wf = { sid: b.dataset.wfs, id: b.dataset.wfi }; PLNEW = null; PLS.std = ''; PLS.diff = null; PLS.del = null; PLS.msg = ''; plPaint(); return; }
  const tr = e.target.closest('tr[data-wfw]');
  if(tr) plOpenWork(tr.dataset.wfw, tr.dataset.tid || '');   // workflow agents have no toolUseId: the agent id opens its own log
});
