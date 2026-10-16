#!/usr/bin/env python3
"""Sidereus — session control viewer (local server).

Name (user decision 2026-08-19): originally `mailbox`, built to read cross-session chat. Session control
    (state, context, idle, unpushed), alarm cards and stale-thread detection now sit on top, so "mailbox" no longer fits.
    ⇒ **Sidereus** (public square): sessions speak in public, a human watches, a third party (advocate) reviews.
    ⚠Only the **UI and document names** changed. The protocol (9 `mailbox_*` tools, `MAILBOX_ME/SELF`,
    `~/.mailbox-mcp`, launchd label, `bus.jsonl`) **stays as is** — it is baked into every session's config,
    and this project has had a real incident where one wrong identity setting **swallowed messages permanently** (2026-08-07).

Why a server: `transcript.py --html` was a snapshot, so the page had to **reload wholesale every 6 s**.
    The screen jumped mid-read. The cause was delivery, not storage — under `file://` the page cannot
    read data directly (CORS), so reload was the only option.
    With a local server the page **appends only new messages** (no reload, scroll kept, read marks updated in place).

Storage is still files (bus.jsonl etc.). The MCP server and watcher scripts share them, so **the protocol is untouched** —
    moving to SQLite is a separate decision, since it needs every peer session to reconnect.
    If query speed becomes a problem, cache an index inside this server only (files remain the source of truth).

Usage: python3 <repo>/chat_server.py [--port N] [--no-open] [--demo]
       --port N > env SIDEREUS_PORT > config `port` > 8799 (mailbox_config.port(), sidereus/config.py)
       --demo serves a synthetic world (sidereus/demo.py) — for screenshots and trying it without Claude Code
       http://127.0.0.1:<port>/       <- stays live while open
Stop:  Ctrl+C  (or pkill -f chat_server.py)
"""
import gzip
import json
import os
import sys
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

# ★Stage 3 split (2026-09-23): the Python lives in sidereus/<domain>.py; this file keeps the HTTP handler core
#   (send/guards/dispatch), and main(). 2026-09-24: state() -> sidereus/state.py, page -> sidereus/page.py,
#   route bodies + route tables -> sidereus/routes_get.py / routes_post.py (mixins Handler inherits).
#   ⇒ Tests and tools read a name from its owning module (tests/_load.py sidereus("<mod>")), not from this one.
#   ⚠A module-level name is owned by exactly one module. Never rebind an imported name — change it in its owner.
#   ⚠One import line per module in refactor/STAGE3.md order — it fixes the load order.
#   The path insert makes `sidereus` importable when this file is loaded by path (importlib, refactor/snap.py).
if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sidereus.memo  # noqa: F401  (nothing used here; kept for import order)
from sidereus.config import GZIP_MIN, INSTANCE_ID, PORT, argv, viewer_origin
from sidereus.warn import log_ts
from sidereus.bus import ensure_bus, messages
from sidereus.features import on as feature_on, route_feature, thread_on
from sidereus.ui_prefs import memory_only as ui_prefs_memory_only
import sidereus.claude_roots  # noqa: F401  (nothing used here; kept for import order)
import sidereus.transcript  # noqa: F401  (nothing used here; kept for import order)
import sidereus.ident  # noqa: F401  (nothing used here; kept for import order)
from sidereus.live import _model_win, _win_ev, _win_load, _win_loop
import sidereus.gitinfo  # noqa: F401  (nothing used here; kept for import order)
import sidereus.steps  # noqa: F401  (nothing used here; kept for import order)
import sidereus.agents  # noqa: F401  (nothing used here; kept for import order)
import sidereus.cards  # noqa: F401  (nothing used here; kept for import order)
import sidereus.usage  # noqa: F401  (nothing used here; kept for import order)
import sidereus.otel  # noqa: F401  (nothing used here; kept for import order)
from sidereus.projcost import _projcost_loop
import sidereus.bgtasks  # noqa: F401  (nothing used here; kept for import order)
import sidereus.notes  # noqa: F401  (nothing used here; kept for import order)
import sidereus.parse  # noqa: F401  (nothing used here; kept for import order)
import sidereus.ext  # noqa: F401  (nothing used here; kept for import order)
import sidereus.sessions  # noqa: F401  (nothing used here; kept for import order)
from sidereus.timeline import _tl_warm
from sidereus.failures import _fail_loop, _wdrop_load, _wsnap_load
import sidereus.work  # noqa: F401  (nothing used here; kept for import order)
import sidereus.git_rail  # noqa: F401  (nothing used here; kept for import order — git_view.git_diff imports it lazily)
import sidereus.git  # noqa: F401  (kept for import order)
from sidereus.git import br_boot_warm_start
import sidereus.history  # noqa: F401  (nothing used here; kept for import order)
import sidereus.toolidx  # warm() is started below; kept in this import order
import sidereus.toolinv  # noqa: F401  (nothing used here; kept for import order)
import sidereus.pipeline  # noqa: F401  (nothing used here; kept for import order)
import sidereus.hook_diag  # noqa: F401  (nothing used here; kept for import order)
import sidereus.quota  # noqa: F401  (nothing used here; kept for import order)
from sidereus.quota_loop import _quota_loop, _usage_loop
import sidereus.agentcost  # noqa: F401  (nothing used here; kept for import order)
from sidereus.burn import _today_loop, _wkuse_loop, qburn_warm_start
from sidereus.awake import _awake_loop
import sidereus.saver  # noqa: F401  (nothing used here; kept for import order)
import sidereus.structure_scan  # noqa: F401  (nothing used here; kept for import order)
import sidereus.structure_snap  # noqa: F401  (nothing used here; kept for import order)
from sidereus.structure import _STRUCT_POLL, _struct_act, _struct_warm_loop
import sidereus.file_owner  # noqa: F401  (nothing used here; kept for import order)
from sidereus.pl_reqs import memory_only as pl_reqs_memory_only
import sidereus.attention  # noqa: F401  (nothing used here; kept for import order)
import sidereus.review  # noqa: F401  (nothing used here; kept for import order)
import sidereus.retro  # noqa: F401  (nothing used here; kept for import order)
import sidereus.commit_link  # noqa: F401  (nothing used here; kept for import order)
import sidereus.agent_brief  # noqa: F401  (nothing used here; kept for import order)
from sidereus.page import BUILD_TIME, PAGE, PAGE_BUILD  # noqa: F401  (PAGE re-exported: tests read cs.PAGE)
from sidereus.state import state  # noqa: F401  (re-exported: tests read cs.state)
from sidereus.routes_post import _PostRoutes
from sidereus.routes_get import _GetRoutes


