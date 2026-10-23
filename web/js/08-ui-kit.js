// ★Shared UI kit (2026-09-24 refactor): «+N» overflow fold, anchored popovers and hover cards that
//   80-structure (#tbstruct) and 74-timeline used to copy.
//   ⚠Each caller keeps its own quirks (fold order, what counts toward «+N», card placement) — these only run the shared part.
// Hide cands in order until box fits one line. opts.n = starting count, opts.count(e) = does e add to «+N»,
// opts.set(n) replaces the default «+N» text update on mb.
function ovfFold(box, cands, mb, opts){
  opts = opts || {};
  let n = opts.n || 0;
  const fits = () => box.scrollWidth <= box.clientWidth + 1;
  for(const e of cands){
    if(fits()) break;
    if(e.hidden) continue;
    e.hidden = true;
    if(!opts.count || opts.count(e)) n++;
    if(opts.set) opts.set(n); else mb.textContent = '+' + n;
  }
  return n;
}
// «+N» list popover: one .thpop element per id, created on first use (extra classes tweak the look per caller).
function popGet(id, cls){
  let p = document.getElementById(id);
  if(!p){ p = document.createElement('div'); p.id = id; p.className = cls; p.hidden = true; document.body.appendChild(p); }
  return p;
}
function popIsOpen(id){ const p = document.getElementById(id); return !!(p && !p.hidden); }
// Fixed under its button and clamped to the viewport, so the header's layout never moves.
//   o (optional): at = rect, or {x, y} point (unrounded, like mouse coords) instead of mb's rect · gap (4) · pad = edge margin (8)
//   side 'right' = beside the anchor, flipped left at the edge · align 'right' = right edges aligned · dy = extra top offset
//   flipY = go above when the bottom overflows (gapUp, default gap) · w = width when offsetWidth is 0.
function popAnchor(p, mb, o){
  o = o || {};
  p.hidden = false;
  const pt = o.at && o.at.right == null ? o.at : null;   // ⚠DOMRect has x/y too — test for a rect field
  const r = pt ? {left: pt.x, right: pt.x, top: pt.y, bottom: pt.y} : (o.at || mb.getBoundingClientRect());
  const gap = o.gap == null ? 4 : o.gap, pad = o.pad == null ? 8 : o.pad, w = p.offsetWidth || o.w || 0;
  let l, t;
  if(o.side === 'right'){
    l = r.right + gap; t = r.top + (o.dy || 0);
    if(l + w > innerWidth - pad) l = Math.max(pad, r.left - w - gap);
  } else {
    l = o.align === 'right' ? Math.round(r.right - w) : r.left;
    if(!pt) l = Math.min(l, innerWidth - w - pad);
    t = r.bottom + gap;
  }
  if(o.flipY){ const h = p.offsetHeight; if(t + h > innerHeight - pad) t = Math.max(pad, r.top - h - (o.gapUp == null ? gap : o.gapUp)); }
  if(!pt){ l = Math.round(Math.max(pad, l)); t = Math.round(t); }
  p.style.left = l + 'px'; p.style.top = t + 'px';
  if(mb) mb.setAttribute('aria-expanded', 'true');
  return t;
}
function popHide(id, mb, focusBack, fo){
  const p = document.getElementById(id);
  if(!p || p.hidden) return false;
  p.hidden = true;
  if(mb){ mb.setAttribute('aria-expanded', 'false'); if(focusBack) mb.focus(fo); }
  return true;
}
// One outside-click + one Esc listener for every registered popover; inside = selector whose clicks keep it open.
const UIPOPS = [];
function popReg(id, inside, close){ UIPOPS.push({ id, inside, close }); }
// ⚠Capture: a click that dismisses a popover over #feed is swallowed — it used to pin the timeline cursor / select a row.
//   Header and toolbar clicks still go through (tab switch in one click).
document.addEventListener('click', e => {
  let shut = false;
  for(const q of UIPOPS) if(popIsOpen(q.id) && !(e.target.closest && e.target.closest(q.inside))){ q.close(false); shut = true; }
  if(shut && e.target.closest && e.target.closest('#feed')){ e.stopPropagation(); e.preventDefault(); }
}, true);
// ⚠Capture + stopPropagation + preventDefault: Esc closes only the open list, not the sessions drawer or branch detail behind it.
document.addEventListener('keydown', e => {
  if(e.key !== 'Escape') return;
  for(const q of UIPOPS) if(popIsOpen(q.id)){ e.preventDefault(); e.stopPropagation(); q.close(true); }
}, true);
// Tab past the last (Shift+Tab before the first) control of an open popover closes it and returns focus to its opener.
//   ⚠Popovers live at the end of <body>, so the browser's next stop was the document start with the popover left open.
function popTabOut(e){
  if(e.key !== 'Tab' || e.altKey || e.ctrlKey || e.metaKey) return;
  const a = document.activeElement;
  for(const q of UIPOPS){
    const p = document.getElementById(q.id);
    if(!p || p.hidden) continue;
    const fs = [...p.querySelectorAll('a[href],button:not([disabled]),input:not([disabled]),select,textarea,[tabindex]:not([tabindex="-1"])')]
      .filter(x => x.offsetParent !== null);
    // ⚠A popover with nothing focusable (#tlqp) never holds focus ⇒ Tab off its opener closes it; focus moves on normally.
    if(!p.contains(a)){ if(!fs.length && a && a.closest && a.closest(q.inside)) q.close(false); continue; }
    const edge = !fs.length || (a === p ? e.shiftKey : a === (e.shiftKey ? fs[0] : fs[fs.length - 1]));
    if(edge){ e.preventDefault(); q.close(true); }
    return;
  }
}
document.addEventListener('keydown', popTabOut, true);
// Skip-if-same innerHTML for poll repaints; returns true when it wrote. Unchanged DOM keeps focus, hover and listeners.
// ⚠Compares to the last source string (el._sh), not el.innerHTML — the browser normalises the serialisation.
//   Anyone else writing el.innerHTML must clear el._sh, or the next same-string call is skipped wrongly.
function setHtml(el, h){
  if(!el || el._sh === h) return false;
  el._sh = h; el.innerHTML = h;
  return true;
}
// setHtml that patches the live DOM instead of replacing it: only changed text/attributes/nodes are written.
// ★The sessions list changes every poll only by its «Ns ago» text; innerHTML rebuilt every row, and the a11y observer
//   re-marked each new node (~48 tabindex/role/data-kb writes per 10s, measured 2026-09-26). Kept nodes stay marked.
// ⚠Attributes added by 98-a11y (tabindex/role/data-kb on [data-kb]) are kept when the new markup lacks them.
const MORPH_KEEP = {tabindex: 1, role: 1, 'data-kb': 1};
function morphKids(o, n){
  const ok = Array.from(o.childNodes), nk = Array.from(n.childNodes);
  for(let i = 0; i < nk.length; i++){
    const a = ok[i], b = nk[i];
    if(!a){ o.appendChild(b); continue; }
    if(a.nodeType !== b.nodeType || a.nodeName !== b.nodeName){ o.replaceChild(b, a); continue; }
    if(a.nodeType !== 1){ if(a.nodeValue !== b.nodeValue) a.nodeValue = b.nodeValue; continue; }
    for(const at of Array.from(b.attributes)) if(a.getAttribute(at.name) !== at.value) a.setAttribute(at.name, at.value);
    const kb = a.hasAttribute('data-kb');
    for(const at of Array.from(a.attributes))
      if(!b.hasAttribute(at.name) && !(kb && MORPH_KEEP[at.name])) a.removeAttribute(at.name);
    if(a.tagName === 'INPUT' && a.checked !== b.defaultChecked) a.checked = b.defaultChecked;
    morphKids(a, b);
  }
  for(let i = ok.length - 1; i >= nk.length; i--) o.removeChild(ok[i]);
}
function morphHtml(el, h){
  if(!el || el._sh === h) return false;
  if(el._sh == null){ el._sh = h; el.innerHTML = h; return true; }
  el._sh = h;
  const t = document.createElement('div'); t.innerHTML = h;
  morphKids(el, t);
  return true;
}
// ⚠A repaint drops focus to <body>, and the data load it starts repaints again later: for a short window, put focus back
// on the first matching selector while it sits on <body>; stops as soon as focus is somewhere else.
function kbHold(...sels){
  const end = performance.now() + 3000, sel = sels.join(', ');
  const step = () => {
    const a = document.activeElement;
    if(a && a !== document.body && !(a.matches && a.matches(sel))) return;
    if(!a || a === document.body){
      for(const s of sels){ const el = document.querySelector(s); if(el){ el.focus({preventScroll: true}); break; } }
    }
    if(performance.now() < end) requestAnimationFrame(step);
  };
  step();
}
// Hover card (.tlhc look, role=tooltip): created once per id, html rewritten only when it changed; the caller positions it.
function hcShow(id, html, cls){
  let c = document.getElementById(id);
  if(!c){ c = document.createElement('div'); c.id = id; c.className = cls; c.setAttribute('role', 'tooltip'); document.body.appendChild(c); }
  setHtml(c, html);
  c.hidden = false;
  return c;
}
function hcHide(id){ const c = document.getElementById(id); if(c) c.hidden = true; }
// GET JSON: no-store by default; a non-2xx answer throws (e.status) so callers' catch paths run instead of parsing an error body.
// ⚠opts.timeout (ms) aborts a hung request (AbortError, e.timeout = true): without it a stalled server kept one poll pending forever,
// pollBusy skipped every later tick and the bar stayed «Connected». Default sits above the slowest healthy call (timeline 90s, cold state 60s).
async function getJSON(url, opts){
  const o = Object.assign({ cache: 'no-store' }, opts || {});
  const ms = o.timeout == null ? 120000 : o.timeout; delete o.timeout;
  const ac = (ms > 0 && typeof AbortController === 'function') ? new AbortController() : null;
  let timedOut = false, to = 0;
  if(ac){
    const up = o.signal;   // caller's own abort still works
    if(up){ if(up.aborted) ac.abort(); else up.addEventListener('abort', () => ac.abort()); }
    o.signal = ac.signal;
    to = setTimeout(() => { timedOut = true; ac.abort(); }, ms);
  }
  try{
    const r = await fetch(url, o);
    if(!r.ok){ const e = new Error('HTTP ' + r.status); e.status = r.status; throw e; }
    return await r.json();
  }catch(e){ if(timedOut && e && typeof e === 'object') e.timeout = true; throw e; }
  finally{ clearTimeout(to); }
}
// POST JSON body: the server's 400s carry {error|err|msg} (403 refusals are text) — non-2xx throws with that message, e.status and e.body.
async function postJSON(url, body){
  // X-Sidereus-Lang: an unset viewer_me posts as the default name of this UI language (sidereus/config.py viewer_me_for)
  const h = { 'Content-Type': 'application/json', 'X-Sidereus-Lang': typeof LANG !== 'undefined' && LANG === 'en' ? 'en' : 'ko' };
  const r = await fetch(url, { method: 'POST', headers: h, body: JSON.stringify(body === undefined ? {} : body) });
  let j = null;
  try{ j = await r.json(); }catch(e){ if(r.ok) throw e; }
  if(!r.ok){ const e = new Error((j && (j.error || j.err || j.msg)) || ('HTTP ' + r.status)); e.status = r.status; e.body = j; throw e; }
  return j;
}
// Human-input heartbeat for the structure warm-up idle check; ⚠throttle must stay well under STRUCT_WARM_IDLE_S (30 s).
var ACT_SENT = 0;
function actPing(){
  const now = Date.now();
  if(now - ACT_SENT < 10000) return;
  ACT_SENT = now;
  postJSON('/api/act').catch(e => softErr('act', e));
}
if(typeof window !== 'undefined' && window.addEventListener)
  ['pointerdown', 'keydown', 'wheel'].forEach(t => window.addEventListener(t, actPing, { capture: true, passive: true }));
