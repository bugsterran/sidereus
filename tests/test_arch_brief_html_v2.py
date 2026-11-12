"""arch_brief_html_v2 (R1-R5 render): title + what, containment figure (screens band, system container with components,
package row and principles, externals with numbered uses), labelled arrows, role table, scroll box, size and label
overlap on a maximal brief, deterministic bytes, escaping."""
import itertools
import re
import unittest
from unittest import mock

from tests._load import sidereus

H2 = sidereus("arch_brief_html_v2")
AH = sidereus("arch_brief_html")


def comp(i, mods=None):
    return {"id": i, "name": i.title(), "note": "note of " + i, "role": "role of " + i, "modules": mods or [i + "_m"]}


def brief():
    return {"v": 2, "repo": "/r", "commit": "b" * 40, "title": "App", "what": "Answers questions for staff",
            "actors": [{"id": "user", "name": "User"}],
            "screens": [{"id": "web", "name": "Web", "note": "pages", "role": "shows answers", "modules": ["ui"]}],
            "system": {"name": "Api", "components": [
                comp("api"), comp("svc"),
                {"id": "dom", "name": "Domain", "note": "packages", "role": "domain rules",
                 "pkgs": [{"name": "Orders", "modules": ["pa"]}, {"name": "Billing", "note": "bills", "modules": ["pb"]}]}],
                "principles": [{"text": "one store", "evidence": {"file": "app/main.py", "line": 3}},
                               {"text": "calls go through Api", "evidence": {"file": "app/store.py", "line": 10}}]},
            "externals": [{"id": "store", "name": "Store", "role": "keeps rows", "uses": [{"name": "Rows"}], "modules": ["db"]},
                          {"id": "llm", "name": "Llm", "role": "answers", "modules": ["llm"],
                           "uses": [{"name": "Chat"}, {"name": "Embed", "note": "vectors"}, {"name": "Rank"}]}],
            "arrows": [{"from": "web", "to": "api", "label": "HTTP calls", "edges": [0]},
                       {"from": "api", "to": "svc", "label": "jobs", "edges": [1]},
                       {"from": "svc", "to": "store", "label": "rows", "use": 1, "edges": [2]},
                       {"from": "svc", "to": "llm", "label": "prompts", "use": 2, "edges": [3]},
                       {"from": "api", "to": "dom", "label": "orders", "edges": [6]}]}


COMP_ARROWS = 6     # api->svc, api->dom, mail->dom, jobs->dom, search->auth, auth->api


def segments(svg):
    """[(path index, (x1, y1), (x2, y2))] of every drawn arrow path (class edge)."""
    out = []
    for i, d in enumerate(re.findall(r'<path d="([^"]+)" class="edge"', svg)):
        pts = [tuple(int(v) for v in m) for m in re.findall(r"[ML](-?\d+),(-?\d+)", d)]
        out += [(i, q, r) for q, r in zip(pts, pts[1:])]
    return out


def big():
    """Maximal brief: 2 actors, 2 screens, 7 components (one with 6 pkgs), 4 principles, 4 externals x 3 uses, 12 arrows."""
    b = brief()
    b["actors"].append({"id": "admin", "name": "Admin"})
    b["screens"].append({"id": "console", "name": "Console", "note": "admin pages", "role": "settings", "modules": ["cm"]})
    b["system"]["components"] = [comp("api"), comp("svc"), comp("auth"), comp("jobs"), comp("search"), comp("mail"),
                                 {"id": "dom", "name": "Domain", "note": "packages", "role": "domain rules",
                                  "pkgs": [{"name": "Pkg%d" % k, "note": "n%d" % k, "modules": ["p%d" % k]} for k in range(6)]}]
    b["system"]["principles"] = [{"text": "principle number %d holds across the code base" % k,
                                  "evidence": {"file": "app/main.py", "line": k + 1}} for k in range(4)]
    b["externals"] = [{"id": "x%d" % k, "name": "Ext %d" % k, "role": "r", "modules": ["e%d" % k],
                       "uses": [{"name": "Use %d" % u, "note": "what it does"} for u in range(3)]} for k in range(4)]
    pairs = [("web", "api"), ("console", "auth"), ("api", "svc"), ("api", "dom"), ("svc", "x0"), ("svc", "x1"),
             ("jobs", "x2"), ("mail", "dom"), ("jobs", "dom"), ("search", "auth"), ("x1", "jobs"), ("auth", "api")]
    b["arrows"] = [{"from": f, "to": t, "label": "carries data %d" % k, "edges": [k]} for k, (f, t) in enumerate(pairs)]
    b["arrows"][4]["use"] = 3
    return b


