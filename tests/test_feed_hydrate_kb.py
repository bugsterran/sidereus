"""10-feed.js hydrate() queues stubs asked for mid-fetch; olderClick ignores re-entry; 98-a11y.js kbKey() maps IME keys by e.code."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_all, js_fn
from tests._node import node_e


def _async_fn(name):
    import re   # js_fn only matches plain `function`
    return re.compile(r"^async function " + name + r"\(.*?^}", re.S | re.M).search(js_all()).group(0)


def _node(js):
    r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20)
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class Hydrate(unittest.TestCase):
    def test_stubs_requested_while_busy_are_filled(self):
        js = ("const HYD_N=1000, HYD_PAD=1e6; let hydBusy=false, hydFailAt=0, hydQ=[], hydNext=null;"
              "const mkey=m=>m.id; const softErr=()=>{}, note=()=>{}, T=s=>s; let calls=0;"
              "const MSGS=[{id:'a',t:1e7,stub:1},{id:'b',t:5e7,stub:1}];"
              "const BUS=[{id:'a',t:1e7,body:'A'},{id:'b',t:5e7,body:'B'}];"
              "function getJSON(u){ calls++; const q=new URLSearchParams(u.split('?')[1]), lo=+q.get('after'), hi=+q.get('before');"
              "return new Promise(r=>setTimeout(()=>r({messages:BUS.filter(x=>x.t>lo&&x.t<hi)}),5)); }"
              + _async_fn("hydrate") +
              "(async()=>{ const p1=hydrate([MSGS[0]]), p2=hydrate([MSGS[1]]);"
              "const n=[await p1, await p2]; process.stdout.write(JSON.stringify({n, calls, b:MSGS.map(m=>m.body||null), s:MSGS.filter(m=>m.stub).length})); })();")
        out = _node(js)
        self.assertEqual(out["b"], ["A", "B"])
        self.assertEqual(out["s"], 0)
        self.assertEqual(out["calls"], 2)
        self.assertEqual(out["n"], [1, 1])

    def test_older_click_reentry_guard(self):
        src = _async_fn("olderClick")
        self.assertIn("if(olderBusy) return;", src)
        self.assertLess(src.index("await hydrate(next)"), src.index("shownN+=SHOW_STEP"))


@unittest.skipUnless(shutil.which("node"), "node not installed")
class KbKey(unittest.TestCase):
    def test_ime_keys_fall_back_to_code(self):
        js = (js_fn("kbKey") + "const c=[['ㄴ','KeyS',0],['Process','KeyS',0],['s','KeyS',0],['1','Digit1',0],"
              "['Process','Digit7',0],['?','Slash',1],['Process','Slash',0],['ㅁ','KeyA',0]];"
              "process.stdout.write(JSON.stringify(c.map(([key,code,sh])=>kbKey({key,code,shiftKey:!!sh}))));")
        self.assertEqual(_node(js), ["s", "s", "s", "1", "7", "?", "/", "ㅁ"])


if __name__ == "__main__":
    unittest.main()
