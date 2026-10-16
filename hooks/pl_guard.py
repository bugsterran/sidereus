#!/usr/bin/env python3
"""Pipeline guards, called by hooks/pl_flow.py main(): a pipeline file's top-level `guards` object is enforced.

guards.requireGates = [stage title]: a `git commit` (main or subagent, Claude Code) while this session's open run of
  that project is unfinished on them is denied, and so is a `[pl-skip:<name>/<stage>]` of one of them. A stage counts
  when it is done (not skipped) and evidence.jsonl has an rc=0 row of its gate's mode at or after the stage's last
  pass start, with no later rc!=0 row of that mode.
guards.maxLoopBacks = n: once the run took n loop-backs, the next loop-back dispatch is denied and the FAIL hand-off
  says «loop budget n reached: stop and report».
Stop marker <data dir>/plstop/<sid>.json (Sidereus «Stop»): a tagged dispatch of that run is denied (code stop) and the
  run is ended; its Post hand-off becomes the stop line. Bash markers and [pl-skip:] are not affected.
Reads stage titles, gates, run times and evidence rc/mode/ts only -- never commands, descriptions or task text.
Fail-open: any problem = no guard (the flow hook runs as before). Stdlib only, Python 3.9, no sidereus imports.
"""
import contextlib
import io
import json
import os
import re
import sys

# Gate command -> evidence mode; first match wins. ⚠Same table as sidereus/pipeline_schema.py GATE_MODES and the runner's
# validate block (.claude/workflows/pipeline.js); tests/test_pl_guard.py pins all three equal.
GATE_MODES = (
    ("(?:^|[\\s/])check\\.sh\\s+--fast(?![\\w-])", "fast"),
    ("(?:^|[\\s/])check\\.sh\\s+--full(?![\\w-])", "full"),
    ("arch_checks\\.py(?=.*\\s--verify(?![\\w-])).*\\s--category[\\s=]+security(?![\\w-])", "checks-security"),
)
LOOP_MAX = 10
EV_FILE = None             # None = $SIDEREUS_EVIDENCE or <flow DATA_DIR>/evidence.jsonl (same rule as scripts/check.sh)
EV_READ_MAX = 512 * 1024   # tail only, like sidereus/harness_evidence.py


def gate_mode(gate):
    """Evidence mode recorded by `gate`'s run, or None (an ungraded gate)."""
    if not isinstance(gate, str):
        return None
    for pat, mode in GATE_MODES:
        if re.search(pat, gate):
            return mode
    return None


def guards_of(proj, name):
    """({"req": [titles], "max": int|None}, stages) from <proj>/.claude/pipelines/<name>.json, or None (none/malformed)."""
    try:
        with open(os.path.join(proj, ".claude", "pipelines", name + ".json"), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    g = d.get("guards") if isinstance(d, dict) else None
    if not isinstance(g, dict):
        return None
    req = g.get("requireGates")
    req = [t for t in req if isinstance(t, str)] if isinstance(req, list) else []
    mx = g.get("maxLoopBacks")
    mx = mx if isinstance(mx, int) and not isinstance(mx, bool) and 1 <= mx <= LOOP_MAX else None
    st = [s for s in d.get("stages") or [] if isinstance(s, dict) and isinstance(s.get("title"), str)]
    return ({"req": req, "max": mx}, st) if (req or mx) and st else None


def _ev_rows(flow, repos):
    """Newest-first [(ts, mode, rc)] of v1 check rows whose repo is in `repos`; [] when unreadable."""
    p = EV_FILE or os.environ.get("SIDEREUS_EVIDENCE") or os.path.join(flow.DATA_DIR, "evidence.jsonl")
    try:
        with open(p, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - EV_READ_MAX))
            lines = f.read(EV_READ_MAX).split(b"\n")
    except OSError:
        return []
    if size > EV_READ_MAX:
        lines = lines[1:]   # ⚠first line of a mid-file seek is partial
    out = []
    for ln in reversed(lines):
        try:
            d = json.loads(ln.decode("utf-8"))
        except ValueError:
            continue
        if not isinstance(d, dict) or d.get("v") != 1 or d.get("kind") != "check" or d.get("repo") not in repos:
            continue
        ts, rc, mode = d.get("ts"), d.get("rc"), d.get("mode")
        if isinstance(ts, (int, float)) and isinstance(rc, int) and not isinstance(rc, bool) and isinstance(mode, str):
            out.append((float(ts), mode, rc))
    return out


