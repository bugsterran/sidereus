"""Settings «Diagnostics» › «Security tools»: which scanners `scripts/arch_checks.py --category security` can use here,
with their version, found by PATH lookup and the install's file layout only.

⚠Nothing is executed (AGENTS.md rule 7): no `--version` call. The version comes from a Homebrew `Cellar/<id>/<ver>/`
segment, npm's own package.json, or a pip/pipx `<id>-<ver>.dist-info` folder; anything else is null.
⚠The reply carries no paths. Stdlib only, Python 3.9.
"""
import glob
import json
import os
import re
import shutil

from sidereus import ident, sec_checks

# (id, needs network: "no" | "yes" | "registry" = only for semgrep registry packs when the repo has no local rules)
TOOLS = (("gitleaks", "no"), ("semgrep", "registry"), ("bandit", "no"), ("osv-scanner", "yes"), ("npm", "yes"))
VER_RE = re.compile(r"^\d+(\.\d+){0,3}[0-9A-Za-z.+-]{0,16}$")
_PKG_MAX = 65536
_GLOB_MAX = 8


def _which(name):
    # ⚠not ident.bin_path: launchd's PATH is /usr/bin:/bin and _BIN_CACHE keeps a miss forever, so a fresh install
    # would never show. rich_env() adds the Homebrew/user bin dirs; no cache, so the next refresh sees it.
    return shutil.which(name, path=ident.rich_env().get("PATH", ""))


_realpath = os.path.realpath


def _ok(v):
    return v if isinstance(v, str) and VER_RE.fullmatch(v) else None


def _cellar(real, tid):
    parts = real.replace("\\", "/").split("/")
    for i, p in enumerate(parts[:-2]):
        if p == "Cellar" and parts[i + 1] == tid:
            return _ok(re.sub(r"_\d+$", "", parts[i + 2]))
    return None


def _pkg_version(fp, name):
    if not os.path.isfile(fp):
        return None   # a FIFO or device named package.json would block the request thread on open()
    try:
        with open(fp, encoding="utf-8") as f:
            d = json.loads(f.read(_PKG_MAX))
    except (OSError, ValueError):
        return None
    return _ok(d.get("version")) if isinstance(d, dict) and d.get("name") == name else None


def _npm(exe, real):
    # brew/unix: <bin>/../lib/node_modules/npm · Windows: <node dir>/node_modules/npm · realpath of npm = npm/bin/npm-cli.js
    for d in (os.path.dirname(exe), os.path.dirname(real)):
        for c in (os.path.join(d, "..", "lib", "node_modules", "npm", "package.json"),
                  os.path.join(d, "node_modules", "npm", "package.json"), os.path.join(d, "..", "package.json")):
            v = _pkg_version(c, "npm")
            if v:
                return v
    return None


def _dist_info(real, tid):
    root = os.path.dirname(os.path.dirname(real))
    hits = []
    for pat in (os.path.join(root, "lib", "python*", "site-packages", tid + "-*.dist-info"),
                os.path.join(root, "Lib", "site-packages", tid + "-*.dist-info")):
        hits += sorted(glob.glob(pat))[:_GLOB_MAX]
    for h in hits:
        v = _ok(os.path.basename(h)[len(tid) + 1:-len(".dist-info")])
        if v:
            return v
    return None


def _version(tid, exe):
    real = _realpath(exe)
    if tid != "npm":
        v = _cellar(real, tid)
        if v:
            return v
    if tid == "npm":
        return _npm(exe, real)
    if tid in ("semgrep", "bandit"):
        return _dist_info(real, tid)
    return None


def tools():
    """[{id, installed, version|None, cmd|None, net}] — cmd = this OS's install command when missing."""
    out = []
    for tid, net in TOOLS:
        exe = _which(tid)
        ver = None
        if exe:
            try:
                ver = _version(tid, exe)
            except OSError:
                ver = None
        out.append({"id": tid, "installed": bool(exe), "version": ver,
                    "cmd": None if exe else sec_checks.install_cmd(tid), "net": net})
    return out
