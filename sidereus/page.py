"""Page assembly (split out of chat_server.py 2026-09-24): web/index.html + `@@INCLUDE` parts -> one inline PAGE, and PAGE_BUILD."""
import base64
import glob
import hashlib
import json
import os
import re
import time

from sidereus.config import ASSET_DIR

# ★Stage 1 split (2026-09-23): the page source lives in web/ — index.html is the skeleton, and each
#   `@@INCLUDE <file>@@` marker is replaced by that file's exact content (app-head.js, app.css, app.js).
#   The result is the same inline string as the old `PAGE = r"""..."""`, so served bytes and PAGE_BUILD are unchanged.
# ★Stage 2 (2026-09-23): a marker may be a glob (`js/*.js`, `css/*.css`) — matches are concatenated in sorted
#   name order, so the NN- prefix is the load order. ⚠Parts are joined with no separator: each file must keep its trailing newline.
# ⚠Read once at import — editing web/ still needs a server restart. newline="" keeps bytes exact (no newline translation).
# ⚠ASSET_DIR is the repo root in a clone (the old `dirname(chat_server.py)`), so WEB_DIR is unchanged there.
WEB_DIR = os.path.join(ASSET_DIR, "web")
_WEB_INCLUDE = re.compile(r"@@INCLUDE ([\w.*/-]+)@@")


def _load_page():
    def rd(name):
        path = os.path.join(WEB_DIR, name)
        try:
            with open(path, encoding="utf-8", newline="") as f:
                return f.read()
        except OSError as e:
            raise RuntimeError("chat_server: page file missing or unreadable: %s (%s)" % (path, e))

    def inc(name):
        if "*" not in name:
            return rd(name)
        hits = sorted(glob.glob(os.path.join(WEB_DIR, name)))
        if not hits:
            raise RuntimeError("chat_server: include pattern matched nothing: %s" % os.path.join(WEB_DIR, name))
        return "".join(rd(os.path.relpath(p, WEB_DIR)) for p in hits)
    return _WEB_INCLUDE.sub(lambda m: inc(m.group(1)), rd("index.html"))


PAGE = _load_page()

# ★Page build fingerprint — sent via /api/state; if the page's own differs, it shows a "refresh" banner.
#   Why: after a server restart **open tabs keep running the old JS.** One build in between had dead JS,
#   and the user experienced it as "sessions do not show" (server and API were fine). Removes a spot that goes stale silently.
PAGE_BUILD = hashlib.sha256(PAGE.encode("utf-8")).hexdigest()[:12]
PAGE = PAGE.replace("__PAGE_BUILD__", PAGE_BUILD)

# CSP script-src hashes (routes_get.PAGE_CSP): one per attribute-less inline <script> in PAGE, then the issues-window script.
# ⚠Computed after the __PAGE_BUILD__ replace — 00-core.js carries that marker inside the inline script.
# ⚠Never count `<script` occurrences: a JS string literal in 84l-structure-arch-checks.js holds one; the
#   non-greedy match consumes it inside the enclosing script, as the HTML parser does.
_INLINE_SCRIPT = re.compile(r"<script>(.*?)</script[\s/>]", re.S | re.I)
# ⚠The popup script is document.write()n into an about:blank window that inherits this CSP; it must stay an
#   escape-free double-quoted literal so the Python capture equals the JS value.
_ARCH_CW_JS = re.compile(r'const ARCH_CW_JS = "([^"\\]*)";')


def _csp_hash(text):
    # ⚠The HTML parser turns CRLF and lone CR into LF before hashing; an autocrlf checkout would otherwise blank the page.
    norm = text.replace("\r\n", "\n").replace("\r", "\n")
    return "'sha256-%s'" % base64.b64encode(hashlib.sha256(norm.encode("utf-8")).digest()).decode("ascii")


def _script_hashes(page):
    norm = page.replace("\r\n", "\n").replace("\r", "\n")
    out = [_csp_hash(m.group(1)) for m in _INLINE_SCRIPT.finditer(norm)]
    if not out:
        raise RuntimeError("chat_server: PAGE has no inline <script> to hash for the CSP")
    cw = _ARCH_CW_JS.search(norm)
    if not cw:
        raise RuntimeError("chat_server: ARCH_CW_JS literal not found (or holds an escape/quote); the issues window would be blocked by the CSP")
    out.append(_csp_hash(cw.group(1)))
    return tuple(out)


PAGE_SCRIPT_HASHES = _script_hashes(PAGE)
# X-Build-Time header value: when (UTC) and which page this process assembled, so a push gate can check the running build was seen on screen.
BUILD_TIME = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + " " + PAGE_BUILD


def _read_bytes(name):
    # ⚠Missing icon = empty bytes (route 404s) rather than a viewer that cannot start.
    try:
        with open(os.path.join(WEB_DIR, name), "rb") as f:
            return f.read()
    except OSError:
        return b""


# Web app manifest + icons (same origin, so the CSP stays unchanged); PNGs are made by scripts/make_icons.py.
ICON_SVG = _read_bytes("icon.svg")
ICON_PNG = {192: _read_bytes("icon-192.png"), 512: _read_bytes("icon-512.png")}
MANIFEST = json.dumps({
    "name": "Sidereus", "short_name": "Sidereus", "start_url": "/", "scope": "/", "display": "standalone",
    "background_color": "#0d1014", "theme_color": "#0d1014",
    "icons": [{"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"},
              {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
              {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"}],
}, indent=1).encode("utf-8")
PWA_FILES = {"/manifest.webmanifest": (MANIFEST, "application/manifest+json"), "/icon.svg": (ICON_SVG, "image/svg+xml"),
             "/icon-192.png": (ICON_PNG[192], "image/png"), "/icon-512.png": (ICON_PNG[512], "image/png")}


def pwa_reply(path):
    """(code, headers, body) for a manifest/icon path; fixed bytes per process, so no-cache (revalidate after a restart)."""
    body, ctype = PWA_FILES[path]
    if not body:
        return 404, [("Content-Type", "text/plain; charset=utf-8")], b"not found"
    return 200, [("Content-Type", ctype), ("Cache-Control", "no-cache"), ("X-Content-Type-Options", "nosniff")], body
