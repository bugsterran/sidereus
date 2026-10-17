// ── "Sessions that need me now" strip (top of the sessions sidebar) ──────────────────
//   Source: /api/state.attention (sidereus/attention.py). ⛔Metadata only — renders project, branch, why, since, score, sigs[].k/why.
//   Sidereus stays read-only toward sessions: "resume" copies a command, nothing is sent.
//   ★This strip is now the source of the tab-title [N] and the top-bar count (replaced the blocked/ask/abort/85% cells).
let ATTN = null, attnMore = false, attnMenu = '', attnHtml = '';
// Copy feedback shared by «Copy resume command» here and «Copy command» (41b); kept in state so a redraw keeps it: {key, ok, until} on the button, box = key with the manual-copy box open.
const CPFB = {key: '', ok: false, until: 0, box: ''};
function cpfbLabel(key, idle){ return CPFB.key === key && CPFB.until > Date.now() ? T(CPFB.ok ? 'Copied ✓' : 'Copy failed — select and copy') : idle; }
function cpfbBox(key, cmd, cls, xAttr){
  return cmd && CPFB.box === key ? '<div class="' + cls + '"><input readonly spellcheck=false value="' + esc(cmd) + '" title="'
    + esc(T('Command is selected — press ⌘C to copy')) + '"><button ' + xAttr + ' title="' + esc(T('Close')) + '">×</button></div>' : '';
}
function cpfbCopy(key, cmd, redraw, okMsg){
  copyText(cmd).then(ok => {
    const until = Date.now() + 2500;
    CPFB.key = key; CPFB.ok = ok; CPFB.until = until; if(!ok) CPFB.box = key;
    note(ok ? okMsg : T('Could not copy — copy the command by hand'));
    redraw();
    setTimeout(() => { if(CPFB.until === until){ CPFB.until = 0; redraw(); } }, 2600);
  });
}
// Inline «Reply» composer: one row at a time. ⚠The draft lives here, not in the DOM — buildAttn replaces innerHTML on change.
let attnRp = {id: '', to: '', draft: '', busy: false};
// Mailbox recipient of a row's session (same rule as the work-log composer wkcTarget): id only when logged in.
function attnRpTo(s){
  const id = (s && s.mboxSrc === 'identity' && s.mbox) || '', pr = (typeof PRES === 'object' && PRES || {})[id];
  return {id, watch: !!(s && (s.mon || []).some(v => v && v.src === 'proc')) || !!(pr && pr.online && pr.source === 'watch')};
}
// ⚠The recipient line is the send preview (Enter sends with no confirm) — keep it visible. No body is ever rendered.
function attnRpHTML(to, watch){
  return '<div class=atrp><span class=atrpto>→ <b>' + esc(to) + '</b>' + (watch ? '' : ' <small>' + esc(T('No mailbox watch')) + '</small>') + '</span>'
    + '<input class=atrpi spellcheck=false aria-label="' + esc(T('Reply to this session')) + '" placeholder="' + esc(T('Reply — Enter to send · Esc to close')) + '">'
    + '<button class=atb data-aa="rps">' + esc(T('Send')) + '</button></div>';
}
function attnRpClose(){ attnRp = {id: '', to: '', draft: '', busy: false}; }
// Reply box keys: Enter sends, Esc closes and returns focus to that row's «Reply» (no scroll).
function attnRpKey(e, el){
  if(!(e.target && e.target.matches && e.target.matches('.atrpi'))) return;
  const redraw = () => { attnHtml = ''; buildAttn(); };
  if(e.key === 'Enter' && !e.isComposing){ e.preventDefault(); attnRp.draft = e.target.value; attnRpSend(redraw); return; }
  if(e.key !== 'Escape') return;
  e.preventDefault(); e.stopPropagation();
  const id = attnRp.id; attnRpClose(); redraw();
  const rows = el ? el.querySelectorAll('.atr') : [];
  for(const r of rows) if(r.getAttribute('data-aid') === id){ const b = r.querySelector('[data-aa="rp"]'); if(b) b.focus({preventScroll: true}); }
}
async function attnRpSend(redraw){
  const to = attnRp.to, body = attnRp.draft.trim();
  if(attnRp.busy || !to || !body) return;
  attnRp.busy = true;
  try{
    const j = await postJSON('/api/dm', {to, body});
    if(!j || !j.ok) throw new Error((j && j.error) || '?');
    attnRpClose(); note(T('Sent to {n}').replace('{n}', to));
  }catch(e){ attnRp.busy = false; note(T('Could not send') + ': ' + e.message); }   // note() sets textContent: no esc, no T() on data
  redraw();
}
let attnLow = (() => { try{ return UIS.getItem('mbAttnLow') === '1'; }catch(e){ return false; } })();   // «N low-priority» expanded
const ATTN_MAX = 5, ATTN_SNZ_MS = 30 * 60 * 1000;
// sig k -> alert-policy kind (15-alarms.js APOL). Kinds not listed have no policy and always count.
// ⚠'fail' merges the four failure cards server-side, so it follows the loudest of them.
const ATTN_APOL = { ask:'ask', abort:'abort', wreck:'fwreck', toolfail:'fcheck', stall:'agent', bgdone:'bgdone',
                    fail:['flimit','fwreck','fcheck','fcut'] };
