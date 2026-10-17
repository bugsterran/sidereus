// ── Retrospect tab — failure trend · weekly summary · tokens per commit ──────────────────
// Server folds history() + _fail_events() + local git (`/api/retro`, 120s cache); this file only draws.
// ⚠Fetched only when this view opens (no poll). Rows are metadata only: project, counts, tool names, failure signatures.
let RETRO = null, retroDays = 7, retroBusy = 0, retroAt = 0, retroWant = 0;
const RETRO_STEPS = [7, 30];
// [label, dark colour, light colour] — light variants are >=3.8:1 on the light cards (dark ones were 2.99:1 there).
const RT_KIND = {tool:['Tool error','#8b95a7','#6b7385'], hook:['Hook block','#e8913a','#b8641a'], deny:['Permission denied','#b07acc','#8f55ad'],
                 api:['API error','#d96a6a','#c04444'], agent:['Subagent failure','#5b8def','#3a6fd4'], bg:['Background failure','#4fa8b8','#2f8394'],
                 monitor:['Monitor failure','#c9a227','#937411'], stop:['Aborted','#5fa96a','#3f8a4b']};
const RT_GRADE = {check:'to check', cut:'external cause', mine:'own denial/block', noise:'noise'};
// What each grade means and what to do (rules: sidereus/failures_scan.py _fail_grade) — shown as tooltips.
const RT_GRADE_TIP = {check:'A failure notice whose cause could not be read — look at it',
                      cut:'External cause (connection, limit, overload) — just rerun',
                      mine:'Something I blocked (permission denial, hook) — nothing to do',
                      noise:'A tool returned an error — part of normal work, usually nothing to do'};
