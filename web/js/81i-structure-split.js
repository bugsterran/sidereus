// ── Structure popup side-by-side splits: drag-resize grip ─────────────────────────────────
// Split panes are resizable by default -> `.strsp` (source | test) and
// `.srmds` (markdown source | preview) get a grip; the left share is kept per viewer in `sidereus.<class>`.
// `.srt` (file tree | code) stores the tree width in px instead (min STR_SPLIT_PX, max 60% via CSS min()).
// `.archbody` (arch map | Edges list) stores the right pane width in px (STR_SPLIT_RPX; max 60% so the map keeps room).
// Default (no key) = the CSS 1fr 1fr. ⚠Drag only changes column widths — never scroll or move anything.
// ⚠The popup may be a child window and 81b stops dblclick bubbling inside .srt -> capture listeners per document.
const STR_SPLIT_KEYS = ['strsp', 'srmds', 'srt', 'archbody'], STR_SPLIT_MIN = 0.15, STR_SPLIT_PX = { srt: 140 }, STR_SPLIT_RPX = { archbody: 240 };
function strSplitGet(k){
  const v = +lsGet('sidereus.' + k, 0) || 0;
  const px = STR_SPLIT_PX[k] || STR_SPLIT_RPX[k];
  if(px) return v >= px && v <= 4000 ? Math.round(v) : 0;
  return v >= STR_SPLIT_MIN && v <= 1 - STR_SPLIT_MIN ? v : 0;
}
// ⚠px keys cap at 60% in CSS too: a width saved on a wide window must not swallow the code side of a narrower one.
function strSplitCols(v, k){ return !v ? '' : STR_SPLIT_PX[k] ? 'min(' + v + 'px,60%) 1fr' : v.toFixed(4) + 'fr ' + (1 - v).toFixed(4) + 'fr'; }
// ⚠RPX keys set only --spw: the two-column CSS rule reads it inside a media query, so the stacked narrow layout always wins.
function strSplitDecl(v, k){ return STR_SPLIT_RPX[k] ? '--spw:' + v + 'px' : 'grid-template-columns:' + strSplitCols(v, k); }
function strSplitStyle(k){ const v = strSplitGet(k); return v ? ' style="' + strSplitDecl(v, k) + '"' : ''; }
function strSplitGrip(k){
  return '<i class=strspg data-spk=' + k + ' title="' + esc(T('Drag to resize · double-click for default')) + '"></i>';
}
function strSplitHook(D){
  if(!D || D._strSplit) return;
  D._strSplit = 1;
  const keyOf = t => { const g = t && t.closest && t.closest('.strspg'); const k = g && g.getAttribute('data-spk'); return STR_SPLIT_KEYS.indexOf(k) >= 0 ? [g, k] : null; };
  D.addEventListener('pointerdown', e => {
    const hit = keyOf(e.target);
    if(!hit || e.button !== 0) return;
    const g = hit[0], k = hit[1];
    e.preventDefault();
    g.classList.add('on');
    D.body.classList.add('dragging');
    let v = 0;
    // ⚠a repaint can drop the captured grip; dragTrack ends on a buttonless move
    dragTrack(e, g, ev => {
      const box = D.querySelector('.' + k);
      if(!box) return;
      const r = box.getBoundingClientRect(), gap = parseFloat(getComputedStyle(box).columnGap) || 0;
      if(r.width <= gap) return;
      const rp = STR_SPLIT_RPX[k], x = rp ? r.right - ev.clientX - gap / 2 : ev.clientX - r.left - gap / 2, px = STR_SPLIT_PX[k] || rp;
      v = px ? Math.round(Math.max(px, Math.min(r.width * 0.6, x)))
             : Math.max(STR_SPLIT_MIN, Math.min(1 - STR_SPLIT_MIN, x / (r.width - gap)));
      if(STR_SPLIT_RPX[k]) box.style.setProperty('--spw', v + 'px'); else box.style.gridTemplateColumns = strSplitCols(v, k);
    }, () => {
      D.body.classList.remove('dragging');
      D.querySelectorAll('.strspg.on').forEach(x => x.classList.remove('on'));
      if(v) lsSet('sidereus.' + k, STR_SPLIT_PX[k] || STR_SPLIT_RPX[k] ? String(v) : v.toFixed(4));
    }, D);
  }, true);
  D.addEventListener('dblclick', e => {
    const hit = keyOf(e.target);
    if(!hit) return;
    e.stopPropagation();
    lsDel('sidereus.' + hit[1]);
    D.querySelectorAll('.' + hit[1]).forEach(b => { b.style.gridTemplateColumns = ''; b.style.removeProperty('--spw'); });
  }, true);
}
// The main page hosts .archbody (84j); popup documents hook themselves in strPopPaint1.
strSplitHook(document);
