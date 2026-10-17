"""Structure treemap scanning: constants, caches, area grouping, per-snapshot build (language scanners: structure_lang,
disk cache: structure_cache)."""
import hashlib
import re
import threading
from datetime import datetime
# Language scanners live in structure_lang (split 2026-09-24); re-exported here for importers and tests.
from sidereus.structure_lang import (STRUCT_JS_EXTS, STRUCT_JAVA_EXTS, STRUCT_JSP_EXTS, STRUCT_GO_EXTS,
    _struct_one_file)
from sidereus.structure_plug import plug_exts, plug_is_test, plug_load, plug_skip, plug_test_pats

plug_load()     # ⚠before STRUCT_EXTS / STRUCT_TEST_FILE / _struct_wanted's default: they take the plug-in values


# ── structure/growth treemap (GET /api/structure) ──────────────────────────────
# ★Emits «how the project has grown» at function granularity
#   (reachable by selecting a session and then its projects).
#   Mechanism: collect `.py/.js/.ts/.tsx/.jsx` in the target directory; extract function lists with `ast` for Python and
#   brace scanning for the rest. Past points are **git first** (`log` + `ls-tree`/`cat-file`),
#   `backup/mailbox-*.tar.gz` if no git. The number of times a body hash changed between snapshots is `churn` (cumulative).
# ⚠Do not call from the server startup thread — compute only on request (parsing 10 snapshots is expensive).
# ⚠git uses **read-only commands only** (`log`·`ls-tree`·`cat-file`). `checkout`·`stash`·`reset`
#   touch the user's working tree — never add them.
# ★Measured 2026-09-22 cold: Sidereus (no git·10 backups) 1.4s · repo-A (560K lines) 3.3s · warm 0.04s.

STRUCT_EXTS = (".py",) + STRUCT_JS_EXTS + STRUCT_JAVA_EXTS + STRUCT_JSP_EXTS + STRUCT_GO_EXTS
STRUCT_EXTS += tuple(e for e in plug_exts() if e not in STRUCT_EXTS)    # language plug-ins (structure_plug)
# Code popup also opens Vue SFCs. ⚠Not in STRUCT_EXTS — the treemap has no SFC scanner.
STRUCT_REL_EXTS = STRUCT_EXTS + (".vue",)
# ★Static vendor assets are «someone else's code», not structure (most of repo-A's 1,640 js).
# ⚠Applies to js family only — applying it to `.java` wipes out sources whose package name is `lib`.
STRUCT_VENDOR_DIRS = {"vendor", "lib", "libs", "assets", "static", "webjars", "plugins"}
STRUCT_VENDOR_NAME = re.compile(
    r"(?:\.min|-min)\.[a-z]+$|^(?:jquery|bootstrap|moment|lodash|d3|chart)", re.I)
