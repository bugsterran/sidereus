# plreplay fixtures

Recorded pipeline event sequences replayed by `tests/test_plreplay.py` through `hooks/pl_flow.py`, then checked at three layers per checkpoint:

1. raw `plmark/<sid>.runs.json` (`st[t].s/k/n`, `end`, `cur`)
2. `sidereus/pl_runs.pl_model` (`o/k/via/n`, `end`)
3. web/js: `tlPlOne` → `plPrLt` (`st/k/via`, ended-run cut), `tlPlCur`, `tlPlSt`, `plPulseOn`

Metadata only: tags, tool names, agent types, booleans, relative seconds. No descriptions, prompts, commands or results.

## Schema

```
{"v": 1, "note": "...",
 "pipe": {"name": "demo-flow", "stages": [...]},          // same shape as .claude/pipelines/<name>.json
 "ev": [{"t": 0, "e": "pre|post|bgdone", "tool": "Agent|Task|SendMessage|Bash",
         "tag": "[pl:demo-flow/Build]" | "[pl-skip:demo-flow/Verify]" | "",
         "sub": "sidereus-implementer", "model": null, "bg": 0, "aid": "a01", "to": null, "commit": 0, "denied": 0}],
 "cp": [{"at": 3, "act": "run", "end": 0, "cur": "Build", "st": {"Design": "done n=1", "Build": "run k=2 via=Verify n=2"},
         "raw": {...}, "model": {...}, "view": {"status": "fin", "cur": "..."}, "pulse": [["Verify", "Build"]], "plm": "Build", "cm": {"Build": 1}}]}
```

- `t` seconds from the run start. `e: bgdone` = a background agent `aid` finished (no hook event; it only leaves the live list).
- `aid` on Agent/Task = the agent it launches; on Bash = the subagent that ran it (hook `agent_id`). `to` = SendMessage target.
- `bg: 1` = `run_in_background` + an async receipt as the Post response. `commit: 1` = the Bash runs `git commit`.
- `denied: 1` = the Pre must be denied (its Post is skipped); a Pre with `denied: 0` must not be.
- `cp.at` = event index the checkpoint runs after; `act` = session activity for `pl_model` (`run|ask|perm|end|idle`); `plm` = main marker stage.

## Cells

`<o>[ k=N][ via=T][ n=N]` — `o` in `run|done|skip|back|fail|hold|wait`; missing stage = `wait`; `k` defaults to 1.
`n` = dispatch count, checked in layers 1–2 only (layer 3 `n` counts agents shown). `via` is checked in layers 2–3.
`raw` / `model` / `view` override cells for that layer only; `view.status` defaults to `fail` if a cell fails, else `fin` when `end`, else `run`.
`pulse` lists the loop-back edges `[from, to]` expected to pulse (all others must not).
`cm` = `{title: N}` commit times expected on that stage, checked in all three layers (raw `st[t].cm`, model `stages[t].cm`, view `lt[t].cm`).

## Adding one

1. Mine a session with `scripts/plreplay_mine.py` (emits `"cp": []`), or write `ev` by hand.
2. Write each checkpoint from what the screen **should** show. ⚠Never copy expectations from replay output — that only freezes today's behaviour.
3. Prove the fixture fails on the code before the fix (load `git show <fix>^:hooks/pl_flow.py` as a temp module and call `replay(fx, hook)`).
