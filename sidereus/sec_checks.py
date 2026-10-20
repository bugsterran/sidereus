"""Security checks for the runner `scripts/arch_checks.py --category security`: tool plans, report parsers, files
examined and network gating. Checks file v2 schema (sidereus/arch_checks.py) plus item `pkg`, stored as
checks-security.json.

⚠Secrets: gitleaks findings keep RuleID / File / StartLine only — Secret, Match, Line and message are never read into
results, logs or relays. Its report lives in the runner's temp dir and is deleted right after parsing (`take_report`).
⚠No subprocess here (AGENTS.md rule 7). Advisory lookups (npm audit, osv-scanner, semgrep registry packs) need the
network: planned unless the runner is offline (probe failed or `--offline`), and a network error is `skipped`,
never `0 issues`. Stdlib only, Python 3.9.
"""
import json
import os
import re
import sys

from sidereus import arch_verify as AV
from sidereus.arch_checks_parse import SEV_RANK, SEVS, clean_help, level
from sidereus.arch_verify import COMMIT_RE, safe_rel

# install hints per OS: (macOS, Windows, Linux). ⚠each fits why's 60-char cap (arch_checks.WHY_MAX).
HINTS = {
    "gitleaks": ("brew install gitleaks", "winget install Gitleaks.Gitleaks (or scoop)",
                 "github.com/gitleaks/gitleaks/releases"),
    "osv-scanner": ("brew install osv-scanner", "winget install Google.OSVScanner (or go install)",
                    "github.com/google/osv-scanner/releases"),
    "semgrep": ("brew install semgrep", "pip install semgrep (Windows beta; prefer WSL)", "pip install semgrep"),
    "java": ("brew install checkstyle pmd", "checkstyle + pmd releases (GitHub download)",
             "checkstyle + pmd releases (GitHub download)"),
    "ruff": ("brew install ruff", "pip install ruff", "pip install ruff"),
    "go": ("brew install go", "winget install GoLang.Go", "go.dev/dl (or the package manager)"),
    "bandit": ("brew install bandit", "pip install bandit", "pip install bandit"),
    "npm": ("brew install node", "winget install OpenJS.NodeJS.LTS", "nodejs.org"),
}


def install_hint(tool):
    """«install: …» for the OS this runs on (read at call time so tests can patch os.name / sys.platform)."""
    mac, win, lin = HINTS[tool]
    return "install: " + (win if os.name == "nt" else mac if sys.platform == "darwin" else lin)


def install_cmd(tool):
    """This OS's HINTS entry without its trailing « (…)» note: a copyable command (or a URL) for Settings «Security tools»."""
    return re.sub(r" \([^()]*\)$", "", install_hint(tool)[len("install: "):])

SEC_IDS = ("gitleaks", "npm-audit", "osv-scanner", "semgrep", "bandit")
SEC_FILE = "checks-security.json"
SEC_LAST = "_checks_last_security.json"   # {repo, commit} of the newest security run (gate `--verify --last --category security`)
CATEGORIES = ("security",)
PKG_RE = re.compile(r"[A-Za-z0-9@/._+:-]{1,100}")
NET_RE = re.compile(r"ENOTFOUND|EAI_AGAIN|ECONNREFUSED|ECONNRESET|ETIMEDOUT|ENETUNREACH|no such host|dial tcp|"
                    r"network is unreachable|getaddrinfo|Max retries exceeded|Failed to resolve|"
                    r"nodename nor servname|Temporary failure in name resolution", re.I)
