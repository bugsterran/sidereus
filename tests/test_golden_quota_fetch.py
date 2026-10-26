"""Golden trace for `_quota_fetch` (guards the behaviour-preserving phase split).

Every dependency is replaced by a recording stub: clock, token reader, urllib Request/urlopen,
warn_once, _cc_account, _iso_ts, the lock, the `_quota` slot and `_quota_retry_after`.
The golden holds, per case, the ordered call trace (incl. lock enter/exit and each slot write),
the final slot, the retry-after cell and the return value. No network, no live file, no real clock.
Regenerate only for an intended change:
    GOLDEN_UPDATE=1 /usr/bin/python3 -m unittest tests.test_golden_quota_fetch
"""
import json
import os
import socket
import unittest
import urllib.error
import urllib.request

from tests._load import sidereus

q = sidereus("quota_fetch")   # the fetch phases read these names from their own module

GOLD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden", "quota_fetch.json")
NOW = 1_790_000_000.0
FUT = "2027-01-01T00:00:00+00:00"
PAST = "2020-01-01T00:00:00Z"


def _snap(v):
    return json.loads(json.dumps(v, default=repr))


def _http(code, hdrs):
    return urllib.error.HTTPError("https://x", code, "m", hdrs, None)


def _ok(obj):
    return ("ok", json.dumps(obj).encode("utf-8"))


H5 = {"utilization": 42.5, "resets_at": FUT}
D7 = {"utilization": 10, "resets_at": FUT}
EX = {"is_enabled": True, "utilization": 24.0, "used_credits": 1234, "monthly_limit": 5000, "currency": "EUR"}
PREV = {"five_hour": {"pct": 99, "resets_at": FUT}, "seven_day": {"pct": 58, "resets_at": FUT}}
PREV_MIX = {"five_hour": {"pct": 70, "resets_at": PAST},
            "seven_day": {"pct": 30, "resets_at": None, "keptAt": NOW - 3600}}
PREV_OLD = {"five_hour": {"pct": 70, "resets_at": None},
            "seven_day": {"pct": 0, "resets_at": FUT}}
BASE = {"data": None, "at": 0, "err": None, "next": 0}

# (name, token, urlopen result, account, initial _quota extra fields)
CASES = [
    ("no_token", None, None, "A", {}),
    ("empty_token", "", None, "A", {}),
    ("ok_both", "tok", _ok({"five_hour": H5, "seven_day": D7}), "A", {}),
    ("ok_extra", "tok", _ok({"five_hour": H5, "seven_day": D7, "extra_usage": EX}), "A", {}),
    ("ok_extra_nocur", "tok", _ok({"five_hour": H5, "extra_usage": dict(EX, currency=None)}), None, {}),
    ("ok_extra_disabled", "tok", _ok({"five_hour": H5, "extra_usage": {"is_enabled": False}}), "A", {}),
    ("ok_extra_notdict", "tok", _ok({"seven_day": D7, "extra_usage": [1]}), "A", {}),
    ("http_401", "tok", _http(401, {}), "A", {}),
    ("http_429_ra", "tok", _http(429, {"Retry-After": "120"}), "A", {}),
    ("http_429_ra_lower", "tok", _http(429, {"retry-after": "7.9"}), "A", {}),
    ("http_429_ra_huge", "tok", _http(429, {"Retry-After": "99999"}), "A", {}),
    ("http_429_ra_neg", "tok", _http(429, {"Retry-After": "-5"}), "A", {}),
    ("http_429_ra_bad", "tok", _http(429, {"Retry-After": "soon"}), "A", {}),
    ("http_500", "tok", _http(500, None), "A", {}),
    ("http_503", "tok", _http(503, {"X": "1"}), "A", {}),
    ("timeout", "tok", socket.timeout("timed out"), "A", {}),
    ("timeout_err", "tok", TimeoutError("t"), "A", {}),
    ("url_error", "tok", urllib.error.URLError("dns"), "A", {}),
    ("bad_json", "tok", ("ok", b"{not json"), "A", {}),
    ("bad_utf8", "tok", ("ok", b"\xff\xfe"), "A", {}),
    ("top_list", "tok", _ok([1, 2]), "A", {}),
    ("top_null", "tok", _ok(None), "A", {}),
    ("member_str", "tok", _ok({"five_hour": "x", "seven_day": D7}), "A", {}),
    ("member_both_bad", "tok", _ok({"five_hour": 3, "seven_day": [1]}), "A", {}),
    ("util_none", "tok", _ok({"five_hour": {"utilization": None}, "seven_day": {}}), "A", {}),
    ("empty_body", "tok", _ok({}), "A", {}),
    ("both_null_fresh", "tok", _ok({"five_hour": None, "seven_day": None}), "A", {}),
    ("both_null_prev", "tok", _ok({"five_hour": None, "seven_day": None}), "A",
     {"data": PREV, "at": NOW - 100, "acct": "A", "src": "omc"}),
    ("missing_prev", "tok", _ok({"extra_usage": EX}), "A",
     {"data": PREV, "at": NOW - 100, "acct": "A"}),
    ("prev_mix", "tok", _ok({"five_hour": None, "seven_day": None}), "A",
     {"data": PREV_MIX, "at": NOW - 50, "acct": "A"}),
    ("prev_old", "tok", _ok({"five_hour": None, "seven_day": None}), "A",
     {"data": PREV_OLD, "at": NOW - 7 * 3600, "acct": "A"}),
    ("prev_old_recent", "tok", _ok({"five_hour": None, "extra_usage": EX}), "A",
     {"data": PREV_OLD, "at": NOW - 3600, "acct": "A"}),
    ("acct_change", "tok", _ok({"five_hour": None, "seven_day": D7}), "B",
     {"data": PREV, "at": NOW - 100, "acct": "A"}),
    ("acct_none_keeps", "tok", _ok({"five_hour": None}), None,
     {"data": PREV, "at": NOW - 100, "acct": "A"}),
    ("acct_first", "tok", _ok({"five_hour": H5}), "A", {"data": PREV, "at": NOW - 100}),
    ("real_overrides_prev", "tok", _ok({"five_hour": H5, "seven_day": None}), "A",
     {"data": PREV, "at": NOW - 100, "acct": "A"}),
    ("fail_keeps_prev", "tok", _http(429, {}), "A", {"data": PREV, "at": NOW - 100, "acct": "A"}),
]


