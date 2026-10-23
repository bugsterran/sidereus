// ★Room row — drawn **from the server's `ROOMS`**. Before, room names were pulled from `MSGS`, so newly created or
// invited **empty rooms never showed** (measured 2026-08-26: ROOMS had one room-A, but the tab existed only because
// it had posts). A place exists with or without posts — do not say something that exists does not.
// ★Stacked as **tabs** like an IDE (2026-08-27: clicking should just open a tab, IDE-style).
// Before, every live session was laid out as a chip — just a list, not one I chose.
// Now only clicked items become tabs, closed with ✕. Each tab keeps its own **scroll position and fetched values**,
// so switching is free (before, it jumped to the bottom on every switch).
let wtabs = [];          // [{key, cwd, tid, label, kind}]
// ★N-pane split (2026-09-23, generalized from the 2-pane wtActive/wtActive2 split of 2026-09-02).
// wtPanes[i] = tab key shown in pane i+1 ('' = empty); length = the layout's pane count. Single = [key].
// Clicking a tab puts it in the focused pane — same rule as an IDE, nothing new to learn.
const WT_LAYOUTS = {
  '1':  {n:1, c:1, r:1, lb:'Single',    tip:'One pane'},
  'h2': {n:2, c:2, r:1, lb:'2 across',  tip:'Two panes side by side'},
  'v2': {n:2, c:1, r:2, lb:'2 stacked', tip:'Two panes stacked'},
  'c3': {n:3, c:3, r:1, lb:'3 columns', tip:'Three panes side by side'},
  'g4': {n:4, c:2, r:2, lb:'2×2',       tip:'Four panes (2×2)'},
};
// ⚠Migration: old mbWtSplit=1 (+ mbWtDir) maps to h2/v2 so a user who had split keeps seeing it.
let wtLayout = (() => { try {
  const v = UIS.mbWtLayout;
  if(WT_LAYOUTS[v]) return v;
  return UIS.mbWtSplit === '1' ? (UIS.mbWtDir === 'v' ? 'v2' : 'h2') : '1';
} catch(e){ return '1'; } })();
function wtLay(){ return WT_LAYOUTS[wtLayout] || WT_LAYOUTS['1']; }
let wtSplit = wtLay().n > 1;     // derived: kept in sync by wtSetLayout (many callers only need "multi or not")
let wtPanes = new Array(wtLay().n).fill('');
// Track sizes (fr) per layout: {h2:{c:[a,b],r:[1]}, ...}. Old 2-pane mbWtRatio seeds h2/v2.
let wtFr = (() => { try { const o = JSON.parse(UIS.mbWtFr || '{}'); return (o && typeof o === 'object') ? o : {}; }
                    catch(e){ return {}; } })();
