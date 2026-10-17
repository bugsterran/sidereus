"""«+ 프로젝트 불러오기» folder browser: GET /api/pipelines/projects/dirs (sidereus/pipeline_projects.browse_dirs) + 48f modal escaping.

⚠Home is a tmp dir (`USER_HOME` patched) — never the live ~.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from tests._i18n_js import i18n_prelude
from tests._load import load, sidereus, ROOT
from tests.test_prefs import get
from tests._node import node_e

cs = load()
PP = sidereus("pipeline_projects")


class Browse(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.home = os.path.join(self.tmp, "home")
        for d in ("b-proj/.git", "A-cl/.claude", "c-md", ".hidden", "zz"):
            os.makedirs(os.path.join(self.home, d))
        open(os.path.join(self.home, "c-md", "AGENTS.md"), "w", encoding="utf-8").close()
        open(os.path.join(self.home, "file.txt"), "w", encoding="utf-8").close()
        os.makedirs(os.path.join(self.tmp, "outside"))
        p = mock.patch.object(PP, "USER_HOME", self.home)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_top_lists_dirs_only_sorted_with_flags(self):
        code, out = PP.browse_dirs("")
        self.assertEqual((code, out["ok"], out["path"], out["parent"], out["more"]), (200, True, self.home, "", False))
        self.assertEqual([(d["name"], d["git"], d["claude"]) for d in out["dirs"]],
                         [("A-cl", False, True), ("b-proj", True, False), ("c-md", False, True), ("zz", False, False)])

    def test_subdir_parent_and_tilde(self):
        code, out = PP.browse_dirs(os.path.join(self.home, "b-proj"))
        self.assertEqual((code, out["parent"], out["dirs"]), (200, self.home, []))   # .git is hidden
        with mock.patch.dict(os.environ, {"HOME": self.home, "USERPROFILE": self.home}):   # Windows expanduser reads USERPROFILE
            self.assertEqual(PP.browse_dirs("~/zz")[1]["path"], os.path.join(self.home, "zz"))

    def test_boundary(self):
        for raw in (os.path.join(self.tmp, "outside"), "/", "/etc", self.home + "/../outside", "rel/dir", "x\0y"):
            self.assertEqual(PP.browse_dirs(raw)[0], 400, raw)
        os.symlink(os.path.join(self.tmp, "outside"), os.path.join(self.home, "link"))
        self.assertEqual(PP.browse_dirs(os.path.join(self.home, "link"))[0], 400)   # realpath leaves home
        self.assertEqual(PP.browse_dirs(os.path.join(self.home, "nope"))[0], 400)

    def test_unreadable(self):
        with mock.patch.object(PP.os, "listdir", side_effect=PermissionError):
            code, out = PP.browse_dirs("")
        self.assertEqual((code, out["ok"]), (200, False))

    def test_cap(self):
        with mock.patch.object(PP, "DIRS_MAX", 2):
            out = PP.browse_dirs("")[1]
        self.assertEqual(([d["name"] for d in out["dirs"]], out["more"]), (["A-cl", "b-proj"], True))

    def test_route(self):
        code, out = get("/api/pipelines/projects/dirs?path=" + os.path.join(self.home, "zz"))[:2]
        self.assertEqual((code, out["ok"]), (200, True))
        self.assertEqual(get("/api/pipelines/projects/dirs?path=/etc")[0], 400)


_F = os.path.join(ROOT, "web", "js", "48f-pipeline-browse.js")
_STUB = """
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'})[c]);
function lsGet(k, d){ return d; } function lsSet(){}
const document = {addEventListener(){}};
"""


class BrowseJs(unittest.TestCase):
    def test_render_escapes(self):
        B = {"path": "/h/<x>", "home": "/h", "parent": "/h", "more": True, "msg": "<m>", "busy": False,
             "dirs": [{"name": "<img onerror=1>", "git": True, "claude": True}, {"name": "a\"b", "git": False, "claude": False}]}
        with open(_F, encoding="utf-8") as f:
            src = _STUB + i18n_prelude("'ko'", ("T", "TV", "U")) + f.read() + "\nconsole.log(JSON.stringify(plBrHtml(%s)))" % json.dumps(B)
        out = json.loads(subprocess.run(node_e(src), capture_output=True, text=True, check=True, encoding="utf-8").stdout)
        for bad in ("<img", "<x>", "<m>", 'a"b'):
            self.assertNotIn(bad, out)
        self.assertIn("&lt;img onerror=1&gt;", out)
        self.assertIn('data-plbrgo="/h/&lt;x&gt;/a&quot;b"', out)
        self.assertEqual(out.count("plbrb git"), 1)
        self.assertIn("Claude 설정", out)

    def test_windows_crumbs(self):
        B = {"path": "C:\\Users\\me\\w\\p", "home": "C:\\Users\\me", "parent": "C:\\Users\\me\\w", "busy": False,
             "dirs": [{"name": "d", "git": False, "claude": False}]}
        with open(_F, encoding="utf-8") as f:
            src = _STUB + i18n_prelude("'ko'", ("T", "TV", "U")) + f.read() + "\nconsole.log(JSON.stringify([plBrCrumbs(%s), plBrList(%s)]))" % (json.dumps(B), json.dumps(B))
        c, l = json.loads(subprocess.run(node_e(src), capture_output=True, text=True, check=True, encoding="utf-8").stdout)
        self.assertIn('data-plbrgo="C:\\Users\\me\\w">w<', c)
        self.assertIn('data-plbrgo="C:\\Users\\me\\w\\p">p<', c)
        self.assertIn('data-plbrgo="C:\\Users\\me\\w\\p\\d"', l)

    def test_modal_focus(self):
        with open(_F, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("if(e.key === 'Tab') return plBrTrap(e);", src)
        self.assertIn("document.querySelector('.plw [data-ppk=\"pl\"]')", src)   # focus goes back to the project picker button on close

    def test_stage_add_does_not_open_browser(self):
        """48d «+ 단계»/«+ 직접 만들기» carry data-pladd; only data-plprojadd may open the folder modal."""
        with open(os.path.join(ROOT, "web", "js", "48-pipeline.js"), encoding="utf-8") as f:
            src = f.read()
        stub = """
const L = []; let opened = 0;
const document = {addEventListener(t, f){ if(t === 'click') L.push(f); }};
function lsGet(k, d){ return d; } function lsSet(){} function plBrOpen(){ opened++; } function plPaint(){}
const ev = attr => ({ preventDefault(){}, target: { closest: s => (s === '.plw' || s === attr) ? { dataset: {} } : null } });
"""
        body = "\nL.forEach(f => f(ev('[data-pladd]'))); const a = opened; L.forEach(f => f(ev('[data-plprojadd]'))); console.log(JSON.stringify([a, opened]));"
        out = subprocess.run(node_e(stub + src + body), capture_output=True, text=True, check=True, encoding="utf-8").stdout
        self.assertEqual(json.loads(out), [0, 1])
        self.assertIn("data-plprojadd>", src)


if __name__ == "__main__":
    unittest.main()
