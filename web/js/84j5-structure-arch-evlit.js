// ── Structure «Architecture» edge-row highlight: hovering / pinning a «Connections» row lights its edge (or its flow) on the map ──
// ⚠Class-only repaint on hover (no full repaint), and nothing here ever moves the view (no 84k «Next lit» either).
// ⚠Edge and flow names are agent data: esc only, never T(). ARCH is owned by 84j; this file reads it inside functions only.
var ARCH_EVL = null;   // ⚠var, not let: 84j3 archLitQ may read it before this file runs. {p, i} | {p, f} | {p, f, s} = hovered row, never stored in ARCH
const ARCH_OFF = { raf: 0 };
// Pure: flow the edge row belongs to — a lit flow holding the edge first, else the first multi-step flow with the same from → to step.
function archEvFlow(d, i, lit){
  const e = ((d && d.edges) || [])[i], fls = (d && Array.isArray(d.flows) ? d.flows : []).filter(f => f && f.id != null && Array.isArray(f.steps));
  if(!e) return null;
  const has = f => f.steps.some(s => s && s.from === e.from && s.to === e.to);
  const ls = (lit || []).filter(x => x != null).map(String), l = fls.find(f => ls.indexOf(String(f.id)) >= 0 && has(f));
  if(l) return String(l.id);
  const f = fls.find(y => y.steps.length >= 2 && has(y));
  return f ? String(f.id) : null;
}
// Pure: null when rect r overlaps the visible rect v; else {side, x, y} — anchor on that side of v, the other axis clamped inside v.
function archOffPos(r, v){
  if(!r || !v || !(r.right <= v.left || r.left >= v.right || r.bottom <= v.top || r.top >= v.bottom)) return null;
  const M = 40, cl = (a, lo, hi) => Math.max(lo, Math.min(hi, a));
  const x = cl((r.left + r.right) / 2, v.left + M, v.right - M), y = cl((r.top + r.bottom) / 2, v.top + M / 2, v.bottom - M / 2);
  if(r.right <= v.left) return { side: 'l', x: v.left, y };
  if(r.left >= v.right) return { side: 'r', x: v.right, y };
  return r.bottom <= v.top ? { side: 't', x, y: v.top } : { side: 'b', x, y: v.bottom };
}
// Drop a hover that a poll repaint left behind (the row under the pointer is gone or another one).
function archEvlLive(p){
  if(!ARCH_EVL || typeof document === 'undefined' || !document.querySelector) return;
  const bs = document.querySelectorAll ? document.querySelectorAll('.archtab .arche:hover > .archeb') : [], b = bs.length ? bs[bs.length - 1] : document.querySelector('.archtab .arche:hover > .archeb');   // innermost: flow nodes nest step rows (84j6)
  if(ARCH_EVL.p !== p || !b || JSON.stringify(archEvlKey(p, b)) !== JSON.stringify(ARCH_EVL)) ARCH_EVL = null;
}
// Pure: hover key of a row button — {p, i} edge row · {p, f} flow node · {p, f, s} flow step (84j6); null otherwise.
function archEvlKey(p, b){
  const ds = (b && b.dataset) || {}, i = parseInt(ds.ae, 10), f = parseInt(ds.aet, 10), m = /^(\d+)\.(\d+)$/.exec(String(ds.ats || ''));
  return i >= 0 ? { p, i } : f >= 0 ? { p, f } : m ? { p, f: parseInt(m[1], 10), s: parseInt(m[2], 10) } : null;
}
// «Off screen» marker for the row's own edge (.arevk) outside the visible map. ⚠Reads rects and places one absolutely positioned
// element in .archbody (not inside the scroller): the view itself never moves.
function archOffMark(slot){
  const am = slot && slot.closest ? slot.closest('.archmap') : null, body = am && am.closest('.archbody');
  if(!body) return;
  const old = body.querySelector('.archoff');
  const es = am.querySelectorAll('.archdg svg .mmdfe.arevk'), v = typeof archViewRect === 'function' ? archViewRect(am) : null;
  let r = null;
  es.forEach(g => { const b = g.getBoundingClientRect();
    r = r ? { left: Math.min(r.left, b.left), top: Math.min(r.top, b.top), right: Math.max(r.right, b.right), bottom: Math.max(r.bottom, b.bottom) } : b; });
  const at = r && v ? archOffPos(r, v) : null;
  if(!at){ if(old) old.remove(); return; }
  const m = old || document.createElement('div'), o = body.getBoundingClientRect();
  if(!old){ m.setAttribute('aria-hidden', 'true'); body.appendChild(m); }
  m.className = 'archoff ' + at.side;
  m.textContent = { l: '← ', r: '→ ', t: '↑ ', b: '↓ ' }[at.side] + T('Off screen');
  m.style.left = Math.round(at.x - o.left) + 'px'; m.style.top = Math.round(at.y - o.top) + 'px';
}
function archEvlPaint(el){
  const tab = el && el.closest && el.closest('.archtab');
  if(tab && typeof archLitNow === 'function') archLitNow(tab.querySelector('.archdg'));
}
document.addEventListener('pointerover', ev => {
  const t = ev.target && ev.target.closest ? ev.target : null, li = t && t.closest('.archtab .arche'), b = li && li.querySelector(':scope > .archeb');
  if(!b || strMode !== 'arch') return;
  const k = archEvlKey(strOn[0] || '', b);
  if(!k || JSON.stringify(k) === JSON.stringify(ARCH_EVL)) return;
  ARCH_EVL = k; archEvlPaint(li);
});
document.addEventListener('pointerout', ev => {
  const t = ev.target && ev.target.closest ? ev.target : null, li = t && t.closest('.archtab .arche'), r = ev.relatedTarget;
  if(!li || !ARCH_EVL || (r && (li.contains(r) || (r.closest && r.closest('.archtab .arche'))))) return;   // ⚠into another row (or a node's own child): its pointerover takes over, no blink
  ARCH_EVL = null; archEvlPaint(li);
});
// ⚠scroll does not bubble: capture phase, one reposition per frame, only while a marker could show.
document.addEventListener('scroll', ev => {
  const am = ev.target;
  if(ARCH_OFF.raf || !am || !am.matches || !am.matches('.archtab .archmap')) return;
  if(!ARCH_EVL && !ARCH.op) return;
  ARCH_OFF.raf = requestAnimationFrame(() => { ARCH_OFF.raf = 0; archOffMark(am.querySelector('.archdg')); });
}, true);
