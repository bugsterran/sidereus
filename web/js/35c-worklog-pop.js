// ★One popup helper for the work log, session diff and branch file diff (2026-09-23 user: regular windows, several at once).
//   Name per item -> re-click focuses that window; new ones cascade 30px and wrap after 8. POPS drops closed windows.
const POPS = {};
function popName(pre, s){ return pre + String(s || '').replace(/[^A-Za-z0-9]/g, '_').slice(-120); }
// ★2026-09-30 popups opened top-left on dual monitors ⇒ left/top are screen coords of the primary display, so place over the Sidereus window (same monitor), centred, cascading 30px.
function popFeat(w, h, n){
  const W = Math.min(screen.availWidth - 40, w), H = Math.min(screen.availHeight - 40, h);
  const x = window.screenX + Math.max(0, (window.outerWidth - W) / 2) + (n || 0) * 30;
  const y = window.screenY + Math.max(0, (window.outerHeight - H) / 2) + (n || 0) * 30;
  return 'width=' + W + ',height=' + H + ',left=' + Math.round(x) + ',top=' + Math.round(y);
}
function popOpen(url, name, w, h){
  for(const k in POPS){ try{ if(POPS[k].closed) delete POPS[k]; }catch(e){ delete POPS[k]; } }
  if(POPS[name]){ try{ POPS[name].focus(); }catch(e){} return POPS[name]; }
  const n = Object.keys(POPS).length % 8;
  const win = window.open(url, name, popFeat(w, h, n) + ',resizable=yes,scrollbars=yes');
  if(!win){ popBlocked(url, name); return null; }
  POPS[name] = win;
  try{ win.focus(); }catch(e){}
  return win;
}
// ⚠Blocked popup must not fail silently: a toast with a link the user can click (a user gesture the blocker allows).
function popBlocked(url, name){
  const box = document.getElementById('toasts');
  if(!box){ alert(T('Popup blocked — allow popups for this site.')); return; }
  const el = document.createElement('div');
  el.className = 'toast tnote';
  el.innerHTML = esc(T('Popup blocked — allow popups for this site.')) + ' <a href="' + esc(url)
    + '" target="' + esc(name) + '">' + esc(T('Open in a new window')) + '</a>';
  el.onclick = e => { if(!e.target.closest('a')) el.remove(); else setTimeout(() => el.remove(), 0); };
  box.appendChild(el);
  setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 320); }, 9000);
}
// Work items join an open work popup as tabs; Shift+click keeps a separate window. WKHOST = last used host, WKAT = moment windows.
let WKHOST = '', WKSHIFT = 0;
const WKAT = {};
// ⚠Callers pass no event, so the modifier comes from the last click/Enter (capture phase runs before their handler).
document.addEventListener('click', e => { WKSHIFT = e.shiftKey ? Date.now() : 0; }, true);
document.addEventListener('keydown', e => { if(e.key === 'Enter') WKSHIFT = e.shiftKey ? Date.now() : 0; }, true);
// Which open work popup takes this item: its own window, else one already holding the tab, else the last host.
// ⚠A moment (&at=) window is never a host: its first tid reads the frozen window (workUrl), a live tab of it would too.
function wkHostOf(cwd, tid, nm, solo){
  const ok = k => { try{ const w = POPS[k]; return k.indexOf('sidereus_work_') === 0 && !WKAT[k] && !!w && !w.closed && typeof w.wkReopen === 'function'; }catch(e){ return false; } };
  const ks = Object.keys(POPS).filter(ok);
  if(ks.includes(nm)) return nm;
  if(solo || !ks.length) return '';
  const has = ks.find(k => { try{ return typeof POPS[k].wkHasTab === 'function' && POPS[k].wkHasTab(cwd, tid); }catch(e){ return false; } });
  return has || (ks.includes(WKHOST) ? WKHOST : ks[ks.length - 1]);
}
// `at` (epoch s, optional) = open the session log at that moment instead of its live tail (retro failure rows) — always its own window.
function wkPopup(cwd, tid, at){
  const a = at > 0 ? Math.round(at) : 0;
  const nm = popName('sidereus_work_', tid + (a ? '@' + a : ''));
  const h = a ? '' : wkHostOf(cwd, tid, nm, Date.now() - WKSHIFT < 1500);
  if(h){
    try{ POPS[h].wkReopen(cwd, tid); POPS[h].focus(); WKHOST = h; return POPS[h]; }
    catch(e){ softErr('wkReopen', e); }   // cross-window call failed -> a new window below, never nothing
  }
  const w = popOpen('/work?cwd=' + encodeURIComponent(cwd) + '&tid=' + encodeURIComponent(tid) + (a ? '&at=' + a : ''), nm, 1100, 800);
  if(w){ if(a) WKAT[nm] = 1; else WKHOST = nm; }
  return w;
}
// ★Name kept but meaning changed: closes **the current window** (before, the single modal was all there was).
function diffClose(){
  if(ISPOP){ window.close(); return; }        // in a popup, close this window
  diffOpen=''; diffRepo=''; diffData=null; diffPick=-1; fullOn=false; diffScope='all';
  buildSessions();
}

