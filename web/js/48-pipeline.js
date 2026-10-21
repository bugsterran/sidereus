// «Pipelines» main tab (mainView 'pipe', feature `pipeline`, docs/dev/PIPELINE.md step 2). Moved out of the «Tokens» tab.
// Project combobox → pipeline select → canvas editor (48c graph model, 48d canvas); «Save» = diff preview, «Confirm» writes (/api/pipelines/save).
// Stage `task` arrives as `instr` (user-written config, edited in the node panel); pipeline `rules` never leaves the server.
// ⚠Korean on purpose: matched against stage titles as saved in the pipeline JSON (data, not UI text).
const PL_JUDGED = ['설계', '리뷰', '원인'];     // judgment stages: a lowered model gets the ⚠ hint (judgment output is not machine-checked, so a weaker model fails silently)
const PL_LOW = ['sonnet', 'haiku'];
const PLS = { projs: null, proj: lsGet('sidereus.plproj', ''), data: {}, busy: {},
  g: {}, diff: null, msg: '', saving: false, off: false, wf: null };   // g = canvas editor entries (48d plEnt) · wf = open Workflow run {sid, id} (48g)
// ⚠PLS.sel is remembered per project: one shared value opened a pipeline picked elsewhere as a borrowed read-only view in a project with none.
// The legacy single key `sidereus.plsel` has no project, so it is ignored.
function plSelMap(){ const m = lsJson('sidereus.plselp', {}); return m && typeof m === 'object' && !Array.isArray(m) ? m : {}; }
function plSelBind(o){
  let m = null;
  Object.defineProperty(o, 'sel', { enumerable: true,
    get(){ if(!m) m = plSelMap(); const v = m[o.proj]; return typeof v === 'string' ? v : ''; },
    set(v){ if(!m) m = plSelMap(); if(v) m[o.proj] = String(v); else delete m[o.proj]; lsSetJson('sidereus.plselp', m); } });
}
plSelBind(PLS);
// «Pipelines | Harness» view toggle (harness body = 47b-harness.js hnHtml, same project chips); hidden when feature `harness` is off.
let PLVIEW = lsGet('sidereus.plview', 'pipe') === 'harness' ? 'harness' : 'pipe';
function plHnOn(){ return PLVIEW === 'harness' && FEATS.harness !== false && typeof hnHtml === 'function'; }
function plViewSeg(){
  if(FEATS.harness === false) return '';
  return '<div class=tkvs>' + [['pipe', 'Pipelines'], ['harness', 'Harness']].map(([k, en]) => '<button class="wkrgb'
    + (k === (plHnOn() ? 'harness' : 'pipe') ? ' on" aria-pressed="true' : '" aria-pressed="false') + '" data-plv="' + k + '">' + esc(T(en)) + '</button>').join('') + '</div>';
}
document.addEventListener('click', e => {
  const b = e.target.closest && e.target.closest('.wkrgb[data-plv]');
  if(!b || b.dataset.plv === PLVIEW) return;
  const hadF = document.activeElement === b;   // ⚠the repaint drops focus to <body> (46 kbHold)
  PLVIEW = b.dataset.plv === 'harness' ? 'harness' : 'pipe';
  lsSet('sidereus.plview', PLVIEW);
  plPaint();
  if(hadF) kbHold('.wkrgb[data-plv].on');
});
async function plLoadProjs(){
  if(PLS.projs || PLS.busy['']) return;
  PLS.busy[''] = 1;
  try{ PLS.projs = await getJSON('/api/pipelines'); }
  catch(e){ PLS.projs = { ok: false, msg: String((e && e.message) || e) }; PLS.off = !!(e && e.status === 404); }
  PLS.busy[''] = 0;
  // Last-picked project if it has pipelines, else the first one that does (★2026-10-01: opened on a project without any).
  // ⚠A self-only chip (Sidereus clone, no history/session there) is never the default: a fresh clone opened its developer pipelines.
  const has = ((PLS.projs.ok && PLS.projs.projects) || []).filter(x => !x.self_only || x.path === PLS.proj).map(x => x.path);
  if(has.length && !has.includes(PLS.proj) && PLS.pend !== PLS.proj) PLS.proj = has[0];   // a jump made before the list loaded keeps its project
  PLS.pend = '';
  plPaint();
}
async function plLoad(proj, force){
  if(!proj || PLS.busy[proj] || (PLS.data[proj] && !force)) return;
  PLS.busy[proj] = 1;
  let v;
  try{ v = await getJSON('/api/pipelines?proj=' + encodeURIComponent(proj)); }
  catch(e){ v = { ok: false, msg: String((e && e.message) || e), status: e && e.status }; }
  PLS.busy[proj] = 0;
  PLS.data[proj] = v;
  const pk = document.activeElement && document.activeElement.closest ? document.activeElement.closest('[data-ppk]') : null;
  plPaint();
  const nb = pk && !pk.isConnected && typeof ppBtn === 'function' ? ppBtn(pk.dataset.ppk) : null;   // ⚠the repaint replaced the focused picker button: focus its successor
  if(nb && document.activeElement !== nb) nb.focus({ preventScroll: true });
}
// {proj: [pipeline names]} running now (marked on project chips, like the timeline).
// Metadata only: wf run flag + [pl:] description tags + the main agent's [pl:] mark.
// known = plKnown() {path: {n, names|null}}: a candidate (cwd + repos) is marked only if it owns that pipeline
// (⚠a cart-origin session running cart-api's bugfix dots cart-api only). known null (list not loaded yet) = no filter.
// orph (optional array) collects {sid, name} of tagged runs no project could take (plAway).
function plLiveProjs(sess, mem, known, orph){
  const out = {};
  let wait = false;
  const owns = (p, n) => !known || (known[p] && known[p].n > 0 && (n === '?' || !known[p].names || known[p].names.includes(n)));
  const add = (p, n) => { if(!owns(p, n)) return; const l = out[p] || (out[p] = []); if(!l.includes(n)) l.push(n); };
  // ⚠A session whose arch-map run already shows on its target (ARCHRUN, below) must not also dot the Sidereus repo:
  //   its repos include the pipeline's home, so the tag landed there too and one run read «Running 2».
  const agSid = new Set(typeof plAgRun === 'function' ? Object.keys(ARCHRUN || {}).filter(p => plAgRun(p)).map(p => ARCHRUN[p].sid).filter(Boolean) : []);
  (sess || []).forEach(x => {
    if(!x) return;
    const names = plTagNames(x, mem).filter(n => !(n === 'arch-map' && agSid.has(x.sid))), aw = plAway(x, names, known);
    names.forEach(n => plHomes(x, n, known).forEach(p => add(p, n)));
    Object.keys(aw.home).forEach(n => add(aw.home[n], n));
    if(orph) aw.orph.forEach(n => orph.push({ sid: x.sid, name: n }));
    wait = wait || aw.wait;
  });
  // Sidereus tool pipeline (48h) on its target project: not owned there, so the `owns` filter is bypassed.
  if(typeof plAgRun === 'function') Object.keys(ARCHRUN || {}).forEach(p => { if(plAgRun(p)){ const l = out[p] || (out[p] = []); if(!l.includes('arch-map')) l.push('arch-map'); } });
  if(wait && typeof plLoadAll === 'function') plLoadAll();   // a tag's home is undecided until every list is loaded
  return out;
}
// Loads every known project's pipeline list (plLoad guards repeats); plAway needs them all to find a tag's home.
function plLoadAll(){
  ((PLS.projs && PLS.projs.ok && PLS.projs.projects) || []).forEach(k => { if(k.n > 0 && !PLS.data[k.path]) plLoad(k.path, false); });
}
// Projects a session's run of `n` belongs to, among its cwd + repos that own `n`.
// ⚠One run must land in ONE project: an app-origin session that also edits app-api, where both have a «bugfix», showed it twice.
// ⇒ Pick the project whose pipeline fits the tagged subagents (stage title present +1, its agent = the sub's type +2);
//   the cwd only breaks a tie. cwd-first alone sent an app-api bugfix (run by app-api agents) to app-origin.
function plHomes(x, n, known){
  const c = [x.cwd].concat(x.repos || []).filter((p, i, a) => p && a.indexOf(p) === i);
  const ownsN = p => !known || (known[p] && known[p].n > 0 && (n === '?' || !known[p].names || known[p].names.includes(n)));
  // ⚠The server's recorded run project (plrun proj, open run first, then newest) beats stage-fit scoring: a same-named
  //   pipeline elsewhere with better-fitting stage agents took the run off the project that actually ran it.
  const rp = (x.plrun || []).filter(r => r && r.name === n && r.proj && ownsN(r.proj))
    .sort((a, b) => (!a.end - !b.end) || ((a.t1 || 0) - (b.t1 || 0))).pop();
  if(rp) return [rp.proj];
  if(!known) return c;
  const own = c.filter(ownsN);
  if(own.length < 2) return own;
  // ⚠Scoring needs every owner's stage list: an unloaded one scored 0 and the run stayed on the cwd project. Load them
  //   (plLoad repaints when done, so the pick corrects itself a moment later).
  if(typeof PLS === 'object' && typeof plLoad === 'function') own.forEach(p => { if(!PLS.data[p]) plLoad(p, false); });
  const tags = (x.sub || []).map(a => ({ d: plDescStage(a && a.lab), ty: plLabType(a && a.lab) })).filter(o => o.d && o.d.name === n);
  const score = p => {
    const q = (((typeof PLS === 'object' && PLS.data[p]) || {}).pipelines || []).find(z => z.name === n);
    if(!q) return 0;
    return tags.reduce((t, o) => { const st = (q.stages || []).find(z => plTk(z.title) === o.d.title); return t + (st ? 1 + (st.agent && st.agent === o.ty ? 2 : 0) : 0); }, 0);
  };
  const sc = own.map(score), hi = Math.max(...sc), best = own.filter((p, i) => sc[i] === hi);
  return best.length === 1 ? best : best.includes(x.cwd) ? [x.cwd] : [best[0]];
}
// Pipeline names a session runs now: wf run flag + [pl:] description tags + the main agent's own stage (metadata only).
function plTagNames(x, mem){
  const names = [];
  (x.wf || []).forEach(r => { if(r && r.name === 'pipeline' && r.run === true) names.push(plRunName(r, mem, x.sid) || '?'); });
  (x.sub || []).forEach(a => { const d = plDescStage(a && a.lab); if(d && d.name !== '-') names.push(d.name); });
  // Main agent's own [pl:] stage (agents.plm_of). ⚠The marker lives 2 min and every tagged Bash renews it, even after the
  // hook already closed the run (last main stage sets end on its first Bash), so an ended run of that name never dots.
  const pr = x.plm && (x.plrun || []).find(r => r && r.name === x.plm.name);
  if(x.plm && x.plm.name && x.plm.name !== '-' && !(pr && pr.end)) names.push(x.plm.name);
  // Open server runs too: plrun is written at the first [pl:] call, subagent labels lag up to the 20 s agent-meta TTL (Timeline already showed it).
  if(typeof plPrLive === 'function') (x.plrun || []).forEach(r => { if(r && r.name && !r.end && plPrLive(r) && !names.includes(r.name)) names.push(r.name); });
  return names;
}
// A session launched in another folder (cwd/repos own no pipeline of that name): home = the one known project owning it.
// ⚠Two owners = ambiguous, never guessed (orph). wait = a known project's list is not loaded yet, so nothing is decided.
function plAway(x, names, known){
  const r = { home: {}, orph: [], wait: false };
  if(!known) return r;
  const ks = Object.keys(known).filter(p => known[p].n > 0);
  const own = (p, n) => known[p] && known[p].n > 0 && (!known[p].names || known[p].names.includes(n));
  names.forEach(n => {
    if(n === '?' || r.home[n] || r.orph.includes(n) || [x.cwd].concat(x.repos || []).some(p => p && own(p, n))) return;
    if(ks.some(p => !known[p].names)){ r.wait = true; return; }
    const hit = ks.filter(p => known[p].names.includes(n));
    if(hit.length === 1) r.home[n] = hit[0]; else r.orph.push(n);
  });
  return r;
}
function plKnown(){
  if(!PLS.projs || !PLS.projs.ok) return null;
  const k = {};
  (PLS.projs.projects || []).forEach(x => {
    const d = PLS.data[x.path];
    k[x.path] = { n: x.n, names: d && d.ok && d.pipelines ? d.pipelines.map(q => q.name) : null };
  });
  return k;
}
// Tab count = distinct (project, name) pairs; known null = distinct names only (cwd + repos would count one run several times).
function plLiveN(live, known){ return known ? Object.values(live).reduce((a, l) => a + l.length, 0) : new Set([].concat(...Object.values(live))).size; }
function plLiveDot(n){ return '<i class=mvdot title="' + esc(TV({msg: '{n} pipelines running', vars: {n: n}})) + '"></i>'; }
// Projects = live projects (structure tab's strProjList) ∪ known projects that have .claude/pipelines.
// Project combobox + picker popover (08b ppComboHtml); «+ Add project» sits in the picker footer.
// ⚠The × of an added project is a sibling button: #ppop lives outside .plw, where the [data-plprojrm] handler never sees it.
// ⚠Not data-plrm: 48b's run-model select (select.plrsel) carries data-plrm, so a click on it removed a project.
function plChips(){
  const m = new Map(), live = plLiveProjs(SESS, plMem(), plKnown());
  ((PLS.projs && PLS.projs.projects) || []).forEach(x => { if(!PROJ_GONE.has(x.path)) m.set(x.path, { p: x.path, n: x.n, last: !!x.self_only }); });   // ⚠the list is fetched once; a folder deleted later is still in it
  (typeof strProjList === 'function' ? strProjList() : []).forEach(e => { const o = m.get(e.p) || { p: e.p, n: 0 }; o.live = e.open > 0; m.set(e.p, o); });
  if(PLS.proj && PROJ_GONE.has(PLS.proj)) PLS.proj = m.size ? m.keys().next().value : '';   // selected folder deleted -> first listed project
  if(PLS.proj && !m.has(PLS.proj)) m.set(PLS.proj, { p: PLS.proj, n: 0 });
  const added = (PLS.projs && PLS.projs.added) || [];   // only «+ Add project» projects get ×
  const items = [...m.values()].map(e => Object.assign(e, { name: strShort(e.p), run: !!live[e.p] }));
  // Button = name + live dot; the pipeline file count lives in the tooltip and the popover rows only.
  const badge = e => (live[e.p] ? plLiveDot(live[e.p].length) : '');
  const rm = PLS.proj && added.includes(PLS.proj) ? '<button type=button class="strp plrm" data-plprojrm="' + esc(PLS.proj) + '" title="' + esc(T('Remove from list')) + '" aria-label="' + esc(T('Remove from list')) + '">×</button>' : '';
  return '<div class=plchips>' + ppComboHtml({ k: 'pl', label: T('Project'), items: items, cur: PLS.proj, rkey: 'sidereus.plrecent', badge: badge,
    tip: e => e.p + (e.n ? '\n' + TV({msg: '{n} pipelines', vars: {n: e.n}}) : ''),
    note: e => (e.n ? ' <small class=strpc>' + e.n + '</small>' : ''),
    pick: plPickProj, extra: plAddForm(), onExtra: plBrOpen }) + rm + '</div>';
}
function plPickProj(p){
  PLS.proj = p; lsSet('sidereus.plproj', PLS.proj); PLNEW = null; PLS.std = ''; PLS.wf = null; PLS.diff = null; PLS.del = null; PLS.msg = ''; plPaint();
}
// «+ Add project»: the person adds a folder explicitly, never automatically; opens the folder browser (48f plBrOpen).
// ⚠own attribute: 48d's «+ Custom stage»/«+ Stage» use data-pladd, so sharing it opened the folder modal on every stage add.
function plAddForm(){
  return '<button class="strp pladd" data-plprojadd>' + esc(T('+ Add project')) + '</button>';
}
async function plProjPost(url, path){
  let r;
  try{ r = await postJSON(url, { path: path }); }
  catch(x){ r = x.body || { ok: false, err: String((x && x.message) || x) }; }
  if(r && r.ok && PLS.projs){ PLS.projs = null; plLoadProjs(); }
  return r || { ok: false, err: '' };
}
// Returns the server reply; the caller (48f modal) shows r.err.
async function plAddGo(path){
  const r = await plProjPost('/api/pipelines/projects/add', path);
  if(r.ok){ PLS.proj = r.path; lsSet('sidereus.plproj', PLS.proj); PLS.data[r.path] = null; plPaint(); }
  return r;
}
async function plRemove(path){
  if(!confirm(T('Remove from the list? (folder and files stay)') + '\n' + path)) return;
  const r = await plProjPost('/api/pipelines/projects/remove', path);
  if(!r.ok) alert(T('Could not remove') + (r.err ? ' — ' + T(r.err) : ''));
}
function plCur(){
  const d = PLS.data[PLS.proj];
  const ps = (d && d.ok && d.pipelines) || [];
  const st = PLS.std && ((d && d.ok && d.std) || []).find(x => x.name === PLS.std);   // unsaved «Standard templates» draft (48e plStdBody)
  if(st) return Object.assign({}, st, { name: 'std:' + st.name, key: st.name });   // ⚠own editor key: never share plEnt with a saved file of the same name
  const bp = plBorrowOf(d, PLS.sel);   // read-only pipeline defined in another project (48h)
  if(bp) return bp;
  if(!ps.length){ const sg = (d && d.ok && d.suggest) || []; return sg[Math.min(PLS.sugI || 0, sg.length - 1)] || null; }   // unsaved «Suggested» (48e plSugBody)
  return ps.find(x => x.name === PLS.sel) || ps[0] || null;
}
// Pipeline combobox (08b ppComboHtml, same look and popover as the project picker): this project's own pipelines only.
// sel null = none open (Workflow / arch-map / borrowed / draft view): the button reads «—». Borrowed runs are 48h chips.
// ⚠Badges carry only what changes on a click or a run start/end (⚠ invalid, • dirty, live dot): the poll repaints this HTML.
function plPickHtml(ps, sel, runs){
  if(!ps.length) return '';
  const items = ps.map(x => ({ p: x.name, name: x.name, title: x.title || x.name, ok: x.ok, dirty: plDirty(x.name), run: runs.includes(x.name) }));
  const mark = e => (e.ok ? '' : ' ⚠') + (e.dirty ? ' •' : '');
  return plComboHtml({ items: items, cur: sel ? sel.name : '', mark: mark, badge: e => esc(mark(e)) + (e.run ? plLiveDot(1) : '') });
}
// Shared by plPickHtml and the suggestion picker (48e plSugBody): key 'plsel', flat list, no recent, pick = plSelPick.
function plComboHtml(o){
  const mark = o.mark || (() => '');
  const row = (e, i) => '<div class="cmdki' + (PPS && i === PPS.i ? ' on' : '') + (e.p === o.cur ? ' ppcur' : '') + '" role=option data-ppi="' + i + '" title="' + esc(e.title || e.name) + '">'
    + '<span class=cmdkp>' + esc(e.name + mark(e)) + '</span>' + (e.run ? '<i class=mvdot></i>' : '') + '</div>';
  return '<div class=plchips>' + ppComboHtml({ k: 'plsel', label: T('Pipeline'), none: '—', items: o.items, cur: o.cur, badge: o.badge,
    ph: T('Find a pipeline'), empty: T('No matching pipelines'), flat: q => ppFilter(o.items, q), rowHtml: row, pick: plSelPick }) + '</div>';
}
// Head row items: in a .pltop (hd given, plMainBody) or as a standalone .plnames row (tests, callers without a head).
function plHeadRow(hd, html){ if(hd){ hd.row = html; return ''; } return '<div class=plnames>' + html + '</div>'; }
function plBody(ov, hd){
  const d = PLS.data[PLS.proj];
  if(!PLS.proj) return '<div class=hidnote>' + esc(T('Pick a project')) + '</div>';
  if(!d) return '<div class=hidnote>' + esc(T('Loading…')) + '</div>';
  // 400 = outside allowed_projects(): say how to get in (run a Claude session there once), not just «refused». ⚠never a raw «HTTP 400»
  if(!d.ok) return '<div class=hidnote>' + (d.status === 400 ? esc(T('Pipelines are saved in .claude/pipelines/ inside the project, so they open only for folders where a Claude session has run.'))
    + '<br>' + esc(T('Open a Claude session in this folder once and «+ New pipeline» appears here.'))
    : esc(T('Could not read the pipelines') + (d.msg ? ' — ' + d.msg : ''))) + '</div>';
  const ps = d.pipelines || [];
  // Running pipelines of this project get the same live dot as the project chips (after the name, like chips and timeline rows), so the one to open is visible on its button.
  const runs = plLiveProjs(SESS, plMem(), plKnown())[PLS.proj] || [];
  const names = sel => plPickHtml(ps, sel, runs);
  const ag = typeof plAgRun === 'function' ? plAgRun(PLS.proj) : null, agc = ag && !plBorrowOf(d, ARCH_PL) ? plAgChip(ag, PLAG) : '';   // Sidereus tool pipeline running here (48h, read-only); a borrowed row replaces the chip
  const wfb = wfBtns(PLS.proj) + agc + plBorrowChips(d), wfv = PLS.wf && wfBody(PLS.wf.sid, PLS.wf.id);   // «Workflow» group + open run (48g, read-only)
  if(agc && PLAG) return plHeadRow(hd, names(null) + plNewBtn(!ps.length) + wfb) + plNewForm() + plAgBody(ag);
  if(wfv) return plHeadRow(hd, names(null) + plNewBtn(!ps.length) + wfb) + plNewForm() + wfv;
  if(PLS.std){ const sp = plCur(); if(sp && sp.std) return plStdBody(d, sp, hd); }
  const bp = plBorrowOf(d, PLS.sel);
  if(bp) return plBorrowBody(d, bp, plHeadRow(hd, names(null) + plNewBtn(!ps.length) + wfb) + plNewForm(), ov);
  if(!ps.length && (d.suggest || []).length) return plSugBody(d, agc + plBorrowChips(d), hd);
  if(!ps.length) return plTplPick() + plHeadRow(hd, names(null) + plNewBtn(1) + wfb) + plNewForm() + (PLS.msg ? '<div class=hidnote>' + esc(PLS.msg) + '</div>' : '');
  const p = plCur();
  const list = plHeadRow(hd, names(p) + plNewBtn() + wfb) + plNewForm();
  // ⚠a schema-breaking file has no editor, so «Force delete» is its only way out (same /delete guards: preview + confirm, moved to backup)
  if(!p.ok) return list + '<div class=hidnote>' + esc(T('The file breaks the schema — fix it by hand')) + '</div><ul class=plerrs>'
    + p.errs.map(x => '<li>' + esc(x) + '</li>').join('') + '</ul>'
    + (p.from ? '' : '<div class=plbar><span class=plact><button class="wkrgb pldl" data-pldel' + (PLS.saving ? ' disabled' : '') + ' title="' + esc(T('Moves the file to the backup folder without reading it')) + '">' + esc(T('Force delete')) + '</button></span></div>')
    + plDelPrev(p) + (PLS.msg ? '<div class=hidnote>' + esc(PLS.msg) + '</div>' : '');
  const models = d.models || [];
  const lv = plViewRun(PLS.proj, p.name), lt = lv ? (lv.lt || plLight(p.stages, lv.run)) : null;   // a run picked in the head menu, else the live one (48b)
  const cv = plCanvas(p, d, lt);
  const dirty = plDirty(p.name);
  // Live run status sits between the title and the actions: on its own row it pushed the buttons above the progress bar.
  const cov = plGateCov(plEnt(p).G);   // from the editor graph: unsaved gate edits count
  const ev = p.sha && !p.std ? plEvalOf(PLS.proj, p.name) : null; plEvalCov(cov, ev, dirty);   // saved file only (48i)
  const bar = '<div class=plbar><b>' + esc(p.title) + '</b><span class="plcov' + (cov.n < cov.m ? ' plcovlo' : '') + '" title="' + esc(TV({msg: 'Stages machine-checked by a gate command: {n} of {m}', vars: {n: cov.n, m: cov.m}})) + '">' + esc(TV({msg: 'Gates {n}/{m}', vars: {n: cov.n, m: cov.m}})) + '</span>' + plEvalHead(ev, PLEVAL_OPEN === p.name) + plLiveHead(lv, lt) + '<span class=plact>'   // right-aligned, colour-coded action group (43-pipeline.css)
    // Run first (primary; relays a run request to a session), then a divider, then the file operations; Delete last.
    + '<button class="wkrgb plrn' + (PLRUN && PLRUN.name === p.name ? ' on' : '') + '" data-plrun' + (dirty ? ' disabled title="' + esc(T('Save before running')) + '"' : '') + '>' + esc(T('Run')) + '</button>'
    + '<span class=plsep aria-hidden=true></span>'   // Save always follows, so the divider never trails
    + (dirty ? '<button class="wkrgb" data-plreset>' + esc(T('Undo')) + '</button>' : '')
    + '<button class="wkrgb plsv" data-plsave' + (dirty && cv.ok && !PLS.saving ? '' : ' disabled') + (cv.ok ? '' : ' title="' + esc(T('Fix the red items before saving')) + '"') + '>' + esc(T('Save')) + '</button>'
    + (p.std || !p.sha ? '' : '<button class="wkrgb pldl" data-pldel' + (PLS.saving ? ' disabled' : '') + '>' + esc(T('Delete')) + '</button>') + '</span></div>';   // unsaved draft: no file
  const diff = PLS.diff && PLS.diff.name === p.name ? '<div class=pldiff><div class=brh2><b>' + esc(T('Changes', 'preview')) + '</b> <i>.claude/pipelines/'
    + esc(p.name) + '.json</i></div><pre>' + diffHtml(PLS.diff.text, agLang('x.json')) + '</pre>' + plRenameWarn(p, lv) + '<div class=plbar>'
    + '<button class="wkrgb" data-plok' + (PLS.saving ? ' disabled' : '') + '>' + esc(T('Confirm')) + '</button>'
    + '<button class="wkrgb" data-plno>' + esc(T('Cancel')) + '</button></div></div>' : '';
  return list + bar + (PLEVAL_OPEN === p.name ? plEvalPanel(ev) : '') + plDelPrev(p) + cv.html + (ov || '') + plRunTable(lv, p) + plRunPanel(p, models)
    + (PLS.msg ? '<div class=hidnote>' + esc(PLS.msg) + '</div>' : '') + diff;
}
// Delete preview: what moves where (rule 7: moved to the backup folder, never deleted)
function plDelPrev(p){
  return PLS.del && PLS.del.name === p.name ? '<div class=pldiff><div class=brh2><b>' + esc(T('Delete pipeline')) + '</b></div><pre>'
    + esc(PLS.del.path) + '\n→ ' + esc(T('Backup (expected)')) + ' ' + esc(PLS.del.to) + '</pre><div class=hidnote>' + esc(T('The file is moved to the backup folder — move it back to undo')) + '</div><div class=plbar>'
    + '<button class="wkrgb" data-pldelok' + (PLS.saving ? ' disabled' : '') + '>' + esc(T('Confirm')) + '</button>'
    + '<button class="wkrgb" data-pldelno>' + esc(T('Cancel')) + '</button></div></div>' : '';
}
// «Apply» = how new sessions use pipelines (hooks/pipelines_brief.py reads config `pipeline_apply` at SessionStart).
const PL_APPLY = [['auto', 'Auto', 'Picks the pipeline that fits the request and runs it · skips unneeded stages'],
  ['ask', 'Ask each time', 'Asks which pipeline to use before a request that fits one · not for questions or one-line fixes'],
  ['off', 'Off', 'Sends no pipeline brief to sessions']];
