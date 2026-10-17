# 보안

[English](SECURITY.md) · **한국어**

시데레우스는 로컬 관제 화면이면서 제어를 전달하는 역할을 한다. 하는 일 전부와, 각각을 끄는 방법을 적는다.

## 모델

- **로컬 전용.** 서버는 `127.0.0.1` 에 바인드한다(하드코딩). 다른 인터페이스에서는 받지 않고, CORS 헤더는 보내지 않는다.
- **모든 요청에 Host 검사.** `127.0.0.1:<port>` 와 `localhost:<port>` 만 받는다 — DNS 리바인딩 방어.
- **POST 에 Origin 검사.** 다른 출처에서 브라우저가 보낸 POST 는 403 이다. `Origin` 이 없는 요청(OTel 내보내기, curl, 로컬 훅)은 통과한다. 브라우저는 교차 출처 POST 에 `Origin` 을 반드시 붙이기 때문이다.
- **교차 사이트 GET 도 거부.** `Sec-Fetch-Site: cross-site` 가 붙은 `/api/*` GET 은 403 이다(교차 사이트 페이지가 `<img>` 등으로 부작용 있는/비싼 호출을 걸 수 있어서다). 같은 사이트 요청과 헤더 없는 요청(curl, 훅, MCP)은 통과한다.
- **루프백 말고는 인증이 없다.** 같은 기계의 로컬 프로세스나 다른 OS 사용자는 API 를 부를 수 있다. 브라우저는 Host·Origin·`Sec-Fetch-Site` 검사로 막고, 페이지는 다른 페이지 안에 넣을 수 없다(`frame-ancestors 'none'`, `X-Frame-Options: DENY`).
- **macOS 에서 작업 내역 팝업 엔드포인트는 같은 사용자만.** `/api/session/work`, `/api/agent/work`, `/api/ext/work` 는 대화 기록 끝부분을 돌려주므로, 루프백 연결의 클라이언트 쪽 소켓을 뷰어와 같은 OS 사용자의 프로세스가 쥐고 있지 않으면 403 이다(`/usr/sbin/lsof` 로 확인; `lsof` 가 없거나 느려도 403).
  ⚠ 다른 OS 에서는 이 엔드포인트를 여전히 로컬 프로세스 누구나(다른 사용자의 `curl` 포함) 읽을 수 있다. 모든 OS 에서 나머지 `/api` 는 인증이 없고, `/work` HTML 껍데기는 로컬 누구에게나 나간다.
- **프로세스를 띄우는 엔드포인트 없음.** 페이지의 어떤 요청도 셸·git checkout/merge·세션을 돌리지 않는다.
- **메일박스 DM 은 등록된 id 에만**(`identity.json`) 보낸다. 추측한 이름으로는 보내지 않는다.
- 밖으로 나가는 요청은 선택 사항인 `api.anthropic.com` 할당량 조회 하나뿐이고, macOS 키체인의 OAuth 토큰을 쓴다.
- **뷰어가 아닌 개발 스크립트:** `scripts/arch_checks.py --category security` 와 `scripts/deps_audit.py` 는 실행할 때 무료 취약점 소스(OSV.dev·npm·semgrep 레지스트리·endoflife.date)를 조회한다 — 패키지 이름과 버전만 보낸다. `--offline` 이면 건너뛰고, 네트워크가 안 닿으면 «문제 없음» 이 아니라 건너뜀으로 적는다.
- **유료 할당량 프로브 — 기본 꺼짐.** `quota_probe: true`(또는 `SIDEREUS_QUOTA_PROBE=1`)면, 조회가 429 를 받는 동안 같은 토큰으로 120초마다 `api.anthropic.com/v1/messages` 에 Haiku 요청 1회를 보낸다(`max_tokens 1`, 회당 약 $0.00002, 그 계정에 청구). 레이트 리밋 헤더만 읽고 본문은 버린다.

## 하지 않는 것

- **텔레메트리가 없다.** 사용자나 세션에 관한 정보가 이 컴퓨터를 떠나지 않는다(예외는 위 할당량 조회 하나).
- **대화 내용을 페이지나 MCP 도구에 올리지 않는다.** 경로, 세션 id, 모델, 에이전트의 한 줄 작업 설명 같은 메타데이터만 쓴다. 유일한 예외는 클릭해야 열리는 작업 내역 팝업이다. 유출 검사와 테스트가 이 규칙을 지킨다.
- **git 에 쓰지 않는다.** 모든 git 호출이 `git_argv` 를 거치고, `core.fsmonitor=false`, `core.hooksPath=/dev/null` 을 붙인다.
- **CLI 를 직접 조작하지 않는다.** pty, stdin 주입, send-keys, 세션 실행이나 종료가 없다. 지시는 메일박스로만 가고, 사람이 미리보기를 보고 확인한 것만 간다.

## 보안 검토에서 물어볼 만한 동작

