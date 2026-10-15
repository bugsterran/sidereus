"""Project checks (lint / static analysis) on the Architecture map: tool detection, report parsers, per-module
aggregation and the `/api/arch` `checks` loader (parsers: sidereus/arch_checks_parse.py).

⚠No subprocess here — Sidereus never runs a tool (AGENTS.md rule 7). The runner `scripts/arch_checks.py` (gate of
`.claude/pipelines/project-checks.json`) executes the argv built by `detect()` and writes
arch/<key>/<commit>/checks.json. Only file / line / rule id / severity are kept, never tool message text.
Stdlib only, Python 3.9 (no tomllib: pyproject sections are found by a line regex).
"""
import json
import os
import re
import shutil
import time

from sidereus.arch_verify import COMMIT_RE, owns, plan_globs, read_json, safe_rel
from sidereus.arch_checks_parse import PARSERS, SEVS, checkstyle_files, clean_help, eslint_files, \
    mypy_files, parse_checkstyle, parse_clippy, parse_eslint, parse_govet, parse_mypy, parse_pmd, parse_ruff, parse_tsc  # noqa: F401
from sidereus import sec_checks as SC

CHECKS_FILE = "checks.json"
CHECKS_LAST = "_checks_last.json"   # {repo, commit} of the newest runner write (gate `--verify --last`)
TOOL_IDS = ("checkstyle", "pmd", "spotbugs", "ruff", "mypy", "eslint", "tsc", "govet", "clippy")
STATUSES = ("ok", "fail", "timeout", "missing", "skipped")
RULE_RE = re.compile(r"[A-Za-z0-9_./@:-]{1,60}")
WHY_MAX, ITEMS_MAX, TOP_MAX, FILES_MAX = 60, 300, 50, 20000
TOOL_TIMEOUT_S, TOTAL_S = 300, 900
OUT_MAX = 32 * 1024 * 1024         # bytes of stdout / one report parsed
WHY_OFFLINE = "dependencies not cached — run a normal build once"
TMP_TOKEN = "@TMP@"                # env value the runner replaces with its own temp dir
OFFLINE_RE = re.compile(r"offline mode|No cached version|Could not resolve|GOPROXY=off|module lookup disabled|"
                        r"failed to download|--offline|cannot find module providing", re.I)
_SKIP = {".git", "node_modules", "build", "target", ".gradle", "dist", "out", ".venv", "venv", "__pycache__", ".idea",
         ".mvn", ".tox", ".mypy_cache", ".ruff_cache"}
_WALK_DIRS, _WALK_DEPTH = 5000, 6


# ── detection (filesystem reads only) ──

def _read(fp, n=262144):
    try:
        with open(fp, encoding="utf-8", errors="replace") as f:
            return f.read(n)
    except OSError:
        return ""


def _scan(repo):
    """One bounded walk: build files, Java source dirs, Java presence."""
    s = {"gradle": [], "pom": [], "java_dirs": [], "java": False}
    n = 0
    for dp, dns, fns in os.walk(repo):
        rel = os.path.relpath(dp, repo)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        dns[:] = sorted(d for d in dns if d not in _SKIP and not d.startswith(".")) if depth < _WALK_DEPTH else []
        n += 1
        if n > _WALK_DIRS:
            break
        r = "" if rel == "." else rel.replace(os.sep, "/")
        if r == "src/main/java" or r.endswith("/src/main/java"):
            s["java_dirs"].append(r)
        for f in fns:
            if f in ("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts") and depth <= 3:
                s["gradle"].append(os.path.join(dp, f))
            elif f == "pom.xml" and depth <= 2:
                s["pom"].append(os.path.join(dp, f))
            elif f.endswith(".java"):
                s["java"] = True
    return s


_WIN_WRAPPER = {"gradlew": "gradlew.bat", "mvnw": "mvnw.cmd"}


def _exe(repo, wrapper, which, name):
    # ⚠Windows: X_OK is always true and the sh wrapper fails with WinError 193 — use the .bat/.cmd one
    if os.name == "nt":
        w = os.path.join(repo, _WIN_WRAPPER[wrapper])
        return w if os.path.isfile(w) else which(name)
    w = os.path.join(repo, wrapper)
    return w if os.path.isfile(w) and os.access(w, os.X_OK) else which(name)


