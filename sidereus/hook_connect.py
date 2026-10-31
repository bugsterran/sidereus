"""«Connect» Sidereus hooks into other CLIs: Cursor ~/.cursor/hooks.json, Codex <CODEX_HOME>/hooks.json, Gemini settings.json,
Copilot <COPILOT_HOME>/hooks/sidereus.json (a Sidereus-owned file; Copilot loads every *.json in that folder).

GET lists installed CLIs and whether every template entry is present (names, states, paths only).
POST previews a diff (dry) or writes after confirm: only the `hooks` / `hooksConfig` members are spliced,
the user's own entries are kept in order, a backup is taken first, and a changed file (sha) is never clobbered.
"""
import difflib
import hashlib
import json
import os
import re
import shutil
import sys
import threading
import time

from sidereus import config, ident, plat_codex, plat_gemini
from sidereus.cc_settings import _members

TRASH_DIR = None            # None = DATA_DIR/tool-trash; ⚠tests set a tmp dir
HC_FILES = None             # None = live paths; ⚠tests set {plat: tmp path} (never the real ~/.cursor, ~/.codex, ~/.gemini)
TPL_DIR = None              # None = ASSET_DIR/ext-hooks
MEMO_S = 30
SYMLINK = "symlink — edit it by hand"
_LOCK = threading.Lock()
_MEMO = {}

PLATS = (("cursor", "Cursor"), ("codex", "Codex"), ("gemini", "Gemini"), ("copilot", "Copilot"))
FLAT = ("cursor", "copilot")    # hooks.<event> is a list of entries, not of matcher groups
OURS = ("ext_hook.py", "pl_mark.py", "pl_flow.py", "gemini_mail_stop.py", "invite_notice.py", "pipelines_brief.py")
_TPL = {"cursor": "cursor-hooks-example.json", "codex": "codex-hooks-example.json", "gemini": "gemini-settings-example.json",
        "copilot": "copilot-hooks-example.json"}
_KEY_RE = re.compile(r"""(?:^|[/\s"'])(%s)["']?(?=\s|$)(.*)$""" % "|".join(re.escape(x) for x in OURS))
_STR_RE = re.compile(r'"(?:[^"\\]|\\.)*"(\s*:)?')


def _now():
    return time.time()


def _strftime(fmt):
    return time.strftime(fmt)


def _which(name):
    # Same lookup as sec_tools._which: launchd's PATH is short, rich_env() adds Homebrew/user bin dirs.
    return shutil.which(name, path=ident.rich_env().get("PATH", ""))


def _home():
    return ident._real_home()       # ⚠not $HOME / config.HOME: the viewer runs with HOME = its data dir


def _asset():
    return config.ASSET_DIR


def _python():
    # macOS: the stock /usr/bin python3 (stable across xcode-select, what launchd runs); elsewhere this interpreter.
    mac = shutil.which("python3", path="/usr/bin") if config.IS_MAC else None
    return mac or sys.executable


def _trash_dir():
    return TRASH_DIR or os.path.join(config.DATA_DIR, "tool-trash")


def _files():
    if HC_FILES:
        return HC_FILES
    return {"cursor": os.path.join(_home(), ".cursor", "hooks.json"),
            "codex": os.path.join(plat_codex.root(), "hooks.json"),
            "gemini": plat_gemini.hook_settings(),
            "copilot": os.path.join(_copilot_home(), "hooks", "sidereus.json")}


def _copilot_home():
    v = os.environ.get("COPILOT_HOME") or ""
    return v if os.path.isabs(v) else os.path.join(_home(), ".copilot")     # ⚠a relative value would resolve against the viewer's cwd


def _linked(p):
    # ⚠a symlinked parent (e.g. a created ~/.copilot/hooks pointing elsewhere) would be followed by the write too
    return os.path.islink(p) or os.path.islink(os.path.dirname(p))


