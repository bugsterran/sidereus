"""Server text from sidereus/l*-z*.py is English with a Korean entry in I18N.ko (06-i18n-zz-srv2.js).

warn_once templates (+ the soft-promotion and load parts in sidereus/warn.py) and {msg, vars} replies are looked up by
TV() on the page; a missing ko entry falls back to English silently, so this test is the guard.
Static source scan + the real dictionaries loaded in node (no live files).
"""
import ast
import glob
import json
import os
import re
import subprocess
import unittest
from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = sorted(f for f in glob.glob(os.path.join(ROOT, "sidereus", "*.py")) if "l" <= os.path.basename(f)[0] <= "z")
HANGUL = re.compile("[가-힣]")
# Fixed parts warn.py / live_probe.py add to a warning (not a warn_once literal at a call site).
PARTS = ("repeated {n}× in {min} min — still slow", "still slow", "load {load} at the time",
         "Background thread {name} stopped — {exc}", "Background thread {name} stopped — {exc} ({where})",
         # action clauses sessions_health.health() appends to kept warnings (BANNER_KEEP)
         "restart Sidereus", "install Claude Code or add it to PATH",
         "run `claude agents --json` in a terminal to see why", "fix or remove that file",
         "check free disk space and permissions of the data folder")
# Phrases spliced into a template with `%` at the call site (usage.py `_shape_list(..., what)`).
WHATS = ("the 5-hour blocks view", "the weekly totals view")

_LOAD = r"""
const fs = require('fs'), dir = process.argv[1];
let src = 'var UIS={},document={documentElement:null,getElementById:()=>null},navigator={language:"ko"};function tabOwn(){return null}\n';
for (const f of fs.readdirSync(dir).sort()) if (/^0[56].*i18n.*\.js$/.test(f)) src += fs.readFileSync(dir + '/' + f, 'utf8') + '\n';
process.stdout.write(JSON.stringify(new Function(src + 'return I18N;')().ko));
"""


def _texts(a):
    """Every literal text an argument can take, or None when it is not a literal form this scan knows."""
    if isinstance(a, ast.Constant) and isinstance(a.value, str):
        return [a.value]
    if isinstance(a, ast.IfExp):
        b, o = _texts(a.body), _texts(a.orelse)
        return b + o if b is not None and o is not None else None
    if isinstance(a, ast.BinOp) and isinstance(a.op, ast.Add):
        left, right = _texts(a.left), _texts(a.right)
        return [x + y for x in left for y in right] if left is not None and right is not None else None
    if isinstance(a, ast.BinOp) and isinstance(a.op, ast.Mod) and isinstance(a.left, ast.Constant):
        return [a.left.value % w for w in WHATS]
    if isinstance(a, (ast.Name, ast.Subscript)):
        return []          # PENDING_MSG / INVITE_MSGS[...] constants: tests/test_room_admin.py checks those keys
    return None


def _templates():
    found = []
    for f in FILES:
        with open(f, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        rel = os.path.relpath(f, ROOT)
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "warn_once" and len(n.args) >= 2:
                found.append(("%s:%d" % (rel, n.lineno), _texts(n.args[1])))
            elif isinstance(n, ast.Dict):
                keys = [k.value for k in n.keys if isinstance(k, ast.Constant)]
                if "vars" in keys:
                    for k, v in zip(n.keys, n.values):
                        if isinstance(k, ast.Constant) and k.value == "msg":
                            found.append(("%s:%d" % (rel, n.lineno), _texts(v)))
    return found


class ServerTextKo2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = subprocess.run(node_e(_LOAD, os.path.join(ROOT, "web", "js")),
                             capture_output=True, text=True, check=True)
        cls.ko = json.loads(out.stdout)
        cls.found = _templates()

    def test_every_template_is_english_with_ko(self):
        self.assertGreater(len(self.found), 60)
        bad = []
        for where, texts in self.found:
            if texts is None:
                bad.append(where + " not a literal template")
                continue
            for t in texts:
                if HANGUL.search(t) or t not in self.ko:
                    bad.append("%s %r" % (where, t))
        self.assertEqual(bad, [])

    def test_fixed_parts_have_ko(self):
        self.assertEqual([p for p in PARTS if p not in self.ko], [])


if __name__ == "__main__":
    unittest.main()
