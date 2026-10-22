"""Gemini runs launched by a Claude session: hook passthrough, persistence across SessionEnd, child rows."""
import importlib.util
import json
import os
import shutil
import tempfile
import unittest

from tests._load import sidereus

ext = sidereus("ext")
st = sidereus("ext_store")   # store internals are patched on their owner
te = sidereus("timeline_ext")
GM = ext.PLAT_MODS["gemini"]
gm = sidereus("plat_gemini")

HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ext-hooks", "ext_hook.py")
_spec = importlib.util.spec_from_file_location("ext_hook_t", HOOK)
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)

T0 = int(__import__("time").time()) - 300     # recent: ext_ingest prunes entries older than 24h
PAR = "11111111-2222-3333-4444-555555555555"
SECRET = "SECRET-PROMPT-TEXT"


class HookParent(unittest.TestCase):
    def test_env_to_payload(self):
        saved = dict(os.environ)
        try:
            os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
            os.environ["SIDEREUS_PARENT_SID"] = PAR
            out, _ = hook.build("gemini", {"hook_event_name": "SessionStart", "session_id": "g1",
                                           "prompt": SECRET})
            self.assertEqual(out["parent"], PAR)
            self.assertNotIn(SECRET, json.dumps(out))
            os.environ.pop("SIDEREUS_PARENT_SID")
            out, _ = hook.build("gemini", {"hook_event_name": "SessionStart", "session_id": "g1"})
            self.assertNotIn("parent", out)
        finally:
            os.environ.clear()
            os.environ.update(saved)

    def test_claude_env_fallback_and_validation(self):
        self.assertEqual(hook.parent_sid({"CLAUDE_CODE_SESSION_ID": PAR}), PAR)
        self.assertEqual(hook.parent_sid({"SIDEREUS_PARENT_SID": "x; rm -rf /"}), "")


class Runs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.saved = (st._ext_save_locked, st.EXT_RUNS_FILE, dict(ext._ext), dict(ext._runs), te._ext)
        st._ext_save_locked = lambda: None
        st.EXT_RUNS_FILE = os.path.join(self.tmp, "ext-runs.json")
        ext._ext.clear()
        ext._runs.clear()
        te._ext = ext._ext
        self.p_chats = gm.scan
        gm.scan = lambda cut: []

    def tearDown(self):
        st._ext_save_locked, st.EXT_RUNS_FILE, e, r, te._ext = self.saved
        gm.scan = self.p_chats
        ext._ext.clear(); ext._ext.update(e)
        ext._runs.clear(); ext._runs.update(r)
        shutil.rmtree(self.tmp)

    def feed(self, ev, t, **kw):
        req = {"platform": "gemini", "session_id": "g1", "event": ev, "cwd": "/tmp/scratch",  # nosec B108 -- fake path, never touched
               "ts": t, "parent": PAR, "prompt": SECRET}
        req.update(kw)
        return ext.ext_ingest(req)

    def test_survives_session_end_and_reload(self):
        self.feed("SessionStart", T0, model="gemini-2.5-flash")
        self.feed("UserPromptSubmit", T0 + 1)
        self.feed("Stop", T0 + 9)
        self.feed("SessionEnd", T0 + 10)
        self.assertNotIn(("gemini", "g1"), ext._ext)
        ext._runs.clear()
        st._runs_load()
        r = ext._runs["g1"]
        self.assertEqual((r["parent"], r["start"], r["end"], r["state"], r["model"]),
                         (PAR, T0, T0 + 10, "done", "gemini-2.5-flash"))
        with open(st.EXT_RUNS_FILE, encoding="utf-8") as f:
            self.assertNotIn(SECRET, f.read())

    def test_not_top_level_but_under_parent(self):
        self.feed("SessionStart", T0)
        self.assertEqual(ext.ext_rows(), [])
        rows = [{"plat": "cc", "sid": PAR}, {"plat": "cc", "sid": "other"}]
        ext.ext_children(rows, now=T0 + 5)
        self.assertEqual(rows[0]["gms"][0]["sid"], "g1")
        self.assertFalse(rows[0]["gms"][0]["done"])
        self.assertNotIn("gms", rows[1])
        self.feed("SessionEnd", T0 + 10)
        rows = [{"plat": "cc", "sid": PAR}]
        ext.ext_children(rows, now=T0 + 20)
        self.assertNotIn("gms", rows[0])                  # finished: gone from the drawer ...
        tr = te._plat_rows(GM, T0 - 60, T0 + 60, {PAR: ("/w/claude", "claude-proj")})
        self.assertEqual([(r["tid"], r["fin"], r["end"] - r["start"]) for r in tr], [("ext:gm|g1", 1, 10)])   # ... still on the timeline

    def test_timeline_child_row(self):
        self.feed("SessionStart", T0)
        self.feed("SessionEnd", T0 + 30)
        rows = te._plat_rows(GM, T0 - 60, T0 + 60, {PAR: ("/w/claude", "claude-proj")})
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertNotEqual(r.get("kind"), "sess")        # agent-kind: hangs under the Claude head
        self.assertEqual((r["cwd"], r["proj"], r["plat"], r["type"], r["parent"]),
                         ("/w/claude", "claude-proj", "gm", "gemini -p", PAR))
        self.assertEqual((r["start"], r["end"], r["fin"], r["run"]), (T0, T0 + 30, 1, False))
        self.assertNotIn(SECRET, json.dumps(r))
        self.assertEqual(te._plat_rows(GM, T0 + 100, T0 + 200, {}), [])   # outside the window

    def test_interactive_unchanged(self):
        ext.ext_ingest({"platform": "gemini", "session_id": "solo", "event": "SessionStart",
                        "cwd": "/w/x", "ts": T0})
        self.assertEqual([r["sid"] for r in ext.ext_rows()], ["solo"])
        self.assertEqual(ext._runs, {})


if __name__ == "__main__":
    unittest.main()
