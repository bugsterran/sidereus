"""Work popup: total edit-body budget — a 400-step MultiEdit session stays under the cap, metadata of every step kept."""
import json
import os
import tempfile
import unittest

from tests._load import sidereus

st = sidereus("steps")
wk = sidereus("work")


def _session(fp, n):
    with open(fp, "w") as f:
        for i in range(n):
            eds = [{"old_string": "o" * 7000, "new_string": "n" * 7000} for _ in range(25)]
            f.write(json.dumps({"type": "assistant", "timestamp": "2026-10-05T00:%02d:%02d.000Z" % (i // 60 % 60, i % 60),
                                "message": {"content": [{"type": "tool_use", "id": "t%d" % i, "name": "MultiEdit",
                                                         "input": {"file_path": "/x/f%d.py" % i, "edits": eds}}]}}) + "\n")


class EditBudget(unittest.TestCase):
    def setUp(self):
        fd, self.fp = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        _session(self.fp, 400)
        self._saved = (wk._allowed_cwds, wk._sid_path, st._git_root, wk.SESS_TAIL)
        wk._allowed_cwds = lambda ttl=5: {"/x": {"project": "x"}}
        wk._sid_path = lambda cwd, sid: self.fp
        st._git_root = lambda d: None
        wk.SESS_TAIL = 0          # read the whole synthetic file

    def tearDown(self):
        wk._allowed_cwds, wk._sid_path, st._git_root, wk.SESS_TAIL = self._saved
        os.unlink(self.fp)

    def test_400_steps_under_cap(self):
        d = wk.session_work("/x", sid="abcdef12-0000")
        self.assertTrue(d["ok"], d)
        size = len(json.dumps(d, ensure_ascii=False).encode())
        self.assertLess(size, st.AGENT_EDIT_BUDGET + 200_000)
        self.assertEqual(len(d["steps"]), 400)
        self.assertTrue(all(s["tool"] == "MultiEdit" and s.get("t") for s in d["steps"]))
        self.assertGreater(d["cutEdits"], 0)
        self.assertTrue(d["steps"][-1].get("edits"))        # newest keeps its bodies
        self.assertTrue(d["steps"][0].get("editCut"))       # oldest lost them
        self.assertNotIn("edits", d["steps"][0])

    def test_small_session_uncut(self):
        steps = [{"tool": "Edit", "edit": {"path": "p", "old": "a", "new": "b"}}]
        self.assertEqual(st._cap_edit_bodies(steps), 0)
        self.assertIn("edit", steps[0])


if __name__ == "__main__":
    unittest.main()
