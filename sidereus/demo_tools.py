"""Demo «Tools» / «Harness» / «Preferences» payloads (split out of demo.py) — invented rows, ⚠never the real ~/.claude."""
import hashlib
import json
import os
import shlex

from sidereus.demo_data import H


# «Tools» tab: (kind, name, scope, proj, path, bytes, on, ro, uses, last_h, flags) — invented; never the real ~/.claude
DEMO_TOOLS = [
    ("skill", "release-notes", "user", "", "~/.claude/skills/release-notes/SKILL.md", 2100, True, False, 14, 5, []),
    ("skill", "release-note", "project", "~/src/acme-web", "~/src/acme-web/.claude/skills/release-note/SKILL.md",
     1800, True, False, 0, 0, ["unused", "near"]),
    ("agent", "code-reviewer", "user", "", "~/.claude/agents/code-reviewer.md", 3400, True, False, 22, 2, []),
    ("agent", "test-writer", "project", "~/src/billing-api", "~/src/billing-api/.claude/agents/test-writer.md",
     2600, False, False, 3, 70, []),
    ("cmd", "ship", "user", "", "~/.claude/commands/ship.md", 900, True, False, 9, 20, []),
    ("mcp", "docs-search", "user", "", "~/.claude.json", 160, True, False, 41, 1, []),
    ("mcp", "browser", "plugin", "", "~/.claude/plugins/cache/demo/browser/1.0/.mcp.json", 120, True, True, 0, 0,
     ["unused"]),
    ("hook", "Stop", "user", "", "~/.claude/settings.json", 140, True, False, 0, 0, []),
]


def _demo_prefs():
    """GET /api/prefs in the real shape (cc_settings.prefs_get_all) from defaults only — ⚠no config/settings file is read."""
    from sidereus.cc_settings import CC_KEYS
    from sidereus.features import _MANIFESTS
    from sidereus.prefs import PREFS, PREFS_OWN_PANE
    cc = "~/.claude/settings.json"
    keys = {k: {"value": d, "default": d, "src": "default", "restart": True}
            for k, (d, _c, _e) in PREFS.items() if k not in PREFS_OWN_PANE}
    keys.update({k: {"value": d, "default": d, "src": "claude", "path": cc, "restart": False, "apply": "new_session"}
                 for k, (_s, _c, d) in CC_KEYS.items()})
    feats = [{"id": f, "title": str(m.get("title") or f)[:64], "deps": m["deps"], "default_on_public": m["default_on_public"],
              "on": True, "set": True} for f, m in sorted(_MANIFESTS.items())]
    return {"ok": True, "path": "~/.mailbox-mcp/config.local.json", "keys": keys,
            "mailbox_watch": {"mode": "on", "projects": {}}, "cc_path": cc, "cc_primary_label": "primary",
            "otel": {"value": "http://127.0.0.1:8799", "ok": True}, "features": feats}


# GET /api/diag in the hook_diag.diag() shape: the bundled plugin enabled, nothing else found.
# ⚠The bare {"ok": True} fallback has no `plugins`/`sidereus`, so the «Get started» checklist read step 1 as unknown and hid.
DEMO_DIAG = {"ok": True, "overlaps": [], "sidereus": {}, "silent": [], "shadow": [],
             "plugins": [{"name": "sidereus", "market": "sidereus", "version": "0.9.5", "accts": ["primary"], "on": True,
                          "known": True, "checked": True}]}


def _demo_diag():
    return json.loads(json.dumps(DEMO_DIAG))


_DEMO_ID = "%s:%012x"   # (kind, 1-based DEMO_TOOLS index): one format for list ids and harness tids


def _demo_tid(kind, name):
    """The _demo_tools row id for (kind, name), so demo harness rows join the Tools list like the real toolinv ids; "" = not listed."""
    i = next((i for i, r in enumerate(DEMO_TOOLS) if r[0] == kind and r[1] == name), None)
    return "" if i is None else _DEMO_ID % (kind, i + 1)


def _demo_tools(a, path, tid):
    rows = [{"id": _DEMO_ID % (k, i + 1), "kind": k, "name": n, "scope": sc, "proj": pj, "path": p, "bytes": b,
             "tok": int(round(b / 3.5)), "on": on, "ro": ro, "uses": us, "last": int(a - lh * H) if us else 0,
             "sha": "%064x" % (i + 1), "flags": fl}
            for i, (k, n, sc, pj, p, b, on, ro, us, lh, fl) in enumerate(DEMO_TOOLS)]
    if path == "/api/tools":
        return 200, {"ok": True, "items": rows}
    r = next((x for x in rows if x["id"] == tid), None)
    if path != "/api/tools/file" or not r:
        return 404, {"ok": False, "msg": "No such item."}
    if r["kind"] == "mcp":
        text = json.dumps({"command": "npx", "args": ["-y", "demo-" + r["name"]], "env": {"API_KEY": "••••"}},
                          ensure_ascii=False, indent=2)
    elif r["kind"] == "hook":
        text = "event: Stop\nmatcher: \ncommand: ~/bin/notify-done"
    else:
        text = "---\nname: %s\ndescription: Demo %s\n---\n\nInvented example body.\n" % (r["name"], r["kind"])
    return 200, {"ok": True, "id": r["id"], "kind": r["kind"], "text": text, "sha": r["sha"], "mtime": a - 86400}


