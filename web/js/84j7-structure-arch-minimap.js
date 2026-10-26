// ── Structure «Architecture» minimap: text-free clone of the cached diagram SVG + viewport rect; click / drag scrolls .archmap ──
// ⚠Cloned once per diagram key and re-attached after each innerHTML repaint: never rebuilt per poll, scroll or hover.
// ⚠.archmm sits outside .archmap (sibling in .archbody): archPanFrom never starts a pan here.
// ⚠Only auto-scroll: first sight of a map identity (overview at 0,0) in archMmFirst; a drill-down click keeps the clicked node where it was (archMmAt), never centres.
const ARCH_MM = { k: '', svg: null, raf: 0, seen: {}, pos: {}, at: null, pad: {} };   // pos: view key -> last .archmap [scrollTop, scrollLeft] · at: clicked node anchor · pad: view key -> .archdg [top, bottom] spacer
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
  return f.length >= 8 ? { id: [f[0], f[6], f[7]].join('|'), all: f[1] === 'all', sel: f[1] === 'all' ? '' : f[2] } : null;
}
// Pure: view key = map identity + focused module ('' = overview); lit / full / fit changes keep the key.
function archMmVk(k){ const m = archMmId(k); return m ? m.id + '\t' + (m.all ? '' : m.sel) : ''; }
// Record the live scroll of a .archmap under its view key (scroll listener below).
function archMmKeep(am){
  const dg = am && am.querySelector ? am.querySelector('.archdg') : null, vk = archMmVk(dg && dg.dataset && dg.dataset.k);
  if(!vk) return;
  if(!(vk in ARCH_MM.pos) && Object.keys(ARCH_MM.pos).length >= 100) ARCH_MM.pos = {};
  ARCH_MM.pos[vk] = [am.scrollTop, am.scrollLeft];
}
// Saved scroll for the view of archKey k, or null. ⚠#feed is shared by every main tab: coming back rebuilds .archmap at 0,0, and archMmFirst never re-centres a seen view.
function archMmPos(k){ const v = ARCH_MM.pos[archMmVk(k)]; return v ? v.slice() : null; }
// Scroll for a paint of view k: carried (old .archmap scroll, null = none) unless there was no map or the view key changed (old key ok),
//   then k's saved entry; no saved entry keeps the carried one. ⚠Same key never swaps: clicks / polls must not move the view.
function archMmPick(carried, ok, k){
  if(carried && ok != null && archMmVk(ok) === archMmVk(k)) return carried;
  return archMmPos(k) || carried;
}
// Pure: first-sight .archmap scroll: horizontally the map centre (bands share one centre axis, so the modules sit there);
//   vertically centred when the map fits below the sticky top, else its top just below it. Clamped to [0, max].
// ⚠Not the vertical centre of a tall map: that clipped the Entry band (top row) out of sight.
function archMmAnchor(view, map){
  const cl = (a, hi) => Math.max(0, Math.min(hi, a)), top = view.top || 0, vh = Math.max(0, view.ch - top);
  const y = map.h <= vh ? map.y + map.h / 2 - top - vh / 2 : map.y - top;
  return { left: Math.round(cl(map.x + map.w / 2 - view.cw / 2, Math.max(0, view.sw - view.cw))), top: Math.round(cl(y, Math.max(0, view.sh - view.ch))) };
}
// Pure: archMmAnchor with left = the hub's centre (hub = {x, w} in content px); no hub = archMmAnchor unchanged.
function archMmHub(view, map, hub){
  const to = archMmAnchor(view, map);
  if(hub && hub.w > 0) to.left = Math.round(Math.max(0, Math.min(Math.max(0, view.sw - view.cw), hub.x + hub.w / 2 - view.cw / 2)));
  return to;
}
// Live .archmap view + diagram svg rect in scroll content px (same frame as archViewRect).
function archMmVM(am, svg){
  const b = am.getBoundingClientRect(), r = svg.getBoundingClientRect(), tp = am.querySelector('.archtop');
  return { view: { sl: am.scrollLeft, st: am.scrollTop, cw: am.clientWidth, ch: am.clientHeight, sw: am.scrollWidth, sh: am.scrollHeight, top: tp ? tp.offsetHeight : 0 },
    map: { x: r.left - b.left - (am.clientLeft || 0) + am.scrollLeft, y: r.top - b.top - (am.clientTop || 0) + am.scrollTop, w: r.width, h: r.height } };
}
// Record where a clicked diagram node sits inside its .archmap (84j archDgClick, before the repaint) for archMmFirst.
function archMmAt(el){
  const am = el && el.closest ? el.closest('.archmap') : null, p = el && el.dataset ? String(el.dataset.p || '') : '';
  if(!am || !/^m\d+$/.test(p) || !el.getBoundingClientRect) { ARCH_MM.at = null; return; }
  const r = el.getBoundingClientRect(), b = am.getBoundingClientRect();
  ARCH_MM.at = { p, x: r.left - b.left, y: r.top - b.top };
}
// Pure: .archmap scroll that puts a node now at (now.x, now.y) back at (was.x, was.y), both relative to the scroller box; left clamped to [0, max].
// Vertically pt / pb = .archdg top / bottom spacer px the scroll needs (a short focus view has no scroll room: the clamp moved the node ★-195px at 900).
function archMmStay(view, now, was){
  const cl = (a, hi) => Math.round(Math.max(0, Math.min(Math.max(0, hi), a))), t = Math.round(view.st + now.y - was.y), my = Math.max(0, view.sh - view.ch);
  return { left: cl(view.sl + now.x - was.x, view.sw - view.cw), top: Math.max(0, t), pt: Math.max(0, -t), pb: Math.max(0, t - my) };
}
// Inline style of the .archdg slot for archKey k (84j archPaint): the spacer archMmFirst set for that view, '' when none.
function archMmPadCss(k){
  const v = ARCH_MM.pad[archMmVk(k)];
  return v ? ' style="padding-top:' + v[0] + 'px;padding-bottom:' + v[1] + 'px"' : '';
}
// First sight of a map identity: anchor it once (archMmAnchor), only on the overview and only if the user has not scrolled (0,0).
// Focus view opened by a diagram click (ARCH_MM.at): the hub goes back to the clicked node's screen position, consumed once.
// ⚠Never centre the hub on a click: centring moved the clicked node from under the pointer (★1100: y 750→491).
// First sight of a focus identity without a click anchor: centre the hub (data-p = hub, 84j data-hub).
// ⚠Marks the overview seen too: returning to it never centres. A zero-size (hidden) layout is not marked and keeps the anchor.
function archMmFirst(am, svg, k, hub){
  const m = archMmId(k);
  if(!am || !svg || !m) return;
  const fk = m.all ? '' : 'f\t' + m.id + '\t' + m.sel, c = fk ? ARCH_MM.at : null;
  if(!c && (fk ? ARCH_MM.seen[fk] : ARCH_MM.seen[m.id])) return;
  const vm = archMmVM(am, svg);
  if(!(vm.map.w > 0) || !(vm.view.cw > 0)) return;
  ARCH_MM.seen[m.id] = 1;
  if(fk){ ARCH_MM.seen[fk] = 1; ARCH_MM.at = null;
    const h = /^m\d+$/.test(hub || '') && svg.querySelector ? svg.querySelector('[data-p="' + hub + '"]') : null, r = h && h.getBoundingClientRect ? h.getBoundingClientRect() : null;
    const b = am.getBoundingClientRect();
    if(c){ if(!h || c.p !== hub) return;
      const dg = svg.closest ? svg.closest('.archdg') : null, vk = archMmVk(k);
      if(dg && dg.style){ dg.style.paddingTop = ''; dg.style.paddingBottom = ''; }   // re-opened view: measure without its old spacer
      delete ARCH_MM.pad[vk];
      const r2 = h.getBoundingClientRect(), b2 = am.getBoundingClientRect(), v2 = archMmVM(am, svg).view;
      const to = archMmStay(v2, { x: r2.left - b2.left, y: r2.top - b2.top }, c);
      if(dg && dg.style && (to.pt || to.pb)){ dg.style.paddingTop = to.pt + 'px'; dg.style.paddingBottom = to.pb + 'px';
        if(Object.keys(ARCH_MM.pad).length >= 100) ARCH_MM.pad = {};
        ARCH_MM.pad[vk] = [to.pt, to.pb]; }   // ⚠kept per view: archPaint re-emits it, else the next repaint drops it and the map jumps
      am.scrollLeft = to.left; am.scrollTop = to.pb && !ARCH_MM.pad[vk] ? to.top - to.pb : to.top; return; }
    const to = archMmHub(vm.view, vm.map, r ? { x: r.left - b.left - (am.clientLeft || 0) + am.scrollLeft, w: r.width } : null);
    am.scrollLeft = to.left; am.scrollTop = to.top; return; }
  if(am.scrollLeft || am.scrollTop) return;
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
  archMmFirst(am, svg, k, slot && slot.dataset && slot.dataset.hub);   // ⚠before the minimap-off return: the first-sight anchor does not depend on the minimap
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
  if(!am || !am.matches || !am.matches('.archtab .archmap')) return;
  archMmKeep(am);   // every event, not per frame: the last position before leaving the tab must be the one kept
  if(ARCH_MM.raf) return;
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
