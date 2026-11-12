"""R3: linked pi children hang under their pi parent's head row; concurrent children get separate rows."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

PI_SID = "pi-par-1"
CWD = "/w/p"


def _sess(sid, plat, start, end):
    return {"kind": "sess", "sid": sid, "plat": plat, "cwd": CWD, "proj": "p", "type": "",
            "segs": [[start, end]], "start": start, "end": end, "state": "wait"}


def _child(n, start, end, typ="scout"):
    # same shape as sidereus/timeline_ext.py _ext_child (agent-kind row, no `kind`, `par` empty, `parent` = pi sid)
    return {"tid": "ext:pi|kid-" + str(n), "type": typ, "aid": "", "par": "", "desc": typ,
            "segs": [[start, end]], "start": start, "end": end, "run": False, "state": "done",
            "done": True, "proj": "p", "cwd": CWD, "depth": 1, "plat": "pi", "model": "",
            "parent": PI_SID, "fin": 1}


def _run(rows):
    js = "\n".join(["let SESS = [];", js_fn("tlLiveOf"), js_fn("tlGroups"), js_fn("tlSessions"),
                    "const r = tlSessions(tlGroups(" + json.dumps(rows) + "), 0, 100);"
                    "console.log(JSON.stringify(r.sessOrder.map(v => ({plat: v.plat, cwd: v.cwd,"
                    " head: v.head ? v.head.items.map(x => x.sid) : null,"
                    " kids: v.kids.map(k => ({tids: k.items.map(x => x.tid), par: k._par || 0}))}))));"])
    p = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if p.returncode != 0:
        raise AssertionError(p.stderr)
    return json.loads(p.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PiChildrenUnderPiHead(unittest.TestCase):
    def test_r3_one_head_bucket_per_pi_parent_with_its_children(self):
        o = _run([_sess(PI_SID, "pi", 1, 50), _child(1, 5, 10), _child(2, 20, 30)])
        self.assertEqual(len(o), 1)
        self.assertEqual((o[0]["plat"], o[0]["cwd"], o[0]["head"]), ("pi", CWD, [PI_SID]))
        tids = [t for k in o[0]["kids"] for t in k["tids"]]
        self.assertEqual(sorted(tids), ["ext:pi|kid-1", "ext:pi|kid-2"])

    def test_r3_no_separate_head_for_a_child(self):
        # a Claude session in the same folder must not receive the pi children, and no headless bucket appears
        o = _run([_sess("cc-1", "", 1, 50), _sess(PI_SID, "pi", 1, 50), _child(1, 5, 10)])
        self.assertEqual(len(o), 2)
        self.assertTrue(all(v["head"] for v in o))
        by = {v["plat"]: v for v in o}
        self.assertEqual(by[""]["kids"], [])
        self.assertEqual(by["pi"]["kids"][0]["tids"], ["ext:pi|kid-1"])

    def test_r3_overlapping_children_on_separate_rows(self):
        o = _run([_sess(PI_SID, "pi", 1, 50), _child(1, 5, 20), _child(2, 10, 30)])
        self.assertEqual(len(o), 1)
        kids = o[0]["kids"]
        self.assertEqual(len(kids), 2)
        self.assertEqual([k["par"] for k in kids], [2, 2])
        self.assertEqual(sorted(t for k in kids for t in k["tids"]), ["ext:pi|kid-1", "ext:pi|kid-2"])

    def test_r3_sequential_children_share_one_row(self):
        o = _run([_sess(PI_SID, "pi", 1, 50), _child(1, 5, 10), _child(2, 20, 30)])
        self.assertEqual([(len(k["tids"]), k["par"]) for k in o[0]["kids"]], [(2, 0)])


if __name__ == "__main__":
    unittest.main()