def _hk(scope, cmd, eff, n, matcher="", timeout=None, miss=0, ch="", src="settings.json", open_="", nomatch=0, cost=None, plug=""):
    rm = "" if plug else "r" + hashlib.sha256(("%s\0%s\0%s" % (scope, cmd, matcher)).encode("utf-8")).hexdigest()[:16]
    return {"open": open_, "scope": scope, "src": src, "matcher": matcher, "cmd": cmd, "timeout": timeout, "eff": eff,
            "desc": "", "n": n, "last": 0, "quiet": int(not n), "plug": plug, "miss": miss, "ch": ch or cmd[:8], "nomatch": nomatch,
            "cost": cost, "rm": rm}   # hook-run counts {runs, avg, blk, out, k} or None (= not measured yet)


def _demo_harness(a, path):
    """Pipeline tab «Harness»: invented rows that trip every harness_verdict code; file views are off in demo."""
    if path != "/api/harness":
        return 404, {"ok": False, "msg": "File not found."}
    from sidereus import harness_cost, harness_flow, harness_trail, harness_verdict, sec_runtime
    t = int(a - 3 * H)
    ev = [{"ev": "SessionStart", "hooks": [_hk("user", "load-context.py", "inject", 41, cost={"runs": 220, "avg": 1450, "blk": 0, "out": 220, "k": 2}),
                                           _hk("user", "warm-cache.sh", "log", None, miss=1)]},
          {"ev": "UserPromptSubmit", "hooks": [_hk("user", "prompt-tag.py", "inject", 88)]},
          {"ev": "PreToolUse", "hooks": [_hk("user", "guard.py", "block", 120, "Bash"), _hk("project", "lint-gate.sh", "block", None, "Edit|Write", nomatch=1),
                                         _hk("project", "guard.py", "block", None, "Bash", src=".claude/settings.json"),
                                         _hk("plugin", "browser-guard.mjs", "log", 7, "mcp__browser__.*", src="hooks.json", plug="browser")]},
          {"ev": "PostToolUse", "hooks": [_hk("user", "audit-log.py", "log", 300, cost={"runs": 60, "avg": 30, "blk": 0, "out": 0, "k": 1})]},
          {"ev": "Stop", "hooks": [_hk("user", "summarize.py", "inject", 12, timeout=90)]}]
    for e in ev:
        for h in e["hooks"]:
            h["last"] = t if h["n"] else 0
    body = {"ok": True, "plat": "cc", "plats": ["cc"], "proj": "", "days": 30, "events": ev, "scanning": False,
            "rules": [{"path": "~/.claude/CLAUDE.md", "size": 5200, "order": 1, "open": ""},
                      {"path": "~/src/acme-web/AGENTS.md", "size": 52000, "order": 2, "open": ""}],
            "agents": [{"name": "code-reviewer", "scope": "user", "open": "", "pipes": [{"pipe": "change", "stage": "리뷰"}], "n": 22},
                       {"name": "release-bot", "scope": "", "open": "", "pipes": [{"pipe": "release", "stage": "배포"}], "n": 0}],
            "mcps": [{"name": "docs-search", "scope": "user", "plug": "", "transport": "stdio", "on": True, "n": 41, "last": t,
                      "status": "ok", "err": "", "fail_at": 0},
                     {"name": "browser", "scope": "plugin", "plug": "browser", "transport": "http", "on": True, "n": 0, "last": 0,
                      "status": "fail", "err": "connection refused", "fail_at": t}],
            "skills": [{"name": "release-notes", "scope": "user", "plug": "", "on": True, "n": 14, "last": t, "open": "",
                        "pipes": [{"pipe": "release", "stage": "릴리스 노트"}]}],
            "counts": {"skill": 2, "cmd": 1, "mcp": 2},
            "evidence": sorted(_demo_evidence(a) + _demo_ci(a) + _demo_incident_rows(a), key=lambda r: -r["ts"])}
    for k, key in (("mcp", "mcps"), ("skill", "skills")):
        for r in body[key]:
            r["tid"] = _demo_tid(k, r["name"])
    rep = _demo_report(harness_trail.report(body["evidence"], "", git=False))
    p = _demo_person(a)
    body["report"] = dict(rep, counts=dict(rep["counts"], person=p["runs"]), person=p)
    body["guards"] = harness_flow.guards("", runs=_demo_flow_runs(a))
    body["runtime"] = sec_runtime.shape(_demo_runtime(a), a, root="/Users/demo/src/sidereus")   # fake checkout: the real install path stays off demo screens
    body["selfcheck"] = _demo_selfcheck(a)
    body["cost"] = harness_cost.cost("", runs=_demo_cost_runs(a), stops=[], policy=0, gates={"change-flow": ["검증"]},
                                     hook={"n": 1320, "rows": [{"ev": "PreToolUse", "ms": 41000}, {"ev": "SessionStart", "ms": 9600}]})
    return 200, harness_verdict.verdict(body, 30)


