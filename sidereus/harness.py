"""«Tooling map» — what Claude Code wraps around a session in one project (GET /api/harness).

Hooks per event (scope · source file · matcher · command basename · timeout · effect · run count), rule files in load
order, agents with the pipeline stages that use them, skill/cmd/MCP counts, MCP servers (name · scope · transport) and
skills with their call counts.
⚠Metadata only: a hook command goes out as the basename of its script (no args, no env, no path); the script is read
  (≤ HN_SCRIPT_MAX bytes, only under ~/.claude, the data dir or the project) to classify its effect, never sent.
  Outside those roots the file is only stat'ed (exists → «ext»), never opened.
GET /api/harness/file opens one card's file on click by an opaque `open` ref, re-derived from config server-side.
"""
import json
import os
import re
import shlex
import shutil

from sidereus import ctxsrc, toolinv
from sidereus.config import DATA_DIR
from sidereus.pipeline import _agent_files, _agents, pipelines
from sidereus.pipeline_projects import _proj_ok
from sidereus.redact import redact
from sidereus.toolidx import hook_hash, mcp_status, scanning, tool_uses

EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop", "SubagentStop", "PreCompact",
          "PostCompact", "Notification")
HN_SCRIPT_MAX = 64 * 1024
HN_CMD_MAX = 80
HN_FILE_MAX = 256 * 1024     # rule / agent / skill .md opened by /api/harness/file
TI_NAME = 120                # MCP / skill name cap in the rows
HN_TOOL_EVENTS = ("PreToolUse", "PostToolUse", "PostToolUseFailure", "PermissionRequest")   # matcher = tool name
_OPEN_EFF = ("inject", "block", "log")   # text scripts under the readable roots
_LANG = {".py": "python", ".js": "js", ".mjs": "js", ".cjs": "js", ".ts": "ts", ".sh": "sh", ".bash": "sh", ".zsh": "sh",
         ".md": "md", ".json": "json", ".rb": "ruby", ".pl": "perl"}
# ⚠Keys, not labels: 47b-harness.js HN_EFF maps them to text; a label here renders as «unknown» on every chip.
EFF_INJECT, EFF_BLOCK, EFF_LOG, EFF_BIN, EFF_EXT, EFF_UNKNOWN = "inject", "block", "log", "bin", "ext", "unknown"
_BIN_MAGIC = (b"\x7fELF", b"MZ", b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xfe\xed\xfa\xce",
              b"\xca\xfe\xba\xbe")   # ELF · PE · Mach-O 64/32 (both byte orders) · universal
_INTERP = re.compile(r"^(python[0-9.]*|node|bash|sh|zsh|deno|bun|ruby|perl|env|uv|uvx|npx|run)$")
_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_NAME_LIKE = re.compile(r"^[A-Za-z0-9._@+-]+$")
_RX_INJECT = re.compile(r"additionalContext")
_RX_BLOCK = re.compile(r"""exit\(?\s*2\b|["']decision["'].*["']block["']|permissionDecision""")
_EFF_CACHE = {}              # (realpath, mtime) -> (effect, desc)
HN_DESC_MAX = 120
_RX_CODING = re.compile(r"^#\s*(-\*-.*)?(vim:.*)?coding[:=]")
# ⚠A header line that looks like it carries a credential is dropped whole, not masked.
_RX_DESC_SECRET = re.compile(r"(?i)(key|token|secret|passw(or)?d|auth)\w*\s*[=:]\s*\S{6,}|=\s*[\"']?[A-Za-z0-9_+/.\-]{20,}")


def _dup_key(h, c):
    """Dup key of a hook: hash of the command, or of the prompt text for type:"prompt" (hash only, never the text)."""
    if isinstance(c, str):
        return hook_hash(c)[:8]
    t = h.get("prompt")
    return hook_hash("prompt\0" + t)[:8] if isinstance(t, str) and t else ""


def _src(it):
    """user · user-local · project · project-local · plugin, from the item scope and its settings file name."""
    if it["scope"] == "plugin":
        return "plugin"
    return it["scope"] + ("-local" if os.path.basename(it["file"]) == "settings.local.json" else "")


