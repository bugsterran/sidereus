// ── Structure «Architecture» overview «Connections» tree: one fold per flow (its ordered steps), then «Not on a traced flow» ──
// ⚠Flow / module names are agent data: esc only, never T(). Clicks change classes/state only: the view never moves.
// Pure: {flows: [{n, id, name, mods, steps: [{k, from, to, ei, eis, s}]}], other: {w: Wiring idx, c: Calls idx}}. A step lights ei = the
// first passed edge with the same from → to, else the first with that pair, else -1; every edge with the pair (eis) counts as «in a flow».
function archEdTree(d){
  const es = (d && d.edges) || [], used = new Set();
  const fls = (d && Array.isArray(d.flows) ? d.flows : []).filter(f => f && f.id != null && Array.isArray(f.steps));
  const at = (a, b) => { const m = (e, ok) => e && e.from === a && e.to === b && (!ok || e.ok);
    const i = es.findIndex(e => m(e, true)); return i >= 0 ? i : es.findIndex(e => m(e, false)); };
  const all = (a, b) => es.map((e, i) => e && e.from === a && e.to === b ? i : -1).filter(i => i >= 0);
  const flows = fls.map((f, n) => {
    const steps = f.steps.filter(s => s).map((s, k) => { const ei = at(s.from, s.to), eis = all(s.from, s.to); eis.forEach(i => used.add(i)); return { k, from: s.from, to: s.to, ei, eis, s }; });
    const mods = new Set(); steps.forEach(s => { mods.add(s.from); mods.add(s.to); });
    return { n, id: String(f.id), name: String(f.name || f.id), mods: mods.size, steps };
  });
  const rest = es.map((e, i) => i).filter(i => es[i] && !used.has(i)).sort((a, b) => (es[b].ok ? 1 : 0) - (es[a].ok ? 1 : 0));   // passed first
  const wk = { import: 1, config: 1, di: 1 };
  return { flows, other: { w: rest.filter(i => wk[es[i].kind]), c: rest.filter(i => !wk[es[i].kind]) } };
}
// Pure: highlight query for a flow node (k null) or one step; null when n / k no longer exist (a refetch may drop them).
// ⚠A step lights only its own edge + 2 modules: no archEvFlow widening to the whole flow.
function archEdTreeQ(d, n, k, tests){
  const f = archEdTree(d).flows[n];
  if(!f) return null;
  if(k == null) return { flow: f.id, tests };
  const s = f.steps[k];
  return !s ? null : s.ei >= 0 ? { edge: s.ei, tests } : { mods: [s.from, s.to], tests };
}
// Pure: «Connections» tree html. o = {op: ARCH.op, et: fold state (key p\tn | p\tother | p\tother.w | p\tother.c, true = open), dv, sn}; default folded.
function archEdTreeHtml(d, names, p, o){
  const tr = archEdTree(d), es = (d && d.edges) || [], op = (o && o.op) || '', et = (o && o.et) || {};
  const nm = id => names[id] || String(id || ''), open = k => archOwn(et, p + '\t' + k) && !!et[p + '\t' + k];
  const car = (k, on) => '<i aria-hidden=true' + (k == null ? '' : ' data-aetf="' + k + '"') + '>' + (on ? '▾' : '▸') + '</i>';
  const fl = tr.flows.map(f => { const on = open(f.n), pin = op === p + '\tf' + f.n;
    const lbl = T('({n} modules · {m} steps)').replace('{n}', f.mods).replace('{m}', f.steps.length);
    return '<li class="arche archtn' + (pin ? ' on' : '') + '" role=treeitem><button type=button class="archeb archtnb" data-aet="' + f.n + '" aria-expanded=' + (on ? 'true' : 'false') + '>'
      + car(f.n, on) + '<b>' + esc(f.name) + '</b><small>' + esc(lbl) + '</small></button>'
      + (on ? '<ul class=archetl role=group>' + f.steps.map(s => { const sk = f.n + '.' + s.k, sp = op === p + '\tf' + sk;
        return '<li class="arche' + (sp ? ' on' : '') + (s.s.ok === false ? ' bad' : '') + '" role=treeitem><button type=button class=archeb data-ats="' + sk + '" aria-expanded=' + (sp ? 'true' : 'false') + '>'
          + '<span class=archen><em class=archsk>' + (s.k + 1) + '</em><b>' + esc(nm(s.from)) + '</b><i>→</i><b>' + esc(nm(s.to)) + '</b>'
          + (s.eis.length > 1 ? '<small>' + esc(T('+{n} same pair').replace('{n}', s.eis.length - 1)) + '</small>' : '') + '</span></button>'
          + (sp ? archEvHtml(Array.isArray(s.s.evidence) ? s.s.evidence : [s.s.evidence], 'f' + sk) : '') + '</li>'; }).join('') + '</ul>' : '') + '</li>'; });
  const oth = tr.other.w.concat(tr.other.c), oo = open('other'), bad = oth.filter(i => es[i].ok !== true).length;
  const rows = l => l.map(i => archEdgeRow(es[i], names, i, op === p + '\t' + i, '', o && o.dv && o.dv[i], o && o.sn)).join('');
  const sub = (k, lbl, l) => { const on = open('other.' + k);
    return !l.length ? '' : '<li class="archtn archto" role=treeitem><button type=button class=archnxb data-aet="other.' + k + '" aria-expanded=' + (on ? 'true' : 'false') + '>'
      + car(null, on) + esc(T(lbl).replace('{n}', l.length)) + '</button>' + (on ? '<ul class=archetl role=group>' + rows(l) + '</ul>' : '') + '</li>'; };
  const olbl = (bad ? T('Not on a traced flow · {n} · {m} unverified').replace('{m}', bad) : T('Not on a traced flow · {n} · all verified')).replace('{n}', oth.length);
  const ot = !oth.length ? '' : '<li class="archtn archto" role=treeitem><button type=button class=archnxb data-aet=other aria-expanded=' + (oo ? 'true' : 'false') + '>'
    + car(null, oo) + esc(olbl) + '</button>'
    + (oo ? '<ul class=archetl role=group>' + sub('w', 'Wiring ({n})', tr.other.w) + sub('c', 'Calls ({n})', tr.other.c) + '</ul>' : '') + '</li>';
  return '<div class=archeth><button type=button class=archnxa data-aetall=1>' + esc(T('Expand all')) + '</button>'
    + '<button type=button class=archnxa data-aetall=0>' + esc(T('Collapse all')) + '</button></div>'
    + '<ul class="archel-list archet" role=tree>' + fl.join('') + ot + '</ul>';
}
// Tree click (ds = the clicked element's dataset): caret folds; a flow node pins its flow (and opens); a step pins its edge.
function archEdTreeClick(p, ds){
  const d = ARCH.cache[p] || {}, et = Object.assign({}, ARCH.et), pin = k => { ARCH.op = ARCH.op === p + '\t' + k ? '' : p + '\t' + k; };
  if(ds.aetall != null){ Object.keys(et).forEach(k => { if(k.indexOf(p + '\t') === 0) delete et[k]; });
    if(ds.aetall === '1'){ archEdTree(d).flows.forEach(f => { et[p + '\t' + f.n] = true; }); ['other', 'other.w', 'other.c'].forEach(k => { et[p + '\t' + k] = true; }); } }
  else if(ds.aetf != null) et[p + '\t' + ds.aetf] = !et[p + '\t' + ds.aetf];
  else if(/^other(\.[wc])?$/.test(ds.aet || '')) et[p + '\t' + ds.aet] = !et[p + '\t' + ds.aet];
  else if(/^\d+$/.test(ds.aet || '')){ pin('f' + ds.aet); if(ARCH.op) et[p + '\t' + ds.aet] = true; }
  else if(ds.ats != null) pin('f' + ds.ats);
  // ⚠A fold that hides the pinned step / Other row must unpin it, else the map stays lit with no visible row.
  const ok = ARCH.op && ARCH.op.indexOf(p + '\t') === 0 ? ARCH.op.slice(p.length + 1) : '', sm = /^f(\d+)\.\d+$/.exec(ok);
  const hid = k => !!(ARCH.et || {})[p + '\t' + k] && !et[p + '\t' + k];
  // ⚠Other rows sit under two folds: closing «other» or the row's own sub-fold (other.w / other.c) hides it.
  const ot = /^\d+$/.test(ok) ? archEdTree(d).other : null, sub = ot && (ot.w.indexOf(+ok) >= 0 ? 'other.w' : ot.c.indexOf(+ok) >= 0 ? 'other.c' : '');
  if(sm ? hid(sm[1]) : sub && (hid('other') || hid(sub))) ARCH.op = '';
  ARCH.et = et;
}
document.addEventListener('click', ev => {
  const t = ev.target && ev.target.closest ? ev.target : null, b = t && strMode === 'arch' && t.closest('.archtab [data-aetf],.archtab [data-aet],.archtab [data-ats],.archtab [data-aetall]');
  if(!b) return;
  const hb = b.closest('button') || b, hadF = document.activeElement === hb, ds = b.dataset;   // ⚠the repaint drops focus to <body>
  archEdTreeClick(strOn[0] || '', ds); paintStruct();
  const a = ['aetall', 'aet', 'ats'].find(x => hb.dataset && hb.dataset[x] != null);
  if(hadF && a && typeof kbHold === 'function') kbHold('.archtab [data-' + a + '="' + hb.dataset[a] + '"]');
});
