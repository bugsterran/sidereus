// ★Invite only — members are never edited directly. The roster is the room's record, and who joined when
//   is verdict evidence for reviews; changing it silently from the screen would contaminate that evidence.
//   Invites are a discovery mechanism, so safe. The invitee also sees it in their inbox.
// ★diff coloring — kept separate from the code highlighter. diff meaning splits **per line** (+/-/@@),
//   and mixing it with token coloring makes both unreadable. Only row color.
// ★Code inside diffs gets **the same coloring as code blocks**.
//   IntelliJ's diff also lays only row backgrounds over syntax coloring. Row background (add/remove) and token color are on different layers,
//   so they don't mix — background on tr/td, color on spans inside.
// ★Line numbers on the left. A unified diff must also be a table to carry numbers (it was pre before, so it couldn't).
// ⚠Prose files (agLang 'none': md/txt/rst/log…) skip hl() — its shape rules painted random words (Capitalized → type, word( → method, # → comment).
const proseCls = s => /^\s*(```|~~~)/.test(s) ? 'cc' : (/^#{1,6}\s/.test(s) ? 'ck' : '');   // code fence · heading
function dhl(src, lang){
  if(lang !== 'none') return hl(src, lang);
  const s = String(src), lc = proseCls(s);
  if(lc) return '<span class='+lc+'>'+esc(s)+'</span>';
  return s.split(/(`[^`\n]+`)/).map((p, i) => i % 2 ? '<span class=cs>'+esc(p)+'</span>' : esc(p)).join('');   // inline code
}
function diffHtml(src, lang, rvp){   // rvp = file path → review-comment gutter (88e), only in a review popup
  if(!String(src == null ? '' : src).trim()) return '<div class=t>'+T('No changes to show')+'</div>';
  const lines = String(src).replace(/\n$/, '').split(NL);   // ⚠a trailing newline is not a blank context line
  let ln = 0, rn = 0;
  const rows = lines.map(l => {
    if(/^@@/.test(l)){
      const m = l.match(/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
      if(m){ ln = parseInt(m[1],10) - 1; rn = parseInt(m[2],10) - 1; }
      return '<tr class=xhk><td colspan=3>'+esc(l)+'</td></tr>';
    }
    if(/^(diff --git |index |--- |\+\+\+ |new file|deleted file|similarity|rename |old mode|new mode|Binary )/.test(l))
      return '<tr class=xfl><td colspan=3>'+esc(l)+'</td></tr>';
    // ★Numbers in **one column only** (2026-08-26). Two columns (before/after) blurred where to look.
    //   Added/context use the new file's number, removed the old file's — the number of the side where the line actually exists.
    //   And `+`/`-` get their own column. Color alone fails in B/W copies and for color-weak users.
    let cls = '', no = '', mk = ' ', body = l;
    if(/^\+/.test(l)){ cls='xa'; body=l.slice(1); no = ++rn; mk='+'; }
    else if(/^-/.test(l)){ cls='xd'; body=l.slice(1); no = ++ln; mk='-'; }
    else { body = l.startsWith(' ') ? l.slice(1) : l; ++ln; no = ++rn; }
    return '<tr class="'+cls+'"><td class=xn>'+no+(cls === 'xd' ? '' : rvnGut(rvp, no))+'</td><td class=xk>'+mk+'</td>'
      + '<td class=xt>'+(dhl(body, lang) || ' ')+'</td></tr>';
  });
  return '<table class="sbs uni"'+rvnAttr(rvp)+'><colgroup><col class=cg><col class=cm2><col></colgroup>'
    + rows.join('') + '</table>';
}
// ★Split per file — no new server call (the full diff is already here). Cutting at `diff --git` boundaries
//   and counting path/+/- only costs nothing.
// C-quoted git path (`"b/a\"b"`, octal UTF-8 bytes) -> plain string; unquoted input is returned as-is.
function gitUnq(s){
  if(s.length < 2 || s[0] !== '"' || s[s.length-1] !== '"') return s;
  const by = [], enc = new TextEncoder(), E = {n:10, t:9, r:13, a:7, b:8, f:12, v:11}, t = s.slice(1, -1);
  for(let i = 0; i < t.length; i++){
    if(t[i] !== '\\'){ const cp = t.codePointAt(i); if(cp > 0xffff) i++; by.push(...enc.encode(String.fromCodePoint(cp))); continue; }
    const o = t.slice(i+1, i+4);
    if(/^[0-7]{3}$/.test(o)){ by.push(parseInt(o, 8)); i += 3; continue; }
    const c = t[++i] || '\\';
    by.push(E[c] != null ? E[c] : c.charCodeAt(0));
  }
  return new TextDecoder().decode(new Uint8Array(by));
}
// New-side path from one file's header lines (before the first @@).
// ⚠`---`/`+++` carry a trailing TAB when the path has a space; a pure rename or a binary has no `+++` at all.
function dfHdrPath(hdr){
  let m = hdr.match(/^(?:rename|copy) to (.+)$/m);
  if(m) return gitUnq(m[1]);
  m = hdr.match(/^\+\+\+ (.+?)\t?$/m);
  if(m && m[1] !== '/dev/null') return gitUnq(m[1]).replace(/^b\//, '');
  m = hdr.match(/^--- (.+?)\t?$/m);
  if(m && m[1] !== '/dev/null') return gitUnq(m[1]).replace(/^a\//, '');
  const r = (hdr.match(/^diff --git (.+)$/m) || [])[1] || '';
  const q = r.match(/ ("(?:[^"\\]|\\.)*")$/);
  if(q) return gitUnq(q[1]).replace(/^b\//, '');
  const n = (r.length - 5) / 2;                    // `a/P b/P` — same path on both sides (no rename line)
  if(n > 0 && n === Math.floor(n) && r.slice(2, 2+n) === r.slice(5+n)) return r.slice(2, 2+n);
  return '';
}
function splitDiff(src){
  const out = [];
  const parts = String(src).split(/^(?=diff --git )/m);
  for(let p of parts){
    if(!p.trim()) continue;
    p = p.replace(/\n$/, '');   // ⚠the newline before the next `diff --git` would render as a phantom numbered row
    const lines = p.split(NL);
    let h = lines.findIndex(l => /^@@/.test(l));
    if(h < 0) h = lines.length;
    // ⚠Header and counts split at the first @@ — a removed `-- x` line reads as `--- x` and is not a header.
    const path = dfHdrPath(lines.slice(0, h).join(NL)) || T('(unknown)');
    const hunk = lines.slice(h);
    const add = hunk.filter(l => /^\+/.test(l)).length;
    const del = hunk.filter(l => /^-/.test(l)).length;
    const isNew = /^new file mode/m.test(p), isGone = /^deleted file mode/m.test(p);
    // ★Binary — git gives no line diff (`Binary files ... differ`).
    //   Measured 2026-08-26: a repo with only one `.jar` changed **showed "no changes"**. Saying what exists is absent
    //   is worse, so the file stays in the list without lines, marked as binary.
    const isBin = /^Binary files .* differ$/m.test(p) || /^GIT binary patch$/m.test(p);
    out.push({path, add, del, body: p, isNew, isGone, isBin});
  }
  return out;
}
let diffPick = -1;       // -1 = all
// ★Expand full file — tens of KB per file, too much for the default response. Only clicked files are fetched and cached.
const fullCache = {};    // "repo\0path" → response
let fullOn = false;      // whether the current file is viewed with full context
// ★Side by side by default — unified is hard to compare (2026-08-26). A diff is for "what changed into
//   what", and stacking vertically makes the eye shuttle between two spots. Unified remains a toggle.
let dfHistOpen = lsGet('sidereus.dfhist', '0') === '1';   // commit history above the diff: folded by default (dozens of rows pushed the diff down)
let sbsOn = true;        // side-by-side view (left/right like IntelliJ diff) — default
let diffScope = 'all';   // all=unpushed+worktree · commit=committed unpushed only · work=uncommitted only

// ★Unified diff → **aligned left/right rows**. IntelliJ diff viewer style (2026-08-26).
//   Consecutive `-` runs and consecutive `+` runs are **paired** on the same row (= modified lines). Leftovers fill one side
//   and leave the other as a filler cell — so context above and below stays aligned.
//   Line numbers start from `@@ -a,b +c,d @@` and are counted separately per side.
function sbsRows(src){
  const rows = [];
  let ln = 0, rn = 0;
  if(!String(src == null ? '' : src).trim()) return rows;
  const lines = String(src).replace(/\n$/, '').split(NL);
  let i = 0;
  const flush = (dels, adds) => {
    const n = Math.max(dels.length, adds.length);
    for(let k = 0; k < n; k++){
      const d = dels[k], a = adds[k];
      rows.push({
        ln: d !== undefined ? ++ln : null, lt: d, lc: d !== undefined ? (a !== undefined ? 'xm' : 'xd') : 'xe',
        rn: a !== undefined ? ++rn : null, rt: a, rc: a !== undefined ? (d !== undefined ? 'xm' : 'xa') : 'xe'
      });
    }
  };
  while(i < lines.length){
    const l = lines[i];
    if(/^@@/.test(l)){
      const m = l.match(/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
      if(m){ ln = parseInt(m[1],10) - 1; rn = parseInt(m[2],10) - 1; }
      rows.push({hunk: l});
      i++; continue;
    }
    if(/^(diff --git |index |--- |\+\+\+ |new file|deleted file|similarity|rename |old mode|new mode|Binary )/.test(l)){
      i++; continue;                                  // file headers are dropped from the side-by-side view (the path is already above)
    }
    if(/^-/.test(l) || /^\+/.test(l)){
      const dels = [], adds = [];
      while(i < lines.length && /^-/.test(lines[i]) && !/^---/.test(lines[i])) dels.push(lines[i++].slice(1));
      while(i < lines.length && /^\+/.test(lines[i]) && !/^\+\+\+/.test(lines[i])) adds.push(lines[i++].slice(1));
      if(!dels.length && !adds.length){ i++; continue; }
      flush(dels, adds);
      continue;
    }
    // context (leading space) · empty line
    const t = l.startsWith(' ') ? l.slice(1) : l;
    rows.push({ln: ++ln, lt: t, lc: '', rn: ++rn, rt: t, rc: ''});
    i++;
  }
  return rows;
}
// ★Changed **characters** are marked (otherwise what changed is hard to tell).
//   A shared background on paired lines says only that they differ, not where.
//   Common prefix/suffix are trimmed and only the remaining middle is highlighted — no LCS:
//   real edits are usually "one value changed", which this catches, at zero cost.
//   A line different at both ends gets fully highlighted, which is true, so not a lie.
function inlineMark(a, b, lang){
  a = a == null ? '' : String(a);
  b = b == null ? '' : String(b);
  let p = 0;
  while(p < a.length && p < b.length && a[p] === b[p]) p++;
  let q = 0;
  while(q < a.length - p && q < b.length - p && a[a.length-1-q] === b[b.length-1-q]) q++;
  const wrap = (t, cls) => {
    const pre = t.slice(0, p), mid = t.slice(p, t.length - q), suf = t.slice(t.length - q);
    const lc = lang === 'none' && proseCls(t);   // whole-line prose class, so a split heading stays one colour
    if(lc) return '<span class='+lc+'>'+esc(pre)+(mid ? '<span class="'+cls+'">'+esc(mid)+'</span>' : '')+esc(suf)+'</span>';
    return dhl(pre, lang) + (mid ? '<span class="'+cls+'">'+dhl(mid, lang)+'</span>' : '') + dhl(suf, lang);
  };
  return { l: wrap(a, 'wd'), r: wrap(b, 'wa') };
}

function sbsHtml(src, lang, rvp){
  const rows = sbsRows(src);
  if(!rows.length) return '<div class=t>'+T('No changes to show')+'</div>';
  const cell = (no, html, cls, g) =>
    '<td class="xn">'+(no==null?'':no)+(g||'')+'</td>'
    + '<td class="xt '+cls+'">'+(html || ' ')+'</td>';
  return '<table class=sbs'+rvnAttr(rvp)+'><colgroup><col class=cg><col><col class=cg><col></colgroup>' + rows.map(r => {
    if(r.hunk) return '<tr class=xhk><td colspan=4>'+esc(r.hunk)+'</td></tr>';
    // only paired (modified) lines per character — add-only/remove-only lines are entirely the change, so not needed
    const pair = r.lc === 'xm' && r.rc === 'xm';
    const m = pair ? inlineMark(r.lt, r.rt, lang) : null;
    const lh = m ? m.l : (r.lt == null ? '' : dhl(r.lt, lang));
    const rh = m ? m.r : (r.rt == null ? '' : dhl(r.rt, lang));
    return '<tr>'+cell(r.ln, lh, r.lc)+cell(r.rn, rh, r.rc, rvnGut(rvp, r.rn))+'</tr>';
  }).join('') + '</table>';
}

// ★File type icons (2026-08-31, IntelliJ-like). No external icon set;
//   drawn as **inline SVG** — the viewer is a single file that loads without network, and one icon is not worth breaking
//   that. Shape is color + one or two letters: unrecognized extensions fall back to a gray dot (no lying).
const FT = {
  java:['#E8913A','C'], kt:['#A175E8','K'], scala:['#DE3423','S'], cs:['#68217A','C#'],
  ts:['#3178C6','TS'], tsx:['#3178C6','TS'], js:['#E9C46A','JS'], jsx:['#E9C46A','JS'], mjs:['#E9C46A','JS'],
  py:['#4B8BBE','PY'], go:['#00ADD8','GO'], rs:['#DE7C3F','RS'], rb:['#CC342D','RB'],
  c:['#7A9CC6','C'], h:['#7A9CC6','H'], cpp:['#7A9CC6','C+'],
  sql:['#5FA9D8','SQ'], xml:['#E8A33D','<>'], html:['#E8A33D','<>'], jsp:['#E8A33D','<>'],
  json:['#C9A227','{}'], yaml:['#8FBF6A','Y'], yml:['#8FBF6A','Y'], toml:['#8FBF6A','T'],
  md:['#8B95A7','M'], sh:['#6A9955','$'], bash:['#6A9955','$'],
  gradle:['#5FA9D8','G'], properties:['#8B95A7','P'], css:['#5B9BD5','#'], g4:['#B07ACC','G4'],
};
// Light-theme letter ink per FT hue: the dark hues fall to 1.5\u20132.4:1 on a light tile; these reach >=3:1. Tile keeps the hue.
const FTL = {'#E8913A':'#a85a10', '#A175E8':'#7446c4', '#E9C46A':'#8a6d10', '#4B8BBE':'#2f6a99', '#00ADD8':'#00718e',
  '#DE7C3F':'#a5521a', '#7A9CC6':'#466c9c', '#5FA9D8':'#2f6f9c', '#E8A33D':'#9a6410', '#C9A227':'#8a6d10',
  '#8FBF6A':'#4d7a2a', '#8B95A7':'#5d6779', '#6A9955':'#47703a', '#5B9BD5':'#2f6aa6', '#B07ACC':'#7f4aa0', '#7A8494':'#5d6779'};
function ficon(name){
  const ext = (String(name).split('.').pop() || '').toLowerCase();
  const v = FT[ext] || ['#7A8494', '\u00b7'];
  const c = v[0], t = v[1], fs = t.length > 1 ? 6 : 8.4, ink = thc(c, FTL[c] || c);
  return '<svg class=fic viewBox="0 0 16 16" aria-hidden=true>'
    + '<rect x=1.5 y=1.5 width=13 height=13 rx=3.2 fill="'+c+'" fill-opacity=".16" '
    + 'stroke="'+c+'" stroke-opacity=".5"/>'
    + '<text x=8 y=11.3 text-anchor=middle font-size="'+fs+'" font-weight=600 fill="'+ink+'">'
    + t + '</text></svg>';
}
function dicon(shut){
  return '<svg class=fic viewBox="0 0 16 16" aria-hidden=true>'
    + '<path d="M1.6 4.3c0-.7.5-1.2 1.2-1.2h3.1l1.5 1.6h6.8c.7 0 1.2.5 1.2 1.2v6.4c0 .7-.5 1.2-1.2 1.2H2.8'
    + 'c-.7 0-1.2-.5-1.2-1.2z" fill="#C7A76C" fill-opacity="'+(shut ? '.45' : '.8')+'"/></svg>';
}
// ★Default is **a 3:7 ratio** (2026-08-31). Fixed px makes only the list look narrow on a wider window.
//   dfW is filled **only when a human dragged** — empty means 30% of the current width each time.
const DFW_MIN = 200, DFW_MAX = 1000;
let dfW = (() => { try { const v = +UIS.dfW;
                         return v ? Math.min(DFW_MAX, Math.max(DFW_MIN, v)) : 0; }
                   catch(e){ return 0; } })();
function dfWidth(){
  if(dfW) return dfW;
  const b = document.querySelector('.dbox');
  const w = b ? b.clientWidth : Math.min(2100, innerWidth * 0.97);
  return Math.round(Math.min(DFW_MAX, Math.max(DFW_MIN, (w - 40) * 0.3)));
}
let dfPW = 'today';              // pushed-commit period: today | 3d | 7d
let dfFil = 'all';               // diff modal file filter: all | main | test
// Tests are told by path only (src/test, /test/, *Test.java, *_test.go, *Spec.*, *IT.java)
//   ⚠JS/TS use `xxx.test.ts` / `xxx.spec.tsx`, so the capitalized rule (FooTest.java) alone misses them (measured).
// ⚠No /i: it let «Test.» match word endings (Contest.java, latest.py). Name suffixes need a lowercase/digit before them.
const DF_TEST = /(^|\/)([Tt]ests?|__tests__)(\/|$)|(^|\/|[a-z0-9_])(Test|Tests|Spec|IT)\.[A-Za-z0-9]+$|[._-]([Tt]est|[Ss]pec)\.[A-Za-z0-9]+$|(^|\/)test_[^\/]+$/;
// Shared path tree (diff popup · structure file tree · timeline git rail · structure path list): split → nest → merge
// single-child folder chains into one line (src/main/java/com/example) — unmerged, six or seven empty steps hide the tree.
// Callers keep their node shape: o.split(it, i) → [folder segments, leaf] · o.node(seg, key) → folder with dirs:[] and o.kid:[]
// · o.name/o.kid field names · o.add(folder, it) per-folder totals (root included) · o.root also merges the root chain
// · o.sort 'seg' = folders by own segment (before merging) | 'name' = by merged name · o.leafSort(a, b).
function pathTree(items, o){
  const nm = o.name || 'name', kid = o.kid || 'files', sub = new Map(), cmp = (a, b) => a < b ? -1 : a > b ? 1 : 0;
  const root = o.node('', '');
  sub.set(root, {m: new Map(), key: ''});
  items.forEach((it, i) => {
    const [segs, leaf] = o.split(it, i);
    let f = root;
    if(o.add) o.add(root, it);
    for(const s of segs){
      const r = sub.get(f);
      let c = r.m.get(s);
      if(!c){ const key = r.key ? r.key + '/' + s : s; c = o.node(s, key); sub.set(c, {m: new Map(), key: key}); r.m.set(s, c); }
      if(o.add) o.add(c, it);
      f = c;
    }
    f[kid].push(leaf);
  });
  const fin = (d, top) => {
    while((!top || o.root) && !d[kid].length && sub.get(d).m.size === 1){
      const c = sub.get(d).m.values().next().value;
      c[nm] = d[nm] ? d[nm] + '/' + c[nm] : c[nm];
      d = c;
    }
    const es = [...sub.get(d).m.entries()];
    if(o.sort === 'seg') es.sort((a, b) => cmp(a[0], b[0]));
    d.dirs = es.map(e => fin(e[1], false));
    if(o.sort === 'name') d.dirs.sort((a, b) => cmp(a[nm], b[nm]));
    if(o.leafSort) d[kid].sort(o.leafSort);
    return d;
  };
  return fin(root, true);
}
// Diff popup tree: insertion order, the root chain merges too.
function dfTree(entries){
  return pathTree(entries, {name: 'label', root: true, node: s => ({label: s, dirs: [], files: []}),
    split: e => { const p = e.f.path.split('/'), name = p.pop(); return [p, {name: name, i: e.i, f: e.f, test: e.test}]; }});
}
// Each directory can be collapsed (2026-08-31). Only collapsed ones are remembered —
// remembering expanded ones would default new directories to 'collapsed' and hide them.
let dfShut = new Set();     // collapsed directories — each popup has its own (different document)
let dfAllDirs = [];              // all directories in the current tree — used by 'collapse all'
function dfCount(node){
  let n = node.files.length;
  for(const c of node.dirs) n += dfCount(c);
  return n;
}
// deco (structure tree): {dir(full) → extra classes, file(x) → {cls, attr, tip, fd}} replaces the diff-only row parts.
function dfTreeHtml(node, depth, prefix, deco){
  let out = '';
  const d2 = depth + (node.label ? 1 : 0);
  const full = node.label ? (prefix ? prefix + '/' + node.label : node.label) : '';
  if(node.label){
    const shut = dfShut.has(full);
    out += '<div '+(deco ? 'class="dfd'+deco.dir(full)+'"' : 'class=dfd')+' data-dir="'+esc(full)+'" style="padding-left:'+(depth*13+6)+'px">'
      + '<span class=dfar>'+(shut?'▸':'▾')+'</span>'+dicon(shut)+esc(node.label)+'/'
      + (shut ? '<span class=dfcn>'+dfCount(node)+'</span>' : '') + '</div>';
    if(shut) return out;
  }
  for(const c of node.dirs) out += dfTreeHtml(c, d2, full, deco);
  for(const x of node.files.sort((a,b) => a.name.localeCompare(b.name))){
    const r = deco ? deco.file(x) : null;
    out += '<div class="dfi'+(r ? r.cls : (diffPick===x.i?' on':'')+(x.test?' dft':''))+'" '+(r ? r.attr : 'data-fi="'+x.i+'"')+' '
      + 'style="padding-left:'+(d2*13+6)+'px" title="'+esc(x.f.path)+(r ? r.tip : '')+'">'
      + '<span class=fp>'+ficon(x.name)+esc(x.name)+'</span>'
      + (r ? '<span class=fd>'+r.fd+'</span>' : '<span class=fd>'+[x.f.cut==='all'?T('patch cut'):(x.f.cut==='part'?T('patch partial'):''),
        x.f.isBin?T('binary'):(x.f.isNew?T('new'):(x.f.isGone?T('deleted'):''))].filter(Boolean).join(' ')+'</span>'
      + (x.f.isBin ? '' : '<span class=fa>+'+x.f.add+'</span><span class=fr>-'+x.f.del+'</span>'))
      + '</div>';
  }
  return out;
}
// ★Commit list — unpushed together with **recent already-pushed ones** (2026-08-26).
//   Listed separately, not mixed: "not sent yet" and "already sent" lead to different decisions.
//   Pushed ones are dimmed with a count — the screen must say it is only the recent few, not all.
// ★Times are localized **by the browser** (the server gives only unix seconds) — this file once sliced UTC strings
//   as-is and 8 AM showed as 22:58. Don't repeat the same mistake.
// ⚠Named `agoAt`. `ago(elapsed seconds)` already exists above, and a same-name function **overrode the earlier one
//   by the later declaration**, turning every session row's `ago(x.ageSec)` into "689 months ago" (measured 2026-08-26).
//   `ago` takes elapsed seconds, `agoAt` takes **a time (unix seconds)** — different argument meaning, so different names.
function agoAt(sec){
  const s = Math.max(0, Math.floor(Date.now()/1000) - sec);
  if(s < 60) return T('just now');
  const mi = Math.floor(s/60);      if(mi < 60)  return AGO(U(mi,'m'));
  const h = Math.floor(mi/60);      if(h  < 24)  return AGO(U(h,'h'));
  const dd = Math.floor(h/24);      if(dd < 30)  return AGO(U(dd,'d'));
  return AGO(U(Math.floor(dd/30),'mo'));
}
// ★For staleness only — `agoAt` collapses under 60s into «just now». What is measured here is **how many seconds stale**, and
//   that range is the information (previous-value cap is 30-90s). From 60s on it passes to `agoAt` as-is.
function agoSec(sec){
  const s = Math.max(0, Math.floor(Date.now()/1000) - Math.floor(sec || 0));   // ★2026-09-27: float `at` printed «7.98…s ago»
  return s < 60 ? AGO(U(s,'s')) : agoAt(sec);
}
function stamp(sec){ return hhmm(sec, {date: true}); }
function commitRow(c, picked){
  const on = picked && c.sha && picked.indexOf(c.sha) === 0;
  return '<div class="dcm'+(on?' on':'')+'" data-sha="'+esc(c.sha)+'" title="'+esc(stamp(c.at)+' · '+c.msg)+'">'
    + '<span class=dcs>'+esc(c.sha)+'</span>'
    + '<span class=dct>'+esc(stamp(c.at))+'</span>'
    + '<span class=dca>'+esc(agoAt(c.at))+'</span>'
    + '<span class=dcx>'+esc(c.msg)+'</span></div>';
}
function commitList(d){
  const up = d.unpushed || [], ps = d.pushed || [];
  if(!d.hasUp) return '';                 // without an upstream the word 'push' doesn't apply
  const tg = '<div class="t dhtg"><span class="dfc'+(dfHistOpen?' on':'')+'" data-dhist>'+(dfHistOpen ? '▾ ' : '▸ ')+esc(T('Commit history'))+'</span> <span class=dsn>'
    + esc(TV({msg: '{n} unpushed · {m} pushed', vars: {n: up.length, m: d.pushedAll || ps.length}})) + '</span></div>';
  if(!dfHistOpen) return tg;
  let out = tg;
  if(up.length)
    out += '<div class=t>'+TV({msg: 'Unpushed commits {n}', vars: {n: up.length}})+' <span class=dsn>'+T('newest first · click a row to see only that commit')+'</span></div>'
      + '<div class=dcl>' + up.map(c => commitRow(c, d.pickedSha)).join('') + '</div>';
  // Period chip — default is today. Dozens a day, so cutting by count wouldn't capture "what was done today".
  const pw = k => '<span class="dfc dpw'+(dfPW===k?' on':'')+'" data-pw="'+k+'">'
    + (k === 'today' ? T('Today') : U(parseInt(k, 10), 'd')) + '</span>';
  const cutN = (d.pushedAll || 0) - ps.length;
  out += '<div class=t>'+T('Pushed commits ')
    + (ps.length ? T(d.pushedWin||'') + ' ' + U(d.pushedAll||ps.length, '#msgs') : T('None'))
    + ' <span class=dsn>'+T('newest first')
    + (cutN > 0 ? TV({msg: ' · capped at {n} (the other {m} in a terminal)', vars: {n: ps.length, m: cutN}}) : '')
    + '</span><span class=dpws>' + pw('today') + pw('3d') + pw('7d') + '</span></div>'
    + (ps.length
        ? '<div class="dcl dcp">' + ps.map(c => commitRow(c, d.pickedSha)).join('') + '</div>'
        : '<div class=dfnone>'+T('No commits pushed in this period')+'</div>');
  return out;
}
// File list = the server's numstat (whole change) joined with the patch pieces (cut at DIFF_MAX).
// ⚠Counting from the cut patch showed 6 files where git had 30. Order matches the patch (same git diff queue),
//   so indices from splitDiff (worklog popup's dfWant) still line up for files that have a patch.
function dfFiles(d){
  const pf = splitDiff((d && d.diff) || '');
  if(!d || !Array.isArray(d.numstat)) return pf;
  const by = new Map(pf.map(f => [f.path, f]));
  const last = d.cutBytes && pf.length ? pf[pf.length-1] : null;
  const out = d.numstat.map(s => {
    const f = by.get(s.path) || (s.from && by.get(s.from));
    if(!f) return {path: s.path, add: s.add, del: s.del, body: '', isNew: false, isGone: false, isBin: s.bin, cut: 'all'};
    by.delete(f.path);
    return Object.assign({}, f, {path: s.path, add: s.add, del: s.del, isBin: f.isBin || s.bin, cut: f === last ? 'part' : ''});
  });
  for(const f of by.values()) out.push(f);       // untracked file appended by the rail (`new`) is not in numstat
  return out;
}
function diffBody(d){
  if(!d) return '<div class=t>'+T('Loading…')+'</div>';
  if(!d.ok) return '<div class=t>'+esc(d.msg ? TV(d) : T('Could not fetch'))+'</div>';
  const files = dfFiles(d);
  // ★Tracked files only — the server doesn't send untracked at all (build/ and target/ buried what mattered).
  const head = [];
  if(d.scopeCommit) head.push(T('Commit ') + d.scopeCommit);
  else if(d.scopeBase) head.push(TV({msg: 'Since {n}', vars: {n: d.scopeBase}}));
  else if(d.scope) head.push(T(d.scope));   // fixed English DIFF_SCOPES labels (sidereus/git_view.py); Korean in I18N.ko
  const nAll = Math.max(files.length, d.numstatN || 0);   // numstatN = uncapped numstat count
  if(nAll) head.push(TV({msg: '{n} files', vars: {n: nAll}}));
  if(d.unpushed && d.unpushed.length)
    head.push(TV({msg: '{n} unpushed commits (latest {m})', vars: {n: d.unpushed.length, m: agoAt(d.unpushed[0].at)}}));
  if(d.cutBytes) head.push(TV({msg: 'First part of {n}KB only — see the rest in a terminal', vars: {n: Math.round(d.cutBytes/1024)}}));
  const meta = (head.length ? '<div class=t>'+esc(head.join(' · '))+'</div>' : '')
    // ★Commit rows are **clickable** (2026-08-26). The list existed but was read-only, so
    //   "view only this commit" was impossible. The chosen commit is passed as a scope (c:<sha>) through the existing pipeline
    //   as-is — tree, filters and side-by-side all follow.
    + commitList(d);

  // Without an upstream only the worktree is diffed, so «pushed» would contradict the no-upstream note.
  if(!files.length) return meta + '<div class=t>'+T(d.hasUp === false ? 'No uncommitted changes' : 'No changes — everything is pushed')+'</div>';

  // ★The file list is **a tree** (test code is mixed in with the rest).
  //   A flat list showed only file names, so same names in src/main and src/test were indistinguishable.
  //   Main vs test is decided **by path** only — no guessing from contents.
  const nT = files.filter(f => DF_TEST.test(f.path)).length, nM = files.length - nT;
  const keep = files.map((f,i) => ({f: f, i: i, test: DF_TEST.test(f.path)}))
    .filter(x => dfFil === 'all' || (dfFil === 'test' ? x.test : !x.test));
  const chip = (k, lab, n) => '<span class="dfc'+(dfFil===k?' on':'')+'" data-dfil="'+k+'">'+lab+' '+n+'</span>';
  // ★Collapse/expand all — **actually collects the directory names of the visible tree**.
  //   Faking "all collapsed" with one flag drifts when a filter change alters the tree.
  const allDirs = dfAllDirs = [];
  (function walk(n, prefix){
    const full = n.label ? (prefix ? prefix + '/' + n.label : n.label) : '';
    if(full) allDirs.push(full);
    for(const c of n.dirs) walk(c, full);
  })(dfTree(keep), '');
  const anyOpen = allDirs.some(d => !dfShut.has(d));
  const list = '<div class=dfl>'
    + '<div class=dfcs>' + chip('all',T('All'),files.length) + chip('main',T('Source'),nM) + chip('test',T('Tests'),nT)
      + (allDirs.length ? '<span class="dfc dfall" data-dall="'+(anyOpen?'shut':'open')+'" title="'
          + (anyOpen ? T('Collapse every directory') : T('Expand every directory')) + '">'
          + (anyOpen ? T('▸ Collapse all') : T('▾ Expand all')) + '</span>' : '')
      + '</div>'
    + '<div class="dfi'+(diffPick<0?' on':'')+'" data-fi="-1">'
      + '<span class=fp>'+T('All')+'</span><span class=fn>'+files.length+'</span></div>'
    + (keep.length ? dfTreeHtml(dfTree(keep), 0, '') : '<div class=dfnone>'+T('No files match this filter')+'</div>')
    + '</div>';
  // ★Full expansion is offered **only when one file is chosen** — expanding the whole list would be several MB.
  const one = diffPick >= 0 ? files[diffPick] : null;
  const key = one ? (diffRepo + '\0' + diffScope + '\0' + one.path) : '';   // a different scope is a different result
  const full = one && fullOn ? fullCache[key] : null;
  const nav = one && fullOn && !sbsOn && full && full.ok ? dfChangeN(full.diff) : -1;
  const btn = (nav >= 0
    ? '<span class=dwnv><button class="dfx" data-dnav="-1" title="'+esc(T('Previous change'))+'" aria-label="'+esc(T('Previous change'))+'"'+(nav?'':' disabled')+'>▲</button>'
      + '<button class="dfx" data-dnav="1" title="'+esc(T('Next change'))+'" aria-label="'+esc(T('Next change'))+'"'+(nav?'':' disabled')+'>▼</button>'
      + '<span class=dwnc>'+esc(TV({msg: '{n} changes', vars: {n: nav}}))+'</span></span>'
    : '')
    + (one
    ? '<button class="dfx dwfull'+(fullOn?' on':'')+'">'
      + (fullOn ? T('▴ Changes only') : T('▾ Show the whole file')) + '</button>'
    : '')
    + '<button class="dfx dwsbs'+(sbsOn?' on':'')+'" title="'+T('Switch between side-by-side (IntelliJ style) and unified diff')+'">'
      + (sbsOn ? T('Side by side') : T('Unified')) + '</button>';
  const dir = '<div class="t dfh'+(nav >= 0 ? ' dfhs' : '')+'">'+esc(one ? one.path : TV({msg: 'All {n}', vars: {n: files.length}}))+btn+'</div>';
  let bodyHtml;
  if(one && fullOn){
    if(!full)          bodyHtml = '<div class=t>'+T('Loading the whole file…')+'</div>';
    else if(!full.ok)  bodyHtml = '<div class=t>'+esc(full.msg ? TV(full) : T('Could not fetch'))+'</div>';
    else               bodyHtml = (full.cutBytes ? '<div class=t>'+TV({msg: 'First part of {n}KB only', vars: {n: Math.round(full.cutBytes/1024)}})+'</div>' : '')
                                  + (sbsOn ? sbsHtml(full.diff, agLang(one.path), one.path)
                                           : '<pre>'+diffHtml(full.diff, agLang(one.path), one.path)+'</pre>');
  } else if(one && one.cut === 'all'){
    bodyHtml = '<div class=t>'+T('Patch cut — the whole diff passed the cap before this file · use «Expand full file»')+'</div>';
  } else if(one && one.isBin){
    const sz = (one.body.match(/Bin (\d+) -> (\d+) bytes/) || []);
    bodyHtml = '<div class=t>'+T('Binary file — git gives no line diff')
      + (sz[1] ? ' · '+Math.round(sz[1]/1024)+'KB → '+Math.round(sz[2]/1024)+'KB' : '') + '</div>'
      + '<pre class=dst>'+esc(one.body.trim())+'</pre>';
  } else if(sbsOn){
    // side-by-side needs file boundaries — when viewing all, each file gets a header
    bodyHtml = (one ? [one] : files.filter(f => f.cut !== 'all')).map(f =>
      (one ? '' : '<div class="t xfh">'+esc(f.path)+'</div>') + sbsHtml(f.body, agLang(f.path), f.path)).join('');
  } else {
    const shown = one ? [one] : files.filter(f => f.cut !== 'all');
    // ★The language is set from the file extension — otherwise the combined keywords apply, TS's `type`/`interface`
    //   are missed and SQL keywords get colored wrongly (measured 2026-08-31: only the diff modal wasn't passing the language).
    bodyHtml = '<pre>' + shown.map(f => diffHtml(f.body, agLang(f.path), f.path)).join(NL) + '</pre>';
  }
  const pane = '<div class=dfv>' + meta + dir + bodyHtml + '</div>';
  // ★Left/right width is draggable (2026-08-31). The width is carried as an inline style —
  //   diffShow() replaces innerHTML wholesale, so without state outside the DOM (dfW) each refresh
  //   reverts to the default.
  return '<div class=dsplit style="grid-template-columns:'+dfWidth()+'px 7px 1fr">'
    + list + '<div class=dgrip title="'+T('Drag to resize · double-click to reset')+'"></div>' + pane + '</div>';
}
// Change blocks (runs of +/- lines) in a patch: the whole-file view's ▲▼ steps between them.
function dfChangeN(src){
  let n = 0, inb = false;
  for(const l of String(src || '').split(NL)){
    const ch = /^[+-]/.test(l) && !/^(\+\+\+ |--- )/.test(l);
    if(ch && !inb) n++;
    inb = ch;
  }
  return n;
}
// Scroll the next/previous change block to a third of the scroller; stateless (reads the scroll position) so a manual scroll is respected.
function dfNav(btn, dir){
  const pane = btn.closest('.dfv'), sc = btn.closest('.dbody') || document.scrollingElement;
  if(!pane || !sc) return;
  const isCh = r => !!r && /\bx[ad]\b/.test(r.className);
  const starts = [...pane.querySelectorAll('table.uni tr.xa, table.uni tr.xd')].filter(r => !isCh(r.previousElementSibling));
  if(!starts.length) return;
  const top = sc === document.scrollingElement ? 0 : sc.getBoundingClientRect().top;
  const ref = top + sc.clientHeight / 3, ys = starts.map(r => r.getBoundingClientRect().top);
  let i = dir > 0 ? ys.findIndex(y => y > ref + 4) : ys.map(y => y < ref - 4).lastIndexOf(true);
  if(i < 0) i = dir > 0 ? 0 : starts.length - 1;   // wrap around at either end
  sc.scrollTop += ys[i] - ref;
  starts.forEach(r => r.classList.remove('dnhit'));
  starts[i].classList.add('dnhit');
  const c = pane.querySelector('.dwnc');
  if(c) c.textContent = (i + 1) + ' / ' + starts.length;
}
function toggleFull(){
  fullOn = !fullOn;
  if(!fullOn){ diffShow(); return; }
  const files = dfFiles(diffData);
  const one = diffPick >= 0 ? files[diffPick] : null;
  if(!one){ fullOn = false; return; }
  const key = diffRepo + '\0' + diffScope + '\0' + one.path;
  diffShow();
  if(fullCache[key]) return;                     // already fetched ones are not requested again
  getJSON('/api/git/file?cwd='+encodeURIComponent(diffRepo)+'&path='+encodeURIComponent(one.path)
        +'&scope='+encodeURIComponent(diffScope))
    .then(j => { fullCache[key]=j; }, () => { fullCache[key]={ok:false,msg:T('Could not fetch')}; })
    .then(() => { if(fullOn) diffShow(); });
}
