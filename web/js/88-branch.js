// ── Branch flow ─────────────────────────────────────────────────────────
// ★Fetched only when the tab opens (no polling) — the request actually reads git, so mixed into the 2.5s poll it would run per repo every time.
let BR = null, brRepo = '', brBusy = 0, brSel = '', brRetry = 0;
// Commit details: {sha, repo, st:'load'|'ok'|'err', j, fp (open file path), fd (its patch response)}. null = branch panel.
let brDet = null, brPanList = '';
// Work unit (worktree <-> sessions, Paseo-style): selected worktree path ('' = none) and its uncommitted-file fetch.
let brWu = '', brWuF = null;
let brKid = [];                       // graph hover: same-lane first-parent child per row (brHl)
brRepo = tabGet('mbBrRepo', '');
const BR_RH = 26;                       // Row height — the SVG and the text lines on the right must use **the same value** to align
const BR_CHIPS = 6;                     // Ref chips per commit row before the «+N» chip
// Repo picker — union of git repos touched by sessions (`sessions[].repos`).
// ⚠`cwd` is added only when `branch` is present — a non-git folder makes the server reply 400.
function brRepos(){
  const out = [], seen = new Set();
  const add = p => { if(p && !seen.has(p)){ seen.add(p); out.push(p); } };
  (SESS || []).forEach(x => { if(!x) return;
    if(x.branch) add(x.cwd);
    (x.repos || []).forEach(add); });
  return out;
}
// ★Lane layout — a **pure function** (reads no globals). Tested separately with node.
// A lane waits for one sha at a time (`act[j]`) — so two commits cannot overlap at the same point.
// The first parent inherits the same lane; only the second and later (merges) open new lanes ⇒ many merges do not blow up.
// ★2026-09-23 (flow lines looked unnatural): a first parent keeps its child's lane down to the parent row
//   (several lanes may wait for one sha), so a fork bends into the parent lane only in the row next to the parent;
//   a merge's extra parent bends out in the row next to the merge. Edge = {lane: child, via: travel lane, plane: parent}.
//   ⚠Do not go back to "reuse the lane already waiting for the first parent" - that drew long diagonals across lanes.
function brLanes(commits){
  const idx = new Map();
  (commits || []).forEach((c, i) => { if(!idx.has(c.sha)) idx.set(c.sha, i); });
  const act = [];                       // act[j] = sha that lane is waiting for (null if none)
  const rows = [], raw = [];
  let wide = 0;
  const near = ln => {                  // free lane closest to `ln` (right side first) - fewer crossings
    for(let d = 1; d <= act.length; d++){
      if(ln + d < act.length && act[ln + d] === null) return ln + d;
      if(ln - d >= 0 && act[ln - d] === null) return ln - d;
    }
    act.push(null); return act.length - 1;
  };
  (commits || []).forEach((c, i) => {
    let ln = act.indexOf(c.sha);
    if(ln < 0){ ln = act.indexOf(null); if(ln < 0){ ln = act.length; act.push(null); } }
    for(let j = 0; j < act.length; j++) if(act[j] === c.sha) act[j] = null;
    const ps = (c.parents || []).filter(p => idx.has(p));
    rows.push({ sha: c.sha, row: i, lane: ln, merge: (c.parents || []).length > 1 });
    if(ln > wide) wide = ln;
    ps.forEach((p, k) => {
      let via = ln;
      if(k > 0){ const ex = act.indexOf(p); via = ex >= 0 ? ex : near(ln); }
      act[via] = p;
      if(via > wide) wide = via;
      raw.push({ from: i, to: idx.get(p), lane: ln, via: via, merge: k > 0 });
    });
  });
  const edges = raw.map(e => ({ from: e.from, to: e.to, lane: e.lane, via: e.via, plane: rows[e.to].lane, merge: e.merge }));
  return { rows: rows, edges: edges, lanes: wide + 1 };
}
let brWaitN = 0;
const brBad = new Set();   // repos that answered 400/403 this page load — never fallen back to twice (no ping-pong)
function brForget(p){ if(tabGet('mbBrRepo', '') === p) tabDel('mbBrRepo'); }
// ⚠Read the body **regardless of status code** — 403 (not in list) and 400 (missing path) carry the reason in the body.
function loadBr(force){
  // ⚠A saved repo is checked against the session list before any fetch — a stale one (repo gone, session closed) used to 400 on every load.
  if(!STATE_IN && brRepo){ BR = null; paintBr();
    if(brWaitN++ < 20) setTimeout(() => { if(mainView === 'br') loadBr(force); }, 600);
    return; }
  const ps = brRepos();
  if(brRepo && ps.indexOf(brRepo) < 0){ brForget(brRepo); brRepo = ''; }
  if(!brRepo) brRepo = ps[0] || '';
  if(!brRepo){
    // ★Before the first state arrives, "no repo" flashed for 1-2 s (2026-09-23) — stay in loading; poll() calls back.
    if(!STATE_IN){ BR = null; return paintBr(); }
    BR = { ok: false, msg: T('No git repository in the session list yet') };
    // Right after boot `SESS` is empty — look once more (not polling)
    if(!brRetry){ brRetry = 1; setTimeout(() => { if(mainView === 'br') loadBr(force); }, 1200); }
    return paintBr();
  }
  if(brBusy) return;
  if(!force && BR && BR.ok && BR.cwd === brRepo) return paintBr();
  brBusy = 1; BR = null; paintBr();
  const want = brRepo;
  fetch('/api/branches?cwd=' + encodeURIComponent(want) + '&n=80', { cache: 'no-store' })
    .then(r => r.json().catch(() => ({ ok: false })).then(j => ({ st: r.status, j: j || {} })))
    .then(o => {
      brBusy = 0;
      if(want !== brRepo) return loadBr(force);          // Another repo was selected while fetching
      const j = o.j;
      if(j && j.ok){ BR = j; if(!BR.cwd) BR.cwd = want; }
      else if((o.st === 400 || o.st === 403) && (brBad.add(want), brRepos().some(p => !brBad.has(p)))){   // unreadable: silently try another
        brForget(want); brRepo = brRepos().find(p => !brBad.has(p)); return loadBr(force);
      }
      else BR = { ok: false, msg: brMsg(o.st, j) };
      if(mainView === 'br') paintBr();
    })
    .catch(() => { brBusy = 0;
      BR = { ok: false, msg: T('Not ready yet — check the server') };
      if(mainView === 'br') paintBr(); });
}
// One-line reason — the server uses `err`, the old screen convention is `msg`, so check both
// Known server `err` strings (sidereus/git.py) -> dictionary key, so T() shows the reworded text in both languages.
const BR_ERRS = {'not a git repo': 'Not a git repository', 'timeout': 'Timed out'};
function brMsg(st, j){
  // Returns translated text (server msg filled by TV, never passed through T() again).
  const e0 = (j && (j.err || j.msg)) || '', e = BR_ERRS[e0] ? T(BR_ERRS[e0]) : (j && !j.err && j.msg) ? TV(j) : T(e0);
  if(st === 403) return T('This repository is not in the list — only repositories a session touched can be viewed');
  if(st === 400) return T('Unreadable path') + (e ? ' — ' + e : '');
  if(st === 404) return T('Not ready yet — /api/branches is missing');
  return e || (T('Could not fetch') + (st ? ' (' + st + ')' : ''));
}
// ── paintBr sections: each helper returns one HTML piece (brBarPaint / brKidSet paint or set state); paintBr assembles.
// Repo combobox (08b ppComboHtml, same as Pipelines/Structure) and ↻ live in the header toolbar slot.
function brBarPaint(ps){
  // ⚠Skip while the picker is open: a poll repaint would replace its opener under the popover.
  if(popIsOpen('ppop')) return;
  const chips = ps.length
    ? ppComboHtml({ k: 'br', label: T('Repository'), items: ps.map(p => ({ p: p, name: strShort(p) })), cur: brRepo, rkey: 'sidereus.brrecent', pick: brPickRepo })
    : '<b>' + esc(T('Repository')) + '</b><span class=strpnl>' + esc(T(STATE_IN ? 'None' : 'Loading…')) + '</span>';
  tbSet('br', brModeHtml() + '<span class="strps tbg">' + chips + (BR && BR.ok ? '<button class="brfc brpwb' + (brPw ? ' on' : '') + '" id=brpwb title="'
      + esc(T('Copy a command that makes another worktree and starts a separate session there (Sidereus does not run it)')) + '">' + esc(T('＋ Parallel work')) + '</button>' : '') + '</span>'
    + '<span class=tbx><em class=tlrf id=brrf title="' + esc(T('Reload now')) + '">↻</em></span>');
}
function brHeadHtml(n){ return '<div class="wvh wvht"><span>' + n + '</span></div>'; }
// Loading (busy or no payload yet) or the one-line error.
function brStatusHtml(){
  if(brBusy || !BR) return '<div class=brtab>' + brHeadHtml(esc(T('Loading…')))
      + '<div class=strload><b>' + esc(T('Reading branches…')) + '</b><br>' + esc(T('Up to 80 commits are scanned.')) + '</div></div>';
  return '<div class=brtab>' + brHeadHtml('')
      + '<div class="tlhd cwerr">' + esc(BR.msg || T('Not ready yet')) + '</div></div>';
}
function brDetachedHtml(){
  if(BR.unborn) return '<div class=strpnw>' + esc(T('Empty repository')) + ' — ' + esc(T('no commits yet')) + '</div>';
  return BR.detached
    ? '<div class=strpnw>' + esc(T('⚠ detached HEAD — not attached to any branch (commit')) + ' '
      + esc(BR.head || '?') + ').</div>' : '';
}
function brLegendHtml(){
  return '<div class=brlg><span>' + esc(T('Lane color = line of work')) + '</span>'
    + '<i class="brf brl">' + esc(T('local')) + '</i><u>' + esc(T('filled chip')) + '</u>'
    + '<i class="brf brm">origin/…</i><u>' + esc(T('outline only')) + '</u>'
    + '<i class="brf brh">HEAD</i><u>' + esc(T('where you are now')) + '</u>'
    + '<span>' + esc(T('· hollow dot = merge')) + '</span></div>';
}
function brNoteHtml(cms, bl){
  return esc(BR.repo || strShort(brRepo)) + ' · ' + esc(BR.head || '?')
    + ' · ' + esc(T('Branches')) + ' ' + bl.length + ' · ' + esc(T('Commits')) + ' ' + cms.length
    + (BR.truncated ? esc(T('(truncated)')) : '')
    + (BR.cached ? ' · ' + esc(T('20s cache')) : (BR.ms ? ' · ' + BR.ms + 'ms' : '')) + brFetchNote();
}
function brGraphSvg(cms, lay){
  // With many lanes, **only shrink the spacing** — never remove the graph
  // Lanes past CAP share the last column (width stays bounded); spacing shrinks before that.
  const CAP = 14, VL = Math.min(Math.max(1, lay.lanes), CAP), vl = l => Math.min(l, CAP - 1);
  const LW = VL > 10 ? 10 : (VL > 6 ? 12 : 14);
  const PAD = Math.round(LW * 0.8);
  const W = PAD * 2 + VL * LW;
  const H = cms.length * BR_RH;
  const cx = l => PAD + vl(l) * LW + LW / 2;
  const cy = r => r * BR_RH + BR_RH / 2;
  // Light set = same hues darkened: ★3.9-4.8:1 on #f4f5f7 (dark set there was 1.39-3.06)
  const HUE = thc(['#5899f3', '#71c269', '#f59e3b', '#ac76d8', '#2cc5c5', '#f45460', '#ead33f', '#f080b8'],
    ['#2b6fd6', '#3a8a3e', '#b8650f', '#8a52bd', '#13808a', '#c9303f', '#856d00', '#c0407f']);
  const col = l => HUE[l % HUE.length];
  const bend = (xa, ya, xb, yb) => 'C' + xa + ' ' + (ya + (yb - ya) * 0.55) + ' ' + xb + ' ' + (yb - (yb - ya) * 0.55) + ' ' + xb + ' ' + yb;
  let g = '';
  lay.edges.forEach(e => {
    const x1 = cx(e.lane), xv = cx(e.via), xp = cx(e.plane), y1 = cy(e.from), y2 = cy(e.to);
    let d = 'M' + x1 + ' ' + y1, y = y1;
    if(e.to - e.from <= 1) d += x1 === xp ? 'V' + y2 : bend(x1, y1, xp, y2);
    else {
      if(xv !== x1){ y = y1 + BR_RH; d += bend(x1, y1, xv, y); }          // merge: bend out right under the merge
      if(xp !== xv){ const yb = y2 - BR_RH; if(yb > y) d += 'V' + yb; d += bend(xv, Math.max(y, yb), xp, y2); }   // fork: bend in right above the parent
      else d += 'V' + y2;
    }
    g += '<path data-f=' + e.from + ' data-t=' + e.to + ' data-m=' + (e.merge ? 1 : 0) + ' d="' + d + '" fill="none" stroke="' + col(e.via)
      + '" stroke-width="2" stroke-linecap="round" stroke-opacity="' + (e.merge ? '.75' : '1') + '"/>';
  });
  lay.rows.forEach(r => {
    const c = cms[r.row], isHd = (c.refs || []).indexOf('HEAD') >= 0, x = cx(r.lane), y = cy(r.row);
    if(isHd) g += '<circle data-r=' + r.row + ' cx="' + x + '" cy="' + y + '" r="8.5" fill="none" stroke="' + thc('#e0b45f', '#9a6a00') + '" stroke-width="2"/>';   // ★light ring 1.77 -> 4.34:1
    g += '<circle data-r=' + r.row + ' cx="' + x + '" cy="' + y + '" r="' + (r.merge ? 4.6 : 4.8)
      + '" style="fill:' + (r.merge ? 'var(--nx-bg,#0a0b0e)' : col(r.lane)) + ';stroke:' + (r.merge ? col(r.lane) : 'var(--nx-bg,#0a0b0e)')
      + '" stroke-width="' + (r.merge ? 2.4 : 1.5) + '"/>';   // merge = hollow ring; ⚠var() only works in style, not presentation attrs
  });
  return '<svg class=brsvg width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '">'
    + g + '</svg>';
}
// Hover highlight: first-parent child in the same lane, per row (brHl walks it upward).
function brKidSet(cms, lay){
  const rIdx = new Map(cms.map((c, i) => [c.sha, i]));
  brKid = cms.map(() => -1);
  lay.rows.forEach(r => { const p = rIdx.get((cms[r.row].parents || [])[0]);
    if(p != null && brKid[p] < 0 && lay.rows[p].lane === r.lane) brKid[p] = r.row; });
}
function brListHtml(cms, bl){
  // ⚠The server drops `origin/HEAD` (symbolic duplicate) — draw assuming it is absent.
  const kind = {};
  bl.forEach(b => { kind[b.name] = b.kind; });
  const isRem = n => (kind[n] ? kind[n] === 'remote' : n.indexOf('/') > 0);
  // When detached, `head` is not a branch name but **the HEAD commit's 7-char sha** — do not match it against name chips
  const hdName = BR.detached ? '' : (BR.head || '');
  const chip = n => '<i class="brf ' + (isRem(n) ? 'brm' : 'brl') + (n === hdName ? ' brh' : '')
    + '" title="' + esc(n) + '">' + esc(n) + '</i>';
  return cms.map((c, i) => {
    const refs = (c.refs || []).filter(x => x !== 'HEAD');
    // ⚠Cap chips so the subject keeps room (a release commit can carry 100+ tags); the rest goes in a «+N» chip title.
    const more = refs.length > BR_CHIPS ? refs.splice(BR_CHIPS) : [];
    const isHd = (c.refs || []).indexOf('HEAD') >= 0;
    return '<div class="brr' + (brSel === c.sha ? ' on' : '') + '" id="brr' + i
      + '" data-bs="' + esc(c.sha) + '" style="height:' + BR_RH + 'px" title="'
      + esc((c.subject || '') + ' · ' + c.sha) + '">'
      + '<span class=brsj>' + (isHd ? '<i class="brf brh brfh">HEAD</i>' : '') + refs.map(chip).join('')
      + (more.length ? '<i class="brf brmore" title="' + esc(more.join(', ')) + '">+' + more.length + '</i>' : '')
      + '<b>' + esc(c.subject || '') + '</b></span>'
      // Column cells (subgrid tracks in 80-branch.css); "name/dept/role" authors show the name, full string in the tooltip.
      + (c.author ? '<s title="' + esc(c.author) + '">' + esc(String(c.author).split('/')[0] || c.author) + '</s>' : '')
      + brLkChip(c.sha) + '<em>' + (c.ts ? agoAt(c.ts) : '') + '</em>'
      + '<u>' + esc(c.sha) + '</u></div>';
  }).join('');
}
// Branch list is a folder tree now (brTreeHtml, rebuilt inside brPanBody).
// While a commit is selected the detail pane takes the branch panel's place (see brDetHtml).
function brPanHtml(){
  if(brWu && !brWtFind(brWu)){ brWu = ''; brWuF = null; }    // repo switched: that worktree is not in this list
  brPanLast = brPanBody();
  return '<div id=brpan class="brpan' + (brDet || brWu ? ' brdt' : '') + '">' + brPanLast + '</div>';
}
function paintBr(){
  if(mainView !== 'br') return;
  const box = document.getElementById('feed');
  if(!box) return;
  if(brBoardOn) return brBoardPaint();    // «Board» mode (88b-board.js)
  brBarPaint(brRepos());
  if(brBusy || !BR || !BR.ok){ box.innerHTML = brStatusHtml(); return brWire(); }
  const cms = BR.commits || [], bl = (BR.branches || []).slice();
  const det = brDetachedHtml(), legend = brLegendHtml(), note = brNoteHtml(cms, bl);
  if(!cms.length){
    box.innerHTML = '<div class=brtab>' + brHeadHtml(note) + brPwHtml() + det
      + '<div class=strload>' + esc(T('No commits to draw.')) + '</div></div>';
    return brWire();
  }
  const lay = brLanes(cms);
  const svg = brGraphSvg(cms, lay);
  brKidSet(cms, lay);
  const list = brListHtml(cms, bl), pan = brPanHtml();
  const op = document.getElementById('brpan'), opTop = op ? op.scrollTop : 0;
  box.innerHTML = '<div class=brtab>' + brHeadHtml(note) + brPwHtml() + det + legend
    + '<div class=brbody><div class=brgw>' + svg + '<div class=brlist>' + list + '</div></div>'
    + pan + '</div></div>';
  const np = document.getElementById('brpan'); if(np && opTop) np.scrollTop = opTop;   // full repaint keeps the tree's scroll
  brWire();
  brLinksLoad();
}
function brPickRepo(p){
  if(!p || p === brRepo) return;
  brRepo = p; brSel = ''; brDet = null; BR = null;
  tabSet('mbBrRepo', brRepo);
  loadBr(true);
}
function brWire(){
  const box = document.getElementById('feed');
  if(!box) return;
  const rf = document.getElementById('brrf');
  if(rf) rf.onclick = () => loadBr(true);
  brPwWire();
  box.querySelectorAll('[data-fcp]').forEach(el => { el.onclick = () => { const v = el.dataset.fcp;
    copyText(v).then(ok => note(ok ? T('Copy') + ': ' + v : T('Copy failed') + ' — ' + v)); }; });
  box.querySelectorAll('.brpr[data-bb]').forEach(el => {
    el.onclick = () => brJump(el.dataset.bb); });
  box.querySelectorAll('.brr[data-bs]').forEach(el => {
    el.onclick = () => brJump(el.dataset.bs); });
  const pan = document.getElementById('brpan');
  if(pan) pan.onclick = e => {
    const t = e.target;
    if(!t || !t.closest) return;
    if(t.closest('#brdb')) return brClose();
    const bt = t.closest('[data-bt]');
    if(bt) return brTreeSet(bt.dataset.bt);
    if(t.closest('#brmg')){ brMerge = !brMerge; lsSet('sidereus.brmerge', brMerge ? '1' : '0');
      brPanPaint(); return brTreeFocus('#brmg'); }
    const rm = t.closest('[data-wrm]');
    if(rm) return brCmdCopy(rm.dataset.wrm, null);
    const cp = t.closest('[data-cp]');
    if(cp){ const v = cp.dataset.cp;
      copyText(v).then(ok => note(ok ? T('Copy') + ': ' + v : T('Copy failed') + ' — ' + v)); return; }
    const pp = t.closest('[data-bpp]');
    if(pp) return brJump(pp.dataset.bpp);
    const bf = t.closest('[data-bf]');
    if(bf) return brFile(+bf.dataset.bf);
    if(t.closest('#brwub')){ brWu = ''; brWuF = null; return brPanPaint(); }
    if(t.closest('#brwuall')) return brWuOpenAll();
    const wa = t.closest('[data-wat]');
    if(wa){ const x = (SESS || []).find(s => s && s.sid === wa.dataset.wat); if(x) try{ cpGo(x); }catch(er){ softErr('cpGo', er); } return; }
    const bw = t.closest('[data-bw]');
    if(bw) return brWuOpen(bw.dataset.bw);
    const ws = t.closest('[data-wks]');
    if(ws) return wkPopup(ws.dataset.wks, ws.dataset.wkt);
    const lw = t.closest('[data-blw]');
    if(lw) return wkPopup(lw.dataset.blc, lw.dataset.blw);    // same /work popup the history tab opens
    const wd = t.closest('[data-wkd]');
    if(wd) return loadDiff(wd.dataset.wkd);
  };
  if(pan) pan.onkeydown = brTreeKey;
  const gw = box.querySelector('.brgw');
  if(gw){
    gw.onmousemove = e => {
      const r = e.target.closest && e.target.closest('.brr');
      if(r) return brHl(+r.id.slice(3));
      const s = gw.querySelector('.brsvg'), b = s && s.getBoundingClientRect();
      if(b && e.clientX <= b.right) brHl(Math.floor((e.clientY - b.top) / BR_RH));
    };
    gw.onmouseleave = () => brHl(-1);
  }
  if(pan){
    pan.onmouseover = e => { const t = e.target.closest && e.target.closest('[data-bb]'); brHl(t ? brRowOf(t.dataset.bb) : -1); };
    pan.onmouseleave = () => brHl(-1);
  }
  brPanFit();
}
// The pane scrolled despite free room below ⇒ the pane's max-height = room left down to #feed's visible bottom (was a fixed 62vh); it scrolls only past that. ⚠max-height, not height: scrollTop is kept.
function brPanFit(){
  const p = document.getElementById('brpan'), fd = document.getElementById('feed');
  if(!p || !fd || mainView !== 'br') return;
  const fr = fd.getBoundingClientRect(), h = Math.floor(fr.top + fd.clientTop + fd.clientHeight - p.getBoundingClientRect().top);
  const v = h >= 160 ? h + 'px' : '';
  if(p.style.maxHeight !== v) p.style.maxHeight = v;
}
let brFitQ = 0;
function brFitSoon(){ if(!brFitQ) brFitQ = requestAnimationFrame(() => { brFitQ = 0; brPanFit(); }); }
window.addEventListener('resize', brFitSoon);
document.addEventListener('scroll', e => { if(e.target && e.target.id === 'feed') brFitSoon(); }, true);    // sticky pane: room grows as the feed scrolls
// Select a commit (row, branch tip or parent link) and open its details. Tips outside the 80-commit graph
// still open — /api/git/commit does not need the commit to be in the list. Short/full shas match by prefix.
function brJump(sha){
  const cms = (BR && BR.commits) || [];
  let i = -1;
  for(let k = 0; k < cms.length; k++) if(sha.indexOf(cms[k].sha) === 0 || cms[k].sha.indexOf(sha) === 0){ i = k; break; }
  brOpen(i >= 0 ? cms[i].sha : sha);
  const el = i >= 0 && document.getElementById('brr' + i);
  if(el) el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}
