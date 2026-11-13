// ── Structure «Architecture» security window: syft SBOM row text and the run summary (checks.security.summary) (84l) ──
// ⚠Package names, versions and the DB time are tool output: substituted after T() and esc'd, never through T().
// Pure: note texts of a syft row, any status (a skipped «no packages» row still says why); [] for other tools.
function archChkSbomNotes(t){
  if(!t || String(t.id) !== 'syft') return [];
  const u = t.unresolved, un = typeof u === 'number' && Number.isInteger(u) && u >= 0 ? String(u) : '?';   // ⚠unknown count reads «?», never 0
  const nt = (Array.isArray(t.notes) ? t.notes : []).filter((k, i, a) => (k === 'mvn-offline' || k === 'gradle-no-lock' || k === 'mvn-unresolved') && a.indexOf(k) === i)
    .map(k => k === 'mvn-offline' ? T('Maven versions not resolved (offline)') : k === 'mvn-unresolved' ? T('{n} Maven versions not resolved').replace('{n}', () => un) : T('transitive dependencies not resolved'));
  return nt;
}
// Pure: syft status «ran · N components» (+ note texts) for an ok syft row with a natural `components`; '' otherwise (archChkStat falls back).
function archChkSbomStat(t){
  const n = t && t.components;
  if(!t || String(t.id) !== 'syft' || t.status !== 'ok' || typeof n !== 'number' || !Number.isInteger(n) || n < 0) return '';
  return [T('ran · {n} components').replace('{n}', () => String(n))].concat(archChkSbomNotes(t)).join(' · ');
}
// Pure: "YYYY-MM-DD HH:MM" (local) of an ISO-Z time, or '' — an absent or malformed time shows nothing, never the epoch.
function archChkDbAt(s){
  if(typeof s !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,9})?)?Z$/.test(s)) return '';
  const d = new Date(s.replace(/(\.\d{3})\d+Z$/, '$1Z')), p = v => String(v).padStart(2, '0');
  return isNaN(d.getTime()) ? '' : d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
}
// Pure: run summary at the top of the issues window — category counts, severity totals, grype DB time, «upgrade X to Y resolves N» lines.
//   fc = fixes group closed (S.sfc). ⚠No summary (old results) renders nothing; a missing count shows «?», never 0.
function archChkSummaryHtml(sec, fc){
  const s = sec && sec.summary, ob = o => o && typeof o === 'object' && !Array.isArray(o) ? o : null;
  if(!ob(s)) return '';
  const nat = v => typeof v === 'number' && Number.isInteger(v) && v >= 0 ? String(v) : '?', c = ob(s.cat) || {}, v = ob(s.sev) || {};
  const cat = T('CVE {c} · SAST {s} · Secret {k} · Config {g}').replace(/\{([cskg])\}/g, (m, k) => nat(c[{ c: 'cve', s: 'sast', k: 'secret', g: 'config' }[k]]));
  const sev = ['critical', 'high', 'medium', 'low'].map(l => archChkLvLbl(l) + ' ' + nat(v[l])).join(' · '), db = archChkDbAt(s.db_built);
  let h = '<div class="archckst cksum" role=status>' + esc([cat, sev].concat(db ? [T('Vulnerability DB built {t}').replace('{t}', () => db)] : []).join(' | ')) + '</div>';
  const str = x => typeof x === 'string' && x.trim() ? x.trim().slice(0, 200) : '';
  const fx = (Array.isArray(s.fixes) ? s.fixes : []).filter(f => ob(f) && str(f.pkg) && str(f.to) && Number.isInteger(f.n) && f.n > 0).slice(0, 20);
  if(!fx.length) return h;
  // one pass over the template: a package name holding «{v}» stays literal
  const line = f => T('upgrade {p} to {v} resolves {n}').replace(/\{([pvn])\}/g, (m, k) => k === 'p' ? str(f.pkg) + (str(f.ver) ? ' ' + str(f.ver) : '') : k === 'v' ? str(f.to) : String(f.n));
  // fixes_more = groups the server cut past its cap; shown so a capped list never reads as complete
  const more = Number.isInteger(s.fixes_more) && s.fixes_more > 0 ? '<div class=archckst>' + esc(T('+{n} more', 'fixes').replace('{n}', () => String(s.fixes_more))) + '</div>' : '';
  return h + '<details class="ckunz cksfix" data-cksfix' + (fc ? '' : ' open') + '><summary>' + esc(T('Upgrades {n}').replace('{n}', () => String(fx.length))) + '</summary><ol class="archckl cksfl">'
    + fx.map(f => { const lv = archChkLv(f.sev); return '<li class="' + lv + '"><b class=archcks>' + esc(archChkLvLbl(lv)) + '</b><span>' + esc(line(f)) + '</span></li>'; }).join('') + '</ol>' + more + '</details>';
}
