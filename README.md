# Sidereus

**English** · [Korean](README.ko.md)

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.9, stdlib only](https://img.shields.io/badge/python-3.9%20stdlib%20only-3776AB.svg)
![Platform: macOS · Windows](https://img.shields.io/badge/platform-macOS%20%C2%B7%20Windows-lightgrey.svg)

Sidereus is a local viewer for checking the work of AI coding sessions. It runs next to the Claude Code, Codex CLI and Gemini CLI sessions in your terminals and shows them on one screen: which ones are waiting for you, whether each run followed its pipeline, and what evidence backs each result. It also draws a module and flow map of the repo and runs security checks on it. It never starts your agents or types into your terminal.

I usually have several Claude Code and Codex sessions running in different terminals and projects. I kept losing track of which one was waiting for me, and when a session reported "all tests pass" I had no quick way to check that it really ran them. I built Sidereus for that.

![Animated: a change-flow run lighting its stages in turn: Design, Implement, Verify, Review sends it back once, Implement and Verify again, then Review done](docs/images/hero-en.gif)

## Try the demo

The demo uses synthetic data and reads nothing from your machine.

```sh
git clone https://github.com/bugsterran/sidereus.git ~/sidereus && cd ~/sidereus
python3 -m sidereus start --demo --open      # port 18799, Ctrl-C stops it. Windows: py -m sidereus
```

## Pipelines

The viewer opens on this tab. A pipeline is a stage order you declare once in `.claude/pipelines/*.json`, with an agent and model per stage, gates and loop-backs. Sessions tag their work with `[pl:<pipeline>/<stage>]`, and each stage lights up while it runs.

On the left, **Working now** lists every live session as a card with its run summary and subagent tree. On the right, the stage canvas shows the run; click a stage to see its result and gate evidence: PASS or FAIL, test count, commit, loop-backs, and whether a PASS broke again later. A bug planted on purpose checks that a gate really catches it.

You can edit a pipeline on the canvas; saving shows a diff and makes a backup first. **Run** writes a request to a session, shows it to you, and sends it through the mailbox only after you confirm. In Claude Code, hooks deny a stage taken out of order and a `git commit` made before the required gates pass ([HOOKS.md](docs/HOOKS.md)).

No pipelines yet? Start from a template or ask a session for a draft. See the [guide](docs/GUIDE.md#watch-a-pipeline-run) and [EXTENDING](docs/EXTENDING.md).

![Pipelines Watch view: Working now session cards with subagent trees on the left; the stage canvas, the selected stage's result pane and the Running N card on the right](docs/images/pipeline-run-en.png)

## Structure

An agent draws the module map, and every edge is checked against the code (file, line, symbol) at a given commit. Each entry point gets its own flow. There is also a minimap, a treemap of how the code grew, and security scans (secrets, dependencies, SAST) per module. **Request fix** sends the findings to a session and asks it to run the check again once the fix is committed. See [STRUCTURE.md](docs/STRUCTURE.md).

![Architecture diagram with the Get an order flow lit from its HTTP entry through web and order to PostgreSQL, the flow list on the right and a minimap](docs/images/structure-arch-en.png)

## Timeline

The timeline shows what each session and subagent did and when, with pipeline stages laid over it. Open it when you want to check a result. The **Changes** chip counts files changed since a baseline, marks files that two sessions both touched, and opens the diff.

![Subagent timeline; the head line carries the session picker, the Changes chip with its baseline badge and the pipeline key](docs/images/timeline-en.png)

## Also included

- **Attention** rail: blocked sessions and sessions asking a question stay on top, with Done, Later and Reply on each row.
- Status bar with 5-hour and 7-day quota per account and the projected headroom at reset. Numbers marked `≈` are estimates ([GUIDE](docs/GUIDE.md)).
- Sessions drawer, alerts, and chat (mailbox rooms and DMs between sessions, which you can post to).
- **Tokens**: usage and cost by model, project and platform, and the most expensive subagent runs.
- **Branches**: which session made each commit and what it cost, uncommitted edits per worktree, conflict risk.
- **History** and **Insights**: past sessions by day, failures and tool errors over 30 days.

| **Branches** | **Tokens** |
|---|---|
| ![Commit graph with session chips per commit and worktree rows with conflict risk and uncommitted counts](docs/images/branches-en.png) | ![Weekly token donut by project, today's split, top costly runs and per-platform table](docs/images/tokens-en.png) |

## Scope

Sidereus is meant for people who run several CLI agent sessions from a terminal, across vendors, accounts or projects; who cannot send their conversations to an outside service; and who run quality gates in pipelines. Claude Code is supported first. Codex, Gemini and Cursor CLI connect through hooks ([HOOKS.md](docs/HOOKS.md)); their tokens are counted apart from Claude's limits. Gemini's plan limits live on Google's server, so check them with `/stats`. The Cursor IDE is not supported yet (#9), and Copilot and other CLIs are untested.

It is probably not what you want if you use one or two agents inside an IDE, if you only use Claude Code and just want waiting sessions first (Claude Code's agent view does that), or if your team needs cloud execution or organisation-wide governance.

This is one person's tool, published so others can fork it. The UI is in English and Korean, the defaults follow the author's habits, and some parts still assume macOS. It is not affiliated with or endorsed by Anthropic. Design and scope are in [CONCEPT.md](docs/CONCEPT.md); third-party notices in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Install

You need Python 3.9 or later (standard library only), Claude Code, and `git` for the Branches, Structure and diff views. The stock macOS `/usr/bin/python3` works; on a fresh Mac its first run offers to install the Xcode Command Line Tools, so accept and run again. macOS is tested, Windows works with a few gaps, Linux is untested. The demo server uses about 50 MB of memory.

```sh
git clone https://github.com/bugsterran/sidereus.git ~/sidereus && cd ~/sidereus
python3 -m sidereus start --open             # http://127.0.0.1:8799. Windows: sidereus.cmd start --open
```

Or install without a clone, using [pipx](https://pipx.pypa.io) or [uv](https://docs.astral.sh/uv/). A few features need a clone; the list is in Getting started.

```sh
pipx install git+https://github.com/bugsterran/sidereus    # or: uv tool install git+https://github.com/bugsterran/sidereus
sidereus start --open                                      # also: status · doctor · stop
```

To connect Claude Code, install the plugin from inside Claude Code, then restart Claude Code once:

```text
/plugin marketplace add bugsterran/sidereus
/plugin install sidereus@sidereus
```

[Getting started](docs/GETTING-STARTED.md) covers the rest: Windows setup, changing the port, manual hooks instead of the plugin, start at login, upgrading and uninstalling. Before installing, read what Sidereus reads and sends (keychain token for the quota lookup, advisory lookups, keeping the Mac awake), why other accounts on a shared Mac can reach its API, and how to turn each off in [SECURITY.md](SECURITY.md) and [CONFIG.md](docs/CONFIG.md).

## Privacy

Conversations from other sessions never appear on the page. Lists, timeline, cards and the MCP server carry metadata only: path, session id, model, state, counts and an agent's one-line task description. This is enforced in code.

The one exception is the work log. When you click a session or agent, Sidereus reads the end of that transcript and shows the recent instruction, replies, tool calls and file diffs. It does this only on click, and only for repos of sessions on this machine.

Sidereus never starts, stops or types into a session. Instructions you send go through the mailbox, and a copy stays there.

## MCP tools for agents

The plugin registers these. For manual setup see [MCP.md](docs/MCP.md).

| Tool | Returns |
|---|---|
| `sidereus_quota` | 5h/7d used %, tokens left, reset time, pace and one line of advice |
| `sidereus_file_peers(path)` | Who else edited this file in the last 30 minutes, and whether they have uncommitted edits |
| `sidereus_peers()` | Live sessions and subagents in the same repo, with state and context % |
| `sidereus_attention()` | Sessions waiting for you |

Agents rarely call them unprompted, so add a line about them to your `AGENTS.md` or `CLAUDE.md`. The server itself uses no Claude tokens; each MCP call adds a few lines to the calling session's context.

## Documentation

| Document | Contents |
|---|---|
| [GETTING-STARTED](docs/GETTING-STARTED.md) | Install and setup, step by step |
| [GUIDE](docs/GUIDE.md) | Everyday tasks, with screenshots |
| [CONFIG](docs/CONFIG.md) | Paths, config keys, environment variables, launchd, backups |
| [HOOKS](docs/HOOKS.md) | Hooks; Codex, Gemini and Cursor CLI setup; the mailbox Stop hook |
| [MCP](docs/MCP.md) | The `sidereus` MCP server |
| [PARALLEL-WORK](docs/PARALLEL-WORK.md) | Parallel worktrees (`claude -w <name> --tmux`) |
| [STRUCTURE](docs/STRUCTURE.md) | Structure tab: architecture diagram and flows, size treemap, languages |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | How the server, page, hooks and mailbox fit together |
| [EXTENDING](docs/EXTENDING.md) | Adding a CLI platform, language plug-in or pipeline |
| [REVIEW-PIPELINES](docs/REVIEW-PIPELINES.md) | Review pipelines per CLI, with templates |
| [sidereus-state.v1.json](docs/schema/sidereus-state.v1.json) | `GET /api/v1/state`, the stable metadata-only schema |

Settings (the gear icon) hold language, background tone and **Preferences**. Server-side values are saved in `config.local.json` and apply after a restart; every key is in [CONFIG.md](docs/CONFIG.md).

## Contributing

The project is shared as is, and forking is the way to change the core. Bug reports are welcome. Pull requests are accepted for extensions only: language plug-ins, CLI adapters and pipeline templates. See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) for private reports, [CHANGELOG.md](CHANGELOG.md), and the [milestones](https://github.com/bugsterran/sidereus/milestones) for the next release.

## How this was made

Most of the code and docs here were written by Claude Code sessions. I set the direction, reviewed the results and decided what shipped, watching those sessions in Sidereus itself.

## Credits

The 5-hour block rule and the `message.id` + `requestId` dedup key come from [ccusage](https://github.com/ryoppippi/ccusage). Other ideas were borrowed from Grafana, Datadog, Paseo, Orca, SourceTree, Conductor, Codex and Vibe Kanban. The code was written for this project.

## License

MIT. See [LICENSE](LICENSE).
