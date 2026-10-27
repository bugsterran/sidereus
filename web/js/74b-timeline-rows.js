// ★**Clicking the name cell also opens it** (2026-09-08: selecting an agent in the left tree should show its
// last or current work; no response on click felt broken).
// Before, the click target was **only the bar** — the row even had `cursor:pointer`, so clicking with nothing
// happening read as broken. What opens is **running first, else the last one**
// (the answer that fits this screen's question "what is it doing now").
function tlPick(g){
  const run = g.items.filter(x => x.run);
  return (run.length ? run : g.items).reduce((m, x) => (!m || x.end > m.end ? x : m), null);
}
// One timeline row (L = shared layout: pct, t0, idleb, ticks, napb). Also fills tlHovG[gi] for the hover card.
function tlRow(g, gi, L){
    const sess = g.sess;
    const pick = tlPick(g) || {};
    const tkSum = g.items.reduce((a2, r) => a2 + (r.tk || 0), 0);
    const nmOpen = ' data-tlt="'+esc(pick.tid || '')+'" data-tlh="'+gi+'"';
    // Totals count **actual activity** — using span would add stopped time too
    const tot = g.items.reduce((a2, r) => a2 + ((r.segs && r.segs.length)
        ? r.segs.reduce((b2, x) => b2 + Math.max(0, x[1] - x[0]), 0)
        : Math.max(0, r.end - r.start)), 0);
    const run = g.items.some(r => r.run);
    // ★Same type running **concurrently** covers each other on one row (measured: two Explores overlapped at 09:00).
    // Only overlapping ones stack in lanes — without overlap there is one lane and row height is unchanged.
    const laneEnd = [];
    for(const r of g.items){
      let k = laneEnd.findIndex(e => e <= r.start);
      if(k < 0){ k = laneEnd.length; laneEnd.push(0); }
      laneEnd[k] = r.end;
      r._lane = k;
    }
    const lanes = Math.max(1, laneEnd.length);
    tlHovG[gi] = {g, pick, tkSum, tot, lanes};        // Hover card source (metadata only)
    // ★Sessions draw **only spans that actually moved** (2026-09-01: barely ran yet showed as one long bar).
    // One continuous bar makes idle time look like work. Outside the tail window a gray underline leaves "unknown".
    return sess ? tlSessRow(g, gi, nmOpen, L) : tlAgentRow(g, gi, nmOpen, lanes, run, L);
}
function tlSessRow(g, gi, nmOpen, L){
      const {pct, t0, idleb, ticks, napb} = L, hh = tlHh;
      // ★A session row takes in **multiple transcripts** of that project (2026-09-09 · server emits
      // every session in the window). Before, only `g.items[last]` was drawn, so an old session split off by `/clear` today
      // was **counted in token totals but had no bar** (row total ≠ what was drawn).
      // ⇒ Keep **one row per project** (more rows make the Gantt unreadable), and within it
      // draw bars, compaction markers and hatching for every session. Status dot and name follow the **latest session**.
      const its = g.items;
      const it = its[its.length-1];
      const col = projColor(g.cwd);          // Bars in project color, state only as a chip
      const segMin = x => (x.segs||[]).reduce((a2,y)=>a2+(y[1]-y[0]),0);
      const act = Math.round(its.reduce((a2,x)=>a2+segMin(x),0)/60);
      const nSeg = its.reduce((a2,x)=>a2+((x.segs||[]).length),0);
      const nComp = its.reduce((a2,x)=>a2+((x.comp||[]).length),0);
      // ★Hatching covers only the part the tail did not reach **within the span the session was alive** (2026-09-04).
      // Before, it painted from `left:0` to seen, so a just-born session covered window start~birth as "unknown"
      // (measured: repo-A start=06:52:11 · seen=06:52:11 — unknown span 0, yet
      // 04:08-06:52, 2h 44m, was hatched). Before birth is not unknown; it is time when it **did not exist**.
      // ⚠The server clamps start to window start (cut), so sessions older than the window behave exactly as before.
      const unk = its.map(x => {
        const seen = x.seen || t0, bornAt = x.start || t0;
        if(!(seen > bornAt + 60 && seen > t0 + 60)) return '';
        const unkL = Math.max(0, pct(bornAt));
        return '<div class=tlunk style="left:'+unkL.toFixed(2)+'%;width:'
          + Math.max(0, pct(seen) - unkL).toFixed(2)+'%" '
          + 'title="'+esc(T("The earlier part of this session's log was not read, so this span is unknown"))+'"></div>';
      }).join('');
      // ★Compaction spot — marked with a vertical mark. It means the session lost prior context there, so
      // "from here on it does not know the earlier conversation" reads visually.
      const comps = its.map(x => (x.comp || []).map(cp =>
        '<div class=tlcp style="left:'+pct(cp.at).toFixed(2)+'%" title="'
        + esc(hh(cp.at) + TV({msg: ' compaction ({t})', vars: {t: cp.trig}}) + ' · ' + Math.round(cp.pre/1000) + 'K → '
              + Math.round(cp.post/1000) + 'K · ' + U(Math.round(cp.ms/1000), 's')
              + '\n' + T('At this point the session lost its earlier context'))
        + '"></div>').join('')).join('') + tlClrMarks(its, pct);
      // ⚠Segment details moved from the native title into the hover card (`tlHovHtml`) — never both.
      // ⚠Gemini bars use 0.5 (= TLBMINW) so a 20 s `gemini -p` run stays visible.
      const bmin = g.plat ? 0.5 : 0.35;
      const bars2 = its.map((x2, ii) => (x2.segs || []).map((x, si) => {
        const l = pct(x[0]), w = Math.max(bmin, pct(x[1]) - l);
        // Accessible name = project + span length (metadata only; details stay in the hover card).
        return '<div class="tlb tlbs" data-tlt="'+esc(x2.tid)+'" data-tlh="'+gi+'" data-tli="'+ii+'" data-tls="'+si+'"'
          + ' aria-label="'+esc((g.proj || g.cwd.split('/').pop())+' · '+U(Math.max(0, Math.round((x[1] - x[0]) / 60)),'m'))+'"'
          + ' style="left:'+l.toFixed(2)+'%;width:'+w.toFixed(2)+'%;background:'+col+'"></div>';
      }).join('')).join('');
      Object.assign(tlHovG[gi], {act, nSeg, nComp});
      const pl = tlPlRun(g, L);            // pipeline strip + bands (74c); '' without a run keeps the row unchanged
      return '<div class="tlr tlrs'+tlPlRowCls(pl)+'" data-tlc="'+esc(g.cwd)+'" data-tlp="'+esc(g.plat || '')+'">'
        + '<div class=tlnm'+nmOpen+'>'
        + tlSessNmB(g, it, act, nComp) + tlPlStrip(pl) + tlPlOffNote(g) + '</div>'
        + '<div class=tlt>'+idleb+ticks+napb+unk+bars2+comps+tlPlBands(pl, L, its)+'</div></div>';
}
// Session name cell «logo · project · state dot · chips»; also the «Pipelines» «Working now» row (48j; bare = no time/token chips).
function tlSessNmB(g, it, act, nComp, bare){
  return '<b>'+aiLogo(g.plat)+'<i class="tlp c'+repoHue(g.cwd)+'" title="'+esc(g.cwd)+'">'+esc(g.proj || g.cwd.split('/').pop())+'</i>'
        + tlStateDot(it)
        // ⚠the chip is ellipsis-truncated (20-timeline.css .tlnm u) — title carries the full value
        + (bare ? '' : g.plat ? (tv => '<u title="'+esc(tv)+'">'+esc(tv)+'</u>')(T('Tokens')+' '+fmtTok(g.items.reduce((a2, x) => a2 + (x.tk || 0), 0)))
                  : '<u title="'+esc(U(act,'m'))+'">'+U(act,'m')+'</u>')
        // Compaction chip shows the count only («N×», red like the .tlcp mark); the ellipsised word lost the meaning, title keeps it.
        + (nComp ? '<u class=tlcpn title="'+TV({msg: 'compacted {n}×', vars: {n: nComp}})+'">'
            + esc(nComp+'×')+'</u>' : '') + '</b>';
}
// /clear spots (`x.clr = [{at, old8, new8}]`); absent/empty renders nothing so rows without a record keep their bytes.
function tlClrMarks(its, pct){
  return its.map(x => (Array.isArray(x.clr) ? x.clr : []).filter(c => c && isFinite(c.at)).map(c =>
    '<div class=tlclr style="left:'+pct(c.at).toFixed(2)+'%" title="'
    + esc(tlHh(c.at) + ' ' + TV({msg: 'Cleared — new session {s}', vars: {s: String(c.new8 || '')}})
          + '\n' + TV({msg: 'Previous session {s}', vars: {s: String(c.old8 || '')}}))
    + '"></div>').join('')).join('');
}
function tlAgentRow(g, gi, nmOpen, lanes, run, L){
    const sess = g.sess, {pct, idleb, ticks, napb} = L;
    // ★One run is drawn split into **active spans** (2026-09-02). Joining it as one bar makes time stopped
    // by closing the MacBook look like work (measured: a 704-min svc-D-live bar had 20 min of real activity).
    const segs = g.items.flatMap((r, ii) => {
      const parts = (r.segs && r.segs.length) ? r.segs : [[r.start, r.end]];
      return parts.map((pp, pi) => {
      const l0 = pct(pp[0]), l = Math.max(0, l0);
      const w = Math.max(0.5, pct(pp[1]) - l);
      // ★Write **the fragment's own** length (2026-09-02: labels appeared on some bars and not others).
      // Before, it was written only when `parts.length === 1` — stamping 'whole-run total' on every fragment
      // repeats the same number on several bars and becomes false. So **runs that paused and resumed
      // lost their number entirely** — exactly the most interesting case. Writing its own length, not the total,
      // avoids both repetition and falsehood (the whole-run total stays in the tooltip).
      const pm = Math.max(0, Math.round((pp[1] - pp[0]) / 60));
      // ★Tokens are also **the fragment's own share** (2026-09-09: per-bar usage).
      // `tks` is in the same order as `segs` (the server emits it so). Rows drawn as one bar for lack of spans
      // (= rows with empty `segs`) — that bar is the whole run, so use the row total as is.
      const tkv = (r.segs && r.segs.length) ? ((r.tks && r.tks[pi]) || 0) : (r.tk || 0);
      const bh = sess ? 6 : Math.max(6, Math.floor(18 / lanes));
      const top = 3 + r._lane * (bh + 2);
      const bg = r.run ? TLC.run : agColor(g.type), ink = tlInk(bg);
      // ⚠Segment and run details live in the hover card (`tlHovHtml`), not a native title — never both.
      return '<div class="tlb'+((r.run && !sess)?' tlbr':'')+(sess?' tlbs':'')+'" data-tlt="'+esc(r.tid)+'"'+(r.aid ? ' data-tla="'+esc(r.aid)+'"' : '')
        + ' data-tlh="'+gi+'" data-tli="'+ii+'" data-tls="'+pi+'"'
        + ' aria-label="'+esc((sess ? (g.proj || g.cwd.split('/').pop()) : tlAgLab(g, tlAgDesc).lab)+' · '+U(pm,'m'))+'"'
        + ' style="left:'+l.toFixed(2)+'%;width:'+w.toFixed(2)+'%;'
        + 'top:'+top+'px;height:'+bh+'px;bottom:auto;'
        + 'background:'+bg+'">'
        // ★Text inside bars: «min · tokens», else «min», else nothing (both are the fragment's own values).
        // ⚠Which part fits is decided in px by tlBarFit after layout, not by % width here (2026-09-25: a %
        // threshold spilled/wrapped labels once the git rail or a 1280 window narrowed the rows). data-s = short form.
        + (bh >= 10 ? '<span'+(ink ? ' class='+ink : '')+' data-s="'+esc(U(pm,'m'))+'">'+U(pm,'m')+(tkv ? ' · '+fmtTok(tkv) : '')+'</span>' : '')
        + '</div>';
      });
    }).join('');
    const rowH = sess ? 16 : (6 + lanes * (Math.max(6, Math.floor(18 / lanes)) + 2));
    const n = g.items.length;
    return '<div class="tlr'+(sess?' tlrs':' tlrk')+'" data-tlc="'+esc(g.cwd)+'" data-tlp="'+esc(g.plat || '')+'">'
      + '<div class=tlnm'+nmOpen+'>'
      // Only session rows get a project chip — branches below obviously belong to that session (duplicate labels are noise)
      // ★When running, put a dot **next to that row's name** — blinking bars alone are hard to find among many rows
      // ⚠Sessions are always open — that is not 'running'. Dots go **only on agent rows**.
      + '<b>' + (sess
          ? aiLogo(g.plat)+'<i class="tlp c'+repoHue(g.cwd)+'" title="'+esc(g.cwd)+'">'+esc(g.proj || g.cwd.split('/').pop())+'</i>'
            + tlStateDot(g.items[g.items.length-1])
          // ★The dot sits **right after the name** — same position (after name) as the session row's state marker
          // ★Agent rows get the same AI mark as sessions (per the original orca screen) — plat is that of the owning session
          : tlAgNmB(g, run))
      + (n > 1 ? '<u>'+U(n,'×')+(lanes > 1 ? ' · '+TV({msg: '{n} parallel', vars: {n: lanes}}) : '')+'</u>' : '') + '</b>'
      // ★The inline «N min total · desc» was removed (2026-09-24: always truncated) — the hover card carries it in full.
      + '</div>'
      + '<div class=tlt style="height:'+rowH+'px">'+idleb+ticks+napb+segs+'</div></div>';
}
// Agent name cell «├─ logo · name · type · running dot»; also the «Working now» subagent rows (48j).
function tlAgNmB(g, run){
  return '<i class=tlbr2>'+'　'.repeat(g.lv||0)+(g.br||'├')+'─</i>'+aiLogo(g.plat)+tlAgNm(g)
            + '<i class="tlds'+(run?' on':'')+'"></i>'
            + (g._par > 1 ? '<i class=tlpar>'+g._pi+'/'+g._par+'</i>' : '');
}
// Bar label ink per bar colour. ⚠#0d1014 on mid-lightness hues was 3.5-4.1:1; one fixed ink cannot pass on all 360 hues.
function tlInk(bg){
  let c = String(bg), rgb;
  const h = c.match(/^hsl\(([\d.]+)\s+([\d.]+)%\s+([\d.]+)%\)$/);
  if(h){
    const H = +h[1], S = h[2] / 100, L = h[3] / 100, a = S * Math.min(L, 1 - L);
    rgb = [0, 8, 4].map(n => { const k = (n + H / 30) % 12; return L - a * Math.max(-1, Math.min(k - 3, 9 - k, 1)); });
  } else {
    if(c.length === 4) c = '#' + c[1] + c[1] + c[2] + c[2] + c[3] + c[3];
    rgb = [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16) / 255);
  }
  const lin = v => v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  const Y = 0.2126 * lin(rgb[0]) + 0.7152 * lin(rgb[1]) + 0.0722 * lin(rgb[2]);
  // Class for the label: '' = default #0d1014 · tlbi = white · tlbk = #000 (hues where neither of the first two reaches 4.5:1)
  return (Y + 0.05) / 0.0556 >= 4.5 ? '' : 1.05 / (Y + 0.05) >= 4.5 ? 'tlbi' : 'tlbk';
}
// Agent name cell: the description keeps the width; chips hide in this order until it fits (hover card still has them).
// ⇒ 1 type / workflow phase chip (bar colour + card header repeat it) · 2 «N×» count · 3 «workflow» kind chip. i/n and fail chips stay.
const TL_NMFIT = ['tlnf1', 'tlnf2', 'tlnf3'];
let tlNmRO = null;
function tlNmFit(box){
  if(tlNmRO){ tlNmRO.disconnect(); tlNmRO = null; }
  const nms = [...box.querySelectorAll('.tlrk .tlnm')].filter(n => n.querySelector('.tlagd'));
  if(!nms.length) return;
  const fit = () => {
    nms.forEach(n => n.classList.remove(...TL_NMFIT));
    let todo = nms;
    for(const k of TL_NMFIT){                       // ⚠Read all, then write all — one layout per step, not per row
      todo = todo.filter(n => { const d = n.querySelector('.tlagd'); return d.scrollWidth > d.clientWidth + 0.5; });
      if(!todo.length) break;
      todo.forEach(n => n.classList.add(k));
    }
  };
  fit();
  if(window.ResizeObserver){ tlNmRO = new ResizeObserver(fit); tlNmRO.observe(nms[0]); }
}
function tlHelpText(){
  // The .tlnote paragraph is hidden and its same (already translated) sentences move into a `?` tooltip.
  const tlHelp = ['The end is <b>when the last record was written</b>, so it is slightly earlier than the real finish.',
      'Below is a <b>summary</b> of this window; click a bar to open its work log in a new window.',
      'Hover <b>outside</b> the bars for a snapshot of that moment; <b>click to pin</b> it.',
      'Press <b>▶</b> and the cursor walks by itself (replay).'].map(s => T(s).replace(/<[^>]+>/g, '')).join(NL);
  return tlHelp;
}
// Header row: window summary, token total, hidden-session count, age / error.
// lg = pipeline stepper key (tlPlLegendFor, 74c) or ''; sits at the header's right end, wraps under it when the line is full.
function tlHeadHtml(d, rows, tlHidden, lg){
  const sum = TV({msg: 'Last {t} · {n} subagents · peak {p} at once', vars: {t: d.hours < 1 ? U(Math.round(d.hours*60),'m') : U(d.hours,'h'), n: rows.filter(r=>r.kind!=='sess').length, p: d.peak}});
  const hidT = tlHidden ? TV({msg: '{n} off-window sessions hidden', vars: {n: tlHidden}}) : '';
  // ⚠.tlsum wraps by a 200px basis then ellipsizes (20 css), so the head's line count never follows the text length; title = the same counts in full.
  const tip = [tlErr ? T(tlErr) : '', sum, d.tok ? T('tokens') + ' ' + fmtTok(d.tok.sum||0) : '', hidT].filter(Boolean).join(' · ');
  const tlHead = '<div class="wvh wvht"><b>'+T('Subagent timeline')+'</b>'
    + '<span class=tlsum title="' + esc(tip) + '">'
      // ★State failures in text instead of erasing bars (loadTl). ⚠First: the span ellipsizes at its end, so a failure is never cut off.
      + (tlErr ? '<em class=tlage style="color:'+thc('#f0b357','var(--nx-warn)')+'">'+esc(T(tlErr))+' · </em>' : '')
      + sum
      // ★Tokens are **the sum of bars this screen drew** — may differ from the sidebar's "today by project".
      // ★There are **only two** sources of difference (re-summarized 2026-09-09 after totals were reported as inconsistent).
      // (1) Window: here the last N hours, today card from midnight, daily per day.
      // (2) Scope: now counts **every transcript in the window** (2026-09-09) — before, session rows
      // read only the latest one per project, missing 23% (524.4M vs full file scan 678.0M).
      // ⚠**The definition is now the same for all three** — input+output+cache read+cache write, each response once
      // (= ccusage `totalTokens`). Before, this place was ×2.94 of the true value and the today card ×1.97.
      + (d.tok ? '<em class=tlhid title="'+esc(T('Tokens used by every transcript with records in this window (input + output + cache read + cache write — same definition as "Today by project" and "Daily").\nOnly the window differs — here the last N hours, the today card from midnight.'))
          + (rows.some(r => r.plat) ? esc((pn => '\n' + TV({msg: 'Claude only — {p} rows show their own tokens.', vars: {p: pn}}))(
              [...new Set(rows.filter(r => r.plat).map(r => r.plat))]
                .map(p => platName(p)).join('·'))) : '')
          + '">· '+(rows.some(r => r.plat) ? aiLogo('cc') + ' ' : '')+T('tokens')+' '+fmtTok(d.tok.sum||0)+'</em>' : '')
      // ★Write **how many** sessions were hidden (see `sessShown` comment above) — removing silently reads as "none".
      + (tlHidden ? '<em class=tlhid title="'+esc(T('Sessions with no bars in this window and no live connection — widen the window to see them'))+'">· '
          + hidT+'</em>' : '')
      + '<em class=tlage id=tlage></em>'
      + '</span>'
      // The label above was removed (2026-09-01) — the session card already says the same. The marker goes **on that row**.
    // ⚠«Changes» group + pipeline key share one right-aligned wrapper: they wrap together, so neither lands under the «Runs N» chip (21 css)
    + '<div class=tlhr>' + (typeof tlgChipHtml === 'function' ? tlgChipHtml() : '') + (lg || '') + '</div></div>';
  return tlHead;
}
// Controls and «?» live in the header toolbar slot (tbSet, 92-mainview-tabs.js); ids are global so tlWireCtl finds them.
function tlCtlHtml(){
  const tlHelp = tlHelpText();
  const tlCtl = '<span class=tlhx>'
      // Short group labels so speed / refresh interval / range read as three separate controls.
      + '<i class=tlgl>'+esc(T('Replay'))+'</i>'
      + '<em class="tlrp'+(tlRpOn?' on':'')+'" id=tlrp title="'
        + esc(T('Replay — the cursor walks from the left edge of the window to the right by itself.'
              + '\nThe right side (time not reached yet) is masked, so the day appears to fill in.'
              + '\nClick a bar cell midway to continue from there.'))+'">'
        + (tlRpOn ? '❙❙' : '▶') + '</em>'
      + '<select class=tlsel id=tlrps title="'+esc(T('Replay speed (timeline time per real second)'))+'">'
        + TL_RSP.map(x=>'<option value="'+x[0]+'"'+(tlRpSpeed===x[0]?' selected':'')+'>'
            + T(x[1]) + '</option>').join('')
      + '</select>'
      + '<i class=tlgl>'+esc(T('Refresh'))+'</i>'
      + '<em class=tlrf id=tlrf title="'+esc(T('Reload now'))+'">↻</em>'
      + '<select class=tlsel id=tlsel title="'+esc(T('Auto-refresh interval'))+'">'
        + TL_EVERY.map(x=>'<option value="'+x[0]+'"'+(tlAuto===x[0]?' selected':'')+'>'
            + T(x[1]) + '</option>').join('')
      + '</select>'
      + '<i class=tlgl>'+esc(T('Range'))+'</i>'
      + '<select class=tlsel id=tlselh title="'+esc(T('Time window'))+'">'
        + (() => { const base = [1,3,6,12,24,48];
            const list = base.includes(tlHours) ? base : base.concat([tlHours]).sort((a,b)=>a-b);
            return list.map(h=>'<option value="'+h+'"'+(tlHours===h?' selected':'')+'>'
              + rangeLbl(h) + '</option>').join('')
              + '<option value="custom">'+T('Custom…')+'</option>'; })()
      + '</select>'
      + '<i class=tlgl>'+esc(T('Rows'))+'</i>'
      + '<select class=tlsel id=tlro title="'
        + esc(T('«Running only» hides finished subagent rows — session rows stay')) + '">'
        + '<option value="0"' + (tlRunOnly ? '' : ' selected') + '>' + esc(T('All rows')) + '</option>'
        + '<option value="1"' + (tlRunOnly ? ' selected' : '') + '>' + esc(T('Running only')) + '</option>'
      + '</select>'
      + (typeof acctPickHtml === 'function' ? acctPickHtml('time') : '')   // '' below 2 accounts
      + '</span>'
      + '<em class=tlq id=tlq role=button tabindex=0 aria-haspopup=dialog aria-expanded=false title="'+esc(tlHelp)+'">?</em>';
  return tlCtl;
}
// «?» opens the same help text as a popover (title alone gave no response to a click). Delegated: tbSet rewrites the toolbar.
function tlqClose(back){ popHide('tlqp', document.getElementById('tlq'), back); }
popReg('tlqp', '#tlqp, #tlq', tlqClose);
function tlqToggle(q){
  if(popIsOpen('tlqp')) return tlqClose(false);
  const p = popGet('tlqp', 'thpop tlqp');
  p.setAttribute('role', 'dialog');
  p.setAttribute('aria-label', T('help'));
  p.innerHTML = tlHelpText().split(NL).map(s => '<div>' + esc(s) + '</div>').join('');
  q.setAttribute('aria-expanded', 'true');
  popAnchor(p, q, {align: 'right'});
}
document.addEventListener('click', e => { const q = e.target.closest && e.target.closest('#tlq'); if(q) tlqToggle(q); });
document.addEventListener('keydown', e => {
  const q = (e.key === 'Enter' || e.key === ' ') && e.target.closest && e.target.closest('#tlq');
  if(q){ e.preventDefault(); tlqToggle(q); }
});
// Toolbar controls (range · refresh · replay) — the markup is tlCtlHtml, set into the tbSet slot before this runs.
function tlWireCtl(apFo){
  const sh = document.getElementById('tlselh');
  if(sh) sh.onchange = () => {
    if(sh.value === 'custom'){
      const v = prompt(T('How many hours to show? (0.5 - 168)'), String(tlHours));
      const n2 = Math.min(168, Math.max(0.5, parseFloat(v)));
      if(!v || !isFinite(n2)){ sh.value = String(tlHours); return; }   // Revert on cancel
      tlHours = Math.round(n2 * 10) / 10;
    } else tlHours = +sh.value;
    lsSet('mbTlHours', tlHours);
    loadTl(true); };
  const sa = document.getElementById('tlsel');
  if(sa) sa.onchange = () => { tlAuto = +sa.value;
    lsSet('mbTlAuto', tlAuto);
    if(tlAuto) loadTl(true); else paintTl(); };
  const rf = document.getElementById('tlrf');
  if(rf) rf.onclick = () => loadTl(true);
  const rp = document.getElementById('tlrp');
  if(rp) rp.onclick = () => tlRpToggle();
  if(typeof acctPickWire === 'function') acctPickWire('time', paintTl, apFo);
  const rs = document.getElementById('tlrps');
  if(rs) rs.onchange = () => { tlRpSpeed = +rs.value;
    lsSet('mbTlRp', tlRpSpeed); };
  const ro = document.getElementById('tlro');
  if(ro){
    // ⚠paintTl rewrites the toolbar, so keyboard focus is put back on the new select.
    ro.onchange = () => { const f = document.activeElement === ro;
      tlRunOnly = ro.value === '1'; lsSet('sidereus.tlrun', tlRunOnly ? '1' : '0'); paintTl();
      const n = f && document.getElementById('tlro'); if(n) n.focus({preventScroll: true}); };
  }
}
// Roving focus: a row is one tab stop (98-a11y gives bars tabIndex -1); arrows walk its bars and the rows above/below.
//   ⚠Up/Down from a bar lands on the bar nearest in x in the next row (bar counts differ per row), else on that row.
function tlRoveTarget(t, key, rows){
  const bar = t.classList.contains('tlb'), row = bar ? t.closest('.tlr') : t;
  const bars = r => [...r.querySelectorAll('.tlb[data-kb]')];
  const bs = bars(row), i = bar ? bs.indexOf(t) : -1;
  if(key === 'ArrowRight') return bs[i + 1] || null;
  if(key === 'ArrowLeft') return !bar ? null : (i > 0 ? bs[i - 1] : row);
  if(key === 'Home') return bs[0] || null;
  if(key === 'End') return bs[bs.length - 1] || null;
  if(key !== 'ArrowUp' && key !== 'ArrowDown') return null;
  const nr = rows[rows.indexOf(row) + (key === 'ArrowUp' ? -1 : 1)];
  if(!nr || !bar) return nr || null;
  const cx = b => { const r = b.getBoundingClientRect(); return r.left + r.width / 2; }, x = cx(t);
  let best = null, bd = Infinity;
  for(const b of bars(nr)){ const d = Math.abs(cx(b) - x); if(d < bd){ bd = d; best = b; } }
  return best || nr;
}
document.addEventListener('keydown', e => {
  if(e.defaultPrevented || e.isComposing || e.metaKey || e.ctrlKey || e.altKey) return;
  const t = e.target;
  if(!t || !t.matches || !t.matches('#feed .tlr[data-kb], #feed .tlr .tlb[data-kb]')) return;
  if((e.key === 'Enter' || e.key === ' ') && !t.classList.contains('tlb')){
    // ⚠The row's own click lands on .tlwrap and toggles the time-cursor pin; the name cell is what opens the work log.
    const nm = t.querySelector('.tlnm[data-tlt]');
    if(nm && nm.dataset.tlt && !e.repeat){ e.preventDefault(); nm.click(); }
    return;
  }
  const n = tlRoveTarget(t, e.key, [...document.querySelectorAll('#feed .tlr[data-kb]')]);
  if(n){ e.preventDefault(); n.focus(); }
});
// Bar / name clicks and the time cursor on the painted rows.
function tlWireRows(box){
  tlNmFit(box);
  // ★Clicking a bar opens that agent's **work-history tab** — hover is a preview, click is everything.
  // No new view (same renderer, same tab system).
  // One row has several spans, so the **bar** is the click target
  tlPlWire(box);
  box.querySelectorAll('.tlb[data-tlt]').forEach(bb => bb.onclick = (e) => {
    e.stopPropagation();
    if(e.target.closest && e.target.closest('.tlpl')) return;
    const tr = bb.closest('.tlr');
    tlgFollow(tr.dataset.tlc, tr.dataset.tlp, bb.dataset.tlt);   // the «Changes» chip follows the clicked session (77)
    tlOpen(tr.dataset.tlc, bb.dataset.tlt);
  });
  // The name cell opens the same drawer (empty tids are not bound — do not create yet another spot where clicking does nothing)
  box.querySelectorAll('.tlnm[data-tlt]').forEach(nn => {
    if(!nn.dataset.tlt) return;
    nn.style.cursor = 'pointer';
    nn.onclick = (e) => {
      e.stopPropagation();                 // ⚠Must not leak into the time cursor's pin toggle
      if(e.target.closest && e.target.closest('.tlpl, .tlplx')) return;   // strips open the pipeline view, the chip folds runs (tlPlWire)
      const tr = nn.closest('.tlr');
      tlgFollow(tr.dataset.tlc, tr.dataset.tlp, nn.dataset.tlt);
      tlOpen(tr.dataset.tlc, nn.dataset.tlt);
    };
  });
  // ★The cursor is bound **to one container only** (not per bar) — there are hundreds of bars, so as many
  // handlers would pile up, and the cursor would break in gaps between bars. Events bubble up anyway.
  const wrap = box.querySelector('.tlwrap');
  if(wrap){
    wrap.onmousemove = (e) => {
      if(tlCurPin || tlRpOn) return;       // Does not follow while pinned or replaying
      tlCurEv = e;                         // ⚠Once per frame via rAF — a full scan of bars is attached
      if(!tlCurRaf) tlCurRaf = requestAnimationFrame(() => {
        tlCurRaf = 0; if(tlCurEv) tlCurMove(tlCurEv); });
    };
    // ★Do **not turn off** during replay (2026-09-09: cursor stuck spinning in place).
    // Before, the mouse leaving the cell set `tlCurAt = 0`, and `tlRpStep` kept adding from 0,
    // so the cursor stuck to the window's left edge forever — playback ran, the screen stayed put.
    wrap.onmouseleave = () => { if(tlCurPin || tlRpOn) return; tlCurAt = 0; tlCurApply(); };
    wrap.onclick = (e) => {
      // Bars are owned by the **drawer** (it does stopPropagation, but once more in case layers overlap)
      if(e.target.closest && e.target.closest('.tlb, .tlnm, .tlpl, .tlnmg')) return;   // .tlnmg: a grip drag release is not a pin toggle
      // ★Clicking during replay is **jump to that spot** (does not stop) — not a pin toggle.
      // This one gesture covers rewind and fast-forward without building them separately.
      if(!tlRpOn) tlCurPin = !tlCurPin;
      tlCurMove(e);                        // Start from the clicked spot
    };
  }
}
