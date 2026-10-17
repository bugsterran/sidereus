# Traps — Branch tab, git and history

Conventions (entry shape, `★` `⚠` `⇒`, `§N`, `:NNNN`): [TRAPS.md](../TRAPS.md). Newest first within an area; new traps go at the top of their area.

## Branch tab, board, git and worktrees

- ★**Diff window «Include untracked files» (`untr=1`) is opt-in and capped** (2026-10-17). Cause: the blanket untracked list once buried real changes under build/ and logs (08-25 decision).
  - ⇒ `git_diff(..., untr="1")` appends `_untracked_patch` for at most `DIFF_UNTR_MAX` = 40 status paths, only for scope `work` or `b:<sha>`; pref `sidereus.dfUntr` (35c).
  - ⚠Each path still goes through `_untracked_patch` (literal pathspec · realpath inside root · no symlink · `ls-files --others` · 1 MB read cap). Keep the `git_rail` import lazy — git_rail imports git_view.
  - ⚠«Since session start» / «vs main / master» ask `view=rail&base=start|remote` once and load `b:<sha>`; no base back = «Uncommitted», never «All». A repo tab click re-asks — a baseline sha belongs to one repo.
- ★**Picker listed a repo the server refused («This repository is not in the list»)** (2026-10-15, 403 on `/api/branches`). Cause: the picker (`brRepos`) collects repos from every session row, while `_branch_ok` used `_allowed_cwds()`, which keeps one row per cwd and drops repos of earlier sessions in it ⇒ `_branch_ok` builds its set from every `sessions_rows()` row, like `git_diff`. ⚠The picker and the server gate must derive the repo set from the same rows; never gate repos through `_allowed_cwds()`. Test `tests/test_branch_allow_rows.py`.
- ★**Committed but unpushed files showed as «Conflict»** (2026-09-25, `base=remote`). Cause: the `git_rail` conflict check looked only at status presence, so committed files matched ⇒ `_status_tracked` (git_rail.py:244) makes only **uncommitted** files conflict candidates (same rule as file_owner.conflicts). ⚠Copy this rule into any new conflict check — never judge by status presence alone.
- ★**file_owner edit counts accumulated for life** (2026-09-25). Numbers never dropped as sessions aged, so «who edited most» was meaningless ⇒ `_FO_N` keeps edit timestamps (cap 500) and counts only within the `FO_KEEP_S` (24h) window (file_owner.py:137).
- ★**The viewer's `git status` rewrote the watched repo's `.git/index`** (2026-09-25 review; index mtime changed after a stat-only `touch` · unchanged with the flag). While writing it holds `index.lock`, so an agent's `git add`/`commit` can fail with «index.lock: File exists» ⇒ every git process runs with `gitinfo.git_env()` (`GIT_OPTIONAL_LOCKS=0`) — `_git_run` uses it, and direct spawns (structure · structure_snap) pass `env=git_env()`. ⚠New git calls use `_git_run` or add `env=git_env()`. Test `tests/test_git_optional_locks.py`.
- ★**A git slot miss is never cached** (2026-09-25 review). Polling `_git_state` waited 1.5 s per slot, so state() grew with the cwd count (10 ≈ 15 s), and the failure value `""` was cached 20 s, making chips look clean; warm-up overwrote a good cache with a «0 worktrees» result that had swallowed a `worktree list` timeout ⇒ `_git_state` uses `wait=0` and returns the previous value on a miss (no cache write) · `branch_graph` does not cache if any sub-call hit `TimeoutExpired` (`miss`) (warm = keep the previous entry; user request = answer once, uncached) · `_br_seen_note` file writes happen inside the lock. ⚠Even when the «extras» fallback `except Exception` swallows a timeout, record it in `miss`. Test `tests/test_git_slot_miss.py`.
- ★**Parallel work = copy only** (2026-09-24, `docs/PARALLEL-WORK.md`). Branch tab «＋ Parallel work» → `cd '<main>' && claude -w <name> --tmux`; a non-main worktree card with no session, «Cleanup cmd» → `git -C '<main>' worktree remove '<path>'` (89-branch-worktree `brPw*` · `brWrmHtml`, strings 06-i18n-f).
  - ⚠Only names matching `^[a-z0-9._-]+$` are copied (the pasted command is parsed by a shell). Paths always single-quoted via `brQ`. An existing worktree name or local branch `<name>`/`worktree-<name>` only warns.
  - ⚠No run endpoint, POST or `--force`. Uncommitted changes only warn; git is left to refuse. `tests/test_parallel_work.py` (node).
  - ⚠`setTheme`'s `full()` overwrites `#feed` with chat even on the branch tab (existing defect · if this form vanishes, this is why).
