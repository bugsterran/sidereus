// Stage result line on pipeline cards (48d plNodeHtml) and the timeline run line (74c): gate evidence + matched commit, metadata only.
// Gate evidence per project (GET /api/harness/evidence), refreshed at most every PLEV_TTL ms; the next repaint picks it up.
const PLEV = {}, PLEV_TTL = 20000;
function plEvRows(proj){
  if(!proj) return [];
  const c = PLEV[proj] || (PLEV[proj] = { at: 0, rows: [], cms: [], busy: false });
  if(!c.busy && Date.now() - c.at > PLEV_TTL){
    c.busy = true;
    fetch('/api/harness/evidence?proj=' + encodeURIComponent(proj), { cache: 'no-store' }).then(r => r.json())
      .then(j => { c.rows = j && j.ok && Array.isArray(j.evidence) ? j.evidence : []; c.cms = j && j.ok && Array.isArray(j.commits) ? j.commits : []; })
      .catch(() => {}).finally(() => { c.at = Date.now(); c.busy = false; });
  }
  return c.rows;
}
// Commits ({h, ct}) from the same fetch; call after plEvRows so the cache entry exists.
function plEvCommits(proj){ return (proj && PLEV[proj] && PLEV[proj].cms) || []; }
// The newest gate run recorded inside a stage's window (+60s slack: the record lands as the gate exits) — the card says what was checked, not who ran it.
// commits ({h, ct}, optional) adds the commit whose time sits within [cm-2, cm+300] of a plrun commit stamp (L.cm).
// link (48d only) makes a FAIL line open its Harness incident via data-plevf «mode|ts»; ⚠74c/48k pass none, so their output stays byte-identical.
function plEvLine(rows, L, commits, link){
  if(!L || !L.w0 || !Array.isArray(rows)) return '';
  const w0 = L.k >= 2 && L.p0 ? L.p0 : L.w0;   // ⚠latest pass only: a looped-back stage's first-pass FAIL showed under a later ✓
  const r = rows.find(x => x && x.ts >= w0 - 5 && x.ts <= L.w1 + 60 && !(L.cap && x.ts >= L.cap - 5));   // ⚠earlier pass: the 60s slack must not reach the next pass's gate
  const cms = Array.isArray(L.cm) && Array.isArray(commits) ? L.cm.slice().reverse() : [];
  let cm = null;
  // Closest commit at or after the stamp, not the newest in the window: two commits within 5 min (parallel slices,
  // a subagent then main, or a stamp left by a rejected commit) otherwise all showed the later hash.
  for(const t of cms){
    for(const c of commits) if(c && typeof c.h === 'string' && c.ct >= t - 2 && c.ct <= t + 300 && (!cm || c.ct - t < cm.ct - t)) cm = c;
    if(cm) break;
  }
  const h7 = cm ? cm.h.slice(0, 7) : '';
  if(!r && !h7) return '';
  const tip = [];
  let body = '';
  if(r){
    const steps = Array.isArray(r.steps) ? r.steps : [], bad = steps.find(s => s && s.rc !== 0), t = steps.find(s => s && s.name === 'tests');
    const sc = Array.isArray(r.screen) ? r.screen : [], scOk = sc.filter(x => x && x.ok).length, scBad = sc.filter(x => x && !x.ok);
    const scTag = x => x.w + (x.lang ? '-' + x.lang : '');
    const badTxt = !bad ? '' : bad.name === 'screen' && scBad.length ? T('screen ') + scTag(scBad[0]) + (scBad.length > 1 ? ' +' + (scBad.length - 1) : '')
      : bad.name + (bad.failed > 0 ? ' ' + T('failed ') + bad.failed + (bad.n > 0 ? '/' + bad.n : '') : ' rc=' + bad.rc);
    body = r.rc === 0
      ? [T('gate PASS'), t && t.n > 0 ? TV({msg: '{n} tests', vars: {n: t.n}}) : '', sc.length ? T('screen ') + scOk + '/' + sc.length : ''].filter(Boolean).join(' · ')
      : T('gate FAIL') + (badTxt ? ' · ' + badTxt : '');
    steps.forEach(s => { if(s) tip.push(s.name + ' rc=' + s.rc + ' n=' + (s.n || 0) + ' failed=' + (s.failed || 0) + ' ' + (s.secs || 0) + 's'); });
    if(sc.length) tip.push(T('screen ') + sc.map(x => scTag(x) + (x.ok ? ' ok' : ' FAIL')).join(', '));
    if(r.head) tip.push('head ' + r.head + (r.dirty ? ' +dirty' : ''));
  }
  if(h7) tip.push(T('commit ') + cm.h);
  // The short hash alone is unexplained: its own span says which commit and where it came from.
  const ct = h7 ? esc(TV({msg: 'Commit made in this stage: {h}', vars: {h: cm.h}})) : '';
  const cmh = h7 ? (body ? ' · ' : '') + '<span class=plevc title="' + ct + '" aria-label="' + ct + '">' + esc(T('commit ') + h7) + '</span>' : '';
  const lk = link && r && r.rc !== 0 ? ' data-plevf="' + esc(String(r.mode || '') + '|' + r.ts) + '" tabindex=0 role=link aria-label="' + esc(T('Open this failure in Harness report')) + '"' : '';
  const ttl = lk ? T('Open this failure in Harness report') + '\n' + (tip.join('\n') || body) : tip.join('\n') || body;
  return '<div class="plev' + (!r || r.rc === 0 ? '' : ' plevng') + '"' + lk + ' title="' + esc(ttl) + '">' + esc(body) + cmh + '</div>';
}
// ⚠Capture phase + stopPropagation: the line sits inside a draggable .plnd, whose pointerdown/click would start a drag or select the stage.
function plEvfKey(e){ const t = e.target && e.target.closest ? e.target.closest('.plnd [data-plevf]') : null; return t ? t.dataset.plevf : null; }
document.addEventListener('pointerdown', e => { if(plEvfKey(e) !== null) e.stopPropagation(); }, true);
document.addEventListener('click', e => {
  const k = plEvfKey(e);
  if(k === null) return;
  e.stopPropagation(); e.preventDefault();
  if(typeof plGoHarness === 'function') plGoHarness(k);
}, true);
document.addEventListener('keydown', e => {
  if(e.key !== 'Enter' && e.key !== ' ') return;
  const k = plEvfKey(e);
  if(k === null) return;
  e.stopPropagation(); e.preventDefault();
  if(typeof plGoHarness === 'function') plGoHarness(k);
}, true);