def _demo_incident_rows(a):
    """Older harness «Results» rows: fast FAIL→PASS then FAIL again (the 2.5h PASS refixes it → «refixed»; that later pair is dirty → «unchecked»),
    and a clean hook-test pair _demo_report marks «reverted».
    ⚠Listed in body["evidence"] too so checkpoint run counts match the «Results» rows; kept out of _demo_evidence (pipeline view)."""
    ok_gates = ("py_compile", 0, 142, 0, 3.1), ("node_check", 0, 96, 0, 2.4)
    row = lambda t, m, h, d, rc, st: {"kind": "check", "ts": a - t * H, "mode": m, "head": h, "dirty": d, "rc": rc, "steps": _ev_steps(*st)}
    return [row(6.2, "fast", "a0c4e19", True, 1, ok_gates + (("tests", 1, 1279, 1, 39.5),)),
            row(5.9, "fast", "a0c4e19", True, 0, ok_gates + (("tests", 0, 1279, 0, 40.1),)),
            row(5.0, "fast", "b71e04d", True, 1, ok_gates + (("tests", 1, 1281, 1, 40.6),)),
            row(8.4, "hook-test", "6e2d0b7", False, 1, (("test", 1, 0, 0, 17.9),)),
            row(8.1, "hook-test", "7f13c5a", False, 0, (("test", 0, 0, 0, 18.2),))]


def _demo_report(rep):
    """git=False never yields «reverted», so the clean hook-test PASS of _demo_incident_rows is marked by hand and the counts redone."""
    inc = [dict(x, state="reverted") if x["pass"]["head"] == "7f13c5a" and x["state"] == "held" else x for x in rep["incidents"]]
    tally = lambda s: sum(1 for x in inc if x["state"] == s)
    cnt = dict(rep["counts"], held=tally("held"), reverted=tally("reverted"), unchecked=tally("unchecked"),
               checked=sum(1 for x in inc if x["state"] != "unchecked"))
    return dict(rep, incidents=inc, counts=cnt)


def _demo_selfcheck(a):
    """Invented harness_selfcheck.load() result: the 11 replay cases, one FAIL (keep-reverted read «held»), same commit."""
    rows = (("gate-pass-only", "gate", "check.sh --fast PASS only", "no r2g", "no r2g", "gate-red-green", []),
            ("gate-red-green", "gate", "check.sh --fast FAIL then PASS on the same repo and head", "r2g", "r2g", "gate-pass-only", []),
            ("guard-commit", "guard", "git commit while the required Verify gate has no rc=0 evidence", "blocked", "blocked", "guard-commit-after-pass", ["gate"]),
            ("guard-commit-after-fail", "guard", "git commit after Verify ran but its --full gate recorded rc=1", "blocked", "blocked", "guard-commit-after-pass", ["gate"]),
            ("guard-commit-after-pass", "guard", "git commit after Verify passed and its --full gate recorded rc=0", "allowed", "allowed", "guard-commit-after-fail", []),
            ("guard-jump", "guard", "Verify dispatched while Build never ran", "blocked", "blocked", "guard-jump-declared", ["jump"]),
            ("guard-jump-declared", "guard", "Build declared skipped with [pl-skip:], then Verify dispatched", "allowed", "allowed", "guard-jump", []),
            ("guard-skip-declared", "guard", "[pl-skip:] of Build, which requireGates does not list", "allowed", "allowed", "guard-skip-required", []),
            ("guard-skip-required", "guard", "[pl-skip:] of the required Verify gate", "blocked", "blocked", "guard-skip-declared", ["skipgate"]),
            ("keep-held", "keep", "PASS recorded at commit A and HEAD is still A", "held", "held", "keep-reverted", []),
            ("keep-reverted", "keep", "PASS at commit A, then a later commit restores A's parent tree", "reverted", "held", "keep-held", []))
    cases = [{"name": n, "guard": g, "situation": s, "expect": e, "actual": x, "pass": e == x, "pair": p, "codes": c}
             for n, g, s, e, x, p, c in rows]
    return {"state": "ok", "ts": int(a - 2 * H), "head": "3f9c2ab71e04d5b8c6a90f1e2d3c4b5a69788776", "stale": False,
            "cmd": "python3 scripts/harness_selfcheck.py", "cases": cases}


