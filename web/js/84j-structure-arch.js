// ── Structure «Architecture» view: verified module map from GET /api/arch (80-structure.js paintStruct dispatches here) ──────
// The diagram is the server's `md` (passed edges only) drawn by 81e mmdBlock; the edge list beside it holds every edge + evidence.
// ⚠Evidence is file:line:symbol only (metadata); code opens on click through the existing popup (81 strPopOpenRel).
// ⚠The request button never sends by itself: preview → a person presses confirm → /api/dm relay (AGENTS.md rule 7).
const ARCH_PL = 'arch-map';
const ARCH = { cache: {}, load: {}, op: '', req: null, msg: '', sel: null, tests: false, full: false, svg: {}, sent: null, flow: null, pstop: null, breq: null, xm: '', scope: null, lit: null, nx: {}, ifx: null, et: {}, dvf: '', ly0: null, lyz: 1 };   // ly0 = {p, scope, lit} overview state when the focus layer opened · lyz = focus layer zoom   // dvf = project path while the deviation filter is on, '' off · et = «Connections» tree folds, key p\tn | p\tother, true = open (84j6) · ifx = {p, id} focus view with infrastructure unfolded (84j4) · scope = {p, layer, group} lit path level · lit = {p, flow, fs?} lit flow(s) · nx = folded neighbour branches (84j3)   // svg = archKey → rendered diagram; flow = {p, id} picked flow (84k)   // op = «path\tedge index» of the open evidence list; sel = {p, id} focused module
const ARCH_DIR = 'TB';   // ★live map, 17 modules · 46 pairs: TB 917x1146px, 85 crossings · LR 2870x328px, 88 crossings

// Fetch through fetch(), not getJSON: an allow-list refusal is a non-2xx whose JSON message must reach the screen.
// ⚠No ARCH.svg wipe on a new response: keys carry the commit, and a wipe re-laid every project out on each switch.
function archFetch(p, force){
  if(!p || ARCH.load[p] || (!force && ARCH.cache[p])) return;
  ARCH.load[p] = 1;
  fetch('/api/arch?path=' + encodeURIComponent(p), { cache: 'no-store' })
    .then(r => r.json().catch(() => null).then(j => j || { ok: false, msg: 'HTTP ' + r.status }))
    .catch(() => ({ ok: false, msg: 'Could not fetch — check the server' }))
    .then(j => { const o = ARCH.cache[p];   // an unchanged refresh keeps the old object: no repaint, cached diagram stays valid
      if(!(o && JSON.stringify(o) === JSON.stringify(j))) ARCH.cache[p] = j; delete ARCH.load[p]; archSentFin(p, ARCH.cache[p]); if(mainView === 'struct' && strMode === 'arch') paintStruct(); });
}
// Pure: {n passed, m total, pct}; server `rate` may be a 0..1 fraction or a percent.
function archRate(d){
  const es = (d && d.edges) || [], n = es.filter(e => e && e.ok).length, m = es.length, r = d && d.rate;
  const pct = typeof r === 'number' && isFinite(r) ? Math.round(r <= 1 ? r * 100 : r) : (m ? Math.round(100 * n / m) : 0);
  return { n, m, pct };
}
// Fixed style/role ids -> English labels (T() the label, never the id: ids are server data). Unknown -> 'Other' / raw text.
const ARCH_STYLE_LBL = { layered: 'Layered', modular: 'Modular', apps: 'Apps', routes: 'Routes', 'feature-pkgs': 'Feature packages',
  'feature-folders': 'Feature folders', crates: 'Crates', mvvm: 'MVVM', hexagonal: 'Hexagonal', library: 'Library', other: 'Other' };
const ARCH_ROLE_LBL = { web: 'Web', service: 'Service', data: 'Data', domain: 'Domain', port: 'Port', adapter: 'Adapter', app: 'App',
  view: 'View', viewmodel: 'ViewModel', model: 'Model', shared: 'Shared' };
