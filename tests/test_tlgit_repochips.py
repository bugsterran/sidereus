"""Timeline git rail repo chips (web/js/77-timeline-git.js tlgRepoChips / tlgTick): clean repos fold into «+N clean» (R1-R4)."""
import json
import re
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e

A, B, C = "/r/a", "/r/b", "/r/c"
DIRTY = {"ok": True, "n": 2, "files": [{"path": "x.py", "st": "M"}, {"path": "y.py", "st": "M"}]}
CLEAN = {"ok": True, "n": 0, "files": []}
UNTR = {"ok": True, "n": 1, "untracked": 1, "files": [{"path": "s.txt", "st": "A", "new": True}]}


def run(body, untr=False):
    src = js_all()
    consts = "\n".join(re.search(p, src, re.M).group(0) for p in (r"^const TLG_TTL_S = .*$", r"^const TLG_BG_TTL_S = .*$"))
    pre = ("let tlgUntr = %s, tlgMode = 'head', tlgOn = true, mainView = 'time', SESS = [], NOW = 1e9;\n"
           "let tlgRepoSel = {key: 'k', repo: '', all: false}; const tlgC = {}, urls = [];\n"
           "const document = {hidden: false}; Date.now = () => NOW;\n"
           "function T(s){ return s; } function TV(o){ return T(o.msg).replace(/\\{(\\w+)\\}/g, (m, k) => String(o.vars[k])); }\n"
           "const TLG_KB = ' data-kb'; function tlgFits(){ return true; } function tlgPaint(){}\n"
           "function getJSON(u){ urls.push(u); return new Promise(() => {}); }\n"
           "function esc(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;'); }\n"
           "const TG = {key: 'k', sid: 's1', repo: %s, repos: [%s, %s, %s]}; TG.ck = TG.repo + '\\0s1\\0head';\n"
           "function tlgTarget(){ return TG; }\n"
           "function put(r, d){ tlgC[r + '\\0s1\\0head'] = {at: 0, d, busy: false}; }\n"
           "function chips(){ const h = tlgRepoChips(TG); return {r: [...h.matchAll(/data-tgr=\"([^\"]*)\"/g)].map(m => m[1]),"
           " x: (h.match(/<em class=\"tlgrc tlgrx\"[^>]*data-tgrx[^>]*>([^<]*)</) || [])[1] || null}; }\n"
           % ("true" if untr else "false", json.dumps(A), json.dumps(A), json.dumps(B), json.dumps(C)))
    fns = "\n".join(js_fn(n) for n in ("tlgShown", "tlgShownN", "tlgRepoOrder", "tlgAge", "tlgRepoLabel", "tlgRepoChips", "tlgFetch", "tlgTick"))
    r = subprocess.run(node_e(consts + "\n" + pre + fns + "\n" + body), capture_output=True, text=True, timeout=20)
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


def out(expr):
    return "process.stdout.write(JSON.stringify(%s));" % expr


class RepoChips(unittest.TestCase):
    def test_r1_clean_repo_hidden_with_control(self):
        o = run("put(%s, %s); put(%s, %s); put(%s, %s);" % (json.dumps(A), json.dumps(DIRTY), json.dumps(B), json.dumps(CLEAN),
                                                           json.dumps(C), json.dumps(DIRTY)) + out("chips()"))
        self.assertEqual(o["r"], [A, C])
        self.assertEqual(o["x"], "+1 clean")

    def test_r2_selected_shown_when_clean(self):
        o = run("put(%s, %s); put(%s, %s); put(%s, %s);" % (json.dumps(A), json.dumps(CLEAN), json.dumps(B), json.dumps(DIRTY),
                                                           json.dumps(C), json.dumps(DIRTY)) + out("chips()"))
        self.assertEqual(o["r"], [A, B, C])
        self.assertIsNone(o["x"])

    def test_r4_unknown_status_shown(self):
        o = run("put(%s, {ok: false, msg: 'x'}); tlgC[%s + '\\0s1\\0head'] = {at: 0, d: null, busy: true};"
                % (json.dumps(B), json.dumps(C)) + out("chips()"))
        self.assertEqual(o["r"], [A, B, C])
        o = run(out("chips()"))   # no cache entry at all
        self.assertEqual(o["r"], [A, B, C])

    def test_r3_all_clean_selected_and_control_only(self):
        o = run("put(%s, %s); put(%s, %s);" % (json.dumps(B), json.dumps(CLEAN), json.dumps(C), json.dumps(CLEAN)) + out("chips()"))
        self.assertEqual(o["r"], [A])
        self.assertEqual(o["x"], "+2 clean")
        h = run("put(%s, %s); put(%s, %s);" % (json.dumps(B), json.dumps(CLEAN), json.dumps(C), json.dumps(CLEAN))
                + out("tlgRepoChips(TG)"))
        self.assertIn("data-tgrx", h)
        self.assertIn('title="Show repos with no changes"', h)

    def test_r3_reveal_shows_every_chip(self):
        o = run("put(%s, %s); put(%s, %s); tlgRepoSel.all = true;" % (json.dumps(B), json.dumps(CLEAN), json.dumps(C), json.dumps(CLEAN))
                + out("chips()"))
        self.assertEqual(o["r"], [A, B, C])
        self.assertIsNone(o["x"])

    def test_r1_untracked_only_repo_follows_filter(self):
        setup = "put(%s, %s);" % (json.dumps(B), json.dumps(UNTR))
        self.assertEqual(run(setup + out("chips()"))["r"], [A, C])
        self.assertEqual(run(setup + out("chips()"), untr=True)["r"], [A, B, C])

    def test_r1_header_count_matches_chip_rule(self):
        o = run(out("[tlgShownN(%s), tlgShownN(%s)]" % (json.dumps(UNTR), json.dumps(DIRTY))))
        self.assertEqual(o, [0, 2])

    def test_r1_tick_fetches_other_repos_once_per_ttl(self):
        o = run("tlgTick(); const n1 = urls.length; for(const k in tlgC){ tlgC[k].busy = false; tlgC[k].at = NOW; }"
                "NOW += 15000; tlgTick(); " + out("{n1, urls}"))
        self.assertEqual(o["n1"], 3)
        u = o["urls"]
        for r in (B, C):
            self.assertEqual(sum(("cwd=" + r.replace("/", "%2F") + "&base=head") in x for x in u), 1, u)
        # Selected repo refetches at 10 s; the others wait for 30 s.
        self.assertEqual(sum(("cwd=" + A.replace("/", "%2F") + "&base=head") in x for x in u), 2, u)


if __name__ == "__main__":
    unittest.main()

    def test_clean_but_ahead_not_folded(self):
        o = run("put(%s, {ok: true, n: 0, files: [], ahead: 2}); put(%s, %s);" % (json.dumps(B), json.dumps(C), json.dumps(CLEAN))
                + out("chips()"))
        self.assertEqual(o["r"], [A, B])
        self.assertEqual(o["x"], "+1 clean")

    def test_label_main_and_branch_with_folder_fallback(self):
        h = run("put(%s, {ok: true, n: 1, files: [], main: 'acme', branch: 'feat'});" % json.dumps(B) + out("tlgRepoChips(TG)"))
        self.assertIn(">acme · feat</em>", h)
        self.assertIn('title="/r/b"', h)
        self.assertIn(">a</em>", h)                            # no reply yet -> folder name
        h = run("put(%s, {ok: true, n: 1, files: [], branch: '<x>'});" % json.dumps(B) + out("tlgRepoChips(TG)"))
        self.assertIn(">b · &lt;x&gt;</em>", h)
