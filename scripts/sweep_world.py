#!/usr/bin/env python3
"""Sandbox «world» for live verification sweeps: a fake home, Claude config dir, data dir and projects under one --out.

  python3 scripts/sweep_world.py build --out DIR [--port N] [--now EPOCH]
  python3 scripts/sweep_world.py append-ask --out DIR [--now EPOCH]

build writes DIR/{home,cc,data,proj} and prints the env lines + the launch line; append-ask appends the answer of case (b).
Cases: (a) a project whose only pipeline file is invalid · (b) an AskUserQuestion pushed out of the 400 KB tail ·
(c) a non-ASCII project folder + a Windows-shaped `C--Users-demo-app` folder · (e) external CLI hook files under home.
Records are metadata only (empty text, tool input {}, empty tool_result), like tests/fixtures/states/README.md.
"""
import argparse
import json
import os
import shlex
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from sidereus import ident  # noqa: E402  (slug rule lives in one place)

ASK_SID = "5ee90000-0000-4000-8000-0000000000b1"  # leakscan: allow (synthetic)
ASK_ID = "toolu_sweep_ask_b1"
SLUG_SID = "5ee90000-0000-4000-8000-0000000000c1"  # leakscan: allow (synthetic)
WIN_SID = "5ee90000-0000-4000-8000-0000000000c2"  # leakscan: allow (synthetic)
BAD_SID = "5ee90000-0000-4000-8000-0000000000a1"  # leakscan: allow (synthetic)
FILL_BYTES = 420_000          # > the 400 KB tail parse._parse_transcript reads
UNICODE_DIR = "\ud504\ub85c\uc81d\ud2b8-caf\u00e9"   # non-ASCII folder name (escaped: no Hangul in source)
WIN_SLUG = "C--Users-demo-app"
WIN_CWD = "C:\\Users\\demo\\app"
_TOOL_DIRS = (".claude", ".codex", ".cursor", ".gemini", ".copilot")


def _homes():
    out = {os.path.realpath(os.path.expanduser("~"))}
    try:
        import pwd
        out.add(os.path.realpath(pwd.getpwuid(os.getuid()).pw_dir))   # ⚠not ident._real_home: that honours the sandbox override
    except (ImportError, KeyError):
        pass
    return out


def check_out(out):
    """Error text, or "" when --out is safe: empty or missing, and not inside a real tool config dir."""
    r = os.path.realpath(out)
    for h in _homes():
        for d in _TOOL_DIRS:
            t = os.path.realpath(os.path.join(h, d))   # dotfile setups symlink these dirs
            if r == t or r.startswith(t + os.sep):
                return "refused: %s is inside %s" % (out, t)
    if os.path.lexists(out) and (not os.path.isdir(out) or os.listdir(out)):
        return "refused: %s exists and is not empty" % out
    return ""


def _iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + ".000Z"


def _rec(sid, cwd, t, typ, n, **kw):
    d = {"cwd": cwd, "sessionId": sid, "timestamp": _iso(t), "type": typ, "uuid": "%s-%06d" % (sid[:8], n)}
    d.update(kw)
    return d


def _user(sid, cwd, t, n, content=""):
    return _rec(sid, cwd, t, "user", n, message={"role": "user", "content": content}, permissionMode="default")


def _asst(sid, cwd, t, n, content, stop="end_turn"):
    return _rec(sid, cwd, t, "assistant", n, message={"id": "msg_%06d" % n, "role": "assistant",
                                                       "content": content, "stop_reason": stop})


def _turn_end(sid, cwd, t, n):
    return _rec(sid, cwd, t, "system", n, subtype="turn_duration")


def _line(d):
    return json.dumps(d, sort_keys=True, separators=(", ", ": ")) + "\n"


def _write(p, text, mtime):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.utime(p, (mtime, mtime))


def _done_session(sid, cwd, t):
    return "".join(_line(r) for r in (_user(sid, cwd, t - 60, 1), _asst(sid, cwd, t - 40, 2, [{"type": "text", "text": ""}]),
                                       _turn_end(sid, cwd, t - 40, 3)))


def paths(out):
    o = os.path.realpath(out)
    p = {k: os.path.join(o, k) for k in ("home", "cc", "data", "proj")}
    p["ask_cwd"] = os.path.join(p["proj"], "ask")
    p["ask"] = os.path.join(p["cc"], "projects", ident._slug(p["ask_cwd"]), ASK_SID + ".jsonl")
    return p


def _ask_text(sid, cwd, now):
    t0 = now - 600
    rows = [_user(sid, cwd, t0, 1),
            _asst(sid, cwd, t0 + 10, 2, [{"type": "tool_use", "id": ASK_ID, "name": "AskUserQuestion", "input": {}}],
                  stop="tool_use")]
    text = "".join(_line(r) for r in rows)
    n, size = 3, len(text.encode("utf-8"))
    parts = [text]
    while size < FILL_BYTES:      # ⚠generated, not committed: a 420 KB fixture would bloat the repo
        ln = _line(_rec(sid, cwd, t0 + 20, "progress", n, data={}))
        parts.append(ln)
        size += len(ln.encode("utf-8"))
        n += 1
    return "".join(parts)


