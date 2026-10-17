"""GET route handlers (split out of chat_server.py 2026-09-24) — a mixin `chat_server.Handler` inherits.
Methods use `self._send`/`self._raw_json` from Handler."""
import gzip
import json
import os
import time
from urllib.parse import parse_qs

from sidereus.usage import LIVE_SEC, LIVE_STEP
from sidereus.otel import _otel, _otel_lock, _otel_sample, _otel_stat, _otel_src_cmp, _otel_src_win
from sidereus.cards import cards
from sidereus.bus import MSG_RANGE_DEFAULT, messages_range
from sidereus.ext import ext_work
from sidereus.timeline import TL_HOURS, agents_timeline
from sidereus.failures import FAIL_HOURS, failures, wreckage
from sidereus.work import agent_work, session_work
from sidereus.peer import peer_ok
from sidereus.git import BRANCH_N_DEF, _branch_ok, branch_graph, git_commit, git_diff, git_file_diff, wt_files
from sidereus.history import history, history_units
from sidereus.recent import recent_sessions
from sidereus.ctxsrc import session_context
from sidereus.toolidx import scanning as tools_scanning
from sidereus.toolinv import scan_items, tool_file
from sidereus.pipeline import pipelines, runs_here as pipeline_runs_here
from sidereus.sessions import sessions_snapshot
from sidereus.arch_map import ARCH_PL, seen_runs as arch_seen_runs
from sidereus.pipeline_projects import browse_dirs as pipeline_dirs
from sidereus.pl_eval_view import pl_eval as pipeline_eval
from sidereus.harness_plat import harness_evidence_only, harness_plat, harness_plat_file
from sidereus.hook_diag import diag as hook_diag
from sidereus.sec_tools import tools as sec_tools
from sidereus.burn import WK_DAYS, _WK_RANGES, _live_buckets, _wk_slot, _wkuse_busy, burn_use, quota_burn, quota_burn_acct, quota_burn_peek, wk_stale, wkuse, wkuse_refresh
from sidereus.claude_roots import accounts as claude_accounts
from sidereus.saver_cap import cap as saver_cap
from sidereus.warn import warn_once
from sidereus.routes_struct import _StructRoutes, _q1, _exc_err, _exc_msg
from sidereus.file_owner import wt_owners
from sidereus.retro import retro
from sidereus.review import review_files
from sidereus.commit_link import commit_links
from sidereus.agent_brief import brief_attention, brief_file, brief_peers, brief_quota
from sidereus.page import BUILD_TIME, PAGE, PAGE_BUILD
from sidereus.state import _state_body
from sidereus.state_v1 import build as state_v1
from sidereus.quota import quota
from sidereus.cc_settings import prefs_get_all
from sidereus.ui_prefs import script as ui_prefs_script


def hook_state():
    """The only `/api/state` fields saver.py reads: quota.{five_hour,seven_day}.{pct,leftSec} (absent slot stays absent)."""
    q = quota() or {}
    out = {}
    for k in ("five_hour", "seven_day"):
        v = q.get(k)
        if isinstance(v, dict):
            out[k] = {"pct": v.get("pct"), "leftSec": v.get("leftSec")}
    return {"ok": True, "quota": out}


_PAGE_RAW = PAGE.encode("utf-8")
_PAGE_GZ = [None]      # compressed once per process, on the first gzip request
# Anti-framing + same-origin-only loads for every HTML route (/, /diff, /work, /brdiff all use _page_reply).
# ⚠'unsafe-inline' in script/style: PAGE is one inline document with onclick= attributes and style= everywhere.
# ⚠img-src data: — the favicon (index.html, FAV_DOT swap in 15-alarms.js) is a data: SVG. No blob:/web fonts are used.
# ⚠Adding an external host (CDN, update check, other port) means widening this string — see docs/dev/traps/security.md «CSP: adding an external source».
PAGE_CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'; object-src 'none'")


