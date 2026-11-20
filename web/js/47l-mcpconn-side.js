// Side column of the «Session tools» view (47k): state tiles (click = filter), this session's calls, server detail with
// [Task][Diagnose][Restart][Reconnect], request log.
// ⚠Rule 7: composed text leaves only through «Confirm — send» (mcpcSend); «Reconnect» shows steps + Copy and sends nothing.
// ⚠Rule 1: the wire text carries the server name and the person's one-line note only — no state, error code, count or scope.
const MCPC_SENDS = ['task', 'diag', 'restart'];
const MCPC_LOG_KEY = 'sidereus.mcpclog', MCPC_LOG_MAX = 20;
function mcpcActLbl(a, st){
  return a === 'task' ? T('Task') : a === 'diag' ? T('Diagnose') : a === 'restart' ? T('Restart', 'mcp') : st === 'auth' ? T('Login steps') : T('Reconnect');
}
// Actions a node offers: a failed or logged-out server cannot do work; a claude.ai connector has no process to restart.
function mcpcActs(srv){
  const st = mcpcStKey(srv && srv.state), cl = !!(srv && srv.scope === 'cloud'), out = [];
  if(st !== 'fail' && st !== 'auth') out.push('task');
  if(st !== 'auth') out.push('diag');
  if(!cl && st !== 'auth') out.push('restart');
  out.push('reconn');
  return out;
}
function mcpcActOf(srv){
  const acts = mcpcActs(srv), cur = MCPC.act[srv.name], st = mcpcStKey(srv.state);
  return acts.includes(cur) ? cur : st === 'fail' ? 'diag' : st === 'auth' ? 'reconn' : acts[0];
}
function mcpcDropTask(name){
  if(mcpcKindOf(MCPC.data) !== 'mcp') return;   // kind items offer «Task» only; ⚠a same-named MCP server keeps its own action
  const d = MCPC.data, srv = d && d.ok ? (d.servers || []).find(s => s && s.name === name) : null;
  if(srv && mcpcActs(srv).includes('task')) MCPC.act[name] = 'task';
}
// One line, at most 200 chars (same cap as a to-do label).
function mcpcNote(v){ return String(v == null ? '' : v).replace(/\s+/g, ' ').trim().slice(0, 200); }
function mcpcPlat(p){ return p === 'codex' ? 'cx' : String(p || ''); }
// The session's own status command (fixed text + server name). ⚠Sidereus never runs it; the session does, with its own permissions.
// ⚠Command form only for a plain name: anything else could read as shell syntax in the session, so it gets the generic wording.
function mcpcStatusCmd(plat, name){
  const p = mcpcPlat(plat);
  if(!/^[A-Za-z0-9_.-]+$/.test(String(name || ''))) return '';
  return p === 'cc' ? 'claude mcp get ' + name : p === 'cx' ? 'codex mcp list' : p === 'pi' ? 'pi mcp list' : '';
}
// English wire text: fixed template + server name + optional note. Pure — the preview and the send both call it.
function mcpcBody(act, srv, row, note){
  const name = String(typeof srv === 'string' ? srv : (srv && srv.name) || ''), n = mcpcNote(note), cmd = mcpcStatusCmd(row && row.plat, name);
  const how = cmd ? ' with `' + cmd + '`' : " with your CLI's MCP status command";
  const tail = n ? '\nNote: ' + n : '';
  if(act === 'task') return 'Use the ' + name + ' MCP server for this: ' + (n || '(one-line request needed)');
  if(act === 'diag') return 'Please diagnose the ' + name + ' MCP server: check its connection state and error code' + how
    + ', give the cause in one line and how to fix it. Do not change any config; report only.' + tail;
  if(act === 'restart') return 'Please restart the ' + name + ' MCP server (its backend process or container): find how the config launches it, restart it, check it'
    + how + ' and report the result. When done, tell the person this session needs an MCP reconnect.' + tail;
  return '';
}
// «Reconnect» steps per CLI; t is an English template ({s} = server, {c} = command), shown through T(). Sends nothing.
function mcpcSteps(plat, srv, state){
  const name = String(typeof srv === 'string' ? srv : (srv && srv.name) || ''), p = mcpcPlat(plat);
  if(state === 'auth') return {steps: [{t: 'claude.ai Settings › Connectors › {s} › Connect'}, {t: 'In that session run {c} › {s} › Authenticate', c: '/mcp'}], copy: '/mcp'};
  if(p === 'cc') return {steps: [{t: "In that session's terminal run {c}", c: '/mcp'}, {t: 'Pick {s} › Reconnect'}, {t: 'If it fails again, use «Diagnose»'}], copy: '/mcp'};
  if(p === 'cx') return {steps: [{t: 'Codex has no in-session command to reconnect an MCP server'}, {t: 'Close the session and reopen it with {c}', c: 'codex resume'}], copy: 'codex resume'};
  if(p === 'pi') return {steps: [{t: 'pi reconnects on the next call by itself'}, {t: "In that session's terminal run {c}", c: '/mcp reconnect ' + name},
    {t: 'After a config edit run {c}', c: '/reload'}], copy: '/mcp reconnect ' + name};
  return {steps: [{t: "Use that CLI's own MCP reconnect, or restart the session"}], copy: ''};
}
function mcpcStepHtml(st, name){
  return '<li>' + esc(T(st.t)).replace(/\{s\}/g, () => '<b>' + esc(name) + '</b>').replace(/\{c\}/g, () => '<code>' + esc(st.c || '') + '</code>') + '</li>';
}
function mcpcReconnHtml(row, srv, st){
  const S = mcpcSteps(row && row.plat, srv, st), cp = MCPC.cp === srv.name;
  return '<div class=mcpcwhy>' + esc(T('A session cannot reconnect an MCP server by itself — a person does it in that terminal. Sidereus never touches the terminal.')) + '</div>'
    + '<ol class=mcpcsteps>' + S.steps.map(x => mcpcStepHtml(x, srv.name)).join('') + '</ol>'
    + (S.copy ? '<div class=mcpcgo><button type=button class=mcpcbtn data-mcpccp="' + esc(S.copy) + '">' + esc(cp ? T('Copied') : T('Copy') + ' ' + S.copy) + '</button></div>' : '');
}
function mcpcDraftHtml(row, srv, act){
  const raw = MCPC.note[srv.name] || '', n = mcpcNote(raw), need = act === 'task', inbox = !!(row && typeof mboxIn === 'function' && mboxIn(row));
  const can = inbox && !MCPC.sending && !(need && !n);
  const why = !inbox ? T('This session is not logged in to the mailbox — nothing can be sent') : need && !n ? T('Write the one-line request first') : '';
  return '<input class=mcpcnote data-mcpcnote="' + esc(srv.name) + '" maxlength=200 spellcheck=false autocomplete=off value="' + esc(raw) + '"'
    + ' placeholder="' + esc(need ? T('One-line request (required)') : T('Note (optional)')) + '" aria-label="' + esc(need ? T('One-line request (required)') : T('Note (optional)')) + '">'
    + '<div class=mcpcto>' + esc(T('To')) + ' <b>' + esc(inbox ? row.mbox : '—') + '</b> · ' + esc((row && row.project) || '') + ' · ' + esc(sid8(row && row.sid)) + '</div>'
    + '<pre class=mcpcpv>' + esc(mcpcBody(act, srv, row, n)) + '</pre>'
    + (why ? '<div class=mcpcwhy>' + esc(why) + '</div>' : '')
    + '<div class=mcpcgo><button type=button class="wkrgb archok" data-mcpcgo' + (can ? '' : ' disabled') + '>' + esc(MCPC.sending ? T('Sending…') : T('Confirm — send')) + '</button></div>'
    + (MCPC.msg ? '<div class="mcpcwhy err">' + esc(MCPC.msg) + '</div>' : '');
}
function mcpcScopeLbl(sc){
  return sc === 'user' ? T('user') : sc === 'project' ? T('project') : sc === 'plugin' ? T('plugin') : sc === 'cloud' ? 'claude.ai'
    : sc === 'seen' ? T('seen in records only') : String(sc || '—');
}
// Totals from the server; a missing key is counted from the rows (never shown as 0 when there is no answer).
function mcpcTotals(d){
  const t = d && d.totals && typeof d.totals === 'object' ? d.totals : {}, out = {};
  for(const k of ['ok', 'fail', 'auth', 'unknown']) out[k] = typeof t[k] === 'number' ? t[k] : (d.servers || []).filter(s => s && mcpcStKey(s.state) === k).length;
  return out;
}
function mcpcCard(title, aside, body, cls){
  return '<section class="mcpccard' + (cls ? ' ' + cls : '') + '"><h4><span>' + esc(title) + '</span>' + (aside ? '<i>' + esc(aside) + '</i>' : '') + '</h4>' + body + '</section>';
}
function mcpcStateCard(d){
  const ok = !!(d && d.ok && d.supported !== false), tot = ok ? mcpcTotals(d) : null, now = d ? +d.now || 0 : 0;
  const tiles = '<div class=mcpctiles>' + ['ok', 'fail', 'auth', 'unknown'].map(k => '<button type=button class="mcpctile st-' + k + (MCPC.filt === k ? ' on' : '')
    + '" data-mcpcf="' + k + '" aria-pressed="' + (MCPC.filt === k) + '"' + (ok ? '' : ' disabled') + '><b>' + (tot ? String(tot[k]) : '—') + '</b><span>'
    + esc(mcpcStLbl(k)) + '</span></button>').join('') + '</div>';
  const bad = ok ? (d.servers || []).filter(s => s && mcpcStKey(s.state) === 'fail') : [];
  const prob = bad.length ? '<div class=mcpcprob>' + bad.map(s => '<div><b>' + esc(s.name) + '</b><code>' + esc(s.err || 'FAIL') + '</code><i>' + esc(mcpcAgo(s.at, now)) + '</i></div>').join('') + '</div>' : '';
  const chk = ok && +d.checked > 0 ? T('Checked {t}').replace('{t}', () => mcpcAgo(d.checked, now)) : '';
  return mcpcCard(T('Connection state'), chk, tiles + prob);
}
function mcpcCallsCard(d){
  const em = s => '<div class=mcpcempty>' + esc(s) + '</div>';
  let body;
  if(!d || !d.ok || d.supported === false) body = em('—');
  else if(d.counts === false) body = em(T("This CLI's records carry no per-server calls"));
  else {
    const now = +d.now || 0, us = (d.servers || []).filter(s => s && +s.n > 0).sort((a, b) => b.n - a.n), mx = Math.max(1, ...us.map(s => +s.n));
    body = us.length ? '<div class=mcpcbars>' + us.map(s => '<button type=button class="mcpcbar' + (MCPC.sel === s.name ? ' on' : '') + '" data-mcpcn="' + esc(s.name) + '">'
      + '<span class=mcpcbn title="' + esc(s.name) + '">' + esc(s.name) + '</span><span class=mcpcbr><i style="width:' + Math.max(2, s.n / mx * 100).toFixed(1) + '%"></i></span>'
      + '<span class=mcpcbc>' + String(+s.n) + ' · ' + esc(mcpcAgo(s.last, now)) + '</span></button>').join('') + '</div>'
      : em(T('This session has not called an MCP server yet'));
  }
  // since > 0: counting began mid-session (pi record kept by an older viewer), so the numbers are not the whole session.
  const sub = d && +d.since > 0 ? T('calls since {t} · last').replace('{t}', () => mcpcAgo(d.since, +d.now || 0)) : T('calls · last');
  return mcpcCard(T('MCP this session called'), sub, body);
}
function mcpcDetailCard(d, row){
  const srv = d && d.ok && MCPC.sel ? (d.servers || []).find(s => s && s.name === MCPC.sel) : null;
  if(!srv) return mcpcCard(T('Server'), '', '<div class=mcpcempty>' + esc(T('Click a node for its state and actions; drag it onto the session to draft a task.')) + '</div>', 'mcpcdet');
  const st = mcpcStKey(srv.state), now = +d.now || 0, act = mcpcActOf(srv), r = (l, v) => '<div class=mcpcr><span>' + esc(l) + '</span><span>' + v + '</span></div>';
  const use = d.counts === false || srv.n == null ? esc(T('not recorded')) : esc(T('{n} calls').replace('{n}', String(+srv.n || 0))) + (+srv.last > 0 ? ' · ' + esc(mcpcAgo(srv.last, now)) : '');
  const body = r(T('State'), '<b class="mcpcsl st-' + st + '">' + esc(mcpcStLbl(st)) + '</b>' + (srv.err ? ' <code class=mcpcerr>' + esc(srv.err) + '</code>' : ''))
    + r(T('Checked'), esc(mcpcAgo(srv.at, now)))
    + r(T('This session'), use)
    + r(T('Scope'), esc(mcpcScopeLbl(srv.scope)) + (srv.plug ? ' · ' + esc(srv.plug) : '') + (srv.on === false ? ' · ' + esc(T('off', 'state')) : ''))
    + (srv.transport ? r(T('Transport'), esc(srv.transport)) : '')
    + '<div class=mcpcacts role=group aria-label="' + esc(T('Actions')) + '">' + mcpcActs(srv).map(a => '<button type=button class="mcpcbtn' + (a === act ? ' on' : '')
      + '" data-mcpca="' + a + '" aria-pressed="' + (a === act) + '">' + esc(mcpcActLbl(a, st)) + '</button>').join('') + '</div>'
    + '<div class=mcpcab>' + (act === 'reconn' ? mcpcReconnHtml(row, srv, st) : mcpcDraftHtml(row, srv, act)) + '</div>';
  return mcpcCard(srv.name, mcpcScopeLbl(srv.scope), body, 'mcpcdet');
}
// Request log: action · server · sid8 · time · sent/failed. Metadata only (no body), newest first, capped.
function mcpcLogGet(){
  if(MCPC.log) return MCPC.log;
  const v = typeof lsJson === 'function' ? lsJson(MCPC_LOG_KEY, []) : [];
  MCPC.log = Array.isArray(v) ? v.filter(x => x && MCPC_SENDS.includes(x.a) && typeof x.s === 'string' && typeof x.at === 'number').slice(0, MCPC_LOG_MAX) : [];
  return MCPC.log;
}
function mcpcLogAdd(it){
  MCPC.log = [it].concat(mcpcLogGet()).slice(0, MCPC_LOG_MAX);
  try{ if(typeof lsSetJson === 'function') lsSetJson(MCPC_LOG_KEY, MCPC.log); }catch(e){ softErr('mcpc-log', e); }
}
function mcpcLogCard(){
  const l = mcpcLogGet();
  const kl = x => x.k && x.k !== 'mcp' && MCPC_KINDS.includes(x.k) ? esc(mcpcKindLbl(x.k)) + ' · ' : '';
  const body = l.length ? '<div class=mcpclog>' + l.map(x => '<div><span>' + esc(hhmm(x.at)) + '</span><span class=mcpclt>' + kl(x) + esc(mcpcActLbl(x.a, '')) + ' · ' + esc(x.s)
    + ' → ' + esc(String(x.sid || '')) + '</span><b class="' + (x.ok ? 'ok' : 'bad') + '">' + esc(x.ok ? T('Sent', 'mcp') : T('Failed', 'mcp')) + '</b></div>').join('') + '</div>'
    : '<div class=mcpcempty>' + esc(T('None yet')) + '</div>';
  return mcpcCard(T('Request log'), T('mailbox'), body);
}
function mcpcSideHtml(d, row){
  const kd = mcpcKindOf(d);
  if(kd !== 'mcp') return mcpcKindSide(d, row, kd) + mcpcLogCard();
  return mcpcStateCard(d) + mcpcCallsCard(d) + mcpcDetailCard(d, row) + mcpcLogCard();
}
// Mailbox thread label (pre = 'mcp' or the kind); ⚠must match sidereus/bus.py DM_THREAD (<= 60 chars of [\w .·:-]) or /api/dm refuses the send.
function mcpcThread(name, pre){ return ((pre || 'mcp') + ':' + String(name || '').replace(/[^\w .·:-]/g, '-')).slice(0, 60); }
// The only sender. ⚠Recipient = the session's logged-in mailbox id (mboxIn); the body is recomputed from the same inputs the preview showed.
// A kind item (47m) sends «Task» only; its note key is kind:name so a same-named MCP server keeps its own draft.
async function mcpcSend(){
  const d = MCPC.data, name = MCPC.sel, row = mcpcRow(MCPC.sid), kd = mcpcKindOf(d), mine = !!(d && d.ok && d.sid === MCPC.sid);
  const it = mine && kd !== 'mcp' ? mcpcKindFind(d, kd, name) : null;
  const srv = mine && kd === 'mcp' ? (d.servers || []).find(s => s && s.name === name) : null;
  if(MCPC.sending || !(srv || it) || !row || !(typeof mboxIn === 'function' && mboxIn(row))) return false;
  const act = it ? 'task' : mcpcActOf(srv), n = mcpcNote(MCPC.note[it ? kd + ':' + name : name]);
  if(!MCPC_SENDS.includes(act) || (act === 'task' && !n)) return false;
  const body = it ? mcpcKindBody(kd, it, n) : mcpcBody(act, srv, row, n);
  MCPC.sending = true; MCPC.msg = ''; mcpcRepaint();
  let ok = false;
  try{
    const j = await postJSON('/api/dm', {to: row.mbox, body, relay: true, sid: row.sid, thread: mcpcThread(name, it ? kd : 'mcp')});
    ok = !!(j && j.ok);
    if(!ok) MCPC.msg = T('Could not send') + ': ' + String((j && (j.error || j.err)) || '?');
  }catch(e){ MCPC.msg = T('Could not send') + ': ' + (e && e.body && (e.body.error || e.body.err || e.body.msg) ? String(e.message) : fetchErrMsg(e)); }
  MCPC.sending = false;
  mcpcLogAdd({a: act, s: name, sid: sid8(row.sid), at: Math.floor(Date.now() / 1000), ok, k: it ? kd : 'mcp'});
  if(ok){
    MCPC.note[it ? kd + ':' + name : name] = '';
    const i = document.querySelector('.mcpc .mcpcnote'); if(i) i.value = '';   // ⚠morph keeps a typed value: clear the property
  }
  mcpcRepaint();
  return ok;
}
if(typeof document !== 'undefined' && document.addEventListener){
  document.addEventListener('click', e => {
    const t = e.target, root = t && t.closest && t.closest('.mcpc');
    if(!root) return;
    const f = t.closest('[data-mcpcf]');
    if(f){ const k = f.dataset.mcpcf; MCPC.filt = MCPC.filt === k ? '' : k; if(MCPC.filt === 'auth') MCPC.cloudOpen = true; mcpcRepaint(); return; }
    const a = t.closest('[data-mcpca]');
    if(a && MCPC.sel){ MCPC.act[MCPC.sel] = a.dataset.mcpca; MCPC.msg = ''; MCPC.cp = ''; mcpcRepaint(); kbHold('.mcpc [data-mcpca][aria-pressed="true"]'); return; }
    const c = t.closest('[data-mcpccp]');
    if(c){
      const nm = MCPC.sel;
      copyText(c.dataset.mcpccp).then(ok => {
        if(!ok){ note(T('Could not copy — copy the command by hand')); return; }
        MCPC.cp = nm; mcpcRepaint();
        setTimeout(() => { if(MCPC.cp === nm){ MCPC.cp = ''; mcpcRepaint(); } }, 2000);
      });
      return;
    }
    if(t.closest('[data-mcpcgo]')) mcpcSend();
  });
  document.addEventListener('input', e => {
    const i = e.target && e.target.closest && e.target.closest('.mcpc [data-mcpcnote]');
    if(!i) return;
    MCPC.note[i.dataset.mcpcnote] = i.value;
    mcpcRepaint();
  });
}
