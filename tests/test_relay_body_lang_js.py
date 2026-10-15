"""Relay bodies follow the UI language: rvBody (web/js/88c-review.js) carries no Hangul under LANG=en."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._node import node_e

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HANGUL = re.compile("[가-힣ㄱ-ㆎ]")


def src(name):
    with open(os.path.join(ROOT, "web", "js", name), encoding="utf-8") as f:
        return f.read()


def fn(s, n):
    return re.search(r"^function " + n + r"\(.*?^}", s, re.S | re.M).group(0)


def run(lang):
    rv = src("88c-review.js")
    js = "\n".join(["let LANG = " + json.dumps(lang) + ";",
                    i18n_prelude("LANG", ("T", "KE")), "const rvBase = p => String(p).split('/').pop();",
                    fn(rv, "rvFileLines"), fn(rv, "rvBody"),
                    "const F = [{path: 'a.py', add: 1, del: 2, rv: 0}];",
                    "console.log(JSON.stringify([rvBody('fix', F, ''), rvBody('commit', F, ''), rvBody('stop', F, ''),",
                    "  rvBody('go', F, '')]));"])
    r = subprocess.run(node_e(js), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class RelayBodyLang(unittest.TestCase):
    def test_en_has_no_hangul(self):
        for body in run("en"):
            self.assertTrue(body)
            self.assertIsNone(HANGUL.search(body), body)

    def test_ko_unchanged(self):
        r = run("ko")
        self.assertTrue(r[0].startswith("수정 요청 — 아래 파일을 다시 확인해 주세요.\n\n- a.py (+1/-2)"))
        self.assertTrue(r[1].startswith("검토 끝났습니다. 이 변경을 커밋해 주세요\n\n"))
        self.assertEqual(r[2], "멈춰 주세요 — 하던 작업을 멈추고 다음 지시를 기다려 주세요.")
        self.assertEqual(r[3], "이어가 주세요.")


if __name__ == "__main__":
    unittest.main()
