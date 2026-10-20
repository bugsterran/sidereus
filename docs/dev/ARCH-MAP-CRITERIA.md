# Arch-map judging criteria

Pre-registered standard for scoring `arch-map` results (`.claude/pipelines/arch-map.json`).
Gate today: `scripts/arch_verify.py` — verified-edge rate below `ARCH_GATE_MIN` 0.7 fails (`sidereus/arch_verify.py`); quality checks (label-target / entry-dup FAIL, flow-overlap / accessor-call / isolated / store-rw warn) live in `sidereus/arch_quality.py`.

## Rule

- Criteria and thresholds are committed **before** the runs they judge. A run is scored only against criteria committed earlier; git history is the proof.
- ⚠A threshold changes only by a new commit, never after looking at one result.
- ⚠A run scored against criteria committed after it is not a scored run.

## Two layers

| Layer | Applies to | Below it |
|---|---|---|
| Usable floor | every model, same numbers | gate FAIL |
| Tier expectation | one model tier | below expectation for that tier (reported, not a FAIL) |

## Model tiers

Tier = the vendor's own description of the model, not a benchmark.

| Tier | Vendor description | Models | Source |
|---|---|---|---|
| Frontier | complex coding / agentic work | Claude Opus | vendor model page |
| Frontier | complex coding / agentic work | OpenAI GPT-6 Sol | not in this account's Codex model list; tier from press coverage (GPT-6 Sol/Luna launch 2026-09-22, TechCrunch), unverified |
| Mid | balanced | Claude Sonnet | vendor model page |
| Mid | «Older balanced model for straightforward work.» | GPT-5.6-Terra | Codex `models_cache.json` |
| Small | fast, low-cost (paraphrase) | Claude Haiku | vendor model page |
| Small | «Fast and affordable model for easier tasks.» | GPT-6-Luna | Codex 0.163.0 `models_cache.json` |
| Small | «Older fast and efficient model.» | gpt-5.6-luna | Codex `models_cache.json` |
| Small | «Fast and affordable agentic coding model.» | gpt-reserve | Codex `models_cache.json` |

- ★2026-10-20: no OpenAI-published SWE-bench / Terminal-Bench number found for Sol or Luna. Third-party benchmark numbers are not used.
- ⚠Small-tier results are reference only for arch-map — never used to set the floor.
- Every scored run records model + reasoning effort. Codex rollout `turn_context` has `model`; effort is `turn_context.collaboration_mode.settings.reasoning_effort`, null ⇒ record «default».

## Metrics

All computed from `map.json` / `flows.json` + the answer key. No judgement.

| Id | Metric | Formula |
|---|---|---|
| Q1 | module skew | files in the largest module / files mapped |
| Q2 | kind conflicts | module pairs with >1 edge kind / module pairs |
| Q3 | label concentration | share of the most common edge label |
| Q4 | store/external miss | modules using DAO/`@Mapper`, Redis or HTTP clients (answer key) without the matching read/write edge or an edge to an `external` module / such modules |
| Q5 | entry coverage | flows / min(40, handler count from answer key) |
| Q6 | flow depth | median steps · share of 1-step flows |
| Q7 | entry quality | share of flow entries whose handler calls no other module (forward-only) |
| R | answer-key recall | share of answer-key facts the map contains |

Precision stays the existing gate rate (verified edges / edges).

## Answer key

- Built per benchmark repo from code facts only: handler mappings, `@Mapper`/DAO, Redis and HTTP-client use sites, packages.
- Built by a script; stored with the commit it was taken at.
- ⚠Never edited by hand after a scored run. A wrong key is fixed by a new script commit and a re-score of every run.

## Thresholds

TBD — set from calibration runs: same repo, same rules, one run per model (frontier, mid, small; both vendors where available).

- Usable floor = the owner's call from those numbers.
- Tier expectation = the observed value for that tier.

Calibration repo: ___ at commit ___ · answer key commit ___

| Metric | Floor | Frontier | Mid | Small (reference) |
|---|---|---|---|---|
| Precision (gate rate) | | | | |
| R | | | | |
| Q1 | | | | |
| Q2 | | | | |
| Q3 | | | | |
| Q4 | | | | |
| Q5 | | | | |
| Q6 median · 1-step share | | | | |
| Q7 | | | | |

Calibration runs:

| Model | Vendor | Effort | Tier | Run commit | Store dir |
|---|---|---|---|---|---|
| | | | | | |

## Not in this doc

- ⚠The gate implementation (`scripts/arch_verify.py`, `sidereus/arch_quality.py`). Q checks move into it only after thresholds exist.
