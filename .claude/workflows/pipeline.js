export const meta = {
  name: 'pipeline',
  description: 'Generic stage runner: runs .claude/pipelines/<pipeline>.json (agent + model per stage, retry, loop-back, fan-out). No commit, no restart.',
  whenToUse: 'Run a declared per-project pipeline. Args: {pipeline: "<name>", request: "<request text>", models?: {"<stage title>": "inherit|opus|sonnet|haiku"}} (models = this run only). Pipelines live in .claude/pipelines/*.json of the project this runs in.',
  phases: [
    { title: '불러오기', detail: 'read and validate .claude/pipelines/<pipeline>.json', model: 'haiku' },
    { title: '설계', detail: 'design / spec stage' },
    { title: '구현', detail: 'implementation stage (often fanned out per slice)' },
    { title: '검증', detail: 'verification gate stage' },
    { title: '리뷰', detail: 'diff review stage' },
    { title: '재검증', detail: 'verification after a review fix round' },
    { title: '재현', detail: 'bug reproduction stage' },
    { title: '원인', detail: 'root-cause stage' },
    { title: '수정', detail: 'fix stage' },
    { title: '회귀', detail: 'regression test stage' },
    { title: '트리아지', detail: 'triage stage' },
    { title: '라이브 검증', detail: 'live-system verification stage' },
    { title: 'AI 설정 점검', detail: 'read-only review of the AI configuration the project ships' },
    { title: '프롬프트 검증', detail: 'run agent/skill prompts on synthetic input and check the promises' },
    { title: '사용자 단계 1', detail: 'user-defined stage slot (label carries the real title)' },
    { title: '사용자 단계 2', detail: 'user-defined stage slot (label carries the real title)' },
    { title: '사용자 단계 3', detail: 'user-defined stage slot (label carries the real title)' },
    { title: '사용자 단계 4', detail: 'user-defined stage slot (label carries the real title)' },
    { title: '사용자 단계 5', detail: 'user-defined stage slot (label carries the real title)' },
    { title: '사용자 단계 6', detail: 'user-defined stage slot (label carries the real title)' },
    { title: '사용자 단계 7', detail: 'user-defined stage slot (label carries the real title)' },
    { title: '사용자 단계 8', detail: 'user-defined stage slot (label carries the real title)' },
    { title: '사용자 단계 9', detail: 'user-defined stage slot (label carries the real title)' },
    { title: '사용자 단계 10', detail: 'user-defined stage slot (label carries the real title)' },
    { title: '사용자 단계 11', detail: 'user-defined stage slot (label carries the real title)' },
    { title: '사용자 단계 12', detail: 'user-defined stage slot (label carries the real title)' },
  ],
}

// ONE fixed runner for every pipeline JSON (docs/dev/PIPELINE.md step 1). Never generated per project.
//
// Why fixed phases: meta must be a pure literal, and a phase() title only groups/lights correctly when it matches a
// meta.phases entry exactly. STAGE_TITLES (== meta.phases minus '불러오기') = 13 recommended titles + 12 «사용자 단계 N» slots.
// Stages are user-defined work, not a fixed set — a stage title may be any text; a recommended
// title runs under its own phase, any other title under the next free slot in stage order (phaseSlots), labelled with its title.
// ⚠Unused phases show as empty groups in /workflows — the accepted cost of exact lighting.
// ⚠Adding a title = edit BOTH meta.phases and STAGE_TITLES (scripts/pipeline_check.mjs enforces equality).
//
// Why a loader agent: workflow scripts have no filesystem API, so a cheap agent reads the file verbatim
// (text + `wc -c` byte count); the runner JSON.parses it, checks the byte count and validates the schema
// itself — the model cannot silently change a stage.
//
// Why the agentType fallback: project agent types are registered only in sessions started after
// .claude/agents/ existed (see sidereus-change.js). If agentType is rejected, the stage runs as
// general-purpose and loads .claude/agents/<agent>.md itself.
//
// ⚠retry restarts the stage agent with the full brief (never resumes) — n8n retryOnFail context-loss trap.
//
// Why cause + signature stops: ★2026-10-01 first live run (wf_5f824c4b-e46) — «검증» failed only on a stale screen
// baseline; the implementer said "not caused by this slice … only the orchestrator may run --update", yet «검증»→«구현»
// looped twice (~3 wasted agents). ⇒ a FAIL with cause "unrelated" (or a fix round answering "unrelated") stops as
// BLOCKED_ORCHESTRATOR with the agent's `after` actions; the same failure signature twice in a row stops the loop.

