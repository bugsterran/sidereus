# «Pipelines» — design (steps 1-2 built, in live use)

★2026-09-30 scope: per project · view, edit and run all included · not n8n-scale ·
agents configured, attached or imported by the person · model per stage · design documented first.

Per-project standard procedures shown as stage diagrams: pick agents and models per stage, press «Run» to relay it to a session,
and see which stage is running. Sidereus never runs anything itself (AGENTS.md rule 7).

## Phases

★2026-09-30 order changed to runner first — a DM alone is free text the session interprets its own way (agent/model not enforced, lighting only guessed from `agentType`).

| Step | What | Writes |
|---|---|---|
| 1 | fixed runner `pipeline.js` + JSON, Sidereus only · port `sidereus-change` into it as the first proof | `.claude/pipelines/<tpl>.json` · runner copy in `.claude/workflows/` |
| 2 | diagram view + «Run» DM on top of the runner (lighting = runner phase titles, exact) | — |
| 3 | other projects · agent «Import» / «New agent» | project `.claude/agents/*.md` |
| 4 | n8n-style node editor over the same JSON (nodes, edges, loop-back for retry, parallel groups) | same JSON |

Templates: «Change» Design→Implement→Verify→Review · «Bug fix» Reproduce→Root cause→Fix→Regression · «Triage» · «Live verify» · «Cross-review (Codex)».

## Step 1 — runner

Runner `.claude/workflows/pipeline.js` (one fixed file, never generated) · args `{pipeline, request}` · reads `.claude/pipelines/<pipeline>.json` of the project it runs in. First proof: `.claude/pipelines/sidereus-change.json` (same flow as `sidereus-change.js`).
Check: `node scripts/pipeline_check.mjs` (in `scripts/check.sh --fast`) runs the runner's own validate block on every pipeline JSON.

**Orchestrator stage (agent `main`)** — a stage the main session runs itself, no subagent (`hooks/pl_flow.py` `NO_AGENT` skips the `subagent_type` check). Marked by a Bash described `[pl:<pipeline>/<title>]`.
sidereus-change starts with one: the Requirements stage (skill `requirements`) — R1..Rn checkable criteria + one Non-goal, owner confirms once; Design slices name the R ids, Live verify reports each R PASS/FAIL with evidence, the commit body ends with `Done when:` / `Not doing:`.