function repoHue(path){
  const n = path.split('/').pop();
  let h = 0;
  for(let i=0;i<n.length;i++) h = (h*31 + n.charCodeAt(i)) % 7;
  return h;                      // 0-6 — 7 colors are defined in CSS
}
function diffShow(){
  // ★One popup window = one diff. One set of globals suffices — opening several windows is done
  //   **by the browser**, and each document has its own globals.
  const row = tlLiveOf(diffOpen) || (SESS||[]).find(x=>x.cwd===diffOpen) || {};   // Claude row first: a Gemini row has no repos/branch
  const repos = (row.repos && row.repos.length) ? row.repos : (diffOpen ? [diffOpen] : []);
  const ttl = row.project ? TV({msg: '{p} changes', vars: {p: row.project}}) : T('Session changes');
  document.getElementById('dttl').textContent = ttl;
  document.getElementById('dsub').textContent = diffRepo + (row.branch && diffRepo===row.cwd ? ' · '+row.branch : '');
  if(ISPOP) document.title = ttl + ' — ' + PAGE_NAME;     // several windows, so the title tells them apart
  const tabs = repos.length > 1
    ? '<div class=drt>' + repos.map(r =>
        '<span class="dtb c'+repoHue(r)+(r===diffRepo?' on':'')+'" data-repo="'+esc(r)+'" title="'+esc(r)+'">'
        + esc(r.split('/').pop()) + '</span>').join('') + '</div>'
    : '';
  const SC = [['all','All'],['commit','Commits only'],['work','Uncommitted']];   // ⚠capital 'Uncommitted' is its own key; lowercase 'uncommitted' belongs to the branch chips
  const onCommit = String(diffScope).indexOf('c:') === 0;
  const noUp = diffData && diffData.ok && diffData.hasUp === false;
  // Real buttons; without an upstream «All»/«Commits only» are disabled and the tooltip says why.
  // ⚠No upstream: the body is the worktree diff, so «Uncommitted» is the active one (not the disabled «All»).
  const scOn = noUp && (diffScope === 'all' || diffScope === 'commit') ? 'work' : diffScope;
  const scb = '<div class=dsc>' + SC.map(([k,l]) => { const off = noUp && k!=='work';
      return '<button type=button class="dscb'+(scOn===k?' on':'')+(off?' dim':'')+'" data-scope="'+k+'"'+(off?' disabled':'')+' title="'
      + esc((off ? T('No upstream — only uncommitted changes can be shown') + '\n' : '') + T(k==='all' ? 'Everything not on the remote yet — commits + uncommitted'
          : (k==='commit' ? 'Only what is committed but not pushed' : 'Only what is not committed yet')))
      + '">'+esc(T(l))+'</button>'; }).join('')
    + (noUp ? '<span class=dsn>'+T('No upstream — only uncommitted changes can be shown')+'</span>' : '')
    + (onCommit ? '<span class=dsn>'+T('Viewing one commit — click a tab above to go back')+'</span>' : '')
    + (String(diffScope).indexOf('b:') === 0 ? '<span class=dsn>'+esc(TV({msg: 'Since the rail baseline {n} — pick a scope above to go back', vars: {n: String(diffScope).slice(2, 9)}}))+'</span>' : '') + '</div>';
  document.getElementById('dbody').innerHTML = tabs + scb + diffBody(diffData);
  rvnPaint();   // review popup (&rvsid): line comments are re-inserted after every full re-render
}

