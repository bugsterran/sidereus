// Project picker shared by «Pipelines» (48 plChips) and «Structure» (80 paintStruct), both the ppComboHtml combobox:
//   one anchored search popover grouped Working / Recent / All.
//   Metadata only (paths, names, counts). Adapters keep their own state/storage and call ppRecent on a pick.
const PP_RECENT_N = 5;
const PPC = {};          // cfg by key, refreshed on every combobox render (the popover reads the latest snapshot)
let PPS = null;          // open popover {cfg, q, i, rows}
const ppByName = (a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0);
// Pure: items [{p, name, live, run}] → {work, rec, all}, disjoint; q filters by name or path.
function ppGroups(items, recent, cur, q){
  items = items || []; recent = recent || [];
  const by = new Map(items.map(e => [e.p, e]));
  const work = items.filter(e => e.live || e.run).sort((a, b) => (b.run ? 1 : 0) - (a.run ? 1 : 0) || ppByName(a, b));
  const s = String(q || '').trim().toLowerCase();
  const hit = e => !s || String(e.name || '').toLowerCase().includes(s) || String(e.p).toLowerCase().includes(s);
  const w = work.filter(hit), wk = new Set(w.map(e => e.p));
  const rec = recent.slice(0, PP_RECENT_N).map(p => by.get(p)).filter(e => e && hit(e) && !wk.has(e.p));
  const rk = new Set(rec.map(e => e.p));
  const all = items.filter(e => hit(e) && !wk.has(e.p) && !rk.has(e.p)).sort((a, b) => (a.last ? 1 : 0) - (b.last ? 1 : 0) || ppByName(a, b));   // e.last = after the rest (48 self-only chip)
  return { work: w, rec: rec, all: all };
}
// Pure: ↑↓ step through n rows, wrapping at both ends; -1 when the list is empty.
function ppStep(i, d, n){
  if(!n) return -1;
  if(i < 0) return d > 0 ? 0 : n - 1;
  return ((i + d) % n + n) % n;
}
// Pure list update: p to the front, deduped, capped at 5.
function ppRecentList(list, p){ return [p].concat((list || []).filter(x => x && x !== p)).slice(0, PP_RECENT_N); }
function ppRecent(key, p){
  if(!p) return tabJson(key, []);
  const l = ppRecentList(tabJson(key, []), p);
  tabSetJson(key, l);
  return l;
}
// Combobox (Pipelines · Structure): one button with the current project's full name; opens the same popover. cfg.badge(e) = trailing html (live dot).
//   Optional (pipeline picker, 48 plPickHtml): flat(q) → rows without group headers · rowHtml(e, i) · ph (search placeholder)
//   · none (button text with no cur) · empty (no-match text); no rkey = no recent list. Absent = project behaviour unchanged.
//   Optional tip(e) → button title (default: the path) · note(e) → trailing html on a popover row (Structure: session count).
//   · bare: no visible label; it moves to the button's aria-label and first title line (tight rows, Timeline head).
function ppComboHtml(cfg){
  PPC[cfg.k] = cfg;
  const p = cfg.cur || '', e = (cfg.items || []).find(x => x.p === p) || { p: p, name: p.slice(p.lastIndexOf('/') + 1) || p };
  const nm = p ? e.name || p : cfg.none || T('Pick a project'), tt = cfg.tip && p ? cfg.tip(e) : p;
  return (cfg.bare ? '' : '<b>' + esc(cfg.label) + '</b>') + '<button type=button class="strp ppbtn ppcombo" data-ppk="' + esc(cfg.k) + '" aria-haspopup=listbox aria-controls=ppop aria-expanded="'
    + (PPS && PPS.cfg.k === cfg.k ? 'true' : 'false') + '"' + (cfg.bare ? ' aria-label="' + esc(cfg.label + ': ' + nm + (cfg.aria ? ' · ' + cfg.aria : '')) + '"' : '')
    + ' title="' + esc(cfg.bare ? cfg.label + (tt ? '\n' + tt : '') : tt) + '"><span class=ppcn>' + esc(nm) + '</span>'
    + (p && cfg.badge ? cfg.badge(e) : '') + ' ▾</button>';
}
// Pure: items whose name or p contains q (case-insensitive), order kept; the flat list of a cfg.flat picker.
function ppFilter(items, q){
  const s = String(q || '').trim().toLowerCase();
  return (items || []).filter(e => !s || String(e.name || '').toLowerCase().includes(s) || String(e.p).toLowerCase().includes(s));
}
function ppRowHtml(e, i){
  return '<div class="cmdki' + (i === PPS.i ? ' on' : '') + (e.p === PPS.cfg.cur ? ' ppcur' : '') + '" role=option data-ppi="' + i + '" title="' + esc(e.p) + '">'
    + '<span class=cmdkp>' + esc(e.name || e.p) + '</span>' + (e.run ? '<i class=mvdot></i>' : e.live ? '<i class=ppdot></i>' : '')
    + (PPS.cfg.note ? PPS.cfg.note(e) : '') + '<span class=cmdkc>' + esc(e.p) + '</span></div>';
}
function ppListPaint(){
  const l = document.querySelector('#ppop .cmdkl');
  if(!l || !PPS) return;
  const c = PPS.cfg, row = c.rowHtml || ppRowHtml;
  const g = c.flat ? null : ppGroups(c.items, tabJson(c.rkey, []), c.cur, PPS.q);
  PPS.rows = g ? g.work.concat(g.rec, g.all) : c.flat(PPS.q);
  if(PPS.i >= PPS.rows.length) PPS.i = PPS.rows.length - 1;
  let i = 0;
  const grp = (t, a) => a.length ? '<div class=ppg>' + esc(T(t)) + '</div>' + a.map(e => row(e, i++)).join('') : '';
  l.innerHTML = !PPS.rows.length ? '<div class=cmdke>' + esc(c.empty || T('No matching projects')) + '</div>'
    : g ? grp('Working', g.work) + grp('Recent', g.rec) + grp('All', g.all) : PPS.rows.map(e => row(e, i++)).join('');
  const on = l.querySelector('.cmdki.on');
  // ⚠Scroll the list box only — scrollIntoView could move the page under a fixed popover.
  if(on){ if(on.offsetTop < l.scrollTop) l.scrollTop = on.offsetTop; else if(on.offsetTop + on.offsetHeight > l.scrollTop + l.clientHeight) l.scrollTop = on.offsetTop + on.offsetHeight - l.clientHeight; }
}
function ppBtn(k){ return document.querySelector('[data-ppk="' + k + '"]'); }
function ppClose(focusBack){
  if(!PPS) return;
  const k = PPS.cfg.k, o = PPS.btn; PPS = null;
  popHide('ppop', o && o.isConnected ? o : ppBtn(k), focusBack);   // by key when a pipeline repaint replaced the opener
}
function ppOpen(cfg, btn){
  if(PPS){ const same = PPS.cfg.k === cfg.k; ppClose(false); if(same) return; }
  const p = popGet('ppop', 'cmdkb ppop');
  const ph = cfg.ph || T('Find a project');
  p.setAttribute('role', 'dialog'); p.setAttribute('aria-label', ph);
  PPS = { cfg: cfg, q: '', i: -1, rows: [], btn: btn };   // btn: opener may be another control (77 Timeline chip)
  p.innerHTML = '<input type=text data-ppq placeholder="' + esc(ph) + '" aria-label="' + esc(ph) + '">'
    + '<div class=cmdkl role=listbox></div><div class="cmdkf ppf">' + (cfg.extra || '') + '<span>' + esc(T('↑↓ move')) + ' · '
    + esc(T('Enter pick')) + ' · ' + esc(T('Esc close')) + '</span></div>';
  PPS.i = 0;
  ppListPaint();
  popAnchor(p, btn, { flipY: true, w: 360 });
  p.querySelector('[data-ppq]').focus({ preventScroll: true });
}
function ppPick(i){
  const e = PPS && PPS.rows[i];
  if(!e) return;
  const cfg = PPS.cfg;
  ppClose(true);
  if(cfg.rkey) ppRecent(cfg.rkey, e.p);
  cfg.pick(e.p);
  const b = ppBtn(cfg.k);   // a full repaint (pipeline tab) replaces the opener: focus its successor
  if(b && document.activeElement !== b) b.focus({ preventScroll: true });
}
popReg('ppop', '#ppop,[data-ppk],[data-ppo]', ppClose);   // data-ppo = extra opener that toggles itself
document.addEventListener('click', e => {
  const b = e.target.closest && e.target.closest('[data-ppk]');
  if(b){ const c = PPC[b.dataset.ppk]; if(c) ppOpen(c, b); return; }
  if(!PPS || !e.target.closest || !e.target.closest('#ppop')) return;
  const r = e.target.closest('[data-ppi]');
  if(r) return ppPick(+r.dataset.ppi);
  if(e.target.closest('.ppf button')){ const cfg = PPS.cfg; ppClose(false); if(cfg.onExtra) cfg.onExtra(); }
});
document.addEventListener('input', e => {
  if(!PPS || !e.target.matches || !e.target.matches('#ppop [data-ppq]')) return;
  PPS.q = e.target.value; PPS.i = 0; ppListPaint();
});
document.addEventListener('keydown', e => {
  if(!PPS || !e.target.matches || !e.target.matches('#ppop [data-ppq]') || e.isComposing) return;
  if(e.key === 'ArrowDown' || e.key === 'ArrowUp'){ e.preventDefault(); PPS.i = ppStep(PPS.i, e.key === 'ArrowDown' ? 1 : -1, PPS.rows.length); ppListPaint(); }
  else if(e.key === 'Enter'){ e.preventDefault(); ppPick(PPS.i); }
});
window.addEventListener('resize', () => { ppClose(false); });
