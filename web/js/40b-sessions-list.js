function buildSessions(){
  const box=document.getElementById('sess');
  if(!box) return;
  if(sessHover){ sessDirty = true; buildFilters(); return; }   // filters are safe to update (the mouse is outside)
  buildFilters();
  // No session at all = likely a first run: name the next step under the empty line.
  if(!SESS.length){ setHtml(box, '<div class=hidnote>'+esc(T('No sessions active in the last 12 hours.'))+'</div>'
    + '<div class=hidnote>'+esc(T('Next: start an AI coding-agent session — it shows up here within seconds.'))+'</div>'); return; }
  // ★So the sidebar doesn't grow with more sessions: **finished ones are folded** (count only) and the rest scroll in this area.
  //   The server sorts state-first (working → awaiting input → unknown → finished), then by recent activity within a state.
  const stOK = x => !stFil
    || (stFil === 'hot' ? (x.win && x.ctx && x.ctx / x.win >= 0.85)
    : (stFil === 'blocked' ? !!x.blocked : x.state === stFil));
  const pass = x => (!idleMin || isIdle(x, idleMin)) && (!gitFil || hasGit(x, gitFil)) && stOK(x);
  const act0 = SESS.filter(x => x.state !== 'done' && pass(x));
  const fin0 = SESS.filter(x => x.state === 'done' && pass(x));
  const pk = acctPick('sess'), keep = x => ACC_OTH.sess || acctInPick(x, 'sess', pk);
  // Count only what the off state would show here: ended rows only while the ended fold is open.
  const act = act0.filter(keep), fin = fin0.filter(keep), oth0 = (sessOpen ? act0.concat(fin0) : act0).filter(x => !keep(x));
  const rows = (sessOpen ? act.concat(fin) : act);
  const hid = SESS.length - (act0.length + fin0.length);      // count hidden by filters — **never silently reduced**
  morphHtml(box, wfFoldBtns(rows) + rows.map(x => sessRowHtml(x)).join('')
    + acctOthHtml('sess', oth0.length, oth0.some(x => x.blocked || x.state === 'ask' || x.state === 'abort'))
    + (fin.length ? '<div class=sfold id=sfold>' + TV({msg: sessOpen ? '▾ Hide {n} ended' : '▸ Show {n} ended', vars: {n: fin.length}}) + '</div>' : '')
    + (act.length ? '' : '<div class=hidnote>' + (idleMin||gitFil ? T('No active sessions match the filter.') : T('No active sessions.')) + '</div>')
    + (hid ? '<div class=hidnote>'+TV({msg: '{n} hidden by filter', vars: {n: hid}})+'</div>' : ''));
  const f = document.getElementById('sfold');
  if(f) f.onclick = () => { sessOpen = !sessOpen; buildSessions(); };
  sessFit(box);
  buildInvite();
  // ★The list redraws every 2.5s, so no handlers on rows; **delegated to one container**
  //   (listeners piling up on every poll would leak).
  box.onclick = sessClick;
}
// Identity rows are one line (60-sessions.css): when the row overflows or the name/branch would ellipsize under 96/64px,
// hide whole low-priority chips in this order — size · cost/tokens · model. ⚠Errors, diff, leftovers, context and ↻ never hide.
const SX_DROP = ['sz', 'sk', 'sm'];
function sessFit(box){
  // ⚠Width changes without a repaint (pin/unpin, window resize, demo data never changes) — refit on box resize.
  if(!box._sxro && window.ResizeObserver){ box._sxro = new ResizeObserver(() => sessFit(box)); box._sxro.observe(box); }
  for(const r of box.querySelectorAll('.sx')){
    r.querySelectorAll(':scope > .sxh').forEach(e => e.classList.remove('sxh'));
    if(!r.clientWidth) continue;
    // ⚠.sb is a flex chip now (branch .sbt + git state): its own scrollWidth no longer shows the cut, its .sbt does
    const ids = [...r.querySelectorAll(':scope > :is(.sp,.swt), :scope > .sb > .sbt')];
    const bad = () => r.scrollWidth > r.clientWidth + 0.5
      || ids.some(e => e.scrollWidth > e.clientWidth + 0.5 && e.clientWidth < (e.classList.contains('sp') ? 96 : 64));
    for(const c of SX_DROP){
      if(!bad()) break;
      r.querySelectorAll(':scope > .' + c).forEach(e => e.classList.add('sxh'));
    }
  }
}// Identity-row badges after the branch: error · git · leftovers · context · size · cost · model · resume.
function sessBadges(x){
  // ★Context **uses no bar** — limits differ per model (1M/200k), so one bar would be false.
  //   Only the number is colored: 600k+ caution · 850k+ warning (for 1M sessions). Values with unknown limits get no color.
  // ★The ceiling is **the model window**, not ours (1m sessions ~1M · 200k models ~200k). Reaching it, the harness
  //   auto-compacts and this number drops sharply — so we don't clamp and use the value as-is.
  //   From 1000k it is shown in M (more digits made the row jitter).
  // ★% is better (2026-08-19) — absolute values mean nothing without the model window (150k on a 200k model is nearly full).
  //   Models with unknown windows get no %, only the absolute value. Reaching the window, auto-compaction drops this value sharply.
  const k = x.ctx ? Math.round(x.ctx/1000) : 0;
  // Uppercase K/M to match fmtTok («264M» · «1.7B») — one token notation across the UI.
  const abs = k>=1000 ? (x.ctx/1e6).toFixed(2).replace(/0$/,'')+'M' : k+'K';
  const pct = (x.win && x.ctx) ? Math.round(x.ctx/x.win*100) : 0;
  const est = pct && x.winSrc === 'model';        // window learned from **another session of the same model** (estimate)
  const ctxCls = (pct ? (pct>=85 ? ' hot' : (pct>=60 ? ' mid' : (pct>=40 ? ' ok' : ' cool'))) : '')
    + (est ? ' est' : '');
  const ctxLbl = pct ? pct+'%' : abs;
  // ★Evidence goes in the tooltip — window detection is observational, and if "where does this % come from" can't be asked it can't be trusted.
  const winLbl = x.win>=1000000 ? '1M' : Math.round(x.win/1000)+'K';
  const basis = est
    ? TV({msg: 'estimate — a {w} window was observed in {n} {m} sessions on this machine (auto-compaction point or over 200K). This session has not passed 200K yet, so it has not proven it itself',
          vars: {w: winLbl, n: (x.winN||0), m: x.model || T('same-model')}})
    : T('proven by this session — seen over 200K, or its own auto-compaction point');
  const ctxTip = (pct ? abs+' / '+winLbl+T(' window · ')+basis
                      : abs+T(' (window unknown — no auto-compaction seen for this model yet, so no %)'))
    + T(' · as of the last response (cache read + write + input) · drops via auto-compaction when it hits the window');
  const ctx = k ? '<span class="sc'+ctxCls+'" title="'+esc(ctxTip)+'">'+ctxLbl+'</span>' : '';
  const errb = x.err ? '<span class=se title="'+esc(T('The last tool result was an error'))+'">!</span>' : '';
  // ★Clicking the badge expands that session's diff (otherwise what subagents edited is hard to skim).
  //   Even with clean git there may be untracked files, so it is clickable whenever there is a cwd.
  const gitOpen = false;   // ★the main view has no diff — open state is unknowable (it is a separate window)
  // With a branch, the branch chip carries the git state and opens the diff (sessBranchHtml) — two chips opening
  // the same window read as two different actions and cost the width the branch name needed at 900.
  const git = x.cwd && !x.branch
    ? '<span class="sg hit'+(gitOpen?' on':'')+'" data-diff="'+esc(x.cwd)+'" title="'
      + esc((x.git ? T('↑unpushed ~dirty · ') : '')
        + (extTid(x) ? T('View changes (diff) in this folder — by folder, not by session') : T("Click to view this session's changes (diff)")))+'">'
      + (x.git ? esc(x.git)+' ' : '') + (extTid(x) ? esc(T('Folder diff')) : 'diff') + '</span>'
    : '';
  // ★The session's own work log (2026-08-26) — four sessions run at once but only one terminal is watched.
  //   Uses **the same screen** as the subagent modal (same parser, same renderer).
  // The «Log» badge was removed: clicking the card itself opens the work log (fewer badges on a narrow row).
  // ★Leftovers — number of **files touched by dead agents and left uncommitted** under this session path. Not drawn at 0.
  //   ⚠A clue, not proof (same as the `wreckage` comment) — so it only says "left over".
  const wrk = (x.wreck > 0)
    ? '<span class=swr data-wreck="'+esc(x.cwd)+'" title="'+esc(TV({msg: '{n} files touched by an interrupted subagent are still uncommitted — you decide whether to finish or revert. Click to open the diff', vars: {n: x.wreck}}))
      +'">'+T('Leftover ')+x.wreck+'</span>' : '';
  const model = x.model ? '<span class=sm>'+esc(x.model)+'</span>' : '';
  // ★Cost is **the project total** (ccusage doesn't give per-session). Two sessions of the same project
  //   show the same value, so the tooltip says so — read per session it would be false.
  const cost = x.cost ? '<span class=sk title="'+esc(TV({msg: '{n} project total cost {m} — a per-project total, not per session; subagents are counted separately', vars: {n: x.project, m: money(x.cost)}}))
    +'">'+money(x.cost)+'</span>' : '';
  // ★Size warning — colored above 500M. A big transcript means more context resent every turn.
  const big = x.bytes >= 524288000;
  const size = x.bytes ? '<span class="sz'+(big?' hot':'')+'" title="'+esc(T('Transcript ')+sz(x.bytes)
    +(big ? T(' — over 500M. The longer a session runs, the more context each turn carries (a new session may be cheaper)') : ''))
    +'">'+sz(x.bytes)+'</span>' : '';
  // ★Copy `claude --resume` — the server had the full session id but sent it cut to 8 chars, so
  //   **there was no way to resume a finished session.** This chip copies that resume command.
  //   ⚠Do not drop `plat==='cc'` - external CLI sessions would get a command they don't understand.
  // an extra Claude root resumes under its own config dir (resumeCmd adds CLAUDE_CONFIG_DIR)
  const rzc = x.acctDir ? resumeCmd(x.cwd, x.sid, x.acctDir) : 'cd '+x.cwd+' && claude --resume '+x.sid;
  const rs = (x.sid && x.sid.length > 8 && x.cwd && (!x.plat || x.plat === 'cc'))
    ? '<span class=srz data-rz="'+esc(rzc)+'" title="'+T('Copy: ')+esc(rzc)+'">↻</span>' : '';
  return errb + git + wrk + ctx + size + cost + extTokChip(x) + model + rs + termBtnHtml(x, 'sx');   // switch-to-terminal chip (88d-term.js)
}
// External CLI session tokens (from its own chat file). Cost is an estimate from a bundled price table (`estCost`).
function extTokChip(x){
  if(!x.plat || x.plat === 'cc' || !x.tok) return '';
  const s = x.tokSplit || {};
  const tip = T('Session total tokens ') + x.tok.toLocaleString()
    + '\n' + T('Input') + ' ' + fmtTok(s.in||0) + ' · ' + T('Cache') + ' ' + fmtTok(s.cache||0)
    + ' · ' + T('Output') + ' ' + fmtTok(s.out||0) + ' · ' + T('Thinking') + ' ' + fmtTok(s.thought||0)
    + '\n' + extCostTip(x.estCost, x.costMiss) + '\n' + T('Not counted in the Claude 5h/7d limits');
  return '<span class=sk title="'+esc(tip)+'">'+fmtTok(x.tok)+' tok</span>';
}
// Branch and worktree chips after the project name on the identity row.
function sessBranchHtml(x){
  // ★The branch is also a handle that opens the diff (2026-08-26). The git badge is 11x15px and
  //   hard to hit precisely — a larger second handle makes it usable.
  return (x.branch
    ? ' <span class="sb hit" data-diff="'+esc(x.cwd||'')+'" title="'+esc(x.branch+' · '+(x.git ? T('↑unpushed ~dirty ')+x.git+' · ' : '')+T("Click to view this session's changes (diff)"))+'">'
      + '<span class=sbt>'+esc(x.branch)+'</span>'+(x.git ? '<span class=sbg>'+esc(x.git)+'</span>' : '')+'</span>'
    : '')
    + ((x.wt && x.wt.main) ? ' <span class=swt data-wtj="'+esc(x.wt.root)+'" data-wtc="'+esc(x.cwd||'')+'" title="'
        + esc(T("Show this worktree's work unit in the Branches tab")+' · '+x.wt.root)+'">worktree: '+esc(x.wt.name)+'</span>' : '');
}
// Pipeline chip: open run «name · stage» · declared [pl-none] «No pipeline · cat» · undeclared edit «Undeclared».
function sessPlChip(x){
  const runs = (x.plrun || []).filter(r => r && r.name), r = runs.find(r => !r.end), n = x.plNone;
  // ⚠Only the name ellipsizes: the stage is the part worth reading, so it sits in its own non-shrinking span.
  if(r) return '<span class="spl splr" title="'+esc(T('Pipeline run')+': '+r.name+(r.cur ? ' · '+r.cur : ''))+'"><span class="splnm">'+esc(r.name)+'</span>'
    + (r.cur ? '<span class="splst"> · '+esc(r.cur)+'</span>' : '')+'</span>';
  // ⚠An ended run still outranks plNone: a nudge written before the run must not read «Undeclared» afterwards.
  if(runs.length) return '<span class="spl spln" title="'+esc(T('Pipeline run')+': '+runs[0].name+' · '+T('done'))+'">'+esc(runs[0].name)+'</span>';
  // ⚠cat is an English key from an allow-list — shown as-is, never passed through T().
  if(n && n.cat) return '<span class="spl spln" title="'+esc(T('Declared no pipeline for this work')+': '+n.cat)+'">'+esc(T('No pipeline')+' · '+n.cat)+'</span>';
  if(n && n.u) return '<span class="spl splu" title="'+esc(T('Edited files without declaring a pipeline or [pl-none]'))+'">'+esc(T('Undeclared'))+'</span>';
  return '';
}
// Identity row: pick box · dot · platform logo · project · branch · badges.
function sessIdRow(x){
  // ⚠A rollout row (x.rollout) has no hook events behind it — its tooltip must not claim they are the source.
  const pl = aiLogo(x.plat, x.rollout ? T(" session — read from its CLI's record file (hooks not connected)")
    : x.plat && x.plat !== 'cc' ? T(' session — drawn from events its CLI hooks send (the transcript is not read)') : T(' session'));
  const nohk = x.rollout ? '<span class="sz snohk" title="'+esc(T("State read from Codex's record file; set up hooks — docs/HOOKS.md"))+'">'
    + esc(T('Hooks not connected'))+'</span>' : '';
  return '<div class=sx>'+sessPickHtml(x)+'<span class=sd></span>'+pl+'<span class=sp title="'+esc(x.project)+'">'+esc(x.project)+'</span>'+sessBranchHtml(x)+acctChip(x, 'sacb')
    + nohk + sessBadges(x) + sessPlChip(x) + '</div>';
}
// Current-task line under the state row ('' when there is nothing to show).
function sessTaskHtml(x){
  // ⚠Metadata only (AGENTS.md rule 1, enforced 2026-09-25): the server sends `targ` only as a running Agent call's
  //   one-line description — no reply summary, human instruction or Bash command reaches this line any more.
  const run0 = (x.state==='tool'||x.state==='think');
  const doing = run0 ? plStrip(x.targ||'') : '';   // display only: drop a leading [pl:…] tag
  return doing ? '<div class=sq title="'+esc(doing + NL + NL + T('— Doing now'))+'">'+esc(doing)+'</div>' : '';
}
// State row: label · tool · elapsed · burn chip · dismiss handle.
function sessStateRow(x, st){
  // ⚠Waiting with a watcher shown: the last tool is stale and read as the watcher's name, so it is dropped.
  const ms = monSuffix(x, st);
  const tool = ms ? '' : (x.tool ? esc(x.tool) : '—');
  // ★What is **running now** — tool calls with no result yet. A session can look «Response done» while
  //   a subagent is actually running, so that is attached next to the state row.
  //   Per this file's no-emoji rule it is written as text, and what is running goes verbatim in the tooltip.
  // ★Split by meaning (no wrapping — it adds height).
  //   «Mailbox watch» = an on/off **attribute** ⇒ first row with git and model (the identity row).
  //   subagents · commands = **progress** happening now ⇒ on the state row. Mixed in one place, neither reads.
  const nsub = (x.sub||[]).length, nbg = (x.bgs||[]).length;
  // ★★Declarations come **before use**. This block was originally below and `lost` was referenced above, so
  //   `node --check` passed but **it blew up at runtime with TDZ** — the session panel didn't draw at all
  //   (2026-08-19: the whole Claude session panel disappeared). A parse check can't catch this.
  // Past 30 min it is not called «Waiting» — if the completion notice is lost, finished items linger,
  //   and calling that 'normal progress' is false. Running or dead is unknown, so it says **«No response»** and leaves cleanup to the human.
  // ★★If the transcript hasn't grown for 10+ min it is not called «Thinking» — **it is unknown.**
  //   Measured 2026-08-19: a bot session printed a response in the terminal ("push done 44b5bb2..f20a639") but that line
  //   was never written to the transcript (the session also showed `Auto-update failed`). A file-only verdict
  //   sees only "the human spoke last" and shows «Thinking» forever.
  // ★No assertion (measured 2026-08-19): seeing «105m» it was taken as "notice lost, probably dead", but
  //   a check showed **it really was running in the background.** The screen was right; the interpretation was wrong.
  //   ⇒ No words that read as dead, like «No response». Show **only the time**; the human judges.
  const mute = (st === 'tool' || st === 'think') && x.ageSec >= 600;
  const MUTETIP = TV({msg: 'In this state for {n} min. ', vars: {n: Math.floor(x.ageSec/60)}})
    + T('It may be a long job or it may be stuck — background work has been seen running in cases like this, so neither is assumed (check that terminal).');
  const RM = x.runmin || {};
  const kind = nsub ? 'sub' : (nbg ? 'bg' : '');
  const rm = kind ? (RM[kind] || 0) : 0;              // ★only the longest elapsed of that kind is used
  // ★Count and elapsed removed from the label (2026-08-25) — the tree below shows each item's name and elapsed, so
  //   repeating them here says the same thing twice and lengthens the row until it wraps.
  //   The label says only **what it is waiting for**.
  const waitOn = waitOnLabel(x, st);
  const lost = rm >= 30;
  // ★The count chip was replaced by the tree — the same info twice overflows the row (2026-08-19, wrapping).
  //   Sub-items each get their own row in stree below.
  // Old items **can be dismissed by click** (not removed by guess)
  const drop = (lost && x.cwd) ? ' <span class=sdrop data-drop="'+esc(x.cwd)+'" title="'+esc(T("Clears this session's subagent and command list — they may really still be running (measured), so check first"))+'">✕</span>' : '';
  // ★«Response done» while an agent is running is false — the label is swapped.
  //   The state value (`state`) itself is untouched. Sorting, filters and cards use it, so swapping only the display is safe.
  //   «Awaiting answer» (ask) is more urgent, so it is not overridden.
  return '<div class=sx2><span class="sl'+(x.blocked?' sblk':'')+(waitOn?' swait':'')+(mute?' smute':'')+'" title="'
    + esc(x.blocked ? T(BLKTIP) : (mute ? MUTETIP : (waitOn ? T(WAITTIP) : T(TIP[st]||''))))+'">'
    + esc(sessLabel(x))+'</span>'+(ms ? ' <span class=smon>'+esc(ms)+'</span>' : '')+' '+(tool ? tool+' · ' : '· ')
    + sessAgoHtml(x, st)
    + sessBurn(x)
    + drop+'</div>';
}
// Elapsed time on the state row, colored when tool/thinking has run 5+ min.
function sessAgoHtml(x, st){
  // ★Tool/thinking over 5 min colors the elapsed time — that spot may be **stuck** (measured 2026-08-19:
  //   a bot session received a user post and its transcript stayed 0 bytes for 12 min. The verdict was honest but unnoticed).
  //   No extra text, only color on the existing «N min ago» — a 5-min tool is normal, so no assertion.
  return (st==='tool'||st==='think') && x.ageSec>=300 ? '<span class=sslow title="'+TV({msg: 'No new transcript line for {n} min in this state — may be a long job or may be stuck (cannot tell from outside)', vars: {n: Math.floor(x.ageSec/60)}})+'">'+AGO(ago(x.ageSec))+'</span>' : AGO(ago(x.ageSec));
}
// Agent/command/watch tree under the card ('' when empty).
function sessTreeHtml(x){
  // ★**Show all**. Folding to 5 was tried and
  //   reverted — how many are running is this panel's purpose, and folding hides that answer.
  //   If height runs short the panel scrolls (#sess already has overflow-y:auto).
  const treeIn = sessTeamHtml(x.team) + sessWfHtml(x.wf) + sessKid(T('Subagents'),'a',sessNest(x.sub))
               + sessKid(T('Command'),'b',sessByIdle(x.bgs)) + sessKid(T('Monitors'),'m',x.mon)
               + sessGmKids(x.gms);
  return treeIn ? '<div class=stree>'+treeIn+'</div>' : '';
}
// Invite pick box (checkbox, dimmed dot, or '' for finished sessions).
function sessPickHtml(x){
  // ★Only sessions whose identity is explicit in the path can be picked. Inviting by an id picked up from a folder name etc.
  //   calls the wrong session — same spot as the measured incident (2026-08-12).
  //   Logged-in rule is mboxIn (17): identity.json or a cx launcher id; the server re-checks it in _room_invite.
  const pickable = x.state !== 'done' && mboxIn(x);
  return pickable
    // ⚠label pads the 13px box to a ~21x27 hit area (right/vertical only: .sx clips overflow); a miss used to fall through to the row's open-log click
    ? '<label class=spickw><input type=checkbox class=spick data-mb="'+esc(x.mbox)+'"'+(picked.has(x.mbox)?' checked':'')
      + ' title="'+esc(TV({msg: 'Pick {n} to invite to a room', vars: {n: x.mbox}}))+'"></label>'
    : (x.state !== 'done' ? '<span class=spick title="'+esc(T('Cannot invite — identity not confirmed')
        + (x.mbox ? TV({msg: ' (guess: {n} · source {m})', vars: {n: x.mbox, m: x.mboxSrc}}) : '')
        + T(' — run `/room as <id>` in that session to register it'))+'" style="opacity:.3">·</span>' : '');
}
// Card tooltip (raw text; caller escapes) — permission mode line only when known.
function sessCardTip(x){
  return (x.cwd||'')+' · '+x.id+(x.model?' · '+x.model:'')+(x.pmode ? NL+T('Permission: ')+x.pmode : '');
}
// One session card (identity row · state row · current task · agent/command/watch tree).
function sessRowHtml(x){
  const cls = (x.ageSec<90 && x.state !== 'gone' ? 'run' : '') + (cpFlash && cpFlash === cpKey(x) ? ' cphit' : '');   // ⚠`warm` was dropped — no CSS applies to it. `run` is used by `.sxw.run .sp`
  const at = acctTip(x), tip = esc(sessCardTip(x) + (at ? NL + at : ''));
  const st = x.state || 'unknown';
  const idl = isIdle(x, markMin()) ? ' idlelong' : '';
  const ac = acctRowCls(x);   // '' with <2 accounts
  // ★`data-ssid` first — several sessions share a cwd (`:8782`), so finding by cwd goes to the first row
  return '<div class="sxw s-'+esc(st)+' '+cls+idl+(ac ? ' '+ac : '')+'" data-ssid="'+esc(x.sid||'')+'" data-scwd="'+esc(x.cwd||'')+'" title="'+tip+'">'
    + sessIdRow(x) + sessStateRow(x, st) + sessTaskHtml(x) + sessTreeHtml(x)
    + '</div>';
}
// Context-per-request / burn chip on the state row ('' without creq).
function sessBurn(x){
  if(!x.creq) return '';
  const bb = burnBand(x.burn);
  const tip = TV({msg: 'Context per request {n} tokens', vars: {n: x.creq.toLocaleString()}})
    + (x.burn ? TV({msg: '\nBurn {n} tokens/min ({m} requests/min)', vars: {n: x.burn.toLocaleString(), m: x.rpm}}) : '')
    + (bb ? TV({msg: '\n{r}× the sustainable pace {p}/min (5h limit ÷ 300 min) — {l}', vars: {r: bb.ratio.toFixed(2), p: bb.pace.toLocaleString(), l: bb.lab}}) : '')
    + T('\n\n97.9% of the cost is cache reads — so these two numbers are the bill.')
    + T('\nWith a large context per request, starting a new session is cheaper (compaction only kicks in at 1M).')
    + T('\nBased on the recent tail, not the whole-session average.');
  const c = bb ? bb.col : '#6f7889';
  return '<span class=sbn style="color:'+c+';border-color:'+c+'55" title="'+esc(tip)+'">'
    + fmtTok(x.creq)+'/req' + (x.burn ? ' · '+fmtTok(x.burn)+T('/min') : '') + '</span>';
}
// ★Subtree — agents, background commands and watchers, one row each. Server-provided labels as-is
//   (`subagent_type: description · Nm` / `command or description` / `watch summary`). **Output content is not shown** —
//   this page is a shared screen and other sessions' output belongs to that session's user (metadata principle above).
// Elapsed is always shown per item — colored past 30 min (may be stuck; not asserted).
// ★Agents spawned by an agent attach **below it** (sub-sub-agents were otherwise missing
//   or shown wrongly). It used to be a flat list with a `↳2` tag, so
//   when the parent wasn't listed an orphan row looked like a direct child of the session. Lineage is meta's parentAgentId.
function sessNest(list){
  const arr = (list||[]).slice();
  const byId = new Map(arr.filter(v => v.aid).map(v => [v.aid, v]));
  const kids = new Map(), roots = [];
  for(const v of arr){
    const p = v.par ? byId.get(v.par) : null;
    if(p && p !== v){ if(!kids.has(p)) kids.set(p, []); kids.get(p).push(v); }
    else roots.push(v);
  }
  const out = [], seen = new Set();
  const walk = (l, d) => {
    // moving ones (short quiet time) on top — the same rule inside the tree
    l.sort((a, b) => ((typeof a.idle === 'number' ? a.idle : 1e9)
                    - (typeof b.idle === 'number' ? b.idle : 1e9)));
    l.forEach((v, i) => {
      if(seen.has(v)) return;             // guard against lineage forming a cycle
      seen.add(v);
      v._lv = d; v._br = (i === l.length - 1) ? '└' : '├';
      out.push(v);
      const c = kids.get(v);
      if(c) walk(c, d + 1);
    });
  };
  walk(roots, 0);
  return out;
}
// Platform display name — the product's own name in both languages (gm -> «Gemini», never its Korean transliteration).
function platName(k){ const n = AILG[k] ? AILG[k][0] : String(k || ''); return n.replace(/\s*\(.*\)$/, ''); }
// Search text for a platform: display name + Korean aliases, lowercased. ⚠platName is Latin-only, so without
// the aliases a Korean-script search for Gemini stopped finding Gemini sessions. New platform = one line here.
function platHay(k){
  const ko = {
    cc: '클로드',
    gm: '제미나이',
    cx: '코덱스',
  };
  return [platName(k), AILG[k] ? AILG[k][0] : '', ko[k] || ''].join(' ').toLowerCase();
}
// One tree group per child platform, each under its own logo.
function sessGmKids(list){
  return [...new Set((list || []).map(g => g && g.plat).filter(Boolean))]
    .map(p => sessKid(aiLogo(p), 'g', sessGms(list.filter(g => g && g.plat === p)))).join('');
}
// Child CLI runs this session launched (`gemini -p`, `codex exec`, ...) — metadata only; label = server `cmd` (CHILD_LABEL).
function sessGms(list){
  return (list||[]).filter(g => g && !g.done).reverse().map(g => {   // live runs only — finished ones stay on the timeline
    const d = Math.max(0, g.dur || 0);
    const st = g.done ? T('Done') : (g.run ? T('running', 'exec') : T('idle'));
    return {lab: [g.cmd || platName(g.plat), g.model || '', ago(d),
                  g.tok ? fmtTok(g.tok) + ' ' + T('Tokens') : '', st].filter(Boolean).join(' · ')};
  });
}
// ★Workflow-tool runs (2026-09-26): agents under subagents/workflows/ were invisible. One collapsible node per run —
//   «Workflow sidereus-change ▰▰▱▱ 1/4 · Implement · 4m · 11M tokens», children = journal labels. Metadata only.
const wfFold = new Set();   // run ids the user collapsed (the list re-renders every poll, so <details> state lives here)
// «Expand all / Collapse all» over every team/workflow group: expand forgets every collapse, collapse pins each id shut.
function wfFoldAll(ids, open){
  if(open) wfFold.clear(); else (ids || []).forEach(i => wfFold.add(i));
  return wfFold.size;
}
// The pair above the list, only when some shown card has a team or workflow group (same .relfx look as the branch/git trees).
function wfFoldBtns(rows){
  if(!(rows || []).some(x => x && (x.team || (x.wf || []).length))) return '';
  return '<div class=swfall>' + [['1', 'Expand all'], ['0', 'Collapse all']]
    .map(t => '<button type=button class="relfx swfa" data-wfa=' + t[0] + '>' + esc(T(t[1])) + '</button>').join('') + '</div>';
}
function wfBar(done, total){
  const n = Math.max(1, Math.min(8, total || 1)), k = total ? Math.round(done / total * n) : 0;
  return '<i class=wfbar>' + '▰'.repeat(k) + '▱'.repeat(n - k) + '</i>';
}
// Run summary as badges, same shape as its child rows: «[Workflow] name [1/4] [phase] [4m] [11M]».
function wfLine(w, sec, tok){
  const m = Math.max(0, Math.round((sec || 0) / 60));
  return '<span class=v>' + esc(w.name || String(w.id || '').slice(0, 11)) + '</span>'
    + '<span class=e>' + (w.done || 0) + '/' + (w.total || 0) + '</span>'
    + [w.phase || '', m < 1 ? T('just now') : U(m, 'm'), tok ? fmtTok(tok) : '',
       w.fail ? U(w.fail, '#msgs') + ' ' + T('failed') : ''].filter(Boolean)
      .map(s => '<span class=e>' + esc(s) + '</span>').join('');
}
function sessWfHtml(list){
  const ST = {done: T('Done'), fail: T('failed'), cut: T('cut off')};
  return (list || []).slice().reverse().map(r => {
    const now = Date.now() / 1000, sec = (r.run ? now : r.end) - r.start;
    const kids = (r.agents || []).map((a, i, arr) => {
      const m = Math.max(0, Math.round(((a.st === 'run' ? now : a.end) - a.start) / 60));
      const hit = /^a[0-9a-f]{6,40}$/.test(String(a.aid || '')) ? ' agh" data-tid="' + esc(a.aid) + '" title="' + esc(T('Click to see what this subagent did')) : '';   // no toolUseId: the agent id opens its log (server matches wf_* files)
      return '<div class="sti wfa' + (a.st === 'run' ? ' on' : '') + hit + '"><i class=stbr>' + (i === arr.length - 1 ? '└' : '├') + '─</i>'
        + '<span class=v title="' + esc(plStrip(a.lab) + (a.phase ? ' · ' + a.phase : '')) + '">' + esc(plStrip(a.lab) || a.aid) + '</span>'
        + (typeof wfBadge === 'function' ? wfBadge(r.name, a.phase) : '')   // type badge (48g)
        + (a.phase ? '<span class=e>' + esc(a.phase) + '</span>' : '')
        + '<span class=e>' + (ST[a.st] ? esc(ST[a.st]) : (m < 1 ? T('just now') : U(m, 'm'))) + '</span>'
        + (a.tok ? '<span class=e>' + fmtTok(a.tok) + '</span>' : '') + '</div>';
    }).join('');
    return '<details class="swf' + (r.run ? ' on' : '') + '" data-wf="' + esc(r.id) + '"' + (wfFold.has(r.id) ? '' : ' open') + '>'
      + '<summary class=sti title="' + esc(T('Workflow run — finished agents / launched agents · current phase · elapsed · tokens')) + '">'
      + '<span class="k w">' + esc(T('Workflow')) + '</span>' + wfLine(r, sec, r.tok) + '</summary>'
      + kids + '</details>';
  }).join('');
}
// ★Agent team the session leads (2026-09-26): «Team · N members · tasks done/total», members = name · state · current task
//   subject · unread count. ⚠Task descriptions and inbox message text never reach the page (server sends counts/subjects).
function sessTeamHtml(t){
  if(!t) return '';
  const ST = {run: T('working'), idle: T('idle'), done: T('Done')};
  const tc = t.tasks || {};
  const head = esc(T('members ') + (t.members || []).length + ' · ' + T('tasks ')) + wfBar(t.done, t.total)
    + ' <b class=wfn>' + (t.done || 0) + '/' + (t.total || 0) + '</b>'
    + esc(' · ' + T('pending ') + (tc.pending || 0) + ' · ' + T('in progress ') + (tc.in_progress || 0));
  const kids = (t.members || []).map((m, i, arr) =>
    '<div class="sti wfa' + (m.st === 'run' ? ' on' : '') + '"><i class=stbr>' + (i === arr.length - 1 ? '└' : '├') + '─</i>'
    + '<span class=v title="' + esc(m.name + (m.tsub ? ' · ' + m.tsub : '')) + '">' + esc(m.name) + (m.tsub ? ' <i class=tmt>' + esc(m.tsub) + '</i>' : '') + '</span>'
    + '<span class=e>' + esc(ST[m.st] || m.st || '') + '</span>'
    + (m.unread ? '<span class="e tmu" title="' + esc(TV({msg: '{n} unread messages', vars: {n: m.unread}})) + '">'
        + esc(T('unread ') + m.unread) + '</span>' : '') + '</div>').join('');
  return '<details class="swf' + (t.run ? ' on' : '') + '" data-wf="team"' + (wfFold.has('team') ? '' : ' open') + '>'
    + '<summary class=sti title="' + esc(T('Agent team — members · tasks done/total · tasks by status')) + '">'
    + '<span class="k w">' + esc(T('Team')) + '</span><span class=v>' + head + '</span></summary>' + kids + '</details>';
}
// Server agent label is «type: description» (bgtasks_parse `_bg_on_launch`). The default types carry no information
// and ate the width at 900/1100, so they go to the tooltip only; other types become a small chip.
const SUB_PLAIN_TY = ['general-purpose', 'agent'];
function subLab(lab){
  const s = plStrip(String(lab == null ? '' : lab)), i = s.indexOf(': ');
  if(i <= 0 || /\s/.test(s.slice(0, i))) return {ty: '', desc: s};
  const ty = s.slice(0, i), desc = s.slice(i + 2);
  return {ty: SUB_PLAIN_TY.includes(ty) ? '' : ty, desc: desc || ty};
}
// Tree rows for one kind (agent 'a' · command 'b' · watch 'm').
// Server row label -> shown text; the watcher label (sidereus/live.py «Mailbox watch[ · id]») is translated, the id suffix kept.
function sessKidLab(s){
  const m = /^Mailbox watch( · .*)?$/.exec(s);
  // ⚠Other labels are agent/command descriptions (user data) — never through T().
  return m ? T('Mailbox watch') + (m[1] || '') : s;
}
function sessKid(kind, cls2, items){
  return (items||[]).map(v => {
    const raw = (v && v.lab != null) ? String(v.lab) : String(v), lab = cls2 === 'm' ? monLab(sessKidLab(raw)) : sessKidLab(raw);
    const sl = cls2 === 'a' ? subLab(lab) : {ty: '', desc: lab};
    const m = (v && typeof v.min === 'number') ? v.min : null;
    // ★`src=proc` is **real uptime measured from the process** (see server comment). Watchers are quiet normally, so
    //   the 30-min color (`late`) and the "completion notice may have been missed" tooltip are **not attached** — this used to paint normal as suspicious.
    //   `src=beat` (legacy heartbeat) items keep their display as-is.
    const prc = !!(v && v.src === 'proc');
    const late = m !== null && m >= 30 && !prc;
    const el = m === null ? '' : '<span class="e'+(late?' late':'')+'" title="'
      + esc(TV({msg: prc ? 'Up for {n} min (the watcher process is alive — being quiet is normal)'
                         : late ? '{n} min in — may be a long job or a missed completion notice (cannot tell from outside)' : '{n} min in', vars: {n: m}}))+'">'+(m<1?T('just now'):U(m,'m'))+'</span>';
    // ★The **tool that agent is running now** — a fact from its own transcript (not an estimate).
    //   Tool name and target are split; the target is a command/path, so **monospace (code)** (2026-08-27).
    // if the parent is in this list, show as **a branch** (dedup tags); otherwise keep the depth tag
    const br2 = (v && v._lv > 0)
      ? '<i class=stbr title="'+esc((v.par ? T('Spawned by the subagent above') : '')+T(' (depth ')+(v.depth||v._lv+1)+')')+'">'
        + '　'.repeat(v._lv - 1) + (v._br || '├') + '─</i>' : '';
    const dep = (v && v.depth > 1 && !(v._lv > 0))
      ? '<span class=dp2 title="'+esc(TV({msg: 'Subagent spawned by a subagent (depth {n}) — the parent is not in the list', vars: {n: v.depth}}))+'">↳'+v.depth+'</span>' : '';
    let sub2 = '';
    if(v && v.now){
      const i = String(v.now).indexOf(' · ');
      const tool = i < 0 ? String(v.now) : String(v.now).slice(0, i);
      const targ = i < 0 ? '' : String(v.now).slice(i + 3);
      // Inline on the agent row so every row stays one line (QA 2026-09-27: «Bash» wrapped onto its own line)
      sub2 = '<span class=tn>'+esc(tool)+'</span>'
        + (targ ? '<code class=tg title="'+esc(targ)+'">'+esc(targ)+'</code>' : '');
    }
    // ★With a tid (= subagent), click to view that agent's footsteps in a modal (2026-08-27)
    const hit = (v && v.tid) ? ' agh" data-tid="'+esc(subWorkId(v))+'" title="'+esc(T('Click to see what this subagent did')) : '';
    // ★Shows **how long it has been quiet** (2026-08-28: actually 2 but 4 on screen).
    //   No completion signal exists on disk — finished and running have the same last event (assistant),
    //   and notices get lost. So **no assertion**: show the silence and allow dismissing by click.
    //   ⚠Silence is not read as death: it stays quiet for 12 min at a time while generating a large document (measured).
    const idl = (v && typeof v.idle === 'number') ? v.idle : -1;
    const cold = idl >= 300;                       // quiet for 5+ min — likely finished (not asserted)
    const qz = idl >= 60
      ? '<span class="stq'+(cold?' stqc':'')+'" title="'
        + esc(TV({msg: '{n} min since the last record — it may be done or still writing a long reply (cannot tell from outside)', vars: {n: Math.floor(idl/60)}}))
        + '">'+T('quiet ')+ago(idl)+'</span>' : '';
    const xdrop = (v && v.tid)
      ? '<span class=stx data-adrop="'+esc(v.tid)+'" title="'+esc(T('Removes it from the list (does not stop the subagent)'))+'">✕</span>' : '';
    return '<div class="stiw'+hit+(cold?' stcold':'')+'"><div class=sti>'+br2
      + '<span class="k '+cls2+'">'+kind+'</span>'
      + (sl.ty ? '<span class=sty title="'+esc(sl.ty)+'">'+esc(sl.ty)+'</span>' : '')
      + '<span class=v title="'+esc(plStrip(lab))+'">'+esc(sl.desc)+'</span>'+sub2+dep+el+qz+xdrop+'</div></div>';
  }).join('');
}
// ★**What moves now goes on top** (2026-09-02). Uses the same value (idle) as «quiet Nm» —
//   writing 'quiet 12 min' on screen and putting that at the top would make the two displays contradict each other.
function sessByIdle(a2){
  return (a2||[]).slice().sort((p, q) =>
    ((typeof p.idle === 'number' ? p.idle : 1e9) - (typeof q.idle === 'number' ? q.idle : 1e9)));
}
// Delegated click handler for #sess (bound once per buildSessions; rows carry data-* targets).
function sessClick(e){
  // ⚠The click is under the mouse, so hover deferral would hold the expansion until mouseleave — lift it.
  if(acctOthClick(e, () => { sessHover = false; sessDirty = false; buildSessions(); })) return;
  // ★Checkboxes are intercepted first — so they don't collide with the delegation below
  const cb = e.target.closest && e.target.closest('input.spick[data-mb]');
  if(cb){
    e.stopPropagation();
    const mb = cb.getAttribute('data-mb');
    if(cb.checked) picked.add(mb); else picked.delete(mb);
    buildInvite();
    return;
  }
  const wfa = e.target.closest && e.target.closest('[data-wfa]');
  if(wfa){
    e.stopPropagation();
    const box = document.getElementById('sess');
    wfFoldAll([...box.querySelectorAll('.swf[data-wf]')].map(d => d.getAttribute('data-wf')), wfa.getAttribute('data-wfa') === '1');
    // ⚠clear _sh: a native toggle changed the DOM without the cached string, so an identical new string would skip the morph
    sessHover = false; sessDirty = false; box._sh = ''; buildSessions();
    return;
  }
  const wfs = e.target.closest && e.target.closest('.swf > summary');
  if(wfs){ const id = wfs.parentElement.getAttribute('data-wf'); if(wfFold.has(id)) wfFold.delete(id); else wfFold.add(id); return; }
  if(e.target && e.target.tagName === 'SUMMARY' && e.target.closest('.agp')){
    agPromptOpen = !e.target.closest('.agp').hasAttribute('open');   // the opposite of the state right before the toggle
    return;
  }
  const ag = e.target.closest && e.target.closest('.agh[data-tid]');
  if(ag){
    e.stopPropagation();
    const rowEl = ag.closest('.sxw');
    const o = agRowOpen(rowEl, ag.getAttribute('data-tid'));   // (35b) empty cwd: openAgent draws the server's refusal, not a silent skip
    openAgent(o.cwd, o.tid);
    return;
  }
  // dismiss just one agent from the list (recorded in the server's _bg_dropped — it won't come back)
  const ad = e.target.closest && e.target.closest('.stx[data-adrop]');
  if(ad){
    e.stopPropagation();
    postJSON('/api/bg/dismiss', {tid: ad.getAttribute('data-adrop')})
      .catch(() => note(T('Could not clear — check the server')))
      .finally(() => { const r0 = ad.closest('.stiw'); if(r0) r0.remove(); });
    return;
  }
  const wr = e.target.closest && e.target.closest('.swr[data-wreck]');
  if(wr){ e.stopPropagation(); loadDiff(wr.getAttribute('data-wreck')); return; }   // same action as the fwreck alert's diff button
  const wj = e.target.closest && e.target.closest('.swt[data-wtj]');
  if(wj){ e.stopPropagation(); brWuJump(wj.getAttribute('data-wtj'), wj.getAttribute('data-wtc')); return; }
  const gb = e.target.closest && e.target.closest('.hit[data-diff]');
  if(gb){
    e.stopPropagation();
    const cwd = gb.getAttribute('data-diff');
    // ★Clicking the same badge again doesn't close — closing the window is that window's ✕ or the OS's job.
    //   window.open with the same window name brings that window forward instead of opening a new one.
    loadDiff(cwd);
    return;
  }
  const dp = e.target.closest && e.target.closest('.sdrop[data-drop]');
  if(dp){
    e.stopPropagation();
    const cwd = dp.getAttribute('data-drop');
    postJSON('/api/bg/dismiss', {cwd: cwd})
      .then(j => { note(TV({msg: 'Cleared: {n}', vars: {n: j.removed}})); poll(); })
      .catch(() => note(T('Could not clear — check the server')));
    return;
  }
  const rz = e.target.closest && e.target.closest('.srz[data-rz]');
  if(rz){                                     // ↻ chip — copies the resume command
    e.stopPropagation();
    const cmd = rz.getAttribute('data-rz');
    copyText(cmd).then(ok => note(ok ? T('Copied: ')+cmd : T('Copy failed — ')+cmd));
    return;
  }
  // ★Row click → path copy was removed (2026-08-27). Once badges, branch and checkbox all became click
  //   targets, the clipboard changing on a click in empty space went against intent.
  //   If the path is needed, the diff modal header shows the full path.
  // A click on the card's header area opens its work log (replaces the removed «Log» badge).
  //   Skipped while text is selected, and inside the agent list / details, which have their own targets.
  const hd = e.target.closest && e.target.closest('.sxw > .sx, .sxw > .sx2, .sxw > .sq');
  if(hd && !(e.target.closest('a,input,label,button,summary,details'))){   // label: pick box padding (forwards its click to the input)
    const sel = window.getSelection && String(window.getSelection());
    const cwd = hd.closest('.sxw').getAttribute('data-scwd'), ssid = hd.closest('.sxw').getAttribute('data-ssid');
    const et = extTid((SESS||[]).find(x => ssid && x.sid === ssid));
    if(et && !sel){ e.stopPropagation(); openSession(cwd, et); }
    else if(cwd && !sel){ e.stopPropagation(); openSession(cwd, ssid ? 'sess:' + cwd + '|' + ssid : undefined); }   // ⚠without the sid the server opens the cwd's newest session
  }
}
// Clipboard — 127.0.0.1 is a secure context, so `navigator.clipboard` works. If it fails, fall back to the old method.
function copyText(t){
  if(navigator.clipboard && navigator.clipboard.writeText)
    return navigator.clipboard.writeText(t).then(()=>true, ()=>fallbackCopy(t));
  return Promise.resolve(fallbackCopy(t));
}
// ⚠Focus the textarea before select(): with focus inside the header drawer, execCommand copied nothing. Restore focus after.
function fallbackCopy(t){
  const prev=document.activeElement;
  try{
    const ta=document.createElement('textarea');
    ta.value=t; ta.readOnly=true; ta.style.position='fixed'; ta.style.top='-1000px';
    document.body.appendChild(ta); ta.focus(); ta.select();
    const ok=document.execCommand('copy'); ta.remove(); return ok;
  }catch(e){ return false; }
  finally{ try{ if(prev && prev.focus) prev.focus(); }catch(e){ softErr('copy-refocus', e); } }
}
// POSIX single-quote: ' -> '\'' so spaces, quotes, $ and ` in a path stay literal. Shared by attention «Copy resume command» and «Recently ended sessions».
function shq(s){ return "'" + String(s).replace(/'/g, "'\\''") + "'"; }
function resumeCmd(cwd, sid, acctDir){
  if(!/^[0-9a-fA-F][0-9a-fA-F-]{7,63}$/.test(sid || '')) return '';
  return (cwd ? 'cd ' + shq(cwd) + ' && ' : '') + (acctDir ? 'CLAUDE_CONFIG_DIR=' + shq(acctDir) + ' ' : '') + 'claude --resume ' + sid;
}
// Account band (state accts, >=2 accounts): row key acct, absent = primary (.acc0 teal); others get one of 6 hues.
function acctList(){ return typeof ACCTS !== 'undefined' && Array.isArray(ACCTS) && ACCTS.length >= 2 ? ACCTS : null; }
// «Main account» view setting (UIS mbMainAcct): a non-primary label still in ACCTS, else '' (primary stays main).
// ⚠Display, the status-bar saver verdict (state.saverViews) and projections (BURNM via burnFor) follow it; the server primary and token figures stay on the primary; the modal burndown follows burnUse() (55b).
function mainAcct(){ let v = ''; try{ v = String(UIS.getItem('mbMainAcct') || ''); }catch(e){ return ''; } return mainAcctOk(v); }
function mainAcctOk(v){
  const list = acctList(); if(!list) return '';
  return v && list.some(a => a && !a.primary && String(a.label || '') === v) ? v : '';
}
function acctHash(s){ let h = 0; for(const c of String(s)) h = (h * 31 + c.codePointAt(0)) >>> 0; return h; }
// Hue = label hash with linear probing over labels sorted, so a label keeps its colour in every list and order.
// With a main account set, main gets .acc0 and the primary's label takes main's place in the hue pool.
function acctCls(label){
  const list = acctList(); if(!list) return '';
  const m = mainAcct(), p = m ? list.find(a => a && a.primary) : null;
  if(m ? label === m : !label) return 'acb acc0';
  if(m && !label) label = String((p && p.label) || '');
  const used = new Set(); let mine = 0;
  list.filter(a => a && (m ? String(a.label || '') !== m : !a.primary)).map(a => String(a.label || '')).sort().forEach(l => {
    let h = acctHash(l) % 6;
    for(let i = 0; i < 6 && used.has(h); i++) h = (h + 1) % 6;
    used.add(h); if(l === label) mine = h + 1;
  });
  return 'acb acc' + (mine || acctHash(label) % 6 + 1);
}
// Row class: external CLI rows (plat other than cc) are not Claude accounts, so no band.
function acctRowCls(x){ return !x || (x.plat && x.plat !== 'cc') ? '' : acctCls(x.acct); }
// Per-view account pick (UIS mbAcctPick.<view>): '' = All accounts; a label not in ACCTS or <2 accounts reads as ''.
// ⚠View-only filter: never writes mbMainAcct. Sessions, Attention, Recent and the drawer counts share the 'sess' pick.
function acctPick(view){
  const list = acctList(); if(!list) return '';
  const k = 'mbAcctPick.' + view; let v = lsGet(k, null);
  // One-time migration of the old «Only main account» toggle (sess only — no other view ever followed it).
  if(v === null && view === 'sess' && lsGet('mbOnlyMain', null) === '1'){
    const p = list.find(a => a && a.primary); v = mainAcct() || String((p && p.label) || '');
    if(lsSet(k, v)) lsDel('mbOnlyMain');
  }
  v = String(v || '');
  return v && list.some(a => a && String(a.label || '') === v) ? v : '';
}
// External CLI rows and unknown sessions are not Claude accounts, so they always stay. Row acct '' = primary (acctLabel).
// pick = acctPick(view) read once by the caller for a whole list (undefined = read here).
function acctInPick(x, view, pick){
  const p = pick === undefined ? acctPick(view) : pick; if(!p) return true;
  const l = acctLabel(x); return !l || l === p;
}
// Picker select ('' with <2 accounts). ⚠Labels are user data: esc() only, never T().
function acctPickHtml(view){
  const list = acctList(); if(!list) return '';
  const cur = acctPick(view), o = (v, t) => '<option value="' + esc(v) + '"' + (v === cur ? ' selected' : '') + '>' + esc(t) + '</option>';
  return '<select class=acpk id="acpk-' + esc(view) + '" title="' + esc(T('Show one account in this view only')) + '">' + o('', T('All accounts'))
    + list.filter(a => a && a.label).map(a => o(String(a.label), String(a.label))).join('') + '</select>';
}
// Id of the focused picker, or '' — read before a repaint that replaces it.
function acctPickFocusId(){ const ae = document.activeElement; return ae && ae.classList && ae.classList.contains('acpk') ? ae.id : ''; }
// ⚠Lists repaint every 2.5 s and drop a focused select to <body>; pass fo = acctPickFocusId() from before the repaint to refocus.
function acctPickWire(view, redraw, fo){
  const el = document.getElementById('acpk-' + view); if(!el) return;
  el.onchange = () => {
    if(el.value) lsSet('mbAcctPick.' + view, el.value); else lsDel('mbAcctPick.' + view);
    (view === 'sess' ? ['sess', 'srec', 'attn'] : [view]).forEach(k => delete ACC_OTH[k]);   // a new pick starts folded
    redraw();
  };
  if(fo && fo === el.id && document.activeElement !== el) try{ el.focus(); }catch(e){ softErr('acpk-focus', e); }
}
const ACC_OTH = {};   // per-list expansion (sess · srec · attn), memory only: resets on reload
// Collapsed line: count only (metadata rule: no labels); hot = a hidden row carries a badge.
function acctOthHtml(key, n, hot){
  return n ? '<div class=acoth data-ao="' + key + '">' + (hot ? '<i class=acothd></i>' : '') + esc(T('In other accounts: {n}').replace('{n}', n)) + '</div>' : '';
}
function acctOthClick(e, redraw){
  const t = e && e.target && e.target.closest && e.target.closest('[data-ao]');
  if(!t) return false;
  ACC_OTH[t.getAttribute('data-ao')] = 1; redraw(); return true;
}
// Visible account label for a row ('' with <2 accounts or an external CLI row); acct '' = primary's label.
function acctLabel(x){
  const list = acctList(); if(!list || !x || (x.plat && x.plat !== 'cc')) return '';
  if(x.acct) return String(x.acct);
  const p = list.find(a => a && a.primary); return String((p && p.label) || '');
}
// Label chip in the band colour (inherits --acc from the row's .accN); cls = list-specific chip class.
// ⚠Shows acctShort (labels can share a prefix, so an ellipsised cut could not tell accounts apart); full text in title.
function acctChip(x, cls){ const l = acctLabel(x); return l ? '<span class="' + cls + '" title="' + esc(acctTip(x)) + '">' + esc(acctShort(l)) + '</span>' : ''; }
// Shortest prefix (>=4 chars) of label l that no other account label starts with; whole l if none.
function acctShort(l){
  const o = (acctList() || []).map(a => String((a && a.label) || '')).filter(v => v && v !== l);
  for(let n = 4; n < l.length; n++){ const p = l.slice(0, n); if(!o.some(v => v.startsWith(p))) return p; }
  return l;
}
// Band tooltip ('' with <2 accounts or an external CLI row); raw text, caller escapes.
function acctTip(x){
  const list = acctList(); if(!list || !x || (x.plat && x.plat !== 'cc')) return '';
  if(x && x.acct) return x.acctDir ? TV({msg: 'Claude account {n} — config dir {d}', vars: {n: x.acct, d: x.acctDir}}) : TV({msg: 'Claude account {n}', vars: {n: x.acct}});
  const p = list.find(a => a && a.primary);
  if(p && p.dir) return TV({msg: 'Claude account {n} — config dir {d}', vars: {n: p.label || '—', d: p.dir}});
  return TV({msg: 'Claude account {n}', vars: {n: (p && p.label) || '—'}});
}
// Text-only short toast — the card toast (`toast`) is tied to bell history; using it for notices like this pollutes that history.
function note(msg){
  const box=document.getElementById('toasts');
  if(!box) return;
  const el=document.createElement('div');
  el.className='toast tnote'; el.textContent=msg;
  el.onclick=()=>el.remove();
  box.appendChild(el);
  setTimeout(()=>{ el.classList.add('out'); setTimeout(()=>el.remove(), 320); }, 2600);
}

