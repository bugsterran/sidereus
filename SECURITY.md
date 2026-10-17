# Security

**English** · [Korean](SECURITY.ko.md)

Sidereus is a local monitor plus a control relay. Everything it does, and how to turn each part off.

## Model

- **Local only.** The server binds `127.0.0.1` (hard-coded). Nothing listens on other interfaces, and no CORS header is sent.
- **Host check on every request.** Only `127.0.0.1:<port>` and `localhost:<port>` are accepted — a DNS-rebinding guard.
- **Origin check on POST.** A browser POST from another origin gets 403. Requests without `Origin` (OTel export, curl, local hooks) pass, because browsers always attach `Origin` to cross-origin POSTs.
- **Cross-site GET refused too.** `/api/*` GETs with `Sec-Fetch-Site: cross-site` get 403 (a cross-site page could otherwise trigger side-effecting/expensive calls via `<img>`); same-site and header-less requests (curl, hooks, MCP) pass.
- **No auth beyond loopback.** Any local process, or another OS user on the same machine, can call the API. Browsers are kept out by the Host, Origin and `Sec-Fetch-Site` checks, and the page refuses to be framed (`frame-ancestors 'none'`, `X-Frame-Options: DENY`).
- **Work-popup endpoints are same-user only on macOS.** `/api/session/work`, `/api/agent/work` and `/api/ext/work` return transcript tails, so they return 403 unless the client end of the loopback connection belongs to a process of the viewer's own OS user (checked with `/usr/sbin/lsof`; a missing or slow `lsof` also means 403).
  ⚠ On other OSes those endpoints are still readable by any local process, including another user's `curl`. On every OS the rest of `/api` stays unauthenticated, and the `/work` HTML shell is served to anyone local.
- **No process-spawning endpoints.** No request from the page runs a shell, git checkout/merge or a session.
- **Mailbox DMs only to registered ids** (`identity.json`), never to a guessed name.
- The only outbound request is the optional quota lookup to `api.anthropic.com`, using the OAuth token from the macOS keychain.
- **Dev scripts, not the viewer:** `scripts/arch_checks.py --category security` and `scripts/deps_audit.py` query free advisory sources (OSV.dev, npm, semgrep registry, endoflife.date) when you run them — package names and versions only; `--offline` skips them, and an unreachable network is reported as skipped, never as clean.
- **Paid quota probe — off by default.** With `quota_probe: true` (or `SIDEREUS_QUOTA_PROBE=1`), while the lookup returns 429 the viewer sends one Haiku request to `api.anthropic.com/v1/messages` every 120 s with the same token (`max_tokens 1`, about $0.00002 each, billed to that account) and reads only the rate-limit headers; the body is discarded.

## What it never does

- **No telemetry.** Nothing about you or your sessions leaves the machine (the one exception is the quota lookup above).
- **Conversation content never reaches the page or the MCP tools.** Only metadata: path, session id, model, the agent's one-line task label. The single exception is the work popup, which opens only on click. The leak scan and the tests enforce this.
- **No git writes.** Every git call goes through `git_argv`, with `core.fsmonitor=false` and `core.hooksPath=/dev/null`.
- **No direct CLI control.** No pty, no stdin injection, no send-keys, no spawn or kill of sessions. Instructions go through the mailbox, and only after you preview and confirm them.

## What it does that a security review may ask about

| # | Behaviour | Where | Why | Turn off |
|---|---|---|---|---|
| 1 | Reads the Claude Code OAuth token from the macOS keychain (`security find-generic-password`) and sends it as a Bearer header to `api.anthropic.com/api/oauth/usage`. The token is never logged, stored or shown. Each extra signed-in config root (several accounts) is looked up the same way: its own keychain service (`Claude Code-credentials-<sha256 of the dir>[:8]`, checked by exit code before `-w` reads it), else `<root>/.credentials.json`. | `sidereus/quota.py`, `sidereus/quota_fetch.py`, `sidereus/quota_roots.py` | 5h/7d quota cards, «Other accounts» lines and the saver pace | `"quota_lookup": false` or `SIDEREUS_QUOTA_LOOKUP=0` (quota cards go blank) |
| 2 | Paid probe: while the usage API returns 429, one Haiku call (`max_tokens 1`) every 120 s reads the credit ratio from response headers. | `sidereus/quota.py` | credit line | Off by default (`quota_probe`) |
| 3 | Runs a fixed AppleScript (tty passed as an argument) to bring an iTerm2 or Terminal tab to the front. It never types into it. | `sidereus/term.py` | go-to-terminal button | Settings > Terminal > `off` |
| 4 | Holds `caffeinate` while sessions are working, so the Mac does not idle-sleep. | `sidereus/awake.py` | a sleeping Mac stops the sessions | `"keep_awake": false` |
| 5 | Writes Claude Code config: project `.claude/pipelines/*.json` (stage agent/model only) and two keys of `~/.claude/settings.json` (`autoCompactEnabled`, `autoCompactWindow`). Each write shows a diff preview and needs confirmation. The old file is backed up first, and the viewer Origin is required. Paths outside the allow-list are refused. Skills, agents, commands, MCP servers and hooks are shown read-only (MCP `env` values masked); nothing writes them. | `sidereus/pipeline.py`, `sidereus/cc_settings.py` | edit pipelines and auto-compact from the viewer | do not use those editors; nothing is written otherwise |
| 6 | Reads transcripts under `~/.claude/projects/`, locally, to derive metadata. | `sidereus/sessions.py` and others | the monitor itself | this is the product |
| 7 | Read-only system commands: `ps`, `lsof`, `sysctl`, `pmset`, `git`, `ccusage` (optional). | `sidereus/live*.py`, `sidereus/gitinfo.py`, `sidereus/burn_usage.py` | live-session detection, sleep gaps, git views, daily totals | — |

Settings go in `config.local.json` ([docs/CONFIG.md](docs/CONFIG.md)); restart the viewer afterwards.

## Security tools

`scripts/arch_checks.py --category security` uses these scanners when they are installed. Settings > Diagnostics > «Security tools» shows which ones are found on `PATH` and their version, read from the install's files; Sidereus never runs or installs them. «Copy» only puts the command on the clipboard.

| Tool | What it catches | Install (macOS · Windows) | Needs network? |
|---|---|---|---|
| `gitleaks` | Secrets committed to the repo (API keys, tokens, passwords) | `brew install gitleaks` · `winget install Gitleaks.Gitleaks` | no |
| `semgrep` | Risky code patterns such as injection or unsafe calls, in many languages | `brew install semgrep` · `pip install semgrep` | only for registry rules (no local `.semgrep.yml`) |
| `bandit` | Common security issues in Python code | `brew install bandit` · `pip install bandit` | no |
| `osv-scanner` | Known vulnerabilities in dependencies, read from lockfiles | `brew install osv-scanner` · `winget install Google.OSVScanner` | yes |
| `npm` | Known vulnerabilities in npm packages (npm audit) | `brew install node` · `winget install OpenJS.NodeJS.LTS` | yes |

## Reporting a problem

Please report privately through GitHub private vulnerability reporting (the repo's Security tab → "Report a vulnerability") rather than in a public issue. Include what you ran, what you saw,
and the commit you tested.
The threat model and scanner image for [Anthropic OSS Scanner](https://github.com/anthropics/oss-scanner) are in [`.oss-scanner/`](.oss-scanner/).
There is no promise of a reply or a fix: the project is shared as-is, and PRs are accepted for extensions only ([README](README.md#how-this-project-works)).
