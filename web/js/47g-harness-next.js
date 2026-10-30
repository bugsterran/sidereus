// Harness «Next step» fold per verdict id (#27): guide text from /api/verdict-guide (docs/verdicts/<id>.md), render + relay only.
// ⚠Guide bodies are server data: esc() only, never T(). Sidereus fixes nothing and stores nothing; open folds live in HN.nx (memory).
// ⚠The relay never sends by itself: «Draft instruction» → preview + recipient pick → «Confirm — send» → /api/dm (AGENTS.md rule 7).
const HN_NX_INC = ['refixed', 'reverted', 'unchecked'], HN_NX_GD = ['skipgate'];
const HN_NX_WHO = { self: 'Yourself', ai: 'Hand to an AI session', owner: 'Owner decision' };
const HN_NXS = { guide: {}, busy: {}, ctx: {}, dr: null };   // guide per UI language · ctx = last rendered row per fold key · dr = open draft
function hnNxOpen(){ return HN.nx || (HN.nx = {}); }
function hnNxLang(){ return typeof LANG !== 'undefined' && LANG === 'en' ? 'en' : 'ko'; }
// One fetch per UI language; a failed load stays empty (folds render nothing) until the next page load.
async function hnNxLoad(){
  const l = hnNxLang();
  if(HN_NXS.guide[l] || HN_NXS.busy[l]) return;
  HN_NXS.busy[l] = 1;
  let v = null;
  try{ v = await hnGet('/api/verdict-guide?lang=' + l); }catch(e){ v = null; }
  HN_NXS.guide[l] = v && typeof v === 'object' && !Array.isArray(v) ? v : {};
  if(typeof hnRepaint === 'function') hnRepaint(true);
}
function hnNxGuide(id){
  const g = HN_NXS.guide[hnNxLang()];
  if(!g){ hnNxLoad(); return null; }
  const x = Object.prototype.hasOwnProperty.call(g, id) ? g[id] : null;
  return x && typeof x === 'object' && HN_NX_WHO[x.who] ? x : null;
}
// Pipelines of the shown project, or null while the list is not loaded (then no pipeline is named).
function hnNxPipes(){
  const d = typeof PLS === 'object' && PLS.data ? PLS.data[PLS.proj] : null;
  return d && d.ok && Array.isArray(d.pipelines) ? d.pipelines.map(q => q && q.name).filter(Boolean) : null;
}
// One line of wire text: no control chars, capped, so a field can never add a line of its own.
function hnNxW(v, max){ return String(v == null ? '' : v).replace(/[\u0000-\u001f\u007f]+/g, ' ').trim().slice(0, max || 200); }
// Pure: relay text (English wire, never T()) = verdict id · level · file/base name · event · counts · short heads · mode
// (+ pipeline when the guide names one that exists). ⚠Metadata only (rule 1): every other field of ctx is dropped.
function hnNxBody(id, ctx, proj, guide, pipes){
  const x = ctx && typeof ctx === 'object' ? ctx : {}, vd = x.vd && typeof x.vd === 'object' ? x.vd : {}, vp = vd.vp && typeof vd.vp === 'object' ? vd.vp : {};
  const L = ['Harness verdict: ' + hnNxW(id, 40) + (vd.lvl === 'bad' || vd.lvl === 'check' ? ' (' + vd.lvl + ')' : '')];
  if(proj) L.push('Project: ' + hnNxW(proj, 300));
  const file = x.path ? x.path : x.cmd || x.src ? hnBase(x.cmd || x.src) : vp.pipe ? '.claude/pipelines/' + vp.pipe + '.json' : x.name;   // hook cmd only as its base name, never args
  if(file) L.push('File: ' + hnNxW(file, 300));
  if(x.ev) L.push('Event: ' + hnNxW(x.ev, 60));
  const n = [['runs', x.n], ['days', vp.days], ['timeout s', vp.timeout], ['bytes', vp.bytes], ['commits', x.commits], ['count', x.count]]
    .filter(a => a[1] != null && a[1] !== '' && isFinite(Number(a[1]))).map(a => a[0] + ' ' + Number(a[1]));
  if(n.length) L.push('Counts: ' + n.join(' · '));
  const hd = s => { const h = s && typeof s === 'object' ? String(s.head || '') : ''; return /^[0-9a-f]{4,64}$/i.test(h) ? h.slice(0, 8) : ''; };
  const fh = hd(x.fail), ph = hd(x.pass);
  if(fh || ph) L.push('Heads: ' + (fh || '?') + ' → ' + (ph || '?'));
  if(typeof x.mode === 'string' && /^[a-z0-9_-]{1,20}$/.test(x.mode)) L.push('Mode: ' + x.mode);
  const pl = guide && typeof guide.pipeline === 'string' ? guide.pipeline : '';
  if(pl && Array.isArray(pipes) && pipes.indexOf(pl) >= 0) L.push('Pipeline: ' + pl);
  L.push('Guide: docs/verdicts/' + hnNxW(id, 40) + '.md — read it, then act on this one item.');
  return L.join('\n');
}
// Fold key: verdict id + the row's own content (incident mode|fail ts · row scope/src/event/matcher/path/name); a guard code has one fold.
// ⚠Never vd.id: it is the row's list position (harness_verdict.py), so a reordered reload moved an open fold under another row.
function hnNxKey(id, x){
  x = x || {};
  const s = v => String(v == null ? '' : v);
  const r = HN_NX_GD.indexOf(id) >= 0 ? '' : x.fail && x.fail.ts != null ? s(x.mode) + '|' + s(x.fail.ts)
    : [x.scope, x.src, x.ev, x.matcher, x.path, x.name, x.cmd ? hnBase(x.cmd) : ''].map(s).join('|');
  return id + '\n' + r;
}
// Recipients: live Claude sessions of the project that are logged into the mailbox (84l archChkFixCands). The pick is not stored.
function hnNxCands(){ return typeof archChkFixCands === 'function' ? archChkFixCands(typeof SESS !== 'undefined' ? SESS : [], PLS.proj).filter(c => c.login) : []; }
function hnNxDraftHtml(k){
  const D = HN_NXS.dr;
  if(!D || D.key !== k) return '';
  const cs = hnNxCands(), cur = cs.find(c => c.sid === D.sid) || cs[0];
  return '<div class=hnnxdr><label>' + esc(T('To session')) + ' <select data-hnnxs>' + (cs.length ? cs.map(c => '<option value="' + esc(c.sid) + '"' + (cur && c.sid === cur.sid ? ' selected' : '') + '>' + esc(archChkCandLabel(c)) + '</option>').join('')
      : '<option value="">' + esc(T('None')) + '</option>') + '</select></label><pre class=hnnxpre>' + esc(D.body) + '</pre>'
    + '<button type=button class="wkrgb archok" data-hnnxgo' + (!cur || D.busy ? ' disabled' : '') + '>' + esc(T(D.busy ? 'Sending…' : 'Confirm — send')) + '</button>'
    + (D.msg ? ' <i class=hntm>' + esc(D.msg) + '</i>' : '') + '</div>';
}
// «Next step» fold: Meaning / Why it matters / Who acts / Next step (+ «Safe to ignore when» for owner, + «Draft instruction» for ai).
// Unknown id or guide not loaded = nothing.
function hnNxFold(id, ctx){
  const g = typeof id === 'string' && id ? hnNxGuide(id) : null;
  if(!g) return '';
  const k = hnNxKey(id, ctx), ln = (lb, v) => '<div class=hnnxl><b>' + esc(T(lb)) + '</b> <span>' + esc(v == null || v === '' ? '—' : String(v)) + '</span></div>';
  HN_NXS.ctx[k] = { id, x: ctx };
  return '<details class=hnnx data-hnnx="' + esc(k) + '"' + (hnNxOpen()[k] ? ' open' : '') + '><summary>' + esc(T('Next step')) + '</summary>'
    + ln('Meaning', g.meaning) + ln('Why it matters', g.why) + ln('Who acts', T(HN_NX_WHO[g.who]))
    + (g.who === 'self' ? '<div class=hnnxl><b>' + esc(T('Next step')) + '</b> <code class=hnrc>' + esc(String(g.next || '—')) + '</code></div>' : ln('Next step', g.next))
    + (g.who === 'owner' ? ln('Safe to ignore when', g.ignore) : '')
    + (g.who === 'ai' ? '<div class=hnnxl><button type=button class=hnnxb data-hnnxd="' + esc(k) + '">' + esc(T('Draft instruction')) + '</button></div>' + hnNxDraftHtml(k) : '')
    + '</details>';
}
// «Draft instruction»: freeze the preview body; what is shown is what «Confirm — send» posts.
function hnNxDraft(k){
  const c = HN_NXS.ctx[k];
  if(!c) return;
  if(HN_NXS.dr && HN_NXS.dr.key === k){ HN_NXS.dr = null; return; }
  const cs = hnNxCands();
  HN_NXS.dr = { key: k, id: c.id, body: hnNxBody(c.id, c.x, PLS.proj, hnNxGuide(c.id), hnNxPipes()), sid: (cs[0] || {}).sid || '', busy: false, msg: '' };
}
// Only the confirm button calls this.
async function hnNxSend(){
  const D = HN_NXS.dr;
  if(!D || D.busy) return false;
  const cur = hnNxCands().find(c => c.sid === D.sid) || hnNxCands()[0];
  if(!cur) return false;
  D.busy = true; hnRepaint(false);
  try{
    const j = await postJSON('/api/dm', { to: cur.id, body: D.body, relay: true, sid: cur.sid, thread: 'harness:' + D.id });
    if(!j || !j.ok) throw new Error((j && (j.error || j.err)) || '?');
    HN_NXS.dr = null;
    note(T('Requested → {s} · {t}').replace('{s}', () => archChkCandLabel(cur)).replace('{t}', () => hhmm(new Date())));
  }catch(e){ D.busy = false; D.msg = T('Could not send') + ': ' + String((e && e.message) || e); }
  hnRepaint(false);
  return true;
}
// ⚠Capture phase: a fold inside a hook chip must not reach 47b's «open file» click/Enter handlers.
document.addEventListener('click', e => {
  const t = e.target, f = t && t.closest && t.closest('.hnw .hnnx');
  if(!f) return;
  e.stopPropagation();
  if(HN.go){ HN.go = null; const a = document.activeElement; if(a && a.classList && a.classList.contains('hngo') && a.blur) a.blur(); }   // same as 47b's click: the target highlight ends on any click in the view
  const d = t.closest('[data-hnnxd]');
  if(d){ hnNxDraft(d.dataset.hnnxd); hnRepaint(false); return; }
  if(t.closest('[data-hnnxgo]')) hnNxSend();
}, true);
document.addEventListener('keydown', e => { if(e.target && e.target.closest && e.target.closest('.hnw .hnnx')) e.stopPropagation(); }, true);
document.addEventListener('change', e => {
  const s = e.target && e.target.closest && e.target.closest('.hnw [data-hnnxs]');
  if(s && HN_NXS.dr) HN_NXS.dr.sid = s.value;
}, true);
// ⚠'toggle' does not bubble: capture phase.
document.addEventListener('toggle', e => {
  const t = e.target;
  if(t && t.classList && t.classList.contains('hnnx') && t.dataset) hnNxOpen()[t.dataset.hnnx] = t.open;
}, true);
