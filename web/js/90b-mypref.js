// «Preferences» settings category (90-settings.js cfgPaneMe): screen prefs in UIS, server prefs via /api/prefs.
// ⚠Empty storage must reproduce the stock screen byte for byte: every normaliser returns the built-in default for missing/bad input.
const MP_TABS = ['pipe', 'time', 'struct', 'br', 'token', 'hist', 'retro', 'chat'];   // stock tab order (92-mainview-tabs.js buildMv); a saved mbTabs order still wins
function mpJson(k){ try{ return JSON.parse(UIS.getItem(k) || 'null'); }catch(e){ return null; } }
function mpPut(k, v){ try{ if(v == null) UIS.removeItem(k); else UIS.setItem(k, typeof v === 'string' ? v : JSON.stringify(v)); return true; }catch(e){ return false; } }
// mbStartView: 'last' (default = reopen the last tab) or one tab key.
function mpStart(raw){ return MP_TABS.includes(raw) ? raw : 'last'; }
// {order, hide} for a fixed key set: unknown/duplicate keys dropped, missing ones appended in stock order; lock can never hide.  // gitleaks:allow
function mpOrder(raw, all, lock){
  const o = raw && typeof raw === 'object' ? raw : {};
  const order = (Array.isArray(o.order) ? o.order : []).filter((k, i, a) => all.includes(k) && a.indexOf(k) === i);
  all.forEach(k => { if(!order.includes(k)) order.push(k); });
  let hide = (Array.isArray(o.hide) ? o.hide : []).filter((k, i, a) => all.includes(k) && k !== lock && a.indexOf(k) === i);
  if(hide.length >= all.length) hide = [];   // never an empty strip
  return {order: order, hide: hide};
}
function mpTabs(){ return mpOrder(mpJson('mbTabs'), MP_TABS, 'time'); }   // ⚠'time' is the fallback view (pipe can be feature-off), so it cannot hide
// Move / hide one key; a result equal to the stock layout clears the key so storage stays empty.
function mpOrderAct(cur, all, lock, k, op){
  const o = {order: cur.order.slice(), hide: cur.hide.slice()}, i = o.order.indexOf(k);
  if(i < 0) return cur;
  if(op === 'up' && i > 0){ o.order[i] = o.order[i-1]; o.order[i-1] = k; }
  else if(op === 'down' && i < o.order.length - 1){ o.order[i] = o.order[i+1]; o.order[i+1] = k; }
  else if(op === 'hide' && k !== lock && !o.hide.includes(k)) o.hide.push(k);
  else if(op === 'show') o.hide = o.hide.filter(x => x !== k);
  return mpOrder(o, all, lock);
}
const mpStock = (p, all) => !p.hide.length && p.order.join() === all.join();
// Server prefs (GET /api/prefs) — loaded when the pane opens, refreshed at most every 15s.
let MPSRV = null, MPSRV_AT = 0, MPSRV_LD = false, MPERR = {}, MPDONE = {};
const MP_SRV_LAB = {
  saver_hook_dir: ['Saver hook folder', 'Folder where saver.py reads its switch and goal files.'],
  compact_history: ['Auto-compact history', '[["YYYY-MM-DD", tokens or null], ...] in ascending date order. Empty = only the current compact threshold.'],
  viewer_me: ['My name', 'Sender name on posts sent from the viewer.'],
  default_room: ['Default room', 'Room picked first when posting from the viewer.'],
  port: ['Port', 'Viewer address http://127.0.0.1:<port>/ (1024-65535). Hooks and MCP read the same value. Applies after a restart — open a new tab at the new address.'],
};
const MP_ADV = ['saver_hook_dir', 'compact_history', 'port'];   // server rows inside the collapsed «Advanced» fold
// viewer_me unset or a default spelling posts as this UI language's default (sidereus/config.py viewer_me_for) — show that name.
function mpVmDefault(s){
  const it = s && s.ok && s.keys && s.keys.viewer_me, d = T('user');
  if(!it || it.src === 'env' || it.default !== '사용자') return;   // wire value from sidereus/config.py VIEWER_ME, not UI
  it.default = d;
  if(it.value === '사용자' || it.value === 'user') it.value = d;
}
async function mpSrvLoad(force){
  if(MPSRV_LD || (!force && MPSRV && Date.now() - MPSRV_AT < 15000)) return;
  MPSRV_LD = true;
  try{ const r = await getJSON('/api/prefs'); MPSRV = (r && r.ok && r.keys) ? r : {ok: false, err: (r && r.err) || T('unexpected response shape')}; }
  catch(e){ MPSRV = {ok: false, err: String((e && e.message) || e)}; }
  mpVmDefault(MPSRV);
  MPSRV_LD = false; MPSRV_AT = Date.now();
  const m = document.getElementById('cfgm'), ae = document.activeElement;
  if((CFGCAT !== 'me' && CFGCAT !== 'sv') || !m || m.hidden || (ae && (ae.tagName === 'INPUT' || ae.tagName === 'SELECT') && m.contains(ae))) return;   // ⚠a repaint would drop typed text; 'sv' shows the compact hint
  paintCfg();
}
const mpShow = v => v == null ? '' : typeof v === 'string' ? v : JSON.stringify(v);
// Parse the typed text by the default's type: number / JSON (lists) / string. Returns [ok, value].
function mpParse(txt, dflt){
  const t = String(txt == null ? '' : txt).trim();
  if(typeof dflt === 'number'){ const n = Number(t); return t !== '' && isFinite(n) ? [true, n] : [false, T('Enter a number')]; }
  if(dflt !== null && typeof dflt === 'object'){ try{ return [true, JSON.parse(t)]; }catch(e){ return [false, T('Not valid JSON')]; } }
  return [true, t];
}
// Client copy of the server validators (sidereus/prefs.py, sidereus/cc_settings.py), checked before the confirm.
//   ⚠Keep in step with PORT_MIN/MAX, WIN_MIN/MAX, _v_name, _v_dir.
//   One rule for numbers: out of range is refused here, never clamped, so the preview is exactly what is typed.
//   The server still clamps autoCompactWindow, but only as a backstop for API callers.
const MP_RULE = {port: {min: 1024, max: 65535}, cc_compact_window: {min: 50000, max: 1000000},
  viewer_me: {name: 1}, default_room: {name: 1}, saver_hook_dir: {dir: 1}};
