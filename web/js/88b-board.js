// ── Branch tab «Board» (review queue + board) ─────────────────────────────
// Toolbar toggle «Work units | Board» (sidereus.brboard). The board groups every live session into 5 columns by priority:
//   «Blocked» > «Running» > «Review» > «Done» > «Waiting»; ended sessions not in the review queue are hidden and counted.
// ⛔Metadata only (AGENTS.md rule 1): name · branch · model · sid8 · targ (Agent description) · age · ctx % · file counts.
// ⚠Relays go through s2's rvRelay (preview + confirm, /api/dm) — the board never sends, runs git or kills anything itself.
let brBoardOn = false, brBdMenu = '', brBdHidden = 0, brBdLast = null;   // brBdLast = model of the last paint (brBdFind)
try { brBoardOn = UIS.getItem('sidereus.brboard') === '1'; } catch(e){ softErr('brboard-read', e); }
const BD_COLS = [['blk', 'Blocked'], ['run', 'Running'], ['rv', 'Review'], ['ok', 'Done'], ['idle', 'Waiting']];
const BD_EMPTY = { blk: 'Nothing blocked', run: 'Nothing running', rv: 'Nothing to review', ok: 'No reviewed changes', idle: 'No idle sessions' };
// Attention signals that put a card in «Blocked» (17-attention.js sig k).
const BD_BLOCK = new Set(['blocked', 'ask', 'abort', 'conflict', 'loop', 'stall', 'toolfail', 'fail', 'wreck', 'ctx95']);
// Relay kinds come from 88c RV_KINDS (single source). ⚠A function, not a const: 88c runs after this file (TDZ).
function bdRelay(){ return Object.entries(RV_KINDS); }
const BD_PRIMARY = { blk: 'go', run: 'stop', rv: 'fix', ok: 'commit', idle: 'go' };
function brBoardSave(){ try { UIS.setItem('sidereus.brboard', brBoardOn ? '1' : '0'); } catch(e){ softErr('brboard-save', e); } }
// Open (true) / leave (false) the board; also used by the «Review N» chip from other tabs.
function brBoard(open){
  brBoardOn = open !== false; brBdMenu = ''; brBoardSave();
  if(mainView !== 'br') return setMainView('br');
  if(brBoardOn) paintBr(); else loadBr(false);
}
function brReviewRows(){
  const r = (typeof REVIEW !== 'undefined' && REVIEW) ? REVIEW : null;
  return (r && Array.isArray(r.rows)) ? r.rows : [];
}
function brModeHtml(){
  return '<span id=brmd class=strseg title="' + esc(T('Work units = branch graph and worktrees · Board = sessions in columns by state')) + '">'
    + [['wu', 'Work units'], ['board', 'Board']].map(o => '<button data-bmd=' + o[0]
        + (((o[0] === 'board') === brBoardOn) ? ' class=on aria-pressed=true' : ' aria-pressed=false') + '>' + esc(T(o[1])) + '</button>').join('')
    + '</span>';
}
// Pure: sessions + review rows + attention rows -> {cols:{blk:[card]...}, hidden}. Tested with node (no DOM, no globals).
function brBoardModel(sess, rrows, arows){
  const sig = {}, rv = {}, cols = { blk: [], run: [], rv: [], ok: [], idle: [] };
  (arows || []).forEach(a => { if(a && a.sid) sig[a.sid] = (a.sigs || []).map(g => g.k); });
  (rrows || []).forEach(r => { if(r && r.sid) rv[r.sid] = r; });
  let hidden = 0;
  const seen = new Set();
  (sess || []).forEach(x => {
    if(!x) return;
    const sid = x.sid || '', r = sid ? rv[sid] : null;
    if(sid) seen.add(sid);
    const st = x.state || 'unknown', ended = st === 'done' || st === 'gone';
    if(ended && !r){ hidden++; return; }
    const ks = sig[sid] || [], bk = ks.find(k => BD_BLOCK.has(k));
    const nwf = Array.isArray(x.wf) ? x.wf.length : (x.wf ? 1 : 0);
    let col;
    if(!ended && (x.blocked || st === 'ask' || st === 'abort' || x.err || bk)) col = 'blk';
    else if(!ended && (st === 'tool' || st === 'think' || (x.sub || []).length || (x.bgs || []).length || nwf)) col = 'run';
    else if(r) col = r.done ? 'ok' : 'rv';
    else col = 'idle';
    cols[col].push({ col: col, x: x, r: r, why: bk || (x.blocked ? 'blocked' : (st === 'ask' || st === 'abort' ? st : (x.err ? 'err' : ''))) });
  });
  // Review rows whose session already left the list still belong in «Review»/«Done».
  (rrows || []).forEach(r => { if(!r || (r.sid && seen.has(r.sid))) return;
    const col = r.done ? 'ok' : 'rv'; cols[col].push({ col: col, x: null, r: r, why: '' }); });
  return { cols: cols, hidden: hidden };
}
function brBdKey(c){ return (c.x && c.x.sid) || (c.r && c.r.sid) || (c.x && c.x.cwd) || (c.r && c.r.cwd) || ''; }
function brBdRow(c){
  const x = c.x || {}, r = c.r;
  return r || { sid: x.sid || '', cwd: x.cwd || '', root: (x.wt && x.wt.root) || x.cwd || '', branch: x.branch || '' };
}
// Pure: newest viewer relay to session `sid` -> {st: 1 «Sent» | 2 «Delivered» (Stop hook receipt acks[id].hooked) | 3 «Confirm» (ack by m.to), lab, t (ns), id,
//   ping (a watcher only notified — `delivered` alone is not a hand-over)} or null.
//   ⚠Matched by sid + idSrc, not m.kind — decorate() (10-feed.js) overwrites m.kind with the subject tag.
function relayStat(sid, msgs, ack){
  if(!sid) return null;
  msgs = msgs || (typeof MSGS !== 'undefined' ? MSGS : []); ack = ack || (typeof ACK !== 'undefined' ? ACK : {});
  let m = null;
  for(const o of msgs) if(o && o.sid === sid && o.idSrc === 'viewer' && !o.room && (!m || +o.t >= +m.t)) m = o;
  if(!m) return null;
  const a = ack[m.id] || {};
  const st = (a.ack || []).some(x => x && x.who === m.to) ? 3 : (a.hooked || []).includes(m.to) ? 2 : 1;
  return { st: st, lab: ['', 'Sent', 'Delivered', 'Confirm'][st], t: +m.t || 0, id: m.id, ping: st === 1 && (a.delivered || []).includes(m.to) };
}
// Stage chip (label + relative time only — never the body, AGENTS.md rule 1).
function relayChipHtml(sid, cls){
  const r = relayStat(sid); if(!r) return '';
  return '<div class="' + cls + ' s' + r.st + '" title="' + esc(T('Last relay') + (r.ping ? ' · ' + T('watcher notified only') : '')) + '">→ ' + esc(r.st === 3 ? T('acked') : T(r.lab, 'short'))   // ⚠KE: the shared entry for this word is the button «Confirm»
    + (r.t ? ' · ' + esc(agoAt(Math.floor(r.t / 1e9))) : '') + '</div>';
}
function brBdName(x, r, cwd){ return (x.wt && !x.wt.main && x.wt.name) ? x.wt.name : (x.project || strShort(r.root || cwd) || '?'); }
function brBdCard(c){
  const x = c.x || {}, r = c.r || {}, key = brBdKey(c);
  const cwd = x.cwd || r.cwd || '', sid = x.sid || r.sid || '';
  const name = brBdName(x, r, cwd);
  const br = x.branch || r.branch || '';
  const pct = (x.win && x.ctx) ? Math.round(x.ctx / x.win * 100) : 0;
  const age = c.r && (c.col === 'rv' || c.col === 'ok') && r.since ? agoAt(r.since) : (x.ageSec != null ? AGO(ago(x.ageSec)) : '');
  const gm = String(x.git || '').match(/~(\d+)/);
  const files = r.nf ? '<span class=bdnf title="' + esc(T('Changed files')) + '">' + esc(T('{n} files', 'bare').replace('{n}', r.nf))
      + ' <b class=ba>+' + (+r.add || 0) + '</b> <b class=bd>−' + (+r.del || 0) + '</b></span>'
    : (gm ? '<span class=bdnf title="' + esc(T('Uncommitted changed files')) + '">~' + esc(gm[1]) + '</span>' : '');
  const why = c.why ? (c.why === 'err' ? T('Tool error') : (typeof attnLbl === 'function' ? attnLbl(c.why) : T(c.why))) : '';
  const doing = c.col === 'run' ? (x.targ || x.tool || '') : '';
  const pk = BD_PRIMARY[c.col], pl = RV_KINDS[pk];
  const menu = brBdMenu === key ? '<div class=bdmenu role=menu>' + bdRelay().map(o => '<button role=menuitem data-bdr="' + o[0]
      + '" data-bdk="' + esc(key) + '">' + esc(T(o[1], 'order')) + '</button>').join('') + '</div>' : '';
  return '<div class="bdc bd-' + c.col + (bdSelOn ? ' bdpick' + (bdSel.includes(sid) ? ' bdon' : '') : '') + '" data-bdo="' + esc(key) + '" data-bdc="' + esc(cwd) + '" data-bds="' + esc(sid) + '" data-bdrv="'
      + (c.r && (c.col === 'rv' || c.col === 'ok') ? 1 : 0) + '">' + bdSelCk(sid)
    + '<button class=bdt data-bdopen title="' + esc(cwd + (sid ? ' · ' + sid : '')) + '"><b>' + esc(name) + '</b>'
    + (br ? '<i>' + esc(br) + '</i>' : '') + '</button>'
    + '<div class=bdm>' + (x.model ? '<span>' + esc(x.model) + '</span>' : '') + (sid ? '<code>' + esc(sid8(sid)) + '</code>' : '')
    + (age ? '<em>' + esc(age) + '</em>' : '') + '</div>'
    + (why ? '<div class=bdw>' + esc(why) + '</div>' : '')
    + (doing ? '<div class=bdq title="' + esc(doing) + '">' + esc(doing) + '</div>' : '')
    + ((pct || files) ? '<div class=bdm>' + (pct ? '<span class="bdx' + (pct >= 85 ? ' hot' : '') + '" title="' + esc(T('Context')) + '">ctx ' + pct + '%</span>' : '') + files + '</div>' : '')
    + relayChipHtml(sid, 'bdrl')
    + '<div class=bda><button data-bdr="' + pk + '" data-bdk="' + esc(key) + '">' + esc(T(pl, 'order')) + '</button>' + termBtnHtml(c.x, 'bd')
    + '<button class=bdmb data-bdm="' + esc(key) + '" aria-haspopup=menu aria-expanded=' + (menu ? 'true' : 'false') + '>' + esc(T('Relay ▾')) + '</button>'
    + menu + '</div></div>';
}
function brBdModelNow(){ return brBoardModel(typeof SESS !== 'undefined' ? SESS : [], brReviewRows(), (typeof ATTN !== 'undefined' && ATTN && ATTN.rows) || []); }
function brBoardHtml(){
  const m = brBdLast = brBdModelNow();
  brBdHidden = m.hidden; bdSelSync(m);   // 88f «Select» mode
  const all = BD_COLS.reduce((n, c) => n + m.cols[c[0]].length, 0);
  return '<div class=bdtab><div class="wvh wvht"><b>' + esc(T('Board')) + '</b><span>' + esc(T('Sessions')) + ' ' + all
    + (m.hidden ? ' · ' + esc(T('{n} ended hidden').replace('{n}', m.hidden)) : '') + '</span>' + bdSelHead() + bdSelBar() + '</div>'
    + '<div class=bdcols>' + BD_COLS.map(c => {
      const cs = m.cols[c[0]];
      return '<section class="bdcol bd-' + c[0] + '"><h4>' + esc(T(c[1])) + '<span>' + cs.length + '</span></h4>'
        + (cs.length ? cs.map(brBdCard).join('') : '<div class=bde>' + esc(T(BD_EMPTY[c[0]])) + '</div>') + '</section>';
    }).join('') + '</div></div>';
}
function brBoardPaint(){
  if(mainView !== 'br') return;
  const box = document.getElementById('feed');
  if(!box) return;
  const h = brBoardHtml();
  tbSet('br', brModeHtml() + '<span class=tbx>' + (brBdHidden ? '<span class=bdhid>'
    + esc(T('{n} ended hidden').replace('{n}', brBdHidden)) + '</span>' : '') + '</span>');
  // ⚠paintBr writes #feed.innerHTML directly, so compare against our own copy and check the board is still mounted.
  if(box._bd === h && box.querySelector(':scope > .bdtab')) return;
  const fk = document.activeElement && box.contains(document.activeElement) ? document.activeElement : null;
  const fsel = fk && fk.dataset ? (fk.dataset.bdr ? '[data-bdr="' + fk.dataset.bdr + '"][data-bdk="' + CSS.escape(fk.dataset.bdk || '') + '"]'
    : fk.dataset.bdm ? '[data-bdm="' + CSS.escape(fk.dataset.bdm) + '"]' : fk.dataset.bdck ? '[data-bdck="' + CSS.escape(fk.dataset.bdck) + '"]'
    : ['data-bdsel', 'data-bdsm', 'data-bdsx'].map(a => '[' + a + ']').find(q => fk.matches(q)) || '') : '';
  box._bd = h; box._sh = null; box.innerHTML = h;
  if(fsel){ const n = box.querySelector(fsel); if(n) n.focus({ preventScroll: true }); }   // poll repaint keeps keyboard focus
}
function brBoardTick(){ if(mainView === 'br' && brBoardOn) brBoardPaint(); bdmqPaint(); }
function brBdFind(key){
  const m = brBdLast || brBdModelNow();
  for(const c of BD_COLS) for(const k of m.cols[c[0]]) if(brBdKey(k) === key) return k;
  return null;
}
function brBdRelay(key, kind){
  const c = brBdFind(key);
  brBdMenu = ''; brBoardPaint();
  const el = document.querySelector('#feed [data-bdm="' + CSS.escape(key) + '"]');   // focus returns here after the preview
  if(!c) return;
  if(typeof rvRelay !== 'function') return note(T('Relay is not available yet'));
  try { rvRelay(brBdRow(c), kind, '', el); } catch(e){ softErr('rvRelay', e); }
}
function brBdOpen(card, el){
  const cwd = card.dataset.bdc || '', sid = card.dataset.bds || '';
  if(card.dataset.bdrv === '1' && typeof rvOpen === 'function') return rvOpen(cwd, sid, el);
  if(cwd) return wkPopup(cwd, 'sess:' + cwd + (sid ? '|' + sid : ''));
  const x = (SESS || []).find(s => s && s.sid === sid); if(x) try { cpGo(x); } catch(e){ softErr('cpGo', e); }
}
// One delegated listener each (poll repaints replace the nodes).
document.addEventListener('click', e => {
  const t = e.target;
  if(!t || !t.closest) return;
  const md = t.closest('#tbbr [data-bmd]');
  if(md){ const on = md.dataset.bmd === 'board'; if(on !== brBoardOn) brBoard(on); return; }
  if(!t.closest('#feed .bdtab')){ if(brBdMenu && !t.closest('.bdmenu')){ brBdMenu = ''; brBoardPaint(); } return; }
  if(t.closest('.bdck, .bdsbar, [data-bdsel]')) return;   // «Select» mode — 88f's own listeners
  const mb = t.closest('[data-bdm]');
  if(mb){ brBdMenu = brBdMenu === mb.dataset.bdm ? '' : mb.dataset.bdm; brBoardPaint();
    const n = document.querySelector('#feed .bdmenu button'); if(n) n.focus({ preventScroll: true }); return; }
  const rb = t.closest('[data-bdr]');
  if(rb) return brBdRelay(rb.dataset.bdk || '', rb.dataset.bdr);
  if(brBdMenu){ brBdMenu = ''; brBoardPaint(); return; }
  const card = t.closest('.bdc[data-bdo]');
  if(card) brBdOpen(card, card.querySelector('.bdt'));
});
// ⚠Window capture: runs before 08-ui-kit's document-capture Esc, so an open review drawer stays open — Esc shuts only the menu.
window.addEventListener('keydown', e => {
  if(e.key !== 'Escape' || !brBdMenu || e.defaultPrevented || e.isComposing) return;
  const k = brBdMenu; e.preventDefault(); e.stopPropagation(); brBdMenu = ''; brBoardPaint();
  const b = document.querySelector('#feed [data-bdm="' + CSS.escape(k) + '"]'); if(b) b.focus({ preventScroll: true });
}, true);
