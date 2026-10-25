"""«도구» usage index (sidereus/toolidx.py): keys, toolu dedup, day window, counts only.
Fixture transcripts live in a temp dir; toolidx.CLAUDE_PROJECTS is patched (never the live ~/.claude)."""
import json
import os
import shutil
import tempfile
import unittest

from tests._load import load, sidereus

load()
ti = sidereus("toolidx")
SECRET = "SECRET-INPUT-do-not-keep"
NOW = 1_800_000_000.0


def _iso(ts):
    import datetime
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _tu(tid, name, inp, ts):
    return {"type": "assistant", "timestamp": _iso(ts),
            "message": {"content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}]}}


def _ent_text(ent):
    """Every string an index entry holds (events are numeric arrays; keys live in the shared table)."""
    from array import array
    return json.dumps([ti._TI_KEYS, dict((k, v) for k, v in ent.items() if not isinstance(v, array))])


class ToolIdxTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sidereus-ti-")
        self.saved = ti.CLAUDE_PROJECTS
        self.saved_knobs = (ti.TI_BG, ti.TI_BUDGET, ti.TI_CHUNK_MIN)
        ti.CLAUDE_PROJECTS = self.tmp
        ti.TI_BG = False
        ti.reset()
        d = NOW - 86400
        main = [_tu("toolu_1", "mcp__docs__search", {"q": SECRET}, d),
                _tu("toolu_2", "Skill", {"skill": "ship", "args": SECRET}, d),
                _tu("toolu_3", "Agent", {"subagent_type": "reviewer", "prompt": SECRET}, d),
                _tu("toolu_4", "Task", {"prompt": SECRET}, d),
                _tu("toolu_5", "Bash", {"command": SECRET}, d),
                _tu("toolu_6", "mcp__docs__fetch", {}, NOW - 10 * 86400),
                _tu("toolu_7", "mcp__old__x", {}, NOW - 40 * 86400),
                {"type": "user", "uuid": "u-1", "timestamp": _iso(d),
                 "message": {"content": "<command-name>/deploy</command-name><command-args>%s</command-args>" % SECRET}},
                _tu("toolu_1", "mcp__docs__search", {}, d)]          # same id repeated: counted once
        self._write(os.path.join(self.tmp, "-proj", "s1.jsonl"), main)
        self._write(os.path.join(self.tmp, "-proj", "s1", "subagents", "agent-a.jsonl"),
                    [_tu("toolu_1", "mcp__docs__search", {}, d), _tu("toolu_9", "mcp__docs__search", {}, d)])

    def tearDown(self):
        ti.CLAUDE_PROJECTS = self.saved
        ti.TI_BG, ti.TI_BUDGET, ti.TI_CHUNK_MIN = self.saved_knobs
        ti.reset()
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def _write(p, recs, mode="w"):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, mode, encoding="utf-8") as f:
            for r in recs:
                f.write(json.dumps(r) + "\n")
            f.write('{"type":"assistant","partial')          # incomplete tail line: not read yet
        os.utime(p, (NOW - 60, NOW - 60))                     # mtime inside the window (no clock read)

    def test_keys_and_dedup(self):
        u = ti.tool_uses(30, now=NOW)
        self.assertEqual({k: v["n"] for k, v in u.items() if not k.startswith("tool:")},
                         {"mcp:docs": 3, "skill:ship": 1, "agent:reviewer": 1, "agent:general-purpose": 1, "cmd:deploy": 1})
        self.assertEqual(u["skill:ship"]["last"], int(NOW - 86400))

    def test_warm_noop_without_bg(self):
        ti.warm(now=NOW)
        self.assertEqual((ti._TI_RES, ti._TI_MCP, ti._TI_FILES), ({}, {}, {}))

    def test_warm_fills_30_day_caches(self):
        ti.TI_BG, ti.TI_BUDGET, ti.TI_CHUNK_MIN = True, 64, 16      # tiny slices: warm loops until caught up
        ti.warm(now=NOW)
        self.assertFalse(ti.scanning())
        self.assertIn(30, ti._TI_RES)
        self.assertIn(30, ti._TI_MCP)
        orig = ti._refresh

        def boom(*a, **k):
            raise AssertionError("cached result expected")
        ti._refresh = boom
        try:
            self.assertEqual(ti.tool_uses(30, now=NOW + 1)["mcp:docs"]["n"], 3)
        finally:
            ti._refresh = orig

    def test_warm_blocks_second_kick(self):
        ti.TI_BG = True
        orig, seen = ti._bg_warm, []
        ti._bg_warm = lambda at=None: (ti._kick(), seen.append(ti._TI_STATE["bg"]))
        try:
            ti.warm(now=NOW)
        finally:
            ti._bg_warm = orig
        import threading
        self.assertEqual(seen, [threading.current_thread()])

    def test_kick_while_warm_queued_scans_once(self):
        import contextlib
        import threading
        ti.TI_BG = True
        go, runs, kicked = threading.Event(), [], []
        saved = (ti._bg_warm, ti.tool_uses, ti.mcp_status, ti.boot_queue.gate)

        def fake_bg(at=None):
            go.wait(1)
            runs.append(threading.current_thread().name)

        @contextlib.contextmanager
        def queued(name):                               # a request kicks while warm still waits for its turn
            ti._kick()
            k = ti._TI_STATE["bg"]
            kicked.append(k)
            orig_join = k.join
            k.join = lambda *a: (go.set(), orig_join(*a))   # release the kicked scan only once warm waits on it
            yield
        ti._bg_warm, ti.tool_uses, ti.mcp_status, ti.boot_queue.gate = fake_bg, lambda *a: {}, lambda *a: {}, queued
        try:
            ti.warm(now=NOW)
        finally:
            go.set()
            for k in kicked:
                k.__dict__.pop("join", None)            # ⚠before the fix this is the main thread: never leave it patched
            ti._bg_warm, ti.tool_uses, ti.mcp_status, ti.boot_queue.gate = saved
        self.assertEqual(runs, ["toolidx-warm"])

    def test_day_window(self):
        self.assertEqual(ti.tool_uses(7, now=NOW)["mcp:docs"]["n"], 2)
        self.assertNotIn("mcp:old", ti.tool_uses(30, now=NOW))
        self.assertEqual(ti.tool_uses(90, now=NOW + 1000)["mcp:old"]["n"], 1)

    def test_counts_only(self):
        blob = json.dumps(ti.tool_uses(90, now=NOW))
        self.assertNotIn(SECRET, blob)
        for ent in ti._TI_FILES.values():
            self.assertNotIn(SECRET, _ent_text(ent))

    def test_hook_runs(self):
        d = NOW - 86400

        def att(u, typ, name):
            return {"type": "attachment", "uuid": u, "timestamp": _iso(d),
                    "attachment": {"type": typ, "hookName": name, "hookEvent": name.split(":")[0], "exitCode": 0,
                                   "content": SECRET, "stdout": SECRET, "stderr": SECRET, "command": SECRET}}
        self._write(os.path.join(self.tmp, "-proj", "s2.jsonl"), [
            att("h1", "hook_success", "PreToolUse:Bash"), att("h2", "hook_success", "PreToolUse:Bash"),
            att("h1", "hook_success", "PreToolUse:Bash"),                       # same uuid: counted once
            att("h3", "hook_additional_context", "UserPromptSubmit"),
            att("h4", "hook_error", "Stop"),                                    # not a counted type
            {"type": "system", "subtype": "stop_hook_summary", "uuid": "h5", "timestamp": _iso(d),
             "hookAdditionalContext": SECRET, "hookName": "Stop"}])
        u = ti.tool_uses(30, now=NOW)
        self.assertEqual(u["hook:PreToolUse:Bash"]["n"], 2)
        self.assertEqual(u["hookctx:UserPromptSubmit"]["n"], 1)
        self.assertFalse([k for k in u if "Stop" in k])
        self.assertEqual(u["hookc:PreToolUse:Bash#" + ti.hook_hash(SECRET)]["n"], 2)   # per-command key: hash only
        self.assertFalse([k for k in u if k.startswith("hookc:UserPromptSubmit")])    # ctx records: no command key
        self.assertNotIn(SECRET, json.dumps(u))
        for ent in ti._TI_FILES.values():
            self.assertNotIn(SECRET, _ent_text(ent))

    def test_mcp_status(self):
        d = NOW - 86400

        def failed(ts, *srv):
            return {"type": "attachment", "uuid": "f%d" % ts, "timestamp": _iso(ts),
                    "attachment": {"type": "deferred_tools_delta", "addedNames": [], "pendingMcpServers": ["p"],
                                   "failedMcpServers": [dict(s, error=SECRET) for s in srv]}}
        self._write(os.path.join(self.tmp, "-proj", "s3.jsonl"), [
            failed(d - 1000, {"name": "docs", "errorCode": "CONNECTION_CLOSED"}),    # docs: failure, then calls (s1) later
            failed(d - 100, {"name": "late", "errorCode": "x" + SECRET}),      # late: call first, then failure
            _tu("toolu_30", "mcp__late__q", {}, d - 200), failed(d - 50, {"name": "late", "errorCode": "CONNECT_TIMEOUT"}),
            failed(d, {"name": "claude.ai Docs"})])                              # no code; name -> tool-prefix form
        ti.tool_uses(30, now=NOW)                                                # mcp_status reads what tool_uses indexed
        st = ti.mcp_status(30, now=NOW)
        self.assertEqual(st["mcp:docs"]["status"], "ok")
        self.assertEqual((st["mcp:late"]["status"], st["mcp:late"]["err"], st["mcp:late"]["fail_at"]),
                         ("fail", "CONNECT_TIMEOUT", int(d - 50)))
        self.assertEqual((st["mcp:claude_ai_Docs"]["status"], st["mcp:claude_ai_Docs"]["err"]), ("fail", ""))
        self.assertNotIn("mcp:none", st)
        self.assertNotIn(SECRET, json.dumps(st))
        for ent in ti._TI_FILES.values():
            self.assertNotIn(SECRET, _ent_text(ent))

    def test_mcp_status_latest_session(self):
        d = NOW - 86400
        self._write(os.path.join(self.tmp, "-proj", "s4.jsonl"), [
            _tu("toolu_40", "mcp__web__a", {}, d - 500),
            {"type": "attachment", "timestamp": _iso(d - 400), "attachment": {"type": "deferred_tools_delta",
                                                                              "failedMcpServers": [{"name": "web", "errorCode": "E"}]}}])
        self._write(os.path.join(self.tmp, "-proj", "s5.jsonl"), [_tu("toolu_41", "mcp__web__a", {}, d - 300)])
        ti.tool_uses(30, now=NOW)
        self.assertEqual(ti.mcp_status(30, now=NOW)["mcp:web"]["status"], "ok")   # a later call clears an older failure

    def test_tool_names(self):
        u = ti.tool_uses(30, now=NOW)
        self.assertEqual(sorted(k for k in u if k.startswith("tool:")),
                         ["tool:Agent", "tool:Bash", "tool:Skill", "tool:Task", "tool:mcp__docs__fetch", "tool:mcp__docs__search"])
        self.assertNotIn("tool:mcp__old__x", u)                                   # each call by its own timestamp
        self.assertEqual(u["tool:mcp__docs__search"]["n"], 2)   # toolu_1 in two files (and twice in one) counts once

    def test_mcp_connect_clears_failure(self):
        d = NOW - 86400

        def delta(ts, added, failed):
            return {"type": "attachment", "timestamp": _iso(ts), "attachment": {
                "type": "deferred_tools_delta", "addedNames": added, "failedMcpServers": [{"name": n} for n in failed]}}
        self._write(os.path.join(self.tmp, "-p2", "a.jsonl"), [delta(d - 900, ["Bash"], ["chrome", "dead"])])
        self._write(os.path.join(self.tmp, "-p2", "b.jsonl"), [delta(d - 100, ["mcp__chrome__click", "Read"], ["dead"])])
        ti.tool_uses(30, now=NOW)
        st = ti.mcp_status(30, now=NOW)
        self.assertEqual(st["mcp:chrome"]["status"], "ok")      # failed, later connected (tools added), never called
        self.assertEqual(st["mcp:dead"]["status"], "fail")      # failure only

    def test_incremental_append(self):
        ti.tool_uses(30, now=NOW)
        p = os.path.join(self.tmp, "-proj", "s1.jsonl")
        with open(p, "a", encoding="utf-8") as f:
            f.write("\n" + json.dumps(_tu("toolu_20", "Skill", {"skill": "ship"}, NOW - 60)) + "\n")
        os.utime(p, (NOW - 30, NOW - 30))
        self.assertEqual(ti.tool_uses(30, now=NOW + 100)["skill:ship"]["n"], 2)

    def _swr(self):
        """TI_BG on, `_spawn` captured (no thread), merges counted; returns (spawned, merges)."""
        spawned, merges, saved = [], [], (ti._spawn, ti._merged)
        ti._spawn = lambda target, args: spawned.append((target, args))
        ti._merged = lambda: merges.append(1) or saved[1]()
        self.addCleanup(setattr, ti, "_spawn", saved[0])
        self.addCleanup(setattr, ti, "_merged", saved[1])
        ti.TI_BG = True
        return spawned, merges

    def test_swr_expired_returns_stale_and_one_refresh(self):
        old = ti.tool_uses(30, now=NOW)
        spawned, merges = self._swr()
        p = os.path.join(self.tmp, "-proj", "s1.jsonl")
        with open(p, "a", encoding="utf-8") as f:
            f.write("\n" + json.dumps(_tu("toolu_20", "Skill", {"skill": "ship"}, NOW - 60)) + "\n")
        os.utime(p, (NOW - 30, NOW - 30))
        later = NOW + ti.TI_TTL_S + 1
        self.assertIs(ti.tool_uses(30, now=later), old)                   # stale, no merge on the caller
        self.assertIs(ti.tool_uses(30, now=later + 1), old)               # second caller: no second pass
        self.assertEqual((len(spawned), merges), (1, []))
        target, args = spawned[0]
        target(*args)
        self.assertFalse(ti._TI_STATE["rv"])
        self.assertEqual(ti.tool_uses(30, now=later + 2)["skill:ship"]["n"], 2)   # refreshed result, fresh hit
        self.assertEqual((len(spawned), len(merges)), (1, 1))

    def test_swr_concurrent_one_refresh(self):
        import threading
        ti.tool_uses(30, now=NOW)
        spawned, _m = self._swr()
        later = NOW + ti.TI_TTL_S + 1
        ts = [threading.Thread(target=ti.tool_uses, args=(30, later)) for _ in range(8)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(len(spawned), 1)

    def test_swr_beyond_stale_max_is_sync(self):
        old = ti.tool_uses(30, now=NOW)
        spawned, merges = self._swr()
        got = ti.tool_uses(30, now=NOW + ti.TI_STALE_MAX_S + 1)
        self.assertIsNot(got, old)
        self.assertEqual((spawned, len(merges), got["mcp:docs"]["n"]), ([], 1, 3))

    def test_mcp_status_busy_lock_returns_cached(self):
        ti.tool_uses(30, now=NOW)
        first = ti.mcp_status(30, now=NOW)
        self.assertIn("mcp:docs", first)
        ti._TI_LOCK.acquire()                       # a revalidate holding the lock
        try:
            self.assertIs(ti.mcp_status(30, now=NOW + ti.TI_TTL_S + 1), first)   # expired, busy: no wait
        finally:
            ti._TI_LOCK.release()
        again = ti.mcp_status(30, now=NOW + ti.TI_TTL_S + 2)                     # lock free: recomputed
        self.assertIsNot(again, first)
        self.assertEqual(again, first)

    def test_mcp_status_no_cache_computes(self):
        ti.tool_uses(30, now=NOW)
        self.assertEqual(ti._TI_MCP, {})
        self.assertEqual(ti.mcp_status(30, now=NOW)["mcp:docs"]["status"], "ok")
        self.assertIn(30, ti._TI_MCP)

    def test_swr_no_prior_result_is_sync(self):
        spawned, merges = self._swr()
        self.assertEqual(ti.tool_uses(30, now=NOW)["mcp:docs"]["n"], 3)
        self.assertEqual((spawned, len(merges)), ([], 1))

    def test_budget_partial_then_complete(self):
        ti.TI_BUDGET, ti.TI_CHUNK_MIN = 300, 1
        first = ti.tool_uses(30, now=NOW)
        self.assertTrue(ti.scanning())
        self.assertLess(sum(v["n"] for v in first.values()), 7)
        for _ in range(50):
            u = ti.tool_uses(30, now=NOW)
            if not ti.scanning():
                break
        self.assertFalse(ti.scanning())
        self.assertEqual(u["mcp:docs"]["n"], 3)

    def test_scanning_flag_in_route(self):
        rg = sidereus("routes_get")
        saved = (rg.scan_items, rg.tools_scanning)
        rg.scan_items, rg.tools_scanning = (lambda d: []), (lambda: True)
        got = {}
        h = rg._GetRoutes()
        h._raw_json = lambda code, out: got.update(code=code, out=out)
        try:
            h._g_tools(_U("days=30"))
        finally:
            rg.scan_items, rg.tools_scanning = saved
        self.assertEqual((got["code"], got["out"]["scanning"], got["out"]["items"]), (200, True, []))

    def test_route_registered(self):
        cs = load()
        self.assertEqual(cs.Handler._GET_ROUTES["/api/tools"].__name__, "_g_tools")
        self.assertEqual(cs.Handler._GET_ROUTES["/api/tools/file"].__name__, "_g_tools_file")
        self.assertNotIn("/api/tools/trash", cs.Handler._GET_ROUTES)


class _U(object):
    def __init__(self, q):
        self.query = q


if __name__ == "__main__":
    unittest.main()


class ToolIdxDiskTest(unittest.TestCase):
    """toolidx-cache.json: a restart resumes from saved offsets instead of rescanning (paths are temp files)."""
    _write = staticmethod(ToolIdxTest._write)

    def setUp(self):
        ToolIdxTest.setUp(self)
        self.saved_disk = (ti.TI_CACHE, ti._TI_ROOT)
        ti.TI_CACHE = os.path.join(self.tmp, "cache.json")
        ti._TI_ROOT = self.tmp
        self.want = {k: v["n"] for k, v in ti.tool_uses(30, now=NOW).items()}

    def tearDown(self):
        ti.TI_CACHE, ti._TI_ROOT = self.saved_disk
        ToolIdxTest.tearDown(self)

    def _restart_counting_scans(self):
        ti.reset()
        calls, real = [], ti._scan_file
        ti._scan_file = lambda *a: calls.append(a[0]) or real(*a)
        try:
            got = {k: v["n"] for k, v in ti.tool_uses(30, now=NOW).items()}
        finally:
            ti._scan_file = real
        return got, calls

    def test_restart_resumes_without_rescan(self):
        self.assertTrue(os.path.exists(ti.TI_CACHE))
        got, calls = self._restart_counting_scans()
        self.assertEqual((got, calls), (self.want, []))

    def test_appended_tail_only(self):
        p = os.path.join(self.tmp, "-proj", "s1.jsonl")
        with open(p, "a", encoding="utf-8") as f:      # close the fixture's partial tail line, then one new record
            f.write("\n" + json.dumps(_tu("toolu_20", "Skill", {"skill": "ship"}, NOW - 3600)) + "\n")
        os.utime(p, (NOW - 30, NOW - 30))
        got, calls = self._restart_counting_scans()
        self.assertEqual(calls, [p])
        self.assertEqual(got["skill:ship"], 2)

    def test_malformed_cache_rescans(self):
        with open(ti.TI_CACHE, "w", encoding="utf-8") as f:
            f.write("{not json")
        warned, real = [], ti.warn_once
        ti.warn_once = lambda k, *a, **kw: warned.append(k)   # capture: the warning is expected, keep stderr clean
        try:
            got, calls = self._restart_counting_scans()
        finally:
            ti.warn_once = real
        self.assertEqual(got, self.want)
        self.assertEqual(len(calls), 2)
        self.assertEqual(warned, ["toolidx-cache"])

    def test_bad_typed_entry_dropped(self):
        with open(ti.TI_CACHE, encoding="utf-8") as f:
            lines = f.read().splitlines()
        p = os.path.join(self.tmp, "-proj", "s1.jsonl")
        for i, ln in enumerate(lines[1:], 1):
            row = json.loads(ln)
            if row[0] == p:
                row[5] = "not base64!"
                row[7]["mcp:x"] = "bad"
                lines[i] = json.dumps(row)
        with open(ti.TI_CACHE, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        warned, real = [], ti.warn_once
        ti.warn_once = lambda k, *a, **kw: warned.append(k)
        try:
            got, calls = self._restart_counting_scans()
        finally:
            ti.warn_once = real
        self.assertEqual((got, calls, warned), (self.want, [p], ["toolidx-cache-ent"]))   # only the bad file rescans

    def test_reload_identical_every_window(self):
        d = NOW - 3 * 86400
        self._write(os.path.join(self.tmp, "-proj", "s6.jsonl"), [
            {"type": "attachment", "uuid": "h9", "timestamp": _iso(d), "attachment": {
                "type": "hook_success", "hookName": "Stop", "command": "x"}},
            {"type": "attachment", "timestamp": _iso(d), "attachment": {
                "type": "deferred_tools_delta", "addedNames": ["mcp__web__a"], "failedMcpServers": [{"name": "dead"}]}}])
        ti.reset()
        want = [(ti.tool_uses(n, now=NOW + 5), ti.mcp_status(n, now=NOW + 5)) for n in (1, 7, 30, 90)]
        ti._TI_STATE["saved"] = -1e9
        ti._save(ti._snapshot(NOW + 5))
        got, calls = self._restart_counting_scans()
        self.assertEqual(calls, [])
        self.assertEqual([(ti.tool_uses(n, now=NOW + 5), ti.mcp_status(n, now=NOW + 5)) for n in (1, 7, 30, 90)], want)
        with open(ti.TI_CACHE, "rb") as f:
            self.assertEqual(f.readline(), b'{"v":%d}\n' % ti.TI_CACHE_V)

    def test_old_version_discarded_silently(self):
        p = os.path.join(self.tmp, "-proj", "s1.jsonl")
        with open(ti.TI_CACHE, "w", encoding="utf-8") as f:            # v3 shape: one JSON object, per-event [key, ts] lists
            json.dump({"v": 3, "files": {p: {"sz": 1, "off": 1, "ev": {"t#x": ["tool:Old", NOW]}, "fail": {}, "conn": {}}}}, f)
        warned, real = [], ti.warn_once
        ti.warn_once = lambda k, *a, **kw: warned.append(k)
        try:
            got, calls = self._restart_counting_scans()
        finally:
            ti.warn_once = real
        self.assertEqual((got, len(calls), warned), (self.want, 2, []))
        ti._TI_STATE["saved"] = -1e9
        ti._save(ti._snapshot(NOW))
        with open(ti.TI_CACHE, "rb") as f:
            self.assertEqual(f.readline(), b'{"v":%d}\n' % ti.TI_CACHE_V)   # rewritten in the current format

    def test_other_root_never_touches_disk(self):
        os.remove(ti.TI_CACHE)
        ti._TI_ROOT = os.path.join(self.tmp, "elsewhere")
        ti.reset()
        ti.tool_uses(30, now=NOW)
        self.assertFalse(os.path.exists(ti.TI_CACHE))


class ToolIdxReindexTest(unittest.TestCase):
    """`_reindex` builds `_TI_SEEN`/`_TI_DUP` from sorted runs, never one list of every id (#26)."""
    def setUp(self):
        import random
        from array import array
        self.saved_chunk = ti.TI_SORT_CHUNK
        ti.reset()
        rnd = random.Random(7)
        for i in range(60):
            ti._TI_FILES["f%d" % i] = {"ids": array("q", (rnd.getrandbits(63) - (1 << 62) for _ in range(300)))}
        ti._TI_FILES["dup"] = {"ids": array("q", list(ti._TI_FILES["f0"]["ids"][:20]) + list(ti._TI_FILES["f9"]["ids"][:5]))}

    def tearDown(self):
        ti.TI_SORT_CHUNK = self.saved_chunk
        vars(sidereus("toolidx_fmt")).pop("sorted", None)
        ti.reset()

    def test_same_as_full_sort(self):
        from itertools import chain, islice
        s = sorted(chain.from_iterable(e["ids"] for e in ti._TI_FILES.values()))
        dup = set(a for a, b in zip(s, islice(s, 1, None)) if a == b)
        ti.TI_SORT_CHUNK = 512
        ti._TI_NEW.add(1)
        ti._reindex()
        self.assertEqual((list(ti._TI_SEEN), ti._TI_DUP, ti._TI_NEW, len(dup)), (s, dup, set(), 25))

    def test_never_sorts_every_id_at_once(self):
        ti.TI_SORT_CHUNK = 512
        lim = 512 + 300                         # one run may overshoot by at most one file

        import builtins

        def guard(it):
            out = builtins.sorted(it)
            assert len(out) <= lim, len(out)
            return out
        sidereus("toolidx_fmt").sorted = guard
        ti._reindex()
        self.assertEqual(len(ti._TI_SEEN), 60 * 300 + 25)


class ToolIdxStreamSaveTest(unittest.TestCase):
    """`_save` streams the snapshot row by row (#26): same bytes as one joined string, no partial file on failure."""
    _write = staticmethod(ToolIdxTest._write)
    setUp, tearDown = ToolIdxDiskTest.setUp, ToolIdxDiskTest.tearDown

    def _fill(self, n):
        from array import array
        k = [ti._kid("tool:T%d" % i) for i in range(20)]
        for i in range(n):
            e = ti._new_ent(100 + i, 100 + i)
            e["ids"], e["ts"] = array("q", range(i * 4, i * 4 + 4)), array("d", [NOW - i] * 4)
            e["ki"], e["fail"] = array("I", [k[(i + j) % 20] for j in range(4)]), {"k%d" % i: (1.0, "E")} if i % 5 == 0 else {}
            ti._TI_FILES[os.path.join(self.tmp, "-p", "s%d.jsonl" % i)] = e
        ti._TI_STATE["dirty"], ti._TI_STATE["saved"] = True, -1e9

    def test_bytes_identical_to_joined(self):
        self._fill(300)
        rows = ti._snapshot(NOW)
        ti._save(rows)
        with open(ti.TI_CACHE, "rb") as f:
            self.assertEqual(f.read(), ("\n".join(rows) + "\n").encode("utf-8"))
        self.assertEqual(os.stat(ti.TI_CACHE).st_mode & 0o777, 0o600)

    def test_failed_write_keeps_previous_cache(self):
        with open(ti.TI_CACHE, "rb") as f:
            before = f.read()

        def rows():
            yield '{"v":%d}' % ti.TI_CACHE_V
            raise OSError("disk full")
        warned, real = [], ti.warn_once
        ti.warn_once = lambda k, *a, **kw: warned.append(k)
        try:
            ti._save(rows())
        finally:
            ti.warn_once = real
        with open(ti.TI_CACHE, "rb") as f:
            self.assertEqual(f.read(), before)
        self.assertEqual((warned, [n for n in os.listdir(self.tmp) if n.startswith(".toolidx-")]), (["toolidx-save"], []))

    def test_save_peak_is_not_the_whole_file(self):
        import tracemalloc
        self._fill(3000)
        rows = ti._snapshot(NOW)
        size = sum(len(r) + 1 for r in rows)
        tracemalloc.start()
        try:
            ti._save(rows)
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        self.assertLess(peak, size // 4)          # joined str + encoded bytes was ~2x size