// [true, value] or [false, message]
function mpCheck(key, v){
  const r = MP_RULE[key];
  if(!r) return [true, v];
  if(r.min != null){
    if(!Number.isInteger(v)) return [false, T('Enter a whole number')];
    if(v < r.min) return [false, T('min') + ' ' + r.min];
    if(v > r.max) return [false, T('max') + ' ' + r.max];
  }
  if((r.name || r.dir) && typeof v === 'string') v = v.trim();   // the server stores the trimmed text
  if(r.name && (!v || v.length > 64 || /[\x00-\x1f\x7f/\\]/.test(v))) return [false, T('1-64 characters, no / or \\')];
  // ⚠"~" or "~/…" only: "~foo" would expand to another user's home
  if(r.dir && (!v || v.length > 512 || v.includes('\x00') || !/^(\/|~$|~\/)/.test(v) || v.replace(/\\/g, '/').split('/').includes('..'))) return [false, T('Enter a path starting with / or ~ (no ..)')];
  return [true, v];
}
// Typed text of a field whose value was refused: the repaint keeps it (with the error) instead of
//   snapping back to the stored value. Dropped on a successful save or a cancelled confirm.
const MPDRAFT = {};
// Server validator messages (English, sidereus/prefs.py) -> Korean for the inline note.
const MP_SRV_ERR = [[/^port must be/, 'whole number only', '1024~65535 '],[/must be 1\.\.64 characters/, '1-64 characters, no / or \\'],
  [/^path must/, 'Enter a path starting with / or ~ (no ..)'], [/must be an integer/, 'Enter a whole number'], [/^set by env/, 'Set by an environment variable, so it cannot be changed here.'],
  [/^write failed/, 'Could not write the file'], [/^value missing|^unknown key/, 'Bad request']];
