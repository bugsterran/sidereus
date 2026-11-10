"""pi work-log popup: steps and replies from the pi session file (R1), empty state without one (R2),
no pi message text on list/timeline/metadata paths (R3)."""
import json
import os
import shutil
import tempfile
import types
import unittest
from unittest import mock

from tests._load import sidereus

pi = sidereus("plat_pi")
st = sidereus("ext_store")
ext = sidereus("ext")
pr = sidereus("ext_presence")
wk = sidereus("work")

NOW = 1800000000.0
CLOCK = types.SimpleNamespace(time=lambda: NOW)   # fixed clock for the store/ingest modules
SID = "0199aaaa-bbbb-7ccc-8ddd-0000000000e7"
MARK = "PIWORK-MARK"
FAKE = "ghp_" + "x" * 36          # dummy token shape: must be masked in the popup


def _lines(cwd):
    ts = lambda s: "2027-01-15T08:00:%02d.000Z" % s
    return [
        {"type": "session", "version": 3, "id": SID, "timestamp": ts(0), "cwd": cwd},
        {"type": "message", "id": "s1", "timestamp": ts(1), "message": {"role": "system", "content": MARK + "-sys"}},
        {"type": "message", "id": "u1", "timestamp": ts(2), "message": {"role": "user", "content": MARK + "-user"}},
        {"type": "message", "id": "a1", "timestamp": ts(3), "message": {"role": "assistant", "content": [
            {"type": "thinking", "thinking": MARK + "-think"},
            {"type": "text", "text": MARK + "-asst"},
            {"type": "toolCall", "id": "k1", "name": "bash", "arguments": {"command": "echo " + FAKE + " " + MARK + "-cmd"}},
            {"type": "toolCall", "id": "k2", "name": "edit", "arguments": {"path": "a.py", "edits": [
                {"oldText": MARK + "-old", "newText": MARK + "-new"}]}},
            {"type": "toolCall", "id": "k3", "name": "mytool", "arguments": {"blob": MARK + "-blob"}}]}},
        {"type": "message", "id": "t1", "timestamp": ts(4), "message": {
            "role": "toolResult", "toolCallId": "k1", "toolName": "bash", "isError": False,
            "content": [{"type": "text", "text": MARK + "-out"}]}},
        {"type": "message", "id": "t2", "timestamp": ts(5), "message": {
            "role": "toolResult", "toolCallId": "k2", "toolName": "edit", "isError": True,
            "content": [{"type": "text", "text": MARK + "-err"}]}},
        {"type": "compaction", "id": "c1", "timestamp": ts(6), "summary": MARK + "-summary"},
    ]


class WorkPi(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-work-pi-")
        self.root = os.path.join(self.tmp, "agent")
        self.cwd = os.path.join(self.tmp, "proj")
        os.makedirs(os.path.join(self.cwd, ".git"))              # tmp repo: edit target resolves to `wrote`
        d = os.path.join(self.root, "sessions", "--w-proj--")
        os.makedirs(d)
        self.path = os.path.join(d, "2027-01-15T08-00-00-000Z_%s.jsonl" % SID)
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("".join(json.dumps(x) + "\n" for x in _lines(self.cwd)))
        self._ext, self._ended = dict(st._ext), dict(st._ext_ended)
        st._ext.clear()
        st._ext_ended.clear()
        self.p = [mock.patch.object(pi, "root", lambda: self.root),
                  mock.patch.object(st, "_ext_save_locked", lambda: None),
                  mock.patch.object(st, "time", CLOCK), mock.patch.object(ext, "time", CLOCK)]
        for p in self.p:
            p.start()
        pi._cache.clear()

    def tearDown(self):
        for p in self.p:
            p.stop()
        st._ext.clear()
        st._ext.update(self._ext)
        st._ext_ended.clear()
        st._ext_ended.update(self._ended)
        pi._cache.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def feed(self, sid, plat="pi"):
        return ext.ext_ingest({"platform": plat, "session_id": sid, "event": "SessionStart", "cwd": self.cwd})

    def test_r1_steps_and_replies(self):
        self.feed(SID)
        w = wk.ext_work_log("pi", SID, NOW)
        self.assertTrue(w["ok"] and w["log"])
        self.assertEqual([s["tool"] for s in w["steps"]], ["bash", "edit", "mytool"])
        bash, edit, other = w["steps"]
        self.assertIn(MARK + "-cmd", bash["arg"])
        self.assertNotIn(FAKE, json.dumps(w))                     # redacted
        self.assertEqual(bash["res"]["lines"], [MARK + "-out"])
        self.assertFalse(bash["res"]["err"])
        self.assertTrue(edit["res"]["err"])
        self.assertEqual(edit["edits"], [{"old": MARK + "-old", "new": MARK + "-new"}])
        self.assertEqual(edit["wrote"], [{"cwd": self.cwd, "path": "a.py"}])
        self.assertNotIn(MARK + "-blob", json.dumps(other))     # arg not on the allow-list
        self.assertEqual([s["text"] for s in w["says"]], [MARK + "-asst"])
        self.assertEqual(w["prompt"], MARK + "-user")
        dump = json.dumps(w)
        for gone in ("-think", "-sys", "-summary"):
            self.assertNotIn(MARK + gone, dump)
        self.assertEqual(w["type"], "Pi · " + SID[:8])

    def test_r2_no_session_file(self):
        self.feed("pi-nosession-1")
        w = wk.ext_work_log("pi", "pi-nosession-1", NOW)
        self.assertTrue(w["ok"])
        self.assertEqual(w["steps"], [])
        self.assertNotIn("log", w)

    def test_symlink_outside_root_refused(self):
        out = os.path.join(self.tmp, "outside.jsonl")
        shutil.move(self.path, out)
        os.symlink(out, self.path)
        pi._cache.clear()
        self.feed(SID)
        w = wk.ext_work_log("pi", SID, NOW)
        self.assertTrue(w["ok"])
        self.assertNotIn("log", w)
        self.assertEqual(wk._pi_file(SID), "")

    def test_bad_sid(self):
        self.assertFalse(wk.ext_work_log("pi", "../x", NOW)["ok"])
        self.assertEqual(wk._pi_file("../x"), "")

    def test_r3_metadata_paths_carry_no_text(self):
        self.feed(SID)
        dump = json.dumps([pi.scan(0.0), pr.ext_work_any("pi", SID, NOW)], default=str)
        self.assertNotIn(MARK, dump)

    def test_other_platforms_unchanged(self):
        self.feed("gm-a", plat="gemini")
        self.assertEqual(json.dumps(wk.ext_work_log("gm", "gm-a", NOW), sort_keys=True),
                         json.dumps(pr.ext_work_any("gm", "gm-a", NOW), sort_keys=True))


if __name__ == "__main__":
    unittest.main()
