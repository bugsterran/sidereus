#!/usr/bin/env python3
"""**Single source of truth for mailbox read routing.** Watchers, viewer and reports all use it.

Why (2026-08-06): "is this a new post for me" was implemented separately in four places —
    `watch_bus.py` (launchd, always on) · `monitor_stream.py` (session alerts) · `chat_server.py` (viewer) · `readcheck.py`.
    So **a defect fixed in one place stayed in the others**:
      · watch_bus had a "lower the baseline when the bus shrinks" guard; monitor_stream did not
        → deleting 2 test lines shrank the file 228→226 lines, the line-count baseline (228) stayed, and **alerts were dead for 6 min**
          (found only because monitoring went silent).
    ⇒ Routing lives here only, and **`--selftest` below reproduces the real failure modes**.
       One fix fixes all four; the self-test says whether the fix holds.

Core rules (change them only here)
  ① The baseline is **t (time)**. Line counts break under deletion/rotation.
  ② Room posts: rooms I joined + **excluding my own** (otherwise my own post wakes me — a loop).
  ③ Addressed mail: mine if `to` is me. **No from condition** — otherwise mail from a peer who misconfigured
     their name as mine gets filtered too (missed in practice). Loop prevention is only needed in rooms.
  ④ Check all aliases — mail sent to an old address must not be lost.

Usage: from mailbox_core import rows, latest_t, mine, my_rooms, cursors, HOME
       python3 mailbox_core.py --selftest      # failure-mode reproduction check
"""
import glob
import re
import json
import os
import sys
import time

CODE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CODE_DIR)
import mailbox_config  # noqa: E402

HOME = mailbox_config.data_dir()   # data dir ($MAILBOX_DIR); not the code dir
BUS = os.path.join(HOME, "bus.jsonl")
ROOMS = os.path.join(HOME, "rooms.json")

# My name and aliases.
# ★Setting only `MAILBOX_ME` must be enough — ME/SELF defaults used to be **hardcoded to agent-A**, so
#   launching with `MAILBOX_ME=repo-A` filtered **every peer (agent) post as "written by me"** (measured
#   2026-08-07 · caught by a peer). Nasty symptom: process, heartbeat, startup log all fine, **only posts never arrive.**
#   Identity must be **derived from one value**, not set three ways (with three settings you set one and silently go wrong).
# Defaults come from config.local.json (self.ids / self.aliases / alias_strip_prefixes); env wins.
# ⚠ the launchd watch daemon runs without MAILBOX_ME, so the config's self.* IS its identity.

_CFG = mailbox_config.load()
_ME1 = (os.environ.get("MAILBOX_ME") or "").strip()
if _ME1:
    _DEF_ALIASES = [_ME1] + [_ME1[len(p):] for p in _CFG["alias_strip_prefixes"] if p and _ME1.startswith(p)]
    _DEF_SELF = [_ME1]
else:
    _DEF_ALIASES = _CFG["self"]["aliases"] or _CFG["self"]["ids"]
    _DEF_SELF = _CFG["self"]["ids"]
ME = {x for x in mailbox_config.env_list("MAILBOX_ALIASES", _DEF_ALIASES) if x}
SELF = {x for x in mailbox_config.env_list("MAILBOX_SELF", _DEF_SELF) if x}


# ── Log silent failures (once) ──────────────────────────────────────────
#   Routing is concentrated in this file, so swallowing errors here blinds watcher, MCP and viewer **at once**.
#   Measured 2026-08-13: the same shape (`except: return {}`) in the viewer blanked the presence log.
_warned = set()


def _warn_once(key, msg):
    if key in _warned:
        return
    _warned.add(key)
    print(f"⚠ mailbox: {msg}", file=sys.stderr, flush=True)


if not SELF and mailbox_config.FILE_OK:
    # No identity: nothing is filtered as "mine", nothing addressed arrives. Say so once.
    _warn_once("noself", "no identity — set MAILBOX_ME or self.ids in config.local.json")


def rows(path=None):
    try:
        with open(path or BUS, encoding="utf-8") as f:
            out = []
            bad = 0
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except Exception:
                        bad += 1        # ★a broken line = conversation that goes unseen. Count and report once
            if bad:
                _warn_once(f"badlines:{bad}", f"bus 에 읽지 못한 줄 {bad}개 — 그만큼 판정에서 빠집니다")
            return out
    except Exception as e:
        _warn_once("rows", f"bus 를 읽지 못했습니다({type(e).__name__}: {e}) — 새 글이 없다고 잘못 판정할 수 있습니다")
        return []


