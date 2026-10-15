"""48d plEvLine: a stage card names the newest gate run inside its window (metadata only)."""
import json
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._load import js_fn
from tests._node import node_e


def _ev(rows, L, commits=None):
    call = "plEvLine(%s, %s)" % (json.dumps(rows), json.dumps(L)) if commits is None else "plEvLine(%s, %s, %s)" % (json.dumps(rows), json.dumps(L), json.dumps(commits))
    src = (i18n_prelude("'ko'", ("T", "TV", "U")) + "const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\"/g, '&quot;');\n"
           + js_fn("plEvLine") + "\nconsole.log(JSON.stringify(%s))" % call)
    return json.loads(subprocess.run(node_e(src), capture_output=True, text=True, check=True).stdout)


PASS = {"ts": 1000, "rc": 0, "steps": [{"name": "tests", "rc": 0, "n": 2908, "failed": 0}],
        "screen": [{"ok": True}, {"ok": True}]}
FAIL = {"ts": 900, "rc": 1, "steps": [{"name": "py_compile", "rc": 0, "n": 9}, {"name": "tests", "rc": 1, "n": 912, "failed": 3}]}


class EvLine(unittest.TestCase):
    def test_pass_in_window(self):
        h = _ev([PASS, FAIL], {"w0": 950, "w1": 990})
        self.assertIn("게이트 PASS · 테스트 2908 · 화면 2/2", h)
        self.assertNotIn("plevng", h)

    def test_fail_names_first_bad_step(self):
        h = _ev([PASS, FAIL], {"w0": 850, "w1": 920})
        self.assertIn("게이트 FAIL · tests 실패 3/912", h)
        self.assertIn("plevng", h)

    def test_outside_window_or_no_window(self):
        self.assertEqual(_ev([PASS], {"w0": 2000, "w1": 2100}), "")
        self.assertEqual(_ev([PASS], {"w0": 0, "w1": 0}), "")

    def test_latest_pass_window(self):
        # second pass starts at 950: the first pass's FAIL (ts 900) must not show; rows are newest first
        h = _ev([PASS, FAIL], {"w0": 850, "w1": 1010, "k": 2, "p0": 950})
        self.assertIn("게이트 PASS", h)
        self.assertEqual(_ev([FAIL], {"w0": 850, "w1": 1010, "k": 2, "p0": 950}), "")

    def test_earlier_pass_window(self):
        # pass 1 (850..940) failed its gate, the latest pass (950..) passed: each window shows its own result
        src = (i18n_prelude("'ko'", ("T", "TV", "U")) + "const esc = s => String(s);\nconst plAgLab = a => a.lab;\n" + js_fn("plAgLabs") + "\n" + js_fn("plPass")
               + "\n" + js_fn("plEvLine") + "\nconst L = %s;\nconsole.log(JSON.stringify([plEvLine(%s, Object.assign({}, L, plPass(L, 0))), plEvLine(%s, L)]))"
               % (json.dumps({"w0": 850, "w1": 1010, "k": 2, "p0": 950, "ag": [], "ps": [{"a": 850, "b": 940, "s": "back"}]}), json.dumps([PASS, FAIL]), json.dumps([PASS, FAIL])))
        one, latest = json.loads(subprocess.run(node_e(src), capture_output=True, text=True, check=True).stdout)
        self.assertIn("게이트 FAIL", one)
        self.assertIn("게이트 PASS", latest)

    def test_step_name_escaped(self):
        bad = {"ts": 10, "rc": 1, "steps": [{"name": "<b>x", "rc": 2}]}
        h = _ev([bad], {"w0": 5, "w1": 20})
        self.assertIn("&lt;b&gt;x rc=2", h)
        self.assertNotIn("<b>x", h)


    def test_pass_counts_and_tooltip(self):
        h = _ev([PASS], {"w0": 950, "w1": 990}, [])
        self.assertIn(">게이트 PASS · 테스트 2908 · 화면 2/2<", h)
        self.assertIn("tests rc=0 n=2908 failed=0", h)

    def test_fail_screen_first_bad_plus_more(self):
        r = {"ts": 100, "rc": 1, "head": "abc1234", "steps": [{"name": "tests", "rc": 0, "n": 5}, {"name": "screen", "rc": 1, "n": 6, "failed": 2}],
             "screen": [{"w": 900, "lang": "ko", "ok": True}, {"w": 1100, "lang": "ko", "ok": False}, {"w": 1440, "lang": "en", "ok": False}]}
        h = _ev([r], {"w0": 90, "w1": 110})
        self.assertIn(">게이트 FAIL · 화면 1100-ko +1<", h)
        self.assertIn("plevng", h)
        self.assertIn("head abc1234", h)

    def test_fail_tests_f_of_n(self):
        self.assertIn(">게이트 FAIL · tests 실패 3/912<", _ev([FAIL], {"w0": 850, "w1": 920}, []))

    def test_commit_appended_and_commit_only(self):
        cms = [{"h": "0123456789ab", "ct": 1100}, {"h": "fedcba9", "ct": 500}]
        h = _ev([PASS], {"w0": 950, "w1": 990, "cm": [980.5]}, cms)
        self.assertIn("화면 2/2 · 커밋 0123456<", h)
        self.assertIn("커밋 0123456789ab", h)   # full hash in the tooltip
        only = _ev([], {"w0": 400, "w1": 600, "cm": [499.0]}, cms)
        self.assertIn(">커밋 fedcba9<", only)
        self.assertNotIn("plevng", only)

    def test_commit_outside_window_ignored(self):
        cms = [{"h": "0123456", "ct": 1300}, {"h": "fedcba9", "ct": 970}]
        self.assertEqual(_ev([], {"w0": 950, "w1": 990, "cm": [980]}, cms), "")   # 1300 > cm+300, 970 < cm-2
        self.assertNotIn("커밋", _ev([PASS], {"w0": 950, "w1": 990, "cm": [980]}, cms))

    def test_commit_closest_not_newest(self):
        cms = [{"h": "bbbbbbb", "ct": 1200}, {"h": "aaaaaaa", "ct": 1010}]   # newest first, both within cm+300
        self.assertIn(">커밋 aaaaaaa<", _ev([], {"w0": 950, "w1": 1100, "cm": [1000]}, cms))

    def test_no_rows_empty(self):
        self.assertEqual(_ev([], {"w0": 950, "w1": 990}, []), "")
        self.assertEqual(_ev([], {"w0": 950, "w1": 990, "cm": [960]}), "")

    def test_two_arg_call_unchanged(self):
        L = {"w0": 950, "w1": 990, "cm": [980]}
        self.assertEqual(_ev([PASS], L), _ev([PASS], {"w0": 950, "w1": 990}, []))


if __name__ == "__main__":
    unittest.main()