function rtKind(k){ const r = RT_KIND[k] || [k, '#7b7c82', '#62636a']; return [r[0], thc(r[1], r[2])]; }
// ★2026-09-25: «Tool error 738» beside «Read 1/7» looked contradictory — each heading names its source and period.
// Failure signatures come from the server (sidereus/failures_scan.py) in Korean; srvEn translates the fixed phrases only.
function rtSig(s){ return s ? srvEn(s) : s; }
// Same contract as loadHist: `want` becomes retroDays only after a successful load.
function loadRetro(force, want){
  const d = want || retroDays;
  if(retroBusy) return false;
  const pk = acctPick('retro');   // '' = All accounts; scopes only the six OTel cards (server swaps them)
  if(!force && RETRO && RETRO.days === d && String(RETRO.acct || '') === pk && Date.now() - retroAt < 120000){
    retroDays = d; if(mainView === 'retro') paintRetro(); return true; }
  retroBusy = 1; retroWant = d;
  if(mainView === 'retro') paintRetro();
  getJSON('/api/retro?days=' + d + (pk ? '&acct=' + encodeURIComponent(pk) : ''))
    .then(j => {
      // ⚠A reply for an older pick lands after the switch (retroBusy blocked the new load) — drop it and load the current pick.
      const cur = acctPick('retro');
      if(pk !== cur){ retroBusy = 0; loadRetro(true, d); return; }
      if(j && j.ok && String(j.acct || '') !== cur) j = {ok:false, msg:'Check the server'};   // never paint another account's cards
      RETRO = j; retroAt = Date.now(); retroDays = d; retroBusy = 0;
                 if(mainView === 'retro') paintRetro(); })
    .catch(e => { retroBusy = 0;
                   if(pk !== acctPick('retro')){ loadRetro(true, d); return; }   // error for an older pick: load the current one instead
                   RETRO =(e && e.status === 404) ? {ok:false, off:true} : {ok:false, msg:'Check the server'};   // 404 = feature off
                   if(mainView === 'retro') paintRetro(); });
  return true;
}
function rtFailChart(r){
  const dl = r.daily || [];
  const mx = Math.max(1, ...dl.map(x => x.fails));
  const H = 84, every = dl.length > 10 ? 5 : 1;
  const order = Object.keys(r.kinds || {}).sort((a, b) => (r.kinds[b] - r.kinds[a]));
  const cols = dl.map((x, i) => {
    const segs = order.filter(k => (x.kinds||{})[k]).map(k =>
      '<i style="height:'+Math.max(1, Math.round(x.kinds[k] / mx * H))+'px;background:'+rtKind(k)[1]+'"></i>').join('');
    const tip = x.d + ' · ' + T('Failures') + ' ' + x.fails
      + order.filter(k => (x.kinds||{})[k]).map(k => '\n' + T(rtKind(k)[0]) + ' ' + x.kinds[k]).join('');
    const lab = (i % every === 0 || i === dl.length - 1) ? esc(x.d.slice(5).replace('-', '/')) : '';
    return '<div class=rtc title="'+esc(tip)+'">'
      + '<span class=rts style="height:'+(H+14)+'px">'+segs+'<b class=rtz>'+(x.fails || '')+'</b></span><span class=rtl>'+lab+'</span></div>';
  }).join('');
  const lg = order.map(k => '<em><b style="background:'+rtKind(k)[1]+'"></b>'+esc(T(rtKind(k)[0]))
    + '<s>'+r.kinds[k]+'</s></em>').join('');
  // «to check N» is a button when a listed failure row holds those events — it opens and marks them (rtShowChk).
  const hasChk = (r.sigs || []).some(x => x.chk);
  const gr = Object.keys(RT_GRADE).filter(g => (r.grades||{})[g])
    .map(g => g === 'check' && hasChk
      ? '<button class=rtchkb data-rtchk title="'+esc(T(RT_GRADE_TIP[g])+' — '+T('Expands the failure rows that hold these'))+'">'+esc(T(RT_GRADE[g]))+' <b>'+r.grades[g]+'</b></button>'
      : '<span class=rtgd title="'+esc(T(RT_GRADE_TIP[g]))+'">'+esc(T(RT_GRADE[g]))+' <b>'+r.grades[g]+'</b></span>').join(' · ');
  return '<div class=rtb>'+cols+'</div><div class="wktl rtlg">'+lg+'</div>'
    + (gr ? '<div class=brsum>'+esc(T('Grade'))+' — '+gr+'</div>' : '');
}
// ★2026-09-28 UX audit: failure rows were dead ends — a click lists the sessions it happened in (server `where`, metadata only).
const rtOpen = new Set();           // expanded rows, keyed by kind|sig — survive range switches and repaints
const rtKey = x => x.kind + '|' + x.sig;
const RT_SID = /^[\w-]{8,80}$/;
function rtWhere(x){
  const ws = x.where || [];
  if(!ws.length) return '<div class=hidnote>'+esc(T('No session information.'))+'</div>';
  return ws.map(w => {
    const ok = RT_SID.test(w.sid || '') && (w.cwd || '').charAt(0) === '/';
    return '<div class=rtwh><b title="'+esc((w.cwd || '')+' · '+T('session id')+' '+w.sid)+'">'+esc(w.project || '?')+'</b>'
      + '<s>'+esc(String(w.sid || '').slice(0, 8))+'</s>'
      + '<span class=rtwn>'+esc(U(w.n, '×'))+'</span><span class=rtwt title="'+esc(stamp(w.last))+'">'+agoAt(w.last)+'</span>'
      + (ok ? '<button class=wkrgb data-rtw="'+esc(w.sid)+'" data-rtc="'+esc(w.cwd)+'" data-rtt="'+(+w.last || 0)+'"'
        + ' title="'+esc(T('Opens the work log up to the last failure'))+'">'+esc(T('Activity'))+'</button>' : '')+'</div>';
  }).join('') + ((x.wn || 0) > ws.length ? '<div class=hidnote>'+esc(T('{n} more sessions').replace('{n}', (x.wn - ws.length)))+'</div>' : '');
}
function rtSigs(r){
  const s = r.sigs || [];
  if(!s.length) return '';
  return '<table class=brt><thead><tr><th>'+esc(T('Frequent failures'))+'</th><th>'+esc(T('Type'))+'</th><th class=brv>'
    + esc(T('Count'))+'</th><th class=brv>'+esc(T('Last'))+'</th></tr></thead><tbody>'
    + s.map((x, i) => { const op = rtOpen.has(rtKey(x));
      return '<tr class="rtsr'+(x.chk ? ' rtchk' : '')+(op ? ' on' : '')+'" data-rsi="'+i+'" role=button tabindex=0 aria-expanded="'+op+'">'
      + '<td class=brd title="'+esc(rtSig(x.sig)+' — '+T('click to see the sessions it happened in'))+'"><span class=hsc aria-hidden=true>'+(op ? '▾' : '▸')+'</span>'+esc(rtSig(x.sig))
      + (x.chk ? ' <em class=rtchkt>'+esc(T('to check'))+' '+x.chk+'</em>'
        // grade chip: without it a top row of «noise» looked as urgent as a real failure
        : x.grade && RT_GRADE[x.grade] ? ' <em class="rtgc rtg-'+esc(x.grade)+'" title="'+esc(T(RT_GRADE_TIP[x.grade]))+'">'+esc(T(RT_GRADE[x.grade]))+'</em>' : '')+'</td>'
      + '<td class=brn><span style="color:'+rtKind(x.kind)[1]+'">■</span> '+esc(T(rtKind(x.kind)[0]))+'</td>'
      + '<td class=brv>'+x.n+'</td><td class=brv title="'+esc(stamp(x.last))+'">'+agoAt(x.last)+'</td></tr>'
      + (op ? '<tr class=rtwr><td colspan=4>'+rtWhere(x)+'</td></tr>' : ''); }).join('')
    + '</tbody></table>';
}
function rtToggle(i, force){
  const x = ((RETRO || {}).sigs || [])[i];
  if(!x) return;
  const k = rtKey(x), op = force == null ? !rtOpen.has(k) : force;
  if(op) rtOpen.add(k); else rtOpen.delete(k);
}
// Opens every row holding «to check» events, scrolls to the first and flashes them.
function rtShowChk(){
  const sg = (RETRO || {}).sigs || [];
  sg.forEach((x, i) => { if(x.chk) rtToggle(i, true); });
  paintRetro();
  const rows = [...document.querySelectorAll('#feed .rtsr.rtchk')];
  if(!rows.length) return;
  rows[0].scrollIntoView({block: 'center', behavior: 'smooth'});
  rows.forEach(el => { el.classList.add('rtflash'); setTimeout(() => el.classList.remove('rtflash'), 1600); });
  rows[0].focus({preventScroll: true});
}
function rtBind(box){
  // Own tabindex + keydown (98-a11y skips elements with a tabindex) so focus can land on a freshly painted row.
  box.querySelectorAll('.rtsr[data-rsi]').forEach(el => {
    el.onclick = () => {
      const i = +el.dataset.rsi;
      rtToggle(i); paintRetro();
      const n = document.querySelector('#feed .rtsr[data-rsi="'+i+'"]'); if(n) n.focus({preventScroll: true});
    };
    el.onkeydown = ev => { if(ev.key === 'Enter' || ev.key === ' '){ ev.preventDefault(); el.onclick(); } };
  });
  box.querySelectorAll('[data-rtw]').forEach(b => b.onclick = ev => {
    ev.stopPropagation();
    const c = b.getAttribute('data-rtc');
    // Open at the last failure, not the live tail — the tail usually holds none of these failures.
    wkPopup(c, 'sess:' + c + '|' + b.getAttribute('data-rtw'), +b.getAttribute('data-rtt') || 0);
  });
  const cb = box.querySelector('[data-rtchk]'); if(cb) cb.onclick = rtShowChk;
  const fd = box.querySelector('[data-rtfold]'), rb = box.querySelector('.rtrest');
  if(fd && rb){
    fd.onclick = () => { rtRankOpen = !rtRankOpen; rb.hidden = !rtRankOpen; fd.setAttribute('aria-expanded', String(rtRankOpen));
                         const s = fd.querySelector('.hsc'); if(s) s.textContent = rtRankOpen ? '▾' : '▸'; };
    fd.onkeydown = ev => { if(ev.key === 'Enter' || ev.key === ' '){ ev.preventDefault(); fd.onclick(); } };
  }
}
function rtTools(r){
  const t = (r.tools || {}).rows || [];
  if(!t.length) return '';
  const mx = Math.max(1, ...t.map(x => x[2]));
  const since = (r.tools || {}).since;
  return '<div class=brh2 title="'+esc(T('Counts only tool calls received over OTel since the server started — «Failure trend» on the left covers all transcript records, so it is larger'))+'">'
    + esc(T('Tools failing most'))+' <i>'+esc(T('since server start · OTel tally'))
    + (since ? ' · '+esc(MDCLK(new Date(since*1000)))+'~' : '')+'</i></div>'
    + '<table class=brt><thead><tr><th>'+esc(T('Tool'))+'</th><th class=brv>'+esc(T('Failures'))+'</th><th></th><th class=brv>'
    + esc(T('Calls'))+'</th><th class=brv>'+esc(T('Fail rate'))+'</th></tr></thead><tbody>'
    + t.map(x => '<tr><td class=brn>'+esc(x[0])+'</td><td class=brv>'+x[2]+'</td>'
      + '<td class=brg><span class=brb><i style="width:'+Math.max(1, x[2]/mx*100).toFixed(1)+'%;background:#d96a6a"></i></span></td>'
      + '<td class=brv>'+x[1]+'</td><td class=brv>'+(x[1] ? fmtPct(x[2]/x[1]*100) : '—')+'</td></tr>').join('')
    + '</tbody></table>';
}
// Card ① tool ranking — server `rank` = per-day OTel tally (survives restarts), top rows + folded rest.
let rtRankOpen = false;             // «N more» fold state, kept across repaints
// Hours unit: «Time spent» totals reach days of Bash time, and «3384m 35s» does not read as 56 hours.
const rtMs = ms => ms == null ? '—' : ms >= 3600000 ? Math.floor(Math.round(ms / 60000) / 60) + 'h ' + Math.round(ms / 60000) % 60 + 'm'
  : ms >= 60000 ? Math.floor(Math.round(ms / 1000) / 60) + 'm ' + Math.round(ms / 1000) % 60 + 's'
  : ms >= 500 ? (ms / 1000).toFixed(1) + 's' : Math.round(ms) + 'ms';
