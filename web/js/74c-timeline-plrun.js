// Pipeline run on a session row: a stage stepper in the name cell + one band per stage on the bar track.
// Metadata only (rule 1): stage titles, outcomes, times, loop-back counts, gate step names/numbers — never agent labels.
const TLPL_REQ = new Set();      // projects whose pipeline list was requested once (stage order)
const TLPL_ICON = { done: '✓', run: '◉', skip: '↷', back: '↺', fail: '✕', hold: '⏸', wait: '·' };   // known states (keys); glyphs are no longer drawn
let TLPL_FO = '';                // id of the focused strip, restored after paintTl rewrites #feed
const TLPL_EXP = new Set();      // session sids whose ended runs are expanded under the live ones (in-memory only)
const TLPL_MAX = 3;              // live runs stacked per row; the rest fold into «+N»
// Runs for timeline group g -> {runs, more, ended, st, key} | null. runs = up to 3 live runs (no end, a stage still «run»), newest t1 first;
// with none live, the newest run that touched the window (t1 >= L.t0). ended = the other non-live runs in the window, newest first.
function tlPlRun(g, L){
  if(typeof FEATS === 'object' && FEATS && FEATS.pipeline === false) return null;
  const sids = new Set(((g && g.items) || []).map(x => x && x.sid).filter(Boolean));
  if(!sids.size) return null;
  const all = [];
  (SESS || []).forEach(x => { if(x && sids.has(x.sid)) (x.plrun || []).forEach(r => { if(r && r.name) all.push({ sid: x.sid, r }); }); });
  const newest = (a, b) => (b.r.t1 || 0) - (a.r.t1 || 0);
  const open = all.filter(o => !o.r.end && plPrLive(o.r)).sort(newest);
  const w0 = (L && L.t0) || 0;
  const done = all.filter(o => !open.includes(o) && (o.r.t1 || 0) >= w0).sort(newest);
  const top = open.length ? open.slice(0, TLPL_MAX) : done.slice(0, 1);
  if(!top.length) return null;
  const mk = (o, fin) => tlPlOne(o, fin, g, L);
  const runs = top.map(o => mk(o, !open.includes(o))), ended = done.filter(o => !top.includes(o)).map(o => mk(o, true));
  // Row status: a failed stage in any shown or folded run wins, then live, else ended.
  const st = runs.concat(ended).some(p => tlPlSt(p) === 'fail') ? 'fail' : open.length ? 'run' : 'fin';
  return { runs, more: Math.max(0, open.length - TLPL_MAX), ended, st, key: top[0].sid };
}
// One run -> {sid, pr, proj, name, titles, lt, fin, now (s)}; fin = not live (its stage left at «run» shows the closed outcome).
function tlPlOne(o, fin, g, L){
  const pr = o.r, proj = pr.proj || (g && g.cwd) || '';
  const d = PLS.data[proj];
  if(!d && proj && !TLPL_REQ.has(proj)){ TLPL_REQ.add(proj); tlPlLoad(proj); }
  const p = d && (d.pipelines || []).find(q => q && q.name === pr.name);
  const S = pr.stages || {};
  // File order once the list is loaded (unrun file stages keep their file slot); recorded stages the file lacks follow by start time.
  // ⚠A file stage never run shows first as «·» when it leads the file (e.g. live-verify «deploy check») — that is file order, not a fallback.
  const byT0 = Object.keys(S).sort((a, b) => ((S[a] && S[a].t0) || 1e15) - ((S[b] && S[b].t0) || 1e15));
  const fs = p && Array.isArray(p.stages) ? p.stages.filter(s => s && s.title) : [];
  const stages = fs.concat(byT0.filter(t => !fs.some(s => plTk(s.title) === t)).map(t => ({ title: t })));
  const lt = plPrLt(pr, stages, ((L && L.now) || Date.now() / 1000) * 1000);
  // ⚠An ended run must not look live: a stage left at «run» shows its closed outcome.
  if(fin) Object.keys(lt).forEach(t => { if(lt[t].st === 'run'){ lt[t].st = 'done'; lt[t].cut = 1; lt[t].w1 = (S[plTk(t)] && (S[plTk(t)].t1 || S[plTk(t)].t0)) || lt[t].w0; } });
  return { sid: o.sid, pr, proj, name: pr.name, titles: stages.map(s => s.title), lt, fin, now: (L && L.now) || Date.now() / 1000 };
}
// plOc (48d) picks the stage context.
function tlPlOc(st){ return st === 'wait' ? T('Waiting') : (PL_OUTCOME[st] ? plOc(st) : T('Waiting')); }
// Current stage = the running one, else the one that finished last.
function tlPlCur(pl){
  const run = pl.titles.find(t => pl.lt[t] && pl.lt[t].st === 'run');
  if(run) return run;
  return pl.titles.reduce((m, t) => (pl.lt[t] && pl.lt[t].st !== 'wait' && (!m || pl.lt[t].w1 >= pl.lt[m].w1) ? t : m), '');
}
// Run status for the row accent and stepper colours: a failed stage wins, then ended, else running.
function tlPlSt(pl){ return pl.titles.some(t => pl.lt[t] && pl.lt[t].st === 'fail') ? 'fail' : pl.fin ? 'fin' : 'run'; }
// Class hook for the session row (74b): left accent bar coloured by the row status (tlPlRun st); '' without a run.
function tlPlRowCls(pl){ return pl ? ' tlrpl tlrpl-' + pl.st : ''; }
// Shared stage stepper (timeline row here, work log in 35e — hoisted, both run after load): one bar segment per stage
// (`.tlpd`, colour = state; name under it, ellipsised in the row, title keeps stage + state), p/cur mark steps before / at ci. steps = [{st, nm, tip, cls (escaped class suffix), attr (escaped attributes), extra (escaped html)}];
// mod = root class suffix ('fin' ended, 'lg' popup size). Styles: 21-timeline-plrun.css.
function plStepper(steps, ci, mod){
  return '<i class="tlpst' + (mod ? ' ' + mod : '') + '">' + steps.map((s, i) => {
    const st = TLPL_ICON[s.st] ? s.st : 'wait', pos = i < ci ? ' p' : i === ci ? ' cur' : '';   // p = passed: both sides coloured
    return '<i class="tlpls pl-' + st + pos + (s.cls || '') + '"' + (s.attr || '') + ' title="' + esc(s.tip) + '">'
      + '<i class=tlpd aria-hidden=true></i><i class=tlpn>' + esc(s.nm) + (s.extra || '') + '</i></i>';
  }).join('') + '</i>';
}
// Stepper key for the timeline header: [state, label, one-sentence tip]; drawn by plStepper so colours and stripes are the rows' own.
//   4th item = T() context of the label.
const TLPL_LEGEND = [['done', 'Done', 'this stage finished'], ['run', 'Running', 'this stage is running now', 'stage'], ['back', 'Sent back', 'this stage sent the run back to an earlier stage'],
  ['fail', 'Failed', 'this stage ended in failure'], ['wait', 'Waiting', 'not started yet'], ['skip', 'Skipped', 'not needed, skipped']];
