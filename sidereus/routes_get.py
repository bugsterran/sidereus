"""GET route handlers (split out of chat_server.py 2026-09-24) — a mixin `chat_server.Handler` inherits.
Methods use `self._send`/`self._raw_json` from Handler."""
import gzip
import json
from urllib.parse import parse_qs

from sidereus.cards import cards
from sidereus.bus import MSG_RANGE_DEFAULT, messages_range
from sidereus.ext import ext_work
from sidereus.timeline import TL_HOURS, agents_timeline
from sidereus.failures import FAIL_HOURS, failures, wreckage
from sidereus.work import agent_work, session_work
from sidereus.peer import peer_state
from sidereus.history import history, history_units
from sidereus.recent import recent_sessions
from sidereus.ctxsrc import session_context
from sidereus.toolidx import scanning as tools_scanning
from sidereus.toolinv import scan_items, tool_file
from sidereus.pipeline import pipelines, runs_here as pipeline_runs_here
from sidereus.sessions import sessions_snapshot
from sidereus.arch_map import ARCH_PL, seen_runs as arch_seen_runs
from sidereus.pipeline_projects import browse_dirs as pipeline_dirs, recent_dirs as pipeline_recent_dirs
from sidereus.pl_eval_view import pl_eval as pipeline_eval
from sidereus.harness_plat import harness_evidence_only, harness_plat, harness_plat_file
from sidereus.verdict_guide import load as verdict_guide
from sidereus.hook_diag import diag as hook_diag
from sidereus.sec_tools import tools as sec_tools
from sidereus.hook_connect import listing as hook_connect_list
from sidereus.claude_roots import accounts as claude_accounts
from sidereus.warn import warn_once
from sidereus.routes_struct import _StructRoutes, _q1, _exc_err, _exc_msg
from sidereus.routes_git import _GitRoutes
from sidereus.routes_usage import _UsageRoutes, _agent_quota
from sidereus.retro import retro
from sidereus.review import review_files
from sidereus.agent_brief import brief_attention, brief_file, brief_peers
from sidereus.page import BUILD_TIME, PAGE, PAGE_BUILD, PWA_FILES, pwa_reply
from sidereus.state import _state_body
from sidereus.state_v1 import build as state_v1
from sidereus.quota import quota
from sidereus.cc_settings import prefs_get_all
from sidereus.ui_prefs import script as ui_prefs_script, snapshot as ui_prefs_snapshot


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


