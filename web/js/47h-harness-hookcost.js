// Harness hook-cost reasons (#28 R1-R4): 47b hnVdTxt delegates unknown ids here; null = fall back to the level label.
// Returns plain text: hnVdRow escapes it. Only counts arrive from the server (vp); numbers never pass through T().
function hnVdTxtHook(v){
  const a = (v && v.vp) || {}, num = x => (x == null || x === '' || !isFinite(Number(x))) ? '' : Math.round(Number(x));
  switch(v && v.why){
    case 'slow':
      return TV({msg: 'Slow — avg {n} ms over {m} runs', vars: {n: num(a.avg), m: num(a.runs)}})
        + (Number(a.k) >= 2 ? TV({msg: ' · {k} hooks combined', vars: {k: num(a.k)}}) : '');   // R2: the time is the sum of every hook on that Event:subject
    case 'no_effect':   // R3 limit sentence; min = server VD_QUIET_RUNS
      return TV({msg: 'No visible effect — {min}+ runs, never blocked, never printed', vars: {min: num(a.min) || 50}}) + ' · ' + T('side effects such as file writes are not visible here');
  }
  return null;
}
// R4: OTel counted firings but no cost record came back = time/effect unknown; a muted hint, not a verdict.
function hnHookHint(h){
  return h && h.cost == null && h.nsrc === 'otel' && Number(h.n) > 0
    ? '<span class="hncost hnvdr" style="opacity:.6">' + esc(T('time and effect not measured yet')) + '</span>' : '';
}
