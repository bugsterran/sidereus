// % uses the same 4-level colors as the context display (same meaning must mean same color)
const qcls = p => p>=100 ? 'qover' : (p>=85 ? 'qhot2' : (p>=60 ? 'qmid' : (p>=40 ? 'qok' : 'qcool')));
// Gauge — also shown as **length** beside the number (readable at a glance). Over 100% fills the cell and signals by color.
const gauge = p => '<span class="qg '+qcls(p)+'"><i style="width:'+Math.min(100,Math.max(0,p))+'%"></i></span>';
// Data-age span shared by quota/burn rows: seconds below `sUnder`, then minutes, hours only when `hrs`. ⚠Not ago() — its cut-offs differ (tests/test_age_span.py).
function ageU(sec, sUnder, hrs){
  if(sec < sUnder) return U(sec,'s');
  return hrs && sec >= 3600 ? U(Math.floor(sec/3600),'h') : U(Math.floor(sec/60),'m');
}
// ★Hold on to the last official value — dropping to an estimate on one empty poll makes numbers jump
// (2026-09-04: value went 30 > 25 back down). Held values recompute their age and say they are stale.
let QLAST = null;
// ★Saver mode badge (2026-09-04).
// The **server** decides — it must use the same inputs as the hook so screen and model say the same thing.
function buildSaver(sv){
  const el = document.getElementById('saver');
  if(!el) return;
  // ★2026-09-21: this badge covers **all modes** (goal label moved into the saver label position).
  // The header chip was removed.
  // ⚠There are two verdicts — server `_saver_state` (`sv`) and hook snapshot (`SV`). **Do not mix them.** If the snapshot is fresh
  // use only it; if missing or stale, go wholly to `sv` (`sv` does not know `pace`). Which one is shown in the tooltip.
  const r = svParts(SV, null, svLive());
  const snap = !!(r && !r.old);
  const legacy = !!(sv && sv.on);
  // ⚠`body.svon` (whole-screen tint) and pulse are **only for saver «stages»**. Keep this condition separate from
  // badge visibility — if tint turns on for `pace`/headroom, the whole screen looks like saver mode when it is not.
  const saving = snap ? (r.stage > 0) : legacy;
  document.body.classList.toggle('svon', saving);
  // ⚠«Turn on tint?» (`saving`) and «which markup to draw?» (`legacyBadge`) are **different questions**.
  // Goal mode must not be replaced by "saver stage N" even when a stage is set — goal time and required rate vanish
  // and people cannot tell why it is tightening. `svParts` puts the stage into the same badge via `tag`/`sub`.
  const legacyBadge = saving && !(snap && r.mode === 'pace');
  const srcNote = snap ? '' : '\n\n' + (r ? T('(hook snapshot is stale, so the server verdict is shown)') : T('(hook snapshot is missing, so the server verdict is shown)'));
  if(!legacyBadge){
    // Non-saver modes — goal/off/headroom/limit unknown. With no inputs at all, take no space
    // (hiding is the "hook is dead" signal — headroom is not hidden, it stays at lowest contrast).
    if(!r){ setHtml(el, ''); if(el.className !== 'saver') el.className = 'saver'; el.removeAttribute('title'); return; }
    const tip2 = KE(r.head || r.main, r.main + (r.sub ? '\n' + r.sub : '')) +(r.old ? '\n\n' + r.ago + T(' — the hook has not run since') : '')
      + svCapTip(r.head)
      + '\n\n' + T('Manual switch — /saver on [1-4] (pick a stage) · /saver off · /saver auto · /saver status');
    if(el.className !== 'saver sv2 ' + r.cls) el.className = 'saver sv2 ' + r.cls;   // ⚠same-value writes still mutate
    el.removeAttribute('title');
    // ⚠**Always** two lines — see `svr1`/`svr2` comments below. Do not revert to one line.
    setHtml(el, '<div class=svr1><b>' + esc(r.main) + '</b>' + svChip(r.judge)
      + '<i title="' + esc(tip2) + '">?</i></div>'
      + '<div class=svr2><span>' + esc(r.tag || r.sub) + '</span></div>');
    return;
  }
  // ── Below is saver-stage only (pulse + screen tint). Numbers come from the snapshot when it is fresh.
  const manual = snap ? (r.mode === 'on') : (sv.why === 'manual');
  const th = (sv && sv.th) || 50;
  // ★Stage and cap (2026-09-10). Before there was only "saver mode", so how many agents
  // could be spawned now was nowhere on screen. The hook sets the cap; the screen **copies it as is**.
  // ⚠`sv` may be empty on the snapshot path — every read site branches on `snap`.
  const st = snap ? r.stage : (sv.stage || 0);
  const cap = snap ? r.rec : (sv.cap == null ? null : sv.cap);
  const spct = snap ? r.pct : (sv ? sv.pct : null);
  const capTxt = cap == null ? '' : (cap > 0 ? (T('Subagents at once') + ' ' + U(cap,'#'))
                 : (st >= 4 ? T('Subagents off · wrap up') : T('Subagents off')));
  // ★Goal must stay visible even with a saver stage — the reason for tightening is "over goal" (2026-09-22).
  // ⚠`stage>0` goes through `legacyBadge` and does not use `r.sub`. Fixing only the stage-0 label leaves this empty.
  // ⚠Do not recompute the verdict — only copy the `goal` that `svParts` passed (a key absent from server `sv`).
  // Manual (`on`) is independent of limit/goal, so it is excluded (same rule as `mode !== 'on'` in `svParts`).
  const goalTxt = (!manual && r && r.goal != null) ? (T('Goal') + ' ' + r.goal + '%') : '';
  // ★Verdict and rate shown here too (2026-09-22) — measured to fit one line at 474px. ⚠Full text source of truth is tooltip `head`.
  const rS = (!manual && snap) ? svRate(SV, svLive()) : '';
  const jS = (!manual && snap) ? svJudge(SV) : null;
  const why = (manual ? T('Turned on manually') : (T('5h limit') + ' ' + (spct == null ? '?' : fmtPct(spct))))
              + (rS ? ' · ' + rS : '')
              + (goalTxt ? ' · ' + goalTxt : '')
              + (capTxt ? ' · ' + capTxt : '');
  // ★★The question mark explains **how this state is entered and how it is released**
  // (2026-09-08: the tooltip should explain how saver mode is triggered).
  // Before it only had «list of injected rules» — what to obey was clear, but not why it turned on or when it ends,
  // so the user had to ask every time. Written in order trigger → hold → release.
  // ⚠Threshold uses server-provided `th` (= `SAVER_ON`). Hard-coding 85 here makes the two
  // diverge when the server constant changes (this file's recurring failure shape: "freezing a hypothesis into a constant").
  const tip = (manual
      ? T('You turned this on yourself — it has nothing to do with the limit.') + '\n\n'
      : TV({msg: 'When it turns on — automatically once {th}% or more of the 5h limit is used (now {p}%).', vars: {th: th, p: spct == null ? '?' : spct}}) + '\n\n')
    + T('How it applies — the hook injects rules into the session context.') + '\n'
    + T('· Each prompt injects the saver rules into that turn (UserPromptSubmit hook)\n· Each stage adds rules — stage 1 (50%+) 2 subagents at once · stage 2 (75%+) 1 at once\n  + narrow reads · shorter output · stage 3 (85%+) no subagents + no watchers · suggest /clear\n  · stage 4 (100%) no new work, only finish what is running (credit = really billed)') + '\n'
    + T('When it lifts') + '\n'
    + (manual
        ? T('· A manual switch never lifts on its own — run /saver auto') + '\n'
        : TV({msg: '· Lifts automatically once usage drops below {th}%, and each session then gets one «lifted»\n  notice (silence is not a release signal, so a positive one is sent)\n· If the limit resets during a long turn, the release lands on the next tool call (PostToolUse hook)', vars: {th: th}}) + '\n')
    + '\n' + T('Manual switch — /saver on [1-4] (pick a stage) · /saver off · /saver auto · /saver status')
    + svCapTip(r && r.head) + srcNote;
  if(el.className !== 'saver on') el.className = 'saver on';
  setHtml(el, '<div class=svr1><b>' + esc(st ? TV({msg: 'Saver: level {n}', vars: {n: st}}) : T('Saver') + ' ' + T('mode')) + '</b>' + svChip(jS)
    + '<i title="'+esc(tip)+'">?</i></div>'
    + '<div class=svr2><span>' + esc(why) + '</span></div>');
}
// Concurrency inputs line: the hook's own copy (`SV.capIn`/`capN`, clamped) when present, else burn `cap`. ⚠tpm values are raw tokens/min.
function svCapLine(){
  const fresh = SV && SV.capIn && SV.capN != null;
  // ⚠capN is before the hook's hard stops — show capEff (after them), else 0 at pct >= 85 (CAP_STOP_PCT)
  const hn = !fresh ? null : (SV.capEff != null ? SV.capEff : (SV.pct >= 85 ? 0 : SV.capN));
  const bf = fresh ? null : burnFor(), b = fresh ? SV.capIn : (bf && bf.cap), n = fresh ? hn : (b && b.n);
  if(!b || n == null) return '';
  // ⚠avail_tpm null = not measured (stale burn body) — printing it as 0.0 read as a real zero headroom
  const na = b.avail_tpm == null;
  return T(na ? '{n} at once = headroom not measured · {p}M/min per agent · {r} running'
              : '{n} at once = headroom {a}M/min ÷ {p}M/min per agent − {r} running').replace('{n}', +n)
    .replace('{a}', na ? '' : ((+b.avail_tpm || 0)/1e6).toFixed(1)).replace('{p}', ((+b.per_tpm || 0)/1e6).toFixed(2))
    .replace('{r}', +b.running || 0) + (b.conf === 'low' ? ' · ' + T('estimate') : '');
}
function svCapTip(head){
  const l = svCapLine();
  // ⚠The hook head carries its own inputs line (per-agent rate «d.ddM/») — skip ours even when n differs
  //   (head may show the hook's n, this line capEff), otherwise the same formula reads twice with two numbers.
  return (!l || (head && (head.indexOf(l) >= 0 || /\d\.\d\dM\//.test(head)))) ? '' : '\n\n' + l;
}
// ★Hook-dropped saver/goal snapshot (`state.saverView` ← `_saver_view`) → **screen pieces**.
// ⚠**No verdict is made here** — only copy what the hook already decided (screen and model must not
// say different things · the principle of `buildSaver`). Do **not parse** the `head` string either: the source of truth
// for verdict wording is `saver.py`. Assemble only from structured keys (`until`·`need`·`pct`·`leftMin`·`rec`·`stage`·`mode`)
// and leave the full `head` in the tooltip as is.
// ⚠`pace` is a mode the server's `_saver_state` does not know. So this snapshot, not `s.saver`, is the source of truth.
// ⚠**Displayed in exactly one place: the sidebar badge (`buildSaver`).** On 2026-09-21 it was added twice and removed twice
// — header chip (`.svchip`), full-text row in burndown (`svBlock`/`.burn .svrow`). The latter sat vertically against the badge
// and the same text read twice (duplicate exposure, one was removed). Do not draw it anywhere else.
// ★Label % and minutes left use live values, not `saverView` — that file only updates on prompt submit,
// so it freezes between prompts while only the 5h bar moves, and they diverge (measured 2026-09-22: label 55% vs bar 59%).
// ⚠Stage and recommended count still use the snapshot. Do not replicate the verdict formula here — saver.py is the source of truth.
let SV = null;
function svViewSet(v){ SV = v; }   // other modules set SV through this (owner rule)
// Settings-modal saver switch: raw /saver files (`saverSwitch`) and the effective verdict (`saver`).
let SVSW = null, SVST = null, SVERR = '';
const SV_STALE = 120;   // Verdict older than this = hook has not run for a while (session idle)
// ★The hook puts the verdict level in the snapshot (`saver.py` `pace_lv` → `lv` + `earlyMin` · 2026-09-22,
// levels by degree). The screen **only picks name and color.**
// ⚠Do not compare `need`/`rate` against thresholds again here — screen and injection would diverge.
// ⚠Do not derive the verdict from `rec` (recommended concurrency) — once a stage is set that value flips to a **cap**.
// Fall back to `SV_JREC` only for old snapshots without `lv`.
const SV_JLV = {'2': {nm: 'Way too fast', k: 'fast2'}, '1': {nm: 'Fast', k: 'fast'},
                '0': {nm: 'On pace', k: 'ok'},
                '-1': {nm: 'Slow', k: 'slow'}, '-2': {nm: 'Way too slow', k: 'slow2'}};
const SV_JREC = {'1': {nm: 'Fast', k: 'fast'}, '2': {nm: 'On pace', k: 'ok'},
                 '3': {nm: 'Slow', k: 'slow'}, '4': {nm: 'Way too slow', k: 'slow2'}};
// ★auto also shows «verdict name · multiple» and «required/actual %/min» on the badge (2026-09-22: these
// had been visible before and were missed).
// Before it was only in the `mode==='pace'` branch, so once auto became default it vanished from screen (measurement kept running).
// ⚠Do not invent new wording — only **shorten** `goalSay` from `saver.py` (the hook is the source of truth).
// ★Verdict is one word for «rate» + color (2026-09-22: "on pace" was unclear;
// a badge color reads better). "On pace" did not say relative to what — required and current are shown as numbers
// beside it, so the name need only be fast/ok/slow. Meaning (current/required) is in the chip tooltip.
// ⚠Unless it is one of the 4 known names (+pending), **do not put the sentence in as is** — when the hook could not measure rate, a whole
// paragraph came in and the badge overflowed to three lines (measured 99px).
// ⚠No "Nx" suffix — it is current/required itself, so it would say the same thing twice.
const SV_JTIP = 'Judged by **how many minutes off the target time you land at this rate**.\n'
              + 'On pace within ±10 min · fast/slow up to 30 min · beyond that, way too fast/slow\n'
              + 'The verdict changes only once a bound is passed by 3 min, so it does not flicker at the edge.\n'
              + 'The hook (saver.py) makes the call and adjusts on its own.';
function svJudge(v){
  if(!v) return null;
  // Weekly >= 90% the hook sends lvNm «Weekly near cap» (lv null); warn colour.
  if(v.lvNm === '주간 임박') return {nm: 'Weekly near cap', k: 'fast'};   // ⚠lvNm is the hook's wire value, keep it Korean
  if(v.lv != null) return SV_JLV[String(v.lv)] || null;      // Source of truth — only copy the level the hook produced
  const g = v.goalSay ? String(v.goalSay) : '';   // goalSay is the hook's wire value (saver.py), not UI: the regexes stay Korean
  if(!g) return (v.mode === 'pace' && v.rate == null) ? {nm: 'Pending', k: 'wait'} : null;
  return /크게 뒤처/.test(g) ? SV_JLV['-2']
       : /뒤처/.test(g)      ? SV_JLV['-1']
       : /너무 빠릅/.test(g) ? SV_JLV['2']
       : /빠릅/.test(g)      ? SV_JLV['1']
       : /페이스/.test(g)    ? SV_JLV['0']
       : /못 쟀|판정 없/.test(g) ? {nm: 'Pending', k: 'wait'} : null;
}
// Chip markup — shared by both badge paths (`sv2` · saver stage). ⚠Join only after passing through `esc`.
// The verdict names its reference. «Easy» (no saver stage) beside a bare «Way too slow»(burn vs goal)
//   read as opposites; the long form says which axis it is on.
// ⚠Same wording as the status bar (SB_JNAME, «use») — two names for one state read as two states.
const SV_JLONG = {'Way too fast': 'Burning far above target', 'Fast': 'Above target', 'On pace': 'On target',
                  'Slow': 'Below target', 'Way too slow': 'Far below target'};
const svJName = j => T(SV_JLONG[j.nm] || j.nm);
function svChip(j){
  return j ? ('<em class="svj svj' + j.k + '" title="' + esc(T(SV_JTIP).replace(/\*\*/g, '')) + '">' + esc(svJName(j)) + '</em>') : '';
}
// ★Show all three **with labels** (2026-09-22: average/current/required were ambiguous without labels).
// required = per hour left until goal · current = slope of last 45 min · average = from window start to now. Before there were only
// two, "required/actual", and "actual" did not read as average or recent. ⚠Unit is appended once, at the very end.
function svRate(v, live){
  const f = x => (Math.round(x * 100) / 100).toFixed(2);
  const out = [];
  const nd = (v && v.need != null) ? +v.need : null;
  const cur = (live && live.rate != null) ? +live.rate
            : ((v && v.rate != null) ? +v.rate : null);
  const avg = (live && live.avg != null) ? +live.avg : null;
  if(nd != null) out.push(T('Needed') + ' ' + f(nd));
  if(cur != null) out.push(T('Current') + ' ' + f(cur));
  if(avg != null) out.push(T('Average') + ' ' + f(avg));
  return out.length ? out.join(' · ') + T('%/min') : '';
}
// ★Show «when it runs out at this rate» **compared with** the target time (2026-09-22: goal 18:00 but run-out
// showed 5:46 while the verdict said "ok"). The verdict band (0.8-1.3x) is wide to tolerate
// noise in the 45-min slope — past 1.0x the goal is already missed, yet the chip said "ok", hiding that fact.
// ⚠Do not touch the chip (verdict) — the source of truth is the threshold in `saver.py`. Only **facts** are appended here.
function svOver(v){
  const ov = (v && v.overAt) ? +v.overAt : 0;
  if(!ov) return '';
  const at = +v.at || Math.floor(Date.now()/1000);
  const ref = (v.paceMin != null) ? at + v.paceMin * 60          // pace = target time
            : (v.leftMin != null ? at + v.leftMin * 60 : 0);     // otherwise = reset
  const d = new Date(ov * 1000);
  const hm = ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2);
  // ⚠Minute difference also prefers the hook's value (`earlyMin`) — it must match the chip (level) number.
  const diff = (v.earlyMin != null) ? Math.round(+v.earlyMin)
             : (ref ? Math.round((ref - ov) / 60) : 0);
  // ⚠Do not call a late run-out "headroom" — in goal mode it means **it will not all be used**.
  // ⚠svParts tests this text with a regex for the Korean and English "early" — keep both words if you reword it.
  return TV({msg: 'Runs out at {t}', vars: {t: hm}})
       + (diff >= 2 ? TV({msg: ' ({n}m early)', vars: {n: diff}}) : diff <= -2 ? TV({msg: ' ({n}m late)', vars: {n: -diff}}) : '');
}
// Live % and minutes left — first choice is **exactly the value the 5h bar draws** (`QLAST.q.five_hour`, `poll()` 2.5s).
// No new API. Minutes left re-measure `resets_at` (absolute time) against the current clock so the countdown
// does not look frozen (same ★ rationale as `buildBurn`). Fallback is burndown (`/api/quota/burn`, 30s).
// ⚠If both are missing return `null` and the caller draws snapshot values — the label must not go blank.
function svLive(){
  let pct = null, leftMin = null;
  // ⚠Non-primary main: SV is main's, so live numbers come from main's window (knQ) and BURNM, never the primary's.
  const ma = typeof mainAcct === 'function' && mainAcct(), mq = ma ? knQ('5h') : null;
  const fh = ma ? (mq.miss ? null : mq.w) : QLAST && QLAST.q && QLAST.q.five_hour;
  if(fh && fh.pct != null) pct = +fh.pct;   // raw; printed via fmtPct so status bar and badge agree
  const ms = (fh && fh.resets_at) ? Date.parse(fh.resets_at) : NaN;
  if(!isNaN(ms)) leftMin = Math.max(0, Math.round((ms - Date.now())/60000));
  else if(fh && fh.leftSec != null) leftMin = Math.max(0, Math.round(fh.leftSec/60));
  const bf = ma ? burnFor() : (typeof BURN !== 'undefined' ? BURN : null), c = (bf && bf.ok) ? bf.cur : null;
  if(pct == null && c && c.now_pct != null) pct = +c.now_pct;
  if(leftMin == null && c && c.reset != null)
    leftMin = Math.max(0, Math.round((c.reset - Date.now()/1000)/60));
  // ⚠`rate_pph` is the **slope of the last 45 min** (% per hour) — not the window average. Average is computed here separately
  // (`now_pct / elapsed min`). Not shown under 5 min — the start of a window spikes with noise.
  let rate = null, avg = null;
  if(c && c.rate_pph != null && c.rate_pph > 0) rate = c.rate_pph / 60;
  if(c && c.now_pct != null && c.elapsed > 300) avg = c.now_pct / (c.elapsed / 60);
  return (pct == null && leftMin == null) ? null
       : {pct: pct, leftMin: leftMin, rate: rate, avg: avg};
}
// Kept a pure function — touches no DOM, so node can call it directly (measure wording without restart).
// `live` (= `svLive()`) is an **optional argument** — omitted, it draws from the snapshot only as before.
// ★Show **by logo** which AI did the work (2026-09-22: logo before the working AI,
// in front of the timeline). Offline, so no images or web fonts ⇒ drawn as inline SVG.
// Paths are verbatim from simple-icons 16.32.0 (18 marks, see THIRD_PARTY_NOTICES.md) — do not hand-edit.
// `cx` is the OpenAI mark from simple-icons 9.x (dropped in later releases). ⚠`gk` stays an original glyph: Grok must not borrow X Corp's mark.
// ⚠Color is `currentColor` — fill is set by CSS (`.ailg-*`). Do not hard-code colors here.
const AILG = {
  cc: ['Claude', '<svg viewBox="0 0 24 24" fill="currentColor"><path d="m4.7144 15.9555 4.7174-2.6471.079-.2307-.079-.1275h-.2307l-.7893-.0486-2.6956-.0729-2.3375-.0971-2.2646-.1214-.5707-.1215-.5343-.7042.0546-.3522.4797-.3218.686.0608 1.5179.1032 2.2767.1578 1.6514.0972 2.4468.255h.3886l.0546-.1579-.1336-.0971-.1032-.0972L6.973 9.8356l-2.55-1.6879-1.3356-.9714-.7225-.4918-.3643-.4614-.1578-1.0078.6557-.7225.8803.0607.2246.0607.8925.686 1.9064 1.4754 2.4893 1.8336.3643.3035.1457-.1032.0182-.0728-.164-.2733-1.3539-2.4467-1.445-2.4893-.6435-1.032-.17-.6194c-.0607-.255-.1032-.4674-.1032-.7285L6.287.1335 6.6997 0l.9957.1336.419.3642.6192 1.4147 1.0018 2.2282 1.5543 3.0296.4553.8985.2429.8318.091.255h.1579v-.1457l.1275-1.706.2368-2.0947.2307-2.6957.0789-.7589.3764-.9107.7468-.4918.5828.2793.4797.686-.0668.4433-.2853 1.8517-.5586 2.9021-.3643 1.9429h.2125l.2429-.2429.9835-1.3053 1.6514-2.0643.7286-.8196.85-.9046.5464-.4311h1.0321l.759 1.1293-.34 1.1657-1.0625 1.3478-.8804 1.1414-1.2628 1.7-.7893 1.36.0729.1093.1882-.0183 2.8535-.607 1.5421-.2794 1.8396-.3157.8318.3886.091.3946-.3278.8075-1.967.4857-2.3072.4614-3.4364.8136-.0425.0304.0486.0607 1.5482.1457.6618.0364h1.621l3.0175.2247.7892.522.4736.6376-.079.4857-1.2142.6193-1.6393-.3886-3.825-.9107-1.3113-.3279h-.1822v.1093l1.0929 1.0686 2.0035 1.8092 2.5075 2.3314.1275.5768-.3218.4554-.34-.0486-2.2039-1.6575-.85-.7468-1.9246-1.621h-.1275v.17l.4432.6496 2.3436 3.5214.1214 1.0807-.17.3521-.6071.2125-.6679-.1214-1.3721-1.9246L14.38 17.959l-1.1414-1.9428-.1397.079-.674 7.2552-.3156.3703-.7286.2793-.6071-.4614-.3218-.7468.3218-1.4753.3886-1.9246.3157-1.53.2853-1.9004.17-.6314-.0121-.0425-.1397.0182-1.4328 1.9672-2.1796 2.9446-1.7243 1.8456-.4128.164-.7164-.3704.0667-.6618.4008-.5889 2.386-3.0357 1.4389-1.882.929-1.0868-.0062-.1579h-.0546l-6.3385 4.1164-1.1293.1457-.4857-.4554.0608-.7467.2307-.2429 1.9064-1.3114Z"/></svg>'],
  gm: ['Gemini', '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M11.04 19.32Q12 21.51 12 24q0-2.49.93-4.68.96-2.19 2.58-3.81t3.81-2.55Q21.51 12 24 12q-2.49 0-4.68-.93a12.3 12.3 0 0 1-3.81-2.58 12.3 12.3 0 0 1-2.58-3.81Q12 2.49 12 0q0 2.49-.96 4.68-.93 2.19-2.55 3.81a12.3 12.3 0 0 1-3.81 2.58Q2.49 12 0 12q2.49 0 4.68.96 2.19.93 3.81 2.55t2.55 3.81"/></svg>'],
  cx: ['Codex', '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M22.2819 9.8211a5.9847 5.9847 0 0 0-.5157-4.9108 6.0462 6.0462 0 0 0-6.5098-2.9A6.0651 6.0651 0 0 0 4.9807 4.1818a5.9847 5.9847 0 0 0-3.9977 2.9 6.0462 6.0462 0 0 0 .7427 7.0966 5.98 5.98 0 0 0 .511 4.9107 6.051 6.051 0 0 0 6.5146 2.9001A5.9847 5.9847 0 0 0 13.2599 24a6.0557 6.0557 0 0 0 5.7718-4.2058 5.9894 5.9894 0 0 0 3.9977-2.9001 6.0557 6.0557 0 0 0-.7475-7.0729zm-9.022 12.6081a4.4755 4.4755 0 0 1-2.8764-1.0408l.1419-.0804 4.7783-2.7582a.7948.7948 0 0 0 .3927-.6813v-6.7369l2.02 1.1686a.071.071 0 0 1 .038.052v5.5826a4.504 4.504 0 0 1-4.4945 4.4944zm-9.6607-4.1254a4.4708 4.4708 0 0 1-.5346-3.0137l.142.0852 4.783 2.7582a.7712.7712 0 0 0 .7806 0l5.8428-3.3685v2.3324a.0804.0804 0 0 1-.0332.0615L9.74 19.9502a4.4992 4.4992 0 0 1-6.1408-1.6464zM2.3408 7.8956a4.485 4.485 0 0 1 2.3655-1.9728V11.6a.7664.7664 0 0 0 .3879.6765l5.8144 3.3543-2.0201 1.1685a.0757.0757 0 0 1-.071 0l-4.8303-2.7865A4.504 4.504 0 0 1 2.3408 7.872zm16.5963 3.8558L13.1038 8.364 15.1192 7.2a.0757.0757 0 0 1 .071 0l4.8303 2.7913a4.4944 4.4944 0 0 1-.6765 8.1042v-5.6772a.79.79 0 0 0-.407-.667zm2.0107-3.0231l-.142-.0852-4.7735-2.7818a.7759.7759 0 0 0-.7854 0L9.409 9.2297V6.8974a.0662.0662 0 0 1 .0284-.0615l4.8303-2.7866a4.4992 4.4992 0 0 1 6.6802 4.66zM8.3065 12.863l-2.02-1.1638a.0804.0804 0 0 1-.038-.0567V6.0742a4.4992 4.4992 0 0 1 7.3757-3.4537l-.142.0805L8.704 5.459a.7948.7948 0 0 0-.3927.6813zm1.0976-2.3654l2.602-1.4998 2.6069 1.4998v2.9994l-2.5974 1.4997-2.6067-1.4997Z"/></svg>'],
  cp: ['GitHub Copilot', '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M23.922 16.997C23.061 18.492 18.063 22.02 12 22.02 5.937 22.02.939 18.492.078 16.997A.641.641 0 0 1 0 16.741v-2.869a.883.883 0 0 1 .053-.22c.372-.935 1.347-2.292 2.605-2.656.167-.429.414-1.055.644-1.517a10.098 10.098 0 0 1-.052-1.086c0-1.331.282-2.499 1.132-3.368.397-.406.89-.717 1.474-.952C7.255 2.937 9.248 1.98 11.978 1.98c2.731 0 4.767.957 6.166 2.093.584.235 1.077.546 1.474.952.85.869 1.132 2.037 1.132 3.368 0 .368-.014.733-.052 1.086.23.462.477 1.088.644 1.517 1.258.364 2.233 1.721 2.605 2.656a.841.841 0 0 1 .053.22v2.869a.641.641 0 0 1-.078.256Zm-11.75-5.992h-.344a4.359 4.359 0 0 1-.355.508c-.77.947-1.918 1.492-3.508 1.492-1.725 0-2.989-.359-3.782-1.259a2.137 2.137 0 0 1-.085-.104L4 11.746v6.585c1.435.779 4.514 2.179 8 2.179 3.486 0 6.565-1.4 8-2.179v-6.585l-.098-.104s-.033.045-.085.104c-.793.9-2.057 1.259-3.782 1.259-1.59 0-2.738-.545-3.508-1.492a4.359 4.359 0 0 1-.355-.508Zm2.328 3.25c.549 0 1 .451 1 1v2c0 .549-.451 1-1 1-.549 0-1-.451-1-1v-2c0-.549.451-1 1-1Zm-5 0c.549 0 1 .451 1 1v2c0 .549-.451 1-1 1-.549 0-1-.451-1-1v-2c0-.549.451-1 1-1Zm3.313-6.185c.136 1.057.403 1.913.878 2.497.442.544 1.134.938 2.344.938 1.573 0 2.292-.337 2.657-.751.384-.435.558-1.15.558-2.361 0-1.14-.243-1.847-.705-2.319-.477-.488-1.319-.862-2.824-1.025-1.487-.161-2.192.138-2.533.529-.269.307-.437.808-.438 1.578v.021c0 .265.021.562.063.893Zm-1.626 0c.042-.331.063-.628.063-.894v-.02c-.001-.77-.169-1.271-.438-1.578-.341-.391-1.046-.69-2.533-.529-1.505.163-2.347.537-2.824 1.025-.462.472-.705 1.179-.705 2.319 0 1.211.175 1.926.558 2.361.365.414 1.084.751 2.657.751 1.21 0 1.902-.394 2.344-.938.475-.584.742-1.44.878-2.497Z"/></svg>'],
  cu: ['Cursor', '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M11.503.131 1.891 5.678a.84.84 0 0 0-.42.726v11.188c0 .3.162.575.42.724l9.609 5.55a1 1 0 0 0 .998 0l9.61-5.55a.84.84 0 0 0 .42-.724V6.404a.84.84 0 0 0-.42-.726L12.497.131a1.01 1.01 0 0 0-.996 0M2.657 6.338h18.55c.263 0 .43.287.297.515L12.23 22.918c-.062.107-.229.064-.229-.06V12.335a.59.59 0 0 0-.295-.51l-9.11-5.257c-.109-.063-.064-.23.061-.23"/></svg>'],
  cl: ['Cline', '<svg viewBox="0 0 24 24" fill="currentColor"><path d="m23.365 13.556-1.442-2.895V8.994c0-2.764-2.218-5.002-4.954-5.002h-2.464c.178-.367.276-.779.276-1.213A2.77 2.77 0 0 0 12.018 0a2.77 2.77 0 0 0-2.763 2.779c0 .434.098.846.276 1.213H7.067c-2.736 0-4.954 2.238-4.954 5.002v1.667L.64 13.549c-.149.29-.149.636 0 .927l1.472 2.855v1.667C2.113 21.762 4.33 24 7.067 24h9.902c2.736 0 4.954-2.238 4.954-5.002V17.33l1.44-2.865c.143-.286.143-.622.002-.91m-12.854 2.36a2.27 2.27 0 0 1-2.261 2.273 2.27 2.27 0 0 1-2.261-2.273v-4.042A2.27 2.27 0 0 1 8.249 9.6a2.267 2.267 0 0 1 2.262 2.274zm7.285 0a2.27 2.27 0 0 1-2.26 2.273 2.27 2.27 0 0 1-2.262-2.273v-4.042A2.267 2.267 0 0 1 15.535 9.6a2.267 2.267 0 0 1 2.261 2.274z"/></svg>'],
  wf: ['Windsurf', '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M23.55 5.067c-1.2038-.002-2.1806.973-2.1806 2.1765v4.8676c0 .972-.8035 1.7594-1.7597 1.7594-.568 0-1.1352-.286-1.4718-.7659l-4.9713-7.1003c-.4125-.5896-1.0837-.941-1.8103-.941-1.1334 0-2.1533.9635-2.1533 2.153v4.8957c0 .972-.7969 1.7594-1.7596 1.7594-.57 0-1.1363-.286-1.4728-.7658L.4076 5.1598C.2822 4.9798 0 5.0688 0 5.2882v4.2452c0 .2147.0656.4228.1884.599l5.4748 7.8183c.3234.462.8006.8052 1.3509.9298 1.3771.313 2.6446-.747 2.6446-2.0977v-4.893c0-.972.7875-1.7593 1.7596-1.7593h.003a1.798 1.798 0 0 1 1.4718.7658l4.9723 7.0994c.4135.5905 1.05.941 1.8093.941 1.1587 0 2.1515-.9645 2.1515-2.153v-4.8948c0-.972.7875-1.7594 1.7596-1.7594h.194a.22.22 0 0 0 .2204-.2202v-4.622a.22.22 0 0 0-.2203-.2203Z"/></svg>'],
  wp: ['Warp', '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12.035 2.723h9.253A2.712 2.712 0 0 1 24 5.435v10.529a2.712 2.712 0 0 1-2.712 2.713H8.047Zm-1.681 2.6L6.766 19.677h5.598l-.399 1.6H2.712A2.712 2.712 0 0 1 0 18.565V8.036a2.712 2.712 0 0 1 2.712-2.712Z"/></svg>'],
  tr: ['Trae', '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M24 20.5H3.5V17H0V3.5h24ZM3.5 17h17V7h-17Zm8.5-5-2.5 2.5L7 12l2.5-2.5Zm7 0-2.5 2.5L14 12l2.5-2.5z"/></svg>'],
  zd: ['Zed', '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M2.25 1.5a.75.75 0 0 0-.75.75v16.5H0V2.25A2.25 2.25 0 0 1 2.25 0h20.095c1.002 0 1.504 1.212.795 1.92L10.764 14.298h3.486V12.75h1.5v1.922a1.125 1.125 0 0 1-1.125 1.125H9.264l-2.578 2.578h11.689V9h1.5v9.375a1.5 1.5 0 0 1-1.5 1.5H5.185L2.562 22.5H21.75a.75.75 0 0 0 .75-.75V5.25H24v16.5A2.25 2.25 0 0 1 21.75 24H1.655C.653 24 .151 22.788.86 22.08L13.19 9.75H9.75v1.5h-1.5V9.375A1.125 1.125 0 0 1 9.375 8.25h5.314l2.625-2.625H5.625V15h-1.5V5.625a1.5 1.5 0 0 1 1.5-1.5h13.19L21.438 1.5z"/></svg>'],
  gk: ['Grok(xAI)', '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="1.5" y="1.5" width="21" height="21" rx="5"/><path d="M10.6 9A3.6 4 0 1 0 10.6 15V12.4H8.4M13.6 8v8M18.6 8l-5 4.4 5 3.6"/></svg>'],
  ds: ['DeepSeek', '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M23.748 4.651c-.254-.124-.364.113-.512.233-.051.04-.094.09-.137.137-.372.397-.806.657-1.373.626-.829-.046-1.537.214-2.163.848-.133-.782-.575-1.248-1.247-1.548-.352-.155-.708-.311-.955-.65-.172-.24-.219-.509-.305-.774-.055-.16-.11-.323-.293-.35-.2-.031-.278.136-.356.276-.313.572-.434 1.202-.422 1.84.027 1.436.633 2.58 1.838 3.393.137.094.172.187.129.323-.082.28-.18.553-.266.833-.055.179-.137.218-.328.14a5.5 5.5 0 0 1-1.737-1.179c-.857-.828-1.631-1.743-2.597-2.46a12 12 0 0 0-.689-.47c-.985-.957.13-1.743.387-1.836.27-.098.094-.433-.778-.428-.872.003-1.67.295-2.687.685a3 3 0 0 1-.465.136 9.6 9.6 0 0 0-2.883-.101c-1.885.21-3.39 1.1-4.497 2.622C.082 8.776-.231 10.854.152 13.02c.403 2.284 1.568 4.175 3.36 5.653 1.857 1.533 3.997 2.284 6.438 2.14 1.482-.085 3.132-.284 4.994-1.86.47.234.962.328 1.78.398.629.058 1.235-.031 1.705-.129.735-.155.684-.836.418-.961-2.155-1.004-1.682-.595-2.112-.926 1.095-1.295 2.768-3.598 3.284-6.733.05-.346.115-.834.108-1.114-.004-.171.035-.238.23-.257a4.2 4.2 0 0 0 1.545-.475c1.397-.763 1.96-2.016 2.093-3.517.02-.23-.004-.467-.247-.588M11.58 18.168c-2.088-1.642-3.101-2.183-3.52-2.16-.39.024-.32.472-.234.763.09.288.207.487.371.74.114.167.192.416-.113.603-.673.416-1.842-.14-1.897-.168-1.361-.801-2.5-1.86-3.301-3.306-.775-1.393-1.225-2.888-1.299-4.482-.02-.385.094-.522.477-.592a4.7 4.7 0 0 1 1.53-.038c2.131.311 3.946 1.264 5.467 2.774.868.86 1.525 1.887 2.202 2.89.72 1.066 1.494 2.082 2.48 2.915.348.291.626.513.892.677-.802.09-2.14.109-3.055-.615zm1.001-6.44a.306.306 0 0 1 .415-.287.3.3 0 0 1 .113.074.3.3 0 0 1 .086.214c0 .17-.136.307-.308.307a.303.303 0 0 1-.306-.307m3.11 1.596c-.2.081-.4.151-.591.16a1.25 1.25 0 0 1-.798-.254c-.274-.23-.47-.358-.551-.758a1.7 1.7 0 0 1 .015-.588c.07-.327-.007-.537-.238-.727-.188-.156-.426-.199-.689-.199a.6.6 0 0 1-.254-.078.253.253 0 0 1-.114-.358 1 1 0 0 1 .192-.21c.356-.202.767-.136 1.146.016.352.144.618.408 1.001.782.392.451.462.576.685.915.176.264.336.536.446.848.066.194-.02.353-.25.45"/></svg>'],
  qw: ['Qwen', '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M23.919 14.545 20.817 9.17l1.47-2.544a.56.56 0 0 0 0-.566l-1.633-2.83a.57.57 0 0 0-.49-.283h-6.207L12.487.402a.57.57 0 0 0-.49-.284H8.732a.56.56 0 0 0-.49.284L5.139 5.775h-2.94a.56.56 0 0 0-.49.284L.077 8.887a.56.56 0 0 0 0 .567L3.18 14.83l-1.47 2.545a.56.56 0 0 0 0 .566l1.634 2.83a.57.57 0 0 0 .49.283h6.205l1.47 2.545a.57.57 0 0 0 .49.284h3.266a.57.57 0 0 0 .49-.284l3.104-5.375h2.94a.57.57 0 0 0 .49-.283l1.634-2.828a.55.55 0 0 0-.004-.568M8.733.686l1.634 2.828-1.634 2.828H21.8L20.164 9.17H7.425L5.63 6.06Zm1.306 19.801-6.205-.002 1.634-2.83h3.265L2.201 6.344h3.267q3.182 5.517 6.367 11.032zm10.124-5.66L18.53 12l-6.532 11.315-1.634-2.83c2.129-3.673 4.25-7.351 6.373-11.028h3.592l3.102 5.374z"/></svg>'],
  ki: ['Kimi', '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M21.765.351C22.998.351 24 1.353 24 2.586S22.998 4.82 21.765 4.82h-1.974c-.15 0-.26-.12-.26-.26V2.586A2.237 2.237 0 0 1 21.765.35M9.41 13.388l8.447-8.377c.16-.16.07-.471-.14-.471h-4.55s-.1.02-.14.06l-9.099 9.029c-.14.14-.35.02-.35-.21V4.81c0-.15-.1-.27-.221-.27H.22c-.12 0-.22.12-.22.27v18.57c0 .15.1.27.22.27h3.137c.12 0 .22-.12.22-.27v-3.79c0-.08.03-.16.08-.21l2.826-2.796c.07-.07.16-.08.241-.03l7.546 5.551a8.9 8.9 0 0 0 4.018 1.493c.12.01.23-.11.23-.27V19.76c0-.14-.08-.25-.19-.26a5.8 5.8 0 0 1-2.355-.942l-6.533-4.73c-.14-.09-.15-.32-.03-.441"/></svg>'],
  mi: ['Mistral', '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M17.143 3.429v3.428h-3.429v3.429h-3.428V6.857H6.857V3.43H3.43v13.714H0v3.428h10.286v-3.428H6.857v-3.429h3.429v3.429h3.429v-3.429h3.428v3.429h-3.428v3.428H24v-3.428h-3.43V3.429z"/></svg>'],
  ol: ['Ollama', '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M16.361 10.26a.894.894 0 0 0-.558.47l-.072.148.001.207c0 .193.004.217.059.353.076.193.152.312.291.448.24.238.51.3.872.205a.86.86 0 0 0 .517-.436.752.752 0 0 0 .08-.498c-.064-.453-.33-.782-.724-.897a1.06 1.06 0 0 0-.466 0zm-9.203.005c-.305.096-.533.32-.65.639a1.187 1.187 0 0 0-.06.52c.057.309.31.59.598.667.362.095.632.033.872-.205.14-.136.215-.255.291-.448.055-.136.059-.16.059-.353l.001-.207-.072-.148a.894.894 0 0 0-.565-.472 1.02 1.02 0 0 0-.474.007Zm4.184 2c-.131.071-.223.25-.195.383.031.143.157.288.353.407.105.063.112.072.117.136.004.038-.01.146-.029.243-.02.094-.036.194-.036.222.002.074.07.195.143.253.064.052.076.054.255.059.164.005.198.001.264-.03.169-.082.212-.234.15-.525-.052-.243-.042-.28.087-.355.137-.08.281-.219.324-.314a.365.365 0 0 0-.175-.48.394.394 0 0 0-.181-.033c-.126 0-.207.03-.355.124l-.085.053-.053-.032c-.219-.13-.259-.145-.391-.143a.396.396 0 0 0-.193.032zm.39-2.195c-.373.036-.475.05-.654.086-.291.06-.68.195-.951.328-.94.46-1.589 1.226-1.787 2.114-.04.176-.045.234-.045.53 0 .294.005.357.043.524.264 1.16 1.332 2.017 2.714 2.173.3.033 1.596.033 1.896 0 1.11-.125 2.064-.727 2.493-1.571.114-.226.169-.372.22-.602.039-.167.044-.23.044-.523 0-.297-.005-.355-.045-.531-.288-1.29-1.539-2.304-3.072-2.497a6.873 6.873 0 0 0-.855-.031zm.645.937a3.283 3.283 0 0 1 1.44.514c.223.148.537.458.671.662.166.251.26.508.303.82.02.143.01.251-.043.482-.08.345-.332.705-.672.957a3.115 3.115 0 0 1-.689.348c-.382.122-.632.144-1.525.138-.582-.006-.686-.01-.853-.042-.57-.107-1.022-.334-1.35-.68-.264-.28-.385-.535-.45-.946-.03-.192.025-.509.137-.776.136-.326.488-.73.836-.963.403-.269.934-.46 1.422-.512.187-.02.586-.02.773-.002zm-5.503-11a1.653 1.653 0 0 0-.683.298C5.617.74 5.173 1.666 4.985 2.819c-.07.436-.119 1.04-.119 1.503 0 .544.064 1.24.155 1.721.02.107.031.202.023.208a8.12 8.12 0 0 1-.187.152 5.324 5.324 0 0 0-.949 1.02 5.49 5.49 0 0 0-.94 2.339 6.625 6.625 0 0 0-.023 1.357c.091.78.325 1.438.727 2.04l.13.195-.037.064c-.269.452-.498 1.105-.605 1.732-.084.496-.095.629-.095 1.294 0 .67.009.803.088 1.266.095.555.288 1.143.503 1.534.071.128.243.393.264.407.007.003-.014.067-.046.141a7.405 7.405 0 0 0-.548 1.873c-.062.417-.071.552-.071.991 0 .56.031.832.148 1.279L3.42 24h1.478l-.05-.091c-.297-.552-.325-1.575-.068-2.597.117-.472.25-.819.498-1.296l.148-.29v-.177c0-.165-.003-.184-.057-.293a.915.915 0 0 0-.194-.25 1.74 1.74 0 0 1-.385-.543c-.424-.92-.506-2.286-.208-3.451.124-.486.329-.918.544-1.154a.787.787 0 0 0 .223-.531c0-.195-.07-.355-.224-.522a3.136 3.136 0 0 1-.817-1.729c-.14-.96.114-2.005.69-2.834.563-.814 1.353-1.336 2.237-1.475.199-.033.57-.028.776.01.226.04.367.028.512-.041.179-.085.268-.19.374-.431.093-.215.165-.333.36-.576.234-.29.46-.489.822-.729.413-.27.884-.467 1.352-.561.17-.035.25-.04.569-.04.319 0 .398.005.569.04a4.07 4.07 0 0 1 1.914.997c.117.109.398.457.488.602.034.057.095.177.132.267.105.241.195.346.374.43.14.068.286.082.503.045.343-.058.607-.053.943.016 1.144.23 2.14 1.173 2.581 2.437.385 1.108.276 2.267-.296 3.153-.097.15-.193.27-.333.419-.301.322-.301.722-.001 1.053.493.539.801 1.866.708 3.036-.062.772-.26 1.463-.533 1.854a2.096 2.096 0 0 1-.224.258.916.916 0 0 0-.194.25c-.054.109-.057.128-.057.293v.178l.148.29c.248.476.38.823.498 1.295.253 1.008.231 2.01-.059 2.581a.845.845 0 0 0-.044.098c0 .006.329.009.732.009h.73l.02-.074.036-.134c.019-.076.057-.3.088-.516.029-.217.029-1.016 0-1.258-.11-.875-.295-1.57-.597-2.226-.032-.074-.053-.138-.046-.141.008-.005.057-.074.108-.152.376-.569.607-1.284.724-2.228.031-.26.031-1.378 0-1.628-.083-.645-.182-1.082-.348-1.525a6.083 6.083 0 0 0-.329-.7l-.038-.064.131-.194c.402-.604.636-1.262.727-2.04a6.625 6.625 0 0 0-.024-1.358 5.512 5.512 0 0 0-.939-2.339 5.325 5.325 0 0 0-.95-1.02 8.097 8.097 0 0 1-.186-.152.692.692 0 0 1 .023-.208c.208-1.087.201-2.443-.017-3.503-.19-.924-.535-1.658-.98-2.082-.354-.338-.716-.482-1.15-.455-.996.059-1.8 1.205-2.116 3.01a6.805 6.805 0 0 0-.097.726c0 .036-.007.066-.015.066a.96.96 0 0 1-.149-.078A4.857 4.857 0 0 0 12 3.03c-.832 0-1.687.243-2.456.698a.958.958 0 0 1-.148.078c-.008 0-.015-.03-.015-.066a6.71 6.71 0 0 0-.097-.725C8.997 1.392 8.337.319 7.46.048a2.096 2.096 0 0 0-.585-.041Zm.293 1.402c.248.197.523.759.682 1.388.03.113.06.244.069.292.007.047.026.152.041.233.067.365.098.76.102 1.24l.002.475-.12.175-.118.178h-.278c-.324 0-.646.041-.954.124l-.238.06c-.033.007-.038-.003-.057-.144a8.438 8.438 0 0 1 .016-2.323c.124-.788.413-1.501.696-1.711.067-.05.079-.049.157.013zm9.825-.012c.17.126.358.46.498.888.28.854.36 2.028.212 3.145-.019.14-.024.151-.057.144l-.238-.06a3.693 3.693 0 0 0-.954-.124h-.278l-.119-.178-.119-.175.002-.474c.004-.669.066-1.19.214-1.772.157-.623.434-1.185.68-1.382.078-.062.09-.063.159-.012z"/></svg>'],
  px: ['Perplexity', '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M22.3977 7.0896h-2.3106V.0676l-7.5094 6.3542V.1577h-1.1554v6.1966L4.4904 0v7.0896H1.6023v10.3976h2.8882V24l6.932-6.3591v6.2005h1.1554v-6.0469l6.9318 6.1807v-6.4879h2.8882V7.0896zm-3.4657-4.531v4.531h-5.355l5.355-4.531zm-13.2862.0676 4.8691 4.4634H5.6458V2.6262zM2.7576 16.332V8.245h7.8476l-6.1149 6.1147v1.9723H2.7576zm2.8882 5.0404v-3.8852h.0001v-2.6488l5.7763-5.7764v7.0111l-5.7764 5.2993zm12.7086.0248-5.7766-5.1509V9.0618l5.7766 5.7766v6.5588zm2.8882-5.0652h-1.733v-1.9723L13.3948 8.245h7.8478v8.087z"/></svg>'],
  hf: ['Hugging Face', '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12.025 1.13c-5.77 0-10.449 4.647-10.449 10.378 0 1.112.178 2.181.503 3.185.064-.222.203-.444.416-.577a.96.96 0 0 1 .524-.15c.293 0 .584.124.84.284.278.173.48.408.71.694.226.282.458.611.684.951v-.014c.017-.324.106-.622.264-.874s.403-.487.762-.543c.3-.047.596.06.787.203s.31.313.4.467c.15.257.212.468.233.542.01.026.653 1.552 1.657 2.54.616.605 1.01 1.223 1.082 1.912.055.537-.096 1.059-.38 1.572.637.121 1.294.187 1.967.187.657 0 1.298-.063 1.921-.178-.287-.517-.44-1.041-.384-1.581.07-.69.465-1.307 1.081-1.913 1.004-.987 1.647-2.513 1.657-2.539.021-.074.083-.285.233-.542.09-.154.208-.323.4-.467a1.08 1.08 0 0 1 .787-.203c.359.056.604.29.762.543s.247.55.265.874v.015c.225-.34.457-.67.683-.952.23-.286.432-.52.71-.694.257-.16.547-.284.84-.285a.97.97 0 0 1 .524.151c.228.143.373.388.43.625l.006.04a10.3 10.3 0 0 0 .534-3.273c0-5.731-4.678-10.378-10.449-10.378M8.327 6.583a1.5 1.5 0 0 1 .713.174 1.487 1.487 0 0 1 .617 2.013c-.183.343-.762-.214-1.102-.094-.38.134-.532.914-.917.71a1.487 1.487 0 0 1 .69-2.803m7.486 0a1.487 1.487 0 0 1 .689 2.803c-.385.204-.536-.576-.916-.71-.34-.12-.92.437-1.103.094a1.487 1.487 0 0 1 .617-2.013 1.5 1.5 0 0 1 .713-.174m-10.68 1.55a.96.96 0 1 1 0 1.921.96.96 0 0 1 0-1.92m13.838 0a.96.96 0 1 1 0 1.92.96.96 0 0 1 0-1.92M8.489 11.458c.588.01 1.965 1.157 3.572 1.164 1.607-.007 2.984-1.155 3.572-1.164.196-.003.305.12.305.454 0 .886-.424 2.328-1.563 3.202-.22-.756-1.396-1.366-1.63-1.32q-.011.001-.02.006l-.044.026-.01.008-.03.024q-.018.017-.035.036l-.032.04a1 1 0 0 0-.058.09l-.014.025q-.049.088-.11.19a1 1 0 0 1-.083.116 1.2 1.2 0 0 1-.173.18q-.035.029-.075.058a1.3 1.3 0 0 1-.251-.243 1 1 0 0 1-.076-.107c-.124-.193-.177-.363-.337-.444-.034-.016-.104-.008-.2.022q-.094.03-.216.087-.06.028-.125.063l-.13.074q-.067.04-.136.086a3 3 0 0 0-.135.096 3 3 0 0 0-.26.219 2 2 0 0 0-.12.121 2 2 0 0 0-.106.128l-.002.002a2 2 0 0 0-.09.132l-.001.001a1.2 1.2 0 0 0-.105.212q-.013.036-.024.073c-1.139-.875-1.563-2.317-1.563-3.203 0-.334.109-.457.305-.454m.836 10.354c.824-1.19.766-2.082-.365-3.194-1.13-1.112-1.789-2.738-1.789-2.738s-.246-.945-.806-.858-.97 1.499.202 2.362c1.173.864-.233 1.45-.685.64-.45-.812-1.683-2.896-2.322-3.295s-1.089-.175-.938.647 2.822 2.813 2.562 3.244-1.176-.506-1.176-.506-2.866-2.567-3.49-1.898.473 1.23 2.037 2.16c1.564.932 1.686 1.178 1.464 1.53s-3.675-2.511-4-1.297c-.323 1.214 3.524 1.567 3.287 2.405-.238.839-2.71-1.587-3.216-.642-.506.946 3.49 2.056 3.522 2.064 1.29.33 4.568 1.028 5.713-.624m5.349 0c-.824-1.19-.766-2.082.365-3.194 1.13-1.112 1.789-2.738 1.789-2.738s.246-.945.806-.858.97 1.499-.202 2.362c-1.173.864.233 1.45.685.64.451-.812 1.683-2.896 2.322-3.295s1.089-.175.938.647-2.822 2.813-2.562 3.244 1.176-.506 1.176-.506 2.866-2.567 3.49-1.898-.473 1.23-2.037 2.16c-1.564.932-1.686 1.178-1.464 1.53s3.675-2.511 4-1.297c.323 1.214-3.524 1.567-3.287 2.405.238.839 2.71-1.587 3.216-.642.506.946-3.49 2.056-3.522 2.064-1.29.33-4.568 1.028-5.713-.624"/></svg>'],
  ma: ['Meta AI', '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M10.73.032c-1.333 0-2.032 1.016-2.032 2.285 0 2.223 2.127 4.953 4.318 4.953 1.301 0 2-.953 2-2.254 0-2.254-2.095-4.984-4.286-4.984m8.413 2.984c-1.968 0-3.397 2.73-3.397 4.825 0 1.556.794 3.016 2.254 3.016 2 0 3.365-2.762 3.365-4.794 0-1.523-.762-3.047-2.222-3.047M4.857 4.159c-1.968 0-3.778 1.016-3.778 2.54 0 1.65 2.16 2.793 4.254 2.793 1.873 0 3.778-.92 3.778-2.508 0-1.682-2.159-2.825-4.254-2.825m-.222 6.476C2.413 10.635 0 13.175 0 15.397c0 1.301.825 2.159 2.095 2.159 2.19 0 4.603-2.508 4.603-4.794 0-1.27-.761-2.127-2.063-2.127m16.667.698c-2.223 0-5.016 1.62-5.016 3.651 0 1.238 1.047 2.19 2.698 2.19 2.159 0 5.016-1.587 5.016-3.682 0-1.302-1.08-2.159-2.698-2.159M7.619 16c-1.524 0-2.38 1.746-2.38 3.429 0 2.063 1.269 4.54 3.047 4.54 1.524 0 2.38-1.81 2.38-3.461C10.667 18.57 9.46 16 7.62 16m6.571 1.016c-1.333 0-2.476.667-2.476 2.032 0 2.095 2.667 4.063 4.92 4.063 1.366 0 2.54-.73 2.54-2.063 0-2.032-2.698-4.032-4.984-4.032"/></svg>'],
  or: ['OpenRouter', '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M16.778 1.844v1.919q-.569-.026-1.138-.032-.708-.008-1.415.037c-1.93.126-4.023.728-6.149 2.237-2.911 2.066-2.731 1.95-4.14 2.75-.396.223-1.342.574-2.185.798-.841.225-1.753.333-1.751.333v4.229s.768.108 1.61.333c.842.224 1.789.575 2.185.799 1.41.798 1.228.683 4.14 2.75 2.126 1.509 4.22 2.11 6.148 2.236.88.058 1.716.041 2.555.005v1.918l7.222-4.168-7.222-4.17v2.176c-.86.038-1.611.065-2.278.021-1.364-.09-2.417-.357-3.979-1.465-2.244-1.593-2.866-2.027-3.68-2.508.889-.518 1.449-.906 3.822-2.59 1.56-1.109 2.614-1.377 3.978-1.466.667-.044 1.418-.017 2.278.02v2.176L24 6.014Z"/></svg>'],
};

function aiLogo(p, extra){
  const k = AILG[p] ? p : 'cc';          // Unknown values fall back to Claude — the timeline carries only Claude for now
  return '<i class="ailg ailg-'+k+'" title="'+esc(T(AILG[k][0])+(extra||''))+'">'+AILG[k][1]+'</i>';
}
function svParts(v, nowS, live){
  if(!v || typeof v !== 'object') return null;           // No snapshot, draw nothing
  const now = nowS || Math.floor(Date.now()/1000);
  const at = +v.at || 0;
  const old = at > 0 && (now - at) > SV_STALE;
  const mode = (v.mode === 'pace' || v.mode === 'off' || v.mode === 'on') ? v.mode : 'auto';
  const pct = (v.pct == null) ? null : v.pct;            // null drops **only that piece**
  // ★Only the printed numbers are swapped for live values (★ rationale above). ⚠**Branch on the snapshot (`pct`)** —
  // `pct == null` (= limit unknown) is a «verdict» that the hook could not read it, so do not overturn it with live values.
  const shown = (live && live.pct != null && pct != null) ? live.pct : pct;
  const lmin = (live && live.leftMin != null) ? live.leftMin
             : (v.leftMin == null ? null : v.leftMin);
  const rec = (v.rec == null) ? null : +v.rec;
  // ★Goal burn rate (`goal`) is also shown in the label — auto judges on the goal axis, but it was not on screen
  // (2026-09-22, no "goal 100%" label was visible).
  // ⚠If the key is missing, omit silently. Do not recompute the verdict here — saver.py is the source of truth.
  // ⚠Do not put `goalSay`/`proj` in the label — the subtitle overflows to two lines and breaks the badge layout.
  // That text is already in the tooltip (full `head`).
  const goal = (v.goal == null) ? null : +v.goal;
  // ⚠`stage` is the saver «stage» — `body.svon` (whole-screen tint) branches on it. `off` is 0.
  // ★Do not force `pace` to 0 either (reverted 2026-09-21). In goal mode the hook changes the denominator
  // to «until goal» and emits a stage **again** (`stage_of(p, pace_min, floor=False)` in `saver.py`)
  // — burning faster than goal sets a stage in pace too. Forcing 0 means the model tightens while the screen says
  // it does not. ⚠Instead «which markup to draw» is decided separately (`legacyBadge` in `buildSaver`).
  const stage = (mode === 'off') ? 0
              : (+v.stage || (mode === 'on' ? 3 : 0));   // Default stage for manual on is 3, same as the hook
  let cls, main, tag = '', sub = [], judge = null;
  if(mode === 'pace'){
    // Screen shows only three: **target time · required rate · verdict**. Directives like "run independent work in parallel …"
    // are addressed to the session, so they go to the second line/tooltip.
    cls = 'svpace';
    // ⚠Required rate is not put in `main` — shown as one «required·current·average» group like the headroom/saver badges
    // (2026-09-22). Only the target time is the title.
    main = T('Goal') + ' ' + (v.until || '?') + (v.need == null ? ' · ' + T('spend 100%') : '');
    // ⚠In goal mode, once a stage is set **that statement comes first** — "N concurrent recommended" (advice) and "up to N" (cap)
    // are different statements, and the badge's single `tag` slot goes to the binding one.
    // ⚠⚠The **meaning of `rec` flips with a stage** — `view_snap` in `saver.py` checks `elif stage: rec =
    // CAP.get(stage)` **before** the pace branch. So with a stage, `rec` is not the pace verdict
    // (`pace_rec`) but the **cap**. Hence with a stage we do not look up `SV_JREC` —
    // doing so would read the cap number as a verdict name and say something wrong.
    tag = stage ? (TV({msg: 'Saver: level {n}', vars: {n: stage}}) + ' · ' + (rec ? T('At once') + ' ' + U(rec,' max') : T('Subagents off')))
                : '';
    // ★The verdict is a **color chip** instead of a name (same word, same color as headroom/saver badges). Level comes from the snapshot `lv`
    // — ⚠with a stage, `rec` is a **cap**, not a verdict, so it is not used as fallback either (⚠⚠ above).
    if(!stage) judge = svJudge(v) || SV_JREC[String(rec)] || null;
    if(pct != null) sub.push(T('Now') + ' ' + fmtPct(shown));
    const ov = svOver(v);
    if(ov) sub.push(ov); else if(lmin != null) sub.push(U(lmin,'m left'));
    const rp = svRate(v, live);
    if(rp) sub.push(rp);
  }else if(mode === 'off'){
    cls = 'svoff'; main = T('Saver off'); sub.push(T('Also blocks auto-activation'));
  }else if(stage){
    cls = stage >= 3 ? 'svhot' : 'svwarn';
    main = TV({msg: 'Saver: level {n}', vars: {n: stage}}) + (pct == null ? '' : ' · ' + fmtPct(shown));
    if(mode !== 'on'){ const rt = svRate(v, live);
      judge = svJudge(v); if(rt) sub.push(rt); if(goal != null) sub.push(T('Goal') + ' ' + goal + '%'); }
    if(rec != null) sub.push(rec ? T('At once') + ' ' + U(rec,' max') : T('Subagents off'));
  }else if(pct == null){
    // ⚠auto without `pct` = **limit could not be read**, not headroom. Printing "headroom" would be a lie.
    cls = 'svoff'; main = T('Limit unknown'); sub.push(T('No response from Sidereus'));
  }else{
    // This state only means "no saver stage"; the % is already in the stat panels and the 5h bar.
    cls = 'svfree'; main = T('No throttle');
    const rf = svRate(v, live);
    judge = svJudge(v);
    const ovf = svOver(v);
    if(ovf && /일찍| early/.test(ovf)) sub.push(ovf);
    if(rf) sub.push(rf);
    if(goal != null) sub.push(T('Goal') + ' ' + goal + '%');
    // ⚠`end` = the hook's live brake (`brake_of` in `saver.py`: projected exhaustion >10 min before reset, or a
    // hard stop) — not a fixed last-minutes window. While it is set, `rec` is a brake value, not a verdict:
    // printing it as "1 concurrent recommended" would read as «behind schedule, yet spawn only one».
    // ★Recommended concurrency is not shown (2026-09-22: not needed; pace mode adjusts on its own).
    // ⚠A stage «cap» is different — that stays above.
    if(v.end) sub.push(T('Wrap up'));
  }
  const ago = old ? TV({msg: 'judged {t}', vars: {t: agoAt(at)}}) : '';
  if(old) sub.push(ago);          // Stale is not removed: dimmed + keep when the verdict was made
  return {cls: cls + (old ? ' svold' : ''), main: main, tag: tag, sub: sub.join(' · '), judge: judge,
          old: old, at: at, ago: ago, stage: stage, mode: mode, pct: shown, rec: rec, goal: goal,
          head: v.head || ''};
}