function tlPlLegend(){
  // ⚠'Failed|stage' context: plain 'Failed' maps to a different Korean sentence.
  const steps = TLPL_LEGEND.map(([st, k, tip, c]) => { const nm = st === 'fail' ? T('Failed', 'stage') : T(k, c); return { st, nm, tip: nm + ': ' + T(tip) }; });
  // Expanded inline; tlPlKeyFit folds it (.tlplgf: «Pipeline ▾» + hover/focus popover) only when the head would take two lines.
  return '<div class=tlplg><i class=tlplgt title="' + esc(T('A finished run reads ✓ Done · ✕ Failed · ⏸ Aborted')) + '">' + esc(T('Pipeline')) + '<i class=tlplgc aria-hidden=true> ▾</i></i>'
    + '<div class=tlplgp id=tlplgp>' + plStepper(steps, -1, 'tlplgs') + '</div></div>';
}
// Pure: fold when the expanded head wrapped (the .tlhr wrapper starts below the summary's middle line).
function tlPlKeyWraps(sum, hr){ return !!(sum && hr) && hr.top > sum.top + sum.height / 2; }
// ⚠Decided from the expanded layout only, in one synchronous pass (expand → measure → fold): .tlsum wraps by its 200px basis,
//   so the answer depends on width alone and the observer cannot flap. Folded = focusable label describing the popover.
let TLPL_KRO = null;
function tlPlKeyFit(box){
  if(TLPL_KRO){ TLPL_KRO.disconnect(); TLPL_KRO = null; }
  const head = box && box.querySelector('.wvh.wvht'), g = head && head.querySelector('.tlplg');
  if(!g) return;
  const fit = () => {
    const lab = g.querySelector('.tlplgt'), pop = g.querySelector('.tlplgp');
    g.classList.remove('tlplgf');
    const sm = head.querySelector('.tlsum'), hr = head.querySelector('.tlhr');
    const f = tlPlKeyWraps(sm && sm.getBoundingClientRect(), hr && hr.getBoundingClientRect());
    g.classList.toggle('tlplgf', f);
    if(lab){ if(f){ lab.tabIndex = 0; lab.setAttribute('aria-describedby', 'tlplgp'); } else { lab.removeAttribute('tabindex'); lab.removeAttribute('aria-describedby'); } }
    if(pop){ if(f) pop.setAttribute('role', 'tooltip'); else pop.removeAttribute('role'); }
  };
  fit();
  if(typeof ResizeObserver !== 'undefined'){ TLPL_KRO = new ResizeObserver(fit); TLPL_KRO.observe(head); const hr = head.querySelector('.tlhr'); if(hr) TLPL_KRO.observe(hr); }
}
// Header: the key only when a drawn row (gs = tlOrdered groups) has a run, then the «Runs N» chip (every session, not only drawn rows; chips open in a popover).
// ⚠The chip is out of flow (21-timeline-plrun.css): in flow it wrapped alone to a new header line and shifted the body.
let TLPL_HS = [];
function tlPlLegendFor(gs, L){
  const now = (L && L.now) || Date.now() / 1000;
  TLPL_HS = tlPlHead(SESS, typeof ATTN === 'undefined' ? null : ATTN, now);
  return ((gs || []).some(g => tlPlRun(g, L)) ? tlPlLegend() : '') + tlPlHeadBtn(TLPL_HS);
}
// One compact chip instead of always-on run chips; colour = worst state (fail > back > stuck > none). '' without runs.
function tlPlHeadBtn(hs){
  if(!hs || !hs.length) return '';
  const k = ['fail', 'back', 'stuck'].find(s => hs.some(h => h.k === s)) || 'none';
  const open = typeof popIsOpen === 'function' && popIsOpen('tlplhp');
  return '<button type=button class="tlplhb tlplhb-' + k + '" id=tlplhb aria-haspopup=dialog aria-expanded=' + open
    + ' title="' + esc(T('Pipeline runs — click to list them')) + '">' + esc(TV({ msg: 'Runs {n}', vars: { n: hs.length } })) + '</button>';
}
// Popover with the run chips (tlPlHeadHtml), fixed under the chip (popAnchor): ⚠never scrolls; Esc / outside click close it (popReg).
function tlPlHeadClose(back){ popHide('tlplhp', document.getElementById('tlplhb'), back, { preventScroll: true }); }
function tlPlHeadFill(p){
  p.innerHTML = tlPlHeadHtml(TLPL_HS);
  p.querySelectorAll('.tlplc[data-tlpln]').forEach(tlPlChipWire);
}
function tlPlHeadToggle(b){
  if(popIsOpen('tlplhp')) return tlPlHeadClose(false);
  const p = popGet('tlplhp', 'thpop tlplhp');
  p.setAttribute('role', 'dialog');
  p.setAttribute('aria-label', T('Pipeline runs'));
  tlPlHeadFill(p);
  popAnchor(p, b, { align: 'right', flipY: true });
}
popReg('tlplhp', '#tlplhp, #tlplhb', tlPlHeadClose);
// «Pipeline recording off» note (row `plOff`, sessions._pl_off): Apply is off for the project, so its [pl:] tags record no run.
function tlPlOffNote(g){
  if(typeof FEATS === 'object' && FEATS && FEATS.pipeline === false) return '';
  const sids = new Set(((g && g.items) || []).map(x => x && x.sid).filter(Boolean));
  if(!(SESS || []).some(x => x && x.plOff && sids.has(x.sid))) return '';
  return '<i class=tlploff title="' + esc(T('«Apply» is off for this project, so its [pl:] tagged stages record no run — turn it on in Pipelines › Apply')) + '">'
    + esc(T('Pipeline recording off')) + '</i>';
}
// Run summary at the timeline head: open runs and runs ended within TLPL_RECENT_S, from all of SESS[].plrun.
const TLPL_RECENT_S = 600, TLPL_HMAX = 3;
const TLPL_STALL_S = 1800;   // mirrors sidereus/attention.py ATT_STALL_S
const TLPL_HK = { fail: 0, back: 1, stuck: 2, run: 3, ok: 4, stop: 4 };   // chip order, most urgent first
// -> [{sid, ri, proj, name, stages[], sec, k, why, ev, pl}]; k: fail > back > stuck > run for open runs, fail/ok/stop for ended ones.
function tlPlHead(sess, attn, now){
  if(typeof FEATS === 'object' && FEATS && FEATS.pipeline === false) return [];
  const stall = new Set(((attn && attn.rows) || []).filter(a => a && (a.sigs || []).some(g => g && g.k === 'stall')).map(a => a.sid));
  const out = [];
  (sess || []).forEach(x => ((x && x.plrun) || []).forEach((r, ri) => {
    if(!r || !r.name) return;
    const open = !r.end && plPrLive(r);
    if(!open && !(r.end && now - r.end <= TLPL_RECENT_S)) return;
    const pl = tlPlOne({ sid: x.sid, r }, !open, { cwd: x.cwd }, { now }), lt = pl.lt, cur = tlPlCur(pl), cv = cur ? lt[cur] : null;
    const runT = open ? pl.titles.filter(t => lt[t] && lt[t].st === 'run') : [];
    const fail = tlPlSt(pl) === 'fail', st = x.state || '';
    let k = open ? 'run' : tlPlEnd(pl, '', true), why = '';
    if(open){
      // ⚠Idle = the session's ageSec (last transcript activity), not the stage's pass age: a long stage can be busy.
      const idle = +x.ageSec || 0, quiet = idle >= TLPL_STALL_S && !runT.some(t => (lt[t].ag || []).some(a => a && a.run));
      if(st === 'ask' || st === 'abort') why = T('waiting for an answer');
      else if(stall.has(x.sid)) why = T('Subagent stalled');
      else if(quiet && st !== 'think' && st !== 'tool') why = TV({ msg: 'no activity {t}', vars: { t: ago(idle) } });
      k = fail ? 'fail' : cv && (cv.via || (cv.k || 1) >= 2) ? 'back' : why && runT.length ? 'stuck' : 'run';
      if(k !== 'stuck') why = '';
    }
    const stages = runT.length ? runT : cur ? [cur] : [];
    const sec = open ? stages.reduce((m, t) => Math.max(m, lt[t].sec || 0), 0) : Math.max(0, Math.round(now - r.end));
    const ev = !open || fail ? plEvLine(plEvRows(pl.proj), cv, plEvCommits(pl.proj)) : '';
    out.push({ sid: x.sid, ri, proj: pl.proj, name: r.name, stages, sec, k, why, ev, open, t1: r.t1 || 0, pl });
  }));
  return out.sort((a, b) => (TLPL_HK[a.k] - TLPL_HK[b.k]) || (b.open - a.open) || (b.t1 - a.t1));
}
// Chips: <pipeline> · <stage(s)> · <elapsed> + a small stepper; at most TLPL_HMAX, then «+N». Same data-tlplp/tlpln as row strips.
function tlPlHeadHtml(hs){
  if(!hs || !hs.length) return '';
  const ids = new Set();
  const chip = h => {
    let id = 'tlplh-' + sid8(h.sid) + '-' + h.name;
    if(ids.has(id)) id += '-' + h.ri;   // run index within the session: stable across repaints
    ids.add(id);
    const pl = h.pl, cur = tlPlCur(pl), stn = h.stages.map(plgShow).join(' · ');
    const steps = plStepper(pl.titles.map(t => { const st = (pl.lt[t] || {}).st, nm = plgShow(t); return { st, nm, tip: nm + ' · ' + tlPlOc(TLPL_ICON[st] ? st : 'wait') }; }),
      pl.titles.indexOf(cur), pl.fin ? 'fin' : '');
    const body = pl.fin ? tlPlEnd(pl, cur)
      : (h.k === 'stuck' ? '<strong class=tlplcw>' + esc(T('Stuck')) + '</strong>' : '')
        + '<i class=tlplcs>' + (h.k === 'back' ? '↺ ' : '') + esc(stn) + '</i>' + (h.sec > 0 ? '<i class=tlplct>' + esc(ago(h.sec)) + '</i>' : '');
    const lab = [h.name, stn, h.why].filter(Boolean).join(' · ') + ' — ' + T('Click to open it in the pipeline view');
    return '<div class="tlplc tlplc-' + h.k + '" role=button tabindex=0 id="' + esc(id) + '" data-tlplp="' + esc(h.proj) + '" data-tlpln="' + esc(h.name) + '"'
      + ' title="' + esc(lab) + '" aria-label="' + esc(lab) + '"><i class=tlplcn>' + esc(h.name) + '</i>' + steps + body + (h.ev || '') + tlPlEvWatch(h.proj) + '</div>';
  };
  const more = hs.length - TLPL_HMAX;
  return '<div class=tlplh>' + hs.slice(0, TLPL_HMAX).map(chip).join('')
    + (more > 0 ? '<i class=tlplhm title="' + esc(TV({ msg: '+{n} runs', vars: { n: more } }) + '\n' + hs.slice(TLPL_HMAX).map(h => h.name).join('\n')) + '">+' + more + '</i>' : '')
    + '</div>';
}
// Name-cell strips (pl = tlPlRun result; '' without one): one `.tlpl` line per live run (stepper + current stage and elapsed),
// «+N» on the last live line for live runs past 3, ended runs when expanded, then the `.tlplx` «+N done»/«Collapse» toggle.
// The gate line (plEvLine, styled in 21-timeline-plrun.css) sits inside the top run's line only.
function tlPlStrip(pl){
  if(!pl) return '';
  const ids = new Set(), exp = TLPL_EXP.has(pl.key);
  const line = (r, more, ev, nm) => {
    let id = 'tlpl-' + sid8(r.sid) + '-' + r.name;
    if(ids.has(id)) id += '-' + (r.pr.t0 || ids.size);
    ids.add(id);
    return tlPlLine(r, id, more, ev, nm);
  };
  const top = pl.runs[0], tc = tlPlCur(top), tv = tc ? top.lt[tc] : null;
  const ev = plEvLine(plEvRows(top.proj), tv, plEvCommits(top.proj)) + tlPlEvWatch(top.proj);
  const many = pl.runs.length + (exp ? pl.ended.length : 0) > 1;   // 2+ stacked lines: each names its pipeline
  let h = pl.runs.map((r, i) => line(r, i === pl.runs.length - 1 ? pl.more : 0, i ? '' : ev, many)).join('');
  if(exp) h += pl.ended.map(r => line(r, 0, '', many)).join('');
  if(pl.ended.length){
    const lab = exp ? T('Collapse') : T('+{n} finished runs').replace('{n}', pl.ended.length);
    h += '<button type=button class=tlplx id="' + esc('tlplx-' + sid8(pl.key)) + '" data-tlplx="' + esc(pl.key) + '" aria-expanded=' + exp + '>' + esc(lab) + '</button>';
  }
  return h;
}
// One run line: [pipeline name when shown] + stepper (segment + name per stage) + running stage names and elapsed + «+N» + ev (escaped gate line html, top run only).
function tlPlLine(r, id, more, ev, shown){
  const cur = tlPlCur(r);
  const steps = plStepper(r.titles.map(t => {
    const st = (r.lt[t] || {}).st, nm = plgShow(t);
    return { st, nm, tip: nm + ' · ' + tlPlOc(TLPL_ICON[st] ? st : 'wait') + ((r.lt[t] || {}).nn ? ' (' + T('not needed') + ')' : ''), cls: ' pf-' + esc(plgFam(t)) + ([...nm].length > 2 ? ' ln' : '') };   // ln: may ellipsise
  }), r.titles.indexOf(cur), r.fin ? 'fin' : '');
  // Live label names every running stage (parallel stages), elapsed = the longest; else the stage that finished last.
  const runT = r.fin ? [] : r.titles.filter(t => r.lt[t] && r.lt[t].st === 'run'), nm = runT.length ? runT : cur ? [cur] : [];
  const sec = nm.reduce((m, t) => Math.max(m, r.lt[t].sec || 0), 0);
  const now = r.fin ? tlPlEnd(r, cur) : nm.length ? '<i class=tlpc><strong>' + esc(nm.map(plgShow).join(' · ')) + '</strong>' + (sec > 0 ? ' · ' + esc(ago(sec)) : '') + '</i>' : '';
  const m = more ? '<i class=tlplm title="' + esc(T('Other pipelines running in the same session')) + '">+' + more + '</i>' : '';
  const lab = r.name + ' · ' + (r.fin ? T('Finished run') : T('Running', 'stage')) + ' — ' + T('Click to open it in the pipeline view');
  return '<div class="tlpl tlpl-' + tlPlSt(r) + (r.fin ? ' fin' : '') + '" role=button tabindex=0 id="' + esc(id) + '"'
    + ' data-tlplp="' + esc(r.proj) + '" data-tlpln="' + esc(r.name) + '" title="' + esc(lab) + '" aria-label="' + esc(lab) + '">'
    + (shown ? '<i class=tlpnm>' + esc(r.name) + '</i>' : '') + steps + now + m + (ev || '') + '</div>';
}
// ⚠An ended run's line reads as ended (outcome + how long ago), not as its last stage: the session often keeps working afterwards.
// kOnly: return the outcome key ('ok' | 'fail' | 'stop') instead of html (head chips, tlPlHead).
function tlPlEnd(r, cur, kOnly){
  // Done = the last non-skipped stage reached done (a «run» closed by the end counts); earlier «back» loops don't block it.
  const last = r.titles.slice().reverse().find(t => !(r.lt[t] && r.lt[t].st === 'skip'));
  const k = tlPlSt(r) === 'fail' ? 'fail' : last && r.lt[last] && r.lt[last].st === 'done' ? 'ok' : 'stop';
  if(kOnly) return k;
  // ⚠'Failed|stage' context: plain 'Failed' maps to a different Korean sentence.
  const lab = { ok: ['✓', T('Done')], fail: ['✕', T('Failed', 'stage')], stop: ['⏸', T('Aborted')] }[k];
  const t1 = r.pr.end || r.pr.t1 || 0, sec = t1 ? Math.max(0, Math.round((r.now || Date.now() / 1000) - t1)) : -1;
  return '<i class="tlpc tlpe tlpe-' + k + '"><strong><i aria-hidden=true>' + lab[0] + '</i> ' + esc(lab[1]) + '</strong>'
    + (cur ? ' · ' + esc(plgShow(cur)) : '') + (sec >= 0 ? ' · ' + esc(AGO(ago(sec))) : '') + '</i>';
}
// «+N done» chip: toggle this row's ended runs. ⚠Repaint only — paintTl keeps scroll; focus comes back by id (tlPlWire), never scrolled.
function tlPlExp(key){
  if(!key) return;
  if(TLPL_EXP.has(key)) TLPL_EXP.delete(key); else TLPL_EXP.add(key);
  tlPlRepaint();
}
// One coalesced timeline repaint when async inputs (stage list, gate evidence) land; paintTl keeps scroll and refocuses by id.
let TLPL_RP = 0;
function tlPlRepaint(){ if(!TLPL_RP) TLPL_RP = setTimeout(() => { TLPL_RP = 0; if(typeof paintTl === 'function') paintTl(); }, 50); }
// ⚠paintTl runs only on the timeline fetch (tlAuto, 30 s default; never when manual) while SESS[].plrun changes every poll:
//   tlSyncState calls this each poll and repaints when the stage outline changes (no times, so a steady run never repaints).
let TLPL_SIG = '';
function tlPlSig(sess){
  return JSON.stringify((sess || []).filter(x => x && x.plrun && x.plrun.length).map(x => [x.sid, x.plrun.map(r => [r.name, r.end ? 1 : 0, r.cur,
    Object.keys(r.stages || {}).map(t => { const s = r.stages[t] || {}; return [t, s.o, s.k || 0, s.via || '', (s.ag || []).filter(a => a && a.run).length]; })])]));
}
// ⚠Repaint on the first signature too: a Timeline painted before the first poll (no plrun, no accounts yet) otherwise kept
//   no «Runs n» lane and no account picker until the next loadTl (30 s, never in Manual). Account labels join the signature
//   because the picker is built only in paintTl. tlPlRepaint is debounced, so this costs one paint.
function tlPlSync(){
  const a = typeof acctList === 'function' ? (acctList() || []).map(x => x && x.label).join(',') : '';
  const s = tlPlSig(SESS) + '|' + a;
  if(s === TLPL_SIG) return;
  TLPL_SIG = s; tlPlRepaint();
}
// ⚠If another caller holds PLS.busy[proj], plLoad returns at once with no data: re-arm silently (repainting here would spin).
function tlPlLoad(proj){
  const q = plLoad(proj);
  if(q && q.then) q.then(() => { if(PLS.data[proj]) tlPlRepaint(); else TLPL_REQ.delete(proj); }, () => TLPL_REQ.delete(proj));
}
// plEvRows (48d) fetches without a callback: watch its cache entry and repaint once if the rows changed. Returns ''.
const TLPL_EVW = {};
function tlPlEvSig(rows){ return Array.isArray(rows) ? rows.length + ':' + ((rows[0] && rows[0].ts) || 0) : ''; }
function tlPlEvWatch(proj){
  const c = typeof PLEV === 'object' && PLEV ? PLEV[proj] : null;
  if(!c || !c.busy || TLPL_EVW[proj]) return '';
  const sig0 = tlPlEvSig(c.rows);
  TLPL_EVW[proj] = setInterval(() => {
    if(c.busy) return;
    clearInterval(TLPL_EVW[proj]); delete TLPL_EVW[proj];
    if(tlPlEvSig(c.rows) !== sig0) tlPlRepaint();
  }, 250);
  return '';
}
// Bands on the bar track: one per started stage over its window; a ↺ tick where the latest pass began when k >= 2.
// Work inside one stage span: session segs ∪ stage agent spans, clipped to [a, b] -> {sec: union seconds, pc: [[l, r] %]}.
// Pieces whose gap is under 0.5% of the track merge; at most TLPL_WMAX pieces (smallest gaps merge first).
const TLPL_WMAX = 40;
function tlPlWork(its, ag, a, b, pct){
  const iv = [];
  (its || []).forEach(x => ((x && x.segs) || []).forEach(p => { if(Array.isArray(p)) iv.push([+p[0], +p[1]]); }));
  (ag || []).forEach(x => { if(x && x.t0) iv.push([+x.t0, +(x.t1 || x.t0)]); });
  const u = [];
  iv.map(p => [Math.max(a, p[0]), Math.min(b, p[1])]).filter(p => p[1] > p[0]).sort((x, y) => x[0] - y[0])
    .forEach(p => { const z = u[u.length - 1]; if(z && p[0] <= z[1]) z[1] = Math.max(z[1], p[1]); else u.push(p.slice()); });
  const pc = [];
  u.forEach(p => { const l = pct(p[0]), r = pct(p[1]), z = pc[pc.length - 1]; if(z && l - z[1] < 0.5) z[1] = r; else pc.push([l, r]); });
  while(pc.length > TLPL_WMAX){
    let m = 1;
    for(let i = 2; i < pc.length; i++) if(pc[i][0] - pc[i - 1][1] < pc[m][0] - pc[m - 1][1]) m = i;
    pc[m - 1][1] = pc[m][1]; pc.splice(m, 1);
  }
  return { sec: u.reduce((n, p) => n + p[1] - p[0], 0), pc };
}
function tlPlBands(row, L, its){
  const pl = row && row.runs ? row.runs[0] : null;   // bands follow the top run only
  if(!pl || !L) return '';
  const S = pl.pr.stages || {}, now = L.now || Date.now() / 1000, pct = L.pct;
  return pl.titles.map(t => {
    const v = pl.lt[t], s = S[plTk(t)];
    if(!v || v.st === 'wait' || !s || !s.t0) return '';
    const end = v.st === 'run' ? now : (s.t1 || s.t0);
    if(end < L.t0) return '';
    const l = Math.max(0, pct(s.t0)), w = Math.max(0.3, pct(end) - l), fam = esc(plgFam(t)), nm = plgShow(t);
    // ⚠The span covers idle waits too: it is drawn faint, the actual work inside it solid (.tlplw).
    const wk = tlPlWork(its, s.ag, s.t0, end, pct);
    const pcs = wk.pc.map(p => { const pl0 = Math.max(0, p[0] - l), pw = Math.max(0, Math.min(w, p[1] - l) - pl0);
      return '<i class=tlplw style="left:' + (pl0 / w * 100).toFixed(2) + '%;width:' + (pw / w * 100).toFixed(2) + '%"></i>'; }).join('');
    let h = '<div class="tlplb pf-' + fam + ' pl-' + esc(v.st) + '" style="left:' + l.toFixed(2) + '%;width:' + w.toFixed(2) + '%"'
      + ' title="' + esc(pl.name + ' · ' + nm + ' · ' + tlPlOc(v.st) + '\n'
        + TV({msg: 'work {w} of {s}', vars: {w: ago(Math.round(wk.sec)), s: ago(Math.max(0, Math.round(end - s.t0)))}})) + '">' + pcs + '</div>';
    if((s.k || 1) >= 2 && s.p0 && s.p0 >= L.t0){
      const fr = Object.keys(s.from || {}).filter(f => s.from[f] > 0);
      const tip = '↺ ' + fr.map(f => TV({msg: '{n} from {s}', vars: {n: s.from[f], s: plgShow(f)}})).concat(TV({msg: 'pass {n}', vars: {n: s.k}})).join(' · ');
      h += '<div class="tlplk pf-' + fam + '" style="left:' + pct(s.p0).toFixed(2) + '%" title="' + esc(nm + ' ' + tip) + '">↺</div>';
    }
    return h;
  }).join('');
}
// Strip click / Enter: open that pipeline in the pipeline view. ⚠Never scroll or centre (plOvPick does neither).
function tlPlGo(el){
  const r = el.closest('.tlr');
  popHide('tlplhp', document.getElementById('tlplhb'));
  setMainView('pipe');
  plOvPick(el.dataset.tlplp || (r ? r.dataset.tlc : '') || '', el.dataset.tlpln || '');
  // ⚠The strip/chip is gone with the timeline, so focus would fall to <body>: land on the picked pipeline, else the tab.
  kbHold('.plw [data-ppk="plsel"]', '.mvb.on');
}
// ⚠paintTl replaces #feed's HTML, so a focused strip is lost; removal fires no reliable focusout, hence focusin/mousedown tracking.
document.addEventListener('focusin', e => { const s = e.target && e.target.closest ? e.target.closest('.tlpl, .tlplx, .tlplc, .tlplhb') : null; TLPL_FO = s ? s.id : ''; });
document.addEventListener('mousedown', e => { if(!(e.target && e.target.closest && e.target.closest('.tlpl, .tlplx, .tlplc, .tlplhb'))) TLPL_FO = ''; }, true);
// Name drop order when a row stepper overflows: done/skip names first, then back/hold, then waiting, farthest from the
// running stage first; running and failed names are never dropped. sts = segment states in order -> indices.
function tlPlDrop(sts){
  const ix = sts.map((st, i) => i), keep = st => st === 'run' || st === 'fail';
  let a = sts.indexOf('run');
  if(a < 0) a = sts.indexOf('fail');
  if(a < 0) a = sts.reduce((m, st, i) => (st !== 'wait' ? i : m), 0);
  const rank = st => (st === 'done' || st === 'skip' ? 0 : st === 'wait' ? 2 : 1);
  return ix.filter(i => !keep(sts[i])).sort((x, y) => (rank(sts[x]) - rank(sts[y])) || (Math.abs(y - a) - Math.abs(x - a)) || (y - x));
}
// ⚠Every segment stays visible: names fall back whole -> 2 chars + «…» (CSS, .ln) -> none (.nn, 22px, name in title).
function tlPlFit(el){
  const segs = [...el.children];
  segs.forEach(s => s.classList.remove('nn'));
  if(el.scrollWidth <= el.clientWidth + 1) return;
  const sts = segs.map(s => ((/(?:^| )pl-(\w+)/.exec(s.className) || [])[1]) || 'wait');
  const fits = () => el.scrollWidth <= el.clientWidth + 1, gone = [];
  for(const i of tlPlDrop(sts)){
    segs[i].classList.add('nn'); gone.push(i);
    if(fits()) break;
  }
  // Dropping a name lets the long ones before it widen again: give back the latest drops that still fit.
  for(let k = gone.length - 2; k >= 0; k--){ segs[gone[k]].classList.remove('nn'); if(!fits()) segs[gone[k]].classList.add('nn'); }
}
// One observer for the row steppers: refits on paint, window/name-column resize and --fs changes.
let TLPL_RO = null;
function tlPlFitAll(box){
  const els = box.querySelectorAll('.tlnm .tlpst');
  if(typeof ResizeObserver === 'undefined'){ els.forEach(tlPlFit); return; }
  if(!TLPL_RO) TLPL_RO = new ResizeObserver(es => es.forEach(e => { const st = e.target.querySelector('.tlpst'); if(st) tlPlFit(st); }));
  TLPL_RO.disconnect();
  els.forEach(e => TLPL_RO.observe(e.parentNode));
}
function tlPlWire(box){
  tlNmColWire(box);   // name-column grip (74d)
  tlPlFitAll(box);
  box.querySelectorAll('.tlpl[data-tlpln], .tlplc[data-tlpln]').forEach(tlPlChipWire);   // row strips (+ run chips in the popover)
  const hb = box.querySelector('#tlplhb');
  if(hb) hb.onclick = e => { e.stopPropagation(); tlPlHeadToggle(hb); };   // native button: Enter/Space click
  // ⚠paintTl rebuilt the header: refill an open popover from the new runs, close it when none are left.
  const hp = document.getElementById('tlplhp');
  if(hp && !hp.hidden){ if(hb) tlPlHeadFill(hp); else tlPlHeadClose(false); }
  box.querySelectorAll('.tlplx[data-tlplx]').forEach(b => {
    b.onclick = e => { e.stopPropagation(); TLPL_FO = b.id; tlPlExp(b.dataset.tlplx); };
    b.onkeydown = e => e.stopPropagation();   // native Enter/Space click; keep the row's Enter (opens the work log) out
  });
  const a = document.activeElement;
  if(TLPL_FO && (!a || a === document.body)){
    const f = document.getElementById(TLPL_FO);
    if(f && (box.contains(f) || (hp && hp.contains(f)))) f.focus({ preventScroll: true });
  }
}
function tlPlChipWire(s){
  s.onclick = e => { e.stopPropagation(); tlPlGo(s); };
  s.onkeydown = e => { if(e.key === 'Enter' || e.key === ' '){ e.preventDefault(); e.stopPropagation(); tlPlGo(s); } };
}
