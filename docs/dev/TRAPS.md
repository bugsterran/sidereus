# Sidereus — traps already hit

Do not step on these again. One file per area under [traps/](traps/); read the area before you touch it.

| File | Area | Entries |
|---|---|---|
| [traps/arch.md](traps/arch.md) | Structure tab: architecture map, flows, arch_verify, Size treemap, language plug-ins | 70 |
| [traps/timeline.md](traps/timeline.md) | Timeline rows, bars, sleep/idle bands, replay, «Changes» rail | 43 |
| [traps/quota.md](traps/quota.md) | Quota, burndown, saver mode, token and usage accounting | 90 |
| [traps/sessions.md](traps/sessions.md) | Session state, subagents, external CLIs, permission badges, work-log popup and diff window | 50 |
| [traps/pipeline.md](traps/pipeline.md) | Pipeline runs, `pl_flow` stage hooks, stage lighting, gates, evaluation | 45 |
| [traps/git.md](traps/git.md) | Branch tab, board, git, worktrees, History and retro tabs | 20 |
| [traps/attention.md](traps/attention.md) | Alarms, cards, health strip, attention ranking | 20 |
| [traps/mailbox.md](traps/mailbox.md) | Mailbox, chat rooms, mail watch (`mailbox_wake`) | 23 |
| [traps/ui.md](traps/ui.md) | UI kit, CSS, layout, header, i18n (`T()`), animations, drag-resize | 66 |
| [traps/server.md](traps/server.md) | Server, `/api/state` payload, caching, performance | 20 |
| [traps/security.md](traps/security.md) | Security and privacy (CSP, guards, metadata-only) | 25 |
| [traps/platform.md](traps/platform.md) | Platform, config, launcher, Windows, plugin, tests and tooling | 47 |
| [traps/general.md](traps/general.md) | General lessons that span areas | 30 |
| [traps/archive.md](traps/archive.md) | Removed features — evidence only, not current rules | 4 |

## Adding a trap

- Put it at the **top of its area** in the matching file (AGENTS.md rule 6); newest first.
- No file fits ⇒ use the closest one; a new file only with an index row here.
- A trap about code you delete ⇒ move its entry to `traps/archive.md` under «From «<area>»».
- Entry shape — `docnote` skill:

```
- ★**<one-line conclusion>** (<date> · <user quote or trigger>).
  - Cause: <mechanism> (★measured <number>).
  - ⇒ <fix>.
  - ⚠<what the next person must not undo>.
```

`★` evidence · `⚠` trap / prohibition · `⇒` fix. Older entries are kept verbatim — their ★ evidence and ⚠ rules are the record.
`§N` = item N of the 2026-08-19 feature log in [HANDOVER.md](HANDOVER.md#feature-log-2026-08-19-137). `:NNNN` line numbers predate the file split — grep the name instead.
Code comments cite an entry as `TRAPS «<title words>»` — grep `docs/dev/traps/` for the words.
