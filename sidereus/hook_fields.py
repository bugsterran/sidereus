"""Static check of a hook script's JSON output against the fields Claude Code reads for its event (docs/HOOKS.md).

`resolve(cmd, plugin_root, roots, home)` finds the script a hook command runs; `judge(path, event)` -> (verdict, unread).
Verdicts: ok · partial (some keys are read, some are not) · silent (JSON goes out, nothing in it is read, no exit-2 path)
· unknown (binary, unresolvable, outside the roots, or no JSON output found).
⚠Static estimate: the script is read (<= HF_SCRIPT_MAX bytes, only under the given roots) and never executed.
⚠Metadata only: only key names (charset-filtered) leave this module; values and script text never do.
"""
import os
import re
import shlex

HF_SCRIPT_MAX = 64 * 1024
HF_KEY_MAX = 64
HF_UNREAD_MAX = 12
HF_CACHE_MAX = 512
_HF_CACHE = {}               # (realpath, mtime_ns) -> facts
# Fields Claude Code reads from hook stdout JSON, per event (dotted = nested under hookSpecificOutput).
HF_COMMON = ("continue", "stopReason", "suppressOutput", "systemMessage")
HF_READ = {
    "PreToolUse": ("decision", "reason", "hookSpecificOutput.permissionDecision", "hookSpecificOutput.permissionDecisionReason",
                   "hookSpecificOutput.updatedInput", "hookSpecificOutput.additionalContext"),
    "PostToolUse": ("decision", "reason", "hookSpecificOutput.additionalContext", "hookSpecificOutput.updatedMCPToolOutput"),
    "UserPromptSubmit": ("decision", "reason", "hookSpecificOutput.additionalContext"),
    "Stop": ("decision", "reason"),
    "SubagentStop": ("decision", "reason"),
    "SessionStart": ("hookSpecificOutput.additionalContext",),
    "PermissionRequest": ("hookSpecificOutput.decision.behavior", "hookSpecificOutput.decision.updatedInput",
                          "hookSpecificOutput.decision.message", "hookSpecificOutput.decision.interrupt"),
}
HF_NOOP = ("continue", "suppressOutput")   # read, but change nothing for the model (continue only when true)
_WRAPPERS = ("run.cjs", "run.js", "run.mjs")   # plugin runners that take the real script as the next argument
_INTERP = re.compile(r"^(python[0-9.]*|node|bash|sh|zsh|deno|bun|ruby|perl|env|uv|uvx|npx)$")
_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_KEY_OK = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")
_RX_IDENT = re.compile(r"[A-Za-z_$][\w$]*")
# ⚠Only calls whose result goes to stdout count: JSON.stringify for a state file would read as an unread key.
_RX_EMIT = re.compile(r"(?:console\.log|process\.stdout\.write|print|sys\.stdout\.write)\s*\(\s*(?:JSON\.stringify|json\.dumps)\s*\(\s*")
_RX_DUMP = re.compile(r"json\.dump\s*\(\s*([A-Za-z_]\w*)\s*,\s*sys\.stdout")
_RX_EXIT2 = re.compile(r"(?:process\.exit|sys\.exit|exit)\s*\(\s*2\s*\)|^\s*exit\s+2\b", re.M)
_BIN_MAGIC = (b"\x7fELF", b"MZ", b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe")


def _argv(cmd):
    try:
        return shlex.split(cmd)
    except ValueError:
        return cmd.split()


def _expand(tok, plugin_root, home):
    rep = {"CLAUDE_PLUGIN_ROOT": plugin_root or "", "HOME": home or ""}
    t = re.sub(r"\$\{?([A-Z_]+)\}?", lambda m: rep.get(m.group(1)) or "\0", tok)
    if "\0" in t:
        return ""
    if t.startswith("~/") and home:
        t = home + t[1:]
    return t if os.path.isabs(t) else ""


def _under(p, roots):
    for r in roots:
        if not r:
            continue
        rr = os.path.realpath(r)
        if p == rr or p.startswith(rr.rstrip(os.sep) + os.sep):
            return True
    return False


def resolve(cmd, plugin_root, roots, home):
    """Realpath of the script `cmd` runs (through a run.cjs wrapper), or "" when unresolvable or outside `roots`."""
    toks = _argv(cmd if isinstance(cmd, str) else "")
    i = 0
    while i < len(toks) and _ENV_ASSIGN.match(toks[i]):
        i += 1
    while i < len(toks) and (_INTERP.match(os.path.basename(toks[i])) or toks[i].startswith("-")):
        i += 1
    if i >= len(toks):
        return ""
    t = _expand(toks[i], plugin_root, home)
    if t and os.path.basename(t) in _WRAPPERS and i + 1 < len(toks):
        t = _expand(toks[i + 1], plugin_root, home)
    if not t:
        return ""
    rp = os.path.realpath(t)
    return rp if _under(rp, roots) and os.path.isfile(rp) else ""


def _skip_str(s, i):
    q, i = s[i], i + 1
    while i < len(s) and s[i] != q:
        i += 2 if s[i] == "\\" else 1
    return i + 1


def _skip_val(s, i):
    """Index of the ',' or closing brace that ends the value starting at i."""
    depth = 0
    while i < len(s):
        c = s[i]
        if c in "\"'`":
            i = _skip_str(s, i)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                return i
            depth -= 1
        elif c == "," and depth == 0:
            return i
        i += 1
    return i


def _keys(s, i, pre, out):
    """Dotted keys of the object literal at s[i] == '{' -> index after its '}'. Values that are literals recurse."""
    i += 1
    while i < len(s):
        while i < len(s) and s[i] in " \t\r\n,":
            i += 1
        if i >= len(s) or s[i] == "}":
            return i + 1
        if s.startswith("...", i) or s.startswith("**", i):   # spread: contents unknown
            out.append((pre + "*", ""))
            i = _skip_val(s, i)
            continue
        if s[i] in "\"'":
            j = _skip_str(s, i)
            k = s[i + 1:j - 1]
        else:
            m = _RX_IDENT.match(s, i)
            if not m:
                return _skip_val(s, i) + 1
            k, j = m.group(0), m.end()
        while j < len(s) and s[j] in " \t\r\n":
            j += 1
        if j >= len(s) or s[j] != ":":   # JS shorthand `{ reason }`
            out.append((pre + k, ""))
            i = j
            continue
        j += 1
        while j < len(s) and s[j] in " \t\r\n":
            j += 1
        if j < len(s) and s[j] == "{":
            out.append((pre + k, "{"))
            i = _keys(s, j, pre + k + ".", out)
        else:
            e = _skip_val(s, j)
            out.append((pre + k, s[j:e].strip()[:8]))
            i = e
    return i


def _emits(src):
    """[[(dotted key, value head)] or None (opaque)] per stdout JSON emission."""
    res = []
    for m in _RX_EMIT.finditer(src):
        i = m.end()
        if src[i:i + 1] == "{":
            out = []
            _keys(src, i, "", out)
            res.append(out)
            continue
        v = re.match(r"([A-Za-z_]\w*)\s*[,)]", src[i:])
        res.append(_var_keys(src, v.group(1)) if v else None)
    for m in _RX_DUMP.finditer(src):
        res.append(_var_keys(src, m.group(1)))
    return res


def _var_keys(src, name):
    """Keys of `name = {...}` plus later `name.k =` / `name["k"] =`; None when no literal assignment is found."""
    m = re.search(r"\b" + re.escape(name) + r"\s*(?::\s*\w+\s*)?=\s*\{", src)
    if not m:
        return None
    out = []
    _keys(src, m.end() - 1, "", out)
    for a in re.finditer(r"\b" + re.escape(name) + r"""(?:\.([A-Za-z_]\w*)|\[\s*["']([A-Za-z_]\w*)["']\s*\])\s*=[^=]""", src):
        out.append((a.group(1) or a.group(2), ""))
    return out


def scan(path):
    """Facts of one script: {st: ok|bin|none|err, emits, exit2}; cached by (realpath, mtime)."""
    try:
        stt = os.stat(path)
    except OSError:
        return {"st": "err"}
    key = (path, stt.st_mtime_ns)
    hit = _HF_CACHE.get(key)
    if hit is not None:
        return hit
    try:
        with open(path, "rb") as f:
            raw = f.read(HF_SCRIPT_MAX)
    except OSError:
        return {"st": "err"}
    if raw.startswith(_BIN_MAGIC) or b"\0" in raw[:1024]:
        facts = {"st": "bin"}
    else:
        src = raw.decode("utf-8", "replace")
        em = _emits(src)
        facts = {"st": "ok" if em else "none", "emits": em, "exit2": bool(_RX_EXIT2.search(src))}
    if len(_HF_CACHE) >= HF_CACHE_MAX:
        _HF_CACHE.clear()
    _HF_CACHE[key] = facts
    return facts


def _is_read(k, read):
    if k in read:
        return True
    return any(r.startswith(k + ".") for r in read)   # a container whose children were not listed (opaque)


def judge(path, event):
    """(verdict, unread keys) for `path` run on `event`."""
    if not path or event not in HF_READ:
        return "unknown", []
    f = scan(path)
    if f.get("st") != "ok":
        return "unknown", []
    read = set(HF_COMMON) | set(HF_READ[event])
    if any(r.startswith("hookSpecificOutput.") for r in read):
        read.add("hookSpecificOutput.hookEventName")
    unread, eff = set(), False
    for em in f["emits"]:
        if em is None:
            eff = True      # opaque object: may carry read fields
            continue
        parents = {k.rsplit(".", 1)[0] for k, _v in em if "." in k}
        for k, v in em:
            if k.endswith("*"):
                eff = True
            elif v == "{" and k in parents:
                continue    # judged by its children
            elif _is_read(k, read):
                if k not in HF_NOOP and k != "hookSpecificOutput.hookEventName" or (k == "continue" and v.lower() != "true"):
                    eff = True
            elif len(k) <= HF_KEY_MAX and all(_KEY_OK.match(x) for x in k.split(".")):
                unread.add(k)
    un = sorted(unread)[:HF_UNREAD_MAX]
    if not un:
        return "ok", []
    if eff:
        return "partial", un
    return ("ok" if f["exit2"] else "silent"), un
