function buildInvite(){
  const b = document.getElementById('sinv');
  if(!b) return;
  // ★Kept **visible** even before selection. Hidden, nobody knows the feature
  //   exists — the checkbox is 13px and unnoticeable. One line of guidance does that job.
  if(!picked.size){
    if(b.className !== 'sinv on idle') b.className = 'sinv on idle';
    setHtml(b, '<div class=t>' + T('Pick sessions to <b>invite to a room</b> — use the checkbox at the left of each row') + '</div>');
    return;
  }
  const ids = [...picked];
  const rooms = Object.keys(ROOMS||{});
  // ⚠Inviting writes rooms.json and sends DMs: the server's dry body is shown first and only «Confirm» sends it (as `expect`).
  if(invPv && invPv.key !== invKey()) invPv = null;
  if(invPv){
    if(b.className !== 'sinv on') b.className = 'sinv on';
    const d = invPv, add = Array.isArray(d.added) ? d.added : [], al = Array.isArray(d.already) ? d.already : [];
    setHtml(b, '<div class=t>' + esc(T(d.isNew ? "Create room '{m}' and invite {n}" : "Invite DM to {n} into '{m}'")
        .replace('{n}', d.body == null ? ids.length : add.length).replace('{m}', () => d.room)) + '</div>'
      + (d.body == null ? '' : '<div class=t>' + add.map(esc).join(', ')
        + (al.length ? ' · ' + esc(T('Already there')) + ': ' + al.map(esc).join(', ') : '') + '</div>')
      + '<pre class=c style="white-space:pre-wrap;max-height:180px;overflow:auto">' + esc(d.err ? T('Failed') + ': ' + d.err : d.body == null ? T('Loading…') : d.body) + '</pre>'
      + '<div class=r><button id=invok' + (typeof d.body === 'string' && add.length && !d.busy ? '' : ' disabled') + '>' + esc(T('Confirm')) + '</button>'
      + '<button id=invno style="background:#2a3542">' + esc(T('Cancel')) + '</button></div>');
    const ok = document.getElementById('invok'), no = document.getElementById('invno');
    if(no) no.onclick = () => { invPv = null; buildInvite(); };
    if(ok) ok.onclick = () => {
      if(!invPv || typeof invPv.body !== 'string' || invPv.busy) return;
      const p = invPv; p.busy = true; ok.disabled = true;
      postJSON('/api/room/invite', {room: p.room, ids: p.ids, expect: p.body})
        .then(j=>{
          note(TV(j) || (j.ok ? T('Invited') : T('Could not invite')));
          if(j.ok){ invPv = null; picked.clear(); inviteRoom=''; buildSessions(); poll(); }
          else if(invPv === p){ invPreview(p.room); }   // e.g. stale: rebuild the preview before «Confirm» again
        }).catch(()=>{ p.busy = false; note(T('Could not invite — check the server')); buildInvite(); });
    };
    return;
  }
  const focused = document.activeElement && document.activeElement.id === 'invroom';
  if(!focused){
    if(b.className !== 'sinv on') b.className = 'sinv on';
    setHtml(b, '<div class=t>'+TV({msg: 'Selected <b>{n}</b> — ', vars: {n: ids.length}})+ids.map(esc).join(', ')+'</div>'
      + '<div class=r><input id=invroom list=invrooms placeholder="'+esc(T('Room name (created if it does not exist)'))+'" value="'+esc(inviteRoom)+'">'
      + '<button id=invgo'+(inviteRoom.trim()?'':' disabled')+'>'+esc(T('Invite'))+'</button></div>'
      + '<datalist id=invrooms>'+rooms.map(r=>'<option value="'+esc(r)+'">').join('')+'</datalist>'
      + '<div class=c>'+esc(T('This only invites — each session decides whether to join. It also lands in their inbox.'))+'</div>');
  }
  const inp = document.getElementById('invroom');
  const go  = document.getElementById('invgo');
  if(inp && !inp.oninput){
    inp.oninput = () => { inviteRoom = inp.value; if(go) go.disabled = !inp.value.trim(); };
    inp.onkeydown = (e) => { if(e.key === 'Enter' && inp.value.trim()) send(); };
  }
  function send(){
    const room = (document.getElementById('invroom')||{}).value || inviteRoom;
    if(!room.trim()) return;
    inviteRoom = room;
    invPreview(room.trim());
  }
  if(go) go.onclick = send;
}
let invPv = null;   // drawer invite preview: {key, room, ids, isNew, body?, added?, already?, err?, busy?}
const invKey = () => JSON.stringify([inviteRoom.trim(), [...picked].sort()]);
// Dry POST (nothing written); the answer is dropped if the picks or room changed meanwhile.
function invPreview(room){
  const key = invKey(), ids = [...picked];
  const p = invPv = {key, room, ids, isNew: !Object.prototype.hasOwnProperty.call(ROOMS||{}, room)};
  buildInvite();
  postJSON('/api/room/invite', {room: room, ids: ids, dry: true}).then(j=>{
    if(invPv !== p) return;
    if(j && j.ok && typeof j.body === 'string'){ p.body = j.body; p.added = j.added; p.already = j.already; }
    else p.err = (j && (j.error || j.msg)) ? TV({msg: j.error || j.msg, vars: j.vars}) : T('unknown error');
    buildInvite();
  }).catch(()=>{ if(invPv === p){ p.err = T('Could not invite — check the server'); buildInvite(); } });
}