def _demo_person(a):
    """Invented harness_person.person() result (built here: demo may not import a feature module): two sidereus-bugfix
    runs and one quick-fix run — newest with 2 commits and a test, quick-fix without a test, the oldest with one."""
    card = lambda n, t0, end, cm, ts: {"name": n, "t0": a - t0 * H, "end": a - end * H, "commits": cm, "tests": ts}
    return {"pipes": ["quick-fix", "sidereus-bugfix"], "runs": 3, "git": True,
            "cards": [card("sidereus-bugfix", 6, 5, ["9f3c2a1b7d4e", "5e8d0c4a2b19"], ["tests/test_timeline_gap.py"]),
                      card("quick-fix", 26, 25.5, ["c71b9e2f0a63"], []),
                      card("sidereus-bugfix", 50, 49, ["2a4f6e8b1c03"], ["tests/test_quota_reset.py"])]}


def _demo_runtime(a):
    """Invented deps-last.json, 9 days old (stale): brew node one patch behind (2 lines behind 26.x), system Python 3.9 EOL,
    brew node@24 on its latest patch, brew python@3.10 EOL."""
    node = {"rt": "nodejs", "path": "/opt/homebrew/opt/node@22/bin/node", "cls": "homebrew", "viewer": False,
            "cur": "22.23.3", "cycle": "22", "level": "warn",
            "patch": {"level": "warn", "target": "22.23.4", "security": False, "eol": "2027-04-30", "eol_past": False},
            "newest": {"level": "info", "target": "26.2.0", "behind_n": 2}}
    py = {"rt": "python", "path": "/usr/bin/python3", "cls": "system", "viewer": True, "cur": "3.9.6", "cycle": "3.9",
          "level": "fail", "patch": {"level": "fail", "target": "3.9.25", "security": False, "eol": "2025-10-31", "eol_past": True},
          "newest": {"level": "info", "target": "3.14.2", "behind_n": 5}}
    # patch-ok on an older cycle (no step) and an EOL Homebrew cycle (install step) show both next-step branches
    node24 = {"rt": "nodejs", "path": "/opt/homebrew/opt/node@24/bin/node", "cls": "homebrew", "viewer": False,
              "cur": "24.22.1", "cycle": "24", "level": "info",
              "patch": {"level": "ok", "target": "24.22.1", "security": False, "eol": "2028-04-30", "eol_past": False},
              "newest": {"level": "info", "target": "26.2.0", "behind_n": 1}}
    py310 = {"rt": "python", "path": "/opt/homebrew/opt/python@3.10/bin/python3.10", "cls": "homebrew", "viewer": False,
             "cur": "3.10.19", "cycle": "3.10", "level": "fail",
             "patch": {"level": "fail", "target": "3.10.19", "security": False, "eol": "2026-10-04", "eol_past": True},
             "newest": {"level": "info", "target": "3.14.2", "behind_n": 4}}
    return {"at": a - 9 * 86400, "report": "security-report-20261019-0930.md", "dev": True, "offline": False,
            "items": [py, py310, node, node24]}


def _demo_flow_runs(a):
    """Invented plmark run for the «What is guarding» strip: one skip, one loop-back, one denied stage jump, one denied gate skip
    and one denied loop-back after a passing review verdict."""
    st = lambda s, t0, t1, n=1: {"s": s, "t0": a - t0 * H, "t1": a - t1 * H, "n": n}
    # ⚠`verdict` stays last: _demo_cost_runs copies dl[0]/dl[1] only, so «Gate cost» is unchanged by it
    return [{"sid": "d3m0f10w0000", "name": "change-flow", "t0": a - 2.0 * H, "t1": a - 0.41 * H, "end": a - 0.41 * H,
             "h0": "b71e04d", "h1": "3f9c2ab", "deny": 3, "dl": [{"c": "jump", "t": a - 1.8 * H, "title": "검증"},
                                                                 {"c": "skipgate", "t": a - 0.6 * H, "title": "리뷰"},
                                                                 {"c": "verdict", "t": a - 0.45 * H, "title": "리뷰"}],
             "st": {"설계": st("skip", 2.0, 2.0, 0), "구현": st("done", 1.9, 1.0, 2), "검증": st("done", 1.3, 0.5, 2),
                    "리뷰": st("done", 0.5, 0.42)},
             "lb": [{"f": "검증", "g": "구현", "n": 1, "t": a - 1.2 * H}]}]


def _demo_cost_runs(a):
    """«Gate cost»: the flow run with resume times and a looped gate stage (complied + unknown), plus an older run
    whose gate block was followed by a skip (Overridden). Kept apart so the «What is guarding» counts stay as they are."""
    r = dict(_demo_flow_runs(a)[0])
    r["dl"] = [dict(r["dl"][0], r=a - 1.8 * H + 240), dict(r["dl"][1])]
    r["st"] = dict(r["st"])
    r["st"]["검증"] = dict(r["st"]["검증"], p0=a - 0.8 * H, k=2, ps=[{"a": a - 1.3 * H, "b": a - 1.0 * H, "s": "back"}])
    old = {"sid": "d3m0c0s70000", "name": "change-flow", "t0": a - 5.0 * H, "t1": a - 4.4 * H, "end": a - 4.4 * H, "deny": 1,
           "dl": [{"c": "gate", "t": a - 4.6 * H, "title": "리뷰", "r": a - 4.6 * H + 420}],
           "st": {"구현": {"s": "done", "t0": a - 5.0 * H, "t1": a - 4.7 * H, "n": 1},
                  "리뷰": {"s": "skip", "t0": a - 4.6 * H + 300, "t1": a - 4.6 * H + 300, "n": 0}}}
    return [r, old]


