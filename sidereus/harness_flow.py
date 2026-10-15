"""Harness «Flow»: `flow(proj, rows, trail)` → one 7-node flow per pipeline run (req · guard · edit · gate · review · commit · keep).

Runs come from DATA_DIR/plmark/<sid>.runs.json (hooks/pl_flow.py), evidence rows from harness_evidence.scan, «Kept»
from harness_trail. No run → one flow from the latest evidence burst.
⚠Metadata only (rule 1): counts, rc, hashes, times, stage/step titles and changed file paths — never diff bodies,
  commit subjects or anything from runs.json outside the pl_runs allow-list.
⚠Guard `deny` = runs.json `deny` (pl_flow.py counts its denials); None only for runs written before that field (0 = counted, nothing denied).
"""
import glob
import json
import os
import re
import subprocess
import time

from sidereus import gitinfo, pl_runs
from sidereus.config import DATA_DIR

HF_DIR = os.path.join(DATA_DIR, "plmark")
HF_KEEP_S = 7 * 86400      # run history kept here; ⚠not pl_runs.PLR_KEEP_S (6 h, live stage lighting only)
HF_FILES_MAX = 40          # newest runs files read per call
HF_RUNS_MAX = 6            # flows returned
HF_WIN_S = 7200            # evidence-only flow: rows this close to the newest one
HF_PRE_S, HF_POST_S = 5, 60   # run window [t0-5, (end|t1)+60], same as the page's plEvLine
HF_DIFF_MAX = 3            # uncached diffs per call (2 git spawns each = 6)
HF_GIT_TIMEOUT, HF_GIT_WAIT = 2, 0.5
HF_REC_MAX = 30
HF_PATH_MAX = 300
HF_CACHE_MAX = 64
HF_ST = ("ok", "ng", "run", "none")
HF_HEX = re.compile(r"[0-9a-f]{7,40}")
HF_REVIEW = re.compile(r"리뷰|review", re.I)
HF_DENY_CODES = ("jump", "agent", "model", "tag", "stage", "stop")   # hooks/pl_flow.py DENY_CODES
HF_DL_MAX = 20
_HF_CACHE = {}             # (repo, a, b) -> (rec, files, commits) or None; commit pairs never change
_now = time.time


def _git(repo, args):
    try:
        r = gitinfo._git_run(repo, args, HF_GIT_TIMEOUT, wait=HF_GIT_WAIT)
    except (subprocess.TimeoutExpired, OSError):
        return None
    return (r.stdout or "") if r.returncode == 0 else None


def _diff(repo, a, b):
    """(rec [{path, add, del}] ≤ HF_REC_MAX, files, commits) for a..b, or None on git failure. Tests patch this."""
    out = _git(repo, ["diff", "--numstat", a, b])
    cnt = _git(repo, ["rev-list", "--count", "%s..%s" % (a, b)]) if out is not None else None
    if out is None or cnt is None or not cnt.strip().isdigit():
        return None
    rec = []
    lines = [ln for ln in out.splitlines() if ln.count("\t") >= 2]
    for ln in lines[:HF_REC_MAX]:
        ad, de, path = ln.split("\t", 2)
        rec.append({"path": path[:HF_PATH_MAX], "add": int(ad) if ad.isdigit() else None,
                    "del": int(de) if de.isdigit() else None})   # binary files: "-"
    return rec, len(lines), int(cnt.strip())


def _repos(proj):
    if not isinstance(proj, str) or not proj:
        return ()
    rp = os.path.realpath(proj)
    root = gitinfo._git_root(rp)
    return (rp, os.path.realpath(root)) if root else (rp,)


def _parse(sid, name, r, now):
    if not (isinstance(name, str) and re.match(r"^[a-z0-9-]{1,40}$", name) and isinstance(r, dict)):
        return None
    t1 = pl_runs._num(r.get("t1"))
    if not t1 or now - t1 > HF_KEEP_S:
        return None
    t0 = pl_runs._num(r.get("t0")) or t1
    return {"id": "%s:%s:%d" % (sid[:8], name, int(t0)), "name": name, "sid8": sid[:8], "t0": t0, "t1": t1,
            "end": pl_runs._num(r.get("end")), "st": pl_runs._stages(r.get("st")), "lb": pl_runs._loopbacks(r.get("lb")),
            "deny": _deny_n(r.get("deny")), "dl": _deny_log(r.get("dl")), "h0": _hex(r.get("h0")), "h1": _hex(r.get("h1"))}


