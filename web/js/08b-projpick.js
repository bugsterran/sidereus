// Project picker shared by «Pipelines» (48 plChips, combobox) and «Structure» (80 paintStruct, short chip row
//   selection · working · recent + «More ▾»): one anchored search popover grouped Working / Recent / All.
//   Metadata only (paths, names, counts). Adapters keep their own state/storage and call ppRecent on a pick.
const PP_RECENT_N = 5;
const PPC = {};          // cfg by key, refreshed on every chip render (the popover reads the latest snapshot)
let PPS = null;          // open popover {cfg, q, i, rows}
const ppByName = (a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0);
// Pure: items [{p, name, live, run}] → {chips, work, rec, all}. q filters the groups only (chips ignore it).
function ppGroups(items, recent, cur, q){
  items = items || []; recent = recent || [];
  const by = new Map(items.map(e => [e.p, e]));
  const work = items.filter(e => e.live || e.run).sort((a, b) => (b.run ? 1 : 0) - (a.run ? 1 : 0) || ppByName(a, b));
  const chips = [], seen = new Set();
  const push = e => { if(e && !seen.has(e.p)){ seen.add(e.p); chips.push(e); } };
  // ⚠Stable order (working → recent by name → selection last): recency picks members, never positions, so a click does not reshuffle the row.
  work.forEach(push);
  recent.slice(0, PP_RECENT_N).map(p => by.get(p)).filter(Boolean).sort(ppByName).forEach(push);
  if(cur) push(by.get(cur) || { p: cur, name: cur.slice(cur.lastIndexOf('/') + 1) || cur });   // selection always shows
  const s = String(q || '').trim().toLowerCase();
  const hit = e => !s || String(e.name || '').toLowerCase().includes(s) || String(e.p).toLowerCase().includes(s);
  const w = work.filter(hit), wk = new Set(w.map(e => e.p));
  const rec = recent.slice(0, PP_RECENT_N).map(p => by.get(p)).filter(e => e && hit(e) && !wk.has(e.p));
  const rk = new Set(rec.map(e => e.p));
  const all = items.filter(e => hit(e) && !wk.has(e.p) && !rk.has(e.p)).sort(ppByName);
  return { chips: chips, work: w, rec: rec, all: all };
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
// cfg: {k, label, items, cur, rkey, chip(e) → html, pick(p), extra (footer html), onExtra()}
function ppChipsHtml(cfg){
  PPC[cfg.k] = cfg;
  const g = ppGroups(cfg.items, tabJson(cfg.rkey, []), cfg.cur, '');
  ppFitSoon();   // callers insert the html themselves; fit after it lands (a morph patch may drop .ppfold)
  // ⚠Fixed shape <b> · <span> · <button>: the structure toolbar is morph-patched by index, so the button keeps its node.
  return '<b>' + esc(cfg.label) + '</b><span class=ppcs>' + g.chips.map(cfg.chip).join('') + '</span>'
    + '<button type=button class="strp ppbtn" data-ppk="' + esc(cfg.k) + '" aria-haspopup=listbox aria-controls=ppop aria-expanded="'
    + (PPS && PPS.cfg.k === cfg.k ? 'true' : 'false') + '">' + esc(T('More ▾')) + '</button>';
}
// Combobox form (Pipelines): one button with the current project's full name; opens the same popover. cfg.badge(e) = trailing html (live dot).
function ppComboHtml(cfg){
  PPC[cfg.k] = cfg;
  const p = cfg.cur || '', e = (cfg.items || []).find(x => x.p === p) || { p: p, name: p.slice(p.lastIndexOf('/') + 1) || p };
  return '<b>' + esc(cfg.label) + '</b><button type=button class="strp ppbtn ppcombo" data-ppk="' + esc(cfg.k) + '" aria-haspopup=listbox aria-controls=ppop aria-expanded="'
    + (PPS && PPS.cfg.k === cfg.k ? 'true' : 'false') + '" title="' + esc(p) + '"><span class=ppcn>' + esc(p ? e.name || p : T('Pick a project')) + '</span>'
    + (p && cfg.badge ? cfg.badge(e) : '') + ' ▾</button>';
}
// Pure: chip widths ws, flex gap, row width avail, index of the selection → indices to fold, nearest-to-selection first.
//   ⚠The selection renders last (stable order), so a narrow row clipped exactly it; folded chips stay in «More».
function ppFitHide(ws, gap, avail, on){
  const out = [];
  if(on < 0) return out;
  let tot = ws.reduce((a, w) => a + w, 0) + gap * Math.max(0, ws.length - 1);
  for(let i = ws.length - 1; i >= 0 && tot > avail + 0.5; i--){
    if(i === on) continue;
    out.push(i); tot -= ws[i] + gap;
  }
  return out;
}
let ppFitQ = 0;
function ppFit(){
  ppFitQ = 0;
  document.querySelectorAll('.ppcs').forEach(row => {
    const cs = [...row.children];
    cs.forEach(c => c.classList.remove('ppfold'));
    if(row.scrollWidth <= row.clientWidth + 0.5) return;
    const gap = parseFloat(getComputedStyle(row).columnGap) || 0;
    ppFitHide(cs.map(c => c.getBoundingClientRect().width), gap, row.clientWidth, cs.findIndex(c => c.classList.contains('on')))
      .forEach(i => cs[i].classList.add('ppfold'));
  });
}
function ppFitSoon(){ if(!ppFitQ && typeof requestAnimationFrame === 'function') ppFitQ = requestAnimationFrame(ppFit); }
function ppRowHtml(e, i){
  return '<div class="cmdki' + (i === PPS.i ? ' on' : '') + (e.p === PPS.cfg.cur ? ' ppcur' : '') + '" role=option data-ppi="' + i + '" title="' + esc(e.p) + '">'
    + '<span class=cmdkp>' + esc(e.name || e.p) + '</span>' + (e.run ? '<i class=mvdot></i>' : e.live ? '<i class=ppdot></i>' : '')
    + '<span class=cmdkc>' + esc(e.p) + '</span></div>';
}
function ppListPaint(){
  const l = document.querySelector('#ppop .cmdkl');
  if(!l || !PPS) return;
  const g = ppGroups(PPS.cfg.items, tabJson(PPS.cfg.rkey, []), PPS.cfg.cur, PPS.q);
  PPS.rows = g.work.concat(g.rec, g.all);
  if(PPS.i >= PPS.rows.length) PPS.i = PPS.rows.length - 1;
  let i = 0;
  const grp = (t, a) => a.length ? '<div class=ppg>' + esc(T(t)) + '</div>' + a.map(e => ppRowHtml(e, i++)).join('') : '';
  l.innerHTML = PPS.rows.length ? grp('Working', g.work) + grp('Recent', g.rec) + grp('All', g.all)
    : '<div class=cmdke>' + esc(T('No matching projects')) + '</div>';
  const on = l.querySelector('.cmdki.on');
  // ⚠Scroll the list box only — scrollIntoView could move the page under a fixed popover.
  if(on){ if(on.offsetTop < l.scrollTop) l.scrollTop = on.offsetTop; else if(on.offsetTop + on.offsetHeight > l.scrollTop + l.clientHeight) l.scrollTop = on.offsetTop + on.offsetHeight - l.clientHeight; }
}
function ppBtn(k){ return document.querySelector('[data-ppk="' + k + '"]'); }
function ppClose(focusBack){
  if(!PPS) return;
  const k = PPS.cfg.k; PPS = null;
  popHide('ppop', ppBtn(k), focusBack);   // queried by key: a pipeline repaint may have replaced the opener
}
function ppOpen(cfg, btn){
  if(PPS){ const same = PPS.cfg.k === cfg.k; ppClose(false); if(same) return; }
  const p = popGet('ppop', 'cmdkb ppop');
  p.setAttribute('role', 'dialog'); p.setAttribute('aria-label', T('Find a project'));
  PPS = { cfg: cfg, q: '', i: -1, rows: [] };
  p.innerHTML = '<input type=text data-ppq placeholder="' + esc(T('Find a project')) + '" aria-label="' + esc(T('Find a project')) + '">'
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
  ppRecent(cfg.rkey, e.p);
  cfg.pick(e.p);
  const b = ppBtn(cfg.k);   // a full repaint (pipeline tab) replaces the opener: focus its successor
  if(b && document.activeElement !== b) b.focus({ preventScroll: true });
}
popReg('ppop', '#ppop,[data-ppk]', ppClose);
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
window.addEventListener('resize', () => { ppClose(false); ppFitSoon(); });