Review in sidereus-change is two stages (find/verify split, https://claude.dev/blog/solving-code-review-at-anthropic/): «Review-find» = 2 `sidereus-reviewer` (opus, `parallel: 2`), one lens each (AGENTS.md rules + security · logic/regressions), every finding file:line + rule/scenario + diff excerpt, always PASS · «Review-confirm» = `sidereus-review-verifier` (opus) disproves each against the code and `git blame`/`git log -L`, tags Important/Nit/Pre-existing, drops Nits, FAILs only on a confirmed Important from this diff (→ Implement once, then Re-verify), and ends with a metadata-only ledger (id · rule · verdict). Both read `.claude/review-guide.md`. Small change (< ~100 lines, no security/metadata path): one reviewer covers both lenses, its FAIL is final, and «Review-confirm» is declared `[pl-skip:]`.
«Cross-review (Codex)» template (`cross-review`, `sidereus/pipeline_new.py` `_CROSS_TASK`): one `main` stage (title = the Korean for «Cross-review»). The orchestrator runs one Bash described `[pl:<pipeline>/<Cross-review stage title>]` with `codex exec --sandbox read-only "<prompt>"` (review git diff or the named range; blocking findings as file:line + fix; change nothing) — the stage lights from the tag and the Codex run folds under the parent session. PASS/FAIL = Codex blocking findings; the orchestrator relays them and fixes nothing.
  ⚠This stage is billed to the Codex account; every other stage stays on Claude. ⚠`codex exec` is one-shot: it takes no follow-up instructions — to ask again, run a new exec. ⚠The task opens with a subagent guard (a subagent changes nothing and FAILs with cause `unrelated`). ⚠Sidereus never runs or spawns codex; only the orchestrator's own Bash does.
⚠`main` stages work only when the orchestrator runs the pipeline itself — the Workflow runner (`.claude/workflows/pipeline.js`) has no `main` branch and would dispatch it as general-purpose with no owner confirm.

```
{ v:1, name (== file stem), title, use?: one line <= 120, rules?, after?[],
  guards?:{ requireGates?: [<stage title with a graded gate>], maxLoopBacks?: 1..10 },   // enforced by hooks/pl_guard.py
  defaults:{ model: inherit|opus|sonnet|haiku, retry: 0..3 },
  stages:[{ title, agent, task?, model?, skill?, retry?, gate?, parallel?: 1..16,
            produces?: "slices", fanout?: "slices",
            onFail?: { goto: <earlier title>, max: 1..5, then?: <later title>, stopOn?: [] | ["unrelated"] },
            onError?: stop|continue, onlyOnJump? }] }
```

- `title`: any text, 1–40 chars, one line, unique per pipeline (★2026-10-01: stages are tasks the person defines). The 13 recommended titles (saved in Korean; English display names Design · Implement · Verify · Review · Re-verify · Reproduce · Root cause · Fix · Regression · Triage · Live verify · AI config review · Prompt check, `PLG_NAMES` in 06-i18n-w.js) run under their own phase with a default task; any other title needs `task` and runs under the next free custom-stage phase slot 1..12 in stage order (`phaseSlots` in the runner, mirrored by `plgSlots` in web/js/48c), its agent label carrying the real title. Renamed recommended title: the old final-verify title → Re-verify (`RENAMED`, see traps/pipeline.md «Renamed stage title»); a legacy file or tag still runs and lights under the new title. ⇒ `meta` stays a pure literal (13 titles + 12 slots + the load phase); lighting maps phase → stage through the same slot assignment.
  ⚠The custom-stage slot phase names (`phaseSlots`) are reserved; at most 12 custom stages. ⚠New recommended title = edit `meta.phases`, `STAGE_TITLES`, `DEFAULT_TASKS` (and `STAGE_TITLES` in sidereus/pipeline_schema.py, `_REC` in sidereus/pipeline_std.py, `_defaults.json`, `PLG_FAM` and en `PLG_NAMES`, `PLG_TITLES` in 48c); the check fails otherwise. ⚠Unused phases show as empty groups in `/workflows`.
- Every stage returns `{status PASS|FAIL, summary, findings[{file,line,text}], changed[]}`; the next brief carries the request, `rules`, `task`, `gate`, earlier stage summaries and changed files.
- `retry`: rerun the same stage with the full brief on FAIL or a dead agent. `onFail`: after retries, loop back to `goto` with the findings (at most `max`), then continue at `then` or at the stage after `goto`. Exhausted → `onError` (default `stop`).
- Additions beyond the design: `task` (stage instruction) · `rules` (every brief) · `after` (returned as-is for the orchestrator) · `produces/fanout:"slices"` (one agent per designer slice, overlapping slices merged, loop-back findings routed to the slice owning the file) · `onFail.then` + `onlyOnJump` (review fix → final verify only, as in `sidereus-change.js`).
- `gate` is text the stage agent runs itself; the runner never runs shell.
- `skill`: a skill name (`^[a-z0-9-]{1,60}$`); the brief ends with «Follow the <skill> skill.». ⚠Name only — SKILL.md is never read or shown (rule 1). GET lists `skills` (`toolinv.skill_names`: project `.claude/skills` then `~/.claude/skills`, dirs with SKILL.md, no sidereus-off/plugin). Save refuses a new/changed skill not installed (`unknown skill x`); an unchanged one still saves.
- Failure cause: a FAIL result may carry `cause: change|unrelated`, `causeReason`, `after[]` (findings may carry `step`).
  ★2026-10-01 first live run: Verify failed only on a stale screen baseline, yet Verify→Implement looped twice (~3 wasted agents).
  ⇒ `unrelated` (stage FAIL, or a fix round answering it) → run status `BLOCKED_ORCHESTRATOR` + `blocked{stage,reason,after}`; returned `after` = the unblocking actions only. `onFail.stopOn: []` opts out (default `["unrelated"]`).
  ⇒ Same failure signature (failing `step`+`file` set) on two consecutive loop-backs → stop as `FAIL_<title>`.
- ⚠Workflow scripts have no filesystem API: a haiku load-phase agent returns the file text + `wc -c`; the runner rejects a byte mismatch and validates the schema itself.
- ⚠Agent type unregistered in the session (agents added after it started) → the stage reruns as `general-purpose` reading `.claude/agents/<agent>.md`.
- ⚠The validate block must stay self-contained (`P`, `pipelineName`, `STAGE_TITLES`, `MODELS` only) — `pipeline_check.mjs` executes its text.
- Done when `sidereus-change` runs through it live with the same result and `/workflows` shows the stage titles.

## Steps 2–3 — view, run, agents

Status: **2a built 2026-10-01** (view + edit, feature `pipeline`): `sidereus/pipeline.py` (`validate` = Python port of the runner block, ⚠keep both in step — `tests/test_pipeline_schema_mirror.py` runs both on the same boundary cases and repo files; the block includes the legacy-title rename, lengths count UTF-16 units, blanks use JS `trim`) · Tokens › «Pipelines» (`web/js/48-pipeline.js`) · edits = stage `agent`/`model` + `defaults.model` only; save needs the GET `sha` as `base` (409 if the file changed). Tests `tests/test_pipeline.py`.

**2b built 2026-10-01**: «Run» panel (`web/js/48b-pipeline-run.js`) — live cc session of the project with a mailbox login → one-line request → per-stage run-only model selects → DM preview → «Confirm — send» = `/api/dm` relay (thread `pipeline:<name>`); name remembered per session 2 h (localStorage `sidereus.plrun`). Runner accepts `args.models` (checked by its own self-contained block; `pipeline_check.mjs` self-tests it). Lighting = client only from `SESS[].wf` on each state poll (`plPoll`): run name from the loader label `load <name>` (else the DM memory), box state per phase title (run pulse · done · fail · wait), agents · elapsed · «Retry n» (labels ending ` retry k`). No new route or thread. Tests `tests/test_pipeline_run.py`.
Session ↔ project (`plProjSess`, lighting + run picker): `cwd == project` or `project in repos`, cwd matches first. ★2026-10-01 a session started in one repo and editing a sibling repo never lit that repo's pipeline.

**Step 4 built 2026-10-01** (pulled forward; ★2026-10-01 the box row was not n8n-style drag & drop): canvas editor replaces the box row (`web/js/48c-pipeline-graph.js` model · `48d-pipeline-canvas.js` UI). Stage order = the flow chain; loop-back edge = `onFail`. Node position `stage.ui {x,y}` — validated by runner + server, ignored at run time. Save sends the whole stage list (`stages: [...]`, `task` travels as `instr`); server keeps name/v/title/rules/after and each stage's key order. Parallel groups are not in the schema — not drawn.
«Stage catalog» (palette): templates in `sidereus/stage_catalog.json` — `{id, group, title:{ko,en}, role|agent, model, task, gate, gateHint, asserts, loop?, tools:[{id,bin,install,net}]}`; `ko` is the title written. `sidereus/stage_catalog.py` validates each as a one-stage pipeline (`pipeline_schema.validate`), fills `{sidereus}` (this repo, shell-quoted) so gates run from any repo, sends `task` as `instr`, and marks tool `avail` by `shutil.which` only; GET /api/pipelines returns it as `catalog`. 48c `plgAddTpl` adds one (gate prefilled, role -> project agent, loop-back to an earlier match). ⚠A new catalog title needs its English in `PLG_NAMES.en` (tests/test_stage_catalog.py). ⚠Templates add no stage fields.
«Guards» pane (no selection): `guards {requireGates: [titles], maxLoopBacks: 1..10}` (validated in `pipeline_schema`); only stages whose gate matches GET `gate_modes` (schema `GATE_MODES`) are offered; a stage rename (`_rename`) follows `requireGates`. ⚠The save body must send `guards: plgGuards(E.G, gate_modes)`.
Canvas toolbar is its own strip (never over nodes) with «+ Stage» (adds the first unused catalog title after the selected stage) · each loop-back has its own lane below the boxes, label pill on the lane · 100% zoom unless the chain does not fit.
«+ New pipeline» (`web/js/48e-pipeline-new.js`): name + title + template (Change · Bug fix · Triage · Live verify · Empty) → full-file preview → «Confirm» = `POST /api/pipelines/create` (Origin, `known_projects`, validates, creates the dir, ⚠never overwrites). Agents the project lacks become `general-purpose`.
Default tasks (instructions an AI can follow, plus rules): runner `DEFAULT_TASKS` (pure JSON between markers — the one source; `sidereus/pipeline.py default_tasks()` and `pipeline_check.mjs` parse it) gives every title an instruction; `stage.task` is appended as ADDITIONAL INSTRUCTIONS. Node panel shows the default read-only above «Extra instructions». Templates carry no task text, except a custom-title stage («Cross-review (Codex)»), which carries its own `task`.
«Rules»: `rules` goes to the page and saves through the same diff + Confirm (checkable common rules stored as English lines + free text). «Ask AI for a draft»: DM preview → Confirm → `/api/dm` relay to a logged-in live session, which writes the file itself (Sidereus writes nothing); the list re-reads every 20 s for 10 min.

- Place: own main tab «Pipelines» after Branches (★2026-10-01 moved out of Tokens — pipelines are not token usage); hidden when the feature is off. ⚠An old stored Tokens segment `sidereus.tkview=pipe` falls back to Usage.
- Server `sidereus/pipeline.py` (after `toolinv` in STAGE3 order): `GET /api/pipelines?proj=` · `POST /api/pipelines/save` (first call `dry` → unified diff, second writes).
- Stage rename: `save` dict edit `{stages: {old: {title: new}}}` (or a changed title in the canvas list) renames the stage and every onFail `goto`/`then` in one write; `title_err`: trimmed, not empty, ≤ `TITLE_MAX` 24, no `/` `]` `|` or line break, unique. Canvas: title input in the node panel (48d `plRetitle`), «Save» diff warns when a run of that pipeline is open (`plRenameWarn`: its running tags keep the old name). ⚠A recommended title renamed to a custom one needs a `task` (schema).
- JSON: schema in step 1 · `v:1` so step 4 can migrate.
  - `model`: `inherit | opus | sonnet | haiku`.
  - `agent`: candidates = project `.claude/agents` + `~/.claude/agents`; «Import» copies an agent file from another project / `~/.claude/agents` into this project; «New agent» writes a new `.md` — both through the same guards.
- Live lighting: a Workflow run's phase title == stage title (`plLight`); otherwise the row's `plrun` (`sidereus/pl_runs.pl_model`: runs.json outcomes + loop-backs + tagged agents + live subs + main mark) → `plPrLt` (48b). The client renders only — a stage absent from `plrun` is wait. The newest 2 runs carry `ag`; `{aid:"main"}` = the orchestrator itself.
- Under the canvas: one row per stage (outcome · ↺n · agents · elapsed · newest agent type, `plRunTable`). Row or running-node click = newest agent's work log, or a chooser for 2+ (`plNodeWork`, 48d).
- Loop-back edge: `.plel.pulse` (flowing dash, source → target) only while the target runs with `from[source]`; afterwards the dashed lane keeps «↺ n» on its pill. Reduced motion = static thicker line.
- «Run»: pick a live session of that project → one-line request → DM preview (pipeline name, the request, and each stage with agent·model in order) → send on confirm via `/api/dm`.
- Client: `web/js/48-pipeline.js` · `web/css/43-pipeline.css` — stage boxes with arrows (flex, no SVG), `<select>` for agent and model per stage.
- Demo: one project with «Change» bound, a live run on Verify, «Retry 1».

## Run modes

★2026-10-01 Workflow runs cost many tokens, so the session runs the pipeline directly by default.
- **Direct run in the session (default)** — DM tells the session to run the stages itself with the Agent tool (agent + model per stage, default task + stage task + rules). Loop-back (`onFail.goto`) and retry = `SendMessage` to the earlier agent (no cold start); parallel/fanout = several Agent calls in one message.
- Lighting: each Agent description starts `[pl:<name>/<stage title>]` (label cut at 40 chars ⇒ keep names short); the server folds tagged agents into `plrun`. Untagged agents light nothing (no inference).
- **Workflow** — the old path (`pipeline.js` runner, phase lighting). Choice remembered per pipeline (localStorage `sidereus.plmode.<name>`).
- `.claude/pipelines/_defaults.json` = copy of the runner's `DEFAULT_TASKS`; `pipeline_check.mjs` fails if they differ. ⚠`_`-prefixed files are not pipelines.

## Workflow view (read-only)

The name list ends with a «Workflow» group: one button per Workflow-tool run in the project (`SESS[].wf`, runs named `pipeline` are the runner and stay on the canvas). A click shows the run instead of the canvas: done/total agents, elapsed, tokens (`run.tok`), phase boxes lit like canvas nodes, and an agent table (row = session work log). Running ones also appear in «Running N». Metadata only: phase titles, one-line labels, states, times (`web/js/48g-pipeline-wf.js`).
- ⚠Nothing is editable or sent from this view.
- ⚠Two windows (`sessions._wf_sets`): `wf` = running + finished < 300 s (`WF_KEEP_S`; tree, «Running», attention, saver); `wfh` = older finished runs < 6 h, newest 10 per session, always `run:false` — read only by this view. Don't widen `wf` instead: every other consumer treats it as «now».

## Session brief (SessionStart hook)

★2026-10-02 owner-approved: new pipelines reach sessions automatically. `hooks/pipelines_brief.py` reads `<cwd>/.claude/pipelines/*.json` and adds one line per pipeline (`name — title · when: <use> · stages: A → B` + `· missing agents (run as general-purpose): x` when a stage agent is neither builtin nor in project/user `.claude/agents/*.md`) + the «run it directly, tag `[pl:<name>/<stage title>]`, pass agent/model, declare skips» line as `additionalContext`.
- Enforcement (`hooks/pl_flow.py` PreToolUse): undeclared jump denied every time (declare with a Bash description `[pl-skip:<name>/<stage>] <reason>`) · Agent/Task with another `subagent_type` (general-purpose accepted when the stage agent is not installed) or `model` (omitted = mismatch; override `[pl-model:<name>/<stage>=<model>]`) denied · unknown stage title denied · untagged SendMessage denied while a run is open (45 min). Outcome per stage in `plmark/<sid>.runs.json` `runs[name].st` = `{title: {s: run|done|skip|back|fail, t0, t1, n}}` (`back` = onFail loop-back, canvas «Sent back» ↺, becomes `done` when the stage passes later; `fail` = shell `[pl-end:…|fail]` only). «Apply» off = no deny.
- Run boundary: a new run opens on a tag after `end`, after 6 h idle, or when the first stage is tagged (Pre or `[pl-skip:]`) while the open run is past it — that run is closed (cur «run» → done) first. A re-mark at cur and a declared loop-back to the first stage (cur's `onFail.goto`, pending `ret`) stay in the run. Replaced runs: `runs.json` `past[name]`, oldest first, `PAST_MAX` = 5, only `st lb cur end t0 t1` (`PAST_KEYS`: what pl_runs reads; runs.json over its read cap parses as nothing).
- In-flight + untagged Bash: `runs[name].inflight[title]` drops by one on every Post of that stage, background included (a background dispatch gets only that one Post; skipping it leaked the count). An untagged main-session Bash Pre (no `[pl:-]`/`[pl-`) while a run is open gets `additionalContext` naming the run and stage, never a deny; `runs[name].nudge_t` limits it to once per `NUDGE_S` = 600 s, saved under the lock before printing (lock/save fails = silent).
- HEAD stamps: `runs[name].h0` = short HEAD of `r.proj`'s repo at run start, `h1` = at the latest stage change (`_head`, 1 s timeout, one git call per transition; absent when git fails). ⚠Never stamped in `_commit_close` (Pre fires before the commit exists).
- Loop-back edges: `runs[name].lb` = `[{f, g, n, t}]` (from-stage → goto-stage, count, last time; ≤16 in the hook, counted on the loop-back Pre and on shell `[pl-end:…|fail]`; a denied dispatch records nothing). Row `plr[].lb` via `_loopbacks` (titles ≤40, `n` int ≥1, ≤`PLR_STAGES_MAX`); `loops`/`ret` never reach a row.
- `use` = «When to use» in the canvas «Default» panel (saved through the same diff + Confirm). ≤2.5 KB (extra pipelines → «+N more»); no pipelines → prints nothing; bad JSON skipped; never fails the session.
- ⚠Metadata only — never `task`/`rules` text. Tests `tests/test_pipelines_brief.py`.
- «Apply» mode (pipeline tab, `plApplySeg`): `auto` = the «run it directly» line · `ask` = ask first with AskUserQuestion (fitting pipelines + a proceed-without-pipeline option; questions/one-line fixes skip it) · `off` = prints nothing. Stored in config.local.json `pipeline_apply` `{mode, projects: {exact cwd: mode}}` (POST `/api/pipelines/apply`, viewer Origin + confirm; `pipeline_projects.apply_set`). Read at SessionStart: new sessions only. ⚠Any config problem = `auto`. Tests `tests/test_pipeline_apply.py`.
- Missing agents also show in the canvas Agent select (`name (missing → general-purpose)`, 48b `plAgMissing`) and as one line at the end of the run DM.
- Registration (user, by hand — Sidereus never writes it) — add to `~/.claude/settings.json` `hooks.SessionStart`:
  `{"matcher": "startup|resume|clear|compact", "hooks": [{"type": "command", "command": "/usr/bin/python3 $HOME/.mailbox-mcp/hooks/pipelines_brief.py", "timeout": 10}]}`

## Import (★2026-10-01 owner-approved)
- Rules panel: follow-the-project-rules-file option (AGENTS.md|CLAUDE.md) (repo root, existence only) = one line `Follow <file> in the repo.`; nothing copied.
- «Import from another project»: create with `from:{proj, name}` (both known projects, source must validate); agents missing here → general-purpose, returned as `replaced` and shown in the preview.
- «Ask AI for a draft» › source «Port an existing workflow»: `.claude/workflows/*.js` names only (`workflows` in GET) — ⚠Sidereus never reads the JS; the DM asks the session to port it. «Port from a rule document» : same, for AGENTS.md/CLAUDE.md — the session extracts the delegation flow.
- Live-run look (only while a run is known; editing stays calm): running = family-colour glow + spinner (no border streak), flowing dashes and a travelling dot on its incoming edge · done = ✓ pop + green flash · fail = ✗ + shake (pop/shake only on a state change, not every 2.5 s repaint) · retry = «Retry n» badge + one orange dot on the loop-back lane · waiting dimmed to 0.38 · header = gradient bar (done / stages) + elapsed, green «done» at the end. All motion off under `prefers-reduced-motion`. ★2026-10-01 made more visible and colourful.
- Reorder: panel «Order» ◀ ▶ swaps with the neighbour (`plgMove`, places swap too); dragging a node onto a flow edge (10px) inserts it there, neighbours joined, then re-flows like «Arrange» (`plgEdgeAt`/`plgInsertAt`). Single chain only; loop-backs keep their stages; unsaved until «Save».
- Stage colour: `stage.ui.color` `#rrggbb` (lower-case; server/runner validate, a bad value is dropped on save) → node style `--pfc` overrides the family `--pf` everywhere (bar, tint, glow, rain, ports, edge ends); light theme mixes it 72% toward black. Panel «Colour»: 8 swatches · colour input · «Default».
- Node colour by stage family (`plgFam`): plan purple · build blue · check green · review amber · custom teal; lighting borders win (`:where`).

## Auto suggestions
★2026-10-01 a matching suggestion loads automatically when one exists.
- GET `suggest[]` (≤2, validated): agent **names** → roles (`_ROLES`: triage · design/spec · fix · implement/-be/-fe/dev · gate/verifier/qa · review · live/verify · probe/measure), best agent = project `.claude/agents` first, then global `<dir name>-*` or sharing a project agent's first segment (`<prefix>-*`); ⚠no shorter fallback (a shorter shared prefix picked other projects' agents); no match = no stage. «Bug fix» needs a fix agent, «Change» an implementer.
- A project with no pipelines opens on the first suggestion (dashed «Suggested · not saved»); «Save this suggestion» = create `template:"suggest:<key>"` (server rebuilds it) + preview + Confirm. ⚠Never auto-saved, never sent; canvas edits before saving are not kept.

## Standard drafts
★2026-10-01 drafts researched from public per-task standard procedures.
- `sidereus/pipeline_std.py` `STD`: 11 per-task drafts (bugfix · feature · refactor · perf · security · deps · incident · review · hook · skill · mcp), each citing its public source (`src`). Roles P plan→design/triage · B build→build/fix (fix first for bugfix/security/incident) · C check (model sonnet) · R review · L live · M probe.
- GET `std[]` = suggest-shaped rows + `std:true, src, chain:[{title, role, opt}], gp:[titles]`; only drafts that validate. Create with `template:"std:<key>"` → dry reply `replaced: gp`.
- ⚠No matching agent = `general-purpose` + title in `gp`; a stage is never dropped. Optional stages are in `chain` only, not in the saved file. The 13 recommended titles carry no `task` (runner DEFAULT_TASKS); other titles carry a short English one.
- ⚠Server rebuilds the draft from `STD`; stages sent by the client are ignored.

## Rules
- ⚠Never read `<sess>/workflows/wf_<id>.json` — it holds promptPreview/resultPreview/args/script (rule 1). Payload is an allow-list: path, sid, model, agentType, label/phase, counts, times.
- ⚠Never generate or hand-edit workflow JS from the UI — arbitrary code with no preview a person can judge. Declarative JSON + one fixed runner only (step 1).
- ⚠Writes: viewer Origin + `known_projects()` allow-list + backup to `DATA_DIR/pipeline-bak` + diff confirm; name `^[a-z0-9-]{1,40}$`; gate ≤200 chars, one line, stored as text, never run by Sidereus.
- Project picker/allow-list also include `DATA_DIR/pipeline-projects.json` (≤50) = folders the person added with «+ Add project» (`POST /api/pipelines/projects/add|remove {path}`, viewer Origin; ~ expanded, realpath, a real dir strictly inside home; × removes the entry only). ★2026-10-01 a repo with no session was missing from the chips; adding projects implicitly was rejected: ⚠never remember projects automatically.
- Built-in (`"builtin": true`, ★2026-10-13 `security-checks`): Sidereus plumbing (the security runner). Hidden from GET /api/pipelines (list, project counts, borrowed rows — `pipeline._listed`) and from the session brief (`pipelines_brief._line`). ⚠The file stays in `.claude/pipelines/`: `pl_flow`/`pl_guard` resolve `[pl:<name>/…]` tags and gates there, and the relay DM names it by absolute path.
- `security-checks` stages: 1 scanners (→ `checks-security.json`, gated) → 2 threat-model review (opus, no gate): reads `<repo>/.oss-scanner/threat_model.md` else `<repo>/threat_model.md`; `--log-show` → `--mark <slug>@<file> resolved` for fixed ones → new findings as TSV to `arch_checks.py --log-review` → `$MAILBOX_DIR/arch/<key>/security-log.jsonl`. ⚠Findings are model-generated and unverified. ⚠The agent never marks false-positive (human, via CLI). No threat model = one line pointing to `templates/oss-scanner/`, not a failure. Runs monthly alongside `deps-audit`.
- One report per runner run (`sidereus/sec_report.py`): `arch/<key>/security-report-YYYYMMDD-HHMM.md` beside `security-log.jsonl`, written after `log_append` (the delta compares the last two scan records, never old Markdown), newest 10 kept, same-minute rerun replaces it. Deps lines = `deps_audit.collect()` in-process, only when the repo is this checkout (else «not applicable»). `deps-audit` and `release` «Check» stages run `arch_checks.py --repo <this repo> --category security` (release adds `--dev`) and read the report named on the summary line (`· report <name>`).
- «Force delete» (48 `plBody`): a file that breaks the schema (no canvas editor) shows «Force delete» under its error list — same `POST /api/pipelines/delete` (Origin, allow-listed project, symlink refused, preview naming the file, confirm, move to `pipeline-bak`, never unlinked); also for an unreadable file without `sha`. ⚠Borrowed rows still delete only in their own project. Tests `tests/test_pipeline_force_del_js.py`, `tests/test_pipeline_del.py`.
- Rule 7's write allow-list must gain `.claude/pipelines/` (AGENTS.md) when step 1 is built.

## Known limits

- Stages that use `general-purpose` (sidereus-change does) cannot light by `agentType` — phase-title match comes first for Workflow runs.
- Plain-subagent runs could match several templates; only the one DM'd to that session lights (name kept in viewer memory for 2 h).
- Only `~/.mailbox-mcp` has a workflow today (`sidereus-change.js`, 6 phases); other projects have agents only.

## Prior art (researched 2026-09-30)

No tool combines per-project procedures + per-stage agent/model + diagram + live stage; each covers one or two.

| Tool | Procedures | Agent+model per stage | Diagram | Live stage | File |
|---|---|---|---|---|---|
| Claude Code Workflow | yes | yes | no | `/workflows` (per phase: agents · tokens · time) | JS + `meta.phases` |
| Copilot custom agents | via `handoffs` | yes (`model` array = fallback) | no | sessions only | `.github/agents/*.agent.md` |
| Kiro | spec req→design→tasks + hooks | yes | no | task list [?] | `.kiro/agents/*.json` |
| Cursor · Codex · Factory | no | single agents/roles | no | no | md / toml |
| n8n · LangGraph · Dify · Flowise | graph | per node | yes | yes | JSON / YAML |

Borrowed into the schema:
- ⇒ `stage.title` == runner `phase()` title == `meta.phases` entry — required by Claude Code, so lighting can rely on it ([docs](https://code.claude.com/docs/en/workflows)).
- ⇒ pipeline `defaults{model:"inherit", retry}` overridden per stage (LangGraph `setNodeDefaults`, Factory/Copilot `inherit`).
- ⇒ `retry` (rerun same stage, n8n `maxTries`) is separate from loop-back `onFail:{goto:"<Implement stage title>", max:2}` (Kiro review loop, Flowise Loop) · per-stage `onError: stop|continue|goto` (Dify, n8n `continueOnFail`).
- ⇒ «Run» = Copilot handoff `send:false` pattern: prefilled, a person sends.
- ⇒ stage box shows agents · tokens · elapsed · retry n, like `/workflows`.
- ⚠n8n Agent V3 + `retryOnFail` drops context (known bug) — retry must restart the stage agent with the full brief, not resume.

## Model per stage

★2026-10-01 added.
- Stored: `stage.model` (else `defaults.model`, `inherit` = session model). sidereus-change: Verify · Re-verify = sonnet (gate output is machine-judged).
- ⇒ Step 2 UI: model `<select>` per stage box (inherit · opus · sonnet · haiku), saved with diff + confirm.
- ⇒ Run-time override: «Run» may pass `args.models = {"<stage title>": "<model>"}` for one run only; the JSON is not changed.
- ⚠Lower a model only on machine-judged stages (gates, lookups); design · diagnosis · review stay on the strong model (global rule 2026-09-10).

## arch-map: architecture style

- Stage 1 writes `plan.arch` = {style, framework ≤80, units ≤120, evidence: 1..5 repo-relative files}; modules are cut by that unit. Stage 2 may set module `role` (layered · hexagonal · mvvm only).
- Gate (`arch_verify.run`) adds `verify.json` `style` (each evidence file must exist at the commit) and `dev` [{i, a, b}] = verified non-estimated import/call edges whose role pair is outside `STYLE_FLOW`.
- ⚠Advisory only: a missing/invalid arch or any deviation never changes the rate, the summary line or the exit code. Old plans/maps without `arch`/`role` load as `style: null`, `dev: []`.

## arch-map: process flows

- Stage Draw flows (between Draw modules and Verify; opus) writes `S/flows.json` = {v:1, repo, commit, flows: ≤40 × {id, name, entry:{kind http|cli|job|event|hook|mcp, label}, steps: 1..40 × {from, to, label, evidence:{file, line, symbol}, est?}}}.
- Gate (`arch_flow.run`, called by `scripts/arch_verify.py`) checks each step with the edge rules (why `nomod|owner|overlap|nofile|range|nosym|bad|nodef`), writes `flows.verify.json` and appends ` · flows a/b (steps c/d)` to the rate line.
- ⚠Advisory only: flows never change the edge rate or the exit code; a broken flow is dropped (counted), a broken file is ignored. `/api/arch` `flows` = [] for old stores.

## arch-map: schema v2

- Plan adds `groups` [{id, name, file}] (container/boundary cuts, one proof file each), `entries` [{id, ext http|hook|mcp|cli|file|job, file}] and `stores` [{id, ext store|file|queue|db, file}].
- Draw modules writes `map.json` `v: 2`: every module has `layer` (entry·ui·api·service·domain·data·infra·shared; role table in the task), `group` (plan group id), `summary` ≤120 (own words); entry/store modules (`kind entry|store`), `owns` [store ids]; edge kinds add `read|write` (→ store, evidence in from), `serve` (entry →, evidence in to), `event`.
- ⚠A v1 base map is never reused: the plan marks every module changed. On a failed gate, Verify reports the schema line(s).

## Evaluation: seeds, red check, flaky gates

`scripts/pl_eval.py` (core `sidereus/pl_eval.py`) answers «does this pipeline catch known defects, and can its gates fail at all?». Store: `DATA_DIR/eval/` only, key = `arch_verify.repo_key`.

- `seeds --repo R --set F | --check` — `{v:1, seeds:[{id, kind secret|dep|sast|logic, file, line?, rule?, pkg?, expectStage, holdout?}]}` → `eval/<key>/seeds.json` (0600). Prints counts only.
- `score --repo R --pipeline P.json [--findings F]` — each seed is matched in its stage (`expectStage` = stage title, or a catalog id / title.ko → that title or the first stage with the same gate mode): kind → tool (secret gitleaks · dep npm-audit|osv-scanner · sast semgrep|bandit · logic `--findings` only), same file, same rule/pkg (sast: a dotted semgrep id compares by its last segment), line ±2. Findings come from the stage's gate mode (checks-security → `checks-security.json` at HEAD). Writes `eval/<key>/<commit>/eval.json` and an evidence row `kind eval, mode eval-catch` (rc 0 only if every public seed was caught).
- `redcheck --pipeline P.json --stage T --repo R [--timeout 600]` — `git clone --shared` into a temp dir, one injected break per gate mode (checks-security: a fake `api_key` file; fast/full: syntax error in one .py), producer (`arch_checks.py --repo <clone>`) then the gate verbatim with `MAILBOX_DIR`/`SIDEREUS_EVIDENCE` in the temp dir. Verdict → `eval/redcheck.json` under `sha1(gate)[:16]` + evidence row `kind red, mode redcheck`.
- Graded stage = has a gate · red check passed · its mode is not flaky (both rc 0 and rc≠0 on the same clean commit within 14 days). View API: `load_eval`, `redcheck_status`, `flaky_modes`, `graded_summary`.
- ⚠The gate runs where the pipeline's project dir maps into the clone; a pipeline file outside the target repo runs its gate in that project dir (the clone's break is then unseen → fail).
- ⚠Holdout ids never leave seeds.json (counts only). Evidence readers keyed on `kind: "check"` (pl_guard, harness) ignore eval/red rows.
- View: GET `/api/pipelines/eval?proj=&name=` (`sidereus/pl_eval_view.py`, counts and verdict words only) → «Evaluation» panel (`web/js/48i-pipeline-eval.js`).
- `security: {n, m, checks:[{id, v}]}` = supply-chain posture (`sidereus/pl_scorecard.py`, subset of OpenSSF Scorecard): security-policy · license · pinned-deps (each manifest has its lockfile in its dir or an ancestor) · dep-update-tool · secret-gate · sast-gate · dep-audit-gate · binary-artifacts. Verdict pass/fail/na from tracked file names (`git ls-files`) and the project's pipeline gate strings only — no contents, no network, no tool runs; n = passes, m = checks not na (the three gate checks are na without pipelines). Adapt the file/tool lists in `SC_*`.
- Per stage `ci: {lo, hi}` (and `holdout.ci`) = 95% Wilson interval of caught/n in whole percent (`pl_eval_view.wilson`, z 1.96; n 0 → null). ★7/7 → 65–100, 0/1 → 0–79: few seeds leave a wide range.
- Per stage `agree: {k, n}` = clean `kind: "check"` runs of the stage's gate mode at HEAD (else the commit of its newest row), k = runs matching the majority verdict (`pl_eval.gate_agreement`, same 14-day filter as `flaky`; null when the mode has no rows). ⚠check.sh records a short sha, so heads match by prefix.
- Auto score: when a run ends (last stage back · `[pl-end:]` · main's `git commit`) and `eval/<key>/seeds.json` exists, `hooks/pl_flow.py` launches `pl_eval.py score --auto` detached (argv list, no wait, output to devnull). `--auto` waits out `index.lock`, then scores once per (pipeline, commit): an empty O_EXCL claim `eval/<key>/<commit>/auto-<name>`. ⚠Sidereus itself never runs it.
- «red check needed»: a gated stage with no `redcheck.json` entry for its current gate text (never checked, or the gate changed). The panel badge copies the exact `pl_eval.py redcheck` command; the header chip lists them in its tooltip. Nothing runs automatically.
- Suggestions (`pl_eval_view.suggest`, rule table, no AI; codes + parameters only): ungated stage that missed seeds → `add-gate` (catalog template whose tools catch that seed kind, fewest tools) · red «fail» → `tighten-gate` (mode flags) · unstable → `unstable` · holdout missed with no review/test stage → `add-review` · no red-check record → `redcheck`. Each row: «Fix it myself» (selects the stage, pre-fills the template gate or filters the catalog; unsaved until «Save») or tick + «Ask AI» (preview + confirm → `/api/dm` relay to a session inside the project, same targets as the checks «Request fix»).

### Reading the «Evaluation» panel

- Columns: «Catch» (seeded defects found / seeded), «Red check» (pass · fail · skip), «unstable».
- A gate counts toward «Gates n/m» only after its red check passed (seen failing on a deliberately broken copy) and while it is not unstable (passed and failed on the same commit). The rest show as amber «gate not red-checked k».
- «95% lo–hi%» beside a catch count = the range the true catch rate likely sits in; it narrows as more defects are seeded.
- «k/n agree» = runs of the gate on one commit that gave the majority verdict.
- «Holdout» shows counts only.
- With `seeds.json` present, each finished run is scored once per commit in the background; the red «red check needed» badge copies the command to run.

### Reading the result layer

The panel's «Result layer» block states facts per pipeline, no score (`sidereus/pl_outcome.py`, sentences `OC_SENT`).

- Gate: graded gates / gates (same as «Gates n/m»).
- Procedure: ended runs in the ledger `eval/<key>/runs.jsonl` and order violations the `pl_flow` hook blocked (deny code `jump`).
- Result: of the gate PASSes in the last 30 days, how many later broke (reverted · gone · broke, as in the harness «Kept» check) and how many had a commit within 14 days touching a file that PASS changed («fix followed», file names only).
- Review loop-backs: share of runs with a loop-back from a review stage, last 30 days vs the 30 days before. A falling share with «fix followed» flat means review finds less, not that code got better — read the two together.
- Report: `scripts/pl_report.py` writes the same sentences plus the broken / fix-followed PASS list (short sha, file names) to `eval/<key>/reports/YYYY-MM-DD.md`; a run end regenerates it when the newest is older than 7 days.
- ⚠«Fix followed» is a proxy: any commit touching the same file counts, including unrelated work. It flags where to look, not a defect count.

Basis: seeded defects stand in for real ones because mutant detection correlates with real-fault detection (Just et al., FSE 2014); a gate that passes and fails on the same code is flaky and its verdict carries no signal (Luo et al., FSE 2014); a check counts only once it is seen failing on a known-bad input, as SWE-bench Verified validated each task's tests against the broken and fixed code.

Adapting it: seeds and the answer key are data — write your own `seeds.json` (schema `seed_errors`) and store it with `pl_eval.py seeds --set`. Matching is `matches()` and the kind → tool map `KIND_TOOLS`; the line window is `EVAL_LINE_K`, the unstable window `EVAL_FLAKY_DAYS`, the graded rule `graded_summary()` (all in `sidereus/pl_eval.py`). Breaks per gate mode are `inject()` in `scripts/pl_eval.py`; a new gate mode needs a row in `pipeline_schema.GATE_MODES`. Pass/fail of `score` (every public seed caught) is in `cmd_score()`.
