"""Golden output for `quota_burn` and `agents_timeline` on fixed inputs (guards behaviour-preserving splits).

Every source is monkeypatched (clock, quota log points, token events, sessions, file stats, agent meta),
so no live file, clock or network is touched. Expected output lives in tests/golden/*.json and is compared
as `json.dumps(sort_keys=True)` — byte-identical. Regenerate only for an intended change:
    GOLDEN_UPDATE=1 /usr/bin/python3 -m unittest tests.test_golden_burn_timeline
"""
import json
import os
import unittest

from tests._load import sidereus

bu = sidereus("burn")
bw = sidereus("burn_week")
tl = sidereus("timeline")
BW_SHARED = ("quota", "_tok_events", "_qwk_pts")   # burn imports these by name: the 7d side reads its own binding

GOLD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden")
NOW = 1_790_000_000.0


def _canon(v):
    return json.dumps(v, sort_keys=True, ensure_ascii=False, indent=1)


class _Patch:
    """Set module attributes for one test and restore them afterwards."""

    def __init__(self):
        self.saved = []

    def set(self, mod, name, val):
        self.saved.append((mod, name, getattr(mod, name)))
        setattr(mod, name, val)

    def undo(self):
        for mod, name, val in reversed(self.saved):
            setattr(mod, name, val)
        self.saved = []


class _Clock:
    def __init__(self, t):
        self.t = t

    def time(self):
        return self.t


class _Golden(unittest.TestCase):
    name = ""

    def check(self, got):
        path = os.path.join(GOLD, self.name + ".json")
        text = _canon(got)
        if os.environ.get("GOLDEN_UPDATE") == "1":
            os.makedirs(GOLD, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text + "\n")
        with open(path, encoding="utf-8") as f:
            self.assertEqual(text + "\n", f.read())


# ─── quota_burn ──────────────────────────────────────────────────────────────

def _cycle(reset, pcts, step=600):
    """Points of one 5h cycle ending at `reset`: pct values every `step` seconds from the window start."""
    s0 = reset - bu.QBURN_WIN
    return [(int(s0 + i * step), float(p), float(reset)) for i, p in enumerate(pcts)]


def _past(k, scale):
    # a past cycle ending k windows ago, a gently curved ramp scaled per cycle
    return _cycle(NOW + 3600 - k * bu.QBURN_WIN, [round(scale * (i ** 1.2), 1) for i in range(30)])


def _current(pcts, start_off=-4 * 3600, step=600):
    reset = NOW + start_off + bu.QBURN_WIN
    return _cycle(reset, pcts, step)