def latest_t(rs):
    """Latest t — the baseline (watermark). Unaffected by deletion/rotation."""
    return max((int(r.get("t", 0)) for r in rs), default=0)


def my_rooms(path=None):
    """Rooms I joined — **re-reads the file every call** (hardcoding repeats the same incident in a new room)."""
    try:
        with open(path or ROOMS, encoding="utf-8") as f:
            return {n for n, r in json.load(f).items() if ME & set(r.get("members") or [])}
    except Exception:
        return set()


def mine(r, rooms=None):
    """Is this a post I need to know about — rules ②③④. This is the only routing decision."""
    room = r.get("room")
    if room:
        return room in (rooms if rooms is not None else my_rooms()) and r.get("from") not in SELF
    return r.get("to") in ME


def new_for_me(since_t, rs=None, rooms=None):
    """Only posts **for me** after since_t. Shared entry point for watchers and viewer."""
    rs = rs if rs is not None else rows()
    rooms = rooms if rooms is not None else my_rooms()
    out = [r for r in rs if int(r.get("t", 0)) > since_t and mine(r, rooms)]
    out.sort(key=lambda r: int(r.get("t", 0)))
    return out


# ── Presence ────────────────────────────────────────────────────
# Why: cursors and send times are **last activity**, not "attached right now". When a peer was quiet we
#   couldn't tell "thinking" from "session dead" (measured: both sides waited until a person stepped in).
# Two signals — strongest first:
#   ① watch  = watcher process heartbeat. **Dies with the session** → alive means truly attached.
#   ② mcp    = MCP tool call time. Covers sessions without a watcher, but "last call" is a weak signal.
FRESH_S = 30          # updated within this = online (generous vs the 2–3s watcher poll)
STALE_S = 3600        # 1h without response → **removed from the list** — keeping it makes the presence display lie
                      #   (decided 2026-08-07: not attached → offline; no response for over 1h → remove)
ACT_STALE_S = 3600    # ★even with a live heartbeat, no **real activity** (MCP call) for this long → not counted online
                      #   (measured 2026-09-23: repo-A heartbeat still updating for 11d 22h · no MCP call for 21h)
                      #   ⚠Same value as STALE_S — this applies the existing "1h without response" rule, previously on
                      #     one signal only, to both signals, so it is not set separately.


def touch_presence(who, source="mcp"):
    try:
        with open(os.path.join(HOME, f"presence-{who}.{source}"), "w", encoding="utf-8") as f:
            f.write(str(int(time.time())))
    except Exception as e:
        # a failed heartbeat makes me **look absent** on others' screens — swallowing it hides the cause
        _warn_once("beat", f"하트비트를 쓰지 못했습니다({type(e).__name__}: {e}) — 상대 화면에 접속 표시가 안 뜹니다")


def presence():
    """id → {"at", "source": watch|mcp, "online", "state": online|offline|unknown}.

    ★Keep the two signals apart — mixing them makes the screen lie (measured 2026-08-07: a peer without a watcher
      showed "active 13 min ago", which the user read as "not reading". The truth was **unknown**).
        · watch = heartbeat process → if it stops, truly offline
        · mcp   = stamped only at tool calls → ages even while idle. With only this, undecidable = unknown
    """
    out = {}
    has_watch = set()
    mcp_at = {}          # keep **last MCP call** time separately from the heartbeat (for the active check below)
    for p in glob.glob(os.path.join(HOME, "presence-*")):
        base = os.path.basename(p)[len("presence-"):]
        who, _, source = base.rpartition(".")
        if not who:
            continue
        try:
            at = int(open(p, encoding="utf-8", errors="replace").read().strip())
        except Exception:
            try:
                at = int(os.path.getmtime(p))
            except OSError:
                continue
        if source == "watch":
            has_watch.add(who)
        elif source == "mcp":
            mcp_at[who] = max(mcp_at.get(who, 0), at)   # kept even when the heartbeat wins
        cur = out.get(who)
        rank = {"watch": 2, "mcp": 1}
        # Stronger signal first; same rank → newest. (Previously `or at > cur["at"]` let **a weak signal overwrite a strong one**,
        #  so the source flipped to mcp while the heartbeat was alive.)
        if not cur or rank.get(source, 0) > rank.get(cur["source"], 0) \
                or (rank.get(source, 0) == rank.get(cur["source"], 0) and at > cur["at"]):
            out[who] = {"at": at, "source": source}
    now = int(time.time())
    stale = [w for w, v in out.items() if (now - v["at"]) > STALE_S]
    for w in stale:
        # Delete the file too — a leftover state file shows up again as a "stale presence" next time.
        out.pop(w, None)
        for f in glob.glob(os.path.join(HOME, f"presence-{w}.*")):
            try:
                os.remove(f)
            except OSError:
                pass
    for w, v in out.items():
        fresh = (now - v["at"]) <= FRESH_S
        v["online"] = fresh
        # ★A heartbeat means **the watcher process is alive**, not that the id did anything.
        #   Do not merge the two into one value — merging makes the screen falsely say "alive" (same reason as FRESH_S).
        act = mcp_at.get(w)
        v["act"] = act                                  # last real activity (s) · None = unknown
        v["active"] = bool(act and (now - act) <= ACT_STALE_S)
        # A peer whose heartbeat was never seen is not declared offline — that is something we don't know.
        v["state"] = "online" if fresh else ("offline" if w in has_watch else "unknown")
    return out


