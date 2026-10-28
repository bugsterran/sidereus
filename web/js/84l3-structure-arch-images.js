// ── Structure «Architecture» security window: trivy base-image groups and the «Include images» run option (84l) ──
// ⚠Image refs, `why` and counts are tool output: esc() always, never through T().
// Pure: scanner label `id target` (trivy-image runs once per base image).
function archChkTid(t){ const g = t && typeof t.target === 'string' ? t.target.trim() : ''; return String((t && t.id) || '') + (g ? ' ' + g : ''); }
// Pure: one line naming the image-scan gap, '' when there is none. ⚠Only trivy rows count: the runner emits them only for a repo
// with a Dockerfile or compose file, so a project without one never gets an install nag; the badge total alone hides a missing scanner.
function archChkImgGap(sec){
  const tv = archChkTools(sec).filter(t => /^trivy-/.test(String(t.id)));
  if(tv.some(t => t.status === 'missing')) return T('Container images not scanned — trivy is not installed');
  // ⚠Only the runner's «add --images» skip: a FROM built from an ARG is also a skipped trivy-image row, after the box was ticked
  const im = tv.filter(t => t.id === 'trivy-image');
  if(im.length && im.every(t => t.status === 'skipped' && /add --images/.test(String(t.why || '')))) return T('Base images not scanned — tick «Include images» when requesting the check');
  return '';
}
// Pure: «Include images» box of the run preview; checked = S.run.img → the body / command carry --images.
function archChkImgBox(S){ return '<label class=ckimgb><input type=checkbox data-ckimg' + (S && S.run && S.run.img ? ' checked' : '') + '> ' + esc(T('Include images')) + '</label>'; }
// Pure: «Base images» group, one row per trivy-image target: fixable high/critical → «Replace base image», unfixed → waiting.
// ⚠A row that did not run (login needed, image not found) shows its reason, never a clean line.
function archChkImgHtml(sec){
  const rows = archChkTools(sec).filter(t => t.id === 'trivy-image' && typeof t.target === 'string' && t.target.trim());
  if(!rows.length) return '';
  return '<div class=ckimgs role=group aria-label="' + esc(T('Base images')) + '"><b>' + esc(T('Base images')) + '</b><ul>' + rows.map(t => {
    const g = t.target.trim(), f = archChkN(t.fixable), wt = archChkN(t.waiting);
    const body = t.status !== 'ok' ? '<span class=archwhy>' + esc(archChkStat(t)) + '</span>'
      : (f ? '<span class=ckimgfx>' + esc(T('fixable high/critical {n}').replace('{n}', f)) + ' → ' + esc(T('Replace base image')) + '</span>'
        : '<span>' + esc(T('No fixable high/critical')) + '</span>')
        + (wt ? '<span class=ckimgw title="' + esc(T('No fixed version released yet')) + '">' + esc(T('waiting {n}').replace('{n}', wt)) + '</span>' : '');
    return '<li><code title="' + esc(g) + '">' + esc(g) + '</code>' + body + '</li>';
  }).join('') + '</ul></div>';
}
