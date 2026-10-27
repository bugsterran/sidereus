"""Runtime patch card (Harness «Runtime behind latest patch»): local Python / Node vs the newest patch of their release
line and the newest line overall, as stored by `scripts/arch_checks.py` (deps_audit `collect(argv, rich=[])`).

`write` is the runner's (arch/deps-last.json, atomic, 0644); `view` is the viewer's read (lstat, size cap, allow-lists);
pure `shape(doc, now)` builds the `/api/harness` `runtime` body.
⚠The viewer never looks anything up: only the runner fetches. No data / offline is `unknown`, never `ok`.
⚠Metadata only: paths, versions, dates and flags — never command output.
"""
import json
import math
import os
import re
import shlex
import stat

from sidereus.bus import _atomic_write

DEPS_FILE = "deps-last.json"
MAX_BYTES = 64 * 1024
RT_STALE_D = 7
RT_ITEMS_MAX = 20
RT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the viewer checkout the runner must scan
# next-step key per (runtime, install class); the page maps the key to its own sentence
RT_FIX = {("nodejs", "homebrew"): "brew-node", ("python", "homebrew"): "brew-python", ("python", "system"): "system-python"}
RT_LV = ("ok", "info", "unknown", "warn", "fail")   # item level = the higher of the two lines in this order
RT_PATCH_LV = ("fail", "warn", "ok", "unknown")
RT_NEWEST_LV = ("info", "ok", "unknown")
RT_CLS = ("homebrew", "system", "other")
RT_RTS = ("python", "nodejs")
_VER = re.compile(r"\d+(\.\d+){1,2}")
_CYC = re.compile(r"\d+(\.\d+)?")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_REPORT = re.compile(r"[A-Za-z0-9._-]{1,80}")


def cmd(root=None):
    """The runner command that refreshes deps-last.json (arch_checks.py requires --repo). `python3` from PATH: any
    3.9+ runs the runner, and a fixed /usr/bin path does not exist on Windows."""
    r = root or RT_ROOT
    return " ".join(shlex.quote(a) for a in ("python3", os.path.join(r, "scripts", "arch_checks.py"),
                                             "--repo", r, "--category", "security", "--dev"))


def write(arch_dir, doc):
    os.makedirs(arch_dir, exist_ok=True)
    _atomic_write(os.path.join(arch_dir, DEPS_FILE), (json.dumps(doc, ensure_ascii=False) + "\n").encode("utf-8"),
                  prefix=".arch-", mode=0o644)


def _none(root):
    return {"state": "none", "at": 0, "age_d": None, "stale": False, "report": "", "dev": False, "offline": False,
            "cmd": cmd(root), "items": []}


def _is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _ver(x, empty=False):
    return isinstance(x, str) and ((empty and x == "") or bool(_VER.fullmatch(x)))


def _item(x):
    """Allow-listed copy of one stored item, None when any field is off-contract. fix and level are recomputed here."""
    if not isinstance(x, dict) or x.get("rt") not in RT_RTS or x.get("cls") not in RT_CLS:
        return None
    p, n, path = x.get("patch"), x.get("newest"), x.get("path")
    if not isinstance(p, dict) or not isinstance(n, dict) or not isinstance(path, str) or not 0 < len(path) <= 512 \
            or any(ord(c) < 32 for c in path) or not _ver(x.get("cur")) or not isinstance(x.get("cycle"), str) \
            or not _CYC.fullmatch(x["cycle"]) or not isinstance(x.get("viewer"), bool):
        return None
    if p.get("level") not in RT_PATCH_LV or not _ver(p.get("target"), True) or not isinstance(p.get("security"), bool) \
            or not isinstance(p.get("eol"), str) or not (p["eol"] == "" or _DATE.fullmatch(p["eol"])) \
            or not isinstance(p.get("eol_past"), bool):
        return None
    bn = n.get("behind_n")
    if n.get("level") not in RT_NEWEST_LV or not _ver(n.get("target"), True) or not isinstance(bn, int) \
            or isinstance(bn, bool) or not 0 <= bn <= 99:
        return None
    patch = {"level": p["level"], "target": p["target"], "security": p["security"], "eol": p["eol"], "eol_past": p["eol_past"]}
    newest = {"level": n["level"], "target": n["target"], "behind_n": bn}
    return {"rt": x["rt"], "path": path, "cls": x["cls"], "viewer": x["viewer"], "cur": x["cur"], "cycle": x["cycle"],
            "level": max(patch["level"], newest["level"], key=RT_LV.index), "patch": patch, "newest": newest,
            "fix": RT_FIX.get((x["rt"], x["cls"]), "other")}


def shape(doc, now, root=None):
    """`/api/harness` runtime body from a stored doc. Pure. Anything off-contract ⇒ state none (+ cmd)."""
    if not isinstance(doc, dict) or not _is_num(doc.get("at")) or not math.isfinite(doc["at"]) or doc["at"] <= 0 \
            or not isinstance(doc.get("report"), str) or not (doc["report"] == "" or _REPORT.fullmatch(doc["report"])) \
            or not isinstance(doc.get("dev"), bool) or not isinstance(doc.get("offline"), bool) \
            or not isinstance(doc.get("items"), list) or len(doc["items"]) > RT_ITEMS_MAX:
        return _none(root)
    items = [_item(x) for x in doc["items"]]
    if any(x is None for x in items):
        return _none(root)
    lv = {x["level"] for x in items}
    state = "behind" if lv & {"warn", "fail"} else "unknown" if "unknown" in lv or not items else "ok"
    age = max(0, int((now - doc["at"]) // 86400))
    return {"state": state, "at": float(doc["at"]), "age_d": age, "stale": age > RT_STALE_D, "report": doc["report"],
            "dev": doc["dev"], "offline": doc["offline"], "cmd": cmd(root), "items": items}


def view(arch_dir, now):
    """shape() of arch_dir/deps-last.json; a missing, symlinked, non-regular, oversized or bad file ⇒ state none."""
    fp = os.path.join(arch_dir, DEPS_FILE)
    try:
        st = os.lstat(fp)
        if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_BYTES:
            return _none(None)
        with open(fp, "rb") as f:
            raw = f.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            return _none(None)
        doc = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError):
        return _none(None)
    return shape(doc, now)
