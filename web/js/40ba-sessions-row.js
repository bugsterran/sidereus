// Session identity row (split from 40b-sessions-list.js): lead cell + chip groups, group fit, chip builders.
// R1/R2: identity-row groups get box-wide widths so each group starts at the same x on every row; R3: drop levels
// (box .sxd1..3, 60-sessions.css) hide size · cost/tokens · model only when that makes every row fit one line;
// otherwise nothing hides and whole groups wrap.
// ⚠Errors, diff, leftovers, context, pipeline, to-do and ↻ never hide; the name only ellipsizes.
const SX_DROP = ['sz', 'sk', 'sm'];
function sessFit(box){
  // ⚠Refit on width change only: a group wrap changes the box height and would loop the observer.
  if(!box._sxro && window.ResizeObserver){ box._sxro = new ResizeObserver(() => { if(box.clientWidth !== box._sxw) sessFit(box); }); box._sxro.observe(box); }
  box._sxw = box.clientWidth;
  box.classList.remove('sxd1', 'sxd2', 'sxd3');
  for(const v of ['--sxlead', '--sxidw', '--sxusw']) box.style.removeProperty(v);
  const rows = [...box.querySelectorAll('.sx')].filter(r => r.clientWidth);
  if(!rows.length) return;
  // A glued tail (.sxtl: «To-do n» / actions moved into usage or identity) is not part of that group's column width.
  // ⚠Subpixel widths: offsetWidth rounds 225.4 to 225, so the pinned group got 1px short and its last chip wrapped.
  const bw = e => e.getBoundingClientRect().width;
  const nat = e => { const t = e.querySelector(':scope > .sxtl'); return bw(e) - (t ? bw(t) + 6 : 0); };
  const mx = sel => rows.reduce((m, r) => { const e = r.querySelector(sel); return e ? Math.max(m, nat(e)) : m; }, 0);
  const px = (v, n) => box.style.setProperty(v, Math.ceil(n) + 1 + 'px');   // +1px slack over the rounded-up width
  px('--sxlead', mx('.sxl'));
  const gw = rows[0].querySelector('.sxgs').clientWidth;
  // ⚠The 45% cap never goes below a row's identity with its name at the 96px floor (.sp min-width): nowrap would clip chips.
  const need = rows.reduce((m, r) => { const id = r.querySelector('.sxid'), sp = id && id.querySelector('.sp');
    if(!id) return m; const s = sp ? Math.max(bw(sp), sp.scrollWidth || 0) : 0; return Math.max(m, nat(id) - (s - Math.min(s, 96))); }, 0);
  px('--sxidw', Math.min(mx('.sxid'), Math.max(gw * 0.45, need)));
  const fits = () => rows.every(r => { const id = r.querySelector('.sxid'), t = id ? id.offsetTop : null;
    // ⚠Line test, not equal tops: baseline-aligned groups with mixed font sizes sit at different offsetTop on one line.
    return [...r.querySelectorAll('.sxg')].every(g => t === null || !g.firstChild || g.offsetTop < t + id.offsetHeight); });
  const level = lv => {
    box.classList.remove('sxd1', 'sxd2', 'sxd3');
    for(let i = 1; i <= lv; i++) box.classList.add('sxd' + i);   // cumulative: level n hides the first n of SX_DROP
    box.style.removeProperty('--sxusw');
    px('--sxusw', mx('.sxus'));
    return fits();
  };
  let lv = 0;
  while(!level(lv) && lv < SX_DROP.length) lv++;
  // ⚠Hide chips only when it buys one line: if level 3 still wraps, show everything and let groups wrap.
  if(lv && !fits()) level(0);
}
// Identity group tail: git chip (diff) for a row without a branch — with a branch, the branch chip opens the diff.
function sessGitChip(x){
  // ★Clicking the badge expands that session's diff (otherwise what subagents edited is hard to skim).
  //   Even with clean git there may be untracked files, so it is clickable whenever there is a cwd.
  const gitOpen = false;   // ★the main view has no diff — open state is unknowable (it is a separate window)
  // With a branch, the branch chip carries the git state and opens the diff (sessBranchHtml) — two chips opening
  // the same window read as two different actions and cost the width the branch name needed at 900.
  return x.cwd && !x.branch
    ? '<span class="sg hit'+(gitOpen?' on':'')+'" data-diff="'+esc(x.cwd)+'" title="'
      + esc((x.git ? T('↑unpushed ~dirty · ') : '')
        + (extTid(x) ? T('View changes (diff) in this folder — by folder, not by session') : T("Click to view this session's changes (diff)")))+'">'
      + (x.git ? esc(x.git)+' ' : '') + (extTid(x) ? esc(T('Folder diff')) : 'diff') + '</span>'
    : '';
}
// Usage group: context · size · cost (or external-CLI tokens) · model.
function sessUsage(x){
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
  return ctx + size + cost + extTokChip(x) + model;
}
// Work group: error · leftovers · pipeline chip (sessIdRow appends «To-do n», 40c).
function sessWorkBadges(x){
  const errb = x.err ? '<span class=se title="'+esc(T('The last tool result was an error'))+'">!</span>' : '';
  // ★Leftovers — number of **files touched by dead agents and left uncommitted** under this session path. Not drawn at 0.
  //   ⚠A clue, not proof (same as the `wreckage` comment) — so it only says "left over".
  const wrk = (x.wreck > 0)
    ? '<span class=swr data-wreck="'+esc(x.cwd)+'" title="'+esc(TV({msg: '{n} files touched by an interrupted subagent are still uncommitted — you decide whether to finish or revert. Click to open the diff', vars: {n: x.wreck}}))
      +'">'+T('Leftover ')+x.wreck+'</span>' : '';
  return errb + wrk + sessPlChip(x);
}
// Action group: resume copy · terminal jump.
function sessActs(x){
  // ★Copy `claude --resume` — the server had the full session id but sent it cut to 8 chars, so
  //   **there was no way to resume a finished session.** This chip copies that resume command.
  //   ⚠Do not drop `plat==='cc'` - external CLI sessions would get a command they don't understand.
  // an extra Claude root resumes under its own config dir (resumeCmd adds CLAUDE_CONFIG_DIR)
  const rzc = x.acctDir ? resumeCmd(x.cwd, x.sid, x.acctDir) : 'cd '+x.cwd+' && claude --resume '+x.sid;
  const rs = (x.sid && x.sid.length > 8 && x.cwd && (!x.plat || x.plat === 'cc'))
    ? '<span class=srz data-rz="'+esc(rzc)+'" title="'+T('Copy: ')+esc(rzc)+'">↻</span>' : '';
  return rs + termBtnHtml(x, 'sx');   // switch-to-terminal chip (88d-term.js)
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
// Identity row: lead (pick box · dot · logo) + groups [identity][usage][work][actions] (R1); an empty action group is omitted.
function sessIdRow(x){
  // ⚠A rollout row (x.rollout) has no hook events behind it — its tooltip must not claim they are the source.
  const pl = aiLogo(x.plat, x.rollout ? T(" session — read from its CLI's record file (hooks not connected)")
    : x.plat && x.plat !== 'cc' ? T(' session — drawn from events its CLI hooks send (the transcript is not read)') : T(' session'));
  const nohk = x.rollout ? '<span class="sz snohk" title="'+esc(TV({msg: "State read from {name}'s record file; set up hooks — docs/HOOKS.md", vars: {name: platName(x.plat)}}))+'">'
    + esc(T('Hooks not connected'))+'</span>' : '';
  const g = c => h => '<span class="sxg '+c+'">'+h+'</span>';
  const td = typeof stodoChip === 'function' ? stodoChip(x) : '';   // 40c; guarded: tests load this file alone
  let id = '<span class=sp title="'+esc(x.project)+'">'+esc(x.project)+'</span>'+sessBranchHtml(x)+acctChip(x, 'sacb')+nohk+sessGitChip(x);
  let us = sessUsage(x), wk = sessWorkBadges(x);
  const ac = sessActs(x), acg = ac ? g('sxac')(ac) : '';
  // ⚠R3: «To-do n» and the action group never wrap alone — they are glued to the end of the last non-empty group
  //   (nested in .sxwk, else wrapped in .sxtl inside usage or identity).
  if(wk) wk += td + acg;
  else if(td || acg){ const tl = '<span class=sxtl>' + td + acg + '</span>'; if(us) us += tl; else id += tl; }
  // ⚠R2: .sxus/.sxwk are always emitted (empty = placeholder) so a later group keeps its x.
  return '<div class=sx><span class=sxl>'+sessPickHtml(x)+'<span class=sd></span>'+pl+'</span><div class=sxgs>'
    + g('sxid')(id) + g('sxus')(us) + g('sxwk')(wk) + '</div></div>';
}
