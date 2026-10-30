"""«Remove» one Claude Code hook entry from a user or project settings file (POST /api/hooks/remove, feature `harness`).

{proj, rm, dry:true} -> diff preview + base sha; {proj, rm, dry:false, base} -> sha-checked write after a backup.
`rm` is the opaque row id of harness.rm_key, recomputed here from the file: no index, path or command comes from the page.
Only the `hooks` member is re-serialised; every other byte of the file is kept and checked before writing.
Only the primary ~/.claude/settings.json and a known project's .claude files; plugin hook files and ~/.claude/settings.local.json are never written.
"""
import copy
import json
import os
import re

from sidereus import cc_settings, ctxsrc, harness, hook_connect, toolinv

HR_RM_RE = re.compile(r"r[0-9a-f]{16}")
HR_LABEL = {"user": "claude-user", "project": "claude-project", "project-local": "claude-project"}
HR_E_OUTSIDE = "outside the allowed settings files"
HR_E_GONE = "hook not found (reload the list)"
HR_E_BASE = "file changed since the preview (open it again)"
HR_E_UNSAFE = "could not edit safely (edit by hand)"


def _allowed(proj):
    """[(path, src)] the remover may edit: the primary settings.json, plus the project's two files for a known project.
    ⚠Extra accounts' settings.json stay limited to the cc_settings keys; a project whose .claude is ~/.claude adds nothing
    (its settings.local.json is user-local, never written)."""
    out, seen = [], set()
    cands = [(os.path.join(ctxsrc.CLAUDE_DIR, "settings.json"), "user")]
    base = os.path.join(proj, ".claude") if isinstance(proj, str) and proj else ""
    if base and proj in toolinv.known_projects() and os.path.realpath(base) != os.path.realpath(ctxsrc.CLAUDE_DIR):
        cands += [(os.path.join(base, "settings.json"), "project"), (os.path.join(base, "settings.local.json"), "project-local")]
    for p, src in cands:
        rp = os.path.realpath(p)
        if rp not in seen:
            seen.add(rp)
            out.append((p, src))
    return out


def _walk(path, hooks):
    """Yield (rm key, ev, group index, hook index) in file order, counting duplicates like harness._hook_rows."""
    dup = {}
    for ev, groups in (hooks.items() if isinstance(hooks, dict) else []):
        for gi, g in enumerate(groups if isinstance(groups, list) else []):
            if not isinstance(g, dict):
                continue
            m = g.get("matcher") if isinstance(g.get("matcher"), str) else ""
            for hi, h in enumerate(g.get("hooks") if isinstance(g.get("hooks"), list) else []):
                if not isinstance(h, dict):
                    continue
                dk = (str(ev), m, json.dumps(h, sort_keys=True))
                k, dup[dk] = dup.get(dk, 0), dup.get(dk, 0) + 1
                yield harness.rm_key(path, str(ev), m, h, k), ev, gi, hi


def _blocked(rm, allowed):
    """True when `rm` names a hook in a file outside the allow-list (plugin, user-local): refused, not «not found»."""
    ok = set(os.path.realpath(p) for p, _s in allowed)
    files = []
    for it in toolinv._raw_items():
        if it["kind"] == "hook" and it["file"] not in files and os.path.realpath(it["file"]) not in ok:
            files.append(it["file"])
    for p in files:
        _raw, d, err = hook_connect._read(p)
        if d and not err and any(x[0] == rm for x in _walk(p, d.get("hooks"))):
            return True
    return False