class QuotaBurnGolden(_Golden):
    name = "quota_burn"

    def setUp(self):
        self.p = _Patch()
        self.p.set(bu, "time", _Clock(NOW))
        self.lim_set = []
        self.p.set(bu, "_qb_lim_set", lambda lim, at, *_a: self.lim_set.append((lim, at)))
        self.p.set(bu, "_qb_lim_load", lambda: None)
        self.p.set(bu, "_qb_lim", {"lim": 0.0, "at": 0.0, "loaded": True})
        self.p.set(bu, "_qburn", {"pos": None, "pts": [], "at": 0, "out": None})
        self.p.set(bu, "_anchors", lambda: {"blockLimitTokens": 519164200})
        self.p.set(bw, "usage", lambda: {"week": {"tokens": 90_000_000}})
        self.p.set(bu, "quota", lambda: {"seven_day": {"pct": 30.0, "leftSec": 86400}})
        self.p.set(bu, "_tok_events", lambda since: [(since + 60 * i, 1_000_000 + 7_000 * i) for i in range(200)])
        self.p.set(bu, "_qwk_pts", lambda: [])
        for k in BW_SHARED:
            self.p.set(bw, k, getattr(bu, k))
        self.p.set(bu, "_qburn_pts", lambda: [])
        self.p.set(bu, "burn_est", lambda out, acct: None)   # never the live history pass (sidereus/burn_hist.py)

    def tearDown(self):
        self.p.undo()

    def run_case(self, pts=None, qwk=None, exc=None, **patch):
        bu._qburn.update({"pos": None, "pts": [], "at": 0, "out": None})
        if exc:
            def boom():
                raise exc
            bu._qburn_pts = boom
        else:
            bu._qburn_pts = lambda: list(pts)
        if qwk is not None:
            bu._qwk_pts = bw._qwk_pts = lambda: list(qwk)
        for k, v in patch.items():
            setattr(bu, k, v)
            if k in BW_SHARED:
                setattr(bw, k, v)
        return bu.quota_burn()

    def test_golden(self):
        out = {}
        pasts = [pt for k in range(1, 8) for pt in _past(k, 0.8 + 0.15 * k)]
        cur = _current([2 * i for i in range(25)])                     # 4h in, rising to 48%
        # A: full window back-computation, weekly reset detected (`cyc`)
        qwk_cyc = [(NOW - 5 * 86400 + 3600 * i, float(min(80, i))) for i in range(40)] + \
                  [(NOW - 3 * 86400 + 3600 * i, float(i)) for i in range(31)]
        out["A_full_cyc"] = self.run_case(pasts + cur, qwk=qwk_cyc)
        out["A_lim_set"] = list(self.lim_set)
        # A2: TTL cache hit returns the same object without recomputing
        bu._qburn_pts = lambda: []
        out["A2_cached_same"] = bu.quota_burn() is bu._qburn["out"]
        # B: warm-up (15 min into the window) -> last success reused; weekly `step`
        bu._qb_lim.update({"lim": 150_000_000.0, "at": NOW - 600})
        warm = _current([0.0, 3.0, 5.0], start_off=-900, step=300)
        qwk_step = [(NOW - 6 * 86400 + 1800 * i, float(i // 2)) for i in range(60)]
        out["B_warm_recent_step"] = self.run_case(pasts + warm, qwk=qwk_step)
        # C: no recent success -> anchor; weekly calendar-week fallback; few past cycles (band "n")
        bu._qb_lim.update({"lim": 0.0, "at": 0.0})
        out["C_anchor_week"] = self.run_case(_past(1, 1.0) + _past(2, 1.1) + warm, qwk=[])
        # D: flat past cycles (band "flat"), current at 100% (over_at = last point)
        flat = [pt for k in range(1, 7) for pt in _cycle(NOW + 3600 - k * bu.QBURN_WIN, [0.0] * 30)]
        out["D_flat_full"] = self.run_case(flat + _current([10 * i for i in range(11)] + [100.0] * 5))
        # E: wide past cycles (band "wide")
        wide = [pt for k in range(1, 7) for pt in
                _cycle(NOW + 3600 - k * bu.QBURN_WIN, [(95.0 if k % 2 else 1.0) * i / 29 for i in range(30)])]
        out["E_wide"] = self.run_case(wide + cur)
        # F: a single recent point -> no forecast (n_obs < 2)
        out["F_one_point"] = self.run_case(pasts + _current([0.0], start_off=-4000))
        # G: stale cycle, no data, source failure, 7d missing
        out["G_stale"] = self.run_case(_cycle(NOW - 100, [5.0, 6.0]))
        out["G_nodata"] = self.run_case([])
        out["G_error"] = self.run_case(exc=ValueError("bad log"))
        out["G_no7d"] = self.run_case(pasts + cur, quota=lambda: {})
        # H: token source raising inside the head block -> falls through to the anchor
        def tok_boom(since):
            raise OSError("gone")
        out["H_tok_error"] = self.run_case(pasts + cur, _tok_events=tok_boom, _qwk_pts=lambda: [])
        self.check(out)


# ─── agents_timeline ─────────────────────────────────────────────────────────

class _Stat:
    def __init__(self, mtime, born):
        self.st_mtime, self.st_ctime, self.st_birthtime = mtime, born - 5, born


class _FakePath:
    def __init__(self, files):
        self.files = files

    def exists(self, p):
        return p in self.files

    basename = staticmethod(os.path.basename)
    join = staticmethod(os.path.join)


class _FakeOS:
    def __init__(self, files):
        self.files = files
        self.path = _FakePath(files)

    def stat(self, p):
        if p not in self.files:
            raise OSError(p)
        return _Stat(*self.files[p])


class AgentsTimelineGolden(_Golden):
    name = "agents_timeline"

    def setUp(self):
        self.p = _Patch()
        H = 3600
        F = {}
        meta = {}
        # two projects, three transcripts; agents with lineage, a duplicate tid, a resumed live agent, a stale one
        for i, (sd, n) in enumerate((("/p/a/s1", 4), ("/p/a/s0", 2), ("/p/b/s2", 3))):
            F[sd + ".jsonl"] = (NOW - 60 * (i + 1), NOW - 8 * H + i * 600)
            m = {}
            for j in range(n):
                f = "%s/subagents/agent-a%d%d.jsonl" % (sd, i, j)
                F[f] = (NOW - 400 * j - 90 * i, NOW - 3 * H + 700 * j + 50 * i)
                m["toolu_%d%d" % (i, j)] = {"_file": f, "_id": "a%d%d" % (i, j), "agentType": "t%d" % j,
                                            "description": "job %d-%d " % (i, j) * 6,
                                            "parentAgentId": ("a%d0" % i) if j else "", "spawnDepth": 2 if j else 1}
            meta[sd] = m
        meta["/p/b/s2"]["toolu_00"] = meta["/p/a/s1"]["toolu_00"]            # same tid twice -> dedup
        F["/p/a/s1/subagents/agent-old.jsonl"] = (NOW - 20 * H, NOW - 21 * H)  # before the cut
        meta["/p/a/s1"]["toolu_old"] = {"_file": "/p/a/s1/subagents/agent-old.jsonl", "_id": "old"}
        meta["/p/a/s1"]["toolu_gone"] = {"_file": "/p/a/s1/subagents/missing.jsonl", "_id": "gone"}
        rows = [{"cwd": "/w/a", "project": "a", "sid": "s1", "task": "build the thing", "state": "tool",
                 "ageSec": 3, "blocked": "", "tool": "Bash", "targ": "make",
                 "sub": [{"tid": "toolu_01"}, {"aid": "a02", "tid": "toolu_resume"}]},
                {"cwd": "/w/b", "project": "b", "sid": "s9", "state": "idle", "sub": []}]
        pick = [("/w/a", "a", ["/p/a/s1.jsonl", "/p/a/s0.jsonl"], "/p/a/s1.jsonl"),
                ("/w/b", "b", ["/p/b/s2.jsonl"], "/p/b/s2.jsonl")]

        def segs(fp, cut, nb=0, lim=0, tok_out=None):
            mt, born = F[fp]
            a = max(cut, born)
            pieces = [(a, a + (mt - a) * 0.3), (a + (mt - a) * 0.5, mt)]
            if tok_out is not None:
                for k in range(6):
                    tok_out.append((a + (mt - a) * k / 5.0, 1000 * (k + 1) + len(fp)))
                tok_out.append((a - 30, 7))                                   # before the first piece
            return pieces, a - 100

        self.p.set(tl, "time", _Clock(NOW))
        self.p.set(tl, "os", _FakeOS(F))
        self.p.set(tl, "sessions_rows", lambda **k: rows)
        self.p.set(tl, "_tl_pick", lambda cut, rows=None: pick)
        self.p.set(tl, "_agent_meta", lambda sd, ttl=0: meta.get(sd, {}))
        self.p.set(tl, "_agent_last", lambda f: ("Read " + f) * 3)
        self.p.set(tl, "_agent_tools", lambda f: len(f) % 7)
        self.p.set(tl, "_agent_fin", lambda f: f.endswith("0.jsonl"))
        self.p.set(tl, "_sess_segments", segs)
        self.p.set(tl, "_compacts", lambda fp, cut: [[int(cut) + 999, "auto"]])
        self.p.set(tl, "naps", lambda hours: [[int(NOW - 5 * H), int(NOW - 4 * H)], [int(NOW - 2 * H), int(NOW - 2 * H + 900)]])
        self.p.set(tl, "_plat_tl_rows", lambda cut, now, pcwd=None: [])                # ext CLI rows: test_timeline_gemini, test_codex
        self.p.set(tl.claude_roots, "acct_of", lambda sid, fp: ("", ""))             # never read live roots / acct records

    def tearDown(self):
        self.p.undo()

    def test_golden(self):
        out = {"h12": tl.agents_timeline(12), "h_clamp_low": tl.agents_timeline(0.1),
               "h_clamp_high": tl.agents_timeline(999)}
        self.p.set(tl, "TL_ROW_MAX", 5)                                        # row cap: sessions kept, agents cut
        out["capped"] = tl.agents_timeline(12)
        self.check(out)


if __name__ == "__main__":
    unittest.main()
