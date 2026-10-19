"""Timeline assembly: transcript pick, token events, session/agent rows, agents_timeline.
Scanning (segments, compactions, token lines, sleep/idle) lives in `sidereus/timeline_scan.py`; ext CLI rows in `sidereus/timeline_ext.py`."""
import bisect
import os
import threading
import time
from sidereus.warn import warn_once
from sidereus.memo import BoundedMemo
from sidereus import claude_roots
from sidereus.transcript import CLAUDE_PROJECTS, _tail_bytes
from sidereus.ident import _proj_name, _sid8, _slug
from sidereus.agents import _agent_fin, _agent_last, _agent_meta, _agent_tools, wf_agent_files, wf_runs
from sidereus.sessions import sessions_cached, sessions_rows
from sidereus.sess_clear import clear_of
from sidereus.timeline_ext import _plat_tl_rows
# ⚠Re-exported for importers (chat_server, burn_usage, usage lazy import) and for the golden test, which patches
#   `_sess_segments`/`_compacts`/`naps` here. Patch scan internals (`_seg_scan`, `_naps_fetch`, ...) on timeline_scan.
from sidereus.timeline_scan import (TL_HOURS, SEG_CAP_BYTES, _SEG_WIN, _fast_ts, _resp_key,
                                 _sess_segments, _sess_waits, _compacts, naps, _naps_awake, _idle_gaps)


# Cap on transcripts read per project — count all, but prevent runaway (measured 2026-09-09: max 4 per
# project in a 12 h window). If this cuts, the project's **oldest** session is dropped.
TL_SESS_MAX = 12
TL_ROW_MAX = 200           # cap on Gantt rows — on overflow **only agents** are cut, oldest first


TOKEV_TTL = 30             # shared-scan cache (s) — same level as QBURN_TTL
_TOKEV = {}
_tokev_lock = threading.Lock()
TL_SNAP_S = 600            # snapshot age accepted by `_tl_pick` — rows only add the «newest 3» fallback, stale is fine


def _tl_snap_rows():
    """`(rows, fresh)` from the poll's snapshot — never a sessions() call.
    ★2026-09-29 after a reboot (every spawn slow, /usr/bin/true 0.6 s): cold /api/quota/burn took 6-20 s because
      `_tok_events` -> `_tl_pick` ran a 40 s cold sessions() in the request thread; hooks calling it (mailbox_stop 5 s,
      invite_notice 10 s) timed out 28x in one session.
    ⚠Never call sessions() from a request or hook path; fall back to the last snapshot, else no rows."""
    return sessions_cached(wait=0.5, max_age=TL_SNAP_S)


def _tl_pick(cut, rows=None):
    """Transcripts with activity since `cut`, grouped per project dir.

    Yields `(cwd, project, [transcript paths], newest path)`. Split out of `agents_timeline`
    (2026-09-23) so `_tok_events` picks the exact same files without a second
    copy of the rules drifting away. ⚠The picking rules below are unchanged."""
    if rows is None:
        rows = _tl_snap_rows()[0]
    dirs, seen_dirs, dinfo = [], set(), {}
    proots = claude_roots.projects_dirs(CLAUDE_PROJECTS)   # every Claude root
    for r in rows:
        cwd = r.get("cwd") or ""
        if not cwd:
            continue
        for pr in proots:
            d = os.path.join(pr, _slug(cwd))
            if d in seen_dirs:
                continue
            seen_dirs.add(d)
            dirs.append(d)
            dinfo[d] = (cwd, r.get("project") or os.path.basename(cwd))
    for pr in proots:
        try:
            for nm in sorted(os.listdir(pr)):
                d = os.path.join(pr, nm)
                if d not in seen_dirs and os.path.isdir(d):
                    seen_dirs.add(d)
                    dirs.append(d)
        except OSError:
            pass                    # no projects dir yet: only the on-screen sessions' dirs
    got = []
    for d in dirs:
        try:
            fs = sorted((os.path.join(d, f) for f in os.listdir(d) if f.endswith(".jsonl")),
                        key=os.path.getmtime, reverse=True)
        except OSError:
            continue                # dir or a file vanished mid-listing
        except Exception as e:      # unexpected: the whole project would drop off the timeline
            warn_once("tl-dir", "Could not list a timeline folder ({err})", vars={"err": type(e).__name__}, soft=True)
            continue
        # ★Picking rule: **everything written in the window** + (for live projects) always the newest 3.
        #   ⚠Why keep the latter — while a subagent runs **the session file is quiet**. Cutting by session file
        #     mtime alone makes running agents vanish entirely on short windows (`hours=0.5`).
        #   ⚠Projects absent from `sessions()` don't get that fallback — no running session, so no need, and
        #     using it would dig through `subagents` of 26 quiet projects every time (measured 31 folders).
        known = d in dinfo
        pick = list(fs[:3]) if known else []
        for p in fs:
            try:
                if p not in pick and os.path.getmtime(p) >= cut:
                    pick.append(p)
            except OSError:
                pass                # transcript deleted since the listing
        if not pick:
            continue
        if not known:                            # project not in sessions() — dig it from the file
            _c = _tx_cwd(pick[0])
            dinfo[d] = (_c, _proj_name(_c) if _c else os.path.basename(d))
        dcwd, dproj = dinfo[d]
        got.append((dcwd, dproj, pick[:TL_SESS_MAX], fs[0]))
    return got


