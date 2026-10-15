#!/usr/bin/env python3
"""Event stream for session notifications — prints **one line** per item addressed to me and keeps watching.

vs watch_bus.py: that one **exits** on new mail (the background-exit notice is the alert);
this one is for Monitor where **one line = one alert**, so it never exits. Different roles; both run.
  · launchd(watch_loop.sh → watch_bus.py) : always on, session-independent. Loss prevention (cursor).
  · session Monitor (this file)           : wakes my session immediately.

★Watches rooms too — once a conversation moves into a room, watching only `to` misses room posts.
★Lives next to the code — the scratchpad path changes per session, so scripts there vanished (measured).

Usage: python3 ~/.mailbox-mcp/monitor_stream.py     (with Monitor persistent:true)
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# ★The routing decision lives **only in mailbox_core** — separate copies once got fixed on one side only (see core comments).
from mailbox_core import (rows, latest_t, my_rooms, new_for_me, where, touch_presence, mark_ack, acks,
                          mine, thread_state, is_closed)

POLL_S = 2                       # the human viewer polls at 2.5s; stay faster (otherwise I always learn last)

# ── Token savings (2026-08-19) ────────────────
#   ★Found the axis by measurement first. Cost is dominated by **wake count × session context**, not body bytes:
#     all bus bodies 552 posts 1,018,420 chars ≈ 727k tokens (2-week total) vs **one session wake = 985k tokens once**.
#     204 wakes. One wake costs hundreds of times one body ⇒ **not waking** is the only large saving.
#
#   ① Batch wakes — measured bursts: a 2-min window cuts wakes 552→320 (42%), 5 min → 209 (62%).
#      Discussions arrive in bursts (quick replies, follow-ups), so batching is not late. Only urgent posts pass immediately.
#   ② **Carry the id** in the alert — this was the real cause of duplication. Without an id, `mailbox_ack` required
#      calling `mailbox_inbox`, which pulled **the full body into context a second time**.
#      ⛔Do not fix this by dropping the body from the alert — that reverts the 2026-08 incident lesson
#        (subject-only alerts led to "act on the summary" and a warning that was only in the body was missed · see below).
#   ③ **Raise** the cap 1800 → 3000 chars (not lower). At 1800, **50% were truncated** and that half
#      called inbox again for the full text. At 3000 only 7% are truncated (measured).
#   ④ Posts that need no reply (share/notice tags, [FYI]) **do not wake**; they get one line in the next batch.
#      ⚠Cursors are separate (stream-*.cursor vs read-*.cursor), so skipped alerts still remain in `mailbox_inbox`.
HOLD_QUIET_S = int(os.environ.get("MAILBOX_HOLD_QUIET_S", "60"))   # flush the batch after this much quiet
HOLD_MAX_S = int(os.environ.get("MAILBOX_HOLD_MAX_S", "180"))      # always flush by this time, even if posts keep coming
BODY_CAP = int(os.environ.get("MAILBOX_BODY_CAP", "3000"))
URGENT_TAGS = {"긴급", "요청", "질문", "차단", "URGENT"}            # these tags and 1:1 posts skip batching
QUIET_TAGS = {"공유", "통지", "FYI", "참고"}                        # posts with only these tags do not wake

# MAILBOX_ME -> config self.ids[0]. ⚠ the cursor file name below derives from this; keep it stable.
import mailbox_config  # noqa: E402
ME_ID = os.environ.get("MAILBOX_ME") or (mailbox_config.get("self", {}).get("ids") or [""])[0]
if not ME_ID:
    sys.exit("⚠no identity — set MAILBOX_ME or self.ids in config.local.json")
# ★The baseline is **persisted to a file** — it used to be `latest_t(rows())` at startup, so posts that arrived
#   while the watcher was down fell below the baseline and were **never alerted** (measured 2026-08-07: a mail
#   went unseen until someone checked by hand). watch_bus.py already used a cursor — only this file lacked one.
CURSOR = os.path.join(mailbox_config.data_dir(), f"stream-{ME_ID}.cursor")   # data dir, not the code dir
_cur = rows()
try:
    seen_t = int(open(CURSOR, encoding="utf-8", errors="replace").read().strip())
except Exception:
    seen_t = latest_t(_cur)          # first run only — do not re-alert the whole past
# ★If identity is misconfigured, **no post is mine**, and the loop below just advances the cursor,
#   swallowing those posts forever (measured 2026-08-07: MAILBOX_ME set without MAILBOX_SELF made
#   every peer post filter as 'sent by me' — the watcher was alive and silently lost 2 posts).
#   To avoid failing silently, print identity at startup and flag a mismatch loudly.
# Check **the values the routing actually uses**, not env vars — stays valid if derivation rules change.
import mailbox_core as _core
_ids_cache = (0.0, set())


def _registered_ids():
    """All registered identities — identity.json (path→id) · profiles.json (id→role). 5-min cache."""
    global _ids_cache
    if time.time() - _ids_cache[0] < 300 and _ids_cache[1]:
        return _ids_cache[1]
    import json as _json
    got = set()
    for _fn, _pick in (("identity.json", lambda d: d.values()), ("profiles.json", lambda d: d.keys())):
        try:
            with open(os.path.join(_core.HOME, _fn), encoding="utf-8") as f:
                got |= {str(x) for x in _pick(_json.load(f))}
        except Exception:
            pass          # no registry → conservatively judged «no owner» (only means more frequent warnings)
    _ids_cache = (time.time(), got)
    return got


if ME_ID not in _core.ME or ME_ID not in _core.SELF:
    print(f"⚠신원 어긋남 — MAILBOX_ME={ME_ID} 인데 판정값 ME={sorted(_core.ME)} · SELF={sorted(_core.SELF)}."
          " 남의 글이 '내 발신' 으로 걸러진다. 감시는 살아 있어도 글이 안 온다.", flush=True)
elif _registered_ids() and ME_ID not in _registered_ids():
    # ★The skip warning below no longer counts «owned posts» as evidence (2026-09-22), so a typo'd identity
    #   is caught here — an unregistered id receives nothing, since nobody sends to it; delivery stays 0 forever.
    print(f"⚠미등록 신원 — MAILBOX_ME={ME_ID} 가 identity.json·profiles.json 어디에도 없다."
          " 오타이거나 등록 전이면 이 주소로는 아무도 보내지 않는다.", flush=True)
gap = new_for_me(seen_t, _cur)
print(f"메일박스 감시 시작 — {ME_ID} · bus {len(_cur)}줄 · 기준 t={seen_t} · 방 {sorted(my_rooms()) or '없음'}"
      + (f" · ★꺼져 있던 동안 온 글 {len(gap)}건" if gap else ""), flush=True)
# ★**The system re-alerts** unconfirmed posts — the problem was a design where the user had to nag
#   before mail got checked. Not left to habit: if something stays unconfirmed, the alert comes again.
SKIP_QUIET_S = int(os.environ.get("MAILBOX_SKIP_QUIET_S", "1800"))  # skip warning only after delivery has been 0 this long
NAG_AFTER_S = int(os.environ.get("MAILBOX_NAG_S", "300"))        # eligible after 5 min unconfirmed
NAG_EVERY_S = int(os.environ.get("MAILBOX_NAG_EVERY_S", "600"))  # re-alert interval (not every poll)
# ★Needs an age cap — 112 posts predate the ack convention; alerting all of them causes **alert fatigue and neglect**.
#   Old posts are not current work. By default only posts within 24h are nagged.
NAG_MAX_AGE_S = int(os.environ.get("MAILBOX_NAG_MAX_AGE_S", "86400"))
# ★**How many times** to nag one post. Previously uncapped: every 10 min for 24h = up to 144
#   nags, and each wake is a request that re-reads the whole session context (same shape as
#   541 acks costing 60M). The signal is all in the first one or two; after that it's fatigue — cut the tail.
#   Nothing is lost: posts no longer nagged still remain in the `mailbox_inbox` list.
NAG_MAX_TIMES = int(os.environ.get("MAILBOX_NAG_MAX_TIMES", "2"))
_nag_count = {}                  # id -> times nagged so far
_last_skip_log = 0.0
_last_nag = 0.0            # 0 = report once right after startup (don't make unconfirmed wait 10 min)
_pending = []              # posts not yet emitted (batch) — ★cursor advances **on emit** (so a crash re-alerts)
_heard_t = seen_t          # in-memory baseline (avoid re-collecting). Unlike the cursor (seen_t), not persisted
_hold_since = 0.0          # when batching started
_quiet_held = 0            # count of share-tag posts passed without waking
_last_deliver = time.time()  # ★last time a «post to me» was emitted. Gates the skip warning:
                             #   while delivery runs, delivery itself proves identity is correct — the warning is meaningless then


def _tag_of(r):
    import re as _re
    m = _re.match(r"^\s*\[([^\]]{1,20})\]", r.get("subject") or "")
    return (m.group(1).strip() if m else "")


def _urgent(r):
    """Posts that wake immediately without batching — an urgent tag, or **a 1:1 addressed to me**."""
    t = _tag_of(r)
    return t in URGENT_TAGS or t.upper() in URGENT_TAGS or (r.get("to") == ME_ID and not r.get("room"))


def _quiet(r):
    t = _tag_of(r)
    return t in QUIET_TAGS or t.upper() in QUIET_TAGS


def _suspect(r, myrooms):
    """Is a skipped post evidence that «my identity is wrong»?

    ★Measured 2026-09-22 (Sidereus): the warning "skipped N · delivery 0 for 299,655s" fired for 83 hours
      while identity was correct (ME=SELF=Sidereus · registered). All 16 new bus posts in that span were in
      **room-A, a room I had not joined**, and 1:1s to Sidereus were 0 in the whole 972-line bus — «delivery 0»
      was normal; only the warning was wrong. The old condition was «any post by others», so a quiet identity nags forever.
    ⇒ Posts with another owner are not counted. Only two kinds of evidence:
      ⓐ a post in **my room** that got filtered — SELF overreach (the shape of the 2026-08-07 incident)
      ⓑ a 1:1 to an address with no registered owner — vanished recipient
    ⚠Routing (mine()) is unchanged — only «whether to warn» changed. Do not fix this by joining
      rooms you are not in: that means receiving others' conversations and breaks this project's rule #1.
    """
    if r.get("room"):
        return r.get("room") in myrooms
    return (r.get("to") or "") not in _registered_ids()


def _flush(reason):
    """Emit the batch at once. **Only here** is the cursor advanced and delivery recorded."""
    global _pending, _hold_since, seen_t, _quiet_held, _last_deliver
    if not _pending:
        return
    batch, _pending = _pending, []
    _hold_since = 0.0
    _last_deliver = time.time()   # ★proof delivery is running — the skip-warning gate reads this
    mark_ack([r.get("id") for r in batch], ME_ID, "delivered")
    # ★★**No ack here** (2026-09-23 — reverts the 2026-09-04 rule «emitting the full text counts as confirmed»).
    #   Printing the full text to `stdout` is **delivery**, not «someone read it». With the session dead and only
    #   the watcher alive, the sender's screen showed "✔ confirmed" though nobody read it — a false report, worse than loss.
    #   Measured 2026-09-23: all 1,485 acks in `acks.jsonl` were automatic records from this spot, so the
    #   «confirmed» signal lost its meaning entirely.
    #   ⚠Nor do we tell sessions to call `mailbox_ack` — on 2026-09-04 that path burned **60M tokens**
    #     (advocate-repo 241 · bot-A 300, all ack-only turns).
    #     Remaining signals: `delivered` above, and the reply itself.
    seen_t = max(seen_t, max(int(r.get("t", 0)) for r in batch))
    save_cursor(seen_t)
    ids = [r.get("id") for r in batch if r.get("id")]
    # ★Give the id — that alone removes any reason to call `mailbox_inbox` again (full body follows below).
    # ★Do not instruct ack (see above). Only delivery is recorded; if a post needs an answer,
    #   reply with `mailbox_say`·`mailbox_send` — that is the real handled signal.
    print(f"★새 글 {len(batch)}건 ({reason}) — 아래 전문 · 전달만 기록됨(확인은 답글로)"
          + (f" · [공유]류 {_quiet_held}건은 알림 생략(inbox 에 있음)" if _quiet_held else ""), flush=True)
    _quiet_held = 0
    for r in batch:
        body = (r.get("body") or "").strip()
        print(f"[메일박스] id={r.get('id')} from={r.get('from')} {where(r)}"
              f" :: {r.get('subject') or body[:60]}", flush=True)
        if body:
            print(body[:BODY_CAP]
                  + (f"\n…(이하 생략 {len(body) - BODY_CAP}자 — 전문은 mailbox_inbox)" if len(body) > BODY_CAP else ""),
                  flush=True)


def save_cursor(t):
    try:
        open(CURSOR, "w", encoding="utf-8").write(str(int(t)))
    except Exception as e:
        print(f"[메일박스] ⚠커서 저장 실패 — 재기동 시 다시 알릴 수 있음: {e}", flush=True)


def unacked():
    """Posts to me with **no delivery record** — oldest first."""
    a = acks()
    rs = rows()
    st = thread_state(rs)          # ★closed threads are not nagged — the peer declared no reply needed
    out = []
    for r in rs:
        if not mine(r) or is_closed(r, st):
            continue
        # ★My own posts are not nagged. mine() includes 'posts in my rooms', so my own posts come in too,
        #   and the server rejects acking your own post (confirm = the recipient saw it), so they never clear.
        #   → an uncleared item nags every 5 min, and that fatigue buries the real unconfirmed ones.
        if r.get("from") == ME_ID:
            continue
        # ★Criterion is «delivered» (2026-09-23) — with auto-ack removed, «no ack» would nag every delivered post. Nag only «delivery failed».
        _e = a.get(r.get("id")) or {}
        if ME_ID in (_e.get("delivered") or []) or any(x.get("who") == ME_ID for x in (_e.get("ack") or [])):
            continue
        age = time.time() - int(r.get("t", 0)) / 1e9
        if NAG_AFTER_S <= age <= NAG_MAX_AGE_S:
            if _nag_count.get(r.get("id"), 0) >= NAG_MAX_TIMES:
                continue
            out.append((age, r))
    out.sort(key=lambda x: -x[0])
    return out
_last_arrival = 0.0
while True:
    time.sleep(POLL_S)
    touch_presence(ME_ID, "watch")      # ★heartbeat — this process dies with the session, so it is a true presence signal
    # ★Alerts carry **the body too** — subject-only alerts allowed "act on the summary", and a warning only in
    #   the body was missed (measured; the user flagged it). The alert itself carries the full text.
    #   ⇒ Token savings never come from **dropping the body**. They come from fewer wakes (batching) and carrying the id (no duplicates).
    fresh = new_for_me(_heard_t)
    if fresh:
        _heard_t = max(_heard_t, max(int(r.get("t", 0)) for r in fresh))
        _added = 0
        for r in fresh:
            # ★Don't alert my own just-written posts (self echo) — the cursor advances with the rest below.
            if r.get("from") == ME_ID:
                continue
            if _quiet(r):                  # share/notice-tag posts don't wake (they stay in inbox)
                _quiet_held += 1
                continue
            _pending.append(r)
            _added += 1
        if _pending and not _hold_since:
            _hold_since = time.time()
        # ★Reset the quiet timer **only when something was actually batched**. Otherwise share-tag posts that never
        #   wake keep pushing the pending batch back (measured 2026-08-19: 4s quiet got pushed to 10s).
        if _added:
            _last_arrival = time.time()
    if _pending:
        # Three flush triggers: ⓐ an urgent post is included ⓑ it went quiet ⓒ the cap was reached
        if any(_urgent(r) for r in _pending):
            _flush("즉시 · 급한 글")
        elif time.time() - _last_arrival >= HOLD_QUIET_S:
            _flush(f"{int(time.time() - _hold_since)}초 묶음")
        elif time.time() - _hold_since >= HOLD_MAX_S:
            _flush(f"{HOLD_MAX_S}초 상한")
    elif not fresh:
        # ★Count posts skipped as "not mine" — the cursor advances **trusting** the routing, so a wrong routing
        #   erases the evidence too (flagged by a peer). If this grows while alerts stay 0, identity is wrong.
        _rs = rows()
        _skip = 0
        # ★One wake = the whole session context re-enters input (measured ≈517k tokens per wake).
        #   So this warning fires **only when it can mean something**: delivery has been 0 for long while skips pile up.
        #   While delivery runs, delivery itself proves identity, so this line carries zero information
        #   (measured 2026-09-04: on a normal-delivery day this line alone woke 5 times, all 5 with zero info).
        #   ⚠The guard is not dead — with a wrong identity delivery is «0 since startup», so it always fires after SKIP_QUIET_S.
        _deliver_quiet = time.time() - _last_deliver
        # ★Count only «once the fire condition already holds» — it used to scan the whole bus every 2s (even when info was 0).
        if _deliver_quiet >= SKIP_QUIET_S and time.time() - _last_skip_log >= 600:
            _myrooms = my_rooms()
            _skip = sum(1 for r in _rs
                        if int(r.get("t", 0)) > seen_t and not mine(r, _myrooms) and _suspect(r, _myrooms))
        if _skip:
            _last_skip_log = time.time()
            print(f"[메일박스·판정] 내 것이 아니라고 건너뜀 {_skip}건 (신원={ME_ID})"
                  f" · 배달 {int(_deliver_quiet)}초째 0 — 신원 설정을 의심할 것", flush=True)
        nt = max(seen_t, latest_t(_rs))
        if nt != seen_t:
            seen_t = nt
            save_cursor(seen_t)
    # Re-alert **undelivered** posts even with no new posts (spaced out — not every poll).
    if time.time() - _last_nag >= NAG_EVERY_S:
        pend = unacked()
        if pend:
            _last_nag = time.time()
            # ★Only «posts with no delivery record» land here — the watcher was down, or only the list was fetched.
            for _a, _r in pend:
                _i = _r.get("id")
                _nag_count[_i] = _nag_count.get(_i, 0) + 1
            # ★Naming this _quiet overwrites the predicate _quiet(r) above with a list, killing the next round (measured 2026-09-07).
            _final_nag = [1 for _a, _r in pend
                          if _nag_count.get(_r.get("id"), 0) >= NAG_MAX_TIMES]
            print(f"[메일박스·미전달] 전달되지 않은 글 {len(pend)}건 — mailbox_inbox(full=true) 로 받을 것"
                  + (f" · 이 중 {len(_final_nag)}건은 이번이 마지막 알림이다(목록에는 남는다)" if _final_nag else ""),
                  flush=True)
            for age, r in pend[:3]:
                print(f"  · {int(age // 60)}분 전 · from={r.get('from')} · {(r.get('subject') or '')[:70]}", flush=True)
