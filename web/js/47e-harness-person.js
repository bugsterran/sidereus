// «A person» cards of the Harness report: ended runs of a bug-fix pipeline (`"catch": "person"`), from /api/harness report.person (render only, no fetch).
// ⚠Pipeline names, hashes and test paths go through esc() only, never T(); commits null = git could not be read, which is not «no commit».
function hnPersonCard(x){
  const cm = x.commits, ts = Array.isArray(x.tests) ? x.tests.filter(t => typeof t === 'string' && t) : [];
  const sha = Array.isArray(cm) ? cm.filter(h => typeof h === 'string' && h) : null;
  const chips = sha == null ? '<span class=hnstp>' + esc(T('commits unavailable')) + '</span>'
    : sha.length ? sha.map(h => '<code class=hnrc title="' + esc(h) + '">' + esc(h.slice(0, 8)) + '</code>').join('')
    : '<span class=hnstp>' + esc(T('no commit')) + '</span>';
  // Unknown commits leave the guarding test unknown too: no «no guarding test» claim then.
  const tip = T('test that now guards it'), tests = ts.length ? ts.map(t => '<span class="hnstp hnpst" title="' + esc(tip) + '">' + esc(t) + '</span>').join('')
    : sha == null ? '' : '<span class="hnstp hnng">' + esc(T('no guarding test')) + '</span>';
  return '<div class="hnrun hnperson" data-hncpc=person><span class=hnrh><b>' + esc(T('A person')) + '</b> <em class=hnsc>' + esc(x.name == null ? '?' : x.name) + '</em>'
    + ' <i class=hntm>' + esc(hnWhen(x.end || x.t0)) + '</i></span><span class="hnsteps hnpss">' + chips + tests + '</span></div>';
}
function hnPerson(R, cp){
  const p = (R && R.p) || {}, cards = (Array.isArray(p.cards) ? p.cards : []).filter(x => x && typeof x === 'object');
  let h = cards.map(hnPersonCard).join('');
  const old = cp === 'person' ? hnN(p.runs) - cards.length : 0;   // same rule as the gate checkpoints: the note shows under the filter only
  if(old > 0) h += '<div class=hidnote>' + esc(TV({msg: hnPl(old, '{n} older find, not listed', '{n} older finds, not listed'), vars: {n: old}})) + '</div>';
  return h;
}
