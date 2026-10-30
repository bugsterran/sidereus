// Harness «Guard self-check» fold: results of scripts/harness_selfcheck.py from /api/harness selfcheck (render only; the viewer never runs it).
// ⚠Class prefix hnsk, not hnsc: hnsc is the mode/scope chip class in 47b. Case names, situations and heads go through esc() only, never T().
const HN_SKV = { blocked: 'blocked', allowed: 'let through', r2g: 'red → green', 'no r2g': 'no red → green', held: 'held', reverted: 'reverted' };
const HN_SKCTL = { allowed: 1, 'no r2g': 1, held: 1 };   // control outcomes sort after the catch rows of a group
const HN_SKCODE = { 'guard-jump': 'jump', 'guard-commit': 'gate', 'guard-commit-after-fail': 'gate', 'guard-skip-required': 'skipgate' };   // fallback when a failed catch recorded no code
function hnSkVal(v){ const s = v == null ? '?' : String(v); return HN_SKV[s] ? T(HN_SKV[s], 'selfcheck') : s; }
// Groups = cases joined by `pair` (one control may serve several catches), in first-appearance order.
function hnSkGroups(cs){
  const up = {}, f = n => { while(up[n] !== n) n = up[n] = up[up[n]]; return n; };
  cs.forEach(c => { up[c.name] = c.name; });
  cs.forEach(c => { if(Object.prototype.hasOwnProperty.call(up, c.pair)){ const a = f(c.name), b = f(c.pair); if(a !== b) up[b] = a; } });
  const gs = [], at = {};
  cs.forEach(c => { const r = f(c.name); if(!(r in at)){ at[r] = gs.length; gs.push([]); } gs[at[r]].push(c); });
  return gs.map(g => g.map((c, i) => [c, i]).sort((a, b) => (HN_SKCTL[a[0].expect] ? 1 : 0) - (HN_SKCTL[b[0].expect] ? 1 : 0) || a[1] - b[1]).map(a => a[0]));
}
// Real-run counts beside a group: guard deny codes (HN_GD whitelist), gate catches at fast+full, keep held/reverted.
function hnSkSide(g, R){
  const kind = g[0].guard;
  if(kind === 'gate') return TV({msg: 'caught {n}', vars: {n: R.cp('fast').caught + R.cp('full').caught}});
  if(kind === 'keep') return TV({msg: 'held {n} · reverted {m}', vars: {n: hnN(R.c.held), m: hnN(R.c.reverted)}});
  if(kind !== 'guard') return '';
  const cs = R.g.codes && typeof R.g.codes === 'object' ? R.g.codes : {}, codes = [];
  g.forEach(c => (Array.isArray(c.codes) ? c.codes : []).concat(HN_SKCODE[c.name] || []).forEach(k => { if(typeof k === 'string' && HN_GD[k] && codes.indexOf(k) < 0) codes.push(k); }));
  return codes.map(k => T(HN_GD[k], 'flow') + ': ' + TV({msg: 'Blocked {n}', vars: {n: hnN(cs[k])}})).join(' · ');
}
function hnSkTitle(g){
  const k = g[0].guard, code = (g.map(c => HN_SKCODE[c.name]).filter(Boolean)[0]) || '';
  if(k === 'guard') return code ? T(HN_GD[code], 'flow') : T('Pipeline guard');
  return k === 'gate' ? T('Gate red → green') : k === 'keep' ? T('Fix kept or reverted') : T('Other');
}
function hnSkRow(c){
  return '<div class="hnskr' + (c.pass === true ? '' : ' hnng') + '"><span class=hnsks title="' + esc(c.name == null ? '' : c.name) + '">' + esc(c.situation == null ? '?' : c.situation) + '</span>'
    + '<span class=hnskv>' + esc(hnSkVal(c.expect)) + '</span><span class=hnskv>' + esc(hnSkVal(c.actual)) + '</span>' + hnPF(c.pass === true) + '</div>';
}
function hnSelfcheck(d){
  const s = d && d.selfcheck && typeof d.selfcheck === 'object' ? d.selfcheck : { state: 'none' };
  const cmd = typeof s.cmd === 'string' && s.cmd ? s.cmd : 'python3 scripts/harness_selfcheck.py';
  const cs = (Array.isArray(s.cases) ? s.cases : []).filter(c => c && typeof c === 'object' && typeof c.name === 'string');
  const none = s.state !== 'ok' || !cs.length, ok = cs.filter(c => c.pass === true).length;
  const head = typeof s.head === 'string' ? s.head.slice(0, 8) : '';
  const badge = !none && s.stale ? ' <em class="hnsc hnskst" title="' + esc(TV({msg: 'results from commit {h}, not the current HEAD', vars: {h: head || '?'}})) + '">' + esc(T('different commit')) + '</em>' : '';
  const sum = none ? ' <i>' + esc(T('Not run yet')) + '</i>' : ' <i>PASS ' + ok + '/' + cs.length + (s.ts ? ' · ' + esc(hnWhen(s.ts)) : '') + '</i>' + badge;
  let body = '<div class="hntm hnskcap">' + esc(T('Replays the fixed replay set of the Sidereus repo (not the picked project): each guard must catch its case and let its control through.')) + '</div>';
  if(none) body += '<div class=hidnote>' + esc(T('Not run yet')) + ' — ' + esc(T('run:')) + ' <code class=hnrc>' + esc(cmd) + '</code></div>';
  else body += '<div class="hnskr hnskh"><span>' + esc(T('Situation fed')) + '</span><span>' + esc(T('Expected')) + '</span><span>' + esc(T('Actual')) + '</span><span></span></div>'
    + hnSkGroups(cs).map(g => {
      const side = hnSkSide(g, hnRep(d));
      return '<div class=hnskg><div class=hnskb><b class=hnskt>' + esc(hnSkTitle(g)) + '</b>' + g.map(hnSkRow).join('') + '</div>'
        + '<div class=hnske title="' + esc(T('Seen in real runs of this project')) + '">' + esc(side || '—') + '</div></div>';
    }).join('');
  return '<details class="hnmore hnskw" data-hnmore=sc' + (HN.fold.sc ? ' open' : '') + '><summary><div class=brh2><b>' + esc(T('Guard self-check')) + '</b>' + sum + '</div></summary>' + body + '</details>';
}
