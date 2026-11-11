"""pi session-file reader (sidereus/plat_pi.py): header fields (R1), token tuples and model (R2), bad input (R4)."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from tests._load import sidereus

pi = sidereus("plat_pi")
st = sidereus("ext_store")

SID = "0199aaaa-bbbb-7ccc-8ddd-0000000000c1"
T0 = 1791162000.0      # 2026-10-05T01:00:00Z


def _iso(t):
    import datetime
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def head(sid=SID, cwd="/w/my-proj"):
    return {"type": "session", "version": 3, "id": sid, "timestamp": _iso(T0), "cwd": cwd}


def asst(eid, dt, prov="anthropic", model="claude-sonnet-4-5", usage=None, ms=True):
    u = {"input": 1000, "output": 200, "cacheRead": 400, "cacheWrite": 100, "totalTokens": 1700,
         "cost": {"total": 0.25}} if usage is None else usage
    m = {"role": "assistant", "content": [{"type": "text", "text": "x"}], "provider": prov, "model": model, "usage": u}
    if ms:
        m["timestamp"] = int((T0 + dt) * 1000)
    return {"type": "message", "id": eid, "timestamp": _iso(T0 + dt), "message": m}


class PiBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-pi-")
        self.root = os.path.join(self.tmp, "agent")
        self.sess = os.path.join(self.root, "sessions")
        os.makedirs(self.sess)
        self.p = [mock.patch.object(pi, "root", lambda: self.root)]
        for p in self.p:
            p.start()
        pi._cache.clear()

    def tearDown(self):
        for p in self.p:
            p.stop()
        pi._cache.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, lines, folder="--w-my-proj--", sid=SID, raw=False):
        d = os.path.join(self.sess, folder)
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "2026-10-05T01-00-00-000Z_%s.jsonl" % sid)
        with open(p, "w", encoding="utf-8") as f:
            for ln in lines:
                f.write((ln if raw and isinstance(ln, str) else json.dumps(ln)) + "\n")
        return p


class R1Header(PiBase):
    def test_r1_header_fields_not_folder(self):
        # folder name says /Users/x/my/proj, the header says /w/my-proj: cwd comes from the header only
        p = self.write([head(), asst("a1", 2)], folder="--Users-x-my-proj--")
        rows = pi.scan(0.0)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r["sid"], r["cwd"], r["path"], r["kind"]), (SID, "/w/my-proj", p, ""))
        self.assertEqual(r["project"], "my-proj")
        self.assertEqual(r["start"], T0)
        self.assertIn("mtime", r)

    def test_r1_bad_header_id_uses_file_name(self):
        self.write([head(sid="bad/id"), asst("a1", 2)])
        self.assertEqual([r["sid"] for r in pi.scan(0.0)], [SID])

    def test_r1_one_by_sid(self):
        self.write([head(), asst("a1", 2)])
        self.assertEqual(pi.one(SID)["cwd"], "/w/my-proj")
        self.assertIsNone(pi.one("nope"))
        self.assertIsNone(pi.one("../x"))

    def test_sid_rule_matches_ext_store(self):
        for s in ("", "a", "a-b_c", "a/b", "a b", "x" * 64, "x" * 65, "..", "é1"):
            self.assertEqual(pi._sid_ok(s), st._sid_ok(s), s)


class R2Tokens(PiBase):
    def test_r2_assistant_tuple(self):
        self.write([head(), {"type": "model_change", "id": "c1", "timestamp": _iso(T0 + 1),
                             "provider": "openai", "modelId": "gpt-5"}, asst("a1", 2)])
        r = pi.scan(0.0)[0]
        self.assertEqual(r["msgs"]["a1"], (1000, 200, 500, 0, T0 + 2, "anthropic/claude-sonnet-4-5", 0.25))
        self.assertEqual(r["model"], "anthropic/claude-sonnet-4-5")       # assistant line is later than the change
        self.assertEqual(r["acts"], {"a1": T0 + 2})

    def test_r2_usage_compaction_branch_entries(self):
        u = {"input": 5, "output": 6, "cacheRead": 7, "cacheWrite": 8}            # no cost
        self.write([head(), asst("a1", 2),
                    {"type": "usage", "id": "w1", "timestamp": _iso(T0 + 3), "provider": "google", "model": "g-1",
                     "usage": dict(u, cost={"total": 0.5})},
                    {"type": "compaction", "id": "k1", "timestamp": _iso(T0 + 4), "summary": "s", "usage": u},
                    {"type": "branch_summary", "id": "b1", "timestamp": _iso(T0 + 5), "summary": "s", "usage": u},
                    {"type": "compaction", "id": "k2", "timestamp": _iso(T0 + 6), "summary": "s"}])
        m = pi.scan(0.0)[0]["msgs"]
        self.assertEqual(m["u:w1"], (5, 6, 15, 0, T0 + 3, "google/g-1", 0.5))
        self.assertEqual(m["u:k1"], (5, 6, 15, 0, T0 + 4, "anthropic/claude-sonnet-4-5", None))
        self.assertEqual(m["u:b1"][6], None)
        self.assertNotIn("u:k2", m)

    def test_r2_missing_cost_and_bad_counts(self):
        self.write([head(), asst("a1", 2, usage={"input": -3, "output": "9", "cacheRead": True,
                                                 "cost": {"total": float("inf")}}, ms=False)])
        self.assertEqual(pi.scan(0.0)[0]["msgs"]["a1"], (0, 0, 0, 0, T0 + 2, "anthropic/claude-sonnet-4-5", None))

    def test_r2_model_change_switches_model(self):
        self.write([head(), asst("a1", 2), {"type": "model_change", "id": "c1", "timestamp": _iso(T0 + 3),
                                            "provider": "openai", "modelId": "gpt-5"}])
        self.assertEqual(pi.scan(0.0)[0]["model"], "openai/gpt-5")

    def test_r2_fork_counts_only_new_entries(self):
        parent = [head(), asst("a1", 2), {"type": "usage", "id": "w1", "timestamp": _iso(T0 + 3),
                                          "usage": {"input": 1, "output": 1}},
                  {"type": "message", "id": "t1", "timestamp": _iso(T0 + 4), "message": {
                      "role": "toolResult", "toolName": "bash", "timestamp": int((T0 + 4) * 1000)}}]
        pp = self.write(parent)
        h2 = dict(head(sid="fork-1"), timestamp=_iso(T0 + 100), parentSession=pp)
        self.write([h2] + parent[1:] + [asst("a9", 120, model="m2")], folder="--fork--", sid="fork-1")
        rows = {r["sid"]: r for r in pi.scan(0.0)}
        self.assertEqual(set(rows[SID]["msgs"]), {"a1", "u:w1"})       # parent unchanged
        self.assertEqual(rows[SID]["tools"], [(T0 + 4, "bash")])
        f = rows["fork-1"]
        self.assertEqual(set(f["msgs"]), {"a9"})
        self.assertEqual((set(f["acts"]), f["tools"], f["model"]), ({"a9"}, [], "anthropic/m2"))

    def test_r2_session_msgs(self):
        p = self.write([head(), asst("a1", 2)])
        self.assertEqual(set(pi.session_msgs(p)), {"a1"})
        self.assertIsNone(pi.session_msgs(os.path.join(self.tmp, "x.jsonl")))


class Who5h(PiBase):
    def test_who_5h_anthropic_only_inside_window(self):
        self.write([head(), asst("a0", -50), asst("a1", 2), asst("a2", 3, prov="openai", model="gpt-5"),
                    asst("a3", 4, prov="github-copilot", model="claude-x"), asst("a4", 500)])
        w = pi.who_5h(T0, T0 + 100)
        self.assertEqual(w, {"my-proj": {"tok": 1700, "sids": {SID: 1700}}})   # a0 before start, a4 after now

    def test_who_5h_fork_counts_only_new_entries(self):
        parent = [head(), asst("a1", 2)]
        pp = self.write(parent)
        h2 = dict(head(sid="fork-1"), timestamp=_iso(T0 + 100), parentSession=pp)
        self.write([h2] + parent[1:] + [asst("a9", 120)], folder="--fork--", sid="fork-1")
        w = pi.who_5h(T0, T0 + 200)
        self.assertEqual(w["my-proj"], {"tok": 3400, "sids": {SID: 1700, "fork-1": 1700}})

    def test_who_5h_empty(self):
        self.assertEqual(pi.who_5h(T0, T0 + 100), {})


class R4Robust(PiBase):
    def test_r4_bad_lines_skipped(self):
        self.write([head(), "{not json", "[1,2]", "null",
                    {"type": "message", "id": "m", "message": "str"},
                    {"type": "message", "id": 5, "message": {"role": "assistant", "usage": []}},
                    {"type": "message", "id": "t", "message": {"role": "toolResult", "toolName": "rm -rf /"}},
                    asst("a1", 2)], raw=True)
        r = pi.scan(0.0)[0]
        self.assertEqual(set(r["msgs"]), {"a1"})
        self.assertEqual(r["tools"], [])

    def test_r4_oversize_symlink_and_non_session_skipped(self):
        self.write([head(), asst("a1", 2)])
        self.write([head(sid="big-1")] + [asst("a%d" % i, i) for i in range(40)], folder="--big--", sid="big-1")
        self.write([{"type": "message", "id": "x"}, asst("a1", 2)], folder="--nohead--", sid="nohead-1")
        self.write([], folder="--empty--", sid="empty-1")
        out = os.path.join(self.tmp, "outside")
        os.makedirs(out)
        src = os.path.join(out, "2026_esc-1.jsonl")
        with open(src, "w", encoding="utf-8") as f:
            f.write(json.dumps(head(sid="esc-1")) + "\n")
        os.makedirs(os.path.join(self.sess, "--esc--"))
        link = os.path.join(self.sess, "--esc--", "2026_esc-1.jsonl")
        os.symlink(src, link)
        with mock.patch.object(pi, "SCAN_MAX", 4096):
            self.assertEqual([r["sid"] for r in pi.scan(0.0)], [SID])
            self.assertIsNone(pi.session_msgs(link))
            self.assertFalse(pi.path_ok(link))

    def test_r4_symlinked_root_still_reads(self):
        self.write([head(), asst("a1", 2)])
        alias = os.path.join(self.tmp, "alias")
        os.symlink(self.root, alias)
        with mock.patch.object(pi, "root", lambda: alias):
            self.assertEqual([r["sid"] for r in pi.scan(0.0)], [SID])

    def test_r4_since_filter_and_missing_root(self):
        p = self.write([head(), asst("a1", 2)])
        os.utime(p, (T0, T0))
        self.assertEqual(pi.scan(T0 + 1), [])
        shutil.rmtree(self.sess)
        self.assertEqual(pi.scan(0.0), [])



class R1Rev(PiBase):
    """ext_rev (sha256[:12] of the template) and installed_rev (REV read from extensions/sidereus.ts)."""

    def setUp(self):
        super().setUp()
        pi._rev_memo.clear()
        self.addCleanup(pi._rev_memo.clear)
        self.tpl = os.path.join(self.tmp, "pi-extension.ts")
        with open(self.tpl, "wb") as f:
            f.write(b'const REV: string = "<SIDEREUS_REV>";\n')
        self.inst = os.path.join(self.root, "extensions", "sidereus.ts")
        os.makedirs(os.path.dirname(self.inst))

    def put(self, text, path=None):
        with open(path or self.inst, "w", encoding="utf-8") as f:
            f.write(text)

    def test_r1_ext_rev_is_sha_prefix_and_follows_edits(self):
        import hashlib
        want = hashlib.sha256(b'const REV: string = "<SIDEREUS_REV>";\n').hexdigest()[:12]
        self.assertEqual(pi.ext_rev(self.tpl), want)
        self.assertTrue(pi.REV_HEX.fullmatch(want))
        self.put("// changed template, other size\n", self.tpl)
        self.assertNotEqual(pi.ext_rev(self.tpl), want)

    def test_r1_ext_rev_default_path_and_missing(self):
        os.makedirs(os.path.join(self.tmp, "ext-hooks"))
        shutil.copy(self.tpl, os.path.join(self.tmp, "ext-hooks", "pi-extension.ts"))
        with mock.patch.object(pi.config, "ASSET_DIR", self.tmp):
            self.assertEqual(pi.ext_rev(), pi.ext_rev(self.tpl))
        self.assertIsNone(pi.ext_rev(os.path.join(self.tmp, "nope.ts")))

    def test_r2_installed_rev(self):
        self.assertIsNone(pi.installed_rev())                       # missing
        self.put('// x\nconst REV: string = "0123456789ab";\n')
        self.assertEqual(pi.installed_rev(), "0123456789ab")
        self.put('const REV: string = "<SIDEREUS_REV>";\n')     # unrendered / pre-rev copy
        self.assertIsNone(pi.installed_rev())
        self.put('const REV: string = "0123456789AB";\n')
        self.assertIsNone(pi.installed_rev())

    def test_r2_installed_rev_bounded_read(self):
        with mock.patch.object(pi, "REV_READ_MAX", 64):
            self.put("/" * 100 + '\nconst REV: string = "0123456789ab";\n')
            self.assertIsNone(pi.installed_rev())

    def test_r2_installed_rev_symlink_out_of_root_refused(self):
        out = os.path.join(self.tmp, "elsewhere.ts")
        self.put('const REV: string = "0123456789ab";\n', out)
        os.symlink(out, self.inst)
        self.assertIsNone(pi.installed_rev())

    def test_r2_installed_rev_symlinked_root_resolved(self):
        self.put('const REV: string = "0123456789ab";\n')
        alias = os.path.join(self.tmp, "alias")
        os.symlink(self.root, alias)
        with mock.patch.object(pi, "root", lambda: alias):
            self.assertEqual(pi.installed_rev(), "0123456789ab")


if __name__ == "__main__":
    unittest.main()
