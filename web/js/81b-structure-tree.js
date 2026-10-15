// ── Source viewer (structure tab «Source») ─────────────────────────────────────────────────
// Left: the project's file tree (diff popup's dfTree/dfTreeHtml, reused) · right: one file through strCodeTable.
// ⚠Shares #spop with the code/diff popup; the popup may be a child window, so events are delegated on #spbody.
// ⚠Clicks inside .srt stop propagating: 35c's document handlers would otherwise run diffShow() for .dfi/.dfd.
const strTreeLs = {};       // project path → adapted listing
const strTreeLsLoad = {};
const strTreeFc = {};       // project\nfile → adapted file
const strTreeFcLoad = {};
const STR_TREE_FC_KEEP = 12;
let strTreeVis = { paths: [], dirs: [] };   // last render — row index → path, every directory key
const STR_TREE_ST = { A: 'A', R: 'A', M: 'M', D: 'D' };
// Every server field is read here only — adjust this when the endpoint shape changes.
function strTreeAdapt(kind, j){
  const fail = { ok: false, msg: (j && j.msg) || 'Could not fetch', vars: j && j.vars };
  if(kind === 'tree'){
    if(!j || !j.ok) return fail;
    const fs = (Array.isArray(j.files) ? j.files : []).map(e => (typeof e === 'string') ? { p: e, sec: 0, bytes: 0, st: '' }
      : { p: String((e && (e.p || e.path)) || ''), sec: (e && e.sec) ? 1 : 0, bytes: +(e && (e.sz || e.bytes)) || 0,
          st: STR_TREE_ST[e && e.st] || '' });
    const ok = fs.filter(e => e.p), cnt = { A: 0, M: 0, D: 0 };
    ok.forEach(e => { if(e.st) cnt[e.st]++; });
    const sn = (j.stn && typeof j.stn === 'object') ? j.stn : cnt;     // git status «st»: R counts as added
    return { ok: true, files: ok, truncated: !!j.truncated, stn: { A: +sn.A || 0, M: +sn.M || 0, D: +sn.D || 0 } };
  }
  if(!j || !j.ok) return { ok: false, locked: !!(j && j.locked), bin: !!(j && j.bin), gone: !!(j && j.gone), msg: fail.msg, vars: fail.vars };
  const code = (j.code != null) ? j.code : j.text;
  return { ok: true, text: String(code == null ? '' : code), lines: +(j.n || j.lines) || 0, bytes: +j.bytes || 0,
           truncated: !!j.truncated, enc: String(j.enc || ''), masked: +j.masked || 0, note: j.note ? String(j.note) : '' };
}
function strTreeRedraw(){ if(strPop && strPop.tree) strPopPaint(); }
function strTreeGet(p){
  if(strTreeLs[p]) return strTreeLs[p];
  if(strTreeLsLoad[p]) return null;
  strTreeLsLoad[p] = 1;
  const done = g => { delete strTreeLsLoad[p]; strTreeLs[p] = g; strTreeRedraw(); };
  getJSON('/api/structure/tree?path=' + encodeURIComponent(p))
    .then(j => done(strTreeAdapt('tree', j)))
    .catch(() => done({ ok: false, msg: 'Could not fetch — check the server' }));
  return null;
}
function strTreeFile(p, file, line){
  const k = p + '\n' + file;
  if(strTreeFc[k]) return strTreeFc[k];
  if(strTreeFcLoad[k]) return null;
  strTreeFcLoad[k] = 1;
  const done = g => {
    delete strTreeFcLoad[k];
    const ks = Object.keys(strTreeFc);
    if(ks.length >= STR_TREE_FC_KEEP) ks.slice(0, ks.length - STR_TREE_FC_KEEP + 1).forEach(x => { delete strTreeFc[x]; });
    strTreeFc[k] = g; strTreeRedraw();
  };
  getJSON('/api/structure/file?path=' + encodeURIComponent(p) + '&file=' + encodeURIComponent(file) + '&line=' + (line || 1))
    .then(j => done(strTreeAdapt('file', j)))
    .catch(() => done({ ok: false, msg: 'Could not fetch — check the server' }));
  return null;
}
function strTreeDirs(node, prefix, out){
  const full = node.label ? (prefix ? prefix + '/' + node.label : node.label) : '';
  if(node.label) out.push(full);
  node.dirs.forEach(c => strTreeDirs(c, full, out));
  return out;
}
// files [{p, sec}] → {html, paths, dirs}. Filter is a case-insensitive path substring; dfTree rebuilds the parents.
// cur = 'f:<path>' | 'd:<dir>' (keyboard cursor) · open = the file on the right. Locked (sec) rows get data-lk, never data-fi.
function strTreeHtml(files, filt, cur, open){
  const q = String(filt || '').trim().toLowerCase(), ent = [], paths = [], sts = [], chd = new Set();
  (files || []).forEach(e => {
    const p = String((e && e.p) || '').replace(/^\/+/, '');
    if(!p || (q && p.toLowerCase().indexOf(q) < 0)) return;
    const i = paths.length; paths.push(p); sts.push(STR_TREE_ST[e.st] || '');
    if(sts[i]){ const ps = p.split('/'); for(let k = 1; k < ps.length; k++) chd.add(ps.slice(0, k).join('/')); }
    ent.push({ i: e.sec ? 'L' + i : i, f: { path: p, isBin: 0, add: 0, del: 0 }, test: 0 });
  });
  if(!ent.length) return { html: '', paths: paths, dirs: [] };
  const root = dfTree(ent), dirs = strTreeDirs(root, '', []);
  const lock = '<svg class=srtlk viewBox="0 0 16 16" aria-hidden=true><rect x=3 y=7 width=10 height=7 rx=1.5 fill=currentColor />'
    + '<path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" fill=none stroke=currentColor stroke-width=1.5 /></svg>';
  // Row parts come through dfTreeHtml's deco hook, so diff-tree markup changes cannot silently break this tree.
  const h = dfTreeHtml(root, 0, '', {
    dir: d => (cur === 'd:' + d ? ' srtcur' : '') + (chd.has(d) ? ' srtdc' : ''),
    file: x => {
      if(typeof x.i === 'string') return { cls: ' dflk', attr: 'data-lk=1', tip: ' — ' + esc(T('File cannot be opened')), fd: lock };
      const p = paths[x.i], st = sts[x.i];
      return { cls: (p === open ? ' on' : '') + (cur === 'f:' + p ? ' srtcur' : '') + (st ? ' srt' + st : ''),
               attr: 'data-fi="' + x.i + '"', tip: st === 'D' ? ' — ' + esc(T('Deleted file')) : '', fd: '' };
    }
  });
  return { html: h, paths: paths, dirs: dirs };
}
function strTreeCode(g, q){
  if(!g) return '<div class=strpnl>' + esc(T('Reading the code…')) + '</div>';
  if(!g.ok) return '<div class=strpnl>' + esc(g.gone ? T('Deleted file') : g.locked ? T('File cannot be opened') : g.bin ? T('Binary file') : TV(g)) + '</div>';
  const enc = (g.enc && g.enc !== 'utf-8') ? g.enc : '';
  const notes = (g.truncated ? '<div class=strpnh>' + esc(T('First 512 KB only')) + '</div>' : '')
    + ((g.note || enc) ? '<div class=strpnh>' + esc(T(g.note || 'Not UTF-8 — shown with a guessed encoding'))
                         + (enc ? ' (' + esc(enc) + ')' : '') + '</div>' : '')
    + (g.masked > 0 ? '<div class=strpnh>' + esc(T('{n} values masked').replace('{n}', g.masked)) + '</div>' : '');
  if(!q.fold || q.fold.file !== q.file) q.fold = { file: q.file, ranges: strFoldRanges(g.text, strFoldKind(q.file)), shut: new Set() };
  if(q.line > 0) strFoldReveal(q.fold.ranges, q.fold.shut, q.line - 1);     // a deep link never lands inside a fold
  const md1 = strIsMd(q.file);
  const tbl = strSrcTable(g.text, md1 ? 'none' : strPairLang(q.file), q.fold.ranges);
  return notes + (md1 ? strMdBody(g.text, tbl, strTreeMdv) : tbl);
}
function strTreeRevealFile(file){
  dfShut.forEach(k => { if(file.indexOf(k + '/') === 0) dfShut.delete(k); });
}
// Pure: is `f` a folder? trailing '/' = yes · a line = no · listed file = no · listed child = yes · list not loaded = last segment has no '.'.
function strTreeIsDir(ls, f, line){
  const b = String(f || '').replace(/\/+$/, '');
  if(!b) return false;
  if(b !== f) return true;
  if(line > 0) return false;
  const fs = ls && ls.ok ? (ls.files || []).map(e => String((e && e.p) || '').replace(/^\/+/, '')) : null;
  if(fs && fs.indexOf(b) >= 0) return false;
  if(fs && fs.some(x => x.indexOf(b + '/') === 0)) return true;
  return b.slice(b.lastIndexOf('/') + 1).indexOf('.') < 0;
}
function strPopOpenTree(p, file, line){
  if(!p) return;
  let f = String(file || '').replace(/^\/+/, ''), dir = '';
  if(strTreeIsDir(strTreeLs[p], f, line || 0)){ dir = f.replace(/\/+$/, ''); f = ''; }   // folder: unfold it, no file on the right
  strPop = { tree: { p: p, file: f, line: f ? line || 0 : 0, filt: '', cur: f ? 'f:' + f : dir ? 'd:' + dir : '', fresh: 1, dir: dir,
                     find: '', nav: { b: [], f: [] }, fold: null } };
  if(f) strTreeRevealFile(f);
  if(dir) strTreeRevealFile(dir + '/x');
  strPopShow(T('Source', 'code') + ' — ' + strShort(p));
}
function strTreePaintList(body){
  const q = strPop.tree, el = body.querySelector('.srtt');
  if(!el) return;
  const ls = strTreeGet(q.p);
  if(!ls){ el.innerHTML = '<div class=strpnl>' + esc(T('Reading the file list…')) + '</div>'; return; }
  if(!ls.ok){ el.innerHTML = '<div class=strpnl>' + esc(TV({msg: ls.msg || '', vars: ls.vars})) + '</div>'; return; }
  const lg = body.querySelector('.srtlg'), sn = ls.stn || { A: 0, M: 0, D: 0 };
  if(lg) lg.innerHTML = (sn.A + sn.M + sn.D) ? '<b class=srtA>' + esc(T('{n} added').replace('{n}', sn.A)) + '</b> · <b class=srtM>'
    + esc(T('{n} modified').replace('{n}', sn.M)) + '</b> · <b class=srtD>' + esc(T('{n} deleted').replace('{n}', sn.D)) + '</b>' : '';
  // ★Large repos start folded — 20000 rows of HTML at once stalls the child window.
  if(q.fresh){ q.fresh = 0; if(ls.files.length > 1500 && !q.file){ strTreeHtml(ls.files, '', '', '').dirs.forEach(d => dfShut.add(d)); if(q.dir) strTreeRevealFile(q.dir + '/x'); } }
  const r = strTreeHtml(ls.files, q.filt, q.cur, q.file), top = el.scrollTop;
  strTreeVis = { paths: r.paths, dirs: r.dirs };
  el.innerHTML = r.html ? r.html : '<div class=strpnl>' + esc(T(q.filt ? 'No matching file' : 'No files')) + '</div>';
  if(ls.truncated) el.insertAdjacentHTML('beforeend', '<div class=strpnh>' + esc(T('Too many files — showing part of the list')) + '</div>');
  el.scrollTop = top;
  const c = el.querySelector('.srtcur');
  if(c && c.scrollIntoView) c.scrollIntoView({ block: 'nearest' });
}
function strTreePaintCode(body){
  const q = strPop.tree, el = body.querySelector('.srtc');
  if(!el) return;
  if(!q.file){ el.innerHTML = '<div class=strpnl>' + esc(T('Pick a file on the left · ↑↓ move · Enter open · ←→ fold')) + '</div>';
               el.dataset.k = ''; return; }
  const ls = strTreeLs[q.p], del = !!(ls && ls.ok && ls.files.some(e => e.p === q.file && e.st === 'D'));
  const g = del ? { ok: false, gone: true } : strTreeFile(q.p, q.file, q.line);     // deleted: never fetched
  if(g && g.ok && q.find){ q.line = strSrcDeclLine(g.text, q.find) || q.line; q.find = ''; }
  const k = q.p + '\n' + q.file + '\n' + q.line + '\n' + (g ? (g.ok ? 1 : 2) : 0);
  const k2 = strIsMd(q.file) ? strTreeMdv : '';
  if(el.dataset.k === k && el.dataset.k2 === k2) return;    // same file already shown — keep the reader's scroll
  const keep = el.dataset.k === k ? Array.prototype.map.call(el.querySelectorAll('.srmdc,.srmdp'), x => x.scrollTop) : null;
  const top = el.scrollTop;
  el.dataset.k = k; el.dataset.k2 = k2;
  el.innerHTML = strTreeCode(g, q);
  strMdImgs(el, q);
  strFoldApply(el);
  const tr = (g && g.ok && q.line > 0) ? el.querySelector('table.srft tr[data-l="' + q.line + '"]') : null;
  if(tr) tr.classList.add('srtln');
  if(keep){                                    // only the markdown mode changed
    el.scrollTop = top;
    el.querySelectorAll('.srmdc,.srmdp').forEach((x, i) => { if(keep[i] != null) x.scrollTop = keep[i]; });
    strMdSync(el, true);
    return;
  }
  strMdSync(el);
  el.scrollTop = 0;
  if(tr && tr.scrollIntoView) tr.scrollIntoView({ block: 'center' });
}
function strTreePaint(t, s, b, body){
  const q = strPop.tree, g = q.file ? strTreeFc[q.p + '\n' + q.file] : null;
  t.textContent = T('Source', 'code') + ' — ' + strShort(q.p);
  s.textContent = q.file ? q.file + (g && g.ok ? (' · ' + T('{n} lines').replace('{n}', g.lines)) : '') : q.p;
  b.onclick = strSrcBtnClick;
  strTreeWire(body);
  const sk = body.firstElementChild;
  if(!sk || !sk.classList.contains('srt') || sk.dataset.p !== q.p){
    const fb = (v, tip, d) => '<button type=button class=srtfa data-tf=' + v + ' title="' + esc(T(tip)) + '" aria-label="' + esc(T(tip))
      + '"><svg viewBox="0 0 16 16" aria-hidden=true><path d="' + d + '" fill=none stroke=currentColor stroke-width=1.6 /></svg></button>';
    body.innerHTML = '<div class=srt' + strSplitStyle('srt') + ' data-p="' + esc(q.p) + '"><div class=srtl><div class=srth><input class=srtq type=search placeholder="'
      + esc(T('Filter by file name')) + '" value="' + esc(q.filt) + '">'
      + fb(1, 'Expand all folders', 'M4 3l4 4 4-4M4 9l4 4 4-4') + fb(0, 'Collapse all folders', 'M4 7l4-4 4 4M4 13l4-4 4 4') + '</div><div class=srtlg></div><div class=srtt tabindex=0></div></div>'
      + '<div class=srtr><div class=srtc tabindex=-1></div></div>' + strSplitGrip('srt') + '</div>';
    const inp = body.querySelector('.srtq');
    if(inp) try{ inp.focus(); }catch(e){ softErr('srt-focus', e); }
  }
  strTreePaintList(body);
  strTreePaintCode(body);
  b.innerHTML = strSrcBtns(q);     // again: folds are known only after the code paint
}
// Branch badge in the popup header (#spbr, after the title) — same data and markup as the toolbar #strbr.
function strTreeBrHtml(p){ return p ? strBrBadge(strBrInfo(p, SESS, strBrPick(p, SESS, BR, STR_BRF, Date.now(), strBrGet)), 'spbr') : ''; }
function strTreeBrSync(){
  const D = strPopDoc(), t = D.getElementById('sptl'), cur = D.getElementById('spbr');
  const h = (t && strPop && strPop.tree) ? strTreeBrHtml(strPop.tree.p) : '';
  if(h === D._spbrH && !!cur === !!h) return;   // per window document
  D._spbrH = h;
  if(cur) cur.remove();
  if(!h) return;
  t.insertAdjacentHTML('afterend', h);
  const bb = D.getElementById('spbr'), p = strPop.tree.p;
  // ⚠Overlay mode (window.open blocked) covers the page — close it first; a real window stays open.
  if(bb) bb.onclick = () => { if(!(strWin && !strWin.closed)) strPopClose(); strBrGo(p); try{ window.focus(); }catch(e){ softErr('spbr-focus', e); } };
}
function strTreeOpenFile(p){ strSrcGo(p, 0, ''); }
function strTreeToggle(d, want){         // want: 'open' | 'shut' | undefined (flip)
  const shut = dfShut.has(d);
  if(want === 'open' ? !shut : (want === 'shut' ? shut : false)) return;
  if(shut) dfShut.delete(d); else dfShut.add(d);
}
// Tree expand/collapse all: dirs = the listing's dirs (expand: filtered listing only · collapse: every dir). Returns shut.
function strTreeFoldAll(shut, dirs, open){
  (dirs || []).forEach(d => { if(open) shut.delete(d); else shut.add(d); });
  return shut;
}
function strTreeRowKey(row){
  if(row.hasAttribute('data-dir')) return 'd:' + row.getAttribute('data-dir');
  return 'f:' + (strTreeVis.paths[+row.getAttribute('data-fi')] || '');
}
function strTreeKey(ev, body){
  const q = strPop.tree, tree = body.querySelector('.srtt');
  if(!tree) return;
  const inInput = ev.target && ev.target.classList && ev.target.classList.contains('srtq');
  const k = ev.key;
  if(ev.altKey && (k === 'ArrowLeft' || k === 'ArrowRight')){ ev.preventDefault(); ev.stopPropagation(); strSrcMove(k === 'ArrowLeft' ? -1 : 1); return; }
  if(ev.altKey || ev.metaKey || ev.ctrlKey || (ev.target.closest && ev.target.closest('.srtr'))) return;   // ⚠arrows scroll the code pane
  if(k !== 'ArrowUp' && k !== 'ArrowDown' && k !== 'Enter' && (inInput || (k !== 'ArrowLeft' && k !== 'ArrowRight'))) return;
  const rows = Array.prototype.slice.call(tree.querySelectorAll('.dfi[data-fi],.dfd[data-dir]'));
  if(!rows.length) return;
  ev.preventDefault(); ev.stopPropagation();
  let i = rows.findIndex(r => strTreeRowKey(r) === q.cur);
  if(k === 'ArrowUp' || k === 'ArrowDown'){
    i = (i < 0) ? 0 : Math.max(0, Math.min(rows.length - 1, i + (k === 'ArrowDown' ? 1 : -1)));
    q.cur = strTreeRowKey(rows[i]); strTreePaintList(body); return;
  }
  if(i < 0) return;
  const cur = q.cur, isDir = cur.slice(0, 2) === 'd:', key = cur.slice(2);
  if(k === 'Enter'){ if(isDir){ strTreeToggle(key); strTreePaintList(body); } else strTreeOpenFile(key); return; }
  if(isDir){ strTreeToggle(key, k === 'ArrowRight' ? 'open' : 'shut'); strTreePaintList(body); return; }
  if(k === 'ArrowLeft'){                 // file → its nearest parent directory row
    let best = '';
    strTreeVis.dirs.forEach(d => { if(key.indexOf(d + '/') === 0 && d.length > best.length) best = d; });
    if(best){ q.cur = 'd:' + best; strTreePaintList(body); }
  }
}
// Bound once per #spbody element (a reopened child window has a new one). Every handler returns unless tree mode is on.
function strTreeWire(body){
  if(body._srtw) return;
  body._srtw = 1;
  const on = () => !!(strPop && strPop.tree);
  body.addEventListener('click', ev => {
    if(!on() || !ev.target.closest || !ev.target.closest('.srt')) return;
    ev.stopPropagation();
    if(strSrcClick(ev)) return;                 // right pane: folds, markdown links (81d)
    const fi = ev.target.closest('.dfi[data-fi]'), dd = ev.target.closest('.dfd[data-dir]');
    const fa = ev.target.closest('.srtfa');
    if(fa){
      const open = fa.getAttribute('data-tf') === '1', ls = strTreeGet(strPop.tree.p);
      if(!ls || !ls.ok) return;
      strTreeFoldAll(dfShut, open ? strTreeVis.dirs : strTreeHtml(ls.files, '', '', '').dirs, open);
      strTreePaintList(body); return;
    }
    if(fi){ const p = strTreeVis.paths[+fi.getAttribute('data-fi')]; if(p) strTreeOpenFile(p); return; }
    if(dd){ const d = dd.getAttribute('data-dir'); strTreeToggle(d); strPop.tree.cur = 'd:' + d; strTreePaintList(body); }
  });
  body.addEventListener('dblclick', ev => { if(on() && ev.target.closest && ev.target.closest('.srt')) ev.stopPropagation(); });
  body.addEventListener('input', ev => {
    if(!on() || !ev.target.classList || !ev.target.classList.contains('srtq')) return;
    strPop.tree.filt = ev.target.value || '';
    if(strPop.tree.filt) dfShut.clear();        // a match hidden under a folded directory reads as «no match»
    strTreePaintList(body);
  });
  body.addEventListener('keydown', ev => { if(on()) strTreeKey(ev, body); });
}
