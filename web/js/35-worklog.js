// ★Agent footsteps modal — shares the diff modal shell (same place, same close rules).
let agentData = null, agentTid = '', agentCwd = '';
// ★Files a subagent edited — the list comes from commands (_wrote_files), **the +/- body from git**.
//   Paths git doesn't know (build output · temp files) are naturally filtered: candidates are intersected with git's change list.
const agRepoDiff = {};         // repo → {st:'load'|'ok'|'err', files:[…], msg}
const AG_EXT_LANG = {java:'java',kt:'java',gradle:'java',cs:'java',scala:'java',sql:'sql',
  js:'js',mjs:'js',cjs:'js',jsx:'js',ts:'js',tsx:'js',py:'py',sh:'sh',bash:'sh',zsh:'sh',
  go:'go',rs:'go',rb:'rb',c:'c',h:'c',cc:'c',cpp:'c',cxx:'c',hpp:'c',hh:'c',hxx:'c',inl:'c',xml:'xml',html:'xml',jsp:'xml',
  php:'java',proto:'java',graphql:'py',graphqls:'py',gql:'py',vue:'js',svelte:'js',   // same picks as strPairLang (81-structure-panel)
  json:'json',yaml:'yaml',yml:'yaml',css:'css',properties:'props',g4:'g4',
  md:'none',txt:'none',log:'none',patch:'none',diff:'none',csv:'none',rst:'none',adoc:'none'};
const agLang = pth => AG_EXT_LANG[(String(pth).split('.').pop()||'').toLowerCase()] || '';
function agLoadRepo(repo){
  if(!repo || agRepoDiff[repo]) return;
  agRepoDiff[repo] = {st:'load', files:[]};
  getJSON('/api/git/diff?cwd='+encodeURIComponent(repo)+'&scope=all')
    .then(j=>{ agRepoDiff[repo] = j && j.ok
        ? {st:'ok', files: splitDiff(j.diff||'')}
        : {st:'err', files:[], msg:(j&&j.msg) ? TV(j) : T('Could not fetch')};
      agentRepaint(); })
    .catch(()=>{ agRepoDiff[repo] = {st:'err', files:[], msg:T('Could not fetch')}; agentRepaint(); });
}
let agPromptOpen = false;      // instruction expanded state — survives modal redraws
// ★Received-instruction height — set by a human dragging the bottom handle (2026-08-31).
//   ⚠It must be an inline style: the modal replaces innerHTML every 2.5s, so without the value outside the DOM
//   the dragged height reverts to the default on every refresh (a trap already hit with width resizing).
const AGP_MIN = 90, AGP_MAX = 900, AGP_DEF = 300;
let agPH = (() => { try { const v = +UIS.agPH;
                          return v ? Math.min(AGP_MAX, Math.max(AGP_MIN, v)) : AGP_DEF; }
                    catch(e){ return AGP_DEF; } })();
