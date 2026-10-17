// Session row's linked worktree from SESS (same `wt` as the sidebar chip); main checkout -> null.
function tlWtOf(cwd){ const c = brNorm(cwd); const x = (SESS || []).find(s => s && s.wt && s.wt.main && s.cwd && (brNorm(s.cwd) === c || c.indexOf(brNorm(s.wt.root) + '/') === 0 || c === brNorm(s.wt.root))); return x ? x.wt : null; }
// ★Row hover card (2026-09-24: inline label text was always truncated) — replaces the native titles on `.tlnm` and bars.
// ⚠Metadata only: Agent `description`, type, status, times, tokens, tool count, last tool NAME (never its target), worktree, path, id.
let tlHovG = [], tlHovT = 0, tlHovKey = '', tlHovEl = null, tlHovXY = [0, 0];
function tlHovHtml(el){
  const h = tlHovG[+el.dataset.tlh];
  if(!h) return '';
  const g = h.g, bar = el.classList.contains('tlb');
  const r = bar ? g.items[+el.dataset.tli] : h.pick;
  if(!r) return '';
  const hh = tlHh;
  const mn = s => HM(Math.max(0, Math.round(s / 60)));
  const actOf = x => (x.segs && x.segs.length) ? x.segs.reduce((a, y) => a + Math.max(0, y[1] - y[0]), 0)
                                                : (g.sess ? 0 : Math.max(0, x.end - x.start));
  const rows = [];
  const add = (k, v, c) => { if(v) rows.push('<dt>'+esc(T(k, c))+'</dt><dd>'+v+'</dd>'); };
  const live = g.sess ? tlLiveOf(g.cwd, g.plat) : null;   // ⚠child rows: a live row at the same cwd is another session
  let st;
  if(g.sess){ const sl = tlSessLabel(r); st = esc(sl.lab) + (sl.mon ? ' <s>'+esc(sl.mon)+'</s>' : ''); }
  else if(r.state === 'gone') st = esc(T('Disconnected'))+' · '+hh(r.end);
  else if(r.run) st = '<b class=on>'+esc(T('running'))+'</b> · '+TV({msg: 'since {t}', vars: {t: hh(r.start)}});
  else st = esc(T(r.fin ? 'Done — reported' : 'Stopped without a report'))+' · '+hh(r.end);
  add('Type', esc(g.sess ? (g.plat && g.plat !== 'cc' ? platName(g.plat)+' ' : '') + T('Session') : g.type) + (g._par > 1 ? ' <s>'+g._pi+'/'+g._par+'</s>' : ''), 'kind');
  add('Status', st);
  if((g.sess || g.plat) && (r.model || (live && live.model))) add('Model', esc(r.model || live.model));
  add('Time', hh(r.start)+' ~ '+hh(r.end)+' <s>'+mn(r.end - r.start)+'</s>', 'span');
  if(g.sess && !bar) add('Active', U(h.act || 0, 'm') + ' <s>'+TV({msg: '{n} spans', vars: {n: h.nSeg}})
      + (g.items.length > 1 ? ' · ' + TV({msg: '{n} sessions', vars: {n: g.items.length}}) : '')+'</s>');
  else add('Active', mn(actOf(r)) + (!bar && g.items.length > 1
      ? ' <s>'+U(g.items.length,'×')+' · '+T('total')+' '+mn(h.tot)+'</s>' : ''));
  if(bar){                                   // Segment under the pointer — merged here instead of a second tooltip
    const ps = (r.segs && r.segs.length) ? r.segs : [[r.start, r.end]], si = +el.dataset.tls, p = ps[si];
    if(p){ const tkv = (r.segs && r.segs.length) ? ((r.tks && r.tks[si]) || 0) : (r.tk || 0);
      add('This span', hh(p[0])+' ~ '+hh(p[1])+' <s>'+mn(p[1] - p[0])+' · '+(tkv ? fmtTok(tkv) : esc(T('no token records')))+'</s>'); }
  }
  const tkAll = (g.sess && !bar) ? h.tkSum : r.tk;
  add('Tokens', (tkAll ? fmtTok(tkAll) : '') + (!bar && !g.sess && g.items.length > 1 && h.tkSum ? ' <s>'+esc(T('Total'))+' '+fmtTok(h.tkSum)+'</s>' : ''));
  if(!g.sess && typeof r.tc === 'number') add('Tool calls', String(r.tc));
  add('Last tool', esc(String(r.last || '').split(' · ')[0]));
  if(g.sess && h.nComp) add('Compactions', U(h.nComp, '×'));
  const wt = tlWtOf(g.cwd);
  if(wt) add('worktree', esc(wt.name)+' <s>'+esc(wt.root)+'</s>');
  const sid = g.sess ? ((String(r.tid || '').split('|')[1]) || (live && live.sid) || '') : (r.aid || '');
  add('Path', esc(g.cwd || '') + (sid ? ' <s>· '+esc(g.sess ? sid8(sid) : sid.slice(0, 8))+'</s>' : ''));
  return '<div class=tlhch>'+esc(g.sess ? (g.proj || g.cwd) : g.type)+'</div>'
    // ⚠Session rows skip `desc` — it is the session task, which can be prompt text (agents: Agent tool description only).
    + (r.desc && !g.sess && tlAgDesc ? '<div class=tlhcd>'+esc(plStrip(r.desc))+'</div>' : '')
    + '<dl>'+rows.join('')+'</dl>'
    + (r.tid ? '<div class=tlhcf>'+esc(T('Click to open the work log'))+'</div>' : '');
}
function tlHovHide(){
  clearTimeout(tlHovT); tlHovT = 0; tlHovKey = ''; tlHovEl = null;
  hcHide('tlhc');
  document.querySelectorAll('.tlwrap.tlhov').forEach(w => w.classList.remove('tlhov'));
}
// Card spot for a w×h card at pointer (x,y): inside box {l,t,r,b}, never over `av` (#tlcurp rect) when any candidate avoids it.
function tlHovPos(w, h, x, y, box, av){
  const cl = (v, a, b) => Math.max(a, Math.min(v, b));
  const X = [x + 14, x - 14 - w], Y = [y + 16, y - 12 - h];
  if(av) X.push(av.right + 8, av.left - 8 - w), Y.push(av.bottom + 8, av.top - 8 - h);
  const hit = (l, t) => av ? Math.max(0, Math.min(l + w, av.right) - Math.max(l, av.left)) * Math.max(0, Math.min(t + h, av.bottom) - Math.max(t, av.top)) : 0;
  let best = null;
  for(const ty of Y) for(const tx of X){
    const l = cl(tx, box.l, box.r - w), t = cl(ty, box.t, box.b - h);
    const s = hit(l, t) * 1e6 + Math.abs(l - tx) + Math.abs(t - ty);   // overlap first, then how far clamping moved it
    if(!best || s < best[2]) best = [l, t, s];
  }
  return [Math.round(best[0]), Math.round(best[1])];
}
function tlHovPlace(c, x, y){
  c.hidden = false;
  // ⚠Bounded by the Gantt (.tlwrap), not the window — a panel beside the Gantt would be covered by the card.
  const wr = document.querySelector('#feed .tlwrap'), a = wr ? wr.getBoundingClientRect() : null, pad = 8;
  const box = {l: Math.max(pad, a ? a.left : 0), r: Math.min(innerWidth - pad, a ? a.right : innerWidth), t: pad, b: innerHeight - pad};
  const p = document.getElementById('tlcurp');
  const av = p && !p.hidden && p.offsetWidth ? p.getBoundingClientRect() : null;   // display:none while unpinned (CSS .tlhov)
  const [l, t] = tlHovPos(c.offsetWidth, c.offsetHeight, x, y, box, av);
  c.style.left = l + 'px'; c.style.top = t + 'px';
}
function tlHovShow(el, x, y){
  const html = tlHovHtml(el);
  if(!html) return tlHovHide();
  tlHovEl = el;
  const w = el.closest('.tlwrap');
  if(w) w.classList.toggle('tlhov', el.classList.contains('tlb'));   // ⚠Before placing — it decides whether #tlcurp is there to avoid
  tlHovPlace(hcShow('tlhc', html, 'tlhc'), x, y);
  // ⚠State dots are re-rendered with a native title by the 2.5s sync — strip them so only the card shows.
  const nm = el.closest('.tlr');
  if(nm) nm.querySelectorAll('.tlnm [title]').forEach(t => t.removeAttribute('title'));
}
document.addEventListener('mousemove', e => {
  if(e.buttons){ if(tlHovKey) tlHovHide(); return; }             // Hidden while dragging
  tlHovXY = [e.clientX, e.clientY];
  const t = e.target && e.target.closest ? e.target.closest('#feed .tlnm[data-tlh], #feed .tlb[data-tlh]') : null;
  if(!t){ if(tlHovKey) tlHovHide(); return; }
  const k = (t.classList.contains('tlb') ? 'b' : 'n') + t.dataset.tlh + '|' + (t.dataset.tli || '') + '|' + (t.dataset.tls || '');
  const c = document.getElementById('tlhc'), open = c && !c.hidden;
  if(k === tlHovKey && open){ if(t !== tlHovEl) tlHovShow(t, e.clientX, e.clientY); else tlHovPlace(c, e.clientX, e.clientY); return; }
  if(k === tlHovKey && tlHovT) return;
  tlHovKey = k; clearTimeout(tlHovT); tlHovT = 0;
  if(open) return tlHovShow(t, e.clientX, e.clientY);            // Already open: switch rows without the delay
  tlHovT = setTimeout(() => { tlHovT = 0; if(document.contains(t)) tlHovShow(t, tlHovXY[0], tlHovXY[1]); }, 150);
}, {passive: true});
document.addEventListener('mousedown', () => { if(tlHovKey) tlHovHide(); }, true);
document.addEventListener('scroll', () => { if(tlHovKey) tlHovHide(); }, true);
document.addEventListener('wheel', () => { if(tlHovKey) tlHovHide(); }, {passive: true, capture: true});
// Keyboard focus (98-a11y marks `.tlr` rows) shows the row's card under the label.
document.addEventListener('focusin', e => {
  const r = e.target && e.target.closest ? e.target.closest('#feed .tlr') : null;
  const nm = r && r.querySelector('.tlnm[data-tlh]');
  if(!nm) return;
  const b = nm.getBoundingClientRect();
  tlHovKey = 'f' + nm.dataset.tlh; tlHovShow(nm, b.left + 20, b.bottom - 10);
});
document.addEventListener('focusout', () => { if(tlHovKey && tlHovKey[0] === 'f') tlHovHide(); });
// Esc dismisses the card without moving focus (WCAG 1.4.13).
document.addEventListener('keydown', e => {
  const c = document.getElementById('tlhc');
  if(e.key === 'Escape' && c && !c.hidden){ tlHovHide(); e.stopPropagation(); }
}, true);
// Empty-window line (HTML). ⚠When the account pick hid every row, say so — «No subagents ran» would read as an idle window.
function tlEmptyMsg(d, rows){
  const all = (d && d.rows) || [], p = typeof acctPick === 'function' ? acctPick('time') : '';
  if(rows.length || !all.length || !p) return esc(TV({msg: 'No subagents ran in the last {n}h', vars: {n: d.hours}}));
  return esc(TV({msg: 'Nothing for {a} in the last {n}h · {m} in other accounts', vars: {a: p, n: d.hours, m: all.length}}));
}
function paintTl(){
  if(mainView !== 'time') return;        // Draw only on the timeline tab
  const box = document.getElementById('feed');
  if(!box) return;
  const d = TLD;
  if(!d) return void(box.innerHTML = '<div class=tlhd><i>'+T('Building timeline…')+' <span id=tlwait>'
    + (tlReqAt ? U(Math.round((Date.now() - tlReqAt) / 1000), 's') : '') + '</span></i></div>');
  if(!d.ok){
    box.innerHTML = '<div class="tlhd cwerr"><i>'+esc(d.msg ? TV(d) : T('Could not fetch'))+'</i> '
      + '<em class=tlrf id=tlretry>'+esc(T('Retry'))+'</em></div>';
    const rb = document.getElementById('tlretry');
    if(rb) rb.onclick = () => { TLD = null; paintTl(); loadTl(true); };
    return;
  }
  // ⚠Account pick filters before tlRange/tlGroups: session rows of several sids merge onto one `S|cwd` line.
  const apFo = typeof acctPickFocusId === 'function' ? acctPickFocusId() : '';   // ⚠tbSet below replaces the picker
  const tpk = typeof acctPick === 'function' ? acctPick('time') : '';   // read once for all rows
  const rows = (d.rows || []).filter(r => typeof acctInPick !== 'function' || acctInPick(r, 'time', tpk));
  // No sessions at all = a first run: add the next step, otherwise an empty timeline is just a quiet period.
  const tlNext = (SESS || []).length ? '' : '<div class=hidnote>' + T('Next: start an AI coding-agent session — its subagents are drawn here.') + '</div>';
  // ⚠Controls before the empty return: widening the range is the only way out of an empty window ; the git chip stays (changes exist without subagents)
  if(!rows.length){ tbSet('time', tlCtlHtml() + tlgChipHtml()); tlgWire(); box.innerHTML = '<div class=tlhd><i>' + (typeof tlEmptyMsg === 'function' ? tlEmptyMsg(d, rows) : esc(TV({msg: 'No subagents ran in the last {n}h', vars: {n: d.hours}}))) + '</i></div>' + tlNext; return void tlWireCtl(apFo); }
  const {t0, t1, span, pct} = tlRange(d, rows);
  const {ticks, axis} = tlAxis(d, t0, t1, span, pct);
  const drawn = tlDrawn(rows, pct);
  const idleb = tlIdle(d, drawn, pct), napb = tlNaps(d, drawn, pct);
  const {sessOrder, tlHidden} = tlSessions(tlGroups(rows), t0, t1);
  const ordered = tlOrdered(sessOrder, tlRunOnly);
  // Snapshot is built only from **drawn rows** — counting hidden sessions would say something different from the screen
  tlCurRows = ordered;
  const tkRow = tlTokRow(d, pct, ticks);
  tlHovG = [];
  const L = {pct, t0, idleb, ticks, napb};
  const bars = ordered.map((g, gi) => tlRow(g, gi, L)).join('');
  const tlHead = tlHeadHtml(d, rows, tlHidden, tlPlLegendFor(ordered, L));
  const tlgFo = tlgFocusId();   // ⚠rebuilding the toolbar drops a focused chip control to <body>; refocused by id below
  tbSet('time', tlCtlHtml() + tlgChipHtml());
  const sc0 = box.querySelector('.tlscr'), scTop = sc0 ? sc0.scrollTop : 0;   // ⚠the rows scroller is rebuilt every repaint — keep its position
  box.innerHTML = tlHead
    // ★No bands on the axis row (2026-09-18: mark spans only on bar rows, leave the time band alone
    // · it hurt visibility). Before, bands were laid in four places incl. the axis row and top graph row, and hatching covered
    // the screen. ⚠The axis row label («asleep N min») was removed at the same time — the bar-row band tooltip carries the explanation
    // Inline legend in the axis row's empty name cell — hatching meaning was only in band tooltips (UX audit 09-24).
    + ('<div class=tlaxr><div class="tlnm tllg"><i class=tllgn></i>'+esc(T('Asleep'))
      + '<span title="'+esc(T("The earlier part of this session's log was not read, so this span is unknown"))+'"><i class=tllgu></i>'+esc(T('Earlier log not read'))+'</span>'+'</div><div class=tlt>'+axis+'</div></div>'
      // .tlscr = the only scroller on this tab (20-timeline.css): rows scroll, the summary below stays pinned
      + '<div class=tlscr><div class=tlwrap>'+tkRow+bars
        + '<div class=tlfut id=tlfut hidden></div>'
        + '<div class=tlcur id=tlcur hidden></div>'
        + '<div class=tlcurp id=tlcurp hidden></div></div></div>'
      + '<div class=tlnote>'
      + T('The end is <b>when the last record was written</b>, so it is slightly earlier than the real finish.') + ' '
      + T('Below is a <b>summary</b> of this window; click a bar to open its work log in a new window.') + ' '
      + T('Hover <b>outside</b> the bars for a snapshot of that moment; <b>click to pin</b> it.') + ' '
      + T('Press <b>▶</b> and the cursor walks by itself (replay).') + '</div>'
      + '<div id=tldrw></div>');
  const sc1 = box.querySelector('.tlscr'); if(sc1 && scTop) sc1.scrollTop = scTop;
  tlWireCtl(apFo);
  tlgWire();
  if(tlgFo){ const f = document.getElementById(tlgFo); if(f) f.focus({preventScroll: true}); }
  tlAxFit(box);
  tlAgeTick();
  tlWireRows(box);
  tlCurApply();          // ★After redraw, **restore the pinned cursor** (same reason as tlDrawer)
  tlDrawer();
}
// en uses the CLK 12h clock like the rest of the page (24h here beside «4:00 PM» elsewhere read as two clocks)
function tlHh(sec){ return LANG === 'en' ? CLK(new Date(sec * 1000)) : hhmm(sec); }
function tlRange(d, rows){
  // ★Horizontal range is fixed to **the requested window** (2026-09-02: shrinking to 1 hour changed nothing).
  // Before, it started at the oldest bar's start, so one agent started before the window stretched the whole axis.
  const t1 = Math.max(d.at, ...rows.map(r=>r.end));
  const t0 = Math.max(t1 - (d.hours || 12) * 3600, Math.min(...rows.map(r=>r.start)));
  const span = Math.max(60, t1 - t0);
  const pct = v => ((v - t0) / span * 100);
  tlCurT0 = t0; tlCurT1 = t1;          // Used by the time cursor for mouse x → time conversion
  return {t0, t1, span, pct};
}
// Axis labels (header row) and label-less tick lines (every bar row).
function tlAxis(d, t0, t1, span, pct){
  const hh = tlHh;
  // Ticks — grid step from TL_STEPS, labels thinned by tlAxGrade
  // ★Times are written **only in one header row** (2026-09-01: move in-table labels to the header).
  // Before, every row drew tick labels, making ticks more prominent than bars.
  // Inside rows only **label-less vertical lines** remain — enough to read position.
  // ⚠Base grid = finest nice step with <= 24 ticks; which of them get a label depends on pixel width,
  // so tlAxFit picks the label step (a multiple of this one). A range-only step overlapped at 1100 (12h/24h).
  const step = TL_STEPS.find(s => span / s <= 24) || TL_STEPS[TL_STEPS.length - 1];
  // ⚠Grid on local time: UTC multiples of 2h/6h are odd hours in KST, so labels would never align.
  const off = -new Date(t0*1000).getTimezoneOffset() * 60;
  tlAxInfo = {span, at: d.at, step};
  let ticks = '', axis = '';
  for(let t = Math.ceil((t0 + off)/step)*step - off; t < t1; t += step){
    const x = pct(t).toFixed(2);
    const dt = new Date(t*1000), sod = dt.getHours()*3600 + dt.getMinutes()*60;
    const day = sod === 0;                        // Tick where the date changes
    ticks += '<div class=tlk style="left:'+x+'%"></div>';
    axis  += '<div class=tlax data-t='+t+' data-s='+sod+' style="left:'+x+'%"><i>'
           + (day ? ((dt.getMonth()+1)+'/'+dt.getDate()) : hh(t)) + '</i></div>';
  }
  return {ticks, axis};
}
const TL_STEPS = [300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400];
let tlAxInfo = null;
// ★Ticks get **grades** (CSS `.tlaxm/.tlaxd/.tlaxc` · 2026-09-21: the axis looked flat) — set per label step:
// major = next coarser multiple (30m → 1h, 1h → 3h, 2h → 6h ...), midnight shows the date, the labelled
// cell holding "now" is blue. Unlabelled ticks (`.tlaxn`) keep only their line.
function tlAxGrade(ax){
  const I = tlAxInfo, W = ax.clientWidth;
  const tks = [...ax.querySelectorAll('.tlax')];
  if(!I || !W || !tks.length) return;
  tks.forEach(k => { k.className = 'tlax tlaxm'; });   // measure at the widest (bold) weight
  const lw =Math.max(...tks.map(k => k.firstChild.getBoundingClientRect().width));
  const lab = TL_STEPS.find(s => s >= I.step && s % I.step === 0 && s / I.span * W >= lw + 8)
            || TL_STEPS[TL_STEPS.length - 1];
  const maj = [3600, 10800, 21600, 43200, 86400].find(s => s > lab && s % lab === 0) || 0;
  let curK = null;
  tks.forEach(k => {
    const s = +k.dataset.s, on = s % lab === 0;
    k.className = 'tlax' + (!on ? ' tlaxn' : (s === 0 ? ' tlaxd' : (maj && s % maj === 0 ? ' tlaxm' : '')));
    if(on && +k.dataset.t <= I.at) curK = k;
  });
  if(curK && I.at - (+curK.dataset.t) < lab) curK.classList.add('tlaxc');
}
// ⚠Labels hang right of their tick, so the last one can run past the axis edge and get cut («05:» for
// «05:00» — 12px over once the git rail narrowed the timeline). The first tick is always >= t0, so only
// the right edge can clip. ⇒ Flip an overflowing label to the left of its tick; if that would collide with
// the previous label, hide it (the tick line stays). Width-dependent, so re-fit on every axis resize.
let tlAxRO = null;
function tlAxFit(box){
  const ax = box.querySelector('.tlaxr .tlt');
  if(tlAxRO){ tlAxRO.disconnect(); tlAxRO = null; }
  if(!ax) return;
  const fit = () => {
    ax.querySelectorAll('.tlax i').forEach(i => { i.classList.remove('tlaxe'); i.style.visibility = ''; });
    tlAxGrade(ax);
    const labs = [...ax.querySelectorAll('.tlax:not(.tlaxn) i')];
    const R = ax.getBoundingClientRect().right;
    for(let k = labs.length - 1; k >= 0; k--){
      const i = labs[k];
      if(i.getBoundingClientRect().right <= R + 0.5) break;
      i.classList.add('tlaxe');
      const prev = labs[k-1], b = i.getBoundingClientRect();
      const hit = prev && prev.getBoundingClientRect().right + 4 > b.left;
      // ⚠The blue «now» label (.tlaxc) wins a collision — hiding it left the axis without its current hour for most of each hour.
      if(b.right > R + 0.5) i.style.visibility = 'hidden';
      else if(hit && i.parentNode.classList.contains('tlaxc')) prev.style.visibility = 'hidden';
      else if(hit) i.style.visibility = 'hidden';
    }
    // ⚠An en «8:00 AM» label is wider than one grid step, so the next unlabelled tick line ran through its text ⇒ drop those lines.
    const lr = labs.filter(i => i.style.visibility !== 'hidden').map(i => i.getBoundingClientRect());
    ax.querySelectorAll('.tlax.tlaxn').forEach(k => { const x = k.getBoundingClientRect().left;
      k.classList.toggle('tlaxu', lr.some(b => x > b.left - 2 && x < b.right + 2)); });
    tlBarFit(box);          // Bar widths follow the same axis width, so the same resize re-fits them
  };
  fit();
  if(window.ResizeObserver){ tlAxRO = new ResizeObserver(fit); tlAxRO.observe(ax); }
}
// ⚠Bar labels drop whole parts, never cut or wrap: «22 min · 6M» → «22 min» → hidden (hover card has the numbers).
function tlBarFit(box){
  // ⚠Read all, then write all: interleaving forced one layout per bar (28 bars ≈ 8.6ms, 2026-09-25).
  const spans = [...box.querySelectorAll('.tlrk .tlb span')];
  if(!spans.length) return;
  const rooms = spans.map(s => {
    const b = s.parentElement;
    if(s.dataset.f == null) s.dataset.f = s.textContent;
    return b.clientWidth - (parseFloat(getComputedStyle(b).paddingRight) || 0) - 3;
  });
  // Widths are per distinct text, via hidden clones of a real span (same font and box as the bar label).
  const texts = [...new Set(spans.flatMap(s => [s.dataset.f, s.dataset.s || ''].filter(Boolean)))];
  const host = spans[0].parentElement;
  const probes = texts.map(t => {
    const p = spans[0].cloneNode(false);
    p.hidden = false; p.textContent = t;
    p.style.cssText = 'position:absolute;visibility:hidden;left:0;top:0';
    host.appendChild(p);
    return p;
  });
  const wid = new Map(texts.map((t, k) => [t, probes[k].scrollWidth]));
  probes.forEach(p => p.remove());
  spans.forEach((s, k) => {
    const f = s.dataset.f, sh = s.dataset.s || '';
    if((wid.get(f) || 0) <= rooms[k]){ s.hidden = false; s.textContent = f; return; }
    s.textContent = sh;
    s.hidden = !sh || wid.get(sh) > rooms[k];
  });
}
// Drawn-bar footprints (%, sorted) — the sleep and idle bands carve these out.
function tlDrawn(rows, pct){
  // ★Lay **machine-asleep spans** as background bands (2026-09-17: why was it empty while working).
  // ★Measured that day 15:08:08-15:12:23 (4 min) — the transcript was entirely empty at 15:09·15:10·15:11.
  // If the screen does not say whether a gap is "unused" or "stopped", it is always read as the former.
  // ⚠Must not be confused with bars, so it is **gray hatching**, not a fill, and inserted **before** `.tlb`
  // in the row so it lies underneath (neither has z-index, so DOM order is paint order).
  // ★**Carve the drawn bars' «minimum width» out of the band** (2026-09-18: on zoom, a green bar
  // sat on top of the hatching. Measured 5 overlaps · all at bar width 6.7px).
  // ⚠The cause is **rendering**, not data — the backend already subtracts active spans from sleep.
  // Even a 16s fragment takes 0.5% (6.7px) because of the `Math.max(0.35/0.5, …)` minimum width in the bar code below,
  // biting into the adjacent band. ⇒ **Trim the band** (shrinking bars would make short work vanish from screen).
  // ⚠The minimum width **must move together** with the two bar-drawing sites (`bars2` 0.35 · `segs` 0.5).
  const TLBMINW = 0.5;                 // Bar minimum width (%) — use the wider of the two
  const drawn = [];
  for(const r of (rows || [])){
    const ps = (r.segs && r.segs.length) ? r.segs
             : (r.kind === 'sess' ? [] : [[r.start, r.end]]);   // ⚠Session rows draw nothing when segs is empty
    for(const p of ps){
      const dl = pct(p[0]);
      drawn.push([dl, dl + Math.max(TLBMINW, pct(p[1]) - dl)]);
    }
  }
  drawn.sort((a2, b2) => a2[0] - b2[0]);
  return drawn;
}
// Pieces of [l0, r0] with drawn-bar footprints carved out (sleep and idle bands share it).
function tlCarve(drawn, l0, r0){
  let ps = [[l0, r0]];
  for(const dg of drawn){
    if(!ps.length) break;
    if(dg[1] <= ps[0][0]) continue;
    const o2 = [];
    for(const p of ps){
      if(dg[1] <= p[0] || dg[0] >= p[1]){ o2.push(p); continue; }
      if(dg[0] > p[0]) o2.push([p[0], dg[0]]);
      if(dg[1] < p[1]) o2.push([dg[1], p[1]]);
    }
    ps = o2;
  }
  return ps;
}
function tlIdle(d, drawn, pct){
  const hh = tlHh, carve = (l0, r0) => tlCarve(drawn, l0, r0);
  // ★**Idle bands** (approved 2026-09-21 · server `_idle_gaps`). Time that is not sleep and has no bar.
  // ⚠The server guarantees zero overlap, but that is **data** — on screen the bar minimum width (TLBMINW)
  // spreads short fragments sideways (the trap already hit with sleep bands). **Trim the band** the same way.
  // ⚠Append **before** `ticks` — idle is the bottom-most layer; ticks, sleep and bars sit above it.
  let idleb = '';
  for(const iv of (d.idle || [])){
    const l = Math.max(0, pct(iv[0])), w = Math.min(100, pct(iv[1])) - l;
    if(!(w > 0)) continue;
    // ⚠The tooltip uses the **original span** (same reason as sleep bands — writing each piece's own length would
    // state the same idle period with several numbers).
    const tip = esc(TV({msg: 'Idle {n}m', vars: {n: Math.max(1, Math.round((iv[1]-iv[0])/60))}}) + ' · '
          + hh(iv[0])+'~'+hh(iv[1]));
    for(const p of carve(l, l + w)){
      const pw = p[1] - p[0];
      if(pw < 0.05) continue;                // ⚠Drop dust pieces (they look like dots)
      idleb += '<div class=tlidle style="left:'+p[0].toFixed(2)+'%;width:'+pw.toFixed(2)+'%" '
        + 'title="'+tip+'"></div>';
    }
  }
  return idleb;
}
function tlNaps(d, drawn, pct){
  const hh = tlHh;
  let napb = '';
  for(const np of (d.naps || [])){
    const l = Math.max(0, pct(np[0])), w = Math.min(100, pct(np[1])) - l;
    if(!(w > 0)) continue;
    const mm = Math.max(1, Math.round((np[1] - np[0]) / 60));
    // ⚠Tooltip and text use the **original sleep span** — writing each piece's own length would state the same sleep
    // several times with different numbers (there is only one real sleep).
    const tip = esc(TV({msg: 'Asleep {n}m', vars: {n: mm}}) + ' · '+hh(np[0])+'~'+hh(np[1])
          + '\n' + T('The Mac was asleep here — an empty record is expected'));
    for(const p of tlCarve(drawn, l, l + w)){
      const pw = p[1] - p[0];
      if(pw < 0.05) continue;          // ⚠Drop dust pieces (only the 2px border remains and looks like a dot)
      const lab = pw >= 4 ? '<i>' + TV({msg: 'Asleep {n}m', vars: {n: mm}}) + '</i>' : '';  // ⚠No text in narrow bands (it overflows)
      napb += '<div class=tlnap style="left:'+p[0].toFixed(2)+'%;width:'+pw.toFixed(2)+'%" '
        + 'title="'+tip+'">'+lab+'</div>';
    }
  }
  return napb;
}
// Rows -> row groups (one row per session / agent type+parent; concurrent runs split into their own rows).
function tlGroups(rows){
  // ★The same agent is gathered **into spans on one row** (2026-09-01: not stacked in a list).
  // Grouping key is (project + type) — different projects are different work and must not mix.
  // The click target becomes the **bar**, not the row (one row has several runs).
  const groups = [];
  const gmap = new Map();
  for(const r of rows){
    // ★The grouping key includes the **parent** (2026-09-01). Grouping by type alone mixes runs with different parents on one row
    // and lineage cannot be drawn (6 Explore runs from different agents actually happened).
    const key = r.kind === 'sess' ? ('S|' + (r.plat ? r.plat + '|' : '') + r.cwd)
              : (r.cwd + '|' + r.type + '|' + (r.par || r.parent || ''));   // Gemini children: per launching session
    let g = gmap.get(key);
    if(!g){ g = {key, sess: r.kind === 'sess', type: r.type, proj: r.proj, cwd: r.cwd, plat: r.plat, items: []};
            gmap.set(key, g); groups.push(g); }
    g.items.push(r);
  }
  // ★Same name running **concurrently** gets separate rows (2026-09-02: show parallel runs separately even with the same name).
  // Before, they stacked as lanes within one row, so row height varied
  // with lane count, drifting from the axis (the cause just fixed), and how many were running was unreadable.
  // Non-overlapping consecutive runs **stay on one row** — that reuses the same slot, so no lanes.
  const split = [];
  for(const g of groups){
    if(g.sess || g.items.length < 2){ split.push(g); continue; }
    const laneEnd = [], byLane = [];
    for(const r of g.items){
      let k = laneEnd.findIndex(e => e <= r.start);
      if(k < 0){ k = laneEnd.length; laneEnd.push(0); byLane.push([]); }
      laneEnd[k] = r.end;
      byLane[k].push(r);
    }
    if(byLane.length < 2){ split.push(g); continue; }
    byLane.forEach((items, i) => split.push(
      Object.assign({}, g, {key: g.key + '#' + i, items, _par: byLane.length, _pi: i + 1})));
  }
  groups.length = 0;
  groups.push(...split);
  return groups;
}
// Session buckets (head + agent kids), hidden off-window ones dropped, sorted running-first.
function tlSessions(groups, t0, t1){
  // ★Like git branches, **a session's agents hang below that session** (2026-09-01).
  // Before, 4 session rows came first with agents clumped below, hiding who spawned whom.
  const bySess = new Map();
  // ★A Gemini child hangs under the Claude session that launched it — resolved by its parent sid (timeline rows, then live SESS), cwd only as fallback.
  const sidCwd = new Map();
  groups.forEach(g => { if(g.sess && !g.plat) g.items.forEach(x => { if(x.sid) sidCwd.set(x.sid, g.cwd); }); });
  // CLI subagents (parent = a CLI session sid) hang under that CLI head's bucket (key with plat).
  groups.forEach(g => { if(g.sess && g.plat) g.items.forEach(x => { if(x.sid && !sidCwd.has(x.sid)) sidCwd.set(x.sid, g.plat + '|' + g.cwd); }); });
  (SESS||[]).forEach(s2 => { if(s2 && s2.sid && s2.cwd && (s2.plat || 'cc') === 'cc' && !sidCwd.has(s2.sid)) sidCwd.set(s2.sid, s2.cwd); });
  for(const g of groups){
    const sk = (g.plat ? g.plat + '|' : '') + g.cwd;      // agents carry no plat, so they hang under the Claude head
    if(g.sess){ if(!bySess.has(sk)) bySess.set(sk, {head: g, kids: [], cwd: g.cwd, plat: g.plat || ''});
                else bySess.get(sk).head = g; }
    else { const ps = (g.items.find(x => x.parent) || {}).parent;
           const kc = (ps && sidCwd.get(ps)) || g.cwd;    // Claude-space key, or `plat|cwd` for a CLI subagent
           const kp = kc === g.cwd || !g.plat || kc.indexOf(g.plat + '|') ? '' : g.plat;
           if(!bySess.has(kc)) bySess.set(kc, {head: null, kids: [], cwd: kp ? kc.slice(kp.length + 1) : kc, plat: kp});
           bySess.get(kc).kids.push(g); }
  }
  // ★**Session groups also put «running on top»** (2026-09-08: active ones should go to the top of the timeline).
  // Branches (agents) were already sorted that way on 2026-09-02,
  // but session group order stayed the server's `start` ascending (= bySess insertion order), so **a quiet session started
  // 12 hours ago took the top** and running sessions were pushed down. This screen's question is
  // "who is running now".
  // ⚠Judge by **live SESS** — the timeline response can be up to 1 min stale (must use the same
  // basis as `tlStateDot` so status dots and order agree). If absent from SESS, fall back to timeline values.
  // ⚠A session with a running agent **counts as running** even if its own state is `wait` — it is not the human's turn
  // (same judgment as `sessLabel` calling that state «waiting for subagents to finish»).
  // ⚠Order changes **only on redraw** (`tlSyncState` swaps only dots in place). Rows jumping every 2.5s
  // lose your place while reading — breaking this screen's purpose (keep beside you and compare).
  const tlLiveTid = new Set();
  (SESS||[]).forEach(s2 => (s2.sub||[]).forEach(v2 => { if(v2.tid) tlLiveTid.add(v2.tid); }));
  const sessItems = v => {
    const a2 = v.head ? v.head.items.slice() : [];
    v.kids.forEach(k => a2.push(...k.items));
    return a2;
  };
  const sessRank = v => {
    const hi = v.head ? v.head.items[v.head.items.length - 1] : null;
    const live = tlLiveOf(v.cwd || '', v.plat);     // ⚠bucket plat, not kids[0]'s — a Gemini child must not rank the Claude bucket
    const st = (live && live.gotPrompt > 0) ? 'stuck'
             : ((live && live.state) || (hi && hi.state) || 'unknown');
    const kidRun = v.kids.some(k => k.items.some(x => (x.tid && tlLiveTid.has(x.tid)) || x.run));
    if(st === 'tool' || st === 'think' || kidRun) return 0;          // Running now
    if(st === 'ask' || st === 'abort' || st === 'stuck') return 1;    // Human's turn — needs action
    if(st === 'done' || st === 'gone') return 3;                     // Finished at the very bottom
    return 2;                                                        // wait·unknown — alive but quiet
  };
  const sessLast = v => sessItems(v).reduce((m, x) => Math.max(m, x.end || 0), 0);
  // ★★**Hide sessions with no visible bar «and not connected»** (2026-09-08: rows with no bars
  // and no connection need not be shown).
  // The server filters by window. Still, a session row enters **if its span (start~end) touches the window**,
  // while that session's **active spans (`segs`) may be outside it** ⇒ empty rows with no bars remain.
  // ★Measured (2026-09-08 · `hours=3`): 5 of 10 sessions had 0 bars in window, and of those
  // `repo-C-batch`·`admin_log`·`repo-C-apms` were **also disconnected** (= to hide).
  // ⚠**It is AND — hide only when both hold.** At the same moment `proj-C/admin`·`advocate-repo` also had 0 bars
  // but **were alive** ⇒ keep. Quiet differs from absent (this file's 2026-08-24 trap:
  // a session may be launched and deliberately left doing nothing).
  // ⚠**The window parameter is `hours`** (not `h` · :11322). Measuring with `h=` makes the server ignore it and return the default
  // 12 hours, yielding the **wrong conclusion** «narrowing the window changes nothing» — this misfire actually happened
  // once. Measure anything window-related with `?hours=`.
  // ⚠The basis is **the same SESS** as `sessRank`. `state === 'done'` is disconnected,
  // and paths absent from SESS entirely are also not connected.
  // ⚠**Write down that something was hidden** — "do not say something that exists does not". Count it in the header row.
  // ⚠★**The verdict must match «the drawing code» — session heads and branches differ.**
  // Session heads draw **no bar at all** when `segs` is empty (`sg.map` — the `tlbs` site below).
  // Branches (agents) draw `start~end` **as one bar** when `segs` is empty (the `parts` site).
  // At first the fallback was applied to sessions too, and rows that should hide stayed — ★caught by directly counting
  // `.tlt > .tlb` in the DOM: three rows
  // labelled «<repo> 0 min» had **0** bars. "Data exists" and "is drawn" are different.
  const inWin = (x, sess) => {
    const sg = x.segs || [];
    if(sg.length) return sg.some(g2 => g2 && g2[1] > t0 && g2[0] < t1);
    return sess ? false : (x.end > t0 && x.start < t1);
  };
  // Compaction markers are also **visible on screen** — hiding rows that have only those erases visible information.
  const hasMark = x => (x.comp || []).some(cp => cp && cp.at > t0 && cp.at < t1);
  const sessShown = v => {
    if((SESS||[]).some(s2 => s2.cwd === (v.cwd || '') && (s2.plat || 'cc') === (v.plat || 'cc')
                             && s2.state !== 'done')) return true;
    if(v.head && v.head.items.some(x => inWin(x, true) || hasMark(x))) return true;
    return v.kids.some(k => k.items.some(x => inWin(x, false)));
  };
  const sessAll = [...bySess.values()];
  const sessKeep = sessAll.filter(sessShown);
  const tlHidden = sessAll.length - sessKeep.length;
  const sessOrder = sessKeep.sort((a2, b2) =>
    (sessRank(a2) - sessRank(b2)) || (sessLast(b2) - sessLast(a2)));
  return {sessOrder, tlHidden};
}
// Flatten sessions into drawn row order: session head, then its agents as a lineage tree (running branches first).
// runOnly: agent rows only — keep branches with a running agent (finished ancestors stay for lineage); session heads always stay.
function tlOrdered(sessOrder, runOnly){
  // ★Nested agents hang **below the agent that spawned them** (2026-09-01). meta's parentAgentId gives
  // the real lineage — before, all sat flat directly under the session, hiding who spawned whom.
  const parOf = g => (g.items.find(x=>x.par)||{}).par || '';
  const ordered = [];
  for(const v of sessOrder){
    v.kids.sort((x, y) => x.items[0].start - y.items[0].start);
    if(v.head) ordered.push(v.head);
    // ★After splitting, include ids of **all items** in the group — including only the first makes nested agents
    // spawned by the 2nd run fail to find their parent and fall directly under the session (lineage becomes false).
    const byId = new Map();
    v.kids.forEach(k => k.items.forEach(it => { if(it.aid) byId.set(it.aid, k); }));
    const childOf = new Map();          // Parent group → child groups
    const roots = [];
    for(const k of v.kids){
      const pg = byId.get(parOf(k));
      if(pg && pg !== k){ if(!childOf.has(pg)) childOf.set(pg, []); childOf.get(pg).push(k); }
      else roots.push(k);
    }
    // ★**Running on top** (2026-09-02). But lineage must not break, so not just that row but
    // **the whole branch where it or a descendant is running** is lifted — lifting only the child leaves
    // `└─ Explore` attached under someone else, falsifying who spawned it.
    const runDeep = new Map(), seen = new Set();
    const mark = k => {
      if(runDeep.has(k)) return runDeep.get(k);
      if(seen.has(k)) return false;            // Guard against lineage cycles
      seen.add(k);
      let v2 = k.items.some(x => x.run);
      for(const c of (childOf.get(k) || [])) if(mark(c)) v2 = true;
      runDeep.set(k, v2);
      return v2;
    };
    v.kids.forEach(mark);
    const ord = list => list.sort((x, y) =>
      ((runDeep.get(y) ? 1 : 0) - (runDeep.get(x) ? 1 : 0)) || (x.items[0].start - y.items[0].start));
    const walk = (list, depth) => {
      if(runOnly) list = list.filter(k => runDeep.get(k));
      ord(list);
      list.forEach((k, i) => {
        k.br = (i === list.length - 1) ? '└' : '├';
        k.lv = depth;
        ordered.push(k);
        const ch = childOf.get(k);
        if(ch) walk(ch, depth + 1);
      });
    };
    walk(roots, 0);
  }
  return ordered;
}
function tlTokRow(d, pct, ticks){
  const hh = tlHh;
  // ★Token strip (2026-09-08: show token usage alongside).
  // ⚠Cell x uses **`pct()`** — the server's window start (`tok.t0` = now-hours) and the screen's `t0`
  // (may be cut at the oldest bar) are not exactly the same. Drawing by ratio drifts from the axis.
  // ⚠Lay tick verticals (`ticks`) here too — without them this row alone looks like it has no time reference.
  let tkRow = '';
  if(d.tok && d.tok.v && d.tok.v.length){
    const tk = d.tok, mx = Math.max(1, ...tk.v);
    let kb = '';
    tk.v.forEach((val, i) => {
      if(!val) return;
      const a = tk.t0 + i * tk.step, l = pct(a), w = pct(a + tk.step) - l;
      if(l > 100 || l + w < 0) return;
      const l2 = Math.max(0, l), w2 = Math.max(0.2, Math.min(100, l + w) - l2);
      kb += '<div class=tlkb style="left:'+l2.toFixed(2)+'%;width:'+w2.toFixed(2)+'%;'
        + 'height:'+Math.max(6, Math.round(val / mx * 100))+'%" '
        // ⚠If a cell is shorter than 1 min, `hh` shows both ends as the same time (actually happened with 45s cells)
        // ⇒ write "time · N seconds".
        + 'title="'+esc(hh(a) + (tk.step < 60 ? ' · ' + U(tk.step,'s') : ' ~ ' + hh(a + tk.step))
            + ' · ' + fmtTok(val) + ' ' + T('tokens'))+'"></div>';
    });
    tkRow = '<div class="tlr tlrtk">'
      + '<div class=tlnm title="'+esc(TV({msg: 'Tokens used in this window — one cell is {n}s.\nThe tallest cell is {m}; heights are proportional.', vars: {n: tk.step, m: fmtTok(mx)}}))+'">'
      + '<b>'+((d.rows || []).some(r => r.plat) ? aiLogo('cc') + ' ' : '')+T('Tokens')+'</b><u>'+fmtTok(tk.sum||0)+'</u></div>'
      + '<div class=tlt style="height:30px">'+ticks+kb+'</div></div>';
  }
  return tkRow;
}