WHY_NET = "offline (network unreachable or --offline)"
WHY_NET_FAIL = "needs network"
_RULE = re.compile(r"[A-Za-z0-9_./@:-]{1,60}")      # same shape as arch_checks.RULE_RE
_GHSA = re.compile(r"GHSA(?:-[a-z0-9]{4}){3}")
CVE_RE = re.compile(r"CVE-\d{4}-\d{4,7}")
CVE_MAX = 3   # extra CVE aliases shown next to the rule; ⚠never part of the finding key (rule stays GHSA-first)
_SCANNED = re.compile(r"scanned ~?(\d[\d,]*) bytes")
_OSV_N = re.compile(r"Scanned .+? file and found (\d+) packages?")
_LOCKS = ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Pipfile.lock", "uv.lock", "requirements.txt",
          "go.sum", "Cargo.lock", "Gemfile.lock", "composer.lock", "gradle.lockfile", "buildscript-gradle.lockfile",
          "pom.xml", "libs.versions.toml")   # ⚠osv-scanner reads none of build.gradle(.kts): those are BUILDS only
_GRADLE_META = "verification-metadata.xml"   # counts only directly under a `gradle/` folder
_BUILDS = ("build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts")
WHY_GRADLE = "Gradle without lockfile: gradle dependencies --write-locks"   # ⚠must not match sec_report._NET
WHY_NO_DEPS = "no dependency manifest"
_SEMGREP_CFG = (".semgrep.yml", ".semgrep.yaml", ".semgrep")
SEMGREP_PACKS = ("p/python", "p/javascript", "p/secrets")   # registry packs used online when no local config
_SKIP = {".git", "node_modules", "build", "target", ".gradle", "dist", "out", ".venv", "venv", "__pycache__", ".idea",
         ".mvn", ".tox", ".mypy_cache", ".ruff_cache"}
_WALK_DIRS, _WALK_DEPTH = 5000, 6


def scan(repo):
    """One bounded walk: files counted, python present, lockfile present."""
    s = {"n": 0, "py": False, "lock": False, "build": False}
    dirs = 0
    for dp, dns, fns in os.walk(repo):
        rel = os.path.relpath(dp, repo)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        dns[:] = sorted(d for d in dns if d not in _SKIP and not d.startswith(".")) if depth < _WALK_DEPTH else []
        dirs += 1
        if dirs > _WALK_DIRS:
            break
        s["n"] += len(fns)
        s["py"] = s["py"] or any(f.endswith(".py") for f in fns)
        s["lock"] = s["lock"] or any(f in _LOCKS for f in fns) or (
            os.path.basename(dp) == "gradle" and _GRADLE_META in fns)
        s["build"] = s["build"] or any(f in _BUILDS for f in fns)
    return s


def _tool(tid, rules, **kw):
    return dict({"id": tid, "rules": rules}, **kw)


def _read(fp, n=262144):
    try:
        with open(fp, encoding="utf-8", errors="replace") as f:
            return f.read(n)
    except OSError:
        return ""


def _npm_dirs(repo):
    """Root + direct subfolders holding package-lock.json (e.g. frontend/)."""
    try:
        subs = sorted(d for d in os.listdir(repo) if d not in _SKIP and not d.startswith("."))
    except OSError:
        subs = []
    return [d for d in [repo] + [os.path.join(repo, x) for x in subs] if os.path.isfile(os.path.join(d, "package-lock.json"))]


