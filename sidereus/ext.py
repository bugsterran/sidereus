"""External CLI agent sessions (Gemini CLI, Codex CLI) fed by hooks — views: rows, work panel, child runs,
today usage, hook-settings check. The store (registry, ingest, persistence, token store) is sidereus/ext_store.py."""
import json
import os
import time
from sidereus.warn import warn_once
from sidereus.bus import _load, codex_cursor, codex_id_ok, codex_ok_set
from sidereus.ident import _proj_name, _sid8, mbox_codex
from sidereus.timefmt import iso_local
from sidereus.adapter import adapter_scan
from sidereus import live_probe   # module access: `_ps_snap_cache` is read at call time (tests patch it)
from sidereus.agents import plm_of
from sidereus.pl_runs import pl_act, pl_model
from sidereus import plat_copilot   # module access: tests patch `plat_copilot.root`
# Re-exported: chat_server, timeline, history import these from `sidereus.ext`.
# ⚠Patch store internals (`_ext_save_locked`, `_runs_save_locked`, `EXT_FILE`/`EXT_RUNS_FILE`, `_pid_start`) on `ext_store`.
from sidereus.ext_store import (PLAT_MODS, EXT_PLAT, EXT_EV_N, EXT_RATE_WIN, _ext_lock, _ext,
                             _ext_stat, _runs, _tok_lock, _tok, _ext_prune_locked, ext_ingest, ext_runs,
                             ext_gone_check, ext_dismiss, ext_tok_refresh, _tok_sum, ext_tok,
                             EXT_ENDED_KEEP_S, ext_ended, ext_hook_msgs, ext_hook_cwds,
                             ext_side_msgs, ext_side_sess, ext_side_tok)


EXT_NAME = {m.KEY: m.NAME for m in PLAT_MODS.values()}
ROLL_WIN_S = EXT_ENDED_KEEP_S   # 600 s: a Codex rollout written this recently, with no hook event, gets a row