- ★**Parallel work = git-flow by default** (2026-09-24). Form kind (feature · bugfix · release · hotfix) + name → `git -C '<main>' worktree add '<main>.wt/<kind>-<name>' -b '<prefix><name>' '<base>' && cd … && claude`. Last option «claude -w (from HEAD)».
  - Server `sidereus/git_view.py flow_parse` (one `git config --get-regexp '^gitflow\.'`, inside the `branch_graph` cache) → payload `flow`. develop = configured value or local `develop`, else null → form «no develop — branching from main».
  - Card ↑↓ base = `wt_base`: feature/bugfix → develop, release/hotfix → master (+PR «main · develop»), otherwise the main checkout's branch. ⚠If the base is not a **local** branch, the old rule applies (no fetch).
  - ⚠Names starting/ending with `.`, containing `..` or `.lock` are refused by git → blocked before copying. Tests `tests/test_gitflow.py` · `test_parallel_work.py`.
  - ★**develop/main only on a remote** (fresh clone): `flow_info` uses `for-each-ref refs/remotes/*/<name>` to take `origin/…` (else the first remote by name) as base (`devRemote` · `mstRemote`). PR targets are bare names (`develop` · `main`); commands add `--no-track`; form «no local branch — branching from remote {m}».
- ★**Branch tab «work unit» = worktree ↔ session** (2026-09-23 · Paseo 1:1 model). Server `_worktrees` (third git call in branch_graph) · session row `wt`=`_wt_of` (root · main · name) · `/api/git/wtfiles` (uncommitted, `_branch_ok`).
  - ⇒ Screen `brWtHtml` (sessions per worktree above the list) · `brWuHtml` (session+sub → `wkPopup`, recent commit → `brJump`, file → `loadDiff`) · sidebar chip `worktree: <name>` → `brWuJump`.
  - ⇒ «open all work logs» `brWuOpenAll` → `/work?…&lay=&more=cwd\ttid\n…` (1 · h2 · c3 · g4, max 4). ⚠Layout lives in memory only — never overwrite `mbWtLayout`.
  - ⚠Compare paths with `brNorm` — the server uses realpath (`/private/tmp`), session cwd may be `/tmp`. Matching is **longest prefix** — the main checkout contains `.claude/worktrees/*`.
  - ⚠Sessions sharing a cwd open as `sess:<cwd>|<sid>` (`brSessTid`). Poll hook `brWtTick` does not repaint while the mouse is over the pane (it swallows a click in progress).
  - ★**Work-unit signal line** (2026-09-24 · the layer that differs from Paseo). Server `sidereus/git_wt.py` `wt_signals` (`wtSig` · `wtTok` · `wtStaleDays` on the branch_graph result, sharing the 20s cache) · screen `brWtMeta` · `brWtOrder` · `brWtAttn`.
    - Tokens = `byc` (5-min buckets keyed by sid · subagents already carry the parent sid) → `_sid_roots` (sessions() rows + `_WT_SID` memory) → `_wt_pick` longest prefix. Share % denominator = the whole current cycle (`quota_who` start).
    - Today = `_WT_DAY` copies byc buckets (byc keeps only ~5h) — 60s folder thread (started on first call). ⚠If coverage starts after midnight, show `~` (`dayPartial`).
    - Health = per worktree `status -uno` + `rev-list --left-right --count <main branch>...HEAD` (no fetch, first `WT_HEALTH_MAX`=12 only) · last commit = for-each-ref ts. Stale = 0 running sessions + `chg` older than `WT_STALE_DAYS` (7) days.
    - Sort = attention score → running sessions → recent activity. ⚠`wt_sort_key` (py, tested) and `brWtOrder` (js) are the same rule — never change one alone. Attention chip click → `cpGo`.
    - ⚠Use `sessions()` — `_allowed_cwds()` has one row per cwd, so other sids in the same cwd drop out.
    - ★Rows use the poll's `sessions_snapshot(WT_SNAP_S=60)` — calling directly costs 0.25–1s per miss (measured 09-24: miss 913→54ms · only the first call with no poll ~0.95s sync).
  - ★**Remote freshness** (2026-09-24; on a repo hosted on a private Git server, stale remote info went unnoticed). Server `remote_info` → `remote:[{name,host,local,fetchAt}]` · `fetchStaleH` (24) — reads files only (0 git calls, sharing the 20s cache).
    - fetchAt = max FETCH_HEAD mtime (common dir + `worktrees/*/`) · ⚠FETCH_HEAD is per-worktree. The common dir is resolved via the `.git` file → `commondir`. None → `null` = never fetched.
    - ⚠Only the host is sent (`user:token@` and path stripped; local paths `local:true`) — it appears on the page.
    - Screen: header «remote origin · last fetch N days ago» + copy «fetch cmd» (Sidereus never fetches). Past 24h upstream ↑↓ fades (`brSgHtml` `.brsgo`) with the reference time in the tooltip.
    - ⚠The worktree card's ↑↓ vs base branch (`brWtMeta`) uses local refs and does not fade.
  - Timeline session-row name tooltip shows `worktree: <name> · <root>` (not for main) — `74-timeline.js` `tlWtOf` (SESS `wt`, cwd ⊂ root match · no server addition).
  - ★**Uncommitted file owner · conflict risk** (2026-09-24). `sidereus/file_owner.py` incrementally scans Edit/Write/MultiEdit/NotebookEdit `file_path` in session + subagent transcripts (per-file offset, 10s TTL, 24h retention, first read last 1MB) → `/api/git/owners?cwd=` (git reuses `wt_files`).
    - Owner unit = (parent sid, aid) — aid is the subagent id or `main`. Live unit = session row not done + subagent still in row `sub` (reuses the bgtasks completion rule).
    - Screen: per-session sid8 chips in the file line `<em>` (`brWoHtml`, ended sessions faded) · an uncommitted file edited by 2+ live units within 30 min (`FO_CONFLICT_S`) gets ⚠.
    - attention `conflict` 85 pts (below question wait 90) — one signal on the last editor's row: within one session «conflict risk · N files · subagents a, b» (description ≤24 chars); across sessions «sessions a, b».
    - ★Sibling subagents count too (measured 09-24: all 16 co-edited files were agents of one session b12214b1). Main editing after an agent finished is not a conflict.
    - ⚠Edits via Bash (sed -i · > · heredoc) are invisible — guessing from command text is too loose to blame a session. Untracked (-uno) files excluded.
    - ⚠Tests swap `attention._conflicts` — otherwise attention() reads live transcripts.