function wtTracks(){
  const L = wtLay(), s = wtFr[wtLayout] || {};
  const ok = (a, n) => Array.isArray(a) && a.length === n && a.every(x => isFinite(x) && x > 0);
  let c = ok(s.c, L.c) ? s.c.slice() : new Array(L.c).fill(1);
  let r = ok(s.r, L.r) ? s.r.slice() : new Array(L.r).fill(1);
  if(!s.c && !s.r){
    const v = parseFloat(lsGet('mbWtRatio', ''));
    if(isFinite(v) && v > .15 && v < .85){ if(wtLayout === 'h2') c = [v, 1 - v]; if(wtLayout === 'v2') r = [v, 1 - v]; }
  }
  return {c, r};
}
let wtDragging = false;   // Dragging the divider — **do not redraw** meanwhile
// ★dataTransfer **cannot be read** in dragover (the browser blocks it). So what is being dragged
// is remembered at dragstart — needed to split the drop indicator into tab (blue) and pane (green).
let wtDragWhat = '';
function wtDragKind(){ return wtDragWhat; }
let wtFocus = 1;          // 1-based index into wtPanes
function wtShown(){ return wtPanes.filter(Boolean); }
// ★In single mode it is **always pane 1**. Before, `p===2` returned the right pane, so
// if focus had been left on pane 2 from split mode, the single view broke entirely
// (measured 2026-09-02: leaving to another tab and returning stuck on loading).
// `wtFetch` fills agentData only when `wtKeyOf(wtFocus) === t.key`; that mismatched,
// agentData stayed null, and the single render drew it as «Loading…» forever.
function wtKeyOf(p){ return wtPanes[(wtSplit ? Math.min(Math.max(p|0, 1), wtPanes.length) : 1) - 1] || ''; }
function wtPaneName(p){ return TV({msg: 'Pane {n}', vars: {n: p}}); }
// Changing the focused pane makes **that pane's tab the current target** (polling, expansion, scroll all follow it)
function wtSetFocus(p){
  if(wtSplit && !(p >= 1 && p <= wtPanes.length)) return;
  wtFocus = wtSplit ? p : 1;
  const k = wtKeyOf(wtFocus);
  const t = wtabs.find(x => x.key === k);
  if(t){ agentCwd = t.cwd; agentTid = t.tid; agentData = wtData[k] || null; }
}
// Swap two panes wholesale — focus follows the focused tab so **you keep seeing what you were seeing**
function wtSwapPanes(a, b){
  const n = wtPanes.length;
  if(!wtSplit) return;
  a = a || wtFocus; b = b || (a % n) + 1;
  if(a === b || a < 1 || b < 1 || a > n || b > n) return;
  const x = wtPanes[a-1]; wtPanes[a-1] = wtPanes[b-1]; wtPanes[b-1] = x;
  if(wtFocus === a) wtFocus = b; else if(wtFocus === b) wtFocus = a;
  wtSetFocus(wtFocus);
  buildMv(); workPaint();
}
// Switch layout: growing fills new panes with tabs not yet shown (an empty pane does not tell you what to do);
// shrinking keeps the focused tab visible by moving it into the last surviving pane.
function wtSetLayout(id){
  if(!WT_LAYOUTS[id]) return;
  const fk = wtKeyOf(wtFocus);
  wtLayout = id;
  lsSet('mbWtLayout', id);
  const n = wtLay().n;
  let ps = wtPanes.slice();
  if(ps.length > n){
    if(wtFocus > n && fk){ ps[n-1] = fk; wtFocus = n; }
    ps = ps.slice(0, n);
  }
  while(ps.length < n) ps.push('');
  for(let i = 0; i < n; i++){
    if(ps[i]) continue;
    const nx = wtabs.find(t => !ps.includes(t.key));
    ps[i] = nx ? nx.key : '';
  }
  wtPanes = ps;
  wtSplit = n > 1;
  wtFocus = wtSplit ? Math.min(Math.max(wtFocus, 1), n) : 1;
  wtPanes.forEach(k => { if(k && !wtData[k]) wtFetch(wtabs.find(t => t.key === k)); });
  wtSetFocus(wtFocus);
  buildMv(); workPaint();
}
const wtData = {};       // key → last fetched work history
const wtScroll = {};     // key → scroll position
function wtKey(cwd, tid){ return (tid||'') + '@' + (cwd||''); }
// Called by the main window (35c wkHostOf): `let wtabs` is not a window property, a function is.
function wkHasTab(cwd, tid){ return wtabs.some(t => t.key === wtKey(cwd, tid)); }
// Tab row at the top of the work-history view — only opened items stack up
// ★Tabs show **whether still running or finished** (2026-09-01). The verdict uses the **same values** as the session card
// (SESS sub/state) — the two views must not disagree.
// Agent: is that tid in the live sub list. Session: is state tool/think (waiting for input is not 'working').
function wtLive(t){
  const S = SESS || [];
  if(String(t.tid).indexOf('ext:') === 0){
    const sid = String(t.tid).slice(String(t.tid).indexOf('|') + 1), r = S.find(x => x.sid === sid);
    return r ? ['tool','think'].includes(r.state) : (S.length ? false : null);
  }
  if(String(t.tid).indexOf('sess:') === 0){
    // ★A tid with a trailing sid is an **old session** — borrowing the state of the session now running in that cwd
    // shows a finished session as 'working' (2026-09-09).
    if(tidSid(t.tid)) return false;
    const r = tlLiveOf(t.cwd);                // Claude row only — `sess:` tabs are Claude; a Gemini row can share the cwd
    if(!r) return null;                      // Not in the list — unknown (do not conclude it finished)
    return ['tool','think'].includes(r.state);
  }
  // ⚠A tab id may carry a trailing `/<sid>` part (empty for agents opened from the timeline) — compare the head only.
  const id = String(t.tid).split('/')[0];
  if(S.some(x => (x.sub||[]).some(v => v.tid === id || v.aid === id))) return true;
  // ⚠A SendMessage-resumed agent has a new tool-use id in the session list — match by its agent id too
  //   (taken from the timeline row with this tid), else a running agent's tab read as finished.
  const tr = TLD && Array.isArray(TLD.rows) ? TLD.rows.find(r => r && r.tid === id) : null;
  const aid = (tr && tr.aid) || t.aid;
  if(aid && S.some(x => (x.sub||[]).some(v => v.aid === aid))) return true;
  return S.length ? false : null;
}
function wtStrip(){
  if(!wtabs.length) return '';
  return '<div class=wtb>' + wtabs.map(t => {
      const live = wtLive(t);
      const cls = live === true ? ' wtrun' : (live === false ? ' wtend' : '');
      const tip = live === true ? T('running') : (live === false ? T('finished or idle') : T('Unknown'));
      // Which pane it is shown in — added only when split (meaningless in single)
      const pn = wtSplit ? (wtPanes.indexOf(t.key) + 1) : 0;
      const on = wtSplit ? (pn > 0) : (wtPanes[0] === t.key);
      return '<span class="wt1'+(on?' on':'')+(pn && pn === wtFocus ? ' wtf' : '')+cls+'" data-wk2="'+esc(t.key)+'">'
      + '<i class="wtk '+(t.kind==='agent'?'wtka':'wtks')+'">'+(t.kind==='agent'?'A':'S')+'</i>'
      + '<i class=wtd title="'+esc(tip)+'"></i>'
      + '<span class=wtl title="'+esc(t.label)+'">'+esc(t.label)+'</span>'
      + (pn ? '<em title="'+esc(wtPaneName(pn))+'">'+pn+'</em>' : '')
      + '<b class=wtx data-wx="'+esc(t.key)+'" title="'+esc(T('Close'))+'">✕</b></span>';
    }).join('')
    // Layout picker (replaces the old «Single»/«Split» toggle + direction button)
    + '<span class=wlo role=group aria-label="'+esc(T('Layout'))+'" title="'
    + esc(T('Drag a divider to resize · narrow windows stack the panes'))+'"><i>'+T('Layout')+'</i>'
    + Object.keys(WT_LAYOUTS).map(id => '<span class="wsb'+(wtLayout===id?' on':'')+'" data-wlo="'+id
        + '" role=button aria-pressed="'+(wtLayout===id)+'" title="'+esc(T(WT_LAYOUTS[id].tip))+'">'
        + T(WT_LAYOUTS[id].lb)+'</span>').join('')
    + '</span></div>';
}
function wtBind(box){
  box.querySelectorAll('.wtx[data-wx]').forEach(b => b.onclick = (e) => {
    e.stopPropagation(); wtClose(b.dataset.wx); });
  box.querySelectorAll('.wt1[data-wk2]').forEach(b => b.onclick = () => wtActivate(b.dataset.wk2));
  box.querySelectorAll('.wlo [data-wlo]').forEach(b => b.onclick = (e) => {
    e.stopPropagation(); if(b.dataset.wlo !== wtLayout) wtSetLayout(b.dataset.wlo); });
  // ★Tabs can be dragged onto a pane (2026-09-02).
  box.querySelectorAll('.wt1[data-wk2]').forEach(el => {
    el.setAttribute('draggable', 'true');
    el.ondragstart = ev => {
      ev.dataTransfer.setData('text/plain', el.dataset.wk2);
      ev.dataTransfer.effectAllowed = 'move';
      wtDragWhat = 'tab';
      el.classList.add('drag');
    };
    el.ondragend = () => { wtDragWhat = ''; el.classList.remove('drag'); };
  });
}
function workOpen(cwd, tid, label, kind){
  const key = wtKey(cwd, tid);
  if(!wtabs.some(t => t.key === key)) wtabs.push({key, cwd, tid, label, kind});
  // When split, open in the **focused pane** — in single mode that tab simply becomes current as before.
  // ★But if the other pane is empty, open **there** (★2026-09-02: after splitting, clicking «Log»
  // twice only changed the same pane while the other stayed 'empty' — defeating side-by-side viewing).
  // Generalized: already shown → focus that pane; else the first empty pane; else the focused pane.
  if(wtSplit){
    const at = wtPanes.indexOf(key);
    const empty = wtPanes.indexOf('');
    if(at >= 0) wtFocus = at + 1;
    else if(empty >= 0 && wtKeyOf(wtFocus)){ wtPanes[empty] = key; wtFocus = empty + 1; }
    else wtPanes[wtFocus - 1] = key;
  } else wtPanes[0] = key;
  agentCwd = cwd; agentTid = tid;
  agentData = wtData[key] || null;
  // ★**Clicking** «Log» or an agent row means wanting to see "what is it doing now" — always go to the bottom (latest).
  // Re-selecting a tab (wtActivate) keeps the position — that is going back, a different intent.
  agentFirst = true;
  toWork();
  buildMv();
  agentRepaint();
  const bx = wkBox();
  if(bx) bx.scrollTop = bx.scrollHeight;      // Scroll to bottom even if the tab is already cached
  delete wtScroll[key];                        // Discard the saved position too (next switch starts from bottom)
  return key;
}
function wtClose(key){
  const i = wtabs.findIndex(t => t.key === key);
  if(i < 0) return;
  wtabs.splice(i, 1);
  delete wtData[key]; delete wtScroll[key];
  if(wtSplit && wtPanes.includes(key)){
    // every pane that showed it takes the next tab not already shown, else stays empty
    wtPanes = wtPanes.map(k => {
      if(k !== key) return k;
      const nx = wtabs.find(t => !wtPanes.includes(t.key));
      return nx ? nx.key : '';
    });
    if(!wtShown().length){
      wtPanes.fill(''); agentTid = ''; agentCwd = ''; agentData = null;
      buildMv(); return wkClose();     // nothing left to show, close the modal
    }
    if(!wtKeyOf(wtFocus)) wtFocus = wtPanes.findIndex(Boolean) + 1;
    wtSetFocus(wtFocus);
    buildMv();
    return workPaint();
  }
  if(!wtSplit && wtPanes[0] === key){
    const nx = wtabs[Math.min(i, wtabs.length - 1)];
    if(nx) return wtActivate(nx.key);
    wtPanes[0] = ''; agentTid = ''; agentCwd = ''; agentData = null;
    buildMv(); return wkClose();       // last tab closed -> nothing left to show, close the modal
  }
  buildMv();
}
function wtActivate(key){
  const t = wtabs.find(x => x.key === key);
  if(!t) return;
  if(wtSplit){
    // ★Put it in the **focused pane**. If already shown in another pane, swap those two panes —
    // showing the same tab in two panes is meaningless; what was wanted is a swap.
    const at = wtPanes.indexOf(key);
    if(at >= 0 && at !== wtFocus - 1){ wtPanes[at] = wtPanes[wtFocus - 1]; }
    wtPanes[wtFocus - 1] = key;
    wtSetFocus(wtFocus);
    agentFirst = false;
    buildMv(); agentRepaint();
    if(!wtData[key] || wtData[key].ok === false) wtFetch(t);
    return;
  }
  if(wtPanes[0]) wtScroll[wtPanes[0]] = (wkBox()||{}).scrollTop || 0;
  wtPanes[0] = key;
  agentCwd = t.cwd; agentTid = t.tid;
  agentData = wtData[key] || null;
  agentFirst = false;
  buildMv(); agentRepaint();
  const box = wkBox();
  if(box) box.scrollTop = wtScroll[key] || box.scrollHeight;
  // Refetch if missing or **cached as a failure** — clicking the tab is the retry
  if(!wtData[key] || wtData[key].ok === false) wtFetch(t);
}
// Work-log GET that rides out 503 (peer check undetermined under load) with 2/4/8/16 s backoff; onBusy() before each wait.
// ⚠Only 503 is retried here — 403 is a real refusal and must surface at once.
function workGetJSON(url, onBusy, n){
  n = n || 0;
  return getJSON(url).catch(e => {
    if(!(e && e.status === 503) || n >= 4) throw e;
    if(onBusy) onBusy();
    return new Promise(res => setTimeout(res, 2000 * Math.pow(2, n))).then(() => workGetJSON(url, onBusy, n + 1));
  });
}
const wtBusy = new Set();   // tab keys inside a 503 backoff chain — polls and clicks must not start a second one
function wtFetch(t, retry){
  // ★Do **not swallow** failures. Before it was `.catch(()=>{})`, so when a request broke the tab stayed on
  // «Loading…» forever with no progress shown.
  // The screen must state the reason so the user can decide whether to click again.
  if(!t || wtBusy.has(t.key)) return;
  const url = workUrl(t.cwd, t.tid);
  workGetJSON(url, () => {
    wtBusy.add(t.key);
    if(wtData[t.key] && wtData[t.key].ok !== false) return;   // keep showing data already received
    wtData[t.key] = {ok:false, busy:true, msg:T('Viewer is busy — retrying…')};
    if(wtKeyOf(wtFocus) === t.key) agentData = wtData[t.key];
    if(wtShown().includes(t.key)) agentRepaint();
  })
    .then(j => {
      wtBusy.delete(t.key);
      // Even when the server returns a failure with a reason, ask once more (the allow list may be fluctuating)
      if(j && j.ok === false && !retry){ return setTimeout(() => wtFetch(t, 1), 900); }
      wtData[t.key] = j;
      if(wtKeyOf(wtFocus) === t.key) agentData = j;
      if(wtShown().includes(t.key)) agentRepaint();
      buildMv();
    })
    .catch(e => {
      wtBusy.delete(t.key);
      // ★Retry once silently (2026-09-02: work history occasionally failed to load).
      // If the server is heavy at that moment (ps delay, large transcript parse) it bounces once and succeeds next time.
      if(!retry && !(e && e.status === 503)){ return setTimeout(() => wtFetch(t, 1), 900); }   // 503 already backed off
      const j = {ok:false, msg:T('Could not fetch') + ' — ' + ((e && e.message) || T('unknown error'))
                 + ' ' + T('(click the tab again to retry)')};
      wtData[t.key] = j;
      if(wtKeyOf(wtFocus) === t.key) agentData = j;
      if(wtShown().includes(t.key)) agentRepaint();
      buildMv();
    });
}
