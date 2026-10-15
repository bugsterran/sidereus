// ── Timeline bottom drawer ────────────────────────────────────────────────────
let tlSel = null, tlSelAt = 0;   // {cwd, tid} — what is expanded now · time last fetched
let tlSelShown = '';             // Key last rendered into the body — decides **whether something else was opened**
// ★Scroll position is held **outside the DOM** (2026-09-03: jumped to top on every refresh).
// paintTl replaces `#feed` wholesale every 30s, and tlDrawer is called **right after** —
// by then `#tldc` is already gone, so the position read from the DOM was always 0, and that 0 was restored.
// `atEnd` is held too: if viewing the end, stay stuck to the end after content grows.
let tlSelTop = 0, tlSelEnd = true;
const tlSelD = {};         // key → fetched work history (shows instantly on re-click)
function tlKey(cwd, tid){ return (tid||'')+'@'+(cwd||''); }
function tlOpen(cwd, tid){
  if(!cwd || !tid) return;
  if(/^wfa?:/.test(String(tid))) return;   // workflow run/agent rows have no Agent tool_use id, so no work popup
  // Timeline bar/name clicks open the work-log modal (user-confirmed 2026-09-23), not the bottom drawer below.
  if(String(tid).indexOf('sess:') === 0 || String(tid).indexOf('ext:') === 0) return openSession(cwd, tid);
  return openAgent(cwd, tid);
  tlSel = {cwd, tid};   // unreachable: old bottom-drawer path, kept for a quick revert
  tlDrawer();
  tlFetch(cwd, tid);
  // ★Opening **scrolls the page to the bottom** (2026-09-03). The drawer sits below the timeline, so
  // left alone, clicking looks like nothing happened — more so the longer the scroll.
  // Height grows after values arrive, so scroll twice (on click + after the body arrives).
  tlToEnd();
}
// Size the drawer to fill **down to the bottom of the visible area**. Re-measure on window resize.
function tlFit(){
  const c = document.getElementById('tldc'), f = document.getElementById('feed');
  if(!c || !f) return;
  const drw = c.parentElement;
  const hd = drw.querySelector('.tldh');
  const headH = hd ? hd.offsetHeight : 30;
  const view = f.clientHeight;
  // ★Measure **relative to the scroll content**. Measuring in viewport coords (getBoundingClientRect) varies with the current
  // scroll position, so on small windows the minimum (220px) kicked in and it **overflowed past the bottom**
  // (measured 2026-09-03: 234px over in a 720px window). offsetTop is independent of scroll.
  const fill = view - drw.offsetTop - headH - 14;   // Height **remaining** after the content above
  const cap = view - headH - 24;                    // Upper bound not exceeding the window
  // If the content above is short, fill what remains and stick to the bottom (no bottom gap); if long, use 60% of the window
  const h = Math.max(160, Math.min(cap, fill > 200 ? fill : Math.round(view * 0.6)));
  c.style.maxHeight = h + 'px';
  c.style.height = h + 'px';
}
function tlToEnd(){
  const f = document.getElementById('feed');
  if(!f) return;
  const go = () => f.scrollTo({top: f.scrollHeight, behavior: 'smooth'});
  go();
  setTimeout(go, 260);
  setTimeout(go, 700);
}
function tlClose(){ tlSel = null; tlSelShown = ''; tlSelTop = 0; tlSelEnd = true; tlDrawer(); }
function tlFetch(cwd, tid){
  const k = tlKey(cwd, tid);
  const url = workUrl(cwd, tid);
  getJSON(url)
    .then(j => { const had = !!tlSelD[k]; tlSelD[k] = j;
                 if(tlSel && tlKey(tlSel.cwd,tlSel.tid) === k){
                   tlDrawer();
                   // On the render where values arrive **for the first time**, scroll the inside to the bottom too (recent activity is at the bottom)
                   if(!had){ const c = document.getElementById('tldc');
                             if(c){ c.scrollTop = c.scrollHeight; tlSelTop = c.scrollTop; }
                             tlSelEnd = true;
                             tlToEnd(); }
                 } })
    .catch(e => { tlSelD[k] = {ok:false, msg:T('Could not fetch')+' — '+((e&&e.message)||T('unknown error'))};
                  if(tlSel && tlKey(tlSel.cwd,tlSel.tid) === k) tlDrawer(); });
}
// Replace timeline state markers in place **based on live SESS** (bars untouched)
function tlSyncState(){
  // Session row — status dot
  document.querySelectorAll('.tlr.tlrs[data-tlc]').forEach(el => {
    const cur = el.querySelector('.tlsi');
    if(!cur) return;
    const tmp = document.createElement('span');
    tmp.innerHTML = tlStateDot({cwd: el.dataset.tlc, plat: el.dataset.tlp || ''});   // ⚠plat too: a Gemini row must not take the Claude dot of the same cwd
    const neu = tmp.firstElementChild;
    if(neu && neu.outerHTML !== cur.outerHTML) cur.replaceWith(neu);
  });
  // Agent row — «Running now» dot. Uses the same value as the session card (SESS sub).
  // ⚠Match by agent id too: a resumed agent (SendMessage) has a new tool-use id in the list, so a tid-only
  //   match switched the dot off a few seconds after render (same trap as timeline.py _tl_live).
  const liveTid = new Set(), liveAid = new Set();
  (SESS||[]).forEach(s => (s.sub||[]).forEach(v => { if(v.tid) liveTid.add(v.tid); if(v.aid) liveAid.add(v.aid); }));
  document.querySelectorAll('.tlr.tlrk').forEach(el => {
    const on = [...el.querySelectorAll('.tlb[data-tlt]')]
      .some(b => liveTid.has(b.getAttribute('data-tlt')) || liveAid.has(b.getAttribute('data-tla') || ''));
    const b = el.querySelector('.tlnm b');
    if(!b) return;
    // ★Toggle the slot on/off — before, it was inserted via `afterbegin` and attached at a different spot than the render
    const d = b.querySelector('.tlds');
    if(d) d.classList.toggle('on', on);
  });
  tlPlSync();   // pipeline strips/chips follow SESS[].plrun every poll (74c)
}
// ★The timeline bottom is a «selection detail drawer», so with nothing clicked 615px (46vh) was always empty
// ⇒ Default is a summary card; clicking a bar covers it with detail; closing returns to the summary (2026-09-22).
// ⚠Do not fill it via auto-selection — `paintTl` redraws every 2.5s and the viewed detail would bounce.
// ⚠**No conversation content** — only path, model, time, counts, tokens (`desc`/`last` are forbidden).
// The only input is the already-received `TLD` — no new API (`tok.sum` · `rows[].segs` · `naps`).
let tlSumHtml = '';
function tlSumDur(s){
  s = Math.max(0, Math.round(s));
  if(s < 60) return U(s,'s');
  const m = Math.round(s / 60);
  return m < 60 ? U(m,'m') : U(Math.floor(m / 60),'h') + ' ' + U(m % 60,'m');
}
// ★2026-09-25: summary said «longest gap 17:29~18:03 · 34 min» while pmset had one sleep 15:30~20:26 —
// `_naps_awake` cuts sleep at 1-45 s session segments written during DarkWakes (a background monitor firing).
// ⇒ Bands separated by less than TL_NAP_JOIN_S are one sleep; `[a, b, autoWakes]`.
// ⚠60 s: the longest measured DarkWake was 45 s (14:45:18~14:46:03); real wakes were followed by minutes of work.
// ⚠Summary only — the hatch keeps per-band drawing: separators are narrower than a pixel there, and
//   carving out activity is what keeps a long DarkWake with real work (★09-18, 27 min) visible.
const TL_NAP_JOIN_S = 60;
function tlNapJoin(naps, joinS){
  const src = (naps || []).filter(n => n && n[1] > n[0]).slice().sort((x, y) => x[0] - y[0]);
  const out = [];
  for(const n of src){
    const l = out[out.length - 1];
    if(l && n[0] - l[1] < joinS){ if(n[0] > l[1]) l[2]++; if(n[1] > l[1]) l[1] = n[1]; }
    else out.push([n[0], n[1], 0]);
  }
  return out;
}
// External-platform tokens {plat: n}: whole row (`tk`) when bs is null, else only bars starting at/after bs (`tks[i]`).
function tlExtTok(rows, bs){
  const o = {};
  for(const r of rows || []){
    if(!r || !r.plat) continue;
    let n = 0;
    if(bs == null) n = r.tk || 0;
    else if(Array.isArray(r.tks) && r.segs) r.segs.forEach((g, i) => { if(g[0] >= bs) n += (r.tks[i] || 0); });
    else if((r.start || 0) >= bs) n = r.tk || 0;
    o[r.plat] = (o[r.plat] || 0) + n;
  }
  return o;
}
function tlSumDraw(host){
  const d = TLD, rows = (d && d.ok) ? (d.rows || []) : [];
  // For an empty window the header above already says "no agents ran" — do not list 0 on four lines
  if(!rows.length){ host.innerHTML = ''; tlSumHtml = ''; return; }
  const t1 = d.at, t0 = (d.tok && d.tok.t0) || (t1 - (d.hours || 12) * 3600);
  const ss = rows.filter(r => r.kind === 'sess'), ag = rows.filter(r => r.kind !== 'sess');
  const iv = [], sl = tlNapJoin(d.naps, TL_NAP_JOIN_S);
  for(const r of rows) for(const g of (r.segs || [])){
    const a = Math.max(t0, g[0]), b = Math.min(t1, g[1]);
    // DarkWake blips inside one joined sleep do not end the gap (★ at tlNapJoin)
    if(b >= a && !sl.some(n => a >= n[0] && b <= n[1])) iv.push([a, b]);
  }
  // (1) Whole-window total — bars are individual, so the total does not read
  // ★Before it wrote "N active fragments" (count of `segs`) — because the response had no tool-call count, and "fragment"
  // was hard to understand. Now each row carries `tc` (tool calls made by that agent) (2026-09-22).
  let tcN = 0;
  for(const r of ag) tcN += (r.tc || 0);
  // ★Only tokens use the «current 5h limit window» (2026-09-22) — cause: `tok.sum` is the timeline's 12h window total,
  // so with a just-reset limit at 2% the screen showed 157M including the previous window's share.
  // Reported by the user: the hourly usage should restart from the newly granted quota.
  // ⚠Do not revert — reverting to `tok.sum` brings back exactly the same confusion.
  // ⚠Boundary cells (straddling `start`) are dropped entirely, keeping «under- rather than over-count» — pre-window consumption
  // mixed into the new window would disagree with the limit gauge. Session/agent/tool counts stay as the 12h activity totals.
  // ★The math is consolidated in one `curWinTok()` (2026-09-22) — the 5h quota row and burndown header had three copies
  // of the same formula, and copies are how one side gets fixed and the windows diverge again. ⚠Do not inline it again here.
  const _w = curWinTok();
  // ⚠`tok.sum`/curWinTok are Claude-only; external rows are added per platform behind their logo (logo-only rule),
  //   same window and same «drop the straddling piece» rule (`tks` per bar), so the count and the tokens cover the same sessions.
  const bs = (_w == null) ? null : BURN.cur.start, xt = tlExtTok(rows, bs);
  const xs = Object.keys(xt).map(p => ' · ' + aiLogo(p) + ' ' + fmtTok(xt[p])).join('');
  const cl = xs ? aiLogo('cc') + ' ' : '';
  const tkTxt = (_w == null) ? T('tokens') + ' ' + cl + fmtTok((d.tok || {}).sum || 0) + xs   // Fallback: label as before too
                             : T('this-window tokens') + ' ' + cl + fmtTok(_w) + xs;
  let h = '<u><i>'+T('Total')+'</i><b>' + TV({msg: '{s} sessions · {a} subagents · {t} tool calls', vars: {s: ss.length, a: ag.length, t: tcN}}) + ' · ' + tkTxt + '</b></u>';
  // (2) Longest gap — empty space is not drawn, so «absence» is invisible unless the screen says so
  iv.sort((x, y) => x[0] - y[0]);
  let gs = 0, ge = 0, cur = t0;
  for(const g of iv){
    if(g[0] - cur > ge - gs){ gs = cur; ge = g[0]; }
    if(g[1] > cur) cur = g[1];
  }
  if(t1 - cur > ge - gs){ gs = cur; ge = t1; }
  if(ge - gs >= 60){
    let nap = 0, wk = 0;         // Overlapping a sleep span means «stopped», not «unused»
    for(const n of sl){
      const o = Math.min(ge, n[1]) - Math.max(gs, n[0]);
      if(o > 0){ nap += o; wk += n[2]; }
    }
    h += '<u><i>'+T('Longest gap')+'</i><b>' + hhmm(gs) + '~' + hhmm(ge) + ' · ' + tlSumDur(ge - gs)
       + (nap > (ge - gs) * 0.5 ? ' <s>· ' + T('asleep') + ' ' + tlSumDur(nap)
          + (wk ? ' · ' + TV({msg: '{n} auto-wakes in between', vars: {n: wk}}) : '') + '</s>' : '') + '</b></u>';
  }
  // (3) Running now — if none, drop this row entirely (do not write 0)
  const liv = ss.filter(r => r.run), lag = ag.filter(r => r.run).length;
  if(liv.length || lag){
    const nm = liv.slice(0, 3).map(r => {
      const s = tlLiveOf(r.cwd, r.plat);      // Model uses the same value as the session card (same plat)
      return esc(r.proj || r.cwd) + (s && s.model ? ' <s>' + esc(s.model) + '</s>' : '');
    }).join(' · ');
    h += '<u><i>'+T('Running now')+'</i><b>' + nm
       + (liv.length > 3 ? ' <s>' + T('+{n} more', 'drawer').replace('{n}', liv.length - 3) + '</s>' : '')
       + (lag ? (nm ? ' · ' : '') + '<s>' + TV({msg: '{n} subagents', vars: {n: lag}}) + '</s>' : '') + '</b></u>';
  }
  // (4) Outliers — ⚠measured only with fields **actually present** in the response (start/end · fin).
  // ★End state is not a «status field» in the source — all there is is **the shape of the last record**, so
  // it is called "cut off without report", not "abnormal exit" (server `_agent_ended`, 2026-09-22).
  // ⚠Just-finished rows may be about to write their report, so only count those over 5 min — otherwise 1-2 always show.
  // With few samples the median is meaningless, so that piece is dropped.
  const ox = [];
  if(ag.length >= 4){
    const du = ag.map(r => r.end - r.start).sort((a, b) => a - b);
    const med = du[du.length >> 1];
    const lim = Math.max(300, med * 3);
    const big = ag.filter(r => r.end - r.start >= lim)
                  .sort((a, b) => (b.end - b.start) - (a.end - a.start));
    if(big.length) ox.push(TV({msg: '{n} at 3×+ the median duration {d}', vars: {n: big.length, d: tlSumDur(med)}}) + ' '
      + '<s>' + big.slice(0, 2).map(r =>
          esc(r.type || T('Subagent')) + ' ' + tlSumDur(r.end - r.start)).join(' · ') + '</s>');
  }
  const dead = ag.filter(r => !r.run && r.fin === 0 && t1 - r.end > 300).length;
  if(dead) ox.push(TV({msg: '{n} cut off without a report', vars: {n: dead}}));
  if(ox.length) h += '<u><i>'+T('Outliers')+'</i><b>' + ox.join(' · ') + '</b></u>';
  const html = '<div class=tldrw><div class=tldh><b>'+T('Window summary')+'</b><span>'
    + rangeLbl(d.hours)
    + ' — ' + T('click a bar to open its work log in a new window') + '</span></div>'
    + '<div class=tlsb>' + h + '</div></div>';
  // ⚠Do not touch if content is identical — so the screen does not jump when polling redraws.
  // ★Check `firstChild` too: right after paintTl replaces `#feed`, the host is **a new empty div**,
  // so comparing strings alone says "same", skips, and the summary is never drawn.
  if(host.firstChild && html === tlSumHtml) return;
  tlSumHtml = html;
  host.innerHTML = html;
}
function tlDrawer(){
  const host = document.getElementById('tldrw');
  if(!host) return;
  if(!tlSel){ tlSumDraw(host); return; }
  tlSumHtml = '';                    // Detail is covering it — redraw the summary on close and return
  const k = tlKey(tlSel.cwd, tlSel.tid);
  const d = tlSelD[k];
  const isS = String(tlSel.tid).indexOf('sess:') === 0;
  const ttl = (d && d.ok) ? (wkLab(d.type) || T('Activity')) : (isS ? T('Session') : T('Subagent'));
  const sub = (d && d.ok) ? wkLab(d.desc || tlSel.cwd) : tlSel.cwd;
  // ★Preserve scroll position — polling redraws every 2.5s, so without it the view keeps jumping while reading.
  // ⚠Deciding «first render» by **DOM presence** was wrong: right after clicking there is no value yet, so only the shell
  // is drawn, and on the second render when values arrive the DOM already exists and it reverted to `keep` (0 at that time).
  // So decide by **which key was drawn** (if something else was opened, go to the bottom).
  const live = document.getElementById('tldc');
  if(live){                                  // Update only while alive — do not pick up 0 after it was removed
    tlSelTop = live.scrollTop;
    tlSelEnd = (live.scrollHeight - live.scrollTop - live.clientHeight) < 40;
  }
  const first = (tlSelShown !== k);
  if(first){ tlSelTop = 0; tlSelEnd = true; }
  tlSelShown = k;
  host.innerHTML = '<div class=tldrw><div class=tldh><b>'+esc(ttl)+'</b>'
    + '<span>'+esc(sub)+'</span><em>'
    + '<span class=tldb id=tldtab title="'+esc(T('Move to the work log tab in the middle column for a larger view'))+'">'+T('To tab')+'</span>'
    + '<span class=tldx id=tldcls title="'+esc(T('Close'))+'">✕</span></em></div>'
    + '<div class=tldc id=tldc>'+agentBody(d)+'</div></div>';
  const c = document.getElementById('tldc');
  tlFit();
  // If viewing the end, stay at the end (content grows) · otherwise keep the position
  if(c) c.scrollTop = (first || tlSelEnd) ? c.scrollHeight : tlSelTop;
  if(c) c.onscroll = () => {
    tlSelTop = c.scrollTop;
    tlSelEnd = (c.scrollHeight - c.scrollTop - c.clientHeight) < 40;
  };
  agBind(c, tlDrawer);
  const x = document.getElementById('tldcls');
  if(x) x.onclick = tlClose;
  const tb = document.getElementById('tldtab');
  if(tb) tb.onclick = () => { const s = tlSel; tlClose();
    if(!s) return;
    if(String(s.tid).indexOf('sess:') === 0) openSession(s.cwd, s.tid); else openAgent(s.cwd, s.tid); };
}
