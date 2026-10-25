"""Off macOS, an account whose `claude agents --json` lookup failed must not mark its open sessions ended.

agent_view() merges the accounts that answered, so `live` is a partial dict; rows of the blind account
(agent_view_unknown()) read Unknown instead of Ended. macOS keeps rows alive through ps+lsof path slots.
No live files, clock or processes: every collaborator is replaced on sidereus.sessions / sidereus.notes.
"""
import types
import unittest
from unittest import mock

from tests import _clock
from tests._load import sidereus

S = sidereus("sessions")
N = sidereus("notes")

# sid -> (cwd, account label; "" = primary)
ROWS = {"A": ("/a", ""), "B": ("/b", "work")}


class BlindAccount(unittest.TestCase):
    def run_rows(self, is_mac, live, alive_sids, blind):
        cache = types.SimpleNamespace(get=lambda k: None, put=lambda k, v: None)

        def row(fp, mt, now, lv, p, stale=False):
            return {"sid": p["sid"], "state": S._row_state(mt, now, lv, p, stale)[0]}

        pats = {
            "IS_MAC": is_mac, "live_cwds": lambda: live, "agent_view_unknown": lambda: set(blind),
            "sid_alive": lambda sid: sid in alive_sids, "_parse_cache": cache,
            "_recent_transcripts": lambda now, h, lv: [(_clock.NOW - 5, "/t/%s.jsonl" % s) for s in ROWS],
            "_parse_transcript": lambda fp: {"sid": fp[3], "cwd": ROWS[fp[3]][0], "shape": "text"},
            "_continued": lambda fp: "", "_subs_mt": lambda sd: 0, "_session_row": row,
            "_row_acct": lambda sid, fp: {"acct": ROWS[sid][1]} if ROWS[sid][1] else {},
            "_otel_state": lambda sid: None, "_note_bg_done": lambda fp, r: None,
            "_note_transition": lambda i: None, "_note_ctx": lambda i: None,
            "ext_children": lambda out: None, "codex_env_dedupe": lambda rows: [],
            "ext_rows": lambda: [], "ext_rollout_rows": lambda: [], "term_attach": lambda out: None,
            "_sid_proj": types.SimpleNamespace(put=lambda k, v: None),
        }
        with mock.patch.multiple(S, create=True, **pats), \
                mock.patch.multiple(N, sid_alive=lambda sid: sid in alive_sids, sid_alive_stale=lambda sid: False), \
                _clock.frozen(S, N):
            return {r["sid"]: r["state"] for r in S._sessions(1, 10)}

    def test_failed_work_account_reads_unknown_not_done(self):
        st = self.run_rows(False, {"/a": 1}, {"A"}, {"work"})
        self.assertEqual(st, {"A": "wait", "B": "unknown"})

    def test_failed_primary_account_reads_unknown_not_done(self):
        st = self.run_rows(False, {"/b": 1}, {"B"}, {""})
        self.assertEqual(st, {"A": "unknown", "B": "wait"})

    def test_answered_accounts_still_end_closed_sessions(self):
        st = self.run_rows(False, {"/a": 1}, {"A"}, set())
        self.assertEqual(st, {"A": "wait", "B": "done"})

    def test_mac_path_slot_keeps_row_alive(self):
        st = self.run_rows(True, {"/a": 1, "/b": 1}, set(), {"work"})
        self.assertEqual(st, {"A": "wait", "B": "wait"})


if __name__ == "__main__":
    unittest.main()
