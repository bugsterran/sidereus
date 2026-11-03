// «Get started» checklist above the Pipelines body (48 plMainBody): four steps read from data the viewer already has.
// Gone for good once every step is done or «Hide» is pressed (ui pref `sidereus.plStartDone`).
// ⚠Unknown is not «not done»: a step still loading or an unexpected reply shape hides the list instead of showing a false gap.
const PLST_KEY = 'sidereus.plStartDone';
let PLST_DX = null;   // null = not asked · 'busy' · {on: true|false|null}; one lazy GET, never polled
let PLST_PV = null;   // «Start with recommended setup» preview {proj, policy, busy, diff, files, cmd (null until the first reply), det, err, seq}
// Pure: Sidereus hooks or plugin seen in a GET /api/diag reply; null = reply without either key (not a diag body).
function plStartDxOn(d){
  if(!d || typeof d !== 'object' || d.ok === false) return null;
  const sid = d.sidereus && typeof d.sidereus === 'object' ? d.sidereus : null, pl = Array.isArray(d.plugins) ? d.plugins : null;
  if(!sid && !pl) return null;
  if(sid && Object.keys(sid).some(k => Array.isArray(sid[k]) && sid[k].length)) return true;
  return !!(pl && pl.some(x => x && x.name === 'sidereus' && x.on !== false));
}
function plStartDx(){
  if(PLST_DX === null){
    if(typeof FEATS === 'object' && FEATS && FEATS.diag === false){ PLST_DX = { on: false }; return false; }   // ⚠the route 404s with the feature off
    PLST_DX = 'busy';
    getJSON('/api/diag').then(d => { PLST_DX = { on: plStartDxOn(d) }; }, e => { PLST_DX = { on: e && e.status === 404 ? false : null }; })
      .then(() => plPaint());
  }
  return PLST_DX === 'busy' ? null : PLST_DX.on;
}
// Pure: [{k, en, done}] with done true / false / null (unknown). projs = /api/pipelines list, data = PLS.data.
// ⚠self_only rows (Sidereus' own sample pipelines in a clone) are not the person's project and never count.
function plStartSteps(dx, projs, data){
  const L = projs && projs.ok ? (projs.projects || []).filter(x => x && !x.self_only) : null;
  const add = L ? L.length > 0 : null;
  const ld = L ? L.map(x => data && data[x.path]).filter(d => d && d.ok) : [];
  const pls = [].concat(...ld.map(d => d.pipelines || []));
  const first = L ? L.some(x => x.n > 0) || pls.length > 0 : null;
  // ⚠An invalid pipeline file (ok false) never gets `red` from the server; counting it made the step unknown and hid the list.
  const plv = pls.filter(q => q && q.ok !== false);
  const red = first === false ? false : first === null ? null : plv.some(q => (+q.red || 0) > 0) ? true
    : !plv.length || plv.some(q => typeof q.red !== 'number') ? null : false;   // no list loaded yet, or a server without `red`
  return [{ k: 'cc', en: 'Claude Code connected', done: dx }, { k: 'proj', en: 'Project added', done: add },
    { k: 'pl', en: 'First pipeline', done: first }, { k: 'red', en: 'Gate red-checked', done: red }];
}
function plStartList(){
  if(lsGet(PLST_KEY, '') === '1') return '';
  const st = plStartSteps(plStartDx(), PLS.projs, PLS.data);
  if(st.every(s => s.done === true)){ lsSet(PLST_KEY, '1'); return ''; }
  if(st[2].done && st[3].done === null && typeof plLoadAll === 'function') plLoadAll();   // red counts live in each project's list
  if(st.some(s => s.done === null)) return '';
  const d = PLS.data[PLS.proj], cur = (((PLS.projs || {}).projects) || []).find(x => x.path === PLS.proj);
  const empty = !!(PLS.proj && d && d.ok && !(d.pipelines || []).length && !(cur && cur.self_only));   // starter only on a real project with no pipelines
  const li = st.map((s, i) => '<li class="plsti' + (s.done ? ' on' : '') + '" data-plst="' + s.k + '"><span class=plstm aria-hidden=true>' + (s.done ? '✓' : (i + 1)) + '</span><span class=plstt>' + esc(T(s.en)) + '</span>'
    + (s.k === 'pl' && empty ? '<button type=button class="wkrgb plsv" data-plstgo' + (PLST_PV && PLST_PV.busy ? ' disabled' : '') + '>' + esc(T('Start with recommended setup')) + '</button>' : '') + '</li>').join('');
  return '<section class=plst aria-label="' + esc(T('Get started')) + '"><div class=plsth><b>' + esc(T('Get started')) + '</b><button type=button class=wkrgb data-plsthide>' + esc(T('Hide')) + '</button></div>'
    + '<ol class=plstl>' + li + '</ol>' + (empty ? plStartPrev(PLST_PV, PLS.proj) : '') + '</section>';
}
// Pure: server dry diff + strict-mode box (unticked by default) + test-command input (gate); nothing is written before «Confirm».
function plStartPrev(V, proj){
  if(!V || V.proj !== proj) return '';
  // ⚠Server rows are {rel, state}; an error keeps the form so the command can be fixed and previewed again.
  const files = (V.files || []).map(f => f && typeof f === 'object' ? String(f.rel || '') : String(f)).filter(Boolean).join(' · ');
  return '<div class="pldiff plstpv"><div class=brh2><b>' + esc(T('Start with recommended setup')) + '</b> <i>' + esc(files) + '</i></div>'
    + '<label class=plstpol><input type=checkbox data-plstpol' + (V.policy ? ' checked' : '') + (V.busy ? ' disabled' : '') + '> ' + esc(T('Turn on strict mode (file edits need an open run)')) + '</label>'
    + '<div class="hidnote plstpoln">' + esc(T('When on, file edits in this project need an open pipeline run.')) + '</div>'
    + (V.cmd != null ? '<label class=plstcmd>' + esc(T('Test command')) + ' <input type=text data-plstcmd value="' + esc(V.cmd) + '" placeholder="' + esc(T('Your test command, e.g. npm test')) + '"' + (V.busy ? ' disabled' : '') + '>'
      + (V.det && V.cmd === V.det ? ' <span class=plstdet>' + esc(T('Detected')) + '</span>' : '') + '</label>'
      + (V.cmd.trim() ? '' : '<div class="hidnote plstng">' + esc(T('Empty — the gate is left out')) + '</div>') : '')
    + (V.diff != null ? '<pre>' + diffHtml(V.diff, typeof agLang === 'function' ? agLang('x.json') : '') + '</pre>' : V.err && !V.busy ? '' : '<div class=hidnote>' + esc(T('Loading…')) + '</div>')
    + (V.err ? '<div class="hidnote plerr" role=alert>' + esc(V.err) + '</div>' : '')
    + '<div class=plbar><button type=button class=wkrgb data-plstok' + (V.busy || V.diff == null ? ' disabled' : '') + '>' + esc(T('Confirm')) + '</button><button type=button class=wkrgb data-plstno>' + esc(T('Cancel')) + '</button></div></div>';
}
async function plStartFetch(write){
  const V = PLST_PV;
  if(!V || V.busy) return;
  const seq = V.seq = (V.seq || 0) + 1, proj = V.proj;
  V.busy = true; V.err = ''; if(!write) V.diff = null;
  plPaint();
  let r;
  const q = { proj: proj, policy: !!V.policy, dry: !write };
  if(V.cmd != null) q.gate = V.cmd.trim();   // ⚠after the first reply the preview's command is always sent, so Confirm writes what was shown
  try{ r = await postJSON('/api/pipelines/starter', q); }
  catch(x){ r = x.body || { ok: false, err: String((x && x.message) || x) }; }
  if(PLST_PV !== V || V.seq !== seq) return;   // ⚠a late reply for a closed preview or an older strict-mode tick is dropped
  V.busy = false;
  if(!r || !r.ok){ V.err = T('Could not save') + (r && (r.err || r.error || r.why) ? ' — ' + TE(r) : ''); plPaint(); return; }
  if(!write){ V.diff = String(r.diff || ''); V.files = Array.isArray(r.files) ? r.files : []; if(V.cmd == null){ V.det = typeof r.detected === 'string' ? r.detected : ''; V.cmd = V.det; } plPaint(); return; }
  PLST_PV = null;
  const wr = (Array.isArray(r.files) ? r.files : []).filter(f => f && f.state === 'written').map(f => String(f.rel || '')).filter(Boolean);   // server reports per-file state, no `written` list
  PLS.msg = r.demo ? T('Demo — nothing is written') : wr.length ? T('Saved: {s}').replace('{s}', () => wr.join(' · ')) : T('Nothing written — the files already exist');
  PLS.projs = null; plLoadProjs(); await plLoad(proj, true);
  plPaint();
}
document.addEventListener('click', e => {
  const t = e.target && e.target.closest ? e.target : null;
  if(!t || !t.closest('.plst')) return;
  if(t.closest('[data-plsthide]')){ lsSet(PLST_KEY, '1'); PLST_PV = null; plPaint(); return; }
  if(t.closest('[data-plstgo]')){ if(PLST_PV && PLST_PV.proj === PLS.proj){ if(!PLST_PV.busy){ PLST_PV = null; plPaint(); } return; }   // second press closes the preview
    PLST_PV = { proj: PLS.proj, policy: false, busy: false, diff: null, files: [], cmd: null, det: '', err: '' }; plStartFetch(false); return; }
  if(t.closest('[data-plstok]')) return plStartFetch(true);
  if(t.closest('[data-plstno]')){ if(PLST_PV && !PLST_PV.busy) PLST_PV = null; plPaint(); }
});
document.addEventListener('change', e => {
  const t = e.target;
  if(!t || !t.matches || !PLST_PV || PLST_PV.busy) return;
  if(t.matches('[data-plstpol]')) PLST_PV.policy = !!t.checked;   // strict mode changes the written files: preview again before any write
  else if(t.matches('[data-plstcmd]')) PLST_PV.cmd = String(t.value || '');   // change (blur/Enter), not input: one dry fetch per edit
  else return;
  plStartFetch(false);
});
