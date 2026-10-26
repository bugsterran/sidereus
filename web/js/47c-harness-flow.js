// «Harness» flow strip (47b hnHtml top): one pipeline run as 7 nodes req → guard → edit → gate → review → commit → keep (/api/harness `flow`).
// ⚠Metadata only; every value goes through esc() and `st` reaches a class only via HN_FST. Run/node choice lives in HN.flowRun/HN.flowNode.
const HN_FST = { ok: 'ok', ng: 'ng', run: 'run', none: 'none' };
// HN_FK / HN_FO / HN_FD are shown as T(x, 'flow') — 'Edit' and 'running' alone are other Korean words.
const HN_FK = { req: 'Request', guard: 'Guard', edit: 'Edit', gate: 'Gate', review: 'Review', commit: 'Commit', keep: 'Kept' };
const HN_FO = { done: 'done', run: 'running', skip: 'skipped', back: 'sent back', fail: 'failed' };
// pl_flow.py deny codes (harness_flow.HF_DENY_CODES)
const HN_FD = { jump: 'Stage jump', agent: 'Wrong agent', model: 'Wrong model', tag: 'Missing tag', stage: 'Unknown stage', stop: 'Stopped',
  gate: 'Commit before gate', skipgate: 'Required gate skipped' };
function hnFN(s, n){ return esc(T(s).replace('{n}', n)); }
// Why a node has no value (harness_flow `why`); ⚠class and text come only from these maps, never the raw value. Missing/unknown → dash.
const HN_FW = { norec: 'not recorded', pending: 'not yet', window: 'outside read window', na: 'n/a' };
const HN_FWT = { norec: 'No gate evidence for this repo — the check gate or ev_hook did not capture it', pending: 'Run still open or uncommitted',
  window: 'Older than the evidence read window (512 KB tail)', na: 'This pipeline has no such stage' };
