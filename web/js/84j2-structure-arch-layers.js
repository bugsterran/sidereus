// ── Structure «Architecture» v2 overview: layer bands top → bottom, group boxes inside, edge kinds (called from 84j) ──────
// ⚠Only called from inside 84j functions: no top-level reads of 84j names. A v1 map never reaches this file (archHasLayers).
const ARCH_LAYERS = ['entry', 'ui', 'api', 'service', 'domain', 'shared', 'infra', 'data'];
const ARCH_LAYER_LBL = { entry: 'Entry', ui: 'UI', api: 'API', service: 'Service', domain: 'Domain', shared: 'Shared', infra: 'Infra', data: 'Data' };
const ARCH_KIND_LBL = { call: 'Call', read: 'Read', write: 'Write', event: 'Event', uses: 'Uses' };
// R1/R4: v2 map whose every visible module has a known layer (externals get their own band, so theirs is not needed).
function archHasLayers(d, tests){
  if(!d || d.v !== 2) return false;
  const ms = (d.modules || []).filter(m => m && m.id != null && (tests || !archIsTest(m)));
  return ms.length > 0 && ms.every(m => m.kind === 'external' || ARCH_LAYERS.indexOf(m.layer) >= 0);
}
// Styles without a layer stack (feature packages, apps, ...): 8 layer bands put one feature's files in five bands, so these
// draw 4 location bands instead. ⚠Labels stay ≤ 28 chars (band title width sets the band's minimum width).
const ARCH_BAND_LOC = ['feature-pkgs', 'feature-folders', 'modular', 'apps', 'routes', 'crates', 'library', 'other'];
const ARCH_LAYER_TIP = { entry: 'Entry · where requests start', ui: 'UI · screens and components', api: 'API · request handlers',
  service: 'Service · business logic', domain: 'Domain · core models and rules', shared: 'Shared · common helpers',
  infra: 'Infra · platform glue', data: 'Data · storage and schemas' };
const ARCH_LOC_BAND = [['Entry · where requests start', 'Where requests start: HTTP routes, CLI commands, hooks and jobs.'],
  ['Client · runs in the browser', 'Code that runs in the browser: screens and client logic.'],
  ['Server · backend code', 'Backend code that handles requests and business logic.'],
  ['Stores · DB, files, queues', 'Where data is kept: databases, files and queues.']];