// ★No redraw while the mouse is over the list (measured 2026-08-26: tooltips never appeared).
//   The browser's native tooltip waits ~1s before showing, but polling replaces innerHTML every 2.5s,
//   so the element vanishes in between and the tooltip never shows. It is the only way to see truncated text, so this is blocked.
//   When the mouse leaves, draw once then (pending updates are not lost).
let sessHover = false, sessDirty = false;
document.addEventListener('mouseover', e => {
  const on = !!(e.target.closest && e.target.closest('#sess'));
  if(on !== sessHover){
    sessHover = on;
    if(!on && sessDirty){ sessDirty = false; buildSessions(); }
  }
});

// ── Global search palette (Cmd+K) ──────────────────────────────────────────────
// ★With dozens of sessions the three filters can't find «that session» — narrowing and finding are different jobs.
// ⚠Only **metadata** is scanned (project · cwd · session id · model · state label · platform name).
//   `task`/`reply` are phrases pulled from conversations — do not include them (this page's rule #1).
let cpOn = false, cpSel = 0, cpRows = [], cpFlash = '';
function cpHay(x){
  const p = (x && AILG[x.plat]) ? x.plat : 'cc';
  return [x.project||'', x.cwd||'', x.id||'', x.sid||'', x.model||'',
          x.state||'', stateLbl(x.state||'unknown'), platHay(p)].join(' ').toLowerCase();
}
// Pure function — doesn't touch the DOM (callable directly from node). Every whitespace-separated word must match.
function cpMatch(q, list){
  const arr = (list||[]).slice();
  const s = String(q == null ? '' : q).trim().toLowerCase();
  if(!s) return arr;                     // empty input returns the list as-is — visible right on open
  const ws = s.split(/\s+/);
  return arr.filter(x => { const h = cpHay(x); return ws.every(w => h.indexOf(w) >= 0); });
}
function cpPaint(){
  const box = document.getElementById('cmdkl');
  if(!box) return;
  const q = (document.getElementById('cmdkq')||{}).value || '';
  cpRows = cpMatch(q, SESS);
  if(cpSel >= cpRows.length) cpSel = Math.max(0, cpRows.length - 1);
  if(!cpRows.length){ box.innerHTML = '<div class=cmdke>'+T('No matching sessions.')+'</div>'; return; }
  box.innerHTML = cpRows.map((x, i) =>
    '<div class="cmdki'+(i === cpSel ? ' on' : '')+'" data-i="'+i+'">'
    + aiLogo(x.plat) + '<span class=cmdkp>'+esc(x.project||'?')+'</span>'
    + '<span class=cmdks>'+esc(sessLabel(x))+'</span>'
    + (x.model ? '<span class=cmdkm>'+esc(x.model)+'</span>' : '')
    + '<span class=cmdkc title="'+esc((x.cwd||'')+(x.id?' · '+x.id:''))+'">'+esc(x.cwd||'')+'</span>'
    + '</div>').join('');
  const cur = box.querySelector('.cmdki.on');
  if(cur) cur.scrollIntoView({block:'nearest'});
}
function cpOpen(){
  const el = document.getElementById('cmdk'), q = document.getElementById('cmdkq');
  if(!el || !q) return;
  if(ISPOP || ISWP || ISBP) return;   // ⚠popups have no session list, and diff consumes Esc first, closing the window
  if(!cpOn) cpRet = document.activeElement;   // opener, restored on close (else focus falls to BODY)
  cpOn = true; cpSel = 0; q.value = '';
  el.classList.add('on'); cpPaint(); q.focus();
}
let cpRet = null;
function cpClose(){
  cpOn = false;
  const el = document.getElementById('cmdk');
  if(el) el.classList.remove('on');
  const r = cpRet; cpRet = null;
  if(r && r !== document.body && r.isConnected && typeof r.focus === 'function' && (!el || !el.contains(r))) r.focus({preventScroll: true});   // ⚠preventScroll: cpGo scrolls to the row right after
}
// Takes you **to the row** of the chosen session. ⚠If the row is hidden by a filter or fold, that is undone first —
//   otherwise "I picked it and nothing happened".
// key pointing to the row — sid if present, else cwd (external rows always have a sid)
function cpKey(x){ return (x && x.sid) ? 's:'+x.sid : 'c:'+((x && x.cwd) || ''); }
function cpGo(x){
  cpClose();
  if(!x) return;
  const undone = [];                               // if something the user set was undone, **say so**
  try{ sesdrReveal(); }catch(e){ softErr('sesdrReveal', e); }                  // the list lives in the top-right drawer — open it before scrolling
  if(x.state === 'done') sessOpen = true;          // inside the folded finished list it must be expanded to show
  cpFlash = cpKey(x);
  const find = () => {
    const ns = Array.prototype.slice.call(document.querySelectorAll('#sess .sxw'));
    return (x.sid ? ns.find(n => n.getAttribute('data-ssid') === x.sid) : null)
        || ns.find(n => n.getAttribute('data-scwd') === (x.cwd||''));
  };
  sessHover = false; sessDirty = false; buildSessions();
  let row = find();
  if(!row){                                        // hidden by a filter — clear filters and redraw
    if(idleMin) undone.push('idle filter');
    if(gitFil) undone.push('git filter');
    if(stFil) undone.push('state filter');
    idleMin = 0; gitFil = ''; stFil = ''; saveFil();
    buildSessions(); buildTodo();
    row = find();
  }
  if(undone.length) note(TV({msg: 'Cleared {f} to reach it', vars: {f: undone.map(s => T(s)).join(' · ')}}));   // ⚠the list always ends with the word «filter», so the Korean object particle is fixed (no vowel/consonant switch)
  // ⚠when `.lside` is hidden in narrow windows/popups, scrollIntoView does nothing — say why it couldn't go
  if(row && row.offsetParent) row.scrollIntoView({behavior:'smooth', block:'center'});
  else if(row) note(T('The session list is hidden on this screen, so the row could not be reached'));
  else note(T('That session is not in the list — it probably dropped out between polls'));
  setTimeout(() => { cpFlash = ''; sessHover = false; buildSessions(); }, 1400);
}
document.addEventListener('keydown', e => {
  // ★Cmd+K (mac) / Ctrl+K — the only other shortcuts in this file are Esc/Enter, so no collision.
  if((e.metaKey || e.ctrlKey) && !e.altKey && (e.key === 'k' || e.key === 'K')){
    const t = e.target, tag = (t && t.tagName) || '';
    // ⚠Not intercepted while typing — the palette must not open mid-chat (the palette's own input is the exception).
    if(!cpOn && (tag === 'INPUT' || tag === 'TEXTAREA' || (t && t.isContentEditable))) return;
    e.preventDefault();
    if(cpOn) cpClose(); else cpOpen();
    return;
  }
  if(!cpOn) return;
  if(e.key === 'Escape'){ e.preventDefault(); cpClose(); return; }
  if(e.key === 'ArrowDown'){ e.preventDefault(); if(cpRows.length){ cpSel = (cpSel + 1) % cpRows.length; cpPaint(); } return; }
  if(e.key === 'ArrowUp'){ e.preventDefault(); if(cpRows.length){ cpSel = (cpSel - 1 + cpRows.length) % cpRows.length; cpPaint(); } return; }
  // ⚠No match: Enter keeps the palette open (cpGo(undefined) would close it with no feedback).
  if(e.key === 'Enter' && !e.isComposing){ e.preventDefault(); if(cpRows.length) cpGo(cpRows[cpSel]); return; }
});
function cpInit(){
  const el = document.getElementById('cmdk'), q = document.getElementById('cmdkq'),
        box = document.getElementById('cmdkl');
  if(!el || !q || !box) return;
  q.oninput = () => { cpSel = 0; cpPaint(); };
  box.onclick = ev => {
    const it = ev.target.closest && ev.target.closest('.cmdki[data-i]');
    if(!it) return;
    cpSel = parseInt(it.getAttribute('data-i'), 10) || 0;
    cpGo(cpRows[cpSel]);
  };
  el.onclick = ev => { if(ev.target === el) cpClose(); };   // clicking outside (dark backdrop) closes it
}
window.addEventListener('DOMContentLoaded', cpInit);

