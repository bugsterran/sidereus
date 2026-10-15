// Participant panel — id, role, last read/sent. Status dot comes from **cursor and send time** (not guessed).
// Why: a room conversation showed no one present, so context was missing.
// ★Weekly tokens — donut **per project** (2026-08-27). Per-session values do not exist:
// ccusage only reports per project slug (per-project view confirmed acceptable).
// ⚠`session --since` only **selects sessions** by period and returns their **lifetime totals**, so it is not weekly.
// Only `daily --instances --since` is a true period total (see server comment).
// Donut is one SVG — no external library (this page must load without network).
const WKC = ['#5b8def','#e8913a','#5fa96a','#b07acc','#d96a6a','#4fa8b8','#c9a227','#8b95a7'];
// Light-theme twins (same hues as RT_KIND's light pair): ⚠WKC on the light panel fell to 2.25:1, below 3:1 for UI marks.
// Dark enough for white bar labels at >=4.5:1 (#b8641a 4.31 · #3f8a4b 4.24 · #2f8394 4.38 · #937411 4.42 were below).
const WKC_LT = ['#3a6fd4','#a8581a','#387e44','#8f55ad','#c04444','#2a7786','#846810','#6b7385'];
const wkc = i => thc(WKC[i % WKC.length], WKC_LT[i % WKC_LT.length]);
let WKU = null, wkuAt = 0;
// Daily bars — today's cell stacks **ccusage share + live share since last fetch**
// Sun-Sat rainbow pastels. Saturation picked to read on the dark background (#12161d).
const WKDC = ['#f0a6a6','#f2c19b','#efe1a0','#aade9f','#9ed6d0','#a3c4f0','#c9aeea'];
const WKDN_EN = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
function wkDaily(d){
  const dl = d.daily || [];
  if(!dl.length) return '';
  const add = d.liveAdd || 0;
  const val = x => x.tok + ((x.d === d.today) ? add : 0);
  const mx = Math.max(1, ...dl.map(val));
  // ⚠H + live piece + value/date labels (~39px) must fit .wkdb (88px); 54 in 74px overflowed into the header note.
  const H = 42;
  const bars = dl.map(x => {
    const isT = (x.d === d.today);
    const bh = Math.max(x.tok > 0 ? 2 : 1, Math.round(x.tok / mx * H));
    const ah = (isT && add) ? Math.max(2, Math.round(add / mx * H)) : 0;
    const v = val(x);
    // ★`new Date('2026-09-03')` parses as **UTC midnight** and lands a day early in KST — append a time to make it local
    const wd = new Date(x.d + 'T00:00:00').getDay();
    const col = thc(WKDC, ['#d95f5f','#c26a1e','#9a7a12','#4f9a4a','#2f9a90','#3f7fd6','#8a62c9'])[wd];   // pastels vanish on white; every entry >=3:1 on #f4f5f7 (orange/yellow were 2.45/2.22)
    const tip = x.d + T('(' + WKDN_EN[wd] + ')') + ' · ' + v.toLocaleString() + T(' tokens')
      + (x.cost ? ' · $' + x.cost : '')
      + (ah ? TV({msg: '\nof which {n} is live since the last fetch (estimate)', vars: {n: add.toLocaleString()}}) : '')
      + (v === 0 ? T('\nNo records on this day') : '');
    return '<div class="wkdc'+(isT?' today':'')+'" title="'+esc(tip)+'">'
      + '<span class=wkdz'+(isT?' style="color:'+col+'"':'')+'>'+(v ? fmtTok(v) : '')+'</span>'
      + '<span class=wkdv style="height:'+(bh+ah)+'px;background:'+col+'">'
        + (ah ? '<i style="height:'+ah+'px"></i>' : '') + '</span>'
      + '<span class=wkdl'+(isT?' style="color:'+col+'"':'')+'>'
        + esc(x.d.slice(5).replace('-','/'))+'</span></div>';
  }).join('');
  // ★Do not add live here — different data source (daily=ccusage, live=OTel).
  // It used to include `+ wkLive(d)`, so **when daily was empty, live vanished too.**
  return '<div class=wkdy><div class=wkdh><b>'+esc(T('Daily'))+'</b>'
    + '<i>'+(add ? TV({msg: 'today +{n} live', vars: {n: fmtTok(add)}}) : TV({msg: 'last {n} days', vars: {n: dl.length}}))+'</i></div>'
    + '<div class=wkdb>'+bars+'</div></div>';
}
// Live sparkline — drawn as **per-minute rate (moving average)**
// ★Raw values look wrong (2026-09-03). OTel sends one request's
// tokens **all at once** (hundreds of thousands incl. cache reads), so buckets go `· · · █ ▂ ·`,
// flickering on and off — not a usage spike but **samples arriving in clumps**.
// So a 60s moving window draws **tokens/min**: the meaning is clear and it scrolls one cell per poll
// smoothly. The line is a midpoint curve, not a polyline.
// ★**Today only · one horizontal bar** (2026-09-04, today at 30s granularity). One row per project
// means 4 rows eating vertical space, while the only question is
// "who used how much today" — a **share**; one split bar reads at a glance.
// ccusage has no hourly data, so the server counts from transcripts itself (measured 0.75s / 192MB · every 30s).
// Colors use WKC in the **same order** as the donut legend — the eye must link them to trace causes.
function wkTrend(d, list){
  const it = d.intraday || {};
  const by = (it.by || []).filter(x => (x.tok || 0) > 0);
  if(!by.length) return '';
  const tot = by.reduce((a, x) => a + (x.tok || 0), 0);
  if(!tot) return '';
  const segs = by.map((x, i) => {
    const col = wkc(i);
    const pct = x.tok / tot * 100;
    // ★No time-of-day axis (it made the chart harder to read).
    // The only question is "who used how much today" — adding times adds more to read.
    return '<i style="width:'+pct.toFixed(2)+'%;background:'+col+'" title="'
      + esc(TN(x.name) + ' · ' + (x.tok||0).toLocaleString() + T(' tokens · ') + fmtPct(pct))
      + '">' + (pct >= 11 ? '<s>'+esc(TN(x.name))+' '+fmtPct(pct)+'</s>' : '') + '</i>';
  }).join('');
  const legend = by.map((x, i) =>
    '<em title="'+esc(TN(x.name)+' · '+(x.tok||0).toLocaleString()+T(' tokens'))+'">'
    + '<b style="background:'+wkc(i)+'"></b>'+esc(TN(x.name))
    + '<s>'+fmtTok(x.tok||0)+'</s></em>').join('');
  const ago = it.at ? Math.max(0, Math.round(Date.now()/1000 - it.at)) : null;
  return '<div class=wktr><div class=wktrh><b>'+esc(T('Today by project'))+'</b>'
    + '<i title="'+esc(T('Tokens used since midnight today, split by project')
        + T('(counted straight from transcripts · recounted every 30s).')
        + (it.cut ? '\n' + T('⚠Very large transcripts are read only in their last 60MB — early hours may be missing.') : '')
        + (ago !== null ? '\n' + TV({msg: 'counted {n}s ago', vars: {n: ago}}) : ''))+'">'
    + T('Today')+' · '+T('this PC · all projects')+' · '+fmtTok(tot) + (it.cut ? ' · ' + T('tail-capped') : '') + '</i></div>'
    + '<div class=wktb>'+segs+'</div>'
    + (list ? wkTrendList(by, tot) : '<div class=wktl>'+legend+'</div>') + '</div>';
}
// Token tab only: the cell sits beside the ~200px donut, so a one-line legend left it mostly empty ⇒ top-6 rows (same data).
function wkTrendList(by, tot){
  const top = by.map((x, i) => ({x, i})).sort((a, b) => b.x.tok - a.x.tok).slice(0, 6);
  const mx = top.length ? top[0].x.tok : 1;
  return '<div class=wktq>' + top.map(({x, i}) => {
    const pct = x.tok / tot * 100;
    return '<div class=wktqr title="'+esc(TN(x.name)+' · '+(x.tok||0).toLocaleString()+T(' tokens · ')+fmtPct(pct))+'">'
      + '<b style="background:'+wkc(i)+'"></b><span>'+esc(TN(x.name))+'</span>'
      + '<em><i style="width:'+(x.tok / mx * 100).toFixed(1)+'%;background:'+wkc(i)+'"></i></em>'
      + '<s>'+fmtTok(x.tok||0)+'</s><u>'+fmtPct(pct)+'</u></div>';
  }).join('') + (by.length > 6 ? '<div class=wktqm>+'+(by.length - 6)+'</div>' : '') + '</div>';
}
// Live-rate math for the sidebar chart (wkLive).
function wkLiveCalc(d){
  const step = d.liveStep || 10;
  // ★Draw **0** even with no data (the graph must stay visible when live data is absent,
  // e.g. halted by token expiry). Previously the graph disappeared in two places:
  // (a) no `d.live` at all (weekly response failed) → drew nothing
  // (b) bucket sum 0 → **replaced** with "no records in the last N min" text
  // Both look "broken". Quiet is **a value of 0**; axis and baseline must stay so one can tell
  // a quiet period from a dead screen.
  const nb = Math.max(1, Math.round((d.liveSec || 600) / step));
  const L = (d.live && d.live.length) ? d.live : new Array(nb).fill(0);
  const M = Math.round((d.liveSec || L.length*step) / 60);
  const win = Math.max(1, Math.round(60 / step));      // 60s window = this many buckets
  // rate[i] = tokens used in the 60s up to that point (= tokens/min). Early points use only the samples available.
  const rate = L.map((_, i) => {
    let s = 0, c = 0;
    for(let j = Math.max(0, i - win + 1); j <= i; j++){ s += L[j]; c++; }
    return c ? Math.round(s * win / c) : 0;
  });
  const tot = L.reduce((a,x)=>a+x,0);
  const now = rate[rate.length-1];
  // ★Baseline: **the rate that spends the 5h limit in exactly 5h** (limit/300min). Faster burns the block early.
  // Coloring by absolute numbers breaks whenever the limit changes — derive the baseline from the limit.
  const lim = burnLim();    // ★2026-09-27 cross-tab audit: back-solved limit, never the anchor
  const pace = lim ? Math.round(lim / 300) : 0;
  // Bands — multiple of baseline. Without a known limit, no color bands (do not paint by guesswork).
  const BAND = [[0.5,thc('#5fd3ba','#1a7f6a'),T('Easy')],[1,thc('#5b8def','#1b5fd6'),T('Normal')],[2,thc('#e8b478','#a35c00'),T('Fast')],[1e9,thc('#e0736c','#c11e32'),T('Very fast')]];
  let col = '#5b8def', lab = '', ratio = 0;
  if(pace && now){
    ratio = now / pace;
    const b = BAND.find(x => ratio < x[0]) || BAND[BAND.length-1];
    col = b[1]; lab = b[2];
  }
  // Y axis is chosen so **the baseline is always visible** — otherwise it clips off the top and comparison fails
  const mx = Math.max(1, ...rate, pace ? pace * 1.15 : 0);
  const W = 100, H = 60;
  const px = i => (rate.length < 2 ? 0 : (i / (rate.length - 1)) * W);
  const py = v => H - (v / mx) * (H - 3);
  // Midpoint curve (quadratic) — so the line has no sharp corners
  let line = 'M' + px(0).toFixed(2) + ',' + py(rate[0]).toFixed(2);
  for(let i = 1; i < rate.length; i++){
    const x0 = px(i-1), y0 = py(rate[i-1]), x1 = px(i), y1 = py(rate[i]);
    const mxp = ((x0 + x1) / 2).toFixed(2), myp = ((y0 + y1) / 2).toFixed(2);
    line += ' Q' + x0.toFixed(2) + ',' + y0.toFixed(2) + ' ' + mxp + ',' + myp;
  }
  line += ' L' + px(rate.length-1).toFixed(2) + ',' + py(now).toFixed(2);
  const area = line + ' L'+W+','+H+' L0,'+H+' Z';
  const tip = TV({msg: 'Last {m} min · one point every {s}s · 60s moving window · refreshed every 3s', vars: {m: M, s: step}})
    + TV({msg: '\nRate now: {n} tokens/min', vars: {n: now.toLocaleString()}})
    + (pace ? TV({msg: '\nBaseline: {n} tokens/min', vars: {n: pace.toLocaleString()}})
            + T(' (the rate that spends the 5h limit in exactly 5h)')
            + TV({msg: '\nNow at {r}x baseline — {l}', vars: {r: ratio.toFixed(2), l: lab}}) : '')
    + TV({msg: '\nWindow total: {n} tokens', vars: {n: tot.toLocaleString()}})
    + T('\n\nValues OTel records per request as it happens (not ccusage · no delay).')
    + T("\nEach request's tokens arrive at once, so raw values are spiky — smoothed over 60s into a rate.")
    + T('\nUsage from sessions that send no telemetry is not included.');
  return {M, rate, tot, now, pace, col, lab, ratio, mx, W, H, py, line, area, tip};
}
function wkLive(d){
  const {M, rate, tot, now, pace, col, lab, ratio, mx, W, H, py, line, area, tip} = wkLiveCalc(d);
  // ★Top-project chips **removed** (project info is not needed on live).
  // The today bar just above is already split by project, so it was duplicated,
  // and chips wrapping to two lines pushed the header up over the graph. Data (`liveTop`) stays on the server.
  return '<div class=wkrt><div class=wkrh><b>'+esc(T('Live'))+'</b><span>'+TV({msg: 'last {n} min · tokens/min', vars: {n: M}})+'</span>'
    + (lab ? '<em class=wkrb style="color:'+col+';border-color:'+col+'55" title="'
        + esc(TV({msg: '{m}x the baseline of {n} tokens/min (5h limit ÷ 300 min)', vars: {n: pace.toLocaleString(), m: ratio.toFixed(2)}}))+'">'+esc(lab)+'</em>' : '')
    + '<i style="color:'+(lab?col:'')+'">'+(tot ? fmtTok(now)+T('/min') : T('0/min · quiet'))+'</i></div>'
    + ((() => {
        // Y ticks — 0 · baseline · max. Baseline has a different color (it is the comparison target).
        // ★Max tick is drawn **only when the real peak exceeds baseline** (found during 2026-09-04 verification).
        // With the peak below baseline, mx is just headroom (pace×1.15), not data,
        // and fmtTok rounded both to the same string, printing `2M` twice (measured: baseline 1.73M · mx 1.99M).
        const peak = Math.max(0, ...rate);
        const yt = [{v:0}];
        if(!pace || peak > pace * 1.02) yt.push({v:mx});
        if(pace && pace <= mx) yt.push({v:pace, pc:1});
        // ★Invariant: **the same string is never drawn twice.** fmtTok rounds to M, so
        // 1,533,223 (baseline) and 2,400,000 (max) both become `2M` (measured 2026-09-04).
        // Value conditions alone cannot prevent it — decide by the **text** to be drawn. On collision keep the baseline
        // (baseline is the comparison target; max is only axis height).
        const lbl = t => t.v ? fmtTok(t.v) : '0';
        const pcTxt = yt.filter(t => t.pc).map(lbl);
        const ylab = '<div class=wkry>' + yt.filter(t => t.pc || !pcTxt.includes(lbl(t))).map(t =>
            '<i class="'+(t.pc?'pc':'')+'" style="top:'+(py(t.v)/H*100).toFixed(2)+'%" title="'
            + esc(t.v.toLocaleString()+T(t.pc ? ' tokens/min — baseline (5h limit ÷ 300 min)' : ' tokens/min'))+'">'
            + lbl(t) + '</i>').join('') + '</div>';
        // X ticks — split into quarters (10 min: -10 · -7.5 · -5 · -2.5 · now)
        const xs = [0, .25, .5, .75, 1];
        const xlab = '<div class=wkrx>' + xs.map((f,i) => {
            const back = Math.round(M * (1 - f) * 10) / 10;
            const cls = i === 0 ? 'a0' : (i === xs.length-1 ? 'a1' : '');
            return '<i class="'+cls+'" style="left:'+(f*100)+'%">'
              + (f === 1 ? T('Now') : '-'+U(back,'m')) + '</i>';
          }).join('') + '</div>';
        const grid = xs.slice(1,-1).map(f =>
            '<path class=gl d="M'+(f*W).toFixed(2)+',0 L'+(f*W).toFixed(2)+','+H+'"/>').join('')
          + '<path class=gl d="M0,'+H+' L'+W+','+H+'"/>';
        return '<div class=wkrw>' + ylab + xlab + '<div class=wkrp>'
        + '<svg class=wkrs viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="none" title="'+esc(tip)+'">'
        + grid
        + '<defs><linearGradient id=wkrg x1=0 y1=0 x2=0 y2=1>'
        + '<stop offset="0%" stop-color="'+col+'" stop-opacity=".5"/>'
        + '<stop offset="100%" stop-color="'+col+'" stop-opacity="0"/></linearGradient></defs>'
        + '<path class=ar d="'+area+'"/>'
        + (pace && pace <= mx ? '<path class=pc d="M0,'+py(pace).toFixed(2)
            +' L'+W+','+py(pace).toFixed(2)+'"/>' : '')
        + '<path class=ln style="stroke:'+col+'" d="'+line+'"/></svg>'
        + '<i class="wknow'+(now?' on':'')+'" style="background:'+col+';left:100%;top:'
          + (py(now)/H*100).toFixed(2)+'%"></i>'
        + '</div></div>'; })()
      + (tot ? '' : '<div class=wkrz title="'+esc(tip)+'">'+TV({msg: 'No records in the last {n} min — shown as 0', vars: {n: M}})+'</div>'))
    + '</div>';
}

