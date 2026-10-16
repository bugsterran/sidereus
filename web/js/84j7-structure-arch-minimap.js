// ── Structure «Architecture» minimap: text-free clone of the cached diagram SVG + viewport rect; click / drag scrolls .archmap ──
// ⚠Cloned once per diagram key and re-attached after each innerHTML repaint: never rebuilt per poll, scroll or hover.
// ⚠.archmm sits outside .archmap (sibling in .archbody): archPanFrom never starts a pan here.
// ⚠Only auto-scroll: the first overview sync of a map identity at scroll 0,0 (archMmFirst); clicks / expands / lit / polls never centre.
const ARCH_MM = { k: '', svg: null, raf: 0, seen: {} };
// Pref: on unless stored '0' (missing key or a throwing store = on).
function archMmOn(){ try{ return lsGet('sidereus.archmm', '1') !== '0'; }catch(e){ return true; } }
// Pure: slot + icon chip (label in title/aria-label); the clone is attached by archMmSync.
function archMmHtml(on){
  const l = esc(T(on ? 'Hide minimap' : 'Show minimap'));
  return '<div class="archmm' + (on ? '' : ' off') + '" aria-label="' + esc(T('Minimap')) + '"><button type=button class=archmm-tg data-armm aria-pressed='
    + (on ? 'true' : 'false') + ' title="' + l + '" aria-label="' + l + '">' + (on ? '&minus;' : '&#9635;') + '</button></div>';
}
// Pure: view = .archmap {sl, st, cw, ch, sw, sh, top (sticky .archtop height)}, map = svg {x, y, w, h} in scroll content px,
// box = minimap svg {w, h} px (content meet-scaled and centred). r = viewport rect in box px, f = same as map fractions (both clamped),
// to(px, py) = .archmap scroll that centres that box point, clamped to [0, max].
function archMmGeom(view, map, box){
  if(!view || !map || !box || !(map.w > 0) || !(map.h > 0) || !(box.w > 0) || !(box.h > 0)) return null;
  const cl = (a, lo, hi) => Math.max(lo, Math.min(hi, a)), s = Math.min(box.w / map.w, box.h / map.h), W = map.w * s, H = map.h * s;
  const ox = (box.w - W) / 2, oy = (box.h - H) / 2, top = view.top || 0, vw = view.cw, vh = Math.max(0, view.ch - top);
  const vx = view.sl - map.x, vy = view.st + top - map.y;
  const x0 = cl(vx / map.w, 0, 1), y0 = cl(vy / map.h, 0, 1), x1 = cl((vx + vw) / map.w, 0, 1), y1 = cl((vy + vh) / map.h, 0, 1);
  const mx = Math.max(0, (view.sw || 0) - view.cw), my = Math.max(0, (view.sh || 0) - view.ch);
  return { s, w: W, h: H, f: { x: x0, y: y0, w: x1 - x0, h: y1 - y0 }, r: { x: ox + x0 * W, y: oy + y0 * H, w: (x1 - x0) * W, h: (y1 - y0) * H },
    to: (px, py) => ({ left: Math.round(cl(map.x + (px - ox) / s - vw / 2, 0, mx)), top: Math.round(cl(map.y + (py - oy) / s - top - vh / 2, 0, my)) }) };
}
// Pure: map identity from an archKey (commit, module and edge count); null when it does not parse.
// ⚠Not the svg key: that changes with selection / full / lit, and centring on those would move the view on a click.
function archMmId(k){
  const f = String(k || '').split('\t'); if(/^fv/.test(f[0] || '')) f.shift();
  return f.length >= 8 ? { id: [f[0], f[6], f[7]].join('|'), all: f[1] === 'all' } : null;
}
// Pure: first-sight .archmap scroll: map top just below the sticky top; left centred if the map fits, else its left edge. Clamped to [0, max].
// ⚠Not the map centre: on a map taller/wider than the view, centring clips the Entry band (top-left) out of sight.
function archMmAnchor(view, map){
  const cl = (a, hi) => Math.max(0, Math.min(hi, a)), top = view.top || 0;
  const x = map.w <= view.cw ? map.x + map.w / 2 - view.cw / 2 : map.x;
  return { left: Math.round(cl(x, Math.max(0, view.sw - view.cw))), top: Math.round(cl(map.y - top, Math.max(0, view.sh - view.ch))) };
}
// Live .archmap view + diagram svg rect in scroll content px (same frame as archViewRect).
function archMmVM(am, svg){
  const b = am.getBoundingClientRect(), r = svg.getBoundingClientRect(), tp = am.querySelector('.archtop');
  return { view: { sl: am.scrollLeft, st: am.scrollTop, cw: am.clientWidth, ch: am.clientHeight, sw: am.scrollWidth, sh: am.scrollHeight, top: tp ? tp.offsetHeight : 0 },
    map: { x: r.left - b.left - (am.clientLeft || 0) + am.scrollLeft, y: r.top - b.top - (am.clientTop || 0) + am.scrollTop, w: r.width, h: r.height } };
}
// First sight of a map identity: anchor it once (archMmAnchor), only on the overview and only if the user has not scrolled (0,0).
// A focus view or a scrolled scroller marks it seen without moving. A zero-size (hidden) layout is not marked.
function archMmFirst(am, svg, k){
  const m = archMmId(k);
  if(!am || !svg || !m || ARCH_MM.seen[m.id]) return;
  const vm = archMmVM(am, svg);
  if(!(vm.map.w > 0) || !(vm.view.cw > 0)) return;
  ARCH_MM.seen[m.id] = 1;
  if(!m.all || am.scrollLeft || am.scrollTop) return;
  const to = archMmAnchor(vm.view, vm.map);
  am.scrollLeft = to.left; am.scrollTop = to.top;
}
// Copy the lit state onto the clone index by index (text stripping keeps [data-p] / .mmdfe order).
function archMmLit(src, dst){
  if(!src || !dst) return;
  dst.classList.toggle('arlitdim', src.classList.contains('arlitdim'));
  ['[data-p]', '.mmdfe'].forEach(q => { const a = src.querySelectorAll(q);
    dst.querySelectorAll(q).forEach((g, i) => g.classList.toggle('arlit', !!a[i] && a[i].classList.contains('arlit'))); });
}
function archMmClone(svg){
  const c = svg.cloneNode(true);
  c.querySelectorAll('text,title').forEach(n => n.remove());
  c.querySelectorAll('.arn,.arin,.arout,.arh,.arhe,.arflash').forEach(n => n.classList.remove('arn', 'arin', 'arout', 'arh', 'arhe', 'arflash'));
  c.classList.remove('archdim');   // ⚠a clone taken mid-hover would freeze the hover dim
  c.removeAttribute('width'); c.removeAttribute('height'); c.removeAttribute('role'); c.setAttribute('aria-hidden', 'true');
  return c;
}
// Live measures of .archmap and its diagram svg (same frame as 84k archViewRect: minus the sticky .archtop).
function archMmMeasure(am){
  const svg = am && am.querySelector && am.querySelector('.archdg svg'), mm = am && am.closest && am.closest('.archbody'), cs = mm && mm.querySelector('.archmm > svg');
  if(!svg || !cs) return null;
  const c = cs.getBoundingClientRect(), vm = archMmVM(am, svg);
  return { g: archMmGeom(vm.view, vm.map, { w: c.width, h: c.height }), cs, c };
}
// Move the viewport rect (an SVG rect in the clone's viewBox units).
function archMmView(am){
  const m = archMmMeasure(am), g = m && m.g, vp = m && m.cs.querySelector('.archmm-vp');
  if(!g || !vp) return;
  const vb = (m.cs.getAttribute('viewBox') || '0 0 0 0').split(/[\s,]+/).map(Number);
  vp.setAttribute('x', vb[0] + g.f.x * vb[2]); vp.setAttribute('y', vb[1] + g.f.y * vb[3]);
  vp.setAttribute('width', g.f.w * vb[2]); vp.setAttribute('height', g.f.h * vb[3]);
}
// Called from 84j3 archLitNow after every paint / lit change: attach the cached clone, copy lit classes, place the rect.
function archMmSync(slot){
  const am = slot && slot.closest ? slot.closest('.archmap') : null, body = am && am.closest('.archbody'), mm = body && body.querySelector('.archmm');
  const svg = slot && slot.querySelector && slot.querySelector('svg'), k = (slot && slot.dataset && slot.dataset.k) || '';
  archMmFirst(am, svg, k);   // ⚠before the minimap-off return: the first-sight anchor does not depend on the minimap
  if(!mm || mm.classList.contains('off') || !svg) return;
  if(ARCH_MM.k !== k || !ARCH_MM.svg){
    const c = archMmClone(svg), vp = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    vp.setAttribute('class', 'archmm-vp'); c.appendChild(vp);
    ARCH_MM.k = k; ARCH_MM.svg = c;
  }
  if(ARCH_MM.svg.parentNode !== mm) mm.insertBefore(ARCH_MM.svg, mm.firstChild);
  archMmLit(svg, ARCH_MM.svg);
  archMmView(am);
}
// ⚠scroll does not bubble: capture phase, one rect move per frame.
document.addEventListener('scroll', ev => {
  const am = ev.target;
  if(ARCH_MM.raf || !am || !am.matches || !am.matches('.archtab .archmap')) return;
  ARCH_MM.raf = requestAnimationFrame(() => { ARCH_MM.raf = 0; archMmView(am); });
}, true);
// Press / drag on the minimap: centre the map on that point. ⚠A poll repaint swaps .archmap mid-drag: re-query on every move.
function archMmGo(ev){
  const am = document.querySelector('.archtab .archmap'), m = archMmMeasure(am);
  if(!m || !m.g) return;
  const to = m.g.to(ev.clientX - m.c.left, ev.clientY - m.c.top);
  am.scrollLeft = to.left; am.scrollTop = to.top;
}
document.addEventListener('pointerdown', ev => {
  const t = ev.target && ev.target.closest ? ev.target : null, cs = t && ev.button === 0 && strMode === 'arch' ? t.closest('.archtab .archmm > svg') : null;
  if(!cs) return;
  ev.preventDefault();
  archMmGo(ev);
  dragTrack(ev, cs, archMmGo);
});
document.addEventListener('click', ev => {
  const t = ev.target && ev.target.closest ? ev.target : null, b = t && t.closest('.archtab [data-armm]');
  if(!b) return;
  lsSet('sidereus.archmm', archMmOn() ? '0' : '1');
  const hadF = document.activeElement === b, f = document.getElementById ? document.getElementById('feed') : null;   // ⚠the repaint drops focus to <body>
  if(f) f._arsig = '';   // same sig: archPaint would skip the repaint
  paintStruct();
  if(hadF) kbHold('.archtab [data-armm]');
});
