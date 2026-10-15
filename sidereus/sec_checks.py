"""Security checks for the project-checks runner (`--category security`): tool plans, report parsers, files examined
and network gating. Same checks.json v1 schema as sidereus/arch_checks.py plus item `pkg`, stored as checks-security.json.

⚠Secrets: gitleaks findings keep RuleID / File / StartLine only — Secret, Match, Line and message are never read into
results, logs or relays. Its report lives in the runner's temp dir and is deleted right after parsing (`take_report`).
⚠No subprocess here (AGENTS.md rule 7). Advisory lookups (npm audit, osv-scanner) need the network: planned only with
the runner's `--net`, and a network error is `skipped`, never `0 issues`. Stdlib only, Python 3.9.
"""
import json
import os
import re
import sys

from sidereus.arch_checks_parse import clean_help

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
}


def install_hint(tool):
    """«install: …» for the OS this runs on (read at call time so tests can patch os.name / sys.platform)."""
    mac, win, lin = HINTS[tool]
    return "install: " + (win if os.name == "nt" else mac if sys.platform == "darwin" else lin)

SEC_IDS = ("gitleaks", "npm-audit", "osv-scanner", "semgrep", "bandit")
SEC_FILE = "checks-security.json"
SEC_LAST = "_checks_last_security.json"   # {repo, commit} of the newest security run (gate `--verify --last --category security`)
CATEGORIES = ("quality", "security")
PKG_RE = re.compile(r"[A-Za-z0-9@/._+:-]{1,100}")
NET_RE = re.compile(r"ENOTFOUND|EAI_AGAIN|ECONNREFUSED|ECONNRESET|ETIMEDOUT|ENETUNREACH|no such host|dial tcp|"
                    r"network is unreachable|getaddrinfo", re.I)
WHY_NET = "needs network (run with --net)"
WHY_NET_FAIL = "needs network"
_RULE = re.compile(r"[A-Za-z0-9_./@:-]{1,60}")      # same shape as arch_checks.RULE_RE
_GHSA = re.compile(r"GHSA(?:-[a-z0-9]{4}){3}")
_SCANNED = re.compile(r"scanned ~?(\d[\d,]*) bytes")
_OSV_N = re.compile(r"Scanned .+? file and found (\d+) packages?")
_LOCKS = ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Pipfile.lock", "uv.lock", "requirements.txt",
          "go.sum", "Cargo.lock", "Gemfile.lock", "composer.lock", "gradle.lockfile")
_SEMGREP_CFG = (".semgrep.yml", ".semgrep.yaml", ".semgrep")
_SKIP = {".git", "node_modules", "build", "target", ".gradle", "dist", "out", ".venv", "venv", "__pycache__", ".idea",
         ".mvn", ".tox", ".mypy_cache", ".ruff_cache"}
_WALK_DIRS, _WALK_DEPTH = 5000, 6


def scan(repo):
    """One bounded walk (same bounds as arch_checks._scan): files counted, python present, lockfile present."""
    s = {"n": 0, "py": False, "lock": False}
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
        s["lock"] = s["lock"] or any(f in _LOCKS for f in fns)
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
    """Security tool plans (same shape as arch_checks.detect). `src: report` = gitleaks' report file (see bind)."""
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
    exe = which("semgrep")
    cfg = next((c for c in _SEMGREP_CFG if os.path.exists(os.path.join(repo, c))), None)
    out.append(_tool("semgrep", "project", status="missing", why=install_hint("semgrep")) if not exe else
               _tool("semgrep", "project", status="skipped", why="no local rules (--config auto needs network)") if not cfg else
               _tool("semgrep", "project", argv=[exe, "scan", "--config", cfg, "--json", "--metrics=off",
                                                 "--disable-version-check", "--quiet", "."], cwd=repo, src="stdout", ok_rc=(0, 1)))
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


def _it(f, line, rule, sev, pkg=None, url=None, desc=None):
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
    return [_it(x.get("File"), x.get("StartLine"), x.get("RuleID"), "error") for x in j if isinstance(x, dict)]


def _sev(s):
    return "error" if str(s).lower() in ("high", "critical") else "warning"


def parse_npm_audit(text):
    """npm 7+ `vulnerabilities` (advisories in `via`) or npm 6 `advisories`; file = the lockfile, line 1."""
    j = _json(text)
    if not isinstance(j, dict):
        raise ValueError("npm audit: not an object")
    out, seen = [], set()

    def add(rule, pkg, sev, url):
        if (rule, pkg) not in seen:
            seen.add((rule, pkg))
            out.append(_it("package-lock.json", 1, rule, _sev(sev), pkg, url))
    for name, v in (j.get("vulnerabilities") or {}).items() if isinstance(j.get("vulnerabilities"), dict) else ():
        for via in (v.get("via") or ()) if isinstance(v, dict) else ():
            if isinstance(via, dict):   # string entries name another vulnerable package (listed on its own)
                url = via.get("url") if isinstance(via.get("url"), str) else ""
                m = _GHSA.search(url)
                add(m.group(0) if m else str(via.get("source")), via.get("name") or name, via.get("severity"), url)
    for a in (j.get("advisories") or {}).values() if isinstance(j.get("advisories"), dict) else ():
        if isinstance(a, dict):
            url = a.get("url") if isinstance(a.get("url"), str) else ""
            m = _GHSA.search(url + " " + str(a.get("github_advisory_id") or ""))
            add(m.group(0) if m else str(a.get("id")), a.get("module_name"), a.get("severity"), url)
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
                try:
                    hi = float(g.get("max_severity") or 0) >= 7.0
                except (TypeError, ValueError):
                    hi = False
                out.append(_it(path, 1, rule, "error" if hi or _sev(sv) == "error" else "warning", name,
                               "https://osv.dev/vulnerability/" + v["id"] if _RULE.fullmatch(v["id"]) else None))
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
                           "error" if ex.get("severity") == "ERROR" else "warning", None, md.get("source")))
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
            out.append(_it(x.get("filename"), x.get("line_number"), x.get("test_id"), _sev(x.get("issue_severity")),
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
