// Static check for .claude/pipelines/*.json against the runner .claude/workflows/pipeline.js.
// Runs the runner's own validate block (single source of rules) and checks meta.phases == '불러오기' + STAGE_TITLES,
// so every stage title lights an exact phase. No deps. Exit 1 on any error; last line is the summary.
import { readFileSync, readdirSync, existsSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const runner = join(root, '.claude/workflows/pipeline.js')
const dir = join(root, '.claude/pipelines')
const errs = []
const src = readFileSync(runner, 'utf8')

const metaSrc = src.slice(src.indexOf('export const meta ='), src.indexOf('\n}\n') + 2).replace('export const meta =', 'return')
const meta = new Function(metaSrc)()
const phases = (meta.phases || []).map(p => p.title)
const m = src.match(/^const STAGE_TITLES = (\[.*\])$/m)
const MODELS_M = src.match(/^const MODELS = (\[.*\])$/m)
if (!m || !MODELS_M) { console.log('pipeline_check: STAGE_TITLES / MODELS not found in runner'); process.exit(1) }
const STAGE_TITLES = JSON.parse(m[1].replace(/'/g, '"'))
const MODELS = JSON.parse(MODELS_M[1].replace(/'/g, '"'))
const want = ['불러오기', ...STAGE_TITLES]
if (JSON.stringify(phases) !== JSON.stringify(want)) errs.push(`runner: meta.phases ${JSON.stringify(phases)} != ['불러오기', ...STAGE_TITLES]`)

const a = src.indexOf('// ---- validate'), b = src.indexOf('\nif (errs.length)', a)
if (a < 0 || b < 0) { console.log('pipeline_check: validate block markers not found in runner'); process.exit(1) }
const validate = new Function('P', 'pipelineName', 'STAGE_TITLES', 'MODELS', src.slice(a, b) + '\nreturn errs')

// Run-time model override block (args.models): self-test against fixed cases.
const ma = src.indexOf('// ⚠scripts/pipeline_check.mjs executes the text from here to `if (mErrs.length)`'), mb = src.indexOf('\nif (mErrs.length)', ma)
if (ma < 0 || mb < 0) { console.log('pipeline_check: models block markers not found in runner'); process.exit(1) }
const checkModels = new Function('models', 'S', 'MODELS', src.slice(ma, mb) + '\nreturn mErrs')
const S0 = [{ title: '설계' }, { title: '검증' }]
for (const [models, n] of [[{}, 0], [{ 설계: 'opus', 검증: 'haiku' }, 0], [{ 리뷰: 'opus' }, 1], [{ 설계: 'gpt' }, 1], [[], 1], [null, 1], ['opus', 1]]) {
  const got = checkModels(models, S0, MODELS).length
  if (got !== n) errs.push(`runner: args.models ${JSON.stringify(models)} gave ${got} error(s), want ${n}`)
}

// Default tasks: pure JSON between markers, one per STAGE_TITLES entry; stageTask appends stage.task.
const dt = src.match(/\/\/ DEFAULT_TASKS-BEGIN\nconst DEFAULT_TASKS = ([\s\S]*?)\n\/\/ DEFAULT_TASKS-END\n(const stageTask = [^\n]*)/)
if (!dt) { console.log('pipeline_check: DEFAULT_TASKS markers not found in runner'); process.exit(1) }
let DT = {}
try { DT = JSON.parse(dt[1]) } catch (e) { errs.push(`runner: DEFAULT_TASKS is not pure JSON (${e.message})`) }
const REC = STAGE_TITLES.filter(t => !t.startsWith('사용자 단계'))
if (JSON.stringify(Object.keys(DT)) !== JSON.stringify(REC)) errs.push('runner: DEFAULT_TASKS keys != recommended STAGE_TITLES')
// Custom titles: phase slot assignment + validation (task required, reserved slot names refused).
const ps = src.match(/^const phaseSlots = [^\n]*$/m)
if (!ps) errs.push('runner: phaseSlots not found')
else {
  const phaseSlots = new Function(ps[0] + '\nreturn phaseSlots')()
  const got = phaseSlots([{ title: '설계' }, { title: '문서 정리' }, { title: '검증' }, { title: '배포 확인' }], STAGE_TITLES)
  if (JSON.stringify(got) !== JSON.stringify({ 설계: '설계', '문서 정리': '사용자 단계 1', 검증: '검증', '배포 확인': '사용자 단계 2' })) errs.push('runner: phaseSlots assignment wrong')
  if (!Object.values(got).every(t => phases.includes(t))) errs.push('runner: phaseSlots gave a phase not in meta.phases')
}
const stageTask = new Function('DEFAULT_TASKS', dt[2] + '\nreturn stageTask')(DT)
if (stageTask({ title: '검증' }) !== DT['검증']) errs.push('runner: stageTask without task must be the default')
if (stageTask({ title: '검증', task: 'X' }) !== DT['검증'] + '\n\nADDITIONAL INSTRUCTIONS:\nX') errs.push('runner: stageTask must append stage.task')
if (stageTask({ title: '검증', skill: 'sidereus-ship' }) !== DT['검증'] + '\n\nFollow the sidereus-ship skill.') errs.push('runner: stageTask must append the stage skill')

const base = { v: 1, name: 'x', title: 'x', defaults: { model: 'inherit', retry: 0 } }
for (const [stages, want] of [[[{ title: '문서 정리', agent: 'a', task: 'do' }], 0], [[{ title: '문서 정리', agent: 'a' }], 1],
  [[{ title: '사용자 단계 1', agent: 'a', task: 'x' }], 1], [[{ title: 'a\nb', agent: 'a', task: 'x' }], 1],
  [[{ title: '검증', agent: 'a', skill: 'sidereus-ship' }], 0], [[{ title: '검증', agent: 'a', skill: 'Bad X' }], 1]]) {
  const n = validate({ ...base, stages }, 'x', STAGE_TITLES, MODELS).length
  if (n !== want) errs.push(`runner: custom-title validate ${JSON.stringify(stages)} gave ${n} error(s), want ${want}`)
}
// guards: required stages exist and have a graded gate; maxLoopBacks 1..10.
const GS = [{ title: '구현', agent: 'a', gate: 'scripts/check.sh --fast' }, { title: '검증', agent: 'a', gate: 'bash scripts/check.sh --full' },
  { title: '리뷰', agent: 'a' }, { title: '문서 정리', agent: 'a', task: 'x', gate: '/usr/bin/python3 scripts/arch_checks.py --verify --last --category security' }]
for (const [guards, want] of [[{ requireGates: ['구현', '검증', '문서 정리'], maxLoopBacks: 3 }, 0], [{}, 0], [{ maxLoopBacks: 10 }, 0],
  [{ requireGates: ['없음'] }, 1], [{ requireGates: ['리뷰'] }, 1], [{ maxLoopBacks: 0 }, 1], [{ maxLoopBacks: 11 }, 1], [{ maxLoopBacks: true }, 1],
  [{ requireGates: '검증' }, 1], [{ other: 1 }, 1], [[], 1], [null, 1]]) {
  const n = validate({ ...base, stages: GS, guards }, 'x', STAGE_TITLES, MODELS).length
  if (n !== want) errs.push(`runner: guards validate ${JSON.stringify(guards)} gave ${n} error(s), want ${want}`)
}

// .claude/pipelines/_defaults.json = copy of DEFAULT_TASKS for «세션 직접 실행» sessions (no runner involved); must stay identical.
const dj = join(dir, '_defaults.json')
if (existsSync(dj)) { try { if (JSON.stringify(JSON.parse(readFileSync(dj, 'utf8'))) !== JSON.stringify(DT)) errs.push('_defaults.json != runner DEFAULT_TASKS (regenerate it from the runner)') } catch (e) { errs.push(`_defaults.json: ${e.message}`) } }
const files = existsSync(dir) ? readdirSync(dir).filter(f => f.endsWith('.json') && !f.startsWith('_')).sort() : []
for (const f of files) {
  const name = f.slice(0, -5)
  if (!/^[a-z0-9-]{1,40}$/.test(name)) { errs.push(`${f}: file name must match ^[a-z0-9-]{1,40}$`); continue }
  let P
  try { P = JSON.parse(readFileSync(join(dir, f), 'utf8')) } catch (e) { errs.push(`${f}: ${e.message}`); continue }
  for (const e of validate(P, name, STAGE_TITLES, MODELS)) errs.push(`${f}: ${e}`)
  // Every stage must land on a runner phase (recommended title or a «사용자 단계 N» slot).
  if (ps && Array.isArray(P.stages)) { const m = new Function(ps[0] + '\nreturn phaseSlots')()(P.stages.filter(Boolean), STAGE_TITLES); for (const t in m) if (!phases.includes(m[t])) errs.push(`${f}: stage "${t}" has no runner phase`) }
}
errs.forEach(e => console.log('FAIL ' + e))
console.log(errs.length ? `pipeline_check: ${errs.length} error(s)` : `pipeline_check: ${files.length} pipeline(s) ok`)
process.exit(errs.length ? 1 : 0)
