# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Pipelines: clickable marks are at least 24px; session state is named in words (title and accessible name), not only by its dot; «↺n», «Unverified» and the stage commit explain themselves on hover; the canvas refits on first open when live run data widens the cards, so it no longer opens clipped at 900/1100.
- Pipelines: a project with no pipeline opens on one primary start («Ask AI for a draft»); «Start from a template» is secondary, the quick templates fold behind «Quick templates ▾», and «Apply» appears once the project has a pipeline.
- Pipelines: clicking a subagent in «Working now» also opens its work log, the same popup as a Timeline agent row.
- Pipelines: «Cross-review (Codex)» template — one main stage where the session runs a read-only `codex exec` review of `git diff` (billed to the Codex account, one-shot; Sidereus never runs Codex). Copying a template now keeps agent `main` instead of turning it into general-purpose.
- Pipelines: work outside a pipeline is declared with a Bash described `[pl-none:<category>]` (small-fix · no-fit · explore · other; only the category and time are kept). In a project with pipeline files, the first Edit/Write or git commit with no open run and no declaration is denied once with the project's pipeline names. Each session row shows a chip: the run «<name> · <stage>», «No pipeline · <category>» or «Undeclared».
- Mailbox: Codex mail wake — the example Stop hook now runs `gemini_mail_stop.py --platform codex --wake`, which spawns a detached waiter that starts one turn on the session's own thread through the local Codex app-server socket when mail arrives (ids and a count only; exits if you type first; experimental API checked on 0.163.0; macOS/Linux only). `ext-hooks/codex-config-example.toml` auto-approves only the mailbox tools. `--wait` stays for unattended sessions.
- Structure: the architecture header shows which AI drew the map — platform logo and model after «Generated», each model when stages used different ones (stage names in the tooltip). Sidereus records it from the running session's own metadata in its own store, not from the map files; older maps show «Drawn by: unknown».

### Changed

- First screen: the viewer opens on Pipelines and the rail lists Pipelines before Timeline; Timeline becomes the evidence view behind a verdict. A saved tab or tab order still wins. The Pipelines tab has a collapsible, resizable «Working now» list on the left (each live session's Timeline name cell plus a one-line run summary; click a session to open its run on the right; collapsed it is a rail of status dots). The tab is split into «Watch» (list, select-only canvas, the running or last finished stage's result and gate evidence) and «Edit» (palette, editable canvas, stage editor under an «Editing <name>» band; «Apply», gate counts and evaluation live here) behind «✎ Edit»; «Edit» shows «Close» while nothing changed and «Cancel» beside «Save» once something did (Cancel writes nothing); drafts show a «Draft — not saved yet» band with «✓ Save this draft» and «Cancel» (Esc does the same); the mode is remembered, unsaved edits survive the switch, a new pipeline opens in «Edit» and a borrowed one stays in «Watch». A project with no pipelines leads with «Start from a template» and «Ask AI for a draft».
- Structure: a framework name joined with « + » or «, » (e.g. a BE and an FE stack) shows as one badge per part, so each wraps instead of being clipped; the full name stays in the tooltip.
- Chat: the «Participants» panel shows each participant's platform logo when the id matches a live session.

### Fixed

- Pipelines: canvas stages and edges are reachable with Tab and selected with Enter/Space; the Watch and split grips move with the arrow keys and carry labels and values for screen readers.
- Pipelines: the run summary in «Working now» widens with the list instead of stopping at 16 characters.
- Pipelines: the «Running N» card lists failed or blocked runs first and always shows at least two rows; a failed run was cut off below the first row.
- Pipelines: «Working now» subagent rows show the task description instead of only the agent type (the type moves to the tooltip).
- Pipelines: switching project (picker, «Working now», overview, workflow row, «+ Add project») closes an open «Ask AI for a draft» form and «Standard templates» panel instead of leaving them above the new project's canvas.
- Pipelines: a project with no pipelines shows its start row as a panel with full-size controls (30px «Start from a template» / «Ask AI for a draft», 26px filled template buttons) instead of 22px chips.
- Pipelines: the «Working now» run summary names the stage as the canvas does (English display name in English, not the raw stage title).
- Attention: a «done · waiting» row appears about 15 s after a session ends its turn (was 120–150 s); a hidden tab now polls every 10 s instead of 30 s.
- Pipelines: the «Cross-review (Codex)» template now runs `codex exec` with `< /dev/null` (it hung with an open non-TTY stdin) and closes the run with `[pl-end:…]` after the review.
- Pipelines: a fresh git clone with no session history no longer opens the Sidereus repo's own pipelines by default; that project is listed last and opens only when picked.
- Pipelines: copying a pipeline from another project keeps an orchestrator stage (agent `main`) instead of turning it into general-purpose and listing `main` as a replaced agent.
- Structure: «Request fix» in the security window now asks the session to re-run the security check (it asked for an architecture re-analysis, which never refreshed the Security badge). A scan older than HEAD shows ⚠ and a dashed border on the badge, with «Scanned commit … · HEAD now …» in the tooltip.
- Timeline: a connected session that sat idle longer than the window keeps its row (no bars) instead of disappearing.
- Rail: the chat unread count on the left rail is readable in the light theme (white bold on blue instead of dark text on mid blue).
- Attention: «... done N unread» no longer waits for «Seen» once the session has carried on past the completion (more than 60 s of later activity in the same session), like failure cards.
- Pipelines: a Codex (or other non-Claude CLI) stage no longer stays «running» for 45 minutes after its turn ends without an end marker; it closes like a Claude stage when main stops.
- Work popup: sending to a Codex session no longer asks «cannot receive right now — send anyway?»; the recipient line says it is delivered when the session's next turn ends.
- Structure: the architecture header no longer wraps into many lines at narrow widths — the «older than the code» notice moved onto the «Generated» badge (⚠ + tooltip) and the framework badge is capped with its full name in the tooltip.

## [0.5.0] - 2026-10-20

### Added

