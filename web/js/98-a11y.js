// Keyboard reach for click targets that are not native controls (HANDOVER 2026-09-23 §7-5).
//   Targets = elements matched by any stylesheet rule with cursor:pointer, so ~60 handlers need no per-site edits.
//   ⚠cursor:pointer is the contract: a clickable div without it stays out of the tab order.
const A11Y_NATIVE = /^(A|BUTTON|INPUT|SELECT|TEXTAREA|SUMMARY|LABEL|OPTION|DETAILS)$/;
function a11yBuildSel(){
  const out = new Set();
  const walk = rs => { for(const r of rs){
    if(!r.selectorText){ if(r.cssRules) walk(r.cssRules); continue; }   // @media / @supports groups
    if(!r.style || r.style.cursor !== 'pointer') continue;
    const s = r.selectorText.replace(/:(hover|focus-visible|focus|active)\b/g, '');
    try{ document.querySelector(s); out.add(s); }catch(e){}            // skips ::before etc.
  } };
  for(const sh of document.styleSheets){ try{ walk(sh.cssRules); }catch(e){} }
  return out.size ? [...out].join(',') : '';
}
const A11Y_SEL = a11yBuildSel();
function a11yOne(el){
  // ⚠Skip elements that already manage focus (own tabindex + keydown, e.g. .wpk, .sbar) — marking them double-fires.
  if(A11Y_NATIVE.test(el.tagName) || el.hasAttribute('tabindex') || el.closest('a,button,summary,label')) return;
  if(getComputedStyle(el).cursor !== 'pointer') return;               // e.g. read failure cards override to default
  // ⚠Timeline bars are not tab stops (up to 50 per row hid everything after #feed); arrows reach them (74b tlRoveTarget).
  el.tabIndex = el.matches('#feed .tlr .tlb') ? -1 : 0; el.setAttribute('data-kb', '');
  if(!el.hasAttribute('role')) el.setAttribute('role', 'button');
}
function a11yMark(root){
  if(!A11Y_SEL || !root || root.nodeType !== 1 || !document.contains(root)) return;
  if(root.matches(A11Y_SEL)) a11yOne(root);
  root.querySelectorAll(A11Y_SEL).forEach(a11yOne);
}
// Renders replace innerHTML every poll, so newly added subtrees are marked once per frame.
let a11yQ = [], a11yRaf = 0;
new MutationObserver(ms => {
  ms.forEach(m => m.addedNodes.forEach(n => { if(n.nodeType === 1) a11yQ.push(n); }));
  if(!a11yRaf && a11yQ.length) a11yRaf = requestAnimationFrame(() => {
    const q = a11yQ; a11yQ = []; a11yRaf = 0; q.forEach(a11yMark); a11yRestore();
  });
}).observe(document.body, {childList: true, subtree: true});
a11yMark(document.body);
// One delegated activator: Enter/Space on a marked element = click (handlers read e.target/closest, so click() fits).
document.addEventListener('keydown', e => {
  if((e.key !== 'Enter' && e.key !== ' ') || e.defaultPrevented || e.isComposing || e.repeat) return;
  const t = e.target;
  if(!t || !t.hasAttribute || !t.hasAttribute('data-kb')) return;
  e.preventDefault(); t.click();
});
// Re-renders (the click's own and every 2.5s poll) swap the focused node out, dropping focus to <body>.
//   ⚠Refocusing only right after click() is not enough — the next poll dropped it again (measured 2026-09-23).
//   So track the focused [data-kb] by a stable identity and restore it after each observer pass.
//   Identity = id, else tag + first class + data-* (state classes like .on toggle) and its index.
function a11yKey(el){
  if(el.id) return {sel: '#' + CSS.escape(el.id), i: 0};
  let sel = el.tagName.toLowerCase() + (el.classList[0] ? '.' + CSS.escape(el.classList[0]) : '');
  for(const a of el.attributes) if(a.name.startsWith('data-') && a.name !== 'data-kb')
    sel += '[' + a.name + '="' + CSS.escape(a.value) + '"]';
  return {sel, i: [...document.querySelectorAll(sel)].indexOf(el)};
}
let a11yLast = null;
document.addEventListener('focusin', e => {
  const t = e.target; a11yLast = t && t.hasAttribute && t.hasAttribute('data-kb') ? a11yKey(t) : null; });
