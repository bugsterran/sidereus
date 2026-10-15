"""Mermaid sequenceDiagram in the markdown preview (web/js/81h-structure-mermaid-seq.js via 81e mmdBlock).
Fixtures are the docs/ARCHITECTURE.md diagrams copied inline; one node run — no server, no DOM."""
import json
import shutil
import subprocess
import unittest

from tests._load import js_fn
from tests._node import node_e

FNS = ("codeBlock", "mmdLabel", "mmdSplit", "mmdChain", "mmdParse", "mmdTw", "mmdBox", "mmdSeqParse", "mmdSeqLayout", "mmdSeqSvg", "mmdBlock")
PRE = r"""const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
function hl(s){ return esc(s); } function T(s){ return s; }
"""
POLL = """sequenceDiagram
  participant P as Page (95-poll.js)
  participant H as Handler
  participant S as state.py
  participant D as Domain modules
  P->>H: GET /api/state?since=<ns>
  H->>S: _state_body(since, nc)
  alt cached < 1 s
    S-->>H: cached body (+ gzip)
  else rebuild
    S->>D: quota · sessions · cards · usage · health (no lock)
    S->>D: presence · acks · messages · cursors · rooms (short _lock)
    S->>D: attention · review · saver · … (_piece each)
    D-->>S: pieces
    S-->>H: JSON + build fingerprint
  end
  H-->>P: 200 (gzip if accepted)
  Note over P: PAGE_BUILD differs → «refresh» banner
"""
FOCUS = """sequenceDiagram
  actor U as Human
  participant P as Page (88d-term.js)
  participant A as routes_post._p_term_focus
  participant T as term.py
  participant O as osascript
  U->>P: «터미널» button
  P->>A: POST /api/term/focus {sid}
  A->>A: sid regex check; tty/app from server rows only
  A->>T: term_focus(sid, rows)
  T->>O: fixed script, tty as argv item 1
  O-->>T: ok / notrunning
  T-->>P: {how:"focused"} or {cmd:"claude --resume <sid>"}
  Note over P: not focused → copy cmd
"""
RELAY = """sequenceDiagram
  actor U as Human
  participant W as Board / review drawer
  participant A as Sidereus (bus.dm_send)
  participant B as bus.jsonl
  participant K as mailbox_stop.py
  participant S as Session
  participant C as acks.jsonl
  U->>W: «전달 ▾» → preview → confirm
  W->>A: POST /api/dm {to, body, relay:true, sid}
  A->>A: to ∈ identity.json values, body ≤ DM_MAX
  A->>B: append {kind:"relay", idSrc:"viewer", sid}
  Note over W: card «보냄»
  S->>K: turn ends (Stop)
  K->>B: read tail, relays for this id (≤ 3, 24 h floor)
  K-->>S: block stop once, body in reason
  K->>C: {kind:"hooked"} + relay_t cursor
  Note over W: card «전달됨»
  S->>C: ack
  Note over W: card «읽음»
"""
MISC = """sequenceDiagram
  autonumber
  %% comment
  participant A
  box Grey
  participant B as <b>Bee</b>
  end
  activate A
  A-xB: cross
  B--xA: dashed cross
  A->B: open line
  B-->A: dashed open
  A-)B: async
  A->>+B: act
  loop every 2 s
    opt maybe
      Note left of A: left
      Note right of B: right
    end
  end
  par one
    A->>B: x
  and two
    B->>A: y
  end
  Note over A,B: spans both
  deactivate A
  this line is unknown
  C->>C: self <script>
  critical unclosed
"""

# docs/ARCHITECTURE.md §4 (a)-(c), copied inline: tests never read repo docs.
DOC = [POLL, RELAY, FOCUS]