def ext_usage_today(now=None):
    """{plat key: {tok, in, out, cache, thought, n_sessions, cost, costMiss, models}} for today (local midnight)."""
    import datetime as _dt
    now = now or time.time()
    t = _dt.datetime.fromtimestamp(now)
    mid = _dt.datetime(t.year, t.month, t.day).timestamp()
    win = now - EXT_RATE_WIN
    # ★Disk scan first — the same source as the timeline and History (09-24: `_tok` alone read {} after a
    # restart and missed ended sessions). Live `_tok` only adds message ids not on disk yet.
    sess = {}
    rate = {}
    subs = set()             # CLI subagent chats: tokens count, but they are not sessions
    for plat, mod in PLAT_MODS.items():
        for c in adapter_scan(mod, min(mid, win)):
            sess[(plat, c["sid"])] = dict(c["msgs"])
            if c.get("parent"):
                subs.add((plat, c["sid"]))
            if c.get("rate") and c["rate"][0] > rate.get(plat, (0,))[0]:
                rate[plat] = c["rate"]
    ondisk = {m for ms in sess.values() for m in ms}
    with _tok_lock:
        live = [(k, dict(e["msgs"])) for k, e in _tok.items()]
    for k, msgs in live:
        d = sess.setdefault(k, {})
        for m, v in msgs.items():
            if m not in ondisk:
                d.setdefault(m, v)
    for k, msgs in ext_side_msgs(min(mid, win)).items():   # hook-sent tokens (Cursor) + Copilot usage records
        sess.setdefault(k, {}).update(msgs)
    out = {}
    for (plat, _sid), msgs in sess.items():
        s = _tok_sum(msgs, mid)
        if not s["tok"]:
            continue
        p = out.setdefault(EXT_PLAT.get(plat, plat), {"tok": 0, "in": 0, "out": 0, "cache": 0,
                                                      "thought": 0, "n_sessions": 0,
                                                      "cost": None, "costMiss": 0})
        for k in ("tok", "in", "out", "cache", "thought", "costMiss"):
            p[k] += s[k]
        if s["cost"] is not None:
            p["cost"] = (p["cost"] or 0.0) + s["cost"]
        p["n_sessions"] += 0 if (plat, _sid) in subs else 1
        ms = set(p.get("models") or ()) | {v[5] for v in msgs.values() if v[4] >= mid and v[5]}
        p["models"] = sorted(ms)
    # Last-10-min rate per platform for the «Live · 10 min» card (own line, never on Claude's chart).
    for (plat, _sid), msgs in sess.items():
        p = out.get(EXT_PLAT.get(plat, plat))
        w = _tok_sum({k: v for k, v in msgs.items() if v[4] <= now}, win)
        if p is None or not w["tok"]:
            continue
        r = p.setdefault("rate10", {"tok": 0, "perMin": 0.0, "cost": None, "costMiss": 0, "win": EXT_RATE_WIN})
        r["tok"] += w["tok"]
        r["costMiss"] += w["costMiss"]
        r["perMin"] = r["tok"] / (EXT_RATE_WIN / 60.0)
        if w["cost"] is not None:
            r["cost"] = (r["cost"] or 0.0) + w["cost"]
    # A CLI with a session today but no tokens yet (no reply, or hook-only like Cursor) still gets a «Today 0» entry,
    # so a connected CLI does not look missing. ⚠Entries come only from sessions seen today or still open (live pid,
    # not gone — an idle CLI left open overnight is still in use), never from installs alone.
    with _ext_lock:
        seen = {(p, sid) for (p, sid), v in _ext.items()
                if float(v.get("lastSeen") or 0) >= mid or (v.get("pid") and not v.get("gone"))}
    seen |= {k for k, msgs in sess.items() if k not in subs}
    for plat, _sid in seen:
        k = EXT_PLAT.get(plat)
        if k and k not in out:
            out[k] = {"tok": 0, "in": 0, "out": 0, "cache": 0, "thought": 0, "n_sessions": 0,
                      "cost": None, "costMiss": 0, "models": []}
    for plat, _sid in seen:
        k = EXT_PLAT.get(plat)
        if k and not out[k]["tok"]:
            out[k]["n_sessions"] += 1
    # ★The platform's own limit windows (Codex 5h/weekly %), only when its record carried them and not yet reset.
    for plat, (_t, rt) in rate.items():
        p = out.get(EXT_PLAT.get(plat, plat))
        ws = {k: w for k, w in rt.items() if isinstance(w, dict) and (not w.get("reset") or w["reset"] > t.timestamp())}
        if p is not None and ws:
            if isinstance(rt.get("plan"), str):   # plan rides along only with a live window, never alone
                ws["plan"] = rt["plan"]
            p["rate"] = ws
    cp = out.get(EXT_PLAT[plat_copilot.PLAT])
    if cp is not None:   # Copilot request quota: the newest snapshot any session reported
        cp["quota"] = plat_copilot.quota(t.timestamp())
    return out


def _codex_running():
    """False only when the cached process list (never a fresh `ps`) is non-empty and holds no codex process."""
    snap = live_probe._ps_snap_cache[1]
    if not snap:
        return True
    for row in snap:
        argv = str(row[2] if len(row) > 2 else "").split()[:3]
        if any(os.path.basename(a).startswith("codex") for a in argv):
            return True
    return False


def _rollouts(now):
    mod = PLAT_MODS.get("codex")
    return adapter_scan(mod, now - ROLL_WIN_S) if mod is not None else []


def _rollout_of(sid, now=None):
    now = now or time.time()
    return next((c for c in _rollouts(now) if c.get("sid") == sid and c.get("live")), None)


