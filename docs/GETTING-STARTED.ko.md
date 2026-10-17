# 시작하기

[English](GETTING-STARTED.md) · **한국어**

1~2단계면 화면이 뜬다. 나머지는 필요할 때 한다.

## 1. 코드 받기

```sh
git clone https://github.com/bugsterran/sidereus.git ~/sidereus      # 폴더는 어디든 된다
```

Python 3.9 이상만 있으면 된다. macOS 기본 `/usr/bin/python3` 로 된다.
데이터(로그·캐시·메일박스·설정)는 `$MAILBOX_DIR` 에 쌓이고, 기본값은 `~/.mailbox-mcp` 다
(Windows: `%USERPROFILE%\.mailbox-mcp`).

**Windows**(실제 기기에서는 아직 확인 못 함): 이 문서의 `python3`·`/usr/bin/python3` 는 `py` 로 바꿔 쓴다.
`python3 -m sidereus …` 는 아무 폴더에서 `C:\path\sidereus\sidereus.cmd …` 로 해도 된다(`py -3`, 없으면 `python` 을 쓴다).
`py -m sidereus` 는 클론 안에서만 된다. `~/.claude/settings.json` 은 `%USERPROFILE%\.claude\settings.json` 이다.

## 2. 뷰어 띄우기

```sh
cd ~/sidereus
python3 -m sidereus start --demo --open      # 합성 데이터, :18799, 실제 데이터는 안 읽는다. Ctrl-C 로 끈다
python3 -m sidereus start --open             # 내 세션, :8799. --port N 으로 옮긴다(저장됨)
python3 -m sidereus status
python3 -m sidereus stop
```

처음 `start` 하면 `config.local.json` 을 만든다(있으면 덮어쓰지 않는다). `self.ids` 기본값 `<user>-sidereus` 는
그대로 써도 된다. 세션은 몇 초 안에 나타난다. 이 기기에서 Claude Code 를 한 번도 안 돌렸다면 경고 없이
빈 화면이 나온다. 런처 없이 띄우려면 `/usr/bin/python3 chat_server.py [--no-open] [--port N]`.
두 번째 클론이나 다른 데이터 폴더는 `--port N` 으로 다른 포트를 써야 한다. 8799 에서는 `start` 가 «다른 Sidereus(다른 데이터 폴더)» 라며 멈춘다.

기본 설정에서는 할당량 조회를 위해 macOS 키체인에서 Claude Code OAuth 토큰을 읽고, 세션이 일하는 동안
`caffeinate` 를 잡는다. 끄려면 `config.local.json` 에 `"quota_lookup": false`, `"keep_awake": false`.
[SECURITY.md](../SECURITY.md) 참고.

Windows 에서도 뷰어·트랜스크립트·메일박스는 된다. 꺼지는 것: 실시간 프로세스 확인, 터미널 이동, 할당량
조회, 잠자기 방지, 하네스 증거 기록(`hooks/ev_hook.py` 가 `fcntl` 을 쓴다).
셸 스크립트(`watch.sh`, `backup.sh`, `backup-data.sh`)는 Git Bash 나 WSL 이 있어야 돈다.

## 3. 계속 띄워 두기

```sh
python3 -m sidereus stop                         # 그냥 start 로 띄운 게 있으면
python3 -m sidereus start --install-service      # 로그인할 때 뜨고, 죽으면 다시 뜬다
```

macOS 는 `~/Library/LaunchAgents/io.sidereus.viewer.plist` 를 쓴다. 서비스는 `sidereus stop` 으로 꺼지지 않으니
launchctl 을 쓴다.

```sh
launchctl kickstart -k gui/$(id -u)/io.sidereus.viewer     # 재시작
launchctl bootout gui/$(id -u)/io.sidereus.viewer          # 멈춤
rm ~/Library/LaunchAgents/io.sidereus.viewer.plist         # 제거. 안 지우면 stop/status 가 서비스가 있다고 본다
```