def _tok_events(since_ts):
    """Raw `(ts, tokens)` pairs from every primary-account transcript active since `since_ts`.

    ★Why (2026-09-23): `quota_burn` used to read `agents_timeline()`'s render
      buckets, whose width is `max(30, span/240)` — i.e. the quota denominator
      moved with the screen's resolution. Measured at 4.95h elapsed: 75s buckets,
      the first usable bucket started 48s after reset, so the slice right after
      reset was dropped whole (bucket sum 237,189,564 vs 237,043,400).
    ⚠No bucketing here — `_sess_segments` cuts on `since_ts` itself, so the
      reset boundary is exact. Keep it that way.
    ⚠Same `nb`/`lim` as `agents_timeline` on purpose: `_SEG_RAW` is keyed by
      those, and different values would evict the cache on every other call."""
    now = time.time()
    key = int(since_ts)
    with _tokev_lock:
        hit = _TOKEV.get(key)
        if hit and now - hit[0] < TOKEV_TTL:
            return hit[1]
    cut = float(since_ts)
    ev, seen = [], set()
    rows, fresh = _tl_snap_rows()
    own = {}                                 # sid -> primary? (one record lookup per session per scan)
    for _cwd, _proj, pick, _newest in _tl_pick(cut, rows):
        for fp in pick:
            _sd = fp[:-len(".jsonl")]
            _sid = os.path.basename(_sd)
            if _sid not in own:
                own[_sid] = claude_roots.primary_owned(_sid, fp)
            if not own[_sid]:
                continue                     # ⚠primary sums only: a shared projects dir holds other accounts' sessions
            for f2 in [mm.get("_file") or "" for mm in _agent_meta(_sd, ttl=10).values()] + wf_agent_files(_sd):
                if not f2 or f2 in seen:
                    continue
                try:
                    if os.stat(f2).st_mtime < cut:
                        continue
                except OSError:
                    continue
                seen.add(f2)
                _sess_segments(f2, cut, nb=2_000_000, lim=4000, tok_out=ev)
            if fp in seen:
                continue
            try:
                if os.stat(fp).st_mtime < cut:
                    continue
            except OSError:
                continue
            seen.add(fp)
            _sess_segments(fp, cut, tok_out=ev)
    ev.sort()
    with _tokev_lock:
        if len(_TOKEV) > 8:
            _TOKEV.clear()
        _TOKEV[key] = (now if fresh else now - TOKEV_TTL + 5, ev)   # no fresh snapshot: retry in 5 s
    return ev


