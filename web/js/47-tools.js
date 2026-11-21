// «Tools» view of the Tools tab (47a TLVIEW 'tools', painted by tlPaint) — read-only list of skills/agents/commands/MCP/hooks.
// ⚠Metadata only: the list shows names, paths, sizes, counts; config text appears only after a row click (/api/tools/file).
let TOOLS = null, toolsAt = 0, toolsBusy = false, TOOLF = null;   // TOOLF = {id, name, path, text|err} of the opened row
const TOOL_KINDS = [['skill', 'Skills'], ['agent', 'Agents'], ['cmd', 'Commands'], ['mcp', 'MCP servers'], ['hook', 'Hooks']];
const TOOL_SCOPE = { user: 'user', project: 'project', plugin: 'plugin' };   // shown through T(); an unknown scope is shown raw
const TOOL_FLAG = { unused: 'unused', dup: 'duplicate', near: 'similar' };
async function loadTools(force){
  const now = Date.now();
  if(toolsBusy || (!force && now - toolsAt < 60000)) return;
  toolsBusy = true; toolsAt = now;
  try{ TOOLS = await getJSON('/api/tools?days=30'); }
  catch(e){ TOOLS = { ok: false, msg: fetchErrMsg(e) }; }
  toolsBusy = false;
  if(tvwOn()) tlPaint();
  if(typeof hnVdPendRun === 'function') hnVdPendRun();   // a «Check results» jump that arrived before the list
  if(TOOLS && TOOLS.scanning) setTimeout(() => { if(tvwOn()) loadTools(true); }, 5000);   // partial counts: poll while visible
}
function tvwOn(){ return mainView === 'tools' && TLVIEW === 'tools'; }
// The list can carry Claude Code skill/MCP harness rows (else the Harness report's «Config map» draws them).
function tvwListed(){ return !!(TOOLS && TOOLS.ok); }
// Claude Code harness skill/MCP rows for the Tools list: {by: Tools id -> row, miss: {skill, mcp} rows with no list item}.
// null = no harness data for this project (not loaded, failed, feature off, another platform) -> no decoration, never «none».
function tvwHn(items){
  if(typeof HN === 'undefined' || typeof hnKey !== 'function' || typeof PLS === 'undefined' || HN.plat !== 'cc' || !PLS.proj) return null;
  if(typeof FEATS !== 'undefined' && FEATS.harness === false) return null;
  const d = HN.data[hnKey(PLS.proj)];
  if(!d || d.ok === false) return null;
  const ids = new Set(items.map(x => x.id)), by = {}, miss = { skill: [], mcp: [] };
  [['skill', d.skills], ['mcp', d.mcps]].forEach(([k, rows]) => (Array.isArray(rows) ? rows : []).forEach(x => {
    if(!x) return;
    if(x.tid && ids.has(x.tid)) by[x.tid] = x;
    else if(k === 'skill' || hnVd(x)) miss[k].push(x);   // ⚠a flagged row with no list item must stay reachable from «Check results»
  }));
  return { by, miss, vd: d.verdict };
}
// The only reason tvwHn is null that the person can act on: the project comes from the Pipelines tab, this tab has no picker.
function tvwNoProj(){
  return typeof HN !== 'undefined' && typeof PLS !== 'undefined' && HN.plat === 'cc' && !PLS.proj
    && !(typeof FEATS !== 'undefined' && FEATS.harness === false);
}
// Stage chips in the Name cell, check result in a full-width row below (the Flags cell is too narrow for «Next step»).
function tvwPipes(h){ return h && Array.isArray(h.pipes) && h.pipes.length ? ' ' + h.pipes.map(hnPipeChip).join('') : ''; }
function tvwVdRow(h){ return h && hnVd(h) ? '<tr class=tvwvdr><td colspan=7>' + hnVdRow(h) + '</td></tr>' : ''; }
function tvwRow(r, h){
  const sc = TOOL_SCOPE[r.scope] ? T(TOOL_SCOPE[r.scope]) : r.scope;
  const pj = r.proj ? String(r.proj).split('/').pop() : '';
  const fl = (r.flags || []).map(f => TOOL_FLAG[f] ? '<em class="tvwf tvwf-' + esc(f) + '">' + esc(T(TOOL_FLAG[f])) + '</em>' : '').join('');
  const ps = tvwPipes(h), nc = ps ? '"brn tvwnp"' : 'brn';
  return '<tr class="tvwr' + (TOOLF && TOOLF.id === r.id ? ' on' : '') + (r.on ? '' : ' off') + (h ? hnVdCls(h) : '') + '" data-tid="' + esc(r.id) + '" tabindex=0' + (h ? hnVdAttr(h) : '') + '>'
    + '<td class=brd' + (r.proj ? ' title="' + esc(r.proj) + '"' : '') + '>' + esc(sc) + (pj ? ' <span class=tvwj>' + esc(pj) + '</span>' : '') + '</td>'
    // Plugin rows drop the «plugin:» prefix (the scope column says plugin); full name stays in the tooltip
    + (r.scope === 'plugin' && String(r.name).includes(':') ? '<td class=' + nc + ' title="' + esc(r.name) + '">' + esc(String(r.name).slice(String(r.name).indexOf(':') + 1)) : '<td class=' + nc + '>' + esc(r.name)) + (r.ro ? ' <s>' + esc(T('read-only')) + '</s>' : '') + ps + '</td>'
    + '<td class="brd tvwp" title="' + esc(r.path) + '">' + esc(r.path) + '</td>'
    + '<td class=brv>' + fmtTok(r.tok || 0) + '</td>'
    + '<td class=brv' + (r.last ? ' title="' + esc(stamp(r.last)) + '"' : '') + '>' + (r.uses ? r.uses : '—') + '</td>'
    + '<td class=tvwfs>' + fl + '</td>'
    + '<td class="brd tvwo">' + esc(r.on ? T('on') : T('off', 'state')) + '</td></tr>' + tvwVdRow(h);
}
// Harness row with no list item (a stage names a skill that is not installed, or a flagged server the list lacks): shown, never clickable.
function tvwMiss(x){
  const sc = TOOL_SCOPE[x.scope] ? T(TOOL_SCOPE[x.scope]) : String(x.scope || '');
  const ps = tvwPipes(x);
  return '<tr class="tvwr tvwmiss' + hnVdCls(x) + '"' + hnVdAttr(x) + '><td class=brd>' + esc(sc) + '</td>'
    + '<td class=' + (ps ? '"brn tvwnp"' : 'brn') + '>' + esc(x.name) + ps + '</td>'
    + '<td class="brd tvwp">' + (x.tid ? '' : esc(T('not installed'))) + '</td><td class=brv></td>'
    + '<td class=brv' + (x.last ? ' title="' + esc(stamp(x.last)) + '"' : '') + '>' + (x.n == null ? '' : x.n ? esc(x.n) : '—') + '</td>'   // null = not counted (unknown)
    + '<td class=tvwfs></td><td class="brd tvwo"></td></tr>' + tvwVdRow(x);
}
function tvwFile(){
  if(!TOOLF) return '';
  return '<div class=tvwv><div class=brh2><b>' + esc(TOOLF.name) + '</b> <i>' + esc(TOOLF.path) + ' · ' + esc(T('read-only')) + '</i>'
    + '<button class="wkrgb tvwx" data-tvwx>' + esc(T('Close')) + '</button></div>'
    + (TOOLF.err ? '<div class=hidnote>' + esc(TOOLF.err) + '</div>'
      : TOOLF.text == null ? '<div class=hidnote>' + esc(T('Loading…')) + '</div>'
      : '<pre class=tvwpre>' + esc(TOOLF.text) + '</pre>') + '</div>';
}
function paintTools(box){
  loadTools(false);
  // ⚠The only harness load on this tab: without it the rows get no chips/check results when the Tools tab opens first.
  if(typeof hnLoad === 'function' && typeof PLS !== 'undefined' && !(typeof FEATS !== 'undefined' && FEATS.harness === false)) hnLoad(PLS.proj, false);
  const head = '<div class="wvh wvht"><span>' + esc(T('Tool list · 30-day use')) + '</span></div>';
  let body;
  if(!TOOLS) body = '<div class=hidnote>' + esc(T('Loading…')) + '</div>';
  else if(!TOOLS.ok) body = '<div class=hidnote>' + esc(T('Could not read the tool list')) + (TOOLS.msg ? ' — ' + esc(TOOLS.msg) : '') + '</div>';
  else {
    const items = TOOLS.items || [], hn = tvwHn(items);
    body = (hn ? hnVdLine(hn.vd) : tvwNoProj() ? '<div class=hidnote>' + esc(T('Pick a project in Pipelines to see stage chips and check results here')) + '</div>' : '')   // check line here too, so stepping continues in this list
      + (TOOLS.scanning ? '<div class=hidnote>' + esc(T('Counting uses…')) + '</div>' : '')
      + '<div class=hidnote>' + esc(T('≈Tokens are estimated from file size · click a row to view its content')) + '</div>'
      + TOOL_KINDS.map(([k, en]) => {
        const rs = items.filter(x => x.kind === k), ms = hn && hn.miss[k] || [];
        if(!rs.length && !ms.length) return '';
        const tot = rs.reduce((a, x) => a + (x.tok || 0), 0);
        return '<div class=tvwg><div class=brh2><b>' + esc(T(en)) + '</b> <i>' + U(rs.length, '#') + ' · ≈' + fmtTok(tot) + ' ' + esc(T('tokens')) + '</i></div>'
          + '<table class="brt tvwt"><thead><tr><th>' + esc(T('Scope')) + '</th><th>' + esc(T('Name')) + '</th><th>' + esc(T('Path'))
          + '</th><th>' + esc(T('≈Tokens')) + '</th><th>' + esc(T('Uses (30d)')) + '</th><th>' + esc(T('Flags')) + '</th><th>' + esc(T('Status'))
          // ⚠The file view sits right under its row: after the table it landed ~1350px below the click, off screen.
          + '</th></tr></thead><tbody>' + rs.map(r => tvwRow(r, hn ? hn.by[r.id] : null)
              + (TOOLF && TOOLF.id === r.id ? '<tr class=tvwvr><td class=tvwvc colspan=7>' + tvwFile() + '</td></tr>' : '')).join('')
          + ms.map(tvwMiss).join('') + '</tbody></table></div>';
      }).join('')
      + (items.length || (hn && hn.miss.skill.length + hn.miss.mcp.length) ? '' : '<div class=hidnote>' + esc(T('No tools found')) + '</div>');
  }
  const h = '<div class="brep tvw">' + head + body + '</div>';
  if(box._tvw === h && box.querySelector('.tvw')) return;   // ⚠30s repaints would reset the <pre> scroll
  box._tvw = h;
  box.innerHTML = h;
}
async function tvwOpen(id){
  if(TOOLF && TOOLF.id === id){ TOOLF = null; tlPaint(); return; }
  const r = ((TOOLS && TOOLS.items) || []).find(x => x.id === id);
  if(!r) return;
  TOOLF = { id, name: r.name, path: r.path, text: null };
  tlPaint();
  let v;
  try{ v = await getJSON('/api/tools/file?id=' + encodeURIComponent(id)); }
  catch(e){ v = { ok: false, msg: e && e.status === 404 ? T('No such item.') : fetchErrMsg(e) }; }
  if(!TOOLF || TOOLF.id !== id) return;
  if(v && v.ok) TOOLF.text = String(v.text || ''); else TOOLF.err = (v && v.msg) || T('Could not read');
  tlPaint();
}
document.addEventListener('click', e => {
  if(!e.target.closest) return;
  if(e.target.closest('[data-tvwx]')){ TOOLF = null; tlPaint(); return; }
  const r = e.target.closest('.tvwr[data-tid]');
  if(r) tvwOpen(r.dataset.tid);
});
document.addEventListener('keydown', e => {
  const r = e.key === 'Enter' && e.target.closest && e.target.closest('.tvwr[data-tid]');
  if(r){ e.preventDefault(); tvwOpen(r.dataset.tid); }
});
