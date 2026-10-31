// ── Server self-status strip ─────────────────────────────────────────────────────
//   ★`/api/state.health` gives **absolute times** only — elapsed is computed here with `agoAt`.
//   ★Normally innerHTML is an empty string, so CSS `:empty` removes even the slot.
//   ⚠Stuck threads (dead) are **not user-dismissable** — they disappear only on server restart.
//     Neither has a click action (cursor:default); details live in the strip's title tooltip.
//   ★Warnings strip: one click = dismiss every current warning (the strip is an acknowledgement, not a detail view).
//     It used to expand a list; the list moved into the tooltip. The server drops each from `_warned`, so a recurrence shows again.
let HLTH = null;
function buildHealth(){
  const el = document.getElementById('hlb');
  if(!el) return;
  // Banner = actionable only: `stale` (a late collector recovers by itself) and `diag` are never drawn.
  const h = HLTH || {}, dead = h.dead || [], warns = h.warns || [];
  if(!dead.length && !warns.length){ if(el.className !== 'hlb') el.className = 'hlb'; el.title = ''; setHtml(el, ''); return; }
  let head, tip, cls;
  if(dead.length){
    // If there are stuck threads, say only that — warnings are usually a by-product of that incident
    const t = dead[0];
    cls = 'hlb';
    head = TV({msg: dead.length > 1 ? '<b>{n}</b> background threads stopped — ' : '<b>{n}</b> background thread stopped — ', vars: {n: dead.length}})
         + esc(t.thread || '?') + ' · ' + esc(t.exc || '') + ' · ' + esc(T('Restart Sidereus to recover'));
    tip = dead.map(d => (d.thread || '?') + ' · ' + (d.exc || '') + (d.where ? ' · ' + d.where : '') + ' · ' + agoAt(d.at));
  } else {
    cls = 'hlb hlwarn hlclk';
    // ★2026-09-28 the strip looked empty: the text was tooltip-only ⇒ the newest warning is written on the strip itself
    const w0 = warns[warns.length - 1];
    head = TV({msg: 'Warnings <b>{n}</b>', vars: {n: warns.length}}) + ' — <span class=hlmsg>' + esc(hlMsg(w0))
      + (warns.length > 1 ? TV({msg: ' +{n} more', vars: {n: (warns.length - 1)}}) : '') + '</span>';
    tip = [T('Click = dismiss all (shows again if it recurs)')]
      .concat(warns.slice().reverse().map(w => hlMsg(w) + ' · ' + agoAt(w.at)));
  }
  if(el.className !== cls) el.className = cls;
  el.title = tip.join('\n');   // DOM property, not markup — text only, no HTML path
  setHtml(el, head);
}
document.getElementById('hlb').onclick = (e) => {
  const warns = (HLTH && !(HLTH.dead || []).length && HLTH.warns) || [];
  if(!warns.length) return;         // dead strips have no click action
  e.stopPropagation();
  const ks = warns.map(w => w.key).filter(Boolean);
  HLTH.warns = []; buildHealth();
  Promise.all(ks.map(k => postJSON('/api/health/dismiss', {key:k})))
    .catch(() => note(T('Could not clear — check the server')));
};

