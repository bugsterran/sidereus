"""Harness «흐름» strip (web/js/47c-harness-flow.js, with 47b for shared helpers): node order, escaping, node click without fetch."""
import json
import os
import subprocess
import unittest

from tests._i18n_js import i18n_switch
from tests._load import ROOT
from tests.test_harness_js import _STUB
from tests._node import node_e

_B = os.path.join(ROOT, "web", "js", "47b-harness.js")
_C = os.path.join(ROOT, "web", "js", "47c-harness-flow.js")
KEYS = ["req", "guard", "edit", "gate", "review", "commit", "keep"]


def _node(k, st="ok", v=None, rec=None):
    return {"k": k, "st": st, "v": v, "rec": rec or []}


def _run(rid, name, t1, **over):
    v = {"req": {"t0": t1 - 100, "sid8": "abcd1234", "name": name}, "guard": {"deny": None, "skip": 2, "loop": 1},
         "edit": {"files": 3, "commits": 1, "from": "aaaa111", "to": "bbbb222", "dirty": False},
         "gate": {"steps": [{"name": "tests", "rc": 0, "n": 9, "failed": 0, "secs": 1, "mode": "full"}], "rows": 2, "r2g": True},
         "review": None, "commit": {"head": "bbbb2222cccc", "dirty": False}, "keep": {"state": "held", "mode": "full", "ts": t1}}
    v.update(over)
    rec = {"edit": [{"path": "src/a.py", "add": 3, "del": 1}],
           "gate": [{"kind": "check", "ts": t1, "mode": "full", "head": "bbbb222", "dirty": False, "rc": 0, "steps": []}]}
    return {"id": rid, "src": "plrun", "name": name, "sid8": "abcd1234", "t0": t1 - 100, "t1": t1, "end": t1,
            "nodes": [_node(k, "none" if v[k] is None else "ok", v[k], rec.get(k)) for k in KEYS]}