const STAGE_TITLES = ['설계', '구현', '검증', '리뷰', '재검증', '재현', '원인', '수정', '회귀', '트리아지', '라이브 검증', 'AI 설정 점검', '프롬프트 검증', '사용자 단계 1', '사용자 단계 2', '사용자 단계 3', '사용자 단계 4', '사용자 단계 5', '사용자 단계 6', '사용자 단계 7', '사용자 단계 8', '사용자 단계 9', '사용자 단계 10', '사용자 단계 11', '사용자 단계 12']
// title -> phase: recommended titles map to themselves, others take «사용자 단계 1..12» in stage order (mirrored: web/js/48c plgSlots).
const phaseSlots = (S, titles) => { const rec = titles.filter(t => !t.startsWith('사용자 단계')), m = {}; let n = 0; for (const s of S) m[s.title] = rec.includes(s.title) ? s.title : '사용자 단계 ' + (++n); return m }
const MODELS = ['inherit', 'opus', 'sonnet', 'haiku']
// Default instruction per stage title; stage.task is appended as extra instructions (docs/dev/PIPELINE.md «Default tasks»).
// ⚠Pure JSON between the markers: sidereus/pipeline.py (UI) and scripts/pipeline_check.mjs parse it — one source of truth.
// DEFAULT_TASKS-BEGIN
const DEFAULT_TASKS = {
  "설계": "Read the request and the code it touches; change nothing. Put a spec in summary: goal, approach, files to change, rules affected, tests to add, risks. PASS when the spec is complete; FAIL with findings if the request is unclear or unsafe.",
  "구현": "Implement the spec (only your slice if one is given). Keep the change minimal, follow the repo's rules and add or update tests. Run the gate if one is given. PASS when done and the gate passes; list every file you changed in changed.",
  "검증": "Verify the change; fix nothing. Run the gate (or the project's tests) once and report each failing step as a finding with file/line. PASS only if everything passes. A failure not caused by this change gets cause \"unrelated\" with the reason.",
  "리뷰": "Review the working-tree diff against the repo's rules, security and simplicity; fix nothing. FAIL only for blocking findings (file/line and the fix in text); put non-blocking notes in summary.",
  "재검증": "Run the gate once more after the review fix round; fix nothing. PASS only if it passes; report each failing step as a finding.",
  "재현": "Reproduce the reported bug; change nothing. Put exact steps, inputs and the failing output in summary. PASS when reproduced; FAIL if it cannot be reproduced, saying what you tried.",
  "원인": "Find the root cause of the reproduced bug with file/line evidence; change nothing. Put the causal chain in summary and the key lines in findings. FAIL if the cause is not proven.",
  "수정": "Fix the root cause with the smallest change and add a regression test that fails before and passes after. List the changed files. PASS when the fix and the test are in.",
  "회귀": "Run the regression test and the project's test suite once; fix nothing. PASS only if all pass; report each failure as a finding. A failure not caused by this change gets cause \"unrelated\".",
  "트리아지": "Classify the request: kind (bug / feature / question), severity, affected area, likely owner and the next step. Change nothing. Put the classification in summary; PASS unless the request is unreadable.",
  "라이브 검증": "Check the running system, not just the code, against the request: observe the real behaviour and report what you saw with evidence. Change nothing. PASS only if the live behaviour matches.",
  "AI 설정 점검": "Review the AI configuration this project ships; change nothing. Read AGENTS.md/CLAUDE.md, .claude/agents/*.md, .claude/skills/*, hook settings, .mcp.json and the pipeline stage tasks. Report each finding with file:line: contradictions between files, references to agents/skills/paths/commands that do not exist, prohibitions not stated first, the same rule worded differently in two places, prompts with no output-size cap or no verifiable done-criterion, judgment work (design, diagnosis, review) set to a small model. PASS when no blocking finding remains.",
  "프롬프트 검증": "Run each agent/skill prompt named in the request on a small synthetic input you write yourself (never live data, never the real project files as input). Check the output against what the prompt promises: required fields and format, output-size cap, prohibited actions not taken (no edits or commits when read-only), done-criterion met. Change nothing. Report PASS/FAIL per prompt with the evidence; PASS only if every prompt passes."
}
// DEFAULT_TASKS-END
const stageTask = st => (DEFAULT_TASKS[st.title] || '') + (st.task ? '\n\nADDITIONAL INSTRUCTIONS:\n' + st.task : '') + (st.skill ? '\n\nFollow the ' + st.skill + ' skill.' : '')

