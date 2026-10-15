// «Tools» view of the token tab (46-tokens-tab.js TKVIEW) — read-only list of skills/agents/commands/MCP/hooks.
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
  catch(e){ TOOLS = { ok: false, msg: String((e && e.message) || e) }; }
  toolsBusy = false;
  if(mainView === 'token' && TKVIEW === 'tools') paintToken();
  if(TOOLS && TOOLS.scanning) setTimeout(() => { if(mainView === 'token' && TKVIEW === 'tools') loadTools(true); }, 5000);   // partial counts: poll while visible
}
function tvwRow(r){
  const sc = TOOL_SCOPE[r.scope] ? T(TOOL_SCOPE[r.scope]) : r.scope;
  const pj = r.proj ? String(r.proj).split('/').pop() : '';
  const fl = (r.flags || []).map(f => TOOL_FLAG[f] ? '<em class="tvwf tvwf-' + esc(f) + '">' + esc(T(TOOL_FLAG[f])) + '</em>' : '').join('');
  return '<tr class="tvwr' + (TOOLF && TOOLF.id === r.id ? ' on' : '') + (r.on ? '' : ' off') + '" data-tid="' + esc(r.id) + '" tabindex=0>'
    + '<td class=brd' + (r.proj ? ' title="' + esc(r.proj) + '"' : '') + '>' + esc(sc) + (pj ? ' <span class=tvwj>' + esc(pj) + '</span>' : '') + '</td>'
    // Plugin rows drop the «plugin:» prefix (the scope column says plugin); full name stays in the tooltip
    + (r.scope === 'plugin' && String(r.name).includes(':') ? '<td class=brn title="' + esc(r.name) + '">' + esc(String(r.name).slice(String(r.name).indexOf(':') + 1)) : '<td class=brn>' + esc(r.name)) + (r.ro ? ' <s>' + esc(T('read-only')) + '</s>' : '') + '</td>'
    + '<td class="brd tvwp" title="' + esc(r.path) + '">' + esc(r.path) + '</td>'
    + '<td class=brv>' + fmtTok(r.tok || 0) + '</td>'
    + '<td class=brv' + (r.last ? ' title="' + esc(stamp(r.last)) + '"' : '') + '>' + (r.uses ? r.uses : '—') + '</td>'
    + '<td class=tvwfs>' + fl + '</td>'
    + '<td class="brd tvwo">' + esc(r.on ? T('on') : T('off', 'state')) + '</td></tr>';
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
  const head = '<div class="wvh wvht"><span>' + esc(T('Tool list · 30-day use')) + '</span></div>';
  let body;
  if(!TOOLS) body = '<div class=hidnote>' + esc(T('Loading…')) + '</div>';
  else if(!TOOLS.ok) body = '<div class=hidnote>' + esc(T('Could not read the tool list')) + (TOOLS.msg ? ' — ' + esc(TOOLS.msg) : '') + '</div>';
  else {
    const items = TOOLS.items || [];
    body = (TOOLS.scanning ? '<div class=hidnote>' + esc(T('Counting uses…')) + '</div>' : '')
      + '<div class=hidnote>' + esc(T('≈Tokens are estimated from file size · click a row to view its content')) + '</div>'
      + TOOL_KINDS.map(([k, en]) => {
        const rs = items.filter(x => x.kind === k);
        if(!rs.length) return '';
        const tot = rs.reduce((a, x) => a + (x.tok || 0), 0);
        return '<div class=tvwg><div class=brh2><b>' + esc(T(en)) + '</b> <i>' + U(rs.length, '#') + ' · ≈' + fmtTok(tot) + ' ' + esc(T('tokens')) + '</i></div>'
          + '<table class="brt tvwt"><thead><tr><th>' + esc(T('Scope')) + '</th><th>' + esc(T('Name')) + '</th><th>' + esc(T('Path'))
          + '</th><th>' + esc(T('≈Tokens')) + '</th><th>' + esc(T('Uses (30d)')) + '</th><th>' + esc(T('Flags')) + '</th><th>' + esc(T('Status'))
          // ⚠The file view sits right under its row: after the table it landed ~1350px below the click, off screen.
          + '</th></tr></thead><tbody>' + rs.map(r => tvwRow(r)
              + (TOOLF && TOOLF.id === r.id ? '<tr class=tvwvr><td class=tvwvc colspan=7>' + tvwFile() + '</td></tr>' : '')).join('')
          + '</tbody></table></div>';
      }).join('')
      + (items.length ? '' : '<div class=hidnote>' + esc(T('No tools found')) + '</div>');
  }
  const h = '<div class="brep tvw">' + head + body + '</div>';
  if(box._tvw === h && box.querySelector('.tvw')) return;   // ⚠30s repaints would reset the <pre> scroll
  box._tvw = h;
  box.innerHTML = h;
}
async function tvwOpen(id){
  if(TOOLF && TOOLF.id === id){ TOOLF = null; paintToken(); return; }
  const r = ((TOOLS && TOOLS.items) || []).find(x => x.id === id);
  if(!r) return;
  TOOLF = { id, name: r.name, path: r.path, text: null };
  paintToken();
  let v;
  try{ v = await getJSON('/api/tools/file?id=' + encodeURIComponent(id)); }
  catch(e){ v = { ok: false, msg: e && e.status === 404 ? T('No such item.') : String((e && e.message) || e) }; }
  if(!TOOLF || TOOLF.id !== id) return;
  if(v && v.ok) TOOLF.text = String(v.text || ''); else TOOLF.err = (v && v.msg) || T('Could not read');
  paintToken();
}
document.addEventListener('click', e => {
  if(!e.target.closest) return;
  if(e.target.closest('[data-tvwx]')){ TOOLF = null; paintToken(); return; }
  const r = e.target.closest('.tvwr[data-tid]');
  if(r) tvwOpen(r.dataset.tid);
});
document.addEventListener('keydown', e => {
  const r = e.key === 'Enter' && e.target.closest && e.target.closest('.tvwr[data-tid]');
  if(r){ e.preventDefault(); tvwOpen(r.dataset.tid); }
});