def _repos(flow, proj):
    p = os.path.realpath(proj)
    g = flow._git_root(p)
    return {p, os.path.realpath(g)} if g else {p}


def _missing(flow, r, proj, req, stages):
    """[(title, why)] of required stages run `r` has not passed with evidence."""
    rows = _ev_rows(flow, _repos(flow, proj))
    gates = {s["title"]: s.get("gate") for s in stages}
    out = []
    for t in req:
        e = (r.get("st") or {}).get(t)
        e = e if isinstance(e, dict) else {}
        mode = gate_mode(gates.get(t))
        if e.get("s") == "skip":
            out.append((t, "skipped"))
            continue
        if e.get("s") != "done":
            out.append((t, "not passed (%s)" % (e.get("s") or "not run")))
            continue
        start = e.get("p0", e.get("t0"))
        start = int(start) if isinstance(start, (int, float)) else 0   # ⚠evidence ts is whole seconds
        mine = [x for x in rows if x[1] == mode and x[0] >= start]
        if not mode or not mine:
            out.append((t, "no %s evidence since its last pass started" % (mode or "graded")))
        elif mine[0][2] != 0:
            out.append((t, "latest %s gate run failed (rc=%d)" % (mode, mine[0][2])))
    return out


def _commit(flow, ev, now):
    """Deny reason for a `git commit` while an open run of this project lacks its required gates, else None."""
    cmd = flow._shell_cmd(ev.get("tool_input"))
    m = flow._COMMIT_RE.search(cmd or "")
    sid, cwd = ev.get("session_id"), ev.get("cwd")
    if not m or "--dry-run" in cmd:
        return None
    dirs = [cwd]
    if m.group(1):
        c = m.group(1).strip("\"'")
        dirs.append(c if os.path.isabs(c) else os.path.join(cwd, c))
    dirs = [os.path.realpath(x) for x in dirs]
    dirs += [g for g in (flow._git_root(x) for x in dirs) if g]
    runs = flow._load(os.path.join(flow.MARK_DIR, sid + ".runs.json"))["runs"]
    msgs = []
    for name, r in sorted(runs.items()):
        proj = r.get("proj") if isinstance(r, dict) else None
        if not isinstance(proj, str) or not proj or not flow._is_open(r, now) or flow._apply_off(proj):
            continue
        p = os.path.realpath(proj)
        if not any(x == p or x.startswith(p + os.sep) for x in dirs):
            continue
        g = guards_of(proj, name)
        if not g or not g[0]["req"]:
            continue
        miss = _missing(flow, r, proj, g[0]["req"], g[1])
        if miss:
            gates = {s["title"]: s.get("gate") or "" for s in g[1]}
            msgs.append("%s: %s" % (name, "; ".join("%s (gate %s): %s" % (t, gates.get(t) or "-", w) for t, w in miss)))
    if not msgs:
        return None
    return ("Commit blocked by pipeline guards.requireGates — %s. Run each listed stage tagged [pl:<pipeline>/<stage>] "
            "and its gate until it records rc=0, then commit." % " | ".join(msgs))


def _skip(flow, ev, path, desc):
    """Deny reason for a `[pl-skip:]` naming a requireGates stage, else None."""
    for m in flow.SKIP_TAG.finditer(desc):
        name, title = m.group(1), flow._ren(m.group(2).strip())
        old = flow._load(path)["runs"].get(name)
        keep = old.get("proj") if isinstance(old, dict) and not old.get("end") else None
        proj = flow._project(ev, "Bash", name, title, keep)
        if not proj or flow._apply_off(proj):
            continue
        g = guards_of(proj, name)
        if g and title in g[0]["req"]:
            return ("%s is a required gate of %s (guards.requireGates): it cannot be skipped. Run it tagged "
                    "[pl:%s/%s] and pass its gate." % (title, name, name, title))
    return None


def _loops(r):
    return sum(int(v) for v in (r.get("loops") or {}).values() if isinstance(v, (int, float)))


