// Store detail «Data path»: which flow entry points write or read this store, from the verified map only (no fetch).
// Pure: {w, r} rows [{f, est}] in d.flows order, one per flow per side; null when the map has no flows or sid is no store.
// ⚠A flow reaches a module only when that module is named in one of its ok steps — never walk the call graph.
// A route = one ok edge M->store (read|write) + one ok step touching M; it is estimated when the edge or that step is est.
// A side of a flow is estimated only when every route is; one non-est route wins.
function archDataPath(d, sid){
  const fl = d && Array.isArray(d.flows) ? d.flows : [], mods = (d && d.modules) || [];
  if(!fl.length || !mods.some(x => x && x.id === sid && x.kind === 'store')) return null;
  const eds = ((d && d.edges) || []).filter(e => e && e.ok === true && e.to === sid && (e.kind === 'read' || e.kind === 'write'));
  const out = { w: [], r: [] };
  fl.forEach(f => {
    if(!f) return;
    const st = (Array.isArray(f.steps) ? f.steps : []).filter(s => s && s.ok === true), side = { write: null, read: null };
    eds.forEach(e => {
      st.forEach(s => {
        if(s.from !== e.from && s.to !== e.from) return;
        const est = !!e.est || !!s.est;
        side[e.kind] = side[e.kind] === null ? est : side[e.kind] && est;
      });
    });
    if(side.write !== null) out.w.push({ f, est: side.write });
    if(side.read !== null) out.r.push({ f, est: side.read });
  });
  return out;
}
// Pure: «Data path» section for a store's detail panel; '' when archDataPath is null. lit = the lit flow id or null.
function archDataPathHtml(d, m, lit){
  const dp = m ? archDataPath(d, m.id) : null;
  if(!dp) return '';
  const kind = k => typeof archFlowKind === 'function' ? archFlowKind(k) : String(k || '');
  const row = x => { const f = x.f, en = f.entry && typeof f.entry === 'object' ? f.entry : {}, id = String(f.id);
    const on = lit != null && String(lit) === id;
    return '<li><button type=button data-ardp="' + esc(id) + '" aria-pressed=' + (on ? 'true' : 'false') + (on ? ' class=on' : '') + '>'
      + '<b>' + (en.kind ? '<em class=archk>' + esc(kind(en.kind)) + '</em> ' : '') + esc(en.label || f.name || id) + '</b>'
      + '<small>' + esc(f.name || id)
      + (x.est ? ' <em class="archbg archest" title="' + esc(T('Evidence is inferred, not a direct reference')) + '">' + esc(T('estimate')) + '</em>' : '')
      + '</small></button></li>'; };
  const side = (t, xs) => xs.length ? '<div class=archdps>' + esc(T(t)) + '</div><ul class=archfv>' + xs.map(row).join('') + '</ul>' : '';
  return '<div class=archdh><b>' + esc(T('Data path')) + '</b></div>'
    + (dp.w.length || dp.r.length ? side('Written by', dp.w) + side('Read by', dp.r)
      : '<div class=archevn>' + esc(T('No entry point reaches this store')) + '</div>');
}
// Row click opens that flow's sequence view and lights it (same state as «Sequence diagram» in 84k archFlowBtn).
function archDataPathClick(t){
  if(!t || !t.closest || strMode !== 'arch' || !t.closest('.archtab')) return false;
  const b = t.closest('[data-ardp]');
  if(!b) return false;
  const p = strOn[0] || '', id = b.dataset.ardp, hadF = document.activeElement === b;
  ARCH.flow = ARCH.flow && ARCH.flow.p === p && String(ARCH.flow.id) === id ? null : { p, id };
  ARCH.lit = { p, flow: id }; ARCH.op = ''; paintStruct();
  if(hadF && typeof kbHold === 'function') kbHold('.archdet [data-ardp="' + id.replace(/["\\]/g, '\\$&') + '"]', '.archtab [data-arseq]');   // ⚠the repaint drops focus to <body>
  return true;
}
document.addEventListener('click', ev => { archDataPathClick(ev.target); });