def node_bin(d, tid):
    """node_modules/.bin tool path; ⚠Windows needs the .cmd shim (the extensionless one is sh)."""
    return os.path.join(d, "node_modules", ".bin", tid + (".cmd" if os.name == "nt" else ""))


def _tool(tid, rules, **kw):
    return dict({"id": tid, "rules": rules}, **kw)


def _java(repo, s, which):
    """checkstyle / pmd / spotbugs plans, only where the Gradle / Maven build declares them.
    ⚠No CLI fallback with our own rules: on a repo without lint config it reported noise the repo never agreed to."""
    out = {}
    gtxt = " ".join(_read(f) for f in s["gradle"])
    ptxt = " ".join(_read(f) for f in s["pom"])
    for tid, gword, mplug, rep in (("checkstyle", r"\bcheckstyle\b", "maven-checkstyle-plugin", "checkstyle-result.xml"),
                                   ("pmd", r"\bpmd\b", "maven-pmd-plugin", "pmd.xml")):
        if re.search(gword, gtxt):
            gw = _exe(repo, "gradlew", which, "gradle")
            tasks = [t for t, w in (("checkstyleMain", r"\bcheckstyle\b"), ("pmdMain", r"\bpmd\b")) if re.search(w, gtxt)]
            out[tid] = _tool(tid, "project", argv=[gw, "--offline", "--no-daemon", "-q"] + tasks, cwd=repo, src="reports",
                             reports=[("build/reports/" + tid, None)]) if gw else \
                _tool(tid, "project", status="missing", why="install: gradle (or add ./gradlew)")
        elif mplug in ptxt:
            mv = _exe(repo, "mvnw", which, "mvn")
            goals = [g for p, g in (("maven-checkstyle-plugin", "checkstyle:checkstyle"), ("maven-pmd-plugin", "pmd:pmd"))
                     if p in ptxt]
            out[tid] = _tool(tid, "project", argv=[mv, "-o", "-q"] + goals, cwd=repo, src="reports",
                             reports=[("target", rep)]) if mv else _tool(tid, "project", status="missing", why="install: maven")
    res = [out[t] for t in ("checkstyle", "pmd") if t in out]
    if (s["java"] or s["java_dirs"]) and re.search(r"spotbugs", gtxt + ptxt, re.I):
        res.append(_tool("spotbugs", "project", status="skipped", why="needs build"))
    return res


def _py(repo, which):
    out = []
    pp = _read(os.path.join(repo, "pyproject.toml"))
    rcfg = any(os.path.isfile(os.path.join(repo, f)) for f in ("ruff.toml", ".ruff.toml")) or \
        bool(re.search(r"^\[tool\.ruff\b", pp, re.M))
    if rcfg:   # ⚠repo's own ruff config only (no --isolated default rules)
        exe = which("ruff")
        argv = [exe, "check", "--output-format", "json", "--no-cache", "--exit-zero", "."]
        out.append(_tool("ruff", "project", argv=argv, cwd=repo, src="stdout") if exe else
                   _tool("ruff", "project", status="missing", why=SC.install_hint("ruff")))
    cfg = [f for f in ("mypy.ini", ".mypy.ini") if os.path.isfile(os.path.join(repo, f))]
    sc = _read(os.path.join(repo, "setup.cfg"))
    if cfg or re.search(r"^\[mypy\]", sc, re.M) or re.search(r"^\[tool\.mypy\]", pp, re.M):
        txt = " ".join([pp, sc] + [_read(os.path.join(repo, f)) for f in cfg])
        exe = which("mypy")
        # the error summary carries «checked N source files» (files examined)
        # ⚠Windows has no /dev/null dir semantics (NUL): cache goes to the runner's temp dir, removed after the run
        nt = os.name == "nt"
        argv = [exe, "--show-error-codes", "--no-color-output", "--no-pretty"] + \
            ([] if nt else ["--cache-dir", os.devnull]) + ([] if re.search(r"^\s*files\s*=", txt, re.M) else ["."])
        env = {"env": {"MYPY_CACHE_DIR": TMP_TOKEN}} if nt else {}
        out.append(_tool("mypy", "project", argv=argv, cwd=repo, src="stdout", ok_rc=(0, 1), **env) if exe else
                   _tool("mypy", "project", status="missing", why="install: pip install mypy"))
    return out


_ESL = ("eslint.config.js", "eslint.config.mjs", "eslint.config.cjs", "eslint.config.ts", ".eslintrc", ".eslintrc.js",
        ".eslintrc.cjs", ".eslintrc.json", ".eslintrc.yml", ".eslintrc.yaml")