def _ev_steps(*rows):
    return [{"name": n, "rc": rc, "n": k, "failed": f, "secs": sec} for n, rc, k, f, sec in rows]


# QA widths (design at 1920; 1440/1100/900 must wrap or collapse) — the demo screen evidence covers all four.
DEMO_QA_WIDTHS = (900, 1100, 1440, 1920)


def _demo_evidence(a):
    """Invented «Results» rows (same shape as harness_evidence.recent): PASS --full, FAIL at tests, PASS --fast, hook PASS."""
    ok_gates = ("py_compile", 0, 142, 0, 3.1), ("node_check", 0, 96, 0, 2.4)
    return [{"kind": "check", "ts": a - 0.4 * H, "mode": "full", "head": "3f9c2ab", "dirty": False, "rc": 0,
             "steps": _ev_steps(*(ok_gates + (("tests", 0, 1284, 0, 41.7), ("leak", 0, 1, 0, 0.8), ("screen", 0, 8, 0, 22.5)))),
             "screen": [{"w": w, "lang": l, "ok": True, "diff": 0.0} for w in DEMO_QA_WIDTHS for l in ("ko", "en")]},
            {"kind": "check", "ts": a - 1.2 * H, "mode": "full", "head": "3f9c2ab", "dirty": True, "rc": 1,
             "steps": _ev_steps(*(ok_gates + (("tests", 1, 1284, 2, 39.9),)))},
            {"kind": "check", "ts": a - 2.5 * H, "mode": "fast", "head": "b71e04d", "dirty": True, "rc": 0,
             "steps": _ev_steps(*(ok_gates + (("tests", 0, 1281, 0, 40.2),)))},
            # Row written by the Bash evidence hook (hooks/ev_hook.py): rc and duration only, n/failed stay 0.
            {"kind": "check", "ts": a - 3.1 * H, "mode": "hook-test", "head": "b71e04d", "dirty": True, "rc": 0,
             "steps": _ev_steps(("test", 0, 0, 0, 18.6))}]


def _demo_ci(a):
    """Invented ev_hook CI rows (`gh run watch --exit-status`): one red, then 3 greens on later heads — 1 CI incident, streak 3.
    ⚠Kept out of _demo_evidence: the pipeline view reads check rows only, like harness_evidence.recent."""
    ci = lambda t, h, rc: {"kind": "ci", "ts": a - t * H, "mode": "ci", "head": h, "dirty": False, "rc": rc, "steps": []}
    return [ci(0.3, "3f9c2ab", 0), ci(2.2, "c58a3e1", 0), ci(4.2, "b71e04d", 0), ci(4.8, "9d1e7a0", 1)]


def _demo_pl_evidence(a):
    """GET /api/harness/evidence body: the «Results» rows plus «Implement» extras — a screen FAIL in pass 1 (a-85m..a-53m, shown via the pass picker)
    and a PASS in the latest pass (a-52m..a-31m) with the commit stamped there (demo.World.pl_runs `cm`).
    ⚠The extra rows stay out of _demo_evidence so the harness view keeps its own story."""
    ok_gates = ("py_compile", 0, 142, 0, 3.1), ("node_check", 0, 96, 0, 2.4)
    shots = [{"w": w, "lang": l, "ok": not (w == 1100 or (w == 1440 and l == "en")), "diff": 0.0} for w in DEMO_QA_WIDTHS for l in ("ko", "en")]
    fail = {"kind": "check", "ts": a - 60 * 60, "mode": "full", "head": "b71e04d", "dirty": True, "rc": 1,
            "steps": _ev_steps(*(ok_gates + (("screen", 1, 8, 3, 23.0),))), "screen": shots}
    ok = {"kind": "check", "ts": a - 40 * 60, "mode": "fast", "head": "b71e04d", "dirty": True, "rc": 0,
          "steps": _ev_steps(*(ok_gates + (("tests", 0, 1284, 0, 40.8),)))}
    rows = sorted(_demo_evidence(a) + [fail, ok], key=lambda r: -r["ts"])
    return {"ok": True, "evidence": rows, "commits": [{"h": "3f9c2ab", "ct": int(a - 33 * 60 + 20)}, {"h": "b71e04d", "ct": int(a - 3.3 * H)}]}


