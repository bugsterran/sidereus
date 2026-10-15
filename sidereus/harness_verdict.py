"""Harness check (GET /api/harness `verdict`): flags rows of a harness body that need a look.

`verdict(body, days)` is pure — it reads only the rows already built by harness / harness_plat and attaches
`vd: {lvl, why, vp, id}` to flagged rows, plus `body["verdict"] = {bad, check, ok}`.
  bad   = hook_missing (script path gone) · mcp_fail · ref_missing (pipeline stage names an agent/skill that is not there)
  check = idle (tool-event matcher that matched no tool used in the window, harness `nomatch`) · dup (same command twice on one event+matcher)
          · slow_block (long timeout on an event the session waits for) · rule_big (rule file over VD_RULE_BYTES)
⚠Metadata only: `vp` (verdict params) carries names, matcher, numbers, scope labels — never script text, env or paths.
"""
VD_BLOCK_EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "Stop", "SubagentStop", "PreCompact")
VD_BLOCK_TIMEOUT = 30        # seconds
VD_RULE_BYTES = 40000        # ★Claude Code warns on instruction files over 40k chars
VD_BUILTIN_AGENTS = ("general-purpose", "Explore", "Plan")


def _hook_vd(ev, h, seen, days, partial, lane=""):
    m = h.get("matcher") or ""
    if h.get("miss"):
        return "bad", "hook_missing", {"ev": ev, "cmd": h.get("cmd") or ""}
    k = (m, h.get("ch") or "")   # ⚠never fall back to cmd: it is a type name or basename, not the command
    if k[1] and k in seen:
        return "check", "dup", {"ev": ev, "srcs": seen[k]}
    to = h.get("timeout")
    if (lane or ev) in VD_BLOCK_EVENTS and isinstance(to, (int, float)) and to > VD_BLOCK_TIMEOUT:
        return "check", "slow_block", {"ev": ev, "timeout": to}
    # ⚠A silent hook leaves no run record, so run counts never prove idle — only a matcher no used tool name fits.
    if h.get("nomatch") and not partial:
        return "check", "idle", {"days": days, "matcher": m}
    return None


def _ref_vd(r):
    if r.get("scope") or r.get("open") or r.get("name") in VD_BUILTIN_AGENTS or not r.get("pipes"):
        return None
    p = r["pipes"][0]
    return "bad", "ref_missing", {"pipe": p.get("pipe", ""), "stage": p.get("stage", "")}


def verdict(body, days):
    """Attach `vd` to flagged rows of a 200 harness body and set body["verdict"]; returns body."""
    flagged = []
    total = 0
    for e in body.get("events") or []:
        ev = e.get("ev") or ""
        hooks = e.get("hooks") or []
        seen = {}
        for h in hooks:
            total += 1
            # cx/gm events carry their Claude Code lane (Gemini BeforeTool = PreToolUse).
            flagged.append((h, _hook_vd(ev, h, seen, days, bool(body.get("scanning")), e.get("lane") or "")))
            k = (h.get("matcher") or "", h.get("ch") or "")
            seen.setdefault(k, []).append(h.get("src") or h.get("scope") or "")
    for r in body.get("rules") or []:
        total += 1
        big = isinstance(r.get("size"), int) and r["size"] > VD_RULE_BYTES
        flagged.append((r, ("check", "rule_big", {"bytes": r["size"]}) if big else None))
    for key in ("agents", "skills"):
        for r in body.get(key) or []:
            total += 1
            flagged.append((r, _ref_vd(r)))
    for r in body.get("mcps") or []:
        total += 1
        fail = r.get("status") == "fail"
        flagged.append((r, ("bad", "mcp_fail", {"name": r.get("name", "")}) if fail else None))
    out = {"bad": 0, "check": 0, "ok": 0}
    i = 0
    for row, v in flagged:
        row.pop("vd", None)
        if v is None:
            continue
        row["vd"] = {"lvl": v[0], "why": v[1], "vp": v[2], "id": "v%d" % i}
        out[v[0]] += 1
        i += 1
    out["ok"] = total - out["bad"] - out["check"]
    body["verdict"] = out
    return body
