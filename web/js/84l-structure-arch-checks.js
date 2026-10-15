// ── Structure «Architecture» project checks: `/api/arch` `checks` (lint/type tools run by the project-checks pipeline) ──────
// Header badges (incl. the «Top issues» popup), per-module count badges on the overview, focus chip, and the «Run project checks» request.
// ⚠Tool ids, `why`, files and rules are tool output: esc() always, never through T().
// ⚠The request never sends by itself: preview → a person presses confirm → /api/dm relay (AGENTS.md rule 7).
const ARCH_CHK_PL = 'project-checks';
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
  // ⚠Raw text: every caller escapes (strHdBadge tip); the runner's why already reads «install: …» / the skip reason.
  if(s === 'missing') return T('not available') + (why ? ': ' + why : '');
  if(s === 'skipped') return T('skipped') + (why ? ': ' + why : '');
  if(s === 'timeout') return T('timed out');
  if(s === 'fail') return T('failed') + (why ? ': ' + why : '');
  return s || '?';
}
// Pure: header badges — «Checks {n} · errors {e} · warnings {w}» («cut» when stale), a default-rules chip, a source-changed chip.
function archChkBadge(d){
  const c = d && d.checks && typeof d.checks === 'object' ? d.checks : null;
  if(!c) return '';
  const ts = archChkTools(c), s = archChkSum(c);
  if(!ts.length && !c.commit) return archChkTopBtn(d);   // security results only (empty quality shell)
  const line = t => { const n = t.n || {};
    return String(t.id) + ' · ' + archChkStat(t) + (t.rules === 'default' ? ' · ' + T('default rules') : '')
      + ' · ' + T('errors {e} · warnings {w}').replace('{e}', archChkN(n.error)).replace('{w}', archChkN(n.warning)); };
  const cm = String(c.commit || '').slice(0, 7), at = typeof c.at === 'number' && isFinite(c.at) && c.at > 0 ? c.at : 0;
  const head = (cm || at ? T('Checked {t} · {c}').replace('{t}', at ? hhmm(at, { date: true, dsep: '-' }) : '?').replace('{c}', cm || '?') + '\n' : '')
    + (c.stale ? T('Older than HEAD') + '\n' : '') + (c.dirty ? T('Uncommitted changes were checked') + '\n' : '');
  // n counts tools with status ok only; the tooltip lists every tool.
  const df = ts.filter(t => t.rules === 'default' && (t.status === 'ok' || t.status === 'fail')).map(t => String(t.id));   // ⚠tools that never ran applied no rules
  return strHdBadge(c.stale ? 'cut archckh' : 'archckh', T('Checks {n} · errors {e} · warnings {w}').replace('{n}', ts.filter(t => t.status === 'ok').length).replace('{e}', s.e).replace('{w}', s.w),
      head + ts.map(line).join('\n'))
    + archChkTopBtn(d)
    + (df.length ? strHdBadge('archckd', T('default rules'), T("Not the project's own standard") + '\n' + df.join(', ')) : '')
    + (c.src_changed ? strHdBadge('cut', T('Source changed during checks')) : '');
}
// Pure: {e, w} for module id, null when both are 0.
function archChkOf(c, id){
  const M = c && c.mods && typeof c.mods === 'object' ? c.mods : {};
  const x = Object.prototype.hasOwnProperty.call(M, id) ? M[id] : null;
  const e = archChkN(x && x.error), w = archChkN(x && x.warning);
  return e || w ? { e, w } : null;
}
// Pure: focus-view chip beside the module name; '' when the module has no issues.
function archChkChip(id, d){
  const k = archChkOf(d && d.checks, id);
  if(!k) return '';
  return '<span class=archckc>' + (k.e ? '<em class="archbg archbad">' + esc(T('errors {n}').replace('{n}', k.e)) + '</em>' : '')
    + (k.w ? '<em class="archbg archest">' + esc(T('warnings {n}').replace('{n}', k.w)) + '</em>' : '') + '</span>';
}
// Pure: SVG count pills straddling the node's top-right corner (errors right, warnings left of them).
function archChkSvg(R, k){
  if(!R || !k || !(k.e || k.w)) return '';
  const f = v => (Math.round(v * 10) / 10).toString(), lab = n => n > 99 ? '99+' : String(n);
  const pill = (x2, n, cls) => { const t = lab(n), w = Math.max(14, 6.4 * t.length + 8), x = x2 - w;
    return { x, s: '<rect class="' + cls + '" x="' + f(x) + '" y="' + f(R.y - 7) + '" width="' + f(w) + '" height="14" rx="7"/>'
      + '<text class=archckt x="' + f(x + w / 2) + '" y="' + f(R.y) + '" text-anchor=middle dominant-baseline=central>' + esc(t) + '</text>' }; };
  let x2 = R.x + R.w + 4, o = '';
  if(k.e){ const p = pill(x2, k.e, 'archcke'); o += p.s; x2 = p.x - 2; }
  if(k.w) o += pill(x2, k.w, 'archckw').s;
  const tip = T('errors {e} · warnings {w}').replace('{e}', k.e).replace('{w}', k.w);
  return '<g class=archckb><title>' + esc(tip) + '</title>' + o + '</g>';
}
// Node box from its first rect (81e draws rect shapes); getBBox otherwise.
function archChkBox(g){
  const r = g.querySelector('rect');
  if(r){ const a = n => parseFloat(r.getAttribute(n)); const R = { x: a('x'), y: a('y'), w: a('width'), h: a('height') };
    if([R.x, R.y, R.w, R.h].every(isFinite)) return R; }
  try{ const b = g.getBBox(); return b && b.width ? { x: b.x, y: b.y, w: b.width, h: b.height } : null; }catch(e){ return null; }
}
// Overview: count badges on each module node (nodes found by data-p, as archHovPaint does). Idempotent per rendered svg.
function archChkPaint(slot, d){
  const c = d && d.checks, svg = slot && slot.querySelector && slot.querySelector('svg');
  if(!c || !svg) return 0;
  const mods = (d && d.modules) || [];
  let n = 0;
  svg.querySelectorAll('g.mmdn[data-p]').forEach(g => {
    if(g.querySelector('.archckb')) return;
    const m = mods[parseInt(String(g.dataset.p).slice(1), 10)], k = m && archChkOf(c, m.id), R = k && archChkBox(g);
    const s = R ? archChkSvg(R, k) : '';
    if(s){ g.insertAdjacentHTML('beforeend', s); n++; }
  });
  return n;
}
// Pure: top issues of a category (cat 's' = checks.security, else quality; server caps at 50), errors first, original order kept within each severity.
function archChkTop(d, cat){
  const c = d && d.checks, src = cat === 's' ? c && c.security : c;
  const top = (src && Array.isArray(src.top) ? src.top : []).filter(x => x && x.file).slice(0, 50);
  return top.filter(x => x.sev === 'error').concat(top.filter(x => x.sev !== 'error'));
}
// Pure: header badge that opens the issue popup; '' when there is nothing to list.
function archChkTopBtn(d){
  const c = d && d.checks, sec = c && c.security && typeof c.security === 'object' ? c.security : null;
  const n = archChkTop(d).length, e = archChkSum(c).e + archChkSum(sec).e;   // red only with errors, amber otherwise
  const cls = '<button type=button class="strbg strbg-archcki' + (e ? '' : ' strbg-archckiw') + '" data-arck aria-haspopup=dialog';
  if(!sec) return n ? cls + '>' + esc(T('Top issues {n}').replace('{n}', n)) + '</button>' : '';
  // with security results: both counts, security tool states in the tooltip (shown even at 0 so missing scanners stay visible)
  const tip = archChkTools(sec).map(t => String(t.id) + ' · ' + archChkStat(t)).join('\n');
  return cls + ' title="' + esc(tip) + '">' + esc(T('Quality {q} · Security {s}').replace('{q}', n).replace('{s}', archChkTop(d, 's').length)) + '</button>';
}
// Pure: one-line rule help — checks.rules[item.rk | "tool:rule"] (sidereus/arch_checks.load_checks); url kept only when https.
function archChkHelp(c, x){
  const ob = o => o && typeof o === 'object' ? o : {}, R = Object.assign(Object.create(null), ob(ob(c && c.security).rules), ob(c && c.rules));   // ⚠null prototype: a «__proto__» key stays data
  const own = k => k && Object.prototype.hasOwnProperty.call(R, k) && R[k] && typeof R[k] === 'object' ? R[k] : null;
  const r = own(String(x.rk || '')) || own(String(x.tool || '') + ':' + String(x.rule || '')) || {};
  const desc = String(r.desc || '').replace(/\s+/g, ' ').trim().slice(0, 140), url = String(r.url || '').trim();
  return { desc, url: /^https:\/\/[^\s"'<>]+$/i.test(url) ? url : '' };
}
function archChkKey(x){ return [x.tool || '', x.file, parseInt(x.line, 10) || 1, x.rule || ''].join('\t'); }
// Pure: selected items in list order (keys of items no longer listed drop out).
function archChkSel(d, sel){ return archChkTop(d).concat(archChkTop(d, 's')).filter(x => sel && sel[archChkKey(x)]); }
// Pure: fix-request targets = every live cc session, tiered g: 0 cwd is p / under p/ / worktree of p (wt.main),
//   1 lists p in `repos` (touched it, works elsewhere), 2 the rest. Tier, then logged-in first, then most recently active.
//   ⚠`repos` is tier 1, never 0 — it lists every repo a session touched; the body names the target path instead.
function archChkFixCands(sess, p){
  const inRepo = x => !!p && (x.cwd === p || String(x.cwd || '').startsWith(p + '/') || !!(x.wt && x.wt.main && x.wt.main === p));
  const tier = x => inRepo(x) ? 0 : p && Array.isArray(x.repos) && x.repos.indexOf(p) >= 0 ? 1 : 2;
  return (sess || []).filter(x => x && x.sid && x.state !== 'done' && (!x.plat || x.plat === 'cc'))
    .map(x => ({ sid: x.sid, model: x.model || '', id: x.mbox || '', login: !!(x.mbox && x.mboxSrc === 'identity'), proj: x.project || archBase(x.cwd), age: +x.ageSec || 0,
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
  const tools = items.map(x => String(x.tool || '?')).filter((t, i, a) => a.indexOf(t) === i).join(', '), cm = String((c && c.commit) || '').slice(0, 8);
  return 'Please fix these ' + tools + ' findings in ' + p + (cm ? ' (commit ' + cm + ')' : '') + ':\n'
    + 'Target repository: ' + p + ' — work there (cd), not in your own cwd.\n'   // recipient may be a session of another repo (tier 1/2)
    + items.map(x => { const h = archChkHelp(c, x);
      return '- ' + (x.sev === 'error' ? 'error' : 'warning') + ' · ' + (x.rule || '?') + (x.pkg ? ' · ' + x.pkg : '') + ' · ' + x.file + ':' + (parseInt(x.line, 10) || 1)
        + (h.desc ? ' — ' + h.desc : '') + (h.url ? ' (' + h.url + ')' : ''); }).join('\n')
    + "\nFix the cause, keep behaviour, run the project's tests."
    + "\nOnce the fix is committed, request a re-analysis of " + p + " so the architecture diagram reflects it — run:\n" + archDmBody(ARCH_PL, p, home);   // map is per commit; a stale one hides the fix
}
// Pure: window body — header (counts · select all · «Request fix»), preview / sent line, issue rows.
function archChkWinHtml(p, d, S, cands){
  const c = d && d.checks, sec = c && c.security && typeof c.security === 'object' ? c.security : null, cat = sec && S.cat === 's' ? 's' : 'q';
  const top = archChkTop(d, cat), s = archChkSum(cat === 's' ? sec : c), sel = archChkSel(d, S.sel), n = sel.length, cm = String((c && (c.commit || (sec && sec.commit))) || '').slice(0, 8);
  const why = !cands.length ? T('No live session') : !n ? T('Select at least one issue') : '';
  let h = '<div class=ckwh><b>' + esc(T('Top issues {n}').replace('{n}', top.length)) + '</b><span>' + esc(T('errors {e} · warnings {w}').replace('{e}', s.e).replace('{w}', s.w))
    + '</span><span class=ckwp title="' + esc(p) + '">' + esc(archBase(p) + (cm ? ' · ' + cm : '')) + '</span>'
    + '<label class=ckwa><input type=checkbox data-ckall' + (top.length && top.every(x => S.sel && S.sel[archChkKey(x)]) ? ' checked' : '') + '>' + esc(T('Select all')) + '</label>'
    + '<button type=button class="archgo' + (S.req ? ' on' : '') + '" data-ckfix' + (why ? ' disabled title="' + esc(why) + '"' : '') + '>' + esc(T('Request fix') + (n ? ' (' + n + ')' : '')) + '</button>'
    + (why ? '<span class=archwhy>' + esc(why) + '</span>' : '') + '</div>';
  // Quality | Security tabs only with security results; the security tab lists each scanner's state (why is tool text: esc)
  if(sec) h += '<div class=archrqb role=tablist>' + [['q', 'Quality {n}', archChkTop(d).length], ['s', 'Security {n}', archChkTop(d, 's').length]].map(a => '<button type=button role=tab class="archgo' + (a[0] === cat ? ' on' : '')
      + '" data-ckcat=' + a[0] + ' aria-selected=' + (a[0] === cat) + '>' + esc(T(a[1]).replace('{n}', a[2])) + '</button>').join('') + '</div>'
    + (cat === 's' ? '<div class=archckst>' + esc(archChkTools(sec).map(t => String(t.id) + ' · ' + archChkStat(t)).join(' | ')) + '</div>' : '');
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
      + '<b class=archcks>' + esc(sv === 'error' ? T('error', 'severity') : T('warning', 'severity')) + '</b><small title="' + esc(x.tool || '') + '">' + esc(x.tool || '') + '</small><code title="' + esc((x.rule || '') + (x.pkg ? ' · ' + x.pkg : '')) + '">' + esc((x.rule || '') + (x.pkg ? ' · ' + x.pkg : '')) + '</code>'
      + '<span class=archckf title="' + esc(x.file + ':' + ln) + '">' + esc(x.file).replace(/\//g, '/<wbr>') + '<span class=archevl>:' + esc(ln) + '</span></span>'   // full path, may break after «/»
      + '<em title="' + esc(x.mod || '') + '">' + esc(x.mod || '') + '</em></button>'
      + (hp.desc || hp.url ? '<div class=archckh>' + (hp.desc ? '<span>' + esc(hp.desc) + '</span>' : '')
        + (hp.url ? '<a href="' + esc(hp.url) + '" target=_blank rel="noopener noreferrer">' + esc(T('docs ↗')) + '</a>' : '') + '</div>' : '') + '</div></li>'; }).join('') + '</ol>'
    + (cat === 's' ? archChkLogHtml(sec.log) : '');
}
// Pure: read-only security history (sidereus/sec_checks.log_view) — last check age, then open / resolved / false-positive rows.
//   Metadata only (sev · file:line · key · one-line desc); AI review rows are labelled as unverified model output.
function archChkLogHtml(L){
  L = L && typeof L === 'object' ? L : {};
  const arr = k => (Array.isArray(L[k]) ? L[k] : []).filter(x => x && x.file), num = v => typeof v === 'number' && isFinite(v);
  const open = arr('open'), res = arr('resolved'), fp = arr('fp');
  const SV = { critical: T('critical', 'severity'), high: T('high', 'severity'), medium: T('medium', 'severity'), low: T('low', 'severity'), error: T('error', 'severity'), warning: T('warning', 'severity') };
  const ST = { open: T('open', 'finding'), resolved: T('resolved', 'finding'), fp: T('false positive', 'finding') };
  let h = '<div class=archckst>' + esc(num(L.at_scan) ? T('Last security check {t}').replace('{t}', () => agoAt(L.at_scan)) : T('Never checked'))
    + (num(L.at_review) ? ' · ' + esc(T('Last AI review {t}').replace('{t}', () => agoAt(L.at_review))) : '')
    + ' · ' + esc(T('Open {o} · resolved {r} · false positives {f}').replace('{o}', open.length).replace('{r}', res.length).replace('{f}', fp.length)) + '</div>';
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
  const c0 = ARCH.cache[p] && ARCH.cache[p].checks, nq = archChkTop(ARCH.cache[p]).length;
  if(!nq && !(c0 && c0.security)) return;
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
  ARCH_CW = { p, w, sel: Object.create(null), req: null, sent: '', msg: '', cat: nq ? 'q' : 's' };
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
    if(t.matches('[data-ckall]')){ const cs = ARCH.cache[S.p] && ARCH.cache[S.p].checks;   // current tab only; the other tab's ticks stay
      archChkTop(ARCH.cache[S.p], cs && cs.security && S.cat === 's' ? 's' : 'q').forEach(x => { const k = archChkKey(x); if(t.checked) S.sel[k] = 1; else delete S.sel[k]; }); }
    else if(t.matches('[data-ckk]')){ if(t.checked) S.sel[t.dataset.ckk] = 1; else delete S.sel[t.dataset.ckk]; }
    else if(t.matches('[data-cks]') && S.req){ S.req.sid = t.value; S.req.again = false; }
    else return;
    archChkWinPaint(); return;
  }
  let b;
  if((b = t.closest('[data-ckcat]'))){ S.cat = b.dataset.ckcat === 's' ? 's' : 'q'; archChkWinPaint(); return; }
  if((b = t.closest('[data-ckv]'))){ strPopOpenRel(S.p, b.dataset.af, parseInt(b.dataset.al, 10) || 1, 80, ''); return; }
  if(t.closest('[data-ckfix]')){
    if(!S.req){ S.req = { sid: archChkPick(archChkFixCands(SESS, S.p), S.p), busy: false }; S.msg = ''; }   // S.sent stays: it marks a repeat
    else if(!S.req.busy) S.req = null;   // second press closes the preview
    archChkWinPaint(); return;
  }
  if(t.closest('[data-ckx]')){ if(S.req && !S.req.busy) S.req = null; archChkWinPaint(); return; }
  if(t.closest('[data-ckgo]')) archChkFixSend();
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
// Pure: DM body the person previews; same wire format as 84j archDmBody (mailbox text, not UI).
function archChkDmBody(repo, home){
  const h = home ? String(home).replace(/\/+$/, '') + '/' : '';
  return '파이프라인 ' + ARCH_CHK_PL + ' 실행 — 요청: «' + repo + ' 프로젝트 검사»\n'
    + '대상 저장소: ' + repo + '\n'
    + '대상 소스는 읽기 전용 — 소스·설정을 고치지 않음, 결과는 ${MAILBOX_DIR:-~/.mailbox-mcp}/arch/ 아래만 (파이프라인 rules)\n'
    + '파이프라인: ' + h + '.claude/pipelines/' + ARCH_CHK_PL + '.json';
}
// Header button left of the «Architecture | Size» switch (80 head `pre`); toggles the preview, hidden while the sent line shows.
function archChkBtn(p, home, cands){
  const req = ARCH.creq && ARCH.creq.p === p, d = ARCH.cache[p];
  if(!(d && d.checks_runnable === true)) return '';   // ⚠only repos that configure a tool: the runner has no default-tool fallback
  if(!req && (archChkSentOf(p, d) || (typeof archReqBusy === 'function' && archReqBusy(p, ARCH_CHK_PL)))) return '';   // one run per repo (84l2)
  const why = req ? '' : archWhyOff(home, cands, cands[0]);
  return '<button type=button class="archgo archckgo' + (req ? ' on' : '') + '" data-arcq aria-expanded=' + (req ? 'true' : 'false')
    + (why ? ' title="' + esc(why) + '"' : '') + '>' + esc(T('Run project checks')) + '</button>';
}
// Pure: the preview once open, the sent line, or '' (the button itself is archChkBtn in the header).
function archChkReqHtml(req, repo, home, cands, sent){
  if(sent) return '<span class=archckst role=status>' + esc(T('Checks requested') + ' · ' + sent.id + ' · ' + CLK(new Date(sent.at))) + '</span>';
  if(!req) return '';
  const cur = cands.find(c => c.sid === req.sid) || null, why = archWhyOff(home, cands, cur);
  return '<div class=archreq role=group aria-label="' + esc(T('Checks request preview')) + '"><div class=archrqh><b>' + esc(T('Checks request preview')) + '</b>'
    + '<label>' + esc(T('To session')) + ' <select data-arcs>' + (cands.length ? cands.map(c => '<option value="' + esc(c.sid) + '"' + (c.sid === req.sid ? ' selected' : '') + '>'
      + esc((c.dir ? c.dir + ' · ' : '') + sid8(c.sid) + (c.model ? ' · ' + c.model : '') + (c.id ? ' · ' + c.id : '')) + '</option>').join('') : '<option value="">' + esc(T('None')) + '</option>')
    + '</select></label></div><pre class=archdm>' + esc(archChkDmBody(repo, home)) + '</pre><div class=archrqb>'
    + '<button type=button class="wkrgb archok" data-arcgo' + (why || req.busy ? ' disabled' : '') + (why ? ' title="' + esc(why) + '"' : '') + '>' + esc(T(req.busy ? 'Sending…' : 'Confirm — send')) + '</button>'
    + '<button type=button class=wkrgb data-arcx>' + esc(T('Cancel')) + '</button>' + (why ? '<span class=archwhy>' + esc(why) + '</span>' : '') + '</div></div>';
}
// Sent line ends once checks newer than the send arrive.
function archChkSentOf(p, d){
  const q = ARCH.csent;
  if(!q || q.p !== p) return null;
  const c = d && d.checks;
  if(c && typeof c.at === 'number' && c.at * 1000 >= q.at){ ARCH.csent = null; return null; }
  return q;
}
// Strip under the header: checks preview or sent line; '' when neither shows.
function archChkStrip(p, d, home, cands){
  const req = ARCH.creq && ARCH.creq.p === p ? ARCH.creq : null;
  const h0 = archChkReqHtml(req, p, home, cands, req ? null : archChkSentOf(p, d));
  const h = typeof archReqSlot === 'function' ? archReqSlot(p, ARCH_CHK_PL, h0, req ? h0 : '') : h0;   // request record row (84l2)
  return h ? '<div class=archck>' + h + '</div>' : '';
}
// Guard + send: only the confirm button calls this, and only with an open preview (no auto-send).
async function archChkSend(){
  const q = ARCH.creq;
  if(!q || q.busy) return false;
  const home = archHome(ARCH.cache[q.p]), cur = archCands(home, SESS, q.p).find(c => c.sid === q.sid);
  if(!cur || !cur.login || !home) return false;
  q.busy = true; paintStruct();
  try{
    const j = await postJSON('/api/dm', { to: cur.id, body: archChkDmBody(q.p, home), relay: true, sid: cur.sid, thread: 'pipeline:' + ARCH_CHK_PL,
      plreq: { kind: 'req', pipeline: ARCH_CHK_PL, repo: q.p } });   // server records who received it (state `plReq`)
    if(!j || !j.ok) throw new Error((j && (j.error || j.err)) || '?');   // ⚠ok first: nothing went out, remember nothing
    const m = plMem(); m[cur.sid] = { name: ARCH_CHK_PL, at: Date.now() }; lsSetJson('sidereus.plrun', m);
    ARCH.creq = null; ARCH.msg = ''; ARCH.csent = { p: q.p, id: cur.id, at: Date.now() };
  }catch(e){ q.busy = false; ARCH.msg = T('Could not send') + ': ' + String((e && e.message) || e); }
  paintStruct();
  return true;
}
document.addEventListener('click', ev => {
  const t = ev.target && ev.target.closest ? ev.target : null;
  if(!t || !t.closest('.archtab') || strMode !== 'arch') return;
  const p = strOn[0] || '';
  if(t.closest('[data-arck]')){ archChkWinOpen(p); return; }
  if(t.closest('[data-arcq]')){ const c = archCands(archHome(ARCH.cache[p]), SESS, p); ARCH.msg = '';
    if(ARCH.creq && ARCH.creq.p === p && !ARCH.creq.busy) ARCH.creq = null;   // second press closes the preview
    else if(!ARCH.creq || ARCH.creq.p !== p) ARCH.creq = { p, sid: (c[0] || {}).sid || '', busy: false };
    const hadF = document.activeElement === t.closest('[data-arcq]');   // ⚠the repaint drops focus to <body> (08 kbHold)
    paintStruct();
    if(hadF) kbHold('.archtab [data-arcq]');
    return; }
  if(t.closest('[data-arcx]')){ ARCH.creq = null; paintStruct(); return; }
  if(t.closest('[data-arcgo]')) archChkSend();
});
document.addEventListener('change', ev => {
  const s = ev.target;
  if(!ARCH.creq || !s || !s.matches || !s.matches('.archtab select[data-arcs]')) return;
  ARCH.creq.sid = s.value; paintStruct();
});
