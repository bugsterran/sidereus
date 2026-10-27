// ★Sessions drawer (replaces the right column with a top-right modal-like view). Header «Sessions» opens `aside.lside` top-right; pin = the old right column.
//   ⚠Keys: sidereus.sespin ('1' pinned) · sidereus.sesdr ('1' drawer open). sidereusLsOff is migrated once ('0' forced open → pinned, else drawer) and removed.
let SESPIN = false, SESOPEN = false, sesdrBdg = '';
(function(){
  let p = lsGet('sidereus.sespin', null), ok = true;
  // One-time sidereusLsOff migration (09-24) — remove after 2026-10-24, when every open tab has run it.
  if(p === null){ p = lsGet('sidereusLsOff', null) === '0' ? '1' : '0'; ok = lsSet('sidereus.sespin', p) && lsDel('sidereusLsOff'); }
  if(ok){ SESPIN = p === '1'; SESOPEN = lsGet('sidereus.sesdr', null) === '1'; }
  if(ISPOP || ISWP || ISBP) SESOPEN = false;       // popup windows have no header button
})();
function sesdrPinned(){ return SESPIN; }
function sesdrSave(){ lsSet('sidereus.sespin', SESPIN ? '1' : '0') && lsSet('sidereus.sesdr', SESOPEN ? '1' : '0'); }
// Anchor right under the button row (like the alerts panel) — the header below it grows with tabs/cards and would eat the drawer height.
function sesdrPlace(){
  const h = document.querySelector('header .hrow'); if(h) document.body.style.setProperty('--sesdr-top', Math.round(h.getBoundingClientRect().bottom + 6) + 'px');
  // Bottom edge stops just above the status bar (#sbar), so the drawer uses the viewport minus header and footer.
  const f = document.getElementById('sbar'), ft = f && f.getBoundingClientRect().top;
  document.body.style.setProperty('--sesdr-bot', (ft > 0 ? Math.max(0, Math.round(innerHeight - ft)) + 6 : 12) + 'px');
}
function sesdrApply(){
  const b = document.body;
  b.classList.toggle('sespin', SESPIN); b.classList.toggle('sesopen', !SESPIN && SESOPEN);
  const btn = document.getElementById('sesb'); if(btn) btn.setAttribute('aria-expanded', String(SESPIN || SESOPEN));
  const pin = document.getElementById('sespin');
  if(pin){ pin.setAttribute('aria-pressed', String(SESPIN)); pin.textContent = SESPIN ? T('Unpin') : T('Pin');
           pin.title = SESPIN ? T('Unpin and go back to the drawer') : T('Pin as the right column (previous layout)'); }
  if(!SESPIN && SESOPEN) sesdrPlace();
}
function sesdrOpen(open, focus){
  if(SESPIN || (ISPOP || ISWP || ISBP)) return;
  const d = document.getElementById('sesdr'), btn = document.getElementById('sesb');
  if(open && !SESOPEN){   // remember the opener (top chip, attention row…) so closing returns focus there, not to #sesb (★ 2026-09-27 interaction audit)
    const ae = document.activeElement;
    sesdrFrom = ae && ae !== document.body && !(d && d.contains(ae)) ? ae : null;
  }
  SESOPEN = !!open; sesdrSave(); sesdrApply();
  if(SESOPEN){ if(focus && d) d.focus({preventScroll: true}); return; }
  // ⚠the hidden list would stay frozen by the hover guard (40-sessions.js) until the next mouseover
  if(sessHover){ sessHover = false; if(sessDirty){ sessDirty = false; buildSessions(); } }
  const back = sesdrFrom && sesdrFrom.isConnected ? sesdrFrom : btn;
  sesdrFrom = null;
  if(d && back && (focus || d.contains(document.activeElement))) back.focus({preventScroll: true});
}
let sesdrFrom = null;   // element focused when the drawer opened (null = #sesb)
// Jumps (Cmd+K, attention rows, top chips) open the drawer before scrolling to a row.
function sesdrReveal(){ if(!SESPIN && !SESOPEN) sesdrOpen(true, false); }
function sesdrPin(on, keepOpen){
  SESPIN = !!on; if(!SESPIN) SESOPEN = !!keepOpen;
  sesdrSave(); sesdrApply();
}
function sesdrBadge(){
  // sesCount (below): the number is open sessions, breakdown in the title.
  const s = sesCount(), at = attnBadgeN();
  const key = s.open + '|' + s.work + '|' + s.need + '|' + at + '|' + LANG;
  if(key === sesdrBdg) return;                      // skip identical writes (a11y observer watches childList)
  sesdrBdg = key;
  const n = document.getElementById('sesbn'), a = document.getElementById('sesba'), btn = document.getElementById('sesb');
  if(n) n.textContent = s.open ? String(s.open) : '';
  // ⚠labelled: two bare numbers side by side gave no hint which one was «need you»
  if(a) a.textContent = at ? T('need you {n}').replace('{n}', at) : '';
  if(btn) btn.title = TV({msg: 'Sessions — {o} open ({w} working · {n} waiting on you · {i} idle) · {a} need you',
                          vars: {o: s.open, w: s.work, n: s.need, i: s.idle, a: at}}) + '\n' + T('Show sessions');
}
// ★Drawer size (resizable): sidereus.sesdrsz {w,h} = width / max-height px, 0 = default (640 · content-driven).
//   ⚠Grips live in #sesrz, a fixed overlay sibling of the aside — the aside itself scrolls, so edge grips inside it would scroll away.
const SESDR_STEP = 24;
let SESDRSZ = {w: 0, h: 0};
try{ const v = JSON.parse(UIS.getItem('sidereus.sesdrsz') || 'null'); if(v && typeof v === 'object') SESDRSZ = {w: +v.w || 0, h: +v.h || 0}; }catch(e){ softErr('sesdrsz-read', e); }
function sesdrClampW(w){ return Math.round(Math.max(420, Math.min(Math.min(1200, innerWidth - 32), w))); }
function sesdrClampH(h){ return Math.round(Math.max(240, Math.min(innerHeight - 80, h))); }
function sesdrSzApply(){
  const s = document.body.style;
  if(SESDRSZ.w) s.setProperty('--sesdr-w', sesdrClampW(SESDRSZ.w) + 'px'); else s.removeProperty('--sesdr-w');
  if(SESDRSZ.h) s.setProperty('--sesdr-mh', sesdrClampH(SESDRSZ.h) + 'px'); else s.removeProperty('--sesdr-mh');
}
function sesdrSzSave(){ try{ if(SESDRSZ.w || SESDRSZ.h) UIS.setItem('sidereus.sesdrsz', JSON.stringify(SESDRSZ)); else UIS.removeItem('sidereus.sesdrsz'); }catch(e){ softErr('sesdrsz-write', e); } }
// ⚠Reset is per grip on purpose: an edge resets its own axis, the corner resets both — the tooltip says which.
function sesrzTips(o){
  if(!o) return;
  const tip = {w: 'Resize the sessions panel width — drag · arrows 24px · double-click/Home = default width',
               s: 'Resize the sessions panel height — drag · arrows 24px · double-click/Home = default height',
               ws: 'Resize the sessions panel — drag · arrows 24px · double-click/Home = default size'};
  o.querySelectorAll('.sesrz').forEach(g => { g.title = T(tip[g.dataset.rz] || tip.ws); g.setAttribute('aria-label', g.title); });
}
function sesdrRzWire(){
  const d = document.getElementById('sesdr');
  if(!d || ISPOP || ISWP || ISBP) return;
  const o = document.createElement('div'); o.id = 'sesrz';
  o.innerHTML = '<div class="sesrz sesrz-w" data-rz=w tabindex=0 role=separator aria-orientation=vertical></div>'
    + '<div class="sesrz sesrz-s" data-rz=s tabindex=0 role=separator aria-orientation=horizontal></div>'
    + '<div class="sesrz sesrz-sw" data-rz=ws tabindex=0 role=separator></div>';
  document.body.appendChild(o);
  sesrzTips(o);
  const meas = () => document.body.style.setProperty('--sesdr-ch', d.offsetHeight + 'px');
  if(window.ResizeObserver) new ResizeObserver(meas).observe(d);
  meas();
  const set = (k, w, h) => { if(k.includes('w')) SESDRSZ.w = sesdrClampW(w); if(k.includes('s')) SESDRSZ.h = sesdrClampH(h); sesdrSzApply(); };
  const reset = k => { if(k.includes('w')) SESDRSZ.w = 0; if(k.includes('s')) SESDRSZ.h = 0; sesdrSzApply(); sesdrSzSave(); };
  o.addEventListener('pointerdown', ev => {
    const g = ev.target.closest && ev.target.closest('.sesrz');
    if(!g || ev.button !== 0) return;
    ev.preventDefault();
    const g0 = {k: g.dataset.rz, x: ev.clientX, y: ev.clientY, w: d.offsetWidth, h: d.offsetHeight};
    let moved = false;
    g.classList.add('on');
    dragTrack(ev, g, mv => { moved = moved || mv.clientX !== g0.x || mv.clientY !== g0.y; set(g0.k, g0.w - (mv.clientX - g0.x), g0.h + mv.clientY - g0.y); }, e2 => {
      g.classList.remove('on');
      if(e2.type !== 'pointercancel' && moved) sesdrSzSave();
    });
  });
  o.addEventListener('dblclick', ev => { const g = ev.target.closest && ev.target.closest('.sesrz'); if(g) reset(g.dataset.rz); });
  o.addEventListener('keydown', ev => {
    const g = ev.target.closest && ev.target.closest('.sesrz'); if(!g) return;
    const k = g.dataset.rz;
    if(ev.key === 'Home'){ ev.preventDefault(); reset(k); return; }
    const dx = ev.key === 'ArrowLeft' ? SESDR_STEP : ev.key === 'ArrowRight' ? -SESDR_STEP : 0;   // right-anchored: left = wider
    const dy = ev.key === 'ArrowDown' ? SESDR_STEP : ev.key === 'ArrowUp' ? -SESDR_STEP : 0;
    if(!(k.includes('w') && dx) && !(k.includes('s') && dy)) return;
    ev.preventDefault();
    set(k, d.offsetWidth + dx, d.offsetHeight + dy); sesdrSzSave();
  });
  addEventListener('resize', sesdrSzApply);
  sesdrSzApply();
}
function sesdrLang(){
  document.documentElement.dataset.lang = LANG;   // CSS hook for en-only header widths (93-header-toolbar.css); not `lang` — that swaps CJK fonts
  const l = document.querySelector('#sesb .sesbl'); if(l) l.textContent = T('Sessions');
  const btn = document.getElementById('sesb'); if(btn) btn.setAttribute('aria-label', T('Sessions'));
  const d = document.getElementById('sesdr'); if(d) d.setAttribute('aria-label', T('Sessions'));
  const x = document.getElementById('sesx'); if(x){ x.title = T('Close (Esc)'); x.setAttribute('aria-label', T('Close')); }
  sesrzTips(document.getElementById('sesrz'));
  try{ srecLang(); }catch(e){ softErr('srecLang', e); }   // «Recently ended sessions» (41b-sesrecent.js)
  sesdrBdg = ''; sesdrApply(); try{ sesdrBadge(); }catch(e){ softErr('sesdrBadge', e); }
}
(function(){
  const btn = document.getElementById('sesb'), pin = document.getElementById('sespin'), x = document.getElementById('sesx');
  if(btn) btn.onclick = () => {
    if(!SESPIN) return sesdrOpen(!SESOPEN, true);
    const d = document.getElementById('sesdr');   // pinned: bring the column into view instead
    if(d){ d.scrollIntoView({behavior: 'smooth', block: 'nearest'}); d.focus({preventScroll: true}); }
  };
  if(pin) pin.onclick = () => { sesdrPin(!SESPIN, true); pin.focus({preventScroll: true}); };
  if(x) x.onclick = () => sesdrOpen(false, true);
  // Outside press closes. Capture phase: list repaints can detach the target before a bubbling handler sees it.
  //   ⚠Overlays the drawer spawns or sits under (diff, Cmd+K, settings, alarm, toasts, status drawer) and the top chips that open it do not count as outside.
  document.addEventListener('pointerdown', e => {
    if(!SESOPEN || SESPIN) return;
    const t = e.target;
    if(!t || !t.closest || t.closest('#sesdr,#sesrz,#sesb,#todo .td,#rattnl,#rattnb,#dpop,#spop,.cmdk,.cfgm,#alarm,#toasts,#sdrw,#stale')) return;
    sesdrOpen(false, false);
  }, true);
  // ⚠Esc yields to anything layered on top (earlier handlers preventDefault; later ones are checked here); preventDefault keeps branch detail open.
  document.addEventListener('keydown', e => {
    if(e.key !== 'Escape' || e.defaultPrevented || e.isComposing || !SESOPEN || SESPIN) return;
    const cm = document.getElementById('cfgm'), wm = document.getElementById('wkm'), dp = document.getElementById('dpop');
    if((cm && !cm.hidden) || (wm && !wm.hidden) || document.querySelector('.cmdk.on,.sdrw.on')
       || (dp && getComputedStyle(dp).display !== 'none')) return;
    e.preventDefault(); sesdrOpen(false, true);
  });
  const h = document.querySelector('header .hrow');
  if(h && window.ResizeObserver) new ResizeObserver(() => { if(SESOPEN && !SESPIN) sesdrPlace(); }).observe(h);
  addEventListener('resize', () => { if(SESOPEN && !SESPIN) sesdrPlace(); });
  sesdrRzWire();
  sesdrApply();
})();
// ★One session count for the header «Sessions» badge and its breakdown title (2026-09-24 UX audit: header and chips disagreed).
// open = not done; work = thinking, in a tool, or waiting on its own subagents / background jobs; idle = the rest.
// Sessions account pick (40b acctInPick 'sess'): other accounts' rows are left out of every count and tallied in oth.
function sesCount(){
  let open = 0, think = 0, tool = 0, subw = 0, need = 0, oth = 0;
  const pk = acctPick('sess');
  for(const x of SESS || []){
    if(x.state === 'done' || x.state === 'gone') continue;   // gone = external CLI killed, leaving soon
    if(!acctInPick(x, 'sess', pk)){ oth++; continue; }
    open++;
    if(x.state === 'think') think++;
    else if(x.state === 'tool') tool++;
    else if(x.state === 'ask' || x.state === 'abort') need++;   // ⚠blocked on the user — not idle
    else if(waitOnLabel(x, x.state)) subw++;
  }
  const work = think + tool + subw;
  return { open, work, need, idle: open - work - need, think, tool, subw, oth };
}
