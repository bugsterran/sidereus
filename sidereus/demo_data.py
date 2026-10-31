"""Demo world fixtures and tab payloads for `chat_server.py --demo` (split out of sidereus/demo.py).

Owns the fixed synthetic data (ROOT, SEED, REPOS, GEM_ROW, CU_ROW, CP_ROW, CX, ...), the id/time helpers, and `_WorldPanels` —
the per-tab payload builders (quota, tokens, timeline, history, retro, work logs) that `World` inherits.
Branch/git payloads are in sidereus/demo_git.py (`_WorldGit`, imports from here).
⚠Imported only by sidereus/demo.py (itself lazy, under --demo). Never import sidereus.demo from here (cycle).
⚠Keep it 100% synthetic — tests/test_demo.py scans every response against a denylist.
"""
import random
import time
from datetime import datetime, timezone

ROOT = "/home/demo/src"
SEED = 20260924
_DEMO_TARG = {"Edit": "src/checkout/Form.tsx", "Grep": "AddressInput", "Bash": "npm run build:index"}   # work-popup targets per tool
H = 3600
DEMO_TITLES = {"web": "Checkout redesign with inline validation", "cart": "Fix cart total rounding drift",
               "bill": "Webhook retry backoff for billing", "inv": "Invoice PDF layout and tax lines",
               "docs": "Rewrite the docs quickstart"}

# repo name -> (main worktree path, extra worktrees [(path, branch)])
REPOS = {
    "acme-web": (ROOT + "/acme-web", [(ROOT + "/acme-web.wt/cart-rounding", "bugfix/cart-rounding")]),
    "billing-api": (ROOT + "/billing-api", [(ROOT + "/billing-api.wt/invoice-pdf", "feature/invoice-pdf")]),
    "docs-site": (ROOT + "/docs-site", [(ROOT + "/docs-site.wt/search-index", "feature/search-index")]),
}


# Synthetic Gemini CLI session — same key set as sidereus/ext.py ext_rows(); cwd/ageSec are set per poll.
GEM_ROW = {
    "id": "7f3e21c0", "sid": "7f3e21c0-4b1d-4e8a-9c55-2d0a6b91e4f7", "project": "docs-site", "gotPrompt": 0,
    "creq": 0, "burn": 0, "rpm": 0, "cwd": "", "branch": "", "tool": "", "targ": "", "sub": [], "bgs": [],
    "mon": [], "runmin": {"sub": 0, "bg": 0, "run": 38}, "kind": "gemini", "ageSec": 0, "bytes": 0, "repos": [],
    "mbox": "", "mboxSrc": "", "cost": 0, "ctx": 0, "model": "gemini-2.5-pro", "win": 0, "winSrc": "", "winN": 0,
    "git": "", "state": "wait", "blocked": "", "otel": True, "otelEv": "wait", "otelAt": 0,
    "err": False, "plat": "gm", "tok": 1_284_600,
    "tokSplit": {"in": 402_100, "out": 61_300, "cache": 779_800, "thought": 41_400},
    "estCost": 1.63, "costMiss": 0,      # gemini-2.5-pro rates on tokSplit, all requests under 200k
}


def _nohook_row(plat, kind, sid, project, model, run):
    """Hook-less external row (sidereus/ext.py ext_rollout_rows key set): lights «Hooks not connected» in the demo."""
    return {"id": sid[:8], "sid": sid, "project": project, "gotPrompt": 0, "creq": 0, "burn": 0, "rpm": 0,
            "cwd": "", "branch": "", "tool": "", "targ": "", "sub": [], "bgs": [], "mon": [],
            "runmin": {"sub": 0, "bg": 0, "run": run}, "kind": kind, "ageSec": 0, "bytes": 0, "repos": [],
            "mbox": "", "mboxSrc": "", "cost": 0, "ctx": 0, "model": model, "win": 0, "winSrc": "", "winN": 0,
            "git": "", "state": "unknown", "blocked": "", "otel": False, "otelEv": "", "otelAt": 0,
            "err": False, "plat": plat, "tok": 0, "tokSplit": {"in": 0, "out": 0, "cache": 0, "thought": 0},
            "estCost": None, "costMiss": 0, "goneWhy": "", "pid": 0, "rollout": True}


CU_ROW = _nohook_row("cu", "cursor", "5d2c8e14-7a3f-4b09-8e61-c4f0a2b9d375", "acme-web", "gpt-5", 12)
CP_ROW = _nohook_row("cp", "copilot", "9a4f0b37-2e6d-4c18-b5a2-1f7e3c8d6b04", "billing-api", "claude-sonnet-4.5", 7)
# Demo GET /api/hooks/connect rows (hook_connect.listing() shape): both CLIs installed, hooks missing.
HOOKS_CONNECT = [
    {"plat": "cursor", "name": "Cursor", "state": "missing", "file": "~/.cursor/hooks.json", "can": True,
     "why": "", "approve": ""},
    {"plat": "copilot", "name": "Copilot", "state": "missing", "file": "~/.copilot/hooks/sidereus.json",
     "can": True, "why": "", "approve": ""},
]
_HC_CMD = "/usr/bin/python3 /home/demo/.sidereus/ext-hooks/ext_hook.py --platform "
_HC_EV = {"cursor": ("sessionStart", "beforeSubmitPrompt", "stop"), "copilot": ("SessionStart", "UserPromptSubmit", "Stop")}


