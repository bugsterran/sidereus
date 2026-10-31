"""Harness «Gate cost»: `cost(proj)` = what the pipeline gates cost over the last 7 days.

Blocks = runs.json `dl` (hooks/pl_flow.py, parsed by harness_flow.runs). A block is «Overridden» when a «Stop» of that
run's pipeline (pl_reqs.stops), a [pl-skip] (stage `s` == "skip", t0 = skip time) in the same session, or strict mode
turned off (`_policy.json` mtime while its content is not {"enforce":"writes"}) falls in (t, t + HC_WIN_S].
«Complied» = resumed (`rt`) and the window has passed; anything else is «unknown» (pending, or no `rt` recorded).
Gate time = passes of stages whose `gate` key is set in the pipeline file; hook overhead = otel_hooks day totals.
⚠Metadata only (rule 1): codes, stage titles, times and durations — never tool input or conversation content.
⚠None, never 0, when nothing was measured; there is no combined score.
"""
import json
import os
import re
import time

from sidereus import harness_flow, otel_hooks, pl_reqs, pl_runs
from sidereus.timefmt import ymd

HC_WIN_S = 1800            # a signal this soon after a block overrides it
HC_EV_MAX = 30             # evidence rows per list
HC_POLICY_MAX = 4096       # bytes read from _policy.json
HC_PIPE_MAX = 262144       # bytes read from a pipeline file
_HC_NAME = re.compile(r"[a-z0-9-]{1,40}")
_now = time.time


def _policy(proj):
    """mtime of <proj>/.claude/pipelines/_policy.json while strict mode is off (enforce != "writes"), else None (missing = no signal)."""
    if not (isinstance(proj, str) and os.path.isabs(proj)):
        return None
    fp = os.path.join(proj, ".claude", "pipelines", "_policy.json")
    try:
        mt = os.path.getmtime(fp)
        with open(fp, "rb") as f:
            b = f.read(HC_POLICY_MAX + 1)
        d = json.loads(b.decode("utf-8")) if len(b) <= HC_POLICY_MAX else None
    except (OSError, ValueError):
        return None
    return None if isinstance(d, dict) and d.get("enforce") == "writes" else mt   # = the hook's strict test: extra keys stay strict


def _gates(proj, name):
    """Titles of the stages with a `gate` in <proj>/.claude/pipelines/<name>.json, or None (missing / unreadable).
    ⚠Read here, not via pipeline._read_pipe: harness_cost belongs to no feature manifest (feature_couplings)."""
    if not (isinstance(proj, str) and os.path.isabs(proj) and _HC_NAME.fullmatch(name or "")):
        return None
    d = os.path.join(proj, ".claude", "pipelines")
    fp = os.path.join(d, name + ".json")
    if os.path.dirname(os.path.realpath(fp)) != os.path.realpath(d):
        return None
    try:
        with open(fp, "rb") as f:
            b = f.read(HC_PIPE_MAX + 1)
        p = json.loads(b.decode("utf-8")) if len(b) <= HC_PIPE_MAX else None
    except (OSError, ValueError):
        return None
    st = p.get("stages") if isinstance(p, dict) else None
    if not isinstance(st, list):
        return None
    return {pl_runs._title(s["title"]) for s in st if isinstance(s, dict) and isinstance(s.get("title"), str) and s.get("gate")}


def _row(code, stage, ts, dur_s, by=""):
    """Whitelisted evidence row; dur_ms None when there is no duration. ⚠`by` is a fixed key the page maps
    (stop · strict_off · skip = Overridden, pending · none = unknown, "" = complied / no cause)."""
    return {"code": code, "stage": stage, "ts": ts, "dur_ms": None if dur_s is None else int(round(dur_s * 1000)), "by": by}


def _union_s(iv):
    tot, end = 0.0, None
    for a, b in sorted(iv):
        if end is None or a > end:
            tot += b - a
            end = b
        elif b > end:
            tot += b - end
            end = b
    return tot


def _gate_time(got, gates_of):
    """(seconds or None, lower bound, rows) over gate stages of runs whose pipeline file is readable."""
    tot, lb, rows, seen = 0.0, False, [], False
    for r in got:
        g = gates_of(r["name"])
        if g is None:
            continue   # missing pipeline file: this run is not measured
        for title, s in r["st"].items():
            if title not in g or s["s"] == "skip" or not s["t1"]:
                continue
            seen = True   # ⚠only a counted gate stage measures: no / renamed gate stage stays None, not 0
            ps = s.get("ps") or []
            a = s.get("p0") or s["t0"] or s["t1"]
            d = sum(p["b"] - p["a"] for p in ps) + max(0.0, s["t1"] - a)
            short = s.get("k", 1) > len(ps) + 1
            lb = lb or short   # dropped passes (hook keeps PS_MAX): the sum is a lower bound
            tot += d
            rows.append(_row("gate", title, a, d))
    return (tot if seen else None), lb, rows


