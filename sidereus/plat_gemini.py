"""Gemini CLI platform: everything Gemini-specific in one place (prices, chat-file reader, labels).

The generic code (sidereus/ext.py, timeline.py, history.py) reads this module through `ext.PLAT_MODS`.
Records: `~/.gemini/tmp/<name>/chats/session-*.jsonl` (header line, message lines, `$set` rewrites),
project path from `tmp/<name>/.project_root` or `projects.json` (projectHash = sha256(path)).
⚠Metadata only: header ids/times, project root path, and per-message id/timestamp/model/tokens (`_tok_msg`).
⚠Gemini tokens/cost never enter Claude's 5h/7d/cost totals — they stay in the ext store.
"""
import json
import os
import threading

from sidereus.ident import _proj_name, _real_home
from sidereus.transcript import iso_epoch

PLAT = "gemini"          # hook `platform` value
KEY = "gm"               # row `plat` key (same as the logo `AILG.gm`)
NAME = "Gemini"
CHILD_LABEL = "gemini -p"    # a run launched from a Claude session's Bash (ext-hooks/ask-gemini)

# Gemini API Standard paid-tier prices, USD per 1M tokens (text input). Bundled: Sidereus must work offline.
# Source: https://ai.google.dev/gemini-api/docs/pricing (read 2026-09-24).
# (uncached input, cached input, output incl. thinking[, same three for prompts > 200k tokens])
# ⚠This is an estimate — free-tier usage is billed 0. It never enters Claude's quota/usage/cost.
# ⚠Read the Paid Tier column: «Not available» on that page is the Free Tier column (3.5-flash-lite caching is $0.03 paid).
LONG = 200_000
PRICE_VER = "2026-09-24b"
PRICE = {
    "gemini-3.8-flash": (0.75, 0.075, 3.75),
    "gemini-3.7-flash": (0.75, 0.075, 3.75),
    "gemini-3.6-flash": (0.75, 0.075, 3.75),
    "gemini-3.5-flash": (1.50, 0.15, 9.00),
    "gemini-3.5-flash-lite": (0.30, 0.03, 2.50),
    "gemini-3.1-flash-lite": (0.25, 0.025, 1.50),
    "gemini-3.1-pro-preview": (2.00, 0.20, 12.00, 4.00, 0.40, 18.00),
    "gemini-3.1-pro-preview-customtools": (2.00, 0.20, 12.00, 4.00, 0.40, 18.00),
    "gemini-3-flash-preview": (0.50, 0.05, 3.00),
    "gemini-2.5-pro": (1.25, 0.125, 10.00, 2.50, 0.25, 15.00),
    "gemini-2.5-computer-use-preview-10-2025": (1.25, 1.25, 10.00, 2.50, 2.50, 15.00),
    "gemini-2.5-flash": (0.30, 0.03, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.01, 0.40),
}
# ★The same page announces 2x prices for 3.6/3.7/3.8 Flash from 2027-01-01 — applied by request time.
PRICE_NEXT = (1798729200.0, {    # 2027-01-01 00:00 KST
    "gemini-3.8-flash": (1.50, 0.15, 7.50),
    "gemini-3.7-flash": (1.50, 0.15, 7.50),
    "gemini-3.6-flash": (1.50, 0.15, 7.50),
})


def cost(model, uncached, cached, out, thought, ts=0.0):
    """USD for one request, or None for a model not in the table. Tier by this request's prompt size."""
    p = None
    if ts >= PRICE_NEXT[0]:
        p = PRICE_NEXT[1].get(model)
    p = p or PRICE.get(model)
    if not p:
        return None
    if len(p) > 3 and uncached + cached > LONG:
        p = p[3:]
    return (uncached * p[0] + cached * p[1] + (out + thought) * p[2]) / 1e6


def root():
    # Gemini CLI's own override: GEMINI_CLI_HOME replaces the home dir and `.gemini` sits under it (like CODEX_HOME).
    return os.path.join(os.environ.get("GEMINI_CLI_HOME") or _real_home(), ".gemini")


def _with_cost(v):
    """Per-message cost stored beside its tokens, so a price-table change can recompute it (`pv`)."""
    i, o, c, t, ts, model = v[:6]
    return (i, o, c, t, ts, model, cost(model, i, c, o, t, ts))


def _tok_msg(m, msgs):
    """One message dict → msgs[id]. Later lines win (`$set` rewrites the same ids)."""
    if not isinstance(m, dict) or m.get("type") != "gemini":
        return
    tk = m.get("tokens")
    mid = m.get("id")
    if not isinstance(tk, dict) or not mid:
        return
    n = lambda k: max(0, int(tk.get(k) or 0)) if isinstance(tk.get(k), (int, float)) else 0
    cache = n("cached")
    # ★`input` (promptTokenCount) already includes cached tokens — split them so the parts add up.
    v = (max(0, n("input") - cache) + n("tool"), n("output"), cache, n("thoughts"),
         iso_epoch(m.get("timestamp")), str(m.get("model") or "")[:40])
    msgs[str(mid)] = _with_cost(v)


