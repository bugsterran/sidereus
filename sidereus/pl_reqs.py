"""Pipeline run requests the page sent (arch-map diagram, security-checks, security-fix), plain fix DMs (checks-fix, eval-fix) and «Stop» instructions.

DATA_DIR/plreq.json {"v": 1, "reqs": [{id, repo, pipeline, sid, to, mid, at, name? (eval-fix), keys? + closed? (security-fix),
stop?: {mid, at}}]} keeps who received a
request so the row survives a reload (`id` = `mid` = the request DM's mailbox id).
DATA_DIR/plstop/<sid>.json {pipeline: {at, mid, of}} = the stop marker hooks/pl_guard.py reads before a stage dispatch.
⚠Metadata only (AGENTS.md rule 1): ids, paths, times — the DM body is never stored or read back.
"""
import json
import os
import re
import subprocess
import threading
import time

from sidereus.config import CODE_DIR, DATA_DIR
from sidereus.bus import RELAY_SID, _atomic_write
from sidereus import arch_map, gitinfo

PLREQ_PATH = os.path.join(DATA_DIR, "plreq.json")   # None = memory only (--demo)
PLSTOP_DIR = os.path.join(DATA_DIR, "plstop")       # None = no marker writes (--demo)
PIPELINES = ("arch-map", "security-checks", "security-fix", "checks-fix", "eval-fix")   # checks-fix: old plain records stay readable
PLAIN = ("checks-fix", "eval-fix")   # a plain fix DM: sent/gone only, no run tracking, no stop marker (exclude-list: _state also gets other pipeline names)
RUNS = tuple(p for p in PIPELINES if p not in PLAIN)
REQ_MAX = 50              # records kept, newest
REQ_KEEP_S = 7 * 86400    # older records dropped
REPO_MAX = 300
TO_MAX = 64
READ_MAX = 262144
KEYS_MAX = 50             # security-fix: finding keys per request (= the page's cap)
KEY_MAX = 300
KEYS_CHARS_MAX = 6000     # per record: 50 records x 6000 stay under READ_MAX (_write also drops the oldest past it)
FIX_PL = "security-fix"
REVIEW_STAGE = "리뷰"      # fallback only: the review is the last stage of .claude/pipelines/security-fix.json (_review_title)
VIEW_PER_REPO = 5
RUN_SLACK_S = 60          # a run whose t0 is this far before the request still answers it (clock / tag order)
_ID = re.compile(r"^[0-9A-Za-z]{1,32}$")
_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_KEY_CTRL = re.compile(r"[\x00-\x08\x0a-\x1f\x7f]")   # ⚠a finding key (84l archChkKey) joins its fields with TAB: tab only is allowed
_NAME = re.compile(r"[a-z0-9-]{1,40}")   # = pipeline_schema._NAME (no cross-feature import); ⚠fullmatch only
_LOCK = threading.Lock()
_MEM = []                 # records while PLREQ_PATH is None
_now = time.time          # tests patch
FIX_HASH = re.compile(r"[0-9a-f]{7,12}")   # ⚠fullmatch only: the page gets a short hash, never commit text
FIX_LOG_N = 50
FIX_MISS_S = 30           # no commit yet: asked again after this; a found hash is final
FIX_CACHE_MAX = 64
_FIX_CACHE = {}           # (repo, at) -> (checked at, hash or "")


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


