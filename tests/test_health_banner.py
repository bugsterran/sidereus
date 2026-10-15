"""Health strip keeps only actionable warnings (BANNER_KEEP) with what to do; the rest go to `diag`.
selfcheck makes no decision on rows whose account's official lookup is unknown.

No live files or clock: sessions_health globals (_WARN_LOG, _THREAD_DEAD, time, agent_view, ...) are replaced.
"""
import types
import unittest

from tests._load import sidereus
from tests.test_i18n_srv2 import PARTS

ss = sidereus("sessions_health")
W = sidereus("warn")

NOW = 90_000.0
A = "aa11aa11-0000-4000-8000-000000000000"
B = "bb22bb22-0000-4000-8000-000000000000"


def _w(key, msg="m"):
    return {"at": NOW - 5, "key": key, "msg": msg, "msgEn": msg, "tv": [{"msg": msg}]}


class _Patch(unittest.TestCase):
    NAMES = ()

    def setUp(self):
        g = ss.health.__globals__
        self.saved = {k: g[k] for k in self.NAMES}
        self.addCleanup(g.update, self.saved)
        self.g = g


class Banner(_Patch):
    NAMES = ("_WARN_LOG", "_THREAD_DEAD", "_SOFT", "_stale", "time", "ext_hook_check")

    def setUp(self):
        super().setUp()
        self.g["time"] = types.SimpleNamespace(time=lambda: NOW)
        self.g["ext_hook_check"] = lambda: None
        self.g["_SOFT"], self.g["_stale"], self.g["_THREAD_DEAD"] = {}, {}, {}

    def run_health(self, *keys):
        self.g["_WARN_LOG"] = [_w(k) for k in keys]
        return ss.health()

    def test_demoted_keys_go_to_diag(self):
        h = self.run_health("live-slow", "loop:quota", "ccusage-missing", "agents-slow", "failscan:x", "selfcheck-mon")
        self.assertEqual(h["warns"], [])
        self.assertEqual([d["key"] for d in h["diag"]],
                         ["live-slow", "loop:quota", "ccusage-missing", "agents-slow", "failscan:x", "selfcheck-mon"])

    def test_kept_keys_carry_action(self):
        h = self.run_health("thread:wkuse", "agents", "agents-nobin", "pref:x", "bus", "hooks:gm", "selfcheck-live")
        by = {w["key"]: w for w in h["warns"]}
        self.assertEqual(set(by), {"thread:wkuse", "agents", "agents-nobin", "pref:x", "bus", "hooks:gm", "selfcheck-live"})
        self.assertEqual(by["thread:wkuse"]["tv"][-1], {"msg": "restart Sidereus"})
        self.assertTrue(by["agents"]["msgEn"].endswith("in a terminal to see why"))
        self.assertEqual(by["bus"]["tv"][-1]["msg"], "check free disk space and permissions of the data folder")
        self.assertEqual(by["hooks:gm"]["tv"], [{"msg": "m"}])          # its text already says what to do
        self.assertEqual(h["diag"], [])

    def test_log_entry_not_mutated(self):
        self.run_health("bus")
        self.assertEqual(self.g["_WARN_LOG"][0]["tv"], [{"msg": "m"}])

    def test_every_action_has_ko(self):
        acts = {a for a in ss.BANNER_KEEP.values() if a}
        self.assertEqual(acts - set(PARTS), set())


class SelfcheckAccounts(_Patch):
    NAMES = ("agent_view", "agent_view_unknown", "sid_alive", "mailbox_watches", "warn_once", "SELF_GRACE_S",
             "clear_links")

    def setUp(self):
        super().setUp()
        self.warns = []
        self.g["clear_links"] = lambda: []
        self.g["agent_view"] = lambda: {}
        self.g["agent_view_unknown"] = lambda: {"work"}
        self.g["sid_alive"] = lambda sid: False
        self.g["mailbox_watches"] = lambda: None
        self.g["warn_once"] = lambda key, msg, **kw: self.warns.append((key, W._fill(msg, kw.get("vars"))))
        self.g["SELF_GRACE_S"] = 0
        since = dict(ss._self_since)
        ss._self_since.clear()
        self.addCleanup(lambda: (ss._self_since.clear(), ss._self_since.update(since)))

    def test_failed_account_row_not_flagged(self):
        ss.selfcheck([{"sid": A, "acct": "work", "state": "busy"}, {"sid": B, "acct": "", "state": "busy"}])
        live = [m for k, m in self.warns if k == "selfcheck-live"]
        self.assertEqual(len(live), 1)
        self.assertIn(B[:8], live[0])
        self.assertNotIn(A[:8], live[0])
        self.assertTrue(live[0].endswith("check those sessions in their terminal"))


if __name__ == "__main__":
    unittest.main()
