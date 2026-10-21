// «Working now» strip at the top of «Pipelines»: each live session · platform logo · project · pipeline chip (40b sessPlChip).
// ⚠Metadata only: never targ, prompts or tool input. ⚠One fixed-height line, always rendered (empty → note): a strip that came and went shifted the canvas every poll.
const PLNOW_MAX = 4;         // more items collapse to «+N»; items shrink with ellipsis so 900px never overflows
// ⚠'gone' = dead-pid ext session kept up to 600s (ext_store); one button per timeline row (cwd + plat).
function plNowLive(ss){
  const seen = {};
  return (ss || []).filter(x => {
    if(!x || x.state === 'done' || x.state === 'abort' || x.state === 'gone') return false;
    const k = (x.cwd || '') + '\n' + (x.plat || '');
    return seen[k] ? false : (seen[k] = true);
  });
}
function plNowHtml(ss){
  const live = plNowLive(ss === undefined ? SESS : ss), shown = live.slice(0, PLNOW_MAX), more = live.length - shown.length;
  const head = '<span class=plnowh>' + esc(T('Working now')) + '</span>';
  if(!live.length) return '<div class=plnow>' + head + '<span class=plnowe>' + esc(T('No sessions working now')) + '</span></div>';
  return '<div class=plnow>' + head + shown.map(x => '<button type=button class=plnowi data-pncwd="' + esc(x.cwd || '') + '" data-pnplat="' + esc(x.plat || '') + '" title="'
      + esc((x.project || '') + ' — ' + T('Show in Timeline')) + '">' + aiLogo(x.plat) + '<span class=plnowp>' + esc(x.project || '') + '</span>' + sessPlChip(x) + '</button>').join('')
    + (more > 0 ? '<span class=plnowm title="' + esc(live.slice(PLNOW_MAX).map(x => x.project || '').join(', ')) + '">+' + more + '</span>' : '') + '</div>';
}
function plNowGo(cwd, plat){
  // ⚠Timeline rows carry no plat for Claude (74b data-tlp = g.plat || ''; 74 compares plat || 'cc'): 'cc' maps to ''.
  const tp = plat && plat !== 'cc' ? plat : '';
  const sel = '.tlr.tlrs[data-tlc="' + CSS.escape(cwd || '') + '"][data-tlp="' + CSS.escape(tp) + '"]';
  if(typeof mvGo === 'function') mvGo('time', sel); else setMainView('time');
}
document.addEventListener('click', e => {
  const b = e.target.closest && e.target.closest('.plw [data-pncwd]');
  if(b) plNowGo(b.dataset.pncwd, b.dataset.pnplat);
});
