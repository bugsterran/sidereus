// «Since your last visit» strip above the Watch canvas (48 plMainBody): runs finished, commits after a pass, sessions waiting, sessions ended.
// ⚠Metadata only (rule 1): an item shows path · sid8 · pipeline name · stage title · verdict · hh:mm — never lab, agent labels, targ or why.
// ⚠localStorage, not UIS (app-head.js keeps sidereus.visit out of the UIS migration): {seen, open:{since, at}} is per browser, shared by its tabs.
const VISIT_KEY = 'sidereus.visit';
const VISIT_GAP_S = 600, VISIT_SEEN_S = 30;   // away >= 10 min opens a window; `seen` is refreshed at most every 30 s while visible
const VISIT_KEEP_S = 6 * 3600;   // = sidereus/pl_runs.py PLR_KEEP_S: older runs are gone from the rows
const VISIT_PAST_MAX = 5;        // = sidereus/pl_runs.py PLR_PAST_MAX: earlier runs per name, oldest dropped first
const VISIT_RUNS_MAX = 6;        // = sidereus/pl_runs.py PLR_MODEL_MAX: runs per session row
let VISIT = { ready: false, away: false, w: 0, html: '', data: null, pop: null };
// -> {seen, open, vd} | null when storage throws (the strip stays off). vd = the --demo visitDemo stamp already opened (or dismissed).
function visitLoad(){
  try{
    const v = JSON.parse(localStorage.getItem(VISIT_KEY) || 'null');
    if(!v || typeof v !== 'object') return { seen: 0, open: null, vd: null };
    const o = v.open, ok = o && typeof o === 'object' && +o.since > 0 && +o.at >= +o.since;
    return { seen: +v.seen > 0 ? +v.seen : 0, open: ok ? { since: +o.since, at: +o.at } : null, vd: typeof v.vd === 'number' ? v.vd : null };
  }catch(e){ return null; }
}
function visitSave(r){
  const o = { seen: r.seen, open: r.open || null };
  if(typeof r.vd === 'number') o.vd = r.vd;
  try{ localStorage.setItem(VISIT_KEY, JSON.stringify(o)); return true; }catch(e){ softErr('ls', e); return false; }
}
// Run verdict: fail if any stage failed; pass only for a run that ended, was not stopped, and whose `cur` is the definition's last stage done|skip.
// ⚠An archived (past) run with `stop` null was archived before the hook kept it: never pass, since _close_stale turns a stopped/idle cur stage into done.
// ⚠Equals sidereus/state_v1.py verdict (GET /api/v1/state runs[].verdict); change both — vectors in tests/fixtures/verdict_vectors.json.
function visitVerdict(S, end, stop, titles, cur, past){
  const v = Object.values(S || {}).filter(s => s && typeof s === 'object');
  if(v.some(s => s.o === 'fail')) return 'fail';
  if(past && stop == null) return 'unknown';
  const last = Array.isArray(titles) && titles.length ? titles[titles.length - 1] : null, c = last != null && cur === last ? (S || {})[cur] : null;
  return end > 0 && !stop && c && typeof c === 'object' && (c.o === 'done' || c.o === 'skip') ? 'pass' : 'unknown';
}
// Stage titles of a pipeline definition from 48 PLS.data (as 48b plLiveRun reads it); null when not loaded = verdict unknown.
// ⚠PLS.data holds only the selected project: other projects read 48n's own VISIT_DEFS (never written into PLS.data, 48 owns it).
const VISIT_DEFS = {};   // proj -> {at, map: {name: titles}} | {at, busy} | {at, err}
const VISIT_DEFS_TTL_S = 600, VISIT_DEFS_ERR_S = 60;
function visitDefs(proj, name){
  const d = typeof PLS === 'object' && PLS && PLS.data ? PLS.data[proj] : null;
  const p = d && [].concat(d.pipelines || [], d.borrowed || []).find(x => x && x.name === name);   // borrowed rows share the pipeline row shape (pipeline._row)
  if(p && Array.isArray(p.stages) && p.stages.length) return p.stages.map(s => s && s.title);
  const c = VISIT_DEFS[proj];
  return c && c.map && Object.prototype.hasOwnProperty.call(c.map, name) ? c.map[name] : null;
}
// One /api/pipelines fetch per project (in-flight guard; a failure waits VISIT_DEFS_ERR_S); the next visitTick recomputes with it.
async function visitDefsLoad(proj){
  const c = VISIT_DEFS[proj], t0 = Date.now() / 1000;
  if(!proj || (c && (c.busy || t0 - c.at < (c.map ? VISIT_DEFS_TTL_S : VISIT_DEFS_ERR_S)))) return;
  VISIT_DEFS[proj] = { at: t0, busy: true };
  let v = null;
  try{ v = await getJSON('/api/pipelines?proj=' + encodeURIComponent(proj)); }catch(e){ v = null; }
  if(v && v.ok && Array.isArray(v.pipelines)){
    const map = {};
    v.pipelines.concat(Array.isArray(v.borrowed) ? v.borrowed : []).forEach(p => { if(p && typeof p.name === 'string' && Array.isArray(p.stages) && p.stages.length) map[p.name] = p.stages.map(s => s && s.title); });
    VISIT_DEFS[proj] = { at: Date.now() / 1000, map };
  } else VISIT_DEFS[proj] = { at: Date.now() / 1000, err: true };
}
// Pure: SESS rows + {at, resp} (attention time and attnRows().resp, null = unknown) -> counts for (since, at]; defs(proj, name) -> titles|null.
// ⚠Runs and commits are deduped by sid|name|rid(|stamp); waiting is live; attn null leaves waiting/ended null (unknown, never 0).
// ⚠cap measures from `now` (server keep runs from now, pl_runs PLR_KEEP_S), not from the frozen `at`.
function visitCollect(sess, attn, since, at, defs, now){
  const inW = t => typeof t === 'number' && t > since && t <= at, after = t => typeof t === 'number' && t > since;
  const runs = [], cms = [], sr = new Set(), sc = new Set();
  let cap = (typeof now === 'number' ? now : at) - since > VISIT_KEEP_S;
  for(const x of Array.isArray(sess) ? sess : []){
    if(!x || typeof x !== 'object') continue;
    const rows = (Array.isArray(x.plrun) ? x.plrun : []).filter(r => r && typeof r === 'object' && r.name);
    if(rows.length >= VISIT_RUNS_MAX && after(Math.min(...rows.map(r => +r.end || +r.t1 || 0)))) cap = true;   // older runs may be cut
    for(const r of rows){
      const proj = String(r.proj || x.cwd || ''), sid = String(r.sid || x.sid || ''), cur = r.rid != null ? r.rid : r.t0;
      const titles = typeof defs === 'function' ? defs(proj, String(r.name)) : null;
      const one = (q, past) => {
        const rid = q.rid != null ? q.rid : q.t0, end = +q.end || (past ? +q.t1 || 0 : 0), S = q.stages && typeof q.stages === 'object' ? q.stages : {};
        // ⚠The verdict takes the stamped `end` only: the t1 fallback dates an idle-replaced past run but never proves it finished.
        const stop = past && q.stop == null ? null : +q.stop || 0, vd = visitVerdict(S, +q.end || 0, stop, titles, q.cur, past), k = sid + '|' + r.name + '|' + rid;
        const base = { sid, name: String(r.name), proj, rid, cur, past, stage: String(q.cur || ''), vd };
        if(inW(end) && !sr.has(k)){ sr.add(k); runs.push(Object.assign({ k: 'run', t: end }, base)); }
        if(vd === 'fail' || (vd !== 'pass' && (end > 0 || stop))) return;   // commits count in a passed run or a still-open one only
        const st = Object.values(S).filter(s => s && typeof s === 'object'), dn = st.filter(s => s.o === 'done' && typeof s.t1 === 'number').map(s => s.t1);
        for(const s of st) for(const c of Array.isArray(s.cm) ? s.cm : []){
          const ck = k + '|' + c;
          if(!inW(c) || sc.has(ck) || !dn.some(t => t <= c)) continue;
          sc.add(ck); cms.push(Object.assign({ k: 'cm', t: c }, base));
        }
      };
      one(r, false);
      const ps = (Array.isArray(r.past) ? r.past : []).filter(q => q && typeof q === 'object' && (q.rid != null ? q.rid : q.t0) !== cur);
      ps.forEach(q => one(q, true));
      if(ps.length >= VISIT_PAST_MAX && after(Math.min(...ps.map(q => +q.end || +q.t1 || 0)))) cap = true;
    }
  }
  const resp = attn && Array.isArray(attn.resp) ? attn.resp : null;
  const wait = resp ? resp.filter(w => w && w.r).map(w => ({ k: 'wait', sid: String(w.r.sid || ''), proj: String(w.r.cwd || ''), t: +w.since || 0 })) : null;
  const ref = attn && typeof attn.at === 'number' ? attn.at : null, ended = ref == null ? null : [], se = new Set();
  if(ended) for(const x of Array.isArray(sess) ? sess : []){
    if(!x || (x.state !== 'done' && x.state !== 'gone') || typeof x.ageSec !== 'number' || !isFinite(x.ageSec)) continue;
    const t = ref - x.ageSec, key = x.sid || 'cwd:' + (x.cwd || '');
    if(!inW(t) || se.has(key)) continue;
    se.add(key); ended.push({ k: 'end', sid: String(x.sid || ''), proj: String(x.cwd || ''), t });
  }
  const by = (a, b) => b.t - a.t, nv = v => runs.filter(r => r.vd === v).length;
  [runs, cms, wait || [], ended || []].forEach(l => l.sort(by));
  const fresh = !!wait && wait.some(w => w.t > since);
  return { since, at, cap, runs, pass: nv('pass'), fail: nv('fail'), unk: nv('unknown'), cms, wait, ended,
    changed: runs.length > 0 || cms.length > 0 || (!!ended && ended.length > 0) || fresh };
}
function visitVdLab(v){ return v === 'pass' ? T('gate passed') : v === 'fail' ? T('gate failed') : T('verdict unknown'); }
// Strip HTML; '' when nothing changed. ⚠Absolute hh:mm only: a relative «ago» changes every poll and defeats paintPipe's unchanged-HTML skip.
function visitHtml(d){
  if(!d || !d.changed) return '';
  const w = t => hhmm(t, { date: 'other' }), cnt = (n, cap) => n == null ? '?' : String(n) + (cap ? '+' : '');
  const capTip = d.cap ? ' — ' + T('Older runs may be missing: the server keeps 6 hours and 5 earlier runs per pipeline') : '';
  const btn = (key, lab, n, cap, extra, tip) => '<button type=button class="plvsc' + (n ? '' : ' nil') + '" data-plvs="' + key + '"' + (n ? '' : ' disabled')
    + ' title="' + esc(tip) + '">' + esc(lab) + ' <b>' + esc(cnt(n, cap)) + '</b>' + extra + '</button>';
  const rTip = T('Gate passed {p} · failed {f} · unknown {u}').replace('{p}', d.pass).replace('{f}', d.fail).replace('{u}', d.unk)
    + (d.unk ? ' — ' + T('unknown = stopped, not at its last stage, an earlier archived run (never graded pass) or no definition loaded') : '') + capTip;
  const rx = (d.pass ? ' <span class=ok>✓' + d.pass + '</span>' : '') + (d.fail ? ' <span class=bad>✕' + d.fail + '</span>' : '');
  const unk = T('Unknown — attention data did not arrive');
  return '<div class=plvs role=status><b>' + esc(T('Since your last visit')) + '</b><span class=plvst>' + esc(w(d.since) + ' – ' + w(d.at)) + '</span>'
    + btn('runs', T('Runs finished'), d.runs.length, d.cap, rx, rTip)
    + btn('cms', T('Commits after a pass'), d.cms.length, d.cap, '', T('Commits made after a stage passed, in runs with no failed stage') + capTip)
    + btn('wait', T('Waiting on a person'), d.wait ? d.wait.length : null, false, '', d.wait ? T('Sessions that need your response now') : unk)
    + btn('end', T('Sessions ended'), d.ended ? d.ended.length : null, false, '', d.ended ? T('Sessions that ended while you were away') : unk)
    + '<button type=button class=plvsx data-plvsx>' + esc(T('Dismiss')) + '</button></div>';
}
function visitStripHtml(){ return VISIT.html; }   // 48 plMainBody, right under the .pltop row
// One popover row: folder name · sid8 · pipeline · stage, verdict, hh:mm; full path in the tooltip. All values esc(), never T().
function visitItemHtml(it, i){
  const p = String(it.proj || ''), base = p.replace(/[\\/]+$/, '').split(/[\\/]/).pop() || p;
  const lab = [base, it.sid ? it.sid.slice(0, 8) : '', it.name || '', it.stage || ''].filter(Boolean).join(' · ');
  return '<button type=button class=plapki role=menuitem data-plvi="' + i + '" title="' + esc(p) + '"><span>' + esc(lab) + '</span>'
    + (it.vd ? '<i class="plvsv ' + (it.vd === 'pass' || it.vd === 'fail' ? it.vd : 'unknown') + '">' + esc(visitVdLab(it.vd)) + '</i>' : '')
    + '<i class=plvsw>' + esc(hhmm(it.t, { date: 'other' })) + '</i></button>';
}
function visitList(key){ const d = VISIT.data; return !d ? [] : (key === 'runs' ? d.runs : key === 'cms' ? d.cms : key === 'wait' ? d.wait : key === 'end' ? d.ended : null) || []; }
function visitPopClose(){ const el = document.getElementById('plvsm'); if(el) el.remove(); VISIT.pop = null; }
// One item opens directly; two or more open a fixed menu on body (like 48b #plrvm) — never shifts the canvas.
function visitOpen(key, rc){
  const L = visitList(key).slice();
  visitPopClose();
  if(!L.length) return;
  if(L.length === 1){ visitGo(L[0]); return; }
  const el = document.createElement('div');
  el.id = 'plvsm'; el.className = 'plapk plvsm'; el.setAttribute('role', 'menu');
  el.innerHTML = L.map(visitItemHtml).join('');
  el.style.left = Math.max(4, Math.min(rc.left, window.innerWidth - 404)) + 'px'; el.style.top = Math.round(rc.bottom + 4) + 'px';
  document.body.appendChild(el); VISIT.pop = L;
}
// Run/commit -> its Watch result pane (a past run via PLS.runSel); waiting -> its «Attention» row; ended -> its session row.
function visitGo(it){
  if(!it) return;
  if(it.k === 'run' || it.k === 'cm'){
    if(mainView !== 'pipe') setMainView('pipe');
    plOvPick(it.proj, it.name, it.sid);   // ⚠clears runSel: set the pin after it
    // Pin head or past: plOvPick/plLiveRun alone open another session's live run of the same name (48b plPinRun).
    PLS.runSel = { sid: it.sid, name: it.name, rid: it.rid, cur: it.cur, pin: true }; plPaint();
    return;
  }
  if(it.k === 'wait'){ let ok = false; try{ ok = actAttnGo({ sid: it.sid, cwd: it.proj }); }catch(e){ softErr('visitWait', e); } if(ok) return; }
  cpGo((SESS || []).find(s => s && it.sid && s.sid === it.sid) || { sid: it.sid, cwd: it.proj, state: 'done' });
}
function visitSet(d){
  VISIT.data = d;
  const h = visitHtml(d);
  if(h === VISIT.html) return;
  const tog = !h !== !VISIT.html;
  VISIT.html = h;
  if(!h) visitPopClose();
  plPaint(true);
  if(tog) plFitSoon();   // the strip's come-and-go changes the canvas height
}
// Poll hook (95-poll, after ATTN): gap check against the shared `seen`, throttled `seen` refresh, strip refresh. Hidden tab: nothing.
// ⚠Any visible tab refreshes `seen`, so a gap means no tab of this browser was visible for 10 min (incl. sleep / server outage).
function visitTick(s){
  if(ISPOP || ISWP || ISBP || document.hidden) return;
  const rec = visitLoad();
  if(!rec){ visitSet(null); return; }
  const now = Date.now() / 1000, a = s && s.attention;
  const attn = a && typeof a === 'object' ? { at: a.at, resp: attnRows().resp } : null;
  const srv = attn && typeof attn.at === 'number' ? attn.at : now;   // server clock for the keep cap (demo clock under --demo)
  let open = rec.open, dv = rec.vd;
  const vd = s && typeof s.visitDemo === 'number' && isFinite(s.visitDemo) ? s.visitDemo : null;
  // --demo only: open (visitDemo, attention.at] on the demo clock so counts are deterministic; keyed on the stamp, so Dismiss sticks until a demo restart
  if(vd != null && !open && dv !== vd && attn && typeof attn.at === 'number' && attn.at > vd){ open = { since: vd, at: attn.at }; dv = vd; }
  else if(!rec.seen) open = null;   // first visit: seed only
  else if(now - rec.seen >= VISIT_GAP_S){
    if(open) open = { since: open.since, at: now };   // still not dismissed: widen the same window
    else if(visitCollect(SESS, attn, rec.seen, now, visitDefs, srv).changed) open = { since: rec.seen, at: now };
  }
  const d = open ? visitCollect(SESS, attn, open.since, open.at, visitDefs, srv) : null;   // ⚠re-read each tick: another tab's Dismiss closes it here too
  if(d && !d.changed && attn && typeof attn.at === 'number') open = null;   // missing attention = wait/ended unknown: keep it   // ⚠a window held only by a waiting row ends with it; kept, the next absence widened it from the old since
  if(open && typeof getJSON === 'function') new Set(d.runs.filter(r => r.vd === 'unknown' && !visitDefs(r.proj, r.name)).map(r => r.proj)).forEach(visitDefsLoad);
  if(!rec.seen || now - rec.seen >= VISIT_GAP_S || now - VISIT.w >= VISIT_SEEN_S || open !== rec.open || dv !== rec.vd){ visitSave({ seen: now, open, vd: dv }); VISIT.w = now; }
  VISIT.ready = true;
  visitSet(open ? d : null);
}
function visitDismiss(){
  const now = Date.now() / 1000, r = visitLoad();
  visitSave({ seen: now, open: null, vd: r ? r.vd : null }); VISIT.w = now;
  visitPopClose(); visitSet(null);
}
// ⚠Only after the first visible tick: a hide/close before it would overwrite `seen` and lose the gap unseen.
function visitAway(){
  if(!VISIT.ready) return;
  const r = visitLoad();
  if(r) visitSave({ seen: Date.now() / 1000, open: r.open, vd: r.vd });
}
if(!ISPOP && !ISWP && !ISBP){
  VISIT.away = document.hidden;
  document.addEventListener('visibilitychange', () => { if(document.hidden){ visitAway(); VISIT.away = true; } else VISIT.away = false; });
  window.addEventListener('pagehide', () => { if(!VISIT.away) visitAway(); });   // ⚠a tab hidden before closing already saved; closing must not move `seen`
  document.addEventListener('click', e => {
    const t = e.target && e.target.closest ? e.target : null;
    if(!t) return;
    if(t.closest('[data-plvsx]')){ visitDismiss(); return; }
    const c = t.closest('[data-plvs]');
    if(c){ visitOpen(c.dataset.plvs, c.getBoundingClientRect()); return; }
    const i = t.closest('#plvsm [data-plvi]');
    if(i){ const it = VISIT.pop && VISIT.pop[+i.dataset.plvi]; visitPopClose(); visitGo(it); }
  });
  document.addEventListener('pointerdown', e => { if(VISIT.pop && !(e.target.closest && e.target.closest('#plvsm,[data-plvs]'))) visitPopClose(); }, true);
  document.addEventListener('keydown', e => { if(e.key === 'Escape' && VISIT.pop) visitPopClose(); });
}