def _js(body):
    src = _STUB + i18n_switch() + "const document = {addEventListener(){}};\n"
    for p in (_B, _C):
        with open(p, encoding="utf-8") as f:
            src += f.read() + "\n"
    return json.loads(subprocess.run(node_e(src + body), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


class HarnessFlowJs(unittest.TestCase):
    def test_node_check(self):
        subprocess.run(["node", "--check", _C], check=True)

    def test_order_guard_and_selector(self):
        fl = [_run("r2", "newer", 2000), _run("r1", "older", 1000)]
        h = _js("console.log(JSON.stringify(hnFlow(%s)))" % json.dumps(fl))
        idx = [h.index('data-hnfn="%s"' % k) for k in KEYS]
        self.assertEqual(idx, sorted(idx))
        self.assertEqual(h.count("hnfa"), 6)
        self.assertLess(h.index('data-hnfr="r2"'), h.index('data-hnfr="r1"'))
        self.assertIn('class="hnfb on" data-hnfr="r2"', h)
        self.assertNotIn("기록 없음", h)   # counts present: no «no record» beside them
        self.assertIn("<span class=hnfi1>건너뜀 선언 2</span>", h)   # one unbreakable item
        for t in ("건너뜀 선언 2", "되돌림 1", "파일 3개", "Red→Green", "해당 없음", ">bbbb2222<", "Stable"):
            self.assertIn(t, h)
        self.assertNotIn("hnfrec", h)   # nothing open until a node is chosen

    def test_escape_and_class_whitelist(self):
        r = _run("<x>", "<img src=x onerror=1>", 1000)
        r["nodes"][0]["st"] = "ok\" onclick=\"x"
        r["nodes"][1]["rec"] = [{"k": "skip", "title": "<b>t</b>"}]
        h = _js("HN.flowNode = 'guard'; console.log(JSON.stringify(hnFlow(%s)))" % json.dumps([r]))
        self.assertNotIn("<img", h)
        self.assertNotIn("<b>t", h)
        self.assertNotIn("onclick", h)
        self.assertIn("hnf-none", h)
        self.assertIn("&lt;b&gt;t&lt;/b&gt;", h)

    def test_guard_deny(self):
        r = _run("r1", "x", 1000, guard={"deny": 2, "skip": 0, "loop": 0})
        r["nodes"][1]["rec"] = [{"k": "deny", "ts": 900, "code": "agent", "title": "<b>구현</b>"},
                                {"k": "deny", "ts": 800, "code": "<i>x</i>", "title": ""}]
        h = _js("HN.flowNode = 'guard'; console.log(JSON.stringify(hnFlow(%s)))" % json.dumps([r]))
        self.assertIn("차단 2", h)
        self.assertNotIn("기록 없음", h)
        self.assertIn("에이전트 불일치 · &lt;b&gt;구현&lt;/b&gt;", h)
        self.assertIn("&lt;i&gt;x&lt;/i&gt;", h)
        self.assertNotIn("<b>구현", h)

    def test_node_rec_without_fetch(self):
        fl = [_run("r2", "newer", 2000), _run("r1", "older", 1000)]
        body = ("HN.flowRun = 'r1'; HN.flowNode = 'edit'; const a = hnFlow(%s); HN.flowNode = 'gate'; const b = hnFlow(%s);"
                "console.log(JSON.stringify({a, b, urls: URLS}))") % (json.dumps(fl), json.dumps(fl))
        r = _js(body)
        self.assertIn('class="hnfb on" data-hnfr="r1"', r["a"])
        self.assertIn("src/a.py", r["a"])
        self.assertIn('aria-expanded=true><b class=hnft>수정', r["a"])
        self.assertIn("hnrun", r["b"])
        self.assertEqual(r["urls"], [])

    def test_why_badges(self):
        want = {"norec": ("기록 없음", "게이트 증거가 없습니다"), "pending": ("아직", "커밋 전"),
                "window": ("읽기 범위 밖", "512 KB"), "na": ("해당 없음", "단계가 없습니다")}
        for why, (lab, tip) in want.items():
            r = _run("r1", "x", 1000, commit=None)
            r["nodes"][5]["why"] = why
            h = _js("HN.flowNode = 'commit'; console.log(JSON.stringify(hnFlow(%s)))" % json.dumps([r]))
            self.assertIn('class="hntm hnf-w-%s" title="' % why, h)
            self.assertIn(">%s</i>" % lab, h)
            self.assertIn(tip, h)
            self.assertNotIn("<div class=hidnote>기록 없음</div>", h)   # rec panel shows the cause too
        r = _run("r1", "x", 1000, commit=None)
        r["nodes"][5]["why"] = "norec"
        h = _js("LANG = 'en'; console.log(JSON.stringify(hnFlow(%s)))" % json.dumps([r]))
        self.assertIn('title="No gate evidence for this repo', h)
        self.assertIn(">not recorded</i>", h)

    def test_why_unknown_is_dash(self):
        for why in ("x\" onclick=\"y", "<b>", "constructor", None):
            r = _run("r1", "x", 1000, commit=None)
            if why is not None:
                r["nodes"][5]["why"] = why
            h = _js("console.log(JSON.stringify(hnFlow(%s)))" % json.dumps([r]))
            self.assertIn("<i class=hntm>—</i>", h)
            self.assertNotIn("hnf-w-", h)
            self.assertNotIn("onclick", h)

    def test_html_order(self):
        data = {"ok": True, "events": [], "rules": [], "agents": [], "evidence": [], "flow": [_run("r1", "x", 1000)]}
        h = _js("HN.data[hnKey('/w/a')] = %s; HN.at[hnKey('/w/a')] = NOW; console.log(JSON.stringify(hnHtml()))" % json.dumps(data))
        self.assertLess(h.index("hnfw0"), h.index("data-hnmore=det"))
        self.assertLess(h.index("data-hnmore=det"), h.index("hncfg"))
        self.assertIn("<details class=hnmore data-hnmore=det open>", h)   # open by default, flow or not
        data["flow"] = []
        h = _js("HN.data[hnKey('/w/a')] = %s; HN.at[hnKey('/w/a')] = NOW; console.log(JSON.stringify(hnHtml()))" % json.dumps(data))
        self.assertIn("<details class=hnmore data-hnmore=det open>", h)


if __name__ == "__main__":
    unittest.main()
