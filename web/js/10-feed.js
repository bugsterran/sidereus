// ★The scroll owner is **the conversation column (main#feed)**, not the window
const atBottom=()=>feed.scrollHeight-feed.scrollTop-feed.clientHeight<140;
// reveal 'load more' only at the top edge (show it outright when there is no scroll at all)
function olderToggle(){
  const el=document.getElementById('older');
  if(!el) return;
  const noScroll = feed.scrollHeight <= feed.clientHeight + 4;
  el.classList.toggle('hid', !(noScroll || feed.scrollTop < 80));
}
// ⚠The room list (92 rcPaint) reads top-down — callers outside 92 still ask for the bottom after full().
const toBottom=(smooth)=>{ if(feed.querySelector(':scope > .rcw')) feed.scrollTop=0; else feed.scrollTo({top:feed.scrollHeight, behavior: smooth?'smooth':'auto'}); };
function decorate(m){
  m.selfaddr = !m.room && !!m.to && m.to===m.from;
  m.mine = MINE.includes(m.from) && !m.selfaddr;
  m.role = (PROF[m.from]||{}).role||'';
  m.kind = kindOf(m.subject);
  const mem = m.room ? (ROOMS[m.room]||{}).members||[] : (m.to?[m.to]:[]);
  m.audience = mem.filter(x=>x!==m.from);
  return m;
}
function readersOf(m){ return m.audience.filter(w=>(CUR[w]||0)>=m.t); }
function receipt(m){
  if(m.selfaddr) return '<div class=rd>'+T('⚠ from == to — the sender field cannot be trusted')+'</div>';
  if(!m.audience.length) return '<div class=rd>'+T(m.room?'No recipients (room of one)':'No recipients')+'</div>';
  // ★By signal strength: ack > delivered > cursor. The cursor means "fetched", not "seen", so it goes last.
  const a = ACK[m.id] || {};
  const acked = (a.ack || []).filter(x => x.who !== m.from);
  if(acked.length){
    const who = acked.map(x => esc(x.who) + (x.note ? ' — ' + esc(String(x.note).slice(0,60)) : '')).join(' · ');
    // only a full ack gets the green done style; a partial one (2/5) stays amber so it doesn't read as complete
    return '<div class="rd '+(acked.length>=m.audience.length?'ok':'part')+'">'+T('✔ Acknowledged')+(m.audience.length>1?' '+acked.length+'/'+m.audience.length:'')+' · '+who+'</div>';
  }
  // ★A watcher emitting the full text is **delivery**, not ack (auto ack removed 2026-09-23) — this is the normal state.
  const deliv = (a.delivered || []).filter(w => w !== m.from);
  if(deliv.length) return '<div class=rd>'+T('➡ Delivered')+(m.audience.length>1?' '+deliv.length+'/'+m.audience.length:'')
    +' · '+deliv.map(esc).join(', ')+' <em>'+T('(not acknowledged yet)')+'</em></div>';
  // outside the retention window (server ACK_KEEP_S) the record **doesn't exist**; it is not unread
  const gone = ACKSINCE && m.t < ACKSINCE;
  const r=readersOf(m);
  if(!r.length) return '<div class=rd>'+T('✓ Sent')+' · '+T(gone?'receipt records expired':'Unread')+'</div>';
  return '<div class=rd>'+T('◔ Cursor passed')+(m.audience.length>1?' '+r.length+'/'+m.audience.length:'')+' · '+r.map(esc).join(', ')
    + ' <em>'+T('(cursor position — not proof they read it)')+'</em></div>';
}
function answered(m){
  // ★Don't rely on title wording — **if the other side posted in that thread later than me, a reply came**.
  //   It used to require `kind.cls==='ans'` (title matching a fixed list of Korean "reply" words), but real batch-reply titles were
  //   tagged "[done · batch reply] ..." and didn't match → **a reply came but all my posts stayed 'awaiting reply'**.
  //   Sending several and getting one reply is normal conversation, yet the label hinged on one phrase.
  //   ⚠But if the other side only sent a counter-question (`ask`), that is not a reply — then **their bubble** shows as awaiting reply.
  return MSGS.some(o => o.thread === m.thread && o.t > m.t && o.from !== m.from
                        && !(o.kind && o.kind.cls === 'ask'));
}
function waiting(m){ if(!(m.kind&&m.kind.cls==='ask'&&m.thread)) return false;
  // A closed thread is not awaiting reply — the other side declared "no reply needed".
  const later=MSGS.filter(o=>o.thread===m.thread&&o.t>m.t);
  if(later.length&&later[later.length-1].kind&&later[later.length-1].kind.cls==='done') return false;
  return !answered(m); }

