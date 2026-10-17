// Pipeline-run strip at the bottom of an agent's or session's work log: SESS[].plrun (metadata only — titles, states, counts, labels).
// The popup polls /api/state itself (95-poll), so SESS here is its own copy, same source as the main window.
const WP_TAG = /\[pl:([^\/\]]{1,60})\/([^\]]{1,80})\]/;
let WPCH = null;          // open inline agent chooser {k: tab key, t: stage title} (null = none)
const WPHITS = {};        // tab key -> last painted {run, title, cwd}; click handlers resolve against it
const WPPL = {};          // proj -> stage titles per pipeline name, fetched once in the popup (PLS.data is main-window only)
// Live = no end and a stage still «run» (same test as the timeline, 74c); anything else draws as an ended (.fin) stepper.
function wpLive(r){ return !!r && !r.end && plPrLive(r); }
// Runs holding this agent: every run whose stage ag has its tid/aid (live first, then newest t1; `runs` stacks them);
// else the [pl:name/title] tag of the agent's description, newest run.
function wpRunOf(cwd, tid, desc){
  const id = String(tid || '').split('|')[0];
  const rows = (typeof SESS !== 'undefined' && SESS) || [];
  const hits = [];
  if(id) rows.forEach(x => ((x && x.plrun) || []).forEach(r => {
    const t = Object.keys((r && r.stages) || {}).find(k => ((r.stages[k] && r.stages[k].ag) || []).some(a => a && (a.tid === id || a.aid === id)));
    if(t) hits.push({ run: r, title: t, cwd: x.cwd || cwd });
  }));
  if(hits.length){
    hits.sort((a, b) => (wpLive(b.run) - wpLive(a.run)) || ((+b.run.t1 || 0) - (+a.run.t1 || 0)));
    return { run: hits[0].run, title: hits[0].title, cwd: hits[0].cwd, runs: hits };
  }
  let best = null;
  const m = WP_TAG.exec(String(desc || ''));
  if(!m) return null;
  rows.forEach(x => ((x && x.plrun) || []).forEach(r => {
    if(r && r.name === m[1] && (!best || (+r.t0 || 0) > (+best.run.t0 || 0))) best = { run: r, title: m[2], cwd: x.cwd || cwd };
  }));
  return best;
}
// Stage order: the pipeline file's stages (PLS.data in the main window, WPPL in the popup), then any extra run keys.
function wpOrder(run){
  const st = Object.keys((run && run.stages) || {});
  const pd = (typeof PLS !== 'undefined' && PLS.data[run.proj]) || null;
  const p = pd ? ((pd.pipelines || []).find(q => q && q.name === run.name) || {}).stages : null;
  const file = p ? p.map(s => s && s.title).filter(Boolean) : ((WPPL[run.proj] || {})[run.name] || []);
  return file.concat(st.filter(t => !file.includes(t)));
}
function wpLabel(o){
  return ({ run: T('running', 'exec'), done: T('done'), skip: T('skipped'), fail: T('failed'),
            back: T('looped back'), hold: T('paused'), wait: T('waiting') })[o] || o;
}
// Reason of a «hold» stage (pl_runs._close_stale `why`), '' otherwise.
function plWhy(s){ return s && s.o === 'hold' ? ({ ask: T('waiting on a question'), perm: T('waiting for approval'), end: T('session ended'), idle: T('no tagged work for 10 min') })[s.why] || '' : ''; }
// Openable work-log id of a stage agent (aid survives resumes); the 'main' marker has none.
function wpAgId(a){
  if(!a || a.aid === 'main') return '';
  const aid = String(a.aid || '');
  return /^a[0-9a-f]{6,40}$/.test(aid) ? aid : String(a.tid || '');
}
function wpAgs(s){ return ((s && s.ag) || []).filter(a => wpAgId(a)).slice().sort((x, y) => (+y.t0 || 0) - (+x.t0 || 0)); }
function wpStripHtml(run, title, chT){
  if(!run || !run.stages) return '';
  // Same stepper as the timeline row (plStepper, 74c); .me = this agent's stage, progress runs up to the run's current stage.
  const ord = wpOrder(run), oc = t => (run.stages[t] && run.stages[t].o) || 'wait';
  const cur = ord.find(t => oc(t) === 'run') || run.cur || ord.filter(t => oc(t) !== 'wait').pop() || '';
  const chips = plStepper(ord.map(t => {
    const s = run.stages[t] || { o: 'wait' }, o = !TLPL_ICON[s.o] ? 'wait' : s.o === 'run' && !wpLive(run) ? 'done' : s.o;   // ended: no «run» look (as 74c)
    const fr = Object.keys(s.from || {}), nb = fr.reduce((k, f) => k + (+s.from[f] || 0), 0);
    const ags = wpAgs(s);
    const tip = t + ' · ' + wpLabel(o) + (plWhy(s) ? ' (' + plWhy(s) + ')' : '') + (nb ? ' · ↺ ' + fr.map(f => f + ' ×' + s.from[f]).join(', ') : '')
      + (ags.length ? ' · ' + T('agents ') + ags.length : '');
    return { st: o, nm: t, tip, cls: (t === title ? ' me' : '') + (ags.length ? '' : ' na'), extra: nb ? '<em>↺' + nb + '</em>' : '',
      attr: (ags.length ? ' role=button tabindex=0' : '') + ' data-wpls="' + esc(t) + '"' };
  }), ord.indexOf(cur), 'lg' + (wpLive(run) ? '' : ' fin'));
  // Ended run: same outcome label as the timeline row (tlPlEnd, 74c); a «run» stage left by the end counts as cut.
  const fin = !wpLive(run), end = fin ? tlPlEnd({ pr: run, titles: ord, fin, now: Date.now() / 1000, lt: Object.fromEntries(ord.map(t => {
    const o = oc(t);
    return [t, o === 'run' ? { st: 'done', cut: 1 } : { st: TLPL_ICON[o] ? o : 'wait' }];
  })) }, cur) : '';
  const ch = chT && run.stages[chT] ? wpAgs(run.stages[chT]) : [];
  const chooser = ch.length > 1 ? '<div class=wplc>' + ch.map(a => {
    const ty = String(a.lab || '').split(': ')[0] || String(wpAgId(a)).slice(-6);
    return '<span role=button tabindex=0 data-wplc="' + esc(wpAgId(a)) + '">' + (a.run ? '● ' : '') + esc(ty)
      + ' · ' + esc(a.t0 ? CLK(new Date(a.t0 * 1000)) : '') + '</span>';
  }).join('') + '</div>' : '';
  return '<div class=wpl data-wplp="' + esc(run.proj || '') + '" data-wpln="' + esc(run.name) + '">'
    + '<u>' + esc(T('Pipeline') + ' · ' + run.name) + '</u>' + chips + end
    + (run.proj ? '<button class=wplj data-wplj=1>' + esc(T('Show in pipeline')) + '</button>' : '')
    + '</div>' + chooser;
}
// Session (orchestrator) tab: its own row's plrun — open runs newest first (≤3 stacked), else the newest ended one.
function wpSessRuns(cwd, tid){
  const sid = tidSid(tid), rows = (typeof SESS !== 'undefined' && SESS) || [];
  // ⚠Plain sess:<cwd> only from old saved tabs = the server's newest transcript: match it by the smallest ageSec (no mtime on the row).
  const age = r => (typeof r.ageSec === 'number' ? r.ageSec : Infinity);
  const x = sid ? rows.find(r => r && r.sid === sid)
    : rows.filter(r => r && r.cwd === cwd && (!r.plat || r.plat === 'cc')).reduce((b, r) => (!b || age(r) < age(b) ? r : b), null);
  const rs = ((x && x.plrun) || []).filter(r => r && r.stages).sort((a, b) => (+b.t0 || 0) - (+a.t0 || 0));
  if(!rs.length) return null;
  const open = rs.filter(r => !r.end), pick = open.length ? open.slice(0, 3) : rs.slice(0, 1);
  const cur = r => r.cur || Object.keys(r.stages).find(t => r.stages[t] && r.stages[t].o === 'run') || '';
  const runs = pick.map(r => ({ run: r, title: cur(r) }));
  return { run: runs[0].run, title: runs[0].title, cwd: x.cwd || cwd, runs: runs };
}
// Run(s) of tab `k` (data d = its work log): agent tab = its run, session tab = wpSessRuns; null for ext tabs, {hit: null} when none.
function wpHitOf(k, d){
  const tab = (typeof wtabs !== 'undefined' ? wtabs : []).find(x => x.key === k);
  const tid = tab ? String(tab.tid || '') : '';
  if(!tid || tid.indexOf('ext:') === 0) return null;
  const hit = tid.indexOf('sess:') === 0 ? wpSessRuns(tab.cwd, tid) : wpRunOf(tab.cwd, tid, d && d.ok ? d.desc : '');
  WPHITS[k] = hit;
  ((hit && hit.runs) || (hit ? [hit] : [])).forEach(x => {
    const p = x.run.proj;
    if(p && !WPPL[p] && !(typeof PLS !== 'undefined' && PLS.data[p])) wpFetchOrder(p);
  });
  return { hit: hit };
}
// Strip body + a small signature of what it shows (order, outcomes, counts, agents, open chooser, language).
function wpView(k, hit){
  if(!hit) return { html: '', sig: '' };
  const rs = hit.runs || [{ run: hit.run, title: hit.title }];
  const chOf = i => WPCH && WPCH.k === k && (WPCH.i || 0) === i ? WPCH.t : '';
  const sig = JSON.stringify([LANG, rs.map((x, i) => [x.run.name, x.run.sid, x.run.t0, x.title, chOf(i), wpOrder(x.run).map(t => {
    const s = x.run.stages[t] || {};
    return [t, s.o || 'wait', s.n || 0, s.from || {}, ((s.ag) || []).map(a => [wpAgId(a), !!a.run])];
  })])]);
  return { html: rs.map((x, i) => wpStripHtml(x.run, x.title, chOf(i))).join(''), sig: sig };
}
// Hook for 35b workPaint and each split pane: a wrapper per agent/session tab (empty while no run) so wpRefresh can fill it later.
function wpPlrunHook(d, key){
  const k = key === undefined ? wtPanes[0] : key, h = wpHitOf(k, d);
  if(!h) return '';
  const v = wpView(k, h.hit);
  return '<div class=wplw data-wplk="' + esc(k) + '" data-sig="' + esc(v.sig) + '">' + v.html + '</div>';
}
// Redraws only strips whose signature changed — the agent log and its scroll are left alone. Returns the redraw count.
function wpRefresh(root){
  let n = 0;
  ((root && root.querySelectorAll('.wplw[data-wplk]')) || []).forEach(el => {
    const k = el.dataset.wplk, h = wpHitOf(k, (typeof wtData !== 'undefined' && wtData[k]) || null);
    const v = wpView(k, h ? h.hit : null);
    if(el.dataset.sig === v.sig) return;
    // ⚠a redraw after the first scroll-to-bottom grows the log; stay pinned to the end if the reader was there
    const sc = el.closest('.wpb') || document.getElementById('wkmb');
    const end = !!sc && sc.scrollHeight - sc.scrollTop - sc.clientHeight < 40;
    el.dataset.sig = v.sig; el.innerHTML = v.html; n++;
    if(end) sc.scrollTop = sc.scrollHeight;
  });
  return n;
}
// ⚠95-poll has no popup hook; a 2.5 s tick (the poll interval) re-reads the SESS it refreshed. Cheap: signature compare only.
if(ISWP) setInterval(() => { try{ wpRefresh(document); }catch(e){ softErr('wpRefresh', e); } }, 2500);
function wpFetchOrder(proj){
  WPPL[proj] = {};        // ⚠set before the fetch: one request per proj even if it fails
  getJSON('/api/pipelines?proj=' + encodeURIComponent(proj)).then(v => {
    const m = {};
    ((v && v.pipelines) || []).forEach(p => { if(p && p.name) m[p.name] = (p.stages || []).map(s => s && s.title).filter(Boolean); });
    WPPL[proj] = m; wpRefresh(document);
  }).catch(e => softErr('wpOrder', e));
}
// Cross-window jump: the popup writes sidereus.pljump; the main window picks it up within 10 s, else ignores it.
function wpJumpRecv(raw, now){
  let v; try{ v = JSON.parse(raw || ''); }catch(e){ return null; }
  if(!v || typeof v.proj !== 'string' || typeof v.name !== 'string' || !v.proj || !v.name || typeof v.at !== 'number') return null;
  return now - v.at >= 0 && now - v.at <= 10000 ? { proj: v.proj, name: v.name } : null;
}
// ⚠localStorage is writable by any same-origin page: only jump to a project the main window already knows.
function wpJumpKnown(proj){
  if(typeof PLS !== 'undefined' && (PLS.data[proj] || ((PLS.projs && PLS.projs.projects) || []).some(x => x && x.path === proj))) return true;
  return ((typeof SESS !== 'undefined' && SESS) || []).some(x => x && (x.cwd === proj || (x.plrun || []).some(r => r && r.proj === proj)));
}
document.addEventListener('click', e => {
  const t = e.target && e.target.closest ? e.target : null;
  const w = t && t.closest('.wplw[data-wplk]'), k = w ? w.dataset.wplk : '', hit = w ? WPHITS[k] : null;
  if(!hit) return;
  const j = t.closest('[data-wplj]');
  if(j){
    const w = j.closest('.wpl');
    try{ localStorage.setItem('sidereus.pljump', JSON.stringify({ proj: w.dataset.wplp, name: w.dataset.wpln, at: Date.now() })); }catch(err){ softErr('pljump', err); }
    try{ if(window.opener) window.opener.focus(); }catch(err){ softErr('pljumpFocus', err); }
    return;
  }
  const c = t.closest('[data-wplc]');
  if(c){ WPCH = null; openAgent(hit.cwd, c.dataset.wplc); return; }
  const s = t.closest('[data-wpls]');
  if(!s) return;
  // Stacked session strips: the clicked .wpl's position picks its run.
  const i = Math.max(0, Array.prototype.indexOf.call(w.querySelectorAll('.wpl'), s.closest('.wpl')));
  const run = ((hit.runs || [])[i] || hit).run, st = s.dataset.wpls, ags = wpAgs(run.stages[st]);
  if(ags.length === 1){ WPCH = null; openAgent(hit.cwd, wpAgId(ags[0])); }
  else if(ags.length > 1){ WPCH = WPCH && WPCH.k === k && WPCH.t === st && (WPCH.i || 0) === i ? null : { k: k, t: st, i: i }; wpRefresh(document); }
});
document.addEventListener('keydown', e => {
  if(e.key === 'Enter' && e.target && e.target.matches && e.target.matches('[data-wpls],[data-wplc]')){ e.preventDefault(); e.target.click(); }
});
window.addEventListener('storage', e => {
  if(e.key !== 'sidereus.pljump' || ISWP || ISPOP) return;
  const j = wpJumpRecv(e.newValue, Date.now());
  if(!j || !wpJumpKnown(j.proj)) return;
  setMainView('pipe');      // ⚠no scroll / centre — plOvPick only repaints
  plOvPick(j.proj, j.name);
});
