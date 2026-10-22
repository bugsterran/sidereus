"""Per-session pipeline runs for stage lighting that survives a page reload.

hooks/pl_flow.py writes DATA_DIR/plmark/<sid>.runs.json {"v": 1, "runs": {<name>: {cur, end, t0, t1, st, ...}},
"past": {<name>: [run, ...]}} (past = earlier runs of the same name, oldest first, same run shape).
⚠Metadata only (AGENTS.md rule 1): name/cur/end/t0/t1/st/lb/stop are copied through an allow-list — cwd, proj, loops, ret,
  inflight and anything a later hook version adds never reach a row.
  `pl_model` (row `plrun`) adds only a validated absolute `proj` path on top of that.
"""
import json
import os
import re
import time

from sidereus.config import DATA_DIR
from sidereus.memo import BoundedMemo
from sidereus.redact import redact
from sidereus.agents import _agent_meta, _subs_mt

PLR_DIR = os.path.join(DATA_DIR, "plmark")
PLR_KEEP_S = 6 * 3600     # = hooks/pl_flow.py IDLE_S: an older run is over and the next tag opens a new one
PLR_MAX = 8               # runs per session row
PLR_READ_MAX = 262144     # bytes read from one runs file; ⚠a cut file fails to parse and loses every run, and `past` multiplies its size
PLR_STAGES_MAX = 32       # stages per run
_PLR_SID = re.compile(r"^[0-9a-zA-Z-]{8,64}$")
PLR_NONE_MAX = 4096       # bytes of <sid>.none.json; larger -> None
PLR_NONE_CATS = ("small-fix", "no-fit", "explore", "other")   # = hooks/pl_flow.py [pl-none:<cat>] allow-list
PLR_NONE_LOG = "none-log.jsonl"   # = hooks/pl_flow.py NONE_LOG
PLR_NONE_LOG_MAX = 262144         # bytes read from its tail; = hooks/pl_flow.py NONE_LOG_MAX
_PLR_ST = ("run", "done", "skip", "back", "fail")
PLR_AG_MAX = 24           # stage agents kept per run (oldest first)
PLR_AG_SLACK_S = 5        # meta mtime may sit this far outside [t0, end|now]
_PLR_TAG = re.compile(r"\[pl:([a-z0-9-]{1,40})/([^\]]{1,80})\]")
PLR_AG_TTL_S = 15         # stage-agent list reused this long while subagents/ mtime is unchanged
_PLR_AG_MEMO = BoundedMemo(64)   # sess_dir -> (sig, {name: [agent]})
PLR_MODEL_MAX = 6         # runs in row `plrun`
PLR_MODEL_AG_RUNS = 3     # open runs (newest first) carrying per-stage `ag`, plus the newest ended run
PLR_PROJ_MAX = 300        # chars of `proj`; longer / relative / control chars -> ""
PLR_LAB_MAX = 120
PLR_PAST_MAX = 5          # earlier runs per name in row `past` (= hooks/pl_flow.py past cap)
PLR_IDS_MAX = 8           # = hooks/pl_flow.py AG_IDS_MAX
PLR_PS_MAX = 6            # = hooks/pl_flow.py PS_MAX
PLR_OPEN_S = 1800         # open run with no evidence this long and nothing live -> shown ended at its last evidence
PLR_STALE_S = 600         # cur «run» with no tagged evidence this long -> «hold» idle (busy signal alone cannot keep it lit)
PLR_TITLE_MAX = 80       # stage title cap = `_PLR_TAG` group 2; ⚠every cut must use it or one stage splits in two
RENAMED = {"최종 검증": "재검증"}   # = sidereus/pipeline_schema.RENAMED (feature modules stay uncoupled; a test keeps them equal)


def _title(t):
    """Stage title as shown: a renamed recommended title maps to its new name (legacy runs, old tags), then the cap."""
    return RENAMED.get(t, t)[:PLR_TITLE_MAX]


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def _passes(v):
    """[{a, b, s}] closed earlier passes; ⚠all or nothing — one bad entry drops the list (pass numbers would shift)."""
    if not isinstance(v, list) or not v or len(v) > PLR_PS_MAX:
        return []
    for e in v:
        if not (isinstance(e, dict) and set(e) == {"a", "b", "s"} and _num(e["a"]) and _num(e["b"]) and e["s"] in _PLR_ST):
            return []
    return [{"a": _num(e["a"]), "b": _num(e["b"]), "s": e["s"]} for e in v]


