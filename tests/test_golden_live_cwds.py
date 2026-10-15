"""Golden output for `live_cwds` on fixed inputs (guards behaviour-preserving splits).

Every dependency is replaced on sidereus.live (clock, ps snapshot, lsof, agent_view, sid probes, warn/stale
hooks), so no live process, file or clock is touched. Each scenario records the return value, the ordered
trace of dependency calls (with the fake clock reading) and the shared state it leaves behind
(_live_cache, _live_sids, _live_pid_cwd). Regenerate only for an intended change:
    GOLDEN_UPDATE=1 /usr/bin/python3 -m unittest tests.test_golden_live_cwds
"""
import json
import os
import subprocess
import unittest

from tests._load import sidereus

lv = sidereus("live")

GOLD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden")
T0 = 1_790_000_000.0

A = "aa11aa11-0000-4000-8000-000000000001"
B = "bb22bb22-0000-4000-8000-000000000002"
C = "cc33cc33-0000-4000-8000-000000000003"
D = "dd44dd44-0000-4000-8000-000000000004"
E = "ee55ee55-0000-4000-8000-000000000005"


def _lsof(pmap):
    return "".join("p%s\nfcwd\nn%s\n" % (p, c) for p, c in pmap.items())


def _base():
    """Official 101 (A), argv-resumed 102 (B), bare 103/104 sharing a path, fork ghost 106 (C -> D)."""
    snap = [("101", "1", "claude"), ("102", "1", "/usr/local/bin/claude --resume " + B),
            ("103", "1", "claude"), ("104", "1", "claude --model opus"),
            ("105", "1", "zsh -c ls"), ("106", "1", "claude --resume " + C),
            ("107", "1", "claude --session-id %s --fork-session --resume /p/%s.jsonl" % (D, C)),
            ("108", "1", "")]
    pmap = {"101": "/w/a", "102": "/w/b", "103": "/w/c", "104": "/w/c", "106": "/w/d", "107": "/w/d"}
    return {"snap": snap, "lsof": _lsof(pmap), "av": {"101": {"sessionId": A}, "107": {"sessionId": D}},
            "tx": {A, B, C, D}, "stale": set(), "mac": True, "cache": (0.0, set())}


def _scenarios():
    s = {}
    s["base"] = _base()
    d = _base(); d["tx"] = set(); s["gone_transcripts"] = d          # official sids with no transcript
    d = _base(); d["av"] = None; s["no_official"] = d
    d = _base(); d["av"] = {}; s["empty_official"] = d
    d = _base(); d["av"] = {"101": "junk", "107": {"sessionId": ""}, "999": {"sessionId": E}}; s["official_junk"] = d
    d = _base(); d["stale"] = {B, C}; s["stale_labels"] = d
    d = _base(); d["stale"] = "raise"; s["argv_phase_raises"] = d
    d = _base(); d["snap"] = [x for x in d["snap"] if x[0] != "107"]; d["av"] = {"101": {"sessionId": A}}
    s["no_fork_successor"] = d
    d = _base(); d["snap"] = []; s["empty_snap"] = d
    d = _base(); d["snap"] = [("105", "1", "zsh"), ("108", "1", "  ")]; s["no_claude"] = d
    d = _base(); d["lsof"] = ""; s["lsof_empty"] = d
    d = _base(); d["lsof"] = "n/orphan\np101\nn/w/a\np102\nx\np\nn/w/z\n"; s["lsof_odd"] = d
    d = _base(); d["mac"] = False; s["non_mac"] = d
    d = _base(); d["lsof"] = "raise"; d["cache"] = (T0 - 5, {"/old": 2}); s["fail_fresh_prev"] = d
    d = _base(); d["lsof"] = "raise"; d["cache"] = (T0 - 500, {"/old": 2}); s["fail_old_prev"] = d
    d = _base(); d["lsof"] = "raise"; d["cache"] = (T0 - 5, None); s["fail_prev_none"] = d
    d = _base(); d["cache"] = (T0 - 1, {"/hit": 1}); s["ttl_hit"] = d
    d = _base(); d["snap"] = "raise"; s["snap_raises"] = d
    d = _base(); d["snap"] = [("%d" % (200 + i), "1", "claude") for i in range(70)]
    d["lsof"] = _lsof({"%d" % (200 + i): "/w/m%d" % (i % 3) for i in range(70)}); d["av"] = {}
    s["over_64"] = d
    return s


