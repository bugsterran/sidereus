#!/usr/bin/python3
"""Dependency and runtime security-patch audit. Prints «OK|WARN|FAIL|INFO item — detail» lines; exit 1 on any FAIL.

  /usr/bin/python3 scripts/deps_audit.py             import guard + runtime EOL table, then online lookups: latest
                                                     Python / Node patch (endoflife.date) and OSV.dev advisories
  /usr/bin/python3 scripts/deps_audit.py --offline   skip every online lookup (--online is accepted as a no-op)

⚠Online lookups run after one reachability probe; unreachable or --offline = a «skipped» line, never «no advisories».
OSV.dev covers npm/PyPI packages only (Claude Code CLI, browser drivers) — not the CPython / Node / Chrome runtimes,
which keep the EOL lines. Reads metadata only: plist ProgramArguments, app Info.plist versions,
installed_plugins.json name/version — never credentials or session files.
"""
import ast
import datetime
import json
import os
import plistlib
import re
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
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


OSV_QUERY = "https://api.osv.dev/v1/query"


def _probe():
    """True when OSV.dev answers at all within 3 s (an HTTP error status still means reachable)."""
    import urllib.error
    import urllib.request
    try:
        urllib.request.urlopen(urllib.request.Request("https://api.osv.dev/", method="HEAD"), timeout=3).close()
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


def osv_targets(mjs_files, root, claude_version):
    """[(ecosystem, package, version)] OSV can answer for: the Claude Code CLI (npm) and installed browser drivers."""
    out = []
    m = re.match(r"\s*(\d+\.\d+\.\d+)", claude_version or "")
    if m:
        out.append(("npm", "@anthropic-ai/claude-code", m.group(1)))
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


def main(argv):
    today = datetime.date.today()
    lines = []

    def emit(level, item, detail):
        lines.append(level)
        print("%-4s %s — %s" % (level, item, detail))

    # 1. third-party dependency guard
    bad = foreign_py(_walk_py(ROOT), ROOT)
    emit("FAIL" if bad else "OK", "python imports", "; ".join("%s: %s" % b for b in bad) if bad else "stdlib + first-party only")
    mjs = [os.path.join(ROOT, "scripts", f) for f in sorted(os.listdir(os.path.join(ROOT, "scripts"))) if f.endswith(".mjs")]
    bad = foreign_mjs(mjs, ROOT)
    emit("FAIL" if bad else "OK", "node imports", "; ".join("%s: %s" % b for b in bad) if bad else
         "node: builtins only (%d scripts/*.mjs)" % len(mjs))

    # 2. runtimes
    lpy = _launchd_python()
    pyv = _run([lpy if os.path.isabs(lpy) else "/usr/bin/python3", "-c", "import platform;print(platform.python_version())"])
    cyc = ".".join(pyv.split(".")[:2])
    lvl, det = eol_status(cyc, PY_EOL, today)
    emit(lvl, "python (launchd: %s)" % lpy, "%s · %s" % (pyv or "?", det))
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
    cv = _run(["claude", "--version"])
    emit("OK" if cv else "WARN", "claude code cli", cv or "not found")
    cfg = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    try:
        with open(os.path.join(cfg, "plugins", "installed_plugins.json"), encoding="utf-8") as h:
            plugs = json.load(h).get("plugins") or {}
        emit("OK", "claude plugins", ", ".join("%s %s" % (k, (v[0] or {}).get("version", "?") if v else "?")
                                           for k, v in sorted(plugs.items())) or "none")
    except (OSError, ValueError, AttributeError):
        emit("OK", "claude plugins", "no installed_plugins.json under %s" % cfg)

    # 3. online: latest patch per cycle + OSV.dev advisories
    why = offline_reason(argv)   # --online is a no-op: online is the default
    if why:
        emit("WARN", "online lookups", "skipped — %s (no advisory data, not «clean»)" % why)
    else:
        for prod, cur, key in (("python", pyv, cyc), ("nodejs", nodev, (nodev or "x").split(".")[0])):
            try:
                rows = _fetch("https://endoflife.date/api/%s.json" % prod)
            except Exception as e:   # network errors of any kind are a WARN, never a crash
                emit("WARN", "online %s" % prod, "fetch failed: %s" % type(e).__name__)
                continue
            row = next((r for r in rows if str(r.get("cycle")) == key), None)
            newest = rows[0] if rows else {}
            if not row:
                emit("WARN", "online %s" % prod, "cycle %s not listed" % key)
                continue
            behind = _ver_tuple(cur or "0") < _ver_tuple(str(row.get("latest", "0")))
            emit("WARN" if behind or row.get("eol") is True or str(row.get("eol")) <= today.isoformat() else "OK",
                 "online %s" % prod, "local %s · latest %s %s (EOL %s) · newest cycle %s → %s (EOL %s)" % (
                     cur, key, row.get("latest"), row.get("eol"), newest.get("cycle"), newest.get("latest"), newest.get("eol")))
        for eco, pkg, ver in osv_targets(mjs, ROOT, cv):
            try:
                vs = osv_vulns(eco, pkg, ver)
            except Exception as e:   # a lookup error is «skipped», never «no advisories»
                emit("WARN", "osv %s %s" % (pkg, ver), "skipped — fetch failed: %s" % type(e).__name__)
                continue
            emit("WARN" if vs else "OK", "osv %s %s" % (pkg, ver),
                 ", ".join("%s (%s)" % v for v in vs) if vs else "no advisories (OSV.dev %s)" % eco)
        emit("INFO", "osv runtimes", "CPython, Node.js and Chrome are not OSV ecosystems — not checked there (see EOL lines)")
    return 1 if "FAIL" in lines else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
