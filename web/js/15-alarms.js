// ── Task-done alarms ───────────────────────────────────────────────────────────
//   External messenger notifications were removed, so completion is signaled **on the page**.
//   ★Both at once: a new card passes as **a 5s toast**, and **stacks in the bell until acknowledged.**
//   Read state is on the server (cards-read.txt), so it survives closing the browser. Cards themselves are never deleted (history).
let CARDS=[], CREAD='', CRIDS=new Set(), seenToast=null, alarmOpen=false;
// ★The alarm list draws **only the latest 50** (2026-08-26). To see older cards press «Full history» —
//   only then is the cap lifted (that is why the button exists). What is hidden is stated on screen.
const ALARM_MAX = 50;
let alarmAll = false;
let unreadOnly=false;              // narrows the bell list to unread only
unreadOnly = lsGet('mbUnreadOnly', null) === '1';
const FAV_PLAIN = document.getElementById('fav') ? document.getElementById('fav').href : '';
// With unread cards a badge sits at top right (the corner the mark leaves free); no ring, the favicon has no tile behind it.
// ⚠Coordinates are in the favicon's 32-unit viewBox; the badge must clear the moon disc (16,16 r12).
const FAV_DOT = FAV_PLAIN.replace("%3C/svg%3E",
  "%3Ccircle cx='28.2' cy='3.8' r='3.8' fill='%23e0725f'/%3E%3C/svg%3E");
const CKIND = { wait:'Awaiting input', ask:'Awaiting answer', abort:'Aborted', done:'Done', note:'Alerts', ctx:'Context nearly full',
                agent:'Subagent done', bgdone:'Background done', fail:'Failures',
                flimit:'Stopped by limit', fcut:'Cut by external cause', fcheck:'Cause needs a look', fwreck:'Half-edited files' };
// Shown name of a card kind ('' = unknown kind); 'Aborted' alone is a different Korean word, hence the context.
const ckName = k => CKIND[k] ? T(CKIND[k], k === 'abort' ? 'state' : null) : '';   // ★a name collided with the existing KIND and killed JS (2026-08-19)
function ckey(c){ return c.at+'|'+c.kind+'|'+c.project; }
function isoHM(iso){ return (iso||'').slice(11,16); }   // ⚠string slice of the stored ISO; not hhmm() (05-i18n.js), which converts epoch/Date
// ★Unread = newer than the watermark **and not individually read**. Why both are kept is in the server comment
//   (setting the watermark to an old card's time on click would mark even newer cards read).
// `c.old` = past the server's expire age (24h, failures 3d) — counts as read so the badge agrees across tabs.
function isNew(c){ return !c.old && (!CREAD || c.at > CREAD) && !CRIDS.has(ckey(c)); }
// Alert policy (per browser, UIS `mbAlertPolicy`): per kind 'badge' | 'list' (quiet) | 'hide' (view-time only; cards stay stored).
// ★2026-09-23: 7d = 610 cards, agent 485 — agent/bgdone pinged constantly, so the default 'imp' keeps them quiet.
// Failure alerts (flimit/fwreck/fcheck/fcut) replaced the old 'fail' kind and the «Failures» tab (2026-09-23);
//   under «Important only» an external cut is list-only — the response is just "rerun", nothing to decide.
const APOL_PRESET = { imp: {ask:'badge', abort:'badge', flimit:'badge', fwreck:'badge', fcheck:'badge', fcut:'list',
                            agent:'list', bgdone:'list'},
                      all: {ask:'badge', abort:'badge', flimit:'badge', fwreck:'badge', fcheck:'badge', fcut:'badge',
                            agent:'badge', bgdone:'badge'} };
