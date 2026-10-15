"""Agent rows labeled by the Agent tool's task description (2026-09-25): server row carries a truncated `desc`,
JS picks desc + type chip / type only (no desc or setting off)."""
import json
import os
import subprocess
import tempfile
import unittest

from tests._load import sidereus, js_fn
from tests._node import node_e

tl = sidereus("timeline")


class RowDesc(unittest.TestCase):
    def setUp(self):
        self.saved = {k: getattr(tl, k) for k in ("_agent_last", "_sess_segments", "_agent_tools", "_agent_fin")}
        tl._agent_last = lambda f: ""
        tl._sess_segments = lambda *a, **k: ([], 0)
        tl._agent_tools = lambda f: 0
        tl._agent_fin = lambda f: False
        fd, self.f = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(tl, k, v)
        os.unlink(self.f)

    def test_desc_truncated(self):
        mm = {"_file": self.f, "_id": "a1", "agentType": "general-purpose", "description": "x" * 200}
        r = tl._tl_agent_row("toolu_1", mm, 0, {}, {}, "p", "/w/p")
        self.assertEqual(r["desc"], "x" * 80)
        self.assertEqual(r["type"], "general-purpose")
        r = tl._tl_agent_row("toolu_2", dict(mm, description=None), 0, {}, {}, "p", "/w/p")
        self.assertEqual(r["desc"], "")


def run(body):
    src = ("const esc = s => String(s).replace(/</g, '&lt;');\nlet tlAgDesc = true;\n"
           + js_fn("plStrip") + "\n" + js_fn("tlAgLab") + "\n" + js_fn("tlAgNm") + "\n" + body)
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


class Label(unittest.TestCase):
    def test_choice(self):
        out = run("const g = d => ({type: 'builder', items: [{aid: 'a1', desc: 'old'}, {aid: 'a2', desc: d}]});"
                  "const x = {type: 'gemini', items: [{aid: '', desc: 'gemini -p · m'}]};"
                  "process.stdout.write(JSON.stringify([tlAgLab(g('Fix <rail>'), true), tlAgLab(g(''), true),"
                  " tlAgLab(g('Fix'), false), tlAgLab(x, true), tlAgNm(g('Fix <rail>')), tlAgNm(g('Fix'), false)]));")
        self.assertEqual(out[0], {"lab": "Fix <rail>", "type": "builder"})     # latest run's desc + type chip
        self.assertEqual(out[1], {"lab": "builder", "type": ""})               # no desc -> type
        self.assertEqual(out[2], {"lab": "builder", "type": ""})               # setting off -> type
        self.assertEqual(out[3], {"lab": "gemini", "type": ""})                # ext child (no aid) -> type
        self.assertIn('<em class=tlagd title="Fix &lt;rail>">Fix &lt;rail></em>', out[4])
        self.assertIn('<i class="tlpar tlagt">builder</i>', out[4])
        self.assertEqual(out[5], "builder")


if __name__ == "__main__":
    unittest.main()