def run(body):
    src = PRE + "\n".join(js_fn(f) for f in FNS) + "\nconst R = {};\n" + body + "\nprocess.stdout.write(JSON.stringify(R));"
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class MermaidSeq(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run(r"""
const S = [%s, %s, %s];
R.g = S.map(s => mmdSeqParse(s));
R.L = R.g.map(g => mmdSeqLayout(g));
R.h = S.map(s => mmdBlock(s));
R.flow = mmdSeqParse('flowchart TD\n A --> B');
R.empty = mmdSeqParse('sequenceDiagram\n autonumber');
R.doc = %s.map(s => { const g = mmdSeqParse(s); return { n: g.parts.length, m: g.items.filter(i => i.k === 'msg').length, h: mmdBlock(s) }; });
""" % (json.dumps(POLL), json.dumps(FOCUS), json.dumps(MISC), json.dumps(DOC)))

    def kinds(self, g, k):
        return [i for i in g["items"] if i["k"] == k]

    def test_architecture_diagrams(self):
        (p, f) = self.R["g"][:2]
        self.assertEqual([x["label"] for x in p["parts"]], ["Page (95-poll.js)", "Handler", "state.py", "Domain modules"])
        self.assertEqual(len(self.kinds(p, "msg")), 9)
        self.assertEqual([(i["kind"], i["label"]) for i in self.kinds(p, "open")], [("alt", "cached < 1 s")])
        self.assertEqual([i["label"] for i in self.kinds(p, "sect")], ["rebuild"])
        self.assertEqual(len(self.kinds(p, "note")), 1)
        self.assertEqual(len(f["parts"]), 5)
        self.assertTrue(f["parts"][0]["actor"])
        self.assertEqual(len(self.kinds(f, "msg")), 7)
        self.assertEqual(self.kinds(f, "msg")[2]["label"], "sid regex check; tty/app from server rows only")   # ';' stays in the label
        for h in self.R["h"]:
            self.assertNotIn("미지원", h)
            self.assertIn('<svg class="mmdsvg mmdseq"', h)
        self.assertIn("GET /api/state?since=&lt;ns&gt;</tspan>", self.R["h"][0])      # non-formatting tags stay as text
        self.assertIn("--resume &lt;sid&gt;", self.R["h"][1].split("<div class=mmdsrc>")[0])

    def test_docs_file(self):
        self.assertGreaterEqual(len(self.R["doc"]), 2)
        for d in self.R["doc"]:
            self.assertGreaterEqual(d["n"], 2)
            self.assertGreaterEqual(d["m"], 1)
            self.assertNotIn("미지원", d["h"])

    def test_layout(self):
        for g, L in zip(self.R["g"], self.R["L"]):
            cx = L["cx"]
            self.assertEqual(cx, sorted(cx))
            for i in range(len(cx) - 1):                          # boxes never touch
                self.assertGreater(cx[i + 1] - cx[i], (L["bx"][i]["w"] + L["bx"][i + 1]["w"]) / 2)
            ys = [m["pts"][0][1] for m in L["msgs"]]
            self.assertEqual(ys, sorted(ys))                     # top to bottom in source order
            self.assertGreater(L["bot"], ys[-1])
        fr = self.R["L"][0]["frames"][0]
        self.assertLess(fr["y"], self.R["L"][0]["msgs"][2]["pts"][0][1])
        self.assertGreater(fr["y"] + fr["h"], self.R["L"][0]["msgs"][6]["pts"][0][1])

    def test_misc_constructs(self):
        g, L, h = self.R["g"][2], self.R["L"][2], self.R["h"][2]
        self.assertEqual([x["id"] for x in g["parts"]], ["A", "B", "C"])
        self.assertEqual(g["parts"][1]["label"], "Bee")
        ms = self.kinds(g, "msg")
        self.assertEqual([(m["head"], m["dash"]) for m in ms[:5]], [("cross", False), ("cross", True), ("none", False), ("none", True), ("open", False)])
        self.assertEqual([m["n"] for m in ms], list(range(1, 10)))
        self.assertEqual(ms[5]["b"], "B")                         # activation marker stripped
        self.assertEqual([i["kind"] for i in self.kinds(g, "open")], ["loop", "opt", "par", "critical"])
        self.assertEqual(len(self.kinds(g, "close")), 4)          # unclosed critical closes quietly
        self.assertEqual([n["pos"] for n in self.kinds(g, "note")], ["left", "right", "over"])
        self.assertTrue(L["msgs"][-1]["self"])
        self.assertEqual(len(L["msgs"][-1]["pts"]), 4)
        self.assertNotIn("<script", h)
        self.assertIn("self &lt;script&gt;", h)
        self.assertIn('marker-end="url(#mmds', h)
        self.assertEqual(h.count("x)\"/>"), 2)                      # both -x arrows use the cross marker
        self.assertIn("class=mmdsqn", h)
        self.assertEqual(self.R["flow"]["ok"], False)
        self.assertEqual(self.R["empty"], {"ok": False, "type": "empty"})


if __name__ == "__main__":
    unittest.main()