# «Pipelines» definition for the demo plrun (demo.World.pl_runs): same titles, so the timeline strip opens a populated view.
# `red` 0 = no stage red-checked yet: the «Get started» checklist shows 3/4 instead of hiding on an unknown step.
DEMO_PIPE = {"name": "change-flow", "ok": True, "errs": [], "sha": "0d1e2m3o4p5i6p7e", "title": "Change — acme-web",
             "use": "", "rules": "", "defaults": {"model": "inherit", "retry": 0}, "after": 1, "red": 0, "stages": [
                 {"title": "설계", "agent": "planner", "model": "opus", "produces": "slices", "ui": {"x": 44, "y": 24}},
                 {"title": "구현", "agent": "implementer", "fanout": "slices", "gate": "npm test", "ui": {"x": 292, "y": 24}},
                 {"title": "검증", "agent": "verifier", "model": "sonnet", "gate": "npm run check",
                  "onFail": {"goto": "구현", "max": 2}, "ui": {"x": 540, "y": 24}},
                 {"title": "리뷰", "agent": "code-reviewer", "onFail": {"goto": "구현", "max": 1}, "ui": {"x": 788, "y": 24}}]}
# Definition of the ended demo `release-check` run: «Since your last visit» grades «pass» only when `cur` is the last defined stage.
DEMO_PIPE_REL = dict(DEMO_PIPE, name="release-check", sha="0r1e2l3c4h5e6c7k", title="Release check — acme-web")


def _demo_catalog(demo_proj):
    """stage_catalog.catalog() shape from sidereus/stage_catalog.json, read directly (stage_catalog is a pipeline-feature module);
    ⚠fake `{sidereus}` path and `avail` pinned True (no `which` on the host). tests/test_demo.py asserts it equals catalog()."""
    try:
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sidereus", "stage_catalog.json"), "rb") as f:
            d = json.loads(f.read())
    except (OSError, ValueError):
        return {"groups": [], "items": []}
    side = shlex.quote(os.path.join(os.path.dirname(demo_proj), "sidereus"))
    items = []
    for t in d.get("templates") or []:
        it = {k: t[k] for k in ("id", "group", "title", "role", "agent", "model", "gateHint", "asserts", "loop") if k in t}
        it["gate"] = t["gate"].replace("{sidereus}", side)
        if t.get("task"):
            it["instr"] = t["task"].replace("{sidereus}", side)
        it["tools"] = [dict(x, avail=True) for x in t["tools"]]
        items.append(it)
    return {"groups": d.get("groups") or [], "items": items}


def _demo_pipelines(proj, demo_proj, empty_proj=None):
    """GET /api/pipelines in the pipeline.pipelines shape: the demo project plus `empty_proj` (no pipelines, so the empty-project
    start row is reachable in the demo); the only disk read is the bundled stage catalog."""
    if not proj:
        projects = [{"path": demo_proj, "n": 2}] + ([{"path": empty_proj, "n": 0}] if empty_proj else [])
        return 200, {"ok": True, "projects": projects, "added": []}
    if proj != demo_proj and not (empty_proj and proj == empty_proj):
        return 400, {"ok": False, "msg": "unknown project"}   # ⚠not 404: the page reads 404 as «feature off»
    agents = [{"name": n, "scope": "project", "desc": d} for n, d in (
        ("code-reviewer", "Reviews a diff for bugs, regressions and rule violations."),
        ("implementer", "Implements one file slice and passes the fast gate."),
        ("planner", "Turns a request into acceptance criteria and file slices."),
        ("verifier", "Runs the full gate and reports pass or fail; fixes nothing."))]
    pls = [json.loads(json.dumps(p)) for p in (DEMO_PIPE, DEMO_PIPE_REL)] if proj == demo_proj else []
    return 200, {"ok": True, "proj": proj, "pipelines": pls, "agents": agents, "catalog": _demo_catalog(demo_proj),
                 "models": ["inherit", "opus", "sonnet", "haiku"], "roles": {}, "default_tasks": {}, "skills": [],
                 "rule_files": [], "workflows": [], "suggest": [], "std": [],
                 "apply": {"mode": "auto", "global": "auto", "own": None}}


