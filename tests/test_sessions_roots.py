"""Extra Claude roots (accounts) in sessions and popups: row acct keys, lookups across roots, path guard (temp dirs only)."""
import json
import os
import shutil
import subprocess
import tempfile
import types
import unittest
from unittest import mock

from tests import _load
from tests._node import node_e

SID = "0123abcd-0000-4000-8000-0000000000a1"
SLUG = "-w-proj"
NOW = 1_800_000_000.0   # fixed epoch: tests never read the real clock


def _w(fp, body="{}\n", mt=None):
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    with open(fp, "w") as f:
        f.write(body)
    if mt:
        os.utime(fp, (mt, mt))
    return fp


class RootsBase(unittest.TestCase):
    def setUp(self):
        self.cr = _load.sidereus("claude_roots")
        self.home = tempfile.mkdtemp(prefix="sidereus-sroots-")
        self.addCleanup(shutil.rmtree, self.home, True)
        self.prim = os.path.join(self.home, ".claude")
        self.pp = os.path.join(self.prim, "projects")
        self.work = os.path.join(self.home, ".claude-work")
        self.wp = os.path.join(self.work, "projects")
        os.makedirs(self.pp)
        os.makedirs(self.wp)
        ps = [mock.patch.object(self.cr, "SCAN_HOME", self.home),
              mock.patch.object(self.cr, "claude_home", lambda: self.prim),
              mock.patch.object(self.cr, "effective", lambda k: [])]
        for m in ("work", "cards", "live_probe", "live", "timeline", "history"):
            ps.append(mock.patch.object(_load.sidereus(m), "CLAUDE_PROJECTS", self.pp))
        for p in ps:
            p.start()
            self.addCleanup(p.stop)
        self.cr.reset()
        self.addCleanup(self.cr.reset)


class GuardTest(RootsBase):
    def test_accepts_only_under_a_projects_dir(self):
        W = _load.sidereus("work")
        ok = _w(os.path.join(self.wp, SLUG, SID + ".jsonl"))
        self.assertEqual(W._under_projects(ok), os.path.realpath(ok))
        self.assertTrue(W._under_projects(_w(os.path.join(self.pp, SLUG, SID + ".jsonl"))))
        # never the root dir itself, its parent, a `..` escape or an unregistered sibling
        bad = [_w(os.path.join(self.work, "settings.json")), self.wp, self.work, self.home,
               os.path.join(self.wp, "..", "settings.json"), os.path.join(self.wp, SLUG, "..", "..", ".credentials.json"),
               "/etc/passwd",
               _w(os.path.join(self.home, "other", "projects", SLUG, SID + ".jsonl"))]
        for b in bad:
            self.assertEqual(W._under_projects(b), "", b)

    def test_symlink_out_of_projects_refused(self):
        W = _load.sidereus("work")
        sec = _w(os.path.join(self.work, ".credentials.json"))
        ln = os.path.join(self.wp, SLUG, SID + ".jsonl")
        os.makedirs(os.path.dirname(ln))
        os.symlink(sec, ln)
        self.assertEqual(W._under_projects(ln), "")
        with mock.patch.object(W, "_sid_transcript", lambda s: ""):
            self.assertEqual(W._sid_path("/w/proj", SID), "")

    def test_sid_path_extra_root(self):
        W = _load.sidereus("work")
        fp = _w(os.path.join(self.wp, SLUG, SID + ".jsonl"))
        with mock.patch.object(W, "_sid_transcript", lambda s: ""):
            self.assertEqual(W._sid_path("/w/proj", SID), os.path.realpath(fp))
            self.assertEqual(W._sid_path("/w/proj", "../" + SID), "")


class LookupTest(RootsBase):
    def test_sid_transcript_newest_across_roots(self):
        lp = _load.sidereus("live_probe")
        now = NOW
        _w(os.path.join(self.pp, SLUG, SID + ".jsonl"), mt=now - 100)
        newer = _w(os.path.join(self.wp, SLUG, SID + ".jsonl"), mt=now - 10)
        with mock.patch.object(lp, "_sid_file", [0.0, {}]), mock.patch.object(lp, "time", types.SimpleNamespace(time=lambda: NOW)):
            self.assertEqual(lp._sid_transcript(SID), newer)

    def test_recent_transcripts_walk_every_root(self):
        cards = _load.sidereus("cards")
        now = NOW
        a = _w(os.path.join(self.pp, SLUG, "a.jsonl"), mt=now - 60)
        b = _w(os.path.join(self.wp, SLUG, "b.jsonl"), mt=now - 30)
        old = _w(os.path.join(self.wp, "-w-q", "c.jsonl"), mt=now - 99 * 3600)
        with mock.patch.object(cards, "agent_view", lambda: {}):
            got = [fp for _mt, fp in cards._recent_transcripts(now, 12)]
            self.assertEqual(got, [b, a])
            got = [fp for _mt, fp in cards._recent_transcripts(now, 12, live={"/w/q": 1})]   # quiet live path revived from the extra root
            self.assertIn(old, got)

    def test_team_root_follows_transcript_root(self):
        ag = _load.sidereus("agents")
        sd = os.path.join(self.wp, SLUG, SID)
        _w(os.path.join(self.work, "tasks", SID, "1.json"),
           json.dumps({"id": "1", "subject": "s", "status": "pending", "owner": "x"}), mt=NOW - 10)
        t = ag.team_info(sd, now=NOW)
        self.assertIsNotNone(t)
        self.assertEqual(t["total"], 1)


