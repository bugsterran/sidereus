"""«Tools» inventory — skills, agents, slash commands, MCP servers and hooks Claude Code loads (GET /api/tools).

Sources: ~/.claude/{skills,agents,commands,sidereus-off}, <proj>/.claude/{same}, installed plugins (read-only),
~/.claude.json + <proj>/.mcp.json MCP servers, settings `hooks`. Paths and roots are read from `ctxsrc` at call time.
⚠The list carries names, paths, sizes and usage counts only. `tool_file` returns one item's config text on click;
  MCP env/headers are always masked (`mask_mcp`) and hook commands go through `redact`.
"""
import copy
import difflib
import hashlib
import json
import os
import re
from sidereus import ctxsrc
from sidereus.redact import redact
from sidereus.work import _allowed_cwds
from sidereus.toolidx import tool_uses

KINDS = ("skill", "agent", "cmd", "mcp", "hook")
MASK = "••••"
TOOL_FILE_MAX = 256 * 1024       # same cap the write side enforces
NEAR_RATIO = 0.85                # difflib name similarity that earns the «Similar» flag
_SECRET_KEY = re.compile(r"(?i)secret|token|key|passw(or)?d|auth|credential")
_MASK_KEYS = ("headersHelper",)   # runs a command that prints headers; its text carries the secret
_SECRET_FLAG = re.compile(r"(?i)^-{1,2}[a-z0-9_.-]*(key|token|secret|passw(or)?d|auth)[a-z0-9_.-]*$")


def _read_json(p):
    return ctxsrc._json_file(p)


