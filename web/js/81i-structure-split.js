// ── Structure popup side-by-side splits: drag-resize grip ─────────────────────────────────
// Split panes are resizable by default -> `.strsp` (source | test) and
// `.srmds` (markdown source | preview) get a grip; the left share is kept per viewer in `sidereus.<class>`.
// `.srt` (file tree | code) stores the tree width in px instead (min STR_SPLIT_PX, max 60% via CSS min()).
// `.plmd` («Pipelines» «Working now» list | run view, 48j) stores the list width in px the same way.
// `.archbody` (arch map | Edges list) stores the right pane width in px (STR_SPLIT_RPX; max 60% so the map keeps room).
// Default (no key) = the CSS 1fr 1fr. ⚠Drag only changes column widths — never scroll or move anything.
// ⚠The popup may be a child window and 81b stops dblclick bubbling inside .srt -> capture listeners per document.
const STR_SPLIT_KEYS = ['strsp', 'srmds', 'srt', 'archbody', 'plmd'], STR_SPLIT_MIN = 0.15, STR_SPLIT_PX = { srt: 140, plmd: 150 }, STR_SPLIT_RPX = { archbody: 240 };
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
// Focusable separator: ArrowLeft/ArrowRight move the boundary STR_SPLIT_STEP px through the drag path, Home = default.
// aria-valuenow = boundary position in percent; share keys know it up front, px keys measure on focus (strSplitAria).
const STR_SPLIT_STEP = 24;
function strSplitGrip(k){
  const v = STR_SPLIT_PX[k] || STR_SPLIT_RPX[k] ? 0 : strSplitGet(k) || 0.5;
  return '<i class=strspg data-spk=' + k + ' tabindex=0 role=separator aria-orientation=vertical aria-valuemin=0 aria-valuemax=100'
    + (v ? ' aria-valuenow=' + Math.round(v * 100) : '') + ' aria-label="' + esc(T('Resize panes')) + '" title="' + esc(T('Drag to resize · double-click for default')) + '"></i>';
}
// Resolved grid columns [left px, right px] of a split box (computed style is always px).
function strSplitTracks(box){ const t = (getComputedStyle(box).gridTemplateColumns || '').split(' ').map(parseFloat).filter(x => x >= 0); return t.length >= 2 ? [t[0], t[t.length - 1]] : null; }
function strSplitAria(D, k){
  const box = D.querySelector('.' + k), t = box && strSplitTracks(box);
  if(!t || !(t[0] + t[1] > 0)) return;
  D.querySelectorAll('.' + k + ' > .strspg').forEach(g => g.setAttribute('aria-valuenow', Math.round(100 * t[0] / (t[0] + t[1]))));
}
// Boundary at clientX -> stored value v (px or share), applied to the box. Shared by drag and keys so the clamps match.
function strSplitAt(D, k, clientX){
  const box = D.querySelector('.' + k);
  if(!box) return 0;
  const r = box.getBoundingClientRect(), gap = parseFloat(getComputedStyle(box).columnGap) || 0;
  if(r.width <= gap) return 0;
  const rp = STR_SPLIT_RPX[k], x = rp ? r.right - clientX - gap / 2 : clientX - r.left - gap / 2, px = STR_SPLIT_PX[k] || rp;
  const v = px ? Math.round(Math.max(px, Math.min(r.width * 0.6, x)))
               : Math.max(STR_SPLIT_MIN, Math.min(1 - STR_SPLIT_MIN, x / (r.width - gap)));
  if(STR_SPLIT_RPX[k]) box.style.setProperty('--spw', v + 'px'); else box.style.gridTemplateColumns = strSplitCols(v, k);
  return v;
}
function strSplitSave(k, v){ if(v) lsSet('sidereus.' + k, STR_SPLIT_PX[k] || STR_SPLIT_RPX[k] ? String(v) : v.toFixed(4)); }
function strSplitReset(D, k){
  lsDel('sidereus.' + k);
  D.querySelectorAll('.' + k).forEach(b => { b.style.gridTemplateColumns = ''; b.style.removeProperty('--spw'); });
}
function strSplitKey(D, e){
  const g = e.target && e.target.closest && e.target.closest('.strspg'), k = g && g.getAttribute('data-spk');
  if(STR_SPLIT_KEYS.indexOf(k) < 0 || e.altKey || e.metaKey || e.ctrlKey) return;
  if(e.key === 'Home'){ e.preventDefault(); strSplitReset(D, k); strSplitAria(D, k); return; }
  const dx = e.key === 'ArrowRight' ? STR_SPLIT_STEP : e.key === 'ArrowLeft' ? -STR_SPLIT_STEP : 0;
  const box = dx && D.querySelector('.' + k), t = box && strSplitTracks(box);
  if(!t) return;
  e.preventDefault(); e.stopPropagation();   // ⚠the .srt grip sits in the file tree: 81b strTreeKey would also move the selection
  const r = box.getBoundingClientRect(), gap = parseFloat(getComputedStyle(box).columnGap) || 0;
  strSplitSave(k, strSplitAt(D, k, r.left + gap / 2 + t[0] + dx));
  strSplitAria(D, k);
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
    dragTrack(e, g, ev => { v = strSplitAt(D, k, ev.clientX) || v; }, () => {
      D.body.classList.remove('dragging');
      D.querySelectorAll('.strspg.on').forEach(x => x.classList.remove('on'));
      strSplitSave(k, v); strSplitAria(D, k);
    }, D);
  }, true);
  D.addEventListener('dblclick', e => {
    const hit = keyOf(e.target);
    if(!hit) return;
    e.stopPropagation();
    strSplitReset(D, hit[1]);
  }, true);
  D.addEventListener('keydown', e => strSplitKey(D, e), true);
  D.addEventListener('focusin', e => { const hit = keyOf(e.target); if(hit) strSplitAria(D, hit[1]); }, true);
}
// The main page hosts .archbody (84j); popup documents hook themselves in strPopPaint1.
strSplitHook(document);