Windows 는 `schtasks /Create /SC ONLOGON` 으로 로그온 작업 `Sidereus` 를 만들고 한 번 실행한다(확인 못 함).
로그인할 때 뜨지만 죽으면 다시 뜨지 않는다. 만들 때 관리자 권한이 필요할 수 있다. `Access is denied` 가 나오면
«관리자 권한으로 실행» 한 터미널에서 같은 `start --install-service` 를 다시 실행한다.
여기서도 `sidereus stop` 은 작업을 건드리지 않는다. 멈춤: `schtasks /End /TN Sidereus`, 다시 띄우기:
`schtasks /Run /TN Sidereus`, 제거: `/End` 다음 `schtasks /Delete /TN Sidereus /F`.

## 4. OpenTelemetry 로 세션 상태 보내기

Claude Code 는 세션 상태(생각 중, 어떤 도구)를 Sidereus 로 바로 보낼 수 있다. `~/.claude/settings.json` 의
`env` 블록에 넣는다. 포트는 뷰어 포트와 같아야 한다.

```json
"CLAUDE_CODE_ENABLE_TELEMETRY": "1",
"OTEL_LOGS_EXPORTER": "otlp",
"OTEL_METRICS_EXPORTER": "none",
"OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",
"OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:8799",
"OTEL_LOGS_EXPORT_INTERVAL": "3000"
```

새로 시작한 세션부터 적용된다. 프롬프트·응답·도구 내용은 보내지 않는다. 없어도 트랜스크립트로 동작하고,
조금 늦게 반영될 뿐이다.

## 5. MCP 와 훅

둘 중 한 방법만 고른다. ⚠ 둘 다 하면 훅이 모두 두 번 걸리고 MCP 서버도 둘(`sidereus`, `plugin:sidereus:sidereus`)이 된다.

