# 리뷰 파이프라인

주요 플랫폼이 공개한 내용을 바탕으로, 자기 CLI 에 맞는 리뷰·검증 파이프라인을 쓰는 법.
파이프라인 파일 형식: [EXTENDING › 파이프라인](EXTENDING.ko.md#파이프라인). English: [REVIEW-PIPELINES.md](REVIEW-PIPELINES.md).

템플릿(`<project>/.claude/pipelines/<name>.json` 으로 복사하고 `name` 을 파일 이름과 맞춘다):

- [review-claude.json](examples/pipelines/review-claude.json): Claude Code, 찾기 둘을 병렬로.
- [review-codex.json](examples/pipelines/review-codex.json): Codex CLI, 한 번에. 미검증.
- [review-gemini.json](examples/pipelines/review-gemini.json): Gemini CLI, 한 번에. 미검증.

셋 다 Context, Find, Verify, Gate 순서다. Gate 는 확인된 Important 지적이 있을 때만 실패하고, Find 로 한 번만 되돌아간다.

## 플랫폼별 방식

자료는 2026-10-17 에 읽었다. 숫자는 자료에 나온 것만 옮겼다.

**Anthropic**: [Solving code review at Anthropic](https://claude.dev/blog/solving-code-review-at-anthropic/)

- 찾는 쪽 여럿이 병렬로 돈다. 그다음 별도 그룹이 지적 하나하나에 투표한다. 스타일·정리 지적은 버린다.
- 저장소 주인이 `REVIEW.md` 를 쓴다: 무엇을 실패로 볼지, 사소한 지적(nit) 상한, 건너뛸 경로, 지적마다 file:line 근거.
- 라운드 상한: 3라운드가 지나면 작성자에게 변경을 다시 생각해 보라고 한다. 다시 리뷰할 때는 새 diff 만 읽는다.
- 태그: Important, Nit, Pre-existing.
- 결과: 실질적인 지적 비율 16% → 54%. 한 라운드에 통과 65% → 78%. 5라운드 이상 걸린 리뷰 8.9% → 1.5%.

**OpenAI**: [Scaling code verification](https://alignment.openai.com/scaling-code-verification) (2025-12-01)

- 저장소에 접근하고 코드를 실행할 수 있는 전담 리뷰어가 diff 만 보는 리뷰어보다 낫다.
- 정밀도가 먼저고, 재현율은 다소 낮아져도 받아들인다. 지적은 그 이득이 확인 비용과 예상 오탐 비용의 합보다 클 때만 남긴다. 스타일 지적은 오히려 손해일 수 있다.
- 작성자는 지적의 52.7% 에서 코드를 고쳤다.
- GitHub 의 Codex 리뷰는 P0/P1 만 올린다. 규칙은 가장 가까운 `AGENTS.md` 의 «Code Review Rules» 절에서 읽는다(예전 문서: «Review guidelines»). 규칙은 두세 개로 시작하고 포맷·린트는 CI 에 맡긴다. 푸시 전에는 Codex CLI 에서 `/review` 를 돌린다.

**Google**: [Gemini Code Assist, 리뷰 맞춤 설정](https://docs.cloud.google.com/gemini/docs/code-review/customize-repo-review)

- 심각도는 LOW, MEDIUM, HIGH, CRITICAL.
- `.gemini/config.yaml` 에 `code_review.comment_severity_threshold`(기본 MEDIUM), `max_review_comments`, `ignore_patterns` 가 있다. 스타일 규칙은 `.gemini/styleguide.md`.
- 연구: [Resolving code review comments with ML](https://research.google/blog/resolving-code-review-comments-with-ml/) (2023-05-23). 목표 정밀도 50% 에 맞춰 보정했다. 실제 배포에서 리뷰어 지적의 7.5% 가 이 방식으로 해결됐다.

**Meta**

- MetaMateCR([arXiv 2507.13499](https://arxiv.org/abs/2507.13499)): 무작위 안전성 시험에서 리뷰가 5% 넘게 느려져, 패치를 작성자에게만 보여 주기로 했다.
- TestGen-LLM([arXiv 2402.09171](https://arxiv.org/abs/2402.09171)): 생성한 테스트는 빌드되고, 안정적으로 통과하고, 커버리지를 올릴 때만 남긴다. 생성분 중 75% 가 빌드됐고 57% 가 안정적으로 통과했고 25% 가 커버리지를 올렸다. 추천의 73% 가 받아들여졌다.
- Muse Code 는 Meta 의 코딩 에이전트다. 공개된 리뷰 방식은 찾지 못했다.

**Cursor**: [Building Bugbot](https://cursor.com/blog/building-bugbot) (2026-01-15)

- 8번을 병렬로 돌리고 다수결로 정한다. 그다음 검증 모델이 결과를 확인하고, 이전 실행에서 이미 낸 지적은 지운다.
- 해결률 52% → 70%+. 설정은 `BUGBOT.md`.

**GitHub Copilot**

- 지시는 `.github/copilot-instructions.md` 와 `.github/instructions/*.instructions.md`(`applyTo` 로 범위 지정)에 둔다. 앞 4,000자만 읽는다.

## 공통 패턴

| 패턴 | 파이프라인 필드 |
|---|---|
| 재현율보다 정밀도: 적게 내되 맞게 | Verify·Gate 의 `task`(Nit 은 버리고 Important 에서만 막는다). Find 에는 더 강한 `model` |
| 지적마다 반박을 시도하는 별도 검증 단계 | Find 뒤에 다른 `agent`(와 `model`)로 단계를 따로 둔다 |
| diff 만이 아니라 저장소 맥락과 코드 실행 | 맨 앞에 Context 단계. Verify 의 `gate` 에 테스트 명령을 둘 수 있다 |
| 짧고 범위가 좁은 규칙 파일 | `rules` 가 CLI 고유의 규칙 파일을 가리킨다. 긴 절차는 `skill` 로 |
| 다시 돌릴 때는 새 지적만 | Find `task`: "되돌아온 뒤에는 수정 diff 만 리뷰" |
| 라운드 상한 | Gate `onFail.max`(템플릿은 1). 실행 전체 상한은 `guards.maxLoopBacks`(Claude Code 만) |
| 결과 측정 | Verify 대장(id, rule, verdict)과 `after`. Sidereus 는 실행마다 단계·되돌림 횟수·시간을 기록한다 |

`use` 는 세션마다 파이프라인 목록에서 보는 한 줄이다. 목적은 여기에 적는다.

이 저장소의 `review` 파이프라인은 마지막에 «리뷰-확인» 단계(`sidereus-review-verifier`)가 있어 찾은 지적을 하나씩 반박해 보고 확인된 것만 보고한다.

이 저장소의 `security-checks` 파이프라인도 같은 생각이다. 위협 모델 리뷰 단계는 세션에 그 프로젝트의 보안 리뷰 에이전트가 있으면 그것으로 돌리고(`[pl-agent:]` 로 선언), 대상 저장소에 위협 모델이 없으면 기본 관점(권한 우회, 주입, 비밀값, SSRF, 위험한 파일 처리)으로 본다.

## CLI 별

| | Claude Code | Codex CLI | Gemini CLI |
|---|---|---|---|
| 리뷰어가 읽는 규칙 파일 | `REVIEW.md` 또는 `.claude/review-guide.md`, 그리고 `AGENTS.md`/`CLAUDE.md` | `AGENTS.md` 의 «Code Review Rules» 절 | `.gemini/styleguide.md` + `.gemini/config.yaml` |
| 단계 실행 방식 | Agent 도구 서브에이전트, 설명에 `[pl:<name>/<stage>]` 태그. Find 는 한 메시지에서 서브에이전트 둘 | 한 세션이 단계를 차례로 돈다. 단계는 셸 명령 `echo "[pl:<name>/<stage>]"` 로 시작하고 `[pl-end:<name>/<stage>]`(또는 `…\|fail]`)로 끝낸다 | Codex 와 같은 셸 마커 |
| Sidereus 지원 | 단계 표시, 순서·agent·model 확인(`pl_mark.py`, `pl_flow.py`), 커밋 전 `guards` | 마커와 다음 단계 안내(`pl_mark.py` / `pl_flow.py --platform codex`). guards 없음. ⚠훅 입력 형식은 실제 CLI 로 확인하지 않았다 | 마커와 안내(`--platform gemini`). guards 없음. ⚠입력 형식은 실제 CLI 로 확인하지 않았다 |
| 템플릿 | 이 저장소의 리뷰(`sidereus-change`)와 같은 단계 | CLI 에서 미검증 | CLI 에서 미검증 |

- `model` 은 `inherit|opus|sonnet|haiku` 만 받는다. Codex·Gemini 템플릿은 `inherit` 이라 CLI 자체 모델을 쓴다.
- Codex·Gemini 에서 `agent` 는 이름표일 뿐이다. 확인하는 곳이 없다.
- Gemini CLI 가 서브에이전트로 나눠 돌릴 수 있는지는 확인하지 않았다. 그래서 템플릿은 한 번에 돈다.
- Codex·Gemini 훅 설정: [HOOKS › 외부 CLI 훅](HOOKS.ko.md#외부-cli-훅).
