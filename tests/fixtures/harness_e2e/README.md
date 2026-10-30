# harness_e2e fixtures

End-to-end replays for `tests/test_harness_e2e.py` and the guard self-check `scripts/harness_selfcheck.py` (which holds the replay code): real recorder input → `sidereus/harness_plat._results` → the flow node the Harness screen draws.
Metadata only: stage titles, tool names, agent types, modes, rc, counts, relative seconds. No descriptions, prompts or command output.
Every catch case has a control (`pair`) under the same guard with the opposite `expect`; a guard that blocks or passes everything fails one of the two.
Pairs are mutual, except that one control may serve several catch cases (`guard-commit` → `guard-commit-after-pass`, whose own partner is `guard-commit-after-fail`).

| case | guard | situation | chain | expect | pair | node |
|---|---|---|---|---|---|---|
| `gate-pass-only` | gate | check.sh --fast PASS only | `scripts/evidence_rec.py` PASS row only | `no r2g` | `gate-red-green` | st "ok", r2g false, rows 1 |
| `gate-red-green` | gate | check.sh --fast FAIL then PASS on the same repo and head | `scripts/evidence_rec.py` FAIL then PASS rows → `harness_evidence.scan` | `r2g` | `gate-pass-only` | st "ok", r2g true, rows 2 |
| `guard-commit` | guard | git commit while the required Verify gate has no rc=0 evidence | `hooks/pl_guard.py` (via pl_flow main()) denies `git commit` before the required gate passed | `blocked` | `guard-commit-after-pass` | st "ok", deny 1, codes ["gate"], «Blocked 1» |
| `guard-commit-after-fail` | guard | git commit after Verify ran but its --full gate recorded rc=1 | `hooks/pl_guard.py`: `scripts/evidence_rec.py` rc=1 row of the gate's mode, then `git commit` | `blocked` | `guard-commit-after-pass` | st "ok", deny 1, codes ["gate"], «Blocked 1» |
| `guard-commit-after-pass` | guard | git commit after Verify passed and its --full gate recorded rc=0 | `hooks/pl_guard.py`: `scripts/evidence_rec.py` rc=0 row of the gate's mode, then `git commit` | `allowed` | `guard-commit-after-fail` | st "ok", deny 0, codes [], «Blocked 0» |
| `guard-jump` | guard | Verify dispatched while Build never ran | `hooks/pl_flow.py` main() denies a stage jump → `plmark/<sid>.runs.json` `deny` | `blocked` | `guard-jump-declared` | st "ok", deny 1, codes ["jump"], «Blocked 1» |
| `guard-jump-declared` | guard | Build declared skipped with [pl-skip:], then Verify dispatched | `hooks/pl_flow.py` main(): declared `[pl-skip:]` makes the later dispatch legal | `allowed` | `guard-jump` | st "ok", deny 0, codes [], «Blocked 0 · 1 declared skip(s)» |
| `guard-skip-declared` | guard | [pl-skip:] of Build, which requireGates does not list | `hooks/pl_guard.py`: `[pl-skip:]` of a stage requireGates does not list | `allowed` | `guard-skip-required` | st "ok", deny 0, codes [], «Blocked 0 · 1 declared skip(s)» |
| `guard-skip-required` | guard | [pl-skip:] of the required Verify gate | `hooks/pl_guard.py` denies a `[pl-skip:]` of a required gate | `blocked` | `guard-skip-declared` | st "ok", deny 1, codes ["skipgate"], «Blocked 1» |
| `keep-held` | keep | PASS recorded at commit A and HEAD is still A | temp git repo → `harness_trail` | `held` | `keep-reverted` | st "ok", state "held" |
| `keep-reverted` | keep | PASS at commit A, then a later commit restores A's parent tree | temp git repo → `harness_trail` (exact tree rollback) | `reverted` | `keep-held` | st "ng", state "reverted" |

Self-check fields (each case.json): `guard` = guard · gate · keep · `situation` = one line · `expect` = outcome the test derives from the node
(guard: `blocked` when deny > 0 else `allowed` · gate: `r2g` / `no r2g` · keep: harness_trail state) · `pair` = its partner case · `node` = node details asserted too.
Schema: `ev` = hook events (`e` pre/post, `tool` Agent/Bash, `stage`, `cmd` and `desc` for Bash, `denied` checked on Pre) or `{"check": {mode, rc}}` = a gate row recorded at that point ·
`rows` = check.sh records (`dt` seconds, `steps` = `[name, rc, n, failed, secs]`) · `steps` = ordered `commit` (file → content) / `check` (recorded at the current HEAD).