def _argv(cmd):
    try:
        if os.name != "nt":
            return shlex.split(cmd)
        # ⚠Windows: escapes off so `C:\h\x.py` keeps its `\` (POSIX shlex gave `C:hx.py`); quotes still removed,
        # also inside a token (`"${ROOT}"/x.mjs`, kept by posix=False). Same as hook_fields.split_cmd.
        lx = shlex.shlex(cmd, posix=True)
        lx.whitespace_split, lx.escape, lx.commenters = True, "", ""
        return list(lx)
    except ValueError:       # unbalanced quotes: a plain split still finds the script token
        return cmd.split()


def _script_tok(cmd):
    """The token that names what runs: interpreters, their flags and leading VAR=x are skipped."""
    toks = _argv(cmd if isinstance(cmd, str) else "")
    i = 0
    while i < len(toks) and _ENV_ASSIGN.match(toks[i]):
        i += 1
    while i < len(toks) and (_INTERP.match(os.path.basename(toks[i])) or toks[i].startswith("-")):
        i += 1
    if i < len(toks):
        return toks[i]
    return toks[0] if toks and not _ENV_ASSIGN.match(toks[0]) else ""


def cmd_name(cmd):
    """Basename of the script a hook command runs; MASK when that token looks like a secret."""
    t = _script_tok(cmd)
    b = os.path.basename(t.rstrip("/"))[:HN_CMD_MAX]
    # ⚠Inline code (node -e "…", bash -c "…") is a token too: anything not name-like is masked, never shown.
    if not b or "=" in b or b.startswith("-") or toolinv._SECRET_FLAG.match(b) or not _NAME_LIKE.match(b):
        return toolinv.MASK if b else ""
    return b


def _resolve(tok, proj, plug_root):
    """Absolute script path, or "" when it cannot be resolved without running a shell."""
    rep = {"CLAUDE_PROJECT_DIR": proj or "", "CLAUDE_PLUGIN_ROOT": plug_root or "", "HOME": os.path.expanduser("~")}
    t = re.sub(r"\$\{?([A-Z_]+)\}?", lambda m: rep.get(m.group(1), "\0"), tok)
    if "\0" in t or not t:
        return ""
    t = os.path.expanduser(t)
    if os.path.isabs(t):
        return t
    if os.sep not in t:      # bare name: the shell finds it on PATH
        return shutil.which(t) or ""
    return os.path.join(proj, t) if proj else ""


def _under(p, roots):
    rp = os.path.realpath(p)
    return any(r and (rp == r or rp.startswith(r.rstrip(os.sep) + os.sep)) for r in roots)


def _clip_desc(t):
    """One header line as a label: markdown/quotes stripped, whitespace collapsed, ≤ HN_DESC_MAX, "" if secret-looking."""
    t = " ".join(t.replace("**", "").replace("`", "").split()).strip("\"' ")
    if not t or _RX_DESC_SECRET.search(t) or any(toolinv._SECRET_FLAG.match(w) for w in t.split()):
        return ""
    return t if len(t) <= HN_DESC_MAX else t[:HN_DESC_MAX - 1] + "…"


def header_desc(src):
    """First line of a leading docstring or of a leading # / // comment block ("" when the script starts with code)."""
    lines = src.splitlines()[:60]
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s or s.startswith("#!") or (s.startswith("#") and _RX_CODING.search(s)):
            continue
        if s[:3] in ('"""', "'''"):
            q, body = s[:3], s[3:]
            if q in body or body.strip():
                return _clip_desc(body.split(q)[0])
            for nx in lines[i + 1:]:
                if nx.strip():
                    return _clip_desc(nx.split(q)[0])
            return ""
        if s.startswith("//") or s.startswith("#"):
            t = s.lstrip("/#").strip()
            if t:
                return _clip_desc(t)
            continue
        return ""
    return ""


