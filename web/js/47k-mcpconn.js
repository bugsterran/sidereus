// «Connections» view of the pipeline tab (48 PLVIEW 'conn'): one live session at the centre, one node per MCP server it can load
// (GET /api/mcp-conn, sidereus/mcp_conn.py); side panel, actions and request log are 47l.
// ⚠Metadata only: server names, scope, state words, error codes, counts and times — never tool arguments, results or error text.
const MCPC = {sid: lsGet('sidereus.mcpcsid', ''), sel: '', filt: '', cloudOpen: false, act: {}, note: {}, data: null, err: '',
  busy: '', wh: [0, 0], drag: '', sending: false, msg: '', log: null, cp: '', failAt: {}};
const MCPC_LIVE_S = 900;   // a call this recent (server clock) draws flowing dots
const MCPC_BACKOFF_MS = 10000;   // ⚠after a failed load, repaints do not refetch (each paint calls loadMcpConn: a tight loop otherwise)
// Live strip: every CLI; ⚠ended rows ('done'/'gone') never come back from a stale pick.
function mcpcRows(){
  return (typeof SESS === 'object' && Array.isArray(SESS) ? SESS : []).filter(x => x && x.sid && x.state !== 'done' && x.state !== 'gone');
}
function mcpcRow(sid){ return mcpcRows().find(x => x.sid === sid) || null; }
// Edge width by this session's call count; null/0 (no count, e.g. pi) = hairline.
function mcpcEdgeW(n){
  const v = +n;
  return v > 0 && isFinite(v) ? Math.round(Math.min(6, 1.5 + Math.log2(v + 1)) * 100) / 100 : 1;
}
// ⚠Both times are server epoch seconds: the browser clock is not compared with the server's.
function mcpcLive(last, now){
  const l = +last, n = +now;
  return l > 0 && n > 0 && n - l <= MCPC_LIVE_S;
}
function mcpcStLbl(k){
  return k === 'ok' ? T('Connected', 'mcp') : k === 'fail' ? T('Failed', 'mcp') : k === 'auth' ? T('Login needed') : T('Unknown', 'mcp');
}
function mcpcStKey(k){ return k === 'ok' || k === 'fail' || k === 'auth' ? k : 'unknown'; }
// Relative time on the server clock; missing = '—' (never «0 s ago»).
function mcpcAgo(ts, now){
  const t = +ts, n = +now;
  if(!(t > 0) || !(n > 0)) return '—';
  return AGO(ago(Math.max(0, Math.floor(n - t))));
}
function mcpcSidOk(d, sid){ return !!(d && d.sid === sid); }
// Drops a late reply for an old pick; a failed refresh keeps the last good answer for the same session and says so.
async function loadMcpConn(sid, force){
  if(!sid) return;
  if(MCPC.busy === sid) return;
  if(!force && mcpcSidOk(MCPC.data, sid) && MCPC.data.ok) return;
  if(!force && Date.now() - (MCPC.failAt[sid] || 0) < MCPC_BACKOFF_MS) return;
  MCPC.busy = sid;
  let j = null, er = '';
  try{ j = await getJSON('/api/mcp-conn?sid=' + encodeURIComponent(sid), {timeout: 60000}); }
  catch(e){ er = fetchErrMsg(e); }
  if(MCPC.busy === sid) MCPC.busy = '';
  if(er || !(j && j.ok)) MCPC.failAt[sid] = Date.now(); else delete MCPC.failAt[sid];
  if(MCPC.sid !== sid) return;
  if(er){
    MCPC.err = er;
    if(!mcpcSidOk(MCPC.data, sid)) MCPC.data = null;
  } else {
    MCPC.err = '';
    MCPC.data = j && typeof j === 'object' ? Object.assign({}, j, {sid: j.sid || sid}) : {ok: false, sid};
  }
  mcpcRepaint();
  if(MCPC.data && MCPC.data.scanning) setTimeout(() => { if(mcpcShown() && MCPC.sid === sid) loadMcpConn(sid, true); }, 5000);
}
function mcpcShown(){ return typeof mainView !== 'undefined' && mainView === 'pipe' && typeof PLVIEW !== 'undefined' && PLVIEW === 'conn'; }
function mcpcRepaint(){
  if(!mcpcShown()) return;
  const box = document.getElementById('feed');
  if(box) paintMcpConn(box);
}
function mcpcPick(sid){
  if(!sid || sid === MCPC.sid) return;
  MCPC.sid = sid; MCPC.sel = ''; MCPC.filt = ''; MCPC.cloudOpen = false; MCPC.msg = ''; MCPC.err = '';
  if(!mcpcSidOk(MCPC.data, sid)) MCPC.data = null;
  lsSet('sidereus.mcpcsid', sid);
}
// Ring layout: configured servers on the inner ring (+ one claude.ai fold node), connectors on the outer ring when open.
function mcpcSplit(servers){
  const all = Array.isArray(servers) ? servers.filter(s => s && typeof s.name === 'string' && s.name) : [];
  return {local: all.filter(s => s.scope !== 'cloud'), cloud: all.filter(s => s.scope === 'cloud')};
}
function mcpcClamp(v, lo, hi){ return hi < lo ? (lo + hi) / 2 : Math.max(lo, Math.min(hi, v)); }
// ⚠Positions are clamped inside the stage: an outer-ring label past the edge widened the page at 900px.
function mcpcGeo(W, H, nIn, nOut){
  const cx = W / 2, cy = H / 2, half = W < 860 ? 60 : 68;
  const R = Math.min(W * 0.34, 300), RY = Math.min(H * 0.34, 210), R2 = Math.min(W * 0.46, 430), R2Y = Math.min(H * 0.45, 270);
  const at = (i, n, rx, ry, off, hw) => {
    const a = -Math.PI / 2 + (i + off) * 2 * Math.PI / Math.max(1, n);
    return {a, x: mcpcClamp(cx + Math.cos(a) * rx, hw + 4, W - hw - 4), y: mcpcClamp(cy + Math.sin(a) * ry, 22, H - 44)};
  };
  return {cx, cy, inner: Array.from({length: nIn}, (_, i) => at(i, nIn, R, RY, 0, half)),
    outer: Array.from({length: nOut}, (_, i) => at(i, nOut, R2, R2Y, 0.5, 50))};
}
function mcpcPath(x, y, cx, cy, a){
  const r = v => Math.round(v * 10) / 10;
  return 'M' + r(x) + ' ' + r(y) + ' Q ' + r((x + cx) / 2 + Math.sin(a) * 26) + ' ' + r((y + cy) / 2 - Math.cos(a) * 26) + ' ' + r(cx) + ' ' + r(cy);
}
// One edge; a live one gets a dotted overlay animated in CSS (41c .mcpcfl), so prefers-reduced-motion can stop it.
function mcpcEdge(s, p, g, now, dim, outer){
  const st = mcpcStKey(s.state), n = +s.n > 0 ? +s.n : 0;
  if(outer && !n && st !== 'fail') return '';
  const d = mcpcPath(p.x, p.y, g.cx, g.cy, p.a);
  const cls = 'mcpce st-' + st + (n ? ' used' : '') + (dim ? ' dim' : '') + (outer ? ' out' : '');
  return '<path class="' + cls + '" d="' + d + '" stroke-width="' + mcpcEdgeW(n) + '"/>'
    + (mcpcLive(s.last, now) && !dim ? '<path class=mcpcfl d="' + d + '" pathLength="100"/>' : '');
}
function mcpcNodeUse(s, d, now){
  const st = mcpcStKey(s.state);
  if(st === 'fail') return '<span class=mcpcbad>' + esc(s.err || 'FAIL') + '</span>';
  if(d.counts !== false && +s.n > 0) return esc(T('{n} calls').replace('{n}', String(+s.n))) + ' · ' + esc(mcpcAgo(s.last, now));
  return esc(mcpcStLbl(st));
}
function mcpcNode(s, p, d, now, small){
  const st = mcpcStKey(s.state), used = d.counts !== false && +s.n > 0, sel = MCPC.sel === s.name, dim = !!MCPC.filt && MCPC.filt !== st;
  const tip = s.name + ' — ' + mcpcStLbl(st) + (s.err ? ' (' + s.err + ')' : '')
    + (d.counts !== false && s.n != null ? ' · ' + T('{n} calls').replace('{n}', String(+s.n || 0)) : '');
  return '<button type=button class="mcpcn st-' + st + (used ? ' used' : '') + (sel ? ' sel' : '') + (small ? ' small' : '') + (dim ? ' dim' : '')
    + '" data-mcpcn="' + esc(s.name) + '" draggable="true" aria-pressed="' + sel + '" style="left:' + Math.round(p.x) + 'px;top:' + Math.round(p.y) + 'px"'
    + ' title="' + esc(tip) + '"><span class=mcpcb><i></i></span><span class=mcpct>' + esc(s.name) + '</span><span class=mcpcu>'
    + mcpcNodeUse(s, d, now) + '</span></button>';
}
function mcpcFold(cloud, p){
  const nA = cloud.filter(s => mcpcStKey(s.state) === 'auth').length, nOk = cloud.filter(s => mcpcStKey(s.state) === 'ok').length;
  const dim = !!MCPC.filt && !cloud.some(s => mcpcStKey(s.state) === MCPC.filt);
  return '<button type=button class="mcpcn mcpccl' + (MCPC.cloudOpen ? ' open' : '') + (dim ? ' dim' : '') + '" data-mcpcc aria-expanded="' + MCPC.cloudOpen
    + '" style="left:' + Math.round(p.x) + 'px;top:' + Math.round(p.y) + 'px" title="' + esc(T(MCPC.cloudOpen ? 'Collapse' : 'Expand to the outer ring'))
    + '"><span class=mcpcb>' + cloud.length + '</span><span class=mcpct>' + esc(T('claude.ai connectors')) + '</span><span class=mcpcu>'
    + esc(T('{a} connected · {b} login needed').replace('{a}', String(nOk)).replace('{b}', String(nA))) + '</span></button>';
}
function mcpcFoldEdge(cloud, p, g, now){
  const n = cloud.reduce((a, s) => a + (+s.n > 0 ? +s.n : 0), 0), live = cloud.some(s => mcpcLive(s.last, now));
  const d = mcpcPath(p.x, p.y, g.cx, g.cy, p.a);
  return '<path class="mcpce st-cl' + (n ? ' used' : '') + '" d="' + d + '" stroke-width="' + mcpcEdgeW(n) + '"/>'
    + (live ? '<path class=mcpcfl d="' + d + '" pathLength="100"/>' : '');
}
function mcpcStrip(rows){
  return '<div class=mcpcstrip role=group aria-label="' + esc(T('Live sessions')) + '">' + rows.map(x => {
    const on = x.sid === MCPC.sid, w = x.state === 'wait' || x.blocked ? 'wait' : (x.state === 'think' || x.state === 'tool' || x.state === 'run') ? 'run' : 'idle';
    const lb = typeof sessLabel === 'function' ? sessLabel(x) : String(x.state || '');
    return '<button type=button class="mcpcss' + (on ? ' on' : '') + '" data-mcpcs="' + esc(x.sid) + '" aria-pressed="' + on + '" title="' + esc(x.cwd || x.project || '') + '">'
      + '<span class=mcpcsh><i class="mcpcsd ' + w + '"></i>' + (typeof aiLogo === 'function' ? aiLogo(x.plat) : '') + '<b>' + esc(x.project || sid8(x.sid)) + '</b></span>'
      + '<span class=mcpcsm>' + esc(sid8(x.sid)) + ' · ' + esc(lb) + '</span></button>';
  }).join('') + '</div>';
}
function mcpcCore(row, d, g){
  const pl = typeof platName === 'function' ? platName(row.plat) : String(row.plat || '');
  const sum = mcpcCoreSum(d);
  return '<div class=mcpccore data-mcpccore style="left:' + Math.round(g.cx) + 'px;top:' + Math.round(g.cy) + 'px" title="' + esc(T('Drop a node here to draft a task')) + '">'
    + '<b>' + esc(row.project || sid8(row.sid)) + '</b><span>' + esc(pl) + ' · ' + esc(sid8(row.sid)) + '</span>'
    + (row.model ? '<span>' + esc(row.model) + '</span>' : '')
    + (sum ? '<em>' + esc(sum) + '</em>' : '') + '</div>';
}
// Core subtitle. ⚠No counts (pi) or every server unknown = «Unknown n», never «0 connected · 0 failed».
function mcpcCoreSum(d){
  if(!d || !d.ok || d.supported === false || typeof mcpcTotals !== 'function') return '';
  const tot = mcpcTotals(d), all = (d.servers || []).filter(s => s && s.name).length;
  if(!all) return '';
  if(d.counts === false || tot.unknown >= all) return T('{n} unknown').replace('{n}', String(tot.unknown));
  return T('{a} connected · {b} failed').replace('{a}', String(tot.ok)).replace('{b}', String(tot.fail));
}
function mcpcLegend(){
  const k = (c, t) => '<span><i class="mcpclk ' + c + '"></i>' + esc(t) + '</span>';
  return '<div class=mcpcleg>' + k('st-ok', T('Connected', 'mcp')) + k('st-ok used', T('Called by this session (larger · thicker edge)'))
    + k('st-fail', T('Failed', 'mcp')) + k('st-auth', T('Login needed')) + k('st-unknown', T('Unknown', 'mcp'))
    + '<span class=mcpclf>' + esc(T('Flowing dots = a call in the last 15 min')) + '</span><span>' + esc(T('Edge width = calls by this session')) + '</span></div>';
}
// Stage: SVG edges under absolutely placed <button> nodes, positions in stage pixels (measured; 41c fixes the height).
function mcpcStage(row, d, W, H){
  const g0 = {cx: W / 2, cy: H / 2};
  let msg = '';
  if(!d) msg = MCPC.err ? T('Could not read MCP connections') + ' — ' + MCPC.err : T('Loading…');
  else if(!d.ok) msg = (typeof TV === 'function' && d.msg ? TV(d) : '') || T('Could not read MCP connections');
  else if(d.supported === false) msg = T('MCP connections are not read for this CLI yet');
  if(msg) return '<div class=mcpcst><svg class=mcpcsky viewBox="0 0 ' + W + ' ' + H + '" aria-hidden=true></svg>' + mcpcCore(row, d, g0)
    + '<div class=mcpcmsg>' + esc(msg) + '</div></div>';
  const now = +d.now || 0, sp = mcpcSplit(d.servers), fold = sp.cloud.length > 0;
  const g = mcpcGeo(W, H, sp.local.length + (fold ? 1 : 0), MCPC.cloudOpen ? sp.cloud.length : 0);
  let edges = '', nodes = '';
  sp.local.forEach((s, i) => {
    const dim = !!MCPC.filt && MCPC.filt !== mcpcStKey(s.state);
    edges += mcpcEdge(s, g.inner[i], g, now, dim, false); nodes += mcpcNode(s, g.inner[i], d, now, false);
  });
  if(fold){ const p = g.inner[sp.local.length]; edges += mcpcFoldEdge(sp.cloud, p, g, now); nodes += mcpcFold(sp.cloud, p); }
  if(MCPC.cloudOpen) sp.cloud.forEach((s, i) => {
    const dim = !!MCPC.filt && MCPC.filt !== mcpcStKey(s.state);
    edges += mcpcEdge(s, g.outer[i], g, now, dim, true); nodes += mcpcNode(s, g.outer[i], d, now, true);
  });
  const empty = !sp.local.length && !fold ? '<div class=mcpcmsg>' + esc(T('No MCP server is configured for this session')) + '</div>' : '';
  return '<div class=mcpcst role=group aria-label="' + esc(T('MCP servers of this session')) + '"><svg class=mcpcsky viewBox="0 0 ' + W + ' ' + H + '" aria-hidden=true>'
    + edges + '</svg>' + mcpcCore(row, d, g) + nodes + empty + '</div>';
}
// Stage size: the stage drawn last time, else the feed minus the side column; the repaint after layout corrects it once.
function mcpcSize(box){
  const st = box.querySelector && box.querySelector('.mcpc .mcpcst');
  if(st && st.clientWidth > 0) return [st.clientWidth, st.clientHeight || 600];
  const w = box.clientWidth || 1200;
  return [Math.max(320, w > 1500 ? w - 434 : w > 1100 ? w - 374 : w - 2), w > 860 ? 620 : 520];   // same breakpoints as 41c
}
function paintMcpConn(box){
  const rows = mcpcRows();
  if(!rows.length){ box.innerHTML = '<div class=mcpc><div class=hidnote>' + esc(T('No live session')) + '</div></div>'; return; }
  if(!rows.some(x => x.sid === MCPC.sid)) mcpcPick(rows[0].sid);
  const row = mcpcRow(MCPC.sid), d = mcpcSidOk(MCPC.data, MCPC.sid) ? MCPC.data : null;
  if(MCPC.sel && !(d && d.ok && (d.servers || []).some(s => s && s.name === MCPC.sel))) MCPC.sel = d ? '' : MCPC.sel;
  loadMcpConn(MCPC.sid, false);
  const [W, H] = mcpcSize(box);
  MCPC.wh = [W, H];
  const h = mcpcStrip(rows)
    + (d && d.scanning ? '<div class=hidnote>' + esc(T('Reading records…')) + '</div>' : '')
    + (d && MCPC.err ? '<div class=hidnote>' + esc(T('Could not refresh — showing the last answer')) + ' (' + esc(MCPC.err) + ')</div>' : '')
    + '<div class=mcpcg><div class=mcpcl>' + mcpcStage(row, d, W, H) + mcpcLegend() + '</div>'
    + '<div class=mcpcside>' + (typeof mcpcSideHtml === 'function' ? mcpcSideHtml(d, row) : '') + '</div></div>';
  const root = box.firstElementChild;
  // ⚠#feed is shared with Pipelines/Tools (they write innerHTML): morph only inside our own root, never setHtml(box).
  if(root && root.classList && root.classList.contains('mcpc') && box.children.length === 1) morphHtml(root, h);
  else { box.innerHTML = '<div class=mcpc></div>'; morphHtml(box.firstElementChild, h); }
  const st = box.querySelector('.mcpc .mcpcst');
  if(st && st.clientWidth > 0 && (Math.abs(st.clientWidth - W) > 2 || Math.abs(st.clientHeight - H) > 2)) requestAnimationFrame(mcpcRepaint);
}
// Poll while visible (the pipeline tab's state poll repaints too, 48b plPoll; this keeps a 15-min live window honest).
if(typeof setInterval === 'function') setInterval(() => { if(mcpcShown() && !(typeof document !== 'undefined' && document.hidden)) loadMcpConn(MCPC.sid, true); }, 20000);
let MCPC_RZ = 0;
if(typeof window !== 'undefined' && window.addEventListener) window.addEventListener('resize', () => {
  if(MCPC_RZ || !mcpcShown()) return;
  MCPC_RZ = requestAnimationFrame(() => { MCPC_RZ = 0; mcpcRepaint(); });
});
if(typeof document !== 'undefined' && document.addEventListener){
  document.addEventListener('click', e => {
    const t = e.target, root = t && t.closest && t.closest('.mcpc');
    if(!root) return;
    const s = t.closest('[data-mcpcs]');
    if(s){ const had = document.activeElement === s; mcpcPick(s.dataset.mcpcs); mcpcRepaint(); if(had) kbHold('.mcpc .mcpcss.on'); return; }
    if(t.closest('[data-mcpcc]')){ MCPC.cloudOpen = !MCPC.cloudOpen; mcpcRepaint(); kbHold('.mcpc [data-mcpcc]'); return; }
    const n = t.closest('[data-mcpcn]');
    if(n){ MCPC.sel = MCPC.sel === n.dataset.mcpcn ? '' : n.dataset.mcpcn; MCPC.msg = ''; mcpcRepaint(); return; }
  });
  // Drag a node onto the centre = «Task» draft for that server (keyboard path: click the node, then «Task»).
  document.addEventListener('dragstart', e => {
    const n = e.target && e.target.closest && e.target.closest('.mcpc [data-mcpcn]');
    if(!n) return;
    MCPC.drag = n.dataset.mcpcn;
    try{ e.dataTransfer.setData('text/plain', MCPC.drag); e.dataTransfer.effectAllowed = 'copy'; }catch(x){ softErr('mcpc-drag', x); }
    const c = document.querySelector('.mcpc .mcpccore'); if(c) c.classList.add('can');
  });
  document.addEventListener('dragend', () => {
    MCPC.drag = '';
    const c = document.querySelector('.mcpc .mcpccore'); if(c) c.classList.remove('can', 'over');
  });
  document.addEventListener('dragover', e => {
    const c = MCPC.drag && e.target && e.target.closest && e.target.closest('.mcpc .mcpccore');
    if(!c) return;
    e.preventDefault(); c.classList.add('over');
  });
  document.addEventListener('dragleave', e => { const c = e.target && e.target.closest && e.target.closest('.mcpc .mcpccore'); if(c) c.classList.remove('over'); });
  document.addEventListener('drop', e => {
    const c = MCPC.drag && e.target && e.target.closest && e.target.closest('.mcpc .mcpccore');
    if(!c) return;
    e.preventDefault();
    const name = MCPC.drag; MCPC.drag = '';
    MCPC.sel = name;
    if(typeof mcpcDropTask === 'function') mcpcDropTask(name);
    mcpcRepaint();
    const i = document.querySelector('.mcpc .mcpcnote'); if(i) i.focus({preventScroll: true});
  });
}