def jsonc(text):
    """dict from JSON with comments / trailing commas (tsconfig), {} if unreadable. String contents are kept."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            out.append(c)
            i += 1
    try:
        j = json.loads(re.sub(r",(\s*[}\]])", r"\1", "".join(out)))
    except ValueError:
        return {}
    return j if isinstance(j, dict) else {}


def tsc_projects(d):
    """`-p` targets for tsc in package dir d: the referenced configs of a solution-style tsconfig.json
    (references + empty/absent files and include — it checks nothing itself), else ["tsconfig.json"]."""
    j = jsonc(_read(os.path.join(d, "tsconfig.json")))
    refs = j.get("references")
    if not isinstance(refs, list) or not refs or j.get("files") or j.get("include"):
        return ["tsconfig.json"]
    out = []
    for r in refs:
        p = r.get("path") if isinstance(r, dict) else None
        rel = safe_rel(os.path.normpath(p).replace(os.sep, "/")) if isinstance(p, str) else ""
        if rel and os.path.isdir(os.path.join(d, rel)):
            rel += "/tsconfig.json"
        if rel and os.path.isfile(os.path.join(d, rel)) and rel not in out:
            out.append(rel)
    return out or ["tsconfig.json"]


def _node(repo):
    """eslint / tsc, each from the first of root + its direct subdirs (e.g. frontend/) holding package.json and that
    tool's config; local bins only, run with cwd = that package dir. tsc: one plan per `-p` target (merged by id)."""
    try:
        subs = sorted(d for d in os.listdir(repo) if d not in _SKIP and not d.startswith("."))
    except OSError:
        subs = []
    pkgs = [d for d in [repo] + [os.path.join(repo, x) for x in subs] if os.path.isfile(os.path.join(d, "package.json"))]
    esl = next((d for d in pkgs if any(os.path.isfile(os.path.join(d, f)) for f in _ESL)
                or '"eslintConfig"' in _read(os.path.join(d, "package.json"))), None)
    tsd = next((d for d in pkgs if os.path.isfile(os.path.join(d, "tsconfig.json"))), None)
    out = []
    for d, tid, argvs, rc in ((esl, "eslint", [["-f", "json-with-metadata", "."]], (0, 1)),
                              (tsd, "tsc", [["-p", x, "--noEmit", "--pretty", "false", "--incremental", "false",
                                             "--listFiles"]
                                            for x in (tsc_projects(tsd) if tsd else ())], (0, 1, 2))):
        if not d:
            continue
        exe = node_bin(d, tid)
        if not os.path.isfile(exe):
            out.append(_tool(tid, "project", status="missing", why="install: npm install"))
            continue
        # eslint < 8.x lacks json-with-metadata (rule docs): the runner retries a failed run with plain json
        fb = {"fallback": [exe, "-f", "json", "."]} if tid == "eslint" else {}
        out += [_tool(tid, "project", argv=[exe] + a, cwd=d, src="stdout", ok_rc=rc, **fb) for a in argvs]
    return out


_RANK = {"ok": 0, "skipped": 1, "missing": 2, "timeout": 3, "fail": 4}


def merge_tool(a, b):
    """Fold runner entry b into a (same tool id run more than once, e.g. tsc per project): ms / files summed, worst status."""
    a["ms"] = int(a.get("ms") or 0) + int(b.get("ms") or 0)
    a["files"] = int(a.get("files") or 0) + int(b.get("files") or 0)
    if _RANK.get(b["status"], 0) > _RANK.get(a["status"], 0):
        a["status"], a["why"] = b["status"], b.get("why")
    return a


def detect(repo, which=shutil.which):
    """Tool plans for repo: {id, rules, argv, cwd, src: stdout|stderr|reports, reports?, ok_rc?, env?} to run, or
    {id, rules, status: missing|skipped, why}. Only tools the repo itself declares / configures."""
    s = _scan(repo)
    out = _java(repo, s, which) + _py(repo, which) + _node(repo)
    if os.path.isfile(os.path.join(repo, "go.mod")):
        exe = which("go")
        out.append(_tool("govet", "default", argv=[exe, "vet", "./..."], cwd=repo, src="stderr", ok_rc=(0,),
                         env={"GOPROXY": "off"}) if exe else
                   _tool("govet", "default", status="missing", why=SC.install_hint("go")))
    if os.path.isfile(os.path.join(repo, "Cargo.toml")):
        exe = which("cargo")
        out.append(_tool("clippy", "project", argv=[exe, "clippy", "--offline", "--message-format=json", "-q"], cwd=repo,
                         src="stdout", env={"CARGO_TARGET_DIR": TMP_TOKEN}) if exe else
                   _tool("clippy", "project", status="missing", why="install: rustup (cargo clippy)"))
    return out


