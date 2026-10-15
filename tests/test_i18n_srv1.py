"""Server text from chat_server.py and sidereus/a*-h*.py is English with a Korean entry in I18N.ko.

warn_once templates and {msg, vars} replies are looked up by TV() on the page; a missing ko entry falls back to
English silently, so this test is the guard. Static source scan + the real dictionaries loaded in node.
"""
import ast
import glob
import json
import os
import re
import subprocess
import unittest
from tests._node import node_e


def _read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = [os.path.join(ROOT, "chat_server.py")] + sorted(glob.glob(os.path.join(ROOT, "sidereus", "[a-h]*.py")))
HANGUL = re.compile("[가-힣]")

_LOAD = r"""
const fs = require('fs'), dir = process.argv[1];
let src = 'var UIS={},document={documentElement:null,getElementById:()=>null},navigator={language:"ko"};function tabOwn(){return null}\n';
for (const f of fs.readdirSync(dir).sort()) if (/^0[56].*i18n.*\.js$/.test(f)) src += fs.readFileSync(dir + '/' + f, 'utf8') + '\n';
const I = new Function(src + 'return I18N;')();
process.stdout.write(JSON.stringify(I.ko));
"""


def _ko():
    out = subprocess.run(node_e(_LOAD, os.path.join(ROOT, "web", "js")), capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def _hook_docs():
    """HOOK_DOC_EN of every platform module (fixed phrase baked into the hooks warning template)."""
    out = []
    for p in glob.glob(os.path.join(ROOT, "sidereus", "plat_*.py")):
        m = re.search(r'^HOOK_DOC_EN = "([^"]+)"', _read(p), re.M)
        if m:
            out.append(m.group(1))
    return out


def _templates():
    """(file:line, text) for every warn_once template and every {msg|error, vars} reply literal."""
    found = []
    for f in FILES:
        tree = ast.parse(_read(f))
        rel = os.path.relpath(f, ROOT)
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "warn_once" and len(n.args) >= 2:
                a = n.args[1]
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    found.append(("%s:%d" % (rel, n.lineno), a.value))
                elif isinstance(a, ast.BinOp) and isinstance(a.left, ast.Constant) \
                        and getattr(a.right, "attr", None) == "HOOK_DOC_EN":
                    found.extend(("%s:%d" % (rel, n.lineno), a.left.value + d) for d in _hook_docs())
                else:
                    found.append(("%s:%d" % (rel, n.lineno), None))
            elif isinstance(n, ast.Dict):
                keys = [k.value for k in n.keys if isinstance(k, ast.Constant)]
                if "vars" in keys:
                    for k, v in zip(n.keys, n.values):
                        if isinstance(k, ast.Constant) and k.value in ("msg", "error", "err") and isinstance(v, ast.Constant):
                            found.append(("%s:%d" % (rel, n.lineno), v.value))
    return found


class ServerTextKo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ko = _ko()
        cls.found = _templates()

    def test_found_some(self):
        self.assertGreater(len([t for _w, t in self.found if t]), 50)

    def test_templates_are_english_with_ko_entry(self):
        for where, t in self.found:
            if t is None:
                continue
            with self.subTest(where=where, text=t):
                self.assertIsNone(HANGUL.search(t))
                self.assertIn(t, self.ko)

    def test_ko_keeps_the_slots(self):
        for where, t in self.found:
            if t and t in self.ko:
                with self.subTest(where=where):
                    self.assertEqual(sorted(re.findall(r"\{(\w+)\}", t)), sorted(re.findall(r"\{(\w+)\}", self.ko[t])))


if __name__ == "__main__":
    unittest.main()