def _budget(flow, path, name, now):
    """(max, run, stages) when the open run `name` has used its loop budget, else None."""
    r = flow._load(path)["runs"].get(name)
    if not flow._is_open(r, now) or not isinstance(r.get("proj"), str) or flow._apply_off(r["proj"]):
        return None
    g = guards_of(r["proj"], name)
    if not g or not g[0]["max"] or _loops(r) < g[0]["max"]:
        return None
    return g[0]["max"], r, g[1]


def _loopback(flow, path, name, title, now):
    """Deny reason for a loop-back dispatch past the run's loop budget, else None."""
    b = _budget(flow, path, name, now)
    if not b:
        return None
    mx, r, st = b
    st = [flow._ren_stage(s) for s in st]
    t, c = flow._idx(st, title), flow._idx(st, r.get("cur") or "")
    f = flow._onfail(st[c]) if c >= 0 else None
    if 0 <= t < c and f and f["goto"] == title:
        return "loop budget %d reached (guards.maxLoopBacks): stop and report instead of [pl:%s/%s]." % (mx, name, title)
    return None


# Stop marker <flow DATA_DIR>/plstop/<sid>.json = {name: {at, mid, of}}, written by Sidereus with its mailbox stop
# instruction. It is a mailbox-dir signal like PAUSED that this session's own hook reads: Sidereus kills nothing,
# the session simply cannot dispatch the stopped run's next stage.
STOP_PENDING_S = 1800      # with no open run, a stop this recent still applies (the next tag would open a new run)
STOP_READ_MAX = 4096
_STOP_ID = re.compile(r"^[\w.:-]{1,64}$")


def _stop_of(flow, sid, name):
    """(at, of) of the stop entry for pipeline `name` in this session's marker, else None; any problem = None."""
    try:
        with open(os.path.join(flow.DATA_DIR, "plstop", sid + ".json"), "rb") as f:
            b = f.read(STOP_READ_MAX + 1)
        d = json.loads(b.decode("utf-8")) if len(b) <= STOP_READ_MAX else None
    except Exception:
        return None
    e = d.get(name) if isinstance(d, dict) else None
    at = e.get("at") if isinstance(e, dict) else None
    if not isinstance(at, (int, float)) or isinstance(at, bool):
        return None
    of = e.get("of")
    return float(at), (of if isinstance(of, str) and _STOP_ID.match(of) else "-")


def _stop_active(flow, path, sid, name, now):
    """(at, of, run) when the stop applies: the open run started at/before it, or no open run and it is recent."""
    s = _stop_of(flow, sid, name)
    if not s:
        return None
    r = flow._load(path)["runs"].get(name)
    if flow._is_open(r, now):
        return (s[0], s[1], r) if float(r.get("t0") or 0) <= s[0] else None
    return (s[0], s[1], None) if 0 <= now - s[0] <= STOP_PENDING_S else None


def _stop_line(name, of):
    return ("Run %s was stopped from Sidereus (request %s): dispatch no further stages; report what was done and end."
            % (name, of))


def _stop(flow, path, sid, name, title, now):
    """Deny reason for a dispatch of a stopped run; ends the open run (stop/end, cur stage done) and notes the deny."""
    a = _stop_active(flow, path, sid, name, now)
    if not a:
        return None
    if a[2] is not None and os.path.isfile(path):
        try:
            with flow._Lock(path) as lk:
                if lk.ok:
                    d = flow._load(path)
                    r = d["runs"].get(name)
                    if flow._is_open(r, now):
                        cur = r.get("cur") or ""
                        e = (r.get("st") or {}).get(cur)
                        if cur and isinstance(e, dict) and e.get("s") == "run":
                            flow._mark(r, cur, "done", now)
                        flow._deny_note(r, title, "stop", now)
                        r["stop"], r["end"] = a[0], now
                        flow._save(path, d)
        except Exception:
            pass   # ⚠the deny stands even when the runs file cannot be updated
    return _stop_line(name, a[1])


