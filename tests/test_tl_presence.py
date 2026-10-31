"""Hook-less Cursor/Copilot sessions (ext_presence) get a main-session timeline row; a hook row wins."""
import unittest
from unittest import mock

from tests._load import sidereus

te = sidereus("timeline_ext")
pr = sidereus("ext_presence")
st = sidereus("ext_store")
ident = sidereus("ident")

NOW = 1800000000.0
CUT = NOW - 3600
CWD = "C:\\Users\\o\\proj"
CU = "0199aaaa-bbbb-7ccc-8ddd-eeeeffff0042"
CP = "0199aaaa-bbbb-7ccc-8ddd-eeeeffff0043"


class TlPresence(unittest.TestCase):
    def setUp(self):
        self._ext = dict(st._ext)
        st._ext.clear()
        self._ended = dict(st._ext_ended)
        st._ext_ended.clear()
        pr._PRES_MEMO.clear()
        # Cursor: started before the window, active inside it; Copilot: whole span inside the window.
        self.cands = {"cursor": [{"sid": CU, "cwd": CWD, "start": CUT - 1200, "mtime": NOW - 60}],
                      "copilot": [{"sid": CP, "cwd": CWD, "start": NOW - 1800, "mtime": NOW - 600}]}
        self.p = [mock.patch.object(pr, "_cands", lambda plat, now: list(self.cands[plat])),
                  mock.patch.object(te, "PLAT_MODS", {}),
                  mock.patch.object(te, "ext_runs", lambda parent=None: []),
                  mock.patch.object(te, "ext_hook_cwds", lambda: {}),
                  mock.patch.object(ident.os, "sep", "\\")]   # Windows path split on any host
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        st._ext.clear()
        st._ext.update(self._ext)
        st._ext_ended.clear()
        st._ext_ended.update(self._ended)
        pr._PRES_MEMO.clear()

    def rows(self, sid):
        return [r for r in te._plat_tl_rows(CUT, NOW) if r.get("sid") == sid]

    def test_main_rows(self):
        for sid, key, segs in ((CU, "cursor", [[int(CUT), int(NOW - 60)]]),
                               (CP, "copilot", [[int(NOW - 600 - 1200), int(NOW - 600)]])):
            got = self.rows(sid)
            self.assertEqual(len(got), 1, sid)
            r = got[0]
            self.assertEqual(r["tid"], "ext:" + st.EXT_PLAT[key] + "|" + sid)
            self.assertEqual((r["depth"], r["kind"], r["proj"]), (0, "sess", "proj"))
            self.assertEqual(r["segs"], segs)

    def test_idle_before_window(self):
        self.cands["copilot"][0].update(start=CUT - 900, mtime=CUT - 100)
        r = self.rows(CP)
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["segs"], [])

    def test_hook_row_wins(self):
        st._ext[("cursor", CU)] = {"cwd": "/w/other", "ev": [{"e": "stop", "t": NOW - 30}],
                                   "firstSeen": NOW - 100, "lastSeen": NOW - 30, "state": "idle"}
        with mock.patch.object(te, "ext_side_msgs", lambda cut: {}):
            got = self.rows(CU)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["cwd"], "/w/other")


if __name__ == "__main__":
    unittest.main()
