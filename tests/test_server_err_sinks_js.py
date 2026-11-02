"""Server error replies reach the UI through TE(): a known key is translated under ko, raw text stays as sent.

Covers the «Features» save note (90c mpfSave) and the prefs error fallback (90b mpSrvErr); both used to show r.err raw.
"""
import json
import os
import subprocess
import unittest

from tests._load import js_fn, ROOT
from tests._node import node_e
from tests._i18n_js import i18n_prelude

def _async_fn(fname, name):
    """Top-level `async function name` from web/js/<fname> (js_fn only finds plain functions)."""
    with open(os.path.join(ROOT, "web", "js", fname), encoding="utf-8") as fh:
        src = fh.read()
    i = src.index("\nasync function " + name + "(") + 1
    return src[i:src.index("\n}\n", i) + 3]


def _run(body):
    pre = i18n_prelude("'ko'", ("T", "TV", "TE"))
    r = subprocess.run(node_e(pre + body), capture_output=True, text=True, timeout=20, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


class ServerErrSinks(unittest.TestCase):
    def test_features_save_note_translates_known_key(self):
        src = ("let MPF_NOTE = null, MPF_PEND = null; const paintCfg = () => {}, mpfWant = () => ({a: false}), featsApply = null;\n"
               "let REPLY;\nconst postJSON = async () => REPLY;\n" + _async_fn("90c-features.js", "mpfSave") + "\n"
               "(async () => { const out = {};\n"
               "  REPLY = {ok: false, err: 'Bad request'}; await mpfSave([{id: 'a'}]); out.known = MPF_NOTE.err;\n"
               "  REPLY = {ok: false, err: 'disk on fire'}; await mpfSave([{id: 'a'}]); out.raw = MPF_NOTE.err;\n"
               "  REPLY = null; await mpfSave([{id: 'a'}]); out.none = MPF_NOTE.err;\n"
               "  console.log(JSON.stringify(out)); })();\n")
        R = _run(src)
        self.assertEqual(R["known"], "저장하지 못했습니다: 잘못된 요청입니다")
        self.assertEqual(R["raw"], "저장하지 못했습니다: disk on fire")   # unknown server text is shown unchanged
        self.assertEqual(R["none"], "저장하지 못했습니다: ?")               # no reply = unknown, not blank

    def test_prefs_fallback_goes_through_te(self):
        src = ("const MP_SRV_ERR = [];\n" + js_fn("mpSrvErr") + "\n"
               "console.log(JSON.stringify({known: mpSrvErr('Bad request'), raw: mpSrvErr('constructor')}));\n")
        R = _run(src)
        self.assertEqual(R["known"], "저장 실패: 잘못된 요청입니다")
        self.assertTrue(R["raw"].endswith(": constructor"), R["raw"])


if __name__ == "__main__":
    unittest.main()
