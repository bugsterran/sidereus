# Documents

User docs have a Korean version alongside (`*.ko.md`).

## Using Sidereus

| Document | For |
|---|---|
| [../README.md](../README.md) · [Korean](../README.ko.md) | What Sidereus is, install, uninstall |
| [CONCEPT.md](CONCEPT.md) · [Korean](CONCEPT.ko.md) | The idea: watch, record, relay — and what it never does |
| [GETTING-STARTED.md](GETTING-STARTED.md) · [Korean](GETTING-STARTED.ko.md) | Setup step by step |
| [GUIDE.md](GUIDE.md) · [Korean](GUIDE.ko.md) | Everyday tasks, with screenshots |
| [CONFIG.md](CONFIG.md) · [Korean](CONFIG.ko.md) | Paths, `config.local.json` keys, environment variables, launchd, distribution exclusions |
| [HOOKS.md](HOOKS.md) · [Korean](HOOKS.ko.md) | Hooks; Gemini, Codex and other CLIs next to Claude Code |
| [MCP.md](MCP.md) · [Korean](MCP.ko.md) | The `sidereus` MCP server |
| [PARALLEL-WORK.md](PARALLEL-WORK.md) · [Korean](PARALLEL-WORK.ko.md) | Parallel worktrees from the Branches tab |
| [STRUCTURE.md](STRUCTURE.md) · [Korean](STRUCTURE.ko.md) | Structure tab relations mode; supported languages and frameworks |
| [EXTENDING.md](EXTENDING.md) · [Korean](EXTENDING.ko.md) | Adding platforms, language plug-ins and frameworks |
| [REVIEW-PIPELINES.md](REVIEW-PIPELINES.md) · [Korean](REVIEW-PIPELINES.ko.md) | Writing a review pipeline: what the platforms publish, templates per CLI |
| [EXPERIMENT-LOG.md](EXPERIMENT-LOG.md) · [Korean](EXPERIMENT-LOG.ko.md) | Each idea with what was tried, what was measured and the verdict |
| [schema/sidereus-state.v1.json](schema/sidereus-state.v1.json) | `GET /api/v1/state`, the stable metadata-only schema. The Architecture map's `map.json`: [STRUCTURE](STRUCTURE.md) |
| [../SECURITY.md](../SECURITY.md) · [../CONTRIBUTING.md](../CONTRIBUTING.md) · [../CHANGELOG.md](../CHANGELOG.md) | Security model, contribution policy, release notes |

## Changing Sidereus

| Document | For |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) · [Korean](ARCHITECTURE.ko.md) | What it reads, what it serves, where each piece lives |
| `../AGENTS.md` | Rules for working in the repo. They override every other doc. |
| `../refactor/STAGE3.md` | Python module order and ownership |
| `../scripts/README.md` | Gates, leak scan, screen and router checks |
| `dev/HANDOVER.md` | Run and check commands, feature log |
| `dev/TRAPS.md` | Traps already hit — index of `dev/traps/<domain>.md`. Read the area before you touch it. |
| `dev/FILEMAP.md` | One row per `web/js` and `web/css` file |
| `notes/` | Design notes and deferred research |

`AGENTS.md`, `dev/` and `notes/` are internal. `.distignore` (mirrored as `export-ignore` in `.gitattributes`) leaves them out of the `git archive` zip only; the git repository and its forks contain them.
