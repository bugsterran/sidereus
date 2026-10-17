"""Timeline toolbar «Changes» chip (web/js/77-timeline-git.js): untracked files never count, «⚠ n shared» from the
rail's conflict flag (paths only in the tooltip), plain «Changes» before a reply, fetch gating and the click baseline."""
import json
import re
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e

FILES = [{"path": "a.py", "st": "M", "add": 10, "del": 5, "conflict": True},
         {"path": "scratch/x.txt", "st": "A", "new": True, "add": 15, "del": 0, "conflict": True},
         {"path": "<b>.py", "st": "M", "add": 3, "del": 1, "conflict": True},
         {"path": "b.js", "st": "A", "add": 2, "del": 0}]
REPLY = {"ok": True, "n": 4, "untracked": 1, "add": 30, "del": 6, "files": FILES, "base": "abc1234"}
SESS = [{"sid": "s1", "cwd": "/r/a", "project": "a", "ageSec": 5}, {"sid": "s2", "cwd": "/r/b", "project": "b", "ageSec": 90}]


def run(body, sess=SESS):
    ttl = re.search(r"^const TLG_TTL_S = .*$", js_all(), re.M).group(0)
    pre = ("let tlgSel = '', mainView = 'time', NOW = 1e9, SESS = %s; const tlgC = {}, urls = [], opened = [];\n"
           "const document = {hidden: false}; Date.now = () => NOW;\n"
           "function T(s){ return s; } function TV(o){ return T(o.msg).replace(/\\{(\\w+)\\}/g, (m, k) => String(o.vars[k])); }\n"
           "function esc(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;'); }\n"
           "const cpKey = x => 's:' + x.sid, sid8 = s => s.slice(0, 8), stateLbl = s => s; function tlgPaint(){}\n"
           "function getJSON(u){ urls.push(u); return new Promise(() => {}); }\n"
           "function loadDiff(...a){ opened.push(a); }\n" % json.dumps(sess))
    fns = "\n".join(js_fn(n) for n in ("tlgShownN", "tlgNum", "tlgShared", "tlgAge", "tlgName", "tlgSessions", "tlgTarget",
                                        "tlgSelHtml", "tlgChipInner", "tlgFetch", "tlgTick", "tlgOpen"))
    r = subprocess.run(node_e(ttl + "\n" + pre + fns + "\n" + body), capture_output=True, text=True, timeout=20)
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


def chip(reply, sess=SESS):
    return run("const tg = tlgTarget(); if(tg) tlgC[tg.ck] = {at: 0, d: %s, busy: false};"
               " process.stdout.write(JSON.stringify(tlgChipInner(tg)));" % json.dumps(reply), sess)


def text(h):
    return re.sub(r"<[^>]*>", "", h.split("<button", 1)[1].split(">", 1)[1])


@unittest.skipUnless(shutil.which("node"), "node not installed")
class Chip(unittest.TestCase):
    def test_counts_exclude_untracked(self):
        h = chip(REPLY)
        self.assertIn("Changes · 3 files +15−6", text(h))      # 30-15 added, untracked file and its lines left out

    def test_shared_count_and_paths_only(self):
        h = chip(REPLY)
        self.assertIn("· ⚠ 2 shared", text(h))                # untracked x.txt is never shared
        tip = re.search(r'class=tlgsh title="([^"]*)"', h).group(1)
        self.assertIn("a.py\n&lt;b&gt;.py", tip)
        self.assertNotIn("x.txt", tip)

    def test_no_shared_suffix_without_conflicts(self):
        d = dict(REPLY, files=[dict(f, conflict=False) for f in FILES])
        self.assertNotIn("shared", chip(d))

    def test_no_reply_or_error_is_plain(self):
        self.assertEqual(text(chip(None)), "Changes")
        self.assertEqual(text(chip({"ok": False})), "Changes")

    def test_no_session_is_disabled_without_select(self):
        h = chip(None, [])
        self.assertIn(" disabled", h)
        self.assertNotIn("<select", h)

    def test_select_only_with_two_sessions(self):
        self.assertIn("<select", chip(None))
        self.assertNotIn("<select", chip(None, SESS[:1]))

    def test_tick_gating_and_ttl(self):
        # getJSON never settles here, so a finished fetch is simulated: busy off, at = now.
        o = run("tlgTick(); const a = urls.length; Object.assign(tlgC['/r/a'], {busy: false, at: NOW}); NOW += 29e3; tlgTick(); const b = urls.length;"
                " NOW += 2e3; tlgTick(); const c = urls.length; mainView = 'chat'; NOW += 60e3; tlgC['/r/a'].busy = false;"
                " tlgTick(); process.stdout.write(JSON.stringify({a, b, c, d: urls.length, u: urls[0]}));")
        self.assertEqual((o["a"], o["b"], o["c"], o["d"]), (1, 1, 2, 2))
        self.assertEqual(o["u"], "/api/git/diff?view=rail&cwd=%2Fr%2Fa&base=auto")

    def test_click_opens_at_baseline_with_sid(self):
        o = run("const tg = tlgTarget(); tlgOpen(); tlgC[tg.ck] = {d: {ok: true, base: 'abc1234'}}; tlgOpen();"
                " process.stdout.write(JSON.stringify(opened));")
        self.assertEqual(o, [["/r/a", "", "work", "", "s1"], ["/r/a", "", "b:abc1234", "", "s1"]])


if __name__ == "__main__":
    unittest.main()
