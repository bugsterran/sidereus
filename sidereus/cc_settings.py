"""«Preferences» Claude Code keys: autoCompactEnabled / autoCompactWindow in ~/.claude/settings.json.

Exactly these two keys, nothing else in that file, ever. A save writes every account's settings.json
(claude_roots.accounts(); primary is the reference, extras missing/invalid/symlinked are skipped, never created). Wraps prefs_get/prefs_set so GET /api/prefs and POST /api/prefs/set carry both kinds of keys.
One more: `env.OTEL_EXPORTER_OTLP_ENDPOINT`, only its port, only together with a
«Port» save, only while it is the local Sidereus URL form. The value is replaced in the raw bytes, so no other byte moves.
"""
import json
import os
import re
import shutil
import threading
import time

from sidereus import claude_roots, ctxsrc
from sidereus.config import DATA_DIR
from sidereus.prefs import compact_hist_append, prefs_get, prefs_set
from sidereus.features import check_toggles, listing as features_listing

SETTINGS_PATH = None        # None = ctxsrc.CLAUDE_DIR/settings.json at call time; ⚠tests set a tmp path (never the live file)
TRASH_DIR = None            # None = DATA_DIR/tool-trash; ⚠tests set a tmp dir
WIN_MIN, WIN_MAX = 50_000, 1_000_000
_LOCK = threading.Lock()


def _v_bool(v):
    if not isinstance(v, bool):
        raise ValueError("must be true or false")
    return v


def _v_win(v):
    if isinstance(v, bool) or not isinstance(v, int):
        raise ValueError("must be an integer")
    if not WIN_MIN <= v <= WIN_MAX:     # ⚠refused, not clamped: the page (mpCcSet) shows a refusal, a silent clamp stores a value nobody confirmed
        raise ValueError("must be between %d and %d" % (WIN_MIN, WIN_MAX))
    return v


# pref key -> (settings.json key, validator, default shown when the key is absent). ⚠The only writable keys of that file.
CC_KEYS = {
    "cc_auto_compact": ("autoCompactEnabled", _v_bool, True),
    "cc_compact_window": ("autoCompactWindow", _v_win, None),
}


def settings_path():
    return SETTINGS_PATH or os.path.join(ctxsrc.CLAUDE_DIR, "settings.json")


def _strftime(fmt):
    return time.strftime(fmt)            # tests patch this, not the time module


def _trash_dir():
    return TRASH_DIR or os.path.join(DATA_DIR, "tool-trash")


def _targets():
    """[{label, path, primary}] — settings_path() first, then each other account's settings.json (deduped by realpath)."""
    prim = settings_path()
    accs = claude_roots.accounts()
    plab = next((a["label"] for a in accs if a.get("primary")), "primary")
    out = [{"label": plab, "path": prim, "primary": True}]
    seen = {os.path.realpath(prim)}
    for a in accs:
        if a.get("primary"):
            continue
        p = os.path.join(a["dir"], "settings.json")
        rp = os.path.realpath(p)
        if rp in seen:          # ⚠a link to an already-listed file would be written twice
            continue
        seen.add(rp)
        out.append({"label": a["label"], "path": p, "primary": False})
    return out


def _read():
    return _read_at(settings_path())