def _find(proj, rm):
    """-> (hit dict, None) or (None, (code, error))."""
    allowed = _allowed(proj)
    hits, bad = [], False
    for p, src in allowed:
        raw, d, err = hook_connect._read(p)
        bad = bad or bool(err)   # an unparsable allowed file may hold the entry: unsafe, not «not found»
        if raw is None or err or not d:
            continue
        for key, ev, gi, hi in _walk(p, d.get("hooks")):
            if key == rm:
                hits.append({"path": p, "src": src, "raw": raw, "d": d, "ev": ev, "gi": gi, "hi": hi})
    if len(hits) > 1:
        return None, (500, HR_E_UNSAFE)
    if hits:
        hp = hits[0]["path"]
        # ⚠A symlinked file or a symlinked .claude folder: os.replace would write through to wherever it points.
        if os.path.islink(hp) or os.path.islink(os.path.dirname(hp)):
            return None, (400, hook_connect.SYMLINK)   # ⚠os.replace would turn a dotfiles link into a regular file
        return hits[0], None
    if _blocked(rm, allowed):
        return None, (400, HR_E_OUTSIDE)
    if bad:
        return None, (500, HR_E_UNSAFE)
    return None, (404, HR_E_GONE)


def _plan(hit):
    """-> (new raw, diff, what) or None when the edit can't be proven to touch only that entry."""
    raw, d, ev, gi, hi = hit["raw"], hit["d"], hit["ev"], hit["gi"], hit["hi"]
    hooks = copy.deepcopy(d["hooks"])
    grp = hooks[ev][gi]
    h = grp["hooks"].pop(hi)
    if not grp["hooks"]:
        hooks[ev].pop(gi)
    if not hooks[ev]:
        del hooks[ev]
    bom = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""
    try:
        text = raw[len(bom):].decode("utf-8")
    except UnicodeDecodeError:
        return None
    sp = hook_connect._splice(text, [("hooks", hooks)])
    om = cc_settings._members(text)
    if sp is None or om is None:
        return None
    new, _nsp = sp
    nm = cc_settings._members(new)
    want = dict(d, hooks=hooks)
    try:
        ok = json.loads(new) == want
    except ValueError:
        ok = False
    oh = [x for x in om[1] if x[0] == "hooks"]
    nh = [x for x in (nm[1] if nm else []) if x[0] == "hooks"]
    # ⚠Self-check: everything outside the hooks value (other keys, their order, odd indentation, env) byte-identical.
    if not ok or len(oh) != 1 or len(nh) != 1 or [x[0] for x in om[1]] != [x[0] for x in nm[1]] \
            or text[:oh[0][3]] != new[:nh[0][3]] or text[oh[0][4]:] != new[nh[0][4]:]:
        return None
    diff = hook_connect._diff(text, new, hook_connect._shown(hit["path"]),
                              hook_connect._lines_of(text, [(oh[0][1], oh[0][4])]),
                              hook_connect._lines_of(new, [(nh[0][1], nh[0][4])]))
    c = h.get("command") if h.get("type", "command") == "command" else None
    what = {"ev": str(ev), "matcher": grp.get("matcher") if isinstance(grp.get("matcher"), str) else "",
            "cmd": harness.cmd_name(c) if isinstance(c, str) else str(h.get("type") or "")[:harness.HN_CMD_MAX], "src": hit["src"]}
    return bom + new.encode("utf-8"), diff, what


def remove(req):
    """(code, body) for POST /api/hooks/remove; the caller has checked the viewer Origin."""
    if not isinstance(req, dict) or not isinstance(req.get("rm"), str) or not HR_RM_RE.fullmatch(req["rm"]):
        return 404, {"ok": False, "err": HR_E_GONE}
    proj = req.get("proj") if isinstance(req.get("proj"), str) else ""
    with cc_settings._LOCK:   # same lock as the «Preferences» writes to the user settings.json
        hit, err = _find(proj, req["rm"])
        if err:
            return err[0], {"ok": False, "err": err[1]}
        pl = _plan(hit)
        if pl is None:
            return 500, {"ok": False, "err": HR_E_UNSAFE}
        new_raw, diff, what = pl
        base = hook_connect._sha(hit["raw"])
        if req.get("dry") is not False:
            return 200, {"ok": True, "diff": diff, "base": base, "what": what}
        if not isinstance(req.get("base"), str) or req["base"] != base:
            return 409, {"ok": False, "err": HR_E_BASE}
        code, bak = hook_connect._write(HR_LABEL[hit["src"]], hit["path"], hit["raw"], new_raw)
        if code != 200:
            return code, bak
    return 200, {"ok": True, "changed": True, "backup": hook_connect._shown(bak) if bak else ""}
