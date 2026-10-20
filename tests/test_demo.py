"""Demo world (`chat_server.py --demo`, sidereus/demo.py): payload shapes and a leak guard.

★The demo feeds README screenshots, so a real name slipping in would be published. The denylist below
  holds the author's real home segment and project names; every demo response is scanned for them.
"""
import json
import os
import unittest

from sidereus import arch_schema
from tests._load import sidereus

# ⚠Real project/company words must not ship in this file: they come from tests/.private-deny
# (one word per line, gitignored and .distignored), so a fork's own names can be listed there too.
_PRIV = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".private-deny")
DENY = ("mailbox-mcp", "/Users/") + tuple(
    w.strip() for w in (open(_PRIV, encoding="utf-8").read().splitlines() if os.path.exists(_PRIV) else [])
    if w.strip() and not w.startswith("#"))

STATE_KEYS = {"presence", "acks", "acksSince", "messages", "cursors", "rooms", "profiles", "sessions", "cards",
              "attention", "build", "usage", "bgskip", "quota", "quotaWho", "saver", "saverView", "saverSwitch",
              "health", "cardsRead", "cardsReadIds", "fail1h", "extUsage", "mine", "cfg", "review", "roomTags", "accts"}

# Same keys as sidereus/arch_map.load() output.
ARCH_KEYS = {"ok", "prov", "empty", "sidereus", "commit", "head", "stale", "behind", "at", "v", "groups", "modules", "edges", "rate", "md",
             "style", "dev", "flows", "checks"}


class _U:
    def __init__(self, q=""):
        self.query = q


def all_responses(demo, world):
    """Every demo payload the page can ask for (leak + determinism tests)."""
    qs = [("/api/state", "since=0&cards=300"), ("/api/cards", ""), ("/api/agents/timeline", "hours=12"),
          ("/api/quota/burn", ""), ("/api/live", ""), ("/api/wkuse", "range=7"), ("/api/history", "days=7"),
          ("/api/sessions/recent", "days=7"), ("/api/retro", "days=7"), ("/api/git/diff", ""), ("/api/structure", ""), ("/api/arch", ""),
          ("/api/structure/src", "file=order/OrderService.java&line=3"),
          ("/api/structure/tree", ""), ("/api/structure/file", "file=ui/src/api.ts&line=2")]
    for repo, (main, wts) in demo.REPOS.items():
        for p in [main] + [x for x, _ in wts]:
            qs += [("/api/branches", "cwd=" + p), ("/api/git/owners", "cwd=" + p), ("/api/git/wtfiles", "cwd=" + p),
                   ("/api/git/diff", "view=rail&cwd=" + p), ("/api/git/diff", "view=rail&base=head&cwd=" + p),
                   ("/api/git/diff", "view=rail&base=start&cwd=" + p)]
        cm = world.graph[repo]["commits"]
        qs += [("/api/git/links", "repo=%s&shas=%s" % (main, ",".join(c["sha"] for c in cm))),
               ("/api/git/commit", "repo=%s&sha=%s" % (main, cm[0]["sha"]))]
    for s in world.sess:
        qs += [("/api/history/units", "sid=" + s["sid"]), ("/api/session/work", "sid=" + s["sid"]),
               ("/api/git/diff", "scope=work&cwd=" + s["cwd"])]
    return [(p + "?" + q, demo.respond(world, p, _U(q))) for p, q in qs]


class DemoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.demo = sidereus("demo")
        cls.anchor = 1_790_000_000
        cls.w = cls.demo.World(anchor=cls.anchor, page_build="abc123def456", now=cls.anchor)

    def get(self, path, q=""):
        code, out = self.demo.respond(self.w, path, _U(q))
        self.assertEqual(code, 200, path)
        return out

    def test_state_shape(self):
        st = self.get("/api/state", "since=0")
        self.assertEqual(set(st), STATE_KEYS)
        self.assertEqual(st["build"], "abc123def456")      # same as PAGE_BUILD, or the «new version» toast shows
        self.assertEqual(len(st["sessions"]), 7)              # 6 Claude + 1 synthetic Gemini
        self.assertEqual([s["plat"] for s in st["sessions"]].count("gm"), 1)
        self.assertEqual(st["extUsage"]["gm"]["tok"], sum(st["extUsage"]["gm"][k] for k in ("in", "out", "cache", "thought")))
        self.assertEqual({s["state"] for s in st["sessions"]}, {"think", "tool", "ask", "wait", "done"})
        self.assertTrue(any(s["sub"] for s in st["sessions"]))
        self.assertIn("conflict", {g["k"] for r in st["attention"]["rows"] for g in r["sigs"]})
        self.assertNotIn("_reset", st["quota"]["five_hour"])
        self.assertEqual(st["quota"]["five_hour"]["pct"], 55.0)
        self.assertEqual([(a["label"], a["primary"]) for a in st["accts"]], [("personal", True), ("work", False)])
        sids = {s["sid"] for s in st["sessions"]}
        self.assertTrue(all(r["sid"] in sids for r in st["attention"]["rows"]))

    def test_prefs_has_real_shape(self):
        # 90b-mypref.js treats a reply without `keys` as a read failure (red error in Preferences).
        out = self.get("/api/prefs")
        prefs, cc = sidereus("prefs"), sidereus("cc_settings")
        self.assertTrue(out["ok"])
        self.assertEqual(set(out["keys"]), (set(prefs.PREFS) - prefs.PREFS_OWN_PANE) | set(cc.CC_KEYS))
        self.assertTrue({"path", "cc_path", "otel", "features", "mailbox_watch"} <= set(out))
        self.assertNotIn("err", out)

    def test_mine_includes_viewer_me(self):
        st = self.get("/api/state", "since=0")
        self.assertIn(st["cfg"]["viewerMe"], st["mine"])     # same rule as state.py: the page's own posts are mine

    def test_room_tags_and_ascii_viewer_id(self):
        st = self.get("/api/state", "since=0")
        tags = st["roomTags"]
        self.assertGreaterEqual(len(tags), 2)
        self.assertTrue(set(tags) <= set(st["rooms"]))   # tags only on rooms that exist
        self.assertTrue(all(isinstance(v, list) and all(isinstance(t, str) for t in v) for v in tags.values()))
        ids = [st["cfg"]["viewerMe"]] + st["cfg"]["viewerIds"] + st["mine"] + [m["from"] for m in st["messages"]]
        self.assertTrue(all(i.isascii() for i in ids if i))    # Korean ids leaked into en card text

    def test_session_work_shows_cut_edits(self):
        w = self.w.session_work(self.w.sess[0]["sid"])
        self.assertGreater(w["cutEdits"], 0)
        self.assertEqual(sum(1 for s in w["steps"] if s.get("editCut")), w["cutEdits"])

    def test_incremental_state_has_no_old_messages(self):
        st = self.get("/api/state", "since=0")
        last = st["messages"][-1]["t"]
        self.assertEqual(self.get("/api/state", "since=%d" % last)["messages"], [])

    def test_first_load_stubs_and_messages_route(self):
        ms = self.get("/api/state", "since=0")["messages"]
        full = [m for m in ms if not m.get("stub")]
        stubs = [m for m in ms if m.get("stub")]
        self.assertEqual(len(full), self.demo.MSG_FIRST)       # same cut as bus.messages_first
        self.assertTrue(stubs and all("body" not in m for m in stubs))
        self.assertEqual(ms, sorted(ms, key=lambda m: m["t"]))
        lo, hi = stubs[0]["t"], stubs[-1]["t"]
        got = self.get("/api/messages", "after=%d&before=%d&n=1000" % (lo - 1, hi + 1))["messages"]
        self.assertEqual([m["id"] for m in got], [m["id"] for m in stubs])
        self.assertTrue(all(m["body"] for m in got))
        self.assertEqual(len(self.get("/api/messages", "after=0&before=0&n=5")["messages"]), 5)
        self.assertEqual(self.demo.respond(self.w, "/api/messages", _U("after=x"))[0], 400)
        self.assertNotIn("body", stubs[0])                     # the route hands out copies

    def test_timeline_shape(self):
        tl = self.get("/api/agents/timeline", "hours=12")
        self.assertTrue(tl["ok"])
        self.assertEqual(len(tl["tok"]["v"]), 12 * 3600 // tl["tok"]["step"] + 1)
        kinds = {r.get("kind", "agent") for r in tl["rows"]}
        self.assertEqual(kinds, {"sess", "agent", "wf"})
        for r in tl["rows"]:
            for a, b in r["segs"]:
                self.assertLessEqual(a, b)
        # workflow run row: its agents hang under it (par = run aid), like timeline._tl_wf_rows
        (run,) = [r for r in tl["rows"] if r.get("kind") == "wf"]
        kids = [r for r in tl["rows"] if r.get("par") == run["aid"]]
        self.assertEqual(len(kids), run["wf"]["total"])
        self.assertEqual(run["tk"], sum(k["tk"] for k in kids))

    def test_workflow_and_team_nodes(self):
        rows = self.get("/api/state", "since=0")["sessions"]
        (w,) = [x for r in rows for x in r.get("wf", [])]   # the Gemini row has no wf
        self.assertEqual((w["done"], w["fail"], w["total"]), (4, 1, 7))
        self.assertEqual({a["phase"] for a in w["agents"]}, {"Design", "Implement", "Verify"})
        self.assertFalse(any(k.startswith("_") for a in w["agents"] for k in a))   # wf_public drops _file
        (t,) = [r["team"] for r in rows if "team" in r]
        self.assertEqual((len(t["members"]), t["done"], t["total"]), (3, 3, sum(t["tasks"].values())))
        self.assertEqual({m["st"] for m in t["members"]}, {"run", "idle", "done"})

    def test_plrun_shape(self):
        rows = self.get("/api/state", "since=0")["sessions"]
        (r,) = [p for x in rows for p in x.get("plrun", []) if p["name"] == "change-flow"]
        self.assertEqual(set(r), {"name", "proj", "sid", "cur", "end", "t0", "t1", "stages"})
        self.assertEqual((r["cur"], r["end"]), ("검증", 0))
        self.assertEqual({t: s["o"] for t, s in r["stages"].items()}, {"설계": "done", "구현": "done", "검증": "run"})
        im = r["stages"]["구현"]
        self.assertEqual((im["k"], im["from"]), (2, {"리뷰": 1}))
        for s in r["stages"].values():
            self.assertLessEqual(set(s), {"o", "n", "t0", "t1", "from", "p0", "k", "ag", "ps", "cm"})
            cm = s.get("cm", [])   # commit stamps: epoch numbers only
            self.assertTrue(isinstance(cm, list) and len(cm) <= 4 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in cm), cm)
            for a in s["ag"]:   # metadata only: no message/prompt fields
                self.assertEqual(set(a), {"aid", "tid", "lab", "run", "t0", "t1"})
        ev = self.get("/api/harness/evidence", "proj=" + r["proj"])["evidence"]
        st = r["stages"]
        self.assertTrue(any(st["검증"]["t0"] <= e["ts"] <= st["검증"]["t1"] for e in ev))   # 검증 has a result line
        self.assertEqual(self.get("/api/pipelines")["projects"][0]["path"], r["proj"])
        (p,) = self.get("/api/pipelines", "proj=" + r["proj"])["pipelines"]
        self.assertEqual(p["name"], r["name"])
        self.assertLessEqual(set(st), {s["title"] for s in p["stages"]})
        P = dict({k: p[k] for k in ("title", "defaults", "stages")}, v=1, name=p["name"])
        self.assertEqual(sidereus("pipeline_schema").validate(P, p["name"]), [])   # a file the real loader would accept

    def test_branches_and_links(self):
        root = self.demo.REPOS["acme-web"][0]
        br = self.get("/api/branches", "cwd=" + root)
        self.assertTrue(br["ok"])
        self.assertGreaterEqual(len(br["worktrees"]), 2)
        shas = {c["sha"] for c in br["commits"]}
        for c in br["commits"]:
            self.assertTrue(set(c["parents"]) <= shas, c)
        self.assertTrue(any(len(c["parents"]) > 1 for c in br["commits"]))     # a real merge in the graph
        links = self.get("/api/git/links", "repo=%s&shas=%s" % (root, ",".join(shas)))
        self.assertTrue(links["links"])
        code, _ = self.demo.respond(self.w, "/api/branches", _U("cwd=/elsewhere"))
        self.assertEqual(code, 400)

    def test_quota_burn_and_wkuse(self):
        qb = self.get("/api/quota/burn")
        self.assertEqual(qb["cur"]["now_pct"], 55.0)
        pts = qb["cur"]["pts"]
        self.assertEqual(pts, sorted(pts))
        wk = self.get("/api/wkuse", "range=7")
        self.assertEqual(len(wk["daily"]), 7)
        self.assertEqual(wk["total"], sum(r["tok"] for r in wk["rows"]))

    def test_rail_owners_conflict_and_base_modes(self):
        """Changes rail: owner lines, one «충돌» example on both acme-web worktrees, all three base modes."""
        main, wt = self.demo.REPOS["acme-web"][0], self.demo.REPOS["acme-web"][1][0][0]
        for cwd in (main, wt):
            r = self.get("/api/git/diff", "view=rail&cwd=" + cwd)
            self.assertEqual(r["baseMode"], "remote")                       # auto resolves like a repo with origin
            self.assertEqual(r["baseKind"], "branch")
            self.assertGreater(r["nCommits"], 0)
            self.assertGreater(r["n"], r["dirty"])                          # committed-since-base files are listed too
            cf = [f for f in r["files"] if f.get("conflict")]
            self.assertEqual([f["path"] for f in cf], ["src/cart/total.ts"])
            self.assertEqual(len({o["sid"] for o in cf[0]["own"]}), 2)      # conflict = 2+ distinct sessions
            own = [o for f in r["files"] for o in f.get("own", [])]
            self.assertTrue(own and any(not o["main"] and o["tid"] and o["lab"] for o in own))
            for f in r["files"]:
                ags = [o["ago"] for o in f.get("own", [])]
                self.assertEqual(ags, sorted(ags))                          # latest first, like _rail_owners
        sid = self.w.by["web"]["sid"]
        hd = self.get("/api/git/diff", "view=rail&base=head&cwd=" + main)
        self.assertEqual((hd["baseKind"], hd["base"], hd["nCommits"]), ("head", "", 0))
        self.assertEqual(hd["n"], hd["dirty"])
        st = self.get("/api/git/diff", "view=rail&base=start&sid=%s&cwd=%s" % (sid, main))
        self.assertEqual(st["baseKind"], "start")
        self.assertEqual(st["since"], self.w.by["web"]["born"])
        bill = self.get("/api/git/diff", "view=rail&cwd=" + self.demo.REPOS["billing-api"][0])
        self.assertEqual((bill["baseKind"], bill["baseRef"]), ("remote", "origin/develop"))

    def test_tokens_top5_and_headroom_uncertainty(self):
        top = self.get("/api/wkuse", "range=7")["agc"]["top"]
        tids = {s["tid"] for s in self.w.subs}
        for nd in ("1", "7"):
            rs = top[nd]
            self.assertEqual(len(rs), 5)
            self.assertEqual([r["tok"] for r in rs], sorted((r["tok"] for r in rs), reverse=True))
            for r in rs:
                self.assertTrue(r["desc"] and r["cwd"] and r["dur"] > 0 and 0 < r["share"] <= 100)
                t, s = r["tid"].split("|")
                self.assertIn(t, tids)
                self.assertTrue(self.get("/api/agent/work", "tid=%s&sid=%s" % (t, s))["ok"])   # row click opens a popup
        hd = self.get("/api/quota/burn")["head"]
        self.assertTrue(0 < hd["unc"] <= 0.5 and hd["unc_n"] > 0)          # «±N%», not «추정 초기»
        self.assertTrue(0 < hd["wk"]["unc"] <= 0.5)

    def test_arch_schema_and_src(self):
        """Demo Architecture view: arch_map.load() keys, closed edges, one unproven flow step, evidence opens in code."""
        r = self.get("/api/arch", "path=" + self.demo.REPOS["acme-web"][0])
        self.assertEqual(set(r), ARCH_KEYS)
        self.assertTrue(r["ok"] and not r["empty"] and not r["stale"])
        # v2 with a valid layer on every non-external module, or the screen drops the layer bands (archHasLayers).
        self.assertEqual(r["v"], 2)
        for m in r["modules"]:
            if m["kind"] != "external":
                self.assertIn(m.get("layer"), arch_schema.LAYERS, m)
                self.assertEqual(arch_schema.ROLE_LAYER[m["role"]], m["layer"], m)
            else:
                self.assertNotIn("ext", m)
        ids = {m["id"] for m in r["modules"]}
        self.assertEqual(len(ids), len(r["modules"]))
        for e in r["edges"]:
            self.assertEqual(set(e), {"from", "to", "kind", "label", "est", "ok", "evidence"})
            self.assertTrue(e["from"] in ids and e["to"] in ids, e)
        self.assertTrue(0 < r["rate"] < 1)
        self.assertTrue(r["md"].startswith("```mermaid"))
        self.assertEqual(r["style"]["style"], "layered")
        self.assertEqual(len(r["flows"]), 2)
        self.assertEqual([f["ok"] for f in r["flows"]], [True, False])
        bad = [s for f in r["flows"] for s in f["steps"] if not s["ok"]]
        self.assertEqual([s["why"] for s in bad], ["nosym"])
        for f in r["flows"]:
            self.assertEqual(set(f), {"id", "name", "entry", "ok", "steps"})
            for s in f["steps"]:
                self.assertTrue(s["from"] in ids and s["to"] in ids, s)
        self.assertNotIn("/Users", json.dumps(r))
        for e in r["edges"]:
            ev = e["evidence"][0]
            src = self.get("/api/structure/src", "file=%s&line=%d&lines=1" % (ev["file"], ev["line"]))
            self.assertTrue(src["ok"], ev)
            self.assertIn(ev["symbol"], src["code"], ev)
        self.assertFalse(self.get("/api/structure/src", "file=../etc/passwd")["ok"])

    def test_arch_files_shape(self):
        """Module detail «Files»: arch_map.files() keys, names under the module path, ext/bad answered with a reason."""
        keys = {"ok", "commit", "id", "path", "files", "total", "cut", "why"}
        cm = self.get("/api/arch")["commit"]
        r = self.get("/api/arch/files", "id=order")
        self.assertEqual(set(r), keys)
        self.assertEqual((r["commit"], r["why"], r["total"]), (cm, "", len(r["files"])))
        self.assertTrue(r["files"] and all(f.startswith("order/") for f in r["files"]), r)
        self.assertEqual(self.get("/api/arch/files", "id=db")["why"], "ext")
        self.assertEqual(self.get("/api/arch/files", "id=nope")["why"], "bad")

    def test_pipelines_catalog_shape(self):
        """Stage palette: catalog {groups, items} from the bundled templates, no real install path, avail pinned."""
        proj = self.get("/api/pipelines")["projects"][0]["path"]
        c = self.get("/api/pipelines", "proj=" + proj)["catalog"]
        self.assertEqual(set(c), {"groups", "items"})
        self.assertTrue(c["groups"] and c["items"])
        for it in c["items"]:
            self.assertTrue({"id", "group", "title", "gate", "tools"} <= set(it), it)
            self.assertNotIn("task", it)
            self.assertTrue(all(x["avail"] is True for x in it["tools"]), it)
        sc = sidereus("stage_catalog")
        self.assertNotIn(sc.CODE_DIR, json.dumps(c))
        self.assertIn("{sidereus}", json.dumps(sc.load()))   # the substitution is exercised
        # same body as the real catalog() with the demo's fake path and every tool available
        from unittest import mock
        fake = os.path.join(os.path.dirname(proj), "sidereus")
        with mock.patch.object(sc, "CODE_DIR", fake), mock.patch.object(sc, "_which", lambda b: "/bin/" + b):
            self.assertEqual(c, sc.catalog())

    def test_structure_tree_and_file(self):
        """Demo file tree/viewer: real keys, arch evidence files open, .env locked, logo.png binary, unknown refused."""
        t = self.get("/api/structure/tree", "")
        self.assertEqual(set(t), {"ok", "path", "git", "files", "n", "truncated", "warm", "stn"})
        self.assertEqual(t["stn"], {"A": 2, "M": 3, "D": 1})
        self.assertEqual(self.get("/api/structure/file", "file=order/LegacyOrderDao.java").get("gone"), True)
        self.assertTrue(t["ok"] and t["git"] and t["warm"] and not t["truncated"])
        self.assertEqual(t["n"], len(t["files"]))
        self.assertTrue(25 <= t["n"] <= 40)
        by = {f["p"]: f for f in t["files"]}
        self.assertTrue(all(set(f) <= {"p", "sz", "sec", "st"} for f in t["files"]))
        self.assertEqual([p for p, f in by.items() if f.get("sec")], [".env"])
        self.assertIn("docs/logo.png", by)
        arch = self.get("/api/arch", "")
        for e in arch["edges"] + [s for fl in arch["flows"] for s in fl["steps"]]:
            for ev in e["evidence"] if isinstance(e["evidence"], list) else [e["evidence"]]:
                self.assertIn(ev["file"], by)
        f = self.get("/api/structure/file", "file=order/OrderService.java&line=3")
        self.assertEqual(set(f), {"ok", "path", "file", "line", "n", "code", "truncated", "bytes", "enc", "masked", "note"})
        self.assertTrue(f["ok"] and f["line"] == 3 and "class OrderService" in f["code"])
        self.assertEqual(f["bytes"], by["order/OrderService.java"]["sz"])
        self.assertEqual(self.get("/api/structure/file", "file=.env"), {"ok": False, "locked": True, "msg": "This file cannot be opened."})
        self.assertEqual(self.get("/api/structure/file", "file=docs/logo.png"),
                         {"ok": False, "bin": True, "bytes": 2048, "msg": "This is a binary file."})
        self.assertEqual(self.get("/api/structure/file", "file=../etc/passwd"), {"ok": False, "msg": "This file is not in the list."})
        self.assertNotIn("/Users", json.dumps([t, f]))

    def test_deterministic(self):
        w2 = self.demo.World(anchor=self.anchor, page_build="abc123def456", now=self.anchor)
        a = json.dumps([o for _, o in all_responses(self.demo, self.w)], sort_keys=True)
        b = json.dumps([o for _, o in all_responses(self.demo, w2)], sort_keys=True)
        self.assertEqual(a, b)

    def test_no_real_names_leak(self):
        rs = all_responses(self.demo, self.w)
        self.assertGreater(len(rs), 20)
        for path, (code, out) in rs:
            blob = json.dumps(out, ensure_ascii=False).lower()
            for bad in DENY:
                self.assertNotIn(bad.lower(), blob, "%s leaks %r" % (path, bad))

    def test_review_diff_term_and_relay(self):
        inv = self.w.by["inv"]
        d = self.get("/api/git/diff", "scope=work&cwd=" + inv["cwd"])
        self.assertTrue(d["ok"])
        self.assertIn("diff --git a/src/invoice/pdf.ts", d["diff"])
        self.assertIn("\n+", d["diff"])       # new-side lines -> review «+» gutter
        self.assertEqual(self.get("/api/git/diff", "cwd=/nowhere")["diff"], "")
        st = self.get("/api/state", "since=0")
        cc = [r for r in st["sessions"] if r.get("plat") == "cc"]
        self.assertTrue(all((r["term"] is None) == (r["state"] == "done") for r in cc))
        rl = [m for m in st["messages"] if m.get("kind") == "relay"]
        self.assertEqual([(m["sid"], m["to"], m["idSrc"]) for m in rl], [(inv["sid"], inv["mbox"], "viewer")])
        a = st["acks"][rl[0]["id"]]
        self.assertEqual((a["delivered"], a["hooked"], a["ack"]), ([inv["mbox"]], [inv["mbox"]], []))
        ts = [m["t"] for m in st["messages"]]
        self.assertEqual(ts, sorted(ts))

    def test_install_swaps_every_api_route(self):
        class H:
            _GET_ROUTES = {"/": "page", "/api/state": "real", "/api/branches": "real"}
            _POST_ROUTES = {"/api/say": "real"}
        self.demo.install(H, "b")
        self.assertEqual(H._GET_ROUTES["/"], "page")
        self.assertNotEqual(H._GET_ROUTES["/api/state"], "real")
        self.assertNotEqual(H._POST_ROUTES["/api/say"], "real")


if __name__ == "__main__":
    unittest.main()
