"""Tools file view and Harness «Could not send» never show the browser's raw fetch error text."""
import json
import re
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._load import js_all, js_fn
from tests._node import node_e


def _send_err(lang):
    js = i18n_prelude("'%s'" % lang, ("T",)) + js_fn("fetchErrMsg") + "\n" + js_fn("hnNxSendErr") + \
        "\nconst te = new TypeError('Failed to fetch');" \
        "const he = new Error('HTTP 503'); he.status = 503; he.body = null;" \
        "const be = new Error('bad recipient'); be.status = 400; be.body = {error: 'bad recipient'};" \
        "const se = new Error('no such session'); se.srv = true;" \
        "process.stdout.write(JSON.stringify([hnNxSendErr(te), hnNxSendErr(he), hnNxSendErr(be), hnNxSendErr(se)]));"
    r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


class TestHarnessSendErr(unittest.TestCase):
    def test_ko(self):
        self.assertEqual(_send_err("ko"), ["서버를 확인하세요", "HTTP 503", "bad recipient", "no such session"])

    def test_en(self):
        self.assertEqual(_send_err("en"), ["check the server", "HTTP 503", "bad recipient", "no such session"])


class TestToolsFileViewErr(unittest.TestCase):
    def test_file_view_catch_uses_fetch_err_msg(self):
        m = re.search(r"getJSON\('/api/tools/file\?id='.*\n\s*catch\(e\)\{([^\n]*)", js_all())
        self.assertIsNotNone(m)
        self.assertIn("fetchErrMsg(e)", m.group(1))
        self.assertNotIn("e.message", m.group(1))


if __name__ == "__main__":
    unittest.main()
