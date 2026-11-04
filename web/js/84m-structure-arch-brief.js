// ── Structure «Architecture» header «Export HTML» menu: «Simple» = the HEAD commit's brief.html (arch-brief) in a new tab, or a run
// request when there is none; «Detailed» = 84m2 archXDownload. ⚠brief.html is served with a no-script sandbox CSP; tabs open only on a click.
const ARCH_BRIEF_PL = 'arch-brief';
// Pure: /api/arch/brief URL of p's HEAD brief, '' without one. ⚠The file path is server data: esc, never T().
function archBriefHref(d, p){
  const b = d && d.ok && d.brief && typeof d.brief === 'object' ? d.brief : null;
  if(!b || !p || !b.commit || !b.file) return '';
  return '/api/arch/brief?path=' + encodeURIComponent(p) + '&commit=' + encodeURIComponent(String(b.commit));
}
// Pure: export needs a map drawn at HEAD; a stale or other-commit map would describe code that is no longer there.
function archXOk(d){
  return !!(d && d.ok && !d.empty && !d.bad && (d.modules || []).length && !d.stale && d.head && d.commit === d.head);
}
function archBriefBusy(p){ return !!((typeof archReqLive === 'function' && archReqLive(archReqLast(p, ARCH_BRIEF_PL))) || (BRIEFRUN && BRIEFRUN[p])); }   // ⚠'sent' counts: only run/stopping let a second request out
// Pure: header button (disabled with the reason when there is no HEAD map) + its menu while ARCH.xm === p (absolute: the header never shifts).
function archXBtn(d, p){
  const ok = archXOk(d), open = ok && !!p && ARCH.xm === p;
  return '<span class=archxw><button type=button class="archgo archckgo' + (open ? ' on' : '') + '" data-arxp aria-haspopup=menu aria-expanded=' + (open ? 'true' : 'false')
    + (ok ? '' : ' disabled') + ' title="' + esc(T(ok ? 'Export the architecture as an HTML page' : 'Draw the architecture map for the current commit first')) + '">'
    + esc(T('Export HTML')) + ' ▾</button>' + (open ? archXMenu(d, p) : '') + '</span>';
}
// Pure: «Simple» is a real link when the brief exists (the browser opens it), else a request button; «Detailed» downloads (84m2).
function archXMenu(d, p){
  const href = archBriefHref(d, p), busy = !href && archBriefBusy(p), lb = esc(T('Simple', 'arch export'));
  const s = href ? '<a role=menuitem class="wkrgb archxi" data-arxc target=_blank rel="noopener noreferrer" href="' + esc(href) + '" title="'
      + esc(T('Open the big-picture overview in a new tab') + '\n' + String(d.brief.file)) + '">' + lb + '</a>'
    : '<button type=button role=menuitem class="wkrgb archxi" data-arxs' + (busy ? ' disabled' : '') + ' title="'
      + esc(T(busy ? 'An overview run is in progress' : 'No overview for this commit yet — ask a session to draw one')) + '">' + lb + '</button>';
  return '<div class=archxm role=menu aria-label="' + esc(T('Export HTML')) + '">' + s + '<button type=button role=menuitem class="wkrgb archxi" data-arxd title="'
    + esc(T('Download the module map as one HTML file')) + '">' + esc(T('Detailed', 'arch export')) + '</button></div>';
}
// Paint signature part (84j archPaint): menu, brief preview, request record and server run.
function archXSig(p){
  return JSON.stringify([ARCH.xm === p, ARCH.breq || null, typeof archReqLast === 'function' ? archReqLast(p, ARCH_BRIEF_PL) : null, !!(BRIEFRUN && BRIEFRUN[p])]);
}
// ⚠95-poll repaints Structure only on a session change and archTick watches arch-map: without this Sent → Running → «Stop» never shows.
let ARCH_BRIEF_SIG = '';
setInterval(() => {
  if(typeof mainView === 'undefined' || mainView !== 'struct' || strMode !== 'arch' || document.hidden) return;
  const p = strOn[0] || '', s = JSON.stringify([p, archXSig(p)]);
  if(s !== ARCH_BRIEF_SIG){ ARCH_BRIEF_SIG = s; paintStruct(); }
}, 5000);
// From 84j archPaint: menu and preview belong to the shown project; a live run closes the preview so no second request goes out.
function archXFix(p, cands){
  if(ARCH.xm && ARCH.xm !== p) ARCH.xm = '';
  const q = ARCH.breq;
  if(q && (q.p !== p || (!q.busy && archBriefBusy(p)))) ARCH.breq = null;
  else if(q && cands.length && !cands.some(c => c.sid === q.sid)) q.sid = cands[0].sid;
}
// Pure: mailbox wire text (English, not UI) — arch-map's tail (stage tags) via 84j archDmBody; stage titles verbatim: [pl:] tags match them.
function archBriefDmBody(repo, home, cx){
  return archDmBody(ARCH_BRIEF_PL, repo, home, '', cx, { reread: 'S/map.json and S/verify.json, then S/brief.json', head: h =>
    'Pipeline arch-brief run — request: «' + repo + ': draw architecture overview»\n'
    + 'Target repository: ' + repo + '\n'
    + 'Read-only: never write to the repository — write only S/brief.json, S = the store dir printed by stage 준비\n'
    + 'Pipeline: ' + h + '.claude/pipelines/arch-brief.json (준비 → 개요 그리기 → 검증)\n'
    + 'Gate: python3 ' + h + 'scripts/arch_brief.py --last (Windows: py ' + h + 'scripts/arch_brief.py --last)' });
}
// Pure: preview of the arch-brief request (rule 7: Sidereus composes it, so preview + confirm); '' without one.
function archBriefReqHtml(q, repo, home, cands){
  if(!q) return '';
  const cur = cands.find(c => c.sid === q.sid) || null, why = archWhyOff(home, cands, cur);
  return '<div class=archreq role=group aria-label="' + esc(T('Request preview')) + '"><div class=archrqh><b>' + esc(T('Simple overview')) + '</b>'
    + '<label>' + esc(T('To session')) + ' <select data-arbs>' + (cands.length ? cands.map(c => '<option value="' + esc(c.sid) + '"' + (c.sid === q.sid ? ' selected' : '') + '>'
      + esc((c.dir ? c.dir + ' · ' : '') + sid8(c.sid) + (c.model ? ' · ' + c.model : '') + (c.id ? ' · ' + c.id : '')) + '</option>').join('') : '<option value="">' + esc(T('None')) + '</option>')
    + '</select></label></div><pre class=archdm>' + esc(archBriefDmBody(repo, home, !!(cur && cur.cx))) + '</pre>' + (typeof plCxHint === 'function' ? plCxHint(cur) : '') + '<div class=archrqb>'
    + '<button type=button class="wkrgb archok" data-arbgo' + (why || q.busy ? ' disabled' : '') + (why ? ' title="' + esc(why) + '"' : '') + '>' + esc(T(q.busy ? 'Sending…' : 'Confirm — send')) + '</button>'
    + '<button type=button class=wkrgb data-arbx>' + esc(T('Cancel')) + '</button>' + (why ? '<span class=archwhy>' + esc(why) + '</span>' : '') + '</div></div>';
}
// Slot under the header (84j .archck): request row (84l2, «Stop» reuses its handlers) + the open preview.
function archBriefSlot(p, home, cands){
  const q = ARCH.breq && ARCH.breq.p === p ? ARCH.breq : null, pv = q ? archBriefReqHtml(q, p, home, cands) : '';
  return typeof archReqSlot === 'function' ? archReqSlot(p, ARCH_BRIEF_PL, pv, pv) : pv;
}
// Guard + send: only the preview's confirm calls this (no auto-send).
async function archBriefSend(){
  const q = ARCH.breq;
  if(!q || q.busy) return false;
  const d = ARCH.cache[q.p], home = archHome(d), cs = archCands(home, SESS, q.p), cur = cs.find(c => c.sid === q.sid);
  if(!cur || archWhyOff(home, cs, cur) || archBriefBusy(q.p) || !archXOk(d)) return false;
  q.busy = true; paintStruct();
  try{
    const j = await postJSON('/api/dm', { to: cur.id, sid: cur.sid, relay: true, thread: 'pipeline:' + ARCH_BRIEF_PL, body: archBriefDmBody(q.p, home, !!cur.cx),
      plreq: { kind: 'req', pipeline: ARCH_BRIEF_PL, repo: q.p } });   // server records who received it (state `plReq`)
    if(!j || !j.ok) throw new Error((j && (j.error || j.err)) || '?');   // ⚠ok first: nothing went out, remember nothing
    const m = plMem(); m[cur.sid] = { name: ARCH_BRIEF_PL, at: Date.now() }; lsSetJson('sidereus.plrun', m);   // same lighting memo as 48b plRunSend
    ARCH.breq = null; ARCH.msg = '';
  }catch(e){ q.busy = false; ARCH.msg = T('Could not send') + ': ' + String((e && e.message) || e); }
  paintStruct();
  return true;
}
// ⚠Closes by dropping the node, no repaint: a rebuild during a click detaches its target and swallows it.
function archXClose(){
  ARCH.xm = '';
  document.querySelectorAll('.archtab .archxm').forEach(m => m.remove());
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
  if(t.closest('[data-arxs]')){ const d = ARCH.cache[p], c = archCands(archHome(d), SESS, p); ARCH.xm = ''; ARCH.msg = '';
    if(archXOk(d) && !archBriefBusy(p) && !(ARCH.breq && ARCH.breq.p === p)){ ARCH.breq = { p, sid: (c[0] || {}).sid || '', busy: false }; if(ARCH.req && !ARCH.req.busy) ARCH.req = null; }   // one preview at a time
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
}
