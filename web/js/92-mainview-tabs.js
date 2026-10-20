// Tab glyphs, self-drawn 16x16 line art like CFG_ICO (90-settings.js); timeline reuses the settings glyph.
const TAB_ICO = {
  time: CFG_ICO.tl,
  chat: '<path d="M2.5 4A1.5 1.5 0 0 1 4 2.5h8A1.5 1.5 0 0 1 13.5 4v5.5A1.5 1.5 0 0 1 12 11H7l-3 2.5V11a1.5 1.5 0 0 1-1.5-1.5z"/>',
  token: '<ellipse cx="8" cy="4.5" rx="5" ry="2"/><path d="M3 4.5V8c0 1.1 2.2 2 5 2s5-.9 5-2V4.5M3 8v3.5c0 1.1 2.2 2 5 2s5-.9 5-2V8"/>',
  struct: '<rect x="6" y="2" width="4" height="3" rx=".8"/><rect x="2" y="11" width="4" height="3" rx=".8"/><rect x="10" y="11" width="4" height="3" rx=".8"/><path d="M8 5v3M4 11V8h8v3"/>',
  br: '<circle cx="4.5" cy="3.5" r="1.5"/><circle cx="4.5" cy="12.5" r="1.5"/><circle cx="11.5" cy="5.5" r="1.5"/><path d="M4.5 5v6M11.5 7c0 3-3 3.5-6.2 4.3"/>',
  hist: '<path d="M2.8 8A5.2 5.2 0 1 0 4.3 4.3"/><path d="M2.5 2.3v2.5H5"/><path d="M8 5v3l2 1.5"/>',
  retro: '<path d="M2.5 2.5v11h11"/><path d="M5 10.5l2.5-3 2 1.5 3.5-4.5"/>',
  pipe: '<rect x="1.5" y="3.5" width="4" height="4" rx=".8"/><rect x="10.5" y="3.5" width="4" height="4" rx=".8"/><path d="M5.5 5.5h5M8.8 4l1.5 1.5L8.8 7"/><path d="M12.5 7.5v3.5a1.5 1.5 0 0 1-1.5 1.5H5a1.5 1.5 0 0 1-1.5-1.5V7.5"/>',
};
// Tab -> feature manifest id: the tab is hidden while /api/state.features says that feature is off (FEATS, 95-poll.js).
const TAB_FEAT = {pipe: 'pipeline', retro: 'retro'};
let FEATS = {};
const tabIco = k => TAB_ICO[k] ? '<svg class=mvic viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false"'
  + ' fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">' + TAB_ICO[k] + '</svg>' : '';
