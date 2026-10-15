# Contributing

**English** · [Korean](CONTRIBUTING.ko.md)

Sidereus is a personal tool, shared as-is. No support, no roadmap promise. The direction is the author's.

Settings › «Preferences» and `config.local.json` cover most needs without code — see [Customising](README.md#customising) and [docs/CONFIG.md](docs/CONFIG.md).

## What we accept

| Tier | What | How |
|---|---|---|
| Bug reports | Welcome | An issue with steps to reproduce, and a check that the bug does not involve conversation text on the page (metadata only). |
| Extension PRs | Accepted | Structure language plug-ins (`sidereus/structure_lang_*.py` via `lang_register`) · CLI adapters (platform readers like `sidereus/plat_codex.py`) · pipeline templates (`.claude/pipelines/*.json`). |
| Core PRs | Not accepted | Server, UI, state shape. **Fork** for these. |

Why: extensions plug into shared formats, so forks stay compatible with each other.

Extension docs: [docs/EXTENDING.md](docs/EXTENDING.md) (also [docs/ARCHITECTURE.md § 8](docs/ARCHITECTURE.md#extending) · [docs/STRUCTURE.md](docs/STRUCTURE.md)).

## Pull requests and AI help

Writing code is cheap now; reviewing it is not (see James Ross, "Open source as we knew it is dead"). So:

- Say whether the PR was written with AI help (checkbox in the PR template). Both are fine; not saying is not.
- Include a failing test or a reproduction that the PR fixes. PRs without one are closed without review.
- Adapter PRs are reviewed only after the adapter contract tests pass: `bash tests/run.sh -p test_adapter_contract.py` (`tests/test_adapter_contract.py`).
- One change per PR. Keep it small.

## Extension PR checklist

- `bash scripts/check.sh --fast` passes.
- Tests use crafted inputs and run in under 1 s; no live files, clock or network.
- Metadata only — no conversation text or tool inputs on the page or in MCP answers.
- Comments in English.
- No new dependencies (standard library only, runs offline).

## Gates in a fork

```sh
bash scripts/check.sh --fast   # py_compile (/usr/bin/python3, 3.9) + node --check + leak scan
bash scripts/check.sh --full   # also unit tests and the screen check
bash tests/run.sh              # unit tests only
```

- ⚠Use `/usr/bin/python3` (3.9) — launchd runs the viewer with it; a newer Python lets 3.9-incompatible syntax slip in. Tests never touch live files, the clock or the network.

## Keep these if you want the metadata-only guarantee

- Never put conversation text or tool inputs on the page or in an MCP answer — paths, session ids, models, states, counts and times only. The one exception is the click-to-open work popup (`sidereus/work.py`).
- Loopback only; keep the Host/Origin guard on every POST. `esc()` anything put into `innerHTML`.
- No git writes, no CLI control (pty, send-keys, spawn/kill). Git calls go through `git_argv`.
- Standard library only; it must run offline.
- What Sidereus never does, and each off switch: [SECURITY.md](SECURITY.md).