def _scan(path, proj, roots=None):
    """(effect, desc) of a script. Cached by (realpath, mtime); outside the readable roots the file is never opened.
    `roots` (other platforms) replaces the default ~/.claude · data dir · project."""
    if not path or not os.path.isfile(path):
        return EFF_UNKNOWN, ""
    roots = [os.path.realpath(x) for x in (roots if roots is not None else (ctxsrc.CLAUDE_DIR, DATA_DIR, proj)) if x]
    if not _under(path, roots):
        return EFF_EXT, ""
    rp = os.path.realpath(path)
    try:
        mt = os.path.getmtime(rp)
    except OSError:
        return EFF_UNKNOWN, ""
    k = (rp, mt)
    if k not in _EFF_CACHE:
        try:
            with open(rp, "rb") as f:
                raw = f.read(HN_SCRIPT_MAX)
        except OSError:
            return EFF_UNKNOWN, ""
        if raw.startswith(_BIN_MAGIC) or b"\0" in raw[:4096]:
            _EFF_CACHE[k] = (EFF_BIN, "")
            return _EFF_CACHE[k]
        src = raw.decode("utf-8", "replace")
        eff = EFF_INJECT if _RX_INJECT.search(src) else EFF_BLOCK if _RX_BLOCK.search(src) else EFF_LOG
        _EFF_CACHE[k] = (eff, header_desc(src))
    return _EFF_CACHE[k]


def effect(path, proj, roots=None):
    """Effect key: inject · block · log · bin (compiled) · ext (outside the readable roots) · unknown."""
    return _scan(path, proj, roots)[0]


def _plugin_desc(plug):
    """`description` of <plugin root>/.claude-plugin/plugin.json; only under ~/.claude."""
    p = os.path.join(plug, ".claude-plugin", "plugin.json") if plug else ""
    if not p or not os.path.isfile(p) or not _under(p, [os.path.realpath(ctxsrc.CLAUDE_DIR)]):
        return ""
    try:
        with open(p, "rb") as f:
            d = json.loads(f.read(HN_SCRIPT_MAX).decode("utf-8", "replace"))
    except (OSError, ValueError):
        return ""
    v = d.get("description") if isinstance(d, dict) else None
    return _clip_desc(v) if isinstance(v, str) else ""


def _runs(uses, ev, matcher, cmd=None):
    """Hook runs from toolidx `hook:<Event>[:<name>]` keys whose name the matcher accepts (empty / * = every run).
    With `cmd`: only `hookc:` keys of that command (per hook; the plain keys count the whole matcher group)."""
    n = last = 0
    m = matcher if isinstance(matcher, str) else ""
    pre, tail = ("hookc:", "#" + hook_hash(cmd)) if cmd is not None else ("hook:", "")
    for k, v in uses.items():
        if not k.startswith(pre) or (tail and not k.endswith(tail)):
            continue
        e, _, sub = k[len(pre):len(k) - len(tail)].partition(":")
        if e != ev:
            continue
        ok = not m or m == "*"
        if not ok:
            try:
                ok = bool(re.fullmatch(m, sub))
            except re.error:
                ok = m == sub
        if ok:
            n += int(v.get("n") or 0)
            last = max(last, int(v.get("last") or 0))
    return n, last


def _nomatch(ev, matcher, tools):
    """1 when a tool-event matcher accepts none of the tool names used in the window (provable idle); 0 otherwise."""
    if ev not in HN_TOOL_EVENTS or not matcher or matcher == "*" or not tools:
        return 0
    for t in tools:
        try:
            if re.fullmatch(matcher, t):
                return 0
        except re.error:
            if matcher == t:
                return 0
    return 1


