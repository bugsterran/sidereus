// Chat room admin on the room list (92 rcPaint/rcBind/rcCards call in here): «Manage» mode — hide · unhide · create · invite.
// ⚠Rule 1: room names · members · counts · times · mbox · path · model only — never post bodies or subjects.
//   The one text shown is the invite DM this page is about to send: the server builds it (dry) with the same function
//   that sends it, and the confirm sends it back as `expect`, so what was previewed is what goes out, byte for byte.
// ⚠Hide is view-only on the server side (posts stay in the mailbox); soleRoom()/roomNames() in 10-feed.js ignore it on purpose.
let RADM = {hidden: {}, pending: {}};   // state().roomAdmin, fed by roomAdminSet
let rcAdm = false;                       // «Manage» mode
const raSel = new Set();                 // checked room names
let raBox = null;                        // open panel: {k:'hide', rooms} | {k:'new'} | {k:'inv', room} | {k:'hid'}
const raPick = new Set();                // picked session mbox ids (create / invite)
let raName = '';                         // create-form name (kept across repaints)
let raDry = null;                        // server-built invite DM for the current panel: {key, body} | {key, err}
let raDryT = 0;                          // debounce timer for the dry fetch
function roomAdminSet(v){
  const o = (v && typeof v === 'object' && !Array.isArray(v)) ? v : {};
  const ob = x => (x && typeof x === 'object' && !Array.isArray(x)) ? x : {};
  RADM = {hidden: ob(o.hidden), pending: ob(o.pending)};
}
const raHidden = r => Object.prototype.hasOwnProperty.call(RADM.hidden, r);
// Panels with an input skip poll repaints (same reason as rcEdit) — typing and focus survive.
const raHold = () => !!(raBox && (raBox.k === 'new' || raBox.k === 'inv'));
// Pending rooms (created, nobody joined yet) not yet in roomNames(); shown as 0-post cards.
function raPendingNames(have){
  return Object.keys(RADM.pending).filter(r => r && !have.includes(r) && !raHidden(r));
}
// A hidden room has a post newer than the moment it was hidden -> dot on the «Hidden rooms» chip / row.
const raNewer = r => (MSGS || []).some(m => m.room === r && (+m.t || 0) > (+RADM.hidden[r] || 0));
function raBarHtml(){
  const hid = Object.keys(RADM.hidden), dot = hid.some(raNewer);
  return (hid.length ? '<button class="strp raop rahid' + (raBox && raBox.k === 'hid' ? ' on' : '') + '">' + esc(T('Hidden rooms')) + ' ' + hid.length
      + (dot ? '<span class=radot title="' + esc(T('New posts since hidden')) + '"></span>' : '') + '</button>' : '')
    + '<button class="strp raop raadm' + (rcAdm ? ' on' : '') + '" aria-pressed=' + rcAdm + '>' + esc(T('Manage')) + '</button>';
}
function raToolHtml(cs){
  if(!rcAdm) return '';
  const n = raSel.size, all = cs.filter(c => c.k !== 'dm').length;
  return '<div class=rabar>'
    + '<button class="strp raop raall"' + (all ? '' : ' disabled') + '>' + esc(n && n >= all ? T('Clear selection') : T('Select all')) + '</button>'
    + '<button class="strp raop rahsel"' + (n ? '' : ' disabled') + '>' + esc(T('Hide selected ({n})').replace('{n}', n)) + '</button>'
    + '<button class="strp raop ranew' + (raBox && raBox.k === 'new' ? ' on' : '') + '">' + esc(T('New room')) + '</button></div>';
}
// Session picker: identity-confirmed live sessions only are pickable (same rule as 40b sessPickHtml).
function raPickerHtml(){
  const rows = (SESS || []).filter(x => x.state !== 'done');
  if(!rows.length) return '<div class=ranone>' + esc(T('No sessions to pick')) + '</div>';
  return '<div class=rapick>' + rows.map(x => {
    const ok = !!(x.mbox && x.mboxSrc === 'identity');
    return '<label class="raop rapr' + (ok ? '' : ' off') + '"' + (ok ? '' : ' title="' + esc(T('Cannot invite — identity not confirmed')) + '"') + '>'
      + '<input type=checkbox class="raop rasp" data-mb="' + esc(x.mbox || '') + '"' + (ok ? (raPick.has(x.mbox) ? ' checked' : '') : ' disabled') + '>'
      + '<b>' + esc(x.mbox || '—') + '</b><span title="' + esc(x.cwd || '') + '">' + esc(x.cwd || '') + '</span><i>' + esc(x.model || '') + '</i></label>';
  }).join('') + '</div>';
}
function raPreview(){
  const d = raDry && raDry.key === raKey() && Array.isArray(raDry.added) ? raDry : null;
  const n = d ? d.added.length : raPick.size;   // already-invited members get no DM, so count the dry `added`
  if(raBox.k === 'inv') return T("Invite DM to {n} into '{m}'").replace('{n}', n).replace('{m}', () => raBox.room);
  const nm = raName.trim();
  if(!nm) return T('Enter a room name');
  return T("Create '{n}' + invite DM to {m}").replace('{n}', () => nm).replace('{m}', n);
}
// Panels that send invite DMs need the server's dry body for exactly this (kind, room, picks) before «Confirm» is enabled.
const raInvRoom = () => raBox.k === 'inv' ? raBox.room : raName.trim();
const raKey = () => JSON.stringify([raBox.k, raInvRoom(), [...raPick].sort()]);
const raNeedDry = () => (raBox.k === 'inv' || raBox.k === 'new') && raPick.size > 0 && !!raInvRoom();
const raDryOk = () => !!(raDry && raDry.key === raKey() && typeof raDry.body === 'string');
// ⚠Per box kind: the hide confirm has no name field, so a name check here silently swallowed its «Confirm».
const raOkOn = () => raBox.k === 'hide' ? raBox.rooms.length > 0
  : raNeedDry() ? raDryOk() && !(Array.isArray(raDry.added) && !raDry.added.length)   // nobody new: nothing to send
  : raBox.k === 'inv' ? false : !!raName.trim();
