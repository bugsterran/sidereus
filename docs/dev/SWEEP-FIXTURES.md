# Sweep fixture world

Reproduces live-sweep defects in a sandbox, so a fix can be checked without the person's real sessions.
Everything is synthetic and metadata only (paths · ids · timestamps · line shapes). ⚠Never copy live files into it.

## Build

```
python3 scripts/sweep_world.py build --out <tmp> [--port N] [--now EPOCH]
python3 scripts/sweep_world.py append-ask --out <tmp>
```

- `build` generates the world in code (`tests/fixtures/sweep/manifest.json` lists the cases) under `<tmp>`; `--now` pins every timestamp (default: the current time).
- `append-ask` appends the answer (empty tool_result) to the case b ask, to replay a later poll.
- It prints the env to launch the viewer with:

| Variable | Value |
|---|---|
| `HOME` | `<tmp>/home` |
| `CLAUDE_CONFIG_DIR` | `<tmp>/cc` |
| `MAILBOX_DIR` | `<tmp>/data` |
| `SIDEREUS_USER_HOME` | `<tmp>/home` (external CLI hook paths; see TRAPS «HOME override alone») |
| `SIDEREUS_QUOTA_LOOKUP` | `0` (otherwise the sandbox calls the real usage API with the live keychain token) |
| port | a spare port (`--port`), never 8799 |
| unset | `CODEX_HOME` `GEMINI_CLI_HOME` `COPILOT_HOME` `PI_CODING_AGENT_DIR` (they win over `SIDEREUS_USER_HOME`) |

`sidereus_cli.py start` opens no browser unless `--open` is passed.

## Cases

| | Fixture | Must hold |
|---|---|---|
| a | project whose only pipeline file is invalid | the «Get started» checklist still shows |
| b | ask answered after the memo offset, beyond the 400 KB tail | no «Question waiting» |
| c | non-ASCII folder name + Windows `C--` slug | resolves to the same transcript folder as Claude Code |
| d | `states/bg-job-across-clear` (background job running across `/clear`) | the current output stays pinned |
| e | external CLI hook files under the sandbox home | Settings › «Diagnostics» reads only `<tmp>/home`, never the real home |

## Adding a case

One builder in `scripts/sweep_world.py` + a manifest entry + one test that fails without the fix and passes with it. Add a row above.
