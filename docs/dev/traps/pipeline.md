# Traps — Pipelines: runs, stage hooks, gates and evaluation

Conventions (entry shape, `★` `⚠` `⇒`, `§N`, `:NNNN`): [TRAPS.md](../TRAPS.md). Newest first within an area; new traps go at the top of their area.

## Runs, stage hooks and evaluation

- ⚠**`codex exec` hangs on an open non-TTY stdin** (★2026-10-21, codex-cli 0.163.0). From a Claude Bash call it waited 10+ min with no output and no rollout file; with `< /dev/null` it finished in about a minute. ⇒ The «Cross-review (Codex)» template task (`sidereus/pipeline_new.py` `_CROSS_TASK`) runs it with `< /dev/null` and ends with `[pl-end:<name>/<stage>]` (a last `main` stage otherwise leaves the run open). ⚠Never drop `< /dev/null` from the command. Test: `test_create_cross_review_keeps_main_r1`.

- **`_touched` lowercases the whole tool-input blob on Windows** (hooks/pl_flow.py `_pkey`).
  - Cause: inputs mix `\` and `/` (`~/x` expands onto a `C:\` home) and Windows paths ignore case, so `C:\u\agent` never matched `c:/u/agent/docs`.
  - ⇒ Both the blob and each owner path go through `_pkey` (`\`→`/`, lower) on Windows only; POSIX is unchanged.
  - ⚠The result is a membership test only. Never return or show the `_pkey` form; the owner path is returned in its original spelling.

- ★**A subagent's `git commit` must not close the pipeline run** (2026-10-08). Hook events from inside a subagent carry the parent's `session_id` plus `agent_id`; `_commit_close` (hooks/pl_flow.py) took a stage agent committing its own slice as the end of the change and set `end`, so the timeline showed «Stopped · Implement» while that agent was still running.
  - ⇒ `_commit_close` returns when `agent_id` is present; only the main agent's commit closes a run. Test: `test_subagent_commit_keeps_run_open`.
- ⚠**A subagent's commit stamps its own stage, not `cur`** (2026-10-09). A slice agent of Implement that commits after the run moved to Verify put `cm` on Verify. ⇒ `_cm_stage`: stage whose `ag` lists the `agent_id` (SendMessage `to`, or a background launch's `agentId` — structured key first, regex fallback), else the single stage whose pipeline `agent` == `agent_type` (running one preferred), else `cur`. ⚠`agent_type` on subagent hook events is not seen in repo fixtures — `.get()` only, falls back to `cur`. ⚠The receipt is matched JSON-dumped: a letter before `agentId` blocks the match (`subagentId`) unless it is an escape (`\nagentId` reads `nagentId`). Tests: `test_subagent_commit_*`, `test_bg_*`.
- ⚠**Red check on Windows: node_modules is a junction, never recurse into it** (2026-10-13). Without admin/Developer Mode `os.symlink` fails, so `pl_eval._link_dir` falls back to `mklink /J`; cleanup must not delete through it into the real repo's node_modules. `shutil.rmtree` stops at junctions since Python 3.8 — keep `_rmtree` on rmtree, never a hand-rolled walk. Neither link works ⇒ the red check reports skip («node_modules not linked»), not a crash.
- ⚠**Evidence `head` is a short sha, `_head()` is full** (2026-10-13). `check.sh` records `git rev-parse --short`, the eval code reads the full sha. ⇒ `pl_eval.agreement` matches commits by prefix. ⚠`flaky()` still compares exactly and only works because every evidence row is short — switch it to the same prefix match before any producer records a full sha.
- ⚠**Pipeline «Arrange» left the chain near the top** (2026-10-13). It called `plWrapBest(E, cv, true)` without `ctr`, so `plFit` kept its top anchor (`ch/6`) and never ran `plCentre`. ⇒ «Arrange» passes `ctr` like «Fit to view» (48d-pipeline-cv-input.js); the zoom is still kept (`keepZ`). ⚠`plCentre` centres an axis only when the graph fits on it — a taller chain still starts at the top.
- ⚠**Run attached to the wrong project when both repos have the same pipeline name** (2026-10-14). `hooks/pl_flow.py` `_project()` ranked by stage/agent fit and used cwd only as a tie-break, so a cd'd repo beat the cwd repo for a shared pipeline name. ⇒ Order is now cwd or its git root (file existence, not cached `.dirs`) → open run's keep → newest cd target; the shared «session pipeline dirs» block reads multiple cds in one command newest-first. ⚠Never put fit scoring ahead of cwd. Test: `tests/test_pl_session_dirs.py`.

## Stage lighting and run tracking

Moved from «Sessions: state, subagents, external CLIs».

- **A running pipeline row drew another session's abandoned run** (`48b` `plLiveRun`, `hooks/pl_flow.py` `_known_owner`/`_touched`).
  - Cause: `plLiveRun` took any project session's `plrun`; a tagged session with no run record (cwd without pipelines, so `pl_flow` recorded nothing) showed a 2 h old run (done, end=0).
  - ⇒ While a session carries a live `[pl:name/]` tag only its own `plrun` counts; with none, the tag alone lights its stage. `pl_flow` finds the home among known projects owning the file, narrowed by paths in the transcript tail.
  - ⚠A pipeline name alone is ambiguous (bugfix.json had 3 owners) — never pick a home by name without the session's touched paths.
- **Run on another project's same-name pipeline drew the others as wait** (2026-10-14; `48-pipeline.js` `plHomes` fit scoring, `48b-pipeline-run.js` `plLiveRun` stand-in).
  - Cause: client fit scoring ignored `plrun.proj`; the tag-only stand-in then drew the other projects' stages as wait.
  - ⇒ `plHomes` returns the recorded `plrun.proj` before scoring; `plLiveRun` drops sessions whose run of that name has another `proj`. Scoring only places runs with no project.
- ★**Pipeline direct-mode lit nothing for untagged subagents** (2026-10-01; a session outside Sidereus ran a `bugfix` pipeline untagged).
  - Cause: lighting required `[pl:<name>/<title>]` in the label; sessions outside Sidereus's AGENTS.md never tag.
  - ⇒ superseded by stage inference (next entry).
- ★**Inferred stages lit every stage sharing an agent** (2026-10-05; the Verify / Final verify stages both `sidereus-verifier`, a stray reviewer lit the Review stage alone).
  - Cause: the untagged fallback mapped an agentType to all its stages, with no run start and no per-agent memory.
  - ⇒ `plAssign` (`web/js/48b-pipeline-run.js`): tag wins; one stage per aid, fixed once seen (SendMessage keeps the aid); new aid = first candidate after the highest seen stage, else latest at/before it; a run starts only on the first stage's type or 2+ types; owner tie → tab pick or nothing; `inf` marks «Estimated». `tests/test_pipeline_run.py`, `test_pipeline_live.py`.
  - ⚠Any `[pl:` text in a label disables inference (other pipeline, `[pl:-]`); `main`/generic types are never inferred.
  - ⇒ superseded by plrun (see «Client-side run stitching drifted from the hook record» below; server `sidereus/pl_runs.pl_model`).
- ★**Pipeline stages the MAIN agent runs never lit** (2026-10-01).
  - Cause: lighting read only subagent labels (`SESS[].sub`); the main agent has none.
  - ⇒ hook `~/.claude/hooks/pl-mark.py` writes `DATA_DIR/plmark/<sid>.json` on a `[pl:<name>/<stage>]` Bash description; `agents.plm_of` → row `plm` (≤ `PLM_LIVE_S` 120 s old) → 48b `plSubsOf` adds it as sub `main: [pl:…]`, id `main:<sid>`. `tests/test_plmark.py`.
  - ⚠Only `name`/`title`/`age` reach the page — never the file's `cwd` or anything else. `main` never uses the agent-type fallback.
  - ⚠Shell-marker marks (`"hold": 1`, non-Claude CLIs) get no per-tool refresh — 120 s would drop a running stage; they live `PLM_HOLD_S` (45 min = `pl_flow.LOST_S`) and `ext_rows` attaches the same `plm`.
- ★**A pipeline created mid-session was never tagged** (2026-10-06, `db-migration.json` added after session start; Sidereus lit nothing). Cause: the tag guidance came only from the SessionStart brief.
  - ⇒ `hooks/pipelines_brief.py` also runs on UserPromptSubmit and re-briefs when names/stage titles change (hashes in `plbrief/<sid>`); `hooks/pl_mark.py` denies the first untagged Agent/Task per session in a pipeline project (`plbrief/<sid>.nudged`). Tests `test_pipelines_brief.py`, `test_pl_mark_hook.py`.
  - ⚠No marker written = no deny, or every dispatch would be blocked. `[pl:-]` counts as tagged; the «Apply» (enforce) toggle off silences both.
- ★**Stage hand-off hook cannot live on SubagentStop** (2026-10-06): SubagentStop carries no description (no `[pl:]` tag) and cannot add context to the main agent.
  - ⇒ `hooks/pl_flow.py` on PostToolUse of `Task|Agent|SendMessage` (tag from description/summary); run state in `plmark/<sid>.runs.json`.
  - ⚠Never write `plmark/<sid>.json` from it — `agents.plm_of` reads that name as the main agent's live mark.
  - ⚠A background dispatch's Post fires at launch and is the only Post it gets: it decrements `inflight[title]` (skipping it leaked the count) but never marks the stage done; stale counts are dropped when the run moves to another stage.
- ★**Pipeline hooks looked only at the session's cwd** (2026-10-06): a session launched in one repo worked in another repo (2 pipelines) and got no brief, nudge or hand-off; its dispatches went untagged or `[pl:-]`.
  - ⇒ `session_dirs` (same block in `pl_mark.py`·`pl_flow.py`·`pipelines_brief.py`, test compares): cwd (alone if it has pipelines), else git roots with pipelines the session moved into in the transcript tail (256 KB: Bash `cd` targets · entry `cwd`), cached `plbrief/<sid>.dirs` 60 s. `tests/test_pl_session_dirs.py`.
  - ⚠Paths only read/written or seen in output never count — a session reading another repo's files got its pipelines. The mailbox data dir is never a resolved project (every session touches it). ⚠`pl_flow` is not cwd-first: when several projects own `<name>.json` (live: two repos with a `bugfix` pipeline of different stages — one file skip-denied a stage) it picks by fit (stage title +1, stage agent == `subagent_type` +2, cwd breaks ties) and keeps it in `runs[name].proj`. No `transcript_path` = cwd only.
- ★**A deny-once skip guard let skips through unrecorded** (2026-10-06): the retry passed, so a stage was skipped with no record, and wrong agents/models and untagged SendMessage ran unchecked.
  - ⇒ `pl_flow.pre` denies every undeclared jump; Bash `[pl-skip:<name>/<stage>] <reason>` declares one (stage title only stored), `[pl-model:<name>/<stage>=<model>]` overrides the model, `[pl-agent:<name>/<stage>=<agent>]` the subagent_type. Agent/Task must use the stage agent (general-purpose if not installed) and model (omitted = mismatch); unknown stage title denied; untagged SendMessage denied while a run was touched < `LOST_S`. Outcome `runs[name].st` = `{title: {s: run|done|skip|fail, t0, t1, n}}`. `tests/test_pl_flow.py`.
  - ⚠«Apply» (enforce) off silences every deny; other CLIs never deny (jump recorded as skip). Untagged Agent/Task stays with `pl_mark` nudge — no double deny.
- **Skipping a loop-back's return stage re-listed stages that already ran** (`pl_flow._jumped`): after a review FAIL (onFail `then` = final verify), skipping the final verify and dispatching the live check was denied «You skipped verify, review».
  - Cause: a skip declaration only adds to `skipok`; `cur` stays at implement, and the check measured from `cur`.
  - ⇒ When `ret` is in `skipok` and after `cur`, the check starts at `ret`. `tests/test_pl_flow.py` `test_skipped_return_stage_*`.
  - ⚠A loop-back to stage `g` (`pre` backward move, `end` FAIL) drops `skipok` entries at index ≥ `g` (`_reopen`): a round-1 skip must be declared again. `st[t]["s"]` skip marks stay. A return-stage skip declared after the loop-back still counts.
- **`pl_flow._mark` rebuilds `st[t]` from scratch**: a stage key with no carry line there vanishes on the next outcome change (`ag`·`m`·`p0`/`k`·`ps`·`cm` each have one).
  - ⇒ a new per-stage key gets a carry line in `_mark` plus a test that `_mark` done/back/fail/skip-after-run keeps it. `ps` = closed earlier passes `[{a, b, s}]` (≤ `PS_MAX` 6, appended in `pre`'s new-pass branch); `pl_runs._passes` drops the whole list on one bad entry so pass numbers never shift.
- **Commit times `cm` must survive `_mark`**: `_commit_close` stamps `st[cur].cm` (≤ `CM_MAX` 4, newest last) on every non-dry-run `git commit` Pre, then the stage's own Post marks it done — without the carry the stamp vanished at once.
  - ⇒ carry line in `_mark`; subagent commits (`agent_id`) only stamp, main stamps and closes. `pl_runs` keeps numbers only; `plPass` shows a commit only inside `[p.a-5, cap)`. ⚠No git spawn in the hook. Test: `edge-subagent-commit` cp 4 (`cm` kept after done).
- **A closed run swallowed stages that ran, so the next stage was denied «You skipped …»** (2 denies in one session, 2026-10-14).
  - Cause 1: `_commit_close` closed every open run of the commit's repo; arch-map's file lives in Sidereus but drives another repo, so an unrelated `[pl:-]` commit here ended it mid-run. Cause 2: the closed-run Bash branch in `_flow` (no new run, only `t1` moves) also caught a run closed on an earlier stage, so main's next-run Bash mark for its own first stage was dropped.
  - ⇒ `[pl:-]` commits close nothing, `[pl:<name>/…]` closes only `<name>`; the closed-run branch needs the last stage (`_plain_next < 0`). Tests: `test_outside_commit_keeps_run_open`, `test_main_stage_bash_after_closed_run_counts`.
- **Reload kept stage lights but lost the agents** (run table 0 rows, node click → session popup). ⇒ 48b `plPlrAgents` adds `plr[].ag` aids to PLSEEN every poll. ⚠It never sets `live`/`ep`/`infA` and skips when a stage started >60 s after the record (a newer run would inherit the old agents).
  - ⇒ superseded by plrun (see «Client-side run stitching drifted from the hook record» below; server `sidereus/pl_runs.pl_model`).
- **The retry dot keyed on the target's retry flashed every loop into that target** (two onFail edges into one stage both lit, whichever fired). ⇒ 48b `plPlrOverlay` copies `plr[].lb` to `lt[target].from = {source: n}`; 48d `plEdgesSvg` marks `.plel.fired` (solid) and fires the dot only on the edge whose own `n` grew (`E.seenRt`). Badge «↺ 1 from Verify · …» per source. `tests/test_pipeline_run.py` `LoopBack`.
  - ⚠Do not key the dot or the solid style on `lt[target].retry` again.
- **Renamed stage title Final verify → Re-verify (Korean stage titles)** (2026-10-09). Old tags, other projects' files and stored runs still carry the old title.
  - ⇒ One old→new map, copied where titles are compared: `hooks/pl_flow.py` `RENAMED` (tags + file stages/onFail), `sidereus/pipeline_schema.py` + `sidereus/pl_runs.py` `RENAMED` (validation · run keys, lb, cur, plm, sub tags), runner `.claude/workflows/pipeline.js` `RENAMED` (in-memory, before validate), 48c `plTk` (page lookups). `tests/test_stage_rename.py` keeps the copies equal.
  - ⚠A run open across the rename keeps its old keys inside the hook's runs.json (cur, skipok, loops); only display maps them. Files are never rewritten automatically.
  - ⇒ superseded by plrun (see «Client-side run stitching drifted from the hook record» below; server `sidereus/pl_runs.pl_model`).
- **Client-side run stitching drifted from the hook record** (inferred «Estimated» stages, faded previous run, per-row hide, PLSEEN/PLPREV rebuilt per tab). ⇒ the server builds one model, row `plrun` (`sidereus/pl_runs.pl_model`); 48b `plPrLt` only renders it, the loop-back pulse keys on `from[source]` while the target is `run`.
  - ⚠A stage absent from `plrun` = wait. Never re-add client stitching (seen maps, agent-type inference, record overlays) — fix the server model instead.

## Schema, gates and evaluation

Moved from «Platform, config, launcher, tests and tooling».

- **Stage agent `Explore` refused the whole pipeline file** (2026-10-07, `pipeline_schema._AGENT`).
  - Cause: the agent rule was `^[a-z0-9-]{1,60}$`; built-in agent types are capitalised (`Explore`, `Plan`).
  - ⇒ Agent: `^[A-Za-z0-9][A-Za-z0-9_-]{0,59}$` in schema · 48c canvas check · preset fallback · `.claude/workflows/pipeline.js`. Skill names stay lowercase (`_SKILL`).
  - ⚠The four copies must change together — one strict copy re-breaks the file on save or on run.
- **Red check of a checks-* gate is not its rc** (`scripts/pl_eval.py redcheck`, `sidereus/pl_eval.py`).
  - Cause: `arch_checks.py --verify` exits 0 when findings exist (it only fails EMPTY / schema), so rc≠0 never shows the break was seen.
  - ⇒ checks-* red = the injected item is in the temp clone's checks file; `fast`/`full` red = gate rc≠0. Missing tool or timeout = skip, never pass; any change to the target's HEAD/status = fail «target changed».
  - ⚠Holdout secrecy is by convention only: ids live in `eval/<key>/seeds.json` (0600) and leave it as counts (`holdout {n, caught}`) — never print, store or serve a holdout id.
- **Gate → mode table lives in three places** (`pipeline_schema.GATE_MODES`, `hooks/pl_guard.py GATE_MODES`, runner validate block in `.claude/workflows/pipeline.js`).
  - Cause: the hook must run without importing `sidereus/`, and the runner is plain JS; one drifted regex makes the editor, the validator and the hook disagree on which gates are graded and which evidence counts.
  - ⇒ `tests/test_pl_guard.py` pins all three equal. ⚠A new gate mode = edit all three in one change.
- **Eval endpoint returns 400, not 404, for an unknown project** (`sidereus/pl_eval_view.py`, demo `_demo_eval`).
  - Cause: the page reads a 404 as «feature off» and hides the view.
  - ⚠Keep 400 for bad input in any new pipeline sub-endpoint.

## Run-end auto score fires before the commit lands (`hooks/pl_flow.py`, `scripts/pl_eval.py score --auto`)

- Cause: a run closed by `git commit` is closed on the commit's PreToolUse — HEAD is still the old commit, and the commit may be denied or cancelled.
- ⇒ The hook passes `--since <Pre time>`; the scorer sleeps, waits while `index.lock` exists, and scores only if HEAD's commit time >= since.
- ⇒ Claim `eval/<key>/<commit>/auto-<name>` holds «run» then «done»; a «run» older than `AUTO_STALE_S` (crashed) is retaken.
- ⚠Never read HEAD in the hook to compare: the scorer may start after a fast commit already landed.

## Current stage stays «run» while the session works on something else (`sidereus/pl_runs.py` `_close_stale`)

- Cause: session activity `act == "run"` is session-wide (any tool use), so a cur stage with no tagged agent or marker stayed lit forever.
- ⇒ `pl_model` passes the row's last evidence (run t1, stage t1, finished agent t1); older than `PLR_STALE_S` (600 s) the cur stage is «hold» `why: "idle"`.
- ⚠A live tagged agent or the main marker still skips the check — never drop the `any(a.get("run"))` guard in front of it.

## Orchestrator stage `agent: "main"` (`hooks/pipelines_brief.py`, sidereus-change Requirements stage)

- Cause: `pipelines_brief.BUILTIN` lacked `"main"`, so the session brief listed «missing agents: main» for a stage the orchestrator runs itself.
- ⇒ `main` is a built-in agent name there, as in `pl_flow.NO_AGENT`.
- ⚠Every sidereus-change run does the Requirements stage (Bash `[pl:sidereus-change/<Requirements stage title>]`) or declares `[pl-skip:sidereus-change/<Requirements stage title>] <reason>` first — `pl_flow` denies an undeclared jump to the Design stage.

## Template copy turned `main` into general-purpose (`sidereus/pipeline_new.py` `_from_template`)

- Cause: `_from_template` replaced every agent missing from the project with general-purpose, so the «Cross-review (Codex)» orchestrator stage became a subagent stage.
- ⇒ `main` is kept like `general-purpose` (same as `pl_flow.NO_AGENT`). Test: `test_create_cross_review_keeps_main_r1`.
- ⚠Do not drop `main` from the keep list: a subagent would get a `codex exec` task meant for the orchestrator (its guard makes it FAIL `unrelated`).
- ⚠`_from_other` (copy from another project) needs the same keep list — it had its own loop and turned `main` into general-purpose. Test: `test_import_from_other_keeps_main`.

## Runs folded into one slot (`hooks/pl_flow.py` `_boundary`, `_run_of`)

- Cause: a run was replaced only when ended or idle 6 h, so a new change tagged at the first stage folded into the previous run and carried its stage marks and passes.
- ⇒ A tagged Pre (or `[pl-skip:]`) of the first stage while the open run is past it closes that run (cur «run» → done, `end`), and `_run_of` opens a fresh one. The replaced run goes to runs.json `past[name]` (oldest first, `PAST_MAX` 5, only `st lb cur end t0 t1`).
- ⚠Not a boundary: a re-mark at cur, or a declared loop-back to the first stage (cur's `onFail.goto` or pending `ret`) — those stay in one run.
- ⚠Runs already folded on disk are not split retroactively.

## Harness flow: window by run time, not by row count (`harness_flow.py`, `harness_evidence.scan`)

- Cause: the flow got the newest 120 evidence rows, so a run older than those rows showed empty gate/edit nodes as if nothing ran.
- ⇒ `scan()` passes every row of the 512 KB tail (≤ `EV_SCAN_MAX`); each run takes [t0-5, (end|t1)+60]. Edit/commit fall back to runs.json `h0`/`h1` and `commits()`.
- ⚠`floor` > 0 = the tail was cut there: a run starting below it is `why: "window"` (outside the read), never «no record».

## Live tagged agent skipped as «earlier run» (`pl_runs.pl_model`)

- Cause: a stage absent from runs.json (hook wrote nothing after a skip) is lit from the live `sub` row, but an aid present in `byname` was always taken as an earlier run's agent.
- ⇒ skip only when none of its meta t0 values falls in the run window [t0-5, now+5]. `tests/test_pl_runs.py`.
- ⚠Unexplained: `hooks/pl_flow.py` did not save runs.json after the skip although `_flow` in memory produces the stage; suspect the silent return on `_Lock` failure.
- Diagnostic: each silent exit of `_flow` and each exception `main()` re-raises appends `<iso> <event> <tool> <code>` to `plmark/<sid>.why` (codes `no-project` · `no-stages` · `apply-off` · `lock` · `post-no-run` · `post-ended` · `exc:<Type>`; capped at 32 KB, written only if `plmark/` exists).
- ⚠Metadata only — never tool input; `LOCK_WAIT_S` 2.0 < `LOCK_STALE_S` 5.0, so a waiter gives up before a stale lock can be taken over.

## Pipelines tab: no side-by-side layout on wide screens (`web/css/43-pipeline.css`, 48d `PL_SPLIT`)

- Cause: above a 1220px container the stage panel and palette moved beside the canvas, so the canvas was narrower at 1440 than at 1100 and a pipeline that fit in one row wrapped.
- ⇒ below 1600px canvas (full width) stacks over palette (left, 220–360px) + stage panel (right, rest of the width, 2 field columns from ~710px, one-line fields ≤420px); one row-resize handle `.plgh`, height in `sidereus.plpanh`, double-click = 420.
- ★Demo 4-stage pipeline, headless (2026-10-16): canvas 816 / 1016 / 1356 px at 900 / 1100 / 1440, one row at each (80% / 100% / 100%).
- ⚠Do not put the stage panel beside the canvas; it costs canvas width exactly where there is the most room.
- ⇒ Only the palette may sit beside it, and only at ≥1600px (`@media`, 280px column spanning all rows): the canvas loses 286px (≈1230px at 1600, still above 1100's 1016). ⚠Lowering the breakpoint toward 1440 brings back the narrower-than-1100 canvas.

## Pipelines tab head row: comboboxes under the poll, menu inside `.plw` (48 `plPickHtml`/`paintPipe`, 48e `plNewBtn`, 48h `plBorrowChips`)

- Cause: the head row is rebuilt on poll; a native `<select>` closed under it, and a menu item lost focus. Item handlers return early outside `.plw`, so a menu in a body-level popover would do nothing.
- ⇒ Project and pipeline pickers are both 08b `ppComboHtml` (`data-ppk` `pl` / `plsel`); the list is `#ppop` outside `.plw`, so a repaint keeps it open and `ppPick` refocuses the new button. «+ New ▾» renders inside `.plw`; an outside click removes it without a repaint.
- ⇒ Borrowed pipelines are head-row chips only while `plBorrowLv` reports a live run; the server lists ended runs too.
- ⚠Refocus/kbHold targets are `[data-ppk="plsel"]`; `data-plsel` no longer exists. `.plhead` is taken by the canvas arrowheads: the row is `.pltop`.
- ★Demo headless (2026-10-17): row height 30px, one row at 900 / 1100 / 1440 (ko, en).

## «Working now» list beside the canvas (48j `plNowList`/`plNowWrap`/`plNowPick`, 74b `tlSessNmB`, 81i split `plmd`)

- Cause: a block whose size follows the live session count shifts the canvas on every poll (the earlier top strip did this until pinned to 26px).
- ⇒ `aside.plnl` is always rendered with a fixed width (the saved split, or the collapsed rail); only its contents change with the sessions.
- ⇒ `paintPipe` skips while the split is being dragged, so a poll never rebuilds the handle under the pointer.
- ⇒ Collapsed, it is a rail of status dots, not hidden; a dot click expands and picks that session.
- ⇒ Watch canvas | result pane | «Running N» card take shares of the free height (48k `plWatchFit`, ls `sidereus.plwv`, two grips), never their content; the card is always present.
- ⇒ Subagents appear only as the session's live subagent tree (48j `plNowAgents`, max 6 + «+N more»); no per-row Timeline link.
- ⚠Never size the list by its content or render it only when sessions exist.

## Watch/Edit split (48k `PLMODE`/`plModeSet`/`plWatchOn`, 48h `plRO`)

- Cause: Watch reuses the canvas read-only, so every edit guard has to stop there as it does for a borrowed pipeline.
- ⇒ 48h `plRO()` is true in Watch as well as for a borrowed pipeline. Any new canvas/panel handler that writes must check `plRO()`, never `p.from` — except a handler that switches to Edit itself (48i «Fix it myself» checks `p.from`, then calls `plModeSet`).
- ⇒ Edit renders byte-identical output to the tab before the split; Watch only adds around it.
- ⇒ Leaving Edit with unsaved edits keeps them in memory (`PLS.g`, • mark, «Unsaved changes — Edit to save» in Watch).
- ⚠A reload still loses unsaved edits; Watch never saves. The tour (98b) never switches the mode: in Edit its 'pl-live' step drops.

## Canvas row height follows the graph (48d `plCvNeed`/`plGwFit`, 43 `--plcvh`)

- Cause: the canvas row was a fixed clamp(360px, 62vh, 700px), so at 1440x900 a one-row chain left the stage panel (Custom, the default) below the fold.
- ⇒ `plCvNeed(G, cw, vh)` = graph height at min(1, width-fit) zoom + 8px, clamped to [200, 62vh]; `plGwFit` sets `--plcvh` = need + toolbar strip every pass (cards grow on later paints), floor = row + 6 + 420. The changed canvas height re-fits through `plFitKey`.
- ⚠A dragged split (`sidereus.plpanh`) drops `--plcvh` so the canvas row stays flexible; do not pin both rows in px (the leftover height would sit empty).
- ⚠Stage-name input: placeholder is the short «Stage name»; the long hint is its `title` (it clipped as a placeholder).


## «Result layer» sentences are keyed twice (48i `PLE_OC`, `pl_outcome.OC_SENT`)

- Cause: the panel renders the sentences itself from counts; the report renders them in Python. Same English text, two places.
- ⇒ `PLE_OC` values are the `OC_SENT` templates verbatim (each is also an `I18N.ko` key); numbers go in `vars`, never through `T()`. Percentages round half up in JS (`Math.round`).
- ⚠Rewording one side breaks the ko lookup or makes panel and report disagree; change both and `06-i18n-zx-eval.js` together (`tests/test_pl_outcome_js.py` checks the key list).

## Pipelines tab dot lagged the Timeline (48 `plTagNames`)

- Cause: the tab took run names only from live tags (Workflow row, `[pl:]` subagent label, `plm`); subagent labels come through `agents._agent_meta` (TTL 20 s), so a run showed 10–20 s after the Timeline, which reads `plrun`.
- ⇒ `plTagNames` also adds open `plrun` runs (`!r.end && plPrLive(r)`); the project is still picked by `plHomes` (`r.proj` first), so one run lands in one project.
- ⚠Do not add ended runs or bypass `plHomes`: the dot would stay after the run or show in every repo of the session.

## `[pl-none]` state lives in its own file (`hooks/pl_flow.py` `_none_decl`/`_none_gate`)

- Cause: the declaration and the once-per-session edit/commit deny need a per-session flag; `<sid>.json` is read by `agents.plm_of` as the main marker and `.runs.json` by `pl_runs`.
- ⇒ `plmark/<sid>.none.json` = `{v, cat, t}` or `{v, nudge}` only; `nudge` is saved before the deny prints (same order as `_nudge`).
- ⚠Never merge it into `<sid>.json` or `.runs.json` · never store the description · a deny printed before a failed save would deny every edit.
- ⚠The gate resolves the project from the edited file (walk up to its git root) or, for a commit, cwd / its git root — never `session_dirs`: a repo merely `cd`'d into earlier lent its pipelines to edits in a repo without any.
- Each declaration also appends `{v, proj, cat, t}` to `plmark/none-log.jsonl` (`_none_log`; project = `_none_proj`, none resolved = no line); `pl_runs.pl_none_counts(days)` reads its tail as `{proj: {cat: n}}`.
  - ⚠The append takes the same `_Lock` as `_none_trim` (read → tmp → replace); without it an append between read and replace lands in the old file and is lost. Lock wait ≤ `LOCK_WAIT_S`, then append anyway (fail-open).
- ⚠Category, time and project path only — never the description. The append is fail-silent (a log error must not block the tool); over 256 KB or with a first line past 90 days it is rewritten to recent lines.
- The 3rd `no-fit` of a project in 7 days (main session, this one counted from the log tail) adds Pre additionalContext offering a draft pipeline (`_none_nudge`); `plmark/none-nudge.json` `{proj: t}` keeps it to once per project per 7 days. ⚠One JSON object per Pre: `main` buffers the flow's stdout while a nudge is pending; `_none_emit` merges into a context-only PreToolUse object, passes a deny or unparseable output through unchanged, and stamps only when the nudge is printed.

## A clone's own repo is a «self-only» project (`pipeline_projects.project_list` · 48 `plLoadProjs`)

- ⚠`allowed_projects()` always adds `CODE_DIR` on a clone, so a fresh clone listed only it and the tab opened its developer pipelines (arch-map) instead of the empty state. ⇒ The list marks it `self_only` unless history, «+ Add project» or a live session's cwd/repos also name it; the default pick skips it and the picker sorts it last.
- ⚠Never drop it from the allow-list, and never flag it when a session runs there — the developer's default would change.
- The picker row says «(built-in)» (48 `plChips` note); with no project and no session `plBody` adds the next step (start a session, or `sidereus start --demo`) under «Pick a project».

## First-open canvas fit went stale when cards grew (48d `plGwFit` · `plSizeKey`)

- Cause: the first paint fits 184px cards; the live run (status pill, gate/commit line) lands on a later paint and widens them (★2026-10-22, 1100 demo: 184 -> 252px, drawn width 814 > canvas 799 at 88%). `fitK` holds only canvas size + stage count, so no refit ran.
- ⇒ `E.szK` (measured `wd`/`ht`) also triggers the untouched refit, but only while `E.first`.
- ⚠Never let card size refit after `E.first` is cleared (node click, «Working now» pick): a poll would move a view the person acted on. No fit/centre call from click, select or expand handlers.

## Marks need words; targets need 24px

- ⚠A bare mark (`↺n`, `↺k ▾`, «Unverified», short hash) carries `title` + `aria-label` in words (`Sent back here {n} times`, `Pass {k} of this stage — …`, `Commit made in this stage: <hash>`); the visible text stays as is.
- ⚠Clickable marks are at least 24x24px (WCAG 2.5.8), and a state is named by its word, never by colour or mark alone.

## An open run with no closer stayed «running» 6 h (`pl_runs.pl_model` · `hooks/pl_flow.py` `_skip_ends`)

- Cause: `end` is written only by a foreground last-stage Post, `[pl-end:]`, a commit or `_boundary`; main's push-only tail, a background last stage and skipped tails never close, and `PLR_KEEP_S` kept them listed for 6 h.
- ⇒ The viewer shows an `end`-0 run ended at its last evidence after `PLR_OPEN_S` (30 min) with no live agent / bg task / main marker of that run; the hook ends a run when a skip leaves only skipped stages after a finished cur.
- ⚠Never close by age alone: a background arch-map stage agent runs > 30 min. Never write `runs.json` from the viewer.
- ⚠Agent rows are collected only for the newest `PLR_MODEL_AG_RUNS` (3) open runs; older open runs still get a cheap `_PLR_TAG` match against live sub/bgs rows (`row["_live"]`, popped before output) — without it a 4th run with a live tagged bg stage auto-ended at 30 min.

## Following live runs: reload opens the newest working run only when no working run is shown (48j `plNowFollow`)

- Cause: every run is «new» to an empty seen set on the first poll; seeding only left a reload on an idle pipeline while a run was working.
- ⇒ First call: a viewed working run is kept; otherwise the newest working run is picked, then `PLNOW_SEEN` is filled. Edit / diff / past-run views keep updating it, so returning to Watch does not jump.
- ⚠Never jump away from a viewed working run, on reload or later. Working = a stage `o === 'run'` (plPrLive) or a stage `t1` within `PLNOW_GRACE` 120 s; an open run whose stages all wait is not working (it held the selection while another run ran).
- ⚠Never plPaint / plFit from the follow step: the poll paint shows the pick, and the view must not move on its own.

## Agent description line must not size the card (48d `.plnad` · 48k `.plwad`/`.plphd`)

- ⚠The card is `width:max-content` (184..320); a plain nowrap description would push every card with a description to 320 and move edges and «Arrange». `.plnad` is `width:0;min-width:100%` + ellipsis so it takes the width the other lines set. Descriptions are agent-file data: `esc()` in text and `title`, never `T()`.

## Stage agent «now» line is the tool name only (48k `plAgNowLine`)

- Cause: `sub.now` is `_agent_last` — the tool name, plus « · description» for Agent/Task.
- ⇒ The result pane cuts it at the first « · » client-side and shows `name · elapsed`, or `Idle · <ago>` past `PLNOW_QUIET`; no `title` on the line.
- ⚠Never show the suffix or any tool input there (rule 1); the tool name is data: `esc()`, never `T()`.

## Hook run counts: transcripts miss silent hooks, OTel does not (`otel_hooks.hook_fires` · `harness_verdict` `never_ran`)
- Cause: `hook_success` is written only for runs that printed, so a transcript count of 0 cannot prove a hook unused.
- Fix: OTel `hook_execution_complete` fires once per firing with `hook_name` = `Event:<tool or source>`; every hook whose matcher fits that subject ran, so per-hook counts come from matching stored `Event:subject` keys.
- ⚠MCP tools arrive as `mcp_tool` (unless OTEL_LOG_TOOL_DETAILS=1) and SubagentStart/Stop carry no subject: a specific matcher there is ambiguous → keep the transcript count, never claim 0.
- ⚠Counts are global across projects (session id is never stored); a project-scope hook's 0 is still a real 0.
- ⚠A 0 (and `never_ran`) needs ≥ 3 covered days (`HN_FIRE_MIN_D` · `VD_FIRE_MIN_D`) — coverage starts the day the store first saw a firing; before that a silent hook stays «?».

## A guard deny that is not saved shows «Blocked 0» (`hooks/pl_guard.py` `_commit`/`_skip` · `pl_flow._deny_save`)
- Cause: pl_guard denied a commit before a required gate (and a `[pl-skip:]` of a required gate) but never wrote it to runs.json, so the Harness guard node read 0.
- Fix: both go through `flow._deny_save` with codes `gate` / `skipgate`; a failed save never lifts the deny.
- ⚠A new deny code goes in three allow-lists: `pl_flow.DENY_CODES`, `harness_flow.HF_DENY_CODES`, `pl_outcome.OC_DENY_CODES` (else dropped from result-layer counts), plus an `HN_FD` label.
- ★Caught by the end-to-end replay set `tests/test_harness_e2e.py` (2026-10-26).
