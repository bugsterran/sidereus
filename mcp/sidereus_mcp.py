#!/usr/bin/env python3
"""Sidereus MCP server (stdio) — lets a Claude session ASK Sidereus about quota, peers and file owners.

★2026-09-24 (user-approved): Sidereus answers when asked; it never controls sessions. Every tool is a GET on the
  local viewer (`/api/agent/*`, built in sidereus/agent_brief.py) — no writes, no session control.
⛔Metadata only: outputs carry ids, names, states, tool names, counts and times — never conversation text.
Protocol: JSON-RPC 2.0, one JSON message per line on stdin/stdout (MCP stdio transport). Stdlib only (3.9).
Caller identity = this process's cwd (Claude Code starts MCP servers in the session cwd), overridable per call.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

NAME, VERSION = "sidereus", "0.1.0"


def _cfg_root():
    """Folder holding mailbox_config.py: the parent (clone, plugin), else site-packages for sidereus/_bundle/mcp (pipx/uv)."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return root if os.path.isfile(os.path.join(root, "mailbox_config.py")) else os.path.dirname(os.path.dirname(root))


def _port():
    """Viewer port via mailbox_config.port() (env SIDEREUS_PORT > config `port` > 8799); 8799 if it cannot load."""
    try:
        root = _cfg_root()
        if root not in sys.path:
            sys.path.insert(0, root)
        import mailbox_config
        return mailbox_config.port()
    except Exception:
        return 8799


BASE = "http://127.0.0.1:%d" % _port()
DETECT_SELF = False   # set True under __main__: resolve the caller's sid from its parent claude process
TIMEOUT_S = 8.0  # ⚠The first request right after a viewer restart took >3s (cold caches) and failed — warm calls are ~3ms.
PROTOCOLS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")   # newest first; echo the client's if listed
DOWN = "Sidereus is not reachable at %s (%s). Start it: python3 -m sidereus start"
PLATFORM = sys.platform   # tests replace this


def _plist_path(label):
    """Same path sidereus_cli.mac_plist_path uses (mirrored: importing sidereus_cli reloads the config)."""
    return os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents", label + ".plist")


def down_text(err):
    """Viewer-down hint. ⚠launchctl only on macOS with the plist installed — elsewhere it does not exist."""
    text = DOWN % (BASE, err)
    if PLATFORM == "darwin":
        label = launchd_label()
        if os.path.exists(_plist_path(label)):
            text += " (launchd service installed: launchctl kickstart -k gui/%d/%s)" % (
                getattr(os, "getuid", lambda: -1)(), label)
    return text


def launchd_label():
    """Viewer job label: env SIDEREUS_LAUNCHD_LABEL, else mailbox_config (config.local.json), else the public default.
    ⚠Resolved at call time, not import: the label is install-specific and lives in the local config."""
    env = os.environ.get("SIDEREUS_LAUNCHD_LABEL")
    if env:
        return env
    try:
        root = _cfg_root()
        if root not in sys.path:
            sys.path.insert(0, root)
        import mailbox_config
        return mailbox_config.launchd_label("viewer")
    except Exception:
        return "io.sidereus.viewer"

TOOLS = [
    {"name": "sidereus_quota",
     "description": "Quota: 5h/7d used %, tokens used this 5h window (no remaining budget), reset time, "
                    "time to empty at this pace, pace vs goal, one advice line "
                    "(same verdict as the saver hook).",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "sidereus_file_peers",
     "description": "Call before editing a shared file: sessions/agents that edited it in the last 30 min "
                    "(sid8, agent type, project, ago, live) and whether it is uncommitted. Your own session is "
                    "marked (you) when known.",
     "inputSchema": {"type": "object", "properties": {
         "path": {"type": "string", "description": "File path (absolute, or relative to cwd)"},
         "sid": {"type": "string", "description": "Your session id (default: detected from the parent Claude process)"},
         "cwd": {"type": "string", "description": "Base dir for a relative path (default: this session's cwd)"}},
         "required": ["path"], "additionalProperties": False}},
    {"name": "sidereus_peers",
     "description": "Live sessions and subagents in the same repo (any worktree): state (think/tool/ask/idle), "
                    "current tool name, ctx %.",
     "inputSchema": {"type": "object", "properties": {
         "cwd": {"type": "string", "description": "Repo dir to look at (default: this session's cwd)"}},
         "additionalProperties": False}},
    {"name": "sidereus_attention",
     "description": "Sessions currently needing the user — labels only.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
]


class SidereusDown(Exception):
    pass


def _get(path, params=None):
    """GET {BASE}{path}?params -> dict. Raises SidereusDown on any transport/JSON failure (never crashes the server)."""
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_S) as r:  # nosec B310 -- constant loopback http base
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:     # ⚠subclass of URLError — up but an older build without /api/agent/*
        raise SidereusDown("Sidereus answered HTTP %d for %s — restart it to load the /api/agent routes" % (e.code, path))
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise SidereusDown(down_text(type(e).__name__))