def _page_reply(if_none_match, accept_encoding):
    """(code, headers, body) for the static PAGE.

    ★2026-09-25: the 1.1MB document went out uncompressed with `no-store` on every load/popup.
      PAGE is fixed per process (PAGE_BUILD = its hash) ⇒ gzip + ETag + `no-cache` so a reload is a 304.
    ⚠`no-cache` (revalidate every time), not max-age — after a restart the new build must load at once.
    ⚠The ETag differs per encoding (Vary: Accept-Encoding) — one tag for two bodies breaks caches.
    """
    gz = "gzip" in (accept_encoding or "")
    tag = '"%s%s"' % (PAGE_BUILD, "-gz" if gz else "")
    hdr = [("Content-Type", "text/html; charset=utf-8"), ("Vary", "Accept-Encoding"),
           ("ETag", tag), ("Cache-Control", "no-cache"),
           ("Content-Security-Policy", PAGE_CSP), ("X-Frame-Options", "DENY"),
           ("X-Build-Time", BUILD_TIME)]   # HTML routes skip Handler._send, so the header is added here too
    tags = [t.strip().replace("W/", "", 1) for t in (if_none_match or "").split(",")]
    if tag in tags or "*" in tags:
        return 304, hdr, b""
    body = _PAGE_RAW
    if gz:
        if _PAGE_GZ[0] is None:
            _PAGE_GZ[0] = gzip.compress(_PAGE_RAW, 6)
        body = _PAGE_GZ[0]
        hdr.append(("Content-Encoding", "gzip"))
    return 200, hdr, body


def _acct_of_dir(d):
    """Account row whose config dir realpath-matches `d`, else None. The path itself is never opened."""
    try:   # ⚠a NUL byte makes realpath raise ValueError on 3.9
        rp = os.path.realpath(os.path.expanduser(d))
        return next((r for r in claude_accounts() if r.get("dir") and os.path.realpath(r["dir"]) == rp), None)
    except ValueError:
        return None


def _agent_quota(d):
    """`/api/agent/quota[?dir=]` — the calling session's account; an unknown dir never gets the primary's numbers."""
    if not d:
        return brief_quota()
    hit = _acct_of_dir(d)
    if not hit:
        return {"ok": False, "err": "unknown account"}
    return brief_quota(acct=hit.get("label"))