- Structure: the security issues window shows a running security check as «Running · stage n/of · <stage> · <elapsed>», the same progress line as an architecture-map run, for Claude and Codex sessions; a check ends only when the review stage writes its record (the scan stage's log record no longer ends it), and a dead session reads «No session».
- Chat: room cards, the open room's member strip and the invite picker show each participant's platform logo (from the live session list; no logo when the id matches no session).
- Mailbox: an idle Codex session can pick up mail (opt-in, for unattended sessions). Adding `--wait` (timeout 3600) to the Codex Stop hook (`ext-hooks/codex-hooks-example.json` ships it off, because typed input queues while it waits) makes it wait inside its own Stop by polling the bus file's stat every 2 s (same code on every OS, no model call while waiting; `SIDEREUS_MAIL_WAIT_MAX` caps wakes per human prompt) and skips the wait under `codex exec`. One wake-method table (`hooks/mail_wait.py`): Claude async rewake, Codex Stop wait, Gemini turn end, others none. A session that cannot be woken with mail unread for 10+ minutes shows in attention as «Mail waiting · session idle» (counts and age only). Refs #14.
- Structure: the security issues window filters by severity («All severities / High and above / Critical only») and tool, and «Hide rule» hides a rule per repo until «N rules hidden · Show»; the tab badge counts only rules not hidden (tooltip says how many are hidden). View only — check results, log and report are unchanged.
- arch-map: the gate (`scripts/arch_verify.py`) also checks map quality and writes `quality.json`. It fails when edge labels only repeat the target module's name (3+ edges and 25%+ of edges) or two flows share one entry label, and warns on flows sharing 80%+ of their steps, accessor-only calls, modules with no edge and stores with no read/write. The arch-map rules state the same checks, an entry's flow covers only its own handler, and a single-session (Codex) run re-reads only the previous stage's files at each stage.
- Pipelines: the «Evaluation» panel's «Result layer» states per pipeline, without a score, how many gates were seen failing, runs and blocked order violations, how many gate passes in the last 30 days broke later or had a fix follow within 14 days, and the review loop-back share against the 30 days before; `scripts/pl_report.py` writes the same facts to a dated report, refreshed weekly at run end.
- Timeline: the «Session» picker and «Changes» chip moved from the toolbar to the right of the «Subagent timeline» head line (the toolbar no longer wraps at 1100px). The «Changes» chip starts with a badge naming the baseline the files are counted against (Uncommitted, Unpushed, Since session start, Since the default branch); it turns the warning colour when the chosen baseline was not available and another was used.
- Timeline: the head line no longer reflows as its text changes. The summary wraps by a fixed basis and ends in «…» when it runs long (full text in its tooltip); the «Session» label and the word «Changes» moved into the accessible name and tooltip; the pipeline key shows inline when the line has room and folds to «Pipeline ▾» with a hover/focus popover when it does not.
- Plugin: installs straight from GitHub (`/plugin marketplace add bugsterran/sidereus`), no clone needed; a local clone still works. Without a clone, pipeline scoring is skipped.
- Pipelines: the «Pipelines» empty state shows the template choices instead of a blank list.
- Install without a clone: `pipx install git+https://github.com/bugsterran/sidereus` (or `uv tool install git+…`) puts `sidereus` on PATH; `start`, `status`, `doctor` work from it, start at login still needs a clone.
- `python3 -m sidereus doctor` prints one `OK`/`FAIL` line per setup check (Python 3.9+, git, claude, hooks connected, viewer answering; on Windows `SIDEREUS_PYTHON` and the Store alias) with the fix on each `FAIL`; exit 1 on any `FAIL`, writes nothing.
- Tokens: the Codex row of «By platform» shows each plan-limit window with its used %, reset time and the plan name (read locally from the newest rollout record that carries limits; «No limit data» when none did); the Codex status-bar tooltip shows the same line.
- Structure / Pipelines: arch-map and pipeline run requests can be sent to Codex sessions. A Codex recipient gets the stages to run in that session with `[pl:]` shell markers instead of the Agent tool; it needs one `mailbox_login` in that session first (until then send stays off, as for any session not logged in). Requests to Claude sessions are unchanged. With a Codex recipient both dialogs note that it picks the request up when its current or next turn ends (an idle Codex session is not woken).
- Codex: mail worker mode (`.mail-worker` in the folder or `SIDEREUS_MAIL_WORKER=1`, same opt-in as Gemini) keeps an idle Codex session waiting for mail at turn end: it calls `mailbox_wait`, does the task that arrives, replies on the same thread and stops after `SIDEREUS_MAIL_WORKER_MAX_IDLE` empty rounds; a new typed prompt resets the count. Needs `tool_timeout_sec = 3600` in `[mcp_servers.mailbox]` (Refs #14).

### Changed

- Security checks: findings use the levels critical / high / medium / low instead of error / warning (older result files are converted on load); the issues window header counts each level, the tab badge is red with any critical or high finding.
- Hooks: mailbox relay headers, stop-hook block reasons and invite notices shown to the model are in English.

### Fixed

- Sessions: a short branch name (such as «dev») no longer spills over the account chip.
- Sessions: a session with one watcher shows the watcher's label (e.g. «Mailbox watch») instead of «watch 1» followed by a stale last tool.
- Timeline: the English toolbar fits on one line at 900px (the «?» help wrapped to a second line).
- Structure: an architecture focus-view edge label near the right edge is no longer cut off by the drawing's edge.
- Codex: the SessionStart mailbox notice no longer fails with «hook returned invalid session start JSON output».
- Security checks: the scan reads the files of the commit it is stored under (a `git archive` export of HEAD in a temp folder) instead of the working tree, so uncommitted edits and untracked files no longer leak into a result labelled with that commit. The repo itself is only read.
- Security checks: the dependency scan no longer disappears when a repo has no lockfile — the osv-scanner row shows «skipped» with the reason («Gradle without lockfile: gradle dependencies --write-locks» or «no dependency manifest»), so a Gradle repo no longer reads as clean. Java manifests osv-scanner reads are now detected: `pom.xml`, `buildscript-gradle.lockfile`, `gradle/verification-metadata.xml`, `gradle/libs.versions.toml`.
- Pipelines: the editor canvas keeps where you panned it after «Save» (it snapped to the left edge) and after «Undo» (it re-centred, as on first open). A pipeline opened for the first time still fits and centres.
- Structure: an arch-map request whose session never marked its last stage (a Codex run that skipped the verify marker) no longer shows «running · <stage>» forever; the gate's result written after the run's last stage sign closes it as «Done».
- Structure: the «Run security check» recipient picker lists Codex sessions too (it showed Claude sessions only, so a repo with only a Codex session offered just the Sidereus session). A Codex recipient gets the stages with `[pl:]` shell markers, run back to back in one turn, and the same next-turn note as arch-map requests; «Request fix» stays Claude-only.
- Codex pipeline runs: a Codex session running a pipeline whose file lives in another project (an arch-map request from Sidereus) now gets its run record, so the next-stage hand-off reaches it after each stage and it no longer ends its turn between stages; Codex run requests also say to run all stages back to back in one turn. The hook's owner lookup failed silently when `CLAUDE_CONFIG_DIR` was unset, as it always is for Codex. Structure: a request to a session without a run record shows «Done» once the repo's result is newer than the request, instead of staying «Sent», and an older result no longer ends a run that is still drawing.
- Structure: the «Stop» button on a running pipeline request is drawn in the error colour so it stands out on the status line.
- Status bar: the primary account's 5h and 7d «used» (and the «left ≈» history behind them) count only that account's sessions. When accounts share one projects folder (a symlinked `projects/`), every account's sessions were summed, so the 7d figure ran far ahead of the 5h one.
- Mailbox: a Codex session no longer shows as «not logged in» when its launcher id (`<folder>-codex`) has a reader — Sidereus hooks connected, or a read cursor for a rollout-only row — and no other live Codex session shares that id; viewer DMs, run requests and room invites reach it. Folder guesses stay refused, and the check fails closed until the first session poll.
- Status bar: with a main account chosen, the Claude 5h and 7d segments show that account's own «used ≈» tokens (counted from its own sessions, hourly, so approximate) instead of no token figure at all; without a main account nothing changes.
- Pipelines: a running pipeline shows in the «Pipelines» tab as soon as the Timeline shows it, instead of 10–20 s later (the tab waited for subagent labels, refreshed every 20 s).
- `sidereus stop --port N` / `status --port N`: a background service on another port no longer claims the port — `stop` used to print «Managed by a service» and exit 0 while a `--demo` on 18799 kept running. `stop` now takes `--port`, refuses only when the service serves that port, and points at Ctrl-C / the other data dir for a viewer it did not start; `status` shows the service's port (Refs #11).
- Codex: a session whose hooks are not approved yet now appears in the session list when its rollout changed in the last 10 minutes, marked «Hooks not connected» (folder and model, state unknown); the hook row replaces it once events arrive (Refs #6).
- Codex: a second Codex session no longer disappears from the list (every Codex TUI runs its hooks under one shared `codex app-server`, so two sessions reported the same pid and were merged as a resume); the session row's «Terminal» button now finds the Codex tab by its folder and brings it forward, and the copied command is `codex resume <sid>` instead of `claude --resume`. Measured on Codex 0.163.0: list, state, turn-end mail and `[pl:]` stage marks work through the hooks.
- Codex: `hooks/invite_notice.py` and `hooks/pipelines_brief.py` take `--platform codex` for `SessionStart` notices that name the Codex parts (mail at turn end via the `Stop` hook under the `<folder>-codex` id, stages run in order with `[pl:]` shell markers) instead of `mailbox_wake` and the Agent tool; without the flag the output is unchanged (Refs #7).
- Quota: a non-primary «Main account» had no «left ≈» token estimate; until it has history it gets a low-accuracy estimate from its own tokens in this window, shown per account in the status-bar layer («≈ N left» under the 5h/7d %).

## [0.4.0] - 2026-10-18

### Added

- Structure: «Run security check» in the security window relays a `security-checks` run request to a logged-in session of the project (preview + confirm), or shows the terminal command (`python3` / Windows `py`) to copy when there is none; the window refreshes when the new scan lands.
- `setup-claude --write` shows the `claude mcp add` command and a `settings.json` diff, asks, then backs up, merges the hooks idempotently (none when the plugin is installed) and registers the MCP server; `--yes` for scripts.
- CI: a required `windows-latest` job (Python 3.9 and 3.12) runs the same gates and unit tests plus a `start --demo` smoke test.
- Docs: [REVIEW-PIPELINES](docs/REVIEW-PIPELINES.md) summarises what Anthropic, OpenAI, Google, Meta, Cursor and GitHub published on AI code review, maps it to pipeline fields, and ships review templates for Claude Code, Codex CLI and Gemini CLI (`docs/examples/pipelines/`; Codex and Gemini untested).

### Changed

- Plugin version is 0.3.2 (was 0.1.0 since the first release): Claude Code caches plugins per version, so plugin fixes never reached installed copies on update.
- Security checks: osv-scanner and npm audit findings also list their CVE ids (up to 3) next to the GHSA rule in the issues window and the report; finding keys and triage history are unchanged.
- Pipelines: sidereus-change review is split into «Review-find» (two opus reviewers, one lens each, evidence required) and «Review-confirm» (a verifier that disproves each finding and blocks only on a confirmed Important from the diff), with a shared `.claude/review-guide.md`; the reviewer's UI-string rule now matches English-source + `I18N.ko`. Find/verify split after [Solving code review at Anthropic](https://claude.dev/blog/solving-code-review-at-anthropic/).
- Timeline: the «Changes» chip counts uncommitted changes by default (was everything since the default branch); Settings › Timeline «Changes baseline» picks Uncommitted · Unpushed · Since session start · Since the default branch · Auto, and the tooltip names the baseline; the diff window's «Uncommitted» tab now shows only uncommitted changes (no fallback to unpushed commits).
- UI names: one concept, one name in English, Korean and the internal id — Pipelines «Tooling» is «Harness»; the attention list is «Attention» everywhere; the Korean labels of «Insights» and «Preferences» match their English names; «Stuck» no longer shares its Korean word with «Paused»; the canvas fail state reads «Failed»; «No subagents» reads «Subagents off».
- UI names, second pass: the bell panel is «Alerts» everywhere (tooltip «Alerts — done · failed»); the work-log popup is «Work log» (was «Activity», «work popup»); the Korean for «Mailbox watch» no longer shares its word with «Monitors»; the Korean for «Stuck» and the saver table's «Level» no longer reuse the words of «Blocked» and pipeline «Stage»; the workflow agent table's fail state reads «Failed»; the Korean README names the History tab as the UI does.
- Pipelines: the project button shows only the name and the live dot; the pipeline file count moved to the tooltip and the picker rows.
- Pipelines: the header actions read «Run», a divider, then «Undo» · «Save» · «Delete» (file operations grouped, Delete last).
- Structure: the project picker is the same search combobox as Pipelines instead of a chip row (session count in the tooltip and picker rows).
- Branches: the repository picker is the same search combobox as Pipelines and Structure instead of a chip row (full path in the tooltip).
- Timeline: the account picker is a select box like the other toolbar selects instead of a pill.
- History: the project filter is the same search combobox as Pipelines, Structure and Branches in the toolbar instead of a chip row (single select, «All» first, session count per row).
- Timeline: «Running only» is a «Rows» select («All rows» / «Running only») like Range instead of a toggle chip.
- Timeline: the session picker beside «Changes» is the same search combobox as Pipelines, Structure and Branches instead of a native select (project · sid · state per row, «Auto (latest active)» first).
- Structure: opening a module's focus view centres the focused module horizontally once; later clicks, polls and repaints of that view keep the scroll.
- Docs: ARCHITECTURE opens with where to change things; setup pages, CONTRIBUTING, README, HOOKS and MCP give the Windows form of each command (`py` next to `/usr/bin/python3`, `sidereus.cmd`, `schtasks` for the logon task, `%USERPROFILE%` paths) and list what needs Git Bash or WSL; the Windows setup page follows a real Windows 11 run; AGENTS.md holds project rules only.

### Fixed

- Structure: the first view centres the map horizontally again (0.3.0 anchored it at the top-left); a tall map still keeps the Entry band visible under the toolbar.
- Structure: coming back from another tab puts the architecture map (overview or focus view) back at the scroll it was left at instead of the top-left.
- Structure: relayed arch-map and security-check requests name both the `python3` and the Windows `py` gate commands (was `/usr/bin/python3` only, which does not exist on Windows).
- Quota history: a missing `quota-log.jsonl` on a fresh install is empty history instead of a `FileNotFoundError` repeated in the warning bar every minute.
- Windows: the `invite_notice` and `room_auto` hooks looped forever walking up from the project folder (a drive root `C:\` is its own parent and never equals `/`), so every prompt waited for the 10 s hook timeout.
- Plugin (Windows): hooks run through `hooks/pyrun.sh`, which finds a real Python 3.9+ (`py -3`, then `python3`, then `python`; a Microsoft Store alias under `WindowsApps` is never run) and caches the exe per PATH, so a hook starts one Python instead of up to three (UserPromptSubmit overran its 10 s timeout); `SIDEREUS_PYTHON` overrides it and also sets the plugin MCP server's command (`${SIDEREUS_PYTHON:-python3}`; `python3` alone hit the Store stub, exit 49); macOS/Linux still exec `python3`.
- Windows: the MCP server, `sidereus` CLI, viewer banner, `mailbox_config.py`, `scripts/room_log.py` and `scripts/deps_audit.py` write UTF-8 stdout (a cp949 pipe could not encode «—», so `tools/list` and `setup-claude` crashed).
- Windows: every text-mode file open in the product and tests names `encoding="utf-8"` (the cp1252 default broke reads of UTF-8 files; guarded by `tests/test_open_encoding.py`), and a test module that fails to import is reported by name instead of aborting its whole parallel group.
- Windows CI: checkouts keep LF (`.gitattributes` `* text=auto eol=lf`, images binary); tests remove temp git repos with read-only objects (`tests/_fs.py`), skip POSIX-only checks (permission bits, FIFOs, `pwd`/`resource`, the shell launcher and `check.sh`) and compare paths with the OS separator.
- Windows: `C:\…` edit paths now count for file owners, conflicts, review and the git rail (were dropped as non-absolute); session repos, project names and hook script names parse `\` paths; the git rail reads files without `O_NOFOLLOW`; Structure dates no longer use `%-m`; pre-1970 cut-offs and near-epoch room-log times no longer raise Errno 22; `scripts/evidence_rec.py` imports without `fcntl` (no evidence row, like the hook).
- Windows: hooks read and write UTF-8 on stdin/stdout (Korean block reasons came out empty on a cp1252 pipe); subagent, workflow-name, mailbox-watch, Structure pairing and pipeline-owner path checks accept `\`, mixed separators and any case; the transcript path guard refuses a drive root (`D:\`) like `/`; a runs.json project with `..` is refused on either separator; hook commands keep `\` and drop quotes inside a token; `cd /d C:\x` and 8.3 names (`RUNNER~1`) parse; Orbit reads its registry (Windows mode bits are not ACLs) and writes `~/...` paths; the pipeline-owner match no longer raises on a `C:\Users\…` home (it was read as a regex escape, so a session that only `cd ~/x` recorded no run). `sidereus start` no longer calls a free port «busy» (a closed localhost port times out instead of refusing on Windows, so the server was never spawned), and `status` prints the config path with one separator style.

## [0.3.0] - 2026-10-17

### Added

- Settings › «Diagnostics» › «Security tools»: gitleaks, semgrep, bandit, osv-scanner and npm — installed or not, version, what each catches, and this OS's install command with «Copy» (clipboard only; nothing is run or installed). Same list as the new SECURITY.md table.

### Changed

- `--demo` opens on Pipelines; the real viewer still opens on Timeline unless a saved preference says otherwise.
- Chat tab count reads «N rooms + Outside rooms» when the «Outside rooms» card is shown.
- Pipelines: the pipeline picker is the same search combobox as the project picker and lists this project's pipelines only (⚠ invalid, • unsaved, dot = running).
- Pipelines: a pipeline defined in another project shows only while it runs here, as a read-only chip at the end of the header row.
- Pipelines: «Apply» always sets the mode for the selected project; the «This project only» checkbox is gone.
- Pipelines: on windows 1600px and wider the palette («Make your own» + «Stage catalog») is a 280px column left of the canvas; below that the palette caps at 360px and the stage editor takes the rest. One-line editor fields cap at 420px.
- Timeline: a toolbar chip «Changes · N files +a −d» (with a session select when 2+ sessions) opens the diff window at the same base; «⚠ n shared» counts files two sessions touched.
- Diff window: «Since session start» and «vs main / master» base buttons and an «Include untracked files» checkbox.
- Security checks: advisory lookups (npm audit, osv-scanner, semgrep registry packs, OSV.dev, endoflife.date) run by default; offline or `--offline` marks them «skipped». The OSS Scanner image pins its base by digest and applies OS security updates.
- Timeline «Window summary»: Results (commits, pipeline runs) and Evidence (gate PASS/FAIL, first failing step) by default; «More» adds Waited on you, Outliers and Cost (tokens, tokens per commit), remembered.
- Security checks: one run writes one Markdown report (`security-report-YYYYMMDD-HHMM.md` beside `security-log.jsonl`, newest 10 kept) with scanner status, findings, triage, the delta since the previous scan and — for this checkout only — the dependency and runtime audit. The `deps-audit` and `release` «Check» stages run it; `deps_audit.py` covers only what the viewer depends on by default (`--dev` adds Node, Chrome and browser drivers) and no longer checks the Claude Code CLI or plugins.

### Removed

- Timeline: the right «Changes» rail and its width grip, the per-file «edited by» chips and the conflict popover (stored prefs `sidereus.tlgit`/`tlgw`/`tlgUntr` are no longer read).
- Timeline «Window summary»: «Longest gap» and «Running now».

### Fixed

- Structure: on first open the map anchors at its top-left so the Entry band is not clipped; clicking a node never moves the scroll.
- Pipelines: the canvas height is fitted so the stage edit panel is visible without scrolling at 1440x900.
- Pipelines: the stage-name placeholder is no longer clipped, and the «Agent and model per stage» caption is separated from the title.
- Timeline: switching from another tab left the Changes panel on «Loading…» until the next poll.
- Timeline: a Timeline painted before the first poll never showed the account picker or the «Runs n» lane (until the next reload, never in Manual).
- Counts read «1 file», «1 commit», «1 prompt» instead of the plural.

## [0.2.1] - 2026-10-17

### Changed

- Pipelines tab: the canvas spans the full width at every screen size, with the stage panel and palette below it; drag the handle between them to resize (double-click resets).
- Pipelines tab header is one row: a project combobox (full name, same picker as Structure), a pipeline select, and a «+ New ▾» menu holding «+ New pipeline», «Import from another project», «Ask AI for a draft» and «Standard templates».

### Fixed

- Wide screens wrapped a pipeline into several rows even when it fit in one row at the minimum zoom.
- Demo Architecture map now draws layer bands and the minimap instead of «No layers — redraw the diagram».
- An external module with no type goes straight into the «External» band, with no nested «External» box.
- Flow view side panel (1061px and wider): the title stays on one line with an ellipsis and the hint gets its own line, so neither is clipped.
- A pipeline stage lit by a running agent showed «0s»; it now counts from the agent's start.
- English «Needs you» rows for a blocked session name the tool waiting for approval.
- Architecture map: a module whose file list came back empty threw an error and stayed on «Loading files…».
- Architecture map: picking a flow no longer grows the top bar and pushes the map down at 900 and 1100px; cut-off text shows in full on hover.
- Demo Pipelines palette lists the stage catalog, and demo module details list their files; README pipeline screenshots retaken.

## [0.2.0] - 2026-10-16

### Added

- `templates/oss-scanner/`: threat model, `project.yaml` and Dockerfile in Anthropic OSS Scanner's format; Sidereus's own copy in `.oss-scanner/`.
- security-checks: a threat-model review stage, and a per-repo findings log (open / resolved / false positive) opened from the Architecture map's «Security N» button, with the time since the last check.

### Changed

- Default tab order is now Timeline, Pipelines, Structure, Branches, Tokens, History, Insights, Chat. A saved custom order still wins.

### Removed

- Project lint checks (`project-checks` pipeline, lint runner, Quality tab, «Checks n · errors · warnings» badge, «Run project checks» button). Security checks stay; the Architecture map's «Security N» button opens the issues window directly.

### Security

- macOS: the work-popup APIs (`/api/session/work`, `/api/agent/work`, `/api/ext/work`) refuse clients whose loopback connection is not owned by the viewer's OS user (checked with `lsof`, fail-closed).
- `/api/ui-prefs.js` (holds local paths) is served only to same-origin requests; a missing or cross-site `Sec-Fetch-Site` gets 403.
- Work popup: text is redacted before it is truncated, so a secret straddling a length cap no longer leaks partly.

### Fixed

- Attention: a permission prompt opened mid-message (several tool calls in one turn, or followed by a question) now shows as blocked; it was dropped as stale.
- Pipelines: a stage with a live tagged agent now lights as running even when the run record has no entry for it yet (it showed every stage waiting).
- Security checks: gitleaks findings in gitignored paths are dropped; ignored local state filled the item cap and hid real findings.
- CI: `AGENTS.md` no longer trips the no-Hangul docs test.
- `scripts/readme_shots.mjs` waits for the Pipelines tab before clicking it.
- `scripts/screen_check.mjs` masks one-character Korean weekday labels, so the Korean screens no longer fail on some days.

## [0.1.0] - 2026-10-16

### Added
- Structure › Source: a Markdown preview shows repo-relative images (png, jpg, gif, webp, svg up to 5 MB) inline through `/api/structure/img`, which applies the same root and path checks as the file view; remote, absolute, out-of-repo and secret paths stay as grey alt text.
- Attention: «agent completions unread» rows get a «Seen» button that marks those completion cards read (same store as the bell); opening that session does too, so the row no longer comes back on the next poll.
- Structure › Architecture: feature/app-style maps draw 4 location bands (Entry · Client · Server · Stores) with a hover tip each; entry modules sit in left-aligned rows by kind (HTTP · Hook · Job …), each way in drawn once as a hexagon (a flow entry and its entry module no longer show as hexagon → box), and clicking it selects the module. Cross-band edges enter nodes from the top or bottom.
- Structure › Architecture: corner minimap — the whole map scaled down in the bottom-right corner; its viewport rect follows scroll, click or drag moves the map, a lit flow is mirrored, and the show/hide toggle is remembered.
- Accounts: with 2+ Claude accounts, Retro gets an «All accounts / <account>» picker above the six OTel cards (tool ranking, time spent, cache rewrites, hours, models, hook cost); incoming OTel records are now also aggregated per account (from the session id only — no email, uuid, config path or session ids stored). Records from before collection started have no account and count under All only («Records before <date> have no account»). Failure, weekly and commit cards stay All; picking never changes the main account.
- Accounts: with 2+ Claude accounts, History and Tokens «Period totals» each get their own «All accounts / <account>» picker — History keeps only that account's rows (day headers recompute, «In other accounts: N»), Period totals recompute from that account's usage. Today's bar, donut, burn and live figures stay all accounts; picking never changes the main account.
- Accounts: with 2+ Claude accounts, Sessions and Timeline each get an «All accounts / <account>» picker (per view, independent; replaces the «Only main account» toggle); the status-bar account layer gets «Show in bar» to show another account's 5h/7d in the bar. Picking never changes the main account.
- Structure › Architecture: hovering a «Connections» row lights its edge and both modules on the map (the rest dims); an edge that is a step of a multi-step flow lights that flow. Clicking pins it (same row or empty space clears). The view never moves; an edge outside the visible map shows an «Off screen» marker on that side.
- Tokens › Usage: «Daily» table under the trend chart — one row per day of the selected range (newest first) with tokens, cost and the top 2 projects; follows the 7/30-day switch in a fixed-height box so the content below does not move.
- `room-minutes` skill + `scripts/room_log.py`: appends a dated Decisions / Open questions section for one mailbox room to `docs/decisions/<room>.md`, each line citing its message time and sender; reruns read only messages after the last section.
- Status-bar layer: clicking the 5h/7d bar shows each signed-in account's 5h/7d left and reset (main marked) and open sessions (working / idle); «Quota details» opens the full quota window.
- Status-bar layer: click another account's row to make it the main account (same setting as Preferences); names, % left and failure kinds are coloured.
- New mark: the Moon as Galileo drew it in *Sidereus Nuncius*. The favicon is his first-quarter plate; the sidebar mark shows today's phase (rough terminator, maria, a lit peak, earthshine at new moon) with phase, age and % lit on hover, and still dims with a red edge when the viewer is offline. Replaces the orbiting Jupiter mark.
- Several Claude Code accounts at once: sessions from every config root (`~/.claude`, `~/.claude-*`, `claude_roots`) with a label chip and a resume command that sets `CLAUDE_CONFIG_DIR`; limits and settings stay on the primary account. See docs/CONFIG.md.
- Shown name is now Sidereus (also transliterated in the Korean UI), with a new mark and favicon (the Moon, see above). Identifiers followed in a later rename (see «Changed»).
- SECURITY.md (+ .ko, repo root): what Sidereus never does, what a security review may ask about, and the switch for each; new `quota_lookup` (no keychain read, no quota call) and `keep_awake` config keys.
- Settings «Preferences»: saver hook folder, auto-compact history, viewer name/default room, relation node cap and terminal app (server, `config.local.json` via `/api/prefs`, apply after restart; env-set keys read-only), plus chat thread tiers, start tab, tab order/hide and KPI card order/hide (browser). Empty config and storage keep today's screens.
- Package cycle warnings list each hop with the class link behind it and the count of further links (popup and DM body).
- Selections survive a refresh: chat place, filter/thread and grouping, token range, structure project and per-repo relation scope (validated; a room or project that is gone falls back to the default).
- Local web viewer for Claude Code sessions (single entry `chat_server.py`, `http://127.0.0.1:8799`), standard library only.
- Tabs: Timeline (with replay and hover card), Chat (mailbox bus), Tokens, Structure (code treemap, source/test pairs, Go scanning), Branches, History, Retro (30-day failures and activity).
- Activity strip, four KPI cards (5-hour and 7-day quota, session states and context %, failures in the last hour) and a pinnable sessions drawer.
- «Needs me» attention ranking; failure alert cards with one action line each, batch read, auto-expire and trim.
- Branches tab: folder tree, commit graph, commits linked to their session with cost, worktree cards (quota share, uncommitted files and their owners, ahead/behind), «conflict risk» alert, remote fetch freshness.
- Work popup can send a mailbox DM to a session (`/api/dm`), with watch state and ack/reply status.
- Mailbox Stop hook `hooks/mailbox_stop.py`: unread mail notice at the end of a turn.
- Sidereus MCP server `mcp/sidereus_mcp.py`: read-only `sidereus_quota`, `sidereus_peers`, `sidereus_file_peers`, `sidereus_attention`.
- OTel log collector built in; by-source counts persist across restarts with a transcript comparison.
- Quota attribution, keyboard navigation, own Sidereus palette, background tones including white.
- Unit tests (`tests/`), golden tests for split functions, and a snapshot tool for refactor proofs.
- `THIRD_PARTY_NOTICES.md`, non-affiliation note, neutral CX/GK glyphs.
- Timeline «Changes» rail: diff vs a selectable base (auto → remote/last commit, or head/start/remote), session and repo pickers, per-file owner chip (agent task or session, edit count) and a red «Conflict» chip for concurrent edits, click-through to the work popup or a peer list.
- Optional OS notification (Settings, off by default): desktop alert only on transitions into blocked/ask/abort/conflict, metadata only (project, reason, minutes), suppressed while the tab is focused.
- Tokens tab «Top 5 costly runs» (today / 7 days): priciest subagent runs by tokens, with task, type, project, duration and share; click opens the work popup.
- KPI headroom uncertainty (`±N%`): 5-hour and 7-day cards show a spread band while the estimate is still sharpening.
- `/api/hookstate`: lightweight quota-only endpoint for the saver hook's poll (subset of `/api/state`).
- Structure tab: code select (Source / All / Tests) and a color select, both at the top of the tab; the gray «+N more» area list gains fixed columns (color swatch, function, path, lines, edit count, last change, growth since first seen, first seen).
- Timeline «Changes» rail is resizable (drag the divider, double-click to reset) and clicking a rail commit row opens its diff.
- Attention ranking: below-threshold sessions (done/background-finished-only signals) collapse into a «N below threshold» row that expands on click.
- Timeline sleep bands: `DarkWake`-split sleep intervals with no activity in between are joined into one gap instead of shown as repeated short wakes.
- Structure relations view: drag individual boxes and cards (a card stays inside its box, which grows), background drag pans, lines re-route on drop; positions saved per repo and scope with a reset-layout button.
- Icons on the header tabs (hidden at ≤1200px) and on the Settings categories.
- Structure relations warnings (toolbar «Warnings N»; removed later with the static relations view): import and Spring injection cycles, duplicate MyBatis mapper namespaces (high); package cycles and ambiguous injection (medium); layer reversals and the same JVM class name in several packages (low). In-function Python imports are not counted; warning nodes are kept past the node cap; clicking a row shows only its nodes.
- Warning relay: «DM» per warning or a bundled DM per kind (numbered, capped at the DM limit) to any mailbox session — this project's sessions first, each with its live state. Preview and explicit «Send» (no auto-send); a reply from the recipient marks it replied and re-checks the graph, and warnings gone after that are listed as resolved.

### Changed
- Structure › Architecture: every band and entry row is centred on one shared vertical axis (a focused module sits on that axis too); all modules served by an entry share the first row of the Server band.
- Structure › Architecture: entry rows are centred in the Entry band; modules served directly by an entry (e.g. security/auth) sit in the first row of their band, and calls from other modules into them are drawn as dashed «uses» edges (legend item added) instead of solid calls.
- Structure › Architecture: «map» is now «diagram» across the view, tour, guide and docs; the request button reads «Generate diagram» (none yet), «Update diagram» (older than the code) or «Redraw» (at HEAD) — same run, same confirm.
- Timeline › «Changes» rail: repo chips read «main repo · branch» (a worktree shows its main repo name); a repo ahead of its upstream lists the unpushed commits' files and is no longer folded into «+N clean».
- arch-map: a flow now covers every handler of its entry's module, up to 40 steps (was 20).
- Structure › Architecture: arch-map draws one flow per entry point (cap raised from 8 to 40); the entry band wraps at 8 entries per row (8 or fewer render unchanged).
- Structure › Architecture: arch-map edge kinds are defined language-neutral (precedence call > di > import).
- Structure › Top issues: «Request fix» asks the recipient to re-run arch-map for the repo once the fix is committed.
- Structure › Architecture: «Other» connections become «Not on a traced flow · N · all verified» (or «· M unverified»), split into «Wiring» (import/config/di) and «Calls» sub-groups with counts, both opened by «Expand all»; every edge whose from→to pair is a flow step is credited to that flow instead of staying in Other.
- Structure › Architecture: «Connections» is a flow tree — one node per flow (module and step counts) with its ordered steps, plus «Other connections (not in a flow · #)»; default collapsed with Expand all / Collapse all. Hovering a flow lights the whole flow, a step lights its edge and both modules; clicking pins (same item or empty map clears) and a pinned step shows its evidence. The view never moves.
- Header KPI strip removed; 5-hour and 7-day quota show in the status bar only, and tab content starts right under the top bar.
- Code name renamed to Sidereus everywhere (package `sidereus/`, `python3 -m sidereus`, `sidereus.cmd`, MCP server `sidereus` with `sidereus_*` tools, launchd labels `io.sidereus.*`, scheduled task `Sidereus`, `SIDEREUS_*` env vars, `X-Sidereus-*` headers, agent/skill/pipeline names). The old names are no longer recognised — no fallback. Migrate:
  - Rename every old-prefix env var to `SIDEREUS_*` (e.g. `SIDEREUS_PORT`).
  - MCP: `claude mcp remove` the old server and add `sidereus` (the line `python3 -m sidereus setup-claude` prints), or reinstall the plugin. Update permission allow-lists to `mcp__sidereus__*`.
  - Service: remove the old launchd agent / scheduled task, then re-run `python3 -m sidereus start --install-service`.
- Claude Code plugin and marketplace renamed to `sidereus`. Reinstall: uninstall the old plugin (and `folder-accounts` if installed), remove its marketplace, `/plugin marketplace add <clone>`, `/plugin install sidereus@sidereus`.
- Optional accounts plugin renamed `folder-accounts` → Orbit (`plugins/orbit/`, install `orbit@sidereus`; command `orbit`, `claude-account` kept as an alias). Registry `~/.claude-accounts` and the rc block are unchanged. Reinstall: `/plugin uninstall folder-accounts@sidereus`, `/plugin install orbit@sidereus`.
- Main views moved into a collapsible left sidebar (56px icons, 208px open; pushes the page at ≥1200px, overlays below; Cmd/Ctrl+B; remembered; folded icons show a quick name tooltip with the shortcut digit). It also holds the logo, the «Attention» list of sessions that need you, and alerts/settings. The top bar is one 48px row: view title, running sessions, «needs me» chips, sessions. The header width-squeeze steps are gone.
- Structure tab is now «Architecture» (agent-drawn, verified module map + process flows) and «Size» (treemap). The static relations view, its flow/path views, framework rules, warnings, `/api/structure/rel|path|calls`, the `rel_max_nodes` pref and `scripts/rel_route_check.mjs`/`stack_check.py` are removed. Language plug-in keys are now `exts`, `lang`, `scan`, `test`, `test_dirs`, `skip`, `gen`. A stored relations mode opens «Architecture».
- Page moved into `web/` (byte-identical assembly); JS/CSS split into feature files, Python into the `sidereus/` package.
- Route tables for GET/POST; large Python and JS functions split into named helpers; shared UI kit (overflow fold, popover, hover card).
- Token widgets moved to the Tokens tab and the 5-hour card; per-tab toolbar below the KPI cards.
- Failure tab replaced by actionable alert cards.

- Structure relations regions are business packages (`com/<co>/<app>/<pkg>`, `features/<pkg>`), the same key in every lane; the lane comes from the deepest layer folder (`domain/` = data); the middle lane is Logic. Caps: 16 per lane, 48 total; small packages fold into linked or sibling packages before «Other».
- 5-hour headroom pairs the official % with tokens up to the moment it was logged, and subtracts tokens spent since (it no longer rises between polls).
- Relations view is not rebuilt by polls that change nothing it shows (no periodic twitch).

### Fixed
- Pipeline: the «Workflow» group label and the workflow head note are translated.
- Config: a `claude_roots` list in `config.local.json` is kept on load (it was dropped as an unknown key, so extra account roots never applied).
- Chat: the room «← Rooms» back button uses the shared 28px nav height and 13px label (was 24px / 12px, too small a target).
- Sessions: a running background shell (e.g. a dev server) stays listed under its session past 2 hours; it closes on its completion notice, an error, session end or ✕.
- Pipelines: the tab fills the window height and the run panels sit at the bottom (about 22px padding) at every width; narrow widths use a canvas-over-panes grid, and in-place size changes refit it.
- Timeline › Changes: a session's repo list keeps repos it touched early in a long transcript (the whole transcript is scanned once, then only appended lines), instead of only those in the last 1.5MB.
- Architecture gate: a step calling a Java record accessor or a Lombok-generated getter/setter now counts as defined when the call site names the type (it was dropped as «nodef»).
- Left rail: with the rail collapsed, the Attention badge opens a temporary peek that closes on an outside click; only the rail toggle (or Cmd/Ctrl+B) saves the collapsed setting.
- Structure › Architecture: the minimap reads at small scale (1px strokes that do not scale, no arrowheads, a small corner toggle), and a map opens centred once per map without ever re-centring on repaint or click.
- Pipeline: a new request whose first tagged stage comes after the first stage (e.g. main did Requirements itself) now opens its own run instead of continuing the finished run as a second pass with its old done marks.

### Security
- `/api/*` GET requests with `Sec-Fetch-Site: cross-site` are refused (403), alongside the existing cross-origin POST check.
- Work popup masks secrets (API keys, Bearer/JWT, AWS/GitHub/Slack tokens, private keys, `*_KEY=` values) before sending.
- Git runs with fsmonitor and hooks disabled; diffs use `--no-ext-diff --no-textconv` and are read with a size cap.
- User paths reach git as literal pathspecs; paths starting with `:` or containing NUL are refused (a glob pathspec could read the whole repo).
- Structure/source roots exclude `/` and the home directory.
- Request timeout 30s; `/api/*` GET also refuses `Sec-Fetch-Site: same-site`; data files are created 0600 and `backup.sh` runs with umask 077; two more HTML-escape fixes.
- POST handlers type-check untrusted JSON and answer 400 instead of closing without a response.
- Git calls ignore the worktree `.gitattributes` (`--attr-source` on git ≥ 2.40), so a cloned repo's filter drivers no longer run during status/diff; LFS/eol attributes are ignored for display.

### Privacy (metadata only)
- Sessions drawer and external-platform rows no longer carry task/reply text or tool input (Agent task descriptions only).
- Failure samples, wreckage and Retro tool errors are grouped by a fixed label + tool name — no raw text or arguments.
- Ask/abort cards are created with an empty body; old stored bodies are emptied on read.
- Test fixtures use placeholder session ids and paths.

### UI
- A hidden tab polls every 30s instead of 2.5s (OS notifications still fire); becoming visible polls at once.
- Poll repaints skip unchanged content, so hover and focus survive; idle timeline mutations per 10s 629 → 464, attribute mutations ~390 → ~70–115.
- Structure: functions beyond the per-area cap are drawn as one grey cell per file; clicking expands the area filtered to that file.
- One name per concept («Subagent», «Background tasks»); token and failure numbers state their scope with tooltips; the day/week/month toggle moved into the period totals title.
- Four actions that failed silently (mark all read, history all, health/background dismiss) now show the error toast.
- Structure relations: cards centred in their box both ways; «Layer N» is a chip on the band separator; merged lines leave boxes straight and same-row pairs are one straight line; «Fit to view» fits the canvas and the view can no longer drift off-screen; the selection card opens below the clicked node; Esc closes it.
- Settings modal keeps a fixed height across categories; saver mode rows aligned; the target time is a plain HH:MM field.
- Timeline axis labels never overlap (step from measured width); bar labels ≥ 4.5:1 contrast on every hue; name column scales with the window.
- Tokens trend: round end dots, 1/2/5 y ticks, hover tooltip; top-5 rows align.
- Sessions drawer rows stay on one line; less important chips hide first when narrow. Branch commit rows are aligned columns.
- Popovers share one radius/shadow/border; the bell panel no longer touches the status bar; treemap labels are shortened by measured fit instead of cut.
- Light-theme contrast fixes (chat bold text, blocked todo, commit author, KPI legend).
- Segmented controls share one look and height (24px) and titles one scale; percentages, money and counts use one format everywhere (whole %, «<1%», uppercase K).
- KPI cards stay on one row at 1081–1200px, so the feed is no longer pushed down.
- Structure relations: a dropped box moves to the nearest free spot and is drawn on top, so boxes never overlap; narrow card text is centred.
- Diff window: prose files (Markdown, text, logs) colour only headings and code; lines wrap at word boundaries.
- More contrast fixes (work-popup send and token labels, Cmd+K paths, quick-reply buttons, rule-kind swatches).

### Fixed
- Branches: a repository listed in the picker is no longer refused («This repository is not in the list», 403) when a later session in the same folder did not carry it — the server gate now reads every session row, like the picker.
- Structure: folding a flow or «Other» (caret or «Collapse all») unpins a pinned step or Other row that the fold hides, so the map no longer stays lit with no visible row; a pinned flow node stays lit.
- Pipeline guard: a loop-back clears skip declarations from the loop-back stage on, so a stage skipped in round 1 must be run or declared skipped again in later rounds; «skip» marks on screen are unchanged.
- Pipeline guard: declaring a skip of a loop-back's return stage no longer reports stages that already ran (e.g. verify, review) as skipped; the jump check starts at the declared return stage.
- Pipelines: each request is its own run — a new first-stage tag closes the previous run, so a new run shows only its own progress; declared onFail loop-backs stay in one run, and earlier runs are reachable from «Run k/N ▾» (time + label).
- Structure › Main issues and Pipeline «Ask AI»: a sent improvement request shows a green «✓ Requested → session · time» line plus a toast (failures show a red line); resending the same request takes a second click on «Sent · send again».
- Tokens: a project keeps one name across the 7-day and 30-day views (one view no longer shows the folder slug while the other shows the project name).
- 5h headroom no longer saw-tooths while the official % sits still: tokens pair with the first log of the current %.
- Subagent completion detection for attachment notifications; live detection of resumed subagents.
- Forked-away session pid no longer shows the old transcript as live.
- Concurrency races (background dismiss, card read, mark-all, atomic saves, window save, wreck map); `saver_set` read-merge-write lock; quota attribution re-seeded on a new 5-hour cycle.
- Failure scan no longer drops the first new line on each tick (failures tab, alert cards, wreckage and «Failures (1h)» were undercounted).
- A background-task completion notice caught mid-write no longer leaves an agent «Running» forever.
- One failing optional part of the state (quota, usage, health, attention, …) is sent empty with a warning instead of freezing the screen; the branch warm-up thread survives a failing tick.
- Live probe: «nothing running» now flags a pending Bash approval; failed or skipped probes stay unknown.
- Per-transcript and failure-scan bookkeeping for gone or 30-day-old files is pruned (was kept forever).
- 20 duplicate English UI strings resolved (a later file overrode the earlier translation everywhere).
- A 403/500 from the server lands in the normal error path instead of a JSON parse error.
- History rows crossing midnight carry a previous-day / next-day mark («23:00~01:00» from the day before, «22:00~01:00» into the next day) instead of «00:00~00:00»; newest start first.
- The new-version bar no longer covers the header tabs.
- 5-hour and 7-day percentages now agree across the KPI cards, status bar and saver badge.
- Invalid `font: Npx inherit` CSS was dropped by browsers (buttons fell back to 13.33px); font sizes now apply as intended.
- The token trend tooltip no longer shows as an empty pill.

### Internals
- One shared bounded cache replaces 16 hand-written caches; shared timestamp formats; pure burndown math split out; attention ranking and branch graph split into collect and rank steps — outputs verified identical.
- UI kit: one skip-if-unchanged repaint helper, JSON fetch helpers, a soft-error counter (one console warning per tag), one `HH:MM` formatter.
- Tests: 47 for POST routes and live probe, duplicate-i18n-key check, metadata-only check.

### Docs and install
- Fresh install verified with an empty HOME: first start creates an empty 0600 bus file and a missing `~/.claude/projects` is not a warning (0 warnings).
- Docs say what ships here (bus, `watch.sh`, Stop hook) vs the external mailbox MCP tools; the saver hook is optional; `launchctl bootstrap/bootout` throughout; the OTel endpoint must match `--port`.
- launchd labels default to neutral `io.sidereus.*`, overridable per install (`launchd_labels` in `config.local.json`).
- Optional hook `hooks/file_peers_notice.py` (PreToolUse, Edit/Write): one metadata line when another live session recently edited the file; never blocks. Enable steps in GETTING-STARTED.

[Unreleased]: https://github.com/bugsterran/sidereus/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/bugsterran/sidereus/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/bugsterran/sidereus/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/bugsterran/sidereus/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/bugsterran/sidereus/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/bugsterran/sidereus/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/bugsterran/sidereus/releases/tag/v0.1.0