def _act_msg(m, acts):
    """user/gemini message id → timestamp (the timeline's activity points; `info` lines are not activity)."""
    if isinstance(m, dict) and m.get("type") in ("user", "gemini") and m.get("id"):
        t = iso_epoch(m.get("timestamp"))
        if t:
            acts[str(m["id"])[:64]] = t


# ── live session tail (hook `transcript_path`) ──
TAIL_READ = 8 << 20          # max bytes read per refresh (the rest on the next poll)
_tail_lock = threading.Lock()
_tail = {}                   # path → {"size", "off", "pv", "msgs"}


def path_ok(path):
    """Only a Gemini chat file under the real ~/.gemini — the path arrives in a hook POST."""
    if not path or not path.endswith(".jsonl"):
        return False
    return os.path.realpath(path).startswith(os.path.realpath(root()) + os.sep)


def session_msgs(path):
    """Per-request tuples of one live chat file, tailed from the last offset (restart when it shrank), or None."""
    if not path_ok(path):
        return None
    try:
        size = os.path.getsize(path)
    except OSError:
        return None
    with _tail_lock:
        e = _tail.get(path)
        if not e or size < e["off"]:
            e = {"size": 0, "off": 0, "pv": PRICE_VER, "msgs": {}}
            _tail[path] = e
        if e.get("pv") != PRICE_VER:
            e["msgs"] = {k: _with_cost(v) for k, v in e["msgs"].items()}
            e["pv"] = PRICE_VER
        if size == e["size"]:
            return dict(e["msgs"])
        off, msgs = e["off"], dict(e["msgs"])
    try:
        with open(path, "rb") as f:
            f.seek(off)
            buf = f.read(min(size - off, TAIL_READ))
    except OSError:
        return None
    end = buf.rfind(b"\n")
    if end < 0:
        return msgs                              # no complete line yet
    for ln in buf[:end].split(b"\n"):
        try:
            o = json.loads(ln)
        except ValueError:
            continue
        if not isinstance(o, dict):
            continue
        st = o.get("$set")
        if isinstance(st, dict) and isinstance(st.get("messages"), list):
            for m in st["messages"]:
                _tok_msg(m, msgs)
        else:
            _tok_msg(o, msgs)
    with _tail_lock:
        if _tail.get(path) is e:
            e.update(off=off + end + 1, size=off + end + 1, msgs=msgs)
    return dict(msgs)


# ── chat files on disk (timeline, history, today's usage) ──
SCAN_MAX = 64 << 20          # skip chat files larger than this
_lock = threading.Lock()
_cache = {}                  # path -> ((size, mtime, price ver), parsed)


def read(path):
    head, msgs, acts = {}, {}, {}
    try:
        with open(path, "rb") as f:
            for ln in f:
                try:
                    o = json.loads(ln)
                except ValueError:
                    continue
                if not isinstance(o, dict):
                    continue
                if not head and o.get("sessionId"):
                    head = {k: str(o.get(k) or "") for k in ("sessionId", "projectHash", "startTime", "kind")}
                    continue
                st = o.get("$set")
                if isinstance(st, dict) and isinstance(st.get("messages"), list):
                    for m in st["messages"]:
                        _tok_msg(m, msgs)
                        _act_msg(m, acts)
                else:
                    _tok_msg(o, msgs)
                    _act_msg(o, acts)
    except OSError:
        return None
    return {"head": head, "msgs": msgs, "acts": acts}


def _roots(r):
    """projectHash -> project path. ★Gemini's projectHash is sha256(path); paths come from projects.json keys."""
    import hashlib
    paths = []
    try:
        with open(os.path.join(r, "projects.json"), encoding="utf-8") as f:
            pj = json.load(f)
        pj = pj.get("projects") if isinstance(pj, dict) else None
        paths = [k for k in pj if isinstance(k, str)] if isinstance(pj, dict) else []
    except (OSError, ValueError):
        pass                    # optional projects.json missing or mid-write: no hash -> path names
    return {hashlib.sha256(p.encode("utf-8")).hexdigest(): p for p in paths}


def _dir_root(d):
    """`tmp/<name>/.project_root` holds the project path (one line)."""
    try:
        with open(os.path.join(d, ".project_root"), encoding="utf-8") as f:
            return f.read(4096).strip()
    except (OSError, UnicodeDecodeError):
        return ""


