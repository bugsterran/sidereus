"""fetchErrMsg (web/js/08-ui-kit.js): a getJSON that never got a status shows «check the server», not the browser's English fetch error."""
import json
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._load import js_fn
from tests._node import node_e


def _run(lang):
    js = i18n_prelude("'%s'" % lang, ("T",)) + js_fn("fetchErrMsg") + \
        "\nconst te = new TypeError('Failed to fetch'), he = new Error('HTTP 503'); he.status = 503;" \
        "process.stdout.write(JSON.stringify([fetchErrMsg(te), fetchErrMsg(he), fetchErrMsg(null)]));"
    r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


class TestFetchErrMsg(unittest.TestCase):
    def test_ko(self):
        self.assertEqual(_run("ko"), ["서버를 확인하세요", "HTTP 503", "서버를 확인하세요"])

    def test_en(self):
        self.assertEqual(_run("en"), ["check the server", "HTTP 503", "check the server"])


if __name__ == "__main__":
    unittest.main()