| # | 동작 | 위치 | 이유 | 끄기 |
|---|---|---|---|---|
| 1 | macOS 키체인에서 Claude Code OAuth 토큰을 읽어(`security find-generic-password`) `api.anthropic.com/api/oauth/usage` 에 Bearer 헤더로 보낸다. 토큰은 기록하지도, 저장하지도, 화면에 보이지도 않는다. 로그인된 추가 설정 폴더(계정 여러 개)도 같은 방식으로 조회한다: 폴더마다 자기 키체인 서비스(`Claude Code-credentials-<폴더 sha256>[:8]`, `-w` 로 읽기 전에 종료 코드로 존재만 확인), 없으면 `<폴더>/.credentials.json`. | `sidereus/quota.py`, `sidereus/quota_fetch.py`, `sidereus/quota_roots.py` | 5h/7d 한도 카드, «다른 계정» 줄, 절약 모드 페이스 | `"quota_lookup": false` 또는 `SIDEREUS_QUOTA_LOOKUP=0` (한도 카드가 빈다) |
| 2 | 유료 프로브: 사용량 API 가 429 를 주는 동안 120초마다 Haiku 호출 1회(`max_tokens 1`)로 응답 헤더의 크레딧 비율을 읽는다. | `sidereus/quota.py` | 크레딧 줄 | 기본으로 꺼져 있다(`quota_probe`) |
| 3 | 고정된 AppleScript(tty 를 인자로 넘김)로 iTerm2 나 터미널 탭을 앞으로 가져온다. 탭에 입력하지는 않는다. | `sidereus/term.py` | «터미널로» 버튼 | 설정 > 터미널 > `off` |
| 4 | 세션이 일하는 동안 `caffeinate` 를 잡아 맥이 유휴 절전에 들어가지 않게 한다. | `sidereus/awake.py` | 맥이 잠들면 세션도 멈춘다 | `"keep_awake": false` |
| 5 | Claude Code 설정을 쓴다: 프로젝트 `.claude/pipelines/*.json`(단계의 에이전트·모델만)과 `~/.claude/settings.json` 의 두 키(`autoCompactEnabled`, `autoCompactWindow`). 쓸 때마다 diff 미리보기를 보여 주고 확인을 받는다. 쓰기 전에 원래 파일을 백업하고, 뷰어 Origin 이 필요하다. 허용 목록 밖 경로는 거부한다. 스킬, 에이전트, 커맨드, MCP 서버, 훅은 읽기 전용으로 보여 주기만 한다(MCP `env` 값은 가린다). | `sidereus/pipeline.py`, `sidereus/cc_settings.py` | 뷰어에서 파이프라인·자동 압축 편집 | 그 편집기를 쓰지 않으면 아무것도 쓰지 않는다 |
| 6 | `~/.claude/projects/` 아래 대화 기록을 로컬에서 읽어 메타데이터를 뽑는다. | `sidereus/sessions.py` 외 | 관제 자체 | 이 기능이 제품의 본체다 |
| 7 | 읽기 전용 시스템 명령: `ps`, `lsof`, `sysctl`, `pmset`, `git`, `ccusage`(선택). | `sidereus/live*.py`, `sidereus/gitinfo.py`, `sidereus/burn_usage.py` | 실시간 세션 감지, 잠든 구간, git 화면, 일별 합계 | — |

설정은 `config.local.json` 에 넣는다([docs/CONFIG.ko.md](docs/CONFIG.ko.md)). 넣은 뒤 뷰어를 재시작한다.

## 보안 도구

`scripts/arch_checks.py --category security` 는 설치된 스캐너를 쓴다. 설정 > 진단 > «보안 도구» 는 `PATH` 에서 찾은 도구와 설치 파일에서 읽은 버전을 보여 준다. Sidereus 는 이 도구들을 실행하거나 설치하지 않는다. «복사» 는 명령을 클립보드에 넣기만 한다.

| 도구 | 잡는 것 | 설치 (macOS · Windows) | 네트워크 필요? |
|---|---|---|---|
| `gitleaks` | 저장소에 커밋된 비밀값 (API 키·토큰·비밀번호) | `brew install gitleaks` · `winget install Gitleaks.Gitleaks` | 아니오 |
| `semgrep` | 여러 언어의 위험한 코드 패턴 (인젝션·안전하지 않은 호출 등) | `brew install semgrep` · `pip install semgrep` | 레지스트리 규칙만 (로컬 `.semgrep.yml` 이 없을 때) |
| `bandit` | Python 코드의 흔한 보안 문제 | `brew install bandit` · `pip install bandit` | 아니오 |
| `osv-scanner` | 락파일로 읽은 의존성의 알려진 취약점 | `brew install osv-scanner` · `winget install Google.OSVScanner` | 예 |
| `npm` | npm 패키지의 알려진 취약점 (npm audit) | `brew install node` · `winget install OpenJS.NodeJS.LTS` | 예 |

## 문제 알리기

공개 이슈가 아니라 GitHub 의 비공개 취약점 신고(저장소 Security 탭 → «Report a vulnerability»)로 알려 주기 바란다. 실행한 것, 본 것, 시험한 커밋을 적는다.
[Anthropic OSS Scanner](https://github.com/anthropics/oss-scanner) 용 위협 모델과 스캐너 이미지는 [`.oss-scanner/`](.oss-scanner/) 에 있다.
답이나 수정을 약속하지 않는다. 이 프로젝트는 있는 그대로 공유하며, PR 은 확장만 받는다([README](README.ko.md#프로젝트-운영-방식)).
