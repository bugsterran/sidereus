"""agents per-file caches: a 72h-sized working set (~640 files) stays cached; the caches stay bounded."""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import load, sidereus

load()
ag = sidereus("agents")


def _line(content):
    return json.dumps({"type": "assistant", "message": {"content": content}}, separators=(",", ":")) + "\n"


class AgentCaches(unittest.TestCase):
    N = 700   # above the measured 72h working set (639)

    def setUp(self):
        self.saved = (dict(ag._AGENT_LAST), dict(ag._AGENT_TOOLS), dict(ag._AGENT_FIN), ag._AGENT_LAST.cap)
        for d in (ag._AGENT_LAST, ag._AGENT_TOOLS, ag._AGENT_FIN):
            d.clear()
        self.d = tempfile.mkdtemp(prefix="sidereus-agcache-")
        self.fps = []
        for i in range(self.N):
            fp = os.path.join(self.d, "agent-%d.jsonl" % i)
            with open(fp, "w", encoding="utf-8") as f:
                f.write(_line([{"type": "tool_use", "name": "Read", "input": {"file_path": "/x/%d.py" % i}}]))
                f.write(_line([{"type": "text", "text": "done"}]))
            self.fps.append(fp)

    def tearDown(self):
        last, tools, fin, cap = self.saved
        self._cap(cap)
        for d, s in ((ag._AGENT_LAST, last), (ag._AGENT_TOOLS, tools), (ag._AGENT_FIN, fin)):
            d.clear()
            d.update(s)   # dict(OrderedDict) keeps order, so LRU order is restored too
        shutil.rmtree(self.d, ignore_errors=True)

    @staticmethod
    def _cap(n):
        for d in (ag._AGENT_LAST, ag._AGENT_TOOLS, ag._AGENT_FIN):
            d.cap = n

    def _pass(self):
        return [(ag._agent_last(f), ag._agent_tools(f), ag._agent_fin(f)) for f in self.fps]

    def test_working_set_second_pass_reads_nothing(self):
        first = self._pass()
        self.assertEqual(first[3], ("Read", 1, True))
        orig = ag._tail_lines
        calls = []
        ag._tail_lines = lambda *a, **k: calls.append(a) or orig(*a, **k)
        try:
            second = self._pass()
        finally:
            ag._tail_lines = orig
        self.assertEqual(second, first)
        self.assertEqual(calls, [])                      # _agent_last/_agent_fin all hit
        self.assertEqual(len(ag._AGENT_TOOLS), self.N)   # no clear() mid-pass

    def test_caches_stay_bounded(self):
        self._cap(100)
        self._pass()
        for d in (ag._AGENT_LAST, ag._AGENT_TOOLS, ag._AGENT_FIN):
            self.assertLessEqual(len(d), 100)

    def test_hot_keys_survive_eviction(self):
        self._cap(100)
        hot = self.fps[:10]
        for f in self.fps[10:310]:   # 3x the cap
            for h in hot:   # keep touching the hot files while cold ones stream through
                ag._agent_last(h), ag._agent_tools(h), ag._agent_fin(h)
            ag._agent_last(f), ag._agent_tools(f), ag._agent_fin(f)
        for d in (ag._AGENT_LAST, ag._AGENT_TOOLS, ag._AGENT_FIN):
            for h in hot:
                self.assertIn(h, d)
            self.assertNotIn(self.fps[10], d)   # least-recent cold file went first

    def test_mtime_change_replaces_in_place(self):
        fp = self.fps[0]
        self.assertEqual(ag._agent_fin(fp), True)
        self.assertEqual(ag._agent_last(fp), "Read")     # tool name only — no path (rule 1)
        for i in range(5):
            with open(fp, "a", encoding="utf-8") as f:
                f.write(_line([{"type": "tool_use", "name": "Grep", "input": {"pattern": "p%d" % i}}]))
            st = os.stat(fp)
            os.utime(fp, (st.st_atime, st.st_mtime + 10 * (i + 1)))
            self.assertEqual(ag._agent_fin(fp), False)
            self.assertTrue(ag._agent_last(fp).startswith("Grep"))
            self.assertEqual(ag._agent_tools(fp), i + 2)
        for d in (ag._AGENT_LAST, ag._AGENT_TOOLS, ag._AGENT_FIN):
            self.assertEqual(list(d), [fp])     # one entry per file, no dead (file, mtime) keys


if __name__ == "__main__":
    unittest.main()