# ★A directory named `<name>-<version>` is **a bundle imported wholesale** — this catches more than the list.
#   Measured 2026-09-22 repo-A: this one rule removes 1,409 js (36.7MB, ace-builds-1.2.6 ·
#   lodash-4.16.5 etc.), leaving only 234 js (4.8MB). Without it cold runs take minutes.
STRUCT_VENDOR_VER = re.compile(r"^[A-Za-z][\w.$@-]*[-.]\d+(?:\.\d+)+$")
# ★Name lists always lag ⇒ also split by **properties of the file itself** (2026-09-22, show only code-related
#   files). Measured: `repo-A/src/main/webapp/template/js` 45 files = 621,887 lines, all
#   third-party libraries (jindo · FusionCharts · dhtmlX · canvg · FileSaver · jit), yet the name/version rule
#   caught only `ace-builds-1.2.6`, and `template/js 18,434 lines` rose to the top areas.
# ⚠Applies to js/ts family only — generated JSP or large Java files **may be the core**.
# ⚠Keep the name/path rules (`STRUCT_VENDOR_DIRS`·`_NAME`·`_VER`) — applying both is fine.
STRUCT_VENDOR_MAXCOL = 500               # a line longer than this means minified
STRUCT_VENDOR_AVGCOL = 200               # average line length
STRUCT_VENDOR_LINES = 4000               # huge — not a size a human writes by hand
# ⚠license header in the first 40 lines. Measured to confirm app code is not caught
#   (all 14 of repo-B `frontend/src/lib/*.ts` lic=0 · maxcol≤146).
STRUCT_VENDOR_LIC = re.compile(rb"Copyright|Licensed under|@license|MIT License")
# ★Tests are not the core (2026-09-22 — tests showing up first was unwanted). Measured repo-B:
#   `src/main` 96,315 lines vs `src/test` 111,052 lines — tests took the top 1·2 areas.
#   ⇒ Included only when `?tests=1` (default 0).
STRUCT_TEST_DIRS = {"test", "tests", "__tests__"}
STRUCT_TEST_FILE = re.compile("|".join([
    r"(?:[A-Za-z0-9_$]Test|Tests|IT)\.(?:java|kt)$"
    r"|\.(?:test|spec)\.(?:ts|tsx|js|jsx|mjs|cjs|mts|cts)$"
    r"|(?:^|/)test_[^/]*\.py$|_test\.py$|_test\.go$"] + ["(?:%s)" % p for p in plug_test_pats()]))


def _struct_tmode(v):
    """Test filter mode: 0 = core only (default) · 1 = all · 2 = tests only (`tests=only`).
    ⚠0/1 hash and format like the old bool, so existing cache keys stay valid."""
    if v == 2 or (isinstance(v, str) and v.strip().lower() in ("2", "only")):
        return 2
    if isinstance(v, str):
        return 1 if v.strip().lower() in ("1", "true", "on", "yes") else 0
    return 1 if v else 0


# ⚠**Bump this** when changing the classification rules — it is part of the cache key (without a bump old results come back as-is).
STRUCT_RULES_VER = 11   # 11: route tagging removed with the Relations stack · 10: route-tagged fns -> «http» area · 4: Java annotated methods, Kotlin return types, Go pairs same-dir only · 5: JS ignores fns in comments/strings (2026-09-25) · 6: areas carry `rest` (2026-09-25) · 7: .mjs/.cjs/.mts/.cts (2026-09-28) · 8: skip scratchpad/ (2026-09-30) · 9: language plug-ins (2026-10-05)
# `scratchpad` = agent throwaway scripts (<agent repo>/scratchpad: e2e/probe .mjs), not the project's structure
STRUCT_SKIP = {"node_modules", ".git", "__pycache__", "dist", "build", "target",
               "venv", ".venv", ".next", ".idea", "coverage", "vendor", "bower_components", "scratchpad"}
STRUCT_MAX_FILES = 3000                  # ⚠cap — above it, drop «smallest files first» and set truncated
# ★2026-09-22 raised 2000 -> 3000 when adding java. At the cap **large files are kept** (it used to be the reverse) —
#   large files are the structure. repo-B has 2,200 files so it does not hit the cap (cold measurement in the comment below).
STRUCT_MAX_BYTES = 2 * 1024 * 1024       # 2MB per file
STRUCT_SNAPS = 10                        # number of past points for git repositories (the current one is added on top)
# ★Projects without git use **20**, chosen evenly along «the time axis», not by count
#   (2026-09-22). ⚠Do not just take the latest 10 — Sidereus's 10 `backup/*.tar.gz` are all
#   from 70 min of the same day (measured 08:11~09:21 · total 17,319→18,525), so churn was 0 for 356 of 365.
STRUCT_SNAPS_LOCAL = 20
# ⚠Cap on functions emitted per area. `n`·`lines` are **the full values even after truncation**, and the truncated count
#   goes in `more` — the treemap only needs to draw the big cells, but totals must be right.
#   ★Measured 2026-09-22: without the cap the repo-A (13,485 functions) response was 22MB.
STRUCT_MAX_FNS = 60
# ★Cap for drill-down (`full=1`) only — used when clicking a "Show N more" bundle cell to view one area.
# ⚠Do not use this value for the full screen: the 22MB response and thousands of rendered cells come right back (measured above).
STRUCT_FULL_FNS = 400
# ★Omitted functions are summarised **per file** in `rest` (2026-09-25 user: one grey blob was ~60% of big areas and said nothing).
# ⚠Files beyond this cap fold into one final entry (`etc`) so sum(rest.lines) still equals the omitted lines.
# ★Measured 2026-09-25 sidereus area: cap 12 left `etc` at 42% of the area (the same blob again) · 24 -> 24% · 40 -> 8%.
STRUCT_REST_FILES = 40
STRUCT_GIT_TIMEOUT = 20
STRUCT_CACHE_N = 10                      # LRU up to 10 projects