def detect(repo, which, net=False):
    """Security tool plans: {id, rules, argv, cwd, src, ...} or {id, rules, status, why}. `src: report` = gitleaks'
    report file (see bind)."""
    s, out = scan(repo), []
    exe = which("gitleaks")
    gl = "project" if os.path.isfile(os.path.join(repo, ".gitleaks.toml")) else "default"
    out.append(_tool("gitleaks", gl, argv=[exe, "dir", repo, "--redact", "--no-banner", "--report-format", "json"],
                     cwd=repo, src="report", ok_rc=(0, 1)) if exe else
               _tool("gitleaks", gl, status="missing", why=install_hint("gitleaks")))
    npm = _npm_dirs(repo)
    if npm and not net:
        out.append(_tool("npm-audit", "default", status="skipped", why=WHY_NET))
    elif npm:
        exe = which("npm")
        out += [_tool("npm-audit", "default", argv=[exe, "audit", "--json"], cwd=d, src="stdout", ok_rc=(0, 1), net=True)
                for d in npm] if exe else [_tool("npm-audit", "default", status="missing", why="install: node (npm)")]
    if s["lock"]:
        exe = which("osv-scanner")
        out.append(_tool("osv-scanner", "default", status="skipped", why=WHY_NET) if not net else
                   _tool("osv-scanner", "default", argv=[exe, "--format", "json", "-r", "."], cwd=repo, src="stdout",
                         ok_rc=(0, 1), net=True) if exe else
                   _tool("osv-scanner", "default", status="missing", why=install_hint("osv-scanner")))
    else:   # ⚠keep the row: a missing row reads as «dependencies clean» on screen and in the report
        out.append(_tool("osv-scanner", "default", status="skipped", why=WHY_GRADLE if s["build"] else WHY_NO_DEPS))
    exe = which("semgrep")
    cfg = next((c for c in _SEMGREP_CFG if os.path.exists(os.path.join(repo, c))), None)
    tail = ["--json", "--metrics=off", "--disable-version-check", "--quiet", "."]
    # ⚠not `--config auto`: semgrep refuses auto with --metrics=off, so name registry packs explicitly.
    reg = [a for p in SEMGREP_PACKS for a in ("--config", p)]
    out.append(_tool("semgrep", "project", status="missing", why=install_hint("semgrep")) if not exe else
               _tool("semgrep", "project", argv=[exe, "scan", "--config", cfg] + tail, cwd=repo, src="stdout",
                     ok_rc=(0, 1)) if cfg else
               _tool("semgrep", "default", argv=[exe, "scan"] + reg + tail, cwd=repo, src="stdout", ok_rc=(0, 1),
                     net=True) if net else
               _tool("semgrep", "project", status="skipped", why="no local rules; registry packs offline"))
    if s["py"]:
        exe = which("bandit")
        own = bool(re.search(r"^\[tool\.bandit\]", _read(os.path.join(repo, "pyproject.toml")), re.M))
        argv = [exe, "-r", ".", "-f", "json", "-q", "-x", ",".join("./" + d for d in sorted(_SKIP))] + \
            (["-c", "pyproject.toml"] if own else [])
        out.append(_tool("bandit", "project" if own else "default", argv=argv, cwd=repo, src="stdout", ok_rc=(0, 1))
                   if exe else _tool("bandit", "default", status="missing", why="install: pip install bandit"))
    return out


def bind(plan, tmp):
    """Plan with its report path inside the runner's temp dir (gitleaks writes the report there, never stdout)."""
    rp = os.path.join(tmp, "%s-report.json" % plan["id"])
    return dict(plan, argv=list(plan["argv"]) + ["--report-path", rp], report=rp)


def take_report(plan):
    """Report text, then the file is removed. ⚠It holds the redacted secret context: never kept, logged or copied."""
    rp = plan.get("report") or ""
    try:
        with open(rp, encoding="utf-8", errors="replace") as f:
            return f.read(32 * 1024 * 1024)
    except OSError:
        raise ValueError("no report")
    finally:
        _rm(rp)


def _rm(fp):
    """Remove fp; False when it was already gone (nothing to report: the runner's rmtree is the backstop)."""
    try:
        os.remove(fp)
    except OSError:
        return False
    return True


def net_fail(plan, res):
    """True when a network tool failed for lack of network (DNS / connect errors) — judged `skipped`, not `fail`."""
    if not plan.get("net") or res.get("rc") == 0:
        return False
    txt, e = res.get("err") or "", _jd(res.get("out")).get("error")
    if isinstance(e, dict):
        txt += " %s %s" % (e.get("code"), e.get("summary"))
    return bool(NET_RE.search(txt))


