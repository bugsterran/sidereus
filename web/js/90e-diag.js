// Settings «Diagnostics»: read-only view of GET /api/diag (hook overlaps, rule-file shadowing, silently-off hooks, plugins).
// ⚠Read-only by design: the only control is «Refresh». Every value is tool/config text: esc(), never T().
let DX = null, DX_LD = false;   // last /api/diag reply ({ok, ...} or {err}) · request in flight
async function dxLoad(force){
  if(DX_LD || (DX && !force)) return;
  DX_LD = true;
  try{ const r = await getJSON('/api/diag'); DX = r && r.ok ? r : { err: String((r && (r.error || r.err)) || '?') }; }
  catch(e){ DX = { err: String((e && e.message) || e) }; }
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
function cfgPaneDx(){
  if(!DX && !DX_LD) dxLoad();   // first paint of the category only; never at load time
  const top = '<div class="cfgrc dxtop">' + cfgOpt('dxr', '1', T('Refresh'), DX_LD) + '</div>';
  if(!DX) return top + dxEmpty(T('Loading…'));
  if(DX.err) return top + '<div class="cfgpd err">' + esc(T('Could not load')) + ': ' + esc(DX.err) + '</div>';
  return top + dxSec(T('Hooks on the same event'), '', dxOverlaps(DX)) + dxSec(T('Rule files'), '', dxShadow(DX))
    + dxSec(T('Silently off'), T('static estimate'), dxSilent(DX)) + dxSec(T('Plugins'), '', dxPlugins(DX));
}