def _hex(v):
    return v if isinstance(v, str) and HF_HEX.fullmatch(v) else ""


def _deny_n(v):
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None


def _deny_log(v):
    """[{k: "deny", ts, title, code}] from runs.json `dl`; unknown codes and extra keys dropped."""
    out = []
    for e in (v[-HF_DL_MAX:] if isinstance(v, list) else ()):
        if isinstance(e, dict) and e.get("c") in HF_DENY_CODES and pl_runs._num(e.get("t")):
            out.append({"k": "deny", "ts": pl_runs._num(e.get("t")), "code": e["c"],
                        "title": e["title"][:40] if isinstance(e.get("title"), str) else ""})
    return out


def _disk_runs(repos, now):
    """Runs of `repos` from the newest HF_FILES_MAX runs files; junk files and other projects skipped."""
    files = []
    for fp in glob.glob(os.path.join(HF_DIR, "*.runs.json")):
        try:
            files.append((os.path.getmtime(fp), fp))
        except OSError:
            continue
    out = []
    for mt, fp in sorted(files, reverse=True)[:HF_FILES_MAX]:
        sid = os.path.basename(fp)[:-len(".runs.json")]
        if now - mt > HF_KEEP_S or not pl_runs._PLR_SID.match(sid):
            continue
        try:
            with open(fp, "rb") as f:
                d = json.loads(f.read(pl_runs.PLR_READ_MAX))
        except (OSError, ValueError):
            continue
        runs = d.get("runs") if isinstance(d, dict) else None
        for name, r in (runs.items() if isinstance(runs, dict) else ()):
            p = pl_runs._proj(r.get("proj")) if isinstance(r, dict) else ""
            if p and os.path.realpath(p) in repos:
                x = _parse(sid, name, r, now)
                if x:
                    out.append(x)
    return out


def _given_runs(runs, now):
    out = []
    for r in runs if isinstance(runs, list) else ():
        sid = r.get("sid") if isinstance(r, dict) else None
        x = _parse(sid, r.get("name"), r, now) if isinstance(sid, str) and pl_runs._PLR_SID.match(sid) else None
        if x:
            out.append(x)
    return out


def _row(r):
    """Whitelisted evidence row (same shape as harness_evidence rows), or None."""
    if not isinstance(r, dict) or r.get("kind") != "check":
        return None
    ts, rc = r.get("ts"), r.get("rc")
    if isinstance(ts, bool) or not isinstance(ts, (int, float)) or ts <= 0 or isinstance(rc, bool) or not isinstance(rc, int):
        return None
    steps = [{"name": s["name"][:20], "rc": s.get("rc"), "n": s.get("n"), "failed": s.get("failed"), "secs": s.get("secs")}
             for s in (r.get("steps") if isinstance(r.get("steps"), list) else []) if isinstance(s, dict) and isinstance(s.get("name"), str)]
    head = r.get("head") if isinstance(r.get("head"), str) and HF_HEX.fullmatch(r["head"]) else ""
    mode = r.get("mode")[:20] if isinstance(r.get("mode"), str) else ""
    out = {"kind": "check", "ts": float(ts), "mode": mode, "head": head, "dirty": r.get("dirty") is True, "rc": rc, "steps": steps}
    if isinstance(r.get("screen"), list):
        out["screen"] = [dict((k, s.get(k)) for k in ("w", "lang", "ok", "diff")) for s in r["screen"][:20] if isinstance(s, dict)]
    return out


def _node(k, st, v, rec=None):
    return {"k": k, "st": st if st in HF_ST else "none", "v": v, "rec": rec or [], "why": ""}