def _hook_files(home):
    cmd = [{"type": "command", "command": "true"}]
    return {os.path.join(home, ".cursor", "hooks.json"): {"version": 1, "hooks": {"stop": [{"command": "true"}]}},
            os.path.join(home, ".codex", "hooks.json"): {"hooks": {"Stop": [{"hooks": cmd}]}},
            os.path.join(home, ".gemini", "settings.json"): {"hooks": {"AfterAgent": [{"hooks": cmd}]}},
            os.path.join(home, ".copilot", "hooks", "sidereus.json"): {"version": 1, "hooks": {}}}


def build(out, port=8899, now=None):
    """Write the world under `out` and return the printed lines (env + launch). Raises ValueError when refused."""
    err = check_out(out)
    if err:
        raise ValueError(err)
    now = int(time.time() if now is None else now)
    p = paths(out)
    for k in ("home", "cc", "data", "proj"):
        os.makedirs(p[k], exist_ok=True)
    proj = p["proj"]
    # (a) the project's only pipeline file is invalid JSON
    bad = os.path.join(proj, "onlybad")
    _write(os.path.join(bad, ".claude", "pipelines", "broken.json"), '{"title": "broken", "stages": [\n', now)
    _write(os.path.join(p["cc"], "projects", ident._slug(bad), BAD_SID + ".jsonl"), _done_session(BAD_SID, bad, now - 300), now - 300)
    # (b) open ask, then > 400 KB of empty records; the answer comes from append_ask
    os.makedirs(p["ask_cwd"], exist_ok=True)
    _write(p["ask"], _ask_text(ASK_SID, p["ask_cwd"], now), now - 500)
    # (c) non-ASCII folder name (slug via ident._slug) and a Windows-shaped slug folder
    uni = os.path.join(proj, UNICODE_DIR)
    os.makedirs(uni, exist_ok=True)
    _write(os.path.join(p["cc"], "projects", ident._slug(uni), SLUG_SID + ".jsonl"), _done_session(SLUG_SID, uni, now - 200), now - 200)
    _write(os.path.join(p["cc"], "projects", WIN_SLUG, WIN_SID + ".jsonl"), _done_session(WIN_SID, WIN_CWD, now - 250), now - 250)
    # (e) external CLI hook files, each with one user entry (Connect must keep it)
    for fp, d in sorted(_hook_files(p["home"]).items()):
        _write(fp, json.dumps(d, indent=2, sort_keys=True) + "\n", now)
    projs = {k: {} for k in sorted((bad, p["ask_cwd"], uni))}
    _write(os.path.join(p["cc"], ".claude.json"), json.dumps({"projects": projs}, indent=1, sort_keys=True, ensure_ascii=False) + "\n", now)
    return lines(out, port)


def lines(out, port):
    p = paths(out)
    env = (("HOME", p["home"]), ("CLAUDE_CONFIG_DIR", p["cc"]), ("MAILBOX_DIR", p["data"]), ("SIDEREUS_USER_HOME", p["home"]))
    # ⚠the per-CLI home overrides beat SIDEREUS_USER_HOME, so a set one would point the sandbox at real files
    return ["unset CODEX_HOME GEMINI_CLI_HOME COPILOT_HOME"] + ["export %s=%s" % (k, shlex.quote(v)) for k, v in env] + \
        ["python3 %s start --port %d" % (shlex.quote(os.path.join(REPO, "sidereus_cli.py")), int(port))]


def append_ask(out, now=None):
    """Append the tool_result answering case (b)'s ask (empty content). Returns the transcript path."""
    now = int(time.time() if now is None else now)
    p = paths(out)
    if not os.path.isfile(p["ask"]):
        raise ValueError("no case (b) transcript under %s (run build first)" % out)
    r = _user(ASK_SID, p["ask_cwd"], now - 30, 999999, [{"type": "tool_result", "tool_use_id": ASK_ID, "content": ""}])
    with open(p["ask"], "a", encoding="utf-8", newline="\n") as f:
        f.write(_line(r))
    os.utime(p["ask"], (now - 30, now - 30))
    return p["ask"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd")
    b = sub.add_parser("build")
    b.add_argument("--out", required=True)
    b.add_argument("--port", type=int, default=8899)
    b.add_argument("--now", type=int, default=None)
    a = sub.add_parser("append-ask")
    a.add_argument("--out", required=True)
    a.add_argument("--now", type=int, default=None)
    ns = ap.parse_args(argv)
    try:
        if ns.cmd == "build":
            if not 1024 <= ns.port <= 65535 or ns.port == 8799:
                raise ValueError("bad --port (8799 is the live viewer)")
            print("\n".join(build(ns.out, ns.port, ns.now)))
        elif ns.cmd == "append-ask":
            print(append_ask(ns.out, ns.now))
        else:
            ap.print_help()
            return 2
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
