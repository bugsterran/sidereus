// Pipeline editor «Stage catalog» palette (split from 48d at the 700-line cap): render, name filter, fold state.
// «+ Custom stage» (any title, instruction required) above the «Stage catalog» (GET /api/pipelines `catalog`), one fold per group;
// each item: «Graded» when it brings a gate, a dot when it needs tools (tooltip = install hint), «+ Add». Folds closed by the user stay closed (PLPGRP).
// The «Stage name» box also filters the catalog (PLPQ, kept across repaints): ko/en title or group label, case-insensitive.
let PLPGRP = {}, PLPQ = '';
function plPalHit(hay, q){ q = String(q || '').trim().toLowerCase(); return !q || hay.includes(q); }
function plPalette(E, cat){
  const used = E.G.nodes.map(n => n.title), C = cat || {}, items = C.items || [], q = PLPQ.trim();
  const hay = (t, g) => [t.title.ko, t.title.en, plgShow(t.title.ko), g.en, T(g.en, 'catalog')].join(' ').toLowerCase();
  const hits = items.filter(t => { const g = (C.groups || []).find(x => x.id === t.group); return g && plPalHit(hay(t, g), q); });
  PLG_CAT = {}; items.forEach(t => { PLG_CAT[t.title.ko] = t.group; });
  const dot = t => { const ts = t.tools || [], miss = ts.filter(x => !x.avail); if(!ts.length) return '';
    const tip = miss.length ? T('Not installed') + ':\n' + miss.map(x => x.id + ' — ' + x.install).join('\n') : T('Tools installed');
    return '<i class="plcdot' + (miss.length === ts.length ? ' off' : miss.length ? ' part' : '') + '" title="' + esc(tip + (ts.some(x => x.net) ? '\n' + T('Needs the network') : '')) + '"></i>'; };
  const tip = t => [T('Drag onto the canvas, or press, to add a stage'), t.instr || '', t.gate ? T('Gate') + ': ' + t.gate : '', t.asserts ? T('Checks') + ': ' + t.asserts : '', !t.gate && t.gateHint ? T('Gate idea') + ': ' + t.gateHint : ''].filter(Boolean).join('\n\n');
  return '<div class=plpal><div class=plph>' + esc(T('Custom', 'build')) + '</div><div class=plnt>'
    + '<input data-plnt data-plpq maxlength=24 value="' + esc(PLPQ) + '" placeholder="' + esc(T('Stage name')) + '"><button class="wkrgb' + (q && !hits.length ? ' plhot' : '') + '" data-pladd>' + esc(T('+ Custom stage')) + '</button></div>'
    + '<div class=plpnm' + (q && !hits.length ? '' : ' hidden') + '>' + esc(T('No match — + Custom stage creates "{name}"').replace('{name}', q)) + '</div>'
    + '<div class=plph>' + esc(T('Stage catalog')) + '</div><div class=plfd>' + esc(T('Click + or drag onto the canvas')) + '</div>'
    + (C.groups || []).map(g => {
      // ⚠Items already on the canvas stay listed (hiding them read as «missing»); adding one again makes «<title> 2» (plgAddTpl).
      const ps = items.filter(t => t.group === g.id), n = ps.filter(t => hits.includes(t)).length;
      return !ps.length ? '' : '<details class=plgd data-plgrp="' + esc(g.id) + '"' + (q ? (n ? ' open' : ' hidden') : PLPGRP[g.id] ? '' : ' open') + '><summary class=plgrp>' + esc(T(g.en, 'catalog')) + '</summary>'
        + ps.map(t => { const u = used.includes(t.title.ko);
          return '<div class="plci pf-' + plgFam(t.title.ko) + (u ? ' used' : '') + '" data-plq="' + esc(hay(t, g)) + '"' + (hits.includes(t) ? '' : ' hidden') + '><button type=button class=plpi draggable=true data-pldrag="c:' + esc(t.id) + '" title="' + esc(tip(t)) + '">'
          + esc(plgShow(t.title.ko)) + '</button>' + (t.gate ? '<b class=plcg title="' + esc(T('Graded — brings a gate command')) + '">✓</b>' : '') + dot(t)
          + (u ? '<span class=plcu title="' + esc(T('Already on the canvas — adding it again makes a numbered copy')) + '">' + esc(T('in use')) + '</span>' : '')
          + '<button type=button class=plcadd data-plcadd="' + esc(t.id) + '" aria-label="' + esc(T('+ Add') + ' ' + plgShow(t.title.ko)) + '">' + esc(T('+ Add')) + '</button></div>'; }).join('') + '</details>';
    }).join('')
    + '</div>';
}
document.addEventListener('toggle', e => { const g = e.target && e.target.dataset && e.target.dataset.plgrp; if(g && !PLPQ.trim()) PLPGRP[g] = !e.target.open; }, true);   // ⚠filter opens folds: not the user's choice
// Filter in place on each keystroke (no repaint: focus and caret stay); the same rule as plPalette's render.
function plPalFilter(pal){
  const q = PLPQ.trim(); let all = 0;
  pal.querySelectorAll('.plgd').forEach(d => {
    let n = 0; d.querySelectorAll('.plci').forEach(r => { const h = plPalHit(r.dataset.plq || '', q); r.hidden = !h; n += h ? 1 : 0; });
    all += n; d.hidden = !!q && !n; d.open = q ? n > 0 : !PLPGRP[d.dataset.plgrp];
  });
  const nm = pal.querySelector('.plpnm'), b = pal.querySelector('[data-pladd]');
  if(nm){ nm.hidden = !q || all > 0; nm.textContent = T('No match — + Custom stage creates "{name}"').replace('{name}', q); }
  if(b) b.classList.toggle('plhot', !!q && !all);
}
document.addEventListener('input', e => {
  const i = e.target && e.target.closest && e.target.closest('.plpal [data-plpq]');
  if(!i) return;
  PLPQ = i.value; plPalFilter(i.closest('.plpal'));
});