def check(plat, ev, flow):
    """Deny reason for this Pre event, or None. Claude Code only (other CLIs have no verified deny contract)."""
    if plat != "cc" or ev.get("hook_event_name") != "PreToolUse":
        return None
    sid, cwd, tool = ev.get("session_id"), ev.get("cwd"), ev.get("tool_name")
    if not (isinstance(sid, str) and flow.SID.match(sid) and isinstance(cwd, str) and os.path.isabs(cwd)):
        return None
    ti = ev.get("tool_input") if isinstance(ev.get("tool_input"), dict) else {}
    path = os.path.join(flow.MARK_DIR, sid + ".runs.json")
    now = flow._now()
    if tool in ("Bash", "PowerShell"):
        desc = ti.get("description") if isinstance(ti.get("description"), str) else ""
        return (_skip(flow, ev, path, desc) if "[pl-skip:" in desc else None) or _commit(flow, ev, now)
    if tool in flow.DISPATCH:
        desc = ti.get(flow.FIELD[tool])
        m = flow.TAG.search(desc) if isinstance(desc, str) else None
        if m:
            name, title = m.group(1), flow._ren(m.group(2).strip())
            return _stop(flow, path, sid, name, title, now) or _loopback(flow, path, name, title, now)
    return None


def _post_tag(plat, ev, flow):
    """(sid, pipeline name) of a cc tagged dispatch PostToolUse, else None."""
    if plat != "cc" or ev.get("hook_event_name") != "PostToolUse" or ev.get("tool_name") not in flow.DISPATCH:
        return None
    sid = ev.get("session_id")
    ti = ev.get("tool_input") if isinstance(ev.get("tool_input"), dict) else {}
    desc = ti.get(flow.FIELD[ev["tool_name"]])
    m = flow.TAG.search(desc) if isinstance(desc, str) else None
    return (sid, m.group(1)) if m and isinstance(sid, str) and flow.SID.match(sid) else None


def _post_budget(plat, ev, flow):
    """Loop budget for a cc dispatch PostToolUse of an open run that used it up, else None."""
    t = _post_tag(plat, ev, flow)
    b = _budget(flow, os.path.join(flow.MARK_DIR, t[0] + ".runs.json"), t[1], flow._now()) if t else None
    return b[0] if b else None


def _post_stop(plat, ev, flow):
    """Stop line for a cc dispatch PostToolUse of a stopped run, else None."""
    t = _post_tag(plat, ev, flow)
    a = _stop_active(flow, os.path.join(flow.MARK_DIR, t[0] + ".runs.json"), t[0], t[1], flow._now()) if t else None
    return _stop_line(t[1], a[1]) if a else None


def _rewrite(txt, mx):
    """The flow hook's Post output with every FAIL line replaced by the loop-budget stop."""
    d = json.loads(txt)
    h = d["hookSpecificOutput"]
    h["additionalContext"] = "\n".join(
        "FAIL → loop budget %d reached: stop and report." % mx if x.startswith("FAIL") else x
        for x in h["additionalContext"].split("\n"))
    return json.dumps(d, ensure_ascii=False)


def _rewrite_stop(txt, line):
    """The flow hook's Post output with the PASS/FAIL hand-off replaced by the single stop line."""
    d = json.loads(txt)
    h = d["hookSpecificOutput"]
    out = []
    for x in h["additionalContext"].split("\n"):
        if x.startswith(("PASS", "FAIL", "When it finishes")):
            if line not in out:
                out.append(line)
        else:
            out.append(x)
    h["additionalContext"] = "\n".join(out)
    return json.dumps(d, ensure_ascii=False)


def run(plat, ev, flow, inner):
    """pl_flow main()'s entry: guard deny, else `inner(plat, ev)` (with the loop-budget text on Post).
    ⚠Guard errors never block or change the flow; `inner` runs exactly once and its own errors propagate."""
    try:
        why = check(plat, ev, flow)
    except Exception:
        why = None
    if why:
        return flow._deny(why)
    try:
        sl = _post_stop(plat, ev, flow)
    except Exception:
        sl = None
    try:
        mx = None if sl else _post_budget(plat, ev, flow)
    except Exception:
        mx = None
    if not (sl or mx):
        return inner(plat, ev)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            return inner(plat, ev)
    finally:
        txt = buf.getvalue()
        try:
            txt = (_rewrite_stop(txt, sl) if sl else _rewrite(txt, mx)) if txt else txt
        except Exception:
            pass
        try:
            sys.stdout.reconfigure(encoding="utf-8")   # ⚠Windows codepage cannot encode Korean deny reasons
        except Exception:
            pass
        sys.stdout.write(txt)
