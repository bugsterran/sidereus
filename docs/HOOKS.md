# Hooks

**English** · [Korean](HOOKS.ko.md)

Claude Code hooks in `hooks/` hand mailbox mail and notices to a session. External CLI hooks in `ext-hooks/` report
another CLI's state so its sessions appear next to Claude's. See also [CONFIG](CONFIG.md),
[`ext-hooks/README.md`](../ext-hooks/README.md).

Every hook is standalone stdlib Python 3.9 and follows two rules:

- ⚠Never trap a session: any error, timeout or budget overrun exits 0 with empty stdout.
- ⚠Metadata only. The one exception is a Sidereus relay.

## Claude Code hooks

| Script | Event (matcher), timeout | Does |
|---|---|---|
| `mailbox_stop.py` | `Stop`, 5 s | hands new mail and relays over at turn end |
| `mailbox_wake.py` | `Stop`, `asyncRewake`, 6 h | waits in the background after each turn and wakes the idle session on new mail (no Monitor or watch.sh needed) |
| `invite_notice.py` | `SessionStart`, `UserPromptSubmit`, 10 s | room invites, unregistered id, wake notice |
| `pipelines_brief.py` | `SessionStart`, `UserPromptSubmit`, 5 s | lists the project's pipelines |
| `file_peers_notice.py` | `PreToolUse` (`Edit\|Write\|MultiEdit\|NotebookEdit`), 2 s | another live session edited this file |
| `pl_mark.py` | `PreToolUse` (`Task\|Agent\|SendMessage`, `Bash`), 5 s | records the main agent's pipeline stage |
| `pl_flow.py` | `PreToolUse` (`Task\|Agent\|SendMessage`, `Bash`, `Edit\|Write\|MultiEdit\|NotebookEdit`), `PostToolUse` (`Task\|Agent\|SendMessage`), 5 s | keeps a tagged run in stage order, hands off the next stage |
| `ev_hook.py` | `PreToolUse`, `PostToolUse`, `PostToolUseFailure` (all `Bash`), 3 s | records test/build/check/lint runs as harness evidence |
| `perm_mark.py` | `PermissionRequest` + `Notification` (`permission_prompt`), 5 s | marks the session as waiting on a permission prompt |
| `room_auto.py` | `SessionStart` | joins rooms by path from `room-map.json` (optional, not in the plugin) |

The plugin (`scripts/build_plugin.py`) registers the nine hooks other than `room_auto.py` (via `hooks/pyrun.sh`; on Windows that needs Git Bash). `python3 -m sidereus setup-claude` (Windows: `py -m sidereus setup-claude`) prints the
same nine hooks with this clone's paths; it never writes settings. ⚠Use the plugin or the manual blocks, not both (every hook would run twice).

⚠`pl_mark.py` and `pl_flow.py` are the only hooks that deny a tool call (plugin or manual), and only in a
project with `.claude/pipelines/*.json` (details below). Every other hook only adds context or writes a marker.

### Claude Code Stop hook

`mailbox_stop.py` serves sessions that do not run `watch.sh`. With mail waiting it prints
`{"decision":"block","reason":"..."}` so the model reads its inbox before going idle. The reason holds only the count
and senders (`bob(DM)`, or `bob(<room> r1)` with the Korean word for "room").

| Check | Rule |
|---|---|
| Id | `identity.json[cwd]`, exact key only; none means silent |
| Watcher | a live PID in `.watch-<id>.pid` means silent (the Monitor delivers) |
| Candidates | DMs to the id; posts by others in its rooms |
| Newer than | max(`read-<id>.cursor`, last t surfaced for this session, now − 6 h) |
| Not acked | no `kind:"ack"` by the id in `acks.jsonl` |

- ⚠It blocks only for a message newer than `last_t`, so a `stop_hook_active` retry exits 0.
- Two-phase when the input has `stop_hook_active`: a block keeps `last_t`/`relay_t` and stages the new values as
  `pending`. The next Stop promotes them (and writes the `hooked` rows) when `stop_hook_active` is true, or drops them
  when false — another Stop hook's `continue:false` overrides `decision:block`, so that reason never reached the
  model and the same mail blocks again. At-least-once: delivery is confirmed one stop later; Esc can repeat it.
  Without the key (other CLIs) it commits at once.
