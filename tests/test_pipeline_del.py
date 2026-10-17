"""sidereus/pipeline_del.py gaps not covered by test_pipeline.py: non-dict body, symlinked pipelines dir, failed move.

⚠Everything lives in a tmp dir: `BAK_DIR`/`_strftime` (pipeline) and `_proj_ok` (pipeline_del) are patched.
"""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import load, sidereus

load()
PL = sidereus("pipeline")
PD = sidereus("pipeline_del")


class PipelineDel(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.proj = os.path.join(self.tmp, "proj")
        self.bak = os.path.join(self.tmp, "bak")
        for k, v in (("BAK_DIR", self.bak), ("_strftime", lambda fmt: "20261001-120000")):
            p = mock.patch.object(PL, k, v)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(PD, "_proj_ok", lambda proj: proj == self.proj)
        p.start()
        self.addCleanup(p.stop)

    def _file(self, d):
        os.makedirs(d, exist_ok=True)
        f = os.path.join(d, "demo.json")
        with open(f, "w", encoding="utf-8") as fh:
            fh.write("{}")
        return f

    def test_non_dict_body(self):
        for body in (None, [], "x", 3):
            self.assertEqual(PD.delete(body)[0], 400, body)

    def test_symlinked_pipelines_dir(self):
        out = self._file(os.path.join(self.tmp, "outside"))
        os.makedirs(os.path.join(self.proj, ".claude"))
        os.symlink(os.path.dirname(out), os.path.join(self.proj, ".claude", "pipelines"))
        for dry in (True, False):
            self.assertEqual(PD.delete({"proj": self.proj, "name": "demo", "dry": dry})[0], 400)
        self.assertTrue(os.path.isfile(out))                              # nothing moved
        self.assertFalse(os.path.exists(self.bak))

    def test_schema_breaking_file_force_delete(self):
        # «Force delete» uses this same endpoint: an invalid file previews, then moves (never unlinked)
        f = self._file(os.path.join(self.proj, ".claude", "pipelines"))
        self.assertTrue(PL.validate({}, "demo"))
        code, out = PD.delete({"proj": self.proj, "name": "demo"})
        self.assertEqual((code, out["path"]), (200, f))
        self.assertTrue(os.path.isfile(f))
        code, out = PD.delete({"proj": self.proj, "name": "demo", "dry": False})
        self.assertEqual(code, 200, out)
        self.assertFalse(os.path.exists(f))
        self.assertTrue(os.path.isfile(out["backup"]) and out["backup"].startswith(self.bak))

    def test_backup_oserror(self):
        f = self._file(os.path.join(self.proj, ".claude", "pipelines"))

        def boom(*a, **k):
            raise OSError("disk")
        with mock.patch.object(PL, "_backup", boom):
            code, out = PD.delete({"proj": self.proj, "name": "demo", "dry": False})
        self.assertEqual(code, 500, out)
        self.assertFalse(out["ok"])
        self.assertTrue(os.path.isfile(f))


if __name__ == "__main__":
    unittest.main()
