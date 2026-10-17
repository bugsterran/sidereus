# 시데레우스 확장하기

[English](EXTENDING.md) · **한국어**

확장 지점마다 새 파일 하나와 등록 몇 줄이면 된다. 내부 배선(상태 조각, 라우트, 웹 조각)은
[ARCHITECTURE](ARCHITECTURE.ko.md#확장).

- 메타데이터만. id, 경로, 이름, 종류, 줄, 시각, 개수. 메시지 본문과 도구 입력은 넣지 않는다.
- Python 3.9 표준 라이브러리, 네트워크 없음. 게이트: `bash scripts/check.sh --fast`.
- `sidereus/` 에 새 모듈을 넣으면 `refactor/STAGE3.md` 의 순서와 개수에 올린다. 안 그러면 `tests/test_arch.py` 가 실패한다.
- 테스트는 실제 파일, 시계, 네트워크를 쓰지 않는다. 주인 모듈을 패치한다.

## CLI 어댑터

다른 CLI 의 로컬 기록 파일에서 토큰, 모델, 하위 실행을 읽는다. 실시간 상태는 그 CLI 의 훅에서 온다([HOOKS](HOOKS.ko.md)).
`sidereus/plat_TEMPLATE.py.txt` 를 `sidereus/plat_<x>.py` 로 복사한다. 예: `plat_gemini.py`, `plat_codex.py`.
`adapter_register()`(`sidereus/adapter.py`)가 import 때 계약을 검사하고 맞지 않으면 `ValueError` 를 낸다.

| 이름 | 뜻 |
|---|---|
| `PLAT`, `KEY`, `NAME` | 훅의 `platform`, 두 글자 행 키(= 로고 `AILG.<KEY>`, `cc` 예약), 표시 이름 |
| `CHILD_LABEL`, `SCAN_MAX` | Claude 에서 띄운 실행의 라벨, 기록 파일마다 읽을 바이트 |
| `root()`, `path_ok(path)` | 데이터 폴더, 그 아래 기록 파일일 때만 True(경로가 훅 POST 로 들어온다) |
| `scan(since)` | 행 `{sid, path, cwd, project, start, kind, msgs, acts}`(+ `parent`, `rate`) |
| `session_msgs(path)` | `{id: (in, out, cache, thought, ts, model, cost 또는 None)}` 또는 None |

모두 필수다. 선택 항목(`LANE`, `harness_items`, `TIME_BUDGET_S` …)은 `sidereus/adapter.py` 에 있다.

- ⚠로컬 파일만 읽는다. 네트워크도 쓰기도 없다. 토큰과 비용은 Claude 합계에 넣지 않는다.
- 예외를 내는 `scan` 은 `[]` 와 경고 하나가 되고, `TIME_BUDGET_S`(1초)보다 느리면 경고한다.

등록은 `sidereus/ext_store.py` 에서 한다. `EXT_PLAT` 에 `PLAT: KEY` 쌍, import, `PLAT_MODS` 튜플. STAGE3 에서는 `ext_store`
앞에 둔다. 테스트: `tests/test_adapter_contract.py` 와 픽스처로 `scan` 을 보는 테스트(`tests/test_ext*.py`).

## 언어 플러그인

구조 탭 «크기» 트리맵에 언어 하나를 가르친다. 파일 `sidereus/structure_lang_<x>.py`, 예 `structure_lang_rs.py`.

```python
from sidereus.structure_plug import lang_register

lang_register("rust", {"exts": (".rs",), "scan": rs_scan,
                       "test": r"(?:_tests?|(?:^|/)tests?)\.rs$", "test_dirs": ("tests", "benches"), "skip": ("target",)})
```

| 키 | 뜻 |
|---|---|
| `exts` | 필수. `.ext` 튜플, 가장 길게 맞는 것이 이긴다 |
| `lang` | 행 언어. 문자열이나 `lang(rel, src)` |
| `scan(src)` | 트리맵에 쓸 함수 목록. `None` 은 파싱 실패 |
| `test`, `gen` | 정규식, 패턴 문자열, `rel -> bool`. 테스트 파일 / 생성된 파일 |
| `test_dirs` | 테스트를 담는 폴더(정규식이나 이름) |
| `skip` | 스캔에서 뺄 폴더 이름이나 fnmatch glob |

모르는 키는 `ValueError` 다. `structure_scan` 이 import 될 때 `structure_plug.plug_load()` 를 부르고, 이것이
`structure_lang_*.py` 를 이름순으로 모두 import 한다. 따로 등록할 것은 없다. import 에 실패한 플러그인은 경고 하나와
함께 건너뛴다.

- ⚠`structure_lang_*.py` 에 맞는 파일은 모두 플러그인이다. 도우미는 다른 이름에 둔다. `structure_lex.py`,
  `structure_c_util.py`.
- ⚠`structure_scan` 이 import 되는 도중에 실행된다. STAGE3 에서 `structure_scan` 앞의 모듈과 `structure_lex`,
  `structure_c_util` 만 import 한다. 다른 플러그인은 안 된다.
- ⚠최선 노력, 선형 시간. 틀리게 짐작하느니 놓치는 편이 낫다. 길이는 상수로 제한한다.

테스트: `tests/test_structure_lang_<x>.py` 에 트리맵, test/skip 픽스처와 1초 안에 끝나는 병적인 입력.

## 파이프라인

파이프라인은 단계의 순서이고, 스킬은 한 단계 안의 절차다(단계에 `skill` 을 지정할 수 있다).

1. 작성: `<project>/.claude/pipelines/<name>.json`(키는 아래). 저장할 때 `sidereus/pipeline_schema.py` 가,
   `check.sh --fast` 에서 `scripts/pipeline_check.mjs` 가 검사한다.
2. 전달: `pipelines_brief.py` 가 SessionStart 에 목록을 세션마다 넣는다([HOOKS](HOOKS.ko.md#pipelines_briefpy)).
3. 강제: 세션이 Agent 도구로 단계를 직접 돌리고 `[pl:<pipeline>/<단계>]` 태그를 붙인다. `pl_mark.py` 는 태그 없는
   에이전트를, `pl_flow.py` 는 잘못된 순서·에이전트·모델을 막는다([HOOKS](HOOKS.ko.md#pl_markpy),
   [pl_flow](HOOKS.ko.md#pl_flowpy)). `guards` 는 지정한 게이트를 커밋 전 필수로 만든다([가드](HOOKS.ko.md#가드-hookspl_guardpy-claude-code-만)).
4. 보기: «파이프라인» 탭([GUIDE](GUIDE.ko.md#파이프라인-진행-보기))과 타임라인([GUIDE](GUIDE.ko.md#세션이-한-일-되짚기)).

내부 구조: [dev/PIPELINE.md](dev/PIPELINE.md). CLI 별 리뷰 파이프라인과 템플릿: [REVIEW-PIPELINES.ko.md](REVIEW-PIPELINES.ko.md).

`<project>/.claude/pipelines/<name>.json`, 이름은 `[a-z0-9-]{1,40}`. 예: `.claude/pipelines/sidereus-change.json`.

```json
{ "v": 1, "name": "my-change", "title": "변경", "defaults": {"model": "inherit"},
  "stages": [ {"title": "설계", "agent": "my-designer", "task": "…", "produces": "slices"},
              {"title": "구현", "agent": "my-implementer", "fanout": "slices", "gate": "scripts/check.sh --fast"} ] }
```

- 최상위 키: `v`, `name`, `title`, `use`(`pipelines_brief.py` 가 읽는다), `rules`, `after`, `defaults`, `guards`(`requireGates`, `maxLoopBacks`), `stages`.
- 단계 키: `title`, `agent`, `model`(`inherit|opus|sonnet|haiku`), `skill`, `task`, `gate`, `produces`/`fanout`, `parallel`,
  `retry`, `onError`(`stop|continue`), `onFail {goto, max 1..5, then?, stopOn?}`, `onlyOnJump`, `ui`.
- `pipeline_schema.STAGE_TITLES` 밖의 제목은 사용자 단계다(1–40자, `task` 필요).
- «AI 설정 점검»(`STAGE_TITLES` 의 추천 제목 그대로): 프로젝트의 AI 설정(AGENTS.md/CLAUDE.md, 에이전트, 스킬, 훅, `.mcp.json`, 단계 지시)을 읽기만 하며 점검한다. 지적은 file:line.
- «프롬프트 검증»(`STAGE_TITLES` 의 추천 제목 그대로): 지정한 에이전트·스킬 프롬프트를 합성 입력으로 돌려, 약속한 것과 맞는지 프롬프트별 통과/실패로 보고한다.
- 표준 초안 «훅 변경» · «스킬 작성·변경» · «도구·MCP 추가» 가 이 두 단계로 AI 설정 작업을 점검한다.
- 단계마다 Agent 설명에 `[pl:<pipeline>/<단계>]` 를 붙인다(40자). 태그 붙은 메인 에이전트 Bash 는 2분 동안 «main» 을
  켜고 `[pl:-]` 가 끈다([HOOKS](HOOKS.ko.md#pl_markpy)).
- `onFail`, `onlyOnJump`, `onError`, `after` 는 `pl_flow.py` 의 다음 단계 안내에도 쓰인다([HOOKS](HOOKS.ko.md#pl_flowpy)).

테스트: `tests/test_pipeline*.py`. `check.sh --fast` 도 `scripts/pipeline_check.mjs` 를 돌린다.

## 다른 프로그램에서 상태 읽기

- `GET /api/v1/state` 를 쓴다(«sidereus-state v1», `sidereus/state_v1.py`, 스키마 `docs/schema/sidereus-state.v1.json`).
  `/api/state` 와 `/api/messages` 는 내부용이다(`n` 기본 200, 상한 1000, 0 이하는 400).
- v1 에는 선택 필드를 더할 수 있다. 필드를 빼거나 이름·뜻을 바꾸면 v2 다.
- Host 는 `127.0.0.1:<port>` 나 `localhost:<port>` 여야 하고, 브라우저의 cross-site·same-site 요청은 거부한다.
- ⚠v1 은 메타데이터만 담고 도구 입력에서 나온 필드(`targ`, `blocked`)는 뺀다. 메시지나 도구 내용을 담을 수 있는 필드는
  더하지 않는다.
