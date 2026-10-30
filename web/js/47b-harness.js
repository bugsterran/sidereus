// «Harness» view of the pipeline tab (48-pipeline.js PLVIEW, project = PLS.proj): gate report + hook lifecycle lane + rule files + agent ↔ pipeline map.
// ⚠Metadata only (GET /api/harness): names, paths, sizes, counts. File text only on a card click (/api/harness/file by opaque ref) into 81's code window.
const HN = { data: {}, at: {}, busy: {}, vdAt: {}, days: 30, opening: '', exOpen: false, cp: '', fold: {}, plat: lsGet('sidereus.hnplat', 'cc') || 'cc', flowOpen: lsGet('sidereus.hnflow', '1') !== '0', cfgOpen: (v => v === '1' ? true : v === '0' ? false : null)(lsGet('sidereus.hncfg', '')), cfgShown: false, go: null };   // go = incident target from a stage card's FAIL line (hnGo); opening = ref being fetched (double-click guard); exOpen survives repaints; plat = global choice
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
    case 'never_ran': return TV({msg: 'did not run in {n} days', vars: {n: n(a.days)}});
    case 'dup': return TV({msg: 'same command registered again ({s})', vars: {s: hnSrcs(a.srcs)}});
    case 'slow_block': return TV({msg: 'can hold {n} for up to {m} s', vars: {n: n(a.ev), m: n(a.timeout)}});
    case 'rule_big': return TV({msg: 'large rule file ({n}B) — loaded into every session', vars: {n: fmtTok(Number(a.bytes) || 0)}});
    default: { const h = typeof hnVdTxtHook === 'function' ? hnVdTxtHook(v) : null; if(h) return h; }   // 47h hook-cost reasons (slow · no_effect)
  }
  return T(HN_VDL[v.lvl], 'verdict');
}
function hnVd(x){ const v = x && x.vd; return v && HN_VDL[v.lvl] ? v : null; }   // ⚠lvl is whitelisted: it lands in class/attr names
function hnVdCls(x){ const v = hnVd(x); return v ? ' hnvd hnvd-' + v.lvl : ''; }
function hnVdAttr(x){ const v = hnVd(x); return v ? ' data-hnvd="' + esc(v.id || '') + '" data-hnvdl=' + v.lvl : ''; }
function hnVdRow(x){ const v = hnVd(x); return v ? '<span class="hnvdr hnvd-' + v.lvl + '">' + esc(hnVdTxt(v)) + '</span>' + (typeof hnNxFold === 'function' ? hnNxFold(v.why, x) : '') : ''; }   // 47g «Next step»
// Check-results line; a count chip jumps to the next flagged row of that level.
function hnVdLine(c){
  if(!c || typeof c !== 'object') return '';
  const k = x => Number(c[x]) || 0;
  return '<div class=hnvdl><b>' + esc(T('Check results')) + '</b>' + ['bad', 'check'].map(l => k(l)
      ? '<button class="hnvdc hnvd-' + l + '" data-hnvdgo=' + l + ' title="' + esc(T('Go to the next one')) + '">' + esc(T(HN_VDL[l], 'verdict')) + ' <b>' + k(l) + '</b></button>'
      : '<span class="hnvdc hnvdz">' + esc(T(HN_VDL[l], 'verdict')) + ' 0</span>').join('')
    + '<span class="hnvdc hnvdz">' + esc(T('ok')) + ' ' + k('ok') + '</span></div>';
}
// Flagged rows live in the Tools view's «Config map»: from the Harness report, open it there first, then step after paint.
function hnVdGo(lvl){
  const w = document.querySelector('.hnw');
  if(!(w && w.classList && w.classList.contains('hncfgw'))){
    HN.cfgOpen = true; lsSet('sidereus.hncfg', '1');
    TKVIEW = 'tools'; lsSet('sidereus.tkview', TKVIEW); setMainView('token');
    (typeof requestAnimationFrame === 'function' ? requestAnimationFrame : setTimeout)(() => hnVdStep(lvl));
    return;
  }
  hnVdStep(lvl);
}
function hnVdStep(lvl){
  const w = document.querySelector('.hncfgw'), els = w ? Array.from(w.querySelectorAll('[data-hnvdl="' + lvl + '"]')) : [];
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
    // ⚠Transcripts record only runs that printed something: quiet = no record, so the count is unknown («?»), not 0.
    // nsrc otel = every firing from Claude Code telemetry since nfrom, so 0 is a real 0.
    + '<i class="hncr' + (h.quiet ? ' hncrg' : '') + '"' + (h.n == null && !h.quiet ? '' : ' title="' + esc(h.quiet ? T('Runs without output are not recorded, so the count is unknown')
      : (h.nsrc === 'otel' ? TV({msg: 'All runs since {d} (Claude Code telemetry)', vars: {d: String(h.nfrom || '')}}) : T('Counts only runs that printed output')) + (h.last ? ' · ' + stamp(h.last) : '')) + '"') + '>'
      + (h.quiet ? '?' : h.nsrc === 'otel' && !h.n ? '0' + T('×') : hnCnt(h.n)) + '</i>' + (typeof hnRmBtn === 'function' ? hnRmBtn(h) : '') + '</span>' + hnVdRow(h) + (typeof hnHookHint === 'function' ? hnHookHint(h) : '') + '</div>';
}
function hnLaneHtml(events){
  return '<div class=hnl>' + hnLanes(events).map((c, i) => (i ? '<span class=hna aria-hidden=true>→</span>' : '')
    + '<div class="hncol' + (c.tool ? ' hntool' : '') + (c.hooks.length || c.tool ? '' : ' hnempty') + '">'
    + (c.extra ? '<details class=hnex' + (HN.exOpen ? ' open' : '') + '><summary class=hnev title="' + esc(c.evs.join(' · ')) + '">' + esc(TV({msg: '{n} other events', vars: {n: c.evs.length}})) + '</summary>'
      + c.hooks.map(h => hnChip(h, 1)).join('') + '</details></div>' : '')
    + (c.extra ? '' : '<div class=hnev title="' + esc(c.tool ? T('Tool runs') : c.evs.join(' / ')) + '">' + (c.tool ? esc(T('Tool runs')) : c.evs.map(esc).join(' / ')) + '</div>'
    + (c.tool ? '' : c.hooks.length ? c.hooks.map(h => hnChip(h)).join('') : '<div class=hnnone>' + esc(T('no hooks')) + '</div>') + '</div>')).join('') + '</div>';
}
// Summary over the lane hooks; ⚠Σn = telemetry runs where covered, else only runs that printed output (quiet/null hooks are left out).
function hnSum(events){
  const hs = [].concat(...hnLanes(events).map(c => c.hooks));
  let sum = 0, quiet = 0, block = 0, top = null;
  hs.forEach(h => {
    if(h.quiet || h.n == null) quiet++;   // no record: total = counted + quiet
    if(h.eff === 'block') block++;
    if(h.n != null && !h.quiet){ const n = Number(h.n) || 0; sum += n; if(n && (!top || n > top.n)) top = { h: h, n: n }; }
  });
  const ot = hs.some(h => h.nsrc === 'otel');   // telemetry rows count every run, so the total is no longer «with output» only
  return '<div class=hnsum><span>' + esc(TV({msg: '{n} hooks', vars: {n: hs.length}})) + '</span> · <span title="' + esc(ot ? T('All runs where Claude Code telemetry covers the hook; otherwise only runs that printed output') : T('Counts only runs that printed output')) + '">'
    + esc(TV({msg: ot ? '{n} runs' : '{n} runs with output', vars: {n: sum}})) + '</span> · <span>' + esc(TV({msg: 'no record {n}', vars: {n: quiet}})) + '</span> · '
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
  hnRepaint(true);   // poll-style: skipped while focus is inside .hnw
  if(v && v.scanning) setTimeout(() => { if(FEATS.harness !== false && hnShown() && PLS.proj === proj && HN.plat === plat) hnLoad(proj, true); }, 5000);
}
// Harness data shows in two places: the Harness report and the Tools view's «Config map».
function hnShown(){ return (mainView === 'pipe' && PLVIEW === 'harness') || (mainView === 'token' && TKVIEW === 'tools'); }
function hnRepaint(poll){
  if(mainView === 'pipe' && PLVIEW === 'harness') plPaint(poll);
  else if(mainView === 'token' && TKVIEW === 'tools' && typeof paintToken === 'function'){
    // ⚠Same guards as plPaint: a poll rebuild drops keyboard focus and an open title tooltip inside the map.
    const fe = document.activeElement;
    if(poll && ((fe && fe.closest && fe.closest('.hncfgw')) || (document.querySelector && document.querySelector('.hncfgw [title]:hover')))) return;
    paintToken();
  }
}
function hnSetPlat(p){
  HN.plat = String(p || 'cc'); lsSet('sidereus.hnplat', HN.plat); HN.go = null;
  hnRepaint();
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
function hnRes(list, bare){
  const head = bare ? '' : '<div class=brh2><b>' + esc(T('Results')) + '</b></div>';   // bare: the «Gate runs» fold already titles it
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
// Incident states (report incidents, harness_trail). ⚠state reaches a class only via this map.
const HN_TRS = { held: ['Stable', 'ok'], broke: ['Regressed', 'ng'], refixed: ['Re-fixed', 're'], reverted: ['Reverted', 'rv'], gone: ['Dropped', 'gn'],
  unchecked: ['Unverified (uncommitted)', 'uc'] };
function hnTrHead(x){
  x = x || {};
  const h = String(x.head == null ? '' : x.head);
  return '<i class=hntm>' + esc(hnWhen(x.ts)) + '</i> <code class=hnrc title="' + esc(h) + '">' + esc(h.slice(0, 8) || '—') + '</code>'
    + (x.dirty ? ' <em class="hnsc hndirty">' + esc(T('uncommitted changes')) + '</em>' : '');
}
function hnTrStep(s, ng, tail){ return '<span class="hnstp' + (ng ? ' hnng' : '') + '">' + esc(s == null ? '?' : s) + (tail ? ' ' + esc(tail) : '') + '</span>'; }
// Gate report (#27 R1-R4): /api/harness `report` + `guards`. ⚠Metadata only: hashes, ts, mode, rc, counts, step names, deny codes.
// ⚠Checkpoint keys reach a class/attr only via HN_CP; the filter lives in HN.cp (memory only, no fetch, no scroll).
// [label, command chip, tooltip] — the chip alone named a script, not what it guards.
const HN_CP = { hooks: ['Before edit', 'hooks', 'Pipeline hook (hooks/pl_flow.py): refuses a step or edit that breaks the run order'],
  fast: ['Right after', 'check --fast', 'scripts/check.sh --fast: the quick gate an implementer runs right after editing'],
  full: ['Before commit', 'check --full', 'scripts/check.sh --full: the full gate (tests, screen check) the verifier runs before a commit'],
  ci: ['After push (CI)', 'gh run watch', 'The evidence hook records the result of gh run watch --exit-status; Sidereus never calls GitHub'],
  other: ['Other gates', '', 'Any other gate command recorded by a run'],
  person: ['A person', '', 'A bug-fix pipeline run (marked "catch": "person"): a person found the defect before any gate did'] };
const HN_CPK = ['hooks', 'fast', 'full', 'ci', 'other', 'person'];
// hooks/pl_flow.py deny codes, shown as T(x, 'flow'); unknown codes are never shown raw.
const HN_GD = { jump: 'Stage jump', agent: 'Wrong agent', model: 'Wrong model', tag: 'Missing tag', stage: 'Unknown stage', stop: 'Stopped',
  gate: 'Commit before gate', skipgate: 'Required gate skipped' };
function hnN(x){ const n = Number(x); return isFinite(n) && n > 0 ? Math.floor(n) : 0; }
function hnMs(ts){ let t = Number(ts); if(!isFinite(t)) t = Date.parse(ts); return isFinite(t) && t ? (t < 1e12 ? t * 1000 : t) : 0; }
function hnRep(d){
  const o = x => x && typeof x === 'object' && !Array.isArray(x) ? x : {};
  const r = o(d && d.report), g = o(d && d.guards), cps = o(r.checkpoints);
  return { c: o(r.counts), g: g, p: o(r.person), since: r.since, inc: (Array.isArray(r.incidents) ? r.incidents : []).filter(x => x && typeof x === 'object'),
    cp: k => { const c = o(cps[k]), n = hnN(c.caught);   // listed = this cp's incidents among the shown newest ones; missing (older server) = caught
      if(k === 'person'){ const p = o(r.person); return { runs: hnN(p.runs), caught: hnN(p.runs), listed: Array.isArray(p.cards) ? p.cards.length : 0 }; }   // every ended bug-fix run = one find
      return k === 'hooks' ? { runs: hnN(g.runs), caught: hnN(g.deny), listed: hnN(g.deny) } : { runs: hnN(c.runs), caught: n, listed: c.listed == null ? n : hnN(c.listed), streak: hnN(c.streak) }; } };
}
// Strip keys for this report; «Other gates» only when it ran, «A person» only when a bug-fix pipeline exists, CI only with recorded runs.
function hnCpKeys(R){ return HN_CPK.filter(k => k === 'person' ? Array.isArray(R.p.pipes) && R.p.pipes.length > 0 : k === 'ci' ? R.cp(k).runs > 0 : k !== 'other' || R.cp(k).runs || R.cp(k).caught); }
function hnIncCp(x){ return x.cp !== 'hooks' && x.cp !== 'person' && HN_CP[x.cp] ? x.cp : 'other'; }
// R1: three numbers straight from report.counts.
// One-vs-many message key (English source); ko entries may share one text.
function hnPl(n, one, many){ return Number(n) === 1 ? one : many; }
function hnTiles(R){
  const k = x => hnN(R.c[x]);   // missing key (older server) = 0
  const t = [['caught', 'Caught (red→green)', 'A gate failed, then a later run of the same gate passed'],
    ['held', 'Held', 'The fixed gate still passes'],
    ['again', 'Broke again', 'Failed again later or the fix was reverted', 1],   // again + reverted; Reverted stays an incident card state
    ['person', 'Found by a person first', 'Ended bug-fix pipeline runs: a person found the defect before any gate did']];
  const val = key => key === 'again' ? k('again') + k('reverted') : k(key);
  const note = [];
  if(R.c.checked != null && k('checked') !== k('caught')) note.push(TV({msg: 'checked {n} of {m}', vars: {n: k('checked'), m: k('caught')}}));
  if(k('gone')) note.push(TV({msg: '{n} no longer in branch history', vars: {n: k('gone')}}));
  return '<div class=hnrept>' + t.map(([key, en, tip, q]) => '<div class="hnrepn hnrepn-' + key + '"' + (q ? '' : ' title="' + esc(T(tip)) + '"') + '><b>' + val(key) + '</b><span>' + esc(T(en))
      + (q ? ' <span class=hntip tabindex=0 role=img title="' + esc(T(tip)) + '" aria-label="' + esc(T(tip)) + '">?</span>' : '') + '</span></div>').join('')
    + (note.length ? '<i class="hntm hnrepk">' + esc(note.join(' · ')) + '</i>' : '') + '</div>';
}
// R4: «What is guarding» — one button per checkpoint; «Other gates» only when it ran.
function hnStrip(R){
  const ks = hnCpKeys(R);
  return '<div class=hnrepg role=group aria-label="' + esc(T('What is guarding')) + '"><b class=hnrepgh>' + esc(T('What is guarding')) + '</b>' + ks.map(k => {
    const v = R.cp(k), on = HN.cp === k;
    const n = !v.runs && !v.caught ? TV({msg: 'ran {n}', vars: {n: 0}}) : TV({msg: k === 'hooks' ? 'blocked {n}' : k === 'person' ? 'found {n}' : 'caught {n}', vars: {n: v.caught}});
    return '<button class="hncpb' + (on ? ' on' : '') + '" data-hncp=' + k + ' aria-pressed=' + on + ' title="' + esc(T(HN_CP[k][2]) + '\n' + TV({msg: hnPl(v.runs, 'ran {n} time', 'ran {n} times'), vars: {n: v.runs}})) + '"><b>' + esc(T(HN_CP[k][0])) + '</b>'
      + (HN_CP[k][1] ? ' <code class=hnrc>' + esc(HN_CP[k][1]) + '</code>' : '') + ' <i>' + esc(n) + '</i></button>';
  }).join('') + (ks.indexOf('ci') >= 0 ? '<i class=hntm>' + esc(TV({msg: 'Holding: CI streak {n}/5', vars: {n: Math.min(R.cp('ci').streak, 5)}})) + '</i>' : '') + '</div>';
}
// R2: red → fix commits → green → held/reverted.
function hnInc(x, go){
  const o = v => v && typeof v === 'object' ? v : {}, f = o(x.fail), p = o(x.pass), s = HN_TRS[x.state];
  const fl = Array.isArray(x.flipped) ? x.flipped : [], st = Array.isArray(x.still) ? x.still : [];
  const rc = f.rc == null || f.rc === '' ? '?' : String(f.rc), fd = f.failed == null || f.failed === '' ? null : String(f.failed);
  const ev = TV(fd == null ? {msg: 'exit {n}', vars: {n: rc}} : {msg: 'exit {n} · failed {m}', vars: {n: rc, m: fd}}), ar = ' <span class=hntra>→</span> ';
  return '<div class="hnrun hninc' + (x.state === 'broke' ? ' hnng' : '') + (go === true ? ' hngo" tabindex=-1' : '"') + ' data-hncpc=' + hnIncCp(x) + '><span class=hnrh>'
    + (x.mode ? '<em class=hnsc' + ((x.mode === 'fast' || x.mode === 'full' || x.mode === 'ci') ? ' title="' + esc(T(HN_CP[x.mode][2])) + '"' : '') + '>' + esc(x.mode) + '</em> ' : '') + hnTrHead(f) + ' ' + hnPF(false) + ' <i class=hnrepe>' + esc(ev) + '</i>' + ar
    + (typeof x.commits === 'number' ? '<i class=hntm>' + esc(TV({msg: hnPl(x.commits, '{n} commit', '{n} commits'), vars: {n: x.commits}})) + '</i>' + ar : '')
    + hnTrHead(p) + ' ' + hnPF(true) + ar
    + (s ? '<b class="hntrs hntrs-' + s[1] + '">' + esc(T(s[0])) + '</b>' : '<b class=hntrs>' + esc(x.state == null ? '?' : x.state) + '</b>')
    + (x.at && (x.state === 'broke' || x.state === 'reverted') ? ' <i class=hntm>' + esc(hnWhen(x.at)) + '</i>' : '') + '</span>'
    + (fl.length || st.length ? '<span class=hnsteps>' + fl.map(v => hnTrStep(v, false, 'FAIL→PASS')).join('') + st.map(v => hnTrStep(v, true, T('unchanged'))).join('') + '</span>' : '')
    + (typeof hnNxFold === 'function' && HN_NX_INC.indexOf(x.state) >= 0 ? hnNxFold(x.state, x) : '') + '</div>';
}
// R3: a checkpoint that ran but caught nothing = one quiet card; hooks show their deny codes.
function hnQuiet(R, k){
  const v = R.cp(k), hk = k === 'hooks';
  if(k === 'person' || !v.runs || (!hk && v.caught)) return '';   // person cards come from 47e hnPerson
  const cs = hk && R.g.codes && typeof R.g.codes === 'object' ? R.g.codes : {}, unk = hk ? hnN(R.g.unknown) : 0;
  const codes = Object.keys(HN_GD).filter(c => hnN(cs[c])).map(c => '<span class=hnstp>' + esc(T(HN_GD[c], 'flow')) + ' ×' + hnN(cs[c]) + '</span>');
  if(unk) codes.push('<span class=hnstp>' + esc(TV({msg: 'unknown {n}', vars: {n: unk}})) + '</span>');
  return '<div class="hnrun' + (v.caught ? '' : ' hnquiet') + '" data-hncpc=' + k + '><span class=hnrh><b>' + esc(T(HN_CP[k][0])) + '</b>'
    + (HN_CP[k][1] ? ' <code class=hnrc>' + esc(HN_CP[k][1]) + '</code>' : '') + ' <i class=hntm>'
    + esc(TV({msg: hk ? hnPl(v.runs, 'ran {n} time, blocked {m}', 'ran {n} times, blocked {m}') : hnPl(v.runs, 'ran {n} time, caught 0', 'ran {n} times, caught 0'), vars: {n: v.runs, m: v.caught}})) + '</i></span>'
    + (codes.length ? '<span class=hnsteps>' + codes.join('') + '</span>' : '')
    + (hk && hnN(cs.skipgate) && typeof hnNxFold === 'function' ? hnNxFold('skipgate', { key: 'skipgate', count: hnN(cs.skipgate) }) : '') + '</div>';
}
// Stage card FAIL line (48 plGoHarness) → target incident by evidence row key «mode|ts». Bad keys are ignored.
function hnGo(key){
  const m = String(key == null ? '' : key).match(/^([a-z0-9_-]{0,20})\|(\d+(?:\.\d+)?)$/), ts = m ? Number(m[2]) : NaN;
  if(!m || !isFinite(ts) || ts <= 0) return;
  HN.go = { mode: m[1], ts: ts, proj: PLS.proj, done: false }; HN.cp = '';   // ⚠a checkpoint filter could hide the target card
}
// Target incident for HN.go, or {note} when there is none. ⚠Number compare: report ts is float, the row key may be an int.
function hnGoFind(R){
  const g = HN.go, n = v => Number(v && v.ts), same = R.inc.filter(x => x.mode === g.mode);
  const hit = same.find(x => n(x.fail) === g.ts);
  if(hit) return { x: hit };
  // A superseded FAIL pairs through the latest FAIL before the next PASS: the earliest same-mode pair whose FAIL is at or after it.
  const cov = same.filter(x => n(x.fail) >= g.ts && n(x.pass) > g.ts).sort((a, b) => n(a.pass) - n(b.pass))[0];
  if(!cov) return { note: 'Not fixed yet — an incident card appears with the next PASS' };
  // ⚠Unlisted pairs (caught > listed) are older than every listed PASS of the mode: below that, cov may not be the real pair.
  const passes = same.map(x => n(x.pass)).filter(isFinite), minP = Math.min.apply(null, passes);
  return hnN(R.c.caught) <= R.inc.length || g.ts >= minP ? { x: cov } : { note: 'Older than the incidents listed here' };
}
// Drop the incident target (48 calls it when the view toggle leaves Harness).
function hnGoClear(){ if(HN.go) HN.go = null; }
// Once per hnGo: bring the target into view (nearest edge only) and focus it without scrolling again.
function hnGoScroll(){
  const g = HN.go;
  if(!g || g.done || typeof document === 'undefined' || !document.querySelector) return;
  const el = document.querySelector('.hnw .hngo') || document.querySelector('.hnw .hngonote');
  if(!el) return;
  g.done = true;
  if(el.scrollIntoView) el.scrollIntoView({ block: 'nearest' });
  if(el.classList && el.classList.contains('hngo') && el.focus) el.focus({ preventScroll: true });
}
function hnReport(d){
  if(HN.go && HN.go.proj !== PLS.proj) HN.go = null;   // target belongs to the project it was opened from
  const R = hnRep(d), cp = hnCpKeys(R).indexOf(HN.cp) >= 0 ? HN.cp : '';   // ⚠a filter whose button is not shown (project/platform switch) is ignored
  const inc = R.inc.map((x, i) => [x, i, hnMs((x.pass && x.pass.ts) || (x.fail && x.fail.ts))]).sort((a, b) => b[2] - a[2] || a[1] - b[1]).map(a => a[0]);   // newest first
  const any = inc.length || HN_CPK.some(k => R.cp(k).runs), go = HN.go ? hnGoFind(R) : null;
  let cards = inc.filter(x => !cp || hnIncCp(x) === cp).map(x => hnInc(x, !!go && go.x === x)).join('') + HN_CPK.filter(k => !cp || k === cp).map(k => hnQuiet(R, k)).join('');
  if((!cp || cp === 'person') && typeof hnPerson === 'function') cards += hnPerson(R, cp);
  const old = cp && cp !== 'person' ? R.cp(cp).caught - R.cp(cp).listed : 0;   // person writes its own note
  if(old > 0) cards += '<div class=hidnote>' + esc(TV({msg: hnPl(old, '{n} older catch, not listed', '{n} older catches, not listed'), vars: {n: old}})) + '</div>';
  if(!any) cards = '<div class=hidnote>' + esc(T('No gate records yet — running scripts/check.sh adds them')) + '</div>';
  else if(!cards) cards = '<div class=hidnote>' + esc(T('Nothing recorded at this checkpoint')) + '</div>';
  if(go && go.note) cards = '<div class="hidnote hngonote">' + esc(T(go.note)) + '</div>' + cards;
  if(go && !HN.go.done) (typeof requestAnimationFrame === 'function' ? requestAnimationFrame : setTimeout)(hnGoScroll);   // after plPaint has put the HTML in place
  const since = hnWhen(R.since);
  return '<div class=hnrep><div class=brh2><b>' + esc(T('What the gates caught')) + '</b>' + (since ? ' <i>' + esc(TV({msg: 'since {d}', vars: {d: since}})) + '</i>' : '') + '</div>'
    + (typeof hnRuntime === 'function' ? hnRuntime(d) : '') + hnTiles(R) + hnStrip(R) + '<div class=hnrepc>' + cards + '</div></div>';
}
// Verdict counts as plain text for the «Config map» summary (buttons inside <summary> would toggle the fold).
function hnVdSum(c){
  if(!c || typeof c !== 'object') return '';
  const k = x => Number(c[x]) || 0;
  return ' <i>' + esc(T('Check results')) + ' ' + ['bad', 'check'].map(l => '<span class="hnvdq' + (k(l) ? ' hnvd-' + l : '') + '">' + esc(T(HN_VDL[l], 'verdict')) + ' ' + k(l) + '</span>').join(' · ')
    + ' · <span class=hnvdq>' + esc(T('ok')) + ' ' + k('ok') + '</span></i>';
}
// No stored choice (null): open while the check found problems, so the count has its list under it.
function hnCfgOpen(d){ return HN.cfgOpen == null ? (Number(d && d.verdict && d.verdict.bad) || 0) > 0 : HN.cfgOpen; }
// Body only: the pipeline tab owns the header, the view toggle and the project chips.
function hnHtml(){
  const proj = PLS.proj, d = HN.data[hnKey(proj)];
  hnLoad(proj, false);
  let body;
  if(!proj) body = '<div class=hidnote>' + esc(T('Pick a project')) + '</div>';
  else if(!d) body = '<div class=hidnote>' + esc(T('Loading…')) + '</div>';
  else if(d.ok === false) body = '<div class=hidnote>' + esc(T('Could not read the harness')) + (d.msg ? ' — ' + esc(hnMsg(d.msg)) : '') + '</div>';
  // Report (+ check-results line, its counts jump to the Tools «Config map»), then «How to read this» and raw «Gate runs», both closed by default.
  else body = hnReport(d) + hnVdLine(d.verdict) + hnReadHtml() + (typeof hnSelfcheck === 'function' ? hnSelfcheck(d) : '')   // 47f «Guard self-check»
    + '<details class="hnmore hnruns" data-hnmore=runs' + (HN.fold.runs ? ' open' : '') + '><summary><div class=brh2><b>' + esc(T('Gate runs')) + '</b></div></summary>'
    + hnRes(d.evidence, true) + '</details>';
  return '<div class=hnw>' + (proj ? hnPlatSwitch(HN.plats) : '') + body + '</div>';
}
const HN_READ = [['Caught (red→green)', 'a gate failed and a later run of the same gate passed: a defect found and fixed before it shipped'],
  ['Held', 'of those fixes, the ones whose gate still passes in later runs'],
  ['Broke again', 'the same check step failed again in a later run, or the fix commit was reverted; the card says which'],
  ['Found by a person first', 'ended runs of a bug-fix pipeline: a person reported the defect before any gate caught it'],
  ['What is guarding', 'where each catch happened: hooks before an edit, check --fast right after, check --full before a commit, or a person; click one to show only its cards'],
  ['Incident cards', 'one card per catch, newest first: red run → fix commits → green run → held or reverted']];
function hnReadHtml(){
  return '<details class="hnmore hnread" data-hnmore=read' + (HN.fold.read ? ' open' : '') + '><summary><div class=brh2><b>' + esc(T('How to read this')) + '</b></div></summary><ul class=hnrdl>'
    + HN_READ.map(([k, v]) => '<li><b>' + esc(T(k)) + '</b> — ' + esc(T(v)) + '</li>').join('') + '</ul></details>';
}
// Tools view (47 paintTools): the hook/rule/agent/MCP/skill map; ⚠only one .hnw exists at a time (#feed is shared), click handlers scope to it.
function hnCfgHtml(proj){
  if(typeof FEATS !== 'undefined' && FEATS.harness === false) return '';
  const d = proj ? HN.data[hnKey(proj)] : null;
  if(proj) hnLoad(proj, false);
  HN.cfgShown = hnCfgOpen(d);
  let body;
  if(!proj) body = '<div class=hidnote>' + esc(T('Pick a project in Pipelines')) + '</div>';
  else if(!d) body = '<div class=hidnote>' + esc(T('Loading…')) + '</div>';
  else if(d.ok === false) body = '<div class=hidnote>' + esc(T('Could not read the harness')) + (d.msg ? ' — ' + esc(hnMsg(d.msg)) : '') + '</div>';
  else body = hnPlatSwitch(HN.plats) + hnVdLine(d.verdict) + (d.scanning ? '<div class=hidnote>' + esc(T('Counting runs…')) + '</div>' : '')
    + '<details class=hnflow data-hnflow' + (HN.flowOpen ? ' open' : '') + '><summary>'
    + '<div class=brh2><b>' + esc(T('Hook flow')) + '</b> <i>' + esc(TV({msg: 'effects are estimates · counts = last {n} days', vars: {n: HN.days}})) + '</i></div>'
    + hnSum(d.events) + '</summary>' + hnLegend() + hnLaneHtml(d.events) + '</details>'
    + '<div class=hnbot><div class=hnbx><div class=brh2><b>' + esc(T('Rule files')) + '</b> <i>' + esc(T('load order')) + '</i></div>' + hnRules(d.rules) + '</div>'
    + '<div class=hnbx><div class=brh2><b>' + esc(T('Agents ↔ pipelines')) + '</b></div>' + hnAgents(d.agents) + '</div>'
    + hnToolBox(d.mcps, 'MCP servers', 'full') + (Array.isArray(d.skills) ? '<div class=hnbx><div class=brh2><b>' + esc(T('Skills')) + '</b></div>' + hnSkills(d.skills) + '</div>' : '') + '</div>'
    + (HN.plat === 'cc' ? hnCounts(d.counts) : '');   // the «Tools» list they jump to is Claude Code's
  // Project name as plain text: a button inside <summary> would toggle the fold.
  return '<div class="hnw hncfgw"><details class=hncfg' + (HN.cfgShown ? ' open' : '') + '><summary class=hncfgs><div class=brh2><b>' + esc(T('Config map')) + '</b>'
    + (proj ? ' <i class=hncfgp>' + esc(String(proj).split('/').pop()) + '</i>' : '') + (d && d.ok !== false ? hnVdSum(d.verdict) : '') + '</div></summary>' + body + '</details></div>';
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
  if(HN.go && e.target.closest('.hnw')){   // the highlight lasts until the next click in the view
    HN.go = null;
    const a = document.activeElement;   // ⚠focus inside .hnw pauses poll repaints: let go of the focused target card
    if(a && a.classList && a.classList.contains('hngo') && a.blur) a.blur();
  }
  const pb = e.target.closest('.hnw [data-hnplat]');
  if(pb){ if(pb.dataset.hnplat !== HN.plat) hnSetPlat(pb.dataset.hnplat); return; }
  const vg = e.target.closest('.hnw [data-hnvdgo]');
  if(vg){ hnVdGo(vg.dataset.hnvdgo === 'bad' ? 'bad' : 'check'); return; }
  const r = e.target.closest('.hnw [data-hnref]');
  if(r){ hnOpen(r.dataset.hnref, hnCardName(r)); return; }
  const cb = e.target.closest('.hnw [data-hncp]');   // checkpoint filter: in-memory choice + repaint, no fetch
  if(cb){
    const k = HN_CP[cb.dataset.hncp] ? cb.dataset.hncp : '';
    HN.cp = HN.cp === k ? '' : k;
    plPaint();
    const b = k && document.querySelector('.hnw [data-hncp="' + k + '"]');   // repaint replaced the button: keep keyboard focus, never scroll
    if(b) b.focus({ preventScroll: true });
    return;
  }
  const c = e.target.closest('[data-hntools]');
  if(!c || !c.closest('.hnw')) return;
  if(c.closest('.hncfgw')){ const g = document.querySelector('.tvwg'); if(g && g.scrollIntoView) g.scrollIntoView({ block: 'nearest' }); return; }   // already in Tools: the list sits below
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
  else if(e.target.classList.contains('hncfg')){ if(e.target.open === HN.cfgShown) return;   // ⚠the paint's own open fires toggle too: only a change is a choice
    HN.cfgOpen = HN.cfgShown = e.target.open; lsSet('sidereus.hncfg', e.target.open ? '1' : '0'); }
  else if(e.target.classList.contains('hnflow')){ HN.flowOpen = e.target.open; lsSet('sidereus.hnflow', e.target.open ? '1' : '0'); }
  else if(e.target.classList.contains('hnmore') && e.target.dataset) HN.fold[e.target.dataset.hnmore] = e.target.open;
}, true);
