"""Mermaid flowcharts in the source viewer markdown preview (web/js/81e-structure-mermaid.js, 00-core md/mdLinks).
One node run over own fixtures — no server, no DOM."""
import json
import re
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_prelude
from tests._load import js_fn
from tests._node import node_e

FNS = ("codeBlock", "mdLinks", "md", "mmdLabel", "mmdSplit", "mmdChain", "mmdParse", "mmdTw", "mmdBox", "mmdAcyclic", "mmdFixed", "mmdRank",
       "mmdPav", "mmdOrder", "mmdLayers", "mmdPlace", "mmdAnc", "mmdRoute", "mmdSegRect", "mmdSpread", "mmdUncross", "mmdRouteAll", "mmdPathD", "mmdNum",
       "mmdLabels", "mmdQuality", "mmdLayout", "mmdPoly", "mmdTip", "mmdFlPlace", "mmdSvg", "mmdLegend", "mmdSeqParse", "mmdSeqLayout", "mmdSeqSvg", "mmdBlock")
# The grid router (81g0) runs whole: its RR_* constants and relRRB buffer are top-level statements, not functions.
ROUTER = open(__import__("os").path.join(__import__("os").path.dirname(__file__), "..", "web", "js", "81g0-structure-grid-router.js")).read()

PRE = (r"""const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
const NL = String.fromCharCode(10);
const inline = s => esc(s).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
function hl(s){ return esc(s); }
""") + i18n_prelude("'ko'", ("T", "U"))

FLOW = """%% a comment
graph LR
  subgraph outer["Outer <b>box</b>"]
    direction TB
    a1["first<br/>line two"] --> a2(round) --> a3{choice}
    subgraph inner [Inner]
      i1[[sub]] -.-> i2[(db)]
    end
  end
  a3 -- "yes" --> b1((circle))
  a3 -->|no| b2>flag] & b3{{hex}}
  b1 == thick ==> c1([stadium]); b2 --- c1
  b3 -.dotted.-> c1
  outer -. "to box" .-> c1
  classDef x fill:#fff;
  class a1 x
  style a2 fill:#f00
  linkStyle 0 stroke:#f00
  click a1 callback
"""
BIG = "flowchart TD\n" + "\n".join("  r --> n%d[node number %d]\n  n%d --> m%d" % (i, i, i, i % 3) for i in range(9))
XSS = 'flowchart TD\n  x["<script>alert(1)</script>ok"] --> y["&lt;img src=x onerror=alert(1)&gt;"]\n  y -->|"<i>q</i>"| z'
NEST = """flowchart LR
  subgraph A["Outer A"]
    subgraph A1["Inner A1"]
      a1[alpha one] --> a2[alpha two]
    end
    a3[alpha three]
  end
  subgraph B["Outer B"]
    direction TB
    b1[beta one] --> b2[beta two]
    subgraph B1[Inner B1]
      b3[beta three]
    end
  end
  hub[hub node]
  a1 -->|first label| hub
  a2 -->|second label| b1
  a3 --> b3
  b2 -->|third| hub
  hub --> a3
  hub -->|back to b| b3
  x[lonely] --> b2
  a2 --> hub
  A1 -.-> B1
"""
# docs/ARCHITECTURE.md diagram #1 (copied: tests never read live files) — the crossing count is pinned below.
ARCH = """flowchart LR
  subgraph SES["Sessions"]
    CC["Claude Code sessions + subagents"]
    EXT["Other AI CLIs (19 platform keys)"]
  end
  subgraph DISK["Files they leave"]
    TR[("~/.claude/projects/*/*.jsonl transcripts")]
    GIT[("git repos and worktrees")]
  end
  subgraph MBX["Mailbox (~/.mailbox-mcp)"]
    BUS[("bus.jsonl")]
    ACK[("acks.jsonl")]
    ID[("identity.json")]
  end
  subgraph HK["Hooks (in each session)"]
    STOP["mailbox_stop.py (Stop)"]
    PEER["file_peers_notice.py (PreToolUse)"]
    INV["invite_notice.py · room_auto.py"]
  end
  subgraph SRV["Sidereus server 127.0.0.1:8799 (launchd)"]
    CORE["chat_server.py + sidereus/*.py"]
  end
  QAPI["quota API (optional)"]
  PAGE["Browser page (web/)"]
  MMCP["mailbox MCP (separate package)"]
  AMCP["mcp/sidereus_mcp.py"]

  CC --> TR
  CC -->|"OTel POST /v1/logs"| CORE
  EXT -->|"POST /api/hook"| CORE
  TR --> CORE
  GIT --> CORE
  QAPI --> CORE
  BUS --> CORE
  ACK --> CORE
  ID --> CORE
  CORE -->|"GET /api/state (2.5 s)"| PAGE
  PAGE -->|"POST /api/dm, /api/term/focus"| CORE
  CORE -->|"append DM / relay"| BUS
  MMCP --> BUS
  BUS --> STOP
  ID --> INV
  INV --> CC
  STOP -->|"hooked receipt"| ACK
  STOP --> CC
  PEER -->|"GET /api/agent/file"| CORE
  AMCP -->|"GET /api/agent/*"| CORE
  CC --> AMCP

"""
SHAPES = "\n  s[start] --> d{is it ok}\n  d -->|yes| h{{hex step}}\n  d -->|no| x[retry]\n  d --> y[other]\n  h --> z[end]\n  x --> h\n  h --> w[side]\n"
MD = ("# T\n\n```mermaid\nsequenceDiagram\n  A->>B: hi\n```\n\n```mermaid\nflowchart TD\n  A --> B\n```\n\n"
      "```mermaid\nflowchart TD\n  A --> \n```\n\nafter [`../H.md`](../H.md) and `[k](x.md)` and [a `b` c](d.md)\n")


