// «Usage | Tools» view switch for the token tab (default «Usage»; tools = 47-tools.js). ⚠A stored 'pipe'/'harness' (moved to their own tab) falls back to 'use'.
const TKVIEWS = ['use', 'tools'];
let TKVIEW = TKVIEWS.includes(lsGet('sidereus.tkview', 'use')) ? lsGet('sidereus.tkview', 'use') : 'use';
function tkViewSeg(){
  return '<div class=tkvs>' + [['use', 'Usage'], ['tools', 'Tools']].map(([k, en]) => '<button class="wkrgb'
    + (k === TKVIEW ? ' on" aria-pressed="true' : '" aria-pressed="false') + '" data-tv="' + k + '">' + esc(T(en)) + '</button>').join('') + '</div>';
}
document.addEventListener('click', e => {
  const b = e.target.closest && e.target.closest('.wkrgb[data-tv]');
  if(!b || b.dataset.tv === TKVIEW) return;
  const hadF = document.activeElement === b;
  TKVIEW = TKVIEWS.includes(b.dataset.tv) ? b.dataset.tv : 'use';
  lsSet('sidereus.tkview', TKVIEW);
  paintToken();
  if(hadF) kbHold('.wkrgb[data-tv].on');   // ⚠the repaint drops focus to <body> (08 kbHold)
});
function tkBar(v, mx, col){
  return '<span class=brb><i style="width:'
      + Math.max(1, Math.min(100, v / Math.max(1, mx) * 100)).toFixed(1) + '%;background:'+col+'"></i></span>';
}
// Colour index per row = the project's index in the weekly project table; unknown projects take the next free slots.
function tkProjIdx(rows, ref){
  const at = new Map(ref.map((x, i) => [x.name, i]));
  let nx = ref.length;
  return rows.map(r => at.has(r.name) ? at.get(r.name) : nx++);
}
function paintToken(){
  if(mainView !== 'token') return;
  const box = document.getElementById('feed');
  if(!box) return;
  // ⚠Period buttons sit in the «Period totals» title line they control (the header toolbar was ~360px above it); clicks stay delegated (.wkrgb).
  tbSet('token', tkViewSeg());   // sub-view switch lives in the header toolbar slot, like Branches/Insights
  if(TKVIEW === 'tools'){ paintTools(box); return; }
  const wkrBtns = [1,7,30].map(x => '<button class="wkrgb'
    + (x === WKRANGE ? ' on' : '') + '" data-r="' + x + '">' + esc(T(WKR_LABEL[x])) + '</button>').join('');
  const d = WKU, b = (d && d.burn) || null;
  // A failed fetch with nothing held says so with a retry — «Measuring…» is only for a server that is measuring.
  if(d && d.err){ box.innerHTML = '<div class="hidnote cwerr">'
      + esc(T('Could not read the token report — check the server'))
      + ' <button type=button class=tkretry>'+esc(T('Retry'))+'</button></div>'; return; }
  if(!b || !b.at){ box.innerHTML = '<div class=tlhd><i>'+esc(T('Measuring…'))+'</i></div>'; return; }
  const lim = burnLim();    // ★2026-09-27 cross-tab audit: back-solved 5h limit; 0 (no %) until measured
  const pct = v => lim ? (v / lim * 100) : 0;
  const bar = tkBar;
  const mx = Math.max(1, ...(b.rows || []).map(r => r.ctx));
  const ci = tkProjIdx(b.rows || [], ((WKR && WKR.rows) || []).filter(x => x.tok > 0));
  const rows = (b.rows || []).map((r, i) => {
    const col = wkc(ci[i]);   // ⚠by project, not row: the context table sorts differently from the project table
    return '<tr><td class=brn><span style="color:'+col+'">■</span> '+esc(TN(r.name))+'</td>'
      + '<td class=brv>'+fmtTok(r.ctx)+'</td>'
      + '<td class=brg>'+bar(r.ctx, mx, col)+'</td>'
      + '<td class=brv>'+r.req+'</td>'
      + '<td class=brv>'+fmtTok(r.med)+'</td>'
      + '<td class=brv>'+fmtTok(r.per)+T('/min')+'</td>'
      + '<td class=brv>'+(lim ? fmtPct(pct(r.ctx)) : '—')+'</td></tr>';
  }).join('');
  const subs = (b.subs || []).map(x =>
    '<tr><td class=brn>'+(x.run?'<b class=brdot></b>':'<b class="brdot off"></b>')
      + esc(x.type)+(x.depth>1?' <s>'+T('depth {n}', 'tight').replace('{n}', x.depth)+'</s>':'')+'</td>'
      + '<td class=brv>'+x.req+'</td>'
      + '<td class=brd>'+esc(x.proj)+'</td><td class=brd>'+esc(plStrip(x.desc))+'</td></tr>').join('');
  const ses = (b.sess || []).map(x =>
    '<tr><td class=brn>'+esc(x.proj)+' <s>'+esc(x.id)+'</s></td>'
      + '<td class=brd>'+new Date(x.born*1000).toLocaleString(LOC(),{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})+'</td>'
      + '<td class=brv>'+(x.win === b.win && x.win != null ? '<em class=brok>'+fmtTok(x.win)+'</em>'
        : x.win != null ? '<em class=brbad>'+fmtTok(x.win)+' <s>'+esc(T('previous'))+'</s></em>'
        : '<em class=brbad>'+esc(T('previous setting'))+'</em>')+'</td></tr>').join('');
  const ago = Math.max(0, Math.round(Date.now()/1000 - b.at));
  const agch = tkAgentCost(d);
  const rng = tkRange();
  const apFo = typeof acctPickFocusId === 'function' ? acctPickFocusId() : '';   // ⚠innerHTML below replaces the picker
  // Caption only: the header title already names the tab.
  box.innerHTML = '<div class=brep><div class="wvh wvht"><span>' + esc(agoSec(b.at)) + '</span></div>'
    + wkTab(d) + tkPlat(d)
    + '<div class=brh><b>'+esc(T('Period totals'))+'</b><span class=wkrt2>'+wkrBtns+'</span>'
      + (typeof acctPickHtml === 'function' ? acctPickHtml('tok') : '')   // '' below 2 accounts; scopes only this block
      + '<i>' + (WKR && WKR.at ? new Date(WKR.at*1000).toLocaleTimeString(LOC())+' '+esc(T('measured'))+' · '
        + esc(T(WKRANGE === 30 ? 'every hour' : 'every 15 min')) : 'ccusage') + '</i></div>'
    + rng
    + '<div class=brh><b>'+esc(T('Token burn report'))+'</b><i>'+TV({msg: 'Last {n} min · counted {m}s ago · every 30s', vars: {n: b.min, m: ago}})+'</i></div>'
    + '<div class=brsum>'+esc(T('Total'))+' <b>'+fmtTok(b.tot)+'</b>'
      + (lim ? TV({msg: ' · <b>{n}</b> of the 5h limit', vars: {n: fmtPct(pct(b.tot))}}) : '')
      + TV({msg: ' · {n}/min · {m} requests', vars: {n: fmtTok(Math.round(b.tot/Math.max(1,b.min))), m: (b.rows||[]).reduce((a,r)=>a+r.req,0)}})+'</div>'
    + '<table class=brt><thead><tr><th>'+esc(T('Project'))+'</th><th>'+esc(T('Context'))+'</th><th></th><th>'+esc(T('Requests'))+'</th>'
      + '<th>'+esc(T('Per request'))+'</th><th>'+esc(T('Per minute'))+'</th><th>'+esc(T('Of limit'))+'</th></tr></thead><tbody>'+rows+'</tbody></table>'
    + '<div class="bsp'+(subs || agch ? ' split2' : '')+'"><div>'
    // ⚠`b.subs` = every subagent with requests in the burn window (burn_scan), finished ones included — the dot marks
    // the running ones. Titling it «running now» listed agents that had ended an hour ago.
    + (subs ? '<div class=brh2>'+esc(TV({msg: 'Subagents, last {n} min', vars: {n: b.min}}))
        +' <i>'+esc(T('most requests first · dot = running now'))+'</i></div>'
        + '<table class=brt><thead><tr><th>'+esc(T('Type'))+'</th><th>'+esc(T('Requests'))+'</th><th>'+esc(T('Project'))+'</th><th>'+esc(T('Doing'))+'</th></tr></thead>'
        + '<tbody>'+subs+'</tbody></table>' : '')
    + agch + '</div><div>'
    + '<div class=brh2>'+esc(T('Compaction window per session'))+' <i>'+esc(T('Each session keeps the setting it started with'))+(b.win ? ' · '+esc(T('Current'))+' '+fmtTok(b.win) : '')+'</i></div>'
    + '<table class=brt><thead><tr><th>'+esc(T('Sessions'))+'</th><th>'+esc(T('Started'))+'</th><th>'+esc(T('Window'))+'</th></tr></thead><tbody>'+ses+'</tbody></table>'
    + '</div></div></div>';
  if(typeof acctPickWire === 'function') acctPickWire('tok', () => { WKR = null; wkrAt = 0; paintToken(); loadWkRange(true); }, apFo);
}
// ★**Agent cost table** (2026-09-21) — there was no other place answering "which agent spent how much".
// The "running subagents" above only says how many requests right now.
// ⚠Lifetime totals — independent of the period buttons. Hence a "last" column (it exposes idle agents
// still sitting at the top). Type is `agentType` from `agent-*.meta.json`;
// rows without that sidecar group under `?` — not filled by guessing.
function tkAgentCost(d){
  const bar = tkBar;
  const ac = d && d.agc;
  let agch = '';
  if(ac && ac.at && (ac.rows||[]).length){
    const amx = Math.max(1, ...ac.rows.map(r => r.cost));
    const shr = ac.all ? (ac.sub / ac.all * 100) : 0;
    agch = '<div class=brh2>'+esc(T('Subagent cost table'))+' <i>'+esc(T('All-time total · biggest cost first'))+' · '
        + Math.round(ac.ms)+'ms '+esc(T('to aggregate · every 2 min'))+'</i></div>'
      + '<div class=brsum>'+esc(T('Subagents'))+' <b>'+fmtMoney(ac.sub)+'</b> · '+fmtTok(ac.subtok)
        + TV({msg: ' · {n} calls · {m} types — <b>{x}</b> of {k} total', vars: {n: ac.n.toLocaleString(), m: ac.types, k: fmtMoney(ac.all), x: fmtPct(shr)}})+'</div>'
      + '<table class=brt><thead><tr><th>'+esc(T('Subagent'))+'</th><th>'+esc(T('Cost'))+'</th><th></th><th>'+esc(T('Calls'))+'</th>'
        + '<th>'+esc(T('Average'))+'</th><th>'+esc(T('Tokens'))+'</th><th>'+esc(T('Last'))+'</th></tr></thead><tbody>'
      + ac.rows.map((r,i) => '<tr><td class=brn><span style="color:'+wkc(i)+'">■</span> '
          + esc(r.type)+'</td><td class=brv>'+fmtMoney(r.cost)+'</td>'
          + '<td class=brg>'+bar(r.cost, amx, wkc(i))+'</td>'
          + '<td class=brv>'+r.n+'</td><td class=brv>'+fmtMoney(r.avg)+'</td>'
          + '<td class=brv>'+fmtTok(r.tok)+'</td>'
          + '<td class=brv'+(r.last?' title="'+esc(stamp(r.last))+'"':'')+'>'
          + (r.last?agoAt(r.last):'—')+'</td></tr>').join('')
      + '</tbody></table>';
  }
  return agch;
}
// Per-project totals for the period picked in the toolbar (ccusage). Tables below are 'now' (last 60 min), independent of period.
function tkRange(){
  const bar = tkBar;
  let rng = '';
  if(!WKR) loadWkRange();          // Never fetched yet — fetch now (throttle prevents duplicates)
  if(WKR && WKR.err){ rng = '<div class=hidnote>'+esc(T('Could not read the period totals'))+' — '+esc(T(WKR.err))+'</div>'; }
  else if(!WKR || !WKR.at){ rng = '<div class=hidnote>'+esc(T(WKR_DESC[WKRANGE]))+' '+esc(T('totals are being measured.'))+'</div>'; }
  else {
    const rr = (WKR.rows||[]).filter(x=>x.tok>0);
    const tt = WKR.total || rr.reduce((a,x)=>a+x.tok,0);
    const cc = rr.reduce((a,x)=>a+(x.cost||0),0);
    const rmx = Math.max(1, ...rr.map(x=>x.tok));
    // ★Daily trend — **lines**. Bars (composition) show "what shape now" but
    // not "where it is heading". Total is a faint area, top 3 projects + other overlay as lines
    // (a line-graph combination). Data is the already-fetched daily/trend.
    const dl = WKR.daily || [];
    // Today's point adds the live share since the last ccusage run (carried over from the removed aside «Daily» bars).
    const pk = WKR.acct || '';   // live share has no account: none under a pick
    const td = WKR.today || (WKU && WKU.today), add = pk ? 0 : ((WKU && WKU.at === WKR.at) ? WKU.liveAdd : WKR.liveAdd) || 0;
    if(WKU && WKU.at !== WKR.at) loadWkRange();   // other range: its own liveAdd, refreshed on the 60s throttle
    const lnh = tkTrend(dl, td, add), dth = tkDailyTable(dl, tkTot(dl, td, add), td), mixh = tkMix(WKR.mix || {}), moh = tkModels();
    rng = '<div class=brsum title="'+esc(T(SCOPE_PC_TIP))+'">'+esc(T(WKR_DESC[WKRANGE]))+' '+esc(T('Total'))
        // Scope in words: Claude only, and no live share since the last count (the platform table adds it).
        + ' <small>('+esc(T('this PC · all projects'))+(pk ? ' · '+esc(pk) : '')+' · Claude · '+esc(T('excl. live share'))+')</small> <b>'+fmtTok(tt)+'</b> · '+fmtMoney(cc)
        + TV({msg: ' · {n} projects · ', vars: {n: rr.length}})+esc(T('Daily average'))+' '+fmtTok(Math.round(tt/Math.max(1,WKR.days||1)))+'</div>'
      + lnh + dth
      // Mix + models | projects side by side when #feed is wide (`.split2`, container query in 50-layout-feed.css).
      + '<div class="bsp'+(mixh || moh ? ' split2' : '')+'"><div>' + mixh + moh + '</div><div>'
      + '<table class=brt><thead><tr><th>'+esc(T('Project'))+'</th><th>'+esc(T('Tokens'))+'</th><th></th><th>'+esc(T('Cost'))+'</th><th>'+esc(T('Share'))+'</th></tr></thead><tbody>'
      + rr.map((x,i) => '<tr><td class=brn><span style="color:'+wkc(i)+'">■</span> '+esc(TN(x.name))+'</td>'
          + '<td class=brv>'+fmtTok(x.tok)+'</td><td class=brg>'+bar(x.tok, rmx, wkc(i))+'</td>'
          + '<td class=brv>'+fmtMoney(x.cost||0)+'</td>'
          + '<td class=brv>'+(tt ? fmtPct(x.tok/tt*100) : '—')+'</td></tr>').join('')
      + '</tbody></table></div></div>';
  }
  return rng;
}
// Per-day totals shared by the trend line and the daily table; today's point adds the live share.
function tkTot(dl, td, add){ return dl.map(x => x.tok + (x.d === td ? add : 0)); }
// «Daily» table, newest first. ⚠Cost has no live share (only tokens do), so today's cost cell says so in a tooltip.
// ⚠Fixed-height scroll box: a 30-row table would push everything below it when the range changes.
function tkDailyTable(dl, tot, td){
  if(!dl.length) return '';
  const row = i => {
    const x = dl[i], top = Array.isArray(x.top) ? x.top.slice(0, 2) : [], isT = x.d === td;
    const wd = T(WKDN_EN[new Date(x.d + 'T12:00:00').getDay()]);
    return '<tr' + (isT ? ' class=today' : '') + '><td class=brn>' + esc(x.d.slice(5).replace('-', '/')) + ' <s>' + esc(wd) + '</s></td>'
      + '<td class=brv>' + fmtTok(tot[i], {zero: 1}) + '</td>'
      + '<td class=brv' + (isT ? ' title="' + esc(T('Cost excludes the live share since the last count')) + '"' : '') + '>' + fmtMoney(x.cost || 0) + '</td>'
      + '<td class=tkdtp>' + (top.length ? top.map(p => esc(TN(p.name)) + ' <s>' + fmtTok(p.tok) + '</s>').join(' · ') : '–') + '</td></tr>';
  };
  return '<div class=brh2>' + esc(T('Daily')) + '</div><div class=tkdtw><table class="brt tkdt"><thead><tr><th>' + esc(T('Date')) + '</th><th class=brv>' + esc(T('Tokens'))
    + '</th><th class=brv>' + esc(T('Cost')) + '</th><th>' + esc(T('Top projects')) + '</th></tr></thead><tbody>'
    + dl.map((x, i) => row(dl.length - 1 - i)).join('') + '</tbody></table></div>';
}
// Daily trend lines (total area + top projects) for the picked period; '' with fewer than 2 days.
function tkTrend(dl, td, add){
    let lnh = '';
    if(dl.length > 1){
      const W = 300, H = 82, PAD = 4;
      const tot = tkTot(dl, td, add);
      const tr = (WKR.trend || []).filter(t => (t.series || []).length === dl.length);
      // Nice y ticks: step = smallest 1/2/5x10^n >= max/4, so the axis has 2-4 steps ending on a round value.
      const raw = Math.max(1, ...tot), e10 = Math.max(1, Math.pow(10, Math.floor(Math.log10(raw / 4))));
      const step = [1, 2, 5, 10].map(m => m * e10).find(v => v >= raw / 4);
      const mv = Math.ceil(raw / step) * step;
      const px = i => i / (dl.length - 1) * W;
      const py = v => H - PAD - (v / mv) * (H - PAD * 2);
      const pth = a => a.map((v,i) => (i ? 'L' : 'M') + px(i).toFixed(1) + ',' + py(v).toFixed(1)).join(' ');
      const sd = x => x.slice(5).replace('-', '/');
      const yt = [];
      for(let v = 0; v <= mv + step / 2; v += step) yt.push(v);
      const grid = yt.map(v => '<path class=gl d="M0,'+py(v).toFixed(1)+' L'+W+','+py(v).toFixed(1)+'"/>').join('');
      const ylab = '<div class=rgy>' + yt.map(v =>
          '<i style="top:'+(py(v)/H*100).toFixed(2)+'%">'+fmtTok(v, {zero: 1})+'</i>').join('') + '</div>';
      const xi = dl.length > 2 ? [0, Math.floor((dl.length-1)/2), dl.length-1] : [0, dl.length-1];
      const xlab = '<div class=rgx>' + xi.map((i,k) =>
          // ⚠No inline `left` on the last label — it beat `.a1{left:auto}` and pushed the label past the right edge (h-scroll).
          '<i class="'+(k===0?'a0':(k===xi.length-1?'a1':''))+'"'
          + (k===xi.length-1 ? '' : ' style="left:' + (px(i)/W*100).toFixed(2)+'%"')+'>'+esc(sd(dl[i].d))+'</i>').join('') + '</div>';
      // ⚠The svg stretches (preserveAspectRatio=none), so dots are HTML on top — an svg circle drew as a ~4x-wide ellipse.
      const dot = (a, c) => '<i class=rgdot style="background:'+c+';left:100%;top:'+(py(a[a.length-1])/H*100).toFixed(2)+'%"></i>';
      TKTR = {d: dl.map(x => sd(x.d)), tot: tot, tr: tr.map((t,i) => ({n: TN(t.name), s: t.series, c: wkc(i)})),
              y: v => py(v) / H * 100};
      lnh = '<div class=rgw>' + ylab + xlab + '<div class=rgp>'
        + '<svg class=rgs viewBox="0 0 '+W+' '+H+'" preserveAspectRatio=none>'
        + '<defs><linearGradient id=rgg x1=0 y1=0 x2=0 y2=1>'
          + '<stop offset="0%" stop-color="#7e8896" stop-opacity=".22"/>'
          + '<stop offset="100%" stop-color="#7e8896" stop-opacity="0"/></linearGradient></defs>'
        + grid
        + '<path class=ar d="'+pth(tot)+' L'+W+','+H+' L0,'+H+' Z"/>'
        + '<path class=tl d="'+pth(tot)+'"/>'
        + tr.map((t,i) => '<path class=ln style="stroke:'+wkc(i)+'" d="'+pth(t.series)+'"/>').join('')
        + '</svg>' + tr.map((t,i) => dot(t.series, wkc(i))).join('')
        + '<i class=rgcur hidden></i><div class=rgtip hidden></div></div></div>'
        + '<div class=rglg><span><em style="background:#7e8896"></em>'+T('All')+' <b>'
          + fmtTok(tot.reduce((a,b)=>a+b,0))+'</b></span>'
        + tr.map((t,i) => '<span><em style="background:'+wkc(i)+'"></em>'
            + esc(TN(t.name))+' <b>'+fmtTok(t.tok)+'</b></span>').join('')
        + (add ? '<span title="'+esc(T('Live share since the last fetch (estimate)'))+'">'
            + TV({msg: 'today +{n} live', vars: {n: fmtTok(add)}})+'</span>' : '') + '</div>';
    }
    return lnh;
}
// Hover on the trend: nearest day -> guide line + tooltip (date, total, top series). Token counts only.
let TKTR = null;
document.addEventListener('mousemove', e => {
  const p = e.target.closest && e.target.closest('.rgp');
  document.querySelectorAll('.rgp').forEach(q => { if(q !== p){ q.querySelector('.rgcur').hidden = true; q.querySelector('.rgtip').hidden = true; } });
  if(!p || !TKTR) return;
  const r = p.getBoundingClientRect(), n = TKTR.d.length;
  const i = Math.max(0, Math.min(n - 1, Math.round((e.clientX - r.left) / Math.max(1, r.width) * (n - 1))));
  const x = n > 1 ? i / (n - 1) * 100 : 0;
  const cur = p.querySelector('.rgcur'), tip = p.querySelector('.rgtip');
  cur.hidden = false; cur.style.left = x + '%';
  tip.innerHTML = '<b>' + esc(TKTR.d[i]) + '</b><span><em style="background:#7e8896"></em>' + esc(T('All'))
    + ' <s>' + fmtTok(TKTR.tot[i], {zero: 1}) + '</s></span>'
    + TKTR.tr.map(t => '<span><em style="background:' + t.c + '"></em>' + esc(t.n) + ' <s>' + fmtTok(t.s[i], {zero: 1}) + '</s></span>').join('');
  tip.hidden = false;
  // Flip to the left of the guide past the middle so the tip never leaves the chart.
  const left = x > 50;
  tip.style.left = left ? '' : 'calc(' + x + '% + 10px)';
  tip.style.right = left ? 'calc(' + (100 - x) + '% + 10px)' : '';
});
// ★Composition — where it burns. This bar shows directly that "speak briefly" can only cut
// output's 0.15% share. What to cut is context per request (= cache reads).
function tkMix(mx){
    // ★light swatches 2.25-2.96 -> 3.9-4.8:1 on #f4f5f7 (same hues, darker)
    const MIXK = [['cr','Cache read',thc('#5b8def','#2b6fd6')], ['cc','Cache write',thc('#e8913a','#b8650f')],
                  ['out','Output',thc('#5fa96a','#3a8a3e')], ['in','Input',thc('#b07acc','#8a52bd')]];   // ⚠labels go through T() below
    let mixh = '';
    if(mx.tot > 0){
      mixh = '<div class=mixbar>'
        + MIXK.map(([k,,c]) => '<span style="flex:'+(mx[k]||0)+';background:'+c+'"></span>').join('')
        + '</div><div class=mixlg>'
        + MIXK.map(([k,lb,c]) => '<span><em style="background:'+c+'"></em>'+esc(T(lb))
            + ' <b>'+fmtPct(mx[k]/mx.tot*100)+'</b> '+fmtTok(mx[k]||0)+'</span>').join('')
        + '</div>'
        // How many times each cache build was reused. Falling means sparse use, paying TTL-expiry rewrites.
        + '<div class=mixnote>'+esc(T('Cache reuse'))+' <b style="color:' + thc('#cfe0f2', 'var(--nx-t1)') + '">'+(mx.ratio||0)+T('x')+'</b>'
          + ' '+esc(T('— a cache written once was read back that many times (reads cost 0.1x · writes 1.25x)'))+'</div>';
    }
    return mixh;
}
// With a single model it is one 100% row that only takes space — shown only when mixed
// External CLI cost: «≈ $x.xx» estimate (null = no priced request). ⚠Display only — never added to Claude totals.
function extCostStr(c){ return c == null ? '—' : '≈ ' + fmtMoney(c); }
// Window length in minutes -> «30d» / «5h» / «90m»; 0 or missing -> «window».
function extWinLbl(m){
  return !m ? T('window') : m % 1440 === 0 ? TV({msg: '{n}d', vars: {n: m / 1440}}) : m % 60 === 0 ? TV({msg: '{n}h', vars: {n: m / 60}}) : TV({msg: '{n}m', vars: {n: m}});
}
// The platform's own limit windows (extUsage[k].rate, e.g. Codex 5h/weekly) — only sent when its record had them.
function extRateStr(rt){
  const ws = ['primary', 'secondary'].map(k => rt && rt[k]).filter(Boolean)
    .map(x => (x.win ? extWinLbl(x.win) + ' ' : '') + fmtPct(x.pct));
  return ws.length ? T('limit') + ' ' + ws.join(' · ') : '';
}
// Per-window detail (label · used % · reset) + plan; escaped HTML, or plain text with `raw` (tooltips escape later).
// ⚠Shows only what the CLI last reported — never filled in.
function extRateDetail(rt, k, raw){
  const ws = ['primary', 'secondary'].map(n => rt && rt[n]).filter(Boolean)
    .map(x => extWinLbl(x.win) + ' ' + fmtPct(x.pct)
      + (x.reset ? ' · ' + TV({msg: 'resets {t}', vars: {t: hhmm(x.reset, {date: 'other'})}}) : ''));
  // Plan is the CLI's own string: TV substitutes it after translation, so it never goes through T().
  const s = !ws.length ? (k === 'cx' ? T('No limit data') : '')
    : ws.join(' · ') + (rt.plan ? ' · ' + TV({msg: 'plan {p}', vars: {p: rt.plan}}) : '');
  return raw ? s : esc(s);
}
function extCostTip(c, miss, k){
  if(c == null) return T('Model not in the price table');
  return T('Estimated cost') + ' ' + extCostStr(c) + ' — '
    + T(k === 'cx' ? 'Estimate from OpenAI API list prices · a ChatGPT login is not billed per token' : 'Estimate from Google list prices · actual charge is 0 on the free tier')
    + (miss ? '\n' + TV({msg: '{n} requests left out (model not in the price table)', vars: {n: miss}}) : '');
}
// «By platform» today — Claude from ccusage (WKU), others from their own chat files (state().extUsage).
// ⚠Only Claude has a 5h/7d limit; other rows' cost is an estimate and never enters the quota figures.
function tkPlat(d){
  const ex = EXTU || {}, ks = Object.keys(ex).filter(k => ex[k]);
  if(!ks.length) return '';
  const t = d && (d.daily || []).find(x => x.d === d.today);
  const nc = (SESS || []).filter(x => (!x.plat || x.plat === 'cc') && x.state !== 'done').length;
  // `cell` = cost cell inner HTML incl. its tag attrs; Claude is exact, others are «≈» estimates.
  const row = (p, tok, cell, sub, n) => '<tr><td class=brn>' + aiLogo(p) + ' ' + esc(platName(p)) + '</td>'
    + '<td class=brv>' + fmtTok(tok) + '</td>' + cell + '<td class=brd>' + sub + '</td><td class=brv>' + n + '</td></tr>';
  const rows = (t ? row('cc', t.tok + (d.liveAdd || 0), '<td class=brv>' + fmtMoney(t.cost || 0) + '</td>',
                        esc(T('this PC · incl. subagents')) + ' · ' + esc(T('Counts toward the 5h/7d limits')), nc) : '')
    + ks.map(k => { const e = ex[k], rd = extRateDetail(e.rate, k);
        return row(k, e.tok, '<td class=brv title="' + esc(extCostTip(e.cost, e.costMiss, k)) + '">' + extCostStr(e.cost) + '</td>',
          esc(T('Input')) + ' ' + fmtTok(e.in) + ' · ' + esc(T('Cache')) + ' ' + fmtTok(e.cache)
          + ' · ' + esc(T('Output')) + ' ' + fmtTok(e.out) + ' · ' + esc(T('Thinking')) + ' ' + fmtTok(e.thought)
          + (rd ? ' · ' + rd : ''), e.n_sessions); }).join('');
  return '<div class=brh><b>' + esc(T('By platform')) + '</b><i>' + esc(T('Today')) + ' · '
    + esc(T('Limits are Claude only · other platforms’ cost is estimated')) + '</i></div>'
    + '<table class=brt><thead><tr><th>' + esc(T('Platform')) + '</th><th>' + esc(T('Tokens')) + '</th><th>' + esc(T('Cost'))
    + '</th><th>' + esc(T('Breakdown')) + '</th><th>' + esc(T('Sessions')) + '</th></tr></thead><tbody>' + rows + '</tbody></table>';
}
function tkModels(){
    const mo = (WKR.models || []).filter(x => x.tok > 0);
    let moh = '';
    if(mo.length > 1){
      const mot = mo.reduce((a,x)=>a+x.tok, 0);
      moh = '<table class=brt><thead><tr><th>'+esc(T('Model'))+'</th><th>'+esc(T('Tokens'))+'</th><th>'+esc(T('Cost'))+'</th><th>'+esc(T('Share'))+'</th></tr></thead><tbody>'
        + mo.map((x,i) => '<tr><td class=brn><span style="color:'+wkc(i)+'">■</span> '
            + esc(TN(x.name))+'</td><td class=brv>'+fmtTok(x.tok)+'</td>'
            + '<td class=brv>'+fmtMoney(x.cost)+'</td>'
            + '<td class=brv>'+(mot ? fmtPct(x.tok/mot*100) : '—')+'</td></tr>').join('')
        + '</tbody></table>';
    }
    return moh;
}
// «Token widgets on the right» (default off): on keeps donut/daily/today/live in the aside; off moves them to the token tab and 5h card.
let WKSIDE = null;
function wkSide(){ if(WKSIDE !== null) return WKSIDE; try{ return UIS.getItem('sidereus.wkside') === '1'; }catch(e){ return false; } }
function wkSideSet(on){ WKSIDE = !!on; lsSet('sidereus.wkside', on ? '1' : '0'); wkSideApply(); }
function wkSideApply(){ document.body.classList.toggle('wkside', wkSide()); }
wkSideApply();
function buildWku(){
  const el = document.getElementById('wku');
  if(!el) return;
  if(!wkSide()){ el.innerHTML = ''; return; }   // hidden by CSS; keeps loadLive from redrawing an invisible `.wkrt`
  const d = WKU;
  el.innerHTML = wkDonut(d, d ? wkDaily(d) + wkTrend(d) + wkLive(d) : '');
}
// Token tab: weekly donut beside today-by-project (the aside copies only show when the setting is on).
function wkTab(d){
  return '<div class=wktab><div class=wktabc>' + wkDonut(d, '') + '</div>'
    + '<div class=wktabc>' + (d && !d.err ? wkTrend(d, true) + tkTopRuns(d) : '') + '</div></div>';
}
// «Top 5 costly runs today» — subagent runs by tokens (server agc.top, 2-min TTL); metadata only, click opens the work log.
let AGT_ND = '1';
function tkTopRuns(d){
  const tp = (d && d.agc && d.agc.top) || {}, rs = tp[AGT_ND] || [];
  if(!tp['1'] && !tp['7']) return '';
  const mx = rs.length ? rs[0].tok : 1;
  const dur = s => s == null ? '—' : actDur(s);
  const tg = ['1', '7'].map(k => '<button class="atpb' + (k === AGT_ND ? ' on' : '') + '" data-nd="' + k + '">'
    + esc(k === '1' ? T('Today') : T('7 days')) + '</button>').join('');
  return '<div class="wktr atp"><div class=wktrh><b>' + esc(AGT_ND === '1' ? T('Top 5 costly runs today')
      : T('Top 5 costly runs · 7 days')) + '</b><span class=atpg>' + tg + '</span></div>'
    + (rs.length ? '<div class=wktq>' + rs.map((r, i) => {
      const col = wkc(i), ok = r.tid && r.cwd;
      return '<div class="wktqr atpr' + (ok ? ' atpk' : '') + '"' + (ok ? ' data-cwd="' + esc(r.cwd) + '" data-tid="' + esc(r.tid) + '"' : '')
        + ' title="' + esc((plStrip(r.desc) || '—') + ' · ' + r.type + ' · ' + r.proj + ' · ' + (r.tok || 0).toLocaleString()
          + T(' tokens') + (r.end ? ' · ' + stamp(r.end) : '')) + '">'
        + '<b style="background:' + col + '"></b><span>' + esc(plStrip(r.desc) || '—') + '</span>'
        + '<code>' + esc(r.type) + '</code><span class=atpn>' + esc(TN(r.proj)) + '</span>'
        + '<em><i style="width:' + (r.tok / Math.max(1, mx) * 100).toFixed(1) + '%;background:' + col + '"></i></em>'
        + '<s>' + fmtTok(r.tok) + '</s><s>' + dur(r.dur) + '</s><u>' + fmtPct(r.share) + '</u></div>';
    }).join('') + '</div>'
    : '<div class=hidnote>' + esc(T('No subagent runs in this period')) + '</div>') + '</div>';
}
document.addEventListener('click', e => {
  const b = e.target.closest && e.target.closest('.atpb');
  if(b){ AGT_ND = b.dataset.nd; paintToken(); return; }
  const r = e.target.closest && e.target.closest('.atpr.atpk');
  if(r) openAgent(r.dataset.cwd, r.dataset.tid);
});
// Weekly donut block as HTML; `tail` is appended in every branch (aside: daily/today/live · token tab: '').
function wkDonut(d, tail){
  if(!d) return '<div class=wkh>'+esc(T('Weekly tokens'))+'</div><div class=hidnote>'+esc(T('Loading…'))+'</div>';
  // ★The three pieces have **different data sources and are drawn independently** (otherwise live was hidden
  // until weekly tokens loaded).
  // Weekly donut, daily = ccusage (20-100s · once per 5 min)
  // Live                = OTel (`out["live"]` — server computes immediately, unconditionally, zero cost)
  // Before, it `return`ed before weekly was ready, hiding the live graph that was already in hand.
  // ⇒ Every branch below exits with `tail` appended. Missing pieces return '' from their own function.
  // ★If a forced refresh gave up at the cap (`WKU_WAIT_TICKS`), **write that down** — quitting silently
  // makes old values look new and the user sees "clicked, nothing happened". Same wording frame/class as the existing err branch.
  const gup = wkuGiveUp
    ? '<div class="hidnote cwerr">'+TV({msg: 'Waited {n}s for a refresh but no new value came — press ↻ to measure again', vars: {n: WKU_WAIT_SEC}})+'</div>' : '';
  if(d.err) return '<div class=wkh>'+esc(T('Weekly tokens'))+'<button class=wkr title="'+esc(T('Measure again'))+'">↻</button></div>'
      + '<div class="hidnote cwerr">'+esc(T('Could not read'))+' — '+esc(T(d.err))+'</div>' + tail;
  const rows = (d.rows||[]).filter(r => r.tok > 0);
  const tot = d.total || rows.reduce((a,r)=>a+r.tok,0);
  // ★Separate "not measured yet" from "measured, nothing there" — saying the latter while the server runs ccusage for 26s is a lie
  // ⚠After giving up, this branch also needs ↻ — otherwise the button the text points to is not on screen
  if(!d.at) return '<div class=wkh>'+esc(T('Weekly tokens'))+' <i>'+esc(wkuGiveUp?T('Not measured'):T('Measuring'))+'</i>'
      + (wkuGiveUp ? '<button class=wkr title="'+esc(T('Measure again'))+'">↻</button>' : '') + '</div>'
      + (gup || '<div class=hidnote>'+esc(T('ccusage takes about 20s — the live chart below shows first'))+'</div>') + tail;
  if(!rows.length || !tot) return '<div class=wkh>'+esc(T('Weekly tokens'))+'</div>' + gup
      + '<div class=hidnote>'+TV({msg: 'No records in the last {n} days', vars: {n: (d.days||7)}})+'</div>' + tail;
  // Donut — circumference set to 100, slices via stroke-dasharray (no path math needed)
  const R = 15.9155, C = 2*Math.PI*R;
  let off = 0;
  const arcs = rows.map((r,i)=>{
    const frac = r.tok/tot, len = frac*C;
    const a = '<circle class=wkarc r="'+R+'" cx="21" cy="21" fill="none" stroke="'+wkc(i)+'"'
      + ' stroke-width="7" stroke-dasharray="'+len.toFixed(3)+' '+(C-len).toFixed(3)+'"'
      + ' stroke-dashoffset="'+(-off).toFixed(3)+'" data-i="'+i+'">'
      + '<title>'+esc(TN(r.name)+' · '+fmtTok(r.tok)+' ('+fmtPct(frac*100)+')')+'</title></circle>';
    off += len;
    return a;
  }).join('');
  // ★Legend also shows **token amount** (2026-08-27) — % alone says "uses a lot" but not how much
  const legend = rows.map((r,i)=>
    '<div class=wkl title="'+esc(TN(r.name)+' · '+r.tok.toLocaleString()+TV({msg: ' tokens · {n} d', vars: {n: r.days}}))+'">'
    + '<span class=wkd style="background:'+wkc(i)+'"></span>'
    + '<span class=wkn>'+esc(TN(r.name))+'</span>'
    + '<span class=wkv>'+fmtTok(r.tok)+'</span>'
    + '<span class=wkp>'+fmtPct(r.tok/tot*100)+'</span></div>').join('');
  const when = d.at ? new Date(d.at*1000) : null;
  const wago = when ? Math.max(0, Math.round((Date.now()-when.getTime())/60000)) : null;
  return '<div class=wkh>'+esc(T('Weekly tokens'))+' <i>'+TV({msg: 'Last {n} days · by project', vars: {n: (d.days||7)}})+'</i>'
    + '<button class="wkr'+(d.busy?' spin':'')+'" title="'
    + esc(TV({msg: 'Measure again · last fetched {t}', vars: {t: wago===null ? '?' : (wago<1 ? T('just now') : AGO(U(wago,'m')))}}))
    + '">↻</button></div>' + gup
    + '<div class=wkbox><svg class=wksvg viewBox="0 0 42 42" aria-label="'+esc(T('Weekly token share'))+'">'
    + '<circle r="'+R+'" cx="21" cy="21" fill="none" stroke="#1c2husk" stroke-width="7"/>'.replace('#1c2husk',thc('#1b2129','#e3e6ea'))
    + arcs
    + '<text x="21" y="20.4" class=wkt1>'+fmtTok(tot)+'</text>'
    + '<text x="21" y="24.6" class=wkt2>'+esc(T('Tokens'))+'</text></svg>'
    + '<div class=wkls>'+legend+'</div></div>' + tail;
}
// ↻ is delegated: the donut can be drawn in the aside and the token tab at once, so ids/onclick would collide.
document.addEventListener('click', e => { const b = e.target.closest && e.target.closest('.wkr'); if(b) wkuForce(); });
// ★Only the live sparkline refreshes **every 3s** (it must move in real time).
// Why separate: `/api/wkuse` carries today's per-project totals, weekly donut and burn in one response,
// so it was tied to 30s — but live buckets are 10s and OTel arrives every 3s.
// The 30s poll was the bottleneck: data was already on the server, only the screen looked frozen.
// `/api/live` is just a bucket fold (a few KB response), so pulling it to 3s costs nothing.
// ⚠Not called while the tab is hidden — no reason for a background tab to knock every 3s all day.
const LIVE_EVERY = 3000;
// ⚠One request at a time: on a stalled server 3s ticks piled up 7 pending /api/live and used up the browser's 6 connections per host.
let liveBusy = false;
async function loadLive(){
  if(document.hidden || !WKU) return;      // If the card does not exist yet, loadWku draws it first
  if(CONN.fails) return;                   // server down: the poll backs off; a 3s knock would only add console errors
  if(liveBusy) return;
  let j;
  liveBusy = true;
  try{ j = await getJSON('/api/live', {timeout: 10000}); }
  catch(e){ return; }                      // Ignore quietly — another call comes in 3s
  finally{ liveBusy = false; }
  if(!j || !j.live) return;
  WKU.live = j.live; WKU.liveSec = j.liveSec; WKU.liveStep = j.liveStep;
  const html = wkLive(WKU);
  // Replace every instance in place
  document.querySelectorAll('.wkrt').forEach(el => { try{ el.outerHTML = html; }catch(e){ softErr('wkLive', e); } });
}
// On a failed fetch keep the last good snapshot (html.agstale marks it old) — replacing it with {err} drew
// the live rate as «0/min» and dropped «Today 400M». {err} only when nothing good was ever held.
function keepGood(prev, msg){ return prev && prev.at && !prev.err ? prev : {err: msg}; }
document.addEventListener('click', e => { if(e.target.closest && e.target.closest('.tkretry')) loadWku(true); });
async function loadWku(force, hard){
  const now = Date.now();
  // If the server has never measured or is measuring, ask often (drops to 5-min interval once values arrive)
  // ★Even after values arrive, **ask lightly every 20s** (today's tokens must refresh periodically).
  // Only ccusage (20s) is heavy and it runs only on `force` — this request reads the server's held values
  // and recomputes only today's live share (liveAdd) (measured 0.00s). At 5 min today's bar was frozen.
  // ★Live sparkline added, so pulled to 10s (response is 0.02-0.11s)
  // ★30s period. This request reads the server's held
  // values and recounts only today's live share, so it is cheap (measured 0.02-0.11s) — heavy
  // ccusage runs only on `force`. It was 10s, but the value is not worth checking that often.
  const gap = 30000;
  if(!force && (document.hidden || now - wkuAt < gap)) return;   // hidden: the visibilitychange poll refreshes once
  wkuAt = now;
  const prevAt = (WKU && WKU.at) || 0;
  try{ WKU = await getJSON('/api/wkuse'+(hard?'?force=1':'')); }
  catch(e){ WKU = keepGood(WKU, 'Could not fetch'); }
  // ★Clear the 'gave up' marker when a new value arrives — the 30s poll keeps running after giving up,
  // so a value may arrive later. Leaving the warning up until then would be a lie.
  if(WKU && WKU.at && WKU.at !== prevAt) wkuGiveUp = false;
  buildWku();
  if(mainView === 'token') paintToken();
}
// ★Forced refresh (2026-08-27) — the server only measures every 15 min, so sometimes the "current value" is wanted.
// Clicking makes the server re-measure in background (26s); meanwhile the screen watches for `at` to change.
// ⚠Does not await the response — awaiting blocks that request for 26s and delays polling too.
let wkWatch = 0, wkuGiveUp = false;   // wkuGiveUp — whether we gave up at the cap (buildWku writes it on screen)
async function wkuForce(){
  const was = (WKU && WKU.at) || 0;
  wkuGiveUp = false;                  // Clicked again — clear the earlier give-up marker
  await loadWku(true, true);
  clearInterval(wkWatch);
  let n = 0;
  wkWatch = setInterval(async () => {
    n++;
    await loadWku(true);
    if(WKU && WKU.at && WKU.at !== was){ clearInterval(wkWatch); return; }
    // ★Cap is `WKU_WAIT_TICKS` (= 300s). Before, only this place used 20 ticks (60s) while `loadWkRange` used 100,
    // so they diverged — cold measurement for 30 days is 51s, so 60s falls short even once (see constant comment above).
    // ⚠If giving up, **write it on screen and exit** — quitting silently leaves the user at "clicked, nothing happened".
    if(n > WKU_WAIT_TICKS){ clearInterval(wkWatch); wkuGiveUp = true; buildWku(); }
  }, WKU_TICK_MS);
}
