function buildBurn(){
  buildSbar();
  const el = document.getElementById('burn');
  if(!el) return;
  const b = burnDraw(), un = burnUse(), ul = acctList() ? un.label : '';   // name the account only with >= 2 accounts
  // ⚠No current 5h window on the drawn account (idle since the last reset, or no rows yet): an empty block read as a broken chart.
  if(!(b && b.ok && b.cur)){
    const idle = !!(b && (b.why === 'stale' || b.why === 'no-data' || (un.dir && b.ok === false))), cls = idle ? 'burn on' : 'burn';
    if(el.className !== cls) el.className = cls;
    setHtml(el, idle ? burnIdle(un.dir ? un.label : '') : ''); return;
  }
  const pj = b.proj || {};
  // ★Remaining time is re-measured with **the current clock** — the response can be up to 30s old (the countdown must not look frozen).
  const nowS = Math.floor(Date.now()/1000);
  const warn = (pj.raw != null && pj.raw >= 100);
  const body = burnHead(b, nowS) + burnCurve(b);
  const cls = 'burn on' + (warn ? ' bwarn' : '');
  if(el.className !== cls) el.className = cls;   // ⚠same-value writes still fire attribute mutations every poll
  // ★Show a **text label**, not only a glyph — a lone `▾` did not show the row is clickable.
  // The click area is still the whole header row (`.bnh`). Narrowing it to the label would be worse than now.
  setHtml(el, '<div class=bnh>'+(ul ? '<b class=bnac>'+esc(ul)+'</b>' : '')+'<u>'+burnSum(pj)+'</u><i>'+(BURN_OPEN?'▴ '+esc(T('Collapse')):'▾ '+esc(T('Show curve')))+'</i></div>' + body);
  // ⚠In the modal a native title cannot be styled and pops over the modal title — use a hover card on `.bnh` instead.
  if(el.closest && el.closest('.sdrw')){
    if(el.hasAttribute('title')) el.removeAttribute('title');
    burnHcBind(el);
    if(typeof SDRW_OPEN !== 'undefined' && !SDRW_OPEN) hcHide('bnhc');
  } else {
    const tip = burnTitle(b);
    if(el.title !== tip) el.title = tip;
  }
  // ⚠No header click toggle — the drawer always shows the curve; sidereus.burn is set only from the settings modal.
}
// ⚠Warning (`.bwarn`) reddens **only this one `.bpj`** — this number is the basis of `warn` (`pj.raw >= 100`).
// ★`pj.pct == null` means **too few samples** (e.g. right after reset, 2026-09-22) — "? at reset" is unhelpful.
// No "now %" or "until reset" here — the stat panels and the status bar already show them.
function burnSum(pj){
  return (pj.pct==null ? T('rate not measured yet')
                       : TV({msg: 'At this rate: <em class=bpj>{p}</em> used by reset', vars: {p: esc(fmtPct(pj.pct))}}));
}
// Only official % and times here — no token «used / headroom» (traps/quota.md «Token headroom»).
// ⚠Do not bring back a token figure: tokens per 1% spread CV 0.29-0.49 in the backtest, ~7x between plans.
// The 5h row carries the run-out time itself (the separate ⚠ «runs out» line was folded in).
// «left ≈» from our history of tokens per 1% per account (server `est`, sidereus/burn_hist.py) — backtest
//   median error at 30/50/70% used: window average 27/22/19% vs history 12/17/15% (traps/quota.md «Token headroom»).
function burnEstTip(k, e){
  // plan changed: this window's own per-1% stands in for history (server `plan_est`)
  if(e.low) return T('this window\'s tokens per 1% × % left — estimate') + ' · ' + T('Not enough history — low accuracy');
  if(k === '7d') return TV({msg: 'this account\'s 7d history ({n} pts): tokens per 1% × % left — estimate', vars: {n: e.wk_n}});
  return e.h5_src === 'med' ? TV({msg: 'median tokens per 1% over this account\'s {n} windows × % left — estimate', vars: {n: e.h5_n}})
    : TV({msg: 'tokens per 1% over this account\'s {n} windows × % left — estimate', vars: {n: e.h5_n}});
}
// {left, tip} for «left ≈»; ⚠this window's average (used `n` ÷ `p`% × left %, from 30%) only when `est` is null.
// ★5h history from < 3 windows (server HIST_MIN_WIN) yields to the window average: live 10-05 49%, pool n=2
//   2.66M/% vs window 3.97M/% put «Used 207M · left ≈ 136M» at 60% by tokens. ⚠≥ 3 windows: history still wins.
function burnEst(b, k, n, p){
  const e = b && b.est, l = e && (k === '5h' ? e.h5_left : e.wk_left);
  const win = n != null && p >= 30 && p < 100;
  const thin = k === '5h' && e && !e.low && l != null && (e.h5_n || 0) < 3;
  if(l != null && !(thin && win)) return {left: l, tip: burnEstTip(k, e)};
  const low = b && b.est_why === 'plan' ? ' · ' + T('Not enough history — low accuracy') : '';   // plan changed: history dropped
  return win ? {left: n / p * (100 - p),
    tip: (thin ? TV({msg: 'history {n} windows — estimated from this window\'s average', vars: {n: e.h5_n || 0}}) + '\n' : '')
      + T('this window\'s average (used ÷ %) × remaining % — varies with usage') + low} : null;
}
// 7d {used, left, tip} when nothing was measured: `est` first, else head.wk (same-account step). Always «≈».
function burnWkEst(b){
  const e = b && b.est;
  if(e && e.wk_left != null && e.wk_used != null) return {used: e.wk_used, left: e.wk_left, tip: burnEstTip('7d', e)};
  const w = b && b.head && b.head.wk;
  return w && w.lim > 0 && w.used != null ? {used: w.used, left: Math.max(0, w.lim - w.used),
    tip: T('same-account tokens per 1% × % — estimate')} : null;
}
function burnWkTxt(b){
  const e = burnWkEst(b);
  return e ? T('used ≈') + ' ' + fmtTok(e.used) + ' · ' + T('left ≈') + ' ' + fmtTok(e.left) : '';
}
function burnHead(b, nowS){
  const c = b && b.cur, pj = (b && b.proj) || {}, w = b && b.wk;
  const left = p => esc(fmtPct(Math.min(100, p)));   // used %, as before
  // Used tokens are a measured local sum (server `cur.used_local`), so they stay — no ≈.
  const used = n => n == null ? '' : ' · <span title="' + esc(burnUsedTip()) + '">' + esc(T('used') + ' ' + fmtTok(n)) + '</span>';
  const lt = (k, n, p) => { const e = burnEst(b, k, n, p); return e ? ' · <span title="' + esc(e.tip) + '">' + esc(T('left ≈') + ' ' + fmtTok(e.left)) + '</span>' : ''; };
  let body = '';
  if(c && c.now_pct != null){
    const tail = pj.over_at ? TV({msg: 'runs out {t} at this pace', vars: {t: bnHM(pj.over_at)}})
               : c.reset ? T('resets') + ' ' + LATER(bnDur(Math.max(0, c.reset - nowS))) : '';
    body += '<span class=bhead><b class=blab>5h</b> ' + left(c.now_pct) + used(c.used_local) + lt('5h', c.used_local, c.now_pct) + (tail ? ' · ' + esc(tail) : '') + '</span>';
  }
  // Top-level `wk` = the official 7d snapshot (server `_qb_add_wk`); omitted when missing — never a guessed 0.
  const we = burnWkEst(b);
  if(w && w.now_pct != null && w.left > 0)
    body += '<span class="bhead bheadwk"><b class=blab>7d</b> ' + left(w.now_pct)
          + (c && c.wk_used_local != null ? used(c.wk_used_local) + lt('7d', c.wk_used_local, w.now_pct)
             : we ? ' · <span title="' + esc(we.tip) + '">' + esc(burnWkTxt(b)) + '</span>' : '')
          + ' · ' + esc(T('resets') + ' ' + LATER(bnDur(w.left))) + '</span>';
  return body;
}
function burnUsedTip(){ return T('From this PC\'s logs · other devices and claude.ai not included'); }
// ★Do **not re-add** the full goal/saver row here (2026-09-21: duplicate exposure, one was removed).
// The same text appeared in two places, the sidebar badge (`.saver.sv2`) and here — the two blocks are vertically adjacent and read as overlapping.
// ⇒ Keep only the badge (position chosen by the user on 2026-09-04). Inputs remain available via `svParts()`.
function burnCurve(b){        // the drawer always shows the curve
    const dl = b.delta, ba = b.base || {}, hasB = (ba.band || []).length >= 2;
    // ⚠The legend wraps (`flex-wrap`, 13px in the modal), so it wraps instead of pushing sideways. Still keep cells short.
    const why = ba.why === 'wide' ? T('Spread too wide · band omitted')
              : ba.why === 'flat' ? T('Spread ~0 · band omitted')
              : ba.why === 'plan' ? T('Not enough history — low accuracy')   // plan changed: old history unusable
              : ba.why === 'n'    ? TV({msg: +(ba.n||0) === 1 ? '{n} cycle sampled · band omitted' : '{n} cycles sampled · band omitted', vars: {n: ba.n||0}}) : '';
    // Glyph colours match the chart strokes: curve colour for current/extrapolation, the median grey for band/median (burnSvg).
    // ⚠Inline hex skips the light-theme twin remap — pick both twins via thc().
    const g = (c, ch) => '<b style="color:'+c+';font-weight:inherit">'+ch+'</b> ', col = burnCol(b), gr = thc('#8b95a7','#61656c');
    const o = burnOut(b);
    return '<div class=bnb>' + burnOutLab(o) + burnSvg(b)
      + '<div class=bleg><span>'+g(col, '━')+esc(T('This cycle'))+'</span>'
      + (hasB ? '<span>'+g(gr, '▨')+TV({msg: 'last {n} cycles', vars: {n: ba.n}})+' p25~p75</span><span>'+g(gr, '┄')+esc(T('median'))+'</span>'
              : ((ba.n >= 2) ? '<span>'+g(gr, '┄')+TV({msg: 'last {n} cycles median', vars: {n: ba.n}})+'</span>' : ''))
      + (why ? '<span>'+why+'</span>' : '')
      + '<span>'+g(col, '┄')+esc(T('At this rate'))+'</span>'
      + (o && o.none ? '<span>'+esc(T('No run-out before reset'))+'</span>' : '')
      + (dl == null ? '' : '<span>'+T('vs same time') + ' '+(dl>0?'+':'')+dl+'%p</span>')
      + '</div></div>';
}
function burnIdle(acct){
  const s = acct ? TV({msg: 'No active 5h window on {a} yet — the graph starts after its next use.', vars: {a: esc(acct)}})
    : esc(T('No active 5h window on the default account yet — the graph starts after its next use.'));
  return '<div class=bleg><span>'+s+'</span></div>';
}
// Label row above the plot for the run-out marker (HTML, not SVG text — the SVG is stretched). Same x as burnSvg's X();
// ⚠past 70% the label anchors at its right end so it cannot run off the chart's right edge.
function burnOutLab(o){
  if(!(o && o.at)) return '<div class=bnout></div>';   // row always reserved so the plot does not jump between polls
  const x = burnX(o.e)/BURN_W*100, pos = x > 70 ? 'right:'+(100-x).toFixed(2)+'%' : 'left:'+x.toFixed(2)+'%';
  return '<div class=bnout><span style="'+pos+';color:'+thc('#e0725f','#c11e32')+'">'+esc(TV({msg: 'Out at {t}', vars: {t: bnHM(o.at)}}))+'</span></div>';
}
// Hover card for the modal header row: fixed at the row's bottom + 6px; bound once per element (delegated, survives re-render).
function burnHcBind(el){
  if(el._bnhc) return;
  el._bnhc = 1;
  el.addEventListener('mouseover', e => {
    const h = e.target.closest && e.target.closest('.bnh');
    const bd = burnDraw();
    if(!h || !(bd && bd.cur)) return;
    const c = hcShow('bnhc', esc(burnTitle(bd, true)), 'tlhc bnhc'), r = h.getBoundingClientRect();
    c.style.left = Math.round(r.left) + 'px'; c.style.top = Math.round(r.bottom + 6) + 'px';
  });
  el.addEventListener('mouseout', e => {
    const h = e.target.closest && e.target.closest('.bnh');
    if(h && !(e.relatedTarget && h.contains(e.relatedTarget))) hcHide('bnhc');
  });
  document.addEventListener('keydown', e => { if(e.key === 'Escape') hcHide('bnhc'); });   // Escape closes the modal under the pointer
  document.addEventListener('click', e => { if(!(e.target.closest && e.target.closest('#burn .bnh'))) hcHide('bnhc'); });
}
// noToggle: the modal has no collapse toggle, so the «Click the row…» line is omitted there.
function burnTitle(b, noToggle){
  const c = b.cur;
  return TV({msg: 'Estimate — the slope of the last 45 min ({r}%/h) extended unchanged to the reset.', vars: {r: c.rate_pph==null?'?':c.rate_pph}}) + '\n' + T('The measured value is the 5h row above (official quota); this row is computed.')
    + '\n\n' + TV({msg: 'Cycle {a} – {b} · last measured {t}', vars: {a: bnHM(c.start), b: bnHM(c.reset), t: AGO(ageU(c.age,120,false))}})
    + (b.delta == null ? '' : '\n' + T('vs the median of past cycles at the same elapsed time') + ' '
        + (b.delta>0?'+':'') + b.delta + '%p')
    + (b.base && b.base.band && b.base.band.length >= 2
        ? '\n\n' + TV({msg: 'Faint band = p25–p75 of the last {n} cycles at the same elapsed time', vars: {n: b.base.n}})
          + (b.base.bw == null ? '' : TV({msg: ' (median width {w}%p)', vars: {w: b.base.bw}})) : '')
    + (noToggle ? '' : '\n' + (BURN_OPEN ? T('Click the row to collapse the curve.') : T('Click the row to expand the curve.')));
}
function buildQuotaLocal(u, q){
  const el = document.getElementById('quota');
  if(!el) return;
  if(!u || (!u.block && !u.week)){
    // Never leave it blank — cannot tell aggregating from broken
    const cr0 = creditRow(q);   // ⚠Show credits even while aggregating — it is a money value and must not be hidden
    setHtml(el, '<span class=qold>'+T('Counting usage…')
      + ((q && q.err) ? TV({msg: ' (official fetch failed: {e})', vars: {e: esc(qErrText(q.err))}}) : '') + '</span>'
      + (cr0 ? '<div class=qrow>'+cr0+'</div>' : ''));
    const t0 = T('ccusage is counting past usage (cold start 40-100s). 5h and weekly appear when it finishes.');
    if(el.title !== t0) el.title = t0;
    return;
  }
  const b=u.block, w=u.week, out=[];
  // ★Write **on screen** that the official value is missing and why — without %, people read "broken".
  out.push('<span class=qnone title="'
    + esc(T('Quota % comes only from the official fetch (GET /api/oauth/usage). It is never computed from the local count — a wrong denominator would print a wrong number.\nBelow is the amount actually used, from the local count (transcripts). It is a sum, not a calculation.'))
    + '">' + T('No quota %') + (q && q.err ? ' · ' + esc(qErrText(q.err)) : '') + '</span>');
  const R = u.reset || {};
  const fmtLeft = ms => HM(Math.max(0,Math.round(ms/60000)));
  if(b){
    // ★With an anchor (usage-anchor.json) state it is a **real reset**; without, that it is the end of a ccusage block.
    const anchored = !!R.block;
    const end = anchored ? new Date(R.block*1000) : (b.end ? new Date(b.end) : null);
    const hh = end ? CLK(end) : '?';
    const m = anchored ? Math.max(0, Math.round((R.block*1000-Date.now())/60000)) : (b.leftMin || 0);
    const left = fmtLeft(m*60000);
    // Color under 30 min — means reset is near (reset is not bad, but it affects planning)
    // ★**No %** (2026-09-04: show only officially provided values, no local calculation).
    // Local % is a **calculation** `tokens used ÷ anchor denominator`; if the denominator is off
    // it is simply wrong — measured 09-04 07:57 local 56% vs official 46% vs actual 59%.
    // The only fact available here is **amount used**. Show only that.
    const pc = '';
    out.push('5h '+pc+fmtTok(b.tokens, {dec: 2, zero: true})
      + ' <span class="'+(m<30?'qhot':'')+'">'+hh+' '+(anchored?T('reset'):T('block end'))+'·'+left+'</span>');
  }
  if(w){
    // Weekly follows the same rule — with an anchor print date/time, without show the calendar week range
    let tail;
    if(R.week){
      const d=new Date(R.week*1000);
      tail = ' <span class="'+((R.week*1000-Date.now())<6*3600e3?'qhot':'')+'">'
           + MDCLK(d)+' '+T('reset')+'·'
           + fmtLeft(R.week*1000-Date.now())+'</span>';
    } else {
      // ★Without an anchor, **say the reset is unknown.** Writing a calendar-week range reads as if it were the account's window.
      // Stating the unknown as unknown is this screen's rule.
      tail = ' <span class=qold title="'+esc(T('Put the weekly reset time from /usage in usage-anchor.json to show it here'))+'">'+T('Reset not set')+'</span>';
    }
    out.push('7d '+fmtTok(w.tokens, {dec: 2, zero: true})+' '+esc(fmtMoney(w.cost))+tail);   // % is shown only from the official value (see comment above)
  }
  const cr = creditRow(q);
  if(cr) out.push(cr);            // ⚠Even if the limit query fails, credits are a separate field — do not kill them together
  setHtml(el, out.map(x => '<div class=qrow>'+x+'</div>').join(''));   // 5h above · 7d below (one line each)
  const ago = u.stale==null ? T('?', 'ago') : AGO(ageU(u.stale,60,false));
  // 5h denominator = the back-solved burnLim() (block.max was the dropped 519M anchor); hidden when unknown.
  const bl = burnLim(), bh = bl ? BURN.head : null, bu = bh ? knUnc(bh.unc, bh.unc_n) : null;
  const bsrc = bh ? (bh.src === 'win' ? T('this window, back-solved') : T('last measurement')) : '';
  const tip = T('5h block') + (b ? ' '+b.start+' → '+b.end+' · '+(b.tokens||0).toLocaleString()+' tok · $'+b.cost : '')
    + (w ? '\n' + TV({msg: 'Weekly ({w}) {n} tok · ${c}', vars: {w: w.week, n: (w.tokens||0).toLocaleString(), c: w.cost}}) : '')
    + '\n' + TV({msg: 'Counted: ccusage backfill {a} + {n} live since', vars: {a: ago, n: u.live||0}})
    + (bl ? '\n' + TV({msg: '5h denominator ({s}) ≈{n} tok', vars: {s: bsrc, n: Math.round(bl).toLocaleString()}}) + (bu ? ' '+bu[0] : '') : '')
    + (w && w.max ? '\n' + TV({msg: 'Weekly denominator ({s}) {n} tok', vars: {s: T(w.src||'?'), n: (w.max||0).toLocaleString()}}) : '')
    + '\n' + T('⚠The official limit has no API (claude-code#43149). The 5h denominator is an estimate back-solved from the official % and local tokens; the weekly one is the observed maximum, so if you never hit the limit it reads higher than reality.')
    + '\n' + (R.block||R.week ? T('Reset time: anchor from /usage + cycle (exact)')
                       : T('⚠Reset time: ccusage blocks (5h = first activity rounded down · weekly = calendar week), not the account\'s real reset. Put the /usage values in usage-anchor.json to make it exact.'));
  if(el.title !== tip) el.title = tip;
}
// Uncertainty of a back-solved headroom (`head.unc` / `wk.unc`, a fraction) -> [short text, method line]; null when missing.
// ★Shown even when large (an early estimate shows its error and converges, never hidden behind a guard); over 50% the ± is meaningless, so it reads «early estimate».
// n = per-sample estimates behind the spread term (5h); 0 = rounding term only (7d).
function knUnc(u, n){
  if(u == null || !isFinite(u)) return null;
  const p = Math.round(u * 100);
  const t = u > 0.5 ? T('early estimate') : '±' + (p < 1 ? '<1' : p) + '%';
  return [t,
    t + ' — ' + (n ? TV({msg: 'larger of official-% rounding (±0.5pt) and the spread of the last {n} samples', vars: {n: n}})
      : T('official-% rounding error (±0.5pt)'))
      + '\n' + T('Estimate — the error shrinks and converges as samples accumulate (small jumps are normal)')];
}
