"""Timeline rows carry `acct` (account picker filter) only for a non-primary account; primary rows have no key."""
import unittest

from tests._load import sidereus

tl = sidereus("timeline")
cr = sidereus("claude_roots")


class _Stat:
    st_mtime, st_ctime, st_birthtime = 1000.0, 100.0, 100.0


class TlAcct(unittest.TestCase):
    def setUp(self):
        self._saved = {n: getattr(tl, n) for n in ("_tl_pick", "_agent_meta", "_tl_wf_rows", "_tl_sess_row",
                                                    "_tl_agent_row", "_tl_live")}
        self._acct = cr.acct_of
        self.calls = []
        tl._tl_pick = lambda cut, rows=None: [("/w/a", "a", ["/p/a/s1.jsonl", "/p/a/s2.jsonl"], "/p/a/s1.jsonl")]
        tl._tl_live = lambda rows: ({}, {})
        tl._agent_meta = lambda sd, ttl=0: {"toolu_" + sd[-2:]: {}}
        tl._tl_agent_row = lambda tid, mm, *a: {"tid": tid}
        tl._tl_wf_rows = lambda sd, sid, *a: [{"tid": "wf:" + sid}]
        tl._tl_sess_row = lambda fp, sid, *a: {"tid": "sess:" + sid, "kind": "sess"}

        def acct_of(sid, fp):
            self.calls.append(sid)
            return ("work", "/x/.claude-work") if sid == "s2" else ("", "")
        cr.acct_of = acct_of

    def tearDown(self):
        for n, v in self._saved.items():
            setattr(tl, n, v)
        cr.acct_of = self._acct

    def test_acct_only_on_non_primary_rows(self):
        out = tl._tl_rows(0, [])
        by = {r["tid"]: r for r in out}
        for t in ("toolu_s2", "wf:s2", "sess:s2"):
            self.assertEqual(by[t].get("acct"), "work")
        for t in ("toolu_s1", "wf:s1", "sess:s1"):
            self.assertNotIn("acct", by[t])
        self.assertEqual(self.calls, ["s1", "s2"])     # once per transcript


if __name__ == "__main__":
    unittest.main()
