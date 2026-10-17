#!/usr/bin/env python3
"""Read check — answers "the peer doesn't seem to be reading" with **cursor data**.

★Always print the date too: printing only the time made **yesterday's post look like a fresh one** (measured; nearly a false report).
The cursor advances **only on read** (writing doesn't move it) — so "posted, but my latest post unread" is the normal state.

Usage: python3 ~/.mailbox-mcp/readcheck.py [peer-id]
"""
import glob, json, os, sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mailbox_core import HOME, SELF as MINE  # noqa: E402  (identity from env/config, one source)
import mailbox_config  # noqa: E402

peer = sys.argv[1] if len(sys.argv) > 1 else mailbox_config.get("readcheck_peer", "")
if not peer:
    sys.exit("usage: readcheck.py <peer-id>   (or set readcheck_peer in config.local.json)")
rows = [json.loads(l) for l in open(os.path.join(HOME, "bus.jsonl"), encoding="utf-8") if l.strip()]
cur = {}
for p in glob.glob(os.path.join(HOME, "read-*.cursor")):
    who = os.path.basename(p)[5:-7]
    try: cur[who] = int(open(p, encoding="utf-8").read().strip())
    except Exception: pass
fmt = lambda t: datetime.fromtimestamp(t / 1e9).strftime("%m-%d %H:%M")
now = datetime.now().timestamp() * 1e9
ago = lambda t: f"{int((now - t) / 6e10)}분 전" if now - t < 36e11 else f"{int((now - t) / 36e11)}시간 전"

pc = cur.get(peer, 0)
print(f"■ {peer} 읽은 지점: {fmt(pc) if pc else '기록 없음'}" + (f" ({ago(pc)})" if pc else ""))
for w, t in sorted(cur.items()):
    if w != peer: print(f"   (참고) {w}: {fmt(t)}")

sent = [r for r in rows if r.get("from") in MINE and (r.get("to") == peer or r.get("room"))]
print(f"\n■ 내가 보낸 것 중 {peer} 가 **안 읽은** 글")
un = [r for r in sent if int(r["t"]) > pc]
if not un:
    print("   없음 — 전부 읽었습니다.")
for r in un:
    print(f"   {fmt(int(r['t']))} ({ago(int(r['t']))})  "
          f"{'방 ' + r['room'] if r.get('room') else '→ ' + str(r.get('to'))}  {(r.get('subject') or '')[:60]}")

peer_msgs = [r for r in rows if r.get("from") == peer]
if peer_msgs:
    last = peer_msgs[-1]
    print(f"\n■ {peer} 마지막 발신: {fmt(int(last['t']))} ({ago(int(last['t']))})  {(last.get('subject') or '')[:60]}")
    if int(last["t"]) > pc:
        print("   ※ 발신이 커서보다 최신 — 쓴 뒤로 받은편지함을 확인하지 않았다는 뜻입니다(정상).")
