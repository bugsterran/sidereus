"""Bounded in-memory memo shared by every module (stdlib only, no sidereus imports)."""
import contextlib
import threading
from collections import OrderedDict

_NO = object()
MISS = object()   # pass as `default` when a cached value may itself be falsy


class BoundedMemo(OrderedDict):
    """Thread-safe LRU dict capped at `cap` entries.

    `get`/`put` refresh recency and `put` evicts least-recent entries past `cap`. Plain `d[k]`, `in`
    and iteration behave like a dict (no recency, no eviction), so readers and tests treat it as one.
    With `stamp=` the entry is stored as `(stamp, value)` and `get` returns `value` only while the
    stamp still matches (e.g. mtime or (mtime, size)).
    ⚠Callers that iterate it from several threads still need their own lock, as with a dict.
    """

    def __init__(self, cap):
        super().__init__()
        self.cap = cap
        self._lock = threading.Lock()

    def get(self, key, default=None, stamp=_NO):
        with self._lock:
            ent = OrderedDict.get(self, key, _NO)
            if ent is _NO or (stamp is not _NO and ent[0] != stamp):
                return default
            self.move_to_end(key)
        return ent if stamp is _NO else ent[1]

    def put(self, key, value, stamp=_NO):
        with self._lock:
            OrderedDict.pop(self, key, None)
            self[key] = value if stamp is _NO else (stamp, value)
            while len(self) > self.cap:
                self.popitem(last=False)
        return value

    def pop(self, key, *default):
        with self._lock:
            return OrderedDict.pop(self, key, *default)

    def clear(self):
        with self._lock:
            OrderedDict.clear(self)

    def copy(self):
        return OrderedDict(self)   # ⚠mock.patch.dict copies via copy(); the default would call __init__(mapping)


def _start(fn):
    threading.Thread(target=fn, name="bg-refresh", daemon=True).start()


def run_inline(fn):
    """`Refresher.spawn` for tests: the refresh runs in the caller, so the cache is filled when `kick` returns."""
    fn()


class Refresher:
    """At most one background run per key — request paths serve their own cache (any age) and `kick` the refresh.
    ⚠`fn` must store its result itself and catch its own errors; read the cache again after `kick` (an inline
    `spawn` has filled it). Instances are owned by the module that defines them, like BoundedMemo."""

    def __init__(self):
        self._on = set()
        self._lock = threading.Lock()
        self.spawn = _start

    def kick(self, key, fn):
        """Start fn() off the caller's thread unless `key` is already running; True when started."""
        with self._lock:
            if key in self._on:
                return False
            self._on.add(key)

        def run():
            try:
                fn()
            finally:
                with self._lock:
                    self._on.discard(key)
        try:
            self.spawn(run)
        except RuntimeError:   # thread limit: retried on the next poll
            with self._lock:
                self._on.discard(key)
            return False
        return True


# ★Load 105-135 on 12 CPUs (2026-11-04): /api/state stalled 30-60 s; `sample` showed 9 request threads parked on
#   live_probe's `_ps_snap_lock`/`_av_lock` behind spawns (ps 4 s, claude agents 6 s cap). ⇒ Inside `request_path()`
#   a probe never spawns or takes those locks: it kicks one off-thread refresh per key and serves its last value.
#   ⚠Background collectors (sessions refresh, term, live_probe._AV_BG) run outside the flag and spawn as before.
_req = threading.local()
_PROBE_BG = Refresher()
PROBE_ERR = {}               # probe key -> last exception its background refresh raised (kept off the thread's stderr)


@contextlib.contextmanager
def request_path():
    """Mark this thread as serving a request: probes answer from cache only (`serve_last`)."""
    prev = getattr(_req, "on", False)
    _req.on = True
    try:
        yield
    finally:
        _req.on = prev


def on_request_path():
    return bool(getattr(_req, "on", False))


def serve_last(key, refresh, read, max_age, clock):
    """Kick `refresh()` off-thread (one per key) and return `read()` = (measured at, value) if younger than
    max_age by `clock()`, else None (unknown). ⚠`refresh` records its own failure; read is taken after the kick
    because an inline spawn (tests) has just filled it."""
    def run():
        prev = getattr(_req, "on", False)
        _req.on = False        # ⚠an inline spawn runs on the caller's thread — the refresh itself must probe for real
        try:
            refresh()
            PROBE_ERR.pop(key, None)
        except Exception as e:  # ⚠the probe caches its own failure (e.g. `_ps_snap_fail`) and its readers warn
            PROBE_ERR[key] = e
            from sidereus.warn import warn_once   # lazy: memo is imported before warn by several modules
            # ⚠without this a refresh that fails every time is silent — the value just stays unknown
            warn_once("probe:" + key, "Background refresh {key} failed ({err}) — that value shows as unknown",
                      vars={"key": key, "err": type(e).__name__}, soft=True)
        finally:
            _req.on = prev
    _PROBE_BG.kick(key, run)
    at, val = read()
    return val if val is not None and clock() - at < max_age else None
