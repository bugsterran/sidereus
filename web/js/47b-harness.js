// «Tooling» (harness) view of the pipeline tab (48-pipeline.js PLVIEW, project = PLS.proj): hook lifecycle lane + rule files + agent ↔ pipeline map.
// ⚠Metadata only (GET /api/harness): names, paths, sizes, counts. File text only on a card click (/api/harness/file by opaque ref) into 81's code window.
const HN = { data: {}, at: {}, busy: {}, vdAt: {}, days: 30, opening: '', exOpen: false, flowRun: '', flowNode: '', fold: {}, plat: lsGet('sidereus.hnplat', 'cc') || 'cc', flowOpen: lsGet('sidereus.hnflow', '1') !== '0', cfgOpen: lsGet('sidereus.hncfg', '0') === '1' };   // opening = ref being fetched (double-click guard); exOpen survives repaints; plat = global choice
// Cache key per platform + project (the same project looks different per CLI).
function hnKey(proj){ return HN.plat + '\n' + proj; }
// Server msgs that are English or Korean literals -> one Korean key, translated by T().
const HN_MSG = { 'unknown project': 'Unknown project', 'bad days': 'Invalid period', 'bad ref': 'Invalid file reference', 'unknown platform': 'Unknown platform' };
function hnMsg(m){ m = String(m || ''); return T(HN_MSG[m] || m); }
// ⚠Not getJSON: it throws on 4xx and drops the {msg} body these routes answer with.
async function hnGet(url){
  const r = await fetch(url, { cache: 'no-store' });
  let j = null;
  try{ j = await r.json(); }catch(e){ j = null; }
  if(!j){ const e = new Error('HTTP ' + r.status); e.status = r.status; throw e; }
  return j;
}
// Fixed lifecycle order; one column may hold several events. '' = the tool call itself (no hooks).
const HN_LANE = [['SessionStart'], ['UserPromptSubmit'], ['PreToolUse'], [''], ['PostToolUse'], ['Stop', 'SubagentStop'],
  ['PreCompact', 'PostCompact'], ['Notification']];
// Shown as T(x, 'hook') — 'binary' alone is another Korean word.
const HN_EFF = { inject: 'injects', block: 'can block', log: 'log only', bin: 'binary', ext: 'external', unknown: 'unknown' };
// Why an effect could not be read (server keys bin/ext/unknown).
const HN_EFF_TIP = { bin: 'compiled binary — effect cannot be read from its text',
  ext: 'outside ~/.claude, the data dir and the project — not read', unknown: 'script path not found' };