def _hook_rows(items, proj, uses, paths=None):
    """Rows per event; `paths` (when given) collects ref -> resolved script for /api/harness/file."""
    by = {}
    tools = [k[5:] for k in uses if k.startswith("tool:")]   # toolidx `tool:<Name>` keys
    for it in items:
        g = it.get("entry") if isinstance(it.get("entry"), dict) else {}
        ev = str(it["key"][1]) if len(it["key"]) > 1 else ""
        plug = os.path.dirname(os.path.dirname(it["file"])) if it["scope"] == "plugin" else ""
        pn = os.path.basename(plug)
        if re.match(r"^\d", pn):   # cache/<market>/<plugin>/<version>/
            pn = os.path.basename(os.path.dirname(plug))
        m = g.get("matcher") if isinstance(g.get("matcher"), str) else ""
        hs = [h for h in (g.get("hooks") if isinstance(g.get("hooks"), list) else []) if isinstance(h, dict)]
        cs = [h.get("command") if h.get("type", "command") == "command" else None for h in hs]
        for h, c in zip(hs, cs):
            # ⚠hook_success is written only for runs that printed something: a silent hook has no record at all, and
            # the plain `hook:<Event>` key mixes every group's records. So count per command hash; 0 = unknown
            # (n None, `quiet`), never the group/event total.
            n, last = _runs(uses, ev, m, c) if isinstance(c, str) else (0, 0)
            quiet = int(not n)
            n = n or None
            sp = ""
            if isinstance(c, str):
                tok = _script_tok(c)
                name = cmd_name(c)
                sp = _resolve(tok, proj, plug)
                eff, desc = _scan(sp, proj)
            else:
                name, eff, desc = str(h.get("type") or "")[:HN_CMD_MAX], EFF_UNKNOWN, ""
            if not desc and plug:
                desc = _plugin_desc(plug)
            to = h.get("timeout")
            ref = "h:%s:%d" % (ev, len(by.get(ev, [])))   # ⚠opaque index: the absolute path never goes in the row
            if paths is not None and eff in _OPEN_EFF:
                paths[ref] = sp
            by.setdefault(ev, []).append({"open": ref if eff in _OPEN_EFF else "", "scope": it["scope"], "src": _src(it), "matcher": m[:HN_CMD_MAX], "cmd": name,
                                          "timeout": to if isinstance(to, (int, float)) and not isinstance(to, bool) else None,
                                          "eff": eff, "desc": desc, "n": n, "last": last, "quiet": quiet, "plug": pn[:HN_CMD_MAX],
                                          "miss": int(bool(sp) and os.path.isabs(sp) and not os.path.exists(sp)),
                                          "ch": _dup_key(h, c),
                                          "nomatch": _nomatch(ev, m, tools)})
    order = list(EVENTS) + sorted(e for e in by if e not in EVENTS)
    return [{"ev": e, "hooks": by.get(e, [])} for e in order if e in EVENTS or by.get(e)]


def _rule_list(proj):
    root = ctxsrc._git_root(proj) or ""
    rows = [(r["path"], r["bytes"]) for r in ctxsrc._instr_files(proj, root)]
    mem = ctxsrc._memory(proj, root)
    if mem["index"]:
        rows.append((mem["index"], mem["bytes"]))
    return rows


def _rule_rows(proj):
    return [{"path": toolinv._abbrev(p), "size": n, "order": i + 1, "open": "r:%d" % i} for i, (p, n) in enumerate(_rule_list(proj))]


def _agent_path(proj, name):
    """File of agent `name` (frontmatter name may differ from the file name) — same order as pipeline._agents."""
    for n, _scope, p in _agent_files(proj):
        if n == name:
            return p
    return ""


def _stage_refs(body, key, default=""):
    """{name: [{pipe, stage}]} of pipeline stages naming `key` (agent / skill); empty names skipped."""
    refs = {}
    for row in body.get("pipelines") or []:
        for s in row.get("stages") or []:
            nm = s.get(key) or default
            if nm:
                refs.setdefault(nm, []).append({"pipe": row.get("name", ""), "stage": s.get("title", "")})
    return refs


def _agent_rows(proj, uses, pipes):
    out, seen = [], set()
    for a in _agents(proj):
        seen.add(a["name"])
        out.append({"name": a["name"], "scope": a["scope"], "open": "a:" + a["name"], "pipes": pipes.get(a["name"], []),
                    "n": int((uses.get("agent:" + a["name"]) or {}).get("n") or 0)})
    for nm in sorted(x for x in pipes if x not in seen):   # used by a stage but no file (runs as general-purpose)
        out.append({"name": nm, "scope": "", "open": "", "pipes": pipes[nm], "n": int((uses.get("agent:" + nm) or {}).get("n") or 0)})
    return out


def _plug_name(root):
    """Plugin name from its install dir (cache/<market>/<plugin>/<version>/ → <plugin>)."""
    pn = os.path.basename(root.rstrip(os.sep)) if root else ""
    if re.match(r"^\d", pn):
        pn = os.path.basename(os.path.dirname(root.rstrip(os.sep)))
    return pn[:HN_CMD_MAX]


