# Extending Sidereus

**English** · [Korean](EXTENDING.ko.md)

Each extension point takes one new file and a few registration lines. Internal wiring (state pieces, routes, web
parts) is in [ARCHITECTURE](ARCHITECTURE.md#extending).

- Metadata only: ids, paths, names, kinds, lines, timestamps, counts. Never message bodies or tool input.
- Python 3.9 stdlib, no network. Gate: `bash scripts/check.sh --fast`.
- A new `sidereus/` module goes into the `refactor/STAGE3.md` order and count, or `tests/test_arch.py` fails.
- Tests never read live files, the clock or the network; patch the owning module.

## CLI adapter

Reads another CLI's local record files for tokens, model and child runs; live state comes from its hook
([HOOKS](HOOKS.md)). Copy `sidereus/plat_TEMPLATE.py.txt` to `sidereus/plat_<x>.py`. Examples: `plat_gemini.py`,
`plat_codex.py`. `adapter_register()` (`sidereus/adapter.py`) checks the contract at import and raises `ValueError`.

| Name | Meaning |
|---|---|
| `PLAT`, `KEY`, `NAME` | hook `platform`; 2-char row key (= logo `AILG.<KEY>`, `cc` reserved); display name |
| `CHILD_LABEL`, `SCAN_MAX` | label of a run started from Claude; bytes read per record file |
| `root()`, `path_ok(path)` | data folder; True only for a record file under it (the path comes from a hook POST) |
| `scan(since)` | rows `{sid, path, cwd, project, start, kind, msgs, acts}` (+ `parent`, `rate`) |
| `session_msgs(path)` | `{id: (in, out, cache, thought, ts, model, cost or None)}` or None |

All required. Optional ones (`LANE`, `harness_items`, `TIME_BUDGET_S`, …) are listed in `sidereus/adapter.py`.

- ⚠Local files only: no network, no writes. Tokens and cost never count in Claude's totals.
- A raising `scan` becomes `[]` plus a warning; one slower than `TIME_BUDGET_S` (1 s) warns.

Register in `sidereus/ext_store.py`: the `PLAT: KEY` pair in `EXT_PLAT`, the import, and the `PLAT_MODS` tuple. Place it
before `ext_store` in STAGE3. Tests: `tests/test_adapter_contract.py` and a fixture `scan` test (`tests/test_ext*.py`).

A CLI that only needs a hook-less session row (folder, start, last activity) and has no token records to read goes in
the presence registry instead: `PRES_MODS` in `sidereus/ext_presence.py` (see `plat_cursor.py`, `plat_copilot.py`).
⚠Not in `PLAT_MODS` — that registry also drives token reads (Cursor's tokens come from hook `stop` counts).

## Language plug-in

Teaches the Structure tab's «Size» treemap a language. File `sidereus/structure_lang_<x>.py`; example
`structure_lang_rs.py`.

```python
from sidereus.structure_plug import lang_register

lang_register("rust", {"exts": (".rs",), "scan": rs_scan,
                       "test": r"(?:_tests?|(?:^|/)tests?)\.rs$", "test_dirs": ("tests", "benches"), "skip": ("target",)})
```

| Key | Meaning |
|---|---|
| `exts` | required; tuple of `.ext`, longest match wins |
| `lang` | row language: a string or `lang(rel, src)` |
| `scan(src)` | functions for the treemap; `None` = parse failure |
| `test`, `gen` | regex, pattern string or `rel -> bool`: test file / generated file |
| `test_dirs` | regex or folder names that hold tests |
| `skip` | folder names or fnmatch globs left out of the scan |

Unknown keys raise `ValueError`. `structure_scan` calls `structure_plug.plug_load()` at import, which imports every
`structure_lang_*.py` in sorted order. Nothing else to register; a plug-in that fails to import is skipped with one
warning.

- ⚠Every file matching `structure_lang_*.py` is a plug-in. Helpers go elsewhere: `structure_lex.py`,
  `structure_c_util.py`.
- ⚠It runs while `structure_scan` is importing. Import only modules before `structure_scan` in STAGE3 plus
  `structure_lex`, `structure_c_util`. Never another plug-in.
- ⚠Best effort, linear time: missing beats guessing wrong; cap lengths with constants.

Tests: `tests/test_structure_lang_<x>.py` with treemap and test/skip fixtures, plus a pathological input that
finishes in under 1 s.

## Pipeline

A pipeline is the order of stages; a skill is the procedure inside one stage (a stage can name a `skill`).

1. Write: `<project>/.claude/pipelines/<name>.json` (keys below). Checked on save by `sidereus/pipeline_schema.py`
   and in `check.sh --fast` by `scripts/pipeline_check.mjs`.
2. Delivery: `pipelines_brief.py` adds the list to each session at SessionStart ([HOOKS](HOOKS.md#pipelines_briefpy)).
3. Enforcement: the session runs the stages itself with the Agent tool, tagged `[pl:<pipeline>/<stage>]`. `pl_mark.py`
   denies untagged agents; `pl_flow.py` denies a wrong order, agent or model ([HOOKS](HOOKS.md#pl_markpy),
   [pl_flow](HOOKS.md#pl_flowpy)); `guards` make listed gates required before commit ([Guards](HOOKS.md#guards-hookspl_guardpy-claude-code-only)).
4. View: «Pipelines» tab ([GUIDE](GUIDE.md#watch-a-pipeline-run)) and timeline ([GUIDE](GUIDE.md#check-the-evidence-in-the-timeline)).

Internals: [dev/PIPELINE.md](dev/PIPELINE.md). Review pipelines per CLI, with templates: [REVIEW-PIPELINES.md](REVIEW-PIPELINES.md).

`<project>/.claude/pipelines/<name>.json`, name `[a-z0-9-]{1,40}`. Example `.claude/pipelines/sidereus-change.json`.

```json
{ "v": 1, "name": "my-change", "title": "Change", "defaults": {"model": "inherit"},
  "stages": [ {"title": "Design", "agent": "my-designer", "task": "…", "produces": "slices"},
              {"title": "Implement", "agent": "my-implementer", "fanout": "slices", "gate": "scripts/check.sh --fast"} ] }
```

- Top keys: `v`, `name`, `title`, `use` (one line, up to 120 characters; read by `pipelines_brief.py` and shown on the Pipelines screen), `rules`, `after`, `defaults`, `guards` (`requireGates`, `maxLoopBacks`), `stages`.
- Stage keys: `title`, `agent`, `model` (`inherit|opus|sonnet|haiku`), `skill`, `task`, `gate`, `produces`/`fanout`,
  `parallel`, `retry`, `onError` (`stop|continue`), `onFail {goto, max 1..5, then?, stopOn?}`, `onlyOnJump`, `ui`.
- Titles outside `pipeline_schema.STAGE_TITLES` are custom stages (1–40 chars, need `task`).
- «AI config review» and «Prompt check» are recommended titles in `STAGE_TITLES`; the file stores their Korean form (see [EXTENDING.ko](EXTENDING.ko.md)).
- «AI config review»: read-only review of the project's AI config (AGENTS.md/CLAUDE.md, agents, skills, hooks, `.mcp.json`, stage tasks) — findings with file:line.
- «Prompt check»: runs the named agent/skill prompts on synthetic input and reports pass/fail per prompt against what each promises.
- Standard drafts «Hook change» · «Skill write · change» · «Add tool · MCP» use these two stages for AI-configuration work.
- Tag each stage's Agent description `[pl:<pipeline>/<stage>]` (40 chars). A tagged main-agent Bash lights «main» for
  2 min; `[pl:-]` clears it ([HOOKS](HOOKS.md#pl_markpy)).
- Work that fits no pipeline: a Bash description `[pl-none:<category>]` (`small-fix` · `no-fit` · `explore` · `other`).
  Otherwise the first edit or commit with no open run is denied once ([HOOKS](HOOKS.md#pl_flowpy)).
- `onFail`, `onlyOnJump`, `onError` and `after` also drive the hand-off text of `pl_flow.py` ([HOOKS](HOOKS.md#pl_flowpy)).

Tests: `tests/test_pipeline*.py`; `check.sh --fast` also runs `scripts/pipeline_check.mjs`.

## Verdict guide

Each Harness verdict id has a «Next step» guide: `docs/verdicts/<id>.md` (English) and `<id>.ko.md` (Korean, same headings).
Add a file to explain a new verdict id; `sidereus/verdict_guide.py` reads it, GET `/api/verdict-guide?lang=` serves it.

```md
# my_verdict

## Meaning
One line: what was found.

## Why it matters
One line.

## Who acts
self

## Next step
One line; for `self`, one command or setting location (`/hooks`).

## Safe to ignore when
Required when Who acts is `owner`.

## Pipeline
Optional: the pipeline to hand it to (`sidereus-bugfix`).
```

- Id `[a-z][a-z0-9_-]{0,40}`; `Who acts` is `self`, `ai` or `owner`; each field up to 300 characters.
- A file missing a field is skipped; a missing `.ko.md` falls back to English.

Tests: `tests/test_verdict_guide.py` (every id the server emits needs a file).

## Reading state from another program

- Use `GET /api/v1/state` («sidereus-state v1», `sidereus/state_v1.py`; schema `docs/schema/sidereus-state.v1.json`).
  `/api/state` and `/api/messages` are internal (`n` defaults to 200, caps at 1000, ≤ 0 is 400).
- v1 may gain optional fields; removing, renaming or redefining one makes v2.
- Host must be `127.0.0.1:<port>` or `localhost:<port>`; browser cross-site and same-site requests are refused.
- ⚠v1 is metadata only and omits fields derived from tool input (`targ`, `blocked`). Never add a field that can carry
  message or tool content.
