"""Codex CLI platform: everything Codex-specific in one place (event names, rollout reader, prices, labels).

The generic code (sidereus/ext.py, timeline.py, history.py) reads this module through `ext.PLAT_MODS`.
Formats: Codex CLI 0.156.1 (source tag rust-v0.156.1) — hooks.json events, rollout JSONL
`$CODEX_HOME/sessions/YYYY/MM/DD/rollout-<ts>-<uuid>.jsonl` (+ `archived_sessions/`).
⚠Metadata only: timestamps, ids, cwd, model, token counts, rate-limit numbers. Message text
(response_item, user prompts, tool input/output, last_assistant_message) is never read into a result.
⚠Codex tokens/cost never enter Claude's 5h/7d/cost totals — they stay in the ext store like Gemini's.
"""
import json
import os
import re
import threading

from sidereus.ident import _proj_name, _real_home
from sidereus.plat_gemini import _item, _load_json, hook_items, rule_dirs
from sidereus.transcript import iso_epoch

PLAT = "codex"         # hook `platform` value
KEY = "cx"              # row `plat` key (same as the logo `AILG.cx`)
NAME = "Codex"
CHILD_LABEL = "codex exec"   # a run launched from a Claude session's Bash

# Codex hook event -> Sidereus wire event. ⚠Mirrored in ext-hooks/ext_hook.py (standalone script, copied into
# other CLIs, so it cannot import this); tests/test_codex.py asserts the two are equal.
# ★No `Notification` event in Codex: `PermissionRequest` is the «waiting for a person» signal (hook prints nothing).
EVENTS = {
    "SessionStart": "SessionStart",
    "SessionEnd": "SessionEnd",
    "PreToolUse": "PreToolUse",
    "PostToolUse": "PostToolUse",
    "UserPromptSubmit": "UserPromptSubmit",
    "Stop": "Stop",
    "PermissionRequest": "Notification",
    "Interrupt": "Stop",
    "Notification": "Notification",     # never sent by Codex; kept so `--event Notification` still works
}

# OpenAI API Standard tier, USD per 1M tokens: (input, cached input, cache write, output incl. reasoning).
# Source: https://developers.openai.com/api/docs/pricing (read 2026-09-24).
# ⚠Short-context prices only: the page lists long-context prices but not the threshold that triggers them,
#   so long prompts are under-estimated. ⚠A ChatGPT-plan login is not billed per token — this is an estimate.
PRICE_VER = "2026-09-24"
PRICE = {
    "gpt-6-astra": (10.0, 1.0, 12.5, 50.0),
    "gpt-6-sol": (2.0, 0.2, 2.5, 10.0),
    "gpt-6-luna": (0.10, 0.01, 0.125, 0.50),
    "gpt-5.6-sol": (4.0, 0.4, 5.0, 20.0),
}
_DATED = re.compile(r"-\d{4}-\d{2}-\d{2}$")


def cost(model, uncached, cached, write, out):
    """USD for one request, or None for a model not in the table (same rule as Gemini).
    `uncached` includes `write`; `out` includes reasoning tokens."""
    p = PRICE.get(model) or PRICE.get(_DATED.sub("", model or ""))
    if not p:
        return None
    w = min(max(0, write), max(0, uncached))
    return ((uncached - w) * p[0] + cached * p[1] + w * p[2] + out * p[3]) / 1e6


def root():
    return os.environ.get("CODEX_HOME") or os.path.join(_real_home(), ".codex")


def _n(d, k):
    v = d.get(k) if isinstance(d, dict) else None
    return max(0, int(v)) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def _usage(u, ts, model):
    """TokenUsage -> (in, out, cache, thought, ts, model, cost) — the ext store's per-request tuple.
    ★input_tokens INCLUDES cached (Codex `non_cached_input` = input - cached); output INCLUDES reasoning."""
    cached = _n(u, "cached_input_tokens")
    unc = max(0, _n(u, "input_tokens") - cached)
    out = _n(u, "output_tokens")
    th = min(_n(u, "reasoning_output_tokens"), out)
    return (unc, out - th, cached, th, ts, model,
            cost(model, unc, cached, _n(u, "cache_write_input_tokens"), out))


def _rate(rl):
    """rate_limits -> {primary/secondary: {pct, win, reset}, plan} or None (often null: Codex bug #14880)."""
    if not isinstance(rl, dict):
        return None
    out = {}
    for k in ("primary", "secondary"):
        w = rl.get(k)
        if isinstance(w, dict) and isinstance(w.get("used_percent"), (int, float)):
            out[k] = {"pct": float(w["used_percent"]), "win": _n(w, "window_minutes"),
                      "reset": _n(w, "resets_at")}
    if not out:
        return None
    if isinstance(rl.get("plan_type"), str):
        out["plan"] = rl["plan_type"][:20]
    return out


# Only lines of these types are parsed; the byte test skips big response_item lines without json.loads.
_WANT = (b'"session_meta"', b'"turn_context"', b'"token_count"')


