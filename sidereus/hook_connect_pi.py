"""«Connect» Sidereus into pi: `<agent dir>/mcp.json` (only missing `mcpServers` entries appended) and
`<agent dir>/extensions/sidereus.ts` (a Sidereus-owned file rendered from ext-hooks/pi-extension.ts).

Same guards as hook_connect: viewer Origin (route) · diff preview, then a sha-checked write · backup to tool-trash first ·
a symlinked file or extensions folder is refused · the user's servers and every other top-level key stay as they were.
"""
import hashlib
import json
import os

from sidereus import config, hook_connect as hc, plat_pi
from sidereus.cc_settings import _members

PI_FILES = None     # None = live paths; ⚠tests set {"mcp": tmp, "ts": tmp} (never the real ~/.pi)
TPL = None          # None = ASSET_DIR/ext-hooks/pi-extension.ts
PLAT = "pi"


def _files():
    if PI_FILES:
        return PI_FILES
    r = plat_pi.root()      # honours PI_CODING_AGENT_DIR; ⚠never config.HOME (the viewer's data dir)
    return {"mcp": os.path.join(r, "mcp.json"), "ts": os.path.join(r, "extensions", "sidereus.ts")}


def _win():
    return bool(config.IS_WIN)   # ⚠config only: tests patch it to plan either OS on any runner


def _fold(name):
    # ⚠`side_reus` / `Side-Reus` is the same server to a person: adding a second copy would start two.
    return name.replace("-", "").replace("_", "").lower() if isinstance(name, str) else name


def _servers():
    """[(name, entry)] Sidereus wants in mcpServers; mailbox runs a sh launcher, so not on Windows."""
    a = hc._asset()
    out = [("sidereus", {"command": hc._python(), "args": [os.path.join(a, "mcp", "sidereus_mcp.py")]})]
    if not _win():
        out.append(("mailbox", {"command": os.path.join(a, "ext-hooks", "gemini_mailbox_mcp.sh"), "args": [PLAT]}))
    return out


def _missing(ms):
    have = {_fold(k) for k in ms}
    return [(k, v) for k, v in _servers() if _fold(k) not in have]


def _render():
    """Rendered extension bytes, or None (template missing or unreadable)."""
    p = TPL or os.path.join(hc._asset(), "ext-hooks", "pi-extension.ts")
    try:
        with open(p, "rb") as f:
            t = f.read().decode("utf-8")
    except (OSError, ValueError):
        return None
    py = hc._python()
    if not (isinstance(py, str) and os.path.isabs(py)):
        return None   # ⚠the extension spawns PY with no shell: only one absolute executable path works
    # ⚠json.dumps, not hc._q: a path with a quote or backslash must stay one valid TS string literal
    t = t.replace('"<PYTHON>"', json.dumps(py)).replace('"<MAILBOX_CODE_DIR>"', json.dumps(hc._asset()))
    return t.encode("utf-8")


def _read_raw(p):
    try:
        with open(p, "rb") as f:
            return f.read(), None
    except FileNotFoundError:
        return None, None
    except OSError as e:
        return None, hc._Err("unreadable ({e})", e=type(e).__name__)


def _read_mcp(p):
    """(raw or None, dict or None, error or None)."""
    raw, err = _read_raw(p)
    if err or raw is None:
        return raw, None, err
    try:
        d = json.loads(raw.decode("utf-8-sig"))
    except ValueError:
        return raw, None, "not valid JSON — fix it by hand"
    if not isinstance(d, dict):
        return raw, None, "top level is not an object — fix it by hand"
    if "mcpServers" in d and not isinstance(d["mcpServers"], dict):
        return raw, None, "`mcpServers` is not an object — fix it by hand"
    return raw, d, None


def _linked(fs):
    return os.path.islink(fs["mcp"]) or os.path.islink(fs["ts"]) or os.path.islink(os.path.dirname(fs["ts"]))


def _spans(text, keys):
    """(start, end) of each top-level member in `keys` -> {key: (ks, ve)}."""
    m = _members(text)
    return {x[0]: (x[1], x[4]) for x in (m[1] if m else []) if x[0] in keys}


def _check(text, new, old, adds):
    """Re-parse: other top-level keys byte-identical, old servers equal and first, nothing left to add."""
    try:
        chk = json.loads(new)
    except ValueError:
        return False
    om, nm = _members(text), _members(new)
    if om is None or nm is None or not isinstance(chk, dict):
        return False
    oth = [text[x[1]:x[4]] for x in om[1] if x[0] != "mcpServers"]
    if [new[x[1]:x[4]] for x in nm[1] if x[0] != "mcpServers"] != oth:
        return False
    ms, oms = chk.get("mcpServers"), old.get("mcpServers") or {}
    if not isinstance(ms, dict) or list(ms.items())[:len(oms)] != list(oms.items()):
        return False
    return len(ms) == len(oms) + adds and not _missing(ms)


