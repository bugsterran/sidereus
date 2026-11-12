# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Structure: «Export HTML › Simple» opens an older map's own overview too, marked «HEAD is N commits ahead» like «Detailed»; only a new overview request still needs the map at HEAD.
- Structure: a store module's detail in «Architecture» shows «Data path» — the entry points that write it («Written by») and read it («Read by»), worked out from the map's verified read/write edges and the flows' checked steps; a row opens that flow.
- Pipelines: each pipeline gets one verdict from its 30-day result (a pass broke, too few runs, review loop-backs rose, or healthy); the weekly report writes it right after the date, with «Next step» guides for the three warnings.
- Pipelines: «Working now» lists a session's live CLI children (pi subagents, `gemini -p`, `codex exec`) under its card, and a session running two or more at once shows «parallel ×N» there and on its sessions row.
- Sessions: a pi session logged in to Anthropic with OAuth is billed to extra usage (credits), not the plan's 5h limit; its row shows a «Credits» chip with its tokens in the current 5h window, and Attention lists «Spending credits» while it spends.

### Changed

- Timeline: each session group has a visible divider above it, and its agent rows are lightly tinted, so a session and its agents read as one block and neighbouring sessions no longer run together.

### Fixed

- Status bar: the credit line no longer disappears when extra usage is disabled or used up; it stays with «off» and the reason.
- Sessions: pi subagent child lines show their tokens instead of 0; the Sidereus pi extension now reports each child reply's token counts (run `/reload` in open pi sessions to load it).
- Attention: «Spending credits» and the «Credits» chip no longer show while extra usage is off; pi's requests then draw on the plan's 5h limit, not credits.
- Status bar: the Korean label for «Machine busy» (load above twice the CPU count) now reads as overload, with the number named as load average; the English text is unchanged.
- Tests: `bash tests/run.sh tests/test_x.py` runs that file instead of failing with «Start directory is not importable»; other arguments still go to unittest discover.

## [0.18.0] - 2026-11-12

**Highlights**

- Platforms: pi connects through «Connect» (hooks, MCP servers, a Sidereus extension), and new mail wakes an idle pi session without a model turn while it waits.
- Security checks: osv-scanner findings get a reachability verdict, and test code is left out of the code scanners by default («Include test code» scans it).
- Requests: recipient pickers (security fixes, Harness «Next step», pipeline evaluation, runs) list live sessions of every platform, not only Claude Code.

### Added

- Platforms: pi hooks and the Sidereus MCP server connect through «Connect» in Settings › «Diagnostics» (an extension plus `mcp.json`, previewed first); a pi row without hooks shows «Hooks not connected».
- Platforms: new mail wakes an idle pi session through the Sidereus pi extension (one turn with the mail metadata only, sent only while pi is idle); no model turn runs while it waits.
- Sessions: two live sessions in one folder each show a muted «n in folder» chip; its tooltip says cost and To-do are folder totals.
- Sessions: pi subagent children hang under their pi parent row with the agent name as label (re-run «Connect» for pi).
- Sessions: a running pi session whose loaded Sidereus extension is older than the current one shows an «Old extension» chip; its tooltip says to run `/reload` in pi, or to «Connect» pi in Settings › «Diagnostics» first when the installed file is old too.
- Sessions: the work-log popup shows steps and replies for pi sessions, read from the pi session file.
- Docs: a pi migration pipeline template (`docs/examples/pipelines/migrate-pi.json`, stages Inventory, Map, Convert, Verify, Report) keeps the Claude Code files as the source and gives pi symlinks or generated copies; linked from the pi section of HOOKS (untested on pi).
- Security checks: osv-scanner findings get a reachability verdict — «Unused (verified)» (collapsed, out of the counts), «Invalidated» with the hit file:line, or «Unjudged»; the builtin `osv-triage` pipeline reads the advisory preconditions of unjudged ids and appends fixed-string usage rules (source URL and date) through `scripts/osv_rules.py`.
- Security checks: test code (tests/, fixtures/, `*.test.*` and similar) is left out of the code scanners (gitleaks, semgrep, bandit) by default, so mock secrets no longer show as findings; «Include test code» scans it. Dependency and image scanners always read the full tree.

### Changed

- Sessions: when the main repo's session is in view, a linked-worktree session is one «Worktree» line inside that card (name or branch, state, age), next to the subagent lines; clicking it opens that session. With no main session in view the header row stays.
- Quota: «left ≈» on the 5h window shows a range (for example «57M-107M») when the history estimate and this window disagree by more than 1.5x between 30% and 60%; from 60%, and on the weekly window from 30%, it is one value blended toward this window.
- Structure: the diagram request («Generate diagram» / «Update diagram» / «Redraw») also draws the one-page overview, so «Simple» is ready after one request; `arch-brief` remains for redrawing only the overview, and a failed overview leaves the verified map in place.
- Requests: the recipient pickers for security check fixes, the Harness «Next step» and pipeline evaluation «Ask AI» list live sessions of every platform (before, Claude Code only), and the structure diagram, overview and pipeline run pickers, which already listed several platforms, now list every one; the Harness «Next step» lists only sessions logged in to the mailbox. Sessions from other CLIs get a run-it-yourself body with shell stage markers, and sending still needs a mailbox login.
- Pipelines: the red-check «off» hint reads «Open an AI session in this project and log in to the mailbox to request it» instead of naming Claude Code.
- Retro: the «All accounts» picker moves to the toolbar.

### Fixed

