"""pi sessions on the screen paths: presence row (R1/R2), timeline row and work panel (R3), no text leak (R3)."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

pi = sidereus("plat_pi")
st = sidereus("ext_store")
pr = sidereus("ext_presence")
te = sidereus("timeline_ext")

NOW = 1800000000.0
SID = "0199aaaa-bbbb-7ccc-8ddd-0000000000d1"
MARK = "PI-MARKER-TEXT"


def _iso(t):
    import datetime
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _lines():
    t0 = NOW - 300
    u = {"input": 100, "output": 20, "cacheRead": 30, "cacheWrite": 0, "cost": {"total": 0.01}}
    return [
        {"type": "session", "version": 3, "id": SID, "timestamp": _iso(t0), "cwd": "/w/pi-proj"},
        {"type": "message", "id": "s1", "timestamp": _iso(t0), "message": {
            "role": "system", "content": MARK + "-sys", "sections": {"preamble": MARK + "-section"}}},
        {"type": "session_info", "id": "n1", "timestamp": _iso(t0), "name": MARK + "-name"},
        {"type": "model_change", "id": "c1", "timestamp": _iso(t0 + 1), "provider": "openai", "modelId": "gpt-5"},
        {"type": "message", "id": "u1", "timestamp": _iso(t0 + 2), "message": {
            "role": "user", "content": MARK + "-user", "timestamp": int((t0 + 2) * 1000)}},
        {"type": "message", "id": "a1", "timestamp": _iso(t0 + 3), "message": {
            "role": "assistant", "provider": "openai", "model": "gpt-5", "usage": u,
            "timestamp": int((t0 + 3) * 1000),
            "content": [{"type": "thinking", "thinking": MARK + "-think"}, {"type": "text", "text": MARK + "-asst"},
                        {"type": "toolCall", "id": "k1", "name": "read", "arguments": {"path": MARK + "-arg"}}]}},
        {"type": "message", "id": "t1", "timestamp": _iso(t0 + 4), "message": {
            "role": "toolResult", "toolCallId": "k1", "toolName": "read", "isError": False,
            "content": [{"type": "text", "text": MARK + "-out"}], "details": {"x": MARK + "-details"},
            "timestamp": int((t0 + 4) * 1000)}},
        {"type": "compaction", "id": "k1", "timestamp": _iso(t0 + 5), "summary": MARK + "-summary",
         "usage": dict(u, cost={"total": 0.02})},
    ]


class PiRows(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-pi-rows-")
        self.root = os.path.join(self.tmp, "agent")
        d = os.path.join(self.root, "sessions", "--w-pi-proj--")
        os.makedirs(d)
        self.path = os.path.join(d, "2027-01-15T08-00-00-000Z_%s.jsonl" % SID)
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("".join(json.dumps(x) + "\n" for x in _lines()))
        os.utime(self.path, (NOW - 30, NOW - 30))
        self._ext, self._ended = dict(st._ext), dict(st._ext_ended)
        st._ext.clear()
        st._ext_ended.clear()
        self.p = [mock.patch.object(pi, "root", lambda: self.root),
                  mock.patch.object(te, "PLAT_MODS", {"pi": pi}),           # never the live Gemini/Codex folders
                  mock.patch.object(te, "ext_runs", lambda parent=None: []),
                  mock.patch.object(te, "ext_hook_cwds", lambda: {}),
                  mock.patch.object(pr.plat_cursor, "scan", lambda since, n, stat_n: []),
                  mock.patch.object(pr.plat_copilot, "scan", lambda n: [])]
        for p in self.p:
            p.start()
        pi._cache.clear()
        pr._PRES_MEMO.clear()

    def tearDown(self):
        for p in self.p:
            p.stop()
        st._ext.clear()
        st._ext.update(self._ext)
        st._ext_ended.clear()
        st._ext_ended.update(self._ended)
        pi._cache.clear()
        pr._PRES_MEMO.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _pres(self):
        return [r for r in pr.ext_presence_rows(NOW) if r["plat"] == "pi"]

    def test_r1_r2_presence_row(self):
        rows = self._pres()
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r["sid"], r["cwd"], r["project"], r["state"]), (SID, "/w/pi-proj", "pi-proj", "unknown"))
        self.assertTrue(r["rollout"])
        self.assertNotIn("hookless", r)                         # pi hooks connect now: the row lights «Hooks not connected»
        self.assertEqual(r["model"], "openai/gpt-5")
        self.assertEqual(r["tok"], 2 * (100 + 20 + 30))
        self.assertAlmostEqual(r["estCost"], 0.03)
        self.assertEqual(r["runmin"]["run"], 4)                 # header start NOW-300 -> mtime NOW-30

    def test_r1_dismissed_stays_hidden(self):
        import types
        self.assertEqual(len(self._pres()), 1)
        with mock.patch.object(st, "time", types.SimpleNamespace(time=lambda: NOW)), \
                mock.patch.object(st, "_ext_save_locked", lambda: None):
            st.ext_dismiss(SID)
        pr._PRES_MEMO.clear()
        self.assertEqual(self._pres(), [])

    def test_r3_timeline_row(self):
        rows = [r for r in te._plat_tl_rows(NOW - 3600, NOW) if r["tid"] == "ext:pi|" + SID]
        self.assertTrue(rows)
        r = rows[0]                                             # adapter row first; _tl_dedup keeps it
        self.assertEqual((r["plat"], r["last"], r["model"], r["proj"]), ("pi", "read", "openai/gpt-5", "pi-proj"))

    def test_r3_work_panel_events(self):
        w = pr.ext_work_any("pi", SID, NOW)
        self.assertTrue(w["ok"])
        self.assertEqual(w["events"], [{"e": "PostToolUse", "tool": "read", "t": NOW - 296}])
        self.assertEqual(w["model"], "openai/gpt-5")
        self.assertEqual(w["type"], "Pi · " + SID[:8])

    def test_r3_no_text_anywhere(self):
        out = json.dumps([pi.scan(0.0), pi.one(SID), pi.session_msgs(self.path), self._pres(),
                          te._plat_tl_rows(NOW - 3600, NOW), pr.ext_work_any("pi", SID, NOW)], default=str)
        self.assertIn("read", out)
        self.assertNotIn(MARK, out)


if __name__ == "__main__":
    unittest.main()
