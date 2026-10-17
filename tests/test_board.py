"""Branch-tab board (web/js/88b-board.js): brBoardModel sorts sessions into 막힘 > 실행 중 > 리뷰 > 완료 > 대기
and hides ended sessions that are not in the review queue."""
import json
import re
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e


def model(sess, rrows, arows):
    blk = re.search(r"^const BD_BLOCK[^\n]*$", js_all(), re.M).group(0)
    src = (blk + "\n" + js_fn("brBoardModel") + "\nconst r = brBoardModel(" + json.dumps(sess) + ", " + json.dumps(rrows)
           + ", " + json.dumps(arows) + ");\nconsole.log(JSON.stringify({hidden: r.hidden, cols: Object.fromEntries("
           "Object.entries(r.cols).map(([k, v]) => [k, v.map(c => (c.x || c.r).sid + (c.why ? ':' + c.why : ''))]))}));")
    return json.loads(subprocess.run(node_e(src), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


class BoardModel(unittest.TestCase):
    def test_columns_and_hidden(self):
        r = model([{"sid": "a", "state": "tool"}, {"sid": "b", "state": "wait"}, {"sid": "c", "state": "done"},
                   {"sid": "d", "state": "gone"}, {"sid": "e", "state": "wait", "err": 1}, {"sid": "f", "state": "wait"},
                   {"sid": "g", "state": "wait", "sub": [{"tid": "t"}]}, {"sid": "h", "state": "wait"}],
                  [{"sid": "d", "done": 0}, {"sid": "z", "done": 1}, {"sid": "f", "done": 0}],
                  [{"sid": "b", "sigs": [{"k": "loop"}]}, {"sid": "h", "sigs": [{"k": "done"}]}])
        self.assertEqual(r["cols"], {"blk": ["b:loop", "e:err"], "run": ["a", "g"], "rv": ["d", "f"], "ok": ["z"], "idle": ["h"]})
        self.assertEqual(r["hidden"], 1)   # c: ended, not in review

    def test_blocked_beats_review(self):
        r = model([{"sid": "a", "state": "ask"}], [{"sid": "a", "done": 0}], [])
        self.assertEqual(r["cols"]["blk"], ["a:ask"])
        self.assertEqual(r["cols"]["rv"], [])


def relay(sid, msgs, ack):
    src = js_fn("relayStat") + "\nconsole.log(JSON.stringify(relayStat(" + ", ".join(json.dumps(v) for v in (sid, msgs, ack)) + ")));"
    return json.loads(subprocess.run(node_e(src), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


class RelayStat(unittest.TestCase):
    MS = [{"id": "m1", "t": 1, "sid": "s1", "idSrc": "viewer", "to": "alice", "room": None},
          {"id": "m2", "t": 5, "sid": "s1", "idSrc": "viewer", "to": "alice", "room": None, "kind": "relay"},
          {"id": "m3", "t": 9, "sid": "s1", "idSrc": "watch", "to": "alice", "room": None}]

    def test_stages(self):
        self.assertIsNone(relay("s9", self.MS, {}))
        r = relay("s1", self.MS, {})
        self.assertEqual((r["id"], r["st"], r["lab"]), ("m2", 1, "Sent"))   # label key; T(lab, 'short') shows «보냄»   # newest viewer relay; m3 is not from the viewer
        # A watcher's `delivered` only notified — still «보냄»; «전달됨» needs the Stop hook receipt (acks[id].hooked).
        r = relay("s1", self.MS, {"m2": {"delivered": ["alice"], "ack": []}})
        self.assertEqual((r["st"], r["ping"]), (1, True))
        r = relay("s1", self.MS, {"m2": {"delivered": [], "hooked": ["alice"], "ack": []}})
        self.assertEqual((r["st"], r["lab"], r["ping"]), (2, "Delivered", False))
        self.assertEqual(relay("s1", self.MS, {"m2": {"hooked": ["bob"]}})["st"], 1)
        self.assertEqual(relay("s1", self.MS, {"m2": {"delivered": ["bob"], "ack": [{"who": "bob"}]}})["st"], 1)
        self.assertEqual(relay("s1", self.MS, {"m2": {"delivered": [], "ack": [{"who": "alice"}]}})["lab"], "Confirm")


def rvn_text(notes):
    return rvn_js("rvnPack(" + json.dumps(notes) + ", Infinity).text")


def rvn_js(expr):
    src = js_fn("rvnQuote") + "\n" + js_fn("rvnPack") + "\nconsole.log(JSON.stringify(" + expr + "));"
    return json.loads(subprocess.run(node_e(src), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


class RvnText(unittest.TestCase):
    """Line comments (web/js/88e-rvnotes.js) -> the comment block of the «수정 요청» relay body."""

    def test_empty(self):
        self.assertEqual(rvn_text([]), "")
        self.assertEqual(rvn_text([{"p": "a.py", "ln": 3, "c": "  "}]), "")

    def test_sorted_quoted_capped(self):
        out = rvn_text([{"p": "b.py", "ln": 9, "q": "x = 1\t", "c": "why?"},
                        {"p": "a.py", "ln": 12, "ln2": 15, "q": "y" * 300, "c": "first\nsecond"}])
        lines = out.split("\n")
        self.assertEqual(lines[0], "줄 코멘트 2건:")
        self.assertEqual(lines[1], "- a.py:12-15")
        self.assertEqual(lines[2], "  > " + "y" * 199 + "…")   # quote capped at 200 chars
        self.assertEqual(lines[3:5], ["  first", "  second"])
        self.assertEqual(lines[5:], ["- b.py:9", "  > x = 1", "  why?"])

    def test_range_quote_multiline(self):
        out = rvn_text([{"p": "a.py", "ln": 3, "ln2": 5, "q": "a = 1  \nb = 2\n" + "z" * 300, "c": "fix"}])
        self.assertEqual(out.split("\n")[1:4], ["- a.py:3-5", "  > a = 1", "  > b = 2"])
        self.assertLessEqual(len(out.split("\n")[4]), 4 + 200)   # the whole quote is capped at 200 chars

    def test_length_cap_keeps_order_and_reports_dropped(self):
        ns = [{"id": "n%d" % i, "p": "a.py", "ln": i + 1, "q": "q" * 300, "c": "c" * 1900} for i in range(12)]
        r = rvn_js("rvnPack(" + json.dumps(ns) + ", 19000)")
        self.assertLessEqual(len(r["text"]), 19000)
        self.assertEqual(r["ids"], ["n%d" % i for i in range(len(r["ids"]))])   # a prefix, in line order
        self.assertEqual(r["dropped"], 12 - len(r["ids"]))
        self.assertGreater(r["dropped"], 0)
        self.assertTrue(r["text"].endswith("… 코멘트 %d개는 길이 제한으로 빠졌습니다 — 나머지는 다음 요청으로" % r["dropped"]))
        self.assertEqual(rvn_js("rvnPack(" + json.dumps(ns[:1]) + ", 10)"), {"text": "", "ids": [], "dropped": 1})


def sel_js(expr):
    src = "\n".join(js_fn(f) for f in ("bdSelWhy", "bdSelToggle", "bdSelKeep", "bdRcpt")) + "\nconsole.log(JSON.stringify(" + expr + "));"
    return json.loads(subprocess.run(node_e(src), capture_output=True, text=True, check=True, encoding="utf-8").stdout)


class BoardMultiSelect(unittest.TestCase):
    """«선택» mode (web/js/88f-bdmulti.js): only identity-confirmed mailboxes are pickable; one recipient per picked sid."""
    TG = {"a": {"id": "alice", "login": True, "watch": True}, "b": {"id": "bob", "login": False},
          "c": {"id": "", "login": True}, "d": {"id": "dan", "login": True, "blocked": True}}

    def test_why(self):
        self.assertEqual(sel_js("bdSelWhy('', null)"), "No session id")   # key; T() shows it
        self.assertEqual(sel_js("bdSelWhy('a', %s)" % json.dumps(self.TG["a"])), "")
        for s in "bc":   # not logged in / no mailbox id -> same reason rvRelay disables on
            self.assertEqual(sel_js("bdSelWhy('%s', %s)" % (s, json.dumps(self.TG[s]))), "Not logged into the mailbox — cannot receive")

    def test_toggle(self):
        self.assertEqual(sel_js("bdSelToggle(['a'], 'd', true)"), ["a", "d"])
        self.assertEqual(sel_js("bdSelToggle(['a', 'd'], 'd', true)"), ["a", "d"])   # no duplicate
        self.assertEqual(sel_js("bdSelToggle(['a', 'd'], 'a', false)"), ["d"])
        self.assertEqual(sel_js("bdSelToggle(null, '', true)"), [])

    def test_keep_and_recipients(self):
        tg = json.dumps(self.TG)
        # b/c lost identity, z left the board, a is deduped; order kept
        self.assertEqual(sel_js("bdSelKeep(['d', 'b', 'a', 'z', 'c', 'a'], %s)" % tg), ["d", "a"])
        self.assertEqual(sel_js("bdRcpt(['d', 'b', 'a'], %s)" % tg),
                         [{"sid": "d", "id": "dan", "watch": False, "blocked": True},
                          {"sid": "a", "id": "alice", "watch": True, "blocked": False}])
        self.assertEqual(sel_js("bdRcpt(['a'], null)"), [])


if __name__ == "__main__":
    unittest.main()
