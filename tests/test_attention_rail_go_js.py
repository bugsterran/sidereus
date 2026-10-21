"""Rail «Attention» pill click (42-activity.js actGo): opens the drawer at the session's #attn row,
unfolds «+N more» / «N low-priority» when the row sits there, and falls back to cpGo when no row renders."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

FNS = ("attnUnfold", "actKey", "actAttnIds", "actAttnRow", "actAttnGo", "actGo")


def run(rows, more=False, low=False, sess=None):
    """rows = {'shown': [ids], 'low': [ids]}; rendered rows follow attnMore/attnLow like buildAttn."""
    sess = sess or [{"sid": "s1", "cwd": "/w"}]
    src = (
        "const ATTN_MAX = 2, ROWS = " + json.dumps(rows) + ", SESS = " + json.dumps(sess) + ";\n"
        "let attnMore = " + json.dumps(more) + ", attnLow = " + json.dumps(low) + ", rendered = [];\n"
        "const out = {reveal: 0, cp: [], scroll: [], flash: [], q: [], pref: [], peek: 0, term: 0};\n"
        "const CSS = {escape: s => s};\n"
        "const UIS = {setItem(k, v){ out.pref.push(k + '=' + v); }};\n"
        "function sesdrReveal(){ out.reveal++; } function softErr(n, e){ throw e; } function actHovHide(){}\n"
        "function railPeekEnd(){ out.peek++; } function termGo(){ out.term++; } function cpGo(x){ out.cp.push(x.sid); }\n"
        "function setTimeout(){}\n"
        "function attnRows(){ return {shown: ROWS.shown.map(id => ({id})), low: ROWS.low.map(id => ({id}))}; }\n"
        "function buildAttn(){ rendered = (attnMore ? ROWS.shown : ROWS.shown.slice(0, ATTN_MAX)).concat(attnLow ? ROWS.low : []); }\n"
        "const document = {querySelector(sel){ out.q.push(sel); const m = sel.match(/^#attn \\.atr\\[data-aid=\"(.*)\"\\]$/);\n"
        "  if(!m || rendered.indexOf(m[1]) < 0) return null;\n"
        "  return {id: m[1], scrollIntoView(o){ out.scroll.push([m[1], o.block]); }, classList: {add(c){ out.flash.push(c); }, remove(){}}}; }};\n"
        + "\n".join(js_fn(n) for n in FNS) + "\n"
        "actGo('s1'); out.more = attnMore; out.low = attnLow;\n"
        "process.stdout.write(JSON.stringify(out));")
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class RailAttentionGo(unittest.TestCase):
    def test_visible_row_reveals_drawer_and_targets_row(self):
        o = run({"shown": ["s1"], "low": []})
        self.assertEqual((o["reveal"], o["peek"], o["cp"], o["term"]), (1, 1, [], 0))
        self.assertIn('#attn .atr[data-aid="s1"]', o["q"])
        self.assertEqual((o["scroll"], o["flash"]), ([["s1", "nearest"]], ["cphit"]))
        self.assertEqual((o["more"], o["low"]), (False, False))

    def test_cwd_only_row_matches(self):
        o = run({"shown": ["cwd:/w"], "low": []})
        self.assertEqual(o["scroll"], [["cwd:/w", "nearest"]])

    def test_past_max_expands_more(self):
        o = run({"shown": ["a", "b", "s1"], "low": []})
        self.assertEqual((o["more"], o["low"], o["scroll"], o["cp"]), (True, False, [["s1", "nearest"]], []))

    def test_low_priority_expands_low(self):
        o = run({"shown": ["a"], "low": ["s1"]})
        self.assertEqual((o["low"], o["more"], o["pref"], o["scroll"]), (True, False, ["mbAttnLow=1"], [["s1", "nearest"]]))

    def test_absent_falls_back_to_cpgo(self):
        o = run({"shown": ["a"], "low": []})
        self.assertEqual((o["cp"], o["scroll"], o["more"], o["low"], o["term"]), (["s1"], [], False, False, 0))

    def test_unknown_key_does_nothing(self):
        o = run({"shown": ["s1"], "low": []}, sess=[{"sid": "zz", "cwd": "/z"}])
        self.assertEqual((o["reveal"], o["cp"], o["peek"]), (0, [], 1))


if __name__ == "__main__":
    unittest.main()
