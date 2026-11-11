// Sessions list: linked-worktree sessions nest under their main repo's session (40b buildSessions walks these groups).
// ⚠Cards are built by 40b sessRowHtml and only post-processed here (lead-cell insert), so sessFit (40ba) keeps every
//   row's columns aligned: the branch glyph and the caret live inside .sxl, never as a row margin.
const wtFold = new Set();   // normalised main roots the user collapsed (the list re-renders every poll)
// ⚠brNorm is owned by 89-branch-worktree.js; the fallback only covers this file loaded alone.
function sessWtNorm(p){ return typeof brNorm === 'function' ? brNorm(p) : String(p || '').replace(/\/+$/, ''); }
// Rows (server order) -> [{head: row|null, main, name, key, kids: [row...]}]; a plain row is {head: x, kids: []}.
// A group sits at its best-ranked member's index; the first-ranked main-checkout session of that root is the head.
function sessWtGroups(rows){
  const N = sessWtNorm, list = (rows || []).filter(Boolean), kids = new Map(), par = new Map(), done = new Set(), out = [];
  // ⚠Nest only when the session runs inside the worktree. A non-git cwd gets wt from the repo it last touched
  //   (sidereus/sessions.py _row_repos_wt); nesting that row put it under a repo it does not live in.
  const inWt = x => { const c = N(x.cwd), r = N(x.wt.root); return !c || !r || c === r || c.startsWith(r + '/'); };
  const mainOf = x => (x.wt && x.wt.main && inWt(x)) ? N(x.wt.main) : '';
  // ⚠A row without wt (git lookup failed) can still head its repo by cwd; a worktree row never heads one.
  const rootOf = x => x.wt ? (x.wt.main ? '' : N(x.wt.root)) : N(x.cwd);
  list.forEach(x => { const m = mainOf(x); if(m){ if(!kids.has(m)) kids.set(m, []); kids.get(m).push(x); } });
  list.forEach(x => { const r = rootOf(x); if(r && kids.has(r) && !par.has(r)) par.set(r, x); });
  list.forEach(x => {
    const m = mainOf(x) || (par.get(rootOf(x)) === x ? rootOf(x) : '');
    if(!m){ out.push({head: x, main: '', name: '', key: '', kids: []}); return; }
    if(done.has(m)) return;
    done.add(m);
    const ks = kids.get(m), main = String(ks[0].wt.main);
    out.push({head: par.get(m) || null, main: main, name: main.replace(/\/+$/, '').split('/').pop() || main, key: m, kids: ks});
  });
  return out;
}
// Strongest attention among child rows: 'blocked' > 'ask' > 'abort' > 'stuck' (prompt arrived, transcript still) > ''.
function sessWtAttn(kids){
  const k = (kids || []).filter(Boolean);
  if(k.some(x => x.blocked)) return 'blocked';
  if(k.some(x => x.state === 'ask')) return 'ask';
  if(k.some(x => x.state === 'abort')) return 'abort';
  return k.some(x => x.gotPrompt > 0) ? 'stuck' : '';
}
function sessWtNeed(kids){ return (kids || []).filter(x => x && (x.blocked || x.state === 'ask' || x.state === 'abort' || x.gotPrompt > 0)).length; }
function sessWtCount(n){ return TV({msg: n === 1 ? '{n} worktree session' : '{n} worktree sessions', vars: {n: n}}); }
// Fold caret (header-only groups); collapsed, it carries the hidden children's count and attention so a need never disappears (R4).
function sessWtCaret(gr){
  const open = !wtFold.has(gr.key), at = sessWtAttn(gr.kids), need = sessWtNeed(gr.kids);
  const cnt = sessWtCount(gr.kids.length), nd = need ? TV({msg: '{n} in Attention', vars: {n: need}}) : '';
  const tip = (open ? T('Collapse worktrees') : T('Expand worktrees')) + ' · ' + cnt + (nd ? ' · ' + nd : '');
  return '<button type=button class="swtg' + (at ? ' swta-' + at : '') + '" data-wtf="' + esc(gr.key) + '" aria-expanded=' + (open ? 'true' : 'false')
    + ' title="' + esc(tip) + '">' + (open ? '▾' : '▸' + gr.kids.length) + (!open && nd ? ' <b class=swtnd>' + esc(nd) + '</b>' : '') + '</button>';
}
// Header-only row for a group whose main checkout has no session in view (R3); not a .sx row, so sessFit skips it.
// ⚠Folded, it gets a row end (.swthf): otherwise the next top-level row reads as its child.
function sessWtHeadHtml(gr){
  return '<div class="swth' + (wtFold.has(gr.key) ? ' swthf' : '') + '" title="' + esc(gr.main + ' · ' + T('Main repo has no session in view')) + '">' + sessWtCaret(gr)
    + '<span class=swthn>' + esc(gr.name) + '</span><span class=swthc>' + esc(sessWtCount(gr.kids.length)) + '</span></div>';
}
function sessWtLead(h, ins){ return h.replace('<span class=sxl>', '<span class=sxl>' + ins); }
// Worktree sessions as one-line subs inside the main card (R1); metadata only: name, state, age — never targ or bodies.
// ⚠Wrapped in .stree so the indent (--sxlead) and rhythm match the subagent sub-lines; never add a separate offset.
function sessWtSubHtml(kids){
  const ks = (kids || []).filter(Boolean);
  return ks.length ? '<div class="stree swtsl">' + ks.map(x => {
    const at = sessWtAttn([x]), hit = cpFlash && cpFlash === cpKey(x) ? ' cphit' : '';
    const nm = (x.wt && x.wt.name) || x.branch || '';
    return '<div class="stiw swts' + (at ? ' swta-' + at : '') + hit + '" data-ssid="' + esc(x.sid || '') + '" data-scwd="' + esc(x.cwd || '')
      + '" title="' + esc(sessCardTip(x)) + '"><div class=sti><span class="k w">' + esc(T('Worktree')) + '</span>'
      + '<span class=v>' + esc(nm) + '</span><span class=swtst>' + esc(sessLabel(x)) + '</span>'
      + (typeof x.ageSec === 'number' ? '<span class=e>' + esc(AGO(ago(x.ageSec))) + '</span>' : '') + '</div></div>';
  }).join('') + '</div>' : '';
}
// Main session in view: one card with worktree subs (R1). Otherwise header-only group, children with ├─/└─ in the lead cell (R3).
function sessWtListHtml(rows){
  return sessWtGroups(rows).map(gr => {
    if(!gr.kids.length) return sessRowHtml(gr.head);
    if(gr.head) return sessRowHtml(gr.head, sessWtSubHtml(gr.kids));
    const head = sessWtHeadHtml(gr);
    if(wtFold.has(gr.key)) return head;
    // ⚠Open group is wrapped (.swtgr) so it has a visible end; unwrapped, every row below read as one of its children.
    return '<div class=swtgr>' + head + gr.kids.map((x, i) => sessWtLead(sessRowHtml(x).replace('class="sxw ', 'class="sxw swtk '),
      '<i class=swtbr>' + (i === gr.kids.length - 1 ? '└─' : '├─') + '</i>')).join('') + '</div>';
  }).join('');
}
// Lead width a child row would take (widest bare lead + gap + ├─ stem); sessFit (40ba) floors --sxlead at it.
function sessWtStemLead(rows, nat){
  const ls = rows.map(r => r.querySelector('.sxl')).filter(Boolean);
  if(!ls.length) return 0;
  const bw = e => e.getBoundingClientRect().width, gap = l => parseFloat(getComputedStyle(l).columnGap) || 0;
  const base = ls.reduce((m, l) => Math.max(m, nat(l) - [...l.querySelectorAll('.swtg,.swtbr')].reduce((s, e) => s + bw(e) + gap(l), 0)), 0);
  const br = ls.map(l => l.querySelector('.swtbr')).find(Boolean);
  let stem = br ? bw(br) : 0;
  if(!br){ const p = document.createElement('i'); p.className = 'swtbr'; p.textContent = '├─'; ls[0].prepend(p); stem = bw(p); p.remove(); }
  // Boxed children (.swtgr) lose the box inset from their lead (60-sessions.css --swtin); reserved even when folded.
  let p = ls[0]; while(p && !(p.querySelector && p.querySelector('.swth'))) p = p.parentElement;
  const h = p && p.querySelector('.swth'), inset = h ? parseFloat(getComputedStyle(h).getPropertyValue('--swtin')) || 0 : 0;
  return base + gap(ls[0]) + stem + inset;
}
// Only header-only groups keep a fold caret, so only they need «Expand all».
function sessWtAny(rows){ return sessWtGroups(rows).some(g => g.kids.length && !g.head); }
// «Expand all / Collapse all» (40b) also covers worktree groups.
function sessWtFoldAll(keys, open){
  if(open) wtFold.clear(); else (keys || []).forEach(k => wtFold.add(k));
  return wtFold.size;
}
function sessWtToggle(key){ if(wtFold.has(key)) wtFold.delete(key); else wtFold.add(key); }