# ── Delivery · confirmation (ack) ─────────────────────────────────────────────────────────
# Why: a cursor means **"fetched"**, not "seen". A peer can fetch while its watcher is dead and never see it
#   (measured), so the user stopped trusting that sent mail was read. Split into two stages:
#     delivered — **that message id was actually included** in an inbox response (server records it). More precise than the cursor.
#     ack       — confirmation the recipient left **explicitly** via `mailbox_ack`. The only evidence of "seen".
#   Records are appended to a separate file so the bus stays clean (don't mix conversation and metadata).
ACKS = os.path.join(HOME, "acks.jsonl")


def mark_ack(msg_ids, who, kind="ack", note=None):
    """Record delivery/confirmation for msg_ids. Failure never blocks the conversation.

    ⚠`kind="ack"` is **only an explicit confirmation by the recipient**. No process may stamp it on their behalf —
      on 2026-09-23 the watcher's automatic stamping was removed (all 1,485 of those records looked like «someone saw it»)."""
    ids = [i for i in (msg_ids if isinstance(msg_ids, (list, tuple, set)) else [msg_ids]) if i]
    if not ids:
        return 0
    try:
        with open(ACKS, "a", encoding="utf-8") as f:
            for i in ids:
                f.write(json.dumps({"id": i, "who": who, "kind": kind,
                                    "t": time.time_ns(), "note": note}, ensure_ascii=False) + "\n")
        return len(ids)
    except Exception:
        return 0


