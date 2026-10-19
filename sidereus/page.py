"""Page assembly (split out of chat_server.py 2026-09-24): web/index.html + `@@INCLUDE` parts -> one inline PAGE, and PAGE_BUILD."""
import glob
import hashlib
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
# X-Build-Time header value: when (UTC) and which page this process assembled, so a push gate can check the running build was seen on screen.
BUILD_TIME = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + " " + PAGE_BUILD