# GET /api/pipelines/eval for the demo: a fixed pl_eval_view.body() result (core may not import the pipeline
# feature; tests/test_pl_eval_view.py asserts it still equals body() of the inputs). Invented counts.
# ⚠No stage red "pass": DEMO_PIPE `red` counts the same verdicts (pipeline._red_counts) and must stay 0 for «Get started».
DEMO_EVAL = {"ok": True, "graded": {"n": 0, "m": 4, "unred": 2, "unstable": ["검증"]},
             "stages": [{"title": "설계", "catch": None, "red": "none", "unstable": False, "ci": None, "agree": None},
                        {"title": "구현", "catch": {"caught": 7, "n": 8}, "red": "fail", "unstable": False,
                         "ci": {"lo": 53, "hi": 98}, "agree": {"k": 3, "n": 3}},
                        {"title": "검증", "catch": {"caught": 5, "n": 6}, "red": "none", "unstable": True,
                         "ci": {"lo": 44, "hi": 97}, "agree": {"k": 2, "n": 3}},
                        {"title": "리뷰", "catch": None, "red": "skip", "unstable": False, "ci": None, "agree": None}],
             "holdout": {"n": 12, "caught": 10, "ci": {"lo": 55, "hi": 95}}, "commit": "3f9c2ab0d1e2",
             "sugg": [{"code": "tighten-gate", "stage": "구현", "mode": "fast", "flags": "--fast", "tpl": ""},   # = suggest() (b) for the red "fail"
                      {"code": "unstable", "stage": "검증", "mode": "fast"},
                      {"code": "redcheck", "stage": "검증", "cmd": ""}],   # cmd filled per request from the demo project path
             "security": {"n": 5, "m": 7, "checks": [
                 {"id": "security-policy", "v": "fail"}, {"id": "license", "v": "pass"}, {"id": "pinned-deps", "v": "pass"},
                 {"id": "dep-update-tool", "v": "fail"}, {"id": "secret-gate", "v": "pass"}, {"id": "sast-gate", "v": "pass"},
                 {"id": "dep-audit-gate", "v": "na"}, {"id": "binary-artifacts", "v": "pass"}]},
             # = pl_outcome.counts() shape (no per-PASS list); path is a fake data dir, never the real install
             "outcome": {"proc": {"runs": 14, "jump": 3}, "lb": {"cur": {"n": 14, "k": 4}, "prev": {"n": 11, "k": 5}},
                         "result": {"n": 12, "broke": 2, "fixed": 3, "unchecked": 1, "partial": False},
                         "verdict": "pl_broke",   # = pl_outcome.verdict() of this body (broke 2)
                         "eff": {"설계": {"n": 14, "sec": 95, "tok": 41000, "tn": 14}, "구현": {"n": 14, "sec": 610, "tok": 236000, "tn": 12},
                                 "검증": {"n": 13, "sec": 240, "tok": None, "tn": 0}, "리뷰": {"n": 11, "sec": 180, "tok": 58000, "tn": 11}},
                         "cost": {"share": {"설계": 12, "구현": 71, "리뷰": 17}, "med": 330000, "mn": 12,
                                  "last": {"tok": 318000, "sec": 1425}}},
             "rep": {"date": "2026-10-14", "path": "~/.mailbox-mcp/eval/3f9c2ab0d1e2a4b5/reports/2026-10-14.md"}}


def _demo_eval(proj, demo_proj, name):
    if proj != demo_proj:
        return 400, {"ok": False, "msg": "unknown project"}
    b = dict(json.loads(json.dumps(DEMO_EVAL)), name=str(name or "")[:60])
    # = pl_eval_view.redcheck_cmd(demo_proj, name, stage, code_dir=<demo root>/sidereus) on POSIX (test_pl_eval_view.test_demo);
    #   ⚠core may run without the pipeline feature, and the fake code dir keeps the real install path off demo screens
    for s in b["sugg"]:
        if s["code"] == "redcheck":
            nm = b["name"] or "change-flow"
            s["cmd"] = " ".join(shlex.quote(a) for a in (
                "python3", os.path.join(os.path.dirname(demo_proj), "sidereus", "scripts", "pl_eval.py"), "redcheck",
                "--pipeline", os.path.join(demo_proj, ".claude", "pipelines", nm + ".json"), "--stage", s["stage"], "--repo", demo_proj))
    return 200, b


# Demo GET /api/mcp-conn servers (mcp_conn.conn shape): (name, scope, plug, transport, state, err, calls, last call min ago)
DEMO_MCP_CC = [
    ("docs-search", "user", "", "stdio", "ok", "", 41, 4), ("issue-tracker", "project", "", "http", "ok", "", 6, 95),
    ("metrics", "user", "", "stdio", "fail", "CONNECT_TIMEOUT", 0, 0), ("browser", "plugin", "browser", "stdio", "unknown", "", 0, 0),
    ("claude_ai_Calendar", "cloud", "", "", "ok", "", 3, 30), ("claude_ai_Drive", "cloud", "", "", "auth", "", 0, 0),
]
DEMO_MCP_PI = [("docs-search", "user", "stdio"), ("repo-notes", "project", "stdio")]
# Demo `kinds` (mcp_conn._cc_kinds shape): (name, kind, scope, plug, calls, last call min ago) — invented names only
DEMO_KIND_SK = [
    ("release-notes", "skill", "user", "", 6, 12), ("lint-fix", "skill", "user", "", 2, 90), ("changelog", "skill", "user", "", 0, 0),
    ("pr-summary", "skill", "user", "", 0, 0), ("api-docs", "skill", "project", "", 3, 40), ("db-migrate", "skill", "project", "", 0, 0),
    ("ui-review", "skill", "project", "", 1, 200), ("browser:screenshot", "skill", "plugin", "browser", 1, 25),
    ("browser:record", "skill", "plugin", "browser", 0, 0), ("browser:trace", "skill", "plugin", "browser", 0, 0),
    ("diagram", "skill", "user", "", 0, 0), ("frontend-design", "skill", "seen", "", 2, 300),
    ("ship", "cmd", "user", "", 4, 8), ("deploy-check", "cmd", "project", "", 0, 0),
]
DEMO_KIND_AG = [("code-reviewer", "project", 5, 20), ("test-writer", "project", 2, 60), ("doc-writer", "project", 0, 0),
                ("perf-probe", "project", 0, 0), ("general-purpose", "seen", 3, 15)]
