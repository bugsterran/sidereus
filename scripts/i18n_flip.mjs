// Rewrites Korean UI literals to their English source: T('<ko>') -> T('<en>'[, '<ctx>']) and U(n, '<ko unit>'[, '<en>'])
// -> U(n, '<en unit>'[, '<ctx>']). The map is the inverse of I18N.ko (web/js/05-i18n.js, 05a, 06-i18n-*), so a literal
// flips only when its exact value is an old Korean key; everything else is listed for manual work. No deps.
//   node scripts/i18n_flip.mjs [--write] [--all-literals] [files...]   (default: web/app-head.js + web/js/*.js minus dictionaries)
//   --all-literals  also flips any other string literal equal to an old key (⚠comparisons and dictionary blocks are never touched; never run it on files holding wire strings: mailbox tags, server values, request bodies)
// Also the shared library for scripts/i18n_check.mjs and tests/test_i18n_flip.py (exports below).
import { readFileSync, writeFileSync, readdirSync } from 'node:fs'
import { join, dirname, basename } from 'node:path'
import { fileURLToPath } from 'node:url'
import vm from 'node:vm'

export const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
export const JD = join(ROOT, 'web', 'js')
export const HANGUL = /[가-힣]/
export const isDict = f => /^0(5|6)[a-z0-9-]*\.js$/.test(basename(f)) && /i18n/.test(f)
const own = (o, k) => Object.prototype.hasOwnProperty.call(o, k)

