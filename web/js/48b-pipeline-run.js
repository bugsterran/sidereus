// «Pipelines» «Run» + live lighting (docs/dev/PIPELINE.md steps 2–3). Extends 48-pipeline.js.
// «Run» = DM preview a person confirms (relay via /api/dm, nothing auto-sent); lighting reads SESS[].wf rows only
// (agents.wf_runs allow-list: phase/label/state/times) — ⚠never wf_<id>.json (rule 1).
const PL_MEM_MS = 2 * 3600 * 1000;           // DM'd pipeline name per session, kept 2 h (PIPELINE.md Known limits)
const PL_RETRY_RE = / retry \d+$/;           // runner label for a retry launch (pipeline.js withRetry)
let PLRUN = null;                            // open run panel {name, sid, req, models:{title: model}, busy}
function plMem(){
  const m = lsJson('sidereus.plrun', {}), now = Date.now(), out = {};
  Object.keys(m || {}).forEach(k => { if(m[k] && now - m[k].at < PL_MEM_MS) out[k] = m[k]; });
  return out;
}
// Pipeline name of one Workflow run: the runner's load agent label «load <name>», else the name DM'd to that session.
function plRunName(run, mem, sid){
  if(!run || run.name !== 'pipeline') return '';
  const ld = (run.agents || []).find(a => a.phase === '불러오기' &&   /* ⚠phase name written by the runner, not UI text */ /^load [a-z0-9-]{1,40}$/.test(a.lab || ''));
  if(ld) return ld.lab.slice(5);
  return (mem && mem[sid] && mem[sid].name) || '';
}
// {title: {st: run|done|fail|wait, n, sec, retry}} for one run; phase title == stage title (runner meta.phases).
function plLight(stages, run){
  const out = {}, ph = plgSlots(stages);   // custom titles run under "custom stage N" phases (48c plgSlots)
  (stages || []).forEach(s => {
    const ags = ((run && run.agents) || []).filter(a => a.phase === ph[s.title]);
    if(!ags.length){ out[s.title] = { st: 'wait', n: 0, sec: 0, retry: 0 }; return; }
    const live = run.run && ags.some(a => a.st === 'run');
    const last = ags[ags.length - 1];
    const st = live ? 'run' : (last.st === 'fail' || last.st === 'cut') ? 'fail' : 'done';
    const t0 = Math.min(...ags.map(a => a.start || 0)), t1 = Math.max(...ags.map(a => a.end || 0));
    out[s.title] = { st, n: ags.length, sec: Math.max(0, t1 - t0), retry: ags.filter(a => PL_RETRY_RE.test(a.lab || '')).length };
  });
  return out;
}
// Sessions of `proj`: cwd matches first, then sessions whose repos include it (⚠a cart-origin session edits cart-api),
// or whose tagged pipeline lives only in `proj` (plAway: launched from another folder).
function plProjSess(proj){
  const mem = plMem(), kn = plKnown();
  const s = (SESS || []).filter(x => x && (x.cwd === proj || (x.repos || []).includes(proj)
    || (kn && Object.values(plAway(x, plTagNames(x, mem), kn).home).includes(proj))));
  return s.filter(x => x.cwd === proj).concat(s.filter(x => x.cwd !== proj));
}
// Latest run of pipeline `name` among sessions of `proj` -> {sid, run, lt?, pr?} | null.
// Workflow runner rows (x.wf) light through plLight; otherwise the server's merged model x.plrun (sidereus/pl_runs.pl_model).
// ⚠Render only: a stage absent from plrun is «wait» — never stitch stages client-side again (traps/pipeline.md «Client-side run stitching drifted from the hook record»).
//   One exception: a live-tagged session with no run record lights only its tagged stage (traps/pipeline.md «A running pipeline row drew another session's abandoned run»).
function plLiveRun(proj, name){
  const mem = plMem(), kn = plKnown(), ss = plProjSess(proj).filter(x => !kn || x.cwd === proj || plHomes(x, name, kn).includes(proj)
    || Object.values(plAway(x, plTagNames(x, mem), kn).home).includes(proj));
  let best = null;
  [ss.filter(x => x.cwd === proj), ss.filter(x => x.cwd !== proj)].forEach(grp => { if(!best) grp.forEach(x => {
    (x.wf || []).forEach(r => {
      if(plRunName(r, mem, x.sid) !== name) return;
      if(!best || (r.run && !best.run.run) || (r.run === best.run.run && r.end > best.run.end)) best = { sid: x.sid, run: r };
    });
  }); });
  if(best) return best;
  // ⚠While a session carries a live [pl:name/] tag, only that session's plrun counts: another session's abandoned run
  //   of the same pipeline was drawn under the tagged row. No plrun there = the tagged stage alone (others wait).
  // ⚠A session whose recorded run of `name` belongs to another project is not tagged here: its tags made a stand-in run
  //   (every untagged stage «wait») on this project's same-named pipeline.
  const away = x => ((x && x.plrun) || []).some(r => r && r.name === name && r.proj && r.proj !== proj);
  // Ordering only: the session picked in the «Working now» list (48j PLS.nowSid) ranks first at equal liveness.
  const me = s => !!PLS.nowSid && s === PLS.nowSid;
  const tg = ss.filter(x => !away(x)).map(x => ({ x, t: plSubsOf(x).map(a => plDescStage(a && a.lab)).filter(d => d && d.name === name).map(d => d.title) })).filter(o => o.t.length)
    .sort((p, q) => me(q.x.sid) - me(p.x.sid));
  let pr = null, sid = '';
  (tg.length ? tg.map(o => o.x) : (SESS || [])).forEach(x => ((x && x.plrun) || []).forEach(r => {   // no proj recorded: the session must belong to `proj`
    if(!r || r.name !== name || !(r.proj ? r.proj === proj : ss.includes(x))) return;
    const on = plPrLive(r);
    if(!pr || (on && !plPrLive(pr)) || (on === plPrLive(pr) && (me(x.sid) !== me(sid) ? me(x.sid) : (r.t1 || 0) > (pr.t1 || 0)))){ pr = r; sid = x.sid; }
  }));
  if(!pr && tg.length){
    const t = Date.now() / 1000, S = {};
    tg[0].t.forEach(k => { S[k] = { o: 'run', n: 1, t0: t, t1: t }; });
    pr = { name, proj, sid: tg[0].x.sid, cur: tg[0].t[0], end: 0, t0: t, t1: t, stages: S }; sid = tg[0].x.sid;
  }
  if(!pr) return null;
  const p = ((PLS.data[proj] || {}).pipelines || []).find(q => q.name === name);
  return plPrLv(sid, pr, (p && p.stages) || [], Date.now());
}
// Run the canvas shows: an earlier run of the live session picked in the head menu (PLS.runSel {sid, name, rid, cur}, memory only), else plLiveRun.
// ⚠The pick drops itself once the live session or its current rid changes — an old run must never cover a newly started one.
function plViewRun(proj, name){
  const lv = plLiveRun(proj, name), s = PLS.runSel;
  if(!s) return lv;
  const nav = plRunNav(lv), i = nav && s.name === name && s.sid === nav.sid && s.cur === nav.cur ? nav.past.findIndex(q => q.rid === s.rid) : -1;
  if(i < 0){ PLS.runSel = null; return lv; }
  const q = nav.past[i], p = ((PLS.data[proj] || {}).pipelines || []).find(x => x.name === name);
  const v = plPrLv(lv.sid, Object.assign({}, q, { name, proj }), (p && p.stages) || [], Date.now());
  v.nav = Object.assign({}, nav, { k: nav.N - 1 - i, rid: q.rid, end: q.end || q.t1 || 0 });
  return v;
}
// Run picker data of a plrun-based lv: {sid, name, cur, t0, lab, past (newest first, ≤5), N, k, rid}; null without earlier runs (= today's head).
function plRunNav(lv){
  if(lv && lv.nav) return lv.nav;
  const pr = lv && lv.pr, ps = pr && pr.rid != null && Array.isArray(pr.past) ? pr.past.filter(q => q && q.rid != null && q.rid !== pr.rid).slice(0, 5) : [];
  return ps.length ? { sid: lv.sid, name: pr.name, cur: pr.rid, t0: pr.t0 || 0, lab: String(pr.lab || ''), past: ps, N: ps.length + 1, k: ps.length + 1, rid: pr.rid } : null;
}
function plRunLab(k, t0, lab){ return TV({msg: 'Run {k}', vars: {k}}) + (t0 ? ' · ' + hhmm(t0) : '') + (lab ? ' · ' + String(lab) : ''); }   // lab is session data: esc() only, never T()
// «Run k/N ▾» in the live head (+ «Back to current» while an earlier run is shown); the menu is a fixed overlay (never shifts the canvas).
function plRunPick(nav){
  if(!nav) return '';
  const old = nav.rid !== nav.cur, lab = TV({msg: 'Run {k}/{n}', vars: {k: nav.k, n: nav.N}}) + (old && nav.end ? ' · ' + TV({msg: 'ended {t}', vars: {t: hhmm(nav.end)}}) : '');
  return '<button class="plrv' + (old ? ' old' : '') + '" data-plrv aria-haspopup=menu>' + esc(lab + ' ▾') + '</button>'
    + (old ? '<button class=plrv data-plrvb>' + esc(T('Back to current')) + '</button>' : '');
}
let PLRV = false;   // run menu open
function plRvClose(){ const el = document.getElementById('plrvm'); if(el) el.remove(); PLRV = false; }
function plRvOpen(rc){
  const p = plCur(), nav = plRunNav(p && plViewRun(PLS.proj, p.name));
  plRvClose();
  if(!nav) return;
  const it = (rid, k, t0, lab, cur) => '<button class=plapki data-plrvi="' + esc(String(rid)) + '" aria-checked=' + (rid === nav.rid) + ' role=menuitemradio><span>'
    + esc(plRunLab(k, t0, lab)) + '</span>' + (cur ? '<i>' + esc(T('current', 'run')) + '</i>' : '') + '</button>';
  const el = document.createElement('div');
  el.id = 'plrvm'; el.className = 'plapk plrvm'; el.setAttribute('role', 'menu');
  el.innerHTML = it(nav.cur, nav.N, nav.t0, nav.lab, true) + nav.past.map((q, i) => it(q.rid, nav.N - 1 - i, q.t0, q.lab, false)).join('');
  el.style.left = Math.max(4, Math.min(rc.left, window.innerWidth - 304)) + 'px'; el.style.top = Math.round(rc.bottom + 4) + 'px';   // fixed: never scrolls the view
  document.body.appendChild(el); PLRV = true;
}
function plRvPick(v){
  const p = plCur(), nav = plRunNav(p && plViewRun(PLS.proj, p.name)), q = nav && nav.past.find(x => String(x.rid) === v);
  PLS.runSel = q ? { sid: nav.sid, name: p.name, rid: q.rid, cur: nav.cur } : null;
  plRvClose(); plPaint();
}
document.addEventListener('pointerdown', e => { if(PLRV && !(e.target.closest && e.target.closest('#plrvm,[data-plrv]'))) plRvClose(); }, true);
document.addEventListener('click', e => {
  const t = e.target.closest ? e.target : null;
  if(!t) return;
  if(t.closest('[data-plrvb]')){ PLS.runSel = null; plRvClose(); plPaint(); return; }
  const b = t.closest('[data-plrv]');
  if(b){ if(PLRV) plRvClose(); else plRvOpen(b.getBoundingClientRect()); return; }
  const m = PLRV && t.closest('[data-plrvi]');
  if(m) plRvPick(m.dataset.plrvi);
});
document.addEventListener('keydown', e => { if(PLRV && e.key === 'Escape') plRvClose(); });
const PL_OS = ['run', 'done', 'skip', 'fail', 'back', 'hold'];   // plrun stage outcomes; anything else renders as wait (it lands in a class name)
function plPrLive(r){ const S = (r && r.stages) || {}; return Object.keys(S).some(t => S[t] && S[t].o === 'run'); }
// One-line label of a plrun agent; the orchestrator mark {aid:'main'} reads «main: » (plLabDesc → «orchestrator»).
function plAgLab(a){ return a && a.aid === 'main' ? 'main: ' : String((a && (a.lab || a.aid)) || ''); }
// plrun row -> lt {title: {st, n, sec, retry, from, ag, labs}} for the file's stages; `now` in ms.
function plPrLt(pr, stages, now){
  const out = {}, S = (pr && pr.stages) || {}, ss = stages || [], t0 = t => (S[t] && PL_OS.includes(S[t].o) ? S[t].p0 || S[t].t0 || 0 : -1);   // S keys = current titles (pl_runs maps renamed ones)
  // Unrecorded onlyOnJump stage behind the latest-started stage, or right after it in an ended run, was not needed (the hook writes no st).
  // ⚠An ended run that stopped earlier (regular stages still unrun in between) keeps it waiting like those stages.
  const li = ss.reduce((m, s, i) => (t0(plTk(s.title)) >= 0 && (m < 0 || t0(plTk(s.title)) >= t0(plTk(ss[m].title))) ? i : m), -1);
  ss.forEach((s, i) => {
    const v = S[plTk(s.title)];
    if(!v || !PL_OS.includes(v.o)){
      const nn = !!s.onlyOnJump && li >= 0 && (li > i || (!!(pr && pr.end) && ss.slice(li + 1, i).every(x => x.onlyOnJump)));
      out[s.title] = { st: nn ? 'skip' : 'wait', nn, why: nn ? T('not needed') : '', n: 0, sec: 0, retry: 0, from: {}, ag: [], labs: [] }; return;
    }
    const ag = Array.isArray(v.ag) ? v.ag : [], run = v.o === 'run';
    const end = run ? now / 1000 : v.t1 || v.t0 || 0;   // ⚠sec = latest pass (p0); tot = since the first start (t0)
    out[s.title] = { st: v.o, why: plWhy(v), main: !!v.main, n: ag.length || v.n || 0, sec: Math.max(0, Math.round(end - (v.p0 || v.t0 || 0))),
      tot: Math.max(0, Math.round(end - (v.t0 || 0))), k: v.k || 1, p0: v.p0 || 0, retry: 0, w0: v.t0 || 0, w1: end,   // w0..w1 = stage window (s) for matching gate evidence
      from: v.from || {}, via: typeof v.via === 'string' ? v.via : '', ag, labs: plAgLabs(ag), ps: plPsOk(v.ps),
      cm: Array.isArray(v.cm) ? v.cm.filter(c => typeof c === 'number').slice(-4) : [] };   // commit times (s) in this stage
  });
  return out;
}
function plAgLabs(ag){ return ag.slice().sort((a, b) => (b.run - a.run) || ((b.t0 || 0) - (a.t0 || 0))).map(a => ({ lab: plAgLab(a), run: !!a.run })); }
// Closed earlier passes (pl_flow st[t].ps, oldest first, ≤6); an entry lands in a class name, so the outcome must be known.
function plPsOk(ps){
  return Array.isArray(ps) ? ps.filter(p => p && typeof p.a === 'number' && typeof p.b === 'number' && PL_OS.includes(p.s)).slice(-6) : [];
}
// Earlier pass i of a lit stage as an lt overlay: its outcome, window and the agents started inside it (±5s).
// ⚠pass number = k - ps.length + i: ps keeps only the last 6, so ps[0] is not always pass 1.
function plPass(L, i){
  const ps = (L && L.ps) || [], p = ps[i];
  if(!p) return null;
  const ag = (L.ag || []).filter(a => a && (a.t0 || 0) >= p.a - 5 && (a.t0 || 0) <= p.b + 5), cap = (ps[i + 1] || {}).a || L.p0 || 0;
  const cm = (L.cm || []).filter(c => c >= p.a - 5 && (!cap || c < cap));
  return { st: p.s, w0: p.a, w1: p.b, p0: p.a, k: Math.max(1, (L.k || 1) - ps.length + i), ag, n: ag.length, labs: plAgLabs(ag), cm,
    sec: Math.max(0, Math.round(p.b - p.a)), tot: Math.max(0, Math.round(p.b - (L.w0 || p.a))), why: '', via: '', cap };   // cap = next pass start (plEvLine)
}
function plPrLv(sid, pr, stages, now){
  const S = pr.stages || {}, ts = Object.keys(S), runT = ts.filter(t => S[t] && S[t].o === 'run'), ids = new Set();
  ts.forEach(t => ((S[t] && S[t].ag) || []).forEach(a => ids.add(a.aid || a.tid)));
  return { sid, pr, lt: plPrLt(pr, stages, now), run: { run: runT.length > 0, phase: runT.join(', '), fail: ts.filter(t => S[t].o === 'fail').length,
    total: ids.size || ts.reduce((a, t) => a + ((S[t] && S[t].n) || 0), 0), start: pr.t0 || 0, end: runT.length ? 0 : (pr.end || pr.t1 || 0) } };
}
// Direct-mode tag. ⚠The label is "<agentType>: <description ≤40 chars>" — keep pipeline names short so the prefix survives.
const PL_DESC_RE = /\[pl:([a-z0-9-]{1,40})\/([^\]\n]{1,80})\]/;
function plDescStage(lab){ const m = PL_DESC_RE.exec(lab || ''); return m ? { name: m[1], title: plTk(m[2]) } : null; }
// Builtin agent types: never «missing». Stage agent not installed (project/user agents from /api/pipelines) ⇒ the session runs it as general-purpose.
const PL_PICK_BUILTIN = ['general-purpose', 'Explore', 'Plan', 'claude-code-guide', 'statusline-setup'];
const PL_BUILTIN_AG = new Set(['', 'claude', 'main', 'general-purpose', 'Explore', 'Plan', 'claude-code-guide', 'statusline-setup']);   // ⚠literal: tests lift this line alone
function plAgMissing(name, agents){
  return !!name && !PL_BUILTIN_AG.has(name) && !(agents || []).some(a => (a && a.name != null ? a.name : a) === name);
}
// Stage agent/skill picker: the selected project's own entries (scope project + global `<folder>-*`, as pipeline._role_agents) + builtins;
// cur outside those stays first, out = true; grp = own | bi | out (optgroups). ⚠items keeps user-scope entries: plAgMissing/plDmMissing need them.
function plFolder(p){ return String(p || '').replace(/[\\/]+$/, '').split(/[\\/]/).pop().replace(/^\.+/, '').toLowerCase(); }
// Stem = folder name before its first '-' (shop-api → shop): sibling repos share global `<stem>-*` agents/skills.
function plStem(p){ return plFolder(p).split('-')[0]; }
function plOwnName(n, proj){ const b = plFolder(proj), st = plStem(proj); n = String(n); return !!b && (n.startsWith(b + '-') || (!!st && n.startsWith(st + '-'))); }
function plPickScoped(items, cur, proj, builtins){
  const own = (items || []).filter(a => a && (a.scope === 'project' || plOwnName(a.name, proj))).map(a => a.name);
  const L = [...new Set(own)].map(name => ({ name, out: false, grp: 'own' }));
  (builtins || []).forEach(name => { if(!L.some(a => a.name === name)) L.push({ name, out: false, grp: 'bi' }); });
  if(cur && !L.some(a => a.name === cur)) L.unshift({ name: cur, out: true, grp: 'out' });
  return L;
}
function plPickAgents(agents, cur, proj){ return plPickScoped(agents, cur, proj, PL_PICK_BUILTIN); }
// Skills: own + `<folder|stem>-*`, then user-scope skills without another known project's `<folder|stem>-` prefix as the generic group.
function plPickSkills(skills, cur, proj, projs){
  const st = plStem(proj), other = [...new Set((projs || []).filter(q => plStem(q) && plStem(q) !== st).flatMap(q => [plFolder(q), plStem(q)]))];
  const gen = (skills || []).filter(k => k && k.scope === 'user' && !other.some(f => String(k.name).startsWith(f + '-'))).map(k => k.name);
  return plPickScoped(skills, cur, proj, gen);
}
function plDmMissing(p, agents){
  if(!agents) return '';
  const m = [...new Set(p.stages.map(s => s.agent).filter(a => plAgMissing(a, agents)))];
  return m.length ? '\nMissing agents → run as general-purpose with the same task: ' + m.join(', ') : '';
}
// x.sub + the main agent's own [pl:] stage (server agents.plm_of: name/title/age only) as one extra live sub with a stable id.
function plSubsOf(x){
  const m = x && x.plm, s = (x && x.sub) || [];
  return m && m.name && m.title ? s.concat([{ lab: 'main: [pl:' + m.name + '/' + m.title + ']', aid: 'main:' + x.sid }]) : s;
}
function plLabType(lab){ const l = lab || '', i = l.indexOf(': '); return i > 0 ? l.slice(0, i).trim() : ''; }
// «Session runs it directly» DM (cheaper than the Workflow runner): the session runs the stages
// itself with the Agent tool; loop-backs and retries continue the same agent with SendMessage instead of spawning a new one.
function plDmDirect(p, req, models, dt){
  const ovr = models || {}, used = p.stages.map(s => s.title);
  const steps = p.stages.map((s, i) => (i + 1) + '. ' + s.title + ' — agent ' + s.agent + ' · model ' + (ovr[s.title] || s.model || p.defaults.model) + (s.skill ? ' · skill ' + s.skill : '')
    + (s.retry != null ? ' · retry ' + s.retry : '') + (s.gate ? ' · gate `' + s.gate + '`' : '') + (s.parallel ? ' · parallel ' + s.parallel : '')
    + (s.produces ? ' · produces slices' : '') + (s.fanout ? ' · fanout slices' : '') + (s.onlyOnJump ? ' · only after a loop-back' : '')
    + (s.onFail ? ' · onFail → ' + s.onFail.goto + ' (max ' + s.onFail.max + (s.onFail.then ? ', then ' + s.onFail.then : '') + ')' : '')).join('\n');
  const defs = used.filter(t => dt && dt[t]).map(t => t + ': ' + dt[t]).join('\n');
  // ⚠hooks/pl_flow.py denies a stage Agent whose model differs from the file unless a Bash description declared the override first.
  const mo = used.filter(t => ovr[t]).map(t => '[pl-model:' + p.name + '/' + t + '=' + ovr[t] + ']');
  const mtag = mo.length ? 'Model overrides for this run — before the first stage run one Bash (`true`) per line, description = the line:\n' + mo.join('\n') + '\n' : '';
  // «» bounds the request: it may itself contain ' or " (e.g. "isn't").
  // ⚠The run request is mailbox text the session reads (wire format), so its Korean head line stays as is.
  return '파이프라인 ' + p.name + ' 실행 (세션 직접) — 요청: «' + req + '»\n'
    + 'Run .claude/pipelines/' + p.name + '.json yourself with the Agent tool (not the Workflow tool). Stages in order:\n' + steps + '\n'
    + mtag + 'Each stage: Agent(subagent_type = its agent, model unless inherit, description starting with "[pl:' + p.name + '/<stage title>]" — Sidereus lights stages from it), '
    + 'prompt = the default instruction for the title + the stage "task" + the pipeline "rules" + this request + earlier stage summaries and changed files'
    + (p.stages.some(s => s.skill) ? ' + for a stage with a skill: "Follow the <skill> skill." (load it with the Skill tool first)' : '') + '. '
    + 'Each stage returns status PASS/FAIL, summary, findings (file/line/text), changed files.\n'
    + 'onFail: continue the goto stage\'s existing agent with SendMessage (attach the findings) instead of a new Agent, then rerun the failing stage the same way — at most max times; after it passes go to "then" if set. '
    + 'retry: SendMessage to the same agent. parallel / fanout: several Agent calls in one message.\n'
    + 'Report each stage in ≤10 lines. Never restart or commit unless the rules say so.\n'
    + 'Default instructions (also .claude/pipelines/_defaults.json in the Sidereus repo):\n' + (defs || '(custom stages only — use their task)');
}
// Codex recipient: no Agent tool / SendMessage / Workflow, so one session runs every stage and lights it with shell markers
// (same wording as hooks/pipelines_brief.py _RUN_CODEX; pl_mark.py --platform codex). ⚠Model overrides do not apply there.
function plDmCodex(p, req, models, dt){
  const used = p.stages.map(s => s.title);
  const steps = p.stages.map((s, i) => (i + 1) + '. ' + s.title + (s.skill ? ' · skill ' + s.skill : '') + (s.gate ? ' · gate `' + s.gate + '`' : '')
    + (s.onFail ? ' · onFail → ' + s.onFail.goto + ' (max ' + s.onFail.max + (s.onFail.then ? ', then ' + s.onFail.then : '') + ')' : '')).join('\n');
  const defs = used.filter(t => dt && dt[t]).map(t => t + ': ' + dt[t]).join('\n');
  return '파이프라인 ' + p.name + ' 실행 (세션 직접) — 요청: «' + req + '»\n'
    + 'Run .claude/pipelines/' + p.name + '.json yourself in this session, doing each stage\'s task in order (stage agent/model are Claude settings; a stage skill means follow that skill). Stages in order:\n' + steps + '\n'
    + 'Start each stage with a shell command echo "[pl:' + p.name + '/<stage title>]" and end it with echo "[pl-end:' + p.name + '/<stage title>]" ("|fail" before "]" when its gate failed); echo "[pl:-]" clears.\n'
    + 'At each stage start re-read only the files the previous stage wrote; do not rely on earlier stage context.\n'   // ⚠one Codex context holds every stage
    + 'Each stage: the default instruction for the title + the stage "task" + the pipeline "rules" + this request + earlier stage results. Each stage ends with status PASS/FAIL, summary, findings (file/line/text), changed files.\n'
    + 'onFail: redo the goto stage with the findings, then rerun the failing stage — at most max times; after it passes go to "then" if set.\n'
    + 'Run all stages back to back in this turn: do not end the turn or report between stages; report once after the last stage (≤10 lines per stage). Never restart or commit unless the rules say so.\n'   // ⚠Codex ended its turn after each stage
    + 'Default instructions (also .claude/pipelines/_defaults.json in the Sidereus repo):\n' + (defs || '(custom stages only — use their task)');
}
function plModeOf(name){ return lsGet('sidereus.plmode.' + name, 'direct') === 'wf' ? 'wf' : 'direct'; }
function plDmFor(p, req, models, cx){   // cx = Codex recipient: ignores PLRUN.mode
  const d = PLS.data[PLS.proj] || {};
  return (cx ? plDmCodex(p, req, models, d.default_tasks || {}) : PLRUN && PLRUN.mode === 'wf' ? plDmText(p, req, models) : plDmDirect(p, req, models, d.default_tasks || {})) + (cx ? '' : plDmMissing(p, d.agents));   // Codex runs no agents
}
// DM body: one-line request + how to run it (Workflow runner args) + stage summary with the effective model.
function plDmText(p, req, models){
  const ovr = {};
  Object.keys(models || {}).forEach(t => { if(models[t]) ovr[t] = models[t]; });
  const args = Object.assign({ pipeline: p.name, request: req }, Object.keys(ovr).length ? { models: ovr } : {});
  const steps = p.stages.map(s => s.title + '(' + s.agent + '·' + (ovr[s.title] || s.model || p.defaults.model) + ')').join('→');
  return '파이프라인 ' + p.name + ' 실행 — 요청: «' + req + '»\n'
    + 'Workflow 도구로 실행: scriptPath .claude/workflows/pipeline.js · args ' + JSON.stringify(args) + '\n'
    + '단계: ' + steps;
}
// Live sessions of the project (metadata only: sid, model, state, mailbox login, project, running Agent one-line description).
function plSessions(proj){
  return plProjSess(proj).filter(x => x.state !== 'done' && (!x.plat || x.plat === 'cc' || x.plat === 'cx'))
    .map(x => ({ sid: x.sid, model: x.model || '', cx: x.plat === 'cx', state: x.state || '', id: x.mbox || '', login: mboxIn(x),
      project: x.project || '', doing: ['tool', 'think'].includes(x.state) ? plStrip(x.targ || '') : '' }));   // doing: same rule as sessTaskHtml (targ = Agent description only)
}
function plRunModels(p){   // overrides that differ from the saved value only
  const o = {};
  Object.keys((PLRUN && PLRUN.models) || {}).forEach(t => {
    const st = p.stages.find(s => s.title === t), v = PLRUN.models[t];
    if(st && v && v !== (st.model || p.defaults.model)) o[t] = v;
  });
  return o;
}
// Why «Confirm — send» is disabled ('' = enabled); shown as the button title so a greyed button explains itself.
function plGoWhy(cur, req, busy){
  if(busy) return T('Sending…', 'run');
  if(!cur) return T('No session to send to');
  if(!cur.login) return T('This session is not logged in to the mailbox, so it cannot receive the request');
  if(!String(req || '').trim()) return T('Type a one-line request');
  return '';
}
function plGoSet(go, cur, req, busy){
  if(!go) return;
  const why = plGoWhy(cur, req, busy);
  go.disabled = !!why;
  if(why) go.title = why; else go.removeAttribute('title');
}
function plRunPanel(p, models){
  if(!PLRUN || PLRUN.name !== p.name) return '';
  const ss = plSessions(PLS.proj);
  if(!ss.some(x => x.sid === PLRUN.sid)) PLRUN.sid = (ss.find(x => x.login) || ss[0] || {}).sid || '';
  const cur = ss.find(x => x.sid === PLRUN.sid);
  const sOpts = ss.map(x => '<option value="' + esc(x.sid) + '"' + (x.sid === PLRUN.sid ? ' selected' : '') + (x.login ? '' : ' disabled') + '>'
    + esc(sid8(x.sid) + (x.model ? ' · ' + x.model : '') + (x.login ? '' : ' · ' + T('not logged in to the mailbox'))) + '</option>').join('');
  const mRows = p.stages.map(s => {
    const saved = s.model || p.defaults.model, v = PLRUN.models[s.title] || saved;
    return '<label class=pll><span>' + esc(s.title) + '</span><select class=plrsel data-plrm="' + esc(s.title) + '">'
      + models.map(x => '<option value="' + esc(x) + '"' + (x === v ? ' selected' : '') + '>' + esc(x + (x === saved ? ' · ' + T('saved') : '')) + '</option>').join('')
      + '</select></label>';
  }).join('');
  const req = String(PLRUN.req || '').trim();
  const why = plGoWhy(cur, req, PLRUN.busy);
  return '<div class=plrun><div class=brh2><b>' + esc(T('Send a run request')) + '</b> <i>' + esc(T('The session runs it — Sidereus runs nothing')) + '</i></div>'
    + '<label class=pll><span>' + esc(T('Mode', 'how')) + '</span><select class=plrsel data-plmode' + (cur && cur.cx ? ' disabled title="' + esc(T('Workflow mode is not available for this session')) + '"' : '') + '>'
    + '<option value=direct' + (PLRUN.mode === 'wf' && !(cur && cur.cx) ? '' : ' selected') + '>' + esc(T('Session runs it directly (default)')) + '</option>'
    + '<option value=wf' + (PLRUN.mode === 'wf' && !(cur && cur.cx) ? ' selected' : '') + '>Workflow</option></select></label>'
    + '<div class=plfd>' + esc(T('Direct reuses the same agent on loop-backs and retries (fewer tokens) · Workflow starts a new agent per stage')) + '</div>'
    + (ss.length ? '<label class=pll><span>' + esc(T('Sessions')) + '</span><select class=plrsel data-plrs>' + sOpts + '</select></label>'
      : '<div class=hidnote>' + esc(T('No live session in this project')) + '</div>')
    + '<label class=pll><span>' + esc(T('Request')) + '</span><input class=plreq data-plrq maxlength=500 value="' + esc(PLRUN.req || '') + '" placeholder="' + esc(T('One-line request')) + '"></label>'
    + '<div class=plrms><span class=plrmh>' + esc(T('Change models for this run only')) + '</span>' + mRows + '</div>'
    + '<div class=brh2><b>' + esc(T('Message to send')) + '</b>' + (cur && cur.id ? ' <i>→ ' + esc(cur.id) + '</i>' : '') + '</div>'
    + '<pre class=plprev>' + esc(plDmFor(p, req || '…', plRunModels(p), !!(cur && cur.cx))) + '</pre>'
    + plCxHint(cur)
    + '<div class=plbar><button class="wkrgb" data-plgo' + (why ? ' disabled title="' + esc(why) + '"' : '') + '>' + esc(T('Confirm — send')) + '</button>'
    + '<button class="wkrgb" data-plrx>' + esc(T('Cancel')) + '</button></div></div>';
}
// Pure: UI-only note for a Codex recipient (it reads the mailbox at a turn end); never part of the sent body.
function plCxHint(cur){
  return cur && cur.cx ? '<div class=plfd data-cxhint>' + esc(T('This session picks it up when its current or next turn ends — type a line in its terminal if it is idle')) + '</div>' : '';
}
// Label "<type>: [pl:x/y] <desc>" -> {type, desc} (tag stripped); shared by the stage overview and the node tooltip.
function plLabParts(lab){
  const l = String(lab || ''), i = l.indexOf(': ');
  return { type: i > 0 ? l.slice(0, i).trim() : '', desc: plStrip((i > 0 ? l.slice(i + 2) : l).replace(PL_DESC_RE, '')).trim() };   // plStrip: also [pl:-]/[pl-skip:]/[pl-model:]
}
function plLabDesc(p){ return p.desc || (p.type === 'main' ? T('orchestrator') : ''); }
function plLabTip(lab){ const p = plLabParts(lab); return p.type + ' · ' + plLabDesc(p); }
// Agents of stage `title` (lt[title].ag from plrun), newest first: running ones if any, else all. Canvas node / overview row click (48d).
function plStageAgents(lt, title, now){
  const ag = (((lt || {})[title] || {}).ag) || [], live = ag.filter(a => a && a.run), use = live.length ? live : ag.filter(Boolean);
  return use.map(a => ({ id: a.aid || a.tid || '', run: !!a.run, lab: plAgLab(a), tid: a.aid === 'main' ? '' : subWorkId(a), t0: a.t0 || 0,
    sec: Math.max(0, Math.round((a.run ? now / 1000 : a.t1 || a.t0 || 0) - (a.t0 || 0))) })).sort((p, q) => q.t0 - p.t0);
}
// Work log (sidereus/work.py, click only): an agent with a tid → its own log, else (main mark, workflow) the session's.
function plOpenWork(sid, tid){
  const x = (SESS || []).find(r => r.sid === sid);
  if(!x || !x.cwd) return;
  if(tid) openAgent(x.cwd, tid); else openSession(x.cwd, 'sess:' + x.cwd + '|' + sid);
}
const PL_MK = { done: '✓', run: '●', fail: '✕', back: '↺', skip: '↷', hold: '⏸', wait: '·' };
// Stage overview rows (file order): outcome, loop-backs in, agent count, elapsed, newest agent's type.
function plStageRows(lt, stages){
  return (stages || []).map(s => {
    const L = (lt || {})[s.title] || { st: 'wait' }, ag = L.ag || [];
    const nw = ag.reduce((b, a) => a && (!b || (a.t0 || 0) >= (b.t0 || 0)) ? a : b, null);
    return { t: s.title, st: PL_MK[L.st] ? L.st : 'wait', why: L.why || '', rb: Object.values(L.from || {}).reduce((a, v) => a + (+v || 0), 0), n: L.n || 0, sec: L.sec || 0, tot: L.tot || L.sec || 0, k: L.k || 1,
      ps: (L.ps || []).map((p, i) => plPass(L, i)),
      ag: ag.length, type: nw ? plLabParts(plAgLab(nw)).type : L.main ? 'main' : '' };   // server `main`: no dispatch, only main's tagged Bash
  });
}
// Under the canvas: compact per-stage overview of the plrun run. Workflow runs: nothing (48g has its own table).
function plRunTable(lv, p){
  if(!lv || !lv.pr) return '';
  const th = ['Stage', 'State', '↺', 'Agents', 'Elapsed', 'Latest agent'];
  return '<div class=plrt data-plsid="' + esc(lv.sid) + '"><div class=plrth><b>' + esc(TV({msg: 'By stage · agents {n}', vars: {n: lv.run.total}})) + '</b></div>'
    + '<table class="plrtb plso"><colgroup><col class=c1><col class=c4><col class=c5><col class=c5><col class=c5><col></colgroup><thead><tr>'
    + th.map(e => '<th>' + esc(T(e)) + '</th>').join('') + '</tr></thead><tbody>'
    + plStageRows(lv.lt, p.stages).map(r => '<tr' + (r.st === 'wait' ? ' class=plso-w' : ' data-plst="' + esc(r.t) + '"' + (r.st === 'run' ? ' class=on' : '')) + '>'
      + '<td title="' + esc(r.t) + '">' + esc(plgShow(r.t)) + '</td><td class=plrt-' + r.st + (r.why ? ' title="' + esc(r.why) + '"' : '') + '><span class=plrtpl>' + esc(PL_MK[r.st] + ' ' + (r.st === 'wait' ? T('Waiting') : plOc(r.st)))
      + '</span></td><td>' + (r.rb ? esc('↺ ' + r.rb) : '') + '</td><td>' + (r.n ? esc(String(r.n)) : '') + '</td><td' + (r.k > 1 ? ' title="' + esc(plPassTip(r)) + '"' : '') + '>' + (r.sec ? esc(ago(r.sec)) : '')
      + '</td><td title="' + esc(r.type) + '">' + esc(r.type) + '</td></tr>').join('') + '</tbody></table></div>';
}
// Pass picked on a card (E.pass[nodeId] = {k, i}, memory only); dropped once the stage starts another pass. -1 = latest.
function plPassSel(E, id, L){
  const c = E.pass && E.pass[id];
  if(!c) return -1;
  if(!L || c.k !== L.k || !plPass(L, c.i)){ delete E.pass[id]; return -1; }
  return c.i;
}
// Card pass picker (.plpass): same fixed menu as #plapk. ⚠Its pointerdown must not start a node drag or the work log.
let PLPSK = null;   // open pass menu {id}
function plPskClose(){ const el = document.getElementById('plpsk'); if(el) el.remove(); PLPSK = null; }
function plPskOpen(id, rc){
  const E = plCurEnt(), n = E && plgNode(E.G, id), L = n && E.lt && E.lt[n.title];
  plPskClose();
  if(!L || !(L.ps || []).length) return;
  const cur = plPassSel(E, id, L), it = (i, lab) => '<button class=plapki data-plpsk="' + i + '" aria-checked=' + (i === cur) + ' role=menuitemradio><span>' + esc(lab) + '</span></button>';
  PLPSK = { id };
  const el = document.createElement('div');
  el.id = 'plpsk'; el.className = 'plapk plpsk'; el.setAttribute('role', 'menu');
  el.innerHTML = L.ps.map((p, i) => it(i, TV({msg: 'Pass {n}', vars: {n: plPass(L, i).k}}) + ' · ' + plOc(p.s))).join('') + it(-1, T('Latest pass') + ' · ' + plOc(L.st));
  el.style.left = Math.max(4, Math.min(rc.left, window.innerWidth - 184)) + 'px'; el.style.top = Math.round(rc.bottom + 4) + 'px';   // fixed: never scrolls the view
  document.body.appendChild(el);
}
document.addEventListener('pointerdown', e => {
  const t = e.target.closest ? e.target : null;
  if(t && t.closest('[data-plpass]')){ e.stopPropagation(); return; }   // capture: the canvas drag handler never sees it
  if(PLPSK && !(t && t.closest('#plpsk'))) plPskClose();
}, true);
document.addEventListener('click', e => {
  const t = e.target.closest ? e.target : null, b = t && t.closest('[data-plpass]');
  if(b){ const id = b.dataset.plpass; if(PLPSK && PLPSK.id === id) plPskClose(); else plPskOpen(id, b.getBoundingClientRect()); return; }
  const m = PLPSK && t && t.closest('[data-plpsk]'), E = m && plCurEnt();
  if(!m) return;
  const i = +m.dataset.plpsk, n = E && plgNode(E.G, PLPSK.id), L = n && E.lt && E.lt[n.title];
  if(E && L){ E.pass = E.pass || {}; if(i >= 0) E.pass[n.id] = { k: L.k, i }; else delete E.pass[n.id]; }
  plPskClose(); plPaint();
});
document.addEventListener('keydown', e => { if(PLPSK && e.key === 'Escape') plPskClose(); });
// Elapsed-cell tooltip: total + pass count, then one «Pass n · outcome · elapsed» line per recorded pass and the latest.
function plPassTip(r){
  const pl = (k, st, sec) => TV({msg: 'Pass {n}', vars: {n: k}}) + ' · ' + plOc(st) + ' · ' + ago(sec);
  const ls = (r.ps || []).filter(Boolean).map(p => pl(p.k, p.st, p.sec));
  return [TV({msg: 'total {n} · pass {m}', vars: {n: ago(r.tot), m: r.k}})].concat(ls.length ? ls.concat(pl(r.k, r.st, r.sec)) : []).join('\n');
}
// Row click = the newest agent's work log, or the chooser for 2+ (48d plNodeWork, same as a running node click).
document.addEventListener('click', e => {
  const tr = e.target.closest && e.target.closest('.plrt tr[data-plst]');
  if(tr && typeof plNodeWork === 'function') plNodeWork(tr.dataset.plst, tr.getBoundingClientRect());
});
// Header strip: gradient progress (done / stages) + elapsed; green «Done» once every stage is done and nothing runs.
// Running-runs overview: every running (project, pipeline) above the chips. Metadata only: stage titles + agent counts.
// p = that project's pipeline (null = not loaded: no strip, running titles from the [pl:] tags), lv = plLiveRun, tags = [{aid, title}].
function plOvRow(proj, name, p, lv, tags, now){
  if(!p){ const ts = tags || []; return { proj, name, sid: (ts[0] || {}).sid || '', stages: null, cur: [...new Set(ts.map(t => t.title))], n: new Set(ts.map(t => t.aid)).size }; }
  const lt = lv ? (lv.lt || plLight(p.stages, lv.run)) : {};
  const stages = (p.stages || []).map(s => { const L = lt[s.title] || {}, st = L.st; return { t: s.title, st: st === 'run' || st === 'done' || st === 'fail' || st === 'back' || st === 'skip' || st === 'hold' ? st : 'wait',
    rb: Object.values(L.from || {}).reduce((a, v) => a + v, 0) }; });
  const n = lv ? (lv.run && lv.run.total) || 0 : 0;
  return { proj, name, sid: lv ? lv.sid : '', stages, cur: stages.filter(s => s.st === 'run').map(s => s.t), n };
}
// Running stage: the dot gets its own box so the pulse ring (43-pipeline.css .plovdot) centres on it without moving text.
function plOvRunHtml(t){ return '<span class="plovst plov-run plov-pulse"><i class=plovdot aria-hidden=true>●</i> ' + esc(t) + '</span>'; }
function plOvHtml(rows, proj, sel){
  if(!rows.length) return '';
  const mk = PL_MK;   // same marks as the run table (skip = ↷)
  // Row click = open that pipeline (project + name); agent work logs are in the run table under the canvas.
  return '<div class=plov><b class=plovh>' + esc(TV({msg: 'Running {n}', vars: {n: rows.length}})) + '</b>' + rows.map(r => '<div role=button tabindex=0 class="plovr'
    + ((r.wf ? r.on : r.proj === proj && r.name === sel) ? ' on' : '') + '" data-plovw="' + esc(r.sid || '') + '" data-plovwp="' + esc(r.proj) + '" data-plovwn="' + esc(r.name) + '"'
    + (r.wf ? ' data-plovwf="' + esc(r.wf) + '"' : '') + ' title="'   // Workflow run row (48g): opens that run read-only
    + esc(r.proj + '\n' + (r.wf ? T('Click to open this Workflow') : T('Click to open this pipeline'))) + '"><span class=plovp>'
    + esc(strShort(r.proj)) + '</span><b class=plovn>' + esc(r.name) + '</b><span class=plovs>'
    + (r.stages ? r.stages.map(s => s.st === 'run' ? plOvRunHtml(plgShow(s.t) + (s.rb ? ' ↺' + s.rb : ''))   // display name, as the canvas and run table
        : '<span class="plovst plov-' + s.st + '">' + esc(mk[s.st] + ' ' + plgShow(s.t) + (s.rb ? ' ↺' + s.rb : '')) + '</span>').join('')
      : r.cur.map(t => plOvRunHtml(plgShow(t))).join(''))
    + '</span><span class=plova>' + (r.sumh || esc(TV({msg: 'Agents {n}', vars: {n: r.n}}))) + '</span></div>').join('') + '</div>';   // sumh = 48g wfSumHtml (escaped there)
}
// Live data → rows; a project whose pipeline list isn't loaded gets the tag-only row and a load kick (plLoad guards repeats).
function plOverview(){
  const orph = [], live = plLiveProjs(SESS, plMem(), plKnown(), orph), now = Date.now(), rows = [];
  Object.keys(live).sort().forEach(proj => live[proj].forEach(name => {
    const ag = name === ARCH_PL && typeof plAgRun === 'function' ? plAgRun(proj) : null;
    if(ag){ rows.push(plAgOvRow(proj, ag, now)); return; }   // Sidereus tool pipeline: not in proj's list, state from archRun
    const d = PLS.data[proj];
    if(!d) plLoad(proj, false);
    const p = d && d.ok ? (d.pipelines || []).find(q => q.name === name) : null;
    const tags = p ? null : [].concat(...plProjSess(proj).map(x => plSubsOf(x).map(a => ({ aid: a.aid || a.lab, sid: x.sid, d: plDescStage(a.lab) }))))
      .filter(t => t.d && t.d.name === name).map(t => ({ aid: t.aid, sid: t.sid, title: t.d.title }));
    rows.push(plOvRow(proj, name, p, p ? plLiveRun(proj, name) : null, tags, now));
  }));
  (SESS || []).forEach(x => (x && x.cwd ? x.wf || [] : []).forEach(r => {   // running Workflow-tool runs (not the pipeline runner)
    if(!r || !r.id || !r.run || r.name === 'pipeline') return;
    const lt = wfLight(r);
    rows.push({ proj: x.cwd, name: r.name || r.id, sid: x.sid, wf: r.id, on: !!(PLS.wf && PLS.wf.sid === x.sid && PLS.wf.id === r.id),
      stages: wfStages(r).map(t => ({ t, st: lt[t].st })), cur: [], n: (r.agents || []).length, sumh: wfSumHtml(r, now / 1000) });
  }));
  const cp = PLS.wf ? null : plCur();
  return plOvHtml(rows, PLS.proj, cp ? cp.name : '') + plOrphHtml(orph);
}
// Tagged run whose pipeline file is in no known project (or in two): session id + pipeline name only (rule 1).
function plOrphHtml(orph){
  return (orph || []).map(o => '<div class=hidnote>' + esc(T('Pipeline running from another folder') + ': ' + o.name + ' · ' + T('session') + ' '
    + sid8(o.sid) + ' — ' + T('pipeline file not found')) + '</div>').join('');
}
function plOvPick(proj, name){   // same as a chip click + pipeline pick; ⚠never scroll or centre
  if(PLVIEW !== 'pipe'){ PLVIEW = 'pipe'; lsSet('sidereus.plview', PLVIEW); }   // ⚠a remembered Harness sub-view would hide the picked pipeline
  PLS.proj = proj; PLS.sel = name; PLS.wf = null; lsSet('sidereus.plproj', PLS.proj);
  if(!PLS.projs) PLS.pend = proj;   // ⚠plLoadProjs would reset a project not in its list (borrowed-only) to the first one
  PLAG = false;   // an open arch-map panel (48h) would hide the picked pipeline
  PLNEW = null; PLS.std = ''; PLS.diff = null; PLS.del = null; PLS.msg = ''; plPaint();
}
document.addEventListener('click', e => {
  const r = e.target.closest && e.target.closest('[data-plovw]');
  if(r && r.dataset.plovwf){ PLS.proj = r.dataset.plovwp; lsSet('sidereus.plproj', PLS.proj); PLS.wf = { sid: r.dataset.plovw, id: r.dataset.plovwf };
    PLNEW = null; PLS.std = ''; PLS.diff = null; PLS.del = null; PLS.msg = ''; plPaint(); }
  else if(r) plOvPick(r.dataset.plovwp, r.dataset.plovwn);
});
document.addEventListener('keydown', e => {
  if(e.key === 'Enter' && e.target && e.target.matches && e.target.matches('[data-plovw]')){ e.preventDefault(); e.target.click(); }
});
function plLiveHead(lv, lt){
  if(!lv) return '';
  const r = lv.run, v = Object.values(lt || {}), n = v.length, k = v.filter(x => x.st === 'done' || x.st === 'skip').length;   // a skipped stage is finished too
  const fin = !r.run && n > 0 && k === n, sec = r.start ? Math.max(0, (r.run ? Date.now() / 1000 : (r.end || 0)) - r.start) : Math.max(0, ...v.map(x => x.sec || 0));
  const txt = (fin ? T('Done') : r.run ? T('Running') : T('Last run')) + ' · ' + sid8(lv.sid)
    + (r.phase ? ' · ' + plgShow(r.phase) : '') + ' · ' + T('Agent') + ' ' + r.total + (r.fail ? ' · ' + T('Failures') + ' ' + r.fail : '') + ' · ' + TV({msg: '{n}/{m} done', vars: {n: k, m: n}}) + ' · ' + ago(Math.round(sec));   // counts finished stages; agents are counted above
  const nav = plRunNav(lv), old = !!nav && nav.rid !== nav.cur;
  return '<div class="plrunst' + (r.run ? ' on' : '') + (fin ? ' fin' : '') + (old ? ' old' : '') + '"><span title="' + esc(txt) + '">' + plRunPick(nav) + esc(txt)   // title: the bar line is ellipsised (43-pipeline.css)
    + '</span><i class=plprog><i style="width:' + (n ? Math.round(100 * k / n) : 0) + '%"></i></i></div>';
}
async function plRunSend(){
  const p = plCur();
  if(!PLRUN || PLRUN.busy || !p) return;
  const cur = plSessions(PLS.proj).find(x => x.sid === PLRUN.sid), req = String(PLRUN.req || '').trim();
  if(!cur || !cur.login || !req) return;
  PLRUN.busy = true; plPaint();
  try{
    const j = await postJSON('/api/dm', { to: cur.id, body: plDmFor(p, req, plRunModels(p), !!cur.cx), relay: true, sid: cur.sid, thread: 'pipeline:' + p.name });
    if(!j || !j.ok) throw new Error((j && (j.error || j.err)) || '?');   // ⚠ok first: nothing went out, remember nothing
    const m = plMem(); m[cur.sid] = { name: p.name, at: Date.now() }; lsSetJson('sidereus.plrun', m);
    PLRUN = null; PLS.msg = T('Sent') + ' → ' + cur.id;
  }catch(e){ PLRUN.busy = false; PLS.msg = T('Could not send') + ': ' + T((e && e.message) || e); }
  plPaint();
}
document.addEventListener('click', e => {
  if(!e.target.closest || !e.target.closest('.plw')) return;
  if(e.target.closest('[data-plrun]')){ const p = plCur(); if(p && !p.from){ PLRUN = PLRUN && PLRUN.name === p.name ? null : { name: p.name, sid: '', req: '', models: {}, busy: false, mode: plModeOf(p.name) }; PLS.msg = ''; plPaint(); } return; }
  if(e.target.closest('[data-plrx]')){ PLRUN = null; plPaint(); return; }
  if(e.target.closest('[data-plgo]')) plRunSend();
});
document.addEventListener('change', e => {
  const s = e.target;
  if(!PLRUN || !s || !s.closest || !s.closest('.plw')) return;
  if(s.dataset.plrs != null){ PLRUN.sid = s.value; plPaint(); }
  else if(s.dataset.plmode != null){ PLRUN.mode = s.value === 'wf' ? 'wf' : 'direct'; lsSet('sidereus.plmode.' + PLRUN.name, PLRUN.mode); plPaint(); }
  else if(s.dataset.plrm != null){ PLRUN.models[s.dataset.plrm] = s.value; plPaint(); }
});
// Typing updates state + preview in place (a repaint would drop the caret).
document.addEventListener('input', e => {
  const s = e.target;
  if(!PLRUN || !s || !s.closest || !s.closest('.plw') || s.dataset.plrq == null) return;
  PLRUN.req = s.value;
  const p = plCur(), pre = s.closest('.plw').querySelector('.plprev'), go = s.closest('.plw').querySelector('[data-plgo]');
  const cur = plSessions(PLS.proj).find(x => x.sid === PLRUN.sid);
  if(p && pre) pre.textContent = plDmFor(p, String(PLRUN.req).trim() || '…', plRunModels(p), !!(cur && cur.cx));
  plGoSet(go, cur, PLRUN.req, PLRUN.busy);
});
// Called from each /api/state poll (95-poll.js): relight the open pipeline view from the fresh SESS rows.
function plPoll(){
  if(mainView !== 'pipe') return;
  // After an «Ask AI for a draft» DM: re-list every 20 s for 10 min so the new file shows up (48e PLS.draft); the session's cwd too
  const now = Date.now(), dr = PLS.draft;
  if(dr && !(now - dr.at < PL_DRAFT_TTL)) plDraftSet(null);
  else if(dr && now - (PLS.listAt || 0) > 20000){ PLS.listAt = now; [...new Set([PLS.proj, dr.proj, dr.cwd])].forEach(p => { if(p) plLoad(p, true); }); }
  const box = document.getElementById('feed');
  if(box) paintPipe(box, true);
}
