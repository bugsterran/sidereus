// Status-bar layer: per-account quota + open sessions, anchored above #sbar (the bar click opens it;
// the centred «Quota details» modal is one click deeper through its button). Metadata only — counts, labels, percents.

// One row per signed-in account: the primary (QLAST.q windows) first, then quota.accounts. l5/l7 = left %, '—' when unknown.
function sblAccRows(q, list, main){
  if(!q) return [];
  const p = (list || []).find(a => a && a.primary), pl = String((p && p.label) || '');
  const used = w => w && typeof w.pct === 'number' ? w.pct : null;
  const left = w => used(w) == null ? '—' : fmtPct(Math.max(0, 100 - w.pct));
  // resets_at arrives as an ISO string or epoch seconds.
  const rs = w => { const d = w && w.resets_at ? new Date(typeof w.resets_at === 'number' ? w.resets_at * 1000 : w.resets_at) : null; return d && !isNaN(d) ? CLK(d) : ''; };
  // ⚠A failed refetch keeps the last pct next to err (sidereus/quota_roots.py): show it while age <= ROW_KEEP_S (1800 s, same cap
  //   as knQ) so the numbers survive the 429 backoff; no age or older = failed, never an unbounded stale %.
  const row = (a, prim) => { const e = !prim && !!a.err && !(typeof a.age === 'number' && a.age <= 1800), w5 = e ? null : a.five_hour, w7 = e ? null : a.seven_day;
    return {label: prim ? (pl || '—') : String(a.label || '—'), c: prim ? '' : String(a.label || ''),
      l5: left(w5), l7: left(w7), u5: used(w5), u7: used(w7), rs5: rs(w5), main: false, primary: prim, err: e}; };
  const rows = [row(q, true)];
  for(const a of (Array.isArray(q.accounts) ? q.accounts : [])) if(a && !(pl && a.label === pl)) rows.push(row(a, false));
  // Exactly one mark: the chosen main account, else (unset or not in the quota response) the primary.
  const mi = main ? rows.findIndex(r => !r.primary && r.c === main) : -1;
  rows[mi >= 0 ? mi : 0].main = true;
  return rows;
}
// Remaining-token estimate {left, tip} for a row: primary = BURN, the non-primary main = its own body (burnFor); else null.
function sblEst(r, k){
  const prim = r.primary, b = prim ? (typeof BURN !== 'undefined' ? BURN : null) : (r.c && r.c === mainAcct() && typeof burnFor === 'function' ? burnFor() : null);
  if(!(b && b.ok)) return null;
  const c = b.cur || {}, p = k === '5h' ? r.u5 : r.u7;
  if(p == null) return null;
  if(k === '5h') return burnEst(b, '5h', prim ? c.used_local : null, p);
  return prim && c.wk_used_local != null ? burnEst(b, '7d', c.wk_used_local, p) : burnWkEst(b);
}
function sblEstHtml(r, k){
  const e = sblEst(r, k);
  return e && e.left != null ? '<small class=sbl-est title="' + esc(e.tip) + '">' + esc(TV({msg: '≈ {n} left', vars: {n: fmtTok(e.left)}})) + '</small>' : '';
}
function sblHtml(nowMs){
  const q = typeof QLAST !== 'undefined' && QLAST && QLAST.q;
  const rows = sblAccRows(q, acctList(), mainAcct());
  let h = connStaleNote(CONN, nowMs == null ? Date.now() : nowMs);
  // «Show in bar» lives above the grid (not a .sbl-tbl child) so the shared subgrid columns stay untouched; 2+ accounts only.
  const al = typeof kpiAcct === 'function' && acctList();
  if(al){ const kp = kpiAcct(), o = (v, t) => '<option value="' + esc(v) + '"' + (v === kp ? ' selected' : '') + '>' + t + '</option>';
    h += '<label class=sbl-kpi>' + esc(T('Show in bar')) + ' <select data-kpi>' + o('', esc(T('Follow main')))
      + al.map(a => o(String((a && a.label) || ''), esc(String((a && a.label) || '')))).join('') + '</select></label>'; }
  // One .sbl-tbl grid owns the column template; rows are subgrids, so every row shares the same column x-positions.
  h += '<div class=sbl-tbl><div class="sbl-acc sbl-hd"><span>' + esc(T('Account')) + '</span><span>5h ' + esc(T('left')) + '</span><span>7d ' + esc(T('left'))
    + '</span><span>' + esc(T('Resets')) + '</span></div>';
  // Non-main rows switch the main account only with 2+ rows and 2+ signed-in accounts (multi); the main row is not a control.
  const multi = rows.length >= 2 && (acctList() || []).length >= 2;
  const sw = r => multi && !r.main && !r.err && (r.primary || mainAcctOk(r.c) === r.c);
  const pcls = u => u == null ? '' : ' class=' + sbPctCls(u);
  h += rows.map(r => '<div class="sbl-acc' + (r.main ? ' sbl-me' : '') + (sw(r) ? ' sbl-sw" role=button tabindex=0 data-acct="' + esc(r.c) + '" title="' + esc(T('Make main account')) : '') + '">'
    + '<span class="' + esc(acctCls(r.c)) + '">'
    + (r.main ? '<i class=sbl-main title="' + esc(T('Main account')) + '"></i>' : '') + esc(r.label)
    + (r.main ? '<em class=sbl-badge>' + esc(T('Main')) + '</em>' : '')
    + (r.err ? '<em class="sbl-badge sbl-err" title="' + esc(T('Quota fetch failed for this account')) + '">' + esc(T('Failed', 'short')) + '</em>' : '') + '</span>'
    + '<span><b' + pcls(r.u5) + '>' + esc(r.l5) + '</b>' + (r.err ? '' : sblEstHtml(r, '5h')) + '</span><span><b' + pcls(r.u7) + '>' + esc(r.l7) + '</b>' + (r.err ? '' : sblEstHtml(r, '7d')) + '</span><small>' + esc(r.rs5 || '—') + '</small>'
    // Hint overlays the reset cell (absolute), shown by CSS on :hover/:focus-visible only, so columns never shift.
    + (sw(r) ? '<em class=sbl-hint aria-hidden=true>' + esc(T('Make main')) + '</em>' : '') + '</div>').join('');
  if(!rows.length) h += '<div class=sbl-acc><span>—</span></div>';
  h += '</div>';
  const s = sesCount();
  h += '<div class=sbl-ses>' + esc(T('Open sessions')) + ' <b>' + s.open + '</b> · ' + esc(T('Working')) + ' ' + s.work
    + ' · ' + esc(T('Idle')) + ' ' + s.idle + (s.need > 0 ? ' · ' + esc(T('Waiting on you')) + ' <b>' + s.need + '</b>' : '') + '</div>';
  return h + '<button type=button class=sbl-btn data-sdrw>' + esc(T('Quota details')) + '</button>';
}
// Display-only switch (UIS mbMainAcct, '' = primary, same key as Preferences); the layer stays open and keeps focus.
function sblMakeMain(v){
  v = String(v || '');
  if(v === mainAcct()) return;
  if(v && mainAcctOk(v) !== v) return;   // junk data-acct: only a non-primary label still in state accts
  mpPut('mbMainAcct', v || null);
  mpMainAcctRedraw();   // sessions · attention · recent · status bar (repaints this layer) · drawer badge (90b)
  // The clicked row is now the main row (not a control): focus the container.
  const p = document.getElementById('sblpop'); if(p) p.focus({preventScroll: true});
}
// ⚠A repaint replaces focused children: put keyboard focus back on the same account row, else the container.
function sblPaint(){
  const p = document.getElementById('sblpop'); if(!p) return;
  const a = document.activeElement, had = a && a !== p && p.contains(a), k = had && a.getAttribute('data-acct');
  if(!setHtml(p, sblHtml(Date.now())) || !had) return;
  const b = a.hasAttribute('data-kpi') ? p.querySelector('[data-kpi]') : k == null ? null : [...p.querySelectorAll('[data-acct]')].find(n => n.getAttribute('data-acct') === k);
  (b || p).focus({preventScroll: true});
}
function sblClose(focus){ popHide('sblpop', document.getElementById('sbar'), focus, {preventScroll: true}); }
function sblToggle(){
  if(popIsOpen('sblpop')) return sblClose(false);
  const bar = document.getElementById('sbar'), p = popGet('sblpop', 'thpop sblpop');
  p.setAttribute('role', 'dialog'); p.setAttribute('aria-label', T('Quota and session summary'));
  const acc = e => e.target.closest && e.target.closest('#sblpop [data-acct]');
  p.onclick = e => { const r = acc(e); if(r) sblMakeMain(r.getAttribute('data-acct')); };
  // View-only pick: stores mbKpiAcct and repaints the bar (which repaints this layer); main stays as it is.
  p.onchange = e => { const s = e.target.closest && e.target.closest('#sblpop [data-kpi]'); if(s){ mpPut('mbKpiAcct', s.value || null); buildSbar(); } };
  p.onkeydown = e => { const r = acc(e); if(r && (e.key === 'Enter' || e.key === ' ')){ e.preventDefault(); sblMakeMain(r.getAttribute('data-acct')); } };
  p._sh = null; sblPaint();
  popAnchor(p, bar, {flipY: true, align: 'right'});
  // Focus the container (not a row) so the 2.5s repaint never drops it.
  p.tabIndex = -1; p.focus({preventScroll: true});
}
popReg('sblpop', '#sbar, #sblpop', sblClose);
