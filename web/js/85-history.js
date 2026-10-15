// ── History tab — past sessions (by date) ──────────────────────────────────────────────
// ★Why needed: the list is cut at `max_age_h=12`, so **ended sessions older than 12h vanish entirely**.
// There was no place on screen to look back (common in ADEs — Conductor Archive · Codex task history).
// ⚠Fetched **only when this view opens**. Do not attach to the 2.5s poll (the server also applies a 60s cache).
// ⚠Rows carry **metadata only** — the source is the token index, so there is no path for conversation content.
let HIST = null, histDays = 7, histBusy = 0, histAt = 0, histWant = 0;
const HIST_STEPS = [7, 14, 30, 90];   // range toggle, same shape as the retro tab's 7/30 (was a grow-only «Show more»)
// ⚠Days received via `want` go into `histDays` **only after a successful load** — setting it first leaves a stale `HIST`
// with just the header saying "last 90 days". If already running, return `false` so the caller can report it.
function loadHist(force, want){
  const d = want || histDays;
  if(histBusy) return false;
  if(!force && HIST && HIST.days === d && Date.now() - histAt < 60000){
    histDays = d; if(mainView === 'hist') paintHist(); return true; }
  histBusy = 1; histWant = d;
  if(mainView === 'hist') paintHist();      // the picked range lights up at once, with «Loading…»
  getJSON('/api/history?days=' + d)
    .then(j => { HIST = j; histAt = Date.now(); histDays = d; histBusy = 0;
                 if(mainView === 'hist') paintHist(); })
    .catch(() => { histBusy = 0; HIST = {ok:false, msg:'Check the server'};
                   if(mainView === 'hist') paintHist(); });
  return true;
}
// ★2026-09-28 UX audit: project chips + title search over the loaded list; kept in UIS sidereus.histf {p:[names], q}.
let histProj = [], histQ = '';
try{ const v = JSON.parse(tabGet('sidereus.histf', null) || 'null');
     if(v && typeof v === 'object'){ histProj = Array.isArray(v.p) ? v.p.filter(x => typeof x === 'string').slice(0, 50) : [];
                                     histQ = typeof v.q === 'string' ? v.q.slice(0, 200) : ''; } }catch(e){ softErr('histf-read', e); }
