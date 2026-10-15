// Split panes are resizable by default -> drag grips on the .wrap column borders.
// Widths live in CSS vars --wrl (participants) / --wrr (pinned sessions) on <html>; unset = the CSS defaults, so nothing moves until dragged.
// ⚠Grips are position:fixed (not children laid out in .wrap): making .wrap positioned would re-anchor absolute descendants.
// ⚠#composein reads the same vars — the input stays aligned with the feed (45-saver-quota.css · 65-code-compose-alarm.css).
const WR_SIDES = {
  l: { key: 'sidereus.wrapl', v: '--wrl', min: 260, max: 600, col: () => document.querySelector('.wrap > .pside') },
  r: { key: 'sidereus.wrapr', v: '--wrr', min: 320, max: 900, col: () => document.querySelector('.wrap > .lside') },
};
const WR_FEED_MIN = 400;
function wrPref(s){ const v = +lsGet(WR_SIDES[s].key, 0) || 0; return v >= WR_SIDES[s].min ? v : 0; }
// Is this side a real grid column next to the feed right now? (hidden · folded above the feed · drawer = no)
function wrCol(s){
  const c = WR_SIDES[s].col(), m = document.getElementById('feed');
  if(!c || !m || !m.offsetWidth || !c.offsetWidth || getComputedStyle(c).position === 'fixed') return null;
  const cr = c.getBoundingClientRect(), mr = m.getBoundingClientRect();
  return (s === 'l' ? cr.right <= mr.left + 1 : cr.left >= mr.right - 1) ? { c: cr, m: mr } : null;
}
function wrClamp(s, w){
  const d = WR_SIDES[s], g = wrCol(s);
  const max = g ? Math.min(d.max, g.m.width + g.c.width - WR_FEED_MIN) : d.max;
  return Math.round(Math.max(d.min, Math.min(max, w)));
}
function wrApply(s, w){
  if(w) document.documentElement.style.setProperty(WR_SIDES[s].v, w + 'px');
  else document.documentElement.style.removeProperty(WR_SIDES[s].v);
}
function wrGrip(s){
  let g = document.getElementById('wrg' + s);
  if(!g){
    g = document.createElement('div');
    g.id = 'wrg' + s; g.className = 'wrg'; g.dataset.s = s; g.hidden = true;
    g.title = T('Drag to resize · double-click for default');
    document.body.appendChild(g);
  }
  return g;
}
// Sit each grip in the 8px grid gap between its column and the feed.
function wrPlace(){
  ['l', 'r'].forEach(s => {
    const g = wrGrip(s), p = wrCol(s);
    g.hidden = !p;
    if(!p) return;
    const x0 = s === 'l' ? p.c.right : p.m.right, x1 = s === 'l' ? p.m.left : p.c.left;
    g.style.left = Math.round(x0) + 'px';
    g.style.width = Math.max(6, Math.round(x1 - x0)) + 'px';
    g.style.top = Math.round(p.m.top) + 'px';
    g.style.height = Math.round(p.m.height) + 'px';
  });
}
// Re-fit stored widths to the current window (the stored preference itself is kept).
function wrFit(){
  ['l', 'r'].forEach(s => { const w = wrPref(s); if(w) wrApply(s, wrClamp(s, w)); });
  wrPlace();
}
document.addEventListener('pointerdown', e => {
  const g = e.target.closest && e.target.closest('.wrg');
  if(!g || e.button !== 0) return;
  const s = g.dataset.s;
  e.preventDefault();
  g.classList.add('on');
  document.body.classList.add('dragging');
  let w = 0;
  dragTrack(e, g, ev => {
    const c = WR_SIDES[s].col();
    if(!c) return;
    const r = c.getBoundingClientRect();
    w = wrClamp(s, s === 'l' ? ev.clientX - r.left - 4 : r.right - ev.clientX - 4);
    wrApply(s, w);
    wrPlace();
  }, () => {
    document.body.classList.remove('dragging');
    g.classList.remove('on');
    if(w) lsSet(WR_SIDES[s].key, w);
  });
});
document.addEventListener('dblclick', e => {
  const g = e.target.closest && e.target.closest('.wrg');
  if(!g) return;
  lsDel(WR_SIDES[g.dataset.s].key);
  wrApply(g.dataset.s, 0);
  wrPlace();
});
(() => {
  ['l', 'r'].forEach(s => { const w = wrPref(s); if(w) wrApply(s, w); });
  window.addEventListener('resize', wrFit);
  if(typeof ResizeObserver === 'function'){
    const ro = new ResizeObserver(() => wrPlace());
    ['.wrap', '#feed', '.wrap > .pside', '.wrap > .lside'].forEach(q => { const el = document.querySelector(q); if(el) ro.observe(el); });
  }
  requestAnimationFrame(wrFit);
})();