// ★Token tab = **consumption report**.
// Sidebar monitoring (donut, daily, today bar, live) stays; here are tables that answer **why it drains fast**:
// per-project request count and context per request, running subagents, whether window settings applied.
// Previously each question got a table typed into chat — visible only on asking, and long.
// ★Report period is **separate from the sidebar** (the report needs its own period while daily/live
// monitoring stays unchanged). Sharing `WKU` would switch the sidebar donut and daily to 30 days the moment
// a month is picked in the report — the sidebar was to be left alone. Hence a separate `WKR`.
// ⚠30 days takes ccusage a long time (7 days alone measured 34s). The server caches per period and measures in background,
// so the first pick is empty then fills — show 'measuring' meanwhile.
// ★Wait cap for weekly token (wkuse) recompute — **defined in one place only** (2026-09-07).
// Before, forced refresh (`wkuForce`) gave up at 20 ticks (60s) while the range loader (`loadWkRange`) waited 100 ticks (300s).
// Both wait on the same server job (ccusage recompute); split caps in the 60-300s range produced
// «clicked but old value stays» · «loading indicator never ends» screens. Hence a constant —
// ⚠hard-coding the number in two places will split them again.
// 1 tick = 3s (both watchers are setInterval at this interval).
// Measured (2026-09-07 · cold · two periods fired almost together, queued on `_ccusage_lock`):
// range=1 → 21s (7 ticks) · range=30 → 51s (17 ticks).
// The server runs ccusage 30-60s per period (subprocess timeout in `_wkuse_fetch` is 180s),
// and three periods (1·7·30) share one lock ⇒ queuing stretches it to minutes.
// So 60s is not enough for even **one** cold 30-day run. Use the generous 300s.
const WKU_TICK_MS = 3000;
const WKU_WAIT_TICKS = 100;                                        // 100 ticks × 3s = 300s
const WKU_WAIT_SEC = Math.round(WKU_WAIT_TICKS * WKU_TICK_MS / 1000);
let WKR = null, WKRANGE = 7, wkrAt = 0, wkrWatch = 0;
const WKR_LABEL = {1: 'D', 7: 'W', 30: 'M'};
const WKR_DESC  = {1: 'Today', 7: 'Last 7 days', 30: 'Last 30 days'};
// ★Scope labels (2026-09-25): «Today 437M» · «7d 2.2B» · «Last 7 days total 3.5B» read as contradictory without saying what each counts.
const SCOPE_PC_TIP = 'All projects on this PC (ccusage · calendar days) — the account limit windows (5h·7d) also count other devices and claude.ai and start at their reset time, so the numbers differ';
async function loadWkRange(force, retry){
  // ★No mainView guard — on initial hash entry this function ran before routing,
  // silently returned, WKR stayed null forever and the screen stuck on 'measuring' (measured 2026-09-04).
  const now = Date.now();
  if(!force && now - wkrAt < 60000) return;      // 1 min — server aggregates refresh every 2-3 min (local index)
  wkrAt = now;
  const pk = typeof acctPick === 'function' ? acctPick('tok') : '';
  try{
    const r = await getJSON('/api/wkuse?range=' + WKRANGE + (pk ? '&acct=' + encodeURIComponent(pk) : ''));
    // ⚠A reply for an older pick lands after the switch — painting it would show another account's totals.
    if(String((r && r.acct) || '') !== (typeof acctPick === 'function' ? acctPick('tok') : '')) return;
    WKR = r;
  }
  catch(e){ WKR = keepGood(WKR, 'Could not fetch'); }   // last good totals stay (46-tokens-tab.js)
  paintToken();
  // ⚠Watcher retries keep the one running timer (recreating it reset `n`, so the cap never tripped); stop only once settled.
  if(retry){ if(!WKR || WKR.at || WKR.err) clearInterval(wkrWatch); return; }
  // Period not yet measured means the server is measuring in background — watch until `at` appears
  clearInterval(wkrWatch);
  if(WKR && !WKR.at && !WKR.err){
    // ★Cap is `WKU_WAIT_TICKS` (evidence above). 40 ticks (2 min) **was not enough** — right after a server restart
    // 30 days plus ccusage lock wait exceeded 2 min, the watcher quit first and the screen stayed on 'measuring' (measured).
    let n = 0;
    wkrWatch = setInterval(() => {
      if(++n > WKU_WAIT_TICKS){
        clearInterval(wkrWatch);
        // ★If we give up, **say so on screen** — quitting silently leaves 'measuring' forever and the user thinks it is
        // still measuring (this file's rule: if unknown, say unknown). Text is written by the err branch of `paintToken` below.
        WKR = {err: TV({msg: 'Waited {n}s but the totals did not finish (press the period button again to retry)', vars: {n: WKU_WAIT_SEC}})};
        paintToken();
        return;
      }
      loadWkRange(true, true);
    }, WKU_TICK_MS);
  }
}
function setWkRange(d){
  // ★Same period **re-measures after a failure** (2026-09-07) — after giving up at the cap we say "press again
  // to retry"; blocking the same button would make that text a lie.
  if(WKRANGE === d && !(WKR && WKR.err)) return;
  WKRANGE = d; WKR = null; wkrAt = 0;
  paintToken(); loadWkRange(true);
}
document.addEventListener('click', e => {
  // ⚠`.wkrb` was already used for something else (the «Easy» burn badge, `<em class=wkrb>`) — on overlap
  // clicking that badge calls setWkRange(NaN). Period buttons use a separate `.wkrgb`.
  const b = e.target.closest && e.target.closest('.wkrgb');
  if(b && b.dataset.r) setWkRange(parseInt(b.dataset.r, 10));
});