def cves(xs):
    """Sorted, deduped CVE ids (capped) from an id list; anything not shaped like a CVE id is dropped."""
    return sorted({x for x in xs if isinstance(x, str) and CVE_RE.fullmatch(x)})[:CVE_MAX]


def _it(f, line, rule, sev, pkg=None, url=None, desc=None, cve=()):
    try:
        ln = max(0, int(line))
    except (TypeError, ValueError):
        ln = 0
    r = rule if isinstance(rule, str) else ""
    if len(r) > 60 and "." in r:   # semgrep ids are dotted paths: keep the rule's own name
        r = r.rsplit(".", 1)[-1]
    x = {"file": f if isinstance(f, str) else "", "line": ln, "rule": r, "sev": sev}
    if isinstance(pkg, str) and PKG_RE.fullmatch(pkg):
        x["pkg"] = pkg
    cv = cves(cve or ())
    if cv:
        x["cve"] = cv
    h = clean_help(desc, url)
    if h:
        x["help"] = h
    return x


def _json(text):
    try:
        return json.loads(text)
    except ValueError:
        raise ValueError("bad json")


def parse_gitleaks(text):
    """⚠Reads RuleID / File / StartLine only — Secret, Match, Line, message stay unread."""
    j = _json(text)
    if not isinstance(j, list):
        raise ValueError("gitleaks: not a list")
    return [_it(x.get("File"), x.get("StartLine"), x.get("RuleID"), _lv("gitleaks", None)) for x in j if isinstance(x, dict)]


_WORD = {"critical": "critical", "high": "high", "moderate": "medium", "medium": "medium", "low": "low", "info": "low",
         "error": "high", "warning": "medium"}


def _lv(tool, raw):
    """Level of one finding from the tool's own severity field (osv: (cvss score, GHSA label)); unknown -> medium."""
    if tool == "gitleaks":
        return "high"   # a committed secret has no tool severity
    if tool == "osv-scanner":
        score, label = raw
        try:
            s = float(score)
        except (TypeError, ValueError):
            s = None
        if s is not None and s > 0:
            return "critical" if s >= 9.0 else "high" if s >= 7.0 else "medium" if s >= 4.0 else "low"
        raw = label
    return _WORD.get(str(raw or "").lower(), "medium")


def parse_npm_audit(text):
    """npm 7+ `vulnerabilities` (advisories in `via`) or npm 6 `advisories`; file = the lockfile, line 1."""
    j = _json(text)
    if not isinstance(j, dict):
        raise ValueError("npm audit: not an object")
    out, seen = [], set()

    def add(rule, pkg, sev, url, cv=()):
        if (rule, pkg) not in seen:
            seen.add((rule, pkg))
            out.append(_it("package-lock.json", 1, rule, _lv("npm-audit", sev), pkg, url, None, cv))
    for name, v in (j.get("vulnerabilities") or {}).items() if isinstance(j.get("vulnerabilities"), dict) else ():
        for via in (v.get("via") or ()) if isinstance(v, dict) else ():
            if isinstance(via, dict):   # string entries name another vulnerable package (listed on its own)
                url = via.get("url") if isinstance(via.get("url"), str) else ""
                m = _GHSA.search(url)
                add(m.group(0) if m else str(via.get("source")), via.get("name") or name, via.get("severity"), url,
                    via.get("cves") if isinstance(via.get("cves"), list) else ())
    for a in (j.get("advisories") or {}).values() if isinstance(j.get("advisories"), dict) else ():
        if isinstance(a, dict):
            url = a.get("url") if isinstance(a.get("url"), str) else ""
            m = _GHSA.search(url + " " + str(a.get("github_advisory_id") or ""))
            add(m.group(0) if m else str(a.get("id")), a.get("module_name"), a.get("severity"), url,
                a.get("cves") if isinstance(a.get("cves"), list) else ())
    return out


