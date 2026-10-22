"""arch_prov: arch map provenance captured from Sidereus' own session metadata (temp dirs; clock, transcript lookup,
Codex rollout lookup and account roots patched — no live files)."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

AP = sidereus("arch_prov")
AM = sidereus("arch_map")
AV = sidereus("arch_verify")
PL = sidereus("pl_runs")
W = sidereus("work")
CR = sidereus("claude_roots")
C1 = "c" * 40
T = 1_800_000_000.0
SID, SID2 = "aaaabbbb-1111-2222-3333-444455556666", "ccccdddd-1111-2222-3333-444455556666"
MODS, FLOWS, VER = "모듈 그리기", "흐름 그리기", "검증"


def _iso(t):
    import datetime
    return datetime.datetime.utcfromtimestamp(t).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _jl(fp, rows):
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    with open(fp, "w", encoding="utf-8") as f:
        f.write("".join(json.dumps(r) + "\n" for r in rows))


def _asst(t, model, body="secret body"):
    return {"type": "assistant", "timestamp": _iso(t), "message": {"model": model, "content": [{"type": "text", "text": body}]}}


class ProvTest(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sidereus-prov-"))
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.repo)
        self.sidereus = os.path.join(self.tmp, "sidereus")
        os.makedirs(self.sidereus)
        self.projects = os.path.join(self.tmp, "projects")
        self.plr = os.path.join(self.tmp, "plmark")
        os.makedirs(self.plr)
        self.paths = {}
        self.rollouts = {}
        self.p = [mock.patch.object(AP, "PROV_DIR", os.path.join(self.tmp, "prov")),
                  mock.patch.object(AP, "_now", lambda: T + 300),
                  mock.patch.object(AP, "_MISS", {}),
                  mock.patch.object(AP, "_rollout", lambda sid: self.rollouts.get(sid, "")),
                  mock.patch.object(PL, "PLR_DIR", self.plr),
                  mock.patch.object(W, "_sid_path", lambda cwd, sid: self.paths.get(sid, "")),
                  mock.patch.object(CR, "projects_dirs", lambda primary: [self.projects]),
                  mock.patch.object(AV, "ARCH_DIR", os.path.join(self.tmp, "arch")),
                  mock.patch.object(AM, "ARCH_DIR", os.path.join(self.tmp, "arch"))]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def runs_json(self, sid, t0, end, st, cwd=None):
        # Real shape: `proj` = pipeline owner (the Sidereus repo for every arch-map run), `cwd` = the session's folder.
        fp = os.path.join(self.plr, sid + ".runs.json")
        with open(fp, "w", encoding="utf-8") as f:
            json.dump({"v": 1, "runs": {"arch-map": {"cur": VER, "t0": t0, "t1": end, "end": end, "proj": self.sidereus,
                                                      "cwd": cwd or self.repo,
                                                      "st": {k: {"s": "done", "t0": a, "t1": b, "n": 1} for k, (a, b) in st.items()}}}}, f)
        os.utime(fp, (T + 250, T + 250))

    def cc_session(self, sid, agents, main=(("claude-opus-4-1-20250805", 0),)):
        """Main transcript + tagged subagents [(aid, stage, meta time, model)]."""
        fp = os.path.join(self.projects, "-slug", sid + ".jsonl")
        _jl(fp, [_asst(T + dt, m) for m, dt in main])
        sub = os.path.join(fp[:-6], "subagents")
        for aid, stage, mt, model in agents:
            _jl(os.path.join(sub, "agent-%s.jsonl" % aid), [_asst(mt, "<synthetic>")] + ([_asst(mt + 1, model)] if model else []))
            meta = os.path.join(sub, "agent-%s.meta.json" % aid)
            with open(meta, "w", encoding="utf-8") as f:
                json.dump({"toolUseId": "tu-" + aid, "agentType": "general", "description": "[pl:arch-map/%s] draw" % stage}, f)
            os.utime(meta, (mt, mt))
        self.paths[sid] = fp
        return fp

    def test_r1_claude_two_subagents_per_stage(self):
        # R1: stage models are observed in each subagent transcript; the verify stage ran in main (Opus).
        self.cc_session(SID, [("a1", MODS, T + 20, "claude-opus-4-1-20250805"), ("a2", FLOWS, T + 120, "claude-sonnet-4-5-20250929")])
        self.runs_json(SID, T, T + 210, {MODS: (T + 20, T + 100), FLOWS: (T + 120, T + 180), VER: (T + 190, T + 205)})
        row = {"sid": SID, "plat": "cc", "cwd": self.repo, "model": "opus-4-1"}
        out = AP.record(self.repo, C1, T + 200, row, T)
        got = AP.get(self.repo, C1, T + 200)
        self.assertEqual(got, out)
        self.assertEqual((got["plat"], got["sid"], got["model"]), ("cc", SID, "opus-4-1"))
        self.assertEqual(got["stages"], [{"t": MODS, "model": "opus-4-1"}, {"t": FLOWS, "model": "sonnet-4-5"},
                                         {"t": VER, "model": "opus-4-1"}])
        self.assertNotIn("secret body", json.dumps(got))
        fp = os.path.join(AP.PROV_DIR, AV.repo_key(self.repo), C1 + ".json")
        if os.name != "nt":   # ⚠Windows st_mode only reflects the read-only bit (0o666/0o444)
            self.assertEqual(os.stat(fp).st_mode & 0o777, 0o600)

    def test_r1_claude_same_model_collapses(self):
        self.cc_session(SID, [("a1", MODS, T + 20, "claude-sonnet-4-5"), ("a2", FLOWS, T + 120, "claude-sonnet-4-5")])
        out = AP.record(self.repo, C1, T + 200, {"sid": SID, "plat": "cc", "model": "opus-4-1"}, T)
        self.assertEqual((out["model"], out["stages"]), ("sonnet-4-5", []))

    def test_r1_codex_turn_context_by_stage_window(self):
        rp = os.path.join(self.tmp, "rollout-x-%s.jsonl" % SID)
        _jl(rp, [{"timestamp": _iso(T + 5), "type": "turn_context", "payload": {"model": "gpt-5-codex", "cwd": "/x"}},
                 {"timestamp": _iso(T + 50), "type": "response_item", "payload": {"model": "nope", "text": "body"}},
                 {"timestamp": _iso(T + 130), "type": "turn_context", "payload": {"model": "gpt-5"}}])
        self.rollouts[SID] = rp
        self.runs_json(SID, T, T + 210, {MODS: (T + 10, T + 100), FLOWS: (T + 110, T + 200)})
        out = AP.record(self.repo, C1, T + 200, {"sid": SID, "plat": "cx", "model": "gpt-5"}, T)
        self.assertEqual((out["plat"], out["model"]), ("cx", "gpt-5"))
        self.assertEqual(out["stages"], [{"t": MODS, "model": "gpt-5-codex"}, {"t": FLOWS, "model": "gpt-5"}])

    def test_r1_late_one_match_records(self):
        self.cc_session(SID, [])
        self.runs_json(SID, T, T + 210, {VER: (T + 190, T + 205)})
        got = AP.load_prov(self.repo, C1, T + 200)
        self.assertEqual((got["plat"], got["sid"], got["model"], got["stages"]), ("cc", SID, "opus-4-1", []))

    def test_r1_forged_prov_inside_store_ignored(self):
        # R1: a prov-shaped file the drawing agent wrote under S (or a `prov` key in map.json) is never read.
        s = os.path.join(AM.ARCH_DIR, AV.repo_key(self.repo), C1)
        os.makedirs(s)
        forged = {"v": 1, "plat": "cc", "sid": SID, "model": "forged", "stages": [], "at": T, "vt": T + 200}
        for name in ("prov.json", C1 + ".json"):
            with open(os.path.join(s, name), "w", encoding="utf-8") as f:
                json.dump(forged, f)
        self.assertIsNone(AP.load_prov(self.repo, C1, T + 200))

    def test_r1_window_not_covering_vt(self):
        self.cc_session(SID, [])
        self.runs_json(SID, T, T + 100, {VER: (T + 90, T + 100)})
        self.assertIsNone(AP.load_prov(self.repo, C1, T + 200))

    def test_r1_two_candidates_unknown(self):
        for sid in (SID, SID2):
            self.cc_session(sid, [])
            self.runs_json(sid, T, T + 210, {VER: (T + 190, T + 205)})
        self.assertIsNone(AP.load_prov(self.repo, C1, T + 200))

    def test_r1_verify_stage_session_wins(self):
        for sid, st in ((SID, {MODS: (T + 10, T + 100)}), (SID2, {VER: (T + 190, T + 205)})):
            self.cc_session(sid, [])
            self.runs_json(sid, T, T + 210, st)
        self.assertEqual(AP.load_prov(self.repo, C1, T + 200)["sid"], SID2)

    def test_r1_older_than_late_window(self):
        self.cc_session(SID, [])
        self.runs_json(SID, T, T + 210, {VER: (T + 190, T + 205)})
        self.assertIsNone(AP.load_prov(self.repo, C1, T + 200, now=T + 200 + AP.PROV_LATE_S + 1))

    def test_r1_sid_in_two_accounts_unknown(self):
        self.cc_session(SID, [])
        _jl(os.path.join(self.projects, "-other", SID + ".jsonl"), [_asst(T, "claude-haiku-4-5")])
        self.runs_json(SID, T, T + 210, {VER: (T + 190, T + 205)})
        self.assertIsNone(AP.load_prov(self.repo, C1, T + 200))

    def test_r1_runs_records_from_session_row(self):
        # R1: arch_map.runs() records when a tracked run ends with a verify.json newer than its t0.
        self.cc_session(SID, [])
        d = os.path.join(AM.ARCH_DIR, AV.repo_key(self.repo), C1)
        os.makedirs(d)
        with open(os.path.join(d, "verify.json"), "w", encoding="utf-8") as f:
            f.write("{}")
        os.utime(os.path.join(d, "verify.json"), (T + 200, T + 200))
        row = {"sid": SID, "plat": "cc", "cwd": self.repo, "model": "opus-4-1", "state": "think", "tool": "",
               "plm": {"name": "arch-map", "title": VER, "age": 100}, "plrun": []}
        seen = {self.repo: {"stage": VER, "sid": SID, "t0": T, "at": T + 100}}
        with mock.patch.object(AM, "_RUN_SEEN", seen), mock.patch.object(AM, "_titles", lambda: []), \
                mock.patch.object(AM, "_target", lambda s, now, pl="arch-map": (self.repo, 0.0)):
            AM.runs([row], now=T + 250)
        self.assertEqual(AP.get(self.repo, C1, T + 200)["sid"], SID)

    def test_r1_fallback_matches_non_sidereus_repo(self):
        # R1: the target is the session cwd (repo subfolder or its store dir), never runs.json `proj`.
        self.cc_session(SID, [])
        self.runs_json(SID, T, T + 210, {VER: (T + 190, T + 205)}, cwd=os.path.join(self.repo, "admin"))
        os.makedirs(os.path.join(self.repo, "admin"))
        self.assertEqual(AP.load_prov(self.repo, C1, T + 200)["sid"], SID)

    def test_r1_fallback_store_cwd_and_fail_closed(self):
        self.cc_session(SID, [])
        store = os.path.join(AV.ARCH_DIR, AV.repo_key(self.repo), C1)
        os.makedirs(store)
        self.runs_json(SID, T, T + 210, {VER: (T + 190, T + 205)}, cwd=store)
        self.assertEqual(AP.load_prov(self.repo, C1, T + 200)["sid"], SID)
        AP._MISS.clear()
        self.runs_json(SID, T, T + 210, {VER: (T + 190, T + 205)}, cwd=self.sidereus)   # cwd = pipeline owner only
        self.assertIsNone(AP.load_prov(self.repo, "d" * 40, T + 200))

    def test_r2_stage_agent_without_model_is_omitted(self):
        # R2: a stage whose agent wrote no model line is left out, not labelled with main's model.
        self.cc_session(SID, [("a1", MODS, T + 20, ""), ("a2", FLOWS, T + 120, "claude-sonnet-4-5")])
        self.runs_json(SID, T, T + 210, {MODS: (T + 20, T + 100), FLOWS: (T + 120, T + 180), VER: (T + 190, T + 205)})
        out = AP.record(self.repo, C1, T + 200, {"sid": SID, "plat": "cc", "model": "opus-4-1"}, T)
        self.assertEqual(out["stages"], [{"t": FLOWS, "model": "sonnet-4-5"}, {"t": VER, "model": "opus-4-1"}])

    def test_r1_runs_records_when_signs_are_gone(self):
        # R1: usual end — verify.json written, agent gone, plrun closed, marker cleared: no sign, the gap loop records.
        self.cc_session(SID, [])
        d = os.path.join(AM.ARCH_DIR, AV.repo_key(self.repo), C1)
        os.makedirs(d)
        with open(os.path.join(d, "verify.json"), "w", encoding="utf-8") as f:
            f.write("{}")
        os.utime(os.path.join(d, "verify.json"), (T + 200, T + 200))
        row = {"sid": SID, "plat": "cc", "cwd": self.repo, "model": "opus-4-1", "state": "wait", "tool": "",
               "plrun": [{"name": "arch-map", "end": T + 210, "t0": T, "t1": T + 210, "cur": VER}]}
        seen = {self.repo: {"stage": VER, "sid": SID, "t0": T, "at": T + 230}}
        with mock.patch.object(AM, "_RUN_SEEN", seen), mock.patch.object(AM, "_titles", lambda: []):
            self.assertEqual(AM.runs([row], now=T + 250), {})
        self.assertEqual(AP.get(self.repo, C1, T + 200)["sid"], SID)

    def cross(self, sid, agents, run):
        """Session in another repo: tagged agents [(aid, stage, t0, t1, model)], runs.json arch-map run or none."""
        other = os.path.join(self.tmp, "other-" + sid[:4])
        os.makedirs(other, exist_ok=True)
        fp = self.cc_session(sid, [(a, s, t0, m) for a, s, t0, _t1, m in agents])
        for a, _s, _t0, t1, _m in agents:
            os.utime(os.path.join(fp[:-6], "subagents", "agent-%s.jsonl" % a), (t1, t1))
        runs = {"arch-map": dict(run, cwd=other, proj=self.sidereus)} if run else {}
        rj = os.path.join(self.plr, sid + ".runs.json")
        with open(rj, "w", encoding="utf-8") as f:
            json.dump({"v": 1, "runs": runs}, f)
        os.utime(rj, (T + 250, T + 250))

    def req(self, asked):
        return lambda sid, pl, at: self.repo if sid in asked and pl == "arch-map" else ""

    def test_r3_cross_repo_open_run_late(self):
        # Case A: cwd is the requesting repo, run still open (end 0, t1 = verify stage start), verify.json a minute later.
        st = {MODS: {"s": "done", "t0": T + 20, "t1": T + 190, "n": 1}, VER: {"s": "run", "t0": T + 190, "t1": T + 190, "n": 1}}
        self.cross(SID, [("a1", MODS, T + 20, T + 180, "claude-opus-4-1"), ("a3", VER, T + 190, T + 262, "claude-sonnet-4-5")],
                   {"cur": VER, "t0": T, "t1": T + 190, "end": 0, "st": st})
        self.assertIsNone(AP.load_prov(self.repo, C1, T + 250))   # no request source: cwd alone never matches
        AP._MISS.clear()
        got = AP.load_prov(self.repo, C1, T + 250, req=self.req({SID}))
        self.assertEqual((got["sid"], got["stages"]), (SID, [{"t": MODS, "model": "opus-4-1"}, {"t": VER, "model": "sonnet-4-5"}]))

    def test_r3_cross_repo_no_run_uses_tagged_agents(self):
        # Case B: the session's own pipelines kept no arch-map run; an older run's agent past the gap is not counted.
        self.cross(SID, [("a0", MODS, T - 5000, T - 4900, "claude-haiku-4-5"), ("a1", MODS, T + 20, T + 180, "claude-opus-4-1"),
                         ("a3", VER, T + 190, T + 262, "claude-sonnet-4-5")], None)
        self.cross(SID2, [("b1", VER, T + 190, T + 262, "claude-haiku-4-5")], None)   # same time, never asked
        got = AP.load_prov(self.repo, C1, T + 250, req=self.req({SID}))
        self.assertEqual((got["sid"], got["stages"]), (SID, [{"t": MODS, "model": "opus-4-1"}, {"t": VER, "model": "sonnet-4-5"}]))

    def test_r3_unrequested_other_repo_not_credited(self):
        st = {VER: {"s": "run", "t0": T + 190, "t1": T + 190, "n": 1}}
        self.cross(SID2, [("b1", VER, T + 190, T + 262, "claude-haiku-4-5")], {"cur": VER, "t0": T, "t1": T + 190, "end": 0, "st": st})
        self.assertIsNone(AP.load_prov(self.repo, C1, T + 250, req=self.req({SID})))


if __name__ == "__main__":
    unittest.main()