def _files(r0):
    """Main chats `chats/session-*.jsonl` + subagent chats `chats/<parent sessionId>/<subagent id>.jsonl`.
    ★2026-10-01: subagents were invisible — their tokens are not in the parent file (0 shared message ids)."""
    import glob
    base = os.path.join(r0, "tmp", "*", "chats")
    return glob.glob(os.path.join(base, "session-*.jsonl")) + glob.glob(os.path.join(base, "*", "*.jsonl"))


def _parent(p):
    """Parent sessionId for a subagent chat (its folder name = the parent header's `sessionId`), else ""."""
    d = os.path.basename(os.path.dirname(p))
    return "" if d == "chats" else d


def chats(since=0.0):
    """Gemini chat files modified since `since` → [{sid, path, cwd, project, start, kind, msgs, acts}],
    cached by (size, mtime). Subagent chats carry `parent` (parent sid) and kind "subagent"."""
    r0 = root()
    hashes, dirs, out, seen = None, {}, [], set()
    for p in _files(r0):
        try:
            st = os.stat(p)
        except OSError:
            continue
        if st.st_mtime < since or st.st_size > SCAN_MAX:
            continue
        seen.add(p)
        key = (st.st_size, st.st_mtime, PRICE_VER)
        with _lock:
            c = _cache.get(p)
        if c and c[0] == key:
            r = c[1]
        else:
            r = read(p)
            with _lock:
                _cache[p] = (key, r)
        if not r:
            continue
        par = _parent(p)
        d = os.path.dirname(os.path.dirname(os.path.dirname(p)) if par else os.path.dirname(p))
        if d not in dirs:
            dirs[d] = _dir_root(d)
        cwd = dirs[d]
        h = r["head"].get("projectHash") or ""
        if not cwd and h:
            if hashes is None:
                hashes = _roots(r0)
            cwd = hashes.get(h, "")
        name = os.path.basename(d)
        sid = r["head"].get("sessionId") or os.path.basename(p)[:-6]
        out.append({"sid": sid, "path": p, "cwd": cwd,
                    "project": _proj_name(cwd) or (name if len(name) < 40 else name[:8]),
                    "start": iso_epoch(r["head"].get("startTime")),
                    "kind": "subagent" if par else (r["head"].get("kind") or ""), "parent": par,
                    "msgs": r["msgs"], "acts": r.get("acts") or {}})
    with _lock:
        if len(_cache) > 2 * len(seen) + 64:
            for k in [k for k in _cache if k not in seen]:
                _cache.pop(k, None)
    return out


def scan(since=0.0):
    """Generic entry point used by ext/timeline/history (looked up at call time, so tests can patch)."""
    return chats(since)


# ── Hook settings check (read by ext.ext_hook_check) ────────────────────────
# ★Interactive `gemini` or `/auth` rewrites settings.json and can silently drop our hooks; sessions then vanish.
# ⚠Read only, never write. Only event names and booleans leave this function — the file may hold keys.
HOOK_EVENTS = ("SessionStart", "SessionEnd", "BeforeAgent", "AfterAgent", "BeforeTool", "AfterTool",
               "Notification")
HOOK_MARK = "ext_hook.py"
HOOK_DOC_EN = "the Gemini section of docs/HOOKS.md"


def hook_settings():
    return os.path.join(root(), "settings.json")


def used_since(since):
    """True if any Gemini chat file changed since `since` (stat only)."""
    for p in _files(root()):
        try:
            if os.stat(p).st_mtime >= since:
                return True
        except OSError:
            continue
    return False


def hook_gaps(cfg):
    """Parsed settings.json -> list of missing items (`hooksConfig.enabled` and/or event names)."""
    if not isinstance(cfg, dict):
        return ["hooksConfig.enabled"] + list(HOOK_EVENTS)
    hc = cfg.get("hooksConfig")
    gaps = [] if isinstance(hc, dict) and hc.get("enabled") is True else ["hooksConfig.enabled"]
    hooks = cfg.get("hooks") if isinstance(cfg.get("hooks"), dict) else {}
    for ev in HOOK_EVENTS:
        groups = hooks.get(ev) if isinstance(hooks.get(ev), list) else []
        ok = any(HOOK_MARK in str(h.get("command") or "")
                 for g in groups if isinstance(g, dict) and isinstance(g.get("hooks"), list)
                 for h in g["hooks"] if isinstance(h, dict))
        if not ok:
            gaps.append(ev)
    return gaps


# ── Harness map items (read by sidereus/harness_plat.py; helpers shared with plat_codex) ──
# Native hook event -> lane event (one of harness.EVENTS) or "" for «Other».
LANE = {"SessionStart": "SessionStart", "BeforeAgent": "UserPromptSubmit", "BeforeTool": "PreToolUse",
        "AfterTool": "PostToolUse", "AfterAgent": "Stop", "PreCompress": "PreCompact", "Notification": "Notification",
        "SessionEnd": "", "BeforeModel": "", "AfterModel": "", "BeforeToolSelection": ""}
