// ── Cell source ──────────────────────────────────────────────────────────────────
// ★2026-09-22: clicking in structure should show the code or a child code list to be worth viewing
// ⇒ the metadata-only panel gained **the code at that point** and **the change (diff)**.
// Syntax highlighting is the existing `hl()`, the table is the **same** `table.sbs.uni` as work history — making a different
// look here would bring back the 2026-09-01 "looks different" complaint as is.
function strProjOf(a){ return (a && a.pk) || (STR && STR.path) || strOn[0] || ''; }
// Find the same function (file, language, name) in snapshot k of that project. ⚠Do not look up by area key —
// the depth of path grouping can differ per snapshot.
function strFnIn(a, f, k){
  const s = (strSnapsOf(a) || [])[k];
  if(!s) return null;
  const ars = s.areas || [];
  for(let i = 0; i < ars.length; i++){
    const fns = ars[i].fns || [];
    for(let j = 0; j < fns.length; j++){
      const y = fns[j];
      if(!y.more && y.file === f.file && y.lang === f.lang && y.name === f.name) return y;
    }
  }
  return null;
}
// Request for «that cell» at snapshot k — carries the line position, line count and origin (git rev · tar/bak time) at that point as is
function strReq(a, f, k){
  const s = (strSnapsOf(a) || [])[k], g = strFnIn(a, f, k);
  if(!s || !g) return null;
  return { p: strProjOf(a), file: g.file || '', line: g.line || 1, lines: g.lines || 1,
           src: s.src || 'cur', rev: s.rev || '', at: s.at || 0, label: s.label || '' };
}
function strSrcKey(q){ return [q.p, q.file, q.line, q.lines, q.src, q.rev, q.at].join('\n'); }
// From cache if present · otherwise request once and return null (redraw on arrival)
function strSrcGet(q){
  const k = strSrcKey(q);
  if(strSrc[k]) return strSrc[k];
  if(strSrcLoad[k]) return null;
  strSrcLoad[k] = 1;
  const done = j => {
    delete strSrcLoad[k];
    const ks = Object.keys(strSrc);
    if(ks.length > STR_SRC_KEEP) ks.slice(0, ks.length - STR_SRC_KEEP).forEach(x => { delete strSrc[x]; });
    strSrc[k] = j;
    if(strPop) strPopPaint();                  // The popup redraws itself independently of the main screen render
    if(mainView === 'struct') paintStruct();
  };
  getJSON('/api/structure/src?path=' + encodeURIComponent(q.p) + '&file=' + encodeURIComponent(q.file)
        + '&line=' + (q.line || 1) + '&lines=' + (q.lines || 1)
        + '&src=' + encodeURIComponent(q.src || 'cur') + '&rev=' + encodeURIComponent(q.rev || '')
        + '&at=' + (q.at || 0))
    .then(j => done((j && j.ok) ? j : { ok: false, msg: (j && j.msg) || 'Could not fetch', vars: j && j.vars }))
    .catch(() => done({ ok: false, msg: 'Could not fetch — check the server' }));
  return null;
}
// Code table — numbers are **real line numbers in the file** (starting at `from`). Table is the same `sbs.uni` as diff.
function strCodeTable(code, lang, from){
  const ls = String(code == null ? '' : code).split(NL);
  return '<table class="sbs uni"><colgroup><col class=cg><col class=cm2><col></colgroup>'
    + ls.map((t, i) => '<tr><td class=xn>' + (from + i) + '</td><td class=xk> </td>'
        + '<td class=xt>' + (hl(t, lang) || ' ') + '</td></tr>').join('') + '</table>';
}
// ★**Same algorithm** as work history's `editRows` (:13135 · a local closure inside that function) —
// strip only common leading/trailing lines and emit the remaining middle as -/+. No LCS (inventing correspondences
// that do not exist is plausible and false). ⚠Do not change only one side — both screens must look the same.
function strEdRows(oldT, newT){
  const A = String(oldT == null ? '' : oldT).split(NL), B = String(newT == null ? '' : newT).split(NL);
  let p = 0;
  while(p < A.length && p < B.length && A[p] === B[p]) p++;
  let q = 0;
  while(q < A.length - p && q < B.length - p && A[A.length-1-q] === B[B.length-1-q]) q++;
  const rows = [];
  const ctx = t => rows.push({ m: ' ', t: t });
  A.slice(0, p).forEach(ctx);
  A.slice(p, A.length - q).forEach(t => rows.push({ m: '-', t: t }));
  B.slice(p, B.length - q).forEach(t => rows.push({ m: '+', t: t }));
  A.slice(A.length - q).forEach(ctx);
  return rows.length > 600 ? rows.slice(0, 600) : rows;      // Cap is also as in `editRows`
}
function strDiffTable(rows, lang){
  let ln0 = 0, rn0 = 0;
  return '<table class="sbs uni"><colgroup><col class=cg><col class=cm2><col></colgroup>'
    + rows.map(r => {
        let cls = '', no = '';
        if(r.m === '+'){ cls = 'xa'; no = ++rn0; }
        else if(r.m === '-'){ cls = 'xd'; no = ++ln0; }
        else { ++ln0; no = ++rn0; }
        return '<tr class="' + cls + '"><td class=xn>' + no + '</td><td class=xk>' + r.m + '</td>'
          + '<td class=xt>' + (hl(r.t, lang) || ' ') + '</td></tr>';
      }).join('') + '</table>';
}
// Two points to compare — B = snapshot where it last changed (`last`), A = the snapshot just before where this cell existed.
// ⚠churn 0 · the first snapshot has no diff. Do not draw an empty table; return the **reason**.
function strDiffPair(a, f){
  const si = strSi(a), B = Math.min(strLastOf(a, f), si);
  if(si <= 0) return { why: T('This is the first point in time — nothing to compare against') };
  if(B <= 0) return { why: T((f.churn || 0) ? 'No change in this range — unchanged since the first point'
                                            : 'Never changed — same as at the first point') };
  let A = -1;
  for(let k = B - 1; k >= 0; k--) if(strFnIn(a, f, k)){ A = k; break; }
  if(A < 0) return { why: T('It was created at that point — there is no earlier version') };
  return { A: A, B: B };
}
function strPanBody(a, f, tab){
  if((tab || strPanTab) === 'diff'){
    const pr = strDiffPair(a, f);
    if(pr.why) return '<div class=strpnl>' + esc(pr.why) + '</div>';
    const qa = strReq(a, f, pr.A), qb = strReq(a, f, pr.B);
    if(!qa || !qb) return '<div class=strpnl>' + esc(T('Could not find the points to compare')) + '</div>';
    const ga = strSrcGet(qa), gb = strSrcGet(qb);
    if(!ga || !gb) return '<div class=strpnl>' + esc(T('Reading the change…')) + '</div>';
    if(!ga.ok || !gb.ok) return '<div class=strpnl>' + esc(TV(ga.ok ? gb : ga)) + '</div>';
    const rows = strEdRows(ga.code, gb.code);
    const del = rows.filter(r => r.m === '-').length, add = rows.filter(r => r.m === '+').length;
    const si = strSi(a);
    return '<div class=strpnh>' + esc(qa.label || '?') + ' → ' + esc(qb.label || '?')
      + ' · <b class=edpl>+' + add + '</b> <b class=edmn>-' + del + '</b>'
      + (pr.B < si ? ' · ' + esc(T('unchanged since then')) : '') + '</div>'
      + ((ga.exact === false || gb.exact === false)
          ? '<div class=strpnw>' + esc(ga.note || gb.note || '') + '</div>' : '')
      + (add + del ? strDiffTable(rows, f.lang) : '<div class=strpnl>' + esc(T('No change in this range')) + '</div>');
  }
  const q = strReq(a, f, strSi(a));
  if(!q) return '<div class=strpnl>' + esc(T('Could not find the code at this point')) + '</div>';
  const g = strSrcGet(q);
  if(!g) return '<div class=strpnl>' + esc(T('Reading the code…')) + '</div>';
  if(!g.ok) return '<div class=strpnl>' + esc(TV({msg: g.msg || '', vars: g.vars})) + '</div>';
  return (g.exact === false ? '<div class=strpnw>' + esc(g.note || '') + '</div>' : '')
    + strCodeTable(g.code, f.lang, g.line || 1)
    + (g.truncated ? ('<div class=strpnh>' + T('Too long — showing the first {n} lines (of {m})').replace('{n}', g.n).replace('{m}', (q.lines || 0)) + '</div>') : '');
}
// ★Code/diff popup — open/close, ✕ and Esc follow the `#dpop` convention. The body reuses `strPanBody` above.
// ⚠Even when the 2.5s poll redraws the main screen, this content is not erased — `#spop` is a sibling **outside** `.wrap`,
// so `paintStruct` cannot touch it. Hence content persists while it is open.
function strPopFind(){
  if(!strPop || !STR) return null;
  const snap = (STR.snaps || [])[strIdx];
  if(!snap) return null;
  let a = null, f = null;
  (snap.areas || []).forEach(x => {
    if(x.key !== strPop.ak) return;
    a = x;
    (x.fns || []).forEach(y => { if(!y.more && strFk(x, y) === strPop.fk) f = y; });
  });
  return (a && f) ? { a: a, f: f } : null;
}
// Real window (window.open). ⚠If blocked, falls back to the overlay `#spop` — do not delete that markup.
let strWin = null;
function strPopDoc(){ return (strWin && !strWin.closed) ? strWin.document : document; }
// One window per target (strWins); each keeps
// its state in win._sp. strPop/strWin point at the active one (set on focus/pointer); a repaint visits every window.
// ⚠Paint code still reads strPop/strWin, so strPopPaint swaps them per window and restores the active pair.
const strWins = {};   // window name -> open code window
function strPopPaint(){
  const cur = strPop, cw = strWin;
  for(const k in strWins){
    const w = strWins[k];
    try{ if(w.closed || !w._sp) continue; strPop = w._sp; strWin = w; strPopPaint1(); }catch(e){ softErr('strpop-paint', e); }
  }
  strPop = cur; strWin = cw;
  let real = false;
  try{ real = !!(cw && !cw.closed && cw._sp); }catch(e){ softErr('strpop-win', e); }
  if(cur && !real) strPopPaint1();   // overlay (popup blocked)
}
// Pure: popup state -> window identity (kind + project + file + line / cell); the same target reopens the same window.
function strPopKey(sp){
  if(sp.text) return ['x', sp.text.key || sp.text.path + '\n' + sp.text.name].join('\n');
  if(sp.tree) return ['t', sp.tree.p, sp.tree.file, sp.tree.line].join('\n');
  if(sp.rel) return ['r', sp.rel.p, sp.rel.file, sp.rel.line].join('\n');
  const pr = sp.pair;
  return ['c', sp.ak, sp.fk, pr ? [pr.p, pr.s, pr.t].join('|') : ''].join('\n');
}
// Pure: key -> stable window name (djb2).
function strWinName(pre, k){
  let h = 5381;
  for(let i = 0; i < k.length; i++) h = ((h * 33) ^ k.charCodeAt(i)) >>> 0;
  return pre + h.toString(36);
}
function strPopPaint1(){
  const D = strPopDoc();
  strSplitHook(D);
  const t = D.getElementById('sptl'), s = D.getElementById('spsub'),
        b = D.getElementById('spbtn'), body = D.getElementById('spbody');
  if(!t || !s || !b || !body || !strPop) return;
  strTreeBrSync();
  if(strPop.text){ strTextPaint(t, s, b, body); return; }
  if(strPop.tree){ strTreePaint(t, s, b, body); return; }
  if(strPop.rel){ strRelPopPaint(t, s, b, body); return; }
  if(strPop.pair){ strPairPaint(t, s, b, body); return; }
  const hit = strPopFind();
  t.textContent = hit ? (hit.f.name || '') : (strPop.name || '');
  if(!hit){
    s.textContent = T('This box does not exist at this point — either not created yet, or over the cap');
    b.innerHTML = ''; body.innerHTML = '';
    return;
  }
  const a = hit.a, f = hit.f, sn = strSnapsOf(a), L = strLastOf(a, f), age = strSi(a) - L;
  s.textContent = (f.file || '') + ' : ' + (f.line || 0) + ' · ' + (f.lang || '')
    + (' · ' + T('{n} lines · {m} edits').replace('{n}', (f.lines || 0)).replace('{m}', (f.churn || 0)))
    + ' · ' + T('last change') + ' ' + (((sn[L] || {}).label) || '?')
    + (age > 0 ? T(' ({n} snapshots ago)').replace('{n}', age) : T('(this point)'));
  const sp = strPop, tab = sp.tab === 'diff' ? 'diff' : 'code';   // per window; strPanTab is only the default
  b.innerHTML = '<button data-spt=code' + (tab === 'diff' ? '' : ' class=on') + '>' + esc(T('Code')) + '</button>'
    + '<button data-spt=diff' + (tab === 'diff' ? ' class=on' : '') + '>' + esc(T('Changed')) + '</button>';
  b.querySelectorAll('button[data-spt]').forEach(x => x.onclick = () => {
    const k = (x.dataset.spt === 'diff') ? 'diff' : 'code';
    if(k === sp.tab) return;
    sp.tab = k; strPopPaint();
  });
  body.innerHTML = strPanBody(a, f, tab);
}
function strPopOpen(ak, fk, name, tab, pair){
  strPop = { ak: ak, fk: fk, name: name || '', pair: pair || null, tab: tab ? (tab === 'diff' ? 'diff' : 'code') : strPanTab };
  strPopShow(name);
}
// Text already fetched by the caller (47b harness: {name, path, text, lang}) → the same code window, read-only, no tabs.
const STR_TEXT_LANG = { python: 'py', js: 'js', ts: 'js', sh: 'sh', ruby: 'rb', json: 'json', md: 'none', c: 'c', cpp: 'c', cs: 'java', php: 'java', proto: 'java', graphql: 'py', rb: 'rb', rust: 'go', svelte: 'js' };
function strTextState(f){
  f = f || {};
  return { key: String(f.key || ''), name: String(f.name || ''), path: String(f.path || ''), text: String(f.text == null ? '' : f.text),
    lang: STR_TEXT_LANG[f.lang] || 'none' };
}
// ⚠Call from the click itself (window.open needs the user gesture); fill it later with strPopTextSet under the same key.
function strPopOpenText(f){
  strPop = { text: strTextState(f) };
  strPopShow(strPop.text.name);
}
// Repaint the window (or blocked-popup overlay) already open for f.key; nothing when the user closed it.
function strPopTextSet(f){
  const q = strTextState(f), nm = strWinName('sidereus_code_', strPopKey({ text: q }));
  const w = strWins[nm];
  let live = false;
  try{ live = !!(w && !w.closed && w._sp); }catch(e){ softErr('strtext-win', e); }
  if(live){ w._sp.text = q; try{ w.document.title = T('Structure') + ' — ' + q.name; }catch(e){ softErr('strtext-title', e); } }
  else if(strPop && strPop.text && strPop.text.key === q.key) strPop.text = q;
  else return;
  strPopPaint();
}
function strTextPaint(t, s, b, body){
  const q = strPop.text;
  t.textContent = q.name;
  s.textContent = (q.path ? q.path + ' · ' : '') + T('read-only');
  b.innerHTML = '';
  body.innerHTML = strCodeTable(q.text, q.lang, 1);
}
// Architecture evidence (84j/84k file:line) → the same popup, current tree only, code tab only (no snapshot series).
// lang = the node's own lang from the server (a .h is cpp or c per file); '' = guess from the extension.
function strPopOpenRel(p, file, line, lines, name, lang){
  strPop = { rel: { p: p || '', file: file || '', line: line || 1, lines: lines || 80, name: name || '', lang: lang || '' } };
  strPopShow(name);
}
function strRelPopPaint(t, s, b, body){
  const q = strPop.rel, rl = strRelLang(q.file, q.lang), lang = rl.hl;
  t.textContent = q.name || String(q.file).split('/').pop();
  s.textContent = q.file + ' : ' + q.line + ' · ' + rl.label + ' · ' + T('current files');
  b.innerHTML = '<button data-spt=code class=on>' + esc(T('Code')) + '</button>'
    + '<button data-spt=full>' + esc(T('Whole file')) + '</button>';
  const fb = b.querySelector('button[data-spt=full]');
  if(fb) fb.onclick = () => strPopOpenTree(q.p, q.file, q.line);
  const g = strSrcGet({ p: q.p, file: q.file, line: q.line, lines: q.lines, src: 'cur', rev: '', at: 0 });
  if(!g){ body.innerHTML = '<div class=strpnl>' + esc(T('Reading the code…')) + '</div>'; return; }
  if(!g.ok){ body.innerHTML = '<div class=strpnl>' + esc(TV({msg: g.msg || '', vars: g.vars})) + '</div>'; return; }
  body.innerHTML = strCodeTable(g.code, lang, g.line || q.line)
    + (g.truncated ? ('<div class=strpnh>' + T('Too long — showing the first {n} lines').replace('{n}', g.n) + '</div>') : '');
}
// Popup window skeleton (#sptl/#spsub/#spbtn/#spbody + the page's styles).
function strPopWrite(w){
  const css = Array.prototype.map.call(document.querySelectorAll('style'), z => z.textContent).join('\n');
  const d = w.document;
  d.open();
  d.write('<!doctype html><meta charset=utf-8><title>' + esc(T('Structure — Sidereus')) + '</title><style>' + css + '</style>'
    + '<body class=spop><div id=spop><div class=dhead>'
    + '<span class=dttl id=sptl></span><span class=dsub id=spsub></span>'
    + '<span class=strpnb id=spbtn></span></div><div class=dbody id=spbody></div></div>');
  d.close();
  strWinTheme(w);
}
// ⚠The CSS keys on html[data-theme]/[data-tone]/[data-ui]; a written popup has a bare <html>, so copy them (and again on setTheme).
function strWinTheme(w){
  try{ const a = document.documentElement.dataset, b = w.document.documentElement.dataset;
    Object.keys(a).forEach(k => { b[k] = a[k]; }); }catch(e){ softErr('strwin-theme', e); }
}
// Same target open -> focus it (a requested tab still applies); else a new window cascading 30px like 35c popOpen.
function strPopShow(name){
  const sp = strPop, nm = strWinName('sidereus_code_', strPopKey(sp));
  for(const k in strWins){ try{ if(strWins[k].closed) delete strWins[k]; }catch(e){ delete strWins[k]; } }
  let w = strWins[nm] || null;
  if(w){
    if(sp.tab) w._sp.tab = sp.tab;
    if(sp.text) w._sp.text = sp.text;   // reopened file: show the fresh text
    strPop = w._sp; strWin = w;
    try{ w.focus(); }catch(e){ softErr('strpop-focus', e); }
    strPopPaint(); return;
  }
  try{ w = window.open('', nm, popFeat(1200, 880, Object.keys(strWins).length % 8) + ',scrollbars=yes,resizable=yes'); }
  catch(e){ w = null; softErr('strpop-open', e); }
  strWin = w;
  if(w){
    strPopWrite(w);
    w._sp = sp; strWins[nm] = w;
    const act = () => { strPop = w._sp; strWin = w; };   // the window being used becomes the active one
    w.addEventListener('focus', act); w.addEventListener('pointerdown', act, true);
    w.addEventListener('keydown', ev => { act(); if(ev.key === 'Escape') w.close(); }, true);   // Esc closes this window only
    w.addEventListener('unload', () => { delete strWins[nm]; if(strWin === w){ strWin = null; strPop = null; } });
    try{ w.document.title = T('Structure') + ' — ' + (name || ''); w.focus(); }catch(e){ softErr('strpop-title', e); }
  }else{
    document.body.classList.add('spop');
    const x = document.getElementById('spx');
    if(x) x.onclick = strPopClose;
  }
  strPopPaint();
}
function strPopClose(){
  strPop = null;
  if(strWin && !strWin.closed){ try{ strWin.close(); }catch(e){} }
  strWin = null;
  document.body.classList.remove('spop');
  // ⚠While the popup is open `.wrap` is hidden and canvas width reads 0 — redraw once on close
  if(mainView === 'struct') paintStruct();
}
// Area cell — **child code list**. Shown along with drilldown (strZoom); clicking an item goes to the popup.
// `file` (from a per-file grey cell) narrows the list to that file.
function strPanList(a, file){
  const rows = (a.fns || []).filter(x => !x.more && (!file || x.file === file)).sort((x, y) => (y.lines || 0) - (x.lines || 0));
  if(!rows.length) return '<div class=strpnl>' + esc(T(file ? "This file's functions are not in the list yet" : 'No boxes to draw in this area')) + '</div>';
  const sn = strSnapsOf(a), fs = strFirstSeen(a.key), all = (STR && STR.snaps) || [];
  // The right side was needlessly wide ⇒ fixed compact columns, and the freed space carries
  // «lines since first seen» (what grew) and «first seen» (what is new). Swatch = that cell's treemap color.
  const hd = '<div class=strflh><s></s><b>' + esc(T('Function')) + '</b><i>' + esc(T('File : line')) + '</i>'
    + '<u class=c1>' + esc(T('Lines')) + '</u><u class=c2>' + esc(T('Edits')) + '</u>'
    + '<u class=c3>' + esc(T('last change')) + '</u>'
    + '<u class=c4 title="' + esc(T('Line change since first seen')) + '">' + esc(T('Δ lines')) + '</u>'
    + '<u class=c5 title="' + esc(T('First snapshot it appears in — may have been hidden by the cap (60) before')) + '">'
    + esc(T('First seen', 'shown')) + '</u></div>';
  return hd + rows.map(f => {
    const k = strFk(a, f), s0 = fs.get(k), d = s0 ? (f.lines || 0) - s0.v : 0;
    const lastL = ((sn[strLastOf(a, f)] || {}).label) || '?';
    const firstL = !s0 ? '?' : (s0.j < 0 ? T('from start')
                                         : (s0.cap ? '≤ ' : '') + ((((all[s0.j] || {}).label)) || '?'));
    const chg = strSi(a) > 0 && strLastOf(a, f) === strSi(a);
    return '<button class=strfl data-sfk="' + esc(k) + '">'
      + '<s style="background:' + strColor(strLevel(a, f)) + '"></s>'
      + '<b title="' + esc(f.name || '') + '">' + esc(f.name || '') + '</b>'
      + '<i title="' + esc((f.file || '') + ' : ' + (f.line || 0)) + '">' + esc((f.file || '') + ' : ' + (f.line || 0)) + '</i>'
      + '<u class=c1>' + U(f.lines || 0, '#lines') + '</u><u class=c2>' + U(f.churn || 0, '#times') + '</u>'
      + '<u class="c3' + (chg ? ' chg' : '') + '" title="' + esc(chg ? T('changed here') : lastL) + '">' + esc(lastL) + '</u>'
      + '<u class="c4' + (d > 0 ? ' edpl' : d < 0 ? ' edmn' : '') + '" title="'
      + esc(s0 ? T('{n} → {m} lines').replace('{n}', s0.v).replace('{m}', (f.lines || 0)) : '') + '">'
      + (d > 0 ? '+' + d : d < 0 ? String(d) : '·') + '</u>'
      + '<u class="c5' + (s0 && s0.cap ? ' weak' : '') + '" title="' + esc(firstL + (s0 && s0.cap
          ? (' ' + T('— the snapshot before was capped; may be older')) : '')) + '">'
      + esc(firstL) + '</u>'
      + '</button>';
  }).join('');
}
// fk → { j, v } — first snapshot (up to the one being viewed) where each function of area `ak` appears, and its line count.
// `j` = -1 when it was there from the area's first snapshot. `cap` = the snapshot before was over the cap, so it may be older.
// ⚠«First seen», not «created»: measured 2026-09-25 sidereus (full) — 123 of 700 «appeared» at one snapshot because of the cap.
function strFirstSeen(ak){
  const m = new Map(), snaps = (STR && STR.snaps) || [];
  let seen = 0, prevMore = 0;
  for(let j = 0; j <= strIdx && j < snaps.length; j++){
    const ar = (snaps[j].areas || []).find(x => x.key === ak);
    const fns = ((ar && ar.fns) || []).filter(y => !y.more);
    if(!fns.length){ prevMore = 0; continue; }
    fns.forEach(y => { const k = strFk(ar, y);
      if(!m.has(k)) m.set(k, { j: seen ? j : -1, v: y.lines || 0, cap: !!(seen && prevMore) }); });
    seen = 1; prevMore = ar.more || 0;
  }
  return m;
}
// ── Source <-> test pairing ──
// Source/test pair: `/api/structure/pair` finds them from the
// current tree, independent of the «include tests» toggle. Clicking a pair opens a split popup (source left, test right).
const strPair = {}, strPairLoad = {};
const STR_PAIR_WHY = { mirror: 'mirrored path', dir: 'same folder', name: 'name rule', ref: 'reference' };
function strPairGet(p, file){
  const k = p + '\n' + file;
  if(strPair[k]) return strPair[k];
  if(strPairLoad[k]) return null;
  strPairLoad[k] = 1;
  const done = j => {
    delete strPairLoad[k];
    const ks = Object.keys(strPair);
    if(ks.length > STR_SRC_KEEP) ks.slice(0, ks.length - STR_SRC_KEEP).forEach(x => { delete strPair[x]; });
    strPair[k] = j;
    if(mainView === 'struct') paintStruct();
  };
  getJSON('/api/structure/pair?path=' + encodeURIComponent(p) + '&file=' + encodeURIComponent(file))
    .then(j => done((j && j.ok) ? j : { ok: false, msg: (j && j.msg) || 'Could not fetch', vars: j && j.vars }))
    .catch(() => done({ ok: false, msg: 'Could not fetch — check the server' }));
  return null;
}
function strPairBox(a, f){
  const p = strProjOf(a), file = f.file || '';
  if(!p || !file) return '';
  const g = strPairGet(p, file);
  let rows;
  if(!g) rows = '<div class=strpnl>' + esc(T('Finding pairs…')) + '</div>';
  else if(!g.ok) rows = '<div class=strpnl>' + esc(TV({msg: g.msg || '', vars: g.vars})) + '</div>';
  else if(!(g.pairs || []).length) rows = '<div class=strpnl>' + esc(T(g.isTest ? 'No source' : 'No tests')) + '</div>';
  else rows = g.pairs.map(x => '<button class=strfl data-ppp="' + esc(p) + '" data-pps="' + esc(g.isTest ? x.file : file)
      + '" data-ppt="' + esc(g.isTest ? file : x.file) + '">'
      + '<b>' + esc(String(x.file).split('/').pop()) + '</b><i>' + esc(x.file) + '</i>'
      // `ref` = only used by that test (not a name/path pair) — shown dimmer so it reads as weaker
      + '<u' + (x.reason === 'ref' ? ' class=weak' : '')
      + (x.uses ? ' title="' + esc(T('Times the test code uses it')) + '"' : '') + '>' + esc(T(STR_PAIR_WHY[x.reason] || x.reason || ''))
      + (x.via ? ' · ' + esc(x.via) : '')
      // ref pairs are ranked by this count (sidereus/structure.py `_struct_pair_match`)
      + (x.uses ? ' · ' + esc(T('{n} uses').replace('{n}', x.uses)) : '') + '</u></button>').join('');
  return '<div class=strpr><div class=strpnh><b>' + esc(T('Source / Tests')) + '</b> · '
    + esc(T(g && g.isTest ? 'Test → source' : 'Source → tests')) + ' · ' + esc(T('Click to view side by side'))
    + ' · ' + esc(T('current files')) + '</div><div class=strprl>' + rows + '</div></div>';
}
// Pure: file + node lang -> {hl: highlighter mode, label: shown lang}; node lang wins over the extension guess.
function strRelLang(file, nl){
  return { hl: (nl && STR_TEXT_LANG[nl]) || strPairLang(file), label: nl || strPairLang(file) };
}
function strPairLang(file){
  const e = String(file || '').split('.').pop().toLowerCase();
  return (e === 'py') ? 'py' : (e === 'java' || e === 'kt') ? 'java'
    : (e === 'jsp' || e === 'jspf' || e === 'tag') ? 'jsp' : (e === 'go' || e === 'rs') ? 'go' : (e === 'rb') ? 'rb'
    : /^(c|h|cc|cpp|cxx|hpp|hh|hxx|inl)$/.test(e) ? 'c' : (e === 'cs' || e === 'php' || e === 'proto') ? 'java'
    : /^(graphql|graphqls|gql)$/.test(e) ? 'py' : 'js';   // cs/php/proto -> java (C-style comments) · GraphQL -> py (# and """) · rs -> go (LKW.go carries Rust keywords) · vue/svelte -> js
}
// One column of the split popup — the whole current file (server caps at STRUCT_SRC_MAX_LINES).
function strPairCol(p, file, role){
  const head = '<div class=strpnh><b>' + esc(T(role)) + '</b> · ' + esc(file) + '</div>';
  if(!file) return '<div>' + head + '<div class=strpnl>' + esc(T(role === 'Tests' ? 'No tests' : 'No source')) + '</div></div>';
  const g = strSrcGet({ p: p, file: file, line: 1, lines: 100000, src: 'cur', rev: '', at: 0 });
  if(!g) return '<div>' + head + '<div class=strpnl>' + esc(T('Reading the code…')) + '</div></div>';
  if(!g.ok) return '<div>' + head + '<div class=strpnl>' + esc(TV({msg: g.msg || '', vars: g.vars})) + '</div></div>';
  return '<div>' + head + strCodeTable(g.code, strPairLang(file), 1)
    + (g.truncated ? ('<div class=strpnh>' + T('Too long — showing the first {n} lines (of {m})').replace('{n}', g.n).replace('{m}', (g.total || 0)) + '</div>') : '')
    + '</div>';
}
function strPairPaint(t, s, b, body){
  const q = strPop.pair;
  t.textContent = String(q.s || '').split('/').pop() + ' ↔ ' + String(q.t || '').split('/').pop();
  s.textContent = T('Source / Tests') + ' · ' + T('current files');
  b.innerHTML = '';
  body.innerHTML = '<div class=strsp' + strSplitStyle('strsp') + '>' + strPairCol(q.p, q.s, 'Source') + strPairCol(q.p, q.t, 'Tests') + strSplitGrip('strsp') + '</div>';
}
let strPnOpen = lsGet('sidereus.strpnl', '0') === '1';   // area list unfolded (drill-down panel)
function strPanel(snap){
  if(!strPan) return '';
  let a = null, f = null;
  (snap.areas || []).forEach(x => {
    if(x.key !== strPan.ak) return;
    a = x;
    if(!strPan.list) (x.fns || []).forEach(y => { if(!y.more && strFk(x, y) === strPan.fk) f = y; });
  });
  const top = '<span class=strpx id=strpx title="' + esc(T('Close')) + '">✕</span><b class=strpnn>'
    + esc((f && f.name) || strPan.name || '') + '</b>';
  // (1) Area cell — child code list (by line count, descending). Clicking continues to the code view in (2)
  // ⚠The open list takes 3/5 of the height (75-structure.css) — the map fell 499 -> 188px on a drill-down, cells lost
  //   their labels. ⇒ folded to one line by default; «Show list» splits again (kept per browser).
  const fold = '<button type=button class="wkrgb strpnt" id=strpnt aria-expanded=' + strPnOpen + '>'
    + esc(T(strPnOpen ? 'Hide list' : 'Show list')) + '</button>';
  if(strPan.list) return '<div class="strpn strpnL' + (strPnOpen ? '' : ' strpnC') + '">' + top + fold
    + (a ? '<u>' + T('{n} lines · <em>{m}</em> functions').replace('{n}', (a.lines || 0).toLocaleString()).replace('{m}', a.n || 0)
           + (a.more ? ' · ' + T('{n} over the cap are not listed').replace('{n}', a.more) : '') + '</u>'
         : '<u>' + esc(T('This area does not exist at this point')) + '</u>')
    + '<div class=strpnh>' + esc(T("By line count, descending · click to see that function's code")) + '</div>'
    + '<div class=strpnc>' + (a ? strPanList(a, strPan.file) : '') + '</div></div>';
  const vals = strSeries(strPan.ak, strPan.fk);
  if(!f) return '<div class=strpn>' + top
    + '<u>' + esc(T('This box does not exist at this point — either not created yet, or over the cap')) + '</u>'
    + strSpark(vals, strIdx) + '</div>';
  const sn = strSnapsOf(a), L = strLastOf(a, f), age = strSi(a) - L;
  return '<div class=strpn>' + top
    + '<u><em>' + esc(f.file || '') + '</em> : ' + (f.line || 0) + ' · ' + esc(f.lang || '')
    + (' · ' + T('<em>{n}</em> lines · <em>{m}</em> edits').replace('{n}', (f.lines || 0)).replace('{m}', (f.churn || 0)))
    + ' · ' + esc(T('last change')) + ' <em>' + esc(((sn[L] || {}).label) || '?') + '</em>'
    + (age > 0 ? T(' ({n} snapshots ago)').replace('{n}', age) : esc(T('(this point)'))) + '</u>'
    + strSpark(vals, strIdx)
    // ★Bodies do not go here — they go to the popup (2026-09-22: the screen is already narrow).
    + '<div class=strpnb>'
    + '<button data-sop=code>' + esc(T('View code')) + '</button>'
    + '<button data-sop=diff>' + esc(T('View change')) + '</button>'
    + ('<span class=strpnm>' + T('Lines per snapshot · {n} points').replace('{n}', vals.length) + '</span></div>')
    + strPairBox(a, f) + '</div>';
}
// Branch badge -> Branches tab on this repo (view only; ⚠a path outside brRepos() would 400, so keep the current pick then).
function strBrWire(){
  const bb = document.getElementById('strbr');
  if(bb) bb.onclick = () => strBrGo(strOn[0] || (STR && STR.path) || '');
}
function strBrGo(p){
  const n = brNorm(p), pick = brRepos().find(q => brNorm(q) === n);
  if(pick && pick !== brRepo){ brRepo = pick; BR = null; brSel = ''; brDet = null; tabSet('mbBrRepo', pick); }
  if(brBoardOn){ brBoardOn = false; brBoardSave(); }   // ⚠a remembered Board sub-view would hide the jump target (as plOvPick)
  setMainView('br');
}
// Switch the one selected project (toolbar chip or the 08b picker; the picker records recent itself).
function strPickProj(p){
  if(!p || (strOn.length === 1 && strOn[0] === p)) return;
  strOn = [p]; strAuto = 0; tabSet('sidereus.strp', p);
  strStop(); strZoom = ''; strErr = '';
  strRebuild(true); paintStruct(); loadStruct(false);
}
function strWire(){
  const sv = document.getElementById('strsrc');
  if(sv) sv.onclick = () => strPopOpenTree(strOn[0] || (STR && STR.path) || '');
  strBrWire();
  const rf = document.getElementById('strrf');
  if(rf) rf.onclick = () => { strStop(); strOn.forEach(p => { delete strCache[strCk(p)]; });
                              STR = null; strErr = '';
                              paintStruct(); loadStruct(true); };
  // "Include tests" — the cache key changes, so each toggle **calls the server again** (cache if already fetched)
  // Color axis — no server call. It only reads the same response with different colors.
  // «Size» — view switch only (Architecture uses data-ma, wired in 84j); each mode fetches its own data on paint.
  document.querySelectorAll('#strmd button[data-md]').forEach(b => b.onclick = () => {
    if(strMode === 'size') return;
    const hadF = document.activeElement === b;   // ⚠the repaint drops focus to <body>; keep a keyboard toggle on the new button
    strStop(); strMode = 'size';
    tabSet('sidereus.strmd', 'size');
    paintStruct();
    if(hadF) kbHold('#strmd button[data-md]');
  });
  const ax = document.getElementById('strax');
  if(ax) ax.onchange = () => {
    strAxis = (ax.value === 'churn') ? 'churn' : 'recent';
    lsSet('mbStrAxis', strAxis);
    paintStruct();
  };
  const px = document.getElementById('strpx');
  if(px) px.onclick = () => { strPan = null; paintStruct(); };
  const pt = document.getElementById('strpnt');
  if(pt) pt.onclick = () => { strPnOpen = !strPnOpen; lsSet('sidereus.strpnl', strPnOpen ? '1' : '0'); paintStruct(); };
  // Code view / diff view — opens a **popup** (stacking in the panel narrows the treemap)
  document.querySelectorAll('#feed .strpnb button[data-sop]').forEach(b => b.onclick = () => {
    if(!strPan || !strPan.fk) return;
    strPopOpen(strPan.ak, strPan.fk, strPan.name, b.dataset.sop);
  });
  // Area-list item → that function's code popup. ★This is the core of making it worth viewing (2026-09-22)
  document.querySelectorAll('#feed .strfl[data-sfk]').forEach(b => b.onclick = () => {
    if(!strPan) return;
    strPopOpen(strPan.ak, b.dataset.sfk || '', b.querySelector('b') ? b.querySelector('b').textContent : '', 'code');
  });
  // Source/test pair → split popup (source left, test right)
  document.querySelectorAll('#feed .strfl[data-ppt]').forEach(b => b.onclick = () => {
    if(!strPan) return;
    const pr = { p: b.dataset.ppp || strProjOf(null), s: b.dataset.pps || '', t: b.dataset.ppt || '' };
    const k = pr.s.split('/').pop() + ' ↔ ' + pr.t.split('/').pop();
    strPopOpen(strPan.ak, strPan.fk, k, 'code', pr);
  });
  const tc = document.getElementById('strtf');
  if(tc) tc.onchange = () => {
    strStop(); strTests = Math.max(0, Math.min(2, +tc.value | 0)); strZoom = ''; strErr = '';
    lsSet('mbStrTests', String(strTests));
    strRebuild(true); paintStruct(); loadStruct(false);
  };
  const rg = document.getElementById('strrg');
  if(rg) rg.oninput = () => { strStop(); strGo(+rg.value); };
  const pl = document.getElementById('strpl');
  if(pl) pl.onclick = strToggle;
  const cv = document.getElementById('strcv');
  if(cv){
    cv.onmousemove = strMove;
    cv.onmouseleave = () => { const t = document.getElementById('strtip'); if(t) t.style.display = 'none'; };
    cv.onclick = strClick;
    strWatch(cv.parentNode);
    strDraw();
  }
}
// Redraw on canvas cell size changes (window size, side panel collapse, tab switch).
// ⚠Each `innerHTML` swap removes old elements, so **re-attach every time** and disconnect the old observer.
// ⚠Resize fires dozens of times per second — coalesce into one `requestAnimationFrame` and skip if size is unchanged.
function strWatch(el){
  if(strRO){ try{ strRO.disconnect(); }catch(e){} strRO = null; }
  if(!el || typeof ResizeObserver === 'undefined') return;
  strRO = new ResizeObserver(() => {
    if(strRaf) return;
    strRaf = requestAnimationFrame(() => {
      strRaf = 0;
      if(mainView !== 'struct') return;
      const b = document.querySelector('#feed .strwrap');
      if(!b || (b.clientWidth === strLastW && b.clientHeight === strLastH)) return;
      strDraw();
    });
  });
  try{ strRO.observe(el); }catch(e){}
}