function bubble(m, fresh){
  const k=m.kind;
  return '<div class="row'+(m.mine?' me':'')+(m.selfaddr?' odd':'')+(fresh?' fresh':'')+'" data-id="'+esc(m.id)+'" data-t="'+m.t+'">'
    +'<div class=av'+avSty(m.from)+'>'+esc(ini(m.from))+'</div><div class=col>'
    +'<div class=nm><b'+nmSty(m.from)+'>'+esc(m.from)+(m.selfaddr?' ⚠':'')+'</b>'
    +(m.role?'<span>'+esc(m.role)+'</span>':'')+'<span>'+hm(m.t)+'</span>'
    +'<span class=pill>'+(m.room?T('Room ')+esc(m.room):'→ '+esc(m.to))+'</span>'
    // thread name: identical posts sent to several threads (e.g. a «[DONE] cleanup» post) otherwise read as duplicates; wk:<id> is auto-made
    +(m.thread && !/^wk:/.test(m.thread) ? '<span class="pill thp" title="'+esc(T('Thread')+' · '+m.thread)+'">'+esc(m.thread)+'</span>' : '')
    +(waiting(m)?'<span class=open>'+T('Awaiting reply')+'</span>':'')
    +'<button class=rbtn data-rt="'+esc(m.id)+'" data-who="'+esc(m.from)+'">'+T('↩ Reply')+'</button>'
    +'</div><div class=bub>'
    +(m.replyTo ? (()=>{ const par=MSGS.find(x=>x.id===m.replyTo);
        return '<div class=reply>↩ <b>'+esc(par?par.from:'?')+'</b> '
          + esc(par ? (par.subject || mbody(par).replace(/\s+/g,' ').slice(0,60)) : m.replyTo)+'</div>'; })() : '')
    +(k?'<span class="kind k-'+k.cls+'">'+esc(k.tag)+'</span> ':'')
    +(m.subject?'<span class=subj>'+inline(stripTag(m.subject))+'</span>':'')
    +(()=>{ const d=digest(mbody(m));
        if(!d.long) return '<div class="bd">'+md(mbody(m))+'</div>';   // short posts as-is (a summary longer than the post is a loss)
        // the gist stays as **a lead line** and the body stays markdown — only the height is folded
        return '<div class=sum>'+d.picks.map(t=>'<div class=sl>'+inline(t)+'</div>').join('')
          +'<div class=smeta>'+esc(d.meta)+'</div></div>'
          +'<div class="bd clamp">'+md(mbody(m))+'</div><button class=more>'+T('▾ Show more')+'</button>'; })()
    +'</div><div class=rcpt>'+receipt(m)+'</div></div></div>';
}
// ── Send — typed by a human. Enter sends (Shift+Enter newline) · replies attach via replyTo.
let replyTo = null;
function setReply(id, who){
  replyTo = id;
  const box = document.getElementById('rt');
  box.style.display = id ? 'flex' : 'none';
  if(id) box.innerHTML = '↩ <b>'+esc(who)+'</b> '+T('— reply')+' <span class=x>'+T('✕ Cancel')+'</span>';
  if(id) box.querySelector('.x').onclick = ()=>setReply(null);
  ctoPaint();
  document.getElementById('cbox').focus();
}
// Where Enter will post: {room} | {to} | null. A reply follows its parent (a DM reply goes back to the peer);
// otherwise the open room. ⚠The default room is chosen here, visibly, never by the server.
function chatTarget(){
  const par = replyTo ? MSGS.find(x => x.id === replyTo) : null;
  if(par){
    if(par.room) return {room: par.room};
    if(par.to) return {to: (par.mine || ((CFG || {}).viewerIds || [(CFG || {}).viewerMe]).includes(par.from)) ? par.to : par.from};
    if(absorbed(par)) return {room: soleRoom()};
  }
  else if(place.indexOf('room:') === 0) return {room: place.slice(5)};
  // «Outside rooms» new post: the configured default room, sent by name and labelled «(default room)» — the server never picks one.
  const dr = (CFG || {}).defaultRoom;
  return dr ? {room: dr, dflt: true} : null;
}
function ctoPaint(){
  const el = document.getElementById('cto'); if(!el) return;
  const g = chatTarget();
  const h = !g ? '<span class=ctono>' + esc(T('No target — pick a post to reply to')) + '</span>'
    : esc(T('To', 'feed')) + ' <b>' + esc(g.room ? '# ' + g.room : 'DM → ' + g.to) + '</b>' + (g.dflt ? ' ' + esc(T('(default room)')) : '');
  if(el._h !== h){ el.innerHTML = h; el._h = h; }
  const btn = document.getElementById('csend'); if(btn && !btn._busy) btn.disabled = !g;
}
async function send(){
  const box=document.getElementById('cbox'), btn=document.getElementById('csend');
  if(btn._busy) return;   // ⚠Enter and click share this in-flight flag — a fast double Enter posted twice
  const body=box.value.trim(); if(!body) return;
  const g = chatTarget();
  if(!g){ note(T('No target — pick a post to reply to')); return; }
  btn.disabled=true; btn._busy=true;
  try{
    const par = replyTo ? MSGS.find(x=>x.id===replyTo) : null;
    const j=await postJSON('/api/say', {body, replyTo, room:g.room, to:g.to, thread:(par&&par.thread)||undefined});
    if(j&&j.error) throw new Error(j.error);
    box.value=''; box.style.height='auto'; setReply(null); await poll();
    // ⚠«Outside rooms» shows only room-less posts, so a default-room post would vanish — follow it into that room.
    if(g.dflt && place.indexOf('room:') !== 0) rcOpen('room:' + g.room);
  }catch(e){ alert(T('Could not send')+': '+T(e.message)); }
  finally{ btn._busy=false; btn.disabled=false; ctoPaint(); box.focus(); }
}
document.addEventListener('click', e=>{
  const b=e.target.closest('.rbtn'); if(b) setReply(b.dataset.rt, b.dataset.who);
});
// ★The compose bar is static markup, so T() cannot wrap it at build time — repaint its labels here.
//   ⚠Touch only the jump button's first text node; its <b id=njump> counter is written elsewhere.
function paintCompose(){
  const box = document.getElementById('cbox');
  if(box) box.placeholder = T('Type here — Enter to send · Shift+Enter for a new line');
  const btn = document.getElementById('csend');
  if(btn) btn.textContent = T('Send');
  const jb = document.getElementById('jump');
  if(jb && jb.firstChild && jb.firstChild.nodeType === 3) jb.firstChild.nodeValue = T('↓ New') + ' ';
  ctoPaint();
}
// ★Header text is baked into the PAGE template, so T() has to be applied to it by hand — once at
//   boot and again after a language switch (nothing repaints the header on its own).
function hdrLang(){
  const set = (id, f) => { const e = document.getElementById(id); if(e) f(e); };
  set('q',      e => e.placeholder = T('Search text, title, sender'));
  set('vwb',    e => { e.textContent = T('Views', 'saved') + ' ▾';
                       e.title = T('Saved views — pick one to restore that combination'); });
  set('vwsave', e => { e.textContent = '+ ' + T('Save');
                       e.title = T('Name and save the current filter combination'); });
  set('bell',   e => { e.title = T('Task-done alerts (they collect here)'); e.setAttribute('aria-label', T('Completion alarms'));
    e.setAttribute('aria-controls', 'alarm'); if(!e.hasAttribute('aria-expanded')) e.setAttribute('aria-expanded', 'false'); });
  set('gear',   e => { e.title = T('Settings'); e.setAttribute('aria-label', T('Settings')); });
  set('cmdkq',  e => e.placeholder = T('Search sessions — project · path · session id · model · state · platform'));
  // The monitoring panel heading is static markup as well, so it rides along here.
  const sh = document.querySelector('h2.sesh .seshn'); if(sh) sh.textContent = T('Sessions');
  try{ sesdrLang(); }catch(e){ softErr('sesdrLang', e); }   // drawer button, pin/close labels (41-sesdrawer.js)
  // Alarm panel header is static markup too.
  const ah = document.querySelector('#alarm .ahead > b'); if(ah) ah.textContent = T('Alerts — done · failed');
  set('aunread', e => { e.textContent = T('Unread only'); e.title = T('Collapse to unread cards only (history is not deleted)'); });
  set('aread',   e => { e.textContent = T('Mark all read'); e.title = T('Clears the badge only — history is kept'); });
  set('aall',    e => { e.textContent = T('Full history'); e.title = T('Include older cards'); });
  // Remaining static markup of index.html (stale banner, participants heading, popup close buttons, Cmd+K footer).
  set('stale',   e => { if(e.firstChild && e.firstChild.nodeType === 3) e.firstChild.nodeValue = T('The server was updated — this tab shows the old screen.') + ' '; });
  set('sreload', e => e.textContent = T('Reload'));
  const ph = document.querySelector('aside.pside > h2'); if(ph) ph.textContent = T('Participants');
  set('dx',      e => e.title = T('Close this window (Esc)'));
  set('spx',     e => e.title = T('Close (Esc)'));
  const kf = document.querySelector('#cmdk .cmdkf'); if(kf) kf.textContent = T('↑↓ move · Enter select · Esc close — conversation text is never searched (metadata only)');
  try{ buildAlarm(); }catch(e){ softErr('buildAlarm', e); }
}
window.addEventListener('DOMContentLoaded', ()=>{
  hdrLang();
  const box=document.getElementById('cbox');
  document.getElementById('csend').onclick=send;
  box.addEventListener('input', ()=>{ box.style.height='auto'; box.style.height=Math.min(box.scrollHeight,160)+'px'; });
  box.addEventListener('keydown', e=>{ if(e.key==='Enter' && !e.shiftKey && !e.isComposing){ e.preventDefault(); send(); } });
});