RUNNABLE_TTL_S = 300
_RUNNABLE = {}   # realpath -> (monotonic at, bool); detect() is a bounded walk + which, too costly per /api/arch fetch


def checks_runnable(repo, which=None, now=None):
    """True when detect(repo) plans at least one tool with an argv (not missing/skipped). Cached per repo for
    RUNNABLE_TTL_S. ⚠The «Run project checks» button only offers checks the repo configures: the runner has no
    default-tool fallback, so a repo with none would get an empty run."""
    k, t = os.path.realpath(repo), time.monotonic() if now is None else now
    hit = _RUNNABLE.get(k)
    if hit and 0 <= t - hit[0] < RUNNABLE_TTL_S:
        return hit[1]
    try:
        ok = any(p.get("argv") for p in detect(k, which or shutil.which))
    except (OSError, ValueError):
        ok = False
    if len(_RUNNABLE) > 64:
        _RUNNABLE.clear()
    _RUNNABLE[k] = (t, ok)
    return ok


def find_reports(repo, specs, newer=0.0):
    """Report files under repo: spec (dir_suffix, name|None) = any .xml in a dir ending with dir_suffix, or that name."""
    out, n = [], 0
    for dp, dns, fns in os.walk(repo):
        r = os.path.relpath(dp, repo).replace(os.sep, "/")
        depth = 0 if r == "." else r.count("/") + 1
        base = os.path.basename(dp)
        # ⚠build/ and target/ hold the reports: enter build/ only for reports/, never below target/ (class trees are huge).
        dns[:] = [] if depth >= _WALK_DEPTH + 2 or base == "target" else \
            [d for d in dns if d == "reports"] if base == "build" else \
            sorted(d for d in dns if d in ("build", "target") or (d not in _SKIP and not d.startswith(".")))
        n += 1
        if n > _WALK_DIRS:
            break
        for suf, name in specs:
            if r == suf or r.endswith("/" + suf):
                for f in fns:
                    fp = os.path.join(dp, f)
                    try:
                        fresh = os.path.getmtime(fp) >= newer
                    except OSError:
                        continue
                    if fresh and (f == name if name else f.endswith(".xml")):
                        out.append(fp)
    return sorted(out)


def rel_path(p, repo, cwd=None):
    """Repo-relative path of a tool-reported path (absolute or relative to cwd), "" if outside the repo."""
    if not isinstance(p, str) or not p or "\0" in p:
        return ""
    a = os.path.realpath(p if os.path.isabs(p) else os.path.join(cwd or repo, p))
    r = os.path.relpath(a, repo).replace(os.sep, "/")
    return "" if r.startswith("..") else safe_rel(r)


_LANG_EXT = {"pmd": (".java",), "spotbugs": (".java",), "ruff": (".py", ".pyi"), "govet": (".go",), "clippy": (".rs",)}


def lang_files(d, exts):
    """Files ending in exts under d (same _SKIP walk and bounds as _scan)."""
    n, dirs = 0, 0
    for dp, dns, fns in os.walk(d):
        rel = os.path.relpath(dp, d)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        dns[:] = sorted(x for x in dns if x not in _SKIP and not x.startswith(".")) if depth < _WALK_DEPTH else []
        dirs += 1
        if dirs > _WALK_DIRS:
            break
        n += sum(1 for f in fns if f.endswith(exts))
    return n


def tsc_files(text, repo, cwd):
    """`--listFiles` lines that are in-repo paths outside node_modules (diagnostic lines are not paths)."""
    n = 0
    for ln in text.splitlines():
        r = rel_path(ln.strip(), repo, cwd) if ln.strip() and not PARSERS["tsc"](ln) else ""
        n += bool(r) and "node_modules" not in r.split("/")
    return n


