"""POST route handlers (split out of chat_server.py 2026-09-24) — a mixin `chat_server.Handler` inherits.
Methods use `self._send`/`self._raw_json`/`self._body_json` from Handler."""
import json
import os
import time
import uuid

from sidereus.config import BUS_PATH, ROOM_DEFAULT, VIEWER_ME, _lock
from sidereus import config as _cfg
from sidereus.warn import WARN_MUTE_S, _SOFT, _WARN_LOG, _warn_lock, _warned, _wmute, warn_once
from sidereus.bus import _bus_append, _load, _open_append, dm_send, dm_target_error, thread_close
from sidereus.live import _parse_cache, _parse_lock
from sidereus.cards import mark_cards_read, set_cards_read
from sidereus.otel import _otel_ingest, _otel_lock, _otel_stat
from sidereus.bgtasks import bg_dismiss
from sidereus.ext import _ext_lock, _ext_stat, ext_dismiss, ext_ingest
from sidereus.sessions import sessions_rows
from sidereus.saver import saver_set
from sidereus.state import state_cache_clear
from sidereus.structure import struct_mark_act
from sidereus.review import RV_BODY_MAX, review_mark
from sidereus.work import _SID_SAFE
from sidereus.term import term_focus, term_set
from sidereus.prefs import PREFS_BODY_MAX
from sidereus import ui_prefs
from sidereus.pipeline import SAVE_BODY_MAX as PIPE_BODY_MAX, save as pipeline_save
from sidereus.pipeline_new import create as pipeline_create
from sidereus.pipeline_del import delete as pipeline_delete
from sidereus.pipeline_projects import add_project as pipeline_add, apply_set as pipeline_apply, pick_folder, remove_project as pipeline_remove
from sidereus.cc_settings import prefs_set_all
from sidereus.hook_connect import connect as hook_connect
from sidereus.hook_remove import remove as hook_remove
from sidereus.room_tags import BODY_MAX as TAGS_BODY_MAX, set_tags as room_tags_set
from sidereus import bus as _busmod
from sidereus import room_admin
from sidereus import pl_reqs

# (created, any already-present) -> fixed i18n key for the invite note; each needs an I18N.ko entry
INVITE_MSGS = {(True, False): "Created '{room}' and invited {n}", (False, False): "Invited {n} to '{room}'",
               (True, True): "Created '{room}' and invited {n} · {m} already there",
               (False, True): "Invited {n} to '{room}' · {m} already there"}


def invite_text(room, topic, members):
    """(subject, body) of an invite DM — one builder for the confirm preview (dry) and the sent post."""
    # ⚠The leading tag is the mailbox wire tag for invites (kept as is); the rest is read by the invited session's model.
    return (f"[초대] room '{room}'",
            f"The user invited you to room **'{room}'** from the screen (Sidereus)."
            + (f"\nTopic: {topic}" if topic else "")
            + f"\nMembers: {', '.join(members) or 'none yet'}"
            + f"\n\nTo join: mailbox_room {{ action: \"join\", room: \"{room}\" }}")


