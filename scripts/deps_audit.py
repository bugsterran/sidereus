#!/usr/bin/python3
"""Dependency and runtime security-patch audit of what this checkout depends on. Prints «OK|WARN|FAIL|INFO item —
detail» lines; exit 1 on any FAIL. `collect(argv)` returns the same lines for scripts/arch_checks.py's report.

  /usr/bin/python3 scripts/deps_audit.py             python import guard + runtime EOL, then online: latest Python
                                                     patch (endoflife.date)
  /usr/bin/python3 scripts/deps_audit.py --dev       also the dev tooling: node import guard + EOL, Chrome, latest Node
                                                     patch and OSV.dev advisories for browser drivers
  /usr/bin/python3 scripts/deps_audit.py --offline   skip every online lookup (--online is accepted as a no-op)

⚠Online lookups run after one reachability probe; unreachable or --offline = a «skipped» line, never «no advisories».
OSV.dev covers npm packages only (browser drivers) — not the CPython / Node / Chrome runtimes, which keep the EOL
lines. Reads metadata only: plist ProgramArguments and app Info.plist versions — never credentials or session files.
Writes nothing. With `collect(argv, rich=[])` it also lists local Python/Node runtimes vs python.org / nodejs.org
release lists (scripts/arch_checks.py stores that as deps-last.json).
"""
import ast
import datetime
import glob
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ★Source: endoflife.date (python, nodejs) — checked 2026-10-12. Refresh from the online lines; update when a cycle changes.
PY_EOL = {"3.9": "2025-10-31", "3.10": "2026-10-01", "3.11": "2027-10-31", "3.12": "2028-10-31",
          "3.13": "2029-10-31", "3.14": "2030-10-31", "3.15": "2031-10-31"}
NODE_EOL = {"18": "2025-04-30", "20": "2026-04-30", "22": "2027-04-30", "24": "2028-04-30", "26": "2029-04-30"}
EOL_SOON_DAYS = 180

PY_DIRS = ("sidereus", "hooks", "plugin", "plugins", "mcp")
PY_FILES = ("chat_server.py", "mailbox_config.py", "mailbox_core.py", "sidereus_cli.py")
# Browser drivers a scripts/*.mjs may import besides node: builtins. screen_check.mjs drives Chrome over raw CDP (none today).
KNOWN_DRIVERS = ("playwright", "playwright-core", "puppeteer", "puppeteer-core")
# The viewer's LaunchAgent: any plist whose arguments run this checkout's chat_server.py (label is per-install).
LAUNCH_AGENTS = os.path.expanduser("~/Library/LaunchAgents")
CHROME_APP = "/Applications/Google Chrome.app"