def _files(plan, res, repo, fs):
    """Files the tool examined (count only). fs = report files of a `reports` plan."""
    tid, out = plan["id"], res.get("out") or ""
    if tid in SC.SEC_IDS:
        return SC.files(plan, res, repo)
    if tid == "checkstyle":
        return sum(checkstyle_files(_read(fp, OUT_MAX)) for fp in fs) if fs is not None else checkstyle_files(out)
    if tid == "eslint":
        return eslint_files(out)
    if tid == "mypy":
        return mypy_files(out + "\n" + (res.get("err") or ""))
    if tid == "tsc":
        return tsc_files(out, repo, plan.get("cwd"))
    return lang_files(plan.get("cwd") or repo, _LANG_EXT.get(tid, ()))


def judge(plan, res, repo):
    """(status, why|None, items, files) of one plan from the runner's result {rc, out, err, timeout, t0};
    files = files examined (0 unless ok)."""
    st, why, items, fs = _judge(plan, res, repo)
    if st != "ok":
        return st, why, items, 0
    try:
        return st, why, items, _files(plan, res, repo, fs)
    except ValueError:
        return st, why, items, 0


def _judge(plan, res, repo):
    fs = None
    if res.get("timeout"):
        return "timeout", "over %d s" % TOOL_TIMEOUT_S, [], fs
    if res.get("rc") == 127 and res.get("nostart"):
        return "fail", "cannot start", [], fs
    if SC.net_fail(plan, res):
        return "skipped", SC.WHY_NET_FAIL, [], fs
    rc, blob = res.get("rc"), (res.get("out") or "") + (res.get("err") or "")
    parse = PARSERS.get(plan["id"]) or SC.PARSERS[plan["id"]]
    try:
        if plan["src"] == "report":
            raw = parse(SC.take_report(plan))
        elif plan["src"] == "reports":
            fs = find_reports(repo, plan["reports"], res.get("t0", 0) - 1)
            if not fs and rc == 0:
                fs = find_reports(repo, plan["reports"])    # task up to date: its old report matches the inputs
            if not fs:
                return "fail", WHY_OFFLINE if OFFLINE_RE.search(blob) else "no report (exit %s)" % rc, [], None
            raw = [x for fp in fs for x in parse(_read(fp, OUT_MAX))]
        else:
            raw = parse(res.get("err" if plan["src"] == "stderr" else "out") or "")
    except ValueError:
        return "fail", WHY_OFFLINE if OFFLINE_RE.search(blob) else "unreadable output (exit %s)" % rc, [], fs
    ok_rc = plan.get("ok_rc", (0,))
    if ok_rc is not None and rc not in ok_rc and not raw:
        return "fail", WHY_OFFLINE if OFFLINE_RE.search(blob) else "exit %s" % rc, [], fs
    items = []
    for x in raw:
        f = rel_path(x["file"], repo, plan.get("cwd"))
        if f and RULE_RE.fullmatch(x["rule"]) and os.path.isfile(os.path.join(repo, f)):
            items.append(dict(x, file=f, tool=plan["id"]))
    return "ok", None, items, fs


def build(repo, commit, dirty, src_changed, at, tools, items):
    """checks.json v1 dict. tools = [{id, rules, status, why?, ms, files}] (n added here); items errors first, capped."""
    files, n = {}, {}
    for x in items:
        c = files.setdefault(x["file"], {"error": 0, "warning": 0})
        c[x["sev"]] += 1
        n.setdefault(x["tool"], {"error": 0, "warning": 0})[x["sev"]] += 1
    out_t = []
    for t in tools:
        e = {"id": t["id"], "rules": t["rules"], "status": t["status"], "ms": int(t.get("ms") or 0),
             "files": int(t.get("files") or 0), "n": n.get(t["id"], {"error": 0, "warning": 0})}
        if t.get("why"):
            e["why"] = t["why"][:WHY_MAX]
        out_t.append(e)
    its = sorted(items, key=lambda x: (x["sev"] != "error", x["file"], x["line"], x["tool"]))[:ITEMS_MAX]
    rules = {}
    for x in its:   # help only for rules that reach the stored items; first finding's metadata wins
        h = clean_help((x.get("help") or {}).get("desc"), (x.get("help") or {}).get("url"))
        if h:
            rules.setdefault(x["tool"] + ":" + x["rule"], h)
    return {"v": 1, "repo": repo, "commit": commit, "dirty": bool(dirty), "src_changed": bool(src_changed), "at": at,
            "tools": out_t, "files": dict(sorted(files.items())[:FILES_MAX]),
            "items": [dict({"tool": x["tool"], "file": x["file"], "line": x["line"], "rule": x["rule"], "sev": x["sev"]},
                           **({"pkg": x["pkg"]} if x.get("pkg") else {})) for x in its], "rules": rules}