// Hover a commit / branch label: highlight its first-parent path (down to the root, up through same-lane children), dim the rest.
// Class toggles only - no layout change, no repaint.
function brHl(row){
  const svg = document.querySelector('#feed .brsvg');
  if(row >= ((BR && BR.commits) || []).length) row = -1;
  if(!svg || svg._hl === row) return;
  svg._hl = row;                        // per-svg state: a full repaint starts clean
  svg.querySelectorAll('.hl').forEach(el => el.classList.remove('hl'));
  if(row == null || row < 0){ svg.classList.remove('dim'); return; }
  const cms = (BR && BR.commits) || [], idx = new Map(cms.map((c, i) => [c.sha, i])), on = new Set();
  for(let r = row; r != null && !on.has(r); r = idx.get((cms[r].parents || [])[0])) on.add(r);
  for(let r = brKid[row]; r != null && r >= 0 && !on.has(r); r = brKid[r]) on.add(r);
  svg.querySelectorAll('circle[data-r]').forEach(el => { if(on.has(+el.dataset.r)) el.classList.add('hl'); });
  svg.querySelectorAll('path[data-f]').forEach(el => { if(el.dataset.m === '0' && on.has(+el.dataset.f) && on.has(+el.dataset.t)) el.classList.add('hl'); });
  svg.classList.add('dim');
}
function brRowOf(sha){
  const cms = (BR && BR.commits) || [];
  for(let k = 0; k < cms.length; k++) if(sha.indexOf(cms[k].sha) === 0 || cms[k].sha.indexOf(sha) === 0) return k;
  return -1;
}
function brOpen(sha){
  brSel = sha;
  if(brDet && brDet.sha === sha && brDet.repo === brRepo && brDet.st !== 'err') return brPanPaint();
  const d = brDet = { sha: sha, repo: brRepo, st: 'load', j: null, fp: '', fd: null, msg: '' };
  brPanPaint();
  fetch('/api/git/commit?repo=' + encodeURIComponent(d.repo) + '&sha=' + encodeURIComponent(sha), { cache: 'no-store' })
    .then(r => r.json().catch(() => ({ ok: false })).then(j => ({ st: r.status, j: j || {} })))
    .then(o => { if(brDet !== d) return;
        if(o.j.ok){ d.st = 'ok'; d.j = o.j; }
        else { d.st = 'err'; d.msg = (o.st === 404 && o.j.err) ? T(o.j.err) : brMsg(o.st, o.j); } },
      () => { if(brDet === d){ d.st = 'err'; d.msg = T('Could not fetch — check the server'); } })
    .then(() => { if(brDet === d) brPanPaint(); });
}
function brFile(i){
  const d = brDet;
  const f = d && d.j && (d.j.files || [])[i];
  if(!f) return;
  d.fp = f.path; brPanPaint();
  // Commit file diff opens in its own popup window, one per sha+path (2026-09-23; was the in-page #brfm modal).
  const sha = d.j.sha;
  popOpen('/brdiff?repo=' + encodeURIComponent(d.repo) + '&sha=' + encodeURIComponent(sha)
          + '&path=' + encodeURIComponent(f.path) + '&add=' + (f.add || 0) + '&del=' + (f.del || 0) + (f.bin ? '&bin=1' : ''),
          popName('sidereus_brdiff_', String(sha).slice(0, 12) + '_' + f.path), 1100, 800);
}
// /brdiff popup body — header path · short sha · +/-, body = diffHtml of that one file.
function brPopPaint(fd){
  const path = WPQ.get('path'), sha = WPQ.get('sha') || '', bin = WPQ.get('bin') === '1';
  document.title = path.split('/').pop() + ' @' + sha.slice(0, 7) + ' — ' + PAGE_NAME;
  const t = document.getElementById('wkmt'); if(t){ t.textContent = path; t.title = path; }
  const s = document.getElementById('wkms');
  if(s) s.innerHTML = esc(sha.slice(0, 7)) + (bin ? ' · ' + esc(T('binary'))
    : ' · <b style="color:' + thc('#7fbf7f', 'var(--nx-ok)') + '">+' + (+WPQ.get('add') || 0) + '</b> <b style="color:' + thc('#e08080', 'var(--nx-err)') + '">−' + (+WPQ.get('del') || 0) + '</b>');
  const b = wkBox(); if(!b) return;
  b.innerHTML = !fd ? '<div class=strload>' + esc(T('Reading the diff…')) + '</div>'
    : !fd.ok ? '<div class="tlhd cwerr">' + esc(fd.err ? T(fd.err) : TV({msg: fd.msg || 'Could not fetch', vars: fd.vars})) + '</div>'
    : (fd.cutBytes ? '<div class=hidnote>' + esc(T('Only the first part is shown')) + '</div>' : '') + diffHtml(fd.diff || '', agLang(path));
}
function brPopBoot(){
  wkOpenModal(); brPopPaint(null);
  fetch('/api/git/commit?repo=' + encodeURIComponent(WPQ.get('repo')) + '&sha=' + encodeURIComponent(WPQ.get('sha'))
        + '&path=' + encodeURIComponent(WPQ.get('path')), { cache: 'no-store' })
    .then(r => r.json()).then(j => brPopPaint(j || { ok: false }), () => brPopPaint({ ok: false }));
}
function brClose(){ brDet = null; brSel = ''; brPanPaint(); }
// Repaint only the right pane (keeps graph/list scroll); ⚠the pane's own scrollTop is carried over by hand.
function brPanPaint(){
  const p = document.getElementById('brpan');
  if(!p) return paintBr();
  const top = p.scrollTop, ae = document.activeElement;
  const fk = ae && p.contains(ae) ? (ae.dataset.bt != null ? '[data-bt="' + CSS.escape(ae.dataset.bt) + '"]'
    : ae.dataset.bn != null ? '[data-bn="' + CSS.escape(ae.dataset.bn) + '"]' : '') : '';
  p.className = 'brpan' + (brDet || brWu ? ' brdt' : '');
  p.innerHTML = brPanLast = brPanBody();
  p.scrollTop = top;
  if(fk) brTreeFocus(fk);    // poll repaint must not drop keyboard focus in the tree
  document.querySelectorAll('#feed .brr[data-bs]').forEach(el => el.classList.toggle('on', el.dataset.bs === brSel));
  document.querySelectorAll('#feed .brpr[data-bb]').forEach(el => el.classList.toggle('on', el.dataset.bb === brSel));
  brWire();
}
function brDetHtml(){
  const d = brDet, j = d.j || {};
  const back = '<div class=brdh><button class=brdb id=brdb>' + esc(T('← Branch list')) + '</button><b>'
    + esc(T('Commit details')) + '</b></div>';
  if(d.st === 'load') return back + '<div class=strload>' + esc(T('Reading the commit…')) + '</div>';
  if(d.st !== 'ok') return back + '<div class="tlhd cwerr">' + esc(d.msg || T('Could not fetch')) + '</div>';
  const inList = ((BR && BR.commits) || []).some(c => j.sha.indexOf(c.sha) === 0);
  const lines = String(j.msg || '').split(NL), subj = lines[0] || '', rest = lines.slice(1).join(NL).trim();
  const when = j.at ? agoAt(j.at) + ' · ' + new Date(j.at * 1000).toLocaleString(LANG === 'en' ? 'en-US' : 'ko-KR') : '';
  const par = (j.parents || []).length
    ? j.parents.map(p => '<button class=brdp data-bpp="' + esc(p) + '" title="' + esc(p) + '">' + esc(p.slice(0, 7)) + '</button>').join('')
    : esc(T('root commit'));
  const fs = j.files || [];
  const files = fs.map((f, i) => {
    const on = d.fp === f.path;
    let h = '<button class="brdf' + (on ? ' on' : '') + '" data-bf="' + i + '" title="' + esc(f.path) + '"><b>' + esc(f.path) + '</b>'
      + (f.bin ? '<em>' + esc(T('binary')) + '</em>' : '<span class=ba>+' + f.add + '</span><span class=bd>−' + f.del + '</span>')
      + '</button>';
    return h;    // the diff itself opens in a popup window (brFile -> /brdiff), not inline
  }).join('');
  return back
    + (inList ? '' : '<div class=strpnw>' + esc(T('This commit is outside the recent list — not in the graph')) + '</div>')
    + '<div class=brds>' + esc(subj) + '</div>'
    + (rest ? '<pre class=brdm>' + esc(rest) + '</pre>' : '')
    + '<div class=brdk><i>sha</i><span><code>' + esc(j.sha) + '</code><button class=brdc data-cp="' + esc(j.sha)
    + '" title="' + esc(T('Copy full hash')) + '">' + esc(T('Copy')) + '</button></span>'
    + '<i>' + esc(T('Author')) + '</i><span title="' + esc(j.email || '') + '">' + esc(j.author || '') + '</span>'
    + '<i>' + esc(T('Time')) + '</i><span>' + esc(when) + '</span>'
    + '<i>' + esc(T('Parents')) + '</i><span>' + par + '</span>' + brLkDet(j.sha) + '</div>'
    + '<div class=hidnote>' + esc(T('Changed files')) + ' ' + (j.nfiles > fs.length ? fs.length + '/' + j.nfiles : fs.length)
    + ' · ' + esc(T('Click a file to see its diff in this commit · Esc to close')) + '</div>' + files;
}
// ── Commit -> Claude session link (server: sidereus/commit_link.py). Metadata only: sid · agent type · tokens · $ (estimate).
// Fetched after the graph paints (never blocks it); a cold server index answers busy -> retry a few times.
let BRL = { repo: '', at: 0, st: '', m: {}, tries: 0 };
function brLk(sha){ const m = BRL.repo === brRepo ? BRL.m : {}; return m[sha] || m[String(sha).slice(0, 7)] || null; }
function brLkChip(sha){
  const l = brLk(sha);
  if(!l) return '';
  const who = l.agent || T('Session') + ' ' + sid8(l.sid);   // agent name alone: "agent sid8 · tok" hit the 190px cap; sid stays in the tooltip
  return '<i class=brlk title="' + esc(T('Session') + ' ' + l.sid + (l.agent ? ' · ' + T('Subagent') + ' ' + l.agent : '')
    + ' · ' + fmtTok(l.tok || 0) + ' · $' + (+l.usd || 0).toFixed(2) + ' — ' + T("Tokens since this session's previous commit (estimate)")) + '">'
    + esc(who) + ' · ' + fmtTok(l.tok || 0) + '</i>';
}
function brLinksLoad(force){
  const repo = brRepo, cms = (BR && BR.commits) || [];
  if(!repo || !cms.length) return;
  if(!force && BRL.repo === repo && (BRL.st === 'load' || (BRL.st === 'ok' && Date.now() - BRL.at < 30000))) return;
  if(BRL.repo !== repo) BRL = { repo: repo, at: 0, st: '', m: {}, tries: 0 };
  BRL.st = 'load';
  getJSON('/api/git/links?repo=' + encodeURIComponent(repo) + '&shas=' + encodeURIComponent(cms.map(c => c.sha).join(',')))
    .then(j => {
      if(BRL.repo !== repo) return;
      if(j && j.ok && j.busy && BRL.tries++ < 6){ BRL.st = ''; setTimeout(() => { if(mainView === 'br') brLinksLoad(); }, 4000); return; }
      BRL.st = j && j.ok ? 'ok' : 'err'; BRL.at = Date.now(); BRL.m = (j && j.links) || {};
      brLinksPaint();
    }, () => { if(BRL.repo === repo){ BRL.st = 'err'; BRL.at = Date.now(); } });
}
// Patch chips into the painted rows in place (no full repaint -> graph/list scroll and hover stay).
function brLinksPaint(){
  document.querySelectorAll('#feed .brr[data-bs]').forEach(el => {
    const old = el.querySelector('.brlk'); if(old) old.remove();
    const h = brLkChip(el.dataset.bs), u = el.querySelector('em');
    if(h && u) u.insertAdjacentHTML('beforebegin', h);
  });
  if(brDet && brDet.st === 'ok') brPanPaint();
}
function brLkDet(sha){
  const l = brLk(sha);
  if(!l) return '<i>' + esc(T('Made by')) + '</i><span class=brlkn>'
    + esc(T(BRL.repo === brRepo && BRL.st === 'load' ? 'Reading session links…' : 'No linked session')) + '</span>';
  return '<i>' + esc(T('Made by')) + '</i><span><code>' + esc(sid8(l.sid)) + '</code> '
    + esc(l.proj || '') + (l.tid ? ' <button class=brdc data-blw="' + esc(l.tid) + '" data-blc="' + esc(l.cwd || '') + '">'
    + esc(T('Open work')) + '</button>' : '') + '</span>'
    + '<i>' + esc(T('Agent')) + '</i><span>' + esc(l.agent || T('Main session')) + '</span>'
    + '<i>' + esc(T('Tokens')) + '</i><span title="' + esc(T("Tokens since this session's previous commit (estimate)")) + '">'
    + (l.tok || 0).toLocaleString() + ' (' + fmtTok(l.tok || 0) + ')</span>'
    + '<i>' + esc(T('Cost')) + '</i><span>$' + (+l.usd || 0).toFixed(2) + '</span>';
}
