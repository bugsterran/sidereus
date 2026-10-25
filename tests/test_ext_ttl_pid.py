"""External CLI rows past EXT_TTL_S: a row with a live pid stays (ext_gone_check is its exit); pid-less rows age out."""
import json
import os
import tempfile
import unittest

from tests._clock import NOW, frozen
from tests._load import sidereus

st = sidereus("ext_store")

IDLE = 30 * 3600


def _row(pid=0, **kw):
    v = {"cwd": "/w", "state": "wait", "firstSeen": NOW - IDLE, "lastSeen": NOW - IDLE}
    if pid:
        v.update(pid=pid, pstart="Sat Oct 24 17:00:00 2026")
    v.update(kw)
    return v


class TtlPid(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.saved = (dict(st._ext), dict(st._ext_ended), st._ext_save_locked, st._pid_gone,
                      st._run_note_locked, st._runs_save_locked, st.EXT_FILE)
        st._ext.clear()
        st._ext_save_locked = lambda: None
        st._run_note_locked = lambda *a, **k: None
        st._runs_save_locked = lambda: None
        st.EXT_FILE = os.path.join(self.tmp, "ext-sessions.json")
        self.dead = set()
        st._pid_gone = lambda pid, pstart: pid in self.dead

    def tearDown(self):
        (ext, ended, st._ext_save_locked, st._pid_gone, st._run_note_locked,
         st._runs_save_locked, st.EXT_FILE) = self.saved
        st._ext.clear()
        st._ext.update(ext)
        st._ext_ended.clear()
        st._ext_ended.update(ended)

    def test_live_pid_idle_kept(self):
        st._ext[("cursor", "a")] = _row(pid=12089)
        with frozen(st):
            st.ext_gone_check(NOW)
            with st._ext_lock:
                st._ext_prune_locked(NOW)
        self.assertIn(("cursor", "a"), st._ext)
        self.assertFalse(st._ext[("cursor", "a")].get("gone"))

    def test_dead_pid_gone_then_dropped(self):
        st._ext[("gemini", "b")] = _row(pid=99698)
        self.dead.add(99698)
        st.ext_gone_check(NOW)
        self.assertEqual(st._ext[("gemini", "b")]["state"], "gone")
        with st._ext_lock:
            st._ext_prune_locked(NOW)
        self.assertIn(("gemini", "b"), st._ext)       # shown as «Disconnected» during the grace
        st.ext_gone_check(NOW + st.EXT_GONE_GRACE_S + 1)
        self.assertNotIn(("gemini", "b"), st._ext)

    def test_no_pid_idle_dropped(self):
        st._ext[("cursor", "c")] = _row()
        with st._ext_lock:
            st._ext_prune_locked(NOW)
        self.assertNotIn(("cursor", "c"), st._ext)

    def test_no_pid_pending_kept(self):
        st._ext[("cursor", "d")] = _row(state="ask")
        with st._ext_lock:
            st._ext_prune_locked(NOW)
        self.assertIn(("cursor", "d"), st._ext)

    def test_load_old_pid_row(self):
        recs = [dict(_row(pid=12089), platform="cursor", session_id="e"),
                dict(_row(), platform="cursor", session_id="f")]
        with open(st.EXT_FILE, "w", encoding="utf-8") as f:
            json.dump(recs, f)
        with frozen(st):
            st._ext_load()
        self.assertIn(("cursor", "e"), st._ext)
        self.assertNotIn(("cursor", "f"), st._ext)


if __name__ == "__main__":
    unittest.main()
