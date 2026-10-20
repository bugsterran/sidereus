"""sidereus/commit_link: commit detection, subagent attribution, cost window, incremental offsets, subject fallback."""
import json
import os
import tempfile
import types
import unittest

from tests._load import sidereus

cl = sidereus("commit_link")


def _asst(ts, mid, tok, tool=None):
    body = [{"type": "tool_use", "id": tool[0], "name": "Bash", "input": {"command": tool[1]}}] if tool else []
    return {"type": "assistant", "timestamp": ts, "cwd": "/w", "requestId": "r" + mid,
            "message": {"id": mid, "model": "claude-opus-5", "content": body,
                        "usage": {"input_tokens": tok, "output_tokens": 0}}}


def _res(ts, tuid, text, err=False):
    return {"type": "user", "timestamp": ts, "cwd": "/w",
            "message": {"content": [{"type": "tool_result", "tool_use_id": tuid, "content": text, "is_error": err}]}}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.saved = (cl.CL_ROOT, cl.CL_INDEX, dict(cl._cl))
        cl.CL_ROOT = os.path.join(self.tmp, "projects")
        cl.CL_INDEX = os.path.join(self.tmp, "idx.json")
        cl._cl.update({"files": {}, "at": 0.0, "loaded": False, "busy": False, "more": False, "bg": False,
                       "saved": 0.0, "dirty": False})

    def tearDown(self):
        cl.CL_ROOT, cl.CL_INDEX = self.saved[0], self.saved[1]
        cl._cl.clear()
        cl._cl.update(self.saved[2])

    def write(self, rel, rows, mode="w"):
        fp = os.path.normpath(os.path.join(cl.CL_ROOT, rel))   # the scan keys files by OS-separated glob paths
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, mode, encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        return fp

    def recs(self, fp):
        return cl._cl["files"][fp]["cm"]


class Detect(unittest.TestCase):
    def one(self, cmd, out, err=False):
        return cl._cl_records(cmd, "/w", out, err, 100.0)

    def test_plain(self):
        r = self.one('git add -A && git commit -m "Add x"', "[master abc1234] Add x\n 1 file changed")
        self.assertEqual([(x["sha"], x["subj"], x["dir"]) for x in r], [("abc1234", "Add x", "/w")])

    def test_dash_C_and_cd(self):
        self.assertEqual(self.one("git -C /repo/a commit -m y", "[main 1234567] y")[0]["dir"], os.path.normpath("/repo/a"))
        self.assertEqual(self.one("cd sub && git commit -m y", "[main 1234567] y")[0]["dir"], os.path.normpath("/w/sub"))

    def test_amend_and_root(self):
        self.assertEqual(self.one("git commit --amend --no-edit", "[master def5678] y")[0]["sha"], "def5678")
        self.assertEqual(self.one("git commit -m init", "[master (root-commit) 0a1b2c3] init")[0]["sha"], "0a1b2c3")

    def test_heredoc_quiet(self):
        r = self.one("git commit -q -F - <<'EOF' && git log -1\nSubj here\n\nbody\nEOF", "")
        self.assertEqual((r[0]["sha"], r[0]["subj"]), ("", "Subj here"))
        r = self.one('git commit -q -m "$(cat <<\'EOF\'\nOther subj\n\nCo-Authored-By: x\nEOF\n)"', "")
        self.assertEqual(r[0]["subj"], "Other subj")

    def test_failed_none(self):
        self.assertEqual(self.one('git commit -m "x"', "nothing to commit, working tree clean"), [])
        self.assertEqual(self.one('git commit -q -m "x"', "pre-commit hook failed", err=True), [])
        self.assertEqual(self.one("git status", "[master abc1234] x"), [])