// ★Async callbacks must update **that window (w), not the globals** — if a human clicked another window
//   while the response was in flight, the globals already belong to it (with one window this distinction wasn't needed).
function loadRepo(repo){
  diffRepo = repo; diffData = null; diffPick = -1; fullOn = false; diffShow();
  if(dfWant) dfNew = [repo, dfWant];   // keep the rail's file through later reloads of the same repo
  const nw = (dfNew && dfNew[0] === repo && (diffScope === 'work' || String(diffScope).indexOf('b:') === 0)) ? '&new=' + encodeURIComponent(dfNew[1]) : '';
  getJSON('/api/git/diff?cwd='+encodeURIComponent(repo)+'&scope='+encodeURIComponent(diffScope)
        +'&pw='+encodeURIComponent(dfPW) + nw)
    // ★Rendering is moved **outside catch** (measured 2026-09-04). `.then(...).catch(...)` also catches exceptions thrown
    //   inside then, so what diffShow() threw was disguised as «Could not fetch — check the server»
    //   and looked **like a network problem** (the real cause was agLang being undefined).
    .then(j => { if(diffRepo===repo){ diffData=j;
                   if(dfWant && j && j.ok){ diffPick = splitDiff(j.diff || '').findIndex(f => f.path === dfWant); dfWant = ''; } } },
          () => { if(diffRepo===repo){ diffData={ok:false,msg:T('Could not fetch — check the server')}; } })
    .then(() => { if(diffRepo===repo) diffShow(); });
}
let dfWant = '';   // popup `file` param: pick this path once the first diff arrives (timeline git rail)
let dfNew = null;  // [repo, path]: the rail file sent as `new=` so an untracked one appears as an all-added patch
function loadDiff(cwd, file, scope, rvsid){   // rvsid: opened from the review drawer → line-comment gutter (88e)
  // ★Opens **a separate browser window** (not an
  //   in-page popup). Window size, moving, sending to another monitor, opening several are
  //   handled by the OS. The window name is the cwd, so clicking the same session badge again brings
  //   that window forward instead of a new one (browser rule). Other sessions have different names and open another window.
  if(ISPOP){   // called inside the popup (repo switch etc.) — handled in this window
    diffOpen = cwd;
    // ⚠repos can be [] (not a git repo / nothing touched) — `([]||[cwd])[0]` is undefined, fetched as cwd=undefined.
    const rp = (tlLiveOf(cwd) || {}).repos;   // Claude row: a Gemini row at the same cwd has repos []
    loadRepo((rp && rp.length) ? rp[0] : cwd);
    return;
  }
  const url = '/diff?cwd=' + encodeURIComponent(cwd) + (file ? '&scope=' + encodeURIComponent(scope || 'work') + '&file=' + encodeURIComponent(file) : '')
    + (rvsid ? '&rvsid=' + encodeURIComponent(rvsid) : '');
  const nm = 'sidereus_diff_' + cwd.replace(/[^A-Za-z0-9]/g, '_');
  if(file && POPS[nm]) try{ if(!POPS[nm].closed) POPS[nm].location.href = url; }catch(e){}   // popOpen only focuses an open window
  popOpen(url, nm, 1700, 1100);
}
// diff operations — meaningful only inside the popup window (the main view has no diff)
document.addEventListener('click', e => {
  if(e.target.closest && e.target.closest('#dx')){ diffClose(); return; }
  const tb = e.target.closest && e.target.closest('.dtb[data-repo]');
  if(tb){ loadRepo(tb.getAttribute('data-repo')); return; }
  if(e.target.closest && e.target.closest('.dwfull')){ toggleFull(); return; }
  if(e.target.closest && e.target.closest('.dwsbs')){ sbsOn = !sbsOn; diffShow(); return; }
  const nvb = e.target.closest && e.target.closest('[data-dnav]');
  if(nvb){ dfNav(nvb, +nvb.getAttribute('data-dnav')); return; }
  if(e.target.closest && e.target.closest('[data-dhist]')){ dfHistOpen = !dfHistOpen; lsSet('sidereus.dfhist', dfHistOpen ? '1' : '0'); diffShow(); return; }
  const pwb = e.target.closest && e.target.closest('.dfc[data-pw]');
  if(pwb){ dfPW = pwb.getAttribute('data-pw'); if(diffRepo) loadRepo(diffRepo); return; }
  const df = e.target.closest && e.target.closest('.dfc[data-dfil]');
  if(df){ dfFil = df.getAttribute('data-dfil'); diffShow(); return; }
  const da = e.target.closest && e.target.closest('.dfc[data-dall]');
  if(da){
    // ★Uses **the full list collected by the render**, not the DOM — children of already-collapsed directories aren't in the DOM, so
    //   scanning the screen alone doesn't collapse everything in one click, needing several (which looks broken).
    const want = da.getAttribute('data-dall') === 'shut';
    for(const k of dfAllDirs){ if(want) dfShut.add(k); else dfShut.delete(k); }
    diffShow();
    return;
  }
  const dd = e.target.closest && e.target.closest('.dfd[data-dir]');
  if(dd){
    const k = dd.getAttribute('data-dir');
    if(dfShut.has(k)) dfShut.delete(k); else dfShut.add(k);
    diffShow(); return;
  }
  const sc = e.target.closest && e.target.closest('.dscb[data-scope]:not([disabled])');
  if(sc){ diffScope = sc.getAttribute('data-scope'); if(diffRepo) loadRepo(diffRepo); return; }
  const cm = e.target.closest && e.target.closest('.dcm[data-sha]');
  if(cm){
    const sha = cm.getAttribute('data-sha');
    // clicking the same commit again clears it — back to the full scope
    diffScope = (diffScope === 'c:' + sha) ? 'all' : ('c:' + sha);
    diffPick = -1; dfShut.clear();
    if(diffRepo) loadRepo(diffRepo);
    return;
  }
  const fi = e.target.closest && e.target.closest('.dfi[data-fi]');
  if(fi){ diffPick = parseInt(fi.getAttribute('data-fi'), 10); fullOn = false; diffShow(); return; }
  // ★'click outside = close' was removed — a floating window exists so you can use what is outside it.
});
document.addEventListener('keydown', e => {
  // in the popup, Esc closes that window. The main view has no diff anymore.
  if(e.key === 'Escape' && strPop){ strPopClose(); return; }   // the structure code popup follows the same rule
  if(e.key === 'Escape' && ISPOP) diffClose();
});
// ★On window resize the drawer height is re-measured (fixed vh was dropped, so it is fitted here).
//   ⚠Measuring once is wrong — at the resize event layout isn't finished yet and an intermediate value is caught
//   (measured 2026-09-03: enlarged to 1400px and 139px remained below). Measure once more a bit later.
window.addEventListener('resize', () => {
  try{ tlFit(); }catch(e){ softErr('tlFit', e); }
  setTimeout(() => { try{ tlFit(); }catch(e){ softErr('tlFit', e); } }, 150);
  setTimeout(() => { try{ tlFit(); }catch(e){ softErr('tlFit', e); } }, 450);
});
// ★Width resizing — **no redraw** while dragging. Replacing innerHTML removes the handle being dragged and
//   breaks pointer events. Save once after it ends; the screen only touches style.
// received-instruction height resizing — no redraw while dragging (a re-render removes the handle and breaks it)
document.addEventListener('pointerdown', e => {
  const g = e.target.closest && e.target.closest('.agpg');
  if(!g) return;
  const pb = g.previousElementSibling;
  if(!pb) return;
  const y0 = pb.getBoundingClientRect().top;
  e.preventDefault();
  document.body.classList.add('rowdrag');
  dragTrack(e, g, ev => {
    agPH = Math.round(Math.min(AGP_MAX, Math.max(AGP_MIN, ev.clientY - y0)));
    pb.style.maxHeight = agPH + 'px';
  }, () => {
    document.body.classList.remove('rowdrag');
    lsSet('agPH', agPH);
  });
});
document.addEventListener('dblclick', e => {
  if(e.target.closest && e.target.closest('.agpg')){
    agPH = AGP_DEF;
    lsDel('agPH');
    agentRepaint();
  }
});
document.addEventListener('pointerdown', e => {
  const g = e.target.closest && e.target.closest('.dgrip');
  if(!g) return;
  const sp = g.parentElement;
  const x0 = sp.getBoundingClientRect().left;
  e.preventDefault();
  document.body.classList.add('dragging');
  dragTrack(e, g, ev => {
    dfW = Math.round(Math.min(DFW_MAX, Math.max(DFW_MIN, ev.clientX - x0)));
    sp.style.gridTemplateColumns = dfW + 'px 7px 1fr';
  }, () => {
    document.body.classList.remove('dragging');
    lsSet('dfW', dfW);
  });
});
document.addEventListener('dblclick', e => {
  if(e.target.closest && e.target.closest('.dgrip')){
    dfW = 0;                                  // back to 3:7
    lsDel('dfW');
    diffShow();
  }
});