function apolLoad(){
  const v = lsJson('mbAlertPolicy', null);
  const preset = (v && (v.preset === 'all' || v.preset === 'custom')) ? v.preset : 'imp';
  const kinds = Object.assign({}, APOL_PRESET.imp, preset === 'all' ? APOL_PRESET.all : {});
  if(preset === 'custom' && v.kinds) for(const k in v.kinds) if(['badge','list','hide'].includes(v.kinds[k])) kinds[k] = v.kinds[k];
  return {preset, kinds, group: !(v && v.group === false)};
}
let APOL = apolLoad();
function apolSave(){ lsSetJson('mbAlertPolicy', APOL); }
// ⚠Unknown future kinds: 'list' unless the preset is «Everything» (everything badges).
function apolOf(kind){ return APOL.kinds[kind] || (APOL.preset === 'all' ? 'badge' : 'list'); }
// Newest-first cards -> groups. With grouping on, same cwd+kind within 30 min of the group's newest card merge.
const AGRP_MS = 30 * 60 * 1000;
function cardGroups(cards){
  const out = []; let g = null;
  for(const c of cards){
    const who = c.cwd || c.project || '', t = Date.parse(c.at) || 0;
    if(APOL.group && g && g.kind === c.kind && g.who === who && g.t0 - t <= AGRP_MS) g.items.push(c);
    else { g = {kind: c.kind, who, t0: t, items: [c]}; out.push(g); }
  }
  return out;
}
const grpNew = g => g.items.some(isNew);
const visCards = () => CARDS.filter(c => apolOf(c.kind) !== 'hide');
// Badge / tab title / favicon / top bar all use this: unread groups whose kind is set to 'badge'.
function alarmBadgeN(){ return cardGroups(visCards()).filter(g => apolOf(g.kind) === 'badge' && grpNew(g)).length; }
// Verdict = a post closing the thread (`[DONE]` and its Korean equivalents) · correction = a post reversing an earlier one (a Korean correction tag, FIXT).
//   The tag set reuses `DONE` (= mailbox_core.CLOSE_TAGS) — two copies would drift apart someday.
const FIXT = new Set(['정정','수정','철회','번복']);
const tagOf = m => { const t = kindOf(m.subject); return t ? t.tag : ''; };
const isDecided = m => { const t = tagOf(m); return DONE.has(t) || DONE.has(String(t).toUpperCase()); };
const isFixed = m => FIXT.has(tagOf(m));
// ── Failure alerts: response line + action buttons (2026-09-23, replaced the «Failures» tab) ──
//   ⚠Actions stay read-only toward sessions: «Copy resume prompt» only copies a generic prompt, never sends it.
const FA_ACTS = { flimit: [['work','Open activity']],
                  fcut:   [['copy','Copy resume prompt'], ['work','Open activity']],
                  fwreck: [['diff','Open diff'], ['copy','Copy resume prompt']],
                  fcheck: [['work','Open activity at that point']] };
