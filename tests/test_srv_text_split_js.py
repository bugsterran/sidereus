"""Server text translated on the page without passing data through T(): blocked tool label, ctx card numbers, burn placeholders."""
import json
import os
import shutil
import subprocess
import unittest
from unittest import mock

from tests._i18n_js import i18n_switch
from tests._load import sidereus, js_fn
from tests._node import node_e


def run(lang, body, fns):
    js = ("let LANG = %s;\n" % json.dumps(lang) + i18n_switch(("T", "TV", "U", "TN", "srvEn")) + "\n"
          + "\n".join(js_fn(f) for f in fns) + "\nprocess.stdout.write(JSON.stringify(" + body + "));")
    r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20)
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PageSide(unittest.TestCase):
    def test_blocked_tool_keeps_name(self):
        body = "(() => { const stateLbl = s => s; return [T('Blocked'), sessLabel({state: 'tool', blocked: 'Bash waiting for approval'})]; })()"
        blk, got = run("ko", body, ["sessLabel"])
        self.assertEqual(got, blk + " · Bash 승인 대기")
        self.assertEqual(run("en", body, ["sessLabel"])[1], "Blocked · Bash waiting for approval")

    def test_ctx_card_numbers_translate(self):
        c = {"kind": "ctx", "pct": 87, "used": 174, "win": 200, "text": "87% (174k / 200k) — leave a handover before auto-compaction"}
        stub = "globalThis.cardText = c => c.text; globalThis.plStrip = s => s;"
        body = "(() => { %s return faLine(%s); })()" % (stub, json.dumps(c))
        self.assertEqual(run("ko", body, ["faLine"]), "87% (174k / 200k) — 자동 압축 전에 인수 노트를 남기세요")
        self.assertEqual(run("en", body, ["faLine"]), c["text"])
        old = dict(c)
        for k in ("pct", "used", "win"):
            del old[k]
        self.assertEqual(run("ko", "(() => { %s return faLine(%s); })()" % (stub, json.dumps(old)), ["faLine"]), old["text"])

    def test_burn_placeholders(self):
        body = "['임시(스크래치패드)', '홈', '홈x'].map(TN)"
        self.assertEqual(run("en", body, []), ["Temporary (scratchpad)", "Home", "홈x"])
        self.assertEqual(run("ko", body, []), ["임시(스크래치패드)", "홈", "홈x"])


class ServerSide(unittest.TestCase):
    def test_ctx_card_carries_numbers(self):
        n = sidereus("notes")
        got = []
        with mock.patch.dict(os.environ, {"MAILBOX_CARD_CTX": "1"}), \
                mock.patch.object(n, "_card_add", lambda *a: got.append(a)), \
                mock.patch.object(n, "_recent_card", lambda *a: False), \
                mock.patch.object(n, "_ctx_warned", set()):
            n._note_ctx({"sid": "s1", "cwd": "/w", "project": "p", "ctx": 174000, "win": 200000, "state": "tool"})
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0][5], {"pct": 87, "used": 174, "win": 200})


if __name__ == "__main__":
    unittest.main()
