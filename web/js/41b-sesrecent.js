// ★«Recently ended sessions» (2026-09-27): ended sessions of the last 7 days in the sessions drawer, for `claude --resume` from a terminal.
//   Collapsed by default (sidereus.sesrec '1' = open); GET /api/sessions/recent runs on expand only, never on the poll.
//   ⚠Metadata only — name, branch, model, times; the command is built here from cwd + sid (sid checked hex/hyphen).
let SREC = {open: false, rows: null, at: 0, err: false, q: '', busy: false};
try{ SREC.open = UIS.getItem('sidereus.sesrec') === '1'; }catch(e){ softErr('sesrec-read', e); }
function srecCmd(r){ return r ? resumeCmd(r.cwd, r.sid, r.acctDir) : ''; }   // quoting lives in 40b resumeCmd
function srecHead(){
  const n = SREC.rows ? ' <b class=srecn>' + SREC.rows.length + '</b>' : '';
  return '<button type=button class=srech aria-expanded=' + SREC.open + ' title="' + esc(T('Expand/collapse recently ended sessions')) + '">'
    + '<span class=srecc>' + (SREC.open ? '▾' : '▸') + '</span> ' + esc(T('Recently ended sessions')) + n + '</button>';
}
function srecRows(){
  if(SREC.err) return '<div class=srecm>' + esc(T('Could not load ended sessions')) + '</div>';
  if(!SREC.rows) return '<div class=srecm>' + esc(T('Loading…')) + '</div>';
  if(!SREC.rows.length) return '<div class=srecm>' + esc(T('No sessions ended in the last 7 days')) + '</div>';
  const q = SREC.q.trim().toLowerCase();
  const rq = q ? SREC.rows.filter(r => ((r.name || '') + ' ' + (r.branch || '') + ' ' + (r.sid || '') + ' ' + (r.agentDesc || '')).toLowerCase().includes(q)) : SREC.rows;
  const rs = ACC_OTH.srec ? rq : rq.filter((pk => r => acctInPick(r, 'sess', pk))(acctPick('sess'))), oth = acctOthHtml('srec', rq.length - rs.length, false);
  if(!rs.length) return (oth ? '' : '<div class=srecm>' + esc(T('No matching sessions')) + '</div>') + oth;
  return rs.map(r => {
    const i = SREC.rows.indexOf(r), cmd = srecCmd(r), ac = acctRowCls(r);
    return (ac ? '<div class="srecr ' + ac + '" data-i=' + i + ' title="' + esc(acctTip(r)) + '">' : '<div class=srecr data-i=' + i + '>')
      + '<span class=srecnm title="' + esc(r.cwd || '') + '">' + esc(r.name || '?') + '</span>'
      + (r.branch ? '<span class=srecbr>' + esc(r.branch) + '</span>' : '')
      + acctChip(r, 'srecac')
      // short sid + last Agent description: rows of one repo/branch were otherwise identical
      + (r.sid ? '<span class=srecsd title="' + esc(r.sid) + '">' + esc(String(r.sid).slice(0, 8)) + '</span>' : '')
      + (r.agentDesc ? '<span class=srecds title="' + esc(plStrip(r.agentDesc)) + '">' + esc(plStrip(r.agentDesc)) + '</span>' : '')
      + (r.model ? '<span class=srecmd>' + esc(r.model) + '</span>' : '')
      + (r.pct != null ? '<span class=srecpc title="' + esc(T('Context')) + '">' + (+r.pct || 0) + '%</span>' : '')
      + (r.gone ? '<span class=srecgn title="' + esc(T('The folder no longer exists')) + '">⚠</span>' : '')
      + '<span class=srecag>' + esc(agoAt(+r.endedAt || 0)) + '</span>'
      + (cmd ? '<button type=button class=srecb data-a=copy title="' + esc(T('Paste into a terminal to resume this session') + '\n' + cmd) + '">' + esc(cpfbLabel('srec:' + r.sid, T('Copy command'))) + '</button>' : '')
      + (r.cwd ? '<button type=button class=srecb data-a=work>' + esc(T('Work log')) + '</button>' : '')
      + '</div>' + cpfbBox('srec:' + r.sid, cmd, 'srcp', 'type=button class=srecb data-a=cpx');
  }).join('') + oth;
}
function srecPaint(){
  const s = document.getElementById('sesrec'); if(!s) return;
  s.querySelector('.srechd').innerHTML = srecHead();
  const body = s.querySelector('.srecbd'); body.hidden = !SREC.open;
  const f = s.querySelector('.srecf'), many = !!(SREC.rows && SREC.rows.length > 10);
  f.hidden = !many;
  if(!many && SREC.q){ SREC.q = ''; f.value = ''; }
  f.placeholder = T('Filter by name or branch'); f.setAttribute('aria-label', f.placeholder);
  s.querySelector('.srecl').innerHTML = srecRows();
}
function srecLoad(){
  if(SREC.busy || (SREC.rows && Date.now() - SREC.at < 30000)) return;
  SREC.busy = true;
  fetch('/api/sessions/recent?days=7').then(r => r.json()).then(j => {
    SREC.err = !(j && j.ok); SREC.rows = SREC.err ? null : (j.rows || []); SREC.at = Date.now();
  }).catch(e => { SREC.err = true; softErr('sesrec-load', e); })
    .finally(() => { SREC.busy = false; srecPaint(); });
}
function srecToggle(){
  SREC.open = !SREC.open;
  try{ UIS.setItem('sidereus.sesrec', SREC.open ? '1' : '0'); }catch(e){ softErr('sesrec-write', e); }
  if(SREC.open){ SREC.err = false; srecLoad(); }
  srecPaint();
}
function srecLang(){ srecPaint(); }
(function(){
  const sess = document.getElementById('sess');
  if(!sess || ISPOP || ISWP || ISBP) return;
  const s = document.createElement('section'); s.id = 'sesrec'; s.className = 'srec';
  s.innerHTML = '<div class=srechd></div><div class=srecbd><input class=srecf type=search hidden><div class=srecl></div></div>';
  sess.after(s);   // outside #sess: the 2.5 s list repaint would wipe the filter input
  s.addEventListener('click', e => {
    if(e.target.closest('.srech')) return srecToggle();
    const l = s.querySelector('.srecl');
    if(acctOthClick(e, () => { l.innerHTML = srecRows(); })) return;
    if(e.target.closest('[data-a=cpx]')){ CPFB.box = ''; l.innerHTML = srecRows(); return; }
    const b = e.target.closest('.srecb'), row = b && b.closest('.srecr');
    const r = row && SREC.rows && SREC.rows[+row.dataset.i]; if(!r) return;
    if(b.dataset.a === 'copy'){   // same in-place feedback as attention «Copy resume command» (17 cpfb*)
      const key = 'srec:' + r.sid;
      cpfbCopy(key, srecCmd(r), () => {
        l.innerHTML = srecRows();
        const cp = CPFB.box === key && CPFB.until && l.querySelector('.srcp input'); if(cp){ cp.focus(); cp.select(); }
      }, T('Copied — paste it in a terminal'));
    }
    else if(b.dataset.a === 'work') wkPopup(r.cwd, 'sess:' + r.cwd + '|' + r.sid);
  });
  s.querySelector('.srecf').addEventListener('input', e => { SREC.q = e.target.value; s.querySelector('.srecl').innerHTML = srecRows(); });
  srecPaint();
  if(SREC.open) srecLoad();
})();
