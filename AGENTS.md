# Sidereus (viewer) — rules for working in this folder

Session control screen. `http://127.0.0.1:8799` · started by launchd `io.sidereus.viewer` (label = `<launchd_label_prefix>.viewer`; `python3 mailbox_config.py --label viewer` prints it).
**`chat_server.py` = entry point** (~250 lines: `Handler` core (send · guards · dispatch) · `main()` — route bodies are `sidereus/routes_get.py`·`routes_post.py`, `state()` is `sidereus/state.py`, PAGE assembly is `sidereus/page.py`) · **Python body is `sidereus/<domain>.py`**
(134 modules · order and ownership rules in `refactor/STAGE3.md`) · ⚠each global is owned by **one module only** — don't reassign another module's name, fix it in the owning module · **the screen is `web/`** — `index.html` (skeleton, `@@INCLUDE file@@` placeholders) +
`app-head.js` · `css/NN-*.css` · `js/NN-*.js` (per feature, `@@INCLUDE js/*.js@@` = concatenated in name order · NN is the order).
The server reads them at import and assembles an **inline PAGE with the same bytes** as before (`_load_page`). Feature ↔ file map: `docs/dev/FILEMAP.md` (was the web/ file map section of `VIEWER-HANDOVER.md`).
⚠Split JS files **only at top-level statement boundaries** (each file passes `node --check` on its own) · removing/adding a trailing newline changes the PAGE bytes.
⚠UI changes are made in `web/`. It is read once at import, so **a change only shows after a restart.**
`sidereus/attention.py` = ranking of «sessions that need me now» (`state().attention`, metadata only · top layer).
`sidereus/arch_checks.py` = security check results (loader); runner `scripts/arch_checks.py --category security` (tools never run in Sidereus).
No external libraries (must run offline). **Git: GitHub remote `origin`; the orchestrator commits, and pushes only when the owner asks · agents never push.**
**Branches: work is committed on `dev`; `main` is the published default branch and only moves by merging `dev` when the owner says so · releases are SemVer tags `vX.Y.Z` on `main` (CHANGELOG in Keep a Changelog form).**

## Direction

Refuse work that does not fit this; long form in `docs/CONCEPT.md`.

- **Identity**: a local observatory where one person verifies and judges the results and process of several AI coding sessions on one screen, and directs them by relaying instructions.
- **Core features = pipelines · timeline · structure analysis**: three views of the same sessions, linked; none is the lead. Gate evidence is what makes a verdict trustworthy — show it, not just the headline.
- **Goal**: a foundation to fork and extend, not a finished product. Extension PRs (language plug-ins, CLI adapters, pipeline templates) accepted · core PRs closed · bug reports welcome (`CONTRIBUTING.md`).
- **Never**: runs agents or attaches to terminals · shows conversation content · remote/enterprise monitoring · tied to one vendor (Claude Code, Codex CLI, Gemini CLI, …).
- **Filter for new work, in order**: fits the identity? → helps others extend it? → fixes a real defect? A «no» stops it.

```
restart   launchctl kickstart -k gui/$(id -u)/io.sidereus.viewer
check     curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8799/api/state
backup    bash backup.sh            # run after a change (keeps the last 10)
stderr    viewer.err                # ★append-only — old lines are fossils
```

## Break these and there is an incident

1. **Conversation content never goes on the page — metadata only.** Another session's conversation belongs to that user.
   A row carries only `path · session id · model · the agent's one-line task description (Agent tool description)` — never message bodies or tool input.
   Changing this rule is the owner's decision.
   - A subagent row may show the Agent tool `description` (the task, not only the agent name).
   - A resumed agent's label may use the latest SendMessage `summary` (one-line label from the parent) — never `message`.
   ⚠Message bodies appear nowhere (the description is only a one-line label passed by the parent).
   - The only exception = the **work-log popup** (`sidereus/work.py` `session_work`·`agent_work`, opens on click only · same allow-list as diff; owner-approved).
     ⚠Do not widen this exception to lists, timeline, cards or MCP.
2. **`HOME` is `~/.mailbox-mcp`** (`:42`), not the user's home. Check it every time you build a path.
3. **Two gates — both must pass before a restart.**
   - `for f in chat_server.py sidereus/*.py; do /usr/bin/python3 -m py_compile "$f"; done` — always `/usr/bin/python3` (3.9.6).
     **3.9 is the supported floor** (stock macOS python; the viewer itself may run a newer one — `scripts/deps_audit.py` shows which). Passing with another python lets syntax that 3.9 lacks slip in.
   - `for f in web/*.js web/js/*.js; do node --check "$f"; done`. The Python compile cannot catch JS errors.