class RowTest(RootsBase):
    def test_row_acct_only_for_extra_root(self):
        S = _load.sidereus("sessions")
        self.assertEqual(S._row_acct(SID, os.path.join(self.wp, SLUG, SID + ".jsonl")),
                         {"acct": "work", "acctDir": self.work})
        self.assertEqual(S._row_acct(SID, os.path.join(self.pp, SLUG, SID + ".jsonl")), {})

    def _rec(self, sid, d):
        ad = tempfile.mkdtemp(prefix="sidereus-acct-")
        self.addCleanup(shutil.rmtree, ad, True)
        p = mock.patch.object(self.cr, "ACCT_DIR", ad)
        p.start()
        self.addCleanup(p.stop)
        if d is not None:
            _w(os.path.join(ad, sid), d + "\n")

    def test_acct_record_beats_transcript_path(self):
        S, R = _load.sidereus("sessions"), _load.sidereus("recent")
        alt = os.path.join(self.home, ".claude-alt")
        os.makedirs(alt)
        os.symlink(self.pp, os.path.join(alt, "projects"))   # shared history with the primary
        _w(os.path.join(alt, ".claude.json"))
        self._reg("account job ~/.claude-alt\n")
        self.cr.reset()
        self._rec(SID, alt)
        fp = os.path.join(self.pp, SLUG, SID + ".jsonl")
        self.assertEqual(S._row_acct(SID, fp), {"acct": "job", "acctDir": alt})
        self.assertEqual(R._acct(SID, fp), {"acct": "job", "acctDir": alt})

    def test_acct_record_primary_absent(self):
        S = _load.sidereus("sessions")
        self._rec(SID, self.prim)
        self.assertEqual(S._row_acct(SID, os.path.join(self.wp, SLUG, SID + ".jsonl")), {})

    def test_acct_no_record_or_bad_sid_falls_back(self):
        S = _load.sidereus("sessions")
        self._rec(SID, None)
        fp = os.path.join(self.wp, SLUG, SID + ".jsonl")
        self.assertEqual(S._row_acct(SID, fp), {"acct": "work", "acctDir": self.work})
        self.assertEqual(S._row_acct("../etc", fp), {"acct": "work", "acctDir": self.work})

    def test_acct_record_fifo_ignored(self):
        S = _load.sidereus("sessions")
        self._rec(SID, None)
        os.mkfifo(os.path.join(self.cr.ACCT_DIR, SID))   # open() on it would block the poll
        fp = os.path.join(self.wp, SLUG, SID + ".jsonl")
        self.assertEqual(S._row_acct(SID, fp), {"acct": "work", "acctDir": self.work})

    def _reg(self, text):
        with open(os.path.join(self.home, ".claude-accounts"), "w") as f:
            f.write(text)

    def test_single_root_no_acct(self):
        S = _load.sidereus("sessions")
        shutil.rmtree(self.work)
        self.cr.reset()
        self.assertEqual(S._row_acct(SID, os.path.join(self.pp, SLUG, SID + ".jsonl")), {})
        self.assertEqual(self.cr.projects_dirs(self.pp), [self.pp])

    def test_state_v1_acct(self):
        v1 = _load.sidereus("state_v1")
        self.assertNotIn("acct", v1._session({"sid": SID, "model": "m"}))
        s = v1._session({"sid": SID, "acct": "work", "acctDir": self.work})
        self.assertEqual(s["acct"], "work")
        self.assertNotIn("acctDir", s)
        sch = v1.load_schema()
        self.assertIn("acct", sch["$defs"]["session"]["properties"])


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ResumeAcctTest(unittest.TestCase):
    def test_config_dir_prefix_quoted(self):
        sid = "0a1b2c3d-4e5f-6789-abcd-ef0123456789"
        js = "\n".join([_load.js_fn("shq"), _load.js_fn("resumeCmd"),
                        "console.log(JSON.stringify([resumeCmd('/w', '%s', \"/h/.claude-it's\"), resumeCmd('/w', '%s')]));"
                        % (sid, sid)])
        r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out[0], "cd '/w' && CLAUDE_CONFIG_DIR='/h/.claude-it'\\''s' claude --resume " + sid)
        self.assertEqual(out[1], "cd '/w' && claude --resume " + sid)


if __name__ == "__main__":
    unittest.main()
