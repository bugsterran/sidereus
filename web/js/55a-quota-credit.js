// ★Credit row (2026-09-09: show credit remaining as %). % is usage against the monthly limit
// (official `extra_usage.utilization`), amount is cents → currency unit.
// ⚠**Drawn separately from the 5h limit** (2026-09-10). It used to live inside `buildQuota`, so a 429 on the limit query
// dropped the whole quota block to local display and **credits vanished too** — although credits are a separate field.
// ★Measured 09-10: `err:"HTTPError 429"` left five_hour empty, yet extra arrived intact (4.8% · $9.69/$200).
// Credit amounts arrive in cents; non-USD keeps the fmtMoney digits with the currency code instead of '$'.
function creditMoney(c, cur){
  if(c == null) return '?';
  const s = fmtMoney(c/100);
  return (!cur || cur === 'USD') ? s : s.replace('$', '') + ' ' + cur;
}
function creditRow(q){
  const ex = q && q.extra;
  if(!(ex && (ex.pct!=null || ex.used!=null))) return '';
  const money = c => creditMoney(c, ex.cur);
  const p = ex.pct==null ? null : Math.round(ex.pct);
  // ★`≈` = an **approximation reconstructed as ratio × monthly limit** (header path · server `_quota_probe_hdr`).
  // Headers carry only the ratio, no cents — looking like an exact value would be a lie.
  const ap = ex.approx ? '≈' : '';
  // ⚠This row says **only "credit"** (2026-09-11: "credit" on the usage display, "credit mode" on the separate indicator).
  // This is where gauges line up; inserting status text blurs gauge reading —
  // the **status** "credit mode" is stated only in one place, the badge (`#credit`).
  // ★**This row states its own age** (2026-09-11: 16% was used but it still showed 5%).
  // Credits come only from the official API — when blocked by 429, 5h becomes fresh via OMC
  // but the amount stays frozen, and **nothing on screen said so** (payload age keeps updating).
  const cage = ex.age || 0;
  const cold = cage >= 120
    ? ' <span class="qold'+(cage>=1800?' qhot':'')+'" title="'+esc(T('Credit comes only from the official API (extra_usage) — this value freezes when the lookup is blocked'))+'">'
        + TV({msg: 'as of {t}', vars: {t: AGO(ageU(cage,0,true))}}) + '</span>'
    : '';
  return esc(T('Credit')) + ' ' + (p!=null ? gauge(p)+'<b class="'+qcls(p)+'">'+esc(fmtPct(ex.pct))+'</b> ' : '')
    + '<span class=qamt title="'+esc(T('Extra usage (credit) — official extra_usage · against the monthly limit'))+'">'
    + ap + money(ex.used) + (ex.limit!=null ? ' / '+money(ex.limit) : T(' used')) + '</span>'
    + (ex.limit!=null && ex.used!=null
        ? '<span class="'+(p!=null&&p>=90?'qhot':'')+'">'+ap+money(ex.limit-ex.used)+T(' left')+'</span>' : '')
    + cold;
}
// ⛔NOT the reset cycle's total - it sums `TLD`, so it follows the timeline's **display range**
//   (4h51m into the cycle: range 1h 90.0M vs range 6h 226.1M, gauge 225.3M). Use it only where the
//   label names that range, such as «Window summary». ⚠Quota readouts take `BURN.head` instead.
//   ⚠Buckets straddling the window start are dropped whole - undercount beats overcount.
//   ⚠Returns null until `BURN.cur` and the timeline exist; callers must handle it.
function curWinTok(){
  const bs = (typeof BURN !== 'undefined' && BURN && BURN.ok && BURN.cur) ? BURN.cur.start : null;
  const tk = (typeof TLD !== 'undefined' && TLD && TLD.ok) ? (TLD.tok || {}) : null;
  if(!bs || !tk || !tk.step || !Array.isArray(tk.v)) return null;
  let w = 0;
  for(let i = 0; i < tk.v.length; i++) if(tk.t0 + i * tk.step >= bs) w += (tk.v[i] || 0);
  return w;
}
function buildQuota(u, q){
  const el0 = document.getElementById('quota');
  if(q && (q.five_hour || q.seven_day)) QLAST = {q: q, got: Date.now()};
  else if(QLAST) q = Object.assign({}, QLAST.q,
    {age: (QLAST.q.age || 0) + Math.round((Date.now() - QLAST.got) / 1000)});
  // ★When the official quota arrives **it is the source of truth** (same value as /usage). Local totals/corrections stay only in the tooltip as reference.
  if(q && (q.five_hour || q.seven_day)){
    const fmt = sec => { if(sec==null) return '?'; return HM(Math.max(0,Math.round(sec/60))); };
    // ★Also show the **amount** used (2026-08-27: token usage should be viewable). Before only % and reset were shown,
    // actual tokens/cost were tooltip-only — surfacing them makes them readable without hovering.
    // ⚠Different sources: % is official quota (api), tokens/cost are **local totals (transcripts)**. So they are shown together but
    // the tooltip states which is which — so neither becomes false when they disagree.
    // No cost (2026-08-27: cost not needed) — token amount only.
    // ⚠If `win` (sum of this reset cycle) arrives, use it and the tooltip states **which window** — on fallback keep the old wording.
    const amt = (o2, win, gauged) => {
      const n = (win != null) ? win : (o2 && o2.tokens);
      if(!n) return '';
      return '<span class=qamt title="' + esc(gauged
          ? T('Usage from the official quota — same source as the % on the left')
          : (win != null
              ? T('Local count for this reset window (transcripts) — same window as the % above')
              : T('Local count (transcripts) — the % above is the official quota')))
        + '">' + fmtTok(n, {dec: 2}) + '</span>';
    };
    const one = (o, label, loc, win, gauged) => {
      if(!o) return '';
      const p = Math.round(o.pct);
      const d = o.resets_at ? new Date(o.resets_at) : null;
      const when = d ? ((d.toDateString()===new Date().toDateString() ? '' :
              (d.getMonth()+1)+'/'+d.getDate()+' ')
              + CLK(d)) : '?';
      const hot = (o.leftSec!=null && o.leftSec < 1800) || p >= 90;
      // ★When a value is stale, **say so on screen.** The reset countdown ticks every second, so % is mistaken for current
      // (measured 2026-08-20: 429 backoff left % 34 min old while the screen looked fine — reported as "not updating").
      // ★Each cell may have a different age (2026-09-10). Even when a 429 returns an empty `five_hour`, the server
      // **carries over values whose window has not ended** (`keptAt`) — that cell's age is not the response age (`q.age`)
      // but the last measured time. Without the distinction, stale % looks like "just now".
      const age = o.keptAt ? Math.max(0, Math.round(Date.now()/1000) - o.keptAt) : (q.age||0);
      const old = age >= 120;
      // ★Color when stale over 10 min — gray alone kept being missed
      const vold = age >= 600;
      // ★Numbers are **always official values** (2026-09-02: local estimate did not match).
      // Swapping in a local estimate when stale was tried and was worse: the local denominator was hand-corrected on 8/20
      // (5h 479M) and 13 days old, producing 81% where official said 31% (2.6x off).
      // ⇒ Showing a stale value **while saying it is stale** is right. Slotting another metric into the official slot
      // makes the screen say two different things under one name.
      // (`_quota_calibrate` auto-adjustment is disabled since 2026-09-04; the 5h denominator is burn's back-solve.)
      const ago = AGO(ageU(age,0,true));
      // the status bar shows the left share; this drawer shows used, so name it
      return label+' '+esc(T('used'))+' '+gauge(p)+'<b class="'+qcls(p)+(old?' qstale':'')+'">'+esc(fmtPct(o.pct))+'</b> '
        + amt(loc, win, gauged)
        + (old ? '<span class="qold'+(vold?' qstale2':'')+'" title="'+esc(T(String(q.err||'The lookup is running late'))
              + T(' — actual usage has risen further since then'))+'">'+TV({msg: 'as of {t}', vars: {t: ago}})+'</span> ' : '')
        // The status bar already shows the 5h countdown, so the 5h row keeps the clock; 7d uses the shared RST7 text.
        + '<span class="'+(hot?'qhot':'')+'">'+(label === '5h' ? when+' '+esc(T('reset'))
            : esc(T('reset'))+' '+(d ? esc(RST7(d).abs+' · '+RST7(d).rel) : LATER(fmt(o.leftSec))))+'</span>';
    };
    // ★5h and 7d each on **their own line** (2026-08-27). The card is 500px wide, so joining them on one line
    // wraps anywhere in the middle and one cannot tell which value belongs to which window.
    // The amount beside the % must come from the same source as the %. Mixing them printed `5h 119M`
    //   here and `5h 206M` in the burn-down below. ⚠An alternate tally belongs in the tooltip, not here.
    // Only the MEASURED local sum
    //   (cur.used_local / cur.wk_used_local) — head.used / wk.used are % x back-solved limit (estimates, 130M vs real).
    const gaugeTok = which => {
      const c = (typeof BURN !== 'undefined' && BURN && BURN.ok) ? BURN.cur : null;
      if(!c) return null;
      return which === '7d' ? (c.wk_used_local != null ? c.wk_used_local : null) : (c.used_local != null ? c.used_local : null);
    };
    const g5 = gaugeTok('5h'), g7 = gaugeTok('7d');
    // ⚠No tally fallback: until the back-solve warms up the chip shows the % alone. A number from another
    //   source here is what put `5h 119M` next to the burn-down's `5h 206M` on the same screen.
    const parts=[one(q.five_hour,'5h',null, g5, g5 != null),
                 // ★2026-09-27 cross-tab audit: 7d passed the local weekly tally here (182M first paint -> 105M after burn).
                 one(q.seven_day,'7d',null, g7, g7 != null)].filter(Boolean);
    const cr = creditRow(q);
    if(cr) parts.push(cr);
    if(typeof sbPrimNote === 'function' && sbPrimNote()) parts.unshift('<small>' + esc(sbPrimNote()) + '</small>');   // rows are the primary's
    setHtml(el0, parts.map(x => '<div class=qrow>'+x+'</div>').join(''));
    const b=(u&&u.block)||{}, w=(u&&u.week)||{};
    // ★Hover describes the **same window** as the row text (2026-09-22: fix the 165M shown here).
    // `block.tokens` is the local 5h block (e.g. 05:00-10:00), whose boundaries differ from the reset cycle (08:30-13:30),
    // so it drags in pre-reset share — the row showed 15M while hover showed 172M.
    // ⚠If it cannot be measured, use the block value but **label it as the local block**. Do not revert to unlabeled.
    const cwt = curWinTok();
    const qt = TV({msg: 'Official quota (GET /api/oauth/usage · same value as /usage) · fetched {n}s ago', vars: {n: q.age||0}})
      + (q.err ? '\n' + TV({msg: '⚠Last fetch failed: {e} (showing older values)', vars: {e: T(q.err)}}) : '')
      + '\n\n' + T('[Reference · local count]')
      // ★2026-09-27 cross-tab audit: curWinTok counts from the 5h cycle start (clipped to the loaded timeline).
      + (cwt != null ? '\n' + TV({msg: 'Tokens since this 5h reset cycle began {n} (only the timeline range, if that is shorter)', vars: {n: cwt.toLocaleString()}})
         : (b.tokens ? '\n' + TV({msg: '5h tokens {n} · ${c} (local 5h block — its edges differ from the reset cycle)', vars: {n: (b.tokens||0).toLocaleString(), c: b.cost||0}}) : ''))
      + (w.tokens ? '\n' + TV({msg: 'Weekly tokens {n} · ${c}', vars: {n: (w.tokens||0).toLocaleString(), c: w.cost||0}}) : '');
    if(el0.title !== qt) el0.title = qt;
    return;
  }
  buildQuotaLocal(u, q);
}
// ★Credit badge — says only **whether money is being spent right now** (2026-09-09).
// Both conditions required: (a) `quota.extra` exists (= extra_usage.is_enabled) (b) 5h limit at 100%.
// ⚠Turning on with (a) alone is a lie — `is_enabled` means "credits are allowed", not "in use".
// While limit remains, credits do not decrease.
function buildCredit(q){
  const el = document.getElementById('credit');
  if(!el) return;
  const ex = q && q.extra, fh = q && q.five_hour;
  // ★If the seat is **billed by usage**, do not wait for 5h (2026-09-11 · the credit-in-use badge had disappeared).
  // `enterprise_usage_based` is a seat that pays from the start, so the 5h 100% condition
  // never holds — when the 5h cell went empty on 429, the badge went off with it.
  // ⚠Subscription seats still require **5h 100%**. `is_enabled` means "can use", not "in use".
  const meter = ex && typeof ex.seat === 'string' && ex.seat.indexOf('usage_based') >= 0;
  const on = !!(ex && (meter || (fh && fh.pct != null && fh.pct >= 100)));
  if(!on){ setHtml(el, ''); if(el.className !== 'credit') el.className = 'credit'; return; }
  const money = c => creditMoney(c, ex.cur);
  const left = (ex.limit!=null && ex.used!=null) ? money(ex.limit-ex.used)+T(' left') : money(ex.used)+T(' used');
  if(el.className !== 'credit on') el.className = 'credit on';
  setHtml(el, '<b>'+esc(T('Credit mode'))+'</b><span>'+esc(left)+'</span>');   // ★Unified wording (2026-09-10)
  const ct = (meter ? TV({msg: 'This seat is billed by usage ({s}) — what you use now is billed.', vars: {s: esc(String(ex.seat))}}) + '\n'
                    : T('The 5h limit is spent; from here it draws credit (extra usage) — this is really billed.') + '\n')
    + TV({msg: '{u} used of the {l} monthly limit', vars: {u: money(ex.used), l: money(ex.limit)}})
    + (ex.pct!=null ? ' (' + fmtPct(ex.pct) + ')' : '')
    + (meter ? '' : T('\nWhen the limit resets (5h row above), usage is back to the included allowance.'));
  if(el.title !== ct) el.title = ct;
}
// Quota window of the «Main account» (UIS mbMainAcct) -> {w, main, miss}; no main = the primary's QLAST window as before.
// miss = main's row absent, errored without kept data younger than quota_roots.ROW_KEEP_S (1800 s), or without a numeric pct: the primary window is shown and the card title says so.
// m = any label (knQFor); '' or the primary's label = the primary window (matches the sblAccRows primary row).
function knQ(k, m){
  if(m === undefined) m = mainAcct();
  const q = typeof QLAST !== 'undefined' && QLAST && QLAST.q, pw = (q && (k === '5h' ? q.five_hour : q.seven_day)) || null;
  const p = (acctList() || []).find(a => a && a.primary);
  if(!m || m === String((p && p.label) || '')) return {w: pw, main: '', miss: false};
  const a = q && Array.isArray(q.accounts) ? q.accounts.find(r => r && r.label === m) : null, w = a && (!a.err || (typeof a.age === 'number' && a.age <= 1800)) ? (k === '5h' ? a.five_hour : a.seven_day) : null;
  return w && typeof w.pct === 'number' ? {w, main: m, miss: false} : {w: pw, main: m, miss: true};
}
function knQFor(k, label){ return knQ(k, String(label || '')); }
// «Show in bar» account (UIS mbKpiAcct): any label in acctList (primary included); '' or stale = follow main. View-only, never changes main.
function kpiAcct(){
  let v = ''; try{ v = String(UIS.getItem('mbKpiAcct') || ''); }catch(e){ return ''; }
  const list = acctList();
  return v && list && list.some(a => a && String(a.label || '') === v) ? v : '';
}
// Bar window -> knQ fields + kpi (the picked account when it is not the effective main, else '') + kmiss (its row missing/errored: main's window shown).
function kpiQ(k){
  const p = (acctList() || []).find(a => a && a.primary), kp = kpiAcct();
  const own = kp && kp !== (mainAcct() || String((p && p.label) || '')) ? kp : '';
  if(!own) return Object.assign(knQ(k), {kpi: '', kmiss: false});
  const r = knQFor(k, own);
  return r.miss ? Object.assign(knQ(k), {kpi: own, kmiss: true}) : Object.assign(r, {kpi: own, kmiss: false});
}
