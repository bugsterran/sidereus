// ── Saved views ────────────────────────────────────────────────────────────────
// ★Why: filters have many layers (mode · room · filter row · search · grouping · session idle/unpushed · todo bar ·
// timeline range/interval). Recreating the same combination took six
// manual clicks each time. Name the combination and restore it in one go.
// ⚠Only **filter/display state** is stored — open modals · scroll position · split (wtLayout/wtFr) ·
// alarm window size/open · chosen session tabs are not. People are surprised when things they did not choose change.
// ⚠Restore **sets state, then calls the existing render functions** — changing only DOM values desyncs screen and state.
// ⚠`v` is a format tag. Bump it when stored items change. Old views are not silently ignored; a one-line notice is shown.
const VW_KEY = 'mbViews', VW_V = 1, VW_MAX = 12, VW_NAME_MAX = 60;   // name cap: the list row ellipsizes, the full name is only in storage
let vwOpen = false;
function vwLoad(){ try{ const a = JSON.parse(UIS.getItem(VW_KEY) || '[]');
                        return Array.isArray(a) ? a : []; }catch(e){ return []; } }
function vwStore(a){ lsSetJson(VW_KEY, a); }
function vwSnap(){
  return { mv:mainView, place:place, filter:filter, q:q,
           idle:idleMin, git:gitFil, st:stFil, todo:todoOpen,
           tlH:tlHours, tlA:tlAuto, tlRp:tlRpSpeed };   // fvH/fvK/fvG in old views are ignored (failure tab removed 2026-09-23)
}
function vwApply(rec){
  if(!rec || rec.v !== VW_V || !rec.s){ note(T('This view is in an old format and could not be restored')); return; }
  const s = rec.s;
  place = s.place || 'all'; setFilter(s.filter); q = s.q || '';   // an old view's byThread key is ignored (thread grouping removed)
  // A room that no longer exists falls back to the room list
  if(place.indexOf('room:') === 0){
    const rn = place.slice(5);
    if(!((ROOMS||{})[rn] || MSGS.some(m => m.room === rn))) place = 'all';
  }
  shownN = 10;
  idleMin  = IDLE_STEPS.includes(s.idle) ? s.idle : 0;
  gitFil   = GIT_STEPS.includes(s.git) ? s.git : '';
  stFil    = ['','ask','abort','hot','blocked'].includes(s.st) ? s.st : '';
  todoOpen = !!s.todo;
  saveFil();
  // Timeline settings also go into **their own storage keys** — on refresh those keys are the source of truth, otherwise it reverts
  if(isFinite(s.tlH) && s.tlH >= 0.5 && s.tlH <= 168){
    tlHours = s.tlH; lsSet('mbTlHours', tlHours); }
  if(TL_EVERY.some(x => x[0] === s.tlA)){ tlAuto = s.tlA; lsSet('mbTlAuto', tlAuto); }
  if(TL_RSP.some(x => x[0] === s.tlRp)){ tlRpSpeed = s.tlRp; lsSet('mbTlRp', tlRpSpeed); }
  const qb = document.getElementById('q'); if(qb) qb.value = q;
  buildRooms(); buildTabs(); buildPeople(); buildTodo(); buildFilters(); buildSessions(); full();
  toBottom(false);
  setMainView(s.mv || 'chat');          // Mode views are drawn only through this one path (no second copy)
}
// «+ Save» only when something differs from the plain room list — saving the default combination is a no-op view.
function vwHasState(){ return place !== 'all' || filter !== 'all' || !!q || !!idleMin || !!gitFil || !!stFil || !!todoOpen; }
function vwSaveVis(){ const s = document.getElementById('vwsave'); if(s) s.hidden = !vwHasState(); }
function vwPaint(){
  const b = document.getElementById('vwb'), p = document.getElementById('vwpop');
  vwSaveVis();
  if(!b || !p) return;
  const a = vwLoad();
  b.hidden = !a.length;          // An empty dropdown looks broken — hide it entirely if there are none
  if(!a.length){ vwOpen = false; p.hidden = true; return; }
  p.hidden = !vwOpen;
  if(!vwOpen) return;
  p.innerHTML = a.map((it, i) =>
    '<div class=vwi data-i="'+i+'" title="'+esc(T('Go back to this combination'))+'"><span class=vwn>'
    + esc(it.n || T('(unnamed)')) + '</span><i class=vwx data-x="'+i+'" title="'+esc(T('Delete this view'))+'">✕</i></div>').join('');
  p.querySelectorAll('.vwi').forEach(el => el.onclick = (e) => {
    if(e.target.closest('.vwx')) return;
    const it = vwLoad()[+el.dataset.i];
    vwOpen = false; vwPaint();
    if(it) vwApply(it);
  });
  p.querySelectorAll('.vwx').forEach(el => el.onclick = (e) => {
    e.stopPropagation();
    const arr = vwLoad(), i = +el.dataset.x, it = arr[i];
    if(!it) return;
    if(!confirm(T('Delete view “{n}”?').replace('{n}', () => (it.n||'')))) return;
    arr.splice(i, 1); vwStore(arr); vwPaint();
  });
}
const vwb = document.getElementById('vwb');
if(vwb) vwb.onclick = (e) => { e.stopPropagation(); vwOpen = !vwOpen; vwPaint(); };
const vwsave = document.getElementById('vwsave');
if(vwsave) vwsave.onclick = () => {
  const name = (prompt(T('Name for the current filter combination?'), '') || '').trim().slice(0, VW_NAME_MAX);
  if(!name) return;
  const arr = vwLoad(), at = arr.findIndex(x => x.n === name);
  // Over the cap, **do not drop silently** — write in one line what to do
  if(at < 0 && arr.length >= VW_MAX){
    note(T('Already {n} saved views — delete one and save again').replace('{n}', VW_MAX)); return; }
  if(at >= 0 && !confirm(T('A view with this name exists — overwrite it?'))) return;
  const rec = {v:VW_V, n:name, s:vwSnap()};
  if(at >= 0) arr[at] = rec; else arr.push(rec);
  vwStore(arr); vwOpen = false; vwPaint();
  note((at >= 0 ? T('Overwrote view “{n}”') : T('Saved view “{n}”')).replace('{n}', () => name));
};
// Close on outside click. ⚠An element removed from the DOM by a redraw is not 'outside' (same trap as the alarm window)
addEventListener('click', (e) => {
  if(!vwOpen) return;
  if(!document.contains(e.target)) return;
  const p = document.getElementById('vwpop');
  if(p && !p.contains(e.target)){ vwOpen = false; vwPaint(); }
});
vwPaint();
