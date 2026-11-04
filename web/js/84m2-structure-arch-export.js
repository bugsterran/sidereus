// ── Structure «Architecture» «Export HTML» › «Detailed»: one self-contained static HTML of the module map on screen ──
// Computed styles are inlined per element and no stylesheet is copied: the picture depends on ancestor-scoped rules
// (e.g. .archdg[data-fv] hides edge labels) and CSS variables, which a copied stylesheet would lose outside the page.
// ⚠Metadata only (AGENTS.md rule 1): names, labels and counts already drawn; never the .mmdsrc source text or evidence lists.
const ARCH_X_SVG = ['fill', 'fill-opacity', 'fill-rule', 'stroke', 'stroke-width', 'stroke-opacity', 'stroke-dasharray', 'stroke-dashoffset',
  'stroke-linecap', 'stroke-linejoin', 'stroke-miterlimit', 'opacity', 'font-family', 'font-size', 'font-weight', 'font-style',
  'font-variant-numeric', 'text-anchor', 'dominant-baseline', 'text-decoration-line', 'visibility', 'display', 'color',
  'marker-start', 'marker-mid', 'marker-end', 'paint-order', 'vertical-align'];
const ARCH_X_HTML = ['display', 'flex-wrap', 'flex-direction', 'align-items', 'justify-content', 'gap', 'row-gap', 'column-gap', 'white-space',
  'margin-top', 'margin-right', 'margin-bottom', 'margin-left', 'padding-top', 'padding-right', 'padding-bottom', 'padding-left',
  'border-top-width', 'border-right-width', 'border-bottom-width', 'border-left-width', 'border-top-style', 'border-right-style',
  'border-bottom-style', 'border-left-style', 'border-top-color', 'border-right-color', 'border-bottom-color', 'border-left-color',
  'border-radius', 'background-color', 'color', 'opacity', 'visibility', 'vertical-align', 'line-height',
  'font-family', 'font-size', 'font-weight', 'font-style', 'font-variant-numeric'];
// Inherited properties: written only where they differ from the parent, which keeps a large map's file small.
const ARCH_X_INH = new Set(['fill', 'fill-opacity', 'fill-rule', 'stroke', 'stroke-width', 'stroke-opacity', 'stroke-dasharray', 'stroke-dashoffset',
  'stroke-linecap', 'stroke-linejoin', 'stroke-miterlimit', 'font-family', 'font-size', 'font-weight', 'font-style', 'font-variant-numeric',
  'text-anchor', 'dominant-baseline', 'visibility', 'color', 'marker-start', 'marker-mid', 'marker-end', 'paint-order', 'white-space', 'line-height']);
