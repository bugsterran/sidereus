"""Hook-sent token counts (Cursor `stop`): per-generation store, persistence, today usage and timeline rows."""
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime
from unittest import mock

from tests._load import sidereus

ext = sidereus("ext")
st = sidereus("ext_store")   # owner of _hooktok / EXT_HOOKTOK_FILE
te = sidereus("timeline_ext")
gm = sidereus("plat_gemini")

SID = "c0ffee00-1111-2222-3333-444455556666"
SECRET = "SECRET-CURSOR-TEXT"


class HookTok(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # Pinned to local noon so «today» never straddles midnight.
        self.now = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0).timestamp()
        clock = mock.Mock()
        clock.time = lambda: self.now
        self.saved = (dict(st._ext), dict(st._runs), dict(st._tok), dict(st._hooktok), dict(st._ext_ended))
        for p in (mock.patch.object(st, "time", clock),
                  mock.patch.object(st, "EXT_HOOKTOK_FILE", os.path.join(self.tmp, "ext-hooktok.json")),
                  mock.patch.object(st, "_ext_save_locked", lambda: None),
                  mock.patch.object(st, "_runs_save_locked", lambda: None),
                  mock.patch.object(gm, "scan", lambda since=0.0: [])):
            p.start()
            self.addCleanup(p.stop)
        for d in (st._ext, st._runs, st._tok, st._hooktok):
            d.clear()

    def tearDown(self):
        for d, v in zip((st._ext, st._runs, st._tok, st._hooktok, st._ext_ended), self.saved):
            d.clear(); d.update(v)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def stop(self, gen, i, o, cr, cw=0, t=None, **extra):
        req = {"platform": "cursor", "session_id": SID, "event": "Stop", "cwd": "/w/cuproj", "model": "default",
               "ts": t or self.now - 60, "gen_id": gen, "usage": {"in": i, "out": o, "cr": cr, "cw": cw}}
        req.update(extra)
        return st.ext_ingest(req)

    def test_turns_counted_once(self):
        self.stop("gen-1", 14645, 28, 3968)
        self.assertEqual(ext.ext_usage_today(now=self.now)["cu"]["tok"], 18641)
        self.stop("gen-1", 14645, 28, 3968)                   # same generation again: overwritten
        self.assertEqual(ext.ext_usage_today(now=self.now)["cu"]["tok"], 18641)
        self.stop("gen-2", 14727, 17, 3968, t=self.now - 30)
        u = ext.ext_usage_today(now=self.now)["cu"]
        self.assertEqual((u["tok"], u["in"], u["out"], u["cache"], u["n_sessions"], u["models"]),
                         (37353, 29372, 45, 7936, 1, []))

    def test_no_gen_id_dropped_and_metadata_only(self):
        st.ext_ingest({"platform": "cursor", "session_id": SID, "event": "Stop", "ts": self.now - 60,
                       "usage": {"in": 5, "out": 5}})
        self.assertEqual(st._hooktok, {})
        self.stop("gen-1", 1, 2, 3, text=SECRET, user_email=SECRET, transcript_path="/x/" + SECRET)
        self.stop("gen-x", 1, 1, 1, model="m-" + SECRET)
        with open(st.EXT_HOOKTOK_FILE, encoding="utf-8") as f:
            raw = f.read()
        self.assertIn("gen-1", raw)
        self.assertEqual(json.loads(raw)["cursor|" + SID]["gens"]["gen-1"], [1, 2, 3, 0, self.now - 60, ""])
        for key in ("text", "user_email", "transcript_path"):
            self.assertNotIn(key, raw)
        self.assertEqual(raw.count(SECRET), 1)                 # only the model id, cut to 40 chars

    def test_survives_session_end_and_reload(self):
        self.stop("gen-1", 14645, 28, 3968)
        st.ext_ingest({"platform": "cursor", "session_id": SID, "event": "SessionEnd", "ts": self.now - 10})
        self.assertNotIn(("cursor", SID), st._ext)
        self.assertEqual(ext.ext_usage_today(now=self.now)["cu"]["tok"], 18641)
        st._hooktok.clear()
        st._hooktok_load()
        self.assertEqual(ext.ext_usage_today(now=self.now)["cu"]["tok"], 18641)
        rows = te._plat_tl_rows(self.now - 3600, self.now)
        cu = [r for r in rows if r.get("plat") == "cu"]
        self.assertEqual(len(cu), 1)
        self.assertEqual((cu[0]["sid"], cu[0]["tk"], cu[0]["cwd"]), (SID, 18641, "/w/cuproj"))

    def test_timeline_live_row_tokens(self):
        self.stop("gen-1", 14645, 28, 3968)
        self.stop("gen-2", 14727, 17, 3968, t=self.now - 30)
        cu = [r for r in te._plat_tl_rows(self.now - 3600, self.now) if r.get("plat") == "cu"]
        self.assertEqual([r["tk"] for r in cu], [37353])

    def test_yesterday_excluded(self):
        self.stop("gen-old", 1000, 10, 0, t=self.now - 13 * 3600)
        self.stop("gen-1", 14645, 28, 3968)
        self.assertEqual(ext.ext_usage_today(now=self.now)["cu"]["tok"], 18641)

    def test_future_ts_clamped_and_keeps_others(self):
        self.stop("gen-1", 14645, 28, 3968)
        self.stop("gen-far", 1, 1, 1, t=9e9)
        gens = st._hooktok["cursor|" + SID]["gens"]
        self.assertEqual(set(gens), {"gen-1", "gen-far"})
        self.assertEqual(gens["gen-far"][4], self.now)

    def test_adapter_platforms_not_recorded(self):
        for plat in ("codex", "gemini"):
            st.ext_ingest({"platform": plat, "session_id": SID, "event": "Stop", "ts": self.now - 60,
                           "gen_id": "gen-1", "usage": {"in": 5, "out": 5, "cr": 0, "cw": 0}})
        self.assertEqual(st._hooktok, {})

    def test_ttl_and_cap(self):
        self.stop("gen-old", 1, 1, 1, t=self.now - st.EXT_HOOKTOK_TTL_S - 100)
        self.stop("gen-1", 1, 1, 1)
        self.assertEqual(set(st._hooktok["cursor|" + SID]["gens"]), {"gen-1"})
        with mock.patch.object(st, "EXT_HOOKTOK_MAX", 2):
            self.stop("gen-2", 1, 1, 1, t=self.now - 50)
            self.stop("gen-3", 1, 1, 1, t=self.now - 40)
        self.assertEqual(set(st._hooktok["cursor|" + SID]["gens"]), {"gen-2", "gen-3"})


if __name__ == "__main__":
    unittest.main()
