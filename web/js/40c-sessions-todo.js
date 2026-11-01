// Session to-do list (server store DATA_DIR/todo/, recorded by the session via the sidereus MCP tool): «To-do n» chip on the identity row (40ba sessIdRow)
// and an inline layer under the row (40b sessRowHtml). Server: state `todo` {cwd: {o, w, d}} · GET /api/todo · POST /api/todo/add|set.
// ⚠Item text is the person's request label from the store: esc() only, never T() (user data) — tests/test_todo_js.py.
let STODO = null;              // state `todo` (absent when the feature is off ⇒ no chip, no layer)
const STODO_OPEN = new Set();  // open layers by row key (the list redraws every poll, so open state lives here like wfFold)
const STODO_DAY = new Set();   // row keys showing «By day»
const STODO_DATA = {};         // cwd → {sig, at, items, days, max, err, busy}
const STODO_MAX = 200;         // add-box limit until GET /api/todo reports `max` (server TEXT_MAX)
const STODO_SENDING = new Set(); // row keys with an add in flight (a second Enter must not post twice)
const STODO_DRAFT = {};        // row key → add-box text (restored after a morph reused the input for another row)
function stodoSet(v){ STODO = v && typeof v === 'object' ? v : null; }
function stodoCnt(x){
  const c = STODO && x && x.cwd ? STODO[x.cwd] : null;
  return c ? {o: +c.o || 0, w: +c.w || 0, d: +c.d || 0} : null;
}
function stodoKey(x){ return (x.sid || '') + '|' + (x.cwd || ''); }
// Chip count = open + in progress; done-only lists still get the chip (n = 0) so the layer stays reachable.
function stodoChip(x){
  const c = stodoCnt(x);
  if(!c || c.o + c.w + c.d <= 0) return '';
  const k = stodoKey(x), n = c.o + c.w;
  return '<span class="stdc' + (STODO_OPEN.has(k) ? ' on' : '') + (c.w ? ' w' : '') + '" data-todo="' + esc(k) + '" title="'
    + esc(TV({msg: 'To-do: {o} open · {w} in progress · {d} done — click to show the list', vars: {o: c.o, w: c.w, d: c.d}})) + '">'
    + esc(TV({msg: 'To-do {n}', vars: {n: n}})) + '</span>';
}
// In progress first, then open, then done; file order inside each group.
function stodoOrder(items){
  const rk = s => (s === '~' ? 0 : (s === 'x' ? 2 : 1));
  return (items || []).map((it, n) => ({it, n})).sort((a, b) => rk(a.it.s) - rk(b.it.s) || a.n - b.n).map(p => p.it);
}
function stodoItemsHtml(items, x){
  return stodoOrder(items).map(it => {
    const w = it.s === '~', d = it.s === 'x';
    // ⚠«Working» comes only from the session's `start` (state "~"); the state label beside it is the row's live state, never used to infer it.
    return '<label class="stdi' + (w ? ' w' : '') + (d ? ' d' : '') + '"><input type=checkbox class=stdx data-tdi="' + esc(it.i) + '" data-tdh="' + esc(it.h) + '"'
      + (d ? ' checked' : '') + '><span class=stdt>' + esc(it.t) + '</span>'
      + (w ? ' <span class=stdw>' + esc(T('Working')) + '</span> <span class=stds>' + esc(sessLabel(x)) + '</span>' : '') + '</label>';
  }).join('');
}
function stodoDaysHtml(days){
  const kinds = [['added', n => TV({msg: 'Added {n}', vars: {n: n}})], ['started', n => TV({msg: 'Started {n}', vars: {n: n}})],
    ['done', n => TV({msg: 'Done {n}', vars: {n: n}})]];
  const ds = (days || []).slice().sort((a, b) => String(b.day).localeCompare(String(a.day)));
  if(!ds.length) return '<div class=stdn>' + esc(T('No dated entries yet.')) + '</div>';
  return ds.map(d => '<div class=stdd><div class=stddh>' + esc(d.day) + '</div>'
    + kinds.filter(k => (d[k[0]] || []).length).map(k => '<div class="stddk ' + k[0] + '"><span class=stddl>'
      + esc(k[1](d[k[0]].length)) + '</span>'
      + d[k[0]].map(t => '<div class=stddi>' + esc(t) + '</div>').join('') + '</div>').join('') + '</div>').join('');
}
// Layer under the row ('' when closed or the feature is off). Fixed children (head · add box · body) keep the input node across morphs.
function stodoLayer(x){
  const k = stodoKey(x), c = stodoCnt(x);
  if(!c || c.o + c.w + c.d <= 0 || !STODO_OPEN.has(k)) return '';
  const sig = c.o + ',' + c.w + ',' + c.d, dt = STODO_DATA[x.cwd];
  if(!dt || (!dt.busy && (dt.sig !== sig || Date.now() - dt.at > 30000))) Promise.resolve().then(() => stodoLoad(x.cwd, sig));
  const day = STODO_DAY.has(k);
  const body = !dt || (!dt.items && !dt.err) ? '<div class=stdn>' + esc(T('Loading…')) + '</div>'
    : dt.err ? '<div class=stdn>' + esc(T('Could not read the to-do list')) + '</div>'
    : (day ? stodoDaysHtml(dt.days) : stodoItemsHtml(dt.items, x));
  return '<div class=stdl data-todok="' + esc(k) + '" title=""><div class=stdhd><span class=stdh>' + esc(T('To-do')) + '</span>'
    + '<button type=button class="stdb' + (day ? ' on' : '') + '" data-tdday="' + esc(k) + '">' + esc(T('By day')) + '</button></div>'
    + '<input type=text class=stda data-tdadd="' + esc(k) + '" maxlength=' + ((dt && +dt.max > 0) ? +dt.max : STODO_MAX) + ' placeholder="' + esc(T('Add a to-do — Enter to save')) + '">'
    + '<div class=stdbody>' + body + '</div></div>';
}
function stodoRedraw(){
  const box = document.getElementById('sess');
  if(box) box._sh = '';
  sessHover = false; sessDirty = false; buildSessions();
}
async function stodoLoad(cwd, sig){
  const dt = STODO_DATA[cwd] || (STODO_DATA[cwd] = {});
  if(dt.busy) return;
  dt.busy = true;
  try{ const j = await getJSON('/api/todo?cwd=' + encodeURIComponent(cwd), {timeout: 20000}); dt.items = j.items || []; dt.days = j.days || []; dt.max = +j.max || STODO_MAX; dt.err = false; }
  catch(e){ dt.err = true; softErr('todo', e); }
  finally{ dt.busy = false; dt.sig = sig; dt.at = Date.now(); }
  stodoRedraw();
}
function stodoCwd(k){ return String(k).slice(String(k).indexOf('|') + 1); }
// Resolves true on success, false on failure; `ok` runs before the redraw so a cleared draft is not put back.
function stodoPost(url, body, cwd, ok){
  return postJSON(url, body).then(() => { if(ok) ok(); return true; }, e => {
    // ⚠The server's reason (e.g. text too long) is shown as-is, never through T(); no status = the request never arrived.
    note(e && e.status === 409 ? T('The to-do list changed — reloaded')
      : e && e.status && e.message ? T('Could not save the to-do') + ': ' + e.message : T('Could not save the to-do — check the server'));
    return false;
  }).finally(() => { const dt = STODO_DATA[cwd]; if(dt) dt.sig = ''; stodoRedraw(); });
}
// Delegated from sessClick (40b) before the row's work-log click; true = handled.
function stodoClick(e){
  const t = e.target, cl = s => t.closest && t.closest(s);
  const chip = cl('.stdc[data-todo]');
  if(chip){
    e.stopPropagation();
    const k = chip.getAttribute('data-todo');
    if(STODO_OPEN.has(k)) STODO_OPEN.delete(k); else STODO_OPEN.add(k);
    stodoRedraw();
    return true;
  }
  if(!cl('.stdl')) return false;
  e.stopPropagation();
  const dy = cl('[data-tdday]');
  if(dy){ const k = dy.getAttribute('data-tdday'); if(STODO_DAY.has(k)) STODO_DAY.delete(k); else STODO_DAY.add(k); stodoRedraw(); return true; }
  const cb = t.tagName === 'INPUT' && t.classList.contains('stdx') ? t : null;
  if(cb){
    const cwd = stodoCwd(cl('.stdl').getAttribute('data-todok'));
    stodoPost('/api/todo/set', {cwd: cwd, i: +cb.getAttribute('data-tdi'), h: cb.getAttribute('data-tdh'), s: cb.checked ? 'x' : ' '}, cwd);
  }
  return true;
}
function stodoInput(e){
  const t = e.target;
  if(t && t.classList && t.classList.contains('stda')) STODO_DRAFT[t.getAttribute('data-tdadd')] = t.value;
}
// Enter in the add box sends at once (typed by the person, no confirm).
function stodoKeydown(e){
  const t = e.target;
  if(e.key !== 'Enter' || e.isComposing || !t || !t.classList || !t.classList.contains('stda')) return;
  e.preventDefault(); e.stopPropagation();
  const k = t.getAttribute('data-tdadd'), raw = t.value, text = raw.trim();
  if(!text || STODO_SENDING.has(k)) return;
  const cwd = stodoCwd(k);
  // ⚠Clear only after the server saved it: on failure the typed text (and its draft) stays in the box.
  STODO_DRAFT[k] = raw; STODO_SENDING.add(k);
  stodoPost('/api/todo/add', {cwd: cwd, text: text}, cwd, () => {
    if(STODO_DRAFT[k] === raw) delete STODO_DRAFT[k];   // text typed meanwhile is kept
    if(t.getAttribute('data-tdadd') === k && t.value === raw) t.value = '';   // ⚠morph may have moved this input to another row
  }).finally(() => STODO_SENDING.delete(k));
}
// ⚠morphHtml reuses inputs by position: put each row's own draft back after a redraw.
function stodoAfter(box){
  for(const el of box.querySelectorAll('input.stda[data-tdadd]')){
    const v = STODO_DRAFT[el.getAttribute('data-tdadd')] || '';
    if(el.value !== v) el.value = v;
  }
}
