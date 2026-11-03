// «Request a red check» in the 48i Evaluation panel (Red check cell): preview (recipient + exact body) → «Confirm» relays one
// mailbox message; the session runs the command on a temporary clone. ⚠Sidereus never runs the red check itself.
let PLRR = { k: '', stage: '', sid: '', pick: false, busy: false, sent: null, msg: '' };
const PLRR_OFF = 'Open a Claude Code session in this project and log in to the mailbox to request it';
function plRedReqState(){
  const p = typeof plCur === 'function' ? plCur() : null, k = PLS.proj + '\n' + ((p && p.name) || '');
  if(PLRR.k !== k) PLRR = { k, stage: '', sid: '', pick: false, busy: false, sent: null, msg: '' };   // another pipeline/project: no stale preview
  return PLRR;
}
// Pure: DM body (mailbox wire text, English): the exact command + one line on what to do with it. No tool output.
// ⚠Names the project path: the recipient may be a session of another repo (84l archChkCands tier 2), as in the archChk fix body.
function plRedReqBody(cmd, stage, name, repo){
  return String(cmd || '') + '\nTarget repository: ' + String(repo || '') + ' — work there (cd), not in your own cwd.'
    + '\nRun the command above in that repository: it red-checks the gate of stage ' + stage + ' (pipeline ' + name
    + ') on a temporary clone, so your working tree is untouched; reply with the result it prints.';
}
// Pure: cell button; disabled with the how-to tooltip while no live candidate is logged in to the mailbox.
function plRedReqBtn(stage, cands){
  const ok = (cands || []).some(c => c && c.login);
  return '<button type=button class="wkrgb plrrq" data-plrrq="' + esc(stage) + '"' + (ok ? '' : ' disabled title="' + esc(T(PLRR_OFF)) + '"') + '>' + esc(T('Request a red check')) + '</button>';
}
// Pure: preview block (S = PLRR) under the panel table; cmd = the stage's current red-check command (48i need[]).
function plRedReqHtml(S, cmd, cands){
  const sent = S && S.sent ? '<div class="archckst archsent plrrok" role=status><span aria-hidden=true>✓</span> ' + esc(T('Red check requested → {s} · {t}').replace('{s}', () => S.sent.to).replace('{t}', () => S.sent.at)) + '</div>' : '';
  const err = S && S.msg ? '<div class="archmsg archerr plrrer" role=alert>' + esc(S.msg) + '</div>' : '';
  if(!S || !S.stage || cmd == null) return sent + err;
  const cur = cands.find(x => x.sid === S.sid) || null, off = !cur ? T(PLRR_OFF) : !cur.login ? T('That session is not logged in to the mailbox') : '';
  const lab = x => archChkCandLabel(x) + (x.ran ? ' · ' + T('ran this pipeline') : '');   // metadata only (dir · sid · model · mailbox id)
  const to = cur && !S.pick ? '<span class=plsto>' + esc(lab(cur)) + '</span>' + (cands.length > 1 ? ' <button type=button class=wkrgb data-plrrch>' + esc(T('Change')) + '</button>' : '')
    : '<select data-plrrs>' + (cands.length ? cands.map(x => '<option value="' + esc(x.sid) + '"' + (x.sid === S.sid ? ' selected' : '') + '>' + esc(lab(x)) + '</option>').join('') : '<option value="">' + esc(T('None')) + '</option>') + '</select>';
  const body = plRedReqBody(cmd, S.stage, S.k.slice(S.k.indexOf('\n') + 1), S.k.slice(0, S.k.indexOf('\n')));
  return '<div class="archreq plrrv" role=group aria-label="' + esc(T('Request a red check')) + '"><div class=archrqh><b>' + esc(T('Request a red check')) + '</b><label>' + esc(T('To session')) + ' ' + to + '</label></div>'
    + '<pre class=archdm>' + esc(body) + '</pre><div class=archrqb><button type=button class="wkrgb archok" data-plrrgo' + (off || S.busy ? ' disabled' : '') + (off ? ' title="' + esc(off) + '"' : '') + '>'
    + esc(T(S.busy ? 'Sending…' : 'Confirm — send')) + '</button><button type=button class=wkrgb data-plrrx>' + esc(T('Cancel')) + '</button>' + (off ? '<span class=archwhy>' + esc(off) + '</span>' : '') + '</div></div>' + sent + err;
}
// The preview and the sent line render below the popover's visible area: bring the painted element into view (as 48i fix flow).
// ⚠Own marker classes: 48i's fix preview also uses .archreq/.archsent inside #plevp.
function plRedReqReveal(sel){ const el = document.querySelector('#plevp ' + sel); if(el && el.scrollIntoView) el.scrollIntoView({ block: 'nearest' }); }
// Current command for a stage, from the eval suggestions (null once a record exists for the gate text).
function plRedReqCmd(ev, stage){ const s = plEvalSgList(ev).find(x => x.code === 'redcheck' && x.stage === stage); return s ? String(s.cmd || '') : null; }
// Guard + send: only the preview's confirm calls this (no auto-send, AGENTS.md rule 7).
async function plRedReqSend(){
  const S = PLRR, p = plCur(), ev = p && plEvalOf(PLS.proj, p.name);
  if(!S.stage || S.busy || !p) return false;
  const cmd = plRedReqCmd(ev, S.stage), cur = plEvalCands().find(c => c.sid === S.sid);
  if(cmd == null || !cur || !cur.login) return false;
  S.busy = true; S.msg = ''; plPaint();
  try{
    const j = await postJSON('/api/dm', { to: cur.id, body: plRedReqBody(cmd, S.stage, p.name, PLS.proj), relay: true, sid: cur.sid, thread: 'redcheck',
      plreq: { kind: 'req', pipeline: 'redcheck', repo: PLS.proj, name: p.name, stage: S.stage } });
    if(!j || !j.ok) throw new Error((j && (j.error || j.err)) || '?');
    if(PLRR !== S) return true;   // switched pipeline meanwhile: the request went out, the old preview is gone
    S.busy = false; S.stage = ''; S.sent = { to: archChkCandLabel(cur), at: hhmm(new Date()) };
    note(T('Red check requested → {s} · {t}').replace('{s}', () => S.sent.to).replace('{t}', () => S.sent.at));
  }catch(e){ S.busy = false; S.msg = T('Could not send') + ': ' + String((e && e.message) || e); }
  plPaint();
  plRedReqReveal(S.msg ? '.plrrer' : '.plrrok');
  return true;
}
document.addEventListener('click', e => {
  const t = e.target && e.target.closest ? e.target : null;
  if(!t || !t.closest('#plevp')) return;
  const S = plRedReqState();
  let b;
  if((b = t.closest('[data-plrrq]'))){
    if(S.busy) return;
    if(S.stage === b.dataset.plrrq) S.stage = '';   // second press closes the preview
    else { S.stage = b.dataset.plrrq; S.pick = false; S.msg = ''; S.sid = (plEvalPick(plEvalCands()) || {}).sid || ''; }
    plPaint(); if(S.stage) plRedReqReveal('.plrrv'); return;
  }
  if(t.closest('[data-plrrch]')){ if(!S.busy){ S.pick = true; plPaint(); } return; }
  if(t.closest('[data-plrrx]')){ if(!S.busy){ S.stage = ''; plPaint(); } return; }
  if(t.closest('[data-plrrgo]')) plRedReqSend();
});
document.addEventListener('change', e => {
  const t = e.target;
  if(!t || !t.matches || !t.matches('#plevp [data-plrrs]') || PLRR.busy) return;
  PLRR.sid = t.value; plPaint();
});