- ★**Module global `_LOG_FMT` was defined twice; the later one (branch graph) overwrote the earlier (diff)** (2026-09-23). The diff screen's unpushed/pushed lists were always empty (git `ambiguous argument`).
  - ⇒ Graph side renamed `_BR_LOG_FMT`. ⚠In a single file nobody catches global name clashes — check a new global with `grep -n "^name ="` first.
- ★**In the branch panel the current branch is marked by name colour, weight and a `HEAD` tag** (2026-09-23).
  - Previously only the `L` badge colour (`brh`) differed; one 10px badge was invisible in a 43-branch list. ⇒ Row gets `.hd` + `<span class=brhd>HEAD</span>`.
  - ⚠Local/remote is a separate distinction — graph: filled chip (local) / outline only (remote); panel: `L`/`R` badges. Never merge the three into one colour.
- ★**Branch list = folder tree** (2026-09-23, SourceTree style). `brTreeModel`→`brTreeHtml` (groups «local» · «remote <remote>», folders by `/`) · `brTreeSet` · `brTreeKey` (Enter · ←→↑↓).
  - ★With default expansion keyed only on 7 days, a repo with only old branches (44 branches, all 14+ days) showed closed folders plus one `L+R main` line and read as «remote only · no branches» (2026-09-23). ⇒ A group with no hot folder opens its first-level folders (`auto`) · `tests/test_branch_tree.py`.
  - Default expansion: folders containing HEAD, a worktree or activity within 7 days. User expansion in `localStorage['sidereus.brtree.'+repo]`; merge (`L+R` badge, default ON) in `sidereus.brmerge`.
  - ⚠The list is rebuilt inside `brPanBody` every time (not the old `brPanList` string cache) — the polling repaint (`brPanPaint`) carries scroll and focus over.