_SID_CH = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _parent_thread(p):
    """Parent thread id of a subagent rollout (top-level or one level inside source.subagent), else ""."""
    cands = [p.get("parent_thread_id")]
    sub = p.get("source").get("subagent") if isinstance(p.get("source"), dict) else None
    if isinstance(sub, dict):
        cands.append(sub.get("parent_thread_id"))
        cands.extend(v.get("parent_thread_id") for v in sub.values() if isinstance(v, dict))
    return next((c for c in cands if isinstance(c, str) and _SID_CH.match(c)), "")


def read(path):
    """One rollout file -> {head, msgs, acts, rate}. msgs: key -> per-request tuple; acts: key -> ts."""
    head, msgs, acts, rate = {}, {}, {}, None
    model, prev = "", None
    try:
        with open(path, "rb") as f:
            for i, ln in enumerate(f):
                if not any(w in ln for w in _WANT):
                    continue
                try:
                    o = json.loads(ln)
                except ValueError:
                    continue
                if not isinstance(o, dict) or not isinstance(o.get("payload"), dict):
                    continue
                p, typ = o["payload"], o.get("type")
                t = iso_epoch(o.get("timestamp"))
                if typ == "session_meta" and not head:
                    src = p.get("source")
                    # ⚠A subagent rollout has an object source ({"subagent": ...}); keep only the marker and parent id.
                    head = {"id": str(p.get("id") or "")[:64], "cwd": str(p.get("cwd") or ""),
                            "start": iso_epoch(p.get("timestamp")) or t,
                            "source": src if isinstance(src, str) else ("subagent" if isinstance(src, dict)
                                                                        and "subagent" in src else ""),
                            "parentThread": _parent_thread(p)}
                elif typ == "turn_context":
                    # ★session_meta has no model; it is per turn and can change.
                    model = str(p.get("model") or model)[:40]
                    if t:
                        acts["t%d" % i] = t
                elif typ == "event_msg" and p.get("type") == "token_count":
                    rt = _rate(p.get("rate_limits"))
                    if rt and t and (rate is None or t >= rate[0]):
                        rate = (t, rt)
                    info = p.get("info")
                    if not isinstance(info, dict) or not isinstance(info.get("last_token_usage"), dict):
                        continue
                    # ★Sum per-request `last_token_usage`, not the cumulative total (rewritten after compaction).
                    #   A repeat event with an unchanged total is the same request re-announced.
                    tot = info.get("total_token_usage")
                    if isinstance(tot, dict) and tot == prev:
                        continue
                    prev = tot if isinstance(tot, dict) else None
                    k = "%s#%s" % (o.get("timestamp") or "", o.get("ordinal", "l%d" % i))
                    msgs[k] = _usage(info["last_token_usage"], t, model)
                    if t:
                        acts[k] = t
    except OSError:
        return None
    return {"head": head, "msgs": msgs, "acts": acts, "rate": rate, "model": model}


SCAN_MAX = 256 << 20      # skip rollout files larger than this
_lock = threading.Lock()
_cache = {}               # path -> ((size, mtime, price ver), parsed)
_stat = {"zst": 0}        # compressed rollouts seen by the last scan (stdlib cannot decode zstd)


def _files(r):
    import glob
    pats = (os.path.join(r, "sessions", "*", "*", "*", "rollout-*"),
            os.path.join(r, "archived_sessions", "rollout-*"),
            os.path.join(r, "archived_sessions", "*", "*", "*", "rollout-*"))
    return [p for pat in pats for p in glob.glob(pat)]


def _read_cached(path, st):
    key = (st.st_size, st.st_mtime, PRICE_VER)
    with _lock:
        c = _cache.get(path)
    if c and c[0] == key:
        return c[1]
    r = read(path)
    with _lock:
        _cache[path] = (key, r)
    return r


def path_ok(path):
    """Only a rollout under the Codex home — the path arrives in a hook POST."""
    if not path or not path.endswith(".jsonl"):
        return False
    rp = os.path.realpath(path)
    base = os.path.realpath(root())
    return any(rp.startswith(os.path.join(base, d) + os.sep) for d in ("sessions", "archived_sessions"))


def session_msgs(path):
    """Per-request tuples of one live session's rollout (hook `transcript_path`), or None."""
    if not path_ok(path):
        return None
    try:
        st = os.stat(path)
    except OSError:
        return None
    if st.st_size > SCAN_MAX:
        return None
    r = _read_cached(path, st)
    return dict(r["msgs"]) if r else None


