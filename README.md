# Sidereus

**English** · [Korean](README.ko.md)

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.9, stdlib only](https://img.shields.io/badge/python-3.9%20stdlib%20only-3776AB.svg)
![Platform: macOS · Windows](https://img.shields.io/badge/platform-macOS%20%C2%B7%20Windows-lightgrey.svg)

**A local observatory for verifying AI coding sessions.**
It runs beside the Claude Code, Codex CLI and Gemini CLI sessions in your terminals and shows, on one screen, whether each run followed its pipeline and what evidence backs each verdict. It never runs your agents or touches your terminal.

- **Monitoring**: every session on one screen, the ones waiting on you first, with a timeline of what each agent did.
- **Pipelines and Harness report**: stage order, gates, and whether the results held afterwards.
- **Structure and security**: a module and flow map of the repo, plus security checks.

![Animated: a change-flow run lighting its stages in turn — Design, Implement, Verify, Review sends it back once, Implement and Verify again, then Review done](docs/images/hero-en.gif)

## Try the demo

Synthetic data only; nothing real is read.

```sh
git clone https://github.com/bugsterran/sidereus.git ~/sidereus && cd ~/sidereus
python3 -m sidereus start --demo --open      # port 18799, Ctrl-C stops it. Windows: py -m sidereus
```

## Pipelines

The viewer opens here. A pipeline is a stage order declared once in `.claude/pipelines/*.json` (agent and model per stage, gates, loop-backs); sessions tag their work with `[pl:<pipeline>/<stage>]` and the stages light up as they run.

- **Working now** (left): every live session as a card with its run summary («Working · Verify», «Needs you · Review», «✓ change-flow done») and its subagent tree. Collapse it to a rail of status dots or drag its edge.
- **Watch** (right): the stage canvas fills the window; below it the selected stage's result and gate evidence, then a fixed «Running N» card for every run in progress. Drag the grips to resize any region; double-click a grip to reset.
- **Evidence per stage**: gate PASS/FAIL, test count, commit, loop-backs, and whether the PASS broke again later. A bug planted on purpose checks that a gate actually catches it.
- **Edit**: palette, editable canvas and stage editor. «Close» when nothing changed; «Cancel» or «Save» (diff preview + confirm, backup first) when something did.
- **Run**: «▶ Run» composes a request to a session; you see the preview and confirm, and it goes through the mailbox. Nothing is sent on its own.
- **Guards**: in Claude Code, hooks deny a stage out of order or a `git commit` before the required gates pass ([HOOKS.md](docs/HOOKS.md)).

No pipelines yet? Start from a template or ask a session for a draft. Details: [GUIDE](docs/GUIDE.md#watch-a-pipeline-run), [EXTENDING](docs/EXTENDING.md).

![Pipelines Watch view: «Working now» session cards with subagent trees on the left; the stage canvas, the selected stage's result pane and the «Running N» card on the right](docs/images/pipeline-run-en.png)

## Structure analysis

An agent-drawn module map where every edge is checked against the code (file, line, symbol) at a commit. One flow per entry point, a minimap, a treemap of how the code grew, and security scans (secrets, dependencies, SAST) per module. «Request fix» sends the findings to a session and asks it to re-run the check once the fix is committed. Details: [STRUCTURE.md](docs/STRUCTURE.md).

![Architecture diagram with the «Get an order» flow lit from its HTTP entry through web and order to PostgreSQL, the flow list on the right and a minimap](docs/images/structure-arch-en.png)

## Timeline (evidence)

What each session and subagent actually did, and when, with pipeline stages overlaid. Open it to check a verdict. A «Changes» chip counts files changed against a baseline («⚠ shared» when two sessions touched one) and opens the diff.

![Subagent timeline; the head line carries the session picker, the «Changes» chip with its baseline badge and the pipeline key](docs/images/timeline-en.png)

## Also on the screen

| Part | Answers |
|---|---|
| Attention (left rail) | Who needs me now? Blocked and asking sessions stay at the top, with Done, Later and Reply on the row. Scores: `sidereus/attention.py`. |
| Status bar | Will quota last until the reset? 5-hour and 7-day usage per account, projected headroom. |
| Sessions drawer | Which sessions are live: running, thinking, waiting, done, stopped. |
| Alerts | What finished or failed. OS notification optional, off by default. |
| Chat | Mailbox rooms and DMs between sessions. You can post too. |
| Tokens | Tokens and cost by model, project and platform; the costliest subagent runs. |
| Branches | Which session made each commit and what it cost; uncommitted edits per worktree; conflict risk. |
| History · Insights | Past sessions by day; failures and tool errors over 30 days. |

Numbers marked `≈` are estimates: the token caps behind the official quota % are not published, so Sidereus back-solves them each cycle.

| **Branches** | **Tokens** |
|---|---|
| ![Commit graph with session chips per commit and worktree rows with conflict risk and uncommitted counts](docs/images/branches-en.png) | ![Weekly token donut by project, today's split, top costly runs and per-platform table](docs/images/tokens-en.png) |

## Scope

For:
- several CLI sessions run from a terminal, across vendors, accounts or projects (Claude Code first; Codex, Gemini and others through adapters)
- work whose conversations cannot be sent to an outside service
- projects that run quality gates in pipelines

Not for:
- one or two agents inside an IDE
- Claude Code only, when all you want is waiting sessions first; Claude Code's own agent view covers that
- teams that need cloud execution or organisation-wide governance

One person's tool, published to be forked. The UI speaks English and Korean; expect the author's defaults and some macOS assumptions. Not affiliated with or endorsed by Anthropic. Design and scope: [CONCEPT.md](docs/CONCEPT.md). Third-party notices: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Install

Requirements:
- Python 3.9 or later, standard library only. The macOS `/usr/bin/python3` works; on a fresh Mac its first run asks to install the Xcode Command Line Tools — accept, then run again.
- Claude Code. Transcripts are read from `~/.claude/projects/` (`$CLAUDE_CONFIG_DIR/projects/` when set).
- `git` for the Branches, Structure and diff views.
- macOS is tested. Windows 11 was checked on a real PC (2026-10-17); gaps are listed in [GETTING-STARTED](docs/GETTING-STARTED.md#2-start-the-viewer). Linux is untested.
- Footprint: the `--demo` server uses about 45 MB RSS just after start and a few page loads (44 MB on macOS, 46 MB on Linux; the real viewer with many sessions uses more); the shipped code is about 11 MB, 18 MB with the screenshots (macOS, Python 3.9.6, 2026-10-28).

```sh
git clone https://github.com/bugsterran/sidereus.git ~/sidereus && cd ~/sidereus
python3 -m sidereus start --open             # http://127.0.0.1:8799; Windows: sidereus.cmd start --open
```

Without a clone, with [pipx](https://pipx.pypa.io) or [uv](https://docs.astral.sh/uv/):

```sh
pipx install git+https://github.com/bugsterran/sidereus    # or: uv tool install git+https://github.com/bugsterran/sidereus
sidereus start --demo --open                               # also: sidereus start --open · status · doctor · stop
```

Upgrade with `pipx upgrade sidereus` (`uv tool upgrade sidereus`). Start at login (`start --install-service`) and pipeline scoring (`scripts/pl_eval.py`) need a clone: the pipx/uv path changes on every reinstall. The first start after updating to 0.7.0 rebuilds the tool usage cache once (about a minute of «Loading…» in Tools and Harness).

On Windows write `py` wherever these docs say `python3`, or run `sidereus.cmd` from the clone. Install Python, Git for Windows and Claude Code first: [Getting started §0](docs/GETTING-STARTED.md#0-prerequisites).

If 8799 is taken (another clone, or another account on the same Mac), `status` only says something answers there with no run record. Pick a free port; it is saved in `config.local.json` and the MCP server follows it:

```sh
python3 -m sidereus start --port 8800 --open
```

Connect Claude Code with the plugin or the manual hooks, not both ([§5](docs/GETTING-STARTED.md#5-mcp-and-hooks)). The plugin, inside Claude Code (or `/plugin marketplace add ~/sidereus` from a clone):

```text
/plugin marketplace add bugsterran/sidereus
/plugin install sidereus@sidereus
```

The plugin still needs a running viewer. Hooks and MCP tools reach only sessions started after the install, so restart Claude Code once. Check: `python3 -m sidereus status` shows `200` and a pid, and `sidereus_peers` in a new session lists that session. Uninstall: [Getting started](docs/GETTING-STARTED.md#uninstall).

Before you install:
- On macOS it reads the Claude Code token from the keychain for the quota lookup at `api.anthropic.com` (`"quota_lookup": false` turns it off). The only other outbound requests are package-name and version lookups at `api.osv.dev` for the security checks (skipped offline). It holds `caffeinate` while sessions work (`"keep_awake": false`).
- Its hooks apply to every Claude Code session; in a project with `.claude/pipelines/*.json` they can deny an out-of-order step or an early `git commit` ([MCP and hooks](#agents-can-ask-too-mcp)).
- On a Mac shared with other accounts, they can call this viewer's API too: there is no auth beyond loopback ([SECURITY.md](SECURITY.md#model)).
- Keychain, network, AppleScript and file access, and the optional paid quota probe (off by default): [SECURITY.md](SECURITY.md), [CONFIG.md](docs/CONFIG.md).

## Privacy

Other sessions' conversations never appear on the page. Lists, timeline, cards and the MCP server carry metadata only: path, session id, model, state, counts, and an agent's one-line task description. This is enforced in code.

The one exception is the work log. Clicking a session or agent reads the tail of that transcript and shows the recent instruction, replies, tool footprints and file diffs — only on click, and only for repos of sessions on this machine (the same allow list as diffs).

Sidereus relays; it does not drive. Instructions go to a session through the mailbox, and what was sent stays there.

## Agents can ask too (MCP)

Already registered if you installed the plugin (on Windows run `setx SIDEREUS_PYTHON py` first, see [§5](docs/GETTING-STARTED.md#5-mcp-and-hooks)). Manual registration on macOS, from the clone (on Windows run `py -m sidereus setup-claude` and use the line it prints):

```sh
claude mcp add --scope user sidereus -- /usr/bin/python3 "$PWD/mcp/sidereus_mcp.py"
```

| Tool | Returns |
|---|---|
| `sidereus_quota` | 5h/7d used %, tokens left, reset time, pace against your goal, one advice line |
| `sidereus_file_peers(path)` | Who else edited this file in the last 30 min, whether they are live, uncommitted edits |
| `sidereus_peers()` | Live sessions and subagents in the same repo (any worktree), with state, tool and context % |
| `sidereus_attention()` | Sessions waiting for you |

The tools need the viewer running and appear only in sessions started after `claude mcp add`. Agents rarely call them unprompted, so add a rule to your `AGENTS.md` or `CLAUDE.md`. Details: [MCP.md](docs/MCP.md).

Sidereus never starts or stops sessions. Its pipeline hooks (`pl_mark`, `pl_flow`, `pl_guard`) can deny a call only in a project with `.claude/pipelines/*.json`: an untagged Agent call, a stage out of order in a `[pl:<name>/<stage>]` run, or a `git commit` before the run's `guards` gates pass. Off per project with «Apply». Details: [HOOKS.md](docs/HOOKS.md).

The server reads transcripts, git and OpenTelemetry logs in background threads with incremental caches and serves the page and the MCP server from `127.0.0.1:8799`. It costs no Claude tokens; an MCP call adds a few lines to the calling session's context ([ARCHITECTURE.md](docs/ARCHITECTURE.md)).

## Documentation

| Document | For |
|---|---|
| [GETTING-STARTED](docs/GETTING-STARTED.md) | Install and setup, step by step |
| [GUIDE](docs/GUIDE.md) | Everyday tasks, with screenshots |
| [CONFIG](docs/CONFIG.md) | Paths, config keys, environment variables, launchd, backups |
| [HOOKS](docs/HOOKS.md) | Hooks; Codex and Gemini CLI setup; the mailbox Stop hook |
| [MCP](docs/MCP.md) | The `sidereus` MCP server |
| [PARALLEL-WORK](docs/PARALLEL-WORK.md) | Parallel worktrees (`claude -w <name> --tmux`) |
| [STRUCTURE](docs/STRUCTURE.md) | Structure tab: architecture diagram and flows, size treemap, languages |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | How the server, page, hooks and mailbox fit together |
| [EXTENDING](docs/EXTENDING.md) | Adding a CLI platform, language plug-in or pipeline |
| [REVIEW-PIPELINES](docs/REVIEW-PIPELINES.md) | Review pipelines per CLI, based on what the platforms published; templates |
| [sidereus-state.v1.json](docs/schema/sidereus-state.v1.json) | `GET /api/v1/state`, the stable metadata-only schema |

## Customising

Settings (gear icon) hold the language, background tone and «Preferences». Server-side values go to `config.local.json` and apply after a restart. `/usr/bin/python3 mailbox_config.py` (Windows: `py mailbox_config.py`) prints the config path and the merged result. Every key and the settings API: [CONFIG.md](docs/CONFIG.md).

## Other CLIs

Codex CLI and Gemini CLI report through hooks and appear next to Claude Code sessions with their own token counts. ⚠ Their tokens never count toward Claude's 5h/7d limits or cost. Cursor CLI: macOS verified (2026.10.22); the Cursor IDE is not supported yet (#9). Copilot and other CLIs can use the same hook, not yet verified. Setup: [HOOKS.md](docs/HOOKS.md).

⚠ Codex ignores `hooks.json` until you approve it once with `/hooks` in its TUI, and again after every edit (the entries read `ext_hook.py`, not «Sidereus»). Until then a Codex session that wrote in the last 10 minutes shows marked «Hooks not connected», with folder and model only and no state.

Verified on macOS: Codex CLI 0.163.0 — session list and state, turn-end mail, pipeline stage marks and the «Terminal» button; Gemini CLI 0.61.0 — turn-end mail and stage marks. Other CLIs are untested. Gemini CLI's plan limits live only on Google's server, so Sidereus shows its token counts and no limit bar; check what is left with `/stats` in Gemini CLI.

## How this project works

- Shared as is. Forks are the way to change the core.
- Bug reports welcome. PRs accepted for extensions only (language plug-ins, CLI adapters, pipeline templates): [CONTRIBUTING.md](CONTRIBUTING.md).
- Security model and private reporting: [SECURITY.md](SECURITY.md). Release notes: [CHANGELOG.md](CHANGELOG.md). Next release: [Milestones](https://github.com/bugsterran/sidereus/milestones).

Ideas borrowed from [ccusage](https://github.com/ryoppippi/ccusage) (the 5-hour block rule and the `message.id` + `requestId` dedup key), Grafana, Datadog, Paseo, Orca, SourceTree, Conductor, Codex and Vibe Kanban. The code is our own.

## License

MIT. See [LICENSE](LICENSE).
