// ── Timeline toolbar «Changes» chip: files changed vs the auto baseline in the followed session's repo (view only, metadata only) ──
// Data: /api/git/diff?view=rail&base=auto (numstat + base, no patch). Fetched by tlgTick only while the Timeline tab is shown.
// Click opens the diff window at the same baseline; file tree, other baselines, untracked files and repo tabs live there (35c diffShow).
// ★The right rail was removed: at 1100 it left the Gantt ~386px and hid most bar labels; one chip keeps the count at every width.
const TLG_TTL_S = 30;
let tlgSel = '';   // chosen cpKey ('' = auto, latest active); kept across refresh by 97b (sidereus.tlgsel)
const tlgC = {};   // cwd -> {at, d, busy}
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
// Followed session: the chosen one, else (auto, or the chosen one disappeared) the most recently active session.
function tlgTarget(){
  const all = tlgSessions();
  let row = tlgSel ? all.find(x => cpKey(x) === tlgSel) : null;
  if(tlgSel && !row && all.length) tlgSel = '';   // ⚠not before the first /api/state (SESS = []) — a restored pick would be wiped
  const how = row ? 'pick' : 'auto';
  row = row || all[0];
  if(!row) return null;
  return {cwd: row.cwd, row, how, all, key: cpKey(row), ck: row.cwd, sid: (row.plat || 'cc') === 'cc' ? (row.sid || '') : ''};
}
// Session combobox (08b ppComboHtml, same as Pipelines/Structure/Branches), only when there is a choice (2+ sessions).
// Rows are project · sid · state, tooltip cwd · sid (metadata only); the first row 'auto' = tlgSel '' (follow the latest active).
const TLG_AUTO = 'auto';   // ⚠never a cpKey ('s:'/'c:' prefix), so 97b cannot restore it as a pick
function tlgProj(x){ return x.project || x.cwd.split('/').pop() || x.cwd; }
function tlgNote(x){ return [x.sid ? sid8(x.sid) : '', x.state ? (stateLbl(x.state) || T(x.state)) : ''].filter(Boolean).join(' · '); }
function tlgSelHtml(tg){
  if(!tg || tg.all.length < 2) return '';
  const AL = T('Auto (latest active)', 'chip');
  const it = x => ({ p: cpKey(x), name: tlgProj(x), note: tlgNote(x), tip: x.cwd + (x.sid ? ' · ' + x.sid : '') });
  const items = [Object.assign(it(tg.all[0]), { p: TLG_AUTO, auto: true })].concat(tg.all.map(it));
  const cur = tg.how === 'auto' ? TLG_AUTO : tg.key;
  const row = (e, i) => '<div class="cmdki' + (PPS && i === PPS.i ? ' on' : '') + (e.p === cur ? ' ppcur' : '') + '" role=option data-ppi="' + i + '" title="' + esc(e.tip) + '">'
    + '<span class=cmdkp>' + esc(e.auto ? AL : e.name) + '</span><span class=cmdkc>' + esc(e.auto ? [e.name, e.note].filter(Boolean).join(' · ') : e.note) + '</span></div>';
  const flat = q => {
    const s = String(q || '').trim().toLowerCase();
    return items.filter(e => !s || [e.name, e.tip, e.auto ? AL : ''].some(v => String(v).toLowerCase().includes(s)));
  };
  return ppComboHtml({ k: 'tlgs', label: T('Session'), items: items, cur: cur, ph: T('Find a session'), empty: T('No matching sessions'), flat: flat, rowHtml: row,
    tip: e => (e.auto ? AL + '\n' : '') + e.tip, badge: e => e.auto ? '<span class=tlgau>' + esc(T('auto', 'mark')) + '</span>' : '',
    pick: p => { tlgSel = p === TLG_AUTO ? '' : p; tlgKeepSave(); tlgTick(); } });
}
// «Changes · N files +a −d» (+ «· ⚠ n shared»); no target or no reply yet = «Changes» alone.
function tlgChipInner(tg){
  const d = tg && (tlgC[tg.ck] || {}).d;
  let body = esc(T('Changes', 'chip'));
  if(d && d.ok){
    const hid = (d.files || []).filter(f => f.new), sum = k => hid.reduce((s, f) => s + (f[k] || 0), 0);
    body += esc(' · ' + TV({msg: tlgShownN(d) === 1 ? '{n} file' : '{n} files', vars: {n: tlgShownN(d)}}) + ' ') + tlgNum(Math.max(0, (d.add || 0) - sum('add')), Math.max(0, (d.del || 0) - sum('del')));
    const sh = tlgShared(d);
    if(sh.length) body += '<span class=tlgsh title="' + esc(T('Also edited by another live session within 30 min:') + '\n' + sh.join('\n')) + '">'
      + esc(' · ⚠ ' + TV({msg: '{n} shared', vars: {n: sh.length}})) + '</span>';
  }
  const tip = T('Open the changes in the diff window (git · view only)') + (tg ? '\n' + tg.cwd : '');
  return tlgSelHtml(tg) + '<button type=button class="tlrf tlgcp" id=tlgcp' + (tg ? '' : ' disabled') + ' title="' + esc(tip) + '">' + body + '</button>';
}
function tlgChipHtml(){ return '<span class=tlgb id=tlgb>' + tlgChipInner(tlgTarget()) + '</span>'; }
// Id of the focused chip control, or ''. paintTl and tlgPaint refocus it after a rebuild.
function tlgFocusId(){
  const ae = document.activeElement;
  return ae && ae.id === 'tlgcp' ? ae.id : '';
}
function tlgPaint(){
  const el = document.getElementById('tlgb');
  if(!el) return;
  if(popIsOpen('ppop')) return;   // ⚠a repaint would replace the session picker's opener under its popover
  const fo = tlgFocusId();
  if(!setHtml(el, tlgChipInner(tlgTarget()))) return;
  if(el.parentElement) el.parentElement._sh = null;   // ⚠the toolbar slot's setHtml cache no longer matches its DOM; the next tbSet must rewrite
  if(fo){ const f = document.getElementById(fo); if(f) f.focus({preventScroll: true}); }
  tlgWire();
}
function tlgFetch(tg, force){
  const c = tlgC[tg.ck] || (tlgC[tg.ck] = {at: 0, d: null, busy: false});
  if(c.busy || (!force && Date.now() - c.at < TLG_TTL_S * 1000)) return;
  c.busy = true;
  getJSON('/api/git/diff?view=rail&cwd=' + encodeURIComponent(tg.cwd) + '&base=auto')
    .then(j => { c.d = j; }, () => { if(!c.d) c.d = {ok: false}; })
    .then(() => { c.at = Date.now(); c.busy = false; tlgPaint(); });
}
// Called from poll() (2.5 s) and the tab switch; fetches at most once per TLG_TTL_S, only while the Timeline is shown and visible.
function tlgTick(){
  if(mainView !== 'time' || document.hidden) return;
  const tg = tlgTarget();
  if(tg) tlgFetch(tg);
  tlgPaint();
}
// Chip click -> the existing diff window at the chip's baseline; &sid lets that window offer «Since session start».
function tlgOpen(){
  const tg = tlgTarget();
  if(!tg) return;
  const d = (tlgC[tg.ck] || {}).d;
  loadDiff(tg.cwd, '', d && d.ok && d.base ? 'b:' + d.base : 'work', '', tg.sid);
}
function tlgWire(){
  const b = document.getElementById('tlgcp');
  if(b) b.onclick = tlgOpen;
}