RULE_FILE = "GEMINI.md"


def _load_json(p):
    try:
        with open(p, "rb") as f:
            d = json.loads(f.read(1 << 20).decode("utf-8", "replace"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _item(kind, scope, name, path, **kw):
    it = {"kind": kind, "scope": scope, "name": name, "ev": "", "matcher": "", "cmd": "", "timeout": None,
          "transport": "", "on": True, "path": path}
    it.update(kw)
    return it


def hook_items(hooks, scope, path, on=True, ms=False):
    """Claude-shaped `{event: [{matcher, hooks: [{command, timeout}]}]}` -> hook items (`ms`: timeout in milliseconds)."""
    out = []
    for ev, groups in (hooks.items() if isinstance(hooks, dict) else []):
        for g in groups if isinstance(groups, list) else []:
            if not isinstance(g, dict):
                continue
            m = g.get("matcher") if isinstance(g.get("matcher"), str) else ""
            for h in g.get("hooks") if isinstance(g.get("hooks"), list) else []:
                if not isinstance(h, dict):
                    continue
                to = h.get("timeout")
                to = (to / 1000.0 if ms else to) if isinstance(to, (int, float)) and not isinstance(to, bool) else None
                out.append(_item("hook", scope, "", path, ev=str(ev)[:60], matcher=m, timeout=to, on=on,
                                 cmd=h.get("command") if isinstance(h.get("command"), str) else ""))
    return out


def rule_dirs(proj, top):
    """Directories from the git root down to the project (the project alone outside that root)."""
    proj = os.path.realpath(proj)
    top = os.path.realpath(top) if top else proj
    if proj != top and not proj.startswith(top.rstrip(os.sep) + os.sep):
        top = proj
    ds = [proj]
    while ds[-1] != top:
        ds.append(os.path.dirname(ds[-1]))
    return ds[::-1]


def _mcp_items(servers, scope, path, plug="", excluded=()):
    """⚠Transport from key presence only: command/args/env/url/httpUrl/headers values never leave."""
    out = []
    for nm, e in (servers.items() if isinstance(servers, dict) else []):
        if isinstance(e, dict):
            tr = "http" if "httpUrl" in e else "sse" if "url" in e else "stdio" if "command" in e else ""
            out.append(_item("mcp", scope, str(nm)[:120], path, transport=tr, on=nm not in excluded, plug=plug))
    return out


def harness_items(proj, top=""):
    """Raw harness items for one project (`top` = its git root). ⚠Paths/commands stay server-side (harness_plat).
    ★Interactive `gemini` rewrites settings.json, so hooks can vanish between two reads."""
    import glob
    r = root()
    us, ps = os.path.join(r, "settings.json"), os.path.join(proj, ".gemini", "settings.json")
    u, p = _load_json(us), _load_json(ps)
    hc = [c.get("hooksConfig") for c in (p, u) if isinstance(c.get("hooksConfig"), dict) and "enabled" in c["hooksConfig"]]
    on = bool(hc) and hc[0].get("enabled") is True
    mc = [c.get("mcp") for c in (u, p) if isinstance(c.get("mcp"), dict)]
    ex = set(x for m in mc for x in (m.get("excluded") if isinstance(m.get("excluded"), list) else []) if isinstance(x, str))
    out = hook_items(u.get("hooks"), "user", us, on, True) + hook_items(p.get("hooks"), "project", ps, on, True)
    for i, d in enumerate([r] + rule_dirs(proj, top)):
        f = os.path.join(d, RULE_FILE)
        if os.path.isfile(f):
            out.append(_item("rule", "user" if i == 0 else "project", RULE_FILE, f))
    out += _mcp_items(u.get("mcpServers"), "user", us, excluded=ex) + _mcp_items(p.get("mcpServers"), "project", ps, excluded=ex)
    for f in sorted(glob.glob(os.path.join(r, "extensions", "*", "gemini-extension.json"))):
        pn = os.path.basename(os.path.dirname(f))[:80]
        out += _mcp_items(_load_json(f).get("mcpServers"), "plugin", f, plug=pn, excluded=ex)
    for scope, d in (("user", r), ("project", os.path.join(proj, ".gemini"))):
        base = os.path.join(d, "commands")
        for f in sorted(glob.glob(os.path.join(base, "**", "*.toml"), recursive=True)):
            out.append(_item("cmd", scope, os.path.relpath(f, base)[:-5].replace(os.sep, ":"), f))
        for f in sorted(glob.glob(os.path.join(d, "skills", "*", "SKILL.md"))):
            out.append(_item("skill", scope, os.path.basename(os.path.dirname(f)), f))
        for f in sorted(glob.glob(os.path.join(d, "agents", "*.md"))):
            out.append(_item("agent", scope, os.path.basename(f)[:-3], f))
    return out