def parse_osv(text):
    j = _json(text)
    if not isinstance(j, dict):
        raise ValueError("osv-scanner: not an object")
    out = []
    for r in j.get("results") or ():
        path = ((r.get("source") or {}).get("path")) if isinstance(r, dict) else None
        for p in (r.get("packages") or ()) if isinstance(r, dict) else ():
            if not isinstance(p, dict):
                continue
            name = (p.get("package") or {}).get("name")
            groups = [g for g in p.get("groups") or () if isinstance(g, dict)]
            for v in p.get("vulnerabilities") or ():
                if not isinstance(v, dict) or not isinstance(v.get("id"), str):
                    continue
                ids = [v["id"]] + [a for a in v.get("aliases") or () if isinstance(a, str)]
                rule = next((i for i in ids if _GHSA.fullmatch(i)), v["id"])
                sv = str((v.get("database_specific") or {}).get("severity") or "")
                g = next((g for g in groups if v["id"] in (g.get("ids") or ())), {})
                out.append(_it(path, 1, rule, _lv("osv-scanner", (g.get("max_severity"), sv)), name,
                               "https://osv.dev/vulnerability/" + v["id"] if _RULE.fullmatch(v["id"]) else None, None, ids))
    return out


def parse_semgrep(text):
    j = _json(text)
    if not isinstance(j, dict):
        raise ValueError("semgrep: not an object")
    out = []
    for x in j.get("results") or ():
        if isinstance(x, dict):
            ex = x.get("extra") if isinstance(x.get("extra"), dict) else {}
            md = ex.get("metadata") if isinstance(ex.get("metadata"), dict) else {}
            out.append(_it(x.get("path"), (x.get("start") or {}).get("line"), x.get("check_id"),
                           _lv("semgrep", ex.get("severity")), None, md.get("source")))
    return out


def parse_bandit(text):
    """⚠`code` and `issue_text` (source and message) are never read."""
    j = _json(text)
    if not isinstance(j, dict):
        raise ValueError("bandit: not an object")
    out = []
    for x in j.get("results") or ():
        if isinstance(x, dict):
            tn = x.get("test_name") if isinstance(x.get("test_name"), str) else ""
            out.append(_it(x.get("filename"), x.get("line_number"), x.get("test_id"), _lv("bandit", x.get("issue_severity")),
                           None, x.get("more_info"), tn.replace("_", " ")))
    return out


PARSERS = {"gitleaks": parse_gitleaks, "npm-audit": parse_npm_audit, "osv-scanner": parse_osv, "semgrep": parse_semgrep,
           "bandit": parse_bandit}


def _jd(text):
    try:
        j = json.loads(text or "")
    except ValueError:
        return {}
    return j if isinstance(j, dict) else {}


def files(plan, res, repo):
    """Files the tool examined (count only); 0 means the tool did no work (gate EMPTY)."""
    tid, out, err = plan["id"], res.get("out") or "", res.get("err") or ""
    if tid == "gitleaks":   # ⚠a run that read nothing still writes «[]»: require its «scanned ~N bytes» with N > 0
        m = _SCANNED.search(err + "\n" + out)
        return scan(repo)["n"] if m and int(m.group(1).replace(",", "")) > 0 else 0
    if tid == "npm-audit":
        dep = (_jd(out).get("metadata") or {}).get("dependencies")
        tot = dep.get("total") if isinstance(dep, dict) else dep
        return 1 if isinstance(tot, int) and tot > 0 else 0
    if tid == "osv-scanner":
        return sum(1 for m in _OSV_N.finditer(err + "\n" + out) if int(m.group(1)) > 0)
    if tid == "semgrep":
        sc = (_jd(out).get("paths") or {}).get("scanned")
        return len(sc) if isinstance(sc, list) else 0
    if tid == "bandit":
        mt = _jd(out).get("metrics")
        return len([k for k in mt if k != "_totals"]) if isinstance(mt, dict) else 0
    return 0


