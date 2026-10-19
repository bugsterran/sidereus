// Claude session panel — **not the conversation, but what the session is doing now**.
//   Source: the last event of ~/.claude/projects/<slug>/<sessionId>.jsonl (the server extracts metadata only).
//   ⚠"working" is an estimate — based on when lines are appended to the transcript. While the model only thinks
//   no lines are appended, so it **briefly looks idle.** Hence only three colors (running / recent / idle).
function ago(sec){
  if(sec<60) return U(sec,'s');
  if(sec<3600) return U(Math.floor(sec/60),'m');
  // ★Down to days — a session left quiet for days shown as "72 hours" doesn't read as how long it was abandoned.
  if(sec<86400) return U(Math.floor(sec/3600),'h');
  return U(Math.floor(sec/86400),'d');
}
// Size — as the transcript grows, the context sent each turn grows too (the real cost driver).
function sz(b){
  if(!b) return '';
  if(b < 1048576) return Math.round(b/1024)+'K';
  if(b < 1073741824) return Math.round(b/1048576)+'M';
  return (b/1073741824).toFixed(1)+'G';
}
function money(c){ return !c ? '' : fmtMoney(c); }   // rules live in fmtMoney (00-core.js)
// ★State labels — telling "is it done" at a glance is this panel's purpose (2026-08-18).
//   run  = model/tool running (ball with the model)   wait = **response done · awaiting input** (ball with the human)
//   done = no process (finished session)            unknown = process unreadable (no assertion)
//   ⚠Labels are neutral — first written as '★my turn', fixed because "whose turn" didn't read on screen.
//     "awaiting input" means *that session finished its turn*, which answers "is the work done".
let sessOpen = false;              // expanded state of finished sessions — survives polling

// ★Idle/unpushed filters (backlog 2026-08-19) — the goal is **reduction**. With twenty sessions sorting alone doesn't reveal them.
//   Only states **where the ball is with the human** count as idle: response done · question waiting · aborted.
//   Tool running / thinking is not idle even past 20 min (5-min tools are known to be normal — liveness is judged by process).
//   'unknown' means the process couldn't be read, so it is **not asserted** idle (this file's rule: no coloring by guess).
const IDLE_ST = { wait:1, ask:1, abort:1 };
const IDLE_STEPS = [0, 10, 30, 60];      // 0 = filter off. Clicking the chip cycles (no hidden modifier-key tricks)
const GIT_STEPS  = ['', 'push', 'dirty'];// '' = off · push = unpushed (↑) only · dirty = unpushed or dirty (↑~)
let idleMin = 0, gitFil = '', stFil = '';   // stFil: '' | 'ask' | 'abort' | 'hot' | 'blocked' (top bar)
{ const v = lsJson('mbSessFil', {});
  if(IDLE_STEPS.includes(v.idle)) idleMin = v.idle;
  if(GIT_STEPS.includes(v.git)) gitFil = v.git;
  if(['','ask','abort','hot','blocked'].includes(v.st)) stFil = v.st; }
// also accept 'time' as a saved mode
function saveFil(){ lsSetJson('mbSessFil', {idle:idleMin, git:gitFil, st:stFil}); }
// The marker threshold is **the filter value when on**, 30 min when off (so there aren't two thresholds).
const markMin = () => idleMin || 30;
const isIdle = (x, m) => !!IDLE_ST[x.state] && x.ageSec >= m*60;
const hasGit = (x, mode) => { const g = x.git || '';
  return mode==='push' ? g.indexOf('\u2191')>=0 : (mode==='dirty' ? !!g : true); };
// ★«Response done» → «Awaiting input» ("waiting" fits better than "response done") —
//   it **declares done while actually waiting**, and with background work running it is outright false.
//   «Awaiting input» instead of a bare «Waiting» because naming what it waits for pairs it with «Subagent waiting on work»
//   (human's turn / not human's turn is told by the label alone).
const LBL = { tool:'Running a tool', think:'Thinking', ask:'Awaiting answer', wait:'Awaiting input',
              abort:'Aborted', done:'Ended', gone:'Disconnected', unknown:'Unknown' };