# ⚠/usr/bin/python3 is 3.9, which lacks sys.stdlib_module_names (3.10+): fixed 3.9 top-level stdlib list as fallback.
STDLIB_39 = frozenset("""
__future__ _thread _abc _ast _bisect _blake2 _bootlocale _bz2 _codecs _collections _collections_abc _compat_pickle
_compression _contextvars _crypt _csv _ctypes _curses _datetime _dbm _decimal _elementtree _functools _gdbm _hashlib
_heapq _imp _io _json _locale _lsprof _lzma _markupbase _md5 _multibytecodec _multiprocessing _opcode _operator
_osx_support _pickle _posixshmem _posixsubprocess _py_abc _pydecimal _pyio _queue _random _sha1 _sha256 _sha3 _sha512
_signal _sitebuiltins _socket _sqlite3 _sre _ssl _stat _statistics _string _strptime _struct _symtable _sysconfigdata
_threading_local _tkinter _tracemalloc _uuid _warnings _weakref _weakrefset _xxsubinterpreters _zoneinfo
abc aifc antigravity argparse array ast asynchat asyncio asyncore atexit audioop base64 bdb binascii binhex bisect
builtins bz2 cProfile calendar cgi cgitb chunk cmath cmd code codecs codeop collections colorsys compileall concurrent
configparser contextlib contextvars copy copyreg crypt csv ctypes curses dataclasses datetime dbm decimal difflib dis
distutils doctest email encodings ensurepip enum errno faulthandler fcntl filecmp fileinput fnmatch formatter fractions
ftplib functools gc genericpath getopt getpass gettext glob graphlib grp gzip hashlib heapq hmac html http idlelib
imaplib imghdr imp importlib inspect io ipaddress itertools json keyword lib2to3 linecache locale logging lzma mailbox
mailcap marshal math mimetypes mmap modulefinder msilib msvcrt multiprocessing netrc nis nntplib nt ntpath nturl2path
numbers opcode operator optparse os ossaudiodev parser pathlib pdb pickle pickletools pipes pkgutil platform plistlib
poplib posix posixpath pprint profile pstats pty pwd py_compile pyclbr pydoc pydoc_data pyexpat queue quopri random re
readline reprlib resource rlcompleter runpy sched secrets select selectors shelve shlex shutil signal site smtpd smtplib
sndhdr socket socketserver spwd sqlite3 sre_compile sre_constants sre_parse ssl stat statistics string stringprep
struct subprocess sunau symbol symtable sys sysconfig syslog tabnanny tarfile telnetlib tempfile termios textwrap this
threading time timeit tkinter token tokenize trace traceback tracemalloc tty turtle turtledemo types typing unicodedata
unittest urllib uu uuid venv warnings wave weakref webbrowser winreg winsound wsgiref xdrlib xml xmlrpc xxsubtype
zipapp zipfile zipimport zlib zoneinfo
""".split())


def stdlib_names():
    return frozenset(getattr(sys, "stdlib_module_names", ())) | STDLIB_39


def local_names(paths):
    """First-party top-level names: every .py stem and package dir next to the scanned files and at repo root."""
    out = set()
    for d in {os.path.dirname(p) for p in paths}:
        try:
            for n in os.listdir(d):
                if n.endswith(".py"):
                    out.add(n[:-3])
                elif os.path.isdir(os.path.join(d, n)) and not n.startswith((".", "__")):
                    out.add(n)
        except OSError:
            pass
    return out


def py_imports(src):
    """Absolute top-level module names imported by a Python source (relative imports skipped)."""
    names = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            names.add(node.module.split(".")[0])
    return names


def foreign_py(files, root):
    """[(relpath, module)] for imports that are neither stdlib nor first-party. Syntax errors are reported as module '<syntax>'."""
    std = stdlib_names()
    local = local_names(list(files) + [os.path.join(root, "x.py")])
    bad = []
    for f in sorted(files):
        try:
            with open(f, encoding="utf-8") as h:
                mods = py_imports(h.read())
        except (SyntaxError, ValueError):
            bad.append((os.path.relpath(f, root), "<syntax>"))
            continue
        bad += [(os.path.relpath(f, root), m) for m in sorted(mods) if m not in std and m not in local]
    return bad


_MJS_IMPORT = re.compile(r"""(?:^|[\s;])(?:import|export)\s[^'"]*?from\s*['"]([^'"]+)['"]|(?:^|[\s;(=])import\s*\(\s*['"]([^'"]+)['"]|"""
                         r"""(?:^|[\s;])import\s*['"]([^'"]+)['"]|\brequire\s*\(\s*['"]([^'"]+)['"]""", re.M)


def mjs_specifiers(src):
    return {next(g for g in m.groups() if g) for m in _MJS_IMPORT.finditer(src)}


def foreign_mjs(files, root):
    """[(relpath, specifier)] for imports that are not node: builtins, relative paths or a known browser driver."""
    bad = []
    for f in sorted(files):
        with open(f, encoding="utf-8") as h:
            specs = mjs_specifiers(h.read())
        for s in sorted(specs):
            if s.startswith(("node:", "./", "../", "/")) or s.split("/")[0] in KNOWN_DRIVERS:
                continue
            bad.append((os.path.relpath(f, root), s))
    return bad