- Structure overview: two arrows no longer share one vertical line (a lane next to another arrow's attach point or a lane 1 px away), and box titles, notes and ids are cut by measured width so Hangul text stays inside the box.
- Pipelines: agent counts read «Agents N» everywhere (some places said «Agent N»).
- Structure overview: the one-page overview fits a 900 px window; long evidence file:line cells wrap and the figure no longer scrolls sideways inside its frame (an existing overview changes after «Redraw»).
- Security checks: the window title, the re-scan notice and the history no longer count osv-scanner findings marked «Unused (verified)» as open.
- Pipelines: a stage marker in a shell command counts on a later line or after `;` `&&` `||` when it is an `echo`/`printf` of the marker (pi writes them so); a marker inside a multi-line quoted string or a heredoc body is text.
- Pipelines: a builtin security run started from a session in another repo shows and is filed under that repo, instead of «pipeline file not found».
- Pipelines: a commit tagged for a run closes it when the remaining stages were declared skipped, instead of leaving the run open.
- Pipelines: a borrowed canvas shows the open run instead of another session's newer ended run.
- Timeline: finished pi subagent rows keep their agent name instead of collapsing into one «pi -p» row.
- Structure: the one-page overview («Simple») gives every arrow its own lane and moves labels to a free spot, so a busy figure no longer stacks labels on each other or on box text; lanes are ordered to cross the fewest lines and labels and keep clear of band titles; an existing overview changes after «Redraw».
- Plugin: the SessionStart hook shipped in the plugin includes the pi id prompt above (the plugin copy was stale).
- Platforms: a pi session without a `pi:<cwd>` mailbox id is asked at start whether to register `<folder>-pi`, instead of being told the derived id as if it were logged in.
- Platforms: pi «Connect» no longer reports connected while `~/.pi/agent/mcp.json` keeps its own `mailbox` entry that skips the Sidereus launcher (pi logins then never count); Diagnostics says to edit that entry by hand.
- Sessions: the branch chip shows the live git branch of the folder; a session back from an isolation worktree no longer keeps the `worktree-agent-…` name.
- Platforms: an idle pi session no longer drops out of the mailbox after a refused wake (wake cap or busy); its waiter keeps the presence alive and wakes only on newer mail (re-run «Connect» for pi).
- Accounts: a profile signed in to the primary's account is never taken as «Main account» or the in-use account.
- Sessions: a folded header-only worktree group ends with a border, so the next row no longer reads as its child.
- Sessions and Timeline: a session nests under a worktree only when its folder is inside that worktree, not when it merely touched the repo.
- Quota: «left ≈» ignores this window's average when this PC used nothing in it (only claude.ai or another device moved the %), instead of reading «< 1%».
- Platforms: an idle pi session stays listed while pi still runs in its folder, instead of dropping after 10 minutes without writes.
- Platforms: pi rows carry the mailbox id pi logs in as, so the work-popup composer and run pickers address the pi session, and a room member from pi shows the pi logo.
- Structure: in a module focus view a box with many links grows wide enough to keep its link ends 10 px apart, instead of drawing them about 2 px apart.
- Pipelines: in «Watch» the stage detail pane ends on a line boundary instead of cutting its last line in half; at its minimum height it grows to the next line.
- Platforms: a pi session whose explicit `pi:<cwd>` mailbox id is also a Claude folder's id is woken by new mail and told that id at start, instead of falling back to `<folder>-pi`.
- Rooms: when a Claude session and a pi session share a mailbox id, the member logo follows the live one.
- Layout: History rows wrap at 1100/900 instead of cutting fields; Pipelines «Working now» names stay on one line at 1100; Tokens «Top 5 costly runs» and Retro «Frequent failures» keep values next to names at 1920; the light count badge meets contrast.
- Sessions: the tool-state bar sits on the same left edge and height as the account band, instead of a second shorter bar beside it.
- Timeline: the tab dot also lights while a main session works in its own turn without subagents (sessions idle 600 s or more excluded, as in the session list); its tooltip names both counts.

## [0.17.0] - 2026-11-10

**Highlights**

- Credit mode: on a usage-billed seat the status bar and Quota details show the monthly credit (gauge, used share, exact used/limit) instead of 5h/7d windows the seat does not have.
- Platforms: pi sessions are read as a CLI adapter, with rows, tokens, Timeline activity and the work popup; pi's Claude use counts in «Who is using the 5h».
- Sessions and Timeline: linked-worktree sessions are nested under their main repo, with a fold caret and a worktree session count.

### Added

- Status bar: on a usage-billed seat (credit mode) the bar shows «Credit mode» with a monthly-limit gauge, the used share to two decimals and the exact used/limit, instead of «5h left 100%».
- Quota details: a usage-billed seat gets a «Credit mode - billed by usage» headline over the credit gauge row; the 5h/7d rows and 5h curve are hidden.
- Sessions and Timeline: sessions in a linked worktree are indented under the main repo's session (fold caret, «N worktree sessions»); a header row names the main repo when it has no session of its own.
- Sessions: a Copilot session in a repo whose `.github/copilot/settings.json` sets `disableAllHooks` shows «Hooks off in repo» instead of advice to set up hooks.
- Quota details: «Who is using the 5h» includes pi sessions that ran on Claude (provider anthropic), with the pi logo; the pi login is assumed to be the account shown.
- Platforms: pi (earendil-works/pi) sessions are read from `~/.pi/agent/sessions` — session rows, model and token usage, tool activity on the Timeline and in the work popup; metadata only, no hooks or mail wake yet.
- Status bar: on a usage-billed seat (credit mode) the credit segment shows the credit as tokens, «≈ used/limit», converted at this week's local average price; the tooltip states the rate.

### Fixed

- Platforms: a Gemini `settings.json` or `~/.codex/hooks.json` saved with a UTF-8 BOM is read normally; Gemini showed «Sidereus hooks are missing» while Connect said connected, and the hook list was empty.
- Quota details: a usage-billed seat (credit mode) no longer shows «Who is using the 5h»; that seat has no 5-hour window.
- Work popup for pi, Cursor and Copilot sessions says «Session events» and that it reads the session file, not hook events; pi shows its real last tool.
- Quota details: «Who is using the 5h» stays visible when the primary is a credit seat but the list is another account's.
- Status bar account layer: the popup sizes to its content, so a wide credit amount no longer cuts the account name to «myaccount…».
- Saver badge and status bar: a usage-billed seat no longer shows the 5h pace verdict («No throttle», goal %); a manual /saver on/off still shows.
- Sessions and Timeline: a session started in a non-git folder that works inside a linked worktree is nested under that worktree's main repo (judged from the most recently touched repo).
- Quota: the cached usage is bound to account and organization, so switching organization no longer carries the old org's 7d 100% until its reset.
- Quota and status bar: a usage reading rounded to 100% shows «< 1%» left instead of «left ~ 0».
- Credit mode: amounts in the badge, bar, tooltip, status-bar layer and Quota details use exact cents; the layer shows a dash instead of «5h/7d left 100%».
- Pipelines: the weekly report is kept per pipeline, so every pipeline gets its own report and the panel no longer shows another pipeline's.
- Pipelines and Structure: when two sessions share a folder, the repos touched by both are kept for pipeline chips and structure warm-up.
- Harness: evidence for a session working in a linked worktree of an allowed repo loads instead of failing with «unknown project».
- Windows: linked worktrees are recognised (path separator), so their evidence and diff views open.
- Sessions: folding a worktree group no longer shifts the columns; a single child reads «1 worktree session».
- Structure: arrowheads and hit areas in the module focus view are no longer drawn filled black.
- Copilot: a crafted `.github/copilot/settings.json` (symlink to a device or a FIFO) can no longer stall the poll; only a regular file is read, with a size cap.

### Changed

- Sessions: the token tooltip on external session rows uses each platform's wording (Codex, Gemini, pi); a pi session on a Claude model says it counts in «Who is using the 5h».

## [0.16.0] - 2026-11-07

**Highlights**

- Structure: clicking a module opens a detail layer over the map with an HTML focus diagram of only its connected modules, in stage order; the map keeps its scroll spot and Esc closes it.
- Pipelines: Evaluation shows token cost per run (median and last run) and each stage's share; unknown tokens read as a dash, never 0.
- Sessions: a compacting session shows «Compacting» with elapsed time and an estimated percentage; a background shell left open over 30 minutes raises «Long background» with «Ask to check».

### Added

- Structure: clicking a module opens a detail layer over the architecture map (x or Esc closes it, the map keeps its scroll spot). The detail is an HTML focus diagram: only connected modules, in stage order, layer boxes with names above, edge colours per target box, and the rows spread over the free screen height.
- Pipelines: Evaluation shows the median tokens per run, the last run's tokens and duration, and a Share column per stage; the Harness report markdown carries the same numbers.
- Trees: arrow keys in a source tree open the file they land on, and a click on a file keeps the arrow keys on the tree.
- Contributors: a pre-push hook runs the leak scan on outgoing commits.
- Sessions: a Claude Code session that is compacting shows «Compacting» with elapsed time and an estimated percentage (from this account's recent compaction times; capped at 95% until it ends). Needs the plugin's new PreCompact/PostCompact hook.
- Attention: a background shell open for more than 30 minutes raises «Long background» (merged with «Idle shells»); background rows get «Ask to check», which previews a one-line request to that session and sends it only on «Confirm — send».

### Fixed

- Evidence: a gate that Claude Code moved to the background on its own no longer records a pass before it has finished.
- Sessions: a question wrapped in markdown bold counts as a question wait; it used to show Done.
- Structure: the detail layer keeps keyboard focus inside (Tab / Shift-Tab cycle, focus returns to the close button after a repaint, Esc ignores IME composition), and the light theme's flow-edge colours have enough contrast.
- Diff window: picking a file keeps the file list's scroll position.
- Attention: «Long background» minutes use the same short unit as «Idle shells» («45m»).
- Pipelines: Watch also moves to a newly started run when nothing else is working, even if that run opens waiting on a person or before its first stage is recorded; it used to stay on the previous run.
- Structure: on a narrow module focus bar the flow select shrinks and the In/Out legend (with the fold button) wraps as one group instead of splitting across lines. At 1920 the focus bar now takes its own row (legend and zoom below); a long legend had squeezed it to about a quarter of the row.
- Pipelines: stage cards on one row line up on a shared middle line even after hand-dragging (rows group within 30 px, a dropped card snaps to the nearest row and the aligned position is saved), and their status chips sit at the same height.
- Pipelines: when the watched run ends, Watch moves to another open run even if that run is waiting on a person or idle between stages; with none open it moves as soon as one starts.
- Pipelines: Watch (the landing view) shows «Gates n/m» and «Evaluation» in its head row; they were only in Edit.
- Sessions: when `claude agents --json` exits with an error and no output, sessions are treated as unknown instead of all ended (seen off macOS).
- Timeline: the sleep lookup (`pmset`) is stopped with its whole process group on timeout instead of running on in the background.
- Structure: the flow check reads routes declared in a dict table, so those request steps no longer fail as "no route".
- Structure: the export stamp and header tooltip say "HEAD is 1 commit ahead".
- Tokens: the Day/Week/Month and Today/7 days toggles announce their state and name; empty tables show "No data" instead of a bare header.
- Status bar: a long repo name in "mostly <repo>" is cut with an ellipsis; the full name stays in the tooltip.
- History: the time column has a fixed width so the project column lines up.
- Demo: the Timeline no longer reorders when a response spans a second boundary.

### Changed

- Structure: in the overview map a module that 3 or more modules of its own band call (a hub such as an SPA shell) sits on its own row below the band, centred, so the links into it drop straight down instead of running along the row. A hub that another hub calls sits one row lower, modules in a call cycle with the hub share its row (no line climbs back up), and the band title also keeps clear of modules inside group boxes on the top row.

- Contributors: `check.sh --fast` also runs the architecture tests; bug-fix pipelines require a trap note; a commit-msg hook allows closing keywords only in a release commit.

## [0.15.0] - 2026-11-05

**Highlights**

- Busy machine: under heavy load the page keeps answering. `/api/state` no longer waits on git, `ps` or `claude agents --json`; a slow poll reads "Data delayed" instead of "Disconnected", and the status bar names the repo whose Claude session uses the most CPU and memory.
- Attention: sessions ended with `/exit`, parked into a background job or continued with `claude -c` no longer leave an older transcript looking live with a false "Asked a question"; a prompt typed mid-turn counts as your reply.
- Chat: room hashtags, room management and the invite bar are gone; manage rooms from a session with the `room` skill.

### Added

- Structure: an "Export HTML" menu in the Architecture header. "Simple" opens the current commit's `arch-brief` overview in a new tab (served with scripts blocked), or, when none exists, sends an arch-brief run request after preview and confirm. "Detailed" downloads the shown module map as one self-contained HTML file with no scripts, also for a map drawn at an older commit (the file says how many commits HEAD has moved).
- Status bar: while the machine is busy or data is delayed it shows "Machine busy · load N · mostly <repo> · CPU N% · M GB"; the tooltip lists the numbers and executable counts. Metadata only (repo name, numbers, executable names).

### Changed

- Status bar: a slow poll shows "Data delayed · Ns ago" (amber, the age keeps counting) with load in the tooltip; "Disconnected" is kept for network errors or 75 s without any reply.
- Attention: a question card held after the session went back to work reads "Awaiting answer · kept working".
- Attention: "Done" and "Seen" close the Sessions drawer when an Attention chip opened it; a pinned drawer stays open.
- Request previews: "Confirm — send" is painted as the primary action, with a visible focus ring; disabled ones still look disabled.
- OSS Scanner Dockerfiles (own copy and template): run as a non-root `scanner` user with a `HEALTHCHECK`; the user is created before the dependency fetch so caches stay readable.

### Removed

- Chat: room hashtags, the room list "Manage" mode (create, invite, hide rooms) and the sessions drawer invite bar. The Chat tab keeps the room list, reading and posting; manage rooms from a session with the `room` skill.

### Fixed

- Busy machine: `/api/state` stopped answering for 30-60 s under high load (git lookups, `ps` probes and `claude agents --json` ran on the request path behind locks); they now serve the last value and refresh in the background.
- Attention: a session ended with `/exit` no longer holds a live slot and keeps showing "Asked a question".
- Sessions: a claude parked into a background job, or `claude -c` started after `/exit`, no longer lets an older transcript in the same folder show as live.
- Attention: a prompt typed while a turn is running counts as the reply to an open question.
- Sessions: one malformed transcript line no longer empties the session list.
- Pipelines: the "Get started" checklist also shows when every pipeline file of a project is invalid.
- Attention: a question answered after a long run no longer comes back as "Question waiting" when the question was read in an earlier scan.
- Sessions: project folders with non-ASCII names and Windows drive paths map to the same transcript folder Claude Code uses.
- Sessions: a background job whose terminal host was re-parented no longer shows a second "Waiting for input" row.
- Harness: the runtime summary counts only end-of-life runtimes in "end of life · N runtimes"; a runtime on the last patch of an ended cycle is no longer "behind" (it still fails on end of life).
- Harness: gate evidence with a missing or non-numeric exit code stays unknown instead of reading as a pass.
- Quota details: "Who is using the 5h" names the account it counts.
- Insights: durations use Korean units in Korean, drop a zero part ("1h", not "1h 0m"), and fail counts use thousands separators.
- Pipelines: the "Run" side layer takes focus when it opens, keeps it when a mode, session or model select repaints, and gives it back to "Run" when closed with Esc or ✕.
- Pipelines: below 1440 px the live-run status moves under the title instead of wrapping one word per line.
- Pipelines: untagged subagent rows line up with the run group's rows.
- Keyboard: the Timeline summary "More"/"Less" toggle, the Timeline "Pipeline" label and a tour started from shortcut help keep focus; the To-do layer header is no longer an empty tab stop.
- Structure: Enter and Space activate architecture map targets, and edges are named "from → to" for screen readers.
- Tour: the "Working now" step describes the dot rail when the list is folded.
- Branch: below 1000 px the side pane stacks under the graph instead of cramming commit subjects; Work-unit buttons keep focus across the live refresh.
- Korean UI: Preferences, settings and hook-file server errors are translated; Preferences shows the broken-config note it used to hide.
- Chat: the open room's name keeps its width and the member list wraps instead of shrinking to a few pixels.
- Light theme: architecture map focus rings and Branch status chips meet contrast.
- Sessions drawer: the branch chip no longer wraps mid-name.

## [0.14.1] - 2026-11-03

### Fixed

- Pipelines: the "Get started" checklist shows even when one project has an invalid pipeline file (it was hidden as "unknown").
- Structure: edge labels in the architecture overview and focus view prefer spots clear of other edges' lines, so a label no longer reads as another edge's.
- CLI: `sidereus status`/`stop` with `MAILBOX_DIR` set elsewhere no longer treat that instance as the installed service; a service without `--port` is read with its own data folder's port.
- CLI: `sidereus redcheck --help` prints its own usage and exits 0.

## [0.14.0] - 2026-11-03

**Highlights**

- Pipelines: a "Get started" checklist on the Pipelines view, "Start with recommended setup" that writes quick-fix, change and bugfix pipelines, and "Request a red check" that asks a live session to prove its gate turns red.
- Attention: permission prompts and open questions no longer drop out while subagents run, and they clear on their own once you respond (typed prompt, picker answer or `!` command).
- Security: every POST that acts for the person (room posts, DMs, terminal focus, saver settings, dismissals, review marks) now requires the viewer page's Origin, so a local script can no longer act as you.

### Added

- Pipelines: a "Get started" checklist (Claude Code connected, Project added, First pipeline, Gate red-checked), built from existing data and gone once all are done or on "Hide".
- Pipelines: "Start with recommended setup" writes quick-fix, change and bugfix pipelines with a gate from the detected test command or a one-line input; diff preview and confirm, never overwrites, strict mode is an unticked opt-in.
- Pipelines: "Request a red check" in the evaluation panel relays a red-check request to a live session of the project after preview and confirm; `sidereus redcheck` runs the bundled runner, so red checks work in pipx and uv installs.
- Structure: zoom controls on the architecture map (- 100% + Fit); the % label follows Ctrl/Cmd+wheel zoom too.

### Changed

- Header: the "CLI hooks not connected" chip shows the platforms as logos.
- Pipelines: a running stage done by the orchestrator (no agents) shows its elapsed time on the canvas chip.
- Pipelines: the Run button's tooltip says it opens a run request that the chosen session executes; Sidereus runs nothing.
- Pipelines: "Run" opens a side layer that hangs right under its button instead of a block under the canvas; the canvas does not move.
- Pipelines: the bundled refactor, docs and release pipelines gate every stage a command can grade (file-editing stages run `check.sh --fast`, verify stages `--full`, CI stages watch their exact commit).
- Pipelines: recommended setup picks pytest only when the project configures it (pytest.ini, conftest.py, pyproject, setup.cfg or tox.ini); a `tests/` folder alone leaves the gate for you to fill.

### Fixed

- Attention: an unanswered "Question waiting" card no longer drops when long unattended work pushes the question out of the parsed transcript tail; only a real reply after it clears the card.
- Pipelines: a skipped red check shows its reason on hover and offers the red-check command.
- Pipelines: run requests composed by Sidereus (Pipelines "Run", architecture map, security checks) are English; stage titles stay as written.
- Structure: in the architecture map focus view the zoom bar has its own row and no longer covers the diagram at 1100 and 900.
- Sessions: a background job resumed with `claude -r <id>` or from a path with spaces retires its pre-/clear row.
- Pipelines: a red check result is kept per repository. The same gate text in another repository (`npm test`) no longer marks that repository's gate as red-checked or overwrites its result.
- Plugin: version 0.6.0, so `claude plugin update` brings the hook and MCP fixes made since Sidereus 0.13.0 (Claude Code caches a plugin per version).
- Pipelines «Start with recommended setup»: the preview lists file names instead of «[object Object]», an empty test command saves without a gate (projects with no detected command could not save at all), a preview error keeps the form editable, and the saved message names the written files.
- Pipelines «Request a red check»: the preview and the sent line scroll into view, the message names the target repository, and recipient labels show project and state (also for eval fix requests).
- Demo: the room invite preview includes the Topic line like the real one.
- Pipelines: each project keeps its own picked run across project switches, and a run clicked from the overview is no longer covered by an older saved pick.
- Sessions: folding one session's «Team» block no longer folds it on every card.
- External sessions and run requests: a non-finite or far-future hook timestamp no longer keeps a row alive forever.
- Settings: «Terminal integration» buttons now save (a session terminal-jump listener swallowed the click); notifications can be turned on; the header health warning switches language at once; a one-digit hour such as 9:05 is accepted for the saver target time; Start view and Language help texts describe what actually happens.
- Saver: saving with no hook folder returns «Hook folder not found» instead of failing with FileNotFoundError.
- Diagnostics › Connect: a file holding only the user's own hooks shows as not connected instead of «Partly connected»; after Apply the «Connected…» message stays until Close.
- Pipelines: clicking the run panel «Mode» select no longer drops Edit mode; the Save diff preview scrolls into view; renaming a stage keeps its key order.
- Chat, rooms and To-do: the screen updates right after a write (state cache cleared); «Outside rooms» counts the viewer once after a language switch.
- Features: turning Pipelines off no longer erases the Harness choice.
- Rail «Attention» count no longer includes rows marked Done or Later, so it matches the header chip.
- Work popup: pipeline stage chips show translated stage names; the «Evaluation» popover re-places itself on window resize.
- Keyboard: with the shortcut help open, ⌘K, s, / and ⌘B close it before acting, so two overlays never stack.
- Attention: a session snoozed «Later» or acked that asks a new question shows again at once; acking a row without a session id no longer hides other sessions' questions in the same folder.
- Quota details: «Who is using the 5h» counts the window of the account in use (marked «≈» when estimated); an account with no login shows «used unknown» instead of 0%.
- Saver: the «Hook folder not found» message is translated (path shown separately).
- Security: posting to a room, DMs, closing threads, terminal focus/app, saver settings, card/background/health dismiss and review marks now require the viewer page's Origin, so a local script can no longer act as the person.
- Pipelines: a failed folder load in the folder picker no longer overwrites the remembered folder or leaves the dialog busy; errors sent as `error`/`why` show their reason; a focused button or row keeps focus across the live refresh.
- Settings: auto-compact history errors and per-account write failures are translated, with values filled in.
- Quota details: «Who is using the 5h» follows the account whose sessions burned the most this window; per-session figures add up to the project total. The saver badge clock is labelled as the verdict time.
- MCP: To-do errors fill in their values («1-200 characters»); the text field declares its 200-character limit.
- Keyboard: the overlay rail at narrow widths keeps focus inside and returns it to the opener; an attention row keeps focus after Enter.
- Demo: shows To-do items and the account fields of the quota views.
- Tools and Harness report: with the server unreachable they say «check the server» instead of the browser's English «Failed to fetch».
- Attention (English): «Done · waiting for input» under a minute shows seconds, not the same number as minutes; the MCP label too.
- Korean UI: server error messages (pipelines, settings, To-do, rooms, git, hooks) are translated; messages with a file name or count send it separately; OS and exception text stays as sent.
- Quota details: the 5h % in the burn header and the saver badge each show their «as of» time, so two different figures in one modal no longer read as a contradiction.
- Pipelines: a denied stage jump no longer lights the stage as «main»; a stage title over 40 characters is named in the hint instead of an unmatchable tag; the npm-audit install hint is a command.
- MCP: an unknown tool name returns JSON-RPC -32602; `sidereus_attention` labels idle-mail and idle-shell signals; a bad To-do request body gets a body error.
- Structure › Architecture: with a flow lit, the toolbar hint no longer shrinks to a sliver at 900–1100 px; it hides, and a narrow bar shows the lit counter as numbers (full sentence in its tooltip).
- Pipelines: a red check first runs the gate on the clean clone (also for `check.sh --fast`/`--full` gates); a gate that already fails is reported as skipped instead of recording a pass, and "Gate red-checked" counts only passes.
- Pipelines: renaming and reordering a stage in one save keeps the stage's key order.
- Pipelines: a run with a far-future end time is no longer kept as running.
- Attention: a permission prompt is cleared only by a decision for the same tool; subagents' auto-approved tools no longer hide the main session's prompt.
- Attention: "Question waiting" clears when the question is answered in its picker (AskUserQuestion, plan approval), when the reply sits far back in a long transcript, or after a `!` shell command; "Done", "Background done" and "Background idle" clear once you type in that session.
- Attention: a question followed by a status line still counts as asking.
- Sessions: a background job whose `claude agents` lookup times out keeps its session instead of reading "done" under an old id; its pre-`/clear` session id no longer stays as a second live row.
- Terminal: a background job keeps its jump button through a one-poll lookup miss and after a daemon respawn re-parents its host.
- Terminal: concurrent polls no longer fail with "dictionary changed size during iteration" in the background-job terminal lookup.
- Work popup: ended Cursor and Copilot sessions without hooks open instead of "External session not found".
- Security: a scan where no scanner ran reads "Security not checked" instead of "issues 0"; the issues window header counts image scans and the severity filter drops the levels it hides.
- Structure: Ctrl/Cmd+wheel zoom keeps the point under the cursor; the zoom bar stays pinned under the header and no longer overlaps "Source text", which is clickable on a fresh load.
- Structure: module diagram lines no longer cut through group titles and boxes when route search runs out; a 900 px flow sequence view starts its edge list right below the diagram; evidence buttons show a "file:line" tooltip.
- Demo: subagent work logs open, and the diff popup shows the uncommitted files the rail counts.

## [0.13.0] - 2026-11-02

**Highlights**

- Plugin 0.5.0: `claude plugin update sidereus@sidereus` now brings every hook change since Sidereus 0.7.0 (strict mode, the To-do MCP tool, Windows fixes). Earlier releases kept the plugin at 0.4.0, so updating did nothing. The release audit now fails when plugin hooks change without a version bump.
- Attention: sessions waiting for your approval or answer sit in their own "Needs your response" group on top.
- Attention: a row marked "Done" stays dismissed instead of coming back on the next poll.

### Added

- Pipelines: the run ledger records time and tokens per stage, and the weekly report and the "Result layer" of the Evaluation popup show a "Stage cost (last 30 days)" table (median time, tokens and count per stage; unknown tokens are shown as unknown, not zero).

### Changed

- Attention: sessions waiting for your approval or answer sit in their own "Needs your response" group on top, with a red bar and a count, and never fold; everything else is under "For your information".
- Sessions: ended sessions are listed in one place, "Recently ended sessions"; the "Show N ended" fold is gone. Ended external CLI sessions (Codex, Cursor, Gemini, Copilot) appear there too, with their logo and work log. Jumping to an ended session from the palette opens that list and highlights its row.
- Structure: clicking a flow in the Edges panel selects it in the "Flows" picker, so "Clear flow" and "Sequence diagram" follow; clicking it again clears it.
- Timeline: the cost row says "this-window tokens · all accounts"; the status bar's "5h used" counts the primary account only, which the tooltip now says.
- `/api/state` sends `acksV`; the page polls with it and the server leaves out the unchanged `acks` map (about 18 KB per poll). Callers that send no `acksV` get the full map as before.
- Settings: the "Burndown curve" option is gone; it changed nothing (the quota details always show the curve). "Token widgets on the right" now says it applies only while the session list is pinned.
- Harness: the report title is just "Harness report", and a stale runtime check shows its check time once.
- Sessions: a session card no longer repeats its to-do line when a running subagent row right below shows the same task.
- A hidden viewer tab no longer polls harness evidence, branches or hook-connect status; the view refreshes once when it becomes visible. `/api/state` drops two keys nothing read (`fail1h`, `bgskip`), and `sidereus start/stop` checks liveness with a small request instead of the full state.
- Pipelines: the run bar beside subagent rows in the Now list has a tooltip naming its run ("Subagents of pipeline run: <name>").
- Pipelines: when the orchestrator does a stage itself (requirements, CI check, owner confirm, publish), the hand-off line and the skip message name the exact Bash tag that marks it, so the next stage is no longer refused.
- Pipelines: the bundled implementer brief carries a self-check of the review findings that recur most (unknown shown as zero, double counting, ended rows coming back, and others), and the designer names the ones that apply under Risk.
- Release audit: the plugin version check compares against the last release tag and is a gate of the release pipeline and a CI job on tag push; a shallow clone or a missing tag fails instead of passing.

### Fixed

- Structure: the header reload button in Architecture view reloads the architecture map; it reloaded only the size view's data.
- Plugin: version 0.5.0. The plugin stayed at 0.4.0 since Sidereus 0.7.0, so `claude plugin update` kept the old hooks (Claude Code caches a plugin per version); updating now brings strict mode, Windows gate evidence and the To-do MCP tool.
- Sessions: a long-running Bash in auto mode is no longer shown as "Bash waiting for approval".
- Sessions: after `/clear`, the previous session id of the same process no longer shows as a second live row.
- Terminal: a Claude Code background job jumps to the terminal tab of the claude that started it. When that tab is gone, the button says "Background" and copies `claude attach <id>` instead of `claude --resume`, which would open a second session.
- Sessions: a Claude Code installed with npm (process `claude.exe`) is detected as live; its background daemon, pty host and spare process no longer add rows.
- Settings: a "Per account" save no longer adds `autoCompactEnabled` to an account file that did not have it when only the window changed; the confirm dialog no longer lists accounts already at the new value.
- Pipelines: loop-back labels and the editor's edge and loop panels show stage titles in the UI language.
- Tour: on a first run with no project picked, the pipeline step says to pick a project first instead of pointing at a missing «Edit» button.
- Structure: a long flow name cut off with "…" shows its full name on hover.
- Demo: the room invite and room create previews no longer fail with "unknown error".
- Sessions: the pipeline chip on a session row shows the stage title in the UI language ("Live verify" in English), like the pipeline view.
- Timeline: a Cursor session row no longer shows "Tokens 0"; Cursor records carry no token counts, so the chip is left out instead of claiming zero.
- Demo: the work popup of an external session row (Gemini, Codex) opens instead of failing with a script error.
- Pipelines: a run that two sessions both closed (main and a background agent) is counted once in the result layer and the weekly report; it was counted twice, which raised the run count and the review loop-back rate.
- Pipelines: the stage titles of the bundled pipelines (Diagnose, Confirm, Review-find, Tag, ...) have English names; the English UI no longer shows them in Korean.
- Attention: a "Needs your response" row lines up with the "For your information" rows; its red bar no longer stacks with the account colour bar on multi-account screens.
- Terminal: a Claude Code background job shown in the tab of the claude that started it copies `claude attach <id>` (or nothing) when the jump fails, never `claude --resume`, which would open a second session.
- Attention: a row marked "Done" stays dismissed across polls; it came back when nothing new had happened.
- Terminal: a background job row no longer clears other sessions' terminal lookup, which turned their "Terminal" button into copying `--resume`; a reused process id can no longer jump to an unrelated iTerm tab.
- Sessions: the false "Bash waiting for approval" in auto mode no longer returns after a viewer restart when the transcript's last rows were short.
- Sessions: the terminal hosting a Claude Code background job no longer adds a second "Waiting for input" row from an old transcript in the same folder.
- Pipelines: a request whose last stage was renamed closes on screen when the run ends, as it already did for the hook.
- Pipelines: when one session holds several open runs, the subagents of every run are grouped under their own run bar in the Now list; the second run's agents showed as plain rows.
- Tour: the pipeline step says "Press Edit" when the Edit button exists but is scrolled out of view, and the plugin step no longer calls the Sidereus MCP server read-only.
- Chat: at 1100 px the toolbar wraps to a second line instead of scrolling the page sideways.
- Quota: a half-written `.claude.json` no longer lets another account's OMC cache mix into the primary account's quota for 30 s, and the "OMC cache not read or written" warning is no longer logged again on each flip.

## [0.12.1] - 2026-11-02

### Fixed

- To-do: an item in progress shows the session that started it. With two sessions in one repo, both rows used to label it with their own name.
- To-do: a repo whose root folder is a symlink no longer shows a "To-do n" badge whose list then fails to open.
- External CLI sessions: a slow process lookup no longer drops the session's pid, which folded a live session under ended after 30 minutes and broke "To terminal".
- Pipelines (pipx/uv installs): a renamed review stage in the security-fix pipeline now closes the request on screen, as it already did for the hook.
- Connect: `~/.cursor`, `CODEX_HOME` or the Gemini folder kept as a symlink (dotfiles) can be connected again, as in 0.11. A symlinked hooks file is still refused.

## [0.12.0] - 2026-11-02

**Highlights**

- Cursor CLI and Copilot CLI sessions now show up, even before their hooks are connected, and "Connect" works on pipx/uv installs. Refs #9 #10
- Per-project to-do list recorded by the sessions themselves, shown on the session row.
- Session state is more accurate: a Bash waiting for approval keeps its badge, and background shell rows close when the shell is stopped or denied and survive a viewer restart. Refs #23

### Added

- To-do list per project: sessions record items (open, in progress, done) through the Sidereus MCP tool (nothing is written in the repo), the session row shows "To-do n", and the expanded list lets you add and check items and see them "By day".
- Copilot CLI: session list and state via hooks, and "Connect" installs the hooks file. Refs #10
- Copilot CLI: token usage on session rows and the timeline, and its quota in the status bar. Refs #10
- Copilot CLI: pipeline stages light up for Copilot sessions, and "Connect" also adds the pipeline hooks. Refs #10
- Cursor CLI and Copilot CLI sessions appear in the session list and the timeline without Sidereus hooks (read from each CLI's own records, metadata only); a header chip flags CLIs whose hooks are missing. Refs #9 #10
- Attention: "Idle shells" flags a live session whose background shells have produced no output for 15 minutes.
- Harness report: a gate cost line (caught, blocked, overridden; gate time, hook overhead, time paused by a block, last 7 days) next to what the gates caught. Refs #27

### Changed

- Sessions: the first line of each row is grouped into identity, usage, work and actions, and each group starts at the same position on every row.
- Codex and Copilot rows waiting on a permission request read "Waiting for approval" instead of "Waiting on notification".
- After "Connect", the result tells you to restart CLI sessions that are already open (Codex: restart, then run /hooks).
- Harness report: the runtime card folds to one line unless it is all clear, so the tiles come first.

### Fixed

- Pipeline evaluation: passes are counted once per commit, and "fix followed" counts a later commit only when a bug-fix pipeline run (`"catch": "person"`) made it and it touches the same code file; edits in the same run, shared docs, registries, tests and screen baselines no longer count as fixes.
- Pipeline editor: the "Evaluation" panel opens under its button instead of at the left screen edge over the side rail.
- Evaluation popup: the report path sits on its own line instead of breaking at the date.
- security-fix pipeline: edits in the target repo unlock when the pipeline file's last stage finishes, even after that stage is renamed; before, they stayed gated for 24 hours.
- pipx/uv installs now include the external CLI hook templates, so external CLI rows offer "Connect" instead of reading "no ext-hooks".
- Cursor CLI is detected by `~/.cursor/cli-config.json` when it is not on the viewer's PATH (seen on Windows). Refs #9
- Sessions: a Bash waiting for approval keeps its badge while older shells (servers, loops, earlier commands) run in the same folder. Refs #23
- Background shells: a launch denied by a hook inside a subagent no longer stays open. Refs #23
- Background shells: a shell stopped with TaskStop closes its row. Refs #23
- Background shells: open rows survive a viewer restart. Refs #23
- Sessions: identity chips never wrap or clip (only the name is shortened), and the pick box sits on the name's line.
- Sessions: "Show n ended" opens on the first click while the mouse is over the list.
- Windows: external CLI sessions (Codex, Cursor, Copilot, Gemini) leave the list within 10 minutes after the CLI closes; before, the hook sent no process id there and the row stayed "waiting for input" for up to 24 hours.
- External CLI rows with no process id fold under "Show n ended" after 30 minutes without events, instead of reading "waiting for input" for up to 24 hours (sessions closed by closing the terminal send no end event).
- Codex: a session closed with /exit no longer stays "waiting for input" forever; recent Codex runs hooks from its long-lived app-server daemon, which the hook mistook for the session process.
- Windows: a CLI process that has exited no longer reads as alive while another program still holds a handle to it, so closed sessions show "Disconnected" and leave the list.
- Sessions: an ended Codex, Cursor, Copilot or Gemini session folds under "Show n ended" for 12 hours like a Claude session, whether it sent an end event, its process disappeared or it went quiet without a process id; it no longer lingers as "Disconnected" or vanishes at once.
- Header: the "Sessions" button stays at the right edge when there are no to-do chips.

## [0.11.0] - 2026-10-31

### Added

- Harness report: every verdict has a «Next step» (meaning, why, who acts, next step; AI-session verdicts draft a mailbox instruction with preview + confirm); guides live in docs/verdicts/<id>.md. Refs #27
- Hook flow: hooks flagged «Slow» (average time per run from OTel, «n hooks combined» when several share a firing) and «No visible effect» (many runs, never blocked, never printed); rows without measurements say «time and effect not measured yet». Thresholds start at 1000 ms and 50 runs. Refs #28
- Config map: «Remove» on a user/project Claude Code hook (diff preview, backup to tool-trash/, then write); plugin hooks show «How to turn off» with `/plugin disable <name>`. Refs #28

### Changed

- The «Harness» view is renamed «Harness report» (switch, view title, Settings › «Features») and is on by default for new installs; a saved setting that turns it off is kept. Refs #27
- Harness: «Config map» moved to the top of Tokens › «Tools» (same content, open state remembered); the Harness report gains a folded «How to read this» explaining the four numbers, «What is guarding» and the incident cards. Its «problems» / «to check» counts open the map in Tools.
- Harness report: fourth tile and checkpoint «Found by a person first» — ended runs of pipelines marked `"catch": "person"` (bug-fix pipelines), each card listing the commits in the run window and the `tests/` files they touched, or «no guarding test». «Failed again later» and «Reverted» merge into one «Broke again» tile; reverted cards stay as they were.
- Harness report: «After push (CI)» checkpoint from `gh run watch --exit-status` results recorded by the evidence hook — run and caught counts, CI cards on click, red→green CI incidents, and «Holding: CI streak n/5» (newest greens in a row, reset by a red). Hidden with no CI records; Sidereus never calls GitHub. Refs #27
- Harness: folded «Guard self-check» table from `scripts/harness_selfcheck.py` results — per guard the case it must catch and the control it must let through (situation fed · expected · actual · PASS/FAIL), beside the real «Blocked n» / «caught n» counts; «Not run yet» with the command when there are no results, «different commit» when they come from another HEAD. The viewer only reads the results file. Refs #27

### Fixed

- Hook writes («Connect» in Diagnostics, «Remove» in Config map) keep a CRLF settings file CRLF; the rewritten `hooks` block used to come out with LF, leaving mixed line endings on Windows. Refs #28
- Harness report: the recipient select in «Next step» is capped at 32em instead of stretching across the whole card (about 1750 px at 1920); it still shrinks to fit narrow rows. Refs #27

## [0.10.0] - 2026-10-30

**Highlights**

- Security checks: «Request fix» sends a security-fix pipeline run request (fix → re-scan → review) and keeps the repo gated until the review, instead of a plain message a session could mark done without a re-scan.
- Pipelines: per-project strict mode (`.claude/pipelines/_policy.json` `{"enforce":"writes"}`) makes every file edit, Bash write into the repo and commit go through an open run.
- Harness: a gate report replaces the «Flow» strip — what was caught (red→green), what held, what was reverted, and which gate caught it.

### Added

- Harness: «Runtime behind latest patch» card from the newest security report — per runtime, current → latest patch in its cycle (security fix, end of life) and cycles behind the newest release, one next step each; a stale report asks for a rerun, no report shows «No check on record» with the command.
- Security checks: trivy scans Dockerfiles for misconfigurations by default; `--images` also scans each base image (Dockerfile `FROM`, compose `image:`) for CVEs, deduplicated across images, (a `FROM ${ARG}` uses the ARG's default declared before the first `FROM`) with a «Base images» report section (fixable high/critical → replace base image, unfixed → waiting). A registry login or DB download failure is a failed row with its reason, never a clean result.
- Structure: a running security check shows a run banner under the header, like the architecture-map run (stage, project · session, «Stop» when the request came from Sidereus).
- Structure: the «N outside {style} flow» badge is a toggle: its tooltip says it is a review hint, not an error, and pressing it lists only those edges (each with its reason) under a «Not an error · N edges to review» line; pressing again, or picking a module or flow, restores the full list.
- Pipelines: per-project strict mode — with `.claude/pipelines/_policy.json` `{"enforce":"writes"}`, Edit/Write and `git commit` are refused while no run of the session is open (15 minutes after a run ends still count, so the ship commit lands); Bash writes into the repo (redirects, `tee`, `sed -i`, also after `then`/`do`, `VAR=` and `env`) are gated too; a pipeline marked `"readonly": true` (review) does not unlock writes; a light `quick-fix` pipeline ships for known small fixes.
- Pipelines: a stage card's «gate FAIL» line opens the Harness incident card that started from that failure (or says it is not fixed yet); «Pipelines» returns to the same pipeline and scroll.
- Hooks: opt-in `"onFailure": "block"` for `pl_flow.py`, so a guard that cannot start or times out blocks the call instead of letting it through (off by default).

### Fixed

- Memory: the tool-index cache is written row by row instead of building every row first; the boot peak drops by about 65 MB (291 → 226 MB, same machine and data); a transcript tail scan reads only the bytes left in the file instead of reserving its whole 32 MB read limit.
- Security checks: with no scanner findings the issues window shows «No scanner findings» (or «No issues match the filters») instead of a tall empty box, and an open window picks up the viewer's current styles on the next repaint after a reload instead of keeping the old ones.
- Memory: the inline page is held at 2 bytes per character instead of 4 (about 5 MB less RSS): one literal emoji in a regex had widened the whole string; it is now an escape, and a test keeps every page character at or below U+FFFF.
- Pipelines: the «Working now» card puts a subagent under a run only when its description carries that run's tag; an untagged agent is listed apart instead of looking like part of whatever run is open.
- Security checks: the issues window «Request fix» line turns «Done» once a newer security check result exists for the repo, instead of staying «Delivered» forever.
- `backup.sh`: with no mailbox MCP checkout it backs up the code and says the MCP part was skipped, instead of writing an empty archive and reporting success; a failed archive is removed so the keep-10 cleanup never drops a real backup.
- Structure: going back to a map you had already viewed in another project opens it where you left it, instead of the corner.
- Pipelines: a background Bash from an earlier run (a dev server that never reports completion) no longer lights a stage of the current run.
- Harness: the runtime card no longer suggests `brew upgrade` for a runtime already on its latest patch, and suggests moving to a supported cycle for an end-of-life one.
- Harness: a run whose last stage never reported back reads as ended after 30 minutes idle, as Pipelines already does, instead of running forever.
- Attention: a subagent waiting on a permission prompt keeps its badge when its log line is written late (measured 1.2 s lag against a 1.0 s allowance).
- Attention: a main-session Bash permission prompt is no longer cleared by auto-approved Bash calls from background subagents, so «Bash waiting for approval» shows.
- Mailbox wake: after `/clear` or resume the session hears new mail at once instead of only after its first turn ends; mail already seen before `/clear` does not wake it again.
- Mailbox: a concurrent read no longer shows every message as unread for a moment (the read cursor is written atomically).
- Settings: saving keeps a symlinked `~/.claude/settings.json` a symlink and writes its target, instead of replacing the link with a plain file.
- Pipelines: strict mode also catches `/usr/bin/git commit`, `git -c k=v commit` and `--no-pager`, and a commit message containing `--dry-run` no longer passes as a dry run.
- Memory: the mailbox bus no longer grows `sys.path` on every poll.

### Changed

- Harness: a gate report replaces the «Flow» strip — «Caught (red→green)» · «Held» · «Reverted» at the top, «What is guarding» (before edit · right after · before commit, each with its catch count) and one card per catch: red run → fix commits → green run → held or reverted.
- Harness: each «What is guarding» chip and the fast/full mode mark say which hook or gate it is, who runs it and when; the config map summary and its fold both read «Check results», and the fold opens when the check found problems.
- Security checks: «Request fix» sends a security-fix pipeline run request (fix → re-scan → review) with the requested findings, and the target repo stays strict while it is open; its line shows «fix commit seen <hash>» and, after a re-scan, how many issues are left.
- Security checks: the issues window and badge tooltip warn when base images went unscanned (trivy missing, or `--images` not ticked) instead of showing only the total.
- Timeline: row chips name what they count («202m active», «compacted 1×», «+N finished runs», «N repos»), the axis legend keys bar colours and the «Compacted» tick, and the session picker tooltip shows the 8-character id.
- Pipelines: the pass picker reads «pass k» (the loop-back glyph is kept for «sent back here» only); auto-fit never shrinks the canvas below 1.0 (0.9 under 1100 px) — it pans instead — and cards wrap to 2 lines, with «Session model» and «No gate» labels.
- Layout: 1440/1100/900 widths wrap or fold instead of cutting text with an ellipsis («Working now» names wrap and the list starts folded below 1000 px, the run strip and timeline legend wrap); the header keeps «Sessions» at 900; above 1440, history rows cap at 1200 px, branch details at 700 px and prose at 90ch.
- Structure: the edge badge reads «Edges verified n/m».
- Docs: an installed package (pipx/uv) needs a git clone for structure map and security check requests; README and GETTING-STARTED say so next to the install path.

## [0.9.0] - 2026-10-28

**Highlights**

- «Request fix» from the security checks and the evaluation window survives a page reload and shows its delivery status.
- A run ends as soon as its background agents finish — no more «Running» left stale for up to 30 minutes.
- Structure: keyboard focus never hides under the sticky map header.
- Harness: a commit the pipeline guard blocks before a required gate passes now counts as «Blocked» (it showed «Blocked 0»).
- Settings › «Features»: a toggle applies on «Save» — no restart needed.

### Changed

- Sessions: the account chip shows the shortest unique label (for example «myac») instead of a prefix cut by the layout; the full account stays in its tooltip.
- Rail: the alerts and settings buttons use the same 40 px size as the view tabs, and the settings icon keeps full colour so it is easy to find.
- Performance: lower memory at startup — the failure scan reads 1 MB chunks and the tool index saves and re-sorts without holding whole copies in memory.
- Pipelines «Watch»: a stage selected while it was running follows the run to the next running stage, as long as only one run is live.
- Settings › «Features»: a toggle applies on «Save» — no restart; the open page shows or hides the tab and the Pipelines «Harness» switch at once.
- Pipelines: «Red check», «Catch» (seeds) and «Holdout» in the evaluation panel explain themselves on hover.
- Harness: with Claude Code telemetry on, every Claude Code hook shows its full run count (hooks that print nothing included), and a hook that ran 0 times over 3+ days is flagged «did not run in N days».
- Docs: `SECURITY.md` and `docs/CONFIG.md` note that the quota lookup and the paid quota probe reuse the Claude Code sign-in token outside Claude Code, which Anthropic's terms may restrict.

### Fixed

- Pipelines: the «pipeline file not found» note for a run from another folder names the session's folder and says to use «Add project» on the folder holding the pipeline file.
- Header: the second number on «Sessions» reads «need you n» instead of a bare count next to the open-session count.
- Structure: «Redraw» / «Generate diagram» say in their tooltip that they ask a live session (preview first), and the «repository location is unknown» reason now says it needs Sidereus run from a git clone.
- Structure: the security badge reads «Security issues n», and its tooltip shows «ran · n found» per scanner instead of «ok», which read as «no findings» next to a non-zero count.
- Structure: a sent «Request fix» from the security checks window survives a page reload and shows who got it, when, and whether the session acknowledged it.
- Pipelines: a sent «Request fix» from the evaluation window survives a page reload and shows who got it, when, and the session's acknowledgement, for the open pipeline only.
- Work log: opened for the first time on a session with file changes, it ends at the bottom even when the git diff arrives late; a reader who scrolled up stays put.
- Timeline: the «Uncommitted» chip follows the row you click or the session picked in «Session»; clicking it lists the repositories that session touched (worktrees included) with their own counts and a badge of how many have changes, and the pinned «View all changes» row opens the diff.
- Structure: a control reached with Tab no longer hides under the sticky map header, and diagram nodes and edges show a focus ring; the screen check now walks 30 Tab stops per tab and fails on a focus the user cannot see.
- Structure: clicking a module keeps it under the pointer instead of re-centring the view; at 900 px the detail panel floats over the map instead of opening below the fold.
- Pipelines: the «Running» row no longer overlaps its agents summary at 900–1100 px; «Working now» names end in an ellipsis with the status icon kept; the evaluation panel shows English stage names in English; tour step 3 points at «Edit» in Watch mode; the template menu item reads «Start from a template» like the empty-state button.
- Settings: «Connect» from the Pipelines list opens the preview in «Diagnostics», where the diff is readable; Features «Save» is the primary button; an empty «Security tools» list reads «Not installed», not «Could not load».
- Harness: the Guard node no longer says «no record» next to skip counts, and a count never breaks from its word.
- Status bar and timeline: on a narrow bar, reset times, the saver label, CLI costs and the 7d «used» figure drop before «Today» (still in their tooltips); the dark rail badge meets 4.5:1 contrast; the compaction chip shows «N×» instead of a cut word; the timeline «?» has a 24 px hit area.
- Pipelines: a commit at a middle stage (for example the release pipeline's tag stage) no longer ends the run, so the next stage is not refused as a skipped jump.
- Harness: a commit the pipeline guard blocks because a required gate has not passed (or a declared skip of a required gate) now counts as «Blocked» in the flow and result counts, labelled «Commit before gate» / «Required gate skipped»; before it showed «Blocked 0».
- Sessions: on Windows and Linux with several Claude Code accounts, when one account's session list cannot be read its open sessions show as unknown instead of ended.
- Sessions: a Cursor or Gemini CLI session left idle for more than 24 hours no longer disappears while its process is still running.
- Status bar: a CLI whose session is still open but idle since before midnight (Cursor, Gemini, Codex) keeps its «Today 0» entry.
- Sessions: a running session whose last record cannot be read shows as unknown instead of idle, and a subagent whose log cannot be read no longer shows «Idle» or «quiet».
- Sessions: the invite pick box has a larger hit area, so a near miss no longer opens the work log instead of picking the session.
- Sessions: the account tooltip no longer ends in an empty «config dir» when the directory is unknown.
- Structure: at 900 px the map scrolls far enough that bottom-left modules can be brought out from under the floating detail panel.
- Sessions, Timeline and Pipelines: clicking an agent started by a Claude Code workflow opens that agent's work log (it opened nothing, an empty log, or the whole session's log).
- Structure: a diagram run requested for the Sidereus repository itself no longer shows as running (with a Stop button) on another project the same session drew earlier, and an older request from that session no longer reads «Running» once a newer one starts.
- Pipelines and Structure: a run whose last stage ran as a background agent reads done as soon as that agent finishes (it showed «Running» with a Stop button for up to 30 minutes), and «Stop» on a stage the main session runs itself now ends as «Stopped» instead of staying «Stopping».
- Security: bandit reports nothing on shipped code — intentional patterns (silent hook error handling, subprocess with a fixed argument list) are declared once in `pyproject.toml` with the reason, the rest are checked one by one; the invite hook calls `/bin/ps` by full path.
- Structure › security checks: the header stays on one line — «Run security check» no longer drops alone onto a second line; the two buttons stay together on the right and the folder·commit text shortens first.

## [0.8.1] - 2026-10-26

### Fixed

- Windows and Linux: the 5h/7d quota fills in — the token is read from Claude Code's `.credentials.json` (it was macOS keychain only), and when quota cannot be fetched the status bar says why ("Quota lookup is turned off", "No Claude Code login found", "Could not reach the usage API").
- Settings: in «Features», «Save» and «Undo» appear right under the heading instead of below the last row (often off-screen), and a feature switched off by an off dependency is saved as off, matching its checkbox.
- Settings (Windows): «Mailbox watch» treats `C:\x` and `c:/x` as one folder — no duplicate rows, no false change, and the saved setting no longer flips with key order.
- Timeline: the axis always spans the chosen window (e.g. 6 h); with only one short session (a fresh install) it shrank to that session's few seconds, with no time labels and one token block across the whole width.
- Windows: gate results are now recorded (they were silently skipped for lack of a file lock), so a pipeline with required gates can commit after the gate passes and the «Harness» Gate and Kept steps fill in.

## [0.8.0] - 2026-10-25

### Added

- Pipelines: with two or more stages running at once (loop-backs, fan-out) and none picked, the result pane shows one card per running stage (stage, agent, running agents with «tool · ago»); a card click selects the stage like a canvas node click.
- Pipelines: stages show what each agent does — result pane agent buttons carry the task line next to the type, and the stage header and canvas node show the agent file's one-line description.
- Pipelines: each running stage agent in the run view shows what it is doing now — the current tool name and how long ago it last wrote («Bash · 12s», «Idle · 3m»); tool input never appears.
- Hooks: Cursor, Codex and Gemini CLIs installed without Sidereus hooks get a «Connect» line on the first screen and in Settings › «Diagnostics»; it previews the diff, backs up the file and merges the Sidereus entries next to your own hooks (Codex then needs `/hooks` approval) (#21).
- Hooks: Cursor CLI sessions show up through `ext_hook.py --platform cursor` — its camelCase events are mapped, the folder comes from `workspace_roots`, and `ext-hooks/cursor-hooks-example.json` is the hook file (macOS, Cursor CLI 2026.10.22). They also get a Timeline row, drawn from hook event times.
- Tokens: Cursor CLI token counts from its `stop` hook (counts and generation id only) now reach «Today», Tokens › «By platform» and the Timeline row, counted once per turn and kept after the session ends or the viewer restarts.
- Status bar: a CLI with a session today but no tokens yet (a failed first reply, or Cursor) shows «Today 0» instead of being left out.
- Pipelines: the «+ Add project» folder picker suggests «Recent session folders» — up to 8 folders where a Claude Code, Codex or Gemini session worked in the last 14 days and that are not in the project list yet (name, path and last session time only); a click opens that folder like typing its path.

### Changed

- Mailbox: Codex mail wake (`--wake`) is now opt-in; the example and «Connect» install turn-end delivery, because the daemon socket path it relies on is undocumented. Failures in `.codex-wake.log` now record the Codex version.
- Mailbox: Codex mail wake no longer requests the experimental app-server API (the calls it uses work without it on Codex CLI 0.164.0).
- Pipelines: the view follows working runs — with no working run on screen, a run that starts working (or the newest working run after a reload) is selected; while a working run is viewed, later ones only show as running; when the viewed run stops working, the newest other working run is selected. A past run picked from «Run k/N» and the Edit view are never switched.
- Structure: a module's «Files» section is folded by default and sits last in the detail panel (after Neighbours and Flows); opened, it is a folder tree (first level, «name/ count», Expand all / Collapse all) and a file click opens it in the Source popup.
- Server: the idle structure warm-up runs each cell in a short-lived child process that writes only the structure cache, so its memory peak no longer stays in the viewer process (#19).
- Pipelines: finished stage agents move to a muted «Done» row below the running ones, so a two-line running button no longer sits beside a one-line finished one.
- Structure: the architecture header badges are grouped by colour (purple, blue, grey, then amber/red); colours, text and tooltips are unchanged.
- Timeline: the name column can be resized from any row, not only the axis row; limits and the remembered width are unchanged.

### Fixed

- Sessions: on Windows and Linux an open Claude Code session no longer lists as ended — liveness comes from `claude agents` when no process list is available.
- CLI: `doctor` and the CLI hints name the command for how Sidereus was installed — `sidereus` for a pipx/uv install, `py -m sidereus` on Windows, else `python3 -m sidereus`.
- Security checks: tracked files marked `export-ignore` in `.gitattributes` are scanned too; the scan used to see only the export set (1156 of 1209 files in this repo).
- Pipelines: the security gate's red check commits its fake key inside the temp clone, so it no longer reports «injected break not reported» against a scanner that reads only committed files.
- Bell: subagent and background-task completions that happen while the viewer is down are announced after it restarts (only those after its last scan, at most 20 and 24 h, never twice).
- Pipelines: a stage's «Agents N» counts the agents it lists, so a stage with no agent records no longer shows a number with nothing to click.
- Quota details: switching the «Main account» repaints the burndown, saver and quota panels (with the default-account note) at once instead of showing the previous account until the next poll.
- Quota: an account whose usage refetch is rate-limited (HTTP 429) keeps its last numbers for up to 30 minutes instead of dropping to «not measured».
- Pipelines: a stage agent waiting on a long tool call (e.g. a test run over 2 min) shows that tool instead of «Idle».
- Pipelines: the «tool · ago» line under a running stage agent starts at the button's left edge instead of being centred.
- Pipelines: a stage lists every agent, running first, so a finished sibling's work log can be opened while another agent still runs.
- Pipelines: a run whose current stage is done by the orchestrator itself shows «orchestrator» in the running list instead of «Agents 0».
- Server: the idle structure warm-up starts while a tab is open — only page loads and real input (pointer, keys, wheel; sent at most once per 10 s, viewer Origin only) count as activity, not timer polls (#19).
- Attention: acknowledging a «blocked» row holds while sibling subagents come and go; a newer approval wait still shows it again.
- Status bar: it follows a window resize as it happens instead of freezing until the drag stops.
- MCP: `sidereus_attention` reports «blocked» sessions from permission marks (e.g. a subagent waiting for approval) like the screen does.
- Work log: the split view refits its height on window resize instead of keeping the old height until a click.
- Mailbox: a successful Codex mail wake no longer writes a stale daemon socket error to `.codex-wake.log`; scan errors are logged only when no daemon has the thread.
- Work log: when the machine is too busy to confirm the request comes from your own user, the popup says «Viewer is busy — retrying…» and retries (2/4/8/16 s) instead of failing with HTTP 403; a real refusal is unchanged.
- Timeline: the removed-lines count in the «Changes» chip is easier to read in the dark theme.
- Settings: the saver level table's rules and notes show in Korean in the Korean UI (known hook lines are matched to fixed templates; an unknown line stays as sent).
- Pipelines: a finished or earlier run's stage lists its agents (from tagged subagent records) instead of only «Agents N» with no buttons.
- Pipelines: with no logged-in session in the project, «Start from a template» is the primary button instead of «Ask AI for a draft», which could not be sent.
- Pipelines: the «Ask AI for a draft» message was partly Korean; it is now English.
- Pipelines: the empty-screen demo hint and the first-visit tour show the demo command that matches the install (`python3 -m sidereus start --demo` for a clone, `sidereus start --demo` for pip/pipx/uv).

## [0.7.0] - 2026-10-23

### Added

- Structure: the security issues window header and the Security badge tooltip show when the project was last checked («Last check MM-DD HH:MM · 3d ago», or «Never checked»); past 30 days, the monthly cadence of `security-checks`, the line turns amber.
- Pipelines: each pipeline shows its «When to use» line under the header in Watch and Edit (one muted line, full text on hover) and in the picker tooltip; refactor, review and sidereus-change got one.
- Structure: the security issues window has a drag grip between the findings list and the history list (arrow keys step 24px, double-click or Home resets); each list keeps at least about three rows and the height is remembered.
- Pipelines: a Bash description `[pl-agent:<name>/<stage>=<agent>]` lets a run use another subagent_type for one stage; the `security-checks` review stage uses a project's own security agent when the session has one, and reviews with a default lens when there is no threat model.
- Pipelines: `[pl-none]` declarations are now logged per project (category and time only, kept 90 days) so the categories can be counted later; nothing is shown on screen yet (#16).
- Pipelines: the 3rd `[pl-none:no-fit]` of a project within 7 days tells the session to offer the user a draft pipeline for that kind of work (written only after the user agrees); at most once per project per 7 days, count and project path only (#16).
- Viewer: installable as an app (web app manifest + icon) and each window opens/keeps its tab from the URL hash (/#pipelines, /#structure, …) (#18).

### Changed

- Plugin: version 0.4.0, so installed copies pick up the hook changes of this release (`[pl-none]` log, run fixes).
- Server: the heavy first pass of each boot warm-up (usage, timeline, tool index, branches, structure, …) runs one at a time in a fixed order instead of all at once; startup RSS peak 358 → 279 MB, first screen 4.65 → 3.45 s (#20).

### Fixed

- Hooks: `ext_hook.py` refuses a `--url` / `SIDEREUS_HOOK_URL` whose scheme is not http or https.
- Pipelines: with four or more open runs in one session, an older run whose stage still runs as a tagged background agent no longer shows as ended after 30 minutes.
- Pipelines: a `[pl-none]` declaration written while the log was being trimmed (over 256 KB or 90 days) is no longer lost.
- Harness: opening Harness during start-up starts the tool usage scan at once instead of waiting for the earlier warm-ups to finish.
- Diff: an untracked secret file (`.env`, `.env.*` except example/sample/template, `*.pem`, `*.key`, private SSH keys, `.netrc`, `credentials`, …) is listed by name but its contents are never read or sent; the diff shows one line «(contents hidden: secret file)».
- Docs: the README says Gemini CLI sessions show token counts only; their plan limits live only on Google's server (check with `/stats` in Gemini CLI) (#8).
- Pipelines: a run whose last stage never closes it (main's push with no commit, a background last stage, or the remaining stages skipped) no longer shows as running for up to 6 hours; with no live agent or main marker for 30 minutes it shows ended at its last activity, and skipping every remaining stage after a finished stage ends the run.
- Structure: an arch-map or security-check run request sent to a Claude session in another repo is now recorded as a run (a «Running» row and provenance); the request names the stage tag for Claude recipients too, and the untagged-dispatch reminder also lists the pipelines of known projects, so the session no longer tags every stage `[pl:-]`.
- Structure: an arch map drawn by a session working in another repo (a cross-repo request, still-open run, or a folder with its own pipelines) no longer shows «Drawn by: unknown» after a restart; the page's request names the target and the run's tagged stage agents give the models.
- Server: a viewer started with CLAUDE_CONFIG_DIR pointing at another spelling of the same projects folder (e.g. via `sidereus start`) no longer rescans every record and counts each event as a duplicate (tool index 719 → 288 MB peak) (#17).
- Pipelines: an arch-map run on a repo only its subagents touched no longer stays «running» after the map is verified; the run's target is the requested repo, and a finished agent's end no longer counts as activity after the result.
- Pipelines: a «Running» row of a pipeline the session's folder does not own (e.g. arch-map run against another repo) opens that pipeline from its own repo, like the «Working now» tree, instead of silently showing the folder's first pipeline.
- Structure: «Run security check» also offers sessions working in the Sidereus repo (where the pipeline file lives) as recipients, after sessions in the target repo; before, only sessions that had touched the target repo were listed.
- Server: the tool usage index no longer holds every event id as a string; it keeps compact arrays, drops events older than 90 days and stops copying the whole index on each recompute. Measured on 1.5M events: index 328 → 55 MB, process peak 539 → 166 MB, cache file 96 → 47 MB. The first start after updating rebuilds the cache once (about a minute of «Loading» in Tools/Harness) (#17).
- Pipelines: a first run with no session and no project picked now says what to do next (start a Claude Code, Codex or Gemini session, or try `sidereus start --demo`) instead of only «Pick a project»; the Sidereus clone's own row in the project picker is marked «(built-in)»; the «Agent and model per stage» caption shows only in Edit.
- Server: structure snapshots read back from disk no longer pile up in memory without a limit; every cache write goes through one capped put and the cap is 32 instead of 200 (~5 MB each). Measured at 36-40 min uptime: footprint 715 → ~375 MB (#17).
- Server: the structure snapshot cache keeps the gzip form in memory and decodes on a hit; background warm-up writes to disk only and no longer fills the 10-cell result cache, and a disk hit from the screen now respects that 10-cell limit. Footprint at 20-40 min uptime ~375 → ~272 MB; startup peak 483 MB (#17).
- Pipelines: the stage pass pill («↻n») stays a 24px click target at any canvas zoom; the canvas scale (down to 0.4) had shrunk it to as little as 9.6px on screen. The visible pill is unchanged.
- Demo: no saver chip in the status bar — the saver hook is not shipped, so a real install never shows it.
- Pipelines: a session whose turn ended but whose tagged background task, subagent or run stage is still going shows «Working» in «Working now» (row, its dot and the pulsing rail dot), and the canvas keeps that stage in progress until the task ends instead of closing it after two minutes.

## [0.6.0] - 2026-10-22

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
- Pipelines: each «Working now» card lists its live subagents as a tree (Timeline agent cell, running first, at most 6 then «+N more»); clicking one selects the session's run and that agent's stage.
- Pipelines: «Watch» fills the window — canvas, result pane and an always-present «Running N» card, split by drag grips (default shares 0.75 / 0.14 / 0.11, saved; double-click resets); the per-stage run table is gone since the canvas and result pane carry that state. «Project»/«Pipeline» pickers and canvas toolbar buttons read as controls (28px, border, focus ring).
- Timeline: light-theme bars, histogram and stage bands are desaturated so they sit calmer; neutral name-cell chips use stronger text with a ring.
- Structure: a framework name joined with « + » or «, » (e.g. a BE and an FE stack) shows as one badge per part, so each wraps instead of being clipped; the full name stays in the tooltip.
- Chat: the «Participants» panel shows each participant's platform logo when the id matches a live session.

### Fixed

- Viewer: settings stay in sync across open tabs — «Done» and «Later» on an Attention item reach every tab within about a second (a missed tab catches up on its next poll), and a stale tab can no longer erase another tab's «Done» or «Later».
- Attention: clicking an item in the rail list opens the session drawer at that item's row in «Attention» (unfolding low-priority or overflow rows); the terminal jump stays on the drawer row.
- Pipelines: the selected session is marked in the collapsed «Working now» rail (ring) and when a «Running N» row is picked; rail dots show a label with project, state and run on hover or focus, and only working sessions pulse.
- Pipelines: the Watch resize grips have their own 24px row, so a press on the canvas edge (or a «Pass» button there) no longer starts a resize; the collapsed «Working now» rail scrolls instead of clipping dots and pushing the page.
- Pipelines: the «pipeline file not found» note for a run whose pipeline file is missing shows in a project with no pipelines too.
- Sessions: the pipeline chip keeps the stage name visible (only the run name ellipsizes) and the space before it.
- Structure: framework names up to 80 characters are kept, so a BE + FE value no longer cuts the FE badge.
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
- Structure: the architecture header no longer wraps into many lines at narrow widths — the «older than the code» notice moved onto the «Generated» badge (⚠ + tooltip) and the framework badge is capped with its full name in the tooltip; when it does wrap, badges spread evenly across the lines.

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

[Unreleased]: https://github.com/bugsterran/sidereus/compare/v0.18.0...HEAD
[0.18.0]: https://github.com/bugsterran/sidereus/compare/v0.17.0...v0.18.0
[0.17.0]: https://github.com/bugsterran/sidereus/compare/v0.16.0...v0.17.0
[0.16.0]: https://github.com/bugsterran/sidereus/compare/v0.15.0...v0.16.0
[0.15.0]: https://github.com/bugsterran/sidereus/compare/v0.14.1...v0.15.0
[0.14.1]: https://github.com/bugsterran/sidereus/compare/v0.14.0...v0.14.1
[0.14.0]: https://github.com/bugsterran/sidereus/compare/v0.13.0...v0.14.0
[0.13.0]: https://github.com/bugsterran/sidereus/compare/v0.12.1...v0.13.0
[0.12.1]: https://github.com/bugsterran/sidereus/compare/v0.12.0...v0.12.1
[0.12.0]: https://github.com/bugsterran/sidereus/compare/v0.11.0...v0.12.0
[0.11.0]: https://github.com/bugsterran/sidereus/compare/v0.10.0...v0.11.0
[0.10.0]: https://github.com/bugsterran/sidereus/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/bugsterran/sidereus/compare/v0.8.1...v0.9.0
[0.8.1]: https://github.com/bugsterran/sidereus/compare/v0.8.0...v0.8.1
[0.8.0]: https://github.com/bugsterran/sidereus/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/bugsterran/sidereus/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/bugsterran/sidereus/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/bugsterran/sidereus/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/bugsterran/sidereus/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/bugsterran/sidereus/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/bugsterran/sidereus/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/bugsterran/sidereus/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/bugsterran/sidereus/releases/tag/v0.1.0
