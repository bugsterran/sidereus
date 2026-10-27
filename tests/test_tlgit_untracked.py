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
    ttl = "\n".join(re.search(p, js_all(), re.M).group(0) for p in (r"^const TLG_TTL_S = .*$", r"^const TLG_MAX_REPOS = .*$", r"^const TLG_NOGIT_TTL_S = .*$"))
    pre = ("let tlgSel = '', tlgBase = 'head', mainView = 'time', NOW = 1e9, SESS = %s; const tlgC = {}, urls = [], opened = [];\n"
           "const document = {hidden: false}; Date.now = () => NOW;\n"
           "function T(s){ return s; } function TV(o){ return T(o.msg).replace(/\\{(\\w+)\\}/g, (m, k) => String(o.vars[k])); }\n"
           "function esc(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;'); }\n"
           "const cpKey = x => 's:' + x.sid, sid8 = s => s.slice(0, 8), stateLbl = s => s; function tlgPaint(){}\n"
           "function tlgBaseLabel(){ return ''; } function tlgBaseText(){ return 'Base'; }\n"   # baseline badge: tests/test_tlg_base_badge_js.py
           "const PPC = {}; let PPS = null; function popIsOpen(){ return false; }\n"
           "function getJSON(u){ urls.push(u); return new Promise(() => {}); }\n"
           "function loadDiff(...a){ opened.push(a); }\n" % json.dumps(sess))
    fns = "\n".join(re.search(p, js_all(), re.M).group(0) for p in (r"^const TLG_AUTO = .*$", r"^let tlgSelS = .*$")) + "\n" + "\n".join(js_fn(n) for n in ("tlgShownN", "tlgNum", "tlgShared", "tlgAge", "tlgName", "tlgSessions", "tlgSid", "tlgRepos", "tlgTarget",
                                        "ppComboHtml", "tlgRepoName", "tlgCnt", "tlgProj", "tlgNote", "tlgSelHtml", "tlgRepoCfg", "tlgDirty", "tlgBaseTip", "tlgChipInner", "tlgOpenRepo",
                                        "tlgNoGit", "tlgFetch", "tlgNext", "tlgTick", "tlgOpen"))
    r = subprocess.run(node_e(ttl + "\n" + pre + fns + "\n" + body), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


def chip(reply, sess=SESS):
    return run("const tg = tlgTarget(); if(tg) tlgC[tg.ck] = {at: 0, d: %s, busy: false};"
               " process.stdout.write(JSON.stringify(tlgChipInner(tg)));" % json.dumps(reply), sess)


def text(h):
    return re.sub(r"<[^>]*>", "", h.split("id=tlgcp", 1)[1].split(">", 1)[1].split("</button>", 1)[0])


@unittest.skipUnless(shutil.which("node"), "node not installed")
class Chip(unittest.TestCase):
    def test_counts_exclude_untracked(self):
        h = chip(REPLY)
        self.assertEqual(text(h).split(" · ")[0], "3 files +15−6")      # 30-15 added, untracked file and its lines left out; «Changes» only in aria
        self.assertIn('aria-label="Changes · Base · 3 files +15 −6', h)

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
        self.assertNotIn("data-ppk", h)

    def test_picker_only_with_two_sessions(self):
        self.assertIn('data-ppk="tlgs"', chip(None))
        self.assertNotIn("data-ppk", chip(None, SESS[:1]))

    def test_chip_is_combo_opener_with_two_repos(self):
        # Opener only when the followed session itself has 2+ repos; other sessions' repos do not count.
        h = chip(None, [dict(SESS[0], repos=["/r/w"]), SESS[1]])
        self.assertIn('id=tlgcp data-ppo aria-haspopup=listbox aria-controls=ppop aria-expanded="false"', h)
        self.assertIn("Show this session's repositories with their changes", h)
        self.assertNotIn("data-ppo", chip(None))
        self.assertNotIn("data-ppo", chip(None, SESS[:1]))

    def test_tick_gating_and_ttl(self):
        # getJSON never settles here, so a finished fetch is simulated: busy off, at = now. One repo: /r/b is idle here.
        o = run("SESS = SESS.slice(0, 1); tlgTick(); const a = urls.length; Object.assign(tlgC['/r/a'], {busy: false, at: NOW}); NOW += 29e3; tlgTick(); const b = urls.length;"
                " NOW += 2e3; tlgTick(); const c = urls.length; mainView = 'chat'; NOW += 60e3; tlgC['/r/a'].busy = false;"
                " tlgTick(); process.stdout.write(JSON.stringify({a, b, c, d: urls.length, u: urls[0]}));")
        self.assertEqual((o["a"], o["b"], o["c"], o["d"]), (1, 1, 2, 2))
        self.assertEqual(o["u"], "/api/git/diff?view=rail&cwd=%2Fr%2Fa&base=head&sid=s1")

    def test_repos_fetched_one_at_a_time_followed_first(self):
        # getJSON settles on demand: each reply chains the next stale repo; never two in flight, all within the TTL after.
        o = run("let rs = []; getJSON = u => { urls.push(u); return new Promise(r => rs.push(r)); };"
                "SESS = [{sid: 's1', cwd: '/r/a', ageSec: 5, repos: ['/r/a', '/r/wt']}, {sid: 's2', cwd: '/r/b', ageSec: 9, repos: ['/r/wt']}];"
                "tlgSel = 's:s2'; const flight = []; tlgTick(); tlgTick(); flight.push(urls.length);"
                "(async () => { for(let i = 0; i < 4; i++){ const r = rs.shift(); if(r) r({ok: true}); await new Promise(z => setTimeout(z, 0)); flight.push(urls.length); }"
                " tlgTick(); process.stdout.write(JSON.stringify({flight, u: urls.map(u => decodeURIComponent(u.split('cwd=')[1].split('&')[0]))})); })();")
        self.assertEqual(o["flight"], [1, 2, 2, 2, 2])
        self.assertEqual(o["u"], ["/r/b", "/r/wt"])   # the followed session's repos only; s1's /r/a waits until s1 is followed

    def test_not_a_repo_not_refetched_each_ttl(self):
        o = run("SESS = SESS.slice(0, 1); tlgTick(); Object.assign(tlgC['/r/a'], {busy: false, at: NOW, d: {ok: false, msg: 'Not a git repository.'}});"
                " NOW += 31e3; tlgTick(); const a = urls.length; NOW += 600e3; tlgTick(); process.stdout.write(JSON.stringify([a, urls.length]));")
        self.assertEqual(o, [1, 2])

    def test_click_opens_at_baseline_with_sid(self):
        o = run("const tg = tlgTarget(); tlgOpen(); tlgC[tg.ck] = {d: {ok: true, base: 'abc1234'}}; tlgOpen();"
                " process.stdout.write(JSON.stringify(opened));")
        self.assertEqual(o, [["/r/a", "", "work", "", "s1"], ["/r/a", "", "b:abc1234", "", "s1"]])


if __name__ == "__main__":
    unittest.main()
