"""Every warn_once call site has an English form, and warn_once carries it to stderr and the health item.

AST scan only (no live files): a call passes if it has `en=` or its message has no Hangul at all.
"""
import ast
import contextlib
import glob
import io
import os
import re
import unittest

from tests._load import ROOT, sidereus

_HANGUL = re.compile("[가-힣]")
# (file, key) sites deliberately left Korean-only (none today).
ALLOWED = set()


def _strings(node):
    return [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _key(node):
    s = _strings(node)
    return s[0] if s else "?"


def _sites():
    files = [os.path.join(ROOT, "chat_server.py")] + sorted(glob.glob(os.path.join(ROOT, "sidereus", "*.py")))
    for fp in files:
        with open(fp, encoding="utf-8") as f:
            tree = ast.parse(f.read(), fp)
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            fn = n.func
            name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", None)
            if name == "warn_once" and n.args:
                yield os.path.relpath(fp, ROOT), n


class WarnEnglish(unittest.TestCase):
    def test_every_call_site_has_english(self):
        missing, seen = [], 0
        for rel, n in _sites():
            seen += 1
            key = _key(n.args[0])
            if (rel, key) in ALLOWED:
                continue
            kw = {k.arg: k.value for k in n.keywords}
            if "en" in kw:
                self.assertFalse(any(_HANGUL.search(s) for s in _strings(kw["en"])),
                                 "%s:%d en= contains Korean" % (rel, n.lineno))
                continue
            msg = n.args[1] if len(n.args) > 1 else kw.get("msg")
            if msg is None or any(_HANGUL.search(s) for s in _strings(msg)):
                missing.append("%s:%d %s" % (rel, n.lineno, key))
        self.assertGreater(seen, 50)
        self.assertEqual(missing, [], "warn_once without en=: " + ", ".join(missing))

    def test_warn_once_carries_english(self):
        W = sidereus("warn")
        saved = (list(W._WARN_LOG), set(W._warned), dict(W._SOFT), dict(W._wmute))
        try:
            W._WARN_LOG[:] = []
            W._warned.clear()
            W._SOFT.clear()
            W._wmute.clear()
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                W.warn_once("t-en", "old", en="English")           # older form: only the English text is kept
                W.warn_once("t-tv", "Lookup failed ({err})", vars={"err": ValueError("x")})
                for _ in range(W.SOFT_PROMOTE_N):
                    W.warn_once("t-soft", "slow ({n}s)", soft=True, vars={"n": 4},
                                more=[{"msg": "load {load} at the time", "vars": {"load": "9.1"}}])
            by = {w["key"]: w for w in W._WARN_LOG}
            self.assertEqual((by["t-en"]["msg"], by["t-en"]["msgEn"], by["t-en"]["tv"]),
                             ("English", "English", [{"msg": "English"}]))
            self.assertEqual((by["t-tv"]["msg"], by["t-tv"]["tv"]),
                             ("Lookup failed (x)", [{"msg": "Lookup failed ({err})", "vars": {"err": "x"}}]))
            soft = by["t-soft"]
            self.assertEqual(soft["msgEn"], "slow (4s) · load 9.1 at the time · repeated %d× in %d min — still slow"
                             % (W.SOFT_PROMOTE_N, W.SOFT_WIN_S // 60))
            self.assertEqual([p["msg"] for p in soft["tv"]],
                             ["slow ({n}s)", "load {load} at the time", "repeated {n}× in {min} min — still slow"])
            # Lines carry a log_ts() time prefix; compare the part after it.
            lines = [l.split(" ", 2)[2] if l[:2].isdigit() else l for l in err.getvalue().splitlines()]
            self.assertIn("⚠ English", lines)
            self.assertIn("⚠ Lookup failed (x)", lines)
            self.assertIn("⚠ slow (4s) · load 9.1 at the time", lines)
        finally:
            W._WARN_LOG[:] = saved[0]
            W._warned.clear(); W._warned.update(saved[1])
            W._SOFT.clear(); W._SOFT.update(saved[2])
            W._wmute.clear(); W._wmute.update(saved[3])


if __name__ == "__main__":
    unittest.main()
