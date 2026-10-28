"""sidereus/pl_runs.py: plmark/<sid>.runs.json -> row `plrun` (allow-list, cap, stale/bad input). Tmp dir, fixed clock."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

PR = sidereus("pl_runs")
SID = "sess-0001"
NOW = 1_000_000.0


class PlRuns(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        p = mock.patch.object(PR, "PLR_DIR", self.tmp)
        p.start()
        self.addCleanup(p.stop)

    def _write(self, d, sid=SID, mtime=NOW):
        fp = os.path.join(self.tmp, sid + ".runs.json")
        with open(fp, "w", encoding="utf-8") as f:
            f.write(d if isinstance(d, str) else json.dumps(d))
        os.utime(fp, (mtime, mtime))

    def _run(self, t1, **kw):
        r = {"cwd": "/secret", "proj": "/secret", "t0": t1 - 50, "t1": t1, "cur": "구현", "done": ["설계"],
             "inflight": {"구현": 1}, "ret": "msg", "loops": {"리뷰": 1}, "skipok": [], "end": 0,
             "st": {"설계": {"s": "done", "t0": t1 - 50, "t1": t1 - 20, "n": 1, "x": "body"},
                    "리뷰": {"s": "skip", "t0": t1 - 10, "t1": t1 - 10, "n": 0},
                    "리뷰2": {"s": "back", "t0": t1 - 10, "t1": t1 - 5, "n": 1},
                    "구현": {"s": "run", "t0": t1 - 20, "t1": t1, "n": 2},
                    "검증": {"s": "bogus", "t0": 1, "t1": 2, "n": 1}}}
        r.update(kw)
        return r

    def test_allow_list(self):
        self._write({"v": 1, "runs": {"sidereus-change": self._run(NOW - 5)}})
        out = PR.pl_runs_of(SID, NOW)
        self.assertEqual(len(out), 1)
        r = out[0]
        self.assertEqual(set(r), {"name", "cur", "end", "t0", "t1", "st", "lb", "stop", "fin"})
        self.assertEqual(r["lb"], [])   # missing lb -> []; loops/ret never reach a row
        self.assertEqual(r["name"], "sidereus-change")
        self.assertEqual(r["cur"], "구현")
        self.assertEqual(set(r["st"]), {"설계", "리뷰", "리뷰2", "구현"})   # unknown state dropped
        self.assertEqual(r["st"]["설계"], {"s": "done", "t0": NOW - 55, "t1": NOW - 25, "n": 1})
        self.assertNotIn("/secret", json.dumps(out, ensure_ascii=False))
        self.assertNotIn("msg", json.dumps(out, ensure_ascii=False))

    def test_loopbacks(self):
        good = {"f": "검증", "g": "구현", "n": 2, "t": NOW - 1, "x": "body"}
        bad = [{"f": 1, "g": "구현", "n": 1}, {"f": "검증", "g": None, "n": 1}, {"f": "a", "g": "b", "n": -1},
               {"f": "a", "g": "b", "n": True}, {"f": "a", "g": "b", "n": 0}, "x", {"f": "a", "g": "b", "n": 1.5}]
        lb = [good] + bad + [{"f": "p%d" % i, "g": "q", "n": 1, "t": "x"} for i in range(40)]
        self._write({"v": 1, "runs": {"sidereus-change": self._run(NOW - 5, lb=lb)}})
        out = PR.pl_runs_of(SID, NOW)[0]["lb"]
        self.assertEqual(out[0], {"f": "검증", "g": "구현", "n": 2, "t": NOW - 1})   # extra key dropped
        self.assertEqual(len(out), 1 + PR.PLR_STAGES_MAX - 1 - len(bad))   # entries beyond 32 dropped
        self.assertEqual(out[-1], {"f": "p%d" % (PR.PLR_STAGES_MAX - 2 - len(bad)), "g": "q", "n": 1, "t": 0.0})
        self._write({"v": 1, "runs": {"sidereus-change": self._run(NOW - 5, lb={"f": "a"})}})
        self.assertEqual(PR.pl_runs_of(SID, NOW)[0]["lb"], [])
        self._write({"v": 1, "runs": {"sidereus-change": self._run(NOW - 5, lb=[{"f": "x" * 100, "g": "y", "n": 1}])}})
        self.assertEqual(PR.pl_runs_of(SID, NOW)[0]["lb"][0]["f"], "x" * PR.PLR_TITLE_MAX)

    def test_bad_input(self):
        self.assertEqual(PR.pl_runs_of("../etc", NOW), [])
        self.assertEqual(PR.pl_runs_of("", NOW), [])
        self.assertEqual(PR.pl_runs_of(SID, NOW), [])   # missing file
        self._write("{not json")
        self.assertEqual(PR.pl_runs_of(SID, NOW), [])
        self._write({"v": 1, "runs": ["x"]})
        self.assertEqual(PR.pl_runs_of(SID, NOW), [])
        self._write({"v": 1, "runs": {"Bad Name": self._run(NOW), "ok": "nope"}})
        self.assertEqual(PR.pl_runs_of(SID, NOW), [])

    def test_stop_allow_listed_and_closes_run(self):
        # R2: hooks/pl_guard.py stamps `stop` on a run stopped from Sidereus; it must never read as running
        self._write({"v": 1, "runs": {"a": self._run(NOW, stop=NOW - 2), "b": self._run(NOW - 1, stop="x"),
                                      "c": self._run(NOW - 2, stop=True)}})
        by = {r["name"]: r for r in PR.pl_runs_of(SID, NOW)}
        self.assertEqual((by["a"]["stop"], by["a"]["end"]), (NOW - 2, NOW - 2))
        self.assertEqual([(by[k]["stop"], by[k]["end"]) for k in "bc"], [(0.0, 0.0), (0.0, 0.0)])   # non-numbers dropped

    def test_old(self):
        self._write({"v": 1, "runs": {"a": self._run(NOW)}}, mtime=NOW - PR.PLR_KEEP_S - 1)
        self.assertEqual(PR.pl_runs_of(SID, NOW), [])   # stale file
        self._write({"v": 1, "runs": {"a": self._run(NOW - PR.PLR_KEEP_S - 1), "b": self._run(NOW)}})
        self.assertEqual([r["name"] for r in PR.pl_runs_of(SID, NOW)], ["b"])   # stale run

    def test_cap_newest_first(self):
        self._write({"v": 1, "runs": {"p%d" % i: self._run(NOW - i) for i in range(12)}})
        out = PR.pl_runs_of(SID, NOW)
        self.assertEqual(len(out), PR.PLR_MAX)
        self.assertEqual([r["name"] for r in out], ["p%d" % i for i in range(8)])


class AgByName(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.sd = os.path.join(self.tmp, "sess")
        os.makedirs(os.path.join(self.sd, "subagents"))
        self.meta = {}
        self.sig = [0]   # stands in for subagents/ mtime; bumped whenever an agent is added
        for k, v in (("PLR_DIR", self.tmp), ("_agent_meta", lambda sd: self.meta), ("_subs_mt", lambda sd: self.sig[0]),
                     ("_PLR_AG_MEMO", PR.BoundedMemo(8))):
            p = mock.patch.object(PR, k, v)
            p.start()
            self.addCleanup(p.stop)

    def _ag(self, aid, desc, mt, typ="sidereus-implementer", jsonl=True, **extra):
        base = os.path.join(self.sd, "subagents", "agent-" + aid)
        with open(base + ".meta.json", "w", encoding="utf-8") as f:
            f.write("{}")
        os.utime(base + ".meta.json", (mt, mt))
        if jsonl:
            with open(base + ".jsonl", "w", encoding="utf-8") as f:
                f.write('{"message": "secret body"}\n')
            os.utime(base + ".jsonl", (mt + 3, mt + 3))
        m = {"toolUseId": "tu_" + aid, "agentType": typ, "description": desc, "_id": aid, "_file": base + ".jsonl"}
        m.update(extra)
        self.meta["tu_" + aid] = m
        self.sig[0] += 1

    def test_match(self):
        self._ag("a1", "[pl:sidereus-change/설계] spec", NOW - 90)
        self._ag("a2", "[pl:other/설계] spec", NOW - 80)
        self._ag("a4", "no tag", NOW - 60)
        by = PR._ag_by_name(self.sd, NOW)
        self.assertEqual(sorted(by), ["other", "sidereus-change"])
        self.assertEqual(by["sidereus-change"], [{"aid": "a1", "tid": "tu_a1", "t": "설계",
                                               "lab": "sidereus-implementer: [pl:sidereus-change/설계] spec", "d": "spec",
                                               "t0": NOW - 90, "t1": NOW - 87}])

    def test_lab_only_type_and_desc(self):
        self._ag("a1", "[pl:sidereus-change/설계] " + "d" * 200, NOW - 50, message="SEND BODY", prompt="PROMPT")
        a = PR._ag_by_name(self.sd, NOW)["sidereus-change"][0]
        self.assertEqual(set(a), {"aid", "tid", "t", "lab", "d", "t0", "t1"})
        self.assertEqual(a["d"], "d" * PR.PLR_LAB_MAX)   # bare description: tag stripped, capped
        self.assertEqual(len(a["lab"]), 120)
        self.assertTrue(a["lab"].startswith("sidereus-implementer: [pl:sidereus-change/설계] d"))
        self.assertNotIn("secret", json.dumps(a, ensure_ascii=False))

    def test_bad_or_missing(self):
        self.meta = {"tu_x": "nope", "tu_y": {"description": 5}, "tu_z": {"description": "[pl:sidereus-change/설계] x"},
                     "tu_w": {"description": "[pl:sidereus-change/설계] x", "_file": os.path.join(self.sd, "gone.jsonl")}}
        self.assertEqual(PR._ag_by_name(self.sd, NOW), {})
        self._ag("a1", "[pl:sidereus-change/설계] nojsonl", NOW - 50, jsonl=False)   # jsonl missing -> t1 = meta mtime
        self.assertEqual(PR._ag_by_name(self.sd, NOW)["sidereus-change"][0]["t1"], NOW - 50)

    def test_memo(self):
        self._ag("a1", "[pl:sidereus-change/설계] x", NOW - 50)
        first = PR._ag_by_name(self.sd, NOW)
        with mock.patch.object(PR.os.path, "getmtime", side_effect=AssertionError("getmtime")) as gm, \
                mock.patch.object(PR, "redact", side_effect=AssertionError("redact")) as rd:
            again = PR._ag_by_name(self.sd, NOW + 1)   # same signature: no rescan
            self.assertEqual((gm.call_count, rd.call_count), (0, 0))
        self.assertEqual(again, first)
        self._ag("a2", "[pl:sidereus-change/구현] y", NOW - 45)   # new agent -> signature changes
        self.assertEqual(len(PR._ag_by_name(self.sd, NOW)["sidereus-change"]), 2)
        self.assertEqual(len(PR._ag_by_name(self.sd, NOW + PR.PLR_AG_TTL_S)["sidereus-change"]), 2)   # TTL bucket rescan


class PlModel(unittest.TestCase):
    """pl_model -> row `plrun`: runs.json + tagged meta + live sub rows + plm marker."""
    setUp, _ag = AgByName.setUp, AgByName._ag   # same fixtures without re-running AgByName's tests

    def _file(self, runs):
        fp = os.path.join(self.tmp, SID + ".runs.json")
        with open(fp, "w", encoding="utf-8") as f:
            json.dump({"v": 1, "runs": runs}, f)
        os.utime(fp, (NOW, NOW))

    def _r(self, t1=NOW, **kw):
        r = {"cwd": "/secret", "proj": "/Users/x/proj", "t0": NOW - 100, "t1": t1, "cur": "구현", "end": 0, "ret": "msg",
             "st": {"설계": {"s": "done", "t0": NOW - 90, "t1": NOW - 60, "n": 2}, "구현": {"s": "done", "t0": NOW - 50, "t1": NOW - 10, "n": 1}},
             "lb": [{"f": "검증", "g": "설계", "n": 1, "t": NOW - 70}]}
        r.update(kw)
        return r

    def test_meta_live_merge(self):
        self._file({"sidereus-change": self._r()})
        self._ag("a1", "[pl:sidereus-change/설계] spec", NOW - 90)
        self._ag("a2", "[pl:sidereus-change/구현] impl", NOW - 50)
        sub = [{"lab": "sidereus-implementer: [pl:sidereus-change/구현] impl", "min": 0, "aid": "a2", "tid": "tu_a2"}]
        out = PR.pl_model(SID, self.sd, sub, None, NOW)
        self.assertEqual(len(out), 1)
        r = out[0]
        self.assertEqual(set(r), {"name", "proj", "sid", "rid", "lab", "cur", "end", "t0", "t1", "stop", "stages", "past"})
        self.assertEqual((r["rid"], r["lab"], r["past"]), (NOW - 100, "spec", []))   # earliest tagged agent in the run
        self.assertEqual((r["proj"], r["sid"]), ("/Users/x/proj", SID))
        s = r["stages"]
        self.assertEqual(set(s["설계"]), {"o", "n", "t0", "t1", "from", "ag"})
        self.assertEqual(s["설계"]["from"], {"검증": 1})   # from lb f->g
        self.assertEqual(s["구현"]["from"], {})
        self.assertEqual(s["설계"]["ag"], [{"aid": "a1", "tid": "tu_a1", "lab": "sidereus-implementer: [pl:sidereus-change/설계] spec",
                                            "run": False, "t0": NOW - 90, "t1": NOW - 87}])
        self.assertEqual([(a["aid"], a["run"]) for a in s["구현"]["ag"]], [("a2", True)])   # live flag
        self.assertEqual((s["설계"]["o"], s["구현"]["o"]), ("done", "run"))
        dump = json.dumps(out, ensure_ascii=False)
        for bad in ("/secret", "msg", "secret body", "_t"):
            self.assertNotIn(bad, dump)

    def test_sub_without_meta_appended(self):
        self._file({"sidereus-change": self._r()})
        sub = [{"lab": "sidereus-reviewer: [pl:sidereus-change/리뷰] look", "min": 2, "aid": "z9", "tid": "tu_z9"},
               {"lab": "sidereus-reviewer: [pl:other/리뷰] x", "min": 1, "aid": "z8"}, {"lab": "no tag", "min": 1}, "junk"]
        s = PR.pl_model(SID, self.sd, sub, None, NOW)[0]["stages"]
        self.assertEqual(s["리뷰"]["o"], "run")
        self.assertEqual(s["리뷰"]["ag"], [{"aid": "z9", "tid": "tu_z9", "lab": "sidereus-reviewer: [pl:sidereus-change/리뷰] look",
                                            "run": True, "t0": NOW - 120, "t1": NOW}])
        self.assertEqual(sum(len(v["ag"]) for v in s.values()), 1)

    def test_synth_stage_starts_at_agent_start(self):
        # A stage made from a live agent starts when the agent did, not at `now` (read «Running · 0s»).
        self._file({"sidereus-change": self._r()})
        sub = [{"lab": "sidereus-reviewer: [pl:sidereus-change/리뷰] look", "min": 7, "aid": "z9", "tid": "tu_z9"}]
        st = PR.pl_model(SID, self.sd, sub, None, NOW)[0]["stages"]["리뷰"]
        self.assertEqual((st["t0"], st["t1"]), (NOW - 420, NOW))

    def test_long_title_one_stage(self):
        long = "긴단계" * 20   # 60 chars: over the old 40 cut, within the tag's 80
        self._file({"sidereus-change": self._r(st={long: {"s": "run", "t0": NOW - 50, "t1": NOW - 10, "n": 1}})})
        self._ag("m1", "[pl:sidereus-change/%s] meta" % long, NOW - 40)
        sub = [{"lab": "sidereus-implementer: [pl:sidereus-change/%s] live" % long, "min": 1, "aid": "z9", "tid": "tu_z9"}]
        s = PR.pl_model(SID, self.sd, sub, None, NOW)[0]["stages"]
        self.assertEqual(list(s), [long])
        self.assertEqual(sorted(a["aid"] for a in s[long]["ag"]), ["m1", "z9"])

    def test_plm_main(self):
        self._file({"sidereus-change": self._r()})
        s = PR.pl_model(SID, self.sd, [], {"name": "sidereus-change", "title": "구현", "age": 30}, NOW)[0]["stages"]
        self.assertEqual(s["구현"]["ag"], [{"aid": "main", "tid": "", "lab": "main", "run": True, "t0": NOW - 30, "t1": NOW}])
        s = PR.pl_model(SID, self.sd, [], {"name": "other", "title": "구현", "age": 30}, NOW)[0]["stages"]
        self.assertEqual(s["구현"]["ag"], [])

    def test_open_bg_keeps_stage_run(self):
        # Turn ended (act idle), main marker expired: an open tagged bg task keeps its stage running; without it, done.
        st = {"구현": {"s": "run", "t0": NOW - 70, "t1": NOW - 60, "n": 1}}
        self._file({"sidereus-change": self._r(st=st, t0=NOW - 300)})   # the bg task started inside the run
        bgs = [{"lab": "[pl:sidereus-change/구현] run gates", "min": 3}, {"lab": "plain bg", "min": 1}]
        s = PR.pl_model(SID, self.sd, [], None, NOW, "idle", (), bgs)[0]["stages"]["구현"]
        self.assertEqual(s["o"], "run")
        self.assertEqual([(a["lab"], a["run"], a["t0"]) for a in s["ag"]], [("[pl:sidereus-change/구현] run gates", True, NOW - 180)])
        s = PR.pl_model(SID, self.sd, [], None, NOW, "idle", (), [])[0]["stages"]["구현"]   # bg ended -> no longer open
        self.assertEqual(s["o"], "done")

    def test_stale_run_closed(self):
        st = {"설계": {"s": "run", "t0": NOW - 90, "t1": NOW - 80, "n": 1}, "구현": {"s": "run", "t0": NOW - 70, "t1": NOW, "n": 2},
              "검증": {"s": "done", "t0": NOW - 60, "t1": NOW - 50, "n": 1}, "라이브 검증": {"s": "run", "t0": NOW - 40, "t1": NOW - 30, "n": 1},
              "리뷰": {"s": "run", "t0": NOW - 45, "t1": NOW - 35, "n": 1}}
        self._file({"sidereus-change": self._r(st=st)})
        sub = [{"lab": "sidereus-reviewer: [pl:sidereus-change/리뷰] look", "min": 1, "aid": "z9"}]   # live fan-out stays run
        s = PR.pl_model(SID, self.sd, sub, None, NOW)[0]["stages"]
        self.assertEqual({k: v["o"] for k, v in s.items()},
                         {"설계": "done", "구현": "run", "검증": "done", "라이브 검증": "back", "리뷰": "run"})
        s = PR.pl_model(SID, self.sd, [], {"name": "sidereus-change", "title": "설계", "age": 5}, NOW)[0]["stages"]
        self.assertEqual((s["설계"]["o"], s["리뷰"]["o"]), ("run", "back"))   # main marker counts as live

    def _cur(self, act, pend=()):
        st = {"구현": {"s": "run", "t0": NOW - 70, "t1": NOW, "n": 0}}
        self._file({"sidereus-change": self._r(st=st)})
        return PR.pl_model(SID, self.sd, [], None, NOW, act, list(pend))[0]["stages"]["구현"]

    def test_act_from_state(self):
        A = PR.pl_act
        self.assertEqual([A("tool"), A("think"), A("unknown"), A("wait"), A("abort"), A("ask"), A("tool", perm=True),
                          A("done"), A("wait", dead=True)], ["run", "run", "run", "idle", "idle", "ask", "perm", "end", "end"])

    def test_cur_busy_stays_run(self):
        self.assertEqual(self._cur("run")["o"], "run")

    def test_cur_blocked_on_person_holds(self):
        for act in ("ask", "perm"):
            s = self._cur(act)
            self.assertEqual((s["o"], s["why"]), ("hold", act))

    def test_cur_idle_done(self):
        s = self._cur("idle")   # Bash-only stage (n=0, no ag) and every agent finished: same answer
        self.assertEqual(s["o"], "done")
        self.assertNotIn("why", s)

    def _quiet(self, age, sub=(), plm=None):
        st = {"구현": {"s": "run", "t0": NOW - age - 100, "t1": NOW - age, "n": 1}}
        self._file({"sidereus-change": self._r(t1=NOW - age, st=st)})
        self._ag("q1", "[pl:sidereus-change/구현] impl", NOW - age - 3)   # finished agent: t1 = jsonl mtime = NOW - age
        return PR.pl_model(SID, self.sd, list(sub), plm, NOW, "run")[0]["stages"]["구현"]

    def test_cur_busy_without_evidence_holds_idle(self):
        s = self._quiet(PR.PLR_STALE_S + 1)
        self.assertEqual((s["o"], s.get("why")), ("hold", "idle"))
        self.assertEqual(self._quiet(PR.PLR_STALE_S - 1)["o"], "run")

    def test_cur_quiet_but_live_stays_run(self):
        sub = [{"lab": "sidereus-implementer: [pl:sidereus-change/구현] impl", "min": 20, "aid": "z9", "tid": "tu_z9"}]
        self.assertEqual(self._quiet(PR.PLR_STALE_S + 1, sub=sub)["o"], "run")
        plm = {"name": "sidereus-change", "title": "구현", "age": 5}
        self.assertEqual(self._quiet(PR.PLR_STALE_S + 1, plm=plm)["o"], "run")

    def test_open_main_tail_lit_then_done(self):
        # pl_flow leaves a main-run last stage open (no end): the marker lights it; marker gone + idle = done
        st = {"리뷰": {"s": "done", "t0": NOW - 90, "t1": NOW - 60, "n": 1},
              "라이브 검증": {"s": "run", "t0": NOW - 50, "t1": NOW - 10, "n": 0, "m": True}}
        self._file({"sidereus-change": self._r(st=st, cur="라이브 검증", tail="라이브 검증")})
        plm = {"name": "sidereus-change", "title": "라이브 검증", "age": 5}
        row = PR.pl_model(SID, self.sd, [], plm, NOW, "idle")[0]
        s = row["stages"]["라이브 검증"]
        self.assertEqual((row["end"], s["o"], [a["aid"] for a in s["ag"]]), (0, "run", ["main"]))
        self.assertEqual(PR.pl_model(SID, self.sd, [], None, NOW, "idle")[0]["stages"]["라이브 검증"]["o"], "done")
        self.assertNotIn("tail", json.dumps(row, ensure_ascii=False))   # hook-only key never reaches a row

    def test_cur_ended_with_pending_agent_holds(self):
        pend = [{"lab": "sidereus-implementer: [pl:sidereus-change/구현] x", "min": 3}, "junk", {"lab": 5}]
        self.assertEqual((self._cur("end", pend)["o"], self._cur("end", pend)["why"]), ("hold", "end"))
        self.assertEqual(self._cur("end", [{"lab": "t: [pl:other/구현] x"}])["o"], "done")

    def test_live_case_idle_session(self):
        # sid 559ad94f shape: prompt wait, sub=[], every stage agent finished.
        feat = {"구현": {"s": "run", "t0": NOW - 90, "t1": NOW - 5, "n": 5}, "검증": {"s": "skip", "t0": NOW - 80, "t1": NOW - 80, "n": 0},
                "리뷰": {"s": "skip", "t0": NOW - 60, "t1": NOW - 60, "n": 1}, "라이브 검증": {"s": "run", "t0": NOW - 50, "t1": NOW - 50, "n": 1}}
        lv = {"배포 확인": {"s": "done", "t0": NOW - 90, "t1": NOW - 80, "n": 1}, "라이브 검증": {"s": "run", "t0": NOW - 80, "t1": NOW - 20, "n": 5},
              "트리아지": {"s": "run", "t0": NOW - 40, "t1": NOW - 40, "n": 1}}
        self._file({"feature": self._r(st=feat, cur="구현", lb=[]), "live-verify": self._r(t1=NOW - 1, st=lv, cur="라이브 검증", lb=[])})
        self._ag("f1", "[pl:feature/구현] x", NOW - 30)
        out = {r["name"]: {k: v["o"] for k, v in r["stages"].items()} for r in PR.pl_model(SID, self.sd, [], None, NOW, "idle")}
        self.assertEqual(out["feature"], {"구현": "done", "검증": "skip", "리뷰": "skip", "라이브 검증": "back"})
        self.assertEqual(out["live-verify"], {"배포 확인": "done", "라이브 검증": "done", "트리아지": "back"})   # after cur in st order

    def test_act_only_for_newest_open_run(self):
        st = {"구현": {"s": "run", "t0": NOW - 70, "t1": NOW - 60, "n": 1}}
        self._file({"new": self._r(st=st, lb=[]), "old": self._r(t1=NOW - 5, st=st, lb=[]),
                    "ended": self._r(t1=NOW - 9, st=st, lb=[], end=NOW - 9)})
        for act in ("run", "ask"):
            out = {r["name"]: r["stages"]["구현"]["o"] for r in PR.pl_model(SID, self.sd, [], None, NOW, act)}
            self.assertEqual(out, {"new": {"run": "run", "ask": "hold"}[act], "old": "done", "ended": "done"})

    def test_busy_skips_newer_ended_run(self):
        st = {"구현": {"s": "run", "t0": NOW - 70, "t1": NOW - 60, "n": 1}}
        self._file({"ended": self._r(st=st, lb=[], end=NOW - 1), "open": self._r(t1=NOW - 30, st=st, lb=[])})
        out = {r["name"]: r["stages"]["구현"]["o"] for r in PR.pl_model(SID, self.sd, [], None, NOW, "run")}
        self.assertEqual(out, {"ended": "done", "open": "run"})

    def test_finished_earlier_stage_without_sub_row_is_done(self):
        st = {"검증": {"s": "run", "t0": NOW - 90, "t1": NOW - 60, "n": 1}, "리뷰": {"s": "run", "t0": NOW - 60, "t1": NOW - 40, "n": 1},
              "라이브 검증": {"s": "run", "t0": NOW - 40, "t1": NOW - 5, "n": 1}}
        self._file({"flow": self._r(st=st, cur="라이브 검증", lb=[])})
        self._ag("v1", "[pl:flow/검증] gate", NOW - 90)
        self._ag("r1", "[pl:flow/리뷰] look", NOW - 60)
        self._ag("l1", "[pl:flow/라이브 검증] check", NOW - 40)
        sub = [{"lab": "checker: [pl:flow/라이브 검증] check", "min": 0, "aid": "l1"}]
        s = PR.pl_model(SID, self.sd, sub, None, NOW, "run")[0]["stages"]
        self.assertEqual({k: v["o"] for k, v in s.items()}, {"검증": "done", "리뷰": "done", "라이브 검증": "run"})

    def test_main_marker_not_attached_to_closed_run(self):
        st = {"구현": {"s": "done", "t0": NOW - 70, "t1": NOW - 10, "n": 1}}
        self._file({"sidereus-change": self._r(st=st, lb=[], end=NOW - 5)})
        s = PR.pl_model(SID, self.sd, [], {"name": "sidereus-change", "title": "구현", "age": 30}, NOW)[0]["stages"]
        self.assertEqual((s["구현"]["o"], s["구현"]["ag"]), ("done", []))
        self._file({"sidereus-change": self._r(st=st, lb=[])})   # control: open run still takes it
        s = PR.pl_model(SID, self.sd, [], {"name": "sidereus-change", "title": "구현", "age": 30}, NOW)[0]["stages"]
        self.assertEqual([a["aid"] for a in s["구현"]["ag"]], ["main"])

    def test_busy_credited_to_run_with_live_agent(self):
        # Two open runs: the newer one's cur stage has only finished agents, the older one has a live tagged agent.
        new = {"수정": {"s": "run", "t0": NOW - 70, "t1": NOW - 10, "n": 2}}
        old = {"회귀": {"s": "run", "t0": NOW - 40, "t1": NOW - 40, "n": 1}}
        self._file({"bugfix": self._r(st=new, cur="수정", lb=[]), "live-verify": self._r(t1=NOW - 20, st=old, cur="회귀", lb=[])})
        self._ag("f1", "[pl:bugfix/수정] fix", NOW - 60)
        sub = [{"lab": "probe: [pl:live-verify/회귀] probe", "min": 1, "aid": "p1"}]
        out = {r["name"]: r["stages"] for r in PR.pl_model(SID, self.sd, sub, None, NOW, "run")}
        self.assertEqual((out["bugfix"]["수정"]["o"], out["live-verify"]["회귀"]["o"]), ("done", "run"))
        # Control: no live agent anywhere -> the newest open run still takes the busy signal.
        out = {r["name"]: r["stages"] for r in PR.pl_model(SID, self.sd, [], None, NOW, "run")}
        self.assertEqual((out["bugfix"]["수정"]["o"], out["live-verify"]["회귀"]["o"]), ("run", "done"))

    def test_live_continued_agent_lights_every_copy(self):
        st = {"원인": {"s": "done", "t0": NOW - 90, "t1": NOW - 60, "n": 1}, "수정": {"s": "run", "t0": NOW - 50, "t1": NOW, "n": 1, "ag": ["c1"]}}
        self._file({"bugfix": self._r(st=st, cur="수정", lb=[])})
        self._ag("c1", "[pl:bugfix/원인] find", NOW - 80)
        sub = [{"lab": "sidereus-implementer: [pl:bugfix/원인] find", "min": 1, "aid": "c1"}]   # live row keeps the original tag
        s = PR.pl_model(SID, self.sd, sub, None, NOW, "idle")[0]["stages"]
        self.assertEqual((s["수정"]["o"], [a["run"] for a in s["수정"]["ag"]]), ("run", [True]))

    def test_pass_start(self):
        st = {"구현": {"s": "run", "t0": NOW - 900, "t1": NOW, "n": 4, "p0": NOW - 60, "k": 3},
              "검증": {"s": "done", "t0": NOW - 50, "t1": NOW - 40, "n": 1, "p0": "x", "k": 2}}
        self._file({"sidereus-change": self._r(st=st, lb=[])})
        s = PR.pl_model(SID, self.sd, [], None, NOW, "run")[0]["stages"]
        self.assertEqual((s["구현"]["p0"], s["구현"]["k"]), (NOW - 60, 3))
        self.assertNotIn("p0", s["검증"])   # bad p0: falls back to t0 on the client

    def test_passes(self):
        ok = [{"a": NOW - 900, "b": NOW - 500, "s": "back"}, {"a": NOW - 400, "b": NOW - 100, "s": "fail"}]
        bad = {"extra": ok[:1] + [{"a": 1, "b": 2, "s": "done", "x": "secret"}], "state": [{"a": 1, "b": 2, "s": "nope"}],
               "num": [{"a": "1", "b": 2, "s": "done"}], "long": ok * 4, "type": {"a": 1}, "empty": []}
        st = {"구현": {"s": "run", "t0": NOW - 900, "t1": NOW, "n": 4, "p0": NOW - 60, "k": 3, "ps": ok}}
        for k, v in bad.items():
            st[k] = {"s": "done", "t0": NOW - 50, "t1": NOW - 40, "n": 1, "p0": NOW - 45, "k": 2, "ps": v}
        self._file({"sidereus-change": self._r(st=st, lb=[])})
        s = PR.pl_model(SID, self.sd, [], None, NOW, "run")[0]["stages"]
        self.assertEqual(s["구현"]["ps"], ok)
        for k in bad:
            self.assertNotIn("ps", s[k], k)   # all or nothing: one bad entry drops the list

    def test_via_is_the_loopback_of_the_current_pass(self):
        # Hook stamps lb t == p0 for the loop-back that opened a pass; older edges (and a later forward pass) give no via.
        st = {"구현": {"s": "run", "t0": NOW - 900, "t1": NOW, "n": 4, "p0": NOW - 60, "k": 3}}
        lb = [{"f": "검증", "g": "구현", "n": 2, "t": NOW - 300}, {"f": "리뷰", "g": "구현", "n": 1, "t": NOW - 60}]
        self._file({"sidereus-change": self._r(st=st, lb=lb)})
        s = PR.pl_model(SID, self.sd, [], None, NOW, "run")[0]["stages"]["구현"]
        self.assertEqual((s["from"], s["via"]), ({"검증": 2, "리뷰": 1}, "리뷰"))
        self.assertNotIn("_vt", s)
        st["구현"]["p0"] = NOW - 30   # a forward pass after the loop-back
        self._file({"sidereus-change": self._r(st=st, lb=lb)})
        self.assertNotIn("via", PR.pl_model(SID, self.sd, [], None, NOW, "run")[0]["stages"]["구현"])

    def test_main_flag(self):
        st = {"구현": {"s": "done", "t0": NOW - 70, "t1": NOW - 60, "n": 0, "m": True}, "검증": {"s": "done", "t0": NOW - 50, "t1": NOW - 40, "n": 1, "m": False}}
        self._file({"sidereus-change": self._r(st=st, lb=[])})
        s = PR.pl_model(SID, self.sd, [], None, NOW, "idle")[0]["stages"]
        self.assertEqual((s["구현"].get("main"), "main" in s["검증"]), (True, False))

    def test_continued_agent_listed_under_both_stages(self):
        st = {"원인": {"s": "done", "t0": NOW - 90, "t1": NOW - 60, "n": 1},
              "수정": {"s": "done", "t0": NOW - 50, "t1": NOW - 10, "n": 2, "ag": ["c1", 5, "x" * 99]}}
        self._file({"bugfix": self._r(st=st, cur="수정", lb=[])})
        self._ag("c1", "[pl:bugfix/원인] find", NOW - 80)
        s = PR.pl_model(SID, self.sd, [], None, NOW, "idle")[0]["stages"]
        self.assertEqual([a["aid"] for a in s["원인"]["ag"]], ["c1"])
        self.assertEqual([(a["aid"], a["lab"]) for a in s["수정"]["ag"]], [("c1", "sidereus-implementer: [pl:bugfix/원인] find")])
        self.assertNotIn("ids", s["수정"])   # internal key never reaches the row
        self.assertEqual(PR.pl_runs_of(SID, NOW)[0]["st"]["수정"]["ids"], ["c1", "x" * 64])

    def test_caps(self):
        self._file({"p%d" % i: self._r(t1=NOW - i, proj="/p%d" % i) for i in range(8)})
        for i in range(30):
            self._ag("b%02d" % i, "[pl:p0/구현] " + "d" * 200, NOW - 99 + i)
        self._ag("old", "[pl:p3/구현] x", NOW - 60)
        sub = [{"lab": "t: [pl:p0/구현] live", "min": 0, "aid": "b00"}]
        out = PR.pl_model(SID, self.sd, sub, None, NOW)
        self.assertEqual([r["name"] for r in out], ["p0", "p1", "p2", "p3", "p4", "p5"])   # PLR_MODEL_MAX = 6
        ag = out[0]["stages"]["구현"]["ag"]
        self.assertEqual(len(ag), PR.PLR_AG_MAX)
        self.assertEqual(ag[0]["aid"], "b00")   # live one survives the trim
        self.assertTrue(ag[0]["run"])
        self.assertEqual([a["aid"] for a in ag[1:]], ["b%02d" % i for i in range(7, 30)])   # oldest finished dropped
        self.assertTrue(all(len(a["lab"]) <= PR.PLR_LAB_MAX for a in ag))
        self.assertTrue(all("ag" not in st for r in out[3:] for st in r["stages"].values()))   # older runs: stages only
        self.assertTrue(all("ag" in st for st in out[2]["stages"].values()))

    def test_ag_on_older_open_run(self):
        # Two newer ended runs used to take both `ag` slots and the open run behind them showed no agents.
        self._file({"e1": self._r(end=NOW - 1), "e2": self._r(t1=NOW - 2, end=NOW - 2), "o1": self._r(t1=NOW - 3),
                    "o2": self._r(t1=NOW - 4), "o3": self._r(t1=NOW - 5), "o4": self._r(t1=NOW - 6)})
        for n in ("e1", "e2", "o1", "o4"):
            self._ag("x" + n, "[pl:%s/구현] w" % n, NOW - 40)
        out = {r["name"]: r["stages"]["구현"].get("ag") for r in PR.pl_model(SID, self.sd, [], None, NOW)}
        self.assertEqual([a["aid"] for a in out["o1"]], ["xo1"])   # older open run keeps its agents
        self.assertEqual([a["aid"] for a in out["e1"]], ["xe1"])   # newest ended run too
        self.assertEqual((out["o2"], out["o3"]), ([], []))         # open runs 2-3: `ag` present
        self.assertEqual([a["aid"] for a in out["e2"]], ["xe2"])   # older ended run: meta-only agents
        self.assertIsNone(out["o4"])                               # 4th open: stages only

    def _file_past(self, runs, past):
        fp = os.path.join(self.tmp, SID + ".runs.json")
        with open(fp, "w", encoding="utf-8") as f:
            json.dump({"v": 1, "runs": runs, "past": past}, f)
        os.utime(fp, (NOW, NOW))

    def test_past_runs_separate_entries(self):
        # R3: earlier runs of the same name are their own entries with start time, label and their own stage states.
        cur = self._r(t0=NOW - 100, st={"구현": {"s": "run", "t0": NOW - 90, "t1": NOW, "n": 1}}, lb=[])
        old1 = self._r(t0=NOW - 1000, t1=NOW - 900, end=NOW - 900, cur="구현", inflight={"구현": 1}, lb=[],
                       st={"설계": {"s": "done", "t0": NOW - 990, "t1": NOW - 960, "n": 1}, "구현": {"s": "run", "t0": NOW - 950, "t1": NOW - 900, "n": 1}})
        old2 = self._r(t0=NOW - 800, t1=NOW - 700, end=NOW - 700, cur="설계", lb=[],
                       st={"설계": {"s": "fail", "t0": NOW - 790, "t1": NOW - 700, "n": 1}})
        self._file_past({"sc": cur}, {"sc": [old1, "junk", old2], "Bad Name": [old1], "x": "nope"})
        self._ag("a0", "[pl:sc/설계] first request", NOW - 995)
        self._ag("a1", "[pl:sc/구현] later", NOW - 950)
        self._ag("a2", "[pl:sc/설계] second", NOW - 795)
        self._ag("a3", "[pl:sc/구현]  current  one", NOW - 95)
        r = PR.pl_model(SID, self.sd, [], None, NOW, "run")[0]
        self.assertEqual((r["rid"], r["lab"], list(r["stages"])), (NOW - 100, "current one", ["구현"]))
        self.assertEqual([(p["rid"], p["lab"]) for p in r["past"]], [(NOW - 800, "second"), (NOW - 1000, "first request")])
        self.assertEqual(set(r["past"][0]), {"rid", "t0", "t1", "end", "cur", "lab", "stages"})
        self.assertEqual({k: v["o"] for k, v in r["past"][1]["stages"].items()}, {"설계": "done", "구현": "done"})   # closed idle
        self.assertEqual(r["past"][0]["stages"]["설계"]["o"], "fail")
        # Past stages list their window's tagged agents (meta only, never running); a3 is outside every past window.
        ids = lambda p, t: [(a["aid"], a["tid"], a["run"]) for a in p["stages"][t]["ag"]]
        self.assertEqual(ids(r["past"][1], "설계"), [("a0", "tu_a0", False)])
        self.assertEqual(ids(r["past"][1], "구현"), [("a1", "tu_a1", False)])
        self.assertEqual(ids(r["past"][0], "설계"), [("a2", "tu_a2", False)])
        a = r["past"][1]["stages"]["설계"]["ag"][0]
        self.assertEqual((a["t0"], a["t1"], a["lab"]), (NOW - 995, NOW - 992, "sidereus-implementer: [pl:sc/설계] first request"))
        self.assertNotIn("a3", json.dumps(r["past"]))
        dump = json.dumps(r, ensure_ascii=False)
        for bad in ("/secret", "msg", "inflight", "junk"):
            self.assertNotIn(bad, dump)
        many = [self._r(t0=NOW - 2000 + 100 * i, t1=NOW - 1990 + 100 * i, end=NOW - 1990 + 100 * i, lb=[]) for i in range(8)]
        self._file_past({"sc": cur}, {"sc": many})
        past = PR.pl_model(SID, self.sd, [], None, NOW)[0]["past"]
        self.assertEqual([p["rid"] for p in past], [NOW - 2000 + 100 * i for i in (7, 6, 5, 4, 3)])   # newest PLR_PAST_MAX

    def test_live_agent_never_lights_ended_run(self):
        # R4: a stage is marked only by an event inside the current run; an ended run ignores live agents.
        st = {"구현": {"s": "done", "t0": NOW - 70, "t1": NOW - 10, "n": 1}}
        self._file({"sc": self._r(st=st, cur="구현", lb=[], end=NOW - 5)})
        sub = [{"lab": "t: [pl:sc/구현] w", "min": 0, "aid": "z1"}, {"lab": "t: [pl:sc/리뷰] w", "min": 0, "aid": "z2"}]
        s = PR.pl_model(SID, self.sd, sub, None, NOW, "run")[0]["stages"]
        self.assertEqual(list(s), ["구현"])
        self.assertEqual((s["구현"]["o"], s["구현"]["ag"]), ("done", []))

    def test_current_run_has_no_stage_of_earlier_run(self):
        # R1: a still-live agent of the previous run (meta before this run's t0) adds no stage to the new run.
        self._file({"sc": self._r(t0=NOW - 100, st={"구현": {"s": "run", "t0": NOW - 90, "t1": NOW, "n": 1}}, lb=[])})
        self._ag("e1", "[pl:sc/설계] old", NOW - 500)
        sub = [{"lab": "t: [pl:sc/설계] old", "min": 8, "aid": "e1", "tid": "tu_e1"}]
        r = PR.pl_model(SID, self.sd, sub, None, NOW, "run")[0]
        self.assertEqual((list(r["stages"]), r["lab"]), (["구현"], ""))
        self.assertEqual(r["stages"]["구현"]["ag"], [])

    def test_live_agent_with_in_window_meta_lights_unrecorded_stage(self):
        # runs.json has no entry for the stage yet; meta inside the run window is this run's agent, not an earlier run's.
        t0 = NOW - 100
        self._file({"bugfix": self._r(t0=t0, cur="", st={"재현": {"s": "skip", "t0": t0, "t1": t0, "n": 0}}, lb=[])})
        self._ag("A", "[pl:bugfix/원인] diagnose", t0 + 25)
        sub = [{"lab": "fixer: [pl:bugfix/원인] diagnose", "min": 1, "aid": "A", "tid": "tu_A"}]
        s = PR.pl_model(SID, self.sd, sub, None, NOW, "run")[0]["stages"]
        self.assertEqual(s["원인"]["o"], "run")
        self.assertEqual([(a["aid"], a["run"]) for a in s["원인"]["ag"]], [("A", True)])
        self._ag("B", "[pl:bugfix/분석] old", t0 - 500)   # control: meta outside the window stays skipped
        sub = [{"lab": "fixer: [pl:bugfix/분석] old", "min": 9, "aid": "B", "tid": "tu_B"}]
        self.assertNotIn("분석", PR.pl_model(SID, self.sd, sub, None, NOW, "run")[0]["stages"])

    def test_bad_proj(self):
        for bad in ("rel/path", "/a/../b", "/x\ny", "/" + "a" * 300, 5, None):
            self._file({"sidereus-change": self._r(proj=bad)})
            self.assertEqual(PR.pl_model(SID, self.sd, [], None, NOW)[0]["proj"], "")
        self.assertEqual(PR.pl_model("../bad", self.sd, [], None, NOW), [])
        self.assertEqual(PR.pl_model(SID, "", [], None, NOW)[0]["stages"]["설계"]["ag"], [])   # no sess dir


if __name__ == "__main__":
    unittest.main()