def _keys_ok(v):
    return (isinstance(v, list) and 0 < len(v) <= KEYS_MAX and all(isinstance(k, str) and 0 < len(k) <= KEY_MAX and not _KEY_CTRL.search(k) for k in v)
            and sum(len(k) for k in v) <= KEYS_CHARS_MAX)


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
    if r["pipeline"] == "eval-fix":   # names the pipeline file the fix is for: one project holds several
        if not (isinstance(r.get("name"), str) and _NAME.fullmatch(r["name"])):
            return None
        out["name"] = r["name"]
    if r["pipeline"] == FIX_PL and _keys_ok(r.get("keys")):   # metadata: tool · file · line · rule of each requested finding
        out["keys"] = list(r["keys"])
    if r["pipeline"] == FIX_PL and _num(r.get("closed")):
        out["closed"] = _num(r["closed"])
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
    b = json.dumps({"v": 1, "reqs": recs}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    while len(b) > READ_MAX and recs:   # ⚠past READ_MAX _read drops the whole file: shed the oldest records instead
        recs = recs[:-1]
        b = json.dumps({"v": 1, "reqs": recs}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    _atomic_write(PLREQ_PATH, b, mkdir=True)


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
    d = {k: v for k, v in d.items() if k in RUNS and isinstance(v, dict)} if isinstance(d, dict) else {}
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
    if kind not in ("req", "stop") or pipeline not in PIPELINES or not _repo_ok(repo) or (kind == "stop" and pipeline in PLAIN):
        return None, "Invalid pipeline request"
    if not (isinstance(sid, str) and RELAY_SID.match(sid)) or not _to_ok(to):
        return None, "Invalid session id"
    out = {"kind": kind, "pipeline": pipeline, "repo": repo}
    if pipeline == "eval-fix":
        name = plreq.get("name")
        if not (isinstance(name, str) and _NAME.fullmatch(name)):
            return None, "Invalid pipeline request"
        out["name"] = name
    if pipeline == FIX_PL and kind == "req":
        if not _keys_ok(plreq.get("keys")):
            return None, "Invalid pipeline request"
        out["keys"] = list(plreq["keys"])
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
        r = {"id": mid, "repo": p["repo"], "pipeline": p["pipeline"], "sid": sid, "to": to, "mid": mid, "at": now}
        if p.get("name"):
            r["name"] = p["name"]
        if p.get("keys"):
            r["keys"] = list(p["keys"])
        recs.insert(0, r)
        _write(recs)
        if p["pipeline"] not in PLAIN:
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


def _pick_run(r, row, until):
    """Newest plrun of r's pipeline in the session row started from r's send on (and before a newer request), or None."""
    run = None
    if isinstance(row, dict):
        for x in row.get("plrun") or ():
            if isinstance(x, dict) and x.get("name") == r["pipeline"] and _num(x.get("t0")) >= r["at"] - RUN_SLACK_S \
                    and not (until and _num(x.get("t0")) >= until - RUN_SLACK_S) \
                    and (run is None or _num(x.get("t0")) > _num(run.get("t0"))):
                run = x
    return run


def _review_title():
    """Last stage title of the security-fix pipeline file, so renaming the stage does not leave requests open."""
    try:
        with open(os.path.join(CODE_DIR, ".claude", "pipelines", FIX_PL + ".json"), encoding="utf-8") as f:
            t = json.load(f)["stages"][-1]["title"]
        return t if isinstance(t, str) and t else REVIEW_STAGE
    except Exception:
        return REVIEW_STAGE


def _review_done(run):
    st = run.get("stages") if isinstance(run, dict) and isinstance(run.get("stages"), dict) else {}
    s = st.get(_review_title())
    return isinstance(s, dict) and s.get("o") == "done"


def _fix_state(r, run, alive):
    """security-fix: «done» only on evidence that the review stage passed (now, or recorded as `closed` earlier).
    ⚠No result_at / superseded shortcut: a re-scan alone (or a newer request) is not a reviewed fix."""
    if r.get("closed") or _review_done(run):
        return "done", ""
    ended = run is not None and bool(_num(run.get("end")) or _num(run.get("stop")))
    is_open = alive and run is not None and not ended
    stage = (run.get("cur") if is_open and isinstance(run.get("cur"), str) else "") or ""
    if r.get("stop"):
        return ("stopping" if is_open else "stopped"), stage
    if is_open:
        return "run", stage
    return ("sent" if alive else "gone"), ""


def _close(ids, now):
    """Stamp `closed` once on each security-fix record that just reached «done» (hooks/pl_flow.py reads it)."""
    with _LOCK:
        recs = _read(now)
        hit = False
        for r in recs:
            if r["id"] in ids and r["pipeline"] == FIX_PL and not r.get("closed"):
                r["closed"] = now
                hit = True
        if hit:
            _write(recs)


def _state(r, row, arch, until=0.0):
    """(state, stage title) of one record against its session row and the server-tracked run (archRun/secRun) of its repo.
    until = `at` of a newer request of the same pipeline to the same session (0 = none): runs from then on answer that one."""
    alive = isinstance(row, dict) and row.get("state") not in ("done", "gone")
    if r["pipeline"] in PLAIN:   # a fix request has no run to track: delivery/ack is read from ACK on the page
        # ⚠checks-fix only: a newer security-checks result is its re-scan; eval-fix has no such repo-wide end signal.
        if r["pipeline"] == "checks-fix" and arch_map.result_at("security-checks", r["repo"]) > r["at"]:
            return "done", ""
        return ("sent" if alive else "gone"), ""
    run = _pick_run(r, row, until)
    if r["pipeline"] == FIX_PL:
        return _fix_state(r, run, alive)
    if until and isinstance(arch, dict) and _num(arch.get("t0")) >= until - RUN_SLACK_S:
        arch = None   # ⚠plrun has no repo: without this the newer request's run also lit the older one as «run»
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
    if ended or until:   # superseded: the session took the newer request, so the older one no longer waits
        return "done", ""
    # ⚠Codex / hookless runs leave no plrun: the repo's gate result written after the request is the only end signal.
    if run is None and arch_map.result_at(r["pipeline"], r["repo"]) > r["at"]:
        return "done", ""
    return ("sent" if alive else "gone"), ""


def _git_log(repo, at):
    """Raw `git log` (hash TAB commit time) of commits since `at`, or None on any git miss. ⚠Slot wait 0.5 s: never stall the poll."""
    try:
        r = gitinfo._git_run(repo, ["log", "-n", str(FIX_LOG_N), "--since=@%d" % (int(at) - 1), "--format=%h%x09%ct", "HEAD"], 3, wait=0.5)
    except (subprocess.TimeoutExpired, OSError):
        return None
    return r.stdout if r.returncode == 0 else None


def _fix_commit(repo, at, now):
    """Short hash of the first commit in repo after a checks-fix / security-fix request at `at`, "" if none yet (hash + time only)."""
    k = (repo, at)
    hit = _FIX_CACHE.get(k)
    if hit and (hit[1] or now - hit[0] < FIX_MISS_S):
        return hit[1]
    text = _git_log(repo, at)
    h = ""
    for ln in (text or "").splitlines()[:FIX_LOG_N]:   # newest first: the last match is the oldest after the request
        f = ln.strip().split("\t")
        if len(f) >= 2 and FIX_HASH.fullmatch(f[0]) and f[1].isdigit() and int(f[1]) > at:
            h = f[0]
    if text is None and hit:
        return hit[1]   # slot miss keeps the previous answer, uncached
    _FIX_CACHE.pop(k, None)
    _FIX_CACHE[k] = (now, h)
    while len(_FIX_CACHE) > FIX_CACHE_MAX:
        _FIX_CACHE.pop(next(iter(_FIX_CACHE)))
    return h


def view(sessions, arch_run, sec_run=None, now=None):
    """`/api/state` `plReq`: {repo: [{id, pipeline, sid, to, project, state, stage, at, stopAt?, name?, keys?, reviewOk?, fix?}]} newest first."""
    now = _now() if now is None else now
    with _LOCK:
        recs = _read(now)
    rows = {}
    for s in sessions or ():
        if isinstance(s, dict) and isinstance(s.get("sid"), str) and s["sid"]:
            rows.setdefault(s["sid"], s)
    runs = {"arch-map": arch_run if isinstance(arch_run, dict) else {}, "security-checks": sec_run if isinstance(sec_run, dict) else {}}
    out, newer, closing = {}, {}, set()
    for r in recs:   # newest first: newer[(sid, pipeline)] = `at` of the request after this one
        k = (r["sid"], r["pipeline"])
        until = newer.get(k, 0.0)
        newer[k] = r["at"]
        if sum(1 for x in out.get(r["repo"], ()) if x["pipeline"] == r["pipeline"] and x.get("name") == r.get("name")) >= VIEW_PER_REPO:   # per pipeline (+ eval-fix name): fix DMs never crowd out runs
            continue
        row = rows.get(r["sid"])
        st, stage = _state(r, row, runs.get(r["pipeline"], {}).get(r["repo"]), until)
        v = {"id": r["id"], "pipeline": r["pipeline"], "sid": r["sid"], "to": r["to"],
             "project": (row.get("project") if isinstance(row, dict) and isinstance(row.get("project"), str) else ""),
             "state": st, "stage": stage[:80], "at": r["at"]}
        if r.get("stop"):
            v["stopAt"] = r["stop"]["at"]
        if r.get("name"):
            v["name"] = r["name"]
        if r["pipeline"] == FIX_PL:
            v["keys"] = list(r.get("keys") or ())
            v["reviewOk"] = st == "done"
            if st == "done" and not r.get("closed"):
                closing.add(r["id"])
        # ⚠security-fix: the hash is shown only with no run attached («handled without the pipeline»)
        no_run = r["pipeline"] == FIX_PL and st in ("sent", "gone") and _pick_run(r, row, until) is None
        if (r["pipeline"] == "checks-fix" and st != "done") or no_run:   # a re-scan already closes the line: no git call
            fx = _fix_commit(r["repo"], r["at"], now)
            if fx:
                v["fix"] = fx
        out.setdefault(r["repo"], []).append(v)
    if closing:
        _close(closing, now)
    return out