def run(sc):
    """Run live_cwds once under scenario `sc`; return (result, trace, state)."""
    trace = []
    clock = [T0]

    class _T:
        @staticmethod
        def time():
            clock[0] += 0.5
            trace.append(["time", clock[0]])
            return clock[0]

    class _R:
        def __init__(self, out):
            self.stdout = out

    class _SP:
        @staticmethod
        def run(argv, **kw):
            trace.append(["subprocess.run", argv, sorted(kw.items())])
            if sc["lsof"] == "raise":
                raise subprocess.TimeoutExpired(argv, 4)
            return _R(sc["lsof"])

    def ps_snap():
        trace.append(["_ps_snap"])
        if sc["snap"] == "raise":
            raise RuntimeError("ps")
        return list(sc["snap"])

    def agent_view():
        trace.append(["agent_view"])
        return sc["av"]

    def sid_tx(sid):
        trace.append(["_sid_transcript", sid])
        return ("/p/%s.jsonl" % sid) if sid in sc["tx"] else None

    def claim_stale(sid, cwd=None):
        trace.append(["_sid_claim_stale", sid, cwd])
        if sc["stale"] == "raise":
            raise ValueError("boom")
        return sid in sc["stale"]

    def warn(key, msg, soft=False, vars=None, more=None):
        trace.append(["warn_once", key, msg, soft, vars, more])

    fakes = {"time": _T, "subprocess": _SP, "IS_MAC": sc["mac"], "_ps_snap": ps_snap, "agent_view": agent_view,
             "_sid_transcript": sid_tx, "_sid_claim_stale": claim_stale, "warn_once": warn,
             "_slow_why": lambda: [{"msg": "why"}],
             "_stale_clear": lambda k: trace.append(["_stale_clear", k]),
             "_stale_mark": lambda k, at: trace.append(["_stale_mark", k, at]),
             "_live_cache": sc["cache"]}
    saved = {k: getattr(lv, k) for k in fakes}
    sids0, pcwd0 = list(lv._live_sids), list(lv._live_pid_cwd)
    lv._live_sids[:] = [-1.0, {"prev"}]
    lv._live_pid_cwd[:] = [-1.0, {"prev": "/prev"}]
    try:
        for k, v in fakes.items():
            setattr(lv, k, v)
        res = lv.live_cwds()
        cache = lv._live_cache
        state = {"cache_at": cache[0], "cache_is_res": cache[1] is res, "cache": _j(cache[1]),
                 "live_sids": [lv._live_sids[0], _j(lv._live_sids[1])],
                 "live_pid_cwd": [lv._live_pid_cwd[0], _j(lv._live_pid_cwd[1])]}
    finally:
        for k, v in saved.items():
            setattr(lv, k, v)
        lv._live_sids[:] = sids0
        lv._live_pid_cwd[:] = pcwd0
    return {"result": _j(res), "type": type(res).__name__, "trace": _j(trace), "state": state}


def _j(v):
    """JSON-safe, order-preserving for dicts/lists, sorted for sets."""
    if isinstance(v, set):
        return {"set": sorted(v)}
    if isinstance(v, dict):
        return {"dict": [[k, _j(x)] for k, x in v.items()]}
    if isinstance(v, (list, tuple)):
        return [_j(x) for x in v]
    return v


def capture():
    return {name: run(sc) for name, sc in _scenarios().items()}


class GoldenLiveCwds(unittest.TestCase):
    def test_golden(self):
        text = json.dumps(capture(), sort_keys=True, ensure_ascii=False, indent=1) + "\n"
        path = os.path.join(GOLD, "live_cwds.json")
        if os.environ.get("GOLDEN_UPDATE") == "1":
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        with open(path, encoding="utf-8") as f:
            self.assertEqual(text, f.read())


if __name__ == "__main__":
    unittest.main()