**플러그인 (권장).** `sidereus` MCP 서버와 [HOOKS.ko.md](HOOKS.ko.md#claude-code-훅) 의 훅 9개를 등록한다.
훅은 macOS/Linux 에서 `python3` 를 부른다. Windows 에서는 PATH 에서 `py -3`, `python3`, `python` 순으로 Python 3.9 이상을 찾고
(Microsoft Store 의 `python3` 별칭은 건너뛰고, 찾은 결과는 캐시한다) Git Bash 로 돌아가니 Git for Windows 를 설치한다.
MCP 서버는 `python3` 를, `SIDEREUS_PYTHON` 이 있으면 그것을 부른다. Windows 의 `python3` 는 대개 Store 별칭이니
`setx SIDEREUS_PYTHON py` 를 한 번 실행하고 Claude Code 를 다시 띄운다(훅도 같은 변수를 쓴다).

```text
/plugin marketplace add <클론 경로>
/plugin install sidereus@sidereus
```

제거: `claude plugin uninstall sidereus@sidereus` 다음 `claude plugin marketplace remove sidereus`.

**수동.** 명령에 맡긴다(Windows: `py -m sidereus setup-claude --write`).

```sh
python3 -m sidereus setup-claude --write
```

실행할 `claude mcp add` 명령과 `settings.json`(`$CLAUDE_CONFIG_DIR`, 없으면 `~/.claude`)의 diff 를 보여 주고
`Apply? [y/N]` 을 묻는다. 승인하면 파일을 `settings.json.bak-YYYYMMDD-HHMMSS` 로 백업하고 훅을 합친 뒤 MCP 를 등록한다.
다시 실행해도 같은 항목을 두 번 넣지 않는다. 플러그인이 설치돼 있으면 훅은 넣지 않는다(두 번 실행된다).
`--yes` 는 질문을 건너뛴다(스크립트용). 터미널이 아니고 `--yes` 도 없으면 아무것도 쓰지 않는다.

손으로 하려면 이 클론의 경로와 Python 으로 만든 줄을 출력한다(아무것도 쓰지 않는다).

```sh
python3 -m sidereus setup-claude [--mailbox-mcp DIR]
```

`claude mcp add` 줄을 실행하고 훅 JSON 을 `~/.claude/settings.json` 에 합친다. macOS 에서 MCP 줄은
`claude mcp add --scope user sidereus -- /usr/bin/python3 ~/sidereus/mcp/sidereus_mcp.py` 꼴이다. Windows 에서는
`setup-claude` 가 출력한 경로를 쓴다. 훅 JSON 에는 플러그인과 같은 훅 9개가 들어 있다.

어느 쪽도 `mailbox` MCP 서버는 등록하지 않는다(6장).

에이전트는 시키지 않으면 도구를 잘 부르지 않는다. `AGENTS.md` 나 `CLAUDE.md` 에 넣는다.

```md
- Before spawning several subagents, call `sidereus_quota`; follow its advice line.
- Before editing a file other agents may touch, call `sidereus_file_peers(path)`; if another live agent
  edited it in the last 30 min, coordinate or wait.
```

## 6. 세션 사이 메일박스

메일박스는 이 저장소에 들어 있다(`bus.jsonl`, `watch.sh`, `monitor_stream.py`, `mailbox_core.py`, Stop 훅).
채팅 탭과 작업 팝업 DM 은 이미 이걸 쓴다. 세션은 둘 중 한 방법으로 메일을 본문까지 받는다.

- 즉시: Stop 비동기 훅 `hooks/mailbox_wake.py`(asyncRewake)가 쉬고 있는 세션을 깨운다. `mailbox_inbox` 로 읽는다.
  - 플러그인이나 `setup-claude` 훅 JSON(5장)을 넣으면 켜진다. 따로 띄울 것은 없다.
  - `watch.sh` 는 일반 터미널용 선택 사항이다.
  - 세션 시작 안내는 설정 `mailbox_watch` 로 전체 또는 프로젝트별로 끌 수 있다.
- 턴 끝: Stop 훅 `hooks/mailbox_stop.py` 가 알린다(보낸 사람과 개수만). [HOOKS.ko.md](HOOKS.ko.md) 참고.

세션이 스스로 글을 올리려면 별도 MCP 패키지 `mailbox-mcp` 가 필요하다. 이 저장소에는 없다.

```sh
claude mcp add --scope user mailbox -- uv --directory <path-to-mailbox-mcp> run mailbox-mcp
```

## 7. 확인

- 세션 서랍(오른쪽 위)에 내 세션이 보인다.
- 상태 표시줄의 5시간 수치에 `≈` 가 붙어 나온다. 추정치라 몇 주기 지나면 정확해진다.
- 새 세션에 `sidereus_quota` 를 불러 보라고 하면 몇 줄로 답한다.

평소 쓰는 법은 스크린샷과 함께 [GUIDE.ko.md](GUIDE.ko.md) 에 있다.

## 제거

1. `python3 -m sidereus stop`. 서비스는 3장, 플러그인은 5장대로 지운다.
2. 클론 폴더를 지운다. 데이터까지 지우려면 `~/.mailbox-mcp` 도 지운다.

## 이상할 때

| 증상 | 할 일 |
|---|---|
| 화면이 안 뜬다 | `python3 -m sidereus status` 로 보고 띄운다(서비스면 `launchctl kickstart -k ...`, Windows 는 `schtasks /Run /TN Sidereus`) |
| 코드를 고쳤는데 안 바뀐다 | 화면은 시작할 때 만들어진다. 뷰어를 재시작한다. |
| 세션이 하나도 안 보인다 | `~/.claude/projects/` 에 최근 `.jsonl` 파일이 있는지 본다. `CLAUDE_CONFIG_DIR` 을 쓰면 뷰어에도 같은 변수를 준다(launchd: `EnvironmentVariables`) |
| MCP 도구가 "not reachable" | 뷰어가 꺼졌거나 막 재시작했다. 다시 부른다. |
| MCP 도구가 없다 | `claude mcp add` 뒤에 시작한 세션에만 있다 |

로그: `~/.mailbox-mcp/viewer.err`. 덧붙이기만 하는 파일이라 오래된 줄은 지난 기록이지 지금 오류가 아니다.