def _ago(s):
    if not isinstance(s, (int, float)):
        return "?"
    s = int(s)
    return "%ds" % s if s < 60 else "%dm" % (s // 60) if s < 3600 else "%dh%02dm" % (s // 3600, s % 3600 // 60)


def _tok(n):
    if not isinstance(n, (int, float)):
        return "?"
    return "%.1fM" % (n / 1e6) if n >= 1e6 else "%dk" % (n // 1000)


def _pct(d):
    v = d.get("pct")         # ⚠a null pct (first run) must not print «None%»
    return "?" if v is None else v


def _quota_params():
    """{"dir": CLAUDE_CONFIG_DIR} when the session runs on a non-default account, else None (primary request)."""
    cfg = os.environ.get("CLAUDE_CONFIG_DIR") or ""
    if not cfg or os.path.realpath(os.path.expanduser(cfg)) == os.path.realpath(os.path.expanduser("~/.claude")):
        return None
    return {"dir": cfg}


def fmt_quota(d):
    if d.get("ok") is False and d.get("err"):    # ⚠never show primary numbers for another account; ok:false without err = unmeasured primary
        return "quota unavailable: %s" % (d.get("err") or "unknown error")
    f, s, p, sv = d.get("fiveHour") or {}, d.get("sevenDay") or {}, d.get("pace") or {}, d.get("saver") or {}
    # ⚠No token headroom (traps/quota.md «Token headroom»): used tokens are a measured local sum, not a remaining budget.
    ea = d.get("emptyAt")
    out = ["5h: %s%% used · %s tokens used on this PC · resets in %s%s" % (
               _pct(f), _tok(d.get("used5Tok")), _ago(f.get("leftSec")),
               (" · empties in %s at this pace" % _ago(ea - time.time())) if isinstance(ea, (int, float)) else ""),
           "7d: %s%% used · resets in %s" % (_pct(s), _ago(s.get("leftSec")))]
    if d.get("acct"):
        out.insert(0, "account: %s" % d["acct"])
    if p.get("lv") is not None:
        em = p.get("earlyMin")
        out.append("pace: %s (lv %+d%s) · goal %s%% · recommended concurrency %s" % (
            p.get("name") or "", p["lv"], (", empties %d min early" % em) if isinstance(em, int) and em > 0 else "",
            p.get("goal", "?"), p.get("rec", "?")))
    else:
        out.append("pace: no verdict (mode %s)" % (p.get("mode") or "unknown"))
    out.append("saver: %s" % (("on · stage %s · max %s subagents" % (sv.get("stage"), sv.get("cap")))
                               if sv.get("on") else "off (%s)" % (sv.get("why") or "auto")))
    out.append("advice: %s" % (d.get("advice") or "ok"))
    if d.get("age") is not None and d["age"] > 600:
        out.append("note: quota data is %s old" % _ago(d["age"]))
    return "\n".join(out)


def fmt_peers(d):
    ps = d.get("peers") or []
    if d.get("note") and not d.get("repo"):
        return d["note"]
    out = ["repo %s · %d live session(s)" % (d.get("repo") or "?", d.get("n", len(ps)))]
    for p in ps[:12]:
        subs = p.get("subagents") or []
        out.append("- %s %s@%s%s · %s%s · ctx %s · %s ago%s" % (
            p.get("sid8"), p.get("project"), p.get("branch") or "-",
            "" if p.get("sameWorktree") else " [wt %s]" % (p.get("worktree") or "?"),
            p.get("state") or "?", (" " + p["tool"]) if p.get("tool") else "",
            ("%s%%" % p["ctxPct"]) if p.get("ctxPct") is not None else "?", _ago(p.get("ageSec")),
            (" · subagents: " + ", ".join("%s%s" % (x.get("type"), "(idle)" if x.get("idle") else "")
                                          for x in subs[:4]) + (" +%d" % (len(subs) - 4) if len(subs) > 4 else ""))
            if subs else ""))
    if len(ps) > 12:
        out.append("... %d more" % (len(ps) - 12))
    return "\n".join(out)


def _self_sid():
    """Caller's session id from Claude Code's per-process file ~/.claude/sessions/<ppid>.json (the MCP server is
    spawned by the session's claude process). "" when unknown — never guessed."""
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    try:
        with open(os.path.join(base, "sessions", "%d.json" % os.getppid()), encoding="utf-8") as f:
            return str(json.load(f).get("sessionId") or "")
    except (OSError, ValueError, AttributeError):
        return ""


def fmt_file(d, me=""):
    """`me` = caller's sid (any length); its sid8 prefix is excluded from the conflict count."""
    # Same short form as the server's ident._sid8 (standalone script: mirrored, not imported).
    me8 = str(me or "")
    for p in ("session-", "rollout-"):
        if me8.startswith(p):
            me8 = re.sub(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}(?:-\d{2})?-", "", me8[len(p):])
            break
    me8 = me8[:8]
    unc = d.get("uncommitted")
    eds = d.get("editors") or []
    out = ["%s · %s · edited by %d unit(s) in last %s min (%d live)" % (
        d.get("path"), "uncommitted" if unc else "no such file" if d.get("exists") is False
        else "clean" if unc is False else "not in git",
        d.get("n", 0), d.get("windowMin", 30), d.get("liveN", 0))]
    for e in eds[:10]:
        out.append("- %s/%s %s · %s · %s ago%s%s" % (e.get("sid8"), e.get("unit"), e.get("agent"), e.get("project"),
                                                    _ago(e.get("agoSec")), " · live" if e.get("live") else "",
                                                    " (you)" if me8 and e.get("sid8") == me8 else ""))
    # ⚠Warn on distinct live SESSIONS, not liveN (units: a session + its own subagent is 2) — same rule as the rail
    #   (2+ sessions). Known caller: any other live session is enough (the caller's edit makes it 2).
    sids = d.get("liveSids")
    if sids is None:        # older viewer build without liveSids
        sids = sorted({e.get("sid8") for e in eds if e.get("live")})
    others = [s for s in sids if not (me8 and s == me8)]
    if unc and len(others) >= (1 if me8 else 2):
        out.append("warning: %s (%s) on an uncommitted file — coordinate before editing" % (
            "another live session" if me8 else "2+ live sessions", ", ".join(others)))
    return "\n".join(out)


def fmt_attention(d):
    rs = d.get("rows") or []
    if not rs:
        return "no session needs the user right now"
    out = ["%d session(s) need the user:" % len(rs)]
    for r in rs[:12]:
        out.append("- %s %s@%s · %s (score %s)" % (r.get("sid8"), r.get("project"), r.get("branch") or "-",
                                                    r.get("why"), r.get("score")))
    return "\n".join(out)


_JSON_TYPES = {"string": str, "object": dict, "array": list, "boolean": bool}


def check_args(name, args):
    """Error text when `args` breaks the tool's inputSchema (type, unknown key, required), else "".
    ⚠Unchecked, `path: 123` became the path "<cwd>/123" and unknown keys were silently dropped."""
    tool = next((t for t in TOOLS if t["name"] == name), None)
    if tool is None:
        return ""                           # call_tool answers "unknown tool" as a tool error
    if not isinstance(args, dict):
        return "arguments must be an object"
    sch = tool["inputSchema"]
    props = sch.get("properties") or {}
    for k, v in args.items():
        if k not in props:
            if sch.get("additionalProperties") is False:
                return "unknown argument: %s" % k
            continue
        want = _JSON_TYPES.get(props[k].get("type"))
        if want and not isinstance(v, want):
            return "argument %s must be a %s" % (k, props[k]["type"])
    miss = [k for k in sch.get("required") or () if k not in args]
    return "missing argument: %s" % ", ".join(miss) if miss else ""


def call_tool(name, args, cwd=None):
    """-> (text, is_error)."""
    cwd = (args or {}).get("cwd") or cwd or os.getcwd()
    try:
        if name == "sidereus_quota":
            q = _quota_params()
            d, fmt = (_get("/api/agent/quota", q) if q else _get("/api/agent/quota")), fmt_quota
        elif name == "sidereus_peers":
            d, fmt = _get("/api/agent/peers", {"cwd": cwd}), fmt_peers
        elif name == "sidereus_file_peers":
            path = (args or {}).get("path") or ""
            if not path:
                return "path is required", True
            me = (args or {}).get("sid") or (_self_sid() if DETECT_SELF else "")
            d, fmt = _get("/api/agent/file", {"path": path, "cwd": cwd}), (lambda x: fmt_file(x, me))
        elif name == "sidereus_attention":
            d, fmt = _get("/api/agent/attention"), fmt_attention
        else:
            return "unknown tool: %s" % name, True
    except SidereusDown as e:
        return str(e), True
    if not isinstance(d, dict) or d.get("ok") is False and d.get("err"):
        if name == "sidereus_quota" and isinstance(d, dict):
            return fmt_quota(d), True
        return "Sidereus error: %s" % ((d or {}).get("err") if isinstance(d, dict) else "bad reply"), True
    return fmt(d), False


def handle(msg, cwd=None):
    """One JSON-RPC message -> response dict, or None for notifications."""
    if not isinstance(msg, dict):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid request"}}
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if "id" not in msg:          # notification (notifications/initialized, cancelled, ...): no reply
        return None
    def ok(res):
        return {"jsonrpc": "2.0", "id": mid, "result": res}

    def bad(text):
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": text}}
    if not isinstance(params, dict):
        return bad("params must be an object")
    if method == "initialize":
        want = params.get("protocolVersion")
        return ok({"protocolVersion": want if want in PROTOCOLS else PROTOCOLS[0],
                   "capabilities": {"tools": {"listChanged": False}},
                   "serverInfo": {"name": NAME, "version": VERSION},
                   "instructions": "Read-only view of Sidereus (local session control viewer). Ask sidereus_file_peers "
                                   "before editing a shared file; sidereus_quota before spawning many subagents."})
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": TOOLS})
    if method == "tools/call":
        args = params.get("arguments")
        args = {} if args is None else args
        why = check_args(params.get("name"), args)
        if why:
            return bad(why)
        text, err = call_tool(params.get("name"), args, cwd)
        return ok({"content": [{"type": "text", "text": text}], "isError": err})
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "method not found: %s" % method}}


def utf8_stdio(streams=None):
    """Re-encode stdio as UTF-8. ⚠Windows pipes default to the ANSI code page (cp949 cannot encode the em dash in
    tools/list) and the server died on the first reply."""
    for s in streams or (sys.stdin, sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


def serve(inp=None, out=None):
    inp, out = inp or sys.stdin, out or sys.stdout
    cwd = os.getcwd()
    for line in inp:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            try:
                resp = handle(msg, cwd)
            except Exception as e:     # a bad message must never kill the server
                resp = {"jsonrpc": "2.0", "id": msg.get("id") if isinstance(msg, dict) else None,
                        "error": {"code": -32603, "message": "%s: %s" % (type(e).__name__, e)}}
        if resp is not None:
            out.write(json.dumps(resp, ensure_ascii=False) + "\n")
            out.flush()


if __name__ == "__main__":
    DETECT_SELF = True      # only the real server reads ~/.claude/sessions; imported (tests) it stays off
    utf8_stdio()
    serve()