def codex_rollouts(since=0.0):
    """Rollouts modified since `since` -> [{sid, path, cwd, project, start, kind, msgs, acts, rate, model, mtime, live}]
    (the `plat_gemini.chats` shape). Same sid in two files (archived copy, resume) merges by request key.
    `model` = last turn_context of the newest file · `live` = some file is under sessions/, not archived_sessions/."""
    by, seen, zst = {}, set(), 0
    live_dir = os.path.join(os.path.realpath(root()), "sessions") + os.sep
    for p in _files(root()):
        if p.endswith(".jsonl.zst"):
            zst += 1
            continue
        if not p.endswith(".jsonl"):
            continue
        try:
            st = os.stat(p)
        except OSError:
            continue
        if st.st_mtime < since or st.st_size > SCAN_MAX:
            continue
        seen.add(p)
        r = _read_cached(p, st)
        if not r:
            continue
        sid = r["head"].get("id") or os.path.basename(p)[:-6]
        c = by.get(sid)
        if c is None:
            cwd = r["head"].get("cwd") or ""
            c = by[sid] = {"sid": sid, "path": p, "cwd": cwd, "project": _proj_name(cwd) or "?",
                           "start": r["head"].get("start") or 0.0, "kind": r["head"].get("source") or "",
                           "parentThread": r["head"].get("parentThread") or "",
                           "msgs": {}, "acts": {}, "rate": None, "model": "", "mtime": 0.0, "live": False}
        if st.st_mtime >= c["mtime"]:
            c["mtime"] = st.st_mtime
            c["model"] = r.get("model") or c["model"]
        c["live"] = c["live"] or os.path.realpath(p).startswith(live_dir)
        c["msgs"].update(r["msgs"])
        c["acts"].update(r["acts"])
        if r["rate"] and (c["rate"] is None or r["rate"][0] >= c["rate"][0]):
            c["rate"] = r["rate"]
    _stat["zst"] = zst
    with _lock:
        if len(_cache) > 2 * len(seen) + 64:
            for k in [k for k in _cache if k not in seen]:
                _cache.pop(k, None)
    return list(by.values())


def scan(since=0.0):
    """Generic entry point used by ext/timeline/history (looked up at call time, so tests can patch)."""
    return codex_rollouts(since)


# ── Harness map items (read by sidereus/harness_plat.py) ───────────────────────
# Native hook event -> lane event (one of harness.EVENTS) or "" for «Other». ⚠Not EVENTS above (wire names).
LANE = {"SessionStart": "SessionStart", "UserPromptSubmit": "UserPromptSubmit", "PreToolUse": "PreToolUse",
        "PostToolUse": "PostToolUse", "Stop": "Stop", "Interrupt": "Stop", "PermissionRequest": "Notification",
        "SessionEnd": ""}
RULE_FILE = "AGENTS.md"
_TOML_SEC = re.compile(r'^\[\s*mcp_servers\s*\.\s*("([^"]+)"|\'([^\']+)\'|[A-Za-z0-9_-]+)\s*(\.[^\]]*)?\]\s*(#.*)?$')
_TOML_KEY = re.compile(r"^([A-Za-z0-9_-]+)\s*=\s*(.*)$")


def toml_mcp(p):
    """[(name, transport, enabled)] from `[mcp_servers.<n>]` tables — a line parser, not TOML (3.9 has no tomllib).
    ⚠Only key names and the `enabled` boolean are read; values (command/args/env/url/headers) are never kept.
    ⚠Inline-table form (`mcp_servers = { … }`) is not seen."""
    out, cur = {}, None
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read(1 << 20).splitlines()
    except OSError:
        return []
    for ln in lines:
        s = ln.strip()
        if s.startswith("["):
            m = _TOML_SEC.match(s)
            if not m:
                cur = None
                continue
            nm = m.group(2) or m.group(3) or m.group(1)
            cur = None if m.group(4) else out.setdefault(nm[:120], {"t": "", "on": True})   # sub-tables (.env) skipped
            continue
        m = _TOML_KEY.match(s) if cur is not None else None
        if m and m.group(1) == "command":
            cur["t"] = "stdio"
        elif m and m.group(1) == "url" and not cur["t"]:
            cur["t"] = "http"
        elif m and m.group(1) == "enabled":
            cur["on"] = not m.group(2).split("#")[0].strip().startswith("false")
    return [(k, v["t"], v["on"]) for k, v in out.items()]


def harness_items(proj, top=""):
    """Raw harness items for one project (`top` = its git root). ⚠Paths/commands stay server-side (harness_plat)."""
    import glob
    r = root()
    out = hook_items(_load_json(os.path.join(r, "hooks.json")).get("hooks"), "user", os.path.join(r, "hooks.json"))
    for i, d in enumerate([r] + rule_dirs(proj, top)):
        p = os.path.join(d, RULE_FILE)
        if os.path.isfile(p):
            out.append(_item("rule", "user" if i == 0 else "project", RULE_FILE, p))
    for scope, cfg in (("user", os.path.join(r, "config.toml")), ("project", os.path.join(proj, ".codex", "config.toml"))):
        for nm, tr, on in toml_mcp(cfg):
            out.append(_item("mcp", scope, nm, cfg, transport=tr, on=on))
    for p in sorted(glob.glob(os.path.join(r, "prompts", "*.md"))):
        out.append(_item("cmd", "user", os.path.basename(p)[:-3], p))
    for scope, d in (("user", r), ("project", os.path.join(proj, ".codex"))):
        for p in sorted(glob.glob(os.path.join(d, "skills", "*", "SKILL.md"))):
            out.append(_item("skill", scope, os.path.basename(os.path.dirname(p)), p))
    return out
