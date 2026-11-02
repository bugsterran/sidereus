"""TE() (web/js/05-i18n.js): server error replies translate only known I18N.ko keys and fill {name} slots from vars."""
import json
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._node import node_e

CASES = [
    "not allowed",
    {"ok": False, "err": "not a git repo"},
    {"ok": False, "err": "{rel} not found", "vars": {"rel": "a.json"}},
    {"ok": False, "error": "write failed ({e})", "vars": {"e": "OSError"}},
    {"ok": False, "why": "git {cmd}", "vars": {"cmd": "TimeoutExpired"}},
    {"ok": False, "err": "some arbitrary {rel} text", "vars": {"rel": "x"}},
    "constructor",
    {"ok": False, "msg": "git failed ({err})", "vars": {"err": "OSError"}},
    {},
    None,
]


def _run(lang):
    js = i18n_prelude("'%s'" % lang, ("T", "TV", "TE")) + \
        "process.stdout.write(JSON.stringify(%s.map(c => TE(c))));" % json.dumps(CASES)
    r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


class TestTE(unittest.TestCase):
    def test_ko(self):
        out = _run("ko")
        self.assertEqual(out[0], "허용되지 않습니다")
        self.assertEqual(out[1], "git 저장소가 아닙니다")
        self.assertEqual(out[2], "a.json 이(가) 없습니다")
        self.assertEqual(out[3], "쓰기 실패(OSError)")
        self.assertEqual(out[4], "git 오류(TimeoutExpired)")
        self.assertEqual(out[5], "some arbitrary {rel} text")    # unknown string: returned as is, no fill
        self.assertEqual(out[6], "constructor")                  # prototype member is not a key
        self.assertEqual(out[7], "git 실패(OSError)")            # msg path = TV()
        self.assertEqual(out[8:], ["", ""])

    def test_en(self):
        out = _run("en")
        self.assertEqual(out[:5], ["not allowed", "not a git repo", "a.json not found", "write failed (OSError)",
                                   "git TimeoutExpired"])
        self.assertEqual(out[5], "some arbitrary {rel} text")
        self.assertEqual(out[7], "git failed (OSError)")


if __name__ == "__main__":
    unittest.main()
