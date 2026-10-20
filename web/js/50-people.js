function buildPeople(){
  const now = Date.now() * 1e6;
  // ★Collect **only participants of the selected place** (2026-08-27: participants did not change with the room).
  // Before, members of all rooms + senders of all posts were collected, so the list stayed the same across rooms —
  // "who is in this room now" was unreadable. Send count and last send are also counted within that place only.
  const RM = place.indexOf('room:') === 0 ? place.slice(5) : '';
  const IN = MSGS.filter(m => inPlace(m, RM ? place : 'dm'));
  const ids = new Set();
  if(RM) ((ROOMS[RM] || {}).members || []).forEach(m => ids.add(m));   // Members count as participants even with no posts
  IN.forEach(m => { if(!m.selfaddr){ ids.add(m.from); if(m.to) ids.add(m.to); } });
  const lastSent = {}, sentN = {};
  IN.forEach(m => { if(m.selfaddr) return;
    if(!lastSent[m.from] || m.t > lastSent[m.from]) lastSent[m.from] = m.t;
    sentN[m.from] = (sentN[m.from] || 0) + 1; });
  // ⚠Named agoNs, not ago — a local `ago` would shadow the global ago() the rows below use. ns timestamps.
  const agoNs = t => { if(!t) return null; const s = Math.floor((now - t) / 1e9);
    return s < 60 ? T('just now') : AGO(ago(s)); };
  const people = [...ids].filter(Boolean).map(id => {
    const act = Math.max(lastSent[id] || 0, CUR[id] || 0);
    return { id: id, role: (PROF[id]||{}).role || '', read: CUR[id] || 0,
             sent: lastSent[id] || 0, n: sentN[id] || 0, act: act,
             mem: RM ? ((ROOMS[RM]||{}).members||[]).includes(id) : false,
             rooms: Object.keys(ROOMS).filter(r => (ROOMS[r].members||[]).includes(id)) };
  }).sort((a,b) => b.act - a.act)
  // ★**Remove participants quiet for over a day** (user instruction 2026-08-11) — ids that passed once long ago
  // stayed on the list and blurred "who is in this conversation now". Keep only current participants.
  // ⚠Ids with **no activity timestamps at all** (send, read cursor) have no basis for judgment, so keep them —
  // do not mix "old" with "unknown" (discipline repeated in this repo).
  // ★And **exempt anyone connected** (2026-08-21: being connected via ack means online).
  // Measured: room chat had merely been silent 24.4h, yet `repo-A`·`advocate` with heartbeats 1s ago were caught
  // by this filter and vanished entirely. Removing **someone attached right now** for being 'quiet' is wrong.
  .filter(p => { const pr = PRES[p.id] || {};
    if(pr.online || (pr.at && Date.now()/1000 - pr.at < 900)) return true;   // Connected — always keep
    return !p.act || (now - p.act) / 6e10 < 1440; });
  // ★**Show only connected people** (user instruction 2026-08-14) — before, everyone showed regardless of connection
  // and "who is in this room now" was invisible. presence (heartbeat) is the source of truth.
  // ⚠Keep **a count** of hidden people — deleting silently cannot tell "nobody" from "not shown".
  // ★Two-stage check — `watch` updates every second, but `mcp` is stamped **only on tool calls**.
  // Using only `online` (30s) drops peers that are actually working (measured: origin called 350s ago → dropped).
  // So with a watcher, use it as is; without, keep if **called within the last 15 min** (shown as ◐).
  const MCP_RECENT_S = 900;
  const nowS = Date.now() / 1000;
  const onlineNow = people.filter(p => { const pr = PRES[p.id] || {};
    return pr.online || (pr.at && nowS - pr.at < MCP_RECENT_S); });
  const hidden = people.length - onlineNow.length;
  const peopleShown = onlineNow;
  // **Write on screen** whose place's participants these are — otherwise one cannot tell a stale list from
  // those people actually being in that room (also the cause of this complaint).
  const whereLbl = RM ? '# ' + RM : T('No room (shared)');
  const pTtl = document.querySelector('.pside h2');   // ★static heading — repaint so it follows LANG
  // Panel header row — title left, place and shown count as meta on the right (.pwhere is hidden).
  setHtml(pTtl, esc(T('Participants')) + '<small>' + esc(whereLbl) + ' · ' + onlineNow.length + '</small>');
  setHtml(document.getElementById('people'),
      `<div class=pwhere>${esc(whereLbl)}</div>`
    + (hidden
      ? `<div class=hidnote>${esc(T('Shown'))} ${U(onlineNow.length,'#people')}${esc(T('(online · active in last 15 min)'))} · ${esc(T('hidden'))} ${U(hidden,'#people')}</div>` : '')
    + (peopleShown.length ? '' : '<div class=hidnote>'+esc(T('No one is online right now.'))+'</div>')
    + (peopleShown.length ? '<div class="nxr nxh"><i></i><span>' + esc(T('Participants')) + '</span><span class=nxm>' + esc(T('Messages'))
        + '</span><span class=nxm>' + esc(T('Last')) + '</span><span class=nxm>' + esc(T('Unread')) + '</span></div>' : '')
    + peopleShown.map(p => {
    // ★Connection state source of truth is presence (heartbeat) — without it, guess from activity time (title states it is a guess).
    const pr = PRES[p.id];
    const mins = (now - p.act) / 6e10;
    // ★state=unknown is **a peer with no watcher heartbeat** — writing only "active N min ago" reads as "not reading".
    // Do not state the unknown as known (measured: origin looked like that and was misread).
    const unk = pr && pr.state === 'unknown';
    // ★A running heartbeat means «watcher process is up», not «that id is working».
    // Measured 2026-09-23: heartbeat updating for 11d 22h · that id's real activity absent for 21h — still showed ●.
    // ⇒ Combine the server verdict (presence.active = MCP call within last hour) + send time this screen already knows.
    const nowS2 = Date.now()/1000;
    const actS = Math.max((pr && pr.act) || 0, p.sent ? Math.round(p.sent/1e9) : 0);
    const acting = !!(pr && pr.active) || (actS && nowS2 - actS < 3600);
    const beatOnly = !!(pr && pr.online && !acting);      // Heartbeat alone alive = not counted as ●
    const agoSpan = s => AGO(ago(Math.floor(s)));   // ago() floors like every other «N min ago»; not the global agoSec(ts)
    const cls = pr ? (pr.online ? (beatOnly ? 'idle' : 'on') : (unk ? 'unk' : (Date.now()/1000 - pr.at < 3600 ? 'idle' : '')))
                   : (!p.act ? '' : mins < 10 ? 'on' : mins < 60 ? 'idle' : '');
    const liveTxt = pr
      ? (pr.online ? (beatOnly ? T('Heartbeat only · active') + ' ' + (actS ? agoSpan(nowS2 - actS) : T('no record'))
                               // "Online" read as "posting"; it means a mailbox MCP call within the hour, so say that and when.
                               : (pr.source === 'watch' ? (actS ? T('Checked mailbox') + ' · ' + agoSpan(nowS2 - actS) : T('Online')) : T('Active just now')))
         : unk ? T('No watcher · last call') + ' ' + agoSpan(Math.max(0, Date.now()/1000 - pr.at))
               : TV({msg: 'active {t}', vars: {t: agoSpan(Math.max(0, Date.now()/1000 - pr.at))}}))
      : T('No presence record (inferred from activity time)');
    const liveTip = unk ? T('This peer has no heartbeat (watcher process), so presence is unknown — only the moment an MCP tool is called gets recorded. It does not mean they are offline.')
                  : beatOnly ? T('The watcher heartbeat is running, but this id has had no real activity (MCP calls or messages) for over an hour — it does not mean the session is alive.') : '';
    // Count of my messages this person has not read — shows where to nudge
    const owe = MSGS.filter(m => m.mine && m.audience.includes(p.id) && (CUR[p.id]||0) < m.t).length;
    // One list row (dot · name/state · metric columns); role, read time and rooms move to the tooltip.
    return '<div class=nxr title="' + esc([liveTip, p.role, p.read ? T('viewed') + ' ' + agoNs(p.read) : T('No read record'),
        p.rooms.length ? T('Rooms') + ' ' + p.rooms.join(', ') : T('No room')].filter(Boolean).join(' · ')) + '">'
      + '<i class="nxd ' + (cls === 'on' || cls === 'idle' ? cls : '') + '"></i>'
      // Logo only when a live session row owns this mbox (rcWho in 92-mainview-tabs.js); no guessing from the id.
      + '<span class=nxn><b' + nmSty(p.id) + '>' + rcWho(p.id) + '</b><small>' + esc(liveTxt) + '</small></span>'
      + '<span class=nxm>' + p.n + '</span><span class=nxm>' + (p.sent ? agoNs(p.sent) : '—') + '</span>'
      + '<span class="nxm' + (owe ? ' nxo' : '') + '">' + (owe || '—') + '</span></div>';
  }).join('') || '<div class=wt><span>' + esc(T('No participants')) + '</span></div>');
  const rl = Object.entries(ROOMS).map(([n, r]) =>   // room rows — name · owner · member count
    '<div class="nxr nxrm' + (place === 'room:' + n ? ' on' : '') + '"' + (r.topic ? ' title="' + esc(r.topic) + '"' : '') + '>'
    + '<span class=nxn><b>#' + esc(n) + '</b></span><span class=nxm>' + esc(T('owner')) + ' ' + esc(r.owner || '?') + '</span>'
    + '<span class=nxm>' + (r.members||[]).length + '</span></div>').join('');
  setHtml(document.getElementById('rinfo'), (rl || '<div>' + esc(T('No room')) + '</div>')
    // Legend uses the same dot elements as the rows, so its colors can never drift from them.
    + '<div class=nxlg>' + [['on', 'Online / active'], ['idle', 'Heartbeat only / within 1h'], ['', 'Other', 'rest']]
        .map(x => '<span><i class="nxd ' + x[0] + '"></i>' + esc(T(x[1], x[2])) + '</span>').join('') + '</div>');
}
// Narrow chat folds participants into their heading (45-saver-quota.css); the heading toggles .popen. Wide grids ignore it.
(function(){
  const h = document.querySelector('.pside h2');
  if(h) h.addEventListener('click', () => { h.setAttribute('aria-expanded', h.parentElement.classList.toggle('popen')); });
})();

