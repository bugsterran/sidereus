// ── Source viewer: back/forward + toolbar + clicks in the code pane (81b right pane) ────────────────────────────────────
function strSrcDeclLine(text, name){
  if(!/^[A-Za-z_$][\w$]*$/.test(String(name || ''))) return 0;
  const re = new RegExp('\\b(class|interface|enum|record|object|trait|struct|type|def|func|function|const|let|var)\\s+'
    + name.replace(/\$/g, '\\$') + '\\b');
  const i = String(text == null ? '' : text).split(NL).findIndex(t => re.test(t));
  return i + 1;
}
// Back/forward stacks {b: [], f: []} of {file, line}.
function strNavPush(h, cur){
  if(cur && cur.file){
    const t = h.b[h.b.length - 1];
    if(!t || t.file !== cur.file || t.line !== cur.line) h.b.push({ file: cur.file, line: cur.line || 0 });
    if(h.b.length > 50) h.b.shift();
  }
  h.f.length = 0;
}
function strNavMove(h, cur, dir){
  const from = dir < 0 ? h.b : h.f, to = dir < 0 ? h.f : h.b;
  if(!from.length) return null;
  if(cur && cur.file) to.push({ file: cur.file, line: cur.line || 0 });
  return from.pop();
}
function strSrcShow(file, line, find){
  const q = strPop.tree;
  q.file = file; q.line = line || 0; q.find = find || ''; q.cur = 'f:' + file;
  strTreeRevealFile(file);
  strPopPaint();
  const D = strPopDoc(), c = D.querySelector('#spbody .srtc');
  if(c) try{ c.focus({ preventScroll: true }); }catch(e){ softErr('srt-focus2', e); }
}
function strSrcGo(file, line, find){
  const q = strPop && strPop.tree;
  if(!q || !file) return;
  strNavPush(q.nav, { file: q.file, line: q.line });
  strSrcShow(file, line, find);
}
function strSrcMove(dir){
  const q = strPop && strPop.tree;
  if(!q) return;
  const e = strNavMove(q.nav, { file: q.file, line: q.line }, dir);
  if(e) strSrcShow(e.file, e.line, '');
}
// Toolbar (#spbtn): back/forward · folding · markdown mode.
function strSrcBtns(q){
  const bt = (a, lab, on, tip) => '<button data-srb="' + esc(a) + '"' + (on === false ? ' disabled' : '') + (tip ? ' title="' + esc(tip) + '"' : '')
    + '>' + esc(lab) + '</button>';
  let h = bt('nav:-1', '◀', q.nav.b.length > 0, T('Back (Alt+←)')) + bt('nav:1', '▶', q.nav.f.length > 0, T('Forward (Alt+→)'));
  if(!q.file) return h;
  const md1 = strIsMd(q.file);
  if(q.fold && q.fold.file === q.file && q.fold.ranges.length && !(md1 && strTreeMdv === 'prev'))
    h += bt('fold:1', T('Collapse all')) + bt('fold:0', T('Expand all'));
  if(md1) h += strMdBtns();
  return h;
}
function strSrcBtnClick(ev){
  const x = ev.target && ev.target.closest ? ev.target.closest('button[data-srb]') : null, q = strPop && strPop.tree;
  if(!x || !q || x.disabled) return;
  const a = x.getAttribute('data-srb'), D = strPopDoc(), el = D.querySelector('#spbody .srtc');
  if(a === 'nav:-1' || a === 'nav:1'){ strSrcMove(a === 'nav:1' ? 1 : -1); return; }
  if(a === 'fold:1' || a === 'fold:0'){ strFoldAll(el, a === 'fold:1'); return; }
  if(a.indexOf('md:') === 0){ strTreeMdv = a.slice(3); strPopPaint(); }
}
// Clicks inside the right pane; true = handled. ⚠A drag-selection ends in a click too — never navigate on one.
function strSrcClick(ev){
  const q = strPop.tree, t = ev.target, W = t.ownerDocument.defaultView;
  const sel = W && W.getSelection ? String(W.getSelection() || '') : '';
  const fb = t.closest('.srfb');
  if(fb){
    const tr = fb.closest('tr[data-fs]'), s = tr ? +tr.getAttribute('data-fs') : -1;
    if(q.fold && s >= 0){ if(q.fold.shut.has(s)) q.fold.shut.delete(s); else q.fold.shut.add(s); strFoldApply(tr.closest('.srtc')); }
    return true;
  }
  if(sel) return !!t.closest('.srtc');
  const ml = t.closest('a.mdrel');
  if(ml){
    const f = strMdRel(q.file, ml.getAttribute('data-mdrel')), ls = strTreeLs[q.p];
    if(f && ls && ls.ok && ls.files.some(e => e.p === f && !e.sec)) strSrcGo(f, 0, '');
    return true;
  }
  return !!t.closest('.srtc');
}
// R1/R2: image URL for a relative markdown image, '' when it leaves the root, is unlisted, secret or over 5 MB.
function strMdImgSrc(p, from, href, files){
  const f = strMdRel(from, href);
  if(!f) return '';
  const e = (files || []).find(x => x && x.p === f);
  if(!e || e.sec || (+e.bytes || 0) > 5 * 1024 * 1024) return '';
  return '/api/structure/img?path=' + encodeURIComponent(p) + '&file=' + encodeURIComponent(f);
}
// ⚠DOM only (R4: svg through <img>, never inline) — alt is user data, so no HTML string and no T(); a load error restores the span.
function strMdImgs(el, q){
  const files = (strTreeLs[q.p] || {}).files || [];
  el.querySelectorAll('.srmdp span.mdimg[data-mdimg]').forEach(span => {
    const src = strMdImgSrc(q.p, q.file, span.getAttribute('data-mdimg'), files);
    if(!src) return;
    const img = document.createElement('img');
    img.className = 'mdimg1'; img.alt = span.textContent; img.loading = 'lazy';
    img.onerror = () => img.replaceWith(span);
    img.src = src;
    span.replaceWith(img);
  });
}
