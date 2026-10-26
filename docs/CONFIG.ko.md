# 설정

[English](CONFIG.md) · **한국어**

## 파일과 우선순위

| | 위치 | 내용 |
|---|---|---|
| 데이터 | `$MAILBOX_DIR`, 기본 `~/.mailbox-mcp` | 버스, 커서, presence, 캐시, 로그, `config.local.json`, `backup/` |
| 코드 | 스크립트가 있는 폴더 | `chat_server.py`, `mailbox_*.py`, 셸 스크립트, `hooks/`, `ext-hooks/` |

데이터와 코드는 같은 폴더여도 된다. 설정 파일은 `$MAILBOX_CONFIG`, 없으면 `$MAILBOX_DIR/config.local.json`, 그것도 없으면 내장 기본값이다.
값마다 환경 변수 > 설정 파일 > 기본값 순으로 정한다.

```sh
/usr/bin/python3 mailbox_config.py                 # config path + merged settings (JSON)
/usr/bin/python3 mailbox_config.py --get KEY       # one value; lists/objects print as JSON
/usr/bin/python3 mailbox_config.py --port          # resolved viewer port
/usr/bin/python3 mailbox_config.py --label NAME    # launchd label for job NAME
```

Windows 에서는 `py mailbox_config.py ...` 로 실행한다. 데이터 폴더 기본값은 `%USERPROFILE%\.mailbox-mcp` 다.

설정 파일이 없거나 읽을 수 없으면 경고 한 줄을 내고 기본값으로 돈다.

## 키 (`config.local.json`)

`config.example.json` 을 복사해서 쓴다. `_` 로 시작하는 키는 주석이다. 모르는 키나 타입이 틀린 값은 경고 한 번 내고 무시한다.