function raDryHtml(){
  if(!raNeedDry()) return '';
  const d = raDry && raDry.key === raKey() ? raDry : null;
  return '<pre class=rapb>' + esc(!d ? T('Loading…') : d.err ? T('Failed') + ': ' + d.err : d.body) + '</pre>';
}
// Dry POST (nothing written) to the same route the confirm uses; a stale answer for an older selection is dropped.
function raDryFetch(){
  clearTimeout(raDryT);
  if(!raBox || !raNeedDry() || raDryOk()) return;
  const key = raKey(), room = raInvRoom(), ids = [...raPick];
  raDryT = setTimeout(async () => {
    let d;
    try{
      const j = await postJSON(raBox.k === 'inv' ? '/api/room/invite' : '/api/rooms/create', {room: room, ids: ids, dry: true});
      d = j && j.ok && typeof j.body === 'string' ? {key, body: j.body, added: j.added}
        : {key, err: (j && (j.error || j.msg)) ? TV({msg: j.error || j.msg, vars: j.vars}) : T('unknown error')};
    }catch(e){ d = {key, err: T(e.message)}; }
    if(!raBox || raKey() !== key) return;
    raDry = d;
    const pb = feed.querySelector('.rapb'), ok = feed.querySelector('.rayes'), pv = feed.querySelector('.rapv');
    if(pb) pb.textContent = d.err ? T('Failed') + ': ' + d.err : d.body;
    if(pv) pv.textContent = raPreview();
    if(ok) ok.disabled = !raOkOn();
  }, 250);
}
function raBoxHtml(){
  if(!raBox) return '';
  const btns = ok => '<div class=raok><button class="strp on raop rayes"' + (ok ? '' : ' disabled') + '>' + esc(T('Confirm')) + '</button>'
    + '<button class="strp raop rano">' + esc(T('Cancel')) + '</button><span class=raerr></span></div>';
  if(raBox.k === 'hide') return '<div class="rabox raop">'
    + '<div class=rat>' + raBox.rooms.map(r => '<b>' + esc('# ' + r) + '</b>').join(' ') + '</div>'
    + '<div class=rac>' + esc(T('Posts stay in the mailbox · restore from Hidden rooms')) + '</div>' + btns(true) + '</div>';
  if(raBox.k === 'hid'){
    const hid = Object.keys(RADM.hidden).sort();
    return '<div class="rabox raop"><div class=rat>' + esc(T('Hidden rooms')) + '</div>'
      + (hid.length ? hid.map(r => '<div class=rahr><b>' + esc('# ' + r) + '</b>' + (raNewer(r) ? '<span class=radot title="' + esc(T('New posts since hidden')) + '"></span>' : '')
        + '<button class="strp raop raun" data-r="' + esc(r) + '">' + esc(T('Undo')) + '</button></div>').join('') : '<div class=ranone>' + esc(T('No hidden rooms')) + '</div>')
      + '<div class=raok><button class="strp raop rano">' + esc(T('Close')) + '</button><span class=raerr></span></div></div>';
  }
  return '<div class="rabox raop">'
    + (raBox.k === 'new'
      ? '<input class="svin rain" maxlength=64 autocomplete=off spellcheck=false value="' + esc(raName) + '" placeholder="' + esc(T('Room name')) + '" aria-label="' + esc(T('Room name')) + '">'
      : '<div class=rat>' + esc(T('Invite')) + ' <b>' + esc('# ' + raBox.room) + '</b></div>')
    + '<div class=rash>' + esc(T('Sessions to invite — only sessions with a confirmed identity can be picked')) + '</div>'
    + raPickerHtml() + '<div class=rapv>' + esc(raPreview()) + '</div>' + raDryHtml() + btns(raOkOn()) + '</div>';
}
// One room card with the admin parts ('dm' never gets the checkbox or «Invite» · «Hide»).
function raCardHtml(c){
  return rcCardHtml(c, {pend: c.pend, adm: rcAdm && c.k !== 'dm', sel: raSel.has(c.name)});
}
function raOpen(box){
  raBox = box; raPick.clear(); raDry = null; if(box && box.k === 'new') raName = ''; rcPaint(true);
  // preventScroll: opening the panel must not move the list.
  if(box && box.k === 'new') requestAnimationFrame(() => { const i = feed.querySelector('.rain'); if(i) i.focus({preventScroll: true}); });
}
function raBind(cs){
  const on = (s, f) => feed.querySelectorAll(s).forEach(b => b.onclick = f(b));
  on('.raadm', () => () => { rcAdm = !rcAdm; raSel.clear(); if(raBox && raBox.k !== 'hid') raBox = null; rcPaint(true); });
  on('.rahid', () => () => raOpen(raBox && raBox.k === 'hid' ? null : {k: 'hid'}));
  on('.raall', () => () => {
    const names = cs.filter(c => c.k !== 'dm').map(c => c.name);
    if(raSel.size >= names.length) raSel.clear(); else names.forEach(r => raSel.add(r));
    rcPaint(true);
  });
  on('.rahsel', () => () => { if(raSel.size) raOpen({k: 'hide', rooms: [...raSel].sort()}); });
  on('.ranew', () => () => raOpen(raBox && raBox.k === 'new' ? null : {k: 'new'}));
  on('.rainv', b => () => raOpen({k: 'inv', room: b.dataset.r}));
  on('.rahone', b => () => raOpen({k: 'hide', rooms: [b.dataset.r]}));
  on('.raun', b => () => raPost('/api/rooms/unhide', {rooms: [b.dataset.r]}, () => { delete RADM.hidden[b.dataset.r]; }));
  on('.rano', () => () => raOpen(null));
  on('.rayes', () => raGo);
  feed.querySelectorAll('.rachk').forEach(x => x.onchange = () => { if(x.checked) raSel.add(x.dataset.r); else raSel.delete(x.dataset.r); rcPaint(true); });
  // Picker and name only refresh the preview line — a full repaint would drop input focus.
  const sync = () => {
    const pv = feed.querySelector('.rapv'), ok = feed.querySelector('.rayes');
    if(pv) pv.textContent = raPreview();
    const pb = feed.querySelector('.rapb'); if(pb) pb.remove();
    if(pv) pv.insertAdjacentHTML('afterend', raDryHtml());
    if(ok) ok.disabled = !raOkOn();
    raDryFetch();
  };
  raDryFetch();
  feed.querySelectorAll('.rasp').forEach(x => x.onchange = () => { if(x.checked) raPick.add(x.dataset.mb); else raPick.delete(x.dataset.mb); sync(); });
  // Escape on any panel closes it like «Cancel»/«Close» (the invite panel has no name input to catch it).
  feed.querySelectorAll('.rabox').forEach(x => x.onkeydown = e => { if(e.key === 'Escape'){ e.stopPropagation(); raOpen(null); } });
  const nm = feed.querySelector('.rain');
  if(nm){
    nm.oninput = () => { raName = nm.value; sync(); };
    nm.onkeydown = e => { if(e.key === 'Escape'){ e.stopPropagation(); raOpen(null); } };
  }
}
function raGo(){
  if(!raBox || !raOkOn()) return;
  const b = raBox, ids = [...raPick];
  if(b.k === 'hide') return raPost('/api/rooms/hide', {rooms: b.rooms}, () => {
    const t = Date.now() * 1e6; b.rooms.forEach(r => { RADM.hidden[r] = t; raSel.delete(r); });
  });
  const expect = raDryOk() ? raDry.body : undefined;   // the previewed bytes; the server refuses if they would differ
  if(b.k === 'inv') return raPost('/api/room/invite', {room: b.room, ids: ids, expect: expect}, () => {});
  const room = raName.trim();
  return raPost('/api/rooms/create', ids.length ? {room: room, ids: ids, expect: expect} : {room: room}, () => {
    if(!ids.length) RADM.pending[room] = {created: Date.now() * 1e6};
    raName = '';
  });
}
// POST, then apply the change locally so the list updates before the next poll; errors stay in the panel.
async function raPost(url, body, apply){
  const ok = feed.querySelector('.rayes'), er = feed.querySelector('.raerr');
  if(ok) ok.disabled = true;
  try{
    const j = await postJSON(url, body);
    if(!j || j.ok === false) throw new Error((j && (j.error || j.msg)) ? TV({msg: j.error || j.msg, vars: j.vars}) : T('unknown error'));
    apply(); raBox = null; raPick.clear();
    if(j.msg) note(TV(j));
    rcPaint(true); poll();
  }catch(e){
    if(er) er.textContent = T('Failed') + ': ' + T(e.message);
    if(raBox && raNeedDry()){ raDry = null; raDryFetch(); }   // e.g. room changed since the preview: rebuild it before «Confirm» again
    if(ok) ok.disabled = !(raBox && raOkOn());
  }
}
