"""Bounded in-memory memo shared by every module (stdlib only, no sidereus imports)."""
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