def _installed(plat, path):
    d = os.path.dirname(path)
    if plat == "cursor":    # ⚠a bare `agent` is too generic a name: count it only next to ~/.cursor
        return bool(_which("cursor-agent") or (_which("agent") and os.path.isdir(d)))
    if plat == "copilot":   # ⚠the hooks/ folder does not exist by default: look at the Copilot home above it
        return bool(_which("copilot") or os.path.isdir(os.path.dirname(d)))
    return bool(_which(plat) or os.path.isdir(d))


def _shown(p):
    h = _home()
    return "~" + p[len(h):] if h and p.startswith(h + os.sep) else p


def _key(cmd):
    """Our hook entry -> (script name, args) or None. Matches by script basename so another python path still counts."""
    if not isinstance(cmd, str):
        return None
    m = _KEY_RE.search(cmd.replace("\\", "/"))
    if not m:
        return None
    args = m.group(2).split()
    if m.group(1) == "gemini_mail_stop.py":     # ⚠--wake / --wait (opt-in) and the plain entry are one: adding the other would run both
        args = [" ".join(args[i:i + 2]) for i, a in enumerate(args) if a == "--platform"]
    return m.group(1), " ".join(args)


def _cmd(e):
    """Command string of one hook entry: Copilot entries carry `bash` / `powershell` instead of `command`."""
    return e.get("command") or e.get("bash") or e.get("powershell")


def _q(s):
    return '"%s"' % s if " " in s else s


def _subst(cmd):
    """<PYTHON> / <MAILBOX_CODE_DIR>/rel -> real paths, each quoted when it holds a space."""
    asset = _asset()
    sep = "\\" if "\\" in asset else "/"

    def code(m):
        rel = m.group(1).lstrip("/")
        return _q(asset.rstrip("/\\") + (sep + rel.replace("/", sep) if rel else ""))
    cmd = re.sub(r"<MAILBOX_CODE_DIR>(\S*)", code, cmd)
    return cmd.replace("<PYTHON>", _q(_python()))


