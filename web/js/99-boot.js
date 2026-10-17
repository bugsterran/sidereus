jump.onclick=()=>{ pending=0; jump.style.display='none'; toBottom(true); };
feed.addEventListener('scroll',()=>{ if(atBottom()){ pending=0; jump.style.display='none'; } olderToggle(); },{passive:true});
// ★Boot — the popup window does not run the chat screen. It fetches the session list (SESS) once to fill repo tabs/branches
// and shows the diff. Afterwards it refreshes lightly every 15s (no reason to run the 2.5s poll per window).
if(ISPOP){
  document.body.classList.add('dpop');
  document.getElementById('dbody').innerHTML = '<div class=t>' + T('Loading…') + '</div>';
  { const dq = new URLSearchParams(location.search);   // open at one file, one commit or a baseline
    if(dq.get('file')) dfWant = dq.get('file');
    // b:<sha> = a baseline (Timeline chip) · c:<sha> = one commit; the server re-validates both.
    const sc = dq.get('scope') || '';
    if(sc === 'work' || /^[bc]:[0-9a-f]{4,40}$/i.test(sc)) diffScope = sc;
    const sd = dq.get('sid') || '';   // Timeline chip session: id shape only, the server resolves it
    if(/^[0-9a-f][0-9a-f-]{7,63}$/i.test(sd)) dfSid = sd; }
  Promise.resolve(poll(true)).then(() => loadDiff(DPOP_CWD), () => loadDiff(DPOP_CWD));
  setInterval(poll, 15000);
} else if(ISWP){
  // Work-log popup: SESS once for labels, then the light 15s poll; the log itself refreshes every 2.5s like the old tab.
  document.body.classList.add('wpop');
  const wc = WPQ.get('cwd'), wt = WPQ.get('tid');
  // Work unit "open all" (brWuOpenAll): &more = extra "cwd\ttid" lines, &lay = layout for the total count.
  // ⚠Layout is set in memory only — not saved to mbWtLayout, so the user's own default is untouched.
  const more = (WPQ.get('more') || '').split('\n').map(s => s.split('\t')).filter(a => a.length === 2 && a[0] && a[1]).slice(0, 3);
  const wl = WT_LAYOUTS[WPQ.get('lay')];
  if(more.length && wl && wl.n === more.length + 1){
    wtLayout = WPQ.get('lay'); wtSplit = true; wtPanes = new Array(wl.n).fill(''); wtFocus = 1;
  }
  const one = (c, t) => { if(t.indexOf('sess:') === 0 || t.indexOf('ext:') === 0) openSession(c, t); else openAgent(c, t); };
  const go = () => { one(wc, wt); more.forEach(a => one(a[0], a[1])); };
  Promise.resolve(poll(true)).then(go, go);
  setInterval(poll, 15000); setInterval(() => { refreshAgent(); wkcTick(); }, 2500);   // wkcTick: faster poll only after a DM
} else if(ISBP){
  document.body.classList.add('wpop');      // branch file diff: static, fetched once
  brPopBoot();
} else {
  // ⚠A hidden tab still polls, but every 30s instead of 2.5s — 43-notify.js fires OS notifications from poll
  // exactly when the tab is not visible, so stopping would silence them. Back to visible = poll at once.
  let pollLast = Date.now();
  const pollTick = () => { if(document.hidden && Date.now() - pollLast < 30000) return; pollLast = Date.now(); poll(); };
  poll(true); setInterval(pollTick, 2500); setInterval(loadLive, LIVE_EVERY);
  document.addEventListener('visibilitychange', () => { if(!document.hidden){ pollLast = Date.now(); poll(); } });
}
