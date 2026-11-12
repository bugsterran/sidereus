"""External CLI session exits: ext_gone_check (dead pid / silence -> gone -> folded) and ext_dismiss (person
dismissed a pid-less pending row). Split out of sidereus/ext_store.py; bodies unchanged except store names.
⚠Every store name is read as `ext_store.X` at call time: tests patch `_ext_save_locked`, `_runs_save_locked`,
`_pid_gone`, `time` ... on ext_store, and a `from` import would freeze the unpatched objects."""
from sidereus import ext_store


def ext_gone_check(now=None):
    """Mark sessions whose CLI died (pid) or fell silent while busy (no pid) as gone; fold them after
    `EXT_GONE_GRACE_S` like a SessionEnd. History/timeline data stays (runs end at the last event)."""
    now = now or ext_store.time.time()
    with ext_store._ext_lock:
        if ext_store._ext_dedupe_locked():                  # rows saved before the dedupe existed
            ext_store._ext_save_locked()
        due = [(k, v["pid"], v.get("pstart") or "") for k, v in ext_store._ext.items()
               if v.get("pid") and not v.get("gone")
               and now - float(v.get("pidAt") or 0) >= ext_store.EXT_PID_EVERY_S]
        for k, _p, _s in due:
            ext_store._ext[k]["pidAt"] = now
    dead = {k: pid for k, pid, ps in due if ext_store._pid_gone(pid, ps)}   # outside the lock: may run `ps`
    changed = runs = False
    with ext_store._ext_lock:
        for k, v in list(ext_store._ext.items()):
            try:
                last = float(v.get("lastSeen") or 0)
            except (TypeError, ValueError):
                last = 0.0
            if not v.get("gone"):
                why = ""
                if k in dead and v.get("pid") == dead[k] and last <= now:
                    why = "pid"
                elif not v.get("pid") and v.get("state") in ("think", "tool") and now - last > ext_store.EXT_SILENT_S:
                    why = "silent"
                if not why and not v.get("pid") and v.get("state") == "wait" and not v.get("blocked") \
                        and now - last > ext_store.PIDLESS_IDLE_SEC:
                    v["state"] = "done"
                    changed = True
                if why:
                    v.update(goneFrom=v.get("state") or "", state="gone", goneWhy=why, blocked=False, tool="",
                             gone=now if why == "pid" else last + ext_store.EXT_SILENT_S)
                    changed = True
                    if v.get("parent"):
                        ext_store._run_note_locked(k[0], k[1], v, "Gone", last)
                        runs = True
            if v.get("gone") and now - float(v["gone"]) > ext_store.EXT_GONE_GRACE_S:
                ext_store._run_note_locked(k[0], k[1], v, "SessionEnd", last)
                ext_store._end_locked(k, v, float(v["gone"]), v.get("goneWhy") or "pid")
                changed = True
                runs = runs or bool(v.get("parent"))
        if runs:
            ext_store._runs_save_locked()
        if changed:
            ext_store._ext_save_locked()


def ext_dismiss(sid):
    """Person dismissed a pid-less pending row (liveness unknown, never pruned): drop it from the store like a SessionEnd.
    ⚠pid rows are refused — ext_gone_check owns their exit. A live CLI's next event re-creates the row. -> rows removed."""
    if not isinstance(sid, str) or not ext_store._sid_ok(sid):
        return 0
    n = 0
    with ext_store._ext_lock:
        now = ext_store.time.time()
        if not any(k[1] == sid for k in ext_store._ext):   # a record-file-only row (Codex rollout, Cursor/Copilot folder): hide it for its window
            for p in ("codex", "cursor", "copilot", "pi"):
                ext_store._ended_note_locked((p, sid), now)
            n += 1
        for k, v in list(ext_store._ext.items()):
            if k[1] == sid and not v.get("pid") and ext_store._pending(v):
                ext_store._ext.pop(k, None)
                ext_store._ended_note_locked(k, now)
                if ext_store._run_note_locked(k[0], k[1], v, "SessionEnd", float(v.get("lastSeen") or 0)):
                    ext_store._runs_save_locked()
                n += 1
        if n:
            ext_store._ext_save_locked()
    return n
