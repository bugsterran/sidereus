"""Synthetic demo world for `chat_server.py --demo` — the real page, fed made-up data.

Why: README screenshots and first-time visitors need a believable screen without Claude Code and without
    exposing anyone's real projects, paths, commit subjects or chat. Every value here is invented.
How: `install(Handler, build)` swaps the handler's GET/POST route tables in one place, so no data-source
    function (transcripts, git, quota, bus) ever runs. Pages ("/", "/diff", ...) keep their real handlers.
⚠Everything is deterministic (fixed seed). Times are offsets from an anchor taken once at install, so polls
    see a stable world (message `t` must not move, or the incremental poll re-appends them) while ages grow.
⚠Keep it 100% synthetic — tests/test_demo.py scans every response against a denylist.
"""
import json
import random
import time
from urllib.parse import parse_qs

# ⚠Fixtures, helpers and the tab payload builders (_WorldPanels) live in sidereus/demo_data.py; re-exported here
from sidereus.demo_data import (CX, GEM_ROW, H, REPOS, SEED, _WorldPanels,  # noqa: F401
                             _hex, _iso, _local_iso, _uuid)
from sidereus.demo_git import _WorldGit   # branch tab + rail payloads (split out of demo_data)
from sidereus.demo_rel import _ARCH_COMMIT, _ARCH_MODS, demo_arch, demo_file, demo_src, demo_tree   # structure arch/tree payloads
from sidereus.demo_tools import _demo_eval, _demo_evidence, _demo_harness, _demo_pl_evidence, _demo_pipelines, _demo_prefs, _demo_tools   # noqa: F401  tools/harness/prefs payloads

MSG_FIRST, MSG_RANGE_MAX = 200, 1000   # ⚠mirror sidereus.bus (demo stays stdlib-only, never imports live-data modules)
DEMO_OLD = 240   # > MSG_FIRST - 8 so the oldest posts go out as stubs

# Workflow run under the search session (agents.wf_runs shape): (phase, label, st, start_min_ago, end_min_ago|None, tok)
WF_AGENTS = [("Design", "Spec the search result page", "done", 28, 23, 1_800_000),
             ("Implement", "Result list component", "done", 22, 14, 4_200_000),
             ("Implement", "Query parser for filters", "done", 22, 12, 3_100_000),
             ("Implement", "Index worker retry", "fail", 21, 16, 2_400_000),
             ("Implement", "Highlight matched terms", "done", 20, 11, 2_700_000),
             ("Verify", "Run full check", "run", 10, None, 1_300_000),
             ("Verify", "Screen regression at 3 widths", "run", 9, None, 900_000)]
# Agent team led by the billing session (agents.team_info shape).
TEAM = {"members": [{"name": "api-dev", "st": "run", "model": "sonnet-5", "tsub": "Retry queue for webhooks", "unread": 0},
                    {"name": "reviewer", "st": "done", "model": "opus-5", "tsub": "", "unread": 1},
                    {"name": "test-writer", "st": "idle", "model": "sonnet-5", "tsub": "Contract tests for refunds",
                     "unread": 2}],
        "tasks": {"pending": 1, "in_progress": 2, "completed": 3}, "done": 3, "total": 6, "run": True}


