// ── Timeline time cursor ────────────────────────────────────────────────────
// Pierces «that moment» under the mouse with a vertical line and shows that moment's snapshot in a side panel.
// All client-side computation — no new server API (the only input is the already-received `TLD`).
function tlCurTrack(){
  // Every row's bar cell (.tlt) has the same width (same flex layout) — measure one.
  // ⚠`.tlaxr .tlt` (axis) has a different height. Take the one **inside .tlwrap**.
  const wrap = document.querySelector('.tlwrap');
  return wrap ? [wrap, wrap.querySelector('.tlt')] : [null, null];
}
function tlCurMove(ev){
  const [wrap, tk] = tlCurTrack();
  if(!wrap || !tk) return;
  const r = tk.getBoundingClientRect(), wr = wrap.getBoundingClientRect();
  // ⚠The name cell (left 340px) is not time — accepting input there clamps the cursor to window start
  // and falsely says «that time» while reading names. Outside the cell, turn the cursor off.
  // ⚠Not turned off during replay — playback stopping because the mouse moved to read a name would be absurd.
  if(ev.clientX < r.left - 2 && !tlRpOn){ tlCurAt = 0; tlCurPin = false; tlCurApply(); return; }
  const frac = Math.min(1, Math.max(0, (ev.clientX - r.left) / Math.max(1, r.width)));
  tlCurAt = tlCurT0 + frac * Math.max(60, tlCurT1 - tlCurT0);
  tlCurXY = [ev.clientX - wr.left, ev.clientY - wr.top];
  tlCurApply();
}
function tlCurApply(){
  const [wrap, tk] = tlCurTrack();
  const line = document.getElementById('tlcur'), pan = document.getElementById('tlcurp');
  if(!wrap || !line || !pan) return;
  const fut = document.getElementById('tlfut');
  if(!tlCurAt || !tk){
    line.hidden = true; pan.hidden = true;
    if(fut) fut.hidden = true;
    wrap.querySelectorAll('.tlb.tlbon').forEach(b => b.classList.remove('tlbon'));
    return;
  }
  const span = Math.max(60, tlCurT1 - tlCurT0);
  const frac = Math.min(1, Math.max(0, (tlCurAt - tlCurT0) / span));
  const r = tk.getBoundingClientRect(), wr = wrap.getBoundingClientRect();
  const x = (r.left - wr.left) + frac * r.width;
  line.hidden = false;
  line.style.left = x.toFixed(1) + 'px';
  line.classList.toggle('on', tlCurPin && !tlRpOn);
  line.classList.toggle('rp', tlRpOn);
  if(fut){                               // Cover time not reached yet (only during replay)
    fut.hidden = !tlRpOn;
    if(tlRpOn) fut.style.left = x.toFixed(1) + 'px';
  }
  // ★Highlight is **geometric** — a bar's offsetParent is its row's .tlt, so one in-cell x checks every row
  const xin = frac * r.width;
  // ⚠1px is **tolerance** — the data-derived snapshot list and the geometric highlight disagreed at bar edges
  // (measured 2026-09-08: at the window's right edge the panel said "1 session" but 0 bars were highlighted).
  // Bar widths are fractional pixels, so one rounding step splits them.
  wrap.querySelectorAll('.tlb').forEach(b => b.classList.toggle('tlbon',
    b.offsetLeft - 1 <= xin && xin <= b.offsetLeft + b.offsetWidth + 1));
  pan.hidden = false;
  pan.innerHTML = tlCurSnap(tlCurAt);
  // ⚠Before pinning, the panel must **not capture the mouse** — otherwise touching the panel
  // breaks mousemove and the cursor freezes there. Once pinned it must be read and scrolled, so enable it.
  pan.style.pointerEvents = tlCurPin ? 'auto' : 'none';
  const pw = pan.offsetWidth || 252, ph = pan.offsetHeight || 120;
  let px = x + 14;
  if(px + pw > wr.width) px = Math.max(0, x - pw - 14);      // Flip at the right edge
  // ⚠Clamp to the visible part of the rows scroller (.tlscr), not the full content height — near the bottom it slid under the footer.
  const fd = wrap.closest('.tlscr') || document.getElementById('feed'), vb = fd ? Math.min(wr.height, fd.getBoundingClientRect().bottom - wr.top) : wr.height;
  let py = tlCurXY[1] + 12;
  if(py + ph > vb - 2) py = tlCurXY[1] - ph - 12;             // Flip above the cursor at the bottom edge
  py = Math.min(Math.max(0, vb - ph - 2), Math.max(0, py));
  pan.style.left = px.toFixed(1) + 'px';
  pan.style.top = py.toFixed(1) + 'px';
  const hc = document.getElementById('tlhc');   // The panel walks during replay — keep the open card off it
  if(tlHovKey && hc && !hc.hidden) tlHovPlace(hc, tlHovXY[0], tlHovXY[1]);
}
// Tokens at that time — **cumulative** (window start~T) and **rate at that time** (previous 60s, tokens/min).
// ★The input is the timeline's whole-window buckets (`TLD.tok`). Before, it used the sidebar's live buckets (10 min),
// so nothing could be written when the cursor was beyond 10 min — on a 3-12h window that is almost always «none».
// ★Straddling cells are added **proportionally** — as replay passes, numbers rise smoothly instead of jumping per cell.
function tlTokAt(ts){
  const tk = TLD && TLD.tok;
  if(!tk || !tk.v || !tk.v.length) return null;
  const step = tk.step || 60, t0 = tk.t0 || 0, v = tk.v;
  let cum = 0, rate = 0;
  const s0 = ts - 60;                                 // Rate window is 60s, same as wkLive
  for(let i = 0; i < v.length; i++){
    const a = t0 + i * step, b = a + step;
    if(a >= ts) break;
    if(!v[i]) continue;
    cum += v[i] * Math.min(1, (ts - a) / step);
    if(b > s0) rate += v[i] * Math.max(0, Math.min(b, ts) - Math.max(a, s0)) / step;
  }
  return {cum: Math.round(cum), rate: Math.round(rate), sum: tk.sum || 0};
}
// ★Play/stop. **Stops by itself** at the end — no looping:
// it would burn rAF endlessly, and reaching «now» is itself the information to read.
function tlRpToggle(){
  if(tlRpOn) return void tlRpStop(true);
  if(!tlCurT1) return;                       // Not drawn yet
  // With no cursor or already at the end, start **from the beginning (window left)**
  if(!tlCurAt || tlCurAt >= tlCurT1 - 1) tlCurAt = tlCurT0;
  tlRpOn = true; tlCurPin = false; tlRpPrev = 0;
  // ★**Discard** the pending cursor rAF (2026-09-09: hovering the mouse jumped the cursor there).
  // `onmousemove` defers to once per frame, so pressing ▶ in between makes the cursor jump once
  // to the old mouse position after playback starts. The start time must be the value set below.
  if(tlCurRaf){ cancelAnimationFrame(tlCurRaf); tlCurRaf = 0; }
  tlCurEv = null;
  const rp = document.getElementById('tlrp');
  if(rp){ rp.classList.add('on'); rp.textContent = '❙❙'; }
  tlRpRaf = requestAnimationFrame(tlRpStep);
}
function tlRpStop(pin){
  tlRpOn = false;
  if(tlRpRaf) cancelAnimationFrame(tlRpRaf);
  tlRpRaf = 0;
  // On stop, **pin** at that spot — otherwise the cursor jumps on the next mouse move
  if(pin && tlCurAt) tlCurPin = true;
  const rp = document.getElementById('tlrp');
  if(rp){ rp.classList.remove('on'); rp.textContent = '▶'; }
  tlCurApply();
}
function tlRpStep(now){
  if(!tlRpOn) return;
  if(mainView !== 'time') return void tlRpStop(false);   // Stop when switching tabs
  const dt = tlRpPrev ? Math.min(0.5, (now - tlRpPrev)/1000) : 0;   // Prevent a jump after returning to the tab
  tlRpPrev = now;
  tlCurAt = Math.min(tlCurT1, tlCurAt + dt * tlRpSpeed);
  tlCurApply();
  if(tlCurAt >= tlCurT1) return void tlRpStop(true);     // Reached «now»
  tlRpRaf = requestAnimationFrame(tlRpStep);
}
// ⚠The parameter was named `T`, which shadowed the i18n T() once T('…') calls were added here (hover snapshot went blank).
function tlCurSnap(ts){
  const z = n => String(n).padStart(2,'0');
  const age = Math.round(Date.now()/1000 - ts);   // ⚠not `ago` — that would shadow ago() used below
  const agoS = age < 0 ? T('time not reached yet')
    : (age < 60 ? T('just now')
    : AGO(age < 3600 ? ago(age)
    : U(Math.floor(age/3600),'h')+' '+U(z(Math.floor((age%3600)/60)),'m')));
  // ★The coverage test uses **the same rule as the drawing code** (see the `inWin` comment in paintTl):
  // session heads draw no bar at all when `segs` is empty, so they count as not covering.
  // Branches (agents) draw start~end as one bar when `segs` is empty, so use that.
  const cov = (x, sess) => {
    const sg = x.segs || [];
    const list = sg.length ? sg : (sess ? [] : [[x.start, x.end]]);
    return list.some(g => g && g[0] <= ts && ts <= g[1]);
  };
  const ss = [], ag = [], cps = [], clrs = [];
  for(const g of (tlCurRows || [])){
    if(g.items.some(x => cov(x, g.sess))) (g.sess ? ss : ag).push(g);
    if(g.sess) g.items.forEach(x => (x.comp || []).forEach(cp => {
      if(cp && Math.abs(cp.at - ts) <= 120) cps.push({g: g, cp: cp}); }));
    if(g.sess) g.items.forEach(x => (Array.isArray(x.clr) ? x.clr : []).forEach(c => {
      if(c && Math.abs(c.at - ts) <= 120) clrs.push({g: g, c: c}); }));
  }
  const tkn = tlTokAt(ts);
  let h = '<b>' + hhmm(ts, {sec: true})
        + '<s' + (tlCurPin || tlRpOn ? ' class=tlcpin' : '') + '>' + esc(agoS)
        + (tlRpOn ? ' · ' + T('replay') + ' ' + T((TL_RSP.find(x=>x[0]===tlRpSpeed)||[0,''])[1])
                  : (tlCurPin ? ' · ' + T('pinned (click again to release)') : '')) + '</s></b>';
  if(tkn) h += '<div class="tlodo'+(tlRpOn?' rp':'')+'" title="'
    + esc(TV({msg: 'Tokens used by the bars drawn on this screen, from the window start to this moment.\nThe whole window is {n}; the right-hand value is the rate over the 60s before this moment.', vars: {n: fmtTok(tkn.sum)}}))
    + '"><b>'+tkn.cum.toLocaleString()+'</b><s>'+T('tokens so far')+'</s>'
    + '<i>'+fmtTok(tkn.rate)+T('/min')+'</i></div>';
  if(!ss.length && !ag.length && !cps.length && !clrs.length)
    h += '<em>'+T('Nothing was running at this moment')+'</em>';
  if(ss.length) h += '<em>'+TV({msg: '{n} sessions', vars: {n: ss.length}})+'</em>' + ss.map(g =>
    '<u title="'+esc(g.cwd)+'"><i style="background:'+projColor(g.cwd)+'"></i>'
    + '<b>'+esc(g.proj || g.cwd.split('/').pop())+'</b></u>').join('');
  if(ag.length) h += '<em>'+T('{n} subagents', 'now').replace('{n}', ag.length)+'</em>' + ag.map(g =>
    '<u title="'+esc(g.type+' · '+g.proj+(tlAgDesc ? '\n'+plStrip((g.items[g.items.length-1]||{}).desc||'') : ''))+'">'
    + '<i style="background:'+agColor(g.type)+'"></i><b>'+esc(tlAgLab(g, tlAgDesc).lab)
    // ★When the same name runs in parallel, add which row it is here too — measured (2026-09-08 17:24)
    // `repo-A-live-verify` appeared as two rows of the same project, indistinguishable (the rows are different runs).
    + (g._par > 1 ? ' ' + g._pi + '/' + g._par : '') + '</b>'
    + '<s>'+esc(g.proj || '')+'</s></u>').join('');
  if(cps.length) h += '<em>'+T('Compaction (cursor ±2 min)')+'</em>' + cps.map(c =>
    '<u class=tlcx title="'+esc(T('At this point the session lost its earlier context'))+'"><i style="background:#e8b478"></i>'
    + '<b>'+esc(c.g.proj || '')+'</b><s>'+Math.round(c.cp.pre/1000)+'K → '
    + Math.round(c.cp.post/1000)+'K</s></u>').join('');
  if(clrs.length) h += '<em>'+T('Cleared (cursor ±2 min)')+'</em>' + clrs.map(c =>
    '<u class=tlcx title="'+esc(TV({msg: 'Previous session {s}', vars: {s: String(c.c.old8 || '')}}))+'"><i class=tlclri></i>'
    + '<b>'+esc(c.g.proj || '')+'</b><s>'+esc(String(c.c.new8 || ''))+'</s></u>').join('');
  return h;
}