def _sha(p):
    try:
        with open(p, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return ""


def _size(p):
    try:
        return os.path.getsize(p)
    except OSError:
        return 0


def _abbrev(p):
    home = os.path.expanduser("~")
    return "~" + p[len(home):] if p == home or p.startswith(home + os.sep) else p


def make_id(kind, path, key=None):
    """Opaque id: kind + ":" + sha1(realpath) or sha1(file#keypath) — resolved only server-side."""
    src = os.path.realpath(path) + ("#" + json.dumps(list(key), ensure_ascii=False) if key else "")
    # nosemgrep: python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1 -- opaque id, not security
    return kind + ":" + hashlib.sha1(src.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]


def mask_mcp(entry):
    """Deep copy of one MCP entry: `env`/`headers` values -> MASK, secret-flag args masked, args/url redacted."""
    out = copy.deepcopy(entry) if isinstance(entry, dict) else {}
    for k in ("env", "headers"):
        v = out.get(k)
        if isinstance(v, dict):
            out[k] = {str(n): MASK for n in v}
        elif v is not None:
            out[k] = MASK
    # ⚠args/url carry tokens too (--api-key X, ?token=): mask the value after a secret-looking flag, redact the rest
    args = out.get("args")
    if isinstance(args, list):
        masked, prev = [], ""
        for a in args:
            s = str(a) if not isinstance(a, str) else a
            masked.append(MASK if _SECRET_FLAG.match(prev) else redact(s))
            prev = s
        out["args"] = masked
    # ⚠Any other field may nest a secret (headersHelper, oauth.clientSecret): secret-named keys masked whole, strings redacted
    for k in list(out):
        if k not in ("env", "headers") and not (k == "args" and isinstance(args, list)):
            out[k] = MASK if _secret_key(k) else _mask_deep(out[k])
    return out


def _secret_key(k):
    return str(k) in _MASK_KEYS or bool(_SECRET_KEY.search(str(k)))


def _mask_deep(v):
    if isinstance(v, dict):
        return {k: (MASK if _secret_key(k) else _mask_deep(x)) for k, x in v.items()}
    if isinstance(v, list):
        return [_mask_deep(x) for x in v]
    return redact(v) if isinstance(v, str) else v


def _front(p):
    """`name`/`description` from a markdown frontmatter (first 4 KB only)."""
    try:
        head = ctxsrc.read_text(p, 4096, errors="replace")
    except OSError:
        return {}
    if not head.startswith("---"):
        return {}
    out, blk = {}, None
    for ln in head.split("\n")[1:]:
        if ln.strip() == "---":
            break
        if blk and ln[:1] in (" ", "\t"):   # YAML block scalar body (`description: |`): fold the indented lines into one
            out[blk] = (out[blk] + " " + ln.strip()).strip()
            continue
        blk = None
        k, sep, v = ln.partition(":")
        if sep and k.rstrip() in ("name", "description"):   # ⚠column-0 keys only: a nested `  name:` is not the agent's
            v = v.strip()
            if v in ("|", ">", "|-", ">-", "|+", ">+"):
                blk, v = k.rstrip(), ""
            out[k.rstrip()] = v.strip("\"'")
    return out


def agent_name(p):
    """Agent id the Agent tool's subagent_type uses: frontmatter `name`, else the file name."""
    return _front(p).get("name") or os.path.splitext(os.path.basename(p))[0]


AGENT_DESC_MAX = 120


def agent_desc(p):
    """One-line frontmatter `description` (<= AGENT_DESC_MAX chars + «…»), or "".
    ⚠Most agent files use a block scalar (`description: |`); _front folds its indented body into one line."""
    d = " ".join((_front(p).get("description") or "").split())
    return d if len(d) <= AGENT_DESC_MAX else d[:AGENT_DESC_MAX].rstrip() + "…"


def known_projects():
    """~/.claude.json `projects` keys that are existing dirs + the cwds of sessions on screen (sorted, unique)."""
    pr = _read_json(ctxsrc.CLAUDE_JSON).get("projects")
    out = set(k for k in (pr if isinstance(pr, dict) else {}) if isinstance(k, str) and os.path.isabs(k) and os.path.isdir(k))
    try:
        out |= set(k for k in _allowed_cwds() if isinstance(k, str) and os.path.isabs(k) and os.path.isdir(k))
    except Exception:   # the session list is a bonus; the config keys alone still work
        return sorted(out)
    return sorted(out)


_SKILL_NAME = re.compile(r"[a-z0-9-]{1,60}")     # fullmatch only; same shape as a pipeline stage agent


def skill_names(proj):
    """[{name, scope}] of skills a pipeline stage may name: <proj>/.claude/skills first, then ~/.claude/skills.
    ⚠Names only (`<base>/skills/<n>/SKILL.md` exists) — SKILL.md is never read. sidereus-off and plugin skills are skipped."""
    out, seen = [], set()
    bases = ([("project", os.path.join(proj, ".claude"))] if proj else []) + [("user", ctxsrc.CLAUDE_DIR)]
    for scope, base in bases:
        d = os.path.join(base, "skills")
        try:
            names = sorted(os.listdir(d))
        except OSError:
            continue
        for n in names:
            if _SKILL_NAME.fullmatch(n) and n not in seen and os.path.isfile(os.path.join(d, n, "SKILL.md")):
                seen.add(n)
                out.append({"name": n, "scope": scope})
    return out


def _md_walk(d):
    """[(rel, abs)] of *.md under `d`, recursive and sorted."""
    out = []
    for base, dirs, files in os.walk(d):
        dirs.sort()
        for f in sorted(files):
            if f.endswith(".md"):
                p = os.path.join(base, f)
                out.append((os.path.relpath(p, d), p))
    return out


def _md_items(base, scope, proj, overrides, prefix="", ro=False, plug_on=True):
    """skill/agent/cmd items under one `.claude`-like dir (`base`), including sidereus-off parked files."""
    out = []
    sk = os.path.join(base, "skills")
    try:
        names = sorted(os.listdir(sk))
    except OSError:
        names = []
    for n in names:
        p = os.path.join(sk, n, "SKILL.md")
        if os.path.isfile(p):
            on = plug_on and (ro or overrides.get(n) != "off")
            out.append(dict(kind="skill", scope=scope, proj=proj, name=prefix + n, path=p, file=p, key=[],
                            on=on, ro=ro, base=base, rel=n, ukey="skill:" + prefix + n))
    for kind, sub in (("agent", "agents"), ("cmd", "commands")):
        for off, d in ((False, os.path.join(base, sub)), (True, os.path.join(base, "sidereus-off", sub))):
            if off and ro:
                continue
            for rel, p in _md_walk(d):
                if kind == "agent":
                    # ⚠Plugins ship agent templates/docs under agents/; only frontmatter-named files are agents
                    if scope == "plugin" and not _front(p):
                        continue
                    nm = agent_name(p)
                else:
                    nm = os.path.splitext(rel)[0].replace(os.sep, ":")
                    # Plugin command that shadows its own skill = one tool: fold into the skill row, uses summed
                    sk_row = next((x for x in out if x["kind"] == "skill" and x["rel"] == nm), None) if scope == "plugin" else None
                    if sk_row is not None:
                        sk_row.setdefault("ukeys", []).append(kind + ":" + prefix + nm)
                        continue
                out.append(dict(kind=kind, scope=scope, proj=proj, name=prefix + nm, path=p, file=p, key=[],
                                on=plug_on and not off, ro=ro, base=base, rel=rel, ukey=kind + ":" + prefix + nm))
    return out


def _mcp_items(file, key, servers, scope, proj, disabled=(), ro=False, on=True):
    out = []
    for n in sorted(servers if isinstance(servers, dict) else {}):
        out.append(dict(kind="mcp", scope=scope, proj=proj, name=str(n), path=file, file=file,
                        key=list(key) + [n], on=on and n not in disabled, ro=ro, entry=servers[n],
                        ukey="mcp:" + str(n)))
    return out


def _hook_items(file, hooks, scope, proj, ro=False):
    out = []
    for ev in sorted(hooks if isinstance(hooks, dict) else {}):
        for i, g in enumerate(hooks[ev] if isinstance(hooks[ev], list) else []):
            if not isinstance(g, dict):
                continue
            m = g.get("matcher")
            nm = str(ev) + (" " + str(m) if isinstance(m, str) and m else "")
            out.append(dict(kind="hook", scope=scope, proj=proj, name=nm, path=file, file=file,
                            key=["hooks", ev, i], on=True, ro=ro, entry=g, ukey=""))
    return out


def _plugins(user_settings):
    """Installed plugins: [(label, install dir, enabled)]."""
    reg = _read_json(os.path.join(ctxsrc.CLAUDE_DIR, "plugins", "installed_plugins.json")).get("plugins")
    en = user_settings.get("enabledPlugins") if isinstance(user_settings.get("enabledPlugins"), dict) else {}
    out = []
    for k in sorted(reg if isinstance(reg, dict) else {}):
        for inst in (reg[k] if isinstance(reg[k], list) else []):
            d = inst.get("installPath") if isinstance(inst, dict) else None
            if isinstance(d, str) and os.path.isdir(d):
                out.append((str(k).split("@", 1)[0], d, bool(en.get(k, True))))
                break
    return out


def _raw_items():
    """Every item with its private fields (file, key, entry, base, rel). Deduped by id."""
    cd = ctxsrc.CLAUDE_DIR
    us_path = os.path.join(cd, "settings.json")
    us = _read_json(us_path)
    ov = us.get("skillOverrides") if isinstance(us.get("skillOverrides"), dict) else {}
    items = _md_items(cd, "user", "", ov)
    cj = _read_json(ctxsrc.CLAUDE_JSON)
    items += _mcp_items(ctxsrc.CLAUDE_JSON, ["mcpServers"], cj.get("mcpServers"), "user", "")
    items += _hook_items(us_path, us.get("hooks"), "user", "")
    ul = os.path.join(cd, "settings.local.json")
    items += _hook_items(ul, _read_json(ul).get("hooks"), "user", "", ro=True)
    cjp = cj.get("projects") if isinstance(cj.get("projects"), dict) else {}
    home_rc = os.path.realpath(cd)
    for proj in known_projects():
        base = os.path.join(proj, ".claude")
        if os.path.realpath(base) == home_rc:
            continue
        loc_path = os.path.join(base, "settings.local.json")
        loc = _read_json(loc_path)
        pov = loc.get("skillOverrides") if isinstance(loc.get("skillOverrides"), dict) else {}
        items += _md_items(base, "project", proj, pov)
        pj = cjp.get(proj) if isinstance(cjp.get(proj), dict) else {}
        items += _mcp_items(ctxsrc.CLAUDE_JSON, ["projects", proj, "mcpServers"], pj.get("mcpServers"), "project", proj)
        dis = set(x for v in (loc.get("disabledMcpjsonServers"), pj.get("disabledMcpjsonServers"))
                  for x in (v if isinstance(v, list) else []) if isinstance(x, str))   # ⚠a non-list value is ignored, not a crash
        mj = os.path.join(proj, ".mcp.json")
        items += _mcp_items(mj, ["mcpServers"], _read_json(mj).get("mcpServers"), "project", proj, disabled=dis)
        sp = os.path.join(base, "settings.json")
        items += _hook_items(sp, _read_json(sp).get("hooks"), "project", proj, ro=True)
        items += _hook_items(loc_path, loc.get("hooks"), "project", proj)
    for label, d, on in _plugins(us):
        items += _md_items(d, "plugin", "", {}, prefix=label + ":", ro=True, plug_on=on)
        mj = os.path.join(d, ".mcp.json")
        items += _mcp_items(mj, ["mcpServers"], _read_json(mj).get("mcpServers"), "plugin", "", ro=True, on=on)
        hj = os.path.join(d, "hooks", "hooks.json")
        items += _hook_items(hj, _read_json(hj).get("hooks"), "plugin", "", ro=True)
    out, seen = [], set()
    for it in items:
        it["id"] = make_id(it["kind"], it["file"], it["key"])
        if it["id"] not in seen:
            seen.add(it["id"])
            out.append(it)
    return out


def item_by_id(item_id):
    """Private item dict (kind, scope, name, path, file, key, proj, on, ro, base, rel, entry) or None."""
    if not isinstance(item_id, str) or ":" not in item_id or item_id.split(":", 1)[0] not in KINDS:
        return None
    for it in _raw_items():
        if it["id"] == item_id:
            return it
    return None


def _item_bytes(it):
    if it["kind"] in ("mcp", "hook"):
        return len(json.dumps(it.get("entry"), ensure_ascii=False).encode("utf-8"))
    return _size(it["path"])


def _flags(rows):
    by = {}
    for r in rows:
        by.setdefault(r["kind"], []).append(r)
    for kind, rs in by.items():
        cnt = {}
        for r in rs:
            cnt[r["name"]] = cnt.get(r["name"], 0) + 1
        names = sorted(cnt)
        near = set()
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                if difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() >= NEAR_RATIO:
                    near.update((a, b))
        for r in rs:
            f = []
            if kind != "hook" and r["on"] and not r["uses"]:
                f.append("unused")
            if cnt[r["name"]] > 1:
                f.append("dup")
            if r["name"] in near:
                f.append("near")
            r["flags"] = f


def scan_items(days=30):
    """Public rows for GET /api/tools: names, paths (~-abbreviated), sizes, usage — no config text."""
    uses = tool_uses(days)
    shas = {}
    rows = []
    for it in _raw_items():
        us = [uses.get(k) or {} for k in [it["ukey"]] + it.get("ukeys", []) if k]
        u = {"n": sum(int(x.get("n") or 0) for x in us), "last": max([int(x.get("last") or 0) for x in us] or [0])}
        n = _item_bytes(it)
        if it["file"] not in shas:
            shas[it["file"]] = _sha(it["file"])
        rows.append({"id": it["id"], "kind": it["kind"], "name": it["name"], "scope": it["scope"],
                     "proj": _abbrev(it["proj"]) if it["proj"] else "", "path": _abbrev(it["path"]),
                     "bytes": n, "tok": ctxsrc._tok(n), "on": it["on"], "ro": it["ro"],
                     "uses": int(u.get("n") or 0), "last": int(u.get("last") or 0), "sha": shas[it["file"]]})
    _flags(rows)
    rows.sort(key=lambda r: (KINDS.index(r["kind"]), r["scope"], r["name"].lower(), r["path"]))
    return rows


def tool_file(item_id):
    """(code, body) for GET /api/tools/file — one item's text: .md as is, MCP masked, hook redacted."""
    it = item_by_id(item_id)
    if not it:
        return 404, {"ok": False, "msg": "No such item."}
    try:
        mt = os.stat(it["file"]).st_mtime
    except OSError:
        return 404, {"ok": False, "msg": "File not found."}
    if it["kind"] == "mcp":
        text = json.dumps(mask_mcp(it["entry"]), ensure_ascii=False, indent=2)
    elif it["kind"] == "hook":
        g = it["entry"]
        lines = ["event: " + str(it["key"][1]), "matcher: " + str(g.get("matcher") or "")]
        for h in (g.get("hooks") if isinstance(g.get("hooks"), list) else []):
            if isinstance(h, dict):
                lines.append("command: " + redact(str(h.get("command") or h.get("type") or "")))
        text = "\n".join(lines)
    else:
        # ⚠A symlinked skill/agent may point anywhere; serve only inside ~/.claude or its project, never a transcript
        rp = os.path.realpath(it["path"])
        roots = [os.path.realpath(x) for x in (ctxsrc.CLAUDE_DIR, it["proj"]) if x]
        if rp.endswith(".jsonl") or not any(rp == r or rp.startswith(r.rstrip(os.sep) + os.sep) for r in roots):
            return 404, {"ok": False, "msg": "File not found."}
        if _size(it["path"]) > TOOL_FILE_MAX:
            return 413, {"ok": False, "msg": "The file is too large."}
        try:
            with open(it["path"], encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            return 404, {"ok": False, "msg": "File not found."}
    return 200, {"ok": True, "id": it["id"], "kind": it["kind"], "text": text, "sha": _sha(it["file"]), "mtime": mt}
