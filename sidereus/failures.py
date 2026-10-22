"""Failure catalog and unfinished wreckage."""
import os
import time
from sidereus.warn import warn_once
from sidereus import boot_queue
from sidereus.bus import _load, _save_json
from sidereus.memo import BoundedMemo
from sidereus.transcript import _iso_ts
from sidereus.ident import _sid8
from sidereus.gitinfo import DIFF_TIMEOUT, _git_run
from sidereus.steps import _open_or_tail, _work_scan
from sidereus.cards import _WRECK_BY_CWD, _card_add
# ⚠Split 2026-09-24: the scan (grading, signatures, _fail_read/_fail_events, _FAIL_EV/_FAIL_LOCK) lives in
#   failures_scan and owns that state. Re-exported here for retro/attention/chat_server; patch scan internals there.
from sidereus.failures_scan import (
    FAIL_HOURS, FAIL_SEEN_H, _FAIL_EV, _FAIL_LOCK, _fail_events, _fail_read, _fail_transcripts
)


# ── Failure catalog · unfinished wreckage ───────────────────────────────────
WRECK_MAX_AGENTS = 40       # cap on agents searched for wreckage
WRECK_TAIL = 4000           # tail lines read from an agent log
_WRECK_CACHE = BoundedMemo(300)   # (agent log, cwd) -> (mtime, [{cwd,path}])
_DIRTY_CACHE = {}           # repo -> (lookup time, {relative path: status})


FAIL_1H_SPAN = 3600         # header card window (s)
FAIL_1H_BINS = 6            # 10-min buckets
_FAIL_1H = {}               # last summary; ⚠rebound only by _fail_1h_build (the loop), read by fail1h() in state()