def _template(plat):
    """Template `hooks` with placeholders substituted, or None (template missing or unreadable)."""
    p = os.path.join(TPL_DIR or os.path.join(_asset(), "ext-hooks"), _TPL[plat])
    try:
        with open(p, "rb") as f:
            d = json.loads(f.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
    hooks = d.get("hooks") if isinstance(d, dict) else None
    if not isinstance(hooks, dict):
        return None

    def fix(e):
        e = dict(e)
        for k in ("command", "bash", "powershell"):
            if isinstance(e.get(k), str):
                e[k] = _subst(e[k])
        return e
    out = {}
    for ev, lst in hooks.items():
        if plat in FLAT:
            out[ev] = [fix(e) for e in lst]
        else:
            out[ev] = [dict(g, hooks=[fix(e) for e in g.get("hooks", [])]) for g in lst]
    return out


def _read(p):
    """(raw bytes or None, dict or None, error or None). Missing file = (None, None, None)."""
    try:
        with open(p, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return None, None, None
    except OSError as e:
        return None, None, "unreadable (%s)" % type(e).__name__
    try:
        d = json.loads(raw.decode("utf-8-sig"))
    except ValueError:
        return raw, None, "not valid JSON — fix it by hand"
    if not isinstance(d, dict):
        return raw, None, "top level is not an object — fix it by hand"
    if "hooks" in d and not isinstance(d["hooks"], dict):
        return raw, None, "`hooks` is not an object — fix it by hand"
    return raw, d, None


def _merge(plat, cur, tpl):
    """-> (new hooks dict, number of entries added) or raises ValueError. Never edits an existing entry or group."""
    new, adds = dict(cur), 0
    for ev, tl in tpl.items():
        have = cur.get(ev, [])
        if not isinstance(have, list):
            raise ValueError("hooks.%s is not a list — fix it by hand" % ev)
        lst = list(have)
        if plat in FLAT:
            keys = {_key(_cmd(e)) for e in have if isinstance(e, dict)}
            for e in tl:
                if _key(_cmd(e)) not in keys:
                    lst.append(e)
                    adds += 1
        else:
            for g in tl:
                m = g.get("matcher")
                keys = set()
                for hg in have:
                    # ⚠Codex trusts per event:group:entry, so presence is event-wide; Gemini also matches the matcher
                    if not isinstance(hg, dict) or (plat == "gemini" and hg.get("matcher") != m):
                        continue
                    for e in hg.get("hooks") or []:
                        if isinstance(e, dict):
                            keys.add(_key(_cmd(e)))
                miss = [e for e in g["hooks"] if _key(_cmd(e)) not in keys]
                if miss:
                    ng = {"matcher": m} if "matcher" in g else {}
                    ng["hooks"] = miss
                    lst.append(ng)
                    adds += len(miss)
        if lst != have or ev not in cur:
            new[ev] = lst
    return new, adds


def _ind(text, ks):
    nl = text.rfind("\n", 0, ks)
    seg = text[nl + 1:ks]
    return seg if nl >= 0 and not seg.strip() else ""


def _enc(val, ind, nl="\n"):
    unit = "\t" if "\t" in ind else ("  " if not ind else (" " * len(ind) if len(ind) <= 4 else "  "))
    return json.dumps(val, indent=unit, ensure_ascii=False).replace("\n", nl + ind)


def _splice(text, sets):
    """text with each top-level key in `sets` replaced (or appended) -> (new text, [(key start, value end)] in new) or None."""
    # ⚠Windows editors write CRLF; a hard-coded "\n" here left mixed line endings after a write.
    nl = "\r\n" if "\r\n" in text else "\n"
    for k, v in sets:
        m = _members(text)
        if m is None:
            return None
        brace, mem = m
        hits = [x for x in mem if x[0] == k]
        if len(hits) > 1:
            return None
        if hits:
            _k, ks, _ke, vs, ve = hits[0]
            text = text[:vs] + _enc(v, _ind(text, ks), nl) + text[ve:]
        elif not mem:
            close = text.rfind("}")
            text = text[:brace + 1] + nl + "  " + json.dumps(k) + ": " + _enc(v, "  ", nl) + nl + text[close:].lstrip(" \t\r\n")
        else:
            _k, ks, ke, vs, ve = mem[-1]
            seg = text[(mem[-2][4] if len(mem) > 1 else brace):ks]
            lead = seg[max(seg.rfind(","), seg.rfind("{")) + 1:]
            ind = lead[lead.rfind("\n") + 1:] if "\n" in lead else ""
            text = text[:ve] + "," + lead + json.dumps(k) + text[ke:vs] + _enc(v, ind, nl) + text[ve:]
    m = _members(text)
    if m is None:
        return None
    spans = [(x[1], x[4]) for x in m[1] if x[0] in dict(sets)]
    return text, spans


def _lines_of(text, spans):
    out = set()
    for a, b in spans:
        out.update(range(text.count("\n", 0, a), text.count("\n", 0, b) + 1))
    return out


def _mask(line, ours):
    # ⚠Lines outside hooks/hooksConfig may hold secrets (Gemini mcpServers env): string values are masked there.
    return line if ours else _STR_RE.sub(lambda m: m.group(0) if m.group(1) else '"…"', line)


def _diff(old, new, shown, ospan, nspan):
    a, b = old.splitlines(), new.splitlines()
    out = ["--- " + shown, "+++ " + shown]
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for grp in sm.get_grouped_opcodes(3):
        i1, i2, j1, j2 = grp[0][1], grp[-1][2], grp[0][3], grp[-1][4]
        out.append("@@ -%d,%d +%d,%d @@" % (i1 + 1, i2 - i1, j1 + 1, j2 - j1))
        for tag, x1, x2, y1, y2 in grp:
            if tag == "equal":
                out += [" " + _mask(a[i], i in ospan) for i in range(x1, x2)]
                continue
            if tag in ("replace", "delete"):
                out += ["-" + _mask(a[i], i in ospan) for i in range(x1, x2)]
            if tag in ("replace", "insert"):
                out += ["+" + _mask(b[j], j in nspan) for j in range(y1, y2)]
    return "\n".join(out) + "\n"


def _sha(raw):
    return hashlib.sha256(raw).hexdigest() if raw is not None else ""


def _plan(plat, p):
    """-> dict(raw, new_raw, adds, diff, err); err = (code, message) or None. Writes nothing."""
    if _linked(p):
        return {"err": (400, SYMLINK)}      # ⚠os.replace would turn a dotfiles link into a regular file
    tpl = _template(plat)
    if tpl is None:
        return {"err": (400, "no ext-hooks")}
    raw, d, err = _read(p)
    if err:
        return {"raw": raw, "err": (400, err)}
    if raw is None:
        if plat == "gemini":     # ⚠settings.json is Gemini CLI's own file: never created here
            return {"raw": None, "err": (400, "settings.json not found — run gemini once")}
        d = {"version": 1} if plat in FLAT else {}
        bom, text = b"", "{}\n"
    else:
        bom = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""
        text = raw[len(bom):].decode("utf-8")
    try:
        hooks, adds = _merge(plat, d.get("hooks") or {}, tpl)
    except ValueError as e:
        return {"raw": raw, "err": (400, str(e))}
    sets = []
    if raw is None and plat in FLAT:
        sets.append(("version", 1))
    want = dict(d)
    if plat == "gemini":
        hc = d.get("hooksConfig", {})
        if not isinstance(hc, dict):
            return {"raw": raw, "err": (400, "`hooksConfig` is not an object — fix it by hand")}
        if hc.get("enabled") is not True:
            hc = dict(hc, enabled=True)
            sets.append(("hooksConfig", hc))
            want["hooksConfig"] = hc
            adds += 1
    if not adds:
        return {"raw": raw, "new_raw": raw, "adds": 0, "diff": "", "err": None}
    sets.append(("hooks", hooks))
    want["hooks"] = hooks
    sp = _splice(text, sets)
    if sp is None:
        return {"raw": raw, "err": (400, "file layout can't be edited safely (duplicate key?) — change it by hand")}
    new, nsp = sp
    if not _check(plat, d if raw is not None else {}, new, want, tpl):
        return {"raw": raw, "err": (500, "refused: other entries would change")}
    om = _members(text) if raw is not None else None
    osp = [(x[1], x[4]) for x in om[1] if x[0] in dict(sets)] if om else []
    diff = _diff(text if raw is not None else "", new, _shown(p),
                 _lines_of(text, osp), _lines_of(new, nsp))
    return {"raw": raw, "new_raw": bom + new.encode("utf-8"), "adds": adds, "diff": diff, "err": None}


def _check(plat, old, new_text, want, tpl):
    """Re-parse: other keys/order equal, every original entry still first and in order, nothing left to add."""
    try:
        chk = json.loads(new_text)
    except ValueError:
        return False
    if chk != want:
        return False
    if [k for k in chk if k in old] != list(old):
        return False
    oh, nh = old.get("hooks") or {}, chk.get("hooks") or {}
    if [k for k in nh if k in oh] != list(oh):
        return False
    for ev, lst in oh.items():
        if nh.get(ev, [])[:len(lst)] != lst:
            return False
    try:
        return _merge(plat, nh, tpl)[1] == 0
    except ValueError:
        return False


def _state(plat, p):
    raw, d, err = _read(p)
    if err:
        return "unreadable", err
    if raw is None:
        return "missing", ""
    tpl = _template(plat)
    if tpl is None:     # no template to compare with: any of our entries counts as connected
        txt = json.dumps(d.get("hooks") or {})
        return ("connected" if "ext_hook.py" in txt else "partial"), ""
    try:
        _h, adds = _merge(plat, d.get("hooks") or {}, tpl)
    except ValueError as e:
        return "unreadable", str(e)
    if plat == "gemini" and (d.get("hooksConfig") or {}).get("enabled") is not True:
        adds += 1
    return ("connected" if not adds else "partial"), ""


def _stamp(files):
    out = []
    for plat, _n in PLATS:
        p = files[plat]
        try:
            out.append((p, os.stat(p).st_mtime_ns))
        except OSError:
            out.append((p, None))
    return tuple(out)


def listing():
    """GET /api/hooks/connect body: [{plat, name, state, file, can, why, approve}] for installed CLIs only."""
    files = _files()
    st = _stamp(files)
    hit = _MEMO.get("list")
    if hit and hit[1] == st and _now() - hit[0] < MEMO_S:
        return hit[2]
    out = []
    for plat, name in PLATS:
        p = files[plat]
        if not _installed(plat, p):
            continue
        state, why = _state(plat, p)
        can = state in ("missing", "partial")
        if can and _linked(p):
            can, why = False, SYMLINK
        elif can and _template(plat) is None:
            can, why = False, "no ext-hooks"
        elif can and state == "missing" and plat == "gemini":
            can, why = False, "settings.json not found — run gemini once"
        out.append({"plat": plat, "name": name, "state": state, "file": _shown(p), "can": can, "why": why,
                    "approve": "/hooks" if plat == "codex" else ""})
    _MEMO["list"] = (_now(), st, out)
    return out


def _backup(p, plat):
    base = os.path.join(_trash_dir(), _strftime("%Y%m%d-%H%M%S"))
    d, n = base, 1
    while os.path.exists(d):
        n += 1
        d = "%s-%d" % (base, n)
    os.makedirs(d)
    dst = os.path.join(d, "%s-%s" % (plat, os.path.basename(p)))
    shutil.copy2(p, dst)
    return dst


def _write(plat, p, raw, new_raw):
    """Backup, tmp + fsync, re-compare, os.replace -> (200, backup or None) or (code, error body). Caller holds _LOCK."""
    tmp = "%s.sidereus-tmp.%d" % (p, os.getpid())
    try:
        bak = _backup(p, plat) if raw is not None else None
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if _linked(p):
            return 400, {"ok": False, "err": SYMLINK}
        with open(tmp, "wb") as f:
            f.write(new_raw)
            f.flush()
            os.fsync(f.fileno())
        try:
            try:
                with open(p, "rb") as f:
                    now = f.read()
            except FileNotFoundError:
                now = None
            if now != raw:      # ⚠the CLI (or an editor) rewrote the file since our read — never clobber that
                return 409, {"ok": False, "err": "file changed while writing — try again"}
            if raw is not None:
                shutil.copymode(p, tmp)
            os.replace(tmp, p)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    except OSError as e:
        return 500, {"ok": False, "err": "write failed (%s)" % type(e).__name__}
    return 200, bak


def connect(req):
    """POST /api/hooks/connect {plat, dry:true} -> {ok, diff, base, adds}; {plat, dry:false, base} -> {ok, changed, approve?}."""
    if not isinstance(req, dict) or req.get("plat") not in _TPL:
        return 400, {"ok": False, "err": "unknown plat"}
    plat = req["plat"]
    p = _files()[plat]
    with _LOCK:
        pl = _plan(plat, p)
        if pl["err"]:
            return pl["err"][0], {"ok": False, "err": pl["err"][1]}
        if req.get("dry") is not False:
            return 200, {"ok": True, "diff": pl["diff"], "base": _sha(pl["raw"]), "adds": pl["adds"]}
        if not isinstance(req.get("base"), str) or req["base"] != _sha(pl["raw"]):
            return 409, {"ok": False, "err": "file changed since the preview — open it again"}
        if not pl["adds"]:
            return 200, {"ok": True, "changed": False}
        code, bak = _write(plat, p, pl["raw"], pl["new_raw"])
        if code != 200:
            return code, bak
        _MEMO.clear()
    out = {"ok": True, "changed": True, "backup": bak}
    if plat == "codex":
        out["approve"] = "/hooks"     # Codex skips edited hooks until they are approved again in its TUI
    return 200, out