def _stages(st):
    out = {}
    if not isinstance(st, dict):
        return out
    for title, s in list(st.items())[:PLR_STAGES_MAX]:
        if isinstance(title, str) and title and isinstance(s, dict) and s.get("s") in _PLR_ST:
            n = s.get("n")
            title = _title(title)
            out[title] = {"s": s["s"], "t0": _num(s.get("t0")), "t1": _num(s.get("t1")),
                               "n": n if isinstance(n, int) and not isinstance(n, bool) and n >= 0 else 0}
            ids = [x[:64] for x in (s.get("ag") if isinstance(s.get("ag"), list) else [])[:PLR_IDS_MAX] if isinstance(x, str) and x]
            if ids:   # SendMessage targets continued into this stage (hook `ag`)
                out[title]["ids"] = ids
            p0, k = s.get("p0"), s.get("k")
            if _num(p0) and isinstance(k, int) and not isinstance(k, bool) and k >= 2:   # hook: start + count of the latest pass
                out[title].update(p0=_num(p0), k=k)
            ps = _passes(s.get("ps"))
            if ps:   # hook: closed earlier passes, oldest first
                out[title]["ps"] = ps
            cm = [_num(x) for x in (s.get("cm") if isinstance(s.get("cm"), list) else [])[-4:] if _num(x)]
            if cm:   # hook: commit times in this stage, newest last
                out[title]["cm"] = cm
            if s.get("m") is True:   # hook: main's own tagged Bash/shell marker ran this stage
                out[title]["main"] = True
    return out


def _loopbacks(v):
    """[{f, g, n, t}] loop-back edges (stage titles + count); malformed entries and extra keys dropped."""
    out = []
    for e in (v[:PLR_STAGES_MAX] if isinstance(v, list) else ()):
        if not isinstance(e, dict):
            continue
        f, g, n = e.get("f"), e.get("g"), e.get("n")
        if isinstance(f, str) and f and isinstance(g, str) and g and isinstance(n, int) and not isinstance(n, bool) and n >= 1:
            out.append({"f": _title(f), "g": _title(g), "n": n, "t": _num(e.get("t"))})
    return out


def _load_doc(sid, now):
    """Raw document of plmark/<sid>.runs.json, or {} (bad sid / missing / stale / unparsable)."""
    if not sid or not _PLR_SID.match(sid):
        return {}
    fp = os.path.join(PLR_DIR, sid + ".runs.json")
    try:
        if now - os.path.getmtime(fp) > PLR_KEEP_S:
            return {}
        with open(fp, "rb") as f:
            d = json.loads(f.read(PLR_READ_MAX))
    except (OSError, ValueError, TypeError):
        return {}
    return d if isinstance(d, dict) else {}


def pl_none(sid):
    """Row `plNone` from plmark/<sid>.none.json (hooks/pl_flow.py): {"cat"} when declared [pl-none:<cat>] with an
    allow-listed cat, {"u": 1} when only the undeclared-edit `nudge` is set, else None. ⚠Reads no other field."""
    if not sid or not _PLR_SID.match(sid):
        return None
    try:
        with open(os.path.join(PLR_DIR, sid + ".none.json"), "rb") as f:
            b = f.read(PLR_NONE_MAX + 1)
        d = json.loads(b) if len(b) <= PLR_NONE_MAX else None
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(d, dict):
        return None
    c = d.get("cat")
    if isinstance(c, str) and c in PLR_NONE_CATS:
        return {"cat": c}
    if c is None and isinstance(d.get("nudge"), (int, float)) and not isinstance(d.get("nudge"), bool):
        return {"u": 1}
    return None


