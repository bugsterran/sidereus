"""R4: an optional brief.json `layout` draws at its own coordinates; the gate refuses overlaps, arrow ends off a box border,
labels over boxes/lines/labels, anything outside the figure, components outside the system and bad numbers — each error
names the box or arrow. Without `layout` the render is byte-identical to the automatic one. Pure: no files, no clock."""
import copy
import hashlib
import re
import unittest

from tests._load import sidereus
from tests.test_arch_brief_html_v2 import brief

AL = sidereus("arch_brief_layout")
AH2 = sidereus("arch_brief_html_v2")
AB = sidereus("arch_brief")
# ⚠sha of AH2.render(brief()) before `layout` existed: the automatic figure must not move a byte.
# Re-pinned when the svg min-width went 900px -> 840px (CSS only; figure bytes unchanged).
AUTO_SHA = "1b7d5c7a068c8bcbd343aaa52369c72f29e553c97d64a1156a51c4efa93f3fac"


def layout():
    return {"size": [1200, 700],
            "boxes": {"user": [20, 20, 80, 24], "web": [200, 10, 240, 50], "system": [20, 100, 840, 560],
                      "api": [60, 150, 200, 60], "svc": [400, 150, 200, 60], "dom": [60, 300, 600, 90],
                      "store": [900, 150, 260, 80], "llm": [900, 300, 260, 140]},
            "arrows": [{"pts": [[240, 60], [240, 150]], "label": [300, 80]},
                       {"pts": [[260, 180], [400, 180]], "label": [330, 165]},
                       {"pts": [[600, 170], [900, 170]], "label": [750, 158]},
                       {"pts": [[590, 210], [590, 250], [870, 250], [870, 340], [900, 340]], "label": [730, 240]},
                       {"pts": [[160, 210], [160, 300]], "label": [200, 255]}],
            "principles": [40, 560]}


def laid():
    b = brief()
    b["layout"] = layout()
    return b


def errors(b):
    return AL.shape_errors(b["layout"], b) or AL.geom_errors(b["layout"], b)


class LayoutRender(unittest.TestCase):
    def test_r4_valid_layout_passes_and_draws_given_coordinates(self):
        b = laid()
        self.assertEqual(errors(b), [])
        svg = AL.figure(b)
        self.assertIn('viewBox="0 0 1200 700"', svg)
        got = dict((m[0], [int(v) for v in m[1:]]) for m in re.findall(
            r'data-box="(\w+)"[^>]*><title>[^<]*</title><rect x="(\d+)" y="(\d+)" width="(\d+)" height="(\d+)"', svg))
        want = dict((k, v) for k, v in b["layout"]["boxes"].items() if k not in ("user", "system"))
        self.assertEqual(got, want)
        self.assertIn('<g data-system="1"><rect x="20" y="100" width="840" height="560"', svg)
        self.assertIn('<g data-actor="user"><rect x="20" y="20" width="80" height="24"', svg)
        paths = re.findall(r'<g data-arrow="[^"]+" data-edges="[^"]+"><path d="([^"]+)"', svg)
        self.assertEqual(paths[3], "M590,210 L590,250 L870,250 L870,340 L900,340")

    def test_r4_render_uses_layout_figure_and_by_line(self):
        b = laid()
        h = AB.render(b, "0a1b2c3d-0000")
        self.assertIn('data-layout="1"', h)
        self.assertIn("<small>commit bbbbbbb · drawn by 0a1b2c3d-0000</small>", h)

    def test_r4_without_layout_byte_identical(self):
        b = brief()
        self.assertEqual(hashlib.sha256(AH2.render(b).encode("utf-8")).hexdigest(), AUTO_SHA)
        self.assertEqual(AB.render(b), AH2.render(b))
        self.assertNotIn('data-layout="1"', AB.render(b))

    def test_r4_label_text_escaped(self):
        b = laid()
        b["arrows"][1]["label"] = "a<b"
        svg = AL.figure(b)
        self.assertIn(">a&lt;b</text>", svg)
        self.assertNotIn("a<b", svg)

    def test_format_names_the_caps(self):
        for n in (AL.W_MIN, AL.W_MAX, AL.H_MIN, AL.H_MAX, AL.PTS_MAX, AL.LABEL_H):
            self.assertIn(str(n), AL.FORMAT)
        self.assertIn('"system"', AL.FORMAT)


