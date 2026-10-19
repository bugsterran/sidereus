// «Evaluation» for the open pipeline (GET /api/pipelines/eval): header «Gates n/m» from red-checked stable gates, amber «gate not red-checked k», per-stage panel. Counts only.
const PLEVAL = {}, PLEVAL_TTL = 30000;
let PLEVAL_OPEN = '';
let PLEVAL_S = { k: '', sel: {}, req: null, sent: '', msg: '', init: false };   // suggestion ticks + «Ask AI» preview of the open pipeline
function plEvalOf(proj, name){
  if(!proj || !name) return null;
  const k = proj + '\n' + name, c = PLEVAL[k] || (PLEVAL[k] = { at: 0, d: null, s: '', busy: false });
  if(!c.busy && Date.now() - c.at > PLEVAL_TTL){
    c.busy = true;
    fetch('/api/pipelines/eval?proj=' + encodeURIComponent(proj) + '&name=' + encodeURIComponent(name), { cache: 'no-store' }).then(r => r.json())
      .then(j => { const s = JSON.stringify(j || null); if(s !== c.s){ c.s = s; c.d = j && j.ok ? j : null; plPaint(); } })   // repaint only on change: the poll keeps the view still
      .catch(() => {}).finally(() => { c.at = Date.now(); c.busy = false; });
  }
  return c.d;
}
// Overrides the editor-graph count (48d plGateCov) with the server's red-checked count; ⚠unsaved gate edits keep the editor count.
function plEvalCov(cov, ev, dirty){
  const g = ev && ev.graded;
  if(g && !dirty){ cov.n = g.n | 0; cov.m = g.m | 0; }
  return cov;
}
function plEvalHead(ev, open){
  if(!ev) return '';
  const k = (ev.graded && ev.graded.unred) | 0;
  const cmds = plEvalSgList(ev).filter(s => s.code === 'redcheck').map(s => s.cmd);   // tooltip: the exact red-check commands
  return (k > 0 ? '<span class="plcov plcovlo pleunred"' + (cmds.length ? ' title="' + esc(T('red check needed') + ':\n' + cmds.join('\n')) + '"' : '') + '>' + esc(TV({msg: 'gate not red-checked {k}', vars: {k: k}})) + '</span>' : '')
    + '<button class="wkrgb plevb' + (open ? ' on' : '') + '" data-pleval>' + esc(T('Evaluation')) + '</button>';
}
const PLE_RED = { pass: 'pass', fail: 'fail', skip: 'skip' };
// Server suggestion (sidereus/pl_eval_view.suggest) -> {msg, vars}; msg is a fixed English key, vars are data (never through T).
const PLE_SG = { 'add-gate': 'Stage {stage} has no gate and missed {kind} cases — add a gate like «{tpl}»',
  'tighten-gate': 'Stage {stage}: the gate stayed green on a broken repo — tighten it ({flags})',
  'unstable': 'Stage {stage}: the gate passed and failed on the same commit — pin tool versions, rerun to confirm',
  'add-review': 'Holdout cases were missed and there is no review or test stage — add «{tpl}»',
  'redcheck': 'Stage {stage}: red check needed — run {cmd}' };
