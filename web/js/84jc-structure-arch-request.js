// Pure: DM body the person previews; names the pipeline and the target repo, read-only by contract.
// Mailbox wire text in the same format as 48b pipeline run requests, not UI.
// ⚠Absolute paths under the Sidereus repo (home): the recipient may run in another repo, where relative ones miss.
function archDmBody(name, repo, home, verb, cx, o, lang){   // verb = archReqOf(d).vb (wire text, default generate) · cx = non-Claude recipient (cand.sh) · o = {head(h), reread}: another pipeline's lines (84m), shared tail · lang = viewer LANG
  const h = home ? String(home).replace(/\/+$/, '') + '/' : '', ln = lang === 'ko' ? 'Korean' : 'English';
  return (o ? o.head(h) : 'Pipeline ' + name + ' run — request: «' + repo + ': ' + (verb || 'generate') + ' architecture diagram»\n'
    + 'Target repository: ' + repo + '\n'
    + 'Read-only: never write to the repository — write only under ${MAILBOX_DIR:-~/.mailbox-mcp}/arch/<key>/<commit>/ (key: pipeline rules)\n'
    + 'Pipeline: ' + h + '.claude/pipelines/' + name + '.json (읽기 계획 → 모듈 그리기 → 흐름 그리기 → 검증 → 개요 그리기 → 개요 검증)\n'   // stage titles verbatim: [pl:] tags match them
    + 'Gate: python3 ' + h + 'scripts/arch_verify.py --last (Windows: py ' + h + 'scripts/arch_verify.py --last); overview: python3 ' + h + 'scripts/arch_brief.py --last (Windows: py ' + h + 'scripts/arch_brief.py --last)') + '\nLanguage: ' + ln + ' — write all human text in map.json, flows.json and brief.json (names, labels, notes, titles, roles) in ' + ln + '; ids, paths and code symbols stay as-is'   // ⚠page has no server-OS signal: both forms · Language line: pipeline tasks read it (none = English); preview and send pass the same LANG
    // ⚠No Agent tool outside Claude Code: stages are lit by a leading shell marker (hooks/pl_mark.py --platform <cli> MARK).
    + (cx ? '\nRun the stages yourself in this session, in order (no subagents). Start each stage with a shell command echo "[pl:' + name + '/<stage title>]" and end it with echo "[pl-end:' + name + '/<stage title>]" ("|fail" before "]" when its gate failed); echo "[pl:-]" clears. Run each marker as its own single-line shell command, never inside a longer script.'
      + ' At each stage start re-read only the files the previous stage wrote (' + (o ? 'for ' + name + ': ' + o.reread : 'for arch-map: plan.json, then map.json, then flows.json, then S/map.json and S/verify.json, then S/brief.json') + '); do not rely on earlier stage context.'   // ⚠one Codex context holds every stage: stale earlier reads leak into later stages
      + ' Run all stages back to back in this turn: do not end the turn or report between stages; report once after the last stage.'
      // ⚠A Claude recipient in another repo tagged every dispatch [pl:-] and no run was recorded: name the tag.
      : '\nTag each stage dispatch description with [pl:' + name + '/<stage title>] (not [pl:-]); a stage you run yourself: Bash description with the same tag.');   // ⚠Codex ended its turn after each stage and waited for a new prompt
}
// Sidereus repo: the server's `sidereus` field, else the project whose pipeline list holds arch-map (48 PLS, if loaded).
function archHome(d){
  if(d && d.sidereus) return String(d.sidereus);
  const D = (typeof PLS !== 'undefined' && PLS && PLS.data) || {};
  return Object.keys(D).find(k => D[k] && D[k].ok && (D[k].pipelines || []).some(q => q && q.name === ARCH_PL)) || '';
}
// Pure: last path segment (option labels tell sessions apart by folder).
function archBase(p){ const s = String(p || '').replace(/[\\/]+$/, ''); return s.slice(Math.max(s.lastIndexOf('/'), s.lastIndexOf('\\')) + 1) || s; }
// Live sessions of every platform (metadata only; ⚠no platform allow-list — a new CLI must not need a picker change): target project p, then the Sidereus repo, then the rest; mailbox login first in each group.
// The first entry is the default recipient — the project's own session already holds that repo.
function archCands(home, sess, p){
  const g = x => x.cwd === p ? 0 : home && x.cwd === home ? 1 : 2;
  return (sess || []).filter(x => x && x.sid && x.state !== 'done')
    .map((x, i) => ({ sid: x.sid, model: x.model || '', plat: x.plat || 'cc', sh: !!x.plat && x.plat !== 'cc', cx: x.plat === 'cx',   // sh = not Claude (no Agent tool: shell-marker body) · cx = Codex only (plCxHint)
      id: x.mbox || '', login: mboxIn(x), dir: archBase(x.cwd), g: g(x), i }))
    .sort((a, b) => a.g - b.g || (b.login ? 1 : 0) - (a.login ? 1 : 0) || a.i - b.i);
}
// Pure: no-home reason plus what to do; ⚠a pipx/uv install has no repo holding the pipeline and its scripts (arch_map.SIDEREUS_ROOT = '').
function archNoHome(){ return T('The Sidereus repository location is unknown') + ' — ' + T('this needs Sidereus run from a git clone; the installed package cannot run this pipeline'); }
// Why «Confirm — send» is disabled ('' = enabled).
function archWhyOff(home, cands, cur){
  if(!home) return archNoHome();
  if(!cands.length) return T('No live session');
  if(!cur || !cur.login) return T('That session is not logged in to the mailbox');
  return '';
}
// Request button label + DM verb by map state: none/invalid -> generate · stale -> update · built at HEAD -> redraw.
function archReqOf(d){
  if(!d || !d.ok || d.empty || d.bad || !(d.modules || []).length) return { lb: 'Generate diagram', vb: 'generate' };
  return !d.stale && d.head && d.commit === d.head ? { lb: 'Redraw', vb: 'redraw' } : { lb: 'Update diagram', vb: 'update' };
}
// Header request button: same place in every map state; disabled while a run/request is in flight.
function archReqBtn(p, home, cands, d){
  const live = !!(archRunOf(p) || archSentPh(p) || (typeof archReqBusy === 'function' && archReqBusy(p, ARCH_PL))), open = !!(ARCH.req && ARCH.req.p === p), why = live ? '' : archWhyOff(home, cands, cands[0]);
  return '<button type=button class="archgo archckgo' + (open ? ' on' : '') + '" data-arq aria-expanded=' + (open ? 'true' : 'false') + (live ? ' disabled' : '')
    + ' title="' + esc(why || T('Asks a live session to draw the map; you see the message before it is sent')) + '">' + esc(T(archReqOf(d).lb)) + '</button>';
}
// Pure: the preview panel once the request button is pressed (titled with its label); '' otherwise.
function archReqHtml(req, repo, home, cands, busy, d){
  if(!req) return '';
  const cur = cands.find(c => c.sid === req.sid) || null, why = archWhyOff(home, cands, cur), rk = archReqOf(d);
  return '<div class=archreq role=group aria-label="' + esc(T('Request preview')) + '"><div class=archrqh><b>' + esc(T(rk.lb)) + '</b>'
    + '<label>' + esc(T('To session')) + ' <select data-ars>' + (cands.length ? cands.map(c => '<option value="' + esc(c.sid) + '"' + (c.sid === req.sid ? ' selected' : '') + '>'
      + esc((c.sh && typeof platName === 'function' ? platName(c.plat) + ' · ' : '') + (c.dir ? c.dir + ' · ' : '') + sid8(c.sid) + (c.model ? ' · ' + c.model : '') + (c.id ? ' · ' + c.id : '')) + '</option>').join('') : '<option value="">' + esc(T('None')) + '</option>')
    + '</select></label></div><pre class=archdm>' + esc(archDmBody(ARCH_PL, repo, home, rk.vb, !!(cur && cur.sh), null, LANG)) + '</pre>' + plCxHint(cur) + '<div class=archrqb>'
    + '<button type=button class="wkrgb archok" data-argo' + (why || busy ? ' disabled' : '') + (why ? ' title="' + esc(why) + '"' : '') + '>' + esc(T(busy ? 'Sending…' : 'Confirm — send')) + '</button>'
    + '<button type=button class=wkrgb data-arx>' + esc(T('Cancel')) + '</button>' + (why ? '<span class=archwhy>' + esc(why) + '</span>' : '') + '</div></div>';
}
// Sent request → the run it started: newest arch-map run of that session touched after the send.
function archSentRun(p){
  const q = ARCH.sent;
  if(!q || q.p !== p) return null;
  const s = (SESS || []).find(x => x && x.sid === q.sid);
  const rs = ((s && s.plrun) || []).filter(r => r && r.name === ARCH_PL && (+r.t1 || 0) * 1000 >= q.at - 60000);
  return rs.sort((a, b) => (+b.t1 || 0) - (+a.t1 || 0))[0] || null;
}
// Phase of the open request for p: '' none · 'sent' · 'run' once the session shows activity after the send (sticky).
function archSentPh(p){
  const q = ARCH.sent;
  if(!q || q.p !== p) return '';
  const s = (SESS || []).find(x => x && x.sid === q.sid);
  if(archSentRun(p) || (s && (s.state === 'think' || s.state === 'tool'))) q.act = 1;   // a pause between stages stays «Analysing»
  return q.act ? 'run' : 'sent';
}
function archEl(q, now){ return ago(Math.max(0, Math.floor((now - q.at) / 1000))); }
// Server-side run in progress for p (state `archRun`, sidereus/arch_map.runs; ARCHRUN in 00-core): survives reload, ends with the run.
// pl: pipeline name (default arch-map); security-checks = state `secRun` (SECRUN, 84l ARCH_SEC_PL). ⚠typeof: tests define ARCHRUN only.
function archRunOf(p, pl){ const M = !pl || pl === ARCH_PL ? ARCHRUN : pl === 'security-checks' && typeof SECRUN !== 'undefined' ? SECRUN : null;
  const r = p && M && M[p]; return r && typeof r === 'object' && r.stage ? r : null; }
