// Pipeline request records (state `plReq`, PLREQ in 00-core): which session received an arch-map request,
// how far its run got, and the «Stop» relay. Metadata only: project · session id · mailbox id · state · stage title.
const ARCH_REQ_KEEP_MS = 3600000;   // a finished row (stopped/done/gone) stays as one muted line for an hour after the send
const ARCH_REQ_LBL = { sent: 'Sent', run: 'Running', stopping: 'Stopping', stopped: 'Stopped', done: 'Done', gone: 'No session' };
function archReqMs(r){ const t = +(r && r.at) || 0; return t < 1e12 ? t * 1000 : t; }   // server seconds or ms
// Pure: rows for repo p, newest first; malformed rows dropped.
function archReqRows(p){
  const l = p && typeof PLREQ !== 'undefined' && PLREQ ? PLREQ[p] : null;
  return (Array.isArray(l) ? l : []).filter(r => r && typeof r === 'object' && r.id && r.pipeline && ARCH_REQ_LBL[r.state]).sort((a, b) => archReqMs(b) - archReqMs(a));
}
function archReqLive(r){ return !!r && (r.state === 'sent' || r.state === 'run' || r.state === 'stopping'); }
// Pure: the newest row for pipeline pl; a finished one only within ARCH_REQ_KEEP_MS.
function archReqLast(p, pl, now){
  const r = archReqRows(p).find(x => x.pipeline === pl) || null;
  return r && !archReqLive(r) && (now || Date.now()) - archReqMs(r) > ARCH_REQ_KEEP_MS ? null : r;
}
// «Stop» only while the run is going (or a stop is pending) and the recipient is known.
function archReqStopOk(r){ return !!r && (r.state === 'run' || r.state === 'stopping') && !!r.to && !!r.sid; }
function archReqBusy(p, pl){ return archReqStopOk(archReqLast(p, pl)); }
// Pure: wire text of the stop instruction (English, mailbox text not UI); ⚠metadata only — no request body.
function archStopBody(pl, repo, of){
  return 'Stop pipeline ' + pl + ' for ' + repo + ' (request ' + of + '): let the running stage agent finish, dispatch no further stages, report and end.';
}
function archReqWho(r){ return [r.project || r.label || '', r.sid ? sid8(r.sid) : '', r.to || ''].filter(Boolean).join(' · '); }
// Pure: one status row; ⚠the stage title is a pipeline stage title (agent/user data): esc only, never T().
function archReqRowHtml(r, open){
  const st = esc(T(ARCH_REQ_LBL[r.state] || '?', 'pl request')) + (r.state === 'run' && r.stage ? ' · ' + esc(String(r.stage)) : '');
  return '<div class="archsent archpr' + (r.state === 'run' ? ' run' : archReqLive(r) ? '' : ' end') + '" role=status data-arpr="' + esc(r.id) + '" title="' + esc(r.pipeline + ' · ' + r.id) + '">'
    + (r.state === 'run' ? '<i class=archspin></i>' : '') + '<span>' + st + '</span><span class=archprw>' + esc(archReqWho(r)) + '</span>'
    + (archReqStopOk(r) && !open ? '<button type=button class="wkrgb archstop" data-arstop="' + esc(r.id) + '">' + esc(T('Stop', 'pl request')) + '</button>' : '') + '</div>';
}
// Pure: stop preview (rule 7: Sidereus composes this text, so it needs preview + confirm).
function archReqStopHtml(r, repo, busy){
  return '<div class=archreq role=group aria-label="' + esc(T('Stop request preview')) + '"><div class=archrqh><b>' + esc(T('Stop request preview')) + '</b>'
    + '<span>' + esc(T('To session')) + ' ' + esc(archReqWho(r)) + '</span></div><pre class=archdm>' + esc(archStopBody(r.pipeline, repo, r.id)) + '</pre><div class=archrqb>'
    + '<button type=button class="wkrgb archok" data-arstopgo' + (busy ? ' disabled' : '') + '>' + esc(T(busy ? 'Sending…' : 'Confirm — send')) + '</button>'
    + '<button type=button class=wkrgb data-arstopx>' + esc(T('Cancel')) + '</button></div></div>';
}
// Status slot with a record: row (+ stop preview); a live row replaces the transient line `s` (an open request preview `open` stays),
// a finished one sits above it. No record: `s` unchanged.
function archReqSlot(p, pl, s, open, now){
  const r = archReqLast(p, pl, now);
  if(!r) return s;
  const q = ARCH.pstop && ARCH.pstop.p === p && ARCH.pstop.id === r.id ? ARCH.pstop : null;
  return archReqRowHtml(r, !!q) + (q && archReqStopOk(r) ? archReqStopHtml(r, p, q.busy) : '') + (archReqLive(r) ? open || '' : s || '');
}
// Paint signature part (84j archPaint): ⚠without it a state change of the record never repaints the cached view.
function archReqSig(p){
  return JSON.stringify([archReqLast(p, ARCH_PL), ARCH.pstop || null, archSecRunSig(p)]);
}
// Pure: Structure tab banner for a live security-checks run of p — request record (receiver + «Stop») › server run line (no receiver, no «Stop»).
// ⚠the stage is the record's, else the server run's, else «Security check»; agent stage titles are esc only, never T().
function archSecRunHtml(p, now){
  const r = archReqLast(p, ARCH_SEC_PL, now), run = typeof archRunOf === 'function' ? archRunOf(p, ARCH_SEC_PL) : null;
  let h = '';
  if(archReqLive(r)){ const q = ARCH.pstop && ARCH.pstop.p === p && ARCH.pstop.id === r.id ? ARCH.pstop : null;
    h = archReqRowHtml(Object.assign({}, r, { stage: r.stage || (run && run.stage) || T('Security check') }), !!q) + (q && archReqStopOk(r) ? archReqStopHtml(r, p, q.busy) : ''); }
  else if(run) h = archRunHtml(run, now, ARCH_SEC_PL);
  return h ? '<div class="archck archsecrun">' + h + '</div>' : '';
}
function archSecRunSig(p){
  const r = archReqLast(p, ARCH_SEC_PL), run = typeof archRunOf === 'function' ? archRunOf(p, ARCH_SEC_PL) : null;
  return [r && [r.id, r.state, r.stage], run && [run.stage, run.n, run.sid]];
}
// ⚠archTick watches arch-map runs only: without this a security run's start/stage/end never repaints the Structure tab.
let ARCH_SEC_SIG = '';
setInterval(() => {
  if(typeof mainView === 'undefined' || mainView !== 'struct' || strMode !== 'arch' || document.hidden) return;
  const p = strOn[0] || '', s = JSON.stringify([p, archSecRunSig(p)]);
  if(s !== ARCH_SEC_SIG){ ARCH_SEC_SIG = s; paintStruct(); return; }
  const run = archRunOf(p, ARCH_SEC_PL), el = run && document.querySelector('.archsecrun [data-arel]');
  if(el) el.textContent = archRunEl(run, Date.now());
}, 5000);
// Guard + send: only the stop preview's confirm calls this (no auto-send).
async function archStopSend(){
  const q = ARCH.pstop;
  if(!q || q.busy) return false;
  const r = archReqRows(q.p).find(x => x.id === q.id);
  if(!archReqStopOk(r)) return false;
  q.busy = true; paintStruct();
  try{
    const j = await postJSON('/api/dm', { to: r.to, sid: r.sid, relay: true, thread: 'pipeline:' + r.pipeline, body: archStopBody(r.pipeline, q.p, r.id),
      plreq: { kind: 'stop', pipeline: r.pipeline, repo: q.p, of: r.id } });
    if(!j || !j.ok) throw new Error((j && (j.error || j.err)) || '?');
    ARCH.pstop = null; ARCH.msg = '';
  }catch(e){ q.busy = false; ARCH.msg = T('Could not send') + ': ' + String((e && e.message) || e); }
  paintStruct();
  return true;
}
document.addEventListener('click', ev => {
  const t = ev.target && ev.target.closest ? ev.target : null;
  if(!t || !t.closest('.archtab') || strMode !== 'arch') return;
  const p = strOn[0] || '';
  let b;
  if((b = t.closest('[data-arstop]'))){ ARCH.msg = ''; ARCH.pstop = { p, id: String(b.dataset.arstop || ''), busy: false }; paintStruct(); return; }
  if(t.closest('[data-arstopx]')){ if(ARCH.pstop && !ARCH.pstop.busy) ARCH.pstop = null; paintStruct(); return; }
  if(t.closest('[data-arstopgo]')) archStopSend();
});