class _PostRoutes:
    # ★The user **writes directly.** Before it was read-only: humans only watched and had to go through an agent to speak
    #   — so it became a report, not a conversation.
    #   The format follows MCP `_post` as the source of truth (id·t·from·idSrc·to·room·subject·thread·body).
    #   Only `replyTo` is new — whose post is being answered must be **structure** so replies can be short.
    def _viewer_me(self):
        # Page UI language lives in the browser only (05-i18n.js LANG); postJSON sends it so a default id follows it.
        return _cfg.viewer_me_for(VIEWER_ME, (self.headers.get("X-Sidereus-Lang") or "").strip())

    def _room_invite(self, req):
        """**Invite** the sessions picked on screen to a room (does not make them join).

        ★Why not write members directly: the roster is that room's record, and who joined when is
          evidence for verdicts (reviews judge by the traces left, not by either side's word).
          Silently changing the roster from the screen contaminates that evidence. Invites are discovery, so safe.
        ★Weak identities (folder-name fallback etc.) are rejected — measured incident (2026-08-12): an identity
          derived from a folder name left posts under someone else's name. Invites also require a confirmed id.
        ★Does the same as MCP `_invite`: adds to invited in rooms.json and leaves an invite post in the
          peer's inbox (1:1). That way it reaches even sessions without the room feature."""
        if not isinstance(req, dict) or not isinstance(req.get("room") or "", str) \
           or not isinstance(req.get("topic") or "", str) or not isinstance(req.get("ids") or [], list):
            return {"ok": False, "msg": "Bad request."}   # ⚠a string `ids` used to iterate per character
        room = (req.get("room") or "").strip()
        ids = [str(x).strip() for x in (req.get("ids") or []) if str(x).strip()]
        topic = (req.get("topic") or "").strip()
        if not room or not ids:
            return {"ok": False, "msg": "A room name and a target are required."}
        room, err = room_admin.check_name(room)   # same name rules as create: no 'dm', control chars or overlong names
        if err:
            return {"ok": False, "msg": err}

        # Check the targets are sessions on screen now with confirmed identity — never invite by a guessed id
        known = {}
        ident = _load("identity.json", {})
        for r in sessions_rows(max_age=10):   # ⚠request path: short wait for a just-started session, never cold
            # A Codex launcher id counts only under the DM rule (bus.codex_env_ok: published by the poll, fails closed)
            if r.get("mbox") and (r.get("mboxSrc") == "identity"
                                  or (r.get("mboxSrc") == "env" and _busmod.codex_env_ok(r["mbox"], ident))):
                known[r["mbox"]] = r.get("project") or r.get("cwd") or ""
        bad = [i for i in ids if i not in known]
        if bad:
            return {"ok": False, "msg": "Unconfirmed identity: {ids} — run `/room as <id>` in that session to register"
                    " before inviting.", "vars": {"ids": ", ".join(bad)}}

        dry = req.get("dry") is True
        expect = req.get("expect")
        if expect is not None and not isinstance(expect, str):
            return {"ok": False, "msg": "Bad request."}
        with _lock:
            rooms = _load("rooms.json", {})
            if not isinstance(rooms, dict):
                rooms = {}
            created = room not in rooms
            # dry works on a copy so the preview runs the exact code path that builds the sent body
            cur = rooms.get(room)
            r = dict(cur) if isinstance(cur, dict) else {"created": time.time_ns(), "owner": "", "members": [],
                                                          "topic": topic, "invited": []}
            if topic and not r.get("topic"):
                r["topic"] = topic
            inv = list(r.get("invited") or [])
            mem = list(r.get("members") or [])
            added, already = [], []
            for i in ids:
                if i in mem or i in inv:
                    already.append(i)
                else:
                    inv.append(i)
                    added.append(i)
            subject, body = invite_text(room, r.get("topic"), mem)
            if dry:
                return {"ok": True, "dry": True, "subject": subject, "body": body, "added": added, "already": already}
            # ⚠The confirm showed `expect`; if rooms.json changed since (topic, members), the bytes would differ — ask again
            if expect is not None and expect != body:
                return {"ok": False, "stale": True, "msg": "The room changed since the preview — check again."}
            r["invited"], r["members"] = inv, mem
            rooms[room] = r
            # ⚠the MCP owns rooms.json — keep a one-step undo before writing it
            _busmod._save_json_bak(os.path.join(_busmod.DATA_DIR, "rooms.json"), rooms)

            # Also leave it in the inbox — this is the path by which the invite actually arrives
            me = self._viewer_me()
            for i in added:
                _bus_append({
                    "id": uuid.uuid4().hex[:8],
                    "t": time.time_ns(),
                    "from": me,         # same author id as /api/say and /api/dm, so the page counts it as mine
                    "idSrc": "viewer",
                    "to": i,
                    "room": None,
                    "subject": subject,
                    "thread": f"invite:{room}",
                    "body": body,
                })
        # msg = one of INVITE_MSGS (fixed i18n keys); values go in `vars` (TV in 05-i18n.js)
        return {"ok": True, "created": created, "added": added, "already": already,
                "msg": INVITE_MSGS[(bool(created), bool(already))],
                "vars": {"room": room, "n": len(added), "m": len(already)}}

    def _p_otel(self, u):
        # ★Claude Code sends telemetry here (settings.json env). Return 200 quickly —
        #   if slow, that session's export queue piles up.
        try:
            n = int(self.headers.get("Content-Length") or 0)
            # ★Count the POST itself — the first fork separating «never arrives» from «arrives and is dropped».
            with _otel_lock:
                _otel_stat["posts"] += 1
                _otel_stat["lastPost"] = time.time()
            if n > 8_000_000 or n < 0:
                self._body_unread()
            raw = self.rfile.read(n) if 0 < n <= 8_000_000 else b"{}"
            got = _otel_ingest(json.loads(raw.decode("utf-8"))) if u.path == "/v1/logs" else 0
        except Exception as e:
            self._body_unread()          # e.g. a non-numeric Content-Length left the body unread
            warn_once("otel", "Could not read telemetry ({err})", vars={"err": f"{type(e).__name__}: {e}"})
            got = 0
        return self._send(200, "{}", "application/json")

    def _p_hook(self, u):
        # ★External CLI agents' hooks (Gemini, Codex) push events here. The server survives exceptions.
        code, body = 200, {"ok": 1}
        try:
            n = int(self.headers.get("Content-Length") or 0)
            with _ext_lock:                    # Diagnostic — separates «never arrives» from «arrives and is dropped»
                _ext_stat["posts"] += 1
                _ext_stat["lastPost"] = time.time()
            if n > 1_000_000 or n < 0:
                self._body_unread()
            raw = self.rfile.read(n) if 0 < n <= 1_000_000 else b"{}"   # Body cap 1MB
            req = json.loads(raw.decode("utf-8"))
            ok, why = ext_ingest(req if isinstance(req, dict) else {})
            with _ext_lock:
                _ext_stat["kept" if ok else "drop"] += 1
                if ok:
                    _ext_stat["lastKept"] = time.time()
            if not ok:
                code, body = 400, {"ok": 0, "err": why}
        except Exception as e:
            self._body_unread()          # e.g. a non-numeric Content-Length left the body unread
            warn_once("ext-hook", "Could not read external hooks ({err})", vars={"err": f"{type(e).__name__}: {e}"})
            with _ext_lock:
                _ext_stat["drop"] += 1
            code, body = 400, {"ok": 0, "err": "bad request"}
        return self._send(code, json.dumps(body), "application/json; charset=utf-8")

    def _p_bg_dismiss(self, u):
        # ★A human clears it — if the completion notice is lost we **cannot know** whether that agent is running or dead
        #   (subagent conversations are not in the transcript, and they are not OS processes).
        #   Instead of deleting by guess or holding it for 2 hours, the judgment is handed to the human.
        # ⚠A broken/oversize body used to read as {} = «no cwd, no tid» = clear every cwd's entries.
        #   The UI always sends {cwd} or {tid} (web/js/40b-sessions-list.js), so anything else is refused.
        req = self._body_json(4096, None)
        if not isinstance(req, dict) or not ("cwd" in req or "tid" in req) \
           or not all(isinstance(req.get(k, ""), str) for k in ("cwd", "tid")) \
           or not (req.get("cwd", "").strip() or req.get("tid", "").strip()):   # blank both = clear-all too
            return self._send(400, json.dumps({"ok": False, "error": "cwd or tid required"}),
                              "application/json; charset=utf-8")
        cwd = req.get("cwd", "").strip()
        tid = req.get("tid", "").strip()      # ★Clear only one item (2026-08-28)
        gone = bg_dismiss(cwd, tid, lambda fp: _parse_cache.get(fp, (0, {}))[1].get("cwd"))
        with _parse_lock:
            _parse_cache.clear()      # Make the next poll rebuild rows (the cache holds the old list)
        return self._send(200, json.dumps({"ok": True, "removed": gone}),
                          "application/json; charset=utf-8")

    def _p_ext_dismiss(self, u):
        # Attention dismiss of an external row: only a pid-less pending row is dropped (it is never pruned by age).
        if self._refuse_origin():
            return
        req = self._body_json(4096, None)
        sid = req.get("sid") if isinstance(req, dict) else None
        if not isinstance(sid, str) or not sid.strip():
            return self._send(400, json.dumps({"ok": False, "error": "sid required"}), "application/json; charset=utf-8")
        return self._send(200, json.dumps({"ok": True, "removed": ext_dismiss(sid.strip())}),
                          "application/json; charset=utf-8")

    def _p_health_dismiss(self, u):
        # ★The user clears one warning. It is also removed from `_warned`, so **the same cause alerts again if it recurs**
        #   (incl. stderr) — not permanent silence. Stopped threads (dead) cannot be cleared.
        req = self._body_json(4096, {})
        # ⚠_body_json returns any JSON value: a list or a numeric key used to raise out of do_POST with no response.
        if not isinstance(req, dict) or not isinstance(req.get("key") or "", str):
            return self._send(400, json.dumps({"ok": False, "n": 0, "error": "key must be a string"}),
                              "application/json; charset=utf-8")
        _k = (req.get("key") or "").strip()
        gone = 0
        if _k:
            with _warn_lock:
                _b4 = len(_WARN_LOG)
                _WARN_LOG[:] = [w for w in _WARN_LOG if w.get("key") != _k]
                gone = _b4 - len(_WARN_LOG)
                # ★Also reset the tier-1 counts (2026-09-07). Otherwise a promoted soft key's `n` already
                #   exceeds `SOFT_PROMOTE_N`, so **it reappears on the very next occurrence** — clearing becomes
                #   pointless. Restart the counting window so it reappears only «after N more repeats».
                _SOFT.pop(_k, None)
                # ★Give **a quiet period** after clearing (WARN_MUTE_S above). Expired entries are cleared here
                #   — the keys are only a few hard-coded ones, so this suffices (no list without expiry).
                _now2 = time.time()
                for _mk in [k2 for k2, t2 in _wmute.items() if t2 <= _now2]:
                    _wmute.pop(_mk, None)
                _wmute[_k] = _now2 + WARN_MUTE_S
            _warned.discard(_k)
        return self._send(200, json.dumps({"ok": bool(gone), "n": gone}),
                          "application/json; charset=utf-8")

    def _refuse_origin(self):
        # ⚠viewer Origin required (no Origin = 403): these routes write rooms.json / bus.jsonl / room-admin.json
        if _cfg.viewer_origin(self.headers.get("Origin")):
            return False
        self._body_unread()
        self._send(403, json.dumps({"ok": False, "error": "viewer origin required"}), "application/json; charset=utf-8")
        return True

    def _p_act(self, u):
        # Page input heartbeat (web/js/08-ui-kit.js); ⚠viewer Origin required so curl/MCP/hooks cannot hold the warm-up off
        if self._refuse_origin():
            return
        self._body_json(256, None)    # drain the body off the keep-alive socket
        struct_mark_act()
        return self._send(200, json.dumps({"ok": True}), "application/json; charset=utf-8")

    def _p_room_invite(self, u):
        if self._refuse_origin():
            return
        req = self._body_json(65536, {})
        try:
            out = self._room_invite(req)
        except Exception as e:
            out = {"ok": False, "msg": "Invite failed ({err})", "vars": {"err": f"{type(e).__name__}: {e}"}}
        self._raw_json(200, out, cache=False)

    def _p_saver_set(self, u):
        # Same switch files as `/saver`; affects every CLI session from its next prompt.
        req = self._body_json(4096, None)
        # ⚠`limit` (block/warn) can stop every CLI session: viewer Origin required (no Origin = 403), like /api/prefs/set.
        if isinstance(req, dict) and "limit" in req and not _cfg.viewer_origin(self.headers.get("Origin")):
            return self._send(403, json.dumps({"ok": False, "err": "viewer origin required"}),
                              "application/json; charset=utf-8")
        try:
            out = saver_set(req)
            if out.get("ok"):
                state_cache_clear()   # next /api/state poll must carry the new switch
        except Exception as e:
            out = {"ok": False, "err": f"{type(e).__name__}: {e}"[:200]}
        return self._send(200 if out.get("ok") else 400, json.dumps(out, ensure_ascii=False),
                          "application/json; charset=utf-8")

    def _p_cards_read(self, u):
        # Alarm read — clears only the badge. **Cards themselves are not deleted** (history is the purpose).
        #   With `{"key": "<at|kind|project>"}` **only that one card**; an empty body means all (watermark).
        #   `{"keys": [...]}` marks many in one lock + one write (bulk read was N POSTs + N rewrites).
        key, keys = "", []
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 65536 or n < 0:
                self._body_unread()
            if 0 < n <= 65536:
                body = json.loads(self.rfile.read(n) or b"{}") or {}
                key = body.get("key") or ""
                key = key if isinstance(key, str) else ""     # ⚠non-string ids would be stored as card keys
                keys = body.get("keys") if isinstance(body.get("keys"), list) else []
                keys = [k for k in keys if isinstance(k, str) and k]
        except Exception:
            self._body_unread()
            key, keys = "", []           # Broken body falls back to mark-all-read (old behavior)
        if key or keys:
            return self._send(200, json.dumps({"ok": True, "ids": mark_cards_read(([key] if key else []) + keys)}),
                              "application/json; charset=utf-8")
        return self._send(200, json.dumps({"ok": True, "at": set_cards_read()}), "application/json; charset=utf-8")

    def _p_say(self, u):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            # ⚠A negative length passed the cap check and rfile.read(-1) read to EOF with no memory limit.
            if n < 0:
                raise ValueError("negative Content-Length")
            if n > 200_000:
                raise ValueError("body too long")
            req = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(req, dict):
                raise ValueError("not a JSON object")
        except Exception as e:
            self.close_connection = True    # body may be unread (see _refuse)
            return self._send(400, json.dumps({"error": f"Could not read the body: {e}"}), "application/json; charset=utf-8")
        # ⚠A non-string field (e.g. {"body": 5}) raised in .strip() and escaped do_POST with no response.
        bad = [k for k in ("body", "room", "to", "subject", "thread", "replyTo") if not isinstance(req.get(k) or "", str)]
        if bad:
            return self._send(400, json.dumps({"error": f"Fields that are not strings: {', '.join(bad)}"}),
                              "application/json; charset=utf-8")
        body = (req.get("body") or "").strip()
        if not body:
            return self._send(400, json.dumps({"error": "Empty posts are not sent"}), "application/json; charset=utf-8")
        # ⚠Exactly one target: a room, or a DM recipient. A missing target used to fall back to ROOM_DEFAULT,
        #   so a DM reply was posted publicly in the default room and a post typed in room X landed elsewhere.
        room, to = (req.get("room") or "").strip(), (req.get("to") or "").strip()
        me = self._viewer_me()
        if bool(room) == bool(to):
            return self._send(400, json.dumps({"error": "No recipient — pick a room or one person"}),
                              "application/json; charset=utf-8")
        if to:
            why = dm_target_error(to, me)
            if why:
                return self._send(400, json.dumps({"error": why}), "application/json; charset=utf-8")
        else:
            room, why = room_admin.say_room(room, ROOM_DEFAULT)
            if why:
                return self._send(400, json.dumps({"error": why}), "application/json; charset=utf-8")
        msg = {
            "id": uuid.uuid4().hex[:8],
            "t": time.time_ns(),
            "from": me,
            "idSrc": "viewer",                       # Traceable attribution — written by a human, not an MCP session
            "to": to or None,
            "room": room or None,
            "subject": (req.get("subject") or "").strip() or None,   # ★Subject is optional — one-line replies are normal
            "thread": (req.get("thread") or "").strip() or None,
            "body": body,
        }
        rt = (req.get("replyTo") or "").strip()
        if rt:
            msg["replyTo"] = rt
        try:
            with _open_append(BUS_PATH) as f:
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")
        except Exception as e:
            return self._send(500, json.dumps({"error": f"Could not write: {e}"}), "application/json; charset=utf-8")
        return self._send(200, json.dumps({"ok": True, "id": msg["id"]}), "application/json; charset=utf-8")

    def _p_dm(self, u):
        # Work-log compose: one DM to a logged-in session's mailbox id (sidereus/bus.py:dm_send validates).
        req = self._body_json(65536, None)
        if not isinstance(req, dict):
            return self._send(400, json.dumps({"ok": False, "error": "Could not read the body"}, ensure_ascii=False),
                              "application/json; charset=utf-8")
        # ⚠The Stop hook frames a relay as a human instruction: require our page's Origin (no-Origin curl is refused, not downgraded)
        if req.get("relay") is True and not _cfg.viewer_origin(self.headers.get("Origin")):
            return self._send(403, json.dumps({"ok": False, "error": "Relays can only be sent from the Sidereus page",
                                               "err": "relay needs the viewer page"}, ensure_ascii=False),
                              "application/json; charset=utf-8")
        # Pipeline run request / stop (Architecture view): ⚠a stop is validated against its request before anything is sent
        pr = None
        if req.get("plreq") is not None:
            pr, why = pl_reqs.check(req.get("plreq"), req)
            if why:
                return self._send(400, json.dumps({"ok": False, "error": why}, ensure_ascii=False),
                                  "application/json; charset=utf-8")
        try:
            out = dm_send(req, self._viewer_me())
        except Exception as e:
            out = {"ok": False, "error": f"Could not write ({type(e).__name__})"}
        if pr is not None and out.get("ok"):
            try:
                (pl_reqs.stop if pr["kind"] == "stop" else pl_reqs.record)(pr, req["sid"], out["to"], out["id"])
            except Exception:   # the DM is already in the mailbox: flag it, do not fail the send
                out["recorded"] = False
        return self._send(200 if out.get("ok") else 400, json.dumps(out, ensure_ascii=False),
                          "application/json; charset=utf-8")

    def _p_thread_close(self, u):
        # Stale-thread «Clear»: sidereus/bus.py:thread_close validates the name and derives room/recipient from the bus.
        req = self._body_json(4096, None)
        if not isinstance(req, dict):
            return self._send(400, json.dumps({"ok": False, "error": "Could not read the body"}, ensure_ascii=False),
                              "application/json; charset=utf-8")
        try:
            out = thread_close(req, self._viewer_me())
        except Exception as e:
            out = {"ok": False, "error": f"Could not write ({type(e).__name__})"}
        return self._send(200 if out.get("ok") else 400, json.dumps(out, ensure_ascii=False),
                          "application/json; charset=utf-8")

    # ⚠Exact paths only (no prefixes). A path missing here is a 404 (GET: text, POST: JSON) — same as the old if-chain.
    def _p_review_mark(self, u):
        # «Review» mark: {cwd, sid, path | all, on}. Over RV_BODY_MAX / unparsable -> 400; review_mark() recomputes every sig.
        req = self._body_json(RV_BODY_MAX, None)
        try:
            code, out = review_mark(req)
        except Exception as e:
            code, out = 500, {"ok": False, "err": f"{type(e).__name__}"}
        return self._send(code, json.dumps(out, ensure_ascii=False), "application/json; charset=utf-8")

    def _p_term_focus(self, u):
        # «To terminal» {sid}: tty/app come from server rows only; the fixed osascript gets the tty as argv (term.py).
        req = self._body_json(512, None)
        sid = req.get("sid") if isinstance(req, dict) else None
        if not isinstance(sid, str) or not _SID_SAFE.match(sid):
            return self._send(400, json.dumps({"ok": False, "how": "error", "err": "bad sid"}),
                              "application/json; charset=utf-8")
        try:
            code, out = term_focus(sid, sessions_rows(max_age=10))   # ⚠request path: never a cold sessions()
        except Exception as e:
            code, out = 500, {"ok": False, "how": "error", "cmd": "claude --resume " + sid, "err": type(e).__name__}
        return self._send(code, json.dumps(out, ensure_ascii=False), "application/json; charset=utf-8")

    def _p_term_set(self, u):
        req = self._body_json(512, None)
        code, out = term_set(req)
        return self._send(code, json.dumps(out), "application/json; charset=utf-8")

    def _p_prefs_set(self, u):
        # «Preferences» {key, value} | {key, reset}: config.local.json, or 2 keys of ~/.claude/settings.json; ⚠viewer Origin required (no Origin = 403)
        if not _cfg.viewer_origin(self.headers.get("Origin")):
            return self._send(403, json.dumps({"ok": False, "err": "viewer origin required"}),
                              "application/json; charset=utf-8")
        req = self._body_json(PREFS_BODY_MAX, None)
        try:
            code, out = prefs_set_all(req)
        except Exception as e:
            code, out = 500, {"ok": False, "err": type(e).__name__}
        return self._send(code, json.dumps(out, ensure_ascii=False), "application/json; charset=utf-8")

    def _p_pipelines_save(self, u):
        # «Pipelines» save {proj, name, base, dry, defaults?, stages?}: dry = diff, dry:false writes; ⚠viewer Origin required (no Origin = 403)
        # /api/pipelines/create {proj, name, title, template, dry}: same guards, never overwrites (sidereus/pipeline_new.py create)
        # /api/pipelines/delete {proj, name, dry}: same guards, moves the file to pipeline-bak (never deletes)
        # /api/pipelines/projects/add|remove {path}: the person's «+ Add project» list (remove = list entry only)
        # /api/pipelines/apply {mode, proj?}: «Apply» mode read by hooks/pipelines_brief.py (config.local.json `pipeline_apply`)
        if not _cfg.viewer_origin(self.headers.get("Origin")):
            self._body_unread()
            return self._send(403, json.dumps({"ok": False, "err": "viewer origin required"}),
                              "application/json; charset=utf-8")
        req = self._body_json(PIPE_BODY_MAX, None)
        try:
            fn = {"/api/pipelines/create": pipeline_create, "/api/pipelines/delete": pipeline_delete, "/api/pipelines/projects/add": pipeline_add,
                  "/api/pipelines/projects/remove": pipeline_remove, "/api/pipelines/apply": pipeline_apply}.get(u.path, pipeline_save)
            code, out = fn(req)
        except Exception as e:
            code, out = 500, {"ok": False, "err": type(e).__name__}
        return self._send(code, json.dumps(out, ensure_ascii=False), "application/json; charset=utf-8")

    def _p_hooks_connect(self, u):
        # «Connect» {plat, dry} preview / {plat, dry:false, base} write of another CLI's hook file; ⚠viewer Origin required (the diff shows file text)
        if not _cfg.viewer_origin(self.headers.get("Origin")):
            self._body_unread()
            return self._send(403, json.dumps({"ok": False, "err": "viewer origin required"}),
                              "application/json; charset=utf-8")
        req = self._body_json(4096, None)
        try:
            code, out = hook_connect(req)
        except Exception as e:
            code, out = 500, {"ok": False, "err": type(e).__name__}
        return self._send(code, json.dumps(out, ensure_ascii=False), "application/json; charset=utf-8")

    def _p_hooks_remove(self, u):
        # Harness «Remove» {proj, rm, dry} preview / {proj, rm, dry:false, base} write of one settings hook; ⚠viewer Origin required (writes settings, the diff shows file text)
        if not _cfg.viewer_origin(self.headers.get("Origin")):
            self._body_unread()
            return self._send(403, json.dumps({"ok": False, "err": "viewer origin required"}),
                              "application/json; charset=utf-8")
        req = self._body_json(4096, None)
        try:
            code, out = hook_remove(req)
        except Exception as e:
            code, out = 500, {"ok": False, "err": type(e).__name__}
        return self._send(code, json.dumps(out, ensure_ascii=False), "application/json; charset=utf-8")

    def _p_pick_folder(self, u):
        # «Choose folder…»: the OS folder dialog runs on this server (browsers never expose absolute paths); ⚠viewer Origin required
        self._body_unread()
        if not _cfg.viewer_origin(self.headers.get("Origin")):
            return self._send(403, json.dumps({"ok": False, "err": "viewer origin required"}),
                              "application/json; charset=utf-8")
        try:
            code, out = pick_folder()
        except Exception as e:
            code, out = 500, {"ok": False, "err": type(e).__name__}
        return self._send(code, json.dumps(out, ensure_ascii=False), "application/json; charset=utf-8")

    def _p_room_tags(self, u):
        # {room, tags:[...]} -> room-tags.json (Sidereus-owned); ⚠viewer Origin required (no Origin = 403), like other config writes
        if self._refuse_origin():
            return
        req = self._body_json(TAGS_BODY_MAX, None)
        if not isinstance(req, dict):
            code, out = 400, {"ok": False, "error": "Bad request."}
        else:
            try:
                code, out = room_tags_set(req.get("room"), req.get("tags"))
            except Exception as e:
                code, out = 500, {"ok": False, "error": type(e).__name__}
        return self._send(code, json.dumps(out, ensure_ascii=False), "application/json; charset=utf-8")

    def _p_rooms_hide(self, u):
        # {rooms:[...]} -> room-admin.json `hidden` overlay; ⚠never deletes from rooms.json or bus.jsonl
        if self._refuse_origin():
            return
        req = self._body_json(room_admin.BODY_MAX, None)
        if not isinstance(req, dict):
            code, out = 400, {"ok": False, "error": "Bad request."}
        else:
            try:
                code, out = room_admin.set_hidden(req.get("rooms"), u.path == "/api/rooms/hide")
            except Exception as e:
                code, out = 500, {"ok": False, "error": type(e).__name__}
        return self._send(code, json.dumps(out, ensure_ascii=False), "application/json; charset=utf-8")

    def _p_rooms_create(self, u):
        # {room, ids?, topic?}: with ids = the invite path (rooms.json + invite-tag DMs); without = pending overlay only
        if self._refuse_origin():
            return
        req = self._body_json(65536, None)
        if not isinstance(req, dict) or not isinstance(req.get("ids") or [], list):
            code, out = 400, {"ok": False, "error": "Bad request."}
        else:
            room, err = room_admin.check_name(req.get("room"))
            try:
                if err:
                    code, out = 400, {"ok": False, "error": err}
                elif req.get("ids") and room_admin._room_known(room):   # ⚠else «create» silently invites into an existing room
                    code, out = 400, {"ok": False, "error": "This room already exists."}
                elif req.get("ids"):
                    out = self._room_invite(dict(req, room=room))
                    code = 200 if out.get("ok") else 400
                    if out.get("ok") and not out.get("dry"):
                        room_admin.drop_pending(room)
                elif req.get("dry") is True:
                    code, out = 200, {"ok": True, "dry": True, "body": None}   # no invite DM to preview
                else:
                    code, out = room_admin.add_pending(room)
            except Exception as e:
                code, out = 500, {"ok": False, "error": type(e).__name__}
        return self._send(code, json.dumps(out, ensure_ascii=False), "application/json; charset=utf-8")

    def _p_ui_prefs(self, u):
        # {set:{k:v}, del:[k]} -> ui-prefs.json; /reset moves the file to ui-prefs-bak; ⚠viewer Origin required (no Origin = 403)
        if self._refuse_origin():
            return
        req = self._body_json(ui_prefs.BODY_MAX, None)
        try:
            code, out = ui_prefs.reset() if u.path == "/api/ui-prefs/reset" else ui_prefs.update(req)
        except Exception as e:
            code, out = 500, {"ok": False, "error": type(e).__name__}
        return self._send(code, json.dumps(out, ensure_ascii=False), "application/json; charset=utf-8")

    _POST_ROUTES = {
        "/v1/logs": _p_otel, "/v1/metrics": _p_otel, "/api/hook": _p_hook,
        "/api/bg/dismiss": _p_bg_dismiss, "/api/health/dismiss": _p_health_dismiss, "/api/ext/dismiss": _p_ext_dismiss,
        "/api/room/invite": _p_room_invite, "/api/rooms/tags": _p_room_tags,
        "/api/rooms/hide": _p_rooms_hide, "/api/rooms/unhide": _p_rooms_hide, "/api/rooms/create": _p_rooms_create,
        "/api/saver/set": _p_saver_set,
        "/api/cards/read": _p_cards_read, "/api/say": _p_say, "/api/dm": _p_dm,
        "/api/thread/close": _p_thread_close, "/api/review/mark": _p_review_mark,
        "/api/term/focus": _p_term_focus, "/api/term/set": _p_term_set,
        "/api/prefs/set": _p_prefs_set, "/api/pipelines/save": _p_pipelines_save, "/api/pipelines/create": _p_pipelines_save,
        "/api/pipelines/delete": _p_pipelines_save,
        "/api/pipelines/projects/add": _p_pipelines_save, "/api/pipelines/projects/remove": _p_pipelines_save,
        "/api/pipelines/apply": _p_pipelines_save, "/api/pick-folder": _p_pick_folder, "/api/hooks/connect": _p_hooks_connect,
        "/api/hooks/remove": _p_hooks_remove,
        "/api/ui-prefs": _p_ui_prefs, "/api/ui-prefs/reset": _p_ui_prefs, "/api/act": _p_act,
    }
