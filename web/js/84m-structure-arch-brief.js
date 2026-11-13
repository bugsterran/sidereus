// ── Structure «Architecture» header «Export HTML» menu: «Simple» = the HEAD commit's brief.html in a new tab (disabled without one),
// «Ask the session to draw» = a brief-ask request to the repo's own live session; «Detailed» = 84m2 archXDownload.
// ⚠brief.html is served with a no-script sandbox CSP; tabs open only on a click.
const ARCH_ASK_PL = 'brief-ask';   // plain plreq name (no pipeline file): server marks it done when a newer brief.ok.json lands
// Pure: /api/arch/brief URL of p's HEAD brief, '' without one. ⚠The file path is server data: esc, never T().
function archBriefHref(d, p){
  const b = d && d.ok && d.brief && typeof d.brief === 'object' ? d.brief : null;
  if(!b || !p || !b.commit || !b.file) return '';
  return '/api/arch/brief?path=' + encodeURIComponent(p) + '&commit=' + encodeURIComponent(String(b.commit));
}
// Pure: export needs a drawn map; an older-commit map exports too, stamped with its own commit and how far HEAD moved (84m2).
function archXOk(d){
  return !!(d && d.ok && !d.empty && !d.bad && (d.modules || []).length);
}
// Pure: a new overview request needs the map at HEAD (the overview draws on top of the current arch-map result).
function archXHead(d){ return archXOk(d) && !d.stale && !!d.head && d.commit === d.head; }
// Pure: server `ask` usable for d's HEAD map; ⚠absent/partial (older server) = no request, never a guessed path or format.
function archAskOk(d){
  const a = d && d.ask;
  return !!(a && typeof a === 'object' && typeof a.dir === 'string' && a.dir && typeof a.fmt === 'string' && a.fmt && a.commit && String(a.commit) === d.head);
}
// Pure: owning sessions = live sessions whose cwd is the repo itself (84j archCands group 0).
function archOwners(cands){ return (cands || []).filter(c => c && c.g === 0); }
function archBriefBusy(p){ return !!((typeof archReqLive === 'function' && archReqLive(archReqLast(p, ARCH_ASK_PL))) || (BRIEFRUN && BRIEFRUN[p])); }   // ⚠'sent' counts: a second request waits for done/gone
// Pure: header button (disabled with the reason when there is no HEAD map) + its menu while ARCH.xm === p (absolute: the header never shifts).
function archXBtn(d, p){
  const ok = archXOk(d), open = ok && !!p && ARCH.xm === p;
  return '<span class=archxw><button type=button class="archgo archckgo' + (open ? ' on' : '') + '" data-arxp aria-haspopup=menu aria-expanded=' + (open ? 'true' : 'false')
    + (ok ? '' : ' disabled') + ' title="' + esc(T(ok ? 'Export the architecture as an HTML page' : 'Draw the architecture map for the current commit first')) + '">'
    + esc(T('Export HTML')) + ' ▾</button>' + (open ? archXMenu(d, p) : '') + '</span>';
}
// Pure: «Simple» is a real link when the brief exists (the browser opens it), else disabled; «Ask the session to draw» (R1) only with
// the HEAD map + server `ask` and an owning live session, else one reason line; «Detailed» downloads (84m2).
function archXMenu(d, p){
  const href = archBriefHref(d, p), busy = archBriefBusy(p), lb = esc(T('Simple', 'arch export'));
  const own = archOwners(archCands(archHome(d), typeof SESS !== 'undefined' ? SESS : [], p));
  const ask = !archXHead(d) || !archAskOk(d) ? '' : own.length ? '<button type=button role=menuitem class="wkrgb archxi" data-arxa' + (busy ? ' disabled' : '') + ' title="'
      + esc(T(busy ? 'An overview request is in progress' : 'Preview a request to the session working in this repository')) + '">' + esc(T('Ask the session to draw')) + '</button>'
    : '<span class=archwhy role=note>' + esc(T('No live session in this repository')) + '</span>';
  // ⚠An older map's brief opens too (same as «Detailed»), so it says how far HEAD moved; the served bytes are gate-fixed and carry no stamp.
  const old = href && d.head && String(d.brief.commit) !== d.head
    ? (typeof d.behind === 'number' ? TV({msg: d.behind === 1 ? 'HEAD is {n} commit ahead' : 'HEAD is {n} commits ahead', vars: {n: d.behind}}) : T('stale')) : '';
  const s = href ? '<a role=menuitem class="wkrgb archxi" data-arxc target=_blank rel="noopener noreferrer" href="' + esc(href) + '" title="'
      + esc(T('Open the big-picture overview in a new tab') + (old ? ' · ' + old : '') + '\n' + String(d.brief.file)) + '">' + lb + (old ? ' <small>' + esc(old) + '</small>' : '') + '</a>'
    : '<button type=button role=menuitem class="wkrgb archxi" data-arxs disabled title="'
      + esc(T(!archXHead(d) ? 'Draw the architecture map for the current commit first' : 'No overview for this commit yet')) + '">' + lb + '</button>';
  return '<div class=archxm role=menu aria-label="' + esc(T('Export HTML')) + '">' + s + ask + '<button type=button role=menuitem class="wkrgb archxi" data-arxd title="'
    + esc(T('Download the module map as one HTML file')) + '">' + esc(T('Detailed', 'arch export')) + '</button></div>';
}
// Paint signature part (84j archPaint): menu, ask preview, request record and server run.
function archXSig(p){
  return JSON.stringify([ARCH.xm === p, ARCH.breq || null, typeof archReqLast === 'function' ? archReqLast(p, ARCH_ASK_PL) : null, !!(BRIEFRUN && BRIEFRUN[p])]);
}
// ⚠95-poll repaints Structure only on a session change and archTick watches arch-map: without this Sent → Done never shows.
let ARCH_BRIEF_SIG = '';
setInterval(() => {
  if(typeof mainView === 'undefined' || mainView !== 'struct' || strMode !== 'arch' || document.hidden) return;
  const p = strOn[0] || '', s = JSON.stringify([p, archXSig(p)]);
  if(s !== ARCH_BRIEF_SIG){ ARCH_BRIEF_SIG = s; paintStruct(); }
}, 5000);
// From 84j archPaint: menu and preview belong to the shown project; a live request or a lost HEAD map/ask closes an idle preview.
function archXFix(p, cands){
  if(ARCH.xm && ARCH.xm !== p) ARCH.xm = '';
  const q = ARCH.breq, d = ARCH.cache && ARCH.cache[p], own = archOwners(cands);
  if(q && (q.p !== p || (!q.busy && (archBriefBusy(p) || (d && !(archXHead(d) && archAskOk(d))))))) ARCH.breq = null;
  else if(q && !q.busy && own.length && !own.some(c => c.sid === q.sid)) q.sid = own[0].sid;   // picked session ended: next owning one
}
// Pure: mailbox wire text (English, not UI) of «Ask the session to draw» (R2). ⚠Built only from repo, commit, store dir, the server's
// format text, the recipient sid and the language: no other session field, no conversation, no source text (rule 1); no schema copy here.
function archAskBody(repo, ask, sid, home, lang){   // lang = viewer LANG (preview and send pass the same)
  const a = ask || {}, dir = String(a.dir || '').replace(/[\\/]+$/, ''), c = String(a.commit || ''), r = String(repo || ''), by = String(sid || '');
  const h = home ? String(home).replace(/[\\/]+$/, '') + '/' : '', ln = lang === 'ko' ? 'Korean' : 'English';
  const shq = s => /^[\w@%+=:,.\/-]+$/.test(s) ? s : "'" + s.replace(/'/g, "'\\''") + "'", cmdq = s => /^[\w@%+=:,.\/\\-]+$/.test(s) ? s : '"' + s + '"';   // paths with spaces: POSIX sh · Windows cmd
  // ⚠cmdq leaves «%» unescaped on purpose: «%%» folds back to «%» only inside a .bat file, so interactive cmd, PowerShell and Git Bash
  // would get a corrupted path; plain "…" is exact there and wrong only in cmd for a path holding a defined «%NAME%» pair.
  const gate = (py, q) => py + ' ' + q(h + 'scripts/arch_brief.py') + ' --check --repo ' + q(r) + ' --commit ' + q(c) + ' --by ' + q(by);
  return 'Request: draw the architecture overview of ' + r + ' at commit ' + c + '\n'
    + 'Target repository: ' + r + '\nCommit: ' + c + '\n'
    + 'Decide what is core from your own analysis of this repository; the map is a reference only.\n'
    + 'Read-only: never write to the repository — write only ' + dir + '/brief.json\n'
    + 'Map (reference, read-only): ' + dir + '/map.json and ' + dir + '/verify.json\n'
    + 'Gate: ' + gate('python3', shq) + ' (Windows: ' + gate('py', cmdq) + ')\n'   // ⚠page has no server-OS signal: both forms
    + 'Rerun the gate until it passes; each failure names what to fix in brief.json.\n'
    + 'Language: ' + ln + ' — write all human text in brief.json (names, labels, notes, titles, roles) in ' + ln + '; ids, paths and code symbols stay as-is\n'
    + 'Format:\n' + String(a.fmt || '');
}
// Pure: preview of the ask request (rule 7: Sidereus composes it, so preview + confirm); '' without one. cands = owning sessions only.
function archBriefReqHtml(q, repo, home, cands, ask){
  if(!q) return '';
  const cur = cands.find(c => c.sid === q.sid) || null, why = archWhyOff(home, cands, cur);
  return '<div class=archreq role=group aria-label="' + esc(T('Request preview')) + '"><div class=archrqh><b>' + esc(T('Ask the session to draw')) + '</b>'
    + '<label>' + esc(T('To session')) + ' <select data-arbs>' + (cands.length ? cands.map(c => '<option value="' + esc(c.sid) + '"' + (c.sid === q.sid ? ' selected' : '') + '>'
      + esc((c.sh && typeof platName === 'function' ? platName(c.plat) + ' · ' : '') + (c.dir ? c.dir + ' · ' : '') + sid8(c.sid) + (c.model ? ' · ' + c.model : '') + (c.id ? ' · ' + c.id : '')) + '</option>').join('') : '<option value="">' + esc(T('None')) + '</option>')
    + '</select></label></div><pre class=archdm>' + esc(archAskBody(repo, ask, cur ? cur.sid : '', home, LANG)) + '</pre>' + (typeof plCxHint === 'function' ? plCxHint(cur) : '') + '<div class=archrqb>'
    + '<button type=button class="wkrgb archok" data-arbgo' + (why || q.busy ? ' disabled' : '') + (why ? ' title="' + esc(why) + '"' : '') + '>' + esc(T(q.busy ? 'Sending…' : 'Confirm — send')) + '</button>'
    + '<button type=button class=wkrgb data-arbx>' + esc(T('Cancel')) + '</button>' + (why ? '<span class=archwhy>' + esc(why) + '</span>' : '') + '</div></div>';
}
// Slot under the header (84j .archck): request row (84l2) + the open preview.
function archBriefSlot(p, home, cands){
  const q = ARCH.breq && ARCH.breq.p === p ? ARCH.breq : null, d = ARCH.cache && ARCH.cache[p], pv = q ? archBriefReqHtml(q, p, home, archOwners(cands), d && d.ask) : '';
  return typeof archReqSlot === 'function' ? archReqSlot(p, ARCH_ASK_PL, pv, pv) : pv;
}
// Guard + send: only the preview's confirm calls this (no auto-send).
async function archBriefSend(){
  const q = ARCH.breq;
  if(!q || q.busy) return false;
  const d = ARCH.cache[q.p], home = archHome(d), cs = archOwners(archCands(home, SESS, q.p)), cur = cs.find(c => c.sid === q.sid);
  if(!cur || archWhyOff(home, cs, cur) || archBriefBusy(q.p) || !archXHead(d) || !archAskOk(d)) return false;
  q.busy = true; paintStruct();
  try{
    const j = await postJSON('/api/dm', { to: cur.id, sid: cur.sid, relay: true, thread: 'pipeline:' + ARCH_ASK_PL, body: archAskBody(q.p, d.ask, cur.sid, home, LANG),
      plreq: { kind: 'req', pipeline: ARCH_ASK_PL, repo: q.p } });   // server records who received it (state `plReq`)
    if(!j || !j.ok) throw new Error((j && (j.error || j.err)) || '?');   // ⚠ok first: nothing went out, remember nothing
    if(ARCH.breq === q){ ARCH.breq = null; ARCH.msg = ''; }   // ⚠late result after a project switch: never close another project's preview
  }catch(e){ if(ARCH.breq === q){ q.busy = false; ARCH.msg = T('Could not send') + ': ' + String((e && e.message) || e); } }
  paintStruct();
  return true;
}
// ⚠Closes by dropping the node, no repaint: a rebuild during a click detaches its target and swallows it.
function archXClose(){
  ARCH.xm = '';
  document.querySelectorAll('.archtab .archxm').forEach(m => m.remove());
  // ⚠The menu left the DOM without a repaint, so the last paint signature is stale: drop it, else reopening matches it and archPaint skips (menu never shows again).
  document.querySelectorAll('.archtab').forEach(t => { for(let b = t.parentElement; b; b = b.parentElement) if('_arsig' in b){ b._arsig = ''; break; } });
  document.querySelectorAll('.archtab [data-arxp]').forEach(b => { b.classList.remove('on'); b.setAttribute('aria-expanded', 'false'); });
}
document.addEventListener('click', ev => {   // capture: outside click closes the menu
  const t = ev.target && ev.target.closest ? ev.target : null;
  if(ARCH.xm && t && !t.closest('[data-arxp],.archxm')) archXClose();
}, true);
document.addEventListener('keydown', ev => {   // capture + preventDefault: 84j3's Esc (back to the overview) skips a handled event
  if(!ARCH.xm || ev.key !== 'Escape' || ev.isComposing) return;
  ev.preventDefault(); ARCH.xm = ''; paintStruct(); kbHold('.archtab [data-arxp]');
}, true);
document.addEventListener('click', ev => {
  const t = ev.target && ev.target.closest ? ev.target : null;
  if(!t || !t.closest('.archtab') || strMode !== 'arch') return;
  const p = strOn[0] || '';
  if(t.closest('[data-arxp]')){ ARCH.xm = ARCH.xm === p ? '' : p; ARCH.msg = ''; paintStruct(); kbHold(ARCH.xm ? '.archtab .archxi:not([disabled])' : '.archtab [data-arxp]'); return; }
  if(t.closest('[data-arxc]')){ setTimeout(archXClose, 0); return; }   // ⚠a sync removal disconnects the <a> before its navigation runs: no tab opens
  if(t.closest('[data-arxa]')){ const d = ARCH.cache[p], c = archOwners(archCands(archHome(d), SESS, p)); ARCH.xm = ''; ARCH.msg = '';
    if(archXHead(d) && archAskOk(d) && c.length && !archBriefBusy(p) && !(ARCH.breq && ARCH.breq.p === p)){ ARCH.breq = { p, sid: c[0].sid, busy: false }; if(ARCH.req && !ARCH.req.busy) ARCH.req = null; }   // preview only: sending is the confirm's job (rule 7) · one preview at a time
    paintStruct(); kbHold('.archtab [data-arxp]'); return; }
  if(t.closest('[data-arxd]')){ ARCH.xm = ''; ARCH.msg = typeof archXDownload === 'function' && archXDownload(p) ? '' : T('The module map is not drawn yet'); paintStruct(); kbHold('.archtab [data-arxp]'); return; }
  if(t.closest('[data-arbx]')){ if(ARCH.breq && !ARCH.breq.busy) ARCH.breq = null; paintStruct(); return; }
  if(t.closest('[data-arbgo]')) archBriefSend();
});
document.addEventListener('change', ev => {
  const s = ev.target;
  if(!ARCH.breq || !s || !s.matches || !s.matches('.archtab select[data-arbs]')) return;
  ARCH.breq.sid = s.value; paintStruct();
});
let BRIEFRUN = {};   // state `briefRun` (95-poll): arch-brief runs in progress per project
// Pure: projects whose run was live in prev and is gone in cur.
function archBriefEnded(prev, cur){ return Object.keys(prev || {}).filter(p => !(cur && cur[p])); }
// From 95-poll: a project whose arch-brief run just ended re-fetches /api/arch at once so «Overview» shows (mirrors 84l secRun end).
function archBriefPoll(next){
  const done = archBriefEnded(BRIEFRUN, next);
  BRIEFRUN = next || {};
  done.forEach(p => { if(ARCH.cache[p] && !ARCH.load[p]) archFetch(p, true); });   // never-viewed projects fetch on paint anyway
  setTimeout(() => { if(typeof PLREQ !== 'undefined') archAskPoll(PLREQ); }, 0);   // ⚠95-poll sets PLREQ right after this call: read it after
}
let ARCH_ASK_SEEN = {};   // brief-ask row id -> last state seen
// Pure: brief-ask rows that just turned done -> [{p, id}] and the next seen map. ⚠An ended id keeps its first end state:
// a gone/stopped row never fires later, and a done row fires once.
function archAskEdge(seen, plreq){
  const nx = {}, hit = [];
  Object.keys(plreq || {}).forEach(p => (Array.isArray(plreq[p]) ? plreq[p] : []).forEach(r => {
    if(!r || typeof r !== 'object' || r.pipeline !== ARCH_ASK_PL || !r.id) return;
    const was = (seen || {})[r.id], st = was && was !== 'sent' && was !== 'run' && was !== 'stopping' ? was : String(r.state || '');
    if(st === 'done' && was !== 'done') hit.push({ p, id: r.id });
    nx[r.id] = st;
  }));
  return [hit, nx];
}
// R3: a brief-ask row that turned done re-fetches /api/arch so «Simple» becomes the link; a project still loading retries next poll.
function archAskPoll(plreq){
  const [hit, nx] = archAskEdge(ARCH_ASK_SEEN, plreq);
  hit.forEach(h => { if(!ARCH.cache[h.p]) return; if(ARCH.load[h.p]){ if(ARCH_ASK_SEEN[h.id]) nx[h.id] = ARCH_ASK_SEEN[h.id]; else delete nx[h.id]; return; } archFetch(h.p, true); });
  ARCH_ASK_SEEN = nx;
}