def ext_rollout_rows(now=None):
    """Codex sessions seen only through a fresh rollout file (hooks not connected) -> ext_rows-shaped rows.
    ⚠State is unknown (no events); `rollout: True` lets the screen mark it. A hook row for the same sid wins."""
    now = now or time.time()
    rows = []
    try:
        cands = [c for c in _rollouts(now)
                 if c.get("live") and c.get("kind") not in ("exec", "subagent")
                 and (c.get("mtime") or 0) >= now - ROLL_WIN_S]
        if not cands or not _codex_running():
            return rows
        with _ext_lock:
            known = {sid for (p, sid) in _ext if p == "codex"} | set(_runs)
        known |= ext_ended("codex", now)          # ended / gone / dismissed: never back as a rollout row
        for c in cands:
            sid = c.get("sid") or ""
            if not sid or sid in known:
                continue
            cwd = c.get("cwd") or ""
            last = float(c.get("mtime") or now)
            first = float(c.get("start") or last)
            tk = _tok_sum(c.get("msgs") or {})
            row = {
                "id": "", "sid": "", "project": "?", "gotPrompt": 0,
                "creq": 0, "burn": 0, "rpm": 0, "cwd": "", "branch": "",
                "tool": "", "targ": "", "sub": [], "bgs": [], "mon": [],
                "runmin": {}, "kind": "", "ageSec": 0, "bytes": 0, "repos": [],
                "mbox": "", "mboxSrc": "", "cost": 0, "ctx": 0, "model": "",
                "win": 0, "winSrc": "", "winN": 0,
                "git": "", "state": "unknown", "blocked": "",
                "otel": False, "otelEv": "", "otelAt": 0, "err": False, "plat": EXT_PLAT["codex"],
            }
            row.update({
                "id": _sid8(sid), "sid": sid, "project": _proj_name(cwd) or "?", "cwd": cwd,
                "model": str(c.get("model") or "")[:40],
                "tok": tk.get("tok", 0),
                "tokSplit": {k: tk.get(k, 0) for k in ("in", "out", "cache", "thought")},
                "estCost": tk.get("cost"), "costMiss": tk.get("costMiss", 0),
                "ageSec": max(0, int(now - last)),
                "runmin": {"sub": 0, "bg": 0, "run": max(0, int((last - first) / 60))},
                "kind": "codex", "goneWhy": "", "pid": 0, "rollout": True,
            })
            row["mbox"], row["mboxSrc"] = mbox_codex(cwd)
            rows.append(row)
    except Exception as e:                        # the rest of the list must survive
        # Reuses the ext_rows template so no new I18N.ko entry is needed.
        warn_once("ext-rollout-rows", "Could not build external session rows ({err})", vars={"err": type(e).__name__})
    return rows


def ext_work(plat, sid, now=None):
    """Work panel for one external session, resolved by (platform, session_id) only.
    ⚠Never by cwd/project — a Claude session in the same folder would answer instead (user report 2026-09-24)."""
    plat = str(plat or "").strip().lower()
    sid = str(sid or "").strip()
    name = plat if plat in EXT_PLAT else next((k for k, p in EXT_PLAT.items() if p == plat), "")
    if not name or not sid:
        return {"ok": False, "msg": "External session not found"}
    with _ext_lock:
        _ext_prune_locked(time.time())
        v = dict(_ext.get((name, sid)) or {})
        r = _runs.get(sid) if not v else None
    if not v and r and r.get("plat") == name:     # an ended child run — only its stored metadata is left
        v = {"cwd": r.get("cwd") or "", "model": r.get("model") or "", "state": "done",
             "firstSeen": r.get("start"), "lastSeen": r.get("end"), "parent": r.get("parent")}
    if not v and name == "codex":                 # a rollout-only row (no hooks): metadata from the record scan
        c = _rollout_of(sid, now)
        if c:
            v = {"cwd": c["cwd"], "model": c.get("model") or "", "state": "unknown",
                 "firstSeen": c.get("start") or c.get("mtime"), "lastSeen": c.get("mtime")}
    if not v:
        return {"ok": False, "msg": "External session not found"}
    key = EXT_PLAT[name]
    try:
        last = float(v.get("lastSeen") or 0)
        first = float(v.get("firstSeen") or last)
    except (TypeError, ValueError):
        last = first = 0.0
    iso = lambda t: iso_local(t) if t else ""
    evs = [e for e in (v.get("ev") or []) if isinstance(e, dict)][-EXT_EV_N:]
    return {"ok": True, "ext": True, "plat": key, "platform": name, "sid": sid,
            "type": EXT_NAME.get(key, name) + " · " + _sid8(sid), "desc": v.get("cwd") or "",
            "cwd": v.get("cwd") or "", "model": str(v.get("model") or "")[:40],
            "state": v.get("state") or "unknown", "tool": v.get("tool") or "",
            "blocked": bool(v.get("blocked")),
            "firstSeen": first, "lastSeen": last, "first": iso(first), "last": iso(last),
            "events": [{"e": str(e.get("e") or ""), "tool": str(e.get("tool") or ""),
                        "t": float(e.get("t") or 0)} for e in evs],
            "parent": v.get("parent") or "",
            "steps": [], "cutSteps": 0, "says": []}


