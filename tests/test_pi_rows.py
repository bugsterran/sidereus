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



class ExtOld(unittest.TestCase):
    """«Old extension» (R1-R4): rev on ext_hook/ext_store, extOld on ext rows. No live files: store and revs patched."""
    CUR = "0123456789ab"

    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("ext_hook_pi_rev", os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ext-hooks", "ext_hook.py"))
        self.hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.hook)
        self.ext = sidereus("ext")
        self.inst = self.CUR
        self._ext = dict(st._ext)
        st._ext.clear()
        self.p = [mock.patch.object(pi, "ext_rev", lambda tpl=None: self.cur),
                  mock.patch.object(pi, "installed_rev", lambda: self.inst),
                  mock.patch.object(st, "_ext_save_locked", lambda: None),
                  mock.patch.object(st, "_runs_save_locked", lambda: None)]
        for n, v in {"ext_gone_check": lambda now: None, "_ext_prune_locked": lambda now: None,
                     "ext_tok_refresh": lambda *a: None, "ext_tok": lambda *a: {}, "ext_side_tok": lambda *a: {},
                     "plm_of": lambda *a: None, "pl_model": lambda *a: []}.items():
            self.p.append(mock.patch.object(self.ext, n, v))
        for p in self.p:
            p.start()
        self.cur = self.CUR

    def tearDown(self):
        for p in self.p:
            p.stop()
        st._ext.clear()
        st._ext.update(self._ext)

    def _put(self, plat="pi", sid="pi-s1", **kw):
        v = {"cwd": "/w/pi-proj", "state": "think", "firstSeen": NOW, "lastSeen": NOW}
        v.update(kw)
        st._ext[(plat, sid)] = v

    def _old(self, sid="pi-s1"):
        return next(r["extOld"] for r in self.ext.ext_rows() if r["sid"] == sid)

    def test_r1_ext_hook_copies_only_valid_pi_rev(self):
        ev = {"hook_event_name": "PreToolUse", "session_id": "pi-s1", "tool_name": "read"}
        out, _raw = self.hook.build("pi", dict(ev, ext_rev=self.CUR))
        self.assertEqual(out["ext_rev"], self.CUR)
        for bad in ("0123456789AB", "0123456789a", self.CUR + "\n", 123456789012, ["x"]):
            out, _raw = self.hook.build("pi", dict(ev, ext_rev=bad))
            self.assertNotIn("ext_rev", out, bad)
        out, _raw = self.hook.build("gemini", {"hook_event_name": "BeforeTool", "session_id": "g", "ext_rev": self.CUR})
        self.assertNotIn("ext_rev", out or {})

    def test_r1_ext_store_revalidates(self):
        base = {"platform": "pi", "session_id": "pi-s1", "event": "PreToolUse", "ts": NOW}
        st.ext_ingest(dict(base, ext_rev=self.CUR))
        self.assertEqual(st._ext[("pi", "pi-s1")]["extRev"], self.CUR)
        st.ext_ingest(dict(base, ext_rev=self.CUR + "\n"))           # anyone can POST: same shape check as ext_hook
        self.assertEqual(st._ext[("pi", "pi-s1")]["extRev"], "")
        st.ext_ingest(dict(base, platform="gemini", ext_rev=self.CUR))
        self.assertNotIn("extRev", st._ext[("gemini", "pi-s1")])

    def test_r2_old_rev_reload_or_connect(self):
        self._put(extRev="aaaaaaaaaaaa")
        self.assertEqual(self._old(), "reload")                       # installed file is current: /reload in pi
        self.inst = "aaaaaaaaaaaa"
        self.assertEqual(self._old(), "connect")                      # installed file old too: Connect, then /reload
        self.inst = None
        self.assertEqual(self._old(), "connect")

    def test_r3_no_rev_is_old(self):
        self._put()
        self.assertEqual(self._old(), "reload")

    def test_r4_same_rev_ended_other_plat_and_no_reference(self):
        self._put(extRev=self.CUR)
        self._put(sid="pi-dead", state="gone")
        self._put(sid="pi-end", ended=True)
        self._put(plat="gemini", sid="g-1")
        for sid in ("pi-s1", "pi-dead", "pi-end", "g-1"):
            self.assertEqual(self._old(sid), "", sid)
        self._put(sid="pi-old")
        self.cur = None                                               # template unreadable: never warn without a reference
        self.assertEqual(self._old("pi-old"), "")

    def test_r4_hookless_row_has_no_chip(self):
        self.assertEqual(pr._row("pi", {"sid": SID, "cwd": "/w/pi-proj", "start": NOW, "mtime": NOW}, NOW)["extOld"], "")


if __name__ == "__main__":
    unittest.main()
