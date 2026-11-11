"""arch_brief_html: two sections, self-contained (no script/src/href/URL), escaping, box cap, n/a row, deterministic bytes."""
import re
import unittest

from tests._load import sidereus

AH = sidereus("arch_brief_html")


def brief(n_boxes=3, route=None):
    boxes = [{"id": "b%d" % k, "name": "Box %d" % k, "band": "top" if k % 2 == 0 else "low", "modules": ["m%d" % k, "x%d" % k]}
             for k in range(n_boxes)]
    return {"v": 1, "repo": "/r", "commit": "a" * 40, "title": "Demo",
            "bands": [{"id": "top", "name": "Screens"}, {"id": "low", "name": "Data"}],
            "boxes": boxes,
            "arrows": [{"from": "b0", "to": "b1", "label": "reads", "edges": [0, 2]}, {"from": "b0", "to": "b2", "edges": [1]}],
            "route": route or {"by": "path prefix", "rows": [{"when": "/api/*", "goes": "API", "box": "b1",
                                                              "evidence": {"file": "app/router.py", "line": 12}}]}}


class RenderTest(unittest.TestCase):
    def test_two_sections(self):
        h = AH.render(brief())
        self.assertEqual(len(re.findall(r"<section\b", h)), 2)
        self.assertIn(">Architecture<", h)
        self.assertIn(">Decision order<", h)

    def test_self_contained(self):
        h = AH.render(brief()).lower()
        for bad in ("<script", "src=", "href=", "http", "<link", "@import"):
            self.assertNotIn(bad, h)

    def test_escaping(self):
        b = brief()
        b["title"] = "<img onerror=x>"
        b["boxes"][0]["name"] = 'A "q" & <b>'
        b["boxes"][0]["note"] = "<script>"
        b["arrows"][0]["label"] = "</text><x>"
        b["route"]["rows"][0]["when"] = "<i>"
        b["heads"] = {"arch": "<h>", "route": "R&D"}
        h = AH.render(b)
        for raw in ("<img", '"q"', "<b>", "<script>", "</text><x>", "<i>", "<h>", "R&D"):
            self.assertNotIn(raw, h)
        self.assertIn("&lt;img onerror=x&gt;", h)
        self.assertIn("R&amp;D", h)

    def test_box_attributes(self):
        h = AH.render(brief(12))
        self.assertEqual(len(re.findall(r"data-box=", h)), 12)
        self.assertIn('data-mods="m0 x0"', h)
        self.assertIn('data-edges="0 2"', h)
        self.assertEqual(len(re.findall(r"<title>", h)), 12 + 1)   # one per box + the document title

    def test_wrap_second_row(self):
        b = brief(12)
        for x in b["boxes"]:
            x["band"] = "top"
        pos, _bands, _h = AH.layout(b)
        self.assertEqual(len(set(p[1] for p in pos.values())), 2)   # 12 boxes in one band -> two rows
        b = brief(5)
        for x in b["boxes"]:
            x["band"] = "top"
        self.assertEqual(len(set(p[1] for p in AH.layout(b)[0].values())), 1)

    def test_na_one_row(self):
        h = AH.render(brief(route={"na": "No router."}))
        sec = h.split('<section class="route">')[1]
        self.assertEqual(len(re.findall(r"<tr\b", sec)), 1)
        self.assertIn("No router.", sec)

    def test_arrows_never_cross_a_box(self):
        # Three bands: 6 boxes on top (two rows), 2 in the middle, 3 at the bottom; arrows skip boxes and bands.
        bands = [{"id": "t", "name": "T"}, {"id": "m", "name": "M"}, {"id": "l", "name": "L"}]
        layout = ["t"] * 6 + ["m"] * 2 + ["l"] * 3
        boxes = [{"id": "b%d" % k, "name": "B%d" % k, "band": bd, "modules": ["m%d" % k]} for k, bd in enumerate(layout)]
        pairs = [(0, 2), (2, 0), (0, 1), (3, 5), (0, 9), (9, 0), (4, 10), (1, 8), (6, 7), (2, 3), (5, 3), (8, 1), (0, 5)]
        b = {"v": 1, "repo": "/r", "commit": "a" * 40, "title": "T", "bands": bands, "boxes": boxes,
             "arrows": [{"from": "b%d" % f, "to": "b%d" % t, "edges": [0]} for f, t in pairs], "route": {"na": "n/a"}}
        pos = AH.layout(b)[0]
        rt = AH.routes(b)
        self.assertEqual(len(rt), len(pairs))

        def hits(p, q, r):
            x, y, w, h = r
            (x1, y1), (x2, y2) = p, q
            if y1 == y2:
                return y < y1 < y + h and min(x1, x2) < x + w and max(x1, x2) > x
            return x < x1 < x + w and min(y1, y2) < y + h and max(y1, y2) > y

        for k, (f, t) in enumerate(pairs):
            pts = rt[k][0]
            self.assertTrue(all(p[0] == q[0] or p[1] == q[1] for p, q in zip(pts, pts[1:])), "not orthogonal")
            ends = (pos["b%d" % f], pos["b%d" % t])
            for bid, r in pos.items():
                for p, q in zip(pts, pts[1:]):
                    if r in ends:
                        self.assertFalse(hits(p, q, r) and (p, q) not in (tuple(pts[:2]), tuple(pts[-2:])),
                                         "arrow %s crosses its own end box" % (pairs[k],))
                    else:
                        self.assertFalse(hits(p, q, r), "arrow %s crosses box %s" % (pairs[k], bid))
            for pt, r in ((pts[0], ends[0]), (pts[-1], ends[1])):   # attach points spread along a top/bottom side
                self.assertTrue(r[0] < pt[0] < r[0] + r[2] and pt[1] in (r[1], r[1] + r[3]), "end off a box side")

    def test_busy_figure_never_stacks(self):
        # 4 bands, rows of 1/1/4/3 boxes, 24 labelled arrows: opposite pairs, same-row pairs, five arrows into one box.
        bands = [{"id": "b%d" % k, "name": "Band %d" % k} for k in range(4)]
        layout = [0, 1, 2, 2, 2, 2, 3, 3, 3]
        boxes = [{"id": "x%d" % k, "name": "Box %d" % k, "band": "b%d" % bd, "modules": ["m%d" % k]}
                 for k, bd in enumerate(layout)]
        pairs = [(0, 6), (0, 2), (0, 4), (0, 3), (6, 8), (5, 6), (3, 6), (4, 6), (3, 5), (5, 2), (2, 6), (4, 5),
                 (3, 2), (4, 2), (6, 3), (6, 2), (5, 4), (6, 4), (6, 5), (2, 4), (3, 7), (5, 7), (3, 4), (2, 7)]
        wide = u"인증 확인"   # wide glyphs: labels 90-130px, wider than the 28px gap between boxes
        arrows = [{"from": "x%d" % f, "to": "x%d" % t, "label": "%s %d" % (wide if k % 2 else "reads data", k), "edges": [k]}
                  for k, (f, t) in enumerate(pairs)]
        b = {"v": 1, "repo": "/r", "commit": "a" * 40, "title": "T", "bands": bands, "boxes": boxes, "arrows": arrows,
             "route": {"na": "n/a"}}
        pos = AH.layout(b)[0]
        rt = AH.routes(b)
        self.assertEqual(len(rt), len(pairs))

        def tw(s):
            return sum(11 if ord(c) >= 0x1100 else 6.5 for c in s)

        def hit(a, c):
            return a[0] < c[0] + c[2] and c[0] < a[0] + a[2] and a[1] < c[1] + c[3] and c[1] < a[1] + a[3]

        labs = [(rt[k][2] - tw(a["label"]) / 2, rt[k][3] - 10, tw(a["label"]), 13) for k, a in enumerate(arrows)]
        for i, r in enumerate(labs):
            for j in range(i + 1, len(labs)):
                self.assertFalse(hit(r, labs[j]), "labels %d and %d overlap" % (i, j))
            for bid, box in pos.items():
                self.assertFalse(hit(r, box), "label %d covers box %s" % (i, bid))
        hs = [(k, min(p[0], q[0]), max(p[0], q[0]), p[1]) for k, v in rt.items()
              for p, q in zip(v[0], v[0][1:]) if p[1] == q[1] and p[0] != q[0]]
        for i, h in enumerate(hs):
            for g in hs[i + 1:]:
                if h[0] != g[0] and h[1] < g[2] and g[1] < h[2]:
                    self.assertGreaterEqual(abs(h[3] - g[3]), 13, "runs of arrows %d and %d stack" % (h[0], g[0]))
        heads = [v[0][-1] for v in rt.values()]
        self.assertEqual(len(heads), len(set(heads)), "two arrowheads end on one point")

        def cuts(p, q, r):
            x, y, w, h = r
            if p[0] == q[0]:
                return x < p[0] < x + w and min(p[1], q[1]) < y + h and max(p[1], q[1]) > y
            return y < p[1] < y + h and min(p[0], q[0]) < x + w and max(p[0], q[0]) > x

        segs = [(k, p, q) for k, v in rt.items() for p, q in zip(v[0], v[0][1:])]
        for i, r in enumerate(labs):
            for k, p, q in segs:
                self.assertFalse(k != i and cuts(p, q, r), "arrow %d crosses label %d" % (k, i))
        # Band title text at (PAD + 16, band top + 20), 13px bold: ~9px per narrow glyph.
        for bd, y, _h in AH.layout(b)[1]:
            r = (AH.PAD + 16, y + 8, 9 * len(bd["name"]), 15)
            for k, p, q in segs:
                self.assertFalse(cuts(p, q, r), "arrow %d strikes band title %s" % (k, bd["id"]))

    def _verticals_shared(self, layout, pairs):
        bands = [{"id": "b%d" % k, "name": "B%d" % k} for k in range(max(layout) + 1)]
        boxes = [{"id": "x%d" % k, "name": "X%d" % k, "band": "b%d" % bd, "modules": ["m"]} for k, bd in enumerate(layout)]
        b = {"bands": bands, "boxes": boxes, "arrows": [{"from": "x%d" % f, "to": "x%d" % t, "edges": [0]} for f, t in pairs]}
        rt = AH.routes(b)
        self.assertEqual(len(rt), len(pairs))
        vs = [(k, p[0], min(p[1], q[1]), max(p[1], q[1])) for k, v in rt.items()
              for p, q in zip(v[0], v[0][1:]) if p[0] == q[0] and p[1] != q[1]]
        return [(a[0], c[0]) for i, a in enumerate(vs) for c in vs[i + 1:]
                if a[0] != c[0] and abs(a[1] - c[1]) < 6 and a[2] < c[3] and c[2] < a[3]]

    def test_lane_avoids_attach_stub(self):
        # Arrow 1 skips the middle band; its lane must not sit on arrow 0's attach stub in the gap it crosses.
        self.assertEqual(self._verticals_shared([0, 1, 2, 1, 2, 0, 0, 2], [(3, 2), (0, 7)]), [])

    def test_lanes_one_px_apart_are_one_line(self):
        # Two lanes over the same rows from different base candidates (1px apart) must still separate.
        self.assertEqual(self._verticals_shared([0, 1, 2, 0, 2, 0, 2], [(4, 5), (5, 6)]), [])

    def test_note_fits_box(self):
        b = brief(5)
        b["boxes"][0]["note"] = u"인증 토큰을 확인하고 세션 저장소에서 사용자 권한을 읽어 오는 단계" * 2
        b["boxes"][0]["modules"] = ["module_%d" % k for k in range(20)]
        pos = AH.layout(b)[0]
        bw = pos["b0"][2]
        h = AH.figure(b)
        sub = re.search(r'data-box="b0".*?class="t-sub">([^<]*)<', h, re.S).group(1)
        ids = re.search(r'data-box="b0".*?class="t-ids">([^<]*)<', h, re.S).group(1)
        self.assertTrue(sub.endswith(u"…") and ids.endswith(u"…"))

        def w(s, size):   # 12px Hangul ~12px/glyph, narrow ~0.6em
            return sum(size if ord(c) >= 0x1100 else 0.6 * size for c in s)
        self.assertLessEqual(w(sub, 12), bw - 20)
        self.assertLessEqual(w(ids, 10), bw - 20)

    def test_title_fits_box(self):
        b = brief(5)
        b["boxes"][0]["name"] = u"외부 플랫폼 세션 수집과 상태 판정 계층 전체"
        bw = AH.layout(b)[0]["b0"][2]
        lines = re.findall(r'class="t-title">([^<]*)<', AH.figure(b).split('data-box="b1"')[0])
        self.assertEqual(len(lines), 2)
        for ln in lines:   # 14px bold: Hangul ~1em, narrow ~0.6em
            self.assertLessEqual(sum(14 if ord(c) >= 0x1100 else 8.4 for c in ln), bw - 20)

    def test_evidence_wraps(self):
        # A long file:line cell under nowrap widened the decision table past main at 900px.
        b = brief(route={"by": "path", "rows": [{"when": "/x", "goes": "X", "box": "b1",
                                                  "evidence": {"file": "a/" * 40 + "very_long_module_name.py", "line": 1234}}]})
        h = AH.render(b)
        self.assertIn("very_long_module_name.py", h)
        rule = re.search(r"td\.ev\s*\{([^}]*)\}", h).group(1)
        self.assertNotIn("nowrap", rule)
        self.assertIn("overflow-wrap: anywhere", rule)

    def test_svg_min_width_fits_900(self):
        # .fig inner width at a 900px viewport is 866 (main padding 16+16, border 1+1);
        # a larger min-width scrolled the figure sideways at a supported width.
        h = AH.render(brief())
        rule = re.search(r"\nsvg\s*\{([^}]*)\}", h).group(1)
        self.assertLessEqual(int(re.search(r"min-width:\s*(\d+)px", rule).group(1)), 866)

    def test_deterministic(self):
        self.assertEqual(AH.render(brief(7)).encode("utf-8"), AH.render(brief(7)).encode("utf-8"))


if __name__ == "__main__":
    unittest.main()
