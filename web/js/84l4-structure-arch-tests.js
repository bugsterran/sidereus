// ── Structure «Architecture» security window: «Include test code» run option and the excluded-tests line (84l) ──
// Pure: «Include test code» box of the run preview; unchecked by default → the body / command carry --no-tests.
function archChkTestBox(S){ return '<label class=ckimgb><input type=checkbox data-cktests' + (S && S.run && S.run.tests ? ' checked' : '') + '> ' + esc(T('Include test code')) + '</label>'; }
// Pure: «Test code excluded · N files» beside the scanner states; '' unless the result carries tests_excluded with a natural n.
// ⚠n is scanner-run data: esc, and an old result without the key shows nothing (unknown is not zero).
function archChkTestBadge(sec){
  const x = sec && sec.tests_excluded, n = x && typeof x === 'object' && !Array.isArray(x) ? x.n : null;
  if(typeof n !== 'number' || !Number.isInteger(n) || n < 0) return '';
  return '<div class="archckst cktestx">' + esc(T('Test code excluded · {n} files').replace('{n}', () => String(n))) + '</div>';
}