def _signals(got, stops, pol):
    """{sid8: [(time, by, pipeline or "")]} skips per session + stops; policy-off applies to every session (key "")."""
    sig = {}
    for r in got:
        for title, s in r["st"].items():
            if s["s"] == "skip" and s["t0"]:
                sig.setdefault(r["sid8"], []).append((s["t0"], "skip", ""))
    for x in stops if isinstance(stops, list) else ():
        if isinstance(x, dict) and isinstance(x.get("sid8"), str) and pl_runs._num(x.get("at")):
            sig.setdefault(x["sid8"], []).append((pl_runs._num(x["at"]), "stop", str(x.get("pipeline") or "")))
    if pol:
        sig.setdefault("", []).append((pol, "strict_off", ""))
    return sig


def _hook(hook, now):
    v = hook if isinstance(hook, dict) else otel_hooks._oh_view(ymd(now - harness_flow.HF_KEEP_S), top=otel_hooks.OH_CAP)
    rows = [x for x in (v.get("rows") or []) if isinstance(x, dict)]
    if not v.get("n"):
        return None, []
    ms = sum(int(x.get("ms") or 0) for x in rows)
    return ms, [{"code": str(x.get("ev") or "")[:40], "stage": "", "ts": None, "dur_ms": int(x.get("ms") or 0), "by": ""}
                for x in rows[:HC_EV_MAX]]


def cost(proj, runs=None, stops=None, hook=None, policy=None, gates=None):
    """{period_s, blocked, overridden, unknown, gate_ms, gate_lb, hook_ms, pause_ms, ev: {blocked, overridden, unknown, gate,
    pause, hook: [{code, stage, ts, dur_ms, by}] ≤ HC_EV_MAX newest first}}. Counts are None when no run was read.
    `runs`/`stops`/`hook`/`policy`/`gates` ({name: [gate titles]}) replace the disk reads (demo, tests)."""
    now = _now()
    got = harness_flow.runs(proj, runs)
    stops = pl_reqs.stops(now) if stops is None else stops
    pol = _policy(proj) if policy is None else pl_runs._num(policy)
    memo = {}

    def gates_of(n):
        if gates is not None:
            g = gates.get(n) if isinstance(gates, dict) else None
            return set(g) if isinstance(g, (list, set, tuple)) else None
        if n not in memo:
            memo[n] = _gates(proj, n)
        return memo[n]
    sig = _signals(got, stops, pol)
    ev = {"blocked": [], "overridden": [], "unknown": [], "pause": []}
    pause, timed, nb, no, nu = 0.0, False, 0, 0, 0
    for r in got:
        iv = []
        for e in r["dl"]:
            t, rt = e["ts"], e.get("rt")
            hits = sorted((x for x in sig.get(r["sid8"], []) + sig.get("", [])
                           if t < x[0] <= t + HC_WIN_S and (x[1] != "stop" or x[2] == r["name"])))
            dur = (rt - t) if rt else None
            nb += 1
            if hits:
                by, no = hits[0][1], no + 1
                ev["overridden"].append(_row(e["code"], e["title"], t, dur, by))
            elif rt and now - t > HC_WIN_S:
                by = ""   # complied
            else:
                by, nu = ("pending" if now - t <= HC_WIN_S else "none"), nu + 1
                ev["unknown"].append(_row(e["code"], e["title"], t, dur, by))
            ev["blocked"].append(_row(e["code"], e["title"], t, dur, by))
            if rt:
                iv.append((t, rt))
                ev["pause"].append(_row(e["code"], e["title"], t, dur, by))
        if iv:
            timed = True
            pause += _union_s(iv)
    gate_s, gate_lb, ev["gate"] = _gate_time(got, gates_of)
    hook_ms, ev["hook"] = _hook(hook, now)
    for k in ("blocked", "overridden", "unknown", "pause", "gate"):
        ev[k] = sorted(ev[k], key=lambda x: -(x["ts"] or 0))[:HC_EV_MAX]
    has = bool(got)
    return {"period_s": harness_flow.HF_KEEP_S,
            "blocked": nb if has else None, "overridden": no if has else None, "unknown": nu if has else None,
            "gate_ms": None if gate_s is None else int(round(gate_s * 1000)), "gate_lb": gate_lb,
            "hook_ms": hook_ms, "pause_ms": int(round(pause * 1000)) if timed else None, "ev": ev}