class RenderV2Test(unittest.TestCase):
    def test_r1_title_and_what(self):
        h = H2.render(brief())
        self.assertIn("<h1>App</h1>", h)
        self.assertIn('<p class="lead">Answers questions for staff<small>commit bbbbbbb</small></p>', h)

    def test_r2_container_components_pkg_row_and_numbered_uses(self):
        h = H2.render(brief())
        sysg = h.index("data-system=")
        for i in ("api", "svc", "dom"):
            self.assertGreater(h.index('data-box="%s" data-kind="component"' % i), sysg)
        self.assertEqual(re.findall(r'<g data-pkg="(\d)">', h), ["1", "2"])
        self.assertIn('stroke-dasharray="6 4"', h)
        self.assertEqual(re.findall(r'data-use="\d"><text[^>]*>([①②③]) (\w+)</text>', h),
                         [("①", "Rows"), ("①", "Chat"), ("②", "Embed"), ("③", "Rank")])
        self.assertNotIn("vectors", h[:h.index("</svg>")])   # use notes live in the legend, not the figure

    def test_r3_every_arrow_has_label(self):
        h = H2.render(big())
        gs = re.findall(r'<g data-arrow="[^"]*"[^>]*>.*?</g>', h)
        self.assertEqual(len(gs), COMP_ARROWS)
        for g in gs:
            self.assertRegex(g, r'class="t-edge"[^>]*>carries data \d+</text>')

    def test_r4_principles_show_file_line(self):
        h = H2.render(brief())
        # R4: basename:line on screen, the full path in the tooltip
        self.assertIn('· one store<tspan class="t-ev" dx="10"><title>app/main.py:3</title>main.py:3</tspan>', h)
        self.assertIn("<title>app/store.py:10</title>store.py:10</tspan>", h)

    def test_r5_legend_one_row_per_box_and_scroll_box(self):
        h = H2.render(big())
        leg = h[h.index('<table class="legend">'):]
        # R5: one table, exactly one row per screen/component/external, in figure order
        self.assertEqual(h.count("<table"), 1)
        self.assertEqual(len(re.findall(r"<tr\b", leg)), 2 + 7 + 4)
        self.assertEqual(re.findall(r'<tr data-box="(\w+)"', leg),
                         ["web", "console", "api", "svc", "auth", "jobs", "search", "mail", "dom", "x0", "x1", "x2", "x3"])
        self.assertIn('<td>role of api<span class="nt"> · note of api</span></td>', leg)
        for note in ["pages", "admin pages"] + ["note of %s" % i for i in ("svc", "auth", "jobs", "search", "mail")]:
            self.assertIn(" · %s<" % note, leg)   # R5: every note left the figure for the legend
        for k in range(6):
            self.assertIn("<li>Pkg%d — n%d</li>" % (k, k), leg)
        # R5: a use's number, name and note share one line element, so they cannot misalign
        self.assertEqual(leg.count("<li>② Use 1 — what it does</li><li>③ Use 2 — what it does</li>"), 3)
        self.assertIn("<li>③ Use 2 — what it does · ← Svc</li>", leg)
        self.assertIn("td.nm { font-weight: 600; width: 200px; white-space: nowrap; }", H2.CSS)
        self.assertIn("min-width: 900px", H2.CSS)
        self.assertIn(".fig { border: 1px solid var(--line); border-radius: 12px; overflow-x: auto; }", H2.CSS)
        for bad in ("route", "sequence"):
            self.assertNotIn(bad, h.lower())

    def test_r5_max_brief_fits_and_labels_do_not_overlap(self):
        b = big()
        h = H2.render(b)
        H = int(re.search(r'<svg viewBox="0 0 1200 (\d+)"', h).group(1))
        self.assertLessEqual(H, 780)
        rt, _g = H2.routes(b)
        self.assertEqual(len(rt), COMP_ARROWS)
        boxes = [(lx - lw // 2, ly - 11, lw, 13) for _pts, lx, ly, lw in rt.values()]
        for i, p in enumerate(boxes):
            for q in boxes[i + 1:]:
                hit = p[0] < q[0] + q[2] and q[0] < p[0] + p[2] and p[1] < q[1] + q[3] and q[1] < p[1] + p[3]
                self.assertFalse(hit, (p, q))
        for k, (_pts, lx, _ly, lw) in rt.items():
            self.assertEqual(lw, AH._text_w(b["arrows"][k]["label"]))
            self.assertGreaterEqual(lx - lw // 2, 0)
            self.assertLessEqual(lx + lw // 2, 1200)

    def test_r3_one_link_per_external_and_screen(self):
        # R3: a->db, d->db, db->b collapse into one container->external link marked both ways; detail lives in the legend
        b = brief()
        b["system"]["components"] = [comp("a"), comp("b"), comp("c"), comp("d")]
        b["externals"] = [{"id": "db", "name": "Store", "role": "rows", "uses": [{"name": "Rows", "note": "tables"}],
                           "modules": ["db"]}]
        b["arrows"] = [{"from": "a", "to": "db", "label": "writes", "use": 1, "edges": [0]},
                       {"from": "d", "to": "db", "label": "reads", "use": 1, "edges": [1]},
                       {"from": "db", "to": "b", "label": "rows", "edges": [2]},
                       {"from": "web", "to": "a", "label": "HTTP", "edges": [3]},
                       {"from": "web", "to": "b", "label": "HTTP", "edges": [4]}]
        h = H2.render(b)
        links = re.findall(r'<g data-link="(\w+) (\w+)"><path d="([^"]+)" class="edge"([^/]*)/>', h)
        self.assertEqual([(k, i) for k, i, _d, _m in links], [("screen", "web"), ("external", "db")])
        ext = links[1]
        self.assertRegex(ext[2], r"^M840,(\d+) L880,\1$")              # straight from the container edge
        self.assertIn('marker-end="url(#arr)"', ext[3])
        self.assertIn('marker-start="url(#arr)"', ext[3])
        self.assertRegex(links[0][2], r"^M(\d+),\d+ L\1,\d+$")       # one vertical from the screen
        self.assertEqual(h.count(">HTTP</text>"), 1)                      # labels joined, each once
        self.assertEqual(len(re.findall(r"<g data-arrow=", h)), 0)
        leg = h[h.index('<table class="legend">'):]
        self.assertIn("<li>① Rows — tables · ← A, D</li><li>← B</li>", leg)   # R5: who uses each use

    def test_r3_max_fixture_few_paths_no_crossings(self):
        b = big()
        svg = H2.figure(b)
        self.assertLessEqual(len(re.findall(r'class="edge"', svg)), len(b["screens"]) + len(b["externals"]) + COMP_ARROWS)
        segs = segments(svg)
        for i, (pa, a1, a2) in enumerate(segs):
            for pb, b1, b2 in segs[i + 1:]:
                if pa == pb:
                    continue
                for (h1, h2), (v1, v2) in (((a1, a2), (b1, b2)), ((b1, b2), (a1, a2))):
                    if h1[1] != h2[1] or v1[0] != v2[0] or h1[0] == h2[0]:
                        continue
                    x, y = v1[0], h1[1]
                    inside = min(h1[0], h2[0]) < x < max(h1[0], h2[0]) and min(v1[1], v2[1]) < y < max(v1[1], v2[1])
                    self.assertFalse(inside, ("crossing", h1, h2, v1, v2))

    def test_r3_worst_case_lanes_bounded_work(self):
        # R3: rows abc/def/g with 7 lanes in gap 1 and 5 in gap 2 once took ~10s (7! orders per attach permutation).
        # Lane orders are memoised and exhaustive only up to 6 lanes; work is counted, not timed (tests never read the
        # clock). 4 crossings = the same count the old exhaustive 7-lane search reached; zero is not reachable here.
        b = brief()
        b["system"]["components"] = [comp(i) for i in "abcdefg"]
        pairs = ["ab", "ac", "bc", "ca", "ae", "cd", "bg", "de", "ef", "eg", "fg", "da"]
        b["arrows"] = [{"from": p[0], "to": p[1], "label": "x%d" % k, "edges": [k]} for k, p in enumerate(pairs)]
        n, real = [0], itertools.permutations

        def counting(*a):
            for p in real(*a):
                n[0] += 1
                yield p
        with mock.patch.object(H2.itertools, "permutations", counting):
            rt, g = H2.routes(b)
        self.assertEqual([len(x) for x in g["gaps"]], [0, 7, 5, 0])
        self.assertLess(n[0], 100000)
        self.assertEqual(H2._crossings(dict((k, (v[0], None, 0)) for k, v in rt.items())), 4)

    def test_r3_screen_to_screen_not_bundled(self):
        # R3: web->console is not a link to the system: neither screen's vertical carries it; the legend still does
        b = brief()
        b["screens"].append({"id": "console", "name": "Console", "note": "admin", "role": "settings", "modules": ["cm"]})
        b["arrows"].append({"from": "web", "to": "console", "label": "deep link", "edges": [9]})
        h = H2.render(b)
        svg = h[:h.index("</svg>")]
        self.assertNotIn("deep link", svg)
        self.assertEqual(len(re.findall(r'<g data-link="screen ', svg)), 2)
        self.assertNotIn('marker-end', re.search(r'<g data-link="screen console"><path[^>]*>', svg).group(0))

    def test_r5_default_heads(self):
        h = H2.render(brief())
        self.assertIn("<h2>Architecture</h2>", h)
        self.assertIn("<h2>Components</h2>", h)
        self.assertIn("<li>① Rows · ← Svc</li>", h)                    # R5: a use without a note still names its users
        b = brief()
        b["heads"] = {"arch": "Map", "legend": "Parts"}
        h = H2.render(b)
        self.assertIn("<h2>Map</h2>", h)
        self.assertIn("<h2>Parts</h2>", h)

    def test_r2_r5_no_ellipsis_in_figure(self):
        # R2/R5: names wrap or shrink, never cut with an ellipsis; descriptions are not drawn in boxes at all
        long_name = "\uac00\ub098" * 20
        for b in (big(), brief()):
            b["actors"][0]["name"] = ("\ub2e4" * 30)
            b["system"]["components"][0]["name"] = long_name
            b["externals"][0]["name"] = long_name
            b["externals"][0]["uses"][0]["name"] = "\ub77c" * 30
            b["system"]["principles"][0]["text"] = "\ub9c8" * 100
            svg = H2.figure(b)
            self.assertNotIn("\u2026", svg)
            for word in ("\ub2e4" * 30, "\ub77c" * 30):
                self.assertIn(word, re.sub(r"<[^>]+>|\n", "", svg))   # whole across wrapped lines, never cut
            self.assertNotIn("note of", svg)

    def test_self_contained(self):
        h = H2.render(big()).lower()
        for bad in ("<script", "src=", "href=", "http:", "https:", "<link", "@import"):
            self.assertNotIn(bad, h)

    def test_deterministic_bytes(self):
        self.assertEqual(H2.render(big()).encode("utf-8"), H2.render(big()).encode("utf-8"))

    def test_escaping(self):
        b = brief()
        b["title"] = "<img onerror=x>"
        b["what"] = 'A "q" & <b>'
        b["actors"][0]["name"] = "<i>"
        b["system"]["components"][0]["name"] = 'S & "q"'
        b["system"]["principles"][0]["text"] = "</text><x>"
        b["externals"][0]["uses"][0]["name"] = "<c>"
        b["arrows"][0]["label"] = "&amp"
        h = H2.render(b)
        for raw in ("<img", "<i>", "<x>", "<c>", '"q"', "<b>"):
            self.assertNotIn(raw, h)
        self.assertIn("A &quot;q&quot; &amp; &lt;b&gt;", h)
        self.assertIn("&amp;amp", h)


if __name__ == "__main__":
    unittest.main()
