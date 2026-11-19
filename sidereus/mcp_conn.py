"""Token tab «Connections»: the MCP servers one session can load, with that session's own evidence (GET /api/mcp-conn).

⚠Metadata only: server names, scope, transport, status words, error codes and counts leave this module.
  Config values (command/args/env/url/headers), Claude Code failure text and Codex `arguments`/`result`/`error`
  are never read into a result.
⚠Files only: never runs `claude mcp`, `pi mcp list` or an MCP server, never connects to one (AGENTS.md rule 7).
Claude Code: config from `toolinv._raw_items` + per-session evidence from `toolidx.session_mcp`.
Codex: config.toml `[mcp_servers.*]` names + the session's rollout `item_completed` McpToolCall items (server/status only).
pi: mcp.json names only — pi records no per-server call or status, so state stays unknown and counts null.
"""
import glob
import json
import os
import re
import threading
import time

from sidereus import plat_codex, plat_pi, toolidx, toolinv
from sidereus.gitinfo import _git_root
from sidereus.sessions import sessions_rows
from sidereus.toolidx_fmt import _SRV_RE
from sidereus.transcript import iso_epoch

MC_DAYS = 30                 # Claude Code evidence window (same default as the Tools tab)
MC_TTL_S = 10                # per-session result cache; the page polls
MC_CACHE_N = 64              # cached session results / Codex rollout files kept
MC_NAME_MAX = 120
MC_JSON_MAX = 1 << 20        # mcp.json / trust.json bytes read at most (larger -> treated as unreadable)
MC_PLATS = ("cc", "cx", "pi")
MC_SCOPES = ("project", "user", "plugin", "cloud", "seen")
MC_STATES = ("ok", "fail", "auth", "unknown")
_NAME_OK = re.compile(r"[^\x00-\x1f\x7f]{1,%d}" % MC_NAME_MAX)
# "body": sid -> (computed at, body) · "cx": rollout path -> {"sz", "off", "ev": {call id: (server, ok, ts)}}
_MC_CACHE = {"body": {}, "cx": {}}
_MC_LOCK = threading.Lock()
_now = time.time


def _cap_put(d, k, v):
    if k not in d and len(d) >= MC_CACHE_N:
        d.pop(next(iter(d)))
    d[k] = v


def _read_json(p):
    try:
        if os.path.getsize(p) > MC_JSON_MAX:
            return {}
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _transport(e):
    t = e.get("type") if isinstance(e, dict) else None
    if t in ("stdio", "http", "sse"):
        return t
    if not isinstance(e, dict):
        return ""
    return "stdio" if isinstance(e.get("command"), str) else "http" if isinstance(e.get("url"), str) else ""


def _plug_name(root):
    """Plugin name from its install dir (cache/<market>/<plugin>/<version>/ -> <plugin>); same rule as harness."""
    pn = os.path.basename(root.rstrip(os.sep)) if root else ""
    if re.match(r"^\d", pn):
        pn = os.path.basename(os.path.dirname(root.rstrip(os.sep)))
    return pn[:MC_NAME_MAX]


def _keys(nm, plug):
    """toolidx keys of one configured server; ⚠same forms as harness._mcp_rows (tests compare the two)."""
    ks = ["mcp:" + nm] + (["mcp:plugin_%s_%s" % (plug, nm)] if plug else []) + ["mcp:" + _SRV_RE.sub("_", nm)]
    return list(dict.fromkeys(ks))


def _row(nm, scope, plug, tr, on, state="unknown", err="", at=0, n=None, last=None):
    return {"name": nm, "scope": scope, "plug": plug, "transport": tr, "on": bool(on), "state": state,
            "err": err, "at": int(at), "n": n, "last": last}


def _cc_state(keys, st, auth):
    """(state, err, at) from the key whose evidence is newest; no evidence = unknown, never ok."""
    best = None
    for k in keys:
        h = st.get(k)
        if not h:
            continue
        s = h.get("status")
        at = h.get("fail_at") if s == "fail" else auth.get(k, 0) if s == "auth" else h.get("ok_at")
        if s in ("ok", "fail", "auth") and (best is None or int(at or 0) > best[2]):
            best = (s, h.get("err") or "" if s == "fail" else "", int(at or 0))
    return best or ("unknown", "", 0)


