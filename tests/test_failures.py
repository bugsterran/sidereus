"""Deterministic tests for sidereus/failures.py (grading, signatures, alerts, cards) and sidereus/cards.py.

No live files are written: `_card_add` is replaced by a recorder in failures, and the real
`_card_add` is only exercised against a temp CARDS path. No threads are started (module load only).
"""
import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from tests._load import sidereus

F = sidereus("failures")
S = sidereus("failures_scan")   # grading/signature/line parsing moved there 2026-09-24
C = sidereus("cards")
Q = sidereus("quota")


def _ts(offset_s=0):
    """Transcript-style timestamp string (local wall clock as the harness writes it)."""
    return (datetime.now() - timedelta(seconds=offset_s)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _notif(summary, status="failed", tid="toolu_X1"):
    body = ("<task-notification><tool-use-id>%s</tool-use-id><status>%s</status>"
            "<summary>%s</summary></task-notification>" % (tid, status, summary))
    return json.dumps({"type": "user", "timestamp": _ts(), "cwd": "/w/repo",
                       "message": {"role": "user", "content": body}})


def _tool_err(text):
    return json.dumps({"type": "user", "timestamp": _ts(), "cwd": "/w/repo",
                       "message": {"role": "user", "content": [
                           {"type": "tool_result", "is_error": True, "content": text}]}})


class GradeTests(unittest.TestCase):
    def test_every_rule_phrase_maps_to_its_grade_and_basis(self):
        for g, ph in S._GRADE_RULES:
            for kind in ("agent", "bg", "api", "monitor"):
                self.assertEqual(S._fail_grade(kind, "xx " + ph + " yy"), (g, ph), (kind, ph))

    def test_deny_and_hook_are_mine(self):
        for k in ("deny", "hook"):
            g, why = S._fail_grade(k, "Overloaded")
            self.assertEqual(g, "mine")
            self.assertTrue(why)

    def test_tool_is_noise_even_with_cut_phrase(self):
        self.assertEqual(S._fail_grade("tool", "Overloaded")[0], "noise")

    def test_api_without_phrase_is_cut_with_record_basis(self):
        g, why = S._fail_grade("api", "something odd")
        self.assertEqual(g, "cut")
        self.assertIn("api_error", why)

    def test_unknown_is_check_with_empty_basis(self):
        self.assertEqual(S._fail_grade("agent", "exploded"), ("check", ""))
        self.assertEqual(S._fail_grade("bg", None), ("check", ""))

    def test_phrase_precedes_kind(self):
        # api kind with a recognised phrase quotes the phrase, not the generic api basis
        self.assertEqual(S._fail_grade("api", "model is temporarily unavailable"),
                         ("cut", "is temporarily unavailable"))
        # mine phrase wins for an agent kind
        self.assertEqual(S._fail_grade("agent", "Agent was stopped by user"),
                         ("mine", "was stopped by user"))


class SigTests(unittest.TestCase):
    def test_fail_sig_rules(self):
        self.assertIn("600", S._fail_sig("Agent stalled: no progress for 600s"))
        self.assertEqual(S._fail_sig("You've hit your session limit"), "한도 도달 — session")
        self.assertEqual(S._fail_sig("API Error: 529 Overloaded"), "API 529 Overloaded")
        self.assertEqual(S._fail_sig("failed with exit code 2"), "백그라운드 명령 exit 2")
        self.assertEqual(S._fail_sig("nothing known"), "")

    def test_fail_sig_same_cause_groups(self):
        a = S._fail_sig("Agent 'x' Connection closed mid-response at 12:01")
        b = S._fail_sig("Agent 'y' Connection closed mid-response at 18:44")
        self.assertEqual(a, b)
        self.assertTrue(a)

    def test_tool_sig_normalises_paths_numbers_quotes(self):
        a = S._tool_sig('<tool_use_error>File /Users/a/b/c.py line 12 "foo bar" missing</tool_use_error>')
        b = S._tool_sig('<tool_use_error>File /tmp/x/y.txt line 987 "other" missing</tool_use_error>')
        self.assertEqual(a, b)
        self.assertIn("<경로>", a)
        self.assertNotIn("/Users", a)
        self.assertEqual(a, "File <경로> line N <…> missing")
        self.assertEqual(S._tool_sig("  <tool_use_error> File does not exist. </tool_use_error>  "),
                         "File does not exist.")
        self.assertNotIn("12", a)
        self.assertNotIn("foo", a)

    def test_tool_sig_first_line_only_and_empty_fallback(self):
        self.assertEqual(S._tool_sig("Exit code 1\nsecret output here"), "Exit code N")
        self.assertEqual(S._tool_sig(""), "도구 오류")

    def test_tool_sig_cuts_at_word_boundary_with_ellipsis(self):
        # The retro table showed «...before recursi» with no mark that it was cut.
        t = "Hook said: 3 unverified claims in the exchange before recursing into the next subagent call again"
        s = S._tool_sig(t, 60)
        self.assertLessEqual(len(s), 60)
        self.assertTrue(s.endswith("…"))
        self.assertTrue(t.replace("3", "N").startswith(s[:-1]))
        self.assertIn(t.replace("3", "N")[len(s) - 1], " ")   # cut lands on a space, not mid-word
        self.assertEqual(S._tool_sig("short one", 60), "short one")
        self.assertEqual(S._sig_cut("x" * 100, 20), "x" * 19 + "…")   # no space -> hard cut, still marked


class LineTests(unittest.TestCase):
    def test_bad_json_and_no_timestamp(self):
        self.assertEqual(S._fail_line("not json"), ())
        self.assertEqual(S._fail_line(json.dumps({"type": "system", "subtype": "api_error"})), ())

    def test_api_error_record(self):
        ln = json.dumps({"type": "system", "subtype": "api_error", "timestamp": _ts(),
                         "error": {"status": 529, "message": "Overloaded"}})
        (ev,) = S._fail_line(ln)
        self.assertEqual((ev["kind"], ev["grade"], ev["sig"]), ("api", "cut", "API 529"))

    def test_agent_failed_notification(self):
        (ev,) = S._fail_line(_notif("Agent \"fix\" failed: Connection closed mid-response", tid="toolu_A"))
        self.assertEqual(ev["kind"], "agent")
        self.assertEqual(ev["tid"], "toolu_A")
        self.assertEqual(ev["grade"], "cut")
        self.assertEqual(ev["why"], "Connection closed mid-response")
        self.assertEqual(ev["cwd"], "/w/repo")

    def test_stopped_by_user_is_stop_mine(self):
        (ev,) = S._fail_line(_notif("Agent \"x\" was stopped by user", status="killed"))
        self.assertEqual((ev["kind"], ev["grade"]), ("stop", "mine"))

    def test_killed_non_agent_dropped_completed_ignored(self):
        self.assertEqual(S._fail_line(_notif("Background command \"ls\" killed", status="killed")), ())
        self.assertEqual(S._fail_line(_notif("Agent \"x\" done", status="completed")), ())

    def test_bg_and_monitor_kinds(self):
        (ev,) = S._fail_line(_notif("Background command \"make\" failed with exit code 2"))
        self.assertEqual((ev["kind"], ev["sig"], ev["grade"]), ("bg", "백그라운드 명령 exit 2", "check"))
        (ev,) = S._fail_line(_notif("Monitor \"w\" stopped"))
        self.assertEqual((ev["kind"], ev["sig"]), ("monitor", "감시 failed"))

    def test_tool_result_classification(self):
        (h,) = S._fail_line(_tool_err("Hook denied: blocked"))
        (d,) = S._fail_line(_tool_err("The user doesn't want to proceed with this tool use."))
        (u,) = S._fail_line(_tool_err("claude-opus-5 is temporarily unavailable, fallback"))
        (t,) = S._fail_line(_tool_err("Exit code 1"))
        self.assertEqual((h["kind"], h["grade"]), ("hook", "mine"))
        self.assertEqual((d["kind"], d["grade"]), ("deny", "mine"))
        self.assertEqual((u["kind"], u["grade"], u["why"]), ("api", "cut", "is temporarily unavailable"))
        self.assertEqual((t["kind"], t["grade"], t["sig"]), ("tool", "noise", "Exit code N"))


class AlertTests(unittest.TestCase):
    def _q(self, five=None, seven=None):
        q = {}
        if five:
            q["five_hour"] = {"resets_at": five}
        if seven:
            q["seven_day"] = {"resets_at": seven}
        return mock.patch.object(Q, "quota", return_value=q)

    def test_reset_hhmm_formats_and_missing(self):
        t = datetime(2026, 9, 23, 5, 30, tzinfo=timezone.utc)
        iso = t.isoformat().replace("+00:00", "Z")
        with self._q(five=iso, seven=iso):
            self.assertEqual(F._reset_hhmm("5h"), time.strftime("%H:%M", time.localtime(t.timestamp())))
            self.assertEqual(F._reset_hhmm("7d"), time.strftime("%m/%d %H:%M", time.localtime(t.timestamp())))
        with self._q():
            self.assertEqual(F._reset_hhmm("5h"), "")
        with mock.patch.object(Q, "quota", side_effect=RuntimeError("x")):
            self.assertEqual(F._reset_hhmm("7d"), "")

    def test_limit_phrases_map_to_window(self):
        with mock.patch.object(F, "_reset_hhmm", return_value="14:00") as rh:
            for ph, win in F._LIMIT_WIN:
                kind, extra, line = F._fail_alert({"grade": "cut", "why": ph, "text": "x " + ph})
                self.assertEqual(kind, "flimit")
                self.assertEqual((extra["win"], extra["reset"]), (win, "14:00"))
                self.assertIn("14:00", line)
                self.assertIn(win, line)
            self.assertEqual(rh.call_count, len(F._LIMIT_WIN))

    def test_limit_without_quota_has_no_time(self):
        with mock.patch.object(F, "_reset_hhmm", return_value=""):
            kind, extra, line = F._fail_alert({"grade": "cut", "why": "hit your weekly limit", "text": ""})
        self.assertEqual((kind, extra["win"], extra["reset"]), ("flimit", "7d", ""))
        self.assertIn("after the 7d reset", line)

    def test_other_cut_check_mine_noise(self):
        k, extra, _ = F._fail_alert({"grade": "cut", "why": "Overloaded", "text": "Overloaded",
                                      "kind": "bg", "tid": "t1", "sig": "s"})
        self.assertEqual(k, "fcut")
        self.assertNotIn("win", extra)
        self.assertEqual((extra["label"], extra["ekind"], extra["tid"]), ("백그라운드 작업", "bg", "t1"))
        self.assertEqual(F._fail_alert({"grade": "check"})[0], "fcheck")
        self.assertEqual(F._fail_alert({})[0], "fcheck")   # missing grade defaults to check
        for g in ("mine", "noise"):
            self.assertEqual(F._fail_alert({"grade": g})[0], "")
            self.assertEqual(F._fail_alert({"grade": g})[2], "")

    def test_alert_text_carries_no_conversation_text(self):
        secret = "SECRET-CONVERSATION-TEXT"
        with mock.patch.object(F, "_reset_hhmm", return_value="09:00"):
            for g, why in (("cut", "hit your session limit"), ("cut", "Overloaded"), ("check", "")):
                kind, extra, line = F._fail_alert({"grade": g, "why": why, "kind": "agent",
                                                   "text": "%s %s" % (why, secret)})
                self.assertNotIn(secret, line)
                self.assertNotIn(secret, json.dumps(extra, ensure_ascii=False))


class CardFlowBase(unittest.TestCase):
    def setUp(self):
        self.added = []
        rec = lambda kind, project, title, text="", cwd="", extra=None: self.added.append(
            {"kind": kind, "project": project, "title": title, "text": text, "cwd": cwd, "extra": extra or {}})
        self.patches = [mock.patch.object(F, "_card_add", side_effect=rec),
                        mock.patch.dict(F._FAIL_CARDED, {}, clear=True),
                        mock.patch.dict(F._WRECK_CARDED, {}, clear=True),
                        mock.patch.object(F, "_FAIL_SEEDED", [False]),
                        mock.patch.object(F, "_WRECK_SEEDED", [False]),
                        mock.patch.object(F, "_reset_hhmm", return_value="")]
        for p in self.patches:
            p.start()
        self.evs = []
        self.patches.append(mock.patch.object(F, "_fail_events", side_effect=lambda h: (list(self.evs), 0, h)))
        self.patches[-1].start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()


class FailCardTests(CardFlowBase):
    def _ev(self, **kw):
        ev = {"kind": "agent", "grade": "cut", "why": "Overloaded", "text": "Overloaded",
              "sig": "API 529", "tid": "t1", "at": 100, "cwd": "/w", "proj": "w"}
        ev.update(kw)
        return ev

    def test_first_scan_seeds_without_cards(self):
        self.evs = [self._ev()]
        F._fail_cards()
        self.assertEqual(self.added, [])
        F._fail_cards()                           # same failure again: still nothing
        self.assertEqual(self.added, [])

    def test_empty_first_scan_still_ends_seeding(self):
        F._fail_cards()
        self.evs = [self._ev()]
        F._fail_cards()
        self.assertEqual(len(self.added), 1)
        self.assertEqual(self.added[0]["kind"], "fcut")

    def test_dedupe_key_kind_sig_tid(self):
        F._fail_cards()
        self.evs = [self._ev(), self._ev(at=200), self._ev(sig="other"), self._ev(tid="t2")]
        F._fail_cards()
        F._fail_cards()
        self.assertEqual(len(self.added), 3)
        self.assertIn("fcut|API 529|t1", F._FAIL_CARDED)

    def test_dedupe_falls_back_to_sid_then_at(self):
        F._fail_cards()
        self.evs = [self._ev(tid="", sid="S1"), self._ev(tid="", sid="S1", at=999),
                    self._ev(tid="", sid="", at=5), self._ev(tid="", sid="", at=6)]
        F._fail_cards()
        self.assertEqual(len(self.added), 3)
        self.assertIn("fcut|API 529|S1", F._FAIL_CARDED)

    def test_only_card_kinds_and_non_silent_grades(self):
        F._fail_cards()
        self.evs = [self._ev(kind="tool", grade="noise"), self._ev(kind="hook", grade="mine"),
                    self._ev(kind="monitor", grade="check"), self._ev(kind="agent", grade="mine"),
                    self._ev(kind="bg", grade="check", tid="b1")]
        F._fail_cards()
        self.assertEqual([c["kind"] for c in self.added], ["fcheck"])

    def test_card_fields_and_no_conversation_text(self):
        F._fail_cards()
        secret = "USER-SAID-SOMETHING-PRIVATE"
        self.evs = [self._ev(why="hit your 5-hour limit", text="hit your 5-hour limit " + secret, sid="S9")]
        F._fail_cards()
        (c,) = self.added
        self.assertEqual(c["kind"], "flimit")
        self.assertEqual(c["title"], F.FAIL_ALERT_TITLE["flimit"])
        self.assertEqual((c["project"], c["cwd"]), ("w", "/w"))
        for k in ("tid", "sid", "sig", "why", "label", "ekind", "win", "reset"):
            self.assertIn(k, c["extra"], k)
        self.assertEqual((c["extra"]["tid"], c["extra"]["sid"], c["extra"]["win"]), ("t1", "S9", "5h"))
        self.assertNotIn(secret, json.dumps(c, ensure_ascii=False))

    def test_fail_events_error_is_swallowed_and_keeps_seeding(self):
        with mock.patch.object(F, "_fail_events", side_effect=RuntimeError("boom")):
            F._fail_cards()
        self.assertFalse(F._FAIL_SEEDED[0])


class WreckCardTests(CardFlowBase):
    def _row(self, **kw):
        r = {"tid": "w1", "dirty": 3, "proj": "p", "cwd": "/p", "sig": "서브에이전트 failed", "type": "Explore"}
        r.update(kw)
        return r

    def test_seed_then_once_per_wreck(self):
        F._wreck_cards([self._row()])
        self.assertEqual(self.added, [])          # seeding
        F._wreck_cards([self._row(), self._row(tid="w2", dirty=2)])
        F._wreck_cards([self._row(tid="w2", dirty=5)])
        self.assertEqual(len(self.added), 1)
        c = self.added[0]
        self.assertEqual((c["kind"], c["title"]), ("fwreck", F.FAIL_ALERT_TITLE["fwreck"]))
        self.assertIn("2 half-edited files", c["text"])
        for k in ("tid", "n", "sig", "why", "label", "ekind"):
            self.assertIn(k, c["extra"], k)
        self.assertEqual((c["extra"]["tid"], c["extra"]["n"], c["extra"]["label"]), ("w2", 2, "Explore"))

    def test_clean_or_tidless_rows_skipped(self):
        F._wreck_cards([])
        F._wreck_cards([self._row(dirty=0), self._row(tid="")])
        self.assertEqual(self.added, [])
        self.assertEqual(F._WRECK_CARDED, {})


class CardAddTests(unittest.TestCase):
    def test_extra_fields_carried_but_do_not_override_core(self):
        with tempfile.TemporaryDirectory() as d:
            fp = os.path.join(d, "cards.jsonl")
            with mock.patch.object(C, "CARDS", fp):
                row = C._card_add("fcut", "proj", "T", "line", "/c",
                                  {"tid": "t", "sid": "s", "sig": "g", "why": "w", "label": "l",
                                   "ekind": "agent", "n": 2, "win": "5h", "reset": "10:00", "kind": "HIJACK"})
                with open(fp, encoding="utf-8") as f:
                    saved = json.loads(f.readline())
                rows = C.cards(limit=5)
        self.assertEqual(saved, row)
        self.assertEqual(row["kind"], "fcut")
        for k, v in (("tid", "t"), ("sid", "s"), ("n", 2), ("win", "5h"), ("reset", "10:00")):
            self.assertEqual(row[k], v)
        self.assertEqual(rows[0]["tid"], "t")


if __name__ == "__main__":
    unittest.main()
