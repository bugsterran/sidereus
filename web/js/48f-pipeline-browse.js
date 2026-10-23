// «+ Add project» folder browser modal (GET /api/pipelines/projects/dirs: folder names + git/Claude flags only, home only).
// «Add this folder» goes through plAddGo (48-pipeline.js) = the same POST /api/pipelines/projects/add with its Origin guard.
let PLBR = null;   // {path, home, parent, dirs, more, msg, busy, pick, picking, hidden, recent} while the modal is open
// «Recent session folders» (?recent=1): suggestions only; a click is the same plBrLoad as typing the path.
function plBrAt(at){ const n = typeof at === 'number' ? at : (isNaN(+at) ? Date.parse(at) / 1000 : +at); return isFinite(n) && n > 0 ? n : 0; }   // epoch seconds or ISO
function plBrRecent(B){
  const r = Array.isArray(B.recent) ? B.recent.filter(x => x && x.path) : [];
  if(!r.length) return '';
  return '<div class=plbrrec><div class=plbrrt>' + esc(T('Recent session folders')) + '</div>' + r.slice(0, 8).map(x => {
    const t = plBrAt(x.at);
    return '<button class=plbrd data-plbrgo="' + esc(x.path) + '" title="' + esc(x.path) + '"><span class=plbrrn>' + esc(x.name || x.path) + '</span>'
      + '<em class=plbrrp>' + esc(x.path) + '</em>' + (t ? '<i class=plbrra>' + esc(agoAt(t)) + '</i>' : '') + '</button>';
  }).join('') + '</div>';
}
async function plBrRecentLoad(){
  let j = null;
  try{ const r = await fetch('/api/pipelines/projects/dirs?recent=1', { cache: 'no-store' }); j = await r.json(); }
  catch(x){ j = null; }   // no row on failure, no error
  if(!PLBR || !j || !j.ok || !Array.isArray(j.recent) || !j.recent.length) return;
  const i = document.querySelector('[data-plbrin]'), v = i && i.value, f = i && document.activeElement === i;
  PLBR.recent = j.recent; plBrPaint();
  const n = document.querySelector('[data-plbrin]'); if(n && i){ n.value = v; if(f) n.focus(); }   // ⚠async repaint: keep a half-typed path and its focus
}
function plBrCrumbs(B){
  if(!B.home || !B.path) return '';
  // Windows paths split on \ too; the drive prefix stays inside home (the «~» crumb).
  const sep = plBrSep(B), rel = B.path === B.home ? [] : B.path.slice(B.home.length).split(/[\\/]/).filter(Boolean);
  let acc = B.home.replace(/[\\/]+$/, '');
  return '<div class=plbrc><button class=plbrs data-plbrgo="' + esc(B.home) + '" title="' + esc(B.home) + '">~</button>'
    + rel.map(seg => { acc += sep + seg; return '<i>' + esc(sep) + '</i><button class=plbrs data-plbrgo="' + esc(acc) + '">' + esc(seg) + '</button>'; }).join('') + '</div>';
}
function plBrSep(B){ const p = String(B.home || B.path || ''); return p.indexOf('\\') >= 0 && p.indexOf('/') < 0 ? '\\' : '/'; }
function plBrList(B){
  if(!B.dirs) return '<div class=plbre>' + esc(T(B.busy ? 'Loading…' : 'No such folder')) + '</div>';
  if(!B.dirs.length) return '<div class=plbre>' + esc(T('No subfolders')) + '</div>';
  const base = B.path.replace(/[\\/]+$/, ''), sep = plBrSep(B);
  return B.dirs.map(d => '<button class=plbrd data-plbrgo="' + esc(base + sep + d.name) + '"><span>' + esc(d.name) + '</span>'
    + (d.git ? '<b class="plbrb git">git</b>' : '') + (d.claude ? '<b class="plbrb cl">' + esc(T('Claude config')) + '</b>' : '') + '</button>').join('')
    + (B.more ? '<div class=plbre>' + esc(T('Only the first 500 folders are shown — type the path instead')) + '</div>' : '');
}
function plBrHtml(B){
  return '<div class="cfgbox plbrbox' + (plBrRecent(B) ? ' rec' : '') + '" tabindex=-1><div class=cfgh><b>' + esc(T('Add project')) + '</b><span>' + esc(T('Pick a folder to add to the list'))
    + '</span><button class=cfgx data-plbrx title="' + esc(T('Close')) + '">✕</button></div>' + plBrRecent(B) + plBrCrumbs(B)
    + '<div class=plbrr><button class=strp data-plbrup' + (B.parent ? '' : ' disabled') + '>' + esc(T('Parent folder')) + '</button>'
    + '<input class=plbrin data-plbrin value="' + esc(B.path || '') + '" placeholder="' + esc(T('Folder path (e.g. ~/projects/my-app)')) + '">'
    + (B.pick ? '<button class=strp data-plbrpick' + (B.picking ? ' disabled' : '') + '>' + esc(T('Choose folder…')) + '</button>' : '')
    + '<label class=plbrh><input type=checkbox data-plbrhid' + (B.hidden ? ' checked' : '') + '>' + esc(T('Show hidden folders')) + '</label></div>'
    + '<div class=plbrl>' + plBrList(B) + '</div>' + (B.msg ? '<div class=pladdmsg>' + esc(T(B.msg)) + '</div>' : '')
    + '<div class=plbrf><button class="strp on" data-plbradd' + (B.busy || !B.path ? ' disabled' : '') + '>' + esc(T('Add this folder')) + '</button>'
    + '<button class=strp data-plbrx>' + esc(T('Cancel')) + '</button></div></div>';
}
function plBrPaint(){
  let m = document.getElementById('plbr');
  if(!PLBR){ if(m) m.remove(); return; }
  if(!m){ m = document.createElement('div'); m.id = 'plbr'; m.className = 'cfgm plbr'; m.setAttribute('role', 'dialog'); m.setAttribute('aria-modal', 'true'); document.body.appendChild(m); }
  m.innerHTML = plBrHtml(PLBR);
}
async function plBrLoad(path, fallback){
  if(!PLBR) return;
  PLBR.busy = true; PLBR.msg = ''; plBrPaint();
  let j;
  try{ const r = await fetch('/api/pipelines/projects/dirs?path=' + encodeURIComponent(path || '') + (PLBR.hidden ? '&hidden=1' : ''), { cache: 'no-store' }); j = await r.json(); }
  catch(x){ j = { ok: false, msg: String((x && x.message) || x) }; }
  if(!PLBR) return;
  PLBR.busy = false;
  if(!j || !j.ok){
    if(fallback && path) return plBrLoad('', false);   // remembered folder vanished or moved outside home: start at home
    PLBR.msg = (j && j.msg) || 'Could not read the folder'; plBrPaint(); return;
  }
  Object.assign(PLBR, { path: j.path, home: j.home, parent: j.parent, dirs: j.dirs, more: !!j.more, pick: !!j.pick });
  lsSet('sidereus.plbrdir', j.path);
  plBrPaint();
  const i = document.querySelector('[data-plbrin]'); if(i) i.focus();
}
function plBrOpen(){
  PLBR = { path: '', home: '', parent: '', dirs: null, more: false, msg: '', busy: true, recent: [] };
  plBrPaint(); plBrLoad(lsGet('sidereus.plbrdir', ''), true); plBrRecentLoad();   // parallel: the folder list never waits on it
}
function plBrClose(){
  PLBR = null; plBrPaint();
  const b = document.querySelector('.plw [data-ppk="pl"]'); if(b) b.focus({ preventScroll: true });   // queried: a repaint may have replaced the opener (the add button lives in the 08b picker)
}
// Tab cycles inside the modal (aria-modal alone does not stop focus leaving).
function plBrTrap(e){
  const box = document.querySelector('#plbr .plbrbox');
  if(!box) return;
  const f = Array.from(box.querySelectorAll('button:not([disabled]), input:not([disabled])'));
  if(!f.length) return;
  const i = f.indexOf(document.activeElement), n = e.shiftKey ? (i <= 0 ? f.length - 1 : i - 1) : (i < 0 || i === f.length - 1 ? 0 : i + 1);
  e.preventDefault(); f[n].focus();
}
// «Choose folder…»: the server opens the OS dialog (browsers never expose absolute paths); fills the path only, «Add this folder» still adds.
async function plBrPick(){
  if(!PLBR || PLBR.picking) return;
  PLBR.picking = true; PLBR.msg = 'A folder dialog is open…'; plBrPaint();
  let r;
  try{ r = await postJSON('/api/pick-folder', {}); }
  catch(x){ r = x.body || { ok: false, err: String((x && x.message) || x) }; }
  if(!PLBR) return;
  PLBR.picking = false; PLBR.msg = '';
  if(!r || !r.ok || !r.path){
    if(r && !r.ok) PLBR.msg = r.busy ? 'A folder dialog is already open' : (r.err || 'Could not read the folder');
    return plBrPaint();   // cancel: nothing changes
  }
  await plBrLoad(r.path, false);
  if(!PLBR) return;
  if(PLBR.msg){ PLBR.path = r.path; plBrPaint(); }   // not listable (e.g. outside home): keep the pick + the server's reason
  const a = document.querySelector('[data-plbradd]'); if(a) a.focus();
}
async function plBrAdd(){
  if(!PLBR || PLBR.busy || !PLBR.path) return;
  PLBR.busy = true; PLBR.msg = ''; plBrPaint();
  const r = await plAddGo(PLBR.path);
  if(!PLBR) return;
  PLBR.busy = false;
  if(r.ok) return plBrClose();
  PLBR.msg = r.err || 'Could not add'; plBrPaint();
}
document.addEventListener('click', e => {
  if(!PLBR || !e.target.closest || !e.target.closest('#plbr')) return;
  if(e.target.id === 'plbr' || e.target.closest('[data-plbrx]')){ e.preventDefault(); return plBrClose(); }   // backdrop / ✕ / «Cancel»
  if(PLBR.busy) return;
  const g = e.target.closest('[data-plbrgo]');
  if(g) return plBrLoad(g.dataset.plbrgo, false);
  if(e.target.closest('[data-plbrup]') && PLBR.parent) return plBrLoad(PLBR.parent, false);
  if(e.target.closest('[data-plbradd]')) return plBrAdd();
  if(e.target.closest('[data-plbrpick]')) return plBrPick();
  const h = e.target.closest('[data-plbrhid]');
  if(h){ PLBR.hidden = h.checked; return plBrLoad(PLBR.path, false); }
});
document.addEventListener('keydown', e => {
  if(!PLBR) return;
  if(e.key === 'Escape'){ e.preventDefault(); e.stopPropagation(); plBrClose(); return; }   // ⚠swallowed on purpose: see traps/ui.md «48f folder browser swallows Escape while open»
  if(e.key === 'Tab') return plBrTrap(e);
  if(!e.target.closest || !e.target.closest('[data-plbrin]') || e.isComposing || e.keyCode === 229) return;   // ⚠Korean IME Enter
  if(e.key === 'Enter' && !PLBR.busy){ e.preventDefault(); plBrLoad(e.target.value, false); }
}, true);
