// Harness gate cost line (/api/harness d.cost): counts and times side by side, never combined into one score.
// ⚠No subtraction or weighting here: the line only reports what was recorded; missing data reads «not measured».
const HN_COSTBY = { stop: 'Stop', strict: 'Strict mode off', strict_off: 'Strict mode off', skip: 'Skip',
  pending: 'Still within 30 min', open: 'Still within 30 min', none: 'No resume recorded' };   // fixed keys only; unknown `by` shows nothing
function hnCostByTxt(by){ return typeof by === 'string' && Object.prototype.hasOwnProperty.call(HN_COSTBY, by) ? T(HN_COSTBY[by]) : ''; }
// ms -> short duration; null/invalid = not measured.
function hnCostDur(ms){
  if(ms == null || ms === '' || !isFinite(Number(ms)) || Number(ms) < 0) return T('not measured');
  const n = Number(ms);
  if(n < 1000) return Math.round(n) + ' ms';
  const s = Math.round(n / 1000);
  return s < 60 ? U(s, 's') : s < 3600 ? U(Math.floor(s / 60), 'm') + (s % 60 ? ' ' + U(s % 60, 's') : '') : HM(Math.floor(s / 60));
}
function hnCostRows(c, k){ const ev = c.ev && typeof c.ev === 'object' ? c.ev[k] : null; return Array.isArray(ev) ? ev.filter(r => r && typeof r === 'object').slice(0, 30) : []; }
// One item: a button when evidence rows exist (toggles the list under the line), plain text otherwise.
function hnCostItem(c, k, txt, title){
  const tt = title ? ' title="' + esc(title) + '"' : '';
  if(!hnCostRows(c, k).length) return '<span class=hncit' + tt + '>' + esc(txt) + '</span>';
  const on = HN.fold.cost === k;
  return '<button type=button class="hncit hncb' + (on ? ' on' : '') + '" data-hncost=' + k + ' aria-expanded=' + (on ? 'true' : 'false') + tt + '>' + esc(txt) + '</button>';
}
function hnCostEv(c, k){
  const rows = hnCostRows(c, k), by = k === 'overridden';
  if(!rows.length) return '';
  const th = ['Reason', 'Stage', 'Time', 'Duration'].concat(by ? ['Overridden by'] : []);
  return '<div class=hncev data-hncev=' + k + '><table class="brt hncevt"><thead><tr>' + th.map(h => '<th>' + esc(T(h)) + '</th>').join('') + '</tr></thead><tbody>'
    + rows.map(r => '<tr><td class=brd>' + esc(r.code == null ? '' : r.code) + '</td><td class=brd>' + esc(r.stage == null ? '' : hnStg(String(r.stage))) + '</td><td class=brv>'
      + esc(hnWhen(r.ts)) + '</td><td class=brv>' + esc(r.dur_ms == null ? '' : hnCostDur(r.dur_ms)) + '</td>' + (by ? '<td class=brd>' + esc(hnCostByTxt(r.by)) + '</td>' : '') + '</tr>').join('')
    + '</tbody></table></div>';
}
function hnCost(d){
  if(!d || typeof d !== 'object' || d.cost === undefined) return '';   // key absent (other platform / older server): no line
  const c = d.cost && typeof d.cost === 'object' && !Array.isArray(d.cost) ? d.cost : {};   // ⚠null = server failed: every value reads «not measured»
  const cn = x => x == null || x === '' || !isFinite(Number(x)) ? T('not measured') : hnN(x);   // null count = no run was read, never 0
  const r = d.report && typeof d.report === 'object' ? d.report : {}, cnt = r.counts && typeof r.counts === 'object' ? r.counts : {};
  const since = hnWhen(r.since), dot = '<span class=hncdot>·</span>';
  if(HN.fold.cost && !hnCostRows(c, HN.fold.cost).length) HN.fold.cost = '';   // the list it pointed at is gone
  const gate = c.gate_ms == null ? T('not measured') : (c.gate_lb ? '≥' : '') + hnCostDur(c.gate_ms);
  const counts = '<span class=hncg>' + '<span class=hncit' + (since ? ' title="' + esc(TV({msg: 'since {d}', vars: {d: since}})) + '"' : '') + '>' + esc(TV({msg: 'Caught {n}', vars: {n: hnN(cnt.caught)}})) + '</span>'
    + dot + hnCostItem(c, 'blocked', TV({msg: 'Blocked {n}', vars: {n: cn(c.blocked)}}))
    + dot + hnCostItem(c, 'overridden', TV({msg: 'Overridden {n}', vars: {n: cn(c.overridden)}}))
    + dot + hnCostItem(c, 'unknown', TV({msg: 'unknown {n}', vars: {n: cn(c.unknown)}})) + ' <i class=hntm>' + esc(T('last 7 days')) + '</i></span>';
  const times = '<span class=hncg>' + hnCostItem(c, 'gate', TV({msg: 'Gate time {d}', vars: {d: gate}}), c.gate_ms != null && c.gate_lb ? T('lower bound') : '')
    + dot + '<span class=hncg>' + hnCostItem(c, 'hook', TV({msg: 'Hook overhead {d}', vars: {d: hnCostDur(c.hook_ms)}})) + ' <i class=hntm>' + esc(T('all projects')) + '</i></span>'
    + dot + hnCostItem(c, 'pause', TV({msg: 'Paused by a block {d}', vars: {d: hnCostDur(c.pause_ms)}})) + '</span>';
  return '<div class="hncost hncl">' + counts + dot + times + '<i class="hntm hncnote">' + esc(T('Counts only — no combined score')) + '</i></div>'
    + (HN.fold.cost ? hnCostEv(c, HN.fold.cost) : '');
}
// Open state lives in HN.fold.cost (one list at a time, closed by default, kept across repaints).
document.addEventListener('click', e => {
  const b = e.target && e.target.closest && e.target.closest('.hnw [data-hncost]');
  if(!b) return;
  const k = b.dataset.hncost;
  HN.fold.cost = HN.fold.cost === k ? '' : k;
  plPaint();
  const n = document.querySelector('.hnw [data-hncost="' + k + '"]');   // repaint replaced the button: keep keyboard focus, never scroll
  if(n) n.focus({ preventScroll: true });
});
