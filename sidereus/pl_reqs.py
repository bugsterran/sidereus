"""Pipeline run requests the page sent (arch-map diagram, security-checks) and their «Stop» instructions.

DATA_DIR/plreq.json {"v": 1, "reqs": [{id, repo, pipeline, sid, to, mid, at, stop?: {mid, at}}]} keeps who received a
request so the row survives a reload (`id` = `mid` = the request DM's mailbox id).
DATA_DIR/plstop/<sid>.json {pipeline: {at, mid, of}} = the stop marker hooks/pl_guard.py reads before a stage dispatch.
⚠Metadata only (AGENTS.md rule 1): ids, paths, times — the DM body is never stored or read back.
"""
import json
import os
import re
import threading
import time

from sidereus.config import DATA_DIR
from sidereus.bus import RELAY_SID, _atomic_write
from sidereus import arch_map

PLREQ_PATH = os.path.join(DATA_DIR, "plreq.json")   # None = memory only (--demo)
PLSTOP_DIR = os.path.join(DATA_DIR, "plstop")       # None = no marker writes (--demo)
PIPELINES = ("arch-map", "security-checks")
REQ_MAX = 50              # records kept, newest
REQ_KEEP_S = 7 * 86400    # older records dropped
REPO_MAX = 300
TO_MAX = 64
READ_MAX = 65536
VIEW_PER_REPO = 5
RUN_SLACK_S = 60          # a run whose t0 is this far before the request still answers it (clock / tag order)
_ID = re.compile(r"^[0-9A-Za-z]{1,32}$")
_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_LOCK = threading.Lock()
_MEM = []                 # records while PLREQ_PATH is None
_now = time.time          # tests patch


def memory_only():
    """`--demo`: nothing is read or written (called by chat_server.main before serving)."""
    global PLREQ_PATH, PLSTOP_DIR
    PLREQ_PATH = None
    PLSTOP_DIR = None


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def _repo_ok(r):
    return isinstance(r, str) and 0 < len(r) <= REPO_MAX and os.path.isabs(r) and not _CTRL.search(r)


def _to_ok(t):
    return isinstance(t, str) and 0 < len(t) <= TO_MAX and not _CTRL.search(t)


def _clean(r, now):
    """Allow-listed copy of one stored record, or None."""
    if not (isinstance(r, dict) and isinstance(r.get("id"), str) and _ID.match(r["id"]) and _repo_ok(r.get("repo"))
            and r.get("pipeline") in PIPELINES and isinstance(r.get("sid"), str) and RELAY_SID.match(r["sid"])
            and _to_ok(r.get("to")) and isinstance(r.get("mid"), str) and _ID.match(r["mid"])):
        return None
    at = _num(r.get("at"))
    if not at or now - at > REQ_KEEP_S:
        return None
    out = {k: r[k] for k in ("id", "repo", "pipeline", "sid", "to", "mid")}
    out["at"] = at
    s = r.get("stop")
    if isinstance(s, dict) and isinstance(s.get("mid"), str) and _ID.match(s["mid"]) and _num(s.get("at")):
        out["stop"] = {"mid": s["mid"], "at": _num(s["at"])}
    return out


def _read(now):
    if PLREQ_PATH is None:
        raw = _MEM
    else:
        try:
            with open(PLREQ_PATH, "rb") as f:
                b = f.read(READ_MAX + 1)
            d = json.loads(b.decode("utf-8")) if len(b) <= READ_MAX else {}
        except (OSError, ValueError):
            d = {}
        raw = d.get("reqs") if isinstance(d, dict) and isinstance(d.get("reqs"), list) else []
    out = [c for c in (_clean(r, now) for r in raw) if c]
    out.sort(key=lambda r: -r["at"])
    return out[:REQ_MAX]