# ── schema (gate) and page loader ──

def _nat(x):
    return isinstance(x, int) and not isinstance(x, bool) and x >= 0


def _cnt(c):
    return isinstance(c, dict) and set(c) == {"error", "warning"} and \
        all(isinstance(c[k], int) and not isinstance(c[k], bool) and c[k] >= 0 for k in SEVS)


def checks_errors(j, repo=None, commit=None, ids=TOOL_IDS):
    """Strict schema errors of a checks.json dict (gate; ids = SC.SEC_IDS for checks-security.json). Unknown keys are
    refused so no text can ride along."""
    if not isinstance(j, dict):
        return ["top level must be an object"]
    errs = []
    if set(j) - {"rules"} != {"v", "repo", "commit", "dirty", "src_changed", "at", "tools", "files", "items"}:
        errs.append("keys")
    rs = j.get("rules", {})
    if not isinstance(rs, dict) or len(rs) > ITEMS_MAX or any(_rule_key(k, ids) != k or not isinstance(v, dict)
                                                              or clean_help(v.get("desc"), v.get("url")) != v
                                                              for k, v in rs.items()):
        errs.append("rules")
    if j.get("v") != 1:
        errs.append("v must be 1")
    if not isinstance(j.get("repo"), str) or (repo and os.path.realpath(j.get("repo") or "") != os.path.realpath(repo)):
        errs.append("repo")
    if not (isinstance(j.get("commit"), str) and COMMIT_RE.fullmatch(j["commit"])) or (commit and j.get("commit") != commit):
        errs.append("commit")
    if not isinstance(j.get("at"), (int, float)) or isinstance(j.get("at"), bool):
        errs.append("at")
    for i, t in enumerate(j.get("tools") if isinstance(j.get("tools"), list) else [None]):
        if not (isinstance(t, dict) and set(t) - {"why"} == {"id", "rules", "status", "ms", "files", "n"}
                and t["id"] in ids and _nat(t["files"])
                and t["rules"] in ("project", "default") and t["status"] in STATUSES and _cnt(t["n"])
                and isinstance(t["ms"], int) and not isinstance(t["ms"], bool) and (not isinstance(t.get("why"), str) or len(t["why"]) <= WHY_MAX)
                and (t.get("why") is None or isinstance(t.get("why"), str))):
            errs.append("tools[%d]" % i)
    fs = j.get("files")
    if not isinstance(fs, dict) or any(safe_rel(k) != k or not _cnt(c) for k, c in fs.items()):
        errs.append("files")
    its = j.get("items")
    if not isinstance(its, list) or len(its) > ITEMS_MAX or any(_clean_item(x, ids) != x for x in its):
        errs.append("items")
    return errs


def _rule_key(k, ids=TOOL_IDS):
    """`<tool>:<rule>` help key, "" if malformed (rules may contain ':' themselves, e.g. clippy::x)."""
    t, _c, r = k.partition(":") if isinstance(k, str) else ("", "", "")
    return k if t in ids and RULE_RE.fullmatch(r) else ""


def _clean_item(x, ids=TOOL_IDS):
    if not isinstance(x, dict) or x.get("tool") not in ids or x.get("sev") not in SEVS:
        return None
    f, r, ln, pk = safe_rel(x.get("file")), x.get("rule"), x.get("line"), x.get("pkg")
    if not f or not (isinstance(r, str) and RULE_RE.fullmatch(r)) or not isinstance(ln, int) or isinstance(ln, bool) or ln < 0:
        return None
    if "pkg" in x and not (isinstance(pk, str) and SC.PKG_RE.fullmatch(pk)):
        return None
    return dict({"tool": x["tool"], "file": f, "line": ln, "rule": r, "sev": x["sev"]}, **({"pkg": pk} if "pkg" in x else {}))


def aggregate(files, mods, globs):
    """({module id: {error, warning}}, other) — each file counts for its first owning module, else `other`."""
    ms = [d for d in mods if isinstance(d, dict) and d.get("kind") == "module"]
    out, other = {}, {"error": 0, "warning": 0}
    for f, c in files.items():
        o = next((d["id"] for d in ms if owns(d, f, globs)), None)
        t = out.setdefault(o, {"error": 0, "warning": 0}) if o else other
        for k in SEVS:
            t[k] += c[k]
    return out, other


