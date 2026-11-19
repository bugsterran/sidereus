"""`/api/state` `archRun` · `secRun` · `briefRun`: arch-map / security-checks / arch-brief runs in progress, from session rows.

Metadata only — stage title, times, session id. Map reads live in arch_map.
⚠SIDEREUS_ROOT and _REQ_SRC are read as AM.<name> at call time: a from-import would miss patches/registration on arch_map.
"""
import json
import os
import re
import time

from sidereus.arch_verify import BRIEF_OK, ARCH_DIR, COMMIT_RE, read_json, repo_key
from sidereus import arch_map as AM
from sidereus import arch_prov
from sidereus.arch_map import _newest
from sidereus.sec_checks import LOG_FILE as SEC_LOG_FILE

ARCH_PL = "arch-map"
_ARCH_TAG = re.compile(r"\[pl:arch-map/([^\]]{1,80})\]")
SEC_PL = "security-checks"   # = ARCH_SEC_PL (84l); its runs are tracked the same way (state `secRun`)
BRIEF_PL = "arch-brief"     # ends on the gate's brief.ok.json (state `briefRun` via brief_runs)
_TAGS = {ARCH_PL: _ARCH_TAG, SEC_PL: re.compile(r"\[pl:security-checks/([^\]]{1,80})\]"), BRIEF_PL: re.compile(r"\[pl:arch-brief/([^\]]{1,80})\]")}
ARCH_RUN_GAP_S = 180       # a run stays «in progress» this long after its last tagged sign (main thinks between stages)
ARCH_BUSY_S = 30 * 60      # a busy session keeps its open plrun only this long after the run last moved
ARCH_PEND_S = 6 * 3600     # = pl_runs.PLR_KEEP_S: an older plan.json without verify.json is an abandoned run
_RUN_SEEN = {}             # project path -> {stage, sid, t0, at}: last tagged sign per project (bridges stage gaps)
_SEC_SEEN = {}             # same for security-checks runs
_BRIEF_SEEN = {}           # same for arch-brief runs


def _stages(pl):
    """Titled stages of Sidereus' pipeline pl in order, [] if unreadable (read directly: sidereus.pipeline is a feature module)."""
    if not AM.SIDEREUS_ROOT:
        return []
    try:
        with open(os.path.join(AM.SIDEREUS_ROOT, ".claude", "pipelines", pl + ".json"), "rb") as f:
            P = json.loads(f.read(65536))
        return [s for s in P["stages"] if isinstance(s, dict) and isinstance(s.get("title"), str)]
    except (OSError, ValueError, TypeError, KeyError):
        return []


def _titles():
    return [s["title"] for s in _stages(ARCH_PL)]


def _late_titles():
    """arch-map titles from its map gate (arch_verify) on when overview stages follow it, else an empty set.
    ⚠verify.json no longer ends such a run: these stages end on the overview gate's brief.ok.json instead."""
    st = _stages(ARCH_PL)
    g = next((i for i, s in enumerate(st) if "arch_verify.py" in str(s.get("gate") or "")), -1)
    return frozenset(s["title"] for s in st[g:]) if 0 <= g < len(st) - 1 else frozenset()


def _end_at(pl, root, stage, late):
    """Result time that ends a run of pl sitting on `stage`; a late arch-map stage needs a brief.ok.json newer than verify.json."""
    b = _result_at(root, BRIEF_OK) if pl == ARCH_PL and stage in late else None   # ⚠no brief.ok.json = 0.0, not None: still 0
    return _final_at(pl, root) if b is None else (b if b > _result_at(root) else 0.0)


def _pl_titles(pl):
    """Stage titles of pipeline pl (arch-map through _titles so tests can patch it)."""
    if pl == ARCH_PL:
        return _titles()
    return [s["title"] for s in _stages(pl)] if pl in _TAGS else []


def _mtime(fp):
    try:
        return os.path.getmtime(fp)
    except OSError:
        return 0.0


SEC_TAIL_MAX = 65536   # bytes of security-log.jsonl read from its end
_SEC_LOG_CACHE = {}    # log path -> ((mtime, size), newest review/mark `at`)


def _sec_final_at(root):
    """Newest `at` of a review-stage record (src review | mark) in root's security-log.jsonl tail, 0 if none.
    ⚠Not the log mtime or checks-security.json: stage 1 appends a scan record and writes the scan file, so either
    would end the run before the threat-model review. Re-read only when the log's mtime/size changes."""
    fp = os.path.join(ARCH_DIR, repo_key(root), SEC_LOG_FILE)
    try:
        st = os.stat(fp)
    except OSError:
        return 0.0
    sig = (st.st_mtime, st.st_size)
    hit = _SEC_LOG_CACHE.get(fp)
    if hit and hit[0] == sig:
        return hit[1]
    best = 0.0
    try:
        with open(fp, "rb") as f:
            f.seek(max(0, st.st_size - SEC_TAIL_MAX))
            tail = f.read(SEC_TAIL_MAX)
    except OSError:
        return 0.0
    for ln in tail.split(b"\n"):
        try:
            r = json.loads(ln)
        except ValueError:
            continue   # empty or cut first line
        if isinstance(r, dict) and r.get("src") in ("review", "mark"):
            best = max(best, _tnum(r.get("at")))
    if len(_SEC_LOG_CACHE) >= 32:
        _SEC_LOG_CACHE.clear()
    _SEC_LOG_CACHE[fp] = (sig, best)
    return best


