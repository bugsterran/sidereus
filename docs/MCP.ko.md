# 시데레우스 MCP 서버 (`sidereus`)

[English](MCP.md) · **한국어**

`mcp/sidereus_mcp.py` 로 Claude 세션이 시데레우스에 물어볼 수 있다. 읽기 전용이라 세션을 제어·차단하거나 메시지를 보내지 않는다.
답에는 메타데이터만 들어간다(id, 이름, 상태, 도구 이름, 개수, 시각).

## 등록

플러그인이 등록해 준다(`plugin:sidereus:sidereus`). Windows 에서는 플러그인 MCP 서버가 `python3` 를 그대로 부르니, PATH 에 없으면 아래처럼 손으로 등록한다. ⚠플러그인을 쓰면 아래 줄은 건너뛴다. 둘 다 하면 서버가 두 번
등록된다. 손으로 등록할 때는 macOS 에서 클론 안에서 실행한다(Windows 는 클론 안에서 `py -m sidereus setup-claude` 를 실행해 나온 `claude mcp add` 줄을 쓴다).

```sh
claude mcp add --scope user sidereus -- /usr/bin/python3 "$PWD/mcp/sidereus_mcp.py"
```

## 도구

| 도구 | 인자 | 답 |
|---|---|---|
| `sidereus_quota` | 없음 | 5h/7d 사용 %, 이번 5h 창에 이 PC 가 쓴 토큰(남은 예산은 없음), 리셋 시각, 이 속도로 바닥나는 시각, 목표 대비 속도, 절약 단계, 조언 한 줄 |
| `sidereus_file_peers` | `path`(필수), `sid`, `cwd` | 최근 30분 안에 이 파일을 고친 세션·에이전트(sid8/unit, 에이전트 종류, 프로젝트, 경과 시간, 살아 있는지)와 미커밋 여부. 없는 경로는 `no such file` |
| `sidereus_peers` | `cwd` | 같은 저장소(worktree 무관)에서 살아 있는 세션·서브에이전트: 상태, 지금 도구, ctx % |
| `sidereus_attention` | 없음 | 지금 사용자가 봐야 할 세션(라벨만) |

- `sidereus_quota` 숫자는 호출한 세션의 계정 기준이다. `CLAUDE_CONFIG_DIR` 가 있고 `~/.claude` 가 아니면 요청에
  `dir=<그 경로>` 가 붙고, 답의 첫 줄이 `account: <label>` 이다. 모르는 계정이면 `quota unavailable: unknown account` 를
  돌려준다(주 계정 숫자로 대신하지 않는다). 계정이 하나면 `dir` 를 보내지 않는다.
- 호출한 쪽은 MCP 프로세스의 cwd 로 알아낸다. Claude Code 가 세션 cwd 에서 띄우기 때문이다. `cwd` 인자가 우선한다.
- `sidereus_file_peers` 는 부모 Claude 프로세스로 호출한 세션을 찾아 `(you)` 를 붙인다. `sid` 인자가 우선한다. `sidereus_peers` 에는 자기 세션도 나온다.
- 인자는 도구마다 `inputSchema`(타입, 모르는 키, 필수)로 검사한다. 어긋나면 JSON-RPC `-32602`.
- 조언 줄은 절약 훅의 판정(`.saver-view.json` 의 `lv` 와 단계)을 옮긴 것이다. 서버에는 자체 규칙이 없다.
  훅(`~/.claude/hooks/saver.py`)은 선택 사항이고 동봉하지 않는다. 훅이나 스냅숏이 없어도 `sidereus_quota` 는 사용량을
  답하고, 단계는 비우고 조언은 «no pace verdict» 가 된다. 예상 소진 시각이 5h 리셋보다 앞이면 조언이 경고로 바뀐다.

## 구현

- 뷰어 라우트: `sidereus/routes_get.py` 의 `GET /api/agent/{quota,peers,file,attention}`. 본문은 `sidereus/agent_brief.py` 가 만든다. 다른 GET 과 같은 Host 검사를 거친다.
- 웜 호출은 2 ms 미만. 첫 `file` 호출은 소유자 인덱스를 훑느라 ~0.4 s 걸린다.
- stdio 위 JSON-RPC 2.0, 표준 라이브러리만, `/usr/bin/python3`.
- HTTP 타임아웃 8 s. 뷰어 재시작 직후 첫 호출은 3 s 를 넘을 수 있다.
- 포트: `SIDEREUS_PORT` > 설정 `port` > 8799.
- 시데레우스가 꺼져 있거나 옛 버전(404)이면 도구가 오류 문구를 돌려줄 뿐 서버는 죽지 않는다.
- ⚠ 새 라우트는 뷰어를 재시작해야 답한다. 그 전까지는 «Sidereus answered HTTP 404 … — restart it to load the /api/agent routes» 가 나온다.

테스트: `tests/test_sidereus_mcp.py`(프로토콜, 모의 HTTP 위 도구, 다운 경로, 본문 유출 없음), `tests/test_agent_brief.py`(패치한 리더 위 브리프).
