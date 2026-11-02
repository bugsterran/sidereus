"""hooks/pl_flow.py ledger `ss` (R1 per-stage outcome/seconds/dispatches, R2 per-stage subagent tokens). Tmp dirs only."""
import json
import os
import time
import unittest
from unittest import mock

from tests import test_pl_flow as F   # ⚠not `from … import Flow`: its tests would run again here
from tests import test_pl_flow_ledger as L
from tests._load import sidereus  # noqa: F401  (package bootstrap)

H = F.H
_Base = type("_Base", (L.Ledger,), {k: None for k in dir(L.Ledger) if k.startswith("test")})   # helpers only


def _line(mid, rid, i=10, o=5, cc=3, cr=100, ts="2026-11-01T00:00:00.000Z"):
    return json.dumps({"type": "assistant", "requestId": rid, "timestamp": ts,
                       "message": {"id": mid, "model": "claude-opus-4", "content": [{"type": "text", "text": "body"}],
                                   "usage": {"input_tokens": i, "output_tokens": o, "cache_creation_input_tokens": cc,
                                             "cache_read_input_tokens": cr}}}) + "\n"


class Tokens(_Base):
    def setUp(self):
        super().setUp()
        self.sess = os.path.join(self.tmp, "projects", "p", "sess-0001")
        self.subs = os.path.join(self.sess, "subagents")
        os.makedirs(self.subs)
        self.tp = self.sess + ".jsonl"
        p = mock.patch.object(H, "_TP", [self.tp])
        p.start()
        self.addCleanup(p.stop)

    def agent(self, aid, desc, lines, mt=1050.0):
        with open(os.path.join(self.subs, "agent-%s.jsonl" % aid), "w", encoding="utf-8") as f:
            f.writelines(lines)
        mp = os.path.join(self.subs, "agent-%s.meta.json" % aid)
        with open(mp, "w", encoding="utf-8") as f:
            json.dump({"agentType": "x", "description": desc, "toolUseId": "tu-" + aid}, f)
        os.utime(mp, (mt, mt))

    def run_(self, st=None):
        return {"proj": self.proj, "t0": 1000.0, "lb": [],
                "st": st or {"설계": {"s": "done", "t0": 1000.0, "t1": 1060.0, "n": 1}}}

    def ss(self, st=None, now=1100.0):
        H._ledger_add(self.run_(st), F.N, now)
        rows = self.rows()
        if os.path.exists(self.lf):
            os.remove(self.lf)   # the ledger dedupes (name, t0): each call starts empty
        return rows[-1]["ss"]

    def test_r2_tagged_stage_summed_other_run_and_window_excluded(self):
        """R2: only this run's name and meta mtime in [t0, now] count."""
        self.agent("a1", "[pl:%s/설계] x" % F.N, [_line("m1", "r1")])
        self.agent("a2", "[pl:other-pipe/설계] x", [_line("m2", "r2")])
        self.agent("a3", "[pl:%s/설계] x" % F.N, [_line("m3", "r3")], mt=900.0)    # before t0
        self.agent("a4", "[pl:%s/설계] x" % F.N, [_line("m4", "r4")], mt=1200.0)   # after now
        self.assertEqual(self.ss()["설계"]["tok"], 118)

    def test_r2_duplicate_ids_counted_once(self):
        self.agent("a1", "[pl:%s/설계] x" % F.N, [_line("m1", "r1"), _line("m1", "r1"), _line("m2", "r1")])
        self.agent("a2", "[pl:%s/설계] y" % F.N, [_line("m1", "r1")])
        self.assertEqual(self.ss()["설계"]["tok"], 236)

    def test_r2_main_only_stage_is_null(self):
        self.agent("a1", "[pl:%s/설계] x" % F.N, [_line("m1", "r1")])
        self.assertIsNone(self.ss({"설계": {"s": "done", "t0": 1000.0, "t1": 1060.0, "n": 0, "m": True}})["설계"]["tok"])

    def test_r2_missing_transcript_is_null_never_zero(self):
        with mock.patch.object(H, "_TP", []):
            self.assertIsNone(self.ss()["설계"]["tok"])
        os.rmdir(self.subs)
        self.assertIsNone(self.ss(now=1101.0)["설계"]["tok"])
        os.makedirs(self.subs)
        self.assertIsNone(self.ss(now=1102.0)["설계"]["tok"])   # no matching agent

    def test_r2_budget_overrun_null_row_still_written(self):
        self.agent("a1", "[pl:%s/설계] x" % F.N, [_line("m1", "r1")])
        ticks = iter([0.0, 0.0, 10.0, 10.0, 10.0])
        with mock.patch.object(H, "_mono", lambda: next(ticks, 10.0)):
            H._ledger_add(self.run_(), F.N, 1100.0)
        rows_written = self.rows()
        ss = rows_written[-1]["ss"]
        self.assertIsNone(ss["설계"]["tok"])
        self.assertEqual(len(rows_written), 1)

    def test_r2_broken_jsonl_still_writes_row(self):
        self.agent("a1", "[pl:%s/설계] x" % F.N, ['{"usage": broken\n', _line("m1", "r1"), b"\xff\xfe\"usage\"\n".decode("latin-1")])
        with open(os.path.join(self.subs, "agent-a2.meta.json"), "w") as f:
            f.write("{not json")
        os.utime(os.path.join(self.subs, "agent-a2.meta.json"), (1050.0, 1050.0))
        self.assertEqual(self.ss()["설계"]["tok"], 118)
        with mock.patch.object(H, "_stage_tokens", mock.Mock(side_effect=RuntimeError)):
            self.assertIsNone(self.ss(now=1101.0)["설계"]["tok"])   # row still written (ss() reads it)

    def test_r2_equals_usage_index_scan(self):
        """R2: same total as sidereus.usage_index._uidx_scan on the same file."""
        import importlib
        ui = importlib.import_module("sidereus.usage_index")
        lines = [_line("m%d" % i, "r%d" % i, i, 2 * i, 3 * i, 4 * i) for i in range(1, 6)] + [_line("m1", "r1")]
        lines.append(json.dumps({"requestId": "r9", "timestamp": "2026-11-01T01:00:00.000Z", "message": {
            "id": "m9", "model": "claude-opus-4", "usage": {"input_tokens": 1, "output_tokens": 1, "cache_creation_input_tokens": 2,
                                                            "cache_creation": {"ephemeral_5m_input_tokens": 3, "ephemeral_1h_input_tokens": 4}}}}) + "\n")
        self.agent("a1", "[pl:%s/설계] x" % F.N, lines)
        ent = {}
        ui._uidx_scan(os.path.join(self.subs, "agent-a1.jsonl"), ent)
        want = sum(sum(v) for hb in ent["h"].values() for v in hb.values())
        self.assertEqual(self.ss()["설계"]["tok"], want)

    def test_r1_stage_states_seconds_dispatches(self):
        """R1: s/sec/n per stage; run -> done; unknown state dropped; skip has no tok; ps passes summed."""
        st = {"설계": {"s": "done", "t0": 1000.0, "t1": 1030.0, "n": 1},
              "구현": {"s": "back", "t0": 1000.0, "p0": 1080.0, "t1": 1090.0, "n": 3,
                     "ps": [{"a": 1030.0, "b": 1050.0, "s": "done"}, {"a": 1060.0, "b": 1065.0, "s": "back"}]},
              "검증": {"s": "fail", "t0": 1090.0, "t1": 1095.0, "n": 1},
              "리뷰": {"s": "skip", "t0": 1095.0, "t1": 1095.0, "n": 0},
              "재검증": {"s": "run", "t0": 1095.0, "t1": 1099.0, "n": 1},
              "라이브 검증": {"s": "weird", "t0": 1.0, "t1": 2.0}}
        ss = self.ss(st)
        self.assertEqual({k: (v["s"], v["sec"], v["n"]) for k, v in ss.items()},
                         {"설계": ("done", 30, 1), "구현": ("back", 35, 3), "검증": ("fail", 5, 1),
                          "리뷰": ("skip", 0, 0), "재검증": ("done", 4, 1)})
        self.assertNotIn("tok", ss["리뷰"])
        self.assertIsNone(ss["검증"]["tok"])

    def test_r1_old_row_without_ss_still_read(self):
        """R1: rows written before `ss` existed still load in the ledger reader."""
        import importlib
        oc = importlib.import_module("sidereus.pl_outcome")
        self.assertEqual(oc._row({"name": F.N, "t0": 1.0, "end": 2.0, "lb": [], "deny": 0, "dc": {}})["name"], F.N)
        self.assertEqual(oc._row(dict({"name": F.N, "t0": 1.0, "end": 2.0}, ss=self.ss()))["name"], F.N)

    def test_r1_cap_32_stages(self):
        st = {"s%02d" % i: {"s": "done", "t0": 1000.0, "t1": 1001.0, "n": 1} for i in range(40)}
        self.assertEqual(len(self.ss(st)), H.SS_MAX)

    def test_r4_no_content_stored(self):
        self.agent("a1", "[pl:%s/설계] secret task" % F.N, [_line("m1", "r1")])
        H._ledger_add(self.run_(), F.N, 1100.0)
        with open(self.lf, encoding="utf-8") as f:
            raw = f.read()
        for w in ("secret", "body", "m1", "r1"):
            self.assertNotIn(w, raw)

    def test_r4_end_to_end_time_8x2mb(self):
        """R4: added hook time for 8 agents x 2 MB transcripts stays inside TOK_BUDGET_S (synthetic, tmp only)."""
        pad = "x" * 1800
        for a in range(8):
            ls, n = [], 0
            while n < 2 * 1024 * 1024:
                ls.append(_line("m%d-%d" % (a, n), "r%d-%d" % (a, n)).replace('"body"', '"%s"' % pad))
                n += len(ls[-1])
            self.agent("g%d" % a, "[pl:%s/설계] x" % F.N, ls)
        t = time.perf_counter()
        with mock.patch.object(H, "TOK_BUDGET_S", 60.0):   # ⚠measures only; a loaded CI box must not flake on the budget
            tok = self.ss()["설계"]["tok"]
        ms = (time.perf_counter() - t) * 1000
        self.assertIsNotNone(tok)
        if os.environ.get("PLF_TOK_MS"):
            print("pl_flow ss 8x2MB: %.0f ms" % ms)


if __name__ == "__main__":
    unittest.main()