function plApplySeg(d){
  const a = d && d.ok && d.apply;
  if(!a) return '';
  return '<div class="plbar plapply"><b>' + esc(T('Apply')) + '</b><div class=tkvs>' + PL_APPLY.map(([k, en, te]) => '<button class="wkrgb'
    + (k === a.mode ? ' on' : '') + '" data-plap="' + k + '" title="' + esc(T(te)) + '">' + esc(T(en)) + '</button>').join('') + '</div>'
    + '<small class=hidnote>' + esc(T('Applies to sessions started after the change')) + '</small></div>';
}
// Pipelines are per project, so «Apply» always writes this project's mode (the server keeps its global default untouched).
async function plApplySet(mode){
  const d = PLS.data[PLS.proj], a = d && d.ok && d.apply;
  if(!a) return;
  const lab = m => { const r = PL_APPLY.find(x => x[0] === m); return r ? T(r[1]) : String(m || ''); };
  if(!confirm(T('Change how sessions apply pipelines? Applies to sessions started after the change.')
    + '\n\n' + PLS.proj + '\n' + lab(a.mode) + ' → ' + lab(mode))) return false;
  let r;
  try{ r = await postJSON('/api/pipelines/apply', { proj: PLS.proj, mode: mode }); }
  catch(x){ r = x.body || { ok: false, err: String((x && x.message) || x) }; }
  if(!r || !r.ok){ alert(T('Could not change it') + (r && r.err ? ' — ' + r.err : '')); return false; }
  d.apply = r.apply;
  plPaint();
  return true;
}
function plPaint(fromPoll){
  if(mainView !== 'pipe') return;
  const box = document.getElementById('feed');
  if(box) paintPipe(box, fromPoll === true);
}
// «Running N» overview sits under the canvas, above the run table: at the top its come-and-go moved the chips and canvas on every run start/end.
// Bodies with no canvas (loading, empty, Workflow/arch panels) get it at their end instead.
function plMainBody(){
  const ov = plOverview(), hd = { row: '' }, pb = plBody(ov, hd);   // one head row: project · pipeline · «+ New ▾» (· Workflow chips)
  return '<div class=pltop>' + plChips() + hd.row + '</div>' + plApplySeg(PLS.data[PLS.proj]) + pb + (ov && pb.indexOf(ov) < 0 ? ov : '');
}
function paintPipe(box, fromPoll){
  if(PLDRAG) return;                   // ⚠a repaint mid-drag would drop the dragged node
  plLoadProjs();
  if(PLS.projs && !PLS.proj && typeof strDefProj === 'function') PLS.proj = strDefProj() || '';   // same default as «Structure»; not remembered until clicked
  if(PLS.projs) plLoad(PLS.proj, false);
  const hv = !PLS.off && plHnOn();
  tbSlot('pipe', PLS.off ? '' : plViewSeg());   // sub-view switch lives in the header toolbar slot, like Branches/Insights
  // Pipelines view: no <b>, the header title (#vtitle) already says «Pipelines».
  const head = '<div class="wvh wvht">' + (hv ? '<b>' + esc(T('Harness')) + '</b>' : '') + '<span class=plcap>'
    + esc(hv ? T('Hooks · rules · agents · MCP · skills') : T('Agent and model per stage')) + '</span></div>';
  const body = PLS.off ? '<div class=hidnote>' + esc(T('The pipeline feature is off')) + '</div>'
    : (hv ? plChips() + hnHtml() : plMainBody());
  const h = '<div class="brep plw">' + head + body + '</div>';
  if(box._plw === h && box.querySelector('.plw')) return;   // ⚠poll repaints would close an open <select>
  const fe = document.activeElement;   // ⚠a live run changes h every poll: never rebuild under an open select / the caret
  if(fromPoll && fe && fe.closest && fe.closest('.plw') && /^(SELECT|INPUT|TEXTAREA)$/.test(fe.tagName)) return;
  if(fromPoll && fe && fe.closest && fe.closest('.hnw')) return;   // harness chips/rows are focusable: a rebuild drops keyboard focus
  if(fromPoll && fe && fe.closest && fe.closest('.plnewm')) return;   // ⚠open «+ New ▾» menu: a rebuild drops the focused item (48e)
  // ⚠Harness HTML changes every poll (relative times), and a rebuilt node drops its native title tooltip before the ~1s delay ends: hold while hovering one.
  if(fromPoll && box.querySelector('.hnw [title]:hover')) return;
  box._plw = h;
  box.innerHTML = h;
  const pw = box.querySelector('.plw'); if(pw) pw.style.setProperty('--plt', (-performance.now()) + 'ms');   // ⚠rebuild restarts animations: negative delay = document time keeps the phase
  if(!hv) plAfterPaint(box);
}
// A stage title the file has but the editor lost (renamed or removed) while a run is open: its [pl:] tags still carry the old name.
function plRenameWarn(p, lv){
  const open = lv && (lv.pr ? !lv.pr.end : !!(lv.run && lv.run.run)), G = plEnt(p).G;
  const gone = (p.stages || []).some(s => !G.nodes.some(n => n.title === s.title));
  return open && gone ? '<div class="hidnote plwarnrun">⚠ ' + esc(T('A run of this pipeline is open — its running tags use the old stage name')) + '</div>' : '';
}
async function plSave(write){
  const p = plCur();
  if(!p || !plDirty(p.name) || PLS.saving || p.from) return;   // borrowed: saved only in its own project
  const E = plEnt(p), chk = plgCheck(E.G);
  if(chk.errs.length) return;
  PLS.saving = true; PLS.msg = ''; plPaint();
  let r;
  try{ r = await postJSON('/api/pipelines/save', { proj: PLS.proj, name: p.name, base: p.sha, dry: !write, defaults: E.G.defaults, use: E.G.use || '', rules: E.G.rules, guards: plgGuards(E.G, (PLS.data[PLS.proj]||{}).gate_modes), stages: plgStages(E.G, chk.order) }); }
  catch(x){ r = x.body || { ok: false, err: String((x && x.message) || x) }; }
  PLS.saving = false;
  if(!r || !r.ok){ PLS.msg = T('Could not save') + ' — ' + ((r && r.err) || '') + (r && r.errs ? ' (' + r.errs.join(' · ') + ')' : ''); PLS.diff = null; }
  else if(!write) PLS.diff = { name: p.name, text: r.diff || '' };
  else { PLS.diff = null; PLS.msg = T('Saved · backup') + ' ' + (r.backup || ''); await plLoad(PLS.proj, true); }
  plPaint(); plRefocus('[data-plok]:not([disabled])', '[data-plsave]:not([disabled])', '[data-ppk="plsel"]');   // awaited load: a later repaint would drop focus again
}
async function plDelete(write){
  const p = plCur();
  if(!p || PLS.saving || p.std || (!p.sha && p.ok) || p.from) return;   // ⚠unsaved drafts (std/suggest) have no file (no sha); borrowed rows are deleted only in their own project; an unreadable file (!ok, no sha) is still force-deletable
  PLS.saving = true; PLS.msg = ''; PLS.diff = null; plPaint();
  let r;
  try{ r = await postJSON('/api/pipelines/delete', { proj: PLS.proj, name: p.name, dry: !write }); }
  catch(x){ r = x.body || { ok: false, err: String((x && x.message) || x) }; }
  PLS.saving = false;
  if(!r || !r.ok){ PLS.del = null; PLS.msg = T('Could not delete') + ' — ' + ((r && r.err) || ''); }
  else if(!write) PLS.del = { name: p.name, path: r.path || '', to: r.to || '' };
  else {
    PLS.del = null; delete PLS.g[plEntKey(p.name)];
    PLS.msg = T('Deleted · backup') + ' ' + (r.backup || '');
    PLS.sel = '';   // plCur falls back to the first remaining pipeline
    PLS.projs = null; await Promise.all([plLoadProjs(), plLoad(PLS.proj, true)]);
  }
  plPaint(); plRefocus('[data-pldelok]:not([disabled])', '[data-pldel]:not([disabled])', '[data-ppk="plsel"]', '[data-plnewm]');
}
document.addEventListener('click', e => {
  if(!e.target.closest || !e.target.closest('.plw')) return;
  const rm = e.target.closest('[data-plprojrm]');
  if(rm){ e.preventDefault(); return plRemove(rm.dataset.plprojrm); }
  if(e.target.closest('[data-plprojadd]')) return plBrOpen();
  const ap = e.target.closest('[data-plap]');
  if(ap){ const a = (PLS.data[PLS.proj] || {}).apply; if(a && ap.dataset.plap !== a.mode) plApplySet(ap.dataset.plap); return; }
  if(e.target.closest('[data-plsave]')) return plSave(false);
  if(e.target.closest('[data-plok]')) return plSave(true);
  if(e.target.closest('[data-plno]')){ PLS.diff = null; plPaint(); return; }
  if(e.target.closest('[data-pldel]')) return plDelete(false);
  if(e.target.closest('[data-pldelok]')) return plDelete(true);
  if(e.target.closest('[data-pldelno]')){ PLS.del = null; plPaint(); return; }
  if(e.target.closest('[data-plreset]')){ plResetEnt(plCur()); PLS.diff = null; PLS.msg = ''; plPaint(); }
});
// «Undo»: graph back to the file, view kept (a click never re-centres, 48d).
function plResetEnt(p){
  if(!p) return;
  const k = plEntKey(p.name), O = PLS.g[k];
  delete PLS.g[k];
  plViewCarry(plEnt(p), O);
}
// Pipeline combobox pick / borrowed run chip (48h): opens that pipeline; «sug:k» = an unsaved suggestion (48e plSugBody).
function plSelPick(v){
  if(!v) return;
  if(v.indexOf('sug:') === 0){ PLS.sugI = +v.slice(4) || 0; PLS.std = ''; plPaint(); return; }
  PLS.sel = v; PLS.std = ''; PLS.wf = null; PLS.diff = null; PLS.del = null; PLS.msg = ''; plAgSet(false); plPaint();
}