let agTFil = 'all';              // tree filter: all | main | test
let agTreeOpen = true;           // tree expanded — survives refreshes
// ★Edited file tree — see files scattered across the console at a glance. Came from the report that tests and main code
//   were mixed and indistinguishable (2026-08-31). Decided **by path** only (no guessing from contents).
const AG_TEST = /(^|\/)(test|tests|__tests__)(\/|$)|(Test|Tests|Spec|IT)\.[A-Za-z0-9]+$|[._-](test|spec)\.[A-Za-z0-9]+$/i;
function agFileList(d){
  const seen = new Map();
  for(const s of (d.steps||[])) for(const w of (s.wrote||[])){
    if(!w.cwd) continue;
    let rel = w.path;
    if(rel.startsWith(w.cwd + '/')) rel = rel.slice(w.cwd.length + 1);
    if(rel.startsWith('/')) continue;                 // outside the repo
    // ⚠Load here, not only in agWroteBlock: the header count (wkSum) read 0 until a «Changes» block drew. Once per cwd.
    agLoadRepo(w.cwd);
    const c = agRepoDiff[w.cwd];
    if(!c || c.st !== 'ok') continue;
    const f = (c.files||[]).find(x => x.path === rel);
    if(!f) continue;                                  // a change git doesn't know
    seen.set(w.cwd + '|' + rel, {repo: w.cwd, rel: rel, f: f, test: AG_TEST.test(rel)});
  }
  return [...seen.values()];
}
// Fold paths into a tree. Directories with a single child **merge into one line** (a/b/c) —
// otherwise src > main > java > com > example becomes five empty steps.
function agTree(items){
  const root = {dirs: new Map(), files: []};
  for(const it of items){
    const parts = it.rel.split('/');
    const name = parts.pop();
    let n = root;
    for(const seg of parts){
      if(!n.dirs.has(seg)) n.dirs.set(seg, {dirs: new Map(), files: []});
      n = n.dirs.get(seg);
    }
    n.files.push(Object.assign({name: name}, it));
  }
  const squash = (n, label) => {
    while(n.dirs.size === 1 && n.files.length === 0){
      const [k, v] = [...n.dirs.entries()][0];
      label = label ? label + '/' + k : k;
      n = v;
    }
    return {label: label, dirs: [...n.dirs.entries()].map(([k, v]) => squash(v, k)),
            files: n.files};
  };
  return squash(root, '');
}
function agTreeHtml(node, depth){
  let out = '';
  if(node.label){
    out += '<div class=agtd style="padding-left:'+(depth*14)+'px">'+dicon(false)+esc(node.label)+'</div>';
  }
  for(const d2 of node.dirs) out += agTreeHtml(d2, depth + (node.label ? 1 : 0));
  for(const f of node.files.sort((a,b) => a.name.localeCompare(b.name))){
    out += '<div class="agtf'+(f.test?' agtt':'')+'" style="padding-left:'+((depth+(node.label?1:0))*14)+'px" '
      + 'data-go="'+esc(f.repo + '|' + f.rel)+'" title="'+esc(f.rel)+'">'
      + '<span class=agtn>'+ficon(f.name)+esc(f.name)+'</span><span class=agts>'
      + (f.f.del?'<b class=edmn>-'+f.f.del+'</b> ':'') + (f.f.add?'<b class=edpl>+'+f.f.add+'</b>':'')
      + '</span></div>';
  }
  return out;
}
const agWroteOpen = new Set();   // opened **by a human** — survives refreshes
const agWroteShut = new Set();   // closed **by a human** — beats default expansion (otherwise it reopens after closing)
let agentFirst = false;        // first open? — the first time it scrolls **to the bottom** (console: latest at the bottom)
const agEditOpen = new Set();  // edit blocks opened **by a human** — survives refreshes
const agEditShut = new Set();  // edit blocks closed **by a human** — beats default expansion (otherwise it reopens after closing)
const agEditWas = new Map();   // open state decided by the previous render — if the DOM differs from this, «a human changed it»
// ★Only human choices are remembered. Reading the whole DOM and recording every `[open]` as 'opened by a human'
//   turns **default expansions too** into human choices, so old spots stay expanded even after cap/length rules change
//   (wroteBlock blocks bulk DOM recording at :13574 for the same reason).
function agEditHarvest(box){
  if(!box) return;
  box.querySelectorAll('details.aged[data-ek]').forEach(x => {
    const k = x.getAttribute('data-ek'), now = x.hasAttribute('open');
    if(agEditWas.get(k) === now) return;                        // as the render decided — untouched
    if(now){ agEditShut.delete(k); agEditOpen.add(k); }
    else { agEditOpen.delete(k); agEditShut.add(k); }
  });
}
// ★Times are localized **by the browser** — slicing a UTC string on the server is 9 hours off
//   (measured 2026-08-27: 8 AM showed as 22:58). The server gives the ISO original only and makes no decision.
function hhmmss(iso){
  const d = new Date(iso);
  if(isNaN(d)) return String(iso||'').slice(11,19);
  return hhmm(d, {sec: true});
}
// External CLI session panel — only hook metadata exists (no transcript is read), so show exactly that.
function extBody(d){
  const tm = t => t ? new Date(t * 1000).toLocaleTimeString(LANG === 'en' ? 'en-GB' : 'ko-KR', {hour12:false}) : '—';
  const kv = (k, v) => '<tr><th>' + esc(T(k)) + '</th><td>' + v + '</td></tr>';
  const evs = (d.events || []).slice().reverse();
  return '<div class=extw><table class=extkv>'
    + kv('Platform', aiLogo(d.plat) + ' ' + esc(d.platform || d.plat || ''))
    + kv('Model', esc(d.model || T('Unknown')))
    + kv('Path', esc(d.cwd || '—'))
    + kv('Status', esc(stateLbl(d.state) || T(d.state || '')) + (d.blocked ? ' · ' + esc(T('Waiting on notification')) : ''))
    + kv('Last tool', esc(d.tool || '—'))
    + kv('First seen', esc(tm(d.firstSeen)) + ' · ' + esc(agoAt(d.firstSeen)))
    + kv('Last seen', esc(tm(d.lastSeen)) + ' · ' + esc(agoAt(d.lastSeen)))
    + '</table><div class=extnt>' + esc(T('Only events sent by hooks are shown — conversation text and tool input are not read')) + '</div>'
    + '<table class=extev><tr><th>' + esc(T('Time')) + '</th><th>' + esc(T('Event')) + '</th><th>' + esc(T('Tool')) + '</th></tr>'
    + (evs.length ? evs.map(e => '<tr><td>' + esc(tm(e.t)) + '</td><td>' + esc(e.e) + '</td><td>' + esc(e.tool || '') + '</td></tr>').join('')
                  : '<tr><td colspan=3>' + esc(T('No events recorded')) + '</td></tr>')
    + '</table></div>';
}
function agentBody(d){
  if(!d) return '<div class=t>'+T('Loading…')+'</div>';
  if(!d.ok) return '<div class=t>'+esc(d.msg ? TV(d) : T('Could not fetch'))+'</div>';
  if(d.ext) return extBody(d);
  const dur = (d.first && d.last)
    ? Math.max(0, Math.round((Date.parse(d.last)-Date.parse(d.first))/60000)) : null;
  // ★The header states how many files were edited — at 0 the screen answers "why is there no diff" first.
  // ★Counting only `wrote` (Bash-edit candidates) **misses Edit/Write tool calls** (measured 2026-09-01: the screen
  //   showed Write +81 · Edit -2 +27 while the header said «Read only — no files changed»).
  //   This viewer collects the two paths separately: auto mode via Bash (→wrote), otherwise Edit/Write (→edit/edits).
  // ⚠editCut = an edit step whose bodies the server dropped (steps._cap_edit_bodies); it still edited a file.
  const nWrote = (d.steps||[]).filter(s => s.wrote || s.edit || s.edits || s.editCut).length;
  // ★diffs are **cumulative** — edit the same file three times and three steps get the same diff. So the only spot
  //   expanded by default is that file's **last edit step**. Earlier steps stay as one folded line (clickable).
  //   This solves both "looks natural" and "thousands of lines re-rendered every 2.5s".
  const lastAt = new Map();
  (d.steps||[]).forEach((s, i) => {
    s.__i = i;
    for(const w of (s.wrote||[])){
      if(!w.cwd) continue;
      let rel = w.path;
      if(rel.startsWith(w.cwd + '/')) rel = rel.slice(w.cwd.length + 1);
      lastAt.set(w.cwd + '|' + rel, i);
    }
  });
  const head = [TV({msg: d.cutSteps ? '{n} tool calls (first {m} omitted)' : '{n} tool calls', vars: {n: d.steps.length, m: d.cutSteps}}),
                nWrote ? TV({msg: nWrote === 1 ? '{n} editing step' : '{n} editing steps', vars: {n: nWrote}}) : T('Read only — no files changed')];
  // server drops edit bodies of older steps past its character budget (steps.AGENT_EDIT_BUDGET)
  if(d.cutEdits) head.push(TV({msg: 'edit bodies of {n} older steps cut', vars: {n: (+d.cutEdits)}}));
  if(dur !== null) head.push(U(dur,'m'));
  if(d.depth > 1) head.push(TV({msg: 'depth {n}', vars: {n: d.depth}}));
  if(d.size) head.push(sz(d.size));

  // ★Flows chronologically like a console.
  //   A table's fixed columns made the eye shuttle, and utterances and tools were disjoint. Merged into one stream.
  const feed = [];
  (d.says||[]).forEach(x => feed.push({t:x.t, kind:'say', text:x.text}));
  (d.steps||[]).forEach(x => feed.push({t:x.t, kind:'run', s:x}));
  feed.sort((a,b) => (a.t||'').localeCompare(b.t||''));   // ISO, so string sort suffices

  // ★**Cap on the number** of default expansions — bounds re-render cost. Edit blocks (editBlock) and cumulative git diffs
  //   (wroteBlock) — **both paths count against this one** — counted separately, 80 would expand on one screen.
  // `cx` = per-render state shared by the edit and wrote blocks: the default-expansion counter and each file's last edit step.
  const cx = {autoN: 0, lastAt};
  agEditWas.clear();                   // refill with the open state decided by this render
  const body = feed.map(f => agFeedLine(cx, f)).join('');
  return agBodyHtml(d, head, body);
}
// ★Edits are shown as +/- (2026-08-27). An Edit is "this chunk into that chunk", so there is no line
//   correspondence to begin with — so **only common leading/trailing lines are stripped** and the middle is shown as -/+. No LCS,
//   for the same reason: inventing a correspondence that doesn't exist is plausible but false. Stripped common lines stay gray.
function agEditRows(oldT, newT){
    const A = String(oldT||'').split(NL), B = String(newT||'').split(NL);
    let p = 0;
    while(p < A.length && p < B.length && A[p] === B[p]) p++;
    let q = 0;
    while(q < A.length - p && q < B.length - p && A[A.length-1-q] === B[B.length-1-q]) q++;
    // ★Common lines are shown **in full** (2026-08-27). An Edit's old/new is one chunk, so
    //   trimming the ends loses the context of where it was edited. Only a total cap instead.
    const rows = [];
    const ctx = t => rows.push({m:' ', t:t, c:''});
    A.slice(0, p).forEach(ctx);                                     // all common leading lines
    A.slice(p, A.length - q).forEach(t => rows.push({m:'-', t:t, c:'dm'}));
    B.slice(p, B.length - q).forEach(t => rows.push({m:'+', t:t, c:'dp'}));
    A.slice(A.length - q).forEach(ctx);                             // all common trailing lines
    return rows.length > 600 ? rows.slice(0, 600) : rows;
}
function agEditBlock(cx, e, key, lang){
    if(!e) return '';
    const rows = agEditRows(e.old, e.new);
    const del = rows.filter(r=>r.m==='-').length, add = rows.filter(r=>r.m==='+').length;
    // ★Drawn in **the same table** as git diff (the shapes used to differ). Line-number and marker columns match.
    //   ⚠Numbers are **relative to this edit chunk** — Edit gives only old/new chunks, not their position in the file.
    //     Pretending they are file line numbers would be false, so the tooltip says so.
    let ln0 = 0, rn0 = 0;
    const body = '<table class="sbs uni"><colgroup><col class=cg><col class=cm2><col></colgroup>'
      + rows.map(r => {
          let cls = '', no = '';
          if(r.m === '+'){ cls = 'xa'; no = ++rn0; }
          else if(r.m === '-'){ cls = 'xd'; no = ++ln0; }
          else { ++ln0; no = ++rn0; }
          return '<tr class="'+cls+'"><td class=xn>'+no+'</td><td class=xk>'+r.m+'</td>'
            + '<td class=xt>'+(hl(r.t, lang) || ' ')+'</td></tr>';
        }).join('') + '</table>';
    // ★**Expanded by default** (new changes should be readable without a click). There are two paths that draw edit blocks, but
    //   the default-expansion rule was only in wroteBlock, so every spot edited via Edit/Write was collapsed.
    //   ⚠wroteBlock's "only the file's last edit spot" condition exists **because git diff is cumulative**.
    //     Edit's old/new is the change that step actually made, not a duplicate ⇒ that condition is not applied.
    //   Only the remaining two conditions follow wroteBlock as-is: length cap + count cap (shared autoN).
    const big = rows.length > 300, cap = cx.autoN >= 40;
    const auto = !big && !cap;
    if(auto) cx.autoN++;
    const op = agEditShut.has(key) ? false : (agEditOpen.has(key) || auto);
    agEditWas.set(key, op);
    // ★The key is **the edit's identity** (step time · file path · index within the step). It used to be the render index, but
    //   after switching session/agent the same index points to a different file, so fold state moves onto the wrong block
    //   (measured 2026-08-27 · same reason wroteBlock was fixed at :13228).
    return '<details class=aged'+(op?' open':'')+' data-ek="'+esc(key)+'">'
      + '<summary title="'+esc(T('Line numbers are local to this edit chunk — Edit does not report file offsets'))+'">'
      + T('Changes', 'diff')+'<span class=agesz>'
      + (del?'<b class=edmn>-'+del+'</b> ':'') + (add?'<b class=edpl>+'+add+'</b>':'')
      + '</span>' + (e.cut ? '<span class=agesz>'+T('partial', 'only')+'</span>' : '')
      + (auto ? '' : '<span class=agesz>'+(big ? T('collapsed — too long') : T('over the 40 auto-expand limit'))+'</span>')
      + '</summary>'
      + '<div class="edb agwd">'+body+'</div></details>';
}
// ★+/- of files edited via Bash attach **at that step's spot** (in the live console view).
//   ⚠The body is git's **current cumulative change** — not the difference that single step made (if the same file was
//   edited several times, each step shows the same diff). Anything more can't honestly be known, so the summary says so.
function agWroteBlock(cx, list, stepIdx){
    let out = '';
    (list||[]).forEach((w, j) => {
      if(!w.cwd) return;
      agLoadRepo(w.cwd);
      let rel = w.path;
      if(rel.startsWith(w.cwd + '/')) rel = rel.slice(w.cwd.length + 1);
      // ★Absolute paths outside the repo (temp scratch etc.) are unknown to git — say so.
      //   "no changes" would read as committed, which is false.
      if(rel.startsWith('/')){
        out += '<div class=cwload>'+esc(rel)+' — '+T('outside the repo, so git does not track it')+'</div>';
        return;
      }
      const c = agRepoDiff[w.cwd];
      if(!c || c.st === 'load'){ out += '<div class=cwload>'+esc(rel)+' — '+T('checking changes…')+'</div>'; return; }
      // ★Failures are **stated**. It used to silently draw nothing and looked "not working" (2026-08-31).
      if(c.st === 'err'){ out += '<div class="cwload cwerr">'+esc(rel)+' — '+T('could not read git')+': '+esc(T(c.msg||''))+'</div>'; return; }
      const f = (c.files||[]).find(x => x.path === rel);
      if(!f){                              // something git doesn't know as a change — state the reason
        out += '<div class=cwload>'+esc(rel)+' — '+T('no change in git (already committed/pushed, or reverted)')+'</div>';
        return;
      }
      // ★The key is **the file identity** (it used to be the render-order index `si.j`). After switching session/agent
      //   the same index points to **a different file**, so manual fold state moves onto the wrong block
      //   (measured 2026-08-27: open keys `26.0`/`28.0` survived the switch by construction).
      const key = encodeURIComponent(w.cwd) + '|' + encodeURIComponent(rel);
      // Default expansion: this file's last edit spot · diff not too long · within the cap
      const isLast = cx.lastAt.get(w.cwd + '|' + rel) === stepIdx;
      const nLines = (f.add||0) + (f.del||0);
      // Measured (2026-08-31): 15 expanded, 373 rows, re-render 9ms — much cheaper than feared. Cap set at 40.
      const cap = cx.autoN >= 40, big = nLines > 300;
      const auto = isLast && !f.isBin && !big && !cap;
      if(auto) cx.autoN++;
      const op = agWroteShut.has(key) ? false : (agWroteOpen.has(key) || auto);
      out += '<details class=aged'+(op?' open':'')+' data-wk="'+esc(key)+'">'
        + '<summary><span class=agwp>'+esc(rel)+'</span><span class=agesz>'
        + (f.del?'<b class=edmn>-'+f.del+'</b> ':'') + (f.add?'<b class=edpl>+'+f.add+'</b>':'')
        + (f.isBin?' '+T('binary'):'')
        + ' ' + (isLast ? (auto ? T('current cumulative')
                          : (big ? T('current cumulative · collapsed — too long') : T('current cumulative · over the 40 auto-expand limit')))
                  : T('current cumulative · expanded at the last edit')) + '</span></summary>'
        + (op ? '<div class=agwd>' + (f.isBin ? '<div class=cwload>'+T('Binary file — no line-by-line diff')+'</div>'
                                              : diffHtml(f.body, agLang(rel))) + '</div>' : '')
        + '</details>';
    });
    return out;
}
// One console line: an utterance, or a tool call with its result and edit/diff blocks.
function agFeedLine(cx, f){
    if(f.kind === 'say')
      return '<div class=cline><span class=cbul>●</span><div class="bd cbsay">'+md(f.text)+'</div></div>';
    const s = f.s;
    const isEd = !!(s.edit || s.edits || s.wrote);
    let ex = '';
    // Open key of an edit block — step time + file path (target name if absent). Why not the render index:
    // see the editBlock comment. MultiEdit appends the index within the step.
    const epath = (s.edit && s.edit.path) || (s.wrote && s.wrote[0] && s.wrote[0].path) || s.targ || '';
    const ekey = (s.t || '') + '|' + epath + '|';
    if(s.edit) ex = agEditBlock(cx, s.edit, ekey + '0', s.elang);
    else if(s.edits) ex = s.edits.map((x, j) => agEditBlock(cx, {old:x.old, new:x.new}, ekey + j, s.elang)).join('');
    else if(s.wrote) ex = agWroteBlock(cx, s.wrote, s.__i);
    // ★Same shape as the Claude Code console: `Tool(actual args)` with `⎿ result` below.
    //   Args are the command/path itself, not the description (user-specified 2026-08-27).
    const arg = s.arg || s.targ || '';
    const r = s.res;
    // ★Only results judged to be code are colored (the server decides by command) — otherwise left as-is.
    const res = r
      ? '<div class="cres'+(r.err?' cerr':'')+(r.code?' ccode':'')+'">'
        + r.lines.map((l,i) => '<div class=crl><span class=crm>'+(i?'':'⎿')+'</span>'
            + '<span class=crt>'+(r.code && !r.err ? (hl(l, r.lang) || ' ') : esc(l))+'</span></div>').join('')
        + (r.more ? '<div class=crl><span class=crm></span><span class="crt cmore">… +'+U(r.more,' lines')+'</span></div>' : '')
        + '</div>'
      : '';
    return '<div class="cline crun'+(isEd?' ced':'')+'">'
      + '<span class=ctm>'+esc(hhmmss(s.t))+'</span>'
      + '<span class=ccall><span class=cnm>'+esc(s.tool)+'</span>'
      + '<span class=cpar>(</span><span class=carg title="'+esc(arg)+'">'+esc(arg)+'</span><span class=cpar>)</span></span>'
      + '</div>' + res + (ex ? '<div class=cex>'+ex+'</div>' : '');
}
// Pinned received instruction + edited-file tree + header line + console.
function agBodyHtml(d, head, body){
  // ★Received instruction is **pinned at the top** (2026-08-31). It used to sit below the console, but the modal
  //   scrolls to the bottom on open, pushing the instruction off-screen so "what was it asked to do" couldn't be seen.
  //   Being sticky it stays visible collapsed (one line), and expands in place to read.
  // ★Pinning the edited-file list to the header was removed (2026-08-31) — pinned expanded, a 42-item list
  //   took half the screen and followed the scroll; the wanted spot was **that step's spot in the console** all along.
  //   Repo diffs are used by wroteBlock below (same cache).
  // ★Edited file tree — folded per repo. **Not pinned** (it was sticky once and followed
  //   the scroll, so removed). Clicking a file takes you to its diff spot in the console.
  const items = agFileList(d);
  const nT = items.filter(x => x.test).length, nM = items.length - nT;
  const shown = items.filter(x => agTFil === 'all' || (agTFil === 'test' ? x.test : !x.test));
  const byRepo = new Map();
  for(const it of shown){ if(!byRepo.has(it.repo)) byRepo.set(it.repo, []); byRepo.get(it.repo).push(it); }
  const chip = (k, lab, n) => '<span class="agtc'+(agTFil===k?' on':'')+'" data-fil="'+k+'">'+lab+' '+n+'</span>';
  const tree = items.length
    ? '<details class=agtr'+(agTreeOpen?' open':'')+'><summary>'+T('Files changed')+' '+U(items.length,'#')
      + '<span class=agtsum>'+T('Source')+' '+nM+' · '+T('Tests')+' '+nT+'</span></summary>'
      + '<div class=agtb><div class=agtf2>'
      + chip('all',T('All'),items.length) + chip('main',T('Source'),nM) + chip('test',T('Tests'),nT) + '</div>'
      + [...byRepo.entries()].map(([rp, list]) =>
          '<div class=agtrp>'+esc(rp.split('/').pop())+'</div>' + agTreeHtml(agTree(list), 0)).join('')
      + (shown.length ? '' : '<div class=cwload>'+T('No files match this filter')+'</div>')
      + '</div></details>'
    : '';

  // The only pinned thing is **the one-line received instruction** — the modal opens at the bottom, so this must always show.
  return '<div class=aghd>'
    + (d.prompt
        ? '<details class=agp'+(agPromptOpen?' open':'')+'><summary>'+TV({msg: 'Instruction received ({n} chars)', vars: {n: d.prompt.length}})+'</summary>'
          + '<div class="bd agpb" style="max-height:'+agPH+'px">'+md(d.prompt)+'</div>'
          + '<div class=agpg title="'+esc(T('Drag to resize · double-click to reset', 'height'))+'"></div></details>'
        : '')
    + '</div>'
    + ctxsHtml(d)
    + tree
    + '<div class=t>'+esc(head.join(' · '))+'</div>'
    + '<div class=console>'+ (body || '<div class=cline>'+T('No records yet')+'</div>') +'</div>';
}