const ARCH_LOC_CODE = ['Code · project code', 'Project code between the entry points and the stores.'];
// Pure: band plan → {loc, key, n, of(m) band index (n = external band Lx), lbl(i), tip(i), solo(i)}. Style from d.style.style;
// layer mode keeps the 8 layer bands with the same titles (source bytes unchanged). solo(i) = the one group's name of a loc band ('' else).
// Loc bands: 0 entry (kind or layer entry) · 3 stores (kind store) · 1 client (layer ui, or a group with ui and no api/service/domain/data) · 2 the rest.
function archBandPlan(d, mods, tests){
  const st = d && d.style && typeof d.style === 'object' ? String(d.style.style || '') : '', N = ARCH_LAYERS.length;
  const ext = T('Libraries and outside services the code calls.', 'arch layer');
  // front = modules an entry serves (archFront); fk = their node keys for 81f. Layer mode lifts one below the api band into it.
  const f0 = (d && Array.isArray(d.flows) ? d.flows : []).map(f => f && Array.isArray(f.steps) && f.steps[0] ? f.steps[0].from : null);
  const front = archFront(mods, d && d.edges, tests, f0), fk = archFrontKeys(mods, front), API = ARCH_LAYERS.indexOf('api');
  if(ARCH_BAND_LOC.indexOf(st) < 0) return { loc: false, key: 'layer', n: N, front, fk,
    of: m => m.kind === 'external' ? N : front[m.id] && ARCH_LAYERS.indexOf(m.layer) > API ? API : ARCH_LAYERS.indexOf(m.layer),
    lbl: i => i >= N ? T('External') : T(ARCH_LAYER_LBL[ARCH_LAYERS[i]], 'arch layer'),
    tip: i => i >= N ? ext : T(ARCH_LAYER_TIP[ARCH_LAYERS[i]], 'arch layer'), solo: () => '' };
  const own = Object.prototype.hasOwnProperty, gl = Object.create(null), gn = Object.create(null), bg = [{}, {}, {}, {}];
  ((d && d.groups) || []).forEach(g => { if(g && g.id != null && !(String(g.id) in gn)) gn[String(g.id)] = String(g.name || g.id); });
  const vis = (mods || []).filter(m => m && m.id != null && m.kind !== 'external' && (tests || !archIsTest(m)));
  vis.forEach(m => { if(m.group != null){ const k = String(m.group); (gl[k] = gl[k] || {})[m.layer] = 1; } });
  const cli = k => { const s = k == null ? null : gl[String(k)]; return !!s && !!s.ui && !['api', 'service', 'domain', 'data'].some(l => own.call(s, l)); };
  const of = m => m.kind === 'external' ? 4 : m.kind === 'entry' || m.layer === 'entry' ? 0 : m.kind === 'store' ? 3 : m.layer === 'ui' || cli(m.group) ? 1 : 2;
  vis.forEach(m => { bg[of(m)]['\u0001' + (m.group == null ? '' : String(m.group))] = 1; });
  const has1 = Object.keys(bg[1]).length > 0, row = i => i === 2 && !has1 ? ARCH_LOC_CODE : ARCH_LOC_BAND[i];
  const solo = i => { const ks = i < 4 ? Object.keys(bg[i]) : []; if(ks.length !== 1 || ks[0] === '\u0001') return '';
    const k = ks[0].slice(1); return k in gn ? gn[k] : k; };
  return { loc: true, key: 'loc', n: 4, of, front, fk,
    lbl: i => i >= 4 ? T('External') : T(row(i)[0], 'arch layer'),
    tip: i => i >= 4 ? ext : T(row(i)[1], 'arch layer') + (solo(i) ? '\n' + T('Group: {g}', 'arch layer').replace('{g}', () => solo(i)) : ''), solo };
}
// Pure: front modules (id → 1): not entry/external, with a passed `serve` edge from a kind-entry module or a flow's first step
// (84k entry node) on them. ⚠Dependency direction is not request order: every controller calls a request filter, yet it runs first.
function archFront(mods, edges, tests, firsts){
  const kd = Object.create(null), out = Object.create(null);
  (mods || []).forEach(m => { if(m && m.id != null && (tests || !archIsTest(m))) kd[m.id] = m.kind; });
  const ok = id => id != null && id in kd && kd[id] !== 'entry' && kd[id] !== 'external';
  (edges || []).forEach(e => { if(e && e.ok && e.kind === 'serve' && e.from in kd && kd[e.from] === 'entry' && ok(e.to)) out[e.to] = 1; });
  (firsts || []).forEach(id => { if(ok(id)) out[id] = 1; });
  return out;
}
// Pure: front ids → node keys m<i> (last index wins, as archBandSrc).
function archFrontKeys(mods, front){
  const ix = Object.create(null), out = Object.create(null);
  (mods || []).forEach((m, i) => { if(m && m.id != null) ix[m.id] = i; });
  Object.keys(front).forEach(id => { if(id in ix) out['m' + ix[id]] = 1; });
  return out;
}
// Pure: module index → flow entry for the same way in: the entry's only first module i passes l0(i) (an L0 entry module) and no other
// entry starts there. ⚠Drawn apart, every route showed twice (hexagon -> box); 84j2 overview and 84j4 focus draw the pair as one hexagon.
function archEntPair(ents, l0){
  const hit = {}, out = {};
  (ents || []).forEach(e => Array.from(e.to).forEach(i => { hit[i] = (hit[i] || 0) + 1; }));
  (ents || []).forEach(e => { const t = Array.from(e.to); if(t.length === 1 && hit[t[0]] === 1 && l0(t[0])) out[t[0]] = e; });
  return out;
}
// Pure: banded mermaid source. Band L<i> (i = ARCH_LAYERS index) per non-empty layer, a G<n> box per (layer, group);
// externals in band Lx, one box per ext. Node id = 'm' + index in mods, edges as the archSrc overview.
// ⚠Group/ext names are agent data: archMq only, never T(). ⚠Bands stay TB: an LR block ranks along x, so unlinked groups stacked in one column.
// ents = 84k archFlowEntries: hexagon 'en<n>' nodes in band L0 (made when no entry module) with an edge to each first module;
// an entry paired with its L0 entry module draws no en node, the module m<i> takes the hexagon.
// With ents, L0 holds one row block Ek<k>r<r> (≤ 8 items) per entry kind; entry modules (kind entry) join the row of their ext.
// bp = archBandPlan (none = layer bands); a loc band with one group (bp.solo) draws no G box, its name goes to the band tip.
function archBandSrc(mods, edges, tests, full, groups, ents, bp){
  const ix = {}, gn = {}, ln = ['flowchart TB'], bands = {}, own = Object.prototype.hasOwnProperty;
  (mods || []).forEach((m, i) => { if(m && m.id != null) ix[m.id] = i; });
  (groups || []).forEach(g => { if(g && g.id != null && !own.call(gn, g.id)) gn[g.id] = g.name || g.id; });
  let ps = archPairs(mods, edges, tests);
  if(!full) ps = archReduce(ps);
  (mods || []).filter(m => m && m.id != null && (tests || !archIsTest(m))).forEach(m => {
    const ex = m.kind === 'external', b = ex ? 'Lx' : 'L' + (bp ? bp.of(m) : ARCH_LAYERS.indexOf(m.layer)), k = ex ? String(m.ext || '') : m.group == null ? '' : String(m.group);
    const B = bands[b] = bands[b] || { ks: [], by: {} };
    if(!own.call(B.by, '\u0001' + k)){ B.ks.push(k); B.by['\u0001' + k] = []; }
    B.by['\u0001' + k].push(m);
  });
  const en = ents && ents.length ? ents : null;
  if(en) bands.L0 = bands.L0 || { ks: [], by: {} };
  const nd = m => '      m' + ix[m.id] + (m.kind === 'external' ? '([' + archMq(m.name || m.id) + '])' : '[' + archMq(m.name || m.id) + ']');
  const l0 = {};
  if(en) bands.L0.ks.forEach(k => bands.L0.by['\u0001' + k].forEach(m => { if(m.kind === 'entry') l0[ix[m.id]] = 1; }));
  const pr = archEntPair(en, i => !!l0[i]), eu = en ? en.filter(e => pr[Array.from(e.to)[0]] !== e) : null;
  let n = 0;
  // L0 entry rows, one kind per row block in this order (index = <k> of Ek<k>r<r>); any other kind goes to row EK.length.
  const EK = ['http', 'hook', 'event', 'job', 'cli', 'mcp', 'file'], EKL = { http: 'HTTP', hook: 'Hook', event: 'Event', job: 'Job', cli: 'CLI', mcp: 'MCP', file: 'File' };
  const ek = k => { const i = EK.indexOf(String(k || '')); return i < 0 ? EK.length : i; };
  ARCH_LAYERS.slice(0, bp ? bp.n : ARCH_LAYERS.length).map((l, i) => 'L' + i).concat(['Lx']).forEach(b => {
    const B = bands[b];
    if(!B) return;
    const ex = b === 'Lx';
    ln.push('  subgraph ' + b + '[' + archMq(ex ? T('External') : bp ? bp.lbl(+b.slice(1)) : T(ARCH_LAYER_LBL[ARCH_LAYERS[+b.slice(1)]], 'arch layer')) + ']');
    // ⚠L0 with entries turns LR so the kind rows (TB) stack in one column; its groups set TB back. No entries: bytes unchanged.
    const wr = en && b === 'L0';
    if(wr){
      ln.push('    direction LR');
      const rows = EK.map(() => []).concat([[]]);
      eu.forEach(e => { const i = ek(e.kind), kd = i < EK.length ? '' : e.kind;   // label is agent data: archMq only; a known kind is named by its row
        const lb = Array.from(e.label), cut = lb.length > 24 ? lb.slice(0, 23).join('').trimEnd() + '…' : e.label;   // long labels widened the map (full label in the flow toolbar)
        rows[i].push('      ' + e.k + '{{' + archMq(kd && cut ? kd + ' · ' + cut : cut || kd || T(EKL[e.kind], 'arch flow kind')) + '}}'); });
      B.ks.forEach(k => { const ms = B.by['\u0001' + k];   // entry modules leave their group box for their kind row
        B.by['\u0001' + k] = ms.filter(m => { if(m.kind !== 'entry') return true; rows[ek(m.ext)].push(own.call(pr, ix[m.id]) ? '      m' + ix[m.id] + '{{' + archMq(m.name || m.id) + '}}' : nd(m)); return false; }); });
      B.ks = B.ks.filter(k => B.by['\u0001' + k].length);
      rows.forEach((r, i) => { for(let j = 0; j < r.length; j += 8){
        const t = j ? '' : i < EK.length ? T(EKL[EK[i]], 'arch flow kind') : T('Other', 'arch flow kind');
        ln.push('    subgraph Ek' + i + 'r' + (j / 8) + '[' + (t ? archMq(t) : '') + ']', '      direction TB');
        r.slice(j, j + 8).forEach(x => ln.push(x));
        ln.push('    end'); } });
    }
    const so = !ex && !!bp && !!bp.solo(+b.slice(1)) && B.ks.length === 1;
    B.ks.forEach(k => {
      const ms = B.by['\u0001' + k];
      if(!k || (!ex && so)){ ms.forEach(m => ln.push(nd(m).slice(2))); return; }   // no group or no ext: straight in the band (an External box inside the External band repeats it)
      ln.push('    subgraph G' + (n++) + '[' + archMq(ex ? k || T('External') : own.call(gn, k) ? gn[k] : k) + ']');
      if(wr) ln.push('      direction TB');
      ms.forEach(m => ln.push(nd(m)));
      ln.push('    end');
    });
    ln.push('  end');
  });
  ps.forEach(p => ln.push('  m' + ix[p.from] + ' ' + (p.est ? '-.->' : '-->') + (p.n > 1 ? '|' + archMq('×' + p.n) + '|' : '') + ' m' + ix[p.to]));
  if(eu) eu.forEach(e => e.to.forEach(i => ln.push('  ' + e.k + ' --> m' + i)));
  return ln.join('\n');
}
// Parsed banded graph → band ranks top to bottom (compacted, Lx last), bands pass-through for the router (81g), classes for CSS.
// ⚠Every root item needs a rank or 81f mmdFixed drops rankFix; root items here are bands only. bp (archBandPlan): band hover tips.
// hub = focused node key (84j4 focus): on the shared centre axis (81e g.axis) instead of its band's centre.
function archBandFix(g, bp, hub){
  const at = s => s === 'Lx' ? ARCH_LAYERS.length : +s.slice(1), fix = {};
  g.slist.forEach(s => { const S = g.sgs[s], row = /^Ek\d+r\d+$/.test(s);
    if(S.parent && !row){ S.cls = 'archgrp'; return; }
    S.pass = true; S.cls = row ? 'archerow' : 'archband';
    if(bp && !row){ const t = bp.tip(s === 'Lx' ? bp.n : +s.slice(1)); if(t) S.tip = t; }
    if(row) S.oneLayer = true; });   // Ek<k>r<r> entry rows: pass-through like a band, stacked in source (kind) order and centred by 81f
  g.slist.filter(s => !g.sgs[s].parent).sort((a, b) => at(a) - at(b)).forEach((s, i) => { fix[s] = i; });
  g.nlist.forEach(k => { if(!g.nodes[k].sg) fix[k] = 0; });
  g.rankFix = fix;
  g.axis = true;   // bands centred on one vertical axis (81e)
  if(hub && g.nodes[hub]) g.axisHub = hub;
  if(bp && bp.fk && g.nlist.some(k => bp.fk[k])) g.front = bp.fk;   // served modules take their block's first rows (81f mmdFront)
  g.hint0 = archBandHint(g, fix);
  return fix;
}
// Start order for every block (81e hint0): one flat crossing-reduced pass over all modules ranked by band; a group sits at
// its members' mean. ⚠Without it each band kept source order and only one barycentre pass reordered it.
function archBandHint(g, fix){
  const band = k => { let s = g.nodes[k].sg; while(s && g.sgs[s].parent) s = g.sgs[s].parent; return s; }, rk = {}, es = [], h = {}, acc = {};
  g.nlist.forEach(k => { rk[k] = fix[band(k)] || 0; });
  g.edges.forEach(e => { if(rk[e.from] != null && rk[e.to] != null && rk[e.from] !== rk[e.to]) es.push(rk[e.from] < rk[e.to] ? { a: e.from, b: e.to, w: 1 } : { a: e.to, b: e.from, w: 1 }); });
  const pl = mmdPlace(g.nlist, es, k => mmdBox(g.nodes[k].label, g.nodes[k].shape), 'TB', null, rk);
  g.nlist.forEach(k => { h[k] = pl.pos[k].x;
    for(let s = g.nodes[k].sg; s; s = g.sgs[s].parent){ (acc[s] = acc[s] || []).push(h[k]); } });
  Object.keys(acc).forEach(s => { h[s] = acc[s].reduce((a, b) => a + b, 0) / acc[s].length; });
  return h;
}
// Pure: drawn-edge kind per node-key pair ('m<i>\u0001m<j>' → call|read|write|event) for archMmd e.kind (81e data-k).
// Entry-node edges ('en<n>\u0001m<i>', ents = 84k archFlowEntries) → 'entry'. A call pair from a module into a front module → 'uses'.
// ⚠Front set = bp.front (archBandPlan), the one archBandFix places by: no bp, no 'uses'.
function archKindMap(mods, edges, tests, ents, bp){
  const ix = {}, out = {}, kd = {}, fr = (bp && bp.front) || {};
  (mods || []).forEach((m, i) => { if(m && m.id != null){ ix[m.id] = i; kd[m.id] = m.kind; } });
  archPairs(mods, edges, tests).forEach(p => { out['m' + ix[p.from] + '\u0001m' + ix[p.to]] = p.kind === 'call' && fr[p.to] && kd[p.from] !== 'entry' ? 'uses' : p.kind; });
  (ents || []).forEach(e => e.to.forEach(i => { out[e.k + '\u0001m' + i] = 'entry'; }));
  return out;
}
// Pure: Call · Read · Write · Event legend swatches; drawn with the diagram's .mmdfe[data-k] rules (79) so they match the lines.
function archKindLegHtml(uses){   // uses: the drawn diagram has a uses edge (84j archLegHtml)
  return Object.keys(ARCH_KIND_LBL).filter(k => uses || k !== 'uses').map(k => '<span><svg class=archsw width=20 height=12 viewBox="0 0 20 12" aria-hidden=true><g class=mmdfe data-k="' + k
    + '"><path class="mmde e-solid" d="M1 6H19"/></g></svg>' + esc(T(ARCH_KIND_LBL[k], 'arch edge')) + '</span>').join('');
}
