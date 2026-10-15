"""Left rail (web/js/92d-rail.js) mode/restore rules, vertical tab keys (92-mainview-tabs.js) and pill placement (42-activity.js)."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e


def run(src):
    r = subprocess.run(node_e("const RAIL_W = 1200;\n" + src), capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class RailJs(unittest.TestCase):
    def test_mode(self):
        out = run(js_fn("railMode") + "\nprocess.stdout.write(JSON.stringify("
                  "[railMode(1440, false), railMode(1440, true), railMode(1200, true), railMode(1199, true), railMode(900, true)]));")
        self.assertEqual(out, ["collapsed", "push", "push", "overlay", "overlay"])

    def test_restore_never_overlay(self):
        out = run(js_fn("railRestore") + "\nprocess.stdout.write(JSON.stringify("
                  "[railRestore('1', 1440), railRestore('1', 1100), railRestore('0', 1440), railRestore(null, 1440)]));")
        self.assertEqual(out, [True, False, False, False])

    def test_key_b_skips_editable_fields(self):
        out = run(js_fn("railKeyB") + "\nconst k = (t, o) => railKeyB(Object.assign({key: 'b', code: 'KeyB', target: t}, o));\n"
                  "process.stdout.write(JSON.stringify([k({tagName: 'DIV'}, {metaKey: true}), k({tagName: 'BUTTON'}, {ctrlKey: true}),"
                  " k({tagName: 'TEXTAREA'}, {ctrlKey: true}), k({tagName: 'INPUT'}, {metaKey: true}), k({tagName: 'SELECT'}, {metaKey: true}),"
                  " k({tagName: 'DIV', isContentEditable: true}, {metaKey: true}), k({tagName: 'DIV'}, {}),"
                  " k({tagName: 'DIV'}, {metaKey: true, shiftKey: true})]));")
        self.assertEqual(out, [True, True, False, False, False, False, False, False])

    def test_covered_by_work_modal_and_others(self):
        src = ("let cfgHidden = true, cmdk = false, tour = false, wkOn = false, SESOPEN = false, SESPIN = false;\n"
               "const document = {getElementById: id => id === 'cfgm' ? {hidden: cfgHidden} : null, querySelector: () => cmdk ? {} : null};\n"
               "function tourIsOpen(){ return tour; }\n" + js_fn("railCovered") + "\n"
               "const r = [railCovered()]; wkOn = true; r.push(railCovered()); wkOn = false;\n"
               "SESOPEN = true; r.push(railCovered()); SESPIN = true; r.push(railCovered()); SESOPEN = SESPIN = false;\n"
               "cfgHidden = false; r.push(railCovered()); cfgHidden = true; cmdk = true; r.push(railCovered()); cmdk = false;\n"
               "tour = true; r.push(railCovered());\n"
               "process.stdout.write(JSON.stringify(r));")
        self.assertEqual(run(src), [False, True, True, False, True, True, True])

    def test_mvkey_up_down_and_left_right(self):
        src = ("let cur = 1; const set = [];\n"
               "const bs = [0, 1, 2].map(i => ({dataset: {mv: 'v' + i}, focus(){ cur = i; }}));\n"
               "const document = {querySelectorAll: () => bs};\n"
               "function setMainView(v){ set.push(v); }\n"
               + js_fn("mvKey") + "\n"
               "const press = k => { let pd = false; mvKey({key: k, currentTarget: bs[cur], preventDefault(){ pd = true; }}); return pd; };\n"
               "const r = [press('ArrowDown'), cur, press('ArrowDown'), cur, press('ArrowUp'), cur, press('ArrowLeft'), cur, press('ArrowRight'), cur, press('x')];\n"
               "process.stdout.write(JSON.stringify([r, set]));")
        r, seen = run(src)
        self.assertEqual(r, [True, 2, True, 0, True, 2, True, 1, True, 2, False])
        self.assertEqual(seen, ["v2", "v0", "v2", "v1", "v2"])

    def test_place_keeps_focused_pill(self):
        # Minimal DOM list: children/insertBefore/appendChild/contains on plain objects.
        src = ("function mk(n){ return {n, parentNode: null, contains(x){ return x === this; }}; }\n"
               "function box(){ const b = {children: [], contains(x){ return this.children.includes(x); },\n"
               "  insertBefore(e, ref){ if(e.parentNode) e.parentNode.children.splice(e.parentNode.children.indexOf(e), 1);\n"
               "    const i = ref ? this.children.indexOf(ref) : this.children.length; this.children.splice(i < 0 ? this.children.length : i, 0, e); e.parentNode = this; },\n"
               "  appendChild(e){ this.insertBefore(e, null); }}; return b; }\n"
               "const document = {activeElement: null};\n"
               + js_fn("actPlace") + "\n"
               "const a = mk('a'), b = mk('b'), c = mk('c'), run = box(), need = box();\n"
               "actPlace(run, [a, b]); actPlace(need, [c]);\n"
               "const s0 = [run.children.map(e => e.n), need.children.map(e => e.n)];\n"
               "document.activeElement = b; actPlace(need, [c, b]);\n"          # focused b would move to the other list
               "const s1 = [run.children.map(e => e.n), need.children.map(e => e.n)];\n"
               "actPlace(run, [b, a]);\n"                                         # reorder deferred while focus is inside
               "const s2 = run.children.map(e => e.n);\n"
               "document.activeElement = null; actPlace(need, [c, b]);\n"
               "const s3 = [run.children.map(e => e.n), need.children.map(e => e.n)];\n"
               "process.stdout.write(JSON.stringify([s0, s1, s2, s3]));")
        s0, s1, s2, s3 = run(src)
        self.assertEqual(s0, [["a", "b"], ["c"]])
        self.assertEqual(s1, [["a", "b"], ["c"]])
        self.assertEqual(s2, ["a", "b"])
        self.assertEqual(s3, [["a"], ["c", "b"]])

    def test_tip_text(self):
        # Fake buttons: .mvl/.rlab child text, aria-label fallback, digit hint for the first 9 tabs, Cmd+B for the toggle.
        src = ("const mk = (lab, aria, id) => ({id: id || '', querySelector: () => lab == null ? null : {textContent: lab}, getAttribute: () => aria || null});\n"
               + js_fn("railTipText") + "\n"
               "const tabs = Array.from({length: 10}, (_, i) => mk('Tab' + i));\n"
               "process.stdout.write(JSON.stringify([railTipText(tabs[0], tabs), railTipText(tabs[8], tabs), railTipText(tabs[9], tabs),"
               " railTipText(mk(null, 'Expand sidebar', 'railtg'), tabs, true), railTipText(mk(null, 'Expand sidebar', 'railtg'), tabs, false), railTipText(mk('Alerts', 'Completion alarms', 'bell'), tabs),"
               " railTipText(mk(null, 'Attention 3', 'rattnb'), tabs), railTipText(mk(null, null), tabs), railTipText(null, tabs)]));")
        self.assertEqual(run(src), [["Tab0", "1"], ["Tab8", "9"], ["Tab9", ""], ["Expand sidebar", "\u2318B"], ["Expand sidebar", "Ctrl+B"], ["Alerts", ""],
                                    ["Attention 3", ""], None, None])

    def test_peek_keeps_saved_pref(self):
        # Badge peek opens without lsSet; outside press / jump closes it; only railSet writes the pref.
        src = ("let railOpen = false; const saved = [];\n"
               "function lsSet(k, v){ saved.push(v); } function railTip(){} function railApply(){}\n"
               "const mk = inside => ({closest: () => inside ? {} : null});\n"
               "let SESS = [], hid = 0; function actHovHide(){ hid++; } function actTermSid(){ return ''; } function actKey(){ return ''; }\n"
               + "\n".join(js_fn(n) for n in ("railShow", "railSet", "railPeekEnd", "railPeekOut", "actGo"))
               + "\nlet railPeek = false; const r = [];\n"
               "railPeek = true; railShow(true); r.push(railOpen, railPeekOut(mk(true)), railPeekOut(mk(false)));\n"
               "if(railPeekOut(mk(false))) railPeekEnd(); r.push(railOpen, railPeek);\n"
               "railPeek = true; railShow(true); actGo('x'); r.push(railOpen, railPeek, hid);\n"
               "railSet(true); r.push(railOpen, railPeekOut(mk(false))); actGo('x'); r.push(railOpen);\n"
               "railPeek = true; railSet(false); r.push(railPeek, railOpen);\n"
               "process.stdout.write(JSON.stringify([r, saved]));")
        r, saved = run(src)
        self.assertEqual(r, [True, False, True, False, False, False, False, 1, True, False, True, False, False])
        self.assertEqual(saved, ["1", "0"])


if __name__ == "__main__":
    unittest.main()