# ★Area table — **this is the spot people edit.** First match from the top wins.
#   `pre` = name prefix · `has` = name contains (both lowercase). Anything not matched silently becomes `etc`.
# ⚠Reordering changes the classification wholesale — do not move the generic `ui` (build*/draw*) up.
#   Then `buildQuota` leaves quota.
# ⚠This table is used only when «one file makes up the whole project» (Sidereus's chat_server.py). Projects split into
#   many files already have directories as structure and are grouped by path — see `_struct_group()`.
STRUCT_AREAS = [
    ("quota", "Quota/burndown",
     ("quota", "_quota", "_qb", "qb_", "amt", "burn", "bn", "money", "gauge", "pct",
      "_price", "_cost", "cost", "_uidx", "_usage", "_win_", "_today", "_projcost",
      "_cc_", "_oauth", "_omc", "_anchors", "_next_reset", "_blocks_local",
      "_line_tokens", "_round_win", "_model_win", "_ctx_window", "_scan_windows",
      "wk", "curwintok", "creditrow", "painttoken", "_lang_of", "_blocked"),
     ("quota", "usage", "credit", "token", "burn", "cost", "money", "wkuse", "wkrange")),
    ("timeline", "Timeline/sessions",
     ("agent", "ag", "_ag", "tl", "sess", "session", "_parse_transcript", "_tx_",
      "sid", "_sid", "nap", "_nap", "_idle_gaps", "_seg_scan", "carve", "work",
      "_work", "wt", "_wt", "open", "live", "_live", "byidle", "isidle", "commit",
      "_commits", "_compacts", "diff", "git", "_git", "repo", "_repo", "loadtl",
      "painttl", "splitdiff", "hasgit", "_human_text", "_meta_of", "_slug", "_proj",
      "_cwd_from_slug", "_newest_jsonl", "_open_or_tail", "_tail", "_recent_trans",
      "_edit_target", "_wrote_files", "_tool_", "_res_is_code", "_reply_summary"),
     ("session", "agent", "transcript", "timeline", "commit", "diff")),
    ("saver", "Saver mode",
     ("saver", "_saver", "sv", "view", "vw", "pace", "_self_hold"),
     ("saver", "pace")),
    ("http", "HTTP/routing",
     ("do_get", "do_post", "_send", "send", "_json", "handle_one_request",
      "log_message", "_resp_key", "main", "_flush", "bin_path", "rich_env",
      "boot_time", "_origin_ok", "_allowed_cwds", "_save_json", "_load", "g"),
     ("http", "route", "handler")),
    ("bg", "Background/processes",
     ("_running_bg", "_bg", "bg", "_tick", "tick", "_watch", "watch", "_scan",
      "_loop", "loop", "_thread_died", "boot", "_ps_snap", "_dead", "_stale",
      "stalethreads", "_awake", "awake", "poll", "_subs_mt", "warn_once", "_note",
      "selfcheck", "health", "presence", "_mon_rows"),
     ("_loop", "_tick", "_watch", "_scan", "thread", "presence", "health")),
    ("fail", "Failures/leftovers",
     ("_fail", "fail", "wreck", "_wreck", "_wdrop", "_wsnap", "paintfail", "loadfail",
      "_retired", "_dirty_map", "_shape_list", "_slow_why", "_grade"),
     ("fail", "wreck")),
    ("chat", "Mailbox/cards",
     ("card", "_card", "cards", "mark", "receipt", "alarm", "toast", "bubble",
      "chat", "messages", "_bus_append", "ack", "room", "_room", "buildinvite",
      "readers", "_mbox", "identity", "_noise_user", "_recent_card", "set_cards",
      "_lab", "people", "buildpeople", "buildrooms", "buildtodo", "answered",
      "waiting", "isdecided", "isfixed", "isnew", "digest"),
     ("card", "room", "mailbox", "alarm")),
    ("ui", "Screen builders",
     ("build", "draw", "render", "fmt", "paint", "chip", "pill", "esc", "cell",
      "bar", "sty", "color", "hue", "icon", "html", "tab", "pane", "wrap", "head",
      "toggle", "sync", "copy", "md", "codeblock", "inline", "decorate", "nest",
      "tree", "apply", "set", "show", "close", "pick", "trim", "squash",
      "visible", "atbottom", "tobottom", "scroll", "wire", "arm", "bind"),
     ("html", "paint", "draw")),
]
STRUCT_ETC = ("etc", "Other")
# leading «shell» segments of path groups — stripped only from labels (`src/api` -> `api`).
STRUCT_WRAP_DIRS = ("src", "lib", "app", "source", "main", "packages", "pkg", "js", "ts",
                    "java", "webapp", "web", "www", "static", "public", "assets", "resources")
