// «Remove» on Config map hook chips (47b hnChip → hnRmBtn): one Claude Code hook entry out of user/project settings (POST /api/hooks/remove, sidereus/hook_remove.py).
// ⚠Rule 7: «Remove» only previews (dry); nothing is written before «Apply», which posts the preview's base sha (409 = file changed). Plugin hooks are never written: they get the `/plugin disable` hint.
let HNRM = null;   // {st: 'busy'|'prev'|'done'|'err'|'plug', proj, rm, diff, base, what, plug, msg, again}
function hnRmBtn(h){
  if(!h) return '';
  if(h.rm) return '<button type=button class=hnrmb data-hnrm="' + esc(h.rm) + '" title="' + esc(T('Remove this hook entry from its settings file')) + '">' + esc(T('Remove')) + '</button>';
  if(h.plug) return '<button type=button class=hnrmb data-hnrmp="' + esc(h.plug) + '" title="' + esc(T('How to turn off') + ': /plugin disable ' + h.plug) + '">' + esc(T('How to turn off')) + '</button>';
  return '';
}
// Server errors are English lines; only a fixed reason of ours goes through T(), the raw line is shown escaped.
function hnRmErr(e){
  const b = (e && e.body) || {}, m = String(b.err || b.error || (e && e.message) || e || '');
  if(e && e.status === 409) return T('The file changed since the preview. Preview again.');
  if(/origin/i.test(m)) return T('Refused: the request did not come from the viewer page.');
  if(/symlink/i.test(m)) return T('Refused: the settings file is a symlink. Edit it by hand.');
  if(/allow|outside/i.test(m)) return T('Refused: the file is outside the allowed settings files.');
  return T('Not removed') + ': ' + m;
}
function hnRmHtml(){
  const s = HNRM;
  if(!s) return '';
  const w = s.what || {}, row = (k, v) => v ? '<div class=hnrmw><span>' + esc(T(k)) + '</span><code>' + esc(v) + '</code></div>' : '';
  let h = '<div class=hnrmh><b>' + esc(T(s.st === 'plug' ? 'Plugin hook' : 'Remove hook')) + '</b><button type=button class=strp data-hnrma=close aria-label="' + esc(T('Close')) + '">×</button></div>';
  if(s.st === 'plug'){
    const cmd = '/plugin disable ' + s.plug;
    h += '<div class=hnrmw><span>' + esc(T('Plugin')) + '</span><code>' + esc(s.plug) + '</code></div>'
      + '<small>' + esc(T('This hook comes from a plugin. Sidereus never writes plugin files; turn the plugin off inside Claude Code:')) + '</small>'
      + '<div class=hnrmb2><code class=hnrmc>' + esc(cmd) + '</code><button type=button class=strp data-hnrma=copy>' + esc(T('Copy')) + '</button></div>';
  }
  else if(s.st === 'busy') h += '<small>' + esc(T('Loading…')) + '</small>';
  else if(s.st === 'prev'){
    h += row('Event', w.ev) + row('Matcher', w.matcher || (w.ev ? '*' : '')) + row('Command', w.cmd) + row('File', w.src)
      + '<small>' + esc(T('Nothing is written until Apply.')) + '</small><div class=hnrmd2>' + diffHtml(s.diff || '', agLang('x.json')) + '</div>'
      + '<div class=hnrmb2><button type=button class="strp on" data-hnrma=apply>' + esc(T('Apply')) + '</button><button type=button class=strp data-hnrma=close>' + esc(T('Cancel')) + '</button></div>';
  }
  if(s.msg) h += '<small class="hnrmm' + (s.st === 'err' ? ' err' : '') + '" role=status>' + esc(s.msg) + '</small>';
  if(s.again) h += '<div class=hnrmb2><button type=button class=strp data-hnrma=again>' + esc(T('Preview again')) + '</button></div>';
  return h;
}
// One fixed panel on body: ⚠never inside .hnw — poll repaints rebuild the lane and it must not push the main content.
function hnRmPaint(){
  let el = document.getElementById('hnrmdlg');
  if(!HNRM){ if(el) el.remove(); return; }
  if(!el){ el = document.createElement('div'); el.id = 'hnrmdlg'; el.className = 'hnrmdlg'; el.setAttribute('role', 'dialog'); el.setAttribute('aria-modal', 'false'); document.body.appendChild(el); }
  el.setAttribute('aria-label', T(HNRM.st === 'plug' ? 'Plugin hook' : 'Remove hook'));
  setHtml(el, hnRmHtml());
  if(el._st !== HNRM.st){   // new state: put focus on its main control so Tab reaches Apply
    el._st = HNRM.st;
    const f = el.querySelector('[data-hnrma=apply]') || el.querySelector('[data-hnrma=copy]') || el.querySelector('[data-hnrma=again]') || el.querySelector('[data-hnrma=close]');
    if(f) f.focus({ preventScroll: true });
  }
}
let HNRM_FROM = '';   // opener selector: chips are rebuilt by repaints, so focus returns by attribute, not by node
function hnRmClose(){
  HNRM = null; hnRmPaint();
  const b = HNRM_FROM && document.querySelector(HNRM_FROM);
  if(b) b.focus({ preventScroll: true });
}
// ⚠hnLoad drops a forced load while a poll fetch is in flight; that fetch predates the write, so wait for it (bounded).
function hnRmReload(proj, n){
  if(HN.busy[hnKey(proj)] && (n || 0) < 20) setTimeout(() => hnRmReload(proj, (n || 0) + 1), 500);
  else hnLoad(proj, true);
}
async function hnRmPreview(proj, rm){
  HNRM = { st: 'busy', proj, rm }; hnRmPaint();
  try{
    const r = await postJSON('/api/hooks/remove', { proj, rm, dry: true });
    if(!HNRM || HNRM.rm !== rm) return;
    HNRM = r && r.demo ? { st: 'done', proj, rm, msg: T('Demo — nothing is written') } : { st: 'prev', proj, rm, diff: String((r && r.diff) || ''), base: String((r && r.base) || ''), what: (r && r.what) || {} };
  }catch(e){ if(!HNRM || HNRM.rm !== rm) return; HNRM = { st: 'err', proj, rm, msg: hnRmErr(e), again: e && e.status === 409 }; }
  hnRmPaint();
}
async function hnRmApply(){
  const s = HNRM;
  if(!s || s.st !== 'prev') return;
  HNRM = Object.assign({}, s, { st: 'busy', msg: '' }); hnRmPaint();
  try{
    const r = await postJSON('/api/hooks/remove', { proj: s.proj, rm: s.rm, dry: false, base: s.base });
    if(!(r && r.demo)) hnRmReload(s.proj, 0);   // written even if the panel was closed meanwhile
    if(!(HNRM && HNRM.rm === s.rm && HNRM.st === 'busy')) return;   // another chip's panel opened meanwhile
    HNRM = { st: 'done', proj: s.proj, rm: s.rm, msg: r && r.demo ? T('Demo — nothing is written') : TV({msg: 'Removed. Backup: {f}', vars: {f: String((r && r.backup) || '?')}}) };
  }catch(e){ if(!(HNRM && HNRM.rm === s.rm && HNRM.st === 'busy')) return; HNRM = { st: 'err', proj: s.proj, rm: s.rm, msg: hnRmErr(e), again: e && e.status === 409 }; }
  hnRmPaint();
}
// Capture phase + stopPropagation: the chip under the button would otherwise open its file (47b document click/Enter handlers).
document.addEventListener('click', e => {
  const t = e.target && e.target.closest ? e.target : null;
  if(!t) return;
  const b = t.closest('.hnw [data-hnrm], .hnw [data-hnrmp]');
  if(b){
    e.stopPropagation(); e.preventDefault();
    HNRM_FROM = b.dataset.hnrmp ? '.hnw [data-hnrmp="' + CSS.escape(b.dataset.hnrmp) + '"]' : '.hnw [data-hnrm="' + CSS.escape(b.dataset.hnrm) + '"]';
    if(b.dataset.hnrmp){ HNRM = { st: 'plug', plug: b.dataset.hnrmp }; hnRmPaint(); }
    else hnRmPreview(PLS.proj, b.dataset.hnrm);
    return;
  }
  const a = t.closest('#hnrmdlg [data-hnrma]');
  if(!a || !HNRM) return;
  const k = a.dataset.hnrma;
  if(k === 'close') hnRmClose();
  else if(k === 'apply') hnRmApply();
  else if(k === 'again' && HNRM.rm) hnRmPreview(HNRM.proj, HNRM.rm);
  else if(k === 'copy' && HNRM.plug) copyText('/plugin disable ' + HNRM.plug).then(ok => { if(HNRM){ HNRM.msg = ok ? T('Copied') : T('Copy failed'); hnRmPaint(); } });
}, true);
document.addEventListener('keydown', e => {
  if(e.key === 'Escape' && HNRM){ hnRmClose(); return; }
  if((e.key === 'Enter' || e.key === ' ') && e.target && e.target.closest && e.target.closest('.hnw [data-hnrm], .hnw [data-hnrmp]')) e.stopPropagation();   // the button's own click still fires
}, true);