def _write(recs):
    recs = recs[:REQ_MAX]
    if PLREQ_PATH is None:
        _MEM[:] = recs
        return
    _atomic_write(PLREQ_PATH, json.dumps({"v": 1, "reqs": recs}, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                  mkdir=True)


def _marker(sid, pipeline, entry):
    """Set (`entry` dict) or delete (None) one pipeline's stop entry in plstop/<sid>.json; an empty marker is removed."""
    if PLSTOP_DIR is None or not RELAY_SID.match(sid):
        return
    fp = os.path.join(PLSTOP_DIR, sid + ".json")
    try:
        with open(fp, "rb") as f:
            d = json.loads(f.read(READ_MAX).decode("utf-8"))
    except (OSError, ValueError):
        d = {}
    d = {k: v for k, v in d.items() if k in PIPELINES and isinstance(v, dict)} if isinstance(d, dict) else {}
    if entry is None:
        if pipeline not in d:
            return
        d.pop(pipeline)
    else:
        d[pipeline] = entry
    if not d:
        if os.path.exists(fp):
            os.remove(fp)
        return
    _atomic_write(fp, json.dumps(d, separators=(",", ":")).encode("utf-8"), mkdir=True)


def check(plreq, req):
    """(clean plreq, None) or (None, refusal) for /api/dm `plreq`; ⚠a stop is checked here, before anything is sent."""
    if not isinstance(plreq, dict) or req.get("relay") is not True:
        return None, "A pipeline request must be a relay"
    kind, pipeline, repo = plreq.get("kind"), plreq.get("pipeline"), plreq.get("repo")
    sid, to = req.get("sid"), str(req.get("to") or "").strip()
    if kind not in ("req", "stop") or pipeline not in PIPELINES or not _repo_ok(repo):
        return None, "Invalid pipeline request"
    if not (isinstance(sid, str) and RELAY_SID.match(sid)) or not _to_ok(to):
        return None, "Invalid session id"
    out = {"kind": kind, "pipeline": pipeline, "repo": repo}
    if kind == "stop":
        of = plreq.get("of")
        with _LOCK:
            hit = isinstance(of, str) and any(r["id"] == of and r["sid"] == sid and r["to"] == to and r["pipeline"] == pipeline
                                              and r["repo"] == repo for r in _read(_now()))
        if not hit:
            return None, "No such request to stop"
        out["of"] = of
    return out, None


def record(p, sid, to, mid):
    """After a request DM was sent: keep who got it, and lift any earlier stop of that pipeline for that session."""
    now = _now()
    with _LOCK:
        recs = _read(now)
        recs.insert(0, {"id": mid, "repo": p["repo"], "pipeline": p["pipeline"], "sid": sid, "to": to, "mid": mid, "at": now})
        _write(recs)
        _marker(sid, p["pipeline"], None)


def stop(p, sid, to, mid):
    """After a stop DM was sent: mark the record and write the marker the session's own hook enforces."""
    now = _now()
    with _LOCK:
        recs = _read(now)
        for r in recs:
            if r["id"] == p["of"] and r["sid"] == sid and r["to"] == to:
                r["stop"] = {"mid": mid, "at": now}
        _write(recs)
        _marker(sid, p["pipeline"], {"at": now, "mid": mid, "of": p["of"]})


REQ_TARGET_S = 6 * 3600   # = arch_map.ARCH_PEND_S: an older request no longer names a session's run target


def req_repo(sid, pipeline, now):
    """Repo of the newest unstopped request of pipeline sent to sid within REQ_TARGET_S, "" if none (arch_map._target)."""
    with _LOCK:
        recs = _read(now)
    for r in recs:
        if r["sid"] == sid and r["pipeline"] == pipeline:
            return r["repo"] if not r.get("stop") and now - r["at"] <= REQ_TARGET_S else ""
    return ""


arch_map.set_req_source(req_repo)


def _state(r, row, arch):
    """(state, stage title) of one record against its session row and the server-tracked run (archRun/secRun) of its repo."""
    alive = isinstance(row, dict) and row.get("state") not in ("done", "gone")
    run = None
    if isinstance(row, dict):
        for x in row.get("plrun") or ():
            if isinstance(x, dict) and x.get("name") == r["pipeline"] and _num(x.get("t0")) >= r["at"] - RUN_SLACK_S \
                    and (run is None or _num(x.get("t0")) > _num(run.get("t0"))):
                run = x
    ended = run is not None and bool(_num(run.get("end")) or _num(run.get("stop")))
    # ⚠Codex leaves a record at end 0: a result newer than its last sign ends it unless the tracked run still runs it.
    mine = isinstance(arch, dict) and arch.get("sid") == r["sid"]
    ended = ended or (run is not None and not mine and arch_map._closed_by_result(run, r["repo"], r["pipeline"]))
    stage = (run.get("cur") if run is not None and isinstance(run.get("cur"), str) else "") or ""
    is_open = alive and run is not None and not ended
    if alive and isinstance(arch, dict) and arch.get("sid") == r["sid"] and not ended:
        is_open, stage = True, (arch.get("stage") if isinstance(arch.get("stage"), str) else "") or stage
    if r.get("stop"):
        return ("stopping" if is_open else "stopped"), stage if is_open else ""
    if is_open:
        return "run", stage
    if ended:
        return "done", ""
    # ⚠Codex / hookless runs leave no plrun: the repo's gate result written after the request is the only end signal.
    if run is None and arch_map.result_at(r["pipeline"], r["repo"]) > r["at"]:
        return "done", ""
    return ("sent" if alive else "gone"), ""


def view(sessions, arch_run, sec_run=None, now=None):
    """`/api/state` `plReq`: {repo: [{id, pipeline, sid, to, project, state, stage, at, stopAt?}]} newest first."""
    now = _now() if now is None else now
    with _LOCK:
        recs = _read(now)
    rows = {}
    for s in sessions or ():
        if isinstance(s, dict) and isinstance(s.get("sid"), str) and s["sid"]:
            rows.setdefault(s["sid"], s)
    runs = {"arch-map": arch_run if isinstance(arch_run, dict) else {}, "security-checks": sec_run if isinstance(sec_run, dict) else {}}
    out = {}
    for r in recs:
        if len(out.get(r["repo"], ())) >= VIEW_PER_REPO:
            continue
        row = rows.get(r["sid"])
        st, stage = _state(r, row, runs.get(r["pipeline"], {}).get(r["repo"]))
        v = {"id": r["id"], "pipeline": r["pipeline"], "sid": r["sid"], "to": r["to"],
             "project": (row.get("project") if isinstance(row, dict) and isinstance(row.get("project"), str) else ""),
             "state": st, "stage": stage[:80], "at": r["at"]}
        if r.get("stop"):
            v["stopAt"] = r["stop"]["at"]
        out.setdefault(r["repo"], []).append(v)
    return out
