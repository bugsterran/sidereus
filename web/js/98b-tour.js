// First-visit coach-mark tour (six steps over the live screen). Pipeline steps are the centrepiece (accent badge, richer bubble).
//   ⚠Never scrolls (no scrollIntoView/scrollTo): a target outside the viewport counts as missing and the step is centred.
//   ⚠Tabs change only on «Next»; the tab open before the tour is restored on finish/skip.
//   ⚠Commands are copy-only — Sidereus never spawns a process (AGENTS.md rule 7).
const TOUR_STEPS = [
  {id: 'time',     tab: 'time',   sel: '#feed .tlr.tlrs'},
  {id: 'pl-what',  feat: 'pipeline', pl: 1},
  {id: 'pl-live',  tab: 'time',   sel: '#feed .tlpl', feat: 'pipeline', pl: 1},   // ⚠strip root only — its inner classes change
  {id: 'pl-start', tab: 'pipe',   sel: '[data-plstd]', also: '[data-pldnew]', feat: 'pipeline', pl: 1},
  {id: 'arch',     tab: 'struct', sel: '.archtab'},   // ⚠never calls setStrMode — the user's structure mode stays
  {id: 'done'},
];
const TOUR_KEY = 'sidereus.tourDone';   // ⚠must match sidereus/ui_prefs.py KEY_RE or the server drops it
// Pure: steps whose feature is off drop out; a step spotlights only when its target is on screen (hasSel(sel) -> bool).
function tourPlan(feats, hasSel, nSes){
  return TOUR_STEPS.filter(s => !(s.feat && feats && feats[s.feat] === false)).map(s => {
    const demo = s.id === 'time' && !nSes;
    return {id: s.id, mode: s.sel && !demo && hasSel(s.sel) ? 'spot' : 'centre', demo};
  });
}
// Pure: ?tour=1 forces (headless checks); otherwise done flag, ?tour=0 and automation (navigator.webdriver) keep it shut.
function tourShouldAuto(done, webdriver, search){
  let q = null; try{ q = new URLSearchParams(search || '').get('tour'); }catch(e){ softErr('tourQ', e); }
  if(q === '1') return true;
  return !(q === '0' || webdriver || done);
}
function tourPluginLines(dir){
  return ['/plugin marketplace add ' + (dir || T('<Sidereus folder>')), '/plugin install sidereus@sidereus'];
}
let tourI = -1, tourList = [], tourFrom = '', tourBack = null, tourDir = '', tourTimer = 0, tourSpot = null, tourCmds = [];
function tourIsOpen(){ const r = document.getElementById('tour'); return !!(r && !r.hidden); }
// First match visible in the viewport (clipped rect), else null. ⚠Visibility only — never scrolls to it.
function tourRect(sel){
  if(!sel) return null;
  const vw = innerWidth, vh = innerHeight;
  for(const el of document.querySelectorAll(sel)){
    const r = el.getBoundingClientRect(), t = Math.max(r.top, 0), l = Math.max(r.left, 0), b = Math.min(r.bottom, vh), rt = Math.min(r.right, vw);
    if(b - t >= Math.min(r.height, 20) && rt - l >= Math.min(r.width, 20) && r.width > 2 && r.height > 2) return {t, l, b, r: rt};
  }
  return null;
}
function tourTarget(st){
  let a = tourRect(st.sel);
  const b = a && st.also ? tourRect(st.also) : null;
  if(a && b) a = {t: Math.min(a.t, b.t), l: Math.min(a.l, b.l), b: Math.max(a.b, b.b), r: Math.max(a.r, b.r)};
  return a;
}
// Mini pipeline: done → running → waiting, a gate pill and a loop-back arrow. CSS-only motion (off under reduced motion).
function tourStepper(){
  // ⚠Labels must match the screen: stage names = PLG_NAMES en values, «Sent back» = the timeline legend (test_tour_js guards both).
  const nd = (c, g, l) => '<span class="tourmn ' + c + '"><b>' + g + '</b><em>' + esc(l) + '</em></span>';
  return '<div class=tourms aria-hidden=true>' + nd('ok', '✓', T('Design')) + '<i class="tourml a"></i>' + nd('run', '◉', T('Implement'))
    + '<i class="tourml g"><span class=tourgate>PASS</span></i>' + nd('wait', '·', T('Verify'))
    + '<svg class=tourlp viewBox="0 0 100 24" preserveAspectRatio="none"><path d="M100 24 C 92 2, 8 2, 0 24"/><path class=tourah d="M-3 15 L0 24 L5 16"/></svg>'
    + '<span class=tourlpt>↺ ' + esc(T('Sent back')) + '</span></div>';
}
function tourCmdHtml(cmds){
  return cmds.map((c, i) => '<div class=tourcmd><code>' + esc(c) + '</code><button type=button data-tourcp="' + i + '">' + esc(T('Copy')) + '</button></div>').join('');
}
// Bubble body for one plan entry {id, mode, demo}; dir = Sidereus code folder (state.codeDir) for the plugin line.
function tourBody(p, dir){
  const P = s => '<p>' + esc(T(s)) + '</p>';
  if(p.id === 'time' && p.demo) return {t: 'Try the demo', cmds: ['python3 -m sidereus start --demo --open'],
    h: P('AI coding-agent sessions on this computer gather here automatically') + P('No sessions yet — start the demo from a terminal to look around.')};
  if(p.id === 'time') return {t: 'Timeline', h: P('AI coding-agent sessions on this computer gather here automatically')};
  if(p.id === 'pl-what') return {t: 'Pipelines', h: tourStepper()
    + '<p class=tourval>' + esc(T('Set the order once and sessions follow it; every stage leaves its result as evidence')) + '</p>'
    + '<dl class=tourterms>' + [[T('Stage'), 'One stretch of work owned by one agent'], [T('Gate'), 'A check that must pass before the next stage'],
        [T('Sent back'), 'A failed gate sends the work back to an earlier stage']].map(x => '<dt>' + esc(x[0]) + '</dt><dd>' + esc(T(x[1])) + '</dd>').join('') + '</dl>'};
  if(p.id === 'pl-live') return {t: 'Live progress', h: (p.mode === 'spot' ? '' : tourStepper())
    + P('See the current stage and whether its gate passed here — the evidence stays in Pipelines › Tooling «Results»')
    + (p.mode === 'spot' ? '' : '<p class=tourdim>' + esc(T('No pipeline is running right now.')) + '</p>')};
  if(p.id === 'pl-start') return {t: 'Your first pipeline', h: P('Start with the standard template «Review only» (2 stages) · if writing one is hard, use «Ask AI for a draft»')};
  if(p.id === 'arch') return {t: 'Architecture', h: P('Architecture — a module diagram drawn by an agent; only edges that pass the evidence check remain')};
  return {t: 'You are set', cmds: tourPluginLines(dir),
    h: P('If you use Claude Code, these two lines install the Sidereus plugin (mailbox relay · pipeline stage marks · read-only MCP).')};
}
function tourHas(sel){ return !!tourRect(sel); }
function tourCur(){
  const p = tourList[tourI], st = TOUR_STEPS.find(s => s.id === (p && p.id));
  if(!p || !st) return null;
  const r = st.sel && !p.demo ? tourTarget(st) : null;
  return {p: Object.assign({}, p, {mode: r ? 'spot' : 'centre'}), st, r};
}
// Ring + bubble geometry; bubble goes below, above, right, left of the target, else the bottom-right corner.
function tourPlace(){
  const root = document.getElementById('tour'); if(!root) return;
  const c = tourCur(); if(!c) return;
  const ring = root.querySelector('.tourring'), bub = root.querySelector('.tourbub'), r = c.r;
  if(!!r !== !!tourSpot){ tourPaint(); return; }   // target appeared/vanished (poll re-render, tab load): rebuild for the mode
  root.classList.toggle('tourc', !r);
  if(!r){ ring.hidden = true; bub.style.left = bub.style.top = ''; return; }
  const pad = 6, vw = innerWidth, vh = innerHeight, gap = 14;
  ring.hidden = false;
  Object.assign(ring.style, {left: (r.l - pad) + 'px', top: (r.t - pad) + 'px', width: (r.r - r.l + pad*2) + 'px', height: (r.b - r.t + pad*2) + 'px'});
  const bw = bub.offsetWidth, bh = bub.offsetHeight, cx = Math.min(Math.max((r.l + r.r)/2 - bw/2, 12), vw - bw - 12);
  let x, y;
  if(r.b + pad + gap + bh <= vh - 8){ x = cx; y = r.b + pad + gap; }
  else if(r.t - pad - gap - bh >= 8){ x = cx; y = r.t - pad - gap - bh; }
  else if(r.r + pad + gap + bw <= vw - 8){ x = r.r + pad + gap; y = Math.min(Math.max(r.t, 12), vh - bh - 12); }
  else if(r.l - pad - gap - bw >= 8){ x = r.l - pad - gap - bw; y = Math.min(Math.max(r.t, 12), vh - bh - 12); }
  else { x = vw - bw - 24; y = vh - bh - 24; }
  bub.style.left = Math.round(x) + 'px'; bub.style.top = Math.round(y) + 'px';
}
function tourPaint(){
  const root = document.getElementById('tour'), c = tourCur(); if(!root || !c) return;
  const bub = root.querySelector('.tourbub'), fk = document.activeElement && bub.contains(document.activeElement) && document.activeElement.dataset
    ? (document.activeElement.dataset.tour || '') : 'next';
  const b = tourBody(c.p, tourDir), last = tourI === tourList.length - 1;
  tourSpot = c.r; tourCmds = b.cmds || [];
  bub.className = 'tourbub' + (c.st.pl ? ' tourpl' : '');
  bub.innerHTML = '<div class=tourhd><span class=tourn>' + (tourI + 1) + ' / ' + tourList.length + '</span>'
      + (c.st.pl ? '<span class=tourbdg>★ ' + esc(T('Key feature')) + '</span>' : '') + '</div>'
    + '<h3 id=tourt>' + esc(T(b.t)) + '</h3>' + b.h + tourCmdHtml(tourCmds)
    + '<div class=tourft><button type=button class=tourlk data-tour=skip>' + esc(T('Skip')) + '</button>'
    + '<span class=tourdots aria-hidden=true>' + tourList.map((x, i) => '<i' + (i === tourI ? ' class=on' : '') + '></i>').join('') + '</span>'
    + (tourI > 0 ? '<button type=button class=tourbk data-tour=prev>' + esc(T('Back')) + '</button>' : '')
    + '<button type=button class=tourgo data-tour=next>' + esc(T(last ? 'Get started' : 'Next')) + '</button></div>';
  tourPlace();
  const f = bub.querySelector('[data-tour="' + fk + '"]') || bub.querySelector('[data-tour=next]');
  if(f) f.focus({preventScroll: true});
}
function tourGo(i, fwd){
  if(i < 0 || i >= tourList.length) return;
  tourI = i;
  const st = TOUR_STEPS.find(s => s.id === tourList[i].id);
  if(fwd && st && st.tab && mainView !== st.tab) try{ setMainView(st.tab); }catch(e){ softErr('tourTab', e); }
  tourSpot = undefined;   // force a full paint for the new step
  tourPaint();
}
function tourOpen(i){
  if(ISPOP || ISWP || ISBP) return;
  try{ if(popIsOpen('kbhelp')) kbHelpClose(false); }catch(e){ softErr('tourKb', e); }
  try{ cfgClose(); }catch(e){ softErr('tourCfg', e); }
  try{ for(const q of UIPOPS) if(popIsOpen(q.id)) q.close(false); }catch(e){ softErr('tourPops', e); }
  let root = document.getElementById('tour');
  if(!root){
    root = document.createElement('div'); root.id = 'tour';
    root.setAttribute('role', 'dialog'); root.setAttribute('aria-modal', 'true'); root.setAttribute('aria-labelledby', 'tourt');
    root.innerHTML = '<div class=tourblk></div><div class=tourring hidden></div><div class=tourbub tabindex=-1></div>';
    root.addEventListener('click', tourClick);
    document.body.appendChild(root);
  }
  if(!tourIsOpen() || tourI < 0){ tourFrom = mainView; tourBack = document.activeElement; }
  tourList = tourPlan(FEATS, tourHas, (SESS || []).length);
  root.hidden = false;
  clearInterval(tourTimer); tourTimer = setInterval(tourPlace, 400);   // polls re-render targets every 2.5s
  tourGo(Math.max(0, Math.min(i || 0, tourList.length - 1)), false);
}
function tourEnd(){
  const root = document.getElementById('tour'); if(!root || root.hidden) return;
  root.hidden = true; clearInterval(tourTimer); tourTimer = 0; tourI = -1;
  try{ UIS.setItem(TOUR_KEY, '1'); }catch(e){ softErr('tourDone', e); }
  if(tourFrom && mainView !== tourFrom) try{ setMainView(tourFrom); }catch(e){ softErr('tourBackTab', e); }
  if(tourBack && tourBack.isConnected && tourBack.focus) tourBack.focus({preventScroll: true});
  tourBack = null;
}
function tourCopy(btn, text){
  const ok = () => { btn.textContent = T('Copied'); setTimeout(() => { if(btn.isConnected) btn.textContent = T('Copy'); }, 1400); };
  try{ navigator.clipboard.writeText(text).then(ok, e => softErr('tourCopy', e)); }catch(e){ softErr('tourCopy', e); }
}
function tourClick(e){
  const cp = e.target.closest('[data-tourcp]');
  if(cp){ const c = tourCmds[+cp.dataset.tourcp]; if(c) tourCopy(cp, c); return; }
  const b = e.target.closest('[data-tour]'); if(!b) return;
  const a = b.dataset.tour;
  if(a === 'skip') tourEnd();
  else if(a === 'prev') tourGo(tourI - 1, false);
  else if(tourI >= tourList.length - 1) tourEnd();
  else tourGo(tourI + 1, true);
}
// ⚠Window capture runs before the document-level handlers (08-ui-kit Esc, 98-a11y shortcuts, ⌘K) — the tour owns the keyboard.
addEventListener('keydown', e => {
  if(!tourIsOpen() || e.isComposing) return;
  const bub = document.querySelector('#tour .tourbub'), k = e.key;
  e.stopPropagation();
  if(k === 'Escape'){ e.preventDefault(); tourEnd(); return; }
  if(k === 'ArrowRight'){ e.preventDefault(); if(tourI < tourList.length - 1) tourGo(tourI + 1, true); return; }
  if(k === 'ArrowLeft'){ e.preventDefault(); tourGo(tourI - 1, false); return; }
  if(k === 'Tab'){
    e.preventDefault();
    const fs = [...bub.querySelectorAll('button')], n = fs.length, j = fs.indexOf(document.activeElement);
    if(n) fs[(j < 0 ? 0 : j + (e.shiftKey ? n - 1 : 1)) % n].focus({preventScroll: true});
    return;
  }
  if(!bub.contains(e.target)) e.preventDefault();
}, true);
addEventListener('focusin', e => {
  if(!tourIsOpen()) return;
  const root = document.getElementById('tour');
  if(!root.contains(e.target)){ const f = root.querySelector('[data-tour=next]'); if(f) f.focus({preventScroll: true}); }
}, true);
addEventListener('resize', () => { if(tourIsOpen()) tourPlace(); });
// Called once by 95-poll.js when the first state lands (dir = state codeDir for the plugin line).
function tourMaybe(dir){
  if(dir) tourDir = String(dir);
  if(ISPOP || ISWP || ISBP) return;
  let done = '';
  try{ done = UIS.getItem(TOUR_KEY) || ''; }catch(e){ softErr('tourRead', e); }
  if(tourShouldAuto(!!done, !!navigator.webdriver, location.search)) setTimeout(() => tourOpen(0), 600);   // let the first paint settle
}
