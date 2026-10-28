# Sidereus

[English](README.md) · **한국어**

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.9, stdlib only](https://img.shields.io/badge/python-3.9%20stdlib%20only-3776AB.svg)
![Platform: macOS · Windows](https://img.shields.io/badge/platform-macOS%20%C2%B7%20Windows-lightgrey.svg)

**여러 AI 코딩 세션을 검증하는 로컬 관측소입니다.**
터미널에서 돌고 있는 Claude Code, Codex CLI, Gemini CLI 세션 옆에서, 각 실행이 파이프라인을 따랐는지와 판정의 근거가 무엇인지를 한 화면에 보여 줍니다. 에이전트를 실행하거나 터미널을 조작하지는 않습니다.

- **모니터링**: 모든 세션을 한 화면에, 내 답을 기다리는 세션을 먼저 보여 주고, 각 에이전트가 한 일을 타임라인으로 남깁니다.
- **파이프라인과 하네스 리포트**: 단계 순서와 게이트, 그리고 결과가 나중에도 유지됐는지를 보여 줍니다.
- **구조와 보안**: 저장소의 모듈·흐름 지도와 보안 점검을 보여 줍니다.

![애니메이션: change-flow 실행의 단계에 차례로 불이 들어옴 — 설계, 구현, 검증, 리뷰에서 한 번 되돌린 뒤 구현·검증을 다시 거쳐 리뷰 완료](docs/images/hero-ko.gif)

## 데모로 둘러보기

합성 데이터만 씁니다. 실제 데이터는 읽지 않습니다.

```sh
git clone https://github.com/bugsterran/sidereus.git ~/sidereus && cd ~/sidereus
python3 -m sidereus start --demo --open      # 18799 포트, Ctrl-C로 끕니다. Windows: py -m sidereus
```

## 파이프라인

뷰어를 열면 이 화면이 먼저 나옵니다. 파이프라인은 `.claude/pipelines/*.json`에 한 번 정해 두는 단계 순서입니다(단계별 에이전트·모델, 게이트, 되돌림). 세션이 작업에 `[pl:<파이프라인>/<단계>]` 태그를 붙이면 해당 단계에 불이 들어옵니다.

- **지금 작업 중**(왼쪽): 살아 있는 세션마다 카드 하나. 실행 요약(«작업 중 · 검증», «응답 필요 · 리뷰», «✓ change-flow 완료»)과 서브에이전트 트리가 붙습니다. 접으면 상태 점 줄이 되고, 가장자리를 끌어 폭을 바꿉니다.
- **보기**(오른쪽): 단계 캔버스가 창을 채우고, 그 아래에 고른 단계의 결과와 게이트 근거, 맨 아래에 진행 중인 실행을 모은 «실행 중 N» 카드가 고정돼 있습니다. 경계를 끌어 영역 크기를 바꾸고, 더블클릭하면 원래대로 돌아갑니다.
- **단계별 근거**: 게이트 PASS/FAIL, 테스트 수, 커밋, 되돌림 횟수, 그리고 그 PASS가 나중에 다시 깨졌는지. 일부러 심은 버그로 게이트가 실제로 잡아내는지도 확인합니다.
- **편집**: 팔레트, 고칠 수 있는 캔버스, 단계 편집기. 바꾼 것이 없으면 «닫기», 있으면 «취소»나 «저장»(diff 미리보기 + 확인, 쓰기 전에 자동 백업).
- **실행**: «▶ 실행»은 세션에 보낼 요청을 만들어 미리 보여 주고, 확인을 눌러야 메일박스로 전달합니다. 저절로 나가는 것은 없습니다.
- **가드**: Claude Code에서는 훅이 순서를 건너뛴 단계나 필수 게이트 통과 전의 `git commit`을 막습니다([HOOKS.ko.md](docs/HOOKS.ko.md)).

파이프라인이 아직 없다면 템플릿으로 시작하거나 세션에 초안을 부탁하면 됩니다. 자세히: [사용법](docs/GUIDE.ko.md#파이프라인-실행-지켜보기), [확장하기](docs/EXTENDING.ko.md).

![파이프라인 보기 화면: 왼쪽에 서브에이전트 트리가 붙은 «지금 작업 중» 세션 카드, 오른쪽에 단계 캔버스·고른 단계의 결과 영역·«실행 중 N» 카드](docs/images/pipeline-run-ko.png)

## 구조 분석

에이전트가 그린 모듈 구조도입니다. 연결 하나하나를 특정 커밋의 코드(파일·줄·심볼)와 대조해 확인합니다. 진입점마다 처리 흐름이 하나씩 있고, 미니맵, 코드가 커져 온 과정을 보여 주는 트리맵, 모듈별 보안 검사(비밀값·의존성·SAST)가 함께 있습니다. «개선 요청»은 검사 결과를 세션에 보내고, 수정이 커밋되면 검사를 다시 돌려 달라고 요청합니다. 자세히: [STRUCTURE.ko.md](docs/STRUCTURE.ko.md).

![«Get an order» 흐름이 HTTP 진입점에서 web·order를 거쳐 PostgreSQL까지 밝혀진 아키텍처 구조도, 오른쪽 흐름 목록과 미니맵](docs/images/structure-arch-ko.png)

## 타임라인 (근거)

세션과 서브에이전트가 실제로 언제 무엇을 했는지를 파이프라인 단계와 겹쳐 보여 줍니다. 판정을 확인할 때 엽니다. «변경» 칩은 기준 대비 바뀐 파일 수를 세고(두 세션이 같은 파일을 건드리면 «⚠ 공유»), 누르면 diff가 열립니다.

![서브에이전트 타임라인. 머리 줄에 세션 선택, 기준 배지가 붙은 «변경» 칩, 파이프라인 범례가 있음](docs/images/timeline-ko.png)

## 그 밖의 화면

| 영역 | 보여 주는 것 |
|---|---|
| 주의(왼쪽 레일) | 지금 나를 기다리는 세션. 막힘·질문 세션은 맨 위에 남고, 줄마다 완료·나중에·답장이 있습니다. 점수: `sidereus/attention.py` |
| 상태 표시줄 | 리셋까지 한도가 버티는지. 계정별 5시간·7일 사용량과 리셋 때 남을 예상 여유 |
| 세션 서랍 | 살아 있는 세션과 상태(실행·생각·답 대기·끝남·멈춤) |
| 알림 | 무엇이 끝났고 무엇이 실패했는지. OS 알림은 선택이며 기본으로 꺼져 있습니다 |
| 채팅 | 세션 사이의 메일박스 방과 DM. 직접 글을 쓸 수도 있습니다 |
| 토큰 | 모델·프로젝트·플랫폼별 토큰과 비용, 가장 비싼 서브에이전트 실행 |
| 브랜치 | 커밋마다 어느 세션이 만들었고 비용이 얼마였는지, worktree별 미커밋 수정, 충돌 위험 |
| 이력 · 인사이트 | 날짜별 지난 세션, 최근 30일의 실패와 도구 오류 |

`≈`가 붙은 숫자는 추정치입니다. 공식 할당량 %의 기준인 토큰 상한이 공개되지 않아 Sidereus가 주기마다 역산합니다.

| **브랜치** | **토큰** |
|---|---|
| ![커밋마다 세션 칩이 붙은 커밋 그래프와 충돌 위험·미커밋 수가 보이는 worktree 줄](docs/images/branches-ko.png) | ![프로젝트별 주간 토큰 도넛, 오늘 비율, 비싼 작업 상위와 플랫폼별 표](docs/images/tokens-ko.png) |

## 적용 범위

이런 경우에 맞습니다.
- 터미널에서 여러 CLI 세션을 도구·계정·프로젝트를 넘나들며 돌릴 때(Claude Code가 먼저, Codex·Gemini 등은 어댑터로)
- 대화 내용을 외부 서비스로 보낼 수 없을 때
- 파이프라인에서 품질 게이트를 돌릴 때

이런 경우에는 맞지 않습니다.
- IDE 안에서 에이전트 한두 개만 쓸 때
- Claude Code만 쓰고 기다리는 세션을 먼저 보는 것으로 충분할 때. Claude Code 자체의 agent view로 됩니다
- 클라우드 실행이나 조직 단위 거버넌스가 필요한 팀

개인이 쓰던 도구를 포크해서 쓰도록 공개했습니다. UI는 한국어와 영어를 지원하지만, 기본값은 만든 사람의 작업 방식을 따르고 macOS를 전제한 부분이 남아 있습니다. Anthropic과는 관계가 없으며 승인받은 프로젝트도 아닙니다. 설계와 범위: [CONCEPT.ko.md](docs/CONCEPT.ko.md). 제3자 고지: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## 설치

요구 사항:
- Python 3.9 이상, 표준 라이브러리만 사용. macOS 기본 `/usr/bin/python3`로 됩니다. 새 Mac에서는 처음 실행할 때 Xcode Command Line Tools 설치 창이 뜨는데, 설치한 뒤 다시 실행하면 됩니다.
- Claude Code. 트랜스크립트는 `~/.claude/projects/`에서 읽습니다(`CLAUDE_CONFIG_DIR`가 있으면 `$CLAUDE_CONFIG_DIR/projects/`).
- 브랜치·구조·diff 화면에는 `git`이 필요합니다.
- macOS에서 테스트했습니다. Windows 11은 실제 PC에서 확인했고(2026-10-17), 빠진 기능은 [시작하기](docs/GETTING-STARTED.ko.md#2-뷰어-띄우기)에 있습니다. Linux는 테스트하지 않았습니다.
- 사용량: `--demo` 서버 RSS 약 50–60MB — 시작 직후 화면 몇 번 연 상태 (실측 51MB · 61MB, 세션이 많은 실제 뷰어는 더 씀), 배포 코드 약 11MB, 스크린샷 포함 18MB (macOS, Python 3.9.6, 2026-10-28 측정).

```sh
git clone https://github.com/bugsterran/sidereus.git ~/sidereus && cd ~/sidereus
python3 -m sidereus start --open             # http://127.0.0.1:8799. Windows: sidereus.cmd start --open
```

클론 없이 [pipx](https://pipx.pypa.io)나 [uv](https://docs.astral.sh/uv/)로 설치할 수도 있습니다.

```sh
pipx install git+https://github.com/bugsterran/sidereus    # 또는: uv tool install git+https://github.com/bugsterran/sidereus
sidereus start --demo --open                               # 그 밖에: sidereus start --open · status · doctor · stop
```

업그레이드는 `pipx upgrade sidereus`(`uv tool upgrade sidereus`). 로그인 시 자동 실행(`start --install-service`)과 파이프라인 채점(`scripts/pl_eval.py`)은 클론에서만 됩니다. pipx/uv 설치 경로는 다시 설치할 때마다 바뀌기 때문입니다. 0.7.0 으로 올린 뒤 처음 시작할 때 도구 사용 캐시를 한 번 다시 만듭니다(도구·하네스에 1분쯤 «불러오는 중…»).

Windows에서는 문서의 `python3`를 `py`로 바꿔 쓰거나 클론 폴더에서 `sidereus.cmd`를 실행하세요. Python·Git for Windows·Claude Code를 먼저 설치합니다: [시작하기 0장](docs/GETTING-STARTED.ko.md#0-준비).

8799가 이미 쓰이고 있으면(다른 클론, 또는 같은 Mac의 다른 계정) `status`는 무언가 응답하지만 실행 기록은 없다고만 말합니다. 빈 포트를 고르세요. 포트는 `config.local.json`에 저장되고 MCP 서버도 따라갑니다.

```sh
python3 -m sidereus start --port 8800 --open
```

Claude Code 연결은 플러그인과 수동 훅 중 하나만 고릅니다([5장](docs/GETTING-STARTED.ko.md#5-mcp-와-훅)). 플러그인은 Claude Code 안에서 설치합니다(클론이 있으면 `/plugin marketplace add ~/sidereus`도 됩니다).

```text
/plugin marketplace add bugsterran/sidereus
/plugin install sidereus@sidereus
```

플러그인도 뷰어가 떠 있어야 합니다. 훅과 MCP 도구는 설치 뒤에 시작한 세션에만 걸리므로 Claude Code를 한 번 다시 시작하세요. 확인: `python3 -m sidereus status`에 `200`과 pid가 나오고, 새 세션에서 `sidereus_peers`를 부르면 그 세션이 보여야 합니다. 제거: [시작하기](docs/GETTING-STARTED.ko.md#제거).

설치 전에 알아 둘 것:
- macOS에서는 사용량 조회를 위해 키체인의 Claude Code 토큰을 읽어 `api.anthropic.com`에 보냅니다(`"quota_lookup": false`로 끔). 그 밖에 나가는 요청은 보안 점검이 `api.osv.dev`에 패키지 이름·버전을 묻는 것뿐입니다(오프라인이면 건너뜀). 세션이 일하는 동안 `caffeinate`를 겁니다(`"keep_awake": false`).
- 훅은 이 컴퓨터의 모든 Claude Code 세션에 걸립니다. `.claude/pipelines/*.json`이 있는 프로젝트에서는 순서를 건너뛴 단계나 이른 `git commit`을 막을 수 있습니다([MCP와 훅](#에이전트에서-쓰기-mcp)).
- 여러 계정이 함께 쓰는 Mac에서는 다른 계정도 이 뷰어의 API를 부를 수 있습니다. 루프백 말고는 인증이 없습니다([SECURITY.ko.md](SECURITY.ko.md#모델)).
- 키체인·네트워크·AppleScript·파일 접근과, 기본으로 꺼진 유료 할당량 탐침: [SECURITY.ko.md](SECURITY.ko.md), [CONFIG.ko.md](docs/CONFIG.ko.md).

## 개인정보

다른 세션의 대화 내용은 화면에 나오지 않습니다. 목록·타임라인·카드·MCP 서버에는 메타데이터만 들어갑니다. 경로, 세션 id, 모델, 상태, 개수, 에이전트의 한 줄 작업 설명이 전부이며, 이 규칙은 코드로 강제합니다.

예외는 작업 내역 하나입니다. 세션이나 에이전트를 클릭하면 그 트랜스크립트의 끝부분을 읽어 최근 지시, 답변, 도구 사용 흔적, 파일 diff를 보여 줍니다. 클릭했을 때만, 그리고 이 기기에서 도는 세션의 저장소일 때만 열립니다(diff와 같은 허용 목록).

Sidereus는 지시를 전달할 뿐 세션을 조작하지 않습니다. 지시는 메일박스로 가고, 보낸 내용은 그대로 남습니다.

## 에이전트에서 쓰기 (MCP)

플러그인을 설치했다면 이미 등록돼 있습니다(Windows는 먼저 `setx SIDEREUS_PYTHON py`, [5장](docs/GETTING-STARTED.ko.md#5-mcp-와-훅) 참고). 직접 등록하려면 macOS에서 클론 폴더에서 실행합니다(Windows는 `py -m sidereus setup-claude`가 출력하는 명령을 쓰세요).

```sh
claude mcp add --scope user sidereus -- /usr/bin/python3 "$PWD/mcp/sidereus_mcp.py"
```

| 도구 | 반환값 |
|---|---|
| `sidereus_quota` | 5시간·7일 사용 %, 남은 토큰, 리셋 시각, 목표 대비 속도, 권고 한 줄 |
| `sidereus_file_peers(path)` | 최근 30분 안에 이 파일을 수정한 다른 세션, 살아 있는지 여부, 커밋하지 않은 수정 여부 |
| `sidereus_peers()` | 같은 저장소(worktree 무관)의 살아 있는 세션·서브에이전트와 상태·도구·컨텍스트 % |
| `sidereus_attention()` | 사용자를 기다리는 세션 |

뷰어가 떠 있어야 하고, `claude mcp add` 뒤에 시작한 세션에서만 도구가 보입니다. 에이전트는 시키지 않으면 잘 부르지 않으니 `AGENTS.md`나 `CLAUDE.md`에 규칙을 적어 두세요. 자세히: [MCP.ko.md](docs/MCP.ko.md).

Sidereus는 세션을 시작하거나 멈추지 않습니다. 파이프라인 훅(`pl_mark`, `pl_flow`, `pl_guard`)은 `.claude/pipelines/*.json`이 있는 프로젝트에서만 호출을 거부합니다. 대상은 태그 없는 Agent 호출, `[pl:<이름>/<단계>]` 실행에서 순서를 건너뛴 단계, 그 실행의 `guards` 게이트를 통과하기 전의 `git commit`입니다. 프로젝트별로 «적용»에서 끕니다. 자세히: [HOOKS.ko.md](docs/HOOKS.ko.md).

서버는 트랜스크립트, git, OpenTelemetry 로그를 백그라운드 스레드와 증분 캐시로 읽고 `127.0.0.1:8799`에서 화면과 MCP 서버를 제공합니다. Claude 토큰은 쓰지 않고, MCP 호출 한 번은 호출한 세션의 컨텍스트에 몇 줄을 더합니다([ARCHITECTURE.ko.md](docs/ARCHITECTURE.ko.md)).

## 문서

| 문서 | 내용 |
|---|---|
| [시작하기](docs/GETTING-STARTED.ko.md) | 단계별 설치와 설정 |
| [사용법](docs/GUIDE.ko.md) | 자주 하는 작업, 스크린샷 포함 |
| [설정](docs/CONFIG.ko.md) | 경로, 설정 키, 환경 변수, launchd, 백업 |
| [훅](docs/HOOKS.ko.md) | 훅, Codex·Gemini CLI 연결, 메일박스 Stop 훅 |
| [MCP](docs/MCP.ko.md) | `sidereus` MCP 서버 |
| [병렬 작업](docs/PARALLEL-WORK.ko.md) | 병렬 worktree (`claude -w <이름> --tmux`) |
| [구조](docs/STRUCTURE.ko.md) | 구조 탭: 아키텍처 구조도와 흐름, 크기 트리맵, 지원 언어 |
| [아키텍처](docs/ARCHITECTURE.ko.md) | 서버·화면·훅·메일박스의 연결 구조 |
| [확장하기](docs/EXTENDING.ko.md) | CLI 플랫폼·언어 플러그인·파이프라인 추가 |
| [리뷰 파이프라인](docs/REVIEW-PIPELINES.ko.md) | 플랫폼 공개 자료에 기반한 CLI별 리뷰 파이프라인과 템플릿 |
| [sidereus-state.v1.json](docs/schema/sidereus-state.v1.json) | `GET /api/v1/state`의 안정 메타데이터 스키마 |

## 설정 바꾸기

설정(톱니바퀴)에서 언어, 배경 톤, «환경설정»을 바꿉니다. 서버 쪽 값은 `config.local.json`에 저장되고 재시작해야 적용됩니다. `/usr/bin/python3 mailbox_config.py`(Windows: `py mailbox_config.py`)는 설정 파일 경로와 병합된 결과를 보여 줍니다. 전체 키와 설정 API: [CONFIG.ko.md](docs/CONFIG.ko.md).

## 다른 CLI

Codex CLI와 Gemini CLI는 훅으로 상태를 보내 Claude Code 세션 옆에 함께 나오고, 토큰도 따로 집계됩니다. ⚠ 이 토큰은 Claude의 5시간·7일 한도나 비용에 절대 합산하지 않습니다. Cursor CLI: macOS 확인(2026.10.22). Cursor IDE는 아직 지원하지 않습니다(#9). Copilot 등 다른 CLI도 같은 훅을 쓸 수 있지만 아직 확인하지 않았습니다. 설정: [HOOKS.ko.md](docs/HOOKS.ko.md).

⚠ Codex는 TUI에서 `/hooks`로 한 번 승인하기 전까지 `hooks.json`을 무시하며, 파일을 고칠 때마다 다시 승인해야 합니다(항목 이름은 «Sidereus»가 아니라 `ext_hook.py`로 보입니다). 승인 전에는 최근 10분 안에 기록이 있는 Codex 세션이 «훅 미연결» 표시와 함께 폴더와 모델만 보이고 상태는 나오지 않습니다.

macOS에서 확인된 것: Codex CLI 0.163.0 — 세션 목록·상태, 턴 끝 메일 전달, 파이프라인 단계 표시, «터미널» 버튼. Gemini CLI 0.61.0 — 턴 끝 메일 전달, 단계 표시. 다른 CLI는 확인하지 않았습니다. Gemini 한도는 Google 서버에만 있어서 Sidereus는 토큰 수만 보여 주고 한도 막대는 없습니다. 남은 양은 Gemini CLI의 `/stats`에서 확인하세요.

## 프로젝트 운영 방식

- 있는 그대로 공개합니다. 핵심 기능을 바꾸려면 포크해 주세요.
- 버그 리포트는 환영합니다. PR은 확장 기능(언어 플러그인, CLI 어댑터, 파이프라인 템플릿)만 받습니다: [CONTRIBUTING.ko.md](CONTRIBUTING.ko.md).
- 보안 모델과 비공개 신고: [SECURITY.ko.md](SECURITY.ko.md). 변경 기록: [CHANGELOG.md](CHANGELOG.md). 다음 출시: [Milestones](https://github.com/bugsterran/sidereus/milestones).

[ccusage](https://github.com/ryoppippi/ccusage)(5시간 블록 규칙, `message.id` + `requestId` 중복 제거 키), Grafana, Datadog, Paseo, Orca, SourceTree, Conductor, Codex, Vibe Kanban에서 아이디어를 얻었습니다. 코드는 직접 작성했습니다.

## 라이선스

MIT 라이선스입니다. [LICENSE](LICENSE)를 참고하세요.
