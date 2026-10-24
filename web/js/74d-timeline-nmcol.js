// Timeline name column: one drag grip in the axis row sets `--tlnm-w` on #feed (every `.tlnm` reads it), pref `sidereus.tlnmW`;
// pipeline steppers in the cell are name-less segment bars that shrink with it (21-timeline-plrun.css), so no fit pass is needed.
const TLNM_MIN = 220;
let tlNmW = (() => { const v = +lsGet('sidereus.tlnmW', 0) || 0; return v >= TLNM_MIN ? v : 0; })();   // 0 = CSS default clamp
// Width -> px within [220, half the timeline column]. ⚠Half of the Gantt column, not of #feed: with the git rail open half of #feed left ~150px of track.
function tlNmWClamp(w, colW){
  const max = Math.max(TLNM_MIN, (colW || 0) / 2);
  return Math.round(Math.max(TLNM_MIN, Math.min(max, +w || 0)));
}
function tlNmApply(){
  const f = document.getElementById('feed'), ax = f && f.querySelector('.tlaxr');
  if(!f) return;
  if(tlNmW && ax) f.style.setProperty('--tlnm-w', tlNmWClamp(tlNmW, ax.clientWidth) + 'px');
  else f.style.removeProperty('--tlnm-w');
}
let tlNmRO2 = null;
// Called after every paint (tlPlWire): re-adds the grip (paintTl rewrites the axis row) and applies the width.
function tlNmColWire(box){
  const c = box.querySelector('.tlaxr > .tlnm'), wr = box.querySelector('.tlwrap');
  const tip = esc(T('Drag to resize the name column · double-click for default'));
  if(c && !c.querySelector('.tlnmg')) c.insertAdjacentHTML('beforeend', '<div class=tlnmg id=tlnmg role=separator aria-orientation=vertical title="' + tip + '"></div>');
  // Full-height twin on .tlwrap so the boundary drags from any row (same handlers via the .tlnmg class).
  if(wr && !wr.querySelector('.tlnmgl')) wr.insertAdjacentHTML('beforeend', '<div class="tlnmg tlnmgl" id=tlnmgl role=separator aria-orientation=vertical title="' + tip + '"></div>');
  tlNmApply();
  if(tlNmRO2){ tlNmRO2.disconnect(); tlNmRO2 = null; }
  // Axis row = viewport / git-rail resize (re-clamp the saved width). Converges: same width, no new callback.
  if(c && window.ResizeObserver){ tlNmRO2 = new ResizeObserver(() => tlNmApply()); tlNmRO2.observe(c.parentNode); }
}
// ⚠preventDefault on pointerdown: no text selection and no scroll; the grip resolves the axis cell per move, so a paintTl mid-drag is harmless.
document.addEventListener('pointerdown', e => {
  const g = e.target.closest && e.target.closest('.tlnmg');
  if(!g || e.button !== 0) return;
  e.preventDefault(); e.stopPropagation();
  document.documentElement.classList.add('tlnmdrag');
  dragTrack(e, g, ev => {
    const ax = document.querySelector('#feed .tlaxr'), c = ax && ax.querySelector('.tlnm');
    if(!c) return;
    tlNmW = tlNmWClamp(ev.clientX - c.getBoundingClientRect().left, ax.clientWidth);
    tlNmApply();
  }, () => {
    document.documentElement.classList.remove('tlnmdrag');
    if(tlNmW) lsSet('sidereus.tlnmW', String(tlNmW));
  });
});
document.addEventListener('dblclick', e => {
  if(!(e.target.closest && e.target.closest('.tlnmg'))) return;
  e.stopPropagation();
  tlNmW = 0;
  lsDel('sidereus.tlnmW');
  tlNmApply();
});