function archRunEl(r, now){ return ago(Math.max(0, Math.floor(now / 1000 - (+r.t0 || now / 1000)))); }
// Pure: in-progress line replacing the request button; ⚠the stage title is a pipeline stage id, never through T().
function archRunHtml(r, now, pl){
  const sec = pl === 'security-checks', st = (r.n && r.of ? T('Stage {n}/{m}').replace('{n}', r.n).replace('{m}', r.of) + ' · ' : '') + r.stage;
  const tip = sec ? T('A security check run is in progress for this project — session {s}') : T('A diagram run is in progress for this project — session {s}');
  return '<div class="archsent run archrun" role=status title="' + esc(tip.replace('{s}', sid8(r.sid || ''))) + '">'
    + '<i class=archspin></i><span>' + esc(T(sec ? 'Checking' : 'Analysing') + ' · ' + st + ' · ') + '<span data-arel>' + esc(archRunEl(r, now || Date.now())) + '</span></span></div>';
}
// Status slot: a live server run wins over the page's own request memo, which wins over the request button.
// A request record (84l2 archReqSlot, state `plReq`) shows the receiving session and replaces the transient line; ⚠typeof: tests load without 84l2.
function archStatusHtml(p, req){ const r = archRunOf(p), s = r ? archRunHtml(r) : (archSentHtml(p) || req);
  return typeof archReqSlot === 'function' ? archReqSlot(p, ARCH_PL, s, ARCH.req && ARCH.req.p === p ? req : '') : s; }
