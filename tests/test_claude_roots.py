"""sidereus/claude_roots.py: extra Claude config roots (temp dirs only)."""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests import _load


class ClaudeRootsTest(unittest.TestCase):
    def setUp(self):
        self.cr = _load.sidereus("claude_roots")
        self.prefs = _load.sidereus("prefs")
        self.home = tempfile.mkdtemp(prefix="sidereus-roots-")
        self.prim = os.path.join(self.home, ".claude")
        os.makedirs(os.path.join(self.prim, "projects"))
        p = [mock.patch.object(self.cr, "SCAN_HOME", self.home),
             mock.patch.object(self.cr, "claude_home", lambda: self.prim),
             mock.patch.object(self.cr, "effective", lambda k: [])]
        for x in p:
            x.start()
            self.addCleanup(x.stop)
        self.cr.reset()
        self.addCleanup(self.cr.reset)

    def _mk(self, name):
        d = os.path.join(self.home, name)
        os.makedirs(os.path.join(d, "projects"))
        return d

    def test_single_root(self):
        r = self.cr.roots()
        self.assertEqual(len(r), 1)
        self.assertTrue(r[0]["primary"])
        pp = os.path.join(self.prim, "projects")
        self.assertEqual(self.cr.projects_dirs(pp), [pp])
        self.assertEqual(self.cr.root_of(os.path.join(pp, "x", "a.jsonl")), ("", ""))

    def test_extra_dirs_and_labels(self):
        work = self._mk(".claude-work")
        os.makedirs(os.path.join(self.home, ".claude-empty"))   # no projects/ -> skipped
        r = self.cr.roots()
        self.assertEqual([x["label"] for x in r[1:]], ["work"])
        self.assertFalse(r[1]["primary"])
        pp = os.path.join(self.prim, "projects")
        self.assertEqual(self.cr.projects_dirs(pp), [pp, os.path.join(work, "projects")])
        self.assertEqual(self.cr.root_of(os.path.join(work, "projects", "p", "s.jsonl")), ("work", work))
        self.assertEqual(self.cr.root_of(os.path.join(pp, "p", "s.jsonl")), ("", ""))
        self.assertEqual(self.cr.root_of("/nowhere/x"), ("", ""))

    def test_config_dir_adds_home_claude_and_dedupes(self):
        alt = self._mk(".claude-alt")
        with mock.patch.object(self.cr, "claude_home", lambda: alt), \
                mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": alt}):
            self.cr.reset()
            r = self.cr.roots()
        self.assertEqual(r[0]["dir"], alt)
        self.assertEqual([(x["dir"], x["label"]) for x in r[1:]], [(self.prim, "claude")])

    def test_prefs_entry_label_and_dedupe(self):
        ext = tempfile.mkdtemp(prefix="sidereus-roots-ext-")
        os.makedirs(os.path.join(ext, "projects"))
        work = self._mk(".claude-work")
        ents = [{"dir": ext, "label": "work"}, {"dir": work, "label": "dup"}]
        with mock.patch.object(self.cr, "effective", lambda k: ents):
            self.cr.reset()
            r = self.cr.roots()
        # prefs label wins for .claude-work even though the home scan reached it first
        self.assertEqual([x["label"] for x in r], ["claude", "dup", "work"])
        self.assertEqual(r[2]["dir"], ext)

    def _reg(self, text):
        with open(os.path.join(self.home, ".claude-accounts"), "w", encoding="utf-8") as f:
            f.write(text)

    def test_registry_label(self):
        work = self._mk(".claude-work")
        self._mk(".claude-other")
        self._reg("# c\naccount job ~/.claude-work\naccount bad!name %s/.claude-other\naccount gone ~/x\n" % self.home)
        r = self.cr.roots()
        self.assertEqual([(x["dir"], x["label"]) for x in r[1:]],
                         [(os.path.join(self.home, ".claude-other"), "bad-name"), (work, "job")])
        self.assertEqual(self.cr.root_of(os.path.join(work, "projects", "s.jsonl")), ("job", work))
        with mock.patch.object(self.cr, "effective", lambda k: [{"dir": work, "label": "pref"}]):
            self.cr.reset()
            self.assertEqual(self.cr.roots()[2]["label"], "pref")

    def test_registry_unreadable_or_single_root(self):
        self._reg("account job ~/.claude\n")       # primary only: output unchanged
        self.assertEqual(self.cr.roots(), [{"dir": self.prim, "label": "claude", "primary": True}])
        self._mk(".claude-work")
        with open(os.path.join(self.home, ".claude-accounts"), "wb") as f:
            f.write(b"account \xff ~/.claude-work\n")
        self.cr.reset()
        self.assertEqual(self.cr.roots()[1]["label"], "work")

    def test_registry_dirs_added_as_roots(self):
        ext = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-roots-reg-"))
        self.addCleanup(shutil.rmtree, ext, True)
        os.makedirs(os.path.join(ext, "a", "projects"))
        os.makedirs(os.path.join(ext, "b"))
        os.makedirs(os.path.join(ext, "nosign", "projects"))   # registry-only: projects/ without .claude.json
        for x in ("a", "b"):
            with open(os.path.join(ext, x, ".claude.json"), "w", encoding="utf-8") as f:
                f.write("{}")
        os.makedirs(os.path.join(ext, "empty"))
        with open(os.path.join(self.home, ".claude.json"), "w", encoding="utf-8") as f:   # signed home: still refused as too wide
            f.write("{}")
        work = self._mk(".claude-work")
        self._reg("account a %s/a\naccount b %s/b\naccount e %s/empty\naccount n %s/nosign\n"
                  "account job ~/.claude-work\naccount p ~/.claude\naccount root /\naccount h ~\naccount up %s\n"
                  % (ext, ext, ext, ext, os.path.dirname(self.home)))
        r = self.cr.roots()
        self.assertEqual([(x["dir"], x["label"]) for x in r[1:]],
                         [(work, "job"), (os.path.join(ext, "a"), "a"), (os.path.join(ext, "b"), "b")])
        pp = os.path.join(self.prim, "projects")
        self.assertEqual(self.cr.projects_dirs(pp),
                         [pp, os.path.join(work, "projects"), os.path.join(ext, "a", "projects")])

    def test_registry_mtime_memo(self):
        self._mk(".claude-work")
        self._reg("account a ~/.claude-work\n")
        self.assertEqual(self.cr.roots()[1]["label"], "a")
        self._reg("account b ~/.claude-work\n")
        os.utime(os.path.join(self.home, ".claude-accounts"), (1, 1))
        self.cr.reset()
        self.assertEqual(self.cr.roots()[1]["label"], "b")

    def test_shared_history_profile_in_accounts_only(self):
        alt = os.path.join(self.home, ".claude-alt")
        os.makedirs(alt)
        os.symlink(os.path.join(self.prim, "projects"), os.path.join(alt, "projects"))
        with open(os.path.join(alt, ".claude.json"), "w", encoding="utf-8") as f:
            f.write("{}")
        self._reg("account me ~/.claude\naccount job ~/.claude-alt\n")
        pp = os.path.join(self.prim, "projects")
        self.assertEqual(len(self.cr.roots()), 1)
        self.assertEqual(self.cr.projects_dirs(pp), [pp])
        self.assertEqual([(a["dir"], a["label"], a["primary"]) for a in self.cr.accounts()],
                         [(self.prim, "me", True), (alt, "job", False)])

    def test_single_root_accounts_equal_roots(self):
        self.assertEqual(self.cr.accounts(), self.cr.roots())
        st = _load.sidereus("state")
        self.assertIsNone(st._accts())

    def test_memo_ttl(self):
        self.assertEqual(len(self.cr.roots()), 1)
        self._mk(".claude-late")
        self.assertEqual(len(self.cr.roots()), 1)   # memoized
        with mock.patch.object(self.cr, "ROOTS_TTL_S", 0):
            self.assertEqual(len(self.cr.roots()), 2)

    def test_wide_roots_dropped(self):
        # projects symlinked to "/", the home dir and the home's parent: every one widens the path guard
        for name, tgt in ((".claude-root", "/"), (".claude-home", self.home),
                          (".claude-up", os.path.dirname(self.home))):
            d = os.path.join(self.home, name)
            os.makedirs(d)
            os.symlink(tgt, os.path.join(d, "projects"))
        ents = [{"dir": "/"}, {"dir": os.path.dirname(self.home)}]
        with mock.patch.object(self.cr, "effective", lambda k: ents):
            self.cr.reset()
            self.assertEqual(len(self.cr.roots()), 1)

    def test_work_guard_refuses_slash(self):
        w = _load.sidereus("work")
        with mock.patch.object(w.claude_roots, "projects_dirs", lambda prim: ["/"]):
            self.assertEqual(w._under_projects("/etc/hosts"), "")

    def test_prefs_validator_refuses_wide_dirs(self):
        v = self.prefs.PREFS["claude_roots"][1]
        with mock.patch.object(self.prefs, "HOME_DIR", self.home):
            for bad in ("/", self.home, os.path.dirname(self.home)):
                with self.assertRaises(ValueError):
                    v([{"dir": bad}])
            self.assertEqual(v([{"dir": self.prim}]), [{"dir": self.prim}])

    def test_prefs_validator(self):
        v = self.prefs.PREFS["claude_roots"][1]
        self.assertEqual(v([{"dir": "~/x", "label": "a.b-c"}]), [{"dir": "~/x", "label": "a.b-c"}])
        for bad in ({}, [{"dir": "rel"}], [{"dir": "/a", "label": "bad label"}], [{"dir": "/a", "x": 1}],
                    [{"dir": "/a/../b"}], [{"dir": "/a"}] * 17):
            with self.assertRaises(ValueError):
                v(bad)
        self.assertIn("claude_roots", self.prefs.PREFS_OWN_PANE)


if __name__ == "__main__":
    unittest.main()