def eol_status(cycle, table, today):
    """('OK'|'WARN', detail) for a release cycle against an EOL table. Pure: `today` is a date."""
    eol = table.get(cycle)
    if not eol:
        return "WARN", "cycle %s not in the EOL table — refresh it" % cycle
    d = datetime.date.fromisoformat(eol)
    if d <= today:
        return "WARN", "EOL %s (past) — no upstream security fixes" % eol
    if (d - today).days <= EOL_SOON_DAYS:
        return "WARN", "EOL %s (in %d days)" % (eol, (d - today).days)
    return "OK", "EOL %s" % eol


def _walk_py(root):
    out = [os.path.join(root, f) for f in PY_FILES if os.path.isfile(os.path.join(root, f))]
    for d in PY_DIRS:
        for dp, dn, fn in os.walk(os.path.join(root, d)):
            dn[:] = [x for x in dn if x not in ("__pycache__",) and not x.startswith(".")]
            out += [os.path.join(dp, f) for f in fn if f.endswith(".py")]
    return out


def _ver_tuple(s):
    return tuple(int(x) for x in re.findall(r"\d+", s)[:3])


def plist_program(text):
    """First ProgramArguments string. ⚠Regex, not plistlib: the viewer plist carries `--` inside XML comments,
    which launchd accepts and expat rejects."""
    m = re.search(r"<key>\s*ProgramArguments\s*</key>\s*<array>(.*?)</array>", text, re.S)
    s = m and re.search(r"<string>([^<]*)</string>", re.sub(r"<!--.*?-->", "", m.group(1), flags=re.S))
    return s.group(1).strip() if s else "?"


def _launchd_python():
    srv = os.path.join(ROOT, "chat_server.py")
    try:
        names = sorted(os.listdir(LAUNCH_AGENTS))
    except OSError:
        return "?"
    for n in names:
        if not n.endswith(".plist"):
            continue
        try:
            with open(os.path.join(LAUNCH_AGENTS, n), encoding="utf-8") as h:
                text = h.read()
        except (OSError, ValueError):
            continue
        if srv in text:
            return plist_program(text)
    return "?"


def _run(argv):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=15).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _fetch(url, body=None):
    """GET (or POST json when body is given) and decode json."""
    import urllib.request
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "deps-audit", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:  # nosec B310 -- callers pass constant https URLs only
        return json.loads(r.read().decode("utf-8"))


OSV_QUERY = "https://api.osv.dev/v1/query"


def _probe():
    """True when OSV.dev answers at all within 3 s (an HTTP error status still means reachable)."""
    import urllib.error
    import urllib.request
    try:
        urllib.request.urlopen(urllib.request.Request("https://api.osv.dev/", method="HEAD"), timeout=3).close()  # nosec B310 -- constant https URL
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False
    return True


def offline_reason(argv, probe=None):
    """Why online lookups are skipped ('--offline' | 'offline'), or None when they run."""
    if "--offline" in argv:
        return "--offline"
    return None if (probe or _probe)() else "offline"


def osv_vulns(eco, name, version, fetch=None):
    """[(advisory id, severity)] from OSV.dev for one package version. Raises on network/format errors."""
    fetch = fetch or _fetch
    out, token = [], None
    for _ in range(10):   # ⚠the query API pages long lists via next_page_token
        body = {"package": {"name": name, "ecosystem": eco}, "version": version}
        if token:
            body["page_token"] = token
        j = fetch(OSV_QUERY, body)
        if not isinstance(j, dict):
            raise ValueError("osv: not an object")
        for v in j.get("vulns") or ():
            if isinstance(v, dict) and isinstance(v.get("id"), str):
                sev = (v.get("database_specific") or {}).get("severity") if isinstance(v.get("database_specific"), dict) else None
                out.append((v["id"], str(sev).lower() if sev else "unrated"))
        token = j.get("next_page_token")
        if not token:
            break
    return out


def osv_targets(mjs_files, root):
    """[(ecosystem, package, version)] OSV can answer for: installed browser drivers imported by scripts/*.mjs."""
    out = []
    used = set()
    for f in mjs_files:
        with open(f, encoding="utf-8") as h:
            used |= {s.split("/")[0] for s in mjs_specifiers(h.read())} & set(KNOWN_DRIVERS)
    for pkg in sorted(used):
        try:
            with open(os.path.join(root, "node_modules", pkg, "package.json"), encoding="utf-8") as h:
                out.append(("npm", pkg, json.load(h)["version"]))
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return out


