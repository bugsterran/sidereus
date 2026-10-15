// ── Work unit: worktree <-> live sessions (Paseo's worktree = agent 1:1). Metadata only (path · sid · model · labels).
// ⚠Paths compare through brNorm: the server realpaths worktree roots, session cwds may still say /tmp (= /private/tmp).
let brPanLast = '';
function brNorm(p){ p = String(p || ''); if(p.indexOf('/private/') === 0) p = p.slice(8); return p.replace(/\/+$/, ''); }
function brWtFind(path){ const n = brNorm(path); return ((BR && BR.worktrees) || []).find(w => brNorm(w.path) === n) || null; }
function brWtName(w){ return strShort(w.path) + (w.main ? ' · ' + T('main') : ''); }
// Longest worktree path containing the session's git root (main checkout contains .claude/worktrees/* too).
function brWtOfSess(x){
  const c = brNorm((x.wt && x.wt.root) || x.cwd);
  let best = '';
  ((BR && BR.worktrees) || []).forEach(w => { const p = brNorm(w.path);
    if((c === p || c.indexOf(p + '/') === 0) && p.length > best.length) best = p; });
  return best;
}
function brWtSess(path){
  const n = brNorm(path);
  return (SESS || []).filter(x => x && x.state !== 'done' && x.cwd && brWtOfSess(x) === n);
}
// Several sessions can share one cwd — then the sid picks the transcript (same form as the timeline's old-session bars).
function brSessTid(x){
  if(extTid(x)) return extTid(x);
  const dup = (SESS || []).filter(s => s && s.cwd === x.cwd && !extTid(s)).length > 1;   // ⚠Claude rows only — a Gemini row is not a sibling
  return 'sess:' + x.cwd + (dup && x.sid ? '|' + x.sid : '');
}
// ── Remote freshness (server: sidereus/git.py remote_info). Sidereus never fetches — it only says how old the remote refs are.
// '' = fresh or no remote; else the tooltip for muted remote ahead/behind (threshold BR.fetchStaleH, default 24h).
function brFetchStale(){
  const rs = (BR && BR.remote) || [];
  if(!rs.length) return '';
  const at = rs[0].fetchAt;
  if(!at) return T('Never fetched — ahead/behind vs the remote cannot be trusted');
  return Date.now() / 1000 - at > ((BR && BR.fetchStaleH) || 24) * 3600
    ? T('Remote info as of {t} — later remote changes are not reflected').replace('{t}', agoAt(at)) : '';
}
function brFetchNote(){
  const rs = (BR && BR.remote) || [];
  if(!rs.length) return ' · ' + esc(T('no remote'));
  const at = rs[0].fetchAt, st = brFetchStale();
  const tip = rs.map(r => r.name + ' · ' + (r.host || (r.local ? 'local path' : '?'))).join('\n');
  const cmd = 'git -C ' + (/^[\w@%+=:,./-]+$/.test(brRepo || '') ? brRepo : "'" + String(brRepo || '').replace(/'/g, "'\\''") + "'") + ' fetch';
  return ' · <span class="brfr' + (st ? ' brfro' : '') + '" title="' + esc(tip + (st ? '\n' + st : '')) + '">' + esc(T('remote')) + ' '
    + esc(rs.map(r => r.name).join(', ')) + ' · ' + esc(at ? T('last fetch') + ' ' + agoAt(at) : T('never fetched')) + '</span>'
    + ' <button class=brfc data-fcp="' + esc(cmd) + '" title="' + esc(T('Copy the fetch command (Sidereus does not fetch)')) + '">' + esc(T('fetch cmd')) + '</button>';
}
// Upstream ahead/behind is remote-based -> muted when the fetch is stale. ⚠Worktree ↑↓ vs base (brWtMeta) is local refs — stays normal.
function brSgHtml(b){
  if(!b || !(b.ahead || b.behind)) return '';
  const st = b.upstream && ((BR && BR.branches) || []).some(v => v.kind === 'remote' && v.name === b.upstream) ? brFetchStale() : '';
  const o = st ? '<span class="brsg brsgo" title="' + esc(st) + '">' : '<span class=brsg>';
  return (b.ahead ? o + '↑' + b.ahead + '</span>' : '') + (b.behind ? o + '↓' + b.behind + '</span>' : '');
}
function brBrSg(name){
  return brSgHtml(((BR && BR.branches) || []).find(v => v.kind === 'local' && v.name === name));
}
function brWsRow(x){
  const st = x.state || 'unknown', ns = (x.sub || []).length;
  return '<div class="brws st-' + esc(st) + '" data-wks="' + esc(x.cwd) + '" data-wkt="' + esc(brSessTid(x)) + '" title="'
    + esc(x.cwd + ' · ' + (x.sid || x.id || '') + (x.model ? ' · ' + x.model : '') + ' — ' + T('Click to see the work log')) + '">'
    + '<span class=sd></span><b>' + esc(x.project || '?') + '</b>'
    + (ns ? '<s>' + esc(T('Subagents')) + ' ' + ns + '</s>' : '')
    + (x.branch ? '<span class=brwb>' + esc(x.branch) + '</span>' : '')
    + (x.git ? '<u>' + esc(x.git) + '</u>' : '')
    + '<em>' + esc(AGO(ago(x.ageSec || 0))) + '</em></div>';
}
// ── Sidereus's own layer on each work unit: attention, 5h quota share, health (server: sidereus/git.py wt_signals).
function brWtSig(w){ return ((BR && BR.wtSig) || {})[w.path] || null; }
// Top attention row among this worktree's sessions (any state); list-only kinds never show, same as the strip.
function brWtAttn(path){
  const n = brNorm(path), sids = new Set((SESS || []).filter(x => x && x.sid && brWtOfSess(x) === n).map(x => x.sid));
  let best = null;
  ((ATTN && ATTN.rows) || []).forEach(r => {
    if(!sids.has(r.sid)) return;
    const g = (r.sigs || []).find(s => !ATTN_LIST_ONLY.has(s.k));
    if(g && (!best || r.score > best.r.score)) best = { r: r, g: g };
  });
  return best;
}
// ⚠Card order comes from the server only (sidereus/git.py wt_order): the poll's per-repo order, else the fetch-time
//   `BR.wtOrder`. Paths missing from it (graph refetched elsewhere) keep input order after the listed ones.
let brWtOrd = {};
function brWtSorted(){
  const ws = (BR && BR.worktrees) || [], ord = brWtOrd[BR && BR.cwd] || (BR && BR.wtOrder) || [];
  const at = new Map(ord.map((p, i) => [p, i]));
  return ws.map((w, i) => [at.has(w.path) ? at.get(w.path) : ord.length + i, w]).sort((a, b) => a[0] - b[0]).map(v => v[1]);
}
function brWtMeta(w, ss){
  const s = brWtSig(w), a = brWtAttn(w.path), bits = [];
  if(a) bits.push('<span class="brwat" data-wat="' + esc(a.r.sid) + '" title="' + esc(attnWhy(a.g) + ' — ' + T('Click to jump to that session')) + '">'
    + esc(attnLbl(a.g.k)) + '</span>');
  if(s){
    const tk = (BR && BR.wtTok) || {};
    // ⚠A trailing «~» read as a range; partial spans now show «≈» plus the reason in the tooltip.
    if(s.cyc) bits.push('<span title="' + esc(T("Tokens this worktree's sessions (incl. subagents) used this 5h cycle")
      + (tk.partial ? '\n≈ ' + T('Only part of this cycle was recorded — may be lower than actual') : '')) + '">'
      + esc(T('5h share')) + ' <b>' + s.share + '%</b> · ' + (tk.partial ? '≈ ' : '') + fmtTok(s.cyc) + '</span>');
    if(s.day) bits.push('<span title="' + esc(T('Tokens used today (only the span the server saw)')
      + (tk.dayPartial ? '\n≈ ' + T('Records start after midnight — partial') : '')) + '">' + esc(T('Today')) + ' ' + (tk.dayPartial ? '≈ ' : '') + fmtTok(s.day) + '</span>');
    if(s.dirty) bits.push('<span class=brwd>' + esc(T('uncommitted')) + ' ' + s.dirty + '</span>');
    // Local refs vs the base branch — no remote involved, so never muted by fetch age.
    if(s.ahead || s.behind) bits.push('<span title="' + esc(T('Commits ahead/behind the base branch (local refs, no fetch)') + ' · ' + s.base) + '">'
      + esc(T('base')) + ' ' + esc(s.base) + (s.ahead ? ' ↑' + s.ahead : '') + (s.behind ? ' ↓' + s.behind : '') + '</span>');
    // git-flow PR target by branch type (server wt_base): feature/bugfix -> develop, release/hotfix -> master + develop.
    if(s.pr && s.pr.length) bits.push('<span class=brwpr title="' + esc(T('PR target by git-flow rules (Sidereus does not open PRs)')) + '">'
      + esc(T('PR to')) + ': ' + esc(s.pr.join(' · ')) + '</span>');
    if(s.last) bits.push('<span>' + esc(T('last commit')) + ' ' + esc(agoAt(s.last)) + '</span>');
    const sd = (BR && BR.wtStaleDays) || 7;
    if(!ss.length && s.chg && Date.now() / 1000 - s.chg > sd * 86400)
      bits.push('<span class=brwst title="' + esc(T('No live session and nothing changed for over {n} days').replace('{n}', sd)) + '">' + esc(T('stale')) + '</span>');
  }
  return bits.length ? '<div class=brwm>' + bits.join('') + '</div>' : '';
}
function brWtHtml(){
  const ws = brWtSorted();
  if(!ws.length) return '';
  return '<div class=hidnote>' + esc(T('Work units')) + ' ' + ws.length + ' · ' + esc(T('sessions per worktree — click to gather')) + '</div>'
    + ws.map(w => {
        const ss = brWtSess(w.path);
        return '<button class="brwt' + (brWu && brNorm(brWu) === brNorm(w.path) ? ' on' : '') + '" data-bw="' + esc(w.path)
          + '" title="' + esc(w.path) + '"><b>' + esc(brWtName(w)) + '</b>'
          + '<i class="brf ' + (w.branch ? 'brl' : 'brh') + '">' + esc(w.branch || w.head || 'detached') + '</i>' + brBrSg(w.branch)
          + '<em>' + (ss.length ? esc(T('Sessions')) + ' ' + ss.length : '') + '</em></button>' + brWtMeta(w, ss)
          + (ss.length ? ss.map(brWsRow).join('') : '<div class=brwn>' + esc(T('No session is running in this worktree'))
            + (w.main ? '' : brWrmHtml(w)) + '</div>');
      }).join('') + '<div class=brwsep></div>';
}
function brPanBody(){ return brDet ? brDetHtml() : (brWu ? brWuHtml() : brWtHtml() + brTreeHtml()); }
// Branch folder tree (SourceTree-style): groups local / remote <remote>, names split on '/'.
// Open state per repo in UIS {nodeId: 1|0}; nodes absent there fall back to brTreeAuto.
let brMerge = true, brTreeSt = {}, brTreeFor = null;
brMerge = lsGet('sidereus.brmerge', null) !== '0';
function brTreeLoad(){
  if(brTreeFor === brRepo) return;
  brTreeFor = brRepo; brTreeSt = {};
  try { brTreeSt = JSON.parse(UIS.getItem('sidereus.brtree.' + brRepo) || '{}') || {}; } catch(e){ brTreeSt = {}; }
}
function brTreeSave(){ lsSetJson('sidereus.brtree.' + brRepo, brTreeSt); }
// Builds {id, label, kids:[], leaves:[], hot} nodes. Leaf = {b, pair (merged origin twin), label}.
function brTreeModel(){
  const bl = ((BR && BR.branches) || []).slice().sort((a, b) => (b.ts || 0) - (a.ts || 0));
  const hd = BR && !BR.detached ? (BR.head || '') : '';
  const wts = new Set(((BR && BR.worktrees) || []).map(w => w.branch).filter(Boolean));
  const recent = Date.now() / 1000 - 7 * 86400;
  const rem = new Map(); bl.forEach(b => { if(b.kind === 'remote') rem.set(b.name, b); });
  const used = new Set(), pairOf = new Map();
  if(brMerge) bl.forEach(b => {
    if(b.kind !== 'local') return;
    let r = b.upstream && rem.get(b.upstream);
    if(!r) for(const [n, v] of rem) if(!used.has(n) && n.slice(n.indexOf('/') + 1) === b.name){ r = v; break; }
    if(r && !used.has(r.name)){ used.add(r.name); pairOf.set(b.name, r); }
  });
  const groups = [], gm = new Map();
  const node = (id, label, parent) => { const n = { id: id, label: label, kids: [], km: new Map(), leaves: [], hot: false, n: 0 };
    if(parent){ parent.kids.push(n); parent.km.set(label, n); } return n; };
  const group = (id, label) => { let g = gm.get(id); if(!g){ g = node(id, label, null); gm.set(id, g); groups.push(g); } return g; };
  group('L', T('local'));
  bl.forEach(b => {
    if(used.has(b.name)) return;
    let g, rest;
    if(b.kind === 'remote'){ const k = b.name.indexOf('/'); const rn = k > 0 ? b.name.slice(0, k) : b.name;
      g = group('R:' + rn, T('remote') + ' ' + rn); rest = k > 0 ? b.name.slice(k + 1) : b.name; }
    else { g = group('L', T('local')); rest = b.name; }
    const parts = rest.split('/'), leafLab = parts.pop();
    const pair = pairOf.get(b.name) || null;
    const hot = b.name === hd || wts.has(b.name) || (b.ts || 0) >= recent || !!(pair && (pair.ts || 0) >= recent);
    const chain = [g];
    let cur = g;
    parts.forEach(p => { cur = cur.km.get(p) || node(cur.id + '/' + p, p, cur); chain.push(cur); });
    cur.leaves.push({ b: b, pair: pair, label: leafLab, hd: b.name === hd, wt: wts.has(b.name) });
    chain.forEach(n => { n.n++; if(hot) n.hot = true; });
  });
  // ★A group with no recent folder (2026-09-23, a repo with 44 branches all >7 days old) showed only closed folders + `L+R main`,
  //   read as "remote only, no branches". ⇒ In such a group open the top folders by default.
  groups.forEach(g => { if(!g.kids.some(k => k.hot)) g.kids.forEach(k => { k.auto = true; }); });
  return groups.filter(g => g.n || g.id === 'L');
}
function brTreeOpen(n, depth){ const v = brTreeSt[n.id]; return v === 1 ? true : v === 0 ? false : (depth === 0 || n.hot || !!n.auto); }
function brTreeHtml(){
  brTreeLoad();
  const all = (BR && BR.branches) || [];
  const gs = brTreeModel();
  const leaf = (x, depth) => {
    const b = x.b, p = x.pair;
    const sg = brSgHtml(b);
    const tip = b.name + (b.upstream ? ' → ' + b.upstream : '') + ' · ' + b.sha + (p ? ' · ' + T('local and remote merged into one row') + ' (' + p.name + ' · ' + p.sha + ')' : '');
    // ★The current branch is not visible by badge color alone in a list of 43 - it is surfaced by name and tag.
    return '<button class="brpr brtl' + (brSel === b.sha ? ' on' : '') + (x.hd ? ' hd' : '') + '" data-bb="' + esc(b.sha)
      + '" data-bn="' + esc(b.name) + '" role=treeitem aria-level=' + (depth + 1) + ' tabindex=0 style="padding-left:' + (3 + depth * 12) + 'px" title="' + esc(tip) + '">'
      + '<i class="brf ' + (b.kind === 'remote' ? 'brm' : 'brl') + (x.hd ? ' brh' : '') + '">' + (b.kind === 'remote' ? 'R' : (p ? 'L+R' : 'L')) + '</i>'
      + '<b>' + esc(x.label) + '</b>' + (x.hd ? '<span class=brhd>HEAD</span>' : '')
      + (x.wt ? '<span class=brtw title="' + esc(T('checked out in a worktree')) + '">wt</span>' : '') + sg
      + '<em>' + (b.ts ? agoAt(b.ts) : '') + '</em></button>';
  };
  const walk = (n, depth) => {
    const open = brTreeOpen(n, depth);
    let h = '<button class="brtf' + (depth ? '' : ' brtg') + '" data-bt="' + esc(n.id) + '" role=treeitem aria-level=' + (depth + 1) + ' tabindex=0 aria-expanded=' + open
      + ' style="padding-left:' + (3 + depth * 12) + 'px" title="' + esc(n.id.replace(/^R:/, '')) + '">'
      + '<i>' + (open ? '▾' : '▸') + '</i><b>' + esc(n.label + (depth ? '/' : '')) + '</b><em>' + n.n + '</em></button>';
    if(open) h += n.kids.map(k => walk(k, depth + 1)).join('') + n.leaves.map(x => leaf(x, depth + 1)).join('');
    return h;
  };
  return '<div class="hidnote brth">' + esc(T('Branches')) + ' ' + all.length + esc(T(' — click one to jump to its tip commit in the graph'))
    + '<button class="brmg' + (brMerge ? ' on' : '') + '" id=brmg aria-pressed=' + brMerge + ' title="'
    + esc(T('Show local X and origin/X as one row when both exist')) + '">' + esc(T('Merge local·remote')) + '</button>'
    + (all.length ? [['1', 'Expand all'], ['0', 'Collapse all']].map(t => '<button class="relfx brtall" data-bta=' + t[0] + '>' + esc(T(t[1])) + '</button>').join('') : '')
    + '</div>'
    + (all.length ? '<div class=brtree role=tree>' + gs.map(g => walk(g, 0)).join('') + '</div>'
      : '<div class=strpnl>' + esc(T('No branches here')) + '</div>');
}
// Toggle / set a node, repaint only the pane, keep keyboard focus on the same row.
function brTreeSet(id, open){
  brTreeLoad();
  const n = brTreeFind(id);
  const cur = n ? brTreeOpen(n.n, n.d) : false;
  const v = open == null ? !cur : open;
  if(v === cur) return;
  brTreeSt[id] = v ? 1 : 0; brTreeSave();
  brPanPaint(); brTreeFocus('[data-bt="' + CSS.escape(id) + '"]');
}
// «Expand all / Collapse all»: pin every folder (groups included) open/closed; ⚠pane + feed scrollTop restored by hand (clamped only when the content gets shorter).
function brTreeAll(open){
  brTreeLoad();
  const f = n => { brTreeSt[n.id] = open ? 1 : 0; n.kids.forEach(f); };
  brTreeModel().forEach(f); brTreeSave();
  const p = document.getElementById('brpan'), fd = document.getElementById('feed');
  const pt = p ? p.scrollTop : 0, ft = fd ? fd.scrollTop : 0;
  brPanPaint();
  if(p && document.body.contains(p)) p.scrollTop = pt;
  if(fd) fd.scrollTop = ft;
  brTreeFocus('[data-bta="' + (open ? 1 : 0) + '"]');
}
// Separate listener: #brpan's onclick lives in 88-branch.js; these buttons carry no data-bt so it ignores them.
document.addEventListener('click', e => {
  const b = e.target && e.target.closest && e.target.closest('#brpan [data-bta]');
  if(b) brTreeAll(b.dataset.bta === '1');
});
function brTreeFind(id){
  let hit = null;
  const f = (n, d) => { if(hit) return; if(n.id === id){ hit = { n: n, d: d }; return; } n.kids.forEach(k => f(k, d + 1)); };
  brTreeModel().forEach(g => f(g, 0));
  return hit;
}
function brTreeFocus(sel){ const p = document.getElementById('brpan'), el = p && p.querySelector(sel); if(el) el.focus({ preventScroll: true }); }
function brTreeKey(e){
  const t = e.target;
  if(!t || !t.closest || !t.closest('.brtree')) return;
  const f = t.closest('[data-bt]'), lf = t.closest('[data-bn]');
  if(e.key === 'ArrowRight' && f){ e.preventDefault(); brTreeSet(f.dataset.bt, true); }
  else if(e.key === 'ArrowLeft'){
    e.preventDefault();
    if(f && f.getAttribute('aria-expanded') === 'true') return brTreeSet(f.dataset.bt, false);
    // Leaf or closed folder: move to the parent folder row (previous row one level shallower).
    const rows = Array.from(document.querySelectorAll('#brpan .brtree > button')), i = rows.indexOf(f || lf);
    const pl = parseInt((f || lf).style.paddingLeft) || 0;
    for(let k = i - 1; k >= 0; k--) if(rows[k].dataset.bt && (parseInt(rows[k].style.paddingLeft) || 0) < pl){ rows[k].focus(); break; }
  } else if(e.key === 'ArrowDown' || e.key === 'ArrowUp'){
    e.preventDefault();
    const rows = Array.from(document.querySelectorAll('#brpan .brtree > button')), i = rows.indexOf(f || lf);
    const nx = rows[i + (e.key === 'ArrowDown' ? 1 : -1)]; if(nx) nx.focus();
  }
}
function brWuFetch(path){
  const f = brWuF = { path: path, st: 'load', j: null, msg: '' };
  fetch('/api/git/wtfiles?cwd=' + encodeURIComponent(path), { cache: 'no-store' })
    .then(r => r.json().catch(() => ({ ok: false })).then(j => ({ st: r.status, j: j || {} })))
    .then(o => { if(brWuF !== f) return;
        if(o.j.ok){ f.st = 'ok'; f.j = o.j; } else { f.st = 'err'; f.msg = brMsg(o.st, o.j); } },
      () => { if(brWuF === f){ f.st = 'err'; f.msg = T('Could not fetch — check the server'); } })
    .then(() => { if(brWuF === f && !brDet) brPanPaint(); });
  // Owners (who edited each uncommitted file) come separately; the file list never waits for them.
  getJSON('/api/git/owners?cwd=' + encodeURIComponent(path))
    .then(j => { if(brWuF === f && j && j.ok){ f.o = j; if(f.st === 'ok' && !brDet) brPanPaint(); } }, () => {});
}
// Owner chips for one uncommitted file. ⛔Metadata only: sid8, project, agent type, time.
function brWoHtml(o, path){
  const ow = (o && o.owners && o.owners[path]) || [];
  if(!ow.length) return '';
  const warn = (o.warn || []).includes(path);
  const chip = x => '<span style="margin-left:4px;padding:0 4px;border:1px solid currentColor;border-radius:6px;font-size:12px;'
    + (x.live ? '' : 'opacity:.55;') + '" title="' + esc(T('Edited by') + ': ' + x.sid8 + ' · ' + (x.proj || '') + (x.agent ? ' · ' + T('Subagents') + ' ' + x.agent : '')
    + ' · ' + AGO(U(Math.max(1, Math.round(x.ago / 60)), 'm')) + (x.live ? '' : ' · ' + T('Ended'))) + '">' + esc(x.sid8) + '</span>';
  return (warn ? '<span style="margin-left:4px;color:var(--nx-err,#d33)" title="' + esc(T('Conflict risk — two or more live sessions/subagents edited this file within {m} min')
      .replace('{m}', o.conflictMin || 30)) + '">⚠</span>' : '') + ow.slice(0, 4).map(chip).join('');
}
function brWuOpen(path){
  brWu = path; brDet = null; brSel = '';
  brWuFetch(path);
  brPanPaint();
}
// Sidebar "worktree: <name>" chip -> Branch tab with that worktree's work unit open (no other view reset).
function brWuJump(root, cwd){
  if(!(BR && BR.ok && brWtFind(root))){
    const x = (SESS || []).find(s => s && s.cwd === cwd) || {};
    const ps = brRepos(), has = p => p && ps.find(q => brNorm(q) === brNorm(p));
    const pick = has(x.wt && x.wt.main) || has(root) || has(cwd) || '';
    if(pick && pick !== brRepo){ brRepo = pick; BR = null; tabSet('mbBrRepo', brRepo); }
  }
  brDet = null; brSel = ''; brWu = root;
  if(brBoardOn){ brBoardOn = false; brBoardSave(); }   // ⚠a remembered Board sub-view would hide the jump target (as plOvPick)
  brWuFetch(root);
  if(mainView !== 'br') setMainView('br'); else loadBr(false);
}
// One /work popup with every session of this worktree, split by count (1 single, 2 side by side, 3 columns, 4 grid; first 4 only).
function brWuOpenAll(){
  const w = brWtFind(brWu), ss = w ? brWtSess(w.path).slice(0, 4) : [];
  if(!ss.length) return;
  const lay = ['1', '1', 'h2', 'c3', 'g4'][ss.length];
  let url = '/work?cwd=' + encodeURIComponent(ss[0].cwd) + '&tid=' + encodeURIComponent(brSessTid(ss[0]));
  if(ss.length > 1) url += '&lay=' + lay + '&more=' + encodeURIComponent(ss.slice(1).map(x => x.cwd + '\t' + brSessTid(x)).join('\n'));
  popOpen(url, popName('sidereus_wu_', w.path + '_' + ss.length), ss.length > 1 ? 1700 : 1100, ss.length > 3 ? 1100 : 800);
}
function brWuHtml(){
  const w = brWtFind(brWu);
  const back = '<div class=brdh><button class=brdb id=brwub>' + esc(T('← Branch list')) + '</button><b>'
    + esc(T('Work units')) + '</b></div>';
  if(!w) return back + '<div class="tlhd cwerr">' + esc(T("Not in this repo's worktree list")) + '</div>';
  const ss = brWtSess(w.path);
  // Recent commits of this worktree's HEAD: first-parent walk inside the fetched graph.
  const cms = (BR && BR.commits) || [], by = new Map();
  cms.forEach(c => by.set(c.sha, c));
  const hd = w.head || '';
  let c = hd ? cms.find(v => v.sha.indexOf(hd) === 0 || hd.indexOf(v.sha) === 0) : null;
  const walk = [];
  while(c && walk.length < 12){ walk.push(c); c = by.get((c.parents || [])[0]); }
  const cmH = walk.length ? walk.map(v => '<button class=brdf data-bpp="' + esc(v.sha) + '" title="' + esc((v.subject || '') + ' · ' + v.sha)
      + '"><b>' + esc(v.subject || '') + '</b><em>' + esc(v.sha) + (v.ts ? ' · ' + agoAt(v.ts) : '') + '</em></button>').join('')
    : '<div class=brwn>' + esc(T('This HEAD is not in the recent graph (80 commits)')) + '</div>';
  const sessH = ss.length ? ss.map(x => brWsRow(x) + (x.sub || []).filter(v => v && v.tid).map(v => {
      const lab = v.lab != null ? plStrip(String(v.lab)) : '';
      return '<div class=brwa data-wks="' + esc(x.cwd) + '" data-wkt="' + esc(v.tid) + '" title="' + esc(lab + ' — ' + T('Click to see what this subagent did')) + '">'
        + '<i>└</i><span>' + esc(lab) + '</span>' + (typeof v.min === 'number' ? '<em>' + (v.min < 1 ? esc(T('just now')) : U(v.min, 'm')) + '</em>' : '') + '</div>';
    }).join('')).join('')
    : '<div class=brwn>' + esc(T('No session is running in this worktree')) + '</div>';
  const f = brWuF && brNorm(brWuF.path) === brNorm(w.path) ? brWuF : null;
  const dc = ss.length ? ss[0].cwd : w.path;
  const fl = !f || f.st === 'load' ? '<div class=strload>' + esc(T('Reading changed files…')) + '</div>'
    : f.st !== 'ok' ? '<div class="tlhd cwerr">' + esc(f.msg || T('Could not fetch')) + '</div>'
    : (f.j.files || []).length ? (f.j.files || []).map(v => '<button class=brdf data-wkd="' + esc(dc) + '" title="' + esc(v.path) + '">' + fileIco(v.path) + '<b>'
        + esc(v.path) + '</b><em>' + esc(v.st) + brWoHtml(f.o, v.path) + '</em></button>').join('')
    : '<div class=brwn>' + esc(T('No uncommitted changes')) + '</div>';
  const nf = f && f.st === 'ok' ? ' ' + (f.j.n > (f.j.files || []).length ? f.j.files.length + '/' + f.j.n : f.j.n) : '';
  return back
    + '<div class=brds>' + esc(brWtName(w)) + '</div>' + brWtMeta(w, ss)
    + '<div class=brdk><i>' + esc(T('Path')) + '</i><span><code>' + esc(w.path) + '</code><button class=brdc data-cp="' + esc(w.path)
    + '" title="' + esc(T('Copy path')) + '">' + esc(T('Copy')) + '</button></span>'
    + '<i>' + esc(T('Branches')) + '</i><span>' + esc(w.branch || T('detached HEAD')) + brBrSg(w.branch) + '</span>'
    + '<i>HEAD</i><span><code>' + esc(hd || '?') + '</code></span></div>'
    + '<button class=brwall id=brwuall' + (ss.length ? '' : ' disabled') + ' title="'
    + esc(T("Open the work logs of this worktree's sessions split in one window (up to 4 panes)")) + '">' + esc(T('Open all work logs')) + '</button>'
    + '<div class=hidnote>' + esc(T('Sessions')) + ' ' + ss.length + ' · ' + esc(T('click for the work log')) + '</div>' + sessH
    + '<div class=hidnote>' + esc(T('Recent commits')) + ' ' + walk.length + ' · ' + esc(T('click for commit details')) + '</div>' + cmH
    + '<div class=hidnote>' + esc(T('Changed files (uncommitted)')) + nf + ' · ' + esc(T('click for the diff window')) + '</div>' + fl;
}
// Poll hook: keep session rows in the branch pane live. ⚠Skipped while hovered (a repaint mid-press eats the click).
function brWtTick(ord){
  brWtOrd = ord || {};
  if(mainView !== 'br' || brDet || !BR || !BR.ok) return;
  const p = document.getElementById('brpan');
  if(!p || p.matches(':hover')) return;
  if(brPanBody() !== brPanLast) brPanPaint();
}
document.addEventListener('keydown', e => {
  if(e.key !== 'Escape' || e.defaultPrevented || mainView !== 'br' || !(brDet || brWu)) return;
  const cm = document.getElementById('cfgm');
  if((cm && !cm.hidden) || document.querySelector('.cmdk.on')) return;
  if(brDet) return brClose();
  brWu = ''; brWuF = null; brPanPaint();
});
// ── Parallel work (docs/PARALLEL-WORK.md): copy-only commands. ⛔Sidereus never runs them — no endpoint, no POST.
let brPw = null;                        // null = form closed; {name, type, focus} while open (type 'w' = claude -w)
const BR_PW_RE = /^[a-z0-9._-]+$/;
const BR_PW_TYPES = ['feature', 'bugfix', 'release', 'hotfix'];
// git-flow from the server (sidereus/git.py flow_parse); an older payload without it gets the default prefixes.
function brPwFlow(){
  const f = (BR && BR.flow) || {}, pre = {};
  BR_PW_TYPES.forEach(t => { pre[t] = (f.prefix && f.prefix[t] != null) ? f.prefix[t] : t + '/'; });
  return { develop: f.develop || null, master: f.master || null, prefix: pre, src: f.src || 'default', devRemote: f.devRemote || null, mstRemote: f.mstRemote || null };
}
// Pure: branch/base/folder for a git-flow type. feature·bugfix·release branch from develop, hotfix from master.
function brPwPlan(type, name, flow, main){
  const noDev = type !== 'hotfix' && !flow.develop;
  const base = type === 'hotfix' || noDev ? (flow.master || 'HEAD') : flow.develop;
  // ⚠develop/master only as origin/<name> (fresh clone): base on the remote ref, --no-track so the new branch does not track it.
  const remote = !!((flow.devRemote && base === flow.develop) || (flow.mstRemote && base === flow.master));
  return { branch: flow.prefix[type] + name, base: base, noDev: noDev, remote: remote,
    folder: String(main || '').replace(/\/+$/, '') + '.wt/' + type + '-' + name };
}
function brPwCur(){ return brPw && brPw.type !== 'w' ? brPwPlan(brPw.type, brPw.name, brPwFlow(), brPwMain()) : null; }
// POSIX single-quote: the pasted command is parsed by the user's shell.
function brQ(s){ return "'" + String(s == null ? '' : s).replace(/'/g, "'\\''") + "'"; }
// Main checkout path (claude -w and worktree remove both run against it); falls back to the picked repo.
function brPwMain(){ const m = ((BR && BR.worktrees) || []).find(w => w.main); return (m && m.path) || (BR && BR.cwd) || brRepo || ''; }
// Pure: {ok, err, warn}. With a git-flow plan it checks that branch/folder; else claude -w's worktree-<name> and basename.
function brPwCheck(name, wts, brs, plan){
  if(!name) return { ok: false, err: 'Enter a name', warn: '' };
  if(/[A-Z]/.test(name) && BR_PW_RE.test(name.toLowerCase())) return { ok: false, err: 'Lowercase letters only', warn: '' };
  if(!BR_PW_RE.test(name)) return { ok: false, err: 'Only lowercase letters, digits and . _ - (blocks characters the shell would interpret)', warn: '' };
  // ⚠A leading '-' turns the name into an option: `claude -w -x` / `git worktree add ... -b -x`.
  if(!/^[a-z0-9]/.test(name)) return { ok: false, err: 'The name must start with a lowercase letter or a digit', warn: '' };
  if(/^\.|\.\.|\.$|\.lock$/.test(name)) return { ok: false, err: 'git rejects this name (leading/trailing ., .., .lock)', warn: '' };
  const nb = p => String(p || '').replace(/\/+$/, '');
  const wt = (wts || []).some(w => !w.main && (plan ? nb(w.path) === nb(plan.folder) : nb(w.path).split('/').pop() === name));
  const br = (brs || []).some(b => b.kind !== 'remote' && (plan ? b.name === plan.branch : (b.name === name || b.name === 'worktree-' + name)));
  return { ok: true, err: '', warn: wt ? 'A worktree with this name already exists' : br ? 'A branch with this name already exists' : '' };
}
// ⚠Every interpolated value is single-quoted: the folder carries the repo path (spaces, quotes).
function brPwCmd(name, plan){
  if(!plan) return 'cd ' + brQ(brPwMain()) + ' && claude -w ' + name + ' --tmux';
  return 'git -C ' + brQ(brPwMain()) + ' worktree add ' + (plan.remote ? '--no-track ' : '') + brQ(plan.folder) + ' -b ' + brQ(plan.branch) + ' ' + brQ(plan.base)
    + ' && cd ' + brQ(plan.folder) + ' && claude';
}
function brPwOk(){ return brPwCheck(brPw.name, BR && BR.worktrees, BR && BR.branches, brPwCur()); }
function brPwMsg(){
  const c = brPwOk(), p = brPwCur();
  // ⚠No error before the first keystroke / copy attempt: an empty name on open read as a mistake already made.
  if(!c.ok) return brPw.touched ? '<span class=brpwe>' + esc(T(c.err)) + '</span>' : '';
  return (p && p.noDev ? '<span class=brpww>' + esc(T('no develop — branching from {m}').replace('{m}', p.base)) + '</span>' : '')
    + (p && p.remote ? '<span class=brpww>' + esc(T('no local branch — branching from remote {m}').replace('{m}', p.base)) + '</span>' : '')
    + (c.warn ? '<span class=brpww>⚠ ' + esc(T(c.warn)) + ' — ' + esc(T('you can still copy')) + '</span>' : '')
    + '<code id=brpwcmd>' + esc(brPwCmd(brPw.name, p)) + '</code>';
}
function brPwHint(){
  return T(brPw.type === 'w' ? 'Paste it in a terminal: Claude Code creates the worktree and opens the session in a new window'
    : 'Paste it in a terminal: git creates the worktree and branch in a sibling folder, then Claude Code opens there');
}
function brPwHtml(){
  if(!brPw) return '';
  const f = brPwFlow();
  const opt = (v, lab) => '<option value="' + v + '"' + (brPw.type === v ? ' selected' : '') + '>' + esc(lab) + '</option>';
  return '<div class=brpw id=brpw><b>' + esc(T('Parallel work')) + '</b>'
    + '<select id=brpwt title="' + esc(T(f.src === 'gitflow-config' ? 'Follows the git flow init config' : 'No git-flow config — default prefixes (feature/ …)')) + '">'
    + BR_PW_TYPES.map(t => opt(t, t + ' (' + f.prefix[t] + ')')).join('') + opt('w', T('claude -w (from HEAD)')) + '</select>'
    + '<input id=brpwn spellcheck=false autocomplete=off maxlength=60 value="' + esc(brPw.name) + '" placeholder="'
    + esc(T('name (a-z 0-9 . _ -)')) + '">'
    + '<button class="brfc brpwc" id=brpwc' + (brPwOk().ok ? '' : ' disabled') + '>' + esc(T('Copy command')) + '</button>'
    + '<button class=brfc id=brpwx title="Esc">' + esc(T('Close')) + '</button>'
    + '<div class=brpwm id=brpwm>' + brPwMsg() + '</div>'
    + '<div class=brpwh id=brpwh>' + esc(brPwHint()) + '</div></div>';
}
function brPwUpd(){
  const m = document.getElementById('brpwm'), b = document.getElementById('brpwc'), h = document.getElementById('brpwh');
  if(m) m.innerHTML = brPwMsg();
  if(h) h.textContent = brPwHint();
  if(b) b.disabled = !brPwOk().ok;
}
// Clipboard in the click handler; on failure select the command text so the user can copy it by hand.
function brCmdCopy(cmd, sel){
  copyText(cmd).then(ok => {
    if(ok) return note(T('Copied — paste it in a terminal'));
    const el = sel && document.getElementById(sel);
    if(el){ const r = document.createRange(); r.selectNodeContents(el); const s = getSelection(); s.removeAllRanges(); s.addRange(r); }
    note(T('Could not copy — copy the command by hand') + ': ' + cmd);
  });
}
function brPwCopy(){
  if(!brPw) return;
  const c = brPwOk();
  if(!c.ok){ brPw.touched = 1; brPwUpd(); return note(T(c.err)); }
  brCmdCopy(brPwCmd(brPw.name, brPwCur()), 'brpwcmd');
}
function brPwWire(){
  const b = document.getElementById('brpwb');
  if(b) b.onclick = () => { brPw = brPw ? null : { name: '', type: 'feature', focus: 1 }; paintBr(); };
  const i = document.getElementById('brpwn');
  if(!i || !brPw) return;
  const t = document.getElementById('brpwt');
  if(t) t.onchange = () => { brPw.type = t.value; brPwUpd(); i.focus(); };
  i.oninput = () => { brPw.name = i.value; brPw.touched = 1; brPwUpd(); };
  i.onfocus = () => { brPw.focus = 1; };
  i.onblur = () => { if(brPw) brPw.focus = 0; };   // ⚠Esc nulls brPw, then the repaint blurs the removed input
  i.onkeydown = e => {
    if(e.key === 'Enter'){ e.preventDefault(); brPwCopy(); }
    else if(e.key === 'Escape'){ e.preventDefault(); brPw = null; paintBr(); }
  };
  const c = document.getElementById('brpwc'); if(c) c.onclick = brPwCopy;
  const x = document.getElementById('brpwx'); if(x) x.onclick = () => { brPw = null; paintBr(); };
  if(brPw.focus && document.activeElement !== i){ i.focus(); i.setSelectionRange(i.value.length, i.value.length); }   // full repaint keeps typing focus
}
// Cleanup command for a worktree card with no live session. ⚠Never --force: git refuses a dirty worktree, which is the point.
function brWrmHtml(w){
  const s = brWtSig(w) || {}, cmd = 'git -C ' + brQ(brPwMain()) + ' worktree remove ' + brQ(w.path);
  return '<button class="brfc brwrm" data-wrm="' + esc(cmd) + '" title="' + esc(cmd + '\n' + T('Copy only — Sidereus does not run it')) + '">'
    + esc(T('Cleanup cmd')) + '</button>'
    + (s.dirty ? '<span class=brwrw>' + esc(T('{n} uncommitted — removing loses them').replace('{n}', s.dirty)) + '</span>' : '');
}