class _GetRoutes(_StructRoutes):
    def _g_page(self, u):
        # ★`/diff` serves **the same document** (to open the diff in a separate browser window).
        #   The page looks at its own path and boots in popup mode (ISPOP) — no second copy of CSS/JS.
        code, hdr, body = _page_reply(self.headers.get("If-None-Match"), self.headers.get("Accept-Encoding"))
        try:
            self.send_response(code)
            for k, v in hdr:
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)
        except (ConnectionResetError, BrokenPipeError):
            pass                        # same quiet disconnect as `_send`

    def _g_branches(self, u):
        # ★Branch graph raw data (2026-09-23). ⚠Do not attach to polling — called only when the screen clicks.
        #   Path confinement is `_branch_ok()` — only repos the screen knows (session cwd + touched repos) open.
        q = parse_qs(u.query)
        cwd = _q1(q, "cwd")
        code = 200
        if not cwd or not os.path.isdir(cwd):
            code, out = 400, {"ok": False, "err": "cwd required"}
        elif not _branch_ok(cwd):
            code, out = 403, {"ok": False, "err": "not allowed"}
        else:
            try:
                out = branch_graph(cwd, (q.get("n") or [str(BRANCH_N_DEF)])[0])
            except Exception as e:
                out = {"ok": False, "err": _exc_err(e)}
        self._raw_json(code, out)

    def _g_wtfiles(self, u):
        # Branches tab work unit: one worktree's uncommitted files (click-only). Validation lives in wt_files().
        q = parse_qs(u.query)
        try:
            code, out = wt_files(_q1(q, "cwd"))
        except Exception as e:
            code, out = 500, {"ok": False, "err": _exc_err(e)}
        self._raw_json(code, out)

    def _g_owners(self, u):
        # Branches tab work unit: which sessions edited each uncommitted file (metadata only). Validation lives in wt_files().
        q = parse_qs(u.query)
        try:
            code, out = wt_owners(_q1(q, "cwd"))
        except Exception as e:
            code, out = 500, {"ok": False, "err": _exc_err(e)}
        self._raw_json(code, out)

    def _g_commit(self, u):
        # Branches tab commit details (read-only, click-only). Validation lives in git_commit().
        q = parse_qs(u.query)
        try:
            code, out = git_commit(_q1(q, "repo"), _q1(q, "sha"),
                                   _q1(q, "path"))
        except Exception as e:
            code, out = 500, {"ok": False, "err": _exc_err(e)}
        self._raw_json(code, out)

    def _g_git_links(self, u):
        # Branch tab, after the graph paints: commit -> session/agent/cost (metadata only, sidereus/commit_link.py).
        q = parse_qs(u.query)
        try:
            code, out = commit_links(_q1(q, "repo"), _q1(q, "shas"))
        except Exception as e:
            code, out = 500, {"ok": False, "err": _exc_err(e)}
        self._raw_json(code, out)

    def _g_otel(self, u):
        # Diagnostic — which sessions are sending telemetry (if absent, that session started without the env)
        q = parse_qs(u.query)
        try:
            h = min(192, max(1, int((q.get("h") or ["5"])[0])))
        except ValueError:
            h = 5
        if _q1(q, "cmp") == "1":
            return self._send(200, json.dumps(_otel_src_cmp(h), ensure_ascii=False, indent=1),
                              "application/json; charset=utf-8")
        with _otel_lock:
            snap = {k: {"ev": v.get("ev"), "tool": v.get("tool"), "tokens": v.get("tokens"),
                        "ago": int(time.time() - (v.get("at") or 0)), "seq": v.get("seq")}
                    for k, v in _otel.items()}
        snap["_sample_api_request"] = dict(_otel_sample)
        with _otel_lock:
            # ⚠Copy nested dicts under the lock — ingest mutates bySrc/names while json.dumps runs outside it.
            st = {k: (dict(v) if isinstance(v, dict) else v) for k, v in _otel_stat.items()}
        now2 = time.time()
        st["postAgo"] = int(now2 - st["lastPost"]) if st["lastPost"] else None
        st["keptAgo"] = int(now2 - st["lastKept"]) if st["lastKept"] else None
        st["bySrcWin"] = _otel_src_win(h)     # persisted 5-min buckets — survives restarts (bySrc does not)
        snap["_stat"] = st
        return self._send(200, json.dumps(snap, ensure_ascii=False, indent=1),
                          "application/json; charset=utf-8")

    def _g_agent_work(self, u):
        if not peer_ok(self.client_address):   # work popups carry transcript text: same-UID client only (macOS)
            return self._send(403, "forbidden", "text/plain; charset=utf-8")
        q = parse_qs(u.query)
        try:
            out = agent_work(_q1(q, "cwd"), _q1(q, "tid"),
                             _q1(q, "sid"))   # sid: parent session, for finished sessions (history tab)
        except Exception as e:
            out = {"ok": False, "msg": "Failed ({err})", "vars": {"err": f"{type(e).__name__}: {e}"}}
        self._raw_json(200, out)

    def _g_live(self, u):
        # ★Live-only lightweight endpoint (2026-09-04: live must move in real time).
        #   `/api/wkuse` carries today's per-project totals, donut and burn, tied to a 30s cycle.
        #   This is served separately so only the live sparkline can be fetched every 3s — the computation is a single bucket fold.
        body = json.dumps({"live": _live_buckets(), "liveSec": LIVE_SEC,
                           "liveStep": LIVE_STEP, "at": int(time.time())},
                          ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _g_quota_burn(self, u):
        # ★Limit burndown — current 5h cycle consumption curve + extrapolation to reset + past-cycle baseline.
        #   Light (TTL 30s cache + incremental tail read) — the screen calls it piggybacked on token-area polling.
        # `?dir=` picks the account by config dir (realpath match only); the path itself is never opened.
        _d = (parse_qs(u.query).get("dir") or [""])[0]
        lab = None
        if _d:
            hit = _acct_of_dir(_d)
            if not hit:
                self._raw_json(400, {"ok": False})
                return
            lab = None if hit.get("primary") else hit["label"]
        try:
            out = quota_burn() if lab is None else quota_burn_acct(lab)
        except Exception as e:
            out = {"ok": False, "why": f"{type(e).__name__}: {e}"}
        try:   # `use` = account in use (burn_use); the cap reads that account's body whichever was asked
            use = burn_use()
            out = dict(out, use=use)   # ⚠copy — `out` may be the cached body
            ub = out if lab == (None if use["primary"] else use["label"]) else None
        except Exception as e:
            use, ub = None, out
            warn_once("burn-use", "account-in-use pick failed ({err}) — cap from the asked account", soft=True,
                      vars={"err": type(e).__name__})
        try:   # concurrency cap for the saver hook
            if ub is None:
                # ⚠cache only for the primary: a cold quota_burn() scan (636 ms warm disk, 6-20 s after reboot) vs the hook's 3 s timeout
                ub = (quota_burn_peek() or out) if use["primary"] else quota_burn_acct(use["label"])
            out = dict(out, cap=saver_cap(time.time(), ub))
        except Exception as e:
            warn_once("saver-cap", "concurrency cap failed ({err}) — responding without cap", soft=True,
                      vars={"err": type(e).__name__})
        self._raw_json(200, out)

    def _g_wkuse(self, u):
        _q = parse_qs(u.query)
        # ★Period (days). Unknown values fall back to default — accepting arbitrary large values makes ccusage run for minutes.
        try:
            _rg = int((_q.get("range") or [WK_DAYS])[0])
        except ValueError:
            _rg = WK_DAYS
        if _rg not in _WK_RANGES:
            _rg = WK_DAYS
        # Account pick: only a known label (it keys a slot); anything else = all accounts.
        _ac = _q1(_q, "acct") or ""
        if _ac not in {a.get("label") for a in claude_accounts()}:
            _ac = ""
        # If that period was never measured, fire now (do not await — ccusage takes over 30s)
        if _ac:
            if _q1(_q, "force") == "1" or wk_stale(_rg, _ac):   # ⚠per-account slots are not in _wkuse_loop
                wkuse_refresh(_rg, _ac)
        elif _q1(_q, "force") == "1" or not (_wk_slot(_rg).get("at") or 0):
            wkuse_refresh(_rg)                    # Fire in background and return the current value right away
        out = wkuse(_rg, _ac) if _ac else wkuse(_rg)
        out["busy"] = _wkuse_busy[0]
        self._raw_json(200, out)

    def _g_retro(self, u):
        # Tab-open only, like /api/history — never on the 2.5s poll (120s cache inside retro()).
        q = parse_qs(u.query)
        # Account pick: only a known label; anything else = All. The primary's per-account key is "".
        _ac = _q1(q, "acct") or ""
        _row = next((a for a in claude_accounts() if _ac and a.get("label") == _ac), None)
        try:
            out = retro((q.get("days") or ["7"])[0], *((_ac, "" if _row.get("primary") else _ac) if _row else ()))
        except Exception as e:
            out = {"ok": False, "msg": "Failed ({err})", "vars": {"err": f"{type(e).__name__}: {e}"}}
        self._raw_json(200, out)

    def _g_history(self, u):
        # ⚠A path reached **only when the view opens** — do not attach to the 2.5s poll (`/api/state`) (a 60s cache sits inside)
        q = parse_qs(u.query)
        try:
            out = history((q.get("days") or ["7"])[0])
        except Exception as e:
            out = {"ok": False, "msg": "Failed ({err})", "vars": {"err": f"{type(e).__name__}: {e}"}}
        self._raw_json(200, out)

    def _g_sessions_recent(self, u):
        # «Recently ended sessions» expand only (30s cache inside) — never on the 2.5s poll
        q = parse_qs(u.query)
        try:
            out = recent_sessions(_q1(q, "days") or 7)
        except Exception as e:
            out = {"ok": False, "msg": "Failed ({err})", "vars": {"err": f"{type(e).__name__}: {e}"}}
        self._raw_json(200, out)

    def _g_session_context(self, u):
        # «Context sources» expand only (60s cache inside) — paths, sizes and counts, never file text
        q = parse_qs(u.query)
        try:
            code, out = session_context(_q1(q, "cwd"), _q1(q, "sid"))
        except Exception as e:
            code, out = 500, {"ok": False, **_exc_msg(e)}
        self._raw_json(code, out)

    def _g_tools(self, u):
        # «Tools» list — names, paths, sizes, usage counts; never config text
        q = parse_qs(u.query)
        try:
            days = max(1, min(90, int(_q1(q, "days", "30") or 30)))
        except ValueError:
            return self._raw_json(400, {"ok": False, "msg": "bad days"})
        try:
            items = scan_items(days)
            code, out = 200, {"ok": True, "items": items, "scanning": tools_scanning()}
        except Exception as e:
            code, out = 500, {"ok": False, **_exc_msg(e)}
        self._raw_json(code, out)

    def _g_pipelines(self, u):
        # «Pipelines» (feature `pipeline`): stage metadata only — task/rules text never leaves sidereus/pipeline.py
        try:
            proj = _q1(parse_qs(u.query), "proj")
            # borrowed rows: runs on this project of a pipeline defined elsewhere (poll snapshot + last archRun, no recompute)
            code, out = pipelines(proj, pipeline_runs_here(proj, sessions_snapshot() or [], arch_seen_runs(), ARCH_PL) if proj else None)
        except Exception as e:
            code, out = 500, {"ok": False, **_exc_msg(e)}
        self._raw_json(code, out)

    def _g_pipeline_eval(self, u):
        # Per-stage evaluation (catch counts · red check · unstable) — counts and verdicts only, never case ids
        try:
            q = parse_qs(u.query)
            code, out = pipeline_eval(_q1(q, "proj"), _q1(q, "name"))
        except Exception as e:
            code, out = 500, {"ok": False, **_exc_msg(e)}
        self._raw_json(code, out)

    def _g_pipeline_dirs(self, u):
        # «+ Add project» folder browser: folder names + git/claude flags inside the user's home only
        try:
            q = parse_qs(u.query)
            code, out = pipeline_dirs(_q1(q, "path"), _q1(q, "hidden") == "1")
        except Exception as e:
            code, out = 500, {"ok": False, **_exc_msg(e)}
        self._raw_json(code, out)

    def _g_harness(self, u):
        # «Harness map» (feature `harness`): hook/rule/agent metadata only — script text never leaves sidereus/harness.py
        q = parse_qs(u.query)
        try:
            code, out = harness_plat(_q1(q, "plat", "cc"), _q1(q, "proj"), _q1(q, "days", "30"))   # plat validated there
        except Exception as e:
            code, out = 500, {"ok": False, **_exc_msg(e)}
        self._raw_json(code, out)

    def _g_harness_evidence(self, u):
        # Gate evidence only (metadata: step names, ints, short sha) for stage labels in the pipeline view
        try:
            code, out = harness_evidence_only(_q1(parse_qs(u.query), "proj"))
        except Exception as e:
            code, out = 500, {"ok": False, **_exc_msg(e)}
        self._raw_json(code, out)

    def _g_diag(self, u):
        # Settings › «Diagnostics» (feature `diag`): hook overlaps / silent plugin hooks, metadata only (sidereus/hook_diag.py)
        try:
            code, out = hook_diag()
        except Exception as e:
            code, out = 500, {"ok": False, **_exc_msg(e)}
        self._raw_json(code, out)

    def _g_sec_tools(self, u):
        # Settings › «Diagnostics» › «Security tools»: installed + version from PATH/file layout only, nothing run (sidereus/sec_tools.py)
        try:
            code, out = 200, {"ok": True, "tools": sec_tools()}
        except Exception as e:
            code, out = 500, {"ok": False, **_exc_msg(e)}
        self._raw_json(code, out)

    def _g_harness_file(self, u):
        # One card's config/script text on click, by opaque ref (path re-derived and root-checked in sidereus/harness.py)
        q = parse_qs(u.query)
        try:
            code, out = harness_plat_file(_q1(q, "plat", "cc"), _q1(q, "proj"), _q1(q, "ref"))
        except Exception as e:
            code, out = 500, {"ok": False, **_exc_msg(e)}
        self._raw_json(code, out)

    def _g_tools_file(self, u):
        # One item's text on click (.md as is, MCP env/headers masked, hook commands redacted)
        try:
            code, out = tool_file(_q1(parse_qs(u.query), "id"))
        except Exception as e:
            code, out = 500, {"ok": False, **_exc_msg(e)}
        self._raw_json(code, out)

    def _g_history_units(self, u):
        # Row click in the history tab only (30s cache inside) — metadata of the session's main + sub-agents
        q = parse_qs(u.query)
        try:
            out = history_units(_q1(q, "sid"))
        except Exception as e:
            out = {"ok": False, "msg": "Failed ({err})", "vars": {"err": f"{type(e).__name__}: {e}"}}
        self._raw_json(200, out)

    def _g_timeline(self, u):
        q = parse_qs(u.query)
        try:
            out = agents_timeline(float((q.get("hours") or [TL_HOURS])[0]))
        except Exception as e:
            out = {"ok": False, "msg": "Failed ({err})", "vars": {"err": f"{type(e).__name__}: {e}"}}
        self._raw_json(200, out)

    def _g_failures(self, u):
        # Serves both `/api/failures` and `/api/wreckage` (same hours parsing).
        q = parse_qs(u.query)
        try:
            h = float((q.get("hours") or [FAIL_HOURS])[0])
            out = failures(h) if u.path == "/api/failures" else wreckage(h)
        except Exception as e:
            out = {"ok": False, "msg": "Failed ({err})", "vars": {"err": f"{type(e).__name__}: {e}"}}
        self._raw_json(200, out)

    def _g_session_work(self, u):
        if not peer_ok(self.client_address):
            return self._send(403, "forbidden", "text/plain; charset=utf-8")
        q = parse_qs(u.query)
        try:
            # `sid` is optional — if absent, the latest transcript of cwd as before (backward compatible)
            # `at` (epoch) = read the window ending then (retro failure rows); junk -> ignored, never an error
            try:
                at = float(_q1(q, "at") or 0) or None
            except ValueError:
                at = None
            out = session_work(_q1(q, "cwd"), _q1(q, "sid"), at)
        except Exception as e:
            out = {"ok": False, "msg": "Failed ({err})", "vars": {"err": f"{type(e).__name__}: {e}"}}
        self._raw_json(200, out)

    def _g_prefs(self, u):
        # «Preferences» server prefs: allow-listed config.local.json keys + the two Claude Code settings.json keys (values, never secrets)
        try:
            code, out = 200, prefs_get_all()
        except Exception as e:
            code, out = 500, {"ok": False, "err": _exc_err(e)}
        self._raw_json(code, out, cache=False)

    def _g_review(self, u):
        # «Review» file list of one finished session (click-only). review_files() validates sid/cwd against visible rows.
        q = parse_qs(u.query)
        try:
            code, out = review_files(_q1(q, "cwd"), _q1(q, "sid"))
        except Exception as e:
            code, out = 500, {"ok": False, "err": _exc_err(e)}
        self._raw_json(code, out)

    def _g_ext_work(self, u):
        if not peer_ok(self.client_address):
            return self._send(403, "forbidden", "text/plain; charset=utf-8")
        q = parse_qs(u.query)
        try:
            out = ext_work(_q1(q, "plat"), _q1(q, "sid"))
        except Exception as e:
            out = {"ok": False, "msg": "Failed ({err})", "vars": {"err": f"{type(e).__name__}: {e}"}}
        self._raw_json(200, out)

    def _g_git_file(self, u):
        q = parse_qs(u.query)
        try:
            out = git_file_diff(_q1(q, "cwd"), _q1(q, "path"),
                                (q.get("scope") or ["all"])[0])
        except Exception as e:
            out = {"ok": False, "msg": "Failed ({err})", "vars": {"err": f"{type(e).__name__}: {e}"}}
        self._raw_json(200, out)

    def _g_git_diff(self, u):
        # ★Do not import inside the function — the name becomes a local for the whole function,
        #   and parse_qs in /api/state died with UnboundLocalError (measured 2026-08-25).
        q = parse_qs(u.query)
        cwd = _q1(q, "cwd")
        try:
            out = git_diff(cwd, (q.get("scope") or ["all"])[0],
                           (q.get("pw") or ["today"])[0], _q1(q, "view") or "", _q1(q, "new") or "",
                           _q1(q, "sid") or "", _q1(q, "base") or "", "1" if _q1(q, "untr") == "1" else "")
        except Exception as e:
            out = {"ok": False, "msg": "Failed ({err})", "vars": {"err": f"{type(e).__name__}: {e}"}}
        self._raw_json(200, out)

    def _g_agent_brief(self, u):
        # Read-only briefs for the `sidereus` MCP server (mcp/sidereus_mcp.py). Metadata only — built in sidereus/agent_brief.py.
        q = parse_qs(u.query)
        a = lambda k: _q1(q, k)
        try:
            out = {"/api/agent/quota": lambda: _agent_quota(a("dir")),
                   "/api/agent/peers": lambda: brief_peers(a("cwd")),
                   "/api/agent/file": lambda: brief_file(a("path"), a("cwd")),
                   "/api/agent/attention": lambda: brief_attention()}[u.path]()
        except Exception as e:
            out = {"ok": False, "err": "%s: %s" % (type(e).__name__, e)}
        self._raw_json(200, out)

    def _g_cards(self, u):
        # ★Lightweight cards-only route (2026-09-22) — the "Full history" button (`#aall`) pulled the full `/api/state`
        #   to get a few tens of KB of cards. Measured 3,186,536B → 65,702B (300 cards · 48x).
        # ⚠The format must be **exactly identical** to `cards` in `state()` — it calls the same builder `cards(n)`.
        #   If they differ, `buildAlarm()` breaks silently. The 300 cap must also match `/api/state`.
        try:
            _n = int((parse_qs(u.query).get("n") or ["300"])[0] or 300)
        except ValueError:
            _n = 300
        _n = max(1, min(_n, 300))
        self._raw_json(200, {"cards": cards(_n)})

    def _g_state(self, u):
        # ⚠Bare int() on `?since=x` raised, dropped the connection and left a traceback in viewer.err.
        _q = parse_qs(u.query)
        try:
            since = int((_q.get("since") or ["0"])[0] or 0)
        except ValueError:
            since = 0
        try:
            nc = int((_q.get("cards") or ["50"])[0] or 50)
        except ValueError:
            nc = 50
        nc = max(1, min(nc, 300))
        _body, _gz = _state_body(since, nc)
        return self._send(200, _body, "application/json; charset=utf-8", _gz)

    def _g_messages(self, u):
        # Feed «Earlier posts» body fetch for first-load stubs (bus.messages_first) — mailbox posts only, same as /api/state.
        _q = parse_qs(u.query)
        try:
            after = int((_q.get("after") or ["0"])[0] or 0)
            before = int((_q.get("before") or ["0"])[0] or 0) or None
            n = int((_q.get("n") or [""])[0] or MSG_RANGE_DEFAULT)   # capped at bus.MSG_RANGE_MAX in messages_range
            if n < 1:
                raise ValueError("n")   # ⚠messages_range clamps to 1, so n<=0 would silently return one post
        except ValueError:
            return self._raw_json(400, {"error": "bad cursor"})
        return self._send(200, json.dumps({"messages": messages_range(after, before, n)}, ensure_ascii=False),
                          "application/json; charset=utf-8", [None])   # gzip: a full range is ~MBs

    def _g_state_v1(self, u):
        # Public versioned projection (sidereus/state_v1.py, docs/schema/sidereus-state.v1.json) — /api/state stays the screen's own.
        try:
            return self._raw_json(200, state_v1())
        except Exception as e:
            return self._raw_json(500, {"ok": False, "err": _exc_err(e)})

    def _g_ui_prefs(self, u):
        # Page UI prefs as a script (loaded before app JS); `null` = no file yet, the page migrates localStorage once
        # ⚠Only route serving private data as executable script: <script src> is readable cross-origin and the shared guard
        # lets a missing Sec-Fetch-Site through, so require same-origin; without it __UIP stays undefined ⇒ defaults, no POST.
        if self.headers.get("Sec-Fetch-Site") != "same-origin":
            return self._send(403, "forbidden", "text/plain; charset=utf-8")
        try:
            body = ui_prefs_script()
        except Exception as e:
            warn_once("ui-prefs-get", "Could not read UI settings ({err})", vars={"err": f"{type(e).__name__}: {e}"})
            body = "window.__UIP={};"
        self._send(200, body, "application/javascript; charset=utf-8")

    def _g_hookstate(self, u):
        # ⚠saver.py fallback: the full /api/state is ~3MB (120-250ms); this is the quota subset only.
        try:
            out = hook_state()
        except Exception as e:
            out = {"ok": False, "err": _exc_err(e)}
        self._raw_json(200, out)
    # ⚠Exact paths only (no prefixes). A path missing here is a 404 (GET: text, POST: JSON) — same as the old if-chain.
    _GET_ROUTES = {
        "/": _g_page, "/diff": _g_page, "/work": _g_page, "/brdiff": _g_page,   # /work, /brdiff: work-log and branch file-diff popups
        "/api/branches": _g_branches, "/api/git/wtfiles": _g_wtfiles, "/api/git/owners": _g_owners,
        "/api/git/commit": _g_commit, "/api/git/links": _g_git_links,
        "/api/otel": _g_otel, "/api/agent/work": _g_agent_work, "/api/live": _g_live,
        "/api/quota/burn": _g_quota_burn, "/api/structure/src": _StructRoutes._g_structure_src,
        "/api/structure/pair": _StructRoutes._g_structure_pair, "/api/structure": _StructRoutes._g_structure,
        "/api/structure/tree": _StructRoutes._g_structure_tree,
        "/api/structure/file": _StructRoutes._g_structure_file, "/api/structure/img": _StructRoutes._g_structure_img, "/api/arch": _StructRoutes._g_arch, "/api/arch/files": _StructRoutes._g_arch_files, "/api/arch/secreport": _StructRoutes._g_arch_secreport, "/api/wkuse": _g_wkuse,
        "/api/retro": _g_retro, "/api/review": _g_review, "/api/history": _g_history, "/api/history/units": _g_history_units,
        "/api/sessions/recent": _g_sessions_recent, "/api/prefs": _g_prefs, "/api/ui-prefs.js": _g_ui_prefs,
        "/api/session/context": _g_session_context,
        "/api/tools": _g_tools, "/api/tools/file": _g_tools_file,
        "/api/pipelines": _g_pipelines, "/api/pipelines/projects/dirs": _g_pipeline_dirs, "/api/pipelines/eval": _g_pipeline_eval, "/api/harness": _g_harness, "/api/harness/file": _g_harness_file, "/api/harness/evidence": _g_harness_evidence, "/api/diag": _g_diag, "/api/sec-tools": _g_sec_tools,
        "/api/agents/timeline": _g_timeline, "/api/failures": _g_failures, "/api/wreckage": _g_failures,
        "/api/session/work": _g_session_work, "/api/ext/work": _g_ext_work, "/api/git/file": _g_git_file, "/api/git/diff": _g_git_diff,
        "/api/cards": _g_cards, "/api/messages": _g_messages, "/api/state": _g_state, "/api/v1/state": _g_state_v1, "/api/hookstate": _g_hookstate,
        "/api/agent/quota": _g_agent_brief, "/api/agent/peers": _g_agent_brief,
        "/api/agent/file": _g_agent_brief, "/api/agent/attention": _g_agent_brief,
    }