# (event, scope, matchers, [(hookName, runs)], last run min ago)
DEMO_KIND_HK = [("PreToolUse", "user", ["Bash", "Edit|Write"], [("PreToolUse:Bash", 31), ("PreToolUse:Edit", 12)], 2),
                ("PostToolUse", "project", ["Write"], [("PostToolUse:Write", 9)], 3), ("Stop", "user", [""], [("Stop", 14)], 1),
                ("SessionStart", "plugin", [""], [("SessionStart:startup", 1), ("SessionStart:resume", 1)], 240),
                ("UserPromptSubmit", "user", [""], [], 0)]


def _demo_kinds(now, k):
    """Demo `kinds` for a Claude Code session; the k == 2 session gets 60 skills (layout check with many nodes)."""
    proj, home = "~/src/acme-web/.claude", "~/.claude"
    plug = home + "/plugins/cache/demo/%s/1.0"

    def base(sc, pl):
        return proj if sc == "project" else plug % pl if sc == "plugin" else home

    def last(n, ago):
        return int(now - ago * 60) if n else 0
    sk = [{"name": nm, "kind": kd, "scope": sc, "plug": pl, "n": n * (k + 1) // 2, "last": last(n * (k + 1) // 2, ago),
           "path": "" if sc == "seen" else base(sc, pl) + ("/commands/%s.md" % nm if kd == "cmd" else
                                                            "/skills/%s/SKILL.md" % nm.split(":")[-1])}
          for nm, kd, sc, pl, n, ago in DEMO_KIND_SK]
    if k == 2:
        sk += [{"name": "toolkit:task-%02d" % i, "kind": "skill", "scope": "plugin", "plug": "toolkit", "n": int(i % 7 == 0),
                "last": last(i % 7 == 0, i), "path": plug % "toolkit" + "/skills/task-%02d/SKILL.md" % i} for i in range(1, 49)]
    ag = [{"name": nm, "scope": sc, "plug": "", "path": "" if sc == "seen" else proj + "/agents/%s.md" % nm, "n": n,
           "last": last(n, ago)} for nm, sc, n, ago in DEMO_KIND_AG]
    hk = []
    for ev, sc, ms, subs, ago in DEMO_KIND_HK:
        p = base(sc, "guard") + ("/hooks/hooks.json" if sc == "plugin" else "/settings.json")
        n = sum(r for _h, r in subs)
        hk.append({"name": ev, "scope": sc, "plug": "guard" if sc == "plugin" else "", "path": p, "n": n, "last": last(n, ago),
                   "files": [{"scope": sc, "path": p, "matcher": m} for m in ms],
                   "subs": [{"name": h, "n": r, "last": last(r, ago)} for h, r in subs]})
    order = ("project", "user", "plugin", "cloud", "seen")   # = mcp_conn.MC_SCOPES display order
    return dict((kd, {"supported": True, "more": 0, "items": sorted(rows, key=lambda r: (order.index(r["scope"]), r["plug"], r["name"].lower()))})
                for kd, rows in (("skill", sk), ("agent", ag), ("hook", hk)))


def _demo_mcp_conn(now, sid, rows):
    """Demo GET /api/mcp-conn body for a session on the demo screen — invented server names only."""
    row = next((r for r in rows if sid and r.get("sid") == sid), None)
    if row is None:
        return 200, {"ok": False, "msg": "Only sessions shown on screen can be opened.", "vars": {}}
    plat, servers = row.get("plat") or "", []
    kinds = dict((kd, {"supported": False, "items": [], "more": 0}) for kd in ("skill", "agent", "hook"))   # = mcp_conn._kinds_none
    if plat == "cc":
        k = sum(map(ord, sid)) % 3          # vary the counts per session so the strip shows different orbits
        kinds = _demo_kinds(now, k)
        for nm, sc, pl, tr, st, err, n, ago in DEMO_MCP_CC:
            n = n * (k + 1) // 2 if n else 0
            servers.append({"name": nm, "scope": sc, "plug": pl, "transport": tr, "on": True, "state": st, "err": err,
                            "at": int(now - (ago or 60) * 60) if st != "unknown" else 0, "n": n,
                            "last": int(now - ago * 60) if n else 0})
    elif plat == "pi":
        servers = [{"name": nm, "scope": sc, "plug": "", "transport": tr, "on": True, "state": "unknown", "err": "",
                    "at": 0, "n": None, "last": None} for nm, sc, tr in DEMO_MCP_PI]
    return 200, {"ok": True, "now": int(now), "sid": sid, "plat": plat, "supported": plat in ("cc", "cx", "pi"),
                 "counts": plat in ("cc", "cx"), "since": 0, "scanning": False, "checked": int(now), "servers": servers,
                 "totals": dict((s, sum(1 for x in servers if x["state"] == s)) for s in ("ok", "fail", "auth", "unknown")),
                 "kinds": kinds}