- ★**Branch graph (`br` tab) lanes are bounded by «one lane = one awaited sha»** (2026-09-23).
  - The pure function `brLanes()` stores **exactly one** awaited sha per lane in `act[j]` ⇒ two commits can never share a lane at the same point. Only the first parent inherits the lane; second and later parents (merges) open new lanes — measured 80 commits · 28 merges → 3 lanes; 12 concurrent branches → 2.
  - ★Update (2026-09-23): several lanes may await **the same first parent** ⇒ forks bend only on the row just above the parent, merges only on the row just below the merge (edge `lane/via/plane`). Long diagonals are gone; a large repo's lanes went 6→8.
  - Drawing: lane cap 14 (`CAP`) · line 2px · dot r4.8 · merge = hollow ring · HEAD gold ring. Hover (`brHl`) marks only the first-parent path `.hl`, the rest `.dim` — class changes only (no relayout).
  - ⚠`var()` does not work in SVG presentation attributes (`stroke=`) — put tone variables in `style`.
  - ⚠**Overlap between lines converging on the same parent is not a violation** (a join has one vertex). Without this exception the overlap check fails valid graphs — 3 false positives at first.
  - ⚠When `detached`, `head` is a **7-char sha**, not a branch name ⇒ never match chips on `name === head` (`hdName` stays empty). `origin/HEAD` is removed by the server; draw as if absent.
  - ⚠**No polling** — only on tab open and `↻`. Only when `SESS` is empty right after boot and the repo picker is empty does it retry **once** after 1.2 s (`brRetry`). 403 (outside the list) · 400 (missing path) also read the body and show the reason in one line.
- ★**Branch tab commit detail swaps the right panel** (2026-09-23).
  - Cause: row click only set `.on` (15% background · faint border); a branch tip beyond 80 commits only showed a toast.
  - ⇒ `/api/git/commit?repo&sha[&path]` → `git_commit()`. Rows, branches and parent links all go `brJump→brOpen`, also beyond 80. Esc · `←` closes.
  - ⚠No inline expansion — a row height off `BR_RH` misaligns the SVG lanes. Only the panel repaints via `brPanPaint()`.
  - ⚠`path` goes to git only when it is in that commit's numstat list. sha is hex 4-40, repo via `_branch_ok`.
  - ⚠The selection's left bar is a `box-shadow` — the `?ui=next` twin CSS changes only bg/border/outline colours, so it stays visible regardless of tone.
- ★**Never define a function with the same name twice — `_git_root`** (2026-09-21). Two versions existed at `:1472` and `:1621`,
  and in Python **the later one wins** — editing the earlier one does nothing.
  ⇒ Removed the earlier one (`.git` directory only · 8 levels up · `_ROOT_CACHE`). The live one accepts
  worktrees (`.git` is a file) and has no climb limit. ⚠Before editing, count definitions with `grep -n "^def name"`.
- ★**Session git marks take a single `status --branch` — `_git_state()` (`sidereus/gitinfo.py`)**
  (2026-09-21 · found while measuring `_ps_snap()` above). Each session called `status --porcelain -uno` and
  `rev-list --count @{u}..HEAD` separately: **12 forks per refresh** (6 sessions × 2).
  ⇒ ①The unpushed count is already in the `--branch` header `## main...origin/main [ahead 3, behind 1]`, one call.
  ②`returncode != 0` (not a repo) is remembered long via `GIT_NOREPO_TTL=300`. Measured 12→6; normal 20 s cycle **12→5**
  (⚠`.mailbox-mcp` itself is not a repo). Same 6 repos measured directly 99ms → **51ms**.
  - ⚠**Do not touch the mark formula** — `↑ahead ~dirty`. It shipped after confirming **identical output in 16 cases**: ahead · ahead+behind · no upstream · detached ·
    worktree (`.git` is a file) · bare · non-repo.
  - ⚠Forget to drop the `--branch` header (the **first line**, starting `##`) from the dirty count and every repo shows `~1`.

