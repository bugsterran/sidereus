// ── Structure «Architecture» header «Overview» link: the HEAD commit's brief.html (arch-brief) in a new tab ──
// ⚠The server sends it with a no-script sandbox CSP; the tab opens only on a person's click. The file path is server data: esc, never T().
// Pure: '' without a brief for the shown project; else one badge link (path cut by CSS ellipsis, full path in the tooltip).
function archBriefHtml(d, p){
  const b = d && d.ok && d.brief && typeof d.brief === 'object' ? d.brief : null;
  if(!b || !p || !b.commit || !b.file) return '';
  const f = String(b.file), href = '/api/arch/brief?path=' + encodeURIComponent(p) + '&commit=' + encodeURIComponent(String(b.commit));
  return '<a class="strbg strbg-n" target=_blank rel="noopener noreferrer" href="' + esc(href) + '" title="' + esc(T('Open the big-picture overview in a new tab') + '\n' + f) + '">'
    + esc(T('Overview')) + ' <span style="display:inline-block;max-width:min(360px,40vw);overflow:hidden;text-overflow:ellipsis;vertical-align:bottom;font-weight:400">' + esc(f) + '</span></a>';
}
let BRIEFRUN = {};   // state `briefRun` (95-poll): arch-brief runs in progress per project
// Pure: projects whose run was live in prev and is gone in cur.
function archBriefEnded(prev, cur){ return Object.keys(prev || {}).filter(p => !(cur && cur[p])); }
// From 95-poll: a project whose arch-brief run just ended re-fetches /api/arch at once so «Overview» shows (mirrors 84l secRun end).
function archBriefPoll(next){
  const done = archBriefEnded(BRIEFRUN, next);
  BRIEFRUN = next || {};
  done.forEach(p => { if(ARCH.cache[p] && !ARCH.load[p]) archFetch(p, true); });   // never-viewed projects fetch on paint anyway
}
