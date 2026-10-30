"""Recorded verification evidence for the harness view («Results»): `scan(proj)` / `recent(proj)` read the tail of `evidence.jsonl`.

⚠Metadata only: rows keep a fixed field whitelist (counts, rc, names); anything else in a line is dropped.
⚠Only the last EV_READ_MAX bytes are read — the file is append-only and may grow without bound.
"""
import json
import os
import re
import subprocess
import time

from sidereus import config, gitinfo

EV_FILE = os.path.join(config.DATA_DIR, "evidence.jsonl")
EV_READ_MAX = 512 * 1024
EV_LIMIT_MAX = 200
EV_SCAN_MAX = 4000    # rows per scan(); the flow windows each run over all of them
EV_TS_MAX = 4102444800   # 2100-01-01 UTC
EV_KINDS = ("check", "ci")   # ci = ev_hook `gh run watch|view --exit-status` row (rc · head only)
EV_STEP = re.compile(r"[a-z0-9_-]{1,20}")
EV_MODE = re.compile(r"[a-z0-9_-]{1,20}")
EV_HEAD = re.compile(r"[0-9a-f]{4,40}")
EV_LANG = re.compile(r"[a-z]{2,5}")
EV_CM_N = 30          # newest commits matched against plrun commit stamps
EV_CM_TTL = 20.0      # s; the pipeline view polls evidence every 20 s
EV_CM_HASH = re.compile(r"[0-9a-f]{7,12}")
_CM_CACHE = {}        # repo -> (fetched_at, [{"h", "ct"}])


def _int(v, lo=-1, hi=10 ** 9):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return 0
    return max(lo, min(hi, int(v)))


def _num(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
        return 0.0
    return round(max(0.0, min(1e7, float(v))), 2)


def _ts(v):
    # ⚠Epoch seconds: _num's 1e7 cap would turn a real ts into 1970; bound at 2100-01-01 instead.
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or v <= 0 or v > EV_TS_MAX:
        return 0.0
    return round(float(v), 3)


def _step(s):
    if not isinstance(s, dict) or not isinstance(s.get("name"), str) or not EV_STEP.fullmatch(s["name"]):
        return None
    return {"name": s["name"], "rc": _int(s.get("rc"), -255, 255), "n": _int(s.get("n"), 0),
            "failed": _int(s.get("failed"), 0), "secs": _num(s.get("secs"))}


def _shot(s):
    if not isinstance(s, dict):
        return None
    lang = s.get("lang") if isinstance(s.get("lang"), str) and EV_LANG.fullmatch(s["lang"]) else ""
    return {"w": _int(s.get("w"), 0, 10000), "lang": lang, "ok": s.get("ok") is True, "diff": _num(s.get("diff"))}


def _row(d, repos):
    """Whitelisted row for one parsed line, or None when it is not a v1 record of one of `repos`."""
    if not isinstance(d, dict) or d.get("v") != 1 or d.get("kind") not in EV_KINDS or d.get("repo") not in repos:
        return None
    mode, head = d.get("mode"), d.get("head")
    steps = [x for x in (_step(s) for s in (d.get("steps") if isinstance(d.get("steps"), list) else [])[:40]) if x]
    row = {"kind": d["kind"], "ts": _ts(d.get("ts")), "mode": mode if isinstance(mode, str) and EV_MODE.fullmatch(mode) else "",
           "head": head if isinstance(head, str) and EV_HEAD.fullmatch(head) else "", "dirty": d.get("dirty") is True,
           "rc": _int(d.get("rc"), -255, 255), "steps": steps}
    if d["kind"] == "ci":
        row.update(mode="ci", steps=[], dirty=False)   # a CI row has no local steps or worktree state
    if isinstance(d.get("screen"), list):
        row["screen"] = [x for x in (_shot(s) for s in d["screen"][:20]) if x]
    return row


def _tail():
    try:
        with open(EV_FILE, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - EV_READ_MAX))
            raw = f.read(EV_READ_MAX)
    except OSError:
        return [], False
    lines = raw.split(b"\n")
    if size > EV_READ_MAX:
        lines = lines[1:]   # ⚠first line of a mid-file seek is partial
    return lines, size > EV_READ_MAX


def _line_ts(ln):
    try:
        d = json.loads(ln.decode("utf-8"))
    except ValueError:
        return 0.0
    return _ts(d.get("ts")) if isinstance(d, dict) else 0.0


def scan(proj):
    """(rows, floor): newest-first rows of realpath(proj) or its git root (≤ EV_SCAN_MAX), and the ts below which this read
    saw nothing (0 = whole file read). ⚠A run older than `floor` is outside the read, not «no evidence»."""
    if not isinstance(proj, str) or not proj:
        return [], 0.0
    repo = os.path.realpath(proj)
    # Hook rows are keyed by git root; _git_root is a cached fs walk (no git spawn) — safe on every poll.
    root = gitinfo._git_root(repo)
    repos = (repo, os.path.realpath(root)) if root else (repo,)
    lines, cut = _tail()
    out = []
    for ln in reversed(lines):
        if len(out) >= EV_SCAN_MAX:
            return out, out[-1]["ts"]   # cap hit: older rows are dropped just like a truncated tail
        try:
            r = _row(json.loads(ln.decode("utf-8")), repos)
        except ValueError:
            continue   # junk / half-written line
        if r:
            out.append(r)
    floor = next((t for t in (_line_ts(ln) for ln in lines) if t), 0.0) if cut else 0.0
    return out, floor


def recent(proj, limit=30):
    """Newest-first check rows recorded for realpath(proj) or its git root; [] when none or unreadable.
    ⚠ci rows are left out: pipeline stage labels and the gate-FAIL line read local gate runs only."""
    try:
        limit = max(1, min(EV_LIMIT_MAX, int(limit)))
    except (TypeError, ValueError):
        limit = 30
    return [r for r in scan(proj)[0] if r["kind"] == "check"][:limit]


def _git_log(repo):
    """Raw `git log` text (hash TAB commit time), or None on any git miss. ⚠Slot wait 0.5 s: never stall the poll."""
    try:
        r = gitinfo._git_run(repo, ["log", "-n", str(EV_CM_N), "--format=%h%x09%ct"], 3, wait=0.5)
    except (subprocess.TimeoutExpired, OSError):
        return None
    return r.stdout if r.returncode == 0 else None


def _now():
    return time.time()


def _parse_log(text):
    out = []
    for ln in (text or "").splitlines()[:EV_CM_N]:
        f = ln.strip().split("\t")
        if len(f) < 2 or not EV_CM_HASH.fullmatch(f[0]) or not f[1].isdigit():
            continue
        ct = int(f[1])
        if 0 < ct <= EV_TS_MAX:
            out.append({"h": f[0], "ct": ct})   # extra fields dropped: hash + time only, never the subject
    return out


def commits(proj):
    """Newest commits of proj's git root as [{"h", "ct"}]; cached EV_CM_TTL s per repo, [] on a git miss."""
    if not isinstance(proj, str) or not proj:
        return []
    repo = os.path.realpath(proj)
    root = gitinfo._git_root(repo)
    repo = os.path.realpath(root) if root else repo
    now = _now()
    hit = _CM_CACHE.get(repo)
    if hit and now - hit[0] < EV_CM_TTL:
        return list(hit[1])
    text = _git_log(repo)
    if text is None:
        return list(hit[1]) if hit else []   # slot miss keeps the previous list, uncached
    out = _parse_log(text)
    _CM_CACHE[repo] = (now, out)
    return list(out)
