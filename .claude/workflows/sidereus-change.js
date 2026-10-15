export const meta = {
  name: 'sidereus-change',
  description: 'Sidereus viewer change: design -> parallel implementers -> verify (retry x2) -> review -> final verify. No commit, no restart.',
  whenToUse: 'A change request for ~/.mailbox-mcp (Sidereus viewer). Arg: the request text. The orchestrator restarts, screen-checks live, backs up and commits afterwards.',
  phases: [
    { title: 'Design', detail: 'sidereus-designer writes the spec and disjoint file slices' },
    { title: 'Implement', detail: 'one sidereus-implementer per slice, in parallel' },
    { title: 'Verify', detail: 'sidereus-verifier runs scripts/check.sh --full; failures loop back (max 2)' },
    { title: 'Review', detail: 'sidereus-reviewer on git diff; blocking findings loop back once' },
    { title: 'Re-verify', detail: 'sidereus-verifier once more after review fixes' },
  ],
}

// Rules every stage gets (AGENTS.md is injected too; these are the ones that bite in parallel runs).
const RULES = [
  'Repo: this repository (the folder holding AGENTS.md). AGENTS.md rules override this prompt.',
  'NEVER restart the viewer, NEVER commit/stash/checkout/reset/add, NEVER run screen_check --update. The orchestrator does those.',
  'Other implementers edit other files in the same tree at the same time: touch only your own files, Edit only on existing files, re-read before each edit.',
].join('\n')

const request = typeof args === 'string' ? args : (args && args.request) || ''
if (!request.trim()) throw new Error('sidereus-change: pass the change request text as args')

const SPEC = {
  type: 'object',
  properties: {
    summary: { type: 'string' },
    slices: {
      type: 'array',
      items: {
        type: 'object',
        properties: { id: { type: 'string' }, files: { type: 'array', items: { type: 'string' } }, task: { type: 'string' } },
        required: ['id', 'files', 'task'],
      },
    },
    rules: { type: 'string' },
    tests: { type: 'string' },
    screen: { type: 'string' },
    risk: { type: 'string' },
  },
  required: ['summary', 'slices', 'rules', 'tests', 'screen', 'risk'],
}
const IMPL = {
  type: 'object',
  properties: {
    slice: { type: 'string' },
    check_fast: { type: 'string', enum: ['PASS', 'FAIL'] },
    changed: { type: 'array', items: { type: 'string' } },
    did: { type: 'string' },
    outside: { type: 'string' },
  },
  required: ['slice', 'check_fast', 'changed', 'did', 'outside'],
}
const VERDICT = {
  type: 'object',
  properties: {
    result: { type: 'string', enum: ['PASS', 'FAIL'] },
    failures: {
      type: 'array',
      items: {
        type: 'object',
        properties: { step: { type: 'string' }, file: { type: 'string' }, line: { type: 'integer' }, why: { type: 'string' } },
        required: ['step', 'file', 'why'],
      },
    },
  },
  required: ['result', 'failures'],
}
const REVIEW = {
  type: 'object',
  properties: {
    verdict: { type: 'string', enum: ['CLEAN', 'BLOCKING'] },
    blocking: {
      type: 'array',
      items: { type: 'object', properties: { file: { type: 'string' }, line: { type: 'integer' }, rule: { type: 'string' }, fix: { type: 'string' } }, required: ['file', 'rule', 'fix'] },
    },
    nonblocking: { type: 'array', items: { type: 'string' } },
  },
  required: ['verdict', 'blocking', 'nonblocking'],
}

// ⚠Project agent types are only registered in sessions started after .claude/agents/ existed, so each
// role runs as general-purpose and loads its definition file itself (same rules, works in any session).
const AT = 'general-purpose'
const role = (name, p) => `First Read .claude/agents/${name}.md (repo root = cwd): it is your role definition — ` +
  `follow its rules and output format exactly.\n\n${p}`

// ---- Design
phase('Design')
const spec = await agent(role('sidereus-designer',
  `${RULES}\n\nWrite the spec for this change request. Slices must have disjoint file lists (no file in two slices).\n\nREQUEST:\n${request}`),
  { agentType: AT, schema: SPEC, label: 'design' })
if (!spec || !spec.slices || !spec.slices.length) throw new Error('sidereus-change: designer returned no slices')

// Guard: overlapping slices would make parallel implementers clobber each other -> merge them.
const slices = []
for (const s of spec.slices) {
  const hit = slices.find(t => t.files.some(f => s.files.includes(f)))
  if (hit) { hit.files = [...new Set([...hit.files, ...s.files])]; hit.task += ' | ' + s.task; log(`slice ${s.id} overlapped ${hit.id} -> merged`) }
  else slices.push({ id: s.id, files: [...s.files], task: s.task })
}
log(`spec: ${spec.summary} (${slices.length} slice${slices.length > 1 ? 's' : ''})`)

