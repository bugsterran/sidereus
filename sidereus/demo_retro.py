"""Demo «Retro» tab payload for `chat_server.py --demo` (split out of sidereus/demo_data.py to keep it under the size cap).

Owns `_WorldRetro` — `retro` and its section builders (daily, signatures, tool rank, cache, heat, models, hooks) that `World` inherits.
⚠Imported only by sidereus/demo.py (lazy, under --demo). Never import sidereus.demo from here (cycle).
⚠Keep it 100% synthetic — tests/test_demo.py scans every response against a denylist.
"""
from datetime import datetime

from sidereus.demo_data import H


class _WorldRetro:
    """Retro payload builders mixed into demo.World (needs self.a/sess and wkuse())."""

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
