"""Harness «A person» checkpoint (47b tiles/strip + 47e hnPerson): R1 tile count · R2 four tiles · R3 strip filter · R4 person cards."""
import json
import os
import re
import subprocess
import unittest

from tests._load import ROOT
from tests._node import node_e
from tests import test_harness_js as thj   # module import: the Harness class must not be collected twice
from tests._i18n_js import i18n_switch

_FS = [os.path.join(ROOT, "web", "js", f) for f in ("47b-harness.js", "47e-harness-person.js")]
_DOC = ("const LST = {}, QS = [], FOC = [];"
        " const document = {addEventListener(t, f){ (LST[t] = LST[t] || []).push(f); }, querySelector(s){ QS.push(s); return {focus(o){ FOC.push(o); }}; }};\n")


def _js(body):
    src = thj._STUB + i18n_switch() + _DOC
    for p in _FS:
        with open(p, encoding="utf-8") as f:
            src += f.read() + "\n"
    return json.loads(subprocess.run(node_e(src + body), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


_PERSON = {"pipes": ["bugfix"], "runs": 3, "git": True,
           "cards": [{"name": "bug<fix>", "t0": 1790000000, "end": 1790000900, "commits": ["abcdef0123456789", "\"><img onerror=1>"],
                      "tests": ["tests/test_<x>.py"]},
                     {"name": "bugfix", "t0": 1790001000, "end": 1790001900, "commits": [], "tests": []},
                     {"name": "bugfix", "t0": 1790002000, "end": 1790002900, "commits": None, "tests": []}]}


def _data(person=_PERSON, counts=None):
    rep = json.loads(json.dumps(thj.Harness._REPORT))
    rep["counts"] = dict(rep["counts"], **(counts or {"person": 3}))
    if person is not None:
        rep["person"] = person
    return json.dumps({"report": rep, "guards": thj.Harness._GUARDS})


class Person(unittest.TestCase):
    def test_node_check(self):
        subprocess.run(["node", "--check", _FS[1]], check=True)

    def test_r1_r2_four_tiles(self):
        h = _js("console.log(JSON.stringify(hnReport(%s)))" % _data())
        tiles = h.split("class=hnrept>", 1)[1].split("class=hnrepg", 1)[0]
        self.assertEqual(re.findall(r'hnrepn-(\w+)"[^>]*><b>(\d+)</b>', tiles), [("caught", "5"), ("held", "3"), ("again", "3"), ("person", "3")])
        self.assertIn("사람이 먼저 찾음", tiles)
        self.assertIn("다시 깨짐", tiles)
        self.assertNotIn("hnrepn-reverted", tiles)   # R2: no Reverted tile
        inc = _js("console.log(JSON.stringify(hnInc({cp: 'fast', mode: 'fast', fail: {ts: 1, rc: 1}, pass: {ts: 2}, state: 'reverted', at: 3})))")
        self.assertIn('class="hntrs hntrs-rv">되돌려짐<', inc)   # R2: Reverted stays on the incident card

    def test_r3_strip_and_filter(self):
        d = _data()
        h = _js("console.log(JSON.stringify(hnReport(%s)))" % d)
        strip = h.split("class=hnrepg", 1)[1].split("class=hnrepc>", 1)[0]
        self.assertEqual(re.findall(r"data-hncp=(\w+)", strip), ["hooks", "fast", "full", "person"])
        self.assertIn("발견 3", strip)
        none = _js("console.log(JSON.stringify(hnReport(%s)))" % _data(person=None, counts={}))   # older server: no person block
        self.assertNotIn("data-hncp=person", none)
        self.assertNotIn("hnperson", none)
        click = "LST.click.forEach(f => f({target: {closest: s => s === '.hnw [data-hncp]' ? {dataset: {hncp: 'person'}} : null}}));"
        r = _js(click + " console.log(JSON.stringify([HN.cp, hnReport(%s), URLS]))" % d)
        self.assertEqual(r[0], "person")
        self.assertEqual(set(re.findall(r"data-hncpc=(\w+)", r[1])), {"person"})   # R3: person cards only
        self.assertEqual(r[1].count("hnperson"), 3)
        self.assertEqual(r[2], [])
        self.assertIn("data-hncp=person aria-pressed=true", r[1])

    def test_r4_card_contents_escaped(self):
        h = _js("HN.cp = 'person'; console.log(JSON.stringify(hnReport(%s)))" % _data(dict(_PERSON, runs=5)))
        a, b, c = h.split('class="hnrun hnperson"')[1:4]
        self.assertIn("bug&lt;fix&gt;", a)
        self.assertIn('>abcdef01</code>', a)
        self.assertIn('title="이제 이것을 지키는 테스트">tests/test_&lt;x&gt;.py<', a)
        for bad in ("<img", "<x>", "<fix>"):
            self.assertNotIn(bad, h)
        self.assertIn("커밋 없음", b)
        self.assertIn("지키는 테스트 없음", b)       # R4: none → «no guarding test»
        self.assertIn("커밋을 읽지 못함", c)          # git miss is not «no commit»
        self.assertNotIn("지키는 테스트 없음", c)
        self.assertIn("이전에 찾은 2건은 목록에 없음", h)
        en = _js("LANG = 'en'; HN.cp = 'person'; console.log(JSON.stringify(hnReport(%s)))" % _data())
        self.assertIn("no guarding test", en)
        self.assertFalse(any("가" <= ch <= "힣" for ch in en.replace("bug&lt;fix&gt;", "")))

    def test_css_wraps(self):
        with open(os.path.join(ROOT, "web", "css", "41b-harness.css"), encoding="utf-8") as f:
            css = f.read()
        self.assertIn(".hnrepn-person{", css)
        self.assertIn(".hnpss{flex-wrap:wrap;min-width:0}", css)


if __name__ == "__main__":
    unittest.main()
