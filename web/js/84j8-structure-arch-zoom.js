// ── Structure «Architecture» zoom buttons (− 100% + Fit) in the map's .mmdbar; same 0.5–3x range as the 81e Ctrl/⌘+wheel zoom ──
// ⚠Scope every selector to .archdg .mmdv > svg.mmdsvg: the .archmm minimap clone carries class mmdsvg too.
const ARCH_ZM = { z: {} };   // z: view key (84j7 archMmVk) -> zoom factor, re-applied after each innerHTML repaint
const ARCH_ZM_MIN = 0.5, ARCH_ZM_MAX = 3;   // ⚠must match the 81e wheel clamp (tests/test_struct_arch_zoom_js.py)
// Pure: one button step (x/÷1.25), clamped.
function archZmStep(z, d){ return Math.max(ARCH_ZM_MIN, Math.min(ARCH_ZM_MAX, (+z || 1) * Math.pow(1.25, d > 0 ? 1 : -1))); }
// Pure: zoom that fits a viewBox width into the pane width, clamped (never below 0.5x).
function archZmFit(paneW, vbW){ return Math.max(ARCH_ZM_MIN, Math.min(ARCH_ZM_MAX, vbW > 0 && paneW > 0 ? paneW / vbW : 1)); }
// Pure: the button group 84j archMmd puts before «Source text»; the 100% label is a number, not a T() string.
function archZmBar(){
  const b = (a, t, l, c) => '<button type=button class="archzm-b' + (c ? ' ' + c : '') + '" data-arz="' + a + '" title="' + esc(T(t)) + '" aria-label="' + esc(T(t)) + '">' + l + '</button>';
  return '<span class=archzm>' + b('-1', 'Zoom out', '&minus;') + b('0', 'Reset to 100%', '100%', 'archzm-pct') + b('1', 'Zoom in', '+') + b('fit', 'Fit to width', esc(T('Fit'))) + '</span>';
}
function archZmSvg(root){ return root && root.querySelector ? root.querySelector('.archdg .mmdv > svg.mmdsvg') : null; }
function archZmLabel(root, z){ const b = root && root.querySelector ? root.querySelector('.archdg .archzm-pct') : null; if(b) b.textContent = Math.round(z * 100) + '%'; }
function archZmKeep(slot, z){
  const vk = typeof archMmVk === 'function' ? archMmVk(slot && slot.dataset && slot.dataset.k) : '';
  if(!vk) return;
  if(!(vk in ARCH_ZM.z) && Object.keys(ARCH_ZM.z).length >= 100) ARCH_ZM.z = {};
  ARCH_ZM.z[vk] = z;
}
// Size from the viewBox exactly as the 81e wheel handler (natural size x z).
function archZmSize(s, z){
  const vb = (s.getAttribute('viewBox') || '').split(' ').map(Number);
  s.dataset.z = String(z);
  s.setAttribute('width', String(Math.round(vb[2] * z))); s.setAttribute('height', String(Math.round(vb[3] * z)));
}
// Zoom the visible map to z, keeping the map point under the viewport centre (below the sticky .archtop) in place. No auto-centre.
function archZmSet(am, z){
  const s = archZmSvg(am), slot = am && am.querySelector ? am.querySelector('.archdg') : null;
  if(!s || !slot) return;
  z = Math.max(ARCH_ZM_MIN, Math.min(ARCH_ZM_MAX, +z || 1));
  const v0 = archMmVM(am, s), t = v0.view.top || 0, vh = Math.max(0, v0.view.ch - t);
  const fx = v0.map.w > 0 ? (v0.view.sl + v0.view.cw / 2 - v0.map.x) / v0.map.w : 0, fy = v0.map.h > 0 ? (v0.view.st + t + vh / 2 - v0.map.y) / v0.map.h : 0;
  archZmSize(s, z);
  const v1 = archMmVM(am, s);
  am.scrollLeft = Math.max(0, Math.round(v1.map.x + fx * v1.map.w - v1.view.cw / 2));
  am.scrollTop = Math.max(0, Math.round(v1.map.y + fy * v1.map.h - t - vh / 2));
  archZmKeep(slot, z);
  if(typeof archMmKeep === 'function') archMmKeep(am);
  if(typeof archMmView === 'function') archMmView(am);
  if(typeof archOffMark === 'function') archOffMark(slot);
  archZmLabel(slot, z);
}
// Re-apply the stored zoom after a repaint (the cached svg string is 1x); no scroll change — archScrollPut runs after this.
function archZmApply(slot){
  const s = archZmSvg(slot);   // ⚠element.querySelector matches the full selector in document context, so .archdg may be slot itself
  const vk = typeof archMmVk === 'function' ? archMmVk(slot && slot.dataset && slot.dataset.k) : '', z = vk ? ARCH_ZM.z[vk] : 0;
  if(!s || !z) return;
  archZmSize(s, z);
  archZmLabel(slot, z);
}
document.addEventListener('click', ev => {
  const b = ev.target && ev.target.closest ? ev.target.closest('.archdg [data-arz]') : null, am = b && b.closest('.archmap');
  if(!am) return;
  const s = archZmSvg(am), a = b.dataset.arz;
  if(!s) return;
  const z = +s.dataset.z || 1, vb = (s.getAttribute('viewBox') || '').split(' ').map(Number);
  const slot = am.querySelector('.archdg'), pane = (slot || am).clientWidth - 18;   // ⚠not .mmdv: it grows with a wide svg (79 .archdg .mmd max-content) · .mmd border 1px x2 + .mmdv padding 8px x2
  archZmSet(am, a === 'fit' ? archZmFit(pane, vb[2]) : a === '0' ? 1 : archZmStep(z, +a));
});
// Ctrl/⌘+wheel: 81e (registered earlier) already resized the svg; record the factor and refresh the label.
document.addEventListener('wheel', ev => {
  if(!(ev.ctrlKey || ev.metaKey)) return;
  const v = ev.target && ev.target.closest ? ev.target.closest('.archdg .mmdv') : null, s = v && v.querySelector(':scope > svg.mmdsvg'), slot = v && v.closest('.archdg');
  if(!s || !slot) return;
  const z = +s.dataset.z || 1;
  archZmKeep(slot, z); archZmLabel(slot, z);
  const am = slot.closest('.archmap'); if(am && typeof archMmView === 'function') archMmView(am);   // minimap rect follows the new size
}, { passive: true });
