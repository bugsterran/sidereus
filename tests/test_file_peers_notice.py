"""hooks/file_peers_notice.py (PreToolUse): fake HTTP + temp state file — never the live viewer or data dir."""
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("file_peers_notice", os.path.join(ROOT, "hooks", "file_peers_notice.py"))
fpn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fpn)

ME = "11111111-aaaa-bbbb-cccc-000000000000"
FILE = "/w/proj/a.py"


def ed(sid8, live=True, ago=120, project="proj"):
    return {"sid8": sid8, "unit": "main", "agent": "main", "project": project, "agoSec": ago, "live": live}


class FilePeersNotice(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self._state, self._fetch = fpn.STATE, fpn.fetch
        fpn.STATE = os.path.join(self.d, ".file-peers-notice.json")
        self.resp, self.calls = None, []

        def fake(path, cwd):
            self.calls.append((path, cwd))
            return self.resp
        fpn.fetch = fake

    def tearDown(self):
        fpn.STATE, fpn.fetch = self._state, self._fetch
        shutil.rmtree(self.d, ignore_errors=True)

    def inp(self, tool="Edit", path=FILE, key="file_path"):
        return {"session_id": ME, "cwd": "/w/proj", "tool_name": tool, "tool_input": {key: path, "old_string": "SECRET"}}

    def file(self, *eds, unc=True):
        self.resp = {"ok": True, "path": FILE, "uncommitted": unc, "editors": list(eds)}

    def test_other_live_session_noticed(self):
        self.file(ed("22222222", ago=180))
        line = fpn.decide(self.inp(), now=1000)
        self.assertEqual(line, "Sidereus: 22222222 (proj) 3 min ago edited this file (uncommitted) — check before overwriting.")
        self.assertNotIn("SECRET", line)

    def test_own_session_and_dead_peers_silent(self):
        self.file(ed("11111111"), ed("33333333", live=False))
        self.assertEqual(fpn.decide(self.inp(), now=1000), "")

    def test_viewer_down_or_no_editors_silent(self):
        self.resp = None
        self.assertEqual(fpn.decide(self.inp(), now=1000), "")
        self.file()
        self.assertEqual(fpn.decide(self.inp(), now=1000), "")

    def test_non_edit_tool_skips_http(self):
        self.file(ed("22222222"))
        self.assertEqual(fpn.decide(self.inp(tool="Read"), now=1000), "")
        self.assertEqual(self.calls, [])

    def test_notebook_and_relative_path(self):
        self.file(ed("22222222", ago=30))
        line = fpn.decide(self.inp(tool="NotebookEdit", path="nb/x.ipynb", key="notebook_path"), now=1000)
        self.assertIn("<1 min ago", line)
        self.assertEqual(self.calls[0][0], os.path.normpath("/w/proj/nb/x.ipynb"))   # backslashes on Windows

    def test_dedup_within_ttl_then_again(self):
        self.file(ed("22222222"))
        self.assertTrue(fpn.decide(self.inp(), now=1000))
        self.assertEqual(fpn.decide(self.inp(), now=1000 + fpn.NOTICE_TTL_S - 1), "")
        self.assertTrue(fpn.decide(self.inp(), now=1000 + fpn.NOTICE_TTL_S))

    def test_new_peer_still_noticed_and_newest_row_used(self):
        self.file(ed("22222222"))
        fpn.decide(self.inp(), now=1000)
        self.file(ed("44444444", ago=60, project="other"), ed("22222222"), ed("44444444", ago=900))
        self.assertEqual(fpn.decide(self.inp(), now=1010),
                         "Sidereus: 44444444 (other) 1 min ago edited this file (uncommitted) — check before overwriting.")

    def test_state_pruned(self):
        with open(fpn.STATE, "w", encoding="utf-8") as f:
            json.dump({"old|x|y": 1.0, "bad": "z"}, f)
        self.file(ed("22222222"), unc=False)
        line = fpn.decide(self.inp(), now=1.0 + fpn.PRUNE_S)
        self.assertNotIn("uncommitted", line)
        with open(fpn.STATE, encoding="utf-8") as f:
            self.assertEqual(list(json.load(f)), ["%s|%s|22222222" % (ME, os.path.normpath(FILE))])

    def test_main_emits_pretooluse_json_never_deny(self):
        self.file(ed("22222222"))
        old_in, old_out = sys.stdin, sys.stdout
        sys.stdin, sys.stdout = io.StringIO(json.dumps(self.inp())), io.StringIO()
        try:
            fpn.main()
            out = sys.stdout.getvalue()
        finally:
            sys.stdin, sys.stdout = old_in, old_out
        hso = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(hso["hookEventName"], "PreToolUse")
        self.assertNotIn("permissionDecision", hso)
        self.assertTrue(hso["additionalContext"].startswith("Sidereus: 22222222"))

    def test_main_garbage_stdin_silent(self):
        old_in, old_out = sys.stdin, sys.stdout
        sys.stdin, sys.stdout = io.StringIO("not json"), io.StringIO()
        try:
            fpn.main()
            out = sys.stdout.getvalue()
        finally:
            sys.stdin, sys.stdout = old_in, old_out
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