// ⚠Show through stateLbl(): three labels are context keys in Korean (plain 'Aborted' / 'Thinking' / 'Unknown' are other words).
const LBL_CTX = { think:'now', abort:'state', unknown:'short' };
function stateLbl(k){ return Object.prototype.hasOwnProperty.call(LBL, k) ? T(LBL[k], LBL_CTX[k] || null) : ''; }
// ★State text is built **only here** (2026-09-02: timeline and Claude session state messages differed).
//   The session card used to build **derived text** like «Blocked · reason», «Running a tool 32m», «Subagent waiting on work»
//   on its own, while the timeline mapped only raw state via LBL — the same session had two names.
//   Per this file's rule that two places must not say different things, it is gathered into one function.
// Burn per minute is compared to **the sustainable rate**: 5h limit ÷ 300 min. Above it the block burns early.
//   ⚠Without a known limit no color (no painting by estimate — this file's rule).
// ★2026-09-27 cross-tab audit: the 5h limit is only the server back-solve (BURN.head.lim, measured src).
//   ⚠USG.block.max is the abandoned 519M anchor (~8x the real ~65M) — it painted «Normal» while #burn said «Runs out».
function burnLim(){
  const h = (typeof BURN !== 'undefined' && BURN && BURN.ok) ? BURN.head : null;
  return (h && h.lim > 0 && h.src && h.src !== 'anchor') ? h.lim : 0;
}
function burnBand(burn){
  const lim = burnLim();
  const pace = lim ? lim / 300 : 0;
  if(!pace || !burn) return null;
  const r = burn / pace;
  const B = [[0.5,thc('#5fd3ba','#1a7f6a'),T('Easy')],[1,thc('#8b95a7','#61656c'),T('Normal')],[2,thc('#e8b478','#a35c00'),T('Fast')],[1e9,thc('#e0736c','#c11e32'),T('Very fast')]];
  const b = B.find(x => r < x[0]) || B[B.length-1];
  return {col:b[1], lab:b[2], ratio:r, pace:Math.round(pace)};
}
function sessLabel(x){
  if(!x) return stateLbl('unknown');
  const st = x.state || 'unknown';
  if(st === 'gone') return T(x.goneWhy === 'silent' ? 'Disconnected?' : 'Disconnected');   // external CLI killed without SessionEnd (sidereus/ext.py)
  // ⚠Codex row read from its rollout file (no hooks): only the file's age is known — never an input/answer/blocked state.
  if(x.rollout) return typeof x.ageSec === 'number'
    ? TV({msg: 'Last activity {n}m ago', vars: {n: Math.max(0, Math.floor(x.ageSec / 60))}}) : stateLbl('unknown');
  // ⚠Fixed server label: must not reach the split below, or "subagent" is shown as a tool name.
  if(x.blocked === 'subagent waiting for approval') return T('Blocked') + ' · ' + T(x.blocked);
  // sidereus/live_probe.py sends '<Tool> waiting for approval': the tool name stays as-is, only the suffix is translated.
  const bw = typeof x.blocked === 'string' && / waiting for approval$/.test(x.blocked) ? x.blocked.slice(0, -21) : null;
  if(bw) return T('Blocked') + ' · ' + bw + ' ' + T('waiting for approval');
  if(x.blocked) return T('Blocked') + ' · ' + T(srvEn(x.blocked));
  // ★Prompt arrived but the transcript didn't move (server gotPrompt). Calling it «Thinking» is false, and
  //   calling it «Awaiting input» means it is the human's turn, also false — **only what is known** is written.
  if(x.gotPrompt > 0)
    return TV({msg: 'Prompt received · no record for {n}m', vars: {n: Math.max(1, Math.floor((x.ageSec||0)/60))}});
  // quiet for 10+ min gets a duration — not declared dead, only **how long** it has been
  // ★600s → 300s (2026-09-04). A 7-minute generation showed only as «Thinking» and read as "not recognized".
  //   For long work, **how long it has been** is information in itself.
  if((st === 'tool' || st === 'think') && x.ageSec >= 300)
    return stateLbl(st) + ' ' + U(Math.floor(x.ageSec / 60),'m', 'ongoing');
  // model turn done but background running is not «Awaiting input» — it is not the human's turn
  return waitOnLabel(x, st) || stateLbl(st) || stateLbl('unknown');
}
// ⚠A Workflow call returns at launch, so the parent ends its turn while the run goes on (server `wf[].run`).
function wfRunning(x){ return (x.wf||[]).some(w => w && w.run); }
// What a finished turn is still waiting on ('' when it really is the human's turn). Shared by list and timeline.
function waitOnLabel(x, st){
  if(st !== 'wait') return '';
  if(wfRunning(x)) return T('Workflow running');
  const w1 = (x.sub||[]).length ? T('Subagent') : ((x.bgs||[]).length ? T('Command') : '');
  return w1 ? w1 + ' ' + T('waiting on work') : '';
}
// Muted «· Mailbox watch N» beside «Awaiting input» ('' otherwise). ⚠Count only — monitors don't change the state (still the human's turn).
function monSuffix(x, st){
  if(!x || st !== 'wait' || x.blocked || x.gotPrompt > 0 || waitOnLabel(x, st)) return '';
  const n = (x.mon || []).length;
  return n ? '· ' + TV({msg: n === 1 ? '{n} monitor' : '{n} monitors', vars: {n}}) : '';
}
// Slot the timeline uses — checks **the live session list (SESS)** first.
// ⚠The timeline response is up to 30s stale (refresh period). Cards are 2.5s — so the same session looked different.
//   Find the current value by cwd; only if missing (session gone out of the window) use what the timeline brought.
// ⚠Match the platform too — a Gemini row and a Claude row can share one cwd.
function tlLiveOf(cwd, plat){
  return (SESS||[]).find(x => x && x.cwd === cwd && (x.plat || 'cc') === (plat || 'cc'));
}
// One state glyph — speaks by color/shape/motion; the sentence goes in the tooltip
function tlStateDot(it){
  const s = tlSessLabel(it);
  const live = tlLiveOf(it.cwd, it.plat);
  const st = it.blocked ? 'blocked'
           : ((live && live.gotPrompt > 0) ? 'stuck'
           : ((live && live.state) || it.state || 'unknown'));
  const dots = (st === 'think') ? '<i></i><i></i><i></i>' : '<i></i>';
  return '<span class="tlsi s-'+esc(st)+'" style="color:'+s.col+'" title="'+esc(s.lab + (s.mon ? ' ' + s.mon : ''))+'">'
       + dots + '</span>';
}
function tlSessLabel(it){
  const live = tlLiveOf(it.cwd, it.plat);
  const x = live || {state: it.state, blocked: it.blocked, ageSec: it.idle, sub: [], bgs: []};
  const key = (x.gotPrompt > 0) ? 'stuck' : (x.state || 'unknown');
  return {lab: sessLabel(x), mon: monSuffix(x, x.state), col: (TLS[key] || TLS.unknown)[0], live: !!live};
}
// ★Blocked tooltip — states the evidence. What was observed to reach that verdict, not a guess, must be on screen
//   so the user can catch misjudgments (same principle as this file's other verdicts).
const BLKTIP = '★Needs you to approve or choose — a tool call is pending with no sign of running (a fast tool taking long, or Bash with no process). MCP tools can legitimately take long, so they are not judged';
const WAITTIP = 'The model turn ended but background work is still running — the session moves again when results arrive (not your turn yet)';
const TIP = {
  tool:'Running a tool — the tool name beside it is what runs now (long commands keep the screen quiet)',
  think:'The model is processing a tool result — the next tool call or reply comes soon',
  ask:'★Needs you to continue — awaiting an answer or plan approval',
  wait:'Finished its reply and awaits your input — it stays put until you give another instruction (your turn)',
  abort:'Interrupted by you (Esc) — it moves again only with a new instruction',
  done:'No claude process — an ended session (use --resume to continue)',
  gone:'The CLI process went away without an end event (killed, terminal closed) — it leaves the list in 10 min. «Disconnected?» is a guess: no pid and no news for over 20 min',
  unknown:'Could not read the process state — not assumed either way' };
