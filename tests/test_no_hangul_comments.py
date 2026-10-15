"""Comments and docstrings in shipped Python are English only (open-source audience).

UI labels are quoted by their I18N.en text in «»; Korean stays only in code string literals.
Reads repo source files only.
"""
import ast
import glob
import io
import os
import re
import tokenize
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HANGUL = re.compile("[가-힣ᄀ-ᇿ㄰-㆏]")
GLOBS = ("chat_server.py", "*.py", "sidereus/*.py", "hooks/*.py", "mcp/*.py", "scripts/*.py")


def shipped_files():
    out = set()
    for g in GLOBS:
        out.update(glob.glob(os.path.join(ROOT, g)))
    return sorted(out)


def hangul_hits(path):
    """[(line, kind)] for comment tokens and module/class/function docstrings holding Hangul."""
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    hits = []
    for t in tokenize.generate_tokens(io.StringIO(src).readline):
        if t.type == tokenize.COMMENT and HANGUL.search(t.string):
            hits.append((t.start[0], "comment"))
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.body:
            e = n.body[0]
            if (isinstance(e, ast.Expr) and isinstance(e.value, ast.Constant)
                    and isinstance(e.value.value, str) and HANGUL.search(e.value.value)):
                hits.append((e.lineno, "docstring"))
    return hits


class NoHangulComments(unittest.TestCase):
    def test_files_found(self):
        self.assertIn(os.path.join(ROOT, "chat_server.py"), shipped_files())
        self.assertGreater(len(shipped_files()), 50)

    def test_detector(self):
        self.assertTrue(HANGUL.search("한"))      # syllable
        self.assertTrue(HANGUL.search("ㄱ"))      # compatibility jamo
        self.assertFalse(HANGUL.search("«Today» ★ ⚠ ⇒"))

    def test_no_hangul(self):
        bad = []
        for p in shipped_files():
            for line, kind in hangul_hits(p):
                bad.append("%s:%d (%s)" % (os.path.relpath(p, ROOT), line, kind))
        self.assertEqual(bad, [], "Hangul in comments/docstrings:\n" + "\n".join(bad))


if __name__ == "__main__":
    unittest.main()
