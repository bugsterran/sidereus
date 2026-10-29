// ── Timeline toolbar «Changes» chip: files changed vs the chosen baseline in the followed session's repo (view only, metadata only) ──
// Data: /api/git/diff?view=rail&base=<tlgBase> (numstat + base, no patch). Fetched by tlgTick only while the Timeline tab is shown.
// Click opens the diff window at the same baseline; file tree, other baselines, untracked files and repo tabs live there (35c diffShow).
// ★The right rail was removed: at 1100 it left the Gantt ~386px and hid most bar labels; one chip keeps the count at every width.
const TLG_TTL_S = 30;
let tlgSel = '';   // 's:'/'c:' cpKey (row click) or 'r:<repo>' (combo pick); '' = auto, latest active; kept across refresh by 97b (sidereus.tlgsel)
const tlgC = {};   // repo (session root, else cwd, or a `repos` path) -> {at, d, busy}
// ⚠★24 live repos measured, 0.07–0.13 s per rail fetch: every repo is fetched one at a time (tlgNext), so cap the list.
const TLG_MAX_REPOS = 30;
const TLG_NOGIT_TTL_S = 600;   // a folder that is not a repo rarely becomes one: recheck every 10 min, not every TTL
// Server reply for a folder outside git (git_view.git_diff «Not a git repository.»).
function tlgNoGit(d){ return !!(d && d.ok === false && /^Not a git repository/.test(String(d.msg || ''))); }
// Baseline = git_rail mode (Settings › Timeline «Changes baseline»). ⚠auto on a feature branch = since the default branch (hundreds of files).
const TLG_BASES = [['head', 'Uncommitted'], ['upstream', 'Unpushed'], ['start', 'Since session start'], ['remote', 'Since the default branch'], ['auto', 'Auto']];
let tlgBase = (v => TLG_BASES.some(x => x[0] === v) ? v : 'head')(lsGet('sidereus.tlgbase', 'head'));
function tlgBaseSet(v){
  if(!TLG_BASES.some(x => x[0] === v)) return;
  tlgBase = v; lsSet('sidereus.tlgbase', v);
  for(const k of Object.keys(tlgC)) delete tlgC[k];   // replies are per baseline; an in-flight one lands on its detached entry
  const tg = tlgTarget();
  if(tg && mainView === 'time') tlgFetch(tg, true);
  tlgPaint();
}
// Tooltip line naming what the count is compared with (rail reply fields only: baseKind · baseRef · base · nCommits · branch).
function tlgBaseTip(d){
  if(!d || !d.ok) return '';
  const v = {b: d.branch || '', r: d.baseRef || '', s: String(d.base || '').slice(0, 7), n: d.nCommits || 0};
  const k = d.baseKind;
  const msg = k === 'start' ? 'Compared with: {b} at session start ({s}), {n} commits'
    : k === 'branch' ? 'Compared with: the default branch {r} (merge-base {s}), {n} commits'
    : k === 'remote' ? 'Compared with: {r} (merge-base {s}), {n} commits'
    : v.b ? 'Compared with: uncommitted changes on {b}' : 'Compared with: uncommitted changes';
  let t = TV({msg: msg, vars: v});
  if(k === 'head' && d.baseMode && d.baseMode !== 'head') t += '\n' + T('No such baseline here — showing uncommitted changes');
  else if(d.noRemote) t += '\n' + T('No remote branch — compared with the session start');
  return t;
}
// Chip badge: the EFFECTIVE baseline from the reply (server may fall back), else the chosen mode; warn = chosen mode not honoured.
const TLG_KIND = {head: 'head', start: 'start', branch: 'remote', remote: 'upstream'};
function tlgBaseText(d){
  const k = d && d.ok ? (TLG_KIND[d.baseKind] || 'head') : tlgBase;
  return T((TLG_BASES.find(x => x[0] === k) || TLG_BASES[0])[1], 'base');
}
function tlgBaseLabel(d){
  const warn = !!(d && d.ok && ((d.baseKind === 'head' && d.baseMode && d.baseMode !== 'head') || d.noRemote));
  return '<span class="tlgbk' + (warn ? ' tlgbkw' : '') + '">' + esc(tlgBaseText(d)) + '</span>';
}
// Untracked files (server `new:True`) never count — scratch files read as changes. Same rule for files, +a and −d.
function tlgShownN(d){ return Math.max(0, (d.n || 0) - (d.untracked || (d.files || []).filter(f => f.new).length)); }
function tlgNum(a, d){ return '<span class=tlga>+' + a + '</span><span class=tlgd>−' + d + '</span>'; }
// Tracked files another live session also edited within 30 min (server `conflict`): paths only, never owners or content.
function tlgShared(d){ return (d.files || []).filter(f => f.conflict && !f.new).map(f => String(f.path || '')); }
// Combobox rows: SESS sessions with a cwd, most recently active first (project name breaks ties).
// ⚠Sessions carry `ageSec`, not `idle` — sessByIdle (bgs rows) left this list in server order.
function tlgAge(x){ return typeof x.ageSec === 'number' ? x.ageSec : 1e12; }
function tlgName(x){ return String(x.project || x.cwd || ''); }
function tlgSessions(){
  return (SESS || []).filter(x => x && x.cwd).sort((p, q) => (tlgAge(p) - tlgAge(q)) || tlgName(p).localeCompare(tlgName(q)));
}
function tlgSid(x){ return (x.plat || 'cc') === 'cc' ? (x.sid || '') : ''; }
// Repos to count: each live session's own repo (fetched via its cwd, which the server allow-list holds) then its `repos`
// (gitinfo.session_repos: worktrees and other repos it edited), deduped by path, most recently active session first.
function tlgRepos(){
  const out = [], by = {};
  for(const x of tlgSessions()){
    [[x.root || x.cwd, x.cwd]].concat((x.repos || []).map(p => [p, p])).forEach(([ck, cwd]) => {
      if(!ck || typeof ck !== 'string') return;
      let e = by[ck];
      if(!e){ e = by[ck] = {ck, cwd, sid: tlgSid(x), ss: []}; out.push(e); }
      if(e.ss.indexOf(x) < 0) e.ss.push(x);
    });
  }
  return out.slice(0, TLG_MAX_REPOS);
}
// Followed repo: the picked repo or session, else (auto, or the pick disappeared) the most recently active session's repo.
// `mine` = repos of the followed session only (its own + its `repos`): the chip list, its badge and the fetch queue.
let tlgSelS = '';   // cpKey of the session a chip repo pick was made from (not kept across reload: falls back to the repo's latest session)
function tlgTarget(){
  const all = tlgSessions(), repos = tlgRepos();
  let row = null, rp = null;
  if(tlgSel.indexOf('r:') === 0) rp = repos.find(e => 'r:' + e.ck === tlgSel) || null;
  else if(tlgSel) row = all.find(x => cpKey(x) === tlgSel) || null;
  if(tlgSel && !row && !rp && all.length) tlgSel = '';   // ⚠not before the first /api/state (SESS = []) — a restored pick would be wiped
  const how = row || rp ? 'pick' : 'auto';
  if(rp) row = rp.ss.find(x => cpKey(x) === tlgSelS) || rp.ss[0];
  row = row || all[0];
  if(!row) return null;
  const mine = repos.filter(e => e.ss.indexOf(row) >= 0);
  if(rp) return {cwd: rp.cwd, row, how, all, repos, mine, key: 'r:' + rp.ck, ck: rp.ck, sid: rp.sid};
  const ck = row.root || row.cwd;
  return {cwd: row.cwd, row, how, all, repos, mine, key: 'r:' + ck, ck, sid: tlgSid(row)};
}
// Timeline row/bar/name click: the chip follows that session (by the row's sid, else its cwd+platform); a past session
// with no SESS entry follows only when its cwd is one of the listed repos, otherwise the chip stays where it was.
function tlgFollow(cwd, plat, tid){
  const all = tlgSessions(), m = /^(?:sess|ext):.*\|([^|]+)$/.exec(String(tid || ''));
  const row = (m && all.find(x => x.sid === m[1])) || all.find(x => x.cwd === cwd && (x.plat || 'cc') === (plat || 'cc'));
  const rp = row ? null : tlgRepos().find(e => e.ck === cwd || e.cwd === cwd);
  const k = row ? cpKey(row) : rp ? 'r:' + rp.ck : '';
  if(!k || k === tlgSel) return;
  tlgSel = k; tlgKeepSave(); tlgTick();
}
// Session combobox (08b ppComboHtml, same as Pipelines/Structure/Branches), only when there is a choice (2+ sessions).
// Rows are project · sid · state, tooltip cwd · sid (metadata only); the first row 'auto' = tlgSel '' (follow the latest active).
// ⚠Two combos: this session button ('tlgs') and the chip's repo list ('tlgr', tlgRepoCfg) — never point the chip at 'tlgs'.
const TLG_AUTO = 'auto';   // ⚠never a cpKey ('s:'/'c:' prefix), so 97b cannot restore it as a pick
function tlgProj(x){ return x.project || x.cwd.split('/').pop() || x.cwd; }
function tlgNote(x){ return [x.sid ? sid8(x.sid) : '', x.state ? (stateLbl(x.state) || T(x.state)) : ''].filter(Boolean).join(' · '); }
function tlgRepoName(p){ return String(p).split('/').filter(Boolean).pop() || String(p); }
function tlgSelHtml(tg){
  if(!tg || tg.all.length < 2) return '';
  const AL = T('Auto (latest active)', 'chip');
  const it = x => ({ p: cpKey(x), name: tlgProj(x), note: tlgNote(x), tip: x.cwd + (x.sid ? ' · ' + sid8(x.sid) : '') });   // short id like every other view; a 36-char uuid read as noise
  const items = [Object.assign(it(tg.all[0]), { p: TLG_AUTO, auto: true })].concat(tg.all.map(it));
  const cur = tg.how === 'auto' ? TLG_AUTO : cpKey(tg.row);
  const row = (e, i) => '<div class="cmdki' + (PPS && i === PPS.i ? ' on' : '') + (e.p === cur ? ' ppcur' : '') + '" role=option data-ppi="' + i + '" title="' + esc(e.tip) + '">'
    + '<span class=cmdkp>' + esc(e.auto ? AL : e.name) + '</span><span class=cmdkc>' + esc(e.auto ? [e.name, e.note].filter(Boolean).join(' · ') : e.note) + '</span></div>';
  const flat = q => {
    const s = String(q || '').trim().toLowerCase();
    return items.filter(e => !s || [e.name, e.tip, e.auto ? AL : ''].some(v => String(v).toLowerCase().includes(s)));
  };
  return ppComboHtml({ k: 'tlgs', label: T('Session'), bare: true, items: items, cur: cur, ph: T('Find a session'), empty: T('No matching sessions'), flat: flat, rowHtml: row,
    tip: e => (e.auto ? AL + '\n' : '') + e.tip, badge: e => e.auto ? '<span class=tlgau>' + esc(T('auto', 'mark')) + '</span>' : '',
    pick: p => { tlgSel = p === TLG_AUTO ? '' : p; tlgKeepSave(); tlgTick(); } });
}
// Chip repo list (no button of its own; the chip opens it): the followed session's repos only (tg.mine), with counts;
// repos with changes first, not yet fetched next, clean (0 files) last and greyed. Registered in PPC so ppOpen/ppPick work.
function tlgRepoCfg(tg){
  if(!tg || tg.mine.length < 2) return null;
  const it = e => {
    const x = e.ss[0], own = (x.root || x.cwd) === e.ck, c = tlgCnt((tlgC[e.ck] || {}).d);
    return { p: 'r:' + e.ck, name: tlgRepoName(e.ck), c, ng: tlgNoGit((tlgC[e.ck] || {}).d), note: [own ? '' : tlgProj(x), tlgNote(x), e.ss.length > 1 ? '+' + (e.ss.length - 1) : ''].filter(Boolean).join(' · '),
      tip: e.ck + '\n' + e.ss.map(s => tlgProj(s) + (s.sid ? ' · ' + s.sid : '')).join('\n') };
  };
  const rank = e => e.c ? (e.c.n ? 0 : 2) : e.ng ? 3 : 1;
  const items = tg.mine.map(it).map((e, i) => [e, i]).sort((p, q) => (rank(p[0]) - rank(q[0])) || (p[1] - q[1])).map(v => v[0]);
  const cur = tg.key, rk = cpKey(tg.row), own = 'r:' + (tg.row.root || tg.row.cwd), wasAuto = tg.how === 'auto';
  const cnt = c => c ? '<span class=tlgcn>' + esc(TV({msg: c.n === 1 ? '{n} file' : '{n} files', vars: {n: c.n}}) + ' ') + tlgNum(c.a, c.dl) + '</span>' : '';
  const row = (e, i) => '<div class="cmdki' + (PPS && i === PPS.i ? ' on' : '') + (e.p === cur ? ' ppcur' : '') + ((e.c && !e.c.n) || e.ng ? ' tlg0' : '') + '" role=option data-ppi="' + i + '" title="' + esc(e.tip) + '">'
    + '<span class=cmdkp>' + esc(e.name) + '</span>' + (e.ng ? '<span class=tlgcn>' + esc(T('No git', 'repo')) + '</span>' : cnt(e.c)) + '<span class=cmdkc>' + esc(e.note) + '</span></div>';
  const flat = q => {
    const s = String(q || '').trim().toLowerCase();
    return items.filter(e => !s || [e.name, e.tip].some(v => String(v).toLowerCase().includes(s)));
  };
  // Picking the session's own repo returns to following the session (auto stays auto); another repo pins it.
  const cfg = { k: 'tlgr', label: T('Repository'), items: items, cur: cur, ph: T('Find a repository'), empty: T('No matching repositories'), flat: flat, rowHtml: row,
    pick: p => { tlgSelS = rk; tlgSel = p === own ? (wasAuto ? '' : rk) : p; tlgKeepSave(); tlgTick(); },
    foot: { html: esc(T('View all changes')) + ' <span class=ppfootn>' + esc(tlgRepoName(tg.ck)) + '</span>', act: tlgOpen } };
  PPC.tlgr = cfg;
  return cfg;
}
// «[baseline] N files +a −d» (+ «· ⚠ n shared»); no target or no reply yet = «[baseline] Changes».
// ⚠The word «Changes» is dropped beside counts so the head holds one line at 1100; it stays the aria name and first tooltip line.
// Shown counts of one rail reply (untracked left out), or null before an ok reply.
function tlgCnt(d){
  if(!d || !d.ok) return null;
  const hid = (d.files || []).filter(f => f.new), sum = k => hid.reduce((s, f) => s + (f[k] || 0), 0);
  return {n: tlgShownN(d), a: Math.max(0, (d.add || 0) - sum('add')), dl: Math.max(0, (d.del || 0) - sum('del'))};
}
function tlgChipInner(tg){
  const d = tg && (tlgC[tg.ck] || {}).d, CH = T('Changes', 'chip');
  let body = tlgBaseLabel(d), aria = [CH, tlgBaseText(d)];
  if(d && d.ok){
    const c = tlgCnt(d), a = c.a, dl = c.dl, nf = TV({msg: c.n === 1 ? '{n} file' : '{n} files', vars: {n: c.n}});
    body += esc(nf + ' ') + tlgNum(a, dl);
    aria.push(nf + ' +' + a + ' −' + dl);
    const sh = tlgShared(d);
    if(sh.length){
      const st = TV({msg: '{n} shared', vars: {n: sh.length}});
      body += '<span class=tlgsh title="' + esc(T('Also edited by another live session within 30 min:') + '\n' + sh.join('\n')) + '">' + esc(' · ⚠ ' + st) + '</span>';
      aria.push('⚠ ' + st);
    }
  } else body += esc(CH);
  // Chip opens the session's repo list (data-ppo keeps 08b's outside-click from closing it before the toggle); 1 repo = no list, so the diff.
  const ls = !!tlgRepoCfg(tg), ex = !!(ls && PPS && PPS.cfg.k === 'tlgr'), nd = ls ? tlgDirty(tg).length : 0;
  // ⚠The badge names its noun («3 repos»): a bare «3곳» next to the baseline read as a count of the baseline itself.
  if(nd){ const rt = TV({msg: 'Repositories with uncommitted changes: {n}', vars: {n: nd}});
    body += '<span class=tlgnb title="' + esc(rt) + '">' + esc(TV({msg: '{n} repos', vars: {n: nd}})) + '</span>'; aria.push(rt); }
  const bt = tlgBaseTip(d);
  const tip = CH + '\n' + (ls ? T("Show this session's repositories with their changes") : T('Open the changes in the diff window (git · view only)')) + (bt ? '\n' + bt : '') + (tg ? '\n' + tg.cwd : '');
  return tlgSelHtml(tg) + '<button type=button class="tlrf tlgcp" id=tlgcp' + (tg ? '' : ' disabled') + (ls ? ' data-ppo aria-haspopup=listbox aria-controls=ppop aria-expanded="' + ex + '"' : '') + ' aria-label="' + esc(aria.join(' · ')) + '" title="' + esc(tip) + '">' + body + '</button>';
}
// Every repo of the followed session (followed one included) with ≥1 tracked changed file, most files first; untracked never count (tlgCnt).
function tlgDirty(tg){
  if(!tg) return [];
  const rs = tg.mine.some(e => e.ck === tg.ck) ? tg.mine : [{ck: tg.ck, cwd: tg.cwd, sid: tg.sid}].concat(tg.mine);
  return rs.map(e => ({e, c: tlgCnt((tlgC[e.ck] || {}).d)})).filter(x => x.c && x.c.n > 0).sort((p, q) => q.c.n - p.c.n);
}
function tlgChipHtml(){ return '<span class=tlgb id=tlgb>' + tlgChipInner(tlgTarget()) + '</span>'; }
// Id of the focused chip control, or ''. paintTl and tlgPaint refocus it after a rebuild.
function tlgFocusId(){
  const ae = document.activeElement;
  return ae && ae.id === 'tlgcp' ? ae.id : '';
}
// paintTl rebuilds #feed (head included): keep the old group while the session picker is open (its opener) or holds focus.
function tlgKeep(box){
  const og = box.querySelector ? box.querySelector('#tlgb') : null, ae = document.activeElement;
  const fo = !!(og && ae && og.contains(ae));
  return {el: og && (popIsOpen('ppop') || fo) ? og : null, ae: fo ? ae : null, id: tlgFocusId()};
}
function tlgRestore(k){
  const nw = document.getElementById('tlgb');
  if(k && k.el && nw && nw !== k.el) nw.replaceWith(k.el);   // ⚠a detached node loses focus; refocused below
  const f = k && (k.ae || (k.id && document.getElementById(k.id)));
  if(f && f.focus) f.focus({preventScroll: true});
  tlgWire();
}
function tlgPaint(){
  const el = document.getElementById('tlgb');
  if(!el) return;
  if(popIsOpen('ppop')) return;   // ⚠a repaint would replace the session picker's opener under its popover
  const fo = tlgFocusId();
  if(!setHtml(el, tlgChipInner(tlgTarget()))) return;
  if(fo){ const f = document.getElementById(fo); if(f) f.focus({preventScroll: true}); }
  tlgWire();
}
function tlgFetch(tg, force){
  const c = tlgC[tg.ck] || (tlgC[tg.ck] = {at: 0, d: null, busy: false});
  if(c.busy || (!force && Date.now() - c.at < TLG_TTL_S * 1000)) return;
  c.busy = true;
  getJSON('/api/git/diff?view=rail&cwd=' + encodeURIComponent(tg.cwd) + '&base=' + encodeURIComponent(tlgBase) + (tg.sid ? '&sid=' + encodeURIComponent(tg.sid) : ''))
    .then(j => { c.d = j; }, () => { if(!c.d) c.d = {ok: false}; })
    .then(() => { c.at = Date.now(); c.busy = false; tlgPaint(); tlgNext(); });
}
// One rail fetch in flight at a time: the followed repo first, then the followed session's other repos older than TLG_TTL_S.
function tlgNext(){
  if(mainView !== 'time' || document.hidden) return;
  if(Object.keys(tlgC).some(k => tlgC[k].busy)) return;
  const tg = tlgTarget();
  if(!tg) return;
  const now = Date.now(), e = [tg].concat(tg.mine).find(r => { const c = tlgC[r.ck]; return !c || now - c.at >= (tlgNoGit(c.d) ? TLG_NOGIT_TTL_S : TLG_TTL_S) * 1000; });
  if(e) tlgFetch(e);
}
// Called from poll() (2.5 s) and the tab switch; fetches at most once per TLG_TTL_S per repo, only while the Timeline is shown and visible.
function tlgTick(){
  if(mainView !== 'time' || document.hidden) return;
  tlgNext();
  tlgPaint();
}
// List foot «View all changes» -> the existing diff window (repo tabs) at the chip's baseline; &sid lets that window offer «Since session start».
function tlgOpen(){ tlgOpenRepo(tlgTarget()); }
// Chip click: the session's repo list under the chip, else (one repo) the diff window.
function tlgChipClick(b){
  const c = PPC.tlgr;
  if(c && b.hasAttribute('data-ppo')) ppOpen(c, b); else tlgOpen();
}
// Diff window on one repo at the baseline its rail reply used.
function tlgOpenRepo(r){
  if(!r) return;
  const d = (tlgC[r.ck] || {}).d;
  loadDiff(r.cwd, '', d && d.ok && d.base ? 'b:' + d.base : 'work', '', r.sid);
}
function tlgWire(){
  const b = document.getElementById('tlgcp');
  if(b) b.onclick = () => tlgChipClick(b);   // Enter/Space on a <button> fire click
}