function mpSrvErr(e){ e = String(e || '?'); const m = MP_SRV_ERR.find(x => x[0].test(e)); return T('Save failed') + ': ' + (m ? (m[2] || '') + T(m[1]) : e); }
const mpBad = msg => T('Check the value') + ': ' + msg;
// Typing in a field drops its stale error note in place (a repaint would steal focus).
if(document.addEventListener) document.addEventListener('input', e => {   // guard: node tests load this file with a bare document stub
  const el = e.target, k = el && el.dataset && (el.dataset.mpin || el.dataset.mpcin);
  if(el && (el.id === 'svgn' || el.id === 'svpt') && SVERR){   // saver pane: same rule for its summary line
    SVERR = ''; const b = document.getElementById('svnow'); if(b){ b.classList.remove('err'); b.textContent = svNowLine(); }
    return;
  }
  if(k && k in MPDRAFT) MPDRAFT[k] = el.value;   // a later repaint shows the latest text
  if(el && el.dataset && el.dataset.mpacct != null && MPSRV && MPSRV.keys){   // «Per account» window: keep the text across seg-click repaints
    const x = mpAcctRows()[+el.dataset.mpacct]; if(x) MPACD[x.path] = {auto: mpAcctD(x).auto, win: el.value};
    return;
  }
  if(!k || !MPERR[k]) return;
  delete MPERR[k];
  const n = el.closest('.cfgrc'), s = n && n.querySelector('.mpnote.err'); if(s) s.remove();
});
// ⚠One write per action: confirm and POST leave the button live, so a double-click confirmed and POSTed twice. Keyed per setting; set before any await.
const MPBUSY = {};
async function mpOnce(k, f){ if(MPBUSY[k]) return; MPBUSY[k] = 1; try{ return await f(); } finally{ delete MPBUSY[k]; } }
function mpSrvSet(key, reset){ return mpOnce(key, () => mpSrvSetRun(key, reset)); }
async function mpSrvSetRun(key, reset){
  const it = MPSRV && MPSRV.keys && MPSRV.keys[key];
  if(!it || it.src === 'env') return;
  let body = {key: key, reset: true}, after = mpShow(it.default);
  delete MPERR[key];
  if(!reset){
    const el = document.querySelector('#cfgbox [data-mpin="' + key + '"]'), raw = el ? el.value : '', p = mpParse(raw, it.default);
    const c = p[0] ? mpCheck(key, p[1]) : p;   // before the confirm: the preview must be the stored value
    if(!c[0]){ MPERR[key] = mpBad(c[1]); MPDRAFT[key] = raw; paintCfg(); return; }
    body = {key: key, value: c[1]}; after = mpShow(c[1]);
  }
  if(after === mpShow(it.value)){ delete MPDRAFT[key]; paintCfg(); return; }
  // ⚠port: the OTEL endpoint in ~/.claude/settings.json follows in the same confirm, only in its local form.
  const ot = key === 'port' && MPSRV.otel && MPSRV.otel.value, np = reset ? it.default : body.value;
  let extra = '';
  if(ot && MPSRV.otel.ok){
    body.otel = true;
    extra = '\n\n' + (MPSRV.cc_path || '~/.claude/settings.json') + '\nOTEL_EXPORTER_OTLP_ENDPOINT\n' + ot + '\n→ ' + ot.replace(/:\d+(\/?)$/, ':' + np + '$1')
      + '\n' + T('Sessions already running report to the new port after they restart');
  } else if(ot) extra = '\n\n' + T('OTEL_EXPORTER_OTLP_ENDPOINT was set by hand, so it is left as is') + ': ' + ot;
  const lab = T((MP_SRV_LAB[key] || [key])[0]) + (MP_SRV_LAB[key] ? ' (' + key + ')' : '');   // screen label first, raw key after
  if(!confirm(T('Change this server setting? It applies after a restart.') + '\n\n' + lab + '\n' + mpShow(it.value) + '\n→ ' + after + extra)){ delete MPDRAFT[key]; paintCfg(); return; }
  let r = null;
  try{ r = await postJSON('/api/prefs/set', body); }catch(e){ r = e.body || {ok: false, err: String((e && e.message) || e)}; }
  if(!reset && !(r && r.ok)){ const el = document.querySelector('#cfgbox [data-mpin="' + key + '"]'); if(el) MPDRAFT[key] = el.value; }   // refused by the server: keep the text too
  if(r && r.ok){ delete MPERR[key]; delete MPDRAFT[key]; MPDONE[key] = 1; it.value = r.value; it.src = reset ? 'default' : 'file';
    if(r.otel && !r.otel.ok) MPERR[key] = 'OTEL: ' + (r.otel.err || '?'); else if(r.otel && r.otel.value) MPSRV.otel.value = r.otel.value; }
  else MPERR[key] = mpSrvErr(r && r.err);
  paintCfg();
}
// Claude Code keys (sidereus/cc_settings.py). ⚠Only these two keys of ~/.claude/settings.json are ever written.
const MP_CC = {cc_auto_compact: 'autoCompactEnabled', cc_compact_window: 'autoCompactWindow'};
// Read-only hint for the «Saver mode» pane (K = MPSRV.keys); '' = value unknown, line hidden.
function mpCcHint(K){
  const a = K && K.cc_auto_compact, w = K && K.cc_compact_window;
  if(!a || !w) return '';
  if(a.value === false) return T('Auto-compact off');
  if(typeof w.value !== 'number' || !isFinite(w.value) || w.value <= 0) return '';
  return T('Compact threshold: {n}').replace('{n}', fmtTok(w.value));
}
function mpCcPaint(){
  const m = document.getElementById('cfgm'), ae = document.activeElement;
  if(CFGCAT !== 'me' || !m || m.hidden || (ae && (ae.tagName === 'INPUT' || ae.tagName === 'SELECT') && m.contains(ae))) return;   // ⚠a repaint would drop typed text
  paintCfg();
}
function mpCcPane(){
  const K = MPSRV.keys, a = K.cc_auto_compact, w = K.cc_compact_window;
  if(!a || !w) return '';
  const note = k => MPERR[k] ? '<span class="mpnote err">' + esc(MPERR[k]) + '</span>'
    : MPDONE[k] ? '<span class=mpnote>' + esc(T(MPDONE[k] === 2 ? 'Checking…' : 'Applies from new sessions')) + '</span>' : '';
  let h = '<div class=cfgpd>' + esc(T('Claude Code settings')) + ': <code>' + esc(MPSRV.cc_path || a.path || '') + '</code> · ' + esc(T('Applies from new sessions'))
    + ' · ' + esc(T('A running Claude Code may rewrite this file, so it is re-read after 3 seconds to check.')) + '</div>';
  if(MPSRV.cc_err) h += '<div class="cfgpd err">' + esc(MPSRV.cc_err) + '</div>';
  const accts = Array.isArray(MPSRV.cc_accts) ? MPSRV.cc_accts : [];
  if(accts.length){
    const on = mpAcctOn();
    h += cfgSet(T('Account'), '', cfgSeg(T('Account'), cfgOpt('mpacm', 'off', T('Same for all accounts'), !on) + cfgOpt('mpacm', 'on', T('Per account'), on))
      + (on ? cfgOpt('mpacs', 'go', T('Apply to changed accounts'), false) + note('cc_accounts')
        + (MPANOTE && !MPERR.cc_accounts ? '<span class=mpnote>' + esc(MPANOTE) + '</span>' : '') : ''), true);
    if(on) return h + mpAcctPane();
  }
  // Other accounts' settings.json: one line only where its value differs from the primary (a save writes them all).
  accts.forEach(x => {
    const d = [];
    if(x.err) d.push(x.err);
    else {
      if(x.auto !== a.value) d.push('autoCompactEnabled ' + String(x.auto));
      if(x.window !== w.value) d.push('autoCompactWindow ' + (x.window == null ? T('None') : String(x.window)));
    }
    if(d.length) h += '<div class=cfgpd>' + esc(String(x.label || '') + ': ' + d.join(' · ')) + '</div>';
  });
  h += cfgSet(T('Auto-compact'), T('Claude Code summarises the conversation when the context fills up.') + ' (autoCompactEnabled)',
    cfgSeg(T('Auto-compact'), cfgOpt('mpcc', 'cc_auto_compact:on', T('On', 'state'), a.value === true) + cfgOpt('mpcc', 'cc_auto_compact:off', T('Off', 'state'), a.value === false))
    + note('cc_auto_compact'));
  h += cfgSet(T('Compact threshold (tokens)'), T("Auto-compacts at this many tokens (50000-1000000). A change is recorded in the auto-compact history under today's date.") + ' (autoCompactWindow)'
      + (w.value == null ? ' · ' + T('Unset now, so the model window decides.') : ''),
    '<input class="svin mpin" data-mpcin=cc_compact_window type=number min=50000 max=1000000 step=10000 value="' + esc('cc_compact_window' in MPDRAFT ? MPDRAFT.cc_compact_window : w.value == null ? '' : String(w.value))
      + '" aria-label="' + esc(T('Compact threshold (tokens)')) + '">' + cfgOpt('mpcc', 'cc_compact_window:set', T('Apply'), false) + note('cc_compact_window'), true);
  return h;
}
// «Per account» mode: one auto/window pair per settings.json. MPACON null = derived from the values (not persisted);
//   MPACD = per-path drafts {auto, win (typed text)} so a seg click repaint keeps typed windows.
let MPACON = null, MPACD = {}, MPANOTE = '';
// Primary first; label/path are user data (esc'd at render, never through T()).
function mpAcctRows(){
  const K = MPSRV.keys, ex = Array.isArray(MPSRV.cc_accts) ? MPSRV.cc_accts : [];
  return [{label: MPSRV.cc_primary_label || '', path: MPSRV.cc_path || K.cc_auto_compact.path || '', primary: true,
    auto: K.cc_auto_compact.value, window: K.cc_compact_window.value, err: MPSRV.cc_err || null}].concat(ex.map(x => Object.assign({primary: false}, x)));
}
function mpAcctOn(){
  if(MPACON != null) return MPACON;
  const r = mpAcctRows(), p = r[0];
  return r.slice(1).some(x => !x.err && (x.auto !== p.auto || x.window !== p.window));
}
const mpAcctD = x => MPACD[x.path] || {auto: x.auto, win: x.window == null ? '' : String(x.window)};
function mpAcctPane(){
  return mpAcctRows().map((x, i) => {
    const d = mpAcctD(x), k = 'cc_acct' + i;
    const ctl = cfgSeg(T('Auto-compact'), cfgOpt('mpacc', i + ':on', T('On', 'state'), d.auto === true) + cfgOpt('mpacc', i + ':off', T('Off', 'state'), d.auto === false))
      + '<input class=svin data-mpacct=' + i + ' type=number min=50000 max=1000000 step=10000 style="width:96px" value="' + esc(x.err ? '' : d.win)
      + '" aria-label="' + esc(T('Compact threshold (tokens)')) + '">'
      + (MPERR[k] ? '<span class="mpnote err">' + esc(MPERR[k]) + '</span>' : '');
    return cfgSet(String(x.label || x.path || '?'), String(x.path || '') + (x.err ? ' · ' + T('skipped') + ': ' + String(x.err) : ''), ctl, false, x.err ? String(x.err) : '');
  }).join('');
}
// Typed window text per row, from the live input when painted, else the draft.
function mpAcctWin(x, i){
  const el = document.querySelector && document.querySelector('#cfgbox [data-mpacct="' + i + '"]');
  return el ? String(el.value) : mpAcctD(x).win;
}
const mpAcctFmt = a => String(a && a.auto) + ',' + (a == null || a.window == null ? T('None') : String(a.window));
function mpAcctApply(){ return mpOnce('cc_accounts', mpAcctApplyRun); }
async function mpAcctApplyRun(){
  const rows = mpAcctRows(), accts = [];
  let bad = false;
  MPANOTE = ''; delete MPERR.cc_accounts;
  rows.forEach((x, i) => {
    delete MPERR['cc_acct' + i];
    if(x.err) return;
    const d = mpAcctD(x), t = mpAcctWin(x, i).trim();
    MPACD[x.path] = {auto: d.auto, win: t};
    let w = null;
    if(t !== '' || x.window != null){   // unset stays unset; clearing a set value is refused like the single field
      const n = Number(t), c = t === '' || !isFinite(n) ? [false, T('Enter a number')] : mpCheck('cc_compact_window', n);
      if(!c[0]){ MPERR['cc_acct' + i] = mpBad(c[1]); bad = true; return; }
      w = c[1];
    }
    accts.push({path: x.path, auto: d.auto, window: w});
  });
  if(bad){ paintCfg(); return; }
  const post = async dry => { try{ return await postJSON('/api/prefs/set', {key: 'cc_accounts', dry: dry, accts: accts}); }
    catch(e){ return e.body || {ok: false, err: String((e && e.message) || e)}; } };
  const r0 = await post(true);
  if(!(r0 && r0.ok)){ MPERR.cc_accounts = mpSrvErr(r0 && r0.err); paintCfg(); return; }
  const files = Array.isArray(r0.files) ? r0.files : [], nm = f => String(f.label || '') + ' ' + String(f.path || '');
  const ch = files.filter(f => f && f.status === 'change'), sk = files.filter(f => f && f.status === 'skipped');
  const skTxt = sk.map(f => nm(f) + '\n' + T('skipped') + ': ' + String(f.err || '?'));
  if(!ch.length){ MPANOTE = [T('No account changed')].concat(sk.map(f => nm(f) + ' ' + T('skipped') + ': ' + String(f.err || '?'))).join(' · '); paintCfg(); return; }
  const msg = ch.map(f => nm(f) + '\n' + mpAcctFmt(f.before) + ' → ' + mpAcctFmt(f.after)).concat(skTxt).join('\n\n');
  if(!confirm(T('Change this Claude Code setting? It applies from new sessions.') + '\n\n' + msg)){ paintCfg(); return; }
  const r = await post(false);
  if(!(r && r.ok)){ MPERR.cc_accounts = mpSrvErr(r && r.err); paintCfg(); return; }
  const out = Array.isArray(r.files) ? r.files : [], wr = out.filter(f => f && f.status === 'written');
  const miss = out.filter(f => f && (f.status === 'skipped' || f.status === 'failed'));
  if(r.hist_err) MPERR.cc_accounts = T('Applied, but the auto-compact history was not updated') + ': ' + r.hist_err;
  if(miss.length){
    const m = T('Applied, but not to') + ': ' + miss.map(f => String(f.label || f.path || '?') + ' (' + String(f.err || f.status) + ')').join(', ');
    MPERR.cc_accounts = MPERR.cc_accounts ? MPERR.cc_accounts + ' · ' + m : m;
  }
  MPDONE.cc_accounts = 2; MPACD = {};
  mpAcctLocal(MPSRV, wr);
  paintCfg();
  // ⚠Same 3 s re-read as mpCcSet: a running Claude Code may write a settings.json back.
  setTimeout(async () => {
    let g = null;
    try{ g = await getJSON('/api/prefs'); }catch(e){ g = null; }
    if(!(g && g.ok && g.keys)) MPERR.cc_accounts = T('Could not re-read');
    else {
      MPSRV = g; MPSRV_AT = Date.now();
      const now = {}; mpAcctRows().forEach(x => { now[x.path] = x; });
      const back = wr.filter(f => { const x = now[f.path]; return !x || x.auto !== (f.after || {}).auto || x.window !== (f.after || {}).window; });
      if(back.length) MPERR.cc_accounts = T('Not applied') + ' — ' + T('a running Claude Code wrote the file back') + ' (' + back.map(nm).join(', ') + ')';
      else MPDONE.cc_accounts = 1;
    }
    mpCcPaint();
  }, 3000);
}
// Mirror written values into MPSRV so the rows show them before the re-read lands.
function mpAcctLocal(s, wr){
  wr.forEach(f => {
    const a = f.after || {};
    if(f.primary){ s.keys.cc_auto_compact.value = a.auto; s.keys.cc_compact_window.value = a.window; return; }
    (Array.isArray(s.cc_accts) ? s.cc_accts : []).forEach(x => { if(x.path === f.path){ x.auto = a.auto; x.window = a.window; } });
  });
}
function mpCcSet(key, val){ return mpOnce(key, () => mpCcSetRun(key, val)); }
async function mpCcSetRun(key, val){
  const it = MPSRV && MPSRV.keys && MPSRV.keys[key];
  if(!it || !MP_CC[key]) return;
  delete MPERR[key];
  let raw = null;
  if(key === 'cc_compact_window'){
    const el = document.querySelector('#cfgbox [data-mpcin="' + key + '"]'), t = el ? String(el.value).trim() : '', n = Number(t);
    raw = el ? el.value : '';
    const c = t === '' || !isFinite(n) ? [false, T('Enter a number')] : mpCheck(key, n);   // refused, not clamped (see MP_RULE)
    if(!c[0]){ MPERR[key] = mpBad(c[1]); MPDRAFT[key] = raw; paintCfg(); return; }
    val = c[1];
  }
  if(val === it.value){ delete MPDRAFT[key]; paintCfg(); return; }
  const show = v => v == null ? T('None') : String(v);
  const lab = T(key === 'cc_auto_compact' ? 'Auto-compact' : 'Compact threshold (tokens)') + ' (' + MP_CC[key] + ')';
  // One «path / old → new» block per account file, primary first; files the server will skip say why.
  const accts = Array.isArray(MPSRV.cc_accts) ? MPSRV.cc_accts : [];
  const blocks = accts.map(x => (x.path || '') + '\n' + (x.err ? T('skipped') + ': ' + x.err
    : show(key === 'cc_auto_compact' ? x.auto : x.window) + '\n→ ' + show(val)));
  const msg = !accts.length ? (MPSRV.cc_path || it.path || '') + '\n' + lab + '\n' + show(it.value) + '\n→ ' + show(val)
    : lab + '\n\n' + [(MPSRV.cc_path || it.path || '') + '\n' + show(it.value) + '\n→ ' + show(val)].concat(blocks).join('\n\n');
  if(!confirm(T('Change this Claude Code setting? It applies from new sessions.') + '\n\n' + msg)){
    delete MPDRAFT[key]; paintCfg(); return; }
  let r = null;
  try{ r = await postJSON('/api/prefs/set', {key: key, value: val}); }catch(e){ r = e.body || {ok: false, err: String((e && e.message) || e)}; }
  if(!(r && r.ok)){ MPERR[key] = mpSrvErr(r && r.err); if(raw != null) MPDRAFT[key] = raw; paintCfg(); return; }
  delete MPERR[key]; delete MPDRAFT[key]; MPDONE[key] = 2; it.value = r.value;
  if(r.hist_err) MPERR[key] = T('Applied, but the auto-compact history was not updated') + ': ' + r.hist_err;
  const miss = (Array.isArray(r.files) ? r.files : []).filter(f => f && (f.status === 'skipped' || f.status === 'failed'));
  if(miss.length){
    const m = T('Applied, but not to') + ': ' + miss.map(f => String(f.label || f.path || '?') + ' (' + String(f.err || f.status) + ')').join(', ');
    MPERR[key] = MPERR[key] ? MPERR[key] + ' · ' + m : m;
  }
  paintCfg();
  // ⚠A running Claude Code may write settings.json back — re-read after 3 s and flag a revert.
  setTimeout(async () => {
    let g = null;
    try{ g = await getJSON('/api/prefs'); }catch(e){ g = null; }
    const now = g && g.ok && g.keys && g.keys[key];
    if(!now) MPERR[key] = T('Could not re-read');
    else if(now.value !== r.value) MPERR[key] = T('Not applied') + ' — ' + T('a running Claude Code wrote the file back') + ' (' + show(now.value) + ')';
    else MPDONE[key] = 1;
    if(g && g.ok && g.keys){ MPSRV = g; MPSRV_AT = Date.now(); }
    mpCcPaint();
  }, 3000);
}
// «Main account» row, only with 2+ accounts. ⚠Labels are user data: esc'd by cfgSel, never passed through T().
function mpMainAcctRow(){
  const list = typeof acctList === 'function' ? acctList() : null;
  if(!list) return '';
  const items = [['', T('Default account')]].concat(list.filter(a => a && !a.primary && a.label).map(a => [String(a.label), String(a.label)]));
  return cfgSet(T('Main account'), '', cfgSel('mpma', T('Main account'), items, mainAcct()));   // 40b mainAcct: stale label reads as ''
}
function mpMainAcctRedraw(){
  [typeof buildSessions === 'function' && buildSessions,
   typeof srecPaint === 'function' && srecPaint, typeof buildAttn === 'function' && buildAttn,
   typeof pollMainRedraw === 'function' && pollMainRedraw,   // 95: SV + burndown + saver badge before the bar reads them
   typeof buildSbar === 'function' && (() => buildSbar()), sesdrBadge].forEach(f => {   // 41 sesdrBadge: header count follows sesCount at once
    if(f) try{ f(); }catch(e){ softErr('mpMainAcct', e); }
  });
}
// Pane body. Buttons use data-mp* keys that mpActs() handles via cfgBind's generic .strp binding.
function cfgPaneMe(){
  const opt = cfgOpt, set = cfgSet, seg = cfgSeg, sel = cfgSel, H = s => '<div class=cfgs>' + esc(s) + '</div>';
  const lab = {time: T('Timeline'), chat: T('Chat'), struct: T('Structure'), br: T('Branches'), pipe: T('Pipelines'), token: T('Tokens'), hist: T('History'), retro: T('Insights')};
  const list = (p, labs, k, lock) => '<div class=mpls>' + p.order.map((x, i) => {
    const hid = p.hide.includes(x);
    return '<div class="mpli' + (hid ? ' off' : '') + '"><span>' + esc(labs[x]) + '</span>'
      + '<button class=strp data-' + k + '="' + x + ':up" title="' + esc(T('Up')) + '" aria-label="' + esc(labs[x] + ' ' + T('Up')) + '"' + (i ? '' : ' disabled') + '>↑</button>'
      + '<button class=strp data-' + k + '="' + x + ':down" title="' + esc(T('Down')) + '" aria-label="' + esc(labs[x] + ' ' + T('Down')) + '"' + (i < p.order.length - 1 ? '' : ' disabled') + '>↓</button>'
      + (x === lock ? '<button class=strp disabled title="' + esc(T('The timeline cannot be hidden')) + '">' + esc(T('Shown', 'visible')) + '</button>'
         : '<button class="strp' + (hid ? '' : ' on') + '" data-' + k + '="' + x + ':' + (hid ? 'show' : 'hide') + '" aria-pressed=' + !hid + '>' + esc(hid ? T('hidden') : T('Shown', 'visible')) + '</button>')
      + '</div>';
  }).join('') + '</div>';
  let h = '<div class=cfgpd>' + esc(T('Display items are saved on the viewer server and shared by every browser. Server items are written to config.local.json and apply after a restart.')) + '</div>'
    + H(T('Display'))
    + set(T('Start view'), T('The tab shown first on reload or a fresh open.'),
          sel('mpv', T('Start view'), [['last', T('Last tab viewed')]].concat(MP_TABS.map(k => [k, lab[k]])), mpStart(lsGet('mbStartView', ''))))
    + set(T('Moon mark'), T('The sidebar mark runs through a full lunation every hour, or shows the real phase. Its tooltip always describes the real moon.'),
          sel('mpmoon', T('Moon mark'), [['', T('Hourly cycle')], ['1', T('Real phase')]], moonReal() ? '1' : ''))   // 92e-moon.js
    + set(T('Tab order and visibility'), T('Reorder or hide the view tabs at the top. The timeline cannot be hidden.'), list(mpTabs(), lab, 'mpt', 'time')
          + opt('mpt', 'reset', T('default'), false), true)
    + mpMainAcctRow()
    + set(T('Reset display settings'), T('Returns display settings (sizes, filters, selected tabs and so on) to their initial state. Note drafts and notification permission stay.'),
          opt('mpr', 'go', T('Reset'), false) + (MPERR.uireset ? '<span class="mpnote err">' + esc(MPERR.uireset) + '</span>' : ''))
    + H(T('Server') + ' · ' + T('Applies after restart'));
  mpSrvLoad(false);
  if(!MPSRV) return h + '<div class=cfgpd>' + esc(T('Loading…')) + '</div>';
  if(!MPSRV.ok) return h + '<div class="cfgpd err">' + esc(T('Could not read the server settings')) + ': ' + esc(MPSRV.err || T('unknown error')) + '</div>';
  if(MPSRV.path) h += '<div class=cfgpd>' + esc(T('File')) + ': <code>' + esc(MPSRV.path) + '</code></div>';
  const row = k => {
    const it = MPSRV.keys[k] || {}, l = MP_SRV_LAB[k] || [k, ''], env = it.src === 'env', ro = env || k === 'compact_history';
    const src = '<span class="mpsrc s-' + esc(it.src || 'default') + '">' + esc(env ? 'env' : T(it.src === 'file' ? 'File' : 'default')) + '</span>';
    // ⚠port: the viewer is not restarted here; the new address only answers after a restart, in a new tab.
    const done = k === 'port' ? T('Applies after a restart — open a new tab at the new address') + ': http://127.0.0.1:' + mpShow(it.value) + '/' : T('Applies after restart');
    const note = (MPERR[k] ? '<span class="mpnote err">' + esc(MPERR[k]) + '</span>' : MPDONE[k] ? '<span class=mpnote>' + esc(done) + '</span>' : '');
    // compact_history is display-only: the «Compaction threshold» apply appends to it (mpCcSet), hand edits are not offered.
    const ctl = ro ? '<code class=mpro>' + esc(mpShow(it.value)) + '</code>' + src
      : '<input class="svin mpin" data-mpin="' + esc(k) + '" ' + (k === 'port' ? 'type=number min=1024 max=65535 step=1' : 'type=text') + ' autocomplete=off spellcheck=false value="' + esc(k in MPDRAFT ? MPDRAFT[k] : mpShow(it.value)) + '" aria-label="' + esc(T(l[0])) + '">'
        + src + opt('mps', k + ':set', T('Apply'), false)
        + (it.src === 'file' && mpShow(it.value) !== mpShow(it.default) ? opt('mps', k + ':reset', T('default'), false) : '');   // already default: the button would do nothing
    let dfl = Array.isArray(it.default) && !it.default.length ? T('None') : mpShow(it.default);
    // A Korean default value (e.g. the Korean default sender name) is what actually gets saved — show it as-is, gloss it in en
    if(LANG === 'en' && typeof it.default === 'string' && T(it.default) !== it.default) dfl += ' («' + T(it.default) + '»)';
    return set(T(l[0]), (l[1] ? T(l[1]) + ' ' : '') + T('default') + ': ' + dfl + (env ? ' · ' + T('Set by an environment variable, so it cannot be changed here.')
      : ro ? ' · ' + T("Read-only — applying a compact threshold records it under today's date.") : ''), ctl + note, true);
  };
  const keys = Object.keys(MPSRV.keys).filter(k => !MP_CC[k]), adv = keys.filter(k => MP_ADV.includes(k));
  const advOpen = lsGet('sidereus.cfgadv', '') === '1';
  return h + keys.filter(k => !MP_ADV.includes(k)).map(row).join('')
    + (adv.length ? '<details class=mpadv' + (advOpen ? ' open' : '') + '><summary>' + esc(T('Advanced')) + '</summary>' + adv.map(row).join('') + '</details>' : '')
    + mpCcPane() + mpfPane();   // mpfPane = «Features» (90c-features.js)
}
// «Reset display settings»: the server moves the prefs file to the backup folder; then drop UIS + this tab's view state and reload.
// ⚠rvnotes drafts and notification keys live in localStorage and are left alone; UIS.wipe() stops any later POST.
function mpUiReset(){ return mpOnce('uireset', mpUiResetRun); }
async function mpUiResetRun(){
  if(!confirm(T('Return display settings (sizes, filters, selected tabs and so on) to their initial state? The current settings are moved to the backup folder.'))) return;
  let r = null;
  try{ r = await postJSON('/api/ui-prefs/reset', {}); }catch(e){ r = e.body || {ok: false, err: String((e && e.message) || e)}; }
  if(!(r && r.ok)){ MPERR.uireset = mpSrvErr(r && (r.err || r.error)); paintCfg(); return; }
  delete MPERR.uireset;
  UIS.wipe();
  try{ sessionStorage.clear(); }catch(e){ softErr('uireset-ss', e); }
  location.reload();
}
// Actions merged into cfgActs(); cfgBind repaints after each.
function mpActs(){
  const ord = (key, all, lock, get, redraw) => v => {
    const p = v === 'reset' ? mpOrder(null, all, lock) : mpOrderAct(get(), all, lock, v.split(':')[0], v.split(':')[1]);
    mpPut(key, mpStock(p, all) ? null : p);
    try{ redraw(); }catch(e){ softErr('mpRedraw', e); }
  };
  return {
    mpv: v => mpPut('mbStartView', v === 'last' ? null : mpStart(v)),
    mpmoon: v => { mpPut('mbMoonReal', v === '1' ? '1' : null); try{ moonPaint(); }catch(e){ softErr('moonPaint', e); } },
    mpt: ord('mbTabs', MP_TABS, 'time', mpTabs, () => buildMv()),
    mpma: v => { mpPut('mbMainAcct', v || null); mpMainAcctRedraw(); },
    mps: v => { const i = v.lastIndexOf(':'); return mpSrvSet(v.slice(0, i), v.slice(i + 1) === 'reset'); },
    mpf: v => mpfAct(v),
    mpr: () => { mpUiReset(); },
    mpacm: v => { MPACON = v === 'on'; MPANOTE = ''; delete MPDONE.cc_accounts; delete MPERR.cc_accounts; },
    mpacc: v => { const i = v.indexOf(':'), x = mpAcctRows()[+v.slice(0, i)]; if(x && !x.err) MPACD[x.path] = {auto: v.slice(i + 1) === 'on', win: mpAcctWin(x, +v.slice(0, i))}; },
    mpacs: () => mpAcctApply(),
    mpcc: v => { const i = v.lastIndexOf(':'), k = v.slice(0, i), op = v.slice(i + 1); return mpCcSet(k, op === 'on' ? true : op === 'off' ? false : null); },
  };
}
