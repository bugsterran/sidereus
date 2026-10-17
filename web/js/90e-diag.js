// Settings «Diagnostics»: read-only view of GET /api/diag (hook overlaps, rule-file shadowing, silently-off hooks, plugins).
// ⚠Read-only by design: the only control is «Refresh». Every value is tool/config text: esc(), never T().
let DX = null, DX_LD = false;   // last /api/diag reply ({ok, ...} or {err}) · request in flight
let DXT = null, DXCP = null;     // last /api/sec-tools reply ({ok, tools} or {err}) · last «Copy» result {id, ok}
const dxGet = async u => { try{ const r = await getJSON(u); return r && r.ok ? r : { err: String((r && (r.error || r.err)) || '?') }; }
  catch(e){ return { err: String((e && e.message) || e) }; } };
async function dxLoad(force){
  if(DX_LD || (DX && !force)) return;
  DX_LD = true; DXCP = null;
  const rs = await Promise.all([dxGet('/api/diag'), dxGet('/api/sec-tools')]);
  DX = rs[0]; DXT = rs[1];
  DX_LD = false;
  if(typeof paintCfg === 'function') paintCfg();
}
const dxArr = v => Array.isArray(v) ? v.filter(x => x && typeof x === 'object') : [];
const dxSec = (lab, note, body) => '<div class=cfgs>' + esc(lab) + (note ? ' <span class=dxnote>' + esc(note) + '</span>' : '') + '</div>' + body;
// Fixed server labels for inline hooks (sidereus/hook_diag.py _disp): only these go through T(); any other cmd is data.
function dxCmd(c){
  const m = {'inline node': T('inline node'), 'inline python': T('inline python'), 'inline shell': T('inline shell'), 'inline script': T('inline script')}, s = String(c || '');
  return Object.prototype.hasOwnProperty.call(m, s) ? m[s] : s;
}
const dxEmpty = s => '<div class=cfgpd>' + esc(s) + '</div>';
// Pure: «Hooks on the same event» — per event, Sidereus hook chips first, then the other hooks on it.
function dxOverlaps(d){
  const sid = d.sidereus && typeof d.sidereus === 'object' ? d.sidereus : {}, ov = dxArr(d.overlaps), evs = [];
  ov.forEach(o => { const e = String(o.event || ''); if(evs.indexOf(e) < 0) evs.push(e); });
  if(!evs.length) return dxEmpty(T('No other hook shares an event with Sidereus'));
  return evs.map(e => '<div class=dxev><div class=dxevh><b>' + esc(e) + '</b>'
      + (Array.isArray(sid[e]) ? sid[e] : []).map(c => '<span class=dxchip title="' + esc(dxCmd(c)) + '">' + esc(dxCmd(c)) + '</span>').join('') + '</div><ul class=dxl>'
      + ov.filter(o => String(o.event || '') === e).map(o => '<li><span class=dxsrc>' + esc(o.src || '') + '</span><b>' + esc(o.name || '') + '</b> · <code title="' + esc(dxCmd(o.cmd)) + '">' + esc(dxCmd(o.cmd)) + '</code>'
        + '<small>' + esc([o.acct, o.matcher].filter(Boolean).join(' · ')) + '</small></li>').join('') + '</ul></div>').join('');
}
// Pure: «Rule files» — a project whose CLAUDE.md hides its AGENTS.md.
function dxShadow(d){
  const L = dxArr(d.shadow);
  if(!L.length) return dxEmpty(T('No CLAUDE.md shadows an AGENTS.md'));
  return '<ul class=dxl>' + L.map(x => '<li class=dxw><b>' + esc(T('CLAUDE.md shadows AGENTS.md')) + '</b> <span title="' + esc(x.proj || '') + '">' + esc(x.proj || '') + '</span>'
    + '<small>' + esc([x.claude, x.agents].filter(Boolean).join(' · ')) + '</small></li>').join('') + '</ul>';
}
// Pure: «Silently off» — hooks that read keys their event never sends (server static estimate).
function dxSilent(d){
  const L = dxArr(d.silent);
  if(!L.length) return dxEmpty(T('No silently-off hooks found'));
  return '<ul class=dxl>' + L.map(x => '<li class=dxw><b>' + esc([x.plugin, x.version].filter(Boolean).join(' ')) + '</b> · ' + esc(x.event || '') + ' · <code title="' + esc(dxCmd(x.cmd)) + '">' + esc(dxCmd(x.cmd)) + '</code>'
    + '<small>' + esc((Array.isArray(x.unread) ? x.unread : []).join(', ') + (x.verdict ? ' · ' + x.verdict : '')) + '</small></li>').join('') + '</ul>';
}
// Pure: «Plugins» — name · version · accounts, «checked» badge only when known and checked.
function dxPlugins(d){
  const L = dxArr(d.plugins);
  if(!L.length) return dxEmpty(T('No plugins installed'));
  return '<ul class=dxl>' + L.map(x => '<li' + (x.on === false ? ' class=off' : '') + '><b>' + esc(x.name || '') + '</b>' + (x.version ? ' · ' + esc(x.version) : '')
    + (x.known && x.checked ? ' <span class=dxok>' + esc(T('checked')) + '</span>' : '')
    + '<small>' + esc((Array.isArray(x.accts) ? x.accts : []).join(', ')) + '</small></li>').join('') + '</ul>';
}
// «what it catches» per scanner: same text as the SECURITY.md «Security tools» table (tests/test_sec_tools.py checks it).
const SEC_CATCH = {
  'gitleaks': 'Secrets committed to the repo (API keys, tokens, passwords)',
  'semgrep': 'Risky code patterns such as injection or unsafe calls, in many languages',
  'bandit': 'Common security issues in Python code',
  'osv-scanner': 'Known vulnerabilities in dependencies, read from lockfiles',
  'npm': 'Known vulnerabilities in npm packages (npm audit)',
};
const dxOwn = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
// Pure: «Security tools» — installed + version, or this OS's install command with «Copy». Nothing is run or sent.
// ⚠Copy only for a real command (brew/winget/pip/go/scoop); a URL hint stays plain text. Server values: esc(), never T().
function dxSecTools(rows){
  const L = dxArr(rows);
  if(!L.length) return dxEmpty(T('Could not load'));
  const net = {'yes': T('needs network'), 'registry': T('network for registry rules')};
  return '<ul class=dxt>' + L.map(x => {
    const id = String(x.id || ''), cmd = x.cmd ? String(x.cmd) : '', ok = x.installed === true;
    const st = ok ? '<span class=dxok>' + esc(T('Installed')) + (x.version ? ' · ' + esc(x.version) : '') + '</span>' : '<span class=dxmiss>' + esc(T('Not installed')) + '</span>';
    const nt = dxOwn(net, String(x.net)) ? ' <span class=dxnote>' + esc(net[String(x.net)]) + '</span>' : '';
    const how = ok || !cmd ? '' : '<div class=dxin><code>' + esc(cmd) + '</code>'
      + (/^(brew|winget|pip|go|scoop) /.test(cmd) ? cfgOpt('dxcp', id, T('Copy'))
        + (DXCP && DXCP.id === id ? '<span class=dxnote>' + esc(T(DXCP.ok ? 'Copied' : 'Copy failed')) + '</span>' : '') : '') + '</div>';
    return '<li' + (ok ? '' : ' class=dxw') + '><b>' + esc(id) + '</b>' + st + nt
      + '<small>' + (dxOwn(SEC_CATCH, id) ? esc(T(SEC_CATCH[id])) : '') + '</small>' + how + '</li>';
  }).join('') + '</ul>';
}
// «Copy»: clipboard only (copyText, 40b-sessions-list.js) — no POST, no mailbox.
function dxCopy(id){
  const x = dxArr(DXT && DXT.tools).find(r => String(r.id) === id);
  if(!x || !x.cmd) return;
  return copyText(String(x.cmd)).then(ok => { DXCP = {id, ok: !!ok}; paintCfg(); });
}
function cfgPaneDx(){
  if(!DX && !DX_LD) dxLoad();   // first paint of the category only; never at load time
  const top = '<div class="cfgrc dxtop">' + cfgOpt('dxr', '1', T('Refresh'), DX_LD) + '</div>';
  if(!DX) return top + dxEmpty(T('Loading…'));
  if(DX.err) return top + '<div class="cfgpd err">' + esc(T('Could not load')) + ': ' + esc(DX.err) + '</div>';
  return top + dxSec(T('Hooks on the same event'), '', dxOverlaps(DX)) + dxSec(T('Rule files'), '', dxShadow(DX))
    + dxSec(T('Silently off'), T('static estimate'), dxSilent(DX)) + dxSec(T('Plugins'), '', dxPlugins(DX))
    + dxSec(T('Security tools'), T('found on PATH; nothing is run'), DXT && DXT.err
      ? '<div class="cfgpd err">' + esc(T('Could not load')) + ': ' + esc(DXT.err) + '</div>' : dxSecTools(DXT && DXT.tools));
}
