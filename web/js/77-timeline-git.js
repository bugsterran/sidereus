// ── Timeline right rail: files changed vs a baseline in the chosen session's repo (view only, metadata only) ──
// Data: /api/git/diff?view=rail&base=<mode>&sid= (numstat + base + branch header + commits, no patch). Polled from poll() only while open.
// TLG_MIN_W matches the CSS hide (22-timeline-git.css max-width:1099px). TLG_AUTO_W = default-open floor:
// ★10-06 at 1100 the 400px rail left the Gantt 386px (narrower than 900's 600px, 16/21 bar labels hidden).
// ⚠Do not raise TLG_MIN_W instead — tlgTick would stop fetching for a rail the user opened at 1100-1299 (stuck on «Loading…»).
const TLG_TTL_S = 10, TLG_MIN_W = 1100, TLG_AUTO_W = 1300;
// Other repos of a multi-repo session are fetched only to know whether their chip is clean (R1) — slower TTL, at most TLG_BG_MAX.
const TLG_BG_TTL_S = 30, TLG_BG_MAX = 6;
// Same attributes a11yOne (98-a11y.js) would add; emitted here so each #tlgit repaint (~39 rows) costs no a11y attribute writes.
// ⚠Only on cursor:pointer targets outside a/button/label — a11yOne skips everything else, so tagging more would change the tab order.
const TLG_KB = ' tabindex=0 role=button data-kb';
// ★Default on at >= TLG_AUTO_W (closed-by-default read as not shipped); an explicit '1'/'0' wins at any width.
let tlgOn = (() => { const v = lsGet('sidereus.tlgit', ''); return v === '1' || (v !== '0' && window.innerWidth >= TLG_AUTO_W); })();
// ★Session combobox replaces hover-follow and the pin chip.
let tlgSel = '', tlgRepoSel = {key: '', repo: '', all: false};   // tlgSel: chosen cpKey ('' = auto); kept across refresh by 97b (sidereus.tlgsel)
// ★Base defaults to the last commit; the others are options. Kept by 97b.
const TLG_MODES = [['head', 'Last commit'], ['start', 'Since session start'], ['remote', 'vs main / master'], ['upstream', 'vs this branch\'s remote']];
// ★'auto' until the user picks: the server resolves it to remote when the repo has a remote, else head.
let tlgMode = 'auto';
// Untracked files (server `new:True`) are hidden unless this UIS pref is '1' — scratch files cluttered the tree.
let tlgUntr = lsGet('sidereus.tlgUntr', '') === '1';
function tlgShown(files){ return tlgUntr ? files : files.filter(f => !f.new); }
// Shown-file count: the header and the repo chips share it so they cannot disagree. Hidden untracked leave the total.
function tlgShownN(d){ return Math.max(0, (d.n || 0) - (tlgUntr ? 0 : (d.untracked || (d.files || []).filter(f => f.new).length))); }
// Checkbox row + «N hidden» link (clicking it turns the checkbox on). Pure: tests call it with a files array.
function tlgUntrHtml(files){
  const nh = tlgUntr ? 0 : files.filter(f => f.new).length;
  return '<div class=tlgun><label class=tlgunl><input type=checkbox id=tlgun' + (tlgUntr ? ' checked' : '') + '> '
    + esc(T('Include untracked files')) + '</label>'
    + (nh ? '<em class=tlgunh' + TLG_KB + ' data-tgu title="' + esc(T('Click to show untracked files')) + '">'
      + esc(T('{n} untracked hidden').replace('{n}', String(nh))) + '</em>' : '') + '</div>';
}
function tlgShownMode(tg){
  if(tlgMode !== 'auto') return tlgMode;
  const d = (tlgC[tg.ck] || {}).d;
  return (d && d.baseMode) || 'head';
}
const tlgC = {};            // repo + '\0' + sid -> {at, d, busy}
const tlgShut = new Set();  // collapsed folders: cwd + '\0' + dir
function tlgSt(st){
  const m = {A:['a','added'], M:['m','modified'], D:['d','deleted'], R:['r','renamed'], U:['u','unmerged']};
  const v = m[st] || m.M;
  return {k: m[st] ? st : 'M', cls: v[0], en: v[1]};
}
// files [{path, st, add, del, bin, old}] -> folder tree with per-folder sums; single-child folder chains are merged.
function tlgTree(files){
  return pathTree(files || [], {sort: 'seg', leafSort: (a, b) => a.name < b.name ? -1 : (a.name > b.name ? 1 : 0),
    node: (name, path) => ({name: name, path: path, dirs: [], files: [], add: 0, del: 0, n: 0}),
    add: (d, f) => { d.add += f.add || 0; d.del += f.del || 0; d.n++; },
    split: f => { const p = String(f.path || '').split('/'), name = p.pop(); return [p, Object.assign({}, f, {name, st: tlgSt(f.st).k})]; }});
}
// Middle truncation: the tail stays whole, the head gets the ellipsis.
function tlgMid(s){
  s = String(s);
  const k = Math.min(10, Math.floor(s.length / 2));
  return '<span class=tlgnh>' + esc(s.slice(0, s.length - k)) + '</span><span class=tlgnt>' + esc(s.slice(s.length - k)) + '</span>';
}
function tlgNum(a, d, bin){
  if(bin) return '<span class=tlgbin>' + esc(T('binary')) + '</span>';
  return '<span class=tlga>+' + a + '</span><span class=tlgd>−' + d + '</span>';
}
// Who edited a file (server `own`, latest first): a muted second line under the name (latest editor + count, full list in the title); «Conflict» = 2+ live sessions.
// ★Second line, not an inline chip (the inline chip squeezed names in the 300px rail to «test_a… op_runs.py»).
function tlgOwnLab(o){ return o.main ? T('Main session', 'git') : (plStrip(o.lab) || o.agent || 'agent'); }
function tlgOwnHtml(f){
  const own = f.own || [];
  if(!own.length) return '';
  const now = Math.floor(Date.now() / 1000);
  const tip = own.map(o => o.sid8 + ' · ' + tlgOwnLab(o) + ' · ' + U(o.n, '×') + ' · ' + agoAt(now - (o.ago || 0))).join('\n');
  const o = own[0], more = own.length > 1 ? ' +' + (own.length - 1) : '';
  return '<div class="tlgol' + (o.main ? ' main' : '') + '"' + TLG_KB + ' title="' + esc(T('Edited by — click for the work log') + '\n' + tip) + '">'
    + (f.conflict ? '<span class=tlgcf' + TLG_KB + ' title="' + esc(T('Another live session edited this file within 30 min — click for the list') + '\n' + tip) + '">' + esc(T('Conflict')) + '</span>' : '')
    + '<span class=tlgow>' + esc(tlgOwnLab(o)) + '</span><b>' + esc('· ×' + o.n + more) + '</b></div>';
}
// Owner line click -> the existing work popup (wkPopup): agent -> "<toolUseId>|<sid>", main or unresolved agent -> "sess:<cwd>|<sid>".
function tlgOwnOpen(o){
  if(!o || !o.cwd) return;
  wkPopup(o.cwd, !o.main && o.tid ? o.tid + '|' + o.sid : 'sess:' + o.cwd + (o.sid ? '|' + o.sid : ''));
}
// «Conflict» click -> small popover (08-ui-kit popGet/popReg: body-level, so rail repaints do not wipe it; shared outside-click/Esc).
// One row per session; a row on screen picks that session in #tlgss.
function tlgCfClose(){ popHide('tlgcfp'); }
popReg('tlgcfp', '#tlgcfp, .tlgcf', tlgCfClose);
function tlgCfOpen(f, anchor){
  const p = popGet('tlgcfp', 'thpop tlgcfp');
  if(!p.hidden && p._a === anchor) return tlgCfClose();   // second click on the same chip toggles it shut
  const tg = tlgTarget(), by = {};
  for(const o of f.own || []) if(o.sid && !by[o.sid]) by[o.sid] = o;     // own is latest first: first unit = session's latest
  const keys = new Set(((tg && tg.all) || []).map(cpKey));
  p._a = anchor;
  p.innerHTML = '<div class=tlgcfh>' + esc(T('Sessions that edited this file')) + '</div>'
    + Object.values(by).map(o => {
      const ok = keys.has('s:' + o.sid);
      return '<div class="tlgcfr' + (ok ? '' : ' off') + '" data-cfs="' + esc(o.sid) + '" title="' + esc(o.cwd + ' · ' + o.sid
        + (ok ? '' : '\n' + T('Session not on screen'))) + '"><b>' + esc(o.proj || '?') + '</b><span>'
        + esc(o.sid8) + '</span><em>' + esc(tlgOwnLab(o)) + '</em></div>';
    }).join('');
  popAnchor(p, anchor);
  p.onclick = e => {
    const row = e.target.closest('[data-cfs]');
    if(!row || row.classList.contains('off')) return;
    tlgSel = 's:' + row.dataset.cfs;
    tlgKeepSave();
    tlgCfClose();
    tlgTick();
  };
}
function tlgFileOf(tg, path){ const d = (tlgC[tg.ck] || {}).d; return ((d && d.files) || []).find(x => x.path === path); }
function tlgTreeHtml(node, depth, cwd){
  let out = '';
  for(const c of node.dirs){
    const key = cwd + '\0' + c.path, shut = tlgShut.has(key);
    out += '<div class="tlgr tlgdir"' + TLG_KB + ' data-tgd="' + esc(c.path) + '" style="padding-left:' + (depth * 12 + 4) + 'px" title="' + esc(c.path + '/') + '">'
      + '<span class=tlgar>' + (shut ? '▸' : '▾') + '</span><span class=tlgnm>' + tlgMid(c.name + '/') + '</span>'
      + '<span class=tlgc>' + c.n + '</span>' + tlgNum(c.add, c.del) + '</div>';
    if(!shut) out += tlgTreeHtml(c, depth + 1, cwd);
  }
  for(const f of node.files){
    const s = tlgSt(f.st);
    const tip = (f.old ? f.old + ' → ' : '') + f.path + ' · ' + T(s.en, 'git');
    // Status is carried by the name colour (added blue, modified/renamed green, deleted grey); the
    // text form stays in title/aria-label for screen readers and colour-blind users.
    const ow = tlgOwnHtml(f);
    out += '<div class="tlgr tlgf tlgf-' + s.cls + (ow ? ' tlgfw' : '') + '"' + TLG_KB + ' data-tgf="' + esc(f.path) + '" style="padding-left:' + (depth * 12 + 16) + 'px" title="' + esc(tip) + '" aria-label="' + esc(tip) + '">'
      + fileIco(f.name) + '<span class=tlgnm>' + tlgMid(f.name) + '</span>'
      + tlgNum(f.add, f.del, f.bin) + ow + '</div>';
  }
  return out;
}
// «Expand all / Collapse all»: every folder key of the shown tree in/out of tlgShut, so poll repaints keep it like single toggles.
function tlgFoldAll(t, cwd, open){
  const walk = n => n.dirs.forEach(c => { const k = cwd + '\0' + c.path; if(open) tlgShut.delete(k); else tlgShut.add(k); walk(c); });
  walk(t);
  return t.dirs.length;
}
// Tree of the shown files, built once per file list (keyed by the d.files object + tlgUntr) and shared by paint and fold-all.
// ⚠Consumers must not mutate the returned tree — it is reused across repaints until the next fetch.
let tlgTreeMemo = null;
function tlgShownTree(files){
  const m = tlgTreeMemo;
  if(m && m.files === files && m.untr === tlgUntr) return m.t;
  tlgTreeMemo = {files, untr: tlgUntr, t: tlgTree(tlgShown(files))};
  return tlgTreeMemo.t;
}
function tlgFoldBtns(t){
  if(!t.dirs.length) return '';
  return [['1', 'Expand all'], ['0', 'Collapse all']].map(t => '<button type=button class="relfx tlgfa" data-tga=' + t[0] + '>' + esc(T(t[1])) + '</button>').join('');
}
// Repos a session covers = its cwd + `repos` of every SESS row with that cwd (cwd first, deduped; same union as strProjs).
function tlgRepos(cwd){
  const out = [cwd];
  for(const s of SESS || []) if(s && s.cwd === cwd) for(const r of s.repos || []) if(r && out.indexOf(r) < 0) out.push(r);
  return out;
}
// Combobox rows: SESS sessions with a cwd, most recently active first (project name breaks ties).
// ⚠Sessions carry `ageSec`, not `idle` — sessByIdle (bgs rows) left this list in server order.
function tlgAge(x){ return typeof x.ageSec === 'number' ? x.ageSec : 1e12; }
function tlgName(x){ return String(x.project || x.cwd || ''); }
function tlgSessions(){
  return (SESS || []).filter(x => x && x.cwd).sort((p, q) => (tlgAge(p) - tlgAge(q)) || tlgName(p).localeCompare(tlgName(q)));
}
// Repo chips newest first: a repo's recency = its freshest session (cwd or `repos` entry); unknown keeps the cwd-first order.
function tlgRepoOrder(repos){
  const age = {};
  for(const s of SESS || []) if(s && s.cwd){
    const rs = [s.cwd].concat(s.repos || []);
    for(const r of rs) if(repos.indexOf(r) >= 0 && !(age[r] <= tlgAge(s))) age[r] = tlgAge(s);
  }
  const a = r => r in age ? age[r] : 1e12;
  return repos.slice().sort((p, q) => (a(p) - a(q)) || (repos.indexOf(p) - repos.indexOf(q)));
}
// Followed session: the chosen one, else (auto, or the chosen one disappeared) the most recently active session.
// `repo` = the git cwd the rail shows — the picked repo while that session stays followed, else the session cwd.
function tlgTarget(){
  const all = tlgSessions();
  let row = tlgSel ? all.find(x => cpKey(x) === tlgSel) : null;
  if(tlgSel && !row && all.length) tlgSel = '';   // ⚠not before the first /api/state (SESS = []) — a restored pick would be wiped
  const how = row ? 'pick' : 'auto';
  row = row || all[0];
  if(!row) return null;
  const tg = {cwd: row.cwd, row, how, all, key: cpKey(row), sid: (row.plat || 'cc') === 'cc' ? (row.sid || '') : ''};
  tg.repos = tlgRepos(tg.cwd);
  if(tlgRepoSel.key !== tg.key) tlgRepoSel = {key: tg.key, repo: '', all: false};   // choice and reveal last only while this session is followed
  tg.repo = tg.repos.indexOf(tlgRepoSel.repo) >= 0 ? tlgRepoSel.repo : tg.cwd;
  tg.ck = tg.repo + '\0' + tg.sid + '\0' + tlgMode;
  return tg;
}
// Baseline line: what the file list is measured against.
function tlgBaseHtml(d){
  const nc = (d.nCommits || 0) + (d.commitsCut ? '+' : ''), nd = Math.max(0, (d.dirty || 0) - (tlgUntr ? 0 : (d.untracked || 0)));   // hidden untracked leave this count too
  const cnt = ' · ' + TV({msg: '{c} commits + {d} uncommitted', vars: {c: nc, d: nd}});
  let t, tip = d.base || '';
  if(d.baseKind === 'branch') t = TV({msg: 'vs {r}', vars: {r: d.baseRef}}) + cnt;
  else if(d.baseKind === 'remote') t = TV({msg: 'vs {r} · {c} unpushed + {d} uncommitted', vars: {r: d.baseRef, c: nc, d: nd}});
  else if(d.baseKind === 'start'){
    const hm = hhmm(d.since || 0, {date: 'other', dsep: '-'});
    t = TV({msg: 'Since session start {t} ({s})', vars: {t: hm, s: String(d.base).slice(0, 7)}}) + cnt;
  } else {
    t = TV({msg: 'vs last commit · {d} uncommitted', vars: {d: nd}}); tip = 'HEAD';
    if(d.baseMode === 'start') t = T('Session start unknown — vs last commit') + ' · ' + t;
  }
  if(d.noRemote) t = T('No remote — session start') + ' · ' + t;
  return '<div class=tlgbs title="' + esc(tip) + '">' + esc(t) + '</div>';
}
// Repo picker: only when the session covers more than one repo. Labels are repo/branch names (metadata only).
// R1-R4: a chip with 0 shown files for this compare mode is hidden unless it is the selected repo (R2) or the reveal flag is on (R3).
// ⚠Unknown status (no reply yet, error) must stay shown (R4) — hiding it would drop a dirty repo before its background fetch lands.
// Chip label: main repo name for a worktree (`main` from the rail reply) + branch; folder name until the reply lands.
function tlgRepoLabel(r, tg){
  const d = (tlgC[r + '\0' + tg.sid + '\0' + tlgMode] || {}).d, ok = d && d.ok;
  return ((ok && d.main) || r.split('/').pop() || r) + (ok && d.branch ? ' · ' + d.branch : '');
}
function tlgRepoChips(tg){
  if(tg.repos.length <= 1) return '';
  let nh = 0;
  const vis = tlgRepoOrder(tg.repos).filter(r => {
    if(r === tg.repo || tlgRepoSel.all) return true;
    const d = (tlgC[r + '\0' + tg.sid + '\0' + tlgMode] || {}).d;
    if(!d || !d.ok || tlgShownN(d) > 0 || (d.ahead || 0) > 0) return true;   // unpushed commits are not «clean»
    nh++;
    return false;
  });
  return '<div class=tlgrp role=group aria-label="' + esc(T('Pick a repo')) + '">' + vis.map(r =>
      '<em class="tlgrc' + (r === tg.repo ? ' on' : '') + '"' + TLG_KB + ' data-tgr="' + esc(r) + '" title="' + esc(r) + '" aria-pressed="' + (r === tg.repo) + '">'
      + esc(tlgRepoLabel(r, tg)) + '</em>').join('')
    + (nh ? '<em class="tlgrc tlgrx"' + TLG_KB + ' data-tgrx title="' + esc(T('Show repos with no changes')) + '">'
      + esc(TV({msg: '+{n} clean', vars: {n: nh}})) + '</em>' : '') + '</div>';
}
function tlgFits(){ return window.innerWidth >= TLG_MIN_W; }
function tlgHtml(){
  const tg = tlgTarget();
  const hd = '<div class=tlghd><b>' + esc(T('Changes', 'panel')) + '</b>'
    + '<em class=tlgx2 id=tlgx' + TLG_KB + ' title="' + esc(T('Close')) + '">✕</em></div>';
  if(!tg) return hd + '<div class=tlgmt>' + esc(T('No session to follow')) + '</div>';
  const row = tg.row;
  const lab = x => (x.project || x.cwd.split('/').pop() || x.cwd) + (x.sid ? ' · ' + sid8(x.sid) : '')
    + (x.state ? ' · ' + (stateLbl(x.state) || T(x.state)) : '')   // stateLbl carries the T() context (Thinking|now);
  // Visible leading labels name each select (label-in-name); the full path + sid stays in the select's title.
  const fol = '<div class=tlgfs><label class=tlgfl for=tlgss>' + esc(T('Session')) + '</label>'
    + '<select class=tlgss id=tlgss title="' + esc(tg.cwd + (row.sid ? ' · ' + row.sid : '')) + '">'
    + '<option value=""' + (tg.how === 'auto' ? ' selected' : '') + '>' + esc(T('Auto (latest active)')
      + (tg.how === 'auto' ? ' — ' + lab(row) : '')) + '</option>'
    + tg.all.map(x => '<option value="' + esc(cpKey(x)) + '"' + (tg.how === 'pick' && cpKey(x) === tg.key ? ' selected' : '') + '>'
      + esc(lab(x)) + '</option>').join('')
    + '</select>'
    + '<label class=tlgfl for=tlgbm>' + esc(T('Compare')) + '</label><select class=tlgss id=tlgbm title="' + esc(T('Compare against')) + '">'
    + TLG_MODES.map(([k, en]) => '<option value="' + k + '"' + (k === tlgShownMode(tg) ? ' selected' : '') + '>' + esc(T(en)) + '</option>').join('')
    + '</select></div>';
  const hdf = hd + fol + tlgRepoChips(tg);
  const c = tlgC[tg.ck], d = c && c.d;
  if(!d) return hdf + '<div class=tlgmt>' + esc(T('Loading…')) + '</div>';
  if(!d.ok) return hdf + '<div class=tlgmt>' + esc(d.msg ? TV(d) : T(d.err || 'Could not fetch')) + '</div>';
  const br = d.branch || (tg.repo === tg.cwd && row.branch) || T('(detached HEAD)');
  const ab = d.hasUp ? '<span class=tlgab title="' + esc(T('vs upstream') + ' ' + d.upstream) + '">↑' + (d.ahead || 0) + ' ↓' + (d.behind || 0) + '</span>'
                     : '<span class=tlgab title="' + esc(T('No upstream')) + '">—</span>';
  const vsBase = !!d.base;
  const files = d.files || [], shown = tlgShown(files), tree = tlgShownTree(files);
  // ⚠Hidden untracked files must leave the header totals too — a scratch dir of new files read as «+38228 uncommitted».
  const hid = files.filter(f => !shown.includes(f));
  const nShow = tlgShownN(d);
  const aShow = (d.add || 0) - hid.reduce((s, f) => s + (f.add || 0), 0), rShow = (d.del || 0) - hid.reduce((s, f) => s + (f.del || 0), 0);
  const sum = '<div class=tlgbr><span class=tlgbn title="' + esc(br) + '">' + tlgMid(br) + '</span>' + ab + '</div>'
    + tlgBaseHtml(d)
    + '<div class=tlgsm><span>' + esc(vsBase ? TV({msg: '{n} files changed', vars: {n: nShow}}) : TV({msg: '{n} uncommitted', vars: {n: nShow}}))
    + '</span>' + tlgNum(aShow, rShow) + tlgFoldBtns(tree) + '</div>';
  const body = shown.length
    ? '<div class=tlgtr>' + tlgTreeHtml(tree, 0, tg.repo) + '</div>'
      + (nShow > shown.length ? '<div class=tlgmt>' + esc(TV({msg: 'First {n} only', vars: {n: shown.length}})) + '</div>' : '')
    : '<div class=tlgmt>' + esc(vsBase ? T('No changes since the base') : T('No uncommitted changes', 'git')) + '</div>';
  const cm = (d.commits || []).map(x => '<div class=tlgcm' + TLG_KB + ' data-tgc="' + esc(x.sha) + '" title="' + esc(x.sha + ' ' + x.msg + '\n' + T('Click to see this commit\'s changes')) + '"><s>' + esc(x.sha) + '</s>'
    + '<span>' + esc(x.msg) + '</span><i>' + esc(agoAt(x.at)) + '</i></div>').join('');
  const cmh = vsBase && d.nCommits ? T('Commits since the base') : T('Recent commits');
  const ft = cm ? '<div class=tlgft><div class=tlgfh>' + esc(cmh) + '</div>' + cm + '</div>' : '';
  return hdf + tlgUntrHtml(files) + sum + body + ft;
}
function tlgBtnHtml(){
  // ★A real toggle (the flat label did not read as the way back).
  return '<em class="tlrf tlgb' + (tlgOn ? ' on' : '') + '" id=tlgb role=button aria-pressed="' + tlgOn + '" title="'
    + esc(tlgOn ? T('Close the changes panel (git · view only)')
                : T('Open the changes panel (git · view only)')) + '">'
    + '<i class=tlgbi aria-hidden=true></i>' + esc(T('Changes', 'git')) + '</em>';
}
// paintTl wraps its markup here so the rail survives every timeline repaint.
function tlgWrap(html){
  if(!tlgOn) return html;
  // ★2026-09-28 cut off at 706 files: the sticky rail had no height cap and ran past the feed ⇒ cap it at the feed height, it scrolls itself
  // ★Fill the full height ⇒ height, not just max-height: the rail spans the feed even when its list is short
  const fh = tlgFeedH(), mh = fh > 200 ? 'height:' + fh + 'px;max-height:' + fh + 'px;' : '';
  const w = (tlgW || mh) ? ' style="' + mh + (tlgW ? 'flex-basis:' + tlgW + 'px;width:' + tlgW + 'px' : '') + '"' : '';
  return '<div class=tlgw><div class=tlgmn>' + html + '</div><div class=tlgrs id=tlgrs' + (fh > 200 ? ' style="height:' + fh + 'px"' : '') + ' title="' + esc(T('Drag to resize · double-click for default'))
    + '"></div><aside class=tlg id=tlgit' + w + '>' + tlgHtml() + '</aside></div>';
}
// ★Resizable rail. 0 = CSS default (400px).
// ⚠The grip sits outside #tlgit (tlgPaint rewrites its innerHTML) and the drag resolves #tlgit per move, so a paintTl mid-drag is harmless.
// Gantt re-fit is automatic: 74-timeline's ResizeObserver on the axis fires when .tlgmn shrinks/grows.
// ⚠A width saved under the old 260 floor would pin the rail narrower than the new default ⇒ below TLGW_MIN it is ignored (0 = default).
const TLGW_MIN = 380, TLGW_MAX = 960;
let tlgW = (() => { try{ const v = +UIS['sidereus.tlgw'] || 0; return v >= TLGW_MIN ? v : 0; }catch(e){ return 0; } })();
function tlgWClamp(w){
  const wr = document.querySelector('.tlgw');
  const max = Math.min(TLGW_MAX, wr ? wr.clientWidth / 2 : TLGW_MAX);
  return Math.round(Math.max(TLGW_MIN, Math.min(max, w)));
}
function tlgWSet(w){
  const el = document.getElementById('tlgit');
  if(!el) return;
  el.style.flexBasis = w ? w + 'px' : '';
  el.style.width = w ? w + 'px' : '';
}
document.addEventListener('pointerdown', e => {
  const g = e.target.closest && e.target.closest('#tlgrs');
  if(!g || e.button !== 0) return;
  e.preventDefault();
  try{ g.setPointerCapture(e.pointerId); }catch(err){}
  g.classList.add('on');
  document.body.classList.add('dragging');
  const move = ev => {
    // ⚠A repaint can drop the captured grip, so a release outside the window never sends pointerup — end on no buttons.
    if(!ev.buttons) return up();
    const wr = document.querySelector('.tlgw');
    if(!wr) return;
    tlgW = tlgWClamp(wr.getBoundingClientRect().right - ev.clientX);
    tlgWSet(tlgW);
  };
  const up = () => {
    document.removeEventListener('pointermove', move);
    document.removeEventListener('pointerup', up);
    document.removeEventListener('pointercancel', up);
    document.body.classList.remove('dragging');
    const cur = document.getElementById('tlgrs');
    if(cur) cur.classList.remove('on');
    if(tlgW) lsSet('sidereus.tlgw', tlgW);
  };
  document.addEventListener('pointermove', move);
  document.addEventListener('pointerup', up);
  document.addEventListener('pointercancel', up);
});
document.addEventListener('dblclick', e => {
  if(!(e.target.closest && e.target.closest('#tlgrs'))) return;
  tlgW = 0;
  lsDel('sidereus.tlgw');
  tlgWSet(0);
});
// ⚠tlgWrap measures #feed before the header rows settle (rail 657px vs a 631px feed on first paint) ⇒ refit on
// every #feed resize, not only window resize. The grip gets the same height (it stretched to the Gantt, ~900px).
let tlgRO = null;
// ⚠Rail height = #feed's exact (fractional) height: the rail starts at the feed top and #feed has no bottom padding, so any
// offset (was -6/-8) or integer clientHeight leaves its bottom above the «Window summary» card's bottom.
function tlgFeedH(){ const f = document.getElementById('feed'); return f ? f.getBoundingClientRect().height : 0; }
function tlgFitH(){
  const f = document.getElementById('feed');
  if(f && !tlgRO && window.ResizeObserver){ tlgRO = new ResizeObserver(() => tlgFitH()); tlgRO.observe(f); }
  const el = document.getElementById('tlgit'), g = document.getElementById('tlgrs'), fh = tlgFeedH();
  if(fh <= 200) return;
  const h = fh + 'px';
  if(el && el.style.height !== h) el.style.height = el.style.maxHeight = h;
  if(g && g.style.height !== h) g.style.height = h;
}
addEventListener('resize', tlgFitH);
// Id of the focused rail select, or ''. Shared by tlgPaint and paintTl (which rebuilds the rail with the Gantt).
function tlgFocusId(){
  const ae = document.activeElement;
  return ae && (ae.id === 'tlgss' || ae.id === 'tlgbm') ? ae.id : '';
}
function tlgPaint(){
  const el = document.getElementById('tlgit');
  if(!el) return;
  if(tlgFocusId()) return;   // ⚠a repaint would close the open dropdown
  const top = el.scrollTop;
  if(setHtml(el, tlgHtml())) el.scrollTop = top;
}
function tlgFetch(tg, force, ttl){
  const c = tlgC[tg.ck] || (tlgC[tg.ck] = {at: 0, d: null, busy: false});
  if(c.busy || (!force && Date.now() - c.at < (ttl || TLG_TTL_S) * 1000)) return;
  c.busy = true;
  getJSON('/api/git/diff?view=rail&cwd=' + encodeURIComponent(tg.repo) + '&base=' + tlgMode
        + (tg.sid && tlgMode !== 'head' && tlgMode !== 'auto' ? '&sid=' + encodeURIComponent(tg.sid) : ''))
    .then(j => { c.d = j; }, () => { if(!c.d) c.d = {ok: false, msg: 'Could not fetch'}; })
    .then(() => { c.at = Date.now(); c.busy = false; tlgPaint(); });
}
// Called from poll() (2.5 s); fetches at most once per TLG_TTL_S and only while the rail is open and visible.
function tlgTick(){
  if(!tlgOn || mainView !== 'time' || document.hidden || !tlgFits()) return;
  const tg = tlgTarget();
  if(tg){
    tlgFetch(tg);
    // Same URL and cache key as picking that chip, so a later click paints from cache.
    if(tg.repos.length > 1) tg.repos.filter(r => r !== tg.repo).slice(0, TLG_BG_MAX).forEach(r =>
      tlgFetch({repo: r, ck: r + '\0' + tg.sid + '\0' + tlgMode, sid: tg.sid}, false, TLG_BG_TTL_S));
  }
  tlgPaint();
}
function tlgToggle(){
  tlgOn = !tlgOn;
  lsSet('sidereus.tlgit', tlgOn ? '1' : '0');
  paintTl();
  tlgTick();
}
// Local filter only: repaint from the cached reply (no fetch); tlgPaint keeps the scroll position.
function tlgUntrSet(on){
  tlgUntr = !!on;
  lsSet('sidereus.tlgUntr', tlgUntr ? '1' : '0');
  tlgPaint();
}
function tlgWire(){
  const b = document.getElementById('tlgb');
  if(b) b.onclick = tlgToggle;
  tlgFitH();
  const el = document.getElementById('tlgit');
  if(el) el.onclick = e => {
    const t = e.target;
    // ⚠✕ is removed by the repaint, so focus would fall to <body>; hand it to the panel's toggle button.
    if(t.closest('#tlgx')){ tlgToggle(); kbHold('#tlgb'); return; }
    const tg = tlgTarget();
    if(!tg) return;
    if(t.closest('[data-tgu]')) return tlgUntrSet(true);
    // R3: reveal is memory only (not kept across reloads) and needs no fetch.
    if(t.closest('[data-tgrx]')){ tlgRepoSel.all = true; return tlgPaint(); }
    const rc = t.closest('[data-tgr]');
    if(rc){ tlgRepoSel = {key: tg.key, repo: rc.dataset.tgr, all: tlgRepoSel.all}; tlgKeepSave(); tlgTick(); return; }
    const fa = t.closest('[data-tga]');
    if(fa){ const d = (tlgC[tg.ck] || {}).d; tlgFoldAll(tlgShownTree((d && d.files) || []), tg.repo, fa.dataset.tga === '1'); return tlgPaint(); }
    const dr = t.closest('[data-tgd]');
    if(dr){ const k = tg.repo + '\0' + dr.dataset.tgd; if(tlgShut.has(k)) tlgShut.delete(k); else tlgShut.add(k); return tlgPaint(); }
    const fl = t.closest('[data-tgf]');
    // ⚠Owner line / «Conflict» handle the click themselves — the file name alone opens the diff.
    const cf = fl && t.closest('.tlgcf'), ol = fl && t.closest('.tlgol');
    if(cf || ol){
      e.stopPropagation();
      const f = tlgFileOf(tg, fl.dataset.tgf);
      if(f && cf) tlgCfOpen(f, cf); else if(f) tlgOwnOpen((f.own || [])[0]);
      return;
    }
    if(fl){ const d = (tlgC[tg.ck] || {}).d; loadDiff(tg.repo, fl.dataset.tgf, d && d.base ? 'b:' + d.base : 'work'); }
    // ★Commit row -> the diff window's single-commit scope `c:<sha>`.
    //   One window per commit so the session's own diff window keeps its scope; the server guards the sha (git_view `c:`).
    const cr = t.closest('[data-tgc]');
    if(cr && /^[0-9a-f]{7,40}$/i.test(cr.dataset.tgc)){
      const sha = cr.dataset.tgc;
      popOpen('/diff?cwd=' + encodeURIComponent(tg.repo) + '&scope=' + encodeURIComponent('c:' + sha),
              popName('sidereus_diffc_', tg.repo + '_' + sha), 1700, 1100);
    }
  };
  if(el) el.onchange = e => {
    if(e.target.id === 'tlgun') return tlgUntrSet(e.target.checked);
    if(e.target.id === 'tlgss') tlgSel = e.target.value;
    else if(e.target.id === 'tlgbm' && TLG_MODES.some(m => m[0] === e.target.value)) tlgMode = e.target.value;
    else return;
    tlgKeepSave();
    e.target.blur();   // tlgPaint skips while the select has focus
    tlgTick();
  };
  if(el){ el.style.maxHeight = Math.max(200, tlgFeedH() || 600) + 'px'; }
}