// Classed on the shown (rounded) value — 97.6 and 98.2 both read «98%» and must share a colour.
const rtOkCls = p => { const q = Math.round(p); return q >= 98 ? 'rtok' : q >= 90 ? 'rtwarn' : 'rterr'; };
// Local-time YYYY-MM-DD; shared by the period labels below.
const rtP2 = n => (n < 10 ? '0' : '') + n;
const rtYmd = d => d.getFullYear() + '-' + rtP2(d.getMonth() + 1) + '-' + rtP2(d.getDate());
// Period label shared by the OTel cards (rank, time spent) so both name the same range.
function rtPer(r, f){
  const okf = f && /^\d{4}-\d{2}-\d{2}$/.test(f), md = okf ? (+f.slice(5, 7)) + '/' + (+f.slice(8, 10)) : '';
  // Collection began inside the range -> say so; «Last 30 days» over data from one day read as a 30-day tally.
  const s0 = new Date(); s0.setDate(s0.getDate() - ((r.days || 7) - 1));
  const since = rtYmd(s0);
  const smd = (+since.slice(5, 7)) + '/' + (+since.slice(8, 10));   // never name a day before the range
  return okf && f > since ? T('since {n} (collection start)').replace('{n}', md)
    : T('Last {n} days').replace('{n}', r.days) + (md ? ' · ' + smd + '~' : '');
}
function rtRank(r){
  const k = r.rank, per = rtPer(r, k && k.from);
  const h = '<div class=brh2>'+esc(T('Tool ranking'))+' <i>'+esc(per)+' · '+esc(T('OTel tally'))+'</i></div>';
  if(k && !k.calls && k.live) return h + '<div class=hidnote>'
    + esc(T('OTel is arriving — no tool calls in this range'))+'</div>';
  if(!k || !k.calls) return h + '<div class=hidnote>'
    + esc(T("No OTel data — once Claude Code's OTel export (OTEL_EXPORTER_OTLP_ENDPOINT) points at this viewer, calls are counted from the next one"))+'</div>';
  const top = k.top || [], rest = k.rest || [], restN = k.restN || 0;
  const mx = Math.max(1, ...top.concat(rest).map(x => x.calls || 0));
  const nm = n => n === '기타' ? T('Other') : n;   // the server's overflow bucket is a fixed Korean key
  const row = x => '<tr><td class=brn title="'+esc(nm(x.n))+'">'+esc(nm(x.n))+'</td><td class=brv>'+(x.calls || 0).toLocaleString()+'</td>'
    + '<td class=brg><span class=brb><i style="width:'+Math.max(1, (x.calls || 0)/mx*100).toFixed(1)+'%;background:var(--nx-info,#5b8def)"></i></span></td>'
    + (x.ok == null ? '<td class=brv>—</td>' : '<td class="brv '+rtOkCls(x.ok)+'">'+esc(fmtPct(x.ok))+'</td>')
    + '<td class=brv>'+esc(rtMs(x.ms))+'</td></tr>';
  const fold = restN > 0 ? '<tr class=rtfold data-rtfold role=button tabindex=0 aria-expanded="'+rtRankOpen+'"><td colspan=5>'
    + '<span class=hsc aria-hidden=true>'+(rtRankOpen ? '▾' : '▸')+'</span>'+esc(T('{n} more').replace('{n}', restN))+'</td></tr>' : '';
  return h + '<table class="brt rtrk"><thead><tr><th>'+esc(T('Tool'))+'</th><th class=brv>'+esc(T('Calls'))+'</th><th></th><th class=brv>'
    + esc(T('Success'))+'</th><th class=brv>'+esc(T('Average'))+'</th></tr></thead><tbody>'
    + top.map(row).join('') + fold + '</tbody>'
    // Server caps the rest list; the rows it left out are named, not silently dropped.
    + (restN > 0 ? '<tbody class=rtrest'+(rtRankOpen ? '' : ' hidden')+'>'+rest.map(row).join('')
      + (restN > rest.length ? '<tr><td colspan=5 class=hidnote>'+esc(T('{n} more not shown').replace('{n}', (restN - rest.length)))+'</td></tr>' : '')
      + '</tbody>' : '')
    + '</table>';
}
// Card ② time spent — server `time` = rank rows sorted by tms (calls × mean ms); fms = failed share of that time (0-100).
function rtTime(r){
  const k = r.time || {}, rows = (k.rows || []).filter(x => (x.tms || 0) > 0), restN = k.restN || 0;
  const h = '<div class=brh2>'+esc(T('Time spent'))+' <i>'+esc(rtPer(r, k.from || (r.rank || {}).from))+' · '+esc(T('OTel tally'))+'</i></div>';
  if(!rows.length) return h + '<div class=hidnote>'+esc(T('No tool time recorded yet — it appears once OTel tool results arrive'))+'</div>';
  const mx = Math.max(1, ...rows.map(x => x.tms)), nm = n => n === '기타' ? T('Other') : n;
  const fc = p => p >= 20 ? 'rterr' : p >= 5 ? 'rtwarn' : '';   // ⚠colour only a share worth a look; 0-4% stays neutral
  return h + '<table class="brt rtrk"><thead><tr><th>'+esc(T('Tool'))+'</th><th class=brv>'+esc(T('Total time'))+'</th><th></th>'
    + '<th class=brv title="'+esc(T('Share of the total time spent on failed calls'))+'">'+esc(T('Failed share'))+'</th></tr></thead><tbody>'
    + rows.map(x => '<tr><td class=brn title="'+esc(nm(x.n))+'">'+esc(nm(x.n))+'</td><td class=brv>'+esc(rtMs(x.tms))+'</td>'
      + '<td class=brg><span class=brb><i style="width:'+Math.max(1, x.tms/mx*100).toFixed(1)+'%;background:'+thc('#4fa8b8', '#2f8394')+'"></i></span></td>'
      + (x.fms == null ? '<td class=brv>—</td>' : '<td class="brv '+fc(x.fms)+'">'+esc(fmtPct(x.fms))+'</td>')+'</tr>').join('')
    + (restN > 0 ? '<tr><td colspan=4 class=hidnote>'+esc(T('{n} more not shown').replace('{n}', restN))+'</td></tr>' : '')
    + '</tbody></table>'
    // Older stored days carry no failed duration, so their failed time reads as 0.
    + '<div class=hidnote>'+esc(T('Failed share counts only days since failed-time collection began'))+'</div>';
}
// Card ③ cache rewrites — server `cache`: per-day cache-creation share of cache tokens + top sessions (metadata only).
function rtCache(r){
  const c = r.cache || {}, dl = (c.days || []).filter(x => (x.read || 0) + (x.create || 0) > 0), ss = c.sessions || [];
  const h = '<div class=brh2 title="'+esc(T('Cache tokens written (created) as a share of cache tokens written + read — a high share means the prompt cache kept being rebuilt'))+'">'
    + esc(T('Cache rewrites'))+' <i>'+esc(T('Last {n} days').replace('{n}', r.days))+' · '+esc(T('creation share of cache tokens'))+'</i></div>';
  if(!dl.length && !ss.length) return h + '<div class=hidnote>'+esc(T('No cache split stored yet — it appears once OTel API requests arrive'))+'</div>';
  const col = thc('#e8913a', '#b8641a'), H = 64, mx = Math.max(1, ...dl.map(x => x.pct || 0)), every = dl.length > 10 ? 5 : 1;
  const bars = dl.length ? '<div class=rtb>' + dl.map((x, i) => {
    const tip = x.d + ' · ' + T('Created', 'cache') + ' ' + fmtTok(x.create || 0) + ' · ' + T('Read', 'cache') + ' ' + fmtTok(x.read || 0);
    const lab = (i % every === 0 || i === dl.length - 1) ? esc(String(x.d).slice(5).replace('-', '/')) : '';
    return '<div class=rtc title="'+esc(tip)+'"><span class=rts style="height:'+(H+14)+'px">'
      + '<i style="height:'+Math.max(1, Math.round((x.pct || 0) / mx * H))+'px;background:'+col+'"></i><b class=rtz>'+esc(fmtPct(x.pct || 0))+'</b></span>'
      + '<span class=rtl>'+lab+'</span></div>'; }).join('') + '</div>' : '';
  const tb = ss.length ? '<table class="brt rtcs"><thead><tr><th>'+esc(T('Sessions with the highest share'))+'</th><th class=brv>'+esc(T('Created', 'cache'))+'</th><th class=brv>'
    + esc(T('Read', 'cache'))+'</th><th class=brv>'+esc(T('Share', 'cache'))+'</th></tr></thead><tbody>'
    + ss.map(x => '<tr><td class=brd title="'+esc((x.path || '')+' · '+T('session id')+' '+(x.sid || ''))+'">'+esc(x.project || x.path || '?')
      + ' <s>'+esc(String(x.sid || '').slice(0, 8))+'</s></td><td class=brv>'+esc(fmtTok(x.create || 0))+'</td><td class=brv>'+esc(fmtTok(x.read || 0))+'</td>'
      + '<td class=brv style="color:'+col+'">'+esc(fmtPct(x.pct || 0))+'</td></tr>').join('')
    + '</tbody></table>' : '';
  return h + bars + tb;
}
// Card ④ activity by hour — server `heat` (otel._otel_src_heat): 7 weekday rows (Mon first) x 24 local hours, [requests, tokens].
const RT_WD = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const rtLv = (c, mx) => c > 0 ? Math.min(5, Math.ceil(5 * c / Math.max(1, mx))) : 0;
function rtHeat(r){
  const k = r.heat || {}, cells = Array.isArray(k.cells) ? k.cells : [];
  // ⚠bysrc keeps 8 days: when its oldest bucket is newer than the range start, rtPer names the collection start.
  const st = Math.max(+k.from || 0, +k.since || 0), dt = st ? new Date(st * 1000) : null;
  const f = dt ? rtYmd(dt) : '';
  const h = '<div class=brh2>'+esc(T('Activity by hour'))+' <i>'+esc(rtPer(r, f))+' · '+esc(T('OTel API requests · local time'))+'</i></div>';
  if(!(k.n > 0) || cells.length !== 7) return h + '<div class=hidnote>'+esc(T('No OTel API requests in this range — the grid fills once they arrive'))+'</div>';
  let mx = 0;
  cells.forEach(row => (row || []).forEach(c => { mx = Math.max(mx, +(c || [])[0] || 0); }));
  const hrs = '<span></span>' + Array.from({length: 24}, (_, i) => '<span class=rthh>'+(i % 3 ? '' : i)+'</span>').join('');
  const body = cells.map((row, d) => '<span class=rthd>'+esc(T(RT_WD[d]))+'</span>'
    + Array.from({length: 24}, (_, i) => {
      const c = (row || [])[i] || [0, 0], n = +c[0] || 0, lv = rtLv(n, mx);
      const tip = T(RT_WD[d]) + ' ' + rtP2(i) + ':00–' + rtP2(i) + ':59 · ' + T('Requests') + ' ' + n.toLocaleString() + ' · ' + T('Tokens') + ' ' + fmtTok(+c[1] || 0);
      return '<i class="rthc'+(lv ? ' rth'+lv : '')+'" title="'+esc(tip)+'"></i>'; }).join('')).join('');
  return h + '<div class=rth style="--rth:'+thc('#5b8def', '#3a6fd4')+'">' + hrs + body + '</div>';
}
// Card ⑤ models — server `models` (otel._otel_src_models): rows sorted by tokens, kinds main/agent/side = [requests, tokens].
// [dark, light] per family, the same hue in both themes; unknown ids fall back to grey.
const RT_MFAM = {opus: ['#b07acc', '#8f55ad'], sonnet: ['#5b8def', '#3a6fd4'], haiku: ['#4fa8b8', '#2f8394']};
const RT_MKIND = [['main', 'Main'], ['agent', 'Subagent'], ['side', 'Side calls']];
// claude-opus-5-5 / claude-sonnet-4-5-20250929 / claude-3-5-haiku-20241022 -> [family, «Opus 5.5»]; anything else -> [null, id].
function rtMdl(id){
  const s = String(id || ''), m = /^claude-(?:(\d{1,2})-(?:(\d{1,2})-)?)?(opus|sonnet|haiku)(?:-(\d{1,2})(?:-(\d{1,2}))?)?(?:-\d{8})?(?:\[1m\])?$/.exec(s);
  if(!m) return [null, s];
  const v = m[4] ? m[4] + (m[5] ? '.' + m[5] : '') : m[1] ? m[1] + (m[2] ? '.' + m[2] : '') : '';
  return [m[3], m[3].charAt(0).toUpperCase() + m[3].slice(1) + (v ? ' ' + v : '')];
}
function rtModels(r){
  const k = r.models || {}, rows = (Array.isArray(k.rows) ? k.rows : []).filter(x => (+x.tokens || 0) > 0 || (+x.count || 0) > 0);
  const st = Math.max(+k.from || 0, +k.since || 0), dt = st ? new Date(st * 1000) : null;
  const f = dt ? rtYmd(dt) : '';
  const h = '<div class=brh2>'+esc(T('Models'))+' <i>'+esc(rtPer(r, f))+' · '+esc(T('OTel API tokens by model'))+'</i></div>';
  if(!(k.n > 0) || !rows.length) return h + '<div class=hidnote>'+esc(T('No OTel API requests in this range — models appear once they arrive'))+'</div>';
  rows.sort((a, b) => (+b.tokens || 0) - (+a.tokens || 0));
  const tot = Math.max(1, rows.reduce((s, x) => s + (+x.tokens || 0), 0));
  const kl = RT_MKIND.map(([, l], i) => '<em><b class="rtmk rtmk'+i+'" style="--rtm:'+thc('#8b95a7', '#6b7385')+'"></b>'+esc(T(l))+'</em>').join('');
  return h + '<table class="brt rtrk rtmd"><thead><tr><th>'+esc(T('Model'))+'</th><th class=brv>'+esc(T('Tokens'))+'</th><th class=brv>'
    + esc(T('Share'))+'</th><th class=brv>'+esc(T('Requests'))+'</th><th></th></tr></thead><tbody>'
    + rows.map(x => {
      const oth = x.model === 'other', [fam, nm] = oth ? [null, T('Other')] : rtMdl(x.model), c = RT_MFAM[fam] || ['#8b95a7', '#6b7385'];
      const col = thc(c[0], c[1]), tk = +x.tokens || 0, sh = tk / tot * 100, ks = x.kinds || {};
      const segs = RT_MKIND.map(([kk], i) => { const t = +((ks[kk] || [])[1]) || 0;
        return t > 0 ? '<i class="rtmk'+i+'" style="width:'+(tk ? t / tk * 100 : 0).toFixed(1)+'%"></i>' : ''; }).join('');
      const tip = RT_MKIND.map(([kk, l]) => { const v = ks[kk] || [0, 0];
        return T(l) + ' ' + fmtTok(+v[1] || 0) + ' · ' + T('Requests') + ' ' + (+v[0] || 0).toLocaleString(); }).join('\n');
      return '<tr><td class=brn title="'+esc(oth ? T('Other') : String(x.model))+'"><b class=rtmdot style="background:'+col+'"></b>'+esc(nm)+'</td>'
        + '<td class=brv>'+esc(fmtTok(tk))+'</td><td class=brv>'+esc(fmtPct(sh))+'</td><td class=brv>'+(+x.count || 0).toLocaleString()+'</td>'
        + '<td class=brg title="'+esc(tip)+'"><span class=brb><span class=rtms style="width:'+Math.max(1, sh).toFixed(1)+'%;--rtm:'+col+'">'+segs+'</span></span></td></tr>';
    }).join('') + '</tbody></table><div class="wktl rtlg">'+kl+'</div>';
}
// Card ⑥ hook cost — server `hooks` (otel_hooks): rows by event type sorted by ms desc. ⚠`ev` is data: esc() only, never T().
function rtHooks(r){
  const k = r.hooks || {}, rows = (Array.isArray(k.rows) ? k.rows : []).filter(x => x && ((+x.count || 0) > 0 || (+x.ms || 0) > 0));
  const h = '<div class=brh2>'+esc(T('Hook cost'))+' <i>'+esc(rtPer(r, k.from))+' · '+esc(T('OTel hook runs by event type'))+'</i></div>';
  if(!rows.length) return h + '<div class=hidnote>'+esc(T('No hook runs recorded yet — they appear once OTel hook events arrive'))+'</div>';
  return h + '<table class="brt rtrk rthk"><thead><tr><th>'+esc(T('Event type'))+'</th><th class=brv>'+esc(T('Runs'))+'</th><th class=brv>'
    + esc(T('Total time'))+'</th><th class=brv title="'+esc(T('Time of one event firing across all its matching hooks'))+'">'+esc(T('Average'))+'</th><th class=brv>'
    + esc(T('Failures'))+'</th></tr></thead><tbody>'
    + rows.map(x => { const f = +x.fail || 0;
      return '<tr><td class=brn title="'+esc(String(x.ev))+'">'+esc(String(x.ev))+'</td><td class=brv>'+(+x.count || 0).toLocaleString()+'</td>'
        + '<td class=brv>'+esc(rtMs(+x.ms || 0))+'</td><td class=brv>'+esc(rtMs(+x.avg || 0))+'</td>'
        + '<td class="brv'+(f > 0 ? ' rtwarn' : '')+'">'+f.toLocaleString()+'</td></tr>'; }).join('')
    + '</tbody></table>';
}
function rtWeeks(r){
  const w = r.weeks || [];
  return '<table class=brt><thead><tr><th>'+esc(T('W'))+'</th><th class=brv>'+esc(T('Tokens'))+'</th><th class=brv>'+esc(T('Cost'))+'</th><th class=brv>'
    + esc(T('Sessions'))+'</th><th class=brv>'+esc(T('Commits'))+'</th><th class=brv>'+esc(T('Failures'))+'</th><th>'+esc(T('Top projects'))+'</th></tr></thead><tbody>'
    + w.map(x => '<tr><td class=brn>'+esc(x.from.slice(5).replace('-','/'))+'~'+esc(x.to.slice(5).replace('-','/'))
        + (x.days < 7 ? ' <s>'+U(x.days,'d')+'</s>' : '')+'</td>'
      + '<td class=brv>'+fmtTok(x.tok)+'</td><td class=brv>'+(x.cost ? money(x.cost) : '—')+'</td>'
      + '<td class=brv>'+x.sessions+'</td><td class=brv>'+x.commits+'</td><td class=brv>'+x.fails+'</td>'
      + '<td class=brd title="'+esc((x.top||[]).map(p => p.project+' '+fmtTok(p.tok)).join(' · '))+'">'+(x.top||[]).map(p => esc(p.project)+' <s>'+fmtTok(p.tok)+'</s>').join(' · ')+'</td></tr>').join('')
    + '</tbody></table>';
}
function rtProjects(r){
  const p = r.projects || [];
  if(!p.length) return '<div class=hidnote>'+esc(T('No sessions were active in this period.'))+'</div>';
  const mx = Math.max(1, ...p.filter(x => x.tpc).map(x => x.tpc));
  // Numeric headers carry .brv so they right-align over their right-aligned values (⚠left-aligned they sat ~150px left of «13M» at 1100).
  return '<table class="brt rtpj"><thead><tr><th>'+esc(T('Project'))+'</th><th class=brv>'+esc(T('Tokens'))+'</th><th class=brv>'+esc(T('Sessions'))+'</th><th class=brv>'
    + esc(T('Commits'))+'</th><th class=brv>'+esc(T('Tokens per commit'))+'</th><th></th></tr></thead><tbody>'
    + p.map((x, i) => '<tr><td class=brn title="'+esc(x.project)+'"><span style="color:'+wkc(i)+'">■</span> '+esc(x.project)+'</td>'
      + '<td class=brv>'+fmtTok(x.tok)+'</td><td class=brv>'+x.sessions+'</td>'
      + '<td class=brv'+(x.commits === null ? ' title="'+esc(T('Not a git repository, or the path is gone'))+'"' : '')+'>'
        + (x.commits === null ? '—' : x.commits)+'</td>'
      // ★2026-09-27 QA: a bare «—» gave no reason; say why (no repo, or no commits to divide by).
      + '<td class=brv'+(x.tpc ? '' : ' title="'+esc(T(x.commits === null ? 'Not a git repository, or the path is gone' : 'No commits to divide by'))+'"')+'>'
        + (x.tpc ? fmtTok(x.tpc) : '—')+'</td>'
      + '<td class=brg>'+(x.tpc ? '<span class=brb><i style="width:'+Math.max(1, x.tpc/mx*100).toFixed(1)
        + '%;background:'+wkc(i)+'"></i></span>' : '')+'</td></tr>').join('')
    + '</tbody></table>';
}
// Account picker row above the OTel cards ('' below 2 accounts); failure, weekly and commit cards always stay All.
// Under a pick, days before the server's acctSince carry no account and count under All only — say so when that falls in range.
function rtAcctHead(r){
  const pk = acctPickHtml('retro'); if(!pk) return '';
  const s = String((r && r.acct && r.acctSince) || ''), okS = /^\d{4}-\d{2}-\d{2}$/.test(s);
  const s0 = new Date(); s0.setDate(s0.getDate() - (((r && r.days) || 7) - 1));
  const since = rtYmd(s0);
  const ln = okS && s > since ? ' <i>' + esc(T('Records before {date} have no account').replace('{date}', (+s.slice(5, 7)) + '/' + (+s.slice(8, 10)))) + '</i>' : '';
  return '<div class=hidnote>' + pk + ln + '</div>';
}
function paintRetro(){
  if(mainView !== 'retro') return;
  const box = document.getElementById('feed');
  if(!box) return;
  const apFo = acctPickFocusId();   // ⚠innerHTML below replaces the picker
  const tabs = RETRO_STEPS.map(x => '<button class="wkrgb'+(x === (retroBusy ? retroWant : retroDays) ? ' on' : '')+'" data-rd="'+x+'">'
    + esc(T('Last {n} days').replace('{n}', x))+'</button>').join('');
  const r = RETRO;
  // Aggregation time is a debug number — tooltip only; the heading keeps just the age.
  const meta = (r && r.ok) ? '<i title="'+esc((r.ms||0)+'ms '+T('measured'))+'">'+agoSec(r.at)+'</i>' : '';
  // Range buttons (+ loading hint) live in the header toolbar slot.
  tbSlot('retro', '<span class="tbg rtrg">'+tabs+(retroBusy ? ' <i>'+esc(T('Loading…', 'read'))+'</i>' : '')+'</span>');
  // Age only (header names the tab); no age yet = no row.
  const head = (meta ? '<div class=tlhd>'+meta+'</div>' : '')
    + '<div class=hidnote>'+esc(T('Sources are the token index, failure records and local git — only projects, counts and tokens are shown (no conversation).'))+'</div>';
  let body;
  // ⚠While switching ranges the old range's charts stayed up for ~3 s with only a dim hint — show the loading box instead.
  if(!r || retroBusy) body = '<div class=strload><b>'+esc(T('Loading insights…'))+'</b><br>'
      + esc(T('Gathering failures, tokens and commits — 30 days takes a few seconds the first time.'))+'</div>';
  else if(r.off) body = '<div class=hidnote>'+esc(T('The Insights feature is off'))+'</div>';
  else if(!r.ok) body = '<div class=hidnote>'+esc(T('Could not read'))+' — '+esc(TV({msg: r.msg || 'Unknown', vars: r.vars}))+'</div>';
  else {
    // Two rows of two panels; `.split2` splits side by side only when the feed is wide (container query in 50-layout-feed.css).
    const tools = rtTools(r);
    body = '<div class="rtg'+(tools ? ' split2' : '')+'"><section class=rtp>'
      + '<div class=brh2 title="'+esc(T('Counted by re-reading failure records in the transcripts — «Tools failing most» on the right counts only tool calls received over OTel since the server started'))+'">'
      + esc(T('Failure trend'))+' <i>'+esc(T('Last {n} days').replace('{n}', r.days))+' · '+esc(T('transcript records'))+' · '+esc(T('daily · by kind'))+' · '+esc(T('Total'))+' '+r.fails+'</i></div>'
      + rtFailChart(r) + rtSigs(r) + '</section>' + (tools ? '<section class=rtp>'+tools+'</section>' : '') + '</div>'
      // OTel cards: ① tool ranking | ② time spent side by side, ③ cache rewrites full width (its day bars need the room).
      + rtAcctHead(r)
      + '<div class="rtg split2"><section class=rtp>' + rtRank(r) + '</section><section class=rtp>' + rtTime(r) + '</section></div>'
      + '<div class=rtg><section class=rtp>' + rtCache(r) + '</section></div>'
      + '<div class=rtg><section class=rtp>' + rtHeat(r) + '</section></div>'
      + '<div class=rtg><section class=rtp>' + rtModels(r) + '</section></div>'
      + '<div class=rtg><section class=rtp>' + rtHooks(r) + '</section></div>'
      + '<div class="rtg split2"><section class=rtp>'
      + '<div class=brh2>'+esc(T('Weekly summary'))+' <i>'+esc(T('weeks start Monday'))+'</i></div>' + rtWeeks(r) + '</section><section class=rtp>'
      + '<div class=brh2>'+esc(T('Tokens per commit'))+' <i>'+esc(T('local branch commits · only those touching that folder'))+'</i></div>' + rtProjects(r)
      + '</section></div>';
  }
  box.innerHTML = '<div class=rtw>' + head + body + '</div>';
  rtBind(box);
  acctPickWire('retro', () => { RETRO = null; retroAt = 0; loadRetro(true); }, apFo);   // view-only pick; the main account is never written
  document.querySelectorAll('#tbretro [data-rd]').forEach(b => b.onclick = () => {
    if(!loadRetro(false, +b.dataset.rd)) note(T('Still aggregating — press again in a moment'));
  });
}