def _online_eol(prod, cur, key, today):
    """One endoflife.date line (level, item, detail): local patch vs the cycle's latest, and the newest cycle."""
    try:
        rows = _fetch("https://endoflife.date/api/%s.json" % prod)
    except Exception as e:   # network errors of any kind are a WARN, never a crash
        return "WARN", "online %s" % prod, "fetch failed: %s" % type(e).__name__
    row = next((r for r in rows if str(r.get("cycle")) == key), None)
    newest = rows[0] if rows else {}
    if not row:
        return "WARN", "online %s" % prod, "cycle %s not listed" % key
    behind = _ver_tuple(cur or "0") < _ver_tuple(str(row.get("latest", "0")))
    return ("WARN" if behind or row.get("eol") is True or str(row.get("eol")) <= today.isoformat() else "OK",
            "online %s" % prod, "local %s · latest %s %s (EOL %s) · newest cycle %s → %s (EOL %s)" % (
                cur, key, row.get("latest"), row.get("eol"), newest.get("cycle"), newest.get("latest"), newest.get("eol")))


RT_PREFIXES = ("/opt/homebrew", "/usr/local")
SYS_PY = "/usr/bin/python3"
PY_RELEASES = "https://www.python.org/api/v2/downloads/release/?is_published=true"
NODE_RELEASES = "https://nodejs.org/dist/index.json"
_VER_RE = re.compile(r"\d+(\.\d+){1,2}")
_which = shutil.which   # tests patch this, never PATH


def _rt_cls(path):
    """homebrew | system | other, from the path layout only."""
    rp = os.path.realpath(path)
    if any(path.startswith(p + "/opt/") for p in RT_PREFIXES) or "/Cellar/" in rp:
        return "homebrew"
    return "system" if path == SYS_PY else "other"


def _rt_version(rt, path):
    v = _run([path, "-c", "import platform;print(platform.python_version())"] if rt == "python" else [path, "--version"])
    v = v.strip().lstrip("v")
    return v if _VER_RE.fullmatch(v) else ""


def runtimes(dev=True):
    """[{rt, path, cls, viewer, cur}] of local Python (and with dev Node) runtimes, deduped by realpath.
    The launchd interpreter is marked viewer: true. A runtime whose version cannot be read is left out."""
    cand = []
    for pre in RT_PREFIXES:
        cand += [("python", p) for p in sorted(glob.glob(os.path.join(pre, "opt", "python@3.*", "bin", "python3.*")))
                 if re.search(r"/python3\.\d+$", p)]
    cand.append(("python", SYS_PY))
    lpy = _launchd_python()
    if os.path.isabs(lpy):
        cand.append(("python", lpy))
    if dev:
        for pre in RT_PREFIXES:
            cand += [("nodejs", p) for p in sorted(glob.glob(os.path.join(pre, "opt", "node@*", "bin", "node")))]
            cand.append(("nodejs", os.path.join(pre, "opt", "node", "bin", "node")))
        w = _which("node")
        if w:
            cand.append(("nodejs", w))
    out, seen = [], set()
    viewer_rp = os.path.realpath(lpy) if os.path.isabs(lpy) else None
    for rt, p in cand:
        if not os.path.isfile(p):
            continue
        rp = os.path.realpath(p)
        if rp in seen:
            continue
        cur = _rt_version(rt, p)
        if not cur:
            continue
        seen.add(rp)
        out.append({"rt": rt, "path": p, "cls": _rt_cls(p), "viewer": rp == viewer_rp, "cur": cur})
    return out


def py_releases():
    """[{v, security: False}] of published final CPython releases. ⚠python.org carries no security flag."""
    rows = _fetch(PY_RELEASES)
    out = []
    for r in rows if isinstance(rows, list) else ():
        m = re.fullmatch(r"Python (\d+\.\d+\.\d+)", str(r.get("name") or "")) if isinstance(r, dict) else None
        if m and not r.get("pre_release"):
            out.append({"v": m.group(1), "security": False})
    if not out:
        raise ValueError("python.org: no releases")
    return out