def agents_timeline(hours=TL_HOURS):
    """Subagents' **start ~ last activity** spans, drawn as a Gantt chart.

    ★Times are the agent log file's creation/modification times (not estimates). The end is "last written",
      slightly earlier than the real end — nothing more is knowable, so it is named that way.
    ★Running state uses **the same test** as the screen (sessions()' sub list) — the two must never disagree."""
    now = time.time()
    hours = max(0.5, min(168, float(hours)))     # 30 min ~ one week
    cut = now - hours * 3600
    rows = sessions_rows()                       # ⚠request path: snapshot, never a cold sessions()
    pcwd = {}                                    # Claude sid → (cwd, project), for ext CLI runs it launched
    out = _tl_rows(cut, rows, pcwd)
    out = _tl_dedup(out + _plat_tl_rows(cut, now, pcwd))
    out.sort(key=lambda x: (x.get("kind") != "sess", x["start"]))
    return _tl_finish(out, hours, cut, now)


def _tl_live(rows):
    """`(live tids, live agent ids)` from `sessions()` sub lists — the same running test as the screen."""
    live = {}
    live_aid = {}
    for r in rows:
        for it in (r.get("sub") or []):
            if it.get("tid"):
                live[it["tid"]] = True
            # ★**A tool-call id is not identity** (2026-09-09; an active subagent was not recognized on the timeline).
            #   A resumed row's (`SendMessage`) key is a new tool_use id, different from meta's original
            #   `toolUseId` (same trap as ★ in `_meta_of`).
            #   ★Measured: a running agent (idle 1 s) had list tid `toolu_013vHK…`,
            #     timeline row tid `toolu_01FhSz…` ⇒ all 12 rows were `run=False`.
            #   ⇒ Also link by the agent's **own id**. The decision itself is still `sessions()` alone.
            if it.get("aid"):
                live_aid[it["aid"]] = True
    return live, live_aid


def _tl_rows(cut, rows, pcwd=None):
    """Agent and session rows (with private `_tk` token lists) for every picked transcript, in pick order.
    `pcwd`, when given, is filled with sid → (cwd, project) for every transcript seen."""
    live, live_aid = _tl_live(rows)
    out = []
    # ★Iterate per **project directory**, not per session (2026-09-04; one subagent was counted as two).
    #   It used to loop `for r in rows` (live sessions), scanning each session's **whole project directory**.
    #   With 2 sessions open in one project (a new session right after clear + the old one still detected alive)
    #   every agent in it went in **twice**, and the lane splitter honestly showed "2 at once"
    #   (1/2 · 2/2 — two rows identical down to tid and aid). File I/O doubled too.
    # ★**Every transcript with records in the window is counted** (2026-09-09: count all so it matches
    #   the daily totals). Session rows used to read only **the newest one** per project (`fs[0]`) and agents only the
    #   last 3 sessions (`fs[:3]`), so old sessions split off by today's `/clear` or restarts were dropped whole —
    #   measured 12 h window: timeline 524.4M vs all files 677.98M (**23% missing**). Directories also cover
    #   **everything written in the window**, not just those in `sessions()` (31 listdirs · measured 1ms).
    # ⚠Gantt lines do not multiply — JS groups session rows by `S|cwd` and draws several bars on
    #   **one line per project** (around `:12469`). So a row per session does not blow up the screen.
    by_sid = {}                     # session id -> sessions() row (live state and task name live here)
    for r in rows:
        if r.get("sid"):
            by_sid[r["sid"]] = r
    # ⚠The picking rules moved to `_tl_pick` — quota calculation (`_tok_events`) must see **the same file set**.
    #   The rules are unchanged (see ★ there).
    for dcwd, dproj, pick, _ in _tl_pick(cut, rows):
        for fp in pick:
            sid = os.path.basename(fp)[:-len(".jsonl")]
            srow = by_sid.get(sid)
            cwd = (srow.get("cwd") if srow else "") or dcwd
            proj = (srow.get("project") if srow else "") or dproj
            if not cwd:
                continue
            if pcwd is not None:
                pcwd[sid] = (cwd, proj)
            sd = fp[:-len(".jsonl")]
            n0 = len(out)
            for tid, mm in _agent_meta(sd, ttl=10).items():
                a = _tl_agent_row(tid, mm, cut, live, live_aid, proj, cwd)
                if a is not None:
                    out.append(a)
            out.extend(_tl_wf_rows(sd, sid, cut, proj, cwd))
            s = _tl_sess_row(fp, sid, srow, cut, cwd, proj)
            if s is not None:
                out.append(s)
            # Account picker filter key; primary rows get no key so the goldens stay byte-equal.
            acct = claude_roots.acct_of(sid, fp)[0] if len(out) > n0 else ""
            for x in out[n0:] if acct else ():
                x["acct"] = acct
    return out


