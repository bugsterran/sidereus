// Split panes are resizable by default -> drag the graph | .brpan border.
// Width lives in --brpw on <html> + class brpsz (CSS 80-branch.css); unset = today's flex widths, so nothing moves until dragged.
// ⚠No grip element: #brpan is rebuilt on every paint, so the hit zone is computed from its rect (left edge ±8px).
const BRP_KEY = 'sidereus.brpan', BRP_MIN = 300, BRP_MAX = 900, BRP_GRAPH_MIN = 400;
function brpPref(){ const v = +lsGet(BRP_KEY, 0) || 0; return v >= BRP_MIN ? v : 0; }
// Pane and graph side by side right now? (narrow layouts wrap the pane below — no resize there)
function brpGeo(){
  if(typeof mainView === 'undefined' || mainView !== 'br') return null;
  const p = document.getElementById('brpan'), g = document.querySelector('#feed .brgw'), b = p && p.parentElement;
  if(!p || !g || !b || !p.offsetWidth) return null;
  const pr = p.getBoundingClientRect(), gr = g.getBoundingClientRect();
  return gr.right <= pr.left + 1 ? { p: pr, b: b.getBoundingClientRect() } : null;
}
function brpClamp(w, geo){
  const max = geo ? Math.min(BRP_MAX, geo.b.right - geo.b.left - 12 - BRP_GRAPH_MIN) : BRP_MAX;
  return Math.round(Math.max(BRP_MIN, Math.min(max, w)));
}
function brpApply(w){
  const h = document.documentElement;
  if(w){ h.style.setProperty('--brpw', w + 'px'); h.classList.add('brpsz'); }
  else { h.style.removeProperty('--brpw'); h.classList.remove('brpsz'); }
  if(typeof brFitSoon === 'function') brFitSoon();
}
function brpHit(e){
  const g = brpGeo();
  return g && e.clientX >= g.p.left - 8 && e.clientX <= g.p.left + 6 && e.clientY >= g.p.top && e.clientY <= g.p.bottom ? g : null;
}
document.addEventListener('pointermove', e => {
  if(e.buttons) return;
  const on = !!brpHit(e), h = document.documentElement;
  if(on !== h.classList.contains('brpgr')) h.classList.toggle('brpgr', on);
});
document.addEventListener('pointerdown', e => {
  if(e.button !== 0) return;
  const geo = brpHit(e);
  if(!geo) return;
  e.preventDefault();
  document.body.classList.add('dragging');
  const right = geo.p.right;
  let w = 0;
  // ⚠capture on #feed, not the pane: a poll repaint replaces #brpan mid-drag
  dragTrack(e, document.getElementById('feed'), ev => {
    w = brpClamp(right - ev.clientX, brpGeo() || geo);
    brpApply(w);
  }, () => {
    document.body.classList.remove('dragging');
    if(w) lsSet(BRP_KEY, w);
  });
}, true);
document.addEventListener('dblclick', e => {
  if(!brpHit(e)) return;
  lsDel(BRP_KEY);
  brpApply(0);
});
// Smaller windows need no re-fit: the CSS max-width keeps the graph >= 400px without touching the stored width.
(() => { const w = brpPref(); if(w) brpApply(w); })();