| 키 | 타입 | 기본값 | 효과 |
|---|---|---|---|
| `self.ids` | 문자열 목록 | `[]` | 이 설치가 글을 쓰는 id. 첫 번째가 모니터 신원이다. |
| `self.aliases` | 문자열 목록 | `[]` | 나에게 온 메일로 치는 주소. 비우면 `self.ids`. |
| `alias_strip_prefixes` | 문자열 목록 | `[]` | `MAILBOX_ME=<접두어>x` 일 때 `x` 로 온 메일도 받는다. |
| `default_room` | 문자열 | `"general"` | 뷰어가 열고 글을 쓰는 방. 1~64자, `/ \` 불가. |
| `viewer_me` | 문자열 | `"사용자"` | 뷰어에서 쓴 글의 이름. 1~64자. 비워 두거나 `"사용자"`/`"user"` 면 화면 언어를 따른다(한국어 `사용자`, 영어 `user`). 두 이름으로 쓴 글 모두 내 글로 본다. |
| `readcheck_peer` | 문자열 | `""` | 인자 없이 `readcheck.py` 를 돌릴 때의 상대. |
| `saver_view_path` | 문자열 | `"~/.claude/hooks/.saver-view.json"` | 외부 절약 훅(동봉 안 함)이 쓰는 스냅숏. 파일이 없으면 절약 칩과 조언 줄이 안 뜰 뿐이다. 선택 키 `levels`(`[{lv, cap, rules}]`)·`how`(문자열 목록)가 있으면 설정 › «절약 모드» › «수준별 동작» 을 채운다. 없거나 형식이 틀리면 접기 자체를 숨긴다. |
| `saver_hook_dir` | 문자열 | `"~/.claude/hooks"` | 절약 훅의 `.saver-force.json`·목표 파일 폴더. 절대 경로나 `~`, `..` 불가. |
| `hook_session_patterns` | 문자열 목록 | `[]` | 훅이 띄운 세션의 작업 폴더 정규식. 맞으면 숨긴다. |
| `launchd_label_prefix` | 문자열 | `"io.sidereus"` | `--label viewer` 가 `<접두어>.viewer` 를 낸다. `ext-hooks/demo.sh` 와 MCP 의 다운 안내가 쓴다. 동봉 plist 는 이 값을 읽지 않는다. |
| `launchd_labels` | 객체 | `{"viewer": "", "watch": "", "databackup": ""}` | 작업별 전체 라벨. 비어 있지 않으면 `<접두어>.<이름>` 대신 쓴다. |
| `quota_probe` | bool | `false` | 할당량 조회가 429 인 동안 120초마다 유료 Haiku 호출 1회(`max_tokens 1`, 약 $0.00002, 한 달 내내 429 여도 ~$0.02)로 응답 헤더의 크레딧 비율을 읽는다. ⚠ Claude Code 로그인 토큰으로 Claude Code 밖에서 추론 요청을 보낸다. Anthropic 약관이 서드파티 도구의 구독 자격 증명 사용을 제한할 수 있으니, 그 위험을 받아들이지 않으면 꺼 둔다. |
| `quota_lookup` | bool | `true` | `false` 면 키체인의 OAuth 토큰을 읽지 않고 `api.anthropic.com` 도 부르지 않는다. 상태 표시줄의 5h/7d 수치가 빈다. ⚠ 조회는 Claude Code 로그인 토큰을 Claude Code 밖에서 쓴다(사용량 읽기만). Anthropic 약관이 서드파티 도구의 구독 자격 증명 사용을 제한할 수 있다. [SECURITY.md](../SECURITY.md) 참고. |
| `keep_awake` | bool | `true` | `false` 면 세션이 일하는 동안에도 `caffeinate` 를 잡지 않는다. |
| `compact_history` | `["YYYY-MM-DD", int\|null]` 목록 | `[]` | 자동 압축 기준 이력: 적용 날짜, 토큰 수(`null` = 끔). 날짜는 엄격히 오름차순, 최대 50행, 값은 1000~10000000. `[]` 면 현재 설정만. |
| `port` | int | `8799` | 뷰어 포트, 1024~65535. 범위 밖은 맞추지 않고 거부한다. [포트](#포트) 참고. |
| `features` | 객체 `{id: bool}` | `{}` | 기능 켜고 끄기(`features/<id>.json`). 없는 id 는 켜짐. 의존 기능이 꺼지면 같이 꺼진다. 모르는 id 는 거부한다. |
| `pipeline_apply` | `{mode, projects}` | `{"mode": "auto", "projects": {}}` | 파이프라인 탭 «적용». `mode` 는 `auto`·`ask`·`off`. `projects` 는 `{절대 경로: mode}`, 최대 200개. `hooks/pipelines_brief.py` 가 읽는다. |
| `mailbox_watch` | `{mode, projects}` | `{"mode": "on", "projects": {}}` | 설정 «메일박스 감시». `mode` 는 `on`·`off`, `projects` 는 위와 같고 가장 긴 접두 경로가 이긴다. SessionStart 훅이 읽는다. |
| `claude_roots` | `{dir, label}` 목록 | `[]` | 더 읽을 Claude Code 설정 폴더. [Claude 계정 여러 개](#claude-계정-여러-개) 참고. |

서버 쪽 키는 뷰어를 재시작해야 적용된다.

### 포트

정하는 순서: `--port N`(서버만) > `SIDEREUS_PORT` > `port` > 8799. 서버, `sidereus_cli.py`, MCP 서버,
`hooks/file_peers_notice.py`, `ext-hooks/ext_hook.py`, 절약 훅이 모두 같은 방식으로 읽는다.
`sidereus_cli.py start --port N` 은 그 값을 설정 파일에 쓴다. 바꾼 뒤에는 새 주소로 탭을 연다.

설정에서 «포트» 를 저장하면 같은 확인 창에서 `~/.claude/settings.json` 의 `env.OTEL_EXPORTER_OTLP_ENDPOINT` 포트도
옮길 수 있다. 값이 `http://127.0.0.1:<포트>` 나 `http://localhost:<포트>` 꼴일 때만이다.
돌고 있는 세션은 재시작해야 반영된다. CLI 의 `--port` 는 이 파일을 건드리지 않는다.

### Claude 계정 여러 개