// ★Up to here is what the transcript **can determine**. Waiting on a permission prompt leaves no line, so it can't be told —
//   then the last event is a tool call and it shows as «Running a tool» (unknown is stated as such, not invented).
// Filter chips — **chips stay** even when the list is empty (so "empty because of a filter" vs "no sessions" is distinguishable).
// ★Stale threads — discussions **unclosed and long quiet**. Material for the advocate charter's axis 3 (3 round trips with no verdict) and axis 4 (agreed but
//   not done); until now visible only by reading `bus.jsonl` by hand.
//   Measured 2026-08-19: of 72 threads, 6 had 4+ posts · unclosed · 2+ people, and 4 of those were quiet for **7-13 days**.
//   ⚠The server is not touched — what the verdict needs (all MSGS · the `DONE` tag set) is already on the page.
const STALE_H = 24;               // quiet this long = stale candidate (a day is a normal round-trip interval, so set above it)
const DEAD_D = 14;                // ★cap — quiet longer than this means **finished, not stale**
// Optimistic «Clear»: thread -> ms sent. ⚠Held 60s after success so the row does not flash back before the `[DONE]`-tag post polls in (demo never writes it).
const THCLOSING = {};
const thClosing = th => !!THCLOSING[th] && Date.now() - THCLOSING[th] < 60000;
// ★Why a cap was needed (measured 2026-08-19): without one **17** were caught, 11 of them quiet for 15-23 days.
//   Those are not to act on but **finished discussions** — the `[DONE]`-tag habit came later in this room, and old threads
//   have no tag even when decided. Relying on tags alone misreads "closed but unmarked" as stale.
//   Why 14 days: the measured distribution splits between 8 and 12 days, and everything above 14 was finished domain work.
//   ⚠What is cut is **not hidden** — stated at the end of the list as «14d+ N» (silently cutting reads as "none").
function staleThreads(){
  const per = {};
  MSGS.forEach(m => { if(!m.thread || m.selfaddr) return; (per[m.thread] = per[m.thread] || []).push(m); });
  const now = Date.now() * 1e6, out = [];
  let dead = 0;
  for(const th in per){
    const v = per[th].slice().sort((a,b) => a.t - b.t);
    if(v.length < 4) continue;                                  // round trips still too few to call it a deadlock
    if(new Set(v.map(m => m.from)).size < 2) continue;           // a thread written by one person is not a discussion
    if(closedT(v) || thClosing(th)) continue;                   // closed with the finish tag (closedT), or «Clear» in flight, is not stale
    const idleH = (now - v[v.length - 1].t) / 1e9 / 3600;
    if(idleH < STALE_H) continue;
    if(idleH > DEAD_D * 24){ dead++; continue; }
    // ★"Whose turn" — saying only that it stopped **leaves what to do undecided.** The side that did not post last is up.
    //   With three or more, all are listed — picking one arbitrarily is a guess.
    const last = v[v.length - 1].from;
    const turn = [...new Set(v.map(m => m.from))].filter(w => w !== last);
    out.push({th: th, n: v.length, who: new Set(v.map(m => m.from)).size, idleH: idleH, turn: turn, last: last});
  }
  out.sort((a, b) => b.idleH - a.idleH);
  out.dead = dead;                       // count cut (stated on screen)
  return out;
}
