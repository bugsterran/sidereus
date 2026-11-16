"""17-attention.js attnWhy renders every attention reason from k + v in both languages.
Korean must equal the server's former `why` strings (sidereus/attention.py templates) byte for byte;
English must equal the former en rebuild. Rows without v return the server `why` unchanged."""
import json
import shutil
import subprocess
import unittest

from tests._i18n_js import i18n_switch
from tests._load import js_fn
from tests._node import node_e

# (k, v, ko, en) — ko built with the server's former format strings.
CASES = [
    ("gone", {"q": True}, "끊김?", "Disconnected?"),
    ("gone", {"q": False}, "끊김", "Disconnected"),
    ("ask", {"kept": False}, "질문 대기", "Awaiting answer"),
    ("ask", {"kept": True}, "질문 대기 · 이후 작업 계속", "Awaiting answer · kept working"),
    ("abort", {}, "중단됨 — 다시 지시 필요", "Interrupted — needs a new instruction"),
    ("ctx95", {"pct": 96}, "컨텍스트 %d%% — 곧 자동 압축" % 96, "Context 96% — auto-compact soon"),
    ("ctx85", {"pct": 87}, "컨텍스트 %d%%" % 87, "Context 87%"),
    ("wreck", {"n": 3}, "반쯤 고친 파일 %d개" % 3, "Leftover edits in 3 files"),
    ("stall", {"m": 7}, "서브에이전트 %d분 무기록 · 부모 대기" % 7, "Subagent stalled 7m · parent waiting"),
    ("loop", {"n": 6, "tool": "Bash"}, "%s 같은 호출 %d회 반복" % ("Bash", 6), "Same action repeated 6× · Bash"),
    ("loop", {"n": 6, "tool": None}, "%s 같은 호출 %d회 반복" % ("도구", 6), "Same action repeated 6×"),
    ("toolfail", {"n": 4, "tool": "Read"}, "같은 오류 %d회 반복 · %s" % (4, "Read"), "Same error repeated 4× · Read"),
    ("toolfail", {"n": 4, "tool": None}, "같은 오류 %d회 반복 · %s" % (4, "도구"), "Same error repeated 4×"),
    ("fail", {"kind": "flimit", "n": 1}, "한도로 멈춤", "Failure alert"),
    ("fail", {"kind": "fcut", "n": 3}, "바깥 원인으로 끊김" + " 등 %d건" % 3, "Failure alert (3)"),
    ("fail", {"kind": "fcheck", "n": 2}, "원인 확인 필요" + " 등 %d건" % 2, "Failure alert (2)"),
    ("fail", {"kind": "fwreck", "n": 1}, "반쯤 고친 파일", "Failure alert"),
    ("fail", {"kind": "fail", "n": 1}, "실패 알림", "Failure alert"),
    ("fail", {"kind": "fail", "n": 5}, "실패 알림 등 5건", "Failure alert (5)"),
    ("mailidle", {"n": 2, "m": 12}, "메일 %d통 대기 · 세션 쉼 %d분" % (2, 12), "Mail waiting · session idle · 2 messages · 12m"),
    ("bglong", {"n": 2, "m": 45, "idle": 0}, "장기 백그라운드 %d개 · 최장 %d분" % (2, 45), "Long background 2 · longest 45m"),
    ("bglong", {"n": 2, "m": 45, "idle": 1}, "장기 백그라운드 %d개 · 최장 %d분" % (2, 45) + " · 무출력 %d개" % 1,
     "Long background 2 · longest 45m · 1 idle"),
    ("bgidle", {"n": 3, "idle": 2, "m": 25}, "백그라운드 셸 %d개 · 무출력 %d개 · 최장 %d분" % (3, 2, 25),
     "3 background shells · 2 idle · longest 25m"),
    ("bgidle", {"n": 1, "idle": 1, "m": 9}, "백그라운드 셸 %d개 · 무출력 %d개 · 최장 %d분" % (1, 1, 9),
     "1 background shell · 1 idle · longest 9m"),
    ("done", {"s": 45}, "작업 끝 · 입력 대기 %d초" % 45, "Done · waiting for input 45s"),
    ("done", {"s": 120}, "작업 끝 · 입력 대기 %d분" % 2, "Done · waiting for input 2m"),
    ("bgdone", {"n": 3, "src": ["agent", "bg"]}, "%s 완료 %d건 미확인" % ("백그라운드·서브에이전트", 3), "3 agent completions unread"),
    ("bgdone", {"n": 1, "src": ["agent"]}, "%s 완료 %d건 미확인" % ("서브에이전트", 1), "1 agent completion unread"),
    ("bgdone", {"n": 2, "src": ["bg"]}, "%s 완료 %d건 미확인" % ("백그라운드", 2), "2 agent completions unread"),
    ("conflict", {"files": 2, "sids": ["a1b2c3d4", "e5f6a7b8"]}, "충돌 위험 · 파일 %d · %s" % (2, "세션 a1b2c3d4, e5f6a7b8"),
     "Conflict risk · 2 files · sessions a1b2c3d4, e5f6a7b8"),
    ("conflict", {"files": 1, "labs": [None, "reviewer"]}, "충돌 위험 · 파일 %d · %s" % (1, "서브에이전트 메인, reviewer"),
     "Conflict risk · 1 file · subagents main, reviewer"),
]


