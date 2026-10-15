"""External CLI work panel resolves by (platform, session_id), never by cwd."""
import time
import unittest

from tests._load import sidereus

ext = sidereus("ext")
st = sidereus("ext_store")   # store internals are patched on their owner


class ExtWork(unittest.TestCase):
    def setUp(self):
        self._save, self._ext = st._ext_save_locked, dict(ext._ext)
        st._ext_save_locked = lambda: None           # no live file writes
        ext._ext.clear()

    def tearDown(self):
        st._ext_save_locked = self._save
        ext._ext.clear()
        ext._ext.update(self._ext)

    def feed(self, sid, ev, cwd="/w/proj", plat="gemini", **kw):
        req = {"platform": plat, "session_id": sid, "event": ev, "cwd": cwd}
        req.update(kw)
        return ext.ext_ingest(req)

    def test_resolves_by_platform_and_sid(self):
        self.feed("gm-a", "SessionStart", model="gemini-2.5-pro")
        self.feed("gm-a", "PreToolUse", tool_name="run_shell")
        self.feed("gm-b", "SessionStart")             # same cwd, other session
        d = ext.ext_work("gm", "gm-a")
        self.assertTrue(d["ok"] and d["ext"])
        self.assertEqual((d["sid"], d["plat"], d["platform"]), ("gm-a", "gm", "gemini"))
        self.assertEqual((d["state"], d["tool"], d["model"]), ("tool", "run_shell", "gemini-2.5-pro"))
        self.assertEqual([e["e"] for e in d["events"]], ["SessionStart", "PreToolUse"])
        self.assertEqual(ext.ext_work("gemini", "gm-b")["sid"], "gm-b")   # platform name works too

    def test_no_cwd_fallback(self):
        self.feed("gm-a", "SessionStart")
        self.assertFalse(ext.ext_work("gm", "claude-sid-in-same-folder")["ok"])
        self.assertFalse(ext.ext_work("cx", "gm-a")["ok"])                # wrong platform
        self.assertFalse(ext.ext_work("gm", "")["ok"])
        self.assertFalse(ext.ext_work("cc", "gm-a")["ok"])                # Claude is not an ext platform

    def test_event_ring_is_bounded_and_metadata_only(self):
        t0 = int(time.time()) - 100                   # recent, or the 24h prune drops it
        for i in range(ext.EXT_EV_N + 5):
            self.feed("gm-a", "UserPromptSubmit", prompt="secret text %d" % i, ts=t0 + i)
        d = ext.ext_work("gm", "gm-a")
        self.assertEqual(len(d["events"]), ext.EXT_EV_N)
        self.assertEqual(d["events"][-1]["t"], t0 + ext.EXT_EV_N + 4)
        self.assertNotIn("secret", repr(d))
        for e in d["events"]:
            self.assertEqual(set(e), {"e", "tool", "t"})


if __name__ == "__main__":
    unittest.main()
