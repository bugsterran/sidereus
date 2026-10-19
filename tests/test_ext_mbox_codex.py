"""Codex rows get a mailbox id by the Codex hook's rule (ident.mbox_codex), never the Claude id of the same folder."""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import sidereus

ident = sidereus("ident")
ext = sidereus("ext")
bus = sidereus("bus")


class MboxCodex(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cwd = os.path.join(os.path.realpath(self.tmp), "proj")
        os.makedirs(self.cwd)
        self.idj = {}
        self._load, self._env = ident._load, ident._mbox_env_default
        ident._load = lambda name, default: self.idj if name == "identity.json" else default
        ident._mbox_env_default = lambda: ""        # no live ~/.claude.json
        self._dd = bus.DATA_DIR
        bus.DATA_DIR = self.tmp                     # read cursors come from a tmp dir, never the live one
        self._ok = bus._codex_ok
        bus.codex_ok_set(())                        # as after a first poll; test_fresh_state covers None
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
        bus.DATA_DIR = self._dd
        bus._codex_ok = self._ok
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

    def _cursor(self, mbox):
        open(os.path.join(self.tmp, "read-%s.cursor" % mbox), "w", encoding="utf-8").close()

    def _cx(self, sid, **kw):
        r = {"sid": sid, "plat": ext.EXT_PLAT["codex"], "state": "idle", "goneWhy": ""}
        r["mbox"], r["mboxSrc"] = ident.mbox_codex(self.cwd)
        r.update(kw)
        return r

    def test_hook_fed_unique_row_without_cursor_is_env(self):
        rows = ext.codex_env_dedupe([self._cx("c1")])
        self.assertEqual(rows[0]["mboxSrc"], "env")
        self.assertIsNone(bus.dm_target_error("proj-codex", "viewer-me"))
        self.assertEqual(ident.mbox_codex(self.cwd), ("proj-codex", "env"))

    def test_rollout_only_needs_cursor(self):
        rows = ext.codex_env_dedupe([self._cx("c1", rollout=True)])
        self.assertEqual(rows[0]["mboxSrc"], "folder")
        self.assertTrue(bus.dm_target_error("proj-codex", "viewer-me"))
        self._cursor("proj-codex")
        rows = ext.codex_env_dedupe([self._cx("c1", rollout=True)])
        self.assertEqual(rows[0]["mboxSrc"], "env")
        self.assertIsNone(bus.dm_target_error("proj-codex", "viewer-me"))

    def test_two_live_rows_same_id_refused(self):
        self._cursor("proj-codex")
        rows = ext.codex_env_dedupe([self._cx("c1"), self._cx("c2", rollout=True)])
        self.assertEqual([r["mboxSrc"] for r in rows], ["folder", "folder"])
        self.assertTrue(bus.dm_target_error("proj-codex", "viewer-me"))
        self.assertEqual(ident.mbox_codex(self.cwd), ("proj-codex", "folder"))

    def test_same_sid_twice_and_gone_rows_do_not_count(self):
        rows = ext.codex_env_dedupe([self._cx("c1"), self._cx("c1"), self._cx("c2", goneWhy="pid")])
        self.assertEqual(rows[0]["mboxSrc"], "env")

    def test_fresh_state_fails_closed(self):
        bus._codex_ok = None                         # module state before any dedupe
        self.assertEqual(ident.mbox_codex(self.cwd), ("proj-codex", "folder"))
        self.assertTrue(bus.dm_target_error("proj-codex", "viewer-me"))
        bus.codex_ok_set({"proj-codex"})
        self.assertIsNone(bus.dm_target_error("proj-codex", "viewer-me"))

    def test_claude_owned_refused(self):
        self.idj["/elsewhere"] = "proj-codex"
        with open(os.path.join(self.tmp, "identity.json"), "w", encoding="utf-8") as f:
            json.dump(self.idj, f)               # bus._load reads DATA_DIR (tmp)
        self.assertEqual(ident.mbox_codex(self.cwd), ("", "none"))
        bus.codex_ok_set({"proj-codex"})             # even if published, the static check refuses it
        self.assertFalse(bus.codex_env_ok("proj-codex"))   # (a DM still reaches the Claude owner via identity.json)

    def test_non_codex_id_refused(self):
        self._cursor("proj-origin")
        bus.codex_ok_set({"proj-origin"})
        self.assertFalse(bus.codex_env_ok("proj-origin", {}))
        self.assertTrue(bus.dm_target_error("proj-origin", "viewer-me"))

    def test_traversal_ids_refused(self):
        bad = ("../x-codex", "a/../b-codex", "..-codex", "a/b-codex", "-codex", "", None)
        bus.codex_ok_set([b for b in bad if b])
        for b in bad:
            self.assertFalse(bus.codex_env_ok(b, {}), b)
        rows = ext.codex_env_dedupe([dict(self._cx("x%d" % i), mbox=b, mboxSrc="folder") for i, b in enumerate(bad[:5])])
        self.assertEqual({r["mboxSrc"] for r in rows}, {"folder"})

    def test_invite_picker_stays_identity_only(self):
        # routes_post room invites still require identity.json, so a cx env row is not pickable
        from tests._load import js_fn
        from tests._node import node_e
        import subprocess
        js = ("const T = s => s, TV = o => o.msg, esc = s => String(s), picked = new Set();\n" + js_fn("sessPickHtml")
              + "\nconsole.log(JSON.stringify(sessPickHtml({state: 'idle', plat: 'cx', mbox: 'p-codex', mboxSrc: 'env'})));")
        out = json.loads(subprocess.run(node_e(js), capture_output=True, text=True, check=True, encoding="utf-8").stdout)
        self.assertNotIn("checkbox", out)

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