STRUCT_DIR_MIN = 4                       # go one level deeper until it splits into at least this many
# ★If one cell exceeds this share, go deeper. It was 0.7, but then repo-B stopped at two cells `main` (31%)·`test` (54%)
#   (measured 2026-09-22). Lowering to 0.35 gives depth 3 (59 cells·max 15%) — domain granularity.
#   ⚠Do not lower further — with hundreds of cells the treemap turns to sand (repo-A has 110 cells at depth 5).
STRUCT_DIR_MAX_SHARE = 0.35
STRUCT_DIR_MAX_DEPTH = 8       # ★measured: repo-A has all js under src/main/webapp/template/*, so 4 gave a single cell

_struct_lock = threading.Lock()
_struct_blob_cache = {}                  # (kind, key) -> extraction result. git sha·tar are immutable
_struct_file_cache = {}                  # (path, content hash) -> (line count, function list) — parse reuse
STRUCT_FCACHE_N = 20000
STRUCT_BCACHE_N = 200
_struct_out_cache = {}                   # realpath -> (key, result, last used time)


def _struct_area(name):
    """One function name to an area key. ⚠A heuristic — silently `etc` if no match."""
    lo = (name or "").lower()
    for key, _nm, pre, has in STRUCT_AREAS:
        for p in pre:
            if lo.startswith(p):
                return key
        for h in has:
            if h in lo:
                return key
    return STRUCT_ETC[0]


def _struct_collapse(per_file):
    """★The set of «cells with only one branch». For repositories with long common prefixes.
    ⚠Without it a `src/main/java/com/example/app/...` repository clumps into two cells `main`·`test`
      (measured 2026-09-22 repo-B: at depth 2, 3 of 4 cells held 99.9% of the total). Going deeper only
      passes «non-splitting» cells like `java`·`com`·`example`, so the auto-selection stalls."""
    kids = {}
    for r in per_file:
        parts = r.replace("\\", "/").split("/")[:-1]
        for k in range(len(parts)):
            kids.setdefault("/".join(parts[:k]), set()).add(parts[k])
    return set(p for p, v in kids.items() if len(v) == 1)