def node_releases():
    """[{v, security}] from nodejs.org/dist/index.json (security = that release fixed a vulnerability)."""
    rows = _fetch(NODE_RELEASES)
    out = [{"v": str(r["version"]).lstrip("v"), "security": r.get("security") is True}
           for r in rows if isinstance(r, dict) and _VER_RE.fullmatch(str(r.get("version") or "").lstrip("v"))] \
        if isinstance(rows, list) else []
    if not out:
        raise ValueError("nodejs.org: no releases")
    return out


_RANK = ("ok", "info", "unknown", "warn", "fail")   # = sidereus/sec_runtime.RT_LV (that module also owns the fix keys)


def _cycle(rt, v):
    p = v.split(".")
    return p[0] if rt == "nodejs" else ".".join(p[:2])


def _lines(rt, releases):
    """Release lines that count for «newest»: every CPython minor; Node even majors only (odd ones never reach LTS)."""
    return [r for r in releases if rt != "nodejs" or int(r["v"].split(".")[0]) % 2 == 0]


def rt_verdict(rt, cur, releases, eol_table, today):
    """Item dict for one runtime. Pure. releases None = no data (offline / fetch failed) ⇒ unknown, never ok.
    patch: fail = cycle EOL or a newer same-cycle security release missed · warn = patch behind · ok (unknown when the
    cycle is not in eol_table).
    newest: info = a newer release line exists (behind_n lines) · ok."""
    rtn = rt["rt"]
    cyc = _cycle(rtn, cur)
    eol = eol_table.get(cyc, "")
    eol_past = bool(eol) and datetime.date.fromisoformat(eol) <= today
    patch = {"level": "fail" if eol_past else "unknown", "target": "", "security": False, "eol": eol, "eol_past": eol_past}
    newest = {"level": "unknown", "target": "", "behind_n": 0}
    if releases is not None:
        same = [r for r in releases if _cycle(rtn, r["v"]) == cyc]
        if same:
            top = max(same, key=lambda r: _ver_tuple(r["v"]))
            missed = [r for r in same if _ver_tuple(r["v"]) > _ver_tuple(cur)]
            sec = any(r["security"] for r in missed)
            patch["target"], patch["security"] = top["v"], sec
            # ⚠a cycle missing from the EOL table (odd Node majors) is never ok: its end date is unknown here
            patch["level"] = "fail" if eol_past or sec else "warn" if missed else "ok" if eol else "unknown"
        lines = _lines(rtn, releases)
        if lines:
            top = max(lines, key=lambda r: _ver_tuple(r["v"]))
            mine = _ver_tuple(cyc)
            ahead = {_cycle(rtn, r["v"]) for r in lines if _ver_tuple(_cycle(rtn, r["v"])) > mine}
            newest = {"level": "info" if ahead else "ok", "target": top["v"], "behind_n": len(ahead)}
    level = max(patch["level"], newest["level"], key=_RANK.index)
    return {"rt": rtn, "path": rt["path"], "cls": rt["cls"], "viewer": bool(rt.get("viewer")), "cur": cur, "cycle": cyc,
            "level": level, "patch": patch, "newest": newest}


def _rich(dev, online, today):
    """{offline, items} for scripts/arch_checks.py's runtime card. Release lists are fetched only when online."""
    rel = {}
    for rtn, fn in (("python", py_releases), ("nodejs", node_releases)):
        try:
            rel[rtn] = fn() if online else None
        except Exception:   # noqa: BLE001 — a lookup error is «unknown», never «ok»
            rel[rtn] = None
    items = [rt_verdict(r, r["cur"], rel[r["rt"]], PY_EOL if r["rt"] == "python" else NODE_EOL, today)
             for r in runtimes(dev)]
    return {"offline": not online or any(v is None for v in rel.values()), "items": items}