def hooks_connect_dry(plat):
    """Demo dry reply of hook_connect.connect() {ok, diff, base, adds}: Sidereus entries added to a new file.
    ⚠Without `diff` 90f-hookconn.js shows «Already connected» for a CLI that is not connected."""
    shown = next(x["file"] for x in HOOKS_CONNECT if x["plat"] == plat)
    ent = (lambda e: '{"command": "%s%s"}' % (_HC_CMD, plat)) if plat == "cursor" else \
        (lambda e: '{"type": "command", "bash": "%s%s", "timeoutSec": 5}' % (_HC_CMD, plat))
    body = ['{', '  "version": 1,', '  "hooks": {']
    evs = _HC_EV[plat]
    for i, e in enumerate(evs):
        body += ['    "%s": [' % e, '      ' + ent(e), '    ]' + ("," if i < len(evs) - 1 else "")]
    body += ['  }', '}']
    diff = ["--- " + shown, "+++ " + shown, "@@ -1,0 +1,%d @@" % len(body)] + ["+" + x for x in body]
    return {"ok": True, "diff": "\n".join(diff) + "\n", "base": "", "adds": len(evs)}


# Synthetic Codex CLI usage (timeline row + extUsage.cx with plan windows); no session row, so the drawer count stays 9.
CX = {"sid": "3c9e5a71-8d20-4f6b-a1e4-7b0c2d9f5e38", "id": "3c9e5a71", "model": "gpt-5-codex",
      "tokSplit": {"in": 318_400, "out": 42_700, "cache": 1_106_200, "thought": 0}, "estCost": 0.87}
CX["tok"] = sum(CX["tokSplit"].values())
DEMO_WT = {"web": [4, 1380], "cart": [2, 420], "bill": [3, 660]}   # session row `wt` = timeline._tl_sess_row
# One `gemini -p` run launched from the billing session (ext-hooks/ask-gemini) — a timeline child row.
GEM_CHILD = {"sid": "b41d7e09-2c6a-4f3e-8d15-9a0e6c3b7f24", "model": "gemini-2.5-flash", "tok": 48_200}


def _tl_acct(k):
    """Timeline `acct` key for one demo session — same extra-root sessions as demo.World's session rows."""
    return {"acct": "work"} if k in ("docs", "search") else {}


def _hex(rng, n):
    return "".join(rng.choice("0123456789abcdef") for _ in range(n))


def _uuid(rng):
    h = _hex(rng, 32)
    return "%s-%s-4%s-a%s-%s" % (h[:8], h[8:12], h[13:16], h[17:20], h[20:32])


