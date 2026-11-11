// ── Structure «Architecture» security window: osv reachability verdicts (item.use from the osv-triage pipeline) (84l) ──
// ⚠Rule name, file and date are verdict data: esc() always, never through T(); no pattern or code text is ever shown.
// Pure: valid verdict of an item or null; an item without `use` (old data, non-osv tools) has none (unknown is not «unused»).
function archChkUse(x){
  const u = x && x.use, s = u && typeof u === 'object' && !Array.isArray(u) ? u.s : '';
  return s === 'unused' || s === 'used' || s === 'none' ? u : null;
}
// Pure: verdict chip — «Unused (verified)» + rule · date, «Invalidated» + the hit file:line (opens the code popup via data-ckv), «Unjudged».
function archChkUseChip(x){
  const u = archChkUse(x);
  if(!u) return '';
  if(u.s === 'none') return '<span class=ckuse><b class="ckuc ckuc-none">' + esc(T('Unjudged')) + '</b></span>';
  const r = typeof u.r === 'string' ? u.r.trim().slice(0, 200) : '', at = typeof u.at === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(u.at) ? u.at : '';
  const meta = [r, at ? T('judged {d}').replace('{d}', () => at) : ''].filter(Boolean).join(' · ');
  const tail = meta ? '<small class=ckum title="' + esc(meta) + '">' + esc(meta) + '</small>' : '';
  if(u.s === 'unused') return '<span class=ckuse><b class="ckuc ckuc-un">' + esc(T('Unused (verified)')) + '</b>' + tail + '</span>';
  const f = typeof u.hf === 'string' && u.hf ? u.hf : '', ln = Number.isInteger(u.hl) && u.hl > 0 ? u.hl : 0;
  const hit = f ? '<button type=button class=ckuhit data-ckv data-af="' + esc(f) + '" data-al="' + esc(ln || 1) + '" title="' + esc(T('View code')) + '">'
    + esc(f).replace(/\//g, '/<wbr>') + (ln ? '<span class=archevl>:' + esc(ln) + '</span>' : '') + '</button>' : '';   // may break after «/» like the row path
  return '<span class=ckuse><b class="ckuc ckuc-used">' + esc(T('Invalidated')) + '</b>' + hit + tail + '</span>';
}
// Pure: {live, un} — verified-unused rows go to the collapsed group; every other row (old data included) stays live, order kept.
function archChkUnusedSplit(top){
  const a = Array.isArray(top) ? top : [], un = a.filter(x => { const u = archChkUse(x); return !!u && u.s === 'unused'; });
  return { live: a.filter(x => un.indexOf(x) < 0), un };
}
// Pure: history row (sec_checks.log_view, key «tool:rule») is verified unused when every current item with the same key and file is.
//   ⚠No matching item (past the top list, other tool, AI review row) = no verdict, so the row stays open (unknown is not «unused»).
function archChkLogUnused(x, top){
  if(!x || x.ai || typeof x.key !== 'string' || !Array.isArray(top)) return false;
  const m = top.filter(y => y && y.file === x.file && String(y.tool || '') + ':' + String(y.rule || '') === x.key);
  return m.length > 0 && m.every(y => { const u = archChkUse(y); return !!u && u.s === 'unused'; });
}
// Pure: header hint «Unjudged {n} · run the osv-triage pipeline»; '' without a natural osv_use.none > 0 (old results show nothing).
function archChkOsvHint(sec){
  const o = sec && sec.osv_use, n = o && typeof o === 'object' && !Array.isArray(o) ? o.none : null;
  if(typeof n !== 'number' || !Number.isInteger(n) || n <= 0) return '';
  return '<span class=ckosvh>' + esc(T('Unjudged {n} · run the osv-triage pipeline').replace('{n}', () => String(n))) + '</span>';
}