## History and retro tabs

- ★**History row = session title + branch** (2026-09-24; an id alone cannot tell sessions apart). Titles come only from Claude Code records — `custom-title` (/rename) > `ai-title` (/resume auto title), latest of each. Branch = latest `gitBranch` (excluding `HEAD`). id goes in the tooltip; no title → id as before.
  - The token index scan (`usage._uidx_meta`) picks them up in the same pass and stores entry `tc` · `ti` · `br`. Old caches (no `tv`) read only the last 2MB once (`_uidx_meta_probe`). Cold 560MB 1.27 → 1.53s.
  - ⚠**Never use the first user prompt as a fallback title** — conversation text would reach the page (metadata-only rule). No title → id.
  - ⚠`gitBranch` is searched only in the first/last 4KB of a line (measured 143k lines, all within · full find is +46%). Test `tests/test_hist_title.py`.
- ★**«Insights» (retro) tab** (2026-09-23 · `retro`) — server `sidereus/retro.py` `retro(days)` → `GET /api/retro?days=7|30` · screen `web/js/86-retro.js` + `web/css/87-retro.css`.
  - Failure trend (stacked bars per day/kind + frequent signatures + `toolStats` failing tools) · weekly summary (weeks start Monday) · tokens per commit (per project).
  - Sources: tokens/sessions = `history(days)` · failures = `_fail_events()` (graded there — never regrade) · commits = one `git log --branches --no-merges -- .` per project (shortest cwd).
  - Measured (module load): cold 7 days 1.65s · 30 days 2.76s · warm 0ms (120 s cache, one lock prevents duplicate aggregation). Not attached to `state()`.
  - ★**30-day failures under-counted** (2026-09-24). Cause: the failure scan's file cap (main 60 · sub 400) read only 453 of 1,030 files in the 30-day window (08-28 7 → actually 50 · 09-01 23 → 116).
    - ⇒ `retro()` uses `_fail_events(h, capped=False)` — every file with mtime in the window. The failure tab and alerts keep the cap. Per-file offset accumulation (`_FAIL_OFF`) is the cache; no extra cache.
    - Measured: 30 days cold 5.82s (~4.6s with the cap) · warm 0.15s. 0 files reached the per-file `FAIL_KEEP` 4000, so no «partial» marker.
    - ⚠Never use `capped=False` in the failure tab or `_fail_loop` — that is the 2.5s poll path. `toolStats` counts since server start.
  - ★**Range-switch loading indicator** (2026-09-24). Cause: for the ~3s of a 7↔30 switch the old range's charts stayed, with only a faint «reading…» by the tab.
    - ⇒ While `retroBusy`, the body becomes a `.strload` box (same pattern as branch/structure tabs) and the pressed range button (`retroWant`) lights.
  - ★**Width fixed at 980px** (2026-09-24). Cause: `.rtw{max-width:980px}` dated from the right session column; with the drawer closed at 1440, ~430px on the right was empty.
    - ⇒ Full width + `.rtg.split2` two columns (failure trend | failing tools · weekly summary | tokens per commit). Split via **container query** `@container (min-width:1100px)` — one column when a pinned column shrinks `#feed`.
    - ⚠Do not switch to a viewport media query — pinned at 1440, feed 908px would go two-column and squash tables. `.brd` is one line + ellipsis (360px) + title.
    - Measured: 1440 closed two-column 750/625 · 1280 two-column 663/553 · 1000 and pinned (1440/1280) one column · horizontal overflow 0.
    - The token tab had the same cause (`.brep{max-width:1080px;margin:0 auto}`) ⇒ full width + `.bsp.on` two columns (composition · model | project · subagents · price table | compaction window), same container query 1100px. The branch tab (`br`) was already full width.
  - ★**«Activity by hour» is capped by bysrc retention** (2026-10-14 · `otel._otel_src_heat`, `rtHeat`). Source = `otel-bysrc` 5-min buckets, kept `OTEL_SRC_KEEP` = 8 days.
    - ⇒ A 30-day view holds at most 8 days; the header names the collection start via `rtPer(r, max(from, since))`.
    - ⚠Do not read it as a 30-day pattern, and do not widen retention just for this card — the file grows with every bucket.
  - ★**Per-account OTel cards** (2026-10-15 · `sidereus/otel_acct.py`, `retro(days, acct, key)`). Account = `claude_roots._acct_rec(sid)` (SessionStart record) → label; primary = key `""`. Only the label is stored — never email, account uuid or config path.
    - ⚠No record (sessions started before the hook, or no `session.id`) = unknown: not stored, counts only under All (`_otel_stat.acctUnk`). Do not fall back to `acct_of(sid, None)` — it returns the primary silently.
    - ⚠Keys are labels: renaming an extra account orphans its history under the old label (no back-fill, no migration).
    - ⚠«Tools failing most» (`tools`, memory since server start) stays All under a pick — it has no per-day or per-account source.
    - ⚠Records before `acctSince` have no account, so a pick under-counts those days; the screen says so in one line. `since` is per account (first add); old files fall back to the top-level `since`.
    - ⚠Lock order is fixed: `otel._otel_lock` → `otel_acct._oa_lock` (adds run under `_otel_lock`). otel_acct must never take `_otel_lock` — the reverse order deadlocks.
    - Unknown sids are memoised for `OA_MISS_S` (60 s), then retried, so a new session resolves once its SessionStart record appears.
  - ⚠A sha found in two projects (worktree · subfolder) counts once in day/week totals, once per project row. Not git = `commits:null` → «—».