def _final_at(pl, root):
    """Result time that ends a run of pl (arch-map: the gate's verify.json · arch-brief: brief.ok.json · security-checks: a review-stage record)."""
    return _sec_final_at(root) if pl == SEC_PL else _result_at(root, BRIEF_OK if pl == BRIEF_PL else "verify.json")


def result_at(pl, root):
    """Result time a request record of pl compares with its send time (sidereus/pl_reqs.py)."""
    return _final_at(pl, root)


def _pending_at(root):
    """mtime of the newest plan.json under root's store with no newer verify.json (a run past stage 1), 0 if none."""
    rdir, best = os.path.join(ARCH_DIR, repo_key(root)), 0.0
    try:
        names = os.listdir(rdir)
    except OSError:
        return 0.0
    for c in names:
        if not COMMIT_RE.fullmatch(c):
            continue
        try:
            p = os.path.getmtime(os.path.join(rdir, c, "plan.json"))
        except OSError:
            continue
        try:
            v = os.path.getmtime(os.path.join(rdir, c, "verify.json"))
        except OSError:
            v = 0.0
        if p > v and p > best:
            best = p
    return best


def _result_at(root, name="verify.json"):
    """mtime of the newest gate result file `name` under root's store, 0 if none."""
    rdir, best = os.path.join(ARCH_DIR, repo_key(root)), 0.0
    try:
        names = os.listdir(rdir)
    except OSError:
        return 0.0
    for c in names:
        if COMMIT_RE.fullmatch(c):
            f = os.path.join(rdir, c, name)
            if os.path.isfile(f):   # most commit dirs have no gate result yet; a vanished file just counts as none
                try:
                    best = max(best, os.path.getmtime(f))
                except OSError:
                    continue
    return best


