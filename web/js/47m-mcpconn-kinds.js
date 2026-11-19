// «Connections» kind chips Skills / Agents / Hooks (47k chip row): the same orbit engine (mcpcGeo + mcpcGrowH) draws one node
// per item this session can load, from the `kinds` block of GET /api/mcp-conn (sidereus/mcp_conn.py). Side cards, «Task» only.
// ⚠Rule 1: names, scope, abbreviated path, matcher, hook names, counts and times only — never a hook command, its output or file text.
// ⚠Rule 7: the only action is «Task»; text leaves through 47l mcpcSend after «Confirm — send». No Reconnect/Restart/Diagnose here.
function mcpcKindBlock(d, k){
  const b = d && d.ok && d.kinds && typeof d.kinds === 'object' ? d.kinds[k] : null;
  return b && typeof b === 'object' && b.supported !== false && Array.isArray(b.items) ? b : null;
}
function mcpcKindItems(d, k){
  const b = mcpcKindBlock(d, k);
  return b ? b.items.filter(x => x && typeof x.name === 'string' && x.name) : [];
}
function mcpcKindFind(d, k, name){ return name ? mcpcKindItems(d, k).find(x => x.name === name) || null : null; }
// n: number = counted (0 = not used); missing = not recorded (⚠unknown is not «Not used»).
function mcpcKindSt(it){ return it.n == null ? 'st-unknown' : +it.n > 0 ? 'st-used' : 'st-unused'; }
function mcpcKindName(k, it){ return k === 'skill' && it.kind === 'cmd' ? '/' + it.name : it.name; }
function mcpcKindUse(k, it, now){
  if(it.n == null) return T('not recorded');
  if(!(+it.n > 0)) return T('Not used');
  return T(k === 'hook' ? '{n} runs' : '{n} calls').replace('{n}', String(+it.n)) + ' · ' + mcpcAgo(it.last, now);
}
// Node label: a plugin item drops its «plugin:» prefix (every node of one plugin read the same once cut; the title and
// the detail card keep the full name), and long labels step the font down (41c .mcpct.l1..l3) instead of being cut.
function mcpcKindLabel(k, it){
  let s = mcpcKindName(k, it);
  const pre = it.plug ? String(it.plug) + ':' : '';
  if(pre && s.replace(/^\//, '').indexOf(pre) === 0) s = (s[0] === '/' ? '/' : '') + s.replace(/^\//, '').slice(pre.length);
  return mcpcLabelHtml(s);
}
function mcpcKindDim(it){ return !!MCPC.filt && 'st-' + MCPC.filt !== mcpcKindSt(it); }
function mcpcKindNode(k, it, p, now){
  const st = mcpcKindSt(it), sel = MCPC.sel === it.name, dim = mcpcKindDim(it), use = mcpcKindUse(k, it, now);
  return '<button type=button class="mcpcn kind ' + st + (st === 'st-used' ? ' used' : '') + (sel ? ' sel' : '') + (dim ? ' dim' : '')
    + '" data-mcpcn="' + esc(it.name) + '" draggable="true" aria-pressed="' + sel + '" style="left:' + Math.round(p.x) + 'px;top:' + Math.round(p.y) + 'px"'
    + ' title="' + esc(mcpcKindName(k, it) + ' — ' + mcpcScopeLbl(it.scope) + ' · ' + use) + '"><span class=mcpcb><i></i></span>' + mcpcKindLabel(k, it) + '<span class=mcpcu>' + esc(use) + '</span></button>';
}
function mcpcKindEdge(it, p, g, now){
  const st = mcpcKindSt(it), n = +it.n > 0 ? +it.n : 0, dim = mcpcKindDim(it), d = mcpcPath(p.x, p.y, g.cx, g.cy, p.a);
  return '<path class="mcpce ' + st + (n ? ' used' : '') + (dim ? ' dim' : '') + '" d="' + d + '" stroke-width="' + mcpcEdgeW(n) + '"/>'
    + (mcpcLive(it.last, now) && !dim ? '<path class=mcpcfl d="' + d + '" pathLength="100"/>' : '');
}
function mcpcKindEmpty(k){
  return k === 'skill' ? T('No skill or slash command this session can load') : k === 'agent' ? T('No agent this session can load')
    : T('No hook is configured for this session');
}
// Stage for a non-MCP kind; d is a loaded answer (47k mcpcStage handles loading and errors). Display order is the server's
// (scope, plugin, name), so nodes do not jump when counts change on a poll.
function mcpcKindStage(row, d, W, H, k){
  const hs = ' style="height:' + Math.round(H) + 'px"', b = mcpcKindBlock(d, k), items = mcpcKindItems(d, k);
  const sky = '<svg class=mcpcsky viewBox="0 0 ' + W + ' ' + H + '" aria-hidden=true>';
  if(!b || !items.length) return '<div class=mcpcst' + hs + '>' + sky + '</svg>' + mcpcCore(row, d, {cx: W / 2, cy: H / 2})
    + '<div class=mcpcmsg>' + esc(b ? mcpcKindEmpty(k) : T('Not read for this CLI yet')) + '</div></div>';
  const now = +d.now || 0, g = mcpcGeo(W, H, items.length, 0, true);
  let edges = '', nodes = '';
  items.forEach((it, i) => {
    const p = g.inner[i];
    if(!p) return;   // ⚠mcpcGrowH caps the height: a node without a cell is skipped, never drawn at undefined
    edges += mcpcKindEdge(it, p, g, now); nodes += mcpcKindNode(k, it, p, now);
  });
  const more = +b.more > 0 ? '<div class=mcpcmore>' + esc(T('{n} more not drawn (the {m} most used are shown)').replace('{n}', String(+b.more)).replace('{m}', String(items.length))) + '</div>' : '';
  return '<div class=mcpcst' + hs + ' role=group aria-label="' + esc(mcpcKindLbl(k)) + '">' + sky + edges + '</svg>' + mcpcCore(row, d, g) + nodes + '</div>' + more;
}
// Core subtitle; ⚠unsupported = no line, never «0 used».
function mcpcKindSum(d, k){
  if(!mcpcKindBlock(d, k)) return '';
  const it = mcpcKindItems(d, k), u = it.filter(x => +x.n > 0).length;
  return it.length ? T('{a} used · {b} unused').replace('{a}', String(u)).replace('{b}', String(it.filter(x => x.n != null && !(+x.n > 0)).length)) : '';
}
function mcpcKindLegend(k){
  const c = (cls, t) => '<span><i class="mcpclk ' + cls + '"></i>' + esc(t) + '</span>';
  return '<div class=mcpcleg>' + c('st-used used', T('Used by this session')) + c('st-unused', T('Not used by this session (dimmed)'))
    + '<span class=mcpclf>' + esc(T('Flowing dots = used in the last 15 min')) + '</span><span>'
    + esc(T(k === 'hook' ? 'Edge width = runs by this session' : 'Edge width = calls by this session')) + '</span></div>';
}
// English wire text: fixed template + item name + the person's note. ⚠No counts, scope or path. Pure — preview and send both call it.
function mcpcKindBody(k, it, note){
  const name = String(typeof it === 'string' ? it : (it && it.name) || ''), n = mcpcNote(note) || '(one-line request needed)';
  if(k === 'skill') return (it && it.kind === 'cmd' ? 'Use the /' + name + ' command for this: ' : 'Use the ' + name + ' skill for this: ') + n;
  if(k === 'agent') return 'Use the ' + name + ' agent for this: ' + n;
  if(k === 'hook') return 'About the ' + name + ' hooks: ' + n;
  return '';
}
function mcpcKindTiles(d, k){
  const b = mcpcKindBlock(d, k), it = mcpcKindItems(d, k);
  const cnt = {used: it.filter(x => +x.n > 0).length, unused: it.filter(x => x.n != null && !(+x.n > 0)).length};
  const tiles = '<div class="mcpctiles two">' + ['used', 'unused'].map(f => '<button type=button class="mcpctile st-' + f + (MCPC.filt === f ? ' on' : '')
    + '" data-mcpcf="' + f + '" aria-pressed="' + (MCPC.filt === f) + '"' + (b ? '' : ' disabled') + '><b>' + (b ? String(cnt[f]) : '—') + '</b><span>'
    + esc(f === 'used' ? T('Used by this session') : T('Not used by this session')) + '</span></button>').join('') + '</div>';
  return mcpcCard(mcpcKindLbl(k), b && +b.more > 0 ? T('+{n} not drawn').replace('{n}', String(+b.more)) : '', tiles);
}
function mcpcKindBars(rows, now, sel){
  const mx = Math.max(1, ...rows.map(x => +x.n));
  return '<div class=mcpcbars>' + rows.map(x => '<button type=button class="mcpcbar' + (sel === x.name ? ' on' : '') + '"' + (x.key ? ' data-mcpcn="' + esc(x.key) + '"' : '')
    + '><span class=mcpcbn title="' + esc(x.label) + '">' + esc(x.label) + '</span><span class=mcpcbr><i style="width:' + Math.max(2, x.n / mx * 100).toFixed(1) + '%"></i></span>'
    + '<span class=mcpcbc>' + String(+x.n) + ' · ' + esc(mcpcAgo(x.last, now)) + '</span></button>').join('') + '</div>';
}
function mcpcKindCalls(d, k){
  const em = s => '<div class=mcpcempty>' + esc(s) + '</div>', b = mcpcKindBlock(d, k), now = +d.now || 0;
  const us = mcpcKindItems(d, k).filter(x => +x.n > 0).sort((a, z) => z.n - a.n)
    .map(x => ({key: x.name, label: mcpcKindName(k, x), n: +x.n, last: x.last}));
  const body = !b ? em(T('Not read for this CLI yet')) : us.length ? mcpcKindBars(us, now, MCPC.sel) : em(T('None yet'));
  return mcpcCard(T(k === 'hook' ? 'Run by this session' : 'Called by this session'), T(k === 'hook' ? 'runs · last' : 'calls · last'), body);
}
function mcpcKindDraft(row, k, it){
  const key = k + ':' + it.name, raw = MCPC.note[key] || '', n = mcpcNote(raw), inbox = !!(row && typeof mboxIn === 'function' && mboxIn(row));
  const can = inbox && !MCPC.sending && !!n, ph = esc(T('One-line request (required)'));
  const why = !inbox ? T('This session is not logged in to the mailbox — nothing can be sent') : !n ? T('Write the one-line request first') : '';
  return '<input class=mcpcnote data-mcpcnote="' + esc(key) + '" maxlength=200 spellcheck=false autocomplete=off value="' + esc(raw) + '" placeholder="' + ph + '" aria-label="' + ph + '">'
    + '<div class=mcpcto>' + esc(T('To')) + ' <b>' + esc(inbox ? row.mbox : '—') + '</b> · ' + esc((row && row.project) || '') + ' · ' + esc(sid8(row && row.sid)) + '</div>'
    + '<pre class=mcpcpv>' + esc(mcpcKindBody(k, it, n)) + '</pre>'
    + (why ? '<div class=mcpcwhy>' + esc(why) + '</div>' : '')
    + '<div class=mcpcgo><button type=button class="wkrgb archok" data-mcpcgo' + (can ? '' : ' disabled') + '>' + esc(MCPC.sending ? T('Sending…') : T('Confirm — send')) + '</button></div>'
    + (MCPC.msg ? '<div class="mcpcwhy err">' + esc(MCPC.msg) + '</div>' : '');
}
// Hook detail: configured files (scope · path · matcher) and this session's runs per hook name. ⚠Only those fields are read.
function mcpcKindHookRows(it, now){
  const fs = (Array.isArray(it.files) ? it.files : []).filter(f => f && typeof f === 'object');
  const fl = fs.length ? '<div class=mcpcflist>' + fs.map(f => '<div><code>' + esc(String(f.path || '—')) + '</code> · ' + esc(mcpcScopeLbl(f.scope))
    + (f.matcher ? ' · ' + esc(T('Matcher')) + ' <code>' + esc(String(f.matcher)) + '</code>' : '') + '</div>').join('') + '</div>' : esc(String(it.path || '—'));
  const subs = (Array.isArray(it.subs) ? it.subs : []).filter(s => s && typeof s.name === 'string' && +s.n > 0)
    .map(s => ({key: '', label: s.name, n: +s.n, last: s.last})).sort((a, z) => z.n - a.n);
  return {files: fl, runs: subs.length ? mcpcKindBars(subs, now, '') : '<div class=mcpcempty>' + esc(T('None yet')) + '</div>'};
}
function mcpcKindDetail(d, row, k){
  const it = MCPC.sel ? mcpcKindFind(d, k, MCPC.sel) : null;
  if(!it) return mcpcCard(mcpcKindLbl(k), '', '<div class=mcpcempty>' + esc(T('Click a node for its scope, file and counts; drag it onto the session to draft a task.')) + '</div>', 'mcpcdet');
  const now = +d.now || 0, r = (l, v) => '<div class=mcpcr><span>' + esc(l) + '</span><span>' + v + '</span></div>';
  const scope = esc(mcpcScopeLbl(it.scope)) + (it.plug ? ' · ' + esc(String(it.plug)) : '');
  let body = r(T('Scope'), scope);
  if(k === 'hook'){ const h = mcpcKindHookRows(it, now); body += r(T('Files'), h.files) + r(T('This session'), esc(mcpcKindUse(k, it, now))) + r(T('Run by this session'), h.runs); }
  else body += r(T('File'), it.path ? '<code>' + esc(String(it.path)) + '</code>' : '—') + r(T('This session'), esc(mcpcKindUse(k, it, now)))
    + (k === 'skill' && it.kind === 'cmd' ? r(T('Slash command'), '<code>/' + esc(it.name) + '</code>') : '');
  body += '<div class=mcpcacts role=group aria-label="' + esc(T('Actions')) + '"><button type=button class="mcpcbtn on" data-mcpcka="task" aria-pressed="true">' + esc(T('Task')) + '</button></div>'
    + '<div class=mcpcab>' + mcpcKindDraft(row, k, it) + '</div>';
  return mcpcCard(mcpcKindName(k, it), mcpcScopeLbl(it.scope), body, 'mcpcdet');
}
function mcpcKindSide(d, row, k){
  if(!(d && d.ok)) return mcpcCard(mcpcKindLbl(k), '', '<div class=mcpcempty>—</div>');
  return mcpcKindTiles(d, k) + mcpcKindCalls(d, k) + mcpcKindDetail(d, row, k);
}
