"""Shared timestamp formats (stdlib only, no sidereus imports, owns no globals).

Local-time helpers use time.localtime (truncates fractional seconds); iso_z uses UTC.
⚠ Keep formats byte-identical to the call sites they replaced: day keys ("%Y-%m-%d") are
compared as strings and stored in caches, and iso_z feeds transcript-style timestamps.
"""
import datetime
import time


def _local(ts):
    """time.localtime, but a pre-1970 value (a far-back cut-off) still formats.
    ⚠Windows localtime raises OSError Errno 22 for negative values; UTC arithmetic is close enough there."""
    try:
        return time.localtime(ts)
    except (OSError, OverflowError, ValueError):
        return (datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=int(ts))).timetuple()


def ymd(ts):
    """Local calendar day, e.g. 2026-09-26."""
    return time.strftime("%Y-%m-%d", _local(ts))


def iso_local(ts):
    """Local ISO-ish second precision, no zone suffix, e.g. 2026-09-26T14:05:09."""
    return time.strftime("%Y-%m-%dT%H:%M:%S", _local(ts))


def iso_z(ts):
    """UTC with a fixed .000Z suffix, matching Claude transcript timestamps."""
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(ts))