class Scan(Base):
    def test_cost_window_and_offsets(self):
        rows = [_asst("2026-09-20T00:00:00Z", "m1", 100),
                _asst("2026-09-20T00:01:00Z", "m2", 50, ("t1", 'git commit -m "A"')),
                _res("2026-09-20T00:01:05Z", "t1", "[master aaaaaaa] A")]
        fp = self.write("-w/s1.jsonl", rows)
        cl._cl_refresh()
        first = cl._cl["files"][fp]["off"]
        more = [_asst("2026-09-20T00:02:00Z", "m3", 7), _asst("2026-09-20T00:02:00Z", "m3", 7),   # duplicate line
                _asst("2026-09-20T00:03:00Z", "m4", 3, ("t2", 'git commit -m "B"')),
                _res("2026-09-20T00:03:05Z", "t2", "[master bbbbbbb] B")]
        self.write("-w/s1.jsonl", more, mode="a")
        cl._cl["at"] = 0
        nch, rd = cl._cl_refresh()
        self.assertEqual((nch, rd), (1, os.path.getsize(fp) - first))   # only the appended tail is read
        r = self.recs(fp)
        self.assertEqual([(x["sha"], x["tok"]) for x in r], [("aaaaaaa", 150), ("bbbbbbb", 10)])
        self.assertEqual(cl._cl["files"][fp]["sid"], "s1")

    def test_no_write_when_unchanged(self):
        fp = self.write("-w/s1.jsonl", [_asst("2026-09-20T00:00:00Z", "m1", 5, ("t1", 'git commit -m "A"')),
                                        _res("2026-09-20T00:00:02Z", "t1", "[master aaaaaaa] A")])
        saves, old = [], cl._atomic_write
        cl._atomic_write = lambda *a, **k: saves.append(a[0])
        try:
            cl._cl_refresh(now=1000.0)
            self.assertEqual(len(saves), 1)                           # new file + record
            cl._cl_refresh(now=1010.0)
            self.assertEqual(len(saves), 1)                           # nothing changed
            self.write("-w/s1.jsonl", [_asst("2026-09-20T00:01:00Z", "m2", 3)], mode="a")
            cl._cl_refresh(now=1020.0)
            self.assertEqual(len(saves), 1)                           # offsets only: deferred
            cl._cl_refresh(now=1020.0 + cl.CL_SAVE_S)
            self.assertEqual(len(saves), 2)                           # flushed after CL_SAVE_S
        finally:
            cl._atomic_write = old
        self.assertEqual(len(cl._cl["files"][fp]["keys"][0]), 8)     # compact dedup key

    def test_budget_resumes_same_result(self):
        rows = [_asst("2026-09-20T00:00:%02dZ" % i, "m%d" % i, 1) for i in range(20)] + \
               [_asst("2026-09-20T00:01:00Z", "mx", 2, ("t1", 'git commit -m "A"')),
                _res("2026-09-20T00:01:02Z", "t1", "[master aaaaaaa] A")]
        fp = self.write("-w/s1.jsonl", rows)
        n = 0
        while True:
            cl._cl_refresh(budget=300)
            n += 1
            if not cl._cl["more"]:
                break
        self.assertGreater(n, 2)
        self.assertEqual(cl._cl["files"][fp]["off"], os.path.getsize(fp))
        self.assertEqual([(x["sha"], x["tok"]) for x in self.recs(fp)], [("aaaaaaa", 22)])

    def test_subagent_attributed_to_parent(self):
        d = "-w/psid/subagents"
        fp = self.write(d + "/agent-x.jsonl", [_asst("2026-09-20T00:00:00Z", "m1", 5, ("t1", "git commit -m s")),
                                               _res("2026-09-20T00:00:02Z", "t1", "[wt ccccccc] s")])
        with open(fp[:-6] + ".meta.json", "w", encoding="utf-8") as f:
            json.dump({"agentType": "general-purpose", "toolUseId": "toolu_1"}, f)
        self.write("-w/psid.jsonl", [{"type": "user", "cwd": "/main", "timestamp": "2026-09-20T00:00:00Z",
                                      "message": {"content": "hi"}}, _asst("2026-09-20T00:00:00Z", "z", 1)])
        # pin the clock: fixture timestamps must stay inside the CL_DAYS scan/return window
        saved_time = cl.time
        cl.time = types.SimpleNamespace(time=lambda: 1789862400.0)   # 2026-09-20T00:00:00Z
        self.addCleanup(setattr, cl, "time", saved_time)
        cl._cl["files"].clear()
        cl._cl_refresh()
        ent = cl._cl["files"][fp]
        self.assertEqual((ent["sid"], ent["agent"], ent["tuid"]), ("psid", "general-purpose", "toolu_1"))
        old = (cl._branch_ok, cl._cl_log)
        cl._branch_ok, cl._cl_log = (lambda r: True), (lambda r: [])
        try:
            cl._cl["at"] = 9e18
            code, b = cl.commit_links("/w", "ccccccc")
        finally:
            cl._branch_ok, cl._cl_log = old
        self.assertEqual(code, 200)
        link = b["links"]["ccccccc"]
        self.assertEqual((link["sid"], link["agent"], link["tid"], link["cwd"]),
                         ("psid", "general-purpose", "toolu_1|psid", "/main"))


class Match(unittest.TestCase):
    def test_subject_fallback_window(self):
        recs = [{"sha": "", "subj": "Fix a", "ts": 1000.0, "rk": "/r"},
                {"sha": "", "subj": "Fix a", "ts": 5000.0, "rk": "/r"},
                {"sha": "", "subj": "Other", "ts": 1000.0, "rk": "/elsewhere"},
                {"sha": "1234567", "subj": "x", "ts": 10.0, "rk": "/x"}]
        commits = [("aaaaaaa", 990, "Fix a"), ("bbbbbbb", 900, "Other"), ("ccccccc", 100, "Fix a")]
        m = cl._cl_match(recs, commits, ["aaaaaaa", "bbbbbbb", "ccccccc", "1234567"], "/r")
        self.assertIs(m["aaaaaaa"], recs[0])
        self.assertNotIn("bbbbbbb", m)            # other repo
        self.assertNotIn("ccccccc", m)            # record 0 used; record 1 is too late
        self.assertIs(m["1234567"], recs[3])      # exact sha wins regardless of repo

    def test_same_subject_quiet_commits_30s_apart(self):
        # two `git commit -q` with one subject: each record must stay with its own commit
        recs = [{"sha": "", "subj": "Same", "ts": 1001.0, "rk": "/r"},
                {"sha": "", "subj": "Same", "ts": 1031.0, "rk": "/r"}]
        commits = [("ddddddd", 1030, "Same"), ("eeeeeee", 1000, "Same")]
        m = cl._cl_match(recs, commits, ["ddddddd", "eeeeeee"], "/r")
        self.assertIs(m["ddddddd"], recs[1])
        self.assertIs(m["eeeeeee"], recs[0])


if __name__ == "__main__":
    unittest.main()