def _struct_segs(rel, flat):
    """File path -> list of «meaningful» directory segments (non-splitting cells removed)."""
    parts = rel.replace("\\", "/").split("/")[:-1]
    return [parts[k] for k in range(len(parts)) if "/".join(parts[:k]) not in flat]


def _struct_dir_depth(per_file, segs):
    """★Choose the grouping depth **automatically** — descend one level at a time from shallow, and use the first depth
    where it splits into at least STRUCT_DIR_MIN cells and **no cell exceeds STRUCT_DIR_MAX_SHARE**.
    ⚠Do not fix the depth shallow: a `src/main/webapp/template/js/...` repository becomes a single
    cell (measured 2026-09-22 repo-A — at depth 4 all 13,485 functions went into one area)."""
    body = sum(per_file.values()) or 1
    fallback = None
    for d in range(1, STRUCT_DIR_MAX_DEPTH + 1):
        agg = {}
        for r, ln in per_file.items():
            parts = segs.get(r) or []
            k = "/".join(parts[:d]) if parts else "(root)"
            agg[k] = agg.get(k, 0) + ln
        if len(agg) >= STRUCT_DIR_MIN:
            if fallback is None:
                fallback = d
            if max(agg.values()) < body * STRUCT_DIR_MAX_SHARE:
                return d
    return fallback or 1


def _struct_dir_area(parts, depth):
    """List of «meaningful» segments -> (area key, label). Top-level files are `(root)`."""
    if not parts:
        return "(root)", "(root)"
    key = "/".join(parts[:depth])
    lab = list(parts[:depth])
    while len(lab) > 1 and lab[0].lower() in STRUCT_WRAP_DIRS:
        lab = lab[1:]
    return key, "/".join(lab)


def _struct_wanted(rel, exts=STRUCT_EXTS):
    if not rel.endswith(exts):
        return False
    parts = rel.replace("\\", "/").split("/")
    if any(p in STRUCT_SKIP for p in parts[:-1]):
        return False
    if plug_skip("/".join(parts)):                    # plug-in vendor dirs / generated files, its own exts only
        return False
    if rel.endswith(STRUCT_JS_EXTS + (".vue",)):       # ⚠js family only — see the ⚠ at STRUCT_VENDOR_DIRS above
        dirs = [p.lower() for p in parts[:-1]]
        for k, p in enumerate(dirs):
            # ⚠`src/lib`·`src/assets` **are app code** (Vite convention) — excluding them wipes out real sources
            #   (measured 2026-09-22 repo-B `frontend/src/lib/*.ts` 14 files). Spared if the preceding segment is `src`.
            if p in STRUCT_VENDOR_DIRS and not (k and dirs[k - 1] == "src"):
                return False
        if any(STRUCT_VENDOR_VER.match(p) for p in parts[:-1]):
            return False
        if STRUCT_VENDOR_NAME.search(parts[-1]):
            return False
    return True


def _struct_is_test(rel):
    """Is it test code — looks at **path·file name only** (the content is not opened)."""
    p = rel.replace("\\", "/")
    if any(seg.lower() in STRUCT_TEST_DIRS for seg in p.split("/")[:-1]):
        return True
    return bool(STRUCT_TEST_FILE.search(p)) or plug_is_test(p)    # plug-in test_dirs (e.g. `X.Tests/`)


def _struct_vendor_blob(rel, b):
    """(is vendor, line count). ⚠Classification for js/ts family only — in java/jsp even large files may be the core."""
    nl = b.count(b"\n") + 1
    if not rel.endswith(STRUCT_JS_EXTS):
        return False, nl
    if nl > STRUCT_VENDOR_LINES:                  # huge
        return True, nl
    if len(b) > nl * STRUCT_VENDOR_AVGCOL:        # average line length
        return True, nl
    for ln in b.split(b"\n"):                     # longest line (= minified)
        if len(ln) > STRUCT_VENDOR_MAXCOL:
            return True, nl
    if STRUCT_VENDOR_LIC.search(b"\n".join(b.split(b"\n", 40)[:40])):
        return True, nl
    return False, nl


