"""Demo GET routing for `chat_server.py --demo` (split out of sidereus/demo.py to keep it under the size cap).

Owns `respond(world, path, u)` — maps each /api GET to a `demo.World` method or a fixture payload — and its helpers.
⚠Imported only by sidereus/demo.py (lazy, under --demo). Never import sidereus.demo from here (cycle).
⚠Keep it 100% synthetic — tests/test_demo.py scans every response against a denylist.
"""
import time
from urllib.parse import parse_qs

from sidereus.demo_data import HOOKS_CONNECT, MSG_FIRST
from sidereus.demo_rel import _ARCH_COMMIT, _ARCH_MODS, demo_arch, demo_file, demo_src, demo_tree   # structure arch/tree payloads
from sidereus.verdict_guide import load as verdict_guide
from sidereus.demo_tools import _demo_diag, _demo_eval, _demo_harness, _demo_pl_evidence, _demo_pipelines, _demo_prefs, _demo_tools   # tools/harness/prefs/diag payloads


# ─────────────────────────────────────────────── HTTP glue
def _q(u, k, d=""):
    return (parse_qs(u.query).get(k) or [d])[0]


def _num(s, d):
    try:
        return float(s)
    except (TypeError, ValueError):
        return d


def respond(world, path, u):
    """(status, payload) for a demo GET. Unknown /api paths get an empty-but-valid answer."""
    w = world
    w._req.now = max(int(time.time()), w.a)   # ⚠one clock per request (per thread): a second tick mid-build split running `end` ties and reordered timeline groups
    if path == "/api/state":
        since = _q(u, "since", "0")     # ⚠ns epoch (19 digits) — int(), never float(), or the last message repeats
        return 200, w.state(int(since) if since.isdigit() else 0,
                            max(1, min(300, int(_num(_q(u, "cards", "50"), 50)))))
    if path == "/api/messages":
        after, before, n = _q(u, "after", "0"), _q(u, "before", "0"), _q(u, "n", str(MSG_FIRST))   # no n = bus.MSG_RANGE_DEFAULT
        if not (after.isdigit() and before.isdigit() and n.isdigit()):   # ⚠ns epochs — int() only, like the live route
            return 400, {"error": "bad cursor"}
        return 200, {"messages": w.messages_range(int(after), int(before) or None, int(n))}
    if path == "/api/cards":
        return 200, {"cards": w.cards()}
    if path == "/api/todo":   # writes (/api/todo/add|set) stay the POST no-op
        return w.todo_get(_q(u, "cwd"))
    if path == "/api/agents/timeline":
        return 200, w.timeline(max(1.0, min(48.0, _num(_q(u, "hours", "12"), 12.0))))
    if path in ("/api/quota/burn", "/api/live"):   # no-arg panels; merged to stay under the 620-line cap
        return 200, w.quota_burn() if path == "/api/quota/burn" else w.live()
    if path == "/api/wkuse":
        return 200, w.wkuse(int(_num(_q(u, "range", "7"), 7)), _q(u, "acct"))
    if path == "/api/branches":
        return w.branches(_q(u, "cwd"))
    if path == "/api/git/links":
        return 200, w.git_links(_q(u, "repo"), set(x for x in _q(u, "shas").split(",") if x))
    if path == "/api/git/commit":
        return w.git_commit(_q(u, "repo"), _q(u, "sha"))
    if path == "/api/git/owners":
        return 200, w.git_owners(_q(u, "cwd"))
    if path == "/api/git/wtfiles":
        return 200, w.git_wtfiles(_q(u, "cwd"))
    if path == "/api/git/diff":
        if _q(u, "view") == "rail":
            return 200, w.git_rail(_q(u, "cwd"), _q(u, "base", "auto"), _q(u, "sid"))
        return 200, w.git_diff(_q(u, "cwd"))
    if path == "/api/review":
        return 200, w.review_files(_q(u, "cwd"), _q(u, "sid"))
    if path == "/api/history":
        return 200, w.history(int(_num(_q(u, "days", "7"), 7)))
    if path == "/api/history/units":
        return 200, w.history_units(_q(u, "sid"))
    if path == "/api/sessions/recent":
        return 200, w.recent(max(1, min(30, int(_num(_q(u, "days", "7"), 7)))))
    if path == "/api/retro":
        return 200, w.retro(max(1, min(30, int(_num(_q(u, "days", "7"), 7)))), _q(u, "acct"))
    if path == "/api/agent/work":
        return 200, w.agent_work(_q(u, "tid"), _q(u, "sid"))
    if path == "/api/session/work":
        return 200, w.session_work(_q(u, "sid") or w.sess[0]["sid"])
    if path == "/api/ext/work":   # ⚠the bare {"ok": True} fallback lacks `steps` — every external work popup threw
        return 200, w.ext_work(_q(u, "plat"), _q(u, "sid"))
    if path == "/api/session/context":
        return 200, w.session_context(_q(u, "cwd"))
    if path.startswith("/api/tools"):
        return _demo_tools(w.a, path, _q(u, "id"))
    if path == "/api/pipelines":
        return _demo_pipelines(_q(u, "proj"), w.by["web"]["cwd"], w.by["bill"]["cwd"])
    if path == "/api/pipelines/eval":
        return _demo_eval(_q(u, "proj"), w.by["web"]["cwd"], _q(u, "name"))
    if path == "/api/verdict-guide":   # static repo docs (docs/verdicts), no user data
        return 200, verdict_guide(_q(u, "lang", "en"))
    if path == "/api/harness/evidence":   # same body as harness_plat.harness_evidence_only (pipeline stage result lines)
        return 200, _demo_pl_evidence(w.a)
    if path.startswith("/api/harness"):
        return _demo_harness(w.a, path)
    if path == "/api/hooks/connect":   # header «CLI hooks» chip; the POST stays the demo no-op
        return 200, {"ok": True, "plats": [dict(x) for x in HOOKS_CONNECT]}
    if path == "/api/prefs":     # ⚠the bare {"ok": True} fallback lacks `keys` — «Preferences» showed a red read error
        return 200, _demo_prefs()
    if path == "/api/diag":
        return 200, _demo_diag()
    if path == "/api/structure":
        return 200, {"ok": False, "msg": "The Size view is not available in demo mode"}   # Architecture view works in demo
    if path == "/api/arch":
        return 200, demo_arch(w.a)
    if path == "/api/arch/files":   # ⚠the bare {"ok": True} fallback left module detail «Files» empty
        return 200, demo_arch_files(_q(u, "id"))
    if path == "/api/structure/src":
        return 200, demo_src(_q(u, "path"), _q(u, "file"), _q(u, "line", "1"), _q(u, "lines", "0"))
    if path == "/api/structure/tree":
        return 200, demo_tree(_q(u, "path"))
    if path == "/api/structure/file":
        return 200, demo_file(_q(u, "path"), _q(u, "file"), _q(u, "line", "1"))
    return 200, {"ok": True}


def demo_arch_files(mid):
    """Body of demo `GET /api/arch/files` — arch_map.files() keys, names from the demo tree under the module path."""
    out = {"ok": True, "commit": _ARCH_COMMIT, "id": "", "path": "", "files": [], "total": 0, "cut": False, "why": ""}
    mod = next((m for m in _ARCH_MODS if m["id"] == mid), None)
    if mod is None:
        return dict(out, why="bad")
    out.update(id=mid, path=mod["path"])
    if mod["kind"] == "external":
        return dict(out, why="ext")
    hit = [f["p"] for f in demo_tree()["files"] if f["p"].startswith(mod["path"])]
    return dict(out, files=hit, total=len(hit), why="" if hit else "gone")
