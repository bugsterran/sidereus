// Settings modal (header gear): every user-controllable setting in one place.
//   It only surfaces EXISTING client preferences; each row drives the same state/function as its original control.
//   ⚠Do not invent settings here. Nothing is fetched: every choice lives in UIS, as before.
function setLang(v){
  LANG = (v === 'en') ? 'en' : 'ko';
  lsSet('mbLang', LANG);
  // ★Redraw in place instead of reloading — the tab row and this pane are all that speak T() yet.
  //   ⚠hdrLang() is required here: header text is static HTML and nothing else repaints it.
  buildMv(); paintCfg(); try{ hdrLang(); }catch(e){ softErr('hdrLang', e); }
  // ⚠Header count, sidebar cards/chart and status bar otherwise keep the old language until the next poll-driven render.
  try{ full(); }catch(e){ softErr('full', e); }
  try{ buildSessions(); }catch(e){ softErr('buildSessions', e); }
  try{ attnHtml = ''; buildAttn(); buildTodo(); attnTitle(); }catch(e){ softErr('buildAttn', e); }   // top chips + attention strip
  try{ buildWku(); }catch(e){ softErr('buildWku', e); }
  try{ buildSbar(); }catch(e){ softErr('buildSbar', e); }
  try{ const h = document.querySelector('#sdrwin .sdrwh > b'); if(h) h.textContent = T('Quota details'); }catch(e){}   // built once at load
  try{ if(mainView === 'token') paintToken(); else if(mainView === 'struct') paintStruct(); else if(mainView === 'br') paintBr(); else if(mainView === 'hist') paintHist(); else if(mainView === 'retro') paintRetro(); else if(mainView === 'time') paintTl(); else if(mainView === 'pipe') plPaint(); }catch(e){ softErr('paintTab', e); }   // ⚠tab screens repaint only here (timeline was missing: full() wiped it and the rail/toolbar kept the old language until the next load)
}
// «Background tone» (mbTone): black·grey·blue = dark tones, white = light theme, system = OS light -> white, OS dark -> last dark tone.
// ⚠Default (nothing stored) = system; web/app-head.js applies the same default before first paint.
function tonePref(){ try{ const v = UIS.mbTone; return ['black','grey','blue','white','system'].includes(v) ? v : 'system'; }catch(e){ return 'system'; } }
function toneDk(){ const v = lsGet('mbToneDk', '') || document.documentElement.dataset.tone; return (v === 'grey' || v === 'blue') ? v : 'black'; }   // falls back to the tone on screen (users from before mbToneDk)
// Applies html[data-tone]/[data-theme]; JS-drawn tabs repaint because they bake colors in via thc().
function setTheme(v){
  if(v && lsSet('mbTone', v) && (v === 'black' || v === 'grey' || v === 'blue')) lsSet('mbToneDk', v);
  const p = v || tonePref(), lt = p === 'white' || (p === 'system' && matchMedia('(prefers-color-scheme: light)').matches);
  const nt = lt ? 'light' : 'dark', de = document.documentElement;
  de.dataset.tone = (p === 'grey' || p === 'blue' || p === 'black') ? p : toneDk();
  const same = de.dataset.theme === nt;
  de.dataset.theme = nt;
  try{ Object.keys(strWins).forEach(k => { if(!strWins[k].closed) strWinTheme(strWins[k]); }); }catch(e){ softErr('popTheme', e); }
  if(same) return;
  try{ strPopPaint(); }catch(e){ softErr('popRepaint', e); }   // popups bake thc() colors too
  try{ full(); }catch(e){ softErr('full', e); }   // ⚠before the tab repaint — full() writes the chat feed into #feed and wiped the open tab
  try{ if(mainView === 'token') paintToken(); else if(mainView === 'struct') paintStruct(); else if(mainView === 'br') paintBr(); else if(mainView === 'hist') paintHist(); else if(mainView === 'retro') paintRetro(); else if(mainView === 'time') paintTl(); else if(mainView === 'pipe') plPaint(); }catch(e){ softErr('paintTab', e); }
  try{ buildBurn(); }catch(e){ softErr('buildBurn', e); }
  try{ buildPeople(); }catch(e){ softErr('buildPeople', e); }   // people list bakes nmSty() colors; full() only redraws the feed
}
try{ matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => { if(tonePref() === 'system') setTheme(''); }); }catch(e){}
// «Text size» (mbFs): text scale only via --fs (font-size calc); 100 = nothing stored. ⚠web/app-head.js seeds --fs with the same normalisation.
const FS_OPTS = [90, 100, 110, 125];
function fsPref(){ const v = +lsGet('mbFs', '100'); return FS_OPTS.includes(v) ? v : 100; }
function setFs(v){
  v = FS_OPTS.includes(+v) ? +v : 100;
  const st = document.documentElement.style;
  if(v === 100){ st.removeProperty('--fs'); lsDel('mbFs'); }
  else { st.setProperty('--fs', String(v / 100)); lsSet('mbFs', String(v)); }
}
// Poll → modal. Repaint only when the switch changed, and never while the user is typing in the modal.
function svSwSync(sw, st){
  if(sw === undefined) return;
  if(SVHOLD && Date.now() - SVHOLD.at < 3000 && JSON.stringify(sw || null) !== SVHOLD.sw) return;   // ⚠a poll body built before the save would undo the click
  const was = JSON.stringify([SVSW, SVST]);
  SVSW = sw || null; SVST = st || null;
  if(was === JSON.stringify([SVSW, SVST])) return;
  const m = document.getElementById('cfgm'), ae = document.activeElement;
  if(!m || m.hidden || (ae && (ae.tagName === 'INPUT' || ae.tagName === 'SELECT') && m.contains(ae))) return;   // ⚠a repaint would close an open <select>
  paintCfg();
}
function svNowLine(){
  const sw = SVSW || {}, st = SVST || {};
  const who = sw.mode === 'on' ? T('Manual on') : sw.mode === 'off' ? T('Manual off')
    : sw.mode === 'pace' ? T('Target time') + ' ' + (sw.until || '') : T('Auto');
  const stg = (st.on && st.stage) ? T('stage {n}').replace('{n}', st.stage) : T('not saving');
  const gl = T('Target burn') + ' ' + (sw.goal === null ? T('off') : (sw.goal == null ? 100 : sw.goal) + '%')
    + (sw.goalSet ? '' : ' (' + T('default') + ')');
  return T('In effect') + ': ' + who + ' · ' + stg + ' · ' + gl + ' · ' + T('at limit:') + ' ' + T(SV_LIM[sw.limit] || SV_LIM.advise);
}
// Goal-reached action: notify only / warn then proceed / block.
//   Read by ~/.claude/hooks/saver_limit.py.
// Saver switches are frequent and reversible, so every saver row saves on click (no confirm);
//   the summary line shows what is in effect, plus a short «Applied» note after each save.
const SV_LIM = {advise: 'Notify only', warn: 'Warn, then allow', block: 'Block'};
function svLimSet(v){
  const cur = (SVSW && SVSW.limit) || 'advise';
  if(!SV_LIM[v] || v === cur) return;
  return svSet({limit: v});
}
let SVHOLD = null;   // {at, sw}: last saved switch; svSwSync drops differing poll bodies for 3 s
let SVOK = 0;   // time of the last successful save; the note shows for 3 s
function svOkLine(){
  const b = document.getElementById('svnow');
  if(b && !SVERR) b.textContent = svNowLine() + (SVOK ? ' — ' + T('Applied · all sessions') : '');   // in place: no repaint while typing
}
async function svSet(body){
  let r = null;
  try{
    r = await postJSON('/api/saver/set', body);
  }catch(e){ r = e.body || {ok:false, err:String(e)}; }
  SVERR = (r && r.ok) ? '' : T('Save failed') + ': ' + ((r && r.err) || '?');   // SVERR carries its own prefix («Check the value» vs «Save failed»)
  if(r && r.ok){
    SVSW = r.switch || SVSW; SVST = r.saver || SVST;
    SVHOLD = {at: Date.now(), sw: JSON.stringify(SVSW || null)};
    if(body.mode) SVPACE = false;   // the stored mode now shows the choice
    try{ buildSaver(SVST); buildSbar(SVST); }catch(e){ softErr('buildSaver', e); }
    const at = SVOK = Date.now();
    setTimeout(() => { if(SVOK === at){ SVOK = 0; svOkLine(); } }, 3000);
  } else SVOK = 0;
  paintCfg();
}
// Selected settings category; survives repaints and reloads (UIS is optional).
let CFGCAT = 'disp';
CFGCAT = tabGet('sidereus.cfgcat', '') || 'disp';
const cfgOpt = (k, v, lab, on) => '<button class="strp'+(on?' on':'')+'" data-'+k+'="'+esc(String(v))+'"'+(on?' aria-pressed=true':'')+'>'+esc(lab)+'</button>';
// One card per setting: label + one-line description on the left, control on the right (below under 640px).
// dis = reason string: the row is dimmed, titled with it, and every control in it is disabled (the stored value is untouched).
const cfgSet = (lab, desc, ctl, stk, dis) => '<div class="cfgr' + (stk ? ' stk' : '') + (dis ? ' dis' : '') + '"' + (dis ? ' title="' + esc(dis) + '" aria-disabled=true' : '')
  + '><div class=cfgrl><b>' + esc(lab) + '</b>' + (desc ? '<span>' + esc(desc) + '</span>' : '')
  + '</div><div class=cfgrc>' + (dis ? ctl.replace(/<(button|input|select)\b/g, '<$1 disabled') : ctl) + '</div></div>';