function faLine(c){
  if(c.kind === 'flimit') return (c.reset ? T('Stopped by the usage limit — rerun after the {w} reset at {t}').replace('{t}', c.reset)
                                          : T('Stopped by the usage limit — rerun after the {w} reset')).replace('{w}', c.win || '5h');
  if(c.kind === 'fwreck') return T('Cut off midway, {n} half-edited files left — revert or have it continue').replace('{n}', c.n || 0);
  if(c.kind === 'fcut') return T('Cut off by an external cause — rerun the same instruction');
  if(c.kind === 'fcheck') return T('Cause could not be read — check where it stopped');
  // Cards saved before the ctx card carried numbers keep their stored English text.
  if(c.kind === 'ctx' && c.pct != null) return TV({msg: '{pct}% ({used}k / {win}k) — leave a handover before auto-compaction', vars: {pct: c.pct, used: c.used, win: c.win}});
  const t = cardText(c);
  return t && c.kind === 'agent' && +c.resumes > 0 ? t + ' · ' + T('resumed {n}×').replace('{n}', +c.resumes) : t;
}
// Tooltip = the harness basis phrase, so "why this alert" stays checkable (as the failure tab's grade chip did).
function faTip(c){
  if(!FA_ACTS[c.kind]) return '';
  const base = c.kind === 'fwreck' ? T(c.why || '')
    : (c.why ? T('Basis — the notice text contained “{p}”').replace('{p}', T(c.why))
             : T('A failure notice whose cause text could not be read — that is why it needs a look'));
  return [TN(c.label || ''), T(srvEn(c.sig || '')), base].filter(Boolean).join('\n');
}
// Failure cards are not "click = read" (HANDOVER 2026-09-23 §7-5): acting is not acknowledging,
//   so an unread card gets an explicit «Read» button (data-fread) and the actions leave it unread.
function faBtns(c, nw){
  const a = FA_ACTS[c.kind];
  return a ? '<div class=cfa>' + a.map(x => '<button class=cfab data-fa="'+x[0]+'" data-fk="'+esc(ckey(c))+'">'
    + esc(T(x[1])) + '</button>').join('')
    + (nw ? '<button class="cfab cfar" data-fread data-fk="'+esc(ckey(c))+'">'+esc(T('Read'))+'</button>' : '') + '</div>' : '';
}
function faAct(btn){
  const k = btn.getAttribute('data-fk'), act = btn.getAttribute('data-fa');
  const c = (CARDS || []).find(x => ckey(x) === k);
  if(!c) return;
  if(act === 'work'){
    if(c.ekind === 'agent' && c.tid) wkPopup(c.cwd, c.tid);
    else openSession(c.cwd, c.sid ? 'sess:' + c.cwd + '|' + c.sid : undefined);
  } else if(act === 'diff'){
    const row = tlLiveOf(c.cwd) || (SESS || []).find(s => s.cwd === c.cwd || ((s.repos || []).indexOf(c.cwd) >= 0));   // cards are Claude's
    loadDiff(row ? row.cwd : c.cwd);
  } else if(act === 'copy'){
    // ⚠Metadata only: agent label + grade reason (harness-derived signature) — nothing from the conversation.
    const txt = T('Continue the interrupted {a} task (stopped because: {r})').replace('{a}', c.label ? TN(c.label) : T('Subagent'))
      .replace('{r}', T(srvEn(c.sig)) || ckName(c.kind));
    copyText(txt).then(ok => note(ok ? T('Resume prompt copied — paste it into that session') : T('Could not copy')));
  }
}
// Waiting-for-me cards jump straight to the session's terminal tab when it can be raised; otherwise the click stays read-only.
const ALARM_TERM_KINDS = new Set(['ask', 'blocked']);
// Shared by every waiting-for-me surface (panel, toast, attention row, activity pill, OS notification): sid if its tab can be raised.
//   ⚠termLive/termCanFocus/termGo live in 88d-term.js (loads later) — call only at click/render time, never at load.
function termJumpSid(sid){
  const row = sid ? (SESS || []).find(s => s && s.sid === sid) : null;
  return row && termLive(row) && termCanFocus(row) ? sid : '';
}
function alarmTermSid(c){
  return c && ALARM_TERM_KINDS.has(c.kind) ? termJumpSid(c.sid) : '';
}
// Registered before 95-poll's #alist onclick, so it runs first and leaves read-marking to that handler.
function alarmTermClick(e){
  const t = e.target;
  if(!t || !t.closest || t.closest('[data-gx],[data-fa],[data-fread]')) return;
  const el = t.closest('.card[data-ck]');
  if(!el) return;
  const g = el.hasAttribute('data-gi') ? AGROUPS[+el.getAttribute('data-gi')] : null;
  const k = el.getAttribute('data-ck');
  const c = g ? g.items[0] : (CARDS || []).find(x => ckey(x) === k);   // a group acts on its newest member
  const sid = alarmTermSid(c);
  if(sid) termGo(sid);
}
const ALIST_EL = document.getElementById('alist');
if(ALIST_EL) ALIST_EL.addEventListener('click', alarmTermClick);
function cardHTML(c, cls, noHint, term){
  const tip = faTip(c) || (term && alarmTermSid(c) ? T('Click to open its terminal') : '');
  return '<div class="card '+(cls||'')+' k-'+esc(c.kind||'note')+'" data-ck="'+esc(ckey(c))+'"'+(tip?' title="'+esc(tip)+'"':'')+'>'
    + '<div class=crow1><b>'+esc(ckName(c.kind)||c.title||T('Alerts'))   /* ⚠title is session-written data: never through T() */+'</b>'
    + (c.project?'<span class=cproj>'+esc(c.project)+'</span>':'')
    + '<span class=ctime>'+esc(isoHM(c.at))+'</span>'
    + (!noHint && (cls||'').indexOf('new') >= 0 && !FA_ACTS[c.kind] ? '<span class=chint>'+esc(T('click = mark read'))+'</span>' : '')
    + '</div>'
    + (faLine(c)?'<div class=ctxt>'+esc(faLine(c))+'</div>':'') + faBtns(c, (cls||'').indexOf('new') >= 0) + '</div>';
}
const titleOf = (hands, unread, name) =>
  (hands ? '[' + hands + '] ' : '') + (unread ? '(' + unread + ') ' : '') + name;
