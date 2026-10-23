# Feature modules — design (s1 built 2026-10-01)

★2026-10-01 requirement: features can be switched off, and the structure stays extensible for the public release.
The user's install keeps every feature on; a fresh public install starts core-only.

## Registry

- `features/<id>.json` manifest: `id, title, default_on_public, deps, modules, routes, threads, state_keys, web, settings`.
- `sidereus/features.py` (STAGE3: `… prefs · features · bus …`): `on(id)` · `route_feature(path)` · `thread_on(name)` · `state_off()` · `snapshot()`.
- Toggles live in `prefs.PREFS["features"] = {id: bool}`; **missing key = all on** (no write at import). `config.example.json` ships core-only defaults.
- Off = routes 404 `{"error":"feature off"}` · threads not started · state keys omitted · tab hidden. Takes effect **after restart**.
- ⚠Modules of an off feature are still imported (core couplings below) and its web files still ship — PAGE stays byte-identical for any toggle state. Top-level JS of a feature must not fetch on load.
- ⚠A dep that is off forces its dependents off.

## Public first run: headline features

★2026-10-01 requirement: three headline features up front; everything else is secondary.
- On by default (`default_on_public: true`): **session control** (core · attention) · **quota pace + limit block** (core · saver) · **structure** (`struct`, AI-written code map) · **pipeline** (per-stage agent/model, run, live stage).
- ★2026-10-01 requirement: pipeline is a headline feature, not secondary.
- First screen = Pipelines in Watch (no saved tab; Timeline only when `pipeline` is off): «Working now» list of live sessions + subagents (48j) beside the canvas | result pane | «Running N» card (48k). See FILEMAP.
- Timeline is the evidence view; it carries open pipeline runs: per-session stage strip + gate result line + stage bands from `SESS[].plrun` (`web/js/74c-timeline-plrun.js`, `web/css/21-timeline-plrun.css`); click opens the Pipeline view.
  - Up to 3 live runs stack one line each (newest first, «+N» for more); ended runs in the window fold behind a «+N ended» chip (in-memory toggle). Row accent fail > run > fin; bands and the gate pill follow the top run. The work log stacks every run an agent appears in (session tab ≤ 3).
- Everything else ships off (`default_on_public: false`) and is switched on in Settings › Features: branch · timeline · retro · history · tools · tokens · failures · awake.
- ⚠The `struct` manifest (migration step) must set `default_on_public: true`.

## Core (never off)

sessions · live · attention · cards · bus/chat · dm · otel · hook · term · work log · prefs · quota/usage/saver/burn · first-visit tour (`98b-tour.js`, no toggle; steps for off features are skipped; `/api/state` `codeDir` is core).

- cards (bell): agent/background completions while the viewer was down ring after restart — only after the saved alive time (`bg-alive.json`, `bgtasks_parse._alive_beat`), ≤ `notes.CATCHUP_MAX` (20) per process, deduped by card `tid`/`aid`, cards carry `done_at`.

## Features and couplings (measured 2026-10-01)

