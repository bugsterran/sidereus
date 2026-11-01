"""A pid-less external CLI row idle in 'wait' past PIDLESS_IDLE_SEC shows as ended ('done'); a pid row keeps its rules."""
import unittest

from tests._load import sidereus

ext = sidereus("ext")
st = sidereus("ext_store")
gm = sidereus("plat_gemini")

NOW = 1790000000.0


class PidlessIdle(unittest.TestCase):
    def setUp(self):
        self.saved = (st._ext_save_locked, st._runs_save_locked, st._run_note_locked, dict(st._ext),
                      dict(st._ext_ended), ext.time.time, st.time.time, gm.scan, st._pid_gone)
        st._ext_save_locked = lambda: None
        st._runs_save_locked = lambda: None
        st._run_note_locked = lambda *a, **k: None
        st._ext.clear()
        self.clock = [NOW]
        ext.time.time = lambda: self.clock[0]
        st.time.time = lambda: self.clock[0]
        gm.scan = lambda cut: []
        self.dead = set()
        st._pid_gone = lambda pid, pstart: pid in self.dead

    def tearDown(self):
        (st._ext_save_locked, st._runs_save_locked, st._run_note_locked, e, ended,
         ext.time.time, st.time.time, gm.scan, st._pid_gone) = self.saved
        st._ext.clear(); st._ext.update(e)
        st._ext_ended.clear(); st._ext_ended.update(ended)

    def feed(self, ev, t, **kw):
        req = {"platform": "cursor", "session_id": "c1", "event": ev, "cwd": "/w", "ts": t}
        req.update(kw)
        return st.ext_ingest(req)

    def state_at(self, t):
        self.clock[0] = t
        st.ext_gone_check(t)
        return st._ext[("cursor", "c1")]["state"]

    def test_pidless_idle_31min_done(self):
        self.feed("Stop", NOW)
        self.assertEqual(self.state_at(NOW + 31 * 60), "done")
        self.assertFalse(st._ext[("cursor", "c1")].get("goneWhy"))

    def test_pidless_idle_29min_wait(self):
        self.feed("Stop", NOW)
        self.assertEqual(self.state_at(NOW + 29 * 60), "wait")

    def test_pid_alive_idle_20h_wait(self):
        self.feed("Stop", NOW, pid=4242, host=st._HOST)
        self.assertEqual(self.state_at(NOW + 20 * 3600), "wait")

    def test_new_event_after_done_live_again(self):
        self.feed("Stop", NOW)
        self.assertEqual(self.state_at(NOW + 31 * 60), "done")
        self.feed("UserPromptSubmit", NOW + 32 * 60)
        self.assertEqual(self.state_at(NOW + 32 * 60), "think")
        self.feed("SessionStart", NOW + 40 * 60)   # Stop-less events also revive it
        self.assertEqual(self.state_at(NOW + 40 * 60), "wait")

    def test_unknown_event_revives_to_wait(self):
        self.feed("Stop", NOW)
        self.state_at(NOW + 31 * 60)
        self.feed("SomethingNew", NOW + 32 * 60)
        self.assertEqual(self.state_at(NOW + 32 * 60), "wait")

    def test_pending_never_done(self):
        self.feed("Notification", NOW)
        self.assertEqual(self.state_at(NOW + 2 * 3600), "ask")

    def test_pidless_24h_still_dropped(self):
        self.feed("Stop", NOW)
        self.state_at(NOW + 31 * 60)
        self.clock[0] = NOW + st.EXT_TTL_S + 60
        with st._ext_lock:
            st._ext_prune_locked(self.clock[0])
        self.assertNotIn(("cursor", "c1"), st._ext)

    def test_row_view_shows_done(self):
        self.feed("Stop", NOW)
        self.clock[0] = NOW + 31 * 60
        r = next(x for x in ext.ext_rows() if x["sid"] == "c1")
        self.assertEqual((r["state"], r["goneWhy"]), ("done", ""))


if __name__ == "__main__":
    unittest.main()
