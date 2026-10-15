"""Health banner (web/js/25-health-todo.js buildHealth): stale-only draws nothing; a dead thread adds the restart hint."""
import json
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._load import js_fn
from tests._node import node_e

BASE = ("const EL = {className: '', title: '', html: null};\n"
        "var document = {getElementById: () => EL};\n"
        "const esc = s => String(s), setHtml = (e, h) => { e.html = h; }, agoAt = () => '1m', hlMsg = w => w.msg || '';\n"
        "let HLTH = null;\n")


def run(body, lang="'en'"):
    src = (BASE + i18n_prelude(lang) + js_fn("buildHealth")
           + "\nconst R = {};\n" + body + "\nprocess.stdout.write(JSON.stringify(R));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class HealthBanner(unittest.TestCase):
    def test_stale_only_is_empty(self):
        R = run("HLTH = {stale: [{key: 'k', label: 'x', at: 1}], diag: [{key: 'd'}]}; buildHealth();"
                " R.h = EL.html; R.c = EL.className; R.t = EL.title;")
        self.assertEqual((R["h"], R["c"], R["t"]), ("", "hlb", ""))

    def test_dead_has_restart_clause(self):
        R = run("HLTH = {dead: [{thread: 'poll', exc: 'Boom', at: 1}], stale: [{key: 'k', label: 'x', at: 1}]};"
                " buildHealth(); R.h = EL.html;")
        self.assertIn("poll · Boom · Restart Sidereus to recover", R["h"])
        self.assertNotIn("previous", R["h"])

    def test_dead_restart_clause_korean(self):
        R = run("HLTH = {dead: [{thread: 'poll', exc: 'Boom', at: 1}]}; buildHealth(); R.h = EL.html;", lang="'ko'")
        self.assertIn("Sidereus를 재시작하면 복구됩니다", R["h"])


if __name__ == "__main__":
    unittest.main()
