// ── Review queue: per-session review drawer (#rvpop) + mailbox relay preview (#rvq) ───────────────────────
//   Source: /api/state.review {n, rows:[{sid,cwd,root,branch,nf,add,del,done,since}]} (sidereus/review.py) — metadata only.
//   ★A human relay is within the rules (relaying is not direct control):
//     Sidereus only relays a human's words into the session's mailbox — always a preview of the exact body, sent on explicit confirm.
//   ⚠Never auto-send; recipient must be an identity-confirmed mailbox id (same rule as 36-wkcompose.js / sidereus/bus.py dm_send).
var REVIEW = null;   // ⚠var, not let: buildTodo (25) may read it before this file runs. Fed by poll from s.review.
let RV = {cwd: '', sid: '', files: null, done: false, err: '', rk: '', opener: null};
let RVQ = null;      // open relay preview {row, kind, to, body, opener}
// Labels go through T(v, 'order') ('Stop|order').
const RV_KINDS = {fix: 'Request changes', commit: 'Approve · ask to commit', stop: 'Stop', go: 'Continue', free: 'Write your own'};
function rvRows(){ return (REVIEW && Array.isArray(REVIEW.rows)) ? REVIEW.rows : []; }
function rvRowOf(sid){ return rvRows().find(r => r && r.sid === sid) || null; }
function rvKey(r){ return r ? [r.nf, r.add, r.del, r.done, r.since].join('|') : ''; }
// Mailbox recipient of a session row (Claude rows only — a Gemini row at the same cwd has no mailbox).
function rvTarget(sid){
  const x = (SESS || []).find(s => s.sid === sid && (!s.plat || s.plat === 'cc')) || null;
  const id = (x && x.mbox) || '', pr = (PRES || {})[id];
  return {id, login: !!(x && id && x.mboxSrc === 'identity'), blocked: !!(x && x.blocked),
          watch: !!(x && (x.mon || []).some(v => v && v.src === 'proc')) || !!(pr && pr.online && pr.source === 'watch')};
}
// /api/dm body cap from state().cfg.dmMax (CFG, when the poll exposes it); 20000 = sidereus/bus.py DM_MAX.
function rvDmMax(){ const c = typeof CFG !== 'undefined' ? CFG : null; return (c && +c.dmMax) || 20000; }
function rvBase(p){ const s = String(p || '').replace(/\/+$/, ''); return s.slice(s.lastIndexOf('/') + 1) || s; }
function rvHead(cwd, sid){
  const r = rvRowOf(sid) || {};
  return esc(rvBase(r.root || cwd)) + (r.branch ? '/' + esc(r.branch) : '') + ' · <code>' + esc(String(sid).slice(0, 8)) + '</code>';
}
// GET /api/review for one session -> {files, done}; throws with the server's error text.
async function rvFetch(cwd, sid){
  const j = await getJSON('/api/review?cwd=' + encodeURIComponent(cwd || '') + '&sid=' + encodeURIComponent(sid));
  if(!j || !j.ok) throw new Error((j && (j.error || j.err)) || '?');
  return {files: Array.isArray(j.files) ? j.files : [], done: !!j.done};
}
async function rvLoad(){
  const cwd = RV.cwd, sid = RV.sid;
  try{
    const j = await rvFetch(cwd, sid);
    if(RV.sid !== sid || RV.cwd !== cwd) return;
    RV.files = j.files; RV.done = j.done; RV.err = '';
  }catch(e){
    if(RV.sid !== sid) return;
    RV.err = e.message || '?'; if(!RV.files) RV.files = [];
  }
  rvPaint();
}
function rvPaint(){
  const p = document.getElementById('rvpop'); if(!p || p.hidden) return;
  const fs = RV.files, t = rvTarget(RV.sid), ok = t.login;
  const nOn = fs ? fs.filter(f => f.rv).length : 0, nAll = fs ? fs.length : 0, nCm = rvnLoad(RV.sid).length;
  const off = ok ? '' : ' disabled title="' + esc(T('Not logged into the mailbox — cannot receive')) + '"';
  let h = '<div class=rvh><b>' + esc(T('Review')) + '</b><span>' + rvHead(RV.cwd, RV.sid) + '</span>'
    + '<button type=button class=rvx data-a=x aria-label="' + esc(T('Close')) + '">✕</button></div>'
    + relayChipHtml(RV.sid, 'rvrl');
  if(!fs) h += '<div class=rvmsg>' + esc(T('Loading…')) + '</div>';
  else if(RV.err) h += '<div class="rvmsg err">' + esc(T('Could not fetch')) + ' — ' + esc(RV.err) + '</div>';
  else if(!nAll) h += '<div class=rvmsg>' + esc(T('No changes')) + '</div>';
  else h += '<ul class=rvl>' + fs.map((f, i) => '<li class="rvf' + (f.rv ? ' on' : '') + '">'
      + '<label title="' + esc(f.path) + '"><input type=checkbox data-i=' + i + (f.rv ? ' checked' : '') + '>'
      + '<span class=rvst>' + esc(f.st || '') + '</span><span class=rvp>' + esc(f.path) + '</span></label>'
      + '<span class=rvn><i class=a>+' + (+f.add || 0) + '</i> <i class=d>-' + (+f.del || 0) + '</i></span>'
      + '<button type=button class=rvd data-a=diff data-i=' + i + '>diff</button></li>').join('') + '</ul>';
  h += '<div class=rvft><span class=rvc>' + esc(T('{n}/{m} reviewed').replace('{n}', nOn).replace('{m}', nAll)) + '</span>'
    + '<button type=button data-a=all' + (nAll && nOn < nAll ? '' : ' disabled') + '>' + esc(T('Mark all reviewed')) + '</button>'
    + '<button type=button data-a=work>' + esc(T('Open work')) + '</button></div>'
    + '<div class=rvact>' + (nCm ? '<span class=rvcm title="' + esc(T('Line comments from the diff window — sent with «Request changes»')) + '">'
      + esc(T('{n} comments').replace('{n}', nCm)) + '</span>' : '')
    + '<button type=button data-a=fix' + off + '>' + esc(T('Request changes')) + '</button>'
    + '<button type=button data-a=commit' + off + '>' + esc(T('Approve (ask to commit)')) + '</button>'
    + (ok ? '' : '<span class=rvw>' + esc(T('Not logged into the mailbox — cannot receive')) + '</span>') + '</div>';
  setHtml(p, h);
}
// Optimistic mark; a failed POST restores the previous flags and says so via note().
function rvMark(idx, on){
  const fs = RV.files || [], cwd = RV.cwd, sid = RV.sid;
  const prev = fs.map(f => !!f.rv), body = {cwd, sid, on: !!on};
  if(idx === 'all') body.all = true; else if(fs[idx]) body.path = fs[idx].path; else return;
  fs.forEach((f, i) => { if(idx === 'all' || i === idx) f.rv = !!on; });
  rvPaint();
  postJSON('/api/review/mark', body).then(j => { if(!j || !j.ok) throw new Error((j && (j.error || j.err)) || '?'); })
    .catch(e => {
      if(RV.sid === sid && RV.files === fs){ fs.forEach((f, i) => { f.rv = prev[i]; }); rvPaint(); }
      note(T('Could not save the review mark') + ' — ' + e.message);
    });
}
function rvOpen(cwd, sid, opener){
  if(!cwd || !sid) return;
  if(popIsOpen('rvpop') && RV.sid === sid && RV.cwd === cwd) return rvLoad();
  RV = {cwd, sid, files: null, done: false, err: '', rk: rvKey(rvRowOf(sid)), opener: opener || document.activeElement};
  const p = popGet('rvpop', 'rvpop');
  p.setAttribute('role', 'dialog'); p.setAttribute('aria-label', T('Review'));
  p._sh = null; p.hidden = false; rvPaint();
  // Focus moves inside; the container (not a row) survives poll repaints.
  p.tabIndex = -1; p.focus({preventScroll: true});
  if(!p._wired){
    p._wired = true;
    p.addEventListener('change', e => {
      const c = e.target.closest && e.target.closest('input[data-i]'); if(c) rvMark(+c.dataset.i, c.checked);
    });
    p.addEventListener('click', e => {
      const b = e.target.closest && e.target.closest('[data-a]'); if(!b || b.disabled) return;
      const a = b.dataset.a, f = (RV.files || [])[+b.dataset.i];
      if(a === 'x') return rvClose(true);
      if(a === 'diff' && f) return loadDiff(RV.cwd, f.path, '', RV.sid);   // sid → line-comment gutter (88e)
      if(a === 'all') return rvMark('all', true);
      if(a === 'work') return openSession(RV.cwd, 'sess:' + RV.cwd + '|' + RV.sid);
      if(a === 'fix' || a === 'commit') return rvRelay(rvRowOf(RV.sid) || {cwd: RV.cwd, sid: RV.sid}, a, '', b);
    });
  }
  rvLoad();
}
function rvClose(focus){
  if(focus && popIsOpen('rvq')) return;   // ⚠Esc closes every open popover — let it shut only the relay preview first
  const op = RV.opener; RV.opener = null;
  if(popHide('rvpop', null, false) && focus && op && op.isConnected) op.focus({preventScroll: true});
}
// Poll hook (from buildTodo): reload the open drawer when its session's review row changed.
function rvTick(){
  if(!popIsOpen('rvpop')) return;
  const k = rvKey(rvRowOf(RV.sid));
  if(k !== RV.rk){ RV.rk = k; rvLoad(); } else rvPaint();
  if(RVQ && popIsOpen('rvq')) rvqPaint();
}
function rvFileLines(fs){ return fs.map(f => '- ' + f.path + ' (+' + (+f.add || 0) + '/-' + (+f.del || 0) + ')').join('\n'); }
function rvBody(kind, fs, text){   // relay body follows the UI language (KE); Korean bytes unchanged
  const extra = String(text || '').trim();
  if(kind === 'fix'){
    const un = fs.filter(f => !f.rv);
    return [T('Fix request — please re-check the files below.'), rvFileLines(un.length ? un : fs), extra].filter(Boolean).join('\n\n');
  }
  if(kind === 'commit') return [T('Review done. Please commit this change.'), rvFileLines(fs), extra].filter(Boolean).join('\n\n');
  if(kind === 'stop') return [T('Please stop — halt the current work and wait for the next instruction.'), extra].filter(Boolean).join('\n\n');
  if(kind === 'go') return [T('Please continue.'), extra].filter(Boolean).join('\n\n');
  return extra;
}
// rvRelay(row, kind, text, opener?) — row {sid, cwd}; kind = 'fix'|'commit'|'stop'|'go'|'free' or its label (RV_KINDS).
//   Opens the #rvq preview (exact body · recipient · watch status); sends only on the explicit «Send» click.
async function rvRelay(row, kind, text, opener, onSent, thread){   // onSent(to): after a confirmed send · thread: named DM thread (84e)
  if(!row || !row.sid) return false;
  const k = RV_KINDS[kind] ? kind : (Object.keys(RV_KINDS).find(x => RV_KINDS[x] === kind) || '');
  if(!k) return false;
  let fs = (RV.sid === row.sid && RV.files) ? RV.files : null;
  if(!fs && (k === 'fix' || k === 'commit')){
    try{ fs = (await rvFetch(row.cwd, row.sid)).files; }catch(e){ note(T('Could not fetch') + ' — ' + e.message); return false; }
  }
  const t = rvTarget(row.sid);
  let body = rvBody(k, fs || [], text), rvn = null;
  if(k === 'fix'){   // line comments (88e) ride along under DM_MAX; only the included ids are cleared after a confirmed send (rvqSend)
    const pk = rvnPack(rvnLoad(row.sid), rvDmMax() - 1000 - body.length - 2);   // 1000 = headroom under the server cap
    if(pk.text){ body += '\n\n' + pk.text; rvn = pk.ids; }
    if(pk.dropped) note(T('{n} comments left out by the length limit — send the rest in the next request').replace('{n}', pk.dropped));
  }
  RVQ = {row, kind: k, to: t.id, body, rvn, opener: opener || document.activeElement, busy: false, onSent, thread};
  const q = popGet('rvq', 'rvq');
  q.setAttribute('role', 'dialog'); q.setAttribute('aria-label', T('Message preview'));
  q._sh = null; q.hidden = false; rvqPaint();
  if(!q._wired){
    q._wired = true;
    q.addEventListener('click', e => {
      const b = e.target.closest && e.target.closest('[data-q]'); if(!b || b.disabled || !RVQ) return;
      if(b.dataset.q === 'ok') rvqSend(); else rvqClose(true);
    });
    q.addEventListener('input', e => {
      if(!RVQ || !e.target.matches('textarea')) return;
      RVQ.body = e.target.value;
      const ok = q.querySelector('[data-q=ok]'); if(ok) ok.disabled = !rvTarget(RVQ.row.sid).login || !RVQ.body.trim();
    });
  }
  // ⚠Never land on «Send» — one Enter would send. Sending needs a deliberate Tab/click.
  const ta = q.querySelector('textarea'), no = q.querySelector('[data-q=no]');
  (ta || no).focus({preventScroll: true});
  return true;
}
function rvqPaint(){
  const q = document.getElementById('rvq'); if(!q || q.hidden || !RVQ) return;
  const t = rvTarget(RVQ.row.sid), free = RVQ.kind === 'free';
  let w;
  if(!t.login) w = '<span class="rvw off">' + esc(T('Not logged into the mailbox — cannot receive')) + '</span>';
  else if(t.watch) w = '<span class="rvw on">● ' + esc(T('Mailbox watch')) + '</span>';
  else w = '<span class="rvw no">○ ' + esc(T('No mailbox watch')) + ' — ' + esc(T('Delivered when its next turn ends · if idle at the prompt, after the next input')) + '</span>';
  if(t.login && t.blocked) w += '<span class="rvw blk">' + esc(T('Waiting for permission — read on the next turn')) + '</span>';
  const h = '<div class=rvh><b>' + esc(T('Message preview')) + ' · ' + esc(T(RV_KINDS[RVQ.kind], 'order')) + '</b>'
    + (RVQ.thread ? ' <span class=rvw>⌗' + esc(RVQ.thread) + '</span>' : '') + '</div>'
    + '<div class=rvto>' + esc(T('To')) + ' <b>' + esc(t.id || '—') + '</b> ' + w + '</div>'
    + (free ? '<textarea class=rvta rows=6 placeholder="' + esc(T('Message to the session')) + '"></textarea>'
            : '<pre class=rvbd>' + esc(RVQ.body) + '</pre>')
    + '<div class=rvft><button type=button data-q=ok' + (t.login && (free || RVQ.body.trim()) && !RVQ.busy ? '' : ' disabled') + '>'
    + esc(T('Send')) + '</button><button type=button data-q=no>' + esc(T('Cancel')) + '</button></div>';
  if(setHtml(q, h) && free){
    const ta = q.querySelector('textarea'); ta.value = RVQ.body;   // value, not markup — typed text never becomes HTML
    const ok = q.querySelector('[data-q=ok]'); if(ok) ok.disabled = !t.login || !RVQ.body.trim() || RVQ.busy;
  }
}
async function rvqSend(){
  const a = RVQ; if(!a || a.busy) return;
  const t = rvTarget(a.row.sid), body = String(a.body || '').trim();
  if(!t.login || !t.id || !body) return;
  a.busy = true; rvqPaint();
  try{
    const j = await postJSON('/api/dm', Object.assign({to: t.id, body, relay: true, sid: a.row.sid}, a.thread ? {thread: a.thread} : {}));
    if(!j || !j.ok) throw new Error((j && (j.error || j.err)) || '?');
    note(T('Sent') + ' → ' + t.id);
    if(a.rvn){ rvnClear(a.row.sid, a.rvn); rvPaint(); }
    if(a.onSent){ try{ a.onSent(t.id); }catch(e){ softErr('rvq onSent', e); } }
    rvqClose(true);
    try{ await poll(); }catch(e){ softErr('rvqSend poll', e); }
  }catch(e){ a.busy = false; rvqPaint(); note(T('Could not send') + ': ' + T(e.message)); }
}
function rvqClose(focus){
  const op = RVQ && RVQ.opener; RVQ = null;
  if(popHide('rvq', null, false) && focus && op && op.isConnected) op.focus({preventScroll: true});
}
// ⚠Order matters: #rvpop first so its Esc handler can see #rvq still open and defer (rvClose).
popReg('rvpop', '#rvpop, #rvq, #todo .td.rv', rvClose);
popReg('rvq', '#rvq', rvqClose);
