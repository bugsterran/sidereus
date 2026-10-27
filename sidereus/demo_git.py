"""Demo branch/git payloads for `chat_server.py --demo` (split out of sidereus/demo_data.py, 2026-09-27).

Owns `_WorldGit` — branches, git links/commit/owners/wtfiles and the timeline rail (`git_rail`) that `World` inherits,
plus the rail file fixtures `_RAIL_FILES`/`_RAIL_COMMITTED`.
⚠Imported only by sidereus/demo.py (lazy, under --demo). Never import sidereus.demo from here (cycle).
⚠Keep it 100% synthetic — tests/test_demo.py scans every response against a denylist.
"""
import random

from sidereus.demo_data import H, REPOS, SEED


class _WorldGit:
    """Branch-tab and rail payload builders mixed into demo.World (needs self.a/sess/subs/by/graph, state())."""

    def _repo_of(self, cwd):
        for repo, (main, wts) in REPOS.items():
            if cwd == main or any(cwd == p for p, _ in wts):
                return repo
        return None

    def branches(self, cwd):
        repo = self._repo_of(cwd)
        if not repo:
            return 400, {"ok": False, "msg": "not a demo repo"}
        g, (main, wts), a = self.graph[repo], REPOS[repo], self.a
        cm = g["commits"]
        tip = {}
        for c in cm:
            for ref in c["refs"]:
                if ref != "HEAD":
                    tip.setdefault(ref, c)
        brs = []
        for name, c in tip.items():
            kind = "remote" if name.startswith("origin/") else "local"
            up = ("origin/" + name) if kind == "local" and ("origin/" + name) in tip else ""
            ahead = len(self._chain(cm, c["sha"], g["base"])) if kind == "local" and name != g["main"] else 0
            brs.append({"name": name, "kind": kind, "sha": c["sha"], "upstream": up, "ahead": ahead, "behind": 0,
                        "ts": c["ts"]})
        head_c = tip.get(g["head"])
        wtl = [{"path": main, "head": head_c["sha"] if head_c else cm[0]["sha"], "branch": g["head"], "main": True,
                "detached": False}]
        for p, b in wts:
            wtl.append({"path": p, "head": tip[b]["sha"] if b in tip else cm[0]["sha"], "branch": b, "main": False,
                        "detached": False})
        sig = {}
        for w in wtl:
            ss = [s for s in self.sess if s["cwd"] == w["path"]]
            tok = sum(int(s["ctx"] * 180) for s in ss)
            sig[w["path"]] = {"cyc": tok, "day": tok, "share": round(100.0 * tok / 212_400_000, 1),
                              "last": a - min([s["age"] for s in ss] or [3600]),
                              "dirty": {"web": 3, "cart": 2, "inv": 1}.get(ss[0]["k"] if ss else "", 0),
                              "chg": a - 120, "ahead": None if w["main"] else len(self._chain(cm, w["head"], g["base"])),
                              "behind": None if w["main"] else 0, "base": "" if w["main"] else g["main"]}
        return 200, {"ok": True, "remote": [{"name": "origin", "host": "git.example.com", "fetchAt": a - 2 * H}],
                     "fetchStaleH": 24, "cwd": cwd, "repo": repo, "head": g["head"], "detached": False,
                     "branches": brs, "commits": cm,
                     "flow": {"develop": "develop" if repo == "billing-api" else None, "master": "main",
                              "prefix": {"feature": "feature/", "bugfix": "bugfix/", "release": "release/",
                                         "hotfix": "hotfix/", "support": "support/"}, "src": "default"},
                     "worktrees": wtl, "wtSig": sig,
                     "wtTok": {"total": 212_400_000, "start": a - 3 * H, "partial": False, "mid": a - 12 * H,
                               "dayCov": a - 3 * H, "dayPartial": False},
                     "wtStaleDays": 7, "truncated": False, "ms": 18, "wtOrder": self._wt_order(wtl, sig)}

    def _wt_order(self, wtl, sig):
        from sidereus.git_wt import wt_order   # same sorter as the real server (no poll-side order in the demo)
        st = self.state()
        return wt_order(wtl, sig, st["sessions"], st["attention"]["rows"])

    @staticmethod
    def _chain(cm, sha, stop):
        by = {c["sha"]: c for c in cm}
        out = []
        while sha and sha != stop and sha in by:
            out.append(sha)
            ps = by[sha]["parents"]
            sha = ps[0] if ps else None
        return out

    def git_links(self, repo_path, shas):
        repo = self._repo_of(repo_path)
        if not repo:
            return {"ok": True, "busy": False, "links": {}, "n": 0, "ms": 1}
        g = self.graph[repo]
        owner = {"acme-web": {"feature/checkout-redesign": "web", "bugfix/cart-rounding": "cart"},
                 "billing-api": {"feature/invoice-pdf": "inv", "feature/webhook-retry": "bill"},
                 "docs-site": {"feature/search-index": "search"}}[repo]
        links = {}
        for bname, k in owner.items():
            s = self.by[k]
            for sha in self._chain(g["commits"], g["tips"][bname], g["base"]):
                if sha in shas:
                    c = next(x for x in g["commits"] if x["sha"] == sha)
                    links[sha] = {"sid": s["sid"], "agent": "", "proj": s["proj"], "ts": c["ts"],
                                  "tok": 1_800_000 + int(sha[:3], 16) * 900, "usd": round(1.1 + int(sha[:2], 16) / 60, 2),
                                  "tid": "sess:%s|%s" % (s["cwd"], s["sid"]), "cwd": s["cwd"], "how": "subj"}
        return {"ok": True, "busy": False, "links": links, "n": len(links), "ms": 4}

    def git_commit(self, repo_path, sha):
        repo = self._repo_of(repo_path)
        c = None
        if repo:
            c = next((x for x in self.graph[repo]["commits"] if sha and x["sha"].startswith(sha[:7])), None)
        if not c:
            return 404, {"ok": False, "msg": "unknown commit"}
        files = [{"path": "src/%s.ts" % w, "add": 12 + len(w), "del": len(w) % 5, "bin": False}
                 for w in c["subject"].lower().replace(":", "").split()[:3]]
        return 200, {"ok": True, "sha": c["sha"] + "0" * 33, "parents": [p + "0" * 33 for p in c["parents"]],
                     "author": "Demo Dev", "email": "dev@example.com", "at": c["ts"], "msg": c["subject"],
                     "files": files, "nfiles": len(files)}

    def git_owners(self, cwd):
        own = {}
        if cwd in (REPOS["acme-web"][0], REPOS["acme-web"][1][0][0]):
            w, c = self.by["web"], self.by["cart"]
            own["src/cart/total.ts"] = [{"sid8": w["id"], "proj": "acme-web", "agent": "", "ago": 300, "live": True},
                                        {"sid8": c["id"], "proj": "acme-web.wt", "agent": "", "ago": 240, "live": True}]
            own["src/checkout/Form.tsx"] = [{"sid8": w["id"], "proj": "acme-web", "agent": "general-purpose",
                                             "ago": 40, "live": True}]
        return {"ok": True, "cwd": cwd, "owners": own, "warn": [], "conflictMin": 30}

    def git_wtfiles(self, cwd):
        f = {REPOS["acme-web"][0]: [("M", "src/checkout/Form.tsx"), ("M", "src/checkout/steps.ts"),
                                    ("M", "src/cart/total.ts")],
             REPOS["acme-web"][1][0][0]: [("M", "src/cart/total.ts"), ("A", "src/cart/total.test.ts")],
             REPOS["billing-api"][1][0][0]: [("M", "src/invoice/pdf.ts")]}.get(cwd, [])
        return {"ok": True, "cwd": cwd, "files": [{"st": s, "path": p} for s, p in f], "n": len(f)}

    # «Review» queue: two finished sessions with unreviewed uncommitted files. (st, path, add, del, reviewed)
    _REVIEW = {"inv": [("M", "src/invoice/pdf.ts", 48, 12, True), ("A", "src/invoice/taxLines.ts", 96, 0, False),
                       ("M", "src/routes/invoices.ts", 7, 3, False)],
               "docs": [("M", "content/quickstart.md", 31, 18, False), ("M", "content/install.md", 5, 2, False)]}

    def review(self, sessions):
        bs, rows = {s["sid"]: s for s in sessions if s.get("sid")}, []
        for k, fs in self._REVIEW.items():
            s = self.by[k]
            rows.append({"sid": s["sid"], "cwd": s["cwd"], "root": s["cwd"], "branch": s["branch"], "nf": len(fs),
                         "add": sum(f[2] for f in fs), "del": sum(f[3] for f in fs), "done": False,
                         "since": int(self.now() - bs[s["sid"]]["ageSec"])})
        return {"n": len(rows), "rows": rows}

    def review_files(self, cwd, sid):
        k = next((s["k"] for s in self.sess if s["sid"] == sid and s["cwd"] == cwd), "")
        fs = self._REVIEW.get(k, [])
        return {"ok": True, "files": [{"path": p, "st": st, "add": a, "del": d, "rv": rv} for st, p, a, d, rv in fs],
                "sig": sid.replace("-", "")[:16] if fs else "", "done": False}

    @staticmethod
    def _patch(st, path):
        """A short made-up unified diff for one review file (M: 3 old lines -> 4 new, A: 4 new lines)."""
        new = ["// %s: demo change %d" % (path.rsplit("/", 1)[-1], i) for i in range(1, 5)]
        if st == "A":
            return ("diff --git a/%s b/%s\nnew file mode 100644\nindex 0000000..3f2a1c9\n--- /dev/null\n+++ b/%s\n"
                    "@@ -0,0 +1,4 @@\n" % (path, path, path)) + "".join("+%s\n" % x for x in new)
        return ("diff --git a/%s b/%s\nindex 8c1d2e4..3f2a1c9 100644\n--- a/%s\n+++ b/%s\n@@ -10,5 +10,6 @@\n"
                " import { money } from './money';\n \n-// old total\n-const round = (n) => n;\n+%s\n+%s\n+%s\n"
                " export default round;\n" % (path, path, path, path, new[0], new[1], new[2]))

    def git_diff(self, cwd):
        """Demo `GET /api/git/diff` (patch view): review files of the session at `cwd`, same keys as git_view.git_diff."""
        k = next((k for k in self._REVIEW if self.by[k]["cwd"] == cwd), "")
        body = "".join(self._patch(st, p) for st, p, _a, _d, _rv in self._REVIEW.get(k, []))
        return {"ok": True, "cwd": cwd, "scope": "Working tree (uncommitted)", "scopeBase": "", "scopeKey": "work", "hasUp": False, "stat": "",
                "diff": body, "cutBytes": 0, "unpushed": [], "pushed": [], "pushedAll": 0, "pushedWin": "today"}

    # Uncommitted trees per worktree for the timeline rail (/api/git/diff?view=rail). (st, path, old?)
    # ⚠Superset of git_wtfiles for the same cwd, so the branch tab and the rail agree.
    _RAIL_FILES = {
        "acme-web": [("M", "src/checkout/Form.tsx"), ("M", "src/checkout/steps.ts"), ("M", "src/cart/total.ts"),
                     ("A", "src/checkout/validation/rules.ts"), ("A", "src/checkout/validation/messages.ts"),
                     ("R", "src/components/forms/TextField.tsx", "src/components/Input.tsx"),
                     ("M", "src/components/forms/ErrorHint.tsx"), ("M", "src/routes/checkout.tsx"),
                     ("D", "src/checkout/legacyValidate.ts"), ("A", "tests/checkout/validation.test.ts"),
                     ("M", "tests/checkout/Form.test.tsx")],
        "acme-web.wt": [("M", "src/cart/total.ts"), ("A", "src/cart/total.test.ts"), ("M", "src/cart/lineItem.ts"),
                        ("M", "src/lib/money.ts")],
        "billing-api": [("M", "src/webhooks/retry.ts"), ("A", "src/webhooks/backoff.ts"),
                        ("M", "src/webhooks/dispatcher.ts"), ("M", "src/config/defaults.ts"),
                        ("A", "tests/webhooks/backoff.test.ts")],
        "billing-api.wt": [("M", "src/invoice/pdf.ts"), ("A", "src/invoice/taxLines.ts"),
                           ("R", "src/invoice/templates/layout.ts", "src/invoice/template.ts"),
                           ("M", "src/routes/invoices.ts"), ("D", "src/invoice/htmlExport.ts"),
                           ("A", "tests/invoice/__snapshots__/pdf.snap"), ("M", "tests/invoice/pdf.test.ts")],
        "docs-site": [],
        "docs-site.wt": [("A", "src/search/indexer.ts"), ("A", "src/search/tokenize.ts"),
                         ("M", "src/routes/search.tsx"), ("M", "src/components/SearchBox.tsx"),
                         ("M", "package.json")],
    }

    # Files only in commits since the base (start/remote modes); shown with the uncommitted ones.
    _RAIL_COMMITTED = {
        "acme-web": [("A", "src/checkout/steps/Layout.tsx"), ("M", "src/checkout/CardForm.tsx"),
                     ("A", "src/checkout/address/autocomplete.ts")],
        "acme-web.wt": [("M", "src/cart/round.ts")],
        "billing-api.wt": [("A", "src/invoice/render.ts"), ("M", "src/invoice/totals.ts")],
        "docs-site.wt": [("A", "src/search/build.ts"), ("A", "src/routes/results.tsx")],
    }

    def _rail_own(self, cwd, files, dirty):
        """Demo `own`/`conflict` (git_rail._rail_owners shape): the worktree's session and its subagents, latest first.
        ★src/cart/total.ts is edited by both acme-web sessions (same pair as git_owners) -> the «Conflict» example."""
        s = next((x for x in self.sess if x["cwd"] == cwd), None)
        if not s:
            return
        def unit(ss, sub, n, ago):
            return {"sid8": ss["id"], "sid": ss["sid"], "cwd": ss["cwd"], "main": sub is None, "proj": ss["proj"],
                    "tid": sub["tid"] if sub else "", "lab": sub["desc"] if sub else "",
                    "agent": sub["type"] if sub else "", "n": n, "ago": ago}
        subs = [x for x in self.subs if x["k"] == s["k"]]
        who = [None] + subs[::-1]
        for i, f in enumerate(files):
            if i % 4 == 3:
                continue                 # some files have no recorded editor (edited outside a watched session)
            sub = who[i % len(who)]
            own = [unit(s, sub, 1 + (i * 3) % 7, 60 + i * 170)]
            if i % 3 == 0 and sub is not None:
                own.append(unit(s, None, 2, 400 + i * 200))
            f["own"] = own
        pair = {REPOS["acme-web"][0]: self.by["cart"], REPOS["acme-web"][1][0][0]: self.by["web"]}.get(cwd)
        for f in files:
            if pair and f["path"] == "src/cart/total.ts" and f["path"] in dirty:
                f["own"] = sorted([unit(s, None, 4, 300 if s["k"] == "web" else 240),
                                   unit(pair, None, 3, 240 if s["k"] == "web" else 300)], key=lambda o: o["ago"])
                f["conflict"] = True

    def git_rail(self, cwd, mode="auto", sid=""):
        """Demo `_git_rail` shape: branch header, numstat files vs the base mode, commits, owner lines.
        auto -> remote (every demo repo has origin); start -> the session's start; head -> uncommitted only."""
        repo = self._repo_of(cwd)
        if not repo:
            return {"ok": False, "msg": "Only repositories touched by a session on screen can be viewed."}
        g, (main, wts) = self.graph[repo], REPOS[repo]
        is_main = cwd == main
        br = g["head"] if is_main else dict(wts)[cwd]
        cm = g["commits"]
        by = {c["sha"]: c for c in cm}
        tip = g["tips"].get(br) or next((c["sha"] for c in cm if br in c["refs"]), cm[0]["sha"])
        if mode not in ("head", "start", "remote", "upstream"):   # ⚠same whitelist as git_rail.RAIL_MODES
            mode = "remote"
        chain, sha = [], tip
        while sha in by:
            chain.append(by[sha])
            sha = (by[sha]["parents"] or [None])[0]
        ss = next((x for x in self.sess if x["sid"] == sid), None) or next((x for x in self.sess if x["cwd"] == cwd), None)
        base, kind, ref, since, no_remote = "", "head", "", 0, False
        if mode == "upstream":   # the branch's own remote (like _rail_base); unpushed -> session start, noRemote
            o = next((c for c in chain if "origin/" + br in c["refs"]), None)
            if o:
                base, kind, ref = o["sha"], "remote", "origin/" + br
            else:
                no_remote = True
        if (mode == "start" or no_remote) and ss:
            hit = next((c for c in chain if c["ts"] <= ss["born"]), None)
            if hit:
                base, kind, ref, since = hit["sha"], "start", br, ss["born"]
        elif mode == "remote":
            if br != g["main"]:
                base, kind, ref = g["base"], "branch", "origin/" + g["main"]
            else:
                o = next((c for c in chain if "origin/" + br in c["refs"]), None)
                base, kind, ref = (o["sha"] if o else tip), "remote", "origin/" + br
        since_base = []
        if base:
            for c in chain:
                if c["sha"] == base:
                    break
                since_base.append(c)
        commits = [{"sha": c["sha"], "at": c["ts"], "msg": c["subject"]} for c in (since_base or chain)[:5]]
        # ⚠Upstream/ahead come from the graph's origin/<br> ref so the branch tab agrees; no ref = unpushed branch.
        up = "origin/" + br
        has_up = any(up in c["refs"] for c in cm)
        ahead, sha = 0, tip
        while has_up and sha in by and up not in by[sha]["refs"]:
            ahead += 1
            sha = (by[sha]["parents"] or [None])[0]
        r = random.Random(SEED + len(cwd))  # nosec B311 -- seeded demo data / retry jitter, not a secret
        files = []
        key = repo if is_main else repo + ".wt"
        dirty = {rec[1] for rec in self._RAIL_FILES[key]}
        extra = self._RAIL_COMMITTED.get(key, []) if since_base else []
        for rec in self._RAIL_FILES[key] + [x for x in extra if x[1] not in dirty]:
            st, path = rec[0], rec[1]
            add = 0 if st == "D" else (r.randint(18, 140) if st == "A" else r.randint(2, 60))
            dl = r.randint(10, 90) if st == "D" else (0 if st == "A" else r.randint(0, 25))
            if st == "R":
                add, dl = r.randint(1, 8), r.randint(0, 4)
            f = {"path": path, "st": st, "add": add, "del": dl, "bin": False}
            if st == "R":
                f["old"] = rec[2]
            files.append(f)
        self._rail_own(cwd, files, dirty)
        return {"ok": True, "cwd": cwd, "view": "rail", "hasUp": has_up, "n": len(files),
                "add": sum(f["add"] for f in files), "del": sum(f["del"] for f in files), "files": files,
                "untracked": 0, "commits": commits, "branch": br, "upstream": up if has_up else "",
                "ahead": ahead, "behind": 0, "base": base, "baseKind": kind, "baseRef": ref, "baseMode": mode,
                "noRemote": no_remote, "since": since, "nCommits": len(since_base), "commitsCut": False,
                "dirty": len(dirty)}