- ⚠Reads the last 512 KB of `bus.jsonl` and 256 KB of `acks.jsonl`; over 0.25 s it gives up. ★About 40 ms on a 3 MB bus.
- State: `.stop-hook/<session_id>.json` (`last_t`, `relay_t`, optional `pending` = `{last_t, relay_t, receipts, at}`), pruned after 7 days.
- `mailbox_wake.py` wakes only for mail newer than max(confirmed, `pending`); it then shows everything above the
  confirmed cursor and clears `pending`.

A relay is a bus row with `kind:"relay"` and `idSrc:"viewer"`: an instruction a person sent from Sidereus. It is
delivered with its body.

| Check | Rule |
|---|---|
| Target | `to` is the id; `sid` absent or equal to this `session_id` |
| Newer than | max(`relay_t`, now − 24 h) |
| Not seen | no `hooked` or `ack` for it. ⚠`delivered` does not count; a watcher writes it within ~1 s and only notifies. |
| Cap | 3 oldest per stop, 24000 characters in total; the rest waits, never cut. A body over 20000 (`DM_MAX`) ends with a Korean "truncated — read the full text with mailbox_inbox, id N" note. |

- Delivered even with a live watcher. Write order: `relay_t` (staged as `pending` when two-phase), stdout, then a
  `hooked` row in `acks.jsonl` (two-phase: at the promoting stop).
- ⚠A `kind:"relay"` row from any other source is ordinary mail.
- `POST /api/dm` takes `relay:true` only with the viewer's `Origin`, else 403. ⚠That stops an agent's casual `curl`,
  not same-user code, which can forge the header or append to `bus.jsonl`.

```json
{ "hooks": { "Stop": [ { "hooks": [ { "type": "command", "timeout": 5,
  "command": "<PYTHON> <MAILBOX_CODE_DIR>/hooks/mailbox_stop.py" } ] } ] } }
```

`<PYTHON>` in this and the `ext-hooks/*.json` examples: `/usr/bin/python3` on macOS, `py -3` (or a full `python.exe` path) on Windows.

Tests: `/usr/bin/python3 -m unittest tests.test_mailbox_stop -v` (Windows: `py -m unittest ...`).

### invite_notice.py

Prints only when there is something to say: new room invites, an unregistered id, or the wake notice (the last
two at `SessionStart` only). The wake notice is one line: `mailbox_wake` wakes the session on new mail, so do not start
Monitor or watch.sh; when woken, read with `mailbox_inbox`.

- Config `mailbox_watch = {"mode": "on"|"off", "projects": {"<abs path>": "on"|"off"}}` in `config.local.json`;
  missing means on. The longest matching project path wins.
- Off drops the wake notice only. ⚠No «watcher off» warning — Monitor is off by policy, so that state is normal.
- At `SessionStart` it also records session id -> Claude config dir in `acct/<session_id>` (metadata only, pruned after 30 days); the viewer uses it to tell accounts apart.

### pipelines_brief.py

At `SessionStart`, one line per `<cwd>/.claude/pipelines/*.json` plus how to run it, at most 2048 bytes. The «Apply»
setting (`pipeline_apply`) picks auto or ask-first, or turns it off. ⚠Never includes `task` or `rules` text.
On `UserPromptSubmit` it re-sends the brief only when pipeline names or stage titles changed since the session's last
brief (hash in `plbrief/<session_id>`).
This hook, `pl_mark.py` and `pl_flow.py` also read the pipelines of projects the session works in outside its cwd
when the cwd has none (git roots of Bash `cd` targets and transcript `cwd` in the transcript tail, never paths only read; cached in `plbrief/<session_id>.dirs`; the mailbox folder excluded). `pl_flow.py` also scans when the cwd has pipelines: if several projects own `<name>.json` it picks the best fit (stage title, stage agent = `subagent_type`) and keeps it for the run (`proj`).

### file_peers_notice.py

If another live session edited the file in the last 30 min, adds sid8, project, minutes ago and an uncommitted flag,
from `GET /api/agent/file`. Once per (session, file, peer) per 10 min. ⚠Advice only; viewer down means silent.

