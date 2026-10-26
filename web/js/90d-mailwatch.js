// Settings «Preferences» › «Mailbox watch»: config `mailbox_watch` {mode, projects} (sidereus/prefs.py), read by the SessionStart hook.
// Mounted by observing #cfgbox (90-settings.js paintCfg rebuilds it); own delegated handlers, saved via /api/prefs/set after confirm().
let MW_PEND = null, MW_NOTE = null, MW_PROJS = null, MW_LD = false;   // pending {mode, projects} · {err|ok} · /api/pipelines projects
function mwSaved(){ const v = MPSRV && MPSRV.ok && MPSRV.mailbox_watch; return v ? { mode: v.mode, projects: Object.assign({}, v.projects) } : null; }
function mwWant(){ return MW_PEND || mwSaved(); }
const mwOO = m => m === 'on' ? T('On', 'state') : T('Off', 'state');
async function mwLoadProjs(){
  if(MW_PROJS || MW_LD || (typeof FEATS === 'object' && FEATS && FEATS.pipeline === false)) return;   // route 404s with the feature off
  MW_LD = true;
  try{ const r = await getJSON('/api/pipelines'); MW_PROJS = (r && r.ok && r.projects) || []; }catch(e){ MW_PROJS = []; }
  MW_LD = false;
  mwRepaint();
}
// Same project source as the pipeline tab chips (48-pipeline.js plChips): known pipeline projects ∪ live session projects ∪ saved overrides.
// ⚠Same path as prefs.py _path_key on Windows: drive/UNC paths ignore case and `/` = `\`; POSIX paths unchanged.
function mwKey(p){
  if(!/^(?:[A-Za-z]:[\\/]|\\\\)/.test(p)) return p;
  const k = p.replace(/\//g, '\\').toLowerCase(), u = k.slice(0, 2) === '\\\\';
  return (u ? '\\' : '') + k.replace(/\\+/g, '\\').replace(/(.)\\$/, (m, c) => c === ':' ? m : c);
}
// {normalised key: [spelling, value]} — last key wins, as the server's save does.
function mwNorm(projs){ const m = {}; Object.keys(projs || {}).forEach(p => { m[mwKey(p)] = [p, projs[p]]; }); return m; }
function mwProjList(w){
  const m = new Map();
  Object.keys((w && w.projects) || {}).forEach(p => m.set(mwKey(p), p));   // saved spelling first
  const add = p => { if(p && !m.has(mwKey(p))) m.set(mwKey(p), p); };
  (MW_PROJS || []).forEach(x => add(x && x.path));
  (typeof strProjList === 'function' ? strProjList() : []).forEach(e => add(e && e.p));
  return [...new Set(m.values())].sort();
}
function mwDiff(a, b){
  const out = [], na = mwNorm(a.projects), nb = mwNorm(b.projects);
  if(a.mode !== b.mode) out.push(T('Default', 'short') + ' ' + mwOO(a.mode) + ' → ' + mwOO(b.mode));
  new Set(Object.keys(na).concat(Object.keys(nb))).forEach(k => {
    const x = na[k] && na[k][1], y = nb[k] && nb[k][1];
    if(x !== y) out.push((nb[k] || na[k])[0] + ' ' + (x ? mwOO(x) : T('default')) + ' → ' + (y ? mwOO(y) : T('default')));
  });
  return out;
}
function mwPane(){
  const sv = mwSaved();
  if(!sv) return '';
  mwLoadProjs();
  const w = mwWant(), ch = mwDiff(sv, w);
  let h = '<div class=mwsec><div class=cfgs>' + esc(T('Mailbox watch')) + '</div>'
    + '<div class=cfgpd>' + esc(T('Applies to sessions started after the change')) + '</div>'
    + cfgSet(T('New sessions turn on mailbox watch automatically'),
        T('A per-project setting overrides this'),
        '<label class=mpfl><input type=checkbox data-mwg' + (w.mode === 'on' ? ' checked' : '') + '> ' + esc(mwOO(w.mode)) + '</label>');
  const ps = mwProjList(w);
  h += '<div class=mpls>' + ps.map(p => {
    const own = w.projects[p], eff = own || w.mode;
    return '<div class="mpli' + (eff === 'on' ? '' : ' off') + '"><span title="' + esc(p) + '">' + esc(typeof strShort === 'function' ? strShort(p) : p) + '</span>'
      + [['', T('Default', 'value')], ['on', T('On', 'state')], ['off', T('Off', 'state')]].map(([k, l]) => '<button class="strp' + ((own || '') === k ? ' on' : '')
        + '" data-mwp="' + esc(k) + '" data-mwpath="' + esc(p) + '">' + esc(l) + '</button>').join('') + '</div>';
  }).join('') + (ps.length ? '' : '<div class=cfgpd>' + esc(T('No projects')) + '</div>') + '</div>';
  if(ch.length) h += '<div class=cfgpd>' + esc(T('Changed', 'state') + ': ' + ch.join(' · ')) + '</div>'
    + '<button class=strp data-mwsave>' + esc(T('Save')) + '</button><button class=strp data-mwundo>' + esc(T('Undo')) + '</button>';
  if(MW_NOTE) h += MW_NOTE.err ? '<span class="mpnote err">' + esc(MW_NOTE.err) + '</span>'
    : '<span class=mpnote>' + esc(T('Saved · applies to new sessions')) + '</span>';
  return h + '</div>';
}
function mwRepaint(){
  const box = document.getElementById('cfgbox'), old = box && box.querySelector('.mwsec');
  const a = document.activeElement, had = !!(old && a && old.contains(a));
  if(old) old.outerHTML = mwPane() || '<div class=mwsec></div>';
  else mwMount();
  const sec = had && box.querySelector('.mwsec');
  if(sec) mwFocusAfter(sec, a);
}
// ⚠outerHTML drops the focused control: re-find it by its data attributes; save/undo vanish once clean → the default checkbox.
function mwFocusAfter(sec, a){
  const d = a.dataset || {}, cs = [...sec.querySelectorAll('button, input')];
  const t = ('mwpath' in d && cs.find(x => x.dataset.mwpath === d.mwpath && x.dataset.mwp === d.mwp))
    || cs.find(x => ['mwsave', 'mwundo', 'mwg'].some(n => n in d && n in x.dataset)) || sec.querySelector('input[data-mwg]');
  if(t) t.focus();
}
// ⚠Only the «Preferences» pane; observer watches #cfgbox children only, so the insert below does not re-trigger it.
function mwMount(){
  const box = document.getElementById('cfgbox'), pn = box && box.querySelector('.cfgpn');
  if(!pn || typeof CFGCAT === 'undefined' || CFGCAT !== 'me' || pn.querySelector('.mwsec')) return;
  const h = mwPane();
  if(h) pn.insertAdjacentHTML('beforeend', h);
}
async function mwSave(){
  const sv = mwSaved(), w = mwWant();
  if(!sv || !w) return;
  const ch = mwDiff(sv, w);
  if(!ch.length || !confirm(T('Change mailbox watch? Applies to sessions started after the change.') + '\n\n' + ch.join('\n'))) return;
  const dflt = w.mode === 'on' && !Object.keys(w.projects).length;
  const body = dflt ? { key: 'mailbox_watch', reset: true } : { key: 'mailbox_watch', value: w };   // default = drop the key (missing = on)
  let r = null;
  try{ r = await postJSON('/api/prefs/set', body); }catch(e){ r = e.body || { ok: false, err: String((e && e.message) || e) }; }
  if(r && r.ok){ MPSRV.mailbox_watch = { mode: w.mode, projects: Object.assign({}, w.projects) }; MW_PEND = null; MW_NOTE = { ok: 1 }; }
  else MW_NOTE = { err: T('Could not save') + ': ' + ((r && r.err) || '?') };
  mwRepaint();
}
document.addEventListener('click', e => {
  const b = e.target.closest && e.target.closest('#cfgbox .mwsec button');
  if(!b) return;
  if(b.hasAttribute('data-mwsave')){ mwSave(); return; }
  if(b.hasAttribute('data-mwundo')){ MW_PEND = null; MW_NOTE = null; mwRepaint(); return; }
  if(b.hasAttribute('data-mwpath')){
    const w = mwWant(); if(!w) return;
    const p = b.dataset.mwpath, k = b.dataset.mwp;
    MW_PEND = { mode: w.mode, projects: Object.assign({}, w.projects) };
    Object.keys(MW_PEND.projects).forEach(o => { if(o !== p && mwKey(o) === mwKey(p)) delete MW_PEND.projects[o]; });
    if(k === 'on' || k === 'off') MW_PEND.projects[p] = k; else delete MW_PEND.projects[p];
    MW_NOTE = null; mwRepaint();
  }
});
document.addEventListener('change', e => {
  const c = e.target;
  if(!c || !c.matches || !c.matches('#cfgbox .mwsec input[data-mwg]')) return;
  const w = mwWant(); if(!w) return;
  MW_PEND = { mode: c.checked ? 'on' : 'off', projects: Object.assign({}, w.projects) };
  MW_NOTE = null; mwRepaint();
});
(function(){
  const box = document.getElementById('cfgbox');
  if(box && typeof MutationObserver === 'function') new MutationObserver(mwMount).observe(box, { childList: true });
})();