def _tnum(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def _closed_by_result(r, root, pl=ARCH_PL):
    """True when an open plrun r of pl has a gate result for root newer than every sign of the run
    (run/stage t0 · t1 · p0, t1 of a running agent only; a live agent or main marker carries t1 = now, so it stays open).
    ⚠Codex may re-emit a stage marker and never send the last stage or [pl-end:]: the record stays end 0 for hours."""
    if not isinstance(r, dict) or r.get("name") != pl or _tnum(r.get("end")) or _tnum(r.get("stop")):
        return False
    st = r.get("stages") if isinstance(r.get("stages"), dict) else {}
    signs = [_tnum(r.get("t0")), _tnum(r.get("t1"))]
    for s in st.values():
        if isinstance(s, dict):
            signs += [_tnum(s.get(k)) for k in ("t0", "t1", "p0")]
            # ⚠A finished agent's t0 and t1 are both stamped when its end is seen (12 s after verify.json): skip it, stage t0 covers dispatch.
            signs += [_tnum(a.get("t1")) for a in s.get("ag") or () if isinstance(a, dict) and a.get("run") is True]
    v = max(_end_at(pl, root, r.get("cur"), _late_titles()), result_at(pl, root)) if pl == ARCH_PL else result_at(pl, root)   # ⚠verify.json still closes a run stopped at the map gate; overview signs postdate it
    return bool(v) and v > max(signs)


def _finished(p, s, sg, pt, old, pl=ARCH_PL, late=frozenset()):
    """True when p's run already has its result: a final result newer than any sign of this run started, and either the
    run record closed after it or no tagged subagent / Agent call is still live in the session."""
    v, tag = _end_at(pl, p, sg[0], late), _TAGS[pl]
    if not v or pt > v or sg[1] > v or (old and old["t0"] > v):
        return False
    for r in s.get("plrun") or ():
        e = r.get("end") if isinstance(r, dict) and r.get("name") == pl else None
        if isinstance(e, (int, float)) and not isinstance(e, bool) and e >= v:
            return True
    subs = any(isinstance(x, dict) and isinstance(x.get("lab"), str) and tag.search(x["lab"]) for x in s.get("sub") or ())
    targ = s.get("tool") in ("Agent", "Task") and isinstance(s.get("targ"), str) and tag.search(s["targ"])
    return not (subs or targ)


def _ended_run(s, pl, t0):
    """True when the session's plrun of pl closed at/after t0 (the run is over, not in a stage gap)."""
    for r in s.get("plrun") or () if isinstance(s, dict) else ():
        if isinstance(r, dict) and r.get("name") == pl and max(_tnum(r.get("end")), _tnum(r.get("stop"))) >= t0 > 0:
            return True
    return False


def _sign(s, now, pl=ARCH_PL):
    """(stage title, start time | 0) of a live stage of pl in one session row, None if none.
    Sources: open plrun run · live subagent label · main's [pl:] marker · the Agent call in flight (targ)."""
    tag = _TAGS[pl]
    for r in s.get("plrun") or ():
        if isinstance(r, dict) and r.get("name") == pl and not r.get("end") and isinstance(r.get("cur"), str) and r["cur"]:
            # ⚠An open run is kept by the hook for hours: count it only while the session works or the run moved recently.
            t1 = r.get("t1") if isinstance(r.get("t1"), (int, float)) and not isinstance(r.get("t1"), bool) else 0
            if now - t1 <= (ARCH_BUSY_S if s.get("state") in ("think", "tool") else ARCH_RUN_GAP_S):
                return r["cur"], float(r.get("t0") or 0)
    for x in s.get("sub") or ():
        m = tag.search(x.get("lab") or "") if isinstance(x, dict) and isinstance(x.get("lab"), str) else None
        if m:
            mn = x.get("min")
            return m.group(1), (now - 60 * mn if isinstance(mn, int) and not isinstance(mn, bool) and mn >= 0 else 0.0)
    plm = s.get("plm")
    if isinstance(plm, dict) and plm.get("name") == pl and isinstance(plm.get("title"), str) and plm["title"]:
        # ⚠No arch-map plrun (Codex / hookless): with start 0 any older verify.json ended the run; the marker's own time
        #   (now - age, the stage start for shell markers) is the only start reachable here. A hooked run keeps 0.
        age = plm.get("age")
        hookless = not any(isinstance(r, dict) and r.get("name") == pl for r in s.get("plrun") or ())
        ok = hookless and isinstance(age, int) and not isinstance(age, bool) and age >= 0
        return plm["title"], (float(now - age) if ok else 0.0)
    m = tag.search(s.get("targ") or "") if s.get("tool") in ("Agent", "Task") and isinstance(s.get("targ"), str) else None
    return (m.group(1), 0.0) if m else None


PLAN_MAX = 1_000_000   # bytes of a store plan.json read to find its repo


def _store_repo(c):
    """c, or for a path inside the arch store (`<ARCH_DIR>/<key>/<commit>/…`) the repo its plan.json records, "" if unknown.
    ⚠Stages run with cwd in the store dir: keyed as-is, the run showed the commit hash instead of the repo."""
    store = os.path.realpath(ARCH_DIR)
    rc = os.path.realpath(c)
    if rc != store and not rc.startswith(store + os.sep):
        return c
    parts = os.path.relpath(rc, store).split(os.sep)
    if len(parts) < 2 or not COMMIT_RE.fullmatch(parts[1]):
        return ""
    fp = os.path.join(store, parts[0], parts[1], "plan.json")
    try:
        if os.path.getsize(fp) > PLAN_MAX:
            return ""
        repo = read_json(fp).get("repo")
    except (OSError, ValueError, AttributeError):
        return ""
    if not (isinstance(repo, str) and os.path.isabs(repo) and os.path.isdir(repo)):
        return ""
    repo = os.path.realpath(repo)
    return repo if repo_key(repo) == parts[0] and not repo.startswith(store + os.sep) else ""


def _target(s, now, pl=ARCH_PL):
    """Project a run of pl works on: the candidate (requested repo + cwd + repos) with a pending arch-map store dir, else the first candidate
    that is not the Sidereus repo (the pipeline's home, not the target), else ""."""
    cands = []
    # ★A requested target only subagents touched is missing from repos (main-thread inputs): the run stuck on cwd, 15+ min.
    req = AM._REQ_SRC(str(s.get("sid") or ""), pl, now) if AM._REQ_SRC else ""
    req = _store_repo(req) if isinstance(req, str) and req and os.path.isabs(req) else ""
    for c in [req, s.get("cwd")] + list(s.get("repos") or ()):
        if isinstance(c, str) and c and os.path.isabs(c):
            c = _store_repo(c)
            if c and c not in cands:
                cands.append(c)
    pend = [(t, c) for c, t in ((c, _pending_at(c) if pl == ARCH_PL else 0.0) for c in cands) if t and now - t <= ARCH_PEND_S]
    if pend:
        return max(pend)[1], max(pend)[0]
    # ⚠The home exclusion below is for cwd/repos guesses only: applied to an explicit request for the Sidereus repo, it moved the run onto another repo.
    if req:
        return req, 0.0
    # Stage 1 writes no plan.json yet: a Sidereus-cwd session still names its target in repos (reload keeps «Analysing»).
    other = [c for c in cands if os.path.realpath(c) != AM.SIDEREUS_ROOT]
    if not other and pl != ARCH_PL and cands:   # a security check of the Sidereus repo itself: home is the target
        return cands[0], 0.0
    return (other[0], 0.0) if other else ("", 0.0)


def _record_prov(p, old, row):
    """Provenance of a tracked run that just ended: the session last seen on the run (_RUN_SEEN sid) drew/verified it."""
    try:
        c = _newest(os.path.join(ARCH_DIR, repo_key(p)))
        vt = _mtime(os.path.join(ARCH_DIR, repo_key(p), c, "verify.json")) if c else 0.0
        if vt > old["t0"]:
            arch_prov.record(p, c, vt, row, old["t0"])
    except (OSError, ValueError, TypeError, KeyError):
        return   # provenance is best-effort (shown as unknown); a run's end must not fail on it


def seen_runs():
    """{project: {sid}} of the last runs() result (= state `archRun` keys) without recomputing; for GET /api/pipelines."""
    return {p: {"sid": v.get("sid") or ""} for p, v in list(_RUN_SEEN.items()) if isinstance(v, dict)}


def sec_runs(sessions, now=None):
    """`/api/state` `secRun`: runs() for security-checks (same shape; ends on a review/mark log record)."""
    return runs(sessions, now, SEC_PL)


def brief_runs(sessions, now=None):
    """`/api/state` `briefRun`: runs() for arch-brief (same shape; ends on brief.ok.json)."""
    return runs(sessions, now, BRIEF_PL)


def runs(sessions, now=None, pl=ARCH_PL):
    """`/api/state` `archRun`: {project path: {stage, n, of, t0, sid}} for runs of pl in progress, from session rows.
    ⚠Metadata only — stage title, times, session id. The pipeline hook keeps no run for a session whose cwd has its own
    pipelines (arch-map lives in the Sidereus repo), so the row's live [pl:arch-map/…] tags are the source, not plrun alone."""
    now = time.time() if now is None else now
    seen, ended, fin, mem = {}, set(), [], {ARCH_PL: _RUN_SEEN, SEC_PL: _SEC_SEEN}.get(pl, _BRIEF_SEEN)
    rows, late = {}, _late_titles() if pl == ARCH_PL else frozenset()
    for s in sessions or ():
        if not isinstance(s, dict) or s.get("state") in ("done", "gone"):
            continue
        rows[str(s.get("sid") or "")] = s
        sg = _sign(s, now, pl)
        if not sg:
            continue
        p, pt = _target(s, now, pl)
        if not p:
            continue
        old = mem.get(p)
        # ⚠A busy orchestrator keeps signs alive long after the gate passed: once the result exists the run is over.
        if _finished(p, s, sg, pt, old, pl, late):
            ended.add(p)
            if old and pl == ARCH_PL:
                fin.append((p, old, s))
            continue
        t0s = [t for t in (sg[1], pt, old and old["t0"]) if t]
        seen[p] = {"stage": sg[0][:80], "sid": str(s.get("sid") or "")[:64], "t0": min(t0s) if t0s else now, "at": now}
    alive = {str(s.get("sid") or "") for s in sessions or () if isinstance(s, dict) and s.get("state") not in ("done", "gone")}
    # ⚠One session = one run: stage 1 guesses the target (no plan.json yet), so when plan.json names another repo the
    #   guessed key must not be carried beside the real one (one run showed on two projects).
    live = {v["sid"] for v in seen.values()}
    for p, v in list(mem.items()):   # ⚠a stage gap keeps the run only while its session lives; past the gap it is over
        if p not in seen and p not in ended and v["sid"] in alive and v["sid"] not in live and now - v["at"] <= ARCH_RUN_GAP_S \
                and _end_at(pl, p, v["stage"], late) < v["t0"] and not _ended_run(rows.get(v["sid"]), pl, v["t0"]):
            seen[p] = v
        elif p not in seen and p not in ended and pl == ARCH_PL and _final_at(pl, p) >= v["t0"]:
            # ⚠Usual end: verify.json written, verify agent ends, plrun closes, marker clears -> no sign, _finished never runs.
            fin.append((p, v, None))
    mem.clear()
    mem.update(seen)
    every = {str(s.get("sid") or ""): s for s in sessions or () if isinstance(s, dict)}   # a just-ended row is «done»
    for p, old, s in fin:
        _record_prov(p, old, rows.get(old["sid"]) or every.get(old["sid"]) or s or {"sid": old["sid"]})
    titles = _pl_titles(pl)
    return {p: {"stage": v["stage"], "n": titles.index(v["stage"]) + 1 if v["stage"] in titles else 0, "of": len(titles),
                "t0": v["t0"], "sid": v["sid"]} for p, v in seen.items()}
