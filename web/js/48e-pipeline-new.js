// «+ New pipeline»: name + title + template -> preview of the whole new file -> «Confirm» creates it.
// Server: POST /api/pipelines/create (sidereus/pipeline.py create — Origin, known_projects, never overwrites).
// «empty» first and default: «+ New pipeline» starting from a full change flow read as a copy of an existing pipeline.
const PL_TPLS = [['empty', 'Empty pipeline (one stage)'], ['change', 'Change (design→implement→verify→review→re-verify)'],
  ['bugfix', 'Bug fix (reproduce→cause→fix→regression)'], ['triage', 'Triage'], ['live', 'Live check'],
  ['cross-review', 'Cross-review (Codex)']];
let PLNEW = null;            // open form {name, title, tpl, diff, busy, err}
// A disabled button says why (one form at a time) — a silent dead click read as a bug.
function plNewDis(on){ return on ? ' disabled title="' + esc(T('Close the open form first')) + '"' : ''; }
// Empty project, no suggestions: template buttons in place of a note; a click only opens the preview (create still needs «Confirm — create»).
// One filled primary (AI draft, or the template start when no session can receive it) then the outlined other; same attributes and disable rules as the «+ New ▾» items, so the existing handlers do the work.
// ⚠No session that can receive the DM (live + mailbox login): the template start is the primary, else the AI draft is a dead end.
function plStartBtns(){
  const live = plSessions(PLS.proj).some(x => x.login);
  const ai = '<button type=button class="wkrgb' + (live ? ' plsv' : '') + '" data-pldnew' + plNewDis(PLDRAFT) + '>' + esc(T('Ask AI for a draft')) + '</button>';
  const st = '<button type=button class="wkrgb' + (live ? '' : ' plsv') + (PLSTD ? ' on' : '') + '" data-plstd>' + esc(T('Start from a template')) + '</button>';
  return live ? ai + st : st + ai;
}
let PLTPLO = false;          // quick-template row open (folded at first, not persisted)
function plTplPick(){
  return '<div class=pltpl>' + plStartBtns() + '<button type=button class="wkrgb' + (PLTPLO ? ' on' : '') + '" data-pltplo aria-expanded="' + (PLTPLO ? 'true' : 'false') + '">'
    + esc(T('Quick templates ▾')) + '</button>' + (PLTPLO ? PL_TPLS.map(([k, lab]) =>
    '<button type=button class=wkrgb data-pltpl="' + esc(k) + '"' + plNewDis(PLNEW || PLDRAFT) + '>' + esc(T(lab)) + '</button>').join('') : '') + '</div>';
}
// «+ New ▾» menu: the four ways to start a pipeline behind one button (one head row at 900px). Items keep their own attributes and handlers.
// pri: primary fill when the project has no pipelines and no start buttons are shown (the empty state fills 48e plStartBtns instead)
// ⚠The menu renders inside .plw: every item handler (here and 48e PLDRAFT) returns early for a click outside .plw.
let PLNEWM = false;          // menu open
function plNewBtn(pri){
  const it = (cls, attr, dis, lab) => '<button type=button role=menuitem class="wkrgb' + cls + '" ' + attr + dis + '>' + esc(lab) + '</button>';
  return '<span class=plnewmw><button type=button class="wkrgb' + (pri ? ' plsv' : '') + (PLNEWM ? ' on' : '') + '" data-plnewm aria-haspopup=menu aria-expanded="' + (PLNEWM ? 'true' : 'false') + '">'
    + esc(T('+ New ▾')) + '</button>' + (PLNEWM ? '<div class=plnewm role=menu aria-label="' + esc(T('New pipeline')) + '">'
    + it('', 'data-plnew', plNewDis(PLNEW), T('+ New pipeline')) + it('', 'data-plimp', plNewDis(PLNEW), T('Import from another project'))
    + it('', 'data-pldnew', plNewDis(PLDRAFT), T('Ask AI for a draft')) + it(PLSTD ? ' on' : '', 'data-plstd', '', T('Standard templates')) + '</div>' : '') + '</span>';
}
function plNewMenu(on){ PLNEWM = !!on; plPaint(); plRefocus(on ? '.plnewm button:not([disabled])' : '[data-plnewm]'); }
document.addEventListener('click', e => {
  if(!PLNEWM || !e.target.closest) return;
  // Capture phase: an item click closes the menu before its own handler repaints.
  if(e.target.closest('[data-plnewm]')) return;
  if(e.target.closest('.plnewm')){ if(e.target.closest('.plnewm button')) PLNEWM = false; return; }
  // ⚠Outside click: drop the menu node without a repaint — a rebuild here would detach e.target and swallow the click.
  PLNEWM = false;
  document.querySelectorAll('.plw .plnewm').forEach(m => m.remove());
  document.querySelectorAll('.plw [data-plnewm]').forEach(b => { b.classList.remove('on'); b.setAttribute('aria-expanded', 'false'); });
}, true);
document.addEventListener('click', e => {
  if(e.target.closest && e.target.closest('.plw [data-plnewm]')) plNewMenu(!PLNEWM);
});
document.addEventListener('keydown', e => {
  if(!PLNEWM || !e.target.closest || !e.target.closest('.plnewmw')) return;
  if(e.key === 'Escape'){ e.preventDefault(); e.stopPropagation(); plNewMenu(false); return; }
  if(e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
  const bs = [...document.querySelectorAll('.plw .plnewm button:not([disabled])')];
  if(!bs.length) return;
  e.preventDefault();
  bs[ppStep(bs.indexOf(e.target), e.key === 'ArrowDown' ? 1 : -1, bs.length)].focus({ preventScroll: true });
});
function plNewNameErr(name){
  const d = PLS.data[PLS.proj], have = ((d && d.pipelines) || []).map(x => x.name);
  if(!/^[a-z0-9-]{1,40}$/.test(name || '')) return T('Name: lowercase letters, digits and -, up to 40');
  return have.includes(name) ? T('That name already exists') : '';
}
function plNewForm(){
  if(!PLNEW) return plStdList() + plDraftForm() + (PLS.draft && Date.now() - PLS.draft.at < PL_DRAFT_TTL ? plDraftStrip(PLS.draft, ACK, PLS.data, PLS.proj) : '');
  const nerr = PLNEW.name ? plNewNameErr(PLNEW.name) : '';
  return plStdList() + '<div class=plnew><div class=brh2><b>' + esc(T('New pipeline')) + '</b> <i>' + esc(strShort(PLS.proj)) + '/.claude/pipelines/</i></div>'
    + '<label class=plfr><span>' + esc(T('Name')) + '</span><input data-plnf=name maxlength=40 value="' + esc(PLNEW.name) + '" placeholder="bugfix"></label>'
    + '<div class="plfd plnerr">' + esc(nerr) + '</div>'
    + '<label class=plfr><span>' + esc(T('Title')) + '</span><input data-plnf=title maxlength=80 value="' + esc(PLNEW.title) + '"></label>'
    + (PLNEW.src === 'other' ? plImpPick() : '<label class=plfr><span>' + esc(T('Template')) + '</span><select data-plnf=tpl>' + plTplList().map(([k, lab]) =>
      '<option value="' + esc(k) + '"' + (k === PLNEW.tpl ? ' selected' : '') + '>' + esc(lab) + '</option>').join('') + '</select></label>')
    + (PLNEW.replaced && PLNEW.replaced.length ? '<div class="plfd plnerr">' + esc(T('Agents missing here, set to general-purpose') + ': ' + PLNEW.replaced.join(', ')) + '</div>' : '')
    + '<div class=plfd>' + esc(T('Agents the project lacks become general-purpose · edit them on the canvas afterwards')) + '</div>'
    + (PLNEW.diff ? '<pre>' + diffHtml(PLNEW.diff, agLang('x.json')) + '</pre>' : '')
    + (PLNEW.err ? '<div class="plfd plnerr">' + esc(PLNEW.err) + '</div>' : '')
    + '<div class=plbar>' + (PLNEW.diff
      ? '<button class="wkrgb" data-plnok' + (PLNEW.busy ? ' disabled' : '') + '>' + esc(T('Confirm — create')) + '</button>'
      : '<button class="wkrgb" data-plnprev' + (PLNEW.busy || !PLNEW.name || nerr || (PLNEW.src === 'other' && !PLNEW.fname) ? ' disabled' : '') + '>' + esc(T('Preview')) + '</button>')
    + plBackBtn('data-plnx') + '</div></div>';
}
// «Cancel» on every unsaved draft / new form (Standard draft · «+ New» form incl. quick templates · AI draft): closes it, writes nothing. Esc does the same (plDraftEsc).
// Not «Back»: a form opened straight from the empty-state buttons has no previous step, and «Edit» uses «Cancel» for the same discard.
function plBackBtn(attr){
  const t = esc(T('Close this draft without saving'));
  return '<button type=button class="wkrgb plback" ' + attr + ' title="' + t + '" aria-label="' + t + '">' + esc(T('Cancel')) + '</button>';
}
// ⚠These layers close on Esc without preventDefault (60 drawer · 35c popup · 80 code popup · 40 Cmd+K) or after us (92d overlay rail): one Esc must close only them.
function plEscOwned(){
  return (typeof SDRW_OPEN !== 'undefined' && SDRW_OPEN) || (typeof ISPOP !== 'undefined' && ISPOP) || (typeof strPop !== 'undefined' && !!strPop)
    || (typeof cpOn !== 'undefined' && cpOn)
    || (typeof railOpen !== 'undefined' && railOpen && typeof railMode === 'function' && railMode(innerWidth, railOpen) === 'overlay');
}
// ⚠The menus' own Esc listeners (48b PLRV/PLPSK, 48d PLAPK) run before ours and clear their flag: a capture-phase snapshot keeps one Esc for the menu only.
let PLESC_MENU = false;
function plMenuOpen(){ return !!(PLNEWM || PLRV || PLPSK || PLAPK || PLRUN); }   // PLRUN = inline run panel (48b)
function plEscSnap(e){ if(e.key === 'Escape') PLESC_MENU = plMenuOpen(); }
// Esc closes the innermost open draft (form first, then the Standard draft); never from a field, never over an open menu (they own Esc).
function plDraftEsc(e){
  if(e.key !== 'Escape' || e.defaultPrevented || mainView !== 'pipe') return false;
  const t = e.target;
  if(t && /^(INPUT|SELECT|TEXTAREA)$/.test(t.tagName || '')) return false;
  if(PLESC_MENU || plMenuOpen()) return false;
  if(plEscOwned()) return false;
  if(PLNEW) PLNEW = null; else if(PLDRAFT) PLDRAFT = null; else if(PLS.std) PLS.std = ''; else return false;
  plPaint();
  return true;
}
document.addEventListener('keydown', plEscSnap, true);   // pure snapshot: never stops the event
document.addEventListener('keydown', plDraftEsc);
// Templates + this project's «Suggested» (agent-name guesses from GET suggest[]; the server rebuilds them on create).
function plTplList(){
  return PL_TPLS.map(([k, lab]) => [k, T(lab)]).concat(((PLS.data[PLS.proj] || {}).suggest || []).map(x =>
    ['suggest:' + x.name, T('Suggested') + ' · ' + plgTplShow(x.title) + ' (' + x.stages.map(s => plgShow(s.title)).join('→') + ')'])).concat(((PLS.data[PLS.proj] || {}).std || []).map(x =>
    ['std:' + x.name, T('Standard templates') + ' · ' + plgTplShow(x.title) + ' (' + (x.chain || []).map(c => plgShow(c.title)).join('→') + ')']));   // display names only
}
// «Standard templates»: GET std[] cards;
// «Open draft» = PLS.std -> unsaved canvas (plStdBody), saved only through the normal create preview + «Confirm» (tpl 'std:<key>').
let PLSTD = false;           // card panel open
function plStdList(){
  if(!PLSTD) return '';
  const st = (PLS.data[PLS.proj] || {}).std || [];
  if(!st.length) return '<div class=hidnote>' + esc(T('No standard templates')) + '</div>';
  return '<div class=plstd>' + st.map(x => '<div class="plstdc' + (PLS.std === x.name ? ' on' : '') + '"><b>' + esc(plgTplShow(x.title)) + '</b>'   // display names only (06-i18n-w.js); the draft keeps the saved titles
    + '<div class=plstdch>' + (x.chain || []).map(c => c.opt ? '<span class=plstdopt>' + esc(plgShow(c.title) + ' ' + T('(optional)')) + '</span>' : '<span>' + esc(plgShow(c.title)) + '</span>').join(' → ') + '</div>'
    + ((x.gp || []).length ? '<div class=plstdgp>' + esc(T('No agent') + ': ' + x.gp.map(plgShow).join(', ')) + '</div>' : '')
    + '<div class=plbar>' + (/^https:\/\//.test(x.src || '') ? '<a href="' + esc(x.src) + '" target=_blank rel=noopener title="' + esc(x.src) + '">' + esc(T('Source', 'origin')) + '</a>' : '')   // ⚠https only
    + '<button class="wkrgb" data-plstdopen="' + esc(x.name) + '">' + esc(T('Open draft')) + '</button></div></div>').join('') + '</div>';
}
// Std draft view, like plSugBody; the canvas row is keyed 'std:<key>' (plCur) so it never shares an editor entry with a saved file.
function plStdBody(d, p, hd){
  const ps = d.pipelines || [], cv = plCanvas(p, d, null);
  return plHeadRow(hd, plPickHtml(ps, null, []) + plNewBtn()) + plNewForm()
    + plDraftBand(T('Standard templates'), T("A published standard process mapped to this project's agents — edit it after saving"))
    + '<div class=plbar><b>' + esc(plgTplShow(p.title)) + '</b><span class=plact>' + plBackBtn('data-plstdx')
    + '<button class="wkrgb plsv" data-plstdsave' + (PLNEW ? ' disabled' : '') + '><span aria-hidden=true>✓</span> ' + esc(T('Save this draft')) + '</button></span></div>' + cv.html;
}
// Unsaved draft band (std / suggestion): says it is not saved; the save button is the primary in the bar's action group.
function plDraftBand(kind, why){
  return '<div class="plsugb plmband pldraftb"><span aria-hidden=true>✎</span> <b>' + esc(T('Draft — not saved yet')) + '</b> <i>' + esc(kind) + '</i> <span>' + esc(why) + '</span></div>';
}
// A project without pipelines opens on its first
// suggestion, unsaved. ⚠Never auto-saved or sent; «Save this suggestion» = the normal create preview + «Confirm».
function plSugBody(d, ex, hd){   // ex = extra chips (48h Sidereus pipeline) · hd = head row sink (48 plHeadRow)
  const sg = d.suggest, i = Math.min(PLS.sugI || 0, sg.length - 1), p = sg[i], cv = plCanvas(p, d, null);
  const sel = sg.length > 1 ? plComboHtml({ cur: 'sug:' + i, items: sg.map((x, k) => ({ p: 'sug:' + k, name: T('Suggested') + ' · ' + x.title })) }) : '';
  return plHeadRow(hd, sel + plNewBtn() + (ex || '')) + plNewForm() + '<div class=pltpl>' + plStartBtns() + '</div>'
    + plDraftBand(T('Suggested'), T('Guessed from agent names — edit it after saving'))
    + '<div class=plbar><b>' + esc(p.title) + '</b><span class=plact><button class="wkrgb plsv" data-plsugsave' + (PLNEW ? ' disabled' : '') + '><span aria-hidden=true>✓</span> ' + esc(T('Save this suggestion')) + '</button></span></div>' + cv.html;
}
// «Import from another project»: known project with pipelines -> one of its valid pipelines.
function plImpPick(){
  const ps = ((PLS.projs && PLS.projs.projects) || []).map(x => x.path), src = PLS.data[PLNEW.fproj];
  const names = ((src && src.pipelines) || []).filter(x => x.ok).map(x => x.name);
  return '<label class=plfr><span>' + esc(T('Project')) + '</span><select data-plnf=fproj><option value="">—</option>' + ps.map(p =>
      '<option value="' + esc(p) + '"' + (p === PLNEW.fproj ? ' selected' : '') + '>' + esc(strShort(p)) + '</option>').join('') + '</select></label>'
    + '<label class=plfr><span>' + esc(T('Pipeline')) + '</span><select data-plnf=fname><option value="">—</option>' + names.map(n =>
      '<option value="' + esc(n) + '"' + (n === PLNEW.fname ? ' selected' : '') + '>' + esc(n) + '</option>').join('') + '</select></label>';
}
async function plNewSend(write){
  if(!PLNEW || PLNEW.busy || plNewNameErr(PLNEW.name)) return;
  PLNEW.busy = true; PLNEW.err = ''; plPaint();
  let r;
  const body = { proj: PLS.proj, name: PLNEW.name, title: PLNEW.title, dry: !write };
  if(PLNEW.src === 'other') body.from = { proj: PLNEW.fproj, name: PLNEW.fname }; else body.template = PLNEW.tpl;
  try{ r = await postJSON('/api/pipelines/create', body); }
  catch(x){ r = x.body || { ok: false, err: String((x && x.message) || x) }; }
  if(!PLNEW) return;
  PLNEW.busy = false;
  if(!r || !r.ok){ PLNEW.err = T('Could not create') + ' — ' + ((r && r.err) || '') + (r && r.errs ? ' (' + r.errs.join(' · ') + ')' : ''); PLNEW.diff = ''; }
  else if(!write){ PLNEW.diff = r.diff || ''; PLNEW.replaced = r.replaced || []; }
  else { plModeSet('edit', true); PLS.sel = r.name; PLS.std = ''; PLS.msg = T('Created') + ' · .claude/pipelines/' + r.name + '.json'; PLNEW = null; PLS.projs = null; await Promise.all([plLoadProjs(), plLoad(PLS.proj, true)]); }
  plPaint(); plRefocus('[data-plnok]:not([disabled])', '[data-plnprev]:not([disabled])', '[data-plnf=name]', '[data-ppk="plsel"]');
}
document.addEventListener('click', e => {
  if(!e.target.closest || !e.target.closest('.plw')) return;
  if(e.target.closest('[data-plnew]')){ PLNEW = { name: '', title: '', tpl: 'empty', diff: '', busy: false, err: '' }; PLDRAFT = null; plPaint(); plRefocus('[data-plnf=name]'); return; }
  if(e.target.closest('[data-pltplo]')){ PLTPLO = !PLTPLO; plPaint(); plRefocus('[data-pltplo]'); return; }
  if(e.target.closest('[data-plstd]')){ PLSTD = !PLSTD; plPaint(); plRefocus(PLSTD ? '.plstd [data-plstdopen]' : '', '[data-plnewm]'); return; }
  const so = e.target.closest('[data-plstdopen]');
  if(so){ PLS.std = so.dataset.plstdopen; PLS.diff = null; PLS.msg = ''; plPaint(); plRefocus('[data-plstdsave]:not([disabled])', '[data-plnewm]'); return; }   // list stays open: nothing is saved yet, the card shows .on for the opened draft
  if(e.target.closest('[data-plstdx]')){ PLS.std = ''; PLS.msg = ''; plPaint(); return; }   // close the unsaved draft; nothing was written
  if(e.target.closest('[data-plstdsave]')){ const p = plCur(); if(p && p.std){ PLNEW = { name: p.key, title: p.title, tpl: 'std:' + p.key, diff: '', busy: false, err: '' }; PLDRAFT = null; plPaint(); } return; }
  if(e.target.closest('[data-plsugsave]')){ const p = plCur(); if(p && p.suggest){ PLNEW = { name: p.name, title: '', tpl: 'suggest:' + p.name, diff: '', busy: false, err: '' }; PLDRAFT = null; plPaint(); } return; }
  const tp = e.target.closest('[data-pltpl]');
  if(tp){ if(PLNEW || PLDRAFT) return; const k = tp.dataset.pltpl; PLNEW = { name: k === 'empty' ? 'main' : k, title: '', tpl: k, diff: '', busy: false, err: '' }; return plNewSend(false); }
  if(e.target.closest('[data-plimp]')){ PLNEW = { src: 'other', fproj: '', fname: '', name: '', title: '', diff: '', busy: false, err: '' }; PLDRAFT = null; plPaint(); return; }
  if(e.target.closest('[data-plnx]')){ PLNEW = null; plPaint(); return; }
  if(e.target.closest('[data-plnprev]')) return plNewSend(false);
  if(e.target.closest('[data-plnok]')) return plNewSend(true);
});
// Typing keeps the caret: state + the name check update in place; a changed field drops a stale preview.
document.addEventListener('input', e => {
  const el = e.target;
  if(!PLNEW || !el || !el.dataset || el.dataset.plnf == null || !el.closest('.plnew')) return;
  PLNEW[el.dataset.plnf] = el.value;
  const f = el.closest('.plnew'), m = f.querySelector('.plnerr'), b = f.querySelector('[data-plnprev]');
  const nerr = PLNEW.name ? plNewNameErr(PLNEW.name) : '';
  if(m) m.textContent = nerr;
  if(b) b.disabled = PLNEW.busy || !PLNEW.name || !!nerr;
  if(PLNEW.diff){ PLNEW.diff = ''; plPaint(); }
});
document.addEventListener('change', e => {
  const el = e.target;
  if(!PLNEW || !el || !el.dataset || !['tpl', 'fproj', 'fname'].includes(el.dataset.plnf)) return;
  PLNEW[el.dataset.plnf] = el.value; PLNEW.diff = ''; PLNEW.replaced = [];
  if(el.dataset.plnf === 'fproj'){ PLNEW.fname = ''; plLoad(el.value, false); }
  plPaint();
});
// «Ask AI for a draft»: a DM asking a live session of this
// project to write the file itself. ⚠Sidereus writes nothing on this path; preview + «Confirm» only (AGENTS.md rule 7).
let PLDRAFT = null;          // open form {desc, name, sid, busy, err}
// `wf` = «Port an existing workflow»: a .claude/workflows/*.js file name, or 'doc:<rule file>' = «Port from a rule document»
// ⚠Sidereus lists names only; the session reads the file. The head line is mailbox wire text (AI-read, English), not UI.
// `proj` = project repo path; the head line names it so the receiver knows which project the file is for.
// `ctx` = {tasks: GET default_tasks (runner DEFAULT_TASKS), skills: names}; tasks give one line per title, skills are capped.
function plDraftText(name, desc, agents, titles, wf, proj, ctx){
  const c = ctx || {}, tk = c.tasks || {}, sk = c.skills || [], cut = (s, n) => s.length > n ? s.slice(0, n - 1) + '…' : s;
  const one = t => { const v = String(tk[t] || '').split('\n')[0], i = v.indexOf('. '); return cut(i > 0 ? v.slice(0, i + 1) : v, 120); };
  const tl = titles.filter(t => tk[t]).map(t => '  ' + t + ' — ' + one(t) + '\n').join('');
  const doc = /^doc:/.test(wf || '') ? wf.slice(4) : '';
  const pp = String(proj || '').replace(/[\\/]+$/, ''), pn = pp.split(/[\\/]/).pop();
  return (pp ? 'Project: ' + (pn || pp) + ' (' + pp + ')\n' : '') + (doc ? 'Pipeline draft request — port from ' + doc + '\n'
      + 'Read ' + doc + ' in this repo, find the work/delegation flow it describes (which agents do what, in what order, retry and loop-back rules)'
      + ' and write .claude/pipelines/' + name + '.json for it with this project\'s agents (recommended titles where they fit, custom stages otherwise).'
      + ' Do not run it and do not commit.\n'
    : wf ? 'Pipeline draft request — port .claude/workflows/' + wf + '\n'
      + 'Read .claude/workflows/' + wf + ' and write .claude/pipelines/' + name + '.json in this project that runs the same steps'
      + ' (recommended titles where a step matches, custom stages otherwise). Do not run either and do not commit.\n'
    : 'Pipeline draft request — \'' + desc + '\'\n'
      + 'Write .claude/pipelines/' + name + '.json in this project for that purpose. Do not run it and do not commit.\n')
    + 'Schema v1: {"v":1,"name":"' + name + '","title":"<one line>","rules"?:"<lines>","defaults":{"model":"inherit|opus|sonnet|haiku","retry":0-3},'
    + '"stages":[{"title","agent","task"?,"model"?,"retry"?,"gate"?:"<one-line command the stage runs>","parallel"?:1-16,"produces"?:"slices","fanout"?:"slices",'
    + '"onFail"?:{"goto":"<earlier title>","max":1-5,"then"?:"<later title>"},"onError"?:"stop|continue","onlyOnJump"?:true}]}\n'
    + 'Recommended stage titles (each at most once, array order = run order): ' + titles.join(' · ') + '\n' + tl
    + 'Each has a built-in default instruction; "task" is only appended as extra instructions. Any other one-line title (<= 40 chars, at most 12) is a custom stage and needs a "task".\n'
    + 'Agents here: ' + (agents.length ? agents.join(', ') : '(none)') + ' — otherwise use general-purpose.\n'
    + 'Skills here (optional "skill" per stage): ' + (sk.length ? sk.slice(0, 40).join(', ') + (sk.length > 40 ? ' (+' + (sk.length - 40) + ' more)' : '') : '(none)') + '\n'
    + 'Rules: docs/EXTENDING.md › Pipeline, if present in this repo.\n'
    + 'Keep it valid: if scripts/pipeline_check.mjs exists run `node scripts/pipeline_check.mjs`, else check the schema above by hand. It shows up in Sidereus on the next refresh.';
}
// Same project-scoped list as the stage agent picker (48b plPickAgents), so the draft only names agents the project can use.
function plDraftAgents(d, proj){ return plPickAgents((d || {}).agents, null, proj).map(a => a.name); }
// Skills scoped like the stage skill picker (48d); stage one-liners come from the runner's DEFAULT_TASKS via GET default_tasks.
function plDraftCtx(d, proj){
  const projs = ((PLS.projs && PLS.projs.projects) || []).map(x => x.path).concat(Object.keys(PLS.data || {}));
  return { tasks: (d || {}).default_tasks || {}, skills: plPickSkills((d || {}).skills, null, proj, projs).map(k => k.name) };
}
// Session option: project · mailbox id · running task · sid8 · model (metadata only, rule 1).
function plDraftOpt(x){
  const t = String(x.doing || ''), doing = t.length > 48 ? t.slice(0, 47) + '…' : t;
  return [x.project, x.id, doing, sid8(x.sid), x.model].filter(Boolean).join(' · ') + (x.login ? '' : ' · ' + T('not logged in to the mailbox'));
}
function plDraftForm(){
  if(!PLDRAFT) return '';
  const ss = plSessions(PLS.proj), d = PLS.data[PLS.proj] || {};
  if(!ss.some(x => x.sid === PLDRAFT.sid)) PLDRAFT.sid = (ss.find(x => x.login) || ss[0] || {}).sid || '';
  const cur = ss.find(x => x.sid === PLDRAFT.sid), nerr = PLDRAFT.name ? plNewNameErr(PLDRAFT.name) : '';
  const wfs = d.workflows || [], docs = (d.rule_files || []).map(f => 'doc:' + f);
  if(PLDRAFT.wf && !wfs.includes(PLDRAFT.wf) && !docs.includes(PLDRAFT.wf)) PLDRAFT.wf = '';
  const ok = plDraftOk(cur, nerr);
  const text = plDraftText(PLDRAFT.name || '…', PLDRAFT.desc.trim() || '…', plDraftAgents(d, PLS.proj), PLG_TITLES, PLDRAFT.wf, PLS.proj, plDraftCtx(d, PLS.proj));
  return '<div class=plnew data-pldraft><div class=brh2><b>' + esc(T('Ask AI for a draft')) + '</b> <i>' + esc(T('The session writes the file — Sidereus writes nothing')) + '</i></div>'
    + (wfs.length || docs.length ? '<label class=plfr><span>' + esc(T('Source', 'origin')) + '</span><select data-pldf=wf><option value="">' + esc(T('Write new from a purpose')) + '</option>'
      + docs.map(w => '<option value="' + esc(w) + '"' + (w === PLDRAFT.wf ? ' selected' : '') + '>' + esc(T('Port from a rule document') + ' · ' + w.slice(4)) + '</option>').join('')
      + wfs.map(w => '<option value="' + esc(w) + '"' + (w === PLDRAFT.wf ? ' selected' : '') + '>' + esc(T('Port an existing workflow') + ' · ' + w) + '</option>').join('') + '</select></label>' : '')
    + '<label class=plfr><span>' + esc(T('Purpose')) + '</span><input data-pldf=desc maxlength=300 value="' + esc(PLDRAFT.desc) + '" placeholder="' + esc(T('One-line purpose')) + '"></label>'
    + '<label class=plfr><span>' + esc(T('Name')) + '</span><input data-pldf=name maxlength=40 value="' + esc(PLDRAFT.name) + '" placeholder="bugfix"></label>'
    + '<div class="plfd plnerr">' + esc(nerr) + '</div>'
    + (ss.length ? '<label class=plfr><span>' + esc(T('Sessions')) + '</span><select data-pldf=sid>' + ss.map(x => '<option value="' + esc(x.sid) + '"'
      + (x.sid === PLDRAFT.sid ? ' selected' : '') + (x.login ? '' : ' disabled') + '>' + esc(plDraftOpt(x)) + '</option>').join('') + '</select></label>'
      : '<div class=hidnote>' + esc(T('No live session in this project')) + '</div>')
    + '<div class=brh2><b>' + esc(T('Message to send')) + '</b>' + (cur && cur.id ? ' <i>→ ' + esc(cur.id) + '</i>' : '') + '</div><pre class=plprev>' + esc(text) + '</pre>'
    + (PLDRAFT.err ? '<div class="plfd plnerr">' + esc(PLDRAFT.err) + '</div>' : '')
    + '<div class=plbar><button class="wkrgb" data-pldgo' + (ok ? '' : ' disabled') + '>' + esc(T('Confirm — send')) + '</button>'
    + plBackBtn('data-pldx') + '</div></div>';
}
function plDraftOk(cur, nerr){ return !!(cur && cur.login && (PLDRAFT.wf || PLDRAFT.desc.trim()) && PLDRAFT.name && !nerr && !PLDRAFT.busy); }
async function plDraftSend(){
  const a = PLDRAFT, cur = a && plSessions(PLS.proj).find(x => x.sid === a.sid), d = PLS.data[PLS.proj] || {};
  if(!a || a.busy || !cur || !cur.login || !(a.wf || a.desc.trim()) || plNewNameErr(a.name)) return;
  a.busy = true; a.err = ''; plPaint();
  try{
    const j = await postJSON('/api/dm', { to: cur.id, relay: true, sid: cur.sid, thread: 'pipeline-draft',
      body: plDraftText(a.name, a.desc.trim(), plDraftAgents(d, PLS.proj), PLG_TITLES, a.wf, PLS.proj, plDraftCtx(d, PLS.proj)) });
    if(!j || !j.ok) throw new Error((j && (j.error || j.err)) || '?');
    const row = (SESS || []).find(x => x && x.sid === cur.sid) || {};
    PLDRAFT = null; PLS.msg = '';
    plDraftSet({ id: j.id || '', to: j.to || cur.id, proj: PLS.proj, cwd: row.cwd || PLS.proj, name: a.name, at: Date.now(), ok: true });
  }catch(e){ a.busy = false; a.err = T('Could not send') + ': ' + T((e && e.message) || e); }
  plPaint();
}
// Draft progress strip: sent → session ack → <name>.json listed → open. Each step lights on its own evidence.
// ⚠Step 2 reads ack `who` only — `note` is message content (rule 1); `hooked`/`delivered` prove nothing was read.
const PL_DRAFT_TTL = 600000;
function plDraftSteps(dr, ack, data){
  const a = (dr && ack && ack[dr.id]) || {};
  const at = [dr.proj, dr.cwd].find(p => p && data && data[p] && (data[p].pipelines || []).some(x => x && x.name === dr.name)) || '';
  return { sent: !!dr.ok || (a.delivered || []).includes(dr.to), got: (a.ack || []).some(x => x && x.who === dr.to), file: !!at, at };
}
function plDraftStrip(dr, ack, data, proj){
  const s = plDraftSteps(dr, ack, data), on = [s.sent, s.got, s.file];
  const lab = [T('Delivered'), T('Session received'), dr.name + '.json ' + T('created')];
  const chip = dr.cwd && dr.cwd !== proj ? ' <button class="strp" data-pldrp="' + esc(dr.cwd) + '" title="' + esc(T('Session folder') + ' · ' + dr.cwd) + '">' + esc(strShort(dr.cwd)) + '</button>' : '';
  return '<div class="hidnote pldrs">' + esc(T('Ask AI for a draft') + ' → ' + dr.to + ' · ') + lab.map((l, i) => '<span' + (on[i] ? ' class=on' : '') + '>'
    + esc((on[i] ? '● ' : '○ ') + l) + '</span>').join(' → ') + ' → '
    + (s.file ? '<button class="wkrgb plsv" data-pldro="' + esc(s.at) + '">' + esc(T('Open')) + '</button>' : '<span>' + esc('○ ' + T('Open')) + '</span>') + chip + '</div>';
}
// Persisted metadata only (no body); restored within the 10 min re-list window.
function plDraftRestore(raw, now){
  let d = null;
  try{ d = JSON.parse(raw || 'null'); }catch(e){ return null; }
  if(!d || typeof d !== 'object' || !d.id || !d.to || !d.name || !(now - (+d.at || 0) < PL_DRAFT_TTL)) return null;
  return { id: String(d.id), to: String(d.to), proj: String(d.proj || ''), cwd: String(d.cwd || ''), name: String(d.name), at: +d.at, ok: true };
}
function plDraftSet(dr){
  PLS.draft = dr;
  if(dr) lsSet('sidereus.pldraft', JSON.stringify({ id: dr.id, to: dr.to, proj: dr.proj, cwd: dr.cwd, name: dr.name, at: dr.at }));
  else lsDel('sidereus.pldraft');
}
PLS.draft = plDraftRestore(lsGet('sidereus.pldraft', ''), Date.now());
document.addEventListener('click', e => {
  if(!e.target.closest || !e.target.closest('.plw') || !PLS.draft) return;
  const o = e.target.closest('[data-pldro]'), c = e.target.closest('[data-pldrp]'), nm = PLS.draft.name;
  if(o){ plDraftSet(null); plOvPick(o.dataset.pldro, nm); }   // ⚠no scroll or centre (plOvPick)
  else if(c) plOvPick(c.dataset.pldrp, nm);
});
document.addEventListener('click', e => {
  if(!e.target.closest || !e.target.closest('.plw')) return;
  if(e.target.closest('[data-pldnew]')){ PLDRAFT = { desc: '', name: '', sid: '', wf: '', busy: false, err: '' }; PLNEW = null; plPaint(); return; }
  if(e.target.closest('[data-pldx]')){ PLDRAFT = null; plPaint(); return; }
  if(e.target.closest('[data-pldgo]')) plDraftSend();
});
document.addEventListener('input', e => {
  const el = e.target;
  if(!PLDRAFT || !el || !el.dataset || el.dataset.pldf == null || el.tagName !== 'INPUT') return;
  PLDRAFT[el.dataset.pldf] = el.value;
  const f = el.closest('[data-pldraft]'), d = PLS.data[PLS.proj] || {};
  const pre = f && f.querySelector('.plprev'), m = f && f.querySelector('.plnerr'), go = f && f.querySelector('[data-pldgo]');
  const nerr = PLDRAFT.name ? plNewNameErr(PLDRAFT.name) : '', cur = plSessions(PLS.proj).find(x => x.sid === PLDRAFT.sid);
  if(pre) pre.textContent = plDraftText(PLDRAFT.name || '…', PLDRAFT.desc.trim() || '…', plDraftAgents(d, PLS.proj), PLG_TITLES, PLDRAFT.wf, PLS.proj, plDraftCtx(d, PLS.proj));
  if(m) m.textContent = nerr;
  if(go) go.disabled = !plDraftOk(cur, nerr);
});
document.addEventListener('change', e => {
  const el = e.target;
  if(!PLDRAFT || !el || !el.dataset || !['sid', 'wf'].includes(el.dataset.pldf)) return;
  PLDRAFT[el.dataset.pldf] = el.value; plPaint();
});