// Walk orig and its deep clone together; each clone element gets the orig's computed allow-listed props as its only style.
function archXInline(o, c, ps){
  if(!o || !c || o.nodeType !== 1 || c.nodeType !== 1) return;
  const svg = o.namespaceURI === 'http://www.w3.org/2000/svg', cs = getComputedStyle(o), snap = {}, out = [];
  (svg ? ARCH_X_SVG : ARCH_X_HTML).forEach(k => {
    const v = cs.getPropertyValue(k); snap[k] = v;
    if(!v || /url\(\s*(?!["']?#)/i.test(v)) return;   // only same-document refs (marker ids)
    if(ARCH_X_INH.has(k) && ps && ps[k] === v) return;
    if(svg && k === 'display' && v !== 'none') return;   // svg layout ignores display except none
    out.push(k + ':' + v);
  });
  c.setAttribute('style', out.join(';'));
  for(let i = 0; i < o.children.length; i++) archXInline(o.children[i], c.children[i], snap);
}
// Pure: sanitise serialised markup — drops script/style/foreignObject elements, on*/data-*/xmlns attributes, any href not '#...',
// any value with a non-local url(); the first <svg> gets width/height = its viewBox (zoom 1x, see 84j8 archZmSize).
function archXClean(s){
  s = String(s || '').replace(/<(script|style|foreignObject)\b[\s\S]*?<\/\1\s*>/gi, '').replace(/<(script|style|foreignObject)\b[^>]*\/?>/gi, '');
  let first = true;
  return s.replace(/<([a-zA-Z][^\s/>]*)((?:\s+[^\s=/>]+(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'>]+))?)*)\s*(\/?)>/g, (m, tag, attrs, sl) => {
    const keep = [];
    let vb = null;
    attrs.replace(/\s+([^\s=/>]+)(?:\s*=\s*("[^"]*"|'[^']*'|[^\s"'>]+))?/g, (x, n, v) => {
      const ln = n.toLowerCase(), raw = v == null ? '' : v.replace(/^["']|["']$/g, '');
      if(/^on/.test(ln) || /^data-/.test(ln) || /^xmlns(:|$)/.test(ln)) return '';
      if(/(^|:)href$/.test(ln) && !/^\s*#/.test(raw)) return '';
      if(/url\(\s*(?!["']?#|&quot;#|&#39;#)/i.test(raw) || /javascript:/i.test(raw)) return '';
      if(ln === 'viewbox') vb = raw.trim().split(/[\s,]+/).map(Number);
      keep.push([n, v]);
      return '';
    });
    if(first && tag.toLowerCase() === 'svg'){
      first = false;
      const ok = vb && vb.length === 4 && vb.every(isFinite);
      const kp = keep.filter(a => !(ok && /^(width|height)$/i.test(a[0])));
      if(ok) kp.push(['width', '"' + vb[2] + '"'], ['height', '"' + vb[3] + '"']);
      return '<' + tag + kp.map(a => ' ' + a[0] + (a[1] == null ? '' : '=' + a[1])).join('') + (sl ? '/' : '') + '>';
    }
    return '<' + tag + keep.map(a => ' ' + a[0] + (a[1] == null ? '' : '=' + a[1])).join('') + (sl ? '/' : '') + '>';
  });
}
// Pure: download file name arch-<base>-<commit7>[-<module id>].html; every part limited to [A-Za-z0-9._-].
function archXName(base, commit, id){
  const sn = (x, n) => String(x || '').replace(/[^A-Za-z0-9._-]+/g, '_').replace(/^[._]+/, '').slice(0, n);
  return 'arch-' + (sn(base, 60) || 'repo') + '-' + (sn(String(commit || '').slice(0, 7), 7) || 'nocommit') + (id ? '-' + (sn(id, 60) || 'module') : '') + '.html';
}
// Pure: the document. leg/svg are archXClean output; title/meta are text and escaped; bg/fg accept colour syntax only.
function archXDoc(o){
  o = o || {};
  const col = (v, d) => /^[#\w\s(),.%-]{1,64}$/.test(String(v || '')) ? String(v) : d;
  return '<!doctype html><html><head><meta charset=utf-8>'
    + '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src data:">'
    + '<title>' + esc(o.title || '') + '</title></head>'
    + '<body style="margin:16px;background:' + esc(col(o.bg, '#ffffff')) + ';color:' + esc(col(o.fg, '#1f2328')) + ';font:13px system-ui,sans-serif">'
    + '<div style="margin:0 0 8px;font-weight:600">' + esc(o.meta || '') + '</div>'
    + (o.leg ? '<div style="margin:0 0 10px">' + o.leg + '</div>' : '') + '<div>' + (o.svg || '') + '</div></body></html>\n';
}
// Background/text colour of the map box; a transparent box takes the nearest painted ancestor.
function archXColors(am){
  let bg = '', e = am;
  while(e && e.nodeType === 1){ const v = getComputedStyle(e).backgroundColor; if(v && !/^(transparent|rgba\(\s*0,\s*0,\s*0,\s*0\s*\))$/.test(v)){ bg = v; break; } e = e.parentElement; }
  return { bg: bg, fg: am ? getComputedStyle(am).color : '' };
}
function archXPart(el){
  const c = el.cloneNode(true);
  archXInline(el, c, null);
  return archXClean(c.outerHTML);
}
// Builds and downloads the HTML; false when no module map is drawn (flow view, loading, another project on screen).
function archXDownload(p){
  const tab = document.querySelector('.archtab'), box = tab && tab.parentElement;
  const s = tab && tab.querySelector('.archdg .mmdv > svg.mmdsvg'), d = p && ARCH.cache[p];
  if(!s || !d || !d.ok || (box && box._arp && box._arp !== p)) return false;
  const leg = tab.querySelector('.archleg'), am = s.closest('.archmap'), r = archRate(d), c7 = String(d.commit || '').slice(0, 7);
  const mods = d.modules || [], sel = ARCH.sel && ARCH.sel.p === p && mods.some(m => m && m.id === ARCH.sel.id) ? ARCH.sel.id : '';
  // ⚠An older-commit map exports too: say how far HEAD moved, so the file never passes for the current code.
  const old = d.stale || (d.head && d.commit && d.commit !== d.head)
    ? (typeof d.behind === 'number' ? TV({msg: d.behind === 1 ? 'HEAD is {n} commit ahead' : 'HEAD is {n} commits ahead', vars: {n: d.behind}}) : T('stale')) : '';
  const base = archBase(p), meta = [base, c7, old, T('Edges verified {n}/{m} ({k}%)').replace('{n}', r.n).replace('{m}', r.m).replace('{k}', r.pct)].filter(Boolean).join(' · ');
  const cl = archXColors(am);
  const html = archXDoc({ title: base + (c7 ? ' · ' + c7 : ''), meta: meta, bg: cl.bg, fg: cl.fg, leg: leg ? archXPart(leg) : '', svg: archXPart(s) });
  const url = URL.createObjectURL(new Blob([html], { type: 'text/html' })), a = document.createElement('a');
  a.href = url; a.download = archXName(base, d.commit, sel); a.style.display = 'none';
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);   // ⚠a synchronous revoke can cancel the download in some browsers
  return true;
}
