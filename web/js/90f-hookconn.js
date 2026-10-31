// «Connect» notice for CLIs installed without Sidereus hooks (GET/POST /api/hooks/connect, sidereus/hook_connect.py).
// One renderer for two places: 'pl' = bottom of the expanded «Working now» list (48j), 'dx' = Settings «Diagnostics» (90e).
// ⚠Rule 7: «Connect» only previews (dry); nothing is written before «Apply», which posts the preview's base sha (409 = file changed).
// ⚠Metadata only on the list (names · states · paths); the diff is shown only after a click, like the other config-write previews.
let HC = null, HC_LD = false, HC_AT = 0, HC_AGAIN = false;   // last GET reply · in flight · fetch time (ms) · forced while in flight
const HCS = {};                             // per plat: {st: 'prev'|'busy'|'done'|'err', diff, base, msg}
const HC_TTL = 300000;                      // refetch at most every 5 min from repaints; «Refresh» and «Apply» force it
const HC_LOGO = { cursor: 'cu', codex: 'cx', gemini: 'gm', copilot: 'cp' };
const hcOn = () => !(typeof FEATS === 'object' && FEATS && FEATS.diag === false);   // ⚠the route 404s with the feature off
const hcLater = p => lsGet('sidereus.hclater.' + p, '') === '1';
async function hcLoad(force){
  if(HC_LD && force) HC_AGAIN = true;   // ⚠a forced reload during a poll fetch must not be dropped: that fetch predates the write
  if(!hcOn() || HC_LD || (HC && !force && Date.now() - HC_AT < HC_TTL)) return;
  HC_LD = true;
  let r = null;
  try{ r = await getJSON('/api/hooks/connect'); }catch(e){ r = { err: String((e && e.message) || e) }; }
  HC = r && r.ok ? r : { err: String((r && (r.err || r.error)) || '?') }; HC_AT = Date.now(); HC_LD = false;
  hcPaint();
  if(HC_AGAIN){ HC_AGAIN = false; hcLoad(true); }
}
const hcPlats = () => (HC && Array.isArray(HC.plats) ? HC.plats : []).filter(x => x && typeof x === 'object' && x.plat && (x.state !== 'connected' || hcPin(String(x.plat))));
// A Codex «/hooks» hint stays until «Close»: ⚠not counted in reloads, which a racing poll reply would consume. The server sends it back as connected, can:false.
const hcPin = p => !!(HCS[p] && HCS[p].pin);
// Header to-do chip (25 buildTodo): connectable CLIs still missing hooks, minus «Later»; [{plat, name}] in server order.
function hcTodo(){
  if(!hcOn() || !HC || !Array.isArray(HC.plats)) return [];
  return HC.plats.filter(x => x && typeof x === 'object' && x.plat && x.can && x.state !== 'connected' && !hcLater(String(x.plat)))
    .map(x => ({ plat: String(x.plat), name: String(x.name || x.plat) }));
}
// Pure: inner HTML of one place. 'pl' shows connectable, not-«Later» rows only; 'dx' also shows `can:false` rows as a muted hint.
function hcInner(where){
  if(!hcOn()) return '';
  const dx = where === 'dx', L = hcPlats().filter(x => hcPin(String(x.plat)) || (dx ? (x.can || x.why) : x.can && !hcLater(String(x.plat))));
  const rows = L.map(x => {
    const p = String(x.plat), s = HCS[p] || {}, busy = s.st === 'busy', nm = String(x.name || p);
    const lab = x.state === 'connected' ? '' : T(x.state === 'partial' ? 'Partly connected' : 'Sidereus hooks not connected');
    let h = '<div class="hcr' + (x.can ? '' : ' off') + '" data-hcp="' + esc(p) + '" aria-label="' + esc(nm + ' · ' + lab) + '">'
      + '<div class=hch>' + aiLogo(HC_LOGO[p] || p) + '<span class=hcl>' + esc(lab) + '</span>';
    // ⚠'pl' never previews in place: the diff was unreadable in the short «Working now» list, so «Connect» opens «Diagnostics».
    if(x.can && (dx ? s.st !== 'prev' : true) && s.st !== 'done') h += '<button type=button class=strp data-hca=' + (dx ? 'go' : 'open') + ' data-hcv="' + esc(p) + '"' + (busy ? ' disabled' : '') + '>' + esc(T('Connect')) + '</button>'
      + (dx ? '' : '<button type=button class=strp data-hca=later data-hcv="' + esc(p) + '">' + esc(T('Later')) + '</button>');
    if(s.st === 'done') h += '<button type=button class=strp data-hca=cancel data-hcv="' + esc(p) + '">' + esc(T('Close')) + '</button>';   // dismiss the result (and a pinned hint)
    h += '</div><small class=hcf title="' + esc(x.file || '') + '">' + esc(x.file || '') + '</small>';
    if(!x.can && x.why) h += '<small class=hcw0>' + esc(x.why) + '</small>';   // server reason is data: esc, never T()
    if(dx && s.st === 'prev') h += '<div class=hcd><small>' + esc(T('Nothing is written until Apply.')) + '</small><pre>' + diffHtml(s.diff || '', agLang('x.json')) + '</pre>'
      + '<div class=hcb><button type=button class="strp on" data-hca=apply data-hcv="' + esc(p) + '">' + esc(T('Apply')) + '</button>'
      + '<button type=button class=strp data-hca=cancel data-hcv="' + esc(p) + '">' + esc(T('Cancel')) + '</button></div></div>';
    if(s.msg) h += '<small class="hcm' + (s.st === 'err' ? ' err' : '') + '" role=status>' + esc(s.msg) + '</small>';
    return h + '</div>';
  }).join('');
  const err = dx && HC && HC.err ? '<div class="cfgpd err">' + esc(T('Could not load')) + ': ' + esc(HC.err) + '</div>' : '';
  if(!rows && !err) return '';
  return (dx ? '<div class=cfgs>' + esc(T('CLI hooks')) + '</div>' : '') + err + rows;
}
// Wrapper is always emitted (empty = hidden by CSS) so a late GET fills it in place without repainting the page around it.
function hcRow(where){
  if(!hcOn()) return '';
  hcLoad(false);
  return '<div class=hcwr data-hcw="' + esc(where) + '">' + hcInner(where) + '</div>';
}
function hcPaint(){
  document.querySelectorAll('[data-hcw]').forEach(el => {
    const f = document.activeElement, inside = !!(f && el.contains && el.contains(f)), key = inside && f.dataset && f.dataset.hca ? f.dataset.hca + '\n' + f.dataset.hcv : '';
    setHtml(el, hcInner(el.dataset.hcw));
    if(key && !el.contains(f)){   // keep focus on the same control, else its row's first button
      const kp = key.split('\n'), b = el.querySelector('[data-hca="' + kp[0] + '"][data-hcv="' + kp[1] + '"]') || el.querySelector('[data-hcp="' + kp[1] + '"] button');
      if(b) b.focus();
    }
  });
  if(typeof buildTodo === 'function') buildTodo();   // header chip follows every reload, «Later» and «Apply» without a page reload
}
const hcErr = e => e && e.status === 409 ? T('The file changed since the preview. Preview again.')
  : T('Could not connect') + ': ' + String((e && e.body && (e.body.err || e.body.error)) || (e && e.message) || e);