const a = (args && typeof args === 'object') ? args : {}
const pipelineName = String(a.pipeline || '')
const request = String(a.request || '')
if (!/^[a-z0-9-]{1,40}$/.test(pipelineName)) throw new Error('pipeline: args.pipeline must match ^[a-z0-9-]{1,40}$')
if (!request.trim()) throw new Error('pipeline: args.request is empty')

// ---- load
phase('불러오기')
const LOADED = {
  type: 'object',
  properties: { bytes: { type: 'integer' }, text: { type: 'string' } },
  required: ['bytes', 'text'],
}
const file = `.claude/pipelines/${pipelineName}.json`
const loaded = await agent(
  `Read the file ${file} (relative to the current working directory, the project root). ` +
  `Run \`wc -c < ${file}\` for "bytes" and put the file content in "text" EXACTLY as stored — byte for byte, no reformatting, no fixes. ` +
  `If the file does not exist, return bytes -1 and text "". Do nothing else.`,
  { schema: LOADED, model: 'haiku', phase: '불러오기', label: `load ${pipelineName}` })
if (!loaded || loaded.bytes < 0) throw new Error(`pipeline: ${file} not found`)
const utf8Len = s => { let n = 0; for (const ch of s) { const c = ch.codePointAt(0); n += c < 0x80 ? 1 : c < 0x800 ? 2 : c < 0x10000 ? 3 : 4 } return n }
// Some readers drop the final newline; allow exactly that one-byte difference.
const diff = loaded.bytes - utf8Len(loaded.text)
if (diff !== 0 && diff !== 1) throw new Error(`pipeline: ${file} came back altered (bytes ${loaded.bytes} vs ${utf8Len(loaded.text)})`)
let P
try { P = JSON.parse(loaded.text) } catch (e) { throw new Error(`pipeline: ${file} is not valid JSON: ${e.message}`) }
// ---- validate
// ⚠scripts/pipeline_check.mjs executes the text from here to `if (errs.length)` — keep it self-contained (uses only P, pipelineName, STAGE_TITLES, MODELS).
// ⚠Every check below is mirrored by sidereus/pipeline_schema.py validate (tests/test_pipeline_schema_mirror.py runs both on the same cases).
// Renamed recommended titles (old -> new): a legacy file runs under the new title. ⚠Same map in sidereus/pipeline_schema.py RENAMED.
const RENAMED = { '최종 검증': '재검증' }, ren = t => (typeof t === 'string' && Object.prototype.hasOwnProperty.call(RENAMED, t)) ? RENAMED[t] : t
if (Array.isArray(P.stages)) P.stages.forEach(s => { if (s && typeof s === 'object') { s.title = ren(s.title); if (s.onFail && typeof s.onFail === 'object') { s.onFail.goto = ren(s.onFail.goto); if (s.onFail.then !== undefined) s.onFail.then = ren(s.onFail.then) } } })
if (P.guards && Array.isArray(P.guards.requireGates)) P.guards.requireGates = P.guards.requireGates.map(ren)