class _GetRoutes(_StructRoutes, _GitRoutes, _UsageRoutes):
    def _peer_refused(self):
        """Answer the work routes' peer gate; True when a reply was sent. False -> 403 · undetermined -> 503 (page retries)."""
        st = peer_state(self.client_address)
        if st is True:
            return False
        if st is False:
            self._send(403, "forbidden", "text/plain; charset=utf-8")
            return True
        body = b'{"ok": false, "busy": true}'
        try:
            self.send_response(503)
            for k, v in (("Content-Type", "application/json; charset=utf-8"), ("Retry-After", "2"),
                         ("Cache-Control", "no-store"), ("Content-Length", str(len(body)))):
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionResetError, BrokenPipeError):
            return True   # client left mid-reply, same quiet disconnect as `_send`
        return True

    def _g_page(self, u):
        # ★`/diff` serves **the same document** (a separate window that boots in popup mode, ISPOP); manifest/icon paths get fixed bytes.
        code, hdr, body = pwa_reply(u.path) if u.path in PWA_FILES else \
            _page_reply(self.headers.get("If-None-Match"), self.headers.get("Accept-Encoding"))
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

    def _g_agent_work(self, u):
        if self._peer_refused():   # work logs carry transcript text: same-UID client only (macOS)
            return
        q = parse_qs(u.query)
        try:
            out = agent_work(_q1(q, "cwd"), _q1(q, "tid"),
                             _q1(q, "sid"))   # sid: parent session, for finished sessions (history tab)
        except Exception as e:
            out = {"ok": False, "msg": "Failed ({err})", "vars": {"err": f"{type(e).__name__}: {e}"}}
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
        # «+ Add project» folder browser: folder names + git/claude flags inside home only; recent=1 = «Recent session folders»
        try:
            q = parse_qs(u.query)
            code, out = (200, {"ok": True, "recent": pipeline_recent_dirs()}) if _q1(q, "recent") == "1" else pipeline_dirs(_q1(q, "path"), _q1(q, "hidden") == "1")
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

    def _g_verdict_guide(self, u):
        # Harness «Next step» guides from docs/verdicts (repo docs, no user data); lang outside ko|en reads as en
        try:
            code, out = 200, verdict_guide(_q1(parse_qs(u.query), "lang", "en"))
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

    def _g_hooks_connect(self, u):
        # «CLI hooks» notice: installed Cursor/Codex/Gemini and whether Sidereus hooks are in place; names, states, paths only (sidereus/hook_connect.py)
        try:
            code, out = 200, {"ok": True, "plats": hook_connect_list()}
        except Exception as e:
            code, out = 500, {"ok": False, **_exc_msg(e)}
        self._raw_json(code, out, cache=False)

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
        if self._peer_refused():
            return
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
        if self._peer_refused():
            return
        q = parse_qs(u.query)
        try:
            out = ext_work(_q1(q, "plat"), _q1(q, "sid"))
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
        if u.path == "/api/ui-prefs": return self._raw_json(200, ui_prefs_snapshot())   # {rev, prefs}: resync on uiRev
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
        "/": _g_page, "/diff": _g_page, "/work": _g_page, "/brdiff": _g_page, **dict.fromkeys(PWA_FILES, _g_page),   # /work, /brdiff: work-log and branch file-diff popups; PWA_FILES: app manifest + icons
        "/api/branches": _GitRoutes._g_branches, "/api/git/wtfiles": _GitRoutes._g_wtfiles, "/api/git/owners": _GitRoutes._g_owners,
        "/api/git/commit": _GitRoutes._g_commit, "/api/git/links": _GitRoutes._g_git_links,
        "/api/otel": _UsageRoutes._g_otel, "/api/agent/work": _g_agent_work, "/api/live": _UsageRoutes._g_live,
        "/api/quota/burn": _UsageRoutes._g_quota_burn, "/api/structure/src": _StructRoutes._g_structure_src,
        "/api/structure/pair": _StructRoutes._g_structure_pair, "/api/structure": _StructRoutes._g_structure,
        "/api/structure/tree": _StructRoutes._g_structure_tree,
        "/api/structure/file": _StructRoutes._g_structure_file, "/api/structure/img": _StructRoutes._g_structure_img, "/api/arch": _StructRoutes._g_arch, "/api/arch/files": _StructRoutes._g_arch_files, "/api/arch/secreport": _StructRoutes._g_arch_secreport, "/api/wkuse": _UsageRoutes._g_wkuse,
        "/api/retro": _g_retro, "/api/review": _g_review, "/api/history": _g_history, "/api/history/units": _g_history_units,
        "/api/sessions/recent": _g_sessions_recent, "/api/prefs": _g_prefs, "/api/ui-prefs.js": _g_ui_prefs, "/api/ui-prefs": _g_ui_prefs,
        "/api/session/context": _g_session_context,
        "/api/tools": _g_tools, "/api/tools/file": _g_tools_file,
        "/api/pipelines": _g_pipelines, "/api/pipelines/projects/dirs": _g_pipeline_dirs, "/api/pipelines/eval": _g_pipeline_eval, "/api/harness": _g_harness, "/api/harness/file": _g_harness_file, "/api/harness/evidence": _g_harness_evidence, "/api/verdict-guide": _g_verdict_guide, "/api/diag": _g_diag, "/api/sec-tools": _g_sec_tools, "/api/hooks/connect": _g_hooks_connect,
        "/api/agents/timeline": _g_timeline, "/api/failures": _g_failures, "/api/wreckage": _g_failures,
        "/api/session/work": _g_session_work, "/api/ext/work": _g_ext_work, "/api/git/file": _GitRoutes._g_git_file, "/api/git/diff": _GitRoutes._g_git_diff,
        "/api/cards": _g_cards, "/api/messages": _g_messages, "/api/state": _g_state, "/api/v1/state": _g_state_v1, "/api/hookstate": _g_hookstate,
        "/api/agent/quota": _g_agent_brief, "/api/agent/peers": _g_agent_brief,
        "/api/agent/file": _g_agent_brief, "/api/agent/attention": _g_agent_brief,
    }