const cfgSeg = (lab, btns) => '<div class=cfgseg role=group aria-label="' + esc(lab) + '">' + btns + '</div>';
// Long option lists become a <select>; its change runs the same act[k] as the old pill buttons.
const cfgSel = (k, lab, items, cur) => '<select class=cfgsel data-k=' + k + ' aria-label="' + esc(lab) + '">'
  + items.map(x => '<option value="' + esc(String(x[0])) + '"' + (x[0] === cur ? ' selected' : '') + '>' + esc(x[1]) + '</option>').join('') + '</select>';
function cfgPaneDisp(){
  const opt = cfgOpt, set = cfgSet, seg = cfgSeg;
  const tone = tonePref();
  const lsPin = sesdrPinned();
  return set(T('Display language'), T('Language used for the interface. Untranslated text stays in Korean.') + ' ' + T('Applies immediately, no reload needed.'),
          seg(T('Display language'), opt('lang','ko',T('Korean'),LANG==='ko') + opt('lang','en','English',LANG==='en')))
    + set(T('Background tone'), T('Color of the page background and panels.') + ' ' + T('System follows the OS: white when light, your last dark tone when dark.'),
          seg(T('Background tone'), [['black','Black'],['grey','Grey'],['blue','Blue'],['white','White'],['system','System']]
        .map(x => opt('tone', x[0], T(x[1]), tone === x[0])).join('')))
    + set(T('Text size'), T('Scales text only; layout and widths stay the same.'),
          seg(T('Text size'), FS_OPTS.map(n => opt('fs', n, n + '%', fsPref() === n)).join('')))
    + set(T('Session list'), T('The drawer opens and closes from the «Sessions» button at the top. Pinned keeps it as the right column, as before.'),
          seg(T('Session list'), opt('ls','0',T('Drawer'),!lsPin) + opt('ls','1',T('Pinned right'),lsPin)))
    + set(T('Token widgets on the right'), T('Keeps the weekly donut, daily, today-by-project and live charts under the session list. When off, they are in the Tokens tab and the 5h card at the top.'),
          seg(T('Token widgets on the right'), opt('wks','1',T('On'),wkSide()) + opt('wks','0',T('Off'),!wkSide())))
    + set(T('Burndown curve'), T('Show or collapse the usage burndown curve.'),
          seg(T('Burndown curve'), opt('burn','1',T('Show curve'),BURN_OPEN) + opt('burn','0',T('Collapse'),!BURN_OPEN)))
    + set(T('Terminal integration'), T('Auto = detected per session') + ' · ' + T('The «Terminal» button brings the session tab to the front; if it cannot, it copies a command.'),
          seg(T('Terminal integration'), [['auto',T('Auto')],['iterm','iTerm2'],['apple','Terminal.app'],['orca','Orca'],['off',T('Off', 'state')]]
        .map(x => opt('term', x[0], x[1], TERM_APP === x[0])).join('')));
}
function cfgPaneAl(){
  const opt = cfgOpt, set = cfgSet, seg = cfgSeg;
  return set(T('Alert level'), T('Important only badges questions, aborts and failures; completions collect quietly in the list.'),
          seg(T('Alert level'), opt('ap','imp',T('Important only'),APOL.preset==='imp') + opt('ap','all',T('Everything'),APOL.preset==='all')
            + opt('ap','custom',T('Custom'),APOL.preset==='custom')))
    // Per-kind rows only matter for «Custom»; a preset overwrites them (act.ap).
    + (APOL.preset !== 'custom' ? '' : [['ask', 'Awaiting answer', 'A session is waiting on a question or plan approval.'],
       ['abort', 'Aborted', 'A session was interrupted and needs a new instruction.'],
       ['flimit', 'Stopped by limit', 'A subagent stopped on the usage limit.'],
       ['fwreck', 'Half-edited files', 'A cut-off subagent left uncommitted files.'],
       ['fcheck', 'Cause needs a look', 'The cause text of a failure notice could not be read.'],
       ['fcut', 'Cut by external cause', 'Cut off by an external cause such as sleep, connection or overload.'],
       ['agent', 'Subagent done', 'A subagent finished.'],
       ['bgdone', 'Background done', 'A background job finished.']]
      .map(r => set(T(r[1]), T(r[2]), seg(T(r[1]), [['badge','Badge'],['list','List only'],['hide','hidden']]
        .map(x => opt('ak', r[0]+':'+x[0], T(x[1]), apolOf(r[0]) === x[0])).join('')))).join(''))
    + set(T('Group repeats per session (30 min)'), T('Consecutive cards with the same path and kind within 30 minutes collapse into one entry and count once on the badge.'),
          seg(T('Group repeats per session (30 min)'), opt('ag','1',T('On'),APOL.group) + opt('ag','0',T('Off'),!APOL.group)))
    + set(T('Cards in the alarm list'), T('Show the full alarm history or only unread cards.'),
          seg(T('Cards in the alarm list'), opt('uo','0',T('Full history'),!unreadOnly) + opt('uo','1',T('Unread only'),unreadOnly)))
    + set(T('Notify when a session waits for me'), ntfHint(),   // 43-notify.js
          seg(T('Notify when a session waits for me'), opt('osn','0',T('Off', 'state'),!ntfOn()) + opt('osn','1',T('On', 'state'),ntfOn())))
    + set(T('Also when this tab is visible'), T('When off, notifies only while this tab is hidden (another tab or minimized).'),
          seg(T('Also when this tab is visible'), opt('osv','0',T('Off', 'state'),!ntfPref().visible) + opt('osv','1',T('On', 'state'),ntfPref().visible)),
          false, ntfOn() ? '' : T('Unused while «Notify when a session waits for me» is off.'));
}
// «Target time» picked in the mode row but not applied yet: reveals the HH:MM input only, nothing is sent.
let SVPACE = false;
function cfgPaneSv(){
  const opt = cfgOpt, set = cfgSet, seg = cfgSeg;
  const sw = SVSW || {}, svm = sw.mode || 'auto', pace = SVPACE || svm === 'pace', cur = SVPACE ? 'pace' : svm;
  mpSrvLoad(false);   // compact hint reads the «Preferences» source (90b-mypref.js), read-only here
  const cch = mpCcHint(MPSRV && MPSRV.ok && MPSRV.keys);
  return '<div class=cfgsum><b id=svnow' + (SVERR ? ' class=err' : '') + '>' + esc(svNowLine()) + (SVERR ? ' — ' + esc(SVERR) : SVOK ? ' — ' + esc(T('Applied · all sessions')) : '') + '</b>'
      + '<span>' + esc(T('Same file as /saver — applies to every CLI session from its next prompt.')) + '</span></div>'
    + set(T('Mode'), T('Auto picks the stage from the target burn; Target time spreads 100% of the limit until that time; On pins a stage.')   // ⚠not the short mode key: it is the lowercase 'mode' used elsewhere
        + (pace ? ' ' + T('Enter as 24-hour HH:MM.') : ''),
          // One bar [«Auto» · «Target time» · «On» 1-4 · «Off»]; stages stay a compact "On 1-4" run inside it.
          '<div class="cfgseg cfgsegm" role=group aria-label="' + esc(T('Mode')) + '">'
          + opt('svm','auto',T('Auto'),cur==='auto') + opt('svm','pace',T('Target time'),cur==='pace')
          + '<span class=cfgsegl aria-hidden=true>' + esc(T('On')) + '</span>'
          + [1,2,3,4].map(n => { const on = cur==='on' && sw.stage===n, l = esc(T('On · stage ' + n));
              return '<button class="strp sn'+(on?' on':'')+'" data-svm="on'+n+'" title="'+l+'" aria-label="'+l+'"'+(on?' aria-pressed=true':'')+'>'+n+'</button>'; }).join('')
          + opt('svm','off',T('Off'),cur==='off') + '</div>'
          // ⚠text, not type=time: an empty time input renders «-- --:-»; svp already validates HH:MM.
          + (pace ? '<input class="svin svtm" id=svpt type=text inputmode=numeric maxlength=5 autocomplete=off placeholder="HH:MM" value="'
            + esc(svm==='pace' ? (sw.until||'') : '') + '" aria-label="' + esc(T('Target time')) + ' (HH:MM)">'
            + opt('svp','set',T('Apply'),false) + (svm==='pace' ? opt('svp','clear',T('Clear'),false) : '') : ''), pace)
    + set(T('Target burn'), T('Share of the 5-hour limit auto mode aims to use by the reset.'),
          // «No target», not «Off»: the mode row above already has an «Off»; the stored value is still goal=null.
          seg(T('Target burn'), opt('svg','off',T('No target'),sw.goal===null) + [50,80,100].map(g => opt('svg', g, g+'%', sw.goal===g)).join(''))
        + '<input class=svin id=svgn type=number min=0 max=100 step=1 value="' + esc(String(sw.goal == null ? '' : sw.goal)) + '" aria-label="' + esc(T('Target burn')) + '">'
        + opt('svg','n',T('Apply'),false), false, svm === 'auto' ? '' : T('Used only when the mode is «Auto».'))
    + set(T('At the target limit'), T('Notify only = just notify, as now · Warn, then allow = blocks the first prompt of each session; sending the same prompt again within 10 min goes through · Block = blocks both prompts and tool runs.')
        + ' ' + T('Starting a prompt with «{kw}» lifts it for that session for 30 min.').replace('{kw}', '한도해제'),   // keyword matched by the saver hook, not UI
          seg(T('At the target limit'), ['advise','warn','block'].map(k => opt('svl', k, T(SV_LIM[k]), (sw.limit || 'advise') === k)).join('')))
    + (cch ? '<div class="cfgpd svcc">' + esc(cch) + ' · <a href="#" id=svccgo>' + esc(T('change it in My settings')) + '</a></div>' : '')
    + svLevelsFold();
}
// «What each level does»: table copied from the hook snapshot (`levels` / `how`, saver.py RULES); hidden when absent.
// ⚠Rule text is snapshot data, so it is escaped and never passed through T().
function svLevelsFold(){
  const L = typeof SV !== 'undefined' && SV && Array.isArray(SV.levels) ? SV.levels : null;   // typeof: JS tests load a subset of files
  if(!L || !L.length) return '';
  const cur = SV.mode === 'off' ? -1 : (Number(SV.stage) || 0);
  const rows = L.map(e => '<tr' + (e.lv === cur ? ' class=on aria-current=true' : '') + '><td>' + esc(String(e.lv)) + '</td><td>'
    + esc(e.cap == null ? T('No cap') : String(e.cap)) + '</td><td>' + (e.rules || []).map(esc).join('<br>') + '</td></tr>').join('');
  const how = Array.isArray(SV.how) ? '<ul class=svlvh>' + SV.how.map(x => '<li>' + esc(x) + '</li>').join('') + '</ul>' : '';
  return '<details class=svlv' + (lsGet('sidereus.svlv', '') === '1' ? ' open' : '') + '><summary>' + esc(T('What each level does')) + '</summary>'
    + '<table class=svlvt><thead><tr><th>' + esc(T('Level')) + '</th><th>' + esc(T('Max concurrent agents')) + '</th><th>' + esc(T('Rules added')) + '</th></tr></thead><tbody>'
    + rows + '</tbody></table>' + how + '</details>';
}
function cfgPaneTl(){
  const opt = cfgOpt, set = cfgSet, seg = cfgSeg, sel = cfgSel;
  const base = [1,3,6,12,24,48], hrs = base.includes(tlHours) ? base : base.concat([tlHours]).sort((a,b)=>a-b);
  return set(T('Replay speed'), T('Timeline time played per second of replay.'),
          seg(T('Replay speed'), TL_RSP.map(x => opt('rp', x[0], T(x[1]), tlRpSpeed === x[0])).join('')))
    + set(T('Refresh interval'), T('How often the timeline reloads.'),
          sel('ta', T('Refresh interval'), TL_EVERY.map(x => [x[0], x[0] ? T(x[1]) : T('Manual')]), tlAuto))
    + set(T('Range'), T('Recent period the timeline shows.'),
          sel('th', T('Range'), hrs.map(h => [h, rangeLbl(h)]), tlHours))
    + set(T('Show task description on subagent rows'), T('Labels subagent rows by the one-line task description given to the subagent, with the type as a chip. Off shows the type only.'),
          seg(T('Show task description on subagent rows'), opt('agd','1',T('On'),tlAgDesc) + opt('agd','0',T('Off'),!tlAgDesc)));
}
function cfgPaneVw(views){
  return '<div class=cfgpd>' + esc(T('Apply switches to that view and closes settings.')) + '</div>'
    + views.map((it, i) => cfgSet(it.n || T('(unnamed)'), '', cfgOpt('vw', i, T('Apply'), false))).join('');
}
// Category glyphs, self-drawn 16x16 line art (07-file-icons.js conventions); tile styling in 85-palette-settings.css.
const CFG_ICO = {
  disp: '<rect x="2" y="2.5" width="12" height="8.5" rx="1.5"/><path d="M6 14h4M8 11v3"/>',
  al: '<path d="M4.5 11V7.2a3.5 3.5 0 0 1 7 0V11l1 1.2h-9z"/><path d="M6.8 14h2.4"/>',
  sv: '<path d="M2.5 11.5a5.5 5.5 0 0 1 11 0"/><path d="M8 11.5l2.6-3.4"/><circle cx="8" cy="11.5" r=".9" fill="currentColor"/>',
  tl: '<path d="M2 8h12"/><circle cx="4.5" cy="8" r="1.4"/><circle cx="11.5" cy="8" r="1.4"/><path d="M8 4.5v7"/>',
  vw: '<path d="M4.5 2h7v12L8 11.2 4.5 14z"/>',
  me: '<circle cx="8" cy="5.5" r="2.5"/><path d="M3 13.5a5 5 0 0 1 10 0"/>',
  dx: '<path d="M2 8h3l1.5-4 3 8L11 8h3"/>',
};
const cfgIco = k => CFG_ICO[k] ? '<span class=cfgic aria-hidden=true><svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false"'
  + ' fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">' + CFG_ICO[k] + '</svg></span>' : '';
