// ── Structure «Architecture» view: verified module map from GET /api/arch (80-structure.js paintStruct dispatches here) ──────
// The diagram is the server's `md` (passed edges only) drawn by 81e mmdBlock; the edge list beside it holds every edge + evidence.
// ⚠Evidence is file:line:symbol only (metadata); code opens on click through the existing popup (81 strPopOpenRel).
// ⚠The request button never sends by itself: preview → a person presses confirm → /api/dm relay (AGENTS.md rule 7).
const ARCH_PL = 'arch-map';
const ARCH = { cache: {}, load: {}, op: '', req: null, msg: '', sel: null, tests: false, full: false, svg: {}, sent: null, flow: null, pstop: null, scope: null, lit: null, nx: {}, ifx: null, et: {} };   // et = «Connections» tree folds, key p\tn | p\tother, true = open (84j6) · ifx = {p, id} focus view with infrastructure unfolded (84j4) · scope = {p, layer, group} lit path level · lit = {p, flow, fs?} lit flow(s) · nx = folded neighbour branches (84j3)   // svg = archKey → rendered diagram; flow = {p, id} picked flow (84k)   // op = «path\tedge index» of the open evidence list; sel = {p, id} focused module
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
// Pure: style badges «Layered» (+ «estimated» when an evidence file is not in the commit) · framework · «Evidence N files»,
// then the deviation count; '' when the server sent no style. Evidence tooltip = files + units (strHdBadge escapes both).
function archStyleNote(d){
  const st = d && d.style && typeof d.style === 'object' ? d.style : null;
  if(!st || !st.style) return '';
  const fw = String(st.framework || ''), ev = (Array.isArray(st.evidence) ? st.evidence : []).filter(x => x && x.file);
  const tip = ev.map(x => x.file + (x.ok === false ? ' ✕' : '')).join('\n') + (st.units ? (ev.length ? '\n' : '') + T('Units: {u}').replace('{u}', String(st.units)) : '');
  const dv = Array.isArray(d.dev) ? d.dev.length : 0;
  // Separate badges: a long framework inside one combined badge got truncated along with the evidence count.
  return strHdBadge(st.ok === false ? 'cut strbg-asty' : 'asty', archStyleName(st) + (st.ok === false ? ' · ' + T('estimated') : ''))
    + (fw ? strHdBadge('dat', fw, fw) : '')
    + strHdBadge('', T('Evidence {n} files').replace('{n}', ev.length), tip)
    + (dv ? strHdBadge('cy', T('{n} outside {s} flow').replace('{n}', dv).replace('{s}', archStyleName(st)), T('Edges whose module roles go against this style')) : '');
}
// Pure: header badges — pass rate, modules, and a document-style version stamp «Generated MM-DD HH:MM · commit» (server `at`).
// A stale map keeps the stamp in the «cut» style; how far HEAD moved goes to its tooltip.
function archHeadNote(d){
  const r = archRate(d), c = String((d && d.commit) || '').slice(0, 7), h = String((d && d.head) || '').slice(0, 7);
  const at = d && typeof d.at === 'number' && isFinite(d.at) && d.at > 0 ? d.at : 0;
  const tip = T('Diagram commit {n} · HEAD now {m}').replace('{n}', c).replace('{m}', h);
  const ahead = d && d.stale ? (typeof d.behind === 'number' ? TV({msg: 'HEAD is {n} commits ahead', vars: {n: d.behind}}) : T('stale')) + ' · ' : '';
  return archStyleNote(d) + strHdBadge('n', T('Verified {n}/{m} ({k}%)').replace('{n}', r.n).replace('{m}', r.m).replace('{k}', r.pct),
      T('Edges with checked evidence / all edges'))
    + strHdBadge('', T('{n} modules').replace('{n}', ((d && d.modules) || []).length))
    + (c ? strHdBadge(d.stale ? 'cut' : '', at ? T('Generated {t} · {c}').replace('{c}', c).replace('{t}', hhmm(at, { date: true, dsep: '-' })) : c, ahead + tip) : '')
    + (typeof archChkHdBtn === 'function' ? archChkHdBtn(d) : '');   // 84l: issues badge, or «Security check» when the project has no results yet
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
    + '<span class=archlgh>' + esc(T('Hover:')) + '</span>'
    + it(sw(20, '<g class="mmdfe arn arin">' + ln('e-solid') + '</g>', 'archdim'), 'incoming')
    + it(sw(20, '<g class="mmdfe arn arout">' + ln('e-solid') + '</g>', 'archdim'), 'calls, 2 steps down')
    + it(sw(22, '<g class=mmdn><rect x=1 y=1 width=20 height=10 rx=2 ry=2 /></g>', 'archdim'), 'unrelated, dimmed') + '</div>';
}
// Pure: evidence list of one edge; every field escaped, file/line carried as data-* for the popup.
function archEvHtml(ev, i){
  const xs = (ev || []).filter(x => x && x.file);
  if(!xs.length) return '<div class=archevn>' + esc(T('No evidence')) + '</div>';
  return '<ol class=archev>' + xs.map(x => '<li><button type=button data-aev="' + esc(i) + '" data-af="' + esc(x.file) + '" data-al="' + esc(parseInt(x.line, 10) || 1)
    + '" data-as="' + esc(x.symbol || '') + '" title="' + esc(T('View code')) + '"><span class=archevf>' + esc(x.file) + '</span><span class=archevl>:' + esc(parseInt(x.line, 10) || 1)
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
// Pure: DM body the person previews; names the pipeline and the target repo, read-only by contract.
// Mailbox wire text in the same format as 48b pipeline run requests, not UI.
// ⚠Absolute paths under the Sidereus repo (home): the recipient may run in another repo, where relative ones miss.
function archDmBody(name, repo, home, verb, cx){   // verb = archReqOf(d).vb (wire text, default generate) · cx = Codex recipient
  const h = home ? String(home).replace(/\/+$/, '') + '/' : '';
  return '파이프라인 ' + name + ' 실행 — 요청: «' + repo + ' 아키텍처 구조도 ' + (verb || '생성') + '»\n'
    + '대상 저장소: ' + repo + '\n'
    + '읽기 전용, 저장소에 쓰지 않음 — 쓰기는 ${MAILBOX_DIR:-~/.mailbox-mcp}/arch/<key>/<commit>/ 아래만 (key: 파이프라인 rules)\n'
    + '파이프라인: ' + h + '.claude/pipelines/' + name + '.json (읽기 계획 → 모듈 그리기 → 흐름 그리기 → 검증)\n'
    + '게이트: python3 ' + h + 'scripts/arch_verify.py --last (Windows: py ' + h + 'scripts/arch_verify.py --last)'   // ⚠page has no server-OS signal: both forms
    // ⚠No Agent tool there: stages are lit by a leading shell marker (hooks/pl_mark.py --platform codex MARK).
    + (cx ? '\nRun the stages yourself in this session, in order (no subagents). Start each stage with a shell command echo "[pl:' + name + '/<stage title>]" and end it with echo "[pl-end:' + name + '/<stage title>]" ("|fail" before "]" when its gate failed); echo "[pl:-]" clears.'
      + ' At each stage start re-read only the files the previous stage wrote (for arch-map: plan.json, then map.json, then flows.json); do not rely on earlier stage context.'   // ⚠one Codex context holds every stage: stale earlier reads leak into later stages
      + ' Run all stages back to back in this turn: do not end the turn or report between stages; report once after the last stage.' : '');   // ⚠Codex ended its turn after each stage and waited for a new prompt
}
// Sidereus repo: the server's `sidereus` field, else the project whose pipeline list holds arch-map (48 PLS, if loaded).
function archHome(d){
  if(d && d.sidereus) return String(d.sidereus);
  const D = (typeof PLS !== 'undefined' && PLS && PLS.data) || {};
  return Object.keys(D).find(k => D[k] && D[k].ok && (D[k].pipelines || []).some(q => q && q.name === ARCH_PL)) || '';
}
// Pure: last path segment (option labels tell sessions apart by folder).
function archBase(p){ const s = String(p || '').replace(/[\\/]+$/, ''); return s.slice(Math.max(s.lastIndexOf('/'), s.lastIndexOf('\\')) + 1) || s; }
// Live Claude / Codex sessions (metadata only): target project p, then the Sidereus repo, then the rest; mailbox login first in each group.
// The first entry is the default recipient — the project's own session already holds that repo.
function archCands(home, sess, p){
  const g = x => x.cwd === p ? 0 : home && x.cwd === home ? 1 : 2;
  return (sess || []).filter(x => x && x.sid && x.state !== 'done' && (!x.plat || x.plat === 'cc' || x.plat === 'cx'))
    .map((x, i) => ({ sid: x.sid, model: x.model || '', cx: x.plat === 'cx', id: x.mbox || '', login: mboxIn(x), dir: archBase(x.cwd), g: g(x), i }))
    .sort((a, b) => a.g - b.g || (b.login ? 1 : 0) - (a.login ? 1 : 0) || a.i - b.i);
}
// Why «Confirm — send» is disabled ('' = enabled).
function archWhyOff(home, cands, cur){
  if(!home) return T('The Sidereus repository location is unknown');
  if(!cands.length) return T('No live session');
  if(!cur || !cur.login) return T('That session is not logged in to the mailbox');
  return '';
}
// Request button label + DM verb by map state: none/invalid -> generate · stale -> update · built at HEAD -> redraw.
function archReqOf(d){
  if(!d || !d.ok || d.empty || d.bad || !(d.modules || []).length) return { lb: 'Generate diagram', vb: '생성' };
  return !d.stale && d.head && d.commit === d.head ? { lb: 'Redraw', vb: '다시 그리기' } : { lb: 'Update diagram', vb: '업데이트' };
}
// Header request button: same place in every map state; disabled while a run/request is in flight.
function archReqBtn(p, home, cands, d){
  const live = !!(archRunOf(p) || archSentPh(p) || (typeof archReqBusy === 'function' && archReqBusy(p, ARCH_PL))), open = !!(ARCH.req && ARCH.req.p === p), why = live ? '' : archWhyOff(home, cands, cands[0]);
  return '<button type=button class="archgo archckgo' + (open ? ' on' : '') + '" data-arq aria-expanded=' + (open ? 'true' : 'false') + (live ? ' disabled' : '')
    + (why ? ' title="' + esc(why) + '"' : '') + '>' + esc(T(archReqOf(d).lb)) + '</button>';
}
// Pure: the preview panel once the request button is pressed (titled with its label); '' otherwise.
function archReqHtml(req, repo, home, cands, busy, d){
  if(!req) return '';
  const cur = cands.find(c => c.sid === req.sid) || null, why = archWhyOff(home, cands, cur), rk = archReqOf(d);
  return '<div class=archreq role=group aria-label="' + esc(T('Request preview')) + '"><div class=archrqh><b>' + esc(T(rk.lb)) + '</b>'
    + '<label>' + esc(T('To session')) + ' <select data-ars>' + (cands.length ? cands.map(c => '<option value="' + esc(c.sid) + '"' + (c.sid === req.sid ? ' selected' : '') + '>'
      + esc((c.dir ? c.dir + ' · ' : '') + sid8(c.sid) + (c.model ? ' · ' + c.model : '') + (c.id ? ' · ' + c.id : '')) + '</option>').join('') : '<option value="">' + esc(T('None')) + '</option>')
    + '</select></label></div><pre class=archdm>' + esc(archDmBody(ARCH_PL, repo, home, rk.vb, !!(cur && cur.cx))) + '</pre>' + plCxHint(cur) + '<div class=archrqb>'
    + '<button type=button class="wkrgb archok" data-argo' + (why || busy ? ' disabled' : '') + (why ? ' title="' + esc(why) + '"' : '') + '>' + esc(T(busy ? 'Sending…' : 'Confirm — send')) + '</button>'
    + '<button type=button class=wkrgb data-arx>' + esc(T('Cancel')) + '</button>' + (why ? '<span class=archwhy>' + esc(why) + '</span>' : '') + '</div></div>';
}
// Pure: test/gate modules — off the map unless «Include tests» (they import everything and add only crossings).
function archIsTest(m){
  return !!m && (m.kind === 'test' || /^(gates?|tests?|checks?)$/i.test(String(m.id || '')) || /\btests?\b/i.test(String(m.name || '')));
}
// Pure: quoted mermaid label; 81e mmdLabel decodes the entities back, mmdSvg esc()s the result.
function archMq(s){
  return '"' + String(s == null ? '' : s).replace(/[\r\n]+/g, ' ').replace(/[&<>"|]/g, c => '&#' + c.charCodeAt(0) + ';') + '"';
}
// Pure: passed edges collapsed to one per ordered module pair; self-edges and hidden (test) modules dropped.
function archPairs(mods, edges, tests){
  const keep = {}, at = {}, out = [], KR = { event: 0, call: 1, read: 2, write: 3 };
  (mods || []).forEach(m => { if(m && m.id != null && (tests || !archIsTest(m))) keep[m.id] = 1; });
  (edges || []).forEach(e => {
    if(!e || !e.ok || e.from === e.to || !keep[e.from] || !keep[e.to]) return;
    const k = e.from + '\u0001' + e.to;
    let p = at[k];
    if(!p) out.push(p = at[k] = { from: e.from, to: e.to, n: 0, est: true, label: '', kind: '' });
    p.n++;
    const kk = KR[e.kind] != null ? e.kind : 'call';   // import/config/di/serve draw as call; event only when every edge is one
    if(!p.kind || KR[kk] > KR[p.kind]) p.kind = kk;
    if(!e.est) p.est = false;   // one direct reference is enough to draw the pair solid
    if(!p.label && e.label) p.label = String(e.label);
  });
  return out;
}
// Pure: transitive reduction for the overview — a pair is dropped while its target stays reachable without it
// (est pairs tried first, then input order; cycles kept). ★Self-map overview crossings 109 -> 2 (mmdQuality).
// ⚠Overview hover then lights only drawn edges, not every neighbour (downstream follows them for 2 hops); the focus view keeps every direct edge.
function archReduce(ps){
  const L = ps || [], on = L.map(() => true);
  const reach = (s, t, skip) => {
    const seen = new Set([s]), q = [s];
    while(q.length){ const u = q.shift();
      for(let i = 0; i < L.length; i++){
        if(!on[i] || i === skip || L[i].from !== u) continue;
        if(L[i].to === t) return true;
        if(!seen.has(L[i].to)){ seen.add(L[i].to); q.push(L[i].to); }
      } }
    return false;
  };
  L.map((p, i) => i).sort((a, b) => (L[b].est ? 1 : 0) - (L[a].est ? 1 : 0) || a - b)
    .forEach(i => { if(reach(L[i].from, L[i].to, i)) on[i] = false; });
  return L.filter((p, i) => on[i]);
}
// Pure: mermaid source. sel = '' → overview (every visible module, pair edges labelled only by «×N» when merged;
// implied pairs dropped by archReduce unless full); sel = module id → that module + direct neighbours, edges labelled.
// Node id = 'm' + index in mods (click maps it back).
function archSrc(mods, edges, tests, sel, full){
  const ix = {}, nb = {}, ln = ['flowchart ' + (sel ? 'LR' : ARCH_DIR)];
  (mods || []).forEach((m, i) => { if(m && m.id != null) ix[m.id] = i; });
  let ps = archPairs(mods, edges, tests);
  if(sel){ ps = ps.filter(p => p.from === sel || p.to === sel); nb[sel] = 1; ps.forEach(p => { nb[p.from] = nb[p.to] = 1; }); }
  else if(!full) ps = archReduce(ps);
  const vis = (mods || []).filter(m => m && m.id != null && (sel ? nb[m.id] : tests || !archIsTest(m)));
  const nd = m => '  m' + ix[m.id] + (m.kind === 'external' ? '([' + archMq(m.name || m.id) + '])' : '[' + archMq(m.name || m.id) + ']');
  vis.filter(m => m.kind !== 'external').forEach(m => ln.push(nd(m)));
  const ex = vis.filter(m => m.kind === 'external');
  if(ex.length){ ln.push('  subgraph xg[' + archMq(T('External')) + ']'); ex.forEach(m => ln.push(nd(m))); ln.push('  end'); }
  ps.forEach(p => {
    const lab = sel ? (p.label + (p.n > 1 ? ' ×' + p.n : '')).trim() : (p.n > 1 ? '×' + p.n : '');
    ln.push('  m' + ix[p.from] + ' ' + (p.est ? '-.->' : '-->') + (lab ? '|' + archMq(lab) + '|' : '') + ' m' + ix[p.to]);
  });
  return ln.join('\n');
}
// Pure, O(V+E): fixed overview ranks (id -> rank). DFS back edges ignored, longest path from entries (rank 0),
// the External box 'xg' one below. ⚠Sinks are not pinned to the bottom (self-map crossings 2 -> 6).
function archRanks(ids, pairs){
  const own = Object.prototype.hasOwnProperty, at = {}, out = {}, inn = {}, rk = {}, L = (ids || []).filter(k => k !== 'xg');
  L.forEach(k => { at[k] = 1; out[k] = []; inn[k] = 0; rk[k] = 0; });
  let xe = false;
  (pairs || []).forEach(p => {
    if(p.from === 'xg' || p.to === 'xg'){ xe = true; return; }
    if(own.call(at, p.from) && own.call(at, p.to) && p.from !== p.to) out[p.from].push(p.to);
  });
  L.forEach(k => out[k].forEach(t => { inn[t]++; }));
  const st = {}, back = new Set(), deg = {};   // st: 1 = on stack, 2 = done
  L.filter(k => !inn[k]).concat(L.filter(k => inn[k])).forEach(r => {
    if(st[r]) return;
    const sk = [[r, 0]]; st[r] = 1;
    while(sk.length){
      const f = sk[sk.length - 1], u = f[0];
      if(f[1] >= out[u].length){ st[u] = 2; sk.pop(); continue; }
      const i = f[1]++, v = out[u][i];
      if(st[v] === 1) back.add(u + '\u0001' + i);
      else if(!st[v]){ st[v] = 1; sk.push([v, 0]); }
    }
  });
  const fw = u => out[u].filter((v, i) => !back.has(u + '\u0001' + i));
  L.forEach(k => { deg[k] = 0; }); L.forEach(k => fw(k).forEach(v => { deg[v]++; }));
  const q = L.filter(k => !deg[k]);
  let mx = 0;
  for(let h = 0; h < q.length; h++){ const u = q[h]; fw(u).forEach(v => { rk[v] = Math.max(rk[v], rk[u] + 1); mx = Math.max(mx, rk[v]); if(!--deg[v]) q.push(v); }); }
  if((ids || []).indexOf('xg') >= 0) rk.xg = xe ? mx + 1 : mx;   // ⚠every root id needs a rank or 81f drops rankFix
  return rk;
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
  return '<div class=mmd><div class=mmdbar><button type=button class=mmdtg aria-pressed=false>' + esc(T('Source text')) + '</button></div>'
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
  return '<div class="archbar on"><button type=button class=archall data-arall title="' + esc(T('Back (Esc)')) + '">' + esc('← ' + T('Back to full diagram')) + '</button>'   // first: where the eye starts
    + (pick || '') + '<b class=archsel>' + esc(m.name || m.id) + '</b>'
    + '<span class="archlg in">' + esc(T('In') + ' ' + ni) + '</span><span class="archlg out">' + esc(T('Out') + ' ' + no) + '</span>'
    + (ifx ? '<button type=button class=archfbt data-arifx>' + esc(T('Fold infrastructure')) + '</button>' : '') + tg + '</div>';
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
    if(slot && slot.dataset && slot.dataset.k === k){ slot.innerHTML = ARCH.svg[k];
      const pd = box._arpend; box._arpend = null;   // ⚠the paint put the scroll back onto the short loading line, which clamped it to 0
      if(pd) archScrollPut(box, pd[0], pd[1], pd[2]);
      if(typeof archLitNow === 'function') archLitNow(slot); }
  };
  if(typeof requestAnimationFrame === 'function') requestAnimationFrame(() => setTimeout(fill, 0)); else setTimeout(fill, 0);
  box._arpend = box._arsm;   // scroll to restore in fill; a paint before then reads this instead of the clamped DOM
  return archWaitHtml();
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
function archPaint(box, head){
  const p = strOn[0] || '';
  if(!p){ box.innerHTML = '<div class="strtab archtab">' + head('') + '<div class=strload>' + esc(T('Pick a project.')) + '</div></div>'; return; }
  archFetch(p, false);
  const d = ARCH.cache[p], home = archHome(d), cands = archCands(home, SESS, p);
  archSentFin(p, d);
  if(ARCH.req && ARCH.req.p !== p) ARCH.req = null;
  const run = archRunOf(p);
  if(run && !ARCH.rsig) ARCH.rsig = [p, run.stage, run.n, run.sid].join('\t');   // first paint: a run ending before archTick's first look still refetches
  if(run) ARCH.req = null;   // ⚠one run per project: a live run closes the preview so no second request goes out
  if(ARCH.req && !cands.some(c => c.sid === ARCH.req.sid) && cands.length) ARCH.req.sid = cands[0].sid;
  const fz = ARCH.sel && ARCH.sel.p === p ? archFitOf(box) : null, fzk = fz ? fz.w + 'x' + fz.h : '';   // focus room (resize repaints on change)
  // Poll repaints on every session change: same response + same view state keeps the drawing (no flicker, select keeps focus).
  const sig = [p, LANG, ARCH.op, JSON.stringify(ARCH.req), ARCH.msg, archSentPh(p), run ? [run.stage, run.n, run.sid].join('/') : '', JSON.stringify(ARCH.sel), JSON.stringify(ARCH.flow || null), JSON.stringify([ARCH.scope, ARCH.lit, ARCH.nx, ARCH.ifx, ARCH.et]), ARCH.tests, ARCH.full, fzk, typeof archReqSig === 'function' ? archReqSig(p) : '', cands.map(c => c.sid + (c.login ? '+' : '')).join(',')].join('\t');
  if(d && box._arj === d && box._arsig === sig && box.querySelector('.archtab')) return;
  box._arj = d; box._arsig = sig;
  const msg = ARCH.msg ? '<div class=archmsg role=status>' + esc(ARCH.msg) + '</div>' : '';
  if(!d){ box.innerHTML = '<div class="strtab archtab">' + head(esc(T('Loading…'))) + '' + archWaitHtml() + '</div>'; return; }
  const req = archReqHtml(ARCH.req, p, home, cands, ARCH.req && ARCH.req.busy, d);
  const pre = archReqBtn(p, home, cands, d), pre0 = pre + (typeof archChkEntry === 'function' ? archChkEntry(d) : '');   // no-map states: security check entry too (84l)
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
  // Stale map / live run: a small header chip + inline status, not a full-width band (small enough to need no dismiss).
  const chip = d.stale ? strHdBadge('cut', T('Diagram is older than the code'), T('The diagram is older than the code — a new one is built from the latest commit.')) : '';
  const prow = typeof archReqLast === 'function' ? archReqLast(p, ARCH_PL) : null;   // request record (84l2): a live one takes the header line's place
  const hst = chip + (prow && archReqLive(prow) ? '' : run ? archRunHtml(run) : d.stale ? archSentHtml(p) : '');
  const rq0 = req || (!d.stale && !run ? archSentHtml(p) : ''), rq = prow ? archReqSlot(p, ARCH_PL, rq0, req) : rq0;   // map preview / sent line under the header
  // Selection survives poll repaints; a module gone from a rebuilt map falls back to the overview.
  const si = ARCH.sel && ARCH.sel.p === p ? mods.findIndex(m => m && m.id === ARCH.sel.id) : -1, sel = si >= 0 ? mods[si].id : '';
  const tests = ARCH.tests || (si >= 0 && archIsTest(mods[si]));   // a focused test module shows its own edges
  const io = e => !sel ? '' : e.from === sel ? 'out' : e.to === sel ? 'in' : null;
  const ord = edges.map((e, i) => ({ e, i, io: io(e) })).filter(o => o.io !== null)
    .sort((a, b) => (b.e.ok ? 1 : 0) - (a.e.ok ? 1 : 0));   // passed first, failed last
  const same = box._arp === p; box._arp = p;   // ⚠keep scroll only within one project: another project opens at 0,0
  const keep = n => { const x = same && box.querySelector && box.querySelector(n); return x ? [x.scrollTop, x.scrollLeft] : null; };
  // ⚠refit pass, or a paint while the diagram is still loading (a lit flow's off-screen count resizes the bar, so the next poll repaints):
  //   the DOM scroll was clamped to 0 under the loading line, use the saved one
  const hold = box._arfit ? box._arhold : same && box._arpend && box._arpend[0] ? box._arpend : null;
  let sm = hold ? hold[0] : keep('.archmap'); const sl = hold ? hold[1] : keep('.archel-list'), sd = hold ? hold[2] : keep('.archdet');   // ⚠innerHTML resets scroll: clicks must not move the view
  box._arsm = [sm, sl, sd];   // a cache miss draws after a frame (archDiagram fill): it restores this once the diagram is in
  const devAt = {}, devSn = d.style && d.style.style ? archStyleName(d.style) : '';   // edge index -> deviation (server validated i)
  if(devSn) (Array.isArray(d.dev) ? d.dev : []).forEach(x => { if(x && typeof x.i === 'number') devAt[x.i] = x; });
  const lay = archHasLayers(d, tests);   // ⚠v1: archSrc/archRanks path unchanged (R4)
  const fv = lay && sel && typeof archFocusSrc === 'function';   // v2 focus: bands kept, neighbours only (84j4)
  const ents = lay && (!sel || fv) && Array.isArray(d.flows) && d.flows.length && typeof archFlowEntries === 'function' ? archFlowEntries(d, mods, tests) : null;   // entry nodes (84k)
  const fo = !!(fv && ARCH.ifx && ARCH.ifx.p === p && ARCH.ifx.id === sel), lf = fv && ARCH.lit && ARCH.lit.p === p ? (ARCH.lit.fs || [ARCH.lit.flow]).map(String) : null;
  const flit = { flows: d.flows, fs: lf }, fx = fv ? 'fv' + (fo ? 1 : 0) + '|' + (lf || []).join(',') : '';
  const bp = lay && typeof archBandPlan === 'function' ? archBandPlan(d, mods, tests) : null;   // band mode from the map style (84j2)
  const kinds = fv ? archFocusKinds(mods, edges, tests, sel, ents, fo, flit, bp) : lay ? archKindMap(mods, edges, tests, ents, bp) : null;
  const src = fv ? archFocusSrc(mods, edges, tests, sel, d.groups, ents, fo, flit, fz, bp) : lay && !sel ? archBandSrc(mods, edges, tests, ARCH.full, d.groups, ents, bp) : archSrc(mods, edges, tests, sel, ARCH.full), any = edges.some(e => e && e.ok), k = archKey(d, sel, tests, ARCH.full, ents, fx) + (sel && fz ? '\t' + fzk : '');
  // ⚠no .archmap in the DOM (back from another main tab / «Size» / a flow) or a view-key change (focus -> overview): put back that view's last scroll (84j7)
  //   instead of the carried one; before archDiagram reads box._arsm. No saved entry = carried scroll (archMmFirst rules apply).
  if(same && !hold && typeof archMmPick === 'function'){ const od = box.querySelector && box.querySelector('.archdg');
    const pv = archMmPick(sm, od && od.dataset ? od.dataset.k : null, k); if(pv !== sm){ sm = pv; box._arsm = [sm, sl, sd]; } }
  const fa = Array.isArray(d.flows) && d.flows.length ? archFlowAt(d, p) : null, fl = fa && fa.fi >= 0 ? fa.fls[fa.fi] : null;   // ⚠no flows: no 84k call, same page as before
  // Flow view has no header buttons: a stale map puts its request button next to the chip; an open preview sits under the header.
  const fhd = d.stale ? chip + archStatusHtml(p, archReqBtn(p, home, cands, d)) : hst;
  if(fl){ box.innerHTML = '<div class="strtab archtab">' + head(archHeadNote(d), '', fhd) + (d.stale && req ? '<div class=archck>' + req + '</div>' : '') + msg + archFlowBody(fa.fls, fa.fi, names) + '</div>';
    archScrollPut(box, sm, sl); archFlowMark(box.querySelector && box.querySelector('.archfdg svg'), fl); return; }
  box.innerHTML = '<div class="strtab archtab">' + head(archHeadNote(d), '', hst + pre) + (rq ? '<div class=archck>' + rq + '</div>' : '') + msg
    + '<div class=archbody' + strSplitStyle('archbody') + '><div class=archmap><div class=archtop>' + (typeof archPathHtml === 'function' ? archPathHtml(mods, d.groups, sel, ARCH.scope && ARCH.scope.p === p ? ARCH.scope : null) : '') + archBarHtml(mods, edges, sel, tests, ARCH.full, fa ? archFlowPick(fa.fls, ARCH.lit && ARCH.lit.p === p ? ARCH.lit.flow : '') : '', fo)
    + (lay ? '' : '<div class="archmsg archnol" role=status>' + esc(T('No layers — redraw the diagram')) + '</div>')
    + (any ? archLegHtml(lay, !!kinds && Object.keys(kinds).some(x => kinds[x] === 'uses')) : '') + '</div>' + (any ? '<div class=archdg data-k="' + esc(k) + '"' + (fv ? ' data-fv' : '') + (si >= 0 ? ' data-hub="m' + si + '"' : '') + (sel && fz ? ' data-fit="' + esc(fzk) + '"' : '') + '>' + archDiagram(box, k, src, mods, si >= 0 ? si : '', kinds, sel ? fz : null, bp) + '</div>' : '<div class=strload>' + esc(T('No edge passed the check.')) + '</div>') + '</div>'
    + (any && lay && typeof archMmHtml === 'function' ? archMmHtml(archMmOn()) : '')   // minimap overlay (84j7), outside .archmap
    + (sel && typeof archDetHtml === 'function' ? archDetHtml(d, sel, names, ARCH.nx, { op: i => ARCH.op === p + '\t' + i, dv: i => devAt[i], sn: devSn, drawn: archDrawn(mods, edges, tests, sel, ARCH.full), lit: ARCH.lit && ARCH.lit.p === p ? ARCH.lit.flow : null })   // module detail (84j3)
      : '<aside class=archside><div class=archsh><b>' + esc(T('Edges')) + '</b><span>' + esc(T('Click for evidence · click evidence for code')) + '</span>'
    + '<button type=button class=archrf data-arf title="' + esc(T('Reload now')) + '">↻</button></div>'
    + (typeof archEdTreeHtml === 'function' ? archEdTreeHtml(d, names, p, { op: ARCH.op, et: ARCH.et, dv: devAt, sn: devSn })   // flow tree (84j6)
      : '<ul class=archel-list>' + ord.map(o => archEdgeRow(o.e, names, o.i, ARCH.op === p + '\t' + o.i, o.io, devAt[o.i], devSn)).join('') + '</ul>') + '</aside>') + strSplitGrip('archbody') + '</div></div>';
  archScrollPut(box, sm, sl, sd);
  // ⚠the room was measured on the previous paint (overview bar or none): re-measure once on the new frame and redraw if it moved
  if(sel && !box._arfit){ const f2 = archFitOf(box); if(f2 && f2.w + 'x' + f2.h !== fzk){ box._arfit = 1; box._arhold = [sm, sl, sd]; box._arsig = ''; try{ archPaint(box, head); } finally { box._arfit = 0; box._arhold = null; } return; } }
  if(typeof archLitNow === 'function') archLitNow(box.querySelector && box.querySelector('.archdg'));   // cached svg: lit classes go back on
}
// Restore the map/list scroll saved before an innerHTML repaint.
function archScrollPut(box, sm, sl, sd){
  const put = (n, v) => { const x = v && box.querySelector && box.querySelector(n); if(x){ x.scrollTop = v[0]; x.scrollLeft = v[1]; } };
  put('.archmap', sm); put('.archel-list', sl); put('.archdet', sd);
}
// Pure guard + send: only the confirm button calls this, and only with an open preview (no auto-send).
async function archSend(){
  const q = ARCH.req;
  if(!q || q.busy) return false;
  const d = ARCH.cache[q.p], home = archHome(d), cur = archCands(home, SESS, q.p).find(c => c.sid === q.sid);
  if(!cur || !cur.login || archRunOf(q.p) || (typeof archReqBusy === 'function' && archReqBusy(q.p, ARCH_PL))) return false;
  q.busy = true; paintStruct();
  try{
    const j = await postJSON('/api/dm', { to: cur.id, body: archDmBody(ARCH_PL, q.p, home, archReqOf(d).vb, !!cur.cx), relay: true, sid: cur.sid, thread: 'pipeline:' + ARCH_PL,
      plreq: { kind: 'req', pipeline: ARCH_PL, repo: q.p } });   // server records who received it (state `plReq`)
    if(!j || !j.ok) throw new Error((j && (j.error || j.err)) || '?');   // ⚠ok first: nothing went out, remember nothing
    const m = plMem(); m[cur.sid] = { name: ARCH_PL, at: Date.now() }; lsSetJson('sidereus.plrun', m);   // same lighting memo as 48b plRunSend
    ARCH.req = null; ARCH.msg = ''; ARCH.sent = { p: q.p, sid: cur.sid, id: cur.id, at: Date.now(), ph: 'sent',
      base: d && d.ok && !d.empty ? String(d.commit || '') : '' };   // base: a map with another commit means done
  }catch(e){ q.busy = false; ARCH.msg = T('Could not send') + ': ' + T((e && e.message) || e); }
  paintStruct();
  return true;
}
// Diagram click (true = handled). Module: focus one level; the focused one again opens its folder in the code tree (no path: no-op).
// Edge line/label: toggle the evidence of its first passed edge (only ok edges are drawn, archPairs; a ×N pair opens the first).
// ⚠No scroll or centring: archPaint restores the map/list scroll like the [data-ae] list rows.
function archDgClick(p, t){
  const d = ARCH.cache[p] || {}, mods = d.modules || [], at = s => mods[parseInt(String(s || '').slice(1), 10)];
  let b;
  if((b = t.closest('.archdg [data-p]'))){ const m = /^m\d+$/.test(String(b.dataset.p || '')) ? at(b.dataset.p) : null;
    if(!m){ if(typeof archFocusClick === 'function') archFocusClick(p, d, String(b.dataset.p || '')); return true; }   // ifx chip / entry node (focus view only)
    if(typeof archFocusHx === 'function' && b.closest('.archdg[data-fv]') && archFocusHx(b.dataset.p)){ archFocusClick(p, d, b.dataset.p); return true; }   // paired entry hexagon: lights its flows
    if(ARCH.sel && ARCH.sel.p === p && ARCH.sel.id === m.id){ if(m.path) strPopOpenTree(p, String(m.path)); }
    else { ARCH.sel = { p, id: m.id }; ARCH.op = ''; paintStruct(); }
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
  if(t.closest('[data-arall]')){ ARCH.sel = null; ARCH.scope = null; ARCH.lit = null; ARCH.op = ''; paintStruct(); return; }
  if((b = t.closest('[data-ae]'))){ const k = p + '\t' + b.dataset.ae; ARCH.op = ARCH.op === k ? '' : k; paintStruct(); return; }
  if(t.closest('[data-arq]')){ const c = archCands(archHome(ARCH.cache[p]), SESS, p); ARCH.msg = '';
    if(archRunOf(p) || archSentPh(p) || (typeof archReqBusy === 'function' && archReqBusy(p, ARCH_PL))) return;
    if(ARCH.req && ARCH.req.p === p){ if(!ARCH.req.busy) ARCH.req = null; }   // second press closes the preview
    else ARCH.req = { p, sid: (c[0] || {}).sid || '', busy: false };
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
  const t = ev.target && ev.target.closest ? ev.target : null, svg = t && t.closest('.archdg svg');   // ⚠not .archmap svg: legend swatches are svgs there too
  if(!svg) return;
  const p = t.closest('[data-p]'), e = !p && t.closest('.mmdfe');
  const h = p ? { node: p.dataset.p } : e ? { edge: { f: e.dataset.f, t: e.dataset.t } } : null, k = JSON.stringify(h);
  if(svg._arh === k) return;
  svg._arh = k; archHovPaint(svg, h);
});
document.addEventListener('pointerout', ev => {
  const t = ev.target && ev.target.closest ? ev.target : null, svg = t && t.closest('.archdg svg'), r = ev.relatedTarget;
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
// Focus view refits to the map box on resize (debounced); archPaint repaints only when the 20px room bucket moved.
let ARCH_RZ = 0;
if(typeof window !== 'undefined' && window.addEventListener) window.addEventListener('resize', () => {
  clearTimeout(ARCH_RZ);
  ARCH_RZ = setTimeout(() => { if(mainView === 'struct' && strMode === 'arch' && ARCH.sel) paintStruct(); }, 160);
});
