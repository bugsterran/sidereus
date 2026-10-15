// ── Source viewer right pane (81b): code table with folding + markdown views ─────────────────────────────
// Folds are client-side and shape-based (braces or indentation), never a parser. A range [s, e] hides rows s+1..e (0-based).
// ⚠Rows are hidden, never removed — line numbers stay the file's real numbers and deep links still find their row.
const STR_FOLD_BRACE = { java: 1, kt: 1, kts: 1, groovy: 1, gradle: 1, scala: 1, ts: 1, tsx: 1, js: 1, jsx: 1, mjs: 1, cjs: 1,
  go: 1, c: 1, h: 1, cc: 1, cpp: 1, hpp: 1, cs: 1, rs: 1, swift: 1, php: 1, dart: 1, css: 1, scss: 1, less: 1, json: 1 };
const STR_FOLD_INDENT = { py: 1, yaml: 1, yml: 1 };
let strTreeMdv = 'split';        // markdown view: 'src' | 'split' | 'prev' — kept across files
function strFoldKind(file){
  const e = String(file || '').split('/').pop().split('.').pop().toLowerCase();
  return STR_FOLD_BRACE[e] ? 'brace' : (STR_FOLD_INDENT[e] ? 'indent' : '');
}
function strIsMd(file){ return /\.(md|markdown)$/i.test(String(file || '')); }
// text → [[s, e], …] sorted by s, one range per start line (the outermost). Blocks under 3 lines do not fold.
function strFoldRanges(text, kind){
  const src = String(text == null ? '' : text), best = {};
  const put = (s, e) => { if(e - s >= 1 && (best[s] == null || best[s] < e)) best[s] = e; };
  if(kind === 'brace'){
    const st = [];
    let ln = 0, q = '', i = 0;
    const n = src.length;
    for(; i < n; i++){
      const c = src[i];
      if(c === '\n'){ ln++; if(q === "'" || q === '"' || q === '//') q = ''; continue; }
      if(q === '//') continue;
      if(q === '/*'){ if(c === '*' && src[i + 1] === '/'){ q = ''; i++; } continue; }
      if(q){ if(c === '\\') i++; else if(c === q) q = ''; continue; }
      if(c === '/' && src[i + 1] === '/'){ q = '//'; i++; continue; }
      if(c === '/' && src[i + 1] === '*'){ q = '/*'; i++; continue; }
      if(c === '"' || c === "'" || c === '`'){ q = c; continue; }
      if(c === '{' || c === '['){ st.push(ln); continue; }
      if((c === '}' || c === ']') && st.length){ const s = st.pop(); if(ln - s >= 2) put(s, ln - 1); }
    }
  }else if(kind === 'indent'){
    const ls = src.split(NL), st = [];
    let last = -1;
    const ind = t => { let w = 0; for(const ch of t){ if(ch === ' ') w++; else if(ch === '\t') w += 4; else break; } return w; };
    const close = w => { while(st.length && st[st.length - 1].w >= w){ const o = st.pop(); if(last - o.s >= 2) put(o.s, last); } };
    ls.forEach((t, i) => {
      const tt = t.trim();
      if(!tt || tt[0] === '#') return;          // blank and comment-only lines never end a block
      close(ind(t));
      st.push({ w: ind(t), s: i });
      last = i;
    });
    close(-1);
  }
  return Object.keys(best).map(Number).sort((a, b) => a - b).map(s => [s, best[s]]);
}
// Row index → hidden? for the shut starts. A shut range inside a hidden one stays shut.
function strFoldHidden(ranges, shut, n){
  const hid = new Array(n).fill(false);
  (ranges || []).forEach(r => { if(shut && shut.has(r[0])) for(let i = r[0] + 1; i <= r[1] && i < n; i++) hid[i] = true; });
  return hid;
}
// Deep link: unfold every range that hides row `idx` (0-based).
function strFoldReveal(ranges, shut, idx){
  (ranges || []).forEach(r => { if(r[0] < idx && idx <= r[1]) shut.delete(r[0]); });
}
// Code table for the source viewer (fold markers per range start).
function strSrcTable(text, lang, ranges){
  const ls = String(text == null ? '' : text).split(NL), fs = {};
  (ranges || []).forEach(r => { fs[r[0]] = r[1] - r[0]; });
  return '<table class="sbs uni srft"><colgroup><col class=cg><col class=cm2><col></colgroup>'
    + ls.map((t, i) => {
        const h = hl(t, lang) || ' ', f = fs[i];
        return '<tr data-l="' + (i + 1) + '"' + (f ? ' data-fs="' + i + '"' : '') + '><td class=xn>' + (i + 1) + '</td><td class=xk>'
          + (f ? '<span class=srfb title="' + esc(T('Fold/unfold')) + '"></span>' : ' ') + '</td>'
          + '<td class="xt">' + h
          + (f ? '<span class=srfn>… ' + esc(T('{n} lines').replace('{n}', f)) + '</span>' : '') + '</td></tr>';
      }).join('') + '</table>';
}
// Applies q.fold.shut to the rendered rows (class toggles only — no re-render).
function strFoldApply(el){
  const q = strPop && strPop.tree, fo = q && q.fold;
  if(!el || !fo) return;
  const rows = el.querySelectorAll('table.srft tr[data-l]');
  const hid = strFoldHidden(fo.ranges, fo.shut, rows.length);
  for(let i = 0; i < rows.length; i++){
    const r = rows[i];
    r.classList.toggle('srfh', hid[i]);
    if(r.hasAttribute('data-fs')) r.classList.toggle('srfc', fo.shut.has(i));
  }
}
function strFoldAll(el, shut){
  const fo = strPop && strPop.tree && strPop.tree.fold;
  if(!fo) return;
  fo.shut = new Set(shut ? fo.ranges.map(r => r[0]) : []);
  strFoldApply(el);
}
// Markdown body: source | side by side | preview. md(text, 1) escapes first, then whitelists (00-core mdLinks).
function strMdBody(text, codeHtml, mode){
  const pv = '<div class="srmdp bd">' + md(text, 1, mode === 'split') + '</div>';
  if(mode === 'src') return codeHtml;
  if(mode === 'prev') return '<div class=srmd1>' + pv + '</div>';
  return '<div class=srmds' + strSplitStyle('srmds') + '><div class=srmdc>' + codeHtml + '</div>' + pv + strSplitGrip('srmds') + '</div>';
}
// Piecewise-linear map through [[fromTop, toTop], ...] (sorted by fromTop); y outside the pairs clamps to the ends.
function strMdMap(pairs, y){
  if(!pairs.length) return 0;
  if(y <= pairs[0][0]) return pairs[0][1];
  for(let i = 1; i < pairs.length; i++){
    const a = pairs[i - 1], b = pairs[i];
    if(y <= b[0]) return b[0] > a[0] ? a[1] + (b[1] - a[1]) * (y - a[0]) / (b[0] - a[0]) : b[1];
  }
  return pairs[pairs.length - 1][1];
}
// Anchor pairs [srcTop, prevTop]: preview [data-ln] ↔ source row tr[data-l], plus both scroll ends; non-monotonic pairs dropped.
function strMdPairs(sp, pp){
  const top = (x, pane) => x.getBoundingClientRect().top - pane.getBoundingClientRect().top + pane.scrollTop;
  const out = [[0, 0]], end = [sp.scrollHeight - sp.clientHeight, pp.scrollHeight - pp.clientHeight];
  pp.querySelectorAll('.mdln').forEach(x => {
    const r = sp.querySelector('tr[data-l="' + x.getAttribute('data-ln') + '"]');
    if(!r || !r.offsetHeight || !x.getClientRects().length) return;   // folded row or hidden block (markers are 0 tall)
    const p = [top(r, sp), top(x, pp)], l = out[out.length - 1];
    // ⚠Anchors past either pane's max scrollTop are unreachable; kept, they blocked the end pair and preview-bottom stopped the source at ~0.97.
    if(p[0] >= l[0] && p[1] >= l[1] && p[0] < end[0] && p[1] < end[1]) out.push(p);
  });
  const l = out[out.length - 1];
  if(end[0] > l[0] && end[1] >= l[1]) out.push(end);
  if(out.length < 3) return [[0, 0], end];                          // no usable anchors: plain ratio
  return out;
}
// Split panes follow each other by source line.
// ⚠The programmatic scroll fires a scroll event on the other pane next frame — `lock` swallows it, cleared in rAF.
function strMdSync(el, quiet){
  const box = el.querySelector('.srmds');
  if(!box) return;
  const sp = box.querySelector('.srmdc'), pp = box.querySelector('.srmdp');
  if(!sp || !pp) return;
  let lock = quiet ? 'all' : null, raf = 0;                          // quiet: restored scroll positions are not re-synced
  if(quiet) requestAnimationFrame(() => requestAnimationFrame(() => { if(lock === 'all') lock = null; }));
  const go = (from, to, fwd) => {
    if(lock === from || lock === 'all' || raf) return;
    raf = requestAnimationFrame(() => {
      raf = 0;
      if(!from.clientHeight || !to.clientHeight) return;             // split not visible
      let ps = strMdPairs(sp, pp);
      if(!fwd) ps = ps.map(p => [p[1], p[0]]);
      const v = Math.round(strMdMap(ps, from.scrollTop));
      if(Math.abs(to.scrollTop - v) < 1) return;
      lock = to; to.scrollTop = v;
      requestAnimationFrame(() => { if(lock === to) lock = null; });
    });
  };
  sp.addEventListener('scroll', () => go(sp, pp, true), { passive: true });
  pp.addEventListener('scroll', () => go(pp, sp, false), { passive: true });
}
function strMdBtns(){
  return [['src', 'Source'], ['split', 'Side by side'], ['prev', 'Preview']].map(x => '<button data-srb="md:' + x[0] + '"'
    + (strTreeMdv === x[0] ? ' class=on' : '') + '>' + esc(T(x[1], 'code')) + '</button>').join('');
}
// Relative markdown link → project file (null when it leaves the project or is only an anchor).
function strMdRel(from, href){
  const u = String(href || '').split('#')[0].split('?')[0];
  if(!u) return null;
  const parts = (u[0] === '/' ? [] : String(from || '').split('/').slice(0, -1));
  for(const s of u.split('/')){
    if(!s || s === '.') continue;
    if(s === '..'){ if(!parts.length) return null; parts.pop(); } else parts.push(s);
  }
  return parts.join('/') || null;
}