def _read_at(p):
    """(raw bytes, dict, error). ⚠A missing, unparsable or non-object file is an error — never written."""
    try:
        with open(p, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return None, None, "settings.json not found"
    except OSError as e:
        return None, None, "settings.json unreadable (%s)" % type(e).__name__
    try:
        d = json.loads(raw.decode("utf-8-sig"))     # Windows editors write a BOM; Claude Code accepts it
    except ValueError as e:
        return raw, None, "settings.json is not valid JSON (%s) — fix it by hand" % type(e).__name__
    if not isinstance(d, dict):
        return raw, None, "settings.json top level is not an object — fix it by hand"
    return raw, d, None


def _same_others(a, b, key):
    """True when a and b hold the same other top-level keys, values and order."""
    ka, kb = [k for k in a if k != key], [k for k in b if k != key]
    return ka == kb and all(a[k] == b[k] for k in ka)


def cc_get():
    """{pref key: {value, default, src:"claude", path, apply:"new_session"}} plus an error string or None."""
    _raw, d, err = _read()
    out = {}
    for pk, (sk, check, default) in CC_KEYS.items():
        val = default
        if d and sk in d:
            try:
                val = check(d[sk])
            except ValueError:
                val = default          # a hand-edited bad value shows as the default
        out[pk] = {"value": val, "default": default, "src": "claude", "path": settings_path(),
                   "restart": False, "apply": "new_session"}
    return out, err


OTEL_KEY = "OTEL_EXPORTER_OTLP_ENDPOINT"
_OTEL_RE = re.compile(r"(http://(?:127\.0\.0\.1|localhost):)(\d{2,5})(/?)")


def otel_get():
    """{value, ok}: ok = it is the local Sidereus URL form, so a «Port» save may rewrite its port."""
    _raw, d, _err = _read()
    env = d.get("env") if isinstance(d, dict) else None
    v = env.get(OTEL_KEY) if isinstance(env, dict) else None
    return {"value": v, "ok": isinstance(v, str) and bool(_OTEL_RE.fullmatch(v))}


def otel_port_set(port):
    """Rewrite only the port of env.OTEL_EXPORTER_OTLP_ENDPOINT -> (code, out). ⚠Raw-byte replace of that one value."""
    p = settings_path()
    with _LOCK:
        raw, old, err = _read()
        if err:
            return 400, {"ok": False, "err": err}
        env = old.get("env")
        cur = env.get(OTEL_KEY) if isinstance(env, dict) else None
        m = _OTEL_RE.fullmatch(cur) if isinstance(cur, str) else None
        if not m:
            return 400, {"ok": False, "err": "OTEL endpoint is not the local Sidereus URL — left as is"}
        val = m.group(1) + str(int(port)) + m.group(3)
        if val == cur:
            return 200, {"ok": True, "value": val, "changed": False}
        a, b = json.dumps(cur).encode("utf-8"), json.dumps(val).encode("utf-8")
        if raw.count(a) != 1:
            return 400, {"ok": False, "err": "OTEL endpoint value is not unique in the file — change it by hand"}
        new_raw = raw.replace(a, b)
        want = dict(old)
        want["env"] = dict(env)
        want["env"][OTEL_KEY] = val
        try:
            chk = json.loads(new_raw.decode("utf-8-sig"))
        except ValueError:
            return 500, {"ok": False, "err": "refused: re-parse check failed"}
        if chk != want or list(chk) != list(old) or list(chk["env"]) != list(env):
            return 500, {"ok": False, "err": "refused: other keys would change"}
        code, bak = _write_raw(p, raw, new_raw)
        if code != 200:
            return code, bak
    return 200, {"ok": True, "value": val, "changed": True, "backup": bak, "apply": "new_session"}


def _write_raw(p, raw, new_raw, label=None, into=None):
    """Backup, then atomically replace p with new_raw -> (200, backup path) or (code, error body). Caller holds _LOCK."""
    try:
        bak = _backup(p) if label is None else _backup(p, label, into)
        tmp = "%s.sidereus-tmp.%d" % (p, os.getpid())
        with open(tmp, "wb") as f:
            f.write(new_raw)
            f.flush()
            os.fsync(f.fileno())
        try:
            with open(p, "rb") as f:
                now = f.read()
            if now != raw:     # ⚠Claude Code may have rewritten the file since our read — never clobber that.
                return 409, {"ok": False, "err": "settings.json changed while writing — try again"}
            shutil.copymode(p, tmp)
            os.replace(tmp, p)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    except OSError as e:
        return 500, {"ok": False, "err": "write failed (%s)" % type(e).__name__}
    return 200, bak


_WS = " \t\n\r"


def _members(text):
    """Top-level members of a JSON object text -> (open brace index, [(key, key start, value start, value end)]) or None."""
    dec = json.JSONDecoder()
    i = 0
    n = len(text)
    while i < n and text[i] in _WS:
        i += 1
    if i >= n or text[i] != "{":
        return None
    brace, i, out = i, i + 1, []
    while True:
        while i < n and text[i] in _WS:
            i += 1
        if i < n and text[i] == "}" and not out:
            return brace, out
        if i >= n or text[i] != '"':
            return None
        ks = i
        try:
            key, i = dec.raw_decode(text, i)
        except ValueError:
            return None
        ke = i
        while i < n and text[i] in _WS:
            i += 1
        if i >= n or text[i] != ":":
            return None
        i += 1
        while i < n and text[i] in _WS:
            i += 1
        vs = i
        try:
            _v, i = dec.raw_decode(text, i)
        except ValueError:
            return None
        if not isinstance(key, str):
            return None
        out.append((key, ks, ke, vs, i))
        while i < n and text[i] in _WS:
            i += 1
        if i < n and text[i] == ",":
            i += 1
            continue
        if i < n and text[i] == "}":
            return brace, out
        return None


def _splice(raw, sk, val):
    """raw with only top-level sk's value replaced (or sk appended, copying the last member's layout) -> bytes or None.

    ⚠Never re-serialises the file: hand formatting (4-space indent, one-line objects, raw non-ASCII) must survive byte for byte.
    """
    bom = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""     # ⚠kept as-is on write (byte-exact rule)
    text = raw[len(bom):].decode("utf-8")
    m = _members(text)
    if m is None:
        return None
    brace, mem = m
    hits = [x for x in mem if x[0] == sk]
    enc = json.dumps(val)
    if len(hits) > 1:
        return None                     # duplicate key: which one Claude Code reads is not ours to guess
    if hits:
        _k, _ks, _ke, vs, ve = hits[0]
        new = text[:vs] + enc + text[ve:]
    elif not mem:
        new = text[:brace + 1] + json.dumps(sk) + ": " + enc + text[brace + 1:]
    else:
        _k, ks, ke, vs, ve = mem[-1]
        seg = text[(mem[-2][4] if len(mem) > 1 else brace):ks]
        lead = seg[max(seg.rfind(","), seg.rfind("{")) + 1:]          # whitespace before the last key, e.g. "\n    "
        new = text[:ve] + "," + lead + json.dumps(sk) + text[ke:vs] + enc + text[ve:]
    return bom + new.encode("utf-8")


def _acct_row(t):
    """One extra account's current values for the page note, same check/default fallback as cc_get."""
    if os.path.islink(t["path"]):
        return {"label": t["label"], "path": t["path"], "auto": None, "window": None, "err": "symlink"}
    _raw, d, err = _read_at(t["path"])
    row = {"label": t["label"], "path": t["path"], "err": err}
    for name, pk in (("auto", "cc_auto_compact"), ("window", "cc_compact_window")):
        sk, check, default = CC_KEYS[pk]
        val = default
        if d and sk in d:
            try:
                val = check(d[sk])
            except ValueError:
                val = default
        row[name] = val
    return row


def prefs_get_all():
    """GET /api/prefs body: config.local.json prefs + the two Claude Code keys."""
    out = prefs_get()
    cc, err = cc_get()
    out["keys"].update(cc)
    out["cc_path"] = settings_path()
    out["otel"] = otel_get()
    out["features"] = features_listing()   # settings «Features» rows (web/js/90c-features.js)
    if err:
        out["cc_err"] = err
    tg = _targets()
    out["cc_primary_label"] = tg[0]["label"]
    if len(tg) > 1:
        out["cc_accts"] = [_acct_row(t) for t in tg[1:]]
    return out


_SAFE_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _backup(p, label=None, into=None):
    """Copy p to <trash>/<ts>[-n]/settings.json; an extra account's copy goes to <ts>[-n]/<label>/settings.json."""
    if into and label and os.path.isdir(into):
        d = into                          # same folder as the primary's backup of this save
    else:
        base = os.path.join(_trash_dir(), _strftime("%Y%m%d-%H%M%S"))
        d, n = base, 1
        while os.path.exists(d):
            n += 1
            d = "%s-%d" % (base, n)
        os.makedirs(d)
    if label:
        sub = label if _SAFE_LABEL.fullmatch(label) else "acct"     # ⚠labels come from a registry file; never a path
        base = d = os.path.join(d, sub)
        n = 1
        while os.path.exists(d):
            n += 1
            d = "%s-%d" % (base, n)
        os.makedirs(d)
    dst = os.path.join(d, "settings.json")
    shutil.copy2(p, dst)
    return dst


def _plan(p, sk, val):
    """Read p and splice sk=val -> (raw, new_raw, prev, err); err = (code, message) or None. Writes nothing."""
    raw, old, err = _read_at(p)
    if err:
        return raw, None, None, (400, err)
    new_raw, _chk, perr = _plan_raw(raw, old, sk, val)
    return raw, new_raw, old.get(sk), perr


def _plan_raw(raw, old, sk, val):
    """Splice sk=val into raw (parsed as old) and re-check -> (new_raw, new dict, err); err = (code, message) or None."""
    new_raw = _splice(raw, sk, val)
    if new_raw is None:
        return None, None, (400, "settings.json layout can't be edited safely (duplicate %s?) — change it by hand" % sk)
    try:
        chk = json.loads(new_raw.decode("utf-8-sig"))
    except ValueError:
        return None, None, (500, "refused: re-parse check failed")
    same = isinstance(chk, dict) and sk in chk and type(chk[sk]) is type(val) and chk[sk] == val
    if not same or not _same_others(old, chk, sk) or (sk not in old and list(chk) != list(old) + [sk]):
        return None, None, (500, "refused: other keys would change")
    return new_raw, chk, None


def cc_set(pk, value):
    """Write one of the two keys -> (code, out). ⚠Raw-byte splice of that one value: every other byte stays identical."""
    sk, check, _default = CC_KEYS[pk]
    try:
        val = check(value)
    except ValueError as e:
        return 400, {"ok": False, "err": str(e)}
    with _LOCK:
        tg = _targets()
        plans = []
        for t in tg:
            if not t["primary"] and os.path.islink(t["path"]):
                plans.append((None, None, None, (400, "symlink")))   # ⚠never write through a link to an unknown file
            else:
                plans.append(_plan(t["path"], sk, val))
        raw, new_raw, prev, perr = plans[0]
        if perr:
            return perr[0], {"ok": False, "err": perr[1]}    # primary refused: nothing is written anywhere
        bak = None
        if new_raw != raw:
            code, bak = _write_raw(tg[0]["path"], raw, new_raw)
            if code != 200:
                return code, bak
        files = [{"label": tg[0]["label"], "path": tg[0]["path"], "status": "written" if bak else "same", "backup": bak}]
        into = os.path.dirname(bak) if bak else None
        for t, (xraw, xnew, _xprev, xerr) in zip(tg[1:], plans[1:]):
            row = {"label": t["label"], "path": t["path"]}
            if xerr:
                row.update(status="skipped", err=xerr[1])
            elif xnew == xraw:
                row["status"] = "same"
            else:
                code, xb = _write_raw(t["path"], xraw, xnew, t["label"], into)
                if code == 200:
                    row.update(status="written", backup=xb)
                    into = into or os.path.dirname(os.path.dirname(xb))
                else:
                    row.update(status="failed", err=xb.get("err"))
            files.append(row)
    out = {"ok": True, "value": val, "restart": False, "apply": "new_session", "backup": bak}
    if len(tg) > 1:
        out["files"] = files
    if sk == "autoCompactWindow" and val != prev:
        herr = compact_hist_append(_strftime("%Y-%m-%d"), val)
        if herr:
            out["hist_err"] = herr
    return 200, out


_ACCT_FIELDS = (("auto", "cc_auto_compact"), ("window", "cc_compact_window"))


def _shown(d):
    """{auto, window} as the page shows them (absent or bad value -> default), from a parsed settings dict or None."""
    out = {}
    for name, pk in _ACCT_FIELDS:
        sk, check, default = CC_KEYS[pk]
        val = default
        if d and sk in d:
            try:
                val = check(d[sk])
            except ValueError:
                val = default
        out[name] = val
    return out


def _plan_acct(t, want):
    """Plan one account's save of `want` ({settings key: value}) -> dict(raw, new_raw, old, err). Writes nothing."""
    if not t["primary"] and os.path.islink(t["path"]):
        return {"raw": None, "new_raw": None, "old": None, "err": (400, "symlink")}   # ⚠never write through a link
    raw, old, err = _read_at(t["path"])
    if err:
        return {"raw": raw, "new_raw": None, "old": None, "err": (400, err)}
    cur_raw, cur = raw, old
    for sk, val in want.items():
        nr, chk, perr = _plan_raw(cur_raw, cur, sk, val)
        if perr:
            return {"raw": raw, "new_raw": None, "old": old, "err": perr}
        cur_raw, cur = nr, chk
    ks = list(want)
    others_a = {k: v for k, v in old.items() if k not in ks}
    others_b = {k: v for k, v in cur.items() if k not in ks}
    if list(others_a) != list(others_b) or others_a != others_b:     # ⚠both splices together must leave every other key as is
        return {"raw": raw, "new_raw": None, "old": old, "err": (500, "refused: other keys would change")}
    return {"raw": raw, "new_raw": cur_raw, "old": old, "err": None}


def cc_set_accts(req):
    """POST /api/prefs/set {key:"cc_accounts", dry, accts:[{path, auto, window}]} -> (code, out). Per-account values.

    ⚠Paths are matched against _targets() exactly, never joined or resolved; an unknown path refuses the whole request.
    """
    accts, dry = req.get("accts"), req.get("dry") is True
    if not isinstance(accts, list) or not accts:
        return 400, {"ok": False, "err": "accts must be a non-empty list"}
    with _LOCK:
        tg = _targets()
        by_path = {t["path"]: t for t in tg}
        want = {}
        for a in accts:
            p = a.get("path") if isinstance(a, dict) else None
            if not isinstance(p, str) or p not in by_path:
                return 400, {"ok": False, "err": "unknown settings.json path"}
            if p in want:
                return 400, {"ok": False, "err": "path listed twice"}
            w = {}
            try:
                if a.get("auto") is not None:
                    w["autoCompactEnabled"] = _v_bool(a["auto"])
                if a.get("window") is not None:
                    w["autoCompactWindow"] = _v_win(a["window"])
            except ValueError as e:
                return 400, {"ok": False, "err": str(e)}
            want[p] = w
        rows, plans = [], []
        for t in tg:
            w = want.get(t["path"]) or {}
            pl = _plan_acct(t, w) if w else None
            row = {"label": t["label"], "path": t["path"], "primary": t["primary"], "err": None}
            if pl is None:
                _r, d, _e = (None, None, None) if (not t["primary"] and os.path.islink(t["path"])) else _read_at(t["path"])
                row.update(before=_shown(d), status="same")
            elif pl["err"]:
                if t["primary"]:
                    return pl["err"][0], {"ok": False, "err": pl["err"][1]}   # primary refused: nothing is written anywhere
                row.update(before=_shown(pl["old"]), status="skipped", err=pl["err"][1])
            else:
                row.update(before=_shown(pl["old"]), status="change" if pl["new_raw"] != pl["raw"] else "same")
            row["after"] = _shown(json.loads(pl["new_raw"].decode("utf-8-sig"))) if row["status"] == "change" else dict(row["before"])
            rows.append(row)
            plans.append(pl)
        if dry:
            return 200, {"ok": True, "dry": True, "files": rows}
        into = None
        for t, row, pl in zip(tg, rows, plans):
            if row["status"] != "change":
                continue
            if t["primary"]:
                code, bak = _write_raw(t["path"], pl["raw"], pl["new_raw"])
                if code != 200:
                    return code, bak       # primary is written first, so nothing else has been written yet
                into = os.path.dirname(bak)
                row.update(status="written", backup=bak)
                continue
            code, xb = _write_raw(t["path"], pl["raw"], pl["new_raw"], t["label"], into)
            if code == 200:
                row.update(status="written", backup=xb)
                into = into or os.path.dirname(os.path.dirname(xb))
            else:
                row.update(status="failed", err=xb.get("err"), after=dict(row["before"]))
    out = {"ok": True, "dry": False, "files": rows, "restart": False, "apply": "new_session"}
    prim, ppl = rows[0], plans[0]
    nw = (want.get(prim["path"]) or {}).get("autoCompactWindow")
    if prim["status"] == "written" and nw is not None and nw != ppl["old"].get("autoCompactWindow"):
        herr = compact_hist_append(_strftime("%Y-%m-%d"), nw)
        if herr:
            out["hist_err"] = herr
    return 200, out


def prefs_set_all(req):
    """POST /api/prefs/set: the two Claude Code keys here, everything else to prefs_set."""
    if isinstance(req, dict) and req.get("key") == "cc_accounts":
        return cc_set_accts(req)
    if isinstance(req, dict) and req.get("key") in CC_KEYS:
        if req.get("reset") is True or "value" not in req:
            return 400, {"ok": False, "err": "value missing (reset is not supported for Claude Code keys)"}
        return cc_set(req["key"], req["value"])
    if isinstance(req, dict) and req.get("key") == "features" and req.get("reset") is not True:
        try:
            check_toggles(req.get("value"))     # ⚠only ids with a manifest; prefs._v_features checks shape only
        except ValueError as e:
            return 400, {"ok": False, "err": str(e)}
    code, out = prefs_set(req)
    # «Port» save with otel:true also moves the OTEL endpoint's port (the page asked in the same confirm).
    if code == 200 and isinstance(req, dict) and req.get("key") == "port" and req.get("otel") is True and isinstance(out.get("value"), int):
        out["otel"] = otel_port_set(out["value"])[1]
    return code, out
