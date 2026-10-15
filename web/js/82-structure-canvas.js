// Snapshot source (server `src`) → [label, tooltip]; raw ids like "cur" were unreadable.
const STR_SRC_LAB = {
  cur: ['Current', 'The working tree on disk now — the latest state, not a commit or backup'],
  git: ['Git commit', 'Files as of a git commit'],
  backup: ['Backup', 'Files as of a tar backup'],
  bak: ['.bak copy', 'As of a .bak copy in the same folder']
};
// Swap only slider, label and total lines in place — a full repaint during playback stutters
// Area label: the server's fixed areas (sidereus/structure_scan.py STRUCT_AREAS + 'etc') are dictionary keys; folder-derived labels are user data.
const STR_AREA_FIXED = new Set(['quota', 'timeline', 'saver', 'http', 'bg', 'fail', 'chat', 'ui', 'etc']);
function strAreaNm(a){ return a && STR_AREA_FIXED.has(a.key) ? T(a.name || '') : (a && a.name) || ''; }
// Snapshot source without a STR_SRC_LAB entry: the merged view's '<n> merged' (80-structure.js) or server text as-is.
function strSrcTxt(src){ const m = /^(\d+) merged$/.exec(String(src)); return m ? T('{n} merged').replace('{n}', m[1]) : String(src); }
function strSyncBar(){
  const snaps = (STR && STR.snaps) || [];
  const snap = snaps[strIdx];
  if(!snap) return;
  const rg = document.getElementById('strrg');
  if(rg && +rg.value !== strIdx) rg.value = strIdx;
  const lb = document.getElementById('strlb');
  if(lb) lb.innerHTML = esc(snap.label || '')
    + (snap.rev ? ' <u>' + esc(snap.rev) + '</u>' : '')
    + (snap.src ? ' <u title="' + esc(STR_SRC_LAB[snap.src] ? T(STR_SRC_LAB[snap.src][1]) : strSrcTxt(snap.src)) + '">'
        + esc(STR_SRC_LAB[snap.src] ? T(STR_SRC_LAB[snap.src][0]) : strSrcTxt(snap.src)) + '</u>' : '')
    // ⚠Without writing `partial` it looks like «lines suddenly jumped» — only some files existed at that point
    + (snap.partial ? ' <b class=strpt title="'
        + esc(T('Only some files existed at that point — do not read this step as «growth»')) + '">' + esc(T('partial')) + '</b>' : '');
  const tt = document.getElementById('strtt');
  if(tt) tt.textContent = (snap.total || 0).toLocaleString();
}
function strGo(i){
  const snaps = (STR && STR.snaps) || [];
  if(!snaps.length) return;
  strIdx = Math.max(0, Math.min(snaps.length - 1, i));
  strNew = strNewSet(strIdx);
  strFlash = strNew.size ? Date.now() : 0;
  strDraw(); strSyncBar();
}
function strToggle(){
  if(strPlay){ strStop(); return paintStruct(); }
  const snaps = (STR && STR.snaps) || [];
  if(snaps.length < 2) return;
  if(strIdx >= snaps.length - 1) strGo(0);        // Clicking at the end regrows from the beginning
  strPlay = setInterval(() => {
    if(mainView !== 'struct'){ strStop(); return; }
    const n = ((STR && STR.snaps) || []).length;
    if(strIdx >= n - 1){ strStop(); return paintStruct(); }
    strGo(strIdx + 1);
  }, STR_STEP);
  paintStruct();
}
// Canvas font = the DOM UI font: computed family + the data-ui=next size bump (00-core fsz: body 13.5 -> 14.5px).
function strFontOf(cv){
  const fam = getComputedStyle(cv).fontFamily || STR_FONT;
  const bump = Math.max(0, Math.min(2, (parseFloat(getComputedStyle(document.body).fontSize) || 13.5) - 13.5));
  return (px, wt) => (wt ? wt + ' ' : '') + (px + bump) + 'px ' + fam;
}
// Longest middle ellipsis of s within w keeping >= min chars ('' if none) — the tail is what tells siblings apart.
function strMid(g, s, w, min){
  s = String(s);
  if(g.measureText(s).width <= w) return s;
  const n = s.length, at = k => s.slice(0, Math.ceil(k / 2)) + '…' + s.slice(n - Math.floor(k / 2));
  let lo = min - 1, hi = n - 1;
  while(lo < hi){ const k = (lo + hi + 1) >> 1; if(g.measureText(at(k)).width <= w) lo = k; else hi = k - 1; }
  return lo >= min ? at(lo) : '';
}
// First candidate that fits whole ('' if none).
function strFit(g, cs, w){
  for(let i = 0; i < cs.length; i++) if(cs[i] && g.measureText(cs[i]).width <= w) return cs[i];
  return '';
}
// Header: «name  N lines» -> name -> middle ellipsis (>= «a…») -> nothing; the hover tooltip carries the full text.
function strHead(g, name, cnt, x, y, w){
  if(w <= 5) return;
  const s = strFit(g, [name + '  ' + cnt], w) || strMid(g, name, w, 1);
  if(s) g.fillText(s, x, y);
}
// Cell name parts: base (file or function name), suffix («· N items»), stem (file name without extension).
function strParts(f){
  const nm = String(f.name || '');
  if(!f.rest) return { base: nm, suf: '', stem: '' };
  const base = f.etc ? nm.split(' · ')[0] : strShort(f.file || nm);
  const m = f.etc ? null : /^(.+)(\.[A-Za-z0-9]{1,5})$/.exec(base);
  return { base: base, suf: nm.indexOf(base) === 0 ? nm.slice(base.length) : '', stem: m ? m[1] : '' };
}
// Cut point of the prefix s shares with a sibling, at a word boundary (_ - . / : or camelCase); 0 = keep whole.
function strCut(s, sibs){
  let L = 0;
  sibs.forEach(t => { if(t === s) return; let i = 0; const m = Math.min(s.length, t.length);
    while(i < m && s[i] === t[i]) i++; if(i > L) L = i; });
  if(L < 3) return 0;
  for(let i = Math.min(L, s.length - 1); i >= 3; i--){
    const c = s[i];
    if('_-. /:'.indexOf(c) >= 0 || (c >= 'A' && c <= 'Z' && s[i - 1] >= 'a' && s[i - 1] <= 'z')) return i;
  }
  return L < s.length ? L : 0;
}
// ⚠An elided label is dropped when its visible pieces also match another sibling — «structure…» told nothing apart.
function strAmb(lab, names){
  const ps = lab.split('…').filter(Boolean), head = lab[0] !== '…';
  let n = 0;
  for(let k = 0; k < names.length; k++){
    const t = names[k];
    let i = 0, ok = true;
    for(let j = 0; j < ps.length && ok; j++){
      const at = t.indexOf(ps[j], i);
      if(at < 0 || (j === 0 && head && at !== 0)) ok = false; else i = at + ps[j].length;
    }
    if(ok && ++n > 1) return true;
  }
  return false;
}
// Sibling names per area, built once per draw.
function strGroups(rects){
  const m = new Map();
  rects.forEach(r => { if(!r.f || r.w <= 0) return;
    let e = m.get(r.a); if(!e){ e = { names: [], forms: [] }; m.set(r.a, e); }
    const p = strParts(r.f); e.names.push(p.base); e.forms.push(p.stem || p.base); });
  return m;
}
// File/function cell label: with count -> name -> no extension -> shared prefix stripped -> middle ellipsis (>= 5 chars).
function strCellLab(g, f, grp, w){
  const p = strParts(f), form = p.stem || p.base;
  const cut = grp ? strCut(form, grp.forms) : 0;
  const stemOk = p.stem && (!grp || grp.forms.filter(x => x === p.stem).length < 2);
  const cs = [p.suf ? p.base + p.suf : '', p.base, stemOk ? p.stem : '',
              cut && p.base.length - cut >= 4 ? '…' + p.base.slice(cut) : '',
              cut && p.stem.length - cut >= 4 ? '…' + p.stem.slice(cut) : ''];
  for(let i = 0; i < cs.length; i++){
    const s = cs[i];
    if(s && g.measureText(s).width <= w && !(s[0] === '…' && grp && strAmb(s, grp.names))) return s;
  }
  const s = strMid(g, stemOk ? p.stem : p.base, w, 5);
  return s && !(grp && strAmb(s, grp.names)) ? s : '';
}
function strDraw(){
  const cv = document.getElementById('strcv');
  if(!cv || !STR || !STR.ok) return;
  const snap = (STR.snaps || [])[strIdx];
  if(!snap) return;
  // ★Height is read from the cell (`.strwrap`) **on every render** — that cell takes the remaining height via `flex:1`.
  // ⚠When the tab is hidden clientWidth/Height are 0. Drawing then collapses the canvas to 0px and it vanishes —
  // **do not draw**, return (ResizeObserver calls again when visible).
  const box = cv.parentNode;
  if(!box || box.clientWidth < 8 || box.clientHeight < 8) return;
  const W = Math.max(240, box.clientWidth), H = Math.max(120, box.clientHeight);
  strLastW = box.clientWidth; strLastH = box.clientHeight;
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  const pw = Math.round(W * dpr), ph = Math.round(H * dpr);
  if(cv.width !== pw) cv.width = pw;
  if(cv.height !== ph) cv.height = ph;
  cv.style.width = W + 'px'; cv.style.height = H + 'px';
  const g = cv.getContext('2d');
  if(!g) return;
  const t0 = (window.performance && performance.now) ? performance.now() : 0;
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.fillStyle = thc('#0d1014', '#f4f5f7'); g.fillRect(0, 0, W, H);
  strRects = strLayout(snap, W, H);
  const F = strFontOf(cv), grps = strGroups(strRects);
  const nw = strNew || new Set();
  const glow = !!strFlash && (Date.now() - strFlash < 900);
  g.textBaseline = 'middle';
  for(let i = 0; i < strRects.length; i++){
    const r = strRects[i];
    if(r.w <= 0 || r.h <= 0) continue;
    if(r.proj){                        // Outermost of 3 tiers = project. Only the last folder name of the path is written
      g.fillStyle = thc('#10151d', '#ffffff'); g.fillRect(r.x, r.y, r.w, r.h);
      g.strokeStyle = thc('#3a4a63', '#b7c3d4'); g.lineWidth = 1.2;
      g.strokeRect(r.x + 0.6, r.y + 0.6, Math.max(0, r.w - 1.2), Math.max(0, r.h - 1.2));
      if(r.h > 18){
        g.fillStyle = thc('#8ab4ff', '#1b5fd6'); g.font = F(11.5, 600);
        // Unit on the label — a bare «10,198» read as unitless (UX audit 09-24).
        strHead(g, r.g.name, U((r.g.lines || 0).toLocaleString(), ' lines'), r.x + 5, r.y + 9, r.w - 9);
      }
      continue;
    }
    // ★With 3 tiers cells are narrow — make the text-omission threshold **one step stricter** (overlaps are unreadable)
    const tg = !!r.tight;
    if(r.area){
      // Test areas (only sent when "include tests" is on) — desaturated and separated by a dotted border
      const tst = r.a && r.a.test === true;
      g.fillStyle = tst ? thc('#191720', '#f3f1f8') : thc('#141922', '#f7f8fa'); g.fillRect(r.x, r.y, r.w, r.h);
      if(tst) g.setLineDash([4, 3]);
      g.strokeStyle = tst ? thc('#55506b', '#a9a2c2') : thc('#2a3442', '#d0d6de'); g.lineWidth = 1;
      g.strokeRect(r.x + 0.5, r.y + 0.5, Math.max(0, r.w - 1), Math.max(0, r.h - 1));
      if(tst) g.setLineDash([]);
      if(tg ? r.h > 13 : r.h > 16){
        g.fillStyle = tst ? thc('#9a93b4', '#5d5578') : thc('#c3ccda', '#3b4148'); g.font = tg ? F(9.5, 600) : F(11, 600);
        strHead(g, strAreaNm(r.a), U((r.a.lines || 0).toLocaleString(), ' lines'),
                r.x + (tg ? 4 : 5), r.y + (tg ? 7 : 8), r.w - (tg ? 7 : 9));
      }
      continue;
    }
    const f = r.f;
    const lv = strLevel(r.a, f);          // Color axis ("recent change" default · "edit count" optional)
    g.fillStyle = strColor(lv);
    g.fillRect(r.x, r.y, r.w, r.h);
    const isNew = !f.more && nw.has(strFk(r.a, f));
    // Cells changed at this point = magenta border (newly created cells stay gold) — `#ff4fa3` below is the source of truth
    const isChg = !f.more && !isNew && strSi(r.a) > 0 && strLastOf(r.a, f) === strSi(r.a);
    if(isNew){ g.strokeStyle = glow ? thc('#ffe7a8', '#f0a800') : thc('#e0b45f', '#b57f00'); g.lineWidth = glow ? 2 : 1.4; }
    else if(isChg){ g.strokeStyle = glow ? thc('#ffc0dd', '#ff7ab8') : thc('#ff4fa3', '#d6247a'); g.lineWidth = 2; }
    else { g.strokeStyle = thc('#0d1014', '#f4f5f7'); g.lineWidth = 1; }
    if(r.w > 1.6 && r.h > 1.6) g.strokeRect(r.x + 0.8, r.y + 0.8, r.w - 1.6, r.h - 1.6);
    // Width gate is the fit itself (strCellLab) — a cell with no distinguishing label that fits stays blank.
    if(r.w >= 24 && r.h >= (tg ? 18 : 15)){
      const dark = lv >= 3;                            // Dark text on dark-filled cells
      const two = r.h >= (tg ? 34 : 29);
      g.fillStyle = dark ? thc('#0c1219', '#ffffff') : thc('#d7dfea', '#252b31');
      g.font = F(tg ? 9.5 : 10);
      const lab = strCellLab(g, f, grps.get(r.a), r.w - 7);
      if(lab) g.fillText(lab, r.x + 4, r.y + (two ? 11 : r.h / 2));
      if(two && lab){
        g.fillStyle = dark ? thc('#16324d', '#e6effa') : thc('#8b95a7', '#61656c');
        g.font = F(tg ? 9 : 9.5);
        const ln = U(String(f.lines || 0), ' lines');
        const l2 = strFit(g, [ln + ((f.churn || 0) > 0 ? ' · ' + T('{n} edits').replace('{n}', f.churn) : ''), ln], r.w - 7);
        if(l2) g.fillText(l2, r.x + 4, r.y + 23);
      }
    }
  }
  if(snap.partial){        // Dotted border = only some files existed at that point
    g.setLineDash([5, 4]); g.strokeStyle = thc('#e0b45f', '#b57f00'); g.lineWidth = 2;
    g.strokeRect(1, 1, W - 2, H - 2); g.setLineDash([]);
  }
  strMs = t0 ? Math.round((performance.now() - t0) * 10) / 10 : 0;
  if(glow){ clearTimeout(strFlashT); strFlashT = setTimeout(() => { strFlash = 0; strDraw(); }, 900); }
}
// Coordinate → cell. Scan from the end — function cells are stacked after area cells, so they are on top.
function strHit(mx, my){
  for(let i = strRects.length - 1; i >= 0; i--){
    const r = strRects[i];
    if(r.w > 0 && r.h > 0 && mx >= r.x && mx <= r.x + r.w && my >= r.y && my <= r.y + r.h) return r;
  }
  return null;
}
function strMove(e){
  const cv = document.getElementById('strcv'), tip = document.getElementById('strtip');
  if(!cv || !tip) return;
  const b = cv.getBoundingClientRect();
  const mx = e.clientX - b.left, my = e.clientY - b.top;
  const r = strHit(mx, my);
  if(!r){ tip.style.display = 'none'; cv.style.cursor = 'default'; return; }
  cv.style.cursor = 'pointer';
  let html;
  if(r.proj && !r.a){            // Project cell — write only the **path** and line count
    html = '<b>' + esc(r.g.name) + '</b><u>' + esc(r.g.path) + '</u>'
         + '<u>' + T('{n} lines · {m} areas').replace('{n}', (r.g.lines || 0).toLocaleString()).replace('{m}', ((r.g.areas || []).length)) + '</u>'
         + (r.g.label ? '<i>' + esc(r.g.label) + ' ' + esc(T('snapshot')) + '</i>' : '');
  } else if(r.area || !r.f){
    html = '<b>' + esc((r.a.pname ? r.a.pname + ' · ' : '') + strAreaNm(r.a))
         + (r.a.test === true ? ' · ' + esc(T('Tests')) : '') + '</b><u>'
         + T('{n} lines · {m} functions').replace('{n}', (r.a.lines || 0).toLocaleString()).replace('{m}', (r.a.n || 0)) + '</u>'
         + '<i>' + esc(T(strZoom ? 'Click to go back to the whole view'
                                 : 'Click to zoom this area with its code list')) + '</i>';
  } else if(r.f.rest){
    html = '<b>' + esc(r.f.etc ? r.f.name : strShort(r.f.file)) + '</b>'
         + (r.f.etc ? '' : '<u>' + esc(r.f.file) + '</u>')
         + '<u>' + T('{n} functions · {m} lines').replace('{n}', (r.f.more || 0)).replace('{m}', (r.f.lines || 0).toLocaleString()) + '</u>'
         + '<u>' + esc(T('Functions left undrawn because of the cap')) + '</u>'
         + '<i>' + esc(T(r.f.etc ? 'Click to expand this area' : "Click to expand this area and list only this file's functions")) + '</i>';
  } else if(r.f.more){
    html = '<b>' + esc(r.f.name) + '</b><u>' + U((r.f.lines || 0).toLocaleString(), ' lines') + '</u>'
         + '<u>' + esc(T('Functions left undrawn because of the cap')) + '</u>'
         + '<i>' + esc(T('Click to expand this area')) + '</i>';
  } else {
    const f = r.f, sn = strSnapsOf(r.a), L = strLastOf(r.a, f);
    html = '<b>' + esc(f.name) + '</b>'
         + '<u>' + esc(f.file || '') + ' : ' + (f.line || 0) + '</u>'
         + '<u>' + (T('{n} lines · {m} edits · last').replace('{n}', (f.lines || 0)).replace('{m}', (f.churn || 0)) + ' ')
         + esc(((sn[L] || {}).label) || '?') + '</u>'
         + '<i>' + esc(T((strNew && strNew.has(strFk(r.a, f))) ? 'Created at this point'
                                                              : "Click to see this box's code")) + '</i>';
  }
  tip.innerHTML = html;
  tip.style.display = 'block';
  tip.style.left = Math.max(0, Math.min(mx + 14, cv.clientWidth - tip.offsetWidth - 4)) + 'px';
  tip.style.top  = Math.max(0, Math.min(my + 14, cv.clientHeight - tip.offsetHeight - 4)) + 'px';
}
function strClick(e){
  const cv = document.getElementById('strcv');
  if(!cv) return;
  const b = cv.getBoundingClientRect();
  const r = strHit(e.clientX - b.left, e.clientY - b.top);
  if(!r || !r.a) return;                 // Project cells (header strip) are not drilldown targets
  strStop();
  // (1) "+N more" group cell — drills into that area and **lifts the cap** (refetch with `full=1`).
  // ⚠Do not lift the cap in the full view — repo-A has 13,485 functions, a 22MB response (measured).
  if(r.f && r.f.more){
    // ⚠Cap already lifted: a per-file grey cell's functions are still not in the response, so its list was always empty
    //   («This file's functions are not in the list yet») ⇒ open that file's source instead.
    if(strFull && strZoom === r.a.key && r.f.rest && r.f.file){ strPopOpenTree(strOn[0] || (STR && STR.path) || '', r.f.file, 1); return; }
    strZoom = r.a.key;
    strPan = { ak: r.a.key, list: 1, name: strAreaNm(r.a) };   // Expanding also emits the **child code list**
    if(r.f.rest && r.f.file){ strPan.file = r.f.file; strPan.name = r.a.name + ' · ' + strShort(r.f.file); }   // per-file cell: list filtered to it
    if(!strFull){ strFull = 1; strRebuild(false); loadStruct(false); }
    return paintStruct();
  }
  // (2) Function cell — a **code panel**, not a drilldown. Clicking the same cell again closes it.
  if(r.f){
    const k = strFk(r.a, r.f);
    strPan = { ak: r.a.key, fk: k, name: r.f.name };   // The panel keeps only metrics and sparkline
    strPopOpen(r.a.key, k, r.f.name, 'code');          // Code is a **popup**
    return paintStruct();
  }
  // (3) Area cell — existing drilldown **as is** (do not remove) + that area's child code list shown in the panel
  // (2026-09-22: show the child code list). Leaving collapses both expansion and panel.
  strPan = null;
  if(strZoom){ strZoom = ''; if(strFull){ strFull = 0; strRebuild(false); } }
  else { strZoom = r.a.key; strPan = { ak: r.a.key, list: 1, name: strAreaNm(r.a) }; }
  paintStruct();
}
// Redraw on width change — canvas does not stretch via CSS (stretching blurs it)
window.addEventListener('resize', () => {
  clearTimeout(strRz);
  strRz = setTimeout(() => { if(mainView === 'struct') strDraw(); }, 140);
});