def _fail_1h_fold(evs, now, span=FAIL_1H_SPAN, nb=FAIL_1H_BINS):
    """Pure fold: events -> counts by kind plus `nb` equal buckets over the last `span` s (oldest first)."""
    step = span // nb
    kinds, bins, bk, last = {}, [0] * nb, [{} for _ in range(nb)], []
    for ev in evs:
        age = max(0.0, now - (ev.get("at") or 0))
        if age >= span:
            continue
        k = ev.get("kind") or "?"
        i = nb - 1 - int(age // step)
        kinds[k] = kinds.get(k, 0) + 1
        bins[i] += 1
        bk[i][k] = bk[i].get(k, 0) + 1
        # ⚠Metadata only (time · kind · project · session id) — no error text/signature reaches the page.
        last.append({"at": int(ev.get("at") or 0), "kind": k, "proj": ev.get("proj") or "", "sid": ev.get("sid") or ""})
    last.sort(key=lambda q: -q["at"])
    return {"at": int(now), "n": sum(bins), "step": step, "kinds": kinds, "bins": bins, "bk": bk, "last": last[:8]}


def _fail_1h_build():
    """Rebuild the cached last-hour summary from `_fail_events` (offsets already advanced by the loop)."""
    global _FAIL_1H
    evs, _n, _h = _fail_events(FAIL_1H_SPAN / 3600.0)
    _FAIL_1H = _fail_1h_fold(evs, time.time())


def fail1h():
    """Cached last-hour failure summary for state() — no scan here; {} until the loop's first pass."""
    return _FAIL_1H


def _fail_loop():
    """Advance read offsets in the background — so opening the tab does not read 1GB on the spot."""
    while True:
        try:
            # ★Pre-scan subagent logs too (2026-09-07) — otherwise opening the tab triggers a cold scan on the spot.
            #   Measured: the subagent share is 38 files in 24 h, 0.04 s — nearly free.
            with boot_queue.gate("fail_loop"):   # ⚠first pass waits its boot turn; no-op after drain (traps/server.md)
                files = _fail_transcripts(time.time(), 48)
                # ★Called without the lock (2026-09-07) — `_fail_read` takes its own lock briefly.
                #   This loop used to hold the lock across all 40 files (cold 2.81 s), during which request threads'
                #   failure tab could read **not one file**. Now they alternate per file.
                for _mt, fp in files:
                    _fail_read(fp)
                _fail_1h_build()       # header «Failures (1h)» card — built here so state() only reads the cache
                _wreck_snapshot()      # ★outside the lock — _fail_events takes the same lock (calling inside would hang)
                _wreck_cards(_wreck_by_cwd())   # session row "leftover" badge + wreckage alerts — computed only here
                _fail_cards()          # put new failures on the bell
        except Exception as e:
            warn_once("loop:fail", "Failure tab refresh failed ({err}) — the failure list may be stale",
                      vars={"err": type(e).__name__})
        time.sleep(60)


_PUB_SIG = {"tool": "도구 오류", "hook": "훅이 막음"}


def _pub_sig(ev):
    """Signature safe to send. ⚠tool/hook `sig` is built from raw tool output — replaced by a fixed label + tool name
    (2026-09-25 user: enforce AGENTS.md rule 1 on /api/failures). Other kinds' sigs are fixed templates already."""
    lab = _PUB_SIG.get(ev.get("kind"))
    if not lab:
        return ev["sig"]
    return lab + (" — " + ev["tool"] if ev.get("tool") else "")


def failures(hours=FAIL_HOURS):
    """**What breaks repeatedly** — failures grouped and counted by signature.

    ★Why group: individual failures already scrolled past in the terminal. What has value is "how many times this cause".
      Knowing whether 529 is 40% or watchdog stalls 50% is what separates own fault from infrastructure.
    ⚠Metadata only: no raw error text or tool input leaves here (samples carry time · project · ids · tool name)."""
    now = time.time()
    evs, nfile, hrs = _fail_events(hours)
    g = {}
    for ev in evs:
        sig = _pub_sig(ev)
        r = g.get(sig)
        if not r:
            r = g[sig] = {"sig": sig, "kind": ev["kind"],
                                "grade": ev.get("grade") or "check",
                                "why": ev.get("why") or "", "n": 0,
                                "first": ev["at"], "last": ev["at"],
                                "projs": {}, "types": {}, "samples": []}
        r["n"] += 1
        r["first"] = min(r["first"], ev["at"])
        r["last"] = max(r["last"], ev["at"])
        if ev.get("proj"):
            r["projs"][ev["proj"]] = r["projs"].get(ev["proj"], 0) + 1
        if ev.get("type"):
            r["types"][ev["type"]] = r["types"].get(ev["type"], 0) + 1
        # ★`aid`·`sess` are sent too (2026-09-07) — saying "which agent, doing what" on screen needs identity.
        #   No conversation content: the raw `text` was dropped 2026-09-25 (rule 1).
        smp = {"at": ev["at"], "tool": ev.get("tool", ""),
               "proj": ev.get("proj", ""), "type": ev.get("type", ""),
               "desc": ev.get("adesc", ""), "aid": ev.get("aid", ""),
               "sess": _sid8(ev.get("sess"))}
        if len(r["samples"]) < 6:
            r["samples"].append(smp)
        elif ev.get("aid") and not any(x.get("aid") for x in r["samples"]):
            # ★One slot is given to **a sample with identity** (2026-09-07). If the first 6 are all main-session,
            #   `types` shows agent names but the expanded list has no identity at all —
            #   measured: a hook-block row of 6 had types={general-purpose:3,...} but all 6 samples were main-session.
            r["samples"][-1] = smp
    kinds, grades = {}, {}
    for ev in evs:
        kinds[ev["kind"]] = kinds.get(ev["kind"], 0) + 1
        gr = ev.get("grade") or "check"
        grades[gr] = grades.get(gr, 0) + 1
    # sort by grade first — things to look at (check) on top, my own (mine) at the bottom
    _ord = {"check": 0, "cut": 1, "mine": 2, "noise": 3}
    rows = sorted(g.values(), key=lambda x: (_ord.get(x.get("grade"), 3), -x["n"], -x["last"]))
    return {"ok": True, "at": int(now), "hours": hrs, "total": len(evs),
            "kinds": kinds, "grades": grades, "scanned": nfile, "rows": rows[:80]}


def _dirty_map(repo, ttl=20):
    """Set of **uncommitted files** in the repo. Empty if not git or slow (no guessing)."""
    if not repo or not os.path.isdir(repo):
        return {}
    hit = _DIRTY_CACHE.get(repo)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    out = {}
    try:
        r = _git_run(repo, ["status", "--porcelain", "-uall"], DIFF_TIMEOUT)
        for ln in r.stdout.splitlines():
            if len(ln) > 3:
                p = ln[3:].strip().strip('"')
                if " -> " in p:                 # renamed — take the new name
                    p = p.split(" -> ", 1)[1].strip().strip('"')
                out[p] = ln[:2].strip() or "M"
    except Exception:
        out = {}
    _DIRTY_CACHE[repo] = (time.time(), out)
    return out


WRECK_TAIL_STEPS = 6       # number of **last footprints** shown on screen


def _agent_trace(afile, cwd=""):
    """Files the agent touched + **footprints right before it stopped**. Cached by (path, mtime).

    ★Why footprints too (2026-09-02; needed to see what it was doing and how it stopped):
      a file list alone does not show "doing what". The last few tool calls are the answer,
      and the same file is already being read, so no extra cost.
    ★Paths **outside** the repo (absolute, `..`) are dropped — they cannot be checked against git status, and
      showing uncheckable ones makes "unknown" read as "still there" (measured 2026-09-02: scratch files in
      /private/tmp showed up posing as repo files)."""
    key = (afile, cwd)
    empty = {"files": [], "steps": [], "nstep": 0, "ran": 0}
    try:
        mt = os.path.getmtime(afile)
    except OSError:
        return empty
    hit = _WRECK_CACHE.get(key, stamp=mt)
    if hit is not None:
        return hit
    files, seen = [], set()
    sc, err = _work_scan(_open_or_tail(afile, tail=WRECK_TAIL), cwd)
    if err or not sc:
        return _WRECK_CACHE.put(key, empty, stamp=mt)
    steps_all = sc[0]
    for st in steps_all:
        for w in (st.get("wrote") or []):
            repo, p = (w.get("cwd") or ""), (w.get("path") or "")
            if not repo or not p or p.startswith("/") or p.startswith(".."):
                continue
            if (repo, p) in seen:
                continue
            seen.add((repo, p))
            files.append({"cwd": repo, "path": p})
            if len(files) >= 40:
                break
    tail = []
    for st in steps_all[-WRECK_TAIL_STEPS:]:
        r = st.get("res") or {}
        # ⚠No `arg`/`targ` — that is the tool input (Bash command etc.); /api/wreckage sends tool names only (rule 1, 2026-09-25).
        tail.append({"tool": st.get("tool") or "?",
                     "t": (st.get("t") or "")[11:16],
                     # if the last footprint **has no result**, it was cut off there — that is "where it stopped"
                     "res": bool(st.get("id") is None or r)})
    ran = 0
    try:
        a, b = sc[4], sc[5]
        if a and b:
            ran = int(max(0, _iso_ts(b) - _iso_ts(a)))
    except Exception:
        ran = 0
    out = {"files": files, "steps": tail, "nstep": len(steps_all), "ran": ran}
    return _WRECK_CACHE.put(key, out, stamp=mt)


def _agent_wrote(afile, cwd=""):
    """Touched files only — used by the snapshot path (footprints not needed)."""
    return _agent_trace(afile, cwd)["files"]


# ★Wreckage is **a perishable fact** (2026-09-02; unfinished wreckage rarely showed up).
#   Asking git now loses everything committed meanwhile — measured: repo-A's uncommitted set was
#   1 tracked file (the other 429 untracked, like screenshots), repo-B 4. This user commits right away,
#   so looking later always gives 0. Hence **snapshot the state at the moment the failure is first seen.**
#   ⚠Agent logs flush later than the completion notice (measured 283 s) — so re-snapshot for 10 min,
#     then freeze. If the server comes up late and first sees an old failure, record **"state at the time unknown"**
#     (writing today's value as if it were then's, without knowing then, is the worst outcome).
WRECK_SNAP = "wreck-snap.json"
WRECK_FRESH_S = 900        # a failure older than this when first seen gets "state at the time unknown"
WRECK_FREEZE_S = 600       # freeze the snapshot this long after the failure (before that, re-snapshot while awaiting flush)
_WSNAP = {}


def _wsnap_load():
    got = _load(WRECK_SNAP, {})
    if isinstance(got, dict):
        _WSNAP.update(got)


# ★A **dict**, not a set (key -> time the card was made). Because of the cap — the old code, past 3000,
#   **emptied it wholesale** with `_FAIL_CARDED.clear()`. Failures still inside the observation window
#   (`_fail_events(6)`, 6 h) then reverted to "first seen" and **the same failure cards reappeared** (immediately, 2.5 s poll).
#   Measured 2026-09-07: 46 failures in 24 h (hook 32 · tool 13 · monitor 1) — only FAIL_CARD_KINDS (agent·bg)
#   get cards, so filling 3000 keys takes weeks. A latent defect, but the moment it fills the result is
#   "a duplicate-card bomb", so evict only the oldest half.
#   ⇒ Same shape as `_bg_popped`'s eviction, but ordered by **time** rather than dict insertion order.
_FAIL_CARDED = {}             # failures already announced (tid) — one card however many notices arrive
# ★Seeding state is **held separately.** Judging by an empty set meant that if the first scan found no failure
#   in the window, seeding never ended and **the first real failure was swallowed** (measured 2026-09-02, caught by a test).
_FAIL_SEEDED = [False]
FAIL_CARD_KINDS = ("agent", "bg")     # tool errors, hooks, permission denials and my own stops are not announced


# ★Failures are alerts, not a tab (the old tab was a list with no
#   response manual). Each alert kind carries **one response line** and the harness basis phrase (`why`).
#   ⚠Card fields are metadata only: ids, harness phrases, counts, reset time — never conversation text.
FAIL_ALERT_TITLE = {"flimit": "Stopped by limit", "fcut": "Cut by external cause",
                    "fcheck": "Cause needs a look", "fwreck": "Half-edited files"}
_LIMIT_WIN = (("hit your weekly limit", "7d"), ("hit your session limit", "5h"),
              ("hit your 5-hour limit", "5h"))


def _reset_hhmm(win):
    """Local HH:MM of the quota reset for window '5h' | '7d' (weekly adds MM/DD). '' when unknown."""
    try:
        from sidereus.quota import quota     # ⚠lazy: quota sits above failures in the STAGE3 layer order
        q = quota() or {}
        t = _iso_ts((q.get("seven_day" if win == "7d" else "five_hour") or {}).get("resets_at"))
    except Exception:
        t = 0
    if not t:
        return ""
    return time.strftime("%m/%d %H:%M" if win == "7d" else "%H:%M", time.localtime(t))


def _fail_alert(ev):
    """(card kind, extra fields, Korean response line) for one failure event; kind '' = no alert (mine/noise)."""
    g, why, txt = ev.get("grade") or "check", ev.get("why") or "", ev.get("text") or ""
    label = ev.get("type") or ("백그라운드 작업" if ev.get("kind") == "bg" else "서브에이전트")
    extra = {"tid": ev.get("tid") or "", "sid": ev.get("sid") or "", "why": why,
             "sig": ev.get("sig") or "", "label": label, "grade": g, "ekind": ev.get("kind") or ""}
    if g == "cut":
        win = next((w for ph, w in _LIMIT_WIN if ph in txt or ph == why), "")
        if win:
            rs = _reset_hhmm(win)
            extra.update({"win": win, "reset": rs})
            return "flimit", extra, ("Stopped by the usage limit — rerun after the %s reset at %s" % (win, rs) if rs
                                     else "Stopped by the usage limit — rerun after the %s reset" % win)
        return "fcut", extra, "Cut off by an external cause — rerun the same instruction"
    if g == "check":
        return "fcheck", extra, "Cause could not be read — check where it stopped"
    return "", extra, ""


_WRECK_CARDED = {}            # wreckage tid -> time its card was made
_WRECK_SEEDED = [False]       # same seeding rule as `_FAIL_SEEDED` — no flood of old wreckage on server start
_WRECK_AT = {}                # cwd -> newest dirty wreckage time (epoch); attention clears `wreck` once the session moved past it


def _wreck_cards(rows):
    """One `fwreck` card per wreckage item that still has uncommitted files (fed by `_fail_loop`)."""
    seeding = not _WRECK_SEEDED[0]
    _WRECK_SEEDED[0] = True
    for r in rows or []:
        tid = r.get("tid") or ""
        if not tid or not r.get("dirty") or tid in _WRECK_CARDED:
            continue
        _WRECK_CARDED[tid] = time.time()
        if seeding:
            continue
        n = int(r.get("dirty") or 0)
        _card_add("fwreck", r.get("proj") or "", FAIL_ALERT_TITLE["fwreck"],
                  "Cut off midway, %d half-edited files left — revert or have it continue" % n,
                  r.get("cwd") or "",
                  {"tid": tid, "n": n, "sig": r.get("sig") or "", "label": r.get("type") or "서브에이전트",
                   "ekind": "agent",
                   "why": "Files left uncommitted — per git status (a hint, not proof)"})
    if len(_WRECK_CARDED) > 3000:
        for k in sorted(_WRECK_CARDED, key=lambda x: _WRECK_CARDED.get(x, 0))[:1500]:
            _WRECK_CARDED.pop(k, None)


def _fail_cards():
    """Record new failures as **alarm cards** (2026-09-02: unseen unless the tab is open).

    ★Only selected kinds — 30-day measurement: tool errors 315 · hooks 332 · permission denials 74.
      Announcing all would make the bell meaningless. Only **dead** agents and background jobs count.
    ★None during seeding — old failures must not flood in when the server first starts."""
    seeding = not _FAIL_SEEDED[0]
    try:
        evs, _n, _h = _fail_events(6)
    except Exception as e:
        warn_once("fail-cards", "failure scan failed ({err}) — no failure alarm cards",
                  vars={"err": f"{type(e).__name__}: {e}"}, soft=True)
        return
    _FAIL_SEEDED[0] = True
    for ev in evs:
        if ev.get("kind") not in FAIL_CARD_KINDS:
            continue
        kind, extra, line = _fail_alert(ev)
        if not kind:
            continue                      # mine / noise: counted by /api/failures only, no alert
        # ★One card per signature per agent (tid) or session (sid) — repeated notices of the same death stay one card.
        key = "%s|%s|%s" % (kind, ev.get("sig") or "", ev.get("tid") or ev.get("sid") or ev.get("at"))
        if key in _FAIL_CARDED:
            continue
        _FAIL_CARDED[key] = time.time()   # the value is the eviction key (time the card was made)
        if seeding:
            continue
        _card_add(kind, ev.get("proj") or "", FAIL_ALERT_TITLE.get(kind, "Failures"), line,
                  ev.get("cwd") or "", extra)
    if len(_FAIL_CARDED) > 3000:
        # ★Evict **only the oldest half** — `clear()` reverted even failures inside the observation window (6 h) to
        #   "first seen" and re-raised the same cards. Keys evicted here are long past the 6 h window and will never
        #   be observed again (`_fail_events` does not return out-of-window failures at all).
        for k in sorted(_FAIL_CARDED, key=lambda x: _FAIL_CARDED.get(x, 0))[:1500]:
            _FAIL_CARDED.pop(k, None)


def _wreck_snapshot():
    """Snapshot what a just-failed agent left uncommitted **at that moment**."""
    now = time.time()
    try:
        evs, _n, _h = _fail_events(24)
    except Exception as e:
        warn_once("wreck-events", "failure scan failed ({err}) — no wreck snapshots",
                  vars={"err": f"{type(e).__name__}: {e}"}, soft=True)
        return
    changed = False
    for ev in evs:
        tid = ev.get("tid") or ""
        if ev.get("kind") != "agent" or not tid or not ev.get("afile"):
            continue
        old = _WSNAP.get(tid)
        if old and old.get("frozen"):
            continue
        if now - ev["at"] > WRECK_FRESH_S:
            if not old:                      # first seen but already old — no way to know the state then
                _WSNAP[tid] = {"at": ev["at"], "known": False, "frozen": True,
                               "dirty": 0, "files": []}
                changed = True
            continue
        files = _agent_wrote(ev["afile"], ev.get("cwd") or "")
        snap = []
        for f in files:
            st = _dirty_map(f["cwd"], ttl=5).get(f["path"], "")
            if st:
                snap.append({"cwd": f["cwd"], "path": f["path"], "st": st,
                             "repo": os.path.basename(f["cwd"])})
        _WSNAP[tid] = {"at": ev["at"], "known": True, "taken": int(now),
                       "frozen": (now - ev["at"]) > WRECK_FREEZE_S,
                       "dirty": len(snap), "nfile": len(files), "files": snap[:40]}
        changed = True
    cut = now - FAIL_SEEN_H * 3600
    for k in [k for k, v in _WSNAP.items() if (v.get("at") or 0) < cut]:
        _WSNAP.pop(k, None)
        changed = True
    if changed:
        try:
            _save_json(WRECK_SNAP, _WSNAP)
        except Exception as e:
            warn_once("wreck-snap", "wreck snapshot save failed ({err}) — lost on restart",
                      vars={"err": f"{type(e).__name__}: {e}"}, soft=True)


# ⚠Read-only since 2026-09-24 (the dismiss/send POST routes that wrote it were removed). The live file still
#   holds 7 tids, so the filter in wreckage() stays until a human decides those may reappear.
WRECK_DROP = "wreck-dismissed.json"
_WDROP = set()


def _wdrop_load():
    got = _load(WRECK_DROP, [])
    if isinstance(got, list):
        _WDROP.update(str(x) for x in got if x)


def wreckage(hours=FAIL_HOURS):
    """**Left half-edited on death** — are files touched by failed or stopped agents still uncommitted?

    ⚠A **clue**, not proof. Uncommitted is not the same as that agent's fault —
      the user may have left it on purpose, or a later agent may already have continued the fix.
      So it only says "left", never "broken"."""
    now = time.time()
    evs, nfile, hrs = _fail_events(hours)
    # ★`stop` (I stopped it) is included — not a failure, but **cut off midway**, so files may remain.
    #   Grade and wreckage are different questions: grade is "whose fault", wreckage is "anything to handle now".
    cand = sorted([e for e in evs if e["kind"] in ("agent", "stop") and e.get("afile")
                   and e.get("tid") not in _WDROP],
                  key=lambda x: -x["at"])[:WRECK_MAX_AGENTS]
    rows = []
    for ev in cand:
        tr = _agent_trace(ev["afile"], ev.get("cwd") or "")
        files = tr["files"]
        if not files:
            continue
        out, nd, unk = [], 0, 0
        for f in files:
            stt = _dirty_map(f["cwd"]).get(f["path"], "")
            if not stt and not os.path.exists(os.path.join(f["cwd"], f["path"])):
                # ★**A path not in that repo** — mis-picked from the command line (without knowing the cd, relative
                #   paths get attached to the root). Listing it as clean reads as "verified" — only count it.
                unk += 1
                continue
            if stt:
                nd += 1
            out.append({"cwd": f["cwd"], "path": f["path"], "st": stt,
                        "repo": os.path.basename(f["cwd"])})
        if not out:
            continue
        out.sort(key=lambda x: (not x["st"], x["path"]))
        sn = _WSNAP.get(ev["tid"]) or {}
        rows.append({"then": (sn.get("dirty") if sn.get("known") else None),
                     "thenFiles": (sn.get("files") or [])[:14] if sn.get("known") else [],
                     "tid": ev["tid"], "at": ev["at"], "ago": int(now - ev["at"]),
                     "sig": ev["sig"], "type": ev.get("type") or "agent",
                     "desc": ev.get("adesc") or "", "proj": ev.get("proj") or "",
                     "cwd": ev.get("cwd") or "",
                     "steps": tr["steps"], "nstep": tr["nstep"], "ran": tr["ran"],
                     "files": out, "nfile": len(out), "dirty": nd, "unk": unk})
    rows.sort(key=lambda x: (-x["dirty"], -(x["then"] or 0), -x["at"]))
    return {"ok": True, "at": int(now), "hours": hrs, "scanned": nfile,
            "checked": len(cand), "left": sum(1 for r in rows if r["dirty"]),
            "was": sum(1 for r in rows if (r.get("then") or 0) > 0),
            "unknown": sum(1 for r in rows if r.get("then") is None),
            "rows": rows[:60]}


def _wreck_by_cwd():
    """`_fail_loop` only — fold wreckage by session cwd. On failure keep the old value (never wipe to 0)."""
    got, at = {}, {}
    rows = wreckage(FAIL_HOURS).get("rows", [])
    for r in rows:
        d = r.get("dirty") or 0
        c = r.get("cwd") or ""
        if d and c:
            got[c] = got.get(c, 0) + d
            at[c] = max(at.get(c, 0), r.get("at") or 0)
    _WRECK_BY_CWD.update(got)   # update then prune: clear() first let a poll see an empty map (badge off for a cycle)
    for c in [k for k in list(_WRECK_BY_CWD) if k not in got]:
        _WRECK_BY_CWD.pop(c, None)
    _WRECK_AT.update(at)
    for c in [k for k in list(_WRECK_AT) if k not in at]:
        _WRECK_AT.pop(c, None)
    return rows