class _Budget(object):
    def __init__(self, fn):
        self.fn, self.left = fn, HF_DIFF_MAX

    def diff(self, repo, a, b):
        if a == b:
            return [], 0, 0
        if self.fn is _diff and not repo:
            return None
        key = (repo, a, b)
        if self.fn is _diff and key in _HF_CACHE:
            return _HF_CACHE[key]
        if self.left <= 0:
            return None
        self.left -= 1
        out = self.fn(repo, a, b)
        if self.fn is _diff:   # failures too: a non-repo or gc'd head would otherwise respawn git on every call
            if len(_HF_CACHE) >= HF_CACHE_MAX:
                _HF_CACHE.clear()
            _HF_CACHE[key] = out
        return out


def _heads(run, before, win, commits, lo, hi):
    """(a, b): evidence heads first; else run h0 / the newest commit made inside the window / run h1 (runs.json)."""
    a = next((r["head"] for r in reversed(before) if r["head"]), "") or (run["h0"] if run else "")
    b = next((r["head"] for r in reversed(win) if r["head"]), "")
    if not b:
        cm = [c for c in (commits if isinstance(commits, list) else ()) if isinstance(c, dict) and _hex(c.get("h"))
              and isinstance(c.get("ct"), (int, float)) and not isinstance(c.get("ct"), bool) and lo <= c["ct"] <= hi]
        b = max(cm, key=lambda c: c["ct"])["h"] if cm else (run["h1"] if run else "")
    return a, b


def _edit(a, b, win, repo, bud):
    dirty = win[-1]["dirty"] if win else False
    v = {"files": None, "commits": None, "from": a, "to": b, "dirty": dirty}
    got = bud.diff(repo, a, b) if a and b else None
    if got is None:
        return _node("edit", "none", v)
    v["files"], v["commits"] = got[1], got[2]
    return _node("edit", "ok", v, got[0])


def _gate(win):
    last = {}
    for r in win:
        last[r["mode"]] = r
    steps = [dict(s, mode=m) for m, r in last.items() for s in r["steps"]]
    seen, r2g = set(), False
    for r in win:
        if r["rc"] != 0:
            seen.add(r["mode"])
        elif r["mode"] in seen:
            r2g = True
    st = "none" if not win else ("ok" if all(r["rc"] == 0 for r in last.values()) else "ng")
    return _node("gate", st, {"steps": steps, "rows": len(win), "r2g": r2g}, list(reversed(win))[:HF_REC_MAX])


def _guard(run):
    if run is None:
        return _node("guard", "none", None)
    skips = [t for t, s in run["st"].items() if s["s"] == "skip"]
    rec = list(reversed(run["dl"])) + [{"k": "skip", "title": t} for t in skips] \
        + [{"k": "back", "f": e["f"], "g": e["g"], "n": e["n"]} for e in run["lb"]]
    # a deny means the guard worked: "ok" whenever the count exists
    return _node("guard", "none" if run["deny"] is None else "ok",
                 {"deny": run["deny"], "skip": len(skips), "loop": sum(e["n"] for e in run["lb"])}, rec)


def _review(run):
    hit = next((t for t in (run["st"] if run else {}) if HF_REVIEW.search(t)), None)
    if hit is None:
        return _node("review", "none", None)
    s = run["st"][hit]
    back = sum(e["n"] for e in run["lb"] if e["f"] == hit)
    st = {"done": "ok", "fail": "ng", "back": "ng", "skip": "none"}.get(s["s"], "ok" if run["end"] else "run")
    return _node("review", st, {"o": s["s"], "n": s["n"], "back": back})


def _keep(last, trail):
    held = (trail or {}).get("held") if isinstance(trail, dict) else None
    h = next((x for x in (held if isinstance(held, list) else ()) if isinstance(x, dict) and last and last["rc"] == 0
              and last["head"] and x.get("head") == last["head"] and x.get("mode") == last["mode"]), None)
    if h is None:
        return _node("keep", "none", None)
    st = {"held": "ok", "refixed": "ok", "broke": "ng", "reverted": "ng", "gone": "ng"}.get(h.get("state"), "none")
    return _node("keep", st, {"state": h.get("state"), "mode": h.get("mode"), "ts": h.get("ts")})