Claude Code 를 설정 폴더 여러 개로 쓰면(`CLAUDE_CONFIG_DIR` 로 계정마다 하나) Sidereus 가 찾아낸다: 기본 루트
(`$CLAUDE_CONFIG_DIR`, 없으면 `~/.claude`), 뷰어가 `CLAUDE_CONFIG_DIR` 로 떠 있을 때의 `~/.claude`, `projects/` 가 있는 모든
`~/.claude-*`, `config.local.json` 의 `claude_roots`(재시작해야 적용 · `/` 와 홈은 거부).
루트 라벨은 `claude_roots` 의 라벨, 없으면 Orbit 등록부(`~/.claude-accounts`)의 이름, 그것도 없으면 폴더 이름이다.
`.claude.json` 의 계정이 기본 계정과 다른 루트를 로그인된 계정으로 본다. 기본이 아닌 루트의 세션은 이어하기 명령에 `CLAUDE_CONFIG_DIR` 가 들어간다. 사용량·파일·실패 집계는 모든 루트를 합치고, 설정·도구 화면은 기본 계정만 본다.
화면(계정 띠, 상태 표시줄 레이어, «메인 계정», 계정 선택): [GUIDE](GUIDE.ko.md#리셋-전에-할당량이-바닥날지-보기).
브라우저 쪽 키(UIS): 화면마다 `mbAcctPick.<view>`(`hist`·`tok`·`retro` 포함, 기본 «모든 계정»), «바에 표시» 는 `mbKpiAcct`. 예전 «메인 계정만» 설정은 한 번 세션의 계정 선택으로 옮겨진다.
다른 계정이 메인이면 요금제·토큰 추정·속도(기본 계정 값)는 숨긴다.
계정 설정과 로그인은 Claude Code 쪽 주제다: <https://code.claude.com/docs/en/authentication>.
터미널에서 폴더마다 계정을 고르려면 선택 플러그인 [Orbit](../plugins/orbit/README.ko.md) 를 본다. Sidereus 는 이것 없이도 동작한다.

⚠ 설정 폴더 하나에서 `/logout`·`/login` 으로 계정을 바꿔 쓰지 않는다. 세션이 섞이고 Sidereus 는 둘을 구분하지 못한다.

## 설정 API

설정 › «환경설정» 은 라우트 두 개를 쓴다. 쓸 수 있는 키: `saver_hook_dir`, `compact_history`, `viewer_me`,
`default_room`, `port`, `features`, `pipeline_apply`, `mailbox_watch`, `claude_roots`(뒤의 넷은 `GET` 의 `keys` 에 없다. 셋은 따로 창이 있고 `claude_roots` 는 아직 화면이 없다).

| 라우트 | 본문 | 응답 |
|---|---|---|
| `GET /api/prefs` | | `{ok, path, keys:{k:{value, default, src, restart:true}}, mailbox_watch, ...}`. `src` 는 `env`·`file`·`default`·`claude` |
| `POST /api/prefs/set` | `{key, value}` 또는 `{key, reset:true}` | `{ok, value, restart:true}`. 400 `{ok:false, err}`. 뷰어 Origin 이 없으면 403 |

- ⚠ 환경 변수로 정한 키는 읽기 전용이다(`src:"env"`).
- 임시 파일에 쓰고 이름을 바꿔 넣으며 `.bak` 을 남긴다. 파일에 있던 모르는 키와 `_` 키는 그대로 둔다.
- 파싱되지 않는 설정 파일은 덮어쓰지 않는다.

Claude Code 의 `settings.json` 에 쓰는 키가 둘 있다(`src:"claude"`). 기본 `~/.claude/settings.json` 과 다른 계정(`~/.claude-*`, 등록한 폴더)의 파일에 모두 쓴다. 기준은 기본 파일이다. 계정 파일이 없거나 올바르지 않거나 심볼릭 링크면 건너뛰고 새로 만들지 않으며, 화면에 그 계정을 알린다. OTEL 포트는 기본 파일에만 쓴다.

| 키 | settings.json 키 | 타입 | 비고 |
|---|---|---|---|
| `cc_auto_compact` | `autoCompactEnabled` | bool | 없으면 `true`. |
| `cc_compact_window` | `autoCompactWindow` | int | 50000~1000000. 범위를 벗어나면 맞추지 않고 거절한다. `compact_history` 에 `[오늘, 값]` 도 넣는다(같은 날짜는 교체). |

- ⚠ 이 두 키와 위의 OTEL 포트 말고는 쓰지 않는다. 나머지 바이트는 그대로다.
- 계정이 2개 이상이면 «계정별» 스위치가 나타난다. 계정마다 행이 있고 현재 값으로 채워진다. 미리보기 + 확인 뒤 값이 바뀐 계정만 쓰며, 각각 백업한다.
- 없거나 심볼릭 링크인 추가 계정은 건너뛰고 만들지 않는다.
- 새 Claude Code 세션부터 적용된다. 뷰어 재시작은 필요 없다. `reset` 은 지원하지 않는다.
- 백업: 데이터 폴더의 `tool-trash/<ts>/settings.json` (다른 계정은 `tool-trash/<ts>/<label>/settings.json`). 파일이 없거나 파싱되지 않으면 거부한다. 쓰는 동안 파일이 바뀌면 409.

## 환경 변수

| 변수 | 읽는 곳 | 기본값 | 효과 |
|---|---|---|---|
| `MAILBOX_DIR` | 모든 스크립트 | `~/.mailbox-mcp` | 데이터 폴더. |
| `MAILBOX_HOME` | `watch.sh` | 없음 | `MAILBOX_DIR` 의 옛 이름. |
| `MAILBOX_CONFIG` | `mailbox_config.py`, 훅 | 없음 | 설정 파일 경로. |
| `MAILBOX_ME` | `mailbox_core.py`, `monitor_stream.py`, `watch.sh`, `hooks/` | `self.ids[0]` | 이 세션의 신원. |
| `MAILBOX_ALIASES` | `mailbox_core.py` | `self.aliases` | 쉼표로 구분한 "나에게" 주소. |
| `MAILBOX_SELF` | `mailbox_core.py`, `watch.sh` | `self.ids` | 쉼표로 구분한, 내 글로 칠 id. `watch.sh` 는 비어 있으면 `MAILBOX_ME` 로 채운다. |
| `MAILBOX_VIEWER_ME` | `sidereus/config.py` | `viewer_me` | 뷰어 글의 이름. |
| `MAILBOX_VIEWER_ROOM` | `sidereus/config.py` | `default_room` | 뷰어가 여는 방. |
| `SIDEREUS_PORT` | 서버, CLI, MCP, 훅 | `port` | 뷰어 포트. |
| `CLAUDE_CONFIG_DIR` | 서버, MCP | `~/.claude` | Claude Code 설정 루트: 트랜스크립트, `settings.json`, 스킬·에이전트·플러그인, 그 안의 `.claude.json`(없으면 `~/.claude.json`). |
| `SIDEREUS_LAUNCHD_LABEL` | `mcp/sidereus_mcp.py` | 설정값 | MCP 다운 안내에 쓰는 뷰어 작업 라벨. |
| `SIDEREUS_QUOTA_PROBE` | `sidereus/quota.py` | `quota_probe` | `1`/`0`: 유료 할당량 탐침 켜기/끄기. |
| `SIDEREUS_QUOTA_LOOKUP` | `sidereus/quota.py` | `quota_lookup` | `1`/`0`: 키체인 읽기와 할당량 API 호출 허용/금지. |
| `MAILBOX_CARD_WAIT` | `sidereus/notes.py` | 꺼짐 | `1`: 세션이 입력을 기다리며 멈추면 알림 카드. |
| `MAILBOX_CARD_CTX` | `sidereus/notes.py` | 꺼짐 | `1`: 컨텍스트가 거의 차면 알림 카드. |
| `MAILBOX_NAG_S` | `monitor_stream.py` | `300` | 확인 없이 이만큼(초) 지나면 재촉. |
| `MAILBOX_NAG_EVERY_S` | `monitor_stream.py` | `600` | 재촉 간격(초). |
| `MAILBOX_NAG_MAX_TIMES` | `monitor_stream.py` | `2` | 메시지당 재촉 횟수. |
| `MAILBOX_NAG_MAX_AGE_S` | `monitor_stream.py` | `86400` | 이보다 오래된 메시지는 재촉하지 않는다. |
| `MAILBOX_HOLD_QUIET_S` | `monitor_stream.py` | `60` | 버스가 이만큼 조용해질 때까지 출력을 모은다. |
| `MAILBOX_HOLD_MAX_S` | `monitor_stream.py` | `180` | 모은 출력을 적어도 이 간격으로 내보낸다. |
| `MAILBOX_BODY_CAP` | `monitor_stream.py` | `3000` | 본문을 몇 글자까지 찍을지. |
| `MAILBOX_SKIP_QUIET_S` | `monitor_stream.py` | `1800` | 이만큼 전달이 없으면 경고. |
| `MAILBOX_MCP_SRC` | `backup.sh` | `~/projects/mailbox-mcp` | 코드 백업에 넣을 메일박스 MCP 서버 체크아웃. |
| `SIDEREUS_EVIDENCE` | `scripts/check.sh` | `$MAILBOX_DIR/evidence.jsonl` | 게이트 실행 기록 파일(실행당 JSON 한 줄, 개수만; 400줄을 넘으면 마지막 200줄만 남긴다). |

- ⚠ launchd 감시 데몬은 `MAILBOX_ME` 없이 뜬다. 신원은 `self.*` 에서 온다. `self.ids` 가 비었거나 틀리면 메일을 놓치거나 엉뚱한 사람 것으로 친다.
- ⚠ `self.ids[0]`(또는 `MAILBOX_ME`)이 커서 파일 이름 `stream-<id>.cursor` 가 된다. 바꾸면 커서를 처음부터 새로 만든다.

## 서비스 (macOS launchd)

macOS 전용이다. Windows 에는 뷰어 자동 실행만 있고(아래), 감시·데이터 백업 작업은 자동 실행이 없다.
그 셸 스크립트는 Git Bash 나 WSL 이 있어야 돈다.

작업마다 `~/Library/LaunchAgents/<Label>.plist` 로 저장한다. `<CODE_DIR>`·`<DATA_DIR>` 는 절대 경로로 쓴다.
launchd 는 `~` 를 풀지 않는다. `MAILBOX_DIR` 등 변수는 `EnvironmentVariables` 딕셔너리에 넣는다.
`<DATA_DIR>` 를 먼저 만든다. 없는 폴더에는 launchd 가 로그를 쓰지 못한다.

뷰어:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>io.sidereus.viewer</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string><CODE_DIR>/chat_server.py</string>
    <string>--no-open</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string><DATA_DIR>/viewer.log</string>
  <key>StandardErrorPath</key><string><DATA_DIR>/viewer.err</string>
  <key>WorkingDirectory</key><string><DATA_DIR></string>
</dict>
</plist>
```

나머지 두 작업은 같은 틀에서 아래만 바꾼다.

| 작업 | Label | ProgramArguments | 실행 시점 | 로그 |
|---|---|---|---|---|
| 감시 | `io.sidereus.watch` | `/bin/bash <CODE_DIR>/watch_loop.sh` | `RunAtLoad`, `KeepAlive`, `ThrottleInterval 10` | `<DATA_DIR>/watch.log`, `watch.err` |
| 데이터 백업 | `io.sidereus.databackup` | `/bin/bash <CODE_DIR>/backup-data.sh` | `StartCalendarInterval` Hour 9 Minute 5, `RunAtLoad`. `KeepAlive` 없음 | `<DATA_DIR>/backup/data/backup-data.log`(둘 다) |

- `watch_loop.sh` 가 `watch_bus.py` 를 다시 띄운다. `watch_bus.py` 는 새 메시지마다 일부러 종료한다.
- ⚠ 백업 작업에 `KeepAlive` 를 넣으면 끝없이 다시 돈다. 09:05 에 잠들어 있었으면 깨어날 때 돈다.
- 백업 작업을 올리기 전에 `<DATA_DIR>/backup/data` 를 만든다.

```sh
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/io.sidereus.viewer.plist   # load
launchctl kickstart -k gui/$(id -u)/io.sidereus.viewer                             # restart
launchctl bootout gui/$(id -u)/io.sidereus.viewer                                  # unload
rm ~/Library/LaunchAgents/io.sidereus.viewer.plist   # also delete it, or stop/status still see a service
```

Windows(확인 못 함): `--install-service` 가 로그온 작업 `Sidereus` 를 만든다(`schtasks /Create /SC ONLOGON`,
`pythonw.exe chat_server.py --no-open` 실행). 죽으면 다시 뜨지 않는다. 만들 때 관리자 권한이 필요할 수 있다.
`Access is denied` 가 나오면 «관리자 권한으로 실행» 한 터미널에서 다시 한다. 재시작: `schtasks /End /TN Sidereus` 다음
`schtasks /Run /TN Sidereus`. 제거: `/End` 다음 `schtasks /Delete /TN Sidereus /F`.

## 백업

| 스크립트 | 담는 것 | 결과 | 보관 |
|---|---|---|---|
| `backup.sh`(직접 실행) | `*.py`, `*.sh`, `config.example.json`, `hooks/`, `ext-hooks/`, `config.local.json`, `$MAILBOX_MCP_SRC/{src,pyproject.toml}` | `$MAILBOX_DIR/backup/mailbox-<stamp>.tar.gz` | 10개 |
| `backup-data.sh`(launchd) | `bus.jsonl`, `acks.jsonl`, `cards.jsonl`, `rooms.json`, `profiles.json`, `identity.json` | `$MAILBOX_DIR/backup/data/mailbox-data-<stamp>.tar.gz` | 7개. 바뀐 게 없으면 건너뜀 |

커서·PID 파일·presence 는 뺀다. 되살리면 전달 위치가 뒤로 감긴다. 백업은 이 컴퓨터 밖으로 나가지 않는다.

## 배포 제외

`.distignore`(gitignore 문법)에 공개본에 넣으면 안 되는 것을 적는다: `config.local.json`, 실데이터(버스·커서·presence·캐시·신원),
로그, 백업, 스크린숏, 도구 상태, 내부 노트. 설치마다 다르거나 개인 대화가 들어 있기 때문이다.

## Codex 메일 깨우기

`ext-hooks/codex-hooks-example.json` 은 `Stop` 에서 `gemini_mail_stop.py --platform codex` 를 돌린다. 메일은 다음 턴이
끝날 때 전달된다. 선택 사항: `--wake` 를 붙이면 분리된 대기 프로세스가 메일이 오면 로컬 Codex app-server 데몬 소켓으로
그 세션의 스레드에 턴 하나를 시작하고, 사람이 먼저 입력하면 끝난다. `--wait`(timeout 3600)는 `Stop` 안에서 막고 기다린다 — 사람 없이 도는 세션 전용이다.

- `ext-hooks/codex-config-example.toml` 을 `~/.codex/config.toml` 에 합친다. `default_tools_approval_mode = "approve"` 는
  메일박스 도구만 자동 승인한다. 셸과 다른 승인은 그대로다. 고친 뒤 세션을 다시 시작한다.
- `hooks.json` 을 고치면 해시가 바뀐다. `/hooks` 로 다시 승인한다.
- ⚠`--wake` 는 문서화된 app-server 메서드를 쓰지만 데몬 소켓 경로는 문서에 없고 WebSocket 전송은 실험 기능이다. Codex 업데이트로 깨질 수 있다(그때는 «메일 대기» 표시가 대신한다). ★Codex 0.163.0·0.164.0 에서 확인. macOS/Linux 만. Windows 에서는 아무것도 띄우지 않는다.
- 자세히: [훅 › Codex CLI](HOOKS.ko.md#codex-cli).

## oh-my-claudecode 와 함께 쓰기

Sidereus 는 oh-my-claudecode(OMC) 3.x·5.x 와 함께 돈다. OMC 나 `~/.claude` 는 고치지 않는다.

- **HUD 사용량.** 조회는 한 곳에서만 한다. Sidereus 가 OMC 플러그인 폴더에 3.x·5.x 두 이름으로 사용량 캐시를 쓰고,
  OMC 캐시가 더 새것이면 그쪽을 읽는다.
- **메일 전달.** OMC 훅이 `continue: false` 로 턴을 끝내면 메일박스 Stop 훅의 차단이 무시된다. 같은 메일은 다음 멈춤에 다시 전달된다.
- **이 저장소에서 `/omc-setup` 을 돌리지 않는다.** `CLAUDE.md` 를 만들고, 그러면 Claude Code 가 `AGENTS.md` 를 무시한다.
- **훅 겹침.** 5.x 는 `OMC_SKIP_HOOKS=keyword-detector,skill-injector` 로 끈다(파이프라인 실행에 걸리면
  `persistent-mode,workflow-drift-guard` 도 추가). 3.x 에는 이런 스위치가 없다.
- «도구» 화면은 OMC 명령을 같은 이름의 스킬 한 줄로 합치고 에이전트 템플릿은 감춘다.
- 다른 플러그인: [훅 › 다른 훅과 같이 쓸 때](HOOKS.ko.md#다른-훅과-같이-쓸-때) 에 훅마다 할 수 있는 일과 끄는 법이 있다.
