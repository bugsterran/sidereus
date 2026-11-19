// Shared confirm: uiConfirm(title, {body, ok, danger}) -> Promise<boolean>, one native <dialog> opened with showModal().
//   title/body are set with textContent only — bodies carry paths and setting values (user data).
//   ok is a label the caller already passed through T(); defaults are T('Confirm') / T('Cancel').
// Open state: {res, d, opener, sels}; null while closed.
let UCF = null;
function ucfEl(){
  let d = document.getElementById('ucf');
  if(d) return d;
  d = document.createElement('dialog'); d.id = 'ucf'; d.className = 'ucf';
  d.setAttribute('role', 'alertdialog'); d.setAttribute('aria-labelledby', 'ucft'); d.setAttribute('aria-describedby', 'ucfb');
  const t = document.createElement('div'); t.id = 'ucft'; t.className = 'ucft';
  const b = document.createElement('div'); b.id = 'ucfb'; b.className = 'ucfb';
  const a = document.createElement('div'); a.className = 'ucfa';
  const no = document.createElement('button'); no.type = 'button'; no.className = 'wkrgb'; no.setAttribute('data-ucf', '0');
  const ok = document.createElement('button'); ok.type = 'button'; ok.className = 'wkrgb archok'; ok.setAttribute('data-ucf', '1');
  a.appendChild(no); a.appendChild(ok); d.appendChild(t); d.appendChild(b); d.appendChild(a);
  d.addEventListener('cancel', e => { e.preventDefault(); ucfDone(false); });   // native Esc path (close watcher)
  // ⚠Appended to <body>, never inside #cfgm: paintCfg rewrites #cfgbox while the dialog is open.
  document.body.appendChild(d);
  return d;
}
function uiConfirm(title, o){
  o = o || {};
  if(UCF){ softErr('ucf-busy', 'uiConfirm while another is open'); return Promise.resolve(false); }   // never stack: the first answer would be lost
  const d = ucfEl(), bs = d.querySelectorAll('[data-ucf]'), body = d.querySelector('.ucfb');
  d.querySelector('.ucft').textContent = String(title == null ? '' : title);
  body.textContent = o.body == null ? '' : String(o.body); body.hidden = !body.textContent;
  bs[0].textContent = T('Cancel');
  bs[1].textContent = o.ok == null ? T('Confirm') : String(o.ok);
  bs[1].classList.toggle('dng', !!o.danger);
  const opener = document.activeElement && document.activeElement !== document.body ? document.activeElement : null;
  // ⚠cfgBind repaints #cfgbox while the dialog is open and detaches the opener: keep selectors to re-find its twin.
  const sels = opener && typeof cfgFocusSel === 'function' ? cfgFocusSel(opener) : [];
  return new Promise(res => {
    UCF = {res, d, opener, sels};
    try{ d.showModal(); }
    catch(e){ softErr('ucf', e); UCF = null; res(false); return; }   // a failed open is «Cancel»: nothing is written or sent
    // An overflowing body (long settings diff at 900 wide) joins the Tab cycle so arrows/PageDown can scroll it; measured after showModal (laid out).
    if(!body.hidden && body.scrollHeight > body.clientHeight + 1) body.setAttribute('tabindex', '0'); else body.removeAttribute('tabindex');
    bs[0].focus();   // the safe answer gets initial focus
  });
}
// Close first (lifts inert so focus can move), refocus the opener, then resolve — callers repaint after the await.
function ucfDone(v){
  const st = UCF;
  if(!st) return;
  UCF = null;
  if(st.d.open) st.d.close();
  let f = st.opener;
  if(f && !f.isConnected){
    f = null;
    for(const s of st.sels){ const n = document.querySelector(s + ':not([disabled])'); if(n){ f = n; break; } }
  }
  if(f && f.focus) try{ f.focus({preventScroll: true}); }catch(e){ softErr('ucf', e); }
  st.res(!!v);
}
// ⚠Window capture runs before the document capture handlers (08-ui-kit popover Esc/outside click, 41 drawer pointerdown,
//   42 hover Esc, 48e Esc) — without this they would close panels behind the dialog on a click or Esc inside it.
function ucfKey(e){
  if(!UCF) return;
  if(e.key === 'Escape'){ e.preventDefault(); e.stopImmediatePropagation(); ucfDone(false); return; }
  e.stopPropagation();   // Enter/Space/arrows/PageDown keep their default: activate the button or scroll the body
  if(e.key !== 'Tab') return;
  e.preventDefault();
  // Cycle order: scrollable body (only when it overflows), «Cancel», ok.
  const bs = [UCF.d.querySelector('.ucfb[tabindex]')].filter(Boolean).concat(Array.from(UCF.d.querySelectorAll('[data-ucf]')));
  const i = bs.indexOf(document.activeElement), c = bs.length - 2;
  const n = i < 0 ? c : (i + (e.shiftKey ? bs.length - 1 : 1)) % bs.length;   // focus outside (BODY) -> «Cancel»
  bs[n].focus();
}
function ucfPtr(e){
  if(!UCF) return;
  e.stopPropagation();
  if(e.type !== 'click') return;
  const b = e.target && e.target.closest ? e.target.closest('#ucf [data-ucf]') : null;   // backdrop click: target is the dialog -> nothing
  if(b) ucfDone(b.getAttribute('data-ucf') === '1');
}
if(typeof window !== 'undefined' && window.addEventListener){
  window.addEventListener('keydown', ucfKey, true);
  ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click', 'auxclick'].forEach(t => window.addEventListener(t, ucfPtr, true));
}
