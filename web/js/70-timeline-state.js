// Middle-column toggle + (in work-history mode) the row of open tabs
// ★Agent Gantt (2026-09-01) — see with your eyes whether 5 spawned agents really ran in parallel.
// Start/end are the creation and last-modified times of that agent's log file. End is 'last written', so
// slightly earlier than the real finish — the screen calls it that (nothing invented).
let TLD = null, tlAt = 0;
let tlSeq = 0, tlBusy = false, tlErr = '';   // Overlap/order guard + last failure text
// ── Timeline time cursor state ───────────────────────────────────────────────
// ★The window (t0/t1) is **recorded here at draw time**. It is a local in paintTl, invisible outside,
// but the cursor must convert mouse x into «absolute time», which needs the window.
// Pin holds an **absolute time** — even when redrawn every 30s (window shifting) it points to the same moment.
let tlCurT0 = 0, tlCurT1 = 0;
let tlCurRows = [];        // Rows last **drawn** — snapshot input (must equal what was drawn)
let tlCurAt = 0;           // Time the cursor points to (0 = no cursor)
let tlCurPin = false;      // Pinned by click?
let tlCurXY = [0, 0];      // Where to place the panel (px relative to .tlwrap)
let tlCurEv = null, tlCurRaf = 0;
// ── Replay (timelapse) ────────────────────────────────────────────────────
// Makes the cursor **walk by itself**. Playback speed is "timeline seconds / 1 real second".
// ⚠Runs on rAF — the browser pauses it when the tab is hidden (setInterval keeps running in background).
const TL_RSP = [[60,'1 min/s'],[300,'5 min/s'],[1800,'30 min/s']];
let tlRpOn = false, tlRpRaf = 0, tlRpPrev = 0;
let tlRpSpeed = (() => { try { const n2 = +UIS.mbTlRp;
                               return TL_RSP.some(x=>x[0]===n2) ? n2 : 300; }
                         catch(e){ return 300; } })();
let tlHours = (() => { try { const v = parseFloat(UIS.mbTlHours);
                             return (isFinite(v) && v >= 0.5 && v <= 168) ? v : 6; }
                       catch(e){ return 6; } })();
// ★Auto-refresh interval (s). 0 = manual (2026-09-01). Remembered in the browser.
// Label = the whole «every …» phrase (T() key); 0 = manual.
const TL_EVERY = [[0,'Manual'],[30,'every 30s'],[60,'every 1 min'],[300,'every 5 min'],[600,'every 10 min'],[1800,'every 30 min'],[3600,'every hour']];
// Defaults: every 30s · last 12 hours (2026-09-01)
let tlAuto = (() => { try { const v = UIS.mbTlAuto;
                            const n2 = +v;
                            return (v != null && TL_EVERY.some(x=>x[0]===n2)) ? n2 : 30; }
                      catch(e){ return 30; } })();
// ★Agent rows labeled by the Agent tool's one-line `description` (2026-09-25: rows of the same type were indistinguishable).
// «Running only» filter: hides finished subagent rows (row `run`); session rows stay. Remembered per browser.
let tlRunOnly = lsGet('sidereus.tlrun', '0') === '1';
let tlAgDesc = (() => { try { return UIS.getItem('sidereus.agdesc') !== '0'; } catch(e){ return true; } })();
// Agent row group -> {lab, type}; lab = latest run's description (Claude subagents only, `aid` set), else type. ⚠off = type only.
function tlAgLab(g, on){
  const r = (g && g.items && g.items[g.items.length - 1]) || {};
  const d = (on && !g.sess && r.aid && r.desc) ? plStrip(String(r.desc)) : '';
  return d ? {lab: d, type: g.type} : {lab: g.type, type: ''};
}
function tlAgNm(g, on){
  const r = (g && g.items && g.items[g.items.length - 1]) || {};
  // Workflow run row: «name [workflow] [1/4] [phase]» — one line like agent rows; time/tokens live on the bar (2026-09-26).
  if(r.wf){
    const w = r.wf;
    return '<em class=tlagd title="' + esc(w.name || w.id || '') + '">' + esc(w.name || String(w.id || '').slice(0, 11)) + '</em>'
      + '<i class="tlpar tlwfk">' + esc(T('Workflow')) + '</i>'
      + '<i class=tlpar>' + (w.done || 0) + '/' + (w.total || 0) + '</i>'
      + (w.phase ? '<i class="tlpar tlagt">' + esc(w.phase) + '</i>' : '')
      + (w.fail ? '<i class="tlpar tlwff">' + esc(U(w.fail, '#msgs') + ' ' + T('failed')) + '</i>' : '');
  }
  const a = tlAgLab(g, on === undefined ? tlAgDesc : on);
  const wb = /^wfa:/.test(String(r.tid || '')) && typeof wfBadge === 'function' ? wfBadge(wfRunNameOf(r.tid, r.par), g.type) : '';   // Workflow-run agent (48g)
  return a.type ? '<em class=tlagd title="'+esc(a.lab)+'">'+esc(a.lab)+'</em><i class="tlpar tlagt">'+esc(a.type)+'</i>' + wb : esc(a.lab) + wb;
}
const TLC = {run:'#5b8def'};
// ★Project (repo) colors — **the same 7 colors** as repoHue used elsewhere (diff tab, timeline chips).
// Painting bars in this color tells which project they belong to by color alone (2026-09-01).
const HUE7 = ['#8ab4f8','#5fd3ba','#f0b357','#c98fd8','#9ccc8f','#e88f8f','#c9c34a'];
const HUE7_LT = ['#3f7fd6','#2f9a90','#c26a1e','#8a62c9','#4f9a4a','#d95f5f','#9a7a12'];   // light pairs: >=3:1 on the light track (pastels were 1.81-2.09)
const projColor = cwd => thc(HUE7, HUE7_LT)[repoHue(cwd) % HUE7.length];
// ★Subagents are **colored by type** (2026-09-01) — several types run within one project, so
// project colors would make them all the same color and rows indistinguishable.
// Uses a separate band with lower saturation/lightness so it does not mix with project colors.
function agColor(t){
  let h = 0; for(let i=0;i<t.length;i++) h = (h*37 + t.charCodeAt(i)) % 360;
  return 'hsl('+h+' 38% '+thc('52%)', '42%)');   // light 42%: greens at 52% were 2.5:1 on the light track
}
// ★Session state colors/names — one bar can only say 'now', so the tooltip says so.
const TLS = {stuck:['#c98fd8','Prompt received, quiet'],
             tool:['#5b8def','Running a tool'], think:['#7aa7e8','Thinking'],
             wait:['#c9a24a','Awaiting input'],   ask:['#e0a33a','Awaiting answer'],
             abort:['#e0725f','Aborted'],     done:['#4e5765','Ended'],   gone:['#5b6472','Disconnected'],
             unknown:['#5b6472','Unknown']};