def _stop_after(v, t):
    """True when the store row's hook ring has a Stop at or after t (the CLI ended its turn after the [pl:] mark)."""
    try:
        return any(isinstance(e, dict) and e.get("e") == "Stop" and float(e.get("t") or 0) >= t
                   for e in (v.get("ev") or []))
    except (TypeError, ValueError):
        return False


def ext_rows():
    """External CLI sessions → rows with **the same key set** as `_session_row`.
    ⚠Missing even one key breaks the frontend at that spot ⇒ lay down safe defaults for all and override only what is known."""
    now = time.time()
    rows = []
    try:
        ext_gone_check(now)
        with _ext_lock:
            _ext_prune_locked(now)
            items = [(k, dict(v)) for k, v in _ext.items()]
        for (plat, sid), v in items:
            if v.get("parent"):
                continue                          # shown under its Claude session (`ext_children`)
            try:
                last = float(v.get("lastSeen") or now)
                first = float(v.get("firstSeen") or last)
            except (TypeError, ValueError):
                last = first = now
            cwd = v.get("cwd") or ""
            st = v.get("state") or "unknown"
            # ⚠No age cap on ask/blocked: a pending request leaves only on the CLI's own event or a dead pid (ext_gone_check).
            ext_tok_refresh(plat, sid, v.get("transcript_path") or "")
            tk = ext_tok(plat, sid) or ext_side_tok(plat, sid) or {}   # Copilot: no transcript_path, tokens from its records
            row = {
                "id": "", "sid": "", "project": "?", "gotPrompt": 0,
                "creq": 0, "burn": 0, "rpm": 0, "cwd": "", "branch": "",
                "tool": "", "targ": "", "sub": [], "bgs": [], "mon": [],
                "runmin": {}, "kind": "", "ageSec": 0, "bytes": 0, "repos": [],
                "mbox": "", "mboxSrc": "", "cost": 0, "ctx": 0, "model": "",
                "win": 0, "winSrc": "", "winN": 0,
                "git": "", "state": "unknown", "blocked": "",
                "otel": False, "otelEv": "", "otelAt": 0, "err": False, "plat": EXT_PLAT[plat],
            }
            row.update({
                "id": _sid8(sid),
                "sid": sid,
                "project": _proj_name(cwd) or "?",
                "cwd": cwd,
                "state": st,
                "tool": v.get("tool") or "",
                "targ": v.get("tool") or "",
                # ⚠`_model_label` strips Claude-specific prefixes/suffixes — do not use it for external models; keep their raw id.
                "model": str(v.get("model") or tk.get("model") or "")[:40],   # «gemini-3.5-flash-lite» is 21
                "tok": tk.get("tok", 0),
                "tokSplit": {k: tk.get(k, 0) for k in ("in", "out", "cache", "thought")},
                # ⚠Estimate only, in its own key — `cost` stays 0 (Claude's project-cost chip).
                "estCost": tk.get("cost"), "costMiss": tk.get("costMiss", 0),
                "ageSec": max(0, int(now - last)),
                # ⚠`runmin` is a **dict** the screen reads as `RM[kind]` — turning it into a number breaks at that spot.
                #   External sessions have no sub·bg, so lay 0 and put total run minutes in `run`.
                "runmin": {"sub": 0, "bg": 0, "run": max(0, int((last - first) / 60))},
                "kind": plat,
                # ⚠The screen prints `blocked` as **a reason string** (`'Blocked · ' + x.blocked`) - a bool would become `Blocked · true`.
                "blocked": ("승인 대기" if v.get("blocked") else ""),
                "otel": True,             # this row's state is **event-based** (not inferred)
                "otelEv": v.get("state") or "",
                "goneWhy": v.get("goneWhy") or "",     # «Disconnected»: "pid" = process gone, "silent" = no news (guess)
                "pid": v.get("pid") if isinstance(v.get("pid"), int) else 0,   # hook-reported CLI pid, for «To terminal»
            })
            if plat == "codex":   # only Codex hooks log in to the mailbox; other CLIs keep "" (send off)
                row["mbox"], row["mboxSrc"] = mbox_codex(cwd)
            plm = None if v.get("goneWhy") else plm_of(sid, now)   # shell-marker [pl:] stage; added only when live, like Claude rows
            if plm and st in ("wait", "abort") and _stop_after(v, now - plm.get("age", 0)):
                plm = None   # ⚠turn ended after the mark: a held (45-min) shell marker would keep the stage «running»
            if plm:
                row["plm"] = plm
            try:   # merged run model; external CLIs have no subagent dir or sub rows
                plrun = pl_model(sid, "", [], plm, now, pl_act(st, dead=bool(v.get("goneWhy"))))
            except Exception as e:
                plrun = []
                warn_once("ext-plmodel", "Could not build the pipeline run model ({err})",
                          vars={"err": type(e).__name__}, soft=True)
            if plrun:
                row["plrun"] = plrun
            rows.append(row)
    except Exception as e:                        # even if external sessions break, the Claude list must survive
        warn_once("ext-rows", "Could not build external session rows ({err})", vars={"err": f"{type(e).__name__}: {e}"})
    return rows