async function hcAct(a, p){
  if(a === 'later'){ lsSet('sidereus.hclater.' + p, '1'); hcPaint(); return; }
  if(a === 'cancel'){ delete HCS[p]; hcPaint(); return; }
  if(a === 'open'){   // Settings › «Diagnostics» (CFGCAT · cfgOpen, 90-settings.js), then the same dry preview there
    if(typeof cfgOpen !== 'function') return;
    CFGCAT = 'dx'; if(typeof tabSet === 'function') tabSet('sidereus.cfgcat', 'dx');
    cfgOpen();
    if(!(HCS[p] && HCS[p].st === 'prev')) return hcAct('go', p);
    return;
  }
  const s = HCS[p] || {};
  if(a === 'go'){
    HCS[p] = { st: 'busy' }; hcPaint();
    try{
      const r = await postJSON('/api/hooks/connect', { plat: p, dry: true });
      HCS[p] = r && r.changed === false || !(r && r.diff) ? { st: 'done', msg: T('Already connected') } : { st: 'prev', diff: String(r.diff), base: String(r.base || '') };
    }catch(e){ HCS[p] = { st: 'err', msg: hcErr(e) }; }
    hcPaint(); return;
  }
  if(a === 'apply' && s.st === 'prev'){
    HCS[p] = { st: 'busy' }; hcPaint();
    try{
      const r = await postJSON('/api/hooks/connect', { plat: p, dry: false, base: s.base });
      HCS[p] = { st: 'done', pin: !!(r && r.approve), msg: r && r.approve ? T('Connected. Restart Codex, then run /hooks in it to approve the new hooks.') : T(r && r.changed === false ? 'Already connected' : 'Connected. Restart sessions that are already open: only newly started ones load the hooks.') };
      hcPaint(); hcLoad(true);   // message shows in place first; the reload then drops the connected row
      return;
    }catch(e){ HCS[p] = { st: 'err', msg: hcErr(e) }; }
    hcPaint(); return;
  }
}
document.addEventListener('click', e => {
  const b = e.target.closest && e.target.closest('[data-hcw] button[data-hca]');
  if(b && !b.disabled) hcAct(b.dataset.hca, b.dataset.hcv);
});
