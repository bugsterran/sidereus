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
            a, z = ends
            self.assertIn(pts[0], [(a[0] + a[2] // 2, a[1]), (a[0] + a[2] // 2, a[1] + a[3]),
                                   (a[0], a[1] + a[3] // 2), (a[0] + a[2], a[1] + a[3] // 2)], "starts off a side mid-point")
            self.assertIn(pts[-1], [(z[0] + z[2] // 2, z[1]), (z[0] + z[2] // 2, z[1] + z[3]),
                                    (z[0], z[1] + z[3] // 2), (z[0] + z[2], z[1] + z[3] // 2)], "ends off a side mid-point")

    def test_deterministic(self):
        self.assertEqual(AH.render(brief(7)).encode("utf-8"), AH.render(brief(7)).encode("utf-8"))


if __name__ == "__main__":
    unittest.main()
