"""Guard: every text-mode open()/read_text()/write_text() names its encoding (tests: also text=True subprocess calls).

⚠Without encoding= Python uses the locale codec (cp1252 on Windows), so a UTF-8 file
raises UnicodeDecodeError there while macOS/Linux pass. Do not paper over it with PYTHONUTF8.
"""
import ast
import os
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = ("tests/fixtures/",)


def _str(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _kw(call, name):
    for k in call.keywords:
        if k.arg == name:
            return k.value
    return None


def needs_encoding(call):
    """True when `call` opens a file in text mode without encoding=."""
    f = call.func
    if any(k.arg is None for k in call.keywords):   # **kwargs may carry it
        return False
    if isinstance(f, ast.Name) and f.id == "open" or (
            isinstance(f, ast.Attribute) and f.attr == "open"
            and isinstance(f.value, ast.Name) and f.value.id == "io"):
        npos, mode = 3, (call.args[1] if len(call.args) > 1 else _kw(call, "mode"))
    elif isinstance(f, ast.Attribute) and f.attr == "read_text":
        npos, mode = 0, None
    elif isinstance(f, ast.Attribute) and f.attr == "write_text":
        npos, mode = 1, None
    else:
        return False
    if len(call.args) > npos or _kw(call, "encoding") is not None:
        return False
    if mode is not None:
        m = _str(mode)
        if m is None or "b" in m:   # non-literal mode: cannot tell, leave to review
            return False
    return True


def text_subprocess(call):
    """True for a text=True / universal_newlines=True call without encoding= (tests read our own UTF-8 output)."""
    return (_kw(call, "encoding") is None and not any(k.arg is None for k in call.keywords)
            and any(k.arg in ("text", "universal_newlines") and isinstance(k.value, ast.Constant) and k.value.value is True
                    for k in call.keywords))


def missing(path, subproc=False):
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    tree = ast.parse(src, path)
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call)
            and (needs_encoding(n) or subproc and text_subprocess(n))]


def is_test(rel):
    return rel.startswith("tests/") or "/tests/" in rel


def py_files():
    try:
        out = subprocess.run(["git", "ls-files", "-z", "--", "*.py"], cwd=ROOT,
                             capture_output=True, check=True).stdout.decode("utf-8")
    except (OSError, subprocess.CalledProcessError):
        raise unittest.SkipTest("not a git checkout")
    return [p for p in out.split("\0") if p and not p.startswith(SKIP_DIRS)
            and os.path.isfile(os.path.join(ROOT, p))]


class OpenEncodingTest(unittest.TestCase):
    def test_detector(self):
        def hit(s):
            return needs_encoding(ast.parse(s).body[0].value)
        self.assertTrue(hit('open(p)'))
        self.assertTrue(hit('open(p, "w")'))
        self.assertTrue(hit('io.open(p, mode="a")'))
        self.assertTrue(hit('P.read_text()'))
        self.assertTrue(hit('P.write_text(s)'))
        self.assertFalse(hit('open(p, "rb")'))
        self.assertFalse(hit('open(p, encoding="utf-8")'))
        self.assertFalse(hit('P.read_text("utf-8")'))
        self.assertFalse(hit('P.write_text(s, encoding="utf-8")'))
        self.assertFalse(hit('os.open(p, 0)'))
        self.assertTrue(text_subprocess(ast.parse('run(a, text=True)').body[0].value))
        self.assertFalse(text_subprocess(ast.parse('run(a, text=True, encoding="utf-8")').body[0].value))

    def test_repo_opens_name_encoding(self):
        bad = []
        for rel in py_files():
            for n in missing(os.path.join(ROOT, rel), subproc=is_test(rel)):
                bad.append("%s:%d" % (rel, n.lineno))
        self.assertEqual(bad, [], "text-mode open without encoding=: " + ", ".join(bad))


if __name__ == "__main__":
    unittest.main()
