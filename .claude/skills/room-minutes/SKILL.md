---
name: room-minutes
description: Append dated meeting minutes (Decisions / Open questions) for one mailbox room to docs/decisions/<room>.md in the current project, reading only messages since the last run. Use when asked to record, summarise or take minutes of a mailbox room's decisions.
---

# Room minutes

Input: a room name. Output: one new section appended to `$PWD/docs/decisions/<slug>.md`.

## Steps

1. Run the reader (path relative to this skill's base dir):
   ```
   /usr/bin/python3 <skill dir>/../../../scripts/room_log.py "<room>" --doc-dir "$PWD/docs/decisions"
   ```
   The header ends with `doc=<path>` — the file to append to (the script picks the name and resumes from its last marker).
   Exit 2 = bad name or unknown room: report the one line and stop.
2. Header `n=0` -> reply one line («no new messages in <room> since <after>») and write nothing.
3. Otherwise append to the header's `doc=` file (create the folder and file if missing):
   ```
   ## <date part of from> (<from>–<to>)
   ### Decisions
   - <decision> (<HH:MM> <sender>)
   ### Open questions
   - <question> (<HH:MM> <sender>)
   <!-- room-minutes: room=<room> until=<until> last=<last> -->
   ```
   - ⚠Copy values, never convert: `from`/`to` come from the header as printed; never turn epoch ns (`until`) into a time.
   - Every bullet ends with `(<HH:MM> <sender>)` — HH:MM cut from that message's own time column, sender from its sender column.
   - Every `[D]` line (the Korean decision tag or `Decision:` in chat) is a Decisions bullet — always.
   - Other decisions / unanswered questions: your judgement; an empty list gets `- none`.
   - Marker values are copied verbatim from the header (`room=` is percent-encoded — keep it so); the marker is the section's last line.
   - Doc language = the conversation language.

## Rules

- ⚠Append only. Never edit, reorder or rewrite earlier sections — the reader cuts at the last marker, so a changed marker re-reads or skips messages.
- Message bodies stay in this session and the doc; nothing goes to the Sidereus page or MCP.
- This is a project skill (loads in sessions started in this repo); other projects need a user-level install (`~/.claude/skills/room-minutes/` with the script path adjusted).
