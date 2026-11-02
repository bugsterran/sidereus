"""Run panel «Mode» select must not be read as the Watch/Edit toggle; Save scrolls the diff preview in;
canvas rename keeps the stage's own key order (sidereus/pipeline.py _replace). No live files."""
import os
import re
import unittest

from tests._load import ROOT, sidereus

PL = sidereus("pipeline")


def _src(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


class RunModeSelect(unittest.TestCase):
    def test_select_not_caught_by_view_mode_click(self):
        run = _src("web/js/48b-pipeline-run.js")
        sel = re.search(r"<select class=plrsel data-(\w+)' \+ \(cur && cur\.cx", run)
        self.assertIsNotNone(sel)
        self.assertNotEqual(sel.group(1), "plmode")   # 48k: `.plw [data-plmode]` click -> plModeSet(undefined) left Edit
        self.assertIn("s.dataset." + sel.group(1) + " != null){ PLRUN.mode", run)
        self.assertIn(".plw [data-plmode]", _src("web/js/48k-pipeline-mode.js"))
        self.assertNotIn(" data-plmode'", run)
        self.assertNotIn("dataset.plmode", run)

    def test_save_preview_scrolls_into_view(self):
        s = _src("web/js/48-pipeline.js")
        body = s[s.index("async function plSave("):s.index("async function plDelete(")]
        self.assertIn("querySelector('.plw .pldiff')", body)
        self.assertIn("scrollIntoView({ block: 'nearest' })", body)


class RenameKeyOrder(unittest.TestCase):
    P = {"name": "x", "v": 1, "defaults": {"model": "sonnet", "retry": 1},
         "stages": [{"title": "A", "task": "t", "agent": "a"},
                    {"title": "B", "model": "opus", "agent": "b", "task": "u"}]}

    def test_renamed_stage_keeps_old_key_order(self):
        rows = [{"title": "A", "agent": "a", "task": "t"}, {"title": "B2", "agent": "b", "task": "u", "model": "opus"}]
        new = PL._replace(self.P, {"stages": rows})
        self.assertEqual(list(new["stages"][1]), ["title", "model", "agent", "task"])
        self.assertEqual(list(new["stages"][0]), ["title", "task", "agent"])

    def test_new_stage_uses_schema_order(self):
        rows = [{"title": "A", "agent": "a", "task": "t"}, {"title": "B", "agent": "b", "task": "u", "model": "opus"},
                {"title": "C", "task": "v", "agent": "c"}]
        new = PL._replace(self.P, {"stages": rows})
        self.assertEqual(list(new["stages"][2]), [k for k in PL.STAGE_KEYS if k in rows[2]])


if __name__ == "__main__":
    unittest.main()