def _struct_build(items, tests=False, fkeys=None):
    """[(relative path, bytes)] -> (total lines, function list, truncated, file count, broken count, exclusion tally, test file set).
    If `fkeys` is a list, the **file cache keys** used this time are put into it (used by the disk file cache).
    ★Identical content is never parsed twice (key = path + content hash) — scanning 10 commits, most files are
    unchanged, so measured repo-A cold dropped from 33.7s to single digits.
    ⚠**Do not mutate** dicts in the cache — several snapshots see the same object (churn is layered separately).
    ⚠Vendor·tests are removed **before applying the cap (STRUCT_MAX_FILES)** — otherwise someone else's code
      eats the cap and the core gets cut."""
    items = [(r, b) for r, b in items if len(b) <= STRUCT_MAX_BYTES]
    mode = _struct_tmode(tests)
    ex = {"vendor": 0, "vendorLines": 0, "test": 0, "testLines": 0}
    if mode == 2:
        ex["core"] = ex["coreLines"] = 0
    tfiles = set()
    keep = []
    for rel, b in items:
        if _struct_is_test(rel):
            nl = b.count(b"\n") + 1
            ex["test"] += 1
            ex["testLines"] += nl
            if not mode:
                continue                          # default 0 — excluded from the core
            if mode == 1:                         # ⚠tests-only marks nothing — every area would be greyed out
                tfiles.add(rel)
            keep.append((rel, b))
            continue
        vend, nl = _struct_vendor_blob(rel, b)
        if vend:
            ex["vendor"] += 1
            ex["vendorLines"] += nl
            continue
        if mode == 2:
            ex["core"] += 1
            ex["coreLines"] += nl
            continue
        keep.append((rel, b))
    items = keep
    trunc = False
    if len(items) > STRUCT_MAX_FILES:
        items.sort(key=lambda t: -len(t[1]))          # ⚠drop smallest first — large files are the structure
        items = items[:STRUCT_MAX_FILES]
        trunc = True
    total = 0
    fns = []
    skipped = 0                                   # number of files the parser gave up on (java)
    for rel, b in items:
        ck = ("f", rel, hashlib.md5(b, usedforsecurity=False).hexdigest())
        if fkeys is not None:
            fkeys.append(ck)
        with _struct_lock:
            hit = _struct_file_cache.get(ck)
        if hit is None:
            try:
                hit = _struct_one_file(rel, b.decode("utf-8", "replace"))
            except Exception:
                hit = (0, [], 1)
            with _struct_lock:
                if len(_struct_file_cache) > STRUCT_FCACHE_N:   # ⚠do not create a dict without expiry
                    _struct_file_cache.clear()
                _struct_file_cache[ck] = hit
        total += hit[0]
        fns += hit[1]
        skipped += hit[2]
    return total, fns, trunc, len(items), skipped, ex, tfiles


def _struct_rest(rows, cap=STRUCT_REST_FILES):
    """Omitted functions -> [{file, n, lines}] by lines desc; past `cap` one {etc, files, n, lines} entry."""
    per = {}
    for r in rows:
        e = per.setdefault(r["file"], [0, 0])
        e[0] += 1
        e[1] += r["lines"]
    items = sorted(per.items(), key=lambda kv: (-kv[1][1], kv[0]))
    out = [{"file": f, "n": v[0], "lines": v[1]} for f, v in items[:cap]]
    tail = items[cap:]
    if tail:
        out.append({"file": "", "etc": True, "files": len(tail),
                    "n": sum(v[0] for _f, v in tail), "lines": sum(v[1] for _f, v in tail)})
    return out