def render(lang, sigs):
    js = ("let LANG = " + json.dumps(lang) + ";\n" + i18n_switch(("T", "TV", "U", "PL")) + js_fn("attnWhy")
          + "\nprocess.stdout.write(JSON.stringify(" + json.dumps(sigs) + ".map(g => attnWhy(g))));")
    r = subprocess.run(node_e(js), capture_output=True, text=True, timeout=20, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class AttnWhyFromV(unittest.TestCase):
    def test_ko_matches_former_server_text(self):
        sigs = [{"k": k, "why": "x", "v": v} for k, v, _, _ in CASES]
        for (k, v, ko, _), got in zip(CASES, render("ko", sigs)):
            self.assertEqual(got.encode("utf-8"), ko.encode("utf-8"), (k, v))

    def test_en_matches_former_rebuild(self):
        sigs = [{"k": k, "why": "x", "v": v} for k, v, _, _ in CASES]
        for (k, v, _, en), got in zip(CASES, render("en", sigs)):
            self.assertEqual(got, en, (k, v))

    def test_no_v_returns_why_unchanged(self):
        sigs = [{"k": "ctx85", "why": "컨텍스트 87%"}, {"k": "loop", "why": "Bash same"}]
        self.assertEqual(render("ko", sigs), ["컨텍스트 87%", "Bash same"])
        self.assertEqual(render("en", sigs), ["컨텍스트 87%", "Bash same"])

    def test_values_are_not_replacement_patterns(self):
        # A tool name holding `$&` / `{n}` must come out verbatim (callback fill, no T() on user data).
        sigs = [{"k": "loop", "v": {"n": 2, "tool": "a$&b{n}"}}, {"k": "conflict", "v": {"files": 1, "labs": ["x$'y"]}}]
        self.assertEqual(render("en", sigs), ["Same action repeated 2× · a$&b{n}", "Conflict risk · 1 file · subagents x$'y"])
        self.assertEqual(render("ko", sigs)[0], "a$&b{n} 같은 호출 2회 반복")

    def test_unknown_number_is_not_zero(self):
        self.assertEqual(render("en", [{"k": "wreck", "v": {}}, {"k": "done", "v": {}}]),
                         ["Leftover edits in ? files", "Done · waiting for input ?"])

    def test_blocked_and_credit_unchanged(self):
        sigs = [{"k": "blocked", "why": "Bash waiting for approval"}, {"k": "blocked", "why": "x"}, {"k": "credit", "why": "12"}]
        self.assertEqual(render("en", sigs), ["Bash waiting for approval", "Waiting for permission", "Spending credits"])
        self.assertEqual(render("ko", sigs)[1:], ["x", "크레딧 사용 중"])


if __name__ == "__main__":
    unittest.main()