function hnFWk(nd){ return nd && typeof nd.why === 'string' && Object.prototype.hasOwnProperty.call(HN_FW, nd.why) ? nd.why : ''; }
function hnFW(nd){
  const w = hnFWk(nd);
  return w ? '<i class="hntm hnf-w-' + w + '" title="' + esc(T(HN_FWT[w])) + '">' + esc(T(HN_FW[w], 'flow')) + '</i>' : '<i class=hntm>—</i>';
}
function hnFRun(list){
  return list.find(r => r && r.id === HN.flowRun) || list[0];
}
function hnFLine(nd){
  const v = nd.v && typeof nd.v === 'object' ? nd.v : null, dash = hnFW(nd);
  if(nd.k === 'req') return v && v.name ? esc(v.name) + ' <i class=hntm>' + esc(hnWhen(v.t0)) + '</i>' : dash;
  if(nd.k === 'guard'){
    if(!v) return dash;
    const bits = [typeof v.deny === 'number' ? hnFN('Blocked {n}', v.deny) : esc(T('no record'))];
    if(v.skip > 0) bits.push(hnFN('{n} declared skip(s)', v.skip));
    if(v.loop > 0) bits.push(hnFN('{n} loop-back(s)', v.loop));
    return bits.join(' · ');
  }
  if(nd.k === 'edit'){
    if(!v) return dash;
    const bits = [];
    if(typeof v.files === 'number') bits.push(hnFN('{n} files', v.files));
    if(v.dirty) bits.push(esc(T('uncommitted')));
    return bits.length ? bits.join(' · ') : dash;
  }
  if(nd.k === 'gate'){
    const steps = v && Array.isArray(v.steps) ? v.steps : [];
    if(!steps.length) return dash;
    // One chip per mode («fast PASS 6/6»): listing every step of every mode overflowed the node; names go to the title,
    // failing ones stay visible.
    const by = {};
    steps.forEach(s => { if(!s) return; const m = s.mode == null ? '?' : String(s.mode); (by[m] = by[m] || []).push(s); });
    return (v.r2g ? '<b class=hnfrg>Red→Green</b> ' : '') + Object.keys(by).map(m => {
      const ss = by[m], bad = ss.filter(s => s.rc !== 0), nm = s => String(s.name != null ? s.name : '?');
      return '<span class="hnfs' + (bad.length ? ' hnng' : '') + '" title="' + esc(ss.map(s => nm(s) + ' ' + (s.rc === 0 ? 'PASS' : 'FAIL')).join(' · ')) + '">'
        + esc(m + ' ' + (bad.length ? 'FAIL ' + bad.map(nm).join(',') : 'PASS ' + ss.length + '/' + ss.length)) + '</span>';
    }).join('');
  }
  if(nd.k === 'review'){
    if(!v) return esc(T('n/a'));
    const o = HN_FO[v.o];
    return (o ? esc(T(o, 'flow')) : esc(v.o == null ? '?' : v.o)) + (v.back > 0 ? ' · ' + hnFN('{n} loop-back(s)', v.back) : '');
  }
  if(nd.k === 'commit'){
    if(!v || !v.head) return dash;
    return '<code class=hnrc>' + esc(String(v.head).slice(0, 8)) + '</code>' + (v.dirty ? ' · ' + esc(T('uncommitted')) : '');
  }
  if(nd.k === 'keep'){
    if(!v) return dash;
    const s = HN_TRS[v.state];
    return s ? esc(T(s[0])) : esc(v.state == null ? '?' : v.state);
  }
  return dash;
}
function hnFRec(nd){
  const rec = Array.isArray(nd.rec) ? nd.rec : [], v = nd.v && typeof nd.v === 'object' ? nd.v : null;
  let body = '';
  if(nd.k === 'req' && v) body = '<div class=hnrun><span class=hnrh>' + esc(v.name || '') + ' <code class=hnrc>' + esc(v.sid8 || '') + '</code> <i class=hntm>' + esc(hnWhen(v.t0)) + '</i></span></div>';
  else if(nd.k === 'guard') body = rec.map(x => x && x.k === 'deny' ? '<div class=hnfi>⊘ <i class=hntm>' + esc(hnWhen(x.ts)) + '</i> '
      + esc(HN_FD[x.code] ? T(HN_FD[x.code], 'flow') : String(x.code)) + (x.title ? ' · ' + esc(hnStg(x.title)) : '') + '</div>'
    : x && x.k === 'skip' ? '<div class=hnfi>↷ ' + esc(hnStg(x.title)) + '</div>'
    : '<div class=hnfi>↺ ' + esc(x && x.f) + ' → ' + esc(x && x.g) + ' ×' + esc(x && x.n) + '</div>').join('');
  else if(nd.k === 'edit') body = (v && v.from && v.to ? '<div class=hnfi><code class=hnrc>' + esc(String(v.from).slice(0, 8)) + '</code> → <code class=hnrc>'
    + esc(String(v.to).slice(0, 8)) + '</code>' + (typeof v.commits === 'number' ? ' <i class=hntm>· ' + esc(TV({msg: '{n} commits', vars: {n: v.commits}})) + '</i>' : '') + '</div>' : '')
    + rec.map(x => '<div class=hnfi><span class=hnfp title="' + esc(x && x.path) + '">' + esc(x && x.path) + '</span> <b class=hnfad>+' + esc(x && x.add != null ? x.add : '-')
      + '</b> <b class=hnfdl>−' + esc(x && x.del != null ? x.del : '-') + '</b></div>').join('');
  else if(nd.k === 'gate') body = rec.map(r => {
    r = r || {};
    const h = String(r.head == null ? '' : r.head);
    return '<div class="hnrun' + (r.rc === 0 ? '' : ' hnng') + '"><span class=hnrh><i class=hntm>' + esc(hnWhen(r.ts)) + '</i> <em class=hnsc>' + esc(r.mode || '') + '</em> '
      + '<code class=hnrc>' + esc(h.slice(0, 8) || '—') + '</code> ' + hnPF(r.rc === 0) + '</span>'
      + '<span class=hnsteps>' + (Array.isArray(r.steps) ? r.steps.map(hnStep).join('') : '') + '</span></div>';
  }).join('');
  // review/commit/keep carry no rec list: echo the node summary from the same `v` fields so a click never says «no record» over data.
  else if(v && (nd.k === 'review' || nd.k === 'commit' && v.head || nd.k === 'keep')) body = '<div class=hnfi>' + hnFLine(nd)
    + (nd.k === 'review' && v.n > 1 ? ' <i class=hntm>×' + esc(v.n) + '</i>' : '')
    + (nd.k === 'keep' ? (v.mode ? ' <em class=hnsc>' + esc(v.mode) + '</em>' : '') + (v.ts ? ' <i class=hntm>' + esc(hnWhen(v.ts)) + '</i>' : '') : '') + '</div>';
  return '<div class=hnfrec>' + (body || '<div class=hidnote>' + (hnFWk(nd) ? hnFW(nd) : esc(T('no record'))) + '</div>') + '</div>';
}
function hnFlow(list){
  list = Array.isArray(list) ? list.filter(r => r && Array.isArray(r.nodes)) : [];
  if(!list.length) return '';
  const run = hnFRun(list), sel = run.nodes.find(n => n && n.k === HN.flowNode);
  const chips = list.length > 1 ? '<div class=hnfc role=group aria-label="' + esc(T('Recent runs')) + '">' + list.map(r => '<button class="hnfb' + (r === run ? ' on' : '')
    + '" data-hnfr="' + esc(r.id) + '" aria-pressed=' + (r === run) + '>' + esc(r.src === 'evidence' ? T('Recent records') : r.name) + ' <i class=hntm>' + esc(hnWhen(r.t1)) + '</i></button>').join('') + '</div>' : '';
  const nodes = run.nodes.map((n, i) => {
    n = n || {};
    const lab = HN_FK[n.k] ? T(HN_FK[n.k], 'flow') : String(n.k);
    return (i ? '<span class=hnfa aria-hidden=true>→</span>' : '') + '<button class="hnfn hnf-' + (HN_FST[n.st] || 'none') + (sel === n ? ' on' : '') + '" data-hnfn="' + esc(n.k)
      + '" aria-expanded=' + (sel === n) + '><b class=hnft>' + esc(lab) + '</b><span class=hnfl>' + hnFLine(n) + '</span></button>';
  }).join('');
  const head = '<div class=brh2><b>' + esc(T('Flow')) + '</b> <i>' + esc(run.src === 'evidence' ? T('Recent records') : run.name + ' · ' + hnWhen(run.t0)) + '</i></div>';
  return '<div class=hnfw0>' + head + chips + '<div class=hnfw><div class=hnfrow>' + nodes + '</div></div>' + (sel ? hnFRec(sel) : '') + '</div>';
}
