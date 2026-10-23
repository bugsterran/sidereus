// ── Structure «Architecture» module detail: side panel, path bar «All › layer › group › module», flow / path-level highlight ──────
// ⚠Only called from inside 84j functions (typeof guards there): no top-level reads of 84j names. ARCH is owned by 84j; fields only.
// ⚠Names, summaries, group ids and flow names are agent data: esc only, never T(). No scroll / focus centring anywhere (R4).
const ARCH_NBR_KINDS = ['call', 'read', 'write', 'event', 'other'];
const ARCH_NBR_LBL = { call: 'Calls', read: 'Reads', write: 'Writes', event: 'Events', other: 'Other' };
// Pure: own-key lookup, so an id like «constructor» never reads the prototype.
function archOwn(o, k){ return !!o && Object.prototype.hasOwnProperty.call(o, String(k)); }
function archGroupName(groups, id){
  const g = (groups || []).find(x => x && x.id != null && String(x.id) === String(id));
  return g && g.name ? String(g.name) : String(id == null ? '' : id);
}
// Pure: drawn pair keys «from\u0001to» (module ids) of the current view — same rules as archSrc / archBandSrc.
function archDrawn(mods, edges, tests, sel, full){
  let ps = archPairs(mods, edges, tests);
  if(sel) ps = ps.filter(p => p.from === sel || p.to === sel);
  else if(!full) ps = archReduce(ps);
  return new Set(ps.map(p => p.from + '\u0001' + p.to));
}
// Pure: flows with a step touching module id → [{f, n steps, on steps drawn}] (drawn = Set from archDrawn, either direction).
function archFlowsVia(d, id, drawn){
  const fls = (d && Array.isArray(d.flows) ? d.flows : []).filter(f => f && f.id != null && Array.isArray(f.steps));
  return fls.filter(f => f.steps.some(s => s && (s.from === id || s.to === id))).map(f => {
    const st = f.steps.filter(s => s && s.from != null && s.to != null);
    const on = drawn ? st.filter(s => drawn.has(s.from + '\u0001' + s.to) || drawn.has(s.to + '\u0001' + s.from)).length : st.length;
    return { f, n: st.length, on };
  });
}
// Pure: highlight set on the svg (node keys m<i> / en<n>, edge keys a\u0001b). q = {flow: id, fs?: ids, tests} → entry nodes + steps of each,
// x = edge keys of unproven steps (kept in --nx-err); {layer, group} → members; {mods: [a, b]} → both modules; {edge: i} → that edge + its two ends,
// or with flow the flow's set; k = the row's own edge (.arevk).
function archLitSet(d, q){
  const mods = (d && d.modules) || [], ix = {}, n = new Set(), e = new Set(), x = new Set(), k = new Set();
  if(!q) return null;
  mods.forEach((m, i) => { if(m && m.id != null) ix[m.id] = 'm' + i; });
  const pair = (a, b, to) => { if(archOwn(ix, a) && archOwn(ix, b)){ to.add(ix[a] + '\u0001' + ix[b]); to.add(ix[b] + '\u0001' + ix[a]); } };
  const ed = q.edge != null ? ((d && d.edges) || [])[q.edge] : null;
  if(q.edge != null){ if(!ed) return null; pair(ed.from, ed.to, k); }
  if(ed && q.flow == null){ [ed.from, ed.to].forEach(id => { if(archOwn(ix, id)) n.add(ix[id]); }); pair(ed.from, ed.to, e); return { n, e, k }; }
  if(Array.isArray(q.mods)){ q.mods.forEach(id => { if(archOwn(ix, id)) n.add(ix[id]); }); pair(q.mods[0], q.mods[1], e); pair(q.mods[0], q.mods[1], k); return { n, e, k }; }   // 84j6 step without an edge
  const fs = Array.isArray(q.fs) && q.fs.length ? q.fs.map(String) : q.flow != null ? [String(q.flow)] : null;   // fs = union of flows (84j4 entry click)
  if(fs){
    const ens = typeof archFlowEntries === 'function' ? archFlowEntries(d, mods, !!q.tests) : [];
    fs.forEach(id => {
      const f = ((d && d.flows) || []).find(y => y && String(y.id) === id), st = (f && f.steps) || [];
      st.forEach(s => { if(!s) return; [s.from, s.to].forEach(k => { if(archOwn(ix, k)) n.add(ix[k]); }); pair(s.from, s.to, e); if(!s.ok) pair(s.from, s.to, x); });
      const s0 = st[0] && st[0].from;
      if(archOwn(ix, s0)) ens.forEach(en => { if(en.flows.indexOf(id) >= 0){ n.add(en.k); e.add(en.k + '\u0001' + ix[s0]); } });
    });
    return { n, e, x, k };
  }
  if(!q.layer) return null;
  const mem = mods.filter(m => m && m.id != null && m.layer === q.layer && (q.group == null || String(m.group) === String(q.group)));
  const ids = new Set(mem.map(m => m.id));
  mem.forEach(m => n.add(ix[m.id]));
  ((d && d.edges) || []).forEach(x => { if(x && ids.has(x.from) && ids.has(x.to)) pair(x.from, x.to, e); });
  return { n, e };
}
// Class-only paint of the highlight. ⚠.arlit / svg.arlitdim are separate from hover .arn / .archdim, so archHovPaint(svg, null) keeps them.
function archLitPaint(svg, set){
  if(!svg || !svg.querySelectorAll) return;
  svg.classList.toggle('arlitdim', !!set);
  svg.querySelectorAll('[data-p]').forEach(g => g.classList.toggle('arlit', !!set && set.n.has(g.dataset.p)));
  svg.querySelectorAll('.mmdfe').forEach(g => { const k = g.dataset.f + '\u0001' + g.dataset.t;
    g.classList.toggle('arlit', !!set && set.e.has(k)); g.classList.toggle('archfx', !!set && !!set.x && set.x.has(k));
    g.classList.toggle('arevk', !!set && !!set.k && set.k.has(k)); });
}
// Current highlight of the project on screen: hovered edge row > pinned row (ARCH.op) > lit flow > path level in the overview.
function archLitQ(p){
  // ⚠Entry nodes are drawn in the overview and focus view; tests must match archPaint's (a focused test module counts) so en<n> keys match.
  const fm = ARCH.sel && ARCH.sel.p === p ? ((ARCH.cache[p] || {}).modules || []).find(m => m && m.id === ARCH.sel.id) : null;
  const tests = !!ARCH.tests || (!!fm && archIsTest(fm)), lit = ARCH.lit && ARCH.lit.p === p ? ARCH.lit : null;
  const hv = typeof ARCH_EVL !== 'undefined' && ARCH_EVL && ARCH_EVL.p === p ? ARCH_EVL : null;   // 84j5 row hover
  const os = typeof ARCH.op === 'string' && ARCH.op.indexOf(p + '\t') === 0 ? ARCH.op.slice(p.length + 1) : '', om = /^f(\d+)(?:\.(\d+))?$/.exec(os);
  const es = (ARCH.cache[p] || {}).edges || [], ok = i => i >= 0 && !!es[i];   // ⚠a refetch may drop the edge: stale index falls back to lit/scope
  const eq = i => { const f = typeof archEvFlow === 'function' ? archEvFlow(ARCH.cache[p], i, lit ? (lit.fs || [lit.flow]) : null) : null;
    return f != null ? { edge: i, flow: f, tests } : { edge: i, tests }; };
  const tq = (n, k) => typeof archEdTreeQ === 'function' ? archEdTreeQ(ARCH.cache[p], n, k, tests) : null;   // 84j6 flow / step row (stale n, k → null)
  const hq = !hv ? null : hv.f != null ? tq(hv.f, hv.s) : ok(hv.i) ? eq(hv.i) : null;
  const pq = om ? tq(parseInt(om[1], 10), om[2] != null ? parseInt(om[2], 10) : null) : os && ok(parseInt(os, 10)) ? eq(parseInt(os, 10)) : null;
  if(hq || pq) return hq || pq;
  if(lit) return { flow: lit.flow, fs: lit.fs, tests };
  const sel = ARCH.sel && ARCH.sel.p === p, sc = ARCH.scope;
  return !sel && sc && sc.p === p && sc.layer ? { layer: sc.layer, group: sc.group } : null;
}
function archLitNow(slot){
  const svg = slot && slot.querySelector && slot.querySelector('svg'), p = strOn[0] || '';
  if(typeof archEvlLive === 'function') archEvlLive(p);   // 84j5: drop a hover that a repaint left behind
  if(svg) archLitPaint(svg, archLitSet(ARCH.cache[p], archLitQ(p)));
  if(typeof archMmSync === 'function') archMmSync(slot);   // 84j7 minimap mirrors the lit classes
  if(typeof archLitCount === 'function' && slot && slot.closest) archLitCount(slot.closest('.archmap'));   // 84k off-screen line
  if(typeof archOffMark === 'function') archOffMark(slot);   // 84j5 «Off screen» marker for the row's edge
}
// Pure: path bar. sel = focused module id ('' none); scope = {layer, group} path level in the overview. '' when neither.
function archPathHtml(mods, groups, sel, scope){
  const m = sel ? (mods || []).find(x => x && x.id === sel) : null, at = m || scope;
  if(!at) return '';
  const ly = typeof at.layer === 'string' && at.layer ? at.layer : '', gr = ly && at.group != null ? at.group : null;
  const seg = [['all', T('All')]];
  if(ly) seg.push(['layer', archOwn(ARCH_LAYER_LBL, ly) ? T(ARCH_LAYER_LBL[ly], 'arch layer') : ly]);
  if(gr != null) seg.push(['group', archGroupName(groups, gr)]);
  if(m) seg.push(['mod', String(m.name || m.id)]);
  return '<nav class=archpath aria-label="' + esc(T('Path')) + '">' + seg.map((s, i) => '<button type=button data-arpath=' + s[0]
    + (i === seg.length - 1 ? ' aria-current=location' : '') + '>' + esc(s[1]) + '</button>').join('<i aria-hidden=true>›</i>') + '</nav>';
}
// Pure: one level up — module → its group (or layer) → layer → All; null at the top.
function archUp(st, mods){
  const m = st && st.sel ? (mods || []).find(x => x && x.id === st.sel) : null, sc = st && st.scope;
  if(st && st.sel) return { scope: m && m.layer ? { layer: m.layer, group: m.group != null ? m.group : null } : null };
  if(sc && sc.layer && sc.group != null) return { scope: { layer: sc.layer, group: null } };
  if(sc && sc.layer) return { scope: null };
  return null;
}
// Pure: neighbours of sel grouped Out/In → kind; leaves are 84j archEdgeRow (data-ae evidence toggle unchanged). nx[key] = folded.
function archNbrTree(d, sel, names, nx, ro){
  const es = (d && d.edges) || [], o = ro || {}, br = { out: {}, in: {} };
  es.forEach((e, i) => { if(!e || (e.from !== sel && e.to !== sel)) return;
    const dir = e.from === sel ? 'out' : 'in', k = ARCH_NBR_KINDS.indexOf(e.kind) >= 0 ? e.kind : 'other';
    (br[dir][k] = br[dir][k] || []).push({ e, i }); });
  const fold = k => archOwn(nx, k) && nx[k], btn = (k, lbl, n) => '<button type=button class=archnxb data-arnx="' + k + '" aria-expanded=' + (fold(k) ? 'false' : 'true') + '>'
    + '<i aria-hidden=true>' + (fold(k) ? '▸' : '▾') + '</i>' + esc(lbl) + '<small>' + n + '</small></button>';
  const dirs = ['out', 'in'].filter(dir => Object.keys(br[dir]).length);
  if(!dirs.length) return '<div class=archevn>' + esc(T('No edges')) + '</div>';
  return '<ul class=archnx role=tree>' + dirs.map(dir => {
    const ks = ARCH_NBR_KINDS.filter(k => br[dir][k]), tot = ks.reduce((a, k) => a + br[dir][k].length, 0);
    return '<li class="archnxd ' + dir + '" role=treeitem>' + btn(dir, T(dir === 'in' ? 'In' : 'Out'), tot) + (fold(dir) ? '' : '<ul role=group>' + ks.map(k => {
      const key = dir + ':' + k, rows = br[dir][k].slice().sort((a, b) => (b.e.ok ? 1 : 0) - (a.e.ok ? 1 : 0));   // passed first
      return '<li role=treeitem>' + btn(key, T(ARCH_NBR_LBL[k], 'arch nbr'), rows.length) + (fold(key) ? ''
        : '<ul class=archnxl>' + rows.map(r => archEdgeRow(r.e, names, r.i, !!(o.op && o.op(r.i)), dir, o.dv && o.dv(r.i), o.sn)).join('') + '</ul>') + '</li>';
    }).join('') + '</ul>') + '</li>';
  }).join('') + '</ul>';
}
// Files under the focused module's path at the map commit (/api/arch/files): c[p\tid] = {commit, r}, load[p\tid] = in flight,
// fold = section folded (starts folded, memory only), op[p\tid] = open folder keys (repo paths, null-proto).
const ARCH_FL = { c: {}, load: {}, fold: true, op: {} };
const ARCH_FL_WHY = { nopath: 'This module has no path', ext: 'External module — no files in this repository', gone: 'Path not found at the diagram commit',
  nomap: 'No diagram for this project', bad: 'Request refused', git: 'Could not list files' };