4. **Verify on the screen.** Check the **rendered page**, not `/api/...` responses
   (an older handover said to verify with curl — that is stale; the API has been right while the screen was wrong more than once).
5. **Never open a new browser.** The user's tab is already open (`--no-open` in the plist).
   Opening `http://127.0.0.1:8799/` with playwright is fine.
6. **Documentation is required for every feature added or changed.** Traps go in `docs/dev/traps/<domain>.md` (index: `docs/dev/TRAPS.md`; was the traps section of `VIEWER-HANDOVER.md`).
7. **Sidereus = monitoring + relaying control.** It is not a read-only web page — it **relays** a person's instruction to a session, and the session executes it with its own permissions.
   - Allowed: sending instructions via the mailbox (DM · room) · signals the session reads itself, such as the mailbox-wide switch (`PAUSED`).
   - ⚠Send only what a person pressed — preview + confirm, no automatic sending. What was sent stays in the mailbox.
     Typed messages (chat box, work-popup composer) send on Enter with no extra confirm — the person wrote the text and the visible recipient is the preview (owner decision). Confirm stays for anything Sidereus composes for the person (pipeline run requests, invites, room admin).
   - ⛔No direct CLI connection (pty · tmux send-keys · process spawn/kill · stdin injection) · Sidereus itself never runs git write commands.
   - Rule 1 (metadata only) still holds — relaying goes outward; bringing conversation onto the page is still not allowed.
   - **Writing tool config is allowed** (owner decision — the feature set outgrew a read-only limit).
     Targets are only skill · agent · command files · MCP servers · hook settings (`~/.claude/` · project `.claude/` · `.mcp.json`).
     Also project `.claude/pipelines/*.json` (stage agent/model, and stage title with every in-file reference renamed in the same write; `sidereus/pipeline.py`; same guards). Owner-approved.
     ⚠Implemented today: only the pipeline files above and the `settings.json` keys below (`sidereus/cc_settings.py`). Skill · agent · command · MCP · hook writes are not built — the «Tools» view is read-only.
     ⚠Every write: preview (diff) + confirm · automatic backup before writing · viewer Origin required · paths outside the allow-list are refused · MCP `env` values are masked on screen.
     ⚠Delete never deletes — it moves the file to the backup folder (can be undone).
   - **Each account's `settings.json` (`claude_roots.accounts()`, primary `~/.claude/settings.json` first): three keys only** — `autoCompactEnabled`·`autoCompactWindow` (`sidereus/cc_settings.py`, Settings › «Preferences»; one save writes every account, or with «Per account» only the accounts whose values changed — an unchanged account is not written; an extra that is missing/invalid/symlinked is skipped, never created). Same guards per file (confirm · backup · Origin) + no other key changes by a single character. Owner-approved, exposed as a settings option.
     + `env.OTEL_EXPORTER_OTLP_ENDPOINT` (primary file only) — only its port, only in the same confirm as a «Port» save, only while it is the local `http://127.0.0.1|localhost:<port>` form (raw-byte replace). Owner-approved.

## When saver mode lifts, go back to delegating on the spot

★Recurring failure (3 days running): after saver mode ended, the main agent kept doing investigation and edits itself by inertia
and only delegated once told to.

- What failed was the **behaviour**, not the notice — the lift injection arrived correctly, and that turn still did all the grep · edit · verify directly.
- On seeing the saver-lift or subagent-default injection (`~/.claude/hooks/saver.py`), delegate **from the next investigation · edit · verification**.
  Do directly only «work where you already know where to look».
- ⚠If that notice keeps coming, it means **you have not fixed it yet** (`~/.claude/hooks/saver.py` repeats it up to 6 times
  until you actually delegate — calling Task/Agent stops it at once).

## Concurrent-edit protocol (put this in the brief when delegating to an agent)

`chat_server.py` and `web/*` are edited by several agents at once. Break this and someone else's work is lost — it applies per file.

- **No whole-file `Write`.** String-replacement `Edit` only.
- **Re-read** the spot right before editing. Find it **by content**, not by line number.
- **Agents do not restart the server** — the orchestrator does it once, at the end.
- Do not touch `__pycache__`.

## When testing

Skill `sidereus-test` (`.claude/skills/sidereus-test/`) — importlib load without starting the server · which module to patch · `bash tests/run.sh`. ⚠Tests never use live files, the clock or the network.

## Style

