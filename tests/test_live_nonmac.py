"""`live_cwds` off Mac: no process snapshot, liveness comes from `claude agents` alone. No live files or processes."""
import unittest

from tests._load import sidereus

lv = sidereus("live")
nt = sidereus("notes")

SID = "87821821-791d-4b4d-a2f1-122463e2b2bb"
NEW = "bb22bb22-0000-4000-8000-000000000002"
CWD = "C:\\Users\\bugst\\sidereus"   # raw `claude agents --json` form; transcripts carry the same string


class LiveNonMac(unittest.TestCase):
    def setUp(self):
        self._saved = {k: getattr(lv, k) for k in ("_ps_snap", "agent_view", "IS_MAC", "_sid_transcript")}
        self._cache = lv._live_cache
        self._sids = list(lv._live_sids)
        lv._live_cache = (0.0, set())
        lv.IS_MAC = False
        lv._ps_snap = lambda ttl=None: []
        lv._sid_transcript = lambda sid: "/t/%s.jsonl" % sid if sid == SID else None

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(lv, k, v)
        lv._live_cache = self._cache
        lv._live_sids[:] = self._sids

    def test_official_sid_is_alive_not_done(self):
        # shape of a real Windows `claude agents --json` entry (keyed by pid string as agent_view returns)
        lv.agent_view = lambda ttl=None: {"29308": {"pid": 29308, "cwd": CWD, "kind": "interactive",
                                                    "startedAt": 1792885170431, "sessionId": SID,
                                                    "name": "sidereus-85", "status": "idle"}}
        live = lv.live_cwds(ttl=0)
        self.assertEqual(live, {})                 # bound by id, so no path slot (same as the Mac path)
        self.assertTrue(lv.sid_alive(SID))
        self.assertNotEqual(nt._sess_state(CWD, "text", live, sid=SID), "done")

    def test_sid_without_transcript_keeps_path_slot(self):
        lv.agent_view = lambda ttl=None: {"10": {"sessionId": NEW, "cwd": CWD}, "11": "junk"}
        self.assertEqual(lv.live_cwds(ttl=0), {CWD: 1})
        self.assertTrue(lv.sid_alive(NEW))

    def test_official_unknown_is_none(self):
        lv.agent_view = lambda ttl=None: None
        self.assertIsNone(lv.live_cwds(ttl=0))


if __name__ == "__main__":
    unittest.main()
