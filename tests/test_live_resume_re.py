"""`_RESUME_ID_RE` on ps-joined argv: `-r`, `--resume=`, paths with spaces, and lookalikes that must not match."""
import unittest

from tests._load import sidereus

lv = sidereus("live")

U = "cc33cc33-0000-4000-8000-000000000001"


def rid(cmd):
    m = lv._RESUME_ID_RE.search(cmd)
    return m.group(1) if m else None


class ResumeRe(unittest.TestCase):
    def test_forms(self):
        for cmd in ("claude --resume " + U,
                    "claude --resume=" + U,
                    "claude -r " + U,
                    "claude -r %s --model opus" % U,
                    "claude --resume /p/%s.jsonl" % U,
                    "claude --resume /Users/a b/Library/Application Support/x/%s.jsonl --print" % U,
                    "claude -r ~/My Projects/p/%s.jsonl" % U):
            self.assertEqual(rid(cmd), U, cmd)

    def test_negative(self):
        for cmd in ("claude --session-id " + U,
                    "claude --foo-r " + U,                         # -r inside another flag
                    "claude -rx " + U,
                    "claude --resume /p/notes --add-dir /q/%s" % U,  # path may not run into the next flag
                    "claude --resume /p/x%s.jsonl" % U,
                    "claude -r " + U + "ff"):
            self.assertIsNone(rid(cmd), cmd)

    def test_retired_via_short_flag_and_spaced_path(self):
        import types
        new, cwd = "dd44dd44-0000-4000-8000-000000000002", "/Users/x/proj"
        saved = {k: getattr(lv, k) for k in ("_ps_snap", "agent_view", "subprocess", "IS_MAC", "_sid_transcript")}
        cache = lv._live_cache
        # ⚠module state shared with sessions: a leaked retired U (== another test's OLD) forced that row to done
        retired, av_argv = set(lv._live_retired[0]), dict(lv._av_argv)
        try:
            lv.IS_MAC = True
            lv._sid_transcript = lambda sid: "/t/%s.jsonl" % sid
            lv.agent_view = lambda ttl=None: {"200": {"sessionId": new, "cwd": cwd}}
            lv.subprocess = types.SimpleNamespace(run=lambda *a, **k: types.SimpleNamespace(stdout="p200\nn%s\n" % cwd))
            for cmd in ("claude -r " + U, "claude --resume /Users/a b/p/%s.jsonl" % U):
                lv._live_cache = (0.0, set())
                lv._ps_snap = lambda ttl=None, c=cmd: [("200", "1", c)]
                lv.live_cwds(ttl=0)
                self.assertIn(U, lv._live_retired[0], cmd)
        finally:
            for k, v in saved.items():
                setattr(lv, k, v)
            lv._live_cache = cache
            lv._live_retired[0] = retired
            lv._av_argv.clear()
            lv._av_argv.update(av_argv)


if __name__ == "__main__":
    unittest.main()