// ---- lexer: strings (with value), template parts, identifiers, punctuation; comments and regex literals skipped
function readStr(src, i) {
  const q = src[i]; let j = i + 1, v = ''
  const esc = { n: '\n', t: '\t', r: '\r', b: '\b', f: '\f', v: '\v', 0: '\0' }
  while (j < src.length && src[j] !== q) {
    if (src[j] === '\\') {
      const e = src[j + 1]
      if (e === 'u' && src[j + 2] === '{') { const k = src.indexOf('}', j); v += String.fromCodePoint(parseInt(src.slice(j + 3, k), 16)); j = k + 1; continue }
      if (e === 'u') { v += String.fromCharCode(parseInt(src.slice(j + 2, j + 6), 16)); j += 6; continue }
      if (e === 'x') { v += String.fromCharCode(parseInt(src.slice(j + 2, j + 4), 16)); j += 4; continue }
      if (e === '\n') { j += 2; continue }
      v += own(esc, e) ? esc[e] : e; j += 2; continue
    }
    v += src[j++]
  }
  return { v, end: j + 1 }
}
const REGEX_AFTER = new Set(['(', ',', '=', ':', '[', '!', '&', '|', '?', '{', '}', ';', '+', '-', '*', '%', '<', '>', '~', '^', 'return', 'typeof', 'case', 'in', 'of', 'void', 'delete', 'new', '=>'])
export function lex(src) {
  const toks = []
  const prevSig = () => { const t = toks[toks.length - 1]; return t ? (t.k === 'p' ? t.v : t.k === 'id' ? t.v : 'x') : '(' }
  function code(i, stopAtBrace) {
    let depth = 0
    while (i < src.length) {
      const c = src[i]
      if (/\s/.test(c)) { i++; continue }
      if (c === '/' && src[i + 1] === '/') { const n = src.indexOf('\n', i); i = n < 0 ? src.length : n; continue }
      if (c === '/' && src[i + 1] === '*') { i = src.indexOf('*/', i + 2) + 2; continue }
      if (c === "'" || c === '"') { const r = readStr(src, i); toks.push({ k: 's', v: r.v, s: i, e: r.end, q: c }); i = r.end; continue }
      if (c === '`') { i = tpl(i); continue }
      if (c === '/' && REGEX_AFTER.has(prevSig())) {
        let j = i + 1, cls = false
        while (j < src.length) { const d = src[j]; if (d === '\\') { j += 2; continue } if (d === '[') cls = true; else if (d === ']') cls = false; else if (d === '/' && !cls) break; else if (d === '\n') break; j++ }
        j++; while (/[a-z]/.test(src[j] || '')) j++
        toks.push({ k: 're', s: i, e: j }); i = j; continue
      }
      if (/[A-Za-z_$]/.test(c)) { const m = /^[\w$]+/.exec(src.slice(i, i + 200)); toks.push({ k: 'id', v: m[0], s: i, e: i + m[0].length }); i += m[0].length; continue }
      if (/[0-9]/.test(c)) { const m = /^[\w.]+/.exec(src.slice(i, i + 100)); toks.push({ k: 'n', s: i, e: i + m[0].length }); i += m[0].length; continue }
      if (c === '=' && src[i + 1] === '>') { toks.push({ k: 'p', v: '=>', s: i, e: i + 2 }); i += 2; continue }
      if (stopAtBrace) { if (c === '{') depth++; else if (c === '}') { if (!depth) return i + 1; depth-- } }
      toks.push({ k: 'p', v: c, s: i, e: i + 1 }); i++
    }
    return i
  }
  function tpl(i) {   // template: no ${} -> one string token; else the inner code is lexed, the template itself is not a candidate
    let j = i + 1, v = '', plain = true
    while (j < src.length && src[j] !== '`') {
      if (src[j] === '\\') { v += src[j + 1] === 'n' ? '\n' : src[j + 1]; j += 2; continue }
      if (src[j] === '$' && src[j + 1] === '{') { plain = false; toks.push({ k: 'p', v: '`', s: j, e: j }); j = code(j + 2, true); continue }
      v += src[j++]
    }
    if (plain) toks.push({ k: 's', v, s: i, e: j + 1, q: '`' })
    else toks.push({ k: 'p', v: '`', s: j, e: j + 1 }, { k: 'tpl', v, s: i, e: j + 1 })   // static text of an interpolated template
    return j + 1
  }
  code(0, false)
  return toks
}
// Calls `name(` with argument token ranges: [{at, open, close, args: [[tokIdxFrom, tokIdxTo)]}]
export function calls(toks, name) {
  const out = []
  for (let i = 0; i < toks.length - 1; i++) {
    const t = toks[i], p = toks[i - 1]
    if (t.k !== 'id' || t.v !== name || toks[i + 1].v !== '(' || toks[i + 1].k !== 'p' || (p && p.k === 'p' && p.v === '.')) continue
    if (p && p.k === 'id' && p.v === 'function') continue
    let d = 0, a = i + 2; const args = []
    for (let j = i + 2; j < toks.length; j++) {
      const x = toks[j]; if (x.k !== 'p') continue
      if ('([{'.includes(x.v)) d++
      else if (')]}'.includes(x.v)) { if (!d) { if (j > a) args.push([a, j]); out.push({ at: i, close: j, args }); break } d-- }
      else if (x.v === ',' && !d) { args.push([a, j]); a = j + 1 }
    }
  }
  return out
}
const litArg = (toks, r) => r && r[1] - r[0] === 1 && toks[r[0]].k === 's' ? toks[r[0]] : null
// T('<literal>'[, '<ctx>']) calls: [{f, tok, ctx, v}]
export function tLiterals(src, f) {
  const toks = lex(src), out = []
  for (const c of calls(toks, 'T')) { const a = litArg(toks, c.args[0]); if (!a) continue
    const cx = litArg(toks, c.args[1]); out.push({ f, tok: a, v: a.v, ctx: cx ? cx.v : null, nargs: c.args.length }) }
  return out
}