def drop_ignored(items, ignored):
    """items minus those under a gitignored path. ignored = `git ls-files -z -o -i --exclude-standard --directory`.
    ⚠Gitignored files (often .env) are skipped on purpose — not committed; never hard-code dot-dirs (would hide committed .github/.env)."""
    ig = [p for p in (ignored or "").split("\0") if p]
    dirs, exact = tuple(p for p in ig if p.endswith("/")), set(p for p in ig if not p.endswith("/"))
    return [x for x in items if x["file"] not in exact and not x["file"].startswith(dirs)]


# ── security log: append-only history of scan / AI-review findings and their later status ──
# ⚠Metadata only: sev · file:line · key · one-line desc. Never Match / Secret / message text or source lines.
# Status is computed on read (log_view), never rewritten. Identity = (src, key, file), not line (lines move).
LOG_FILE = "security-log.jsonl"   # in arch/<repo key>/, beside the per-commit dirs
LOG_LINES = 500                   # only the newest lines are read
LOG_TAIL_BYTES = 4 * 1024 * 1024
LOG_ITEMS_MAX, LOG_DESC_MAX = 200, 160
MARKS = ("resolved", "false-positive")
SLUG_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,59}")


def log_dir(repo):
    """arch/<repo key>/ (parent of arch_verify.store_dir); ARCH_DIR is read at call time so tests can patch it."""
    return os.path.join(AV.ARCH_DIR, AV.repo_key(repo))


def _desc(s):
    return "".join(c for c in s if ord(c) >= 32 and ord(c) != 127).strip()[:LOG_DESC_MAX] if isinstance(s, str) else ""


def _log_item(x, src):
    """Clean finding {sev, file, line, key, desc} or None (unsafe path, bad key / severity).
    Scan and review rows alike read v1 error/warning as high/medium (level())."""
    if not isinstance(x, dict):
        return None
    f, ln, k, sv = safe_rel(x.get("file")), x.get("line"), x.get("key"), level(x.get("sev"))   # old error/warning lines read as levels
    if src == "scan":
        t, _c, r = k.partition(":") if isinstance(k, str) else ("", "", "")
        ok_k = t in SEC_IDS and bool(_RULE.fullmatch(r))
    else:
        ok_k = isinstance(k, str) and bool(SLUG_RE.fullmatch(k))
    if not (f and ok_k and sv and isinstance(ln, int) and not isinstance(ln, bool) and ln >= 0):
        return None
    return {"sev": sv, "file": f, "line": ln, "key": k, "desc": _desc(x.get("desc"))}


def scan_record(commit, at, tools_ok, items):
    """Scan record from checks-security items; tools_ok = ids that ran ok (only those can resolve their findings)."""
    its = [_log_item({"sev": x.get("sev"), "file": x.get("file"), "line": x.get("line"),
                      "key": "%s:%s" % (x.get("tool"), x.get("rule")), "desc": x.get("rule")}, "scan") for x in items]
    return {"v": 1, "at": at, "commit": commit, "src": "scan", "tools": sorted(t for t in set(tools_ok) if t in SEC_IDS),
            "items": [x for x in its if x][:LOG_ITEMS_MAX]}


def review_record(commit, at, items):
    its = [_log_item(x, "review") for x in items]
    return {"v": 1, "at": at, "commit": commit, "src": "review", "items": [x for x in its if x][:LOG_ITEMS_MAX]}


def mark_record(commit, at, key, file, status):
    return {"v": 1, "at": at, "commit": commit, "src": "mark", "key": key, "file": file, "status": status, "by": "cli"}


