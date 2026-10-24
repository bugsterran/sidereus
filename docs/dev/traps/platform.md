# Traps — Platform, config, launcher, tests and tooling

Conventions (entry shape, `★` `⚠` `⇒`, `§N`, `:NNNN`): [TRAPS.md](../TRAPS.md). Newest first within an area; new traps go at the top of their area.

## Platform, config, launcher, tests and tooling

- **Hook connect: never edit an existing Codex group** (`sidereus/hook_connect.py`, #21).
  - Cause: Codex stores approval per `event:group:entry`; changing a group re-hashes it and silently disables the user's approved hooks.
  - ⇒ Missing entries go into one new group appended per event; the reply carries `approve:"/hooks"`.
  - ⚠Do not "tidy" by merging into the user's group or reordering — every original entry must stay in place.
- **`~/.cursor/hooks.json` is shared by Cursor CLI and the Cursor IDE** (`sidereus/hook_connect.py`).
  - Cause: both read the same user file, so a connected CLI also sends IDE agent events.
  - ⇒ Append only the Sidereus `command` entries; the user's IDE hooks stay untouched.
  - ⚠Never replace the file or drop unknown keys to "own" it.
- **A pipx/uv install cannot connect hooks** (`sidereus/hook_connect.py`, `setup.py` `BUNDLE`).
  - Cause: the bundle has no `ext-hooks/`, so there is no template or script path to write.
  - ⇒ `can:false, why:"no ext-hooks"`; manual setup in `docs/HOOKS.md` stays the route.
  - ⚠Do not write a path into the hook file that the install does not have — the CLI would run a missing script every event.
- **Cursor CLI hooks differ from the standard names** (`ext-hooks/ext_hook.py`, ★Cursor CLI 2026.10.22, macOS, 2026-10-24).
  - Cause: events are camelCase (`preToolUse`, `stop`, …); no base `cwd` (tool events send `""`); `cursor-agent -p` sends no `beforeSubmitPrompt`/`stop`.
  - ⇒ `EVENTS["cursor"]` = the codex map plus the camelCase keys (⚠keep the standard names: `--event <standard name>` configs use the same lookup); empty `cwd` = first absolute `workspace_roots` entry; no `session_id` = `conversation_id`.
  - ⚠Cursor reads stdout of `before*`/`preToolUse` hooks as a decision — never print there.
  - ⚠Never map `afterAgentThought`/`afterAgentResponse` (model text) and never forward `user_email` (rule 1).
  - ⚠A `-p` row stays in its last state until `sessionEnd`; do not invent a Stop for it.
  - ⚠Cursor has no record-file adapter (not in `PLAT_MODS`): its timeline row comes from `_ext` alone (`timeline_ext._hook_scan`, bars = hook event times). Without it the session reached the list but never the timeline.
- **Cursor tokens come only from the `stop` hook** (`ext_hook.build` → `ext_store._hooktok`, `ext-hooktok.json`).
  - ★Measured 2026-10-24: turn1 in 14645 out 28 cacheR 3968, turn2 in 14727 out 17 cacheR 3968 — per turn, not cumulative; new `generation_id` each turn; `-p` fires no hooks.
  - ⇒ Store keyed by `generation_id` (a repeated stop overwrites); kept 7 days across `sessionEnd`.
  - ⚠Cursor `input_tokens` assumed to exclude cache (unverified) — `tok` = in + out + cacheR + cacheW may double-count if it does not.
- **Codex mail wake uses the app-server socket without the experimental capability** (`ext-hooks/codex_wake.py`, 2026-10-21).
  - Cause: the wake talks to the app-server daemon socket (`/private/tmp/codex-daemon-$UID/<hash>`, WebSocket over a unix socket); ★0.163.0: injected turn ran in 17 s, all hooks fired, shown in the TUI. ★0.164.0 (2026-10-24): `initialize` with `capabilities: {}` — `thread/loaded/list`, `thread/resume`, `turn/start` respond identically with and without `experimentalApi`.
  - ⇒ Do not re-add `experimentalApi`; any failure (no daemon, thread not loaded, `codex exec`, Windows) = do nothing, «Mail waiting» is the fallback.
  - ⚠macOS `AF_UNIX` paths are capped at 104 bytes — do not build the socket path under a longer temp root.
  - ⚠Changing `~/.codex/hooks.json` (e.g. adding `--wake`) changes its hash: Codex skips the entry until re-approved with `/hooks`.
  - ⚠Only the session's own hook may connect to app-server; the Sidereus server never does (AGENTS.md rule 7).
  - ⚠Codex keeps appending turn-end rows to the rollout after the Stop hook returns, so the waiter takes its «typed» snapshot at the first check (`FIRST_S` = 3 s), not at spawn — a snapshot at spawn makes every waiter exit as typed. How late those rows can come is unmeasured.
- **A Codex rollout-only row is a guess** (`sidereus/ext.py` `ext_rollout_rows`).
  - Cause: without approved hooks there are no events, only a rollout file whose mtime moved in `ROLL_WIN_S` (600 s).
  - ⇒ State stays `unknown`, `rollout: True`, no `plm`/`plrun`/notes; skip `exec`/`subagent` rollouts, archived files, any sid in `_ext`/`_runs`/`_ext_ended` (ended, gone, dismissed), and a cached `ps` snapshot with no codex process.
  - ⚠Never fork `ps` here (read `live_probe._ps_snap_cache` only) and never give this row attention signals — it cannot know «waiting».
- **CODE_DIR is site-packages in a pipx/uv install** (`setup.py`, `mailbox_config.asset_dir`).
  - Cause: the wheel installs code flat, so CODE_DIR means «repo root» in a clone but «site-packages» when installed; `web/`, `hooks/`, `docs/` are not there.
  - ⇒ Read assets via `ASSET_DIR` (`asset_dir()`: CODE_DIR if it has `web/`, else `sidereus/_bundle`); `setup.py` copies an explicit allow-list into the bundle (`tests/test_wheel_build.py`).
  - ⚠Never glob the repo root into the bundle — it may hold live data (`bus.jsonl`, `identity.json`, `config.local.json`). A new asset read = one `BUNDLE` row.
- **A closed localhost port times out on Windows, not refuses** (`sidereus_cli.py` `answering`).
  - Cause: Windows retries the SYN to a closed 127.0.0.1 port for ~2 s, so the 2 s `/api/state` probe timed out and `start` reported a free port as BUSY and never spawned.
  - ⇒ On Windows a timeout is BUSY only when `port_bound()` (a probe bind on 127.0.0.1) fails; a free port returns 0.
  - ⚠Keep the timeout-is-BUSY rule for a bound port — a live `/api/state` can take >2 s; do not raise the probe timeout instead.
- **Orbit registry has no owner/mode check on Windows** (`plugins/orbit/scripts/accounts.py` `safe_owner`).
  - Cause: Windows has no `getuid`, and `st_mode` reports 0o666 for every writable file (ACLs are not mode bits), so the 0o022 check refused every registry.
  - ⇒ `os.name == "nt"` skips the mode check; protection rests on the default user-only ACL of `%USERPROFILE%`.
  - ⚠A registry under a shared or loosened-ACL home is trusted as is. Do not re-add the mode check for nt; an ACL check would need `win32security` (not stdlib).
- **Plugin cache keeps old versions; only `installPath` counts** (`sidereus/hook_diag.py`).
  - ★2026-10-14: `plugins/cache/omc/oh-my-claudecode/` held 3.7.2 on disk while `installed_plugins.json` said 5.6.2.
  - ⇒ Plugins come from `installed_plugins.json` `installPath` only, deduped by realpath; the cache folder is never walked.
  - ⚠Globbing `plugins/cache/*` would report hooks and versions Claude Code no longer runs.
- ⚠**The replay miner keeps only booleans and tags** (`scripts/plreplay_mine.py`). Fixtures are committed and shipped, and a transcript holds other people's prompts, commands and results (rule 1). ⇒ Text is regex-matched (tags, `_COMMIT_RE`, `BG_RE`, deny prefix) and dropped; ids, agent/skill names, cwd and the pipeline name are re-numbered; gate commands become `"gate"`. ⚠Do not add a field that copies text "for debugging" — the fixture would leak. The regexes are copies of `hooks/pl_flow.py`; `test_plreplay_mine` fails if they drift.
- ⚠**In bash, `$HOME` is the user's home, not `HOME`** (2026-10-07, `scripts/check.sh` evidence). Python `HOME` is `~/.mailbox-mcp`; a shell script writing under `$HOME/...` lands in `~`. ⇒ build data paths from `$HOME/.mailbox-mcp` (or an explicit override such as `SIDEREUS_EVIDENCE`).
- ⚠**The first-visit tour never auto-opens under headless/webdriver** (`98b-tour.js`) — otherwise its overlay lands in every `scripts/screen_check.mjs` shot. ⇒ `?tour=1` forces it, `?tour=0` suppresses it; the done flag is UIS `sidereus.tourDone`. ⚠Clearing that flag in a test browser does not open the tour without `?tour=1`.
- ⚠**Under pre-commit, `head` is the parent commit** (2026-10-07, «Results» rows). The gate runs before the commit exists, so `git rev-parse HEAD` names the commit it will sit on, and `dirty` is true. ⚠Do not read a pre-commit row's `head` as the commit that was checked.
- **Feature off: routes and remembered tabs** (2026-10-05). Cause: `/api/pick-folder` was in FEATURES.md but not in `features/pipeline.json`, so it stayed live with pipeline off; a remembered `mbMainView` of `pipe`/`retro` was restored without checking features, so the tab showed and its route 404'd. ⇒ `test_doc_routes_in_manifest` checks the docs table against the manifests; `buildMv` (92) falls back to the timeline and stores `mbTabsOff`, which the 05 restore skips; a retro 404 shows «The Insights feature is off». ⚠The first load after a feature is turned off still makes one 404 call, because `FEATS` only arrives with the first `/api/state`. That is accepted, because `mbTabsOff` covers later loads.
- ★**PATH separator is `os.pathsep`** (2026-10-03, `sidereus/ident.py` `rich_env` · `sidereus/usage.py`). Cause: `split(":")`/`":".join` cuts `C:\...` entries in two, so claude/ccusage/projcost children lose PATH on Windows. ⇒ `os.pathsep` everywhere; Homebrew dirs only on `IS_MAC`, POSIX `_BIN_DIRS` empty on Windows. ⚠Never hard-code `":"` in a PATH string.
- ★**Child processes on Windows: `CREATE_NO_WINDOW`, not `DETACHED_PROCESS`** (2026-10-03). Cause: a console child started with `DETACHED_PROCESS` gets a new console, so every poll flashes a window. ⇒ spawn the server with `CREATE_NO_WINDOW` (`sidereus_cli.WIN_SPAWN_FLAGS`); polled children inherit its hidden console. ⚠Do not combine the two flags.
- ★**Redirected child stdio on Windows needs `PYTHONUTF8=1`** (2026-10-03). Cause: a Python child writing to a pipe/file uses the ANSI code page, so Korean output raises `UnicodeEncodeError`. ⇒ set `PYTHONUTF8=1` in the child env. ⚠`encoding="utf-8"` on our side only fixes reading, not the child's write.
- ★**Hooks must not use `os.kill(pid, 0)` either** (2026-10-03). Cause: on Windows it calls `TerminateProcess` — a stale pid in a hook state file kills an unrelated process. ⇒ same `pid_alive` rule as the viewer. ⚠Applies to `hooks/` and `ext-hooks/` scripts, not only `sidereus/`.
- ⚠**`os.replace` may raise `PermissionError` on Windows while a reader holds the target open** (2026-10-03, unverified — no Windows run yet). ⇒ go through `_atomic_write` (retries). ⚠Confirm on a real Windows box before removing the retry.
- ★**Windows keep-awake is per thread** (2026-10-03, `sidereus/awake.py` `_win_hold`). `SetThreadExecutionState(0x80000001)` holds only while the calling thread lives/keeps it. ⇒ hold and release only from the `_awake_loop` thread; failure (exception or 0) reads as off with one soft warning. ⚠Calling it from a request thread leaks or misses the release.
- ⚠**Windows: `killpg` is missing** (2026-10-13, unverified on a real Windows box; `scripts/arch_checks.py`). Cause: `os.killpg`/`SIGKILL` raise `AttributeError` and `start_new_session` is ignored. ⇒ `_kill_tree()` runs `taskkill /F /T /PID`.
- ★**Codex MCP servers come from a TOML subset parser** (2026-10-03, `sidereus/plat_codex.py` `toml_mcp`): Python 3.9 has no `tomllib`. ⇒ only `[mcp_servers.<n>]` / `[mcp_servers."a.b"]` headers and the key names `command`/`url`/`enabled` are read; `[mcp_servers.<n>.env]` keys belong to the sub-table and are skipped. ⚠Inline tables (`mcp_servers = { … }`) and multi-line strings are not seen; never keep a value — args/env/url can hold tokens.
- ★**Gemini harness rows can flicker** (2026-10-03, `sidereus/plat_gemini.py` `harness_items`): interactive `gemini` and `/auth` rewrite `settings.json` and can drop `hooks`/`hooksConfig`. ⇒ read-only, re-read per request; hook `timeout` is milliseconds (shown ÷1000). ⚠`settings.json`/`config.toml`/`hooks.json` are never openable (`harness_plat.HP_NO_OPEN`, link name and target).
- ★**Feature toggles live in prefs `features` but not in the generic «Server» pane** (2026-10-01, `sidereus/features.py`).
  ⇒ `prefs.PREFS_OWN_PANE` skips it in `prefs_get` — every `PREFS` key otherwise renders as a free-text field in 90b-mypref.js.
  ⚠An off feature's modules still import and its web files still ship (PAGE byte-identical) — gate only routes, threads and state keys, never imports. ⚠A dep off forces dependents off; ids with no manifest are core = always on.
- ★**`~/.claude/settings.json`: two keys only** (2026-09-29, `sidereus/cc_settings.py`). Owner-approved as a settings option: `autoCompactEnabled`/`autoCompactWindow`, nothing else, ever.
  ⇒ `CC_KEYS` is the whole allow-list; every other top-level key/value/order is asserted identical to a fresh read, then to the re-parsed tmp; the file changing under us = 409.
  ⚠A running Claude Code may write the file back — the UI re-reads after 3 s and shows «Not applied». ⚠`burn_scan.py` still says «Never write settings.json» — it only reads; the writer is `cc_settings` alone.
- ★**Accounts: one save writes every account's settings.json** (`cc_settings._targets`/`cc_set`). Primary is planned first and is the reference: its refusal = 400 and nothing is written anywhere.
  ⇒ Extras get the same per-file guards; missing/unparsable/layout-refused/symlinked = `skipped`, a 409/500 on write = `failed`, reported in `files` and on the page as «Applied, but not to».
  ⚠Never create an extra's settings.json and never write through a symlink (deduped by realpath first, so a link to the primary is dropped, not skipped). ⚠The OTEL port stays primary only.
  ⚠The symlink skip checks `settings.json` only: an account dir that is itself a symlink to a folder outside the known roots is still written.
- ★**Re-serialising settings.json changed other keys' bytes** (2026-10-05, `cc_settings.cc_set`). `json.dumps(indent=2)` turned 4-space indent into 2, expanded one-line objects and escaped `é` into raw text — equal after parsing, not equal byte for byte. Out-of-range `autoCompactWindow` was clamped and stored with 200.
  ⇒ `_splice` replaces only the target value's span (absent key: appended after the last member, copying its indent and colon spacing); duplicate key or unparseable layout = 400, file untouched. `_v_win` refuses outside 50000..1000000.
  ⚠Never write the whole file back from a dict, and never clamp a settings value — the page confirms the exact number.
- ★**Windows `os.kill(pid, 0)` is not a probe — it terminates the target** (2026-09-28, Windows phase 1). ⇒ liveness goes through `pid_alive` (sidereus/config.py; `sidereus_cli.py` falls back to «gone» on Windows until it exists). ⚠Never write `os.kill(pid, 0)` in code that can run on Windows.
- ★**Launcher tab opens only on the run that created `config.local.json`** (2026-09-28, `sidereus_cli.py start`). ⇒ `cmd_start` calls `webbrowser.open` only when `ensure_config()` returned True. ⚠Do not open on every start — the user keeps one tab (rule 5), same reason the plist passes `--no-open`.
- ★**Launcher single spawn guard** (2026-09-28). ⇒ `start` spawns nothing when `/api/state` answers, and waits (no second spawn) while `sidereus.pid` holds a live pid still booting; `stop` kills only that recorded pid, only while it is alive and its port answers, and leaves a launchd/schtasks-owned viewer alone. ⚠Do not drop the answering check from `stop` — a reused pid would be killed.
- ★**Demo mode `--demo`** (2026-09-24, for README screenshots). `sidereus/demo.py install()` swaps `Handler._GET_ROUTES` · `_POST_ROUTES` in one place — only page paths are real, `/api/*` is a synthetic `World`, POST writes nothing. 0 background threads.
  - ⚠Every value must be invented — `tests/test_demo.py` scans every response against a real-name list (home path · real project names). If the list matches, fix the demo, never trim the list.
  - ⚠Times are relative to a base fixed once at install — if message `t` moves, incremental polling re-appends the same posts. `since` is `int()` (19-digit ns; as float the last post repeats).
  - ⚠`state.build` must equal `PAGE_BUILD` (else the «new version» toast). When the page starts using a new `/api/*`, add a synthetic response to `demo.respond` (default `{"ok":true}`).
  - Screenshots `docs/images/*.png` (1600×1000 framed · `!docs/images/*.png` in `.gitignore`) — retake with `node scripts/readme_shots.mjs [name…]` (own demo server + headless Chrome, en and ko). ⚠Never shoot the live viewer — README images are demo data only.
  - Hero GIF `docs/images/hero-{en,ko}.gif` (1120×700, ~10s loop) — `node scripts/readme_gif.mjs [--frames DIR]`. The demo run is static, so the script rewrites the change-flow `plrun` per step in the page (SESS + every `/api/state` reply); pure-JS GIF encoder, shared CDP helpers in `scripts/readme_cdp.mjs`.
- ⚠**Never measure «N hours ago» with playwright** — the audit context installs a fake clock, `Date.now` = `clock.now()` (measured 2 hours behind). The /work «last action · 4 hours ago» was this (data 18:57Z, really 6 hours ago — not a code defect). Check: `String(Date.now)`, compare with `performance.timeOrigin + performance.now()`.
- ★**Code paths and data paths differ** (2026-09-23 · open-source prep). Data = `MAILBOX_DIR` (default `~/.mailbox-mcp`) · code = the script's own location (`CODE_DIR`). In this install they are the same folder, so **mixing them goes unnoticed** — that is why 3 cursor/log paths originally keyed on code stayed undiscovered.
  - ⇒ Classify every new path as data or code. `HOME` in `chat_server.py` is an alias of `DATA_DIR` — **never use it for code.**
  - ⚠Backups accumulate on the **data side** in `backup/` (if code is a git clone they must not land there). `backup.sh` also bundles `hooks/` · `ext-hooks/` · `config.local.json` — without them a before/after comparison is impossible.
  - Check: without env, ~124 paths diff 0 before/after · with `MAILBOX_DIR` set only data moves · in a code copy only code paths move.
- ★**Identity, rooms and prefixes come from `config.local.json`** (2026-09-23 · internal names removed from code for open source). Loader `mailbox_config.py` · precedence env > config > generic defaults (`[]` · `general`).
  - ⚠**The watch daemon (`<label>.watch`; the prefix comes from config `launchd_labels`) starts without env** — the config file is its identity. Without the file it logs one warning and **watches nobody.** That is why `backup.sh` bundles it.
  - ⚠The cursor name (`stream-<id>.cursor`) is derived from identity — changing `self.ids[0]` restarts the cursor and skips earlier posts.
  - ⚠The MCP server imports 8 functions from `mailbox_core` — on failure it **silently falls back to substitutes.** Check there when renaming. Warnings must go to stderr (stdout is the MCP protocol).
  - Check (after restart): without env, `ME` (3 ids) · `SELF` (2 ids) identical before/after · self-tests 20/20 · daemon rooms and cursor base time identical.
- ★**Mac-only calls go through the `IS_MAC` (`:60`) gate** (2026-09-22 · 8 places: `ps` · `lsof`×2 · `ps -Ewwo` · `pmset` · `security` · `caffeinate` · `sysctl`).
  - On non-Mac only that feature turns off quietly (each function's existing «could not get it» value), no exceptions. Mac measured unchanged: `_ps_snap` 614 rows · `tool_busy` 2 · `boot_time` valid.
  - ⚠A gate, **not a replacement implementation** — on non-Mac the session list is empty. ⚠A new Mac-only command gets a line in the `:60` list comment too.
- ★**File saves go through one `_atomic_write` (`:73`)** (2026-09-22 · gathered 7 scattered tmp+`os.replace` sites).
  - ⚠Never call `os.replace` directly — use the wrapper. On Windows an open target raises `PermissionError`, and only the wrapper retries.
  - ⚠The wrapper takes **bytes only** (serialisation is the caller's) — `indent` · `separators` · `ensure_ascii` · gzip differ per site, and changing them changes the stored bytes.
- ★**Text I/O states its encoding** (2026-09-22 · portability · `docs/notes/multiplatform.md`).
  - 15 `subprocess(text=True)` + 12 text `open()` calls get `encoding="utf-8"`, reads also `errors="replace"`. Mac behaviour identical (measured: same normal UTF-8 output).
  - ⚠Keep `errors="replace"` — `encoding` alone is strict, raises on broken bytes and kills session detection entirely.
  - ⚠Not for the 2 `Popen` calls (`caffeinate` DEVNULL · `git cat-file --batch` binary) or `"rb"/"wb"` · `gzip` · `tarfile` — TypeError.
- ★**Writing an opening script tag in a Python comment (for `GET /api/structure`) broke the gate** (2026-09-22, structure treemap).
  Cause: the file itself embeds the screen JS in that tag, so «extract embedded script → `node --check`» scraped **Python comments and regex literals** as JS. `py_compile` does not catch it.
  ⇒ If the tag is needed, **concatenate pieces**, e.g. `_STRUCT_SCRIPT = re.compile("<" + "script>(.*?)</" + "script>", re.S)` (above `_struct_one_file` in `chat_server.py`).
  ⚠Past snapshots use **read-only git commands only** (`log` · `ls-tree` · `cat-file`) — one `git archive` snapshot is 78MB (measured on a large repo), and `checkout` · `stash` · `reset` break the user's working tree.
  ⚠Never put it on the poll — cold 2.4 s (Sidereus) to 3.3 s (560k lines). Minified files get line counts only, no function extraction (otherwise 2,572 one-line functions cover the treemap).
- **«Tools»/«Harness» counts showed «loading» ~22 s after every restart** — toolidx rebuilt its index from 90 days of transcripts (★10-03: 4.64 GB · 3,970 files · 21.6 s).
  ⇒ `toolidx-cache.json` keeps per-file offsets + events; restart = load 0.23 s + appended tails (★0.38 s, scanning false).
  ⚠Disk is used only while `CLAUDE_PROJECTS` is the real dir — a test that patches it but also wants the cache must patch `_TI_ROOT`/`TI_CACHE` to temp paths.
- ★**The toolidx cache load peaked at 489 MB** (2026-10-13, `sidereus/toolidx.py` `_load_disk`): v3 was one 80 MB JSON (894k events in 3,822 files, 80% hook runs; only 0.8% older than 90 days, so age pruning does not help), and `json.load` held the text and the whole tree at once.
  ⇒ v4 = header line + one line per file, `ev` grouped by key, read line by line, keys interned. ★Live-shaped fixture: file 75→64 MB, peak 476→191 MB, retained 283→191 MB, load 0.93→0.88 s.
  ⚠Never go back to `json.load` of the whole file, and never read a header without a bound: a v3 file is one 80 MB line (`readline(64)`).
- **Upstream record formats change silently** — Claude Code / Codex / Gemini rename a key and the parser returns empty, not an error; the screen just shows 0.
  ⇒ After a CLI upgrade run `/usr/bin/python3 scripts/fmt_probe.py` (exit 1 names the field). Unit tests use fixtures and cannot see this.
  ⚠Claude `model` is read only from lines that carry `usage` — a missing `usage` also blanks `model`. ★10-03: claude 8/8 · gemini 7/8 ok, codex skip (no files on this machine).
- **`plugin/` is generated** — `scripts/build_plugin.py` copies `hooks/` · `mcp/` into it; a hand edit there is overwritten, an edit only in `hooks/` leaves the plugin stale.
  ⇒ Edit `hooks/` and `mcp/`, then run `python3 scripts/build_plugin.py` (`tests/test_plugin.py` fails on drift).
  ⚠Never point the plugin source at the repo root — it copies live data (`bus.jsonl`, cursors, `config.local.json`) into every plugin cache.
- **`hooks/ev_hook.py` records nothing until its entries are in settings** — Sidereus may write only three `settings.json` keys, so the live `~/.claude/settings.json` needs the owner to add the Pre/Post/PostToolUseFailure `Bash` entries by hand (`sidereus setup-claude` prints them) or use the plugin.
  ⚠`PostToolUseFailure` (`error` = «Exit code N…», `is_interrupt`) is assumed from the hook schema — verify one live failing run writes `rc` N; if the event never fires, failures leave no row at all (PASS-only evidence).
  ⚠A sandbox-blocked run fails with a non-zero exit and is recorded as a real FAIL; a permission-denied call never runs, so no Post event and no row.
- **Plugin and `sidereus setup-claude` together register everything twice** — each hook fires twice and two `sidereus` MCP servers appear.
  ⚠Use one: the plugin, or the manual hooks/MCP that `setup-claude` prints. Switching = remove the other first.
- **An agent is keyed by its frontmatter `name`, not its file name** — the Agent tool's `subagent_type` is the frontmatter name, so `rev.md` with `name: reviewer` showed 0 runs in the harness while «Tools» named it «reviewer».
  ⇒ Every agent list goes through `toolinv.agent_name` (frontmatter `name`, else file name); `pipeline._agent_files` keeps the path server-side.
  ⚠Frontmatter keys are column-0 only (a nested `  name:` is not the agent's); config readers use `ctxsrc.read_text`/`_json_file` (leading BOM dropped) and type-check every value (`disabledMcpjsonServers` string, `env` list, top-level `[]`).
- **Old code name is not recognised — no fallback** (2026-10, code name renamed to Sidereus everywhere).
  - Cause: the old env vars, `X-*` headers, `python3 -m` module, launchd labels, schtasks task and MCP server/tool names were all renamed; nothing reads the old ones.
  - ⇒ Installs migrate by hand (CHANGELOG): set `SIDEREUS_*`, re-add the MCP server `sidereus` (or reinstall the plugin), re-run `--install-service`.
  - ⚠Browser prefs (`localStorage` keys `sidereus.*`) were migrated by a one-time data step, not code — do not add a key-migration shim for them.
  - ⚠`tests/test_no_old_name.py` fails on any tracked path or text containing the old name; do not add an allow-list.
  - The mark (`svg.brandmk#dot`, 93-header-toolbar.css) = the moon in Galileo's plate style, painted by `92e-moon.js` (every minute, minute-aligned + on tab return + on hover); by default it runs one full lunation per hour on the local clock (:00 new, :30 full; `moonHourAge`), Preferences «Moon mark» = «Real phase» (UIS `mbMoonReal`) draws today's moon. ⚠The tooltip always describes the real moon («Today's moon: …»), never the drawn hourly phase; `.off` = lit part dimmed + error outline; `.es` = earthshine (k < .15, about day 0-3 and 26-29): ashen night side with faint maria and a rim, so a thin or absent moon still reads as a moon at 28px (a plain dark disc read as a black dot). `#dot` gets viewBox 2 2 28 28 at paint (disc about 14% larger). The favicon is the static first-quarter plate.
  - ⚠The phase is a mean synodic month from one reference new moon: up to about ±0.75 day off near a real syzygy. Do not "fix" a one-day mismatch with an almanac; it is the model.
  - ⚠Northern-hemisphere view (waxing = lit on the right). The crescent clamp (`rx ≤ r-2.2`) is cosmetic so a 1-day moon still shows a sliver; it is not astronomy.
  - ⚠Mark colours are CSS variables on `.brandmk`; the light theme overrides variables only. A `html[data-theme=light] .brandmk .bmol` rule would outrank `.brandmk.off .bmol` and hide the offline outline.
  - ⚠The favicon data URI must end with `%3C/svg%3E` (once): `FAV_DOT` in `15-alarms.js` adds the unread dot by replacing it — a different ending silently drops the dot.
  - ⚠The favicon has no tile, so its rim is a mid tone (`#8a7a5f`); a dark rim vanishes on a dark tab strip and a light one on white.
- **Plugin `sidereus@sidereus`, MCP server `sidereus`** (`scripts/build_plugin.py` `NAME` vs `MCP_NAME`).
  - ⚠Renaming `MCP_NAME` changes tool ids `mcp__sidereus__*`, which sit in permission allow-lists, hooks and other sessions' configs.
- **Green-but-empty gate** (`scripts/check.sh` · `arch_checks --verify` · `arch_verify`) — a step that checked nothing reports «ok, 0 problems».
  ★10-12 a TS monorepo: a type checker ran on a solution-style config that checks nothing — 147 ms, 0 items, reported ok; after the fix 17 s.
  ⇒ Every step asserts its count > 0 (`need <step> <what> <count>` in check.sh → `FAIL … EMPTY: <what> — nothing was checked`; `tests/test_check_empty.py`).
  ⚠A 0 count (files, pipelines, T literals, shipped files, screen lines, «Ran N», tool items) is a failure — never read it as 0 problems.

## screen_check children die with node (`scripts/screen_check.mjs`)

- Cause: a SIGKILLed node (harness timeout) runs no handler, so detached demo servers and Chrome lived on (one for 1 d 09 h).
- ⇒ Demo and Chrome start behind a stdin-EOF watchdog; stale `screen-check-*` chrome/home dirs older than 10 min are swept at start.
- ⚠Unix only (same as the existing process-group kill). Two concurrent long runs could sweep each other's dirs.

## `sidereus start`: a 200 on the port is not proof it is ours (`sidereus_cli.py` `is_ours`)

- Cause: any Sidereus (another data dir) or app answering 200 on 8799 read as «Already running», exit 0, and its port was saved.
- ⇒ Every reply carries `X-Sidereus-Instance` (16-hex sha256 of the data dir realpath); a viewer without it counts as ours only when our `sidereus.pid` records a live pid on that port.
- ⚠A viewer started before this header existed reads as «taken» until it is restarted.

## Windows: Store `python3` alias and cp949 stdio (`hooks/pyrun.sh` · plugin `.mcp.json` · stdio entry points)

- Cause: `python3` on PATH is the Microsoft Store alias (`WindowsApps\python3.exe`, exit 49); every Python start costs ~0.5-1.5 s, so a probe that ran up to three of them overran the 10 s UserPromptSubmit timeout. Pipes and redirects use the ANSI code page (cp949 has no «—»), so `tools/list` and `setup-claude` died on their first write.
- ⇒ `pyrun.sh`: `SIDEREUS_PYTHON`, else a cache (`$CLAUDE_PLUGIN_DATA/sidereus-pyrun.cache` = PATH + exe; hit = shell builtins only), else probe `py -3`, `python3`, `python`, skipping any path under `WindowsApps` unrun. Plugin MCP `command` = `${SIDEREUS_PYTHON:-python3}` (★expansion verified on Claude Code 2.1.302). Stdio entry points reconfigure stdout to UTF-8 at start (`tests/test_stdio_cp949.py` runs the MCP server under `PYTHONIOENCODING=cp949`).
- ⚠MCP stdio is spawned with no shell: `pyrun.sh` cannot pick the server's Python and there is no per-platform config, so Windows users must set `SIDEREUS_PYTHON` (docs). Do not change the command to `py` — macOS/Linux have none.
- ⚠The probe writes `sys.executable` with `/` and no newline: a Windows `print` adds `\r`, which `$(...)` keeps and the cached path then never exists.

### Plugin update brings nothing when `version` is unchanged
Cause: Claude Code caches an installed plugin per `version` in `plugin.json`; `plugin update` with the same version keeps the old copy.
Fix: bump `VERSION` in `scripts/build_plugin.py` (then rebuild) in every commit that changes `plugin/`.
⚠ ★2026-10-17: version stayed 0.1.0 through three releases; the Windows hook fix did not arrive on a real PC after update.

### Parent-directory walks never end on Windows
Cause: `while p != "/": p = os.path.dirname(p)` — `dirname("C:\\")` returns `C:\\`, so the loop spins until the hook timeout.
Fix: stop when `dirname(p) == p` (`tests/test_hook_drive_root.py`).
⚠ ★2026-10-17: every prompt on a real Windows PC waited 10 s for `invite_notice`; CI did not catch it because no test walked up to a drive root.

### Codex `rate_limits` is often null on token events (`sidereus/plat_codex.py` `_rate` · `sidereus/ext.py`)
Cause: Codex writes `rate_limits: null` on many `token_count` events (Codex #14880), so the last event alone often has no limits.
Fix: the newest non-null `rate_limits` wins; windows past their `resets_at` are dropped, and `plan` is sent only with a live window. No window -> «No limit data» on Codex rows.
⚠Never fill a missing window, guess a percentage, or carry a value past its reset — the screen shows only what the CLI reported.