No emoji. `★` (evidence — measured numbers and their date) · `⚠` (trap) · `⇒` (fix) are this project's existing symbols.
Leave **why it was done this way** in comments — most defects here were «no evidence left, so the next person reverted it
in the opposite direction».
⛔**Code comments never quote the user or cite a conversation** (no «user said …», no request text, no dates of requests) — this is going open source.
Write the technical reason only. When editing a file, delete any such comment you find in it.

**New comments are written in English.** The goal is to publish as open source for others to fork.
Comments hold no Hangul at all (`tests/test_no_hangul_comments*.py`); quote a UI label by its English text.
- **UI strings are English-source**: code literals are English, Korean lives in `I18N.ko` (`web/js/06-i18n-*.js`), `T(s, ctx)` shows the source in English and the dictionary entry in Korean. `scripts/i18n_check.mjs` (in `--fast`) fails on a Korean UI literal or a T() literal without a ko entry. ⚠Never pass user data through `T()`.
- **Language by audience**: English for code comments, AI-read files (skills · agents · pipeline `task`/`rules`/`use` · workflows · hook messages to the model) dev docs (`docs/dev/*`) and **commit messages** (subject and body hold no Hangul — quote a UI label by its English source, e.g. «Workflow», never its Korean translation). Korean only in the `I18N.ko` dictionaries, pipeline stage titles (shown on screen) and the `.ko.md` user docs (README/GUIDE keep an English original).
- ⚠Evidence (`★`) and prohibitions (`⚠`) must **not be shortened** even in English — shorten the prose, not the evidence.
- The symbols (`★` · `⚠` · `⇒`) are used as-is in any language.

## Autonomous change flow

Runs one change request through requirements → design → implement → verify → review; the owner confirms only the criteria. Definitions: `.claude/agents/sidereus-*.md` · `.claude/workflows/sidereus-change.js`.

```
requirements (main)→ criteria R1..Rn + one Non-goal (skill requirements) · owner confirms once · no subagent
sidereus-designer   → spec (disjoint file slices · rules · tests · screen expectations · risks), read-only
sidereus-implementer→ one per slice, in parallel · reports after scripts/check.sh --fast passes
sidereus-verifier   → scripts/check.sh --full (gates · tests · leak scan · scripts/screen_check.mjs) · fixes nothing
                   on FAIL, back to that file's implementer (at most 2 times)
sidereus-reviewer   → reviews git diff against this file's rules · security (esc · path/arg checks · git_argv · metadata only) · simplicity
                   if blocking, implementer once → final verifier
```

- Run: Workflow `{name: "sidereus-change", args: "<request sentence>"}` — result is a summary + list of changed files.
- **Default = the pipeline, run directly**: follow `.claude/pipelines/sidereus-change.json` yourself with the Agent tool — stage order · agent · model · `skill` · `gate` · `onFail` — without the user pressing «Run» and without the Workflow tool (cheaper).
  Live verification sweeps (find defects on the running/demo screens, then fix) follow `.claude/pipelines/sidereus-verify.json` the same way.
  Each stage's Agent description starts with `[pl:sidereus-change/<stage title>]` (Sidereus lights stages from it; ⚠cut at 40 chars). Loop-backs and retries continue the same agent with SendMessage (its `summary` carries the same tag — the hook denies it otherwise). A small fix the user asks for directly may skip it.
  A stage the orchestrator does itself (restart · live check · commit): start the Bash description with the same tag — `~/.claude/hooks/pl-mark.py` records only pipeline/stage/time in `plmark/<sid>.json`, Sidereus lights it as «main» for 2 min, and dispatching a tagged Agent/SendMessage clears it (main is waiting, not working); `[pl:-]` clears it.
  **A stage that is not needed is skipped and the run goes on to the next one** — first run a Bash described `[pl-skip:<name>/<stage title>] <reason>` (`hooks/pl_flow.py` denies an undeclared jump every time), and name the skipped stage and why in one line of the report.
  Pass the stage agent as `subagent_type` and its model as `model` (denied otherwise; another model: Bash `[pl-model:<name>/<stage title>=<model>]`). While a run is open, every SendMessage summary carries its stage tag or `[pl:-]`.
  ⚠Start the session in the project that owns the pipeline file — Sidereus attaches a run by the session's cwd / repos (a run started in another folder showed nowhere). Stage work (verify, live check) carries its stage tag; `[pl:-]` is only for work outside the pipeline.
- Gates: `scripts/check.sh --fast` (implementers · before commit) · `--full` (verifier, screen regression) · structure rules in `tests/test_arch.py`.
- ⚠The flow **does not restart, commit or back up.** The orchestrator does it once at the end — skill `sidereus-ship` (gates → restart → 200 → live screen 900/1100/1440 → backup → commit; screen baseline `--update` is the orchestrator's decision).