function buildMv(){
  const el = document.getElementById('mvw');
  if(!el) return;
  // Update the agent tab label with the fetched value (initially it was the tid suffix)
  for(const t of wtabs){
    const d = wtData[t.key];
    if(t.kind === 'agent' && d && d.ok && d.type) t.label = wkLab(d.type);
  }
  // ★When an agent is running, put **a dot on the mode button** (2026-09-01) — even while viewing chat
  // one must know something is running. Uses the same value as the session card (SESS sub).
  const nRun = (SESS||[]).reduce((a,x) => a + (x.sub||[]).length, 0);
  let nPl = 0; try{ const kn = plKnown(); nPl = plLiveN(plLiveProjs(SESS, plMem(), kn), kn); if(nPl && !kn && FEATS.pipeline !== false) plLoadProjs(); }catch(e){ softErr('plLiveProjs', e); }   // pipe tab dot (48-pipeline.js)
  let nMsg = 0; try{ nMsg = (mainView === 'chat') ? 0 : chatNew(); }catch(e){ softErr('chatNew', e); }
  let kbN = 0;   // shortcut digit = position in the row (98-a11y.js reads the same order)
  const tab = (k, lab) => '<button class="mvb'+(mainView===k?' on':'')+'" data-mv="'+k+'" role=tab aria-selected="'+(mainView===k)
    +'" tabindex="'+(mainView===k?0:-1)+'" title="'+esc(lab+' — '+T('Shortcut')+' '+(++kbN)+' · ? '+T('help'))+'">'+tabIco(k)+'<span class=mvl>'+lab+'</span>'
    + (k === 'time' && nRun ? '<i class=mvdot title="'+T('{n} subagents running', 'tab').replace('{n}', nRun)+'"></i>' : '')
    + (k === 'pipe' && nPl ? plLiveDot(nPl) : '')
    + (k === 'chat' && nMsg ? '<i class="mvnum mvmsg" title="'+T('{n} new unseen messages').replace('{n}', nMsg)+'">'+nMsg+'</i>' : '')
    + '</button>';
  // A tab whose feature is off falls back to the timeline (only once /api/state has said so) and is remembered for the next load (05 restore).
  if(STATE_IN){
    const offT = Object.keys(TAB_FEAT).filter(k => FEATS[TAB_FEAT[k]] === false), js = JSON.stringify(offT);
    if(lsGet('mbTabsOff', '[]') !== js) lsSet('mbTabsOff', js);
    if(offT.includes(mainView)){ setMainView('time'); return; }
  }
  const tp = mpTabs();   // «Preferences» mbTabs order/hide; the open tab always stays visible
  // ★The tab row moved **into the work-history view** (2026-09-01) — in the header it mixed with the mode buttons
  // and blurred "what am I choosing now". This row chooses only the mode.
  // ★Tokens are a **separate tab** (2026-09-04: moved out into its own tab).
  // Putting donut, daily, today bar and live all in the left card column (420px) pushed the session list down.
  // ★«Structure» is a **separate tab** (pick a session, then view its projects' structure).
  // Same slot as tokens — uses the whole middle column.
  // ★Tab labels go through T() so the language pack can rename them without touching markup.
  // Timeline first; «Activity» is no longer a tab but a modal (wkOpenModal).
  // ★The «Failures» tab was removed — failures are bell alerts now.
  // ⚠The rebuild drops focus to <body>; remember it so a keyboard tab switch keeps focus (★ 2026-09-27 interaction audit).
  const hadF = el.contains(document.activeElement);
  // Stock order = MP_TABS (90b-mypref.js).
  if(!setHtml(el, '<div class=mvg role=tablist aria-orientation=vertical aria-label="'+esc(T('Views'))+'">'
    // ⚠Feature tabs stay hidden until /api/state says the feature is on (a default-off tab would 404 if clicked before the first poll).
    +tp.order.filter(k => k === mainView || (!tp.hide.includes(k) && (!TAB_FEAT[k] || (STATE_IN && FEATS[TAB_FEAT[k]] !== false)))).map(k => tab(k, mvLab(k))).join('')
    +'</div>')) return;   // Settings is a modal behind the header gear (#gear), not a tab.
  el.querySelectorAll('.mvb').forEach(b => { b.onclick = () => setMainView(b.dataset.mv); b.onkeydown = mvKey; });
  if(hadF){ const on = el.querySelector('.mvb.on'); if(on) on.focus(); }
  try{ railTitle(); }catch(e){ softErr('railTitle', e); }   // #vtitle follows the active tab (92d-rail.js)
}
function mvLab(k){
  return ({time: T('Timeline'), chat: T('Chat'), struct: T('Structure'), br: T('Branches'), pipe: T('Pipelines'), token: T('Tokens'), hist: T('History'), retro: T('Insights')})[k] || '';
}
// Up/Down (vertical rail) and Left/Right move between tabs (tablist pattern, wraps around); the move also switches the view.
function mvKey(e){
  const d = (e.key === 'ArrowDown' || e.key === 'ArrowRight') ? 1 : (e.key === 'ArrowUp' || e.key === 'ArrowLeft') ? -1 : 0;
  if(!d) return;
  const bs = [...document.querySelectorAll('#mvw .mvb')], i = bs.indexOf(e.currentTarget);
  if(i < 0) return;
  e.preventDefault();
  const n = bs[(i + d + bs.length) % bs.length];
  n.focus(); setMainView(n.dataset.mv);
}
// Only the screen shell adapts to the mode (what to show is decided by the caller)
function applyMainView(){
  // Search, saved views, rooms and filters live in the chat slot, so hiding other slots hides them off-chat.
  document.querySelectorAll('#tbar > .tbs').forEach(s => { s.hidden = (s.dataset.tb !== mainView); });
  chatShell();   // compose box + participant column (.wrap.nops) only inside an open room
}
// ★Clicking a session/agent **sends it to the middle column** (2026-08-27: subagent work was opening in a modal).
// The modal is now diff-only — work history is a screen you keep watching, so a popup does not fit.
// ★2026-09-23: the work log left the tab row and opens in a popup window (wkPopup); inside that window
//   #wkm is shown full-size. toWork() keeps its name for callers — mainView is never touched.
function toWork(){ wkOpenModal(); }
function wkOpenModal(){
  const m = document.getElementById('wkm');
  if(!m) return;
  if(!wkOn){ wkRet = document.activeElement; }
  wkOn = true;
  if(!wtSplit) wtFocus = 1;
  m.hidden = false;
  const t = document.getElementById('wkmt'); if(t) t.textContent = T('Work log');
  const x = document.getElementById('wkmx');
  if(x){ x.setAttribute('aria-label', T('Close')); x.title = T('Close'); x.focus(); }
}
function wkClose(){
  if(ISWP || ISBP){ window.close(); return; }    // in a popup window, ✕ / Esc / last tab closed = close the window
  const m = document.getElementById('wkm');
  if(!m || m.hidden) return;
  m.hidden = true; wkOn = false;
  if(wkRet && wkRet.focus && document.contains(wkRet)) try{ wkRet.focus(); }catch(e){}
  wkRet = null;
}
(() => {
  const m = document.getElementById('wkm');
  if(!m) return;
  m.addEventListener('click', e => { if(e.target === m || e.target.id === 'wkmx') wkClose(); });
  // ⚠Capture phase + stopPropagation: Esc closes only this window, no other Esc handler fires.
  document.addEventListener('keydown', e => {
    if(!wkOn || e.key !== 'Escape') return;
    if(e.target && e.target.id === 'wkcbox' && (e.isComposing || e.target.value.trim())) return;   // ⚠Esc must not close the window over an unsent draft
    e.preventDefault(); e.stopPropagation(); wkClose();
  }, true);
  m.addEventListener('keydown', e => {
    if(e.key !== 'Tab') return;
    const fs = [...m.querySelectorAll('button,summary,a[href],input,select,[tabindex]:not([tabindex="-1"])')]
      .filter(x => x.offsetParent !== null);
    if(!fs.length) return;
    const a = fs[0], z = fs[fs.length-1];
    if(e.shiftKey && (document.activeElement === a || !m.contains(document.activeElement))){ e.preventDefault(); z.focus(); }
    else if(!e.shiftKey && (document.activeElement === z || !m.contains(document.activeElement))){ e.preventDefault(); a.focus(); }
  });
})();
// ★Even entering via refresh **draws the saved view** (measured 2026-09-09).
// Boot only called `loadTl(true)`, and per-view entry existed only in `setMainView` (= click). Measured:
// · «Failures» — after refresh `#feed` stayed **blank to the end** (`feedLen 0`). The tab looked selected, so it
// read as «is the server dead». The 2026-09-08 backup has the same shape, so it is a **pre-existing defect**.
// · «Tokens» — not blank. The main poll (2.5s) calls `loadWku()` and at its end
// `if(mainView === 'token') paintToken()` **draws it by itself on the first poll.**
// The only reason to put it here is removing that 2.5s blank (not fixing a bug).
// ⚠Do not substitute `setMainView(mainView)` — its side effects (chatMark etc.) would mark things 'seen' just by refreshing.
function bootView(){
  // ⚠`time` was missing here too: `#feed` stayed blank until the first timeline response. Fetch is already in flight (boot line).
  if(mainView === 'time'){  paintTl(); return; }
  if(mainView === 'token'){ paintToken(); loadWku(true); loadWkRange(true); return; }
  if(mainView === 'struct'){ paintStruct(); loadStruct(false); return; }
  if(mainView === 'br'){     paintBr();     loadBr(false);    return; }
  if(mainView === 'hist'){   paintHist();   loadHist(false);  return; }
  if(mainView === 'retro'){  paintRetro();  loadRetro(false); return; }
  if(mainView === 'pipe'){   plPaint(); return; }
}
// ★All tabs share one #feed scroller, so its scrollTop leaked across tabs (2026-09-24 audit: chat at 4136 → token opened mid-table at 1965).
//   Remember it per tab in memory; a tab never visited opens at the top. Chat keeps its own stick-to-bottom (toBottom below).
const mvScroll = {};
// ⚠The tab's async load refills #feed after this runs, so the first set clamps to a short page — keep re-applying
//   for a few seconds until the page is tall enough, and give up as soon as the user scrolls or the tab changes.
let mvScrollSeq = 0;
function mvScrollBack(){
  if(mainView === 'chat' || !feed) return;
  const v = mainView, want = mvScroll[v] || 0, seq = ++mvScrollSeq, end = Date.now() + 4000;
  feed.scrollTop = want;
  let user = false;
  const stop = () => { user = true; };
  const evs = ['wheel', 'touchstart', 'pointerdown', 'keydown'];
  evs.forEach(e => window.addEventListener(e, stop, {passive: true, capture: true}));
  const done = () => evs.forEach(e => window.removeEventListener(e, stop, {capture: true}));
  const tick = () => {
    if(user || seq !== mvScrollSeq || mainView !== v || Date.now() > end) return done();
    if(want && feed.scrollTop !== want && feed.scrollHeight - feed.clientHeight >= want) feed.scrollTop = want;
    requestAnimationFrame(tick);
  };
  if(want) requestAnimationFrame(tick); else done();
}
function setMainView(v){
  const _prev = mainView;
  if(feed) mvScroll[_prev] = feed.scrollTop;
  // ⚠'work' is a popup window now (wkPopup); old saved 'work'/'fail' (tabs removed) and unknown values fall back to the timeline.
  mainView = (v === 'chat' || v === 'time' || v === 'br'
              || v === 'token' || v === 'struct' || v === 'hist' || v === 'retro' || v === 'pipe') ? v : 'time';
  // ⚠Leaving the structure tab **stops playback** — otherwise it redraws an invisible screen every 0.6s
  if(mainView !== 'struct') strStop();
  document.documentElement.dataset.mv = mainView;   // CSS hook: html[data-mv=struct] lifts the .wrap width cap
  // ★Switching views **does not close open diff windows** (2026-09-04). As a modal it blocked what was behind and
  // had to be closed, but a floating window's purpose is to stay open while viewing other screens.
  tabSet('mbMainView', mainView);
  applyMainView();
  if(mainView === 'time'){
    agView = 'modal';
    buildMv(); paintTl(); mvScrollBack(); loadTl(true);
    tlgTick();   // ⚠the «Changes» chip fetches only from tlgTick; waiting for poll() left it without numbers after a tab switch
    return;
  }
  if(mainView === 'token'){
    agView = 'modal';
    buildMv(); paintToken(); mvScrollBack(); loadWku(true); loadWkRange(true);
    return;
  }
  if(mainView === 'struct'){
    agView = 'modal';
    buildMv(); paintStruct(); mvScrollBack(); loadStruct(false);
    return;
  }
  // ★Branches are fetched **only when the tab opens** — with no poll, this is the only entry (↻ re-reads)
  if(mainView === 'br'){
    agView = 'modal';
    brRetry = 0;
    buildMv(); paintBr(); mvScrollBack(); loadBr(false);
    return;
  }
  if(mainView === 'hist'){
    agView = 'modal';
    buildMv(); paintHist(); mvScrollBack(); loadHist(false);
    return;
  }
  if(mainView === 'retro'){
    agView = 'modal';
    buildMv(); paintRetro(); mvScrollBack(); loadRetro(false);
    return;
  }
  if(mainView === 'pipe'){
    agView = 'modal';
    buildMv(); plPaint(); mvScrollBack();
    return;
  }
  // chat (the old 'work' branch is gone — the work log is the #wkm modal now)
  agView = 'modal';
  chatMark();                           // Opening this view means 'seen' — clear the badge
  full();                               // Returning to chat redraws the feed (or the room list)
  if(place === 'all' && !q) feed.scrollTop = 0; else toBottom(false);
  buildMv();
}
// Toolbar slot contract: a tab paints its controls via tbSet('<mainView>', html) and wires them on the returned element.
function tbSet(k, html){
  const s = document.querySelector('#tbar > .tbs[data-tb="' + k + '"]');
  if(!s) return null;
  setHtml(s, html);   // unchanged html keeps focus/hover across poll repaints
  return s;
}
// tbSet for tabs without a static #tbar slot (struct/hist/retro): creates the slot once after the last one, then paints it.
function tbSlot(k, html){
  const bar = document.getElementById('tbar');
  if(bar && !bar.querySelector(':scope > .tbs[data-tb="' + k + '"]')){
    const s = document.createElement('div'), all = bar.querySelectorAll(':scope > .tbs');
    s.className = 'tbs'; s.id = 'tb' + k; s.dataset.tb = k; s.hidden = (mainView !== k);
    if(all.length) all[all.length - 1].after(s); else bar.appendChild(s);
  }
  return tbSet(k, html);
}
// Room list (place 'all') = tag chips + room cards in #feed; a room (place 'room:<r>' | 'dm') = member strip + the feed.
// ⚠Rule 1: cards carry metadata only (name · members · count · last time · tags) — never a subject or body.
let ROOMTAGS = {};     // state().roomTags {room: [tag]}; fed by roomTagsSet from the poll
let rcTag = '';        // selected tag chip ('' = «All»)
let rcEdit = null;     // {room, before} while a card's tag editor is open — poll repaints skip the grid so typing survives
function roomTagsSet(v){ ROOMTAGS = (v && typeof v === 'object' && !Array.isArray(v)) ? v : {}; }
function rcTags(r){ const t = ROOMTAGS[r]; return Array.isArray(t) ? t.filter(x => typeof x === 'string' && x) : []; }
// Editor text -> tags: split on commas/spaces, leading '#' dropped, de-duplicated case-insensitively, 8 x 20 chars (the server checks the same caps).
// ⚠Cut by code point (Array.from), not UTF-16 unit: .slice splits an emoji pair and the server counts code points.
function rcParse(s){
  const out = [], seen = new Set();
  String(s || '').split(/[,\s]+/).forEach(x => { x = Array.from(x.replace(/^#+/, '')).slice(0, 20).join(''); const lc = x.toLowerCase();
    if(x && !seen.has(lc) && out.length < 8){ seen.add(lc); out.push(x); } });
  return out;
}
// Per-room «seen up to» time (ns) in this browser only — a viewer convenience, not shared state.
// ⚠First run seeds every room at its latest post, so history does not show up as unread; a room first seen later counts all its posts.
const RC_SEEN_K = 'mbRoomSeen';
let rcSeen = (() => { const v = lsJson(RC_SEEN_K, null); return v && typeof v === 'object' && !Array.isArray(v) ? v : null; })();
const rcSeenSave = () => lsSetJson(RC_SEEN_K, rcSeen);
function rcMarkSeen(k){
  if(!k || k === 'all') return;
  const t = MSGS.filter(m => inPlace(m, k)).reduce((a, m) => Math.max(a, +m.t || 0), 0);
  if(!rcSeen) rcSeen = {};
  if(t > (rcSeen[k] || 0)){ rcSeen[k] = t; rcSeenSave(); }
}
// One card per room plus 'dm' (posts outside rooms); same inPlace predicate as the feed so counts match what opens.
function rcCards(){
  const seed = !rcSeen; if(seed) rcSeen = {};
  const absorb = soleRoom(), card = (k, name, IN, mem) => ({ k: k, name: name, n: IN.length, tags: k === 'dm' ? [] : rcTags(name),
    last: IN.reduce((a, m) => Math.max(a, +m.t || 0), 0),
    un: seed ? 0 : IN.filter(m => !m.mine && (+m.t || 0) > (rcSeen[k] || 0)).length,
    who: mem.length ? mem.slice() : [...new Set(IN.filter(m => !m.selfaddr).map(m => m.from).filter(Boolean))] });
  const live = roomNames(), cs = live.filter(r => !raHidden(r)).map(r => card('room:' + r, r, MSGS.filter(m => inPlace(m, 'room:' + r)), ((ROOMS || {})[r] || {}).members || []));
  raPendingNames(live).forEach(r => cs.push(Object.assign(card('room:' + r, r, [], []), {pend: true})));   // created, nobody joined yet (92c)
  const dm = MSGS.filter(m => inPlace(m, 'dm'));
  if(!(absorb && !dm.length)) cs.push(card('dm', 'dm', dm, []));
  if(seed){ cs.forEach(c => { if(c.last) rcSeen[c.k] = c.last; }); rcSeenSave(); }
  return cs.sort((a, b) => b.last - a.last || (a.name < b.name ? -1 : 1));
}
const rcLabel = c => c.k === 'dm' ? T('Outside rooms') : '# ' + c.name;
const rcAgo = t => t ? AGO(ago(Math.max(0, Math.round((Date.now() * 1e6 - t) / 1e9)))) : T('no messages yet');
const rcChip = t => '<span class=rctg>#' + esc(t) + '</span>';
function rcEditHtml(c){
  return '<div class=rced><input class="svin rcin" data-r="' + esc(c.name) + '" maxlength=200 autocomplete=off spellcheck=false'
    + ' value="' + esc(rcEdit.before.join(', ')) + '" placeholder="' + esc(T('Comma-separated — up to 8')) + '" aria-label="' + esc(T('Tags')) + '">'
    + '<div class=rcdiff>' + rcDiff(rcEdit.before, rcEdit.before) + '</div>'
    + '<button class="strp on rcok" data-r="' + esc(c.name) + '">' + esc(T('Save')) + '</button>'
    + '<button class="strp rcno">' + esc(T('Cancel')) + '</button><span class=rcerr></span></div>';
}
const rcDiff = (a, b) => '<span>' + esc(T('Before')) + ':</span> ' + (a.length ? a.map(rcChip).join(' ') : '<i>' + esc(T('None')) + '</i>')
  + ' <span>→ ' + esc(T('After')) + ':</span> ' + (b.length ? b.map(rcChip).join(' ') : '<i>' + esc(T('None')) + '</i>');
// Member id -> platform from the live session list (same `plat` the session rows draw). ⚠'' when no session matches — aiLogo would guess Claude.
function rcPlat(w){ const x = (SESS || []).find(s => s && s.mbox === w); return x ? (x.plat || 'cc') : ''; }
function rcWho(w){ const p = rcPlat(w); return (p ? aiLogo(p) : '') + esc(w); }
// opts (room admin, 92c): {pend, adm, sel} — pending class, plus checkbox and «Invite» · «Hide» when adm.
function rcCardHtml(c, opts){
  const nm = c.who.join(', '), o = opts || {};
  return (o.pend ? '<div class="rcard rapend" data-p="' : '<div class=rcard data-p="') + esc(c.k) + '">'
    + (o.adm ? '<input type=checkbox class="raop rachk" data-r="' + esc(c.name) + '"' + (o.sel ? ' checked' : '') + ' aria-label="' + esc(T('Select')) + '">' : '')
    + '<div class=rchd><button class=rcnm data-p="' + esc(c.k) + '" title="' + esc(rcLabel(c) + ' — ' + T('Open this room')) + '">' + esc(rcLabel(c)) + '</button>'
    + (c.un ? '<span class=rcun title="' + esc((c.un === 1 ? T('{n} unread post') : T('{n} unread posts')).replace('{n}', c.un)) + '">' + (c.un > 99 ? '99+' : c.un) + '</span>' : '') + '</div>'
    + '<div class=rcwho title="' + esc(nm) + '"><b>' + esc((c.who.length === 1 ? T('{n} person') : T('{n} people')).replace('{n}', c.who.length)) + '</b> ' + (c.who.length ? c.who.map(rcWho).join(', ') : '—') + '</div>'
    + '<div class=rcmeta><span>' + esc((c.n === 1 ? T('{n} post') : T('{n} posts')).replace('{n}', c.n)) + '</span><span>' + esc(rcAgo(c.last)) + '</span></div>'
    + (rcEdit && rcEdit.room === c.name && c.k !== 'dm' ? rcEditHtml(c)
      : '<div class=rctags>' + c.tags.map(rcChip).join('')
        + (c.k === 'dm' ? '' : '<button class="strp rcte" data-r="' + esc(c.name) + '" title="' + esc(T('Edit tags')) + '">' + esc(T('Tags')) + '</button>') + '</div>')
    + (o.adm ? '<div class=raact><button class="strp raop rainv" data-r="' + esc(c.name) + '">' + esc(T('Invite')) + '</button>'
      + '<button class="strp raop rahone" data-r="' + esc(c.name) + '">' + esc(T('Hide')) + '</button></div>' : '')
    + '</div>';
}
// Paints the room list into #feed. ⚠#feed is shared by every tab and full() writes innerHTML directly, so
//   the skip check is our own cache plus «the grid is really there» (setHtml's _sh would go stale).
function rcPaint(force){
  if(mainView !== 'chat' || place !== 'all' || q || ((rcEdit || raHold()) && !force)) return;
  // Chips group case-insensitively like the server's casefold dedupe; the first spelling seen is shown.
  const cs = rcCards(), lc = t => t.toLowerCase(), um = new Map();
  cs.forEach(c => c.tags.forEach(t => { if(!um.has(lc(t))) um.set(lc(t), t); }));
  const used = [...um.values()].sort();
  if(rcTag && !um.has(lc(rcTag))) rcTag = '';
  if(rcTag) rcTag = um.get(lc(rcTag));
  const show = rcTag ? cs.filter(c => c.tags.some(t => lc(t) === lc(rcTag))) : cs;
  const h = '<div class=rcw><div class=rcbar role=group aria-label="' + esc(T('Tags')) + '">'
    + ['', ...used].map(t => '<button class="strp rcf' + (t === rcTag ? ' on' : '') + '" data-t="' + esc(t) + '" aria-pressed=' + (t === rcTag) + '>'
      + (t ? '#' + esc(t) : esc(T('All'))) + '</button>').join('') + raBarHtml() + '</div>' + raToolHtml(show) + raBoxHtml()
    + (show.length ? '<div class=rcgrid>' + show.map(raCardHtml).join('') + '</div>' : '<div class=empty>' + esc(T('No rooms match.')) + '</div>') + '</div>';
  const nr = show.filter(c => c.k !== 'dm').length;   // the «Outside rooms» card is not a room
  // The dm card is named after the room count only when it is on screen, so the label matches the visible cards.
  document.getElementById('cnt').textContent = KE(U(nr, ' rooms'), PL(nr, 'room')) + (show.length > nr ? ' + ' + T('Outside rooms') : '');
  if(feed._rcH === h && feed.querySelector(':scope > .rcw')) return;
  feed.innerHTML = h; feed._rcH = h; feed._sh = undefined;
  rcBind(show);
}
function rcBind(cs){
  feed.querySelectorAll('.rcf').forEach(b => b.onclick = () => { rcTag = b.dataset.t || ''; rcPaint(true); });
  feed.querySelectorAll('.rcard').forEach(c => c.onclick = e => { if(!e.target.closest('.rced,.rcte,.raop') && !c.classList.contains('rapend')) rcOpen(c.dataset.p); });
  feed.querySelectorAll('.rcte').forEach(b => b.onclick = () => {
    rcEdit = {room: b.dataset.r, before: rcTags(b.dataset.r)}; rcPaint(true);
    const i = feed.querySelector('.rcin'); if(i){ i.focus(); i.select(); }
  });
  const i = feed.querySelector('.rcin'), d = feed.querySelector('.rcdiff');
  if(i && d){
    i.oninput = () => { d.innerHTML = rcDiff(rcEdit.before, rcParse(i.value)); };
    i.onkeydown = e => { if(e.key === 'Escape'){ e.stopPropagation(); rcEdit = null; rcPaint(true); } else if(e.key === 'Enter' && !e.isComposing) rcSave(); };
  }
  const no = feed.querySelector('.rcno'); if(no) no.onclick = () => { rcEdit = null; rcPaint(true); };
  const ok = feed.querySelector('.rcok'); if(ok) ok.onclick = rcSave;
  raBind(cs || []);   // «Manage» mode controls (92c)
}
// Saves the editor's tags (the diff above it is the confirmation); the server answers {ok, tags} | {ok:false, error}.
async function rcSave(){
  const i = feed.querySelector('.rcin'), ok = feed.querySelector('.rcok'), er = feed.querySelector('.rcerr');
  if(!i || !rcEdit || (ok && ok.disabled)) return;
  const room = rcEdit.room, tags = rcParse(i.value);
  if(ok) ok.disabled = true;
  try{
    const j = await postJSON('/api/rooms/tags', {room: room, tags: tags});
    if(!j || !j.ok) throw new Error((j && j.error) || '?');
    ROOMTAGS = Object.assign({}, ROOMTAGS, {[room]: Array.isArray(j.tags) ? j.tags : tags});
    rcEdit = null; rcPaint(true);
  }catch(e){
    if(er) er.textContent = T('Could not save') + ': ' + T(e.message);
    if(ok) ok.disabled = false;
  }
}
function rcOpen(k){
  rcEdit = null; place = k; setFilter('all'); shownN = 10;
  rcMarkSeen(k);
  buildRooms(); buildTabs(); buildPeople(); full();
  if(place === 'all') feed.scrollTop = 0; else toBottom(false);
}
// List mode has no compose box and no participant column (they belong to one room); the grid takes the width.
function chatShell(){
  const chat = mainView === 'chat', list = chat && place === 'all';
  const cp = document.getElementById('compose');
  if(cp) cp.style.display = chat && !list ? '' : 'none';
  const wr = document.querySelector('.wrap');
  if(wr) wr.classList.toggle('nops', !chat || list);
}
// Chat filter key: a missing/empty key (e.g. a button without data-k) falls back to 'all' instead of undefined.
// ⚠No thread chips exist any more — a 'thread:<t>' key (to-do rows, warning DMs, old saved views) opens that thread's
//   room and returns 'all', so no filter is ever active without a chip showing it.
function chatFilterKey(k){
  k = (typeof k === 'string' && k) ? k : 'all';
  if(k.indexOf('thread:') !== 0) return k;
  const th = k.slice(7), hit = (MSGS || []).find(m => m.thread === th);
  place = !hit ? 'all' : hit.room ? 'room:' + hit.room : absorbed(hit) ? 'room:' + soleRoom() : 'dm';
  return 'all';
}
function setFilter(k){ filter = chatFilterKey(k); }
// Toolbar strip of the open room («← Rooms» · name · members) and the room list repaint; runs on every poll.
// ⚠With exactly one room, room-less public posts are absorbed into it (soleRoom) — DMs never are.
function buildRooms(){
  const el=document.getElementById('rooms');
  if(!el) return;
  const absorb = soleRoom();
  // ⚠A place restored after refresh (97b) can be gone — a missing room, or «Outside rooms» with nothing left in it — back to the list.
  if(MSGS.length && (place.indexOf('room:')===0 ? !roomNames().includes(place.slice(5)) : place==='dm' && absorb && !MSGS.some(m=>inPlace(m,'dm')))) place='all';
  chatShell();
  vwSaveVis();   // 97-saved-views.js — place/filter changes all pass through here
  if(place==='all'){
    // A search on the room list swaps the cards for a flat feed of every place — say so and offer the way back.
    if(q && mainView === 'chat'){
      if(setHtml(el, '<button class="rm rmback" title="'+esc(T('Clear the search and go back to the room list'))+'">'+esc(T('← Rooms'))+'</button>'
        + '<b class=rmname>'+esc(T('Search results'))+'</b><span class=rmmem><i>'+esc(T('all rooms'))+'</i></span>'))
        el.querySelector('.rmback').onclick = () => { q = ''; const qb = document.getElementById('q'); if(qb) qb.value = ''; rcOpen('all'); };
    } else setHtml(el, '');
    rcPaint(false); return;
  }
  const c = rcCards().find(x => x.k === place) || {k: place, name: place.slice(5), who: [], tags: []};
  const who = c.who.slice(0, 8);
  if(!setHtml(el, '<button class="rm rmback" title="'+esc(T('Back to the room list'))+'">'+esc(T('← Rooms'))+'</button>'
    + '<b class=rmname title="'+esc(rcLabel(c))+'">'+esc(rcLabel(c))+'</b>'
    + '<span class=rmmem title="'+esc(c.who.join(', '))+'"><i>'+esc((c.who.length === 1 ? T('{n} person') : T('{n} people')).replace('{n}', c.who.length))+'</i>'
    + who.map(w => '<span class=rmw'+nmSty(w)+'>'+rcWho(w)+'</span>').join('')
    + (c.who.length > who.length ? '<i>+'+(c.who.length - who.length)+'</i>' : '')+'</span>')) return;   // unchanged: keep the handler
  el.querySelector('.rmback').onclick = () => rcOpen('all');
}
function buildTabs(){
  // ★Rooms were removed from this row — `buildRooms` above owns places. What remains here is **filters within the chosen place**.
  const tb=document.getElementById('tabs');
  if(place==='all'){ setHtml(tb, ''); paintCompose(); return; }   // the room list has no in-room filters
  if(mainView==='chat' && document.visibilityState==='visible') rcMarkSeen(place);   // new posts in the open room are read as they arrive
  const IN=MSGS.filter(m=>inPlace(m, place));   // same predicate as visible — counts cannot drift
  const w=IN.filter(waiting).length;
  const un=IN.filter(m=>m.mine&&m.audience.length&&!readersOf(m).length).length;
  const noack=IN.filter(m=>m.mine&&m.audience.length&&!((ACK[m.id]||{}).ack||[]).length).length;
  const dec=IN.filter(isDecided).length, fix=IN.filter(isFixed).length;
  const tabs=[['all',T('All')+' '+IN.length]]
    .concat(w?[['waiting',T('Awaiting reply')+' '+w]]:[])
    .concat(un?[['unread',T('Not read by them')+' '+un]]:[])
    .concat(noack?[['noack',T('Not acknowledged')+' '+noack]]:[])
    // ★Verdict/correction log — tags are on 483/531 (91%), enough material.
    // **Decisions**: what was decided is scattered across 72 threads. **Corrections**: this room reversed itself 40 times,
    // which is exactly what advocate charter axis 1 (unfounded acceptance) targets — collected, it becomes a checklist itself.
    .concat(dec?[['decided',T('Decisions')+' '+dec]]:[])
    .concat(fix?[['fixed',T('Corrections')+' '+fix]]:[]);
  setHtml(tb, tabs.map(x=>
    '<button class="tab'+(x[0]===filter?' on':'')+'" data-k="'+esc(x[0])+'">'+esc(x[1])+'</button>').join(''));
  document.querySelectorAll('#tabs .tab').forEach(t=>t.onclick=()=>{ setFilter(t.dataset.k); shownN=10; buildTabs(); full(); toBottom(false); });
  paintCompose();   // ★rides the poll so the static compose bar follows a language change too
}

