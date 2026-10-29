---
name: requirements
description: Orchestrator's first stage of a change pipeline (sidereus-change, first stage) — turn the request into 2-5 checkable R1..Rn criteria plus one Non-goal, get one owner confirmation, and carry the ids through design, tests, live check and the commit body. Use before dispatching the design stage.
---

# Requirements (orchestrator only, no subagent)

Written by the orchestrator itself. Mark the stage with a Bash described `[pl:sidereus-change/<stage title>]`, using the first stage's `title` from `.claude/pipelines/sidereus-change.json`.
A run that skips it declares `[pl-skip:sidereus-change/<stage title>] <reason>` first.

## Output

```
R1: <checkable line>
R2: ...               (2-5 lines)
Non-goal: <one thing this change will not do>
Assumption: <optional, one line each>
```

## Rules (sources)

- Each R line is an acceptance criterion; a behaviour with a trigger is written Given/When/Then (BDD, Gherkin).
- Each line must be testable — someone can say PASS or FAIL without asking you (INVEST «Testable»).
- Exactly one `Non-goal:` to fence scope (design-doc practice: Goals / Non-goals).
- Definition of Done (Scrum) is the fixed, project-wide part — `scripts/check.sh` gates, docs updated, live screen at 1920/1440/1100/900 (design at 1920; narrower wraps or collapses, never crams), i18n entries. It is stated here once; never repeat it in a request's R lines.
- Ambiguity: ask at most one question, and only if the answer changes a criterion. Otherwise write an `Assumption:` line and go on.
- Traceability: R ids are reused verbatim in design slices, test names/comments, and the live check report.

## Examples

- Good: `R1: Given a run on the verify stage, when the canvas opens, then the requirements stage is the first box.`
- Good: `R2: Given no upstream on the branch, when «vs this branch's remote» is chosen, then the rail falls back to session start.`
- Bad: `works well` · `UI is nicer` — no one can mark these PASS or FAIL.
- Bad: `R3: tests pass` — repeats the Definition of Done; it holds for every request already.

## Confirm once

Show the block to the owner; one reply (or a one-line edit) confirms it. Then dispatch the design stage. Do not re-ask later stages.

## Storage

- The block goes verbatim into the design, implement and live check briefs.
- The live check reports each R as PASS/FAIL + one piece of evidence (screen crop, test name or `file:line`).
- The commit body ends with `Done when:` (the R lines, each marked PASS/FAIL) and `Not doing:` (the Non-goal).
  A future scorer reads it from `git log` by commit — the same key as `DATA_DIR/eval/<key>/<commit>/`.
- ⚠No scoring UI is built from this; the commit body is the only store.
