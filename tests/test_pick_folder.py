"""«폴더 선택…»: POST /api/pick-folder (sidereus/pipeline_projects.pick_folder) + hidden folders in the in-page browser.

⚠The dialog runner `_run` is patched in every test — no real dialog opens.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from tests._load import load, sidereus
from tests.test_routes_post import post, PORT, EVIL
from tests._node import node_e

cs = load()
PP = sidereus("pipeline_projects")
W = sidereus("warn")
ORIGIN = "http://127.0.0.1:%d" % PORT


def _res(rc=0, out="", err=""):
    return SimpleNamespace(returncode=rc, stdout=out, stderr=err)


class Pick(unittest.TestCase):
    def _os(self, mac, win):
        for p in (mock.patch.object(PP, "IS_MAC", mac), mock.patch.object(PP, "IS_WIN", win)):
            p.start()
            self.addCleanup(p.stop)

    def _pick(self, res):
        calls = []

        def run(argv, **kw):
            calls.append((argv, kw))
            if isinstance(res, Exception):
                raise res
            return res
        self.warned = []
        with mock.patch.object(PP, "_run", run), \
                mock.patch.object(PP, "warn_once", lambda k, m, **kw: self.warned.append((k, W._fill(m, kw.get("vars")), kw.get("soft")))):
            return PP.pick_folder(), calls

    def test_mac_success_and_argv(self):
        self._os(True, False)
        (code, out), calls = self._pick(_res(0, "/Users/me/.hidden-proj/\n"))
        self.assertEqual((code, out), (200, {"ok": True, "path": "/Users/me/.hidden-proj"}))
        argv, kw = calls[0]
        self.assertEqual(argv[0], "osascript")
        self.assertTrue(any("with invisibles" in a for a in argv))
        self.assertTrue(any(a == "activate" for a in argv))
        self.assertNotIn("shell", kw)
        self.assertEqual(kw["timeout"], PP.PICK_TIMEOUT)

    def test_mac_cancel(self):
        self._os(True, False)
        (code, out), _ = self._pick(_res(1, "", "execution error: User canceled. (-128)"))
        self.assertEqual(out, {"ok": True, "cancelled": True})
        out = self._pick(_res(1, "", "other failure"))[0][1]
        self.assertEqual(out, {"ok": False, "err": PP.PICK_ERR_OPEN})              # raw stderr never reaches the page
        self.assertEqual(self.warned, [("pick-folder", "Folder dialog failed: other failure", True)])
        self.assertEqual(self._pick(OSError("boom"))[0][1], {"ok": False, "err": PP.PICK_ERR_OPEN})

    def test_win_success_and_cancel(self):
        self._os(False, True)
        (code, out), calls = self._pick(_res(0, "C:\\Users\\me\\proj\\"))
        self.assertEqual(out, {"ok": True, "path": "C:\\Users\\me\\proj"})
        argv, kw = calls[0]
        self.assertEqual(argv[:4], ["powershell", "-NoProfile", "-STA", "-Command"])
        self.assertIn("FolderBrowserDialog", argv[4])
        self.assertEqual(kw["creationflags"], 0x08000000)
        self.assertEqual(self._pick(_res(0, "C:\\"))[0][1]["path"], "C:\\")   # root keeps its separator
        self.assertEqual(self._pick(_res(0, ""))[0][1], {"ok": True, "cancelled": True})

    def test_bad_output_and_timeout(self):
        self._os(True, False)
        self.assertEqual(self._pick(_res(0, "rel/dir"))[0][1], {"ok": False, "err": PP.PICK_ERR_PATH})
        self.assertEqual(self._pick(subprocess.TimeoutExpired("osascript", 1))[0][1],
                         {"ok": False, "err": PP.PICK_ERR_TIMEOUT})
        i18n = open(os.path.join(os.path.dirname(__file__), "..", "web", "js", "06-i18n-v.js"), encoding="utf-8").read()
        for k in (PP.PICK_ERR_TIMEOUT, PP.PICK_ERR_PATH, PP.PICK_ERR_OPEN):
            self.assertIn("'%s':" % k, i18n)   # I18N.ko key (English source)

    def test_unsupported(self):
        self._os(False, False)
        (code, out), calls = self._pick(_res(0, "/x"))
        self.assertEqual((out, calls), ({"ok": False, "unsupported": True}, []))
        self.assertFalse(PP.pick_supported())

    def test_busy_lock(self):
        self._os(True, False)
        self.assertTrue(PP._PICK_LOCK.acquire(False))
        try:
            (code, out), calls = self._pick(_res(0, "/x"))
        finally:
            PP._PICK_LOCK.release()
        self.assertEqual((out, calls), ({"ok": False, "busy": True}, []))
        self.assertEqual(self._pick(_res(0, "/x"))[0][1]["path"], "/x")   # released after use

    def test_route_origin(self):
        RP = sidereus("routes_post")
        with mock.patch.object(RP, "pick_folder", side_effect=AssertionError("must not run")):
            for o in (None, EVIL):
                self.assertEqual(post("/api/pick-folder", {}, origin=o)[0], 403, o)
        with mock.patch.object(RP, "pick_folder", return_value=(200, {"ok": True, "cancelled": True})):
            code, out = post("/api/pick-folder", {}, origin=ORIGIN)[:2]
        self.assertEqual((code, out), (200, {"ok": True, "cancelled": True}))


class Hidden(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        for d in (".dot", "vis"):
            os.makedirs(os.path.join(self.tmp, d))
        p = mock.patch.object(PP, "USER_HOME", self.tmp)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_hidden_toggle(self):
        self.assertEqual([d["name"] for d in PP.browse_dirs("")[1]["dirs"]], ["vis"])
        self.assertEqual([d["name"] for d in PP.browse_dirs("", True)[1]["dirs"]], [".dot", "vis"])
        with mock.patch.object(PP, "IS_MAC", True):
            self.assertTrue(PP.browse_dirs("")[1]["pick"])


class PickJs(unittest.TestCase):
    def test_button_and_toggle_render(self):
        import json
        from tests._i18n_js import i18n_prelude
        from tests.test_pipeline_browse import _F, _STUB
        B = {"path": "/h", "home": "/h", "parent": "", "dirs": [], "busy": False}
        with open(_F, encoding="utf-8") as f:
            src = _STUB + i18n_prelude("'ko'", ("T", "TV", "U")) + f.read() + "\nconsole.log(JSON.stringify([%s].map(plBrHtml)))" % ",".join(
                json.dumps(dict(B, **x)) for x in ({}, {"pick": True}, {"pick": True, "picking": True, "hidden": True}))
        off, on, busy = json.loads(subprocess.run(node_e(src), capture_output=True, text=True, check=True, encoding="utf-8").stdout)
        self.assertNotIn("data-plbrpick", off)                       # unsupported OS: no button
        self.assertIn("data-plbrpick>", on)
        self.assertIn("data-plbrpick disabled", busy)
        self.assertIn("data-plbrhid checked", busy)
        self.assertNotIn("checked", on)                               # hidden folders default off


if __name__ == "__main__":
    unittest.main()
