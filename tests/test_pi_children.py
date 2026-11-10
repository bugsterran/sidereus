"""pi subagent children (`pi -p --no-session` with a pi parent sid): hang under the pi row, labelled by agent name."""
import os
import shutil
import tempfile
import unittest

from tests._load import sidereus

ext = sidereus("ext")
st = sidereus("ext_store")   # store internals are patched on their owner
pr = sidereus("ext_presence")
PI = ext.PLAT_MODS["pi"]

NOW = 1800000000.0
PAR = "0199aaaa-bbbb-7ccc-8ddd-0000000000p1"
KID = "0199aaaa-bbbb-7ccc-8ddd-0000000000k1"
GPAR = "11111111-2222-3333-4444-555555555555"
CWD = "/w/pi-proj"


class PiChildren(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.saved = (st._ext_save_locked, st.EXT_RUNS_FILE, dict(ext._ext), dict(ext._runs), ext.time.time,
                      PI.session_msgs, pr._cands, dict(st._ext_ended))
        st._ext_save_locked = lambda: None
        st.EXT_RUNS_FILE = os.path.join(self.tmp, "ext-runs.json")
        ext._ext.clear()
        ext._runs.clear()
        st._ext_ended.clear()
        ext.time.time = lambda: NOW
        PI.session_msgs = lambda path: None
        self.cands = []
        pr._cands = lambda plat, now: list(self.cands) if plat == "pi" else []

    def tearDown(self):
        (st._ext_save_locked, st.EXT_RUNS_FILE, e, r, ext.time.time, PI.session_msgs, pr._cands, d) = self.saved
        ext._ext.clear(); ext._ext.update(e)
        ext._runs.clear(); ext._runs.update(r)
        st._ext_ended.clear(); st._ext_ended.update(d)
        shutil.rmtree(self.tmp)

    def feed(self, ev, sid=KID, plat="pi", **kw):
        req = {"platform": plat, "session_id": sid, "event": ev, "cwd": CWD, "ts": NOW - 5}
        req.update(kw)
        return ext.ext_ingest(req)

    def test_R1_R2_R3_child_under_pi_parent_with_agent_name(self):
        self.feed("SessionStart", sid=PAR)
        self.feed("UserPromptSubmit", parent=PAR, agent_name="scout")
        self.feed("PreToolUse", parent=PAR, tool_name="read")
        top = ext.ext_rows()
        self.assertEqual([r["sid"] for r in top], [PAR])          # R1: the child is not its own top-level row
        ext.ext_children(top, now=NOW)
        g = top[0]["gms"]
        self.assertEqual([(x["sid"], x["cmd"], x["plat"], x["done"]) for x in g], [(KID, "scout", "pi", False)])   # R2/R3
        self.assertEqual(ext._runs[KID]["agent"], "scout")

    def test_R3_bad_agent_name_falls_back_to_cli_label(self):
        self.feed("SessionStart", sid=PAR)
        self.feed("UserPromptSubmit", parent=PAR, agent_name="scout\nrm -rf /")
        rows = ext.ext_rows()
        ext.ext_children(rows, now=NOW)
        self.assertEqual(rows[0]["gms"][0]["cmd"], PI.CHILD_LABEL)
        self.assertNotIn("agent", ext._runs[KID])

    def test_R4_parentless_pi_p_is_top_level(self):
        self.feed("UserPromptSubmit", agent_name="scout")
        rows = ext.ext_rows()
        self.assertEqual([r["sid"] for r in rows], [KID])
        ext.ext_children(rows, now=NOW)
        self.assertNotIn("gms", rows[0])

    def test_R2_hookless_parent_stays_visible_beside_child_in_same_cwd(self):
        self.cands = [{"sid": PAR, "cwd": CWD, "start": NOW - 60, "mtime": NOW - 5}]
        self.feed("UserPromptSubmit", parent=PAR, agent_name="scout")
        pres = pr.ext_presence_rows(NOW)
        self.assertEqual([r["sid"] for r in pres], [PAR])
        ext.ext_children(pres, now=NOW)
        self.assertEqual([x["cmd"] for x in pres[0]["gms"]], ["scout"])

    def test_R2_ended_child_follows_gemini_retention(self):
        # Same rule as a finished `gemini -p` under Claude: it leaves the drawer and stays on the timeline (`_runs`).
        self.feed("SessionStart", sid=PAR)
        self.feed("UserPromptSubmit", parent=PAR, agent_name="scout")
        self.feed("SessionEnd")
        rows = ext.ext_rows()
        self.assertEqual([r["sid"] for r in rows], [PAR])
        ext.ext_children(rows, now=NOW)
        self.assertNotIn("gms", rows[0])
        self.assertEqual((ext._runs[KID]["parent"], ext._runs[KID]["agent"], ext._runs[KID]["state"]),
                         (PAR, "scout", "done"))

    def test_gemini_child_still_under_claude_row(self):
        self.feed("UserPromptSubmit", sid="g1", plat="gemini", parent=GPAR)
        rows = [{"plat": "cc", "sid": GPAR}]
        ext.ext_children(rows, now=NOW)
        self.assertEqual([(x["sid"], x["cmd"]) for x in rows[0]["gms"]], [("g1", "gemini -p")])

    def test_child_counted_once_on_duplicate_parent_rows(self):
        self.feed("UserPromptSubmit", parent=PAR, agent_name="scout")
        rows = [{"plat": "pi", "sid": PAR}, {"plat": "pi", "sid": PAR}]
        ext.ext_children(rows, now=NOW)
        self.assertEqual((len(rows[0]["gms"]), "gms" in rows[1]), (1, False))


if __name__ == "__main__":
    unittest.main()
