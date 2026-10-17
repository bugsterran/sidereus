"""Local usage index (ccusage replacement): per-file byte offsets into ~/.claude/projects/**/*.jsonl, hour buckets,
per-model prices/cost, 5h blocks, weekly keys and per-project dailies. Split from sidereus/usage.py (2026-09-24);
usage.py re-exports what others import. Owns _uidx/_uidx_lock (mutated in place, never rebound)."""
import glob
import json
import os
import re
import threading
import time
from sidereus.warn import warn_once
from sidereus.bus import _atomic_write
from sidereus.config import DATA_DIR
from sidereus.transcript import CLAUDE_PROJECTS, _line_ts
from sidereus.agents import slash, sub_globs, sub_sess_dir
from sidereus.claude_roots import accounts, acct_of, projects_dirs
from sidereus.timefmt import iso_z as _uidx_isoz, ymd


# ── Local usage index — ccusage replacement (2026-09-11) ───────────────────
# ★Why replaced (weekly tokens took far too long to load): measured `ccusage weekly --json`
#   **45.35s** · `blocks --json` **30.96s** · even with `--since` **41.68s**. What dominates is not the range but
#   **a full rescan of 2,273 files (2.86GB)** — every refresh rereads the same bytes.
# ⇒ Count the same source ourselves (`message.usage` in `~/.claude/projects/**/*.jsonl`).
#   **Per-file byte offsets** are saved in `usage-index.json`, so afterwards only newly appended tails are read.
#   Measured: first full scan **7.7 s** (2,277 files 2.86GB) · incremental **0.05 s** (changed files only).
# ⚠With `USAGE_LOCAL = False` (sidereus/usage.py) the old ccusage path runs as before (for comparison · do not delete).
USAGE_INDEX = os.path.join(DATA_DIR, "usage-index.json")
# ★Deduplication — measured 2026-09-11 (all 2,273 files · 317,900 usage lines):
#   duplicate tokens are **49.05%** (raw 84.81B → real 43.21B). Without dedup the screen doubles.
#   But of 159,072 duplicate pairs **only 80 (0.05%) cross files**, and within a file
#   **99.73% are on the very next line** (distance 1). The farthest is 779 lines (one file).
#   ⇒ No persistent seen-set (318k global keys). Dedup with **a per-file window of the last 2,048 keys**;
#     incrementally, rewind 8MB from the offset to refill the window (without counting), then continue counting.
#   ⚠Cost: the 80 cross-file duplicates (0.025% of lines) are not removed.
#     Check — this method 43,209,992,699 vs `ccusage` 43,210,604,294 = **0.0014%** difference.
UIDX_REWIND = 8_000_000
UIDX_V = 2                    # index format; another value on disk => full rescan (v2 added |long and |1h keys)
UIDX_WIN = 2048
# ★Per-model price ($/1M tokens) = [input, output]. Cache write = input×1.25 · cache read = input×0.1 (5-min TTL).
#   ★Basis: not written from memory but **back-computed from ccusage's own output** (2026-09-11 · weekly, full period,
#     6 per-model breakdowns). The back-computation matches ccusage's cost to the decimals —
#     opus-5 15,653.59283 ↔ 15,653.592827 · opus-4-8 10,029.30050 ↔ 10,029.3004925 ·
#     sonnet-5 432.47468 ↔ 432.4746800 · sonnet-4-6 323.845227 ↔ 323.84522865 ·
#     haiku-4-5 15.696280 ↔ 15.69628145 · opus-4-7 1,020.01814 ↔ 1,020.01816275.
#   ⚠The opus family is **$5/$25** (not $15/$75) — written from memory it would be 3x wrong.
#   ⚠No LiteLLM price cache on this disk (checked: none in `~/.cache` or `~/Library/Caches`, and the
#     ccusage bundle has no price table — it fetches over the network every time). Must work offline, so it is embedded.
#   Optional third value = cache read $/1M when it is not input×0.1. Rows below opus-5 come from the claude-api
#   skill model catalog (shared/models.md): opus-5-5 $4/$20 read $0.20 · fable-5-1 = mythos-5-1 $10/$50 read $0.25 ·
#   fable-5 = mythos-5 $10/$50 read $1. ⚠Same family is not same price (opus-5 $5 vs opus-5-5 $4) — exact ids only.
#   Rows from opus-4-6 down: official pricing page (platform.claude.com/docs/en/about-claude/pricing). Sonnet 5 $2/$10
#   is the standard rate; cache read is input×0.1 except fable-5-1/mythos-5-1 (0.025x), opus-5-5 and sonnet-5-5 (0.05x).
#   ★haiku-5-5 · sonnet-5-5: official pricing page, fetched 2026-10-12. Haiku 5.5 is tiered per request:
#     prompt (input + cache write + cache read) <=100k = $0.10/$0.50 · >100k = $0.50/$2.50 on the whole request.
#   ⇒ The tier is decided per request at scan time and stored as a separate key `<model>|long` (USAGE_TIER).
#   ★Cache writes: 5-min TTL = input x1.25, 1-hour TTL = input x2 (same page). The 1h share
#     (`usage.cache_creation.ephemeral_1h_input_tokens`) is stored under `<key>|1h` as [0, 0, cc1h, 0].
#   ⚠Suffixed keys hold disjoint tokens — never add one into its base key; show names via `_model_disp`.
#   claude-haiku-5 has no row on that page — left unknown on purpose.
USAGE_PRICE = {
    "claude-opus-5-5": (4.0, 20.0, 0.20),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-fable-5-1": (10.0, 50.0, 0.25),
    "claude-mythos-5-1": (10.0, 50.0, 0.25),
    "claude-fable-5": (10.0, 50.0),
    "claude-mythos-5": (10.0, 50.0),
    "claude-sonnet-5-5": (2.0, 10.0, 0.10),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-opus-4-5": (5.0, 25.0),
    "claude-opus-4-1": (15.0, 75.0),
    "claude-opus-4-0": (15.0, 75.0),
    "claude-opus-4": (15.0, 75.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-sonnet-4-0": (3.0, 15.0),
    "claude-sonnet-4": (3.0, 15.0),
    "claude-3-5-haiku": (0.80, 4.0),
}
# Per-request long-context tier: {bare id: (prompt threshold, price tuple shaped like USAGE_PRICE)}.
# Prompt = input + cache write + cache read; strictly above the threshold the whole request takes the long rate.
USAGE_TIER = {"claude-haiku-5-5": (100_000, (0.50, 2.50, 0.05))}
# Provider/variant wrappers around one model id: Bedrock `us.anthropic.…-v1:0`, Vertex `…@20250929`,
# dated `…-20251001`, `-latest`, Claude Code's `[1m]` context tag.
_MODEL_WRAP = re.compile(r"^(?:[a-z]{2,4}\.)?anthropic\.|\[[^\]]*\]$|@\d{8}$|-v\d+(?::\d+)?$|-\d{8}$|-latest$")


def _model_key(model):
    """Bare model id with provider prefixes and date/version suffixes removed."""
    m, prev = str(model or "").strip().lower(), None
    while m != prev:
        prev, m = m, _MODEL_WRAP.sub("", m)
    return m


def _key_split(key):
    """Index model key -> (model, is_long, is_1h). Suffix order is fixed: `model|long|1h`."""
    parts = str(key or "").split("|")
    return parts[0], "long" in parts[1:], "1h" in parts[1:]


def _model_disp(key):
    """Model name to show for an index key (tier/TTL suffixes dropped)."""
    return _key_split(key)[0]


def _tier_key(model, v):
    """Index key for one request's [in, out, cc, cr]: `model|long` when the prompt is above the model's tier."""
    m = str(model or "?")
    t = USAGE_TIER.get(m) or USAGE_TIER.get(_model_key(m))
    return m + "|long" if t and v[0] + v[2] + v[3] > t[0] else m


def _req_rows(model, u):
    """One request's usage dict -> [(key, [in, out, cc, cr])]; the 1h cache-write share goes to `<key>|1h`."""
    v = [int(u.get("input_tokens") or 0), int(u.get("output_tokens") or 0),
         int(u.get("cache_creation_input_tokens") or 0), int(u.get("cache_read_input_tokens") or 0)]
    cco = u.get("cache_creation")
    h1 = 0
    if isinstance(cco, dict):
        h1 = max(0, int(cco.get("ephemeral_1h_input_tokens") or 0))
        # ⚠A missing/smaller total would drop the 1h share and undercount the prompt for the tier.
        v[2] = max(v[2], max(0, int(cco.get("ephemeral_5m_input_tokens") or 0)) + h1)
    k = _tier_key(model, v)
    h1 = min(h1, v[2])
    if not h1:
        return [(k, v)]
    v[2] -= h1
    return [(k, v), (k + "|1h", [0, 0, h1, 0])]


def _req_cost(model, u):
    """(tokens, $) of one request's usage dict, priced with its tier and cache TTL."""
    tok, usd = 0, 0.0
    for k, v in _req_rows(model, u):
        tok += sum(v)
        usd += _cost4(k, v)
    return tok, usd


def _price(model):
    """Model price (index keys accepted; `|long` -> USAGE_TIER rate). **None if unknown** — never invent a cost."""
    m, lng, _h1 = _key_split(model)
    if lng:
        t = USAGE_TIER.get(m) or USAGE_TIER.get(_model_key(m))
        if t:
            return t[1]
    p = USAGE_PRICE.get(m) or USAGE_PRICE.get(_model_key(m))
    if p:
        return p
    if m and m != "<synthetic>":
        warn_once("price:" + m[:40], "Unknown model price ({model}) — tokens are counted but left out of cost",
                  vars={"model": m[:40]})
    return None


def _cost4(model, t):
    """[input, output, cache creation, cache read] -> $. A `|1h` key prices cache creation at input x2."""
    p = _price(model)
    if not p:
        return 0.0
    i, o = p[0], p[1]
    cr = p[2] if len(p) > 2 else i * 0.1
    cw = i * 2 if _key_split(model)[2] else i * 1.25
    return (t[0] * i + t[1] * o + t[2] * cw + t[3] * cr) / 1e6


#   Index shape: {path: {"sl": slug, "off": bytes scanned, "sz": size, "mt": mtime,
#                        "h": {"<UTC on-the-hour epoch>": {"<model>[|long][|1h]": [in, out, cc, cr]}}}}
# ★Why **hour buckets**: ccusage's 5-hour block starts at "first entry time floored to the hour", so boundaries
#   always fall on the hour ⇒ hour buckets reproduce blocks exactly. Local dates too: KST is a whole-hour offset
#   (+9h), so no bucket straddles two dates. So **one bucket type builds 5h, day and week.**
_uidx = {"files": {}, "at": 0.0, "loaded": False}
_uidx_lock = threading.Lock()


def _uidx_snap(h):
    """Two-level copy of one file's hour buckets; call under `_uidx_lock`.
    ⚠Callers loop outside the lock while `_uidx_scan` adds hour/model keys to the live dicts —
      iterating those raises "dictionary changed size during iteration" and blanks the result."""
    if not isinstance(h, dict):
        return {}
    return {k: (dict(mm) if isinstance(mm, dict) else mm) for k, mm in h.items()}


def _uidx_paths():
    out = []
    # ⚠Subagent files (plain + Workflow-tool agents) sit at varying depth — the project is the session dir's parent.
    # ⚠Every extra account root is globbed on each pass too (scan cost grows per root).
    for root in projects_dirs(CLAUDE_PROJECTS):
        for pat, sub in ((os.path.join(root, "*", "*.jsonl"), False),) + tuple((p, True) for p in sub_globs(root)):
            for fp in glob.glob(pat):
                d = os.path.dirname(fp)
                base = d if not sub else os.path.dirname(sub_sess_dir(fp))
                out.append((fp, os.path.basename(base)))
    return out


# ★Session title + branch for the History tab ride on this pass (no extra read):
#   "tc" = latest `custom-title` (/rename) · "ti" = latest `ai-title` (the /resume auto title) · "br" = latest `gitBranch`.
#   ⚠Only Claude Code's own title records are read — never conversation text, never the first prompt as a fallback.
UIDX_META_V = 1               # entries without "tv" get one bounded tail probe (old caches upgrade)
UIDX_META_PROBE = 2_000_000   # measured: ai-title is re-written through the file (up to 943 per file), so a tail has one
_BR_KEY = b'"gitBranch":"'


def _uidx_meta(raw, ent):
    # ★Measured on 143k lines: the top-level key sits in the first or last 4 KB (key order varies); a full-line
    #   find added ~46% to a cold scan.
    i = raw.find(_BR_KEY, 0, 4096)
    if i < 0 and len(raw) > 4096:
        i = raw.find(_BR_KEY, len(raw) - 4096)
    if i >= 0:
        j = i + len(_BR_KEY)
        k = raw.find(b'"', j)
        while k > 0 and raw[k - 1:k] == b"\\":
            k = raw.find(b'"', k + 1)
        s = raw[j:k] if k > j else b""
        if s and s != b"HEAD":          # detached HEAD is not a branch name
            try:
                b = json.loads(b'"' + s + b'"') if b"\\" in s else s.decode("utf-8")
            except Exception:
                b = ""
            if b:
                ent["br"] = b[:120]
    if len(raw) < 2048 and b'-title"' in raw:           # title records measured <= 134 bytes
        try:
            e = json.loads(raw)
        except ValueError:
            return                      # half-written or non-JSON record: no title from it
        t = e.get("type") if isinstance(e, dict) else None
        if t == "ai-title" and isinstance(e.get("aiTitle"), str) and e["aiTitle"].strip():
            ent["ti"] = e["aiTitle"].strip()[:200]
        elif t == "custom-title":
            v = e.get("customTitle") or e.get("title")
            if isinstance(v, str) and v.strip():
                ent["tc"] = v.strip()[:200]


def _uidx_meta_probe(fp, ent):
    """One-time tail read for an entry cached before titles existed. Returns bytes read."""
    ent["tv"] = UIDX_META_V
    if "/subagents/" in slash(fp):
        return 0
    try:
        with open(fp, "rb") as f:
            f.seek(0, 2)
            end = min(f.tell(), int(ent.get("off") or 0))
            seed = max(0, end - UIDX_META_PROBE)
            f.seek(seed)
            if seed:
                f.readline()
            n = 0
            while f.tell() < end:
                raw = f.readline()
                if not raw:
                    break
                n += len(raw)
                _uidx_meta(raw, ent)
            return n
    except OSError:
        return 0


def _uidx_scan(fp, ent):
    """Scan **only the newly appended part** of one file. Returns bytes read.
    ⚠If the file shrank or its mtime went backwards (copy, rollback), rescan that file from the start."""
    st = os.stat(fp)
    off = int(ent.get("off") or 0)
    if st.st_size < off or st.st_mtime + 2 < float(ent.get("mt") or 0):
        ent["h"] = {}
        for k in ("ti", "tc", "br"):
            ent.pop(k, None)
        off = 0
    ent["tv"] = UIDX_META_V
    meta = "/subagents/" not in slash(fp)
    h = ent.setdefault("h", {})
    seed = max(0, off - UIDX_REWIND)
    win, wset, wi = [], set(), 0
    end, read = off, 0
    with open(fp, "rb") as f:
        f.seek(seed)
        pos = seed
        if seed:
            pos += len(f.readline())        # drop the first line cut by the rewind
        while True:
            raw = f.readline()
            if not raw:
                break
            p0 = pos
            pos += len(raw)
            read += len(raw)
            if not raw.endswith(b"\n"):
                break                        # tail still being written — look again next refresh
            if p0 >= off:
                end = pos
            if meta:
                _uidx_meta(raw, ent)
            if b'"usage"' not in raw:
                continue
            try:
                e = json.loads(raw)
            except Exception:
                continue
            m = e.get("message") or {}
            u = m.get("usage")
            if not isinstance(u, dict):
                continue
            # ⚠**Zero-token lines are not dropped either** (measured 2026-09-11): these lines **set the start**
            #   of 5-hour blocks. Dropping them shifted 41 of 378 block boundaries by 1~2 hours, leaking tokens into
            #   neighboring blocks (e.g. cc `05-27T04:00` vs ours `05-27T05:00`). Totals match, but
            #   "the current block" differs.
            mid, rid = m.get("id") or "", e.get("requestId") or ""
            if mid and rid:                  # lines without a key are not deduped (measured: 0 such lines)
                key = mid + "\x00" + rid
                if key in wset:
                    continue
                if len(win) < UIDX_WIN:
                    win.append(key)
                else:
                    wset.discard(win[wi])    # ring buffer — `pop(0)` would shift 2048 slots every time
                    win[wi] = key
                    wi = (wi + 1) % UIDX_WIN
                wset.add(key)
            if p0 < off:
                continue                     # rewind zone — fill the window only, **do not count**
            t = _line_ts(e, 0)
            if not t:
                continue
            hb = h.setdefault(str(int(t // 3600) * 3600), {})
            for k, v in _req_rows(m.get("model") or "?", u):
                row = hb.setdefault(k, [0, 0, 0, 0])
                for i in range(4):
                    row[i] += v[i]
    ent["off"], ent["sz"], ent["mt"] = end, st.st_size, st.st_mtime
    return read


def _uidx_save():
    with _uidx_lock:
        blob = json.dumps({"v": UIDX_V, "files": _uidx["files"]}, ensure_ascii=False,
                          separators=(",", ":"))
    try:
        # ⚠atomic swap — reading a half-written index means a full rescan
        _atomic_write(USAGE_INDEX, blob.encode("utf-8"), prefix=".usage-index.")
    except OSError as e:
        warn_once("uidx-save", "usage index save failed ({err}) — full rescan on restart",
                  vars={"err": f"{type(e).__name__}: {e}"}, soft=True)


def _uidx_refresh(max_age=30):
    """Bring the index up to date. Reads **only new tails of changed files**. (files scanned, bytes scanned)."""
    now = time.time()
    with _uidx_lock:
        if not _uidx["loaded"]:
            _uidx["loaded"] = True
            try:
                with open(USAGE_INDEX, encoding="utf-8") as f:
                    d = json.load(f)
                if isinstance(d, dict) and d.get("v") == UIDX_V and isinstance(d.get("files"), dict):
                    _uidx["files"] = d["files"]
            except Exception:
                pass                          # missing or corrupt ⇒ full rescan — pass quietly
        if _uidx["at"] and now - _uidx["at"] < max_age:
            return (0, 0)
        files = _uidx["files"]
        seen, nch, rd = set(), 0, 0
        for fp, slug in _uidx_paths():
            seen.add(fp)
            ent = files.get(fp)
            if ent is None:
                ent = files[fp] = {"sl": slug, "off": 0, "sz": -1, "mt": 0.0, "h": {}}
            ent["sl"] = slug
            try:
                st = os.stat(fp)
                if st.st_size == ent.get("sz") and abs(st.st_mtime - (ent.get("mt") or 0)) < 0.5:
                    if ent.get("tv") != UIDX_META_V:
                        rd += _uidx_meta_probe(fp, ent)
                        nch += 1
                    continue
                rd += _uidx_scan(fp, ent)
                nch += 1
            except OSError:
                continue
        for fp in [k for k in files if k not in seen]:
            files.pop(fp, None)               # deleted transcripts are removed from the index too
        _uidx["at"] = now
    if nch:
        _uidx_save()
    return (nch, rd)


def _uidx_hours():
    """Fold all files' hour buckets into one. {on-the-hour epoch: {model: [in, out, cc, cr]}}."""
    out = {}
    with _uidx_lock:
        vals = [_uidx_snap(e.get("h")) for e in _uidx["files"].values()]
    for h in vals:
        for k, mm in h.items():
            a = out.setdefault(int(k), {})
            for mdl, v in mm.items():
                b = a.get(mdl)
                if b is None:
                    a[mdl] = list(v)
                else:
                    for i in range(4):
                        b[i] += v[i]
    return out


def _blocks_local(hours, now=None):
    """Hour buckets -> 5-hour blocks **identical** to ccusage's.
    ★ccusage rule (`identifySessionBlocks`): ① block start = first entry floored to the hour ②
      new block if `t-blockStart > 5h` **or** `t-prevEntry > 5h`. The latter half of ② can never fire alone
      (prevEntry ≥ blockStart, so `t-prev ≤ t-start`) ⇒ hour buckets alone yield the same boundaries."""
    now = now or time.time()
    out, cur = [], None
    for k in sorted(hours):
        if cur is None or k - cur["start"] >= 18000:
            cur = {"start": k, "t": [0, 0, 0, 0], "cost": 0.0, "last": k}
            out.append(cur)
        cur["last"] = k
        for mdl, v in hours[k].items():
            for i in range(4):
                cur["t"][i] += v[i]
            cur["cost"] += _cost4(mdl, v)
    docs = []
    for b in out:
        s, e = b["start"], b["start"] + 18000
        docs.append({
            "id": _uidx_isoz(s), "startTime": _uidx_isoz(s), "endTime": _uidx_isoz(e),
            "isActive": bool(now < e and now - (b["last"] + 3600) < 18000),
            "totalTokens": sum(b["t"]), "costUSD": round(b["cost"], 4),
            "tokenCounts": {"inputTokens": b["t"][0], "outputTokens": b["t"][1],
                            "cacheCreationInputTokens": b["t"][2],
                            "cacheReadInputTokens": b["t"][3]}})
    return docs


def _uidx_week(ts):
    """**Local date of the start (Sunday) of the calendar week** containing the time. Same basis as ccusage `weekly`."""
    lt = time.localtime(ts)
    mid = time.mktime(lt[:3] + (0, 0, 0, 0, 0, -1))
    return ymd(mid - ((lt.tm_wday + 1) % 7) * 86400)




def _uidx_sid(fp):
    """Session id of a transcript path: the session dir for subagent files, else the file name."""
    sd = sub_sess_dir(fp)
    return os.path.basename(sd) if sd else os.path.splitext(os.path.basename(fp))[0]


def _uidx_projects(nd, acct=""):
    """Build `projects` in **the same shape** as `ccusage daily --json --instances --since`:
    {slug: [{date, inputTokens, …, totalTokens, totalCost, modelBreakdowns}]}.
    `acct` = account label: keep only files that account ran ("" = every file, unchanged)."""
    _uidx_refresh()
    cut = ymd(time.time() - (int(nd) - 1) * 86400)
    if acct:
        # ⚠acct_of reads per-session records from disk — never under _uidx_lock (the scan holds it for seconds).
        with _uidx_lock:
            fl = [(fp, (e.get("sl") or "?"), _uidx_snap(e.get("h"))) for fp, e in _uidx["files"].items()]
        prim = next((a["label"] for a in accounts() if a.get("primary")), "")
        # ⚠Period cut first, one lookup per sid: a lookup per indexed file would evict acct_of's bounded memo.
        memo, items = {}, []
        for fp, sl, h in fl:
            if not h or ymd(max(int(k) for k in h)) < cut:
                continue
            sid = _uidx_sid(fp)
            if sid not in memo:
                memo[sid] = acct_of(sid, fp)[0] or prim
            if memo[sid] == acct:
                items.append((sl, h))
    else:
        with _uidx_lock:
            items = [((e.get("sl") or "?"), _uidx_snap(e.get("h"))) for e in _uidx["files"].values()]
    dc, P = {}, {}
    for slug, h in items:
        for k, mm in h.items():
            ki = int(k)
            d = dc.get(ki)
            if d is None:
                d = dc[ki] = ymd(ki)
            if d < cut:
                continue
            days = P.setdefault(slug, {})
            a = days.get(d)
            if a is None:
                a = days[d] = {"date": d, "inputTokens": 0, "outputTokens": 0,
                               "cacheCreationTokens": 0, "cacheReadTokens": 0,
                               "totalTokens": 0, "totalCost": 0.0, "_m": {}}
            for mdl, v in mm.items():
                c = _cost4(mdl, v)
                a["inputTokens"] += v[0]
                a["outputTokens"] += v[1]
                a["cacheCreationTokens"] += v[2]
                a["cacheReadTokens"] += v[3]
                a["totalTokens"] += v[0] + v[1] + v[2] + v[3]
                a["totalCost"] += c
                b = a["_m"].setdefault(_model_disp(mdl), [0, 0, 0, 0, 0.0])
                for i in range(4):
                    b[i] += v[i]
                b[4] += c
    out = {}
    for slug, days in P.items():
        rows = []
        for d in sorted(days):
            a = days[d]
            a["modelBreakdowns"] = [
                {"modelName": mk, "inputTokens": mv[0], "outputTokens": mv[1],
                 "cacheCreationTokens": mv[2], "cacheReadTokens": mv[3], "cost": mv[4]}
                for mk, mv in a.pop("_m").items()]
            rows.append(a)
        out[slug] = rows
    return out
