"""Codex rows get a mailbox id by the Codex hook's rule (ident.mbox_codex), never the Claude id of the same folder."""
import os
import shutil
import tempfile
import unittest

from tests._load import sidereus

ident = sidereus("ident")
ext = sidereus("ext")


class MboxCodex(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cwd = os.path.join(os.path.realpath(self.tmp), "proj")
        os.makedirs(self.cwd)
        self.idj = {}
        self._load, self._env = ident._load, ident._mbox_env_default
        ident._load = lambda name, default: self.idj if name == "identity.json" else default
        ident._mbox_env_default = lambda: ""        # no live ~/.claude.json
        self._ext = dict(ext._ext)
        ext._ext.clear()
        self._saved = {n: getattr(ext, n) for n in
                       ("_ext_prune_locked", "ext_gone_check", "ext_tok_refresh", "ext_tok", "plm_of")}
        ext._ext_prune_locked = lambda now: None
        ext.ext_gone_check = lambda now=None: None
        ext.ext_tok_refresh = lambda *a, **k: None
        ext.ext_tok = lambda *a, **k: {}
        ext.plm_of = lambda *a, **k: None

    def tearDown(self):
        ident._load, ident._mbox_env_default = self._load, self._env
        ext._ext.clear()
        ext._ext.update(self._ext)
        for n, v in self._saved.items():
            setattr(ext, n, v)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_identity_key(self):
        self.idj["codex:" + self.cwd] = "cx-me"
        self.assertEqual(ident.mbox_codex(self.cwd), ("cx-me", "identity"))

    def test_folder_fallback(self):
        self.assertEqual(ident.mbox_codex(self.cwd), ("proj-codex", "folder"))

    def test_collision_with_claude_id(self):
        self.idj["/elsewhere"] = "proj-codex"
        self.assertEqual(ident.mbox_codex(self.cwd), ("", "none"))

    def test_empty_cwd(self):
        self.assertEqual(ident.mbox_codex(""), ("", "none"))

    def _rows(self):
        now = 1800000000.0
        for plat, sid in (("codex", "c1"), ("gemini", "g1")):
            ext._ext[(plat, sid)] = {"cwd": self.cwd, "state": "idle", "lastSeen": now, "firstSeen": now}
        return {r["sid"]: r for r in ext.ext_rows()}

    def test_claude_and_codex_rows_differ(self):
        self.idj[self.cwd] = "claude-me"
        rows = self._rows()
        cx = rows["c1"]
        self.assertEqual(cx["plat"], ext.EXT_PLAT["codex"])
        self.assertEqual((cx["mbox"], cx["mboxSrc"]), ("proj-codex", "folder"))
        self.assertNotEqual(cx["mbox"], ident.mbox_of(self.cwd)[0])

    def test_gemini_row_stays_empty(self):
        g = self._rows()["g1"]
        self.assertEqual(g["plat"], ext.EXT_PLAT["gemini"])
        self.assertEqual((g["mbox"], g["mboxSrc"]), ("", ""))


if __name__ == "__main__":
    unittest.main()
