"""Size-view / code-popup cases kept from the removed Relations test files: Kotlin method scan, HTML script
extraction (Svelte scan) and MyBatis mapper .xml in the code popup. Synthetic sources and a temp dir only."""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import sidereus

L = sidereus("structure_lang")
S = sidereus("structure")

KT = ("package demo.ui\n\nenum class FeedbackState { IDLE, SENT; fun label(): String { return name } }\n"
      "annotation class Marker\ndata class Point(val x: Int, val y: Int) { fun len(): Int { return x } }\n"
      "sealed class Shape { class Circle(val r: Int) : Shape() }\n@JvmInline value class Meters(val v: Double)\n"
      "class Outer { inner class Inner { fun go() { } } }\nsealed interface Ev\nfun interface Cb { fun on() }\n")
TAG = "script"
PAGE = ('<html><body><div>fetch("/not/code")</div>\n'
        '<' + TAG + ' src="/vendor.js"></' + TAG + '>\n'
        '<' + TAG + ' type="application/json">{"u": fetch("/json")}</' + TAG + '>\n'
        '<' + TAG + '>\nasync function load(){ return fetch("/agent/models").then(r => r.json()); }\n'
        'async function send(){ return fetch("/agent/admin/report", {method: "POST"}); }\n</' + TAG + '>\n'
        '</body></html>\n')


class ScanCases(unittest.TestCase):
    def test_kotlin_method_scan_names(self):
        self.assertEqual([o["name"] for o in L._java_scan(KT, "kotlin")], ["FeedbackState.label", "Point.len", "Inner.go"])

    def test_html_scripts_keeps_offsets(self):
        js = L.html_scripts(PAGE)
        self.assertEqual(len(js), len(PAGE))
        self.assertEqual(js.count("\n"), PAGE.count("\n"))
        self.assertNotIn("/not/code", js)
        self.assertNotIn("/json", js)
        self.assertIn('fetch("/agent/models")', js)

    def test_svelte_scan(self):
        src = '<script lang="ts">\nfunction go(a: number) {\n  return a;\n}\n</script>\n<h1>{go(1)}</h1>\n'
        n, fns, skip = L._struct_one_file("src/A.svelte", src)
        self.assertEqual((n, skip), (7, 0))
        self.assertEqual([(f["name"], f["line"], f["lines"]) for f in fns], [("go", 2, 3)])


class MapperXmlSrc(unittest.TestCase):
    """Code popup opens `.xml` only for MyBatis mappers."""
    def setUp(self):
        self.d = os.path.realpath(tempfile.mkdtemp())     # ⚠_struct_src_at confines against the real root (/var -> /private/var)
        os.makedirs(os.path.join(self.d, "res"))
        self._w("res/M.xml", '<?xml version="1.0"?>\n<!DOCTYPE mapper>\n<mapper namespace="a.b.M">\n</mapper>\n')
        self._w("res/app.xml", '<beans><bean><property name="password" value="s3cret"/></bean></beans>\n')
        self._r = S._struct_src_root
        S._struct_src_root = lambda p: self.d if p == "/r" else None

    def tearDown(self):
        S._struct_src_root = self._r
        shutil.rmtree(self.d, ignore_errors=True)

    def _w(self, rel, txt):
        with open(os.path.join(self.d, rel), "w", encoding="utf-8") as f:
            f.write(txt)

    def test_mapper_only(self):
        ok = S.structure_src("/r", "res/M.xml", 1, 80)
        self.assertTrue(ok["ok"])
        self.assertIn("namespace", ok["code"])
        bad = S.structure_src("/r", "res/app.xml", 1, 80)
        self.assertEqual((bad["ok"], bad["msg"]), (False, "This path cannot be read."))
        self.assertNotIn("s3cret", json.dumps(bad))
        for f in ("../res/M.xml", "res/../../x/M.xml", self.d + "/res/M.xml", "res/none.xml"):
            self.assertFalse(S.structure_src("/r", f, 1, 80)["ok"], f)
        self.assertEqual(S._struct_src_rel("res/M.xml"), "")              # no root -> no xml
        self.assertEqual((S._struct_src_rel("web/A.vue"), S._struct_src_rel("../A.vue"),
                          S._struct_src_rel("web/a.json")), ("web/A.vue", "", ""))


if __name__ == "__main__":
    unittest.main()