class _Lock:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        self.log.append(["enter"])

    def __exit__(self, *a):
        self.log.append(["exit"])
        return False


class _Slot(dict):
    def __init__(self, log, init):
        super().__init__(init)
        self.log = log

    def __setitem__(self, k, v):
        self.log.append(["slot_set", k, _snap(v)])
        super().__setitem__(k, v)


class _Cell(list):
    def __init__(self, log, init):
        super().__init__(init)
        self.log = log

    def __setitem__(self, i, v):
        self.log.append(["ra_set", i, v])
        super().__setitem__(i, v)


class _Resp:
    def __init__(self, log, data):
        self.log, self.data = log, data

    def __enter__(self):
        self.log.append(["resp_enter"])
        return self

    def __exit__(self, *a):
        self.log.append(["resp_exit", a[0].__name__ if a[0] else None])
        return False

    def read(self):
        self.log.append(["read"])
        return self.data


def _run_case(case):
    name, tok, res, acct, extra = case
    log = []

    class T:
        @staticmethod
        def time():
            log.append(["time"])
            return NOW

    def fake_tok():
        log.append(["oauth_token"])
        return tok

    def fake_request(url, headers=None, **kw):
        log.append(["Request", url, sorted((headers or {}).items()), sorted(kw)])
        return ("REQ", url)

    def fake_urlopen(req, timeout=None, **kw):
        log.append(["urlopen", list(req), timeout, sorted(kw)])
        if isinstance(res, BaseException):
            raise res
        return _Resp(log, res[1])

    def fake_warn(key, msg, vars=None):
        log.append(["warn_once", key, msg, vars])

    def fake_acct():
        log.append(["cc_account"])
        return acct

    def fake_iso(s):
        r = _REAL_ISO(s)
        log.append(["iso_ts", s, r])
        return r

    slot = _Slot(log, _snap(dict(BASE, **extra)))
    cell = _Cell(log, [0])
    # ⚠IS_MAC pinned: the no-token message differs off macOS (keychain vs .credentials.json) and the golden holds the macOS one.
    patches = {"IS_MAC": True, "time": T, "_oauth_token": fake_tok, "warn_once": fake_warn,
               "_cc_account": fake_acct, "_iso_ts": fake_iso,
               "_quota": slot, "_quota_lock": _Lock(log), "_quota_retry_after": cell}
    saved = {k: getattr(q, k) for k in patches}
    saved_req = (urllib.request.Request, urllib.request.urlopen)
    try:
        for k, v in patches.items():
            setattr(q, k, v)
        urllib.request.Request, urllib.request.urlopen = fake_request, fake_urlopen
        try:
            ret = ["ret", q._quota_fetch()]
        except Exception as e:
            ret = ["raise", type(e).__name__, str(e)]
    finally:
        urllib.request.Request, urllib.request.urlopen = saved_req
        for k, v in saved.items():
            setattr(q, k, v)
    return {"trace": log, "ret": ret, "slot": _snap(dict(slot)), "ra": list(cell)}


_REAL_ISO = q._iso_ts


def capture():
    out = {c[0]: _run_case(c) for c in CASES}
    return json.dumps(out, sort_keys=True, ensure_ascii=False, indent=1) + "\n"


class TestGoldenQuotaFetch(unittest.TestCase):
    def test_trace(self):
        text = capture()
        if os.environ.get("GOLDEN_UPDATE") == "1":
            os.makedirs(os.path.dirname(GOLD), exist_ok=True)
            with open(GOLD, "w", encoding="utf-8") as f:
                f.write(text)
        with open(GOLD, encoding="utf-8") as f:
            self.assertEqual(text, f.read())

    def test_no_live_state_touched(self):
        before = json.dumps([q._quota, q._quota_retry_after], sort_keys=True, default=str)
        capture()
        self.assertEqual(before, json.dumps([q._quota, q._quota_retry_after], sort_keys=True, default=str))
        self.assertEqual(urllib.request.urlopen.__module__, "urllib.request")


if __name__ == "__main__":
    unittest.main()