def _newest(rdir, name=CHECKS_FILE):
    best, at = "", -1.0
    try:
        names = os.listdir(rdir)
    except OSError:
        return ""
    for c in names:
        if COMMIT_RE.fullmatch(c):
            try:
                t = os.path.getmtime(os.path.join(rdir, c, name))
            except OSError:
                continue
            if t > at:
                best, at = c, t
    return best


def load_checks(root, map_dir, m, head=""):
    """`/api/arch` `checks`: newest checks.json of root's store (sibling commit dirs of map_dir), sanitised and
    rolled up onto the map's modules, + `security` (same shape from checks-security.json, else None); None when
    neither exists. Security alone gives an empty quality shell (commit "", no tools)."""
    q = _load_one(root, map_dir, m, head, CHECKS_FILE, TOOL_IDS)
    s = _load_one(root, map_dir, m, head, SC.SEC_FILE, SC.SEC_IDS)
    if not q and not s:
        return None
    return dict(q or {"commit": "", "at": None, "stale": False, "dirty": False, "src_changed": False, "tools": [],
                      "mods": {}, "other": {"error": 0, "warning": 0}, "top": [], "rules": {}}, security=s)


def _load_one(root, map_dir, m, head, name, ids):
    rdir = os.path.dirname(map_dir)
    c = _newest(rdir, name)
    if not c:
        return None
    try:
        j = read_json(os.path.join(rdir, c, name))
    except (OSError, ValueError):
        return None
    if not isinstance(j, dict) or j.get("v") != 1 or j.get("commit") != c or not isinstance(j.get("repo"), str) \
            or os.path.realpath(j["repo"]) != os.path.realpath(root):
        return None
    tools = []
    for t in j.get("tools") if isinstance(j.get("tools"), list) else ():
        if isinstance(t, dict) and t.get("id") in ids and t.get("status") in STATUSES:
            n = t.get("n") if _cnt(t.get("n")) else {"error": 0, "warning": 0}
            ms = t.get("ms") if isinstance(t.get("ms"), int) and not isinstance(t.get("ms"), bool) else 0
            e = {"id": t["id"], "rules": "project" if t.get("rules") == "project" else "default", "status": t["status"],
                 "ms": ms, "files": t["files"] if _nat(t.get("files")) else 0, "n": {"error": n["error"], "warning": n["warning"]}}
            why = t.get("why")
            if isinstance(why, str) and why:
                e["why"] = "".join(ch for ch in why[:WHY_MAX] if ord(ch) >= 32)
            tools.append(e)
    fs = j.get("files") if isinstance(j.get("files"), dict) else {}
    files = {k: {"error": v["error"], "warning": v["warning"]} for k, v in list(fs.items())[:FILES_MAX]
             if safe_rel(k) == k and _cnt(v)}
    try:
        globs = plan_globs(read_json(os.path.join(map_dir, "plan.json")))
    except (OSError, ValueError):
        globs = {}
    mods_l = m.get("modules") if isinstance(m, dict) and isinstance(m.get("modules"), list) else []
    mods, other = aggregate(files, mods_l, globs)
    rs = j.get("rules") if isinstance(j.get("rules"), dict) else {}
    top, rules = [], {}
    for x in j.get("items") if isinstance(j.get("items"), list) else ():
        y = _clean_item(x, ids)
        if y:
            rk = y["tool"] + ":" + y["rule"]
            h = rs.get(rk) if _rule_key(rk, ids) else None
            h = clean_help(h.get("desc"), h.get("url")) if isinstance(h, dict) else None
            if h:
                rules[rk] = h
            top.append(dict(y, rk=rk if h else "", mod=next((d["id"] for d in mods_l if isinstance(d, dict)
                                                             and d.get("kind") == "module" and owns(d, y["file"], globs)), "")))
        if len(top) >= TOP_MAX:
            break
    at = j.get("at")
    return {"commit": c, "at": at if isinstance(at, (int, float)) and not isinstance(at, bool) else None,
            "stale": bool(head) and head != c, "dirty": j.get("dirty") is True, "src_changed": j.get("src_changed") is True,
            "tools": tools, "mods": mods, "other": other, "top": top, "rules": rules}
