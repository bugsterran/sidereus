"""Harness «Guard self-check»: reads the results file scripts/harness_selfcheck.py writes (DATA_DIR/harness-selfcheck.json).

⚠Read only: the viewer never runs or schedules the replay. Fields are whitelisted and capped; a bad field is dropped
  on its own (None), the rest of the case stays. `stale` = the file's head is not the Sidereus checkout's HEAD now.
⚠`head` is the Sidereus repo the guards ran from, not the project picked on the Harness screen.
"""
import json
import os
import re
import time

from sidereus import gitinfo
from sidereus.config import CODE_DIR, DATA_DIR

HSC_FILE = os.path.join(DATA_DIR, "harness-selfcheck.json")
HSC_CMD = "python3 scripts/harness_selfcheck.py"
HSC_CASES_MAX = 32
HSC_STR_MAX = 200
HSC_READ_MAX = 256 * 1024
HSC_GUARDS = ("guard", "gate", "keep")
HSC_HEAD_RE = re.compile(r"^[0-9a-f]{7,40}$")
HSC_CODE_RE = re.compile(r"^[a-z][a-z0-9_-]{0,23}$")
HSC_CODES_MAX = 8
HSC_HEAD_TTL = 30.0
_HSC_MEMO = {}


def _now():
    return time.time()


def _head(root):
    """Current HEAD sha of `root`, memoised HSC_HEAD_TTL (the Harness tab polls); "" on a git miss."""
    t = _now()
    hit = _HSC_MEMO.get(root)
    if hit and t - hit[0] < HSC_HEAD_TTL:
        return hit[1]
    try:
        p = gitinfo._git_run(root, ["rev-parse", "HEAD"], 3, wait=0.5)
        s = (p.stdout or "").strip() if p.returncode == 0 else ""
    except Exception:
        s = ""
    s = s if HSC_HEAD_RE.match(s) else ""
    _HSC_MEMO[root] = (t, s)
    return s


def _str(v):
    return v if isinstance(v, str) and 0 < len(v) <= HSC_STR_MAX else None


def _case(c):
    codes = c.get("codes")
    codes = [x for x in codes if isinstance(x, str) and HSC_CODE_RE.match(x)][:HSC_CODES_MAX] if isinstance(codes, list) else []
    return {"name": _str(c.get("name")), "guard": c.get("guard") if c.get("guard") in HSC_GUARDS else None,
            "situation": _str(c.get("situation")), "expect": _str(c.get("expect")), "actual": _str(c.get("actual")),
            "pass": c.get("pass") if isinstance(c.get("pass"), bool) else None, "pair": _str(c.get("pair")), "codes": codes}


def _read(fp):
    try:
        if os.path.getsize(fp) > HSC_READ_MAX:
            return None
        with open(fp, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError, RecursionError):   # ⚠deep nesting raises RecursionError, not ValueError
        return None
    return d if isinstance(d, dict) and d.get("v") == 1 else None


def load(root=CODE_DIR, now=None):
    """{state: none|ok, ts, head, stale, cmd, cases} for harness_plat._results. `now` is accepted for symmetry with
    the other Harness loaders (no age rule today)."""
    d = _read(HSC_FILE)
    if d is None:
        return {"state": "none", "ts": 0, "head": "", "stale": False, "cmd": HSC_CMD, "cases": []}
    cases = d.get("cases") if isinstance(d.get("cases"), list) else []
    head = d.get("head") if isinstance(d.get("head"), str) and HSC_HEAD_RE.match(d.get("head")) else ""
    ts = d.get("ts")
    cur = _head(root) if root else ""
    return {"state": "ok", "ts": ts if isinstance(ts, (int, float)) and not isinstance(ts, bool) else 0, "head": head,
            "stale": bool(cur) and head != cur, "cmd": HSC_CMD,
            "cases": [_case(c) for c in cases[:HSC_CASES_MAX] if isinstance(c, dict)]}
