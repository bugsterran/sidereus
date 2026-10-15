// ★«Waiting on you» alert — OS notification when a session newly needs the user.
// ⚠Default off (quiet defaults). Metadata only: project · branch · state label · sid8 — never message bodies, tool inputs or relay text.
// Kinds = "the session stopped and waits for me": permission (blocked) · question (ask) · interrupt (abort) · failure stop (fail, merged
//   limit/wreck/check/cut cards) + 'rv' = a finished session with unreviewed edits (state().review row not done). conflict/loop/stall/ctx stay in the strip.
const NTF_KINDS = new Set(['blocked', 'ask', 'abort', 'fail']);
const NTF_SID_MS = 120000, NTF_WIN_MS = 60000, NTF_MAX = 4, NTF_RVMARK = '*|rv';
let NTF_SEEN = null, NTF_ERR = '', NTF_HIST = { sid: {}, all: [] };
// Stored as sidereus.notify {on, visible}; the pre-09-27 key sidereus.osntf='1' still reads as on.
function ntfPref(){
  try{
    const v = JSON.parse(localStorage.getItem('sidereus.notify') || 'null');
    if(v && typeof v === 'object') return { on: !!v.on, visible: !!v.visible };
    return { on: localStorage.getItem('sidereus.osntf') === '1', visible: false };
  }catch(e){ return { on: false, visible: false }; }
}
function ntfSave(p){ lsSetJson('sidereus.notify', { on: !!p.on, visible: !!p.visible }); }
function ntfOn(){ return ntfPref().on && typeof Notification !== 'undefined' && Notification.permission === 'granted'; }
// Pure step: -> {seen, fire:[{r, k, since}]}. First call (seen null) only seeds; a cleared sid|k drops out of seen so it can fire again.
// ⚠Review rows are primed on their own (NTF_RVMARK): state().review can arrive after attention, and a missing review keeps its keys.
function ntfStep(seen, rows, rv){
  const cur = new Set(), fire = [];
  const add = (r, k, since, prime, ep) => {
    const key = r.sid + '|' + k + (ep ? '|' + ep : '');   // ep = prompt time: a new permission prompt fires again while still blocked
    if(!r.sid || cur.has(key)) return;
    cur.add(key);
    if(seen && !prime && !seen.has(key)) fire.push({ r, k, since: since || r.since || 0 });
  };
  for(const r of rows || []) for(const g of r.sigs || []) if(NTF_KINDS.has(g.k)) add(r, g.k, g.since, false, g.ep);
  if(Array.isArray(rv)){
    const prime = !(seen && seen.has(NTF_RVMARK));
    cur.add(NTF_RVMARK);
    for(const r of rv) if(r && !r.done) add(r, 'rv', r.since, prime);
  } else if(seen){
    for(const key of seen) if(key.endsWith('|rv')) cur.add(key);
  }
  return { seen: cur, fire };
}
// Pure rate limit: -> {send:[{sid, r, ks, since}], more, hist}. Signals of one session merge into one notification;
// at most one per session per 2 min (a later one inside the window is dropped — the strip still shows it) and 4 per minute overall (rest -> more).
function ntfGate(hist, fire, now){
  const h = { sid: {}, all: ((hist && hist.all) || []).filter(t => now - t < NTF_WIN_MS) };
  for(const s in (hist && hist.sid) || {}) if(now - hist.sid[s] < NTF_SID_MS) h.sid[s] = hist.sid[s];
  const by = new Map();
  for(const x of fire || []){
    const e = by.get(x.r.sid);
    if(e){ if(!e.ks.includes(x.k)) e.ks.push(x.k); } else by.set(x.r.sid, { sid: x.r.sid, r: x.r, ks: [x.k], since: x.since });
  }
  const send = []; let more = 0;
  for(const e of by.values()){
    if(h.sid[e.sid] !== undefined) continue;
    if(h.all.length >= NTF_MAX){ more++; continue; }
    h.sid[e.sid] = now; h.all.push(now); send.push(e);
  }
  return { send, more, hist: h };
}
function ntfText(e, at){
  const r = e.r, now = at || Date.now() / 1000;
  const min = Math.max(0, Math.round((now - (e.since || now)) / 60));
  const name = attnName(r, attnSess(r));   // ★2026-09-27: board-card (worktree) name, same as the attention row
  return { title: PAGE_NAME + ' — ' + name + (r.branch ? ' · ' + r.branch : ''),
           // fail: the shared «Failures» entry is a plural heading in English; one session's state reads «Failed».
           body: e.ks.map(k => k === 'fail' ? T('Failed', 'short') : (k === 'rv' ? T('Awaiting review') : attnLbl(k))).join(' · ') + ' · ' + U(min, 'm') + ' · ' + String(e.sid).slice(0, 8),
           tag: 'sidereus|' + e.sid };   // tag per session: the OS replaces instead of stacking
}
// Click on a blocked/ask notification raises that session's terminal tab when it can; else focuses Sidereus and opens the session
//   (review drawer for a review-only item).
function ntfClick(e){
  const js = e.ks.some(k => ALARM_TERM_KINDS.has(k)) ? termJumpSid(e.sid) : '';
  if(js) return termGo(js);
  try{ window.focus(); }catch(err){}
  try{
    if(e.ks.length === 1 && e.ks[0] === 'rv' && typeof rvOpen === 'function') rvOpen(e.r.cwd, e.sid);
    else cpGo(attnSess(e.r) || { sid: e.sid, cwd: e.r.cwd });
  }catch(err){ softErr('ntfClick', err); }
}
// Called once per poll with state().attention and state().review.rows; seen is always tracked so enabling later never replays old signals.
function ntfTick(a, rv){
  if(!a) return 0;
  const st = ntfStep(NTF_SEEN, a.rows, rv);
  NTF_SEEN = st.seen;
  if(!st.fire.length || !ntfOn()) return 0;
  if(!ntfPref().visible && !document.hidden) return 0;   // consumed: no late fire when the tab hides
  const g = ntfGate(NTF_HIST, st.fire, Date.now());
  NTF_HIST = g.hist;
  const pop = (t, fn) => { try{ const n = new Notification(t.title, { body: t.body, tag: t.tag });
    n.onclick = () => { if(fn) fn(); try{ n.close(); }catch(err){} }; }catch(err){ softErr('ntfPop', err); } };
  for(const e of g.send) pop(ntfText(e, a.at), () => ntfClick(e));
  if(g.more) pop({ title: PAGE_NAME, body: T('{n} more sessions are waiting').replace('{n}', g.more), tag: 'sidereus|more' },
                 () => { try{ window.focus(); }catch(err){} });
  return g.send.length;
}
// Settings toggle: turning on asks for permission; a refusal keeps it off with a short note. `done` repaints the modal.
function ntfSet(on, done){
  const save = v => ntfSave({ on: v, visible: ntfPref().visible });
  if(!on){ save(false); NTF_ERR = ''; return done && done(); }
  if(typeof Notification === 'undefined'){ save(false); NTF_ERR = T('This browser does not support OS notifications.'); return done && done(); }
  const fin = p => { const ok = p === 'granted'; save(ok);
    // 'default' = the prompt was dismissed without a choice: asking again works, unlike 'denied'.
    NTF_ERR = ok ? '' : p === 'default'
      ? T('No notification permission was chosen, so it stays off. Turn it on again to be asked again.')
      : T('Notification permission was denied, so it stays off. Allow it in the browser site settings.');
    if(!ok) try{ note(NTF_ERR); }catch(e){}
    if(done) done(); };
  if(Notification.permission === 'granted' || Notification.permission === 'denied') return fin(Notification.permission);
  try{ Promise.resolve(Notification.requestPermission()).then(fin, () => fin('denied')); }catch(e){ fin('denied'); }
}
function ntfVisSet(v){ ntfSave({ on: ntfPref().on, visible: !!v }); }
// Settings description: last error, else a blocked-permission hint, else what it does.
function ntfHint(){
  if(NTF_ERR) return NTF_ERR;
  if(typeof Notification !== 'undefined' && Notification.permission === 'denied')
    return T('The browser blocks notifications — allow them for this site in the system or browser settings.');
  return T('Shows an OS notification when a session stops on a permission prompt, a question, an interrupt or a failure, or finishes with edits to review. At most once per session every 2 min and 4 per minute overall.');
}