class Handler(_GetRoutes, _PostRoutes, BaseHTTPRequestHandler):
    # Route bodies and `_GET_ROUTES`/`_POST_ROUTES` come from the mixins (sidereus/routes_get.py, routes_post.py).
    protocol_version = "HTTP/1.1"
    # ⚠Per-socket-op timeout (slowloris: one thread per stalled connection). No route holds a connection open
    #   (no long-poll/SSE); an idle keep-alive socket is closed after 30s and the browser simply reconnects.
    timeout = 30

    def end_headers(self):
        # Every response path (_send, _raw_json, page, send_error) ends here: one place for nosniff.
        self.send_header("X-Content-Type-Options", "nosniff")
        BaseHTTPRequestHandler.end_headers(self)

    def handle_one_request(self):
        # ★Disconnects also happen **while reading** (closing the tab mid request headers blows up in `readinto`).
        #   Guarding only `_send` kept piling up tracebacks (measured 2026-08-19) — both sides must be guarded for a clean log.
        try:
            BaseHTTPRequestHandler.handle_one_request(self)
        except (ConnectionResetError, BrokenPipeError):
            self.close_connection = True
        except Exception:
            # ★Same text socketserver's handle_error writes, but the header line carries the time (2026-09-25).
            #   ⚠Closing the connection here matches what the server does after handle_error.
            self.close_connection = True
            try:
                sys.stderr.write(f"{log_ts()}Exception occurred during processing of request from "
                                 f"{self.client_address}\n{traceback.format_exc()}")
                sys.stderr.flush()
            except Exception:
                pass

    def _send(self, code, body, ctype, gzbox=None):
        data = body.encode("utf-8") if isinstance(body, str) else body
        # ★gzip (2026-09-22) — every tab receives `/api/state` every 2.5s: full 3.73MB · incremental 864KB.
        #   The compressed body is **cached in the caller-provided `gzbox`** (`_state_body`) — recompressing every poll burns CPU.
        # ⚠`Content-Length` must be **the length after compression**. This function sets it itself, so do not reorder.
        # ⚠The hook (`saver.py`) uses urllib and sends no `Accept-Encoding` — it keeps receiving plain text.
        enc = None
        if gzbox is not None and len(data) >= GZIP_MIN \
           and "gzip" in (self.headers.get("Accept-Encoding") or ""):
            if gzbox[0] is None:
                gzbox[0] = gzip.compress(data, 6)
            data, enc = gzbox[0], "gzip"
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            if enc:
                self.send_header("Content-Encoding", enc)
            self.send_header("Vary", "Accept-Encoding")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Sidereus-Instance", INSTANCE_ID)   # sidereus_cli: is the viewer on this port ours (same data dir)?
            self.send_header("X-Build-Time", BUILD_TIME)   # assembly time + PAGE_BUILD; changes only on restart
            self.end_headers()
            self.wfile.write(data)
        except (ConnectionResetError, BrokenPipeError):
            # ★Closing or refreshing the tab disconnects mid-response — this is **normal** (frequent with 2.5s polling).
            #   Before, these piled up as tracebacks in `viewer.err`, and **real errors got buried among them.**
            #   A cause was actually missed that way (a NameError hidden behind ps timeouts) — so it is ignored quietly.
            pass

    def _origin_ok(self):
        """Block POSTs a browser sends from a **different origin**.

        ★A loopback bind blocks only external connections, not browsers (measured 2026-08-24): any web page
          throwing `fetch("http://127.0.0.1:8799/api/...", {method:"POST"})` got a plain 200.
          The response is unreadable (CORS), so no data leaks, but **writes** such as injecting fake session
          state (`/v1/logs`) or marking notifications read went through.
        ★Requests **without** `Origin` pass — OTEL export, curl and native clients send none, and
          blocking them kills session state collection. Browsers always attach Origin to cross-origin POSTs."""
        o = (self.headers.get("Origin") or "").strip()
        return not o or viewer_origin(o)

    def _host_ok(self):
        """DNS-rebinding guard: a rebound name reaches 127.0.0.1 but carries its own Host, so allow only ours.
        ⚠Bind is hard-coded 127.0.0.1 (main). Local senders (OTel, ext_hook.py, saver hooks) all use 127.0.0.1:PORT."""
        h = (self.headers.get("Host") or "").strip().lower()
        if h in (f"127.0.0.1:{PORT}", f"localhost:{PORT}"):
            return True
        self._refuse("host refused\n")
        return False

    def _refuse(self, text):
        # ⚠Content-Length + close: the body is left unread, and without both a keep-alive client hangs (curl >120s).
        self.close_connection = True
        self._send(403, text, "text/plain; charset=utf-8")

    # ── Routing (2026-09-24): exact path → handler table (`_POST_ROUTES` / `_GET_ROUTES`, end of class).
    #   Every old `if u.path == …` was an exact match, so a dict lookup keeps the matching order and results.
    #   ⚠Header order per route is kept as it was (some routes omit Cache-Control, `/api/live` sends it before Content-Length).

    def _raw_json(self, code, out, cache=True):
        """JSON reply without `_send` (no gzip, no disconnect guard) — the shape the raw routes always used."""
        body = json.dumps(out, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if cache:
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body_json(self, cap, default):
        """Small POST body as JSON; `default` when missing, over `cap` bytes, or unparsable."""
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except Exception:
            n = -1
        if not 0 <= n <= cap:
            self._body_unread()
            return default
        try:
            return json.loads(self.rfile.read(n) or b"{}") if n else default
        except Exception:
            return default

    def _feature_off(self, path):
        """404 `feature off` for a route claimed by a switched-off feature (sidereus/features.py) -> True if sent."""
        fid = route_feature(path)
        if fid is None or feature_on(fid):
            return False
        self._send(404, json.dumps({"error": "feature off"}), "application/json; charset=utf-8")
        return True

    def _body_unread(self):
        # ⚠A body left unread on a keep-alive socket is parsed as the next request — close instead (same as _refuse).
        self.close_connection = True

    def do_POST(self):
        if not self._host_ok():
            return
        u = urlparse(self.path)
        # ⚠`/api/hook` (external CLI hooks) is not a human either — including it freezes the idle verdict as permanently awake
        if u.path not in ("/v1/logs", "/v1/metrics", "/api/hook"):    # Telemetry is not a human
            _struct_act[0] = time.time()
        if not self._origin_ok():
            return self._refuse("cross-origin POST refused\n")
        if self.headers.get("Transfer-Encoding"):
            # ⚠No chunked decoder: without a length every route read the body as empty and left the chunks
            #   on the keep-alive socket, to be parsed as the next request. Refuse once here for every route.
            #   With Content-Length too, RFC 9112 says Transfer-Encoding wins, so trusting the length is wrong — refuse as well.
            self.close_connection = True
            return self._send(411, "Content-Length required\n", "text/plain; charset=utf-8")
        if self._feature_off(u.path):
            self.close_connection = True    # body unread (see _refuse)
            return
        fn = self._POST_ROUTES.get(u.path)
        if fn is None:
            self.close_connection = True    # body unread (see _refuse)
            return self._send(404, json.dumps({"error": "not found"}), "application/json; charset=utf-8")
        return fn(self, u)

    def do_GET(self):
        if not self._host_ok():
            return
        u = urlparse(self.path)
        # ⚠A cross-site page could fire side-effecting/expensive GETs (/api/wkuse?force=1, /api/structure).
        #   `same-site` is refused too: a page on another 127.0.0.1 port is same-site. Allowed: same-origin (our page),
        #   `none` (typed URL) and no header (curl/hooks/OTel/MCP send none). Non-API paths stay open so a link still works.
        if u.path.startswith("/api/") and \
           (self.headers.get("Sec-Fetch-Site") or "").strip().lower() in ("cross-site", "same-site"):
            return self._refuse("cross-site GET refused\n")
        # «Human activity» marker that structure pre-warming yields to — timer polling is not counted (⚠ at `_STRUCT_POLL` above)
        if u.path not in _STRUCT_POLL:
            _struct_act[0] = time.time()
        if self._feature_off(u.path):
            return
        fn = self._GET_ROUTES.get(u.path)
        if fn is None:
            return self._send(404, "not found", "text/plain; charset=utf-8")
        return fn(self, u)

    def log_message(self, *a):        # Keep access logs out of the terminal
        pass


def main():
    if "--demo" in argv:       # Synthetic world, no background threads, nothing real is read or written (sidereus/demo.py)
        from sidereus import demo
        ui_prefs_memory_only({"mbMainView": "pipe"})   # in memory only; the demo opens on Pipelines (real viewer: Timeline)
        pl_reqs_memory_only()    # run requests / stop markers too
        return demo.serve(Handler, PORT, PAGE_BUILD, "--no-open" not in argv)
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)   # Loopback only — no external exposure
    url = f"http://127.0.0.1:{PORT}/"
    ensure_bus()
    n = len(messages(0))
    # ★Window learning — load saved learned values first (% attaches immediately), and the scan runs **in background**.
    #   Running it on the startup path keeps the page from opening while launchd starts it (even a 1.6s full scan exceeds the 2.5s poll).
    _win_load()
    _wsnap_load()                 # Snapshots at failure time (persist across restarts)
    _wdrop_load()                 # Debris the human marked as handled
    # Each start is gated by thread_on(name): a thread claimed by a switched-off feature manifest is not started.
    for target, name in (
            (_win_loop, "win_loop"),
            (_usage_loop, "usage_loop"),         # ccusage is slow, so background only
            (_quota_loop, "quota_loop"),         # Official quota (frequent 429s, so it backs off)
            (_projcost_loop, "projcost_loop"),   # Per-project totals (local index)
            (_wkuse_loop, "wkuse_loop"),         # Weekly per-project tokens (measured 26s — separate thread)
            (_today_loop, "today_loop"),         # Today by hour (measured 0.75s — every minute)
            (_fail_loop, "fail_loop"),           # Failure event accumulation (first full scan 1.3GB=2.4s — done ahead)
            (_awake_loop, "awake_loop"),         # Keep-awake while sessions are running
            (_struct_warm_loop, "struct_warm"),  # Structure treemap idle pre-warm (one at a time)
            (_tl_warm, "tl_warm"),               # Timeline cache pre-warm (one shot, see TL_WARM_DELAY_S)
            (sidereus.toolidx.warm, "toolidx_warm")):   # Tool usage index + 30-day caches before the first Harness/Tools click
        if thread_on(name):
            threading.Thread(target=target, name=name, daemon=True).start()
    if thread_on("qburn_warm_start"):
        qburn_warm_start()        # /api/quota/burn: full body after the first live quota sample; light until then
    if thread_on("br_boot_warm_start"):
        br_boot_warm_start()      # Branch tab: rebuild keys requested before the restart (sidereus/git.py BR_WARM_FILE)
    wm = ", ".join(f"{k.replace('claude-','')}={_model_win(k)[0]//1000}k({_model_win(k)[1]} sessions)" for k in sorted(_win_ev))
    print(f"Sidereus (viewer) started — {url}  ({n} messages · 2.5s incremental refresh · no reload)", flush=True)
    print(f"  Learned context windows: {wm or '(none yet — scanning)'}", flush=True)
    if "--no-open" not in argv:
        webbrowser.open(url)    # ★`open` is macOS-only — the standard library covers all 3 platforms at once
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("Stopped")


if __name__ == "__main__":
    main()
