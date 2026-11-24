"""URL hash <-> main tab (web/js/92 mvHashKey/mvHashOf/mvHashSync, 05-i18n mainView boot order).
R4: old Tokens / Pipelines › Tools/Connections state lands on the «Tools» tab (05 mvToolsMoved -> 47a TLVIEW, 48 rewrites plview)."""
import json
import os
import re
import shutil
import subprocess
import unittest

from tests._load import ROOT, js_all, js_fn
from tests._node import node_e

def _src(name):
    with open(os.path.join(ROOT, "web", "js", name), encoding="utf-8") as f:
        return f.read()


TABS = ["pipe", "struct", "time", "chat", "br", "token", "hist", "retro", "tools"]


def run(body):
    js = js_fn("mvHashKey") + "\n" + js_fn("mvHashOf") + "\n" + body
    r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


def boot(hash_, own=None, ui=None, popup=False, full=False):
    """Evaluate the 05-i18n mainView IIFE against a stubbed location/storage; full = [mainView, mvToolsMoved, tabSet calls]."""
    iife = re.search(r"^let mainView = \(\(\) => \{.*?\}\)\(\);", js_all(), re.S | re.M).group(0)
    body = ("const location = {hash: %s}, UIS = %s, OWN = %s, SETS = [];\n" % (json.dumps(hash_), json.dumps(ui or {}), json.dumps(own or {}))
            + "const ISPOP = %s, ISWP = false, ISBP = false;\nlet mvToolsMoved = '';\n" % ("true" if popup else "false")
            + "function tabOwn(k){ return Object.prototype.hasOwnProperty.call(OWN, k) ? OWN[k] : null; }\n"
            + "function tabSet(k, v){ SETS.push([k, v]); return true; }\n"
            + iife + "\nprocess.stdout.write(JSON.stringify(%s));" % ("[mainView, mvToolsMoved, SETS]" if full else "mainView"))
    return run(body)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class MainViewHash(unittest.TestCase):
    def test_round_trip_every_tab(self):
        out = run("process.stdout.write(JSON.stringify(%s.map(k => [mvHashKey('#' + mvHashOf(k)), mvHashKey(k)])));"
                  % json.dumps(TABS))
        self.assertEqual(out, [[k, k] for k in TABS])

    def test_unknown_or_empty_is_null(self):
        out = run("process.stdout.write(JSON.stringify(['', '#', '#x', '#svccgo', null].map(mvHashKey)));")
        self.assertEqual(out, [None] * 5)
        self.assertEqual(run("process.stdout.write(JSON.stringify(mvHashOf('work')));"), "")

    def test_hash_beats_tab_memory(self):
        self.assertEqual(boot("#structure", own={"mbMainView": "chat"}, ui={"mbMainView": "time"}), "struct")

    def test_no_hash_keeps_order(self):
        self.assertEqual(boot("", own={"mbMainView": "chat"}, ui={"mbStartView": "time"}), "chat")
        self.assertEqual(boot("", ui={"mbStartView": "br", "mbMainView": "time"}), "br")
        self.assertEqual(boot("", ui={"mbMainView": "hist"}), "hist")
        self.assertEqual(boot("#nope"), "pipe")

    def test_feature_off_tab_refused_from_hash(self):
        self.assertEqual(boot("#insights", own={"mbMainView": "chat"}, ui={"mbTabsOff": '["retro"]'}), "chat")

    def test_popup_ignores_hash(self):
        self.assertEqual(boot("#structure", own={"mbMainView": "chat"}, popup=True), "chat")

    def test_r4_stored_tokens_tools_lands_on_tools(self):
        self.assertEqual(boot("", ui={"mbMainView": "token", "sidereus.tkview": "tools"}, full=True),
                         ["tools", "tools", [["mbMainView", "tools"]]])
        # a typed hash wins: the old sub-view still migrates (mvToolsMoved) but the tab is the hash's
        self.assertEqual(boot("#tokens", ui={"sidereus.tkview": "conn"}, full=True), ["token", "conn", []])

    def test_r4_tokens_redirect_with_pipelines_off(self):
        self.assertEqual(boot("", ui={"mbMainView": "token", "sidereus.tkview": "tools", "mbTabsOff": '["pipe"]'}, full=True),
                         ["tools", "tools", [["mbMainView", "tools"]]])

    def test_r4_stored_pipelines_tool_view_lands_on_tools(self):
        self.assertEqual(boot("", ui={"mbMainView": "pipe", "sidereus.plview": "conn"}, full=True),
                         ["tools", "conn", [["mbMainView", "tools"]]])
        self.assertEqual(boot("#pipelines", ui={"sidereus.plview": "tools"}, full=True), ["pipe", "tools", []])
        self.assertEqual(boot("", own={"mbMainView": "pipe"}, ui={"sidereus.plview": "conn"}, full=True),
                         ["tools", "conn", [["mbMainView", "tools"]]])

    def test_r4_end_to_end_tlview_and_plview_rewrite(self):
        """05 boot -> 47a TLVIEW init -> 48 PLVIEW init on one store: the matching Tools view opens and plview becomes 'pipe'."""
        src = {n: _src(n) for n in ("47a-tools-tab.js", "48-pipeline.js")}
        tl = re.search(r"^const TLVIEWS = .*?^\}\)\(\);", src["47a-tools-tab.js"], re.S | re.M).group(0)
        pl = re.search(r"^const PLVIEWS = .*?^\}\)\(\);", src["48-pipeline.js"], re.S | re.M).group(0)
        iife = re.search(r"^let mainView = \(\(\) => \{.*?\}\)\(\);", js_all(), re.S | re.M).group(0)
        for hash_, ui, tab, want in (("#pipelines", {"sidereus.plview": "tools"}, "pipe", "tools"),
                                     ("", {"mbMainView": "pipe", "sidereus.plview": "conn"}, "tools", "conn"),
                                     ("", {"mbMainView": "token", "sidereus.tkview": "conn", "mbTabsOff": '["pipe"]'}, "tools", "conn")):
            body = ("const location = {hash: %s}, UIS = %s, SETS = [];\n" % (json.dumps(hash_), json.dumps(ui))
                    + "const ISPOP = false, ISWP = false, ISBP = false;\nlet mvToolsMoved = '';\n"
                    + "function tabOwn(k){ return null; } function tabSet(k, v){ SETS.push([k, v]); return true; }\n"
                    + "function lsGet(k, d){ return Object.prototype.hasOwnProperty.call(UIS, k) ? UIS[k] : d; } function lsSet(k, v){ UIS[k] = v; }\n"
                    + iife + "\n" + tl + "\n" + pl + "\n"
                    + "process.stdout.write(JSON.stringify([mainView, TLVIEW, PLVIEW, UIS['sidereus.plview'] || null]));")
            plv = "pipe" if "sidereus.plview" in ui else None
            self.assertEqual(run(body), [tab, want, "pipe", plv], (hash_, ui))

    def test_typed_hash_beats_old_tool_view_redirect(self):
        """/#pipelines with an old plview 'conn' opens Pipelines; no mbMainView write, the sub-view still reaches 47a."""
        self.assertEqual(boot("#pipelines", ui={"sidereus.plview": "conn"}), "pipe")
        self.assertEqual(boot("#pipelines", ui={"mbMainView": "time", "sidereus.plview": "conn"}, full=True), ["pipe", "conn", []])

    def test_r4_usage_and_other_tabs_unchanged(self):
        self.assertEqual(boot("#tokens", ui={"sidereus.tkview": "use"}, full=True), ["token", "", []])
        self.assertEqual(boot("#tokens", full=True), ["token", "", []])   # bare #tokens with no stored view still opens Usage
        self.assertEqual(boot("", ui={"mbMainView": "time", "sidereus.tkview": "tools"}, full=True), ["time", "", []])
        self.assertEqual(boot("", ui={"mbMainView": "time", "sidereus.plview": "conn"}, full=True), ["time", "", []])
        self.assertEqual(boot("#pipelines", ui={"sidereus.plview": "harness"}, full=True), ["pipe", "", []])
        self.assertEqual(boot("#tools", full=True), ["tools", "", []])

    def test_r1_tools_tab_below_structure(self):
        """Tools sits right below Structure (both read a repo's setup); shortcut digit = rail position (92 buildMv kbN)."""
        mp = _src("90b-mypref.js")
        tabs = json.loads(re.search(r"^const MP_TABS = (\[[^\]]*\]);", mp, re.M).group(1).replace("'", '"'))
        self.assertEqual(tabs, ["pipe", "time", "struct", "tools", "br", "token", "hist", "retro", "chat"])
        mv = _src("92-mainview-tabs.js")
        self.assertNotRegex(re.search(r"^const TAB_FEAT = .*$", mv, re.M).group(0), r"tools")   # reachable with Pipelines off
        self.assertIn("tools: T('Tools')", mv)
        self.assertIn("|| v === 'tools') ? v : 'time'", mv)

    def test_sync_uses_replace_state_and_skips_popups(self):
        tpl = ("let mainView = 'br'; const ISPOP = %s, ISWP = false, ISBP = false, calls = [];\n"
               "const location = {pathname: '/', search: '?a=1', hash: '#timeline'};\n"
               "const history = {state: null, replaceState: (s, t, u) => calls.push(u)};\n"
               "function softErr(){}\n" + js_fn("mvHashSync")
               + "\nmvHashSync(); location.hash = '#branches'; mvHashSync(); process.stdout.write(JSON.stringify(calls));")
        self.assertEqual(run(tpl % "false"), ["/?a=1#branches"])
        self.assertEqual(run(tpl % "true"), [])


if __name__ == "__main__":
    unittest.main()