function wireFold(scope){
  scope.querySelectorAll('.more').forEach(b=>{
    if(b.dataset.w) return; b.dataset.w='1';
    const bd=b.previousElementSibling;
    b.onclick=()=>{ b.textContent = bd.classList.toggle('clamp') ? T('▾ Show more') : T('▴ Collapse'); };
  });
}
// Absorption rule: with exactly one room, room-less public posts count as that room's (stored posts untouched).
// ⚠Single predicate for visible/buildTabs/buildPeople/rcCards — DMs (m.to set) are never absorbed.
// ⚠roomNames is the one room list (ROOMS + rooms named in posts) — room cards and absorption must agree on "one room".
function roomNames(){ return [...new Set([...Object.keys(ROOMS||{}), ...MSGS.filter(m=>m.room).map(m=>m.room)])].sort(); }
// ⚠Memoized on MSGS/ROOMS identity + length — absorbed() runs per message, and a full roomNames() scan each time was O(n²).
function soleRoom(){
  const c=soleRoom._c; if(c && c[0]===MSGS && c[1]===MSGS.length && c[2]===ROOMS) return c[3];
  const k=roomNames(), v=k.length===1 ? k[0] : ''; soleRoom._c=[MSGS, MSGS.length, ROOMS, v]; return v;
}
function absorbed(m){ return !m.room && !m.to && !!soleRoom(); }
function inPlace(m,pl){ return pl==='dm' ? (!m.room && !absorbed(m))
  : pl.indexOf('room:')===0 ? (m.room===pl.slice(5) || (absorbed(m) && soleRoom()===pl.slice(5))) : true; }