def codex_env_dedupe(rows):
    """Hook + rollout Codex rows -> same rows with launcher ids judged: «env» (sendable) when the id is held by exactly
    one live row AND that row has a reader — hook-fed (the Codex Stop hook checks the id's inbox at turn end) or
    `read-<id>.cursor` exists (rollout-only rows need the cursor). Published via bus.codex_ok_set for dm_target_error.
    ⚠A reader proves someone reads `<basename>-codex`, not which row — two folders named `app` share the id."""
    seen, live = set(), {}
    for r in rows:
        sid = r.get("sid")
        if r.get("plat") != EXT_PLAT["codex"] or not sid or sid in seen:
            continue
        seen.add(sid)
        if r.get("goneWhy") or r.get("state") == "done" or r.get("mboxSrc") not in ("env", "folder"):
            continue
        if r.get("mbox"):
            live.setdefault(r["mbox"], []).append(r)
    ident = _load("identity.json", {})
    ok = {m for m, rs in live.items() if len(rs) == 1 and codex_id_ok(m, ident)
          and (not rs[0].get("rollout") or codex_cursor(m))}
    codex_ok_set(ok)
    for r in rows:
        if r.get("plat") == EXT_PLAT["codex"] and r.get("mboxSrc") in ("env", "folder") and r.get("mbox"):
            r["mboxSrc"] = "env" if r["mbox"] in ok else "folder"
    return rows


EXT_CHILD_MAX = 20      # per parent in the sessions drawer (the timeline shows every run in its window)