def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _local_iso(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%S")


def _walk(hs, k, step):
    """End bucket of the hour run through k going `step` (±H) — sidereus/history._cross without its live imports."""
    while k + step in hs:
        k += step
    return k


class _WorldPanels:
    """Tab payload builders mixed into demo.World (needs self.a/sess/subs/by/graph/segs, now(), state())."""

    # ───────────────────────────── quota
    def quota(self):
        now, a = self.now(), self.a
        reset = a + 2 * H + 10 * 60
        wk_reset = a + 3 * 24 * H + 5 * H
        return {"at": now, "age": 40, "err": None, "src": "api",
                "five_hour": {"pct": 55.0, "resets_at": datetime.fromtimestamp(reset, timezone.utc).isoformat(),
                              "leftSec": reset - now, "_reset": reset},
                "seven_day": {"pct": 38.0, "resets_at": datetime.fromtimestamp(wk_reset, timezone.utc).isoformat(),
                              "leftSec": wk_reset - now},
                # One extra signed-in root so the popover's «Other accounts» rows show in the demo.
                "accounts": [{"label": "work", "age": 60, "err": None,
                              "five_hour": {"pct": 22.0, "resets_at": datetime.fromtimestamp(reset + 50 * 60, timezone.utc).isoformat(),
                                            "leftSec": reset + 50 * 60 - now},
                              "seven_day": {"pct": 61.0, "resets_at": datetime.fromtimestamp(wk_reset - 30 * H, timezone.utc).isoformat(),
                                            "leftSec": wk_reset - 30 * H - now}}]}

    def quota_who(self):
        rows, tot = [], 0
        share = {"acme-web": 0.46, "billing-api": 0.38, "docs-site": 0.16}
        total = 212_400_000
        for repo, sh in share.items():
            ss = [s for s in self.sess if s["repo"] == repo]
            tok = int(total * sh)
            rows.append({"name": repo, "tok": tok, "share": round(sh * 100, 1), "n": len(ss),
                         "sids": [{"sid": s["id"], "tok": tok // len(ss)} for s in ss]})
            tot += tok
        q = self.quota()
        return {"start": q["five_hour"]["_reset"] - 5 * H, "exact": True, "total": tot, "rows": rows, "others": 0,
                "partial": False, "since": q["five_hour"]["_reset"] - 5 * H}

    def quota_burn(self):
        now, q = self.now(), self.quota()
        reset = q["five_hour"]["_reset"]
        start = reset - 5 * H
        el = now - start
        pts, t = [], start + 400
        while t <= now:
            f = (t - start) / max(1, el)
            pts.append([t, round(55 * (f ** 1.08), 1)])
            t += 240
        if not pts or pts[-1][0] != now:
            pts.append([now, 55.0])
        base = [[s, round(100 * (s / (5 * H)) ** 1.15 * 0.97, 1)] for s in range(300, 5 * H, 300)]
        band = [[s, round(v * 0.85, 1), round(min(100, v * 1.12), 1)] for s, v in base[2:]]
        rate = 55 / (el / H)
        return {"ok": True, "at": now,
                "cur": {"start": start, "reset": reset, "now": now, "now_pct": 55.0, "left": reset - now,
                        "elapsed": el, "age": 40, "rate_pph": round(rate, 2), "pts": pts},
                "proj": {"pct": 91.0, "raw": 91.4, "over_at": None, "over_in": None},
                "base": {"n": 6, "pts": base, "band": band, "bw": 15.0, "band_n": 5, "why": None},
                "head": {"tok": 173_700_000, "used": 212_400_000, "per_pct": 3_862_000, "lim": 386_000_000,
                         "src": "win", "tph": 75_000_000, "room": 1.1,
                         "wk": {"used": 1_310_000_000, "lim": 3_450_000_000, "pct": 38.0, "left": q["seven_day"]["leftSec"],
                                "src": "cyc", "lo": 3_400_000_000, "hi": 3_500_000_000, "unc": 0.013},
                         "eff": 173_700_000, "cap": "5h", "unc": 0.062, "unc_n": 6},
                "delta": -9.0, "wk": {"now_pct": 38.0, "left": q["seven_day"]["leftSec"]}}

    # ───────────────────────────── tokens tab
    def _live(self):
        r = random.Random(SEED + 7 + (self.now() // 10) % 6)  # nosec B311 -- seeded demo data / retry jitter, not a secret
        return [r.randint(180, 900) * 1000 if i % 7 else 0 for i in range(60)]

    def live(self):
        return {"live": self._live(), "liveSec": 600, "liveStep": 10, "at": self.now()}

    def _agc_top(self, nd):
        """Demo `agc.top[nd]` (agentcost._agc_rows shape): costliest subagent runs; tid = "<toolUseId>|<sid>" opens the popup."""
        a = self.a
        runs = [s for s in self.subs if s["start"] >= a - (6 * H if nd == 1 else 7 * 24 * H)]
        runs.sort(key=lambda s: -s["tk"])
        tot = sum(s["tk"] for s in runs) + (0 if nd == 1 else 38_000_000)   # 7d: older runs outside the demo day
        out = []
        for s in runs[:5]:
            ss = self.by[s["k"]]
            out.append({"tok": s["tk"], "desc": s["desc"], "type": s["type"], "proj": ss["proj"], "cwd": ss["cwd"],
                        "tid": s["tid"] + "|" + ss["sid"], "dur": s["end"] - s["start"], "end": s["end"],
                        "share": round(s["tk"] / tot * 100, 1)})
        return out

    def wkuse(self, rng_days=7, acct=""):
        a, now = self.a, self.now()
        acct = acct if acct in ("personal", "work") else ""
        r = random.Random(SEED + 3)  # nosec B311 -- seeded demo data / retry jitter, not a secret
        days = [datetime.fromtimestamp(a - (6 - i) * 24 * H).strftime("%Y-%m-%d") for i in range(7)]
        per = {"acme-web": [r.randint(40, 260) * 10 ** 6 for _ in days],
               "billing-api": [r.randint(30, 200) * 10 ** 6 for _ in days],
               "docs-site": [r.randint(5, 70) * 10 ** 6 for _ in days]}
        per["acme-web"][2] = 0
        if acct:     # «Period totals» account pick: work = these two repos, personal = the rest (sums to All)
            per = {k: v for k, v in per.items() if (k in ("docs-site", "billing-api")) == (acct == "work")}
        rows = [{"slug": "-home-demo-src-" + k, "name": k, "tok": sum(v), "cost": round(sum(v) * 5.6e-7, 2),
                 "days": sum(1 for x in v if x)} for k, v in per.items()]
        total = sum(x["tok"] for x in rows)
        daily = [{"d": d, "tok": sum(v[i] for v in per.values()),
                  "cost": round(sum(v[i] for v in per.values()) * 5.6e-7, 2),
                  # same shape as burn_usage._wk_daily: top 2 projects of the day, >0 only
                  "top": [{"name": k, "tok": v[i]} for k, v in
                          sorted(per.items(), key=lambda kv: (-kv[1][i], kv[0])) if v[i] > 0][:2]}
                 for i, d in enumerate(days)]
        hrs = datetime.fromtimestamp(now).hour + 1
        intr = []
        for k, sc in (("acme-web", 1.0), ("billing-api", 0.8), ("docs-site", 0.3)):
            ser = [0 if h < max(0, hrs - 7) else int(r.randint(4, 30) * 10 ** 6 * sc) for h in range(hrs)]
            intr.append({"name": k, "tok": sum(ser), "series": ser})
        subs = [{"proj": s["k"] and self.by[s["k"]]["repo"], "type": s["type"], "desc": s["desc"],
                 "depth": s["depth"], "req": s["tc"], "run": s["run"]} for s in self.subs]
        return {"at": now, "rows": rows, "total": total, "days": 7, "err": "", "daily": daily,
                "trend": [{"name": x["name"], "slug": x["slug"], "tok": x["tok"], "series": per[x["name"]]}
                          for x in rows],
                "mix": {"in": 41_000, "out": int(total * 0.0026), "cc": int(total * 0.027),
                        "cr": int(total * 0.97), "tot": total, "ratio": 36.2},
                "models": [{"name": "claude-opus-5", "tok": int(total * 0.71), "cost": round(total * 0.71 * 6.9e-7, 2)},
                           {"name": "claude-sonnet-5", "tok": int(total * 0.27), "cost": round(total * 0.27 * 2.8e-7, 2)},
                           {"name": "claude-haiku-4-5", "tok": int(total * 0.02), "cost": round(total * 0.02 * 9e-8, 2)}],
                "cost": round(total * 5.6e-7, 2), "range": rng_days, "ranges": [1, 7, 30], "acct": acct,
                "liveAdd": 0 if acct else 4_200_000, "today": days[-1], "live": self._live(),
                "liveTop": [{"name": "acme-web", "tok": 3_100_000, "per": 310_000},
                            {"name": "docs-site", "tok": 900_000, "per": 90_000}],
                "intraday": {"at": now, "by": intr, "h0": 0, "h1": hrs - 1, "cut": True},
                "burn": {"at": now, "min": 60,
                         "rows": [{"name": "acme-web (서브에이전트)", "ctx": 31_200_000, "req": 214, "med": 121_000, "per": 520_000},
                                  {"name": "acme-web", "ctx": 18_400_000, "req": 61, "med": 301_000, "per": 306_000},
                                  {"name": "billing-api", "ctx": 12_100_000, "req": 44, "med": 275_000, "per": 201_000},
                                  {"name": "docs-site (서브에이전트)", "ctx": 6_300_000, "req": 70, "med": 90_000, "per": 105_000}],
                         "subs": subs,
                         "sess": [{"proj": s["repo"], "id": s["id"], "born": s["born"], "new": True, "win": 450000}
                                  for s in self.sess],
                         "tot": 68_000_000, "settingsAt": a - 2 * 24 * H, "win": 450000,
                         "winPrev": 200000, "winApprox": True},
                "agc": {"at": now, "rows": [
                    {"type": "general-purpose", "n": 142, "tok": 820_000_000, "cost": 510.2, "avg": 5.77, "last": a - 300},
                    {"type": "Explore", "n": 96, "tok": 210_000_000, "cost": 88.4, "avg": 2.19, "last": a - 700},
                    {"type": "code-reviewer", "n": 31, "tok": 140_000_000, "cost": 79.1, "avg": 4.52, "last": a - 800}],
                    "sub": 677.7, "subtok": 1_170_000_000, "all": 1410.3, "alltok": 2_390_000_000, "n": 269,
                    "types": 3, "ms": 12, "top": {"1": self._agc_top(1), "7": self._agc_top(7)}},
                "liveSec": 600, "liveStep": 10, "busy": False}

    # ───────────────────────────── timeline
    def timeline(self, hours=12.0):
        now, a = self.now(), self.a
        t0 = now - int(hours * H)
        step = 180
        n = int(hours * H) // step + 1
        r = random.Random(SEED + 11)  # nosec B311 -- seeded demo data / retry jitter, not a secret
        rows = []
        v = [0] * n
        for s in self.sess:
            segs = [[a - s0 * 60, a - s1 * 60 if s1 else now] for s0, s1 in self.segs[s["k"]]]
            segs = [[max(x, t0), y] for x, y in segs if y > t0]
            tks = [r.randint(2, 18) * 10 ** 6 for _ in segs]
            for (x, y), tk in zip(segs, tks):
                i0, i1 = max(0, (x - t0) // step), min(n - 1, (y - t0) // step)
                for i in range(i0, i1 + 1):
                    v[i] += tk // max(1, i1 - i0 + 1)
            live = s["state"] in ("think", "tool")
            rows.append({"tid": "sess:%s|%s" % (s["cwd"], s["sid"]), "type": s["cwd"].rsplit("/", 1)[-1],
                         "desc": "세션 — " + {"web": "Redesign the checkout steps", "cart": "Fix cart rounding",
                                            "bill": "Add webhook retries", "inv": "Invoice PDF export",
                                            "docs": "Refresh the quickstart", "search": "Docs search index"}[s["k"]],
                         "segs": segs, "comp": ([{"at": a - 130 * 60, "trig": "auto", "pre": 441_000, "post": 16_200,
                                                  "drop": 424_800}] if s["k"] == "web" else []),
                         "seen": s["born"], "start": max(t0, s["born"]), "end": now if live else segs[-1][1] if segs else now,
                         "run": live, "state": s["state"], "idle": 0 if live else now - (segs[-1][1] if segs else now),
                         "blocked": "", "proj": s["proj"], "cwd": s["cwd"], "depth": 0, "kind": "sess",
                         "sid": s["sid"],   # = timeline._tl_sess_row: the timeline joins SESS[].plrun to a row by sid
                         "tk": sum(tks), "last": ((s["tool"] + " · " + s["targ"]) if s["tool"] in ("Agent", "Task")
                                                  else s["tool"]) if s["tool"] else "",
                         "tks": tks, **_tl_acct(s["k"]),
                         **({"wt": DEMO_WT[s["k"]]} if s["k"] in DEMO_WT else {})})
        # Synthetic Gemini row (same shape as timeline_ext._plat_rows for gemini); tokens stay out of the Claude strip `v`.
        gsegs = [[max(t0, a - m0 * 60), a - m1 * 60] for m0, m1 in ((96, 71), (24, 3)) if a - m1 * 60 > t0]
        if gsegs:
            gtk = [GEM_ROW["tok"] * 3 // 5, GEM_ROW["tok"] - GEM_ROW["tok"] * 3 // 5][-len(gsegs):]
            cwd = REPOS["docs-site"][0]
            rows.append({"tid": "ext:gm|" + GEM_ROW["sid"], "type": "docs-site", "desc": "Gemini — " + GEM_ROW["id"],
                         "segs": gsegs, "comp": [], "seen": gsegs[0][0], "start": gsegs[0][0], "end": gsegs[-1][1],
                         "run": False, "state": GEM_ROW["state"], "idle": now - gsegs[-1][1], "blocked": "",
                         "proj": "docs-site", "cwd": cwd, "depth": 0, "kind": "sess", "plat": "gm",
                         "model": GEM_ROW["model"], "tk": sum(gtk), "last": "", "tks": gtk})
        # Synthetic Codex top-level row and a Gemini child under the billing session (timeline_ext._ext_child shape).
        csegs = [[max(t0, a - m0 * 60), a - m1 * 60] for m0, m1 in ((58, 31),) if a - m1 * 60 > t0]
        if csegs:
            ccwd = REPOS["billing-api"][0]
            rows.append({"tid": "ext:cx|" + CX["sid"], "type": "billing-api", "desc": "Codex — " + CX["id"],
                         "segs": csegs, "comp": [], "seen": csegs[0][0], "start": csegs[0][0], "end": csegs[-1][1],
                         "run": False, "state": "wait", "idle": now - csegs[-1][1], "blocked": "",
                         "proj": "billing-api", "cwd": ccwd, "depth": 0, "kind": "sess", "plat": "cx",
                         "model": CX["model"], "tk": CX["tok"], "last": "", "tks": [CX["tok"]]})
        bs = self.by.get("bill")
        if bs and a - 12 * 60 > t0:
            g0, g1 = a - 19 * 60, a - 12 * 60
            rows.append({"tid": "ext:gm|" + GEM_CHILD["sid"], "type": "gemini -p", "aid": "", "par": "",
                         "desc": "gemini -p · " + GEM_CHILD["model"], "last": "", "segs": [[max(t0, g0), g1]],
                         "start": max(t0, g0), "end": g1, "run": False, "state": "done", "done": True,
                         "proj": bs["proj"], "cwd": bs["cwd"], "depth": 1, "plat": "gm", "model": GEM_CHILD["model"],
                         "parent": bs["sid"], "fin": 1, "tk": GEM_CHILD["tok"], "tks": [GEM_CHILD["tok"]]})
        for x in self.subs:
            s = self.by[x["k"]]
            end = now if x["run"] else x["end"]
            if end < t0:
                continue
            rows.append({"tid": x["tid"], "type": x["type"], "aid": x["aid"], "par": x["paid"], "desc": x["desc"],
                         "last": x["now"] or "SubagentHandback", "segs": [[max(t0, x["start"]), end]], "tk": x["tk"],
                         "tc": x["tc"], "fin": 0 if x["run"] else 1, "start": x["start"], "end": end,
                         "run": x["run"], "proj": s["proj"], "cwd": s["cwd"], "depth": x["depth"], "tks": [x["tk"]],
                         **_tl_acct(x["k"])})
        rows.extend(dict(w, **_tl_acct("search")) for w in self.wf_tl_rows(t0))    # workflow rows hang under «search»
        return {"ok": True, "at": now, "hours": float(hours), "peak": 5,
                "tok": {"t0": t0, "step": step, "v": v, "sum": sum(v)}, "naps": [], "idle": [], "rows": rows}

    # Branch tab + rail payloads (branches, git_*) live in sidereus/demo_git.py (_WorldGit).

    # ───────────────────────────── history / retro
    # "search" is left untitled on purpose — it shows the id fallback.
    # ⚠Rows come from hour buckets split per local day like sidereus/history.py; offsets from `a` put a row's
    #   from/to on the previous date («prev. day 21:55~prev. day 23:55»). "docs" runs 22:00-01:00 across one midnight.
    def history(self, days=7):
        a, r, nd, lt = self.a, random.Random(SEED + 5), min(days, 14), time.localtime(self.a)  # nosec B311 -- seeded demo data / retry jitter, not a secret
        mid = [int(time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday - d, 0, 0, 0, 0, 0, -1))) for d in range(15)]
        # ⚠Today's rows start at fixed local hours (oldest session 07:00, +1h each): born-derived hours shared a bucket
        #   or clamped at midnight depending on the wall clock, reordering the tab (screen_check baseline drift).
        rank = sorted(range(len(self.sess)), key=lambda j: (self.sess[j]["born"], j))
        st = {j: mid[0] + (7 + n) * H for n, j in enumerate(rank)}
        hs = [set(range(st[j], max(st[j], a // H * H) + 1, H)) for j in range(len(self.sess))]
        cx = self.sess.index(self.by["docs"])
        for d in range(1, nd):
            for i in sorted(r.sample(range(6), r.randint(2, 5))):
                h0 = mid[d] + r.randint(8, 17) * H
                if not (i == cx and d in (1, 2)):
                    hs[i].update(range(h0, h0 + r.randint(1, 5) * H, H))
        hs[cx].update((mid[2] + 22 * H, mid[2] + 23 * H, mid[1]))
        agg, byd, lst, n = {}, {}, [], 0
        for i, ks in enumerate(hs):
            for ki in sorted(k for k in ks if k >= mid[nd - 1]):
                g = agg.setdefault((time.strftime("%Y-%m-%d", time.localtime(ki)), i), [ki, ki, 0])
                g[1], g[2] = ki, g[2] + 1
        for (date, i), (frm, last, nh) in sorted(agg.items()):
            s, ks, tok = self.sess[i], hs[i], r.randint(8, 90) * 10 ** 6
            byd.setdefault(date, []).append({
                "date": date, "sid": s["sid"], "id": s["id"], "slug": "-home-demo-src-" + s["repo"],
                "cwd": s["cwd"], "project": s["repo"], "plat": "cc", "model": s["model"], "models": 1,
                "from": frm, "to": last + H, "hours": nh, "tok": tok, "cost": round(tok * 5.6e-7, 4),
                "sub": len(self._sess_subs(s["k"])), "title": DEMO_TITLES.get(s["k"], ""), "branch": s["branch"],
                "runFrom": _walk(ks, frm, -H) if frm - H in ks else None,
                "runTo": _walk(ks, last, H) + H if last + H in ks else None, **_tl_acct(s["k"])})
        for d in range(nd):
            date = time.strftime("%Y-%m-%d", time.localtime(mid[d]))
            rows = sorted(byd.get(date, []), key=lambda x: (-x["from"], -x["to"]))
            n += len(rows)
            lst.append({"date": date, "n": len(rows), "tok": sum(x["tok"] for x in rows),
                        "cost": round(sum(x["cost"] for x in rows), 4), "rows": rows})
            if d == 1:     # one synthetic Gemini history row, in its own `gm` block like sidereus/history.py
                gs = self.sess[0]
                g = {"date": date, "sid": "7f3a9c2e-5b41-4d8e-9a06-2c1e8b4f6d10", "id": "7f3a9c2e", "slug": "",
                     "cwd": gs["cwd"], "project": gs["repo"], "plat": "gm", "model": "gemini-2.5-flash",
                     "models": 1, "from": mid[1] + 14 * H, "to": mid[1] + 16 * H, "hours": 2, "tok": 16420,
                     "cost": 0, "estCost": 0.0112, "costMiss": 0, "sub": 0, "title": "", "branch": "",
                     "runFrom": None, "runTo": None}
                lst[-1]["gm"] = {"n": 1, "tok": g["tok"], "estCost": g["estCost"], "costMiss": 0, "rows": [g]}
        return {"ok": True, "days": days, "at": float(a), "n": n, "list": lst, "ms": 3}

    def recent(self, days=7):
        """Demo `GET /api/sessions/recent` — 3 fictional ended sessions, same keys as sidereus/recent.py."""
        a, rows = self.a, []
        for i, (sid, cwd, name, br, mdl, ago_h, ctx) in enumerate((
                ("5d2e8a41-7c3b-4f90-8e16-3a9b0c4d7e21", REPOS["acme-web"][1][0][0], "acme-web", "bugfix/cart-rounding",
                 "sonnet-4.5", 3, 84_000),
                ("a8c41f6e-2b97-4d05-b3e8-6f1d9a2c0b54", REPOS["billing-api"][0], "billing-api", "main",
                 "opus-4.1", 20, 412_000),
                ("0e7b93d2-4a16-4c8f-9d21-8b5e0f3a6c79", ROOT + "/docs site/it's-old", "docs site", "",
                 "haiku-4.5", 76, 31_500))):
            end, win = a - ago_h * H, (1_000_000 if ctx > 200_000 else 200_000)
            rows.append({"sid": sid, "cwd": cwd, "name": name, "branch": br, "model": mdl, "endedAt": end,
                         "pct": round(ctx * 100 / win), "gone": i == 2,
                         "agentDesc": ("Fix cart rounding", "Invoice PDF review", "")[i],
                         **({"acct": "work", "acctDir": "/home/demo/.claude-work"} if i < 2 else {})})   # extra Claude root
        return {"ok": True, "days": days, "at": float(a), "n": 3, "total": 3, "cap": 50, "rows": rows, "ms": 2}

    def history_units(self, sid):
        s = next((x for x in self.sess if x["sid"] == sid), None)
        if not s:
            return {"ok": False, "sid": sid, "units": []}
        units = [{"kind": "main", "tid": "sess:%s|%s" % (s["cwd"], s["sid"]), "type": "main", "desc": "",
                  "start": s["born"], "end": self.a, "tok": s["ctx"] * 200, "tc": None, "depth": 0,
                  "hours": max(1, (self.a - s["born"]) // H), "st": "run"}]
        for x in self._sess_subs(s["k"]):
            units.append({"kind": "agent", "tid": x["tid"] + "|" + s["sid"], "aid": x["aid"], "type": x["type"],
                          "desc": x["desc"], "start": x["start"], "end": x["end"], "tok": x["tk"], "tc": x["tc"],
                          "depth": x["depth"], "hours": 1, "st": "run" if x["run"] else "done"})
        return {"ok": True, "sid": sid, "cwd": s["cwd"], "project": s["repo"], "units": units, "at": float(self.now())}

    def retro(self, days=7, acct=""):
        out = self._retro_all(days)
        if acct not in ("personal", "work"):
            return out
        # account pick: the six OTel cards split personal 40% / work 60% (integer shares sum to All)
        def sh(v):
            p = v * 2 // 5
            return p if acct == "personal" else v - p

        def rows(xs, keys):
            return [dict(x, **{k: sh(x[k]) for k in keys}) for x in xs]
        rk, c = out["rank"], out["cache"]
        out = dict(out, acct=acct, acctSince=out["daily"][min(2, days - 1)]["d"])
        out["rank"] = dict(rk, top=rows(rk["top"], ("calls", "tms")), rest=rows(rk["rest"], ("calls", "tms")),
                           calls=sh(rk["calls"]))
        out["time"] = dict(out["time"], rows=rows(out["time"]["rows"], ("calls", "tms")))
        cd = rows(c["days"], ("read", "create"))
        out["cache"] = {"days": [dict(x, pct=int(round(100.0 * x["create"] / (x["read"] + x["create"])))) for x in cd],
                        "sessions": rows(c["sessions"], ("read", "create"))}
        out["heat"] = dict(out["heat"], cells=[[[sh(v[0]), sh(v[1])] for v in r] for r in out["heat"]["cells"]])
        out["heat"]["n"] = sum(v[0] for r in out["heat"]["cells"] for v in r)
        ms = [dict(x, kinds={k: [sh(v[0]), sh(v[1])] for k, v in x["kinds"].items()}) for x in out["models"]["rows"]]
        ms = [dict(x, count=sum(v[0] for v in x["kinds"].values()), tokens=sum(v[1] for v in x["kinds"].values()))
              for x in ms]
        out["models"] = dict(out["models"], rows=ms, n=sum(x["count"] for x in ms))
        hk = rows(out["hooks"]["rows"], ("count", "ms", "fail"))
        out["hooks"] = dict(out["hooks"], rows=hk, n=sum(x["count"] for x in hk))
        return out

    def _retro_all(self, days):
        a = self.a
        h = self.wkuse()
        daily = []
        wk = {x["d"]: x for x in h["daily"]}    # wkuse holds 7 days; older days of a 30-day range are synthetic
        for i in range(days):
            dd = datetime.fromtimestamp(a - (days - 1 - i) * 24 * H).strftime("%Y-%m-%d")
            d = wk.get(dd) or {"d": dd, "tok": (60 + (i * 37) % 180) * 10 ** 6}
            d.setdefault("cost", round(d["tok"] * 5.6e-7, 2))
            f = 3 + (i * 7) % 11
            daily.append({"d": d["d"], "tok": d["tok"], "cost": d["cost"], "sessions": 3 + i % 4,
                          "commits": 2 + (i * 5) % 9, "fails": f, "kinds": {"tool": f - 1, "api": 1}})

        def wh(n, last, j):     # drill-down rows, same keys as sidereus/retro.py _rt_where_add
            ss = [self.sess[(j + k) % len(self.sess)] for k in range(min(3, n))]
            ns = [n // len(ss) + (1 if k < n % len(ss) else 0) for k in range(len(ss))]
            return [{"sid": s["sid"], "cwd": s["cwd"], "project": s["repo"], "n": c, "last": last - k * 1800}
                    for k, (s, c) in enumerate(zip(ss, ns))]
        # tms = calls x mean ms · fms = failed share of that time (0-100), as otel._otel_tool_rank adds them
        rk = [{"n": n, "calls": c, "ok": ok, "ms": ms, "tms": c * ms, "fms": fm} for n, c, ok, ms, fm in (
            ("Bash", 41 * days, 96.4, 2300, 7), ("Read", 38 * days, 99.2, 40, 1), ("Edit", 22 * days, 97.6, 60, 2),
            ("Grep", 15 * days, 100.0, 120, 0), ("Agent", 3 * days, 88.0, 95000, 21),
            ("Glob", 4 * days, 100.0, 30, 0), ("WebFetch", days, 85.7, 1800, 14))]
        tm = sorted(rk, key=lambda x: (-x["tms"], x["n"]))
        return {"ok": True, "days": days, "at": a, "daily": daily,
                "kinds": {"tool": sum(x["kinds"]["tool"] for x in daily), "api": len(daily)},
                "grades": {"mine": 9, "noise": 41, "check": 2, "cut": 3},
                "fails": sum(x["fails"] for x in daily),
                # same order as retro._rt_sigs_out (count desc, newest first on ties); the page renders it as-is
                "sigs": sorted([dict(x, chk=x.get("chk", 0), where=wh(x["n"], x["last"], j), wn=min(3, x["n"]))
                         for j, x in enumerate((
                             {"sig": "Exit code N", "kind": "tool", "grade": "noise", "n": 31, "last": a - 900},
                             {"sig": "String to replace not found", "kind": "tool", "grade": "noise", "n": 8, "last": a - 4000},
                             {"sig": "API overloaded", "kind": "api", "grade": "cut", "n": 3, "last": a - 20000},
                             {"sig": "Test failed: cart total", "kind": "tool", "grade": "mine", "n": 5, "last": a - 1900},
                             {"sig": "서브에이전트 failed", "kind": "agent", "grade": "check", "n": 2, "last": a - 3000,
                              "chk": 2}))], key=lambda s: (-s["n"], -s["last"])),
                "weeks": [{"week": daily[0]["d"], "from": daily[0]["d"], "to": daily[-1]["d"], "days": len(daily),
                           "tok": sum(x["tok"] for x in daily), "cost": round(sum(x["cost"] for x in daily), 2),
                           "sessions": 14, "commits": sum(x["commits"] for x in daily),
                           "fails": sum(x["fails"] for x in daily),
                           "top": [{"project": x["name"], "tok": x["tok"]} for x in h["rows"]]}],
                "projects": [{"project": x["name"], "tok": x["tok"], "cost": x["cost"], "sessions": 2,
                              "commits": 6 + len(x["name"]), "tpc": x["tok"] // (6 + len(x["name"]))} for x in h["rows"]],
                "tools": {"rows": [], "since": a - H}, "ms": 9,
                # same shape as otel._otel_tool_rank; from = range start (collection predates the range)
                "rank": {"top": rk[:5], "rest": rk[5:], "restN": 2,
                         "calls": 124 * days, "from": daily[0]["d"], "live": True},
                "time": {"rows": tm[:5], "restN": 2},      # same shape as otel's time payload (rows, not top/rest)
                # same shape as otel_cache; paths are the demo world's fake cwds
                "cache": {"days": [dict(d=x["d"], read=r, create=c, pct=int(round(100.0 * c / (r + c))))
                                   for i, x in enumerate(daily)
                                   for r, c in [((90 + (i * 23) % 70) * 10 ** 5, (6 + (i * 13) % 30) * 10 ** 5)]],
                          "sessions": [{"sid": s["sid"], "path": s["cwd"], "project": s["repo"],
                                        "read": r, "create": c, "pct": int(round(100.0 * c / (r + c)))}
                                       for s, (r, c) in zip(self.sess, ((12 * 10 ** 5, 9 * 10 ** 5), (30 * 10 ** 5, 8 * 10 ** 5),
                                                                        (55 * 10 ** 5, 6 * 10 ** 5)))]},
                "heat": self._retro_heat(days), "models": self._retro_models(days),
                "hooks": self._retro_hooks(days, daily[0]["d"])}

    def _retro_hooks(self, days, first):
        """Same shape as otel_hooks._oh_view — top hook event types by total time."""
        rows = []
        for ev, per_day, avg, fail in (("PreToolUse", 180, 42, 1), ("PostToolUse", 175, 31, 0), ("Stop", 22, 380, 1),
                                       ("UserPromptSubmit", 20, 95, 0), ("SessionStart", 3, 640, 0)):
            n = per_day * days
            rows.append({"ev": ev, "count": n, "ms": n * avg, "avg": avg, "fail": fail * (1 + days // 7)})
        rows.sort(key=lambda x: -x["ms"])
        return {"rows": rows, "n": sum(x["count"] for x in rows), "from": first}

    def _retro_models(self, days):
        """Same shape as otel._otel_src_models — two Claude families, a small one and the overflow «other» row."""
        def row(m, main, agent, side):
            ks = {"main": main, "agent": agent, "side": side}
            return {"model": m, "count": sum(v[0] for v in ks.values()), "tokens": sum(v[1] for v in ks.values()), "kinds": ks}
        rows = [row("claude-opus-5-5", [1840, 96 * 10 ** 6], [920, 41 * 10 ** 6], [60, 2 * 10 ** 6]),
                row("claude-sonnet-4-5-20250929", [310, 12 * 10 ** 6], [640, 22 * 10 ** 6], [40, 10 ** 6]),
                row("claude-haiku-4-5-20251001", [0, 0], [120, 3 * 10 ** 6], [880, 4 * 10 ** 6]),
                row("other", [0, 0], [0, 0], [14, 3 * 10 ** 5])]
        rng = min(days, 8)
        return {"from": int(self.a - (days - 1) * 24 * H), "since": int(self.a - (rng - 1) * 24 * H),
                "n": sum(x["count"] for x in rows), "rows": rows}

    def _retro_heat(self, days):
        """Same shape as otel._otel_src_heat — weekday daytime busy, evenings light, weekends sparse."""
        cells = []
        for d in range(7):
            row = []
            for h in range(24):
                n = (30 + (d * 7 + h * 11) % 25) if (d < 5 and 9 <= h <= 18) else \
                    (4 + (d + h) % 6) if (d < 5 and 19 <= h <= 22) else \
                    ((d + h) % 4 if (d >= 5 and 10 <= h <= 17) else 0)
                row.append([n, n * 41000])
            cells.append(row)
        rng = min(days, 8)      # bysrc keeps 8 days, so the demo grid covers at most that
        return {"from": int(self.a - (days - 1) * 24 * H), "since": int(self.a - (rng - 1) * 24 * H),
                "n": sum(c[0] for r in cells for c in r), "cells": cells}

    # ───────────────────────────── work logs
    def session_work(self, sid):
        s = next((x for x in self.sess if x["sid"] == sid or x["id"] == sid), None)
        if not s:
            return {"ok": False, "msg": "unknown session"}
        a = self.a
        return {"ok": True, "sid": s["sid"], "type": "%s · 세션 %s" % (s.get("proj") or s["repo"], s["id"]),   # tab label uses proj (worktree «.wt» differs)
                "desc": "%s · 세션 %s" % (s["cwd"], s["id"]), "depth": 1, "first": _iso(a - 40 * 60),
                "last": _iso(a - 10), "prompt": "(demo)", "says": [{"t": _iso(a - 30 * 60), "text": "Working on it."}],
                # One older edit with its body cut (editCut) so the «first N edit bodies cut» note shows in the demo.
                "cutSays": 0, "cutEdits": 1, "steps": [{"t": _iso(a - 29 * 60), "tool": "Read", "targ": "src/app.ts", "arg": ""},
                                        {"t": _iso(a - 20 * 60), "tool": "Edit", "targ": "src/app.ts", "arg": "",
                                         "editCut": True},
                                        {"t": _iso(a - 60), "tool": "Bash", "targ": "npm test", "arg": ""}],
                "cutSteps": 0, "tail": 600, "at": None,     # live tail (no retro `at` window in the demo)
                "tools": [["Read", 1], ["Edit", 1], ["Bash", 1]], "size": 120000}

    def session_context(self, cwd):
        """Demo `GET /api/session/context` — fictional paths, same keys as sidereus/ctxsrc.py."""
        cwd = cwd or ROOT + "/acme-web"
        ins = [("/home/demo/.claude/CLAUDE.md", "user", 6120), (cwd + "/AGENTS.md", "project", 9870),
               (cwd + "/.claude/rules/style.md", "rule", 1430)]
        instr = [{"path": p, "scope": sc, "bytes": n, "tokens": int(round(n / 3.5))} for p, sc, n in ins]
        mb = 2840
        mem = {"dir": "/home/demo/.claude/projects/" + "".join(c if c.isalnum() else "-" for c in cwd) + "/memory",
               "index": "", "bytes": mb, "tokens": int(round(mb / 3.5)), "files": 12}
        mem["index"] = mem["dir"] + "/MEMORY.md"
        mcp = [{"name": n, "scope": sc} for n, sc in (("github", "project"), ("playwright", "local"), ("context7", "user"))]
        hooks = [{"event": e, "n": n} for e, n in (("PostToolUse", 1), ("PreCompact", 1), ("Stop", 2))]
        nb = sum(x["bytes"] for x in instr) + mb
        return {"ok": True, "cwd": cwd, "root": cwd, "at": int(self.a), "bytes": nb, "tokens": int(round(nb / 3.5)),
                "instr": instr, "memory": mem, "mcp": mcp, "hooks": hooks,
                "skills": {"user": 5, "project": 1}, "agents": {"user": 3, "project": 4},
                "counts": {"instr": len(instr), "memory": 12, "mcp": len(mcp), "hooks": 4}}

    def agent_work(self, tid, sid=""):
        # ⚠ Look the agent up by its own tid (same shape as work.agent_work); falling back to a session
        #   made every agent popup show the first session's title.
        x = next((y for y in self.subs if y["tid"] == tid), None)
        if not x:
            return {"ok": False, "msg": "Could not find that subagent's record (it may not be written yet)."}
        tool, targ = (x["now"].split(" · ", 1) + [""])[:2] if x["now"] else ("Read", "README.md")
        # sub `now` is the tool name only (rule 1); the work popup may show a target, so it lives here
        targ = targ or _DEMO_TARG.get(tool, "")
        end = self.now() if x["run"] else x["end"]
        return {"ok": True, "type": x["type"], "desc": x["desc"], "depth": x["depth"],
                "first": _iso(x["start"]), "last": _iso(end), "prompt": "(demo)",
                "says": [{"t": _iso(x["start"] + 60), "text": "Starting: " + x["desc"] + "."}], "cutSays": 0, "cutEdits": 0,
                "steps": [{"t": _iso(x["start"] + 90), "tool": "Grep", "targ": "src/", "arg": ""},
                          {"t": _iso(end - 30), "tool": tool, "targ": targ, "arg": ""}],
                "cutSteps": 0, "tools": [["Grep", 2]] if tool == "Grep" else [["Grep", 1], [tool, 1]], "size": x["tk"] // 40}
