/* Structure «Architecture» focus layer (84j3 archLyHtml, role=dialog aria-modal): focus and Tab handling. Split from 84j (size cap). */
// Modal layer focus: after a repaint drops focus to <body>, move it to the close button; Tab / Shift-Tab cycle inside the layer.
// ⚠Focus outside the layer (the ≤1060px detail popover, the header) is left alone: a repaint must not pull it back.
function archLyFocus(box){
  const a = document.activeElement, ly = box && box.querySelector ? box.querySelector('.archly') : null;
  if(!ly || (a && a !== document.body && a !== document.documentElement)) return;
  const x = ly.querySelector('.archlyx');
  if(x) try{ x.focus({ preventScroll: true }); }catch(er){ softErr('arch-ly-focus', er); }
}
function archLyTab(e){
  if(e.key !== 'Tab' || e.altKey || e.ctrlKey || e.metaKey) return;
  const ly = document.querySelector('.archtab .archly'), a = document.activeElement;
  if(!ly || !a || !ly.contains(a)) return;
  const f = Array.from(ly.querySelectorAll('button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])')).filter(n => !n.disabled && n.offsetParent !== null);
  if(!f.length) return;
  const i = f.indexOf(a), n = e.shiftKey ? (i <= 0 ? f.length - 1 : i - 1) : (i < 0 || i >= f.length - 1 ? 0 : i + 1);
  e.preventDefault(); f[n].focus();
}
document.addEventListener('keydown', archLyTab);
