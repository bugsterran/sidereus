"""Frozen clock for tests: tests never read the real clock.

`frozen(mod, ...)` swaps each module's own `time` / `datetime` attribute, so only
the modules under test see the fixed instant and the test runner keeps real time.
⚠A module that did `from time import time` (or `from datetime import datetime`
under another name) holds the function itself; patch that name directly.
"""
import datetime as _dt
import functools
import time as _real_time

NOW = 1767225600.0  # 2026-01-01T00:00:00Z


class _TimeProxy(object):
    """Stands in for the `time` module; only time()/time_ns() are frozen."""

    def __init__(self, at):
        self._at = float(at)

    def time(self):
        return self._at

    def time_ns(self):
        return int(self._at * 1e9)

    def __getattr__(self, name):
        return getattr(_real_time, name)


def _frozen_datetime(at):
    class FrozenDatetime(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            # naive now() is local time of `at`, like the real datetime.now()
            return _dt.datetime.fromtimestamp(at, tz)

        @classmethod
        def utcnow(cls):
            return _dt.datetime.utcfromtimestamp(at)

    return FrozenDatetime


class frozen(object):
    """Context manager / decorator freezing `time` and `datetime` on the given modules."""

    def __init__(self, *mods, **kw):
        self.mods = mods
        self.at = float(kw.pop("at", NOW))
        if kw:
            raise TypeError("unexpected arguments: %s" % ", ".join(sorted(kw)))
        self._saved = []

    def __enter__(self):
        proxy = _TimeProxy(self.at)
        fdt = _frozen_datetime(self.at)
        for m in self.mods:
            if hasattr(m, "time") and getattr(m, "time") is _real_time:
                self._saved.append((m, "time", m.time))
                m.time = proxy
            cur = getattr(m, "datetime", None)
            if isinstance(cur, type) and issubclass(cur, _dt.datetime):
                self._saved.append((m, "datetime", cur))
                m.datetime = fdt
        return self

    def __exit__(self, *exc):
        while self._saved:
            m, name, old = self._saved.pop()
            setattr(m, name, old)
        return False

    def __call__(self, fn):
        @functools.wraps(fn)
        def wrapper(*a, **k):
            with frozen(*self.mods, at=self.at):
                return fn(*a, **k)
        return wrapper