// Pure: done = a map with modules whose commit differs from the one on screen at send time (base; '' when there was none).
function archSentDone(d, q){
  return !!(q && d && d.ok && !d.empty && ((d.modules || []).length) && String(d.commit || '') !== String(q.base || ''));
}
// One-line status in place of the request form; elapsed text is refreshed in place by archTick (no repaint).
function archSentHtml(p, now){
  const q = ARCH.sent, ph = archSentPh(p);
  if(!ph) return '';
  if(ph === 'sent') return '<div class=archsent role=status><span>' + esc(T('Analysis requested') + ' · ' + q.id + ' · ' + CLK(new Date(q.at))) + '</span></div>';
  return '<div class="archsent run" role=status><i class=archspin></i><span>' + esc(T('Analysing') + ' · ')
    + '<span data-arel>' + esc(archEl(q, now || Date.now())) + '</span></span></div>';
}
// The map arrived for the open request: close it and raise one in-page notice.
// ⚠note() (40b), not toast(): card toasts are server bell history and their click posts a read key.
function archSentFin(p, d){
  const q = ARCH.sent;
  if(!q || q.p !== p || !archSentDone(d, q)) return false;
  ARCH.sent = null;
  note(T('{p} architecture diagram ready').replace('{p}', archBase(p)));
  return true;
}
// While a request is open and its project is on screen: re-read the map every ~30s (one in flight); a run end pulls at once.
// ⚠No fetch for a hidden tab or another view; archSentFin clears ARCH.sent on the map, which ends the polling.
const ARCH_POLL_MS = 30000;
function archTick(now){
  if(mainView !== 'struct' || strMode !== 'arch' || document.hidden) return false;
  // Server run: repaint on a stage change, refresh elapsed in place; its end pulls the new map at once.
  const p = strOn[0] || '', sr = archRunOf(p), rs = sr ? [p, sr.stage, sr.n, sr.sid].join('\t') : '', was = ARCH.rsig || '';
  if(rs !== was){ ARCH.rsig = rs; paintStruct();
    if(!rs && was.split('\t')[0] === p && !ARCH.load[p]){ archFetch(p, true); return true; } }
  else if(sr){ const el = document.querySelector('.archrun [data-arel]'); if(el) el.textContent = archRunEl(sr, now); }
  const q = ARCH.sent;
  if(!q || strOn[0] !== q.p) return false;
  const r = archSentRun(q.p), ph = archSentPh(q.p);
  if(ph !== q.ph){ q.ph = ph; paintStruct(); }
  else if(!sr){ const el = document.querySelector('.archsent [data-arel]'); if(el) el.textContent = archEl(q, now); }
  const end = !!(r && r.end) && !q.endF;
  if(ARCH.load[q.p] || !(end || now - (q.polled || q.at) >= ARCH_POLL_MS)) return false;
  q.polled = now; if(end) q.endF = 1;
  archFetch(q.p, true);
  return true;
}
// Pure guard + send: only the confirm button calls this, and only with an open preview (no auto-send).
async function archSend(){
  const q = ARCH.req;
  if(!q || q.busy) return false;
  const d = ARCH.cache[q.p], home = archHome(d), cur = archCands(home, SESS, q.p).find(c => c.sid === q.sid);
  if(!cur || !cur.login || archRunOf(q.p) || (typeof archReqBusy === 'function' && archReqBusy(q.p, ARCH_PL))) return false;
  q.busy = true; paintStruct();
  try{
    const j = await postJSON('/api/dm', { to: cur.id, body: archDmBody(ARCH_PL, q.p, home, archReqOf(d).vb, !!cur.sh, null, LANG), relay: true, sid: cur.sid, thread: 'pipeline:' + ARCH_PL,
      plreq: { kind: 'req', pipeline: ARCH_PL, repo: q.p } });   // server records who received it (state `plReq`)
    if(!j || !j.ok) throw new Error((j && (j.error || j.err)) || '?');   // ⚠ok first: nothing went out, remember nothing
    const m = plMem(); m[cur.sid] = { name: ARCH_PL, at: Date.now() }; lsSetJson('sidereus.plrun', m);   // same lighting memo as 48b plRunSend
    ARCH.req = null; ARCH.msg = ''; ARCH.sent = { p: q.p, sid: cur.sid, id: cur.id, at: Date.now(), ph: 'sent',
      base: d && d.ok && !d.empty ? String(d.commit || '') : '' };   // base: a map with another commit means done
  }catch(e){ q.busy = false; ARCH.msg = T('Could not send') + ': ' + T((e && e.message) || e); }
  paintStruct();
  return true;
}