def acks():
    """message id → {"delivered": [who…], "ack": [{who, at, note}…], "t": last record (ns)}"""
    out = {}
    try:
        with open(ACKS, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                e = out.setdefault(r.get("id"), {"delivered": [], "ack": [], "t": 0})
                # ★**last record time** for the id — the viewer uses it to keep only recent ones (delivered has no time)
                e["t"] = max(e.get("t") or 0, int(r.get("t") or 0))
                if r.get("kind") == "ack":
                    e["ack"].append({"who": r.get("who"), "at": r.get("t"), "note": r.get("note")})
                else:
                    if r.get("who") not in e["delivered"]:
                        e["delivered"].append(r.get("who"))
                    # Stop-hook receipt kept apart too: «delivered» also covers a watcher that only notified
                    if r.get("kind") == "hooked" and r.get("who") not in e.setdefault("hooked", []):
                        e["hooked"].append(r.get("who"))
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return out


def cursors():
    """id → last read t. Basis of the read marker (read-<id>.cursor)."""
    out = {}
    for p in glob.glob(os.path.join(HOME, "read-*.cursor")):
        who = os.path.basename(p)[len("read-"):-len(".cursor")]
        try:
            out[who] = int(open(p, encoding="utf-8", errors="replace").read().strip())
        except Exception:
            pass
    return out


# ★Thread closure — derived from the subject tag (no separate file: with bus.jsonl as the source there is nothing to drift).
#   Decided 2026-08-07: finished items need no reply, so a close tag is allowed; if more checking is needed,
#   a new request reopens it. → Judged by **the nature of the last post, not a close command**.
#   So a new post in a closed thread **reopens it automatically** (no separate reopen needed).
CLOSE_TAGS = {"마침", "종결", "완료", "DONE", "CLOSED"}
_TAG_RE = re.compile(r"^\s*\[([^\]]{1,20})\]")


def subject_tag(subject):
    m = _TAG_RE.match(str(subject or ""))
    return m.group(1).strip() if m else None


def thread_key(r):
    t = (r.get("thread") or "").strip()
    return (r.get("room") or f"dm:{r.get('to')}", t) if t else None


def thread_state(rs=None):
    """(room, thread) → {"closed", "by", "at", "tag"}. Closed if **the last post** has a close tag."""
    rs = rs if rs is not None else rows()
    last = {}
    for r in rs:
        k = thread_key(r)
        if not k:
            continue
        if k not in last or int(r.get("t", 0)) >= int(last[k].get("t", 0)):
            last[k] = r
    out = {}
    for k, r in last.items():
        tag = subject_tag(r.get("subject"))
        closed = bool(tag and tag.upper() in {x.upper() for x in CLOSE_TAGS})
        out[k] = {"closed": closed, "by": r.get("from"), "at": int(r.get("t", 0)), "tag": tag}
    return out


def is_closed(r, st=None):
    k = thread_key(r)
    if not k:
        return False
    st = st if st is not None else thread_state()
    return bool(st.get(k, {}).get("closed"))


def advance_cursor(who, t):
    """**Only advance** the read cursor to t (never move it back).

    ★Why: since alerts carry the body, peers read without opening `inbox` — but the cursor only moved
      in `inbox`. So **even after reading and replying it stayed "unread"** (measured 2026-08-07:
      a peer replied to 1d5dd704 while its cursor was stuck at 11:23). A reply/confirmation is evidence of reading.
    """
    t = int(t or 0)
    if not who or t <= 0:
        return 0
    f = os.path.join(HOME, f"read-{who}.cursor")
    try:
        cur = int(open(f, encoding="utf-8", errors="replace").read().strip())
    except Exception:
        cur = 0
    if t <= cur:
        return cur
    try:
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(str(t))
    except Exception:
        return cur
    return t


def read_upto(msg):
    """Advance **the author's** read cursor based on the post just written (`msg`).

    ★`mine()` decides "is this for me (SELF)", so it can't be used from someone else's view — here we look directly
      at where msg sits (same room / DM to the author). Conservatively counts **only posts earlier than the author's own**.
    """
    who, t = msg.get("from"), int(msg.get("t") or 0)
    room = msg.get("room")
    vis = []
    for r in rows():
        rt = int(r.get("t", 0))
        if rt >= t or r.get("from") == who:
            continue
        if room:
            if r.get("room") == room:
                vis.append(rt)
        elif r.get("to") == who:
            vis.append(rt)
    return advance_cursor(who, max(vis)) if vis else cursors().get(who, 0)


def where(r):
    return f"방 {r['room']}" if r.get("room") else f"to={r.get('to')}"


# ───────────────────────── Self-test ─────────────────────────
def _selftest():
    import tempfile
    d = tempfile.mkdtemp()
    # ★Redirect ACKS too — it was missed once and **the self-test wrote to the real acks.jsonl** (m1010·m1020 leaked).
    #   Same family as the earlier fake lines injected into the bus: a test touching real data pollutes observation.
    global HOME, BUS, ROOMS, ACKS, ME, SELF
    HOME, BUS, ROOMS = d, os.path.join(d, "bus.jsonl"), os.path.join(d, "rooms.json")
    ACKS = os.path.join(d, "acks.jsonl")
    ME, SELF = {"agent-a", "a"}, {"agent-a"}   # fixed test identity, independent of config
    json.dump({"room-a": {"owner": "agent-a", "members": ["agent-a", "agent-b"]},
               "other": {"owner": "x", "members": ["x"]}},
              open(ROOMS, "w", encoding="utf-8"))
    t = [1000]

    def put(**kw):
        t[0] += 10
        m = {"id": f"m{t[0]}", "t": t[0], "from": kw.get("frm"), "to": kw.get("to"),
             "room": kw.get("room"), "subject": kw.get("s", "")}
        open(BUS, "a", encoding="utf-8").write(json.dumps(m, ensure_ascii=False) + "\n")
        return m

    fails = []
    ran = []          # ★count checks that actually ran — it used to be hardcoded `total = 10 + 7`, so after adding 4 checks
                      #   it still claimed "17/17" (while 20 checks printed). A number must be counted to be a number.

    def ck(name, cond):
        ran.append(name)
        print(("  ✅ " if cond else "  ❌ ") + name)
        if not cond:
            fails.append(name)

    print("메일박스 판정 셀프테스트 — 실제로 났던 실패 모드를 재현한다\n")

    m1 = put(frm="agent-b", room="room-a", s="상대의 방 글")
    ck("내가 들어간 방의 상대 글은 알린다", mine(m1))
    m2 = put(frm="agent-a", room="room-a", s="내 방 글")
    ck("내가 쓴 방 글로는 깨어나지 않는다(루프 방지)", not mine(m2))
    m3 = put(frm="x", room="other", s="남의 방")
    ck("들어가지 않은 방은 무시한다", not mine(m3))
    m4 = put(frm="agent-b", to="agent-a", s="주소 메일")
    ck("내 주소로 온 메일은 알린다", mine(m4))
    m5 = put(frm="agent-a", to="agent-a", s="상대 오설정(from==to)")
    ck("★from 이 내 이름이어도 to 가 나면 알린다(오설정 메일 유실 방지)", mine(m5))
    m6 = put(frm="agent-b", to="a", s="옛 별칭")
    ck("별칭(a)으로 온 것도 알린다", mine(m6))
    m7 = put(frm="agent-a", to="agent-b", s="내가 보낸 메일")
    ck("내가 보낸 주소 메일은 내 것이 아니다", not mine(m7))

    # ★Core regression — don't miss new posts after the file shrinks (the line-count baseline incident)
    all_rows = rows()
    base = latest_t(all_rows)
    keep = [json.dumps(r, ensure_ascii=False) for r in all_rows[:-3]]      # delete 3 lines (cleanup scenario)
    open(BUS, "w", encoding="utf-8").write("\n".join(keep) + "\n")
    fresh = put(frm="agent-b", room="room-a", s="삭제 후 도착한 글")
    got = new_for_me(base)
    ck("★파일이 줄어든 뒤 도착한 글을 잡는다(줄 수 기준선이면 놓친다)",
       any(r["id"] == fresh["id"] for r in got))
    ck("이미 본 글은 다시 알리지 않는다", not any(int(r["t"]) <= base for r in got))

    # ── Presence ──
    touch_presence("agent-a", "watch")
    p = presence()
    ck("하트비트를 남기면 접속 중으로 잡힌다", p.get("agent-a", {}).get("online") is True)
    ck("강한 신호(watch)를 출처로 밝힌다", p.get("agent-a", {}).get("source") == "watch")
    old = os.path.join(HOME, "presence-ghost.mcp")
    open(old, "w", encoding="utf-8").write(str(int(time.time()) - STALE_S - 60))
    p2 = presence()
    ck("★1시간 넘게 반응 없으면 목록에서 지운다", "ghost" not in p2)
    ck("지운 상태 파일은 남기지 않는다(다음 조회에 또 보이지 않게)", not os.path.exists(old))

    # ── Delivery · confirmation ──
    mark_ack(["m1010", "m1020"], "agent-b", "delivered")
    mark_ack("m1010", "agent-b", "ack", note="반영했습니다")
    a = acks()
    ck("전달됨을 기록한다", "agent-b" in a.get("m1020", {}).get("delivered", []))
    ck("★확인(ack)은 전달과 구분된다", bool(a.get("m1010", {}).get("ack")) and not a.get("m1020", {}).get("ack"))
    # Thread closure — the last post's tag is authoritative; a new post reopens automatically
    tr = [{"t": 10, "room": "r", "thread": "th", "from": "a", "subject": "[요청] 봐 주세요"},
          {"t": 20, "room": "r", "thread": "th", "from": "b", "subject": "[마침] 처리했습니다"}]
    ck("마지막 글이 마침이면 닫힌다", thread_state(tr)[("r", "th")]["closed"] is True)
    tr2 = tr + [{"t": 30, "room": "r", "thread": "th", "from": "a", "subject": "[요청] 하나 더"}]
    ck("닫힌 뒤 새 글이 오면 다시 열린다", thread_state(tr2)[("r", "th")]["closed"] is False)
    ck("스레드 없는 글은 종결 대상이 아니다", is_closed({"room": "r", "from": "a"}, thread_state(tr)) is False)
    ck("태그가 없으면 열린 것", thread_state([{"t": 1, "room": "r", "thread": "x", "from": "a",
                                              "subject": "제목만"}])[("r", "x")]["closed"] is False)
    ck("확인에 붙인 한 줄을 보존한다", a["m1010"]["ack"][0]["note"] == "반영했습니다")

    total = len(ran)
    print(f"\n결과: {total - len(fails)}/{total} 통과" + (f" · 실패: {', '.join(fails)}" if fails else ""))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(_selftest() if "--selftest" in sys.argv else print(__doc__) or 0)
