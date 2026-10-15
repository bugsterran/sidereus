// Static i18n guard (scripts/check.sh --fast). A missing ko entry falls back to English silently, so this is the check.
//   node scripts/i18n_check.mjs [--stage=A|B|D]   (default A; each stage adds the rules that hold once that stage landed)
//   A: every T() literal resolves (Korean = an old key, English = an I18N.ko entry), T(s, ctx) has 's|ctx', no duplicate ko keys,
//      U() units are in UNIT_EN (Korean) / UNIT_KO (English).
//   B: + no Korean in T()/U() literals outside dictionaries (an English source text that itself holds Korean is allowed).
//   D: + no bridge left (I18N.en, I18N._legacy, i18nBridge, TRX_EN, HL_EN, UNIT_EN).
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { ROOT, JD, HANGUL, isDict, lex, calls, dictBlocks, loadI18n, tLiterals } from './i18n_flip.mjs'

const STAGES = 'ABD'
const arg = process.argv.find(a => a.startsWith('--stage='))
const stage = (arg ? arg.slice(8) : 'A').toUpperCase()
if (!STAGES.includes(stage) || stage.length !== 1) { console.log('i18n_check: unknown stage ' + stage); process.exit(2) }
const at = s => STAGES.indexOf(stage) >= STAGES.indexOf(s)
const own = (o, k) => Object.prototype.hasOwnProperty.call(o, k)
const errs = []
const files = [['web/app-head.js', join(ROOT, 'web', 'app-head.js')], ...readdirSync(JD).filter(f => f.endsWith('.js')).sort().map(f => ['web/js/' + f, join(JD, f)])]
let sb
try { sb = loadI18n() } catch (e) { console.log('i18n_check: dictionaries do not load: ' + e.message); process.exit(1) }
const KO = sb.I18N.ko, LEG = sb.I18N.en || {}, UK = sb.UNIT_KO || {}, UE = sb.UNIT_EN || {}

// duplicate ko keys, source level (Object.assign / a literal would keep the last one silently)
const seen = {}
let nko = 0
for (const [rel, p] of files) {
  const src = readFileSync(p, 'utf8')
  for (const b of dictBlocks(src)) {
    if (b.lang !== 'ko') continue
    const toks = lex(src.slice(b.open, b.end)); let d = 0
    for (let i = 0; i < toks.length; i++) {
      const t = toks[i]
      if (t.k === 'p') { if ('([{'.includes(t.v)) d++; else if (')]}'.includes(t.v)) d--; continue }
      if (d !== 1 || t.k !== 's' || !(toks[i + 1] && toks[i + 1].v === ':') || !(toks[i - 1] && (toks[i - 1].v === '{' || toks[i - 1].v === ','))) continue
      nko++
      const v = toks[i + 2]
      if (!v || v.k !== 's' || !v.v) errs.push(rel + ': ko entry ' + JSON.stringify(t.v) + ' has no Korean string value')
      if (seen[t.v]) errs.push(rel + ': duplicate ko key ' + JSON.stringify(t.v) + ' (first in ' + seen[t.v] + ')'); else seen[t.v] = rel
    }
  }
}
let nlit = 0
for (const [rel, p] of files) {
  const src = readFileSync(p, 'utf8'), dict = isDict(p)
  for (const l of tLiterals(src, rel)) {
    nlit++
    const where = rel + ': T(' + JSON.stringify(l.v).slice(0, 80) + (l.ctx ? ', ' + JSON.stringify(l.ctx) : '') + ')'
    if (l.ctx) { if (!own(KO, l.v + '|' + l.ctx)) errs.push(where + ' has no ko entry ' + JSON.stringify(l.v + '|' + l.ctx)); continue }
    if (HANGUL.test(l.v)) {
      if (own(KO, l.v)) continue   // English source text that quotes Korean verbatim
      if (at('B') && !dict) errs.push(where + ' is Korean — pass the English text (scripts/i18n_flip.mjs)')
      else if (!own(LEG, l.v)) errs.push(where + ' has no dictionary entry')
    } else if (/[A-Za-z]/.test(l.v) && !own(KO, l.v)) errs.push(where + ' has no ko entry')
  }
  const toks = lex(src)
  for (const c of calls(toks, 'U')) {
    const r = c.args[1]; if (!r || r[1] - r[0] !== 1 || toks[r[0]].k !== 's') continue
    const u = toks[r[0]].v, cr = c.args[2], cx = cr && cr[1] - cr[0] === 1 && toks[cr[0]].k === 's' ? toks[cr[0]].v : null
    const where = rel + ': U(…, ' + JSON.stringify(u) + (cx != null ? ', ' + JSON.stringify(cx) : '') + ')'
    if (HANGUL.test(u)) {
      if (at('B')) errs.push(where + ' has a Korean unit — use the English unit + UNIT_KO')
      else if (!own(UE, u) && cx == null) errs.push(where + ' Korean unit not in UNIT_EN')
    } else if (!(cx != null ? own(UK, u + '|' + cx) : own(UK, u))) errs.push(where + ' unit not in UNIT_KO')
  }
  if (at('D')) {
    const m = src.match(/\bI18N\.(en|_legacy)\b|\bi18nBridge\b|\bTRX_EN\b|\bHL_EN\b|\bUNIT_EN\b/g)
    if (m) errs.push(rel + ': bridge still referenced (' + [...new Set(m)].join(', ') + ')')
  }
}
for (const e of errs.slice(0, 40)) console.log('FAIL ' + e)
if (errs.length > 40) console.log('FAIL ... ' + (errs.length - 40) + ' more')
console.log('i18n_check: ' + (errs.length ? errs.length + ' problem(s)' : 'ok') + ' (stage ' + stage + ') · ' + nlit + ' T literals · ' + nko + ' ko keys')
process.exit(errs.length ? 1 : 0)