document.addEventListener('pointerdown', () => { a11yLast = null; }, true);   // a mouse user moved on — do not pull focus back
function a11yRestore(){
  const ae = document.activeElement;
  if(!a11yLast || (ae && ae !== document.body && document.contains(ae))) return;
  let el = null; try{ el = document.querySelectorAll(a11yLast.sel)[Math.max(a11yLast.i, 0)]; }catch(e){}
  if(!el) return;
  a11yOne(el);                                     // in case this pass skipped it
  if(el.hasAttribute('data-kb')) el.focus({preventScroll: true});
}
// ★2026-09-28 UX audit: global shortcuts — 1–N tabs (current order) · / search box of this tab · s sessions · ? help.
//   ⚠Ignored while typing (input/textarea/select/contenteditable), during IME composition and with Cmd/Ctrl/Alt.
//   ⚠'1–N' is filled in at open time from the visible tab count — a fixed '1–7' went stale when an 8th tab was added.
//   ⌘K is listed although it is handled in 40-sessions.js (the session palette).
const KB_KEYS = [['1–N', 'Switch tabs (in the order shown)'], ['/', "Focus this tab's search box"], ['s', 'Open/close the sessions panel'],
                 ['⌘K / Ctrl+K', 'Find and jump to a session'], ['⌘B / Ctrl+B', 'Expand/collapse the sidebar'], ['?', 'Shortcut help'], ['Esc', 'Close']];
function kbKeyLab(k){
  return k === '1–N' ? '1–' + Math.max(1, Math.min(9, document.querySelectorAll('#mvw .mvb').length)) : k;
}
function kbTyping(t){
  return !!(t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName || '')));
}
function kbSearchBox(){
  const vis = el => el && el.offsetParent !== null && !el.disabled;
  return [...document.querySelectorAll('#tbar > .tbs:not([hidden]) input[type=search], #feed input[type=search]')].find(vis) || null;
}
function kbHelpClose(focusBack){ popHide('kbhelp', null, false); if(focusBack && kbHelpFrom && kbHelpFrom.isConnected) kbHelpFrom.focus(); kbHelpFrom = null; }
let kbHelpFrom = null;
function kbHelpOpen(){
  let p = document.getElementById('kbhelp');
  if(!p){ p = document.createElement('div'); p.id = 'kbhelp'; p.className = 'kbhelp'; p.setAttribute('role', 'dialog'); p.tabIndex = -1; document.body.appendChild(p); }
  p.setAttribute('aria-label', T('Shortcuts'));
  p.innerHTML = '<div class=kbhh>'+esc(T('Shortcuts'))+'<button class=kbhx aria-label="'+esc(T('Close'))+'" title="'+esc(T('Close'))+'">✕</button></div>'
    + '<dl>' + KB_KEYS.map(k => '<dt><kbd>'+esc(kbKeyLab(k[0]))+'</kbd></dt><dd>'+esc(T(k[1]))+'</dd>').join('') + '</dl>'
    + '<div class=kbhn>'+esc(T('Inactive while typing or with Cmd/Ctrl/Alt held.'))+'</div>'
    + '<button class=kbhtour>'+esc(T('Replay the tour'))+'</button>';
  p.querySelector('.kbhx').onclick = () => kbHelpClose(true);
  p.querySelector('.kbhtour').onclick = () => { kbHelpClose(false); tourOpen(0); };   // 98b-tour.js
  kbHelpFrom = document.activeElement;
  p.hidden = false; p.focus();
}
popReg('kbhelp', '#kbhelp', kbHelpClose);
// ⚠With the Korean IME on, `s` arrives as that key's Hangul jamo (or 'Process') — fall back to the physical key when e.key is not ASCII.
function kbKey(e){
  const k = e.key || '';
  if(/^[\x20-\x7e]$/.test(k)) return k;
  const c = e.code || '';
  if(c === 'KeyS') return e.shiftKey ? 'S' : 's';
  if(c === 'Slash') return e.shiftKey ? '?' : '/';
  const d = /^Digit([1-9])$/.exec(c);
  return d ? d[1] : k;
}
document.addEventListener('keydown', e => {
  if(e.defaultPrevented || e.isComposing || e.metaKey || e.ctrlKey || e.altKey || kbTyping(e.target)) return;
  if(ISPOP || ISWP || ISBP || wkOn || tourIsOpen()) return;   // popup windows / work-log modal / tour (98b) own the keyboard
  const cm = document.getElementById('cfgm'); if(cm && !cm.hidden) return;
  const k = kbKey(e);
  if(k === '?'){ e.preventDefault(); if(popIsOpen('kbhelp')) kbHelpClose(true); else kbHelpOpen(); return; }
  if(e.repeat) return;
  if(/^[1-9]$/.test(k)){
    if(popIsOpen('kbhelp')) return;                  // help is on top — digits must not switch the tab behind it
    const b = document.querySelectorAll('#mvw .mvb')[+k - 1];
    if(b){ e.preventDefault(); setMainView(b.dataset.mv); }
    return;
  }
  if(k === '/'){ const q = kbSearchBox(); if(q){ e.preventDefault(); q.focus(); q.select(); } return; }
  if(k === 's' || k === 'S'){ const b = document.getElementById('sesb'); if(b && b.offsetParent !== null){ e.preventDefault(); b.click(); } }
});