function archStyleName(st){ const k = String((st && st.style) || ''); return T(Object.prototype.hasOwnProperty.call(ARCH_STYLE_LBL, k) ? ARCH_STYLE_LBL[k] : 'Other', 'arch style'); }
function archRoleName(r){ r = String(r || ''); return Object.prototype.hasOwnProperty.call(ARCH_ROLE_LBL, r) ? T(ARCH_ROLE_LBL[r], 'arch role') : r; }
// Pure: framework string -> parts split on « + » / «, »; one badge per part wraps onto the next line instead of an ellipsis.
function archFwParts(fw){ return String(fw || '').split(/\s+\+\s+|,\s+/).map(x => x.trim()).filter(Boolean); }
// Pure: style badges «Layered» (+ «estimated» when an evidence file is not in the commit) · framework · «Evidence N files»,
// then the deviation count; '' when the server sent no style. Evidence tooltip = files + units (strHdBadge escapes both).
function archStyleParts(d, on){   // {sty, est (sty is the warn-coloured «estimated» form), fw, ev, dev}; null without a style; on = deviation filter pressed
  const st = d && d.style && typeof d.style === 'object' ? d.style : null;
  if(!st || !st.style) return null;
  const fw = String(st.framework || ''), ev = (Array.isArray(st.evidence) ? st.evidence : []).filter(x => x && x.file);
  const tip = ev.map(x => x.file + (x.ok === false ? ' ✕' : '')).join('\n') + (st.units ? (ev.length ? '\n' : '') + T('Units: {u}').replace('{u}', String(st.units)) : '');
  const dv = Array.isArray(d.dev) ? d.dev.length : 0;
  // Separate badges: a long framework inside one combined badge got truncated along with the evidence count.
  return { est: st.ok === false, sty: strHdBadge(st.ok === false ? 'cut strbg-asty' : 'asty', archStyleName(st) + (st.ok === false ? ' · ' + T('estimated') : '')),
    fw: archFwParts(fw).map(x => strHdBadge('dat', x, fw)).join(''),
    ev: strHdBadge('', T('Evidence {n} files').replace('{n}', ev.length), tip),
    dev: dv ? '<button type=button class="strbg strbg-cy strbg-dvf" data-ardv aria-pressed=' + (on ? 'true' : 'false') + ' title="'
      + esc(T('Review hint, not an error: these edges go against the {s} flow. Keep an edge if it is intended; otherwise reverse the dependency. Click to list only these edges.').replace('{s}', archStyleName(st)))
      + '">' + esc(T('{n} outside {s} flow').replace('{n}', dv).replace('{s}', archStyleName(st))) + '</button>' : '' };
}
function archStyleNote(d){ const s = archStyleParts(d); return s ? s.sty + s.fw + s.ev + s.dev : ''; }
// Pure: header badges — pass rate, modules, and a document-style version stamp «Generated MM-DD HH:MM · commit» (server `at`).
// A stale map keeps the stamp in the «cut» style with a ⚠ marker; how far HEAD moved goes to its tooltip.
function archHeadNote(d, on){
  const r = archRate(d), c = String((d && d.commit) || '').slice(0, 7), h = String((d && d.head) || '').slice(0, 7);
  const at = d && typeof d.at === 'number' && isFinite(d.at) && d.at > 0 ? d.at : 0;
  const tip = T('Diagram commit {n} · HEAD now {m}').replace('{n}', c).replace('{m}', h);
  const ahead = d && d.stale ? (typeof d.behind === 'number' ? TV({msg: d.behind === 1 ? 'HEAD is {n} commit ahead' : 'HEAD is {n} commits ahead', vars: {n: d.behind}}) : T('stale')) + ' · ' : '';
  const why = d && d.stale ? '\n' + T('The diagram is older than the code — a new one is built from the latest commit.') : '';
  const s = archStyleParts(d, on) || { est: false, sty: '', fw: '', ev: '', dev: '' };
  const gen = c ? strHdBadge(d.stale ? 'cut' : '', (d.stale ? '⚠ ' : '') + (at ? T('Generated {t} · {c}').replace('{c}', c).replace('{t}', hhmm(at, { date: true, dsep: '-' })) : c), ahead + tip + why) : '';
  // Badges are ordered by colour group (purple · blue · grey · warning) so the row reads as groups; state-coloured ones follow their current colour.
  return (s.est ? '' : s.sty) + s.fw
    + strHdBadge('n', T('Edges verified {n}/{m} ({k}%)').replace('{n}', r.n).replace('{m}', r.m).replace('{k}', r.pct), T('Module connections whose evidence was checked in the code / all connections drawn'))
    + s.ev + strHdBadge('', T('{n} modules').replace('{n}', ((d && d.modules) || []).length)) + (d && d.stale ? '' : gen) + archProvNote(d && d.prov)
    + (s.est ? s.sty : '') + s.dev + (d && d.stale ? gen : '')
    + (typeof archChkHdBtn === 'function' ? archChkHdBtn(d) : '');   // 84l: issues badge (red/amber), or «Security check» when the project has no results yet (the overview link lives in 84m «Export HTML»)
}
// Pure: «drawn by» badge from server `prov` (platform logo + model; per-stage models when they differ).
// ⚠aiLogo falls back to the Claude mark for unknown codes — only call it when AILG has the code. Stage titles are stored data: esc, never T().
function archProvNote(p){
  const unk = () => strHdBadge('', T('Drawn by: unknown'));
  if(!p || typeof p !== 'object' || typeof AILG !== 'object' || !AILG[p.plat]) return unk();
  const st = (Array.isArray(p.stages) ? p.stages : []).filter(s => s && typeof s === 'object' && s.model);
  const per = st.map(s => String(s.t || '') + ': ' + String(s.model));
  const multi = new Set(st.map(s => String(s.model))).size > 1;
  // Badge lists only the distinct models in stage order; stage titles live in the tooltip. With titles inline the
  // ellipsis cut off the second model at 900-1100px, hiding the very fact that the run mixed models.
  const txt = multi ? [...new Set(st.map(s => String(s.model)))].join(' · ') : String(p.model || (st[0] && st[0].model) || T('unknown'));
  const tip = multi ? per.join('\n') : txt;
  return '<em class="strbg strbg-prov" title="' + esc(tip) + '">' + aiLogo(p.plat) + '<span>' + esc(txt) + '</span></em>';
}
// Pure: one-line legend under the toolbar. Swatches reuse the diagram's own classes (.mmde e-solid/e-dot, .mmdn s-stadium,
// svg.archdim .arin/.arout) inside .mmd, so they cannot drift from what the diagram draws.
function archLegHtml(v2, uses){   // v2: + Call · Read · Write · Event (84j2) · uses: + Uses, only when a uses edge is drawn
  const sw = (w, inner, cls) => '<svg class="archsw' + (cls ? ' ' + cls : '') + '" width=' + w + ' height=12 viewBox="0 0 ' + w + ' 12" aria-hidden=true>' + inner + '</svg>';
  const ln = c => '<path class="mmde ' + c + '" d="M1 6H19"/>', it = (s, t) => '<span>' + s + esc(T(t)) + '</span>';
  return '<div class="archleg mmd" aria-label="' + esc(T('Legend')) + '">'
    + it(sw(20, ln('e-solid')), 'Direct reference') + it(sw(20, ln('e-dot')), 'Estimated')
    + it(sw(22, '<g class="mmdn s-stadium"><rect x=1 y=1 width=20 height=10 rx=5 ry=5 /></g>'), 'External')
    + it('<b class=archlgx>×N</b>', 'N edges merged') + (v2 ? archKindLegHtml(uses) : '')
    + '<span class=archlgg><span class=archlgh>' + esc(T('Hover:')) + '</span>'   // one nowrap group: the label never wraps away from its items
    + it(sw(20, '<g class="mmdfe arn arin">' + ln('e-solid') + '</g>', 'archdim'), 'incoming')
    + it(sw(20, '<g class="mmdfe arn arout">' + ln('e-solid') + '</g>', 'archdim'), 'calls, 2 steps down')
    + it(sw(22, '<g class=mmdn><rect x=1 y=1 width=20 height=10 rx=2 ry=2 /></g>', 'archdim'), 'unrelated, dimmed') + '</span></div>';
}
// Pure: evidence list of one edge; every field escaped, file/line carried as data-* for the popup.
function archEvHtml(ev, i){
  const xs = (ev || []).filter(x => x && x.file);
  if(!xs.length) return '<div class=archevn>' + esc(T('No evidence')) + '</div>';
  return '<ol class=archev>' + xs.map(x => '<li><button type=button data-aev="' + esc(i) + '" data-af="' + esc(x.file) + '" data-al="' + esc(parseInt(x.line, 10) || 1)
    + '" data-as="' + esc(x.symbol || '') + '" title="' + esc(x.file + ':' + (parseInt(x.line, 10) || 1) + ' · ' + T('View code')) + '"><span class=archevf>' + esc(x.file) + '</span><span class=archevl>:' + esc(parseInt(x.line, 10) || 1)
    + '</span>' + (x.symbol ? '<code>' + esc(x.symbol) + '</code>' : '') + '</button></li>').join('') + '</ol>';
}
// Pure: one edge row (+ its evidence when open). names = module id → display name; io = 'in'|'out' in the focus view.
// dv = {a, b} from-/to-role when the gate flagged this edge outside style sn (display name); none otherwise.
function archEdgeRow(e, names, i, open, io, dv, sn){
  const nm = id => names[id] || String(id || '');
  return '<li class="arche' + (open ? ' on' : '') + (e.ok ? '' : ' bad') + (io ? ' ' + io : '') + '"><button type=button class=archeb data-ae="' + i + '" aria-expanded=' + (open ? 'true' : 'false') + '>'
    + '<span class=archen>' + (io ? '<em class=archio>' + esc(T(io === 'in' ? 'In' : 'Out')) + '</em>' : '') + '<b>' + esc(nm(e.from)) + '</b><i>→</i><b>' + esc(nm(e.to)) + '</b></span>'
    + '<span class=archem>' + (e.kind ? '<em class=archk>' + esc(e.kind) + '</em>' : '')
    + (e.est ? '<em class="archbg archest" title="' + esc(T('Evidence is inferred, not a direct reference')) + '">' + esc(T('estimate')) + '</em>' : '')
    + (dv ? '<em class="archbg archdev">' + esc(T('{a} → {b} is outside the {s} flow').replace('{a}', archRoleName(dv.a)).replace('{b}', archRoleName(dv.b)).replace('{s}', sn || '')) + '</em>' : '')
    + (e.ok ? '' : '<em class="archbg archbad">' + esc(T('Check failed')) + '</em>')
    + '<small>' + esc(T('{n} refs').replace('{n}', ((e.evidence || []).length))) + '</small></span>'
    + (e.label ? '<span class=archel>' + esc(e.label) + '</span>' : '') + '</button>'
    + (open ? archEvHtml(e.evidence, i) : '') + '</li>';
}
// Pure: deviation filter list — one row per flagged edge index, ascending. ⚠Bypasses the flow tree: flow steps never show the reason badge.
function archDevListHtml(edges, names, p, devAt, sn, op){
  const ix = Object.keys(devAt || {}).map(Number).filter(i => i >= 0 && edges && edges[i]).sort((a, b) => a - b);
  return '<div class=archdvn role=status>' + esc(T('Not an error · {n} edges to review').replace('{n}', ix.length)) + '</div><ul class="archel-list archdvl">'
    + ix.map(i => archEdgeRow(edges[i], names, i, op === p + '\t' + i, '', devAt[i], sn)).join('') + '</ul>';
}
// Diagram through the 81e renderer in tag mode: nodes carry data-p (click target), edges data-c = in|out (focus colours).
// Falls back to plain mmdBlock when anything throws. sel = module index of the focused node ('' in the overview).
function archMmd(src, mods, sel, kinds, fit, bp){   // kinds = 84j2 archKindMap on a layered v2 map, else none (v1 bytes unchanged) · fit = archFitOf room, focus only · bp = 84j2 archBandPlan
  let svg = '';
  try{
    const g = mmdParse(src);
    if(g.ok){
      const me = sel === '' ? '' : 'm' + sel;
      g.nlist.forEach(k => { const m = mods[+k.slice(1)]; if(m) g.nodes[k].tip = (m.name || m.id) + (m.path ? ' · ' + m.path : '')
        + (k === me && m.path ? ' — ' + T('Click again to open the code') : ''); });   // archDgClick: focused + path opens the tree
      if(kinds) g.edges.forEach(e => { const x = kinds[e.from + '\u0001' + e.to]; if(x) e.kind = x; });
      const band = !!kinds && (!me || g.slist.some(s => !g.sgs[s].parent && /^L[\dx]/.test(s)));   // v2 focus keeps the bands (84j4)
      if(me && fit && !band) g.fit = fit;   // spread to the visible map box (81f mmdPlace room); the overview keeps its natural size
      if(me && band) g.edges.forEach(e => { e.calls = e.from === me ? ['out'] : e.to === me ? ['in'] : []; });
      else if(me){ g.edges.forEach(e => { e.calls = [e.from === me ? 'out' : 'in']; });
        g.flHead = me; }   // ⚠out-edges all start at the hub: 81e mmdFlPlace anchors their labels at the head end instead
      if(band) archBandFix(g, bp, me);   // R1: bands ranked by layer, not by call depth · focus: hub on the centre axis
      else if(!me){ const top = k => g.nodes[k] && g.nodes[k].sg ? g.nodes[k].sg : k;   // overview: entries on top (root block ids)
        g.rankFix = archRanks(g.nlist.filter(k => !g.nodes[k].sg).concat(g.slist), g.edges.map(e => ({ from: top(e.from), to: top(e.to) }))); }
      g.flLabels = true;   // mmdSvg tag mode places its own labels (81e mmdFlPlace): skip mmdLabels
      const lab = band && me && typeof archFocusStrip === 'function' ? archFocusStrip(g) : null;   // v2 focus: labels hover-only, off the layout (84j4)
      const L = mmdLayout(g);
      svg = mmdSvg(g, L, 'arch' + (me || 'all'), true);
      if(lab) svg = svg.replace(/<\/svg>$/, archFocusPills(g, L, lab) + '</svg>');
      if(me) svg = svg.split(' data-p="' + me + '">').join(' data-p="' + me + '" data-on=1>');
    }
  }catch(e){ svg = ''; if(typeof softErr === 'function') softErr('arch', e); }
  if(!svg) return mmdBlock(src);
  return '<div class=mmd><div class=mmdbar>' + (typeof archZmBar === 'function' ? archZmBar() : '') + '<button type=button class=mmdtg aria-pressed=false>' + esc(T('Source text')) + '</button></div>'
    + '<div class=mmdv>' + svg + '</div><div class=mmdsrc>' + codeBlock(src, 'mermaid') + '</div></div>';
}
// Drawing room of the visible .archmap box for the focus view, 20px buckets (cache key) · null before the first paint.
// ⚠offset sizes, not client: a scrollbar must not change the room, or a refit could toggle it back and forth
function archFitOf(box){
  const am = box && box.querySelector && box.querySelector('.archmap'), top = am && am.querySelector && am.querySelector('.archtop');
  if(!am || !top || !am.offsetWidth) return null;
  const bar = am.querySelector('.archdg .mmdbar'), q = v => Math.floor(v / 20) * 20;
  const w = q(am.offsetWidth - 52), h = q(am.offsetHeight - top.offsetHeight - (bar ? bar.offsetHeight : 26) - 60);   // borders · paddings · RP margins
  return w >= 200 && h >= 100 ? { w, h } : null;
}
// Pure: toolbar above the diagram — overview hint or «All» + focused name + in/out legend; the test toggle when there is one.
// pick = flow picker html (84k archFlowPick), '' when the map has no flows.
function archBarHtml(mods, edges, sel, tests, full, pick, ifx){   // ifx = infrastructure unfolded (84j4)
  const hasT = (mods || []).some(archIsTest), m = sel ? (mods || []).find(x => x && x.id === sel) : null;
  const tg = hasT ? '<label class=archtg><input type=checkbox data-art' + (tests ? ' checked' : '') + '> ' + esc(T('Include tests')) + '</label>' : '';
  if(!m){ const ps = archPairs(mods, edges, tests), cut = ps.length - archReduce(ps).length;
    const ft = cut ? '<label class=archtg><input type=checkbox data-arfull' + (full ? ' checked' : '') + '> ' + esc(T('All edges')) + '</label>' : '';
    const hint = cut && !full ? T('{n} indirect edges hidden — click a module for all').replace('{n}', cut) : T('Click a module to see only its edges');
    return '<div class=archbar>' + (pick || '') + '<span class=archhint title="' + esc(hint) + '">' + esc(hint) + '</span>' + ft + tg + '</div>'; }
  const ps = archPairs(mods, edges, tests), ni = ps.filter(p => p.to === sel).length, no = ps.filter(p => p.from === sel).length;
  return '<div class="archbar on">' + (pick || '') + '<b class=archsel>' + esc(m.name || m.id) + '</b>'   // focus layer bar: the layer header's × closes it (no back button)
    + '<span class=archlgp><span class="archlg in">' + esc(T('In') + ' ' + ni) + '</span><span class="archlg out">' + esc(T('Out') + ' ' + no) + '</span>'   // one group: a narrow bar wraps In/Out + fold together
    + (ifx ? '<button type=button class=archfbt data-arifx>' + esc(T('Fold infrastructure')) + '</button>' : '') + '</span>' + tg + '</div>';
}
// Pure: rendered-diagram cache key. Layout is deterministic for the same map + view, so re-opens and evidence clicks reuse it.
// ents (84k archFlowEntries) add their signature, so a flows change never reuses a drawing without its entry nodes.
function archKey(d, sel, tests, full, ents, fx){   // fx = focus view state (84j4: ifx open flag + lit flow ids)
  return (fx ? fx + '\t' : '') + [(d && d.commit) || '', sel ? 'focus' : 'all', sel || '', tests ? 1 : 0, full ? 1 : 0, LANG, ((d && d.modules) || []).length, ((d && d.edges) || []).length].join('\t')
    + (typeof archBandPlan === 'function' && archBandPlan(d).loc ? '\tloc' : '')   // band mode (84j2); layer mode keeps the old key
    + (ents && ents.length ? '\t' + ents.map(e => e.kind + '|' + e.label + '|' + Array.from(e.to).join(',')).join(';') : '');
}
// Pure: hover focus set. edges = [{f, t}] node keys; h = {node: k} | {edge: {f, t}} → lit nodes n, edge keys (f\u0001t) in/out of the node.
// A node hover lights downstream drawn edges up to `depth` hops (2) as out, incoming edges direct only.
// ⚠Unbounded downstream lit nearly the whole map from any top module, so the highlight said nothing.
// An edge hover lights the edge (as out) and both ends.
function archHov(edges, h, depth = 2){
  const n = new Set(), i = new Set(), o = new Set(), ek = e => e.f + '\u0001' + e.t;
  if(h && h.node != null){
    n.add(h.node);
    const E = edges || [], seen = new Set([h.node]);
    E.forEach(e => { if(e.t === h.node){ i.add(ek(e)); n.add(e.f); } });
    for(let d = 0, q = [h.node]; d < depth && q.length; d++){ const nx = [];
      q.forEach(u => E.forEach(e => { if(e.f !== u) return; o.add(ek(e)); n.add(e.t); if(!seen.has(e.t)){ seen.add(e.t); nx.push(e.t); } }));
      q = nx; }
  } else if(h && h.edge){ n.add(h.edge.f); n.add(h.edge.t); o.add(ek(h.edge)); }
  return { n, in: i, out: o };
}
// Class-only repaint of the cached SVG (no rebuild, no scroll): .archdim on svg, .arn/.arin/.arout on nodes and edge groups.
function archHovPaint(svg, h){
  const ns = svg.querySelectorAll('[data-p]'), es = svg.querySelectorAll('.mmdfe');
  const S = h ? archHov(Array.from(es, g => ({ f: g.dataset.f, t: g.dataset.t })), h) : null, ni = new Set(), no = new Set();
  if(S){ S.in.forEach(k => ni.add(k.split('\u0001')[0])); if(h.node != null) S.out.forEach(k => no.add(k.split('\u0001')[1])); }
  svg.classList.toggle('archdim', !!S);
  const he = h && h.edge ? h.edge.f + '\u0001' + h.edge.t : '';   // arhe = the one hovered edge: only its label shows (79, focus view)
  es.forEach(g => { const k = g.dataset.f + '\u0001' + g.dataset.t, a = !!S && S.in.has(k), b = !!S && S.out.has(k);
    g.classList.toggle('arn', a || b); g.classList.toggle('arin', a); g.classList.toggle('arout', b); g.classList.toggle('arhe', k === he); });
  ns.forEach(g => { const k = g.dataset.p; g.classList.toggle('arn', !!S && S.n.has(k)); g.classList.toggle('arh', !!S && h.node === k);
    g.classList.toggle('arin', ni.has(k)); g.classList.toggle('arout', no.has(k)); });
}
function archWaitHtml(){ return '<div class="strload archwait" role=status><i class=archspin></i><b>' + esc(T('Loading the architecture diagram…')) + '</b></div>'; }
// ★Live map: /api/arch 15–38ms, overview layout 77–100ms (node) — layout dominates, so a cache miss paints the
// loading line first and lays out after a frame; ⚠the slot is matched by key so a stale timer never fills a newer view.
function archDiagram(box, k, src, mods, si, kinds, fit, bp){
  if(ARCH.svg[k]){ box._arpend = null; return ARCH.svg[k]; }
  const fill = () => {
    const slot = box.querySelector && box.querySelector('.archdg');
    if(fit && !(slot && slot.dataset && slot.dataset.k === k)) return;   // a refit already replaced this view: no stale layout
    if(!ARCH.svg[k]){ const ks = Object.keys(ARCH.svg); if(ks.length >= 40) ARCH.svg = {}; ARCH.svg[k] = archMmd(src, mods, si, kinds, fit, bp); }
    if(slot && slot.dataset && slot.dataset.k === k){ slot.innerHTML = ARCH.svg[k]; if(typeof archZmApply === 'function') archZmApply(slot);   // ⚠cached svg is 1x: re-zoom before the scroll goes back (84j8)
      const pd = box._arpend; box._arpend = null;   // ⚠the paint put the scroll back onto the short loading line, which clamped it to 0
      if(pd) archScrollPut(box, pd[0], pd[1], pd[2]);
      if(typeof archLitNow === 'function') archLitNow(slot); }
  };
  if(typeof requestAnimationFrame === 'function') requestAnimationFrame(() => setTimeout(fill, 0)); else setTimeout(fill, 0);
  box._arpend = box._arsm;   // scroll to restore in fill; a paint before then reads this instead of the clamped DOM
  return archWaitHtml();
}
function archPaint(box, head){
  const p = strOn[0] || '';
  if(!p){ box.innerHTML = '<div class="strtab archtab">' + head('') + '<div class=strload>' + esc(T('Pick a project.')) + '</div></div>'; return; }
  archFetch(p, false);
  const d = ARCH.cache[p], home = archHome(d), cands = archCands(home, SESS, p);
  archSentFin(p, d);
  if(ARCH.req && ARCH.req.p !== p) ARCH.req = null; if(typeof archXFix === 'function') archXFix(p, cands);   // 84m: export menu / brief preview follow the shown project
  const run = archRunOf(p);
  if(run && !ARCH.rsig) ARCH.rsig = [p, run.stage, run.n, run.sid].join('\t');   // first paint: a run ending before archTick's first look still refetches
  if(run) ARCH.req = null;   // ⚠one run per project: a live run closes the preview so no second request goes out
  if(ARCH.req && !cands.some(c => c.sid === ARCH.req.sid) && cands.length) ARCH.req.sid = cands[0].sid;
  // Poll repaints on every session change: same response + same view state keeps the drawing (no flicker, select keeps focus).
  const sig = [p, LANG, ARCH.op, JSON.stringify(ARCH.req), typeof archXSig === 'function' ? archXSig(p) : '', ARCH.msg, archSentPh(p), run ? [run.stage, run.n, run.sid].join('/') : '', JSON.stringify(ARCH.sel), JSON.stringify(ARCH.flow || null), JSON.stringify([ARCH.scope, ARCH.lit, ARCH.nx, ARCH.ifx, ARCH.et, ARCH.dvf]), ARCH.tests, ARCH.full, typeof archReqSig === 'function' ? archReqSig(p) : '', cands.map(c => c.sid + (c.login ? '+' : '')).join(',')].join('\t');
  if(d && box._arj === d && box._arsig === sig && box.querySelector('.archtab')) return;
  box._arj = d; box._arsig = sig;
  const msg = ARCH.msg ? '<div class=archmsg role=status>' + esc(ARCH.msg) + '</div>' : '';
  if(!d){ box.innerHTML = '<div class="strtab archtab">' + head(esc(T('Loading…'))) + '' + archWaitHtml() + '</div>'; return; }
  const req = archReqHtml(ARCH.req, p, home, cands, ARCH.req && ARCH.req.busy, d);
  const pre = archReqBtn(p, home, cands, d) + (typeof archXBtn === 'function' ? archXBtn(d, p) : ''), pre0 = pre + (typeof archChkEntry === 'function' ? archChkEntry(d) : '');   // no-map states: security check entry too (84l)
  if(!d.ok){   // allow-list refusal and other server errors: the server's own words
    box.innerHTML = '<div class="strtab archtab">' + head('', '', d.empty ? pre0 : '') + '<div class="tlhd cwerr">' + esc(d.msg ? TV(d) : T(String(d.error || '?'))) + '</div>'
      + (d.empty ? '<div class=archempty>' + archStatusHtml(p, req) + '</div>' : '') + msg + '</div>';
    return;
  }
  const mods = d.modules || [], edges = d.edges || [], names = {};
  mods.forEach(m => { if(m && m.id != null) names[m.id] = m.name || m.id; });
  if(d.bad){   // map on disk failed schema validation: say so instead of «No architecture diagram yet»
    box.innerHTML = '<div class="strtab archtab">' + head('', '', pre0) + '<div class="tlhd cwerr">' + esc(T('The stored diagram is invalid — request a new one')) + '</div>'
      + '<div class=archempty>' + archStatusHtml(p, req) + '</div>' + msg + '</div>';
    return;
  }
  if(!mods.length || d.empty){   // `empty` may come on ok:true too
    box.innerHTML = '<div class="strtab archtab">' + head('', '', pre0) + '<div class=archempty><b>' + esc(T('No architecture diagram yet')) + '</b><p>'
      + esc(T('The arch-map pipeline reads the code, draws modules and edges, then checks each edge against its evidence (file:line). It never writes to the repository.')) + '</p>' + archStatusHtml(p, req) + '</div>' + msg + '</div>';
    return;
  }
  // Stale map / live run: inline status in the header, not a full-width band; staleness itself is the ⚠ «Generated» badge
  // (a separate chip widened the controls and wrapped the header badges onto many lines at 900-1440px).
  const prow = typeof archReqLast === 'function' ? archReqLast(p, ARCH_PL) : null;   // request record (84l2): a live one takes the header line's place
  const hst = (prow && archReqLive(prow) ? '' : run ? archRunHtml(run) : d.stale ? archSentHtml(p) : '');
  const rq0 = req || (!d.stale && !run ? archSentHtml(p) : ''), rq = (prow ? archReqSlot(p, ARCH_PL, rq0, req) : rq0) + (typeof archBriefSlot === 'function' ? archBriefSlot(p, home, cands) : '');   // map preview / sent line under the header · 84m arch-brief preview / row
  // Selection survives poll repaints; a module gone from a rebuilt map falls back to the overview.
  const si = ARCH.sel && ARCH.sel.p === p ? mods.findIndex(m => m && m.id === ARCH.sel.id) : -1, sel = si >= 0 ? mods[si].id : '';
  const tests = ARCH.tests || (si >= 0 && archIsTest(mods[si]));   // a focused test module shows its own edges
  const io = e => !sel ? '' : e.from === sel ? 'out' : e.to === sel ? 'in' : null;
  const ord = edges.map((e, i) => ({ e, i, io: io(e) })).filter(o => o.io !== null)
    .sort((a, b) => (b.e.ok ? 1 : 0) - (a.e.ok ? 1 : 0));   // passed first, failed last
  const same = box._arp === p; box._arp = p;   // ⚠keep scroll only within one project: another project opens at 0,0
  const keep = n => { const x = same && box.querySelector && box.querySelector(n); return x ? [x.scrollTop, x.scrollLeft] : null; };
  const lyk = sel ? p + '\t' + sel : '', lyNew = box._arly !== lyk; box._arly = lyk;   // a new focus id opens the layer at 0,0 (no centring)
  // ⚠a paint while the diagram is still loading (a lit flow's off-screen count resizes the bar, so the next poll repaints):
  //   the DOM scroll was clamped to 0 under the loading line, use the saved one
  const hold = same && box._arpend && box._arpend[0] ? box._arpend : null;
  let sm = hold ? hold[0] : keep('.archmap'); const sl = hold ? hold[1] : keep('.archel-list'), sd = hold ? hold[2] : keep('.archdet'), slm = sel && !lyNew ? keep('.archlym') : null;   // ⚠innerHTML resets scroll: clicks must not move the view
  box._arsm = [sm, sl, sd];   // a cache miss draws after a frame (archDiagram fill): it restores this once the diagram is in
  const devAt = {}, devSn = d.style && d.style.style ? archStyleName(d.style) : '';   // edge index -> deviation (server validated i)
  if(devSn) (Array.isArray(d.dev) ? d.dev : []).forEach(x => { if(x && typeof x.i === 'number') devAt[x.i] = x; });
  // ⚠Overview is always painted as with no module focused (own tests/ents/bp/key): the focus opens as a layer above it, so the
  //   map behind keeps its exact drawing, zoom and scroll and comes back unchanged when the layer closes.
  const tests0 = ARCH.tests || false, lay0 = archHasLayers(d, tests0);   // ⚠v1: archSrc/archRanks path unchanged (R4)
  const ents0 = lay0 && Array.isArray(d.flows) && d.flows.length && typeof archFlowEntries === 'function' ? archFlowEntries(d, mods, tests0) : null;   // entry nodes (84k)
  const bp0 = lay0 && typeof archBandPlan === 'function' ? archBandPlan(d, mods, tests0) : null;   // band mode from the map style (84j2)
  const kinds0 = lay0 ? archKindMap(mods, edges, tests0, ents0, bp0) : null;
  const src0 = lay0 ? archBandSrc(mods, edges, tests0, ARCH.full, d.groups, ents0, bp0) : archSrc(mods, edges, tests0, '', ARCH.full), any = edges.some(e => e && e.ok), k = archKey(d, '', tests0, ARCH.full, ents0, '');
  // ⚠no .archmap in the DOM (back from another main tab / «Size» / a flow) or a view-key change: put back that view's last scroll (84j7)
  //   instead of the carried one; before archDiagram reads box._arsm. No saved entry = carried scroll (archMmFirst rules apply).
  // ⚠Also after a project switch (no carried scroll): a map seen earlier is never re-anchored by archMmFirst, so without its saved entry it opened at 0,0.
  if(!hold && typeof archMmPick === 'function'){ const od = same && box.querySelector && box.querySelector('.archdg');
    const pv = archMmPick(sm, od && od.dataset ? od.dataset.k : null, k); if(pv !== sm){ sm = pv; box._arsm = [sm, sl, sd]; } }
  const fa = Array.isArray(d.flows) && d.flows.length ? archFlowAt(d, p) : null, fl = fa && fa.fi >= 0 ? fa.fls[fa.fi] : null;   // ⚠no flows: no 84k call, same page as before
  // ⚠A module/flow pick or a rebuilt map without deviations turns the filter off, so the badge never stays pressed over another aside.
  const dvOn = ARCH.dvf === p && !!devSn && Object.keys(devAt).length > 0 && !sel && !fl;
  if(ARCH.dvf === p && !dvOn) ARCH.dvf = '';
  // Flow view has no header buttons: a stale map puts its request button in the controls; an open preview sits under the header.
  const fhd = d.stale ? archStatusHtml(p, archReqBtn(p, home, cands, d)) : hst;
  if(fl){ box.innerHTML = '<div class="strtab archtab">' + head(archHeadNote(d, dvOn), '', fhd) + (d.stale && req ? '<div class=archck>' + req + '</div>' : '') + msg + archFlowBody(fa.fls, fa.fi, names) + '</div>';
    archScrollPut(box, sm, sl); archFlowMark(box.querySelector && box.querySelector('.archfdg svg'), fl); return; }
  const pick = fa ? archFlowPick(fa.fls, ARCH.lit && ARCH.lit.p === p ? ARCH.lit.flow : '') : '';
  const ly = sel && typeof archLyHtml === 'function' ? archLyHtml(d, mods, edges, sel, si, tests, pick, any) : '';   // 84j3
  box.innerHTML = '<div class="strtab archtab">' + head(archHeadNote(d, dvOn), '', hst + pre) + (rq ? '<div class=archck>' + rq + '</div>' : '') + msg
    + '<div class=archbody' + strSplitStyle('archbody') + '><div class=archmap' + (ly ? ' inert' : '') + '><div class=archtop>' + (typeof archPathHtml === 'function' ? archPathHtml(mods, d.groups, '', ARCH.scope && ARCH.scope.p === p ? ARCH.scope : null) : '') + archBarHtml(mods, edges, '', tests0, ARCH.full, pick, false)
    + (lay0 ? '' : '<div class="archmsg archnol" role=status>' + esc(T('No layers — redraw the diagram')) + '</div>')
    + (any ? archLegHtml(lay0, !!kinds0 && Object.keys(kinds0).some(x => kinds0[x] === 'uses')) : '') + '</div>' + (any ? '<div class=archdg data-k="' + esc(k) + '">' + archDiagram(box, k, src0, mods, '', kinds0, null, bp0) + '</div>' : '<div class=strload>' + esc(T('No edge passed the check.')) + '</div>') + '</div>'
    + (any && lay0 && typeof archMmHtml === 'function' ? archMmHtml(archMmOn()) : '')   // minimap overlay (84j7), outside .archmap
    + ly   // focus layer (79e): above the map and minimap, below the ≤1060px detail popover
    + (sel && typeof archDetHtml === 'function' ? archDetHtml(d, sel, names, ARCH.nx, { op: i => ARCH.op === p + '\t' + i, dv: i => devAt[i], sn: devSn, drawn: archDrawn(mods, edges, tests, sel, ARCH.full), lit: ARCH.lit && ARCH.lit.p === p ? ARCH.lit.flow : null })   // module detail (84j3)
      : '<aside class=archside><div class=archsh><b>' + esc(T('Edges')) + '</b><span>' + esc(T('Click for evidence · click evidence for code')) + '</span>'
    + '<button type=button class=archrf data-arf title="' + esc(T('Reload now')) + '">↻</button></div>'
    + (dvOn ? archDevListHtml(edges, names, p, devAt, devSn, ARCH.op)
      : typeof archEdTreeHtml === 'function' ? archEdTreeHtml(d, names, p, { op: ARCH.op, et: ARCH.et, dv: devAt, sn: devSn, lit: ARCH.lit && ARCH.lit.p === p ? ARCH.lit.flow : null })   // flow tree (84j6)
      : '<ul class=archel-list>' + ord.map(o => archEdgeRow(o.e, names, o.i, ARCH.op === p + '\t' + o.i, o.io, devAt[o.i], devSn)).join('') + '</ul>') + '</aside>') + strSplitGrip('archbody') + '</div></div>';
  if(typeof archZmApply === 'function') archZmApply(box.querySelector && box.querySelector('.archdg'));   // ⚠zoom first: a 1x svg clamps the restored scroll (84j8)
  const fs = ly && box.querySelector ? box.querySelector('.archly .archdg') : null;
  if(fs && typeof archLyZoomPut === 'function') archLyZoomPut(fs);   // layer zoom + route (s2 archFhRoute) before its scroll goes back
  archScrollPut(box, sm, sl, sd, slm);
  if(ly && typeof archLyFocus === 'function') archLyFocus(box);   // 84j3: modal layer takes focus only when the repaint dropped it
  if(typeof archLitNow === 'function') archLitNow(box.querySelector && box.querySelector('.archdg'));   // cached svg: lit classes go back on (the layer too)
}
// Restore the map/list/layer scroll saved before an innerHTML repaint (the first .archmap is the overview).
function archScrollPut(box, sm, sl, sd, slm){
  const put = (n, v) => { const x = v && box.querySelector && box.querySelector(n); if(x){ x.scrollTop = v[0]; x.scrollLeft = v[1]; } };
  put('.archmap', sm); put('.archel-list', sl); put('.archdet', sd); put('.archlym', slm);
}
// Diagram click (true = handled). Module: focus one level; the focused one again opens its folder in the code tree (no path: no-op).
// Edge line/label: toggle the evidence of its first passed edge (only ok edges are drawn, archPairs; a ×N pair opens the first).
// ⚠No centring: a new focus keeps the clicked node at its screen position (84j7 archMmAt / archMmFirst).
function archDgClick(p, t){
  const d = ARCH.cache[p] || {}, mods = d.modules || [], at = s => mods[parseInt(String(s || '').slice(1), 10)];
  let b;
  if((b = t.closest('.archdg [data-p]'))){ const m = /^m\d+$/.test(String(b.dataset.p || '')) ? at(b.dataset.p) : null;
    if(!m){ if(typeof archFocusClick === 'function') archFocusClick(p, d, String(b.dataset.p || '')); return true; }   // ifx chip / entry node (focus view only)
    if(typeof archFocusHx === 'function' && b.closest('.archdg[data-fv]') && archFocusHx(b.dataset.p)){ archFocusClick(p, d, b.dataset.p); return true; }   // paired entry hexagon: lights its flows
    if(ARCH.sel && ARCH.sel.p === p && ARCH.sel.id === m.id){ if(m.path) strPopOpenTree(p, String(m.path)); }
    else { if(typeof archMmAt === 'function') archMmAt(b); if(!(ARCH.sel && ARCH.sel.p === p)) ARCH.ly0 = { p, scope: ARCH.scope, lit: ARCH.lit };   // opened from the overview: what × / Esc restore
      ARCH.sel = { p, id: m.id }; ARCH.op = ''; paintStruct(); }   // a module inside the layer only changes the layer
    return true; }
  if((b = t.closest('.archdg .mmdfe'))){ const f = at(b.dataset.f), to = at(b.dataset.t);
    const i = f && to ? (d.edges || []).findIndex(e => e && e.ok && e.from === f.id && e.to === to.id) : -1;
    if(i >= 0){ const k = p + '\t' + i; ARCH.op = ARCH.op === k ? '' : k; paintStruct(); }
    return true; }
  return false;
}
// Mode button uses data-ma (not data-md) so 81's «Size» wiring leaves it alone.
document.addEventListener('click', ev => {
  const t = ev.target && ev.target.closest ? ev.target : null;
  if(!t) return;
  if(t.closest('#strmd button[data-ma]')){
    if(strMode === 'arch') return;
    const hadF = document.activeElement === t.closest('#strmd button[data-ma]');   // ⚠the repaint drops focus to <body>
    strStop(); strMode = 'arch'; tabSet('sidereus.strmd', 'arch'); paintStruct();
    if(hadF) kbHold('#strmd button[data-ma]');
    return;
  }
  if(!t.closest('.archtab') || strMode !== 'arch') return;
  const p = strOn[0] || '';
  let b;
  if((b = t.closest('[data-aev]'))){ strPopOpenRel(p, b.dataset.af, parseInt(b.dataset.al, 10) || 1, 80, b.dataset.as || ''); return; }
  // ⚠.archdg only: flow lifelines (84k .archfdg) carry data-p too
  if(archDgClick(p, t)) return;
  if((b = t.closest('.archly [data-arz]'))){ archLyZoom(b.dataset.arz); return; }
  if(t.closest('[data-arall]') || (t.closest('.archly') && !t.closest('.archly-p'))){ archLyClose(); return; }   // × or the dimmed backdrop
  if(t.closest('[data-ardv]')){ const on = ARCH.dvf !== p; ARCH.dvf = on ? p : '';
    if(on){ ARCH.sel = null; ARCH.flow = null; ARCH.op = ''; }
    const hadF = document.activeElement === t.closest('[data-ardv]');   // ⚠the repaint drops focus to <body>
    paintStruct();
    if(hadF) kbHold('.archtab [data-ardv]');
    return; }
  if((b = t.closest('[data-ae]'))){ const k = p + '\t' + b.dataset.ae; ARCH.op = ARCH.op === k ? '' : k; paintStruct(); return; }
  if(t.closest('[data-arq]')){ const c = archCands(archHome(ARCH.cache[p]), SESS, p); ARCH.msg = '';
    if(archRunOf(p) || archSentPh(p) || (typeof archReqBusy === 'function' && archReqBusy(p, ARCH_PL))) return;
    if(ARCH.req && ARCH.req.p === p){ if(!ARCH.req.busy) ARCH.req = null; }   // second press closes the preview
    else { ARCH.req = { p, sid: (c[0] || {}).sid || '', busy: false }; ARCH.breq = null; ARCH.xm = ''; }   // one preview at a time (84m breq)
    const hadF = document.activeElement === t.closest('[data-arq]');   // ⚠the repaint drops focus to <body>
    paintStruct();
    if(hadF) kbHold('.archtab [data-arq]');
    return; }
  if(t.closest('[data-arx]')){ ARCH.req = null; paintStruct(); return; }
  if(t.closest('[data-arifx]')){ ARCH.ifx = null; paintStruct(); return; }
  if(t.closest('[data-argo]')){ archSend(); return; }
  if(t.closest('[data-arf]')){ ARCH.msg = ''; archFetch(p, true); return; }
  // Empty map / list space unpins an edge row's highlight (a pan's click is eaten by ARCH_PAN_EAT first).
  if(ARCH.op && t.closest('.archmap,.archel-list') && !t.closest('button,input,select,textarea,a,label,[data-p],.mmdfe,.arche,.archtop')){ ARCH.op = ''; paintStruct(); }
});
document.addEventListener('change', ev => {
  const s = ev.target;
  if(s && s.matches && s.matches('.archtab input[data-art]')){ ARCH.tests = !!s.checked; paintStruct(); return; }
  if(s && s.matches && s.matches('.archtab input[data-arfull]')){ ARCH.full = !!s.checked; paintStruct(); return; }
  if(!ARCH.req || !s || !s.matches || !s.matches('.archtab select[data-ars]')) return;
  ARCH.req.sid = s.value; paintStruct();
});
setInterval(() => archTick(Date.now()), 5000);
// Hover focus (overview and focus view alike); the last key is kept on the svg so moves inside one node do no work.
document.addEventListener('pointerover', ev => {
  const t = ev.target && ev.target.closest ? ev.target : null, svg = t && (t.closest('.archdg .archfh') || t.closest('.archdg svg'));   // ⚠not .archmap svg: legend swatches are svgs there too · .archfh = HTML focus layer (84j9)
  if(!svg) return;
  const p = t.closest('[data-p]'), e = !p && t.closest('.mmdfe');
  const h = p ? { node: p.dataset.p } : e ? { edge: { f: e.dataset.f, t: e.dataset.t } } : null, k = JSON.stringify(h);
  if(svg._arh === k) return;
  svg._arh = k; archHovPaint(svg, h);
});
document.addEventListener('pointerout', ev => {
  const t = ev.target && ev.target.closest ? ev.target : null, svg = t && (t.closest('.archdg .archfh') || t.closest('.archdg svg')), r = ev.relatedTarget;
  if(!svg || (r && svg.contains(r))) return;
  svg._arh = 'null'; archHovPaint(svg, null);
});
// Drag-to-pan on the map background (map and flow view). ⚠Modules, edges, controls and text keep their own click/selection.
const ARCH_PAN_PX = 4;
let ARCH_PAN_EAT = false;   // a real pan swallows the click that follows its pointerup
function archPanFrom(t){
  if(!t || !t.closest || t.closest('button,input,select,textarea,a,label,text,[data-p],.mmdfe,.archtop,.archbar,.archleg,.mmdtg')) return null;
  return t.closest('.archtab .archmap');
}
// ⚠A poll repaint swaps the scrollers mid-drag (archScrollPut copies the scroll over), so moves re-query a detached one.
function archPanStart(e){
  const map = e && e.button === 0 && strMode === 'arch' ? archPanFrom(e.target) : null;
  if(!map) return false;
  const sel = ['.archtab .archmap', '.archtab .archfdg .mmdv'], fd = e.target.closest('.archfdg .mmdv');
  const s0 = [[0, map.scrollLeft, map.scrollTop, map]].concat(fd ? [[1, fd.scrollLeft, fd.scrollTop, fd]] : []);
  const live = s => s[3].isConnected === false ? (s[3] = document.querySelector(sel[s[0]]) || s[3]) : s[3];
  const sx = e.clientX, sy = e.clientY;
  let on = false;
  e.preventDefault();   // no text-selection start on the background
  dragTrack(e, map, ev => {
    const dx = ev.clientX - sx, dy = ev.clientY - sy;
    if(!on && Math.abs(dx) < ARCH_PAN_PX && Math.abs(dy) < ARCH_PAN_PX) return;   // under threshold: still a plain click
    if(!on){ on = true; live(s0[0]).classList.add('archpan'); }
    for(const s of s0){ const el = live(s); el.scrollLeft = s[1] - dx; el.scrollTop = s[2] - dy; }
  }, () => {
    live(s0[0]).classList.remove('archpan');
    if(on){ ARCH_PAN_EAT = true; setTimeout(() => { ARCH_PAN_EAT = false; }, 0); }
  });
  return true;
}
document.addEventListener('pointerdown', ev => { archPanStart(ev); });
document.addEventListener('click', ev => { if(ARCH_PAN_EAT){ ARCH_PAN_EAT = false; ev.stopPropagation(); ev.preventDefault(); } }, true);