def pl_none_counts(days=7, now=None):
    """R3: {proj: {cat: n}} of [pl-none:<cat>] declarations in the last `days` from plmark/none-log.jsonl
    (hooks/pl_flow.py _none_log). Reads at most the newest PLR_NONE_LOG_MAX bytes; bad lines and unknown cats are skipped."""
    now = time.time() if now is None else now
    try:
        with open(os.path.join(PLR_DIR, PLR_NONE_LOG), "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - PLR_NONE_LOG_MAX))
            b = f.read(PLR_NONE_LOG_MAX)
    except OSError:
        return {}
    lines = b.split(b"\n")
    if size > PLR_NONE_LOG_MAX:
        lines = lines[1:]   # the first line may be cut mid-record
    out = {}
    for ln in lines:
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        if not isinstance(d, dict):
            continue
        p, c, t = d.get("proj"), d.get("cat"), d.get("t")
        if not (isinstance(p, str) and os.path.isabs(p) and isinstance(c, str) and c in PLR_NONE_CATS
                and isinstance(t, (int, float)) and not isinstance(t, bool) and 0 <= now - t <= days * 86400):
            continue
        row = out.setdefault(p, {})
        row[c] = row.get(c, 0) + 1
    return out


def _load(sid, now):
    """Raw {name: run} of plmark/<sid>.runs.json, or {}."""
    runs = _load_doc(sid, now).get("runs")
    return runs if isinstance(runs, dict) else {}


def _load_past(past, now):
    """{name: [run]} newest first (≤ PLR_PAST_MAX) from the hook's `past` (oldest first); same allow-list as pl_runs_of."""
    out = {}
    for name, xs in (past.items() if isinstance(past, dict) else ()):
        if isinstance(xs, list):
            rows = []
            for r in xs[-PLR_PAST_MAX:]:
                rows += pl_runs_of("", now, _raw={name: r})
            if rows:
                out[name] = sorted(rows, key=lambda r: -r["t0"])[:PLR_PAST_MAX]
    return out


def pl_runs_of(sid, now, _raw=None):
    """[{name, cur, end, t0, t1, st, lb, stop}] newest first (≤ PLR_MAX) for `sid`; [] when missing/stale/bad."""
    runs = _load(sid, now) if _raw is None else _raw
    out = []
    for name, r in runs.items():
        if not (isinstance(name, str) and re.match(r"^[a-z0-9-]{1,40}$", name) and isinstance(r, dict)):
            continue
        t1 = _num(r.get("t1"))
        if now - t1 > PLR_KEEP_S:
            continue
        # `stop` = Sidereus «Stop» time stamped by hooks/pl_guard.py; ⚠a stopped run counts as ended (never shown running)
        stop = _num(r.get("stop"))
        out.append({"name": name, "cur": _title(r.get("cur")) if isinstance(r.get("cur"), str) else "",
                    "end": _num(r.get("end")) or stop, "t0": _num(r.get("t0")), "t1": t1, "st": _stages(r.get("st")),
                    "lb": _loopbacks(r.get("lb")), "stop": stop})
    out.sort(key=lambda r: -r["t1"])
    return out[:PLR_MAX]


def _ag_by_name(sess_dir, now):
    """{run name: [agent {aid, tid, t, lab, t0, t1}]} from `[pl:<name>/<stage>]`-tagged subagent meta, memoized on
    (subagents/ mtime, PLR_AG_TTL_S bucket). ⚠Metadata only: `lab` = agentType + Agent description — never transcript text.
    ⚠Dir mtime alone misses jsonl growth (t1), hence the TTL bucket; the run window is applied per call, not cached."""
    sig = (_subs_mt(sess_dir), int(now // PLR_AG_TTL_S))
    hit = _PLR_AG_MEMO.get(sess_dir, stamp=sig)
    if hit is not None:
        return hit
    byname = {}
    for tid, m in _agent_meta(sess_dir).items():
        if not isinstance(m, dict):
            continue
        desc = m.get("description")
        hit = _PLR_TAG.search(desc) if isinstance(desc, str) else None
        jf = m.get("_file") or ""
        if not hit or not jf.endswith(".jsonl"):
            continue
        try:
            mt = os.path.getmtime(jf[:-len(".jsonl")] + ".meta.json")
        except OSError:
            continue
        try:
            jt = os.path.getmtime(jf)
        except OSError:
            jt = mt
        lab = (str(m.get("agentType") or "") + ": " + desc)[:120]
        d = redact(" ".join(_PLR_TAG.sub(" ", desc).split()))[:PLR_LAB_MAX]   # bare description -> run label `lab`
        byname.setdefault(hit.group(1), []).append(
            {"aid": str(m.get("_id") or ""), "tid": str(tid), "t": _title(hit.group(2)), "lab": redact(lab), "d": d, "t0": mt, "t1": jt})
    return _PLR_AG_MEMO.put(sess_dir, byname, stamp=sig)


def _proj(v):
    """Absolute project path from runs.json, or "" (non-str, relative, `..`, control chars, > PLR_PROJ_MAX)."""
    if not isinstance(v, str) or not v or len(v) > PLR_PROJ_MAX or not os.path.isabs(v):
        return ""
    # ⚠Split on both: Windows takes `/` too, so `/a/../b` slipped past a split on os.sep alone.
    if any(ord(c) < 32 or c == "\x7f" for c in v) or ".." in v.replace("\\", "/").split("/"):
        return ""
    return v


def _cap_ag(ags):
    """≤ PLR_AG_MAX per run, sorted by t0; ⚠trimming drops the oldest finished agents first so live ones stay visible."""
    ags.sort(key=lambda a: a["t0"])
    drop = set(id(a) for a in [a for a in ags if not a["run"]][:max(0, len(ags) - PLR_AG_MAX)])
    return [a for a in ags if id(a) not in drop][:PLR_AG_MAX]


def _stage_map(r):
    """{title: {o, n, t0, t1, from, main?, p0?, k?, ps?, cm?, via?}} of one validated run (no `ag`)."""
    stages = {}
    for title, s in r["st"].items():
        stages[title] = {"o": s["s"], "n": s["n"], "t0": s["t0"], "t1": s["t1"], "from": {}}
        if s.get("main"):
            stages[title]["main"] = True
        if s.get("k"):
            stages[title].update(p0=s["p0"], k=s["k"])   # absent: one pass, starting at t0
        if s.get("ps"):
            stages[title]["ps"] = s["ps"]
        if s.get("cm"):
            stages[title]["cm"] = s["cm"]
    for e in r["lb"]:
        if e["g"] in stages:
            stages[e["g"]]["from"][e["f"]] = e["n"]
            # ⚠`via` = the edge that opened the latest pass (hook stamps lb t == p0); `from` is cumulative, so an older loop-back pulsed on every later pass
            s = stages[e["g"]]
            if s.get("p0") and e["t"] >= s["p0"] and e["t"] >= s.get("_vt", 0):
                s["via"], s["_vt"] = e["f"], e["t"]
    for s in stages.values():
        s.pop("_vt", None)
    return stages


def _run_lab(ags, lo, hi):
    """Run label = bare description of the earliest tagged agent with meta time in [lo, hi], or "" (Agent description only)."""
    xs = [a for a in ags or () if lo <= a["t0"] <= hi and a.get("d")]
    return min(xs, key=lambda a: a["t0"])["d"] if xs else ""


def pl_model(sid, sess_dir, sub, plm, now, act="run", pend_sub=(), bgs=()):
    """Row `plrun`: [{name, proj, sid, rid, lab, cur, end, t0, t1, stop, stages: {title: {o, n, t0, t1, from: {src: n}, ag?: [...]}},
    past: [{rid, t0, t1, end, cur, lab, stages}]}] — rid = t0, lab = first tagged agent's bare description, past = earlier
    runs of that name newest first (≤ PLR_PAST_MAX, no `ag`, closed as idle).
    Newest first, ≤ PLR_MODEL_MAX; `ag` [{aid, tid, lab, run, t0, t1}] only on the newest PLR_MODEL_AG_RUNS open runs + the newest ended run.
    Sources: runs.json st/lb/proj · tagged subagent meta · live `sub` rows ([pl:] in lab) · open `bgs` rows (tagged
    Bash(run_in_background); label = redacted description) · `plm` main marker.
    ⚠Metadata only (rule 1): ids, titles, times, counts, agentType+description label — never message/prompt text."""
    doc = _load_doc(sid, now)
    raw = doc.get("runs") if isinstance(doc.get("runs"), dict) else {}
    runs = pl_runs_of(sid, now, _raw=raw)[:PLR_MODEL_MAX]
    # act = pl_act(row state); pend_sub = an ended session's subagents still open at the transcript end -> {(name, title)}
    pend = set()
    for x in (pend_sub if isinstance(pend_sub, list) else ()):
        m = _PLR_TAG.search(x.get("lab") or "") if isinstance(x, dict) and isinstance(x.get("lab"), str) else None
        if m:
            pend.add((m.group(1), _title(m.group(2))))
    # ⚠Pick by open/ended, not by index: an older open run behind newer ended ones lost its agents with `i < 2`.
    opn = [i for i, r in enumerate(runs) if not r["end"]][:PLR_MODEL_AG_RUNS]
    agi = set(opn + [i for i, r in enumerate(runs) if r["end"]][:1])
    byname = _ag_by_name(sess_dir, now) if sess_dir and runs else {}   # every row needs it for `lab`
    out = []
    past = _load_past(doc.get("past"), now)
    for i, r in enumerate(runs):
        stages = _stage_map(r)
        lo, hi = r["t0"] - PLR_AG_SLACK_S, (r["end"] or now) + PLR_AG_SLACK_S
        row = {"name": r["name"], "proj": _proj((raw.get(r["name"]) or {}).get("proj")), "sid": sid,
               "rid": r["t0"], "lab": _run_lab(byname.get(r["name"]), lo, hi),
               "cur": r["cur"], "end": r["end"], "t0": r["t0"], "t1": r["t1"], "stop": r["stop"], "stages": stages, "past": []}
        for p in past.get(r["name"], ()):
            if p["t0"] >= r["t0"]:
                continue   # ⚠a past entry is never the current run itself (hook archives on a new open)
            ps = {"rid": p["t0"], "t0": p["t0"], "t1": p["t1"], "end": p["end"], "cur": p["cur"],
                  "lab": _run_lab(byname.get(r["name"]), p["t0"] - PLR_AG_SLACK_S, (p["end"] or p["t1"]) + PLR_AG_SLACK_S),
                  "stages": _stage_map(p)}
            _close_stale(ps, "idle", ())   # an archived run is over: nothing in it is live
            row["past"].append(ps)
        out.append(row)
        if i not in agi:
            # ⚠Outside the agent-row window a live tagged sub/bg row still proves the run alive (idle-end check below).
            row["_live"] = not r["end"] and any(
                isinstance(x, dict) and isinstance(x.get("lab"), str) and (_PLR_TAG.search(x["lab"]) or [0, ""])[1] == r["name"]
                for x in list(sub if isinstance(sub, list) else ()) + list(bgs if isinstance(bgs, list) else ()))
            continue
        ags = [{"aid": a["aid"], "tid": a["tid"], "lab": a["lab"][:PLR_LAB_MAX], "run": False, "t0": a["t0"], "t1": a["t1"],
                "_t": a["t"]}
               for a in byname.get(r["name"], ()) if a["t"] in stages and lo <= a["t0"] <= hi]
        # An agent continued (SendMessage) into another stage is listed there too, besides its own tagged stage.
        base = list(ags)
        for title, s in r["st"].items():
            for a in [a for a in base if a["aid"] in s.get("ids", ()) and a["_t"] != title]:
                ags.append(dict(a, _t=title))
        # ⚠Open tagged bg tasks count too: after the turn ends only they prove the stage still works (the marker expires).
        for x in list(sub if isinstance(sub, list) else ()) + list(bgs if isinstance(bgs, list) else ()):
            lab = x.get("lab") if isinstance(x, dict) else None
            m = _PLR_TAG.search(lab) if isinstance(lab, str) else None
            # ⚠A live agent belongs to the open run only: an ended run of the same name had its stage re-lit by it.
            if not m or m.group(1) != r["name"] or r["end"]:
                continue
            title, aid, tid = _title(m.group(2)), str(x.get("aid") or "")[:64], str(x.get("tid") or "")[:64]
            hit = next((a for a in ags if (aid and a["aid"] == aid) or (tid and a["tid"] == tid)), None)
            mine = [a for a in byname.get(r["name"], ()) if (aid and a["aid"] == aid) or (tid and a["tid"] == tid)]
            # ⚠Skip only when no meta falls in the window: in-window meta for a stage not yet in runs.json is this run's agent.
            if hit is None and mine and not any(lo <= a["t0"] <= hi for a in mine):
                continue   # still-live agent of an earlier run of this name (meta outside the window): not this run's work
            if hit is None:
                mn = x.get("min")
                t0 = now - 60 * mn if isinstance(mn, int) and not isinstance(mn, bool) and mn >= 0 else now
                if title not in stages:
                    if len(stages) >= PLR_STAGES_MAX:
                        continue
                    # ⚠t0 = agent start, not now: `now` showed «Running · 0s» for an agent minutes in.
                    stages[title] = {"o": "run", "n": 0, "t0": t0, "t1": now, "from": {}}
                hit = {"aid": aid, "tid": tid, "lab": redact(lab)[:PLR_LAB_MAX], "run": False, "t0": t0, "t1": now, "_t": title}
                ags.append(hit)
            for a in [a for a in ags if a is hit or (hit["aid"] and a["aid"] == hit["aid"])]:
                a["run"] = True   # ⚠every copy: a continued agent's live row still carries its original stage tag
                stages[a["_t"]]["o"] = "run"
        for st in stages.values():
            st["ag"] = []
        for a in _cap_ag(ags):
            stages[a.pop("_t")]["ag"].append(a)
        # ⚠A closed run (end set, e.g. by `git commit`) never takes the main marker: the marker outlives the close by
        #   its 2-min window, and attaching it re-lit a stage of a run that is already over.
        if isinstance(plm, dict) and isinstance(plm.get("title"), str):
            plm = dict(plm, title=_title(plm["title"]))   # an old marker tag keeps lighting the renamed stage
        if isinstance(plm, dict) and not r["end"] and plm.get("name") == r["name"] and plm.get("title") in stages:
            age = plm.get("age")
            t0 = now - age if isinstance(age, int) and not isinstance(age, bool) and age >= 0 else now
            stages[plm["title"]]["ag"].append({"aid": "main", "tid": "", "lab": "main", "run": True, "t0": t0, "t1": now})
    lasts = [max([row["t1"]] + [st["t1"] for st in row["stages"].values()]
                 + [g["t1"] for st in row["stages"].values() for g in st.get("ag") or () if not g.get("run")]) for row in out]
    pmn = plm.get("name") if isinstance(plm, dict) else None
    for j, row in enumerate(out):
        tagged = row.pop("_live", False)
        # ⚠View-side close only (runs.json untouched): some last stages (main's push, bg dispatch) never write `end`.
        #   A live agent / main marker keeps it open at any age (a bg arch-map stage runs > 30 min).
        if (not row["end"] and now - lasts[j] > PLR_OPEN_S and pmn != row["name"] and not tagged
                and not any(a.get("run") for s in row["stages"].values() for a in s.get("ag") or ())):
            row["end"] = lasts[j]
    # ⚠The busy signal is session-wide: with several open runs, credit it only to runs that hold a live agent / main
    # marker (the work is visibly theirs); with none live, the newest open run takes it. Otherwise another run's live
    # agent kept a finished stage of the newest run at «run».
    live = [j for j, row in enumerate(out) if not row["end"]
            and any(a.get("run") for s in row["stages"].values() for a in s.get("ag") or ())]
    # ⚠Newest *open* run, not out[0]: an ended newer run at index 0 left no run busy and an open stage read «done».
    first = next((j for j, row in enumerate(out) if not row["end"]), -1)
    for j, row in enumerate(out):
        mine = (j in live if live else j == first) and not row["end"]
        _close_stale(row, act if mine else "idle", pend, lasts[j], now)
    return out


def pl_act(state, perm=False, dead=False):
    """Session activity for pl_model from the row's own evidence: run | ask | perm | end | idle."""
    if dead or state in ("done", "gone"):
        return "end"
    if state == "ask":
        return "ask"
    if perm:
        return "perm"
    return "idle" if state in ("wait", "abort") else "run"   # ⚠unknown/tool/think stay «run»: never infer idleness


def _close_stale(row, act, pend, last=None, now=None):
    """A stored «run» stage with no live agent (ag run / main marker): not cur -> «back» after cur, else «done» (older
    hooks never closed it on an undeclared backward move); cur -> by session evidence: busy «run» · ask/perm «hold» ·
    ended with a tagged agent still pending «hold» · busy but no evidence (`last`) for PLR_STALE_S «hold» idle ·
    otherwise «done». ⚠Order = runs.json st insertion order."""
    order = list(row["stages"])
    c = order.index(row["cur"]) if row["cur"] in order else -1
    for i, title in enumerate(order):
        s = row["stages"][title]
        if s["o"] != "run" or any(a.get("run") for a in s.get("ag") or ()):
            continue
        if title != row["cur"]:
            s["o"] = "back" if 0 <= c < i else "done"
        elif act in ("ask", "perm") or (act == "end" and (row["name"], title) in pend):
            s["o"], s["why"] = "hold", act
        elif act != "run":
            s["o"] = "done"
        elif last is not None and now is not None and now - last > PLR_STALE_S:
            s["o"], s["why"] = "hold", "idle"   # ⚠session «run» is session-wide (any tool use), not proof this stage works
