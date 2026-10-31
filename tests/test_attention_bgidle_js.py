"""«Idle shells» attention row (17-attention.js): English why rebuilt from the server numbers, click goes to the session."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e

WHY = "백그라운드 셸 3개 · 무출력 2개 · 최장 25분"


def node(src):
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


def const_src(name):
    m = re.search(r"^const " + name + r" = [\s\S]*?;$", js_all(), re.M)
    return m.group(0)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class BgIdleJs(unittest.TestCase):
    def why(self, lang, w):
        src = ("let LANG = " + json.dumps(lang) + "; const T = s => s; const UNIT_KO = {m: '\\ubd84'};\n"
               + "\n".join(js_fn(n) for n in ("U", "PL", "attnWhy")) + "\n"
               "process.stdout.write(JSON.stringify(attnWhy({k: 'bgidle', why: " + json.dumps(w) + "})));")
        return node(src)

    def test_R2_en_why(self):
        self.assertEqual(self.why("en", WHY), "3 background shells · 2 idle · longest 25m")
        self.assertEqual(self.why("en", WHY.replace("셸 3개", "셸 1개")), "1 background shell · 2 idle · longest 25m")
        self.assertEqual(self.why("ko", WHY), WHY)

    def test_R2_label(self):
        self.assertIn("bgidle:'Idle shells'", const_src("ATTN_LBL"))
        self.assertNotIn("bgidle", const_src("ATTN_LIST_ONLY"))

    def test_R3_click(self):
        # Same go handler as any non-terminal kind: scroll to the session card via cpGo.
        src = ("const out = []; " + const_src("ALARM_TERM_KINDS") + "\n"
               "function termJumpSid(s){ return s; } function termGo(s){ out.push('term:' + s); }\n"
               "function attnSess(r){ return {sid: r.sid}; } function cpGo(x){ out.push('cp:' + x.sid); }\n"
               + "\n".join(js_fn(n) for n in ("attnTermSid", "attnRowGo")) + "\n"
               "for(const k of ['bgidle', 'ctx85', 'ask']) attnRowGo({sid: k, sigs: [{k}]}, k, '/w');\n"
               "process.stdout.write(JSON.stringify(out));")
        self.assertEqual(node(src), ["cp:bgidle", "cp:ctx85", "term:ask"])


if __name__ == "__main__":
    unittest.main()
