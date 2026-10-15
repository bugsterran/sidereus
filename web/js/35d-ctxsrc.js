// Context sources — what Claude Code loads besides the conversation (GET /api/session/context; paths, sizes, counts only).
//   Session work views only (`sess:` tids); fetched lazily per cwd, reused 60s like the server cache.
const CTXS = {};            // cwd -> {at, busy, d}
const CTXS_TTL = 60000;
let ctxsOpen = false;       // expanded state survives the 2.5s work-log repaint
// Remember which tab a work payload belongs to (agentBody only receives the payload).
function ctxsTag(d, t){
  if(d && typeof d === 'object' && t) d.__ctx = {cwd: t.cwd || '', tid: t.tid || ''};
  return d;
}
function ctxsGet(cwd, sid){
  const c = CTXS[cwd];
  if(c && (c.busy || Date.now() - c.at < CTXS_TTL)) return c;
  const n = CTXS[cwd] = {at: Date.now(), busy: true, d: c ? c.d : null};
  getJSON('/api/session/context?cwd=' + encodeURIComponent(cwd) + (sid ? '&sid=' + encodeURIComponent(sid) : ''))
    .then(j => { n.d = j; }, () => { n.d = n.d || {ok: false}; })
    .then(() => {
      n.busy = false; n.at = Date.now();
      const b = agBox(), top = b ? b.scrollTop : 0;
      const atEnd = b ? (b.scrollHeight - b.scrollTop - b.clientHeight < 40) : false;
      agentRepaint();
      // ⚠the context line can grow the log; a reader at the end must stay at the end
      const nb = agBox(); if(nb && !wtSplit) nb.scrollTop = atEnd ? nb.scrollHeight : top;
    });
  return n;
}
const CTXS_SCOPE = {user: 'user', 'user-rule': 'user rule', project: 'Project', local: 'local', rule: 'rule'};
function ctxsSc(s){ return T(CTXS_SCOPE[s] || s || '').toLowerCase(); }  // en: 'Project' is a table-header key elsewhere
function ctxsTok(n){ return n >= 1000 ? (n / 1000).toFixed(1) + 'K' : String(n || 0); }
function ctxsHtml(d){
  const x = d && d.__ctx;
  if(!x || !x.cwd || String(x.tid).indexOf('sess:') !== 0) return '';
  const c = ctxsGet(x.cwd, tidSid(x.tid)), j = c && c.d;
  if(!j || !j.ok) return '';
  const k = j.counts || {}, m = j.memory || {};
  const sum = TV({msg: 'Context ≈ {n} tokens', vars: {n: ctxsTok(j.tokens)}})
    + ' · ' + T('instructions') + ' ' + (k.instr || 0) + ' · ' + T('memory') + ' ' + (k.memory || 0)
    + ' · MCP ' + (k.mcp || 0) + ' · ' + T('hooks') + ' ' + (k.hooks || 0);
  const tok = n => TV({msg: '≈{n} tok', vars: {n: ctxsTok(n)}});
  const row = (a, b) => '<div class=ctxr><span>' + esc(a) + '</span><i>' + esc(b) + '</i></div>';
  const wrow = a => '<div class=ctxr><span class=ctxw>' + esc(a) + '</span></div>';
  // Paths: the directory part shrinks with «…», the file name always stays visible; full path in title.
  const prow = (p, b) => { p = String(p || ''); const i = p.lastIndexOf('/', p.length - 2) + 1;
    return '<div class=ctxr title="' + esc(p) + '"><span class=ctxp><b>' + esc(p.slice(0, i)) + '</b><em>' + esc(p.slice(i)) + '</em></span><i>' + esc(b) + '</i></div>'; };
  const sec = t => '<div class=ctxh>' + esc(t) + '</div>';
  let body = sec(T('Instruction files'));
  body += (j.instr || []).map(r => prow(r.path, sz(r.bytes) + ' · ' + tok(r.tokens) + ' · ' + ctxsSc(r.scope))).join('')
    || '<div class=ctxr><i>' + T('None') + '</i></div>';
  body += sec(T('Auto memory'))
    + (m.dir ? prow(m.index || m.dir, (m.bytes ? sz(m.bytes) + ' · ' + tok(m.tokens) + ' · ' : '') + U(m.files || 0, ' files'))
             : '<div class=ctxr><i>' + T('None') + '</i></div>');
  body += sec('MCP ' + U((j.mcp || []).length, '#'))
    + wrow((j.mcp || []).map(r => r.name + ' (' + ctxsSc(r.scope) + ')').join(', ') || T('None'));
  const sk = j.skills || {}, ag = j.agents || {};
  body += sec(T('Skills · agents'))
    + row(T('skills') + ' ' + ((sk.user || 0) + (sk.project || 0)) + ' · ' + T('agents') + ' ' + ((ag.user || 0) + (ag.project || 0)),
          TV({msg: 'user {n}/{m} · project {k}/{x}', vars: {n: (sk.user || 0), m: (ag.user || 0), k: (sk.project || 0), x: (ag.project || 0)}}));
  body += sec(T('Hooks') + ' ' + (k.hooks || 0))
    + wrow((j.hooks || []).map(h => h.event + ' ×' + h.n).join(', ') || T('None'));
  return '<details class=ctxs' + (ctxsOpen ? ' open' : '') + ' title="' + esc(T('Loaded with every request besides the conversation — tokens ≈ bytes/3.5')) + '">'
    + '<summary>' + esc(sum) + '</summary><div class=ctxb>' + body + '</div></details>';
}
document.addEventListener('toggle', e => {
  const t = e.target;
  if(t && t.classList && t.classList.contains('ctxs')) ctxsOpen = t.open;
}, true);
