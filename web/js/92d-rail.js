// Left rail (index.html #rail): 56px icon rail; expanded = 208px, pushes content at >=1200px, overlays (with #railscrim) below.
//   State classes: body.rail (rail active) · #rail.open · body.railpush · body.railover. Layout itself is 93b-rail.css.
const RAIL_W = 1200;
let railOpen = false, railLangAt = '';
function railMode(w, open){ return !open ? 'collapsed' : w >= RAIL_W ? 'push' : 'overlay'; }
// ⚠A stored open state is restored only where it pushes — an overlay covering the page on load reads as a stuck panel.
function railRestore(v, w){ return v === '1' && w >= RAIL_W; }
function railActive(){ return !!(document.body && document.body.classList.contains('rail')); }
function railApply(){
  const r = document.getElementById('rail');
  if(!r || !railActive()) return;
  const m = railMode(innerWidth, railOpen), b = document.body.classList;
  r.classList.toggle('open', railOpen);
  b.toggle('railpush', m === 'push'); b.toggle('railover', m === 'overlay');
  const s = document.getElementById('railscrim'); if(s) s.hidden = m !== 'overlay';
  const tg = document.getElementById('railtg');
  if(tg){
    const l = T(railOpen ? 'Collapse sidebar' : 'Expand sidebar');
    tg.setAttribute('aria-expanded', String(railOpen)); tg.title = l + ' (⌘B / Ctrl+B)'; tg.setAttribute('aria-label', l);
  }
}
// ⚠A peek (opened by the Attention badge) never writes `sidereus.rail`; only railSet (toggle, Cmd/Ctrl+B) changes the saved pref.
let railPeek = false;
function railShow(open){ railOpen = !!open; railTip(null); railApply(); }
function railSet(open){
  railPeek = false; lsSet('sidereus.rail', open ? '1' : '0'); railShow(open);
}
function railPeekEnd(){ if(!railPeek) return false; railPeek = false; railShow(false); return true; }
// Outside press ends a peek; presses inside the rail (incl. the attention list) do not.
function railPeekOut(t){ return railPeek && !(t && t.closest && t.closest('#rail,#rattnl')); }
function railCloseOver(){
  if(!railOpen || railMode(innerWidth, railOpen) !== 'overlay') return false;
  if(!railPeekEnd()) railSet(false);
  const tg = document.getElementById('railtg'); if(tg) tg.focus({preventScroll: true});
  return true;
}
// Something layered above the overlay rail owns Esc (settings, Cmd+K, tour, work-log modal, the floating sessions drawer).
function railCovered(){
  const cm = document.getElementById('cfgm');
  if((cm && !cm.hidden) || document.querySelector('.cmdk.on')) return true;
  if(typeof tourIsOpen === 'function' && tourIsOpen()) return true;
  if(typeof wkOn !== 'undefined' && wkOn) return true;   // work-log modal (#wkm, 35b)
  return typeof SESOPEN !== 'undefined' && SESOPEN && !SESPIN;
}
// Cmd/Ctrl+B toggles the rail. ⚠Not inside an editable field: macOS Ctrl+B moves the caret back (chat box, #wkcbox).
function railKeyB(e){
  if(!(e.metaKey || e.ctrlKey) || e.altKey || e.shiftKey || !(e.key === 'b' || e.key === 'B' || e.code === 'KeyB')) return false;
  const t = e.target;
  return !(t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName || '')));
}
// Static rail markup is baked into the PAGE — translate it at boot and whenever the language changed (rides buildMv).
function railLang(){
  if(railLangAt === LANG) return;
  railLangAt = LANG;
  const r = document.getElementById('rail'); if(r) r.setAttribute('aria-label', T('Main navigation'));
  const h = document.querySelector('#rattnh > span'); if(h) h.textContent = T('Attention');
  try{ actRailN(); }catch(e){ softErr('actRailN', e); }   // #rattnb title/label carry the count (42-activity.js)
  document.querySelectorAll('#rail .rlab').forEach(e => {
    const b = e.closest('button'); if(b && b.id === 'bell') e.textContent = T('Alerts'); else if(b && b.id === 'gear') e.textContent = T('Settings');
  });
  railApply();
}
// #vtitle names the open view: the label of the active rail tab.
function railTitle(){
  railLang();
  const v = document.getElementById('vtitle'), on = document.querySelector('#mvw .mvb.on .mvl');
  if(v && on && v.textContent !== on.textContent) v.textContent = on.textContent;
}
// Collapsed-rail tooltip text: [name, shortcut hint]. Tabs use their .mvl label + digit; others their visible label or aria-label.
function railTipText(el, tabs, mac){
  if(!el) return null;
  const l = el.querySelector && el.querySelector('.mvl, .rlab'), i = tabs ? tabs.indexOf(el) : -1;
  const s = ((l && l.textContent) || el.getAttribute('aria-label') || '').trim();
  return s ? [s, i >= 0 && i < 9 ? String(i + 1) : el.id === 'railtg' ? (mac ? '⌘B' : 'Ctrl+B') : ''] : null;
}
// Quick tooltip (#railtip, aria-hidden: the button already has its name) while collapsed (the toggle: always, so no native title covers it); on mouse hover the native title
//   is parked in data-rtitle so both don't show. ⚠Focus leaves the title alone: it is the screen-reader description (shortcut).
let railTipEl = null, railTipOn = null;
function railTip(el, mouse){
  const t = railTipEl, p = railTipOn;
  if(p){ if(p.dataset.rtitle != null && !p.title) p.title = p.dataset.rtitle; delete p.dataset.rtitle; }   // always restore: a parked title is never lost
  railTipOn = null;
  const r = document.getElementById('rail'), x = el && (!railOpen || el.id === 'railtg') && r && r.offsetWidth && railActive() ? railTipText(el, [...r.querySelectorAll('#mvw .mvb')], /Mac/.test(navigator.platform || navigator.userAgent || '')) : null;
  if(!x){ if(t) t.hidden = true; return; }
  if(!t){ railTipEl = document.createElement('div'); railTipEl.id = 'railtip'; railTipEl.setAttribute('aria-hidden', 'true'); document.body.appendChild(railTipEl); }
  railTipEl.innerHTML = esc(x[0]) + (x[1] ? ' <kbd>' + esc(x[1]) + '</kbd>' : '');
  if(mouse && el.title){ el.dataset.rtitle = el.title; el.title = ''; }
  const b = el.getBoundingClientRect();
  railTipEl.style.left = (r.getBoundingClientRect().right + 8) + 'px'; railTipEl.style.top = (b.top + b.height / 2) + 'px';
  railTipEl.hidden = false; railTipOn = el;
}
function railTipBind(r){
  const pick = e => e.target.closest && e.target.closest('#mvw .mvb, #rattnb, #railtg, #bell, #gear');
  r.addEventListener('mouseover', e => { const b = pick(e); if(b && b !== railTipOn) railTip(b, true); });
  r.addEventListener('mouseout', e => { if(railTipOn && !railTipOn.contains(e.relatedTarget)) railTip(null); });
  r.addEventListener('focusin', e => { const b = pick(e); if(b && b.matches(':focus-visible')) railTip(b, false); });
  r.addEventListener('focusout', () => railTip(null));
  r.addEventListener('click', () => railTip(null), true);
  r.addEventListener('scroll', () => railTip(null), {passive: true});
  document.addEventListener('keydown', e => { if(e.key === 'Escape' && railTipOn) railTip(null); }, true);
}
(function(){
  if(ISPOP || ISWP || ISBP || !document.getElementById('rail')) return;   // popup windows have no rail
  document.body.classList.add('rail');
  railOpen = railRestore(lsGet('sidereus.rail', '0'), innerWidth);
  railLang(); railApply(); railTitle();
  const tg = document.getElementById('railtg'); if(tg) tg.addEventListener('click', () => railSet(!railOpen));
  const ab = document.getElementById('rattnb');
  if(ab) ab.addEventListener('click', () => { if(!railOpen){ railPeek = true; railShow(true); } const f = document.querySelector('#rattnl > .acp'); if(f) f.focus({preventScroll: true}); });
  const sc = document.getElementById('railscrim'); if(sc) sc.addEventListener('click', railCloseOver);
  railTipBind(document.getElementById('rail'));
  document.addEventListener('pointerdown', e => { if(railPeekOut(e.target)) railPeekEnd(); }, true);   // capture: repaints can detach the target
  // Crossing 1200px re-reads the stored choice: open pushes when wide; never left as an overlay after a shrink.
  const mq = window.matchMedia && matchMedia('(min-width: ' + RAIL_W + 'px)');
  if(mq){
    const re = () => { railPeek = false; railOpen = railRestore(lsGet('sidereus.rail', '0'), innerWidth); railTip(null); railApply(); };
    if(mq.addEventListener) mq.addEventListener('change', re); else if(mq.addListener) mq.addListener(re);
  }
  document.addEventListener('keydown', e => {
    if(e.isComposing || e.defaultPrevented) return;
    if(railKeyB(e)){ e.preventDefault(); railSet(!railOpen); return; }
    if(e.key === 'Escape' && !railCovered() && railCloseOver()) e.preventDefault();
  });
})();