# ⚠No per-file memo here: sidereus/agents.py's caches (AGENT_CACHE_MAX) cover the 168h working set (842 files, 2026-09-25).
def _tl_agent_row(tid, mm, cut, live, live_aid, proj, cwd):
    """One subagent row, or None when its log is missing or quiet since `cut`."""
    f2 = mm.get("_file") or ""
    if not f2 or not os.path.exists(f2):
        return None
    try:
        stt = os.stat(f2)
    except OSError:
        return None
    born = getattr(stt, "st_birthtime", stt.st_ctime)
    if stt.st_mtime < cut:
        return None
    _tk = []                  # (time, tokens) this row used in the window — for totals and the strip below
    return {"tid": tid, "type": mm.get("agentType") or "agent",
            # ★a nested agent's **parent agent id** — meta gives it directly (measured 2026-09-01).
            #   Used to link session > agent > nested agent by real lineage.
            "aid": mm.get("_id") or "", "par": mm.get("parentAgentId") or "",
            # ★Agent tool one-line `description` — the row label since 2026-09-25 (metadata, never a message body).
            "desc": (mm.get("description") or "")[:80],
            # last tool line — reads only the tail, cached by (path, mtime) (near-zero extra cost)
            "last": _agent_last(f2)[:90],
            # ★agents are split into **real activity segments** too (2026-09-02: time the MacBook
            #   was closed looked like continuous work). A solid bar is a lie.
            "segs": [[int(a), int(b)] for a, b in
                     _sess_segments(f2, cut, nb=2_000_000, lim=4000,
                                    tok_out=_tk)[0]],
            "tk": sum(n for _t, n in _tk), "_tk": _tk,
            # ★for the summary card to say "N tools" the row needs that count — it was missing and
            #   `segs` (activity pieces) stood in (2026-09-22). ⚠Never fill it with an estimate;
            #   if the source lacks it, dropping the line is better.
            #   `tc` = number of tools the agent called · `fin` = ended with a final report (0/1).
            #   ⚠Two integers only — no new string content (response size).
            "tc": _agent_tools(f2), "fin": 1 if _agent_fin(f2) else 0,
            "start": int(born), "end": int(stt.st_mtime),
            "run": bool(live.get(tid) or live_aid.get(mm.get("_id") or "")),
            "proj": proj,
            "cwd": cwd, "depth": int(mm.get("spawnDepth") or 1)}


def _tl_wf_rows(sd, sid, cut, proj, cwd):
    """Workflow-tool runs of one session: a run row (kind "wf") + one row per agent hanging under it (par = run aid).
    ★2026-09-26: these agents live in subagents/workflows/wf_<id>/ and were missing from the timeline.
    ⚠The run row carries no `_tk` — its children do; the token strip and peak would count it twice otherwise.
    ⚠tids "wf:"/"wfa:" have no work log (no Agent tool_use id) — tlOpen ignores them."""
    out = []
    for r in wf_runs(sd, since=cut):
        kids = []
        for a in r["agents"]:
            f2 = a["_file"]
            if not f2 or a["end"] < cut:
                continue
            tk = []
            segs = _sess_segments(f2, cut, nb=2_000_000, lim=4000, tok_out=tk)[0]
            kids.append({"tid": "wfa:" + a["aid"] + "|" + sid, "type": a["phase"] or "agent", "aid": a["aid"],
                         "par": "wf:" + r["id"], "desc": a["lab"][:80], "last": _agent_last(f2)[:90],
                         "segs": [[int(x), int(y)] for x, y in segs], "tk": sum(n for _t, n in tk), "_tk": tk,
                         "tc": _agent_tools(f2), "fin": 1 if a["st"] == "done" else 0,
                         "start": a["start"], "end": a["end"], "run": a["st"] == "run",
                         "proj": proj, "cwd": cwd, "depth": 2})
        if not kids:
            continue
        out.append({"tid": "wf:" + r["id"] + "|" + sid, "type": r["name"] or r["id"], "aid": "wf:" + r["id"],
                    "par": "", "desc": "", "last": "", "kind": "wf", "segs": [],
                    "wf": {"name": r["name"], "id": r["id"], "phase": r["phase"], "done": r["done"],
                           "fail": r["fail"], "total": r["total"]},
                    "tk": sum(k["tk"] for k in kids), "tc": sum(k["tc"] for k in kids), "fin": 0 if r["run"] else 1,
                    "start": min(k["start"] for k in kids), "end": max(k["end"] for k in kids), "run": r["run"],
                    "proj": proj, "cwd": cwd, "depth": 1})
        out.extend(kids)
    return out