// Pure: repo paths → folder tree relative to the module path pre: {k: folder repo path, d: name → child, f: [[name, path]], n: files below}.
// A path outside pre keeps its full path. ⚠null-proto maps: folder names are repo data («__proto__» stays a plain key).
function archFlTree(files, pre){
  const b = String(pre || '').replace(/\/+$/, ''), node = k => ({ k, d: Object.create(null), f: [], n: 0 }), root = node(b);
  (files || []).forEach(x => { const s = String(x), inb = !!b && s.indexOf(b + '/') === 0;
    const seg = (inb ? s.slice(b.length + 1) : s).split('/').filter(Boolean);
    let at = root, k = inb ? b : '';
    root.n++;
    seg.slice(0, -1).forEach(nm => { k = k ? k + '/' + nm : nm; at = at.d[nm] = at.d[nm] || node(k); at.n++; });
    at.f.push([seg.length ? seg[seg.length - 1] : s, s]); });
  return root;
}
// Pure: every folder key of a tree (for «Expand all»).
function archFlDirs(t){ const out = []; Object.keys(t.d).forEach(nm => { out.push(t.d[nm].k); out.push(...archFlDirs(t.d[nm])); }); return out; }
// Pure: one tree level — folders («name/ <count>», data-arfdir toggles) then files (data-arfopen → Source popup); open = folder keys shown open.
function archFlRows(t, open){
  const by = (a, b) => a < b ? -1 : a > b ? 1 : 0;
  return Object.keys(t.d).sort(by).map(nm => { const c = t.d[nm], on = archOwn(open, c.k) && !!open[c.k];
    return '<li role=treeitem><button type=button class="archnxb archfld" data-arfdir="' + esc(c.k) + '" aria-expanded=' + (on ? 'true' : 'false') + '>'
      + '<i aria-hidden=true>' + (on ? '▾' : '▸') + '</i>' + esc(nm + '/') + '<small>' + c.n + '</small></button>'
      + (on ? '<ul role=group>' + archFlRows(c, open) + '</ul>' : '') + '</li>'; }).join('')
    + t.f.slice().sort((a, b) => by(a[0], b[0])).map(f => '<li role=treeitem><button type=button class=archflf data-arfopen="' + esc(f[1])
      + '" title="' + esc(f[1]) + '">' + esc(f[0]) + '</button></li>').join('');
}
// Pure: «Files <n>» fold header (+ Expand / Collapse all when there are folders) + first-level tree + «+N more» / «N+ more» when cut;
// r null = loading; why = one-line reason; pre = module path (default r.path).
function archFilesHtml(r, fold, open, pre){
  const why = r && (r.why || (r.ok === false ? 'git' : '')), fs = r && !why ? (Array.isArray(r.files) ? r.files : []) : null;   // ⚠ok reply without files = empty, not loading
  const tot = fs ? Math.max(typeof r.total === 'number' ? r.total : 0, fs.length) : 0, cut = !!(fs && r.cut);
  const tr = fs && fs.length && !fold ? archFlTree(fs, pre != null ? pre : r.path) : null;
  const hd = '<div class=archdh><button type=button class="archnxb archflb" data-arfiles aria-expanded=' + (fold ? 'false' : 'true') + '>'
    + '<i aria-hidden=true>' + (fold ? '▸' : '▾') + '</i>' + esc(T('Files')) + (fs ? '<small>' + tot + (cut ? '+' : '') + '</small>' : '') + '</button>'
    + (tr && Object.keys(tr.d).length ? '<button type=button class=archnxa data-arfexp=1>' + esc(T('Expand all')) + '</button>'
      + '<button type=button class=archnxa data-arfexp=0>' + esc(T('Collapse all')) + '</button>' : '') + '</div>';
  if(fold) return hd;
  if(!r) return hd + '<div class=archevn>' + esc(T('Loading files…')) + '</div>';
  if(why) return hd + '<div class=archevn>' + esc(T(archOwn(ARCH_FL_WHY, why) ? ARCH_FL_WHY[why] : ARCH_FL_WHY.git)) + '</div>';
  if(!fs.length) return hd + '<div class=archevn>' + esc(T('No files at the diagram commit')) + '</div>';
  const more = tot - fs.length;
  return hd + '<ul class=archfiles role=tree>' + archFlRows(tr, open || {}) + '</ul>'
    + (cut ? '<div class=archevn>' + esc(T('{n}+ more').replace('{n}', more > 0 ? more : 0)) + '</div>'
      : more > 0 ? '<div class=archevn>' + esc(T('+{n} more').replace('{n}', more)) + '</div>' : '');
}
// ⚠archPaint skips a repaint while its sig is unchanged, and ARCH_FL is not in that sig: drop the box sig first.
function archFlRepaint(){
  const b = typeof document !== 'undefined' && document.getElementById ? document.getElementById('feed') : null;
  if(b) b._arsig = '';
  paintStruct();
}
// One fetch per (project, module, map commit); a reply for another commit is dropped (the map refetch repaints and asks again).
function archFilesKick(p, commit, id){
  const k = p + '\t' + id, c = ARCH_FL.c[k];
  if(ARCH_FL.load[k] || (c && c.commit === commit)) return;
  ARCH_FL.load[k] = 1;
  fetch('/api/arch/files?path=' + encodeURIComponent(p) + '&id=' + encodeURIComponent(id), { cache: 'no-store' })
    .then(r => r.json().catch(() => null)).catch(() => null)
    .then(j => { delete ARCH_FL.load[k];
      const d = ARCH.cache[p], cm = String((d && d.commit) || '');
      if(cm !== commit || (j && j.commit && String(j.commit) !== cm)) return;
      ARCH_FL.c[k] = { commit, r: j || { ok: false, why: 'git' } };
      if(ARCH.sel && ARCH.sel.p === p && ARCH.sel.id === id && mainView === 'struct' && strMode === 'arch') archFlRepaint(); });
}
// Files section for module m of map d; empty path / external answered locally. '' when 84j3 consts are not loaded (84j tests).
function archFilesSec(d, m){
  if(typeof ARCH_FL === 'undefined' || !ARCH.sel) return '';
  if(!m.path || m.ext) return archFilesHtml({ ok: false, why: m.ext ? 'ext' : 'nopath' }, ARCH_FL.fold);
  const p = ARCH.sel.p, cm = String((d && d.commit) || ''), k = p + '\t' + m.id, c = ARCH_FL.c[k];
  const r = c && c.commit === cm ? c.r : null;
  if(!r) archFilesKick(p, cm, m.id);
  return archFilesHtml(r, ARCH_FL.fold, ARCH_FL.op[k], m.path);
}
// Folder toggle (dir = key) or Expand / Collapse all (all = true / false) of the focused module's file tree; memory only.
function archFlOpen(p, dir, all){
  const id = ARCH.sel && ARCH.sel.p === p ? ARCH.sel.id : null, k = p + '\t' + id;
  if(id == null) return;
  const o = Object.assign(Object.create(null), all === false ? null : ARCH_FL.op[k]);
  if(all){ const c = ARCH_FL.c[k], m = (((ARCH.cache[p] || {}).modules) || []).find(x => x && x.id === id);
    archFlDirs(archFlTree(c && c.r && Array.isArray(c.r.files) ? c.r.files : [], m && m.path)).forEach(x => { o[x] = true; }); }
  else if(all == null){ if(archOwn(o, dir) && o[dir]) delete o[dir]; else o[dir] = true; }
  ARCH_FL.op[k] = o;
}
// Pure: side panel for the focused module. ro = {op(i), dv(i), sn, drawn: Set, lit: flow id | null}.
function archDetHtml(d, sel, names, nx, ro){
  const mods = (d && d.modules) || [], m = mods.find(x => x && x.id === sel), o = ro || {};
  if(!m) return '';
  const ly = typeof m.layer === 'string' && m.layer ? m.layer : '';
  const ow = (Array.isArray(m.owns) ? m.owns : []).map(x => archOwn(names, x) && names[x] ? String(names[x]) : String(x));
  const row = (k, v) => '<dt>' + esc(T(k)) + '</dt><dd>' + esc(v) + '</dd>';
  const fv = archFlowsVia(d, sel, o.drawn);
  return '<aside class="archside archdetp"><div class=archsh><b>' + esc(m.name || m.id) + '</b><span>' + esc(m.path || '') + '</span>'
    + '<button type=button class=archrf data-arf title="' + esc(T('Reload now')) + '">↻</button></div><div class=archdet>'
    + (m.summary ? '<p class=archsum>' + esc(m.summary) + '</p>' : '')
    + '<dl class=archmeta>' + (ly ? row('Layer', archOwn(ARCH_LAYER_LBL, ly) ? T(ARCH_LAYER_LBL[ly], 'arch layer') : ly) : '')
    + (m.group != null ? row('Group', archGroupName(d.groups, m.group)) : '') + (ow.length ? row('Owns', ow.join(', ')) : '') + '</dl>'
    + '<div class=archdh><b>' + esc(T('Neighbours')) + '</b><button type=button class=archnxa data-arnall=1>' + esc(T('Expand all')) + '</button>'
    + '<button type=button class=archnxa data-arnall=0>' + esc(T('Collapse all')) + '</button></div>' + archNbrTree(d, sel, names, nx, o)
    + '<div class=archdh><b>' + esc(T('Flows through here')) + '</b></div>'
    + (fv.length ? '<ul class=archfv>' + fv.map(x => { const on = o.lit != null && String(o.lit) === String(x.f.id);
      return '<li><button type=button data-arfx="' + esc(x.f.id) + '" aria-pressed=' + (on ? 'true' : 'false') + (on ? ' class=on' : '') + '>'
        + '<b>' + esc((x.f.ok ? '✓ ' : '✗ ') + (x.f.name || x.f.id)) + '</b>'
        + (x.on < x.n ? '<small>' + esc(T('{a}/{b} steps on this view').replace('{a}', x.on).replace('{b}', x.n)) + '</small>' : '') + '</button></li>'; }).join('') + '</ul>'
      : '<div class=archevn>' + esc(T('No flow passes through this module')) + '</div>')
    + archFilesSec(d, m) + '</div></aside>';   // relations first, the file list last
}
// Path level / up: overview stays (cached svg, no re-layout), members light up; scroll is kept by archPaint.
function archGoUp(p, r){ ARCH.sel = null; ARCH.op = ''; ARCH.scope = r && r.scope ? { p, layer: r.scope.layer, group: r.scope.group } : null; paintStruct(); }
function archPathClick(p, lv){
  const d = ARCH.cache[p] || {}, mods = d.modules || [], m = ARCH.sel && ARCH.sel.p === p ? mods.find(x => x && x.id === ARCH.sel.id) : null;
  const at = m || (ARCH.scope && ARCH.scope.p === p ? ARCH.scope : null);
  if(lv === 'mod' || !at) return;
  if(lv === 'all'){ ARCH.lit = null; archGoUp(p, null); return; }
  archGoUp(p, { scope: { layer: at.layer, group: lv === 'group' && at.group != null ? at.group : null } });
}
document.addEventListener('click', ev => {
  const t = ev.target && ev.target.closest ? ev.target : null;
  if(!t || !t.closest('.archtab') || strMode !== 'arch') return;
  const p = strOn[0] || '', b = t.closest('[data-arpath],[data-arfx],[data-arnx],[data-arnall],[data-arfiles],[data-arfdir],[data-arfexp],[data-arfopen]');
  if(!b) return;
  const hadF = document.activeElement === b, hold = s => { if(hadF && typeof kbHold === 'function') kbHold(s); };   // ⚠the repaint drops focus to <body>
  if(b.dataset.arpath){ const lv = b.dataset.arpath; archPathClick(p, lv); hold('.archpath [data-arpath=' + lv + ']'); return; }
  if(b.dataset.arfx != null){ const id = b.dataset.arfx;
    ARCH.lit = ARCH.lit && ARCH.lit.p === p && String(ARCH.lit.flow) === id ? null : { p, flow: id }; paintStruct(); return; }
  if(b.dataset.arnx != null){ const k = b.dataset.arnx; ARCH.nx = Object.assign({}, ARCH.nx); ARCH.nx[k] = !(archOwn(ARCH.nx, k) && ARCH.nx[k]);
    paintStruct(); hold('.archdet [data-arnx="' + k + '"]'); return; }
  if(b.dataset.arfiles != null){ ARCH_FL.fold = !ARCH_FL.fold; archFlRepaint(); hold('.archdet [data-arfiles]'); return; }
  if(b.dataset.arfdir != null){ const k = b.dataset.arfdir; archFlOpen(p, k); archFlRepaint();
    hold('.archdet [data-arfdir="' + k.replace(/["\\]/g, '\\$&') + '"]'); return; }   // ⚠folder names may hold quotes
  if(b.dataset.arfexp != null){ archFlOpen(p, null, b.dataset.arfexp === '1'); archFlRepaint(); hold('.archdet [data-arfexp="' + b.dataset.arfexp + '"]'); return; }
  if(b.dataset.arfopen != null){ strPopOpenTree(p, b.dataset.arfopen, 1); return; }   // line 1: an extension-less file is not taken for a folder
  if(b.dataset.arnall != null){ const nx = {};
    if(b.dataset.arnall === '0'){ const d = ARCH.cache[p] || {}, sel = ARCH.sel && ARCH.sel.id;
      ((d.edges) || []).forEach(e => { if(!e || (e.from !== sel && e.to !== sel)) return;
        const dir = e.from === sel ? 'out' : 'in'; nx[dir] = true; nx[dir + ':' + (ARCH_NBR_KINDS.indexOf(e.kind) >= 0 ? e.kind : 'other')] = true; }); }
    ARCH.nx = nx; paintStruct(); hold('.archdet [data-arnall="' + b.dataset.arnall + '"]'); return; }
});
// Pure guard for Esc: false in fields, after another handler, while a code popup / palette / drawer is open, or off the arch view.
function archEscOk(e, st){
  const t = e && e.target, tag = t && t.tagName ? String(t.tagName).toLowerCase() : '';
  if(!e || e.key !== 'Escape' || e.defaultPrevented || e.isComposing) return false;
  if(tag === 'input' || tag === 'select' || tag === 'textarea' || (t && t.isContentEditable)) return false;
  return !!st && st.view === 'struct' && st.mode === 'arch' && !st.pop && !st.pal;
}
// One Esc press (true = handled): a lit flow (and its sequence view) clears first, then one level up.
function archEscStep(p){
  if((ARCH.lit && ARCH.lit.p === p) || (ARCH.flow && ARCH.flow.p === p)){ ARCH.lit = null; ARCH.flow = null; paintStruct(); return true; }
  const d = ARCH.cache[p] || {};
  const r = archUp({ sel: ARCH.sel && ARCH.sel.p === p ? ARCH.sel.id : '', scope: ARCH.scope && ARCH.scope.p === p ? ARCH.scope : null }, d.modules);
  if(!r) return false;
  archGoUp(p, r);
  return true;
}
// ⚠Capture phase: 35c closes the code popup on Esc in the bubble phase, and that same press must not also go up a level.
document.addEventListener('keydown', e => {
  const st = { view: mainView, mode: strMode, pop: typeof strPop !== 'undefined' && !!strPop, pal: (typeof cpOn !== 'undefined' && cpOn)
    || (typeof SESOPEN !== 'undefined' && !!SESOPEN) || (typeof alarmOpen !== 'undefined' && !!alarmOpen) };
  if(archEscOk(e, st) && archEscStep(strOn[0] || '')) e.preventDefault();
}, true);