function plEvalSgList(ev){ return (ev && Array.isArray(ev.sugg) ? ev.sugg : []).filter(s => s && PLE_SG[s.code]); }
function plEvalSgMsg(s, cat){
  const tp = s.tpl && typeof plgTpl === 'function' ? plgTpl(cat, s.tpl) : null, tn = tp && tp.title ? (LANG === 'en' && tp.title.en) || tp.title.ko : s.tpl;
  return { msg: PLE_SG[s.code], vars: { stage: String(s.stage || ''), kind: String(s.kind || ''), tpl: String(tn || ''), flags: String(s.flags || s.mode || '-'), cmd: String(s.cmd || '') } };
}
function plEvalSgEn(s){ const m = plEvalSgMsg(s, null); return m.msg.replace(/\{(\w+)\}/g, (a, k) => m.vars[k]); }   // mailbox wire text stays English
// Pure: «Suggestions» block — one checkbox each, «Fix it myself» per row, «Ask AI» relays the ticked ones (preview + confirm).
function plEvalSgHtml(ev, S, cands, cat){
  const L = plEvalSgList(ev);
  if(!L.length) return '';
  const n = L.filter((s, i) => S.sel[i]).length, why = !cands.length ? T('No running session in this project') : !n ? T('Select at least one suggestion') : '';
  let h = '<div class=plesg><div class=plesgh><b>' + esc(T('Suggestions')) + '</b><button type=button class="wkrgb' + (S.req ? ' on' : '') + '" data-plsask' + (why ? ' disabled title="' + esc(why) + '"' : '') + '>' + esc(T('Ask AI') + (n ? ' (' + n + ')' : '')) + '</button></div><ul>'
    + L.map((s, i) => { const t = TV(plEvalSgMsg(s, cat));
      return '<li><label><input type=checkbox data-plsg="' + i + '"' + (S.sel[i] ? ' checked' : '') + '> <span' + (s.cmd ? ' title="' + esc(s.cmd) + '"' : '') + '>' + esc(t) + '</span></label>'
        + '<button type=button class=wkrgb data-plsfix="' + i + '">' + esc(T(s.code === 'redcheck' ? 'Copy command' : 'Fix it myself')) + '</button></li>'; }).join('') + '</ul>';
  if(S.req){
    const cur = cands.find(x => x.sid === S.req.sid) || null, off = !n ? T('Select at least one suggestion') : !cur ? T('No running session in this project') : !cur.login ? T('That session is not logged in to the mailbox') : '';
    const lab = x => archChkCandLabel(x) + (x.ran ? ' · ' + T('ran this pipeline') : '');   // metadata only (dir · sid · model · mailbox id)
    const to = cur && !S.req.pick ? '<span class=plsto>' + esc(lab(cur)) + '</span>' + (cands.length > 1 ? ' <button type=button class=wkrgb data-plsch>' + esc(T('Change')) + '</button>' : '')
      : '<select data-plss>' + (cands.length ? cands.map(x => '<option value="' + esc(x.sid) + '"' + (x.sid === S.req.sid ? ' selected' : '') + '>' + esc(lab(x)) + '</option>').join('') : '<option value="">' + esc(T('None')) + '</option>') + '</select>';
    h += '<div class=archreq role=group aria-label="' + esc(T('Fix request preview')) + '"><div class=archrqh><b>' + esc(T('Fix request preview')) + '</b><label>' + esc(T('To session')) + ' ' + to
      + '</label></div><pre class=archdm>' + esc(S.req.body || '') + '</pre><div class=archrqb><button type=button class="wkrgb archok" data-plsgo' + (off || S.req.busy ? ' disabled' : '') + (off ? ' title="' + esc(off) + '"' : '') + '>'
      + esc(T(archChkGoLabel(S, archChkReqKey(S.req.sid, S.req.body)))) + '</button><button type=button class=wkrgb data-plsx>' + esc(T('Cancel')) + '</button>' + (off ? '<span class=archwhy>' + esc(off) + '</span>' : '') + '</div></div>';
  }
  return h + archChkSentHtml(S) + '</div>';   // same success/error lines and repeat guard as the 84l issues window
}
// Pure: DM body (mailbox wire text, not UI): pipeline file + suggestion lines only (codes, titles, commands — no tool output).
function plEvalFixBody(proj, name, list){
  return 'Please improve pipeline ' + name + ' in ' + proj + ' (.claude/pipelines/' + name + '.json):\n' + list.map(s => '- ' + plEvalSgEn(s)).join('\n')
    + '\nEdit the pipeline file and the gates it names; show the diff before saving.';
}
function plEvalState(p){ const k = PLS.proj + '\n' + ((p && p.name) || ''); if(PLEVAL_S.k !== k) PLEVAL_S = { k, sel: {}, req: null, sent: '', msg: '', init: false }; return PLEVAL_S; }
// Pure: every suggestion starts ticked once per pipeline, so one «Ask AI» press reaches the preview; later unticks stick.
function plEvalPre(S, L){ if(!S.init && L.length){ L.forEach((s, i) => { S.sel[i] = 1; }); S.init = true; } return S; }
// Pure: «7/8» + muted 95% Wilson range (server-computed) · «2/3 agree» = runs at one commit matching the majority verdict.
function plEvalCi(ci){ return ci && ci.hi != null ? ' <span class=pleci title="' + esc(T('Seeded defects n; the range narrows as more are seeded')) + '">' + esc(TV({msg: '95% {lo}–{hi}%', vars: {lo: ci.lo | 0, hi: ci.hi | 0}})) + '</span>' : ''; }
function plEvalAgree(a){ return a && a.n ? '<span class="pleag' + (a.k < a.n ? ' pleag-off' : '') + '">' + esc(TV({msg: '{k}/{n} agree', vars: {k: a.k | 0, n: a.n | 0}})) + '</span>' : ''; }
// Server sentence templates (sidereus/pl_outcome.OC_SENT): msg = fixed English key, numbers are vars (never through T).
const PLE_OC = { gate: 'Gate: {g} of {m} gates confirmed able to fail', proc: 'Procedure: {runs} runs, {jump} order violations blocked',
  result: 'Result: {broke} of {n} passes broke later, fix followed {fixed}',
  lb: 'Review loop-backs: {cur}% of runs (last 30 days) vs {prev}% (30 days before)', lb0: 'Review loop-backs: {cur}% of runs (last 30 days), no earlier data',
  rep: 'Latest report {date} · {path}', norep: 'No report yet' };
