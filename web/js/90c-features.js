// Settings «Preferences» › «Features» (docs/dev/FEATURES.md): feature toggles from GET /api/prefs `features`; saved to config, applies after a restart.
let MPF_PEND = null, MPF_NOTE = null;   // {id: bool} toggles not saved yet (null = untouched) · {err|ok} after a save
// Names for deps that are still core (no manifest, so no title in the listing) — ids are not for the screen.
const MPF_CORE = {hist: 'History', failures: 'Failures', tokens: 'Tokens', tools: 'Tool', struct: 'Structure', br: 'Branches', timeline: 'Timeline'};
function mpfRows(){ return (MPSRV && Array.isArray(MPSRV.features)) ? MPSRV.features : []; }
// Wanted toggle per id: pending, else the saved one.
function mpfWant(rows){ const w = {}; rows.forEach(r => { w[r.id] = MPF_PEND && r.id in MPF_PEND ? MPF_PEND[r.id] : r.set !== false; }); return w; }
// Same rule as features.on(): an off dep with a manifest forces dependents off; deps without one are core = on. ⚠cycle-safe.
function mpfEff(w, deps, id, seen){
  if(!(id in w)) return true;
  seen = seen || {};
  if(seen[id]) return true;
  seen[id] = 1;
  return w[id] && (deps[id] || []).every(d => mpfEff(w, deps, d, seen));
}
// ⚠Value the checkbox shows (blocked by an off dep = off); Changes and Save must use this, not raw want.
function mpfShown(rows, w){
  const deps = {}, s = {};
  rows.forEach(r => { deps[r.id] = r.deps || []; });
  rows.forEach(r => { s[r.id] = !!w[r.id] && !deps[r.id].some(d => d in w && !mpfEff(w, deps, d)); });
  return s;
}
function mpfPane(){
  const rows = mpfRows();
  if(!rows.length) return '';
  const w = mpfWant(rows), deps = {}, tl = {};
  rows.forEach(r => { deps[r.id] = r.deps || []; tl[r.id] = T(r.title || r.id); });
  const nm = id => tl[id] || (MPF_CORE[id] ? T(MPF_CORE[id]) : id), oo = b => b ? T('On', 'state') : T('Off', 'state');
  let h = '<div class=cfgs>' + esc(T('Features') + ' · ' + T('Applies after restart')) + '</div>'
    + '<div class=cfgpd>' + esc(T('A feature that is off stops its tab, requests and background work. Save, then restart to apply.')) + '</div>';
  // ⚠Save/Undo sit above the rows: below the last row they fell off-screen and read as «no Save button».
  const sh = mpfShown(rows, w), ch = rows.filter(r => sh[r.id] !== (r.set !== false));
  if(ch.length) h += '<div class=cfgpd>' + esc(T('Changes') + ': ' + ch.map(r => nm(r.id) + ' ' + oo(r.set !== false) + ' → ' + oo(sh[r.id])).join(' · ')) + '</div>'
    + cfgOpt('mpf', 'save', T('Save'), false) + cfgOpt('mpf', 'undo', T('Undo'), false);
  if(MPF_NOTE) h += MPF_NOTE.err ? '<span class="mpnote err">' + esc(MPF_NOTE.err) + '</span>' : '<span class=mpnote>' + esc(T('Applies after restart')) + '</span>';
  h += rows.map(r => {
    const blk = deps[r.id].filter(d => d in w && !mpfEff(w, deps, d));
    const hint = (blk.length ? T('Turn on first') + ': ' + blk.map(nm).join(', ')
      : deps[r.id].length ? T('Needed') + ': ' + deps[r.id].map(nm).join(', ') : '') + (r.on ? '' : (deps[r.id].length ? ' · ' : '') + T('off now'));
    return cfgSet(nm(r.id), hint, '<label class="mpfl' + (blk.length ? ' off' : '') + '"><input type=checkbox class=cfgck data-k=mpf value="' + esc(r.id) + '"'
      + (sh[r.id] ? ' checked' : '') + (blk.length ? ' disabled' : '') + '> ' + esc(oo(sh[r.id])) + '</label>');
  }).join('');
  return h;
}
// mpf action: 'id:1|0' (checkbox) · 'undo' · 'save' (the button is the confirm step — nothing is sent before it).
function mpfAct(v){
  const rows = mpfRows();
  if(v === 'undo'){ MPF_PEND = null; return; }
  if(v === 'save') return mpfSave(rows);
  const i = v.lastIndexOf(':'), id = v.slice(0, i);
  if(!rows.some(r => r.id === id)) return;
  MPF_PEND = Object.assign({}, MPF_PEND || {}); MPF_PEND[id] = v.slice(i + 1) === '1'; MPF_NOTE = null;
}
async function mpfSave(rows){
  const w = mpfShown(rows, mpfWant(rows)), all = rows.every(r => w[r.id]);
  const body = all ? {key: 'features', reset: true} : {key: 'features', value: w};   // all on = drop the key (missing = all on)
  let r = null;
  try{ r = await postJSON('/api/prefs/set', body); }catch(e){ r = e.body || {ok: false, err: String((e && e.message) || e)}; }
  if(r && r.ok){ rows.forEach(x => { x.set = w[x.id]; }); MPF_PEND = null; MPF_NOTE = {ok: 1}; }
  else MPF_NOTE = {err: T('Could not save') + ': ' + ((r && r.err) || '?')};
  paintCfg();
}