def _use(uses, keys):
    n = last = 0
    for k in keys:
        v = uses.get(k) or {}
        n += int(v.get("n") or 0)
        last = max(last, int(v.get("last") or 0))
    return n, last


def _transport(e):
    t = e.get("type") if isinstance(e, dict) else None
    if t in ("stdio", "http", "sse"):
        return t
    return "stdio" if isinstance(e, dict) and isinstance(e.get("command"), str) else ""


def _sorted_rows(rows):
    return sorted(rows, key=lambda r: (not r["on"], -r["n"], r["name"].lower()))


def _health(st, keys):
    """('ok'|'fail'|'none', errorCode, last failure epoch, last ok epoch) merged over a server's key forms."""
    hs = [st[k] for k in keys if k in st]
    if not hs:
        return "none", "", 0, 0
    f = max(hs, key=lambda h: h.get("fail_at") or 0)
    ok_at = max(int(h.get("ok_at") or 0) for h in hs)
    return ("fail" if any(h.get("status") == "fail" for h in hs) else "ok"), f.get("err") or "", int(f.get("fail_at") or 0), ok_at


def _mcp_rows(items, uses, st=None):
    """⚠Name · scope · transport · status code only: env/headers/args/url and failure text never leave this function."""
    rows = []
    for it in items:
        nm = str(it["name"])[:TI_NAME]
        plug = _plug_name(os.path.dirname(it["file"])) if it["scope"] == "plugin" else ""
        keys = ["mcp:" + nm] + (["mcp:plugin_%s_%s" % (plug, nm)] if plug else [])   # plugin tools: mcp__plugin_<p>_<s>__<t>
        n, last = _use(uses, keys)
        status, err, fail_at, ok_at = _health(st or {}, keys + ["mcp:" + re.sub(r"[^A-Za-z0-9_-]", "_", nm)])
        rows.append({"name": nm, "scope": it["scope"], "plug": plug, "transport": _transport(it.get("entry")),
                     "on": bool(it["on"]), "n": n, "last": last, "status": status, "err": err, "fail_at": fail_at, "ok_at": ok_at})
    return sorted(_sorted_rows(rows), key=lambda r: r["status"] != "fail")   # stable: failed servers first


def _skill_list(proj):
    return [it for it in toolinv._raw_items() if it["kind"] == "skill" and (it["scope"] != "project" or it["proj"] == proj)]


def _file_roots(proj):
    return [os.path.realpath(x) for x in (ctxsrc.CLAUDE_DIR, DATA_DIR, proj, ctxsrc._git_root(proj)) if x]


def _openable(p, proj):
    return bool(p) and os.path.isfile(p) and _under(p, _file_roots(proj)) and not os.path.realpath(p).endswith(".jsonl")


def _skill_rows(items, proj, uses, refs):
    rows = []
    for i, it in enumerate(items):
        n, last = _use(uses, [it["ukey"]])
        nm = str(it["name"])[:TI_NAME]
        rows.append({"name": nm, "scope": it["scope"],
                     "plug": _plug_name(it.get("base", "")) if it["scope"] == "plugin" else "",
                     "on": bool(it["on"]), "n": n, "last": last, "pipes": refs.get(nm, []),
                     "open": "s:%d" % i if _openable(it["path"], proj) else ""})   # ⚠opaque index, path re-derived on click
    seen = set(r["name"] for r in rows)
    for nm in sorted(x for x in refs if x not in seen):   # named by a stage but not installed
        n, last = _use(uses, ["skill:" + nm])
        rows.append({"name": nm, "scope": "", "plug": "", "on": True, "n": n, "last": last, "pipes": refs[nm], "open": ""})
    return _sorted_rows(rows)