class World(_WorldPanels, _WorldGit):
    """The whole synthetic state. `a` = anchor (epoch seconds); every event is `a - offset`."""

    def __init__(self, anchor=None, page_build="", now=None):
        self.a = int(anchor if anchor is not None else time.time())
        self.build = page_build
        self._now = now     # pin (tests): two Worlds with same anchor+now are byte-identical
        rng = random.Random(SEED)
        self.rng = rng
        a = self.a
        R = REPOS
        # ── sessions: (key, repo, cwd, branch, state, tool, targ, model, win, ctx, age, mbox, born_h, cost)
        spec = [
            ("web", "acme-web", R["acme-web"][0], "feature/checkout-redesign", "think", "Agent",
             "Checkout form validation", "opus-5", 1000000, 412000, 6, "web-lead", 5.2, 38.40),
            ("cart", "acme-web", R["acme-web"][1][0][0], "bugfix/cart-rounding", "tool", "Bash",
             "npm test -- cart", "sonnet-5", 200000, 96000, 21, "cart-fix", 2.1, 6.95),
            ("bill", "billing-api", R["billing-api"][0], "develop", "ask", "", "", "opus-5", 1000000, 188000,
             240, "billing", 4.4, 22.10),
            ("inv", "billing-api", R["billing-api"][1][0][0], "feature/invoice-pdf", "wait", "", "", "opus-5",
             1000000, 872000, 14 * 60, "invoice", 3.6, 31.75),
            ("docs", "docs-site", R["docs-site"][0], "main", "done", "", "", "sonnet-5", 200000, 61000,
             52 * 60, "docs", 2.8, 4.20),
            ("search", "docs-site", R["docs-site"][1][0][0], "feature/search-index", "think", "Monitor",
             "Watch search index build", "opus-5", 1000000, 233000, 3, "search", 1.3, 9.60),
        ]
        self.sess = []
        for (k, repo, cwd, br, st, tool, targ, model, win, ctx, age, mb, born_h, cost) in spec:
            sid = _uuid(rng)
            self.sess.append(dict(k=k, repo=repo, cwd=cwd, branch=br, state=st, tool=tool, targ=targ,
                                  model=model, win=win, ctx=ctx, age=age, mbox=mb, sid=sid, id=sid[:8],
                                  born=a - int(born_h * H), cost=cost,
                                  proj=repo if cwd == R[repo][0] else cwd.rsplit("/", 1)[-1]))
        self.by = {s["k"]: s for s in self.sess}
        # ── subagents: (session key, type, desc, start_min_ago, dur_min (None = running), depth, parent idx, now)
        subs = [
            ("web", "Explore", "Map payment button call sites", 290, 9, 1, None, ""),
            ("web", "general-purpose", "Price formatter unit tests", 250, 22, 1, None, ""),
            ("web", "general-purpose", "Checkout form validation", 38, None, 1, None, "Edit · src/checkout/Form.tsx"),
            ("web", "Explore", "Find address field usages", 12, None, 2, 2, "Grep · AddressInput"),
            ("web", "code-reviewer", "Review coupon edge cases", 95, 17, 1, None, ""),
            ("cart", "general-purpose", "Reproduce rounding drift", 70, 25, 1, None, ""),
            ("bill", "general-purpose", "Webhook retry backoff", 210, 41, 1, None, ""),
            ("bill", "Explore", "Locate currency conversion", 150, 8, 1, None, ""),
            ("inv", "general-purpose", "Invoice PDF layout", 120, 64, 1, None, ""),
            ("inv", "general-purpose", "Tax line snapshot tests", 50, 19, 2, 8, ""),
            ("docs", "general-purpose", "Rewrite quickstart page", 170, 55, 1, None, ""),
            ("search", "general-purpose", "Index builder for API pages", 26, None, 1, None, "Bash · npm run build:index"),
        ]
        self.subs = []
        for (k, typ, desc, st_min, dur, depth, par, now_txt) in subs:
            s0 = a - st_min * 60
            run = dur is None
            s1 = a - 5 if run else s0 + dur * 60
            self.subs.append(dict(k=k, type=typ, desc=desc, start=s0, end=s1, run=run, depth=depth, par=par,
                                  now=now_txt, tid="toolu_" + _hex(rng, 24), aid="a" + _hex(rng, 16),
                                  tk=rng.randint(900, 6200) * 1000, tc=rng.randint(12, 90)))
        for s in self.subs:
            s["paid"] = self.subs[s["par"]]["aid"] if s["par"] is not None else ""
        # ── session activity segments (minutes ago) for the timeline
        self.segs = {
            "web": [(312, 262), (248, 196), (120, 64), (44, 0)],
            "cart": [(126, 98), (78, 40), (30, 0)],
            "bill": [(265, 190), (160, 121), (40, 4)],
            "inv": [(215, 150), (128, 70), (58, 14)],
            "docs": [(180, 112), (100, 52)],
            "search": [(78, 60), (30, 0)],
        }
        self._commits()
        self._chat()

    # ───────────────────────────── git
    def _commits(self):
        rng, a = self.rng, self.a
        subj_main = [
            "Initial project layout", "Add product list page", "Cart store with local persistence",
            "Price formatter handles locales", "CI: run lint and unit tests", "Header navigation component",
            "Fix image lazy-loading flicker", "Add coupon code field", "Bump build tooling",
            "Merge branch 'feature/coupons'", "Checkout: shipping step", "Accessibility pass on buttons",
            "Order summary sidebar", "Release 1.4.0",
        ]
        self.graph = {}
        for repo, (main, wts) in REPOS.items():
            r = random.Random(SEED + len(repo))
            cm, t = [], a - 9 * 24 * H
            prev = None
            n_main = 14 if repo == "acme-web" else 10
            for i in range(n_main):
                sha = _hex(r, 7)
                t += r.randint(3, 9) * H
                subj = subj_main[i] if repo == "acme-web" else self._subj(repo, i)
                ps = [prev] if prev else []
                if subj.startswith("Merge branch"):     # a real merge: side branch off two commits back
                    side = cm[-3]["sha"]
                    for sj, back in (("Coupons: validation", 2), ("Coupons: apply to cart", 1)):
                        s2 = _hex(r, 7)
                        cm.append({"sha": s2, "parents": [side], "subject": sj, "author": "Demo Dev",
                                   "ts": min(t, a - 30 * H) - back * 1800, "refs": []})
                        side = s2
                    ps.append(side)
                cm.append({"sha": sha, "parents": ps, "subject": subj,
                           "author": "Demo Dev", "ts": min(t, a - 30 * H), "refs": []})
                prev = sha
            base = prev
            main_br = "main" if repo != "billing-api" else "develop"
            cm[-1]["refs"] = [main_br, "origin/" + main_br]
            # feature branches from the main tip
            feats = {"acme-web": [("feature/checkout-redesign", ["Checkout: new step layout", "Checkout: card form",
                                                                    "Checkout: inline validation messages",
                                                                    "Checkout: address autocomplete"]),
                                  ("bugfix/cart-rounding", ["Cart: round per line, not per total",
                                                            "Cart: regression test for 0.1 + 0.2"])],
                     "billing-api": [("feature/invoice-pdf", ["Invoice: PDF renderer skeleton",
                                                              "Invoice: tax lines and totals",
                                                              "Invoice: snapshot tests"]),
                                     ("feature/webhook-retry", ["Webhooks: exponential backoff"])],
                     "docs-site": [("feature/search-index", ["Search: index builder",
                                                             "Search: result page"])]}[repo]
            tips = {}
            for j, (bname, subjs) in enumerate(feats):
                p, tt = base, a - (5 - j * 2) * H
                for sj in subjs:
                    sha = _hex(r, 7)
                    tt += r.randint(20, 55) * 60
                    cm.append({"sha": sha, "parents": [p], "subject": sj, "author": "Demo Dev",
                               "ts": min(tt, a - 600), "refs": []})
                    p = sha
                tips[bname] = p
                cm[-1]["refs"] = [bname]
                if len(subjs) > 1:      # pushed up to the previous commit (tip is 1 ahead); 1-commit branches unpushed
                    cm[-2]["refs"] = ["origin/" + bname]
            head_branch = {"acme-web": "feature/checkout-redesign", "billing-api": "develop",
                           "docs-site": "main"}[repo]
            for c in cm:
                if head_branch in c["refs"]:
                    c["refs"] = ["HEAD"] + c["refs"]
            cm.sort(key=lambda c: -c["ts"])
            self.graph[repo] = {"commits": cm, "main": main_br, "tips": tips, "base": base, "head": head_branch}

    @staticmethod
    def _subj(repo, i):
        L = {"billing-api": ["Service skeleton", "Customers endpoint", "Stripe-like payment adapter (mock)",
                             "Idempotency keys on POST", "Currency conversion table", "Refund flow",
                             "OpenAPI spec generation", "Rate limiting middleware", "Fix double-charge on retry",
                             "Release 0.9.0"],
             "docs-site": ["Static site scaffold", "Theme and typography", "Quickstart page", "API reference stubs",
                           "Dark mode", "Code block copy button", "Fix broken anchor links", "Sidebar ordering",
                           "Deploy preview workflow", "Release docs v2"]}
        return L[repo][i]

    # ───────────────────────────── chat
    def _chat(self):
        a, rng = self.a, self.rng
        msgs = [
            (58, "web-lead", "release", "Plan for today", "I take the checkout redesign; cart-fix owns rounding. "
             "Shout before touching src/cart/*."),
            (54, "cart-fix", "release", "Re: Plan for today", "Ack. I need src/cart/total.ts for the fix — two lines."),
            (41, "billing", "release", "Invoice totals", "billing-api now returns totals in minor units (cents). "
             "Please do not round on the client."),
            (37, "web-lead", "release", "Re: Invoice totals", "Good, that removes one rounding step in the UI."),
            (22, "invoice", "release", "PDF snapshots", "Snapshot tests are green locally; waiting for review."),
            (9, "docs", "docs", "Docs freeze", "Docs are frozen for 1.5 — the search page lands after the release."),
            (4, "cart-fix", "release", "Heads-up", "Editing src/cart/total.ts now; web-lead has it open too."),
        ]
        self.msgs = []
        for (m, frm, room, subj, body) in msgs:
            t = (a - m * 60) * 1_000_000_000 + rng.randint(0, 999_999_999)
            self.msgs.append({"id": _hex(rng, 8), "t": t, "from": frm, "idSrc": "identity", "to": None, "room": room,
                              "subject": subj, "thread": None, "body": body})
        # One review relay (bus.dm_send shape) so the «Delivered» stage chip renders. ⚠No rng draw: later draws stay put.
        inv = self.by["inv"]
        self.msgs.insert(-1, {"id": "5e1a7c0d", "t": (a - 6 * 60) * 1_000_000_000, "from": "me", "idSrc": "viewer",
                              "to": inv["mbox"], "room": None, "subject": None, "thread": "wk:5e1a7c0d",
                              "body": "Please add a test for the empty tax line case.", "kind": "relay",
                              "sid": inv["sid"]})
        # Older history so first load has stubs like the live server (bus.MSG_FIRST) and hydrate/«Show earlier posts» run.
        # ⚠Own formula, no self.rng draw: later draws (and every other demo panel) stay put.
        who, what = ["web-lead", "cart-fix", "billing", "invoice", "docs", "search"], [
            "Nightly build is green", "Rebased on main, no conflicts", "Picked up the next ticket",
            "Review left two small comments", "Flaky test re-run passed", "Pushed the fix to my branch"]
        old = [{"id": "0d%06x" % i, "t": (a - 26 * H - (DEMO_OLD - i) * 600) * 1_000_000_000, "from": who[i % 6],
                "idSrc": "identity", "to": None, "room": "release", "subject": "Status %d" % (i + 1),
                "thread": None, "body": what[i % 6] + " (status %d)." % (i + 1)} for i in range(DEMO_OLD)]
        self.msgs = old + self.msgs

    def messages_range(self, after=0, before=None, n=MSG_FIRST):
        """Same contract as bus.messages_range — full demo posts with after < t < before, newest n."""
        out = [dict(m) for m in self.msgs if m["t"] > after and (before is None or m["t"] < before)]
        return out[-max(1, min(int(n), MSG_RANGE_MAX)):]

    def messages_first(self, since):
        """/api/state messages: like bus.messages_first on first load (older than the newest MSG_FIRST = stubs)."""
        out = [dict(m) for m in self.msgs if m["t"] > since]
        if not since:
            for m in out[:max(0, len(out) - MSG_FIRST)]:
                m.pop("body", None)
                m["stub"] = 1
        return out

    # ───────────────────────────── helpers
    def now(self):
        if self._now is not None:
            return self._now
        return max(int(time.time()), self.a)

    def _sess_subs(self, k):
        return [s for s in self.subs if s["k"] == k]

    def wf_runs(self, k):
        """wf_public-shaped runs of session `k` (only the search session has one)."""
        if k != "search":
            return []
        now, a, r = self.now(), self.a, random.Random(SEED + 29)   # own rng: keeps self.rng's sequence unchanged
        ags = [{"aid": "a" + _hex(r, 16), "lab": lab, "phase": ph, "st": st, "start": a - s0 * 60,
                "end": now if e is None else a - e * 60, "tok": tok} for ph, lab, st, s0, e, tok in WF_AGENTS]
        return [{"id": "wf_" + _hex(r, 12), "name": "feature-change", "phase": "Verify",
                 "phases": ["Design", "Implement", "Verify", "Review"],
                 "done": sum(x["st"] == "done" for x in ags), "fail": sum(x["st"] in ("fail", "cut") for x in ags),
                 "total": len(ags), "start": ags[0]["start"], "end": now, "run": True,
                 "tok": sum(x["tok"] for x in ags), "agents": ags}]

    def pl_runs(self, k):
        """pl_runs.pl_model-shaped `plrun` of session `k` (only "web"): change-flow «Design» ✓ → «Implement» ✓ (2nd pass after a «Review» loop-back) → «Verify» run;
        plus open `hotfix` («Implement» run) and ended `release-check`."""
        if k != "web":
            return []
        s, now, a, r = self.by["web"], self.now(), self.a, random.Random(SEED + 31)   # own rng: keeps self.rng unchanged

        def ag(lab, t0, t1, run=False):
            return {"aid": "a" + _hex(r, 16), "tid": "toolu_" + _hex(r, 24), "lab": lab, "run": run, "t0": t0, "t1": t1}
        # ⚠Times sit on the anchor like _demo_evidence rows, so the FAIL (a-1.2h) lands in «Implement» and the PASS (a-0.4h) in «Verify».
        st = {"설계": {"o": "done", "n": 1, "t0": a - 100 * 60, "t1": a - 86 * 60, "from": {},
                       "ag": [ag("Plan: Checkout validation spec", a - 100 * 60, a - 86 * 60)]},
              "구현": {"o": "done", "n": 2, "t0": a - 85 * 60, "t1": a - 31 * 60, "from": {"리뷰": 1}, "p0": a - 52 * 60, "k": 2, "cm": [a - 33 * 60],
                       "ps": [{"a": a - 85 * 60, "b": a - 53 * 60, "s": "back"}],
                       "ag": [ag("general-purpose: Form validation rules", a - 85 * 60, a - 60 * 60),
                              ag("general-purpose: Fix review notes", a - 52 * 60, a - 31 * 60)]},
              "검증": {"o": "run", "n": 1, "t0": a - 30 * 60, "t1": now, "from": {},
                       "ag": [ag("general-purpose: Run gates and screen check", a - 30 * 60, now, True)]}}
        # Stacked runs: a second open run and an ended one (agents drawn after `st` so its ids stay the same).
        hot = {"설계": {"o": "done", "n": 1, "t0": a - 40 * 60, "t1": a - 32 * 60, "from": {},
                        "ag": [ag("Plan: Cart total rounding", a - 40 * 60, a - 32 * 60)]},
               "구현": {"o": "run", "n": 1, "t0": a - 30 * 60, "t1": now - 60, "from": {},
                        "ag": [ag("general-purpose: Round cart totals", a - 30 * 60, now - 60, True)]}}
        rel = {t: {"o": "done", "n": 1, "t0": a - (200 - 12 * i) * 60, "t1": a - (189 - 12 * i) * 60, "from": {},
                   "ag": [ag("general-purpose: " + t + " pass", a - (200 - 12 * i) * 60, a - (189 - 12 * i) * 60)]}
               for i, t in enumerate(("설계", "구현", "검증", "리뷰"))}
        return [{"name": "change-flow", "proj": s["cwd"], "sid": s["sid"], "cur": "검증", "end": 0,
                 "t0": a - 100 * 60, "t1": now, "stages": st},
                {"name": "hotfix", "proj": s["cwd"], "sid": s["sid"], "cur": "구현", "end": 0,
                 "t0": a - 40 * 60, "t1": now - 60, "stages": hot},
                {"name": "release-check", "proj": s["cwd"], "sid": s["sid"], "cur": "리뷰", "end": a - 152 * 60,
                 "t0": a - 200 * 60, "t1": a - 152 * 60, "stages": rel}]

    def wf_tl_rows(self, t0):
        """Timeline rows for the workflow run — same shape as timeline._tl_wf_rows (run row + one row per agent)."""
        s, out = self.by["search"], []
        for w in self.wf_runs("search"):
            kids = [{"tid": "wfa:%s|%s" % (x["aid"], s["sid"]), "type": x["phase"], "aid": x["aid"],
                     "par": "wf:" + w["id"], "desc": x["lab"],
                     "last": "Bash · scripts/check.sh" if x["st"] == "run" else "SubagentHandback",
                     "segs": [[max(t0, x["start"]), x["end"]]], "tk": x["tok"], "tks": [x["tok"]],
                     "tc": 8 + len(x["lab"]) % 23, "fin": 1 if x["st"] == "done" else 0, "start": x["start"],
                     "end": x["end"], "run": x["st"] == "run", "proj": s["proj"], "cwd": s["cwd"], "depth": 2}
                    for x in w["agents"] if x["end"] >= t0]
            if kids:
                out.append({"tid": "wf:%s|%s" % (w["id"], s["sid"]), "type": w["name"], "aid": "wf:" + w["id"],
                            "par": "", "desc": "", "last": "", "kind": "wf", "segs": [],
                            "wf": {k: w[k] for k in ("name", "id", "phase", "done", "fail", "total")},
                            "tk": sum(k["tk"] for k in kids), "tc": sum(k["tc"] for k in kids), "fin": 0,
                            "start": min(k["start"] for k in kids), "end": max(k["end"] for k in kids),
                            "run": w["run"], "proj": s["proj"], "cwd": s["cwd"], "depth": 1})
                out.extend(kids)
        return out

    # ───────────────────────────── /api/state
    def state(self, since=0, ncards=50):
        now, a = self.now(), self.a
        sessions = []
        for i, s in enumerate(self.sess):
            run_subs = [x for x in self._sess_subs(s["k"]) if x["run"]]
            age = s["age"] + (now - a)
            if s["state"] in ("think", "tool"):
                age = s["age"]          # live sessions keep writing
            sub = [{"lab": x["type"] + ": " + x["desc"], "min": max(1, (now - x["start"]) // 60), "now": x["now"],
                    "tid": x["tid"], "idle": 0, "aid": x["aid"]} for x in run_subs]
            pl = self.pl_runs(s["k"])
            sessions.append(dict({"team": TEAM} if s["k"] == "bill" else {}, **({"plrun": pl} if pl else {}), **{
                "id": s["id"], "sid": s["sid"], "project": s["proj"], "gotPrompt": 0, "creq": s["ctx"] // 2, "burn": s["ctx"] * 3,
                "rpm": round(2 + (len(s["mbox"]) % 5) * 1.3, 1), "cwd": s["cwd"], "root": s["cwd"], "branch": s["branch"],
                # same shape as sessions._session_row: targ only for an Agent call (rule 1)
                "tool": s["tool"], "targ": s["targ"] if s["tool"] in ("Agent", "Task") else "",
                "sub": sub, "bgs": [], "mon": [], "wf": self.wf_runs(s["k"]),
                "runmin": {"sub": len(sub), "bg": 0} if sub else {}, "kind": "system", "ageSec": age,
                "bytes": s["ctx"] * 40, "repos": [s["cwd"]],   # like git toplevel: a worktree session's repo is its worktree
                "wt": {"root": s["cwd"], "main": "" if s["cwd"] == REPOS[s["repo"]][0] else REPOS[s["repo"]][0],
                       "name": s["cwd"].rsplit("/", 1)[-1]},
                "mbox": s["mbox"], "mboxSrc": "identity", "cost": s["cost"], "ctx": s["ctx"],
                "model": s["model"], "win": s["win"], "winSrc": "model", "winN": 0,
                "git": {"web": "~4", "cart": "~2", "inv": "~1"}.get(s["k"], ""), "wreck": 0,
                "state": s["state"], "blocked": "", "pmode": "default", "otel": True,
                "otelEv": "tool_result" if s["state"] in ("think", "tool") else "", "otelAt": 0,
                "err": False, "rep": {"n": 1, "tool": s["tool"] or "Read"}, "plat": "cc",
                # same as term.term_attach (added in state(), not _session_row): None once done
                "term": None if s["state"] == "done" else {"app": "iterm", "tty": "ttys%03d" % (i + 1)},
                # two sessions from an extra Claude root (sessions._row_acct shape)
                **({"acct": "work", "acctDir": "/home/demo/.claude-work"} if s["k"] in ("docs", "search") else {})}))
        sessions.append(dict(GEM_ROW, cwd=REPOS["docs-site"][0], ageSec=140))   # one external CLI (Gemini) row
        acks = {}
        names = [s["mbox"] for s in self.sess]
        for m in self.msgs:
            if m.get("kind") == "relay":    # handed over by the Stop hook, not yet acked
                acks[m["id"]] = {"delivered": [m["to"]], "ack": [], "hooked": [m["to"]]}
                continue
            others = [n for n in names if n != m["from"]][:3]
            acks[m["id"]] = {"delivered": others, "ack": [{"who": n, "note": "read"} for n in others[:2]]}
        q = self.quota()
        return {
            "presence": {s["mbox"]: ({"online": True, "at": now - 20} if s["state"] in ("think", "tool", "ask")
                                     else {"online": False, "at": now - s["age"]}) for s in self.sess}, "acks": acks, "acksSince": self.msgs[0]["t"],
            "messages": self.messages_first(since),
            "cursors": {n: self.msgs[-1]["t"] for n in names},
            "rooms": {"release": {"created": (a - 3 * 24 * H) * 1_000_000_000, "owner": "web-lead",
                                  "members": names, "topic": "Release 1.5 coordination", "invited": []},
                      "docs": {"created": (a - 2 * 24 * H) * 1_000_000_000, "owner": "docs",
                               "members": ["docs", "search"], "topic": "Docs site", "invited": []}},
            # room_tags.load() shape {room: [tag]}; a shared tag so the tag filter narrows to 2 rooms vs 1.
            "roomTags": {"release": ["release-1.5", "frontend"], "docs": ["docs", "release-1.5"]},
            "profiles": {"web-lead": {"role": "Frontend lead", "updated": (a - 2 * H) * 10 ** 9},
                         "cart-fix": {"role": "Cart bugfix", "updated": (a - 2 * H) * 10 ** 9},
                         "billing": {"role": "Billing API", "updated": (a - 4 * H) * 10 ** 9},
                         "invoice": {"role": "Invoice export", "updated": (a - 3 * H) * 10 ** 9},
                         "docs": {"role": "Docs writer", "updated": (a - 3 * H) * 10 ** 9},
                         "search": {"role": "Docs search", "updated": (a - H) * 10 ** 9}},
            "sessions": sessions, "cards": self.cards()[:ncards], "attention": self.attention(sessions),
            "review": self.review(sessions),
            "build": self.build,
            "usage": {"at": now, "live": 6, "stale": 0, "reset": {"block": q["five_hour"]["_reset"], "week": None,
                                                                  "src": "anchor"},
                      "block": {"tokens": 212_400_000, "cost": 113.0, "start": _iso(q["five_hour"]["_reset"] - 5 * H),
                                "end": _iso(q["five_hour"]["_reset"]), "leftMin": q["five_hour"]["leftSec"] // 60},
                      "week": {"tokens": 1_310_000_000, "cost": 702.4, "week": _iso(a - 3 * 24 * H)[:10],
                               "max": 3_450_000_000, "pct": 38, "src": "보정"}},
            "bgskip": {"n": 0, "mb": 0},
            "quota": self._pub(q),
            "accts": [{"label": "personal", "primary": True}, {"label": "work", "primary": False}],
            "quotaWho": self.quota_who(),
            # ⚠None: the saver hook is not shipped in plugin/hooks, so a real install never shows that chip.
            "saver": None, "saverView": None, "saverSwitch": None,
            "health": {"dead": [], "warns": [], "soft": [], "stale": []},
            "cardsRead": _local_iso(a - 3 * H), "cardsReadIds": [],
            "fail1h": {"at": now, "n": 4, "step": 600, "kinds": {"tool": 4}, "bins": [0, 1, 0, 2, 0, 1],
                       "bk": [{}, {"tool": 1}, {}, {"tool": 2}, {}, {"tool": 1}]},
            "extUsage": {"gm": dict(GEM_ROW["tokSplit"], tok=GEM_ROW["tok"], n_sessions=1,
                                    cost=GEM_ROW["estCost"], costMiss=0),
                         "cx": dict(CX["tokSplit"], tok=CX["tok"], n_sessions=1, cost=CX["estCost"], costMiss=0,
                                    rate={"primary": {"pct": 34.0, "win": 300, "reset": a + 2 * H + 1200},
                                          "secondary": {"pct": 12.0, "win": 10080, "reset": a + 4 * 24 * H},
                                          "plan": "plus"})},
            # Includes viewerMe like state.py, so the demo page's own posts count as mine.
            # ⚠ASCII id: the Korean default leaked into en text («1 person <Korean default name>»).
            "mine": ["web-lead", "me", "user"], "cfg": {"stripPrefixes": [], "defaultRoom": "release", "viewerMe": "me",
                                                 "viewerIds": ["me", "user"]},
        }

    @staticmethod
    def _pub(q):
        """Quota as the page sees it — without the internal `_reset` helper key."""
        return dict(q, five_hour={k: v for k, v in q["five_hour"].items() if k != "_reset"})

    def attention(self, sessions):
        a, now = self.a, self.now()
        bs = {s["id"]: s for s in sessions}
        w, c, b, i = self.by["web"], self.by["cart"], self.by["bill"], self.by["inv"]
        why_c = "충돌 위험 · 파일 1 · 세션 %s, %s" % (w["id"], c["id"])
        rows = [
            (b, 90, [("ask", "질문 대기", 90, now - bs[b["id"]]["ageSec"])]),
            (c, 85, [("conflict", why_c, 85, a - 5 * 60)]),
            (w, 85, [("conflict", why_c, 85, a - 5 * 60)]),
            (i, 25, [("ctx85", "컨텍스트 87%", 25, now - bs[i["id"]]["ageSec"]),
                     ("done", "작업 끝 · 입력 대기 %d분" % (bs[i["id"]]["ageSec"] // 60), 20,
                      now - bs[i["id"]]["ageSec"])]),
        ]
        out = []
        for s, score, sg in rows:
            sigs = [{"k": k, "why": why, "pts": p, "since": int(t)} for k, why, p, t in sg]
            out.append({"sid": s["sid"], "cwd": s["cwd"], "project": s["repo"], "branch": s["branch"],
                        "score": score, "why": sigs[0]["why"], "since": sigs[0]["since"], "sigs": sigs})
        return {"at": now, "rows": out}

    def cards(self):
        a = self.a
        c = [
            (3, "ask", self.by["bill"], "질문 대기", ""),        # ask/abort cards carry no text (rule 1)
            (5, "agent", self.by["inv"], "서브에이전트 완료", "general-purpose: Tax line snapshot tests"),
            (14, "agent", self.by["web"], "서브에이전트 완료", "code-reviewer: Review coupon edge cases"),
            (31, "agent", self.by["cart"], "서브에이전트 완료", "general-purpose: Reproduce rounding drift"),
            (52, "agent", self.by["docs"], "서브에이전트 완료", "general-purpose: Rewrite quickstart page"),
            (96, "abort", self.by["docs"], "중단됨", ""),
        ]
        return [{"at": _local_iso(a - m * 60), "kind": k, "project": s["repo"], "title": t, "text": x,
                 "cwd": s["cwd"]} for m, k, s, t, x in c]


# ─────────────────────────────────────────────── HTTP glue
def _q(u, k, d=""):
    return (parse_qs(u.query).get(k) or [d])[0]


def _num(s, d):
    try:
        return float(s)
    except (TypeError, ValueError):
        return d


def respond(world, path, u):
    """(status, payload) for a demo GET. Unknown /api paths get an empty-but-valid answer."""
    w = world
    if path == "/api/state":
        since = _q(u, "since", "0")     # ⚠ns epoch (19 digits) — int(), never float(), or the last message repeats
        return 200, w.state(int(since) if since.isdigit() else 0,
                            max(1, min(300, int(_num(_q(u, "cards", "50"), 50)))))
    if path == "/api/messages":
        after, before, n = _q(u, "after", "0"), _q(u, "before", "0"), _q(u, "n", str(MSG_FIRST))   # no n = bus.MSG_RANGE_DEFAULT
        if not (after.isdigit() and before.isdigit() and n.isdigit()):   # ⚠ns epochs — int() only, like the live route
            return 400, {"error": "bad cursor"}
        return 200, {"messages": w.messages_range(int(after), int(before) or None, int(n))}
    if path == "/api/cards":
        return 200, {"cards": w.cards()}
    if path == "/api/agents/timeline":
        return 200, w.timeline(max(1.0, min(48.0, _num(_q(u, "hours", "12"), 12.0))))
    if path == "/api/quota/burn":
        return 200, w.quota_burn()
    if path == "/api/live":
        return 200, w.live()
    if path == "/api/wkuse":
        return 200, w.wkuse(int(_num(_q(u, "range", "7"), 7)), _q(u, "acct"))
    if path == "/api/branches":
        return w.branches(_q(u, "cwd"))
    if path == "/api/git/links":
        return 200, w.git_links(_q(u, "repo"), set(x for x in _q(u, "shas").split(",") if x))
    if path == "/api/git/commit":
        return w.git_commit(_q(u, "repo"), _q(u, "sha"))
    if path == "/api/git/owners":
        return 200, w.git_owners(_q(u, "cwd"))
    if path == "/api/git/wtfiles":
        return 200, w.git_wtfiles(_q(u, "cwd"))
    if path == "/api/git/diff":
        if _q(u, "view") == "rail":
            return 200, w.git_rail(_q(u, "cwd"), _q(u, "base", "auto"), _q(u, "sid"))
        return 200, w.git_diff(_q(u, "cwd"))
    if path == "/api/review":
        return 200, w.review_files(_q(u, "cwd"), _q(u, "sid"))
    if path == "/api/history":
        return 200, w.history(int(_num(_q(u, "days", "7"), 7)))
    if path == "/api/history/units":
        return 200, w.history_units(_q(u, "sid"))
    if path == "/api/sessions/recent":
        return 200, w.recent(max(1, min(30, int(_num(_q(u, "days", "7"), 7)))))
    if path == "/api/retro":
        return 200, w.retro(max(1, min(30, int(_num(_q(u, "days", "7"), 7)))), _q(u, "acct"))
    if path == "/api/agent/work":
        return 200, w.agent_work(_q(u, "tid"), _q(u, "sid"))
    if path == "/api/session/work":
        return 200, w.session_work(_q(u, "sid") or w.sess[0]["sid"])
    if path == "/api/session/context":
        return 200, w.session_context(_q(u, "cwd"))
    if path.startswith("/api/tools"):
        return _demo_tools(w.a, path, _q(u, "id"))
    if path == "/api/pipelines":
        return _demo_pipelines(_q(u, "proj"), w.by["web"]["cwd"], w.by["bill"]["cwd"])
    if path == "/api/pipelines/eval":
        return _demo_eval(_q(u, "proj"), w.by["web"]["cwd"], _q(u, "name"))
    if path == "/api/harness/evidence":   # same body as harness_plat.harness_evidence_only (pipeline stage result lines)
        return 200, _demo_pl_evidence(w.a)
    if path.startswith("/api/harness"):
        return _demo_harness(w.a, path)
    if path == "/api/prefs":     # ⚠the bare {"ok": True} fallback lacks `keys` — «Preferences» showed a red read error
        return 200, _demo_prefs()
    if path == "/api/structure":
        return 200, {"ok": False, "msg": "The Structure tab is not used in demo mode"}
    if path == "/api/arch":
        return 200, demo_arch(w.a)
    if path == "/api/arch/files":   # ⚠the bare {"ok": True} fallback left module detail «Files» empty
        return 200, demo_arch_files(_q(u, "id"))
    if path == "/api/structure/src":
        return 200, demo_src(_q(u, "path"), _q(u, "file"), _q(u, "line", "1"), _q(u, "lines", "0"))
    if path == "/api/structure/tree":
        return 200, demo_tree(_q(u, "path"))
    if path == "/api/structure/file":
        return 200, demo_file(_q(u, "path"), _q(u, "file"), _q(u, "line", "1"))
    return 200, {"ok": True}


def demo_arch_files(mid):
    """Body of demo `GET /api/arch/files` — arch_map.files() keys, names from the demo tree under the module path."""
    out = {"ok": True, "commit": _ARCH_COMMIT, "id": "", "path": "", "files": [], "total": 0, "cut": False, "why": ""}
    mod = next((m for m in _ARCH_MODS if m["id"] == mid), None)
    if mod is None:
        return dict(out, why="bad")
    out.update(id=mid, path=mod["path"])
    if mod["kind"] == "external":
        return dict(out, why="ext")
    hit = [f["p"] for f in demo_tree()["files"] if f["p"].startswith(mod["path"])]
    return dict(out, files=hit, total=len(hit), why="" if hit else "gone")


def install(handler_cls, page_build):
    """Swap the handler's routes for the demo world (one place, no data-source function runs).
    Page routes keep their real handler; every other GET and all POSTs are answered here."""
    world = World(page_build=page_build)
    pages = {p: f for p, f in handler_cls._GET_ROUTES.items() if not p.startswith("/api/")}

    def _get(self, u):
        code, out = respond(world, u.path, u)
        return self._raw_json(code, out)

    def _post(self, u):
        self._body_json(1 << 20, {})     # drain the body; nothing is written in demo mode
        if u.path == "/api/term/focus":  # ⚠never osascript in demo — pretend the tab came forward
            return self._raw_json(200, {"ok": True, "demo": True, "how": "focused"})
        return self._raw_json(200, {"ok": True, "demo": True})

    routes = dict(pages)
    for p in handler_cls._GET_ROUTES:
        if p == "/api/ui-prefs.js":     # a script, not JSON: keep the real handler (memory-only in demo, serves {})
            routes[p] = handler_cls._GET_ROUTES[p]
        elif p.startswith("/api/"):
            routes[p] = _get
    handler_cls._GET_ROUTES = routes
    handler_cls._POST_ROUTES = {p: _post for p in handler_cls._POST_ROUTES}
    return world


def serve(handler_cls, port, page_build, open_browser):
    """`--demo` entry: install the demo routes and serve on loopback. No background loops start."""
    from http.server import ThreadingHTTPServer
    install(handler_cls, page_build)
    srv = ThreadingHTTPServer(("127.0.0.1", port), handler_cls)
    url = "http://127.0.0.1:%d/" % port
    print("Sidereus demo (synthetic data) — %s" % url, flush=True)
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("stopped")


if __name__ == "__main__":
    print(json.dumps(World().state(), ensure_ascii=False, indent=1)[:2000])