def _tl_sess_row(fp, sid, srow, cut, cwd, proj):
    """The main-session row of transcript `fp`, or None when unreadable or quiet since `cut`."""
    # ★The main session gets a line too (2026-09-01; the main session's work log was missing). Its bar is
    #   **the span the session was open** — transcript creation to last record. Different nature from agents, so kind separates them.
    #   ⚠It used to run a separate loop over `fs[0]` only — that caused the 23% loss (★ in `_tl_rows`).
    #     Now one row **per transcript of the project**, and the UI groups by `S|cwd` onto one line.
    try:
        stt = os.stat(fp)
    except OSError:
        return None
    if stt.st_mtime < cut:
        return None
    born = getattr(stt, "st_birthtime", stt.st_ctime)
    _tk = []
    segs, seen0 = _sess_segments(fp, cut, tok_out=_tk)   # segments that actually moved
    _wt = _sess_waits(fp, cut)                # waits on the person, from the scan just cached
    comp = _compacts(fp, cut)                 # compaction history (where context was lost)
    # tid always carries the sid: a plain `sess:<cwd>` opens the cwd's newest file, not this one.
    row = {"tid": "sess:" + cwd + "|" + sid,
            "sid": sid,                       # lets a Gemini child find its launching session by sid (JS `tlSessions`)
            "type": proj or os.path.basename(cwd),
            # ⚠Session rows carry no `task` since 2026-09-25 (rule 1) — the desc is fixed text + sid only.
            "desc": ("Session" if srow else "Session — past session " + _sid8(sid)),
            "segs": [[int(a), int(b)] for a, b in segs], "comp": comp,
            "seen": int(seen0),               # oldest time the tail window reached
            "start": int(max(born, cut)), "end": int(stt.st_mtime),
            # a session is running **only when actually working** — old sessions not in the list are not running
            "run": bool(srow) and srow.get("state") in ("tool", "think"),
            "state": (srow.get("state") or "") if srow else "",
            "idle": int((srow.get("ageSec") or 0) if srow else 0),
            "blocked": (srow.get("blocked") or "") if srow else "",
            "proj": proj,
            "cwd": cwd, "depth": 0, "kind": "sess",
            "tk": sum(n for _t, n in _tk), "_tk": _tk,
            "last": ((srow.get("tool") or "") +
                     (" · " + srow.get("targ") if srow.get("targ") else "")) if srow else ""}
    clr = clear_of(sid)               # /clear that started this sid; key absent otherwise (goldens stay byte-equal)
    if clr:
        row["clr"] = [{"at": c["at"], "old8": _sid8(c["old"]), "new8": _sid8(c["new"])} for c in clr]
    if _wt:                           # [prompts that waited on the person, seconds]; key absent at 0 (goldens)
        row["wt"] = [len(_wt), sum(_wt)]
    return row


def _tl_dedup(out):
    # ★Invariant: one agent = one row. Directory duplication is prevented in `_tl_rows`, but locked once more here —
    #   if this breaks, the screen falsely claims "N ran at once".
    _dedup, _uniq = set(), []
    for a in out:
        k = a.get("tid") or ""
        if k and k in _dedup:
            continue
        _dedup.add(k)
        _uniq.append(a)
    return _uniq


