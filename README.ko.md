# Sidereus

[English](README.md) · **한국어**

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.9, stdlib only](https://img.shields.io/badge/python-3.9%20stdlib%20only-3776AB.svg)
![Platform: macOS · Windows](https://img.shields.io/badge/platform-macOS%20%C2%B7%20Windows-lightgrey.svg)

Sidereus는 AI 코딩 세션이 한 일을 확인하는 로컬 뷰어입니다. 터미널에서 돌고 있는 Claude Code, Codex CLI, Gemini CLI 세션 옆에서 돌면서, 어떤 세션이 내 답을 기다리는지, 각 실행이 파이프라인을 따랐는지, 결과의 근거가 무엇인지를 한 화면에 보여 줍니다. 저장소의 모듈·흐름 지도를 그리고 보안 점검도 돌립니다. 에이전트를 직접 실행하거나 터미널에 입력하지는 않습니다.

저는 보통 Claude Code·Codex 세션 여러 개를 터미널과 프로젝트를 나눠 띄워 둡니다. 어느 세션이 제 답을 기다리는지 자꾸 놓쳤고, 세션이 "테스트 통과"라고 해도 정말 돌렸는지 바로 확인할 방법이 없었습니다. 그래서 만들었습니다.

![애니메이션: change-flow 실행의 단계에 차례로 불이 들어옴. 설계, 구현, 검증, 리뷰에서 한 번 되돌린 뒤 구현·검증을 다시 거쳐 리뷰 완료](docs/images/hero-ko.gif)

## 데모로 둘러보기

데모는 합성 데이터만 쓰고, 내 컴퓨터의 데이터는 읽지 않습니다.

```sh
git clone https://github.com/bugsterran/sidereus.git ~/sidereus && cd ~/sidereus
python3 -m sidereus start --demo --open      # 18799 포트, Ctrl-C로 끕니다. Windows: py -m sidereus
```

## 파이프라인

뷰어를 열면 이 탭이 먼저 나옵니다. 파이프라인은 `.claude/pipelines/*.json`에 한 번 정해 두는 단계 순서로, 단계마다 에이전트와 모델, 게이트, 되돌림을 적습니다. 세션이 작업에 `[pl:<파이프라인>/<단계>]` 태그를 붙이면 그 단계에 불이 들어옵니다.

왼쪽 **지금 작업 중**에는 살아 있는 세션이 카드로 하나씩 나오고, 실행 요약과 서브에이전트 트리가 붙습니다. 오른쪽 단계 캔버스에서 단계를 누르면 결과와 게이트 근거가 나옵니다. PASS/FAIL, 테스트 수, 커밋, 되돌림 횟수, 그리고 그 PASS가 나중에 다시 깨졌는지까지 보여 줍니다. 일부러 심은 버그로 게이트가 정말 잡아내는지도 확인합니다.

파이프라인은 캔버스에서 바로 고칠 수 있고, 저장할 때 diff를 보여 주고 먼저 백업합니다. **실행**은 세션에 보낼 요청을 만들어 보여 주고, 확인을 눌러야 메일박스로 보냅니다. Claude Code에서는 훅이 순서를 건너뛴 단계와 필수 게이트를 통과하기 전의 `git commit`을 막습니다([HOOKS.ko.md](docs/HOOKS.ko.md)).

파이프라인이 아직 없다면 템플릿으로 시작하거나 세션에 초안을 부탁하면 됩니다. [사용법](docs/GUIDE.ko.md#파이프라인-실행-지켜보기)과 [확장하기](docs/EXTENDING.ko.md)를 참고하세요.

![파이프라인 보기 화면: 왼쪽에 서브에이전트 트리가 붙은 지금 작업 중 세션 카드, 오른쪽에 단계 캔버스·고른 단계의 결과 영역·실행 중 N 카드](docs/images/pipeline-run-ko.png)

## 구조

모듈 구조도는 에이전트가 그리고, 연결 하나하나를 특정 커밋의 코드(파일·줄·심볼)와 대조해 확인합니다. 진입점마다 처리 흐름이 따로 있고, 미니맵, 코드가 커 온 과정을 보여 주는 트리맵, 모듈별 보안 검사(비밀값·의존성·SAST)도 함께 있습니다. **개선 요청**을 누르면 검사 결과를 세션에 보내고, 수정을 커밋한 뒤 검사를 다시 돌려 달라고 요청합니다. 자세한 내용은 [STRUCTURE.ko.md](docs/STRUCTURE.ko.md)에 있습니다.

![Get an order 흐름이 HTTP 진입점에서 web·order를 거쳐 PostgreSQL까지 밝혀진 아키텍처 구조도, 오른쪽 흐름 목록과 미니맵](docs/images/structure-arch-ko.png)

## 타임라인

세션과 서브에이전트가 언제 무엇을 했는지를 파이프라인 단계와 겹쳐 보여 줍니다. 결과를 직접 확인하고 싶을 때 엽니다. **변경** 칩은 기준 시점 이후 바뀐 파일 수를 세고, 두 세션이 함께 건드린 파일을 표시하며, 누르면 diff가 열립니다.

![서브에이전트 타임라인. 머리 줄에 세션 선택, 기준 배지가 붙은 변경 칩, 파이프라인 범례가 있음](docs/images/timeline-ko.png)

## 그 밖의 기능

- **주의** 레일: 막혔거나 질문 중인 세션이 맨 위에 남고, 줄마다 완료·나중에·답장 버튼이 있습니다.
- 상태 표시줄: 계정별 5시간·7일 사용량과 리셋 때 남을 예상 여유. `≈`가 붙은 숫자는 추정치입니다([사용법](docs/GUIDE.ko.md)).
- 세션 서랍, 알림, 채팅(세션 사이의 메일박스 방과 DM, 직접 글을 쓸 수도 있음).
- **토큰**: 모델·프로젝트·플랫폼별 사용량과 비용, 가장 비싼 서브에이전트 실행.
- **브랜치**: 커밋마다 어느 세션이 만들었고 비용이 얼마였는지, worktree별 미커밋 수정, 충돌 위험.
- **이력**과 **인사이트**: 날짜별 지난 세션, 최근 30일의 실패와 도구 오류.

| **브랜치** | **토큰** |
|---|---|
| ![커밋마다 세션 칩이 붙은 커밋 그래프와 충돌 위험·미커밋 수가 보이는 worktree 줄](docs/images/branches-ko.png) | ![프로젝트별 주간 토큰 도넛, 오늘 비율, 비싼 작업 상위와 플랫폼별 표](docs/images/tokens-ko.png) |

## 누구에게 맞나

터미널에서 여러 CLI 에이전트 세션을 도구·계정·프로젝트를 넘나들며 돌리고, 대화 내용을 외부 서비스로 보낼 수 없고, 파이프라인에서 품질 게이트를 돌리는 사람을 위해 만들었습니다. Claude Code를 가장 먼저 지원합니다. Codex, Gemini, Cursor CLI, Copilot CLI는 훅으로 연결하며([HOOKS.ko.md](docs/HOOKS.ko.md)), 이들의 토큰은 Claude 한도와 따로 셉니다. Gemini 요금제 한도는 Google 서버에만 있으니 `/stats`로 확인하세요. Cursor IDE는 아직 지원하지 않고(#9), 다른 CLI는 확인하지 않았습니다.

IDE 안에서 에이전트 한두 개만 쓰거나, Claude Code만 쓰면서 기다리는 세션만 먼저 보면 되거나(Claude Code의 agent view로 됩니다), 클라우드 실행이나 조직 단위 거버넌스가 필요한 팀이라면 맞지 않을 가능성이 큽니다.

개인이 쓰던 도구를 포크해서 쓰라고 공개했습니다. UI는 한국어와 영어를 지원하지만 기본값은 만든 사람의 작업 방식을 따르고, macOS를 전제한 부분도 남아 있습니다. Anthropic과는 관계가 없으며 승인받은 프로젝트도 아닙니다. 설계와 범위는 [CONCEPT.ko.md](docs/CONCEPT.ko.md), 제3자 고지는 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)에 있습니다.

## 설치

Python 3.9 이상(표준 라이브러리만 사용), Claude Code, 그리고 브랜치·구조·diff 화면용 `git`이 필요합니다. macOS 기본 `/usr/bin/python3`로 됩니다. 새 Mac에서는 처음 실행할 때 Xcode Command Line Tools 설치 창이 뜨니, 설치하고 다시 실행하면 됩니다. macOS에서 테스트했고, Windows는 일부 빠진 기능이 있지만 동작하며, Linux는 테스트하지 않았습니다. 데모 서버는 메모리를 50MB 정도 씁니다.

```sh
git clone https://github.com/bugsterran/sidereus.git ~/sidereus && cd ~/sidereus
python3 -m sidereus start --open             # http://127.0.0.1:8799. Windows: sidereus.cmd start --open
```

클론 없이 [pipx](https://pipx.pypa.io)나 [uv](https://docs.astral.sh/uv/)로 설치해도 됩니다. 클론이 있어야 되는 기능이 몇 가지 있는데, 목록은 시작하기 문서에 있습니다.

```sh
pipx install git+https://github.com/bugsterran/sidereus    # 또는: uv tool install git+https://github.com/bugsterran/sidereus
sidereus start --open                                      # 그 밖에: status · doctor · stop
```

Claude Code와 연결하려면 Claude Code 안에서 플러그인을 설치하고, Claude Code를 한 번 다시 시작하세요.

```text
/plugin marketplace add bugsterran/sidereus
/plugin install sidereus@sidereus
```

나머지는 [시작하기](docs/GETTING-STARTED.ko.md)에 있습니다. Windows 준비, 포트 바꾸기, 플러그인 대신 수동 훅 쓰기, 로그인 시 자동 실행, 업그레이드와 제거까지 다룹니다. 설치 전에 Sidereus가 무엇을 읽고 보내는지(할당량 조회용 키체인 토큰, 취약점 정보 조회, Mac 잠자기 막기), 여러 계정이 쓰는 Mac에서 다른 계정도 API에 닿는 이유, 각각 끄는 방법을 [SECURITY.ko.md](SECURITY.ko.md)와 [CONFIG.ko.md](docs/CONFIG.ko.md)에서 확인하세요.

## 개인정보

다른 세션의 대화 내용은 화면에 나오지 않습니다. 목록·타임라인·카드·MCP 서버에는 메타데이터만 들어갑니다. 경로, 세션 id, 모델, 상태, 개수, 에이전트의 한 줄 작업 설명이 전부이고, 이 규칙은 코드로 강제합니다.

예외는 작업 내역 하나입니다. 세션이나 에이전트를 클릭하면 그 트랜스크립트의 끝부분을 읽어 최근 지시, 답변, 도구 호출, 파일 diff를 보여 줍니다. 클릭했을 때만, 그리고 이 기기에서 도는 세션의 저장소일 때만 엽니다.

Sidereus는 세션을 시작하거나 멈추거나 세션에 입력하지 않습니다. 내가 보낸 지시는 메일박스로 가고, 보낸 내용은 거기 남습니다.

## 에이전트용 MCP 도구

플러그인이 함께 등록합니다. 직접 등록하는 방법은 [MCP.ko.md](docs/MCP.ko.md)에 있습니다.

| 도구 | 반환값 |
|---|---|
| `sidereus_quota` | 5시간·7일 사용 %, 남은 토큰, 리셋 시각, 속도, 권고 한 줄 |
| `sidereus_file_peers(path)` | 최근 30분 안에 이 파일을 고친 다른 세션과 커밋하지 않은 수정이 있는지 |
| `sidereus_peers()` | 같은 저장소의 살아 있는 세션·서브에이전트와 상태, 컨텍스트 % |
| `sidereus_attention()` | 사용자를 기다리는 세션 |

에이전트는 시키지 않으면 잘 부르지 않으니 `AGENTS.md`나 `CLAUDE.md`에 한 줄 적어 두세요. 서버 자체는 Claude 토큰을 쓰지 않고, MCP 호출 한 번이 호출한 세션의 컨텍스트에 몇 줄을 더합니다.

## 문서

| 문서 | 내용 |
|---|---|
| [시작하기](docs/GETTING-STARTED.ko.md) | 단계별 설치와 설정 |
| [사용법](docs/GUIDE.ko.md) | 자주 하는 작업, 스크린샷 포함 |
| [설정](docs/CONFIG.ko.md) | 경로, 설정 키, 환경 변수, launchd, 백업 |
| [훅](docs/HOOKS.ko.md) | 훅, Codex·Gemini·Cursor CLI·Copilot CLI 연결, 메일박스 Stop 훅 |
| [MCP](docs/MCP.ko.md) | `sidereus` MCP 서버 |
| [병렬 작업](docs/PARALLEL-WORK.ko.md) | 병렬 worktree (`claude -w <이름> --tmux`) |
| [구조](docs/STRUCTURE.ko.md) | 구조 탭: 아키텍처 구조도와 흐름, 크기 트리맵, 지원 언어 |
| [아키텍처](docs/ARCHITECTURE.ko.md) | 서버·화면·훅·메일박스의 연결 구조 |
| [확장하기](docs/EXTENDING.ko.md) | CLI 플랫폼·언어 플러그인·파이프라인 추가 |
| [리뷰 파이프라인](docs/REVIEW-PIPELINES.ko.md) | CLI별 리뷰 파이프라인과 템플릿 |
| [sidereus-state.v1.json](docs/schema/sidereus-state.v1.json) | `GET /api/v1/state`의 안정 메타데이터 스키마 |

설정(톱니바퀴)에서 언어, 배경 톤, **환경설정**을 바꿉니다. 서버 쪽 값은 `config.local.json`에 저장되고 재시작하면 적용됩니다. 전체 키는 [CONFIG.ko.md](docs/CONFIG.ko.md)에 있습니다.

## 기여

있는 그대로 공개한 프로젝트라, 핵심 기능을 바꾸려면 포크해 주세요. 버그 리포트는 환영합니다. PR은 언어 플러그인, CLI 어댑터, 파이프라인 템플릿 같은 확장 기능만 받습니다. [CONTRIBUTING.ko.md](CONTRIBUTING.ko.md), 비공개 보안 신고는 [SECURITY.ko.md](SECURITY.ko.md), 변경 기록은 [CHANGELOG.md](CHANGELOG.md), 다음 출시는 [마일스톤](https://github.com/bugsterran/sidereus/milestones)을 보세요.

## 어떻게 만들었나

코드와 문서는 대부분 Claude Code 세션이 썼습니다. 저는 방향을 정하고, 결과를 검토하고, 무엇을 낼지 정했습니다. 그 세션들은 Sidereus로 지켜봤습니다.

## 감사의 말

5시간 블록 규칙과 `message.id` + `requestId` 중복 제거 키는 [ccusage](https://github.com/ryoppippi/ccusage)에서 가져왔습니다. 그 밖에 Grafana, Datadog, Paseo, Orca, SourceTree, Conductor, Codex, Vibe Kanban에서 아이디어를 얻었습니다. 코드는 이 프로젝트를 위해 직접 작성했습니다.

## 라이선스

MIT 라이선스입니다. [LICENSE](LICENSE)를 참고하세요.