function cfgShell(cats, cat, pane){
  return '<div class=cfgh><b id=cfgmt>' + esc(T('Settings')) + '</b><span>' + esc(T('Display settings are saved on the viewer server and shared by every browser; saver mode applies to every session.')) + '</span>'
      + '<button class=cfgtour id=cfgtour>' + esc(T('Replay the tour')) + '</button>'
      + '<button class=cfgx id=cfgx title="' + esc(T('Close')) + '" aria-label="' + esc(T('Close')) + '">✕</button></div>'
    + '<div class=cfgbd><nav class=cfgnav aria-label="' + esc(T('Settings categories')) + '">'
    + cats.map(c => '<button class="cfgnv' + (c[0] === cat ? ' on' : '') + '" data-cat=' + c[0] + (c[0] === cat ? ' aria-current=true' : '') + '>' + cfgIco(c[0]) + esc(c[1]) + '</button>').join('')
    + '</nav><div class=cfgpn data-cat=' + cat + '>' + pane + '</div></div>';
}
// Each row calls what its original control calls (or clicks that control), then repaints and keeps focus.
function cfgActs(){
  return Object.assign(mpActs(), {   // «Preferences» actions (90b-mypref.js)
    lang: v => setLang(v),
    tone: v => setTheme(v),
    fs:   v => setFs(v),   // no full() — CSS reflows; cfgBind repaints only the modal
    ls:   v => sesdrPin(v === '1', false),
    wks:  v => { wkSideSet(v === '1'); buildWku(); if(mainView === 'token') paintToken(); },
    term: v => termSet(v),   // 88d-term.js
    dxr:  () => dxLoad(true),   // «Diagnostics» Refresh (90e-diag.js)
    burn: v => { BURN_OPEN = (v === '1'); lsSet('sidereus.burn', BURN_OPEN?'1':'0'); buildBurn(); },
    uo:   v => { if((v === '1') !== unreadOnly){ const t = document.getElementById('aunread'); if(t) t.click(); } },
    ap:   v => { APOL.preset = v; if(v !== 'custom') APOL.kinds = Object.assign({}, APOL_PRESET[v]); apolSave(); buildAlarm(); },
    ak:   v => { const p = v.split(':'); APOL.kinds[p[0]] = p[1]; APOL.preset = 'custom'; apolSave(); buildAlarm(); },
    ag:   v => { APOL.group = (v === '1'); apolSave(); buildAlarm(); },
    osn:  v => ntfSet(v === '1', paintCfg),   // permission prompt resolves later, so it repaints itself
    osv:  v => ntfVisSet(v === '1'),
    rp:   v => { tlRpSpeed = +v; lsSet('mbTlRp', tlRpSpeed); if(mainView === 'time') paintTl(); },
    ta:   v => { tlAuto = +v; lsSet('mbTlAuto', tlAuto);
                 if(mainView === 'time'){ if(tlAuto) loadTl(true); else paintTl(); } },
    th:   v => { tlHours = +v; lsSet('mbTlHours', tlHours); if(mainView === 'time') loadTl(true); },
    agd:  v => { tlAgDesc = (v === '1'); lsSet('sidereus.agdesc', tlAgDesc ? '1' : '0'); if(mainView === 'time') paintTl(); },
    vw:   v => { const it = vwLoad()[+v]; cfgClose(); if(it) vwApply(it); },
    svl:  v => { SVERR = ''; return svLimSet(v); },   // any new saver action drops the stale error; ⚠return the save promise so cfgBind refocuses after the async repaint
    svm:  v => { SVERR = ''; SVPACE = v === 'pace'; if(!SVPACE) return svSet(v.startsWith('on') ? {mode:'on', stage:+v.slice(2)} : {mode:v}); },
    svg:  v => { SVERR = ''; if(v !== 'n') return svSet({goal: v === 'off' ? null : +v});
                 const el = document.getElementById('svgn'), n = el ? el.value.trim() : '';
                 if(/^\d+$/.test(n) && +n <= 100) return svSet({goal: +n}); else { SVERR = T('Check the value') + ': ' + T('integer 0-100'); } },
    svp:  v => { SVERR = ''; if(v === 'clear'){ SVPACE = false; return svSet({mode:'auto'}); }
                 const el = document.getElementById('svpt'), t = el ? el.value.trim() : '';
                 if(/^([01]\d|2[0-3]):[0-5]\d$/.test(t)) return svSet({mode:'pace', until:t}); else { SVERR = T('Check the value') + ': ' + T('HH:MM format'); } },
  });
}
// ⚠A repaint can drop the pressed button (save/undo vanish once clean): fall back to the same row's control, then the category tab, never BODY.
function cfgRefocus(box, k, v){
  const nb = box.querySelector('.strp[data-'+k+'="'+v+'"]') || box.querySelector('[data-k="'+k+'"]:not([disabled])')
    || box.querySelector('.strp[data-'+k+']') || box.querySelector('.cfgnv[data-cat="'+CFGCAT+'"]');
  if(nb) nb.focus();
}
function cfgBind(box){
  const x = document.getElementById('cfgx'); if(x) x.onclick = () => cfgClose();
  const tb = document.getElementById('cfgtour'); if(tb) tb.onclick = () => { cfgClose(); tourOpen(0); };   // 98b-tour.js
  box.querySelectorAll('.cfgnv').forEach(b => b.onclick = () => {
    CFGCAT = b.dataset.cat; tabSet('sidereus.cfgcat', CFGCAT);
    paintCfg(); const nb = box.querySelector('.cfgnv[data-cat="' + CFGCAT + '"]'); if(nb) nb.focus();
  });
  const act = cfgActs();
  Object.keys(act).forEach(k => box.querySelectorAll('.strp[data-'+k+']').forEach(b => b.onclick = () => {
    const v = b.dataset[k], p = act[k](v);
    if(k === 'vw') return;
    paintCfg(); cfgRefocus(box, k, v);
    if(p && typeof p.then === 'function') p.then(() => { const a = document.activeElement; if(!a || a === document.body) cfgRefocus(box, k, v); });   // async save repaints again when it lands
  }));
  box.querySelectorAll('input.cfgck[data-k]').forEach(c => c.onchange = () => {   // checkbox -> act[k]('value:1|0')
    const k = c.dataset.k, v = c.value; if(!act[k]) return; act[k](v + ':' + (c.checked ? 1 : 0)); paintCfg();
    const nc = box.querySelector('input.cfgck[data-k="'+k+'"][value="'+v+'"]'); if(nc) nc.focus();
  });
  const cg = document.getElementById('svccgo');   // compact hint link: same path as the «Preferences» category button, then the threshold field
  if(cg) cg.onclick = e => { e.preventDefault(); const nv = box.querySelector('.cfgnv[data-cat="me"]'); if(!nv) return; nv.click();
    const f = box.querySelector('[data-mpcin="cc_compact_window"]'); if(f){ f.scrollIntoView({block: 'center'}); f.focus(); } };
  const svl = box.querySelector('details.svlv');   // level table fold; open state survives repaints
  if(svl) svl.ontoggle = () => lsSet('sidereus.svlv', svl.open ? '1' : '0');
  const adv = box.querySelector('details.mpadv');   // «Advanced» fold (90b-mypref.js); open state survives repaints and reloads
  if(adv) adv.ontoggle = () => lsSet('sidereus.cfgadv', adv.open ? '1' : '0');
  box.querySelectorAll('select.cfgsel[data-k]').forEach(s => s.onchange = () => {
    const k = s.dataset.k; if(!act[k]) return; act[k](s.value); paintCfg();
    const ns = box.querySelector('select.cfgsel[data-k="'+k+'"]'); if(ns) ns.focus();
  });
}
// Selectors for the same control after a repaint: id, then every data-* pair, then the first data key alone.
function cfgFocusSel(el){
  const q = s => String(s).replace(/["\\]/g, '\\$&'), tag = String(el.tagName || '').toLowerCase();
  const at = Object.keys(el.dataset || {}).map(k => 'data-' + k.replace(/[A-Z]/g, c => '-' + c.toLowerCase()));
  const out = el.id ? ['[id="' + q(el.id) + '"]'] : [];
  if(at.length) out.push(tag + at.map(a => '[' + a + '="' + q(el.getAttribute(a)) + '"]').join(''), tag + '[' + at[0] + ']');
  return out;
}
// ⚠innerHTML drops the focused control and focus falls to BODY, where #cfgm's Esc/Tab handler never sees keys: refocus the equivalent control, else the dialog box.
function cfgFocusBack(box, sels){
  for(const s of sels){ const n = box.querySelector(s + ':not([disabled])'); if(n){ n.focus(); if(document.activeElement === n) return; } }
  box.focus();
}
function paintCfg(){
  const m = document.getElementById('cfgm'), box = document.getElementById('cfgbox');
  if(!m || !box || m.hidden) return;
  const ae = document.activeElement, fk = ae && box.contains && box.contains(ae) ? cfgFocusSel(ae) : null;
  const views = vwLoad();
  const dx = typeof cfgPaneDx === 'function' && !(typeof FEATS === 'object' && FEATS && FEATS.diag === false);   // «Diagnostics» (90e-diag.js): route 404s with the feature off
  const cats = [['disp', T('Display')], ['al', T('Alerts')], ['sv', T('Saver mode')], ['tl', T('Timeline')], ['me', T('Preferences')]]
    .concat(dx ? [['dx', T('Diagnostics')]] : [], views.length ? [['vw', T('Saved views')]] : []);
  const cat = cats.some(c => c[0] === CFGCAT) ? CFGCAT : 'disp';   // ⚠don't persist the fallback: views may come back
  const oldPn = box.querySelector('.cfgpn'), keepTop = (oldPn && oldPn.dataset.cat === cat) ? oldPn.scrollTop : 0;
  const body = {disp: cfgPaneDisp, al: cfgPaneAl, sv: cfgPaneSv, tl: cfgPaneTl, me: cfgPaneMe, dx: typeof cfgPaneDx === 'function' ? cfgPaneDx : null}[cat];
  const pane = '<div class=cfgpt>' + esc(cats.find(c => c[0] === cat)[1]) + '</div>' + (body ? body() : cfgPaneVw(views));
  box.innerHTML = cfgShell(cats, cat, pane);
  // ⚠Mount the mailbox-watch section before restoring scroll: the observer adds it later and the shorter pane clamped scrollTop.
  if(typeof mwMount === 'function') mwMount();
  const pn = box.querySelector('.cfgpn'); if(pn && keepTop) pn.scrollTop = keepTop;
  cfgBind(box);
  if(fk && !box.contains(document.activeElement)) cfgFocusBack(box, fk);
}
// Modal shell: backdrop click / X / Esc close; Tab is trapped inside; focus returns to the gear.
function cfgOpen(){
  const m = document.getElementById('cfgm'), g = document.getElementById('gear');
  if(!m) return;
  // ⚠#gear's click stops propagation, so the alarm's bubbling outside-click never closes it — close it here (★ 2026-09-27 interaction audit).
  if(alarmOpen) openAlarm(false);
  for(const q of UIPOPS) if(popIsOpen(q.id)) q.close(false);   // UIPOPS popovers opened without a click (keyboard paths)
  m.hidden = false;
  if(g){ g.classList.add('on'); g.setAttribute('aria-expanded', 'true'); }
  paintCfg();
  const f = m.querySelector('.strp.on') || m.querySelector('button'); if(f) f.focus();
}
function cfgClose(){
  const m = document.getElementById('cfgm'), g = document.getElementById('gear');
  if(!m || m.hidden) return;
  m.hidden = true;
  if(g){ g.classList.remove('on'); g.setAttribute('aria-expanded', 'false'); g.focus(); }
}
(() => {
  const m = document.getElementById('cfgm'), g = document.getElementById('gear');
  if(g) g.onclick = (e) => { e.stopPropagation(); if(m && m.hidden) cfgOpen(); else cfgClose(); };
  if(!m) return;
  m.addEventListener('click', e => { if(e.target === m) cfgClose(); });
  // ⚠stopPropagation keeps the document-level Esc handlers (diff popup, palette) from also firing.
  m.addEventListener('keydown', e => {
    if(e.key === 'Escape'){ e.preventDefault(); e.stopPropagation(); cfgClose(); return; }
    if(e.key !== 'Tab') return;
    const fs = [...m.querySelectorAll('button,select,input,a[href],summary,[tabindex]:not([tabindex="-1"])')].filter(x => !x.disabled);
    if(!fs.length) return;
    const a = fs[0], z = fs[fs.length-1], i = fs.indexOf(document.activeElement);   // i < 0: focus on #cfgbox itself (paintCfg fallback), keep it inside
    if(e.shiftKey && i <= 0){ e.preventDefault(); z.focus(); }
    else if(!e.shiftKey && (i < 0 || document.activeElement === z)){ e.preventDefault(); a.focus(); }
  });
})();