def collect(argv, rich=None):
    """[(level, item, detail)]. Default = the viewer's own runtime (python); --dev adds the dev tooling (node, Chrome,
    browser drivers). ⚠Prints and writes nothing: scripts/arch_checks.py calls this in-process for its report.
    rich: a list ⇒ one {offline, items} runtime dict is appended (extra lookups run only then); lines are unchanged."""
    dev = "--dev" in argv
    today = datetime.date.today()
    out = []
    emit = lambda level, item, detail: out.append((level, item, detail))

    bad = foreign_py(_walk_py(ROOT), ROOT)
    emit("FAIL" if bad else "OK", "python imports", "; ".join("%s: %s" % b for b in bad) if bad else "stdlib + first-party only")
    mjs = []
    if dev:
        sd = os.path.join(ROOT, "scripts")
        mjs = [os.path.join(sd, f) for f in sorted(os.listdir(sd)) if f.endswith(".mjs")] if os.path.isdir(sd) else []
        bad = foreign_mjs(mjs, ROOT)
        emit("FAIL" if bad else "OK", "node imports", "; ".join("%s: %s" % b for b in bad) if bad else
             "node: builtins only (%d scripts/*.mjs)" % len(mjs))

    lpy = _launchd_python()
    pyv = _run([lpy if os.path.isabs(lpy) else "/usr/bin/python3", "-c", "import platform;print(platform.python_version())"])
    cyc = ".".join(pyv.split(".")[:2])
    lvl, det = eol_status(cyc, PY_EOL, today)
    emit(lvl, "python (launchd: %s)" % lpy, "%s · %s" % (pyv or "?", det))
    nodev = ""
    if dev:
        nodev = _run(["node", "--version"]).lstrip("v")
        if nodev:
            lvl, det = eol_status(nodev.split(".")[0], NODE_EOL, today)
            emit(lvl, "node (dev tooling)", "%s · %s" % (nodev, det))
        else:
            emit("WARN", "node (dev tooling)", "not found")
        try:
            with open(os.path.join(CHROME_APP, "Contents", "Info.plist"), "rb") as h:
                cv = plistlib.load(h).get("CFBundleShortVersionString", "?")
            emit("OK", "browser (screen_check)", "raw CDP, no driver package · Chrome %s (auto-updates)" % cv)
        except (OSError, ValueError, plistlib.InvalidFileException):
            emit("WARN", "browser (screen_check)", "Chrome not found at %s (set CHROME)" % CHROME_APP)

    why = offline_reason(argv)   # --online is a no-op: online is the default
    if isinstance(rich, list):
        try:
            rich.append(_rich(dev, not why, today))
        except Exception:   # noqa: BLE001 — the runtime card is extra; its failure never changes the lines
            pass
    if why:
        emit("WARN", "online lookups", "skipped — %s (no advisory data, not «clean»)" % why)
        return out
    emit(*_online_eol("python", pyv, cyc, today))
    if dev:
        emit(*_online_eol("nodejs", nodev, (nodev or "x").split(".")[0], today))
        for eco, pkg, ver in osv_targets(mjs, ROOT):
            try:
                vs = osv_vulns(eco, pkg, ver)
            except Exception as e:   # a lookup error is «skipped», never «no advisories»
                emit("WARN", "osv %s %s" % (pkg, ver), "skipped — fetch failed: %s" % type(e).__name__)
                continue
            emit("WARN" if vs else "OK", "osv %s %s" % (pkg, ver),
                 ", ".join("%s (%s)" % v for v in vs) if vs else "no advisories (OSV.dev %s)" % eco)
        emit("INFO", "osv runtimes", "CPython, Node.js and Chrome are not OSV ecosystems — not checked there (see EOL lines)")
    return out


def main(argv):
    lines = collect(argv)
    for lv, item, detail in lines:
        print("%-4s %s — %s" % (lv, item, detail))
    return 1 if any(x[0] == "FAIL" for x in lines) else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # ⚠Windows console code page cannot encode the em dash in each line
    except Exception:
        pass
    sys.exit(main(sys.argv[1:]))
