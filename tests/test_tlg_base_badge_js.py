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
    fns = "\n".join(js_fn(f) for f in ("T", "tlgBaseText", "tlgBaseLabel"))
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
        s = js_fn("tlgChipInner")
        self.assertIn("let body = tlgBaseLabel(d)", s)
        self.assertIn("} else body += esc(CH);", s)   # the word «Changes» only without counts

    def test_ko(self):
        self.assertIn("기본 브랜치 이후", _run("console.log(JSON.stringify(tlgBaseLabel({ok: true, baseKind: 'branch'})));", "ko"))


KEEP = """
const calls = [];
let POP = false, ACT = null;
const mk = n => ({n, contains: x => x === n + ':btn' || (x && x.n === n), replaceWith: o => calls.push('replace:' + n + '>' + o.n), focus: () => calls.push('focus:' + n)});
const OLD = mk('old'), NEW = mk('new');
const document = { get activeElement(){ return ACT; }, getElementById: id => id === 'tlgb' ? NEW : id === 'tlgcp' ? mk('cp') : null };
const popIsOpen = () => POP, tlgWire = () => calls.push('wire');
const box = {querySelector: () => OLD};
"""


def _keep(body):
    code = KEEP + "\n".join(js_fn(f) for f in ("tlgFocusId", "tlgKeep", "tlgRestore")) + "\n" + body + "\nconsole.log(JSON.stringify(calls));"
    r = subprocess.run(node_e(code), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr.decode())
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class HeadRebuild(unittest.TestCase):
    def test_idle_takes_the_new_group(self):
        self.assertEqual(_keep("tlgRestore(tlgKeep(box));"), ["wire"])

    def test_open_picker_keeps_old_opener(self):
        self.assertEqual(_keep("POP = true; tlgRestore(tlgKeep(box));"), ["replace:new>old", "wire"])

    def test_focus_inside_is_restored(self):
        f = _keep("const b = mk('old'); ACT = {n: 'old', focus: () => calls.push('refocus')}; tlgRestore(tlgKeep(box));")
        self.assertEqual(f, ["replace:new>old", "refocus", "wire"])
        self.assertEqual(_keep("ACT = {id: 'tlgcp'}; box.querySelector = () => null; tlgRestore(tlgKeep(box));"), ["focus:cp", "wire"])


if __name__ == "__main__":
    unittest.main()