// Non-fatal render/poll failure: count per tag, console.warn once per tag, keep the UI running.
// ⚠var + function declaration on purpose — 00-core.js calls this at load, before this file's let/const exist.
var SOFT_ERRS = {};
function softErr(tag, e){
  if(!SOFT_ERRS) SOFT_ERRS = {};   // ⚠00-core calls softErr at load, before line 141 runs
  const s = SOFT_ERRS[tag] || (SOFT_ERRS[tag] = { n: 0, msg: '', at: 0 });
  s.n++; s.at = Date.now(); s.msg = String((e && e.message) || e);
  if(s.n === 1) try{ console.warn('[softErr] ' + tag + ':', e); }catch(x){}
}
// UI-pref wrappers over UIS (app-head.js, server-backed): a throwing store → default, counted under softErr('ls').
// ⚠lsGet returns def (not null) for a missing key; lsJson also returns def for a stored null/empty value.
function lsGet(key, def){ try{ const v = UIS.getItem(key); return v === null ? def : v; }catch(e){ softErr('ls', e); return def; } }
function lsSet(key, val){ try{ UIS.setItem(key, val); return true; }catch(e){ softErr('ls', e); return false; } }
function lsDel(key){ try{ UIS.removeItem(key); return true; }catch(e){ softErr('ls', e); return false; } }
function lsJson(key, def){ try{ const v = JSON.parse(UIS.getItem(key) || 'null'); return v === null ? def : v; }catch(e){ softErr('ls', e); return def; } }
function lsSetJson(key, obj){ try{ UIS.setItem(key, JSON.stringify(obj)); return true; }catch(e){ softErr('ls', e); return false; } }
// Shared drag lifecycle for resize grips: capture on cap, onMove(ev) per move, onEnd(ev) once on up / cancel / buttonless move.
// ⚠release outside the window may never send pointerup — a move with ev.buttons === 0 ends the drag. root = listener target (default document).
function dragTrack(e, cap, onMove, onEnd, root){
  const R = root || document;
  let done = false;
  try{ if(cap) cap.setPointerCapture(e.pointerId); }catch(err){ softErr('dragCap', err); }
  const move = ev => { if(!ev.buttons) return end(ev); onMove(ev); };
  const end = ev => {
    if(done) return;
    done = true;
    R.removeEventListener('pointermove', move);
    R.removeEventListener('pointerup', end);
    R.removeEventListener('pointercancel', end);
    if(onEnd) onEnd(ev);
  };
  R.addEventListener('pointermove', move);
  R.addEventListener('pointerup', end);
  R.addEventListener('pointercancel', end);
  return end;
}
// Per-tab view state (unique per browser tab, kept across reloads): sessionStorage = this tab, survives its
//   refresh · UIS = where a brand-new tab starts. Reads prefer the tab's own value; writes go to both.
// ⚠Only for "where am I looking" keys (main tab, place/filter, structure project/scope/mode, branch repo, settings category…);
//   preferences (tone, language, sizes) stay shared. ⚠Function declarations only: 05-i18n reads mbMainView before this file runs.
function tabRead(ss, ls, key){
  for(const s of [ss, ls]){ try{ const v = s ? s.getItem(key) : null; if(v !== null && v !== undefined) return v; }catch(e){ softErr('ls', e); } }
  return null;
}
function tabWrite(ss, ls, key, val){
  let n = 0;
  for(const s of [ss, ls]){ try{ if(s){ if(val === null) s.removeItem(key); else s.setItem(key, val); n++; } }catch(e){ softErr('ls', e); } }
  return n;
}
function tabStores(){
  let ss = null, ls = null;   // ⚠the getters themselves throw when storage is blocked
  try{ ss = typeof sessionStorage === 'undefined' ? null : sessionStorage; }catch(e){ softErr('ls', e); }
  try{ ls = typeof UIS === 'undefined' ? null : UIS; }catch(e){ softErr('ls', e); }
  return [ss, ls];
}
function tabOwn(key){ const t = tabStores(); return tabRead(t[0], null, key); }
function tabGet(key, def){ const t = tabStores(), v = tabRead(t[0], t[1], key); return v === null ? def : v; }
function tabSet(key, val){ const t = tabStores(); return tabWrite(t[0], t[1], key, String(val)) > 0; }
function tabDel(key){ const t = tabStores(); return tabWrite(t[0], t[1], key, null) > 0; }
function tabJson(key, def){ try{ const v = JSON.parse(tabGet(key, null) || 'null'); return v === null ? def : v; }catch(e){ softErr('ls', e); return def; } }
function tabSetJson(key, obj){ return tabSet(key, JSON.stringify(obj)); }