def _why(n, run, rows, floor, last, trail):
    """Reason a node is empty: window (run starts below the read floor) · norec · pending · na; "" when unknown."""
    k = n["k"]
    if n["st"] != "none" and not (k == "commit" and n["v"] and n["v"]["dirty"]):
        return ""
    if k in ("req", "guard", "review") and run is None:
        return "na"
    if k == "review":
        return "" if any(HF_REVIEW.search(t) for t in run["st"]) else "na"
    if k in ("req", "guard"):
        return ""
    if run and floor > 0 and run["t0"] - HF_PRE_S < floor:
        return "window"
    if not rows and not floor and not (k in ("edit", "commit") and run and (run["h0"] or run["h1"])):
        return "norec"
    if k == "commit" and n["v"] and n["v"]["dirty"]:
        return "pending"
    if k in ("gate", "commit") and run and not run["end"]:
        return "pending"
    if k == "keep":
        clean = bool(last and last["rc"] == 0 and last["head"] and not last["dirty"])
        held = (trail or {}).get("held") if isinstance(trail, dict) else None
        unchecked = any(isinstance(x, dict) and x.get("state") == "unchecked" and last and x.get("head") == last["head"]
                        for x in (held if isinstance(held, list) else ()))
        return "pending" if not clean or unchecked else ""
    return ""


def _flow(run, rows, lo, hi, repo, trail, bud, floor=0, commits=None):
    win = [r for r in rows if lo <= r["ts"] <= hi]
    before = [r for r in rows if r["ts"] < lo]
    last = win[-1] if win else None
    if run:
        meta = {"id": run["id"], "src": "plrun", "name": run["name"], "sid8": run["sid8"], "t0": run["t0"], "t1": run["t1"], "end": run["end"]}
    else:
        meta = {"id": "evidence", "src": "evidence", "name": "", "sid8": "", "t0": lo, "t1": hi, "end": hi}
    meta["floor"] = floor
    a, b = _heads(run, before, win, commits, lo, hi)
    req = _node("req", ("ok" if run["end"] else "run") if run else "none", {"t0": meta["t0"], "sid8": meta["sid8"], "name": meta["name"]})
    # no evidence: a head from git/runs.json counts only when it moved (h1 == h0 = nothing committed)
    dirty = last["dirty"] if last else None
    has = bool(b) and (last is not None or b != a)
    commit = _node("commit", ("run" if dirty else "ok") if has else "none", {"head": b, "dirty": dirty} if has or last else None)
    meta["nodes"] = [req, _guard(run), _edit(a, b, win, repo, bud), _gate(win), _review(run), commit, _keep(last, trail)]
    for n in meta["nodes"]:
        n["why"] = _why(n, run, rows, floor, last, trail)
    return meta


def flow(proj, rows, trail, runs=None, diff=None, floor=0, commits=None):
    """[{id, src, name, sid8, t0, t1, end, floor, nodes: [{k, st, v, rec, why}] × 7}] newest first (≤ HF_RUNS_MAX).
    `rows` = newest-first evidence rows (all of harness_evidence.scan, windowed per run); `floor` = its read floor;
    `commits` = harness_evidence.commits; `runs` (demo) = [{sid, name, **runs.json run}] instead of plmark; `diff` replaces _diff."""
    floor = floor if isinstance(floor, (int, float)) and not isinstance(floor, bool) and floor > 0 else 0
    now = _now()
    repos = _repos(proj)
    ev = sorted((r for r in (_row(x) for x in (rows if isinstance(rows, list) else ())) if r), key=lambda r: r["ts"])
    got = _given_runs(runs, now) if runs is not None else _disk_runs(repos, now)
    got.sort(key=lambda r: -r["t1"])
    bud = _Budget(diff or _diff)
    repo = repos[-1] if repos else ""
    if got:
        return [_flow(r, ev, r["t0"] - HF_PRE_S, (r["end"] or r["t1"]) + HF_POST_S, repo, trail, bud, floor, commits) for r in got[:HF_RUNS_MAX]]
    if not ev:
        return []
    hi = ev[-1]["ts"]
    lo = min(r["ts"] for r in ev if r["ts"] >= hi - HF_WIN_S)
    return [_flow(None, ev, lo, hi, repo, trail, bud, floor, commits)]