def harness(proj, days=30):
    """(code, body) for GET /api/harness?proj=&days=. Same project allow-list as the pipeline routes."""
    if not _proj_ok(proj):
        return 400, {"ok": False, "msg": "unknown project"}
    try:
        days = max(1, min(90, int(days or 30)))
    except (TypeError, ValueError):
        return 400, {"ok": False, "msg": "bad days"}
    uses = tool_uses(days)
    items = [it for it in toolinv._raw_items() if it["scope"] != "project" or it["proj"] == proj]
    counts = {k: sum(1 for it in items if it["kind"] == k and it["on"]) for k in ("skill", "cmd", "mcp")}
    code, body = pipelines(proj)
    body = body if code == 200 else {}
    return 200, {"ok": True, "proj": proj, "days": days,
                 "events": _hook_rows([it for it in items if it["kind"] == "hook"], proj, uses),
                 "rules": _rule_rows(proj), "agents": _agent_rows(proj, uses, _stage_refs(body, "agent", "general-purpose")), "counts": counts,
                 "mcps": _mcp_rows([it for it in items if it["kind"] == "mcp"], uses, mcp_status(days)),
                 "skills": _skill_rows([it for it in items if it["kind"] == "skill"], proj, uses, _stage_refs(body, "skill")), "scanning": scanning()}


def _ref_path(proj, ref):
    """(path, max bytes) for an `open` ref, re-derived from config; ("", 0) when it names nothing openable."""
    kind, _, rest = ref.partition(":")
    if kind == "h":
        paths = {}
        items = [it for it in toolinv._raw_items() if it["kind"] == "hook" and (it["scope"] != "project" or it["proj"] == proj)]
        _hook_rows(items, proj, {}, paths)
        p = paths.get(ref, "")
        roots = [os.path.realpath(x) for x in (ctxsrc.CLAUDE_DIR, DATA_DIR, proj) if x]
        return (p, HN_SCRIPT_MAX) if p and _under(p, roots) else ("", 0)   # ⚠same roots as _scan
    if kind == "r" and rest.isdigit():
        rows = _rule_list(proj)
        i = int(rest)
        return (rows[i][0], HN_FILE_MAX) if i < len(rows) else ("", 0)
    if kind == "a" and rest:
        p = _agent_path(proj, rest)
        return (p, HN_FILE_MAX) if p else ("", 0)
    if kind == "s" and rest.isdigit():
        sk = _skill_list(proj)
        i = int(rest)
        return (sk[i]["path"], HN_FILE_MAX) if i < len(sk) else ("", 0)
    return "", 0


def harness_file(proj, ref):
    """(code, body) for GET /api/harness/file?proj=&ref= — {ok, name, text, lang} of one openable card."""
    if not _proj_ok(proj):
        return 400, {"ok": False, "msg": "unknown project"}
    if not isinstance(ref, str) or not re.fullmatch(r"(h:[A-Za-z0-9_]{1,60}:\d{1,4}|r:\d{1,4}|a:[A-Za-z0-9._-]{1,80}|s:\d{1,4})", ref):
        return 400, {"ok": False, "msg": "bad ref"}
    p, cap = _ref_path(proj, ref)
    # ⚠A symlinked rule/agent file may point anywhere; transcripts (.jsonl) are never served whatever names them.
    roots = _file_roots(proj)
    if p and (not _under(p, roots) or os.path.realpath(p).endswith(".jsonl")):
        p = ""
    if not p or not os.path.isfile(p):
        return 404, {"ok": False, "msg": "No file to open."}
    try:
        if os.path.getsize(p) > cap:
            return 413, {"ok": False, "msg": "The file is too large."}
        with open(p, "rb") as f:
            raw = f.read(cap + 1)
    except OSError:
        return 404, {"ok": False, "msg": "File not found."}
    if len(raw) > cap:
        return 413, {"ok": False, "msg": "The file is too large."}
    if raw.startswith(_BIN_MAGIC) or b"\0" in raw[:4096]:
        return 415, {"ok": False, "msg": "Not a text file."}
    text = raw.decode("utf-8", "replace")
    if ref.startswith("h:"):   # ⚠hook scripts often embed tokens; same redact the tools tab applies to hook commands
        text = redact(text)
    return 200, {"ok": True, "name": os.path.basename(p), "path": toolinv._abbrev(p), "text": text,
                 "lang": _LANG.get(os.path.splitext(p)[1].lower(), "")}
