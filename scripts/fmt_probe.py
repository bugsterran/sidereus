#!/usr/bin/python3
"""Record-format probe: runs Sidereus's own parsers over the newest real Claude Code / Codex / Gemini session files
and fails loudly when a field we depend on stops coming out (an upstream format change).

  /usr/bin/python3 scripts/fmt_probe.py [--n N] [--json]

Exit 0 = every installed platform parsed · 1 = a field came out empty on all N newest files · 2 = setup error.
A platform with no files is reported «skip», not a failure.
⚠Reads live files under ~/.claude, ~/.codex, ~/.gemini — never run from check.sh / tests/run.sh (tests use fixtures).
Metadata only: the output holds field names and counts, never record contents.
"""
import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _newest(paths, n):
    def mt(p):
        try:
            return os.path.getmtime(p)
        except OSError:
            return 0
    return sorted(paths, key=mt, reverse=True)[:n]


def _judge(name, files, fields, extract):
    """fields: {field: predicate(parsed) -> bool}. A field passes if ANY file yields it —
    ★one odd file (a session that never got an answer, a resumed stub) must not raise a false alarm."""
    if not files:
        return {"plat": name, "status": "skip", "files": 0, "missing": []}
    got = {k: 0 for k in fields}
    for p in files:
        try:
            r = extract(p)
        except Exception:
            r = None
        if not r:
            continue
        for k, ok in fields.items():
            try:
                if ok(r):
                    got[k] += 1
            except Exception:
                pass
    missing = [k for k, c in got.items() if c == 0]
    return {"plat": name, "status": "fail" if missing else "ok", "files": len(files),
            "missing": missing, "hits": got}


def check_claude(projects_dir, n, parse):
    files = _newest(glob.glob(os.path.join(projects_dir, "*", "*.jsonl")), n)
    return _judge("claude", files, {
        "sessionId": lambda r: bool(r.get("sid")),
        "cwd": lambda r: bool(r.get("cwd")),
        "model": lambda r: bool(r.get("model")),
        "timestamp": lambda r: (r.get("actAt") or 0) > 0,
        "usage": lambda r: (r.get("ctx") or 0) > 0,
    }, parse._parse_transcript)


def _msgs_field(i):
    return lambda r: any(isinstance(v, tuple) and len(v) > i and v[i] for v in (r.get("msgs") or {}).values())


def check_codex(codex_root, n, mod):
    files = _newest(mod._files(codex_root), n)
    return _judge("codex", files, {
        "session_meta.id": lambda r: bool((r.get("head") or {}).get("id")),
        "session_meta.cwd": lambda r: bool((r.get("head") or {}).get("cwd")),
        "timestamp": lambda r: bool((r.get("head") or {}).get("start")),
        "token_count.last_token_usage": lambda r: bool(r.get("msgs")),
        "turn_context.model": _msgs_field(5),
    }, mod.read)


def check_gemini(gemini_root, n, mod):
    files = _newest(mod._files(gemini_root), n)
    return _judge("gemini", files, {
        "sessionId": lambda r: bool((r.get("head") or {}).get("sessionId")),
        "projectHash": lambda r: bool((r.get("head") or {}).get("projectHash")),
        "startTime": lambda r: bool((r.get("head") or {}).get("startTime")),
        "messages.tokens": lambda r: bool(r.get("msgs")),
        "messages.model": _msgs_field(5),
    }, mod.read)


def run(n, roots=None):
    sys.path.insert(0, ROOT)
    from tests._load import sidereus
    parse, cx, gm, tr = sidereus("parse"), sidereus("plat_codex"), sidereus("plat_gemini"), sidereus("transcript")
    roots = roots or {"claude": tr.CLAUDE_PROJECTS, "codex": cx.root(), "gemini": gm.root()}
    return [check_claude(roots["claude"], n, parse),
            check_codex(roots["codex"], n, cx),
            check_gemini(roots["gemini"], n, gm)]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=8, help="newest files per platform (default 8)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        res = run(max(1, a.n))
    except Exception as e:
        print("setup error: %s" % e, file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(res, ensure_ascii=False))
    else:
        for r in res:
            line = "  %-5s %-7s %d file(s)" % (r["status"], r["plat"], r["files"])
            if r["missing"]:
                line += "  — never parsed: " + ", ".join(r["missing"])
            print(line)
    return 1 if any(r["status"] == "fail" for r in res) else 0


if __name__ == "__main__":
    sys.exit(main())