async function loadTl(force){
  // ★Fetch only while viewing the timeline tab — calling every 20s when unseen makes the server do useless work.
  // Refresh interval is **1 min** (2026-09-01). Bars only change meaning at minute resolution.
  if(!force && mainView !== 'time') return;
  if(!force && document.hidden) return;   // hidden tab: the visibilitychange poll refreshes it once on return
  if(!force && (!tlAuto || Date.now() - tlAt < tlAuto * 1000)) return;   // Manual (0) — do not call
  tlAt = Date.now();
  // ★**Do not erase what was drawn on failure** (2026-09-09: flickered a few times then vanished).
  // Before, `catch` **overwrote** `TLD` with an error object — a single failure from a server restart or load spike
  // made the bars vanish entirely (running markers too). That is opposite to this file's rule:
  // "do not claim an unknown span was empty" ⇒ keep the last received data and state it in text.
  // ★No overlapping calls, and **late responses are dropped** — there are two call sites (main poll · `tlAgeTick`),
  // so an old response arriving later would overwrite the new screen with old data.
  if(tlBusy) return;
  tlBusy = true; tlReqAt = Date.now();
  const want = ++tlSeq;
  // ⚠Abort a hung request so the first paint can show a reason + retry instead of waiting forever.
  const ac = (typeof AbortController === 'function') ? new AbortController() : null;
  const to = ac ? setTimeout(() => ac.abort(), TL_TIMEOUT_S * 1000) : 0;
  if(!TLD) tlWaitTick();
  try{
    const d = await getJSON('/api/agents/timeline?hours='+tlHours, {signal: ac ? ac.signal : undefined});
    if(want === tlSeq){ TLD = d; tlErr = ''; }
  }catch(e){
    if(want === tlSeq) tlErr = 'Could not fetch — showing the last data received';
    const why = (e && e.name === 'AbortError') ? T('No response') + ' (' + U(TL_TIMEOUT_S, 's') + ')'
              : ((e && e.message) || T('unknown error'));
    if(!TLD) TLD = {ok:false, msg: T('Could not fetch') + ' — ' + why};
  }finally{ clearTimeout(to); tlBusy = false; tlReqAt = 0; }
  paintTl();
}
// ★First-load counter (2026-09-23): after a restart the first response took 5 s+ and `#feed` stayed blank.
let tlReqAt = 0, tlWaitTimer = 0;
const TL_TIMEOUT_S = 90;
function tlWaitTick(){
  clearInterval(tlWaitTimer);
  tlWaitTimer = setInterval(() => {
    const el = document.getElementById('tlwait');
    if(!el || !tlReqAt || TLD){ clearInterval(tlWaitTimer); return; }
    el.textContent = U(Math.round((Date.now() - tlReqAt) / 1000), 's');
  }, 1000);
}
// Show seconds since last refresh — the only way to tell whether the screen is frozen
let tlAgeTimer = 0;
function tlAgeTick(){
  clearInterval(tlAgeTimer);
  tlAgeTimer = setInterval(() => {
    if(document.hidden) return;   // hidden tab: no DOM writes, no polling; tlAt goes stale so the first visible tick reloads
    const el = document.getElementById('tlage');
    if(!el){ clearInterval(tlAgeTimer); return; }
    const s2 = Math.max(0, Math.round((Date.now() - tlAt) / 1000));
    el.textContent = ' · ' + AGO(s2 < 60 ? U(s2,'s') : U(Math.floor(s2/60),'m'))
      + (tlAuto ? '' : ' (' + T('Manual') + ')');
    if(tlAuto && mainView === 'time' && Date.now() - tlAt >= tlAuto * 1000) loadTl();
  }, 1000);
}
