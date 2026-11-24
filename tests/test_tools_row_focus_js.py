"""Tools list (web/js/47-tools.js): Name cell tooltip on every row, keyboard focus kept across the repaint of Enter/Close.

⚠`.tvwt td` is nowrap+ellipsis, so a clipped name or read-only mark was unreachable without a title;
tlPaint replaces the list's innerHTML, so Enter on a row or Close dropped focus to <body>."""
import json
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

_STUBS = ("const T = s => s; const U = n => String(n); const fmtTok = n => String(n); const stamp = s => String(s);"
          " function esc(s){ return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/\"/g, '&quot;'); }"
          " const TOOL_SCOPE = {user: 'user', project: 'project', plugin: 'plugin'}; const TOOL_FLAG = {}; var TOOLF = null;"
          " function tvwFlagTip(){ return ''; } function tvwPipes(){ return ''; } function tvwVdRow(){ return ''; }\n")

# Fake DOM: each tlPaint disconnects the old elements and builds new rows for IDS; focus() moves activeElement.
_DOM = ("var IDS = ['a', 'b'], ELS = [], PAINTS = 0, TOOLS = {items: [{id: 'a', name: 'na', path: '/p/a'}, {id: 'b', name: 'nb', path: '/p/b'}]};"
        " const BODY = {closest(){ return null; }, isConnected: true};"
        " const document = {activeElement: BODY, querySelectorAll(s){ return s === '.tvwr[data-tid]' ? ELS.filter(e => e.dataset.tid) : []; }};"
        " const mk = tid => ({dataset: tid ? {tid} : {}, isConnected: true, closest(s){ return s === '.tvw' ? {} : null; },"
        "   focus(){ document.activeElement = this; }});"
        " function tlPaint(){ PAINTS++; ELS.forEach(e => { e.isConnected = false; }); ELS = IDS.map(mk).concat([mk(null)]);"
        "   if(!document.activeElement.isConnected) document.activeElement = BODY; }"
        " async function getJSON(){ return {ok: true, text: 'x'}; } function fetchErrMsg(){ return 'e'; }"
        " tlPaint();\n")


def _run(body, fns):
    js = _STUBS + _DOM + "\n".join(js_fn(f) for f in fns) + "\n" + body
    return json.loads(subprocess.run(node_e(js), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


class NameTitle(unittest.TestCase):
    def test_every_row_has_full_name_title(self):
        out = _run("console.log(JSON.stringify([tvwRow({id: 'h', kind: 'hook', scope: 'user', name: 'PreToolUse \"a\" long hook', path: '/x', on: true}, null),"
                   " tvwRow({id: 'p', kind: 'skill', scope: 'plugin', name: 'plg:sk', path: '/y', on: true, ro: true}, null)]))", ["tvwRow"])
        self.assertIn('title="PreToolUse &quot;a&quot; long hook"', out[0])
        self.assertIn('title="plg:sk · read-only">sk <s>read-only</s>', out[1])   # shown name drops the prefix, title keeps it


class FocusKept(unittest.TestCase):
    FNS = ["tvwRepaint", "tvwOpen", "tvwClose"]

    def test_enter_open_and_load_keep_row_focus(self):
        out = _run("document.activeElement = ELS[1]; tvwOpen('b').then(() => console.log(JSON.stringify("
                   "[PAINTS, document.activeElement.dataset.tid, document.activeElement.isConnected, TOOLF.text])));", self.FNS)
        self.assertEqual(out, [3, "b", True, "x"])   # open paint + loaded paint, focus back on row b both times

    def test_close_focuses_the_row_that_was_open(self):
        out = _run("TOOLF = {id: 'a'}; document.activeElement = ELS[2]; tvwClose();"   # ELS[2] = the Close button
                   " console.log(JSON.stringify([TOOLF, document.activeElement.dataset.tid]));", self.FNS)
        self.assertEqual(out, [None, "a"])

    def test_focus_outside_list_not_stolen(self):
        out = _run("TOOLF = {id: 'a'}; tvwClose(); console.log(JSON.stringify(document.activeElement === BODY));", self.FNS)
        self.assertTrue(out)


class PollGuard(unittest.TestCase):
    """web/js/47a-tools-tab.js tlPaint(poll): a focused row is repainted with focus kept (skipping froze the list
    after a click left focus on the row); any other focused control in the list still skips the poll."""
    _ENV = ("var mainView = 'tools', TLVIEW = 'tools', OUT = []; function tbSlot(){} function tlViewSeg(){ return ''; }"
            " function paintTools(){ OUT.push('paint'); } function tvwRepaint(id){ OUT.push('row:' + id); }"
            " const ROW = {dataset: {tid: 'b'}, closest(s){ return s === '.tvw' ? {} : null; }, matches(s){ return s === '.tvwr[data-tid]'; }};"
            " const INP = {dataset: {}, closest(s){ return s === '.tvw' ? {} : null; }, matches(){ return false; }};"
            " var HOVER = null; const document = {activeElement: null, getElementById(){ return {}; }, querySelector(){ return HOVER; }};\n")

    def _poll(self, setup):
        js = self._ENV + js_fn("tlPaint") + "\n" + setup + " tlPaint(true); console.log(JSON.stringify(OUT));"
        return json.loads(subprocess.run(node_e(js), capture_output=True, text=True, check=True, encoding="utf-8").stdout)

    def test_focused_row_repaints_with_focus(self):
        self.assertEqual(self._poll("document.activeElement = ROW;"), ["row:b"])

    def test_other_focused_control_skips(self):
        self.assertEqual(self._poll("document.activeElement = INP;"), [])

    def test_open_tooltip_skips(self):
        self.assertEqual(self._poll("document.activeElement = ROW; HOVER = {};"), [])

    def test_focus_outside_list_paints(self):
        self.assertEqual(self._poll(""), ["paint"])


if __name__ == "__main__":
    unittest.main()
