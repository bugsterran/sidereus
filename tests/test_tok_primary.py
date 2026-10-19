"""Primary-only token sums when another account shares the primary's projects dir. Temp dirs only."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests import _load

T0 = 1.7e9


class PrimaryOwned(unittest.TestCase):
    def setUp(self):
        self.cr = _load.sidereus("claude_roots")
        self.home = tempfile.mkdtemp(prefix="sidereus-tokprim-")
        self.addCleanup(shutil.rmtree, self.home, True)
        self.prim = os.path.join(self.home, ".claude")
        self.pp = os.path.join(self.prim, "projects")
        os.makedirs(os.path.join(self.pp, "p"))
        self.acct = os.path.join(self.home, "acct")
        os.makedirs(self.acct)
        for x in (mock.patch.object(self.cr, "SCAN_HOME", self.home),
                  mock.patch.object(self.cr, "claude_home", lambda: self.prim),
                  mock.patch.object(self.cr, "effective", lambda k: []),
                  mock.patch.object(self.cr, "ACCT_DIR", self.acct)):
            x.start()
            self.addCleanup(x.stop)
        self.cr.reset()
        self.addCleanup(self.cr.reset)
        self.fp = os.path.join(self.pp, "p", "sess-aaaa1111.jsonl")

    def share(self):
        alt = os.path.join(self.home, ".claude-myaccount")
        os.makedirs(alt)
        os.symlink(self.pp, os.path.join(alt, "projects"))
        with open(os.path.join(alt, ".claude.json"), "w", encoding="utf-8") as f:
            f.write("{}")
        self.cr.reset()
        return alt

    def rec(self, sid, d):
        with open(os.path.join(self.acct, sid), "w", encoding="utf-8") as f:
            f.write(d + "\n")

    def test_single_account_unknown_is_primary(self):
        self.assertTrue(self.cr.primary_owned("sess-aaaa1111", self.fp))

    def test_shared_dir_by_record(self):
        alt = self.share()
        self.rec("sess-aaaa1111", self.prim)
        self.rec("sess-bbbb2222", alt)
        self.assertTrue(self.cr.primary_owned("sess-aaaa1111", self.fp))
        self.assertFalse(self.cr.primary_owned("sess-bbbb2222", self.fp))
        self.assertFalse(self.cr.primary_owned("sess-cccc3333", self.fp))   # unknown in a shared dir: excluded


class TokSums(unittest.TestCase):
    """`_tok_events` (cur.used_local / wk used sum it) and `_tok_scan` keep only the primary's sessions."""
    def setUp(self):
        self.tl = _load.sidereus("timeline")
        self.h = _load.sidereus("burn_hist")
        self.d = tempfile.mkdtemp(prefix="sidereus-tokprim-")
        self.addCleanup(shutil.rmtree, self.d, True)
        os.makedirs(os.path.join(self.d, "p"))
        self.files = {}
        for sid, n in (("sess-prim0001", 100), ("sess-myac0002", 7000)):
            fp = os.path.join(self.d, "p", sid + ".jsonl")
            with open(fp, "w", encoding="utf-8") as f:
                f.write(json.dumps({"timestamp": "2023-11-14T22:13:30.000Z", "requestId": sid,
                                    "message": {"id": sid, "usage": {"input_tokens": n}}}) + "\n")
            os.utime(fp, (T0 + 100, T0 + 100))
            self.files[fp] = n
        self.tl._TOKEV.clear()
        self.addCleanup(self.tl._TOKEV.clear)
        self.h._tok_files.clear()
        self.addCleanup(self.h._tok_files.clear)

    def patch(self, obj, **kw):
        for k, v in kw.items():
            p = mock.patch.object(obj, k, v)
            p.start()
            self.addCleanup(p.stop)

    def owned(self, shared):
        return lambda sid, fp: (sid == "sess-prim0001") if shared else True

    def events(self, shared):
        self.tl._TOKEV.clear()
        fs = sorted(self.files)
        self.patch(self.tl, _tl_snap_rows=lambda: ([], True), _tl_pick=lambda cut, rows: [("/w", "w", fs, fs[0])],
                   _agent_meta=lambda sd, ttl=10: {}, wf_agent_files=lambda sd: [],
                   _sess_segments=lambda fp, cut, tok_out, **k: tok_out.append((T0 + 1, self.files[fp])))
        self.patch(self.tl.claude_roots, primary_owned=self.owned(shared))
        return sum(n for _t, n in self.tl._tok_events(T0))

    def scan(self, shared):
        self.h._tok_files.clear()
        self.patch(self.h, CLAUDE_PROJECTS=self.d, primary_owned=self.owned(shared))
        return sum(n for _t, n in self.h._tok_scan(T0 - 10))

    def test_shared_dir_sums_primary_only(self):
        self.assertEqual(self.events(True), 100)
        self.assertEqual(self.scan(True), 100)

    def test_single_account_unchanged(self):
        self.assertEqual(self.events(False), 7100)
        self.assertEqual(self.scan(False), 7100)


if __name__ == "__main__":
    unittest.main()