- ★**«More» raises the day count only after a successful load** (2026-09-23).
  - `loadHist(force, want)` — raising `histDays` first makes only the header say "last 90 days" over a stale `HIST`. ⚠While `histBusy` it returns `false` and the caller reports via `note()` (previously the click was silently dropped).
- ★**The «History» tab is drawn from `usage-index.json`** (2026-09-23 · common ADE feature — Conductor Archive · Codex task history).
  - The list (`sessions()`) cuts at `max_age_h=12`, so **ended sessions older than 12 hours vanish entirely** — `history()` (`/api/history?days=N`) covers the rest. Folded by date × session, 60 s cache (measured cold 0.07 s · 7 days 32 rows).
  - ⚠Do not write a new scanner — that index already holds hourly buckets for every transcript (incremental 0.05 s).
  - ⚠Resolution is **hourly** — minute-level start/end is not in this source. So duration is `hours` (number of active hours).
  - ⚠External CLI sessions are not loaded from `ext-sessions.json` (pruned at 24h). ★Since 2026-09-24 Gemini is loaded from its own chat files (`ext.gemini_chats`, (size, mtime) cache · time · id · model · tokens only) as a **separate `gm` block** per date — project = `tmp/<dir>/.project_root`, else `projectHash`=sha256(path) reverse-mapped via `projects.json` keys. Gemini stores no title, so the id is shown.
    - ⚠Never mix `gm` into Claude `rows`/totals — `retro()` sums those rows as-is. Only the screen (85-history) interleaves them by end time.
  - ⚠Some paths cannot be recovered from the slug (`.` also becomes `-`) ⇒ `_cwd_probe()` extracts **only the `cwd` field** from the transcript. Conversation is not read.
- ★**Clicking a history row expands the session's work units (main + subagents); clicking an item opens the `/work` popup** (2026-09-24).
  - Source `history_units(sid)` (`/api/history/units?sid=`, `sidereus/history.py`, 30 s cache): tokens = usage index, times = file create/modify times, kind/description = `subagents/*.meta.json`, tool count = `_agent_tools` (incremental cache).
  - Main session length = `histActive(hours)` → «active about N h» (09-24, previously «N hour slots»). ⚠The source is hourly buckets, so minutes are impossible — keep «about».
  - ⚠The main page is **metadata only** — content appears only in the existing `/work` popup (`wkPopup`). The main transcript is not read, so its tool count is `None` (no estimating).
  - Ended sessions: `session_work`/`agent_work` allow a cwd outside the list via `_past_row(cwd, sid)` (only when the transcript is under the `_slug(cwd)` folder). Agent tid is `<toolUseId>|<sid>` → `workUrl` passes `&sid=`.
  - ⚠Requests without a sid still allow only the on-screen list — never widen the allow range to cwd alone.