class LayoutRefusals(unittest.TestCase):
    def refused(self, mutate, needle):
        b = laid()
        mutate(b["layout"], b)
        errs = errors(b)
        self.assertTrue(any(needle in x for x in errs), errs)
        return errs

    def test_r4_overlap(self):
        self.refused(lambda L, b: L["boxes"].__setitem__("svc", [200, 150, 200, 60]), "layout box api: overlaps svc")

    def test_r4_end_off_border(self):
        self.refused(lambda L, b: L["arrows"][1].__setitem__("pts", [[250, 180], [400, 180]]),
                     "arrow 2 api->svc: first point (250, 180) not on the border of api")
        self.refused(lambda L, b: L["arrows"][1].__setitem__("pts", [[260, 180], [420, 180]]),
                     "arrow 2 api->svc: last point (420, 180) not on the border of svc")

    def test_r4_label_over_box(self):
        self.refused(lambda L, b: L["arrows"][1].__setitem__("label", [250, 200]), "arrow 2 api->svc: label over box api")

    def test_r4_label_over_line(self):
        self.refused(lambda L, b: L["arrows"][1].__setitem__("label", [330, 180]), "arrow 2 api->svc: label over the line of itself")
        self.refused(lambda L, b: L["arrows"][4].__setitem__("label", [160, 255]),
                     "arrow 5 api->dom: label over the line of itself")
        self.refused(lambda L, b: L["arrows"][2].__setitem__("label", [730, 250]),
                     "arrow 3 svc->store: label over the line of arrow 4 svc->llm")

    def test_r4_label_over_system_border(self):
        self.refused(lambda L, b: L["arrows"][0].__setitem__("label", [300, 100]),
                     "arrow 1 web->api: label over the system border")

    def test_r4_label_over_actor_connector(self):
        self.refused(lambda L, b: L["arrows"][0].__setitem__("label", [150, 34]),
                     "arrow 1 web->api: label over the connector of actor user")

    def test_r4_label_over_principles_rule(self):
        self.refused(lambda L, b: L["arrows"][4].__setitem__("label", [200, 562]),
                     "arrow 5 api->dom: label over the principles rule")

    def test_r4_principles_over_system_name(self):
        self.refused(lambda L, b: L.__setitem__("principles", [40, 104]), "layout principles: block over the system name")

    def test_r4_label_over_label(self):
        self.refused(lambda L, b: L["arrows"][2].__setitem__("label", [735, 238]),
                     "arrow 3 svc->store: label over the label of arrow 4 svc->llm")

    def test_r4_outside_figure(self):
        self.refused(lambda L, b: L["boxes"].__setitem__("llm", [900, 300, 320, 140]), "layout box llm: outside the 1200x700 figure")
        self.refused(lambda L, b: L["arrows"][0].__setitem__("label", [5, 80]), "arrow 1 web->api: label outside the figure")

    def test_r4_component_outside_system(self):
        self.refused(lambda L, b: L["boxes"].__setitem__("svc", [600, 150, 280, 60]), "layout box svc: component outside system")

    def test_r4_screen_touching_system(self):
        self.refused(lambda L, b: L["boxes"].__setitem__("web", [200, 50, 240, 50]), "layout box web: screen touches system")

    def test_r4_principles_block(self):
        self.refused(lambda L, b: L.__setitem__("principles", [40, 330]), "layout principles: block over component dom")
        self.refused(lambda L, b: L.__setitem__("principles", [100, 560]), "outside system")

    def test_r4_box_too_small_for_text(self):
        self.refused(lambda L, b: L["boxes"].__setitem__("dom", [60, 300, 600, 60]), "layout box dom: too small for its text")
        self.refused(lambda L, b: L["boxes"].__setitem__("llm", [900, 300, 260, 60]), "layout box llm: too small for its text")

    def test_r4_numbers_ints_only(self):
        for bad in (True, -1, 1.5, "10", None):
            self.refused(lambda L, b: L["boxes"].__setitem__("api", [bad, 150, 200, 60]), "layout box api: [x, y, w, h] integers")
        self.refused(lambda L, b: L["arrows"][0].__setitem__("label", [False, 80]), "layout arrow 1 web->api: {pts")
        self.refused(lambda L, b: L.__setitem__("size", [True, 700]), "layout size")
        self.refused(lambda L, b: L.__setitem__("size", [599, 700]), "layout size")
        self.refused(lambda L, b: L["arrows"][0].__setitem__("pts", [[240, 60]]), "layout arrow 1 web->api")
        self.refused(lambda L, b: L["arrows"][0].__setitem__("pts", [[240, 60]] * 9), "layout arrow 1 web->api")

    def test_r4_missing_and_extra_box_ids(self):
        self.refused(lambda L, b: L["boxes"].pop("store"), "layout boxes: missing store")
        self.refused(lambda L, b: L["boxes"].pop("system"), "layout boxes: missing system")
        self.refused(lambda L, b: L["boxes"].__setitem__("ghost", [0, 0, 10, 10]), "layout boxes: unknown ghost")

    def test_r4_arrows_length_mismatch(self):
        self.refused(lambda L, b: L["arrows"].pop(), "layout arrows: one {pts, label} per arrow in the same order (5)")

    def test_r4_unknown_layout_key(self):
        self.refused(lambda L, b: L.__setitem__("zoom", 2), "layout: {size, boxes, arrows, principles}")

    def test_valid_layout_not_mutated(self):
        b = laid()
        before = copy.deepcopy(b)
        errors(b)
        AL.figure(b)
        self.assertEqual(b, before)


if __name__ == "__main__":
    unittest.main()
