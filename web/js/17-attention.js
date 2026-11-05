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
// Logged-in mailbox id: identity.json, or a Codex launcher id with a read cursor (src env, server-checked in dm_target_error).
// ⚠env on a Claude row is MAILBOX_ME from ~/.claude.json — the server refuses it, so cx rows only.
function mboxIn(x){
  return !!(x && x.mbox && (x.mboxSrc === 'identity' || (x.plat === 'cx' && x.mboxSrc === 'env')));
}
// Mailbox recipient of a row's session (same rule as the work-log composer wkcTarget): id only when logged in.
function attnRpTo(s){
  const id = (mboxIn(s) && s.mbox) || '', pr = (typeof PRES === 'object' && PRES || {})[id];
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
// «Ask to check» on a background-shell row: Sidereus composes the text, so preview + Confirm (rule 7); one row at a time.
// ⚠body is fixed when the preview opens: what Confirm sends is exactly what was shown. Numbers only, never shell labels/output.
let attnAsk = {id: '', to: '', body: '', busy: false};
const ATTN_BG_KINDS = ['bglong', 'bgidle'];
function attnAskSig(sigs){ for(const k of ATTN_BG_KINDS){ const g = (sigs || []).find(s => s.k === k); if(g) return g; } return null; }
function attnAskBody(k, min){
  return (k === 'bglong' ? 'Background task running ' : 'Background shell quiet ') + Math.max(0, Math.floor(+min || 0))
    + ' min — check whether it is still needed or stuck, and report back';
}
function attnAskHTML(a){
  return '<div class="atrp atask"><span class=atrpto>→ <b>' + esc(a.to) + '</b></span><pre class=atpre>' + esc(a.body) + '</pre>'
    + '<button class="wkrgb archok" data-aa="asks"' + (a.busy ? ' disabled' : '') + '>' + esc(T('Confirm — send')) + '</button>'
    + '<button class=atb data-aa="askx">' + esc(T('Cancel')) + '</button></div>';
}
// Sent marks {rowId: {t}} (unix s). Per-entry writes like attnAckSave. ⚠Only a mark at/after the signal's since shows: a new episode starts clean.
function attnAskLoad(){ const v = lsJson('mbAttnAsk', {}); return (v && typeof v === 'object') ? v : {}; }
function attnAskSave(id, v){
  if(typeof UIS !== 'undefined' && UIS && typeof UIS.patch === 'function') return UIS.patch('mbAttnAsk', id, v);
  const o = attnAskLoad(); if(v === null) delete o[id]; else o[id] = v; lsSetJson('mbAttnAsk', o);
}
// Row parts: button (disabled with the «Reply» reason when not logged in), sent mark, open preview.
function attnAskRow(x, to){
  const g = attnAskSig(x.vis);
  if(!g) return {btn: '', box: ''};
  const t = attnAskAt(x.id, g), dis = '<button class=atb disabled title="' + esc(T('Not logged into the mailbox — cannot receive')) + '">' + esc(T('Ask to check')) + '</button>';
  const btn = (to.id ? '<button class=atb data-aa="ask" title="' + esc(T('Preview a one-line request to check its background task, then confirm to send')) + '">' + esc(T('Ask to check')) + '</button>' : dis)
    + (t ? '<span class=atck>' + esc(T('Check requested')) + ' · ' + esc(agoAt(t)) + '</span>' : '');
  return {btn, box: attnAsk.id === x.id && attnAsk.to ? attnAskHTML(attnAsk) : ''};
}
// Open the preview only; nothing is posted until «Confirm — send». X = whole minutes since the signal's since.
function attnAskOpen(id, r, s){
  const g = attnAskSig(r && r.sigs), to = attnRpTo(s).id;
  if(!id || !to || !g) return false;
  attnRpClose();
  attnAsk = {id, to, body: attnAskBody(g.k, g.since ? (Date.now() / 1000 - g.since) / 60 : 0), busy: false};
  return true;
}
function attnAskAt(id, g){ const e = attnAskLoad()[id], t = e && +e.t || 0; return t && g && t + ATTN_ACK_TOL >= (g.since || 0) ? t : 0; }
async function attnAskSend(redraw){
  const a = attnAsk;
  if(a.busy || !a.id || !a.to || !a.body) return;
  a.busy = true;
  try{
    const j = await postJSON('/api/dm', {to: a.to, body: a.body});
    if(!j || !j.ok) throw new Error((j && j.error) || '?');
    const now = Math.floor(Date.now() / 1000), old = attnAskLoad();
    for(const k in old) if(!(old[k] && +old[k].t > now - 86400)) attnAskSave(k, null);   // marks older than a day can no longer show
    attnAskSave(a.id, {t: now});
    attnAsk = {id: '', to: '', body: '', busy: false}; note(T('Sent to {n}').replace('{n}', a.to));
  }catch(e){ a.busy = false; note(T('Could not send') + ': ' + e.message); }
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
                   done:'Done', bgdone:'Background done', conflict:'Conflict risk', gone:'Disconnected', mailidle:'Mail waiting',
                   bgidle:'Idle shells', bglong:'Long background' };
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
    case 'ask': return / · 이후 작업 계속$/.test(w) ? 'Awaiting answer · kept working' : 'Awaiting answer';   // card-held ask: session worked on after asking
    case 'abort': return 'Interrupted — needs a new instruction';
    case 'ctx95': return 'Context ' + n + '% — auto-compact soon';
    case 'ctx85': return 'Context ' + n + '%';
    case 'wreck': return 'Leftover edits' + (n ? ' in ' + n + ' files' : '');
    case 'stall': return 'Subagent stalled ' + U(n, 'm') + ' · parent waiting';
    case 'loop': { const m = w.match(/^(.*?) 같은 호출 (\d+)회/); return 'Same action repeated ' + (m ? m[2] + '× · ' + m[1] : n + '×'); }
    case 'toolfail': { const m = w.match(/(\d+)회 반복 · (.*)$/); return 'Same error repeated ' + (m ? m[1] + '× · ' + m[2] : n + '×'); }
    case 'fail': { const m = w.match(/등 (\d+)건/); return 'Failure alert' + (m ? ' (' + m[1] + ')' : ''); }
    case 'mailidle': { const m = w.match(/(\d+)\D+(\d+)/); return T('Mail waiting · session idle') + (m ? ' · ' + PL(m[1], 'message') + ' · ' + U(m[2], 'm') : ''); }
    case 'done': return 'Done · waiting for input ' + U(n, /초$/.test(w) ? 's' : 'm');   // ⚠server sends seconds under 60 s
    case 'bgdone': return PL(n, 'agent completion') + ' unread';
    case 'bgidle': { const m = w.match(/(\d+)\D+(\d+)\D+(\d+)/); return m ? PL(m[1], 'background shell') + ' · ' + m[2] + ' idle · longest ' + U(m[3], 'm') : 'Idle shells'; }
    case 'bglong': { const m = w.match(/(\d+)\D+(\d+)/), q = w.match(/무출력 (\d+)/);
      return m ? 'Long background ' + m[1] + ' · longest ' + m[2] + ' min' + (q ? ' · ' + q[1] + ' idle' : '') : 'Long background'; }
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
// Per-entry writes (v null = remove): another tab's acks/snoozes survive. ⚠Never write the whole map back; no UIS.patch (harness) = whole-map fallback.
function attnSnzSave(key, v){
  if(typeof UIS !== 'undefined' && UIS && typeof UIS.patch === 'function') return UIS.patch('mbAttnSnooze', key, v);
  const o = attnSnzLoad(); if(v === null) delete o[key]; else o[key] = v; lsSetJson('mbAttnSnooze', o);
}
// Click-to-dismiss: {rowId: {s: sorted sig kinds, t: top since}}. A new signal set or a new episode (since moved > 2 s) brings the row back.
// ⚠Server `since` jitters ±1 s per poll (now - age, int-truncated), so since is matched with tolerance, never by string equality.
const ATTN_ACK_TOL = 2;
function attnAckLoad(){ const v = lsJson('mbAttnAck', {}); return (v && typeof v === 'object') ? v : {}; }
function attnAckSave(id, v){   // same per-entry rule as attnSnzSave
  if(typeof UIS !== 'undefined' && UIS && typeof UIS.patch === 'function') return UIS.patch('mbAttnAck', id, v);
  const o = attnAckLoad(); if(v === null) delete o[id]; else o[id] = v; lsSetJson('mbAttnAck', o);
}
// Row identity: sid, else cwd — rows with an empty sid must not share one ack/snooze slot.
function attnRowId(r){ return r.sid || ('cwd:' + (r.cwd || '')); }
// ⚠A non-top ask/blocked adds '|a<since>': a re-ask under a higher-scored top keeps kinds and top since, so it needs its own since.
function attnAckKey(vis, top){
  const al = vis.filter(s => s !== top && typeof ALARM_TERM_KINDS !== 'undefined' && ALARM_TERM_KINDS.has(s.k)).map(s => s.since || 0);
  return vis.map(s => s.k).sort().join(',') + '|' + ((top && top.since) || 0) + (al.length ? '|a' + Math.max(...al) : '');
}
// Stored value -> {s, t[, a]}; legacy string acks were 'sid|kinds|since'.
function attnAckParse(v){
  if(v && typeof v === 'object'){ const o = { s: String(v.s || ''), t: +v.t || 0 }; if(v.a !== undefined) o.a = +v.a || 0; return o; }
  if(typeof v !== 'string') return null;
  const p = v.split('|'); const al = /^a\d/.test(p[p.length - 1] || '') ? +p.pop().slice(1) : undefined;
  if(p.length < 2) return null;
  const t = +p.pop(), o = { s: p.pop(), t: t || 0 }; if(al !== undefined) o.a = al || 0; return o;
}
function attnAckHit(stored, key){
  const a = attnAckParse(stored), b = attnAckParse(key);
  if(!(a && b && a.s === b.s)) return false;
  if(a.a !== undefined && b.a !== undefined && b.a > a.a + ATTN_ACK_TOL) return false;   // newer non-top ask/blocked; no stored a = legacy, as before
  // ⚠blocked since = newest open subagent mark, so it moves back as siblings leave; only a NEWER wait re-shows the row.
  if(a.s.split(',').includes('blocked')) return b.t <= a.t + ATTN_ACK_TOL;
  return Math.abs(a.t - b.t) <= ATTN_ACK_TOL;
}
// «Done» / row click: ack this one request (row id + its signal key). ⚠Never ack by session alone — a new request must show again.
function attnDone(id, key){
  const a = attnAckParse(key); if(!id || !key || !a) return false;
  attnAckSave(id, a); return true;
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
// -> {shown:[row], resp:[row], info:[row], snoozed:n}. Each row gets vis (policy-visible sigs), score, why, since, badge.
function attnRows(){
  const rows = (ATTN && ATTN.rows) || [], now = Date.now(), snz = attnSnzLoad(), ack = attnAckLoad();
  const ackKeep = {}, snzGone = [];
  const live = new Set();
  const out = [], low = []; let snoozed = 0, quiet = 0;
  for(const r of rows){
    const id = attnRowId(r);
    const vis = (r.sigs || []).filter(s => attnPolOf(s.k) !== 'hide');
    for(const s of r.sigs || []) live.add(id + '|' + s.k);
    if(!vis.length) continue;
    // Snooze value: number (until) | 'clear' | {u: until|'clear', t: since}. ⚠A newer ask/blocked since = a new question, so it wakes.
    const on = s => { let e = snz[id + '|' + s.k];
      if(e && typeof e === 'object'){
        if(ALARM_TERM_KINDS.has(s.k) && (s.since || 0) > (+e.t || 0) + ATTN_ACK_TOL){ delete snz[id + '|' + s.k]; snzGone.push(id + '|' + s.k); return false; }
        e = e.u; }
      return e === 'clear' || (typeof e === 'number' && e > now); };
    const sz = vis.filter(on), un = vis.filter(s => !on(s));
    if(sz.length){
      const hi = s => Math.max(...s.map(x => x.pts || 0));
      if(!un.length || hi(un) <= hi(sz)){ snoozed++; continue; }
      for(const s of vis) if(snz[id + '|' + s.k] !== undefined){ delete snz[id + '|' + s.k]; snzGone.push(id + '|' + s.k); }   // woken by a higher signal
    }
    const top = vis[0];
    // A row needs the user if ANY visible signal is a badge kind, not only the top-scored one.
    const badge = vis.some(s => attnPolOf(s.k) === 'badge');
    // ⚠Group by kind (blocked/ask = «Needs your response»), never by score: a fail@60 must not outrank an ask@50.
    const resp = vis.some(s => ALARM_TERM_KINDS.has(s.k) && attnPolOf(s.k) === 'badge');   // ⚠a policy-demoted ask is not a response
    const mk = key => ({ r, id, vis, top, key, score: (top.pts || 0) + 5 * (vis.length - 1), since: top.since || r.since || 0,
               why: attnWhy(top) + (vis.length > 1 ? ' ' + T('+{n} more', 'tail').replace('{n}', vis.length - 1) : ''), badge, resp });
    // ⚠Below-threshold rows get key '' so a click never acks them: «N low-priority» must not shrink on click.
    if(!badge){ quiet++; low.push(mk('')); continue; }   // list-only: counted, rendered only when expanded
    // ⚠List-only kinds (done/bgdone/gone) come and go between polls; keying on them re-shows an acked row.
    const kv = vis.filter(s => attnPolOf(s.k) !== 'list');
    const key = attnAckKey(kv, kv[0]);
    if(attnAckHit(ack[id], key)){ ackKeep[id] = ack[id] && typeof ack[id] === 'object' ? ack[id] : attnAckParse(ack[id]); continue; }
    out.push(mk(key));
  }
  // housekeeping: expired timers, and 'clear' entries whose signal disappeared
  if(ATTN) for(const key in snz){ const o = snz[key], e = o && typeof o === 'object' ? o.u : o;
    if((typeof e === 'number' && e <= now) || (e === 'clear' && !live.has(key)) || (e !== 'clear' && typeof e !== 'number')){ delete snz[key]; snzGone.push(key); } }
  for(const k of snzGone) attnSnzSave(k, null);
  // prune acks whose session is gone or whose signal changed (legacy string acks are rewritten as objects)
  if(ATTN) for(const k in ack){ if(!(k in ackKeep)) attnAckSave(k, null); else if(ackKeep[k] !== ack[k]) attnAckSave(k, ackKeep[k]); }
  const cmp = (a, b) => (b.score - a.score) || (a.since - b.since);
  out.sort((a, b) => (b.resp - a.resp) || cmp(a, b)); low.sort(cmp);
  return { shown: out, resp: out.filter(x => x.resp), info: out.filter(x => !x.resp), snoozed, quiet, low };
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
  // ⚠typeof: older row harnesses load attnRowHTML without the «Ask to check» helpers.
  const ask = typeof attnAskRow === 'function' ? attnAskRow(x, to) : {btn: '', box: ''};
  const rzCmd = (r.sid && r.sid.length > 8 && r.cwd && s.plat === 'cc') ? resumeCmd(r.cwd, r.sid, s.acctDir) : '';
  const rzLbl = cpfbLabel(r.sid, T('Copy resume command')), rzBox = cpfbBox(r.sid, rzCmd, 'atcp', 'data-aa="rzx"');
  const b = (act, lbl, t) => '<button class=atb data-aa="' + act + '"' + (t ? ' title="' + esc(t) + '"' : '') + '>' + esc(lbl) + '</button>';
  const menu = attnMenu === x.id
    ? '<div class=atm><button data-aa="snz30">' + esc(T('30 min')) + '</button><button data-aa="snzclr" title="'
      + esc(T('Wakes automatically when a higher signal appears')) + '">' + esc(T('Until the signal clears')) + '</button></div>' : '';
  return '<div class="atr' + (x.key ? '' : ' low') + (x.resp ? ' resp' : '') + (ac ? ' ' + ac : '') + '" data-akey="' + esc(x.key) + '" data-aid="' + esc(x.id) + '" data-asid="' + esc(r.sid) + '" data-acwd="' + esc(r.cwd) + '" title="' + esc(tip) + '">'
    + '<div class=at1><i class="atd ' + tone + '"></i><b' + (r.project && r.project !== nm ? ' title="' + esc(r.project) + '"' : '') + '>' + esc(nm) + '</b>'
    + (r.branch ? '<span class=atbr>' + esc(r.branch) + '</span>' : '')
    + '<span class=atw>' + esc(x.why) + '</span><span class=ata>' + esc(x.since ? agoAt(x.since) : '') + '</span></div>'
    + '<div class=at2>' + b('work', T('Work log'),T("Open this session's work log"))
    + (hasDiff ? (isExt ? b('diff', T('Folder diff'), T('View changes (diff) in this folder — by folder, not by session'))
                        : b('diff', 'diff', T("View this session's changes (diff)"))) : '')
    + (rzCmd ? b('rz', rzLbl, rzCmd) : '') + termBtnHtml(s, 'at')
    + (to.id ? b('rp', T('Reply'), T('Send this session a one-line message')) : '<button class=atb disabled title="' + esc(T('Not logged into the mailbox — cannot receive')) + '">' + esc(T('Reply')) + '</button>')
    + ask.btn
    + (x.vis.some(g => g.k === 'bgdone') && attnSeenKeys(r).length ? b('seen', T('Seen'), T('Mark these agent completions read')) : '')
    + (x.key ? b('done', T('Done'), T('Hide this request; a new request from the session shows again')) + b('later', T('Later'), T('Snooze for 30 min')) : '')
    + '<span class=atl>' + esc(attnLife(x.top)) + '</span>'
    + '<button class="atb atx" data-aa="snz" title="' + esc(T('Snooze')) + '">⋯</button>' + menu + '</div>' + rzBox
    + (attnRp.id === x.id && attnRp.to ? attnRpHTML(attnRp.to, to.watch) : '')
    + ask.box + '</div>';
}
// ⚠innerHTML drops a focused row/button to <body>: keep the same row (same control), else the next, else the previous, else the list.
function attnFocusPick(oldAids, newAids, aid){
  if(newAids.indexOf(aid) >= 0) return aid;
  const i = oldAids.indexOf(aid);
  if(i < 0) return '';
  for(let j = i + 1; j < oldAids.length; j++) if(newAids.indexOf(oldAids[j]) >= 0) return oldAids[j];
  for(let j = i - 1; j >= 0; j--) if(newAids.indexOf(oldAids[j]) >= 0) return oldAids[j];
  return '';
}
function attnFocusOf(el){
  const a = document.activeElement, row = a && el.contains(a) && a.closest && a.closest('.atr');
  if(!row || a.matches('.atcp input, .atrpi')) return null;   // copy/reply boxes restore themselves below
  return {aid: row.getAttribute('data-aid') || '', aa: a === row ? '' : (a.getAttribute('data-aa') || ''),
          aids: [...el.querySelectorAll('.atr')].map(r => r.getAttribute('data-aid') || '')};
}
function attnFocusBack(el, fo){
  const rows = [...el.querySelectorAll('.atr')], id = attnFocusPick(fo.aids, rows.map(r => r.getAttribute('data-aid') || ''), fo.aid);
  const row = id ? rows.find(r => r.getAttribute('data-aid') === id) : null;
  let t = row && id === fo.aid && fo.aa ? row.querySelector('[data-aa="' + CSS.escape(fo.aa) + '"]') : null;
  if(!t) t = row || el;
  // ⚠A fresh row is not a tab stop until 98-a11y marks it on the next frame; mark it now so focus() lands.
  if(!t.hasAttribute('tabindex') && !/^(BUTTON|INPUT)$/.test(t.tagName)){ try{ a11yOne(t); }catch(e){ softErr('attnFocusBack', e); } if(!t.hasAttribute('tabindex')) t.tabIndex = -1; }
  t.focus({preventScroll: true});
}
function buildAttn(){
  const el = document.getElementById('attn');
  if(!el) return;
  const a = attnRows();
  let { snoozed, quiet, low: lowRows } = a, oth = '', resp = a.resp || a.shown.filter(x => x.resp), info = a.info || a.shown.filter(x => !x.resp);   // fallback: stubbed attnRows
  // ⚠Filter here only: attnRows/attnBadgeN feed the tab title and drawer badge, which count every account.
  const pk = acctPick('sess');
  if(pk && !ACC_OTH.attn){   // follows the Sessions account pick
    const main = x => { const s = attnSess(x.r); return !s || acctInPick(s, 'sess', pk); }, hide = resp.concat(info, attnLow ? lowRows : []).filter(x => !main(x));   // low rows only while their fold is open
    resp = resp.filter(main); info = info.filter(main); lowRows = lowRows.filter(main); quiet = lowRows.length;
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
  if(!resp.length && !info.length) h = '<div class="ath none">' + esc(T('No sessions need you')) + low + wake + '</div>' + lowH + oth;
  else {
    // ⚠«Needs your response» rows never fold; ATTN_MAX and «+N more» apply to FYI rows only (actAttnGo checks `info`).
    const vis = attnMore ? info : info.slice(0, ATTN_MAX), rest = info.length - vis.length;
    h = (resp.length ? '<div class="ath resp">' + esc(T('Needs your response')) + ' <b>' + resp.length + '</b></div>' + resp.map(attnRowHTML).join('') : '')
      + (info.length || quiet || snoozed ? '<div class="ath fyi">' + esc(T('For your information')) + ' <b>' + info.length + '</b>' + low + wake + '</div>' : '')
      + vis.map(attnRowHTML).join('')
      + (rest ? '<div class=atmore data-aa="more">' + esc(T('+{n} more').replace('{n}', rest)) + '</div>'
              : (attnMore && info.length > ATTN_MAX ? '<div class=atmore data-aa="more">' + esc(T('Collapse')) + '</div>' : ''))
      + lowH + oth;
  }
  if(h === attnHtml) return;     // poll is 2.5s; skip identical redraws so hover/menus stay put
  const had = !!el.querySelector('.atcp input'), foc = el.contains(document.activeElement) && document.activeElement.matches('.atcp input');
  const rpOld = el.querySelector('.atrpi'), rpFoc = !!rpOld && document.activeElement === rpOld, rpPos = rpFoc ? rpOld.selectionStart : -1;
  const fo = attnFocusOf(el);
  attnHtml = h; el.innerHTML = h;
  if(fo) attnFocusBack(el, fo);
  const cp = el.querySelector('.atcp input');
  if(cp && (!had || foc)){ cp.focus(); cp.select(); }   // select when the box appears; keep it selected across poll redraws
  // Restore the reply draft/caret; focus a newly opened box. ⚠preventScroll: opening it must not move the sidebar.
  const rp = el.querySelector('.atrpi');
  if(rp){ rp.value = attnRp.draft; rp.disabled = attnRp.busy;
    if(rpFoc || !rpOld){ rp.focus({preventScroll: true}); const p = rpPos >= 0 ? rpPos : rp.value.length; rp.setSelectionRange(p, p); } }
}
// Unfold «+N more» / «N low-priority» for a jump to a folded row (rail pill); same pref write as the «low» toggle. -> true if redrawn.
function attnUnfold(more, low){
  let ch = false;
  if(more && !attnMore){ attnMore = true; ch = true; }
  if(low && !attnLow){ attnLow = true; try{ UIS.setItem('mbAttnLow', '1'); }catch(e){ softErr('attnUnfold', e); } ch = true; }
  if(ch) buildAttn();
  return ch;
}
// Another tab changed attention prefs (UIS pull): repaint from the store. ⚠Not while the reply box has focus (next poll repaints); never scrolls.
function attnPrefSync(ks){
  if(!(ks || []).some(k => String(k).indexOf('mbAttn') === 0)) return;
  attnLow = UIS.getItem('mbAttnLow') === '1';
  const a = document.activeElement;
  if(a && a.matches && a.matches('.atrpi')) return;
  buildAlarm();
}
try{ UIS.onChange(attnPrefSync); }catch(e){ softErr('attnPrefSync', e); }
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
    if(act === 'wake'){ for(const k of Object.keys(attnSnzLoad())) attnSnzSave(k, null); return redraw(); }
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
      if(attnAsk.id === id) attnAsk = {id: '', to: '', body: '', busy: false};
      // ⚠A pid-less external pending row is never pruned by age, so the ack also drops it from the server store.
      const s = sid && attnSess(rowOf() || {sid});
      if(s && s.plat && s.plat !== 'cc') postJSON('/api/ext/dismiss', {sid}).catch(() => {});
      row.classList.add('gone'); attnMenu = '';
      setTimeout(redraw, 150);
    };
    if(act === 'work'){ openSession(cwd, 'sess:' + cwd + '|' + sid); attnSeen(rowOf()); if(!row.getAttribute('data-akey')) redraw(); return dismiss(); }
    // Handling a row (Done / Seen) closes the Sessions drawer only when an Attention chip opened it (sesdrAttn): the person came
    // for that row. Opened from «Sessions» it stays; a pinned column stays (sesdrOpen no-ops).
    if(act === 'seen'){ attnSeen(rowOf()); redraw(); if(sesdrAttn) sesdrOpen(false, false); return; }
    if(act === 'diff'){ loadDiff(cwd); return dismiss(); }
    // ★2026-09-27 «Copy resume command» looked dead: the row vanished at once, toast far away. ⚠Do not dismiss on rz: the row is needed until resumed.
    if(act === 'rz'){
      const cmd = resumeCmd(cwd, sid, ((SESS || []).find(x => sid && x.sid === sid) || {}).acctDir);   // extra root: its config dir
      if(!cmd) return;
      cpfbCopy(sid, cmd, redraw, T('Copied the resume command — paste it in a terminal'));
      return;
    }
    if(act === 'rzx'){ CPFB.box = ''; return redraw(); }
    if(act === 'done'){ dismiss(); if(sesdrAttn) sesdrOpen(false, false); return; }
    if(act === 'rp'){
      if(attnRp.id === id){ attnRpClose(); return redraw(); }
      const to = attnRpTo(attnSess(rowOf() || {sid, cwd})).id;
      if(!to) return;
      attnAsk = {id: '', to: '', body: '', busy: false};
      attnRp = {id, to, draft: '', busy: false}; return redraw();
    }
    if(act === 'rps') return attnRpSend(redraw);
    if(act === 'ask'){
      if(attnAsk.id === id){ attnAsk = {id: '', to: '', body: '', busy: false}; return redraw(); }
      const r = rowOf();
      if(attnAskOpen(id, r, attnSess(r || {sid, cwd}))) redraw();
      return;
    }
    if(act === 'askx'){ attnAsk = {id: '', to: '', body: '', busy: false}; return redraw(); }
    if(act === 'asks') return attnAskSend(redraw);
    if(act === 'snz'){ attnMenu = attnMenu === id ? '' : id; return redraw(); }
    if(act === 'snz30' || act === 'snzclr' || act === 'later'){
      const r = rowOf();
      const u = act === 'snzclr' ? 'clear' : Date.now() + ATTN_SNZ_MS;
      for(const g of (r && r.sigs) || []) attnSnzSave(id + '|' + g.k, {u, t: g.since || 0});
      attnMenu = ''; return redraw();
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