def _cc(sid, cwd, now):
    ev = toolidx.session_mcp(sid, now - MC_DAYS * 86400, now)
    uses, st, auth = ev.get("uses") or {}, ev.get("st") or {}, ev.get("auth") or {}
    cw = os.path.realpath(cwd) if cwd else ""
    rank = {"project": 0, "user": 1, "plugin": 2}
    items = [it for it in toolinv._raw_items() if it["kind"] == "mcp" and (
        it["scope"] == "user" or (it["scope"] == "plugin" and it["on"])
        or (it["scope"] == "project" and cw and it["proj"] and os.path.realpath(it["proj"]) == cw))]
    rows, used, names = [], set(), set()
    for it in sorted(items, key=lambda x: rank.get(x["scope"], 3)):   # ⚠project config wins over a user server of that name
        nm = str(it["name"])[:MC_NAME_MAX]
        plug = _plug_name(os.path.dirname(it["file"])) if it["scope"] == "plugin" else ""
        if not plug and nm in names:
            continue
        names.add(nm)
        keys = _keys(nm, plug)
        used.update(keys)
        n = sum(int((uses.get(k) or {}).get("n") or 0) for k in keys)
        last = max(int((uses.get(k) or {}).get("last") or 0) for k in keys)
        rows.append(_row(nm, it["scope"], plug, _transport(it.get("entry")), it["on"], *_cc_state(keys, st, auth), n=n, last=last))
    for k in sorted((set(uses) | set(st)) - used):   # evidence of a server not configured for this cwd
        nm = k[4:]
        u = uses.get(k) or {}
        rows.append(_row(nm, "cloud" if nm.startswith("claude_ai_") else "seen", "", "", True, *_cc_state([k], st, auth),
                         n=int(u.get("n") or 0), last=int(u.get("last") or 0)))
    return rows, bool(ev.get("scanning")), True


def _cx_files(sid):
    r = plat_codex.root()
    pats = (os.path.join(r, "sessions", "*", "*", "*", "rollout-*-%s.jsonl" % sid),
            os.path.join(r, "archived_sessions", "rollout-*-%s.jsonl" % sid),
            os.path.join(r, "archived_sessions", "*", "*", "*", "rollout-*-%s.jsonl" % sid))
    return sorted(set(p for pat in pats for p in glob.glob(pat)))


def _cx_scan(p, size):
    """New McpToolCall completions of one rollout since the last read (call under _MC_LOCK).
    ⚠Only payload.item.id (dedup key) / server / status and the line timestamp are read; arguments/result/error are not."""
    c = _MC_CACHE["cx"].get(p)
    if c is None or size < c["off"]:
        c = {"sz": -1, "off": 0, "ev": {}}
    if size != c["sz"]:
        with open(p, "rb") as f:
            f.seek(c["off"])
            raw = f.read(max(0, size - c["off"]))
        end = raw.rfind(b"\n") + 1
        for ln in raw[:end].split(b"\n"):
            if b'"McpToolCall"' not in ln or b'"item_completed"' not in ln:
                continue
            try:
                d = json.loads(ln)
            except ValueError:
                continue
            pl = d.get("payload") if isinstance(d, dict) else None
            it = pl.get("item") if isinstance(pl, dict) else None
            if not (isinstance(it, dict) and pl.get("type") == "item_completed" and it.get("type") == "McpToolCall"):
                continue
            srv, status, cid = it.get("server"), it.get("status"), it.get("id")
            if isinstance(srv, str) and _NAME_OK.fullmatch(srv.strip() or "\0") and status in ("completed", "failed"):
                key = cid if isinstance(cid, str) and cid else "%s#%d" % (p, c["off"] + raw.find(ln))
                c["ev"][key[:200]] = (srv.strip(), status == "completed", iso_epoch(d.get("timestamp"), 0.0))
        c["off"] += end
        c["sz"] = size if end == len(raw) else -1
    _cap_put(_MC_CACHE["cx"], p, c)
    return c["ev"]