def _plan_mcp(p):
    """-> dict(raw, new_raw, adds, diff, err)."""
    raw, d, err = _read_mcp(p)
    if err:
        return {"raw": raw, "err": (400, err)}
    if raw is None:
        d, bom, text = {}, b"", "{}\n"
    else:
        bom = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""
        text = raw[len(bom):].decode("utf-8")
    cur = d.get("mcpServers") or {}
    miss = _missing(cur)
    if not miss:
        return {"raw": raw, "new_raw": raw, "adds": 0, "diff": "", "err": None}
    ms = dict(cur)
    ms.update(miss)
    sp = hc._splice(text, [("mcpServers", ms)])
    if sp is None:
        return {"raw": raw, "err": (400, "file layout can't be edited safely (duplicate key?) — change it by hand")}
    new = sp[0]
    if not _check(text, new, d, len(miss)):
        return {"raw": raw, "err": (500, "refused: other entries would change")}
    # ⚠only our appended entries are shown unmasked: the user's servers may carry env secrets
    vs = _spans(new, ("mcpServers",)).get("mcpServers")
    nspan = set()
    if vs:
        val = new[vs[0]:vs[1]]
        off = vs[0] + val.index("{", val.index(":"))
        inner = _spans(new[off:vs[1]], {k for k, _v in miss})
        nspan = hc._lines_of(new, [(a + off, b + off) for a, b in inner.values()])
    diff = hc._diff(text if raw is not None else "", new, hc._shown(p), set(), nspan)
    return {"raw": raw, "new_raw": bom + new.encode("utf-8"), "adds": len(miss), "diff": diff, "err": None}


def _plan_ts(p, want):
    raw, err = _read_raw(p)
    if err:
        return {"raw": raw, "err": (400, err)}
    if raw == want:
        return {"raw": raw, "new_raw": raw, "adds": 0, "diff": "", "err": None}
    old = raw.decode("utf-8", "replace") if raw is not None else ""
    new = want.decode("utf-8")
    every = set(range(max(old.count("\n"), new.count("\n")) + 1))     # Sidereus-owned code: nothing to mask
    return {"raw": raw, "new_raw": want, "adds": 1, "diff": hc._diff(old, new, hc._shown(p), every, every), "err": None}


def _base(mraw, traw):
    return hashlib.sha256((mraw or b"") + b"\0" + (traw or b"")).hexdigest()


def _ts_state(p, want):
    raw, err = _read_raw(p)
    if err:
        return "unreadable"
    return "missing" if raw is None else ("sync" if want is not None and raw == want else "partial")


def row():
    """GET /api/hooks/connect rows for pi: [] when pi is not installed, else one hook_connect.listing()-shaped row."""
    fs = _files()
    if not (hc._which("pi") or os.path.isdir(os.path.dirname(fs["mcp"]))):
        return []
    want = _render()
    raw, d, err = _read_mcp(fs["mcp"])
    why = ""
    if err:
        state, why = "unreadable", err
    else:
        ms = (d or {}).get("mcpServers") or {}
        ts = _ts_state(fs["ts"], want)
        mine = len(_missing(ms)) < len(_servers())
        if ts == "unreadable":
            state = "unreadable"
        elif not _missing(ms) and ts == "sync":
            state = "connected"
        elif not mine and ts == "missing":
            state = "missing"
        else:
            state = "partial"
    can = state in ("missing", "partial")
    if can and _linked(fs):
        can, why = False, hc.SYMLINK
    elif can and want is None:
        can, why = False, "no ext-hooks"
    out = {"plat": PLAT, "name": plat_pi.NAME, "state": state, "file": hc._shown(fs["mcp"]), "can": can, "why": why,
           "approve": ""}
    if hc._ev(why):
        out["vars"] = hc._ev(why)
    return [out]


def connect(req):
    """POST /api/hooks/connect {plat:"pi", dry} -> same shapes as hook_connect.connect()."""
    if not isinstance(req, dict) or req.get("plat") != PLAT:
        return 400, {"ok": False, "err": "unknown plat"}
    fs = _files()
    with hc._LOCK:
        if _linked(fs):
            return 400, {"ok": False, "err": hc.SYMLINK}    # ⚠os.replace would turn a dotfiles link into a regular file
        want = _render()
        if want is None:
            return 400, {"ok": False, "err": "no ext-hooks"}
        pm, pt = _plan_mcp(fs["mcp"]), _plan_ts(fs["ts"], want)
        for pl in (pm, pt):
            if pl["err"]:
                out = {"ok": False, "err": pl["err"][1]}
                if hc._ev(pl["err"][1]):
                    out["vars"] = hc._ev(pl["err"][1])
                return pl["err"][0], out
        base = _base(pm["raw"], pt["raw"])
        if req.get("dry") is not False:
            return 200, {"ok": True, "diff": pm["diff"] + pt["diff"], "base": base, "adds": pm["adds"] + pt["adds"]}
        if not isinstance(req.get("base"), str) or req["base"] != base:
            return 409, {"ok": False, "err": "file changed since the preview — open it again"}
        if not pm["adds"] and not pt["adds"]:
            return 200, {"ok": True, "changed": False}
        baks = []
        for key, pl in (("mcp", pm), ("ts", pt)):
            if not pl["adds"]:
                continue
            code, bak = hc._write(PLAT, fs[key], pl["raw"], pl["new_raw"])
            if code != 200:
                return code, bak
            if bak:
                baks.append(bak)
        hc._MEMO.clear()
    return 200, {"ok": True, "changed": True, "backup": baks[0] if baks else None, "backups": baks}