def _tl_finish(out, hours, cut, now):
    """Row cap, sleep/idle strips, peak concurrency and the token strip → the response body."""
    # ★The row cap is applied **here** — it used to be `out[-200:]` at the end. Two things went wrong:
    #   ① session rows sort first, so overflow cut **session rows first** (sessions carry the most tokens).
    #   ② the token strip (`vec`) below summed everything **before** the cut, so on overflowing windows "strip sum ≠ row sum".
    #   ⇒ Keep all session rows and cut only agents to the most recent. Then fold the strip.
    _ss = [a for a in out if a.get("kind") == "sess"]
    _ag = [a for a in out if a.get("kind") != "sess"]
    _nag = max(0, TL_ROW_MAX - len(_ss))
    # ★The sleep strip is "slept + no records" (★ in `_naps_awake`). Activity counts everything **before the cut** —
    #   agents dropped from the screen by the row cap were still awake at the time.
    _nl = naps(hours)
    _naps = _naps_awake(_nl, _ss + _ag)
    # ★The idle strip also uses everything **before the cut** (same reason as ★ above — agents dropped by the cap
    #   were still working then). Raw sleep (`_nl`) is subtracted for zero overlap.
    _idle = _idle_gaps(_nl, _ss + _ag, cut, now)
    out = _ss + (_ag[-_nag:] if _nag else [])
    # peak concurrency — "did they really run in parallel" is this screen's question
    ev = []
    for a in out:
        if a.get("kind") in ("sess", "wf"):
            continue                # peak counts **agents only** (sessions are always up; a workflow run is its agents)
        ev.append((a["start"], 1)); ev.append((a["end"], -1))
    ev.sort()
    cur = mx = 0
    for _, dd in ev:
        cur += dd
        mx = max(mx, cur)
    # ★**Token strip** (added 2026-09-08 to show token usage alongside).
    #   Each row's (time, tokens) is folded into window-wide buckets — as the replay passes, the strip fills,
    #   and the cursor panel reads "cumulative so far" and "rate at that moment" directly.
    #   ⚠**Double counting ① files**: the main transcript holds only the main agent's usage; subagent records
    #     are separate files (`_today_fetch` also adds the two patterns separately) ⇒ plain sum of rows is right.
    #     Verified by measurement (2026-09-09): duplicate response pairs were **all within one file**, none
    #     overlapping between session and subagent.
    #   ⚠**Double counting ② lines**: one response spans several lines, each with a usage copy ⇒
    #     `_seg_scan` filters by `(message.id, requestId)` (★ above `_resp_key_line`).
    #   ★**All transcripts in the window are now counted** (2026-09-09 · "count all to match daily" above).
    #     The only remaining difference is **the window** — here the last N hours, the day card from midnight.
    #     Measured (same 12 h window): row sum 757,445,605 = all files 757,445,605 (error 0.00%).
    #   ⚠Rows whose segments (`segs`) hit the cap only reach that far in tokens too (the hatching already says so).
    span = max(60.0, now - cut)
    step = max(30, int(span / 240))              # within 240 buckets — widening the window doesn't grow the response
    nb2 = int(span // step) + 1
    vec = [0] * nb2
    # ★Each **bar** also gets its own share (`tks` — 2026-09-09; the strip showed only totals, not per-bar usage).
    #   Previously only the row total (`tk`), so the row tooltip showed a single "tokens 15M" — which piece
    #   of the row used them was invisible.
    #   ⚠Minutes (`分`) already taught the same lesson (JS below, "write each piece's own length") —
    #     printing the total on every piece repeats the same number and becomes false. So **own share** is sent.
    #   Assignment: to **the piece covering** that time, else **the preceding piece** (usage is recorded right after
    #   the work ends, so landing in gaps between pieces is normal). Anything before the first piece goes to
    #   the first ⇒ `sum(tks) == tk` always holds (the UI shows both numbers together).
    for a in out:
        _sg = a.get("segs") or []
        _st = [g[0] for g in _sg]
        _ts = [0] * len(_sg)
        _cc = not a.get("plat")          # ⚠the strip and `sum` stay Claude-only; Gemini rows keep `tk`/`tks`
        for t, n in (a.pop("_tk", None) or []):
            i = int((t - cut) // step)
            if _cc and 0 <= i < nb2:
                vec[i] += n
            if _ts:
                _ts[max(0, bisect.bisect_right(_st, t) - 1)] += n
        if _ts:
            a["tks"] = _ts
    return {"ok": True, "at": int(now), "hours": round(hours, 1), "peak": mx,
            "tok": {"t0": int(cut), "step": int(step), "v": vec, "sum": sum(vec)},
            # sleep intervals — let the UI say whether a gap is "unused" or "stopped" (★ above `naps`)
            "naps": _naps,
            # idle intervals — let the UI tell "slept" from "awake but idle" (★ in `_idle_gaps`)
            "idle": _idle,
            "rows": out}


# ★Measured 2026-09-23: cold `agents_timeline` 1h = 2.9 s alone (sessions 1.05 · pmset naps 1.35 · segments 0.45),
#   5.5 s beside the startup threads; warm 0.01-0.07 s. The page reloads right after a restart, so fill the caches first.
# ⚠One shot, delayed past the startup burst: no shared lock is taken, but it competes for the GIL with `/api/state`.
TL_WARM_DELAY_S = 4
# ★2026-09-25: after a restart the first 72h call took ~7.3 s (cold agents.py caches, ~640 agent files); 72h
#   is the common longer pick. Default first (the page reload), then 72h, which also covers 12h..72h picks.
TL_WARM_HOURS = (TL_HOURS, 72)


def _tl_warm():
    time.sleep(TL_WARM_DELAY_S)
    for h in TL_WARM_HOURS:            # each pass on its own: a failed default must not skip the 72h warm
        try:
            agents_timeline(h)
        except Exception as e:
            warn_once(f"tl-warm-{h}", "Timeline warm-up failed — {err}",
                      vars={"err": f"{type(e).__name__}: {e}"[:134]})


_tx_cwd_memo = BoundedMemo(400)            # path -> (mtime, cwd)


def _tx_cwd(fp):
    """Dig cwd out of a transcript. ★Only this survived the 2026-09-21 "daily" removal — the timeline uses it.

    ⚠**Never reconstruct from the slug** — as in `-home-me-work-repo-A`, hyphens inside names
    equal the separator, so restoration is impossible (`repo-A` vs `repo/A`).
    Read the transcript's `"cwd"` directly (every line carries it).

    ★**Read from the end, not the start** (measured 2026-09-09). A session can **continue in another folder**
    via `--resume`: `aa11aa11` started in `/home/me` and continued in `~/.mailbox-mcp` from 13:19.
      Reading the first line makes the chip `me` and fails to tell "which project".
    ⇒ `/today`'s `extract.py:105-107` decides the same (it **overwrites** with each line's `cwd` = last value).
      Two screens must not name the same session differently, so this matches it.
    ⚠The end may lack `cwd` (when the last 64KB is one huge result line) ⇒ fall back to the start."""
    if not fp:
        return ""
    try:
        mt = os.path.getmtime(fp)
    except OSError:
        return ""
    got = _tx_cwd_memo.get(fp, stamp=mt)
    if got is not None:
        return got
    def _last(buf):
        i = buf.rfind('"cwd":"')
        if i < 0:
            return ""
        j = buf.find('"', i + 7)
        return buf[i + 7:j].replace("\\", "/") if j > i else ""

    cwd = ""
    try:
        buf, sz = _tail_bytes(fp, 65536)
        cwd = _last(buf.decode("utf-8", "replace"))
        if not cwd and sz > 65536:
            with open(fp, "rb") as f:
                cwd = _last(f.read(16384).decode("utf-8", "replace"))
    except OSError:
        cwd = ""                    # transcript deleted or unreadable
    except Exception as e:          # unexpected: the row would lose its project
        warn_once("tl-cwd", "Could not read the working folder from a transcript ({err})",
                  vars={"err": type(e).__name__}, soft=True)
        cwd = ""
    return _tx_cwd_memo.put(fp, cwd, stamp=mt)