def _cx(sid, cwd):
    if not plat_codex._SID_CH.match(sid):
        return [], False, False
    ev, whole, files = {}, True, _cx_files(sid)
    for p in files:
        try:
            size = os.path.getsize(p)
            if size > plat_codex.SCAN_MAX:
                whole = False          # ⚠skipped file: counts unknown, never a short count
                continue
            with _MC_LOCK:
                ev.update(_cx_scan(p, size))     # same call id in a live + archived copy counts once
        except OSError:
            whole = False
    counts = whole and bool(files)     # no rollout found = counts unknown, not zero
    agg = {}
    for srv, ok, ts in ev.values():
        a = agg.setdefault(srv, [0, 0.0, True])
        a[0] += 1
        if ts >= a[1]:
            a[1], a[2] = ts, ok
    r = plat_codex.root()
    rows, seen = [], set()
    cfgs = [("project", os.path.join(cwd, ".codex", "config.toml"))] if cwd else []
    for scope, cfg in cfgs + [("user", os.path.join(r, "config.toml"))]:
        for nm, tr, on in plat_codex.toml_mcp(cfg):
            if nm in seen:
                continue
            seen.add(nm)
            rows.append(_cx_row(nm, scope, tr, on, agg.get(nm), counts))
    for nm in sorted(set(agg) - seen):
        rows.append(_cx_row(nm[:MC_NAME_MAX], "seen", "", True, agg[nm], counts))
    return rows, False, counts


def _cx_row(nm, scope, tr, on, a, counts):
    if not a:   # configured, never called: Codex logs no startup connect, so unchecked
        return _row(nm, scope, "", tr, on, n=0 if counts else None, last=None)
    return _row(nm, scope, "", tr, on, "ok" if a[2] else "fail", "", a[1], a[0] if counts else None, int(a[1]))


def _pi_trusted(r, cwd):
    tr = _read_json(os.path.join(r, "trust.json"))
    want = set(os.path.realpath(x) for x in (cwd, _git_root(cwd)) if x)
    return any(v is True and isinstance(k, str) and os.path.isabs(k) and os.path.realpath(k) in want for k, v in tr.items())


def _pi(cwd):
    r = plat_pi.root()
    srcs = [("user", os.path.join(r, "mcp.json"))]
    if cwd and _pi_trusted(r, cwd):     # pi loads a project mcp.json only after the folder is trusted
        srcs.insert(0, ("project", os.path.join(cwd, ".pi", "mcp.json")))
    rows, seen = [], set()
    for scope, p in srcs:
        ms = _read_json(p).get("mcpServers")
        for nm in sorted(ms if isinstance(ms, dict) else {}):
            if not (isinstance(nm, str) and _NAME_OK.fullmatch(nm)) or nm in seen:
                continue
            seen.add(nm)
            e = ms[nm] if isinstance(ms[nm], dict) else {}
            rows.append(_row(nm, scope, "", _transport(e), not (e.get("disabled") is True or e.get("enabled") is False)))
    return rows, False, False


def conn(sid):
    """Body of GET /api/mcp-conn?sid= — only a session on screen; other CLIs answer supported:false."""
    sid = sid if isinstance(sid, str) and 0 < len(sid) <= 80 else ""
    row = next((r for r in sessions_rows() if sid and r.get("sid") == sid), None)
    if row is None:
        return {"ok": False, "msg": "Only sessions shown on screen can be opened.", "vars": {}}
    now = _now()
    hit = _MC_CACHE["body"].get(sid)
    if hit and 0 <= now - hit[0] < MC_TTL_S:
        return dict(hit[1], now=int(now))
    plat, cwd = str(row.get("plat") or ""), str(row.get("cwd") or "")
    servers, scanning, counts = [], False, False
    if plat == "cc":
        servers, scanning, counts = _cc(sid, cwd, now)
    elif plat == "cx":
        servers, scanning, counts = _cx(sid, cwd)
    elif plat == "pi":
        servers, scanning, counts = _pi(cwd)
    servers.sort(key=lambda s: (MC_SCOPES.index(s["scope"]), s["plug"], s["name"].lower()))
    body = {"ok": True, "now": int(now), "sid": sid, "plat": plat, "supported": plat in MC_PLATS, "counts": counts,
            "scanning": scanning, "checked": int(now), "servers": servers,
            "totals": dict((k, sum(1 for s in servers if s["state"] == k)) for k in MC_STATES)}
    if not scanning:
        _cap_put(_MC_CACHE["body"], sid, (now, body))
    return body
