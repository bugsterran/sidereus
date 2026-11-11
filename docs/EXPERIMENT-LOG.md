# Experiment log

Sidereus is an experiment run by one person on one machine (n=1). This log keeps each idea about how it should work next to what was tried, what was measured and what was decided. Ideas that were dropped stay here with the rest.

CI checks what was pushed; Sidereus checks how it got there: stage order, gates and review at edit and commit time, across CLIs. Most entries below test whether that second kind of checking pays for itself.

How to read a verdict: kept means the change stays and the number below is why; dropped means it was removed or the measure was abandoned; undecided means there is not enough data yet, and Next says what would settle it. Every number links to the commit or issue it comes from, with its period. Small samples are stated as such.

## 1. The viewer's memory is in the server, not the page

Hypothesis: the viewer's memory cost comes from the Python server's caches, not from the browser page.

Tried: measured both, then replaced the tool-usage index with compact per-file arrays and capped the structure cache ([80e0978d](https://github.com/bugsterran/sidereus/commit/80e0978d), [2b83fde7](https://github.com/bugsterran/sidereus/commit/2b83fde7), [#17](https://github.com/bugsterran/sidereus/issues/17)).

Measured: on 2026-10-21 the server held 423 MB RSS while the page's JS heap was 28 MB. Before the fix, 715 MB at 36 min after a restart and still rising; after, 282-304 MB from 26 min to 4 h and 310-338 MB flat to 8 h, one sample run ([#17](https://github.com/bugsterran/sidereus/issues/17)).

Verdict: kept.

Next: a 200 MB steady-state budget now runs in `check.sh --full` ([#24](https://github.com/bugsterran/sidereus/issues/24)); steady state read 74 MB after 4 h uptime on 2026-10-26 ([#26](https://github.com/bugsterran/sidereus/issues/26)).

## 2. RSS in the first 30 seconds as a memory budget

Hypothesis: "every second of the first 30 s after boot at or under 200 MB RSS" is a stable budget.

Tried: streamed the tool-index save and the tail scan ([1dcba282](https://github.com/bugsterran/sidereus/commit/1dcba282), [30b51c91](https://github.com/bugsterran/sidereus/commit/30b51c91)) and sampled boot on macOS ([#30](https://github.com/bugsterran/sidereus/issues/30)).

Measured: boot peak 291 to 226 MB with the streamed save (A/B, same data). A reading of 75 MB at 10 s turned out to be page compression: 8 min after boot, footprint 199 MB, compressed 81 MB, RSS 131 MB. How much is compressed depends on system memory pressure (2026-10-26 to 10-29, [#30](https://github.com/bugsterran/sidereus/issues/30)).

Verdict: dropped as a measure. The budget was restated as physical footprint at 30 s; measured 169-180 MB after both commits. The 196-218 MB peak in the first seconds stays as a known spike.

Next: none planned; reopen if the footprint at 30 s goes over 200 MB.

## 3. Lint checks next to security checks

Hypothesis: running project lint checks from the viewer, next to the security checks, is worth a tab, a badge and a pipeline.

Tried: a lint pipeline, a lint runner, a Quality tab and a "Checks n" badge.

Measured: nothing was measured; the removal commit records scope only ([35b1f0dc](https://github.com/bugsterran/sidereus/commit/35b1f0dc), 2026-10-16).

Verdict: dropped. Security checks stayed as the only check category.

Next: none.

## 4. Replaying the guards against cases they must catch and let through

Hypothesis: each claim the Harness report makes (a guard blocked, a gate went red then green, a pass held) can be checked by replaying the real hooks on fixed cases, each with a control that must pass.

Tried: a replay set of catch and control cases through the real recorder ([957e9266](https://github.com/bugsterran/sidereus/commit/957e9266)), 11 of them by the count in [6da368f0](https://github.com/bugsterran/sidereus/commit/6da368f0), later shown as a "Guard self-check" table ([6da368f0](https://github.com/bugsterran/sidereus/commit/6da368f0), [#27](https://github.com/bugsterran/sidereus/issues/27)).

Measured: the set found a real defect: a guard denied a commit before a required gate but did not record it, so the screen read "Blocked 0". After the fix, 11 of 11 cases pass live (2026-10-30, [6da368f0](https://github.com/bugsterran/sidereus/commit/6da368f0)).

Verdict: kept.

Next: add a catch and a control case with each new guard.

## 5. Red check: can each gate fail at all?

Hypothesis: a gate that has never been seen failing may not be able to fail; injecting a known break into a temp clone shows whether it can.

Tried: a red check per gate, which runs the gate on a deliberately broken clone.

Measured: the security gate's red check failed on this repo. The scanner reads a `git archive HEAD` export, so an untracked injected key was never scanned. After committing the injection inside the clone, the red check passes for `check.sh --fast`, `--full` and the security gate (2026-10-24, [d2a39fe5](https://github.com/bugsterran/sidereus/commit/d2a39fe5)).

Verdict: kept.

Next: run it for the gates not yet confirmed; the 2026-10-25 weekly report (local, see entry 6) counted 3 of 8 gates of the `sidereus-change` pipeline as confirmed able to fail.

## 6. Did a gate pass hold up afterwards?

Hypothesis: whether a PASS held can be read from git alone: a later commit touching the same files within 14 days counts as "fix followed" ([06a61ca0](https://github.com/bugsterran/sidereus/commit/06a61ca0), [#1](https://github.com/bugsterran/sidereus/issues/1)).

Tried: a weekly report per pipeline, written at run close (reports stay local; `eval/` is not committed).

Measured: the 2026-10-25 local report for `sidereus-change`: 33 runs, 14 order violations blocked, 0 of 22 passes broke later, a fix followed all 22, review loop-backs in 70% of runs over the last 30 days. The 22 passes come from 4 commits: [0fbd6f55](https://github.com/bugsterran/sidereus/commit/0fbd6f55), [96b7e98b](https://github.com/bugsterran/sidereus/commit/96b7e98b), [d788c6f7](https://github.com/bugsterran/sidereus/commit/d788c6f7), [a8c82d5b](https://github.com/bugsterran/sidereus/commit/a8c82d5b).

Verdict: undecided. A signal that fires on every pass does not tell passes apart yet.

Next: the report repeats commits (22 rows are 4 commits) and every pass reads "fix followed", so the signal does not yet separate passes. The next attempt is to count per commit rather than per gate pass and fix that; read two more weekly reports before changing the 14-day window.

## 7. Declaring work done outside a pipeline

Hypothesis: if sessions must declare unpiped work by category, repeated "no-fit" declarations show which pipeline is missing.

Tried: `[pl-none:<category>]` declarations, denied once when undeclared ([72c5a0f3](https://github.com/bugsterran/sidereus/commit/72c5a0f3)), logged per project ([4128491b](https://github.com/bugsterran/sidereus/commit/4128491b)), with a pipeline draft offered after the third "no-fit" in 7 days ([ee152cab](https://github.com/bugsterran/sidereus/commit/ee152cab), [#16](https://github.com/bugsterran/sidereus/issues/16)).

Measured: no count yet of forgotten versus genuinely missing pipelines, which is the question the issue set out to answer.

Verdict: undecided.

Next: read the per-project counts after a few weeks of real declarations and decide whether the draft offer stays.

## 8. Do enforced gates cost more than they catch?

Hypothesis: enforced gates (strict mode, required gates before commit) catch enough to justify the time they add and the work they block.

Tried: counters for Caught, Blocked and Overridden, and gate time, added in [5d0ef63d](https://github.com/bugsterran/sidereus/commit/5d0ef63d).

Measured: first live numbers over 7 days on 2026-10-31 (n=1): Caught 10, Blocked 14, Overridden 5, unknown 9. Paused is not measured yet; resume stamps start with that commit.

Verdict: undecided.

Next: count Caught against Blocked and Overridden, and total gate time, for 4 to 8 weeks.

## 9. Fix followed counted from fix runs only

Hypothesis: "fix followed" (entry 6) measures fixes to what a gate passed.

Tried: read every flagged pass by hand, then counted a later commit only when the run ledger attributes it to a `"catch": "person"` pipeline run and it shares a code file with the pass commit; docs, tests, `refactor/` and screen baselines are ignored.

Measured: on 2026-11-01, this repo, last 30 days: 12 of 12 flagged passes were unrelated features touching shared registry or doc files (`refactor/STAGE3.md`, `docs/HOOKS*.md`, screen baselines). With the new rule, 12 → 1: [1c0160ea](https://github.com/bugsterran/sidereus/commit/1c0160ea) → [e0639a02](https://github.com/bugsterran/sidereus/commit/e0639a02), which is still an unrelated fix run on the same code file.

Verdict: undecided. File names alone cannot tell a fix of this pass from another fix on the same file.

Next: watch the real counts over the coming weekly reports before adding any cause-analysis stage.
