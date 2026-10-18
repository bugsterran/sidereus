"""Timeline «Changes» chip baseline badge (77 tlgBaseLabel): effective baseKind label, chosen mode before a reply, warn on fallback.
Pure functions under node; no live files."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._load import ROOT, js_all, js_fn
from tests._node import node_e

STUBS = """
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
const I18N = { ko: {} };
"""


def _ko():
    with open(os.path.join(ROOT, "web", "js", "06-i18n-zo-tl.js"), encoding="utf-8") as fh:
        return fh.read()


def _run(body, lang="en", base="head"):
    src = js_all()
    consts = re.search(r"^const TLG_BASES = [^\n]*$", src, re.M).group(0)
    consts += "\n" + re.search(r"^const TLG_KIND = [^\n]*$", src, re.M).group(0)
    fns = "\n".join(js_fn(f) for f in ("T", "tlgBaseLabel"))
    code = ("let LANG = %s;\nlet tlgBase = %s;\n" % (json.dumps(lang), json.dumps(base)) + STUBS + _ko() + "\n"
            + consts + "\n" + fns + "\n" + body)
    r = subprocess.run(node_e(code), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class BaseBadge(unittest.TestCase):
    def test_kind_labels(self):
        r = _run("console.log(JSON.stringify(['head', 'start', 'branch', 'remote'].map(k => tlgBaseLabel({ok: true, baseKind: k, baseMode: k === 'head' ? 'head' : 'remote'}))));")
        self.assertEqual(r, ['<span class="tlgbk">Uncommitted</span>', '<span class="tlgbk">Since session start</span>',
                             '<span class="tlgbk">Since the default branch</span>', '<span class="tlgbk">Unpushed</span>'])

    def test_no_reply_shows_chosen_mode(self):
        self.assertEqual(_run("console.log(JSON.stringify([tlgBaseLabel(null), tlgBaseLabel({ok: false})]));", base="auto"),
                         ['<span class="tlgbk">Auto</span>'] * 2)
        self.assertIn("자동", _run("console.log(JSON.stringify(tlgBaseLabel(undefined)));", "ko", "auto"))

    def test_fallback_warns(self):
        r = _run("console.log(JSON.stringify([tlgBaseLabel({ok: true, baseKind: 'head', baseMode: 'remote'}),"
                 " tlgBaseLabel({ok: true, baseKind: 'start', baseMode: 'upstream', noRemote: true})]));")
        self.assertEqual(r, ['<span class="tlgbk tlgbkw">Uncommitted</span>', '<span class="tlgbk tlgbkw">Since session start</span>'])

    def test_badge_leads_chip(self):
        self.assertIn("tlgBaseLabel(d) + esc(T('Changes', 'chip'))", js_fn("tlgChipInner"))

    def test_ko(self):
        self.assertIn("기본 브랜치 이후", _run("console.log(JSON.stringify(tlgBaseLabel({ok: true, baseKind: 'branch'})));", "ko"))


if __name__ == "__main__":
    unittest.main()