const visible=m=>{
  // (1) Place — picking a room shows only its posts. «Outside rooms» means room-less posts not absorbed.
  if(!inPlace(m, place)) return false;
  // (2) Filters within that place
  if(filter!=='all'){
    const f=String(filter), p=f.indexOf(':'), k=p<0?f:f.slice(0,p), v=p<0?'':f.slice(p+1);   // String(): never throw on a bad saved value
    if(k==='room'&&m.room!==v) return false;      // legacy value compatibility (saved filters may remain)
    if(k==='dm'&&m.room) return false;
    if(k==='waiting'&&!waiting(m)) return false;
    if(k==='unread'&&(!m.mine||readersOf(m).length||!m.audience.length)) return false;
    if(k==='decided'&&!isDecided(m)) return false;
    if(k==='fixed'&&!isFixed(m)) return false;
    if(k==='noack'&&(!m.mine||!m.audience.length||((ACK[m.id]||{}).ack||[]).length)) return false;
  }
  if(q&&!((m.subject||'')+' '+(m.body||'')+' '+m.from).toLowerCase().includes(q)) return false;
  return true;
};

// ★Only recent posts are drawn (too many posts piled up). Drawing all 618 makes the DOM heavy and scroll long.
//   ⚠**Data stays intact** — stale threads, verdict/correction tabs and read counts use the whole `MSGS`. Only **drawing** is cut.
const SHOW_STEP = 30;
// ★Cap on drawn rows (2026-09-22) — `append()` appended without a cap, and a tab left open for days froze the screen
//   (measured 969 rows · `receipt` rewritten 969 times per poll · `full()` 59ms). 300 is 3-4 screens, and
//   overflowing old rows are removed only from the DOM by `trimFeed()` below ⇒ restored via "load earlier".
//   ⚠Never truncate `MSGS` — stale threads, verdict/correction tabs and read counts use all of it.
const SHOW_MAX  = 300;
let shownN = 10;                     // only 10 at first
// ★First load sends older posts as stubs without `body` (server bus.MSG_FIRST) — bodies come from /api/messages when
//   a stub is about to be drawn or searched. ⚠t is ns (> 2^53), so the range is padded 1ms and matched by id.
const HYD_N = 1000, HYD_PAD = 1e6;
let hydBusy = false, hydFailAt = 0, hydQ = [], hydNext = null;   // hydQ: stubs asked for while a fetch is in flight
const mkey = m => m.id || ((m.t||'')+'|'+(m.from||''));
const mbody = m => m.stub ? T('Loading…') : (m.body||'');   // ⚠every body reader goes through this + hydrate()
async function hydrate(stubs){        // -> number of stubs filled (0 = no progress; callers must not loop on it)
  if(!stubs.length || Date.now() - hydFailAt < 5000) return 0;
  if(hydBusy){   // ⚠dropping these left stubs at «Loading…» — queue them; resolves with the follow-up run's count
    hydQ.push(...stubs);
    if(!hydNext){ let res; hydNext = new Promise(r => { res = r; }); hydNext.res = res; }
    return hydNext;
  }
  hydBusy = true;
  try{
    const ts = stubs.map(m => +m.t||0), lo = Math.min(...ts), hi = Math.max(...ts);
    const r = await getJSON('/api/messages?after='+Math.floor(lo-HYD_PAD)+'&before='+Math.ceil(hi+HYD_PAD)+'&n='+HYD_N);
    const got = r.messages || [], by = {};
    got.forEach(x => { by[mkey(x)] = x; });
    const floor = got.length >= HYD_N ? Math.min(...got.map(x => +x.t||0)) : -Infinity;   // truncated: only the newest part is covered
    let n = 0;
    for(const m of MSGS){
      if(!m.stub) continue;
      const t = +m.t||0, x = by[mkey(m)];
      if(!x && (t <= floor || t < lo || t > hi)) continue;
      m.body = x ? x.body : ''; delete m.stub; n++;   // not returned inside a covered range = gone from the bus
    }
    return n;
  }catch(e){ hydFailAt = Date.now(); softErr('hydrate', e); note(T('Could not fetch — check the server')); return 0; }
  finally{
    hydBusy = false;
    if(hydNext){ const p = hydNext, q = [...new Set(hydQ)].filter(m => m.stub); hydQ = []; hydNext = null; hydrate(q).then(p.res); }
  }
}
function full(){                      // full re-render only when filters/sort change
  if(place==='all' && !q){ rcPaint(true); return; }   // no room open = room cards (92); a search still lists every room's posts
  const all=MSGS.filter(visible);
  const hidden=Math.max(0, all.length-shownN);
  const list=hidden ? all.slice(-shownN) : all;
  const par=new Set(list.map(m => m.replyTo).filter(Boolean));   // reply previews read the parent's body
  const stubs=q ? MSGS.filter(m => m.stub) : MSGS.filter(m => m.stub && (par.has(m.id) || list.includes(m)));   // search needs every body
  if(stubs.length) hydrate(stubs).then(n => { if(n){ const stick=atBottom(); full(); if(stick) toBottom(false); } });
  document.getElementById('cnt').textContent=cntText(all.length, hidden ? list.length : 0);
  if(!all.length){ feed.innerHTML='<div class=empty>'+T('No messages match.')+'</div>'; return; }
  let h='';
  // ★The button is not shown from the start (2026-08-21) — it appears when scrolling up **reaches the end**.
  //   Normally only recent conversation shows cleanly; the option appears only when you mean to go back.
  if(hidden) h+='<div class="older hid" id=older>'+olderTxt(hidden)+'</div>';
  let last='';
  for(const m of list){ const d=day(m.t); if(d!==last){ h+='<div class=day><span>'+d+'</span></div>'; last=d; } h+=bubble(m,false); }
  feed.innerHTML=h; feed._sh=undefined; wireFold(feed);
  const more=document.getElementById('older');
  olderToggle();          // once right after drawing — if content is short with no scroll it must show immediately
  if(more) more.onclick=olderClick;
}
let olderBusy = false;
async function olderClick(){    // handler pulled out by name because `trimFeed()` may recreate the button
  if(olderBusy) return;         // ⚠re-entry grew shownN twice and anchored on half-loaded heights
  olderBusy = true;
  const btn=document.getElementById('older');
  if(btn){ btn.setAttribute('aria-disabled','true'); btn.style.pointerEvents='none'; }
  try{
    const next=MSGS.filter(visible).slice(-(shownN+SHOW_STEP)).filter(m => m.stub);
    if(next.length) await hydrate(next);   // bodies first, so the scroll anchor below measures final heights
    // Preserve scroll position — if the view jumps by what is prepended, the reading spot is lost
    const before=feed.scrollHeight, top=feed.scrollTop;
    shownN+=SHOW_STEP; full();
    feed.scrollTop = top + (feed.scrollHeight-before);
  }finally{
    olderBusy = false;
    if(btn){ btn.removeAttribute('aria-disabled'); btn.style.pointerEvents=''; }
  }
}
function syncOlder(){     // reflect the hidden count in the header's "load earlier" (create it if absent)
  const hidden=Math.max(0, MSGS.filter(visible).length - feed.querySelectorAll('.row').length);
  let el=document.getElementById('older');
  if(!hidden){ if(el) el.remove(); return; }
  if(!el){
    feed.insertAdjacentHTML('afterbegin','<div class="older hid" id=older></div>');
    el=document.getElementById('older'); el.onclick=olderClick;
  }
  el.innerHTML=olderTxt(hidden);
  olderToggle();
}
function trimFeed(){      // removes old rows over the cap **only from the DOM** (data stays)
  const rows=feed.querySelectorAll('.row');
  const over=rows.length-shownN;
  if(over<=0){ syncOlder(); return; }
  const h0=feed.scrollHeight, top=feed.scrollTop;
  for(let i=0;i<over;i++) rows[i].remove();
  // date headers left alone after their rows are removed go too
  let n=feed.firstElementChild;
  if(n && n.id==='older') n=n.nextElementSibling;
  while(n && n.classList.contains('day')){
    const nx=n.nextElementSibling;
    if(nx && nx.classList.contains('day')){ n.remove(); n=nx; }
    else break;
  }
  syncOlder();
  feed.scrollTop = Math.max(0, top - (h0-feed.scrollHeight));   // restore by how much the top shrank to keep the reading spot
}

