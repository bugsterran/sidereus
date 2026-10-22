// ── Review line comments: diff popup gutter «+» → per-session drafts → «Request changes» relay (88c rvRelay) ─────────
//   A diff popup opened from the review drawer carries &rvsid=<sid>; only then do its new-side rows get a «+» button.
//   Drafts live in localStorage sidereus.rvnotes.<sid> (shared by same-origin windows, memory fallback); the drawer in the
//   main window recounts them on the `storage` event and folds them into the fix relay text.
//   ⚠Quoted lines are the session's own diff and leave only inside a human-confirmed relay — never lists/cards/MCP.
const RVN_CAP = 50, RVN_CMAX = 2000;
const RVN_SID = (ISPOP && /^[A-Za-z0-9_-]{6,80}$/.test(WPQ.get('rvsid') || '')) ? WPQ.get('rvsid') : '';
const RVN_MEM = {};   // sid -> list, used when localStorage throws
let RVN_ED = null;    // open editor {id?, repo, p, ln, ln0, ln2, q, c, fresh}
function rvnKey(sid){ return 'sidereus.rvnotes.' + sid; }
function rvnLoad(sid){
  if(!sid) return [];
  let a;
  try{ a = JSON.parse(localStorage.getItem(rvnKey(sid)) || '[]'); }catch(e){ a = RVN_MEM[sid] || []; }
  return Array.isArray(a) ? a.filter(n => n && n.id && n.p && n.ln > 0 && n.c).slice(0, RVN_CAP) : [];
}
function rvnStore(sid, list){
  RVN_MEM[sid] = list.slice(0, RVN_CAP);
  try{
    if(list.length) localStorage.setItem(rvnKey(sid), JSON.stringify(RVN_MEM[sid])); else localStorage.removeItem(rvnKey(sid));
  }catch(e){ softErr('rvnStore', e); }
}
// Drop only the sent ids — comments added while the preview was open stay.
function rvnClear(sid, ids){ rvnStore(sid, rvnLoad(sid).filter(n => ids.indexOf(n.id) < 0)); }
function rvnQuote(s){
  s = String(s == null ? '' : s).replace(/\t/g, '  ').replace(/[ \t]+$/gm, '').replace(/\s+$/, '');
  return s.length > 200 ? s.slice(0, 199) + '…' : s;
}
// Pure: comment block of the «Request changes» body (tests/test_board.py). Sorted by path, then line; stops before `max` chars
//   and says how many were left out. Returns {text, ids (included), dropped}.
// Body text is sent through the mailbox (wire), not UI.
function rvnPack(notes, max){
  const ns = (notes || []).filter(n => n && n.p && n.ln > 0 && String(n.c || '').trim())
    .slice().sort((a, b) => a.p < b.p ? -1 : (a.p > b.p ? 1 : a.ln - b.ln));
  if(!ns.length) return {text: '', ids: [], dropped: 0};
  const ent = ns.map(n => '- ' + n.p + ':' + n.ln + (n.ln2 > n.ln ? '-' + n.ln2 : '')
    + (rvnQuote(n.q) ? rvnQuote(n.q).split('\n').map(l => '\n  > ' + l).join('') : '') + '\n  ' + String(n.c).trim().replace(/\n/g, '\n  '));
  const tail = k => '… 코멘트 ' + k + '개는 길이 제한으로 빠졌습니다 — 나머지는 다음 요청으로';
  const cap = max > 0 ? max : Infinity;
  let k = ent.length;
  const build = m => ['줄 코멘트 ' + m + '건:'].concat(ent.slice(0, m), m < ent.length ? [tail(ent.length - m)] : []).join('\n');
  while(k > 0 && build(k).length > cap) k--;
  if(!k) return {text: '', ids: [], dropped: ns.length};
  return {text: build(k), ids: ns.slice(0, k).map(n => n.id), dropped: ns.length - k};
}
function rvnGut(rvp, n){
  if(!rvp || !RVN_SID || n == null || n === '') return '';
  return '<button type=button class=rvnb tabindex=-1 data-rn="' + (+n) + '" aria-label="' + esc(T('Line comment'))
    + '" title="' + esc(T('Line comment · Shift+click = range')) + '">+</button>';
}
function rvnAttr(rvp){ return rvp && RVN_SID ? ' data-rvp="' + esc(rvp) + '"' : ''; }
function rvnRowText(tr){ const c = tr && tr.querySelector('td.xt:last-child'); return c ? c.textContent : ''; }
// New-side lines a..z of one diff table, joined; stops once past the 200-char quote cap (rvnQuote trims the rest).
function rvnRangeText(tb, a, z){
  const out = [];
  for(let i = a, n = 0; i <= z && n <= 200; i++){
    const b = tb.querySelector('button.rvnb[data-rn="' + i + '"]'); if(!b) continue;
    const t = rvnRowText(b.closest('tr')); out.push(t); n += t.length + 1;
  }
  return out.join('\n');
}
function rvnLoc(n){ return n.p + ':' + n.ln + (n.ln2 > n.ln ? '-' + n.ln2 : ''); }
function rvnView(n, cols){
  return '<tr class=rvnr data-id="' + esc(n.id) + '"><td colspan=' + cols + '><div class=rvnc><div class=rvnh><b>' + esc(rvnLoc(n)) + '</b>'
    + '<button type=button data-rvn=edit>' + esc(T('Edit')) + '</button><button type=button data-rvn=del>' + esc(T('Delete')) + '</button></div>'
    + '<div class=rvnx>' + esc(n.c) + '</div></div></td></tr>';
}
function rvnEditor(ed, cols){
  return '<tr class="rvnr ed"><td colspan=' + cols + '><div class=rvnc><div class=rvnh><b>' + esc(rvnLoc(ed)) + '</b>'
    + '<span class=rvnk>' + esc(T('Ctrl/Cmd+Enter save · Esc cancel')) + '</span></div>'
    + '<textarea class=rvnta rows=3 maxlength=' + RVN_CMAX + ' aria-label="' + esc(T('Line comment')) + '" placeholder="'
    + esc(T('What should change on this line…')) + '"></textarea>'
    + '<div class=rvnf><button type=button data-rvn=save>' + esc(T('Save')) + '</button>'
    + '<button type=button data-rvn=cancel>' + esc(T('Cancel')) + '</button></div></div></td></tr>';
}
// Called at the end of diffShow (35c): banner + comment rows under their (last) line; the open editor survives re-renders.
function rvnPaint(){
  if(!RVN_SID) return;
  const box = document.getElementById('dbody'); if(!box) return;
  const ns = rvnLoad(RVN_SID);
  let bar = box.querySelector('.rvnbar');
  if(!bar){ box.insertAdjacentHTML('afterbegin', '<div class="t rvnbar"></div>'); bar = box.firstElementChild; }
  bar.textContent = T('{n} review comments').replace('{n}', ns.length) + ' — '
    + T('Hover a line and press + · send with «Request changes» in the main window review drawer');
  box.querySelectorAll('tr.rvnr').forEach(r => r.remove());
  box.querySelectorAll('table[data-rvp]').forEach(tb => {
    const p = tb.dataset.rvp, cols = tb.querySelectorAll('col').length || 4, rows = new Map();
    tb.querySelectorAll('button.rvnb').forEach(b => rows.set(+b.dataset.rn, b.closest('tr')));
    const mine = (n) => n.p === p && (!n.repo || !diffRepo || n.repo === diffRepo);
    const ed = RVN_ED && mine(RVN_ED) ? RVN_ED : null;
    // insertAdjacentHTML('afterend') stacks upward, so walk newest-last lists in reverse to keep order.
    ns.filter(mine).reverse().forEach(n => {
      const tr = rows.get(n.ln2 > n.ln ? n.ln2 : n.ln); if(!tr) return;
      tr.insertAdjacentHTML('afterend', ed && ed.id === n.id ? rvnEditor(ed, cols) : rvnView(n, cols));  // nosemgrep -- values escaped with esc()
    });
    if(ed && !ed.id){ const tr = rows.get(ed.ln2 > ed.ln ? ed.ln2 : ed.ln); if(tr) tr.insertAdjacentHTML('afterend', rvnEditor(ed, cols)); }  // nosemgrep -- values escaped with esc()
  });
  const ta = box.querySelector('tr.rvnr.ed textarea');
  if(ta && RVN_ED){
    ta.value = RVN_ED.c || '';   // value, not markup
    if(RVN_ED.fresh){ RVN_ED.fresh = false; ta.focus({preventScroll: true}); }
  }
}
// Undo toast (5s) after a delete — puts the comment back at its old index unless it is already there or the cap is full.
function rvnUndo(n, at){
  const box = document.getElementById('toasts'); if(!box) return;
  const el = document.createElement('div'), b = document.createElement('button');
  el.className = 'toast tnote'; el.textContent = T('Comment deleted') + ' ';
  b.type = 'button'; b.textContent = T('Undo');
  b.onclick = e => {
    e.stopPropagation(); el.remove();
    const ns = rvnLoad(RVN_SID); if(ns.some(x => x.id === n.id) || ns.length >= RVN_CAP) return;
    ns.splice(at < 0 ? ns.length : Math.min(at, ns.length), 0, n); rvnStore(RVN_SID, ns); rvnPaint();
  };
  el.appendChild(b); box.appendChild(el);
  setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 320); }, 5000);
}
function rvnSaveEd(){
  const ed = RVN_ED; if(!ed) return;
  const ta = document.querySelector('#dbody tr.rvnr.ed textarea');
  const c = String(ta ? ta.value : (ed.c || '')).trim().slice(0, RVN_CMAX);
  if(!c){ RVN_ED = null; rvnPaint(); return; }
  const ns = rvnLoad(RVN_SID);
  if(ed.id){ const n = ns.find(x => x.id === ed.id); if(n) n.c = c; }
  else{
    if(ns.length >= RVN_CAP){ note(T('Up to {n} comments').replace('{n}', RVN_CAP)); return; }
    ns.push({id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6), repo: ed.repo || '', p: ed.p,
             ln: ed.ln, ln2: ed.ln2 > ed.ln ? ed.ln2 : 0, q: rvnQuote(ed.q), c, t: Math.floor(Date.now() / 1000)});
  }
  rvnStore(RVN_SID, ns);
  RVN_ED = null; rvnPaint();
}
document.addEventListener('click', e => {
  if(!RVN_SID) return;
  const b = e.target.closest && e.target.closest('#dbody .rvnb, #dbody [data-rvn]'); if(!b) return;
  if(b.classList.contains('rvnb')){
    const tr = b.closest('tr'), tb = b.closest('table[data-rvp]'); if(!tr || !tb) return;
    const ln = +b.dataset.rn, p = tb.dataset.rvp;
    if(e.shiftKey && RVN_ED && !RVN_ED.id && RVN_ED.p === p && ln !== RVN_ED.ln0){   // range from the open editor's first line
      const a = Math.min(RVN_ED.ln0, ln), z = Math.max(RVN_ED.ln0, ln);
      RVN_ED.c = (document.querySelector('#dbody tr.rvnr.ed textarea') || {}).value || RVN_ED.c;
      Object.assign(RVN_ED, {ln: a, ln2: z, q: rvnRangeText(tb, a, z) || RVN_ED.q, fresh: true});
    } else RVN_ED = {repo: diffRepo || '', p, ln, ln0: ln, ln2: 0, q: rvnRowText(tr), c: '', fresh: true};
    rvnPaint(); return;
  }
  const act = b.dataset.rvn, tr = b.closest('tr.rvnr');
  if(act === 'save') return rvnSaveEd();
  if(act === 'cancel'){ RVN_ED = null; rvnPaint(); return; }
  const id = tr && tr.dataset.id, n = rvnLoad(RVN_SID).find(x => x.id === id); if(!n) return;
  if(act === 'edit'){ RVN_ED = Object.assign({}, n, {ln0: n.ln, fresh: true}); rvnPaint(); }
  else if(act === 'del'){
    const all = rvnLoad(RVN_SID), at = all.findIndex(x => x.id === id);
    if(RVN_ED && RVN_ED.id === id) RVN_ED = null;
    rvnStore(RVN_SID, all.filter(x => x.id !== id)); rvnPaint(); rvnUndo(n, at);
  }
});
document.addEventListener('input', e => { if(RVN_ED && e.target.matches && e.target.matches('#dbody .rvnta')) RVN_ED.c = e.target.value; });
// ⚠Capture phase: Esc otherwise reaches 35c's document handler and closes the whole popup window.
document.addEventListener('keydown', e => {
  if(!RVN_SID || !RVN_ED || e.isComposing) return;
  if(e.key === 'Escape'){ e.preventDefault(); e.stopPropagation(); RVN_ED = null; rvnPaint(); return; }
  if(e.key === 'Enter' && (e.ctrlKey || e.metaKey) && e.target.matches && e.target.matches('.rvnta')){
    e.preventDefault(); e.stopPropagation(); rvnSaveEd();
  }
}, true);
// Other windows (popup ↔ main drawer) edited the drafts: repaint whichever view shows that session.
window.addEventListener('storage', e => {
  if(!e.key || e.key.indexOf('sidereus.rvnotes.') !== 0) return;
  if(RVN_SID){ if(e.key === rvnKey(RVN_SID)) rvnPaint(); }
  else if(RV.sid && e.key === rvnKey(RV.sid)) rvPaint();
});