function histFSave(){ tabSetJson('sidereus.histf', {p: histProj, q: histQ}); }
function histMatch(x, ps){
  if(ps.length && ps.indexOf(x.project || '?') < 0) return false;
  const q = histQ.trim().toLowerCase();
  return !q || [x.title, x.project, x.branch, x.sid].some(v => v && String(v).toLowerCase().indexOf(q) >= 0);
}
// ⚠ Source is hourly buckets (token index), so minutes are unknown -> «approx. N hours», never «N hour slots».
function histActive(h){ return T('active ~N h').replace('N', h); }
// ⚠Rows are per local day: an end on the next midnight is «24:00» (was «00:00»); runFrom/runTo = the run across midnight.
function histSpan(x){
  const p2 = n => (n < 10 ? '0' : '') + n;
  const day = t => { const a = new Date(t*1000); return new Date(a.getFullYear(), a.getMonth(), a.getDate()).getTime(); };
  const d0 = x.date ? new Date(x.date + 'T00:00:00').getTime() : day(x.from);
  const off = t => Math.round((day(t) - d0) / 86400000);
  // en: CLK 12h like the rest of the page; the «24:00» end below is then simply «next day 12:00 AM»
  const hm = t => { const a = new Date(t*1000); return LANG === 'en' ? CLK(a) : p2(a.getHours())+':'+p2(a.getMinutes()); };
  const pre = n => n === 0 ? '' : n === -1 ? (T('prev day') + ' ') : n === 1 ? (T('next day') + ' ')
    : n < 0 ? (T('{n}d before').replace('{n}', -n) + ' ') : (T('+{n}d').replace('{n}', n) + ' ');
  const st = x.runFrom || x.from, s = pre(off(st)) + hm(st);
  // `to` = last hour bucket + 1h, so the current hour reads as a future end (10:59 showed «~11:00») — clamp to now.
  // ⚠max(st, …): a start after the local clock (demo world, clock skew) must not print an end before the start.
  const now = Math.floor(Date.now() / 1000), e = Math.max(st, Math.min(x.runTo || x.to, now));
  const live = histLive(x) && (x.runTo || x.to) >= now;
  let o = off(e), c = hm(e);
  if(c === '00:00' && o > 0){ o -= 1; c = '24:00'; }
  const tip = (x.runFrom || x.runTo) ? ' title="'+esc(T('Crosses midnight — tokens and active hours count this date only'))+'"' : '';
  return '<span class="hst'+(tip ? ' hsxd' : '')+'"'+tip+'>'+esc(s+T('–', 'range')+pre(o)+c)+'</span>'
    + (live ? '<span class=hslv title="'+esc(T('Session still open — the end is the current time'))+'">'+esc(T('Running', 'stage'))+'</span>' : '');
}
// Live = the poll still lists this session and it has not ended (state done/gone = closed).
function histLive(x){
  const r = (typeof SESS !== 'undefined' && SESS || []).find(s => s.sid === x.sid);
  return !!r && r.state !== 'done' && r.state !== 'gone';
}
function paintHist(){
  if(mainView !== 'hist') return;
  const box = document.getElementById('feed');
  if(!box) return;
  const head = '<div class=tlhd>'+esc(T('Past session history'))+' <i>'+esc(T('Last {n} days · by date').replace('{n}', histDays))+'</i></div>'
    + '<div class=hidnote>'
    + esc(T('The source is the token index — only project, session title, branch, model, active hours and tokens are listed (titles are the ones Claude Code assigns — conversation text is never read). Times are on the hour.'))
    + ((pn => pn ? ' '+esc(T('{n} sessions come from {n} CLI chat files — only times, model and tokens are read (never message text). Cost is an estimate from list prices and is kept out of Claude totals.').replace(/\{n\}/g, () => pn)) : '')(
        [...new Set([].concat(...((HIST && HIST.list) || []).map(histExtKeys)))].map(k => platName(k)).join('·')))
    + '</div>';
  // The range toggle lives in the header toolbar slot (wired below, before any early return).
  // ⚠No value= in the markup: setHtml would rewrite the slot on every keystroke and drop focus — the value is set below.
  const cur = histBusy ? histWant : histDays, fo = acctPickFocusId();   // ⚠tbSlot below replaces a focused picker
  const tb = tbSlot('hist', '<span class=tbg><input type=search id=histq class=histq placeholder="'+esc(T('Search session titles'))+'"'
    + ' aria-label="'+esc(T('Search session titles'))+'" title="'+esc(T('Search session titles'))+' (/ · Esc '+esc(T('clear'))+')"></span>'
    + '<span class="tbg rtrg">' + HIST_STEPS.map(x => '<button class="wkrgb'+(x === cur ? ' on' : '')+'" data-hd="'+x+'" aria-pressed="'+(x === cur)+'">'
      + esc(T('Last {n} days').replace('{n}', x))+'</button>').join('') + (histBusy ? ' <i>'+esc(T('Loading…', 'read'))+'</i>' : '') + '</span>'
    + acctPickHtml('hist'));   // '' below 2 accounts
  acctPickWire('hist', paintHist, fo);
  const qi = tb && tb.querySelector('#histq');
  if(qi){
    if(document.activeElement !== qi && qi.value !== histQ) qi.value = histQ;
    qi.oninput = () => { histQ = qi.value; histFSave(); paintHist(); };
    // Esc clears the search (the browser's own search-field Esc does not fire `input` everywhere)
    qi.onkeydown = ev => { if(ev.key === 'Escape' && qi.value){ ev.preventDefault(); ev.stopPropagation(); qi.value = ''; histQ = ''; histFSave(); paintHist(); } };
  }
  if(tb) tb.querySelectorAll('[data-hd]').forEach(b => b.onclick = () => {   // days change **after** loadHist succeeds
    if(!loadHist(false, +b.dataset.hd)) note(T('The history is still loading — try again in a moment'));
  });
  if(!HIST){ box.innerHTML = head + '<div class=hidnote>'+esc(T('Loading…', 'read'))+'</div>'; return; }
  if(!HIST.ok){ box.innerHTML = head + '<div class=hidnote>'+esc(T('Could not read'))+' — '
      + esc(TV({msg: HIST.msg || 'Unknown', vars: HIST.vars})) + '</div>'; return; }
  const list = HIST.list || [];
  if(!list.length){ box.innerHTML = head + '<div class=hidnote>'+esc(T('No sessions were active in this period.'))+'</div>'; return; }
  // Chips list every project in the loaded range; a saved pick missing from this range is ignored, not stuck on.
  const projs = [...new Set([].concat(...list.map(d => (d.rows||[]).concat(...histExtKeys(d).map(k => d[k].rows))))
    .map(x => x.project || '?'))].sort((a, b) => a.localeCompare(b));
  // Account pick (40b acctInPick 'hist'): narrows like a filter, so day headers recompute from shown rows; uf = chip/search only.
  const pk = acctPick('hist'), ap = !!pk && !ACC_OTH.hist;
  const ps = histProj.filter(p => projs.indexOf(p) >= 0), uf = !!(ps.length || histQ.trim()), filt = uf || ap;
  const chips = projs.length > 1 ? '<div class=hpcs role=group aria-label="'+esc(T('Project'))+'">'
    + '<button class="hpc'+(ps.length ? '' : ' on')+'" data-hp="" aria-pressed="'+!ps.length+'">'+esc(T('All'))+'</button>'
    + projs.map(p => '<button class="hpc'+(ps.indexOf(p) >= 0 ? ' on' : '')+'" data-hp="'+esc(p)+'" aria-pressed="'+(ps.indexOf(p) >= 0)+'">'
      + esc(p)+'</button>').join('') + '</div>' : '';
  let shown = 0, hid = 0;
  const body = list.map(d => {
    // Gemini rows come in a separate `gm` block (never in Claude totals); interleave by start time for display.
    const xb = histExtKeys(d);
    const all0 = (d.rows||[]).concat(...xb.map(k => d[k].rows)).filter(x => histMatch(x, ps))
      .sort((a, b) => b.from - a.from || b.to - a.to);   // newest start first, like the server
    const all = ap ? all0.filter(x => acctInPick(x, 'hist', pk)) : all0;
    hid += all0.length - all.length;
    if(filt && !all.length) return '';
    shown += all.length;
    const rows = all.map(x => {
      if(x.plat && x.plat !== 'cc') return histGmRow(x);
      const rz = (x.sid && x.sid.length > 8 && x.cwd && x.plat === 'cc')
        // A worded button: a bare «↻» read as «refresh», but it copies the resume command.
        ? '<button type=button class="srz hsrz" data-rz="'+esc('cd '+x.cwd+' && claude --resume '+x.sid)
          + '" aria-label="'+esc(T('Copy resume command'))+'" title="'+esc(T('Copy resume command'))+': cd '+esc(x.cwd)+' &amp;&amp; claude --resume '+esc(x.sid)+'">'
          // Below 1100 only the icon shows (60-sessions.css); the label stays in aria-label/title
          + '<svg class=ic viewBox="0 0 16 16" aria-hidden=true><rect x="5.5" y="5.5" width="8" height="8" rx="1.5"/><path d="M10.5 3.5v-.5a1 1 0 0 0-1-1h-6a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h.5"/></svg>'
          + '<span class=hsrzl>'+esc(T('Copy resume command'))+'</span></button>' : '';
      const cost = x.cost ? ' · '+money(x.cost) : '';
      const sub = x.sub ? ' <s>'+esc(T('Subagents'))+' '+x.sub+'</s>' : '';
      const k = d.date + '|' + x.sid, op = histOpen.has(k);
      return '<div class="hsr hsx'+(op ? ' on' : '')+'" role=button tabindex=0 aria-expanded='+op
        + ' data-hk="'+esc(k)+'" data-sid="'+esc(x.sid)+'" data-cwd="'+esc(x.cwd || '')+'">'
        + '<span class=hsc aria-hidden=true>'+(op ? '▾' : '▸')+'</span>'+histSpan(x)
        + aiLogo(x.plat, ' '+T('Session'))
        + '<b title="'+esc((x.cwd || x.slug)+' · '+T('session id')+' '+x.sid)+'">'+esc(x.project||'?')+'</b>'
        // Title = Claude Code's own session title (/rename, else /resume auto title); no title -> the id, as before
        + (x.title ? '<span class=hsti title="'+esc(x.title+' · '+T('session id')+' '+x.sid)+'">'+esc(x.title)+'</span>' : '')
        + (x.branch ? '<span class=hsbr title="'+esc(T('git branch'))+' '+esc(x.branch)+'">'+esc(x.branch)+'</span>' : '')
        + (x.model ? '<span class=hsm title="'+esc(x.model)+'">'+esc(x.model)+(x.models>1?'+':'')+'</span>' : '')
        + '<s title="'+esc(histActive(x.hours)+' · '+T('Number of active hour slots — the source is hourly, so minutes are unknown'))+'">'
        + esc(histActive(x.hours))+'</s>' + sub
        + (x.title ? '' : '<s title="'+esc(T('session id'))+' '+esc(x.sid)+'">'+esc(x.id)+'</s>') + rz
        + '<em>'+fmtTok(x.tok)+cost+'</em></div>'
        + '<div class=hub data-hk="'+esc(k)+'"'+(op ? '' : ' hidden')+'>'+(op ? histUnitsHtml(x.sid, x.cwd) : '')+'</div>';
    }).join('');
    const wd = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][new Date(d.date+'T12:00:00').getDay()];
    const tt = histDayTot(d, all, filt), xk = Object.keys(tt.ext);
    const xs = xk.map(k => '<span title="'+esc(histCostTip(k))+'">'
      + esc(platName(k)+' '+fmtTok(tt.ext[k].tok)+' · '+extCostStr(tt.ext[k].estCost))+'</span>').join(' · ');
    return '<div class=hsd>'+esc(d.date)+esc(T('('+wd+')'))+'<i>'
      + (tt.n || !xk.length ? esc(T('Sessions'))+' '+tt.n+' · '+fmtTok(tt.tok)+(tt.cost ? ' · '+money(tt.cost) : '') : '')
      + (xk.length ? (tt.n ? ' · ' : '')+xs : '')
      + '</i></div>' + rows;
  }).join('');
  const fnote = uf ? '<div class="hidnote hsfn">'+esc(T('Showing {n} sessions').replace('{n}', shown))
    + ' <button class=wkrgb data-hpx>'+esc(T('Clear filters'))+'</button></div>' : '';
  box.innerHTML = head + chips + fnote + acctOthHtml('hist', hid) + (uf && !shown
    ? '<div class=hidnote>'+esc(T('No sessions match — change the project selection or the search.'))+'</div>' : body);
  const aoe = box.querySelector('.acoth[data-ao]');
  if(aoe) aoe.onclick = e => acctOthClick(e, paintHist);
  box.querySelectorAll('.hpc[data-hp]').forEach(b => b.onclick = () => {
    const p = b.getAttribute('data-hp');
    histProj = !p ? [] : ps.indexOf(p) >= 0 ? ps.filter(x => x !== p) : ps.concat([p]);
    histFSave(); paintHist();
    const n = [...document.querySelectorAll('#feed .hpc[data-hp]')].find(e => e.getAttribute('data-hp') === p); if(n) n.focus();
  });
  const fx = box.querySelector('[data-hpx]');
  if(fx) fx.onclick = () => { histProj = []; histQ = ''; if(qi) qi.value = ''; histFSave(); paintHist(); };
  // This view binds the ↻ chip itself — the session list's delegated handler does not watch `#feed`
  box.querySelectorAll('.srz[data-rz]').forEach(el => { el.onclick = ev => {
    ev.stopPropagation();
    const cmd = el.getAttribute('data-rz');
    copyText(cmd).then(ok => note(ok ? T('Copy')+': '+cmd : T('Copy failed')+' — '+cmd));
  }; });
  box.querySelectorAll('.hsx[data-hk]').forEach(el => {
    el.onclick = () => histToggle(el);
    // ev.target check: Enter on the inner «Copy resume» button must copy, not toggle the row
    el.onkeydown = ev => { if(ev.target === el && (ev.key === 'Enter' || ev.key === ' ')){ ev.preventDefault(); histToggle(el); } };
  });
  box.querySelectorAll('.hub:not([hidden])').forEach(histUnitsBind);
}
// Gemini row: same columns, no expansion (work units are Claude-only), cost as a «≈ $» estimate.
// Per-platform blocks of one day (gm, cx, ...) — every key holding a `rows` array except Claude's own.
function histExtKeys(d){ return Object.keys(d || {}).filter(k => k !== 'rows' && d[k] && Array.isArray(d[k].rows)); }
// Day header totals: the server's day sums, or — while a chip/search filter is on — sums of the rows actually shown
// (the header kept saying «Sessions 5 · 191M» above one visible row).
function histDayTot(d, shown, filt){
  const ks = histExtKeys(d);
  if(!filt){
    const ext = {}; ks.forEach(k => { ext[k] = {tok: d[k].tok, estCost: d[k].estCost}; });
    return {n: d.n, tok: d.tok, cost: d.cost, ext};
  }
  const cc = shown.filter(x => !x.plat || x.plat === 'cc'), ext = {};
  ks.forEach(k => { const rs = shown.filter(x => x.plat === k);
    if(rs.length) ext[k] = {tok: rs.reduce((a, x) => a + (x.tok || 0), 0),
                            estCost: rs.some(x => x.estCost != null) ? rs.reduce((a, x) => a + (x.estCost || 0), 0) : null}; });
  return {n: cc.length, tok: cc.reduce((a, x) => a + (x.tok || 0), 0), cost: cc.reduce((a, x) => a + (x.cost || 0), 0), ext};
}
function histCostTip(k){ const n = platName(k); return T('Estimated cost — {n} list prices').replace('{n}', n); }
function histGmRow(x){
  const est = x.estCost != null ? ' · <span title="'+esc(histCostTip(x.plat))+'">'+esc(extCostStr(x.estCost))+'</span>' : '';
  return '<div class=hsr><span class=hsc aria-hidden=true></span>'+histSpan(x)
    + aiLogo(x.plat, ' '+T('Session'))
    + '<b title="'+esc((x.cwd || x.project || '')+' · '+T('session id')+' '+x.sid)+'">'+esc(x.project||'?')+'</b>'
    + (x.model ? '<span class=hsm title="'+esc(x.model)+'">'+esc(x.model)+(x.models>1?'+':'')+'</span>' : '')
    + '<s title="'+esc(histActive(x.hours)+' · '+T('Number of active hour slots — the source is hourly, so minutes are unknown'))+'">'+esc(histActive(x.hours))+'</s>'
    + '<s title="'+esc(T('session id'))+' '+esc(x.sid)+'">'+esc(x.id)+'</s>'
    + '<em>'+fmtTok(x.tok)+est+'</em></div>';
}
// ── Row expansion — the session's work units (main + sub-agents), each opening the /work popup ──
// Clicking a history row lists the session's own and its sub-agents' work, click → popup.
// ⚠Metadata only on this page (type · Agent `description` · times · tokens · tool count · status); content lives in /work.
const HUNITS = {};                 // sid -> /api/history/units response (server caches 30s; fetched on expand only)
const histOpen = new Set();        // expanded `date|sid` keys — survive the 60s re-render
function histToggle(el){
  const k = el.getAttribute('data-hk'), sid = el.getAttribute('data-sid');
  const hub = [...document.querySelectorAll('.hub[data-hk]')].find(b => b.getAttribute('data-hk') === k);
  const op = !histOpen.has(k);
  if(op) histOpen.add(k); else histOpen.delete(k);
  el.classList.toggle('on', op); el.setAttribute('aria-expanded', op);
  const c = el.querySelector('.hsc'); if(c) c.textContent = op ? '▾' : '▸';
  if(!hub) return;
  hub.hidden = !op;
  if(!op) return;
  const draw = () => { hub.innerHTML = histUnitsHtml(sid, el.getAttribute('data-cwd')); histUnitsBind(hub); };
  draw();
  if(!HUNITS[sid] || !HUNITS[sid].ok || Date.now() - (HUNITS[sid]._at || 0) > 30000){
    getJSON('/api/history/units?sid=' + encodeURIComponent(sid))
      .then(j => { j._at = Date.now(); HUNITS[sid] = j; }, () => { HUNITS[sid] = {ok:false, msg:'Check the server'}; })
      .then(() => { if(!hub.hidden) draw(); });
  }
}
function histWhen(a, b){
  const A = new Date(a*1000), B = new Date(b*1000);
  return MDCLK(A) + '–' + (A.toDateString() === B.toDateString() ? CLK(B) : MDCLK(B));
}
const HU_ST = {run:'Running', end:'Ended', done:'Done', cut:'Stopped without a report'};   // T(v, 'history')
function histUnitsHtml(sid, cwd0){
  const j = HUNITS[sid];
  if(!j) return '<div class=hidnote>'+esc(T('Loading…', 'read'))+'</div>';
  if(!j.ok) return '<div class=hidnote>'+esc(T('Could not read'))+' — '+esc(TV({msg: j.msg || 'Unknown', vars: j.vars}))+'</div>';
  const us = j.units || [], cwd = j.cwd || cwd0 || '';
  const na = us.filter(u => u.kind === 'agent').length, can = us.filter(u => u.tid).length;
  const head = '<div class=huh><span>'+esc(T('Work units'))+' '+us.length+' · '+esc(T('Subagents'))+' '+na+'</span>'
    + (can > 1 ? '<button class=wkrgb data-huall title="'+esc(T('Opens the first 4 in one split window'))+'">'
                 + esc(T('Open all'))+' ('+Math.min(4, can)+')</button>' : '') + '</div>';
  const rows = us.map(u => {
    const nm = u.kind === 'main' ? T('Main session') : u.type;
    // Main: active hour buckets from the token index (wall span of a resumed session misleads)
    const dur = u.hours ? histActive(u.hours) : HM(Math.max(0, Math.round((u.end - u.start) / 60)));
    const tip = (u.kind === 'main' ? T('session id')+' '+sid : 'agent '+(u.aid||'')) + (u.desc ? ' · '+plStrip(u.desc) : '');
    return '<div class="hun'+(u.tid ? '' : ' off')+'" role=button tabindex='+(u.tid ? 0 : -1)
      + ' data-tid="'+esc(u.tid || '')+'" data-cwd="'+esc(cwd)+'" title="'+esc(tip)+'"'
      + ' style="padding-left:'+(8 + Math.max(0, (u.depth||0) - 1) * 14)+'px">'
      + '<span class=hst>'+esc(histWhen(u.start, u.end))+'</span><s>'+esc(dur)+'</s>'
      + '<b class="'+(u.kind === 'main' ? 'hum' : '')+'">'+esc(nm)+'</b>'
      + '<span class=hue>'+esc(plStrip(u.desc || ''))+'</span>'
      + (u.tc != null ? '<s>'+esc(T('Tool'))+' '+u.tc+'</s>' : '')
      + '<em>'+fmtTok(u.tok || 0)+'</em>'
      + '<span class="hus hs-'+esc(u.st)+'">'+esc(T(HU_ST[u.st] || u.st, 'history'))+'</span></div>';
  }).join('');
  return head + (rows || '<div class=hidnote>'+esc(T('No work units.'))+'</div>');
}
function histUnitsBind(hub){
  hub.querySelectorAll('.hun[data-tid]').forEach(el => {
    const tid = el.getAttribute('data-tid'); if(!tid) return;
    const go = () => wkPopup(el.getAttribute('data-cwd'), tid);
    el.onclick = go;
    el.onkeydown = ev => { if(ev.key === 'Enter' || ev.key === ' '){ ev.preventDefault(); go(); } };
  });
  const all = hub.querySelector('[data-huall]');
  if(all) all.onclick = ev => { ev.stopPropagation();
    const els = [...hub.querySelectorAll('.hun[data-tid]')].filter(e => e.getAttribute('data-tid')).slice(0, 4);
    if(!els.length) return;
    const cwd = els[0].getAttribute('data-cwd'), ts = els.map(e => e.getAttribute('data-tid'));
    let url = '/work?cwd=' + encodeURIComponent(cwd) + '&tid=' + encodeURIComponent(ts[0]);
    if(ts.length > 1) url += '&lay=' + ['1', '1', 'h2', 'c3', 'g4'][ts.length]
      + '&more=' + encodeURIComponent(ts.slice(1).map(t => cwd + '\t' + t).join('\n'));
    popOpen(url, popName('sidereus_hu_', hub.getAttribute('data-hk') + '_' + ts.length),
            ts.length > 1 ? 1700 : 1100, ts.length > 3 ? 1100 : 800);
  };
}
