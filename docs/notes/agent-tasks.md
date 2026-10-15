# Agent task mail (③ tasks · ② discovery) — design (2026-09-24)

⏸**Not started — on hold** with the other-platform work (`ext-agents.md` «On hold»). Nothing below is implemented.

Goal: use the mailbox as a free channel between agents, not only as chat rooms.
References: Orca = typed inbox (worker_done · question) + blocking `check --wait` · Paseo = MCP `create_agent/send_agent_prompt/wait`.

## Format — DM on the existing bus + optional fields (old readers ignore them)
- Task: `kind:"task"`, `thread:"task:<id>"`, `task:{id, parent, root, depth, ttl_s(default 1800 · max 14400), budget(hint)}`.
- Status/question/result: `kind`, `task:{id, state, note}` on the same thread. States = accepted · running · done · failed · cancelled (+question).
- State is not stored; it is computed by replaying the bus — `mailbox_core.task_state()` (same approach as thread_state). `expired` is derived.
- ⚠Do not group tasks by thread key — the DM thread_key includes `to`, so each direction has a different key (`thread_key`, mailbox_core.py:291).

## Tools
`mailbox_task(to, body, subject?, parent?, ttl_s?, budget?)→id` · `mailbox_task_update(id, state, note?, body?)` · `mailbox_tasks(filter)` · `mailbox_agents(worker_only?)` · `mailbox_wait(kind="task"|"any")`.

## Safety (checked on the server)
- Accepted only when the receiver is a worker (`.mail-worker`) and alive · depth ≤2 · sending to self or an ancestor is refused · ≤3 open tasks per pair · no sending while paused.
- Status and results do not wake the worker (it waits on kind=task) — prevents ping-pong. Only the assignee changes state; only the requester, an ancestor or a person cancels. Finished states are never reverted.
- ⚠Prerequisite defect: if Gemini uses a Claude name via `mailbox_login`, nothing stops it — the server must block this before tasks are accepted.

## Discovery
The presence file holds a single integer and cannot carry capabilities ⇒ `profiles.json[id] = {role, platform, model, worker, cwd, updated}` (written by mailbox_login). Platform comes from the `CLAUDE_PROJECT_DIR` prefix (`gemini:`/`codex:`).

## Sidereus (metadata only — no body · note · subject)
`state().tasks = [{id, root, parent, depth, from, to, state, t0, tu, deadline, expired, nUpd}]` · `state().agents = [{id, platform, model, worker, cwd, online, act}]` · timeline links go identity.json → session id.
- ⚠`state().messages` already sends bus bodies (`messages()`, sidereus/bus.py:159) — whether task bodies show in the chat tab is the owner's decision.

## Phases (tests per phase)
P1 `task_state` · chain checks (mailbox_core) → P2 server tools · guards → P3 discovery (login args · mailbox_agents · codex launcher) → P4 delivery (monitor_stream · mailbox_stop · gemini_mail_stop) → P5 Sidereus tasks/agents + screen → P6 live Codex integration.
- ⚠Codex Stop block · `queue --thread` · app-server are not confirmed in code (measure in P6).
