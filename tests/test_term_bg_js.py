"""termBtnHtml / termGo for a Claude Code background job: no «Copy command», never a `--resume` command."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e


def _async_fn(name):
    """js_fn only matches plain `function`; termGo is `async function`."""
    return re.compile(r"^async function " + name + r"\(.*?^}", re.S | re.M).search(js_all()).group(0)


def run(body):
    src = ("let TERM_APP = 'auto';\n"
           "const esc = s => String(s), T = s => s, out = {notes: [], copied: []};\n"
           "function note(s){ out.notes.push(s); } function softErr(){}\n"
           "async function copyText(s){ out.copied.push(s); return true; }\n"
           "let RESP = null; async function postJSON(){ return RESP; }\n"
           + "\n".join(js_fn(n) for n in ("termLive", "termCanFocus", "termBtnHtml")) + "\n"
           + _async_fn("termGo") + "\n"
           "(async () => {" + body + "\nprocess.stdout.write(JSON.stringify(out)); })();")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


BG = {"sid": "s1", "state": "wait", "term": {"app": "bg", "tty": None}}


@unittest.skipUnless(shutil.which("node"), "node not installed")
class BgButton(unittest.TestCase):
    def test_button_is_not_copy_command(self):
        o = run("out.h = ['sx', 'bd', 'at'].map(k => termBtnHtml(" + json.dumps(BG) + ", k));")
        for h in o["h"]:
            self.assertNotIn("Copy command", h)
            self.assertNotIn("--resume", h)
            self.assertIn("Background job", h)

    def test_click_copies_attach_or_nothing(self):
        o = run("RESP = {how: 'bg', cmd: 'claude attach 5a49e0bd'}; await termGo('s1');"
                "RESP = {how: 'bg', cmd: ''}; await termGo('s1');")
        self.assertEqual(o["copied"], ["claude attach 5a49e0bd"])
        self.assertEqual(o["notes"], ["Background job — copied the attach command: claude attach 5a49e0bd",
                                      "Background job — no terminal tab"])


if __name__ == "__main__":
    unittest.main()