const HN_SCOPE = { user: 'user', project: 'project', plugin: 'plugin' };
const hnSc = s => HN_SCOPE[s] ? T(HN_SCOPE[s]) : (s || '?');   // unknown scope keys are shown raw
// Columns in lifecycle order by `lane || ev` (other CLIs send a native ev + its lane; lane "" = «Other»).
function hnLanes(events){
  const by = {}, exBy = {}, known = new Set([].concat(...HN_LANE).filter(Boolean));
  (events || []).forEach(e => {
    if(!e || !e.ev) return;
    const k = e.lane || e.ev, hs = (e.hooks || []).map(h => Object.assign({ ev: e.ev, nat: k !== e.ev ? 1 : 0 }, h));
    // ⚠An explicit lane "" folds even when the native name matches a lane event.
    if(known.has(k) && !('lane' in e && !e.lane)) by[k] = (by[k] || []).concat(hs);
    else exBy[e.ev] = (exBy[e.ev] || []).concat(hs);
  });
  const cols = HN_LANE.map(evs => ({ evs: evs, tool: evs[0] === '', hooks: [].concat(...evs.map(v => by[v] || [])) }));
  // Off-lane events (catch-all plugins register on ~20) fold into one column so the lane stays one screen wide.
  const ex = Object.keys(exBy).sort();
  if(ex.length) cols.push({ evs: ex, tool: false, extra: true, hooks: [].concat(...ex.map(v => exBy[v])) });
  return cols;
}
// Run count: null = this platform keeps no run records (blank, not «—»).
function hnCnt(n){ return n == null ? '' : n ? esc(n) + T('×') : '—'; }
function hnBase(cmd){
  const t = String(cmd || '').trim().split(/\s+/).filter(Boolean), p = t.filter(x => /[\/.]/.test(x) && !/^-/.test(x)).pop() || t[0] || '';
  return p.replace(/^['"]|['"]$/g, '').split('/').pop() || '?';
}
// Check result (sidereus/harness_verdict.py): rows carry vd {lvl, why, vp, id}; the reason text is built here from codes.
// Shown as T(x, 'verdict') — 'to check' alone is another Korean phrase.
const HN_VDL = { bad: 'problems', check: 'to check' };
// dup sources are scope keys (user · project-local · plugin …) — shown with HN_SCOPE labels.
function hnSrcs(l){
  return (Array.isArray(l) ? l : []).map(x => { const m = String(x == null ? '' : x).match(/^(.*?)(-local)?$/);
    return HN_SCOPE[m[1]] ? T(HN_SCOPE[m[1]]) + (m[2] ? T(' local') : '') : m[0]; }).join(', ');
}
function hnVdTxt(v){
  const a = v.vp || {}, n = x => String(x == null ? '' : x);
  switch(v.why){
    case 'hook_missing': return T('script file not found');
    case 'mcp_fail': return T('last record is a connection failure');
    case 'ref_missing': return TV({msg: 'pipeline {n} · {m} uses it, but it is not defined', vars: {n: n(a.pipe), m: n(a.stage)}});
    case 'idle': return TV({msg: 'no tool call matched «{m}» in {n} days', vars: {n: n(a.days), m: n(a.matcher)}});
    case 'dup': return TV({msg: 'same command registered again ({s})', vars: {s: hnSrcs(a.srcs)}});
    case 'slow_block': return TV({msg: 'can hold {n} for up to {m} s', vars: {n: n(a.ev), m: n(a.timeout)}});
    case 'rule_big': return TV({msg: 'large rule file ({n}B) — loaded into every session', vars: {n: fmtTok(Number(a.bytes) || 0)}});
  }
  return T(HN_VDL[v.lvl], 'verdict');
}
function hnVd(x){ const v = x && x.vd; return v && HN_VDL[v.lvl] ? v : null; }   // ⚠lvl is whitelisted: it lands in class/attr names
function hnVdCls(x){ const v = hnVd(x); return v ? ' hnvd hnvd-' + v.lvl : ''; }
function hnVdAttr(x){ const v = hnVd(x); return v ? ' data-hnvd="' + esc(v.id || '') + '" data-hnvdl=' + v.lvl : ''; }
function hnVdRow(x){ const v = hnVd(x); return v ? '<span class="hnvdr hnvd-' + v.lvl + '">' + esc(hnVdTxt(v)) + '</span>' : ''; }
// Check-results line; a count chip jumps to the next flagged row of that level.
function hnVdLine(c){
  if(!c || typeof c !== 'object') return '';
  const k = x => Number(c[x]) || 0;
  return '<div class=hnvdl><b>' + esc(T('Check')) + '</b>' + ['bad', 'check'].map(l => k(l)
      ? '<button class="hnvdc hnvd-' + l + '" data-hnvdgo=' + l + ' title="' + esc(T('Go to the next one')) + '">' + esc(T(HN_VDL[l], 'verdict')) + ' <b>' + k(l) + '</b></button>'
      : '<span class="hnvdc hnvdz">' + esc(T(HN_VDL[l], 'verdict')) + ' 0</span>').join('')
    + '<span class="hnvdc hnvdz">' + esc(T('ok')) + ' ' + k('ok') + '</span></div>';
}
function hnVdGo(lvl){
  const w = document.querySelector('.hnw'), els = w ? Array.from(w.querySelectorAll('[data-hnvdl="' + lvl + '"]')) : [];
  if(!els.length) return;
  const i = els.findIndex(e => e.dataset.hnvd === HN.vdAt[lvl]), el = els[(i + 1) % els.length];
  HN.vdAt[lvl] = el.dataset.hnvd;
  for(let d = el.closest('details'); d; d = d.parentElement && d.parentElement.closest('details')) if(!d.open) d.open = true;   // fold open; toggle keeps HN state
  w.querySelectorAll('.hnvdon').forEach(e => e.classList.remove('hnvdon'));
  el.classList.add('hnvdon');
  el.scrollIntoView({ block: 'nearest', inline: 'nearest' });   // ⚠nearest: never re-centre the page
}
function hnChip(h, showEv){
  const ef = HN_EFF[h.eff] ? h.eff : 'unknown', sc = hnSc(h.scope);
  // Plugin hooks: the plugin name says what it is; the bare command (e.g. a CLI binary name) moves to the badge.
  const cmdNm = hnBase(h.cmd || h.src), nm = h.plug || cmdNm, tip = HN_EFF_TIP[ef] ? T(HN_EFF_TIP[ef], 'hook') : T('Estimate — guessed from the hook event and its config');
  // desc lives in the tooltip only: inline text made every column twice as tall.
  const op = h.open ? ' hnco" data-hnref="' + esc(h.open) + '" tabindex=0' : '"';   // only inject/block/log scripts carry a ref
  return '<div class="hnc hne-' + ef + hnVdCls(h) + op + hnVdAttr(h) + ' title="' + esc((h.desc ? h.desc + '\n' : '') + String(h.cmd || h.src || '') + (h.src && h.cmd ? ' — ' + h.src : '')) + '">'
    + '<b class=hncn>' + esc(nm) + '</b>'
    + '<span class=hncm>' + ((showEv || h.nat) && h.ev ? esc(h.ev) + ' · ' : '') + (h.matcher ? esc(h.matcher) : '*') + (h.timeout ? ' · ' + esc(h.timeout) + 's' : '') + '</span>'
    + '<span class=hncb><em class="hnef hne-' + ef + '" title="' + esc(tip) + '">' + esc(T(HN_EFF[ef], 'hook')) + '</em>'
    + '<em class=hnsc' + (h.plug ? ' title="' + esc(sc) + '"' : '') + '>' + esc(h.plug ? cmdNm : sc) + '</em>'
    // ⚠Only runs that printed something are recorded: quiet = no record, so the count is unknown («?»), not 0.
    + '<i class="hncr' + (h.quiet ? ' hncrg' : '') + '"' + (h.n == null && !h.quiet ? '' : ' title="' + esc(h.quiet ? T('Runs without output are not recorded, so the count is unknown')
      : T('Counts only runs that printed output') + (h.last ? ' · ' + stamp(h.last) : '')) + '"') + '>' + (h.quiet ? '?' : hnCnt(h.n)) + '</i></span>' + hnVdRow(h) + '</div>';
}
function hnLaneHtml(events){
  return '<div class=hnl>' + hnLanes(events).map((c, i) => (i ? '<span class=hna aria-hidden=true>→</span>' : '')
    + '<div class="hncol' + (c.tool ? ' hntool' : '') + (c.hooks.length || c.tool ? '' : ' hnempty') + '">'
    + (c.extra ? '<details class=hnex' + (HN.exOpen ? ' open' : '') + '><summary class=hnev title="' + esc(c.evs.join(' · ')) + '">' + esc(TV({msg: '{n} other events', vars: {n: c.evs.length}})) + '</summary>'
      + c.hooks.map(h => hnChip(h, 1)).join('') + '</details></div>' : '')
    + (c.extra ? '' : '<div class=hnev title="' + esc(c.tool ? T('Tool runs') : c.evs.join(' / ')) + '">' + (c.tool ? esc(T('Tool runs')) : c.evs.map(esc).join(' / ')) + '</div>'
    + (c.tool ? '' : c.hooks.length ? c.hooks.map(h => hnChip(h)).join('') : '<div class=hnnone>' + esc(T('no hooks')) + '</div>') + '</div>')).join('') + '</div>';
}
// Summary over the lane hooks; ⚠Σn counts only runs that printed output (quiet/null hooks are left out) — not total runs.
function hnSum(events){
  const hs = [].concat(...hnLanes(events).map(c => c.hooks));
  let sum = 0, quiet = 0, block = 0, top = null;
  hs.forEach(h => {
    if(h.quiet || h.n == null) quiet++;   // no record: total = counted + quiet
    if(h.eff === 'block') block++;
    if(h.n != null && !h.quiet){ const n = Number(h.n) || 0; sum += n; if(n && (!top || n > top.n)) top = { h: h, n: n }; }
  });
  return '<div class=hnsum><span>' + esc(TV({msg: '{n} hooks', vars: {n: hs.length}})) + '</span> · <span title="' + esc(T('Counts only runs that printed output')) + '">'
    + esc(TV({msg: '{n} runs with output', vars: {n: sum}})) + '</span> · <span>' + esc(TV({msg: 'no record {n}', vars: {n: quiet}})) + '</span> · '
    + '<b' + (block ? ' class=warn' : '') + '>' + esc(TV({msg: 'can block {n}', vars: {n: block}})) + '</b>'
    + (top ? ' · <span>' + esc(T('most output runs: ') + (top.h.plug || hnBase(top.h.cmd || top.h.src)) + ' ' + (top.h.ev || '') + ' ' + top.n + T('×')) + '</span>' : '')
    + '</div>';
}
// Plain-word key for the effect badges + lane order, shown under «Hook flow».
const HN_LEG = [['inject', 'adds a note to the conversation context'], ['block', 'stops the tool call when its condition matches'], ['log', 'writes a file or updates state only']];
function hnLegend(){
  return '<div class=hnlg>' + HN_LEG.map(([k, t]) => '<span><em class="hnef hne-' + k + '">' + esc(T(HN_EFF[k], 'hook')) + '</em> ' + esc(T(t)) + '</span>').join('')
    + '<span><em class="hnef hne-ext">' + esc(T(HN_EFF.ext, 'hook')) + '</em><em class="hnef hne-bin">' + esc(T(HN_EFF.bin, 'hook')) + '</em> '
    + esc(T('not read, so the effect is unknown')) + '</span>'
    + '<div class=hnlgl>' + esc(T('Hooks run left to right: session start → prompt submit → before the tool → tool run → after the tool → response end')) + '</div></div>';
}
function hnRules(rules){
  if(!(rules || []).length) return '<div class=hidnote>' + esc(T('No rule files')) + '</div>';
  return '<table class="brt hnrt"><thead><tr><th>' + esc(T('Order')) + '</th><th>' + esc(T('Path')) + '</th><th>' + esc(T('Size')) + '</th></tr></thead><tbody>'
    + rules.slice().sort((a, b) => (a.order || 0) - (b.order || 0)).map(r => '<tr' + ((r.open ? ' hnro' : '') + hnVdCls(r) ? ' class="' + ((r.open ? 'hnro' : '') + hnVdCls(r)).trim() + '"' : '') + hnVdAttr(r)
      + (r.open ? ' data-hnref="' + esc(r.open) + '" tabindex=0' : '') + '><td class=brv>' + esc(r.order == null ? '' : r.order) + '</td><td class="brd hnp" title="' + esc(r.path)
      + '">' + esc(r.path) + hnVdRow(r) + '</td><td class=brv>' + esc(fmtTok(r.size || 0)) + 'B</td></tr>').join('') + '</tbody></table>';
}
// Long lists: rows in use stay visible, the rest fold behind «N more» (open state in HN.fold, kept across repaints).
function hnFold(rows, used, key){
  const k = used || Math.min(8, rows.length);
  if(k >= rows.length) return rows.join('');
  return rows.slice(0, k).join('') + '<details class=hnmore data-hnmore=' + key + (HN.fold[key] ? ' open' : '') + '><summary>'
    + esc(TV({msg: '{n} more', vars: {n: (rows.length - k)}})) + '</summary>' + rows.slice(k).join('') + '</details>';
}
// Stage titles through the canvas's en display map (48c loads later; called only at render time).
function hnStg(t){ return typeof plgShow === 'function' ? plgShow(t) : t; }
function hnAgents(agents){
  if(!(agents || []).length) return '<div class=hidnote>' + esc(T('No agents')) + '</div>';
  const isUsed = a => (a.pipes || []).length > 0 || a.n > 0;
  agents = agents.filter(isUsed).concat(agents.filter(a => !isUsed(a)));   // stable: server order within each part
  return '<div class=hnag>' + hnFold(agents.map(a => {
    const sc = hnSc(a.scope);
    return '<div class="hnar' + hnVdCls(a) + (a.open ? ' hnro" data-hnref="' + esc(a.open) + '" tabindex=0' : '"') + hnVdAttr(a) + '><b class=hnan title="' + esc(a.name) + '">' + esc(a.name) + '</b><em class=hnsc>' + esc(sc) + '</em>'
      + '<span class=hnps>' + ((a.pipes || []).length ? a.pipes.map(p => '<span class=hnpc title="' + esc(p.pipe + ' / ' + hnStg(p.stage)) + '">' + esc(p.pipe) + ' · ' + esc(hnStg(p.stage)) + '</span>').join('')
        : '<i class=hnnone>' + esc(T('not in a pipeline')) + '</i>') + '</span>'
      + '<i class=hncr>' + hnCnt(a.n) + '</i>' + hnVdRow(a) + '</div>';
  }), agents.filter(isUsed).length, 'ag') + '</div>';
}
// Skills ↔ pipeline stages, same row layout as hnAgents (⚠no .hntl: it overrides the badge column). Rows with a ref open via hnOpen.
function hnSkills(list){
  if(!Array.isArray(list)) return '';
  if(!list.length) return '<div class=hidnote>' + esc(T('None')) + '</div>';
  const rank = x => (x.pipes || []).length ? 0 : x.n > 0 ? 1 : 2;   // stage-linked, then counted, then the rest; ⚠no `pipes` key = platform without pipelines
  list = [0, 1, 2].reduce((a, k) => a.concat(list.filter(x => rank(x) === k)), []);   // stable within each group
  return '<div class=hnag>' + hnFold(list.map(x => {
    const sc = hnSc(x.scope), ps = x.pipes || [];
    return '<div class="hnar' + (x.on === false ? ' hnoff' : '') + hnVdCls(x) + (x.open ? ' hnro" data-hnref="' + esc(x.open) + '" tabindex=0' : '"') + hnVdAttr(x) + '><b class=hnan title="' + esc(x.name) + '">' + esc(x.name) + '</b>'
      + '<em class="hnsc' + (x.plug ? ' hnplg" title="' + esc(sc + ' · ' + x.plug) + '"' : '"') + '>' + esc(x.plug || sc) + '</em>'
      + '<span class=hnps>' + (ps.length ? ps.map(p => '<span class=hnpc title="' + esc(p.pipe + ' / ' + hnStg(p.stage)) + '">' + esc(p.pipe) + ' · ' + esc(hnStg(p.stage)) + '</span>').join('')
        : 'pipes' in x ? '<i class=hnnone>' + esc(T('not in a pipeline')) + '</i>' : '') + '</span>'
      + (x.on === false ? '<em class="hnsc hnoffb">' + esc(T('off', 'state')) + '</em>' : '')   // ⚠after the chips: before them it shifts the chip column
      + '<i class=hncr' + (x.last ? ' title="' + esc(stamp(x.last)) + '"' : '') + '>' + hnCnt(x.n) + '</i>' + hnVdRow(x) + '</div>';
  }), list.filter(x => rank(x) < 2).length, 'sk') + '</div>';
}
// MCP server rows (metadata only); they never open.
const HN_TR = { stdio: 1, http: 1, sse: 1 };
// Connection dot from transcript records (server: status/err/fail_at; last = last tool call).
function hnStat(x){
  const s = x.status === 'fail' || x.status === 'ok' ? x.status : 'none';
  const tip = s === 'fail' ? T('last failure: ') + stamp(x.fail_at) + (x.err ? ' · ' + x.err : '')
    // ⚠'ok' = called after the last failure (toolidx.mcp_status); the call's result is never read, so don't claim success.
    // ⚠last = 0 when the server connected but was never called — stamp(0) printed «01/01 09:00».
    // ⚠ok with fail_at and no call = reconnected after a failure (ok_at from the deferred-tools delta), not «no failure».
    : s === 'ok' ? (x.last ? T('last call: ') + stamp(x.last) + T(' (result not checked)')
        : x.fail_at ? T('reconnected') + (x.ok_at ? ': ' + stamp(x.ok_at) : '')
        : T('no failure on record · never called'))
      + (x.fail_at ? T(' · earlier failure: ') + stamp(x.fail_at) : '') : T('no connection record');
  return ['<i class="hnst hnst-' + s + '" title="' + esc(tip) + '"></i>',
    s === 'fail' ? '<em class="hnsc hnfailb" title="' + esc(tip) + '">' + esc(T('failed', 'connect')) + '</em>' : ''];
}
function hnTools(list){
  if(!Array.isArray(list)) return '';
  if(!list.length) return '<div class=hidnote>' + esc(T('None')) + '</div>';
  const rows = list.map(x => {
    const sc = hnSc(x.scope), tr = String(x.transport || ''), st = x.status !== '' ? hnStat(x) : ['', ''];   // "" = platform without call records
    return '<div class="hnar hntl' + (x.on === false ? ' hnoff' : '') + hnVdCls(x) + '"' + hnVdAttr(x) + '>'
      + st[0] + '<b class=hnan title="' + esc(x.name) + '">' + esc(x.name) + '</b>' + st[1]
      + (tr ? '<em class="hnsc hntr' + (HN_TR[tr] ? ' hntr-' + tr : '') + '">' + esc(tr) + '</em>' : '')
      + '<em class="hnsc' + (x.plug ? ' hnplg" title="' + esc(sc) + '"' : '"') + '>' + esc(x.plug || sc) + '</em>'
      + (x.on === false ? '<em class="hnsc hnoffb">' + esc(T('off', 'state')) + '</em>' : '')
      + '<i class=hncr' + (x.last ? ' title="' + esc(stamp(x.last)) + '"' : '') + '>' + hnCnt(x.n) + '</i>' + hnVdRow(x) + '</div>';
  });
  return '<div class=hnag>' + rows.join('') + '</div>';   // MCP lists stay whole
}
function hnToolBox(list, en, ctx){
  return Array.isArray(list) ? '<div class=hnbx><div class=brh2><b>' + esc(T(en, ctx)) + '</b></div>' + hnTools(list) + '</div>' : '';
}
function hnCounts(c){
  c = c || {};
  if(typeof FEATS !== 'undefined' && FEATS.tools === false) return '';   // jump target off
  return '<div class=hncnt>' + [['skill', 'Skills'], ['cmd', 'Commands'], ['mcp', 'MCP']].map(([k, en]) =>
    '<button class=wkrgb data-hntools title="' + esc(T('Show in the tools list')) + '">' + esc(T(en)) + ' <b>' + esc(c[k] || 0) + '</b></button>').join('') + '</div>';
}
async function hnLoad(proj, force){
  const k = hnKey(proj), plat = HN.plat;
  if(!proj || HN.busy[k] || (!force && HN.data[k] && Date.now() - (HN.at[k] || 0) < 60000)) return;
  HN.busy[k] = 1; HN.at[k] = Date.now();
  let v;
  try{ v = await hnGet('/api/harness?plat=' + encodeURIComponent(plat) + '&proj=' + encodeURIComponent(proj) + '&days=' + HN.days); }
  catch(e){ v = { ok: false, msg: String((e && e.message) || e) }; }
  HN.busy[k] = 0; HN.data[k] = v;
  if(v && v.ok && Array.isArray(v.plats)) HN.plats = v.plats;   // kept across loads so the switch stays while another platform loads
  // A remembered platform this server no longer knows: fall back to Claude Code instead of a dead end.
  if(v && v.msg === 'unknown platform' && HN.plat === plat && plat !== 'cc'){ hnSetPlat('cc'); return; }
  if(mainView === 'pipe' && PLVIEW === 'harness') plPaint(true);   // poll-style: skipped while focus is inside .hnw
  if(v && v.scanning) setTimeout(() => { if(mainView === 'pipe' && PLVIEW === 'harness' && PLS.proj === proj && HN.plat === plat) hnLoad(proj, true); }, 5000);
}
function hnSetPlat(p){
  HN.plat = String(p || 'cc'); lsSet('sidereus.hnplat', HN.plat);
  if(mainView === 'pipe' && PLVIEW === 'harness') plPaint();
}
// Logo-only platform switch: the name lives in title/aria-label only (logos, never platform names, as visible text).
function hnPlatSwitch(plats){
  if(!Array.isArray(plats) || plats.length < 2) return '';
  return '<div class=hnplat role=group aria-label="' + esc(T('Platform')) + '">' + plats.map(p => {
    const nm = typeof platName === 'function' && p !== 'cc' ? platName(p) : T((AILG[p] || AILG.cc)[0]);
    return '<button class="hnpb ailg-' + (AILG[p] ? p : 'cc') + (p === HN.plat ? ' on' : '') + '" data-hnplat="' + esc(p) + '" title="' + esc(nm) + '" aria-label="' + esc(nm)
      + '" aria-pressed=' + (p === HN.plat ? 'true' : 'false') + '>' + (AILG[p] ? AILG[p][1] : AILG.cc[1]) + '</button>';
  }).join('') + '</div>';
}
// «Results»: recorded gate runs (/api/harness evidence, newest first) as raw rc/counts — no narrative. ts = epoch s|ms or ISO.
function hnWhen(ts){
  let t = typeof ts === 'number' ? ts : Number(ts);
  if(!isFinite(t)) t = Date.parse(ts);
  if(!isFinite(t) || !t) return '';
  if(t < 1e12) t *= 1000;
  const d = new Date(t), p = n => String(n).padStart(2, '0');
  return p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
}
// ⚠ok only on rc === 0 exactly: a missing rc must not read as PASS.
function hnPF(ok){ return '<b class="hnpf ' + (ok ? 'hnok">PASS' : 'hnng">FAIL') + '</b>'; }
function hnStep(s){
  s = s || {};
  const n = x => x == null || x === '' ? null : x, f = n(s.failed), tot = n(s.n), sec = Number(s.secs);
  return '<span class="hnstp' + (s.rc === 0 ? '' : ' hnng') + '">' + esc(s.name == null ? '?' : s.name) + ' rc=' + esc(n(s.rc) == null ? '?' : s.rc)
    // Steps whose output carries no count are recorded as n=0; «failed 0/0» would read as a count, so show it only when something was counted or failed.
    + (Number(tot) > 0 || Number(f) > 0 ? ' · ' + esc(T('failed ')) + esc(f == null ? 0 : f) + '/' + esc(tot == null ? '?' : tot) : '')
    + (s.secs != null && isFinite(sec) ? ' · ' + esc(sec >= 10 ? Math.round(sec) : Math.round(sec * 10) / 10) + 's' : '') + '</span>';
}
function hnShot(x){
  x = x || {};
  return '<span class="hnstp' + (x.ok ? '' : ' hnng') + '">' + esc(x.w == null ? '?' : x.w) + ' ' + esc(x.lang || '') + ' ' + hnPF(!!x.ok)
    + (x.diff != null ? ' (diff ' + esc(x.diff) + ')' : '') + '</span>';
}
function hnRes(list){
  const head = '<div class=brh2><b>' + esc(T('Results')) + '</b></div>';
  if(!Array.isArray(list) || !list.length) return '<div class=hnres>' + head + '<div class=hidnote>' + esc(T('No records yet — running scripts/check.sh adds them')) + '</div></div>';
  const rows = list.map(r => {
    r = r || {};
    const h = String(r.head == null ? '' : r.head);
    return '<div class="hnrun' + (r.rc === 0 ? '' : ' hnng') + '"><span class=hnrh><i class=hntm>' + esc(hnWhen(r.ts)) + '</i> <em class=hnsc>' + esc(r.mode || '') + '</em> '
      + '<code class=hnrc title="' + esc((r.repo ? r.repo + ' @ ' : '') + h) + '">' + esc(h.slice(0, 8) || '—') + '</code>'
      + (r.dirty ? ' <em class="hnsc hndirty">' + esc(T('uncommitted changes')) + '</em>' : '') + ' ' + hnPF(r.rc === 0) + '</span>'
      + '<span class=hnsteps>' + (Array.isArray(r.steps) ? r.steps.map(hnStep).join('') : '') + (Array.isArray(r.screen) ? r.screen.map(hnShot).join('') : '') + '</span></div>';
  });
  return '<div class=hnres>' + head + hnFold(rows, 5, 'ev') + '</div>';
}
// «Red→Green» / «Pass stability» (/api/harness trail): FAIL→PASS pairs and whether each PASS held. ⚠state reaches a class only via this map.
const HN_TRS = { held: ['Stable', 'ok'], broke: ['Regressed', 'ng'], refixed: ['Re-fixed', 're'], reverted: ['Reverted', 'rv'], gone: ['Dropped', 'gn'],
  unchecked: ['Unverified (uncommitted)', 'uc'] };
function hnTrHead(x){
  x = x || {};
  const h = String(x.head == null ? '' : x.head);
  return '<i class=hntm>' + esc(hnWhen(x.ts)) + '</i> <code class=hnrc title="' + esc(h) + '">' + esc(h.slice(0, 8) || '—') + '</code>'
    + (x.dirty ? ' <em class="hnsc hndirty">' + esc(T('uncommitted changes')) + '</em>' : '');
}
function hnTrStep(s, ng, tail){ return '<span class="hnstp' + (ng ? ' hnng' : '') + '">' + esc(s == null ? '?' : s) + (tail ? ' ' + esc(tail) : '') + '</span>'; }
function hnTrFix(f){
  f = f || {};
  const fl = Array.isArray(f.flipped) ? f.flipped : [], st = Array.isArray(f.still) ? f.still : [];
  return '<div class=hnrun><span class=hnrh>' + (f.mode ? '<em class=hnsc>' + esc(f.mode) + '</em> ' : '') + hnTrHead(f.fail) + ' ' + hnPF(false) + ' <span class=hntra>→</span> '
    + hnTrHead(f.pass) + ' ' + hnPF(true) + (typeof f.commits === 'number' ? ' <i class=hntm>· ' + esc(TV({msg: '{n} commits', vars: {n: f.commits}})) + '</i>' : '') + '</span>'
    + (fl.length || st.length ? '<span class=hnsteps>' + fl.map(s => hnTrStep(s, false, 'FAIL→PASS')).join('') + st.map(s => hnTrStep(s, true, T('unchanged'))).join('') + '</span>' : '') + '</div>';
}
function hnTrHeld(x){
  x = x || {};
  const s = HN_TRS[x.state], ng = x.state === 'broke', steps = Array.isArray(x.steps) ? x.steps : [];
  return '<div class="hnrun' + (ng ? ' hnng' : '') + '"><span class=hnrh>' + (x.mode ? '<em class=hnsc>' + esc(x.mode) + '</em> ' : '') + hnTrHead(x) + ' '
    + (s ? '<b class="hntrs hntrs-' + s[1] + '">' + esc(T(s[0])) + '</b>' : '<b class=hntrs>' + esc(x.state == null ? '?' : x.state) + '</b>')
    + (ng && x.at ? ' <i class=hntm>' + esc(hnWhen(x.at)) + '</i>' : '') + '</span>'
    + (ng && steps.length ? '<span class=hnsteps>' + steps.map(t => hnTrStep(t, true)).join('') + '</span>' : '') + '</div>';
}
function hnTip(s){ const t = esc(T(s)); return ' <span class=hntip tabindex=0 role=img title="' + t + '" aria-label="' + t + '">?</span>'; }
function hnTrail(tr){
  tr = tr && typeof tr === 'object' ? tr : {};
  const fx = Array.isArray(tr.fixes) ? tr.fixes : [], hd = Array.isArray(tr.held) ? tr.held : [];
  const k = st => hd.filter(x => x && x.state === st).length;
  return '<div class=hntr><div class="hnres hntrc"><div class=brh2><b>' + esc('Red→Green') + '</b>' + hnTip('A check that went from FAIL to PASS. Shows the commits in between and the steps that flipped FAIL→PASS.') + '</div>'
    + (fx.length ? fx.map(hnTrFix).join('') : '<div class=hidnote>' + esc(T('No FAIL→PASS transition yet')) + '</div>') + '</div>'
    + '<div class="hnres hntrc"><div class=brh2><b>' + esc('Pass stability') + '</b>' + hnTip('Whether the latest PASS stayed green. Regressed = same step FAIL again · Re-fixed = PASS again after a regression · Reverted = that commit was reverted · Dropped = not in the current branch history · Unverified = PASS taken with uncommitted changes.') + ' <i>' + esc('Stable ' + k('held') + ' · Regressed ' + k('broke')) + '</i></div>'
    + (hd.length ? hd.map(hnTrHeld).join('') : '<div class=hidnote>' + esc(T('No PASS records yet')) + '</div>') + '</div></div>';
}
// Verdict counts as plain text for the «Config map» summary (buttons inside <summary> would toggle the fold).
function hnVdSum(c){
  if(!c || typeof c !== 'object') return '';
  const k = x => Number(c[x]) || 0;
  return ' <i>' + ['bad', 'check'].map(l => '<span class="hnvdq' + (k(l) ? ' hnvd-' + l : '') + '">' + esc(T(HN_VDL[l], 'verdict')) + ' ' + k(l) + '</span>').join(' · ')
    + ' · <span class=hnvdq>' + esc(T('ok')) + ' ' + k('ok') + '</span></i>';
}
// ⚠typeof guard: 47c is a separate file, and the 47b-only unit stub loads this file alone.
function hnFlowDet(d){
  const fl = typeof hnFlow === 'function' ? hnFlow(d.flow) : '', open = HN.fold.det != null ? HN.fold.det : true;   // open by default; folding is the person's choice for this page view
  return fl + '<details class=hnmore data-hnmore=det' + (open ? ' open' : '') + '><summary class=hndet>' + esc(T('Details')) + '</summary>' + hnRes(d.evidence) + hnTrail(d.trail) + '</details>';
}
// Body only: the pipeline tab owns the header, the view toggle and the project chips.
function hnHtml(){
  const proj = PLS.proj, d = HN.data[hnKey(proj)];
  hnLoad(proj, false);
  let body;
  if(!proj) body = '<div class=hidnote>' + esc(T('Pick a project')) + '</div>';
  else if(!d) body = '<div class=hidnote>' + esc(T('Loading…')) + '</div>';
  else if(d.ok === false) body = '<div class=hidnote>' + esc(T('Could not read the tooling')) + (d.msg ? ' — ' + esc(hnMsg(d.msg)) : '') + '</div>';
  // Flow first (47c), results + trail fold under «Details» (open when there is no flow), then the config map (closed by default, HN.cfgOpen).
  else return '<div class=hnw>' + hnFlowDet(d) + '<details class=hncfg' + (HN.cfgOpen ? ' open' : '') + '><summary class=hncfgs><div class=brh2><b>' + esc(T('Config map')) + '</b>'
    + hnVdSum(d.verdict) + '</div></summary>' + hnPlatSwitch(HN.plats) + hnVdLine(d.verdict) + (d.scanning ? '<div class=hidnote>' + esc(T('Counting runs…')) + '</div>' : '')
    + '<details class=hnflow data-hnflow' + (HN.flowOpen ? ' open' : '') + '><summary>'
    + '<div class=brh2><b>' + esc(T('Hook flow')) + '</b> <i>' + esc(TV({msg: 'effects are estimates · counts = last {n} days', vars: {n: HN.days}})) + '</i></div>'
    + hnSum(d.events) + '</summary>' + hnLegend() + hnLaneHtml(d.events) + '</details>'
    + '<div class=hnbot><div class=hnbx><div class=brh2><b>' + esc(T('Rule files')) + '</b> <i>' + esc(T('load order')) + '</i></div>' + hnRules(d.rules) + '</div>'
    + '<div class=hnbx><div class=brh2><b>' + esc(T('Agents ↔ pipelines')) + '</b></div>' + hnAgents(d.agents) + '</div>'
    + hnToolBox(d.mcps, 'MCP servers', 'full') + (Array.isArray(d.skills) ? '<div class=hnbx><div class=brh2><b>' + esc(T('Skills')) + '</b></div>' + hnSkills(d.skills) + '</div>' : '') + '</div>'
    + (HN.plat === 'cc' ? hnCounts(d.counts) : '') + '</details></div>';   // the «Tools» list they jump to is Claude Code's
  return '<div class=hnw>' + (proj ? hnPlatSwitch(HN.plats) : '') + body + '</div>';
}
// File viewer = the structure tab's code window (81 strPopOpenText: one window per file, theme, highlight, blocked-popup overlay).
async function hnOpen(ref, nm){
  const proj = PLS.proj;
  if(!ref || !proj || HN.opening === ref) return;
  HN.opening = ref;
  nm = String(nm || '').trim() || ref;   // the card's visible name; the opaque ref only as a fallback
  const plat = HN.plat, key = plat + '\n' + proj + '\n' + ref;   // window identity: fixed before the fetch so the result lands in the same window
  strPopOpenText({ key, name: nm, text: T('Loading…') });   // ⚠synchronous: still inside the click gesture
  let v;
  try{ v = await hnGet('/api/harness/file?plat=' + encodeURIComponent(plat) + '&proj=' + encodeURIComponent(proj) + '&ref=' + encodeURIComponent(ref)); }
  catch(e){ v = { ok: false, msg: String((e && e.message) || e) }; }
  HN.opening = '';
  if(v && v.ok) strPopTextSet({ key, name: v.name, path: v.path, text: v.text, lang: v.lang });
  else strPopTextSet({ key, name: nm, path: '', text: T('Could not read') + ((v && v.msg) ? ' — ' + hnMsg(v.msg) : ''), lang: '' });
}
function hnCardName(el){ const n = el.querySelector('.hncn, .hnan, .hnp'); return n ? n.textContent : ''; }
// Count buttons jump to the token tab's «Tools» list; cards with a ref open their file.
document.addEventListener('click', e => {
  if(!e.target.closest) return;
  const pb = e.target.closest('.hnw [data-hnplat]');
  if(pb){ if(pb.dataset.hnplat !== HN.plat) hnSetPlat(pb.dataset.hnplat); return; }
  const vg = e.target.closest('.hnw [data-hnvdgo]');
  if(vg){ hnVdGo(vg.dataset.hnvdgo === 'bad' ? 'bad' : 'check'); return; }
  const r = e.target.closest('.hnw [data-hnref]');
  if(r){ hnOpen(r.dataset.hnref, hnCardName(r)); return; }
  const fr = e.target.closest('.hnw [data-hnfr]'), fn = !fr && e.target.closest('.hnw [data-hnfn]');   // 47c flow: in-memory choice + repaint, no fetch
  if(fr || fn){
    const sel = fr ? '[data-hnfr="' + CSS.escape(fr.dataset.hnfr) + '"]' : '[data-hnfn="' + CSS.escape(fn.dataset.hnfn) + '"]';
    if(fr) HN.flowRun = fr.dataset.hnfr; else HN.flowNode = HN.flowNode === fn.dataset.hnfn ? '' : fn.dataset.hnfn;
    plPaint();
    const b = document.querySelector('.hnw ' + sel);   // repaint replaced the button: keep keyboard focus, never scroll
    if(b) b.focus({ preventScroll: true });
    return;
  }
  const c = e.target.closest('[data-hntools]');
  if(!c || !c.closest('.hnw')) return;
  TKVIEW = 'tools'; lsSet('sidereus.tkview', TKVIEW); setMainView('token');
});
document.addEventListener('keydown', e => {
  const r = e.key === 'Enter' && e.target.closest && e.target.closest('.hnw [data-hnref]');
  if(r){ e.preventDefault(); hnOpen(r.dataset.hnref, hnCardName(r)); }
});
// ⚠'toggle' does not bubble: capture phase.
document.addEventListener('toggle', e => {
  if(!e.target.classList) return;
  if(e.target.classList.contains('hnex')) HN.exOpen = e.target.open;
  else if(e.target.classList.contains('hncfg')){ HN.cfgOpen = e.target.open; lsSet('sidereus.hncfg', e.target.open ? '1' : '0'); }
  else if(e.target.classList.contains('hnflow')){ HN.flowOpen = e.target.open; lsSet('sidereus.hnflow', e.target.open ? '1' : '0'); }
  else if(e.target.classList.contains('hnmore') && e.target.dataset) HN.fold[e.target.dataset.hnmore] = e.target.open;
}, true);