let pending=0;
function append(fresh){               // ★Append only new posts at the bottom — no reload, no re-render
  if(place==='all' && !q) return;     // room list: the poll's buildRooms repaints the cards
  // New posts stay on screen (so the hidden count doesn't grow for nothing) — but stops at SHOW_MAX.
  // ⚠A value already raised above the cap via "load more" is **left as-is** — lowering it makes the view jump.
  if(shownN < SHOW_MAX) shownN=Math.min(SHOW_MAX, shownN+fresh.filter(visible).length);
  const stick=atBottom();
  let last=feed.querySelector('.day:last-of-type span');
  for(const m of fresh){
    if(!visible(m)) continue;
    const d=day(m.t);
    const cur=[...feed.querySelectorAll('.day span')].pop();
    if(!cur||cur.textContent!==d) feed.insertAdjacentHTML('beforeend','<div class=day><span>'+d+'</span></div>');
    feed.insertAdjacentHTML('beforeend', bubble(m,true));
  }
  wireFold(feed);
  trimFeed();             // trim what exceeds the cap + sync "load earlier"
  const total=MSGS.filter(visible).length, drawn=feed.querySelectorAll('.row').length;
  document.getElementById('cnt').textContent=cntText(total, total>drawn ? drawn : 0);
  if(stick) toBottom(true);
  else { pending+=fresh.length; document.getElementById('njump').textContent=pending; jump.style.display='block'; }
}
function refreshReceipts(){           // update only read receipts in place (keeps scroll and expanded state)
  // ★Write only changed rows (2026-09-22) — stops writing innerHTML to every row on each poll (2.5s).
  //   Measured 969 rows: writes per poll 969 → 0 (when unchanged). The comparison key is **the output string itself** —
  //   ⚠picking inputs to compare (ACK delivered · ack[].who · note, fields of m) means missing one freezes receipts forever.
  const by={}; MSGS.forEach(m=>by[m.id]=m);
  feed.querySelectorAll('.row').forEach(row=>{
    const m=by[row.dataset.id]; if(!m) return;
    const box=row.querySelector('.rcpt'); if(!box) return;
    const h=receipt(m);
    if(box.__rcpt!==h){ box.innerHTML=h; box.__rcpt=h; }
  });
}