def ext_children(rows, now=None):
    """Attach `gms` (child CLI runs **still live**) to each Claude row whose sid launched them.
    ★Finished runs leave the drawer (persistence is the timeline's job — `timeline_ext._ext_tl`, ext-runs.json).
    ⚠Label is metadata only: «gemini -p» + model + duration + tokens — never the task text."""
    now = now or time.time()
    ext_gone_check(now)
    by_par = {}
    for r in ext_runs():
        by_par.setdefault(r.get("parent"), []).append(r)
    if not by_par:
        return
    with _ext_lock:
        live = {sid: dict(v) for (_p, sid), v in _ext.items()
                if v.get("parent") and v.get("state") != "gone"}     # a dead run leaves the drawer at once
    for row in rows:
        if row.get("plat") not in (None, "", "cc"):
            continue
        runs = by_par.get(row.get("sid") or "")
        if not runs:
            continue
        out = []
        for r in [x for x in runs if x["sid"] in live][-EXT_CHILD_MAX:]:
            sid = r["sid"]
            lv = live.get(sid)
            plat = r.get("plat") or "gemini"
            if lv:
                ext_tok_refresh(plat, sid, lv.get("transcript_path") or "")
            tk = ext_tok(plat, sid) or {}
            st = (lv.get("state") if lv else "") or r.get("state") or "done"
            end = float((lv or {}).get("lastSeen") or r.get("end") or now)
            start = float(r.get("start") or end)
            out.append({"sid": sid, "plat": EXT_PLAT.get(plat, plat), "tid": "ext:" + EXT_PLAT.get(plat, plat) + "|" + sid,
                        "model": str(r.get("model") or tk.get("model") or "")[:40],
                        "tok": int(tk.get("tok") or r.get("tok") or 0),
                        "dur": max(0, int(end - start)), "start": int(start), "end": int(end),
                        "run": bool(lv) and st in ("tool", "think"), "done": not lv,
                        "idle": max(0, int(now - end)), "min": max(0, int((now - start) / 60))})
            # ⚠Always send `cmd`: the drawer's JS no longer has a per-platform fallback (it shows the platform name).
            if plat in PLAT_MODS:
                out[-1]["cmd"] = PLAT_MODS[plat].CHILD_LABEL
        if out:
            row["gms"] = out


# ── Hook settings check (generic; platform data lives in plat_<name>.py) ────
# A module opts in with hook_settings(), hook_gaps(cfg), used_since(since), HOOK_DOC(_EN).
# ★Throttled: re-evaluated at most every HOOK_CHECK_S, file re-read only when its mtime changes.
#   A missing hook is certain, not flaky ⇒ hard warning, emitted once per evaluation (5 min < WARN_TTL_S keeps it fresh).
#   ⚠Once fixed it lingers until WARN_TTL_S (30 min): warn.py has no drop-a-key helper (dismiss logic is inline in chat_server).
HOOK_CHECK_S = 300
HOOK_USED_S = 7 * 86400     # only users who ran this CLI recently (store or record files) get the check
_hook_chk = {}              # plat -> {"at": last evaluation, "mt": settings mtime, "gaps": [...]}


def _hook_used(plat, mod, since):
    with _ext_lock:
        if any(k[0] == plat and (v.get("lastSeen") or 0) >= since for k, v in _ext.items()):
            return True
    try:
        return bool(mod.used_since(since))
    except Exception as e:
        warn_once("hook-used:" + plat, "{plat} usage check failed ({err}) — hook check skipped",
                  vars={"plat": plat, "err": f"{type(e).__name__}: {e}"}, soft=True)
        return False


def ext_hook_check(now=None):
    """Warn (hard) when a platform's settings file lost our hooks. Returns {plat: gaps} for tests."""
    now = now or time.time()
    out = {}
    for plat, mod in PLAT_MODS.items():
        if not hasattr(mod, "hook_gaps"):
            continue
        c = _hook_chk.setdefault(plat, {"at": 0.0, "mt": None, "gaps": []})
        if now - c["at"] >= HOOK_CHECK_S:
            c["at"] = now
            path = mod.hook_settings()
            if not os.path.isdir(os.path.dirname(path)) or not _hook_used(plat, mod, now - HOOK_USED_S):
                c["mt"], c["gaps"] = None, []
            else:
                try:
                    mt = os.stat(path).st_mtime
                except OSError:
                    mt = -1.0                     # no settings file = no hooks at all
                if mt != c["mt"]:
                    c["mt"] = mt
                    try:
                        with open(path, encoding="utf-8") as f:
                            cfg = json.load(f)
                    except (OSError, ValueError):
                        cfg = None
                    # ⚠Keep only names from hook_gaps — never the file's values (it may hold API keys).
                    c["gaps"] = list(mod.hook_gaps(cfg))
            if c["gaps"]:
                miss = ", ".join(c["gaps"])
                # The doc reference is a fixed per-platform phrase, so it is part of the template (Korean via I18N.ko).
                warn_once("hooks:" + plat,
                          "Sidereus hooks are missing from {name} settings ({miss}) — re-merge them per " + mod.HOOK_DOC_EN,
                          vars={"name": mod.NAME, "miss": miss})
        if c["gaps"]:
            out[plat] = list(c["gaps"])
    return out
