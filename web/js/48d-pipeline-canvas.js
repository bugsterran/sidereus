// «Pipelines» canvas editor (step 4): canvas on top, node panel | palette below (43-pipeline.css grid).
// Nodes drag, background drag pans, Ctrl+wheel zooms; right port -> next stage (flow), bottom port -> earlier stage (loop-back = onFail).
// ⚠Never auto-centre on a click — the view moves only on a drag, zoom, «Arrange» or the first open.
const PL_SPLIT = { v: '--plpanh', key: 'sidereus.plpanh', min: 200, cv: 200 };   // pane row height under the canvas; cv = canvas row floor while dragged
let PLDRAG = null;          // active pointer gesture {k: node|pan|edge|split, ...}; poll repaints wait while set
function plEntKey(name){ return PLS.proj + '\n' + name; }
// Editor entry per pipeline: graph copy, its saved key (dirty check), selection and view. Rebuilt when the file sha changes.
function plEnt(p){
  if(!p || !p.ok) return null;
  const k = plEntKey(p.name);
  let E = PLS.g[k];
  if(!E || E.sha !== p.sha){
    const G = plgFrom(p);
    // auto = the file has no node positions: the first paint lays the chain out to the canvas width (base re-keyed then, not dirty)
    const O = E;
    E = PLS.g[k] = { G, sha: p.sha, base: plgKey(G), sel: null, view: null, auto: !p.stages.every(s => s.ui) };
    plViewCarry(E, O);
  }
  return E;
}
// ⚠A rebuilt entry (save = new sha, «Undo») must keep the view and its fit flags: without touched/fitK plGwFit re-fitted (x snapped to 0)
// and a null view ran the first-open fit + centre after a click. An unplaced file (auto) still gets the first-open layout.
function plViewCarry(E, O){
  if(!E || !O || !O.view || E.auto) return E;
  E.view = Object.assign({}, O.view);
  ['touched', 'first', 'ctrd', 'laid', 'fitK', 'visY'].forEach(f => { if(O[f] !== undefined) E[f] = O[f]; });
  return E;
}
function plCurEnt(){ return plEnt(plCur()); }
// ⚠plPaint rebuilds .plw with innerHTML, so the pressed control is detached and focus falls to BODY.
// ⇒ after the repaint, focus the first match of the given selectors (stable data- attributes), in order.
function plRefocus(...sels){
  const w = document.querySelector('.plw');
  for(const s of sels){ const el = s && w && w.querySelector(s); if(el){ el.focus({ preventScroll: true }); return el; } }
  return null;
}
function plDirty(name){ const E = PLS.g[plEntKey(name)]; return !!E && plgKey(E.G) !== E.base; }
// Context for plgAddTpl: role -> agent map (GET /api/pipelines); plCat() = the catalog of the open project.
function plAddCtx(){ const d = PLS.data[PLS.proj] || {}; return { roles: d.roles || {}, dt: d.default_tasks || {} }; }
function plCat(){ return (PLS.data[PLS.proj] || {}).catalog || {}; }
// ⚠Chevrons sat under the selected node's outline/shadow (nodes are HTML above the edge SVG).
// ⇒ heads live in their own SVG layer above the nodes (pointer-events none); the lines below carry no marker.
function plMarkers(G){
  // Open chevron in user units (size independent of line width)
  // ⚠ custom-colour ids are 'c-<hex>': a bare 'c' prefix also matched the family 'check' and gave it --pfc:#heck (invisible chevron)
  return PLG_FAMS.concat([...new Set(G.nodes.map(plgHue).filter(Boolean))].map(c => 'c-' + c.slice(1))).map(f => '<marker id=plaf-' + f
      + (f.startsWith('c-') ? ' class=pf-cust style="--pfc:#' + f.slice(2) + '"' : ' class=pf-' + f) + ' viewBox="0 0 10 10" refX=8.9 refY=5 markerWidth=9 markerHeight=9 markerUnits=userSpaceOnUse orient=auto><path d="M2 1.5L8 5L2 8.5" class=plmf /></marker>').join('')
    + '<marker id=plal viewBox="0 0 10 10" refX=8.9 refY=5 markerWidth=9 markerHeight=9 markerUnits=userSpaceOnUse orient=auto><path d="M2 1.5L8 5L2 8.5" class=plml /></marker>';
}
// One 10px marker-only stub per edge end (flow: horizontal into the left side; loop: up into the bottom). Running edge: no chevron, a tail stub.
function plHeadsSvg(E){
  const G = plVG(E), lt = E.lt || {}, pt = id => (plgNode(G, id) || {}).ui, lanes = plgLoopLanes(G);
  let h = '';
  G.flow.forEach((e, i) => {
    const a = pt(e[0]), nb = plgNode(G, e[1]);
    if(!a || !nb) return;
    const c = plgHue(nb), x = nb.ui.x, y = nb.ui.y + plgH(G, e[1]) / 2;
    // ⚠The running node's glow (box-shadow up to 31px, HTML above the edge SVG) washed out the line's last px and read as a gap.
    // ⇒ redraw that tail above the nodes, clipped to end exactly at the border (x).
    // ⚠A lit SOURCE node (done/fail/run) glows over the line's first px the same way, so the start read darker than the end.
    // ⇒ redraw both ends above the nodes with the edge's own gradient (userSpaceOnUse: identical colour at every x).
    const lit = st => st === 'done' || st === 'fail' || st === 'run', fd = plgFlowPath(a, nb.ui, plgW(G, e[0]), plgH(G, e[0]), plgH(G, e[1]));
    const sx = a.x + plgW(G, e[0]), na = plgNode(G, e[0]) || {};
    if(lit((lt[nb.title] || {}).st)){
      h += '<clipPath id=plrc' + i + '><rect x="' + (x - 32) + '" y="' + (y - 40) + '" width=32 height=80 /></clipPath><path class=plrin'
        + ' style="stroke:url(#plgr' + i + ')" clip-path="url(#plrc' + i + ')" d="' + fd + '"/>';
    }
    if(lit((lt[na.title] || {}).st)){
      h += '<clipPath id=plrs' + i + '><rect x="' + sx + '" y="' + (a.y + plgH(G, e[0]) / 2 - 40) + '" width=32 height=80 /></clipPath><path class=plrin'
        + ' style="stroke:url(#plgr' + i + ')" clip-path="url(#plrs' + i + ')" d="' + fd + '"/>';
    }   // every edge keeps its chevron
    h += '<path class=plhead d="M' + (x - 10) + ' ' + y + ' L' + x + ' ' + y + '" marker-end="url(#plaf-' + (c ? 'c-' + c.slice(1) : plgFam(nb.title)) + ')"/>';
  });
  G.loops.forEach((l, i) => {
    const a = pt(l.from), b = pt(l.to);
    if(!a || !b || !lanes[i]) return;
    const q = plgPathPts(plgLoopPath(a, b, lanes[i], plgW(G, l.from), plgW(G, l.to), plgH(G, l.from), plgH(G, l.to)).d), [x, y] = q[q.length - 1];
    h += '<path class=plhead d="M' + x + ' ' + (y + 10) + ' L' + x + ' ' + y + '" marker-end="url(#plal)"/>';
  });
  return h;
}
function plRedrawEdges(E, cv){
  const g = cv.querySelector('.pledges'), hd = cv.querySelector('.plhd');
  if(g){ g.innerHTML = plEdgesSvg(E); plFitPills(g); }
  if(hd) hd.innerHTML = plHeadsSvg(E);
  return g;
}
// Loop-back edge from -> to pulses while `to` runs a pass opened by that edge (tests/test_plreplay.py).
// ⚠keyed on `via` (the edge that opened the target's current pass, pl_runs), not the cumulative `from` count:
//   an earlier loop-back kept pulsing on every later pass of the target, even a forward one
function plPulseOn(lt, from, to){ const L = (lt || {})[to] || {}; return (+((L.from || {})[from]) || 0) > 0 && L.st === 'run' && L.via === from; }
function plEdgesSvg(E){
  const G = plVG(E), sel = E.sel || {}, pt = id => (plgNode(G, id) || {}).ui, lt = E.lt || {}, st = id => (lt[(plgNode(G, id) || {}).title] || {});
  let h = '';
  G.flow.forEach((e, i) => {
    const a = pt(e[0]), b = pt(e[1]);
    if(!a || !b) return;
    const d = plgFlowPath(a, b, plgW(G, e[0]), plgH(G, e[0]), plgH(G, e[1])), on = sel.k === 'f' && sel.i === i ? ' on' : '', run = st(e[1]).st === 'run' ? ' run' : '';
    // Source -> target family gradient (userSpaceOnUse: a straight edge has a zero-height bbox)
    const na = plgNode(G, e[0]) || {}, nb = plgNode(G, e[1]) || {}, fa = plgFam(na.title), fb = plgFam(nb.title);
    // ⚠Running edges draw exactly like idle ones — moving dashes on short edges read as a blob; the running node's own border animation marks the state.
    const gr = '<linearGradient id=plgr' + i + ' gradientUnits=userSpaceOnUse x1=' + (a.x + plgW(G, e[0])) + ' y1=' + (a.y + plgH(G, e[0]) / 2) + ' x2=' + b.x + ' y2=' + (b.y + plgH(G, e[1]) / 2) + '>'
      + '<stop offset=0 class="plgs pf-' + fa + '"' + plgPfc(na) + '/><stop offset=1 class="plgs pf-' + fb + '"' + plgPfc(nb) + '/></linearGradient>';
    h += gr + '<path class=plhit data-pledge="f:' + i + '" d="' + d + '"/><path class="plef' + on + run + '" d="' + d + '"'
      + ' style="stroke:url(#plgr' + i + ')"/>';
  });
  const lanes = plgLoopLanes(G);
  let labs = '';   // labels last, as pills on their own lane's horizontal segment (drawn over every line)
  G.loops.forEach((l, i) => {
    const a = pt(l.from), b = pt(l.to);
    if(!a || !b || !lanes[i]) return;
    const g = plgLoopPath(a, b, lanes[i], plgW(G, l.from), plgW(G, l.to), plgH(G, l.from), plgH(G, l.to)), on = sel.k === 'l' && sel.i === i ? ' on' : '';
    const fn = +((st(l.to).from || {})[(plgNode(G, l.from) || {}).title]) || 0;   // times this edge fired (plrun `from`, 48b)
    const txt = '↩ ' + T('fails') + ' ' + T('max ') + l.max + (l.then ? ' → ' + l.then : '') + (fn ? ' · ↺ ' + fn : ''), w = Math.round(txt.length * 7.2 + 16);
    const pulse = plPulseOn(lt, (plgNode(G, l.from) || {}).title, (plgNode(G, l.to) || {}).title) ? ' pulse' : '';   // 43 .plel.pulse
    h += '<path class=plhit data-pledge="l:' + i + '" d="' + g.d + '"/><path class="plel' + on + pulse + '" d="' + g.d + '"/>';
    const lx = Math.max(g.lx, w / 2 + 4);   // ⚠gutter lanes centre near x≈80: a wide pill ran past x=0 and the canvas clipped it
    labs += '<g class="pllt' + on + '" data-pledge="l:' + i + '"><rect x="' + (lx - w / 2) + '" y="' + (g.ly - 10) + '" width="' + w + '" height=20 rx=10 />'
      + '<text x="' + lx + '" y="' + (g.ly + 4) + '" text-anchor=middle>' + esc(txt) + '</text></g>';
  });
  return h + labs;
}
// Stage outcome word on the node pill (plrun `o`, 48b plPrLt).
// ⚠back = an onFail loop-back sent work back (e.g. non-blocking review fixes); only a shell [pl-end:…|fail] is a failure.
// ⚠Show through plOc(): 'run' is 'Running|stage' in Korean (plain 'Running' is another word).
const PL_OUTCOME = { run: 'Running', done: 'Done', skip: 'Skipped', back: 'Sent back', fail: 'Failed', hold: 'Paused' };
function plOc(st){ return T(PL_OUTCOME[st], 'stage'); }
// Stage flags under the card as readable [label, tooltip] pairs (was raw config keys like «onError continue»).
function plFlagChips(n){
  return [n.skill ? [TV({msg: 'Skill {n}', vars: {n: n.skill}}), T('Loads this skill for the stage')] : null,
    n.retry != null ? [TV({msg: 'Retry up to {n}', vars: {n: n.retry}}), T('Retries the same agent up to this many times')] : null,
    n.gate ? [T('Gate'), T('Runs a check command; the stage passes only when it succeeds') + ' (' + n.gate + ')'] : null,
    n.parallel ? [TV({msg: 'Parallel {n}', vars: {n: n.parallel}}), T('Runs this many agents at once')] : null,
    n.produces ? [T('Produces slices'), T('This stage (usually design) splits the work into slices; a later stage takes them one by one')] : null,
    n.fanout ? [T('Parallel slices'), T('Runs one agent per slice from an earlier stage, in parallel (needs an earlier produces stage)')] : null,
    n.onlyOnJump ? [T('Only on jump'), T('Skipped in the normal order; runs only when another stage jumps here via onFail (e.g. re-verify after a review fix)')] : null,
    n.onError === 'continue' ? [T('Continue on error'), T('A failed slice does not stop the run; the next stage still starts')] : null].filter(Boolean);
}
// Gate coverage: n = stages with a check command, m = all stages (unsaved edits count).
function plGateCov(G){ const ns = (G && G.nodes) || []; return { n: ns.filter(x => String(x.gate || '').trim()).length, m: ns.length }; }
function plNodeHtml(E, n, bad, lt){
  const G = E.G, L0 = lt && lt[n.title], pi = L0 ? plPassSel(E, n.id, L0) : -1, L = pi >= 0 ? Object.assign({}, L0, plPass(L0, pi)) : L0, eff = n.model || G.defaults.model;
  const warn = PL_JUDGED.includes(n.title) && PL_LOW.includes(eff) ? ' <span class=plwarn title="' + esc(T('Judgment stages should keep a strong model')) + '">⚠</span>' : '';
  const chips = plFlagChips(n);
  const unv = String(n.gate || '').trim() ? '' : '<span class=plunv title="' + esc(T('No gate command — nothing machine-checks this stage')) + '">' + esc(T('Unverified')) + '</span>';   // judgment stages are expected here
  const oc = L && PL_OUTCOME[L.st] ? plOc(L.st) + (L.why ? ' (' + L.why + ')' : '') : '', lsTxt = L ? [oc, L.n ? T('Agent') + ' ' + L.n + ' · ' + ago(L.sec) : oc ? '' : T('Waiting')].filter(Boolean).join(' · ') : '';
  const live = L ? '<div class=plls title="' + esc(lsTxt) + '">' + esc(lsTxt) + '</div>' : '';   // title: the pill ellipsizes at 150px
  const sel = E.sel && E.sel.k === 'n' && E.sel.id === n.id ? ' on' : '';
  const seen = E.seenSt || (E.seenSt = {}), fresh = L0 && seen[n.id] !== undefined && seen[n.id] !== L0.st ? ' pl-new' : '';   // pop/shake once; ⚠real state, not the picked pass
  if(L0) seen[n.id] = L0.st;
  const icon = !L ? '' : L.st === 'run' ? '<i class=plspin></i>' : L.st === 'done' ? '<b class=plok>✓</b>' : L.st === 'fail' ? '<b class=plx>✕</b>' : L.st === 'skip' ? '<b class=plsk>↷</b>' : L.st === 'back' ? '<b class="plsk plbk">↺</b>' : L.st === 'hold' ? '<b class=plsk>⏸</b>' : '';
  const fr = L && L.from ? Object.keys(L.from).filter(f => L.from[f] > 0) : [];   // loop-backs into this stage, per source
  const rbt = fr.length ? '↺ ' + fr.map(f => TV({msg: '{m} from {n}', vars: {n: plgShow(f), m: L.from[f]}})).join(' · ') : L && L.retry ? T('Retry', 'stage') + ' ' + L.retry : '';
  const rb = rbt ? '<span class=plrb title="' + esc(rbt) + '">' + esc(rbt) + '</span>' : '';
  // Pass picker: only with recorded earlier passes (older plrun rows carry no ps). Sits on the bottom edge so the title keeps its width.
  const pb = L0 && L0.k >= 2 && L0.ps && L0.ps.length ? '<button type=button class="plpass' + (pi >= 0 ? ' on' : '') + '" data-plpass="' + esc(n.id) + '" aria-haspopup=menu title="'
    + esc(T('Show an earlier pass')) + '">' + esc('↺' + L.k + ' ▾') + '</button>' : '';
  const hl = G.loops.some(l => l.from === n.id) ? ' hasloop' : '';   // its lane leaves 14px*k off-centre: no mark at the centre port
  // Direct-mode subagents behind a lit stage (workflow runs carry no labs: no hover)
  const tip = L && L.nn ? ' title="' + esc(T('Not needed on this run — runs only on a loop-back')) + '"' : L && L.labs && L.labs.length ? ' title="' + esc(L.labs.map(a => plLabTip(a.lab) + ' (' + (a.run ? T('Running') : T('Done')) + ')').join('\n')) + '"' : '';
  return '<div class="plnd pf-' + plgFam(n.title) + hl + sel + (bad ? ' bad' : '') + (L ? ' pl-' + L.st + fresh : '') + '" data-plnode="' + esc(n.id) + '"' + tip + ' style="left:' + (+n.ui.x) + 'px;top:' + (+n.ui.y) + 'px' + (plgHue(n) ? ';--pfc:' + plgHue(n) : '') + '">'
    + '<i class="plport plpin" title="' + esc(T('Incoming flow')) + '"></i>'
    + '<i class="plport plpout" data-plport=flow title="' + esc(T('Drag to connect the next stage')) + '"></i>'
    + '<i class="plport plpbk" data-plport=loop title="' + esc(T('Drag to an earlier stage to loop back on failure')) + '"></i>'
    + '<div class=plt>' + icon + esc(plgShow(n.title)) + rb + '</div><div class=plna>' + esc(n.agent || '') + '</div>'
    + '<div class=plnm>' + esc(n.model || T('default', 'short') + ' (' + G.defaults.model + ')') + warn + '</div>' + (chips.length || unv ? '<div class=plnc title="' + esc(chips.map(c => c[0] + ' — ' + c[1]).join('\n')) + '">' + unv + esc(chips.map(c => c[0]).join(' · ')) + '</div>' : '')
    + (L && typeof PLS === 'object' ? plEvLine(plEvRows(PLS.proj), L, plEvCommits(PLS.proj)) : '') + live + pb + '</div>';
}
function plCanvas(p, d, lt){
  const E = plEnt(p), G = E.G, chk = plgCheck(G), bad = {};
  E.lt = lt || null;
  chk.errs.forEach(x => { if(x.id) bad[x.id] = 1; });
  const v = E.view || { x: 0, y: 0, z: 1 }, VG = plVG(E);
  const mx = Math.max(1200, ...VG.nodes.map(n => n.ui.x + plgW(G, n.id) + 240)), my = Math.max(600, ...VG.nodes.map(n => n.ui.y + plgH(G, n.id) + 240 + PLG_LANE * G.loops.length));
  // Toolbar is its own strip above the canvas (★2026-10-01 live check: overlaid, it hid the first nodes' titles).
  const sugg = ((d.catalog || {}).items || []).map(t => t.title.ko).filter(t => !G.nodes.some(n => n.title === t));   // catalog order
  const tb = '<div class=plcvt><span class=plnt><input data-plnt maxlength=24 list=plsug placeholder="' + esc(T('Stage name')) + '" title="' + esc(T('Stage name (empty = recommended)')) + '">'   // ⚠the long hint clipped as a placeholder
    + '<datalist id=plsug>' + sugg.map(t => '<option value="' + esc(t) + '">').join('') + '</datalist>'
    + '<button class=wkrgb data-pladd title="' + esc(T('Adds a stage after the selected one (else at the end)')) + '">' + esc(T('+ Stage')) + '</button></span>'
    + '<button class=wkrgb data-plfit title="' + esc(T('Re-flow so every stage shows · zoom stays if it fits')) + '">' + esc(T('Arrange')) + '</button>'
    + '<button class=wkrgb data-plfitv title="' + esc(T('Zoom so every stage is visible')) + '">' + esc(T('Fit to view')) + '</button><button class=wkrgb data-plz="-1" title="' + esc(T('Zoom out')) + '" aria-label="' + esc(T('Zoom out')) + '">−</button>'
    + '<span class=plzv>' + Math.round(v.z * 100) + '%</span><button class=wkrgb data-plz="1" title="' + esc(T('Zoom in')) + '" aria-label="' + esc(T('Zoom in')) + '">+</button>'
    + '<span class=plhint>' + esc(T('Drag background = pan · Ctrl+wheel = zoom')) + '</span></div>';
  const cv = '<div class=plcvw>' + tb + '<div class=plcv data-plcv><div class=plcvi style="transform:translate(' + v.x + 'px,' + v.y + 'px) scale(' + v.z + ')">'
    + '<svg class=plsvg width="' + mx + '" height="' + my + '"><g class=pledges>' + plEdgesSvg(E) + '</g><path class=pltmp d=""/></svg>'
    + VG.nodes.map(n => plNodeHtml(E, n, bad[n.id], lt)).join('')
    + '<svg class="plsvg plheads" width="' + mx + '" height="' + my + '"><defs>' + plMarkers(G) + '</defs><g class=plhd>' + plHeadsSvg(E) + '</g></svg></div></div>';
  const errs = chk.errs.length ? '<ul class=plerrs>' + chk.errs.map(x => '<li' + (x.id ? ' data-plpick="' + esc(x.id) + '"' : '') + '>' + esc(x.msg) + '</li>').join('') + '</ul>' : '';
  const gh = '<div class=plgh data-plgh title="' + esc(T('Drag to resize · double-click to reset', 'height')) + '"></div>';
  // 48k Watch: no palette, no editor; the selected stage's result sits in the panel slot. ⚠Edit output must stay byte-identical.
  if(typeof plWatchFor === 'function' && plWatchFor(p)) return { html: '<div class="plgw plwt">' + cv + errs + '</div>' + gh + plWatchPane(E, d, plViewRun(PLS.proj, p.name), lt) + '</div>', ok: !chk.errs.length };
  return { html: '<div class=plgw>' + plPalette(E, d.catalog)
    + cv + errs + '</div>' + gh + plPanel(E, d) + '</div>', ok: !chk.errs.length };
}
const PL_SWATCH = ['#c297ff', '#5899f3', '#71c269', '#fad83e', '#2ec4b6', '#f472b6', '#fb923c', '#94a3b8'];   // 5 families + pink, orange, slate
function plSetColor(E, c){
  const n = E.sel && E.sel.k === 'n' && plgNode(E.G, E.sel.id);
  if(!n) return;
  c = String(c || '').toLowerCase();
  if(/^#[0-9a-f]{6}$/.test(c)) n.ui.color = c; else delete n.ui.color;
  plTouch(); plPaint();
}
function plOpt(v, lab, cur){ return '<option value="' + esc(v) + '"' + (String(v) === String(cur) ? ' selected' : '') + '>' + esc(lab) + '</option>'; }
function plRow(lab, ctl){ return '<label class=plfr><span>' + esc(lab) + '</span>' + ctl + '</label>'; }
// Picker options: the outside/not-installed current entry on top (outLab), then «This project» and «Built-in» optgroups (empty group omitted).
function plGrpOpts(L, cur, outLab, biLab){
  const opt = a => plOpt(a.name, !a.out ? a.name : a.name + ' (' + T(outLab(a.name)) + ')', cur);
  const grp = (g, lab) => { const G = L.filter(a => a.grp === g); return G.length ? '<optgroup label="' + esc(T(lab)) + '">' + G.map(opt).join('') + '</optgroup>' : ''; };
  return L.filter(a => a.grp === 'out').map(opt).join('') + grp('own', 'This project') + grp('bi', biLab || 'Built-in');
}
function plAgOpts(ags, agents, cur){ return plGrpOpts(ags, cur, n => plAgMissing(n, agents) ? 'not installed → general-purpose' : 'outside this project'); }
function plSkOpts(sks, skills, cur){ return plGrpOpts(sks, cur, n => (skills || []).some(k => k && k.name === n) ? 'outside this project' : 'not installed', 'General'); }
function plPanel(E, d){
  const G = E.G, s = E.sel, models = d.models || PLG_MODELS;
  let h = '';
  if(s && s.k === 'n' && plgNode(G, s.id)){
    const n = plgNode(G, s.id), ags = plPickAgents(d.agents, n.agent, PLS.proj);   // d = PLS.data[PLS.proj]: follows the project picker
    const sks = plPickSkills(d.skills, n.skill, PLS.proj, ((PLS.projs && PLS.projs.projects) || []).map(x => x.path).concat(Object.keys(PLS.data)));   // same scoping as agents: another project's skill is not offered
    const tp = plgTpl(d.catalog, n.title) || {}, pt = !PLG_TITLES.includes(plTk(n.title)) && tp.instr;   // catalog stage with its own instruction: instr was prefilled
    h = '<div class=plph><input class=plti data-plti maxlength=24 value="' + esc(n.title) + '" aria-label="' + esc(T('Stage name')) + '" title="' + esc(T('Rename the stage — loop-backs follow; saved with «Save»')) + '"><button class=wkrgb data-pldel>' + esc(T('Delete')) + '</button></div>'
      + plRow('Agent', '<select data-plf=agent>' + plAgOpts(ags, d.agents, n.agent) + '</select>')
      + plRow('Model', '<select data-plf=model>' + plOpt('', T('default', 'short') + ' (' + G.defaults.model + ')', n.model || '') + models.map(m => plOpt(m, m, n.model || '')).join('') + '</select>')
      + plRow('Skill', '<select data-plf=skill>' + plOpt('', T('none'), n.skill || '') + plSkOpts(sks, d.skills, n.skill || '') + '</select>')
      + plRow('Retry', '<select data-plf=retry>' + plOpt('', T('default', 'short') + ' (' + G.defaults.retry + ')', n.retry == null ? '' : n.retry) + [0, 1, 2, 3].map(k => plOpt(k, k, n.retry == null ? '' : n.retry)).join('') + '</select>')
      + plRow(T('Order'), (o => '<span class=plcol><button class=wkrgb data-plmv=-1' + (!o || o[0] === n.id ? ' disabled' : '') + '>◀</button><button class=wkrgb data-plmv=1'
        + (!o || o[o.length - 1] === n.id ? ' disabled' : '') + '>▶</button></span>')(plgLine(G)))
      + plRow(T('Color'), '<span class=plcol>' + PL_SWATCH.map(c => '<button class="plsw' + (plgColor(n) === c ? ' on' : '') + '" data-plcol="' + c + '" style="background:' + c + '" title="' + c + '"></button>').join('')
        + '<input type=color data-plcolc value="' + (plgColor(n) || '#2ec4b6') + '" title="' + esc(T('Pick a colour')) + '"><button class=wkrgb data-plcol="">' + esc(T('default', 'short')) + '</button></span>')
      + plRow('Gate', '<input data-plf=gate maxlength=200 value="' + esc(n.gate || '') + '" placeholder="' + esc(tp.gateHint || 'scripts/check.sh --fast') + '"' + (tp.asserts ? ' title="' + esc(T('Checks') + ': ' + tp.asserts) + '"' : '') + '>')
      + plRow('Parallel', '<input data-plf=parallel type=number min=1 max=16 value="' + esc(n.parallel == null ? '' : n.parallel) + '">')
      + plRow('onError', '<select data-plf=onError>' + plOpt('', 'stop', n.onError || '') + plOpt('continue', 'continue', n.onError || '') + '</select>')
      + '<div class=plfc>' + [['produces', 'produces slices', 'This stage (usually design) splits the work into slices; a later stage takes them one by one'],
        ['fanout', 'fanout slices', 'Runs one agent per slice from an earlier stage, in parallel (needs an earlier produces stage)'],
        ['onlyOnJump', 'onlyOnJump', 'Skipped in the normal order; runs only when another stage jumps here via onFail (e.g. re-verify after a review fix)']].map(([k, lab, tip]) =>
        '<label title="' + esc(T(tip)) + '"><input type=checkbox data-plf="' + k + '"' + (n[k] ? ' checked' : '') + '> ' + esc(lab) + '</label>').join('') + '</div>'
      + (d.default_tasks && d.default_tasks[n.title] ? '<details class=pldt><summary>' + esc(T('Default instruction (the runner always sends it)')) + '</summary><div>' + esc(d.default_tasks[n.title]) + '</div></details>'
        : pt ? '<div class=plfd>' + esc(T('Recommended stage — the instruction is prefilled; edit it freely')) + '</div>'
        : '<div class=plfd>' + esc(T('Custom stage — no default instruction, so an instruction is required')) + '</div>')
      + '<label class="plfr plfta"><span>' + esc(PLG_TITLES.includes(plTk(n.title)) ? T('Extra instructions (empty = default only)') : pt ? T('Instruction (prefilled)') : T('Instruction (required)')) + '</span><textarea data-plf=instr rows=5 maxlength=1000>' + esc(n.instr || '') + '</textarea></label>';
  } else if(s && s.k === 'l' && G.loops[s.i]){
    const l = G.loops[s.i], a = plgNode(G, l.from), b = plgNode(G, l.to), o = plgOrder(G).order;
    const later = o.slice(o.indexOf(l.from) + 1).map(id => plgNode(G, id).title);
    h = '<div class=plph><b>' + esc(a.title + ' ↩ ' + b.title) + '</b><button class=wkrgb data-pldel>' + esc(T('Delete')) + '</button></div>'
      + '<div class=plfd>' + esc(T('On failure it goes back to the earlier stage, fixes, and comes back')) + '</div>'
      + plRow(T('Max loops'), '<select data-plf=max>' + [1, 2, 3, 4, 5].map(k => plOpt(k, k, l.max)).join('') + '</select>')
      + plRow(T('After it passes'), '<select data-plf=then>' + plOpt('', T('next stage'), l.then || '') + later.map(t => plOpt(t, t, l.then || '')).join('') + '</select>')
      + plRow(T('If it fails for another reason'), '<select data-plf=stopOn>' + plOpt('', T('stop'), l.stopOn && !l.stopOn.length ? 'none' : '')
        + plOpt('none', T('never stop'), l.stopOn && !l.stopOn.length ? 'none' : '') + '</select>');
  } else if(s && s.k === 'f' && G.flow[s.i]){
    const e = G.flow[s.i];
    h = '<div class=plph><b>' + esc(plgNode(G, e[0]).title + ' → ' + plgNode(G, e[1]).title) + '</b><button class=wkrgb data-pldel>' + esc(T('Delete')) + '</button></div>';
  } else {
    h = '<div class=plph><b>' + esc(T('default')) + '</b></div>'
      + plRow(T('Default model'), '<select data-pld=model>' + models.map(m => plOpt(m, m, G.defaults.model)).join('') + '</select>')
      + plRow(T('Default retry'), '<select data-pld=retry>' + [0, 1, 2, 3].map(k => plOpt(k, k, G.defaults.retry)).join('') + '</select>')
      // `use` = «when to use», sent to every session of this project at start (hooks/pipelines_brief.py)
      + plRow(T('When to use'), '<input data-plu maxlength=120 value="' + esc(G.use || '') + '" placeholder="' + esc(T('e.g. viewer UI or server changes')) + '" title="' + esc(T("Told to this project's sessions when they start")) + '">')
      + '<div class=plfd>' + esc(T('Click a stage to edit it here · Delete removes it')) + '</div>' + plRulesPane(G) + plGuardsPane(G, d.gate_modes);
  }
  return '<div class=plpan>' + h + '</div>';
}
// «Rules» (no selection): common checkable rules + free text, stored as `rules` lines (English, sent to every stage).
// «Follow the project rule file»: one line per repo-root rule file found (name only, nothing copied).
function plRuleList(){
  return PLG_RULES.concat(((PLS.data[PLS.proj] || {}).rule_files || []).map(f => ['Follow the project rule file', 'Follow ' + f + ' in the repo.', f]));
}
function plRulesPane(G){
  const L = plRuleList(), r = plgRulesSplit(G.rules, L);
  return '<div class=plph><b>' + esc(T('Rules')) + '</b></div><div class=plfd>' + esc(T('Sent to every stage')) + '</div><div class=plfc>'
    + L.map(([ko, en, f], i) => '<label title="' + esc(en) + '"><input type=checkbox data-plr="' + i + '"' + (r.on.includes(i) ? ' checked' : '') + '> ' + esc(T(ko) + (f ? ' · ' + f : '')) + '</label>').join('')
    + '</div><label class="plfr plfta"><span>' + esc(T('Other rules')) + '</span><textarea data-plrf rows=5 maxlength=2000>' + esc(r.free) + '</textarea></label>'
    // Any language works; English costs fewer tokens per stage prompt and matches the checkbox lines and agent files.
    + '<div class=plfd>' + esc(T('English recommended — added to every stage prompt, so it costs fewer tokens and matches the lines above and the agent files. Other languages work too.')) + '</div>';
}
// «Guards» (no selection): graded stages whose gate must pass, and the loop-back limit for a run; saved as `guards` with «Save».
function plGuardsPane(G, modes){
  const g = plgGuards(G, modes), gr = plgGraded(G, modes);
  return '<div class=plph><b>' + esc(T('Guards')) + '</b></div><div class=plfd>' + esc(T('The run stops when a required gate fails or loop-backs exceed the limit')) + '</div>'
    + (gr.length ? '<div class=plfc>' + gr.map(n => '<label title="' + esc(n.gate) + '"><input type=checkbox data-plgq="' + esc(n.title) + '"' + ((g.requireGates || []).includes(n.title) ? ' checked' : '') + '> ' + esc(plgShow(n.title)) + '</label>').join('') + '</div>'
      : '<div class=plfd>' + esc(T('No stage has a graded gate yet (check.sh --fast|--full, arch_checks.py --verify)')) + '</div>')
    + plRow(T('Max loop-backs'), '<input type=number data-plgm min=1 max=10 value="' + esc(g.maxLoopBacks || '') + '" placeholder="' + esc(T('none')) + '">');
}
function plGuardsRead(pan){
  const m = parseInt((pan.querySelector('[data-plgm]') || {}).value, 10), g = { requireGates: [...pan.querySelectorAll('[data-plgq]')].filter(x => x.checked).map(x => x.dataset.plgq) };
  if(m >= 1) g.maxLoopBacks = Math.min(10, m);
  return g;
}
function plRulesRead(pan){
  return plgRulesJoin([...pan.querySelectorAll('[data-plr]')].filter(x => x.checked).map(x => +x.dataset.plr), (pan.querySelector('[data-plrf]') || {}).value || '', plRuleList());
}
// First open / «Arrange» / resize (until the user pans, zooms or drags): zoom ≤ 100% and never below PL_ZMIN — a chain that
// does not fit at PL_ZMIN wraps into rows instead (★2026-10-01 live check: 7 stages fitted to 54% were unreadable).
// `relayout` = positions are ours (file had none, or «Arrange»): re-flow the chain for this canvas width first.
const PL_ZMIN = 0.8, PL_ZFIT = 0.4;   // PL_ZFIT = the zoom buttons' floor
// keepZ («Arrange»): re-flow for the width visible at the current zoom and keep it — snapping to 100% pushed stages off-canvas.
// No relayout (saved positions): fit the whole graph (≥ PL_ZFIT) — at the 80% floor 6 stages showed 1 at 900px, 4 at 1440px.
// Drawn extent in graph units: nodes + the status pill above them + loop lanes (and their label pills) below / in the left gutter.
function plDrawBox(V){
  const L = plgLoopLanes(V), B = { l: Infinity, r: -Infinity, t: Infinity, b: -Infinity };
  V.nodes.forEach(n => { B.l = Math.min(B.l, n.ui.x); B.r = Math.max(B.r, n.ui.x + plgW(V, n.id)); B.t = Math.min(B.t, n.ui.y - 30); B.b = Math.max(B.b, n.ui.y + plgH(V, n.id)); });
  Object.values(L).forEach(l => { B.b = Math.max(B.b, l.y + 11, l.y2 == null ? 0 : l.y2 + 11); if(l.gx != null) B.l = Math.min(B.l, Math.max(4, l.gx)); });
  return B;
}
// Centre the drawn graph in the canvas at the current zoom; ⚠per axis only when it fits — a larger graph keeps the top-left anchor.
// fresh: re-measure the visible band (fit time); otherwise re-measure only when the canvas moved in the page (band[2]) — a scroll never re-centres.
function plCentre(E, cv, fresh){
  const B = plDrawBox(plVG(E)), z = E.view.z, cw = cv.clientWidth, ch = cv.clientHeight || 400;
  if(!isFinite(B.l) || !isFinite(B.t)) return;   // ⚠no stages: an empty box would write NaN into the view
  if((B.r - B.l) * z <= cw) E.view.x = Math.round((cw - (B.r + B.l) * z) / 2);
  if((B.b - B.t) * z > ch) return;
  if(fresh || !E.visY || E.visY[2] !== plVisY(cv)[2]) E.visY = plVisY(cv);
  const a = Math.min(E.visY[0], ch), b = Math.min(E.visY[1], ch), h = (B.b - B.t) * z;
  E.view.y = Math.round(Math.max(-B.t * z, Math.min(ch - B.b * z, a + (b - a - h) / 2 - B.t * z)));   // never above the canvas top
}
// Canvas rows [top, bottom] inside the scrolling #feed and the window; ⚠a run card above the editor pushes the canvas below the fold.
function plVisY(cv){
  const ch = cv.clientHeight || 400;
  if(!cv.getBoundingClientRect) return [0, ch, ''];
  const r = cv.getBoundingClientRect(), fd = document.getElementById('feed'), f = fd ? fd.getBoundingClientRect() : { top: 0, bottom: innerHeight };
  const k = [r.top - f.top + (fd ? fd.scrollTop || 0 : 0), f.top, f.bottom, innerHeight, ch].map(Math.round).join('/');   // layout only: scroll-independent
  const ct = r.top + (cv.clientTop || 0), a = Math.max(0, Math.max(f.top, 0) - ct), b = Math.min(ch, Math.min(f.bottom, innerHeight) - ct);
  return b - a >= 120 ? [a, b, k] : [0, ch, k];   // hardly any of it on screen: centre in the whole canvas
}
// ctr («Fit to view») or E.first (first open until any interaction): centre the drawn graph in the canvas.
// E.ctrd = view is centred (first open / «Fit to view») until the user pans, zooms or drags: a stage click or add must not drop it.
function plFit(E, cv, relayout, keepZ, ctr){
  if(!cv || !cv.clientWidth) return;
  const G = E.G, cw = cv.clientWidth, ch = cv.clientHeight || 400, z0 = keepZ && E.view ? E.view.z : 0;
  if(relayout){
    const W = z0 ? cw / z0 : cw;
    const ws = plgOrder(G).order.map(id => plgW(G, id)), n = ws.length, c = plgCols(n, W, z0 ? 1 : PL_ZMIN, ws);
    plgLayout(G, plgGap(c, W, c === n ? ws : Array(c).fill(Math.max(PLG_W, ...ws))), c);
  }
  const V = plVG(E), w = Math.max(...V.nodes.map(n => n.ui.x + plgW(G, n.id)), PLG_W) + PLG_X0, top = Math.min(...G.nodes.map(n => n.ui.y), PLG_Y0);
  const bot = Math.max(...G.nodes.map(n => n.ui.y + plgH(G, n.id))) + PLG_LANE * (G.loops.length + 1);
  const z = z0 || (relayout ? Math.max(PL_ZMIN, Math.min(1, cw / w))
                            : Math.max(PL_ZFIT, Math.min(1, cw / w, ch / (bot - top + 2 * PLG_Y0))));
  E.view = { x: 0, y: Math.max(Math.round(Math.max(0, 30 - top) * z), Math.round(Math.min(ch / 6 - (top + PLG_H / 2) * z, (ch - (bot - top) * z) / 2 - top * z))), z };
  if(ctr) E.ctrd = true;
  if(ctr || E.first || E.ctrd) plCentre(E, cv, true);
  E.fitK = plFitKey(E, cv);
}
// What an untouched view was last fitted for: plGwFit re-fits only when this changes (canvas size, stage count).
function plFitKey(E, cv){ return cv.clientWidth + 'x' + cv.clientHeight + '/' + E.G.nodes.length; }
// First paint of saved positions that only fit below PL_ZMIN (★6 stages: 40% floor showed 3 of 6 at 900px, 5 at 1100px):
// wrap into the row count that shows the whole chain at the largest zoom — ties keep fewer rows. Display re-flow only:
// E.laid marks the positions ours, so the draft stays clean.
// Largest zoom at which the whole graph fits the canvas (uncapped; same box as plFit).
function plFitRaw(G, cw, ch){
  const V = plVG({ G: G }), w = Math.max(...V.nodes.map(m => m.ui.x + plgW(G, m.id)), PLG_W) + PLG_X0;
  const top = Math.min(...G.nodes.map(m => m.ui.y), PLG_Y0), bot = Math.max(...G.nodes.map(m => m.ui.y + plgH(G, m.id))) + PLG_LANE * (G.loops.length + 1);
  return Math.min(cw / w, ch / (bot - top + 2 * PLG_Y0));
}
// Canvas height the graph needs at min(1, width-fit) zoom + 8px margin, clamped to [200, 62vh] (same box as plFitRaw).
// ⚠A fixed 62vh canvas row pushed the stage panel below the fold at 1440x900 for a one-row chain.
function plCvNeed(G, cw, vh){
  const cap = Math.max(200, Math.floor(0.62 * vh));
  if(!G || !G.nodes.length) return 200;
  if(!(cw > 0)) return cap;
  const top = Math.min(...G.nodes.map(m => m.ui.y), PLG_Y0), bot = Math.max(...G.nodes.map(m => m.ui.y + plgH(G, m.id))) + PLG_LANE * (G.loops.length + 1);
  const hh = bot - top + 2 * PLG_Y0, z = Math.min(1, plFitRaw(G, cw, Infinity));
  return Math.max(200, Math.min(cap, Math.ceil(hh * z + 8)));
}
function plWrapCols(G, cw, ch){
  const n = plgOrder(G).order.length;
  let best = n, bz = -1;
  // One row readable at >= PL_ZMIN wins (same rule as plgCols); max-zoom search alone wrapped 4 stages into 3+1 at 1440.
  const T1 = JSON.parse(JSON.stringify(G)); plgLayout(T1, 28, n);
  if(Math.min(1, plFitRaw(T1, cw, ch)) >= PL_ZMIN) return n;
  for(let c = n; c >= 1; c--){
    const T = JSON.parse(JSON.stringify(G));
    plgLayout(T, 28, c);
    const z = Math.min(1, plFitRaw(T, cw, ch));
    if(z > bz + 1e-6){ bz = z; best = c; }
  }
  return best;
}
// Best-wrap re-flow shared by first paint, «Arrange» and «Fit to view», so all three show every stage at the same best zoom.
// keepZ («Arrange»): keep the current zoom when the re-flowed chain still fits at it, else fit.
// ⚠Never sets touched: the canvas height settles after the first paint, so plGwFit must re-wrap an untouched view (1440 kept a 66% fit).
function plWrapBest(E, cv, keepZ, ctr){
  if(!cv || !cv.clientWidth || !E.G.nodes.length) return;
  const cw = cv.clientWidth, ch = cv.clientHeight || 400, z0 = E.view ? E.view.z : 0;
  plgLayout(E.G, 28, plWrapCols(E.G, cw, ch));
  E.laid = true;
  plFit(E, cv, false, !!(keepZ && z0 && z0 <= plFitRaw(E.G, cw, ch) + 1e-6), ctr);
}
function plWrapFirst(E, cv){
  if(E.laid || !E.view || E.view.z >= PL_ZMIN) return;
  E.view = null; plWrapBest(E, cv, false);
}
function plZoomLabel(cv, z){ const w = cv && cv.closest('.plcvw'), s = w && w.querySelector('.plzv'); if(s) s.textContent = Math.round(z * 100) + '%'; }
function plApplyView(E, cv){
  const i = cv && cv.querySelector('.plcvi');
  if(i) i.style.transform = 'translate(' + E.view.x + 'px,' + E.view.y + 'px) scale(' + E.view.z + ')';
}
// The editor fills from its top to the feed's bottom (like brPanFit);
// columns scroll inside. Until the user pans/zooms (E.touched), a resize re-fits the chain to the new canvas width.
// Dragged pane height clamped to the editor height H (canvas row keeps PL_SPLIT.cv); 0 = not dragged (CSS default row).
function plPanH(h, H){ return h ? Math.max(PL_SPLIT.min, Math.min(H - 6 - PL_SPLIT.cv, h)) : 0; }
function plGwFit(){
  const g = document.querySelector('.plw .plgw'), fd = document.getElementById('feed');
  if(!g || !fd || mainView !== 'pipe') return;
  // ⚠Offset inside the feed's content (scroll-independent): a restored feed scrollTop used to inflate the height (+380px).
  const top = g.getBoundingClientRect().top - fd.getBoundingClientRect().top - fd.clientTop + fd.scrollTop;
  const pb = parseFloat(getComputedStyle(fd).paddingBottom) || 0;
  let h = Math.floor(fd.clientHeight - top - pb - 8);
  const E = plCurEnt(), cv = g.querySelector('.plcv'), cvw = cv && cv.parentNode;
  // Canvas row = plCvNeed + the strip above the canvas (toolbar, errors); ⚠re-measured every pass: cards grow on a later paint.
  // A dragged split keeps the flexible CSS row (--plpanh sizes the panes instead).
  let row = Math.max(260, Math.min(700, 0.34 * innerHeight));   // no canvas yet: the CSS pre-paint row
  if(E && cv && cvw){
    row = plCvNeed(E.G, cv.clientWidth, innerHeight) + (cvw.clientHeight - cv.clientHeight);
    if(+lsGet(PL_SPLIT.key, 0) || (PLDRAG && PLDRAG.k === 'split')) g.style.removeProperty('--plcvh'); else g.style.setProperty('--plcvh', Math.round(row) + 'px');
  }
  const floor = Math.round(row) + 426;   // canvas row + 6px handle + 420px pane row (43-pipeline.css)
  g.style.height = Math.max(floor, h) + 'px';
  const over = fd.scrollHeight - fd.clientHeight;   // whatever else still overflows (margins, a note line) comes off the editor
  if(over > 0){ h -= over; g.style.height = Math.max(floor, h) + 'px'; }
  const ph = plPanH(+lsGet(PL_SPLIT.key, 0), parseFloat(g.style.height));
  if(ph && !(PLDRAG && PLDRAG.k === 'split')) g.style.setProperty(PL_SPLIT.v, ph + 'px');   // ⚠mid-drag the stored value is stale
  // ⚠Re-fit only when the canvas size changed: plGwFit runs on every paint (node click, poll) and must not move the zoom.
  if(E && cv && E.view && !E.touched && cv.clientWidth && E.fitK !== plFitKey(E, cv)){
    const clean = plgKey(E.G) === E.base;
    if(E.laid) plWrapBest(E, cv, false); else plFit(E, cv, false);
    if(E.laid && clean) E.base = plgKey(E.G);   // our own layout never makes the draft dirty
    plApplyView(E, cv); plPaintEdgesNodes(E, cv); plZoomLabel(cv, E.view.z);
  }
  // ⚠Still first open (no interaction yet): the live run (status pills, gate lines) arrives on a later paint and grows the cards.
  if(E && cv && E.view && E.first && !E.touched && cv.clientWidth){ const k = E.view.x + ',' + E.view.y; plCentre(E, cv); if(k !== E.view.x + ',' + E.view.y) plApplyView(E, cv); }
}
// Graph as shown: saved positions + plgPush x + plgAlign y (E.pxF/E.pyF = frozen during a node drag). Geometry reads this, edits go to E.G.
function plVG(E){
  const G = E.G, px = E.pxF || plgPush(G), py = E.pyF || plgAlign(G);
  if(!Object.keys(px).length && !Object.keys(py).length) return G;
  return Object.assign({}, G, { nodes: G.nodes.map(n => px[n.id] == null && py[n.id] == null ? n
    : Object.assign({}, n, { ui: Object.assign({}, n.ui, px[n.id] == null ? {} : { x: px[n.id] }, py[n.id] == null ? {} : { y: py[n.id] }) })) });
}
// Re-place nodes and edges in place after a re-flow (no innerHTML rebuild).
function plPaintEdgesNodes(E, cv){
  plVG(E).nodes.forEach(n => { const el = cv.querySelector('[data-plnode="' + n.id + '"]'); if(el){ el.style.left = n.ui.x + 'px'; el.style.top = n.ui.y + 'px'; } });
  plRedrawEdges(E, cv);
}
// Loop-label pills sized from the rendered text (user units, so zoom does not matter); ⚠a chars*px guess overflowed on Hangul.
function plFitPills(root){
  (root || document).querySelectorAll('.pllt').forEach(t => {
    const tx = t.querySelector('text'), r = t.querySelector('rect'); let w = 0;
    try{ w = tx.getComputedTextLength(); }catch(e){ softErr('plpill', e); }
    if(!(w > 0)) return;
    const W = Math.ceil(w) + 20, x = Math.max(+tx.getAttribute('x'), W / 2 + 4);   // same left clamp as plEdgesSvg
    tx.setAttribute('x', x); r.setAttribute('x', x - W / 2); r.setAttribute('width', W);
  });
}
if(document.fonts && document.fonts.ready) document.fonts.ready.then(() => plFitPills());
let plFitQ = 0;
function plFitSoon(){ if(!plFitQ) plFitQ = requestAnimationFrame(() => { plFitQ = 0; plGwFit(); }); }
window.addEventListener('resize', plFitSoon);
document.addEventListener('scroll', e => { if(e.target && e.target.id === 'feed' && mainView === 'pipe') plFitSoon(); }, true);
// ⚠In-place size changes (a <details> toggle, late content) skip the repaint: without this the editor kept its old height and left a blank under the run panels.
const PLRO = typeof ResizeObserver === 'function' ? new ResizeObserver(() => plFitSoon()) : null;
// Node sizes follow their content (CSS max-content 184..320px, min-height 100px): read them back into G.wd/G.ht for edges, ports and «Arrange»;
// a clipped title/agent gets its full text as a tooltip. Returns true if any size changed.
function plMeasure(E, cv){
  if(!E || !cv) return false;
  const wd = E.G.wd || (E.G.wd = {}), ht = E.G.ht || (E.G.ht = {});
  let ch = false;
  cv.querySelectorAll('[data-plnode]').forEach(el => {
    const w = el.offsetWidth, h = el.offsetHeight, id = el.dataset.plnode;
    if(w > 0 && wd[id] !== w){ wd[id] = w; ch = true; }
    if(h > 0 && ht[id] !== h){ ht[id] = h; ch = true; }   // min-height 100: the gate result line grows the card
    const n = plgNode(E.G, id) || {};   // .plt also holds the retry badge: tooltip = the title alone
    el.querySelectorAll('.plt,.plna,.plnm').forEach(t => { if(t.scrollWidth > t.clientWidth) t.title = t.classList.contains('plt') ? plgShow(n.title || '') : t.textContent; });
  });
  return ch;
}
function plAfterPaint(box){
  const E0 = plCurEnt(), cv0 = box.querySelector('.plcv');
  if(plMeasure(E0, cv0)) plPaintEdgesNodes(E0, cv0);   // new widths can push neighbours; before plGwFit: an auto re-flow («Arrange») needs the real widths
  plGwFit();
  if(PLRO){ PLRO.disconnect(); const pw = box.querySelector('.plw'); if(pw) PLRO.observe(pw); }
  const E = plCurEnt(), cv = box.querySelector('.plcv');
  if(E && cv && !E.view){ E.first = true; E.ctrd = true; E.laid = E.auto; plFit(E, cv, E.auto); E.auto = false; plWrapFirst(E, cv); if(E.view){ if(E.laid) E.base = plgKey(E.G); plApplyView(E, cv); plPaintEdgesNodes(E, cv); plZoomLabel(cv, E.view.z); } }
  plFitPills(box);
}
