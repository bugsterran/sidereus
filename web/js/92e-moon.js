// Rail mark (#dot) = today's moon in the style of Galileo's Sidereus Nuncius plates: rough terminator, maria on the lit part, a lit peak.
// ⚠Mean synodic month from one reference new moon: off by up to about 0.75 day near a real syzygy (no perturbation terms).
// ⚠Northern-hemisphere view: waxing = lit on the right.
const MOON_P = 29.530588853, MOON_EPOCH = Date.UTC(2000, 0, 6, 18, 14);
const MOON_NAMES = ['New moon', 'Waxing crescent', 'First quarter', 'Waxing gibbous', 'Full moon', 'Waning gibbous', 'Last quarter', 'Waning crescent'];
// Fixed terminator jitter (bottom to top): the same offsets every paint, so the edge never flickers as the age moves.
const MOON_JIT = [0, .55, -.8, .35, .9, -.6, .2, -.95, .7, -.3, .6, -.5, 0];
function moonPhase(ms){
  const age = (((ms - MOON_EPOCH) / 864e5) % MOON_P + MOON_P) % MOON_P;   // ⚠JS % keeps the sign: dates before the epoch need the +P wrap
  const idx = Math.round(age / MOON_P * 8) % 8;
  return {age, k: (1 - Math.cos(2 * Math.PI * age / MOON_P)) / 2, idx, name: MOON_NAMES[idx], waxing: age < MOON_P / 2};
}
// Lit-part path: limb arc on the lit side, then the terminator (half-ellipse rx = r|cos θ|) back up. rough = jitter amplitude in user units (0 = clean ellipse).
function moonPath(age, cx, cy, r, rough){
  const c = Math.cos(2 * Math.PI * age / MOON_P), k = (1 - c) / 2, wax = age < MOON_P / 2, f2 = n => +n.toFixed(2);
  if(k < .01) return '';
  if(k > .99) return `M${cx},${cy - r}A${r} ${r} 0 1 1 ${cx},${cy + r}A${r} ${r} 0 1 1 ${cx},${cy - r}Z`;
  const rx = c > 0 ? Math.min(r * c, r - 2.2) : -r * c;   // crescent clamp is cosmetic: a 1-day moon still shows a ~2px sliver at rail size
  const bulgeR = (c > 0) === wax, head = `M${cx},${cy - r}A${r} ${r} 0 0 ${wax ? 1 : 0} ${cx},${cy + r}`;
  if(!rough) return head + `A${f2(rx)} ${r} 0 0 ${bulgeR ? 0 : 1} ${cx},${cy - r}Z`;
  const n = MOON_JIT.length - 1, pts = [];
  for(let i = 1; i <= n; i++){
    const f = Math.PI * i / n, env = Math.sin(f), y = cy + r * Math.cos(f), lim = Math.sqrt(Math.max(0, r * r - (y - cy) * (y - cy)));
    const dx = Math.max(-lim, Math.min(lim, (bulgeR ? 1 : -1) * rx * env + MOON_JIT[i] * rough * env));   // jitter never leaves the disc
    pts.push(f2(cx + dx) + ',' + f2(y));
  }
  return head + 'L' + pts.join('L') + 'Z';
}
// Sunlit summit just past the terminator on the dark side, crescent to gibbous only; null when it would not fit inside the disc.
function moonPeak(age, cx, cy, r){
  const c = Math.cos(2 * Math.PI * age / MOON_P), k = (1 - c) / 2, wax = age < MOON_P / 2;
  if(k <= .06 || k >= .94) return null;
  const rx = c > 0 ? Math.min(r * c, r - 2.2) : -r * c, y = cy - 1.4;
  const x = cx + ((c > 0) === wax ? 1 : -1) * rx * Math.sqrt(1 - ((y - cy) / r) ** 2) + (wax ? -1.8 : 1.8);
  return Math.hypot(x - cx, y - cy) < r - 1.6 ? [+x.toFixed(2), y] : null;
}
function moonTip(ph){
  return T(ph.name) + ' · ' + T('day {n} · {p}% lit').replace('{n}', Math.floor(ph.age) + 1).replace('{p}', Math.round(ph.k * 100));
}
function moonTitle(ph){ return T("Today's moon") + ': ' + moonTip(ph); }
// Default mark = one full lunation per hour (local clock: :00 new, :15 first quarter, :30 full); one minute is about half a day of moon.
function moonHourAge(ms){ const t = new Date(ms); return (t.getMinutes() * 60 + t.getSeconds()) / 3600 * MOON_P; }
function moonReal(){ try{ return UIS.getItem('mbMoonReal') === '1'; }catch(e){ return false; } }   // Preferences › «Moon mark»
function moonPaint(){
  const el = document.getElementById('dot');
  if(!el) return;
  // ⚠The drawn phase may be the hourly cycle; the tooltip always describes the real moon.
  const now = Date.now(), real = moonPhase(now), age = moonReal() ? real.age : moonHourAge(now);
  const ph = {age, k: (1 - Math.cos(2 * Math.PI * age / MOON_P)) / 2}, d = moonPath(age, 16, 16, 12, .85), pk = moonPeak(age, 16, 16, 12);
  el.setAttribute('viewBox', '2 2 28 28');   // crop the empty margin: the disc fills the 28px rail slot
  const es = ph.k < .15;   // new and thin-crescent days: the night side glows with earthshine and shows its maria
  el.querySelectorAll('path.bmlit').forEach(p => p.setAttribute('d', d));
  const clip = el.querySelector('#bmclip path');   // maria follow the lit part; in earthshine they follow the night side (disc minus lit, evenodd)
  if(clip){ clip.setAttribute('d', es ? 'M16,4A12 12 0 1 1 16,28A12 12 0 1 1 16,4Z' + d : d); clip.setAttribute('clip-rule', es ? 'evenodd' : 'nonzero'); }
  const dot = el.querySelector('.bmpk');
  if(dot){ dot.style.display = pk ? '' : 'none'; if(pk){ dot.setAttribute('cx', pk[0]); dot.setAttribute('cy', pk[1]); } }
  el.classList.toggle('es', es);   // honest: no lit sliver is added; k < .01 draws no lit part at all
  const t = el.querySelector('title');
  if(t) t.textContent = moonTitle(real);
}
moonPaint();
setTimeout(() => { moonPaint(); setInterval(moonPaint, 60e3); }, 60e3 - Date.now() % 60e3);   // minute-aligned
document.addEventListener('visibilitychange', () => { if(!document.hidden) moonPaint(); });
// Repaint on hover too: the tooltip then follows a language switch without the settings code knowing about the mark.
if(document.getElementById('dot')) document.getElementById('dot').addEventListener('mouseenter', moonPaint);
