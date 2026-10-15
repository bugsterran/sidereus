// ── Board «Select» mode: relay one message to several sessions (88b-board.js cards · #bdmq preview) ─────────
//   Pick cards (identity-confirmed mailboxes only — same rule as rvRelay's disable) → one preview listing every recipient
//   and the single body → on «Send», POST /api/dm once per recipient (relay + sid), sequential, stop on the first error.
// ⚠AGENTS.md rule 7: human-confirmed only — no auto-send; «Request changes» is left out (its body is per-session files + comments).
let bdSelOn = false, bdSel = [], bdSelMenu = false, BDMQ = null;   // BDMQ = open preview {sids, kind, body, busy}
const BD_MULTI = ['stop', 'go', 'commit', 'free'];
// Pure: why session `sid` cannot be picked ('' = pickable). t = rvTarget(sid).
function bdSelWhy(sid, t){
  if(!sid) return 'No session id';
  return (t && t.login && t.id) ? '' : 'Not logged into the mailbox — cannot receive';
}
// Pure: sel with sid added (on) or removed; order kept, no duplicates.
function bdSelToggle(sel, sid, on){ const s = (sel || []).filter(v => v !== sid); if(on && sid) s.push(sid); return s; }
// Pure: picked sids still on the board (tg = {sid: rvTarget}) and still pickable; order kept, deduped.
function bdSelKeep(sel, tg){
  const seen = new Set();
  return (sel || []).filter(s => { if(seen.has(s) || !tg || !tg[s] || bdSelWhy(s, tg[s])) return false; seen.add(s); return true; });
}
// Pure: preview recipients {sid, id, watch, blocked} for the picked sids.
function bdRcpt(sel, tg){ return bdSelKeep(sel, tg).map(s => ({sid: s, id: tg[s].id, watch: !!tg[s].watch, blocked: !!tg[s].blocked})); }
function bdTargets(sids){ const o = {}; (sids || []).forEach(s => { if(s) o[s] = rvTarget(s); }); return o; }
function bdModelSids(m){ const o = []; BD_COLS.forEach(c => m.cols[c[0]].forEach(k => { const s = (k.x && k.x.sid) || (k.r && k.r.sid); if(s) o.push(s); })); return o; }
// Called by brBoardHtml: drop picks that left the board or lost their mailbox identity.
function bdSelSync(m){ if(bdSelOn) bdSel = bdSelKeep(bdSel, bdTargets(bdModelSids(m))); }
function bdSelHead(){
  return '<button type=button class="bdsel' + (bdSelOn ? ' on' : '') + '" data-bdsel aria-pressed=' + bdSelOn
    + ' title="' + esc(T('Select mode — check cards to relay to several sessions at once')) + '">' + esc(T('Select')) + '</button>';
}
function bdSelCk(sid){
  if(!bdSelOn) return '';
  const why = bdSelWhy(sid, sid ? rvTarget(sid) : null), on = !why && bdSel.includes(sid);
  return '<label class="bdck' + (why ? ' off' : '') + '" title="' + esc(why ? T(why) : T('Select')) + '"><input type=checkbox data-bdck="'
    + esc(sid) + '"' + (on ? ' checked' : '') + (why ? ' disabled' : '') + ' aria-label="' + esc(T('Select') + ' ' + sid8(sid)) + '"></label>';
}
function bdSelBar(){
  if(!bdSelOn) return '';
  const n = bdSel.length;
  const menu = bdSelMenu && n ? '<div class=bdmenu role=menu>' + BD_MULTI.map(k => '<button role=menuitem data-bdsk=' + k + '>'
      + esc(T(RV_KINDS[k], 'order')) + '</button>').join('') + '</div>' : '';
  return '<div class=bdsbar role=toolbar aria-label="' + esc(T('Relay to several sessions')) + '"><b>' + esc(T('{n} selected').replace('{n}', n)) + '</b>'
    + '<span class=bdsrel><button type=button data-bdsm aria-haspopup=menu aria-expanded=' + (menu ? 'true' : 'false')
    + (n ? '' : ' disabled') + '>' + esc(T('Relay ▾')) + '</button>' + menu + '</span>'
    + '<button type=button data-bdsx' + (n ? '' : ' disabled') + '>' + esc(T('Clear selection')) + '</button></div>';
}
function bdSelFocus(q){ const n = document.querySelector('#feed ' + q); if(n) n.focus({preventScroll: true}); }
function bdSelMode(on){ bdSelOn = !!on; bdSel = []; bdSelMenu = false; brBoardPaint(); bdSelFocus('[data-bdsel]'); }
function bdmqOpen(kind){
  bdSelMenu = false; brBoardPaint();
  if(!BD_MULTI.includes(kind) || !bdSel.length) return;
  BDMQ = {sids: bdSel.slice(), kind, body: kind === 'free' ? '' : rvBody(kind, [], ''), busy: false};
  const q = popGet('bdmq', 'bdmq');
  q.setAttribute('role', 'dialog'); q.setAttribute('aria-label', T('Message preview'));
  q._sh = null; q.hidden = false; bdmqPaint();
  if(!q._wired){
    q._wired = true;
    q.addEventListener('click', e => {
      const b = e.target.closest && e.target.closest('[data-q]'); if(!b || b.disabled || !BDMQ) return;
      if(b.dataset.q === 'ok') bdmqSend(); else bdmqClose(true);
    });
    q.addEventListener('input', e => {
      if(!BDMQ || !e.target.matches('textarea')) return;
      BDMQ.body = e.target.value;
      const ok = q.querySelector('[data-q=ok]'); if(ok) ok.disabled = !bdRcpt(BDMQ.sids, bdTargets(BDMQ.sids)).length || !BDMQ.body.trim();
    });
  }
  // ⚠Never land on «Send» — one Enter would send to every recipient.
  const ta = q.querySelector('textarea'), no = q.querySelector('[data-q=no]');
  (ta || no).focus({preventScroll: true});
}
function bdmqName(sid){
  const x = (SESS || []).find(s => s && s.sid === sid) || {}, r = rvRowOf(sid) || {};
  return brBdName(x, r, x.cwd || r.cwd || '');
}
function bdmqPaint(){
  const q = document.getElementById('bdmq'); if(!q || q.hidden || !BDMQ) return;
  const a = BDMQ, tg = bdTargets(a.sids), rs = bdRcpt(a.sids, tg), free = a.kind === 'free';
  const li = a.sids.map(s => {
    const t = tg[s], why = bdSelWhy(s, t);
    const w = why ? '<span class="rvw off">' + esc(T(why)) + '</span>'
      : t.watch ? '<span class="rvw on">● ' + esc(T('Mailbox watch')) + '</span>'
      : '<span class="rvw no" title="' + esc(T('Delivered when its next turn ends · if idle at the prompt, after the next input')) + '">○ ' + esc(T('Stop hook')) + '</span>';
    return '<li><b>' + esc(bdmqName(s)) + '</b> <code>' + esc(sid8(s)) + '</code> ' + (t && t.id ? '<i>' + esc(t.id) + '</i> ' : '') + w
      + (!why && t.blocked ? '<span class="rvw blk">' + esc(T('Waiting for permission — read on the next turn')) + '</span>' : '') + '</li>';
  }).join('');
  const h = '<div class=rvh><b>' + esc(T('Message preview')) + ' · ' + esc(T(RV_KINDS[a.kind], 'order')) + '</b><span>'
      + esc(T('{n} recipients').replace('{n}', rs.length)) + '</span></div>'
    + '<ul class=bdml>' + li + '</ul>'
    + '<div class=bdmn>' + esc(T('Running sessions get it when the current turn ends; sessions waiting at the prompt get it after the next input.')) + '</div>'
    + (free ? '<textarea class=rvta rows=6 placeholder="' + esc(T('Message to the session')) + '"></textarea>' : '<pre class=rvbd>' + esc(a.body) + '</pre>')
    + '<div class=rvft><button type=button data-q=ok' + (rs.length && (free || a.body.trim()) && !a.busy ? '' : ' disabled') + '>'
    + esc(T('Send')) + '</button><button type=button data-q=no>' + esc(T('Cancel')) + '</button></div>';
  if(setHtml(q, h) && free){
    const ta = q.querySelector('textarea'); ta.value = a.body;   // value, not markup — typed text never becomes HTML
    const ok = q.querySelector('[data-q=ok]'); if(ok) ok.disabled = !rs.length || !a.body.trim() || a.busy;
  }
}
async function bdmqSend(){
  const a = BDMQ; if(!a || a.busy) return;
  const body = String(a.body || '').trim(), rs = bdRcpt(a.sids, bdTargets(a.sids));
  if(!body || !rs.length) return;
  a.busy = true; bdmqPaint();
  const sent = []; let err = '';
  for(const r of rs){   // sequential; stop on the first error so the report says exactly who got it
    try{
      const j = await postJSON('/api/dm', {to: r.id, body, relay: true, sid: r.sid});
      if(!j || !j.ok) throw new Error((j && (j.error || j.err)) || '?');
      sent.push(r.sid);
    }catch(e){ err = sid8(r.sid) + ': ' + T(e.message || '?'); break; }
  }
  // «Failed» = the one POST that errored; «Not sent» = never tried (after the stop, or dropped by bdRcpt)
  const fail = a.sids.length - sent.length, bad = err ? 1 : 0, skip = fail - bad;
  note(T('{n} sent · {m} failed').replace('{n}', sent.length).replace('{m}', bad) + (skip ? ' · ' + T('{n} not sent').replace('{n}', skip) : '')
    + (fail && sent.length ? ' — ' + T('Sent to') + ' ' + sent.map(sid8).join(', ') : '') + (err ? ' — ' + err : ''));
  bdSel = fail ? bdSel.filter(s => !sent.includes(s)) : [];   // unsent stay picked for a retry
  bdmqClose(true); brBoardPaint();
  try{ await poll(); }catch(e){ softErr('bdmqSend poll', e); }
}
function bdmqClose(focus){
  BDMQ = null;
  if(popHide('bdmq', null, false) && focus) bdSelFocus('[data-bdsm]');
}
popReg('bdmq', '#bdmq', bdmqClose);
// Runs after 88b's click listener, which ignores these targets (.bdck · .bdsbar · [data-bdsel]).
// ⚠Checkbox via click, not change: a repaint in the same click detaches the input and its change never bubbles.
document.addEventListener('click', e => {
  const t = e.target; if(!t || !t.closest) return;
  if(t.matches('input[data-bdck]')){
    bdSel = bdSelToggle(bdSel, t.dataset.bdck, t.checked); bdSelMenu = false; brBoardPaint();
    return bdSelFocus('[data-bdck="' + CSS.escape(t.dataset.bdck) + '"]');
  }
  if(bdSelMenu && !t.closest('.bdsbar .bdsrel')){ bdSelMenu = false; brBoardPaint(); }
  if(t.closest('[data-bdsel]')) return bdSelMode(!bdSelOn);
  const b = t.closest('.bdsbar button'); if(!b || b.disabled) return;
  if(b.hasAttribute('data-bdsm')){ bdSelMenu = !bdSelMenu; brBoardPaint(); if(bdSelMenu) bdSelFocus('.bdsbar .bdmenu button'); return; }
  if(b.hasAttribute('data-bdsx')){ bdSel = []; bdSelMenu = false; brBoardPaint(); return bdSelFocus('[data-bdsel]'); }
  if(b.dataset.bdsk) bdmqOpen(b.dataset.bdsk);
});
window.addEventListener('keydown', e => {
  if(e.key !== 'Escape' || !bdSelMenu || e.defaultPrevented || e.isComposing) return;
  e.preventDefault(); e.stopPropagation(); bdSelMenu = false; brBoardPaint(); bdSelFocus('[data-bdsm]');
}, true);