// ---- dictionaries: run 05/05a/06-i18n-* like the page does, then every other file's Object.assign(I18N.<lang>, {...}) block
function blockEnd(src, open) {   // index after the '}' that closes the '{' at src[open]
  const toks = lex(src.slice(open)); let d = 0
  for (const t of toks) if (t.k === 'p') { if (t.v === '{') d++; else if (t.v === '}' && !--d) return open + t.e }
  throw new Error('unclosed block at ' + open)
}
export function dictBlocks(src) {   // [{lang, start, open, end}] for `const I18N = {` and Object.assign(I18N.xx, {
  const out = [], re = /Object\.assign\(I18N\.(en|ko), \{|const I18N = \{ (?:en: \{\}, )?ko: \{/g; let m
  while ((m = re.exec(src))) { const open = m.index + m[0].length - 1; out.push({ lang: m[1] || 'ko', start: m.index, open, end: blockEnd(src, open) }) }
  return out
}
export function loadI18n(root = ROOT) {
  const jd = join(root, 'web', 'js'), files = readdirSync(jd).filter(f => f.endsWith('.js')).sort()
  const sb = { UIS: {}, navigator: { language: 'ko' }, document: { getElementById: () => null }, tabOwn: () => null, SHOW_STEP: 50 }
  vm.createContext(sb)
  const all = files.map(f => readFileSync(join(jd, f), 'utf8')).join('\n')
  for (const f of files) {
    const src = readFileSync(join(jd, f), 'utf8')
    if (isDict(f)) { vm.runInContext(src.replace(/^(const|let) /gm, 'var '), sb, { filename: f }); continue }
    for (const b of dictBlocks(src)) {
      const code = src.slice(b.start, b.end) + ')'
      for (let t = 0; ; t++) {   // computed keys ([SOME_CONST]: ...) -> define the const from its top-level declaration
        try { vm.runInContext(code, sb, { filename: f }); break } catch (e) {
          const nm = (/^(\w+) is not defined/.exec(e.message) || [])[1], d = nm && new RegExp('^const ' + nm + ' = (.*);$', 'm').exec(all)
          if (!d || t > 5) throw e
          vm.runInContext('var ' + nm + ' = ' + d[1] + ';', sb)
        }
      }
    }
  }
  return sb
}
// Old Korean key -> {en, ctx}: the inverse of I18N.ko (a 'text|ctx' key is that English text with a context).
//   ⚠First key per Korean value wins: older dictionary files load first, later slices reuse a Korean word under a new key.
export function flipMap(sb) {
  const m = {}
  for (const k of Object.keys(sb.I18N.ko)) { const c = /^([\s\S]*)\|([a-z]+)$/.exec(k); if (!own(m, sb.I18N.ko[k])) m[sb.I18N.ko[k]] = c ? { en: c[1], ctx: c[2] } : { en: k, ctx: null } }
  return m
}
// Old Korean unit -> English unit (the page's UNIT_EN, removed with the i18n bridge); the flip tool still reads old sources.
const UNIT_EN_OLD = {'초': 's', '분': 'm', '시간': 'h', '일': 'd', '개월': 'mo', '주': 'w',
                     '건': '', '개': '', '명': '', '회': '×', '줄': ' lines', '종': ' types', '단계': ''}
// Korean unit (+ optional English override) -> {en, ctx} from UNIT_EN_OLD / UNIT_KO; null when no table entry fits.
export function unitFlip(sb, ko, enOv) {
  const ue = UNIT_EN_OLD, uk = sb.UNIT_KO
  let en = enOv != null ? enOv : own(ue, ko) ? ue[ko] : null
  if (en == null) return null
  if (en === '') { const c = Object.keys(uk).find(k => k.startsWith('#') && uk[k] === ko); return c ? { en: c, ctx: null } : null }
  if (own(uk, en) && uk[en] === ko) return { en, ctx: null }
  const c = Object.keys(uk).find(k => k.startsWith(en + '|') && uk[k] === ko)
  return c ? { en, ctx: c.slice(en.length + 1) } : null
}
export const quote = s => {
  const e = s.replace(/\\/g, '\\\\').replace(/\n/g, '\\n').replace(/\r/g, '\\r').replace(/\t/g, '\\t')
  return e.includes("'") && !e.includes('"') ? '"' + e + '"' : "'" + e.replace(/'/g, "\\'") + "'"
}
const COMPARE = new Set(['===', '!==', '==', '!='])
// One file: {out, flips, manual: [{line, why, text}]}
export function flipSource(src, map, sb, opts = {}) {
  const toks = lex(src), edits = [], manual = []
  const line = i => src.slice(0, i).split('\n').length
  const inDict = dictBlocks(src).map(b => [b.start, b.end])
  const dictAt = i => inDict.some(([a, b]) => i >= a && i < b)
  const used = new Set()
  for (const c of calls(toks, 'T')) {
    const a = litArg(toks, c.args[0]); if (!a || dictAt(a.s)) continue
    used.add(c.args[0][0])
    if (!HANGUL.test(a.v)) continue
    const f = own(map, a.v) ? map[a.v] : null
    if (!f) { manual.push({ line: line(a.s), why: 'T literal without a dictionary entry', text: a.v }); continue }
    if (c.args.length > 1) { manual.push({ line: line(a.s), why: 'T with a second argument', text: a.v }); continue }
    edits.push([a.s, a.e, quote(f.en) + (f.ctx ? ', ' + quote(f.ctx) : '')])
  }
  for (const c of calls(toks, 'U')) {
    if (c.args.length < 2) continue
    const u = litArg(toks, c.args[1]), o = c.args[2] ? litArg(toks, c.args[2]) : null
    if (!u) continue
    used.add(c.args[1][0]); if (o) used.add(c.args[2][0])
    if (!HANGUL.test(u.v)) continue
    if (c.args[2] && !o) { manual.push({ line: line(u.s), why: 'U with a non-literal English unit', text: u.v }); continue }
    const f = unitFlip(sb, u.v, o ? o.v : null)
    if (!f) { manual.push({ line: line(u.s), why: 'U unit without a UNIT_KO entry', text: u.v + (o ? ' / ' + o.v : '') }); continue }
    const end = o ? o.e : u.e
    edits.push([u.s, end, quote(f.en) + (f.ctx ? ', ' + quote(f.ctx) : '')])
  }
  for (let i = 0; i < toks.length; i++) {
    const t = toks[i]
    if (t.k === 'tpl' && HANGUL.test(t.v) && !dictAt(t.s)) { manual.push({ line: line(t.s), why: 'Korean in an interpolated template', text: t.v }); continue }
    if (t.k !== 's' || used.has(i) || dictAt(t.s) || !HANGUL.test(t.v)) continue
    const p = toks[i - 1], n = toks[i + 1]
    const op = x => x && x.k === 'p' ? x.v : ''
    const cmp = (p && p.k === 'p' && p.v === '=' && COMPARE.has(op(toks[i - 3]) + op(toks[i - 2]) + '=')) || (p && p.k === 'id' && p.v === 'case')
      || (n && n.k === 'p' && n.v === '=' && op(toks[i + 2]) === '=') || (n && n.k === 'p' && n.v === '!' && op(toks[i + 2]) === '=')
      || (n && n.k === 'p' && n.v === ':' && p && p.k === 'p' && (p.v === '{' || p.v === ','))   // object key
    if (opts.allLiterals && own(map, t.v) && !cmp) { const f = map[t.v]; if (!f.ctx) { edits.push([t.s, t.e, quote(f.en)]); continue } }
    manual.push({ line: line(t.s), why: cmp ? 'Korean literal in a comparison or object key' : own(map, t.v) ? 'Korean literal (dictionary key, not in T())' : 'Korean literal', text: t.v })
  }
  edits.sort((a, b) => b[0] - a[0])
  let out = src
  for (const [s, e, r] of edits) out = out.slice(0, s) + r + out.slice(e)
  return { out, flips: edits.length, manual }
}

function main() {
  const args = process.argv.slice(2), write = args.includes('--write'), allLiterals = args.includes('--all-literals')
  let files = args.filter(a => !a.startsWith('--'))
  if (!files.length) files = [join(ROOT, 'web', 'app-head.js'), ...readdirSync(JD).filter(f => f.endsWith('.js') && !isDict(f)).sort().map(f => join(JD, f))]
  const sb = loadI18n(), map = flipMap(sb)
  let nf = 0, nm = 0
  for (const f of files) {
    const src = readFileSync(f, 'utf8'), r = flipSource(src, map, sb, { allLiterals })
    nf += r.flips; nm += r.manual.length
    for (const m of r.manual) console.log('MANUAL ' + f.replace(ROOT + '/', '') + ':' + m.line + ' ' + m.why + ': ' + JSON.stringify(m.text).slice(0, 120))
    if (write && r.out !== src) writeFileSync(f, r.out)
  }
  console.log('i18n_flip: ' + (write ? 'wrote' : 'dry run') + ' · ' + files.length + ' files · ' + nf + ' flips · ' + nm + ' manual')
}
if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) main()