def _struct_group(total, fns, trunc, churn, tfiles=(), lastv=None, maxf=STRUCT_MAX_FNS):
    """Fold the function list into areas. ★If one file takes half or more of the function lines (Sidereus's
    chat_server.py), directories are not the structure, so the **name heuristic table** is used; otherwise group
    by **path**. ⚠Remove this split and a single-file project becomes one `(root)` cell.
    ★`lastv` = function key → **the snapshot number where it last changed**. Used by the screen's "recent change" color axis —
      churn is 0 for 73~88% (measured 2026-09-22), so it gives the color no information.
    ★`maxf` = cell cap per area. Only raised for drill-down (`full=1`) — lifting it on the full screen is slow."""
    per_file = {}
    for f in fns:
        per_file[f["file"]] = per_file.get(f["file"], 0) + f["lines"]
    body = sum(per_file.values()) or 1
    by_dir = bool(per_file) and (max(per_file.values()) < body * 0.5)
    names = dict((k, n) for k, n, _p, _h in STRUCT_AREAS)
    names[STRUCT_ETC[0]] = STRUCT_ETC[1]
    order = [k for k, _n, _p, _h in STRUCT_AREAS] + [STRUCT_ETC[0]]
    buckets = {}
    if by_dir:
        flat = _struct_collapse(per_file)
        segs = dict((r, _struct_segs(r, flat)) for r in per_file)
        depth = _struct_dir_depth(per_file, segs)
        for f in fns:
            key, lab = _struct_dir_area(segs.get(f["file"]) or [], depth)
            names[key] = lab
            buckets.setdefault(key, []).append(f)
        order = sorted(buckets, key=lambda k: -sum(x["lines"] for x in buckets[k]))
    else:
        for f in fns:
            buckets.setdefault(_struct_area(f["name"]), []).append(f)
    areas = []
    for key in order:
        rows = buckets.get(key)
        if not rows:
            continue
        rows = sorted(rows, key=lambda r: -r["lines"])
        keep = rows[:maxf]
        lv = lastv or {}
        a = {"key": key, "name": names.get(key, key),
             "lines": sum(r["lines"] for r in rows), "n": len(rows),
             "fns": [{"name": r["name"], "lang": r["lang"], "file": r["file"],
                      "line": r["line"], "lines": r["lines"],
                      "churn": churn.get("%s:%s:%s" % (r["file"], r["lang"], r["name"]), 0),
                      "last": lv.get("%s:%s:%s" % (r["file"], r["lang"], r["name"]), 0)}
                     for r in keep]}
        if len(rows) > len(keep):
            a["more"] = len(rows) - len(keep)
            # ⚠Drill-down (`full=1`) is where «N other files» was clicked to open it — folding again there left a dead
            #   cell (the screen has no deeper level). Per-file entries only, so the size stays bounded by the file count.
            tail = rows[len(keep):]
            a["rest"] = _struct_rest(tail, len(tail) if maxf > STRUCT_MAX_FNS else STRUCT_REST_FILES)
        # ★when `tests=1`, mark so the screen can distinguish it from the core (over half tests = test area).
        if tfiles:
            tl = sum(r["lines"] for r in rows if r["file"] in tfiles)
            if tl * 2 > a["lines"]:
                a["test"] = True
        areas.append(a)
    out = {"total": total, "areas": areas}
    if trunc:
        out["truncated"] = True
    return out


def _struct_label(ts):
    """⚠If the year differs, **append the year** — otherwise sorting is correct but it looks jumbled
    (measured 2026-09-22 repo-A: 400 commits spanning several years were stamped `9/25 → 5/24 → 2/14`)."""
    d = datetime.fromtimestamp(ts)
    if d.year != datetime.now().year:
        return "%d.%d.%d" % (d.year, d.month, d.day)
    return "%d/%d %s" % (d.month, d.day, d.strftime("%H:%M"))   # ⚠`%-m` is glibc/BSD only; Windows strftime raises