### pl_mark.py

A Bash description starting `[pl:<name>/<stage>]` writes `plmark/<session_id>.json`; `[pl:-]` or a tagged
Agent/Task/SendMessage clears it. Stores pipeline, stage, time and cwd only. The first Agent/Task without any
`[pl:` tag in a project with pipelines is denied every time with a «tag it or use `[pl:-]`» reason.

### pl_flow.py

Tracks each tagged pipeline run in `plmark/<session_id>.runs.json` (current stage, finished stages, slices in flight,
loop rounds, times; never descriptions or output). ⚠Never `<session_id>.json`, which `pl_mark.py` owns.

- Pre: a tag opens a run (none open, last one ended, or idle over 6 h). A jump forward past unrun stages
  (`onlyOnJump` stages excepted) is denied once per skipped stage; dispatching again passes. Earlier stages always pass;
  tagging the current stage's `onFail.goto` counts a loop round and returns to it (or `onFail.then`).
- Post: when the stage's last slice returns, adds `PASS → next: [pl:…] · agent · model · skill · gate` and, for a stage
  with `onFail`, the FAIL round line. A background dispatch says «when it finishes»; its Post (the only one it gets)
  takes its slice off the in-flight count but does not mark the stage done. After the last stage it ends the run and
  lists `after`.
- Untagged Bash Pre of the main session while a run is open: adds a reminder (run name and stage only) to tag
  stage work `[pl:<name>/<stage>]` or other work `[pl:-]`. Context only, never a deny; once per 10 min per run.
- `[pl-none:<category>]` in a Bash description (`small-fix` · `no-fit` · `explore` · `other`) declares the session's
  work outside every pipeline: `plmark/<session_id>.none.json` keeps only the category and time, never the reason.
  An unknown category is denied with the list. Without it and with no open run, the main session's first Edit/Write
  or untagged `git commit` in a project with pipelines is denied once, listing them; the retry passes. ⚠Manual
  setups need the `Edit|Write|MultiEdit|NotebookEdit` matcher for `pl_flow.py` (re-run `setup-claude`).
- The 3rd `[pl-none:no-fit]` of a project in 7 days adds context (count and project path only, never a deny) asking
  the model to offer a draft pipeline and write `.claude/pipelines/<name>.json` only after the user agrees; once per
  project per 7 days.
- Main's `git commit` closes this session's open runs of that project; a commit described `[pl:-]` closes none, one
  tagged `[pl:<name>/<stage>]` closes only `<name>`.
