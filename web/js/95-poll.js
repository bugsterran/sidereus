// ★**Overlapping** polls consume the same response twice (2026-09-02: mailbox messages appeared twice):
// it is `setInterval(poll, 2500)` but `since` advances **after** the await. When a response takes over 2.5s
// the next tick requests again with **the same since**, both responses carry the same posts, and they enter `MSGS` twice.
// Measured: bus.jsonl 832 items, 0 duplicate ids · 0 identical t · 0 identical (sender, body) —
// **the store is clean.** The duplicates were a screen-side problem.
// And responses over 2.5s really happen (1GB transcript parse · `ps` timeout warnings in the log).
let pollBusy = false;
const POLL_TIMEOUT_MS = 15000, POLL_COLD_MS = 75000;   // a timeout counts as «Disconnected» (pollDown)
var CFG = null;   // last state().cfg (dmMax for the relay comment cap in 88c)
var ACCTS = [];   // state accts [{label, primary}], only with >=2 Claude accounts (40b acctCls)
const MSEEN = new Set();          // Ids of posts already received — never counted twice whichever path they came in by
async function poll(first){
  if(pollBusy && !first) return;  // Previous request not finished — skip this tick
  // Backing off while down (connBackoffMs, 60-statusbar.js): a skipped tick only refreshes the «as of N s ago» age.
  if(!first && connWait(CONN, Date.now())){ try{ buildSbar(); }catch(e){ softErr('pollWaitSbar', e); } return; }
  pollBusy = true;
  const t0 = Date.now();   // backoff counts from request start, not from when the failure came back
  try{
    // ★While «Full history» is on, polling must also fetch 300 — otherwise the next poll (2.5s) overwrote with the default 50
    // and the list soon collapsed again (measured 2026-08-26: clicking reverted to 50).
    let s;
    // A network failure (TypeError) is «Disconnected»; a reply that is non-2xx or not JSON is «Bad response».
    // Warm state answers from a snapshot in <1s; the first load or one after an outage may wait for a cold build (STATE_COLD_S 60s).
    const stTo = (!STATE_IN || CONN.fails) ? POLL_COLD_MS : POLL_TIMEOUT_MS;
    try{ s = await getJSON('/api/state?since='+since+(alarmAll?'&cards=300':''), {timeout: stTo}); }
    catch(e){ pollDown(!!e.status || e instanceof SyntaxError, t0); return; }
    const wasDown = CONN.fails > 0;
    connMark(CONN, true, false, Date.now());
    document.documentElement.classList.remove('agstale');
    document.getElementById('dot').classList.remove('off');
    if(wasDown) loadWku(true);     // token figures were held from before the outage — refresh them now, not 30s later
    if(s.cfg&&Array.isArray(s.cfg.stripPrefixes)) STRIP_PREFIXES=s.cfg.stripPrefixes;
    if(s.cfg) CFG = s.cfg;
    if(s.cfg) termCfg(s.cfg.termApp);   // «Terminal link» setting (88d-term.js)
    CUR=s.cursors; ROOMS=s.rooms; PROF=s.profiles; MINE=s.mine; PRES=s.presence||{}; ACK=s.acks||{}; ACKSINCE=s.acksSince||0; SESS=s.sessions||[]; ACCTS=s.accts||[];
    ARCHRUN = s.archRun || {}; SECRUN = s.secRun || {}; SIDEREUS_DIR = s.codeDir || '';   // arch-map runs in progress per project (84j archRunOf, 48h)
    PLREQ = s.plReq || {};   // who received each arch-map request and its run state (84l2)
    PROJ_GONE = new Set(s.projGone || []);   // session folders deleted from disk — project chips skip them (80, 48)
    if(typeof roomTagsSet === 'function') roomTagsSet(s.roomTags);   // chat room card tags (92); missing key = {}
    if(typeof roomAdminSet === 'function') roomAdminSet(s.roomAdmin);   // hidden / pending rooms (92c); missing key = {}
    // First state: the branch view painted "loading" while SESS was empty — pick its repo now.
    // ⚠A remembered brRepo skips loadBr, but the repo chips were painted before state arrived — repaint them.
    if(!STATE_IN){ STATE_IN = true; try{ tourMaybe(s.codeDir); }catch(e){ softErr('tourMaybe', e); }   // first-visit tour (98b)
      if(mainView === 'br') try{ if(!brRepo) loadBr(false); else paintBr(); }catch(e){ softErr('pollBr', e); } }
    if(mainView === 'struct' && !ISPOP && !ISWP) try{ if(strSessKey() !== strSessSig){ paintStruct(); if(strMode === 'size' || !strOn.length) loadStruct(false); } else strBrSync(); }catch(e){ softErr('pollStruct', e); }
    FEATS = s.features || {};       // feature-off tabs hide on the buildMv below (92-mainview-tabs.js TAB_FEAT)
    if(!ISPOP && !ISWP) try{ plPoll(); }catch(e){ softErr('pollPipe', e); }   // «Pipelines» live lighting (48b-pipeline-run.js)
    if(s.build && MY_BUILD && s.build!==MY_BUILD) document.getElementById('stale').classList.add('on');
    // ⚠Keep in-flight read keys — a poll snapshotted before the POST landed would flip them back to unread.
    CARDS=s.cards||[]; CREAD=s.cardsRead||''; CRIDS=new Set((s.cardsReadIds||[]).concat([...CRPEND]));
    ATTN = s.attention || null;     // drawn by the buildAlarm wrapper (17-attention.js)
    REVIEW = s.review || null; try{ brBoardTick(); }catch(e){ softErr('brBoardTick', e); }   // review queue (88c) + branch-tab board (88b)
    try{ ntfTick(ATTN, REVIEW && REVIEW.rows); }catch(e){ softErr('ntfTick', e); }   // optional OS notification on new attention / review items (43-notify.js)
    EXTU = s.extUsage || {};        // Tokens tab «By platform» block
    if(seenToast===null){ seenToast=new Set(CARDS.map(ckey)); }   // First poll = seeding (no toasts)
    else { for(const c of CARDS.slice().reverse()){ const k=ckey(c);
             if(!seenToast.has(k)){ seenToast.add(k); if(isNew(c) && apolOf(c.kind) === 'badge') toast(c); } } }   // quiet kinds: no toast
    buildAlarm();
    USG = s.usage || null;
    buildQuota(s.usage, s.quota);
    buildCredit(s.quota);
    // ★Burndown **piggybacks here** — no new timer (throttled to 30s inside).
    // `buildBurn()` re-measures remaining time against the current clock, so redrawing every poll is fine.
    // ⚠Refresh `SV` **before** `buildBurn`/`buildSaver` — both read the same snapshot.
    SV = saverViewFor(s);
    burnTick(); buildBurn();
    buildSaver(s.saver);
    QWHO = s.quotaWho || null;      // read by buildSbar -> buildQwho (quota modal)
    buildSbar(s.saver);             // status bar — same poll, same inputs
    svSwSync(s.saverSwitch, s.saver);   // a CLI `/saver` change reaches the open modal within the 5s TTL
    HLTH = s.health || null; buildHealth();   // If the server failed silently, a strip is attached to the header
    const got=s.messages.map(decorate);
    // ★Advance `since` over **everything received** (advancing by the value after dedup would, on an all-duplicate response,
    // leave the cursor still and refetch the same posts forever).
    if(got.length) since=Math.max(since, ...got.map(m=>+m.t||0));
    const fresh=got.filter(m => {
      const k = m.id || ((m.t||'')+'|'+(m.from||''));
      if(MSEEN.has(k)) return false;
      MSEEN.add(k); return true;
    });
    if(fresh.length){ MSGS=MSGS.concat(fresh); MSGS.forEach(decorate); }
    // ★In work-history mode **skip** chat rendering — otherwise polling overwrites the console
    loadTl();
    try{ tlgTick(); }catch(e){ softErr('tlgTick', e); }   // Timeline «Changes» chip (77-timeline-git.js) — throttled inside, Timeline tab visible only
    // ★Drawing chat into #feed happens **only in chat mode**. Before, mode was not checked, so while viewing timeline/work history
    // a new post made `append` attach chat there (2026-09-01: chat messages flashed briefly
    // below the timeline). The next re-render erased it, so it looked like a 'flicker'.
    buildRooms(); buildTabs(); buildMv();
    if(wkOn && wtShown().length){
      // Update only tab status dots — the body is redrawn only when refreshAgent sees a change (scroll preserved)
      const st0 = document.querySelector('#wkmb .wtb');
      if(st0){ const tmp = document.createElement('div'); tmp.innerHTML = wtStrip();
               const neu = tmp.firstElementChild;
               if(neu && neu.innerHTML !== st0.innerHTML){ st0.innerHTML = neu.innerHTML;
                 wtBind(wkBox()); } }
      // refresh empty-pane pickers in place (the onclick delegate on .wpkw survives innerHTML swaps)
      document.querySelectorAll('#wkmb .wpkw[data-wpe]').forEach(el => {
        setHtml(el, wtPickHtml()); });
      wkSumSet((wtKeyOf(wtFocus) && wtData[wtKeyOf(wtFocus)]) || agentData);   // keep "time ago" fresh
      try{ wkcPaint(); }catch(e){ softErr('wkcPaint', e); }   // compose box: recipient watch state + sent status / replies
    }
    // ★Baseline — set once on the first poll (so old posts do not appear as 'new'), and advanced continuously while viewing chat.
    if(first || mainView === 'chat') chatMark();
    if(mainView !== 'chat') { /* console/timeline is using #feed — leave it alone */ }
    else if(first){ full(); toBottom(false); }
    else if(fresh.length){ append(fresh); }
    refreshReceipts(); buildPeople(); buildSessions(); buildTodo();   // Read state, participants, sessions and top bar in the same poll
    try { brWtTick(s.wtOrder); } catch(e){ softErr('brWtTick', e); }
    loadWku();                       // Weekly tokens — has its own 5-min interval, so not called every poll
    if(agentTid) refreshAgent();      // The open agent modal on the same cycle too (see comment below)
    // ★The timeline bottom drawer must also stay live — it is opened to watch running agents.
    // Lowered to 5s (the poll is 2.5s but there is no reason to fetch that often).
    // ★Only the timeline's **state markers** update in place every poll (2.5s) (2026-09-03: timeline did not
    // show tool execution and was out of sync).
    // Bars rightly stay on the loadTl cycle (default 30s) — their meaning changes only per minute.
    // But **state changes per second.** The session card redraws every 2.5s while the timeline
    // waited 30s, so the same session showed different states on two screens (up to 30s apart).
    // ⇒ Swap only the marker nodes here. No redraw cost and the scroll does not jump.
    if(mainView === 'time') try{ tlSyncState(); }catch(e){ softErr('tlSyncState', e); }
    if(mainView === 'time' && tlSel){
      try{ tlFit(); }catch(e){ softErr('tlFit', e); }      // Whatever drifts, the next poll corrects it on its own
      if(Date.now() - tlSelAt > 5000){ tlSelAt = Date.now(); tlFetch(tlSel.cwd, tlSel.tid); }
    }
    // ★When split, update **the other pane** too — otherwise only one side is live and
    // the "side by side" purpose is only half achieved (2026-09-02).
    if(wkOn && wtSplit){
      const fk = wtKeyOf(wtFocus);
      wtShown().filter(k => k !== fk).forEach(k => wtFetch(wtabs.find(t => t.key === k)));
    }
  }catch(e){ pollDown(true, t0); }      // the reply arrived but could not be applied
  finally{ pollBusy = false; }
}
// Saver verdict of the «Main account»: primary (no main) -> s.saverView; other -> s.saverViews[label].
// ⚠Never fall back to the primary's view for a non-primary main — null hides the chip.
function saverViewFor(s){ const m = mainAcct(); return m ? ((s.saverViews || {})[m] || null) : (s.saverView || null); }
// Mark the screen as stale (html.agstale dims held numbers) and schedule the next try with backoff.
function pollDown(bad, t0){
  connMark(CONN, false, bad, t0 || Date.now());
  document.documentElement.classList.add('agstale');
  document.getElementById('dot').classList.add('off');
  try{ buildSbar(); }catch(e2){}
}
document.getElementById('sreload').onclick=()=>location.reload();
document.getElementById('bell').onclick=(e)=>{ e.stopPropagation(); openAlarm(); };
document.getElementById('aclose').onclick=()=>openAlarm(false);
document.getElementById('aread').onclick=async()=>{
  // Clear only the badge — cards remain as history (empty object = mark all).
  // Apply the server's watermark now — `poll()` returns at once while a poll is in flight, so the badge waited a tick.
  try{ const j = await postJSON('/api/cards/read', {}); if(j && j.at){ CREAD = j.at; buildAlarm(); } }
  catch(e){ note(T('Could not mark as read — check the server')); }
  await poll();
};
document.getElementById('aunread').onclick=()=>{
  unreadOnly=!unreadOnly;
  lsSet('mbUnreadOnly', unreadOnly?'1':'0');
  buildAlarm();
};
// ★Click one card → only that card is read. The list redraws every poll, so **delegate to the list container**.
// Fix the screen first without awaiting the response (waiting for the 2.5s poll looks like "not clicked") — server update follows.
// Mark one card read. **The list and toast use the same path** — if they diverge, only one gets fixed and they silently drift
// (a bug already happened this way in this file: cache path vs parse path).
// Bulk (group / «Read») sends one POST {keys} — one server lock + one write instead of one per key.
const CRPEND = new Set();
async function markCardsRead(ks){
  ks = [...new Set((ks || []).filter(k => k && !CRIDS.has(k)))];
  if(!ks.length) return;
  ks.forEach(k => { CRIDS.add(k); CRPEND.add(k); }); buildAlarm();   // Do not await the response (waiting for the 2.5s poll looks like "not clicked")
  try{ await postJSON('/api/cards/read', {keys:ks}); }
  catch(err){ ks.forEach(k => CRIDS.delete(k)); buildAlarm(); note(T('Could not mark as read — check the server')); }
  finally{ ks.forEach(k => CRPEND.delete(k)); }
}
document.getElementById('alist').onclick=async(e)=>{
  // Group expand toggle: only opens/closes the member lines — not a read.
  const gx = e.target.closest && e.target.closest('[data-gx]');
  if(gx){ e.stopPropagation(); const k = gx.getAttribute('data-gx'); GRP_OPEN.has(k) ? GRP_OPEN.delete(k) : GRP_OPEN.add(k); buildAlarm(); return; }
  // Failure-alert action button: run it only — acting no longer marks read (§7-5, 2026-09-23).
  const fb = e.target.closest && e.target.closest('[data-fa]');
  if(fb){ e.stopPropagation(); faAct(fb); return; }
  // Explicit «Read» button on a failure card: mark that card (or its whole group) read.
  const fr = e.target.closest && e.target.closest('[data-fread]');
  if(fr){
    e.stopPropagation();
    const fc = fr.closest('.card[data-gi]'), fg = fc ? AGROUPS[+fc.getAttribute('data-gi')] : null;
    markCardsRead(fg ? fg.items.filter(isNew).map(ckey) : [fr.getAttribute('data-fk')]);
    return;
  }
  const el = e.target.closest && e.target.closest('.card.new[data-ck]');
  if(!el) return;
  if(el.querySelector('.cfa')){ e.stopPropagation(); return; }   // failure card body: no implicit read
  // ★Stop bubbling — without it **the window closed on every click** (2026-08-19).
  // The "close on outside click" handler below runs on window, and meanwhile `buildAlarm()` redraws the list
  // so **the clicked card leaves the DOM.** Then `#alarm.contains(removed element)` is false and it is mistaken for an outside click.
  e.stopPropagation();
  const g = el.hasAttribute('data-gi') ? AGROUPS[+el.getAttribute('data-gi')] : null;
  markCardsRead(g ? g.items.filter(isNew).map(ckey) : [el.getAttribute('data-ck')]);   // a grouped entry marks every member read
};
document.getElementById('aall').onclick=async()=>{
  alarmAll = true;                       // Lift the 50-item cap only while this button is pressed
  // ★Fetch cards only (2026-09-22) — before, `/api/state?since=0&cards=300` pulled everything.
  // Measured: full 3,186,536B vs cards only 65,702B (at 300 cards · 48x).
  try{ const s2=await getJSON('/api/cards?n=300'); CARDS=s2.cards||CARDS; buildAlarm(); }
  catch(e){ note(T('Could not fetch — check the server')); }
};
addEventListener('click',(e)=>{ const a=document.getElementById('alarm');
  if(!alarmOpen) return;
  // ★An element already removed from the DOM is **not 'outside'** (it was removed by a redraw) — do not close the window on it.
  // The stopPropagation in (1) blocks it, but block here too so the same trap is not hit elsewhere.
  if(!document.contains(e.target)) return;
  if(Date.now() - alarmPtrEnd < 400) return;   // the click that ends a pointer drag begun inside the panel
  if(!a.contains(e.target)) openAlarm(false); });
document.getElementById('q').oninput=e=>{ q=e.target.value.trim().toLowerCase(); shownN=10; buildRooms(); full(); vwSaveVis(); };
