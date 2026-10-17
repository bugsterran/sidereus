"""MCP file-peers warning counts distinct live sessions (not units) and skips the caller; English attention/pace."""
import importlib.util
import json
import os
import tempfile
import unittest
from tests._load import sidereus

ab = sidereus("agent_brief")
_P = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mcp", "sidereus_mcp.py")
_spec = importlib.util.spec_from_file_location("sidereus_mcp_peers", _P)
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)
ROOT = "/r/repo"


def _ed(sid8, unit, live=True):
    return {"sid8": sid8, "unit": unit, "agent": "main" if unit == "main" else "general-purpose",
            "project": "repo", "agoSec": 30, "live": live}


def _file(eds, unc=True, sids=True):
    d = {"ok": True, "path": ROOT + "/a.py", "uncommitted": unc, "windowMin": 30, "n": len(eds),
         "liveN": sum(1 for e in eds if e["live"]), "editors": eds}
    if sids:
        d["liveSids"] = sorted({e["sid8"] for e in eds if e["live"]})
    return d


class Patch(unittest.TestCase):
    def patch(self, mod, name, val):
        old = getattr(mod, name)
        setattr(mod, name, val)
        self.addCleanup(setattr, mod, name, old)


class TestWarning(unittest.TestCase):
    def test_session_plus_own_subagent_no_warning(self):
        d = _file([_ed("aaaaaaaa", "main"), _ed("aaaaaaaa", "bbbbbbbb")])
        self.assertEqual(d["liveN"], 2)
        self.assertNotIn("warning", m.fmt_file(d))

    def test_two_sessions_warn_without_caller(self):
        out = m.fmt_file(_file([_ed("aaaaaaaa", "main"), _ed("cccccccc", "main")]))
        self.assertIn("warning: 2+ live sessions (aaaaaaaa, cccccccc)", out)

    def test_clean_file_no_warning(self):
        self.assertNotIn("warning", m.fmt_file(_file([_ed("aaaaaaaa", "main"), _ed("cccccccc", "main")], unc=False)))

    def test_caller_excluded(self):
        eds = [_ed("aaaaaaaa", "main"), _ed("aaaaaaaa", "bbbbbbbb")]
        self.assertNotIn("warning", m.fmt_file(_file(eds), me="aaaaaaaa-1111-2222"))
        out = m.fmt_file(_file(eds + [_ed("cccccccc", "main")]), me="aaaaaaaa-1111-2222")
        self.assertIn("warning: another live session (cccccccc)", out)
        self.assertIn("aaaaaaaa/main main · repo · 30s ago · live (you)", out)

    def test_old_viewer_without_livesids(self):
        d = _file([_ed("aaaaaaaa", "main"), _ed("aaaaaaaa", "bbbbbbbb")], sids=False)
        self.assertNotIn("warning", m.fmt_file(d))

    def test_sid_arg_reaches_formatter_and_no_live_read(self):
        self.patch_get = m._get
        m._get = lambda p, q=None: _file([_ed("aaaaaaaa", "main"), _ed("cccccccc", "main")])
        self.addCleanup(setattr, m, "_get", self.patch_get)
        self.assertFalse(m.DETECT_SELF)
        txt, err = m.call_tool("sidereus_file_peers", {"path": "a.py", "cwd": ROOT, "sid": "cccccccc-x"})
        self.assertFalse(err)
        self.assertIn("another live session (aaaaaaaa)", txt)

    def test_self_sid_from_parent_session_file(self):
        with tempfile.TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, "sessions"))
            with open(os.path.join(td, "sessions", "%d.json" % os.getppid()), "w", encoding="utf-8") as f:
                json.dump({"pid": os.getppid(), "sessionId": "deadbeef-0000"}, f)
            old = os.environ.get("CLAUDE_CONFIG_DIR")
            os.environ["CLAUDE_CONFIG_DIR"] = td
            try:
                self.assertEqual(m._self_sid(), "deadbeef-0000")
                os.remove(os.path.join(td, "sessions", "%d.json" % os.getppid()))
                self.assertEqual(m._self_sid(), "")
            finally:
                if old is None:
                    os.environ.pop("CLAUDE_CONFIG_DIR", None)
                else:
                    os.environ["CLAUDE_CONFIG_DIR"] = old


class TestBriefFileSids(Patch):
    def test_live_sids_distinct(self):
        now, p = 10000.0, ROOT + "/a.py"
        idx = {p: {("aaaaaaaa-1", "main"): {"ts": now - 60, "agent": "", "cwd": ROOT},
                   ("aaaaaaaa-1", "bbbbbbbbcc"): {"ts": now - 90, "agent": "general-purpose", "cwd": ROOT}}}
        self.patch(ab._fo, "index", lambda n=None: idx)
        self.patch(ab._fo, "_live_units", lambda rows: {("aaaaaaaa-1", "main"), ("aaaaaaaa-1", "bbbbbbbbcc")})
        self.patch(ab, "_edit_target", lambda x: None)
        out = ab.brief_file(p, rows=[], now=now)
        self.assertEqual((out["liveN"], out["liveSids"]), (2, ["aaaaaaaa"]))


class TestEnglish(Patch):
    def test_attention_why_english(self):
        rows = [{"sid": "aaaaaaaa-1", "project": "r", "branch": "main", "score": 25, "why": "작업 끝 · 입력 대기 12분 외 1",
                 "sigs": [{"k": "done", "why": "작업 끝 · 입력 대기 12분"}, {"k": "ctx85", "why": "컨텍스트 88%"}]},
                {"sid": "cccccccc-2", "project": "r", "sigs": [{"k": "loop", "why": "Bash 같은 호출 9회 반복"}]},
                {"sid": "dddddddd-3", "project": "r",
                 "sigs": [{"k": "conflict", "why": "충돌 위험 · 파일 2 · 서브에이전트 메인, general-purpose"}]}]
        self.patch(ab, "attention", lambda *a, **k: {"rows": rows})
        self.patch(ab, "cards", lambda n=50: [])
        self.patch(ab, "quota", lambda: {})
        whys = [r["why"] for r in ab.brief_attention(rows=[])["rows"]]
        self.assertEqual(whys, ["Done · waiting for input 12 min +1 more", "Same call repeated 9× · Bash",
                                "Conflict risk · 2 file(s) · subagents main, general-purpose"])
        for w in whys:
            self.assertFalse(any("가" <= ch <= "힣" for ch in w), w)

    def test_pace_name_english(self):
        self.patch(ab, "quota", lambda: {"five_hour": {"pct": 50, "leftSec": 100}})
        self.patch(ab, "quota_burn", lambda: {})
        self.patch(ab, "_saver_state", lambda p, s: {"on": False})
        self.patch(ab, "_saver_view", lambda: {"at": 1000.0, "lv": -2, "lvNm": "많이 느림", "goal": 100})
        self.assertEqual(ab.brief_quota(now=1001.0)["pace"]["name"], "way too slow")


if __name__ == "__main__":
    unittest.main()
