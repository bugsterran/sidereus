// ★Two draw targets (when the main chat is unused, this area shows the work log instead of
//   a modal). A modal blocks everything else when open, unfit for continuous watching.
//   `agView` 'feed' draws the same body in the middle column, 'modal' in a popup — one renderer.
let agView = 'modal';
// The work log lives in its own modal (#wkm) over the current view (2026-09-23 IA change); wkOn = modal open.
let wkOn = false, wkRet = null;
function wkBox(){ return document.getElementById('wkmb'); }
function agBox(){
  if(wkOn && wtSplit){
    // when split, the scroll owner is **the focused pane**, not the modal body
    return document.getElementById('wpb' + wtFocus) || wkBox();
  }
  return wkOn ? wkBox() : document.getElementById('dbody');
}
function agentRepaint(){
  // ★**The path to the modal is removed.** Blocking case by case kept surfacing new paths (agLoadRepo callback →
  //   refreshAgent → ...). The work log is now always the middle column and the modal is diff-only, so
  //   cut it structurally instead of checking conditions: this function never opens a modal.
  //   ⚠In chat mode drawing into #feed **overwrites the chat** — so it does nothing then.
  if(!wkOn || !wtShown().length) return;
  return workPaint();
}
// One-line summary for the modal header, from the already-fetched work data (no extra API).
function wkSum(d){
  if(!d || !d.ok) return '';
  if(d.ext) return T('Hook events') + ' ' + U((d.events||[]).length, '#msgs') + ' · ' + (stateLbl(d.state) || T(d.state || ''));
  const st = d.steps || [];
  const nErr = st.filter(s => s.res && s.res.err).length;
  const nF = agFileList(d).length;
  const ls = st.length ? st[st.length - 1] : null;
  const lt = Date.parse((ls && ls.t) || d.last || '');
  const age = isFinite(lt) ? ' · ' + AGO(ago(Math.max(0, Math.floor((Date.now() - lt) / 1000)))) : '';
  // Name the span the counts cover: a session popup reads only the transcript tail (steps.SESS_TAIL),
  // so without it «Files changed 0» read as the whole session's total.
  const t0 = Date.parse(d.first || ''), t1 = Date.parse(d.last || '');
  const mins = isFinite(t0) && isFinite(t1) ? Math.max(1, Math.round((t1 - t0) / 60000)) : 0;
  // d.at = window ending at a past moment (retro failure drill-down) — «Recent» would be wrong there.
  const span = !mins ? '' : (d.at ? T('{n} up to {t}').replace('{t}', MDCLK(new Date(d.at * 1000)))
    : 'sid' in d ? T('last {n}') : T('over {n}')).replace('{n}', U(mins, 'm')) + ' · ';
  return span + T('Tool calls') + ' ' + U(st.length + (d.cutSteps || 0), '#msgs')
    + ' · ' + T('Errors') + ' ' + U(nErr, '#msgs')
    + ' · ' + T('Files changed') + ' ' + U(nF, '#')
    + (ls ? ' · ' + T('Last action') + ' ' + ls.tool + age : '');
}
function wkSumSet(d){
  const e = document.getElementById('wkms'); if(e) e.textContent = wkSum(d);
}
// ⚠Server type/desc = user data + a Korean ' · session <8 hex>' suffix (sidereus/work.py); T() would translate a project named like a key, so only the suffix.
function wkLab(s){ s = plStrip(s); return (LANG === 'en' && typeof s === 'string') ? s.replace(/ · 세션 ([0-9a-f]{8})$/, ' · session $1') : s; }
// Account chip (sidereus/work.py acct*, only with 2+ accounts); labels are user data, so esc() and never T().
function wkAcct(d){
  if(!d || !d.ok || !d.acct) return '';
  const c = typeof acctCls === 'function' ? acctCls(d.acctPrimary ? '' : d.acct) : '';
  return '<span class=wvac><span class="knad ' + c + '">●</span>'
    + esc(T('Account') + ': ' + d.acct + (d.acctDir ? ' · ' + d.acctDir : '')) + '</span>';
}
function workPaint(){
  const box = wkBox();
  if(!box) return;
  const cd = (wtKeyOf(wtFocus) && wtData[wtKeyOf(wtFocus)]) || agentData;
  wkSumSet(cd);
  if(ISWP){ const tt = wtabs.find(x => x.key === wtKeyOf(wtFocus));
            document.title = ((cd && cd.ok && cd.type && wkLab(cd.type)) || (tt && tt.label) || T('Work log')) + ' — ' + PAGE_NAME; }
  // ★This used to close the modal — the modal itself is gone (2026-09-04 diff = floating window), so nothing to do.
  try{ wkcPaint(); }catch(e){ softErr('wkcPaint', e); }     // compose box follows the focused pane (36-wkcompose.js)
  if(wtSplit) return workPaintSplit(box);
  // ★The source of truth is **that tab's cache** (agentData is only a convenience variable used by polling).
  //   Hanging on one global opens holes like the coupling above again.
  const d = (wtPanes[0] && wtData[wtPanes[0]]) || agentData;
  ctxsTag(d, wtabs.find(x => x.key === wtPanes[0]) || {cwd: agentCwd, tid: agentTid});   // context-sources line (35d-ctxsrc.js)
  const head = '<div class=wvh><b>' + esc(d && d.ok ? wkLab(d.type) : T('Work log')) + '</b>'
    + '<span>' + esc(d && d.ok ? wkLab(d.desc || agentCwd) : (agentCwd || '')) + '</span>' + wkAcct(d) + '</div>';
  box.innerHTML = wtStrip() + head + agentBody(d) + wpPlrunHook(d);   // pipeline-run strip (35e-worklog-plrun.js)
  wtBind(box);
  agBind(box);
  if(agentFirst && d && d.ok){ agentFirst = false; box.scrollTop = box.scrollHeight; }
}
// ★Dragging the splitter — only **style** is touched while dragging (replacing innerHTML removes the handle).
//   A trap already hit with width resizing and instruction height, blocked the same way.
// Grid track template: fr tracks with a 9px gutter track between each (the divider lives in the gutter).
function wtGridTpl(a){ return a.map(x => 'minmax(0,' + (+x).toFixed(4) + 'fr)').join(' 9px '); }
function wtBindSplitter(box){
  const wrap = box.querySelector('.wsp');
  if(!wrap) return;
  const tr = wtTracks();
  wrap.querySelectorAll('.wsd[data-ax]').forEach(bar => {
    const ax = bar.dataset.ax, i = +bar.dataset.i;          // boundary between track i and i+1 on axis ax
    bar.onpointerdown = ev => {
      ev.preventDefault();
      wtDragging = true;
      bar.classList.add('on');
      bar.setPointerCapture(ev.pointerId);
      const fr = ax === 'r' ? tr.r : tr.c;
      const move = e2 => {
        const r = wrap.getBoundingClientRect();
        const span = ax === 'r' ? r.height : r.width;
        const G = span - 9 * (fr.length - 1), S = fr.reduce((s, x) => s + x, 0);
        if(G < 60) return;
        let st = 9 * i; for(let j = 0; j < i; j++) st += fr[j] / S * G;
        const pos = (ax === 'r' ? e2.clientY - r.top : e2.clientX - r.left) - st - 4.5;
        const pair = fr[i] + fr[i+1];
        const a = Math.min(pair * .88, Math.max(pair * .12, pos / G * S));
        fr[i] = a; fr[i+1] = pair - a;
        wrap.style[ax === 'r' ? 'gridTemplateRows' : 'gridTemplateColumns'] = wtGridTpl(fr);
      };
      const up = () => {
        wtDragging = false;
        bar.classList.remove('on');
        bar.onpointermove = null; bar.onpointerup = null; bar.onpointercancel = null;
        wtFr[wtLayout] = {c: tr.c, r: tr.r};
        lsSetJson('mbWtFr', wtFr);
        workPaint();                       // redraw once after it ends
      };
      bar.onpointermove = move;
      bar.onpointerup = up;
      bar.onpointercancel = up;
    };
  });
}
// Empty-pane picker (2026-09-23): a /work log window starts with only its own tab, so empty panes list live sessions
// and their subagents from SESS. ⚠Metadata only (project · agent label · state) — never conversation text.
// ⚠A resumed (SendMessage) agent's sub.tid is the SendMessage tool_use id, absent from meta ⇒ «Could not find that subagent's record».
// openAgent id for a SESS[].sub row: the agent id (meta file name, agent_work accepts it) survives resumes; else tid.
function subWorkId(v){
  const a = String((v && v.aid) || '');
  return /^a[0-9a-f]{6,40}$/.test(a) ? a : String((v && v.tid) || '');
}
// Background commands (bgs) have no tid, so there is no work log to open for them.
function wtPickHtml(){
  const st = x => ['tool','think'].includes(x.state) ? T('running') : (x.state === 'wait' ? T('Awaiting input') : T('Quiet'));
  const row = (cwd, tid, kind, lab, sub, run) => wtPanes.includes(wtKey(cwd, tid)) ? '' :
    '<div class="wpk'+(kind==='agent'?' wpka':'')+'" role=button tabindex=0 data-wpk="'+esc(tid)+'" data-wpc="'+esc(cwd)+'">'
    + '<i class="wtk '+(kind==='agent'?'wtka':'wtks')+'">'+(kind==='agent'?'A':'S')+'</i>'
    + '<i class="wtd'+(run?' wpkr':'')+'"></i><b title="'+esc(lab)+'">'+esc(lab)+'</b><span>'+esc(sub)+'</span></div>';
  const rows = (SESS || []).filter(x => x.cwd && x.state !== 'done').map(x => {
    const proj = x.project || x.cwd.split('/').pop();
    return row(x.cwd, 'sess:' + x.cwd + (x.sid ? '|' + x.sid : ''), 'sess', proj, st(x), ['tool','think'].includes(x.state))
      + (x.sub || []).filter(v => v && v.tid).map(v => {
          const idl = typeof v.idle === 'number' ? v.idle : -1;
          return row(x.cwd, subWorkId(v), 'agent', (v.lab != null ? plStrip(String(v.lab)) : String(v.tid).slice(-6)),
                     proj + (idl >= 60 ? ' · ' + AGO(ago(idl)) : ''), idl >= 0 && idl < 60);
        }).join('');
  }).join('');
  return '<div class=wpe>'+T('Click a tab to fill this pane')+'<br>'
    + T('Tabs open in the <b>selected pane</b> — click a pane header to change it.')+'</div>'
    + '<div class=wpkl><u>'+T('Or pick a live session / subagent')+'</u>'
    + (rows || '<div class=wpkn>'+T('No sessions to open')+'</div>') + '</div>';
}
// Load a picked session/agent into pane p (adds its tab) — same key and label rules as openSession/openAgent.
function wtPickOpen(p, cwd, tid){
  wtFocus = p;
  const agent = String(tid).indexOf('sess:') !== 0;
  const row = (SESS || []).find(x => x.cwd === cwd) || {}, sid = agent ? '' : tidSid(tid);
  const key = workOpen(cwd, tid, agent ? String(tid).slice(-6) : (row.project || cwd.split('/').pop()) + (sid ? ' · ' + sid8(sid) : ''), agent ? 'agent' : 'sess');
  wtFetch(wtabs.find(t => t.key === key));
}
function wtPickBind(el, p){
  el._sh = wtPickHtml();   // setHtml cache: the markup was written by the caller
  el.onclick = ev => {
    const it = ev.target && ev.target.closest && ev.target.closest('[data-wpk]');
    if(!it) return;
    ev.stopPropagation();
    wtPickOpen(p, it.dataset.wpc, it.dataset.wpk);
  };
  el.onkeydown = ev => { if(ev.key === 'Enter' && ev.target.dataset && ev.target.dataset.wpk) ev.target.click(); };
}
// ★Split render — each pane has **its own scroll** (#feed doesn't move).
//   ⚠Each pane's scroll position is restored on redraw. Polling is 2.5s, so without this it keeps jumping up.
function workPaintSplit(box){
  if(wtDragging) return;      // dragging the splitter — redrawing removes the handle and breaks the drag
  // scroll is kept **per tab key**, so it survives pane swaps and layout changes
  const keep = {};
  box.querySelectorAll('.wpb[data-k]').forEach(el => {
    keep[el.dataset.k] = {top: el.scrollTop, end: el.scrollHeight - el.scrollTop - el.clientHeight < 40};
  });
  const L = wtLay(), tr = wtTracks(), n = wtPanes.length;
  const pane = p => {
    const k = wtKeyOf(p);
    const t = wtabs.find(x => x.key === k);
    const d = k ? wtData[k] : null;
    const ttl = d && d.ok ? wkLab(d.type) : (t ? t.label : T('Empty'));
    const sub = d && d.ok ? wkLab(d.desc || (t ? t.cwd : '')) : (t ? t.cwd : T('Click a tab to open it in this pane'));
    const q = p - 1, gc = 2 * (q % L.c) + 1, gr = 2 * Math.floor(q / L.c) + 1;
    return '<div class="wpn'+(wtFocus===p?' on':'')+'" data-wpn="'+p+'" style="grid-column:'+gc+';grid-row:'+gr+'">'
      + '<div class=wph draggable="true" data-wpd="'+p+'" title="'+esc(T('Drag onto another pane to swap'))+'">'
      + '<b>'+esc(ttl)+'</b><span>'+esc(sub)+'</span>'+wkAcct(d)
      + '<u>'+esc(wtPaneName(p))+(wtFocus===p?' · '+T('selected'):'')+'</u>'
      + '<i class=wpsw data-wpsw="1" title="'+esc(T('Swap with the next pane'))+'">'+(L.c===1?'⇅':'⇄')+'</i></div>'
      + '<div class=wpb id="wpb'+p+'" data-k="'+esc(k)+'">'
      + (t ? agentBody(ctxsTag(d, t)) + wpPlrunHook(d, k) : '<div class=wpkw data-wpe="'+p+'">'+wtPickHtml()+'</div>')
      + '</div></div>';
  };
  let bars = '', panes = '';
  for(let i = 0; i < L.c - 1; i++)
    bars += '<div class=wsd data-ax=c data-i="'+i+'" style="grid-column:'+(2*i+2)+';grid-row:1/-1" title="'+esc(T('Drag to change the split ratio'))+'"></div>';
  for(let i = 0; i < L.r - 1; i++)
    bars += '<div class=wsd data-ax=r data-i="'+i+'" style="grid-row:'+(2*i+2)+';grid-column:1/-1" title="'+esc(T('Drag to change the split ratio'))+'"></div>';
  for(let p = 1; p <= n; p++) panes += pane(p);
  box.innerHTML = wtStrip()
    + '<div class="wsp wsg" data-lay="'+wtLayout+'" style="grid-template-columns:'+wtGridTpl(tr.c)
    + ';grid-template-rows:'+wtGridTpl(tr.r)+'">' + panes + bars + '</div>';
  // ★Height is **measured and set**. CSS `100vh - constant` can't match this column's top/bottom margins, so
  //   #feed itself scrolled too — with two scroll layers you can't tell which one you're rolling (measured 1169px).
  const sp = box.querySelector('.wsp'), st = box.querySelector('.wtb');
  if(sp){
    sp.style.height = Math.max(280, box.clientHeight - ((st && st.offsetHeight) || 0) - 10) + 'px';
    // ⚠the guessed 10px margin can still overflow the box (measured 785 vs 775) — take the leftover back off
    const over = box.scrollHeight - box.clientHeight;
    if(over > 0) sp.style.height = Math.max(280, parseFloat(sp.style.height) - over) + 'px';
  }
  wtBind(box);
  box.querySelectorAll('.wpn[data-wpn]').forEach(el => {
    const p = +el.getAttribute('data-wpn');
    // clicking a pane focuses it — header or body (like an IDE). Body clicks are handled separately by agBind.
    el.addEventListener('mousedown', ev => {
      if(wtFocus === p) return;
      // ⚠a picker row must survive to its click — repainting here would replace it and drop the click
      if(ev.target && ev.target.closest && ev.target.closest('[data-wpk]')) return;
      wtSetFocus(p); buildMv(); workPaint();
    }, true);
    const bd = el.querySelector('.wpb');
    if(bd) agBind(bd);
    const pk = el.querySelector('.wpkw[data-wpe]');
    if(pk) wtPickBind(pk, p);
    // dragging a pane header **swaps panes** (top/bottom order is changeable)
    const hd = el.querySelector('.wph');
    if(hd){
      hd.ondragstart = ev => {
        ev.dataTransfer.setData('text/plain', 'pane:' + p);
        ev.dataTransfer.effectAllowed = 'move';
        wtDragWhat = 'pane';
      };
      hd.ondragend = () => { wtDragWhat = ''; };
      const sw = hd.querySelector('.wpsw');
      if(sw) sw.onclick = ev => { ev.stopPropagation(); wtSwapPanes(p, (p % n) + 1); };
    }
    // drop a tab/pane onto this pane
    el.ondragover = ev => { ev.preventDefault(); ev.dataTransfer.dropEffect = 'move';
                            el.classList.add(wtDragKind() === 'pane' ? 'dropp' : 'drop'); };
    el.ondragleave = () => el.classList.remove('drop', 'dropp');
    el.ondrop = ev => {
      ev.preventDefault(); el.classList.remove('drop', 'dropp');
      const raw = ev.dataTransfer.getData('text/plain') || '';
      if(raw.indexOf('pane:') === 0){
        // dropping onto itself is nothing (a drag ended by mistake)
        if(+raw.slice(5) !== p) wtSwapPanes(+raw.slice(5), p);
        return;
      }
      if(!raw || !wtabs.some(t => t.key === raw)) return;
      wtFocus = p;                       // the pane dropped on becomes the focus
      wtActivate(raw);
    };
  });
  wtBindSplitter(box);
  box.querySelectorAll('.wpb[data-k]').forEach(el => {
    const kp = keep[el.dataset.k];
    if(kp) el.scrollTop = kp.end ? el.scrollHeight : kp.top;
    else el.scrollTop = el.scrollHeight;     // on first draw, go to the bottom (latest activity)
  });
  if(agentFirst){
    agentFirst = false;
    const el = document.getElementById('wpb' + wtFocus);
    if(el) el.scrollTop = el.scrollHeight;
  }
}
// ★Takes `repaint` — this handler was work-log-tab only, but the timeline bottom drawer uses the same
//   body (agentBody). The default stays agentRepaint, so existing callers run unchanged.
//   Without it, expanding «Files changed» in the drawer makes agentRepaint bail at the mainView check and **nothing happens**.
function agBind(box, repaint){
  const RP = repaint || agentRepaint;
  // ★«Files changed» must **draw in** the diff body when expanded, so it redraws (the default details toggle alone leaves it empty).
  //   Delegation is on the modal body — on the session card container, modal clicks weren't caught (measured 2026-08-31).
  //   onclick assignment, so listeners don't pile up on redraw.
  box.onclick = (e) => {
    // ★Collect edit blocks' open/closed state before redrawing — all three branches below (chip · tree · diff)
    //   rebuild the DOM via RP(). Without collecting, an edit block just folded by hand springs open again.
    agEditHarvest(box);
    // tree filter chips
    const ch = e.target && e.target.closest && e.target.closest('.agtc[data-fil]');
    if(ch){ agTFil = ch.getAttribute('data-fil'); RP(); return; }
    // clicking a file in the tree takes you to its diff spot in the console (expanded)
    const go = e.target && e.target.closest && e.target.closest('.agtf[data-go]');
    if(go){
      const [rp, rel] = go.getAttribute('data-go').split('|');
      const hit = [...document.querySelectorAll('.aged[data-wk]')]
        .filter(x => { const el = x.querySelector('.agwp'); return el && el.textContent === rel; }).pop();
      if(hit){
        const k = hit.getAttribute('data-wk');
        agWroteShut.delete(k); agWroteOpen.add(k);
        RP();
        const again = document.querySelector('.aged[data-wk="'+k+'"]');
        if(again) again.scrollIntoView({block:'center'});
      }
      return;
    }
    const sm = e.target && e.target.closest && e.target.closest('summary');
    if(!sm) return;
    const tr = sm.parentElement && sm.parentElement.classList.contains('agtr');
    if(tr){ agTreeOpen = !sm.parentElement.hasAttribute('open'); return; }   // leave it to the default toggle
    // file diff inside a console row — the body must be drawn in on expand, so redraw
    const wk = sm.closest('.aged[data-wk]');
    if(!wk) return;
    const k = wk.getAttribute('data-wk');
    const keep = box ? box.scrollTop : 0;
    if(wk.hasAttribute('open')){ agWroteOpen.delete(k); agWroteShut.add(k); }
    else { agWroteShut.delete(k); agWroteOpen.add(k); }
    e.preventDefault();
    RP();
    const nb = agBox();
    if(nb) nb.scrollTop = keep;        // keep the reading spot even when expanding
  };
}
// ★The modal also refreshes with polling (otherwise it does not feel live).
//   It used to fetch once on open, so the agent kept running while the screen stood still.
//   ⚠Two rules: (1) redraw **only on change** (judged by footstep count and last time) — replacing innerHTML every time
//   jumps the scroll and closes the expanded instruction. (2) Even then, **restore scroll position** on redraw.
function agentSig(d){
  return !d || !d.ok ? String(d && d.msg) : [d.steps.length, d.cutSteps, (d.says||[]).length, d.last].join('|');
}
// ★The tail of a session tid is **that session's id**: live sessions are `sess:<cwd>`, old sessions
//   `sess:<cwd>|<sid>` (server `:1992`). It must be passed to the server to read that session's transcript.
//   ⚠Without it the cwd's **latest** loads, so clicking an old bar always showed the same content (measured 2026-09-09 ·
//   a defect that appeared after the timeline started drawing a bar per session on one row).
function tidSid(tid){
  const s = String(tid || '');
  if(s.indexOf('sess:') !== 0) return '';
  const i = s.lastIndexOf('|');
  return i > 0 ? s.slice(i + 1) : '';
}
// work-log fetch URL — the three session/agent callers (polling · tab · timeline drawer) share this one spot
function workUrl(cwd, tid){
  if(String(tid).indexOf('ext:') === 0){
    const [p, s] = String(tid).slice(4).split('|');
    return '/api/ext/work?plat='+encodeURIComponent(p||'')+'&sid='+encodeURIComponent(s||'');
  }
  if(String(tid).indexOf('sess:') === 0){
    const sid = tidSid(tid);
    // A popup opened with &at= (retro failure row) keeps reading the window ending then, for its first tid only.
    const at = (ISWP && sid && tid === WPQ.get('tid')) ? Math.round(+WPQ.get('at') || 0) : 0;
    return '/api/session/work?cwd='+encodeURIComponent(cwd)
      + (sid ? '&sid='+encodeURIComponent(sid) : '')   // without sid, the latest as before
      + (at > 0 ? '&at='+at : '');
  }
  const [atid, asid] = String(tid).split('|');   // `<toolUseId>|<sid>` from the history tab: parent session of a finished agent
  return '/api/agent/work?cwd='+encodeURIComponent(cwd)+'&tid='+encodeURIComponent(atid)
    + (asid ? '&sid='+encodeURIComponent(asid) : '');
}
function refreshAgent(){
  const tid = agentTid, cwd = agentCwd;
  if(!tid) return;
  // ★**Don't draw when not visible.** Missing this caused a bug (user repro 2026-08-27:
  //   switching from the work log back to chat broke when new posts arrived):
  //     (1) opening a tab leaves agentTid set  (2) going to chat sets agView back to 'modal'
  //     (3) when polling detects a change, agentRepaint() → open modal (then agentShow() · removed 2026-09-21)
  //        → **the modal pops up by itself**
  //   The tab should stay (resume on return), so the place to fix is 'draw or not'.
  const vis = wkOn && !!wtShown().length;     // drawn only while the work-log modal is open
  if(!vis) return;
  const url = workUrl(cwd, tid);
  getJSON(url)
    .then(j=>{
      if(agentTid !== tid) return;                       // closed in the meantime, or something else opened
      if(agentSig(j) === agentSig(agentData)) return;    // no change — leave it alone
      const box = agBox();
      const top = box ? box.scrollTop : 0;
      const atEnd = box ? (box.scrollHeight - box.scrollTop - box.clientHeight < 40) : false;
      // ★Expanded state is **read from the DOM**. Relying on the click handler's remembered value drifts when opened another way
      //   (keyboard · program) and collapses on every refresh (measured 2026-08-27).
      const op = box && box.querySelector('.agp');   // box = agBox()
      if(op) agPromptOpen = op.hasAttribute('open');
      const ot = box && box.querySelector('.agtr');
      if(ot) agTreeOpen = ot.hasAttribute('open');
      agEditHarvest(box);
      // ★Only what a human opened/closed is remembered. Re-reading the whole DOM records **default expansions** as 'opened by a human',
      //   so when the last-edit spot moves later, the old spot stays expanded.
      if(box) box.querySelectorAll('details.aged[data-wk]').forEach(x => {
        const k = x.getAttribute('data-wk');
        if(agWroteOpen.has(k) || agWroteShut.has(k)) return;      // a human choice already exists
        void k;                                                   // the render decides the default again
      });
      agentData = j;
      const fk = wtKeyOf(wtFocus);
      if(fk) wtData[fk] = j;                  // update the tab cache too (value survives switching)
      agentRepaint();
      const nb = agBox();
      if(nb) nb.scrollTop = atEnd ? nb.scrollHeight : top;   // follow if the end was in view
    })
    .catch(()=>{});
}
// ★The session's own work log — reuses the agent modal. Putting `sess:<cwd>` in the tid slot makes
//   polling (refreshAgent) run on the same path (the same screen isn't built twice).
// ⚠External CLI rows (plat != cc) resolve by (plat, sid) only — their folder may also hold a Claude session,
//   and a cwd lookup opened that one instead.
function extTid(x){ return (x && x.plat && x.plat !== 'cc' && x.sid) ? 'ext:' + x.plat + '|' + x.sid : ''; }
function extTidOf(tid){
  const s = String(tid || '');
  if(s.indexOf('ext:') === 0) return s;
  const sid = tidSid(s);
  return sid ? extTid((SESS||[]).find(x => x.sid === sid)) : '';
}
function openSession(cwd, tid){
  // ★diff is not closed — a relic of the shared-shell era (diff is now a separate floating window).
  // `tid` = `sess:<cwd>|<sid>` from every caller that knows the sid; ⚠plain `sess:<cwd>` opens the cwd's newest session.
  const et = extTidOf(tid);
  if(et){
    if(!ISWP) return wkPopup(cwd || '-', et);
    const sid = et.slice(et.indexOf('|') + 1), er = (SESS||[]).find(x => x.sid === sid) || {};
    const k = workOpen(cwd, et, (er.project || (cwd||'').split('/').pop() || '?') + ' · ' + sid8(sid), 'sess');
    return wtFetch(wtabs.find(t => t.key === k));
  }
  if(!ISWP) return wkPopup(cwd, tid || ('sess:'+cwd));   // main window: the work log opens in its own popup
  const row = (SESS||[]).find(x => x.cwd === cwd && (!x.plat || x.plat === 'cc')) || {};
  const t = tid || ('sess:'+cwd), sid = tidSid(t);
  const key = workOpen(cwd, t,
    (row.project || cwd.split('/').pop()) + (sid ? ' · '+sid8(sid) : ''), 'sess');
  wtFetch(wtabs.find(t => t.key === key));
}
function openAgent(cwd, tid){
  // ★Globals are not cleared (2026-09-04). Code from the shared-shell era; now the globals belong to **the open diff
  //   diff is now **a separate window (another document)**, unrelated to these globals.
  if(!ISWP) return wkPopup(cwd, tid);
  // the label is updated by buildMv when data arrives — starts as the short tid (no inventing a missing name)
  const key = workOpen(cwd, tid, String(tid).split('|')[0].slice(-6), 'agent');
  wtFetch(wtabs.find(t => t.key === key));
}
// ⚠Late repaints (agent tree, longer console, context line) and a shrinking box (composer) keep the old scrollTop,
//   leaving the log short of its end (measured 550px). Growth fires no scroll event, so the flag holds the pre-change state.
// ⚠A scrollTop someone set since the last scroll event (tab switch restoring its spot) is deliberate — left alone.
let wkAtEnd = true, wkTop = 0;
function wkPinInit(){
  const b = wkBox();
  if(!b || typeof ResizeObserver === 'undefined' || typeof MutationObserver === 'undefined') return;
  const pin = () => { if(wkAtEnd && !wtSplit && b.scrollTop === wkTop){ b.scrollTop = b.scrollHeight; wkTop = b.scrollTop; } };
  b.addEventListener('scroll', () => { wkTop = b.scrollTop; wkAtEnd = b.scrollHeight - b.scrollTop - b.clientHeight < 40; }, {passive: true});
  new ResizeObserver(pin).observe(b);
  new MutationObserver(pin).observe(b, {childList: true, subtree: true});
}
if(ISWP){ if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wkPinInit); else wkPinInit(); }
// Called by the main window (35c wkPopup) when «Log» hits an already-open popup: focusing alone kept the old
// scroll spot. Same path as a fresh click — the tab comes forward and the log goes to its end.
function wkReopen(cwd, tid){
  if(String(tid).indexOf('sess:') === 0 || extTidOf(tid)) openSession(cwd, tid); else openAgent(cwd, tid);
  wkAtEnd = true; const b = wkBox(); if(b){ b.scrollTop = b.scrollHeight; wkTop = b.scrollTop; }
}