def run(body):
    src = PRE + "const MMD_BUDGET = 1e9, MMD_UNCROSS = 1e9;\n" + ROUTER + "\n" + "\n".join(js_fn(f) for f in FNS) + "\nconst R = {};\n" + body + "\nprocess.stdout.write(JSON.stringify(R));"
    r = subprocess.run(node_e(src), capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


def overlap(a, b):
    return a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"] and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"]


def inside(a, b):
    return b["x"] <= a["x"] and b["y"] <= a["y"] and a["x"] + a["w"] <= b["x"] + b["w"] and a["y"] + a["h"] <= b["y"] + b["h"]


@unittest.skipUnless(shutil.which("node"), "node not installed")
class Mermaid(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.R = run(r"""
const F = %s, B = %s, X = %s, M = %s, N = %s, ARCH = %s, SHAPES = %s;
R.ng = mmdParse(N); R.nL = mmdLayout(R.ng); R.nq = mmdQuality(R.ng, R.nL); R.fq = (g => mmdQuality(g, mmdLayout(g)))(mmdParse(F));
R.ord = (() => { const L = [["a", "b"], ["c", "d"]], up = { a: [], b: [], c: [["b", 1]], d: [["a", 1]] }, dn = { a: [["d", 1]], b: [["c", 1]], c: [], d: [] };
  return [mmdOrder(L, up, dn), L]; })();
R.pav = mmdPav([3, 1, 2, 5], [1, 1, 1, 1]);
R.fb = (() => { const g = { nodes: { a: { label: "a", sg: "" }, b: { label: "b", sg: "" } }, sgs: {} };
  const L = { nodes: { a: { x: 0, y: 0, w: 40, h: 20 }, b: { x: 100, y: 0, w: 40, h: 20 } }, sgs: {},
    edges: [{ from: "a", to: "b", label: "a <script>long</script> label that cannot fit", pts: [[40, 10], [100, 10]] }] };
  mmdLabels(g, L); return { e: L.edges[0], notes: L.notes, q: mmdQuality(g, L), leg: mmdLegend(g, L) }; })();
R.g = mmdParse(F); R.L = mmdLayout(R.g);
R.big = mmdLayout(mmdParse(B)); R.bigg = mmdParse(B);
R.types = ['sequenceDiagram\n A->>B: x', 'classDiagram\n A <|-- B', 'erDiagram\n A ||--o{ B : x', 'gantt\n title x', 'pie\n "a": 1']
  .map(s => mmdParse(s));
R.bad = ['flowchart TD\n A --> ', 'flowchart TD\n subgraph s\n A', 'flowchart TD\n end', 'flowchart TD\n A -- B']
  .map(s => { try { mmdParse(s); return 'parsed'; } catch(e){ return 'threw'; } });
R.dirs = ['graph TD', 'graph BT', 'flowchart RL', 'graph'].map(h => mmdParse(h + '\n A --> B').dir);
R.xss = mmdBlock(X);
R.md = md(M, 1);
R.chain = mmdParse('flowchart LR\n A --> B --> C & D\n E --x F\n G <--> H\n I ~~~ J').edges.map(e => [e.from, e.to, e.style, e.head, e.both]);
R.arch = (g => mmdQuality(g, mmdLayout(g)))(mmdParse(ARCH));
R.pin = [F, ARCH].map(s => (g => mmdSvg(g, mmdLayout(g), 't'))(mmdParse(s)));
R.fix = ['TD', 'LR'].map(d => { const g = mmdParse('flowchart ' + d + '\n a --> b\n b --> c\n c --> a\n e --> b\n a --> d');
  g.rankFix = { a: 2, b: 0, c: 1, d: 3, e: 0 }; return { fix: g.rankFix, nodes: mmdLayout(g).nodes }; });
R.part = (() => { const g = mmdParse(F); g.rankFix = { [g.nlist[0]]: 5 }; return mmdSvg(g, mmdLayout(g), 't'); })();
R.tag = (g => mmdSvg(g, mmdLayout(g), 't', true))(mmdParse('flowchart LR\n a -->|x| b'));
R.sgtip = (() => { const g = mmdParse('flowchart LR\n subgraph s1 [A]\n a --> b\n end\n subgraph s2 [B]\n c\n end'), L = mmdLayout(g);
  const s0 = mmdSvg(g, L, 't', true); g.sgs.s1.tip = 'x <b>&"y'; g.sgs.s2.tip = 'z'; g.sgs.s2.box3d = true;
  return { s0, s1: mmdSvg(g, L, 't', true), plain: mmdSvg(g, L, 't') }; })();
R.tips = ['flowchart TD', 'flowchart LR'].map(h => { const g = mmdParse(h + SHAPES), L = mmdLayout(g);
  return { shape: Object.fromEntries(g.nlist.map(k => [k, g.nodes[k].shape])), nodes: L.nodes, edges: L.edges.map(e => [e.from, e.to]), svg: mmdSvg(g, L, 't') }; });
""" % (json.dumps(FLOW), json.dumps(BIG), json.dumps(XSS), json.dumps(MD), json.dumps(NEST), json.dumps(ARCH), json.dumps(SHAPES)))

    def test_parse_constructs(self):
        g = self.R["g"]
        self.assertEqual(g["dir"], "LR")
        n = g["nodes"]
        self.assertEqual({k: n[k]["shape"] for k in n}, {"a1": "rect", "a2": "round", "a3": "diamond", "i1": "sub", "i2": "cyl",
                                                        "b1": "circle", "b2": "flag", "b3": "hex", "c1": "stadium"})
        self.assertEqual(n["a1"]["label"], "first\nline two")
        self.assertEqual(g["sgs"]["outer"]["title"], "Outer box")
        self.assertEqual(g["sgs"]["outer"]["dir"], "TB")
        self.assertEqual(g["sgs"]["inner"]["parent"], "outer")
        self.assertEqual([n[k]["sg"] for k in ("a1", "i1", "b1")], ["outer", "inner", ""])
        es = {(e["from"], e["to"]): (e["label"], e["style"], e["head"]) for e in g["edges"]}
        self.assertEqual(es[("a1", "a2")], ("", "solid", True))
        self.assertEqual(es[("i1", "i2")], ("", "dot", True))
        self.assertEqual(es[("a3", "b1")], ("yes", "solid", True))
        self.assertEqual(es[("a3", "b2")], ("no", "solid", True))
        self.assertEqual(es[("a3", "b3")], ("no", "solid", True))       # & fans out
        self.assertEqual(es[("b1", "c1")], ("thick", "thick", True))
        self.assertEqual(es[("b2", "c1")], ("", "solid", False))
        self.assertEqual(es[("b3", "c1")], ("dotted", "dot", True))
        self.assertEqual(es[("outer", "c1")], ("to box", "dot", True))  # subgraph id as an edge end
        self.assertNotIn("outer", n)
        self.assertEqual(len(g["edges"]), 10)                            # classDef/class/style/linkStyle/click ignored

    def test_chain_and_edge_kinds(self):
        self.assertEqual(self.R["chain"], [["A", "B", "solid", True, False], ["B", "C", "solid", True, False],
                                           ["B", "D", "solid", True, False], ["E", "F", "solid", True, False],
                                           ["G", "H", "solid", True, True], ["I", "J", "invis", False, False]])
        self.assertEqual(self.R["dirs"], ["TB", "BT", "RL", "TB"])

    def test_layout_no_overlap(self):
        for L in (self.R["L"], self.R["big"]):
            rs = list(L["nodes"].values())
            for i, a in enumerate(rs):
                for b in rs[i + 1:]:
                    self.assertFalse(overlap(a, b), (a, b))
                self.assertTrue(a["x"] >= 0 and a["y"] >= 0 and a["x"] + a["w"] <= L["w"] and a["y"] + a["h"] <= L["h"])
        L, g = self.R["L"], self.R["g"]
        for k, n in g["nodes"].items():                                  # members sit in their box, others outside it
            for s in L["sgs"]:
                anc, p = set(), n["sg"]
                while p:
                    anc.add(p)
                    p = g["sgs"][p]["parent"]
                if s in anc:
                    self.assertTrue(inside(L["nodes"][k], L["sgs"][s]), (k, s))
                else:
                    self.assertFalse(overlap(L["nodes"][k], L["sgs"][s]), (k, s))
        self.assertTrue(inside(L["sgs"]["inner"], L["sgs"]["outer"]))
        self.assertEqual(len(L["edges"]), 10)

    def test_layers_follow_edges(self):
        L = self.R["big"]
        for e in self.R["bigg"]["edges"]:                                # TD: every edge goes down
            self.assertLess(L["nodes"][e["from"]]["y"] + L["nodes"][e["from"]]["h"], L["nodes"][e["to"]]["y"] + 1)

    def test_unsupported_and_errors(self):
        self.assertEqual([t["ok"] for t in self.R["types"]], [False] * 5)
        self.assertEqual(self.R["types"][0]["type"], "sequenceDiagram")
        self.assertEqual(self.R["bad"], ["threw"] * 4)
        h = self.R["md"]
        self.assertEqual(h.count("<div class=mmdno><div class=mmdnote>미리보기 미지원 형식</div><pre class=cb>"), 1)   # sequenceDiagram now drawn (81h)
        self.assertEqual(h.count("<div class=mmd>"), 2)
        self.assertIn("<svg class=mmdsvg", h)
        self.assertIn('<button type=button class=mmdtg aria-pressed=false>원문</button>', h)
        self.assertIn("<div class=mmdsrc><pre class=cb><span class=cl>mermaid</span>", h)
        self.assertIn("sequenceDiagram", h)
        self.assertTrue(h.endswith("</p>"))                              # the rest still renders after a bad block

    def test_labels_escaped(self):
        h = self.R["xss"]
        self.assertIn("<svg", h)
        for bad in ("<script", "<img", "<i>", "onerror=alert(1)>"):
            self.assertNotIn(bad, h.split("<div class=mmdsrc>")[0])
        self.assertIn(">alert(1)ok</tspan>", h)                          # tags dropped, text kept
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", h)          # entities decoded then esc()'d again
        self.assertIn(">q</tspan>", h)

    def test_routes_clear_boxes_and_labels(self):
        for q in (self.R["nq"], self.R["fq"]):                           # nested subgraphs + a hub: nothing through a box
            self.assertEqual((q["boxHits"], q["labelOverlaps"]), (0, 0), q)
        L = self.R["nL"]
        for e in L["edges"]:
            p = e["pts"]
            for a, b in zip(p, p[1:]):                                   # orthogonal runs only
                self.assertTrue(abs(a[0] - b[0]) < 0.6 or abs(a[1] - b[1]) < 0.6, e)
            for end, k in ((p[0], e["from"]), (p[-1], e["to"])):         # ends sit on their own box edge
                r = L["nodes"].get(k) or L["sgs"][k]
                on = (abs(end[0] - r["x"]) < 0.6 or abs(end[0] - r["x"] - r["w"]) < 0.6 or abs(end[1] - r["y"]) < 0.6
                      or abs(end[1] - r["y"] - r["h"]) < 0.6)
                self.assertTrue(on, (e["from"], e["to"], end, r))
        labelled = [e for e in L["edges"] if e["label"]]
        self.assertEqual(len(labelled), 4)
        self.assertTrue(all(e.get("lr") for e in labelled))
        self.assertEqual(len(L["notes"]), sum(1 for e in labelled if e.get("num")))

    def test_diamond_ports_not_shared(self):
        # ★2026-09-29 a2->a3 and a3->b2 ran 40px on one line off the diamond's top vertex (mmdSpread skipped 2-point routes).
        L, g = self.R["L"], self.R["g"]
        runs = []
        for k, e in enumerate(L["edges"]):
            p = e["pts"]
            for end, s in ((e["from"], (p[0], p[1])), (e["to"], (p[-1], p[-2]))):
                if g["nodes"].get(end, {}).get("shape") == "diamond":
                    runs.append((k, s))
        self.assertGreaterEqual(len(runs), 4)
        for x, (k, (a, b)) in enumerate(runs):
            for j, (c, d) in runs[x + 1:]:
                if j == k:
                    continue
                for ax in (0, 1):                                        # collinear on axis ax, overlapping along the other
                    o = 1 - ax
                    if max(abs(a[ax] - b[ax]), abs(c[ax] - d[ax]), abs(a[ax] - c[ax])) < 0.6:
                        ov = min(max(a[o], b[o]), max(c[o], d[o])) - max(min(a[o], b[o]), min(c[o], d[o]))
                        self.assertLess(ov, 1, (L["edges"][k]["from"], L["edges"][k]["to"], L["edges"][j]["from"], L["edges"][j]["to"], ov))

    def test_architecture_crossings(self):
        q = self.R["arch"]                                               # ★2026-09-29 32 -> 15 (source side exits + mmdUncross)
        self.assertEqual((q["boxHits"], q["labelOverlaps"], q["numbered"]), (0, 0, 0), q)
        self.assertLessEqual(q["crossings"], 15, q)

    def test_ends_on_shape_outline(self):
        def poly(s, r):
            x, y, w, h = r["x"], r["y"], r["w"], r["h"]
            if s == "diamond":
                return [(x + w / 2, y), (x + w, y + h / 2), (x + w / 2, y + h), (x, y + h / 2)]
            return [(x + 14, y), (x + w - 14, y), (x + w, y + h / 2), (x + w - 14, y + h), (x + 14, y + h), (x, y + h / 2)]

        def dist(p, a, b):
            dx, dy = b[0] - a[0], b[1] - a[1]
            t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
            return ((p[0] - a[0] - t * dx) ** 2 + (p[1] - a[1] - t * dy) ** 2) ** 0.5
        for T in self.R["tips"]:
            ds = re.findall(r'<path class="mmde[^"]*" d="([^"]+)"', T["svg"])
            self.assertEqual(len(ds), len(T["edges"]))
            n = 0
            for (a, b), d in zip(T["edges"], ds):
                xy = [tuple(map(float, v.split(","))) for v in re.findall(r"-?[\d.]+,-?[\d.]+", d)]
                for k, p in ((a, xy[0]), (b, xy[-1])):
                    if T["shape"][k] not in ("diamond", "hex"):
                        continue
                    P = poly(T["shape"][k], T["nodes"][k])
                    self.assertLess(min(dist(p, P[i], P[(i + 1) % len(P)]) for i in range(len(P))), 0.6, (a, b, k, p))
                    n += 1
            self.assertGreaterEqual(n, 7)                                # every d / h end checked (4 at d, 4 at h)

    def test_rank_fix(self):
        # every item ranked: layers follow the given ranks (back and same-rank edges included), not the longest path
        for ax, f in zip(("y", "x"), self.R["fix"]):
            n, fix = f["nodes"], f["fix"]
            mid = {k: n[k][ax] + n[k]["h" if ax == "y" else "w"] / 2 for k in fix}
            for a in fix:
                for b in fix:
                    if fix[a] < fix[b]:
                        self.assertLess(mid[a], mid[b], (ax, a, b))
                    elif fix[a] == fix[b]:
                        self.assertAlmostEqual(mid[a], mid[b], 3, msg=(ax, a, b))
        self.assertEqual(self.R["part"], self.R["pin"][0])               # a partial map is ignored: output unchanged

    def test_order_and_fit(self):
        n, L = self.R["ord"]
        self.assertEqual(n, 0)                                           # one transpose/sweep uncrosses a->d, b->c
        self.assertEqual(L[0].index("a") < L[0].index("b"), L[1].index("d") < L[1].index("c"))
        self.assertEqual(self.R["pav"], [2, 2, 2, 5])                    # non-decreasing least-squares fit

    def test_label_fallback_numbered(self):
        fb = self.R["fb"]
        self.assertEqual(fb["e"]["num"], "①")                       # no room on a 60px run: badge, not an overlap
        self.assertEqual(fb["q"]["labelOverlaps"], 0)
        self.assertEqual(len(fb["notes"]), 1)
        self.assertIn("<ol class=mmdleg><li><b>①</b> a &lt;script&gt;long&lt;/script&gt; label", fb["leg"])
        self.assertNotIn("<script", fb["leg"])

    def test_svg_untagged_pinned(self):
        # sha256 taken before 84i's opt-in tag arg: without it mmdSvg output stays byte-identical; md never gets the hooks
        import hashlib
        h = [hashlib.sha256(s.encode()).hexdigest() for s in self.R["pin"]]
        self.assertEqual(h, ["14cde5b0dda801fe589c9ca9a4d43c5b01e9252b90d4b7cdba8dbdb991f73fd4",
                             "145a199fb635df0dc6632e09c854ecf18d91e63cfc03e1c548046c9d7ff4ff7c"])   # re-pinned: diagram labels renamed
        for s in (self.R["md"], self.R["xss"]):
            self.assertNotIn("mmdfe", s)
            self.assertNotIn("data-c", s)

    def test_tag_edge_ends(self):
        # tag mode: every edge group names its ends by node key (84j hover reads them); untagged stays pinned above
        h = self.R["tag"]
        self.assertGreaterEqual(h.count('class=mmdfe data-c="" data-f="a" data-t="b">'), 2)   # line + label
        self.assertIn('data-p="a"', h)

    def test_tag_edge_hit_path(self):
        # tag mode: each line group starts with a transparent .mmdhit copy of the same d (84j edge click); untagged has none
        h = self.R["tag"]
        m = re.search(r'class=mmdfe data-c="" data-f="a" data-t="b"><path class=mmdhit d="([^"]+)"/><path class="mmde e-solid" d="([^"]+)"', h)
        self.assertIsNotNone(m, h)
        self.assertEqual(m.group(1), m.group(2))
        self.assertEqual(h.count("mmdhit"), 1)                          # line group only, not the label group
        for s in self.R["pin"]:
            self.assertNotIn("mmdhit", s)

    def test_subgraph_tip_title(self):
        # S.tip -> escaped <title> as the first child of the subgraph <g> (plain and box3d); no tip -> no <title>
        r = self.R["sgtip"]
        self.assertNotIn("<title>", r["s0"])
        self.assertIn('<g class=mmdsg><title>x &lt;b&gt;&amp;&quot;y</title><rect', r["s1"])
        self.assertRegex(r["s1"], r'<g class="mmdsg mmdsg3 [^"]*" data-s="s2"><title>z</title><polygon')
        self.assertNotIn("<b>", r["s1"])

    def test_link_text_with_code(self):
        h = self.R["md"]
        self.assertIn('<a class=mdrel data-mdrel="../H.md"><code>../H.md</code></a>', h)
        self.assertIn("<code>[k](x.md)</code>", h)                       # a link inside code stays code
        self.assertIn('<a class=mdrel data-mdrel="d.md">a <code>b</code> c</a>', h)


if __name__ == "__main__":
    unittest.main()