const specText = `SPEC SUMMARY: ${spec.summary}\nRULES: ${spec.rules}\nTESTS: ${spec.tests}\nSCREEN: ${spec.screen}\nRISK: ${spec.risk}`
const changed = new Set()
const reports = {}
const implPrompt = (s, extra) =>
  `${RULES}\n\nImplement slice ${s.id}. Your files (only these): ${s.files.join(', ')}\nTASK: ${s.task}\n\n${specText}\n` +
  (extra ? `\nFIX THIS (then re-run scripts/check.sh --fast):\n${extra}\n` : '') +
  `\nOriginal request:\n${request}`
const runImpl = async (s, extra, ph, tag) => {
  const r = await agent(role('sidereus-implementer', implPrompt(s, extra)), { agentType: AT, schema: IMPL, phase: ph, label: `${tag} ${s.id}` })
  if (r) { (r.changed || []).forEach(f => changed.add(f)); reports[s.id] = r }
  return r
}

// Route each failure to the slice that owns its file; unowned failures go to every slice (they report "outside" if not theirs).
const owner = file => slices.find(s => s.files.some(f => file && (file === f || file.endsWith(f) || f.endsWith(file))))
const route = items => {
  const by = new Map()
  for (const it of items) {
    const targets = owner(it.file) ? [owner(it.file)] : slices
    for (const s of targets) { if (!by.has(s.id)) by.set(s.id, []); by.get(s.id).push(it.text) }
  }
  return by
}
const fixRound = (by, ph, tag) =>
  parallel(slices.filter(s => by.has(s.id)).map(s => () => runImpl(s, by.get(s.id).join('\n'), ph, tag)))

// ---- Implement
phase('Implement')
await parallel(slices.map(s => () => runImpl(s, '', 'Implement', 'impl')))

// ---- Verify (max 2 fix retries)
phase('Verify')
const verify = (ph, tag) => agent(role('sidereus-verifier',
  `${RULES}\n\nRun scripts/check.sh --full once and report. Do not fix anything.`),
  { agentType: AT, model: 'sonnet', schema: VERDICT, phase: ph, label: tag })
let v = await verify('Verify', 'verify 1')
let retries = 0
while (v && v.result === 'FAIL' && retries < 2) {
  retries++
  log(`verify FAIL (${v.failures.length}) -> fix round ${retries}/2`)
  const by = route(v.failures.map(f => ({ file: f.file, text: `[${f.step}] ${f.file}${f.line ? ':' + f.line : ''} ${f.why}` })))
  await fixRound(by, 'Verify', `fix${retries}`)
  v = await verify('Verify', `verify ${retries + 1}`)
}
if (!v || v.result !== 'PASS') {
  log('verify still failing after 2 retries -> stopping before review')
  return { status: 'FAIL_VERIFY', summary: spec.summary, changed: [...changed].sort(), failures: v ? v.failures : [], slices: reports }
}

// ---- Review (blocking findings loop back once)
phase('Review')
const rv = await agent(role('sidereus-reviewer',
  `${RULES}\n\nReview the working-tree diff (git diff + untracked files) for this change.\n${specText}\nChanged files reported: ${[...changed].join(', ')}`),
  { agentType: AT, schema: REVIEW, phase: 'Review', label: 'review' })
let final = v
if (rv && rv.verdict === 'BLOCKING' && rv.blocking.length) {
  log(`review BLOCKING (${rv.blocking.length}) -> one fix round`)
  const by = route(rv.blocking.map(b => ({ file: b.file, text: `[review:${b.rule}] ${b.file}${b.line ? ':' + b.line : ''} ${b.fix}` })))
  await fixRound(by, 'Review', 'review-fix')
  phase('Re-verify')
  final = await verify('Re-verify', 're-verify')
}

const ok = final && final.result === 'PASS'
return {
  status: ok ? 'PASS' : 'FAIL_FINAL',
  summary: spec.summary,
  changed: [...changed].sort(),
  screen: spec.screen,
  risk: spec.risk,
  verify_retries: retries,
  review: rv ? { verdict: rv.verdict, blocking: rv.blocking, nonblocking: rv.nonblocking } : null,
  failures: ok ? [] : (final ? final.failures : []),
  orchestrator_todo: ['launchctl kickstart -k gui/$(id -u)/io.sidereus.viewer', 'screen-check the live page (900/1100/1440)', 'bash backup.sh', 'commit'],
}
