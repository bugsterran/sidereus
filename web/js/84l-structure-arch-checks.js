// ── Structure «Architecture» security issues: `/api/arch` `checks.security` (scanners run by the security-checks pipeline) ──────
// Header «Top issues» badge, the issues window and its «Request fix» relay.
// ⚠Tool ids, `why`, files and rules are tool output: esc() always, never through T().
// ⚠The request never sends by itself: preview → a person presses confirm → /api/dm relay (AGENTS.md rule 7).
// Pure: non-negative integer from tool output.
function archChkN(v){ const n = parseInt(v, 10); return isFinite(n) && n > 0 ? n : 0; }
// Pure: valid tools list.
function archChkTools(c){ return (c && Array.isArray(c.tools) ? c.tools : []).filter(t => t && typeof t === 'object' && t.id); }
// Pure: {e, w} totals across tools.
function archChkSum(c){
  let e = 0, w = 0;
  archChkTools(c).forEach(t => { const n = t.n || {}; e += archChkN(n.error); w += archChkN(n.warning); });
  return { e, w };
}
// Pure: one tool's status text; fixed parts through T(), `why` appended raw.
function archChkStat(t){
  const why = String((t && t.why) || '').trim(), s = String((t && t.status) || '');
  if(s === 'ok') return T('ok');
  // ⚠Raw text: every caller escapes (button tip); the runner's why already reads «install: …» / the skip reason.
  if(s === 'missing') return T('not available') + (why ? ': ' + why : '');
  if(s === 'skipped') return T('skipped') + (why ? ': ' + why : '');
  if(s === 'timeout') return T('timed out');
  if(s === 'fail') return T('failed') + (why ? ': ' + why : '');
  return s || '?';
}
// Pure: security object of /api/arch `checks`, or null.
function archChkSec(d){ const c = d && d.checks; return c && c.security && typeof c.security === 'object' ? c.security : null; }
// Pure: top security issues (server caps at 50), errors first, original order kept within each severity.
function archChkTop(d){
  const src = archChkSec(d);
  const top = (src && Array.isArray(src.top) ? src.top : []).filter(x => x && x.file).slice(0, 50);
  return top.filter(x => x.sev === 'error').concat(top.filter(x => x.sev !== 'error'));
}
// Pure: header badge that opens the issues window; '' without security results.
function archChkTopBtn(d){
  const sec = archChkSec(d);
  if(!sec) return '';
  const e = archChkSum(sec).e;   // red only with errors, amber otherwise
  // shown even at 0 so missing scanners stay visible; scanner states in the tooltip
  const tip = archChkTools(sec).map(t => String(t.id) + ' · ' + archChkStat(t)).join('\n');
  return '<button type=button class="strbg strbg-archcki' + (e ? '' : ' strbg-archckiw') + '" data-arck aria-haspopup=dialog title="' + esc(tip) + '">'
    + esc(T('Security {n}').replace('{n}', archChkTop(d).length)) + '</button>';
}
// Pure: one-line rule help — checks.security.rules[item.rk | "tool:rule"]; url kept only when https.
function archChkHelp(c, x){
  const ob = o => o && typeof o === 'object' ? o : {}, R = Object.assign(Object.create(null), ob(ob(c && c.security).rules));   // ⚠null prototype: a «__proto__» key stays data
  const own = k => k && Object.prototype.hasOwnProperty.call(R, k) && R[k] && typeof R[k] === 'object' ? R[k] : null;
  const r = own(String(x.rk || '')) || own(String(x.tool || '') + ':' + String(x.rule || '')) || {};
  const desc = String(r.desc || '').replace(/\s+/g, ' ').trim().slice(0, 140), url = String(r.url || '').trim();
  return { desc, url: /^https:\/\/[^\s"'<>]+$/i.test(url) ? url : '' };
}
// Pure: rule label — rule · CVE aliases (dependency findings, ids only) · package; raw text, callers esc().
function archChkRule(x){ return [x.rule || ''].concat(Array.isArray(x.cve) ? x.cve.filter(c => typeof c === 'string' && /^CVE-\d{4}-\d{4,7}$/.test(c)) : [], x.pkg ? [x.pkg] : []).join(' · '); }
function archChkKey(x){ return [x.tool || '', x.file, parseInt(x.line, 10) || 1, x.rule || ''].join('\t'); }
// Pure: selected items in list order (keys of items no longer listed drop out).
function archChkSel(d, sel){ return archChkTop(d).filter(x => sel && sel[archChkKey(x)]); }
// Pure: fix-request targets = every live cc session, tiered g: 0 cwd is p / under p/ / worktree of p (wt.main),
//   1 lists p in `repos` (touched it, works elsewhere), 2 the rest. Tier, then logged-in first, then most recently active.
//   ⚠`repos` is tier 1, never 0 — it lists every repo a session touched; the body names the target path instead.
function archChkFixCands(sess, p){
  const inRepo = x => !!p && (x.cwd === p || String(x.cwd || '').startsWith(p + '/') || !!(x.wt && x.wt.main && x.wt.main === p));
  const tier = x => inRepo(x) ? 0 : p && Array.isArray(x.repos) && x.repos.indexOf(p) >= 0 ? 1 : 2;
  return (sess || []).filter(x => x && x.sid && x.state !== 'done' && (!x.plat || x.plat === 'cc'))
    .map(x => ({ sid: x.sid, model: x.model || '', id: x.mbox || '', login: mboxIn(x), proj: x.project || archBase(x.cwd), age: +x.ageSec || 0,
      g: tier(x), st: typeof sessLabel === 'function' ? sessLabel(x) : String(x.state || '') }))
    .sort((a, b) => a.g - b.g || (b.login ? 1 : 0) - (a.login ? 1 : 0) || a.age - b.age);
}
// Metadata only: project · sid8 · mailbox id · state · model (no task text).
function archChkCandLabel(c){ return [c.proj, sid8(c.sid), c.id, c.st, c.model].filter(Boolean).join(' · '); }
// Last pick per repo (localStorage sidereus.ckfix = {repo: sid}) if still a candidate, else the first candidate.
function archChkPick(cands, p){
  const m = typeof lsJson === 'function' ? lsJson('sidereus.ckfix', {}) : {}, sid = m && typeof m === 'object' && Object.prototype.hasOwnProperty.call(m, p) ? m[p] : '';
  return (cands.find(c => c.sid === sid) || cands[0] || {}).sid || '';
}
// Pure: DM body (mailbox wire text, not UI): rule · file:line · help only — no code text (rule 1).
function archChkFixBody(p, c, items, home){
  const tools = items.map(x => String(x.tool || '?')).filter((t, i, a) => a.indexOf(t) === i).join(', '), cm = String((c && ((c.security && c.security.commit) || c.commit)) || '').slice(0, 8);
  return 'Please fix these ' + tools + ' findings in ' + p + (cm ? ' (commit ' + cm + ')' : '') + ':\n'
    + 'Target repository: ' + p + ' — work there (cd), not in your own cwd.\n'   // recipient may be a session of another repo (tier 1/2)
    + items.map(x => { const h = archChkHelp(c, x);
      return '- ' + (x.sev === 'error' ? 'error' : 'warning') + ' · ' + (archChkRule(x) || '?') + ' · ' + x.file + ':' + (parseInt(x.line, 10) || 1)
        + (h.desc ? ' — ' + h.desc : '') + (h.url ? ' (' + h.url + ')' : ''); }).join('\n')
    + "\nFix the cause, keep behaviour, run the project's tests."
    + "\nOnce the fix is committed, request a re-analysis of " + p + " so the architecture diagram reflects it — run:\n" + archDmBody(ARCH_PL, p, home);   // map is per commit; a stale one hides the fix
}
// ── «Run security check»: relays a security-checks run request (preview + confirm), or shows the terminal command ──
// ⚠Sidereus never runs the scanners itself (AGENTS.md rule 7): a session of the project runs the pipeline.
const ARCH_SEC_PL = 'security-checks';
// Pure: issues badge, or a «Security check» button that opens the window with no results yet (also on the no-map states).
function archChkEntry(d){
  return archChkTopBtn(d) || (d ? '<button type=button class="strbg strbg-archcki strbg-archckiw" data-arck aria-haspopup=dialog>' + esc(T('Security check')) + '</button>' : '');
}
// Pure: map header entry ('' unless the map payload is ok).
function archChkHdBtn(d){ return d && d.ok ? archChkEntry(d) : ''; }
// Pure: recipients = logged-in live sessions whose cwd or repos is the project (fix-request tiers 0-1 only).
function archChkRunCands(cands){ return (cands || []).filter(c => c && c.g <= 1 && c.login); }
// Pure: DM body (mailbox wire text in the archDmBody format, not UI); absolute paths under the Sidereus repo (home).
function archChkRunBody(p, home){
  const h = home ? String(home).replace(/\/+$/, '') + '/' : '';
  return '파이프라인 ' + ARCH_SEC_PL + ' 실행 — 요청: «' + p + ' 보안 점검»\n'
    + 'Target repository: ' + p + '\n'
    + 'Pipeline: ' + h + '.claude/pipelines/' + ARCH_SEC_PL + '.json (scanners → threat-model review); run it from ' + (h || 'the Sidereus repository') + ' with --repo ' + p + '\n'
    + 'Gate: python3 ' + h + 'scripts/arch_checks.py --verify --last --category security (Windows: py ' + h + 'scripts/arch_checks.py --verify --last --category security)';
}
// Pure: terminal commands {sh, win} for the no-session fallback; null when home is unknown or a path could break the quoting (⚠cmd expands %VAR% / !VAR! even inside quotes).
function archChkRunCmds(p, home){
  const ok = x => !!x && !/["`$%!\r\n]/.test(x), h = String(home || '').replace(/[\\/]+$/, '');
  if(!ok(p) || !ok(h)) return null;
  const tail = ' --repo "' + p + '" --category security';
  return { sh: 'python3 "' + h + '/scripts/arch_checks.py"' + tail, win: 'py "' + h + '/scripts/arch_checks.py"' + tail };
}
// Pure: newest scan time (seconds) the page knows for the project: checks file `at` or the log's last scan.
function archChkScanAt(d){
  const s = archChkSec(d), n = v => typeof v === 'number' && isFinite(v) ? v : 0;
  return s ? Math.max(n(s.at), n(s.log && s.log.at_scan)) : 0;
}
// Pure: run panel — preview + confirm to a session of the project, or the copyable command when none is logged in.
function archChkRunHtml(p, d, S, cands){
  const sent = S.runSent && S.runSent.to ? archChkSentHtml({ sent: S.runSent }) + (S.runSent.done ? '' : '<div class=archckst>' + esc(T('Waiting for the security check results')) + '</div>') : '';
  const err = S.runMsg ? '<div class="archmsg archerr" role=alert>' + esc(S.runMsg) + '</div>' : '';   // run send failure, beside its own button
  if(!S.run) return sent + err;
  const home = archHome(d), rc = archChkRunCands(cands), head = '<div class=archrqh><b>' + esc(T('Run security check')) + '</b>';
  if(!rc.length){
    const cm = archChkRunCmds(p, home), row = (k, lb) => '<div class=archckst><small>' + esc(lb) + '</small> <code>' + esc(cm[k]) + '</code> <button type=button class=wkrgb data-ckcp="' + k + '">'
      + esc(S.cp && S.cp.k === k ? T(S.cp.ok ? 'Copied' : 'Copy failed — select and copy') : T('Copy')) + '</button></div>';
    return '<div class=archreq role=group aria-label="' + esc(T('Run security check')) + '">' + head + '</div>'
      + '<div class=archckst>' + esc(T('No session of this project is logged in to the mailbox — run this in a terminal:')) + '</div>'
      + (cm ? row('sh', 'macOS / Linux') + row('win', 'Windows') : '<div class=archwhy>' + esc(T('The Sidereus repository location is unknown')) + '</div>')
      + '<div class=archrqb><button type=button class=wkrgb data-ckrx>' + esc(T('Cancel')) + '</button></div></div>' + sent;
  }
  const cur = rc.find(c => c.sid === S.run.sid) || null, body = archChkRunBody(p, home), off = !home ? T('The Sidereus repository location is unknown') : !cur ? T('No live session') : '';
  return '<div class=archreq role=group aria-label="' + esc(T('Run security check')) + '">' + head
    + '<label>' + esc(T('To session')) + ' <select data-ckrs>' + rc.map(x => '<option value="' + esc(x.sid) + '"' + (cur && x.sid === cur.sid ? ' selected' : '') + '>' + esc(archChkCandLabel(x)) + '</option>').join('')
    + '</select></label></div><pre class=archdm>' + esc(body) + '</pre><div class=archrqb>'
    + '<button type=button class="wkrgb archok" data-ckrgo' + (off || S.run.busy ? ' disabled' : '') + (off ? ' title="' + esc(off) + '"' : '') + '>'
    + esc(T(archChkGoLabel({ req: S.run, sent: S.runSent }, archChkReqKey(cur && cur.sid, body)))) + '</button>'
    + '<button type=button class=wkrgb data-ckrx>' + esc(T('Cancel')) + '</button>' + (off ? '<span class=archwhy>' + esc(off) + '</span>' : '') + '</div></div>' + err + sent;
}
// Pure: window body — header (counts · select all · «Request fix»), preview / sent line, issue rows.
function archChkWinHtml(p, d, S, cands){
  const c = d && d.checks, sec = archChkSec(d);
  const top = archChkTop(d), s = archChkSum(sec), sel = archChkSel(d, S.sel), n = sel.length, cm = String((sec && sec.commit) || '').slice(0, 8);
  const why = !cands.length ? T('No live session') : !n ? T('Select at least one issue') : '';
  let h = '<div class=ckwh><b>' + esc(T('Top issues {n}').replace('{n}', top.length)) + '</b><span>' + esc(T('errors {e} · warnings {w}').replace('{e}', s.e).replace('{w}', s.w))
    + '</span><span class=ckwp title="' + esc(p) + '">' + esc(archBase(p) + (cm ? ' · ' + cm : '')) + '</span>'
    + '<label class=ckwa><input type=checkbox data-ckall' + (top.length && top.every(x => S.sel && S.sel[archChkKey(x)]) ? ' checked' : '') + '>' + esc(T('Select all')) + '</label>'
    + '<button type=button class="archgo' + (S.req ? ' on' : '') + '" data-ckfix' + (why ? ' disabled title="' + esc(why) + '"' : '') + '>' + esc(T('Request fix') + (n ? ' (' + n + ')' : '')) + '</button>'
    + (why ? '<span class=archwhy>' + esc(why) + '</span>' : '')
    + '<button type=button class="archgo' + (S.run ? ' on' : '') + '" data-ckrun aria-expanded=' + (S.run ? 'true' : 'false') + (S.run && S.run.busy ? ' disabled' : '') + '>' + esc(T('Run security check')) + '</button></div>';
  h += archChkRunHtml(p, d, S, cands);
  // scanner states (why is tool text: esc)
  if(sec) h += '<div class=archckst>' + esc(archChkTools(sec).map(t => String(t.id) + ' · ' + archChkStat(t)).join(' | ')) + '</div>';
  if(S.req){
    const cur = cands.find(x => x.sid === S.req.sid) || null, off = !n ? T('Select at least one issue') : !cur ? T('No live session') : !cur.login ? T('That session is not logged in to the mailbox') : '';
    h += '<div class=archreq role=group aria-label="' + esc(T('Fix request preview')) + '"><div class=archrqh><b>' + esc(T('Fix request preview')) + '</b>'
      + '<label>' + esc(T('To session')) + ' <select data-cks>' + (cands.length ? [[0, 'This project'], [1, 'Uses this repo'], [2, 'Other sessions']].map(a => { const G = cands.filter(x => x.g === a[0]);
          return G.length ? '<optgroup label="' + esc(T(a[1])) + '">' + G.map(x => '<option value="' + esc(x.sid) + '"' + (x.sid === S.req.sid ? ' selected' : '') + '>' + esc(archChkCandLabel(x)) + '</option>').join('') + '</optgroup>' : ''; }).join('')
        : '<option value="">' + esc(T('None')) + '</option>') + '</select></label></div><pre class=archdm>' + esc(archChkFixBody(p, c, sel, archHome(d))) + '</pre><div class=archrqb>'
      + '<button type=button class="wkrgb archok" data-ckgo' + (off || S.req.busy ? ' disabled' : '') + (off ? ' title="' + esc(off) + '"' : '') + '>' + esc(T(archChkGoLabel(S, archChkReqKey(S.req.sid, archChkFixBody(p, c, sel, archHome(d)))))) + '</button>'
      + '<button type=button class=wkrgb data-ckx>' + esc(T('Cancel')) + '</button>' + (off ? '<span class=archwhy>' + esc(off) + '</span>' : '') + '</div></div>';
  }
  h += archChkSentHtml(S);
  return h + '<ol class=archckl>' + top.map(x => { const k = archChkKey(x), ln = parseInt(x.line, 10) || 1, sv = x.sev === 'error' ? 'error' : 'warning', hp = archChkHelp(c, x);
    return '<li class="' + sv + '"><input type=checkbox data-ckk="' + esc(k) + '"' + (S.sel && S.sel[k] ? ' checked' : '') + ' aria-label="' + esc(x.file + ':' + ln) + '"><div class=ckwr>'
      + '<button type=button data-ckv data-af="' + esc(x.file) + '" data-al="' + esc(ln) + '" title="' + esc(T('View code')) + '">'
      + '<b class=archcks>' + esc(sv === 'error' ? T('error', 'severity') : T('warning', 'severity')) + '</b><small title="' + esc(x.tool || '') + '">' + esc(x.tool || '') + '</small><code title="' + esc(archChkRule(x)) + '">' + esc(archChkRule(x)) + '</code>'
      + '<span class=archckf title="' + esc(x.file + ':' + ln) + '">' + esc(x.file).replace(/\//g, '/<wbr>') + '<span class=archevl>:' + esc(ln) + '</span></span>'   // full path, may break after «/»
      + '<em title="' + esc(x.mod || '') + '">' + esc(x.mod || '') + '</em></button>'
      + (hp.desc || hp.url ? '<div class=archckh>' + (hp.desc ? '<span>' + esc(hp.desc) + '</span>' : '')
        + (hp.url ? '<a href="' + esc(hp.url) + '" target=_blank rel="noopener noreferrer">' + esc(T('docs ↗')) + '</a>' : '') + '</div>' : '') + '</div></li>'; }).join('') + '</ol>'
    + (sec ? archChkLogHtml(sec.log, sec.report) : '<div class=archckst>' + esc(T('No security check yet')) + '</div>');
}
// Pure: read-only security history (sidereus/sec_checks.log_view) — last check age, then open / resolved / false-positive rows.
//   Metadata only (sev · file:line · key · one-line desc); AI review rows are labelled as unverified model output.
function archChkLogHtml(L, rep){
  L = L && typeof L === 'object' ? L : {};
  const arr = k => (Array.isArray(L[k]) ? L[k] : []).filter(x => x && x.file), num = v => typeof v === 'number' && isFinite(v);
  const open = arr('open'), res = arr('resolved'), fp = arr('fp');
  const SV = { critical: T('critical', 'severity'), high: T('high', 'severity'), medium: T('medium', 'severity'), low: T('low', 'severity'), error: T('error', 'severity'), warning: T('warning', 'severity') };
  const ST = { open: T('open', 'finding'), resolved: T('resolved', 'finding'), fp: T('false positive', 'finding') };
  let h = '<div class=archckst>' + esc(num(L.at_scan) ? T('Last security check {t}').replace('{t}', () => agoAt(L.at_scan)) : T('Never checked'))
    + (num(L.at_review) ? ' · ' + esc(T('Last AI review {t}').replace('{t}', () => agoAt(L.at_review))) : '')
    + ' · ' + esc(T('Open {o} · resolved {r} · false positives {f}').replace('{o}', open.length).replace('{r}', res.length).replace('{f}', fp.length)) + '</div>';
  if(rep && typeof rep === 'object' && typeof rep.name === 'string' && rep.name)   // security.report {name, at}: name is file data, esc
    h += '<div class=archckst><button type=button class=wkrgb data-ckrep="' + esc(rep.name) + '" title="' + esc(rep.name) + '">'
      + esc(T('Last report {t}').replace('{t}', () => num(rep.at) ? hhmm(rep.at, {date: true}) : rep.name)) + '</button></div>';
  const rows = [[open, 'open'], [res, 'resolved'], [fp, 'fp']].map(a => a[0].map(x => {
    const ln = parseInt(x.line, 10) || 1, sv = ['critical', 'high', 'error'].indexOf(x.sev) >= 0 ? 'error' : 'warning';
    const when = a[1] === 'open' ? '' : (num(x.at) ? ' · ' + hhmm(x.at, {date: true}) : '') + (x.commit ? ' · ' + String(x.commit).slice(0, 7) : '');
    return '<li class="' + sv + '"><div class=ckwr><button type=button data-ckv data-af="' + esc(x.file) + '" data-al="' + esc(ln) + '" title="' + esc(T('View code')) + '">'
      + '<b class=archcks>' + esc(SV[x.sev] || String(x.sev || '')) + '</b><small>' + esc(x.ai ? T('model-generated, unverified') : String(x.key || '').split(':')[0]) + '</small>'
      + '<code title="' + esc(x.key || '') + '">' + esc(x.ai ? x.key || '' : String(x.key || '').split(':').slice(1).join(':')) + '</code>'
      + '<span class=archckf title="' + esc(x.file + ':' + ln) + '">' + esc(x.file).replace(/\//g, '/<wbr>') + '<span class=archevl>:' + esc(ln) + '</span></span>'
      + '<em>' + esc(ST[a[1]] + when) + '</em></button>' + (x.ai && x.desc ? '<div class=archckh><span>' + esc(x.desc) + '</span></div>' : '') + '</div></li>';
  }).join('')).join('');
  return h + (rows ? '<ol class=archckl>' + rows + '</ol>' : '');
}
// Pure: one request = recipient + exact body; a repeat of the last sent one needs a second deliberate click (archChkGoLabel).
function archChkReqKey(sid, body){ return String(sid || '') + '\n' + String(body || ''); }
// ⚠A repeat is armed, not disabled: re-sending the same request is sometimes intended (the session lost it), but never by one click.
function archChkGoLabel(S, key){ return S.req.busy ? 'Sending…' : S.sent && S.sent.key === key && !S.req.again ? 'Sent · send again' : 'Confirm — send'; }
// Pure: success line (ok colour, check, send time) or the error line; shared with 48i «Ask AI».
function archChkSentHtml(S){
  return (S.sent && S.sent.to ? '<div class="archckst archsent" role=status><span aria-hidden=true>✓</span> ' + esc(T('Requested → {s} · {t}').replace('{s}', () => S.sent.to).replace('{t}', () => S.sent.at || '')) + '</div>' : '')
    + (S.msg ? '<div class="archmsg archerr" role=alert>' + esc(S.msg) + '</div>' : '');
}
// Issues window: one named window (about:blank written like 81 strPopWrite, no route); ARCH_CW = {p, w, sel, req, sent, msg}.
let ARCH_CW = null;
// ⚠Events are forwarded by a script in the window's own realm: window.open (code popup) needs that window's user activation.
const ARCH_CW_JS = "['click','change','keydown'].forEach(function(t){document.addEventListener(t,function(e){try{if(opener&&opener.archChkWinEv)opener.archChkWinEv(e,window);}catch(x){}});});";
function archChkWinOpen(p){
  if(!ARCH.cache[p]) return;   // opens without results too: «Run security check» starts the first one
  let w = ARCH_CW && ARCH_CW.w;
  try{ if(w && w.closed) w = null; }catch(e){ w = null; }
  if(w && ARCH_CW.p === p){ try{ w.focus(); }catch(e){ softErr('archck-focus', e); } archChkWinPaint(); return; }
  if(!w){ try{ w = window.open('', 'sidereus_checks', popFeat(1100, 760, 0) + ',scrollbars=yes,resizable=yes'); }catch(e){ w = null; softErr('archck-open', e); } }
  if(!w){ note(T('Popup blocked — allow popups for this site.')); return; }
  const css = Array.prototype.map.call(document.querySelectorAll('style'), z => z.textContent).join('\n'), dc = w.document;
  dc.open();
  dc.write('<!doctype html><meta charset=utf-8><title>' + esc(T('Top issues {n}').replace('{n}', archChkTop(ARCH.cache[p]).length)) + '</title><style>' + css + '</style>'
    + '<body class=ckwin><div id=ckroot></div><script>' + ARCH_CW_JS + '</' + 'script>');
  dc.close();
  strWinTheme(w);
  ARCH_CW = { p, w, sel: Object.create(null), req: null, sent: '', msg: '', run: null, runSent: null, cp: null, seen: ARCH.cache[p] };
  try{ w.focus(); }catch(e){ softErr('archck-focus', e); }
  archChkWinPaint();
}
function archChkWinPaint(){
  const S = ARCH_CW, w = S && S.w;
  try{ if(!w || w.closed) return false; }catch(e){ return false; }
  const root = w.document.getElementById('ckroot');
  if(!root) return false;
  const cands = archChkFixCands(SESS, S.p), l = root.querySelector('.archckl'), st = l ? l.scrollTop : 0;   // ⚠innerHTML resets the list scroll
  if(S.req && cands.length && !cands.some(c => c.sid === S.req.sid)) S.req.sid = archChkPick(cands, S.p);
  root.innerHTML = archChkWinHtml(S.p, ARCH.cache[S.p], S, cands);
  const l2 = root.querySelector('.archckl'); if(l2) l2.scrollTop = st;
  w.document.title = T('Top issues {n}').replace('{n}', archChkTop(ARCH.cache[S.p]).length) + ' — ' + archBase(S.p);
  return true;
}
// Events from the issues window (forwarded by ARCH_CW_JS). Esc closes the preview first, then the window.
function archChkWinEv(e, w){
  const S = ARCH_CW, t = e && e.target && e.target.closest ? e.target : null;
  if(!S || S.w !== w || !t) return;
  if(e.type === 'keydown'){
    if(e.key !== 'Escape') return;
    e.preventDefault();
    if(S.req && !S.req.busy){ S.req = null; archChkWinPaint(); } else w.close();
    return;
  }
  if(e.type === 'change'){
    if(t.matches('[data-ckall]')){
      archChkTop(ARCH.cache[S.p]).forEach(x => { const k = archChkKey(x); if(t.checked) S.sel[k] = 1; else delete S.sel[k]; }); }
    else if(t.matches('[data-ckk]')){ if(t.checked) S.sel[t.dataset.ckk] = 1; else delete S.sel[t.dataset.ckk]; }
    else if(t.matches('[data-cks]') && S.req){ S.req.sid = t.value; S.req.again = false; }
    else if(t.matches('[data-ckrs]') && S.run){ S.run.sid = t.value; S.run.again = false; }
    else return;
    archChkWinPaint(); return;
  }
  let b;
  if((b = t.closest('[data-ckv]'))){ strPopOpenRel(S.p, b.dataset.af, parseInt(b.dataset.al, 10) || 1, 80, ''); return; }
  if((b = t.closest('[data-ckrep]'))){ archChkReportOpen(S.p, b.dataset.ckrep); return; }
  if(t.closest('[data-ckfix]')){
    if(!S.req){ S.req = { sid: archChkPick(archChkFixCands(SESS, S.p), S.p), busy: false }; S.msg = ''; }   // S.sent stays: it marks a repeat
    else if(!S.req.busy) S.req = null;   // second press closes the preview
    archChkWinPaint(); return;
  }
  if(t.closest('[data-ckrun]')){
    if(!S.run){ S.run = { sid: (archChkRunCands(archChkFixCands(SESS, S.p))[0] || {}).sid || '', busy: false }; S.runMsg = ''; S.cp = null; }
    else if(!S.run.busy) S.run = null;
    archChkWinPaint(); return;
  }
  if(t.closest('[data-ckrx]')){ if(S.run && !S.run.busy) S.run = null; archChkWinPaint(); return; }
  if(t.closest('[data-ckrgo]')){ archChkRunSend(); return; }
  if((b = t.closest('[data-ckcp]'))){ archChkCopy(S, w, b); return; }
  if(t.closest('[data-ckx]')){ if(S.req && !S.req.busy) S.req = null; archChkWinPaint(); return; }
  if(t.closest('[data-ckgo]')) archChkFixSend();
}
// «Last report»: named about:blank window, report text written as an escaped <pre> (no markdown render, no route).
// ⚠window.open runs before the fetch: after an await the click's user activation may be gone and the popup blocked.
async function archChkReportOpen(p, name){
  let w = null;
  try{ w = window.open('', 'sidereus_secreport', popFeat(900, 760, 0) + ',scrollbars=yes,resizable=yes'); }catch(e){ softErr('archrep-open', e); }
  if(!w){ note(T('Popup blocked — allow popups for this site.')); return; }
  const put = body => { const dc = w.document; dc.open(); dc.write('<!doctype html><meta charset=utf-8><title>' + esc(name) + '</title><body style="margin:0">' + body); dc.close(); };
  put('<pre style="padding:12px">' + esc(T('Loading…')) + '</pre>');
  let j = null;
  try{ j = await getJSON('/api/arch/secreport?path=' + encodeURIComponent(p) + '&name=' + encodeURIComponent(name)); }catch(e){ softErr('archrep-get', e); }
  try{ if(w.closed) return; }catch(e){ return; }
  put('<pre style="padding:12px;white-space:pre-wrap;word-break:break-word">' + esc(j && j.ok ? String(j.text || '') : T('Could not load the report') + (j && j.err ? ': ' + j.err : '')) + '</pre>');
  try{ w.focus(); }catch(e){ softErr('archrep-focus', e); }
}
// Guard + send: only the preview's confirm calls this (no auto-send, AGENTS.md rule 7).
async function archChkFixSend(){
  const S = ARCH_CW, q = S && S.req;
  if(!q || q.busy) return false;
  const d = ARCH.cache[S.p], items = archChkSel(d, S.sel), cur = archChkFixCands(SESS, S.p).find(c => c.sid === q.sid);
  if(!items.length || !cur || !cur.login) return false;
  const body = archChkFixBody(S.p, d && d.checks, items, archHome(d)), key = archChkReqKey(cur.sid, body);
  if(S.sent && S.sent.key === key && !q.again){ q.again = true; archChkWinPaint(); return false; }   // first click on «Sent · send again» only arms
  q.busy = true; archChkWinPaint();
  try{
    const j = await postJSON('/api/dm', { to: cur.id, body, relay: true, sid: cur.sid, thread: 'checks-fix' });
    if(!j || !j.ok) throw new Error((j && (j.error || j.err)) || '?');
    S.req = null; S.msg = ''; S.sent = { to: archChkCandLabel(cur), at: hhmm(new Date()), key };
    note(T('Requested → {s} · {t}').replace('{s}', () => S.sent.to).replace('{t}', () => S.sent.at));
    const m = lsJson('sidereus.ckfix', {}), m2 = m && typeof m === 'object' && !Array.isArray(m) ? m : {}; m2[S.p] = cur.sid; lsSetJson('sidereus.ckfix', m2);   // only after the relay is accepted
  }catch(e){ q.busy = false; S.msg = T('Could not send') + ': ' + String((e && e.message) || e); }
  archChkWinPaint();
  return true;
}
// «Copy»: the issues window's own clipboard (the click's user activation lives there); on failure the command is selected.
function archChkCopy(S, w, b){
  const k = b.dataset.ckcp, cm = archChkRunCmds(S.p, archHome(ARCH.cache[S.p])), txt = cm && cm[k];
  if(!txt) return;
  const done = ok => { S.cp = { k, ok }; archChkWinPaint();
    if(!ok){ try{ const c = w.document.querySelector('[data-ckcp="' + k + '"]'), code = c && c.previousElementSibling, r = w.document.createRange(); if(code){ r.selectNodeContents(code); const sl = w.getSelection(); sl.removeAllRanges(); sl.addRange(r); } }catch(e){ softErr('archck-sel', e); } } };
  try{ w.navigator.clipboard.writeText(txt).then(() => done(true), () => done(false)); }catch(e){ done(false); }
}
// Guard + send: only the run preview's confirm calls this (no auto-send, AGENTS.md rule 7).
async function archChkRunSend(){
  const S = ARCH_CW, q = S && S.run;
  if(!q || q.busy) return false;
  const d = ARCH.cache[S.p], home = archHome(d), cur = archChkRunCands(archChkFixCands(SESS, S.p)).find(c => c.sid === q.sid);
  if(!home || !cur) return false;
  const body = archChkRunBody(S.p, home), key = archChkReqKey(cur.sid, body);
  if(S.runSent && S.runSent.key === key && !q.again){ q.again = true; archChkWinPaint(); return false; }   // first click on «Sent · send again» only arms
  q.busy = true; archChkWinPaint();
  try{
    const j = await postJSON('/api/dm', { to: cur.id, body, relay: true, sid: cur.sid, thread: 'pipeline:' + ARCH_SEC_PL });
    if(!j || !j.ok) throw new Error((j && (j.error || j.err)) || '?');
    S.run = null; S.runMsg = ''; S.runSent = { to: archChkCandLabel(cur), at: hhmm(new Date()), key, t: Date.now(), base: archChkScanAt(d) };
    note(T('Requested → {s} · {t}').replace('{s}', () => S.runSent.to).replace('{t}', () => S.runSent.at));
  }catch(e){ q.busy = false; S.runMsg = T('Could not send') + ': ' + String((e && e.message) || e); }
  archChkWinPaint();
  return true;
}
// While the window is open: repaint when the project's /api/arch data changed; after a run request, re-read it every
// ARCH_POLL_MS until a newer scan shows up (gives up after 3 h so a lost request does not poll forever).
function archChkTick(now){
  const S = ARCH_CW;
  if(!S || document.hidden) return false;
  try{ if(!S.w || S.w.closed) return false; }catch(e){ return false; }
  const d = ARCH.cache[S.p];
  if(d !== S.seen){ S.seen = d; archChkWinPaint(); }
  const q = S.runSent;
  if(!q || q.done) return false;
  if(archChkScanAt(d) > q.base){ q.done = 1; note(T('Security check finished — {p}').replace('{p}', () => archBase(S.p))); archChkWinPaint(); return false; }
  if(ARCH.load[S.p] || now - q.t > 3 * 3600000 || now - (q.polled || q.t) < ARCH_POLL_MS) return false;
  q.polled = now;
  archFetch(S.p, true);
  return true;
}
setInterval(() => archChkTick(Date.now()), 5000);
document.addEventListener('click', ev => {
  const t = ev.target && ev.target.closest ? ev.target : null;
  if(!t || !t.closest('.archtab') || strMode !== 'arch') return;
  if(t.closest('[data-arck]')) archChkWinOpen(strOn[0] || '');
});
