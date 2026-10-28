// «Runtime behind latest patch» card of the Harness report (#27 phase 2): /api/harness `runtime`, read from the newest security report.
// ⚠Versions, paths, cycles and the report name go through esc() only, never T(); level/fix keys reach a class or text only via HN_RTL/HN_RTF.
const HN_RTL = { fail: 'hnrtl-fail', warn: 'hnrtl-warn', info: 'hnrtl-info', ok: 'hnrtl-ok', unknown: 'hnrtl-unk' };
const HN_RTP = { fail: 'behind', warn: 'behind', ok: 'latest patch', unknown: 'latest unknown' };
const HN_RTN = { python: 'Python', nodejs: 'Node.js' };
// Next step per fix key: [message, brew formula or ''] — the formula gets @<cycle> from the item.
const HN_RTF = { 'brew-node': ['Upgrade with Homebrew:', 'node'], 'brew-python': ['Upgrade with Homebrew:', 'python'],
  'system-python': ['System Python updates with macOS — or switch to a Homebrew Python', ''], other: ['Update it with the tool that installed it', ''] };
function hnRtGet(map, k){ return Object.prototype.hasOwnProperty.call(map, String(k)) ? map[k] : ''; }   // ⚠own keys only (no 'constructor')
function hnRtCls(map, k){ const v = hnRtGet(map, k); return v ? ' ' + v : ''; }
// ⚠node@<cycle> only for a versioned keg path; plain `node` is the unversioned formula. Python formulae are always python@3.x (`python` is only an alias to the newest).
function hnRtBrew(f, it, mv){
  const c = it.cycle == null || it.cycle === '' ? '' : String(it.cycle), keg = c && String(it.path || '').indexOf('/' + f + '@') >= 0;
  // ⚠An EOL cycle stays EOL after `brew upgrade`; it has to move to the newest cycle (Python major.minor, Node major).
  const nt = String(((it.newest && typeof it.newest === 'object') ? it.newest.target : '') || ''), nc = mv && /^\d+(\.\d+)*$/.test(nt) ? nt.split('.').slice(0, f === 'python' ? 2 : 1).join('.') : '';
  if(mv) return nc ? 'brew install ' + f + (keg || f === 'python' ? '@' + nc : '') : '';
  return 'brew upgrade ' + f + (keg || (f === 'python' && c) ? '@' + c : '');
}
function hnRtCmd(c){ return c ? '<code class=hnrtc>' + esc(c) + '</code>' : ''; }
function hnRtItem(it, stale){
  const o = v => v && typeof v === 'object' ? v : {}, p = o(it.patch), nw = o(it.newest), s = v => v == null || v === '' ? '?' : String(v);
  const ar = ' <span class=hntra>→</span> ', pl = hnRtGet(HN_RTP, p.level) || 'latest unknown', f = hnRtGet(HN_RTF, it.fix) || HN_RTF.other;   // an unrecognised level never reads as safe
  const pLab = p.level === 'ok' && stale ? 'latest patch when checked' : pl;
  let nLab = '';
  if(nw.level === 'info') nLab = TV({msg: hnPl(nw.behind_n, '{n} cycle behind', '{n} cycles behind'), vars: {n: hnN(nw.behind_n)}});
  else if(nw.level === 'ok') nLab = T(stale ? 'newest cycle when checked' : 'newest cycle');
  else nLab = T('latest unknown');   // unrecognised level never reads as safe
  const eol = p.eol ? '<span class="hnstp' + (p.eol_past ? ' hnng' : '') + '">' + esc(TV({msg: p.eol_past ? 'end of life {d}' : 'supported until {d}', vars: {d: s(p.eol)}})) + '</span>' : '';
  const mv = !!(f[1] && p.eol_past), cmd = f[1] ? hnRtBrew(f[1], it, mv) : '', msg = mv ? 'Move to a supported cycle:' : f[0];
  // Only the viewer's own interpreter needs a viewer restart (it runs on Python); a patch-ok item gets no step (a newer cycle alone is the label's hint).
  const re = f[1] ? (it.viewer && it.rt === 'python' ? 'then restart the viewer' : 'then restart the sessions or tools that use it') : '';
  const step = p.level === 'ok' && !p.eol_past ? '' : '<span class=hnrtn>' + esc(T(msg)) + (cmd ? ' ' + hnRtCmd(cmd) : '') + (re ? ' ' + esc(T(re)) : '') + '</span>';
  return '<div class="hnrun hnrt' + hnRtCls(HN_RTL, it.level) + '"><span class=hnrh><b>' + esc(hnRtGet(HN_RTN, it.rt) || s(it.rt)) + '</b>'
    + (it.path ? ' <code class=hnrc>' + esc(it.path) + '</code>' : '') + (it.viewer ? ' <span class=hnstp>' + esc(T('runs the viewer')) + '</span>' : '') + '</span>'
    + '<span class=hnrtr><i class=hnrtk>' + esc(T('Latest patch in its cycle')) + '</i> <code class=hnrc>' + esc(s(it.cur)) + '</code>' + ar + '<code class=hnrc>' + esc(s(p.target)) + '</code>'
    + (pLab ? ' <b class="hnrtb' + hnRtCls(HN_RTL, p.level) + '">' + esc(T(pLab)) + '</b>' : '')
    + (p.security ? ' <span class="hnstp hnng">' + esc(T('security fix')) + '</span>' : '') + (eol ? ' ' + eol : '') + '</span>'
    + '<span class=hnrtr><i class=hnrtk>' + esc(T('Newest release')) + '</i> '
    + (nLab ? '<b class="hnrtb' + hnRtCls(HN_RTL, nw.level) + '">' + esc(nLab) + '</b>' : '') + ar + '<code class=hnrc>' + esc(s(nw.target)) + '</code></span>'
    + step + '</div>';
}
function hnRuntime(d){
  const rt = d && d.runtime;
  if(!rt || typeof rt !== 'object') return '';
  const items = (Array.isArray(rt.items) ? rt.items : []).filter(x => x && typeof x === 'object');
  const when = hnWhen(rt.at), stale = !!rt.stale, n = hnN(rt.age_d);
  const src = [when ? TV({msg: 'checked {d}', vars: {d: when}}) : '', rt.report ? TV({msg: 'from {r}', vars: {r: String(rt.report)}}) : ''].filter(Boolean).join(' · ');
  // A fresh all-clear stays one quiet line.
  if(rt.state === 'ok' && !stale && !rt.offline && items.every(x => x.level === 'ok'))
    return '<div class="hnrtq hnrtl-ok"><b>' + esc(T('Runtimes on latest patch')) + '</b>' + (src ? ' <i class=hntm>' + esc(src) + '</i>' : '') + '</div>';
  let body = '';
  if(rt.state === 'none') body = '<div class=hidnote>' + esc(T('No check on record')) + (rt.cmd ? ' — ' + esc(T('run:')) + ' ' + hnRtCmd(rt.cmd) : '') + '</div>';
  else {
    if(stale) body += '<div class="hidnote hnrts">' + esc(TV({msg: hnPl(n, 'checked {n} day ago — rerun to know it is current', 'checked {n} days ago — rerun to know it is current'), vars: {n: n}}))
      + (rt.cmd ? ' ' + hnRtCmd(rt.cmd) : '') + '</div>';
    if(rt.offline) body += '<div class=hidnote>' + esc(T('Checked offline — latest versions unknown, not a clean result')) + '</div>';
    if(!items.length) body += '<div class=hidnote>' + esc(T('Latest versions could not be read — not a clean result')) + '</div>';
    body += items.map(x => hnRtItem(x, stale)).join('');
    if(items.length) body += '<div class="hidnote hnrtlim">' + esc(T('Within what the check saw: other installs are not covered. python.org publishes no security flag, so Python is judged by end of life and patch level only.')) + '</div>';
  }
  return '<div class=hnrtw><div class=brh2><b>' + esc(T('Runtime behind latest patch')) + '</b>' + (src ? ' <i>' + esc(src) + '</i>' : '') + '</div>' + body + '</div>';
}
