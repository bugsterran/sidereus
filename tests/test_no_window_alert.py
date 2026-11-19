"""R4: web/ holds no window.alert() call; messages go through the shared <dialog> (08c uiAlert).
prompt/confirm are guarded by tests/test_no_window_confirm.py.
Static source scan only; no live files beyond the repo's own web/."""
import glob
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")

# ⚠No \s before '(' — a UI literal such as 'Failure alert ({n})' must not count as a call.
CALL = re.compile(r"(?<![\w$.])alert\(|window\.alert\b")


def _files():
    return sorted(glob.glob(os.path.join(WEB, "*.js")) + glob.glob(os.path.join(WEB, "js", "*.js"))
                  + [os.path.join(WEB, "index.html")])


def _code(path):
    with open(path, encoding="utf-8") as f:
        src = f.read()
    return re.sub(r"(^|[^:\\'\"])//[^\n]*", r"\1", src)   # drop // comments (keeps «http://» in strings)


def _hits(code):
    return [code.count("\n", 0, m.start()) + 1 for m in CALL.finditer(code)]


class NoWindowAlert(unittest.TestCase):
    def test_no_alert_call(self):
        bad = []
        for p in _files():
            bad += ["%s:%d" % (os.path.relpath(p, WEB), n) for n in _hits(_code(p))]
        self.assertEqual(bad, [])

    def test_pattern_catches_calls_not_labels(self):
        self.assertEqual(len(_hits("x; alert('a'); window.alert; if(ok) alert(q);")), 3)
        self.assertEqual(_hits("T('Failure alert ({n})'); uiAlert(t); o.alert(1); $alert(2);"), [])


if __name__ == "__main__":
    unittest.main()