const errs = []
const isInt = (x, lo, hi) => Number.isInteger(x) && x >= lo && x <= hi
const oneLine = (x, max) => typeof x === 'string' && x.length <= max && !/[\r\n]/.test(x)
if (P.v !== 1) errs.push('v must be 1')
if (P.name !== pipelineName) errs.push(`name must equal file stem "${pipelineName}"`)
if (!oneLine(P.title, 80) || !P.title) errs.push('title: 1-80 chars, one line')
if (P.use !== undefined && !(oneLine(P.use, 120) && P.use.trim())) errs.push('use: one line, 1..120 chars')
if (P.rules !== undefined && (typeof P.rules !== 'string' || P.rules.length > 2000)) errs.push('rules: string <= 2000')
if (P.after !== undefined && !(Array.isArray(P.after) && P.after.every(x => oneLine(x, 200)))) errs.push('after: array of one-line strings')
const D = P.defaults || {}
if (!MODELS.includes(D.model)) errs.push('defaults.model: inherit|opus|sonnet|haiku')
if (!isInt(D.retry, 0, 3)) errs.push('defaults.retry: 0..3')
const S = Array.isArray(P.stages) ? P.stages : []
if (!S.length || S.length > 20) errs.push('stages: 1..20')
const idx = t => S.findIndex(s => s && s.title === t)
S.forEach((s, i) => {
  const at = `stages[${i}]`
  if (!s || typeof s !== 'object') { errs.push(`${at}: object`); return }
  const rec = STAGE_TITLES.filter(t => !t.startsWith('사용자 단계'))
  if (!oneLine(s.title, 40) || !String(s.title).trim()) errs.push(`${at}.title: 1-40 chars, one line`)
  else if (s.title.startsWith('사용자 단계')) errs.push(`${at}.title "${s.title}": «사용자 단계» names are reserved phase slots`)
  else if (!rec.includes(s.title) && !(typeof s.task === 'string' && s.task.trim())) errs.push(`${at}.task: required for a custom stage "${s.title}" (no default instruction)`)
  if (idx(s.title) !== i) errs.push(`${at}.title duplicated`)
  if (typeof s.agent !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,59}$/.test(s.agent)) errs.push(`${at}.agent: ^[A-Za-z0-9][A-Za-z0-9_-]{0,59}$`)
  if ('skill' in s && (typeof s.skill !== 'string' || !/^[a-z0-9-]{1,60}$/.test(s.skill))) errs.push(`${at}.skill: ^[a-z0-9-]{1,60}$`)
  if (s.task !== undefined && (typeof s.task !== 'string' || s.task.length > 1000)) errs.push(`${at}.task: string <= 1000`)
  if (s.model !== undefined && !MODELS.includes(s.model)) errs.push(`${at}.model`)
  if (s.retry !== undefined && !isInt(s.retry, 0, 3)) errs.push(`${at}.retry: 0..3`)
  if (s.parallel !== undefined && !isInt(s.parallel, 1, 16)) errs.push(`${at}.parallel: 1..16`)
  if (s.gate !== undefined && !(oneLine(s.gate, 200) && s.gate)) errs.push(`${at}.gate: one line, 1..200 chars`)
  if (s.produces !== undefined && s.produces !== 'slices') errs.push(`${at}.produces: "slices"`)
  if (s.fanout !== undefined) {
    if (s.fanout !== 'slices') errs.push(`${at}.fanout: "slices"`)
    else if (!S.slice(0, i).some(t => t && t.produces === 'slices')) errs.push(`${at}.fanout needs an earlier stage with produces:"slices"`)
  }
  if (s.onError !== undefined && !['stop', 'continue'].includes(s.onError)) errs.push(`${at}.onError: stop|continue`)
  if (s.onlyOnJump !== undefined && typeof s.onlyOnJump !== 'boolean') errs.push(`${at}.onlyOnJump: boolean`)
  // ui = canvas position for Sidereus's editor only; the runner ignores it
  if (s.ui !== undefined && !(s.ui && typeof s.ui === 'object' && ['x,y', 'color,x,y'].includes(Object.keys(s.ui).sort().join()) && ['x', 'y'].every(k => typeof s.ui[k] === 'number' && Math.abs(s.ui[k]) <= 100000)
    && (s.ui.color === undefined || /^#[0-9a-f]{6}$/.test(s.ui.color)))) errs.push(`${at}.ui: {x, y} numbers (+ color "#rrggbb")`)
  if (s.onFail !== undefined) {
    const f = s.onFail || {}
    const g = idx(f.goto)
    if (g < 0 || g >= i) errs.push(`${at}.onFail.goto must name an earlier stage`)
    if (!isInt(f.max, 1, 5)) errs.push(`${at}.onFail.max: 1..5`)
    if (f.then !== undefined && idx(f.then) <= i) errs.push(`${at}.onFail.then must name a later stage`)
    if (f.stopOn !== undefined && !(Array.isArray(f.stopOn) && f.stopOn.every(x => x === 'unrelated'))) errs.push(`${at}.onFail.stopOn: [] or ["unrelated"]`)
  }
})
// guards (enforced by hooks/pl_guard.py): requireGates stages need a graded gate. ⚠GATE_MODES = sidereus/pipeline_schema.py GATE_MODES (tests pin).
const GATE_MODES = [["(?:^|[\\s/])check\\.sh\\s+--fast(?![\\w-])", "fast"], ["(?:^|[\\s/])check\\.sh\\s+--full(?![\\w-])", "full"], ["arch_checks\\.py(?=.*\\s--verify(?![\\w-])).*\\s--category[\\s=]+security(?![\\w-])", "checks-security"], ["arch_checks\\.py(?=.*\\s--verify(?![\\w-]))(?!.*\\s--category[\\s=]+(?!quality(?![\\w-])))", "checks-quality"]]
if (P.guards !== undefined) {
  const G = P.guards
  if (!G || typeof G !== 'object' || Array.isArray(G) || Object.keys(G).some(k => !['requireGates', 'maxLoopBacks'].includes(k))) errs.push('guards: object with requireGates and/or maxLoopBacks')
  else {
    const rq = G.requireGates === undefined ? [] : G.requireGates
    if (!Array.isArray(rq) || !rq.every(t => typeof t === 'string')) errs.push('guards.requireGates: array of stage titles')
    else rq.forEach(t => {
      const k = idx(t)
      if (k < 0) errs.push(`guards.requireGates: no stage "${t}"`)
      else if (!GATE_MODES.some(([p]) => typeof S[k].gate === 'string' && new RegExp(p).test(S[k].gate))) errs.push(`guards.requireGates: stage "${t}" has no graded gate (check.sh --fast|--full, arch_checks.py --verify)`)
    })
    if (G.maxLoopBacks !== undefined && !isInt(G.maxLoopBacks, 1, 10)) errs.push('guards.maxLoopBacks: 1..10')
  }
}
if (S.length && S[0].onlyOnJump) errs.push('stages[0] cannot be onlyOnJump')
{ const rec = STAGE_TITLES.filter(t => !t.startsWith('사용자 단계')), slots = STAGE_TITLES.length - rec.length   // derived: adding a title must not shift the count
  if (S.filter(s => s && !rec.includes(s.title)).length > slots) errs.push(`at most ${slots} custom stages (phase slots)`) }
if (errs.length) throw new Error(`pipeline: ${file} invalid:\n- ${errs.join('\n- ')}`)
const PHASE = phaseSlots(S, STAGE_TITLES)

// ---- run-time models: args.models = {"<stage title>": model} overrides stage/default model for this run only (JSON unchanged).
const models = a.models === undefined ? {} : a.models
// ⚠scripts/pipeline_check.mjs executes the text from here to `if (mErrs.length)` — keep it self-contained (uses only models, S, MODELS).
const mErrs = []
if (!models || typeof models !== 'object' || Array.isArray(models)) mErrs.push('args.models must be {"<stage title>": model}')
else for (const [t, m] of Object.entries(models)) {
  if (!S.some(s => s && s.title === t)) mErrs.push(`args.models: no stage "${t}"`)
  if (!MODELS.includes(m)) mErrs.push(`args.models["${t}"]: inherit|opus|sonnet|haiku`)
}
if (mErrs.length) throw new Error(`pipeline: ${mErrs.join('; ')}`)
const OVR = models
if (Object.keys(OVR).length) log(`models for this run: ${Object.entries(OVR).map(([t, m]) => t + '=' + m).join(', ')}`)
log(`${P.name}: ${S.map(s => s.title).join(' → ')}`)

// ---- run
const SLICE = {
  type: 'object',
  properties: { id: { type: 'string' }, files: { type: 'array', items: { type: 'string' } }, task: { type: 'string' } },
  required: ['id', 'files', 'task'],
}
const FINDING = {
  type: 'object',
  properties: { step: { type: 'string' }, file: { type: 'string' }, line: { type: 'integer' }, text: { type: 'string' } },
  required: ['text'],
}
const resultSchema = st => {
  const properties = {
    status: { type: 'string', enum: ['PASS', 'FAIL'] },
    summary: { type: 'string' },
    findings: { type: 'array', items: FINDING },
    changed: { type: 'array', items: { type: 'string' } },
    cause: { type: 'string', enum: ['change', 'unrelated'] },
    causeReason: { type: 'string' },
    after: { type: 'array', items: { type: 'string' } },
  }
  const required = ['status', 'summary', 'findings', 'changed']
  if (st.produces === 'slices') { properties.slices = { type: 'array', items: SLICE }; required.push('slices') }
  return { type: 'object', properties, required }
}

const results = {}          // title -> latest merged result
const runs = {}             // title -> agent launches
const changed = new Set()
let slices = []

const clip = (s, n) => (s = String(s || ''), s.length > n ? s.slice(0, n) + '…' : s)
const brief = (st, extra) => {
  const prev = S.filter(t => results[t.title] && t.title !== st.title)
    .map(t => `[${t.title}] ${results[t.title].status} — ${clip(results[t.title].summary, 600)}`)
  const parts = [
    `Pipeline "${P.name}" (${P.title}) — stage "${st.title}".`,
    P.rules ? `RULES:\n${P.rules}` : '',
    `YOUR TASK:\n${stageTask(st)}`,
    st.gate ? `GATE — run it yourself, exactly, and set status from its outcome (PASS only if it passes):\n${st.gate}` : '',
    st.produces === 'slices' ? 'Return "slices": disjoint file lists (no file in two slices), one slice per independent implementer.' : '',
    prev.length ? `PREVIOUS STAGES:\n${prev.join('\n')}` : '',
    changed.size ? `CHANGED FILES SO FAR: ${[...changed].sort().join(', ')}` : '',
    extra || '',
    'Return status PASS/FAIL, a short summary, findings (step = failing gate step name, file/line/text; empty if none) and the files you changed.',
    'On FAIL — or when told to fix something you cannot fix — also set "cause": "change" if this request\'s edits (any slice) caused it, ' +
    '"unrelated" if not (stale screen baseline, a failure that exists without this change, environment/tooling); ' +
    '"causeReason": one line why; and for "unrelated", "after": the exact actions only the orchestrator may take (e.g. "node scripts/screen_check.mjs --update").',
    `REQUEST:\n${request}`,
  ]
  return parts.filter(Boolean).join('\n\n')
}

const opts = (st, label) => {
  const m = OVR[st.title] || st.model || D.model
  const o = { schema: resultSchema(st), phase: PHASE[st.title], label }
  if (m !== 'inherit') o.model = m
  return o
}
const call = async (st, prompt, label) => {
  runs[st.title] = (runs[st.title] || 0) + 1
  if (st.agent === 'general-purpose') return agent(prompt, { ...opts(st, label), agentType: 'general-purpose' })
  try {
    return await agent(prompt, { ...opts(st, label), agentType: st.agent })
  } catch (e) {
    log(`${st.title}: agentType ${st.agent} unavailable (${clip(e && e.message, 80)}) -> general-purpose + role file`)
    return agent(`First Read .claude/agents/${st.agent}.md (repo root = cwd; else ~/.claude/agents/${st.agent}.md): ` +
      `it is your role definition — follow its rules exactly.\n\n${prompt}`,
      { ...opts(st, label), agentType: 'general-purpose' })
  }
}
// retry = rerun the same agent with the full brief when it died (null) or reported FAIL.
const withRetry = async (st, prompt, label) => {
  const n = st.retry !== undefined ? st.retry : D.retry
  let r = null
  for (let k = 0; k <= n; k++) {
    r = await call(st, prompt, k ? `${label} retry ${k}` : label)
    if (r && (r.status === 'PASS' || r.cause === 'unrelated')) break
  }
  return r
}

const owner = f => slices.find(s => f && s.files.some(x => f === x || f.endsWith(x) || x.endsWith(f)))

// fix = findings routed back from a failing later stage (loop-back), or null.
const runStage = async st => {
  const fix = pendingFix
  pendingFix = null
  const fixText = items => items.length
    ? `FIX THESE (from stage "${fix.from}", loop ${fix.round}/${fix.max}), then re-run your gate:\n` +
      items.map(f => `- ${f.file || '?'}${f.line ? ':' + f.line : ''} ${f.text}`).join('\n')
    : ''
  if (st.fanout !== 'slices') {
    const r = await withRetry(st, brief(st, fix ? fixText(fix.items) : ''), fix ? `${st.title} fix${fix.round}` : st.title)
    if (r && st.produces === 'slices') {
      // Guard: overlapping slices would let parallel agents clobber each other -> merge them.
      slices = []
      for (const s of r.slices || []) {
        const hit = slices.find(t => t.files.some(f => s.files.includes(f)))
        if (hit) { hit.files = [...new Set([...hit.files, ...s.files])]; hit.task += ' | ' + s.task; log(`slice ${s.id} overlapped ${hit.id} -> merged`) }
        else slices.push({ id: s.id, files: [...s.files], task: s.task })
      }
      if (!slices.length) return { status: 'FAIL', summary: 'no slices returned', findings: [], changed: [] }
      log(`${st.title}: ${slices.length} slice(s)`)
    }
    return r
  }
  if (!slices.length) return { status: 'FAIL', summary: 'fanout without slices', findings: [], changed: [] }
  // Route each finding to the slice owning its file; unowned findings go to every slice.
  let targets = slices.map(s => ({ s, items: [] }))
  if (fix) {
    for (const f of fix.items) {
      const o = owner(f.file)
      for (const t of targets) if (!o || t.s === o) t.items.push(f)
    }
    targets = targets.filter(t => t.items.length)
  }
  const cap = st.parallel || 16
  const out = []
  for (let k = 0; k < targets.length; k += cap) {
    const chunk = targets.slice(k, k + cap)
    out.push(...await parallel(chunk.map(t => () => withRetry(st,
      brief(st, `YOUR SLICE ${t.s.id} — files (only these): ${t.s.files.join(', ')}\nSLICE TASK: ${t.s.task}` +
        (fix ? '\n\n' + fixText(t.items) : '')),
      `${st.title} ${fix ? 'fix' + fix.round + ' ' : ''}${t.s.id}`))))
  }
  const ok = out.filter(Boolean)
  const causes = ok.map(r => r.cause).filter(Boolean)
  const unrel = ok.filter(r => r.cause === 'unrelated')
  return {
    status: ok.length === out.length && ok.every(r => r.status === 'PASS') ? 'PASS' : 'FAIL',
    summary: out.map((r, j) => `${targets[j].s.id}: ${r ? clip(r.summary, 200) : 'agent died'}`).join(' | '),
    findings: ok.flatMap(r => r.findings || []),
    changed: ok.flatMap(r => r.changed || []),
    ...(causes.length ? { cause: causes.includes('change') ? 'change' : 'unrelated' } : {}),
    ...(unrel.length ? { causeReason: unrel.map(r => clip(r.causeReason, 200)).join(' | '), after: [...new Set(unrel.flatMap(r => r.after || []))] } : {}),
  }
}

let pendingFix = null
const loops = {}            // failing stage title -> loop-backs used
let i = 0
let jumped = false
let resumeAt = -1           // after a loop-back target runs, continue here (onFail.then) instead of i+1
let failedAt = null
let blocked = null          // { stage, reason, after } -> status BLOCKED_ORCHESTRATOR
const lastSig = {}          // failing stage title -> failure signature before its previous loop-back
// Signature = failing steps + files; findings without either fall back to their text with digits stripped.
const sigOf = r => !r ? 'died' : JSON.stringify([...new Set((r.findings.length ? r.findings : [{ text: r.summary }])
  .map(f => (f.step || f.file) ? `${f.step || ''}|${f.file || ''}` : clip(String(f.text || '').replace(/\d+/g, '#'), 120)))].sort())
const block = (st, r) => {
  blocked = { stage: st.title, reason: clip((r && (r.causeReason || r.summary)) || '', 300), after: (r && r.after) || [] }
  log(`${st.title}: unrelated to the change -> BLOCKED_ORCHESTRATOR (${clip(blocked.reason, 120)})`)
}
while (i < S.length) {
  const st = S[i]
  if (st.onlyOnJump && !jumped) { i++; continue }
  jumped = false
  phase(PHASE[st.title])
  const fixRound = !!pendingFix
  const r = await runStage(st)
  if (r) { results[st.title] = r; (r.changed || []).forEach(f => changed.add(f)) }
  // A fix round that answers "unrelated" (and nobody reports "change") cannot be fixed in the slices -> stop.
  if (fixRound && r && r.cause === 'unrelated') { block(st, r); break }
  if (resumeAt >= 0) { i = resumeAt; resumeAt = -1; jumped = true; if (!r || r.status !== 'PASS') log(`${st.title}: fix round did not pass — continuing to verify`); continue }
  if (r && r.status === 'PASS') { i++; continue }
  const f = st.onFail
  const stopOn = f && f.stopOn !== undefined ? f.stopOn : ['unrelated']
  if (r && r.cause === 'unrelated' && (!f || stopOn.includes('unrelated')) && (st.onError || 'stop') === 'stop') { block(st, r); break }
  const sig = sigOf(r)
  if (f && loops[st.title] && lastSig[st.title] === sig) {
    failedAt = st.title
    log(`${st.title} FAIL -> stop (same failure signature as before loop ${loops[st.title]})`)
    break
  }
  if (f && (loops[st.title] || 0) < f.max) {
    lastSig[st.title] = sig
    loops[st.title] = (loops[st.title] || 0) + 1
    log(`${st.title} FAIL -> ${f.goto} (loop ${loops[st.title]}/${f.max})`)
    pendingFix = { from: st.title, round: loops[st.title], max: f.max, items: r ? (r.findings.length ? r.findings : [{ text: r.summary }]) : [{ text: 'stage agent died' }] }
    i = idx(f.goto)
    jumped = true
    if (f.then) resumeAt = idx(f.then)
    continue
  }
  if ((st.onError || 'stop') === 'continue') { log(`${st.title} FAIL -> continue (onError)`); i++; continue }
  failedAt = st.title
  log(`${st.title} FAIL -> stop`)
  break
}

return {
  status: blocked ? 'BLOCKED_ORCHESTRATOR' : failedAt ? `FAIL_${failedAt}` : 'PASS',
  ...(blocked ? { blocked } : {}),
  pipeline: P.name,
  stages: S.filter(s => results[s.title]).map(s => ({
    title: s.title, status: results[s.title].status, runs: runs[s.title] || 0,
    loops: loops[s.title] || 0, summary: results[s.title].summary, findings: results[s.title].findings,
  })),
  slices,
  changed: [...changed].sort(),
  // Blocked: only the unblocking actions — P.after (restart/commit) would be wrong on an unfinished run.
  after: blocked ? blocked.after : (P.after || []),
}
