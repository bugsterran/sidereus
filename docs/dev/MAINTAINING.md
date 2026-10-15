# Maintaining

How issues, PRs and releases are handled. Contributor rules: [CONTRIBUTING.md](../../CONTRIBUTING.md).

## Scope

- One maintainer. A personal-first tool, shared as is.
- macOS is supported. Windows is experimental until it is measured on a real machine.

## What is accepted

- Bug reports.
- Extension PRs: structure language plug-ins, CLI adapters, pipeline templates.
- Core PRs (server, UI, state shape) are closed with a pointer to forking.
- The tiers are defined in [CONTRIBUTING.md](../../CONTRIBUTING.md#what-we-accept); this file does not restate them.

## Response

- Issues are checked about once a week. No reply or fix is guaranteed.

## Issue labels

| Label | For |
|---|---|
| `bug` | Something does not work as documented |
| `adapter` | CLI adapter or other extension work |
| `question` | Usage questions |
| `wontfix` | Core changes; closed with a fork pointer |

A bug report needs: OS, Claude Code version (`claude --version`), and the output of
`/usr/bin/python3 scripts/deps_audit.py`. ⚠No conversation text, private paths or session ids — screenshots from `--demo` only.

## Security reports

- Private channel only: GitHub private vulnerability reporting (Security tab → «Report a vulnerability»).
- Target first response: 7 days.
- Model and reporting details: [SECURITY.md](../../SECURITY.md).

## Versions and release

- SemVer, 0.x. The first public release is `0.1.0`.
- [CHANGELOG.md](../../CHANGELOG.md) (Keep a Changelog) is the single source. Every feature or fix commit adds one line under `[Unreleased]`.
- Before a release: pipeline `deps-audit`, then `bash scripts/check.sh --full`.
- Release:
  1. Rename `[Unreleased]` to `[x.y.z] - YYYY-MM-DD`, open a new empty `[Unreleased]`.
  2. Tag `vx.y.z`.
  3. Release notes = that CHANGELOG section plus 3–5 highlights at the top.
- ⚠Screenshots only from `python3 -m sidereus start --demo` — never the real viewer.

## Milestones

- Version = milestone.
- Before public: one milestone, `0.1.0 — first public`.
- After: bugs go to the next patch (`0.1.x`), features to the next minor.

## Compatibility watch

- Claude Code updates are the main source of breakage: OTel attributes, transcript format, hook events.
- ⇒ On a Claude Code version bump, run the contract tests (`bash tests/run.sh`, at least
  `test_adapter_contract.py` and the `test_otel_*` / hook tests) before anything else.
- README states the supported Claude Code version range.

## Cadence

One maintenance day a month:

1. Triage open issues and PRs.
2. Run the `deps-audit` pipeline (`/usr/bin/python3 scripts/deps_audit.py --online`).
3. Release if anything under `[Unreleased]` is ready.

## Release decisions

- **Comments in English only** — one language in code; two would mean duplicated files that diverge. ⚠Do not shorten `★` evidence or `⚠` prohibitions; ⚠never quote request text.
- **Docs split by audience, not translated** — public `README` · `docs/HOOKS.md` · `docs/CONFIG.md` (English + `.ko.md`); internal `AGENTS.md` · `docs/dev/` · `docs/notes/` are excluded by `.distignore`.
- **UI strings are English-source**, Korean in `I18N.ko` (`AGENTS.md` «Style»).
- `.distignore`: `refactor/` ships (`snap.py`, README, `STAGE3.md`) but `refactor/snap/` does not (live metadata); `tests/` incl. `golden/` ships (synthetic, leak grep 0); `.playwright-mcp/`, `HANDOVER-*`, `NOTES-*`, `AUDIT-*` stay out.
- Provenance (2026-09-24): copied code · CDN · bundled libraries **0**; file-type icons (`web/js/07-file-icons.js`) and favicon self-made; Codex and Grok marks replaced by self-made «CX» / «GK» glyphs; the other logos are simple-icons, attributed in `THIRD_PARTY_NOTICES.md` (CC0 17 + Copilot MIT).

| Feature | Verdict | Kept as |
|---|---|---|
| Colours · thresholds 10%/30% | derived | own OKLCH palette, 0 Grafana hex; «inspired by Grafana's dark theme» in README |
| Worktree as work unit | derived | + 5-hour occupancy · today's tokens · attention chip · git state; attribution only |
| Token totals · history tab · waiting badge | derived | attribution only |
| Quota back-calculation · OTel receiver · attention · mailbox · structure · timeline replay · external CLI hooks | original | — |

- ⚠Grafana values are not copyrightable (theme package Apache-2.0) — an originality issue, not a legal one.

## TODO before 0.1.0

- Issue labels `adapter`, `question`, `wontfix` (only `bug` is referenced, by `.github/ISSUE_TEMPLATE/bug_report.md`).
- Bug template: add a required `deps_audit.py` output field; make Claude Code version required (today optional, under «Other plugins / hooks»).
- Question template (only `bug_report.md` exists; feature requests are not taken — core is fork-only).
- README «How this project works»: add the weekly response line and the supported Claude Code version range.
- SECURITY.md «Reporting a problem»: add the 7-day first-response target (today: «no promise of a reply»).
- CONTRIBUTING.md: state that core PRs are closed with a fork pointer (today: «Not accepted … Fork for these»).
- CHANGELOG backfill: 7 of 116 commits since 2026-10-01 touched CHANGELOG.md; no versioned section or tag exists yet.
- A Claude Code format contract test set (transcript, OTel, hook events) — only the adapter contract is named as one today.
