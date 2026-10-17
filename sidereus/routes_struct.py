"""Structure GET route handlers (split out of routes_get.py) — a mixin `_GetRoutes` inherits.
Also owns `_q1`/`_exc_err`/`_exc_msg` (routes_get imports them back, so no circular import)."""
from urllib.parse import parse_qs

from sidereus.structure import structure, structure_src, structure_pair
from sidereus.structure_tree import structure_file, structure_img, structure_tree
from sidereus.arch_map import files as arch_files, load as arch_load, security_report as arch_secreport


def _q1(q, k, d=""):
    """First value of query key `k` from parse_qs output, else `d` (also when the value list is empty)."""
    return (q.get(k) or [d])[0]


def _exc_err(e):
    """Handler error text for `err` fields (English; the page shows it as is)."""
    return "Failed (%s: %s)" % (type(e).__name__, e)


def _exc_msg(e):
    """Handler error as a TV reply part {msg, vars}: fixed key 'Failed ({err})' (Korean via I18N.ko)."""
    return {"msg": "Failed ({err})", "vars": {"err": "%s: %s" % (type(e).__name__, e)}}


class _StructRoutes:
    def _g_structure_src(self, u):
        # **Source at that point** of one treemap cell (= function); the screen uses it for both code view and
        #   two-point diff.
        # ⚠Path confinement is inside `structure_src()` — projects outside the allow list and `..` are blocked there.
        q = parse_qs(u.query)
        try:
            out = structure_src(_q1(q, "path") or None,
                                _q1(q, "file"),
                                (q.get("line") or ["1"])[0],
                                (q.get("lines") or ["0"])[0],
                                (q.get("src") or ["cur"])[0].strip().lower(),
                                _q1(q, "rev").strip(),
                                (q.get("at") or ["0"])[0])
        except Exception as e:
            out = {"ok": False, **_exc_msg(e)}
        self._raw_json(200, out)

    def _g_structure_pair(self, u):
        # Source <-> test pairing for the structure panel. Confinement is inside `structure_pair()`.
        q = parse_qs(u.query)
        try:
            out = structure_pair(_q1(q, "path") or None, _q1(q, "file"))
        except Exception as e:
            out = {"ok": False, **_exc_msg(e)}
        self._raw_json(200, out)

    def _g_structure_tree(self, u):
        # «Source» popup file list; allow list, ~/.claude and *.jsonl refusal are inside structure_tree().
        try:
            out = structure_tree(_q1(parse_qs(u.query), "path") or None)
        except Exception as e:
            out = {"ok": False, **_exc_msg(e)}
        self._raw_json(200, out)

    def _g_structure_file(self, u):
        # One whole file for the «Source» popup; listing + realpath confinement, secret lock and redaction inside.
        q = parse_qs(u.query)
        try:
            out = structure_file(_q1(q, "path") or None, _q1(q, "file"), _q1(q, "line", "1"))
        except Exception as e:
            out = {"ok": False, **_exc_msg(e)}
        self._raw_json(200, out)

    def _g_structure_img(self, u):
        # Image bytes for inline Markdown images (R3/R4); same listing + realpath guards as structure_file.
        q = parse_qs(u.query)
        try:
            out = structure_img(_q1(q, "path") or None, _q1(q, "file"))
        except Exception as e:
            out = {"ok": False, **_exc_msg(e)}
        if isinstance(out, dict):
            self._raw_json(404, out)
            return
        data, ctype = out
        try:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            # ⚠svg is active content: sandbox + no script even if opened directly; nosniff comes from end_headers.
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; sandbox")
            self.end_headers()
            self.wfile.write(data)
        except (ConnectionResetError, BrokenPipeError):
            self.close_connection = True    # tab closed mid-response: normal, like _send

    def _g_structure(self, u):
        # Structure/growth treemap (how a project grows structurally).
        #   `path` is the absolute path of a «covered project» — omitted, it is sidereus itself.
        # ⚠Slow (cold 1.4-3.3s). Do not attach to polling — the screen calls it once on open.
        q = parse_qs(u.query)
        try:
            # ★`tests` defaults to 0 — tests are not the body. Only `1`/`true`/`on` enable it.
            _t = (q.get("tests") or ["0"])[0].strip().lower()
            # ★`full` — 1 only in the "+N more" drilldown (lifts the per-area cap).
            _f = (q.get("full") or ["0"])[0].strip().lower()
            # ⚠`only` = tests-only filter (2026-09-25) — passed through as a string; structure() normalizes 0/1/2.
            out = structure(_q1(q, "path") or None,
                            _t if _t in ("only", "2") else _t in ("1", "true", "on", "yes"),
                            _f in ("1", "true", "on", "yes"))
        except Exception as e:
            out = {"ok": False, **_exc_msg(e)}
        self._raw_json(200, out)

    def _g_arch(self, u):
        # Architecture map (verified module edges, metadata only). Allow list and store re-validation are inside arch_map.load().
        q = parse_qs(u.query)
        try:
            out = arch_load(_q1(q, "path") or None)
        except Exception as e:
            out = {"ok": False, **_exc_msg(e)}
        self._raw_json(200, out)

    def _g_arch_files(self, u):
        # Module detail «Files»: names under the module's stored path; allow list, id and path checks inside arch_map.files().
        q = parse_qs(u.query)
        try:
            out = arch_files(_q1(q, "path") or None, _q1(q, "id"))
        except Exception as e:
            out = {"ok": False, **_exc_msg(e)}
        self._raw_json(200, out)

    def _g_arch_secreport(self, u):
        # Security tab «Last report»: one report file; allow list, name pattern and file guards inside arch_map.security_report().
        q = parse_qs(u.query)
        try:
            out = arch_secreport(_q1(q, "path") or None, _q1(q, "name"))
        except Exception as e:
            out = {"ok": False, **_exc_msg(e)}
        self._raw_json(200, out)
