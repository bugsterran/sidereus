// ★Needs-me pills in the rail «Attention» list (#rattnl); the header no longer has an activity strip.
//   ⛔Metadata only — project · state · tool NAME · elapsed. Never the tool target/arguments (x.targ), prompts or replies.
//   Source is SESS/ATTN from the existing poll (no new server call); a 1s tick only rewrites elapsed text (DOM stays keyed).
let actSess = null, actAttn = null, actLang = '', actAt = 0, actData = null, actHovK = '';
const actMap = new Map();                             // pill key -> session object of the last paint
function actKey(x){ return x.sid || x.cwd || x.id || ''; }
function actPill(k){ return (actData && actData.pills || []).find(q => actKey(q.x) === k) || null; }
function actProj(x){ return x.project || String(x.cwd || '').split('/').pop() || '?'; }
function actDur(s){ s = Math.max(0, Math.floor(s)); return s < 60 ? U(s, 's') : HM(Math.floor(s / 60)); }
function actAge(x){ return (x.ageSec || 0) + (Date.now() - actAt) / 1000; }
// ⚠State start = server clock − ageSec, never Date.now() − age: a skewed/frozen client clock (09-24 audit tab had a fake
//   clock at 08:07) printed «8:06 AM · 32s» at 09:58. ageSec is server-relative, so the start must be too.
let actSrv = 0;
function actStart(x){ return new Date((actSrv || actAt) - (x.ageSec || 0) * 1000); }
// ⚠Needs-me = every badge row of attnRows (the same rows as the header «Need you N» chip), plus blocked/ask session flags.
function actNeedOf(x, am){
  const a = am.get(x.sid) || am.get('c:' + x.cwd);
  if(x.blocked) return { k: 'blocked', i: -2 };
  if(x.state === 'ask') return { k: 'ask', i: -1 };
  return a || null;
}
function actWhat(x, need, why){
  if(need === 'blocked') return T('Blocked') + (x.tool ? ' · ' + x.tool : '');
  const pc = (need === 'ctx85' || need === 'ctx95') && ((why || '').match(/(\d+)%/) || [])[1];   // real % (as the ctx chip), not the 85/95 threshold
  if(pc) return T('Context') + ' ' + pc + '%';
  return attnLbl(need);                                // every rail pill carries a needs-me kind
}
function actRows(){
  const am = new Map();
  try{ attnRows().shown.forEach((r, i) => { if(!r.badge) return; const v = { k: r.top.k, i, tone: attnTone(r.score), since: r.since, why: r.top.why };   // attnSess matching: sid, else cwd
    if(r.r.sid) am.set(r.r.sid, v); else if(r.r.cwd) am.set('c:' + r.r.cwd, v); }); }catch(e){ softErr('actRows', e); }
  const nd = [];
  for(const x of SESS || []){
    const n = actNeedOf(x, am);
    if(n){ const a = n.tone ? n : am.get(x.sid) || am.get('c:' + x.cwd) || {};   // blocked/ask still take the drawer row's tier + age
      nd.push({ x, need: n.k, rank: n.i, tone: a.tone || (n.k === 'blocked' ? 'err' : 'warn'), since: a.since || 0, why: a.why }); continue; }      // even a done session, so the count matches the header chip
    if(x.state === 'done' || x.state === 'gone') continue;
    // ⚠Same split as sesCount() (41-sesdrawer): ask/abort need the user.
    if(x.state === 'ask' || x.state === 'abort') nd.push({ x, need: x.state, rank: 1e6, tone: 'warn' });
  }
  nd.sort((a, b) => a.rank - b.rank);                               // blocked · ask first, then attention score order
  return { pills: nd };
}
function actSet(e, v){ if(e.textContent !== v) e.textContent = v; }
// Same-value attribute writes still queue a mutation record every poll (measured 2026-09-26) — write only on change.
function actAttr(e, n, v){ if(e.getAttribute(n) !== v) e.setAttribute(n, v); }
function actPillEl(k){
  const e = document.createElement('button');
  e.type = 'button'; e.className = 'acp'; e.dataset.k = k;
  e.innerHTML = '<i class=acd></i><b class=acn></b><span class=act></span><span class=ace></span>';
  return e;
}
// ⚠Needs-me pills show the attention signal's age (agoAt(since), same text as the drawer row), not the state age.
function actAgeTxt(x, since){ return since ? agoAt(since) : actDur(actAge(x)); }
function actFill(e, p){
  e.classList.toggle('need', !!p.need); actAttr(e, 'data-st', p.need || p.x.state || 'unknown'); actAttr(e, 'data-tone', p.need ? p.tone || 'warn' : '');
  actSet(e.children[1], actProj(p.x)); actSet(e.children[2], actWhat(p.x, p.need, p.why)); actSet(e.children[3], actAgeTxt(p.x, p.need && p.since));
}
function actPaint(){
  const d = actData = actRows(), rl = document.getElementById('rattnl');
  if(!rl) return actRailN(d.pills.length);
  const old = new Map([...rl.querySelectorAll(':scope > .acp')].map(e => [e.dataset.k, e]));
  const want = [];
  actMap.clear();
  for(const p of d.pills){
    const k = actKey(p.x); if(!k || actMap.has(k)) continue;
    actMap.set(k, p.x);
    let e = old.get(k); if(e) old.delete(k); else e = actPillEl(k);
    actFill(e, p); want.push(e);
  }
  old.forEach(e => e.remove());
  actRailN(want.length);
  actPlace(rl, want);
  if(actHovK) actHovShow(actHovK);
}
// ⚠Moving a focused node blurs it — defer a reorder while focus is inside the list, and never move the focused pill
//   out of the list; the next poll retries.
function actPlace(box, want){
  if(!want.some((e, i) => box.children[i] !== e)) return;
  const f = document.activeElement;
  if(!box.contains(f)) want.forEach((e, i) => { if(box.children[i] !== e && !e.contains(f)) box.insertBefore(e, box.children[i] || null); });
  else want.forEach(e => { if(e.parentNode !== box && !e.contains(f)) box.appendChild(e); });
}
// Rail «Attention» count (#rattnn) and the collapsed rail's badge button (#rattnb); n omitted = keep the last count.
let actRailNv = 0;
function actRailN(n){
  if(n !== undefined) actRailNv = n;
  const v = actRailNv ? String(actRailNv) : '', h = document.getElementById('rattnn'), b = document.getElementById('rattnb');
  if(h) actSet(h, v);
  if(b){ const bd = b.querySelector('b'); if(bd) actSet(bd, v); const l = T('Attention') + (v ? ' ' + v : '');
    actAttr(b, 'title', l); actAttr(b, 'aria-label', l); b.classList.toggle('on', !!actRailNv); }
  const r = document.getElementById('rattn'); if(r) r.classList.toggle('on', !!actRailNv);
}
function actTick(){
  if(SESS !== actSess || ATTN !== actAttn || LANG !== actLang){
    actSess = SESS; actAttn = ATTN; actLang = LANG; actAt = Date.now();
    actSrv = (ATTN && ATTN.at) ? ATTN.at * 1000 : 0;       // attention.at = server time.time() of the same state() poll
    return actPaint();
  }
  document.querySelectorAll('#rattnl > .acp').forEach(e => {
    const x = actMap.get(e.dataset.k); if(!x) return;
    const p = actPill(e.dataset.k);
    actSet(e.children[3], actAgeTxt(x, p && p.need && p.since));
  });
  if(actHovK) actHovShow(actHovK);
}
// A «Blocked»/«Awaiting answer» pill whose tab can be raised -> its sid, else ''.
function actTermSid(k){ const p = actPill(k); return p && ALARM_TERM_KINDS.has(p.need) ? termJumpSid(p.x.sid) : ''; }
function actGo(k){
  const x = (SESS || []).find(s => actKey(s) === k);
  actHovHide();
  if(typeof railPeekEnd === 'function') railPeekEnd();   // a badge-opened rail closes after the jump (92d)
  const js = actTermSid(k);
  if(js) return termGo(js);
  if(x) try{ cpGo(x); }catch(e){ softErr('cpGo', e); }           // cpGo = the Cmd+K jump: sesdrReveal() + scroll + highlight the row
}
// Hover card — same look as the timeline card (.tlhc); metadata rows only.
function actHovHtml(k){
  const x = actMap.get(k); if(!x) return '';
  const p = (actData && actData.pills || []).find(q => actKey(q.x) === k), need = p ? p.need : '', why = p ? p.why : '';
  const rows = [], add = (a, v) => { if(v) rows.push('<dt>' + esc(T(a)) + '</dt><dd>' + v + '</dd>'); };
  add('Status', esc(actWhat(x, need, why)));
  add('State since', esc(CLK(actStart(x))) + ' <s>· ' + esc(actDur(actAge(x))) + '</s>');
  add('Session', esc(sid8(x.sid || x.id || '')));
  add('Model', esc(x.model || ''));
  if((x.sub || []).length) add('Subagents', esc(String(x.sub.length)));
  if(x.win && x.ctx) add('Context', esc(Math.round(x.ctx / x.win * 100) + '%'));
  add('Path', esc(x.cwd || ''));
  return '<div class=tlhch>' + esc(actProj(x)) + '</div><dl>' + rows.join('') + '</dl>'
    + '<div class=tlhcf>' + esc(T(actTermSid(k) ? 'Click to open its terminal' : 'Click to show it in the session list')) + '</div>';
}
function actHovShow(k){
  const el = document.querySelector('#rattnl > .acp[data-k="' + CSS.escape(k) + '"]');
  const html = el ? actHovHtml(k) : '';
  if(!html) return actHovHide();
  const c0 = document.getElementById('acthc'), fresh = !c0 || c0.hidden || actHovK !== k;
  const c = hcShow('acthc', html, 'tlhc acthc');
  actHovK = k;
  if(!fresh) return;
  popAnchor(c, null, {at: el.getBoundingClientRect(), gap: 6, flipY: true, side: 'right'});
}
function actHovHide(){ actHovK = ''; hcHide('acthc'); }
(function(){
  if(!document.getElementById('rattnl')) return;
  document.addEventListener('click', e => { const t = e.target.closest && e.target.closest('#rattnl > .acp'); if(t && t.dataset.k) actGo(t.dataset.k); });
  const hov = e => { const t = e.target.closest && e.target.closest('#rattnl > .acp'); if(t) actHovShow(t.dataset.k); else if(actHovK) actHovHide(); };
  document.addEventListener('mouseover', hov, {passive: true});
  document.addEventListener('focusin', hov);
  document.addEventListener('scroll', () => { if(actHovK) actHovHide(); }, true);
  document.addEventListener('keydown', e => { if(e.key === 'Escape' && actHovK) actHovHide(); }, true);
  addEventListener('resize', actHovHide);
  setInterval(() => { if(!document.hidden) actTick(); }, 1000);   // nothing to repaint in a hidden tab
})();
