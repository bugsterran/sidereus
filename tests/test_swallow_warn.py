"""Broad excepts that used to swallow everything now report unexpected errors via warn_once; expected ones stay quiet.

No live files: temp dirs only, and every dependency is monkeypatched on the module that reads it.
"""
import json
import os
import re
import shutil
import tempfile
import unittest

from tests import _load

ag = _load.sidereus("agents")
lp = _load.sidereus("live_probe")
bu = _load.sidereus("burn")
bw = _load.sidereus("burn_week")


class _Warns(object):
    def __init__(self, *mods):
        self.mods, self.got, self.saved = mods, [], []

    def __enter__(self):
        for m in self.mods:
            self.saved.append((m, m.warn_once))
            # third field = the English text: legacy `en`, else the template filled from `vars`
            m.warn_once = lambda key, msg, soft=False, en=None, log=True, vars=None, more=None: self.got.append(
                (key, soft, en or re.sub(r"\{(\w+)\}", lambda g: str((vars or {}).get(g.group(1), g.group(0))), msg)))
        return self.got

    def __exit__(self, *a):
        for m, f in self.saved:
            m.warn_once = f


class AgentMeta(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        ag._AGENT_META.pop(self.d, None)

    def tearDown(self):
        ag._AGENT_META.pop(self.d, None)
        shutil.rmtree(self.d, ignore_errors=True)

    def test_missing_subagents_dir_is_quiet(self):
        with _Warns(ag) as got:
            self.assertEqual(ag._agent_meta(self.d), {})
        self.assertEqual(got, [])

    def test_non_dict_meta_warns(self):
        os.makedirs(os.path.join(self.d, "subagents"))
        with open(os.path.join(self.d, "subagents", "agent-x.meta.json"), "w") as f:
            json.dump([1, 2], f)
        with _Warns(ag) as got:
            self.assertEqual(ag._agent_meta(self.d), {})
        self.assertEqual([k for k, _s, _e in got], ["agmeta"])
        self.assertTrue(got[0][1] and "AttributeError" in got[0][2])


class SidClaimStale(unittest.TestCase):
    def setUp(self):
        self.saved = lp._sid_transcript
        lp._sid_stale[0], lp._sid_stale[1] = 0, {}

    def tearDown(self):
        lp._sid_transcript = self.saved
        lp._sid_stale[0], lp._sid_stale[1] = 0, {}

    def _run(self, exc):
        def boom(_sid):
            raise exc
        lp._sid_transcript = boom
        with _Warns(lp) as got:
            self.assertFalse(lp._sid_claim_stale("s1", "/w"))
        return got

    def test_oserror_quiet(self):
        self.assertEqual(self._run(OSError("gone")), [])

    def test_programming_error_warns(self):
        self.assertEqual([k for k, _s, _e in self._run(TypeError("bad"))], ["sidstale"])


class QbWeek(unittest.TestCase):
    def test_failure_warns_and_returns_none(self):
        saved = bw.usage

        def boom():
            raise RuntimeError("x")
        bw.usage = boom
        try:
            with _Warns(bw) as got:
                self.assertIsNone(bw._qb_week(1_800_000_000.0))
        finally:
            bw.usage = saved
        self.assertEqual([(k, s) for k, s, _e in got], [("qbweek", True)])


bs = _load.sidereus("burn_scan")
lv = _load.sidereus("live")


class TodayScanVanishedFile(unittest.TestCase):
    """A path that stats fine but cannot be opened (a directory named *.jsonl) skips that file only."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.saved = {k: getattr(bs, k) for k in ("CLAUDE_PROJECTS", "_slug_name")}
        self.today = dict(bs._today)
        proj = os.path.join(self.d, "proj")
        os.makedirs(os.path.join(proj, "gone.jsonl"))       # open() -> IsADirectoryError
        import time as _t
        ts = _t.strftime("%Y-%m-%dT%H:%M:%S", _t.gmtime())
        with open(os.path.join(proj, "ok.jsonl"), "w") as f:
            f.write(json.dumps({"timestamp": ts, "requestId": "r1",
                                "message": {"id": "m1", "usage": {"input_tokens": 7}}}) + "\n")
        bs.CLAUDE_PROJECTS, bs._slug_name = self.d, (lambda s: s)

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(bs, k, v)
        bs._today.clear()
        bs._today.update(self.today)
        shutil.rmtree(self.d, ignore_errors=True)

    def test_skips_file_and_keeps_others(self):
        with _Warns(bs) as got:
            bs._today_fetch()
        self.assertEqual(got, [])
        self.assertEqual([(r["name"], r["tok"]) for r in bs._today["by"]], [("proj", 7)])


class ArgvClaimsJunkOfficial(unittest.TestCase):
    def test_junk_entry_does_not_abort_claims(self):
        A, B = "a" * 8 + "-1111-2222-3333-" + "4" * 12, "b" * 8 + "-1111-2222-3333-" + "4" * 12
        snap = [("101", "1", "claude"), ("102", "1", "claude --resume " + B)]
        saved = lv._sid_claim_stale
        lv._sid_claim_stale = lambda sid, cwd=None: False
        sids, claimed = set(), set()
        try:
            with _Warns(lv) as got:
                lv._live_argv_claims(snap, ["101", "102"], {"101": "junk", "999": {"sessionId": A}},
                                     {}, sids, claimed)
        finally:
            lv._sid_claim_stale = saved
        self.assertEqual(got, [])
        self.assertEqual((sids, claimed), ({B}, {"102"}))


if __name__ == "__main__":
    unittest.main()