let todoOpen = false;             // stale-thread list expanded
let todoAsk = false;              // inline confirm showing: true = «Clear all», a string = that one thread
// ★«Clear» posts a `[DONE]`-tag post to each thread (closing alone left stale threads with no way to clear them).
//   Optimistic: rows vanish now (THCLOSING); a failed POST restores them and says so via note().
async function thClose(ths){
  ths.forEach(th => { THCLOSING[th] = Date.now(); });
  buildTodo(); buildTabs();
  const bad = [];
  await Promise.all(ths.map(th => postJSON('/api/thread/close', {thread: th})
    .then(j => { if(!j || !j.ok) throw new Error((j && j.error) || '?'); })
    .catch(e => { delete THCLOSING[th]; bad.push(th + ': ' + e.message); })));
  if(bad.length) note(T('Could not clear') + ' — ' + bad.join(', '));
  try{ await poll(); }catch(e){ softErr('thClose poll', e); }
  buildTodo(); buildTabs();
}
function buildTodo(){
  const bar = document.getElementById('todo'), bar2 = document.getElementById('todo2');
  if(!bar) return;
  const unread = alarmBadgeN();   // same count as the bell badge (alert policy applied)
  const stale = staleThreads();
  const cells = [];
  // ★Blocked/ask/abort/85% cells merged into one attention count (2026-09-23) — same sessions as the #attn strip, same number as the tab [N].
  const attnN = attnBadgeN();
  if(attnN)        cells.push(['blk',   T('Attention'), attnN,     'attn', T('Attn')]);
  // Review queue (88c-review.js): sessions whose changes wait for a human look.
  const rvN = (typeof REVIEW !== 'undefined' && REVIEW && +REVIEW.n) || 0;
  if(rvN)          cells.push(['rv',    T('Awaiting review'), rvN,          'review', T('Review')]);
  // the top bar counts **excluding watchers** — watchers are always up, not 'something to act on'
  const nrun = SESS.reduce((a,x) => a + (x.sub||[]).length + (x.bgs||[]).length, 0);
  if(nrun)         cells.push(['run',   T('Background tasks'), nrun,          'run', T('Jobs')]);
  if(unread)       cells.push(['unread',T('Unread'), unread,       'bell', T('Unread', 'short')]);
  if(stale.length) cells.push(['stale', T('Stale threads'), stale.length, 'stale', T('Stale')]);
  // Detected CLIs without Sidereus hooks (90f); names are server data, so they fill a TV slot and are never passed through T().
  if(typeof hcTodo === 'function'){
    hcLoad(false);
    const hk = hcTodo();
    if(hk.length) cells.push(['hk', TV({msg: 'CLI hooks not connected: {names}', vars: {names: hk.map(x => x.name).join(' · ')}}), hk.length, 'hooks', T('Hooks')]);
  }
  // ★2026-09-27 QA 900px: full labels made row 1 ~75px too wide — ≤1000px shows the short label (.tds), full text in title.
  setHtml(bar, cells.map(c =>
    '<span class="td ' + c[0] + (stFil === c[3] || (c[3] === 'stale' && todoOpen) ? ' on' : '') + '" data-go="' + c[3] + '"'
    + ' title="' + esc(c[1] + ' ' + c[2]) + '" aria-label="' + esc(c[1] + ' ' + c[2]) + '">'
    + '<span class=tdl>' + esc(c[1]) + '</span><span class=tds>' + esc(c[4]) + '</span> <b>' + c[2] + '</b></span>').join(''));
  if(typeof todoAsk === 'string' && !stale.some(x => x.th === todoAsk)) todoAsk = false;   // asked thread already gone
  setHtml(bar2, (todoOpen && stale.length)
    ? stale.map(x => '<span class=tdth data-th="' + esc(x.th) + '" title="' + T('Last post: ') + esc(x.last) + '">' + esc(x.th)
        + ' <i>' + TV({msg: '{n} posts · quiet {t}', vars: {n: x.n, t: x.idleH >= 48 ? U(Math.round(x.idleH / 24), 'd') : U(Math.round(x.idleH), 'h')}}) + '</i>'
        + (x.turn.length ? '<u>→ ' + TV({msg: "{n}'s turn", vars: {n: esc(x.turn.join(', '))}}) + '</u>' : '')
        + '<button type=button class=tdcl data-cl="' + esc(x.th) + '" title="' + esc(T('Posts a {t} note that closes this thread').replace('{t}', '[마침]')) + '">'
        + esc(T('Clear', 'tidy')) + '</button></span>').join('')
      + (typeof todoAsk === 'string'
          ? '<span class=tdq><b>' + esc(todoAsk) + '</b>: ' + esc(T('Posts a {t} note that closes this thread').replace('{t}', '«[마침] 정리»'))
            + ' <button type=button data-q=ok>' + esc(T('Clear', 'tidy')) + '</button><button type=button data-q=no>' + esc(T('Cancel')) + '</button></span>'
        : todoAsk
          ? '<span class=tdq>' + esc(TV({msg: 'Close {n} threads with a {t} note?', vars: {n: stale.length, t: '[마침]'}}))
            + ' <button type=button data-q=ok>' + esc(T('Clear all')) + '</button><button type=button data-q=no>' + esc(T('Cancel')) + '</button></span>'
          : (stale.length > 1 ? '<button type=button class=tdall>' + esc(T('Clear all')) + ' ' + stale.length + '</button>' : ''))
      + (stale.dead ? '<span class=tdnote title="' + esc(TV({msg: 'Quiet for over {n} days counts as a finished discussion, not a stale one (just missing the {t} tag)', vars: {n: DEAD_D, t: '[마침]'}})) + '">'
          + TV({msg: '{n}d+ · {m} excluded', vars: {n: DEAD_D, m: stale.dead}}) + '</span>' : '')
    : '');
  bar.querySelectorAll('.td').forEach(el => el.onclick = () => {
    const go = el.dataset.go;
    if(go === 'bell') return openAlarm(true);
    if(go === 'attn'){ sesdrReveal(); const a = document.getElementById('attn'); if(a) a.scrollIntoView({behavior:'smooth', block:'nearest'}); return; }
    if(go === 'run'){ sesdrReveal(); document.querySelector('.lside').scrollIntoView({behavior:'smooth', block:'nearest'}); return; }
    if(go === 'stale'){ todoOpen = !todoOpen; return buildTodo(); }
    if(go === 'hooks'){ const h = hcTodo()[0]; if(h) hcAct('open', h.plat); return; }   // preview only; nothing is written before «Apply»
    if(go === 'review'){
      if(typeof brBoard === 'function') return brBoard(true);
      const r = rvRows()[0]; if(r) rvOpen(r.cwd, r.sid, el); return;
    }
    stFil = (stFil === go) ? '' : go;          // pressing the same cell again clears it
    saveFil(); buildSessions(); buildTodo();
    sesdrReveal(); document.querySelector('.lside').scrollIntoView({behavior:'smooth', block:'nearest'});
  });
  try{ sesdrBadge(); }catch(e){ softErr('sesdrBadge', e); }   // header «Sessions» badge rides every todo repaint (poll + attention redraws)
  try{ rvTick(); }catch(e){ softErr('rvTick', e); }   // open review drawer follows the same poll
  // Single «Clear» posts a Sidereus-composed note too, so it confirms like «Clear all» (todoAsk = thread name).
  const ask = (v) => { todoAsk = v; buildTodo(); const ok = bar2.querySelector('.tdq [data-q=ok]'); if(ok) ok.focus(); };
  bar2.querySelectorAll('.tdcl').forEach(b => b.onclick = e => { e.stopPropagation(); ask(b.dataset.cl); });
  const all = bar2.querySelector('.tdall');
  if(all) all.onclick = () => ask(true);
  bar2.querySelectorAll('.tdq button').forEach(b => b.onclick = () => {
    const was = todoAsk; todoAsk = false;
    if(b.dataset.q !== 'ok') return buildTodo();
    thClose(typeof was === 'string' ? [was] : stale.map(x => x.th));
  });
  bar2.querySelectorAll('.tdth').forEach(el => el.onclick = () => {
    // ★Threads live inside rooms — the place must move to that room for the thread to show in the filter row (otherwise an empty list)
    const th0 = el.dataset.th;
    const hit = MSGS.find(m => m.thread === th0);
    place = hit ? (hit.room ? 'room:' + hit.room : 'dm') : 'all';
    setFilter('thread:' + th0);
    buildRooms(); buildTabs(); full(); feed.scrollTop=0;
  });
}
function buildFilters(){
  const f = document.getElementById('sfil');
  if(!f) return;
  // The label names the current step (off included): a bare «Idle» read as a status, not a cycling filter.
  // en off-state names the filter: «Idle off» read as «idle sessions hidden», but on = show only the idle ones
  const il = idleMin || LANG !== 'en' ? T('Idle') + ' ' + (idleMin ? '≥' + U(idleMin, 'm') : T('off')) : 'Idle filter off';
  // Same pattern for git: the off label used to read «Unpushed», which looked like an active filter.
  const gl = gitFil==='push' ? T('Unpushed')+' ↑' : gitFil==='dirty' ? T('Unpushed or dirty')+' ↑~' : (LANG !== 'en' ? 'git ' + T('off') : 'Git filter off');
  const stLbl = {ask:T('Awaiting answer only'), abort:T('Aborted only'), hot:T('Context 85%+'), blocked:T('Blocked only')};
  const fo = acctPickFocusId();
  setHtml(f, (stFil ? '<span id=fst class="on" title="'+esc(T('Filter set from the top bar — click to clear'))+'">'+stLbl[stFil]+' ✕</span>' : '')
    + '<span id=fidle class="'+(idleMin?'on':'')+'" title="'+esc(T('Idle filter — when on, shows only sessions stopped longer than that in awaiting input, awaiting answer or aborted (running a tool or thinking is never idle). Each click: off→10→30→60 min.'))+'">'+il+'</span>'
    + '<span id=fgit class="g '+(gitFil?'on':'')+'" title="'+esc(T('How far the work got — click to cycle off→unpushed (↑)→unpushed or dirty (↑~)'))+'">'+gl+'</span>' + acctPickHtml('sess'));
  // Sessions pick also drives Attention, Recent and the drawer counts (90b mpMainAcctRedraw repaints them all).
  acctPickWire('sess', () => mpMainAcctRedraw(), fo);
  document.getElementById('fidle').onclick = () => {
    idleMin = IDLE_STEPS[(IDLE_STEPS.indexOf(idleMin)+1) % IDLE_STEPS.length]; saveFil(); buildSessions(); };
  document.getElementById('fgit').onclick = () => {
    gitFil = GIT_STEPS[(GIT_STEPS.indexOf(gitFil)+1) % GIT_STEPS.length]; saveFil(); buildSessions(); };
  const fst = document.getElementById('fst');
  if(fst) fst.onclick = () => { stFil = ''; saveFil(); buildSessions(); buildTodo(); };
}