- Run end (last stage, `[pl-end:]`, main's `git commit`): if `<data dir>/eval/<repo key>/seeds.json` exists it starts
  `scripts/pl_eval.py score --auto` detached (no wait, no output); errors are swallowed and never block the call.
- Silent when «Apply» is off, the pipeline file is missing or bad, or the stage title does not match.

#### Guards (`hooks/pl_guard.py`, Claude Code only)

A pipeline file may set `"guards": {"requireGates": ["<stage>", …], "maxLoopBacks": 1..10}` (both optional; the
validators refuse an unknown stage, a listed stage whose `gate` is not graded, or a max out of range).

- Graded gates → evidence mode: `check.sh --fast` → `fast`, `--full` → `full`, `arch_checks.py --verify
  --category security` → `checks-security`.
- `git commit` (main or subagent) while this session's open run of that project has `requireGates` is denied unless each
  listed stage is done (not skipped) and `evidence.jsonl` has an `rc=0` row of its mode at or after the stage's last
  pass start, with no later failing row of that mode. The reason names the missing stages.
- `[pl-skip:<name>/<stage>]` of a `requireGates` stage is denied.
- After `maxLoopBacks` loop-backs the next loop-back dispatch is denied and the FAIL hand-off reads
  «loop budget n reached: stop and report».
- ⚠Fail-open: a missing guard module, bad pipeline or unreadable evidence never blocks; it reads gate, title, rc, mode
  and times only.

### ev_hook.py

Appends one `evidence.jsonl` row per matched Bash run, so the harness «Results» list fills in any project, not only where
`scripts/check.sh` runs. Row: `mode` (`hook-<kind>` or `gate-<kind>`), repo, short commit, dirty, `rc`, one step
(kind, rc, seconds).

| Matched (after an optional `cd X &&`) | Kind |
|---|---|
| `./gradlew`/`gradle` `test`·`build`·`check`, `mvn test`·`verify` | test · build · check |
| `npm`/`pnpm`/`yarn` (`run`) `test`·`build`·`lint` | test · build · lint |
| `pytest`, `python -m pytest`, `go test`, `cargo test`·`build` | test · build |
| a `gate` string of `<repo>/.claude/pipelines/*.json` (whitespace-normalised) | `gate-*`, step `gate` if no kind word |

- Skipped: `|`, `;`, `&&` after the command, a trailing `&`, `--watch*`, `--continuous`, `-t`, any `check.sh`
  (it writes its own row), `run_in_background`, interrupted runs.
- `rc`: 0 on `PostToolUse`; on `PostToolUseFailure` the number in a leading «Exit code N», else 1.
- ⚠Metadata only: never the command, stdout/stderr or error text. Seconds come from `evstart/<tool_use_id>` written
  at `PreToolUse` (missing = 0, older than 1 h swept).
- `SIDEREUS_EVIDENCE` overrides the file, like `check.sh`. ★An unmatched command costs about 40 ms.

### perm_mark.py

Writes `permwait/<session_id>.json` (`sid`, time) when Claude Code shows a permission prompt; Sidereus shows «waiting for approval» while
it is newer than the session's last transcript activity. `PermissionRequest` fires as the dialog opens; the
`Notification` registration is the fallback. ⚠Claude Code sends the notification about 6 s after the dialog opens (none if
answered sooner). Never the message, title or tool input; prints nothing.

Marker format: main `permwait/<sid>.json` = `{sid, t[, tool]}`; a subagent's event (has `agent_id`) writes
`permwait/<sid>.<agent_id>.json` = `{sid, t, k, aid[, tool]}` (`k` = `req` | `perm` | `elicit`). `tool` is the
`PermissionRequest` `tool_name` only; a main `Notification` within 15 s keeps it. A sub marker is compared with that
agent's own activity, so it shows «subagent waiting for approval» whatever the main row is doing. Sub markers older than
7 days are pruned on the next write. Old `{sid, t}` markers still parse.

## Coexisting with other hooks

Claude Code runs every hook on an event; outputs are combined and a `deny` from any `PreToolUse` hook wins.

| Hook | Can do | Another hook on the same event wins or also blocks | Off switch |
|---|---|---|---|
| `mailbox_stop.py` | block stop (mail count, senders; relay bodies) | `continue:false` elsewhere: see [two-phase](#claude-code-stop-hook), mail comes again next stop. Another block: both reasons reach the model | remove from settings (silent for a cwd without an id in `identity.json`) |
| `mailbox_wake.py` | wake an idle session (exit 2) | not affected; it waits in the background (exits at once under `claude -p`/SDK, which would wait for it; SDK-hosted sessions get mail at their next Stop via `mailbox_stop.py`, no idle wake) | remove from settings (same cwd rule) |
| `invite_notice.py` | inject context | a blocked prompt loses the line; invites already shown are not repeated on prompts, only at the next `SessionStart` | `mailbox_watch` off drops the wake notice only; `identity-skip.json` drops the unregistered notice |
| `pipelines_brief.py` | inject context | a blocked prompt loses the brief; resent at the next `SessionStart` or pipeline change | `pipeline_apply` off |
| `file_peers_notice.py` | inject context | a denied edit still counts as noticed (10 min per file and peer) | remove from settings (silent while the viewer is down) |
| `pl_mark.py` | deny tool (untagged Agent/Task), record mark | its deny wins over an allow; if another hook denies, the mark is already written or cleared | `pipeline_apply` off stops the deny; marks are still recorded |
| `pl_flow.py` | deny tool (stage order, agent/model, tag), inject context (Post) | its deny wins over an allow; if another hook denies a dispatch, the run has already moved to that stage and re-dispatching it passes | `pipeline_apply` off |
| `ev_hook.py` | nothing, records | a denied run writes no row (its `evstart` marker is swept after 1 h) | remove from settings (`SIDEREUS_EVIDENCE` only moves the file) |
| `perm_mark.py` | nothing, records | not affected | remove from settings |
| `room_auto.py` (optional) | inject context (one line on a new join) | not affected | no `room-map.json` entry for the path |

★ Checked live with no conflict (2026-10-11): oh-my-claudecode 5.6.2, superpowers 7.0.0, hookify 0.1.0, ralph-wiggum 1.0.0, security-guidance 2.0.0, claude-mem 13.35.0 — a dated observation, not a compatibility promise.

**Reporting a conflict.** Attach to the issue: the `/plugin` installed list; the `hooks` block of `~/.claude/settings.json`
and of the project `.claude/settings.json` (event, matcher and command only, no `env` values or secrets; redact tokens and paths inside hook commands); the Claude Code
version (`claude --version`); the Sidereus commit (`git rev-parse --short HEAD`).

## Diagnostics (Settings)

<details><summary>What it shows and how «silent» is judged</summary>

Settings › «Diagnostics» (`GET /api/diag`, feature `diag`) reads every account's settings, installed plugins and known
projects, and shows: hooks on the same event as a Sidereus hook (source plugin/user/project, name, account, matcher,
script basename) · plugin hooks whose output Claude Code does not read · installed plugin versions · projects where
`CLAUDE.md` hides `AGENTS.md` (both exist, and `CLAUDE.md` neither links to `AGENTS.md` nor has `@AGENTS.md` in its first 4 KB).
It is read-only and fixes nothing.

⚠«Silent» is a static estimate: the script (≤ 64 KB, only under the plugin's `installPath`) is read, never run.
Keys of the object passed to `JSON.stringify`/`json.dumps` on stdout are compared with this table:

| Event | Fields Claude Code reads |
|---|---|
| every event | `continue`, `stopReason`, `suppressOutput`, `systemMessage` |
| `PreToolUse` | `hookSpecificOutput.{permissionDecision, permissionDecisionReason, updatedInput, additionalContext}`, legacy `decision`, `reason` |
| `PostToolUse` | `decision`, `reason`, `hookSpecificOutput.{additionalContext, updatedMCPToolOutput}` |
| `UserPromptSubmit` | `decision`, `reason`, `hookSpecificOutput.additionalContext` |
| `Stop`, `SubagentStop` | `decision`, `reason` |
| `SessionStart` | `hookSpecificOutput.additionalContext` |
| `PermissionRequest` | `hookSpecificOutput.decision.{behavior, updatedInput, message, interrupt}` |

Verdicts: **silent** = JSON goes out, at least one key is unread, the rest are no-ops (`continue:true`, `suppressOutput`)
and there is no exit-2 path · **partial** = read and unread keys mixed · **ok** · **unknown** = binary, unresolvable or no
JSON output found (other events are always unknown).

</details>

## External CLI hooks

The CLI runs `ext-hooks/ext_hook.py --platform <key>`, which maps the stdin event to a standard name and POSTs it to
`/api/hook`. The viewer keeps the last event per `(platform, session_id)` as a row.

`--platform` must be a key of `EXT_PLAT` (`sidereus/ext_store.py`): `gemini`, `codex`, `copilot`, `cursor`, `cline`,
`windsurf`, `warp`, `trae`, `zed`, `openrouter`, `grok`, `deepseek`, `qwen`, `kimi`, `mistral`, `ollama`,
`perplexity`, `huggingface`, `meta`. ⚠`claude` is not one; Claude sessions come from transcripts.

| Event | State | Gemini name | Codex name |
|---|---|---|---|
| `SessionStart` | `wait` | same | same |
| `UserPromptSubmit` | `think` | `BeforeAgent` | same |
| `PreToolUse` | `tool` | `BeforeTool` | same |
| `PostToolUse` | `think` | `AfterTool` | same |
| `Stop` | `wait` | `AfterAgent` | `Stop`, `Interrupt` |
| `Notification` | `ask` (blocked) | same | `PermissionRequest` |
| `SessionEnd` | row removed | same | same |

- Other platforms use the Codex mapping. ⚠Only Gemini and Codex were checked; otherwise pass `--event <name>`.
- The blocked mark and «needs me» badge stay until the CLI's next event, `SessionEnd` or a dead pid — never by age.
  Any other row silent for 24 h (`EXT_TTL_S`) is deleted. Rows survive restarts (`ext-sessions.json`).
- A hook row has no transcript, cost, context or git data and no resume chip. The model name is cut to 20 characters.

`ext_hook.py` options: `--platform` (required), `--event`, `--url` or `SIDEREUS_HOOK_URL` (default port: `SIDEREUS_PORT` >
config `port` > 8799), `--dry-run` (body to stderr), `MAILBOX_DIR` (log location). It forwards `session_id`, `cwd`,
`transcript_path`, `model`, `tool_name`, `turn_id` when they are non-empty strings, and `parent` from
`SIDEREUS_PARENT_SID` or `CLAUDE_CODE_SESSION_ID`. The server requires `session_id` and caps the body at 1 MB.

⚠stdout stays empty (CLIs read it as control JSON), exit is always 0, a dead viewer costs at most 2 s. Failures go to
`ext-hooks/.ext-hook.log` (200 KB cap). `bash ext-hooks/demo.sh` adds three fake rows; always run `demo.sh clean` after.

### Gemini CLI

Merge `ext-hooks/gemini-settings-example.json` into `~/.gemini/settings.json` (or `$GEMINI_CLI_HOME/.gemini`),
replacing `<MAILBOX_CODE_DIR>`. Timeouts are in ms. `AfterAgent` also runs `gemini_mail_stop.py`, which applies the
Stop hook rules above; Gemini sends `reason` as a new prompt. `gemini_mailbox_mcp.sh` starts the mailbox MCP.

- Id: `identity.json["gemini:<physical cwd>"]`, else `<folder>-gemini`. ⚠Never `identity.json[cwd]`: that is the
  Claude session in the same folder, and reading its inbox would take its mail.
- ⚠The id is set in a script: Gemini expands `$VAR` in settings at load time, which blanked inline shell to `anon`.
- ⚠An interactive `gemini` (and `/auth`) can rewrite `settings.json` and drop hooks; recheck `hooks.AfterAgent`.
- `gemini -p` in an untrusted folder exits 55 (use `--skip-trust`). A personal Google login is refused
  (`IneligibleTierError`, 0.61.0); use an AI Studio key.
- ★End-to-end 2026-09-24: one block, inbox, reply "pong", ack.

<details><summary>Worker mode: an idle Gemini waits for mail</summary>

Worker mode (`touch .mail-worker` in the folder, or `SIDEREUS_MAIL_WORKER=1`) keeps an idle Gemini waiting for mail:
at turn end with nothing pending it blocks with «`mailbox_wait`, do the task, reply on the same thread».

- Each round is `mailbox_wait(timeout_s=3540, round=N)`. Set `mcpServers.mailbox.timeout` above it (e.g. 3600000 ms).
- ⚠Unattended runs need `"trust": true` on `mcpServers.mailbox`.
- ⚠The loop detector stops 5 identical calls (hence a fresh `round`) and judges loops after 30 turns; long runs need
  `{"model": {"disableLoopDetection": true}}` in the worker folder.
- ★About $0.024 per empty round, one per hour. After `SIDEREUS_MAIL_WORKER_MAX_IDLE` (3) empty rounds it goes idle.
- ⚠While waiting the TUI shows «Running a tool»; it is not hung. ⚠The worker folder decides what it can read.
- Gemini only. Codex ignores `.mail-worker`: it waits in the Stop hook instead (below), with no model call per round.

</details>

`ext-hooks/ask-gemini "task"` runs `gemini --skip-trust --approval-mode plan -p` as a read-only subagent from a
Claude Bash call. It is killed after `ASK_GEMINI_TIMEOUT` (600 s, exit 124) or `ASK_GEMINI_STALL` (180 s without
chat-file growth, exit 125). It shows as a child row of the calling session (`ext-runs.json`: 200 runs, 7 days).
⚠Plan mode denies `web_fetch` unless a `--policy` allows it. ⚠A run from a subagent shows under the main session.

### Codex CLI

Copy `ext-hooks/codex-hooks-example.json` to `~/.codex/hooks.json`. Checked with Codex 0.156.1; timeouts in seconds.

- ⚠Codex ignores the entries until approved with `/hooks`, and again after every edit (it stores a hash). Do not
  default to `--dangerously-bypass-hook-trust`.
- `PermissionRequest` marks the row blocked; the script prints nothing, so Codex still asks you.
- Mail wake (`--wake`, the example's default, timeout 5): `Stop` spawns a detached waiter (`ext-hooks/codex_wake.py`)
  and returns at once. When mail arrives it starts one turn on the session's own thread through the local Codex
  app-server socket; the turn text is the «[mailbox] N new mail …» line (ids and a count only). Typing first makes the
  waiter exit. No daemon, a thread not loaded in it, or `codex exec` = nothing happens; «Mail waiting» is the fallback.
  Set `default_tools_approval_mode = "approve"` on `[mcp_servers.mailbox]` (`ext-hooks/codex-config-example.toml`):
  only the mailbox tools are auto-approved, shell and other approvals are unchanged; restart the session after editing.
  ⚠Experimental app-server API (★checked on 0.163.0, 2026-10-21: turn ran in 17 s, all hooks fired, shown in the TUI).
  ⚠macOS/Linux only; on Windows nothing is spawned.
- Idle wake by blocking (**opt-in, unattended sessions only**): replacing `--wake` with `--wait` (set timeout 3600) waits on `bus.jsonl` for up to 59 min
  (`SIDEREUS_MAIL_WAIT_S`, 60-3540) and blocks with the mail line when mail arrives; no mail = exit 0, no output, no
  model call. Re-approve with `/hooks` after the edit.
  ★0.163.0 (2026-10-20): no cap on a sync Stop wait (default 600 s, 3600 accepted); a timeout ends the turn cleanly;
  a block continues the same turn.
  ⚠The wait runs after every interactive turn: the TUI shows «Working · Running hook» and a typed prompt only queues
  (Codex does not cancel the hook) until mail, the timeout or Esc. ★Measured a 1884 s dead gap inside one turn; Codex
  looked hung on simple requests. Never make `--wait` the default for an interactive Codex.
  ⚠After 59 min the turn ends; waiting resumes only after the next prompt (the attention signal covers the gap).
  After `SIDEREUS_MAIL_WAIT_MAX` (20) wakes without a human prompt it stops waiting until you type.
  ⚠`codex exec` never waits: the rollout's `session_meta` (originator `codex_exec` / source `exec`) skips it, and so
  does an unreadable rollout.
- Optional `SessionStart` notices: `<PYTHON> <MAILBOX_CODE_DIR>/hooks/invite_notice.py --platform codex` (timeout 10) and
  `<PYTHON> <MAILBOX_CODE_DIR>/hooks/pipelines_brief.py --platform codex` (timeout 5). Codex wording: mail arrives at
  turn end through the `Stop` hook (id `codex:<cwd>` key or `<folder>-codex`), and stages are run in order by the session
  itself with `echo "[pl:<name>/<stage>]"` / `[pl-end:...]` shell markers. ⚠No flag = Claude wording (`mailbox_wake`,
  Agent tool); the flag is the only signal, the payload is not used to guess. On 0.163 `SessionStart` fires with the first turn.
- Without hooks (not yet approved) a Codex session whose rollout changed in the last 10 minutes still gets a row,
  marked «Hooks not connected»: folder and model only, state unknown. Once hook events arrive the hook row replaces it.
- `sidereus/plat_codex.py` reads tokens, model, cost and rate limits from `$CODEX_HOME/sessions/**/rollout-*.jsonl` and
  `archived_sessions/`, never message text.
  ⚠`input_tokens` includes cache (split out); requests sum `last_token_usage`, not the total.
  ⚠`.jsonl.zst` is skipped. ⚠Cost is an API list-price estimate. ⚠Limit % needs `rate_limits`, often null (#14880).
- Codex tokens and cost never count in Claude's totals.

Other platforms: `ext-hooks/generic-hooks-example.json` with `<PLATFORM>` replaced, wherever that CLI reads hooks
(not verified per CLI).
