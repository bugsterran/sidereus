// Work-popup compose (2026-09-24): DM the viewed session's mailbox id from the /work popup (same bus as the chat tab).
// ⚠Never auto-sends — only Enter or the button. One box follows the focused pane, so the draft survives pane switches.
let wkcSentAt = 0;           // last send from this popup (ms) — speeds up polling only while a reply may arrive
let wkcAsk = null;           // pending no-watch confirmation {to, body}
let wkcBusy = false;         // ⚠in-flight /api/dm — a double click on the confirm or a double Enter posted twice
let wkcHtml = '';
let wkcLast = null;         // {id, to} of the last DM sent from this popup — only its status is shown, never a body
// Recipient of the focused pane: the parent session's mailbox id (sub-agents share their session's cwd).
function wkcTarget(){
  const k = wtKeyOf(wtFocus) || wtPanes[0] || '';
  const t = (wtabs || []).find(x => x.key === k);
  if(!t) return null;
  const et = String(t.tid || '').indexOf('ext:') === 0 ? String(t.tid).slice(String(t.tid).indexOf('|') + 1) : '';
  // ⚠Gemini tab -> that sid only; Claude tab -> Claude rows only (a Gemini row at the same cwd has no mailbox)
  const rows = (SESS || []).filter(x => et ? x.sid === et : (x.cwd === t.cwd && (!x.plat || x.plat === 'cc')));
  const row = rows.find(x => x.state !== 'done') || rows[0] || null;
  const id = row && row.mbox || '';
  const pr = (PRES || {})[id];
  return {t, row, id,
    login: !!(row && id && row.mboxSrc === 'identity'),
    watch: !!(row && (row.mon || []).some(v => v && v.src === 'proc')) || !!(pr && pr.online && pr.source === 'watch'),
    blocked: !!(row && row.blocked), agent: t.kind === 'agent'};
}
// Replies: that id's DMs to me that answer this message (replyTo/thread), or arrive before my next DM to it.
function wkcReplies(m, next){
  return MSGS.filter(o => o.from === m.to && !o.room && o.t > m.t && (o.replyTo === m.id || (m.thread && o.thread === m.thread)
    || (MINE.includes(o.to) && !o.replyTo && (!next || o.t < next.t))));
}
function wkcStage(m, reps){
  const a = ACK[m.id] || {};
  if(reps.length) return 3;
  if((a.ack || []).some(x => x.who === m.to)) return 2;
  return 1;
}
// Status chips of the last DM sent from this popup (metadata only: delivery, ack, reply count).
function wkcStat(m){
  const reps = wkcReplies(m, null), st = wkcStage(m, reps), a = ACK[m.id] || {};
  const dlv = (a.delivered || []).includes(m.to) || (CUR[m.to] || 0) >= m.t;
  const step = (n, lab) => '<i class="wkcs'+(st >= n ? ' on' : '')+(st === n ? ' cur' : '')+'">'+esc(lab)+'</i>';
  return '<span class=wkcst>' + step(1, T(dlv ? 'Delivered' : 'Queued')) + '<em>→</em>' + step(2, T('acked'))   /* ⚠own key: «Confirm» (the button) has the same Korean word */
    + '<em>→</em>' + step(3, reps.length > 1 ? T('Reply') + ' ' + reps.length : T('Reply')) + '</span>';
}
function wkcPaint(){
  const box = document.getElementById('wkc');
  if(!box || !ISWP) return;
  box.hidden = false;
  const g = wkcTarget(), ta = document.getElementById('wkcbox'), btn = document.getElementById('wkcsend');
  const off = !g || !g.login;
  // ⚠This line is the send preview (Enter sends without a confirm) — keep the recipient visible.
  let h = '<span class=wkcto>→ <b>'+esc(g && g.id ? g.id : '—')+'</b>'
    + (g && g.agent ? ' <small>'+esc(T("(subagent's parent session)"))+'</small>' : '') + '</span>';
  if(off) h += '<span class="wkcw off">'+esc(T('Not logged into the mailbox — cannot receive'))+'</span>';
  else h += '<span class="wkcw '+(g.watch ? 'on' : 'no')+'">'+esc(g.watch ? '● '+T('Mailbox watch') : '○ '+T('No mailbox watch'))+'</span>';
  if(g && g.login && g.blocked) h += '<span class="wkcw blk">'+esc(T('Waiting for permission — read on the next turn'))+'</span>';
  const m = wkcLast && g && g.id === wkcLast.to ? MSGS.find(x => x.id === wkcLast.id) : null;
  if(m) h += wkcStat(m);
  if(h !== wkcHtml){ document.getElementById('wkch').innerHTML = h; wkcHtml = h; }
  ta.disabled = off; btn.disabled = off || !!wkcAsk || wkcBusy;
  ta.placeholder = off ? T('Not logged into the mailbox — cannot receive') : T('Message this session — Enter to send · Shift+Enter for newline');
  btn.textContent = T('Send');
  if(wkcAsk && (!g || g.id !== wkcAsk.to)) wkcCancel();   // focus moved to another session — drop the stale confirmation
}
function wkcCancel(){ wkcAsk = null; const q = document.getElementById('wkcq'); q.hidden = true; q.innerHTML = ''; wkcPaint(); }
async function wkcPost(to, body){
  const btn = document.getElementById('wkcsend'), ta = document.getElementById('wkcbox');
  if(wkcBusy) return;
  wkcBusy = true; btn.disabled = true;
  try{
    const j = await postJSON('/api/dm', {to, body});
    if(!j || !j.ok) throw new Error((j && j.error) || '?');
    wkcLast = {id: j.id, to};
    if(ta.value.trim() === body) { ta.value = ''; ta.style.height = 'auto'; }
    wkcSentAt = Date.now();
    await poll();
  }catch(e){ note(T('Could not send') + ': ' + T(e.message)); }
  finally{ wkcBusy = false; wkcAsk = null; const q = document.getElementById('wkcq'); q.hidden = true; q.innerHTML = ''; wkcPaint(); ta.focus(); }
}
function wkcSend(){
  const ta = document.getElementById('wkcbox'), body = ta.value.trim(), g = wkcTarget();
  if(!body || !g || !g.login || wkcAsk) return;
  if(g.watch) return wkcPost(g.id, body);
  // No watcher: the message waits in the mailbox — ask first, never send on the same keystroke.
  wkcAsk = {to: g.id, body};
  const q = document.getElementById('wkcq');
  q.innerHTML = '<span>'+esc(T('This session cannot receive right now — it waits in the mailbox and is read when a watcher starts or a mailbox tool is called. Send anyway?'))+'</span>'
    + '<button type=button data-q=ok>'+esc(T('Send'))+'</button><button type=button data-q=no>'+esc(T('Cancel'))+'</button>';
  q.hidden = false;
  wkcPaint();
  q.querySelector('[data-q=ok]').focus();
}
// Piggybacks on the popup's 2.5s work-log tick: a light incremental poll only for 10 min after a send.
let wkcLastPoll = 0;
function wkcTick(){
  if(!ISWP || !wkcSentAt || Date.now() - wkcSentAt > 600000 || Date.now() - wkcLastPoll < 5000) return;
  wkcLastPoll = Date.now(); poll();
}
window.addEventListener('DOMContentLoaded', () => {
  const ta = document.getElementById('wkcbox'), q = document.getElementById('wkcq');
  if(!ta || !ISWP) return;
  document.getElementById('wkcsend').onclick = wkcSend;
  ta.addEventListener('input', () => { ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 140) + 'px'; });
  ta.addEventListener('keydown', e => { if(e.key === 'Enter' && !e.shiftKey && !e.isComposing){ e.preventDefault(); wkcSend(); } });
  q.addEventListener('click', e => {
    const b = e.target.closest && e.target.closest('[data-q]'); if(!b || !wkcAsk) return;
    if(b.dataset.q === 'ok'){ const a = wkcAsk; wkcPost(a.to, a.body); } else wkcCancel();
  });
});