def log_append(kdir, rec):
    """Append one record line; False on any failure (callers never change their exit code on it)."""
    try:
        os.makedirs(kdir, exist_ok=True)
        with open(os.path.join(kdir, LOG_FILE), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
    except (OSError, TypeError, ValueError):
        return False
    return True


def _valid(r):
    """Cleaned record or None (corrupt / foreign lines are skipped)."""
    if not isinstance(r, dict) or r.get("v") != 1 or r.get("src") not in ("scan", "review", "mark"):
        return None
    at, cm = r.get("at"), r.get("commit")
    if not isinstance(at, (int, float)) or isinstance(at, bool) or not (isinstance(cm, str) and COMMIT_RE.fullmatch(cm)):
        return None
    out = {"at": at, "commit": cm, "src": r["src"]}
    if r["src"] == "mark":
        k, f = r.get("key"), safe_rel(r.get("file"))
        if not (isinstance(k, str) and SLUG_RE.fullmatch(k) and f and r.get("status") in MARKS):
            return None
        return dict(out, key=k, file=f, status=r["status"])
    its = r.get("items") if isinstance(r.get("items"), list) else []
    out["items"] = [y for y in (_log_item(x, r["src"]) for x in its[:LOG_ITEMS_MAX]) if y]
    if r["src"] == "scan":
        out["tools"] = [t for t in r.get("tools") or () if t in SEC_IDS] if isinstance(r.get("tools"), list) else []
    return out


def log_read(kdir):
    """Valid records of the newest LOG_LINES lines, oldest first."""
    try:
        with open(os.path.join(kdir, LOG_FILE), "rb") as f:
            f.seek(0, 2)
            size = f.seek(max(0, f.tell() - LOG_TAIL_BYTES))
            raw = f.read()
    except OSError:
        return []
    lines = raw.split(b"\n")
    if size:
        lines = lines[1:]   # cut mid-line by the tail window
    out = []
    for ln in lines[-LOG_LINES - 1:]:
        try:
            r = _valid(json.loads(ln.decode("utf-8")))
        except (ValueError, UnicodeDecodeError):
            continue
        if r:
            out.append(r)
    return out[-LOG_LINES:]


def log_view(kdir):
    """{at_scan, at_review, open, resolved, fp} — each finding {sev, file, line, key, desc, src, ai, status, at, commit}.
    Scan: resolved when absent from a later scan in which its tool ran ok; reappearing reopens it.
    Review: open until a mark (last mark wins); absence from a later review never resolves it.
    ⚠Model review is not deterministic: a finding missing from the next review is not evidence it was fixed.
    Open rows carry when they were (re)opened; resolved / false-positive rows when they were marked or resolved."""
    st, at_scan, at_review = {}, None, None
    for r in log_read(kdir):
        if r["src"] == "mark":
            x = st.get(("review", r["key"], r["file"]))
            if x:
                x.update(status="false-positive" if r["status"] == "false-positive" else "resolved", at=r["at"],
                         commit=r["commit"])
            continue
        if r["src"] == "scan":
            at_scan = r["at"]
        else:
            at_review = r["at"]
        seen = set()
        for y in r["items"]:
            ident = (r["src"], y["key"], y["file"])
            seen.add(ident)
            x = st.get(ident)
            if x is None or (x["status"] == "resolved"):
                st[ident] = dict(y, src=r["src"], ai=r["src"] == "review", status="open", at=r["at"], commit=r["commit"])
            else:
                x.update(sev=y["sev"], line=y["line"], desc=y["desc"])
        if r["src"] == "scan":
            ran = set(r["tools"])
            for ident, x in st.items():
                if ident[0] == "scan" and ident not in seen and x["status"] == "open" and ident[1].split(":", 1)[0] in ran:
                    x.update(status="resolved", at=r["at"], commit=r["commit"])
    rows = sorted(st.values(), key=lambda x: (SEV_RANK.get(x["sev"], 9), x["file"], x["line"], x["key"]))
    pick = lambda s: [x for x in rows if x["status"] == s][:LOG_ITEMS_MAX]
    return {"at_scan": at_scan, "at_review": at_review, "open": pick("open"), "resolved": pick("resolved"),
            "fp": pick("false-positive")}
