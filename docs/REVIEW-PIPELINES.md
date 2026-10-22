# Review pipelines

How to write a review or verification pipeline for your CLI, based on what the major platforms have published.
Pipeline file format: [EXTENDING › Pipeline](EXTENDING.md#pipeline). Korean: [REVIEW-PIPELINES.ko.md](REVIEW-PIPELINES.ko.md).

Templates (copy one to `<project>/.claude/pipelines/<name>.json` and set `name` to the file stem):

- [review-claude.json](examples/pipelines/review-claude.json): Claude Code, two parallel finders.
- [review-codex.json](examples/pipelines/review-codex.json): Codex CLI, one pass. Untested.
- [review-gemini.json](examples/pipelines/review-gemini.json): Gemini CLI, one pass. Untested.

Each one runs Context, Find, Verify, Gate. Gate fails only on a confirmed Important finding and loops back to Find once.

## What the platforms do

Sources were read 2026-10-17. Numbers are the ones the sources give.

**Anthropic**: [Solving code review at Anthropic](https://claude.dev/blog/solving-code-review-at-anthropic/)

- Several finders run in parallel. A separate group then votes on each finding. Style and cleanup comments are dropped.
- The repo owner writes `REVIEW.md`: what counts as a failure, a cap on nits, paths to skip, and file:line evidence for every finding.
- Round cap: after 3 rounds the author is asked to rethink the change. A re-review reads only the new diff.
- Tags: Important, Nit, Pre-existing.
- Results: substantive comments rose from 16% to 54%. Passing after one round rose from 65% to 78%. Reviews that took 5+ rounds fell from 8.9% to 1.5%.

**OpenAI**: [Scaling code verification](https://alignment.openai.com/scaling-code-verification) (2025-12-01)

- A dedicated reviewer that has repo access and can run code does better than one that sees only the diff.
- Precision comes first, at the cost of somewhat lower recall. A finding is kept only when its benefit is larger than the cost of checking it plus the expected cost of a false alarm. Style comments can be worth less than nothing.
- Authors changed the code after 52.7% of comments.
- Codex review on GitHub posts only P0/P1 findings. Rules come from the nearest `AGENTS.md` section «Code Review Rules» (older docs call it «Review guidelines»). Start with two or three rules and leave formatting and lint to CI. Before pushing, run `/review` in Codex CLI.

**Google**: [Gemini Code Assist, customize review](https://docs.cloud.google.com/gemini/docs/code-review/customize-repo-review)

- Severities are LOW, MEDIUM, HIGH and CRITICAL.
- `.gemini/config.yaml` has `code_review.comment_severity_threshold` (default MEDIUM), `max_review_comments` and `ignore_patterns`. Style rules go in `.gemini/styleguide.md`.
- Research: [Resolving code review comments with ML](https://research.google/blog/resolving-code-review-comments-with-ml/) (2023-05-23). The model was calibrated to a 50% target precision. In deployment, 7.5% of reviewer comments were resolved this way.

**Meta**

- MetaMateCR ([arXiv 2507.13499](https://arxiv.org/abs/2507.13499)): in a randomized safety trial, reviews were more than 5% slower, so patches were shown only to authors.
- TestGen-LLM ([arXiv 2402.09171](https://arxiv.org/abs/2402.09171)): a generated test is kept only if it builds, passes reliably and raises coverage. Of the generated tests, 75% built, 57% passed reliably and 25% raised coverage. 73% of its recommendations were accepted.
- Muse Code is Meta's coding agent. No published review mechanism was found.

**Cursor**: [Building Bugbot](https://cursor.com/blog/building-bugbot) (2026-01-15)

- 8 passes run in parallel and a majority vote decides. A validator model then checks the result, and findings already reported by earlier runs are removed.
- The resolution rate rose from 52% to 70%+. Configuration lives in `BUGBOT.md`.

**GitHub Copilot**

- Instructions go in `.github/copilot-instructions.md` and in `.github/instructions/*.instructions.md`, scoped with `applyTo`. Only the first 4,000 characters are read.

## Common patterns

| Pattern | Pipeline field |
|---|---|
| Precision over recall: report less, but be right | `task` of Verify and Gate (drop Nits, block only on Important). Use a stronger `model` for Find |
| A separate verify step that tries to disprove each finding | its own stage with a different `agent` (and `model`) after Find |
| Repo context and code execution, not only the diff | a Context stage first. Verify may set `gate` to your test command |
| A short, scoped rules file | `rules` points at the CLI's native rules file. A longer procedure goes in a `skill` |
| Re-runs report only new findings | Find `task`: "after a loop-back, review only the fix diff" |
| Round cap | Gate `onFail.max` (1 in the templates). `guards.maxLoopBacks` caps the whole run (Claude Code only) |
| Measure outcomes | the Verify ledger (id, rule, verdict) and `after`. Sidereus records each run's stages, loop rounds and times |

`use` is the one line each session sees in the pipeline list, so keep the purpose there.

This repo's `security-checks` pipeline follows the same idea: its threat-model review stage runs on the project's own security-review agent when the session has one (declared with `[pl-agent:]`), and falls back to a default lens (authz bypass, injection, secrets, SSRF, unsafe files) when the target repo has no threat model.

## Per CLI

| | Claude Code | Codex CLI | Gemini CLI |
|---|---|---|---|
| Rules file the reviewer reads | `REVIEW.md` or `.claude/review-guide.md`, plus `AGENTS.md`/`CLAUDE.md` | `AGENTS.md` section «Code Review Rules» | `.gemini/styleguide.md` + `.gemini/config.yaml` |
| How a stage runs | Agent tool subagent, with the description tagged `[pl:<name>/<stage>]`. Find runs two subagents in one message | One session runs the stages in turn. Each stage starts with a shell command `echo "[pl:<name>/<stage>]"` and ends with `[pl-end:<name>/<stage>]` (or `…\|fail]`) | Same shell markers as Codex |
| Sidereus support | Stage lighting, order, agent and model checks (`pl_mark.py`, `pl_flow.py`), and `guards` before commit | Markers and next-stage hand-off (`pl_mark.py` / `pl_flow.py --platform codex`). No guards. ⚠Hook payload shape has not been checked against the real CLI | Markers and hand-off (`--platform gemini`). No guards. ⚠Payload shape not checked against the real CLI |
| Template | same stages as this repo's own review (`sidereus-change`) | untested on the CLI | untested on the CLI |

- `model` accepts only `inherit|opus|sonnet|haiku`. The Codex and Gemini templates use `inherit`, so the CLI's own model is used.
- `agent` is only a label on Codex and Gemini: nothing there checks it.
- Whether Gemini CLI can fan out to subagents was not checked, so its template uses one pass.
- Hook setup for Codex and Gemini: [HOOKS › External CLI hooks](HOOKS.md#external-cli-hooks).