const plOcPct = c => c && c.n ? Math.round((c.k | 0) * 100 / c.n) : 0;
// Pure: «Result layer» block — gate / procedure / result facts, loop-back trend, latest report. Counts only, no score.
function plEvalOutcome(ev){
  const o = ev && ev.outcome;
  if(!o || !((o.result && o.result.n) || (o.proc && o.proc.runs))) return '';   // pl_outcome always sends outcome: hide it until there is data
  const g = ev.graded || {}, p = o.proc || {}, r = o.result || {}, lb = o.lb || {}, cur = lb.cur || {}, prev = lb.prev || {};
  const L = [TV({msg: PLE_OC.gate, vars: {g: g.n | 0, m: g.m | 0}}), TV({msg: PLE_OC.proc, vars: {runs: p.runs | 0, jump: p.jump | 0}}),
    TV({msg: PLE_OC.result, vars: {broke: r.broke | 0, n: r.n | 0, fixed: r.fixed | 0}})];
  if(cur.n || prev.n) L.push(TV(prev.n ? {msg: PLE_OC.lb, vars: {cur: plOcPct(cur), prev: plOcPct(prev)}} : {msg: PLE_OC.lb0, vars: {cur: plOcPct(cur)}}));   // no runs in either window: no line
  const rp = ev.rep && ev.rep.date ? TV({msg: PLE_OC.rep, vars: {date: String(ev.rep.date), path: String(ev.rep.path || '')}}) : T(PLE_OC.norep);
  return '<div class=pleoc><b>' + esc(T('Result layer')) + '</b><ul>' + L.map(s => '<li>' + esc(s) + '</li>').join('') + '</ul><div class=pleocr>' + esc(rp) + '</div></div>';
}
function plEvalPanel(ev){
  if(!ev) return '';
  const st = Array.isArray(ev.stages) ? ev.stages : [];
  const need = {}; plEvalSgList(ev).forEach(s => { if(s.code === 'redcheck') need[s.stage] = s.cmd; });   // «red check needed» = no record for the current gate text
  const rows = st.map(s => {
    const c = s.catch, r = PLE_RED[s.red], cmd = need[s.title];
    const cc = !c || !c.n ? '' : c.caught >= c.n ? ' class=plec-all' : c.caught > 0 ? ' class=plec-part' : ' class=plec-none';   // catch colour: all / some / none
    return '<tr><td>' + esc(s.title) + '</td><td' + cc + '>' + (c ? esc(c.caught + '/' + c.n) + plEvalCi(s.ci) : '–') + '</td><td class="pler' + (r ? ' pler-' + r : '') + '">' + (cmd != null ? '<button type=button class=plerneed data-plecp="' + esc(cmd) + '" title="' + esc(cmd) + '">' + esc(T('red check needed')) + '</button>' : r ? '<span class=plerv>' + esc(T(r, 'redcheck')) + '</span>' : '–') + '</td><td>'
      + plEvalAgree(s.agree) + (s.unstable ? '<span class=pleun>' + esc(T('unstable')) + '</span>' : '') + '</td></tr>';
  }).join('');
  const h = ev.holdout;
  const ho = h ? '<tr class=pleho><td>' + esc(T('Holdout')) + '</td><td>' + esc(h.caught + '/' + h.n) + plEvalCi(h.ci) + '</td><td></td><td></td></tr>' : '';
  const empty = !st.some(s => s.catch || PLE_RED[s.red]) && !h;
  if(typeof requestAnimationFrame === 'function') requestAnimationFrame(plEvalPlace);   // placed after paintPipe writes it
  const S = typeof PLS === 'object' ? plEvalPre(plEvalState(plCur()), plEvalSgList(ev)) : { sel: {} }, sg = plEvalSgList(ev).length ? plEvalSgHtml(ev, S, plEvalCands(), typeof plCat === 'function' ? plCat() : null) : '';
  return '<div id=plevp class="thpop plevp">' + (typeof plEvalSec === 'function' ? plEvalSec(ev.security, PLE_SEC_OPEN) : '') + '<table><tr><th>' + esc(T('Stage')) + '</th><th>' + esc(T('Catch')) + '</th><th>' + esc(T('Red check')) + '</th><th>' + esc(T('Agreement')) + '</th></tr>' + rows + ho + '</table>' + (typeof plEvalOutcome === 'function' ? plEvalOutcome(ev) : '')
    + (empty && !sg ? '<div class=hidnote>' + esc(T('No evaluation yet')) + '</div>' : '') + sg + '</div>';
}
// Floating under the button (popAnchor, fixed): an inline panel pushed the canvas down. ⚠Rebuilt by every repaint ⇒ re-anchored each time.
function plEvalPlace(){
  const p = document.getElementById('plevp'), b = document.querySelector('[data-pleval]');
  if(p && b) popAnchor(p, b, { align: 'right', flipY: true });
}
function plEvalClose(focusBack){
  PLEVAL_OPEN = '';
  plPaint();
  const b = document.querySelector('[data-pleval]');
  if(focusBack && b) b.focus();
}
popReg('plevp', '#plevp, [data-pleval]', plEvalClose);
// Pure: relay targets, ordered — live sessions that ran this pipeline (runSid = 48b plLiveRun first, then newest plrun), then
//   live sessions inside the project (84l rule). ⚠A gone run session drops out, so the repo rule is the fallback.
function plEvalRecips(sess, proj, name, runSid){
  const mine = r => r && r.name === name && r.proj === proj;
  const ran = (sess || []).filter(x => x && x.sid && x.state !== 'done' && x.state !== 'gone' && (!x.plat || x.plat === 'cc') && (x.sid === runSid || (x.plrun || []).some(mine)));
  const t1 = x => x.sid === runSid ? Infinity : Math.max(0, ...(x.plrun || []).filter(mine).map(r => +r.t1 || 0));
  const rc = ran.sort((a, b) => t1(b) - t1(a)).map(x => ({ sid: x.sid, model: x.model || '', id: x.mbox || '', login: mboxIn(x), dir: archBase(x.cwd), age: +x.ageSec || 0, ran: true }));
  return rc.concat((typeof archChkFixCands === 'function' ? archChkFixCands(sess, proj) : []).filter(c => !rc.some(r => r.sid === c.sid)));
}
// Pure: default recipient — a mailbox-logged-in run session, else any logged-in one, else the first (preview shows why it cannot send).
function plEvalPick(cands){ return cands.find(x => x.ran && x.login) || cands.find(x => x.login) || cands[0] || null; }
function plEvalCands(){
  const p = typeof plCur === 'function' ? plCur() : null;
  if(!p || typeof SESS === 'undefined') return [];
  let rs = '';
  try{ const lv = typeof plLiveRun === 'function' ? plLiveRun(PLS.proj, p.name) : null; rs = (lv && lv.sid) || ''; }catch(e){ rs = ''; }   // lighting model may be mid-load
  return plEvalRecips(SESS, PLS.proj, p.name, rs);
}
// «Fix it myself»: close the popover, select the stage, pre-fill the draft (unsaved until «Save»), focus the field.
function plEvalFixSelf(s){
  const E = plCurEnt(), cat = plCat(), tp = s.tpl ? plgTpl(cat, s.tpl) : null;
  if(s.code === 'redcheck'){ copyText(s.cmd || ''); note(T('Copied')); return; }
  if(!E || plRO()) return;
  PLEVAL_OPEN = ''; E.first = false;
  if(s.code === 'add-review'){ PLPQ = tp && tp.title ? plgShow(tp.title.ko) : ''; plPaint();
    // At narrow widths the palette stacks below the canvas: bring the filtered list into view or the click looks like a no-op
    // The filter is a substring match («Review» also lists «Security review» first): focus the suggested template's own row
    const el = plRefocus(tp && tp.id ? '.plpal [data-plcadd="' + CSS.escape(tp.id) + '"]' : '', '.plpal .plci:not([hidden]) .plcadd', '.plpal [data-plpq]'), pal = el && el.closest('.plpal');
    if(pal) pal.scrollIntoView({ block: 'nearest' });
    return; }
  const n = E.G.nodes.find(x => x.title === s.stage);
  if(!n){ plPaint(); return; }
  E.sel = { k: 'n', id: n.id };
  if((s.code === 'add-gate' || s.code === 'tighten-gate') && tp && tp.gate && n.gate !== tp.gate){ n.gate = tp.gate; plTouch(); }
  plPaint();
  const el = plRefocus('.plpan [data-plf=gate]');
  if(el){ el.scrollIntoView({ block: 'nearest' }); if(el.select) el.select(); }
}
// Guard + send: only the preview's confirm calls this (no auto-send, AGENTS.md rule 7).
async function plEvalFixSend(){
  const S = PLEVAL_S, q = S.req, p = plCur(), ev = p && plEvalOf(PLS.proj, p.name);
  if(!q || q.busy || !p) return false;
  const list = plEvalSgList(ev).filter((s, i) => S.sel[i]), cur = plEvalCands().find(c => c.sid === q.sid);
  if(!list.length || !cur || !cur.login) return false;
  const key = archChkReqKey(cur.sid, q.body);
  if(S.sent && S.sent.key === key && !q.again){ q.again = true; plPaint(); return false; }   // first click on «Sent · send again» only arms
  q.busy = true; plPaint();
  try{
    const j = await postJSON('/api/dm', { to: cur.id, body: q.body, relay: true, sid: cur.sid, thread: 'eval-fix' });
    if(!j || !j.ok) throw new Error((j && (j.error || j.err)) || '?');
    S.req = null; S.msg = ''; S.sent = { to: archChkCandLabel(cur), at: hhmm(new Date()), key };
    note(T('Requested → {s} · {t}').replace('{s}', () => S.sent.to).replace('{t}', () => S.sent.at));
  }catch(e){ q.busy = false; S.msg = T('Could not send') + ': ' + String((e && e.message) || e); }
  plPaint();
  return true;
}
document.addEventListener('change', e => {
  const t = e.target, pv = t && t.closest && t.closest('#plevp');
  if(!pv) return;
  const S = PLEVAL_S;
  if(t.matches('[data-plsg]')){ if(t.checked) S.sel[t.dataset.plsg] = 1; else delete S.sel[t.dataset.plsg]; if(S.req && !S.req.busy) S.req = null; }
  else if(t.matches('[data-plss]') && S.req){ S.req.sid = t.value; S.req.again = false; }
  else return;
  plPaint();
});
document.addEventListener('click', e => {
  const t = e.target && e.target.closest ? e.target : null, pv = t && t.closest('#plevp');
  if(!pv) return;
  const p = plCur(), ev = p && plEvalOf(PLS.proj, p.name), L = plEvalSgList(ev), S = plEvalState(p);
  let b;
  if((b = t.closest('[data-plecp]'))){ copyText(b.dataset.plecp); note(T('Copied')); return; }
  if((b = t.closest('[data-plsfix]'))){ const s = L[+b.dataset.plsfix]; if(s) plEvalFixSelf(s); return; }
  if(t.closest('[data-plsask]')){
    if(S.req && !S.req.busy) S.req = null;   // second press closes the preview
    else if(!S.req){ S.req = { sid: (plEvalPick(plEvalCands()) || {}).sid || '', pick: false, busy: false, body: plEvalFixBody(PLS.proj, p.name, L.filter((s, i) => S.sel[i])) }; S.msg = ''; }   // S.sent stays: it marks a repeat
    plPaint(); return;
  }
  if(t.closest('[data-plsch]')){ if(S.req && !S.req.busy){ S.req.pick = true; plPaint(); } return; }
  if(t.closest('[data-plsx]')){ if(S.req && !S.req.busy) S.req = null; plPaint(); return; }
  if(t.closest('[data-plsgo]')) plEvalFixSend();
});
document.addEventListener('scroll', () => { if(popIsOpen('plevp')) plEvalPlace(); }, true);
document.addEventListener('click', e => {
  const b = e.target.closest && e.target.closest('[data-pleval]');
  if(!b) return;
  const p = plCur();
  PLEVAL_OPEN = p && PLEVAL_OPEN !== p.name ? p.name : '';
  plPaint();
});