// A group of one renders as a plain card; a larger group gets a count title and the time span.
let AGROUPS = [];
function groupHTML(g, i){
  const c = g.items[0], n = g.items.length, nw = grpNew(g);
  // ★The click rule is stated once in the panel header (buildAlarm), not on every card (2026-09-24 audit: noise).
  if(n === 1) return cardHTML(c, nw ? 'new' : '', true, true);
  const d = grpRows(g).length;   // distinct agents/jobs — a resumed agent is one agent, not two
  const ttl = g.kind === 'agent' ? T('{n} subagents done').replace('{n}', d)
            : g.kind === 'bgdone' ? T('{n} background jobs done').replace('{n}', d)
            : (ckName(g.kind) || c.title || T('Alerts')) + ' ×' + n;
  const tip = faTip(c) || (alarmTermSid(c) ? T('Click to open its terminal') : '');
  return '<div class="card '+(nw?'new':'')+' k-'+esc(g.kind||'note')+'" data-ck="'+esc(ckey(c))+'" data-gi="'+i+'"'+(tip?' title="'+esc(tip)+'"':'')+'>'
    + '<div class=crow1><b>'+esc(ttl)+'</b>'
    + (c.project?'<span class=cproj>'+esc(c.project)+'</span>':'')
    + '<span class=ctime>'+esc(isoHM(g.items[n-1].at)+'–'+isoHM(c.at))+'</span>'
    + '</div>'
    + (FA_ACTS[g.kind] ? (faLine(c)?'<div class=ctxt>'+esc(faLine(c))+'</div>':'') : grpLines(g))
    + faBtns(c, nw) + '</div>';   // actions act on the newest member
}
// ⚠A group used to show only its newest member's line, so "3 agents done" read as one agent (2026-09-24 report).
//   Every member's own card text is listed (already-stored metadata, nothing new); repeats collapse to ×n.
//   Past GRP_LINES a toggle expands in place; the open set survives the 2.5s poll redraw.
const GRP_LINES = 5, GRP_OPEN = new Set();
// Agent cards merge by agent id (`aid`), else by description — older cards of one resumed agent carry
//   «agent: X» and «general-purpose: X». The real type label wins over the «agent» fallback.
const agDesc = t => { const i = t.indexOf(': '); return i >= 0 ? t.slice(i + 2) : t; };
function grpRows(g){
  const rows = [], at = new Map();
  for(const m of g.items){      // newest first
    const t = cardText(m); if(!t) continue;
    const ag = g.kind === 'agent', key = ag ? (m.aid || agDesc(t)) : t, runs = 1 + (ag ? (+m.resumes || 0) : 0);
    if(at.has(key)){ const r = rows[at.get(key)]; r.n += runs; if(/^agent: /.test(r.t) && !/^agent: /.test(t)) r.t = t; }
    else { at.set(key, rows.length); rows.push({t, n: runs, at: m.at, ag}); }
  }
  return rows;
}
function grpLines(g){
  const rows = grpRows(g);
  if(!rows.length) return '';
  const k = ckey(g.items[0]), open = GRP_OPEN.has(k), vis = open ? rows : rows.slice(0, GRP_LINES);
  return '<div class="ctxt cgl">' + vis.map(r => '<div><span class=cglt>'+esc(isoHM(r.at))+'</span> '+esc(r.t)
      + (r.n > 1 ? ' <span class=cglt>'+esc(r.ag ? T('resumed {n}×').replace('{n}', r.n - 1) : '×'+r.n)+'</span>' : '')+'</div>').join('') + '</div>'
    + (rows.length > GRP_LINES ? '<button class=cgx data-gx="'+esc(k)+'">'
      + esc(open ? T('Collapse') : T('Show {n} more').replace('{n}', rows.length - GRP_LINES)) + '</button>' : '');
}
// Transition cards (wait/ask/abort) arrive with an empty body — cards() strips old stored text (rule 1, 2026-09-25).
// Agent cards carry the raw Agent description; strip a leading [pl:…] tag for display and grouping (pipeline code reads sub labels, not cards).
function cardText(c){ const t = plStrip((c.text || '').trim()); return c.kind === 'bgdone' ? monLab(t) : t; }
function buildAlarm(){
  const unread = alarmBadgeN();
  const bell=document.getElementById('bell'), bdg=document.getElementById('bdg');
  bell.classList.toggle('has', unread>0);
  bdg.textContent = unread>99?'99+':unread;
  const list=document.getElementById('alist');
  const au=document.getElementById('aunread');
  if(au) au.classList.toggle('on', unreadOnly);
  const ahd = document.querySelector('#alarm .ahead');
  if(ahd){   // own row under the header: inline it squeezed the title and actions into two lines
    let ah = document.getElementById('ahint');
    if(!ah){ ah = document.createElement('div'); ah.id = 'ahint'; ah.className = 'chint'; ah.style.cssText = 'white-space:normal;margin:-2px 0 7px';
      ahd.after(ah); }
    ah.textContent = T('click = mark read · groups as a whole · failures via the Read button');
  }
  const vis = visCards(), polN = CARDS.length - vis.length;   // polN = hidden by the alert policy (still stored)
  const all = cardGroups(vis);
  const pool = unreadOnly ? all.filter(grpNew) : all;
  const hidN = all.length - pool.length;
  const shown = alarmAll ? pool : pool.slice(0, ALARM_MAX);   // the list is newest-first, so cut from the front
  const capN = pool.length - shown.length;
  AGROUPS = shown;
  setHtml(list, shown.length
    ? shown.map((g, i) => groupHTML(g, i)).join('')
      + (capN ? '<div class=hidnote>'+esc(T('Showing the latest {n} — the other {m} are under `Full history`').replace('{n}', ALARM_MAX).replace('{m}', capN))+'</div>' : '')
      + (hidN ? '<div class=hidnote>'+esc(T('{n} read cards hidden — turn off `Unread only` to see them').replace('{n}', hidN))+'</div>' : '')
      + (polN ? '<div class=hidnote>'+esc(T('{n} cards hidden by alert settings').replace('{n}', polN))+'</div>' : '')
    : (CARDS.length
        ? '<div class=hidnote>'+esc(T('No unread cards — turn off `Unread only` to see {n} in history.').replace('{n}', CARDS.length))+'</div>'
        : '<div class=hidnote>'+esc(T('No alarms yet — they pile up here when a session ends its turn.'))+'</div>'));
  // ★Tab title and favicon use **the same value** (unread card count) — the title used to be 'sessions awaiting input',
  //   meaning something different from the bell badge, which prompted "why is (2) there?" (2026-08-19).
  // ★The popup's title is left alone — diffShow puts that window's repo name in it
  //   (with several windows the title is the only way to tell them apart). Unguarded, polling overwrites it every time.
  // ★The leading `[n]` is **sessions needing me** — now the attention strip's count (17-attention.js), so "1 question waiting" isn't buried as chat piles up
  buildAttn(); attnTitle();
  const tb=document.getElementById('todo'); if(tb) buildTodo();     // the bar shrinks too right after marking read
  const fav = document.getElementById('fav');
  if (fav && FAV_PLAIN) fav.href = unread ? FAV_DOT : FAV_PLAIN;
}
// ★Toast — stays **10s**, click = **acknowledged**.
//   It was 5s and click opened the bell: glance at another window and it was already gone,
//   and clicking didn't mark read, so the badge stayed (the only way out was «Mark all read»).
//   (a) hovering **pauses** the timer (vanishing while reading was the original complaint — gone 3s after leaving)
//   (b) click = mark that card read + dismiss (bell not opened — no reason to show what was already seen)
const TOAST_MS = 10000, TOAST_LEAVE_MS = 3000, TOAST_MAX = 5;
// Toast click: buttons act; else mark read, and a waiting-for-me card also raises its terminal tab.
function toastAct(c, e){
  const fb = e.target.closest && e.target.closest('[data-fa]'); if(fb) faAct(fb);
  const fr = e.target.closest && e.target.closest('[data-fread]');
  if(fr || !FA_ACTS[c.kind]) markCardsRead([ckey(c)]);
  const sid = fb || fr ? '' : alarmTermSid(c);
  if(sid) termGo(sid);
}
function toast(c){
  const box=document.getElementById('toasts');
  const el=document.createElement('div');
  el.className='toast'; el.innerHTML=cardHTML(c,'new',false,true);
  let tm=null;
  const gone=()=>{ el.classList.add('out'); setTimeout(()=>el.remove(), 320); };
  const arm=(ms)=>{ clearTimeout(tm); tm=setTimeout(gone, ms); };
  el.onmouseenter=()=>clearTimeout(tm);
  el.onmouseleave=()=>arm(TOAST_LEAVE_MS);
  // Failure toasts: an action or a body click only dismisses; only the «Read» button marks read.
  el.onclick=(e)=>{ e.stopPropagation(); clearTimeout(tm); toastAct(c, e); el.remove(); };
  // Cap the stack: a burst of cards (13 measured) pushed the oldest toast far above the viewport.
  while(box.children.length>=TOAST_MAX) box.firstElementChild.remove();
  box.appendChild(el);
  arm(TOAST_MS);
}
// Remember the dragged size — forcing a re-stretch every time would make resizing pointless.
// ⚠The observer used to save **every** size change while open, including the list growing or shrinking on its own
//   (a click marking read redraws it), so a content height got frozen as `height` on the next load and the popover
//   stopped short with items below (2026-09-24: saved h 647 on a 900px screen, 847 available).
//   ⇒ Save only after a pointer drag on the panel changed its size; the new key drops the polluted heights once.
const ASIZE_KEY = 'mbAlarmSize2';
let alarmPtrEnd = 0;
function alarmSizeLoad(){
  const a = document.getElementById('alarm');
  if(!a) return;
  const v = lsJson(ASIZE_KEY, {});
  if(v.w > 280) a.style.width = v.w + 'px';
  if(v.h > 140) a.style.height = v.h + 'px';
}
function alarmSizeWatch(){
  const a = document.getElementById('alarm');
  if(!a) return;
  // The resize handle writes inline width/height; a content reflow does not — so compare those, not offsetHeight.
  let s0 = null;
  a.addEventListener('pointerdown', () => { s0 = a.style.width + '|' + a.style.height; });
  addEventListener('pointerup', () => {
    if(!alarmOpen || s0 === null) return;        // remember size only while open (so closed = 0 is not saved)
    alarmPtrEnd = Date.now();   // ⚠a grip drag ending outside the panel fires a click there — the outside-click close skips it
    const moved = (a.style.width + '|' + a.style.height) !== s0, w = Math.round(a.offsetWidth), h = Math.round(a.offsetHeight);
    s0 = null;
    if(moved){ lsSetJson(ASIZE_KEY, {w, h}); alarmPlace(); }   // the grip grows rightward past the bell — re-anchor on screen
  });
}
// ★Alarm window coordinates come from **the feed column's actual position** (2026-08-27: it could overlap).
//   Fixed CSS px can't match it: `.wrap` is **centered** at max-width 2240, so the feed's left moves
//   with window width (measured: computed 386 vs actual 413 — it ate 13px of the participants panel).
//   CSS can't reference other elements, so only this line is JS.
function alarmPlace(){
  const a = document.getElementById('alarm'), f = document.getElementById('feed');
  if(!a || !f) return;
  if(getComputedStyle(a).position !== 'fixed') return;      // let the narrow-screen rule win
  // ★Anchored to **the bell button** (the button pressed, not the header). Covering content behind is a popover's nature.
  //   Bell in the left rail (#rail, bottom): the panel opens to the right of the rail, bottom edge on the bell's bottom,
  //   growing upward (top >= 56px, below the 48px bar). Bell elsewhere (no rail): right edge under the bell, as a dropdown.
  //   ⚠Right-aligning to a rail bell put the panel bottom-left and capped it near 300px wide.
  const bell = document.getElementById('bell');
  const br = bell ? bell.getBoundingClientRect() : null;
  const rail = bell && bell.closest && bell.closest('#rail');
  if(br && rail){
    const left = Math.round(rail.getBoundingClientRect().right) + 8, room = Math.max(280, innerWidth - left - 12);
    a.style.maxWidth = room + 'px';   // caps the saved width without overwriting it
    a.style.left = left + 'px'; a.style.right = 'auto'; a.style.top = 'auto';
    a.style.bottom = Math.max(0, Math.round(innerHeight - br.bottom)) + 'px';
    a.style.maxHeight = Math.max(160, Math.round(br.bottom) - 56) + 'px';
    return;
  }
  a.style.bottom = 'auto';
  // right edge aligned to the bell (like a dropdown). Clipped on both sides so it never leaves the screen.
  const at = br || {left: innerWidth - 14, right: innerWidth - 14, top: 46, bottom: 46};
  // ⚠Runs before `.open` (display:none → offsetWidth 0), so popAnchor fell back to 420 while a saved 1056 rendered:
  //   right edge at 1678 on an 1100 screen. ⇒ Pass the saved width, capped (and max-width'd) to the room left of the bell.
  const room = Math.max(300, Math.round(at.right) - 12);
  a.style.maxWidth = room + 'px';
  const t = popAnchor(a, null, {at, align: 'right', gap: 6, pad: 12, w: Math.min(parseFloat(a.style.width) || 420, room)});
  a.style.right = 'auto';
  // a remembered height larger than the remaining space overflows — clip to the screen (the remembered value is untouched)
  // ⚠Leave room for the 30px status bar + 8px gap (the panel covered «Connected»).
  a.style.maxHeight = Math.max(160, innerHeight - t - 38) + 'px';
}
addEventListener('resize', alarmPlace);
function openAlarm(force){
  const was = alarmOpen, a = document.getElementById('alarm');
  alarmOpen = force===undefined ? !alarmOpen : force;
  if(alarmOpen) alarmPlace();
  if(!alarmOpen) alarmAll = false;       // closing restores the cap — next open starts again from 50
  a.classList.toggle('open', alarmOpen);
  const bl = document.getElementById('bell'); if(bl) bl.setAttribute('aria-expanded', String(alarmOpen));
  // Focus moves into the panel on open and back to the bell when it closes from inside (★ 2026-09-27 interaction audit).
  if(alarmOpen && !was){ a.tabIndex = -1; a.focus({preventScroll: true}); }
  else if(!alarmOpen && was && a.contains(document.activeElement)){ const b = document.getElementById('bell'); if(b) b.focus({preventScroll: true}); }
}
// Esc closes the alarm panel first; preventDefault so later Esc handlers (branch detail etc.) skip this press.
document.addEventListener('keydown', e => {
  if(e.key !== 'Escape' || !alarmOpen || e.defaultPrevented || e.isComposing) return;
  e.preventDefault(); openAlarm(false);
});
alarmSizeLoad(); alarmSizeWatch();
// apply the saved selection to the screen (including hidden rows and hidden input)
setTimeout(() => { applyMainView(); buildMv(); loadTl(true); bootView(); }, 0);