| Feature | Routes | Threads | Coupling to fix or baseline |
|---|---|---|---|
| retro | /api/retro | — | deps hist, failures only |
| pipeline | /api/pipelines, /api/pipelines/save, /api/pipelines/apply («Apply» mode for the SessionStart brief, prefs `pipeline_apply`), /api/pipelines/projects/dirs (folder browser for «+ Add project», names + git/Claude flags, home only, `hidden=1` = dot-folders), /api/pick-folder («Choose folder…» = OS native folder dialog on Mac/Windows, fills the path only) | — | built on the registry (2026-10-01); imports `toolinv.known_projects` — add `deps: ["tools"]` when tools gets a manifest |
| harness | /api/harness, /api/harness/file | — | `sidereus/harness.py`; web = pipeline tab «Harness» view (`47b-harness.js`, `41b-harness.css`, toggle in `48-pipeline.js`) — «Results» first (recorded gate evidence, `evidence` list), the config map below folded in «Config map»; `deps: ["pipeline"]` (stage→agent via `pipelines()`, allow-list `_proj_ok`); a card/rule/agent click opens its file in the structure code window (`81-structure-panel.js` `strPopOpenText`) via `/api/harness/file?proj=&ref=` (opaque `open` ref, path re-derived server-side; hook scripts only under the readable roots, text only, ≤ `HN_SCRIPT_MAX`); MCP rows carry `status` ok/fail/none · `err` code · `fail_at` (`toolidx.mcp_status`: transcript `failedMcpServers` vs last tool call; failed first, dot + «failed» badge; `ok` = called after the last failure, the call result is never read, so the tooltip says «last call: … (result not checked)» + any earlier failure, not «success»); `?plat=cc|cx|gm` on both routes (`sidereus/harness_plat.py`: Codex/Gemini rows from `plat_<x>.harness_items` + `LANE`, no run counts — `n` null), logo switch in the view when more than one CLI home exists; hook runs per hook (`hookc:` command-hash keys; only runs with output are recorded, so no record = «?» `quiet`); agents in use (pipeline stage or n>0) first and skills over 8 rows fold the rest behind «N more» (`HN.fold`) |
| diag | /api/diag || diag | /api/diag, /api/sec-tools | — | `sidereus/hook_diag.py` + `hook_fields.py`; Settings › «Diagnostics» (`90e-diag.js`, `85c-diag.css`): hook overlaps with Sidereus hooks, silent plugin hooks (static estimate), plugin versions, CLAUDE.md shadowing AGENTS.md; «Security tools» via `sidereus/sec_tools.py` (PATH + file layout only, nothing executed); read-only, `default_on_public: true`; reads `claude_roots.accounts()` and `toolinv.known_projects()` (no dep while tools has no manifest) |
| hist | /api/history(+/units) | — | agentcost.py:9, retro.py:9 |
| awake | — | awake_loop | Mac-only |
| tools | /api/tools* | — | — |
| tokens | /api/wkuse | wkuse_loop, projcost_loop | — |
| failures | /api/failures, /api/wreckage | fail_loop | state.py:13 `fail1h` |
| struct | /api/structure* (5) · /api/arch (verified module map + process flows, `arch_map.py` + `arch_verify.py` + `arch_flow.py`, pipeline `arch-map`; UI 84j/84k) | struct_warm | `struct_mark_act` marker (chat_server page GET · POST /api/act, core) · demo_rel.py |
| br | /api/branches, /api/git/*, /api/review* | br_boot_warm_start | state.py:14,18 · file_owner.py:13 `wt_files` (peers MCP) · commit_link.py:17 |
| timeline | /api/agents/timeline | tl_warm | burn.py:11 · usage.py:317 · hard fallback view `time` (90b-mypref.js:26) |

## Extension contract

A fork adds `features/<id>.json` + its `sidereus/` modules (placed in STAGE3) + `web/js|css/NN-<id>-*` + a tab key in `MP_TABS`. Routes and threads are claimed only through the manifest.
`tests/test_arch.py`: each route / web file claimed by ≤1 manifest · cross-feature imports only via declared `deps` or `arch_baseline.json` `feature_couplings` (may only shrink) · manifest modules exist in STAGE3.

## Migration (one feature per commit)

s1 registry + gates with `retro` only (done 2026-10-01: `sidereus/features.py`, `features/retro.json`, `tests/test_features.py`; wiring modules `chat_server`/`routes_get`/`routes_post` are exempt from the coupling rule — `chat_server` `_struct_act` is fixed at the struct step) → s2 settings «Features» section (done 2026-10-01: «Preferences» › «Features», `web/js/90c-features.js`; GET /api/prefs `features` rows from `features.listing()`; POST `{key:"features"}` checked by `features.check_toggles` — known ids, bool only; all on = key removed; `tests/test_features_prefs.py`) → hist → awake → tools → tokens → failures → struct → br → timeline (last; needs the fallback change). The pipeline feature is built on this registry from the start.