// Show only what needs attention — list-only kinds are never rendered, whatever APOL says.
const ATTN_LIST_ONLY = new Set(['done', 'bgdone', 'gone']);
// ⚠Show through attnLbl() (88b and 89 read this table too): 'done' is 'Done|work' in Korean, unlike plain 'Done'.
const ATTN_LBL = { blocked:'Blocked', ask:'Awaiting answer', abort:'Aborted', ctx95:'Context 95%+', fail:'Failures', wreck:'Half-edited files',
                   stall:'Subagent stalled', loop:'Repeated calls', toolfail:'Tool failures', ctx85:'Context 85%+',
                   done:'Done', bgdone:'Background done', conflict:'Conflict risk', gone:'Disconnected' };
function attnLbl(k){ return T(ATTN_LBL[k] || k, 'work'); }
function attnPolOf(k){
  if(ATTN_LIST_ONLY.has(k)) return 'list';
  const m = ATTN_APOL[k];
  if(!m) return 'badge';
  if(Array.isArray(m)){ const v = m.map(apolOf); return v.includes('badge') ? 'badge' : (v.includes('list') ? 'list' : 'hide'); }
  return apolOf(m);
}
// ⚠Server `why` is Korean; in English rebuild it per k, pulling numbers/tool names out of the Korean text.
function attnWhy(g){
  const w = g.why || '';
  if(g.k === 'blocked' && w === 'subagent waiting for approval') return T(w);   // fixed perm_marks label, both languages
  // '<tool> waiting for approval' (perm_marks/live_probe): only the fixed phrase is translated, the tool name never goes through T().
  // ⚠Runs in every language: en used to drop the tool name and fall to the fixed «Waiting for permission».
  if(g.k === 'blocked'){
    const bt = typeof g.tool === 'string' ? g.tool : (/ waiting for approval$/.test(w) ? w.slice(0, -21) : null);
    if(bt) return bt + ' ' + T('waiting for approval');
    if(LANG !== 'en' && bt !== null) return T('waiting for approval');
    if(LANG !== 'en' && w === 'waiting for approval') return T(w);
  }
  if(LANG !== 'en') return w;
  const n = (w.match(/(\d+)/) || [])[1] || '';
  switch(g.k){
    case 'blocked': return 'Waiting for permission';
    case 'ask': return 'Awaiting answer';   // same wording as the activity strip
    case 'abort': return 'Interrupted — needs a new instruction';
    case 'ctx95': return 'Context ' + n + '% — auto-compact soon';
    case 'ctx85': return 'Context ' + n + '%';
    case 'wreck': return 'Leftover edits' + (n ? ' in ' + n + ' files' : '');
    case 'stall': return 'Subagent stalled ' + U(n, 'm') + ' · parent waiting';
    case 'loop': { const m = w.match(/^(.*?) 같은 호출 (\d+)회/); return 'Same action repeated ' + (m ? m[2] + '× · ' + m[1] : n + '×'); }
    case 'toolfail': { const m = w.match(/(\d+)회 반복 · (.*)$/); return 'Same error repeated ' + (m ? m[1] + '× · ' + m[2] : n + '×'); }
    case 'fail': { const m = w.match(/등 (\d+)건/); return 'Failure alert' + (m ? ' (' + m[1] + ')' : ''); }
    case 'done': return 'Done · waiting for input ' + U(n, 'm');
    case 'bgdone': return PL(n, 'agent completion') + ' unread';
    case 'gone': return w === '끊김?' ? 'Disconnected?' : 'Disconnected';
    case 'conflict': { const m = w.match(/파일 (\d+) · (세션|서브에이전트|에이전트) (.*)$/);
      return 'Conflict risk' + (m ? ' · ' + PL(m[1], 'file') + ' · ' + (m[2] === '세션' ? 'sessions ' : 'subagents ') + m[3].replace(/(^|, )메인(?=,|$)/g, '$1main') : ''); }
  }
  return w;
}
// Say how each signal leaves (live check vs auto-clear).
//   Failure cards (fail, wreck) stay after the fact and clear on resumed work (fail also at the server's `until` cap); the rest mirror the live state.
const ATTN_AFTER = new Set(['fail', 'wreck']);
function attnLife(g, now){
  if(!ATTN_AFTER.has(g.k)) return T('Live state — clears when resolved');
  const left = g.until ? Math.max(1, Math.ceil((g.until - (now || Date.now() / 1000)) / 60)) : 0;
  return (g.since ? T('at {t}').replace('{t}', LANG === 'en' ? CLK(new Date(g.since * 1000)) : hhmm(g.since)) + ' · ' : '') + T('clears when work resumes')
    + (left ? ' · ' + T('≤{n} min left').replace('{n}', left) : '');
}
function attnSnzLoad(){ const v = lsJson('mbAttnSnooze', {}); return (v && typeof v === 'object') ? v : {}; }
function attnSnzSave(v){ lsSetJson('mbAttnSnooze', v); }
// Click-to-dismiss: {rowId: {s: sorted sig kinds, t: top since}}. A new signal set or a new episode (since moved > 2 s) brings the row back.
// ⚠Server `since` jitters ±1 s per poll (now - age, int-truncated), so since is matched with tolerance, never by string equality.
const ATTN_ACK_TOL = 2;
function attnAckLoad(){ const v = lsJson('mbAttnAck', {}); return (v && typeof v === 'object') ? v : {}; }
function attnAckSave(v){ lsSetJson('mbAttnAck', v); }
// Row identity: sid, else cwd — rows with an empty sid must not share one ack/snooze slot.
function attnRowId(r){ return r.sid || ('cwd:' + (r.cwd || '')); }
function attnAckKey(vis, top){ return vis.map(s => s.k).sort().join(',') + '|' + ((top && top.since) || 0); }
// Stored value -> {s, t}; legacy string acks were 'sid|kinds|since'.
function attnAckParse(v){
  if(v && typeof v === 'object') return { s: String(v.s || ''), t: +v.t || 0 };
  if(typeof v !== 'string') return null;
  const p = v.split('|'); if(p.length < 2) return null;
  const t = +p.pop(); return { s: p.pop(), t: t || 0 };
}
function attnAckHit(stored, key){
  const a = attnAckParse(stored), b = attnAckParse(key);
  return !!(a && b && a.s === b.s && Math.abs(a.t - b.t) <= ATTN_ACK_TOL);
}
// «Done» / row click: ack this one request (row id + its signal key). ⚠Never ack by session alone — a new request must show again.
function attnDone(id, key){
  const a = attnAckParse(key); if(!id || !key || !a) return false;
  const ack = attnAckLoad(); ack[id] = a; attnAckSave(ack); return true;
}
// Card read keys behind a row's «agent completions unread» signal (server attention.py, at|kind|project).
function attnSeenKeys(r){ return [].concat(...((r && r.sigs) || []).filter(g => g.k === 'bgdone' && Array.isArray(g.keys)).map(g => g.keys)).filter(k => typeof k === 'string' && k); }
// «Seen» / opening the session: mark those cards read on the server (same store as the bell) and drop the signal locally until the next poll.
// ⚠Only bgdone: the mbAttnAck local ack never reached cards-read, so the row came back on every poll.
function attnSeen(r){
  const keys = attnSeenKeys(r);
  if(!keys.length) return false;
  r.sigs = r.sigs.filter(g => g.k !== 'bgdone');
  if(ATTN && ATTN.rows && !r.sigs.length) ATTN.rows = ATTN.rows.filter(x => x !== r);
  postJSON('/api/cards/read', {keys}).catch(() => note(T('Could not mark as read — check the server')));
  return true;
}
// -> {shown:[row], snoozed:n}. Each row gets vis (policy-visible sigs), score, why, since, badge.
function attnRows(){
  const rows = (ATTN && ATTN.rows) || [], now = Date.now(), snz = attnSnzLoad(), ack = attnAckLoad();
  let dirty = false, ackDirty = false;
  const ackKeep = {};
  const live = new Set();
  const out = [], low = []; let snoozed = 0, quiet = 0;
  for(const r of rows){
    const id = attnRowId(r);
    const vis = (r.sigs || []).filter(s => attnPolOf(s.k) !== 'hide');
    for(const s of r.sigs || []) live.add(id + '|' + s.k);
    if(!vis.length) continue;
    const on = s => { const e = snz[id + '|' + s.k]; return e === 'clear' || (typeof e === 'number' && e > now); };
    const sz = vis.filter(on), un = vis.filter(s => !on(s));
    if(sz.length){
      const hi = s => Math.max(...s.map(x => x.pts || 0));
      if(!un.length || hi(un) <= hi(sz)){ snoozed++; continue; }
      for(const s of vis) if(snz[id + '|' + s.k] !== undefined){ delete snz[id + '|' + s.k]; dirty = true; }   // woken by a higher signal
    }
    const top = vis[0];
    // A row needs the user if ANY visible signal is a badge kind, not only the top-scored one.
    const badge = vis.some(s => attnPolOf(s.k) === 'badge');
    const mk = key => ({ r, id, vis, top, key, score: (top.pts || 0) + 5 * (vis.length - 1), since: top.since || r.since || 0,
               why: attnWhy(top) + (vis.length > 1 ? ' ' + T('+{n} more', 'tail').replace('{n}', vis.length - 1) : ''), badge });
    // ⚠Below-threshold rows get key '' so a click never acks them: «N low-priority» must not shrink on click.
    if(!badge){ quiet++; low.push(mk('')); continue; }   // list-only: counted, rendered only when expanded
    const key = attnAckKey(vis, top);
    if(attnAckHit(ack[id], key)){ ackKeep[id] = ack[id] && typeof ack[id] === 'object' ? ack[id] : attnAckParse(ack[id]); continue; }
    out.push(mk(key));
  }
  // housekeeping: expired timers, and 'clear' entries whose signal disappeared
  if(ATTN) for(const key in snz){ const e = snz[key];
    if((typeof e === 'number' && e <= now) || (e === 'clear' && !live.has(key)) || (e !== 'clear' && typeof e !== 'number')){ delete snz[key]; dirty = true; } }
  if(dirty) attnSnzSave(snz);
  // prune acks whose session is gone or whose signal changed
  if(ATTN){ for(const k in ack) if(ackKeep[k] !== ack[k]){ ackDirty = true; break; } if(ackDirty) attnAckSave(ackKeep); }
  const cmp = (a, b) => (b.score - a.score) || (a.since - b.since);
  out.sort(cmp); low.sort(cmp);
  return { shown: out, snoozed, quiet, low };
}
function attnBadgeN(){ return attnRows().shown.filter(x => x.badge).length; }
function attnSess(r){ return (SESS || []).find(x => r.sid && x.sid === r.sid) || (r.sid ? null : tlLiveOf(r.cwd)) || null; }   // ⚠no cwd fallback for a sid row: it would pick another platform's session
// Same name as the board card (brBdName): wt.main == '' (main checkout) -> wt.name; linked worktree -> the session project.
function attnName(r, s){
  s = s || {};
  return (s.wt && !s.wt.main && s.wt.name) ? s.wt.name
    : (s.project || r.project || String(r.root || r.cwd || '').replace(/\/+$/, '').split('/').pop() || '?');
}
// Score tier colour — shared with the activity-strip pills (42-activity.js) so both read the same.
function attnTone(score){ return score >= 90 ? 'err' : (score >= 50 ? 'warn' : 'info'); }
// Row whose signals include «Blocked»/«Awaiting answer» -> sid when its terminal tab can be raised, else ''.
function attnTermSid(r){ return r && (r.sigs || []).some(g => ALARM_TERM_KINDS.has(g.k)) ? termJumpSid(r.sid) : ''; }
// Row body click: raise the terminal for a waiting-for-me row, else scroll + flash that session card.
function attnRowGo(r, sid, cwd){
  const js = attnTermSid(r);
  if(js) return termGo(js);
  cpGo(attnSess(r || {sid, cwd}) || {sid, cwd});
}
function attnRowHTML(x){
  const r = x.r, ss = attnSess(r), s = ss || {}, nm = attnName(r, s);
  const ac = ss ? acctRowCls(ss) : '', at = ss ? acctTip(ss) : '';   // account band only when the session is known
  const tone = attnTone(x.score);
  const tip = x.vis.map(g => attnLbl(g.k) + ' — ' + attnWhy(g) + (g.since ? ' · ' + agoAt(g.since) : '') + '\n   ' + attnLife(g)).join('\n')
    + '\n\n' + (attnTermSid(r) ? T('Click to open its terminal') : T(x.key ? 'Click to jump to that session card; the row hides until its signal changes' : 'Click to jump to that session card; low-priority rows stay listed'))
    + (at ? '\n' + at : '');
  const hasDiff = x.vis.some(g => g.k === 'wreck' || g.k === 'fail') || /~/.test(s.git || '');
  const isExt = !!extTid(s), to = attnRpTo(ss);
  const rzCmd = (r.sid && r.sid.length > 8 && r.cwd && s.plat === 'cc') ? resumeCmd(r.cwd, r.sid, s.acctDir) : '';
  const rzLbl = cpfbLabel(r.sid, T('Copy resume command')), rzBox = cpfbBox(r.sid, rzCmd, 'atcp', 'data-aa="rzx"');
  const b = (act, lbl, t) => '<button class=atb data-aa="' + act + '"' + (t ? ' title="' + esc(t) + '"' : '') + '>' + esc(lbl) + '</button>';
  const menu = attnMenu === x.id
    ? '<div class=atm><button data-aa="snz30">' + esc(T('30 min')) + '</button><button data-aa="snzclr" title="'
      + esc(T('Wakes automatically when a higher signal appears')) + '">' + esc(T('Until the signal clears')) + '</button></div>' : '';
  return '<div class="atr' + (x.key ? '' : ' low') + (ac ? ' ' + ac : '') + '" data-akey="' + esc(x.key) + '" data-aid="' + esc(x.id) + '" data-asid="' + esc(r.sid) + '" data-acwd="' + esc(r.cwd) + '" title="' + esc(tip) + '">'
    + '<div class=at1><i class="atd ' + tone + '"></i><b' + (r.project && r.project !== nm ? ' title="' + esc(r.project) + '"' : '') + '>' + esc(nm) + '</b>'
    + (r.branch ? '<span class=atbr>' + esc(r.branch) + '</span>' : '')
    + '<span class=atw>' + esc(x.why) + '</span><span class=ata>' + esc(x.since ? agoAt(x.since) : '') + '</span></div>'
    + '<div class=at2>' + b('work', T('Work log'),T("Open this session's work log"))
    + (hasDiff ? (isExt ? b('diff', T('Folder diff'), T('View changes (diff) in this folder — by folder, not by session'))
                        : b('diff', 'diff', T("View this session's changes (diff)"))) : '')
    + (rzCmd ? b('rz', rzLbl, rzCmd) : '') + termBtnHtml(s, 'at')
    + (to.id ? b('rp', T('Reply'), T('Send this session a one-line message')) : '<button class=atb disabled title="' + esc(T('Not logged into the mailbox — cannot receive')) + '">' + esc(T('Reply')) + '</button>')
    + (x.vis.some(g => g.k === 'bgdone') && attnSeenKeys(r).length ? b('seen', T('Seen'), T('Mark these agent completions read')) : '')
    + (x.key ? b('done', T('Done'), T('Hide this request; a new request from the session shows again')) + b('later', T('Later'), T('Snooze for 30 min')) : '')
    + '<span class=atl>' + esc(attnLife(x.top)) + '</span>'
    + '<button class="atb atx" data-aa="snz" title="' + esc(T('Snooze')) + '">⋯</button>' + menu + '</div>' + rzBox
    + (attnRp.id === x.id && attnRp.to ? attnRpHTML(attnRp.to, to.watch) : '') + '</div>';
}
function buildAttn(){
  const el = document.getElementById('attn');
  if(!el) return;
  let { shown, snoozed, quiet, low: lowRows } = attnRows(), oth = '';
  // ⚠Filter here only: attnRows/attnBadgeN feed the tab title and drawer badge, which count every account.
  const pk = acctPick('sess');
  if(pk && !ACC_OTH.attn){   // follows the Sessions account pick
    const main = x => { const s = attnSess(x.r); return !s || acctInPick(s, 'sess', pk); }, hide = (attnLow ? shown.concat(lowRows) : shown).filter(x => !main(x));   // low rows only while their fold is open
    shown = shown.filter(main); lowRows = lowRows.filter(main); quiet = lowRows.length;
    oth = acctOthHtml('attn', hide.length, hide.some(x => x.badge));
  }
  const wake = snoozed ? '<span class=atz data-aa="wake" title="' + esc(T('Wake all snoozed sessions')) + '">'
    + esc(T('snoozed {n}').replace('{n}', snoozed)) + '</span>' : '';
  // ★2026-09-24: «None» while /api/state.attention had 2 rows (list-only bgdone) read as a contradiction — say they exist.
  // ★2026-09-25: «2 low-priority» did nothing on click — it is now a toggle that lists those rows muted below.
  const low = quiet ? '<span class=atz data-aa="low" title="' + esc(T('Sessions with only low signals (done, background finished) — click to expand')) + '">'
    + esc(T('{n} low-priority').replace('{n}', quiet)) + (attnLow ? ' ▴' : ' ▾') + '</span>' : '';
  const lowH = attnLow ? lowRows.map(attnRowHTML).join('') : '';
  let h;
  if(!shown.length) h = '<div class="ath none">' + esc(T('No sessions need you')) + low + wake + '</div>' + lowH + oth;
  else {
    const vis = attnMore ? shown : shown.slice(0, ATTN_MAX), rest = shown.length - vis.length;
    h = '<div class=ath>' + esc(T('Attention')) + ' <b>' + shown.length + '</b>' + low + wake + '</div>'
      + vis.map(attnRowHTML).join('')
      + (rest ? '<div class=atmore data-aa="more">' + esc(T('+{n} more').replace('{n}', rest)) + '</div>'
              : (attnMore && shown.length > ATTN_MAX ? '<div class=atmore data-aa="more">' + esc(T('Collapse')) + '</div>' : ''))
      + lowH + oth;
  }
  if(h === attnHtml) return;     // poll is 2.5s; skip identical redraws so hover/menus stay put
  const had = !!el.querySelector('.atcp input'), foc = el.contains(document.activeElement) && document.activeElement.matches('.atcp input');
  const rpOld = el.querySelector('.atrpi'), rpFoc = !!rpOld && document.activeElement === rpOld, rpPos = rpFoc ? rpOld.selectionStart : -1;
  attnHtml = h; el.innerHTML = h;
  const cp = el.querySelector('.atcp input');
  if(cp && (!had || foc)){ cp.focus(); cp.select(); }   // select when the box appears; keep it selected across poll redraws
  // Restore the reply draft/caret; focus a newly opened box. ⚠preventScroll: opening it must not move the sidebar.
  const rp = el.querySelector('.atrpi');
  if(rp){ rp.value = attnRp.draft; rp.disabled = attnRp.busy;
    if(rpFoc || !rpOld){ rp.focus({preventScroll: true}); const p = rpPos >= 0 ? rpPos : rp.value.length; rp.setSelectionRange(p, p); } }
}
function attnTitle(){ if(!ISPOP && !ISWP && !ISBP) document.title = titleOf(attnBadgeN(), alarmBadgeN(), PAGE_NAME); }
(function(){
  const el = document.getElementById('attn');
  if(!el) return;
  el.onclick = (e) => {
    if(acctOthClick(e, () => { attnHtml = ''; buildAttn(); })) return;
    const t = e.target.closest && e.target.closest('[data-aa]');
    const row = e.target.closest && e.target.closest('.atr');
    const sid = row ? row.getAttribute('data-asid') : '', cwd = row ? row.getAttribute('data-acwd') : '', id = row ? row.getAttribute('data-aid') : '';
    const rowOf = () => ((ATTN && ATTN.rows) || []).find(x => attnRowId(x) === id);
    const act = t ? t.getAttribute('data-aa') : '';
    const redraw = () => { attnHtml = ''; buildAttn(); buildTodo(); attnTitle(); };
    if(act === 'more'){ attnMore = !attnMore; return redraw(); }
    if(act === 'wake'){ attnSnzSave({}); return redraw(); }
    if(act === 'low'){ attnLow = !attnLow; try{ UIS.setItem('mbAttnLow', attnLow ? '1' : ''); }catch(err){} return redraw(); }
    if(!row) return;
    e.stopPropagation();
    if(!act && e.target.closest('.atcp, .atrp')) return;   // clicks in the manual-copy box or reply box never jump/dismiss
    // acknowledge: fade out (150ms), then hide until the signal set / top since changes
    const dismiss = () => {
      const key = row.getAttribute('data-akey');
      if(!key || row.classList.contains('gone')) return;
      if(!attnDone(id, key)) return;
      if(attnRp.id === id) attnRpClose();
      // ⚠A pid-less external pending row is never pruned by age, so the ack also drops it from the server store.
      const s = sid && attnSess(rowOf() || {sid});
      if(s && s.plat && s.plat !== 'cc') postJSON('/api/ext/dismiss', {sid}).catch(() => {});
      row.classList.add('gone'); attnMenu = '';
      setTimeout(redraw, 150);
    };
    if(act === 'work'){ openSession(cwd, 'sess:' + cwd + '|' + sid); attnSeen(rowOf()); if(!row.getAttribute('data-akey')) redraw(); return dismiss(); }
    if(act === 'seen'){ attnSeen(rowOf()); return redraw(); }
    if(act === 'diff'){ loadDiff(cwd); return dismiss(); }
    // ★2026-09-27 «Copy resume command» looked dead: the row vanished at once, toast far away. ⚠Do not dismiss on rz: the row is needed until resumed.
    if(act === 'rz'){
      const cmd = resumeCmd(cwd, sid, ((SESS || []).find(x => sid && x.sid === sid) || {}).acctDir);   // extra root: its config dir
      if(!cmd) return;
      cpfbCopy(sid, cmd, redraw, T('Copied the resume command — paste it in a terminal'));
      return;
    }
    if(act === 'rzx'){ CPFB.box = ''; return redraw(); }
    if(act === 'done') return dismiss();
    if(act === 'rp'){
      if(attnRp.id === id){ attnRpClose(); return redraw(); }
      const to = attnRpTo(attnSess(rowOf() || {sid, cwd})).id;
      if(!to) return;
      attnRp = {id, to, draft: '', busy: false}; return redraw();
    }
    if(act === 'rps') return attnRpSend(redraw);
    if(act === 'snz'){ attnMenu = attnMenu === id ? '' : id; return redraw(); }
    if(act === 'snz30' || act === 'snzclr' || act === 'later'){
      const r = rowOf(), snz = attnSnzLoad();
      const v = act === 'snzclr' ? 'clear' : Date.now() + ATTN_SNZ_MS;
      for(const g of (r && r.sigs) || []) snz[id + '|' + g.k] = v;
      attnSnzSave(snz); attnMenu = ''; return redraw();
    }
    attnRowGo(rowOf(), sid, cwd);
    if(attnSeen(rowOf()) && !row.getAttribute('data-akey')) redraw();
    dismiss();
  };
  document.addEventListener('click', (e) => {
    if(attnMenu && !(e.target.closest && e.target.closest('#attn'))){ attnMenu = ''; attnHtml = ''; buildAttn(); }
  });
  el.addEventListener('input', e => { if(e.target.matches && e.target.matches('.atrpi')) attnRp.draft = e.target.value; });
  el.addEventListener('keydown', e => attnRpKey(e, el));
})();
