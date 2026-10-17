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
  if(/^wfa?:/.test(String(tid))) return;   // workflow run/agent rows have no Agent tool_use id, so no work log
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
// Inputs are already-received data — `TLD` rows, `SESS[].plrun` and the 48f gate-evidence cache; no new API.
let tlSumHtml = '';
function tlSumDur(s){
  s = Math.max(0, Math.round(s));
  if(s < 60) return U(s,'s');
  const m = Math.round(s / 60);
  return m < 60 ? U(m,'m') : U(Math.floor(m / 60),'h') + ' ' + U(m % 60,'m');
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
// «More» state of the summary card. ⚠Storage may throw (private mode, quota); the card must still render.
const TLSUM_MORE_KEY = 'sidereus.tlsumMore';
function tlSumMoreOn(){ try{ return lsGet(TLSUM_MORE_KEY, '0') === '1'; }catch(e){ return false; } }
function tlSumMoreSet(on){ try{ lsSet(TLSUM_MORE_KEY, on ? '1' : '0'); }catch(e){ softErr('ls', e); } }
// Results + Evidence from the gate-evidence cache of 48f (PLEV, read only): commits, runs and gate rows inside [t0, t1].
// ⚠Metadata only — counts, short step names and times; commit subjects never reach the page.
function tlSumWork(ss, t0, t1){
  const ps = [];
  for(const r of ss){
    const s = tlLiveOf(r.cwd, r.plat), p = (s && Array.isArray(s.repos) && s.repos[0]) || r.cwd;
    if(p && ps.indexOf(p) < 0) ps.push(p);
    if(ps.length >= 6) break;
  }
  const hs = new Set(), ev = [];
  for(const p of ps){
    for(const e of (plEvRows(p) || [])) if(e && e.ts >= t0 && e.ts <= t1) ev.push(e);
    for(const c of (plEvCommits(p) || [])) if(c && typeof c.h === 'string' && c.ct >= t0 && c.ct <= t1) hs.add(c.h);
  }
  let ok = 0, bad = 0, lb = 0, n = 0;
  (SESS || []).forEach(x => ((x && x.plrun) || []).forEach(r => [r].concat((r && r.past) || []).forEach(u => {
    if(!u || !(u.t0 >= t0 && u.t0 <= t1)) return;
    const st = Object.values(u.stages || {}).filter(Boolean);
    n++;
    if(st.some(g => g.o === 'fail')) bad++; else if(u.end) ok++;
    st.forEach(g => Object.values(g.from || {}).forEach(k => { lb += (+k || 0); }));
  })));
  ev.sort((a, b) => b.ts - a.ts);
  const pass = ev.filter(e => e.rc === 0).length, nf = ev.find(e => e.rc !== 0);
  const st = nf && Array.isArray(nf.steps) ? nf.steps.find(g => g && g.rc !== 0) : null;
  const step = st && typeof st.name === 'string' && /^[a-z0-9_-]{1,20}$/.test(st.name) ? st.name : '';   // = harness_evidence.EV_STEP
  return {c: hs.size, n, ok, bad, lb, ev: ev.length, pass, fail: ev.length - pass, step};
}
function tlSumDraw(host){
  const d = TLD, rows = (d && d.ok) ? (d.rows || []) : [];
  // For an empty window the header above already says "no agents ran" — do not list 0 on four lines
  if(!rows.length){ host.innerHTML = ''; tlSumHtml = ''; return; }
  const t1 = d.at, t0 = (d.tok && d.tok.t0) || (t1 - (d.hours || 12) * 3600);
  const ss = rows.filter(r => r.kind === 'sess'), ag = rows.filter(r => r.kind !== 'sess');
  const row = (k, v) => '<u><i>' + T(k) + '</i><b>' + v + '</b></u>';
  const w = tlSumWork(ss, t0, t1);
  // (1) Results — commits and pipeline runs that landed in this window
  let h = row('Results', TV({msg: w.c === 1 ? '{n} commit' : '{n} commits', vars: {n: w.c}})
    + (w.n ? ' · ' + TV({msg: '{n} pipeline runs', vars: {n: w.n}}) + ' <s>✓' + w.ok + ' ✕' + w.bad + (w.lb ? ' ↺' + w.lb : '') + '</s>' : ''));
  // (2) Evidence — gate runs recorded in the window; on FAIL the newest failing run's first failed step
  h += row('Evidence', !w.ev ? T('no gate runs')
    : TV({msg: '{n} gate runs', vars: {n: w.ev}}) + ' · PASS ' + w.pass + ' · FAIL ' + w.fail
      + (w.step ? ' <s>· ' + T('last failure') + ' ' + esc(w.step) + '</s>' : ''));
  const more = tlSumMoreOn();
  let m = '';
  if(more){
    // (3) Waited on you — server `wt` = [human prompts that came ≥30 s after the previous line, seconds]
    let wn = 0, ws = 0;
    for(const r of ss) if(Array.isArray(r.wt)){ wn += (+r.wt[0] || 0); ws += (+r.wt[1] || 0); }
    m += row('Waited on you', wn ? TV({msg: wn === 1 ? '{n} prompt' : '{n} prompts', vars: {n: wn}}) + ' · ' + tlSumDur(ws) : '—');
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
    if(ox.length) m += row('Outliers', ox.join(' · '));
    // (5) Cost — window tokens, activity counts and tokens per commit
    let tcN = 0;
    for(const r of ag) tcN += (r.tc || 0);
    // ★Tokens use the «current 5h limit window» (curWinTok, 55a) — `tok.sum` is the timeline's 12h total and showed the
    //   previous window's share right after a reset. ⚠Do not revert to `tok.sum` and do not inline the math here.
    const _w = curWinTok();
    // ⚠`tok.sum`/curWinTok are Claude-only; external rows are added per platform behind their logo (logo-only rule),
    //   same window and same «drop the straddling piece» rule (`tks` per bar), so the count and the tokens cover the same sessions.
    const bs = (_w == null) ? null : BURN.cur.start, xt = tlExtTok(rows, bs);
    const xs = Object.keys(xt).map(p => ' · ' + aiLogo(p) + ' ' + fmtTok(xt[p])).join('');
    const cl = xs ? aiLogo('cc') + ' ' : '';
    const cc = (_w == null) ? ((d.tok || {}).sum || 0) : _w;
    const tkTxt = ((_w == null) ? T('tokens') : T('this-window tokens')) + ' ' + cl + fmtTok(cc) + xs;
    const all = cc + Object.keys(xt).reduce((s, p) => s + (xt[p] || 0), 0);
    m += row('Cost', tkTxt + ' · ' + T('per commit') + ' ' + (w.c ? fmtTok(Math.round(all / w.c)) : '—')
      + ' <s>· ' + TV({msg: '{s} sessions · {a} subagents · {t} tool calls', vars: {s: ss.length, a: ag.length, t: tcN}}) + '</s>');
  }
  h += m + '<u><i></i><b><span class=tlsmore id=tlsmore role=button tabindex=0 style="cursor:pointer">'
    + (more ? T('Less') + ' ▴' : T('More') + ' ▾') + '</span></b></u>';
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
  const mb = document.getElementById('tlsmore');
  if(mb) mb.onclick = mb.onkeydown = ev => {
    if(ev.type === 'keydown' && ev.key !== 'Enter' && ev.key !== ' ') return;
    tlSumMoreSet(!tlSumMoreOn()); tlSumHtml = ''; tlSumDraw(host);
  };
}
function tlDrawer(){
  const host = document.getElementById('tldrw');
  if(!host) return;
  if(!tlSel){ tlSumDraw(host); return; }
  tlSumHtml = '';                    // Detail is covering it — redraw the summary on close and return
  const k = tlKey(tlSel.cwd, tlSel.tid);
  const d = tlSelD[k];
  const isS = String(tlSel.tid).indexOf('sess:') === 0;
  const ttl = (d && d.ok) ? (wkLab(d.type) || T('Work log')) : (isS ? T('Session') : T('Subagent'));
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
