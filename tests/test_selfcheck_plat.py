"""selfcheck compares only Claude rows against the official list; ext rows (gm/cx) are not ghosts."""
import unittest

from tests._load import sidereus

ss = sidereus("sessions_health")
W = sidereus("warn")

GM = "e6003e15-0000-4000-8000-000000000000"
CC = "cc11cc11-0000-4000-8000-000000000000"


class SelfcheckPlat(unittest.TestCase):
    def setUp(self):
        g = ss.selfcheck.__globals__
        self.saved = {k: g[k] for k in ("agent_view", "sid_alive", "mailbox_watches", "warn_once", "SELF_GRACE_S", "clear_links")}
        self.warns = []
        g["clear_links"] = lambda: []   # sess_clear reads DATA_DIR; keep the test off live files
        g["agent_view"] = lambda: {}
        g["sid_alive"] = lambda sid: False
        g["mailbox_watches"] = lambda: None
        g["warn_once"] = lambda key, msg, **kw: self.warns.append((key, W._fill(msg, kw.get("vars"))))
        g["SELF_GRACE_S"] = 0
        self.since = dict(ss._self_since)
        ss._self_since.clear()

    def tearDown(self):
        ss.selfcheck.__globals__.update(self.saved)
        ss._self_since.clear()
        ss._self_since.update(self.since)

    def live(self):
        return [m for k, m in self.warns if k == "selfcheck-live"]

    def test_gemini_row_not_warned(self):
        ss.selfcheck([{"sid": GM, "plat": "gm", "state": "busy"}])
        self.assertEqual(self.live(), [])

    def test_missing_claude_row_still_warned(self):
        ss.selfcheck([{"sid": GM, "plat": "gm", "state": "busy"},
                      {"sid": CC, "plat": None, "state": "busy"}])
        live = self.live()
        self.assertEqual(len(live), 1)
        self.assertIn(CC[:8], live[0])
        self.assertNotIn(GM[:8], live[0])


if __name__ == "__main__":
    unittest.main()
